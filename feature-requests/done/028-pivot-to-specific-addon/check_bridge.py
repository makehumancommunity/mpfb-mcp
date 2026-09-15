#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 028's live check: does the bridge's transport actually work inside Blender?

This is the effort's own verification, run during the effort and moved into
``done/`` with it - not a smoke item. FR 028 registers no MCP tool, so
``verification/`` gains nothing and ``tests/test_verification_smoke.py`` keeps
passing untouched.

**It is a client and nothing else.** It opens ordinary TCP connections to a
running bridge and asserts what comes back, which is precisely the position a
real caller is in and the only position from which the claims worth making can
be checked: that the socket answers, that the dispatch is closed, and that a
request split across ``recv()`` boundaries is reassembled.

Two things it deliberately cannot do. It cannot start Blender, so the add-on must
already be installed, enabled and its server started from the preferences panel.
And it cannot tell a Blender with MPFB from one without, so *which* state is
correct is an argument: run it once against each.

Usage::

    # Against a Blender with MPFB enabled
    python3 check_bridge.py --expect-state ok

    # Against a Blender without MPFB
    python3 check_bridge.py --expect-state absent

    # Any state, just exercise the transport
    python3 check_bridge.py
"""

from __future__ import annotations

__all__ = ("main",)

import argparse
import json
import socket
import sys
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9877

_FAILURES = []
_PASSES = []


def check(label, condition, detail=""):
    """One assertion. Records rather than raises, so one failure does not hide ten."""
    if condition:
        _PASSES.append(label)
        print("  PASS  {:s}".format(label))
    else:
        _FAILURES.append(label)
        print("  FAIL  {:s}\n          {:s}".format(label, str(detail)[:400]))


def send_raw(host, port, chunks, timeout=10.0):
    """Send the given byte chunks as one request and read one NUL-framed answer."""
    connection = socket.create_connection((host, port), timeout=timeout)
    try:
        for chunk in chunks:
            connection.sendall(chunk)
            if len(chunks) > 1:
                # Give the add-on's timer a chance to tick between chunks, so the
                # request genuinely spans several reads rather than arriving
                # coalesced by the kernel.
                time.sleep(0.05)
        buffer = b""
        while b"\0" not in buffer:
            data = connection.recv(65536)
            if not data:
                break
            buffer += data
    finally:
        connection.close()
    if b"\0" not in buffer:
        raise ValueError("The server closed without sending a complete response")
    return json.loads(buffer.split(b"\0")[0])


def request(host, port, **payload):
    return send_raw(host, port, [(json.dumps(payload) + "\0").encode("utf-8")])


def check_get_status(host, port, expect_state):
    print("\nget_status")
    answer = request(host, port, command="get_status")

    check("answers with an ok envelope", answer.get("status") == "ok", answer)
    check("envelope carries a protocol version",
          isinstance(answer.get("protocol_version"), int) and answer["protocol_version"] >= 1,
          answer)
    check("envelope names the command it answered", answer.get("command") == "get_status", answer)

    result = answer.get("result", {})
    state = result.get("state")
    check("state is one of the three known ones",
          state in ("absent", "not_initialized", "ok"), result)
    check("state comes with a sentence", bool(result.get("message")), result)
    check("candidate_modules is always a list", isinstance(result.get("candidate_modules"), list),
          result)
    check("result carries a protocol version",
          isinstance(result.get("protocol_version"), int), result)
    check("result names the bridge version", bool(result.get("bridge_version")), result)
    check("blender version is reported", bool(result.get("blender", {}).get("version")), result)

    if expect_state:
        check("state is {:s} as expected".format(expect_state), state == expect_state, result)

    if state == "ok":
        package = result.get("package") or ""
        check("package names a real MPFB module", package.endswith("mpfb"), result)
        check("the bridge is not reporting itself as MPFB",
              not package.endswith("mpfb_bridge"), result)
        check("MPFB is reported as enabled", result.get("enabled") is True, result)
        check("MPFB's version is reported", bool(result.get("version")), result)
    elif state == "absent":
        check("no candidate modules when absent", result.get("candidate_modules") == [], result)
        check("package is null when absent", result.get("package") is None, result)

    print("    state={!r} package={!r} version={!r} blender={!r}".format(
        state, result.get("package"), result.get("version"),
        result.get("blender", {}).get("version")))
    return result


def check_closed_vocabulary(host, port):
    print("\nthe vocabulary is closed")

    # The important one. If the add-on were an exec() server wearing a command
    # name, this string is what would run. It must come back refused, and the
    # side effect must not have happened - which get_status reports on, since a
    # bridge that had executed this would be a bridge that could execute anything.
    hostile = "__import__('bpy').data.objects.new('CHECK_BRIDGE_PWNED', None)"
    answer = request(host, port, command=hostile)
    check("a command name that is Python is refused",
          answer.get("status") == "error" and answer.get("error") == "unknown_command", answer)
    check("the refusal echoes the name it refused", answer.get("command") == hostile, answer)
    check("the refusal lists the commands that do exist",
          isinstance(answer.get("known_commands"), list) and answer["known_commands"], answer)
    check("get_status is among them", "get_status" in answer.get("known_commands", []), answer)

    # There is no 'code'/'script'/'exec' key in the protocol; sending one must
    # change nothing, not quietly find a handler.
    for smuggled in ("code", "script", "exec", "eval", "python"):
        answer = send_raw(host, port, [
            (json.dumps({smuggled: "1 + 1", "command": "get_status"}) + "\0").encode("utf-8")])
        check("an extra {!r} key is ignored rather than honoured".format(smuggled),
              answer.get("status") == "ok", answer)

    answer = request(host, port, command="get_status", params={"unexpected": True})
    check("unexpected params do not crash get_status", answer.get("status") == "ok", answer)

    # Still alive, and still reporting the same thing, after all of that.
    answer = request(host, port, command="get_status")
    check("the server is still answering afterwards", answer.get("status") == "ok", answer)


def check_malformed_requests(host, port):
    print("\nmalformed requests")

    answer = send_raw(host, port, [b"{this is not json\0"])
    check("invalid JSON is an error envelope",
          answer.get("status") == "error" and answer.get("error") == "malformed_request", answer)

    answer = send_raw(host, port, [(json.dumps([1, 2, 3]) + "\0").encode("utf-8")])
    check("a JSON array is refused",
          answer.get("status") == "error" and answer.get("error") == "malformed_request", answer)

    answer = request(host, port)
    check("a request with no command is refused",
          answer.get("status") == "error" and answer.get("error") == "malformed_request", answer)

    answer = request(host, port, command="get_status", params="not a dict")
    check("non-object params are refused",
          answer.get("status") == "error" and answer.get("error") == "invalid_params", answer)

    answer = request(host, port, command="get_status")
    check("the server survives every one of those", answer.get("status") == "ok", answer)


def check_framing(host, port):
    print("\nframing across recv() boundaries")

    # A name with characters whose UTF-8 encoding is multi-byte, which is the case
    # that byte-level framing exists to make uninteresting. Asset and preset names
    # in this ecosystem are not reliably ASCII.
    awkward = "Hättebrödsgubben-日本語-émoji-🧔"
    # ensure_ascii=False on purpose. The default escapes non-ASCII to \uXXXX, which
    # would put pure ASCII on the wire and make this whole section pass without
    # testing anything - which is what the meta-assertion below exists to catch.
    payload = (json.dumps({"command": "get_status", "params": {"note": awkward}},
                          ensure_ascii=False) + "\0").encode("utf-8")

    # Split inside a multi-byte sequence: find a continuation byte and cut there.
    marker = "日".encode("utf-8")
    cut = payload.find(marker) + 1
    check("the test really does split a multi-byte character",
          0 < cut < len(payload) and payload[cut] & 0xC0 == 0x80,
          "cut={:d}".format(cut))

    answer = send_raw(host, port, [payload[:cut], payload[cut:]])
    check("a request split inside a multi-byte character is reassembled",
          answer.get("status") == "ok", answer)

    # One byte at a time, which also spans many timer ticks.
    answer = send_raw(host, port, [payload[i:i + 1] for i in range(len(payload))], timeout=30.0)
    check("a request arriving one byte at a time is reassembled",
          answer.get("status") == "ok", answer)

    # Trailing bytes after the NUL are ignored, not treated as a second request.
    answer = send_raw(host, port, [payload + b"trailing rubbish"])
    check("bytes after the NUL delimiter are ignored", answer.get("status") == "ok", answer)


def check_repeated_calls(host, port, count=25):
    print("\nrepeated connections")
    started = time.time()
    states = set()
    for index in range(count):
        answer = request(host, port, command="get_status")
        if answer.get("status") != "ok":
            check("call {:d} of {:d} succeeded".format(index + 1, count), False, answer)
            return
        states.add(answer["result"]["state"])
    elapsed = time.time() - started
    check("{:d} sequential calls all succeeded".format(count), True)
    check("every call agreed on the state", len(states) == 1, states)
    print("    {:d} calls in {:.2f} s, {:.0f} ms each".format(
        count, elapsed, 1000.0 * elapsed / count))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--expect-state", choices=("ok", "not_initialized", "absent"), default=None,
        help="Assert the MPFB state this Blender should report. Run once with 'ok' against a "
             "Blender with MPFB enabled and once with 'absent' against one without.")
    arguments = parser.parse_args(argv)

    print("MPFB Bridge live check against {:s}:{:d}".format(arguments.host, arguments.port))

    try:
        socket.create_connection((arguments.host, arguments.port), timeout=5.0).close()
    except OSError as error:
        print("\nCannot reach the bridge: {:s}".format(str(error)))
        print("Start Blender, enable the MPFB Bridge add-on, and start its server from the "
              "add-on preferences panel.")
        return 2

    check_get_status(arguments.host, arguments.port, arguments.expect_state)
    check_closed_vocabulary(arguments.host, arguments.port)
    check_malformed_requests(arguments.host, arguments.port)
    check_framing(arguments.host, arguments.port)
    check_repeated_calls(arguments.host, arguments.port)

    print("\n{:d} passed, {:d} failed".format(len(_PASSES), len(_FAILURES)))
    if _FAILURES:
        for failure in _FAILURES:
            print("  failed: {:s}".format(failure))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
