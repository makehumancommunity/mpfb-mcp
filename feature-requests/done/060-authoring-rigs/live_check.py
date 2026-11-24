# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 060 against a real Blender: the ``claude_demo`` session again, through the four tools.

The request's own check, through the real tool callables over a real socket against a headless
Blender. ``claude_demo``'s table is read with ``mpfb_get_rig_definition``, its store refused as
shadowed by ``claude_demo`` itself, renamed, rebuilt with ``replace``, weighted, stored, and put on
a deliberately different body with ``mpfb_add_rig``: the elbow must refit, every vertex must be
weighted, and a 90-degree elbow and shoulder bend must read back through ``mpfb_get_pose`` and move
the forearm and not the torso. Then ``transfer`` is compared with MPFB's own MakeRig operator on
the same pair of rigs, and three questions for upstream are put to the install: whether a stray
mask outlives its rig, whether the save loses ``use_deform``, and whether ``identify_rig()``'s
choice between two matching custom rigs is the directory's order.

**Six commands the bridge does not have**, added to the running table in this process only, as
FR 050's check adds its own: a displacement measure, an unweighted count, MPFB's operator, an
object deletion, an identification and a provoked collision. The closed vocabulary is what the
add-on ships.

**Nothing of the user's is written.** MPFB's user data is pointed at a temporary directory holding
a copy of ``claude_demo``, and no scene is saved. Skips without ``claude_demo``. It needs
``mpfb_bridge`` enabled in the Blender it is pointed at (``local_environment.md``)::

    BLENDER=/path/to/blender python3 feature-requests/done/060-authoring-rigs/live_check.py
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

from mpfbmcp import build_server

BLENDER = os.environ.get("BLENDER", shutil.which("blender") or "blender")
LIBRARY = Path("/home/joepal/makehuman/mpfb/data/rigs")
DEMO = "claude_demo"
PREFIX = "fr060_"

# The session's numbers, for the record beside this run's.
SESSION_ELBOWS = (1.140, 0.992)
SESSION_UNWEIGHTED_BEFORE_FILL = 1384
SESSION_MPFB_TRANSFER = (8, 19)

_MACRO = {"gender": 0.5, "age": 0.5, "muscle": 0.5, "weight": 0.5, "proportions": 0.5,
          "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
          "race": {"asian": 1.0 / 3.0, "caucasian": 1.0 / 3.0, "african": 1.0 / 3.0}}

BEFORE_BRIDGE = """
import json, os, sys
import bpy
from mathutils import Vector

root = next(name[:-len(".services.humanservice")] for name in sys.modules
            if name.endswith(".services.humanservice"))
location_service = sys.modules[root + ".services.locationservice"].LocationService
location_service._user_data = {user_data!r}
location_service._second_root = {missing!r}
rig_service = sys.modules[root + ".services.rigservice"].RigService
asset_service = sys.modules[root + ".services.assetservice"].AssetService
asset_service.invalidate_custom_rig_cache()


def _weights_of(basemesh, names):
    index = {{group.index: group.name for group in basemesh.vertex_groups if group.name in names}}
    weights = {{}}
    for vertex in basemesh.data.vertices:
        for element in vertex.groups:
            if element.group in index and element.weight > 0.0001:
                weights.setdefault(index[element.group], {{}})[vertex.index] = element.weight
    return weights


def _displacement(params, resolution):
    basemesh = bpy.data.objects[params["name"]]
    armature = basemesh.parent
    weights = _weights_of(basemesh, set(params["bones"]))

    def evaluated():
        bpy.context.view_layer.update()
        mesh = basemesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        return [vertex.co.copy() for vertex in mesh.vertices]

    # Every modifier but the armature off, the helper mask included, so the evaluated mesh keeps
    # the basemesh's own vertex indices.
    shown = {{modifier.name: modifier.show_viewport for modifier in basemesh.modifiers}}
    for modifier in basemesh.modifiers:
        if modifier.type != "ARMATURE":
            modifier.show_viewport = False
    try:
        posed = evaluated()
        armature.data.pose_position = "REST"
        rest = evaluated()
    finally:
        armature.data.pose_position = "POSE"
        for modifier in basemesh.modifiers:
            modifier.show_viewport = shown[modifier.name]
        bpy.context.view_layer.update()
    answer = {{}}
    for bone in params["bones"]:
        members = [index for index, weight in weights.get(bone, {{}}).items() if weight > 0.5]
        if members and len(posed) == len(rest):
            answer[bone] = round(sum((posed[i] - rest[i]).length for i in members)
                                 / len(members), 4)
        else:
            answer[bone] = None
    return answer


def _unweighted(params, resolution):
    basemesh = bpy.data.objects[params["name"]]
    armature = basemesh.parent
    deforming = {{bone.name for bone in armature.data.bones if bone.use_deform}}
    weighted = set()
    for entries in _weights_of(basemesh, deforming).values():
        weighted.update(entries)
    return dict(unweighted=len(basemesh.data.vertices) - len(weighted))


def _mpfb_transfer(params, resolution):
    source = bpy.data.objects[params["source"]]
    target = bpy.data.objects[params["target"]]
    body = next(child for child in target.children if child.type == "MESH")
    for bone in target.data.bones:
        group = body.vertex_groups.get(bone.name)
        if group is not None:
            body.vertex_groups.remove(group)
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = source
    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window, active_object=source, object=source,
                                   selected_objects=[source, target]):
        outcome = bpy.ops.mpfb.auto_transfer_weights()
    weights = _weights_of(body, {{bone.name for bone in target.data.bones}})
    matched = sorted(name for name in weights if weights[name])
    return dict(outcome=sorted(outcome), matched=len(matched),
                unmatched=len(target.data.bones) - len(matched))


def _delete(params, resolution):
    blender_object = bpy.data.objects[params["name"]]
    for child in list(blender_object.children):
        world = child.matrix_world.copy()
        child.parent = None
        child.matrix_world = world
    bpy.data.objects.remove(blender_object, do_unlink=True)
    return dict(deleted=params["name"])


def _identify(params, resolution):
    return dict(identified_as=rig_service.identify_rig(bpy.data.objects[params["name"]]))


def _collision(params, resolution):
    # Two custom rigs that both match one armature, written straight to the library as a
    # hand-made or MPFB-saved pair would be, then identify_rig() asked about that armature.
    rigs_dir = os.path.join({user_data!r}, "rigs")
    os.makedirs(rigs_dir, exist_ok=True)
    armature = bpy.data.objects[params["name"]]
    bones = [bone.name for bone in armature.data.bones]
    for name, identifying in (("collide_one", bones[:1]), ("collide_two", bones[:2])):
        with open(os.path.join(rigs_dir, name + ".json"), "w", encoding="utf8") as rig_file:
            json.dump(dict(bones=dict(), version=110, identifying_bones=identifying), rig_file)
    asset_service.invalidate_custom_rig_cache()
    order = [record["name"] for record in asset_service.get_custom_rigs()]
    identified = rig_service.identify_rig(armature)
    for name in ("collide_one", "collide_two"):
        os.remove(os.path.join(rigs_dir, name + ".json"))
    asset_service.invalidate_custom_rig_cache()
    return dict(scan_order=order, identified_as=identified)


bridge = next(name[:-len(".commands.table")] for name in sys.modules
              if name.endswith("mpfb_bridge.commands.table"))
table = sys.modules[bridge + ".commands.table"]
validation = sys.modules[bridge + ".validation"]
for command, handler, params in (
        ("live_check_displacement", _displacement,
         (validation.Param("name", validation.TYPE_STRING, required=True),
          validation.Param("bones", validation.TYPE_ARRAY, required=True))),
        ("live_check_unweighted", _unweighted,
         (validation.Param("name", validation.TYPE_STRING, required=True),)),
        ("live_check_mpfb_transfer", _mpfb_transfer,
         (validation.Param("source", validation.TYPE_STRING, required=True),
          validation.Param("target", validation.TYPE_STRING, required=True))),
        ("live_check_delete", _delete,
         (validation.Param("name", validation.TYPE_STRING, required=True),)),
        ("live_check_identify", _identify,
         (validation.Param("name", validation.TYPE_STRING, required=True),)),
        ("live_check_collision", _collision,
         (validation.Param("name", validation.TYPE_STRING, required=True),))):
    table.COMMANDS[command] = table.Command(name=command, handler=handler, params=params,
                                            requires_mpfb=True,
                                            summary="This check's own, in this process only.")
"""

_failures = []
_checks = 0
_record = {}


def check(what: str, passed: bool, observed: object = None) -> None:
    """One claim. Printed either way, so that the run is its own record."""
    global _checks  # pylint: disable=global-statement
    _checks += 1
    print("{:s} {:s}{:s}".format("ok  " if passed else "FAIL", what,
                                 "" if observed is None else "  [{!s}]".format(observed)))
    if not passed:
        _failures.append(what)


def note(what: str, observed: object) -> None:
    """A measurement with no pass or fail, kept for the request's record."""
    _record[what] = observed
    print("note {:s}  [{!s}]".format(what, observed))


class Blender:
    """A headless Blender with the bridge up on a port of its own, stopped on exit."""

    def __init__(self, before_bridge: Path) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.process = subprocess.Popen(  # pylint: disable=consider-using-with
            [BLENDER, "--background", "--python", str(before_bridge),
             "--command", "mpfb_bridge", "--port", str(self.port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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
        raise RuntimeError(json.dumps(envelope)[:1200])
    return envelope["result"]


def live(command: str, **params: object) -> dict:
    """One of this check's own commands, straight over the socket."""
    from mpfbmcp import backend  # pylint: disable=import-outside-toplevel
    return answer(backend.send(command, params=params))


def timed(call, **arguments) -> tuple[dict, float]:
    """A call's answer and how long it took, in milliseconds."""
    started = time.perf_counter()
    result = answer(call(**arguments))
    return (result, (time.perf_counter() - started) * 1000.0)


def human(available: dict, **macro: float) -> str:
    return answer(available["mpfb_create_human"](**macro))["basemesh_name"]


def renamed(table: list) -> list:
    """``claude_demo``'s table with every bone prefixed, so it is a rig of its own."""
    rows = []
    for row in table:
        copy = dict(row)
        copy["name"] = PREFIX + row["name"]
        copy["parent"] = PREFIX + row["parent"] if row["parent"] else ""
        rows.append(copy)
    return rows


def elbow(definition: dict) -> float:
    row = next(bone for bone in definition["bones"] if bone["name"].endswith("lowerarm.L"))
    return row["head"]["position"]["up"]


def authoring(available: dict) -> tuple[str, list]:
    """Read, refuse, rename, rebuild, weight and store. Returns the authoring body and table."""
    first = human(available)
    demo, ms = timed(available["mpfb_get_rig_definition"], name=first, rig="custom." + DEMO)
    note("mpfb_get_rig_definition of claude_demo, ms", round(ms))
    table = demo["bones"]
    check("claude_demo reads as a table of 27 bones", len(table) == 27, len(table))
    for rig, compact in (("default", False), ("default", True), ("custom." + DEMO, False)):
        envelope = available["mpfb_get_rig_definition"](name=first, rig=rig, compact=compact)
        note("answer size {:s}{:s}, bytes".format(rig, " compact" if compact else ""),
             len(json.dumps(envelope)))

    built, ms = timed(available["mpfb_create_rig"], name=first, bones=table)
    note("mpfb_create_rig, ms", round(ms))
    check("the table builds", built["created"] is True, built["message"])
    answer(available["mpfb_weight_rig"](name=first, method="automatic", exclude_bones=["root"]))
    refused = answer(available["mpfb_store_rig"](name=first, rig_name="fr060_demo"))
    check("a copy of claude_demo is refused as shadowed by claude_demo",
          refused["blocked_by"] == "identification_shadowed"
          and refused.get("shadowed_by") == [DEMO], refused.get("shadowed_by"))

    table = renamed(table)
    rebuilt = answer(available["mpfb_create_rig"](name=first, bones=table, replace=True))
    check("replace rebuilds over the rig it built", rebuilt["replaced"] is True)
    check("no group is kept across a rename", rebuilt["weights_kept"] == [],
          len(rebuilt["weights_dropped"]))
    weighted, ms = timed(available["mpfb_weight_rig"], name=first, method="automatic",
                         exclude_bones=[PREFIX + "root"])
    note("mpfb_weight_rig automatic, ms", round(ms))
    note("unweighted before the fill (session: {:d})".format(SESSION_UNWEIGHTED_BEFORE_FILL),
         weighted["unweighted"]["before_fill"])
    check("no body vertex is unweighted before the fill",
          weighted["unweighted"]["before_fill"]["body"] == 0)
    check("nothing is unweighted after the fill",
          sum(weighted["unweighted"]["after_fill"].values()) == 0,
          weighted["unweighted"]["after_fill"])
    check("the excluded root is non-deforming", weighted["set_non_deforming"] == [PREFIX + "root"])
    check("every weighted bone has vertices", weighted["bones_without_weights"] == [])

    stored, ms = timed(available["mpfb_store_rig"], name=first, rig_name="fr060_demo")
    note("mpfb_store_rig, ms", round(ms))
    check("the rig is stored and found as itself",
          stored["stored"] is True and stored["identified_as_after"] == "custom.fr060_demo",
          stored["identifying_bones"])
    check("the excluded root is named as a flag the file loses",
          stored["deform_flags_lost"] == [PREFIX + "root"], stored["deform_flags_lost"])
    note("store: ends_rematched", stored["ends_rematched"])
    return first, table


def other_body(available: dict, first: str, table: list) -> str:
    """The stored rig on a male, old, heavy, short body."""
    second = human(available, gender=1.0, age=0.9, weight=0.9, height=0.1)
    added = answer(available["mpfb_add_rig"](name=second, identifier="custom.fr060_demo"))
    check("mpfb_add_rig applies the stored rig with its weights",
          added["added"] is True and added["weights_loaded"] is True)
    check("MPFB identifies it as itself",
          live("live_check_identify", name=added["rig_object_name"])["identified_as"]
          == "custom.fr060_demo")
    elbows = (elbow(answer(available["mpfb_get_rig_definition"](name=first))),
              elbow(answer(available["mpfb_get_rig_definition"](name=second))))
    note("left elbow up on the two bodies (session: {!s})".format(SESSION_ELBOWS), elbows)
    check("the elbow is refitted to the second body", abs(elbows[0] - elbows[1]) > 0.05, elbows)
    read = answer(available["mpfb_get_rig_definition"](name=second))
    check("the applied rig reads back as the table it was built from",
          [{key: {kind: value for kind, value in row[key].items() if kind != "position"}
            for key in ("head", "tail")} for row in read["bones"]]
          == [{key: {kind: value for kind, value in row[key].items() if kind != "position"}
               for key in ("head", "tail")} for row in table])
    check("every vertex of the second body is weighted",
          live("live_check_unweighted", name=second)["unweighted"] == 0)
    return second


def bend(available: dict, second: str) -> None:
    """A 90-degree elbow and shoulder bend, read back and measured on the mesh."""
    bones = [{"bone": PREFIX + "lowerarm.L", "rotate_by": {"axis": {"up": 1.0}, "degrees": 90.0}},
             {"bone": PREFIX + "upperarm.L", "rotate_by": {"axis": {"forward": 1.0},
                                                           "degrees": 90.0}}]
    written = answer(available["mpfb_set_pose_bones"](name=second, bones=bones))
    check("the bend is written on an unclassified rig", written["performed"] is True,
          written.get("message"))
    pose = answer(available["mpfb_get_pose"](name=second))
    # An authored rig is unclassified, so the pose comes back as a flat posed_bones list.
    posed = {entry["bone"]: entry for entry in pose.get("posed_bones") or []}
    check("mpfb_get_pose reads both bends back",
          {PREFIX + "lowerarm.L", PREFIX + "upperarm.L"} <= set(posed), sorted(posed))
    degrees = {name: posed[name]["rotation"]["degrees"] for name in posed}
    note("bends read back, degrees from rest in the frame", degrees)
    check("the shoulder reads back as 90 degrees",
          abs(degrees.get(PREFIX + "upperarm.L", 0.0) - 90.0) < 0.5, degrees)
    moved = live("live_check_displacement", name=second,
                 bones=[PREFIX + "lowerarm.L", PREFIX + "hand.L", PREFIX + "spine_02",
                        PREFIX + "thigh.R"])
    note("mean displacement of each bone's own vertices, metres", moved)
    check("the forearm moves", (moved[PREFIX + "lowerarm.L"] or 0.0) > 0.05)
    check("the torso and the other leg do not", max(moved[PREFIX + "spine_02"] or 0.0,
                                                   moved[PREFIX + "thigh.R"] or 0.0) < 0.005)
    answer(available["mpfb_reset_pose"](name=second))


def transfer(available: dict) -> None:
    """MPFB's operator and this transfer, from default_no_toes onto claude_demo's table."""
    source_body = human(available)
    source = answer(available["mpfb_add_rig"](name=source_body, identifier="default_no_toes"))
    target_body = human(available)
    demo = answer(available["mpfb_get_rig_definition"](name=target_body, rig="custom." + DEMO))
    target = answer(available["mpfb_create_rig"](name=target_body, bones=demo["bones"]))
    mpfb = live("live_check_mpfb_transfer", source=source["rig_object_name"],
                target=target["rig_object_name"])
    note("MPFB's auto transfer, matched and unmatched (session: {!s})".format(
        SESSION_MPFB_TRANSFER), (mpfb["matched"], mpfb["unmatched"]))
    ours = answer(available["mpfb_weight_rig"](name=target_body, method="transfer",
                                               from_rig="default_no_toes"))
    rules = {}
    for row in ours["bones"]:
        rules[row["matched_by"]] = rules.get(row["matched_by"], 0) + 1
    note("this transfer by rule", rules)
    note("source bones whose weights had nowhere to go", ours["source_bones_unassigned"])
    # claude_demo's root runs from joint-ground; default_no_toes' from a vertex, so it has no match.
    unmatched = [row["name"] for row in ours["bones"] if row["matched_by"] == "none"]
    check("every deforming bone but the root is matched by exact or chain",
          unmatched in ([], ["root"]), unmatched)
    check("nothing is unweighted after the fill", sum(ours["unweighted"]["after_fill"].values())
          == 0, ours["unweighted"])


def upstream(available: dict) -> None:
    """The three questions the request files upstream, put to this install."""
    body = human(available)
    meta = available["mpfb_add_rig"](name=body, identifier="rigify.human_toes")
    if meta.get("status") == "ok" and answer(meta)["added"]:
        live("live_check_delete", name=answer(meta)["rig_object_name"])
        answer(available["mpfb_create_rig"](name=body, bones=[
            {"name": "stray_hips", "parent": "", "head": {"joint": "joint-pelvis"},
             "tail": {"joint": "joint-spine-3"}}]))
        stray = answer(available["mpfb_store_rig"](name=body, rig_name="stray", dry_run=True))
        note("masks left on a body after its rig was deleted", stray["masks_on_body"])
        check("a stray mask outlives its rig, and the store says so",
              bool(stray["masks_on_body"]) and stray["masks_written"] == [],
              stray["masks_on_body"])
    else:
        print("skip: no Rigify, so no rig that carries masks")
    collision = live("live_check_collision",
                     name=answer(available["mpfb_get_rig_definition"](name=body))["rig_object_name"])
    note("identify_rig() between two matching custom rigs", collision)
    check("identify_rig() takes the first of two matching custom rigs in scan order",
          collision["identified_as"] == "custom." + next(
              name for name in collision["scan_order"] if name.startswith("collide_")),
          collision)


def main() -> int:
    if not (LIBRARY / (DEMO + ".json")).exists():
        print("skip: {:s} is not in the library".format(DEMO))
        return 0
    with tempfile.TemporaryDirectory(prefix="fr060_") as temporary:
        user_data = Path(temporary) / "data"
        (user_data / "rigs").mkdir(parents=True)
        for name in (DEMO + ".json", "weights." + DEMO + ".json"):
            shutil.copyfile(LIBRARY / name, user_data / "rigs" / name)
        script = Path(temporary) / "before_bridge.py"
        script.write_text(BEFORE_BRIDGE.format(user_data=str(user_data),
                                               missing=str(Path(temporary) / "none")),
                          encoding="utf8")
        with Blender(script):
            available = tools()
            first, table = authoring(available)
            second = other_body(available, first, table)
            bend(available, second)
            transfer(available)
            upstream(available)
    print(json.dumps(_record, indent=1, default=str))
    print("{:d} checks, {:d} failed".format(_checks, len(_failures)))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
