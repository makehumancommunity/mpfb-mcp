"""
The harness itself, plus the two claims cheap enough to check while proving it.

The point of this module is that it runs at all: pytest inside a headless
Blender, against an add-on resolved by suffix, is an arrangement with enough
moving parts that finding out it does not work would be much worse later than
now. The assertions are deliberately shallow - the bridge's real suite arrives
with its real code.

Named ``aaa_`` because pytest discovers alphabetically and MPFB uses the same
prefix trick to force the core checks to run first. With one module it changes
nothing; it is here so the convention is already in place when there are five.
"""

import bpy

from . import bridge_package
from . import dynamic_import


def test_addon_is_loaded():
    """mpfb_bridge"""
    package = bridge_package()
    assert package is not None, "The MPFB Bridge add-on should be loaded"
    assert package.__name__ in bpy.context.preferences.addons, \
        "The MPFB Bridge add-on should be enabled, not merely importable"


def test_command_vocabulary_is_closed():
    """commands.COMMANDS"""
    commands = dynamic_import("commands", "COMMANDS")
    assert isinstance(commands, dict), "The command table should be a plain dict"
    assert "get_status" in commands, "get_status should be in the command table"
    for name, handler in commands.items():
        assert callable(handler), "Command {:s} should map to a callable".format(name)


def test_server_is_not_listening_by_default():
    """command_server.is_running()"""
    is_running = dynamic_import("command_server", "is_running")
    assert not is_running(), \
        "The command server should be off until it is started from the preferences panel"


def test_bridge_does_not_mistake_itself_for_mpfb():
    """mpfb_resolution.find_candidates()"""
    # The resolution scan looks for module names ending in "mpfb". This add-on's
    # package ends in "mpfb_bridge", so it must not match - but the two names are
    # close enough that a future rename could break it silently, and the failure
    # would be the bridge cheerfully reporting itself as a working MPFB.
    find_candidates = dynamic_import("mpfb_resolution", "find_candidates")
    package = bridge_package()
    candidates = find_candidates()
    assert package.__name__ not in candidates, \
        "The bridge's own package should not be mistaken for MPFB"
    for candidate in candidates:
        assert not candidate.endswith("mpfb_bridge"), \
            "No bridge module should be mistaken for MPFB, but {:s} was".format(candidate)


def test_get_status_answers_in_the_three_state_vocabulary():
    """commands.get_status()"""
    commands = dynamic_import("commands", "COMMANDS")
    result = commands["get_status"]({})
    assert result["state"] in ("absent", "not_initialized", "ok"), \
        "get_status should answer with one of the three known states"
    assert result["message"], "Every state should come with a sentence explaining it"
    assert isinstance(result["candidate_modules"], list), \
        "candidate_modules should always be a list, even when empty"
    assert result["protocol_version"] >= 1, "The answer should carry a protocol version"


def test_server_starts_refuses_a_second_start_and_restarts():
    """command_server.start() / stop()"""
    # The one lifecycle claim worth checking here rather than by hand. It opens a
    # real socket, on the loopback address and on a port the OS picks, and closes
    # it again before returning - so it proves the add-on's own start/stop path
    # without leaving anything listening.
    start = dynamic_import("command_server", "start")
    stop = dynamic_import("command_server", "stop")
    is_running = dynamic_import("command_server", "is_running")
    commands = dynamic_import("commands", "COMMANDS")

    assert not is_running(), "This test needs the server stopped when it begins"

    # Port 0 asks the OS for a free one, so the test cannot collide with a bridge
    # the developer happens to have running on 9877.
    start("127.0.0.1", 0, commands)
    try:
        assert is_running(), "The server should be running after start()"

        raised = False
        try:
            start("127.0.0.1", 0, commands)
        except RuntimeError:
            raised = True
        assert raised, "Starting an already-running server should raise RuntimeError"
    finally:
        stop()

    assert not is_running(), "The server should not be running after stop()"

    start("127.0.0.1", 0, commands)
    restarted = is_running()
    stop()
    assert restarted, "The server should be able to start again after being stopped"


def test_start_operator_refuses_background_mode():
    """mpfb_bridge.server_start in --background"""
    # Regression test for a bug the live verification found. `bpy.app.timers`
    # callbacks are driven by Blender's event loop and a --background Blender has
    # none, so before the guard existed the operator bound the socket, registered
    # a timer that could never fire, and reported FINISHED - leaving a server that
    # accepted connections and answered none of them. Every client hung until its
    # own timeout.
    #
    # This suite always runs headless, so `bpy.app.background` is True here and the
    # refusal is directly assertable. That is the whole reason this test can exist.
    is_running = dynamic_import("command_server", "is_running")

    assert bpy.app.background, "This suite is expected to run in a --background Blender"
    assert not is_running(), "This test needs the server stopped when it begins"

    try:
        bpy.ops.mpfb_bridge.server_start()
    except RuntimeError:
        # bpy.ops raises when an operator reports an ERROR and cancels, which is
        # what refusing looks like from a script.
        pass

    assert not is_running(), \
        "The start operator must not bind a socket in background mode, where nothing can answer"
