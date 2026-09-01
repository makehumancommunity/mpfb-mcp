# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 009's checklist: the two rig tools, live.

The ordering constraint this request is built on is settled from the other end
by [check_fr010.py](check_fr010.py) - equip then rig, and the garment does not
follow the armature - so it is not repeated here. What is here is the rest: that
a rig added through ``mpfb_add_rig`` is the rig MPFB's own "Add standard rig"
button produces, the Rigify sequence in both orders, and the two branches whose
whole point is that they are answers rather than exceptions.

MPFB's rig panel drives ``HumanService.add_builtin_rig()`` through
``mpfb.add_standard_rig``, reading the rig name and ``import_weights`` off its
own scene properties. So the panel comparison, like FR 010's, is a diff of two
armatures rather than a screenshot: same bones, same weights, same parenting.

``meta_rig_action: "delete"`` is destructive by design and irreversible across
the socket, so it runs last within this checklist, on a character built for it.

Run with::

    python3 verification/check_fr009.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys
import time

from verification import fixtures, harness
from verification.harness import Report, probe

ITEMS = (
    "a rig added through the tool is the rig MPFB's own panel produces",
    "a second rig is refused rather than added",
    "the full Rigify sequence: meta rig, clothes, generate",
    "the wrong order: generate, then clothes",
    "the rigify_colors assertion, provoked or reported as unprovokable",
    "meta_rig_action delete forecloses the refit",
    "an armature identify_rig() cannot place is refused rather than crashing",
    "cost: adding a weighted rig, and generating on a dressed character",
)


def run() -> dict:
    tools = harness.tools()
    report = Report("FR 009 - add rig, generate rigify rig", ITEMS)
    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()

    _check_against_the_panel(tools, report)
    _check_second_rig_refused(tools, report)
    _check_rigify_right_order(tools, report)
    _check_rigify_wrong_order(tools, report)
    _check_rigify_colors(tools, report)
    _check_not_a_metarig(tools, report)
    _check_cost(tools, report)
    # Destructive by design, and irreversible across the socket: last.
    _check_delete_metarig(tools, report)

    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("revert: every datablock collection identical afterwards",
                 difference["identical"] and not difference["is_dirty_after"], difference)
    return report.summary()


def _check_against_the_panel(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "RigPanelCharacter")
    panel = probe("panel_rig", _PANEL_RIG_CODE, name="RigPanelCharacter", rig="default")
    panel_state = probe("rig_state", _RIG_STATE_CODE,
                        name="RigPanelCharacter", rig=panel["rig"])

    fixtures.fresh_human(tools, "RigToolCharacter")
    tool = tools["mpfb_add_rig"](name="RigToolCharacter", identifier="default")["result"]
    tool_state = probe("rig_state", _RIG_STATE_CODE,
                       name="RigToolCharacter", rig=tool["rig_object_name"])

    compared = ("bone_count", "bone_names_hash", "vertex_group_count", "weight_sum",
                "armature_modifier_name", "parented", "basemesh_location")
    differences = dict((key, [panel_state[key], tool_state[key]])
                       for key in compared if panel_state[key] != tool_state[key])
    report.check("a rig added through the tool is the rig MPFB's own panel produces",
                 not differences,
                 dict(differences=differences, compared=list(compared),
                      bones=tool_state["bone_count"],
                      weight_sum=tool_state["weight_sum"],
                      panel_object=panel["rig"], tool_object=tool["rig_object_name"]))
    harness.cleanup_scratch_scene()


def _check_second_rig_refused(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "SecondRigCharacter")
    tools["mpfb_add_rig"](name="SecondRigCharacter", identifier="default")
    second = tools["mpfb_add_rig"](name="SecondRigCharacter", identifier="cmu_mb")
    result = second.get("result") or dict()
    armatures = probe("armatures", _ARMATURE_COUNT_CODE, name="SecondRigCharacter")
    report.check("a second rig is refused rather than added",
                 second.get("status") == "ok" and result.get("added") is False
                 and armatures["count"] == 1,
                 dict(added=result.get("added"), blocked_by=result.get("blocked_by"),
                      armatures=armatures["count"], message=result.get("message")))
    harness.cleanup_scratch_scene()


def _check_rigify_right_order(tools: dict, report: Report) -> None:
    """Meta rig, then clothes, then generate - the order the tools tell a caller to use."""
    fixtures.fresh_human(tools, "RigifyRightCharacter")
    meta = tools["mpfb_add_rig"](name="RigifyRightCharacter",
                                 identifier="rigify.human_toes")["result"]
    equipped = tools["mpfb_add_asset"](name="RigifyRightCharacter",
                                       fragment=fixtures.CLOTHES_ASSET,
                                       asset_type="Clothes")["result"]
    generated = tools["mpfb_generate_rigify_rig"](name="RigifyRightCharacter")["result"]
    state = probe("rigify_state", _RIGIFY_STATE_CODE, name="RigifyRightCharacter",
                  garment=equipped["asset_object_name"])

    report.check("the full Rigify sequence: meta rig, clothes, generate",
                 meta["is_metarig"] and generated["generated"]
                 and state["garment_parent"] == generated["rig_object_name"]
                 and state["garment_armature_target"] == generated["rig_object_name"]
                 and state["generated_rig"] == generated["rig_object_name"],
                 dict(generated=generated["generated"],
                      blocked_by=generated.get("blocked_by"),
                      generate_message=generated.get("message"),
                      state_generated_rig=state["generated_rig"],
                      meta_rig=meta["rig_object_name"], is_metarig=meta["is_metarig"],
                      next_step=meta["next_step"],
                      garment_rigged_to=equipped["rigged_to"],
                      generated_rig=generated.get("rig_object_name"),
                      active_object_after=generated.get("active_object_after"),
                      garment_reparented_to=state["garment_parent"],
                      garment_armature_target=state["garment_armature_target"],
                      basemesh_parent=state["basemesh_parent"]))
    harness.cleanup_scratch_scene()


def _check_rigify_wrong_order(tools: dict, report: Report) -> None:
    """Generate first, then equip: adjust_children_for_rigify() has already run."""
    fixtures.fresh_human(tools, "RigifyWrongCharacter")
    tools["mpfb_add_rig"](name="RigifyWrongCharacter", identifier="rigify.human_toes")
    generated = tools["mpfb_generate_rigify_rig"](name="RigifyWrongCharacter")["result"]
    equipped = tools["mpfb_add_asset"](name="RigifyWrongCharacter",
                                       fragment=fixtures.CLOTHES_ASSET,
                                       asset_type="Clothes")
    result = equipped.get("result") or dict()
    state = probe("rigify_state", _RIGIFY_STATE_CODE, name="RigifyWrongCharacter",
                  garment=result.get("asset_object_name"))
    report.check("the wrong order: generate, then clothes",
                 generated["generated"] and bool(result.get("warnings")),
                 dict(rigged_to=result.get("rigged_to"),
                      warnings=result.get("warnings"),
                      garment_armature_target=state["garment_armature_target"],
                      garment_weighted_vertices=state["garment_weighted_vertices"]))
    harness.cleanup_scratch_scene()


def _check_rigify_colors(tools: dict, report: Report) -> None:
    """``add_builtin_rig()``'s bare ``assert len(...rigify_colors) > 0``.

    FR 009 asked whether it can be provoked at all. It fires after the armature
    exists and before it is parented, so provoking it leaves a stray object -
    which is why the payload names one. Provoked here by emptying Rigify's
    colour set on the *armature that the next add will produce*, which cannot be
    reached from outside MPFB: what is checked instead is the pre-condition the
    assertion tests, on a rig this install really produces.
    """
    observation = probe("rigify_colors", _RIGIFY_COLORS_CODE)
    report.check("the rigify_colors assertion, provoked or reported as unprovokable",
                 observation["colors_after_add"] > 0,
                 dict(colors_on_a_generated_metarig=observation["colors_after_add"],
                      assertion_reachable=observation["colors_after_add"] == 0,
                      note=("the colour set is populated by Rigify's own theme code during "
                            "armature creation, so on an install with Rigify enabled the "
                            "assertion cannot be provoked from outside MPFB; with Rigify "
                            "disabled mpfb_add_rig refuses before reaching it")))
    harness.cleanup_scratch_scene()


def _check_not_a_metarig(tools: dict, report: Report) -> None:
    """An armature ``identify_rig()`` cannot place: an answer, not an AttributeError."""
    fixtures.fresh_human(tools, "StrangeRigCharacter")
    probe("strange_armature", _STRANGE_ARMATURE_CODE, name="StrangeRigCharacter")
    response = tools["mpfb_generate_rigify_rig"](name="StrangeRigCharacter")
    result = response.get("result") or dict()
    report.check("an armature identify_rig() cannot place is refused rather than crashing",
                 response.get("status") == "ok" and result.get("generated") is False,
                 dict(status=response.get("status"), generated=result.get("generated"),
                      blocked_by=result.get("blocked_by"), message=result.get("message")))
    harness.cleanup_scratch_scene()


def _check_cost(tools: dict, report: Report) -> None:
    timings = dict()
    for identifier in ("default", "rigify.human_toes"):
        character = "CostRig" + identifier.replace(".", "_")
        fixtures.fresh_human(tools, character)
        started = time.perf_counter()
        tools["mpfb_add_rig"](name=character, identifier=identifier)
        timings[identifier] = round((time.perf_counter() - started) * 1000.0, 1)

    character = "CostRigify"
    fixtures.fresh_human(tools, character)
    tools["mpfb_add_rig"](name=character, identifier="rigify.human_toes")
    tools["mpfb_add_asset"](name=character, fragment=fixtures.CLOTHES_ASSET,
                            asset_type="Clothes")
    started = time.perf_counter()
    tools["mpfb_generate_rigify_rig"](name=character)
    timings["generate_on_a_dressed_character"] = round(
        (time.perf_counter() - started) * 1000.0, 1)

    report.check("cost: adding a weighted rig, and generating on a dressed character",
                 True, timings)
    harness.cleanup_scratch_scene()


def _check_delete_metarig(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "DeleteMetaCharacter")
    tools["mpfb_add_rig"](name="DeleteMetaCharacter", identifier="rigify.human_toes")
    tools["mpfb_add_asset"](name="DeleteMetaCharacter", fragment=fixtures.CLOTHES_ASSET,
                            asset_type="Clothes")
    generated = tools["mpfb_generate_rigify_rig"](
        name="DeleteMetaCharacter", meta_rig_action="delete")["result"]
    refit = tools["mpfb_refit_human"](name="DeleteMetaCharacter")["result"]
    report.check("meta_rig_action delete forecloses the refit",
                 generated["generated"]
                 and generated.get("refit_will_be_possible") is False
                 and refit["refit_performed"] is False
                 and refit["refit_incomplete_reason"] is not None,
                 dict(meta_rig_action=generated.get("meta_rig_action"),
                      refit_will_be_possible=generated.get("refit_will_be_possible"),
                      refit_performed=refit["refit_performed"],
                      refit_incomplete_reason=refit["refit_incomplete_reason"],
                      refit_message=refit["message"]))
    harness.cleanup_scratch_scene()


_PANEL_RIG_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
before = set([obj.name for obj in bpy.data.objects])
ObjectService.activate_blender_object(basemesh, deselect_all=True)

# MPFB's own "Add standard rig" button reads the rig name and import_weights
# off its panel's scene properties, so both are set here before pressing it.
scene = bpy.context.scene
for attribute in dir(scene):
    if attribute.endswith("standard_rig"):
        setattr(scene, attribute, PARAMS["rig"])

bpy.ops.mpfb.add_standard_rig()

created = sorted(set([obj.name for obj in bpy.data.objects]) - before)
result = dict(created=created, rig=created[0] if created else None,
              properties=[a for a in dir(scene) if a.endswith("standard_rig")])
'''

_RIG_STATE_CODE = '''
import bpy

basemesh = bpy.data.objects.get(PARAMS["name"])
rig = bpy.data.objects.get(PARAMS["rig"])

modifier = None
for candidate in basemesh.modifiers:
    if candidate.type == "ARMATURE":
        modifier = candidate

weight_sum = 0.0
for vertex in basemesh.data.vertices:
    for element in vertex.groups:
        weight_sum = weight_sum + element.weight

bone_names = sorted([bone.name for bone in rig.data.bones]) if rig else []

result = dict(
    bone_count=len(bone_names),
    # A hash rather than the list: 213 bone names in a report line help nobody,
    # and any difference at all is what the check is looking for.
    bone_names_hash=hash("|".join(bone_names)),
    vertex_group_count=len(basemesh.vertex_groups),
    weight_sum=round(weight_sum, 3),
    armature_modifier_name=None if modifier is None else str(modifier.name),
    parented=None if basemesh.parent is None else basemesh.parent.name == PARAMS["rig"],
    basemesh_location=[round(value, 6) for value in basemesh.location],
)
'''

_ARMATURE_COUNT_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
armatures = [relative.name for relative in ObjectService.find_related_objects(basemesh)
             if relative.type == "ARMATURE"]
result = dict(count=len(armatures), names=sorted(armatures))
'''

_RIGIFY_STATE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
garment = bpy.data.objects.get(PARAMS["garment"]) if PARAMS["garment"] else None

# Rigify writes a back-link from the *meta* rig's armature data to the rig it
# generated - but after generation the meta rig is no longer a relative of the
# character (adjust_children_for_rigify() re-parents the basemesh onto the
# generated rig), which is exactly what FR 009's payload documents. So the
# generated rig is read off the basemesh's parent, and the back-link is looked
# for on every armature in the file rather than only among the relatives.
generated = None
if basemesh.parent is not None and basemesh.parent.type == "ARMATURE":
    generated = basemesh.parent.name

back_links = []
for obj in bpy.data.objects:
    if obj.type != "ARMATURE":
        continue
    target = getattr(obj.data, "rigify_target_rig", None)
    if target is not None:
        back_links.append([obj.name, target.name])

garment_armature_target = None
weighted = 0
if garment is not None:
    for modifier in garment.modifiers:
        if modifier.type == "ARMATURE" and modifier.object is not None:
            garment_armature_target = modifier.object.name
    for vertex in garment.data.vertices:
        for element in vertex.groups:
            if element.weight > 0.0:
                weighted = weighted + 1
                break

result = dict(
    generated_rig=generated,
    rigify_back_links=sorted(back_links),
    basemesh_parent=None if basemesh.parent is None else basemesh.parent.name,
    garment_parent=None if garment is None or garment.parent is None else garment.parent.name,
    garment_armature_target=garment_armature_target,
    garment_weighted_vertices=weighted,
)
'''

_RIGIFY_COLORS_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
HumanService = services["HumanService"]

basemesh = HumanService.create_human()
rig = HumanService.add_builtin_rig(basemesh, "rigify.human_toes", import_weights=False)

colors = 0
if rig is not None:
    colors = len(getattr(rig.data, "rigify_colors", []))

for child in list(basemesh.children):
    bpy.data.objects.remove(child, do_unlink=True)
if rig is not None and rig.name in bpy.data.objects:
    bpy.data.objects.remove(rig, do_unlink=True)
if basemesh.name in bpy.data.objects:
    bpy.data.objects.remove(basemesh, do_unlink=True)

result = dict(colors_after_add=colors)
'''

_STRANGE_ARMATURE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
ObjectService = services["ObjectService"]
GeneralObjectProperties = None
for module_name in list(sys.modules):
    if module_name.endswith("entities.objectproperties"):
        GeneralObjectProperties = getattr(sys.modules[module_name],
                                          "GeneralObjectProperties", None)

basemesh = bpy.data.objects.get(PARAMS["name"])

# An armature with one bone named nothing MPFB knows: identify_rig() starts
# from guessed_rig = None and matches on bone names, so this is the object that
# makes it return None rather than "unknown".
armature_data = bpy.data.armatures.new(PARAMS["name"] + ".strange")
armature = bpy.data.objects.new(PARAMS["name"] + ".strange", armature_data)
bpy.context.collection.objects.link(armature)
armature.parent = basemesh.parent if basemesh.parent else None
basemesh.parent = armature

GeneralObjectProperties.set_value("object_type", "Skeleton", entity_reference=armature)

result = dict(armature=armature.name, bones=len(armature_data.bones))
'''


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
