#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 032's live check: fourteen tools, two transports, one Blender, compared.

FR 030 compared one tool and FR 031 compared nine. All ten were **read-only**,
and that is what makes this check a different shape rather than a longer one:
**a mutating tool cannot be run twice against the same state.** Calling one on
each backend and comparing is not a comparison if the first call changed what
the second one sees.

So the method is *same starting state, one call each, compare the answer **and**
the scene*:

1. empty the scratch scene and purge the orphaned datablocks it left, so that
   object and material names come out the same rather than uniquified;
2. build a named starting state - a character, a rigged character, a dressed
   one - through the tools, over a **fixed** backend, as instrument rather than
   as subject;
3. call the tool under test on the generated path; snapshot the scene;
4. do 1-3 again on the bridge;
5. compare the two answers field by field, and the two scene snapshots.

Step 1 is what makes step 5 mean anything. Without the purge, the second run's
character is ``Human.001`` and every comparison fails for a reason that has
nothing to do with either transport.

## Expected differences, declared in advance

FR 032's requirement 8 asks for these to be named rather than explained
afterwards. There are four, and each is normalised by
:data:`_VOLATILE` or by the comparison's own shape:

- **The envelope, not the result.** A bridge answer carries ``protocol_version``
  and ``command`` and a generated one does not. Only ``result`` is compared,
  exactly as in FR 031.
- **Wall-clock timestamps.** ``mpfb_save_preset`` reports ``modified`` from
  ``os.stat`` on a file each run writes afresh, so the two differ by however
  long the run took. Compared for presence and type, not value.
- **``mpfb_list_urls``' handshake case.** A protocol mismatch answers with an
  error envelope on the bridge where the generated path would have answered
  with vendored URLs - which is
  [a decision, not a defect](../../../src/mpfbmcp/tools/list_urls.py). It does not
  arise in an ordinary run, where the two ends agree about the version, and it
  is checked in ``tests/test_list_urls.py`` rather than here.
- **MPFB's own caches**, as FR 031 found for ``mpfb_list_asset_materials``. The
  starting state is rebuilt between the two calls, so a cache MPFB warms on the
  first run is warm for the second - which shows up as a *difference* rather
  than hiding one, since the generated path always goes first.

## The vacuity guard

``--self-compare`` runs both sides on the generated path, and the run is then
expected to **FAIL**: a comparison that cannot tell two runs of one backend from
two backends proves nothing. FR 031 established the shape and this keeps it.

## Running

One Blender with **MPFB, blender_mcp and the MPFB Bridge** all enabled, with
both socket servers started. That is the transitional arrangement
verification/README.md describes, and it goes away in FR 033.

    PYTHONPATH=. python3 feature-requests/032-creation-and-modification-migrated/check_creation_migration.py
    PYTHONPATH=. python3 .../check_creation_migration.py --self-compare

It builds in a scene of its own, writes one preset under a name of its own, and
deletes both on the way out. The ``.blend`` is never saved.
"""

from __future__ import annotations

__all__ = ("main",)

import argparse
import json
import socket
import sys

from mpfbmcp import backend, bridge_connection, build_server
from mpfbmcp.connection import get_connection_params, send_code

SCRATCH_SCENE = "MPFBMCP_CREATION_CHECK"

# A preset name of this check's own, so nothing a developer saved is touched.
# It is deleted on the way out whatever happens.
SCRATCH_PRESET = "mpfbmcp-creation-check"

_FAILURES: list[str] = []
_PASSES: list[str] = []
_SKIPPED: list[str] = []

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
    print("  FAIL  {:s}\n          {:s}".format(label, str(detail)[:900]))
    return False


def skip(label: str, why: str) -> None:
    """Not a pass and not a failure: this install cannot answer the question."""
    _SKIPPED.append(label)
    print("  SKIP  {:s}\n          {:s}".format(label, why[:300]))


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
        "# --- payload: creationcheck_{}.py ---\n".format(label),
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

# Emptying the scene is not enough. Blender keeps an unused mesh, material or
# armature datablock around until the file is reloaded, and the *next* character
# built in the same session is then `Human.001` with a material called
# `Human.001.body` - so every name in the second run's answer differs from the
# first's for a reason that has nothing to do with either transport. Purging the
# orphans is what makes "same starting state" true of the names as well as of
# the objects.
_RESET_CODE = '''
import bpy

scene = bpy.data.scenes.get(PARAMS["scene"])
removed_objects = []
if scene is not None:
    for blender_object in list(scene.objects):
        removed_objects.append(blender_object.name)
        bpy.data.objects.remove(blender_object, do_unlink=True)

purged = 0

# Rigify's widget objects are held by a ``WGTS_<rig name>`` collection that is
# linked to **no scene**, so emptying the scratch scene cannot reach them and
# they never fall to zero users. Left behind they are not merely untidy: the
# next generation *appends* into the existing collection rather than making a
# new one, so `verification/`'s own cleanup - which is scene-scoped - then
# misses its widgets too and its "the run put back everything it made" check
# fails for a reason that belongs to this script. Found exactly that way.
for collection in list(bpy.data.collections):
    if collection.name.startswith("WGTS_"):
        for widget in list(collection.objects):
            bpy.data.objects.remove(widget, do_unlink=True)
            purged += 1
        bpy.data.collections.remove(collection)
        purged += 1

# Repeated, because removing a mesh can orphan the material it referenced.
for _pass in range(4):
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures,
                       bpy.data.materials, bpy.data.node_groups, bpy.data.actions,
                       bpy.data.shape_keys, bpy.data.images):
        for datablock in list(collection):
            if datablock.users == 0:
                collection.remove(datablock)
                purged += 1

result = dict(removed_objects=sorted(removed_objects), purged=purged)
'''

_RESTORE_CODE = '''
import bpy

scene = bpy.data.scenes.get(PARAMS["scene"])
removed_objects = []
if scene is not None:
    for blender_object in list(scene.objects):
        removed_objects.append(blender_object.name)
        bpy.data.objects.remove(blender_object, do_unlink=True)

# The widget collections too, for the reason _RESET_CODE gives: they are linked
# to no scene, so nothing else here would reach them.
for collection in list(bpy.data.collections):
    if collection.name.startswith("WGTS_"):
        for widget in list(collection.objects):
            removed_objects.append(widget.name)
            bpy.data.objects.remove(widget, do_unlink=True)
        bpy.data.collections.remove(collection)

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

# What "the scene" means for the purposes of a comparison: everything a mutating
# tool could have changed and a caller could see. Deliberately more than the
# tools report - a tool that reported the right answer and left the scene in a
# different state would pass an answer-only comparison.
_SNAPSHOT_CODE = '''
import bpy

scene = bpy.data.scenes.get(PARAMS["scene"])
objects = []
if scene is not None:
    for blender_object in sorted(scene.objects, key=lambda one: one.name):
        shapekeys = []
        keys = getattr(getattr(blender_object, "data", None), "shape_keys", None)
        if keys is not None and keys.key_blocks is not None:
            shapekeys = [[str(block.name), round(float(block.value), 6)]
                         for block in keys.key_blocks]
        objects.append(dict(
            name=blender_object.name,
            type=blender_object.type,
            parent=None if blender_object.parent is None else blender_object.parent.name,
            location=[round(float(value), 5) for value in blender_object.location],
            hide_viewport=bool(blender_object.hide_viewport),
            modifiers=[[str(modifier.name), str(modifier.type),
                        str(getattr(modifier, "vertex_group", "") or "")]
                       for modifier in (blender_object.modifiers or [])],
            vertex_groups=sorted(str(group.name)
                                 for group in (blender_object.vertex_groups or [])),
            materials=[None if slot.material is None else str(slot.material.name)
                       for slot in (blender_object.material_slots or [])],
            shapekeys=shapekeys,
        ))

active = bpy.context.view_layer.objects.active
result = dict(
    objects=objects,
    object_count=len(objects),
    active=None if active is None else active.name,
    selected=sorted(one.name for one in objects and scene.objects if one.select_get()),
)
'''

_DELETE_PRESET_CODE = '''
import os, sys

result = dict(removed=False, path=None)
candidates = sorted(name for name in list(sys.modules) if name.endswith("mpfb"))
if candidates:
    contextual = getattr(sys.modules[candidates[0]], "MPFB_CONTEXTUAL_INFORMATION", None)
    if isinstance(contextual, dict):
        services = contextual.get("SERVICES") or dict()
        location_service = services.get("LocationService")
        if location_service is not None:
            path = str(location_service.get_user_config(
                "human." + PARAMS["name"] + ".json"))
            result["path"] = path
            if os.path.isfile(path):
                os.remove(path)
                result["removed"] = True
'''


def with_backend(name: str, call, /, *arguments, **keywords):
    """Run one callable with the backend preference set, and put it back.

    Both parameters are **positional-only**, and that slash is load-bearing:
    several of these tools take an argument called ``name``, and without it
    ``with_backend(..., name="Human")`` is a TypeError rather than a call.
    """
    import os  # pylint: disable=import-outside-toplevel

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
    """Which fields disagree, rather than that some field does."""
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


# Per tool, the answer fields that cannot be equal between two runs and why.
# **Declared in advance**, which is FR 032's requirement 8: a difference
# explained afterwards is a difference that was allowed to decide the result.
# Each is compared for presence and type rather than for value.
_VOLATILE: dict[str, tuple[tuple[str, str], ...]] = {
    "mpfb_save_preset": (
        ("modified", "os.stat's mtime on a file each run writes afresh"),
    ),
}

# **This list is shorter than the first draft of it, and that is the finding.**
# It began with ``previous_file`` and ``contents`` on it too, on the reasoning
# that the second run would inevitably see the file the first one wrote. It
# would have - and declaring that volatile would have been normalising away a
# fault in the harness rather than an expected difference between transports.
# What the two runs actually needed was the same *starting state*, the preset
# included, which is what :func:`reset` now provides. Only the mtime is left,
# and it is volatile for a reason no arrangement can remove: the two runs happen
# at different times.


def _without_volatile(result: object, tool_name: str) -> object:
    """The answer with its declared-volatile fields replaced by their types."""
    if not isinstance(result, dict):
        return result
    trimmed = dict(result)
    for key, _why in _VOLATILE.get(tool_name, ()):
        if key in trimmed:
            trimmed[key] = "<volatile:{:s}>".format(type(trimmed[key]).__name__)
    return trimmed


def _volatile_still_present(left: dict, right: dict, tool_name: str) -> str:
    """A volatile field must still be *there*, and of the same type, on both sides."""
    problems = []
    for key, _why in _VOLATILE.get(tool_name, ()):
        if (key in left) != (key in right):
            problems.append("{:s} is on one side only".format(key))
        elif key in left and type(left[key]) is not type(right[key]):
            problems.append("{:s} differs in type: {!r} against {!r}".format(
                key, type(left[key]).__name__, type(right[key]).__name__))
    return "; ".join(problems)


def _summarise(result: object) -> str:
    """A line naming the fields most worth eyeballing, whatever tool answered."""
    if not isinstance(result, dict):
        return repr(result)[:120]
    interesting = ("performed", "found", "ready", "blocked_by", "added", "removed",
                   "applied", "saved", "created", "generated", "recalculated",
                   "refit_performed", "object_name", "count")
    parts = ["{:s}={!r}".format(key, result[key]) for key in interesting if key in result]
    return " ".join(parts) or "(no summary fields)"


# ---------------------------------------------------------------------------
# Starting states
#
# A recipe is built through the tools, over a **fixed** backend, because it is
# instrument rather than subject: what is under test is the one call made after
# it, and a recipe that ran on whichever backend was being compared would make
# the starting states differ rather than the answers.
# ---------------------------------------------------------------------------

_RECIPE_BACKEND = backend.BACKEND_BLENDER_MCP


class Context:
    """What the recipes need, and what they leave behind for a case to name."""

    def __init__(self, all_tools: dict) -> None:
        self.tools = all_tools
        self.clothes_asset: dict | None = None
        self.skin_asset: dict | None = None
        self.rigify_available = False
        self.equipped_name: str | None = None
        self.target_case: dict | None = None


def _tool(context: Context, tool_name: str, /, **keywords):
    """One instrument call, on the fixed recipe backend.

    ``tool_name`` is **positional-only**, and that slash is load-bearing for the
    reason ``with_backend``'s is: several of these tools take an argument called
    ``name``, and without it ``_tool(context, "mpfb_save_preset", name=...)`` is
    a TypeError rather than a call.
    """
    return with_backend(_RECIPE_BACKEND, context.tools[tool_name], **keywords)


def reset(context: Context) -> None:
    """Empty the scratch scene, purge what it orphaned, and delete the preset.

    **The preset is part of the starting state**, which the first run of this
    check discovered the hard way: with the file left behind, the second run's
    ``mpfb_save_preset`` answer says it replaced one and the first's says it did
    not, and the comparison reports a difference that belongs to the harness
    rather than to either transport. Deleting it here is the file's equivalent
    of purging the orphaned datablocks - "same starting state" has to be true of
    the disk as well as of the scene.
    """
    probe("reset", _RESET_CODE, scene=SCRATCH_SCENE)
    probe("delete preset", _DELETE_PRESET_CODE, name=SCRATCH_PRESET)


def recipe_none(context: Context) -> bool:
    """An empty scene."""
    return True


def recipe_plain(context: Context) -> bool:
    """One character, built with default arguments so it is the same every time."""
    answer = _tool(context, "mpfb_create_human")
    return answer.get("status") == "ok"


def recipe_rigged(context: Context) -> bool:
    """A character carrying MPFB's standard rig."""
    if not recipe_plain(context):
        return False
    answer = _tool(context, "mpfb_add_rig", identifier="default")
    return answer.get("status") == "ok" and answer["result"].get("performed") is True


def recipe_metarig(context: Context) -> bool:
    """A character carrying a Rigify meta rig, ready to be generated from."""
    if not context.rigify_available:
        return False
    if not recipe_plain(context):
        return False
    answer = _tool(context, "mpfb_add_rig", identifier="rigify.human")
    return answer.get("status") == "ok" and answer["result"].get("performed") is True


def recipe_dressed(context: Context) -> bool:
    """A character wearing one MHCLO asset this install actually ships."""
    if context.clothes_asset is None:
        return False
    if not recipe_plain(context):
        return False
    answer = _tool(context, "mpfb_add_asset",
                   path=context.clothes_asset["path"],
                   asset_type=context.clothes_asset["object_type"])
    if answer.get("status") != "ok" or not answer["result"].get("performed"):
        return False
    context.equipped_name = answer["result"].get("asset_object_name")
    return context.equipped_name is not None


def recipe_saved_preset(context: Context) -> bool:
    """A character, and a preset of it under this check's own name."""
    if not recipe_plain(context):
        return False
    answer = _tool(context, "mpfb_save_preset", name=SCRATCH_PRESET, overwrite=True)
    return answer.get("status") == "ok" and answer["result"].get("performed") is True


_RECIPES = {
    "none": recipe_none,
    "plain": recipe_plain,
    "rigged": recipe_rigged,
    "metarig": recipe_metarig,
    "dressed": recipe_dressed,
    "saved_preset": recipe_saved_preset,
}


# ---------------------------------------------------------------------------
# The cases
#
# Each is (tool, recipe, label, keywords-or-callable, compares_scene). The
# keywords may be a callable taking the Context, for the cases whose argument is
# only knowable after the recipe has run - the name of the asset it equipped,
# or a category this install actually ships.
# ---------------------------------------------------------------------------

def _equipped(context: Context) -> dict:
    return {"name": context.equipped_name}


def _target_modifier(context: Context) -> dict:
    case = context.target_case
    entry = {"section": case["section"], "category": case["category"], "value": 0.4}
    if case["sided"]:
        entry["side"] = "left"
    return {"modifiers": [entry]}


def _skin_path(context: Context) -> dict:
    return {"path": context.skin_asset["path"]}


def _clothes_path(context: Context) -> dict:
    return {"path": context.clothes_asset["path"],
            "asset_type": context.clothes_asset["object_type"]}


_CASES: tuple[tuple[str, str, str, object], ...] = (
    # Batch A.
    ("mpfb_create_human", "none", "defaults", {}),
    ("mpfb_create_human", "none", "a phenotype", {"gender": 1.0, "age": 0.75}),
    ("mpfb_refit_human", "rigged", "a rigged character", {}),
    ("mpfb_refit_human", "none", "nothing to refit", {"name": "NoSuchObjectHere"}),
    # Batch B.
    ("mpfb_set_macro_details", "plain", "one slider", {"gender": 1.0}),
    ("mpfb_set_macro_details", "plain", "no slider named", {}),
    ("mpfb_set_macro_details", "none", "no subject", {"name": "NoSuchObjectHere"}),
    ("mpfb_set_targets", "plain", "one modifier", _target_modifier),
    ("mpfb_set_targets", "plain", "nothing named", {}),
    ("mpfb_set_targets", "plain", "an unknown category", {
        "modifiers": [{"section": "nose", "category": "no-such-category", "value": 0.1}]}),
    ("mpfb_symmetrize_targets", "plain", "a dry run", {
        "direction": "left_to_right", "dry_run": True}),
    ("mpfb_symmetrize_targets", "plain", "for real", {"direction": "left_to_right"}),
    ("mpfb_symmetrize_targets", "plain", "an unknown section", {
        "direction": "left_to_right", "section": "nostril"}),
    # Batch C.
    ("mpfb_add_rig", "plain", "the standard rig", {"identifier": "default"}),
    ("mpfb_add_rig", "plain", "no weights", {"identifier": "default",
                                             "import_weights": False}),
    ("mpfb_add_rig", "plain", "an unknown identifier", {"identifier": "no-such-rig"}),
    ("mpfb_add_rig", "rigged", "already rigged", {"identifier": "cmu_mb"}),
    ("mpfb_generate_rigify_rig", "metarig", "hide the meta rig", {}),
    ("mpfb_generate_rigify_rig", "metarig", "delete the meta rig",
     {"meta_rig_action": "delete"}),
    ("mpfb_generate_rigify_rig", "plain", "nothing to generate from", {}),
    ("mpfb_add_asset", "plain", "one garment", _clothes_path),
    ("mpfb_add_asset", "plain", "an unknown type", {
        "path": "/no/such/file.mhclo", "asset_type": "Trousers"}),
    ("mpfb_remove_asset", "dressed", "take it off again", _equipped),
    ("mpfb_remove_asset", "plain", "an unknown name", {"name": "NoSuchObjectHere"}),
    # Batch D.
    ("mpfb_set_skin", "plain", "a MakeSkin skin", _skin_path),
    ("mpfb_set_skin", "plain", "a path naming no file",
     {"path": "/no/such/skin.mhmat"}),
    # Refused on **this** side of the socket, before a transport is chosen, so
    # what it compares is that neither backend was spoken to. Kept as a case
    # rather than dropped: the seam's whole claim is that a tool validates
    # first, and a run that never exercised one would not be checking it.
    ("mpfb_set_skin", "plain", "no file for a type that needs one", {}),
    ("mpfb_set_asset_material", "dressed", "restore the default",
     lambda context: dict(_equipped(context), restore_default=True)),
    ("mpfb_set_asset_material", "plain", "a basemesh is refused",
     {"name": "Human", "path": "/no/such/file.mhmat"}),
    # Batch E.
    ("mpfb_save_preset", "plain", "write it", {"name": SCRATCH_PRESET, "overwrite": True}),
    ("mpfb_save_preset", "plain", "a name that is not a path",
     {"name": SCRATCH_PRESET, "subject": "NoSuchObjectHere"}),
    ("mpfb_create_human_from_preset", "saved_preset", "load it back",
     {"name": SCRATCH_PRESET}),
    ("mpfb_create_human_from_preset", "plain", "a preset that is not there",
     {"name": "mpfbmcp-no-such-preset"}),
    ("mpfb_list_urls", "none", "", {}),
)


def _arguments(context: Context, keywords: object) -> dict:
    return keywords(context) if callable(keywords) else dict(keywords)


def compare_one(context: Context, right_backend: str, tool_name: str,
                recipe_name: str, case_label: str, keywords: object) -> None:
    """One case: two starting states, two calls, two scenes, one comparison."""
    label = "{:s}{:s}".format(tool_name, ", " + case_label if case_label else "")
    recipe = _RECIPES[recipe_name]

    answers = {}
    scenes = {}
    for side, name in (("generated", backend.BACKEND_BLENDER_MCP), ("right", right_backend)):
        reset(context)
        if not recipe(context):
            skip(label, "the {!r} starting state could not be built on this install".format(
                recipe_name))
            return
        try:
            arguments = _arguments(context, keywords)
        except (TypeError, KeyError):
            skip(label, "this install does not offer what the case needs")
            return
        try:
            answers[side] = with_backend(name, context.tools[tool_name], **arguments)
        except ValueError as refusal:
            # Local validation, which happens **before** a transport is chosen.
            # Recorded rather than allowed to end the run, because "both sides
            # refused the same way" is a real claim about the seam: an argument
            # this package rejects must never reach either backend.
            answers[side] = {"status": "locally_refused", "message": str(refusal)}
        scenes[side] = probe("snapshot", _SNAPSHOT_CODE, scene=SCRATCH_SCENE)
        _BACKENDS_COMPARED.add(name)

    left, right = answers["generated"], answers["right"]
    if left.get("status") == "locally_refused" or right.get("status") == "locally_refused":
        check("{:s}: refused locally on both sides, before a transport was chosen".format(label),
              left == right, (left, right))
        check("{:s}: the two scenes are identical".format(label),
              scenes["generated"] == scenes["right"],
              _difference(scenes["generated"], scenes["right"]))
        return

    if not check("{:s}: both answered with an ok envelope".format(label),
                 left.get("status") == "ok" and right.get("status") == "ok", (left, right)):
        return

    left_result, right_result = left["result"], right["result"]
    problems = _volatile_still_present(left_result, right_result, tool_name)
    if problems:
        check("{:s}: the declared-volatile fields are on both sides".format(label),
              False, problems)

    identical = check(
        "{:s}: the two answers are identical".format(label),
        _without_volatile(left_result, tool_name) == _without_volatile(right_result, tool_name),
        _difference(_without_volatile(left_result, tool_name),
                    _without_volatile(right_result, tool_name)))

    # The half no read-only check ever needed. An answer can be right about a
    # scene the tool left in a different state, and for a *mutating* tool that
    # is the failure worth catching.
    check("{:s}: the two scenes are identical".format(label),
          scenes["generated"] == scenes["right"],
          _difference(scenes["generated"], scenes["right"]))

    if identical:
        print("       {:s}".format(_summarise(left_result)))


def discover(context: Context) -> None:
    """What this install can actually be asked, decided once and reported.

    A case that names an asset or a target category this Blender does not ship
    is a **skip with a reason**, not a failure: the comparison is about two
    transports, and neither of them is responsible for what is installed.
    """
    reset(context)

    status = _tool(context, "mpfb_get_status")
    context.rigify_available = bool(
        status.get("status") == "ok" and status["result"].get("rigify_available"))

    clothes = _tool(context, "mpfb_list_assets", asset_subdir="clothes", limit=1)
    if clothes.get("status") == "ok" and clothes["result"].get("assets"):
        context.clothes_asset = clothes["result"]["assets"][0]

    skins = _tool(context, "mpfb_list_assets", asset_subdir="skins", limit=1)
    if skins.get("status") == "ok" and skins["result"].get("assets"):
        context.skin_asset = skins["result"]["assets"][0]

    # One real modeling category, taken from the catalogue rather than named
    # here: which sections a Blender ships depends on its target packs. The
    # section is the one that was asked for, because `categories` entries do not
    # repeat it - the catalogue is already scoped to a section by then.
    for section in ("nose", "chin", "ears"):
        targets = _tool(context, "mpfb_list_targets", section=section, limit=5)
        result = targets.get("result") or {}
        if targets.get("status") != "ok" or not result.get("section_recognized"):
            continue
        for entry in result.get("categories") or []:
            if entry.get("name"):
                context.target_case = dict(
                    section=section, category=entry["name"],
                    sided=bool(entry.get("has_left_and_right")))
                break
        if context.target_case is not None:
            break

    print("This install offers: rigify={!r} clothes={!r} skins={!r} target={!r}".format(
        context.rigify_available,
        None if context.clothes_asset is None else context.clothes_asset.get("name"),
        None if context.skin_asset is None else context.skin_asset.get("name"),
        None if context.target_case is None else context.target_case.get("category")))


def check_every_payload_has_a_command() -> None:
    """FR 032's finish line, asserted rather than taken on trust.

    FR 033 reads exactly this as its own precondition, and
    ``mpfb_list_docs`` is the one legitimate exception: it has no payload
    because it never crosses the socket at all.
    """
    from mpfbmcp import codegen  # pylint: disable=import-outside-toplevel

    payloads = set(codegen.payload_names())
    unmigrated = sorted(payloads - set(backend.MIGRATED_COMMANDS))
    check("every payload has a bridge command", not unmigrated, unmigrated)
    check("the table names twenty-four commands, which is every tool that crosses the socket",
          len(backend.MIGRATED_COMMANDS) == 24, sorted(backend.MIGRATED_COMMANDS))

    server = build_server()
    registered = {tool.name for tool in server._tool_manager.list_tools()}  # noqa: SLF001
    check("twenty-five tools are registered and exactly one of them has no payload",
          len(registered) == 25 and len(payloads) == 24, sorted(registered))


def _report() -> int:
    print("\n{:d} passed, {:d} failed, {:d} skipped".format(
        len(_PASSES), len(_FAILURES), len(_SKIPPED)))
    for failure in _FAILURES:
        print("  failed: {:s}".format(failure))
    for entry in _SKIPPED:
        print("  skipped: {:s}".format(entry))
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
        "--only", action="append", default=None,
        help="Compare only cases whose tool name contains this. Repeatable.")
    parser.add_argument("--keep", action="store_true",
                        help="Leave the scratch scene, its contents and the scratch preset.")
    arguments = parser.parse_args(argv)

    all_tools = tools()
    bridge_host, bridge_port = bridge_connection.get_connection_params()
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
    print("Creation migration check: blender_mcp at {:s}:{:d}, bridge at {:s}:{:d}".format(
        addon_host, addon_port, bridge_host, bridge_port))
    if arguments.self_compare:
        print("--self-compare: both sides on the generated path, and this run should FAIL")

    print("\nthe migration's own finish line")
    check_every_payload_has_a_command()

    scene = probe("scene", _SCENE_CODE, scene=SCRATCH_SCENE)
    print("\nWorking in scene {!r} (was {!r})".format(scene["scene"], scene["previous"]))

    context = Context(all_tools)
    try:
        discover(context)

        cases = _CASES
        if arguments.only:
            cases = tuple(case for case in _CASES
                          if any(fragment in case[0] for fragment in arguments.only))
        print("\nthe two paths, one call each from the same starting state "
              "({:d} cases)".format(len(cases)))
        for tool_name, recipe_name, case_label, keywords in cases:
            compare_one(context, right_backend, tool_name, recipe_name, case_label, keywords)
    finally:
        probe("delete preset", _DELETE_PRESET_CODE, name=SCRATCH_PRESET)
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

    check("the two sides really were two different backends", two_backends,
          sorted(_BACKENDS_COMPARED))
    return _report()


if __name__ == "__main__":
    sys.exit(main())
