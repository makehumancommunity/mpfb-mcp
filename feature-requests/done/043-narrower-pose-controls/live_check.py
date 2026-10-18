# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 043's own live check: the narrowing filters on a real install, in a windowed Blender.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. It drives the **real mpfb-mcp
tools over the real socket**, against a Blender that is already running with
the MPFB Bridge's server started (``MPFB_BRIDGE_PORT``, default 9877), and
reuses FR 041's live check for the karate character and for the community
blender-mcp socket (``BLENDER_MCP_PORT``, default 9876), which it needs for two
things the bridge will not do: turning MPFB's game_engine rig into a generated
one, and calling the bridge's own ``pose_writing.charge_refusal`` over every
bone of a rig.

    PYTHONPATH=. .venv/bin/python feature-requests/done/043-narrower-pose-controls/live_check.py

It adds three characters to the open scene and leaves them there.

1. **The default is what a person starts with**: every bone FR 041's karate
   session moved by hand is in the default answer, with its role.
2. **Sizes** of the default call, ``include_hidden``, ``compact`` and the
   blocking pass (``roles: ["ik_control", "pole"]``, ``compact``), on
   ``human_toes``, ``game_engine`` and the default rig, against the 8 KB line
   for the blocking pass. The switches are cut by body part alone (requirement
   7), and on a generated Rigify rig they are about 8 KB by themselves, which
   the request said to record rather than trim: so the line is checked against
   the blocking pass less its switches, and the switches are printed beside it.
3. **No silent cut**: on every call measured, what is listed plus what the
   counts say was left out is every control in the requested parts.
4. **Read-only**: mode, active object, selection and the pose, before and after.
5. **Requirement 12**: every ``write_instead`` a ``not_a_control`` refusal can
   give on ``human_toes`` that points at a control the default listing leaves
   out says so in its message; counted, and one confirmed over the socket.

Prints PASS/FAIL per check, the sizes, and exits non-zero on any failure.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO_ROOT)


def _fr041():
    path = os.path.join(REPO_ROOT, "feature-requests", "done", "041-pose-controls-and-read-back",
                        "live_check.py")
    spec = importlib.util.spec_from_file_location("fr041_live_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FR041 = _fr041()
KARATE_BONES = FR041.KARATE_BONES
in_blender = FR041.in_blender
ok = FR041.ok

BLOCKING_PASS = {"roles": ["ik_control", "pole"], "compact": True}
LINE = 8 * 1024

FAILURES = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print("[{:s}] {:s}{:s}".format(status, label, "" if not detail else " - " + str(detail)),
          flush=True)
    if not condition:
        FAILURES.append(label)


def explained(answer):
    """Listed plus left out is everything in the requested parts, by the answer's own counts."""
    requested = answer["requested_body_parts"]
    in_parts = sum(answer["counts_by_body_part"][part] for part in requested)
    roles = answer["requested_roles"] or list(answer["counts_by_role"])
    of_roles = sum(answer["counts_by_role"][role] for role in roles)
    hidden = 0 if answer["include_hidden"] else sum(answer["hidden_by_body_part"].values())
    listed = sum(len(entries) for entries in answer["controls"].values())
    return (sum(answer["counts_by_role"].values()) == in_parts and listed == of_roles - hidden,
            {"in_parts": in_parts, "of_roles": of_roles, "hidden_left_out": hidden,
             "listed": listed})


def measure(tools, name, label):
    """Every call the request names a size for, measured and checked for a silent cut."""
    sizes = {}
    answers = {}
    for call, params in (("default", {}), ("include_hidden", {"include_hidden": True}),
                         ("compact", {"compact": True}), ("blocking pass", BLOCKING_PASS)):
        envelope = tools["mpfb_get_pose_controls"](name=name, **params)
        answer = ok(envelope, "get_pose_controls {:s}".format(call))
        sizes[call] = len(json.dumps(envelope))
        answers[call] = answer
        good, detail = explained(answer)
        check("{:s}, {:s}: the counts explain every control left out".format(label, call),
              good, detail)
    listed = {call: sum(len(entries) for entries in answer["controls"].values())
              for call, answer in answers.items()}
    print("{:s}: {:s}".format(label, ", ".join(
        "{:s} {:,d} B ({:d} listed)".format(call, size, listed[call])
        for call, size in sizes.items())))
    print("{:s}: switches {:,d} B, message: {:s}".format(
        label, len(json.dumps(answers["default"]["switches"])), answers["default"]["message"]))
    return sizes, answers


def check_karate(tools, name):
    answer = ok(tools["mpfb_get_pose_controls"](name=name), "get_pose_controls")
    controls = {entry["bone"]: (part, entry["role"])
                for part, entries in answer["controls"].items() for entry in entries}
    wrong = {bone: controls.get(bone) for bone, expected in KARATE_BONES.items()
             if controls.get(bone) != expected}
    check("every bone the karate session moved is in the default answer, with its role",
          not wrong, wrong)
    hidden = sum(answer["hidden_by_body_part"].values())
    check("the default human_toes answer leaves out the 109 hidden controls", hidden == 109,
          answer["hidden_by_body_part"])


def check_read_only(tools, name, rig):
    before = FR041.blender_state(rig)
    for params in ({}, {"include_hidden": True, "body_parts": ["face"]}, BLOCKING_PASS):
        tools["mpfb_get_pose_controls"](name=name, **params)
    check("reading changes nothing: mode, active object, selection and pose",
          FR041.blender_state(rig) == before)


# Run inside Blender: charge_refusal over every bone of the rig that is not a
# control, through the bridge's own module, printed as JSON.
_REFUSALS = '''
import json, sys
root = next(name for name in sys.modules if name.endswith(".mpfb_bridge"))
pose_controls = sys.modules[root + ".shared.pose_controls"]
pose_writing = sys.modules[root + ".shared.pose_writing"]
mpfb = next(name for name in sys.modules if name.endswith(".mpfb") and name.startswith("bl_ext"))
rig = bpy.data.objects[{rig!r}]
classification = pose_controls.classify(mpfb, rig, "rigify_generated.human_toes")
controls = classification["controls"]
rows = []
for bone in rig.data.bones:
    if bone.name in controls:
        continue
    refusal = pose_writing.charge_refusal(classification, {{}}, bone.name)
    instead = refusal[2]
    if instead is None:
        continue
    rows.append([bone.name, instead["bone"], controls[instead["bone"]]["hidden_by_default"],
                 "include_hidden" in refusal[1]])
print(json.dumps(rows))
'''


def check_write_instead(tools, name, rig):
    rows = json.loads(in_blender(_REFUSALS.format(rig=rig)))
    to_hidden = [row for row in rows if row[2]]
    unsaid = [row for row in to_hidden if not row[3]]
    said_wrongly = [row for row in rows if not row[2] and row[3]]
    print("write_instead: {:d} internal bone(s) point at a control, {:d} of them at a hidden "
          "one (e.g. {!r})".format(len(rows), len(to_hidden), [row[:2] for row in to_hidden[:4]]))
    check("every write_instead at a hidden control says so", not unsaid, unsaid[:5])
    check("no write_instead at a listed control mentions include_hidden", not said_wrongly,
          said_wrongly[:5])
    answer = ok(tools["mpfb_set_pose_bones"](name=name, bones=[
        {"bone": "DEF-f_index.02.L", "rotate_by": {"axis": {"up": 1.0}, "degrees": 5.0}}]),
        "set_pose_bones")
    errors = answer.get("resolution_errors") or []
    check("over the socket, the refusal names the hidden control and include_hidden",
          errors and errors[0]["write_instead"] == {"bone": "f_index.02.L"}
          and "include_hidden" in errors[0]["message"], errors)


def build_game_engine(tools):
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    rig = ok(tools["mpfb_add_rig"](name=name, identifier="game_engine"), "add_rig")[
        "rig_object_name"]
    in_blender(
        "rig = bpy.data.objects[{rig!r}]\n"
        "for other in bpy.context.view_layer.objects: other.select_set(False)\n"
        "bpy.context.view_layer.objects.active = rig\n"
        "rig.select_set(True)\n"
        "bpy.ops.mpfb.convert_to_rigify()\n".format(rig=rig))
    return name


def build_default(tools):
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    ok(tools["mpfb_add_rig"](name=name, identifier="default"), "add_rig")
    return name


def main():
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()
    name, rig = FR041.build_karate_character(tools)
    print("character {!r} on rig {!r}".format(name, rig))
    check_karate(tools, name)
    sizes, _answers = measure(tools, name, "human_toes")
    switches = len(json.dumps(_answers["blocking pass"]["switches"]))
    check("the blocking pass less its switches is within 8 KB",
          sizes["blocking pass"] - switches <= LINE,
          "{:,d} B, of which switches {:,d} B".format(sizes["blocking pass"], switches))
    check_read_only(tools, name, rig)
    check_write_instead(tools, name, rig)

    game_engine = build_game_engine(tools)
    _sizes, answers = measure(tools, game_engine, "game_engine")
    check("game_engine now leaves hidden controls out by default",
          sum(answers["default"]["hidden_by_body_part"].values()) > 0,
          answers["default"]["hidden_by_body_part"])

    default = build_default(tools)
    _sizes, answers = measure(tools, default, "default rig")
    check("the default rig hides nothing",
          sum(answers["default"]["hidden_by_body_part"].values()) == 0,
          answers["default"]["hidden_by_body_part"])
    print()
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
