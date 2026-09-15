#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 029's live check: the skeleton, and the claim no unit test can make.

This runs beside FR 028's [check_bridge.py](../done/028-pivot-to-specific-addon/check_bridge.py)
rather than replacing it - that one still covers the transport and the framing,
and it should still pass. What this adds is everything FR 029 introduced: the
parameter contract as seen from the wire, the handshake, ``list_commands``, and
the headless drive mechanism.

**The claim worth scripting is the last one.** A unit test only ever sees one
drive mechanism, because the suite runs headless and the GUI timer cannot fire
there. Whether a windowed Blender and a background one answer the *same* is
therefore not something the suite can establish, and it is the whole of what
requirement 7 promises. So this script can record every answer it got and
compare a later run against that record, field by field::

    # 1. GUI Blender, server started from the preferences panel
    python3 check_bridge_skeleton.py --expect-state ok --save /tmp/gui.json

    # 2. Headless, same machine, same MPFB
    blender --background --command mpfb_bridge &
    python3 check_bridge_skeleton.py --expect-state ok --compare /tmp/gui.json

``blender.background`` is expected to *differ* between those two runs and is
checked for differing rather than excluded quietly; everything else must match.

Like FR 028's script this is a client and nothing else, it cannot start Blender,
and it cannot tell a Blender with MPFB from one without - so which state is
correct is an argument, and ``--expect-state`` is how you make it.
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

# Every answer this run received, keyed by a label, for --save / --compare.
_RECORDED = {}

# Fields that legitimately differ between a GUI Blender and a background one.
# Kept as an explicit list rather than a blanket "ignore what differs", because
# the point of the comparison is that nothing else does.
_EXPECTED_TO_DIFFER = ("result.blender.background",)


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


def request(host, port, label=None, **payload):
    """One request, optionally recorded under a label for the run comparison."""
    answer = send_raw(host, port, [(json.dumps(payload) + "\0").encode("utf-8")])
    if label:
        _RECORDED[label] = answer
    return answer


def check_get_status(host, port, expect_state):
    """The status answer, including the two fields FR 029 added to it."""
    print("\nget_status")
    answer = request(host, port, label="get_status", command="get_status")

    check("answers with an ok envelope", answer.get("status") == "ok", answer)
    result = answer.get("result", {})
    state = result.get("state")

    check("state is one of the three known ones",
          state in ("absent", "not_initialized", "ok"), result)
    check("result carries the protocol version spoken",
          isinstance(result.get("protocol_version"), int), result)
    check("result carries the oldest protocol accepted",
          isinstance(result.get("min_supported_protocol_version"), int), result)
    check("the oldest accepted is not newer than the one spoken",
          result.get("min_supported_protocol_version", 99) <= result.get("protocol_version", 0),
          result)
    check("result says whether this Blender is headless",
          isinstance(result.get("blender", {}).get("background"), bool), result)
    check("result names the bridge version", bool(result.get("bridge_version")), result)

    if expect_state:
        check("state is {:s} as expected".format(expect_state), state == expect_state, result)

    print("    state={!r} package={!r} bridge={!r} background={!r}".format(
        state, result.get("package"), result.get("bridge_version"),
        result.get("blender", {}).get("background")))
    return result


def check_list_commands(host, port):
    """The vocabulary, discoverable without having to guess wrong first."""
    print("\nlist_commands")
    answer = request(host, port, label="list_commands", command="list_commands")

    check("list_commands answers", answer.get("status") == "ok", answer)
    result = answer.get("result", {})
    described = result.get("commands", [])

    check("it describes at least get_status and itself", len(described) >= 2, result)
    check("the count agrees with the list", result.get("command_count") == len(described), result)
    check("it says the vocabulary is closed", result.get("closed_vocabulary") is True, result)

    names = [entry.get("name") for entry in described]
    check("the list is sorted, so two runs are comparable", names == sorted(names), names)
    check("get_status is described", "get_status" in names, names)

    for entry in described:
        check("{:s} carries a summary".format(entry.get("name", "?")),
              bool(entry.get("summary")), entry)
        check("{:s} says whether it needs MPFB".format(entry.get("name", "?")),
              isinstance(entry.get("requires_mpfb"), bool), entry)
        check("{:s} carries a parameter specification".format(entry.get("name", "?")),
              isinstance(entry.get("params"), list), entry)

    # The refusal a caller sees when it guessed must agree with the catalogue,
    # or the two ways of learning the vocabulary contradict each other.
    refusal = request(host, port, command="no_such_command")
    check("the refusal's command list agrees with list_commands",
          sorted(refusal.get("known_commands", [])) == sorted(names),
          (refusal.get("known_commands"), names))

    short = request(host, port, label="list_commands_short",
                    command="list_commands", params={"include_params": False})
    check("include_params=False omits the specifications",
          short.get("status") == "ok"
          and all("params" not in entry for entry in short["result"]["commands"]), short)


def check_parameter_contract(host, port):
    """Validation as a caller meets it: before the handler, naming the argument."""
    print("\nthe parameter contract")

    answer = request(host, port, label="bad_param_type",
                     command="list_commands", params={"include_params": "yes"})
    check("a parameter of the wrong type is refused",
          answer.get("error") == "invalid_params", answer)
    check("the refusal names the parameter", "include_params" in answer.get("message", ""), answer)

    answer = request(host, port, label="unknown_param",
                     command="list_commands", params={"includ_params": True})
    check("a misspelled parameter is refused rather than dropped",
          answer.get("error") == "invalid_params", answer)
    check("the refusal quotes the misspelling", "includ_params" in answer.get("message", ""),
          answer)

    # The asymmetry: `params` is a command's declared contract, the envelope is
    # the protocol's and is versioned, so an unknown key there is tolerated.
    answer = request(host, port, label="unknown_envelope_key",
                     command="get_status", request_id="abc123")
    check("an unknown envelope key is tolerated", answer.get("status") == "ok", answer)

    answer = request(host, port, command="get_status", params={"anything": 1})
    check("a command taking no parameters refuses one",
          answer.get("error") == "invalid_params", answer)

    # No command in the shipped table declares requires_mpfb yet, so the
    # mpfb_unavailable path cannot be reached from out here. It is covered by
    # ccc_dispatch_test, which supplies both non-ok states rather than waiting
    # for one. Said out loud so the gap is not mistaken for coverage.
    print("    note: no shipped command declares requires_mpfb yet, so mpfb_unavailable")
    print("          is exercised by the unit suite rather than from here")


def check_handshake(host, port):
    """The version check, from both sides of the range and from neither."""
    print("\nthe protocol handshake")

    status = request(host, port, command="get_status")["result"]
    spoken = status["protocol_version"]
    oldest = status["min_supported_protocol_version"]

    answer = request(host, port, label="protocol_future",
                     command="get_status", protocol_version=spoken + 1)
    check("a protocol version from the future is refused",
          answer.get("error") == "protocol_mismatch", answer)
    check("the mismatch says what would be accepted",
          answer.get("min_supported_protocol_version") == oldest, answer)

    answer = request(host, port, command="get_status", protocol_version=oldest - 1)
    check("a protocol version older than the minimum is refused",
          answer.get("error") == "protocol_mismatch", answer)

    answer = request(host, port, command="get_status", protocol_version=spoken)
    check("the current protocol version is served", answer.get("status") == "ok", answer)

    answer = request(host, port, command="get_status")
    check("a request carrying no protocol version is still served",
          answer.get("status") == "ok", answer)

    answer = request(host, port, command="get_status", protocol_version="1")
    check("a non-integer protocol version is malformed rather than a mismatch",
          answer.get("error") == "malformed_request", answer)


def check_closed_vocabulary(host, port):
    """FR 028's attack shapes, re-run against a dispatcher that grew a layer.

    Adding validation in front of the handler table is exactly the kind of
    change that could open a hole, and the check already existed.
    """
    print("\nthe vocabulary is still closed")

    hostile = "__import__('bpy').data.objects.new('CHECK_SKELETON_PWNED', None)"
    answer = request(host, port, command=hostile)
    check("a command name that is Python is refused",
          answer.get("error") == "unknown_command", answer)
    check("the refusal echoes the name it refused", answer.get("command") == hostile, answer)

    for smuggled in ("code", "script", "exec", "eval", "python"):
        answer = send_raw(host, port, [
            (json.dumps({smuggled: "1 + 1", "command": "get_status"}) + "\0").encode("utf-8")])
        check("an extra {!r} envelope key is ignored rather than honoured".format(smuggled),
              answer.get("status") == "ok", answer)

    answer = send_raw(host, port, [(json.dumps({"code": "1 + 1"}) + "\0").encode("utf-8")])
    check("a bare code request is refused", answer.get("status") == "error", answer)

    answer = request(host, port, command="exec", params={"code": "1 + 1"})
    check("a command called 'exec' is refused", answer.get("error") == "unknown_command", answer)

    answer = request(host, port, command="get_status")
    check("the server is still answering afterwards", answer.get("status") == "ok", answer)


def check_repeated_calls(host, port, count=25):
    """Cost per round trip, which is the number the pivot is argued on."""
    print("\nrepeated connections")
    started = time.time()
    for index in range(count):
        answer = request(host, port, command="get_status")
        if answer.get("status") != "ok":
            check("call {:d} of {:d} succeeded".format(index + 1, count), False, answer)
            return
    elapsed = time.time() - started
    check("{:d} sequential calls all succeeded".format(count), True)
    print("    {:d} calls in {:.2f} s, {:.0f} ms each".format(
        count, elapsed, 1000.0 * elapsed / count))


def _flatten(value, prefix=""):
    """One nested answer as a flat path -> value dict, for comparing two runs."""
    flat = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            flat.update(_flatten(inner, "{:s}.{:s}".format(prefix, key) if prefix else str(key)))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            flat.update(_flatten(inner, "{:s}[{:d}]".format(prefix, index)))
    else:
        flat[prefix] = value
    return flat


def compare_runs(path):
    """Compare this run's answers against a saved run's, field by field.

    This is requirement 7's claim and the one thing no unit test can make: the
    timer-driven path and the blocking one must be the same bridge. Anything
    that differs and is not in ``_EXPECTED_TO_DIFFER`` is a failure, and
    anything in that list that did *not* differ is one too - otherwise a
    comparison between two GUI runs would pass and prove nothing.
    """
    print("\ncomparing against {:s}".format(path))
    with open(path, "r", encoding="utf-8") as stream:
        saved = json.load(stream)

    check("the saved run recorded the same set of requests",
          sorted(saved) == sorted(_RECORDED), (sorted(saved), sorted(_RECORDED)))

    differing = []
    for label in sorted(set(saved) & set(_RECORDED)):
        before = _flatten(saved[label])
        after = _flatten(_RECORDED[label])

        check("{:s}: the same fields came back".format(label),
              sorted(before) == sorted(after),
              (sorted(set(before) ^ set(after))))

        for key in sorted(set(before) & set(after)):
            if before[key] == after[key]:
                continue
            path_key = "{:s}.{:s}".format(label, key)
            if any(key == expected or key.endswith(expected) or path_key.endswith(expected)
                   for expected in _EXPECTED_TO_DIFFER):
                differing.append(key)
                continue
            check("{:s}: {:s} is the same in both runs".format(label, key), False,
                  "{!r} then, {!r} now".format(before[key], after[key]))

    check("the two runs really were a GUI one and a headless one",
          bool(differing),
          "Nothing differed at all, including blender.background - so this compared two runs "
          "of the same kind and establishes nothing about the other drive mechanism.")
    if differing:
        print("    expected differences: {:s}".format(", ".join(sorted(set(differing)))))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--expect-state", choices=("ok", "not_initialized", "absent"), default=None,
        help="Assert the MPFB state this Blender should report.")
    parser.add_argument(
        "--save", metavar="PATH", default=None,
        help="Write this run's answers to PATH, for a later --compare.")
    parser.add_argument(
        "--compare", metavar="PATH", default=None,
        help="Compare this run's answers against a run saved with --save. Use it to check that "
             "a headless Blender answers exactly as a windowed one did.")
    arguments = parser.parse_args(argv)

    print("MPFB Bridge skeleton check against {:s}:{:d}".format(arguments.host, arguments.port))

    try:
        socket.create_connection((arguments.host, arguments.port), timeout=5.0).close()
    except OSError as error:
        print("\nCannot reach the bridge: {:s}".format(str(error)))
        print("Either start Blender, enable the MPFB Bridge add-on and start its server from "
              "the add-on preferences panel, or run")
        print("    blender --background --command mpfb_bridge")
        return 2

    check_get_status(arguments.host, arguments.port, arguments.expect_state)
    check_list_commands(arguments.host, arguments.port)
    check_parameter_contract(arguments.host, arguments.port)
    check_handshake(arguments.host, arguments.port)
    check_closed_vocabulary(arguments.host, arguments.port)
    check_repeated_calls(arguments.host, arguments.port)

    if arguments.compare:
        compare_runs(arguments.compare)

    if arguments.save:
        with open(arguments.save, "w", encoding="utf-8") as stream:
            json.dump(_RECORDED, stream, indent=2, sort_keys=True)
        print("\nSaved {:d} answers to {:s}".format(len(_RECORDED), arguments.save))

    print("\n{:d} passed, {:d} failed".format(len(_PASSES), len(_FAILURES)))
    if _FAILURES:
        for failure in _FAILURES:
            print("  failed: {:s}".format(failure))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
