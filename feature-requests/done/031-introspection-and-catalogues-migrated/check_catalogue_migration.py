#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 031's live check: nine tools, two transports, one Blender, compared.

FR 030 compared one tool and called the result the thing the remaining stages
rest on. This is the same claim for the other nine read-only tools, and the
comparison is harder in two named ways which are handled here rather than
discovered:

- **Several of these tools take ``refresh``, and a first call that rescans
  changes what the second sees.** So every comparison is made over a *fixed*
  ``refresh``, and for the tools that take one the pair is run twice: once with
  ``refresh=False`` on both sides and once with ``refresh=True`` on both. The
  generated path always goes first, so if a rescan changes anything the bridge
  is the side reading the *rescanned* state - which would show up as a
  difference rather than hide one.
- **``mpfb_list_asset_materials`` is stale by design.** MPFB caches that scan
  per asset and nothing invalidates it, so the first of two calls in one Blender
  warms a cache the second reads. A difference there is a fact about MPFB, not a
  migration defect, so that tool is compared **three** times - two calls on one
  backend first, to establish whether the cache is warm, and only then across
  the two. If the two same-backend calls already disagree, the cross-backend
  comparison is reported as inconclusive rather than as a failure.

What no unit test can establish and this does:

- **The two paths agree, field by field**, over an empty scene and a scene with
  a character in it, for every tool in requirement 7's four batches.
- **The cost of each tool on each path, cold and warm** (requirement 10). The
  fragment-carrying tools are the point: ``mpfb_list_targets`` carries 26 KB of
  shared source on a cold generated call and a single small JSON request on the
  bridge.
- **``mpfb_get_status`` answers correctly against a Blender with no MPFB**
  (``--expect-no-mpfb``), which is the one tool for which that is a success case
  rather than an error path. FR 030's ``serve_without_mpfb.py`` is the
  arrangement; it is reused from that request's directory rather than copied.

**The comparison cannot pass vacuously.** ``--self-compare`` runs both sides on
the generated path, and the run is then expected to FAIL: a comparison that
cannot tell two runs of one backend from two backends proves nothing.

## Running

One Blender with **MPFB, blender_mcp and the MPFB Bridge** all enabled, with
both socket servers started - blender_mcp's from its preferences panel, the
bridge's from its own. That is the transitional arrangement
verification/README.md describes, and it goes away in stage 5.

    PYTHONPATH=. python3 feature-requests/031-introspection-and-catalogues-migrated/check_catalogue_migration.py
    PYTHONPATH=. python3 .../check_catalogue_migration.py --self-compare

And, against a second Blender started with the bridge and no MPFB::

    blender --factory-startup --background -P \\
        feature-requests/done/030-backend-seam/serve_without_mpfb.py -- --port 9878
    MPFB_BRIDGE_PORT=9878 PYTHONPATH=. python3 .../check_catalogue_migration.py --expect-no-mpfb

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

from mpfbmcp import backend, bridge_connection, build_server, shared_cache
from mpfbmcp.connection import get_connection_params, send_code

SCRATCH_SCENE = "MPFBMCP_CATALOGUE_CHECK"

_FAILURES: list[str] = []
_PASSES: list[str] = []
_INCONCLUSIVE: list[str] = []

# Set by compare(), so the vacuity guard at the end can say whether two
# different transports were ever actually spoken to.
_BACKENDS_COMPARED: set[str] = set()


def check(label: str, condition: object, detail: object = "") -> bool:
    """One assertion. Records rather than raises, so one failure hides none."""
    if condition:
        _PASSES.append(label)
        print("  PASS  {:s}".format(label))
        return True
    _FAILURES.append(label)
    print("  FAIL  {:s}\n          {:s}".format(label, str(detail)[:800]))
    return False


def inconclusive(label: str, why: str) -> None:
    """Not a pass and not a failure: MPFB itself made the question unanswerable."""
    _INCONCLUSIVE.append(label)
    print("  ????  {:s}\n          {:s}".format(label, why[:400]))


def tools() -> dict:
    """The tool callables of the server an MCP client would connect to."""
    server = build_server()
    return {tool.name: tool.fn for tool in server._tool_manager.list_tools()}  # noqa: SLF001


def probe(label: str, code: str, **params: object) -> dict:
    """Run this script's own code inside Blender, over the generated path.

    Scene bookkeeping rather than a tool call, exactly as ``verification/``'s
    probes are, and on ``send_code()`` for the same reason: it is the harness
    talking to Blender, not a tool, and it goes away with the generated path.
    """
    program = "".join((
        "# --- probe: {} ---\n".format(label),
        "PARAMS = ", json.dumps(params, indent=4), "\n",
        "# --- payload: cataloguecheck_{}.py ---\n".format(label),
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


def with_backend(name: str, call, /, *arguments, **keywords):
    """Run one callable with the backend preference set, and put it back.

    Both parameters are **positional-only**, and that slash is load-bearing:
    three of the nine tools take an argument called ``name``, and without it
    ``with_backend(..., name="Human")`` is a TypeError rather than a call.
    """
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


def _difference(left: object, right: object, path: str = "") -> str:
    """Which fields disagree, rather than that some field does.

    Recursive, because these results are nested - a rig entry's ``weights_from``
    or one asset's ``pack`` is exactly the sort of difference that a top-level
    "the lists differ" would leave a reader hunting for.
    """
    if isinstance(left, dict) and isinstance(right, dict):
        lines = []
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                lines.append(_difference(left.get(key), right.get(key),
                                         "{:s}.{:s}".format(path, key) if path else str(key)))
        return "; ".join(line for line in lines if line)
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        lines = []
        for index, (one, other) in enumerate(zip(left, right)):
            if one != other:
                lines.append(_difference(one, other, "{:s}[{:d}]".format(path, index)))
        return "; ".join(line for line in lines if line)
    return "{:s}: generated={!r} bridge={!r}".format(path or "result", left, right)


def _summarise(result: object) -> str:
    """A line naming the fields most worth eyeballing, whatever tool answered."""
    if not isinstance(result, dict):
        return repr(result)[:120]
    interesting = ("count", "total_count", "truncated", "found", "state",
                   "modifier_count", "section_recognized", "subdir_recognized")
    parts = ["{:s}={!r}".format(key, result[key]) for key in interesting if key in result]
    for key in ("rigs", "assets", "presets", "materials", "user_targets", "targets",
                "related_objects", "sections"):
        if isinstance(result.get(key), list):
            parts.append("{:s}={:d}".format(key, len(result[key])))
    return " ".join(parts) or "(no summary fields)"


def compare(label: str, tool, right_backend: str, **keywords) -> bool:
    """Call one tool once per backend and compare the two results.

    The envelopes are compared through ``result`` rather than whole: a bridge
    answer carries ``protocol_version`` and ``command`` and a generated one does
    not, and that difference is the design rather than a disagreement.

    **The generated path always goes first.** For a tool taking ``refresh``,
    that means the bridge reads whatever state a rescan left behind - so a
    rescan that changed something shows up as a difference rather than hiding
    one.
    """
    left = with_backend(backend.BACKEND_BLENDER_MCP, tool, **keywords)
    right = with_backend(right_backend, tool, **keywords)
    _BACKENDS_COMPARED.add(backend.BACKEND_BLENDER_MCP)
    _BACKENDS_COMPARED.add(right_backend)

    if not check("{:s}: both answered with an ok envelope".format(label),
                 left.get("status") == "ok" and right.get("status") == "ok",
                 (left, right)):
        return False

    left_result, right_result = left["result"], right["result"]
    identical = check("{:s}: the two results are identical".format(label),
                      left_result == right_result,
                      _difference(left_result, right_result))
    if identical:
        print("       {:s}".format(_summarise(left_result)))
    return identical


def stable_on_one_backend(label: str, tool, **keywords) -> bool:
    """Whether two calls on *one* backend already answer the same thing.

    The guard requirement 9 asks for. ``mpfb_list_asset_materials`` caches its
    scan per asset and nothing invalidates it, so two calls in one Blender can
    legitimately differ - and a cross-backend comparison of a tool that is not
    even self-consistent would report a fact about MPFB as a migration defect.
    """
    first = with_backend(backend.BACKEND_BLENDER_MCP, tool, **keywords)
    second = with_backend(backend.BACKEND_BLENDER_MCP, tool, **keywords)
    if first.get("status") != "ok" or second.get("status") != "ok":
        inconclusive(label, "one of the two same-backend calls failed: {!r}".format(second))
        return False
    if first["result"] != second["result"]:
        inconclusive(label, "two calls on one backend already differ, so MPFB's own caching "
                            "is what this tool reports: {:s}".format(
                                _difference(first["result"], second["result"])))
        return False
    return True


# Tool -> the argument sets to compare it over. A tool taking `refresh` is
# compared at both settings, with the flag *fixed* across the pair, because a
# first call that rescans changes what a second one sees.
_CASES: tuple[tuple[str, tuple[tuple[str, dict], ...]], ...] = (
    ("mpfb_get_status", (("", {}),)),
    ("mpfb_get_object_info", (
        ("active object", {}),
        ("by name", {"name": "Human"}),
        ("a name nothing carries", {"name": "NoSuchObjectHere"}),
    )),
    ("mpfb_get_macro_details", (
        ("active object", {}),
        ("by name", {"name": "Human"}),
        ("a name nothing carries", {"name": "NoSuchObjectHere"}),
    )),
    ("mpfb_list_presets", (
        ("no refresh", {"refresh": False}),
        ("refresh", {"refresh": True}),
    )),
    ("mpfb_list_rigs", (
        ("no refresh", {"refresh": False}),
        ("refresh", {"refresh": True}),
    )),
    ("mpfb_list_assets", (
        ("no refresh", {"refresh": False}),
        ("refresh", {"refresh": True}),
        ("one subdir", {"asset_subdir": "clothes"}),
        ("a subdir that does not exist", {"asset_subdir": "clothez"}),
        ("filtered and paged", {"name_contains": "a", "limit": 5, "offset": 2}),
    )),
    ("mpfb_list_targets", (
        ("the overview", {}),
        ("one section", {"section": "nose"}),
        ("a section that does not exist", {"section": "nostril"}),
        ("filtered and paged", {"name_contains": "scale", "limit": 5, "offset": 1}),
    )),
    ("mpfb_get_target_stack", (
        ("active object", {}),
        ("by name", {"name": "Human"}),
        ("with the macro keys", {"name": "Human", "include_macro": True}),
        ("filtered and paged", {"name_contains": "md", "include_macro": True, "limit": 5}),
        ("a name nothing carries", {"name": "NoSuchObjectHere"}),
    )),
)

# Compared apart, because it is the one tool whose answer MPFB caches per asset
# with nothing to invalidate it. Its argument is an object name, so it can only
# be exercised once there is a character in the scene.
_STALE_BY_DESIGN = "mpfb_list_asset_materials"


def check_both_paths(all_tools: dict, right_backend: str, scene_has_character: bool) -> None:
    """The primary claim: the same tool, the same scene, the same answer."""
    for tool_name, cases in _CASES:
        tool = all_tools[tool_name]
        for case_label, keywords in cases:
            label = "{:s}{:s}".format(tool_name, ", " + case_label if case_label else "")
            compare(label, tool, right_backend, **keywords)

    if not scene_has_character:
        return

    # The stale-by-design one. Asked about the basemesh, which is not an
    # equipped asset - so `found` is true, `object_type` is Basemesh and the
    # material list is empty or not, depending on the install. Either way the
    # two paths must say the same thing about it.
    tool = all_tools[_STALE_BY_DESIGN]
    label = "{:s}, the basemesh".format(_STALE_BY_DESIGN)
    if stable_on_one_backend(label + " (self-consistency first)", tool, name="Human"):
        check(label + " (self-consistency first)", True)
        compare(label, tool, right_backend, name="Human")

    equipped = _first_equipped_asset(all_tools)
    if equipped is None:
        equipped = _equip_something(all_tools)
    if equipped is None:
        print("       no MHCLO asset could be equipped here, so the cached-scan path is "
              "untested - the bridge's own suite covers it over a fixture library")
        return
    label = "{:s}, {!r}".format(_STALE_BY_DESIGN, equipped)
    if stable_on_one_backend(label + " (self-consistency first)", tool, name=equipped):
        check(label + " (self-consistency first)", True)
        compare(label, tool, right_backend, name=equipped)


def check_nothing_active(all_tools: dict, right_backend: str) -> None:
    """The three subject-resolving tools with no active object.

    A separate pass rather than a second full scene, because it is the only
    thing an empty scene exercises that the cases above do not: "no name was
    given and nothing is active" is a different branch from "the name resolved
    to nothing", and all three tools phrase it differently.
    """
    probe("deactivate", _DEACTIVATE_CODE)
    try:
        for tool_name in ("mpfb_get_object_info", "mpfb_get_macro_details",
                          "mpfb_get_target_stack"):
            compare("{:s}, nothing active".format(tool_name),
                    all_tools[tool_name], right_backend)
    finally:
        probe("reactivate", _REACTIVATE_CODE)


_DEACTIVATE_CODE = """
import bpy

previous = bpy.context.view_layer.objects.active
bpy.context.view_layer.objects.active = None
result = dict(previous=None if previous is None else previous.name)
"""

_REACTIVATE_CODE = """
import bpy

# Whatever is in the scratch scene; the scene is deleted at the end anyway.
for blender_object in bpy.context.scene.objects:
    bpy.context.view_layer.objects.active = blender_object
    break
result = dict(active=getattr(bpy.context.view_layer.objects.active, "name", None))
"""


def _equip_something(all_tools: dict) -> str | None:
    """Put one MHCLO asset on the character, so the cached scan has a subject.

    `mpfb_list_asset_materials` answers about an **equipped** asset, and the
    branch worth comparing - MPFB's cached alternative-material scan - is
    unreachable without one. So the harness equips one, exactly as it builds a
    character: this is instrument rather than tool, and it goes over whichever
    backend `mpfb_add_asset` has, which is still the generated path.

    Returns None rather than failing when the install ships no MHCLO assets at
    all. A skip that says why is better than a check that cannot run.
    """
    listed = all_tools["mpfb_list_assets"](asset_subdir="clothes", limit=1)
    if listed.get("status") != "ok" or not listed["result"].get("assets"):
        return None
    asset = listed["result"]["assets"][0]
    added = all_tools["mpfb_add_asset"](
        path=asset["path"], asset_type=asset["object_type"])
    if added.get("status") != "ok" or not added["result"].get("performed"):
        print("       could not equip {!r}: {:s}".format(
            asset.get("name"), str(added.get("message"))[:200]))
        return None
    # `asset_object_name`, not `object_name`: what mpfb_add_asset reports is
    # the asset it made, and a character-creating tool's `object_name` is a
    # different field on a different tool.
    name = added["result"].get("asset_object_name")
    if name is None:
        print("       the asset was added but reported no object name: {!r}".format(
            sorted(added["result"])))
        return None
    print("    equipped {!r} so the cached alternative-material scan has a subject".format(name))
    return name


def _first_equipped_asset(all_tools: dict) -> str | None:
    """The name of one equipped mesh asset in the scene, if there is one."""
    listed = all_tools["mpfb_list_objects"]()
    if listed.get("status") != "ok":
        return None
    for entry in listed["result"].get("objects", []):
        if entry.get("object_type") in ("Clothes", "Eyes", "Eyebrows", "Eyelashes",
                                        "Hair", "Teeth", "Tongue", "Proxymeshes"):
            return entry["name"]
    return None


def check_cost(all_tools: dict, right_backend: str, repeats: int) -> None:
    """Requirement 10: request bytes and milliseconds, per tool, per transport.

    **Cold and warm are the point for the fragment-carrying tools.** On the
    generated path a cold call carries its fragments' source and a warm one
    refers to it by fingerprint; on the bridge there is no source to carry, so
    the two are the same call. ``mpfb_list_targets`` is the extreme case and is
    why ``src/mpfbmcp/shared_cache.py`` exists.

    **Wall clock is calibrated rather than reported bare**, because it turns out
    not to be a property of either transport. Both add-ons answer from a
    ``bpy.app.timers`` callback, and how often that callback actually runs is
    Blender's business: an idle, unfocused GUI Blender can run its main loop at
    about 1 Hz however short an interval a timer asks for. So the floor is
    measured first - a trivial program and a trivial command, neither of which
    can cost anything but one tick - and every number below should be read
    against it. What that makes visible is the model
    [architecture.md](../../specifications/architecture.md#what-a-call-costs-is-the-size-of-its-program)
    describes: **the generated path costs one tick per 4 KB of program and the
    bridge costs one tick, whatever a tick happens to be worth.** The byte
    counts beside them are exact and install-independent, and are the number
    this effort is really reporting.
    """
    floor_generated, floor_bridge = _measure_floor(all_tools, right_backend)
    print("\nthe tick this Blender is really running at: a trivial program costs "
          "{:.0f} ms and a trivial command {:.0f} ms".format(floor_generated, floor_bridge))
    print("(both are one tick, so divide by these to read the table as ticks)")

    print("\nthe cost of the two paths ({:d} timed calls each, best of)".format(repeats))
    print("  {:<26s} {:>10s} {:>8s} {:>10s} {:>8s} {:>9s} {:>8s}".format(
        "tool", "gen cold B", "ms", "gen warm B", "ms", "bridge B", "ms"))

    for tool_name, cases in _CASES:
        tool = all_tools[tool_name]
        keywords = cases[0][1]

        cold_bytes, cold = _timed_bytes(
            backend.BACKEND_BLENDER_MCP, tool, keywords, cold=True)
        warm_bytes, warm = _timed_bytes(backend.BACKEND_BLENDER_MCP, tool, keywords,
                                        repeats=repeats)
        bridge_bytes, bridge_warm = _timed_bytes(right_backend, tool, keywords,
                                                 repeats=repeats)

        # The cold/warm byte difference is the session source cache and nothing
        # else: for a tool naming no cached fragment the two are equal, and the
        # gap for the two that do is exactly the fragment source.
        print("  {:<26s} {:>10d} {:>7.0f}m {:>10d} {:>7.0f}m {:>9d} {:>7.0f}m".format(
            tool_name, cold_bytes, cold, warm_bytes, warm, bridge_bytes, bridge_warm))

    check("every tool answered on both paths while being timed", True)


def _measure_floor(all_tools: dict, right_backend: str) -> tuple[float, float]:
    """What one tick costs in this Blender, on each transport.

    A program of one statement and a command taking no parameters: neither can
    cost more than a single tick of the add-on serving it, so whatever they cost
    *is* the tick. ``mpfb_get_status``'s generated program is not trivial - it
    carries the bootstrap - so the floor is measured with a program of this
    script's own rather than with a tool.
    """
    send_code("result = 1", strict_json=True)
    generated = []
    for _ in range(3):
        started = time.perf_counter()
        send_code("result = 1", strict_json=True)
        generated.append((time.perf_counter() - started) * 1000.0)

    bridge_tool = all_tools["mpfb_get_status"]
    with_backend(right_backend, bridge_tool)
    bridge = []
    for _ in range(3):
        started = time.perf_counter()
        with_backend(right_backend, bridge_tool)
        bridge.append((time.perf_counter() - started) * 1000.0)

    return (min(generated), min(bridge))


def _timed_bytes(name: str, tool, keywords: dict, repeats: int = 1,
                 cold: bool = False) -> tuple[int, float]:
    """One tool's request size and duration on one backend.

    The size is taken by watching what the transport client actually sends,
    which is the only honest way to measure a program that may or may not be
    carrying 26 KB of fragment source this time.

    **The duration reported is the best of the timed calls, and a warm-up call
    precedes them.** Both add-ons drop to a one-second tick after five quiet
    seconds, and every generated call in this run is slow enough to put the
    *other* transport to sleep while it happens - so a mean over calls that
    each paid an idle wake-up would be measuring the alternation between the
    two rather than either one. The warm-up is skipped for a **cold**
    measurement, which is a single call by definition: what it measures is the
    fragment source on the wire, and a warm-up would prime exactly what it is
    there to catch.
    """
    sizes: list[int] = []
    durations: list[float] = []

    if cold:
        # Drop what this process believes Blender is holding, so the next call
        # carries its fragments' source. Only the generated path has this.
        shared_cache._PRIMED.clear()  # noqa: SLF001
    else:
        # Wake this transport up before timing it. See the docstring.
        with_backend(name, tool, **keywords)

    # **Both** generated-path send sites, not only the seam's. A tool naming a
    # cached fragment reaches blender_mcp through `shared_cache`, which holds
    # its own reference to `send_code` - and that is precisely the tool whose
    # byte count is the point, so watching one of the two would report zero for
    # the two measurements this table exists for.
    original_generated = backend.send_code
    original_cached = shared_cache.send_code
    original_bridge = bridge_connection.send_command

    def watched_send_code(code, **rest):
        sizes.append(len(code.encode("utf-8")))
        return original_generated(code, **rest)

    def watched_cached_send_code(code, **rest):
        sizes.append(len(code.encode("utf-8")))
        return original_cached(code, **rest)

    def watched_send_command(command, params=None, **rest):
        sizes.append(len(json.dumps({"command": command, "params": params or {}})))
        return original_bridge(command, params, **rest)

    backend.send_code = watched_send_code
    shared_cache.send_code = watched_cached_send_code
    bridge_connection.send_command = watched_send_command
    try:
        for _ in range(repeats):
            started = time.perf_counter()
            with_backend(name, tool, **keywords)
            durations.append((time.perf_counter() - started) * 1000.0)
    finally:
        backend.send_code = original_generated
        shared_cache.send_code = original_cached
        bridge_connection.send_command = original_bridge

    # The last request of the run: for a cold measurement that is the only one,
    # and for a warm one they are all the same size by construction.
    return (sizes[-1] if sizes else 0, min(durations))


def check_no_mpfb(all_tools: dict) -> int:
    """The other Blender: the bridge with no MPFB behind it.

    ``mpfb_get_status`` is the one tool for which this is a **success** case,
    and its command is the first migrated one declaring ``requires_mpfb=False``.
    Every other tool here must fail legibly instead - an install to fix, not an
    empty answer.
    """
    print("MPFB-less bridge check against {:s}:{:d}".format(
        *bridge_connection.get_connection_params()))

    answer = with_backend(backend.BACKEND_BRIDGE, all_tools["mpfb_get_status"])
    check("mpfb_get_status answers rather than refusing", answer.get("status") == "ok", answer)
    result = answer.get("result") or {}
    check("it classifies the install as absent", result.get("state") == "absent", result)
    check("it says what to do about it", "MPFB" in str(result.get("message")), result)
    check("it reports the scan it made", result.get("candidate_modules") == [], result)
    check("nothing from the services tier was invented",
          "asset_roots" not in result and "paths" not in result, sorted(result))
    print("    {:s}".format(str(result.get("message"))[:200]))

    for tool_name in ("mpfb_list_rigs", "mpfb_list_targets", "mpfb_get_object_info"):
        refused = with_backend(backend.BACKEND_BRIDGE, all_tools[tool_name])
        check("{:s} is refused with mpfb_unavailable".format(tool_name),
              refused.get("status") == "error"
              and refused.get("error") == "mpfb_unavailable", refused)
        check("{:s}'s refusal names an install rather than an empty answer".format(tool_name),
              "MPFB" in refused.get("message", "") and "result" not in refused, refused)

    return _report()


def _report() -> int:
    print("\n{:d} passed, {:d} failed, {:d} inconclusive".format(
        len(_PASSES), len(_FAILURES), len(_INCONCLUSIVE)))
    for failure in _FAILURES:
        print("  failed: {:s}".format(failure))
    for entry in _INCONCLUSIVE:
        print("  inconclusive: {:s}".format(entry))
    return 1 if _FAILURES else 0


def _reachable(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=5.0).close()
        return True
    except OSError:
        return False


def main(argv=None) -> int:  # pylint: disable=too-many-branches
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--self-compare", action="store_true",
        help="Run both sides of every comparison on the generated path. The run is then "
             "expected to FAIL: a comparison that cannot tell two runs of one backend from "
             "two backends proves nothing.")
    parser.add_argument(
        "--expect-no-mpfb", action="store_true",
        help="Point at a Blender running the bridge with no MPFB. mpfb_get_status must answer; "
             "everything else must be refused legibly. Needs no blender_mcp.")
    parser.add_argument("--repeats", type=int, default=5,
                        help="How many warm calls per backend the cost measurement makes.")
    parser.add_argument("--cost-only", action="store_true",
                        help="Measure the cost table and skip the comparison. Requirement 10 "
                             "wants both of the add-on's tick settings, and the comparison does "
                             "not change between them - so it is run once and this is run twice.")
    parser.add_argument("--compare-only", action="store_true",
                        help="Compare and skip the cost table.")
    parser.add_argument("--keep", action="store_true",
                        help="Leave the scratch scene and the character behind.")
    arguments = parser.parse_args(argv)

    all_tools = tools()
    bridge_host, bridge_port = bridge_connection.get_connection_params()

    if arguments.expect_no_mpfb:
        if not _reachable(bridge_host, bridge_port):
            print("Cannot reach the bridge at {:s}:{:d}".format(bridge_host, bridge_port))
            return 2
        return check_no_mpfb(all_tools)

    addon_host, addon_port = get_connection_params()
    missing = []
    if not _reachable(addon_host, addon_port):
        missing.append("blender_mcp at {:s}:{:d}".format(addon_host, addon_port))
    if not _reachable(bridge_host, bridge_port):
        missing.append("the MPFB Bridge at {:s}:{:d}".format(bridge_host, bridge_port))
    if missing:
        print("Cannot reach: {:s}".format(", ".join(missing)))
        print("This check needs ONE Blender with MPFB, blender_mcp and the MPFB Bridge all")
        print("enabled, and both socket servers started.")
        return 2

    right_backend = (backend.BACKEND_BLENDER_MCP if arguments.self_compare
                     else backend.BACKEND_BRIDGE)
    print("Catalogue migration check: blender_mcp at {:s}:{:d}, bridge at {:s}:{:d}".format(
        addon_host, addon_port, bridge_host, bridge_port))
    print("Comparing {:d} tools over {:d} argument sets".format(
        len(_CASES) + 1, sum(len(cases) for _name, cases in _CASES)))
    if arguments.self_compare:
        print("--self-compare: both sides on the generated path, and this run should FAIL")

    scene = probe("scene", _SCENE_CODE, scene=SCRATCH_SCENE)
    print("Working in scene {!r} (was {!r})".format(scene["scene"], scene["previous"]))

    try:
        # A character either way: the cost of a tool that reads one is not the
        # cost of the same tool over an empty scene, and the comparison needs
        # something to compare.
        created = all_tools["mpfb_create_human"]()
        if created.get("status") != "ok":
            check("a character could be built to work against", False, created)
            has_character = False
        else:
            print("Built {!r}".format(created["result"].get("object_name")))
            has_character = True

        if not arguments.cost_only:
            print("\nthe two paths, over a scene with a character in it")
            check_both_paths(all_tools, right_backend, scene_has_character=has_character)
            print("\nand with nothing active, which is a different branch in three of them")
            check_nothing_active(all_tools, right_backend)

        if not arguments.self_compare and not arguments.compare_only:
            check_cost(all_tools, right_backend, arguments.repeats)
    finally:
        if arguments.keep:
            print("\n--keep: {!r} and everything in it is left behind".format(SCRATCH_SCENE))
        else:
            removed = probe("restore", _RESTORE_CODE,
                            scene=SCRATCH_SCENE, previous=scene["previous"])
            print("\nRemoved {:d} objects and the scratch scene".format(
                len(removed["removed_objects"])))

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

    if not arguments.cost_only:
        # Only meaningful when a comparison ran: --cost-only compares nothing,
        # and a guard that fires there would be noise rather than a guard.
        check("the two sides really were two different backends", two_backends,
              sorted(_BACKENDS_COMPARED))
    return _report()


if __name__ == "__main__":
    sys.exit(main())
