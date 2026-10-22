# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 047's own live check: every hand shape on a placed character, driven with mpfb-mcp tools alone.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. It drives the **real mpfb-mcp
tools over the real socket**, against a Blender already running with the MPFB
Bridge's server started (``MPFB_BRIDGE_PORT``, default 9877), on the
developer's real install.

**Every character is built, placed and posed through mpfb-mcp.** The community
blender-mcp add-on's socket (``BLENDER_MCP_PORT``, default 9876) is used only
for what no tool reports and a check needs: where the palm's surface is
against a fingertip, a 4 cm cylinder to hold, and a workbench render of each
hand from the front and the side, written to the directory given as the first
argument (default: ``fr047_shots`` in the system temporary directory).

    PYTHONPATH=. .venv/bin/python feature-requests/done/047-rigify-hand-shapes/live_check.py [shots]

It adds two characters to the open scene and leaves them there: a ``human_toes``
character moved and turned away from the origin, and a ``human`` one beside it.

1. **Every shape on both hands** of the ``human_toes`` character, through
   ``symmetry``, read back as itself, every written finger ``achieved``, with
   requirement 18's acceptance measured: ``fist`` with every fingertip outside
   the palm (the tip bone's end against the palm's surface below its
   metacarpal), ``pinch`` with the thumb and index tips within 1 cm by
   ``tip``, ``grip`` with every fingertip and the thumb's within 1.2 cm of a
   4 cm cylinder's surface, ``pointing`` with every index joint under 5 degrees.
   Each shape is also rendered from the front and the side, to be looked at.
2. **The scene session's case in one call**: a loose curl on one hand and
   none on the other.
3. **``pointing`` as ``fist`` plus an override**.
4. **``restore_with``** puts a hand posed by hand (a bent segment, a hook)
   back exactly, after a shape overwrote it.
5. **A reset with ``mpfb_reset_pose`` on ``left_hand``** reads back as ``open``.
6. **The same shape rows on a generated ``human`` rig**, with the findings
   printed rather than failed: a miss there is a calibration finding.
7. **Cheap**: what each call costs and how big each answer is.

Prints PASS/FAIL per check, then the findings, and exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

BLENDER_MCP_PORT = int(os.environ.get("BLENDER_MCP_PORT", "9876"))
SHAPES = ("open", "relaxed", "fist", "pointing", "grip", "pinch")
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
HANDS = ("left_hand", "right_hand")

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


# Where the palm's surface is below each finger's metacarpal, read at rest:
# a ray from the palm side down onto the body, at the middle of the DEF-palm
# bone, and the fingertip's offset along the same normal now. A fingertip at
# least as far out as the surface is outside the palm. The normal is the way a
# curling finger goes, averaged over the four fingers.
PALM_CODE = '''
from mathutils.bvhtree import BVHTree
PALMS = {"index": 1, "middle": 2, "ring": 3, "pinky": 4}
TOKENS = {"index": "f_index", "middle": "f_middle", "ring": "f_ring", "pinky": "f_pinky"}
def body_bvh(body):
    masks = [m for m in body.modifiers if m.type == "MASK" and m.show_viewport]
    for m in masks: m.show_viewport = False
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg); me = ev.to_mesh()
        verts = [body.matrix_world @ v.co for v in me.vertices]
        bvh = BVHTree.FromPolygons(verts, [list(p.vertices) for p in me.polygons])
        ev.to_mesh_clear()
        return bvh
    finally:
        for m in masks: m.show_viewport = True
def palm_normal(rig, side):
    W = rig.matrix_world.to_3x3(); P = rig.pose.bones
    n = Vector()
    for finger, k in PALMS.items():
        palm = P["ORG-palm.0%d.%s" % (k, side)]
        master = P[TOKENS[finger] + ".01_master." + side]
        rest = palm.bone.matrix_local.to_3x3().inverted() @ master.bone.matrix_local.to_3x3()
        axes = W @ palm.matrix.to_3x3() @ rest
        n += axes.col[2].normalized()
    return n.normalized()
def metacarpal(rig, finger, side):
    W = rig.matrix_world; pal = rig.pose.bones["DEF-palm.0%d.%s" % (PALMS[finger], side)]
    return W @ pal.head, W @ pal.tail
def surfaces(rig, body, side):
    bvh = body_bvh(body); n = palm_normal(rig, side); out = {}
    for finger in PALMS:
        a, b = metacarpal(rig, finger, side); mid = (a + b) / 2
        hit = bvh.ray_cast(mid + n * 0.06, -n)[0]
        out[finger] = (hit - mid).dot(n)
    return out
def clearances(rig, side, surface):
    W = rig.matrix_world; n = palm_normal(rig, side); out = {}
    for finger in PALMS:
        a, b = metacarpal(rig, finger, side); ab = b - a
        tip = W @ rig.pose.bones["DEF-%s.03.%s" % (TOKENS[finger], side)].tail
        t = max(0.0, min(1.0, (tip - a).dot(ab) / ab.length_squared))
        out[finger] = round(((tip - (a + ab * t)).dot(n) - surface[finger]) * 1000, 1)
    return out
'''

# A 4 cm cylinder across the palm, against its surface at the knuckle end, as
# FR 047's calibration placed it.
CYLINDER_CODE = '''
def cylinder(rig, body, side, name):
    W = rig.matrix_world; P = rig.pose.bones
    n = palm_normal(rig, side)
    a = W @ P["f_index.01_master." + side].head; b = W @ P["f_pinky.01_master." + side].head
    mid = (a + b) / 2
    hit = body_bvh(body).ray_cast(mid + n * 0.06, -n)[0]
    surface = (hit - mid).dot(n)
    along = ((W @ P["DEF-palm.02." + side].tail) - (W @ P["DEF-palm.02." + side].head)).normalized()
    p0 = a + n * (surface + 0.02) - along * 0.015; p1 = b + n * (surface + 0.02) - along * 0.015
    existing = bpy.data.objects.get(name)
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)
    mesh = bpy.data.meshes.new(name)
    import bmesh
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=0.02,
                                            radius2=0.02, depth=0.12); bm.to_mesh(mesh); bm.free()
    obj = bpy.data.objects.new(name, mesh); bpy.context.scene.collection.objects.link(obj)
    obj.location = (p0 + p1) / 2
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference((p1 - p0).normalized())
    return p0, p1
'''

# A workbench render of one hand, from in front of the character and from its
# side, through a temporary camera. The scene's own camera and engine are put
# back afterwards.
RENDER_CODE = '''
def render_hand(rig, side, path_stem):
    scene = bpy.context.scene
    W = rig.matrix_world
    centre = W @ rig.pose.bones["DEF-palm.02." + side].tail
    forward = (W.to_3x3() @ Vector((0, -1, 0))).normalized()
    left = (W.to_3x3() @ Vector((1, 0, 0))).normalized()
    outward = left if side == "L" else -left
    cam_data = bpy.data.cameras.new("FR047_cam"); cam_data.lens = 85
    cam = bpy.data.objects.new("FR047_cam", cam_data); scene.collection.objects.link(cam)
    saved = (scene.camera, scene.render.engine, scene.render.resolution_x,
             scene.render.resolution_y, scene.render.filepath, rig.hide_render)
    def family(obj):
        while obj is not None:
            if obj == rig:
                return True
            obj = obj.parent
        return False
    # Only this character and the cylinder it holds: other characters may stand
    # in the same place, from an earlier run.
    others = [obj for obj in scene.objects if obj.type == "MESH" and not obj.hide_render
              and not family(obj) and not obj.name.startswith("FR047_cylinder")]
    paths = []
    try:
        for obj in others:
            obj.hide_render = True
        scene.camera = cam
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x = scene.render.resolution_y = 480
        rig.hide_render = True
        for view, direction in (("front", forward), ("side", outward)):
            cam.location = centre + direction * 0.45
            cam.rotation_mode = "QUATERNION"
            cam.rotation_quaternion = (-direction).to_track_quat("-Z", "Y")
            scene.render.filepath = path_stem + "_" + view + ".png"
            bpy.ops.render.render(write_still=True)
            paths.append(scene.render.filepath)
    finally:
        (scene.camera, scene.render.engine, scene.render.resolution_x,
         scene.render.resolution_y, scene.render.filepath, rig.hide_render) = saved
        for obj in others:
            obj.hide_render = False
        bpy.data.objects.remove(cam, do_unlink=True); bpy.data.cameras.remove(cam_data)
    return paths
'''


def build(tools, rig_identifier, position, facing):
    """A character rigged with a generated Rigify rig, placed; returns its basemesh name."""
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    added = ok(tools["mpfb_add_rig"](name=name, identifier=rig_identifier), "add_rig")
    ok(tools["mpfb_generate_rigify_rig"](name=added["rig_object_name"]), "generate")
    ok(tools["mpfb_set_skin"](name=name, skin_type="LAYERED"), "skin")
    ok(tools["mpfb_place_character"](name=name, position=position, facing=facing), "place")
    return name


def timed(tool, **arguments):
    started = time.perf_counter()
    envelope = tool(**arguments)
    return envelope, time.perf_counter() - started


def shape_rows(tools, name, shots, label):
    """Every shape on both hands; returns ``{shape: findings}``."""
    rig = ok(tools["mpfb_get_rigify_hand_shape"](name=name), "read")["rig_object_name"]
    surfaces = blender_json(PALM_CODE + '''
rig = bpy.data.objects[{rig!r}]; body = bpy.data.objects[{body!r}]
print(json.dumps({{side: surfaces(rig, body, side) for side in "LR"}}))
'''.format(rig=rig, body=name))
    results = {}
    for shape in SHAPES:
        written = ok(tools["mpfb_set_rigify_hand_shape"](name=name, hands=[
            {"body_part": "left_hand", "shape": shape, "symmetry": True}]), "shape " + shape)
        read = ok(tools["mpfb_get_rigify_hand_shape"](name=name), "read " + shape)["hands"]
        findings = {"matches": [read[hand]["matches_shape"] for hand in HANDS],
                    "achieved": all(finger["achieved"] for hand in written["hands"]
                                    for finger in hand["fingers_after"].values())}
        if shape == "fist":
            findings["clearance_mm"] = blender_json(PALM_CODE + '''
rig = bpy.data.objects[{rig!r}]
surface = {surfaces!r}
print(json.dumps({{side: clearances(rig, side, surface[side]) for side in "LR"}}))
'''.format(rig=rig, surfaces=surfaces))
        if shape == "pinch":
            findings["pinch_mm"] = []
            for hand in HANDS:
                thumb = read[hand]["fingers"]["thumb"]["tip"]
                index = read[hand]["fingers"]["index"]["tip"]
                findings["pinch_mm"].append(round(1000 * sum(
                    (thumb[axis] - index[axis]) ** 2 for axis in thumb) ** 0.5, 1))
        if shape == "pointing":
            findings["index_joints"] = [read[hand]["fingers"]["index"]["joint_degrees"]
                                        for hand in HANDS]
        if shape == "grip":
            findings["grip_surface_mm"] = blender_json(PALM_CODE + CYLINDER_CODE + '''
from mathutils.geometry import intersect_point_line
rig = bpy.data.objects[{rig!r}]; body = bpy.data.objects[{body!r}]
out = {{}}
for side in "LR":
    p0, p1 = cylinder(rig, body, side, "FR047_cylinder_{label}_" + side)
    gaps = {{}}
    for finger, token in (("thumb", "thumb"), ("index", "f_index"), ("middle", "f_middle"),
                          ("ring", "f_ring"), ("pinky", "f_pinky")):
        tip = rig.matrix_world @ rig.pose.bones["DEF-%s.03.%s" % (token, side)].tail
        point, _ = intersect_point_line(tip, p0, p1)
        gaps[finger] = round(((tip - point).length - 0.02) * 1000, 1)
    out[side] = gaps
print(json.dumps(out))
'''.format(rig=rig, body=name, label=label))
        if shots:
            findings["renders"] = blender_json(RENDER_CODE + '''
rig = bpy.data.objects[{rig!r}]
print(json.dumps([render_hand(rig, side, {stem!r} + "_" + side) for side in "LR"]))
'''.format(rig=rig, stem=os.path.join(shots, "{:s}_{:s}".format(label, shape))))
        # The cylinder is for the grip alone, measured and rendered with it.
        blender_json('''
for obj in [obj for obj in bpy.data.objects if obj.name.startswith("FR047_cylinder")]:
    bpy.data.objects.remove(obj, do_unlink=True)
print(json.dumps(True))
''')
        results[shape] = findings
    ok(tools["mpfb_set_rigify_hand_shape"](name=name, hands=[
        {"body_part": "left_hand", "shape": "open", "symmetry": True}]), "back to open")
    return results


def acceptance(results, label, strict):
    """Requirement 18 per shape; ``strict`` fails a miss, otherwise it is a finding."""
    report = check if strict else (lambda what, condition, detail="": FINDINGS.setdefault(
        "{:s} acceptance".format(label), []).append(
            "{:s}: {:s} {!s}".format("met" if condition else "MISSED", what, detail)))
    for shape, findings in results.items():
        report("{:s} {:s} reads back as itself on both hands".format(label, shape),
               findings["matches"] == [shape, shape], findings["matches"])
        report("{:s} {:s}: every written finger achieved".format(label, shape),
               findings["achieved"])
    fist = results["fist"]["clearance_mm"]
    report("{:s} fist: no fingertip inside the palm".format(label),
           all(value >= 0.0 for side in fist.values() for value in side.values()), fist)
    report("{:s} pinch: thumb and index tips within 1 cm".format(label),
           all(value < 10.0 for value in results["pinch"]["pinch_mm"]),
           results["pinch"]["pinch_mm"])
    report("{:s} pointing: every index joint under 5 degrees".format(label),
           all(abs(value) < 5.0 for joints in results["pointing"]["index_joints"]
               for value in joints), results["pointing"]["index_joints"])
    grip = results["grip"]["grip_surface_mm"]
    report("{:s} grip: every fingertip within 12 mm of the 4 cm cylinder's surface".format(label),
           all(abs(value) <= 12.0 for side in grip.values() for value in side.values()), grip)


def scene_session(tools, name):
    """A loose curl on one hand and none on the other, in one call."""
    envelope, seconds = timed(tools["mpfb_set_rigify_hand_shape"], name=name, hands=[
        {"body_part": "left_hand", "fingers": {finger: {"curl": 0.4} for finger in FINGERS}},
        {"body_part": "right_hand", "shape": "open"}])
    answer = ok(envelope, "scene session")
    read = ok(tools["mpfb_get_rigify_hand_shape"](name=name), "read")["hands"]
    check("the scene session's case is one call: left loosely curled, right open",
          all(read["left_hand"]["fingers"][finger]["curl"] == 0.4 for finger in FINGERS)
          and read["right_hand"]["matches_shape"] == "open", "{:.2f} s".format(seconds))
    del answer


def pointing_by_override(tools, name):
    answer = ok(tools["mpfb_set_rigify_hand_shape"](name=name, hands=[
        {"body_part": "right_hand", "shape": "fist", "fingers": {"index": {"curl": 0.0}}}]),
        "fist plus override")
    check("fist plus an index override is pointing",
          answer["hands"][0]["matches_shape_after"] == "pointing")


def restore_round_trip(tools, name):
    """A hand posed by hand, overwritten by a shape, then put back by restore_with."""
    ok(tools["mpfb_set_rigify_hand_shape"](name=name, hands=[
        {"body_part": "left_hand", "fingers": {"ring": {"curl": 0.35, "spread": -0.4}}}]), "ring")
    ok(tools["mpfb_set_pose_bones"](name=name, bones=[
        {"bone": "f_index.02.L", "rotate_by": {"axis": {"left": 1.0}, "degrees": 20.0}},
        {"bone": "f_middle.01_master.L", "scale_to": {"y": 0.6}}]), "pose by hand")
    before = ok(tools["mpfb_get_rigify_hand_shape"](name=name), "read")["hands"]["left_hand"]
    written, seconds = timed(tools["mpfb_set_rigify_hand_shape"], name=name, hands=[
        {"body_part": "left_hand", "shape": "grip", "symmetry": True}])
    answer = ok(written, "grip over it")
    FINDINGS["two-hand write with restore_with"] = "{:d} B, {:.2f} s".format(
        len(json.dumps(answer)), seconds)
    restore = answer["restore_with"]
    check("restore_with is the two calls, hand shape first",
          list(restore) == ["mpfb_set_rigify_hand_shape", "mpfb_set_pose_bones"], list(restore))
    ok(tools["mpfb_set_rigify_hand_shape"](**restore["mpfb_set_rigify_hand_shape"]), "restore 1")
    ok(tools["mpfb_set_pose_bones"](**restore["mpfb_set_pose_bones"]), "restore 2")
    after = ok(tools["mpfb_get_rigify_hand_shape"](name=name), "read")["hands"]["left_hand"]
    check("restore_with puts the hand posed by hand back", after["fingers"] == before["fingers"],
          {finger: (before["fingers"][finger]["joint_degrees"],
                    after["fingers"][finger]["joint_degrees"])
           for finger in FINGERS if after["fingers"][finger] != before["fingers"][finger]})


def reset_reads_open(tools, name):
    ok(tools["mpfb_set_rigify_hand_shape"](name=name, hands=[
        {"body_part": "left_hand", "shape": "fist"}]), "fist")
    ok(tools["mpfb_reset_pose"](name=name, body_parts=["left_hand"]), "reset")
    read = ok(tools["mpfb_get_rigify_hand_shape"](name=name, body_parts=["left_hand"]), "read")
    check("mpfb_reset_pose on left_hand reads back as open",
          read["hands"]["left_hand"]["matches_shape"] == "open")


def costs(tools, name):
    nothing, idle = timed(tools["mpfb_get_status"])
    read, reading = timed(tools["mpfb_get_rigify_hand_shape"], name=name)
    FINDINGS["reader"] = "{:d} B, {:.2f} s (mpfb_get_status {:.2f} s)".format(
        len(json.dumps(ok(read, "read"))), reading, idle)
    del nothing


def main():
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()
    shots = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(),
                                                               "fr047_shots")
    os.makedirs(shots, exist_ok=True)

    toes = build(tools, "rigify.human_toes", {"x": -2.5, "y": 1.5}, 35.0)
    FINDINGS["human_toes character"] = toes
    acceptance(shape_rows(tools, toes, shots, "human_toes"), "human_toes", strict=True)
    scene_session(tools, toes)
    pointing_by_override(tools, toes)
    restore_round_trip(tools, toes)
    reset_reads_open(tools, toes)
    costs(tools, toes)
    ok(tools["mpfb_reset_pose"](name=toes), "reset")

    human = build(tools, "rigify.human", {"x": -4.0, "y": 1.5}, 35.0)
    FINDINGS["human character"] = human
    acceptance(shape_rows(tools, human, shots, "human"), "human", strict=False)
    ok(tools["mpfb_reset_pose"](name=human), "reset")

    FINDINGS["renders"] = shots
    print("\nFindings:")
    print(json.dumps(FINDINGS, indent=1))
    print("\n{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
