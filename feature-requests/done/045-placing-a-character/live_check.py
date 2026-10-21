# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 045's own live check: a three-character line-up, placed with mpfb-mcp tools alone.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. It drives the **real mpfb-mcp
tools over the real socket**, against a Blender already running with the MPFB
Bridge's server started (``MPFB_BRIDGE_PORT``, default 9877), on the
developer's real install: real rigs, real garments, the real ``ponytail01``.

**Every character is built, dressed and placed through mpfb-mcp.** The
community blender-mcp add-on's socket (``BLENDER_MCP_PORT``, default 9876) is
used only to read what no tool reports and a check needs: where a bone is
against the vertices it moves, where the scene camera is, and what MPFB's own
functions do without this package's repair.

    PYTHONPATH=. .venv/bin/python feature-requests/done/045-placing-a-character/live_check.py

It adds characters to the open scene and leaves them there, lined up in front
of the scene camera.

1. **Requirement 16's premise, before anything else is written**: a turned,
   unrigged character rigged by MPFB directly, and the same through
   ``mpfb_add_rig``; how far a forearm bone is from its forearm in each.
2. **The line-up**: three characters - the default rig with ``ponytail01``,
   dressed at the origin, a generated Rigify rig whose meta-rig is kept hidden,
   and the default rig in a garment - turned toward the scene camera with
   ``face_toward``, then spaced edge to edge from their footprints.
3. **The summary agrees** with each place answer, and stays under 8 KB.
4. **Cheap**: a placement's call time against a call that does nothing.
5. **The pose reads the same** before and after a move, on a posed character.
6. **``ponytail01``'s sub-rig, measured**: the request expected it to break
   whenever its character stood away from the origin. Dressed at the origin and
   then placed, it does not; equipped on a placed character it is dragged
   metres away, still at the origin, and ``mpfb_refit_human`` re-binds it.
7. **A placed meta-rig generates in place** (requirement 17).
8. **MPFB's world helpers**, on a turned rig: which ones ignore the rotation.

Prints PASS/FAIL per check, then the findings, and exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

BLENDER_MCP_PORT = int(os.environ.get("BLENDER_MCP_PORT", "9876"))
GAP_METRES = 0.25

FAILURES = []
FINDINGS = {}


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print("[{:s}] {:s}{:s}".format(status, label, "" if not detail else " - " + str(detail)),
          flush=True)
    if not condition:
        FAILURES.append(label)


def ok(envelope, what):
    if envelope.get("status") != "ok":
        raise SystemExit("{:s} failed: {!r}".format(what, envelope))
    return envelope["result"]


def in_blender(code):
    """Run ``code`` in the running Blender through the community add-on; returns its stdout."""
    with socket.create_connection(("127.0.0.1", BLENDER_MCP_PORT), timeout=300) as connection:
        connection.sendall(json.dumps({"type": "execute_code",
                                       "params": {"code": code}}).encode("utf-8"))
        buffer = b""
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            buffer += chunk
            try:
                answer = json.loads(buffer.decode("utf-8"))
                break
            except ValueError:
                continue
    if answer.get("status") != "success":
        raise SystemExit("Blender-side code failed: {!r}".format(answer))
    return answer["result"]["result"]


def blender_json(code):
    """``code``'s last ``print(json.dumps(...))``."""
    output = in_blender("import bpy, json, math, sys\nfrom mathutils import Vector\n" + code)
    return json.loads([line for line in output.splitlines() if line.strip()][-1])


# How far lowerarm01.L's head is from the middle of the vertices it moves.
FOREARM_CODE = '''
def forearm_mismatch(basemesh, rig):
    head = rig.matrix_world @ rig.data.bones["lowerarm01.L"].head_local
    group = basemesh.vertex_groups["lowerarm01.L"].index
    weighted = [basemesh.matrix_world @ v.co for v in basemesh.data.vertices
                if any(e.group == group and e.weight > 0.9 for e in v.groups)]
    centre = sum(weighted, Vector()) / len(weighted)
    return (head - centre).length
'''


def premise(tools):
    """Requirement 16: MPFB's own add, then the tool's, on a character turned 90 degrees."""
    raw = blender_json(FOREARM_CODE + '''
services = [m for n, m in sys.modules.items() if n.endswith("mpfb")][0].MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
basemesh = services["HumanService"].create_human()
basemesh.location = (-6.0, 3.0, 0.0)
basemesh.rotation_euler = (0.0, 0.0, math.radians(90.0))
bpy.context.view_layer.update()
services["ObjectService"].activate_blender_object(basemesh)
rig = services["HumanService"].add_builtin_rig(basemesh, "default", import_weights=True)
bpy.context.view_layer.update()
print(json.dumps(dict(mismatch=forearm_mismatch(basemesh, rig),
                      rig_rotation_z=math.degrees(rig.rotation_euler.z),
                      basemesh_rotation_z=math.degrees(basemesh.rotation_euler.z))))
''')
    FINDINGS["mpfb_add_builtin_rig_on_a_turned_basemesh"] = raw
    check("MPFB's own add drops a turned basemesh's rotation (the premise)",
          raw["mismatch"] > 0.2 and abs(raw["rig_rotation_z"]) < 1e-6, raw)

    created = ok(tools["mpfb_create_human"](), "create_human")
    name = created["basemesh_name"]
    ok(tools["mpfb_place_character"](name=name, position={"x": -6.0, "y": 5.0}, facing=90.0),
       "place the unrigged character")
    added = ok(tools["mpfb_add_rig"](name=name, identifier="default"), "add_rig")
    fitted = blender_json(FOREARM_CODE + '''
basemesh = bpy.data.objects[{basemesh!r}]
rig = bpy.data.objects[{rig!r}]
print(json.dumps(dict(mismatch=forearm_mismatch(basemesh, rig),
                      rig_rotation_z=math.degrees(rig.rotation_euler.z))))
'''.format(basemesh=name, rig=added["rig_object_name"]))
    FINDINGS["mpfb_add_rig_on_a_turned_basemesh"] = fitted
    check("mpfb_add_rig carries the turn over and the rig fits",
          added["basemesh_rotation_moved_to_rig"] is True and fitted["mismatch"] < 0.05
          and abs(fitted["rig_rotation_z"] - 90.0) < 1e-4, fitted)
    summary = ok(tools["mpfb_get_character_summary"](name=name), "summary")
    check("the rigged character still stands where it was placed",
          summary["placement"]["position"] == {"x": -6.0, "y": 5.0, "z": 0.0}
          and summary["placement"]["facing"] == 90.0, summary["placement"])
    return added["rig_object_name"]


def build(tools, macro, rig, assets):
    created = ok(tools["mpfb_create_human"](**macro), "create_human")
    name = created["basemesh_name"]
    ok(tools["mpfb_add_rig"](name=name, identifier=rig), "add_rig " + rig)
    equipped = []
    for fragment, object_type in assets:
        added = ok(tools["mpfb_add_asset"](name=name, fragment=fragment,
                                           object_type=object_type), "add_asset " + fragment)
        equipped.append(added)
    return name, equipped


def line_up(tools, camera):
    """Three characters, turned to the camera, then spaced edge to edge from their footprints."""
    built = []
    name, equipped = build(tools, {"gender": 0.0, "age": 0.5}, "default",
                           [("ponytail01/ponytail01.mhclo", "Hair")])
    built.append(dict(name=name, ponytail=equipped[0]))
    name, _ = build(tools, {"gender": 1.0, "muscle": 0.7}, "rigify.human_toes",
                    [("punkduck_female_short_jeans/punkduck_female_short_jeans.mhclo",
                      "Clothes")])
    generated = ok(tools["mpfb_generate_rigify_rig"](name=name), "generate_rigify_rig")
    built.append(dict(name=name, generated=generated))
    name, _ = build(tools, {"gender": 0.6, "height": 0.8}, "default",
                    [("toigo_shift_dress/toigo_shift_dress.mhclo", "Clothes")])
    built.append(dict(name=name))

    # First pass: turned toward the camera where each stands, to learn how wide
    # each is when facing it.
    for entry in built:
        entry["turned"] = ok(tools["mpfb_place_character"](
            name=entry["name"], position={"x": 0.0, "y": 0.0},
            face_toward={"object": camera}), "turn " + entry["name"])
    widths = [entry["turned"]["footprint"]["width"] for entry in built]
    total = sum(widths) + GAP_METRES * (len(built) - 1)

    # Second pass: edge to edge, centred on the camera's x, each turned toward
    # the camera from where it now stands - one call per character.
    cursor = camera_x(camera) - total / 2.0
    timings = []
    for entry, width in zip(built, widths):
        offset = entry["turned"]["position_after"]["x"] - entry["turned"]["footprint"]["min"]["x"]
        started = time.perf_counter()
        entry["placed"] = ok(tools["mpfb_place_character"](
            name=entry["name"], position={"x": cursor + offset, "y": 0.0},
            face_toward={"object": camera}), "place " + entry["name"])
        timings.append(time.perf_counter() - started)
        cursor += width + GAP_METRES
    FINDINGS["placement_call_seconds"] = [round(value, 3) for value in timings]
    # Measured against a call that does nothing, in the same Blender: a
    # windowed Blender with no events to process fires its timers about once a
    # second, whatever interval they ask for, so every tool there costs that
    # much. What a placement adds on top of the transport is the claim.
    baseline = []
    for _ in range(3):
        started = time.perf_counter()
        ok(tools["mpfb_list_objects"](), "list_objects")
        baseline.append(time.perf_counter() - started)
    FINDINGS["do_nothing_call_seconds"] = [round(value, 3) for value in baseline]
    check("a placement costs no more than a call that does nothing",
          sorted(timings)[1] <= sorted(baseline)[1] + 0.15,
          (FINDINGS["placement_call_seconds"], FINDINGS["do_nothing_call_seconds"]))

    boxes = [entry["placed"]["footprint"] for entry in built]
    check("the three stand edge to edge without overlapping",
          all(first["max"]["x"] <= second["min"]["x"] + 0.002
              for first, second in zip(boxes, boxes[1:])),
          [(box["min"]["x"], box["max"]["x"]) for box in boxes])
    FINDINGS["line_up"] = [dict(root=entry["placed"]["root_name"],
                                position=entry["placed"]["position_after"],
                                facing=entry["placed"]["facing_after"],
                                footprint=entry["placed"]["footprint"],
                                moved_with=entry["placed"]["moved_with"])
                           for entry in built]

    pony = built[0]
    check("ponytail01 dressed at the origin and then placed is not broken",
          pony["ponytail"]["subrigs_broken"] == [] and pony["placed"]["subrigs_broken"] == [],
          pony["placed"]["subrigs_broken"])
    hair = in_blender(HAIR_CODE.format(body=pony["name"],
                                       hair=pony["ponytail"]["asset_object_name"])).strip()
    check("and its hair really is on its head", float(hair) < 0.4, hair)
    check("the generated Rigify rig carried its hidden meta-rig",
          built[1]["placed"]["moved_with"] == [built[1]["generated"]["metarig_name"]],
          built[1]["placed"]["moved_with"])

    for entry in built:
        envelope = tools["mpfb_get_character_summary"](name=entry["name"])
        summary = ok(envelope, "summary")
        placed = entry["placed"]
        expected = dict(root_name=placed["root_name"], position=placed["position_after"],
                        facing=placed["facing_after"], tilted=placed["tilted"],
                        footprint=placed["footprint"],
                        subrigs_broken=placed["subrigs_broken"])
        size = len(json.dumps(envelope))
        check("the summary agrees with the place answer for " + entry["name"],
              summary["placement"] == expected, summary["placement"])
        check("the summary stays under 8 KB for " + entry["name"], size < 8192, size)
    return built


def camera_x(camera):
    return blender_json('print(json.dumps(list(bpy.data.objects[{!r}].matrix_world.'
                        'to_translation())))'.format(camera))[0]


def pose_invariance(tools, name):
    posed = ok(tools["mpfb_set_pose_bones"](name=name, bones=[
        {"bone": "upperarm01.L", "rotate_by": {"axis": {"forward": 1.0}, "degrees": -35.0}},
        {"bone": "head", "rotate_by": {"axis": {"up": 1.0}, "degrees": 12.0}}]), "pose")
    check("the pose was written", posed["performed"] is True, posed.get("resolution_errors"))
    before = ok(tools["mpfb_get_pose"](name=name), "get_pose")
    moved = ok(tools["mpfb_place_character"](name=name, position={"y": 1.5}, facing=-20.0),
               "move a posed character")
    after = ok(tools["mpfb_get_pose"](name=name), "get_pose")
    check("get_pose answers the same before and after a move",
          all(before[key] == after[key] for key in ("posed", "landmarks", "limbs", "at_rest")))
    back = ok(tools["mpfb_place_character"](**moved["restore_with"]["mpfb_place_character"]),
              "restore_with")
    check("restore_with puts the posed character back",
          back["position_after"] == moved["position_before"]
          and back["facing_after"] == moved["facing_before"],
          (back["position_after"], back["facing_after"]))
    ok(tools["mpfb_reset_pose"](name=name), "reset the pose")


# The furthest hair vertex from the head bone: about a quarter of a metre for a
# ponytail that hangs where it should.
HAIR_CODE = '''
import bpy
dg = bpy.context.evaluated_depsgraph_get()
body = bpy.data.objects[{body!r}]
hair = bpy.data.objects[{hair!r}]
head = body.parent.matrix_world @ body.parent.pose.bones["head"].head
evaluated = hair.evaluated_get(dg)
mesh = evaluated.to_mesh()
print(max(((evaluated.matrix_world @ v.co) - head).length for v in mesh.vertices))
evaluated.to_mesh_clear()
'''


def subrig_equipped_away_from_the_origin(tools):
    """ponytail01 equipped on a placed character, moved to the origin, then refitted."""
    name, _ = build(tools, {"gender": 0.2}, "default", [])
    ok(tools["mpfb_place_character"](name=name, position={"x": -4.0, "y": -4.0}, facing=60.0),
       "place before dressing")
    added = ok(tools["mpfb_add_asset"](name=name, fragment="ponytail01/ponytail01.mhclo",
                                       object_type="Hair"), "ponytail on a placed character")
    hair = added["asset_object_name"]

    def drag():
        return float(in_blender(HAIR_CODE.format(body=name, hair=hair)).strip())

    readings = dict(equipped_while_placed=drag())
    check("equipped on a placed character, ponytail01's sub-rig is reported broken",
          [record["asset_object_name"] for record in added["subrigs_broken"]] == [hair]
          and readings["equipped_while_placed"] > 1.0, (added["subrigs_broken"], readings))
    at_origin = ok(tools["mpfb_place_character"](name=name, position={"x": 0.0, "y": 0.0},
                                                 facing=0.0), "to the origin")
    readings["moved_to_the_origin"] = drag()
    check("moving it to the origin does not cure it, and it is still reported",
          len(at_origin["subrigs_broken"]) == 1 and readings["moved_to_the_origin"] > 1.0,
          readings)
    ok(tools["mpfb_refit_human"](name=name), "refit")
    moved = ok(tools["mpfb_place_character"](name=name, position={"x": 6.0, "y": -2.0},
                                             facing=-120.0), "move after the refit")
    readings["refitted_then_moved"] = drag()
    check("mpfb_refit_human re-binds it, and it then survives a move",
          moved["subrigs_broken"] == [] and readings["refitted_then_moved"] < 0.4, readings)
    FINDINGS["ponytail01_furthest_hair_vertex_from_the_head"] = {
        key: round(value, 3) for key, value in readings.items()}
    FINDINGS["ponytail01_displacement_reported"] = added["subrigs_broken"][0]["displacement"] \
        if added["subrigs_broken"] else None


def placed_generation(tools):
    """Requirement 17 for generation: a meta-rig placed first, then generated."""
    name, _ = build(tools, {"gender": 0.3}, "rigify.human_toes", [])
    placed = ok(tools["mpfb_place_character"](name=name, position={"x": -6.0, "y": -3.0},
                                               facing=-45.0), "place the meta-rig")
    generated = ok(tools["mpfb_generate_rigify_rig"](name=name), "generate in place")
    summary = ok(tools["mpfb_get_character_summary"](name=name), "summary")
    FINDINGS["generation_on_a_placed_metarig"] = dict(
        metarig_placement_moved_to_rig=generated["metarig_placement_moved_to_rig"],
        footprint_before=placed["footprint"], footprint_after=summary["placement"]["footprint"])
    check("a placed meta-rig generates a rig where the character stands",
          generated["metarig_placement_moved_to_rig"] is True
          and summary["placement"]["position"] == placed["position_after"]
          and summary["placement"]["facing"] == placed["facing_after"],
          summary["placement"])
    check("and the body did not move",
          all(abs(placed["footprint"]["min"][axis] - summary["placement"]["footprint"]["min"][axis])
              < 0.01 for axis in "xyz"))


def world_helpers(rig_name):
    """MPFB's location-only world helpers against a turned rig, and the OpenPose one."""
    found = blender_json('''
services = [m for n, m in sys.modules.items() if n.endswith("mpfb")][0].MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
RigService = services["RigService"]
rig = bpy.data.objects[{rig!r}]
bone = rig.pose.bones["lowerarm01.L"]
true_head = rig.matrix_world @ bone.head
true_tail = rig.matrix_world @ bone.tail
head = RigService.find_pose_bone_head_world_location("lowerarm01.L", rig)
tail = RigService.find_pose_bone_tail_world_location("lowerarm01.L", rig)
openpose = RigService.get_world_space_location_of_pose_bone("lowerarm01.L", rig)
print(json.dumps(dict(
    find_head_error=(head - true_head).length, find_tail_error=(tail - true_tail).length,
    openpose_head_error=(openpose["head"] - true_head).length,
    openpose_head_is_the_tail=(openpose["head"] - true_tail).length,
    rig_rotation_z=math.degrees(rig.matrix_world.to_euler().z))))
'''.format(rig=rig_name))
    FINDINGS["mpfb_world_helpers_on_a_turned_rig"] = found
    check("RigService.find_pose_bone_*_world_location ignore the rotation (filed, not used)",
          found["find_head_error"] > 0.05 and found["find_tail_error"] > 0.05, found)
    check("get_world_space_location_of_pose_bone uses the whole matrix (its swap aside)",
          found["openpose_head_is_the_tail"] < 1e-5, found)


def main():
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()
    camera = blender_json("print(json.dumps(bpy.context.scene.camera.name))")

    turned_rig = premise(tools)
    built = line_up(tools, camera)
    pose_invariance(tools, built[2]["name"])
    subrig_equipped_away_from_the_origin(tools)
    placed_generation(tools)
    world_helpers(turned_rig)

    print(json.dumps(FINDINGS, indent=1, sort_keys=True))
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
