# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 044's own live check: the switches filter and compact switch entries on a real install.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. It drives the **real mpfb-mcp
tools over the real socket**, against a Blender that is already running with
the MPFB Bridge's server started (``MPFB_BRIDGE_PORT``, default 9877), and
reuses FR 043's live check, and through it FR 041's, for the karate character,
the generated ``game_engine`` rig and the community blender-mcp socket
(``BLENDER_MCP_PORT``, default 9876).

    PYTHONPATH=. .venv/bin/python feature-requests/done/044-switches-filter/live_check.py

It adds two characters to the open scene and leaves them there.

1. **Sizes** of the default call, ``compact``, FR 043's blocking pass (whose
   switches are now compact too) and FR 044's, which also names
   ``IK_FK``, ``IK_parent`` and ``pole_vector``, on ``human_toes`` and
   ``game_engine``. FR 044's blocking pass must be within 8 KB.
2. **No silent cut**: on every call measured, what is listed plus what the
   counts say was left out is every control, and every switch, in the
   requested parts.
3. **A blocking pass driven by its own answer**: ``IK_parent`` and
   ``pole_vector`` are set from what the compact entries say - the parent named
   ``Torso`` and the end that says the pole aims the elbow - then the hands are
   placed with ``mpfb_set_pose_bones`` and the hips lowered 0.4 m. Where FR 041's
   karate session found the fists left in the air and both arms stretched, the
   hands now go down with the torso and neither arm stretches.
4. **Read-only**: mode, active object, selection and the pose, before and after.

Prints PASS/FAIL per check, the sizes, and exits non-zero on any failure.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FEATURE_REQUESTS = os.path.dirname(HERE)
if os.path.basename(FEATURE_REQUESTS) != "done":
    FEATURE_REQUESTS = os.path.join(FEATURE_REQUESTS, "done")
REPO_ROOT = os.path.dirname(os.path.dirname(FEATURE_REQUESTS))
sys.path.insert(0, REPO_ROOT)


def _fr043():
    path = os.path.join(FEATURE_REQUESTS, "043-narrower-pose-controls", "live_check.py")
    spec = importlib.util.spec_from_file_location("fr043_live_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FR043 = _fr043()
FR041 = FR043.FR041
ok = FR041.ok

FR043_PASS = {"roles": ["ik_control", "pole"], "compact": True}
BLOCKING_PASS = dict(FR043_PASS, switch_names=["IK_FK", "IK_parent", "pole_vector"])
LINE = 8 * 1024
HIPS_DOWN = 0.40
ARMS = ("left_arm", "right_arm")

FAILURES = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print("[{:s}] {:s}{:s}".format(status, label, "" if not detail else " - " + str(detail)),
          flush=True)
    if not condition:
        FAILURES.append(label)


def switches_explained(answer):
    """Listed plus left out by name is every switch of the requested parts, by the answer alone."""
    counts = answer["counts_by_switch"]
    named = answer["requested_switch_names"] or list(counts)
    listed = answer["switches"]
    good = (len(listed) == sum(counts[name] for name in named)
            and all(entry["body_part"] in answer["requested_body_parts"] for entry in listed)
            and all(entry["switch"] in named for entry in listed))
    return good, {"counted": sum(counts.values()), "of_named": sum(counts[n] for n in named),
                  "listed": len(listed)}


def measure(tools, name, label):
    sizes = {}
    answers = {}
    for call, params in (("default", {}), ("compact", {"compact": True}),
                         ("FR 043's blocking pass", FR043_PASS),
                         ("FR 044's blocking pass", BLOCKING_PASS)):
        envelope = tools["mpfb_get_pose_controls"](name=name, **params)
        answer = ok(envelope, "get_pose_controls {:s}".format(call))
        sizes[call] = len(json.dumps(envelope))
        answers[call] = answer
        good, detail = FR043.explained(answer)
        check("{:s}, {:s}: the counts explain every control left out".format(label, call),
              good, detail)
        good, detail = switches_explained(answer)
        check("{:s}, {:s}: counts_by_switch explains every switch left out".format(label, call),
              good, detail)
    for call, answer in answers.items():
        print("{:s}, {:s}: {:,d} B, switches {:,d} B ({:d} listed)".format(
            label, call, sizes[call], len(json.dumps(answer["switches"])),
            len(answer["switches"])))
    print("{:s}: message: {:s}".format(label, answers["FR 044's blocking pass"]["message"]))
    check("{:s}: FR 044's blocking pass is within 8 KB".format(label),
          sizes["FR 044's blocking pass"] <= LINE,
          "{:,d} B".format(sizes["FR 044's blocking pass"]))
    return answers


def _switch(answer, body_part, name):
    return next(entry for entry in answer["switches"]
                if (entry["body_part"], entry["switch"]) == (body_part, name))


def drive_the_blocking_pass(tools, name, answer):
    """IK_parent and pole_vector from the compact entries, then the hands, then the hips."""
    changes = []
    for arm in ARMS:
        parent = _switch(answer, arm, "IK_parent")
        check("{:s} IK_parent is compact and names its parents".format(arm),
              "bone" not in parent and "Torso" in (parent["parent_names"] or []), parent)
        changes.append({"body_part": arm, "switch": "IK_parent",
                        "value": parent["parent_names"].index("Torso")})
        pole = _switch(answer, arm, "pole_vector")
        on = next(end for end, meaning in zip(pole["range"], pole["ends"])
                  if "pole control aims" in meaning)
        changes.append({"body_part": arm, "switch": "pole_vector", "value": on})
    written = ok(tools["mpfb_set_pose_switches"](name=name, switches=changes),
                 "set_pose_switches")
    check("set_pose_switches accepts what the compact entries said",
          not written["resolution_errors"] and written["change_count"] == len(changes),
          written["message"])

    hands = {arm: next(entry["bone"] for entry in answer["controls"][arm]
                       if entry["role"] == "ik_control") for arm in ARMS}
    placed = ok(tools["mpfb_set_pose_bones"](name=name, bones=[
        {"bone": bone, "move_to": FR041.HANDS[bone]} for bone in hands.values()]),
        "set_pose_bones hands")
    check("the hands are placed where the frame says",
          not placed["resolution_errors"] and placed["performed"] is True, placed["message"])
    before = _hand_heights(tools, name, hands)
    lowered = ok(tools["mpfb_set_pose_bones"](name=name, bones=[
        {"bone": "torso", "move_by": {"up": -HIPS_DOWN}}]), "set_pose_bones torso")
    check("the hips are lowered", lowered["performed"] is True, lowered["message"])
    after = _hand_heights(tools, name, hands)
    dropped = {arm: round(before[arm] - after[arm], 3) for arm in ARMS}
    check("with IK_parent on Torso the hands go down with the hips",
          all(abs(drop - HIPS_DOWN) < 0.01 for drop in dropped.values()), dropped)
    limbs = ok(tools["mpfb_get_pose"](name=name), "get_pose")["limbs"]
    check("and neither arm stretches, where the karate session's did",
          not any(limbs[arm]["stretched"] for arm in ARMS),
          {arm: limbs[arm]["reach_ratio"] for arm in ARMS})


def _hand_heights(tools, name, hands):
    posed = ok(tools["mpfb_get_pose"](name=name, body_parts=list(ARMS)), "get_pose")["posed"]
    heads = {entry["bone"]: entry["head"] for entries in posed.values() for entry in entries}
    return {arm: heads[bone]["up"] for arm, bone in hands.items()}


def check_read_only(tools, name, rig):
    before = FR041.blender_state(rig)
    for params in ({}, FR043_PASS, BLOCKING_PASS, {"switch_names": ["parent_switch"]},
                   {"switch_names": ["no_such_switch"]}):
        tools["mpfb_get_pose_controls"](name=name, **params)
    check("reading changes nothing: mode, active object, selection and pose",
          FR041.blender_state(rig) == before)


def main():
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()
    name, rig = FR041.build_karate_character(tools)
    print("character {!r} on rig {!r}".format(name, rig))
    answers = measure(tools, name, "human_toes")
    check_read_only(tools, name, rig)
    drive_the_blocking_pass(tools, name, answers["FR 044's blocking pass"])

    game_engine = FR043.build_game_engine(tools)
    answers = measure(tools, game_engine, "game_engine")
    refused = ok(tools["mpfb_get_pose_controls"](name=game_engine,
                                                 switch_names=["parent_switch"]),
                 "get_pose_controls parent_switch")
    check("parent_switch is human_toes' own and refused on game_engine",
          refused["blocked_by"] == "unknown_switch_names", refused["message"])
    print()
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
