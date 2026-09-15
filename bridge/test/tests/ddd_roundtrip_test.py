"""
A real request over a real socket, in a Blender with no screen.

**This module is why FR 029 added a headless drive mechanism.** Before it, the
bridge's own suite could call into every module and never once exercise the
thing the add-on exists to be: the transport. The GUI path cannot be tested
here - ``bpy.app.timers`` callbacks need an event loop and ``blender
--background`` has none, which is why the start operator refuses - so without
``poll_blocking`` the socket was the one part of the add-on its tests could not
reach.

The arrangement is the same one the add-on has in production, which is most of
the value: **the client runs on a thread and the dispatch runs on the main
one.** A test that drove both from one thread would prove the framing and
nothing about the concurrency. It needs no second Blender process.

What is checked here is framing and the round trip. The decisions a request goes
through are ``ccc_dispatch_test``'s; a test that asserted both over a socket
would be slower and no more convincing.
"""

import json
import socket
import threading
import time

from . import bridge_module
from . import dynamic_import

_TIMEOUT = 15.0


def _pump(command_server, thread):
    """Drive the server from the main thread until the client is done.

    This is what ``cli.py`` does in a loop, with a deadline so that a hung
    client fails the test rather than the suite.
    """
    deadline = time.monotonic() + _TIMEOUT
    while thread.is_alive() and time.monotonic() < deadline:
        command_server.poll_blocking(0.02)
    thread.join(timeout=5.0)


def _roundtrip(chunks, delay=0.0):
    """Send the given byte chunks as one request and return the decoded answer.

    Chunks rather than bytes so that a caller can split a request where it
    likes: the framing's whole job is that where the split falls does not
    matter.
    """
    commands = dynamic_import("commands", "COMMANDS")
    command_server = bridge_module("command_server")

    if command_server.is_running():
        command_server.stop()

    # Port 0: the OS picks, so this cannot collide with a bridge the developer
    # happens to have running on 9877.
    command_server.start("127.0.0.1", 0, commands)
    host, port = command_server.bound_address()

    received = []
    failures = []

    def client():
        try:
            connection = socket.create_connection((host, port), timeout=_TIMEOUT)
            try:
                for chunk in chunks:
                    connection.sendall(chunk)
                    if delay:
                        time.sleep(delay)
                buffer = b""
                while b"\0" not in buffer:
                    data = connection.recv(65536)
                    if not data:
                        break
                    buffer += data
            finally:
                connection.close()
            received.append(buffer)
        except Exception as error:  # pylint: disable=broad-except
            # Carried back rather than raised: an exception on this thread would
            # otherwise be printed and the test would fail on an empty list with
            # no explanation of why.
            failures.append(error)

    thread = threading.Thread(target=client, name="mpfb_bridge_test_client")
    thread.start()
    try:
        _pump(command_server, thread)
    finally:
        command_server.stop()

    assert not failures, "The client thread raised: {!r}".format(failures[0])
    assert received, "The client thread produced nothing within {:.0f} seconds".format(_TIMEOUT)
    assert b"\0" in received[0], "The server closed without sending a complete frame"
    return json.loads(received[0].split(b"\0")[0])


def _framed(payload):
    """One request object as the bytes that go on the wire."""
    return (json.dumps(payload) + "\0").encode("utf-8")


def test_a_request_crosses_a_real_socket_and_comes_back():
    """command_server.poll_blocking() end to end"""
    answer = _roundtrip([_framed({"command": "get_status"})])

    assert answer["status"] == "ok", "A get_status over the socket should succeed"
    assert answer["command"] == "get_status", "The envelope should name the command it answered"
    assert answer["protocol_version"] >= 1, "The envelope should carry the protocol version"
    assert answer["result"]["state"] in ("absent", "not_initialized", "ok"), \
        "The result should carry one of the three known states"


def test_an_error_crosses_the_socket_as_an_envelope():
    """command_server.poll_blocking() with a refused request"""
    answer = _roundtrip([_framed({"command": "not_a_command"})])

    assert answer["status"] == "error", "A refused command should come back as an error envelope"
    assert answer["error"] == "unknown_command", "and should carry the slug a caller branches on"
    assert answer["known_commands"], "and should still list the vocabulary"


def test_a_request_split_inside_a_multibyte_character_is_reassembled():
    """command_server framing across recv() boundaries"""
    # The case byte-level framing exists to make uninteresting. Asset and preset
    # names in this ecosystem are not reliably ASCII, and a frame decoded before
    # its boundary was found would break on exactly this.
    #
    # ensure_ascii=False on purpose: the default escapes non-ASCII to \\uXXXX,
    # which would put pure ASCII on the wire and make this pass without testing
    # anything - hence the assertion that the split really is mid-character.
    payload = (json.dumps({"command": "get_status"}, ensure_ascii=False)[:-1]
               + ', "note": "Hättebröd-日本語-\U0001f9d4"}\0').encode("utf-8")
    marker = "日".encode("utf-8")
    cut = payload.find(marker) + 1

    assert 0 < cut < len(payload), "The test payload should contain the multi-byte marker"
    assert payload[cut] & 0xC0 == 0x80, \
        "The cut should land on a UTF-8 continuation byte, or this tests nothing"

    # An unknown envelope key, so the request is served rather than refused for
    # a reason that has nothing to do with framing.
    answer = _roundtrip([payload[:cut], payload[cut:]], delay=0.05)
    assert answer["status"] == "ok", "A request split mid-character should be reassembled"


def test_a_request_arriving_one_byte_at_a_time_is_reassembled():
    """command_server framing across many reads"""
    payload = _framed({"command": "get_status"})
    answer = _roundtrip([payload[index:index + 1] for index in range(len(payload))])

    assert answer["status"] == "ok", "A request arriving a byte at a time should be reassembled"


def test_bytes_after_the_delimiter_are_ignored():
    """command_server framing past the NUL"""
    # One request per connection, so anything after the delimiter is not a
    # second request and must not be parsed as one. This assertion used to live
    # in FR 028's check_bridge.py; it moved here when that script's payload
    # stopped being accepted, and it is worth keeping somewhere.
    answer = _roundtrip([_framed({"command": "get_status"}) + b"trailing rubbish"])

    assert answer["status"] == "ok", "Bytes after the NUL delimiter should be ignored"


def test_invalid_json_is_an_error_rather_than_a_dropped_connection():
    """command_server framing with a malformed frame"""
    answer = _roundtrip([b"{this is not json\0"])

    assert answer["error"] == "malformed_request", \
        "Unparseable bytes should be answered, not silently hung up on"


def test_the_server_answers_several_requests_in_sequence():
    """command_server.poll_blocking() over repeated connections"""
    # One request per connection, which means the interesting failure is a
    # client slot or a socket not being released. Three is enough to catch it;
    # a leak shows up on the second.
    for index in range(3):
        answer = _roundtrip([_framed({"command": "list_commands"})])
        assert answer["status"] == "ok", "Call {:d} should have succeeded".format(index + 1)
        assert answer["result"]["command_count"] >= 2, \
            "list_commands should report the commands in the table"
