# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 033's live check: twenty-five tools still work with the generated path gone.

**The unit suite cannot establish this effort's central claim.** It can say that
each tool builds the request it meant to build; it cannot say that a tool whose
Blender-side half used to be a Python program this package assembled still
answers the same thing now that the program, its assembler and its transport
have been deleted. That is a question about a running Blender, and this is the
script that asks it.

**The configuration is the proof.** This must be pointed at a Blender with MPFB
and the MPFB Bridge enabled and **blender_mcp not installed, or disabled in that
process** — which is, as of FR 033, the first time in the project's life that
arrangement has been exercised. A run against a Blender that happens to have
blender_mcp sitting there too would establish nothing about whether anything
still depended on it. The cheapest way to get one::

    blender --background --python-expr \\
      "import addon_utils; addon_utils.disable('bl_ext.user_default.mcp', default_set=False)" \\
      --command mpfb_bridge --port 9900

    MPFB_BRIDGE_PORT=9900 PYTHONPATH=. python3 \\
      feature-requests/033-retire-the-generated-code-path/check_retirement.py

Four things are checked, and the third is the one that would catch a regression
nobody was looking for:

1. **The deleted path is actually gone from the installed package**, asserted by
   import rather than by reading a file listing — a stale `.pyc` or an editable
   install pointing at an old tree would otherwise let everything below pass for
   the wrong reason.
2. **Every tool answers**, by running the whole smoke
   ([verification/smoke.py](../../verification/smoke.py)) in this process, with
   the same skipped set the pre-deletion run reported for the same install.
3. **Each tool's answer is compared field by field against the pre-deletion
   run** recorded in ``before/``, which this effort captured with both
   transports before anything was deleted. A difference is not automatically a
   failure — an asset library changes, a name is uniquified differently in a
   fresh Blender — so the known-benign shapes are named in
   :data:`EXPECTED_DIFFERENCES` and everything else is reported.
4. **The narrowed harness still claims what it says it claims**: the scene
   compare ran, nothing that predated the run disappeared, and the asset the run
   equipped is gone again. Requirement 5 narrowed this instrument on purpose,
   and a narrowing that also stopped working would look identical in a passing
   run.

Exit code 0 if every check passed, 1 if any failed, 2 if the run could not be
made at all.
"""

from __future__ import annotations

__all__ = ("main",)

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BASELINE = os.path.join(_HERE, "before", "bridge", "mpfb_mcp_smoke_run.json")

# What FR 033 deleted, asserted by import. Named rather than globbed so that a
# module reappearing under one of these names fails here loudly.
RETIRED_MODULES = (
    "mpfbmcp.codegen",
    "mpfbmcp.shared_cache",
    "mpfbmcp.connection",
)

# Names the seam carried while there were two transports. A tool that still
# reached for one of these would fail at call time rather than here, but here is
# where it says *why*.
RETIRED_SEAM_NAMES = (
    "MIGRATED_COMMANDS",
    "command_for",
    "preferred_backend",
    "as_common_envelope",
    "BACKENDS",
    "BACKEND_BLENDER_MCP",
    "ERROR_COMMAND_FAILED",
    "send_code",
)

# The two run-level items the pre-deletion harness had and this one does not.
# Named rather than filtered out silently, because each is a deliberate
# narrowing and a reader comparing the two runs will notice them missing:
#
# - the traceback item resolved a line number against a recorded *program*, and
#   there are no programs;
# - "the run put back everything it made" was a twelve-collection `bpy.data`
#   compare against a scratch scene the harness created and emptied. The bridge
#   executes nothing on the harness's behalf, so the scratch scene and the
#   cleanup went, and what replaced it is `SCENE_ITEM` below - which asserts
#   less and says so. verification/README.md carries the full accounting.
RETIRED_ITEMS = (
    "a traceback line number from a real failure resolves to the recorded program",
    "the run put back everything it made",
)

# The run-level item that replaced the twelve-collection datablock compare.
SCENE_ITEM = "the run removed nothing it did not create, and names what it left behind"

# Differences between the two runs that are the install talking rather than the
# deletion. Each is a key of an item's reported ``observed`` dict whose value is
# legitimately run-dependent; the *presence* of the key is still compared, so a
# field that disappeared is a finding either way.
EXPECTED_DIFFERENCES = {
    # MPFB names every character `Human` and Blender uniquifies the second one,
    # so a run against a Blender that already holds one gets `Human.001`. The
    # pre-deletion run additionally renamed its character, which the harness can
    # no longer do.
    "name", "object_name", "basemesh_name", "asset_object_name", "rig_object_name",
    # A count off a library that is whatever is installed today.
    "count", "total_count",
}


def _print(line: str = "") -> None:
    print(line, flush=True)


def _check(results: list, item: str, passed: bool, observed: object = None) -> None:
    results.append((item, bool(passed), observed))
    _print("[{:s}] {:s}{:s}".format(
        "x" if passed else " ", item,
        "" if observed is None else " -- {:s}".format(str(observed)[:400])))


def _the_deleted_path_is_gone(results: list) -> None:
    """Requirement 2, asserted by import rather than by looking at the tree."""
    import importlib  # pylint: disable=import-outside-toplevel

    for name in RETIRED_MODULES:
        try:
            importlib.import_module(name)
        except ImportError:
            _check(results, "{:s} cannot be imported".format(name), True)
        else:
            _check(results, "{:s} cannot be imported".format(name), False,
                   "it imported, so this Blender is being driven by code FR 033 deleted")

    from mpfbmcp import backend  # pylint: disable=import-outside-toplevel

    still_there = [name for name in RETIRED_SEAM_NAMES if hasattr(backend, name)]
    _check(results, "the seam carries no name from the two-transport era",
           not still_there, ", ".join(still_there) or None)


def _baseline() -> dict:
    """The pre-deletion run this effort recorded, by item name."""
    with open(_BASELINE, encoding="utf-8") as stream:
        recorded = json.load(stream)
    return {entry["item"]: entry for entry in recorded["counts"]["results"]}


def _differences(before: object, after: object, path: str = "") -> list:
    """Every leaf at which two reported values differ, as dotted paths."""
    if isinstance(before, dict) and isinstance(after, dict):
        found = []
        for key in sorted(set(before) | set(after)):
            here = "{:s}.{:s}".format(path, key) if path else key
            if key not in before:
                found.append("{:s} (new)".format(here))
            elif key not in after:
                found.append("{:s} (gone)".format(here))
            elif key not in EXPECTED_DIFFERENCES:
                found += _differences(before[key], after[key], here)
        return found
    if before != after:
        return ["{:s}: {!r} -> {!r}".format(path or "value", before, after)]
    return []


def _compare_with_the_pre_deletion_run(results: list, counts: dict) -> None:
    """Requirement 3: field by field against what the same tools answered before."""
    try:
        recorded = _baseline()
    except OSError as error:
        _check(results, "the pre-deletion run is on disk to compare against", False, error)
        return
    _check(results, "the pre-deletion run is on disk to compare against", True,
           "{:d} items".format(len(recorded)))

    current = {entry["item"]: entry for entry in counts["results"]}

    missing = sorted(set(recorded) - set(current) - set(RETIRED_ITEMS))
    _check(results, "every item the pre-deletion run had still runs", not missing,
           ", ".join(missing) or None)

    outcome_changed = []
    field_changed = []
    for item, before in sorted(recorded.items()):
        if item in RETIRED_ITEMS or item not in current:
            continue
        after = current[item]
        if before["outcome"] != after["outcome"]:
            outcome_changed.append("{:s}: {:s} -> {:s}".format(
                item, before["outcome"], after["outcome"]))
            continue
        if before["outcome"] != "pass":
            continue
        differences = _differences(before.get("observed"), after.get("observed"))
        if differences:
            field_changed.append("{:s}: {:s}".format(item, "; ".join(differences)))

    _check(results, "no tool's outcome changed", not outcome_changed,
           " | ".join(outcome_changed) or None)
    # Field differences are reported rather than asserted against zero: the two
    # runs are against different Blenders. An *unexplained* one is what matters,
    # so they are printed in full and the check is on the shapes named above.
    _check(results, "no tool's reported fields changed outside the expected shapes",
           not field_changed, " | ".join(field_changed) or None)


def _the_narrowed_harness_still_claims_what_it_claims(results: list, counts: dict) -> None:
    """Requirement 4: what survived the narrowing has to actually work."""
    by_item = {entry["item"]: entry for entry in counts["results"]}
    entry = by_item.get(SCENE_ITEM)
    if entry is None:
        _check(results, "the scene compare ran", False,
               "no item named {!r} in the run".format(SCENE_ITEM))
        return
    _check(results, "the scene compare ran", True)
    _check(results, "the scene compare passed", entry["outcome"] == "pass", entry["observed"])

    observed = entry["observed"]
    if not isinstance(observed, dict):
        _check(results, "the scene compare reports what it compared", False, observed)
        return
    _check(results, "nothing that predated the run disappeared",
           observed.get("nothing_disappeared") is True, observed.get("removed"))
    # The one thing the run still puts back, and the only positive claim the
    # narrowed compare can make: mpfb_remove_asset really removed the object.
    left = observed.get("left_behind") or []
    equipped = by_item.get("mpfb_add_asset", {}).get("observed")
    asset_name = equipped.get("asset_object_name") if isinstance(equipped, dict) else None
    if asset_name is None:
        _check(results, "the equipped asset is gone from the scene again", True,
               "no asset was equipped on this install, so there is none to have removed")
    else:
        _check(results, "the equipped asset is gone from the scene again",
               asset_name not in left, asset_name)
    _check(results, "the run names what it left behind", bool(left),
           "{:d} object(s): {:s}".format(len(left), ", ".join(left)))


def main() -> int:
    _print("=== FR 033: twenty-five tools with the generated path deleted ===")
    _print("    . bridge at {:s}:{:s}".format(
        os.environ.get("MPFB_BRIDGE_HOST", "127.0.0.1"),
        os.environ.get("MPFB_BRIDGE_PORT", "9877")))

    results: list = []
    _the_deleted_path_is_gone(results)

    from verification import smoke  # pylint: disable=import-outside-toplevel

    _print("\n--- the smoke run, in this process ---")
    counts = smoke.run()
    if counts.get("exit_code") == 2:
        _print("\n!!! the smoke run could not be made at all; nothing below means anything.")
        return 2

    _print("\n--- what the run establishes ---")
    _check(results, "no tool failed", not counts["failed"],
           "{:d} passed, {:d} failed, {:d} skipped".format(
               counts["passed"], counts["failed"], counts["skipped"]))
    _compare_with_the_pre_deletion_run(results, counts)
    _the_narrowed_harness_still_claims_what_it_claims(results, counts)

    failed = [item for item, passed, _observed in results if not passed]
    _print("\n--- {:d} checks, {:d} failed".format(len(results), len(failed)))
    for item in failed:
        _print("    FAILED: {:s}".format(item))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
