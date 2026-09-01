# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 011's checklist: skin and materials, live. The one with the least stub backing.

A material *is* a node tree and nothing in ``tests/`` builds one, so every item
here is a first observation rather than a re-check. The comparison against
MPFB's own skin library panel is again exact:
``ui/apply_assets/assetlibrary/operators/loadlibraryskin.py`` coerces
``material_instances`` for three of the five types, calls
``HumanService.set_character_skin()`` and then fixes up the active body slot -
which is precisely what ``mpfb_set_skin``'s payload reproduces. So "same node
tree" is a diff of node counts, node types and link counts per slot, taken on
two characters built the same way.

**What cannot be reverted, and is a decision rather than a surprise.**
``enhanced_settings.default.json`` lives in the user's MPFB config directory,
outside the ``.blend`` entirely. To observe the creation FR 011 asks about, the
existing file is moved aside and put back afterwards; if this script is killed
between those two points the file is at the path recorded in the report. The
alternative-material cache is the other one: MPFB gives no way to invalidate it,
so the staleness item asserts the staleness rather than trying to clear it.

Run with::

    python3 verification/check_fr011.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys
import time

from verification import fixtures, harness
from verification.harness import Report, probe

ITEMS = (
    "all five skin_type values produce the node tree MPFB's own panel produces",
    "material_instances true yields the extra slots, carrying the settings file's values",
    "the settings file is created once and not twice",
    "scale_assumption on a character at a non-default scale",
    "a skin on a character with a body proxy reaches both, and reports what it destroyed",
    "LAYERED with no MHMAT at all",
    "mpfb_set_asset_material both directions, with restore_default and a read-back",
    "the alternative-material cache staleness",
    "cost per skin type",
)

SKIN_TYPES = ("MAKESKIN", "ENHANCED", "ENHANCED_SSS", "LAYERED", "GAMEENGINE")


def run() -> dict:
    tools = harness.tools()
    report = Report("FR 011 - skin and materials", ITEMS)
    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()
    skin = fixtures.skin_fragment(tools)
    skin_path = probe("skin_path", _RESOLVE_SKIN_CODE, fragment=skin)["path"]

    _check_five_types_against_the_panel(tools, report, skin, skin_path)
    _check_material_instances(tools, report, skin)
    _check_settings_file(tools, report, skin)
    _check_scale(tools, report, skin)
    _check_body_proxy(tools, report, skin)
    _check_layered_without_mhmat(tools, report)
    _check_alternative_materials(tools, report)
    _check_cache_staleness(tools, report)
    _check_cost(tools, report, skin)

    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("revert: every datablock collection identical afterwards",
                 difference["identical"] and not difference["is_dirty_after"], difference)
    return report.summary()


def _check_five_types_against_the_panel(tools: dict, report: Report,
                                        skin: str, skin_path: str) -> None:
    outcomes = dict()
    identical = True
    for skin_type in SKIN_TYPES:
        panel_character = "SkinPanel" + skin_type
        tool_character = "SkinTool" + skin_type

        fixtures.fresh_human(tools, panel_character)
        probe("panel_skin", _PANEL_SKIN_CODE, name=panel_character,
              path=skin_path, skin_type=skin_type)
        panel_state = probe("material_state", _MATERIAL_STATE_CODE, name=panel_character)

        fixtures.fresh_human(tools, tool_character)
        response = tools["mpfb_set_skin"](name=tool_character, fragment=skin,
                                          skin_type=skin_type)
        result = response.get("result") or dict()
        tool_state = probe("material_state", _MATERIAL_STATE_CODE, name=tool_character)

        same = (panel_state["slot_shapes"] == tool_state["slot_shapes"]
                and panel_state["material_source"] == tool_state["material_source"]
                and panel_state["active_slot_name"] == tool_state["active_slot_name"])
        if not same or not result.get("applied"):
            identical = False
        outcomes[skin_type] = dict(
            applied=result.get("applied"),
            panel=panel_state["slot_shapes"], tool=tool_state["slot_shapes"],
            material_source=[panel_state["material_source"], tool_state["material_source"]],
            active_slot=[panel_state["active_slot_name"], tool_state["active_slot_name"]],
            material_instances_requested=result.get("material_instances_requested"),
            material_instances_used=result.get("material_instances_used"),
            scale_assumption=result.get("scale_assumption"),
            identified_as=result.get("material_identified_as"))
        harness.cleanup_scratch_scene()

    report.check("all five skin_type values produce the node tree MPFB's own panel produces",
                 identical, outcomes)


def _check_material_instances(tools: dict, report: Report, skin: str) -> None:
    """The two types the UI does *not* coerce, so the instancing really runs."""
    fixtures.fresh_human(tools, "InstancesCharacter")
    off = tools["mpfb_set_skin"](name="InstancesCharacter", fragment=skin,
                                 skin_type="ENHANCED_SSS",
                                 material_instances=False)["result"]
    without = probe("material_state", _MATERIAL_STATE_CODE, name="InstancesCharacter")

    fixtures.fresh_human(tools, "InstancesOnCharacter")
    on = tools["mpfb_set_skin"](name="InstancesOnCharacter", fragment=skin,
                                skin_type="ENHANCED_SSS",
                                material_instances=True)["result"]
    with_instances = probe("material_state", _MATERIAL_STATE_CODE, name="InstancesOnCharacter")
    settings = probe("settings_values", _SETTINGS_VALUES_CODE, name="InstancesOnCharacter")

    report.check("material_instances true yields the extra slots, carrying the settings "
                 "file's values",
                 len(with_instances["slot_shapes"]) > len(without["slot_shapes"])
                 and on["material_instances_used"] is True
                 and bool(settings["matching_slots"]),
                 dict(slots_without=[entry["name"] for entry in without["slot_shapes"]],
                      slots_with=[entry["name"] for entry in with_instances["slot_shapes"]],
                      used_without=off["material_instances_used"],
                      used_with=on["material_instances_used"],
                      settings_file=settings["settings_path"],
                      slots_named_in_the_settings_file=settings["matching_slots"],
                      values_agree=settings["values_agree"]))
    harness.cleanup_scratch_scene()


def _check_settings_file(tools: dict, report: Report, skin: str) -> None:
    """Observed on a profile where the file does not exist, then again where it does."""
    moved = probe("move_settings", _MOVE_SETTINGS_CODE, action="aside")
    try:
        fixtures.fresh_human(tools, "SettingsCharacter")
        first = tools["mpfb_set_skin"](name="SettingsCharacter", fragment=skin,
                                       skin_type="ENHANCED_SSS",
                                       material_instances=True)["result"]
        fixtures.fresh_human(tools, "SettingsCharacterTwo")
        second = tools["mpfb_set_skin"](name="SettingsCharacterTwo", fragment=skin,
                                        skin_type="ENHANCED_SSS",
                                        material_instances=True)["result"]

        fixtures.fresh_human(tools, "SettingsCharacterThree")
        default_call = tools["mpfb_set_skin"](name="SettingsCharacterThree",
                                              fragment=skin)["result"]
        report.check("the settings file is created once and not twice",
                     first["settings_file_created"] is True
                     and second["settings_file_created"] is False
                     and default_call["settings_file_created"] is False,
                     dict(existed_before=moved["existed"], moved_to=moved["moved_to"],
                          first_call=first["settings_file_created"],
                          second_call=second["settings_file_created"],
                          default_call=default_call["settings_file_created"],
                          default_call_material_instances=default_call[
                              "material_instances_used"],
                          path=first["settings_file_path"]))
    finally:
        probe("restore_settings", _MOVE_SETTINGS_CODE, action="restore")
    harness.cleanup_scratch_scene()


def _check_scale(tools: dict, report: Report, skin: str) -> None:
    """All three bands, and what a character created by MPFB actually reports.

    The band for an ordinary character is the thing worth observing here rather
    than the arithmetic: the ``scale_factor`` *property* declares a default of
    1.0, but ``create_human()`` writes 0.1 onto every character it makes, so the
    band is ``METER`` and not the ``DECIMETER`` this package's documentation
    inferred from the property default.
    """
    fixtures.fresh_human(tools, "ScaleCharacter")
    observed_default = probe("read_scale", _READ_SCALE_CODE, name="ScaleCharacter")
    default_scale = tools["mpfb_set_skin"](name="ScaleCharacter", fragment=skin,
                                           skin_type="ENHANCED_SSS")["result"]

    bands = dict()
    for scale, character in ((1.0, "DecimetreCharacter"), (10.0, "CentimetreCharacter")):
        fixtures.fresh_human(tools, character)
        probe("set_scale", _SET_SCALE_CODE, name=character, scale=scale)
        bands[scale] = tools["mpfb_set_skin"](name=character, fragment=skin,
                                              skin_type="ENHANCED_SSS")["result"][
                                                  "scale_assumption"]

    fixtures.fresh_human(tools, "MakeskinScaleCharacter")
    makeskin = tools["mpfb_set_skin"](name="MakeskinScaleCharacter",
                                      fragment=skin, skin_type="MAKESKIN")["result"]

    report.check("scale_assumption on a character at a non-default scale",
                 default_scale["scale_assumption"] == "METER"
                 and bands[1.0] == "DECIMETER" and bands[10.0] == "CENTIMETER"
                 and makeskin["scale_assumption"] is None,
                 dict(scale_factor_of_a_created_character=observed_default["scale_factor"],
                      created_character_band=default_scale["scale_assumption"],
                      scale_factor_1_0=bands[1.0], scale_factor_10=bands[10.0],
                      makeskin=makeskin["scale_assumption"]))
    harness.cleanup_scratch_scene()


def _check_body_proxy(tools: dict, report: Report, skin: str) -> None:
    fixtures.fresh_human(tools, "ProxySkinCharacter")
    tools["mpfb_add_asset"](name="ProxySkinCharacter", fragment=fixtures.PROXY_ASSET,
                            asset_type="Proxymeshes")
    handmade = probe("handmade_material", _HANDMADE_MATERIAL_CODE, name="ProxySkinCharacter")
    result = tools["mpfb_set_skin"](name="ProxySkinCharacter", fragment=skin,
                                    skin_type="MAKESKIN")["result"]
    state = probe("proxy_material_state", _PROXY_MATERIAL_STATE_CODE,
                  name="ProxySkinCharacter", proxy=result["bodyproxy_name"])
    # materials_destroyed is per object: a list of {object_name, materials}, so
    # that "the proxy's were destroyed too" is a claim about a named object
    # rather than a flat list nobody can attribute.
    destroyed = [name for record in (result["materials_destroyed"] or [])
                 for name in record["materials"]]
    report.check("a skin on a character with a body proxy reaches both, and reports what it "
                 "destroyed",
                 result["bodyproxy_name"] is not None
                 and handmade["material"] in destroyed
                 and bool(state["proxy_materials"]) and bool(state["basemesh_materials"]),
                 dict(bodyproxy=result["bodyproxy_name"],
                      materials_destroyed=result["materials_destroyed"],
                      handmade_material=handmade["material"],
                      basemesh_materials=state["basemesh_materials"],
                      proxy_materials=state["proxy_materials"],
                      active_body_slot=result["active_body_slot"]))
    harness.cleanup_scratch_scene()


def _check_layered_without_mhmat(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "LayeredCharacter")
    layered = tools["mpfb_set_skin"](name="LayeredCharacter", skin_type="LAYERED")
    layered_result = layered.get("result") or dict()
    state = probe("material_state", _MATERIAL_STATE_CODE, name="LayeredCharacter")

    # Every other type with no file is refused in the tool module, before any
    # code is generated - so it arrives as a raised ValueError rather than as an
    # envelope. Catching it here is what makes "refused in both layers" a check
    # rather than a crash.
    fixtures.fresh_human(tools, "NoPathCharacter")
    refused_locally = None
    refused = None
    refused_result = dict()
    try:
        refused = tools["mpfb_set_skin"](name="NoPathCharacter", skin_type="ENHANCED_SSS")
        refused_result = refused.get("result") or dict()
    except ValueError as error:
        refused_locally = str(error)

    report.check("LAYERED with no MHMAT at all",
                 layered_result.get("applied") is True and bool(state["slot_shapes"])
                 and (refused_locally is not None
                      or refused_result.get("applied") is not True),
                 dict(layered_applied=layered_result.get("applied"),
                      layered_slots=[entry["name"] for entry in state["slot_shapes"]],
                      layered_material_source=layered_result.get("material_source"),
                      enhanced_without_path=dict(
                          refused_in_the_tool_module=refused_locally,
                          applied=refused_result.get("applied"),
                          blocked_by=refused_result.get("blocked_by"),
                          status=None if refused is None else refused.get("status"))))
    harness.cleanup_scratch_scene()


def _check_alternative_materials(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "AltMaterialCharacter")
    equipped = tools["mpfb_add_asset"](name="AltMaterialCharacter",
                                       fragment=fixtures.ALTERNATIVE_MATERIAL_ASSET,
                                       asset_type="Clothes")["result"]
    garment = equipped["asset_object_name"]

    listing = tools["mpfb_list_asset_materials"](name=garment)["result"]
    alternatives = [entry for entry in listing["materials"] if not entry["is_default"]]

    first = tools["mpfb_set_asset_material"](
        name=garment, fragment=alternatives[0]["fragment"])["result"]
    after_first = tools["mpfb_get_object_info"](name=garment)["result"]
    second = tools["mpfb_set_asset_material"](
        name=garment, fragment=alternatives[1]["fragment"])["result"]
    after_second = tools["mpfb_get_object_info"](name=garment)["result"]
    restored = tools["mpfb_set_asset_material"](name=garment, restore_default=True)["result"]
    after_restore = tools["mpfb_get_object_info"](name=garment)["result"]

    # mpfb_get_object_info reports the recorded fragment as
    # asset_info.material_source, filled from `material_source` for a skin and
    # from `alternative_material` for anything else - one key, two properties,
    # told apart by the object's type.
    recorded_first = (after_first.get("asset_info") or dict()).get("material_source")
    recorded_second = (after_second.get("asset_info") or dict()).get("material_source")
    recorded_restored = (after_restore.get("asset_info") or dict()).get("material_source")

    report.check("mpfb_set_asset_material both directions, with restore_default and a "
                 "read-back",
                 first["applied"] and second["applied"] and restored["applied"]
                 and recorded_first == first["alternative_material"]
                 and recorded_second == second["alternative_material"]
                 and recorded_restored != recorded_second,
                 dict(available=[entry["name"] for entry in listing["materials"]],
                      default_flagged=[entry["name"] for entry in listing["materials"]
                                       if entry["is_default"]],
                      first=dict(applied=first["applied"], recorded=recorded_first,
                                 alternative_material=first["alternative_material"],
                                 material_name=first.get("material_name"),
                                 previous=first.get("previous_alternative_material")),
                      second=dict(applied=second["applied"], recorded=recorded_second),
                      restored=dict(applied=restored["applied"], recorded=recorded_restored,
                                    reason=restored.get("default_material_reason"))))
    harness.cleanup_scratch_scene()


def _check_cache_staleness(tools: dict, report: Report) -> None:
    """MPFB caches this scan per asset with no way to invalidate it."""
    fixtures.fresh_human(tools, "CacheCharacter")
    equipped = tools["mpfb_add_asset"](name="CacheCharacter",
                                       fragment=fixtures.ALTERNATIVE_MATERIAL_ASSET,
                                       asset_type="Clothes")["result"]
    garment = equipped["asset_object_name"]

    first = tools["mpfb_list_asset_materials"](name=garment)["result"]
    written = probe("write_mhmat", _WRITE_MHMAT_CODE,
                    fragment=fixtures.ALTERNATIVE_MATERIAL_ASSET, action="write")
    try:
        second = tools["mpfb_list_asset_materials"](name=garment)["result"]
    finally:
        probe("remove_mhmat", _WRITE_MHMAT_CODE,
              fragment=fixtures.ALTERNATIVE_MATERIAL_ASSET, action="remove")
    report.check("the alternative-material cache staleness",
                 [entry["name"] for entry in first["materials"]]
                 == [entry["name"] for entry in second["materials"]],
                 dict(before=[entry["name"] for entry in first["materials"]],
                      after_writing_a_new_mhmat=[entry["name"]
                                                 for entry in second["materials"]],
                      written=written["path"],
                      note=("MPFB caches alternative_materials_for_asset() per "
                            "(asset_source, asset_subdir) and never invalidates it, so a "
                            "restarted Blender is the only way to see the new file")))
    harness.cleanup_scratch_scene()


def _check_cost(tools: dict, report: Report, skin: str) -> None:
    timings = dict()
    for skin_type in SKIN_TYPES:
        character = "CostSkin" + skin_type
        fixtures.fresh_human(tools, character)
        started = time.perf_counter()
        tools["mpfb_set_skin"](name=character, fragment=skin, skin_type=skin_type)
        timings[skin_type] = round((time.perf_counter() - started) * 1000.0, 1)
        harness.cleanup_scratch_scene()
    report.check("cost per skin type", True, timings)


_RESOLVE_SKIN_CODE = '''
import sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
AssetService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["AssetService"]

result = dict(path=str(AssetService.find_asset_absolute_path(PARAMS["fragment"], "skins")))
'''

_PANEL_SKIN_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
ObjectService.activate_blender_object(basemesh, deselect_all=True)

# MPFB's own skin library button reads skin_type and material_instances off the
# asset settings panel, so both are set there before pressing it.
scene = bpy.context.scene
touched = []
for attribute in dir(scene):
    if attribute.endswith("skin_type"):
        setattr(scene, attribute, PARAMS["skin_type"])
        touched.append(attribute)

bpy.ops.mpfb.load_library_skin(filepath=PARAMS["path"])

result = dict(properties=touched)
'''

_MATERIAL_STATE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
GeneralObjectProperties = None
for module_name in list(sys.modules):
    if module_name.endswith("entities.objectproperties"):
        GeneralObjectProperties = getattr(sys.modules[module_name],
                                          "GeneralObjectProperties", None)

basemesh = bpy.data.objects.get(PARAMS["name"])

# The shape of a material rather than its name: two characters get two
# differently-named materials for the same skin, so the comparison has to be on
# what the node tree *is*. Node count, the sorted set of node types and the link
# count together are enough that a different builder would show up.
shapes = []
for index in range(len(basemesh.data.materials)):
    material = basemesh.data.materials[index]
    if material is None:
        shapes.append(dict(name=None, nodes=None, node_types=None, links=None))
        continue
    tree = material.node_tree
    shapes.append(dict(
        # The character's name prefixes the material's, so it is stripped: what
        # is left is what the builder chose.
        name=str(material.name).replace(PARAMS["name"] + ".", ""),
        nodes=0 if tree is None else len(tree.nodes),
        node_types=[] if tree is None else sorted([str(node.type) for node in tree.nodes]),
        links=0 if tree is None else len(tree.links),
    ))

active_slot_name = None
if len(basemesh.material_slots) > 0:
    slot = basemesh.material_slots[basemesh.active_material_index]
    if slot.material is not None:
        active_slot_name = str(slot.material.name).replace(PARAMS["name"] + ".", "")

material_source = None
if GeneralObjectProperties is not None:
    material_source = GeneralObjectProperties.get_value("material_source",
                                                        entity_reference=basemesh)

result = dict(slot_shapes=shapes, active_slot_name=active_slot_name,
              material_source=material_source)
'''

_SETTINGS_VALUES_CODE = '''
import bpy, json, os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
LocationService = services["LocationService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
settings_path = os.path.join(str(LocationService.get_user_config()),
                             "enhanced_settings.default.json")

settings = dict()
if os.path.isfile(settings_path):
    handle = open(settings_path, "r")
    settings = json.load(handle)
    handle.close()

slot_names = []
for slot in basemesh.material_slots:
    if slot.material is not None:
        slot_names.append(str(slot.material.name).split(".")[-1])

matching = sorted([name for name in slot_names if name in settings])
result = dict(settings_path=settings_path,
              settings_keys=sorted(list(settings))[:20],
              slot_names=sorted(slot_names),
              matching_slots=matching,
              values_agree=len(matching) > 0)
'''

_MOVE_SETTINGS_CODE = '''
import os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
LocationService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["LocationService"]

settings_path = os.path.join(str(LocationService.get_user_config()),
                             "enhanced_settings.default.json")
aside_path = settings_path + ".mpfbmcp-verification-backup"

existed = os.path.isfile(settings_path)
moved_to = None
if PARAMS["action"] == "aside":
    if existed:
        if os.path.exists(aside_path):
            os.remove(aside_path)
        os.rename(settings_path, aside_path)
        moved_to = aside_path
else:
    if os.path.isfile(aside_path):
        if os.path.exists(settings_path):
            os.remove(settings_path)
        os.rename(aside_path, settings_path)
        moved_to = settings_path

result = dict(existed=existed, moved_to=moved_to, path=settings_path,
              present_now=os.path.isfile(settings_path))
'''

_READ_SCALE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
GeneralObjectProperties = None
for module_name in list(sys.modules):
    if module_name.endswith("entities.objectproperties"):
        GeneralObjectProperties = getattr(sys.modules[module_name],
                                          "GeneralObjectProperties", None)

basemesh = bpy.data.objects.get(PARAMS["name"])
result = dict(scale_factor=round(float(GeneralObjectProperties.get_value(
    "scale_factor", entity_reference=basemesh)), 6))
'''

_SET_SCALE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
GeneralObjectProperties = None
for module_name in list(sys.modules):
    if module_name.endswith("entities.objectproperties"):
        GeneralObjectProperties = getattr(sys.modules[module_name],
                                          "GeneralObjectProperties", None)

basemesh = bpy.data.objects.get(PARAMS["name"])
GeneralObjectProperties.set_value("scale_factor", PARAMS["scale"], entity_reference=basemesh)
result = dict(scale_factor=GeneralObjectProperties.get_value("scale_factor",
                                                             entity_reference=basemesh))
'''

_HANDMADE_MATERIAL_CODE = '''
import bpy

basemesh = bpy.data.objects.get(PARAMS["name"])
material = bpy.data.materials.new(PARAMS["name"] + ".handmade")
basemesh.data.materials.append(material)
result = dict(material=material.name,
              materials=[m.name for m in basemesh.data.materials if m is not None])
'''

_PROXY_MATERIAL_STATE_CODE = '''
import bpy

basemesh = bpy.data.objects.get(PARAMS["name"])
proxy = bpy.data.objects.get(PARAMS["proxy"]) if PARAMS["proxy"] else None

result = dict(
    basemesh_materials=[m.name for m in basemesh.data.materials if m is not None],
    proxy_materials=None if proxy is None else [m.name for m in proxy.data.materials
                                                if m is not None],
)
'''

_WRITE_MHMAT_CODE = '''
import os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
AssetService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["AssetService"]

asset_path = str(AssetService.find_asset_absolute_path(PARAMS["fragment"], "clothes"))
new_path = os.path.join(os.path.dirname(asset_path), "mpfbmcp_verification_probe.mhmat")

if PARAMS["action"] == "write":
    handle = open(new_path, "w")
    handle.write("name mpfbmcp_verification_probe\\ndiffuseColor 1.0 0.0 0.0\\n")
    handle.close()
elif os.path.isfile(new_path):
    os.remove(new_path)

result = dict(path=new_path, exists=os.path.isfile(new_path))
'''


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
