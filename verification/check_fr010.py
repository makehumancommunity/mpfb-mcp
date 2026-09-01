# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 010's checklist: mesh assets, live. The largest of the seven.

Two of its items are comparisons against a UI, and both turn out to be exact
rather than approximate once the operator is read.
``ui/apply_assets/assetlibrary/operators/loadlibraryclothes.py`` reads the
asset-settings panel and then calls the same ``HumanService.add_mhclo_asset()``
``mpfb_add_asset`` calls, so "indistinguishable from the panel" is a diff of two
objects rather than a screenshot. ``loadlibraryproxy.py`` is the opposite and
that is the finding: it does *not* call ``add_mhclo_asset()`` at all, it loads
the MHCLO itself - which is the divergence FR 010's Architecture section rests
on, measured here instead of read.

This checklist also settles two claims for other requests, which is why FR 013
puts it third: [FR 009](../feature-requests/done/009-add-rig/README.md)'s
ordering constraint from the equipping end, and the first live evidence that
[FR 007](../feature-requests/done/007-macro-details/README.md)'s
``mpfb_refit_human`` does anything at all.

Run with::

    python3 verification/check_fr010.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys
import time

from verification import fixtures, harness
from verification.harness import Report, probe

ITEMS = (
    "a garment equipped through the tool is indistinguishable from one equipped "
    "through MPFB's asset library panel",
    "each of the eight asset_type values at least once",
    "the proxy divergence, measured rather than read from source",
    "mpfb_add_asset reproduces the code path its docstring names",
    "material_type NONE on an MHCLO that names a material leaves no material",
    "an MHCLO declaring no delete vertices produces no delete group",
    "two copies of one asset, the .001 naming, and removal taking the right one",
    "removal end to end: mask, sub-rig, vertex groups, and the character as it was",
    "equip then rig: rigged_to null was telling the truth",
    "a macro change then mpfb_refit_human re-fits the garment",
    "cost of equipping one asset",
)


def run() -> dict:
    tools = harness.tools()
    report = Report("FR 010 - mesh assets", ITEMS)
    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()

    _check_against_the_panel(tools, report)
    _check_every_asset_type(tools, report)
    _check_proxy_divergence(tools, report)
    _check_material_none(tools, report)
    _check_no_delete_group(tools, report)
    _check_two_copies(tools, report)
    _check_removal(tools, report)
    _check_ordering(tools, report)
    _check_refit(tools, report)
    _check_cost(tools, report)

    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("revert: every datablock collection identical afterwards",
                 difference["identical"] and not difference["is_dirty_after"], difference)
    return report.summary()


def _check_against_the_panel(tools: dict, report: Report) -> None:
    """The same garment twice: once through MPFB's operator, once through the tool."""
    path = fixtures.check_install(tools)["paths"]["clothes"]

    fixtures.fresh_human(tools, "PanelCharacter")
    tools["mpfb_add_rig"](name="PanelCharacter", identifier="default")
    through_panel = probe("panel_equip", _PANEL_EQUIP_CODE,
                          name="PanelCharacter", path=path, object_type="Clothes",
                          material_type="MAKESKIN")

    fixtures.fresh_human(tools, "ToolEquipCharacter")
    tools["mpfb_add_rig"](name="ToolEquipCharacter", identifier="default")
    tools["mpfb_add_asset"](name="ToolEquipCharacter", path=path, asset_type="Clothes",
                            material_type="MAKESKIN")

    panel_state = probe("garment_state", _GARMENT_STATE_CODE,
                        name=through_panel["garment"])
    tool_garment = probe("find_garment", _FIND_GARMENT_CODE, name="ToolEquipCharacter")
    tool_state = probe("garment_state", _GARMENT_STATE_CODE, name=tool_garment["garment"])

    comparable = ("asset_source", "object_type", "vertex_count", "polygon_count",
                  "material_names", "modifier_types", "vertex_group_names",
                  "parent_type", "delete_group_on_basemesh", "vertex_hash", "scale_factor")

    # Both objects and both materials are named after the character they hang
    # off, so the character's name is stripped before comparing. What is left is
    # the part that would differ if the two code paths differed.
    def normalised(state, character):
        stripped = dict(state)
        stripped["material_names"] = [name.replace(character + ".", "")
                                      for name in state["material_names"]]
        return stripped

    panel_normalised = normalised(panel_state, "PanelCharacter")
    tool_normalised = normalised(tool_state, "ToolEquipCharacter")
    differences = dict((key, [panel_normalised[key], tool_normalised[key]])
                       for key in comparable if panel_normalised[key] != tool_normalised[key])
    report.check("a garment equipped through the tool is indistinguishable from one equipped "
                 "through MPFB's asset library panel",
                 not differences,
                 dict(differences=differences,
                      panel_object=through_panel["garment"],
                      tool_object=tool_garment["garment"],
                      compared=list(comparable),
                      material_names=[panel_state["material_names"],
                                      tool_state["material_names"]],
                      vertex_hash=tool_state["vertex_hash"]))
    harness.cleanup_scratch_scene()


def _check_every_asset_type(tools: dict, report: Report) -> None:
    """All eight MHCLO asset types, since the delete-group and colour branches key on it."""
    wanted = (("Clothes", "clothes"), ("Hair", "hair"), ("Eyes", "eyes"),
              ("Eyebrows", "eyebrows"), ("Eyelashes", "eyelashes"), ("Teeth", "teeth"),
              ("Tongue", "tongue"), ("Proxymeshes", "proxymeshes"))
    fixtures.fresh_human(tools, "AllTypesCharacter")
    outcomes = []
    ok = True
    for asset_type, subdir in wanted:
        listing = tools["mpfb_list_assets"](asset_subdir=subdir, limit=5)["result"]
        if not listing["assets"]:
            outcomes.append(dict(asset_type=asset_type, skipped="nothing installed"))
            ok = False
            continue
        entry = listing["assets"][0]
        response = tools["mpfb_add_asset"](name="AllTypesCharacter", fragment=entry["fragment"],
                                           asset_type=asset_type)
        result = response.get("result") or dict()
        outcome = dict(asset_type=asset_type, fragment=entry["fragment"],
                       added=result.get("added"), object_name=result.get("asset_object_name"),
                       recorded_type=result.get("object_type_recorded"),
                       material_type=result.get("material_type_used"),
                       delete_group=result.get("delete_group_name"))
        if not result.get("added"):
            ok = False
            outcome["message"] = response.get("message") or result.get("message")
        outcomes.append(outcome)
    report.check("each of the eight asset_type values at least once", ok, outcomes)
    harness.cleanup_scratch_scene()


def _check_proxy_divergence(tools: dict, report: Report) -> None:
    """The claim FR 010's Architecture section rests on, observed.

    Three MPFB code paths were named as differing, and they are measured here
    against each other rather than compared to mpfb-mcp: ``add_mhclo_asset()``
    alone, ``HumanService._check_add_proxy()`` (which is also what a ``.mhm``
    load calls, so the third named path *is* this one), and the asset library's
    proxy operator. Then, separately, the tool is compared against the path its
    docstring says it follows - which is the claim that can actually be wrong.
    """
    path = fixtures.check_install(tools)["paths"]["proxy"]

    paths = dict()
    for label, character in (("add_mhclo_asset", "ProxyRawCharacter"),
                             ("_check_add_proxy", "ProxyServiceCharacter"),
                             ("library_operator", "ProxyPanelCharacter")):
        # Every character gets a rig first: MPFB's proxy library operator
        # refuses outright when its "set up rigging" setting is on and there is
        # no rig, and that setting is on by default. Comparing a rigged proxy
        # against an unrigged one would be a difference this check invented.
        fixtures.fresh_human(tools, character)
        tools["mpfb_add_rig"](name=character, identifier="default")
        added = probe("mpfb_proxy_path", _MPFB_PROXY_PATH_CODE,
                      name=character, path=path, which=label,
                      fragment=fixtures.PROXY_ASSET)
        paths[label] = probe("proxy_state", _PROXY_STATE_CODE,
                             name=character, proxy=added["proxy"])

    fixtures.fresh_human(tools, "ProxyToolCharacter")
    tools["mpfb_add_rig"](name="ProxyToolCharacter", identifier="default")
    tool_response = tools["mpfb_add_asset"](
        name="ProxyToolCharacter", path=path, asset_type="Proxymeshes")["result"]
    tool_state = probe("proxy_state", _PROXY_STATE_CODE,
                       name="ProxyToolCharacter",
                       proxy=tool_response["asset_object_name"])

    compared = ("basemesh_mask_modifiers", "proxy_modifier_types", "vertex_group_count",
                "material_names", "scale_factor", "object_type", "asset_source",
                "has_corrective_shapekeys")

    def differences(left: dict, right: dict) -> dict:
        return dict((key, dict(left=left[key], right=right[key]))
                    for key in compared if left[key] != right[key])

    raw_vs_service = differences(paths["add_mhclo_asset"], paths["_check_add_proxy"])
    service_vs_operator = differences(paths["_check_add_proxy"], paths["library_operator"])
    # What is asserted is the difference the *decision* rests on: following
    # add_mhclo_asset() alone - the obvious implementation - would produce a
    # different character from the one _check_add_proxy() produces. Whether the
    # library operator also differs is reported rather than asserted, because
    # FR 010 predicted it would and it does not.
    report.check("the proxy divergence, measured rather than read from source",
                 bool(raw_vs_service),
                 dict(add_mhclo_asset_vs_check_add_proxy=raw_vs_service,
                      check_add_proxy_vs_library_operator=service_vs_operator,
                      library_operator_agrees_with_the_service_path=not service_vs_operator,
                      note=("the third path FR 010 named - a .mhm load - is "
                            "_check_add_proxy(), which deserialize_from_dict() calls, "
                            "so it is that column rather than a fourth; and the library "
                            "operator, which FR 010 called a third variant, produced "
                            "identical state on every field compared - it is a duplicated "
                            "implementation rather than a divergent one")))

    tool_vs_service = differences(tool_state, paths["_check_add_proxy"])
    report.check("mpfb_add_asset reproduces the code path its docstring names",
                 not tool_vs_service,
                 dict(differences=tool_vs_service,
                      tool=tool_state["basemesh_mask_modifiers"],
                      _check_add_proxy=paths["_check_add_proxy"]["basemesh_mask_modifiers"],
                      proxy_extras=tool_response.get("proxy_extras")))
    harness.cleanup_scratch_scene()


def _check_material_none(tools: dict, report: Report) -> None:
    path = fixtures.check_install(tools)["paths"]["clothes"]
    fixtures.fresh_human(tools, "NoMaterialCharacter")
    response = tools["mpfb_add_asset"](name="NoMaterialCharacter", path=path,
                                       asset_type="Clothes", material_type="NONE")
    result = response.get("result") or dict()
    state = probe("garment_state", _GARMENT_STATE_CODE, name=result.get("asset_object_name"))
    report.check("material_type NONE on an MHCLO that names a material leaves no material",
                 state["material_names"] == [],
                 dict(materials=state["material_names"],
                      warnings=result.get("warnings"),
                      mhclo_names_a_material=True))
    harness.cleanup_scratch_scene()


def _check_no_delete_group(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "NoDeleteCharacter")
    with_delete = tools["mpfb_add_asset"](
        name="NoDeleteCharacter", fragment=fixtures.CLOTHES_ASSET,
        asset_type="Clothes")["result"]
    without_delete = tools["mpfb_add_asset"](
        name="NoDeleteCharacter", fragment=fixtures.NO_DELETE_GROUP_ASSET,
        asset_type="Clothes")["result"]
    report.check("an MHCLO declaring no delete vertices produces no delete group",
                 with_delete["delete_group_name"] is not None
                 and without_delete["delete_group_name"] is None,
                 dict(declares_delete_verts=with_delete["delete_group_name"],
                      declares_none=without_delete["delete_group_name"],
                      applied_to=with_delete.get("delete_group_applied_to")))
    harness.cleanup_scratch_scene()


def _check_two_copies(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "TwoCopiesCharacter")
    first = tools["mpfb_add_asset"](name="TwoCopiesCharacter",
                                    fragment=fixtures.CLOTHES_ASSET,
                                    asset_type="Clothes")["result"]
    second = tools["mpfb_add_asset"](name="TwoCopiesCharacter",
                                     fragment=fixtures.CLOTHES_ASSET,
                                     asset_type="Clothes")["result"]
    removed = tools["mpfb_remove_asset"](name=second["asset_object_name"])["result"]
    survivors = probe("children", _CHILDREN_CODE, name="TwoCopiesCharacter")
    report.check("two copies of one asset, the .001 naming, and removal taking the right one",
                 first["asset_object_name"] != second["asset_object_name"]
                 and second["asset_object_name"].endswith(".001")
                 and removed["removed"]
                 and first["asset_object_name"] in survivors["children"]
                 and second["asset_object_name"] not in survivors["children"],
                 dict(first=first["asset_object_name"], second=second["asset_object_name"],
                      removed=removed.get("objects_removed"),
                      survivors=survivors["children"]))
    harness.cleanup_scratch_scene()


def _check_removal(tools: dict, report: Report) -> None:
    """Removal end to end, with a body proxy present so both masks are in scope."""
    fixtures.fresh_human(tools, "RemovalCharacter")
    tools["mpfb_add_rig"](name="RemovalCharacter", identifier="default")
    tools["mpfb_add_asset"](name="RemovalCharacter",
                            fragment=fixtures.PROXY_ASSET, asset_type="Proxymeshes")
    before_state = probe("family", _FAMILY_CODE, name="RemovalCharacter")

    equipped = tools["mpfb_add_asset"](name="RemovalCharacter",
                                       fragment=fixtures.CLOTHES_ASSET,
                                       asset_type="Clothes")["result"]
    dressed_state = probe("family", _FAMILY_CODE, name="RemovalCharacter")
    removal = tools["mpfb_remove_asset"](name=equipped["asset_object_name"])["result"]
    after_state = probe("family", _FAMILY_CODE, name="RemovalCharacter")

    masks_gone = all(
        "mhmask" not in modifier.lower()
        for modifiers in after_state["modifiers"].values() for modifier in modifiers)
    report.check("removal end to end: mask, sub-rig, vertex groups, and the character as it was",
                 removal["removed"] and masks_gone
                 and sorted(after_state["objects"]) == sorted(before_state["objects"])
                 and after_state["modifiers"] == before_state["modifiers"],
                 dict(masks_while_dressed=dressed_state["modifiers"],
                      masks_after=after_state["modifiers"],
                      objects_before=sorted(before_state["objects"]),
                      objects_after=sorted(after_state["objects"]),
                      vertex_groups_left_behind=removal.get("vertex_groups_left_behind"),
                      mask_modifiers_removed=removal.get("mask_modifiers_removed"),
                      subrigs_removed=removal.get("subrigs_removed")))
    harness.cleanup_scratch_scene()


def _check_ordering(tools: dict, report: Report) -> None:
    """Character B: dressed first, rigged second. The claim a convention rests on."""
    fixtures.build_character_b(tools)
    state = probe("rigging", _RIGGING_CODE, name=fixtures.CHARACTER_B)

    fixtures.fresh_human(tools, "RightOrderCharacter")
    tools["mpfb_add_rig"](name="RightOrderCharacter", identifier="default")
    right_order = tools["mpfb_add_asset"](name="RightOrderCharacter",
                                          fragment=fixtures.CLOTHES_ASSET,
                                          asset_type="Clothes")["result"]
    right_state = probe("rigging", _RIGGING_CODE, name="RightOrderCharacter")

    wrong = [entry for entry in state["garments"] if entry["is_garment"]]
    right = [entry for entry in right_state["garments"] if entry["is_garment"]]
    report.check("equip then rig: rigged_to null was telling the truth",
                 bool(wrong) and not any(entry["armature_modifier"] for entry in wrong)
                 and bool(right) and all(entry["armature_modifier"] for entry in right)
                 and right_order["rigged_to"] is not None,
                 dict(dressed_then_rigged=wrong, rigged_then_dressed=right,
                      tool_reported_rigged_to=right_order["rigged_to"]))
    harness.cleanup_scratch_scene()


def _check_refit(tools: dict, report: Report) -> None:
    """FR 007's refit, seen doing something for the first time."""
    fixtures.fresh_human(tools, "RefitCharacter")
    tools["mpfb_add_rig"](name="RefitCharacter", identifier="default")
    equipped = tools["mpfb_add_asset"](name="RefitCharacter",
                                       fragment=fixtures.CLOTHES_ASSET,
                                       asset_type="Clothes")["result"]
    garment = equipped["asset_object_name"]

    before = probe("garment_state", _GARMENT_STATE_CODE, name=garment)
    tools["mpfb_set_macro_details"](name="RefitCharacter", weight=0.95, muscle=0.9, refit=False)
    unfitted = probe("garment_state", _GARMENT_STATE_CODE, name=garment)
    refit = tools["mpfb_refit_human"](name="RefitCharacter")["result"]
    after = probe("garment_state", _GARMENT_STATE_CODE, name=garment)

    report.check("a macro change then mpfb_refit_human re-fits the garment",
                 before["vertex_hash"] == unfitted["vertex_hash"]
                 and after["vertex_hash"] != unfitted["vertex_hash"]
                 and refit["refit_performed"],
                 dict(before=before["vertex_hash"], after_macro_change=unfitted["vertex_hash"],
                      after_refit=after["vertex_hash"],
                      macro_change_moved_the_garment=before["vertex_hash"] != unfitted["vertex_hash"],
                      refit_moved_the_garment=after["vertex_hash"] != unfitted["vertex_hash"],
                      refit_performed=refit["refit_performed"],
                      mesh_assets=refit["mesh_assets"]))
    harness.cleanup_scratch_scene()


def _check_cost(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "CostAssetCharacter")
    timings = []
    for fragment in (fixtures.CLOTHES_ASSET, fixtures.NO_DELETE_GROUP_ASSET,
                     fixtures.NO_MATERIAL_ASSET):
        started = time.perf_counter()
        tools["mpfb_add_asset"](name="CostAssetCharacter", fragment=fragment,
                                asset_type="Clothes")
        timings.append(dict(fragment=fragment,
                            ms=round((time.perf_counter() - started) * 1000.0, 1)))
    report.check("cost of equipping one asset", True,
                 dict(timings=timings,
                      median_ms=sorted(entry["ms"] for entry in timings)[1]))
    harness.cleanup_scratch_scene()


_PANEL_EQUIP_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
before = set([obj.name for obj in bpy.data.objects])
ObjectService.activate_blender_object(basemesh, deselect_all=True)

# MPFB's own asset library button, with its own settings panel behind it.
bpy.ops.mpfb.load_library_clothes(filepath=PARAMS["path"],
                                  object_type=PARAMS["object_type"],
                                  material_type=PARAMS["material_type"])

created = sorted(set([obj.name for obj in bpy.data.objects]) - before)
result = dict(created=created, garment=created[0] if created else None)
'''

_MPFB_PROXY_PATH_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
ObjectService = services["ObjectService"]
HumanService = services["HumanService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
before = set([obj.name for obj in bpy.data.objects])
ObjectService.activate_blender_object(basemesh, deselect_all=True)

which = PARAMS["which"]
if which == "add_mhclo_asset":
    # The service function on its own, with the arguments _check_add_proxy()
    # passes it - and nothing else.
    HumanService.add_mhclo_asset(PARAMS["path"], basemesh, asset_type="Proxymeshes",
                                 subdiv_levels=1, material_type="NONE")
elif which == "_check_add_proxy":
    # The private wrapper, which is also what a .mhm load reaches.
    HumanService._check_add_proxy(dict(proxy=PARAMS["fragment"]), basemesh)
else:
    bpy.ops.mpfb.load_library_proxy(filepath=PARAMS["path"], object_type="Proxymeshes")

created = sorted(set([obj.name for obj in bpy.data.objects]) - before)
result = dict(created=created, proxy=created[0] if created else None)
'''

_PANEL_PROXY_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
before = set([obj.name for obj in bpy.data.objects])
ObjectService.activate_blender_object(basemesh, deselect_all=True)

bpy.ops.mpfb.load_library_proxy(filepath=PARAMS["path"], object_type="Proxymeshes")

created = sorted(set([obj.name for obj in bpy.data.objects]) - before)
result = dict(created=created, proxy=created[0] if created else None)
'''

_GARMENT_STATE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
ObjectService = services["ObjectService"]

# GeneralObjectProperties is an entity class, not a service, so it is reached
# off a module rather than out of the SERVICES dict.
GeneralObjectProperties = None
for module_name in list(sys.modules):
    if module_name.endswith("entities.objectproperties"):
        GeneralObjectProperties = getattr(sys.modules[module_name],
                                          "GeneralObjectProperties", None)

garment = bpy.data.objects.get(PARAMS["name"])
if garment is None:
    result = dict(found=False)
else:
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(garment, "Basemesh")

    # A cheap, order-independent fingerprint of where the vertices actually
    # ended up: this is what makes "same fit" and "the refit moved it" claims
    # rather than assumptions.
    total = 0.0
    for vertex in garment.data.vertices:
        total = total + vertex.co.x * 1.0 + vertex.co.y * 2.0 + vertex.co.z * 3.0

    delete_group = None
    if basemesh is not None:
        for modifier in basemesh.modifiers:
            if modifier.type == "MASK":
                delete_group = str(modifier.vertex_group)

    result = dict(
        found=True,
        name=garment.name,
        asset_source=(None if GeneralObjectProperties is None else
                      GeneralObjectProperties.get_value("asset_source", entity_reference=garment)),
        object_type=str(ObjectService.get_object_type(garment)),
        vertex_count=len(garment.data.vertices),
        polygon_count=len(garment.data.polygons),
        material_names=sorted([material.name for material in garment.data.materials
                               if material is not None]),
        modifier_types=sorted([str(modifier.type) for modifier in garment.modifiers]),
        vertex_group_names=sorted([group.name for group in garment.vertex_groups]),
        parent_type=None if garment.parent is None else str(garment.parent.type),
        delete_group_on_basemesh=delete_group,
        vertex_hash=round(total, 4),
        scale_factor=(None if GeneralObjectProperties is None else
                      GeneralObjectProperties.get_value("scale_factor",
                                                        entity_reference=garment)),
    )
'''

_FIND_GARMENT_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
garments = []
for relative in ObjectService.find_related_objects(basemesh):
    if relative == basemesh:
        continue
    if str(ObjectService.get_object_type(relative)) == "Clothes":
        garments.append(relative.name)

result = dict(garments=sorted(garments), garment=sorted(garments)[0] if garments else None)
'''

_FIND_PROXY_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
proxy = ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh, "Proxymeshes")
result = dict(proxy=None if proxy is None else proxy.name)
'''

_PROXY_STATE_CODE = '''
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
proxy = bpy.data.objects.get(PARAMS["proxy"])

scale_factor = None
asset_source = None
if GeneralObjectProperties is not None and proxy is not None:
    scale_factor = GeneralObjectProperties.get_value("scale_factor", entity_reference=proxy)
    asset_source = GeneralObjectProperties.get_value("asset_source", entity_reference=proxy)

corrective = False
if proxy is not None and proxy.data.shape_keys is not None:
    corrective = len(proxy.data.shape_keys.key_blocks) > 0

result = dict(
    proxy=None if proxy is None else proxy.name,
    basemesh_mask_modifiers=sorted(
        [str(modifier.name) + ":" + str(modifier.vertex_group) + ":"
         + str(bool(modifier.invert_vertex_group))
         for modifier in basemesh.modifiers if modifier.type == "MASK"]),
    proxy_modifier_types=sorted(
        [str(modifier.type) for modifier in proxy.modifiers]) if proxy else None,
    vertex_group_count=len(proxy.vertex_groups) if proxy else None,
    material_names=sorted([material.name for material in proxy.data.materials
                           if material is not None]) if proxy else None,
    scale_factor=None if scale_factor is None else round(float(scale_factor), 6),
    object_type=None if proxy is None else str(ObjectService.get_object_type(proxy)),
    asset_source=asset_source,
    has_corrective_shapekeys=corrective,
)
'''

_CHILDREN_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
children = []
for relative in ObjectService.find_related_objects(basemesh):
    if relative != basemesh:
        children.append(relative.name)

result = dict(children=sorted(children))
'''

_FAMILY_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
objects = []
modifiers = dict()
for relative in ObjectService.find_related_objects(basemesh):
    objects.append(relative.name)
    modifiers[relative.name] = sorted([str(modifier.name) for modifier in relative.modifiers])

result = dict(objects=sorted(objects), modifiers=modifiers)
'''

_RIGGING_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
garments = []
for relative in ObjectService.find_related_objects(basemesh):
    if relative == basemesh or relative.type != "MESH":
        continue
    object_type = str(ObjectService.get_object_type(relative))
    armature_modifiers = [str(modifier.name) for modifier in relative.modifiers
                          if modifier.type == "ARMATURE"]
    weighted = 0
    for vertex in relative.data.vertices:
        for element in vertex.groups:
            if element.weight > 0.0:
                weighted = weighted + 1
                break
    garments.append(dict(
        name=relative.name,
        object_type=object_type,
        is_garment=object_type not in ("Basemesh", "Skeleton", ""),
        armature_modifier=armature_modifiers[0] if armature_modifiers else None,
        weighted_vertices=weighted,
    ))

result = dict(garments=garments)
'''


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
