"""
The ``bpy.app.timers`` callback, and the reason every command runs on it.

``bpy`` is main-thread only. A socket server that answered from an accepted
connection's own thread would be reading and writing Blender's data from the
wrong one, which does not reliably fail - it corrupts. So the socket is
non-blocking and is drained from a timer callback instead, which Blender runs on
the main thread between its own work. Every command handler therefore executes
exactly where a button press would.

**The callback swallows everything.** An exception escaping a timer callback makes
Blender unregister the timer, so a single bad tick would leave the add-on looking
installed, enabled and running while answering nothing at all. A broad ``except``
here is not sloppiness; it is what keeps one failed command from silently killing
the server.
"""

__all__ = (
    "run",
    "register_timer",
    "unregister_timer",
)

import bpy

from . import command_server
from .log import get_logger

_LOG = get_logger("timer")


def run():
    """One tick. Returns the seconds until the next one, or ``None`` to stop."""
    if not command_server.is_running():
        # Returning None unregisters this timer, which is how stopping the server
        # from anywhere at all also stops the polling.
        return None

    try:
        did_work = command_server.poll()
    except Exception:  # pylint: disable=broad-except
        _LOG.error("The command server raised while polling", exc_info=True)
        did_work = False

    if did_work:
        command_server.timer_idle_reset()

    return command_server.timer_idle_interval()


def register_timer():
    """Start polling, unless something already is."""
    if not bpy.app.timers.is_registered(run):
        bpy.app.timers.register(
            run,
            first_interval=command_server.TIMER_INTERVAL_ACTIVE,
            persistent=True)


def unregister_timer():
    """Stop polling. Safe to call when nothing is registered."""
    if bpy.app.timers.is_registered(run):
        bpy.app.timers.unregister(run)
