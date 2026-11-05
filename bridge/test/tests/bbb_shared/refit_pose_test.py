"""
``shared/refit_pose.py``, called directly, with what a refit does stood in for by the block.

**The block loses the pose by hand**, so each test says exactly what was lost, including what no real
refit loses today: a rotation mode, a bone, a property. That the module is right about what a real
regenerate does is ``eee_composite/keep_pose_test.py``'s. Here it is what the comparison and the restore
do with a given difference, on the one rig MPFB builds quickly, and on a generated one where drivers
matter.
"""

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import rigged_character
from .._fixtures import services_or_skip


def _refit_pose():
    return bridge_module("shared.refit_pose")


def _resolution():
    return bridge_module("mpfb_resolution").resolve()


@pytest.fixture(name="rigged", scope="module")
def _rigged():
    services = services_or_skip()
    with Character() as character:
        yield character.basemesh, rigged_character(services, character, "default")


@pytest.fixture(autouse=True, name="rest")
def _rest(rigged):
    yield
    armature = rigged[1]
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "XYZ"
        pose_bone.location = (0.0, 0.0, 0.0)
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.scale = (1.0, 1.0, 1.0)
        if "bridge_test" in pose_bone:
            del pose_bone["bridge_test"]
    armature.data.pose_position = "POSE"
    bpy.context.view_layer.update()


def _kept(basemesh, keep_pose=True):
    return _refit_pose().kept(_resolution(), basemesh, keep_pose)


def _channels(pose_bone):
    return (tuple(pose_bone.location), tuple(pose_bone.rotation_euler), tuple(pose_bone.scale))


def _a_bone(armature):
    return next(pose_bone for pose_bone in armature.pose.bones if pose_bone.parent is not None)


def test_nothing_lost_is_unchanged_and_nothing_is_written(rigged):
    basemesh, armature = rigged
    bone = _a_bone(armature)
    bone.rotation_euler = (0.3, 0.0, 0.0)
    with _kept(basemesh) as pose:
        pass
    assert pose.after_refit == "unchanged"
    assert pose.answer() == {"pose_after_refit": "unchanged"}
    assert pose.sentence == ""
    assert abs(bone.rotation_euler[0] - 0.3) < 1e-6


def test_a_lost_channel_comes_back_exactly(rigged):
    basemesh, armature = rigged
    bone = _a_bone(armature)
    bone.rotation_euler = (0.3, 0.1, -0.2)
    bone.scale = (1.5, 1.0, 1.0)
    before = _channels(bone)
    with _kept(basemesh) as pose:
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)
    assert pose.after_refit == "kept"
    assert pose.details["pose_kept_count"] == 1
    assert pose.details["bones_not_restored"] == []
    assert _channels(bone) == before


def test_a_lost_custom_property_comes_back(rigged):
    basemesh, armature = rigged
    bone = _a_bone(armature)
    bone["bridge_test"] = 0.75
    with _kept(basemesh) as pose:
        bone["bridge_test"] = 0.0
    assert pose.after_refit == "kept"
    assert abs(bone["bridge_test"] - 0.75) < 1e-9


def test_a_string_property_is_no_part_of_a_pose(rigged):
    basemesh, armature = rigged
    bone = _a_bone(armature)
    bone["bridge_test"] = "words"
    with _kept(basemesh) as pose:
        bone["bridge_test"] = "other words"
    assert pose.after_refit == "unchanged"


def test_a_lost_rotation_mode_comes_back_before_its_channels(rigged):
    basemesh, armature = rigged
    bone = _a_bone(armature)
    bone.rotation_mode = "QUATERNION"
    bone.rotation_quaternion = (0.9, 0.1, 0.2, 0.3)
    held = tuple(bone.rotation_quaternion)
    with _kept(basemesh) as pose:
        bone.rotation_mode = "XYZ"
    assert pose.after_refit == "kept"
    assert bone.rotation_mode == "QUATERNION"
    assert tuple(bone.rotation_quaternion) == held


def test_a_bone_that_is_gone_is_named_and_the_rest_come_back(rigged):
    services = services_or_skip()
    with Character() as character:
        armature = rigged_character(services, character, "default")
        survivor = _a_bone(armature)
        survivor_name = survivor.name
        leaf = next(pose_bone for pose_bone in armature.pose.bones if not pose_bone.children)
        leaf_name = leaf.name
        assert leaf_name != survivor_name
        leaf["bridge_test"] = 0.5
        armature.pose.bones[survivor_name].location = (0.01, 0.0, 0.0)
        with _kept(character.basemesh) as pose:
            armature.pose.bones[survivor_name].location = (0.0, 0.0, 0.0)
            bpy.context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode="EDIT")
            armature.data.edit_bones.remove(armature.data.edit_bones[leaf_name])
            bpy.ops.object.mode_set(mode="OBJECT")
        assert pose.after_refit == "kept"
        assert pose.details["bones_not_restored"] == [leaf_name]
        assert abs(armature.pose.bones[survivor_name].location[0] - 0.01) < 1e-6


def test_keep_pose_false_leaves_what_the_refit_left_and_hands_back_the_way(rigged):
    basemesh, armature = rigged
    bone = _a_bone(armature)
    bone.rotation_euler = (0.3, 0.0, 0.0)
    with _kept(basemesh, keep_pose=False) as pose:
        bone.rotation_euler = (0.0, 0.0, 0.0)
    assert pose.after_refit == "reset"
    assert pose.details["pose_reset_count"] == 1
    assert _channels(bone)[1] == (0.0, 0.0, 0.0), "reading the way back must not leave it applied"
    entries = pose.details["restore_with"]["mpfb_set_pose_bones"]["bones"]
    assert [entry["bone"] for entry in entries] == [bone.name]
    assert "keep_pose is false" in pose.sentence


def test_a_refit_that_raises_still_restores_and_still_raises(rigged):
    basemesh, armature = rigged
    bone = _a_bone(armature)
    bone.rotation_euler = (0.3, 0.0, 0.0)
    with pytest.raises(RuntimeError, match="the refit failed"):
        with _kept(basemesh):
            bone.rotation_euler = (0.0, 0.0, 0.0)
            raise RuntimeError("the refit failed")
    assert abs(bone.rotation_euler[0] - 0.3) < 1e-6


def test_a_refit_that_raises_with_keep_pose_false_is_left_alone(rigged):
    basemesh, armature = rigged
    bone = _a_bone(armature)
    bone.rotation_euler = (0.3, 0.0, 0.0)
    with pytest.raises(RuntimeError, match="the refit failed"):
        with _kept(basemesh, keep_pose=False):
            bone.rotation_euler = (0.0, 0.0, 0.0)
            raise RuntimeError("the refit failed")
    assert bone.rotation_euler[0] == 0.0


def test_a_rest_position_shown_is_put_back(rigged):
    """With a sub-rig, ``refit()`` sets ``pose_position`` to POSE however it found it."""
    basemesh, armature = rigged
    armature.data.pose_position = "REST"
    with _kept(basemesh) as pose:
        armature.data.pose_position = "POSE"
    assert pose.after_refit == "unchanged"
    assert armature.data.pose_position == "REST"


def test_a_character_with_no_rig_has_nothing_to_lose():
    services_or_skip()
    with Character() as character:
        with _kept(character.basemesh) as pose:
            pass
    assert pose.after_refit == "unchanged"


def test_no_refit_is_null_rather_than_unchanged():
    outcome = _refit_pose().no_refit()
    assert outcome.answer() == {"pose_after_refit": None}
    answer = _refit_pose().answered({"blocked_by": "x"})
    assert answer["pose_after_refit"] is None
    assert _refit_pose().answered({"pose_after_refit": "kept"})["pose_after_refit"] == "kept"


def test_a_driven_channel_is_neither_compared_nor_written():
    """What a driver sets follows the controls, so a difference there is not a lost pose."""
    services = services_or_skip()
    with Character() as character:
        armature = rigged_character(services, character, "default")
        bone = _a_bone(armature)
        curve = armature.driver_add('pose.bones["{:s}"].location'.format(bone.name), 0)
        curve.driver.expression = "0.0"
        try:
            bone.location = (0.25, 0.0, 0.0)
            with _kept(character.basemesh) as pose:
                bone.location = (0.0, 0.0, 0.0)
            assert pose.after_refit == "unchanged"
        finally:
            armature.driver_remove('pose.bones["{:s}"].location'.format(bone.name), 0)
