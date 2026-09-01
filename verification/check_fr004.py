# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 004's checklist, re-run.

FR 004 was live-verified on 2026-08-29 and that verification went stale the day
[FR 009](../feature-requests/done/009-add-rig/README.md) migrated
``payloads/list_rigs.py`` onto the shared ``rig_lookup.py`` fragment: the unit
tests run the same assertions against the same temporary rig tree and see no
behavior change, but the program sent into Blender is a different program. This
script is that re-run, item for item against the record FR 004 left.

The expensive item is the fourth, and it is the one that makes the re-check
worth doing at all: every identifier the catalogue reports is actually *added*,
through the ``add_function`` the entry named, and the weights that arrive are
compared against the ``weights_from`` the entry predicted. That is the claim the
shared fragment exists to keep true in two places at once, so it is the claim a
migration could have broken.

Run with::

    python3 verification/check_fr004.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys

from verification import harness
from verification.harness import Report, probe

ITEMS = (
    "every rig on disk listed and nothing else",
    "labels resolve from MPFB's UI property JSONs",
    "weights fallbacks predicted correctly",
    "every identifier actually adds, through the add_function named",
    "the negative that justifies add_function, both ways",
    "refresh=true returns the same list twice",
    "rigify_available",
    "rig_dirs",
    "whole response survives strict_json",
)

_RIG_STATE_CODE = '''
import bpy

basemesh = bpy.data.objects.get(PARAMS["basemesh"])
armature_name = PARAMS["armature"]
armature = bpy.data.objects.get(armature_name)

modifier = None
if basemesh is not None:
    for candidate in basemesh.modifiers:
        if candidate.type == "ARMATURE":
            modifier = candidate

# "Real weights" means a vertex group that actually holds a non-zero weight,
# not merely a vertex group of the right name: add_builtin_rig() reports a
# missing weights file through an operator only, so an unweighted rig is silent.
weighted_groups = 0
total_weight = 0.0
if basemesh is not None:
    group_names = set([group.name for group in basemesh.vertex_groups])
    seen = set()
    for vertex in basemesh.data.vertices:
        for element in vertex.groups:
            if element.weight > 0.0:
                name = basemesh.vertex_groups[element.group].name
                if name in group_names:
                    seen.add(name)
                    total_weight = total_weight + element.weight
    weighted_groups = len(seen)

result = dict(
    armature_exists=armature is not None,
    armature_type=None if armature is None else str(armature.type),
    bone_count=0 if armature is None else len(armature.data.bones),
    basemesh_parent=None if basemesh is None or basemesh.parent is None else basemesh.parent.name,
    armature_modifier=None if modifier is None else modifier.name,
    armature_modifier_target=(
        None if modifier is None or modifier.object is None else modifier.object.name),
    vertex_group_count=0 if basemesh is None else len(basemesh.vertex_groups),
    weighted_group_count=weighted_groups,
    total_weight=round(total_weight, 3),
)
'''


def run() -> dict:
    tools = harness.tools()
    report = Report("FR 004 - mpfb_list_rigs (re-check after the rig_lookup migration)", ITEMS)
    harness.ensure_scratch_scene()
    # Whatever a previous run or a previous checklist left in the scratch scene
    # is not this checklist's to report on: clear first, snapshot second, or the
    # revert compare at the end reports somebody else's leftovers.
    harness.cleanup_scratch_scene()
    before = harness.snapshot()

    response = tools["mpfb_list_rigs"]()
    report.check("whole response survives strict_json",
                 response.get("status") == "ok", response.get("message"))
    listing = response["result"]
    rigs = listing["rigs"]
    by_identifier = dict((rig["identifier"], rig) for rig in rigs)

    families = dict()
    for rig in rigs:
        families[rig["family"]] = families.get(rig["family"], 0) + 1
    report.check("every rig on disk listed and nothing else",
                 len(rigs) == 13 and not any(
                     identifier.startswith("weights.") for identifier in by_identifier),
                 dict(count=len(rigs), families=families,
                      unrecognized=listing["unrecognized_custom_rig_files"]))

    labelled = [rig["identifier"] for rig in rigs if rig["label"]]
    report.check("labels resolve from MPFB's UI property JSONs",
                 len(labelled) == 10,
                 dict(labelled=len(labelled),
                      default_no_toes=by_identifier["default_no_toes"]["label"],
                      rigify_human=by_identifier["rigify.human"]["label"],
                      custom_label=by_identifier["custom.gurgel"]["label"]))

    report.check("weights fallbacks predicted correctly",
                 by_identifier["default_no_toes"]["weights_from"] == "default"
                 and by_identifier["rigify.human"]["weights_from"] == "human_toes",
                 dict(default_no_toes=by_identifier["default_no_toes"]["weights_from"],
                      rigify_human=by_identifier["rigify.human"]["weights_from"]))

    report.check("rigify_available", listing["rigify_available"] is True,
                 listing["rigify_available"])
    report.check("rig_dirs",
                 all(entry["exists"] for entry in listing["rig_dirs"]),
                 [(entry["path"], entry["family"], entry["exists"])
                  for entry in listing["rig_dirs"]])

    refreshed = tools["mpfb_list_rigs"](refresh=True)["result"]
    report.check("refresh=true returns the same list twice",
                 [rig["identifier"] for rig in refreshed["rigs"]] == list(by_identifier),
                 refreshed["count"])

    _add_every_rig(tools, report, rigs)
    _check_the_negatives(tools, report)

    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("revert: every datablock collection identical afterwards",
                 difference["identical"] and not difference["is_dirty_after"], difference)
    return report.summary()


def _add_every_rig(tools: dict, report: Report, rigs: list) -> None:
    """Add all thirteen, each to its own basemesh, and compare against the prediction."""
    outcomes = []
    all_added = True
    for rig in rigs:
        identifier = rig["identifier"]
        created = tools["mpfb_create_human"]()
        basemesh = created["result"]["object_name"]
        response = tools["mpfb_add_rig"](name=basemesh, identifier=identifier)
        outcome = dict(identifier=identifier, predicted_weights_from=rig["weights_from"],
                       predicted_add_function=rig["add_function"])
        if response.get("status") != "ok" or not response["result"].get("added"):
            outcome["failed"] = response.get("message") or response["result"].get("message")
            all_added = False
        else:
            result = response["result"]
            state = probe("rig_state", _RIG_STATE_CODE,
                          basemesh=result["basemesh_name"], armature=result["rig_object_name"])
            outcome.update(
                add_function=result["add_function_used"],
                weights_from=result["weights_from"],
                weights_loaded=result["weights_loaded"],
                bones=state["bone_count"],
                weighted_groups=state["weighted_group_count"],
                parented=state["basemesh_parent"] == result["rig_object_name"],
                modifier_targets_rig=(
                    state["armature_modifier_target"] == result["rig_object_name"]))
            if (result["add_function_used"] != rig["add_function"]
                    or result["weights_from"] != rig["weights_from"]
                    or state["weighted_group_count"] < 1
                    or state["basemesh_parent"] != result["rig_object_name"]
                    or state["armature_modifier_target"] != result["rig_object_name"]):
                all_added = False
        outcomes.append(outcome)
        harness.cleanup_scratch_scene()
    report.check("every identifier actually adds, through the add_function named",
                 all_added, outcomes)


def _check_the_negatives(tools: dict, report: Report) -> None:
    """The two mismatches that make add_function load-bearing rather than descriptive.

    FR 004 observed both by calling MPFB directly. Here they are provoked
    through the payload's own pre-checks, since ``mpfb_add_rig`` dispatches on
    the ``custom.`` prefix and will not let a caller make the mistake - which
    is the point, and is why the check is that the tool *refuses* rather than
    that MPFB raises.
    """
    builtin_for_custom = probe("negative_builtin", _NEGATIVE_CODE,
                               function="add_builtin_rig", identifier="custom.gurgel")
    custom_for_builtin = probe("negative_custom", _NEGATIVE_CODE,
                               function="add_custom_rig", identifier="default_no_toes")
    report.check("the negative that justifies add_function, both ways",
                 builtin_for_custom["raised"] and custom_for_builtin["raised"],
                 dict(builtin_given_custom=builtin_for_custom,
                      custom_given_builtin=custom_for_builtin))


_NEGATIVE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
HumanService = services["HumanService"]

# A throwaway basemesh: both functions need one, and both are expected to fail
# before doing anything to it.
basemesh = HumanService.create_human()
raised = None
message = None
try:
    getattr(HumanService, PARAMS["function"])(basemesh, PARAMS["identifier"])
except Exception as exception:
    raised = type(exception).__name__
    message = str(exception)

for child in list(basemesh.children):
    bpy.data.objects.remove(child, do_unlink=True)
bpy.data.objects.remove(basemesh, do_unlink=True)

result = dict(raised=raised is not None, exception=raised, message=message)
'''


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
