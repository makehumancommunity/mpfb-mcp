# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 008's checklist: detail targets, live.

The item this exists for is "the slider round trip, which is the whole point",
and like FR 007's it turns out to be automatable exactly rather than by
eyeballing a panel. ``ui/model/_modelsubpanels.py`` registers one
``FloatProperty`` per modeling category on ``bpy.types.Scene``, named
``UiService.as_valid_identifier(section + "." + category)`` - so
``nose.nose-scale-horiz-decr-incr`` is ``scene.nose_nose_scale_horiz_decr_incr``
and reading it *is* reading MPFB's own slider. Both directions are checked here:
a value written by ``mpfb_set_targets`` read off the slider, and a value written
to the slider read back by ``mpfb_get_target_stack``.

**What needs a restarted Blender, and why it is not faked.** That property table
is built at *module import time*, so a target installed after Blender started is
invisible to MPFB's panel however correct mpfb-mcp is about it. Three items
therefore have two halves: the mpfb-mcp half, which runs here, and the
MPFB-panel half, which needs the probe targets to have been on disk when Blender
started. Those halves are skipped with that reason rather than approximated, and
[run_all.py](run_all.py) says when to take the restart.

Run with::

    python3 verification/check_fr008.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys

from verification import fixtures, harness
from verification.harness import Report, probe

ITEMS = (
    "a modifier set through the tool reads back on MPFB's own slider",
    "a modifier moved on MPFB's slider reads back through mpfb_get_target_stack",
    "a negative value, a sided value and a value at exactly zero",
    "a target not on the mesh is loaded from the right file, named as the catalogue said",
    "a user target addressed by shapekey_name applies and reads back",
    "an over-60-character user target applies under its encoded name",
    "the gzipped-custom-target naming divergence, observed",
    "the gzipped custom target really does become two shape keys",
    "the Blender 0.0-1.0 clamp on shape key values, observed",
    "the basis-substring exclusion, observed",
    "symmetrize in both directions, with dry_run first and with a section filter",
    "a dry run's per-target list is null rather than empty",
    "a macro change after detail targets leaves the detail stack intact",
)

# A bundled, unsided category and a bundled, sided one. Both were installed
# before Blender started, which is what makes MPFB's own slider exist for them.
UNSIDED = dict(section="nose", category="nose-scale-horiz-decr-incr")
SIDED = dict(section="arms", category="lowerarm-scale-depth-decr-incr")


def run() -> dict:
    tools = harness.tools()
    report = Report("FR 008 - detail targets", ITEMS)
    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()
    fixtures.install_probe_targets()

    character = "TargetCharacter"
    fixtures.fresh_human(tools, character)

    _check_tool_to_slider(tools, report, character)
    _check_slider_to_tool(tools, report, character)
    _check_value_range(tools, report, character)
    _check_load_on_demand(tools, report, character)
    _check_user_targets(tools, report, character)
    _check_clamp(tools, report, character)
    _check_symmetrize(tools, report, character)
    _check_macro_leaves_details(tools, report, character)

    fixtures.remove_probe_targets()
    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("revert: every datablock collection identical afterwards",
                 difference["identical"] and not difference["is_dirty_after"], difference)
    return report.summary()


def _slider(character: str, section: str, category: str, side: str = "") -> float:
    return probe("read_slider", _READ_SLIDER_CODE, name=character,
                 section=section, category=category, side=side)["value"]


def _check_tool_to_slider(tools: dict, report: Report, character: str) -> None:
    tools["mpfb_set_targets"](name=character, modifiers=[
        dict(UNSIDED, value=0.62)])
    observed = _slider(character, UNSIDED["section"], UNSIDED["category"])
    report.check("a modifier set through the tool reads back on MPFB's own slider",
                 abs(observed - 0.62) < 1e-5,
                 dict(wrote=0.62, mpfb_slider_reads=observed,
                      property=probe("ident", _IDENT_CODE, section=UNSIDED["section"],
                                     category=UNSIDED["category"], side="")["identifier"]))


def _check_slider_to_tool(tools: dict, report: Report, character: str) -> None:
    probe("write_slider", _WRITE_SLIDER_CODE, name=character,
          section=UNSIDED["section"], category=UNSIDED["category"], side="", value=0.4)
    stack = tools["mpfb_get_target_stack"](name=character)["result"]
    entry = _modifier_entry(stack, UNSIDED["category"])
    report.check("a modifier moved on MPFB's slider reads back through mpfb_get_target_stack",
                 entry is not None and abs(entry["value"] - 0.4) < 1e-5,
                 dict(wrote_on_slider=0.4, tool_reads=None if entry is None else entry["value"],
                      entry=entry))


def _check_value_range(tools: dict, report: Report, character: str) -> None:
    negative = tools["mpfb_set_targets"](name=character, modifiers=[
        dict(UNSIDED, value=-0.5)])
    negative_slider = _slider(character, UNSIDED["section"], UNSIDED["category"])

    sided = tools["mpfb_set_targets"](name=character, modifiers=[
        dict(SIDED, value=0.7, side="left")])
    left_slider = _slider(character, SIDED["section"], SIDED["category"], side="l-")
    right_slider = _slider(character, SIDED["section"], SIDED["category"], side="r-")

    tools["mpfb_set_targets"](name=character, modifiers=[dict(UNSIDED, value=0.0)])
    zero_slider = _slider(character, UNSIDED["section"], UNSIDED["category"])

    report.check("a negative value, a sided value and a value at exactly zero",
                 abs(negative_slider + 0.5) < 1e-5 and abs(left_slider - 0.7) < 1e-5
                 and abs(right_slider) < 1e-5 and abs(zero_slider) < 1e-5,
                 dict(negative=negative_slider, left=left_slider, right=right_slider,
                      zero=zero_slider,
                      negative_status=negative.get("status"),
                      sided_status=sided.get("status")))


def _check_load_on_demand(tools: dict, report: Report, character: str) -> None:
    """A category never touched before: the file has to come off disk on this call."""
    fresh = dict(section="chin", category="chin-prognathism-decr-incr")
    catalogue = tools["mpfb_list_targets"](section="chin", limit=500)["result"]
    catalogue_names = dict()
    for category in catalogue["categories"]:
        for target_name in category["targets"]:
            catalogue_names[target_name] = category

    before_keys = set(probe("keys", _KEYS_CODE, name=character)["names"])
    response = tools["mpfb_set_targets"](name=character, modifiers=[dict(fresh, value=0.55)])
    after_keys = set(probe("keys", _KEYS_CODE, name=character)["names"])
    new_keys = sorted(after_keys - before_keys)
    result = response.get("result") or dict()

    # A bundled target's shape key name is its filename with the extension
    # stripped, and no bundled name is long enough to be encoded - which is why
    # the catalogue's own vocabulary is what is compared against here.
    predicted = [name for name in ("chin-prognathism-incr", "chin-prognathism-decr")
                 if name in catalogue_names]
    report.check("a target not on the mesh is loaded from the right file, named as the "
                 "catalogue said",
                 bool(new_keys) and all(key in predicted for key in new_keys),
                 dict(new_shapekeys=new_keys, catalogue_predicted=predicted,
                      loaded_from=[target.get("loaded_from")
                                   for entry in (result.get("applied") or [])
                                   for target in entry.get("targets", [])],
                      applied=result.get("applied")))


def _check_user_targets(tools: dict, report: Report, character: str) -> None:
    """The two probe targets addressed as raw targets rather than as modifiers."""
    catalogue = tools["mpfb_list_targets"](section="custom", limit=500)["result"]
    entries = dict((entry["name"], entry) for entry in catalogue["user_targets"])

    long_name = [name for name in entries if "a_very_long_female" in name]
    basis_name = [name for name in entries if "basis" in name]

    if not long_name:
        report.skip("a user target addressed by shapekey_name applies and reads back",
                    "the long probe target is not in the catalogue")
        report.skip("an over-60-character user target applies under its encoded name",
                    "the long probe target is not in the catalogue")
    else:
        entry = entries[long_name[0]]
        response = tools["mpfb_set_targets"](name=character, targets=[
            dict(shapekey_name=entry["shapekey_name"], value=0.8)])
        keys = probe("keys_values", _KEYS_CODE, name=character)
        values = dict(keys["values"])
        result = response.get("result") or dict()
        report.check("a user target addressed by shapekey_name applies and reads back",
                     entry["shapekey_name"] in values
                     and abs(values[entry["shapekey_name"]] - 0.8) < 1e-5,
                     dict(addressed=entry["shapekey_name"],
                          on_mesh=entry["shapekey_name"] in values,
                          value=values.get(entry["shapekey_name"]),
                          applied=result.get("applied")))
        report.check("an over-60-character user target applies under its encoded name",
                     entry["shapekey_name"] != entry["name"]
                     and entry["shapekey_name"] in values,
                     dict(filename=entry["name"], shapekey_name=entry["shapekey_name"],
                          filename_length=len(entry["name"]),
                          encoded=entry["shapekey_name"] != entry["name"]))

    if not basis_name:
        report.skip("the basis-substring exclusion, observed",
                    "the basis probe target is not in the catalogue")
    else:
        entry = entries[basis_name[0]]
        tools["mpfb_set_targets"](name=character, targets=[
            dict(shapekey_name=entry["shapekey_name"], value=0.5)])
        seen = probe("basis_visibility", _BASIS_CODE, name=character,
                     shapekey=entry["shapekey_name"])
        stack = tools["mpfb_get_target_stack"](name=character, limit=500)["result"]
        in_tool = [item for item in stack["targets"]
                   if item["shapekey_name"] == entry["shapekey_name"]]
        report.check("the basis-substring exclusion, observed",
                     seen["on_mesh"] and not seen["visible_to_targetservice"] and bool(in_tool),
                     dict(on_mesh=seen["on_mesh"],
                          visible_to_targetservice=seen["visible_to_targetservice"],
                          reported_by_get_target_stack=bool(in_tool),
                          flag=in_tool[0].get("visible_to_targetservice") if in_tool else None))

    _check_gzip_divergence(tools, report, character, entries)


def _check_gzip_divergence(tools: dict, report: Report, character: str, entries: dict) -> None:
    gzipped = [name for name in entries if "vwide" in name]
    if not gzipped:
        report.skip("the gzipped-custom-target naming divergence, observed",
                    "the gzipped probe target is not in the catalogue")
        return
    entry = entries[gzipped[0]]
    names = probe("divergence", _DIVERGENCE_CODE, filename=entry["path"])
    registered = probe("registered", _REGISTERED_CODE, section="custom",
                       category=names["modelsubpanel_name"])
    report.check("the gzipped-custom-target naming divergence, observed",
                 names["modelsubpanel_name"] != names["targetservice_name"],
                 dict(file=entry["path"],
                      name_mpfb_panel_would_use=names["modelsubpanel_name"],
                      name_targetservice_reports=names["targetservice_name"],
                      catalogue_reports=entry["shapekey_name"],
                      mpfb_panel_property_registered=registered["registered"]))

    # The second half: that the two names really do become two shape keys for
    # one file. MPFB's panel property for a synthesized custom category exists
    # only for a target that was on disk when Blender started, so this half is
    # skipped rather than approximated when it is not.
    if not registered["registered"]:
        report.skip("the gzipped custom target really does become two shape keys",
                    "MPFB's panel property '" + registered["identifier"] + "' is not registered: "
                    "_modelsubpanels builds its table at module import time, so this needs a "
                    "Blender started with the .target.gz already installed")
        return

    both = probe("two_shapekeys", _TWO_SHAPEKEYS_CODE, name=character,
                 identifier=registered["identifier"],
                 catalogue_name=entry["shapekey_name"])
    tools["mpfb_set_targets"](name=character, targets=[
        dict(shapekey_name=entry["shapekey_name"], value=0.7)])
    after = probe("keys_values", _KEYS_CODE, name=character)
    values = dict(after["values"])

    report.check("the gzipped custom target really does become two shape keys",
                 names["modelsubpanel_name"] in values
                 and names["targetservice_name"] in values,
                 dict(after_mpfb_panel_slider=both,
                      shapekeys_now=sorted(name for name in values
                                           if "mpfbmcp_probe_vwide" in name),
                      panel_name_on_mesh=names["modelsubpanel_name"] in values,
                      catalogue_name_on_mesh=names["targetservice_name"] in values,
                      values=dict((name, values[name]) for name in values
                                  if "mpfbmcp_probe_vwide" in name)))


def _check_clamp(tools: dict, report: Report, character: str) -> None:
    """Blender clamps a shape key value to 0.0-1.0, which is why the category level exists."""
    observed = probe("clamp", _CLAMP_CODE, name=character)
    report.check("the Blender 0.0-1.0 clamp on shape key values, observed",
                 observed["after_negative"] == 0.0 and observed["after_over_one"] == 1.0,
                 observed)


def _check_symmetrize(tools: dict, report: Report, character: str) -> None:
    tools["mpfb_set_targets"](name=character, modifiers=[
        dict(SIDED, value=0.65, side="left"),
        dict(SIDED, value=0.0, side="right")])

    dry = tools["mpfb_symmetrize_targets"](
        name=character, direction="left_to_right", dry_run=True)["result"]
    after_dry = _slider(character, SIDED["section"], SIDED["category"], side="r-")

    wet = tools["mpfb_symmetrize_targets"](
        name=character, direction="left_to_right")["result"]
    after_wet = _slider(character, SIDED["section"], SIDED["category"], side="r-")

    filtered = tools["mpfb_symmetrize_targets"](
        name=character, direction="right_to_left", section="nose")["result"]

    # The category-level claims are what the docstring promises ("exactly the
    # changes a real run would make") and are compared in full. The per-target
    # sub-list is compared separately below, because a dry run cannot know
    # which file a write would come from without doing the write.
    def without_targets(entries):
        return [dict((key, value) for key, value in entry.items() if key != "targets")
                for entry in entries]

    report.check("symmetrize in both directions, with dry_run first and with a section filter",
                 abs(after_dry) < 1e-5 and abs(after_wet - 0.65) < 1e-5
                 and without_targets(dry["changed"]) == without_targets(wet["changed"]),
                 dict(right_after_dry_run=after_dry, right_after_symmetrize=after_wet,
                      dry_run_changed=len(dry["changed"]), applied_changed=len(wet["changed"]),
                      dry_run_matches_applied=(
                          without_targets(dry["changed"]) == without_targets(wet["changed"])),
                      section_filtered=dict(section=filtered.get("section"),
                                            recognized=filtered.get("section_recognized"),
                                            changed=len(filtered.get("changed") or []))))

    # FR 006's rule, applied to a dry run: [] means "none of them" and null
    # means "not computed", and a preview that has not touched a shape key
    # cannot honestly claim the first.
    dry_targets = [entry.get("targets") for entry in dry["changed"]]
    report.check("a dry run's per-target list is null rather than empty",
                 all(entry is None for entry in dry_targets),
                 dict(dry_run_targets=dry_targets,
                      applied_targets=[entry.get("targets") for entry in wet["changed"]]))


def _check_macro_leaves_details(tools: dict, report: Report, character: str) -> None:
    """FR 008's interaction check: reapply_macro_details() must touch only $md- keys."""
    tools["mpfb_set_targets"](name=character, modifiers=[dict(UNSIDED, value=0.42)])
    before = probe("keys_values", _KEYS_CODE, name=character)
    detail_before = dict((name, value) for name, value in before["values"]
                         if not name.startswith("$md-") and name != "Basis")

    tools["mpfb_set_macro_details"](name=character, gender=0.85, age=0.3)
    after = probe("keys_values", _KEYS_CODE, name=character)
    detail_after = dict((name, value) for name, value in after["values"]
                        if not name.startswith("$md-") and name != "Basis")

    report.check("a macro change after detail targets leaves the detail stack intact",
                 detail_before == detail_after and bool(detail_before),
                 dict(detail_keys=len(detail_before),
                      lost=sorted(set(detail_before) - set(detail_after)),
                      gained=sorted(set(detail_after) - set(detail_before)),
                      changed=sorted(name for name in set(detail_before) & set(detail_after)
                                     if detail_before[name] != detail_after[name])))


def _modifier_entry(stack: dict, category: str) -> dict:
    for entry in stack.get("modifiers") or []:
        if entry.get("category") == category:
            return entry
    return None


_IDENT_CODE = '''
import sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
UiService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["UiService"]

result = dict(identifier=UiService.as_valid_identifier(
    PARAMS["section"] + "." + PARAMS["side"] + PARAMS["category"]))
'''

_READ_SLIDER_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
UiService = services["UiService"]
ObjectService = services["ObjectService"]

# The panel's getter resolves the basemesh from the *active object*, so the
# subject has to be active before the property is read. That is a property of
# MPFB's UI, not of this probe.
ObjectService.activate_blender_object(bpy.data.objects.get(PARAMS["name"]), deselect_all=True)

identifier = UiService.as_valid_identifier(
    PARAMS["section"] + "." + PARAMS["side"] + PARAMS["category"])
result = dict(identifier=identifier,
              registered=hasattr(bpy.types.Scene, identifier),
              value=round(float(getattr(bpy.context.scene, identifier)), 6))
'''

_WRITE_SLIDER_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
UiService = services["UiService"]
ObjectService = services["ObjectService"]

ObjectService.activate_blender_object(bpy.data.objects.get(PARAMS["name"]), deselect_all=True)
identifier = UiService.as_valid_identifier(
    PARAMS["section"] + "." + PARAMS["side"] + PARAMS["category"])
setattr(bpy.context.scene, identifier, PARAMS["value"])
result = dict(identifier=identifier,
              value=round(float(getattr(bpy.context.scene, identifier)), 6))
'''

_REGISTERED_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
UiService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["UiService"]

identifier = UiService.as_valid_identifier(PARAMS["section"] + "." + PARAMS["category"])
result = dict(identifier=identifier, registered=hasattr(bpy.types.Scene, identifier))
'''

_TWO_SHAPEKEYS_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
ObjectService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
ObjectService.activate_blender_object(basemesh, deselect_all=True)

# MPFB's own slider for this synthesized custom category. Setting it loads the
# target under the name _modelsubpanels built, which is the half of the
# divergence that lives on MPFB's side.
setattr(bpy.context.scene, PARAMS["identifier"], 0.5)

keys = []
if basemesh.data.shape_keys is not None:
    keys = sorted([str(block.name) for block in basemesh.data.shape_keys.key_blocks])

result = dict(slider=PARAMS["identifier"],
              slider_reads=round(float(getattr(bpy.context.scene, PARAMS["identifier"])), 6),
              shapekeys=[name for name in keys if "mpfbmcp_probe_vwide" in name])
'''

_DIVERGENCE_CODE = '''
import os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
TargetService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["TargetService"]

filename = PARAMS["filename"]

# _modelsubpanels.py builds a synthesized category's name with a *substring*
# replace that does not strip ".gz". TargetService strips it first. The two are
# reproduced side by side here rather than asserted from source.
modelsubpanel_name = str(os.path.basename(filename)).replace(".target", "")
targetservice_name = str(TargetService.filename_to_shapekey_name(filename))

result = dict(modelsubpanel_name=modelsubpanel_name,
              targetservice_name=targetservice_name)
'''

_KEYS_CODE = '''
import bpy

basemesh = bpy.data.objects.get(PARAMS["name"])
names = []
values = []
if basemesh is not None and basemesh.data.shape_keys is not None:
    for block in basemesh.data.shape_keys.key_blocks:
        names.append(block.name)
        values.append([block.name, round(float(block.value), 6)])

result = dict(names=sorted(names), values=sorted(values))
'''

_BASIS_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
TargetService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["TargetService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
shapekey = PARAMS["shapekey"]

on_mesh = False
if basemesh.data.shape_keys is not None:
    on_mesh = shapekey in [block.name for block in basemesh.data.shape_keys.key_blocks]

# get_target_stack() excludes anything *containing* "basis", so MPFB's own
# panel and every TargetService write is blind to it.
visible = shapekey in [entry["target"] for entry in TargetService.get_target_stack(basemesh)]

result = dict(on_mesh=on_mesh, visible_to_targetservice=visible)
'''

_CLAMP_CODE = '''
import bpy

basemesh = bpy.data.objects.get(PARAMS["name"])
block = basemesh.data.shape_keys.key_blocks[1]
original = float(block.value)

block.value = -0.5
after_negative = round(float(block.value), 6)
block.value = 1.5
after_over_one = round(float(block.value), 6)
block.value = original

result = dict(shapekey=block.name, slider_min=round(float(block.slider_min), 6),
              slider_max=round(float(block.slider_max), 6),
              after_negative=after_negative, after_over_one=after_over_one)
'''


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
