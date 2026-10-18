"""
``reset_pose`` against a real MPFB, with poses made by the test in plain ``bpy``.

What only a real rig can establish, and so is asserted here:

- **``restore_with`` is a way back, exactly.** A pose with moved, rotated and
  scaled controls, a twisted IK chain and changed switches is reset, and the
  arguments the answer hands back, sent to ``set_pose_switches`` and then to
  ``set_pose_bones``, put every channel and every switch back to within 1e-5 -
  except the bones ``not_restorable`` names, whose chain ``IK_FK`` had handed
  away, and which moved nothing.
- **The default is every body part, the face included**; ``body_parts`` narrows
  it and leaves the rest alone; switches are left alone unless asked.
- **A character at rest** answers ``performed: false`` with an empty
  ``restore_with``.
- **What is not a control is not touched, and is named** when it is off rest in
  a channel no driver sets (``left_off_rest``) - while the ``MCH-`` bones
  Rigify's finger drivers move are not.
- **A default rig's helpers are reset**, and an FK bone a helper drives is
  ``not_restorable``. An unclassified rig is reset whole, and refuses
  ``body_parts``.
"""

import math

import bpy
import pytest
from mathutils import Matrix
from mathutils import Quaternion
from mathutils import Vector

from .._fixtures import Character
from .._fixtures import posing_state
from .._fixtures import rest_pose
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip
from .._fixtures import with_helpers


def _result(params):
    return _fixture_result("reset_pose", params)


def _move(rig, bone, offset):
    bpy.context.view_layer.update()
    pose_bone = rig.pose.bones[bone]
    matrix = pose_bone.matrix.copy()
    matrix.translation += Vector(offset)
    pose_bone.matrix = matrix
    bpy.context.view_layer.update()


def _channels(rig):
    """Every bone's channels and every switch, unrounded."""
    answer = {}
    for pose_bone in rig.pose.bones:
        quaternion = tuple(pose_bone.rotation_quaternion)
        if quaternion[0] < 0:
            quaternion = tuple(-value for value in quaternion)
        answer[pose_bone.name] = dict(
            location=tuple(pose_bone.location), quaternion=quaternion,
            euler=tuple(pose_bone.rotation_euler), scale=tuple(pose_bone.scale),
            switches={key: float(pose_bone[key]) for key in pose_bone.keys()
                      if isinstance(pose_bone[key], (bool, int, float))})
    return answer


def _differences(first, second, skip=()):
    found = []
    for name, channels in first.items():
        if name in skip:
            continue
        for key, values in channels.items():
            if key == "switches":
                if values != second[name][key]:
                    found.append((name, key))
            elif any(abs(a - b) > 1e-5 for a, b in zip(values, second[name][key])):
                found.append((name, key))
    return found


@pytest.fixture(scope="module", name="human_toes")
def _human_toes():
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        rig.location = (0.5, 1.5, 0.0)
        rig.rotation_euler = (0.0, 0.0, math.radians(200.0))
        bpy.context.view_layer.update()
        yield character.basemesh.name, rig


@pytest.fixture(name="rigify")
def _rigify(human_toes):
    rest_pose(human_toes[1])
    yield human_toes
    rest_pose(human_toes[1])


def _karate(rig):
    """A pose touching every kind of channel, a switch of each type, and the face."""
    bones = rig.pose.bones
    bones["upper_arm_parent.L"]["IK_parent"] = 2
    bones["upper_arm_parent.R"]["pole_vector"] = True
    bones["thigh_parent.L"]["IK_Stretch"] = 0.0
    bpy.context.view_layer.update()
    _move(rig, "torso", (0.0, 0.05, -0.25))
    bones["chest"].rotation_quaternion = Quaternion((0.97, 0.05, 0.0, 0.2)).normalized()
    _move(rig, "hand_ik.L", (-0.1, -0.25, 0.2))
    _move(rig, "hand_ik.R", (0.1, -0.2, 0.25))
    _move(rig, "upper_arm_ik_target.R", (0.0, 0.1, -0.1))
    bones["upper_arm_ik.L"].rotation_euler = (0.0, 0.4, 0.0)
    for finger in ("f_index", "f_middle", "f_ring", "f_pinky"):
        bones["{:s}.01_master.L".format(finger)].scale = (1.0, 0.45, 1.0)
    bones["jaw_master"].rotation_quaternion = Quaternion((0.99, 0.12, 0.0, 0.0)).normalized()
    _move(rig, "foot_ik.R", (0.0, -0.3, 0.1))
    bpy.context.view_layer.update()


def test_a_reset_and_its_restore_with_give_back_the_pose_exactly(rigify):
    """commands.reset_pose with include_switches, then restore_with through both writers"""
    basemesh, rig = rigify
    _karate(rig)
    # An FK bone posed while its arm is in IK: reset, and not restorable.
    rig.pose.bones["forearm_fk.L"].rotation_euler = (0.3, 0.0, 0.0)
    bpy.context.view_layer.update()
    posed = _channels(rig)
    answer = _result({"name": basemesh, "include_switches": True})

    assert answer["performed"] is True and answer["reset"] is True
    assert "jaw_master" in answer["bones_reset"], "the face is reset by default"
    assert "face" in answer["requested_body_parts"]
    assert answer["not_restorable"] == [{"bone": "forearm_fk.L",
                                         "reason": "chain_not_in_charge"}]
    assert {(entry["body_part"], entry["switch"]) for entry in answer["switches_reset"]} == {
        ("left_arm", "IK_parent"), ("right_arm", "pole_vector"), ("left_leg", "IK_Stretch")}
    for name, channels in _channels(rig).items():
        if name in answer["bones_reset"]:
            assert channels["location"] == (0.0, 0.0, 0.0), name
    assert not rig.pose.bones["upper_arm_parent.R"]["pole_vector"]
    restore = answer["restore_with"]
    assert list(restore) == ["mpfb_set_pose_switches", "mpfb_set_pose_bones"]
    assert all(entry["raw"] is True for entry in restore["mpfb_set_pose_switches"]["switches"])

    switched = _fixture_result("set_pose_switches", restore["mpfb_set_pose_switches"])
    assert switched["resolution_errors"] == []
    written = _fixture_result("set_pose_bones", restore["mpfb_set_pose_bones"])
    assert written["resolution_errors"] == [] and written["performed"] is True
    assert _differences(posed, _channels(rig), skip={"forearm_fk.L"}) == []


def test_body_parts_narrow_the_reset_and_switches_are_left_alone(rigify):
    """commands.reset_pose with body_parts, and without include_switches"""
    basemesh, rig = rigify
    _karate(rig)
    before = _channels(rig)
    answer = _result({"name": basemesh, "body_parts": ["left_hand", "face"]})

    assert set(answer["bones_reset"]) == {"f_index.01_master.L", "f_middle.01_master.L",
                                          "f_ring.01_master.L", "f_pinky.01_master.L",
                                          "jaw_master"}
    assert answer["switches_reset"] == []
    assert "mpfb_set_pose_switches" not in answer["restore_with"]
    after = _channels(rig)
    assert after["torso"] == before["torso"], "another body part is left alone"
    assert after["upper_arm_parent.L"]["switches"] == before["upper_arm_parent.L"]["switches"]


def test_a_character_at_rest_has_nothing_to_restore(rigify):
    """commands.reset_pose on a rig nobody has touched"""
    basemesh, rig = rigify
    before = posing_state(rig)
    answer = _result({"name": basemesh})
    assert answer["performed"] is False and answer["reset"] is False
    assert answer["restore_with"] == {} and answer["bones_reset"] == []
    assert answer["message"] == "'{:s}' is already at rest.".format(rig.name)
    assert posing_state(rig) == before


def test_what_is_not_a_control_is_left_alone_and_named(rigify):
    """commands.reset_pose with an ORG bone posed, and finger drivers moving MCH bones"""
    basemesh, rig = rigify
    rig.pose.bones["ORG-spine.003"].location = (0.0, 0.02, 0.0)
    rig.pose.bones["f_index.01_master.L"].scale = (1.0, 0.45, 1.0)
    bpy.context.view_layer.update()
    answer = _result({"name": basemesh})
    assert "ORG-spine.003" not in answer["bones_reset"]
    assert answer["left_off_rest"] == ["ORG-spine.003"], \
        "the MCH bones the finger drivers move are not reported"
    assert tuple(rig.pose.bones["ORG-spine.003"].location) != (0.0, 0.0, 0.0)


def test_a_rig_in_edit_mode_and_an_unknown_body_part_are_refused(rigify):
    """commands.reset_pose's refusals change nothing"""
    basemesh, rig = rigify
    _karate(rig)
    before = posing_state(rig)
    unknown = _result({"name": basemesh, "body_parts": ["tail"]})
    assert unknown["blocked_by"] == "unknown_body_parts" and unknown["restore_with"] == {}
    previous = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        assert _result({"name": basemesh})["blocked_by"] == "rig_in_edit_mode"
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = previous
    assert posing_state(rig) == before


def test_a_default_rigs_helpers_are_reset_and_what_they_drive_is_not_restored():
    """commands.reset_pose on a default rig with MPFB's arm helpers"""
    services = services_or_skip()
    with Character() as character:
        rig = with_helpers(rigged_character(services, character, "default"), arm="LOWERUPPER")
        _move(rig, "left_hand_ik", (0.1, -0.2, 0.3))
        # matrix_basis, so that it lands in whichever rotation mode the bone uses.
        rig.pose.bones["lowerarm02.L"].matrix_basis = Matrix.Rotation(0.6, 4, "X")
        bpy.context.view_layer.update()
        answer = _result({"name": character.basemesh.name})
        assert "left_hand_ik" in answer["bones_reset"]
        assert answer["not_restorable"] == [{"bone": "lowerarm02.L",
                                             "reason": "driven_by_helper"}]
        assert [entry["bone"] for entry in
                answer["restore_with"]["mpfb_set_pose_bones"]["bones"]] == ["left_hand_ik"]


def test_an_unclassified_rig_is_reset_whole_and_refuses_body_parts():
    """commands.reset_pose on a mixamo rig"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "mixamo")
        rig.pose.bones["mixamorig:LeftArm"].rotation_euler = (0.0, 0.0, 0.5)
        bpy.context.view_layer.update()
        name = character.basemesh.name
        refused = _result({"name": name, "body_parts": ["left_arm"]})
        assert refused["blocked_by"] == "rig_not_classified"
        assert tuple(rig.pose.bones["mixamorig:LeftArm"].rotation_euler) != (0.0, 0.0, 0.0)
        answer = _result({"name": name})
        assert answer["classified"] is False and answer["requested_body_parts"] is None
        assert answer["bones_reset"] == ["mixamorig:LeftArm"]
        assert answer["landmarks"] is None
        written = _fixture_result("set_pose_bones", answer["restore_with"]["mpfb_set_pose_bones"])
        assert written["performed"] is True
        assert abs(rig.pose.bones["mixamorig:LeftArm"].rotation_euler[2] - 0.5) < 1e-5
        refused_switches = _fixture_result("set_pose_switches", {"name": name, "switches": [
            {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}]})
        assert refused_switches["blocked_by"] == "rig_has_no_switches"
