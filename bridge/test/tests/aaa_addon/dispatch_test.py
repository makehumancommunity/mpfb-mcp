"""
The dispatcher: what a request becomes before any handler sees it.

These tests call ``dispatch()`` directly rather than over a socket. That is the
right level for them - the framing has its own test module, and what is under
test here is the sequence of decisions between "a JSON object arrived" and "a
handler ran": is this protocol intelligible, is this a command, are these
parameters, can MPFB run it.

**Every assertion is about the error slug, never the sentence.** That is the
contract the wire documents: a caller branches on ``error`` and reads
``message``, so a test that pinned the wording would fail on a rephrasing that
broke nothing.
"""

from .. import bridge_module
from .. import dynamic_import


def _start_with(table):
    """Start the server on an OS-assigned port with a given command table.

    The dispatcher answers out of the table it was *started* with, so a test
    that wants a command of its own has to start a server carrying it. Port 0
    means the OS picks, so this cannot collide with a bridge the developer
    happens to be running on 9877.
    """
    command_server = bridge_module("command_server")
    if command_server.is_running():
        command_server.stop()
    command_server.start("127.0.0.1", 0, table)
    return command_server


def _fake_resolution(state):
    """A Resolution in a given state, for the tests that need a broken MPFB."""
    resolution_class = dynamic_import("mpfb_resolution", "Resolution")
    return resolution_class(state, None, None, [])


def test_an_unknown_command_is_refused_and_lists_the_alternatives():
    """command_server.dispatch() with an unknown command"""
    commands = dynamic_import("commands", "COMMANDS")
    command_server = _start_with(commands)
    try:
        answer = command_server.dispatch({"command": "definitely_not_a_command"})
    finally:
        command_server.stop()

    assert answer["status"] == "error", "An unknown command should be an error"
    assert answer["error"] == command_server.ERROR_UNKNOWN_COMMAND, \
        "An unknown command should carry the unknown_command slug"
    assert "get_status" in answer["known_commands"], \
        "A refusal should list the commands that do exist, or the vocabulary is not discoverable"


def test_a_bad_parameter_is_refused_before_the_handler_runs():
    """command_server.dispatch() validates before dispatching"""
    command = dynamic_import("commands.command", "Command")
    param = dynamic_import("validation", "Param")
    ran = []

    table = {
        "spy": command(
            name="spy",
            handler=lambda params, resolution: ran.append(params) or {"ok": True},
            params=(param("limit", "integer", minimum=0),),
            requires_mpfb=False,
            summary="Records that it ran."),
    }

    command_server = _start_with(table)
    try:
        # True is an int in Python. If the handler runs, the check that exists
        # to stop exactly this did not.
        answer = command_server.dispatch({"command": "spy", "params": {"limit": True}})
    finally:
        command_server.stop()

    assert answer["error"] == command_server.ERROR_INVALID_PARAMS, \
        "A bad parameter should be invalid_params"
    assert "limit" in answer["message"], "The message should name the parameter that was wrong"
    assert not ran, "The handler must not run when validation failed"


def test_an_unknown_parameter_key_is_refused_rather_than_dropped():
    """command_server.dispatch() with a misspelled parameter"""
    commands = dynamic_import("commands", "COMMANDS")
    command_server = _start_with(commands)
    try:
        answer = command_server.dispatch(
            {"command": "list_commands", "params": {"includ_params": True}})
    finally:
        command_server.stop()

    assert answer["error"] == command_server.ERROR_INVALID_PARAMS, \
        "A misspelled parameter should be refused, not silently ignored"
    assert "includ_params" in answer["message"], "The message should quote what was not recognised"


def test_an_unknown_envelope_key_is_tolerated():
    """command_server.dispatch() ignores unknown top-level keys"""
    # The asymmetry with params is deliberate and worth pinning down: the
    # envelope belongs to the protocol and is versioned, so a client may carry a
    # key this bridge has not heard of. `params` belongs to one command whose
    # contract is declared, so a key there is a mistake.
    commands = dynamic_import("commands", "COMMANDS")
    command_server = _start_with(commands)
    try:
        answer = command_server.dispatch(
            {"command": "get_status", "code": "1 + 1", "request_id": "abc"})
    finally:
        command_server.stop()

    assert answer["status"] == "ok", "An unknown envelope key should not turn a request into an error"
    assert answer["command"] == "get_status", "The request should still have been dispatched"


def test_a_handler_gets_defaults_filled_in():
    """command_server.dispatch() passes validated params to the handler"""
    command = dynamic_import("commands.command", "Command")
    param = dynamic_import("validation", "Param")
    seen = []

    table = {
        "spy": command(
            name="spy",
            handler=lambda params, resolution: seen.append(params) or {"ok": True},
            params=(param("limit", "integer", default=7),),
            requires_mpfb=False,
            summary="Records what it was given."),
    }

    command_server = _start_with(table)
    try:
        command_server.dispatch({"command": "spy"})
    finally:
        command_server.stop()

    assert seen == [{"limit": 7}], \
        "A handler should be handed every declared parameter, defaults included, got {!r}".format(
            seen)


def test_a_command_that_needs_mpfb_is_refused_when_mpfb_is_not_usable():
    """command_server.dispatch() with requires_mpfb and a broken install"""
    command = dynamic_import("commands.command", "Command")
    resolution_module = bridge_module("mpfb_resolution")
    ran = []

    table = {
        "needs_mpfb": command(
            name="needs_mpfb",
            handler=lambda params, resolution: ran.append(1) or {"ok": True},
            requires_mpfb=True,
            summary="Needs MPFB."),
    }

    command_server = _start_with(table)
    original = resolution_module.resolve
    answers = {}
    try:
        # Both non-ok states, because they fail for different reasons and a
        # caller is told which. This suite runs against whatever Blender the
        # developer has, which may well have a working MPFB, so the states are
        # supplied rather than waited for.
        for state in (resolution_module.STATE_ABSENT, resolution_module.STATE_NOT_INITIALIZED):
            resolution_module.resolve = lambda state=state: _fake_resolution(state)
            answers[state] = command_server.dispatch({"command": "needs_mpfb"})
    finally:
        resolution_module.resolve = original
        command_server.stop()

    assert not ran, "A command requiring MPFB must not run when MPFB is not usable"
    for state, answer in answers.items():
        assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE, \
            "State {:s} should give mpfb_unavailable, not {!r}".format(state, answer.get("error"))
        assert answer["state"] == state, "The answer should say which state refused it"
        assert answer["message"], "The refusal should carry the sentence explaining that state"


def test_a_command_that_does_not_need_mpfb_runs_anyway():
    """command_server.dispatch() with requires_mpfb False and a broken install"""
    commands = dynamic_import("commands", "COMMANDS")
    resolution_module = bridge_module("mpfb_resolution")

    command_server = _start_with(commands)
    original = resolution_module.resolve
    try:
        resolution_module.resolve = lambda: _fake_resolution(resolution_module.STATE_ABSENT)
        answer = command_server.dispatch({"command": "get_status"})
    finally:
        resolution_module.resolve = original
        command_server.stop()

    assert answer["status"] == "ok", "get_status must answer even when MPFB is absent"
    assert answer["result"]["state"] == "absent", "and it should report the state it was given"


def test_a_future_protocol_version_is_refused():
    """command_server.dispatch() handshake"""
    commands = dynamic_import("commands", "COMMANDS")
    command_server = _start_with(commands)
    try:
        too_new = command_server.dispatch(
            {"command": "get_status", "protocol_version": command_server.PROTOCOL_VERSION + 1})
        too_old = command_server.dispatch(
            {"command": "get_status",
             "protocol_version": command_server.MIN_SUPPORTED_PROTOCOL_VERSION - 1})
        current = command_server.dispatch(
            {"command": "get_status", "protocol_version": command_server.PROTOCOL_VERSION})
        absent = command_server.dispatch({"command": "get_status"})
        wrong_type = command_server.dispatch(
            {"command": "get_status", "protocol_version": "1"})
    finally:
        command_server.stop()

    assert too_new["error"] == command_server.ERROR_PROTOCOL_MISMATCH, \
        "A protocol version this bridge does not speak should be refused, not guessed at"
    assert too_old["error"] == command_server.ERROR_PROTOCOL_MISMATCH, \
        "A protocol version older than the minimum should be refused too"
    assert too_new["min_supported_protocol_version"] >= 1, \
        "A mismatch should say what this bridge would accept"
    assert current["status"] == "ok", "The current protocol version should be served"
    assert absent["status"] == "ok", \
        "A request carrying no protocol version should still be served: a client written by " \
        "hand at a terminal must stay possible"
    assert wrong_type["error"] == command_server.ERROR_MALFORMED_REQUEST, \
        "A non-integer protocol version is malformed rather than a mismatch"


def test_a_handler_that_raises_becomes_an_envelope_and_not_a_dead_server():
    """command_server.dispatch() with a handler that raises"""
    command = dynamic_import("commands.command", "Command")

    def _explode(params, resolution):
        raise ValueError("deliberate")

    table = {
        "explode": command(name="explode", handler=_explode, requires_mpfb=False,
                           summary="Raises."),
    }

    command_server = _start_with(table)
    try:
        answer = command_server.dispatch({"command": "explode"})
        still_alive = command_server.is_running()
    finally:
        command_server.stop()

    assert answer["error"] == command_server.ERROR_COMMAND_FAILED, \
        "A handler that raises should be command_failed"
    assert "deliberate" in answer["traceback"], \
        "The traceback should cross the wire: the caller cannot see Blender's console"
    assert still_alive, "One failing command must not take the server down"


def test_a_result_that_cannot_be_encoded_fails_cleanly():
    """command_server.dispatch() with an unserializable result"""
    # Serializing before committing to an answer is what turns this into an
    # error envelope rather than an exception thrown halfway through writing a
    # response the caller has already started reading.
    command = dynamic_import("commands.command", "Command")

    table = {
        "unserializable": command(
            name="unserializable",
            handler=lambda params, resolution: {"thing": object()},
            requires_mpfb=False,
            summary="Returns something JSON cannot carry."),
    }

    command_server = _start_with(table)
    try:
        answer = command_server.dispatch({"command": "unserializable"})
    finally:
        command_server.stop()

    assert answer["error"] == command_server.ERROR_RESULT_NOT_SERIALIZABLE, \
        "A result that cannot be encoded should have its own slug"


def test_the_stats_follow_what_was_dispatched():
    """stats.snapshot() after dispatching"""
    commands = dynamic_import("commands", "COMMANDS")
    stats = bridge_module("stats")

    command_server = _start_with(commands)
    try:
        # start() resets the counters, so this begins from a known zero.
        assert stats.snapshot()["requests_served"] == 0, \
            "Starting the server should reset the counters"
        command_server.dispatch({"command": "get_status"})
        command_server.dispatch({"command": "nope"})
        counters = stats.snapshot()
    finally:
        command_server.stop()

    assert counters["requests_served"] == 1, "One command succeeded, so one request was served"
    assert counters["failures"] == 1, "One command was refused, so one failure was recorded"
    assert counters["last_command"] == "get_status", "The last successful command should be named"
    assert "unknown_command" in counters["last_error"], \
        "The last error should carry the slug a caller would have branched on"
