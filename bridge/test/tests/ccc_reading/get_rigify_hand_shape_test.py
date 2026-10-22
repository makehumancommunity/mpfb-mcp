"""
``get_rigify_hand_shape`` against a real MPFB, on a generated ``human_toes`` rig moved and turned
away from the origin.

What only a real rig can establish:

- **A hand at rest is ``open``**, with every finger expressible, ``curl`` and
  ``spread`` 0 and the joints measured at 0.
- **A master scaled to 0.45 on Y by plain ``bpy``** - the karate session's fist
  - reads as what that scale does: the later joints at 99 degrees and the
  knuckle at rest, which is a hook rather than a curl, so ``expressible:
  false`` and a fitted ``curl``. The calibration puts a fist's later joints at
  35 to 45 degrees; 99 with the knuckle bent buries the fingertips in the palm.
- **``tip`` is in the character frame** on a moved and turned rig: the same
  fingertip, worked out here from its world position and the rig object alone.
- **Every rig that is not generated from MPFB's own meta-rigs is refused**
  with ``rig_not_supported`` and ``supported_rigs``: the default rig,
  ``mixamo``, and the ``game_engine`` rig MPFB's conversion generates. A
  meta-rig keeps ``rigify_not_generated``, and a body part that is not a hand
  is ``unknown_body_parts``.
- **Nothing changes**: mode, selection, active object and every pose channel.
"""

import math

import bpy
import pytest
from mathutils import Vector

from .._fixtures import Character
from .._fixtures import posing_state
from .._fixtures import rest_pose
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip


def _result(params):
    return _fixture_result("get_rigify_hand_shape", params)


@pytest.fixture(scope="module", name="human_toes")
def _human_toes():
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        rig.location = (2.0, 1.0, 0.0)
        rig.rotation_euler = (0.0, 0.0, math.radians(135.0))
        bpy.context.view_layer.update()
        yield character.basemesh.name, rig


@pytest.fixture(name="rigify")
def _rigify(human_toes):
    _basemesh, rig = human_toes
    rest_pose(rig)
    bpy.context.view_layer.update()
    yield human_toes
    rest_pose(rig)


def test_a_hand_at_rest_is_open(rigify):
    """commands.get_rigify_hand_shape: both hands of a character at rest"""
    basemesh, rig = rigify
    answer = _result({"name": basemesh})

    assert answer["blocked_by"] is None and answer["rig_object_name"] == rig.name
    assert answer["rig_identified_as"] == "rigify_generated.human_toes"
    assert set(answer["hands"]) == {"left_hand", "right_hand"}
    for hand in answer["hands"].values():
        assert hand["matches_shape"] == "open"
        assert list(hand["fingers"]) == ["thumb", "index", "middle", "ring", "pinky"]
        assert hand["finger_errors"] == {} and hand["palm_off_rest"] is False
        for finger in hand["fingers"].values():
            assert finger["expressible"] is True
            assert (finger["curl"], finger["spread"]) == (0.0, 0.0)
            assert finger["joint_degrees"] == [0.0, 0.0, 0.0]
    assert set(answer["known_shapes"]) == {"open", "relaxed", "fist", "pointing", "grip",
                                           "pinch"}
    assert "least-squares" in answer["amounts_measure"]
    assert _result({"name": basemesh, "body_parts": ["right_hand"]})["hands"].keys() == \
        {"right_hand"}


def test_the_karate_fist_reads_as_a_hook(rigify):
    """commands.get_rigify_hand_shape: a master scaled to 0.45 on Y by plain bpy"""
    basemesh, rig = rigify
    rig.pose.bones["f_index.01_master.L"].scale = (1.0, 0.45, 1.0)
    bpy.context.view_layer.update()

    index = _result({"name": basemesh})["hands"]["left_hand"]["fingers"]["index"]

    assert index["joint_degrees"][0] == pytest.approx(0.0, abs=0.5)
    assert index["joint_degrees"][1] == pytest.approx(99.0, abs=0.5)
    assert index["joint_degrees"][2] == pytest.approx(99.0, abs=0.5)
    assert index["expressible"] is False
    assert index["not_expressible_because"] == ["knuckle_and_joints_disagree"]
    assert 0.5 < index["curl"] < 1.0, "the least-squares fit, not 2.8 from the scale alone"


def test_tip_is_in_the_character_frame(rigify):
    """commands.get_rigify_hand_shape: tip on a moved and turned rig"""
    basemesh, rig = rigify
    rig.pose.bones["f_middle.01_master.R"].rotation_euler = (0.6, 0.0, 0.1)
    bpy.context.view_layer.update()

    tip = _result({"name": basemesh})["hands"]["right_hand"]["fingers"]["middle"]["tip"]

    world = rig.matrix_world @ rig.pose.bones["DEF-f_middle.03.R"].tail
    offset = world - rig.matrix_world.to_translation()
    turned = rig.matrix_world.to_3x3().normalized()
    expected = {"forward": offset.dot(turned @ Vector((0.0, -1.0, 0.0))),
                "left": offset.dot(turned @ Vector((1.0, 0.0, 0.0))),
                "up": offset.dot(Vector((0.0, 0.0, 1.0)))}
    for axis, value in expected.items():
        assert tip[axis] == pytest.approx(value, abs=0.0011), axis


def test_nothing_changes(rigify):
    """commands.get_rigify_hand_shape is read-only"""
    basemesh, rig = rigify
    rig.pose.bones["f_ring.01_master.L"].scale = (1.0, 0.8, 1.0)
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    before = posing_state(rig)

    answer = _result({"name": basemesh})

    assert posing_state(rig) == before
    assert rig.data.pose_position == "REST"
    assert answer["pose_position"] == "REST"
    assert answer["hands"]["left_hand"]["fingers"]["ring"]["joint_degrees"][1] == \
        pytest.approx(0.2 * 180.0, abs=0.1), "read in its pose, although it shows its rest"


def test_a_body_part_that_is_not_a_hand_is_refused(rigify):
    """commands.get_rigify_hand_shape: body_parts ['left_arm']"""
    basemesh, _rig = rigify
    answer = _result({"name": basemesh, "body_parts": ["left_hand", "left_arm"]})

    assert answer["blocked_by"] == "unknown_body_parts"
    assert answer["unknown_body_parts"] == ["left_arm"]
    assert answer["known_body_parts"] == ["left_hand", "right_hand"]
    assert answer["hands"] is None and "known_shapes" in answer


@pytest.mark.parametrize("rig_kind,identified", [
    ("default", "default"), ("mixamo", "mixamo"),
    ("generated:game_engine", "rigify_generated.game_engine")])
def test_every_other_rig_is_refused(rig_kind, identified):
    """commands.get_rigify_hand_shape on the default, mixamo and generated game_engine rigs"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, rig_kind)
        answer = _result({"name": character.basemesh.name})

        assert answer["blocked_by"] == "rig_not_supported"
        assert answer["rig_identified_as"] == identified
        assert answer["rig_object_name"] == rig.name
        assert answer["supported_rigs"] == ["rigify_generated.human",
                                            "rigify_generated.human_toes"]
        assert "mpfb_set_pose_bones" in answer["message"]


def test_a_meta_rig_keeps_its_own_refusal():
    """commands.get_rigify_hand_shape on a character rigged with a meta-rig"""
    services = services_or_skip()
    with Character() as character:
        rigged_character(services, character, "rigify.human_toes")
        answer = _result({"name": character.basemesh.name})

        assert answer["blocked_by"] == "rigify_not_generated"
