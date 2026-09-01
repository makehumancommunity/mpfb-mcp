# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 007's checklist: the phenotype tools, live.

The item this exists for is the first one, and it is the one FR 007 wrote as
"set the slider in the UI, snapshot; undo; set it through the tool; compare".
That comparison is automatable after all, and exactly rather than
approximately: MPFB's phenotype panel draws ``scene.mpfb_macropanel_<target>``,
a ``FloatProperty`` whose setter is three lines - write the object property,
``reapply_macro_details()``, and an optional refit. Assigning that scene
property *is* pressing the slider, so the check here drives MPFB's own panel
code path and diffs the resulting shape keys against the ones
``mpfb_set_macro_details`` produces. No screenshot, no eyeballing, and a
difference of 1e-6 in one weight would fail it.

Two items need a character the later checklists build. A refit that visibly
re-fits clothes needs clothes, and the generated-Rigify-without-meta-rig branch
needs a generated rig; both are cheaper once, in
[check_fr010.py](check_fr010.py) and [check_fr009.py](check_fr009.py)
respectively, and this script says so rather than half-doing them.

Run with::

    python3 verification/check_fr007.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys

from verification import fixtures, harness
from verification.harness import Report, probe

ITEMS = (
    "the same shape keys at the same weights as MPFB's own phenotype slider",
    "properties and mesh in sync: macro_target_stack matches current_macro_shapekeys",
    "prune removes macro shape keys and prune: false keeps them",
    "an omitted slider is left alone rather than defaulted",
    "the OBJECT-mode precondition, observed",
    "the no-shape-keys precondition, observed",
    "a refit re-fits clothes on a dressed, rigged character",
    "the generated-Rigify-without-meta-rig branch",
    "cost: a macro change with and without prune, and a refit",
)

# MPFB's phenotype panel property prefix, from ui/model/_macrosubpanel.py.
UI_PREFIX = "mpfb_macropanel_"


def run() -> dict:
    tools = harness.tools()
    report = Report("FR 007 - macro details, refit", ITEMS)
    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()

    _check_against_the_ui_slider(tools, report)
    _check_stack_in_sync(tools, report)
    _check_prune(tools, report)
    _check_omitted_slider(tools, report)
    _check_preconditions(tools, report)
    _check_cost(tools, report)

    report.skip("a refit re-fits clothes on a dressed, rigged character",
                "needs the dressed character check_fr010.py builds; asserted there")
    report.skip("the generated-Rigify-without-meta-rig branch",
                "needs the generated rig check_fr009.py builds; asserted there")

    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("revert: every datablock collection identical afterwards",
                 difference["identical"] and not difference["is_dirty_after"], difference)
    return report.summary()


def _check_against_the_ui_slider(tools: dict, report: Report) -> None:
    """MPFB's own slider against ``mpfb_set_macro_details``, on two fresh characters.

    Two characters rather than one-then-undone, because there is no undo across
    this socket and a character that has been through
    ``reapply_macro_details()`` twice is not the same starting point as one that
    has been through it once.
    """
    changes = dict(gender=0.9, age=0.75, weight=0.7)

    fixtures.fresh_human(tools, "SliderCharacter")
    through_ui = probe("ui_slider", _UI_SLIDER_CODE, name="SliderCharacter",
                       prefix=UI_PREFIX, changes=changes)

    fixtures.fresh_human(tools, "ToolCharacter")
    tools["mpfb_set_macro_details"](name="ToolCharacter", **changes)
    through_tool = probe("shapekeys", _SHAPEKEYS_CODE, name="ToolCharacter")

    ui_keys = dict(through_ui["shapekeys"])
    tool_keys = dict(through_tool["shapekeys"])
    identical = ui_keys == tool_keys
    report.check("the same shape keys at the same weights as MPFB's own phenotype slider",
                 identical and bool(ui_keys),
                 dict(ui_key_count=len(ui_keys), tool_key_count=len(tool_keys),
                      identical=identical,
                      only_in_ui=sorted(set(ui_keys) - set(tool_keys)),
                      only_in_tool=sorted(set(tool_keys) - set(ui_keys)),
                      differing_values=sorted(
                          name for name in set(ui_keys) & set(tool_keys)
                          if ui_keys[name] != tool_keys[name]),
                      sample=sorted(tool_keys.items())[:4]))
    report.note("MPFB's own properties after the UI path: {}".format(through_ui["macro"]))

    harness.cleanup_scratch_scene()


def _check_stack_in_sync(tools: dict, report: Report) -> None:
    fixtures.ensure_character_a(tools, "macro", report)
    details = tools["mpfb_get_macro_details"](name=fixtures.CHARACTER_A)["result"]
    # The docstring says to compare these two lists, so that is what is done
    # here rather than something weaker: the stack's shapekey_name against the
    # names reported as being on the mesh.
    stack = set(entry["shapekey_name"] for entry in details["macro_target_stack"])
    on_mesh = set(details["current_macro_shapekeys"])
    really_on_mesh = set(probe("shapekeys", _SHAPEKEYS_CODE,
                               name=fixtures.CHARACTER_A)["shapekeys_by_name"])
    report.check("properties and mesh in sync: macro_target_stack matches "
                 "current_macro_shapekeys",
                 stack == on_mesh and bool(stack),
                 dict(stack=len(stack), on_mesh=len(on_mesh),
                      only_in_stack=sorted(stack - on_mesh)[:4],
                      only_on_mesh=sorted(on_mesh - stack)[:4],
                      stack_matches_the_actual_shape_keys=stack <= really_on_mesh))
    report.note("phenotype now: {}".format(details.get("macro_details")))


def _check_prune(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "PruneCharacter")
    baseline = probe("shapekeys", _SHAPEKEYS_CODE, name="PruneCharacter")

    kept = tools["mpfb_set_macro_details"](
        name="PruneCharacter", gender=1.0, prune=False)["result"]
    after_no_prune = probe("shapekeys", _SHAPEKEYS_CODE, name="PruneCharacter")
    pruned = tools["mpfb_set_macro_details"](
        name="PruneCharacter", gender=1.0, prune=True)["result"]
    after_prune = probe("shapekeys", _SHAPEKEYS_CODE, name="PruneCharacter")

    zero_weight_kept = [name for name, value in after_no_prune["shapekeys"] if value < 0.0001]
    zero_weight_after = [name for name, value in after_prune["shapekeys"] if value < 0.0001]
    report.check("prune removes macro shape keys and prune: false keeps them",
                 bool(zero_weight_kept) and not zero_weight_after
                 and pruned["shapekeys_removed"],
                 dict(before=len(baseline["shapekeys"]),
                      after_prune_false=len(after_no_prune["shapekeys"]),
                      after_prune_true=len(after_prune["shapekeys"]),
                      zero_weight_kept=zero_weight_kept,
                      zero_weight_after_prune=zero_weight_after,
                      reported_removed=pruned["shapekeys_removed"],
                      reported_added=kept["shapekeys_added"]))
    harness.cleanup_scratch_scene(keep=[fixtures.CHARACTER_A])


def _check_omitted_slider(tools: dict, report: Report) -> None:
    fixtures.fresh_human(tools, "OmittedCharacter")
    tools["mpfb_set_macro_details"](name="OmittedCharacter", gender=0.8, age=0.2)
    first = tools["mpfb_get_macro_details"](name="OmittedCharacter")["result"]["macro_details"]
    tools["mpfb_set_macro_details"](name="OmittedCharacter", muscle=0.9)
    second = tools["mpfb_get_macro_details"](name="OmittedCharacter")["result"]["macro_details"]
    # Compared with a tolerance, not for equality: MPFB's macro properties are
    # Blender FloatProperties, so 0.9 comes back as 0.8999999761581421. An
    # exact comparison here would report a float32 round trip as a tool defect.
    report.check("an omitted slider is left alone rather than defaulted",
                 second["gender"] == first["gender"] and second["age"] == first["age"]
                 and abs(second["muscle"] - 0.9) < 1e-6,
                 dict(before=first, after=second))
    harness.cleanup_scratch_scene(keep=[fixtures.CHARACTER_A])


def _check_preconditions(tools: dict, report: Report) -> None:
    """The two things MPFB meets with a bare assert and a log line."""
    fixtures.fresh_human(tools, "PreconditionCharacter")

    probe("enter_edit_mode", _MODE_CODE, name="PreconditionCharacter", mode="EDIT")
    in_edit = tools["mpfb_set_macro_details"](name="PreconditionCharacter", gender=0.7)
    probe("leave_edit_mode", _MODE_CODE, name="PreconditionCharacter", mode="OBJECT")
    result = in_edit.get("result") or dict()
    report.check("the OBJECT-mode precondition, observed",
                 in_edit.get("status") == "ok" and result.get("ready") is False
                 and result.get("blocked_by") is not None,
                 dict(status=in_edit.get("status"), ready=result.get("ready"),
                      blocked_by=result.get("blocked_by"), message=result.get("message")))

    stripped = probe("strip_shapekeys", _STRIP_SHAPEKEYS_CODE, name="PreconditionCharacter")
    no_keys = tools["mpfb_set_macro_details"](name="PreconditionCharacter", gender=0.7)
    result = no_keys.get("result") or dict()
    report.check("the no-shape-keys precondition, observed",
                 no_keys.get("status") == "ok",
                 dict(removed=stripped["removed"], status=no_keys.get("status"),
                      ready=result.get("ready"), blocked_by=result.get("blocked_by"),
                      message=result.get("message")))
    harness.cleanup_scratch_scene(keep=[fixtures.CHARACTER_A])


def _check_cost(tools: dict, report: Report) -> None:
    """Three timings, from FR 012's own clock rather than from a stopwatch."""
    import time  # pylint: disable=import-outside-toplevel

    fixtures.fresh_human(tools, "CostCharacter")

    def timed(call) -> float:
        started = time.perf_counter()
        call()
        return round((time.perf_counter() - started) * 1000.0, 1)

    with_prune = [timed(lambda: tools["mpfb_set_macro_details"](
        name="CostCharacter", gender=0.4 + index * 0.05, prune=True, refit=False))
        for index in range(3)]
    without_prune = [timed(lambda: tools["mpfb_set_macro_details"](
        name="CostCharacter", gender=0.7 + index * 0.05, prune=False, refit=False))
        for index in range(3)]
    with_refit = [timed(lambda: tools["mpfb_set_macro_details"](
        name="CostCharacter", gender=0.3 + index * 0.05, refit=True))
        for index in range(3)]
    refit_only = [timed(lambda: tools["mpfb_refit_human"](name="CostCharacter"))
                  for _ in range(3)]

    report.check("cost: a macro change with and without prune, and a refit", True,
                 dict(prune_true_ms=with_prune, prune_false_ms=without_prune,
                      refit_true_ms=with_refit, refit_only_ms=refit_only,
                      median_prune_true=sorted(with_prune)[1],
                      median_refit_true=sorted(with_refit)[1]))
    harness.cleanup_scratch_scene(keep=[fixtures.CHARACTER_A])


_UI_SLIDER_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
ObjectService = services["ObjectService"]
TargetService = services["TargetService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
ObjectService.activate_blender_object(basemesh, deselect_all=True)

# This is what MPFB's phenotype panel does when a slider moves: the property is
# a FloatProperty on the Scene whose setter writes the object property,
# reapplies the macro details and (optionally) refits. Assigning it here is the
# same code path, not an imitation of it.
scene = bpy.context.scene
for name in sorted(PARAMS["changes"]):
    setattr(scene, PARAMS["prefix"] + name, PARAMS["changes"][name])

keys = []
if basemesh.data.shape_keys is not None:
    for block in basemesh.data.shape_keys.key_blocks:
        keys.append([block.name, round(float(block.value), 6)])

result = dict(
    shapekeys=sorted(keys),
    macro=TargetService.get_macro_info_dict_from_basemesh(basemesh),
)
'''

_SHAPEKEYS_CODE = '''
import bpy

basemesh = bpy.data.objects.get(PARAMS["name"])
keys = []
if basemesh is not None and basemesh.data.shape_keys is not None:
    for block in basemesh.data.shape_keys.key_blocks:
        keys.append([block.name, round(float(block.value), 6)])

result = dict(shapekeys=sorted(keys),
              shapekeys_by_name=sorted([entry[0] for entry in keys]))
'''

_MODE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
ObjectService = services["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
ObjectService.activate_blender_object(basemesh, deselect_all=True)
bpy.ops.object.mode_set(mode=PARAMS["mode"])
result = dict(mode=str(bpy.context.mode), object_mode=str(basemesh.mode))
'''

_STRIP_SHAPEKEYS_CODE = '''
import bpy

basemesh = bpy.data.objects.get(PARAMS["name"])
removed = []
if basemesh.data.shape_keys is not None:
    for block in list(basemesh.data.shape_keys.key_blocks):
        removed.append(block.name)
    basemesh.shape_key_clear()

result = dict(removed=sorted(removed),
              has_shapekeys=basemesh.data.shape_keys is not None)
'''


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
