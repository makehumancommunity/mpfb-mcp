"""
Preferences, the two operators and the panel that starts and stops the server.

There is no MPFB-style panel in the 3D view here, deliberately. The bridge has
exactly one thing a user does with it - turn the socket on and off - and that
belongs where the user already went to enable the add-on.

**Every operator id starts with ``mpfb_bridge.``, never ``mpfb.``.** That prefix
is MPFB's, this is a different extension, and two installed add-ons registering
the same ``bl_idname`` is the kind of collision that fails quietly and is then
very hard to see.

**The server is off until started.** Not a preference, not an auto-start timer: a
listening socket that appears because software was installed is exactly the
posture the pivot is meant to improve on, and "installation is the consent" only
holds if starting it is a second, separate act.
"""

__all__ = (
    "CLASSES",
    "MPFB_BRIDGE_Preferences",
    "MPFB_BRIDGE_OT_server_start",
    "MPFB_BRIDGE_OT_server_stop",
)

import bpy

from . import command_server
from .commands import COMMANDS
from .commands import BRIDGE_VERSION
from .log import get_logger

_LOG = get_logger("ui")


class _State:
    """Somewhere to put a failure that happened when nobody was drawing.

    The timer and the socket outlive the redraw that started them, so an error
    raised after the panel was drawn has nowhere to be reported. Stashing it here
    and painting it on the next redraw is the pattern blender lab's add-on uses,
    and it is the difference between a silent no-op and a message.
    """

    last_error = ""


def _update_timer_interval_active(self, _context):
    # Cached on the server module rather than read per tick: the timer fires many
    # times a second and a preferences lookup is not free.
    command_server.timer_internal_vars_calc(active=self.timer_interval_active)


class MPFB_BRIDGE_Preferences(bpy.types.AddonPreferences):
    """Where the socket is configured and switched on."""

    bl_idname = __package__

    host: bpy.props.StringProperty(
        name="Host",
        description="Address the command server binds to. Leave this at 127.0.0.1 unless you know "
                    "why you are changing it: any address but the loopback one exposes Blender to "
                    "the network",
        default=command_server.DEFAULT_HOST)

    port: bpy.props.IntProperty(
        name="Port",
        description="Port the command server listens on. 9877 rather than 9876, which is the "
                    "default for both of the general-purpose Blender MCP add-ons and may already "
                    "be in use",
        default=command_server.DEFAULT_PORT,
        min=1024,
        max=65535)

    timer_interval_active: bpy.props.FloatProperty(
        name="Poll interval",
        description="Seconds between checks for incoming commands while a client is active. "
                    "Lower is more responsive and costs a little idle CPU",
        subtype="TIME_ABSOLUTE",
        default=command_server.TIMER_INTERVAL_ACTIVE,
        min=0.01,
        max=1.0,
        update=_update_timer_interval_active)

    def draw(self, _context):
        """Paint the preferences panel: the address, the switch, and what is running."""
        layout = self.layout

        column = layout.column()
        column.prop(self, "host")
        column.prop(self, "port")
        column.prop(self, "timer_interval_active")

        layout.separator()

        if command_server.is_running():
            layout.operator("mpfb_bridge.server_stop", icon="CANCEL")
            layout.label(text="Server is running on {:s}:{:d}".format(self.host, self.port),
                         icon="CHECKMARK")
        else:
            layout.operator("mpfb_bridge.server_start", icon="PLAY")
            layout.label(text="Server is stopped", icon="X")

        if _State.last_error:
            layout.label(text=_State.last_error, icon="ERROR")

        box = layout.box()
        box.label(text="MPFB Bridge {:s}, protocol {:d}".format(
            BRIDGE_VERSION, command_server.PROTOCOL_VERSION))
        box.label(text="{:d} command(s): {:s}".format(len(COMMANDS), ", ".join(sorted(COMMANDS))))
        box.label(text="Commands are dispatched by name. No caller-supplied code is executed.")


class MPFB_BRIDGE_OT_server_start(bpy.types.Operator):
    """Start listening for MPFB commands on the configured address"""

    bl_idname = "mpfb_bridge.server_start"
    bl_label = "Start MPFB Bridge server"

    def execute(self, context):
        """Bind the socket, then register the timer that drives it."""
        from . import timer  # pylint: disable=import-outside-toplevel

        preferences = context.preferences.addons[__package__].preferences

        if bpy.app.background:
            # Refusing here rather than starting something that cannot work.
            # `bpy.app.timers` callbacks are driven by Blender's event loop, and a
            # `--background` Blender has none - so the socket would bind, the timer
            # would register, this operator would report success, and every client
            # would hang until its own timeout. Verified: that is exactly what
            # happened before this guard existed. blender lab's add-on refuses
            # background mode for the same reason and points at a CLI command; the
            # bridge has no such command yet, so it says so plainly.
            message = ("The MPFB Bridge server cannot run in background mode: Blender runs no "
                       "event loop with --background, so the timer that answers requests would "
                       "never fire and every client would hang. Start Blender normally.")
            _State.last_error = message
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        if command_server.is_running():
            self.report({"WARNING"}, "The MPFB Bridge server is already running")
            return {"CANCELLED"}

        _State.last_error = ""
        command_server.timer_internal_vars_calc(active=preferences.timer_interval_active)

        try:
            command_server.start(preferences.host, preferences.port, COMMANDS)
        except Exception as error:  # pylint: disable=broad-except
            message = "Could not start the MPFB Bridge server: {:s}".format(str(error))
            # Blender 4.2+ gates add-ons that declare a network permission on the
            # user's online-access setting. Whether that gate reaches a loopback
            # bind is not documented either way, so rather than refusing to try,
            # name it as a suspect only when a failure has actually happened.
            if not bpy.app.online_access:
                message += (" Online access is disabled in Blender's system preferences, which "
                            "may be what refused the socket.")
            _State.last_error = message
            _LOG.error(message)
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        timer.register_timer()
        self.report({"INFO"}, "MPFB Bridge server listening on {:s}:{:d}".format(
            preferences.host, preferences.port))
        return {"FINISHED"}


class MPFB_BRIDGE_OT_server_stop(bpy.types.Operator):
    """Stop listening for MPFB commands"""

    bl_idname = "mpfb_bridge.server_stop"
    bl_label = "Stop MPFB Bridge server"

    def execute(self, _context):
        """Close the socket, then unregister the timer."""
        from . import timer  # pylint: disable=import-outside-toplevel

        command_server.stop()
        timer.unregister_timer()
        _State.last_error = ""
        self.report({"INFO"}, "MPFB Bridge server stopped")
        return {"FINISHED"}


# Registered in this order and unregistered in the reverse, which is what the
# add-on's __init__ does with it. A ClassManager of MPFB's kind would be overkill
# for three classes.
CLASSES = (
    MPFB_BRIDGE_Preferences,
    MPFB_BRIDGE_OT_server_start,
    MPFB_BRIDGE_OT_server_stop,
)
