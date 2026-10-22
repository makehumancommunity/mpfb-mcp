"""
``set_pose_bones`` against a real MPFB, on a generated ``human_toes`` rig that has been moved
and turned away from the origin - which is what tests the frame.

What only a real rig can establish, and so is asserted here:

- **Every change kind lands where the frame says**: ``move_by``, ``move_to``,
  ``rotate_by``, ``rotate_to``, ``aim`` with ``twist``, and ``scale_to`` in the
  bone's own axes, each read back through ``get_pose`` - and ``get_pose``'s own
  ``head`` and ``rotation``, written back after a reset, reproduce the pose.
- **Parents are written first**, so a child's ``move_to`` holds although its
  parent is listed after it and moves in the same call.
- **Symmetry mirrors the instruction**: from rest, a mirrored pair reads back
  as each other's mirror image.
- **Every refusal of requirement 7, and the rollback**: not a control, a chain
  ``IK_FK`` has handed away (both ways), an FK bone an MPFB helper drives, a
  locked channel (a connected bone's head included), a driven channel, an
  unknown bone. A batch whose last entry fails a check made *after* writing
  leaves every bone's channels exactly as they were.
- **``achieved`` is measured**: Rigify's controls carry no constraints, so a
  stock rig never stops one short; a Limit Location the test adds does, and the
  answer says by how much.
- **An animated channel is written and flagged**, never refused, and no
  keyframe is inserted even with auto-keying on.
- **Nothing is borrowed**, a rig showing its rest position is posed and says so,
  a rig in edit mode is refused, and an unclassified rig takes transforms.
"""

import math

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import answer as _answer
from .._fixtures import posing_state
from .._fixtures import rest_pose
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip
from .._fixtures import with_helpers

_MM = 0.0011


def _result(params):
    return _fixture_result("set_pose_bones", params)


def _close(first, second, tolerance=_MM):
    return all(abs(first[key] - second[key]) <= tolerance for key in ("forward", "left", "up"))


def _frame(rig):
    return bridge_module("shared.character_frame").Frame(rig)


def _posed(basemesh, body_part, bone):
    posed = _fixture_result("get_pose", {"name": basemesh, "body_parts": [body_part]})["posed"]
    return next(entry for entry in posed[body_part] if entry["bone"] == bone)


@pytest.fixture(scope="module", name="human_toes")
def _human_toes():
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        rig.location = (1.5, -2.0, 0.0)
        rig.rotation_euler = (0.0, 0.0, math.radians(120.0))
        bpy.context.view_layer.update()
        yield character.basemesh.name, rig


@pytest.fixture(name="rigify")
def _rigify(human_toes):
    _basemesh, rig = human_toes
    rest_pose(rig)
    yield human_toes
    rest_pose(rig)


def test_each_change_kind_lands_in_the_character_frame(rigify):
    """commands.set_pose_bones: every change kind on a moved and turned rig"""
    basemesh, rig = rigify
    target = {"forward": 0.35, "left": -0.3, "up": 1.2}
    answer = _result({"name": basemesh, "bones": [
        {"bone": "hand_ik.L", "move_by": {"forward": 0.1, "up": 0.2}},
        {"bone": "hand_ik.R", "move_to": target},
        {"bone": "torso", "rotate_by": {"axis": {"up": 1.0}, "degrees": 30.0}},
        {"bone": "head", "aim": {"forward": 1.0, "up": 1.0}, "twist": 15.0},
        {"bone": "f_index.01_master.L", "scale_to": {"y": 0.45}},
    ]})

    assert answer["performed"] is True and answer["resolution_errors"] == []
    assert answer["classified"] is True and answer["pose_position"] == "POSE"
    changes = {change["bone"]: change for change in answer["changes"]}
    assert [change["bone"] for change in answer["changes"]] == [
        "hand_ik.L", "hand_ik.R", "torso", "head", "f_index.01_master.L"], "request order"
    assert all(change["achieved"] for change in answer["changes"])
    moved = changes["hand_ik.L"]
    assert _close(moved["head_after"], {"forward": moved["head_before"]["forward"] + 0.1,
                                        "left": moved["head_before"]["left"],
                                        "up": moved["head_before"]["up"] + 0.2})
    assert (moved["body_part"], moved["role"]) == ("left_arm", "ik_control")
    assert _close(changes["hand_ik.R"]["head_after"], target)
    assert _posed(basemesh, "right_arm", "hand_ik.R")["head"] == changes["hand_ik.R"]["head_after"]
    turned = changes["torso"]["rotation_after"]
    assert turned["degrees"] == 30.0 and turned["axis"]["up"] > 0.999
    head = rig.pose.bones["head"]
    aimed = _frame(rig).armature_direction(head.tail - head.head)
    assert abs(aimed["forward"] - aimed["up"]) < 0.002 and aimed["left"] == 0.0
    scaled = changes["f_index.01_master.L"]
    assert scaled["scale_before"] is None
    assert scaled["scale_after"] == {"x": 1.0, "y": 0.45, "z": 1.0}
    assert set(answer["landmarks"]) == {"hips", "head", "left_hand", "right_hand",
                                        "left_foot", "right_foot"}
    assert answer["landmarks"]["left_hand"]["after"] != answer["landmarks"]["left_hand"]["before"]
    assert answer["limbs"]["left_arm"]["in_charge"] == "ik"
    assert "achieved" in answer["achieved_measure"]


def test_a_read_back_written_back_is_the_same_pose(rigify):
    """commands.set_pose_bones fed get_pose's head and rotation after a reset"""
    basemesh, rig = rigify
    _result({"name": basemesh, "bones": [
        {"bone": "torso", "move_by": {"up": -0.2},
         "rotate_by": {"axis": {"forward": 0.3, "up": 1.0}, "degrees": 25.0}},
        {"bone": "chest", "rotate_by": {"axis": {"left": 1.0}, "degrees": 15.0}},
        {"bone": "hand_ik.L", "move_by": {"forward": 0.2, "up": 0.3},
         "rotate_by": {"axis": {"left": 1.0}, "degrees": -40.0}},
    ]})
    before = _fixture_result("get_pose", {"name": basemesh})["posed"]
    rest_pose(rig)
    entries = [{"bone": entry["bone"], "move_to": entry["head"],
                "rotate_to": entry["rotation"]}
               for entries in before.values() for entry in entries]
    assert _result({"name": basemesh, "bones": entries})["performed"] is True
    after = _fixture_result("get_pose", {"name": basemesh})["posed"]
    for part, entries in before.items():
        for mine, theirs in zip(entries, after[part]):
            assert mine["bone"] == theirs["bone"]
            assert _close(mine["head"], theirs["head"], 0.0021), mine["bone"]
            assert abs(mine["rotation"]["degrees"] - theirs["rotation"]["degrees"]) <= 0.2


def test_a_parent_is_written_before_its_child(rigify):
    """commands.set_pose_bones with a child's move_to listed before its parent's move"""
    basemesh, rig = rigify
    assert rig.pose.bones["chest"].parent.name == "torso"
    target = {"forward": 0.1, "left": 0.05, "up": 1.0}
    answer = _result({"name": basemesh, "bones": [
        {"bone": "chest", "move_to": target},
        {"bone": "torso", "move_by": {"up": -0.3}},
    ]})

    chest = answer["changes"][0]
    assert chest["bone"] == "chest" and chest["achieved"] is True
    assert _close(chest["head_after"], target)


def test_symmetry_mirrors_the_instruction(rigify):
    """commands.set_pose_bones with symmetry, checked for mirror-equality from rest"""
    basemesh, _rig = rigify
    answer = _result({"name": basemesh, "bones": [
        {"bone": "hand_ik.L", "symmetry": True, "move_by": {"forward": 0.15, "left": 0.1},
         "rotate_by": {"axis": {"forward": 0.3, "left": 0.5, "up": 0.2}, "degrees": 40.0}},
        {"bone": "f_index.01_master.L", "symmetry": True, "scale_to": {"y": 0.5}},
    ]})

    left, right = answer["changes"][0], answer["changes"][1]
    assert right["bone"] == "hand_ik.R" and right["mirrored_from"] == "hand_ik.L"
    assert right["body_part"] == "right_arm" and right["role"] == left["role"]
    assert _close(right["head_after"], {"forward": left["head_after"]["forward"],
                                        "left": -left["head_after"]["left"],
                                        "up": left["head_after"]["up"]}, 0.0021)
    mine, theirs = left["rotation_after"], right["rotation_after"]
    assert abs(mine["degrees"] - theirs["degrees"]) <= 0.2
    assert _close(theirs["axis"], {"forward": -mine["axis"]["forward"],
                                   "left": mine["axis"]["left"],
                                   "up": -mine["axis"]["up"]}, 0.005)
    assert answer["changes"][3]["bone"] == "f_index.01_master.R"
    assert answer["changes"][3]["scale_after"] == {"x": 1.0, "y": 0.5, "z": 1.0}


def _refused(basemesh, bones):
    answer = _result({"name": basemesh, "bones": bones})
    assert answer["performed"] is False and answer["changes"] == []
    return answer["resolution_errors"]


def test_a_bone_that_is_not_in_charge_is_refused_naming_the_write_that_would_work(rigify):
    """commands.set_pose_bones: not a control, and a chain IK_FK has handed away"""
    basemesh, rig = rigify
    (error,) = _refused(basemesh, [{"bone": "DEF-forearm.L", "rotate_by": {
        "axis": {"up": 1.0}, "degrees": 10.0}}])
    assert error["reason"] == "not_a_control"
    assert error["write_instead"] == {"bone": "forearm_fk.L"}
    assert "include_hidden" not in error["message"], "forearm_fk.L is listed by default"
    # FR 043, R12: a pointer at a control the default listing leaves out says so.
    (error,) = _refused(basemesh, [{"bone": "DEF-f_index.02.L", "rotate_by": {
        "axis": {"up": 1.0}, "degrees": 10.0}}])
    assert error["write_instead"] == {"bone": "f_index.02.L"}
    assert "hidden by default" in error["message"] and "include_hidden" in error["message"]
    (error,) = _refused(basemesh, [{"bone": "forearm_fk.L", "rotate_by": {
        "axis": {"up": 1.0}, "degrees": 10.0}}])
    assert error["reason"] == "chain_not_in_charge"
    assert error["write_instead"] == {"tool": "mpfb_set_pose_switches", "switches": [
        {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}]}
    rig.pose.bones["upper_arm_parent.L"]["IK_FK"] = 1.0
    bpy.context.view_layer.update()
    (error,) = _refused(basemesh, [{"bone": "hand_ik.L", "move_by": {"up": 0.1}}])
    assert error["write_instead"]["switches"][0]["value"] == 0.0
    answer = _result({"name": basemesh, "bones": [{"bone": "forearm_fk.L", "rotate_by": {
        "axis": {"up": 1.0}, "degrees": 10.0}}]})
    assert answer["performed"] is True, "in FK, the FK chain is in charge"


def test_a_locked_or_driven_channel_is_refused(rigify):
    """commands.set_pose_bones: locks the matrix setter ignores, a connected head, a driver"""
    basemesh, rig = rigify
    (error,) = _refused(basemesh, [{"bone": "upper_arm_ik.L", "rotate_by": {
        "axis": {"forward": 1.0}, "degrees": 20.0}}])
    assert (error["reason"], error["channels"]) == ("locked_channel", ["rotation"])
    # Its own axis, before the IK solver's rotation: a relative change starts there.
    base = rig.pose.bones["upper_arm_ik.L"]
    own = rig.convert_space(pose_bone=base, matrix=base.matrix_basis, from_space="LOCAL",
                            to_space="POSE")
    answer = _result({"name": basemesh, "bones": [{"bone": "upper_arm_ik.L", "rotate_by": {
        "axis": _frame(rig).armature_direction(own.col[1].xyz), "degrees": 30.0}}]})
    assert answer["performed"] is True, "a twist about the bone's own axis is not locked"
    rig.pose.bones["upper_arm_parent.L"]["IK_FK"] = 1.0
    bpy.context.view_layer.update()
    (error,) = _refused(basemesh, [{"bone": "forearm_fk.L", "move_by": {"up": 0.1}}])
    assert error["reason"] == "locked_channel" and "connected" in error["message"]
    curve = rig.pose.bones["torso"].driver_add("location", 0)
    try:
        (error,) = _refused(basemesh, [{"bone": "torso", "move_by": {"up": 0.1}}])
        assert (error["reason"], error["channels"]) == ("driven_channel", ["location"])
        assert _result({"name": basemesh, "bones": [{"bone": "torso", "rotate_by": {
            "axis": {"up": 1.0}, "degrees": 5.0}}]})["performed"] is True
    finally:
        rig.pose.bones["torso"].driver_remove("location", 0)
        del curve
    (error,) = _refused(basemesh, [{"bone": "hand_ikk.L", "move_by": {"up": 0.1}}])
    assert error["reason"] == "unknown_bone" and "hand_ik.L" in error["closest"]


def test_a_batch_that_fails_after_writing_leaves_every_bone_as_it_was(rigify):
    """commands.set_pose_bones rolls back two written bones when the third breaks a lock"""
    basemesh, rig = rigify
    rig.pose.bones["chest"].rotation_quaternion = (0.98, 0.1, 0.1, 0.0)
    bpy.context.view_layer.update()
    before = posing_state(rig)
    errors = _refused(basemesh, [
        {"bone": "torso", "move_by": {"up": -0.2}},
        {"bone": "hand_ik.L", "move_by": {"forward": 0.3}},
        {"bone": "upper_arm_ik.L", "rotate_by": {"axis": {"forward": 1.0}, "degrees": 20.0}},
    ])
    assert [error["index"] for error in errors] == [2]
    assert posing_state(rig) == before


def test_a_default_rigs_helper_driven_bone_is_refused():
    """commands.set_pose_bones on a default rig with MPFB's arm helpers"""
    services = services_or_skip()
    with Character() as character:
        rig = with_helpers(rigged_character(services, character, "default"), arm="LOWERUPPER")
        (error,) = _refused(character.basemesh.name, [{"bone": "lowerarm02.L", "rotate_by": {
            "axis": {"up": 1.0}, "degrees": 10.0}}])
        assert error["reason"] == "driven_by_helper"
        assert error["write_instead"] == {"bone": "left_hand_ik"}
        answer = _result({"name": character.basemesh.name, "bones": [
            {"bone": "left_hand_ik", "move_by": {"up": 0.2}}]})
        assert answer["changes"][0]["achieved"] is True
        assert answer["changes"][0]["role"] == "ik_control"
        del rig


def test_achieved_is_measured_and_a_limit_shows(rigify):
    """commands.set_pose_bones on a control a Limit Location stops short"""
    basemesh, rig = rigify
    hand = rig.pose.bones["hand_ik.L"]
    limit = hand.constraints.new("LIMIT_DISTANCE")
    limit.target = rig
    limit.subtarget = "torso"
    try:
        bpy.context.view_layer.update()
        limit.distance = (hand.head - rig.pose.bones["torso"].head).length
        bpy.context.view_layer.update()
        answer = _result({"name": basemesh, "bones": [
            {"bone": "hand_ik.L", "move_by": {"left": 0.4}}]})
        (change,) = answer["changes"]
        assert change["achieved"] is False
        assert change["deviation"]["distance"] > 0.1
        assert "did not end where asked" in answer["message"]
    finally:
        hand.constraints.remove(limit)


def test_an_animated_channel_is_written_and_flagged_and_nothing_is_keyed(rigify):
    """commands.set_pose_bones on a keyed bone, with auto-keying on"""
    basemesh, rig = rigify
    tool_settings = bpy.context.scene.tool_settings
    keying = tool_settings.use_keyframe_insert_auto
    rig.pose.bones["torso"].keyframe_insert("location")
    action = rig.animation_data.action
    curves = len(list(_fcurves(rig)))
    try:
        tool_settings.use_keyframe_insert_auto = True
        answer = _result({"name": basemesh, "bones": [
            {"bone": "torso", "move_by": {"up": -0.1}},
            {"bone": "chest", "rotate_by": {"axis": {"left": 1.0}, "degrees": 10.0}}]})
        assert answer["changes"][0]["overwritten_on_frame_change"] == ["location"]
        assert "overwritten_on_frame_change" not in answer["changes"][1]
        assert len(list(_fcurves(rig))) == curves, "no keyframe was inserted"
    finally:
        tool_settings.use_keyframe_insert_auto = keying
        # Not animation_data_clear(): that would take Rigify's drivers with it,
        # leaving every later test in this module a rig whose fingers do not curl.
        rig.animation_data.action = None
        bpy.data.actions.remove(action)


def _fcurves(rig):
    from bpy_extras import anim_utils  # pylint: disable=import-outside-toplevel
    animation = rig.animation_data
    channelbag = anim_utils.action_get_channelbag_for_slot(animation.action,
                                                           animation.action_slot)
    return channelbag.fcurves if channelbag else []


def test_nothing_is_borrowed_and_rest_position_is_posed_and_said(rigify):
    """commands.set_pose_bones leaves mode, selection and active object alone"""
    basemesh, rig = rigify
    bystander = bpy.data.objects.new("PoseWriteBystander", None)
    bpy.context.scene.collection.objects.link(bystander)
    try:
        bpy.context.view_layer.objects.active = bystander
        bystander.select_set(True)
        rig.data.pose_position = "REST"
        before = posing_state(rig)
        answer = _result({"name": basemesh, "bones": [
            {"bone": "hand_ik.L", "move_by": {"up": 0.1}}]})
        after = posing_state(rig)
        assert answer["pose_position"] == "REST" and "rest position" in answer["message"]
        assert rig.data.pose_position == "REST", "put back"
        assert answer["changes"][0]["achieved"] is True
        for key in ("mode", "rig_mode", "active", "selected"):
            assert after[key] == before[key], key
    finally:
        bpy.data.objects.remove(bystander, do_unlink=True)


def test_a_rig_in_edit_mode_is_refused(rigify):
    """commands.set_pose_bones on a rig in edit mode"""
    basemesh, rig = rigify
    previous = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        answer = _result({"name": basemesh, "bones": [
            {"bone": "hand_ik.L", "move_by": {"up": 0.1}}]})
        assert (answer["ready"], answer["blocked_by"]) == (False, "rig_in_edit_mode")
        assert answer["performed"] is False
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = previous


def test_an_empty_batch_and_a_bad_entry_change_nothing(rigify):
    """commands.set_pose_bones named nothing, and the bridge's own shape check"""
    basemesh, rig = rigify
    before = posing_state(rig)
    nothing = _result({"name": basemesh, "bones": []})
    assert nothing["performed"] is False and "named nothing" in nothing["message"]
    (error,) = _refused(basemesh, [{"bone": "torso", "move_too": {"up": 1}}])
    assert error["reason"] == "invalid_entry"
    assert posing_state(rig) == before


def test_an_unclassified_rig_takes_transforms():
    """commands.set_pose_bones on a mixamo rig: only locks and drivers are checked"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "mixamo")
        answer = _result({"name": character.basemesh.name, "bones": [
            {"bone": "mixamorig:LeftArm", "rotate_by": {"axis": {"forward": 1.0},
                                                       "degrees": -45.0}}]})
        (change,) = answer["changes"]
        assert answer["classified"] is False
        assert (change["body_part"], change["role"]) == (None, None)
        assert change["achieved"] is True and change["rotation_after"]["degrees"] == 45.0
        assert answer["landmarks"] is None and answer["limbs"] is None
        assert _answer("set_pose_bones", {"name": character.basemesh.name, "bones": [
            {"bone": "mixamorig:LeftArm", "symmetry": True, "move_by": {"up": 0.01}}]}
                       )["status"] == "ok"
        del rig
