# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 041's own live check: the two posing reads on a real install, in a windowed Blender.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. It drives the **real mpfb-mcp
tools over the real socket**, against a Blender that is already running with
the MPFB Bridge's server started (``MPFB_BRIDGE_PORT``, default 9877).

**Posing goes through a second add-on, on purpose.** The bridge executes
nothing a caller sends, and FR 041 adds no command that changes a pose (that is
FR 042's). The request asked for the karate session's poses to be made
"through ``execute_blender_code``", the way that session made them, so this
script sends its posing code to the community blender-mcp add-on's socket
(``BLENDER_MCP_PORT``, default 9876) - the mechanism behind that tool. That
add-on must be running in the same Blender.

    PYTHONPATH=. .venv/bin/python feature-requests/done/041-pose-controls-and-read-back/live_check.py

It adds two characters to the open scene and leaves them there.

1. **The karate session's starting point**: a generated ``human_toes``
   character, moved and turned away from the origin. Every bone that session
   moved by hand must be a control with the role it was used for, and the
   frame's ``forward`` must be where the turned rig object faces.
2. **The pose**: fists made by scaling the finger masters on Y, hands placed in
   front of the chest in the character frame, then the hips lowered. The fists
   must be posed (by scale alone), the hands must be left in the air when the
   hips go down (``IK_parent`` is ``Root``), and the arms must be reported
   stretched - what the session found only by looking.
3. **Read-only**: mode, active object, selection and the pose, before and after.
4. **Sizes**, against the 8 KB line for ``mpfb_get_pose``, and the controls
   answer measured so its ceiling can be written down.
5. **A generated game_engine rig**, measured once: does it classify with no
   bone collections and ``_l``/``_r`` sides.

Prints PASS/FAIL per check and exits non-zero on any failure.
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

# Where the character is placed: away from the origin and turned 120 degrees,
# so that forward is neither world -Y nor any other world axis.
PLACEMENT = {"location": (1.5, -2.0, 0.0), "turn_degrees": 120.0}

# The hands, in the character frame, in front of the chest; and how far the
# hips are lowered. Deep enough that a hand left in the air is out of reach.
HANDS = {"hand_ik.L": {"forward": 0.40, "left": 0.17, "up": 1.30},
         "hand_ik.R": {"forward": 0.40, "left": -0.17, "up": 1.30}}
HIPS_DOWN = 0.40

# The bones the karate session moved by hand, and the role it used each for.
KARATE_BONES = {
    "torso": ("torso", "body"), "hips": ("torso", "body"), "chest": ("torso", "body"),
    "neck": ("head", "fk"), "head": ("head", "fk"),
    "hand_ik.L": ("left_arm", "ik_control"), "hand_ik.R": ("right_arm", "ik_control"),
    "upper_arm_ik_target.L": ("left_arm", "pole"), "upper_arm_ik_target.R": ("right_arm", "pole"),
    "foot_ik.L": ("left_leg", "ik_control"), "foot_ik.R": ("right_leg", "ik_control"),
    "f_index.01_master.L": ("left_hand", "finger_master"),
    "thumb.01_master.L": ("left_hand", "finger_master"),
    "f_pinky.01_master.R": ("right_hand", "finger_master"),
}
FINGER_MASTERS = ("f_index.01_master", "f_middle.01_master", "f_ring.01_master",
                  "f_pinky.01_master", "thumb.01_master")

POSE_LINE = 8 * 1024

FAILURES = []


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
    with socket.create_connection(("127.0.0.1", BLENDER_MCP_PORT), timeout=60) as connection:
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


def build_karate_character(tools):
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    ok(tools["mpfb_add_rig"](name=name, identifier="rigify.human_toes"), "add_rig")
    generated = ok(tools["mpfb_generate_rigify_rig"](name=name), "generate_rigify_rig")
    check("Rigify generated the human_toes meta-rig", generated["generated"] is True,
          generated["message"])
    rig = generated["rig_object_name"]
    in_blender(
        "import math\n"
        "rig = bpy.data.objects[{rig!r}]\n"
        "rig.location = {location!r}\n"
        "rig.rotation_euler = (0.0, 0.0, math.radians({turn!r}))\n"
        "bpy.context.view_layer.update()\n".format(
            rig=rig, location=PLACEMENT["location"], turn=PLACEMENT["turn_degrees"]))
    return name, rig


def check_controls(tools, name):
    started = time.perf_counter()
    envelope = tools["mpfb_get_pose_controls"](name=name)
    elapsed = time.perf_counter() - started
    answer = ok(envelope, "get_pose_controls")
    controls = {entry["bone"]: (part, entry["role"])
                for part, entries in answer["controls"].items() for entry in entries}
    wrong = {bone: controls.get(bone) for bone, expected in KARATE_BONES.items()
             if controls.get(bone) != expected}
    check("every bone the karate session moved is a control with the role it used",
          not wrong, wrong)
    check("nothing on the generated rig fits no body part", answer["unassigned_bones"] == [],
          answer["unassigned_bones"])

    import math  # pylint: disable=import-outside-toplevel
    turn = math.radians(PLACEMENT["turn_degrees"])
    # Local -Y turned about up: (sin t, -cos t, 0).
    expected_forward = [round(math.sin(turn), 3), round(-math.cos(turn), 3), 0.0]
    check("forward is where the turned rig object faces",
          answer["character_frame"]["forward"] == expected_forward,
          (answer["character_frame"]["forward"], expected_forward))
    check("the origin is the rig object's",
          answer["character_frame"]["origin"] == list(PLACEMENT["location"]),
          answer["character_frame"]["origin"])
    hand = [entry for entry in answer["controls"]["left_arm"] if entry["bone"] == "hand_ik.L"][0]
    check("the left hand rests on the character's left, whatever the turn",
          hand["head"]["left"] > 0.3, hand["head"])

    every_part = ["root", "torso", "head", "face", "left_arm", "right_arm", "left_hand",
                  "right_hand", "left_leg", "right_leg"]
    whole = len(json.dumps(envelope))
    with_face = len(json.dumps(tools["mpfb_get_pose_controls"](name=name, body_parts=every_part)))
    arms = len(json.dumps(tools["mpfb_get_pose_controls"](
        name=name, body_parts=["left_arm", "right_arm"])))
    print("controls answer: default {:d} B, every part {:d} B, two arms {:d} B, "
          "{:.0f} ms".format(whole, with_face, arms, elapsed * 1000))
    return answer


def pose_hands_and_fists(rig):
    in_blender(
        "from mathutils import Vector\n"
        "rig = bpy.data.objects[{rig!r}]\n"
        "axes = rig.matrix_world.to_3x3()\n"
        "frame = {{'forward': axes @ Vector((0, -1, 0)), 'left': axes @ Vector((1, 0, 0)),\n"
        "         'up': axes @ Vector((0, 0, 1))}}\n"
        "for bone, where in {hands!r}.items():\n"
        "    world = rig.matrix_world.to_translation().copy()\n"
        "    for axis, value in where.items():\n"
        "        world += frame[axis].normalized() * value\n"
        "    bpy.context.view_layer.update()\n"
        "    pose_bone = rig.pose.bones[bone]\n"
        "    matrix = pose_bone.matrix.copy()\n"
        "    matrix.translation = rig.matrix_world.inverted() @ world\n"
        "    pose_bone.matrix = matrix\n"
        "for side in ('.L', '.R'):\n"
        "    for master in {masters!r}:\n"
        "        y = 0.7 if master.startswith('thumb') else 0.45\n"
        "        rig.pose.bones[master + side].scale = (1.0, y, 1.0)\n"
        "bpy.context.view_layer.update()\n".format(
            rig=rig, hands=HANDS, masters=FINGER_MASTERS))


def lower_hips(rig):
    in_blender(
        "rig = bpy.data.objects[{rig!r}]\n"
        "bpy.context.view_layer.update()\n"
        "torso = rig.pose.bones['torso']\n"
        "matrix = torso.matrix.copy()\n"
        "matrix.translation.z -= {down!r} / rig.matrix_world.to_scale().z\n"
        "torso.matrix = matrix\n"
        "bpy.context.view_layer.update()\n".format(rig=rig, down=HIPS_DOWN))


def blender_state(rig):
    return json.loads(in_blender(
        "import json\n"
        "rig = bpy.data.objects[{rig!r}]\n"
        "active = bpy.context.view_layer.objects.active\n"
        "print(json.dumps({{'mode': bpy.context.mode, 'active': active and active.name,\n"
        "  'selected': sorted(o.name for o in bpy.context.selected_objects),\n"
        "  'pose': [[pb.name, [round(v, 6) for v in (*pb.location, *pb.rotation_quaternion,\n"
        "            *pb.rotation_euler, *pb.scale)]] for pb in rig.pose.bones]}}))\n".format(
                rig=rig)))


def check_pose(tools, name, rig):
    at_rest = ok(tools["mpfb_get_pose"](name=name), "get_pose")
    check("the freshly generated, moved rig is at rest", at_rest["at_rest"] is True,
          at_rest["message"])

    pose_hands_and_fists(rig)
    before_hips = ok(tools["mpfb_get_pose"](name=name), "get_pose")
    fists = [entry for entry in before_hips["posed"]["left_hand"]
             if entry["role"] == "finger_master"]
    check("the fists are posed, by scale alone", len(fists) == 5 and all(
        entry["scale"] is not None and entry["scale"]["y"] < 1.0 for entry in fists),
        [entry["scale"] for entry in fists])
    hand_now = before_hips["landmarks"]["left_hand"]["now"]
    check("the left hand is where it was put, in the character frame",
          abs(hand_now["forward"] - HANDS["hand_ik.L"]["forward"]) < 0.01
          and abs(hand_now["up"] - HANDS["hand_ik.L"]["up"]) < 0.01, hand_now)
    check("the arms reach their hands before the hips go down",
          not any(before_hips["limbs"][arm]["stretched"] for arm in ("left_arm", "right_arm")),
          {arm: before_hips["limbs"][arm] for arm in ("left_arm", "right_arm")})

    lower_hips(rig)
    started = time.perf_counter()
    envelope = tools["mpfb_get_pose"](name=name)
    elapsed = time.perf_counter() - started
    after = ok(envelope, "get_pose")
    torso = [entry for entry in after["posed"]["torso"] if entry["bone"] == "torso"]
    check("the torso is reported lowered", torso and abs(
        torso[0]["moved_by"]["up"] + HIPS_DOWN) < 0.01, torso)
    hips = after["landmarks"]["hips"]
    check("the hips landmark went down with it",
          abs(hips["now"]["up"] - (before_hips["landmarks"]["hips"]["now"]["up"] - HIPS_DOWN))
          < 0.01, hips)
    check("the fists are left in the air: the hands did not follow the hips",
          abs(after["landmarks"]["left_hand"]["now"]["up"] - hand_now["up"]) < 0.01,
          (after["landmarks"]["left_hand"]["now"], hand_now))
    check("IK_parent is Root, which is why",
          after["switch_parents"]["left_arm"]["IK_parent"] == "Root",
          after["switch_parents"]["left_arm"])
    stretched = {arm: after["limbs"][arm] for arm in ("left_arm", "right_arm")}
    check("the arms are reported stretched, as the session found by looking",
          all(limb["stretched"] and limb["reach_ratio"] > 1.0 for limb in stretched.values()),
          stretched)
    print("message: {:s}".format(after["message"]))
    state_before = blender_state(rig)
    tools["mpfb_get_pose"](name=name)
    tools["mpfb_get_pose_controls"](name=name)
    check("reading changes nothing: mode, active object, selection and pose",
          blender_state(rig) == state_before)

    size = len(json.dumps(envelope))
    posed = after["posed_count"]
    print("pose answer: {:d} B for {:d} posed controls, {:.0f} ms".format(
        size, posed, elapsed * 1000))
    check("the pose read-back is within about 8 KB for this pose", size <= POSE_LINE * 1.05,
          size)


def check_game_engine(tools):
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    added = ok(tools["mpfb_add_rig"](name=name, identifier="game_engine"), "add_rig")
    rig = added["rig_object_name"]
    in_blender(
        "rig = bpy.data.objects[{rig!r}]\n"
        "for other in bpy.context.view_layer.objects: other.select_set(False)\n"
        "bpy.context.view_layer.objects.active = rig\n"
        "rig.select_set(True)\n"
        "bpy.ops.mpfb.convert_to_rigify()\n".format(rig=rig))
    envelope = tools["mpfb_get_pose_controls"](name=name)
    answer = ok(envelope, "get_pose_controls")
    check("MPFB's convert-to-Rigify produced a generated game_engine rig",
          answer.get("rig_identified_as") == "rigify_generated.game_engine",
          answer.get("rig_identified_as"))
    check("it is classified with no bone collections to read", answer.get("classified") is True
          and answer.get("unassigned_bones") == [], answer.get("unassigned_bones"))
    counts = answer.get("counts_by_body_part") or {}
    check("both sides of every limb have controls", all(
        counts.get(part, 0) > 0 for part in ("left_arm", "right_arm", "left_hand",
                                             "right_hand", "left_leg", "right_leg")), counts)
    print("game_engine controls answer: {:d} B, counts {!r}".format(len(json.dumps(envelope)),
                                                                   counts))


def main():
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()
    name, rig = build_karate_character(tools)
    print("character {!r} on rig {!r}".format(name, rig))
    check_controls(tools, name)
    check_pose(tools, name, rig)
    check_game_engine(tools)
    print()
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
