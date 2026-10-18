# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 042's own live check: the karate stance rebuilt with mpfb-mcp tools only, in a windowed Blender.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. It drives the **real mpfb-mcp
tools over the real socket**, against a Blender that is already running with
the MPFB Bridge's server started (``MPFB_BRIDGE_PORT``, default 9877).

**Every pose change goes through mpfb-mcp.** The community blender-mcp add-on's
socket (``BLENDER_MCP_PORT``, default 9876) is used for three things that are
not posing: placing the rig object away from the origin, MPFB's legacy
convert-to-Rigify operator for the game_engine rig, and reading Blender's own
state to compare against - plus, for the worst-case measurement only, posing
every control at once, which is a size to measure rather than a stance to make.

    PYTHONPATH=. .venv/bin/python feature-requests/done/042-posing-bones-switches-and-reset/live_check.py

It adds two characters to the open scene and leaves them there.

1. **The karate stance**, on a generated ``human_toes`` character moved and
   turned away from the origin: the fists' parent switched to the torso
   (snapped) and the poles turned on (snapped), stretch turned off, closed
   fists by ``scale_to``, a guard placed in the character frame, the elbows
   brought in, the hips lowered with the fists following, and a stance in the
   feet. The arms must not be stretched, every write must be achieved, and the
   read-back must say all of it.
2. **Cost**: a 30-bone batch timed and measured, every answer's size.
3. **The way back**: a reset with switches, then its ``restore_with`` fed to the
   two writers, and Blender's own channels compared before and after.
4. **The worst case** for ``restore_with``: every control posed, face included.
5. **A generated game_engine rig**: IK to FK and back, snapped.
6. **Nothing borrowed**: mode, active object and selection across a write.

The screenshot comparison is made by the person running this, from the rig name
and the read-back it prints. Prints PASS/FAIL per check and exits non-zero on
any failure.
"""

from __future__ import annotations

import json
import math
import os
import socket
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

BLENDER_MCP_PORT = int(os.environ.get("BLENDER_MCP_PORT", "9876"))

PLACEMENT = {"location": (-2.0, 1.5, 0.0), "turn_degrees": 150.0}

# The guard, in the character frame: the left fist forward, the right at the chin.
GUARD = {"hand_ik.L": {"forward": 0.42, "left": 0.12, "up": 1.32},
         "hand_ik.R": {"forward": 0.22, "left": -0.12, "up": 1.40}}
HIPS_DOWN = 0.25
FINGER_MASTERS = ("f_index.01_master.L", "f_middle.01_master.L", "f_ring.01_master.L",
                  "f_pinky.01_master.L")
POSE_LINE = 8 * 1024
MM = 0.001

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


def timed(tool, **arguments):
    started = time.perf_counter()
    envelope = tool(**arguments)
    return envelope, (time.perf_counter() - started) * 1000, len(json.dumps(envelope))


def in_blender(code):
    """Run ``code`` in the running Blender through the community add-on; returns its stdout."""
    with socket.create_connection(("127.0.0.1", BLENDER_MCP_PORT), timeout=120) as connection:
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


def blender_state(rig):
    return json.loads(in_blender(
        "import json\n"
        "rig = bpy.data.objects[{rig!r}]\n"
        "active = bpy.context.view_layer.objects.active\n"
        "def q(pb):\n"
        "    v = list(pb.rotation_quaternion)\n"
        "    return [-x for x in v] if v[0] < 0 else v\n"
        "print(json.dumps({{'mode': bpy.context.mode, 'active': active and active.name,\n"
        "  'selected': sorted(o.name for o in bpy.context.selected_objects),\n"
        "  'pose': {{pb.name: [*pb.location, *q(pb), *pb.rotation_euler, *pb.scale]\n"
        "           for pb in rig.pose.bones}},\n"
        "  'switches': {{pb.name: {{k: float(pb[k]) for k in pb.keys()\n"
        "               if isinstance(pb[k], (bool, int, float))}} for pb in rig.pose.bones}}}}))\n"
        .format(rig=rig)))


def build_character(tools):
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    ok(tools["mpfb_add_rig"](name=name, identifier="rigify.human_toes"), "add_rig")
    generated = ok(tools["mpfb_generate_rigify_rig"](name=name), "generate_rigify_rig")
    rig = generated["rig_object_name"]
    in_blender(
        "import math\n"
        "rig = bpy.data.objects[{rig!r}]\n"
        "rig.location = {location!r}\n"
        "rig.rotation_euler = (0.0, 0.0, math.radians({turn!r}))\n"
        "bpy.context.view_layer.update()\n".format(
            rig=rig, location=PLACEMENT["location"], turn=PLACEMENT["turn_degrees"]))
    return name, rig


def snapped_within_a_millimetre(answer, what):
    errors = [(c["body_part"], c["switch"], c.get("snap_error")) for c in answer["changes"]]
    check(what, all(c["snapped"] and c["snap_error"] < MM for c in answer["changes"]), errors)


def karate(tools, name):
    controls = ok(tools["mpfb_get_pose_controls"](name=name, body_parts=["left_arm"]),
                  "get_pose_controls")
    parents = next(s for s in controls["switches"] if s["switch"] == "IK_parent")["parent_names"]
    torso = parents.index("Torso")
    print("IK_parent names: {!r}; Torso is {:d}".format(parents, torso))

    # The switches first, snapped: the fists follow the torso, the poles aim the elbows.
    answer = ok(tools["mpfb_set_pose_switches"](name=name, switches=[
        {"body_part": side, "switch": switch, "value": value}
        for side in ("left_arm", "right_arm")
        for switch, value in (("IK_parent", torso), ("pole_vector", True))]),
        "set_pose_switches")
    snapped_within_a_millimetre(answer, "IK_parent to Torso and the poles on keep the arms put")
    answer = ok(tools["mpfb_set_pose_switches"](name=name, switches=[
        {"body_part": side, "switch": "IK_Stretch", "value": 0.0}
        for side in ("left_arm", "right_arm")]), "set_pose_switches")
    check("IK_Stretch has no snap and says so",
          all(not c["snapped"] and "no snap" in c["snap_reason"] for c in answer["changes"]))

    # Fists, the guard and the elbows in, as one batch.
    bones = [{"bone": master, "scale_to": {"y": 0.45}, "symmetry": True}
             for master in FINGER_MASTERS]
    bones.append({"bone": "thumb.01_master.L", "scale_to": {"y": 0.7}, "symmetry": True})
    bones += [{"bone": bone, "move_to": where} for bone, where in GUARD.items()]
    bones.append({"bone": "upper_arm_ik_target.L", "move_by": {"left": -0.15, "up": -0.1},
                  "symmetry": True})
    envelope, ms, size = timed(tools["mpfb_set_pose_bones"], name=name, bones=bones)
    answer = ok(envelope, "set_pose_bones")
    print("guard batch: {:d} changes, {:.0f} ms, {:d} B".format(answer["change_count"], ms, size))
    check("every guard write is achieved", all(c["achieved"] for c in answer["changes"]),
          [(c["bone"], c.get("deviation")) for c in answer["changes"] if not c["achieved"]])
    check("the mirrored fists are reported as their own changes",
          sum(1 for c in answer["changes"] if c.get("mirrored_from")) == 6)
    hands_before = {side: answer["landmarks"][side]["after"] for side in ("left_hand",
                                                                          "right_hand")}
    check("the arms reach the guard without stretching",
          not answer["limbs"]["left_arm"]["stretched"]
          and not answer["limbs"]["right_arm"]["stretched"],
          {arm: answer["limbs"][arm] for arm in ("left_arm", "right_arm")})

    # The hips down and the feet apart; the fists follow the torso now.
    envelope, ms, size = timed(tools["mpfb_set_pose_bones"], name=name, bones=[
        {"bone": "torso", "move_by": {"up": -HIPS_DOWN}},
        {"bone": "foot_ik.L", "move_by": {"forward": 0.3, "left": 0.05}},
        {"bone": "foot_ik.R", "move_by": {"forward": -0.25, "left": -0.05}},
        {"bone": "chest", "rotate_by": {"axis": {"up": 1.0}, "degrees": 15.0}},
    ])
    answer = ok(envelope, "set_pose_bones")
    print("stance batch: {:.0f} ms, {:d} B".format(ms, size))
    print("message: {:s}".format(answer["message"]))
    dropped = {side: hands_before[side]["up"] - answer["landmarks"][side]["after"]["up"]
               for side in hands_before}
    check("the fists followed the hips down (IK_parent is Torso)",
          all(abs(value - HIPS_DOWN) < 0.03 for value in dropped.values()), dropped)
    check("no arm was made to stretch or overreach",
          answer["limbs_made_stretched"] == [] and not any(
              answer["limbs"][arm]["stretched"] for arm in ("left_arm", "right_arm")),
          answer["limbs_made_stretched"])
    check("the legs still reach their feet",
          not any(answer["limbs"][leg]["target_unreachable"] for leg in ("left_leg",
                                                                         "right_leg")),
          {leg: answer["limbs"][leg] for leg in ("left_leg", "right_leg")})

    envelope, ms, size = timed(tools["mpfb_get_pose"], name=name)
    pose = ok(envelope, "get_pose")
    fists = [e for e in pose["posed"]["left_hand"] if e["role"] == "finger_master"]
    check("the read-back has the fists, by scale", len(fists) == 5 and all(
        e["scale"]["y"] < 1.0 for e in fists))
    check("the read-back has the switches as set",
          pose["switch_parents"]["left_arm"]["IK_parent"] == "Torso"
          and pose["switch_values"]["right_arm"]["pole_vector"] is True
          and pose["switch_values"]["left_arm"]["IK_Stretch"] == 0.0,
          pose["switch_values"]["left_arm"])
    print("read-back: {:d} posed, {:d} B, {:.0f} ms".format(pose["posed_count"], size, ms))
    print("landmarks now: {:s}".format(json.dumps(
        {key: value["now"] for key, value in pose["landmarks"].items()})))
    return pose


def thirty(tools, name):
    bones = ["{:s}.{:02d}.{:s}".format(finger, segment, side)
             for side in ("L", "R") for finger in ("f_index", "f_middle", "f_ring")
             for segment in (1, 2, 3)]
    bones += ["thumb.{:02d}.{:s}".format(segment, side) for side in ("L", "R")
              for segment in (2, 3)]
    bones += ["neck", "head", "shoulder.L", "shoulder.R", "hips", "toe_ik.L", "toe_ik.R",
              "jaw_master"]
    entries = [{"bone": bone, "rotate_by": {"axis": {"left": 1.0}, "degrees": 4.0}}
               for bone in bones[:30]]
    envelope, ms, size = timed(tools["mpfb_set_pose_bones"], name=name, bones=entries)
    answer = ok(envelope, "set_pose_bones")
    check("a 30-bone batch is written", answer["change_count"] == 30,
          answer["resolution_errors"])
    print("30-bone batch: {:.0f} ms, {:d} B ({:.0f} B per change)".format(
        ms, size, size / 30.0))


def round_trip(tools, name, rig):
    before = blender_state(rig)
    envelope, ms, size = timed(tools["mpfb_reset_pose"], name=name, include_switches=True)
    reset = ok(envelope, "reset_pose")
    print("reset: {:d} bones, {:d} switches, {:.0f} ms, {:d} B; not_restorable {!r}".format(
        reset["reset_count"], len(reset["switches_reset"]), ms, size, reset["not_restorable"]))
    at_rest = ok(tools["mpfb_get_pose"](name=name), "get_pose")
    check("after the reset the character is at rest", at_rest["at_rest"] is True,
          at_rest["message"])
    restore = reset["restore_with"]
    ok(tools["mpfb_set_pose_switches"](**restore["mpfb_set_pose_switches"]), "restore switches")
    written = ok(tools["mpfb_set_pose_bones"](**restore["mpfb_set_pose_bones"]), "restore bones")
    check("restore_with is accepted whole", written["resolution_errors"] == [])
    after = blender_state(rig)
    skip = {entry["bone"] for entry in reset["not_restorable"]}
    worst = max((abs(a - b), bone) for bone, values in before["pose"].items() if bone not in skip
                for a, b in zip(values, after["pose"][bone]))
    check("restore_with puts every channel back", worst[0] < 1e-5, worst)
    check("and every switch", before["switches"] == after["switches"])


def worst_case(tools, name, rig):
    every = ["root", "torso", "head", "face", "left_arm", "right_arm", "left_hand", "right_hand",
             "left_leg", "right_leg"]
    controls = ok(tools["mpfb_get_pose_controls"](name=name, body_parts=every), "controls")
    names = [entry["bone"] for entries in controls["controls"].values() for entry in entries]
    in_blender(
        "from mathutils import Matrix\n"
        "rig = bpy.data.objects[{rig!r}]\n"
        "for name in {names!r}:\n"
        "    pb = rig.pose.bones[name]\n"
        "    pb.matrix_basis = Matrix.Translation((0.001, 0.002, 0.0)) @ "
        "Matrix.Rotation(0.05, 4, 'Y')\n"
        "bpy.context.view_layer.update()\n".format(rig=rig, names=names))
    envelope, ms, size = timed(tools["mpfb_reset_pose"], name=name)
    reset = ok(envelope, "reset_pose")
    restore = len(json.dumps(reset["restore_with"]))
    print("worst case: {:d} controls posed, reset {:.0f} ms, answer {:d} B, restore_with "
          "{:d} B, {:d} not restorable".format(len(names), ms, size, restore,
                                                 len(reset["not_restorable"])))
    check("every control was reset", reset["reset_count"] == len(names),
          (reset["reset_count"], len(names)))


def game_engine(tools):
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    rig = ok(tools["mpfb_add_rig"](name=name, identifier="game_engine"), "add_rig")[
        "rig_object_name"]
    in_blender(
        "rig = bpy.data.objects[{rig!r}]\n"
        "for other in bpy.context.view_layer.objects: other.select_set(False)\n"
        "bpy.context.view_layer.objects.active = rig\n"
        "rig.select_set(True)\n"
        "bpy.ops.mpfb.convert_to_rigify()\n".format(rig=rig))
    ok(tools["mpfb_set_pose_bones"](name=name, bones=[
        {"bone": "hand_ik_l", "move_by": {"forward": 0.2, "up": 0.25, "left": -0.1}},
        {"bone": "foot_ik_r", "move_by": {"forward": 0.2, "up": 0.15}}]), "set_pose_bones")
    for value in (1.0, 0.0):
        answer = ok(tools["mpfb_set_pose_switches"](name=name, switches=[
            {"body_part": part, "switch": "IK_FK", "value": value}
            for part in ("left_arm", "right_leg")]), "set_pose_switches")
        snapped_within_a_millimetre(answer, "game_engine IK_FK to {:g} keeps the limbs".format(
            value))


def nothing_borrowed(tools, name, rig):
    before = blender_state(rig)
    ok(tools["mpfb_set_pose_bones"](name=name, bones=[
        {"bone": "hand_ik.L", "move_by": {"up": 0.05}}]), "set_pose_bones")
    after = blender_state(rig)
    check("a write borrows no mode, active object or selection",
          all(before[key] == after[key] for key in ("mode", "active", "selected")))


def main():
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()
    name, rig = build_character(tools)
    print("character {!r} on rig {!r}, placed at {!r} turned {:g} degrees".format(
        name, rig, PLACEMENT["location"], PLACEMENT["turn_degrees"]))
    karate(tools, name)
    nothing_borrowed(tools, name, rig)
    round_trip(tools, name, rig)
    print()
    print("THE STANCE IS NOW ON {!r}: compare a screenshot with the landmarks above.".format(
        rig))
    print()
    game_engine(tools)
    if "--worst-case" in sys.argv:
        thirty(tools, name)
        worst_case(tools, name, rig)
    print()
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
