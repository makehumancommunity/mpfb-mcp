"""
``set_rigify_hand_shape`` against a real MPFB, on generated ``human_toes`` and ``human`` rigs moved
and turned away from the origin.

What only a real rig can establish, and so is asserted here:

- **Every shape reads back as itself**, on both meta-rigs, through
  ``get_rigify_hand_shape``'s ``matches_shape`` - the two meta-rigs share their
  hands, so one table serves both - and every written finger is ``achieved``.
- **One amount changes one finger and nothing else**: a curl writes that
  finger's master and nothing more; a spread alone leaves even its Y scale
  exactly as it was.
- **A shape and its override in one entry**, and ``symmetry`` copying the entry
  to the other hand without mirroring.
- **A written finger's segments are reset, and ``restore_with`` brings them
  back**, with a hook and an ordinary curl elsewhere on the hand: every channel
  within 1e-5 after sending both calls in order.
- **The refusals of requirement 14, and the rollback**: a finger whose IK
  control is in charge, a driven master, a locked channel found after writing
  that undoes a hand already written, an unknown shape, finger or hand, a
  finger the rig does not have, a hand named twice or by symmetry, a rig in
  edit mode.
- **An animated channel is written and flagged**, nothing is keyed, and nothing
  is borrowed.
"""

import math

import bpy
import pytest

from .._fixtures import Character
from .._fixtures import answer as _answer
from .._fixtures import posing_state
from .._fixtures import rest_pose
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip

_SHAPES = ("open", "relaxed", "fist", "pointing", "grip", "pinch")
_CHANNELS = ("location", "rotation_quaternion", "rotation_euler", "rotation_axis_angle", "scale")


def _result(params):
    return _fixture_result("set_rigify_hand_shape", params)


def _read(basemesh):
    return _fixture_result("get_rigify_hand_shape", {"name": basemesh})["hands"]


def _channels(rig):
    return {pose_bone.name: {channel: tuple(getattr(pose_bone, channel))
                             for channel in _CHANNELS}
            for pose_bone in rig.pose.bones}


def _differing(before, after, tolerance=0.0):
    return sorted(name for name, channels in before.items()
                  if any(abs(a - b) > tolerance
                         for channel in _CHANNELS
                         for a, b in zip(channels[channel], after[name][channel])))


def _refused(basemesh, hands):
    answer = _result({"name": basemesh, "hands": hands})
    assert answer["performed"] is False and answer["changed"] is False
    assert answer["hands"] == [] and answer["restore_with"] == {}
    assert "nothing at all was applied" in answer["message"]
    return answer["resolution_errors"]


def _placed(services, character, kind):
    rig = rigged_character(services, character, kind)
    rig.location = (-1.5, 2.5, 0.0)
    rig.rotation_euler = (0.0, 0.0, math.radians(-110.0))
    bpy.context.view_layer.update()
    return rig


@pytest.fixture(scope="module", name="both_rigs", params=["generated:human_toes", "generated:human"])
def _both_rigs(request):
    services = services_or_skip()
    with Character() as character:
        yield character.basemesh.name, _placed(services, character, request.param)


@pytest.fixture(scope="module", name="human_toes")
def _human_toes():
    services = services_or_skip()
    with Character() as character:
        yield character.basemesh.name, _placed(services, character, "generated:human_toes")


@pytest.fixture(name="rigify")
def _rigify(human_toes):
    _basemesh, rig = human_toes
    rest_pose(rig)
    bpy.context.view_layer.update()
    yield human_toes
    rest_pose(rig)


@pytest.mark.parametrize("shape", _SHAPES)
def test_every_shape_reads_back_as_itself(both_rigs, shape):
    """commands.set_rigify_hand_shape then get_rigify_hand_shape, on human_toes and human"""
    basemesh, rig = both_rigs
    rest_pose(rig)
    answer = _result({"name": basemesh, "hands": [
        {"body_part": "left_hand", "shape": shape, "symmetry": True}]})

    assert answer["resolution_errors"] == []
    assert answer["performed"] is (shape != "open")
    assert [hand["body_part"] for hand in answer["hands"]] == ["left_hand", "right_hand"]
    assert answer["hands"][1]["mirrored_from"] == "left_hand"
    for hand in answer["hands"]:
        assert hand["matches_shape_after"] == shape
        assert all(finger["achieved"] for finger in hand["fingers_after"].values())
    read = _read(basemesh)
    assert read["left_hand"]["matches_shape"] == shape
    assert read["right_hand"]["matches_shape"] == shape
    rest_pose(rig)


def test_pointing_is_a_fist_with_the_index_straight(rigify):
    """commands.set_rigify_hand_shape: a shape and a fingers override in one entry"""
    basemesh, _rig = rigify
    answer = _result({"name": basemesh, "hands": [
        {"body_part": "right_hand", "shape": "fist", "fingers": {"index": {"curl": 0.0}}}]})

    hand = answer["hands"][0]
    assert hand["matches_shape_after"] == "pointing"
    assert all(abs(value) < 5.0 for value in hand["fingers_after"]["index"]["joint_degrees"])
    assert hand["fingers_written"] == ["thumb", "index", "middle", "ring", "pinky"]


@pytest.mark.parametrize("amounts,bone_channels", [
    ({"curl": 0.5}, {"rotation_euler", "scale"}),
    ({"spread": -0.6}, {"rotation_euler"})])
def test_one_amount_changes_one_finger_and_nothing_else(rigify, amounts, bone_channels):
    """commands.set_rigify_hand_shape: a curl, then a spread alone, on one finger"""
    basemesh, rig = rigify
    _result({"name": basemesh, "hands": [{"body_part": "left_hand",
                                          "fingers": {"ring": {"curl": 0.3, "spread": 0.2}}}]})
    before = _channels(rig)

    answer = _result({"name": basemesh, "hands": [
        {"body_part": "left_hand", "fingers": {"ring": amounts}}]})

    after = _channels(rig)
    assert answer["hands"][0]["fingers_written"] == ["ring"]
    # Rigify's drivers turn the ring's later MCH-..._drv bones from the master's
    # Y scale; those follow the write by design and are not the command's.
    driven = {name for name in before if name.startswith("MCH-f_ring.") and "_drv" in name}
    assert [name for name in _differing(before, after) if name not in driven] == [
        "f_ring.01_master.L"]
    changed = {channel for channel in _CHANNELS
               if before["f_ring.01_master.L"][channel] != after["f_ring.01_master.L"][channel]}
    assert changed == bone_channels
    ring = answer["hands"][0]["fingers_after"]["ring"]
    expected = {"curl": 0.3, "spread": 0.2}
    expected.update(amounts)
    assert (ring["curl"], ring["spread"]) == (expected["curl"], expected["spread"])
    assert answer["restore_with"] == {"mpfb_set_rigify_hand_shape": {
        "name": rig.name, "hands": [{"body_part": "left_hand", "fingers": {
            "ring": {"curl": pytest.approx(0.3, abs=1e-5),
                     "spread": pytest.approx(0.2, abs=1e-5)}}}]}}


def test_segments_are_reset_and_restore_with_brings_everything_back(rigify):
    """commands.set_rigify_hand_shape: posed segments, a hook and a curl, then restore_with"""
    basemesh, rig = rigify
    _result({"name": basemesh, "hands": [{"body_part": "left_hand",
                                          "fingers": {"ring": {"curl": 0.4, "spread": -0.3}}}]})
    pose_bones = rig.pose.bones
    pose_bones["f_index.02.L"].rotation_euler = (0.3, 0.0, 0.05)
    pose_bones["f_index.03.L"].scale = (1.0, 1.1, 1.0)
    pose_bones["f_middle.01_master.L"].scale = (1.0, 0.5, 1.0)  # a hook
    bpy.context.view_layer.update()
    before = _channels(rig)

    answer = _result({"name": basemesh, "hands": [{"body_part": "left_hand", "shape": "fist"}]})

    hand = answer["hands"][0]
    assert sorted(entry["bone"] for entry in hand["segments_reset"]) == ["f_index.02.L",
                                                                         "f_index.03.L"]
    assert all(entry["finger"] == "index" for entry in hand["segments_reset"])
    assert not pose_reading_off_rest(rig, "f_index.02.L")
    assert hand["fingers_before"]["index"]["not_expressible_because"] == ["segment_posed"]
    assert hand["fingers_before"]["middle"]["not_expressible_because"] == [
        "knuckle_and_joints_disagree"]
    restore = answer["restore_with"]
    assert list(restore) == ["mpfb_set_rigify_hand_shape", "mpfb_set_pose_bones"]
    assert "middle" not in restore["mpfb_set_rigify_hand_shape"]["hands"][0]["fingers"], \
        "a hook is not a curl and a spread, so its master goes back through set_pose_bones"
    assert {entry["bone"] for entry in restore["mpfb_set_pose_bones"]["bones"]} == {
        "f_middle.01_master.L", "f_index.02.L", "f_index.03.L"}

    back = _result(restore["mpfb_set_rigify_hand_shape"])
    assert back["performed"] is True
    bones = _fixture_result("set_pose_bones", {
        "name": basemesh, "bones": restore["mpfb_set_pose_bones"]["bones"]})
    assert bones["resolution_errors"] == []
    assert _differing(before, _channels(rig), tolerance=1e-5) == []


def pose_reading_off_rest(rig, bone):
    pose_bone = rig.pose.bones[bone]
    return (any(abs(value) > 1e-4 for value in pose_bone.rotation_euler)
            or any(abs(value - 1.0) > 1e-4 for value in pose_bone.scale))


def test_names_the_package_does_not_have_are_refused(rigify):
    """commands.set_rigify_hand_shape: unknown hand, shape and finger, a hand named twice"""
    basemesh, rig = rigify
    before = posing_state(rig)
    errors = _refused(basemesh, [{"body_part": "left_foot", "shape": "open"},
                                 {"body_part": "left_hand", "shape": "peace"},
                                 {"body_part": "right_hand", "fingers": {"pinkie": {"curl": 1}}}])
    assert [error["reason"] for error in errors] == ["unknown_body_part", "unknown_shape",
                                                     "unknown_finger"]
    assert errors[1]["known_shapes"] == list(_SHAPES)
    errors = _refused(basemesh, [{"body_part": "left_hand", "shape": "open"},
                                 {"body_part": "left_hand", "shape": "fist"}])
    assert [error["reason"] for error in errors] == ["duplicate_body_part"]
    errors = _refused(basemesh, [{"body_part": "left_hand", "shape": "fist", "symmetry": True},
                                 {"body_part": "right_hand", "shape": "open"}])
    assert errors[0]["reason"] == "counterpart_named"
    errors = _refused(basemesh, [{"body_part": "left_hand",
                                  "fingers": {"index": {"curl": 1.5}}}])
    assert errors[0]["reason"] == "invalid_entry"
    assert posing_state(rig) == before


def test_a_finger_the_rig_does_not_have_is_refused_and_a_shape_skips_it(rigify):
    """commands.set_rigify_hand_shape: a renamed pinky master, then a renamed ring DEF- bone"""
    basemesh, rig = rigify
    rig.data.bones["f_pinky.01_master.R"].name = "renamed_master"
    try:
        (error,) = _refused(basemesh, [{"body_part": "right_hand",
                                        "fingers": {"pinky": {"curl": 0.5}}}])
        assert error["reason"] == "finger_not_on_rig" and error["fingers"] == ["pinky"]
        assert error["fingers_found"] == ["thumb", "index", "middle", "ring"]
        answer = _result({"name": basemesh, "hands": [{"body_part": "right_hand",
                                                       "shape": "fist"}]})
        assert answer["hands"][0]["fingers_not_on_rig"] == ["pinky"]
        assert answer["hands"][0]["matches_shape_after"] == "fist"
    finally:
        rig.data.bones["renamed_master"].name = "f_pinky.01_master.R"
    rig.data.bones["DEF-f_ring.03.R"].name = "renamed_deforming"
    try:
        (error,) = _refused(basemesh, [{"body_part": "right_hand", "shape": "fist"}])
        assert (error["reason"], error["fingers"]) == ("finger_not_as_generated", ["ring"])
        assert "DEF-f_ring.03.R" in error["message"], "names what was looked for"
    finally:
        rig.data.bones["renamed_deforming"].name = "DEF-f_ring.03.R"


def test_a_finger_whose_ik_control_is_in_charge_is_refused(rigify):
    """commands.set_rigify_hand_shape with an extra finger IK control at FK_IK 1.0"""
    basemesh, rig = rigify
    previous = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    added = rig.data.edit_bones.new("f_index.01_ik.L")
    added.head, added.tail = (0.0, 0.0, 0.0), (0.0, 0.01, 0.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.pose.bones["f_index.01_ik.L"]["FK_IK"] = 1.0
    try:
        (error,) = _refused(basemesh, [{"body_part": "left_hand", "shape": "fist"}])
        assert (error["reason"], error["finger"]) == ("finger_ik_in_charge", "index")
        rig.pose.bones["f_index.01_ik.L"]["FK_IK"] = 0.0
        assert _result({"name": basemesh, "hands": [{"body_part": "left_hand",
                                                     "shape": "fist"}]})["performed"] is True
    finally:
        bpy.ops.object.mode_set(mode="EDIT")
        rig.data.edit_bones.remove(rig.data.edit_bones["f_index.01_ik.L"])
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = previous


def test_a_driven_master_is_refused(rigify):
    """commands.set_rigify_hand_shape on a master whose rotation a driver sets"""
    basemesh, rig = rigify
    curve = rig.pose.bones["thumb.01_master.R"].driver_add("rotation_euler", 2)
    try:
        (error,) = _refused(basemesh, [{"body_part": "right_hand",
                                        "fingers": {"thumb": {"spread": 0.5}}}])
        assert (error["reason"], error["channels"]) == ("driven_channel", ["rotation"])
    finally:
        rig.pose.bones["thumb.01_master.R"].driver_remove("rotation_euler", 2)
        del curve


def test_a_lock_found_after_writing_undoes_the_whole_batch(rigify):
    """commands.set_rigify_hand_shape: the second hand breaks a lock, the first is put back"""
    basemesh, rig = rigify
    rig.pose.bones["f_middle.02.L"].rotation_euler = (0.2, 0.0, 0.0)
    rig.pose.bones["f_pinky.01_master.R"].lock_rotation[0] = True
    bpy.context.view_layer.update()
    before = posing_state(rig)
    try:
        errors = _refused(basemesh, [{"body_part": "left_hand", "shape": "fist"},
                                     {"body_part": "right_hand", "shape": "fist"}])
        assert [(error["reason"], error["index"], error["bone"]) for error in errors] == [
            ("locked_channel", 1, "f_pinky.01_master.R")]
        assert posing_state(rig) == before
    finally:
        rig.pose.bones["f_pinky.01_master.R"].lock_rotation[0] = False


def test_an_animated_master_is_written_and_flagged_and_nothing_is_keyed(rigify):
    """commands.set_rigify_hand_shape on a keyed master, with auto-keying on"""
    basemesh, rig = rigify
    tool_settings = bpy.context.scene.tool_settings
    keying = tool_settings.use_keyframe_insert_auto
    rig.pose.bones["f_index.01_master.L"].keyframe_insert("scale")
    action = rig.animation_data.action
    try:
        tool_settings.use_keyframe_insert_auto = True
        answer = _result({"name": basemesh, "hands": [
            {"body_part": "left_hand", "fingers": {"index": {"curl": 0.5}}}]})
        assert answer["hands"][0]["overwritten_on_frame_change"] == ["f_index.01_master.L"]
        keyed = [fcurve.data_path for fcurve in _fcurves(rig)]
        assert keyed == ['pose.bones["f_index.01_master.L"].scale'] * 3, "nothing was keyed"
    finally:
        tool_settings.use_keyframe_insert_auto = keying
        # Not animation_data_clear(): that would take Rigify's drivers with it.
        rig.animation_data.action = None
        bpy.data.actions.remove(action)


def _fcurves(rig):
    from bpy_extras import anim_utils  # pylint: disable=import-outside-toplevel
    animation = rig.animation_data
    channelbag = anim_utils.action_get_channelbag_for_slot(animation.action,
                                                           animation.action_slot)
    return channelbag.fcurves if channelbag else []


def test_nothing_is_borrowed_and_rest_position_is_written_and_said(rigify):
    """commands.set_rigify_hand_shape leaves mode, selection and active object alone"""
    basemesh, rig = rigify
    bystander = bpy.data.objects.new("HandShapeBystander", None)
    bpy.context.scene.collection.objects.link(bystander)
    try:
        bpy.context.view_layer.objects.active = bystander
        bystander.select_set(True)
        rig.data.pose_position = "REST"
        before = posing_state(rig)
        answer = _result({"name": basemesh, "hands": [{"body_part": "left_hand",
                                                       "shape": "grip"}]})
        after = posing_state(rig)
        assert answer["pose_position"] == "REST" and "rest position" in answer["message"]
        assert rig.data.pose_position == "REST"
        assert answer["hands"][0]["matches_shape_after"] == "grip"
        for key in ("mode", "rig_mode", "active", "selected"):
            assert after[key] == before[key], key
    finally:
        bpy.data.objects.remove(bystander, do_unlink=True)


def test_a_rig_in_edit_mode_and_a_rig_not_supported_are_refused(rigify):
    """commands.set_rigify_hand_shape on a rig in edit mode, and on a default rig"""
    basemesh, rig = rigify
    previous = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        answer = _result({"name": basemesh, "hands": [{"body_part": "left_hand",
                                                       "shape": "fist"}]})
        assert (answer["ready"], answer["blocked_by"]) == (False, "rig_in_edit_mode")
        assert answer["performed"] is False
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = previous
    services = services_or_skip()
    with Character() as character:
        rigged_character(services, character, "default")
        answer = _result({"name": character.basemesh.name, "hands": [
            {"body_part": "left_hand", "shape": "fist"}]})
        assert answer["blocked_by"] == "rig_not_supported"
        assert "nothing was changed" in answer["message"]


def test_an_open_hand_at_rest_changes_nothing(rigify):
    """commands.set_rigify_hand_shape: open on a hand at rest, and an empty batch"""
    basemesh, rig = rigify
    before = posing_state(rig)
    answer = _result({"name": basemesh, "hands": [{"body_part": "left_hand", "shape": "open"}]})
    assert answer["performed"] is False and answer["changed"] is False
    assert answer["restore_with"] == {}
    assert answer["hands"][0]["matches_shape_after"] == "open"
    assert posing_state(rig) == before
    empty = _answer("set_rigify_hand_shape", {"name": basemesh, "hands": []})["result"]
    assert empty["performed"] is False and "named nothing" in empty["message"]
