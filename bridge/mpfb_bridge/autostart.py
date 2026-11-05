"""
Starting the server when Blender has started, because a person ticked a box.

**This reverses a decision, and what it rests on is the tick.** FR 029 refused
autostart because a socket that appears because software was installed is what
the bridge exists to improve on. The box is off by default, only the person
editing the preferences can tick it, and no command can read or write it, so
installing still opens nothing and starting is still a second, separate act
([FR 058](../../feature-requests/done/058-autostarting-the-bridge/README.md)).

**A one-shot timer, because the event loop is what "started" means.** Timers run
from the window manager's main loop, so this fires after every add-on has
registered, after a ``.blend`` named on the command line has loaded, and after any
``--python`` script has run. ``persistent=True`` is not optional: loading that
``.blend`` would otherwise remove the timer before it ever fired. The box is read
when the timer fires rather than in ``register()``, where the context is
restricted and nothing is gained by reading early.

**Never in a background Blender.** A background Blender is not only somebody's
server: it is every render, every ``--command extension build`` and this add-on's
own test suite. A setting made in a window must not turn those into processes that
bind a port. They could not be served in any case, since a background Blender runs
no timers; ``blender --background --command mpfb_bridge`` is the way to ask there.

**A failure is quiet.** A second Blender finding the port taken is the expected
case once this box exists rather than a fault, so it raises nothing and opens no
popup. It goes in the panel's error line and in the log, and the panel's Start
button still works.

The same ``register()`` runs when the add-on is re-enabled or scripts are reloaded
in a running Blender, so with the box ticked those start the server as well.
Telling them apart from a real startup is not worth a second code path.
"""

__all__ = (
    "cancel",
    "run_once",
    "schedule",
    "start_if_wanted",
)

import bpy

from . import addon_preferences
from . import command_server
from .log import get_logger
from .ui import start_server

_LOG = get_logger("autostart")


def start_if_wanted(background):
    """Start the server if the box asks for it and this Blender can serve.

    ``background`` is an argument so that a suite which only ever runs in a
    background Blender can still ask what a windowed one would do. Leaves a
    running server alone: a ``--python`` script may have started it first, and
    nothing is wrong with that.
    """
    if background or command_server.is_running():
        return
    preferences = addon_preferences.read()
    if preferences is None or not preferences.autostart:
        return
    problem = start_server(preferences, automatic=True)
    if problem:
        _LOG.warning(problem)


def run_once():
    """The timer callback. Returning ``None`` is what makes it fire only once."""
    start_if_wanted(bpy.app.background)


def schedule():
    """Arrange for :func:`run_once` to fire, unless this Blender has no event loop."""
    if bpy.app.background:
        return
    if not bpy.app.timers.is_registered(run_once):
        bpy.app.timers.register(run_once, first_interval=0.0, persistent=True)


def cancel():
    """Remove a one-shot that has not fired. Safe to call when there is none.

    Otherwise a disable in Blender's first moments would leave a callback into an
    add-on that has been unregistered.
    """
    if bpy.app.timers.is_registered(run_once):
        bpy.app.timers.unregister(run_once)
