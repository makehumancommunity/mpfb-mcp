"""
``cli.py``'s parts that do not need a signal or a process of their own.

What the command does as a process - that the line reaches a pipe, that Ctrl+C stops it - is
FR 058's ``live_check.py``, since this suite runs inside the Blender it would have to signal.
"""

import signal

import bpy
import pytest

from .. import bridge_module
from .. import bridge_package


@pytest.fixture(name="preferences")
def _preferences():
    preferences = bpy.context.preferences.addons[bridge_package().__name__].preferences
    saved = (preferences.host, preferences.port)
    try:
        yield preferences
    finally:
        preferences.host, preferences.port = saved


def test_what_was_named_wins_over_the_preference(preferences):
    """cli._address_or_preference()"""
    preferences.host = "127.0.0.2"
    preferences.port = 9900
    assert bridge_module("cli")._address_or_preference("127.0.0.3", 9911) == ("127.0.0.3", 9911)  # pylint: disable=protected-access


def test_port_zero_counts_as_named(preferences):
    """cli._address_or_preference()"""
    # 0 is falsy and means "pick one for me", so it must not fall back.
    preferences.port = 9900
    assert bridge_module("cli")._address_or_preference("127.0.0.1", 0) == ("127.0.0.1", 0)  # pylint: disable=protected-access


def test_the_preference_wins_over_the_default(preferences):
    """cli._address_or_preference()"""
    preferences.host = "127.0.0.2"
    preferences.port = 9900
    assert bridge_module("cli")._address_or_preference(None, None) == ("127.0.0.2", 9900)  # pylint: disable=protected-access


def test_no_preferences_to_read_is_the_default(monkeypatch):
    """cli._address_or_preference() under --addons"""
    # Measured: `--factory-startup --addons` registers the add-on with no entry in
    # preferences.addons. That recipe must serve, not raise.
    command_server = bridge_module("command_server")
    monkeypatch.setattr(bridge_module("addon_preferences"), "read", lambda: None)
    assert bridge_module("cli")._address_or_preference(None, None) == (  # pylint: disable=protected-access
        command_server.DEFAULT_HOST, command_server.DEFAULT_PORT)


def test_handlers_are_installed_and_put_back():
    """cli._stop_on_signals() / _restore_signals()"""
    cli = bridge_module("cli")
    before = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}

    previous = cli._stop_on_signals()  # pylint: disable=protected-access
    try:
        for number in before:
            assert signal.getsignal(number) is cli._interrupt, \
                "Signal {:d} should stop the loop while it runs".format(number)  # pylint: disable=protected-access
    finally:
        cli._restore_signals(previous)  # pylint: disable=protected-access

    for number, handler in before.items():
        # A handler in C reads as None and cannot be put back; the default stands in.
        expected = signal.SIG_DFL if handler is None else handler
        assert signal.getsignal(number) == expected, \
            "Signal {:d} should not stay ours after the loop".format(number)


def test_the_loop_gets_a_window_back_when_blender_dropped_it():
    # What loading a file on the command line leaves, which a test can only supply.
    module = bridge_module("cli")
    windows = bpy.context.window_manager.windows
    if len(windows) == 0:
        pytest.skip("this Blender has no window to give back")
    with bpy.context.temp_override(window=None):
        with module._window_context():  # pylint: disable=protected-access
            assert bpy.context.window == windows[0]
            assert bpy.ops.wm.obj_export.poll()


def test_interrupt_raises_what_the_loop_catches():
    """cli._interrupt()"""
    with pytest.raises(KeyboardInterrupt):
        bridge_module("cli")._interrupt(signal.SIGTERM, None)  # pylint: disable=protected-access
