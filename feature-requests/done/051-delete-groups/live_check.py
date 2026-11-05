# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 051 against the three garments of the spike, the gi first.

The request's own check, through the real tool callables over a real socket against headless
Blenders. From ``taido_gi_v2.blend`` with its group put back to the draft's 2,563, ``merge`` must land
of the order of the session's 3,209, within 10 s, leaving ``delete.original`` holding the draft, and a
rerun must change nothing. Then the asset is written, and ``chudan_gamae.blend`` and
``gedan_gamae.blend`` wear it beside the session's own, measured and rendered. The dress and the suit
then run from their authored groups and from empty, with the same measure taken of the authored
group for comparison. An export and a written MHCLO are checked for the kept group.

**Six commands the bridge does not have**, added to the running table in this process only as FR 050's
check adds its own: setting a group to a list, listing a body's delete groups, measuring a named group,
taking a garment off a posed scene's body, reading a file's vertex groups, and rendering. The closed vocabulary is what the add-on ships.

**Nothing of the user's is written.** Export directories and renders aside, everything is in temporary
directories, and no scene is saved. Renders land in ``renders/`` beside this file, and are kept.

Skips if the gi's files are absent. It needs ``mpfb_bridge`` enabled in the Blender it is pointed at
(``local_environment.md``)::

    BLENDER=/path/to/blender python3 feature-requests/done/051-delete-groups/live_check.py
"""

from __future__ import annotations

__all__ = ()

import json
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
TAIDO = Path("/export/3d/taido")
SCENE = TAIDO / "taido_gi_v2.blend"
SESSION_ASSET = TAIDO / "taido_gi_asset" / "taido_gi.mhclo"
POSES = Path("/home/joepal/claude/interacting_with_blender/taido/poses")
POSED_SCENES = (POSES / "chudan_gamae.blend", POSES / "gedan_gamae.blend")
GARMENT = "Human.nurse_uniform_with_pants"
GROUP = "delete"
LIBRARY = ("toigo_keyhole_neck_dress", "mindfront_m_suit_01")

DRAFT_VERTICES = 2563
SESSION_VERTICES = 3209

BEFORE_BRIDGE = """
import os, sys
import bpy
import numpy
from mathutils import Vector

RENDERS = {renders!r}

bridge = next(name[:-len(".commands.table")] for name in sys.modules
              if name.endswith("mpfb_bridge.commands.table"))
table = sys.modules[bridge + ".commands.table"]
validation = sys.modules[bridge + ".validation"]
delete_group = sys.modules.get(bridge + ".shared.delete_group")
if delete_group is None:
    import importlib
    delete_group = importlib.import_module(bridge + ".shared.delete_group")

VIEWS = dict(
    chest=((0.12, -1.0, 0.10), (0.04, -0.12, -0.20), 1.45),
    macro=((0.25, -1.0, 0.15), (0.09, -0.15, -0.20), 0.62),
    chest_side=((0.75, -1.0, 0.20), (0.04, -0.12, -0.20), 1.45),
    above=((0.15, -0.55, 1.0), (0.0, -0.05, -0.10), 0.9),
)


def _set_group(params, resolution):
    body = bpy.data.objects[params["body"]]
    group = body.vertex_groups[params["group"]]
    members = params["members"]
    if members is None:
        members = list(body[params["from_property"]])
    group.remove(list(range(len(body.data.vertices))))
    group.add(members, 1.0, "REPLACE")
    return dict(vertices=len(members))


def _groups(params, resolution):
    body = bpy.data.objects[params["body"]]
    rows = dict((group.name, sum(1 for vertex in body.data.vertices
                                 if any(element.group == group.index for element in vertex.groups)))
                for group in body.vertex_groups if group.name.lower().startswith("delete"))
    return dict(groups=rows, modifiers=[modifier.name for modifier in body.modifiers])


def _measure(params, resolution):
    body = bpy.data.objects[params["body"]]
    garment = bpy.data.objects[params["garment"]]
    reading, refusal = delete_group.read(body, garment)
    assert refusal is None, refusal
    members = reading.members(body.vertex_groups[params["group"]].index)
    openings = delete_group.openings_of(reading, dict(delete_group.DEFAULT_MARGINS))
    slits, under, here = delete_group.measure(reading, members, openings)
    return dict(vertices=int(members.sum()), as_loaded=int(delete_group.as_loaded(reading, members).sum()),
                masked_skin_still_visible=slits, unmasked_skin_under_garment=under,
                masked_skin_still_visible_authoring=here)


def _clear_garment(params, resolution):
    body = next(blender_object for blender_object in bpy.data.objects
                if blender_object.get("mpfb_placeholder") is None
                and blender_object.type == "MESH" and "body" in blender_object.vertex_groups
                and "joint-neck" in blender_object.vertex_groups)
    removed = []
    for name in params["names"]:
        blender_object = bpy.data.objects.get(name)
        if blender_object is not None:
            removed.append(name)
            bpy.data.objects.remove(blender_object)
    for modifier in list(body.modifiers):
        if modifier.type == "MASK" and modifier.name != "Hide helpers":
            body.modifiers.remove(modifier)
    return dict(body=body.name, removed=removed)


def _file_groups(params, resolution):
    before = set(blender_object.name for blender_object in bpy.data.objects)
    path = params["path"]
    if path.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    created = [blender_object for blender_object in bpy.data.objects
               if blender_object.name not in before]
    names = sorted(set(group.name for blender_object in created
                       for group in blender_object.vertex_groups))
    for blender_object in created:
        bpy.data.objects.remove(blender_object)
    return dict(vertex_groups=names, objects=len(created))


def _render(params, resolution):
    scene = bpy.context.scene
    body = bpy.data.objects[params["body"]]
    for name in ("Puff", "IrradianceVolume"):
        blender_object = bpy.data.objects.get(name)
        if blender_object is not None:
            blender_object.hide_render = True
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = False
    # The CPU: a GPU here may be busy with something else, and 4K textures do not fit beside it.
    scene.cycles.device = "CPU"
    scene.render.resolution_x = 800
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 85
    camera_data = bpy.data.cameras.new("live_check_camera")
    camera = bpy.data.objects.new("live_check_camera", camera_data)
    scene.collection.objects.link(camera)
    previous = scene.camera
    scene.camera = camera
    camera_data.lens = 85
    camera_data.sensor_width = 36
    depsgraph = bpy.context.evaluated_depsgraph_get()
    states = [(modifier, modifier.show_viewport) for modifier in body.modifiers if modifier.type == "MASK"]
    for modifier, _state in states:
        modifier.show_viewport = False
    bpy.context.view_layer.update()
    evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    neck_group = body.vertex_groups["joint-neck"].index
    neck = [vertex.co.copy() for vertex in mesh.vertices
            if any(element.group == neck_group for element in vertex.groups)]
    centre = sum(neck, Vector()) / len(neck)
    world_neck = body.matrix_world @ centre
    evaluated.to_mesh_clear()
    for modifier, state in states:
        modifier.show_viewport = state
    bpy.context.view_layer.update()
    made = []
    for view in params["views"]:
        direction, offset, distance = VIEWS[view]
        direction = Vector(direction).normalized()
        target = world_neck + Vector(offset)
        camera.location = target + direction * distance
        camera.rotation_mode = "QUATERNION"
        camera.rotation_quaternion = (-direction).to_track_quat("-Z", "Y")
        scene.render.filepath = os.path.join(RENDERS, "{{:s}}_{{:s}}.jpg".format(params["prefix"], view))
        bpy.ops.render.render(write_still=True)
        made.append(scene.render.filepath)
    scene.camera = previous
    bpy.data.objects.remove(camera)
    bpy.data.cameras.remove(camera_data)
    return dict(files=made)


string = validation.TYPE_STRING
for name, handler, params in (
    ("live_check_set_group", _set_group, (
        validation.Param("body", string, required=True),
        validation.Param("group", string, required=True),
        validation.Param("members", validation.TYPE_ARRAY, default=None, nullable=True),
        validation.Param("from_property", string, default=None, nullable=True))),
    ("live_check_groups", _groups, (validation.Param("body", string, required=True),)),
    ("live_check_measure", _measure, (
        validation.Param("body", string, required=True),
        validation.Param("garment", string, required=True),
        validation.Param("group", string, required=True))),
    ("live_check_clear_garment", _clear_garment, (
        validation.Param("names", validation.TYPE_ARRAY, required=True),)),
    ("live_check_file_groups", _file_groups, (validation.Param("path", string, required=True),)),
    ("live_check_render", _render, (
        validation.Param("body", string, required=True),
        validation.Param("prefix", string, required=True),
        validation.Param("views", validation.TYPE_ARRAY, required=True))),
):
    table.COMMANDS[name] = table.Command(name=name, handler=handler, params=params, requires_mpfb=True,
                                         summary="This check's own, in this process only.")
"""

_failures = []
_checks = 0
_outcome = dict()
_as_loaded = dict()


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

    def __init__(self, blend: Path | None, before_bridge: Path, export_directory: Path) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        command = [BLENDER, "--background"]
        if blend is not None:
            command.append(str(blend))
        command.extend(("--python", str(before_bridge), "--command", "mpfb_bridge", "--port",
                        str(self.port), "--export-dir", str(export_directory)))
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


def tools() -> dict:
    """The real tool callables, off the server that ships."""
    # pylint: disable=protected-access
    return {tool.name: tool.fn for tool in build_server()._tool_manager.list_tools()}


def answer(envelope: dict) -> dict:
    """The result of a call that must not have failed."""
    if envelope.get("status") != "ok":
        raise RuntimeError(json.dumps(envelope)[:1800])
    return envelope["result"]


def own(command: str, **params: object) -> dict:
    """One of this check's own commands."""
    return answer(backend.send(command, params=params))


def timed(call, **arguments) -> tuple[dict, float]:
    """A call's answer and how long it took, in seconds."""
    started = time.perf_counter()
    result = answer(call(**arguments))
    return (result, time.perf_counter() - started)


def counts(result: dict) -> str:
    return "{:d} vertices, {:d} visible, {:d} under, {:d} visible on this body".format(
        result["vertices_after"], result["masked_skin_still_visible"],
        result["unmasked_skin_under_garment"], result["masked_skin_still_visible_authoring"])


def print_openings(result: dict) -> None:
    for row in result["openings"]:
        if row["perimeter"] >= 0.1:
            print("    {:7s} p={:.3f} open={:.2f} margin={:.3f} kept={:<4d} {!s} {!s}".format(
                row["kind"], row["perimeter"], row["open_share"], row["margin"],
                row["kept_by_margin"], row["limbs"], row["centre"]))
    print("    {:d} openings in all".format(result["openings_total"]))


def the_gi(available: dict, exports: Path) -> Path:
    """From the draft's group, then the asset written with what came back."""
    generate = available["mpfb_generate_delete_group"]
    authored = own("live_check_measure", body="Human", garment=GARMENT, group=GROUP)
    print("the session's group: {!s}".format(authored))
    _outcome["gi authored"] = authored
    _as_loaded["session"] = authored["as_loaded"]
    check("the session's group is what the request says", authored["vertices"] == SESSION_VERTICES)
    own("live_check_set_group", body="Human", group=GROUP, members=None,
        from_property="gi_draft_delete_group")
    draft = own("live_check_measure", body="Human", garment=GARMENT, group=GROUP)
    print("the draft's group: {!s}".format(draft))
    _outcome["gi draft"] = draft
    check("and the draft's", draft["vertices"] == DRAFT_VERTICES)

    dry, seconds = timed(generate, name=GARMENT, delete_group=GROUP, dry_run=True)
    check("a dry run changes nothing", own("live_check_groups", body="Human")["groups"] == {
        GROUP: DRAFT_VERTICES} and dry["generated"] is False, dry["vertices_after"])

    result, seconds = timed(generate, name=GARMENT, delete_group=GROUP)
    print("merge from the draft, in {:.2f} s: {:s}".format(seconds, counts(result)))
    print_openings(result)
    _outcome["gi generated"] = dict(vertices=result["vertices_after"], seconds=round(seconds, 2),
                                    masked_skin_still_visible=result["masked_skin_still_visible"],
                                    unmasked_skin_under_garment=result["unmasked_skin_under_garment"],
                                    authoring=result["masked_skin_still_visible_authoring"])
    check("a call under the request's 10 s", seconds < 10.0, round(seconds, 2))
    check("of the order of the session's 3,209",
          abs(result["vertices_after"] - SESSION_VERTICES) < SESSION_VERTICES * 0.1,
          result["vertices_after"])
    check("no more can be seen than through the session's group, whose renders are clean",
          result["masked_skin_still_visible"] <= authored["masked_skin_still_visible"],
          (result["masked_skin_still_visible"], authored["masked_skin_still_visible"]))
    check("nor on this body, where the wedges were",
          result["masked_skin_still_visible_authoring"] <= authored["masked_skin_still_visible_authoring"],
          (result["masked_skin_still_visible_authoring"], authored["masked_skin_still_visible_authoring"]))
    check("and less stands under the coat than the session left, or about as much",
          result["unmasked_skin_under_garment"] <= authored["unmasked_skin_under_garment"] * 1.1,
          (result["unmasked_skin_under_garment"], authored["unmasked_skin_under_garment"]))
    kinds = sorted(row["kind"] for row in result["openings"])
    check("two cuffs, two hems and the V, found with no threshold",
          kinds.count("cuff") == 2 and kinds.count("hem") == 2 and "trunk" in kinds, kinds)
    groups = own("live_check_groups", body="Human")["groups"]
    check("the draft is kept", groups.get(GROUP + ".original") == DRAFT_VERTICES, groups)
    check("original_kept_as names it", result["original_kept_as"] == GROUP + ".original")

    again = answer(generate(name=GARMENT, delete_group=GROUP))
    check("a rerun changes nothing, and it is deterministic",
          again["added"] == 0 and again["removed"] == 0
          and own("live_check_groups", body="Human")["groups"] == groups)

    measured = answer(available["mpfb_check_intersections"](name=GARMENT))
    rows = [row for row in measured["pairs"] if "Human" in (row["object_name"], row["other_object_name"])]
    print("mpfb_check_intersections after the write: {:s}".format(json.dumps(rows)[:400]))
    _outcome["gi intersections"] = [(row["face_pairs"], row["face_pairs_unmasked"]) for row in rows]

    own("live_check_render", body="Human", prefix="authoring", views=["chest", "macro", "chest_side", "above"])

    _as_loaded["generated"] = own("live_check_measure", body="Human", garment=GARMENT, group=GROUP)["as_loaded"]
    written = answer(available["mpfb_write_mesh_asset"](
        name=GARMENT, asset_name="generated_gi", destination="export_directory", delete_group=GROUP,
        license="CC0", author="Joel"))
    check("the asset is written", written["written"], written["message"])
    check("with the generated group", written["delete_vertices"] == result["vertices_after"],
          written["delete_vertices"])
    path = Path(written["path"])
    text = path.read_text(encoding="utf8")
    check("the MHCLO holds no kept copy", ".original" not in text)
    return path


def worn_on(available: dict, blend: Path, generated: Path, _exports: Path) -> None:
    """On a posed character, what the session's asset and this one each leave."""
    label = blend.stem
    for prefix, mhclo in (("session", SESSION_ASSET), ("generated", generated)):
        cleared = own("live_check_clear_garment", names=["gi_top", "gi_bottom", "taido_gi", "generated_gi"])
        body = cleared["body"]
        added = answer(available["mpfb_add_asset"](name=body, path=str(mhclo), object_type="Clothes"))
        check("{:s}: {:s} goes on".format(label, prefix), added["added"], added["message"])
        measured = answer(available["mpfb_check_intersections"](name=body))
        rows = [row for row in measured["pairs"] if added["asset_object_name"] in (
            row["object_name"], row["other_object_name"]) and body in (
                row["object_name"], row["other_object_name"])]
        pairs = [(row["face_pairs"], row["face_pairs_unmasked"]) for row in rows]
        loaded_groups = own("live_check_groups", body=body)["groups"]
        print("{:s} {:s}: masked and unmasked pairs {!s}, loaded group {!s}".format(
            label, prefix, pairs, loaded_groups))
        expected = _as_loaded.get(prefix)
        if expected is not None:
            check("{:s}: {:s} loads as many as was counted".format(label, prefix),
                  loaded_groups.get("Delete." + mhclo.stem) == expected,
                  (loaded_groups.get("Delete." + mhclo.stem), expected))
        _outcome["{:s} {:s}".format(label, prefix)] = pairs
        own("live_check_render", body=body, prefix="{:s}_{:s}".format(label, prefix),
            views=["chest", "chest_side"])
        answer(available["mpfb_remove_asset"](name=added["asset_object_name"]))


def library_garment(available: dict, exports: Path, garment: str) -> None:
    """A garment with an authored group, from it and from empty."""
    character = answer(available["mpfb_create_human"]())
    body = character["basemesh_name"]
    answer(available["mpfb_add_rig"](name=body, identifier="default"))
    added = answer(available["mpfb_add_asset"](name=body, fragment="{0:s}/{0:s}.mhclo".format(garment),
                                               object_type="Clothes"))
    worn = added["asset_object_name"]
    group = "Delete.{:s}".format(garment)
    authored = own("live_check_measure", body=body, garment=worn, group=group)
    print("{:s}, authored: {!s}".format(garment, authored))
    _outcome[garment + " authored"] = authored
    generate = available["mpfb_generate_delete_group"]

    merged, seconds = timed(generate, name=worn, basemesh=body, delete_group=group)
    print("{:s}, merge in {:.2f} s: {:s}".format(garment, seconds, counts(merged)))
    print_openings(merged)
    check("{:s}: under the request's 10 s".format(garment), seconds < 10.0, round(seconds, 2))
    check("{:s}: a loaded asset's Delete.<name> is honoured".format(garment),
          merged["delete_group"] == group and merged["vertices_before"] == authored["vertices"])
    check("{:s}: its Subdivision is no obstacle".format(garment), merged["ready"], merged["message"])
    check("{:s}: its mask is reported".format(garment), merged["mask_modifier_present"] is True)
    _outcome[garment + " merge"] = dict(vertices=merged["vertices_after"], seconds=round(seconds, 2),
                                        masked_skin_still_visible=merged["masked_skin_still_visible"],
                                        unmasked_skin_under_garment=merged["unmasked_skin_under_garment"],
                                        authoring=merged["masked_skin_still_visible_authoring"])
    replaced = answer(generate(name=worn, basemesh=body, delete_group=group, mode="replace"))
    print("{:s}, replace: {:s}".format(garment, counts(replaced)))
    _outcome[garment + " replace"] = dict(vertices=replaced["vertices_after"],
                                          masked_skin_still_visible=replaced["masked_skin_still_visible"],
                                          unmasked_skin_under_garment=replaced["unmasked_skin_under_garment"],
                                          authoring=replaced["masked_skin_still_visible_authoring"])
    check("{:s}: every run kept the same original".format(garment),
          own("live_check_groups", body=body)["groups"][group + ".original"] == authored["vertices"])

    exported = answer(available["mpfb_export_character"](
        name=body, export_name="fr051_{:s}".format(garment), format="fbx"))
    check("{:s}: it exports".format(garment), exported["performed"], exported["message"])
    in_file = own("live_check_file_groups", path=exported["path"])
    print("{:s}: the FBX has {:d} vertex groups".format(garment, len(in_file["vertex_groups"])))
    check("{:s}: the kept group reaches no FBX".format(garment),
          not any(".original" in name for name in in_file["vertex_groups"]))
    exported = answer(available["mpfb_export_character"](
        name=body, export_name="fr051_{:s}_gltf".format(garment), format="gltf"))
    check("{:s}: nor a glTF".format(garment), exported["performed"] and not any(
        ".original" in name for name in own("live_check_file_groups", path=exported["path"])["vertex_groups"]))


def main() -> int:
    if not SCENE.exists():
        print("skip: the gi's files are absent")
        return 0
    RENDERS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fr051_") as temporary:
        root = Path(temporary)
        exports = root / "exports"
        exports.mkdir()
        script = root / "before_bridge.py"
        script.write_text(BEFORE_BRIDGE.format(renders=str(RENDERS)), encoding="utf8")
        with Blender(SCENE, script, exports):
            generated = the_gi(tools(), exports)
        for blend in POSED_SCENES:
            with Blender(blend, script, exports):
                worn_on(tools(), blend, generated, exports)
        for garment in LIBRARY:
            with Blender(None, script, exports):
                library_garment(tools(), exports, garment)
    print(json.dumps(_outcome, indent=1))
    print("{:d} checks, {:d} failed".format(_checks, len(_failures)))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
