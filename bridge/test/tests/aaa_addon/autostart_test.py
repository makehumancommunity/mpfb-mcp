"""
FR 058's checkbox and what a background Blender does with it, as far as a suite with no
event loop can say.

**What this can establish is the decision.** ``autostart.start_if_wanted()`` takes
``background`` as an argument, so the answers a windowed Blender would get are asserted
here, each binding a real socket. What it cannot establish is that the timer fires in a
window at the right moment, that a second Blender finds the port taken, or that a
real signal stops the real command: those are the request's own ``live_check.py``.

The preference is changed and put back in every test that changes it. Nothing is saved,
so a developer's own ``userpref.blend`` cannot be touched by this module.
"""

import socket
from types import SimpleNamespace

import bpy
import pytest

from .. import bridge_module
from .. import bridge_package


def _preferences():
    return bpy.context.preferences.addons[bridge_package().__name__].preferences


def _free_port():
    """A port nothing holds right now, above the preference's minimum of 1024."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(name="box")
def _box():
    """The checkbox ticked, on a free port, with the server stopped however the test ends."""
    command_server = bridge_module("command_server")
    timer = bridge_module("timer")
    ui = bridge_module("ui")
    preferences = _preferences()
    saved = (preferences.autostart, preferences.port, preferences.host)
    assert not command_server.is_running(), "This test needs the server stopped when it begins"

    preferences.autostart = True
    preferences.port = _free_port()
    preferences.host = "127.0.0.1"
    try:
        yield preferences
    finally:
        command_server.stop()
        timer.unregister_timer()
        ui._State.last_error = ""  # pylint: disable=protected-access
        ui._State.started_automatically = False  # pylint: disable=protected-access
        preferences.autostart, preferences.port, preferences.host = saved


def test_the_box_is_off_by_default():
    """MPFB_BRIDGE_Preferences.autostart"""
    # The default being off is the whole of what FR 029's posture rests on now, so it is
    # read off the property rather than off a preference somebody may have changed.
    properties = bridge_module("ui").MPFB_BRIDGE_Preferences.bl_rna.properties
    assert properties["autostart"].default is False, "The checkbox must be off until ticked"


def test_a_ticked_box_starts_a_windowed_blender(box):
    """autostart.start_if_wanted(background=False)"""
    command_server = bridge_module("command_server")
    ui = bridge_module("ui")

    bridge_module("autostart").start_if_wanted(False)

    assert command_server.is_running(), "A ticked box should start a Blender that has a window"
    assert command_server.bound_address()[1] == box.port, "It should bind the preferred port"
    assert bpy.app.timers.is_registered(bridge_module("timer").run), \
        "It should start the timer that drives the socket, or every client hangs"
    assert ui._State.started_automatically, "The panel should be able to say why it is open"  # pylint: disable=protected-access


def test_an_unticked_box_starts_nothing(box):
    """autostart.start_if_wanted(background=False), unticked"""
    box.autostart = False
    bridge_module("autostart").start_if_wanted(False)
    assert not bridge_module("command_server").is_running(), "An unticked box should start nothing"


def test_a_ticked_box_means_nothing_in_a_background_blender(box):
    """autostart.run_once() and start_if_wanted(background=True)"""
    # The requirement most worth keeping: a background Blender is also every render and
    # every `--command extension build`, none of which asked for a server.
    assert box.autostart
    autostart = bridge_module("autostart")
    assert bpy.app.background, "This suite is expected to run in a --background Blender"

    autostart.start_if_wanted(True)
    assert not bridge_module("command_server").is_running(), "A background Blender must not bind"

    # And the real entry point, which reads bpy.app.background for itself.
    assert autostart.run_once() is None, "The one-shot should fire once and be gone"
    assert not bridge_module("command_server").is_running(), "A background Blender must not bind"


def test_schedule_registers_nothing_in_a_background_blender(box):
    """autostart.schedule()"""
    assert box.autostart
    autostart = bridge_module("autostart")
    autostart.schedule()
    assert not bpy.app.timers.is_registered(autostart.run_once), \
        "A timer in a Blender with no event loop would never fire, so none should be registered"


def test_a_running_server_is_left_alone(box):
    """autostart.start_if_wanted() after something else started it"""
    # A --python script may have got there first. A second start would raise, and the
    # panel would then blame the box for a server that is working.
    command_server = bridge_module("command_server")
    ui = bridge_module("ui")
    commands = bridge_module("commands").COMMANDS

    command_server.start("127.0.0.1", box.port, commands)
    bridge_module("autostart").start_if_wanted(False)

    assert command_server.is_running(), "The server already running should still be running"
    assert not ui._State.last_error, "Finding it running is not a failure"  # pylint: disable=protected-access
    assert not ui._State.started_automatically, "The box did not start this one"  # pylint: disable=protected-access


def test_a_held_port_is_quiet(box):
    """autostart.start_if_wanted() with the port taken"""
    # A second Blender finding the port taken is the expected case once this box exists.
    command_server = bridge_module("command_server")
    ui = bridge_module("ui")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", box.port))
        holder.listen(1)
        bridge_module("autostart").start_if_wanted(False)

    assert not command_server.is_running(), "A held port should leave the server stopped"
    assert "automatically" in ui._State.last_error, \
        "The panel should say the automatic start failed, not only that something did"  # pylint: disable=protected-access
    assert not ui._State.started_automatically
    assert not bpy.app.timers.is_registered(bridge_module("timer").run), \
        "A failed start should leave no timer polling nothing"


def test_start_server_answers_with_its_problem_and_raises_nothing(box):
    """ui.start_server()"""
    # The sequence the operator and the box share. The operator's refusal of background
    # mode is `test_start_operator_refuses_background_mode`'s; this is what is behind it.
    start_server = bridge_module("ui").start_server

    assert start_server(box) is None, "A start that worked should have nothing to report"
    assert bridge_module("command_server").is_running()
    assert not bridge_module("ui")._State.started_automatically, \
        "A click is not automatic"  # pylint: disable=protected-access

    message = start_server(box)
    assert "already running" in message, "A second start should say why it failed, not raise"


def test_unregister_removes_a_pending_one_shot():
    """mpfb_bridge.unregister()"""
    # Otherwise disabling the add-on in Blender's first moments leaves a callback into an
    # add-on that has gone. The one-shot is registered by hand, since schedule() rightly
    # refuses to here; it cannot fire, for the same reason.
    package = bridge_package()
    autostart = bridge_module("autostart")
    bpy.app.timers.register(autostart.run_once, first_interval=3600.0, persistent=True)
    try:
        autostart.cancel()
        assert not bpy.app.timers.is_registered(autostart.run_once), \
            "cancel() should remove a one-shot that has not fired"
        autostart.cancel()  # And it should be safe with none there.

        bpy.app.timers.register(autostart.run_once, first_interval=3600.0, persistent=True)
        package.unregister()
        package.register()
        assert not bpy.app.timers.is_registered(autostart.run_once), \
            "unregister() should remove a one-shot that has not fired"
    finally:
        if bpy.app.timers.is_registered(autostart.run_once):
            bpy.app.timers.unregister(autostart.run_once)


class _FakeLayout:
    """Enough of a layout to record what a panel draws, since a real one needs a redraw."""

    def __init__(self, drawn):
        self.drawn = drawn

    def column(self):
        return self

    def box(self):
        return self

    def separator(self):
        pass

    def prop(self, _owner, name):
        self.drawn.append(name)

    def operator(self, name, **_kwargs):
        self.drawn.append(name)

    def label(self, text="", **_kwargs):
        self.drawn.append(text)


def _draw():
    """What the panel draws now, through its real ``draw()``."""
    panel = bridge_module("ui").MPFB_BRIDGE_Preferences
    drawn = []
    stand_in = SimpleNamespace(
        layout=_FakeLayout(drawn),
        _draw_mpfb_status=panel._draw_mpfb_status,  # pylint: disable=protected-access
        _draw_activity=panel._draw_activity)  # pylint: disable=protected-access
    panel.draw(stand_in, None)
    return drawn


def test_the_panel_offers_the_box_and_says_who_started_the_server(box):
    """MPFB_BRIDGE_Preferences.draw()"""
    assert "autostart" in _draw(), "The panel should offer the checkbox"
    assert not any("automatically" in line for line in _draw()), \
        "A stopped server has nothing to explain"

    bridge_module("autostart").start_if_wanted(False)
    assert box.autostart
    assert any("automatically" in line for line in _draw()), \
        "The panel should say that the box started this server"
