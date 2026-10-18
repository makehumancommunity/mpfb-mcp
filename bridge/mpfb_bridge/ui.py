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
holds if starting it is a second, separate act. An autostart option was
considered and refused for that reason rather than overlooked.

**The export directory is a preference because the human must choose it.**
``export_character`` takes only a file name; the directory is read by
[`export_directory.py`](export_directory.py) from here (or from ``--export-dir``
headless), so nothing that can reach the socket chooses where a file is written.

**The panel says what is true, not only what is configured.** It reports where
MPFB was found and what state it is in, and - once the server is up - how many
requests it has answered and what the last one was. The commonest failure in
this whole system is MPFB not being where the bridge looked, and before this the
only way to learn that was to make a call from somewhere else and read the
answer.
"""

__all__ = (
    "CLASSES",
    "MPFB_BRIDGE_Preferences",
    "MPFB_BRIDGE_OT_server_start",
    "MPFB_BRIDGE_OT_server_stop",
)

import time

import bpy

from . import command_server
from . import mpfb_resolution
from . import stats
from .cli import CLI_COMMAND_ID
from .commands import COMMANDS
from .log import get_logger
from .version import BRIDGE_VERSION

_LOG = get_logger("ui")


class _State:
    """Somewhere to put a failure that happened when nobody was drawing.

    The timer and the socket outlive the redraw that started them, so an error
    raised after the panel was drawn has nowhere to be reported. Stashing it here
    and painting it on the next redraw is the pattern blender lab's add-on uses,
    and it is the difference between a silent no-op and a message.
    """

    last_error = ""


def _clock(timestamp):
    """A wall-clock time for the panel. Local, to the second, no date.

    The panel reports what happened during this Blender session, so the date is
    noise and the seconds are the part a developer watching a client actually
    compares against.
    """
    if not timestamp:
        return "-"
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


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

    export_directory: bpy.props.StringProperty(
        name="Export directory",
        description="Where mpfb_export_character writes the files it exports. A client names only "
                    "the file, never the directory, so this is the one place the destination is "
                    "chosen. Empty means <MPFB user data>/exports. A directory named here that "
                    "does not exist is refused rather than created",
        subtype="DIR_PATH",
        default="")

    def draw(self, _context):
        """Paint the preferences panel: the address, the switch, and what is happening."""
        layout = self.layout

        column = layout.column()
        column.prop(self, "host")
        column.prop(self, "port")
        column.prop(self, "timer_interval_active")
        column.prop(self, "export_directory")

        layout.separator()

        if command_server.is_running():
            layout.operator("mpfb_bridge.server_stop", icon="CANCEL")
            address = command_server.bound_address()
            # The bound address rather than the preference, which may say port 0.
            layout.label(text="Server is running on {:s}:{:d}".format(*address) if address
                         else "Server is running", icon="CHECKMARK")
        else:
            layout.operator("mpfb_bridge.server_start", icon="PLAY")
            layout.label(text="Server is stopped", icon="X")

        if _State.last_error:
            layout.label(text=_State.last_error, icon="ERROR")

        self._draw_mpfb_status(layout)
        if command_server.is_running():
            self._draw_activity(layout)

        box = layout.box()
        box.label(text="MPFB Bridge {:s}, protocol {:d}".format(
            BRIDGE_VERSION, command_server.PROTOCOL_VERSION))
        box.label(text="{:d} command(s): {:s}".format(len(COMMANDS), ", ".join(sorted(COMMANDS))))
        box.label(text="Commands are dispatched by name. No caller-supplied code is executed.")
        box.label(text="Headless: blender --background --command {:s}".format(CLI_COMMAND_ID))

    @staticmethod
    def _draw_mpfb_status(layout):
        """Say where MPFB was found and what state it is in.

        Resolved on every redraw rather than cached. The scan is a pass over
        `sys.modules`, a panel redraws only while somebody is looking at it, and
        a cached answer here would be wrong in precisely the situation this box
        exists for: the user has just enabled or fixed MPFB and wants to see
        whether it took.
        """
        resolution = mpfb_resolution.resolve()

        box = layout.box()
        if resolution.is_ok:
            box.label(text="MPFB is loaded and initialized", icon="CHECKMARK")
        elif resolution.state == mpfb_resolution.STATE_NOT_INITIALIZED:
            box.label(text="MPFB is loaded but did not finish initializing", icon="ERROR")
        else:
            box.label(text="MPFB is not loaded in this Blender", icon="X")

        if resolution.module is not None:
            version = getattr(resolution.module, "VERSION", None)
            box.label(text="Found as {:s}{:s}".format(
                resolution.module.__name__,
                ", version {:s}".format(".".join(str(part) for part in version))
                if isinstance(version, (tuple, list)) else ""))
            if resolution.module.__name__ not in bpy.context.preferences.addons:
                # MPFB's unregister() leaves its contextual information in place,
                # so a disabled MPFB still resolves. Only the preferences tell.
                box.label(text="That add-on is currently disabled", icon="ERROR")

        if len(resolution.candidates) > 1:
            # Two MPFBs is a real situation - two extension repositories, or a
            # legacy install beside an extension one - and which one wins is
            # arbitrary, so say so rather than picking quietly.
            box.label(text="More than one candidate: {:s}".format(
                ", ".join(resolution.candidates)), icon="ERROR")

    @staticmethod
    def _draw_activity(layout):
        """What the server has answered since it started."""
        counters = stats.snapshot()

        box = layout.box()
        box.label(text="{:d} request(s) answered, {:d} of them errors".format(
            counters["requests_served"] + counters["failures"], counters["failures"]))

        if counters["last_command"]:
            box.label(text="Last command: {:s} at {:s}".format(
                counters["last_command"], _clock(counters["last_command_at"])))
        else:
            box.label(text="No command has been dispatched yet")

        if counters["last_error"]:
            box.label(text="Last error at {:s}: {:s}".format(
                _clock(counters["last_error_at"]), counters["last_error"][:120]), icon="ERROR")


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
            # happened before this guard existed.
            #
            # The refusal stands, but it is no longer the end of the sentence:
            # there is now a second drive mechanism for exactly this case, and
            # naming it is the difference between a dead end and a redirect.
            message = ("The MPFB Bridge server cannot run in background mode from this operator: "
                       "Blender runs no event loop with --background, so the timer that answers "
                       "requests would never fire and every client would hang. Use "
                       "'blender --background --command {:s}' instead, which serves the same "
                       "commands from a blocking loop.".format(CLI_COMMAND_ID))
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
