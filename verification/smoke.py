# SPDX-License-Identifier: GPL-3.0-or-later

"""
Does every tool still work against a real MPFB at all?

That is the whole question, and its smallness is the feature: a verification
that takes minutes is one that gets skipped, which is the failure FR 013 was
written to fix and which its own shape - eight exhaustive checklists, kept and
re-run forever - then reproduced at a different scale. One item per tool, one
call each, the tool's own defaults, three shallow assertions.

**What an item asserts is exactly three things**
([FR 023](../feature-requests/done/023-verification-smoke-test/README.md)):

1. the envelope is not an error;
2. the response carries the keys the tool's own contract names as always
   present. Which keys those are is the ``keys`` tuple on the item - and because
   a list of key names kept here is a copy of a contract kept elsewhere,
   ``_keys_the_tool_names()`` holds it to the description the MCP client
   actually downloads. A key the contract stopped naming cannot go on being
   checked for here;
3. for a mutating tool, ``performed`` is true and agrees with that tool's verb
   (``harness.MUTATING_VERBS``) - the one check the unit suite genuinely cannot
   make, because there the flag and the verb are read out of the same stub run.

It asserts nothing about *values*. Whether a garment equipped through the tool
is indistinguishable from one equipped through MPFB's panel is FR 010's claim,
established once by FR 010 and not re-established here. **An exhaustive live
check belongs to the feature request that needs it**, lives in that request's
own subdir and goes to ``done/`` with it; what an effort adds here is at most
the one smoke item for a tool it introduced.

**Coverage is derived from the registry, not from this table.** ``ITEMS`` is
matched against the built server before anything runs: a registered tool with no
item, or an item naming a tool the server does not register, stops the run with
exit code 2, so the table can neither fall behind nor keep entries for tools
that are gone. ``tests/test_verification_smoke.py`` asserts the same without a
Blender, so the rule also fires early.

**Beside the per-tool items the run performs three run-level items, and the set
is closed**: the install gate, the leak compare, and the traceback item. A
fourth is a sign that the exhaustive habit is growing back.

Run with::

    MPFB_MCP_RECORD_DIR=~/mpfb-mcp-records PYTHONPATH=. python3 verification/smoke.py
"""

from __future__ import annotations

__all__ = ("ITEMS", "Skipped", "coverage_errors", "run")

import os
import re
import sys
import time

from mpfbmcp import codegen
from mpfbmcp.connection import send_code

from verification import fixtures, harness
from verification.harness import Report

# The design target, printed and never enforced. Wall clock against somebody
# else's Blender is too noisy and too install-dependent to gate on, and a check
# that fails for a reason outside the repository is one people learn to ignore.
TARGET_SECONDS = 60.0

# The descriptions an MCP client downloads, filled by run(). Read by the
# contract-key check below, which holds each item's ``keys`` to what the tool
# itself still says it always answers with.
_DESCRIPTIONS = dict()


class Skipped(Exception):
    """This install cannot reach this item. Carries the reason, which is reported."""


class _Run:
    """What the items have in common: the tools, the report, and what was built.

    The whole run is one character, so an item that produces an address later
    items need - the character, the equipped asset - puts it here rather than
    rebuilding it.
    """

    def __init__(self, tools: dict, report: Report) -> None:
        self.tools = tools
        self.report = report
        self.character = None
        self.asset_object = None
        self.rigs = None
        self.rig_family = None
        self.materials = None

    def __call__(self, tool_name: str, **arguments: object) -> dict:
        """A helper call: a prerequisite an item needs, not the item's own call."""
        return self.tools[tool_name](**arguments)


ITEMS = []


def _item(tool_name: str, *keys: str):
    """Register the one smoke item for a tool, with its contract keys."""
    def register(function):
        ITEMS.append(dict(tool=tool_name, keys=keys, call=function))
        return function
    return register


# --------------------------------------------------------------------------
# The item table. The order is the ordering constraint the tools report and do
# not enforce: rig before assets, Rigify generation after them. Everything
# read-only that needs no character comes first, so a catalogue an item below
# depends on has already been asked for.
# --------------------------------------------------------------------------


@_item("mpfb_get_status", "state", "message", "candidate_modules", "package", "enabled",
       "blender")
def _get_status(run: _Run) -> dict:
    return run.tools["mpfb_get_status"]()


@_item("mpfb_list_targets", "sections")
def _list_targets(run: _Run) -> dict:
    return run.tools["mpfb_list_targets"]()


@_item("mpfb_list_rigs", "rigs", "count", "families", "rigify_available", "rig_dirs")
def _list_rigs(run: _Run) -> dict:
    envelope = run.tools["mpfb_list_rigs"]()
    if envelope.get("status") == "ok":
        run.rigs = envelope["result"]["rigs"]
    return envelope


@_item("mpfb_list_assets", "assets", "count", "total_count", "truncated", "offset", "limit",
       "counts_by_subdir")
def _list_assets(run: _Run) -> dict:
    return run.tools["mpfb_list_assets"]()


@_item("mpfb_create_human", "object_name", "vertex_count", "macro_detail_dict")
def _create_human(run: _Run) -> dict:
    envelope, name = fixtures.create_character(run.tools)
    run.character = name
    return envelope


@_item("mpfb_list_objects", "objects", "count", "requested_type", "type_recognized",
       "known_types")
def _list_objects(run: _Run) -> dict:
    return run.tools["mpfb_list_objects"]()


@_item("mpfb_get_object_info", "found", "resolved_from", "message")
def _get_object_info(run: _Run) -> dict:
    return run.tools["mpfb_get_object_info"](name=_character(run))


@_item("mpfb_get_macro_details", "macro_details", "default_macro_details", "race_sum",
       "macro_target_stack")
def _get_macro_details(run: _Run) -> dict:
    return run.tools["mpfb_get_macro_details"](name=_character(run))


@_item("mpfb_set_macro_details", "changed", "macro_details", "race_sum", "basemesh_name")
def _set_macro_details(run: _Run) -> dict:
    # One slider. A call naming none does nothing, deliberately, and would come
    # back performed: false - which is the right answer and the wrong smoke test.
    return run.tools["mpfb_set_macro_details"](name=_character(run), gender=0.6)


@_item("mpfb_get_target_stack", "targets", "modifiers", "asymmetries", "basemesh_name",
       "counts_by_kind", "total_count", "truncated")
def _get_target_stack(run: _Run) -> dict:
    return run.tools["mpfb_get_target_stack"](name=_character(run))


@_item("mpfb_set_targets", "applied", "basemesh_name", "shapekeys_added", "shapekeys_removed")
def _set_targets(run: _Run) -> dict:
    section, category = _sided_category(run)
    # One side of a left/right category, so that the symmetrize item below has
    # an asymmetry to remove. Nothing else about the value matters.
    return run.tools["mpfb_set_targets"](
        name=_character(run),
        modifiers=[dict(section=section, category=category, side="left", value=0.5)])


@_item("mpfb_symmetrize_targets", "changed", "already_symmetric", "basemesh_name", "skipped")
def _symmetrize_targets(run: _Run) -> dict:
    # `direction` is the package's only required argument: which half of a
    # character is the good one is not something a tool can guess.
    return run.tools["mpfb_symmetrize_targets"](name=_character(run), direction="left_to_right")


@_item("mpfb_add_rig", "rig_object_name", "basemesh_name", "family", "weights_loaded")
def _add_rig(run: _Run) -> dict:
    identifier, family = _first_available_rig(run)
    run.rig_family = family
    return run.tools["mpfb_add_rig"](name=_character(run), identifier=identifier)


@_item("mpfb_add_asset", "asset_object_name", "basemesh_name", "resolved_path", "asset_source")
def _add_asset(run: _Run) -> dict:
    asset = fixtures.first_asset(run.tools, "clothes")
    if asset is None:
        raise Skipped("this install has no asset under 'clothes'")
    # `asset_type` is required and is exactly the catalogue's `object_type`;
    # MPFB's own "Clothes" default is wrong for six of the eight types.
    envelope = run.tools["mpfb_add_asset"](
        name=_character(run), fragment=asset["fragment"], asset_type=asset["object_type"])
    if envelope.get("status") == "ok":
        run.asset_object = envelope["result"].get("asset_object_name")
    return envelope


@_item("mpfb_list_asset_materials", "found", "asset_object_name", "materials", "count",
       "search_roots")
def _list_asset_materials(run: _Run) -> dict:
    envelope = run.tools["mpfb_list_asset_materials"](name=_asset_object(run))
    if envelope.get("status") == "ok":
        run.materials = envelope["result"].get("materials") or []
    return envelope


@_item("mpfb_set_asset_material", "asset_object_name", "object_type", "resolved_path",
       "material_name")
def _set_asset_material(run: _Run) -> dict:
    asset_object = _asset_object(run)
    if not run.materials:
        raise Skipped("no MHMAT ships beside the asset this run equipped")
    # The first workable answer the catalogue gave, which on most assets is the
    # asset's own material. Applying it is the least interesting legal call.
    return run.tools["mpfb_set_asset_material"](
        name=asset_object, path=run.materials[0]["path"])


@_item("mpfb_set_skin", "basemesh_name", "resolved_path", "skin_type_used",
       "material_instances_requested", "materials_destroyed")
def _set_skin(run: _Run) -> dict:
    skin = fixtures.first_asset(run.tools, "skins")
    if skin is None:
        raise Skipped("this install has no asset under 'skins'")
    # `skin_type` left at its MAKESKIN default, which is MPFB's settings panel
    # rather than the function signature, and which creates no material instances.
    return run.tools["mpfb_set_skin"](name=_character(run), fragment=skin["fragment"])


@_item("mpfb_refit_human", "basemesh_name", "rig_name", "mesh_assets", "mesh_asset_count",
       "subrigs")
def _refit_human(run: _Run) -> dict:
    return run.tools["mpfb_refit_human"](name=_character(run))


@_item("mpfb_generate_rigify_rig", "rig_object_name", "metarig_name", "metarig_disposition",
       "active_object_after")
def _generate_rigify_rig(run: _Run) -> dict:
    if run.rig_family != "rigify":
        raise Skipped("the rig this install offered ({}) is not a Rigify meta rig".format(
            run.rig_family))
    return run.tools["mpfb_generate_rigify_rig"](name=_character(run))


@_item("mpfb_remove_asset", "asset_object_name", "object_type", "basemesh_name",
       "objects_removed")
def _remove_asset(run: _Run) -> dict:
    return run.tools["mpfb_remove_asset"](name=_asset_object(run))


# --------------------------------------------------------------------------
# What an item needs from the install, asked of the catalogue tools rather than
# named by filename here. FR-6: the run works on any adequate install, and names
# what it could not exercise.
# --------------------------------------------------------------------------


def _character(run: _Run) -> str:
    if run.character is None:
        raise Skipped("the character was not created")
    return run.character


def _asset_object(run: _Run) -> str:
    if run.asset_object is None:
        raise Skipped("no asset was equipped, so there is none to act on")
    return run.asset_object


def _first_available_rig(run: _Run) -> tuple:
    """A Rigify meta rig if this install has one, otherwise any available rig.

    Preferring Rigify is not about rigging: it is what lets the
    ``mpfb_generate_rigify_rig`` item run at all. An install without Rigify
    still gets its rig added and skips only the generation.
    """
    rigs = run.rigs or []
    available = [rig for rig in rigs if rig.get("available")]
    for family in ("rigify", "standard", "custom"):
        for rig in available:
            if rig.get("family") == family:
                return rig["identifier"], family
    raise Skipped("this install offers no rig that can be added")


def _sided_category(run: _Run) -> tuple:
    """The first left/right modeling category MPFB's index holds here.

    Asked of ``mpfb_list_targets`` section by section rather than named, because
    a section table is partly synthesized from the user's own target
    directories. In practice this is one or two extra calls.
    """
    sections = (run("mpfb_list_targets")["result"].get("sections") or [])
    for section in sections:
        categories = run("mpfb_list_targets",
                         section=section["name"])["result"].get("categories") or []
        for category in categories:
            if category.get("has_left_and_right"):
                return section["name"], category["name"]
    raise Skipped("MPFB's target index here holds no left/right category")


# --------------------------------------------------------------------------
# The run.
# --------------------------------------------------------------------------


def coverage_errors(registered: set) -> list:
    """FR-1: exactly one item per registered tool, and no item for anything else."""
    named = [item["tool"] for item in ITEMS]
    errors = []
    for tool_name in sorted(set(named)):
        if named.count(tool_name) > 1:
            errors.append("{} has {} smoke items; it must have exactly one".format(
                tool_name, named.count(tool_name)))
    for tool_name in sorted(registered - set(named)):
        errors.append("{} is registered but has no smoke item".format(tool_name))
    for tool_name in sorted(set(named) - registered):
        errors.append("{} has a smoke item but is not registered".format(tool_name))
    return errors


def _keys_the_tool_names(tool_name: str) -> set:
    """Every response field the tool's own description mentions.

    The description is the contract an MCP client downloads, so it is the thing
    to hold an item's ``keys`` to - which is what keeps that tuple from quietly
    becoming a second, private copy of the contract. Read leniently on purpose:
    a field is named in prose, sometimes as ``blender.version`` and sometimes as
    ``found: false``, so what is taken from each backticked span is its leading
    identifier. Being generous here costs nothing - the point is that a key the
    description has stopped mentioning at all cannot go on being checked for.
    """
    documentation = _DESCRIPTIONS.get(tool_name, "")
    named = set()
    for span in re.findall(r"`([^`]+)`", documentation):
        match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", span.strip())
        if match:
            named.add(match.group(0))
    return named


def _run_item(run: _Run, item: dict) -> None:
    """One tool, one call, three assertions - or one skip with its reason."""
    tool_name = item["tool"]
    started = time.perf_counter()
    try:
        envelope = item["call"](run)
    except Skipped as skipped:
        run.report.skip(tool_name, str(skipped), time.perf_counter() - started)
        return
    elapsed = time.perf_counter() - started

    if envelope.get("status") != "ok":
        run.report.check(tool_name, False,
                         dict(status=envelope.get("status"), message=envelope.get("message"),
                              record=envelope.get("mpfb_mcp_record")), elapsed)
        return

    result = envelope.get("result")
    problems = []
    if not isinstance(result, dict):
        problems.append("result is {!r}, not an object".format(type(result).__name__))
        result = dict()
    problems += ["contract key {!r} missing from the answer".format(key)
                 for key in item["keys"] if key not in result]
    named = _keys_the_tool_names(tool_name)
    problems += ["contract key {!r} is not named by the tool's own description".format(key)
                 for key in item["keys"] if key not in named]
    if tool_name in harness.MUTATING_VERBS:
        if result.get("performed") is not True:
            problems.append("performed is {!r}, and this is a mutating tool".format(
                result.get("performed")))
        disagreement = harness.performed_disagreement(tool_name, envelope)
        if disagreement is not None:
            problems.append(disagreement)

    run.report.check(tool_name, not problems,
                     "; ".join(problems) if problems else _worth_reporting(result), elapsed)


def _worth_reporting(result: dict) -> object:
    """The handful of fields that make a passing line say what actually happened."""
    interesting = ("state", "found", "name", "count", "total_count", "object_name",
                   "asset_object_name", "rig_object_name", "basemesh_name", "performed")
    return {key: result[key] for key in interesting if key in result} or None


def _traceback_item(report: Report) -> None:
    """FR 012's inherited check: does a line number from Blender resolve?

    The only part of the per-call record that a test on this side of the socket
    cannot make - nothing in ``tests/`` has ever received a line number from a
    real Blender. The program is built the way ``codegen.assemble()`` builds one,
    so the number has the same distance to travel as a real tool's would.
    """
    item = "a traceback line number from a real failure resolves to the recorded program"
    if not os.environ.get("MPFB_MCP_RECORD_DIR"):
        report.skip(item, "MPFB_MCP_RECORD_DIR is not set, so there is no record to resolve "
                          "against; the run does not require it")
        return

    started = time.perf_counter()
    program = codegen.assemble("get_status.py", bootstrap="non_raising", params=dict())
    if not program.endswith("\n"):
        program = program + "\n"
    program = program + 'raise RuntimeError("MPFB_MCP_DELIBERATE_FAILURE")\n'
    # The raise is the last line; splitting on the trailing newline leaves an
    # empty final element, so the raise is the one before it.
    expected_line = len(program.split("\n")) - 1

    response = send_code(program, strict_json=True)
    elapsed = time.perf_counter() - started
    record = response.get("mpfb_mcp_record") or dict()
    matches = re.findall(r'File "<string>", line (\d+)', response.get("message") or "")
    reported_line = int(matches[-1]) if matches else 0

    dumped = ""
    if record.get("program") and os.path.isfile(record["program"]):
        handle = open(record["program"], "r", encoding="utf-8")
        dumped = handle.read()
        handle.close()
    lines = dumped.split("\n")
    at_reported = lines[reported_line - 1] if 0 < reported_line <= len(lines) else None

    report.check(item,
                 reported_line == expected_line
                 and at_reported is not None
                 and "MPFB_MCP_DELIBERATE_FAILURE" in at_reported,
                 dict(traceback_line=reported_line, expected_line=expected_line,
                      line_in_the_recorded_program=at_reported,
                      program=record.get("program")),
                 elapsed)


def run() -> dict:
    global _DESCRIPTIONS  # pylint: disable=global-statement
    tools = harness.tools()
    _DESCRIPTIONS = harness.descriptions()

    errors = coverage_errors(set(tools))
    if errors:
        # Not a report line: FR-4 closes the set of run-level items at three, and
        # a table that does not match the registry means the run below would be
        # measuring the wrong thing anyway.
        print("!!! the smoke item table does not match the registered tools:",
              file=sys.stderr, flush=True)
        for error in errors:
            print("    {}".format(error), file=sys.stderr, flush=True)
        return dict(failed=1, exit_code=2)

    report = Report("mpfb-mcp smoke run - twenty tools, default arguments")

    install = fixtures.check_install(tools)
    if not report.check("MPFB is loaded and initialized", install["usable"], install["state"]
                        or install.get("envelope")):
        report.note("nothing below can run against this install")
        counts = report.summary(TARGET_SECONDS)
        counts["exit_code"] = 2
        return counts
    report.note("MPFB {} on Blender {}, Rigify {}".format(
        install["mpfb_version"], install["blender"],
        "available" if install["rigify_available"] else "not enabled"))

    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()

    _traceback_item(report)

    smoke_run = _Run(tools, report)
    for item in ITEMS:
        _run_item(smoke_run, item)

    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("the run put back everything it made",
                 difference["identical"] and not difference["is_dirty_after"], difference)

    counts = report.summary(TARGET_SECONDS)
    counts["exit_code"] = 1 if counts["failed"] else 0
    return counts


if __name__ == "__main__":
    sys.exit(run().get("exit_code", 0))
