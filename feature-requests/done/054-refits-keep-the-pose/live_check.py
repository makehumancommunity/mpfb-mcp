# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 054 against a real install: a dressed, posed, excluded character through a body change.

The request's own check, through the real tool callables over a real socket against a headless Blender,
on the developer's real assets. One generated Rigify character wears a dress and ``ponytail01``, whose
sub-rig is what makes this a hard case, and stands in a collection of its own beside two more characters
in theirs. It is posed, excluded, and has its body changed by a call that refits. Then:

- the controls and every switch hold the values they held, to the digit, and the hand has moved, because
  the body did;
- the collection ends excluded, with a bystander selected and active exactly as before;
- ``keep_pose: false`` resets, and ``restore_with`` puts it back;
- a sub-rig's own pose is not touched by a refit, which is why ``shared/refit_pose.py`` does not read it;
- a mesh hidden with ``hide_set()`` loses that to the exclude itself, with no tool involved (FR 12);
- what all this costs beside a refit on this character, against the request's 23 ms and 550 ms.

**Six commands the bridge does not have**, added to the running table in this process only, as FR 051's
check adds its own: the closed vocabulary is what the add-on ships. **Nothing of the user's is written**:
the scene is never saved, and the two renders land in ``renders/`` beside this file, and are kept.

It needs ``mpfb_bridge`` enabled in the Blender it is pointed at (``local_environment.md``)::

    BLENDER=/path/to/blender python3 feature-requests/054-refits-keep-the-pose/live_check.py
"""

from __future__ import annotations

__all__ = ()

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mpfbmcp import backend
from mpfbmcp import build_server

BLENDER = os.environ.get("BLENDER", shutil.which("blender") or "blender")
HERE = Path(__file__).resolve().parent
RENDERS = HERE / "renders"

DRESS = "aethelraed_flapper_dress/aethelraed_flapper_dress.mhclo"
PONYTAIL = "ponytail01/ponytail01.mhclo"
SKIN = "blindsaypatten_uniform_skin_texture/blindsaypatten_uniform_skin_texture.mhmat"
FK_BONE = "upper_arm_fk.L"
SWITCH_BONE = "upper_arm_parent.L"
AXIS = {"forward": 1.0, "left": 0.0, "up": 0.0}

BEFORE_BRIDGE = """
import importlib, math, os, sys, time
import bpy
from mathutils import Vector

RENDERS = {renders!r}

bridge = next(name[:-len(".commands.table")] for name in sys.modules
              if name.endswith("mpfb_bridge.commands.table"))
table = sys.modules[bridge + ".commands.table"]
validation = sys.modules[bridge + ".validation"]
view_layer = importlib.import_module(bridge + ".shared.view_layer")
refit_pose = importlib.import_module(bridge + ".shared.refit_pose")
pose_controls = importlib.import_module(bridge + ".shared.pose_controls")


def _gather(params, resolution):
    "Put a character's family in a new collection of its own, and move it aside."
    body = bpy.data.objects[params["body"]]
    collection = bpy.data.collections.new(params["collection"])
    bpy.context.scene.collection.children.link(collection)
    family = view_layer.family_of(resolution.services, body)
    for blender_object in family:
        for owner in list(blender_object.users_collection):
            owner.objects.unlink(blender_object)
        collection.objects.link(blender_object)
    return dict(family=sorted(blender_object.name for blender_object in family))


def _layer(name):
    return bpy.context.view_layer.layer_collection.children[name]


def _exclude(params, resolution):
    _layer(params["collection"]).exclude = params["value"]
    bpy.context.view_layer.update()
    return dict(exclude=_layer(params["collection"]).exclude)


def _bystander(params, resolution):
    "Something selected and active outside every character."
    bystander = bpy.data.objects.new("Bystander", None)
    bpy.context.scene.collection.objects.link(bystander)
    for blender_object in bpy.context.view_layer.objects:
        blender_object.select_set(False)
    bystander.select_set(True)
    bpy.context.view_layer.objects.active = bystander
    return dict(name=bystander.name)


def _state(params, resolution):
    "The pose as the bones hold it, and the view layer as the user left it."
    view = bpy.context.view_layer
    view.update()
    rig = bpy.data.objects[params["rig"]]
    bones = rig.pose.bones
    active = view.objects.active
    exclude_flags = dict((child.name, child.exclude) for child in view.layer_collection.children)
    answer = dict(exclude=exclude_flags, active=None if active is None else active.name,
                  selected=sorted(item.name for item in view.objects if item.select_get()))
    if rig.name in view.objects or params.get("force_read", True):
        answer.update(
            switch=float(bones["upper_arm_parent.L"]["IK_FK"]),
            channels=dict((name, list(bones[name].rotation_quaternion))
                          for name in ("upper_arm_fk.L", "head")),
            hand=list(rig.matrix_world @ bones["DEF-hand.L"].tail))
    return answer


def _subrig_pose(params, resolution):
    "Hold a bone of a sub-rig off rest, or read it back."
    bone = bpy.data.objects[params["subrig"]].pose.bones[0]
    if params["write"]:
        bone.location = (0.01, 0.0, 0.0)
    return dict(bone=bone.name, location=list(bone.location))


def _hide_cycle(params, resolution):
    "hide_set, excluded and included, with no tool anywhere near it. FR 054's requirement 12."
    collection = bpy.data.collections.new("HideCycle")
    bpy.context.scene.collection.children.link(collection)
    item = bpy.data.objects.new("HideCycleMember", None)
    collection.objects.link(item)
    layer = _layer("HideCycle")
    results = []
    for _run in range(5):
        bpy.context.view_layer.update()
        item.hide_set(True)
        layer.exclude = True
        bpy.context.view_layer.update()
        layer.exclude = False
        bpy.context.view_layer.update()
        results.append(item.hide_get())
    bpy.data.objects.remove(item)
    bpy.data.collections.remove(collection)
    return dict(hidden_after_each=results)


def _timing(params, resolution):
    "What keeping a pose costs on this character, measured beside a bare refit."
    body = bpy.data.objects[params["body"]]
    rig, identified, _metarig = pose_controls.find_rig(resolution.services, body)
    started = time.perf_counter()
    before = refit_pose._read(rig)
    read = time.perf_counter() - started
    started = time.perf_counter()
    classification = pose_controls.classify(resolution.module.__name__, rig, identified)
    classify = time.perf_counter() - started
    started = time.perf_counter()
    refit_pose._limbs_now(rig, classification)
    limbs = time.perf_counter() - started
    started = time.perf_counter()
    resolution.services["HumanService"].refit(body)
    refit = time.perf_counter() - started
    started = time.perf_counter()
    after = refit_pose._read(rig)
    driven = refit_pose.pose_writing.driven_kinds(rig)
    differing, _gone = refit_pose._compared(before, after, driven)
    compare = time.perf_counter() - started
    started = time.perf_counter()
    refit_pose._put_back(rig, before, differing, driven)
    put_back = time.perf_counter() - started
    return dict(bones=len(before), read_ms=read * 1000, classify_ms=classify * 1000,
                limbs_ms=limbs * 1000, refit_ms=refit * 1000, compare_ms=compare * 1000,
                put_back_ms=put_back * 1000, differing=len(differing))


def _render(params, resolution):
    "One character from the front, on a plain ground, lit by one sun."
    scene = bpy.context.scene
    body = bpy.data.objects[params["body"]]
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.cycles.device = "CPU"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 800
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 85
    if scene.world is None:
        scene.world = bpy.data.worlds.new("LiveCheck")
    scene.world.color = (0.5, 0.5, 0.5)
    camera_data = bpy.data.cameras.new("LiveCheckCamera")
    camera = bpy.data.objects.new("LiveCheckCamera", camera_data)
    scene.collection.objects.link(camera)
    sun_data = bpy.data.lights.new("LiveCheckSun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("LiveCheckSun", sun_data)
    sun.rotation_euler = (math.radians(50.0), 0.0, math.radians(20.0))
    scene.collection.objects.link(sun)
    # The headless startup scene's cube stands where the character does, and is no part of this.
    startup_cube = bpy.data.objects.get("Cube")
    if startup_cube is not None:
        startup_cube.hide_render = True
    target = body.matrix_world.translation + Vector((0.0, 0.0, 0.95))
    camera.location = target + Vector((-3.2, -5.2, 0.4))
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    scene.render.filepath = os.path.join(RENDERS, params["file"])
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(camera)
    bpy.data.objects.remove(sun)
    bpy.data.cameras.remove(camera_data)
    bpy.data.lights.remove(sun_data)
    return dict(file=scene.render.filepath)


string = validation.TYPE_STRING
boolean = validation.TYPE_BOOLEAN
for name, handler, params in (
    ("live_check_gather", _gather, (validation.Param("body", string, required=True),
                                    validation.Param("collection", string, required=True))),
    ("live_check_exclude", _exclude, (validation.Param("collection", string, required=True),
                                      validation.Param("value", boolean, required=True))),
    ("live_check_bystander", _bystander, ()),
    ("live_check_state", _state, (validation.Param("rig", string, required=True),)),
    ("live_check_subrig_pose", _subrig_pose, (validation.Param("subrig", string, required=True),
                                              validation.Param("write", boolean, required=True))),
    ("live_check_hide_cycle", _hide_cycle, ()),
    ("live_check_timing", _timing, (validation.Param("body", string, required=True),)),
    ("live_check_render", _render, (validation.Param("body", string, required=True),
                                    validation.Param("file", string, required=True))),
):
    table.COMMANDS[name] = table.Command(name=name, handler=handler, params=params,
                                         requires_mpfb=True,
                                         summary="This check's own, in this process only.")
"""

_failures = []
_checks = 0


def check(what: str, passed: bool, observed: object = None) -> None:
    """One claim. Printed either way, so that the run is its own record."""
    global _checks  # pylint: disable=global-statement
    _checks += 1
    print("{:s} {:s}{:s}".format("ok  " if passed else "FAIL", what,
                                 "" if observed is None else "  [{!s}]".format(observed)), flush=True)
    if not passed:
        _failures.append(what)


class Blender:
    """A headless Blender with the bridge up on a port of its own, stopped on exit."""

    def __init__(self, before_bridge: Path, export_directory: Path) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        command = [BLENDER, "--background", "--python", str(before_bridge), "--command",
                   "mpfb_bridge", "--port", str(self.port), "--export-dir", str(export_directory)]
        self.process = subprocess.Popen(  # pylint: disable=consider-using-with
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def __enter__(self) -> "Blender":
        os.environ["MPFB_BRIDGE_PORT"] = str(self.port)
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return self
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("the bridge did not come up")

    def __exit__(self, *_exception: object) -> None:
        self.process.terminate()
        self.process.wait(timeout=30)


def answer(envelope: dict) -> dict:
    """The result of a call that must not have failed."""
    if envelope.get("status") != "ok":
        raise RuntimeError(str(envelope.get("traceback") or envelope)[-1500:])
    return envelope["result"]


def own(command: str, **params: object) -> dict:
    """One of this check's own commands."""
    return answer(backend.send(command, params=params))


def same(first: list, second: list, tolerance: float = 0.0) -> bool:
    """Whether two lists of numbers agree, exactly unless a tolerance is given."""
    return all(abs(a - b) <= tolerance for a, b in zip(first, second))


def build(tool: dict, collection: str, rig: str, dressed: bool) -> dict:
    """One character in a collection of its own, and what it wears."""
    body = answer(tool["mpfb_create_human"]())["basemesh_name"]
    rig_name = answer(tool["mpfb_add_rig"](name=body, identifier=rig))["rig_object_name"]
    worn = []
    if dressed:
        worn.append(answer(tool["mpfb_add_asset"](name=body, fragment=DRESS,
                                                  object_type="Clothes")))
        worn.append(answer(tool["mpfb_add_asset"](name=body, fragment=PONYTAIL,
                                                  object_type="Hair")))
    if rig.startswith("rigify."):
        rig_name = answer(tool["mpfb_generate_rigify_rig"](name=body))["rig_object_name"]
    answer(tool["mpfb_set_skin"](name=body, fragment=SKIN))
    own("live_check_gather", body=body, collection=collection)
    return dict(body=body, rig=rig_name, collection=collection, worn=worn)


def run(tool: dict) -> None:
    """The check, top to bottom. Each section says which requirement it holds to."""
    star = build(tool, "Star", "rigify.human_toes", dressed=True)
    second = build(tool, "Second", "default_no_toes", dressed=False)
    third = build(tool, "Third", "default_no_toes", dressed=False)
    subrig = next(item["subrig_object_name"] for item in star["worn"]
                  if item.get("subrig_object_name"))
    body, rig = star["body"], star["rig"]
    check("the dressed character has a sub-rig", bool(subrig), subrig)
    own("live_check_exclude", collection="Second", value=True)
    own("live_check_exclude", collection="Third", value=True)

    answer(tool["mpfb_set_pose_switches"](name=body, switches=[
        {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}]))
    answer(tool["mpfb_set_pose_bones"](name=body, bones=[
        {"bone": FK_BONE, "rotate_by": {"axis": AXIS, "degrees": 40.0}},
        {"bone": "head", "rotate_by": {"axis": AXIS, "degrees": 15.0}}]))
    own("live_check_subrig_pose", subrig=subrig, write=True)
    own("live_check_render", body=body, file="before_body_change.jpg")
    posed = own("live_check_state", rig=rig)

    # --- a refit of an unchanged body, at home
    refit = answer(tool["mpfb_refit_human"](name=body))
    check("FR 1, 5: a refit keeps the pose and says so", refit["pose_after_refit"] == "kept",
          refit.get("pose_kept_count"))
    now = own("live_check_state", rig=rig)
    check("FR 3: the hand has not moved, on the same body",
          same(now["hand"], posed["hand"], 1e-5), now["hand"])
    check("FR 3: IK_FK came back", now["switch"] == 1.0)
    subrig_pose = own("live_check_subrig_pose", subrig=subrig, write=False)
    check("a refit left the sub-rig's pose alone, so it is not read",
          same(subrig_pose["location"], [0.01, 0.0, 0.0], 1e-6), subrig_pose)

    # --- excluded, through a body change
    own("live_check_exclude", collection="Star", value=True)
    own("live_check_bystander")
    before = own("live_check_state", rig=rig)
    changed = answer(tool["mpfb_set_macro_details"](name=body, height=0.95, muscle=0.9, refit=True))
    after = own("live_check_state", rig=rig)
    check("FR 8: a refit reaches an excluded character", changed["refit_performed"] is True)
    check("FR 10: temporarily_included names it", changed["temporarily_included"] == ["Star"],
          changed["temporarily_included"])
    check("FR 10: the message says so", "'Star'" in changed["message"])
    check("FR 9: exactly what was excluded is excluded again", after["exclude"] == before["exclude"],
          after["exclude"])
    check("FR 12: the bystander stays selected and active",
          after["active"] == "Bystander" and after["selected"] == ["Bystander"], after["selected"])
    check("FR 5: the pose was kept", changed["pose_after_refit"] == "kept",
          changed.get("pose_kept_count"))
    check("FR 5: the limbs lists are there", "limbs_made_stretched" in changed
          and "limbs_made_unreachable" in changed,
          (changed.get("limbs_made_stretched"), changed.get("limbs_made_unreachable")))
    own("live_check_exclude", collection="Star", value=False)
    included = own("live_check_state", rig=rig)
    check("FR 3: every control holds the value it held",
          all(same(included["channels"][name], posed["channels"][name], 1e-6)
              for name in posed["channels"]), included["channels"])
    check("FR 3: the switch holds", included["switch"] == 1.0)
    moved = sum((a - b) ** 2 for a, b in zip(included["hand"], posed["hand"])) ** 0.5
    check("non-goal: the hand stands somewhere new, because the body changed", moved > 0.01,
          "{:.0f} mm".format(moved * 1000))
    own("live_check_render", body=body, file="after_body_change.jpg")

    # --- a garment on an excluded character
    own("live_check_exclude", collection="Second", value=True)
    worn = answer(tool["mpfb_add_asset"](name=second["body"], fragment=DRESS,
                                         object_type="Clothes"))
    check("FR 11: a new garment goes out with its character",
          {"object": worn["asset_object_name"], "collection": "Second"}
          in worn["objects_moved_to_collection"], worn["objects_moved_to_collection"])

    # --- keep_pose: false, and the way back
    reset = answer(tool["mpfb_refit_human"](name=body, keep_pose=False))
    now = own("live_check_state", rig=rig)
    check("FR 4, 5: keep_pose false is reset", reset["pose_after_refit"] == "reset")
    check("FR 4: MPFB's result stands", now["switch"] == 0.0)
    back = reset["restore_with"]
    answer(tool["mpfb_set_pose_switches"](**back["mpfb_set_pose_switches"]))
    answer(tool["mpfb_set_pose_bones"](**back["mpfb_set_pose_bones"]))
    now = own("live_check_state", rig=rig)
    check("FR 5: restore_with puts it back", now["switch"] == 1.0
          and same(now["hand"], included["hand"], 1e-3), now["hand"])

    # --- what a third character shows
    plain = answer(tool["mpfb_refit_human"](name=third["body"]))
    check("FR 2: a default rig is unchanged", plain["pose_after_refit"] == "unchanged")
    check("FR 8: and it was included too", plain["temporarily_included"] == ["Third"])

    # --- FR 12's finding, and the cost
    cycle = own("live_check_hide_cycle")
    check("FR 12: hide_set is lost by the exclude itself, every time, with no tool involved",
          not any(cycle["hidden_after_each"]), cycle["hidden_after_each"])
    timing = own("live_check_timing", body=body)
    print("timing: " + ", ".join("{:s} {:.1f}".format(key, value) if isinstance(value, float)
                                 else "{:s} {!s}".format(key, value)
                                 for key, value in timing.items()), flush=True)
    overhead = (timing["read_ms"] + timing["classify_ms"] + timing["limbs_ms"]
                + timing["compare_ms"] + timing["put_back_ms"])
    check("cheap: keeping a pose costs little beside the refit it surrounds",
          overhead < timing["refit_ms"] / 2.0,
          "{:.0f} ms beside {:.0f} ms".format(overhead, timing["refit_ms"]))


def main() -> int:
    """Start a headless Blender, run the check, and say how it went."""
    RENDERS.mkdir(exist_ok=True)
    tool = {item.name: item.fn
            for item in build_server()._tool_manager.list_tools()}  # pylint: disable=protected-access
    with tempfile.TemporaryDirectory() as temporary:
        before_bridge = Path(temporary) / "before_bridge.py"
        before_bridge.write_text(BEFORE_BRIDGE.format(renders=str(RENDERS)), encoding="utf-8")
        with Blender(before_bridge, Path(temporary)):
            run(tool)
    print("{:d} checks, {:d} failed".format(_checks, len(_failures)))
    for failure in _failures:
        print("  " + failure)
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
