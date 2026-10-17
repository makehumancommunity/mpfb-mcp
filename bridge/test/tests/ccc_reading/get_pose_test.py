"""
``get_pose`` against a real MPFB, with poses set by the test through plain ``bpy``.

The poses are made here, never through a posing command, so that what is being
tested is the read-back alone. Each is undone at the end of its test, since the
characters are built once per module.

What only a real rig can establish, and so is asserted here:

- **An over-reach is visible both ways.** An IK hand pulled past reach with
  ``IK_Stretch`` at 1.0 makes the arm ``stretched`` and still reaching; with it
  at 0.0 the arm cannot reach, ``target_unreachable``. The karate session found
  the first only by looking.
- **A fist is not at rest.** A finger master scaled on Y is ``posed`` with its
  ``scale``, and ``RigService.get_pose_as_dict()`` - which records no scale -
  is asserted to miss it, which is the divergence the command docstring names.
- **The frame follows the rig object.** A rig moved and turned away from the
  origin reports the same landmarks at rest as before it moved, and a hand IK
  moved along the armature's +X is reported as moved to the ``left``.
- **The landmarks are on deforming bones**: with the arm in FK, moving the IK
  control moves no landmark.
- **Nothing is changed** by reading.
"""

import math

import bpy
import pytest
from mathutils import Vector

from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import posing_state
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip
from .._fixtures import with_helpers


def _result(params=None):
    return _fixture_result("get_pose", params)


def _rest(rig):
    """Back to rest: every bone's local transform and the rig object's placement."""
    for pose_bone in rig.pose.bones:
        pose_bone.location = (0.0, 0.0, 0.0)
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
        pose_bone.scale = (1.0, 1.0, 1.0)
    rig.location = (0.0, 0.0, 0.0)
    rig.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()


def _move(rig, bone, offset):
    """Move one pose bone by an armature-space offset, the way the karate session did."""
    bpy.context.view_layer.update()
    pose_bone = rig.pose.bones[bone]
    matrix = pose_bone.matrix.copy()
    matrix.translation += Vector(offset)
    pose_bone.matrix = matrix
    bpy.context.view_layer.update()


@pytest.fixture(scope="module", name="human_toes")
def _human_toes():
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        yield character.basemesh.name, rig


@pytest.fixture(name="rigify")
def _rigify(human_toes):
    """The generated rig, put back to rest and its switches to default after each test."""
    basemesh, rig = human_toes
    yield basemesh, rig
    for switch_bone in ("upper_arm_parent.L", "upper_arm_parent.R"):
        rig.pose.bones[switch_bone]["IK_Stretch"] = 1.0
        rig.pose.bones[switch_bone]["IK_FK"] = 0.0
    _rest(rig)


def test_a_fresh_rig_is_at_rest(rigify):
    """commands.get_pose on a generated rig nobody has touched"""
    basemesh, rig = rigify
    answer = _result({"name": basemesh})

    assert answer["at_rest"] is True
    assert answer["posed_count"] == 0
    assert all(entries == [] for entries in answer["posed"].values())
    assert answer["switch_values"]["left_arm"]["IK_FK"] == 0.0
    assert answer["switch_parents"]["left_arm"]["IK_parent"] == "Root"
    for name, landmark in answer["landmarks"].items():
        assert landmark["now"] == landmark["rest"], name
        assert rig.data.bones[landmark["bone"]].use_deform, name
    for part, limb in answer["limbs"].items():
        assert limb["in_charge"] == "ik", part
        assert limb["stretched"] is False, part
        assert limb["target_unreachable"] is False, part
        assert limb["reach_ratio"] < 1.0, part
    assert set(answer["limb_measures"]) == {"reach_ratio", "stretched", "target_unreachable"}


def test_an_over_reach_with_stretch_on_stretches_the_arm(rigify):
    """commands.get_pose with hand_ik.L pulled 0.5 m past reach and IK_Stretch at 1.0"""
    basemesh, rig = rigify
    _move(rig, "hand_ik.L", (0.5, 0.0, 0.0))
    answer = _result({"name": basemesh})

    arm = answer["limbs"]["left_arm"]
    assert arm["stretched"] is True
    assert arm["reach_ratio"] > 1.0
    assert arm["target_unreachable"] is False, "a stretching arm reaches its control"
    assert answer["landmarks"]["left_hand"]["now"]["left"] > \
        answer["landmarks"]["left_hand"]["rest"]["left"] + 0.4
    assert "left_arm is" in answer["message"]


def test_an_over_reach_with_stretch_off_cannot_reach(rigify):
    """commands.get_pose with hand_ik.L pulled 0.5 m past reach and IK_Stretch at 0.0"""
    basemesh, rig = rigify
    rig.pose.bones["upper_arm_parent.L"]["IK_Stretch"] = 0.0
    _move(rig, "hand_ik.L", (0.5, 0.0, 0.0))
    answer = _result({"name": basemesh})

    arm = answer["limbs"]["left_arm"]
    assert arm["target_unreachable"] is True
    assert arm["length"] < arm["rest_length"] * 1.1, "the arm does not grow to meet it"
    assert answer["switch_values"]["left_arm"]["IK_Stretch"] == 0.0
    assert "cannot reach hand_ik.L" in answer["message"]


def test_a_fist_is_posed_by_scale_alone(rigify):
    """commands.get_pose with a finger master scaled on Y, which get_pose_as_dict() misses"""
    basemesh, rig = rigify
    services = services_or_skip()
    rig.pose.bones["f_index.01_master.L"].scale = (1.0, 0.45, 1.0)
    bpy.context.view_layer.update()
    answer = _result({"name": basemesh})

    assert answer["at_rest"] is False
    assert answer["counts_by_body_part"]["left_hand"] == 1
    (entry,) = answer["posed"]["left_hand"]
    assert entry["bone"] == "f_index.01_master.L"
    assert entry["role"] == "finger_master"
    assert entry["scale"] == {"x": 1.0, "y": 0.45, "z": 1.0}
    assert entry["rotation"] == {"axis": None, "degrees": 0.0}
    mpfb_pose = services["RigService"].get_pose_as_dict(rig)
    assert "f_index.01_master.L" not in mpfb_pose["bone_rotations"]
    assert "f_index.01_master.L" not in mpfb_pose["bone_translations"], \
        "MPFB records no scale, which is why this command departs from it"


def test_the_frame_follows_the_rig_object(rigify):
    """commands.get_pose on a rig moved and turned away from the origin"""
    basemesh, rig = rigify
    at_origin = _result({"name": basemesh})["landmarks"]
    rig.location = (3.0, -2.0, 0.0)
    rig.rotation_euler = (0.0, 0.0, math.radians(135.0))
    bpy.context.view_layer.update()
    answer = _result({"name": basemesh})

    assert answer["character_frame"]["origin"] == [3.0, -2.0, 0.0]
    for name, landmark in answer["landmarks"].items():
        assert landmark["rest"] == at_origin[name]["rest"], name
    # Moving the bone along the armature's -X is moving it to the character's right.
    pose_bone = rig.pose.bones["hand_ik.R"]
    matrix = pose_bone.matrix.copy()
    matrix.translation += Vector((-0.2, 0.0, 0.0))
    pose_bone.matrix = matrix
    bpy.context.view_layer.update()
    (entry,) = _result({"name": basemesh})["posed"]["right_arm"]
    assert entry["moved_by"] == {"forward": 0.0, "left": -0.2, "up": 0.0}
    rest = at_origin["right_hand"]["rest"]
    assert entry["head"] == {"forward": rest["forward"], "left": round(rest["left"] - 0.2, 3),
                             "up": rest["up"]}


def test_landmarks_are_where_the_body_is_not_where_a_control_is(rigify):
    """commands.get_pose with the left arm in FK and its IK control moved"""
    basemesh, rig = rigify
    rig.pose.bones["upper_arm_parent.L"]["IK_FK"] = 1.0
    _move(rig, "hand_ik.L", (0.0, -0.3, 0.0))
    answer = _result({"name": basemesh})

    assert answer["limbs"]["left_arm"]["in_charge"] == "fk"
    assert answer["limbs"]["left_arm"]["target_unreachable"] is None, \
        "IK is not in charge, so whether it could reach is not computed"
    assert answer["landmarks"]["left_hand"]["now"] == answer["landmarks"]["left_hand"]["rest"]
    assert [entry["bone"] for entry in answer["posed"]["left_arm"]] == ["hand_ik.L"]


def test_a_posed_face_behind_the_filter_is_still_not_at_rest(rigify):
    """commands.get_pose's body_parts filter and at_rest"""
    basemesh, rig = rigify
    rig.pose.bones["jaw_master"].rotation_quaternion = (0.98, 0.2, 0.0, 0.0)
    bpy.context.view_layer.update()
    answer = _result({"name": basemesh})

    assert "face" not in answer["posed"]
    assert answer["counts_by_body_part"]["face"] == 1
    assert answer["at_rest"] is False
    face = _result({"name": basemesh, "body_parts": ["face"]})
    assert [entry["bone"] for entry in face["posed"]["face"]] == ["jaw_master"]


def test_a_default_rigs_helper_past_reach_cannot_reach():
    """commands.get_pose on a default rig whose hand helper is pulled past reach"""
    services = services_or_skip()
    with Character() as character:
        rig = with_helpers(rigged_character(services, character, "default"), arm="LOWERUPPER")
        _move(rig, "left_hand_ik", (0.6, 0.0, 0.0))
        answer = _result({"name": character.basemesh.name})

        arm = answer["limbs"]["left_arm"]
        assert arm["in_charge"] == "ik"
        assert arm["ik_control"] == "left_hand_ik"
        assert arm["stretched"] is False
        assert arm["target_unreachable"] is True
        assert answer["switch_values"] == {}
        assert answer["limbs"]["right_arm"]["target_unreachable"] is False


def test_an_unclassified_rig_reports_bones_and_nothing_it_cannot_compute():
    """commands.get_pose on a mixamo rig"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "mixamo")
        rig.pose.bones["mixamorig:LeftArm"].rotation_euler = (0.0, 0.0, 0.5)
        bpy.context.view_layer.update()
        answer = _result({"name": character.basemesh.name})

        assert answer["classified"] is False
        assert answer["posed"] is None
        assert [entry["bone"] for entry in answer["posed_bones"]] == ["mixamorig:LeftArm"]
        assert "role" not in answer["posed_bones"][0]
        for key in ("landmarks", "limbs", "switch_values", "counts_by_body_part"):
            assert answer[key] is None, key


def test_reading_changes_nothing(rigify):
    """commands.get_pose leaves mode, selection, active object, pose and switches alone"""
    basemesh, rig = rigify
    _move(rig, "hand_ik.L", (0.2, -0.1, 0.0))
    bystander = bpy.data.objects.new("PoseBystander", None)
    bpy.context.scene.collection.objects.link(bystander)
    try:
        bpy.context.view_layer.objects.active = bystander
        bystander.select_set(True)
        before = posing_state(rig)
        assert dispatch("get_pose", {"name": basemesh})["status"] == "ok"
        assert posing_state(rig) == before
    finally:
        bpy.data.objects.remove(bystander, do_unlink=True)
