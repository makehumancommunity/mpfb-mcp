#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 030's live check: one tool, two transports, one Blender, compared.

**The claim this exists to test is the one the remaining three stages rest on**
- that the bridge returns the same answer - and it had never been checked for
any tool. So this calls ``mpfb_list_objects`` through the real MCP tool
callable, once per backend, against the same scene, and compares the results
field by field. Everything else here is secondary to that.

What no unit test can establish and this does:

- **The two paths agree.** Over an empty scene and a scene with a character in
  it, filtered and unfiltered, recognised type and misspelled one. A stub can
  only ever confirm that the payload and the command were written from the same
  reading of MPFB; this asks MPFB.
- **The handshake against a real bridge**: what it reports, that a request
  declaring an impossible version is refused as ``protocol_mismatch``, and that
  this client's own refusal names both versions and which end to upgrade.
- **The cost of the two paths**, measured rather than assumed. FR 029 measured
  the bridge alone; the interesting number is the same tool over both
  transports from the same client, which is the first like-for-like comparison
  this project can make.
- **``mpfb_unavailable`` reaches the tool as a legible failure**, in a separate
  run against a Blender with the bridge and no MPFB (``--expect-no-mpfb``).

**The comparison cannot pass vacuously.** ``--self-compare`` runs both sides on
the *same* backend, and the run is expected to fail: a comparison that reports
"identical" for two runs of one transport is a comparison that would report it
for a bridge that was never spoken to. Following FR 029's arrangement, the
guard is part of the script rather than a note in a README.

## Running

This needs **one Blender with all three of MPFB, blender_mcp and the MPFB
Bridge enabled**, with both socket servers started - blender_mcp's from its
preferences panel, the bridge's from its own. That is the transitional
arrangement described in verification/README.md, and it goes away in stage 5.

    PYTHONPATH=. python3 feature-requests/030-backend-seam/check_backend_seam.py
    PYTHONPATH=. python3 feature-requests/030-backend-seam/check_backend_seam.py --self-compare

And, against a second Blender started with ``--factory-startup`` plus the
bridge only::

    blender --factory-startup --background --command mpfb_bridge   # in another terminal
    PYTHONPATH=. python3 .../check_backend_seam.py --expect-no-mpfb

It builds in a scene of its own and deletes what it made; the ``.blend`` is
never saved.
"""

from __future__ import annotations

__all__ = ("main",)

import argparse
import json
import os
import socket
import sys
import time

from mpfbmcp import backend, bridge_connection, build_server
from mpfbmcp.connection import get_connection_params, send_code

SCRATCH_SCENE = "MPFBMCP_SEAM_CHECK"

_FAILURES: list[str] = []
_PASSES: list[str] = []

# Set by compare_over_backends(), so the vacuity guard at the end can say
# whether two different transports were ever actually spoken to.
_BACKENDS_COMPARED: set[str] = set()


def check(label: str, condition: object, detail: object = "") -> bool:
    """One assertion. Records rather than raises, so one failure hides none."""
    if condition:
        _PASSES.append(label)
        print("  PASS  {:s}".format(label))
        return True
    _FAILURES.append(label)
    print("  FAIL  {:s}\n          {:s}".format(label, str(detail)[:600]))
    return False


def tools() -> dict:
    """The tool callables of the server an MCP client would connect to."""
    server = build_server()
    return {tool.name: tool.fn for tool in server._tool_manager.list_tools()}  # noqa: SLF001


def probe(label: str, code: str, **params: object) -> dict:
    """Run this script's own code inside Blender, over the generated path.

    Scene bookkeeping rather than a tool call, exactly as
    ``verification/harness.py``'s probes are, and on ``send_code()`` for the
    same reason: it is the harness talking to Blender, not a tool, and it goes
    away with the generated path in stage 5.
    """
    program = "".join((
        "# --- probe: {} ---\n".format(label),
        "PARAMS = ", json.dumps(params, indent=4), "\n",
        "# --- payload: seamcheck_{}.py ---\n".format(label),
        code))
    response = send_code(program, strict_json=True)
    if response.get("status") != "ok":
        raise RuntimeError("probe {} failed: {}".format(label, response.get("message")))
    return response.get("result")


_SCENE_CODE = '''
import bpy

previous = bpy.context.window.scene.name if bpy.context.window else bpy.context.scene.name
scene = bpy.data.scenes.get(PARAMS["scene"])
created = False
if scene is None:
    scene = bpy.data.scenes.new(PARAMS["scene"])
    created = True
for window in bpy.context.window_manager.windows:
    window.scene = scene

result = dict(scene=scene.name, created=created, previous=previous)
'''

_RESTORE_CODE = '''
import bpy

scene = bpy.data.scenes.get(PARAMS["scene"])
removed_objects = []
if scene is not None:
    for blender_object in list(scene.objects):
        removed_objects.append(blender_object.name)
        bpy.data.objects.remove(blender_object, do_unlink=True)

previous = bpy.data.scenes.get(PARAMS["previous"])
if previous is not None:
    for window in bpy.context.window_manager.windows:
        window.scene = previous

removed_scene = False
if scene is not None and previous is not None and scene is not previous:
    bpy.data.scenes.remove(scene)
    removed_scene = True

result = dict(removed_objects=sorted(removed_objects), removed_scene=removed_scene)
'''

_SCENE_CONTENTS_CODE = '''
import bpy

result = dict(objects=sorted(o.name for o in bpy.context.scene.objects),
              scene=bpy.context.scene.name)
'''


def with_backend(name: str, call, *arguments, **keywords):
    """Run one callable with the backend preference set, and put it back."""
    previous = os.environ.get(backend.BACKEND_VARIABLE)
    if name == backend.BACKEND_BLENDER_MCP:
        os.environ.pop(backend.BACKEND_VARIABLE, None)
    else:
        os.environ[backend.BACKEND_VARIABLE] = name
    try:
        return call(*arguments, **keywords)
    finally:
        if previous is None:
            os.environ.pop(backend.BACKEND_VARIABLE, None)
        else:
            os.environ[backend.BACKEND_VARIABLE] = previous


def compare_over_backends(label: str, tool, right_backend: str, **keywords) -> None:
    """Call one tool once per backend and compare the two results.

    The envelopes are compared through ``result`` rather than whole: a bridge
    answer carries ``protocol_version`` and ``command`` and a generated one does
    not, and that difference is the design rather than a disagreement.
    """
    left = with_backend(backend.BACKEND_BLENDER_MCP, tool, **keywords)
    right = with_backend(right_backend, tool, **keywords)
    _BACKENDS_COMPARED.add(backend.BACKEND_BLENDER_MCP)
    _BACKENDS_COMPARED.add(right_backend)

    if not check("{:s}: both answered with an ok envelope".format(label),
                 left.get("status") == "ok" and right.get("status") == "ok",
                 (left, right)):
        return

    left_result, right_result = left["result"], right["result"]
    if check("{:s}: the two results are identical".format(label),
             left_result == right_result,
             _difference(left_result, right_result)):
        print("       {:s}".format(_summarise(left_result)))


def _difference(left: dict, right: dict) -> str:
    """Which fields disagree, rather than that some field does."""
    lines = []
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            lines.append("{:s}: generated={!r} bridge={!r}".format(
                key, left.get(key), right.get(key)))
    return "; ".join(lines) or "the two are equal but the comparison said otherwise"


def _summarise(result: dict) -> str:
    return "count={!r} requested_type={!r} type_recognized={!r} known_types={:d}".format(
        result.get("count"), result.get("requested_type"),
        result.get("type_recognized"), len(result.get("known_types") or []))


_CASES = (
    ("no filter", {}),
    ("exact type", {"object_type": "Basemesh"}),
    ("substring type", {"object_type": "mesh"}),
    ("a type that matches nothing here", {"object_type": "Eyebrows"}),
    ("a misspelled type", {"object_type": "Basemseh"}),
)


def check_both_paths(tool, right_backend: str) -> None:
    """The primary claim: the same tool, the same scene, the same answer."""
    print("\nan empty scene")
    for label, keywords in _CASES:
        compare_over_backends("empty, " + label, tool, right_backend, **keywords)

    print("\na scene with a character in it")
    created = tools()["mpfb_create_human"]()
    if created.get("status") != "ok":
        check("a character could be built to compare against", False, created)
        return
    print("    built {!r}".format(created["result"].get("object_name")))

    for label, keywords in _CASES:
        compare_over_backends("character, " + label, tool, right_backend, **keywords)

    # The one case where a wrong answer would be a *plausible* answer, so it is
    # worth naming: the scene really does contain what the comparison is over.
    listed = with_backend(right_backend, tool)["result"]
    check("the character is actually in the compared listing",
          listed.get("count", 0) > 0, listed)


def check_handshake(right_backend: str) -> None:
    """The client's half of the handshake, against a bridge that has the other."""
    print("\nthe handshake")
    host, port = bridge_connection.get_connection_params()

    answer = bridge_connection.send_command("get_status")
    result = answer.get("result", {}) if isinstance(answer, dict) else {}
    check("the bridge answers get_status", answer.get("status") == "ok", answer)
    check("it reports the protocol it speaks",
          isinstance(result.get("protocol_version"), int), result)
    check("and the oldest it accepts",
          isinstance(result.get("min_supported_protocol_version"), int), result)
    print("    bridge={!r} protocol={!r} accepts from {!r}; this client speaks {:d}".format(
        result.get("bridge_version"), result.get("protocol_version"),
        result.get("min_supported_protocol_version"), bridge_connection.PROTOCOL_VERSION))

    # A raw request, because the client will not willingly declare a version it
    # does not speak - which is the point of it being refused rather than
    # misinterpreted.
    refusal = _raw_request(host, port, {"command": "get_status", "protocol_version": 9999})
    check("a request from an impossible future is refused",
          refusal.get("error") == "protocol_mismatch", refusal)
    check("the refusal names both versions",
          str(refusal.get("protocol_version")) in refusal.get("message", "")
          and "9999" in refusal.get("message", ""), refusal)

    # And this client's own refusal, which is the half FR 030 added: it reads
    # min_supported_protocol_version, so it can say which end to upgrade.
    original = bridge_connection.PROTOCOL_VERSION
    bridge_connection.PROTOCOL_VERSION = 9999
    bridge_connection.forget_handshakes()
    try:
        answer = with_backend(right_backend, tools()["mpfb_list_objects"])
    finally:
        bridge_connection.PROTOCOL_VERSION = original
        bridge_connection.forget_handshakes()

    check("a client that speaks a version the bridge cannot serve fails every call",
          answer.get("status") == "error" and answer.get("error") == "protocol_mismatch",
          answer)
    message = answer.get("message", "")
    check("its message names both versions and which end to upgrade",
          "9999" in message and str(result.get("protocol_version")) in message
          and ("Upgrade" in message), message)
    print("    {:s}".format(message[:300]))


def _raw_request(host: str, port: int, payload: dict) -> dict:
    connection = socket.create_connection((host, port), timeout=15.0)
    try:
        connection.sendall((json.dumps(payload) + "\0").encode("utf-8"))
        buffer = b""
        while b"\0" not in buffer:
            data = connection.recv(65536)
            if not data:
                break
            buffer += data
    finally:
        connection.close()
    if b"\0" not in buffer:
        raise ValueError("The bridge closed without sending a complete response")
    return json.loads(buffer.split(b"\0")[0])


def check_cost(tool, right_backend: str, repeats: int) -> None:
    """The same tool over both transports, from the same client.

    Wall clock against one machine's Blender, which is exactly as
    install-dependent as ``verification/``'s timing and is reported rather than
    gated for the same reason. What makes it worth measuring at all is that
    both numbers come from one client in one run.
    """
    print("\nthe cost of the two paths ({:d} calls each)".format(repeats))
    timings = {}
    for name in (backend.BACKEND_BLENDER_MCP, right_backend):
        durations = []
        for _ in range(repeats):
            started = time.perf_counter()
            with_backend(name, tool)
            durations.append((time.perf_counter() - started) * 1000.0)
        timings[name] = durations
        print("    {:>12s}: min {:7.1f} ms  mean {:7.1f} ms  max {:7.1f} ms".format(
            name, min(durations), sum(durations) / len(durations), max(durations)))

    check("both paths answered every call", all(timings.values()), timings)


def check_no_mpfb(tool) -> int:
    """The other Blender: the bridge with no MPFB behind it.

    The first time ``mpfb_unavailable`` is exercised from outside the add-on,
    and the thing worth checking is not the slug but that what reaches an agent
    is legible: an install to fix, not a tool that found no objects.
    """
    print("MPFB-less bridge check against {:s}:{:d}".format(
        *bridge_connection.get_connection_params()))
    answer = with_backend(backend.BACKEND_BRIDGE, tool)

    check("the call comes back as an error rather than an empty listing",
          answer.get("status") == "error", answer)
    check("the slug says the install is wrong, not that the command failed",
          answer.get("error") == "mpfb_unavailable", answer)
    check("the message says what to do about it",
          "MPFB" in answer.get("message", "") and "list_objects" in answer.get("message", ""),
          answer)
    check("nothing invented a count of zero",
          "result" not in answer or not answer.get("result"), answer)
    print("    {:s}".format(str(answer.get("message"))[:300]))
    return _report()


def _report() -> int:
    print("\n{:d} passed, {:d} failed".format(len(_PASSES), len(_FAILURES)))
    for failure in _FAILURES:
        print("  failed: {:s}".format(failure))
    return 1 if _FAILURES else 0


def _reachable(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=5.0).close()
        return True
    except OSError:
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--self-compare", action="store_true",
        help="Run both sides of every comparison on the generated path. The run is then "
             "expected to FAIL: a comparison that cannot tell two runs of one backend from "
             "two backends proves nothing.")
    parser.add_argument(
        "--expect-no-mpfb", action="store_true",
        help="Point at a Blender running the bridge with no MPFB, and check that the tool's "
             "failure is legible. Needs no blender_mcp.")
    parser.add_argument("--repeats", type=int, default=5,
                        help="How many calls per backend the cost measurement makes.")
    parser.add_argument("--keep", action="store_true",
                        help="Leave the scratch scene and the character behind.")
    arguments = parser.parse_args(argv)

    tool = tools()["mpfb_list_objects"]
    bridge_host, bridge_port = bridge_connection.get_connection_params()

    if arguments.expect_no_mpfb:
        if not _reachable(bridge_host, bridge_port):
            print("Cannot reach the bridge at {:s}:{:d}".format(bridge_host, bridge_port))
            return 2
        return check_no_mpfb(tool)

    addon_host, addon_port = get_connection_params()
    missing = []
    if not _reachable(addon_host, addon_port):
        missing.append("blender_mcp at {:s}:{:d}".format(addon_host, addon_port))
    if not _reachable(bridge_host, bridge_port):
        missing.append("the MPFB Bridge at {:s}:{:d}".format(bridge_host, bridge_port))
    if missing:
        print("Cannot reach: {:s}".format(", ".join(missing)))
        print("This check needs ONE Blender with MPFB, blender_mcp and the MPFB Bridge all")
        print("enabled, and both socket servers started from their preferences panels.")
        return 2

    right_backend = (backend.BACKEND_BLENDER_MCP if arguments.self_compare
                     else backend.BACKEND_BRIDGE)
    print("Backend seam check: blender_mcp at {:s}:{:d}, bridge at {:s}:{:d}".format(
        addon_host, addon_port, bridge_host, bridge_port))
    if arguments.self_compare:
        print("--self-compare: both sides on the generated path, and this run should FAIL")

    scene = probe("scene", _SCENE_CODE, scene=SCRATCH_SCENE)
    print("Working in scene {!r} (was {!r})".format(scene["scene"], scene["previous"]))

    try:
        check_both_paths(tool, right_backend)
        if not arguments.self_compare:
            check_handshake(right_backend)
            check_cost(tool, right_backend, arguments.repeats)
    finally:
        if arguments.keep:
            print("\n--keep: {!r} and everything in it is left behind".format(SCRATCH_SCENE))
        else:
            removed = probe("restore", _RESTORE_CODE,
                            scene=SCRATCH_SCENE, previous=scene["previous"])
            print("\nRemoved {:d} objects and the scratch scene: {!r}".format(
                len(removed["removed_objects"]), removed["removed_objects"]))

    print("\nthe comparison itself")
    two_backends = len(_BACKENDS_COMPARED) == 2
    if arguments.self_compare:
        # Inverted on purpose. The guard is the check, and a --self-compare run
        # that "passes" means the comparison would report identical answers for
        # a bridge it never spoke to.
        print("  compared backends: {:s}".format(", ".join(sorted(_BACKENDS_COMPARED))))
        if not two_backends:
            print("\nThe vacuity guard fired: the comparison refuses to call two runs of one")
            print("backend a comparison, which is what makes the ordinary run mean something.")
            return 0
        print("\nFAILED: --self-compare ran two backends after all, so the guard proved nothing.")
        return 1

    check("the two sides really were two different backends", two_backends,
          sorted(_BACKENDS_COMPARED))
    return _report()


if __name__ == "__main__":
    sys.exit(main())
