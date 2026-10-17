"""
``get_pose_controls`` against a real MPFB, on one character per rig family.

One character per family FR 041 classifies - a default rig, a default rig with
MPFB's helpers, a generated ``human_toes`` and a generated ``game_engine`` - plus
one it does not (``mixamo``), each built **once per module**, because
generating a Rigify rig takes seconds and every test here only reads.

What only a real rig can establish, and so is asserted here:

- **The bones the karate session moved by hand are controls with the role it
  used them for** (FR 041's live check, restated as a test): ``torso`` and
  ``hips`` are ``body``, ``hand_ik.L`` an ``ik_control``,
  ``upper_arm_ik_target.L`` a ``pole``, ``f_index.01_master.L`` a
  ``finger_master``.
- **The parent names are Rigify's own.** They are read off the property's
  ``items``; Rigify writes the same list into the generated ``rig_ui.py``, and
  this test reads that script - as data, searched and never executed - to
  check the two agree. That is the check FR 041 required before reading names
  live rather than out of the script.
- **``hidden_by_default`` is what Rigify hid**: each control's flag equals its
  collection's visibility on a freshly generated rig.
- **The game_engine rig is classified without collections**, every control
  given a body part, with its ``_l``/``_r`` sides.
- **Nothing is changed**: mode, active object, selection, every bone's pose and
  every switch, before and after.
"""

import json
import re

import bpy
import pytest

from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import posing_state
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip
from .._fixtures import with_helpers


def _result(params=None):
    return _fixture_result("get_pose_controls", params)


@pytest.fixture(scope="module", name="human_toes")
def _human_toes():
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        yield character.basemesh.name, rig


@pytest.fixture(scope="module", name="game_engine")
def _game_engine():
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:game_engine")
        yield character.basemesh.name, rig


@pytest.fixture(scope="module", name="default_with_helpers")
def _default_with_helpers():
    services = services_or_skip()
    with Character() as character:
        rig = with_helpers(rigged_character(services, character, "default"),
                           arm="LOWERUPPER", leg="LOWERUPPER", finger="GRIP_AND_MASTER", eye=True)
        yield character.basemesh.name, rig


def _controls_by_name(answer):
    return {entry["bone"]: dict(entry, body_part=part)
            for part, entries in answer["controls"].items() for entry in entries}


def test_the_karate_sessions_bones_are_controls_with_the_role_it_used(human_toes):
    """commands.get_pose_controls on a generated human_toes rig"""
    basemesh, rig = human_toes
    answer = _result({"name": basemesh})

    assert answer["ready"] is True
    assert answer["rig_object_name"] == rig.name
    assert answer["rig_identified_as"] == "rigify_generated.human_toes"
    assert answer["classified"] is True
    assert answer["unassigned_bones"] == []
    controls = _controls_by_name(answer)
    expected = {
        "torso": ("torso", "body"), "hips": ("torso", "body"), "chest": ("torso", "body"),
        "hand_ik.L": ("left_arm", "ik_control"), "hand_ik.R": ("right_arm", "ik_control"),
        "upper_arm_ik_target.L": ("left_arm", "pole"), "foot_ik.R": ("right_leg", "ik_control"),
        "f_index.01_master.L": ("left_hand", "finger_master"),
        "upper_arm_fk.L": ("left_arm", "fk"), "upper_arm_parent.L": ("left_arm", "switches"),
        "head": ("head", "fk"), "root": ("root", "root"),
    }
    for bone, (body_part, role) in expected.items():
        assert (controls[bone]["body_part"], controls[bone]["role"]) == (body_part, role), bone
    assert controls["hand_ik.L"]["chain"] == "ik"
    assert controls["upper_arm_fk.L"]["chain"] == "fk"
    assert controls["hand_ik.L"]["source"] == "rigify"
    assert not any(name.startswith(("DEF-", "MCH-", "ORG-", "VIS_")) for name in controls)


def test_hidden_by_default_is_what_rigify_hid(human_toes):
    """commands.get_pose_controls' hidden_by_default against the generated collections"""
    basemesh, rig = human_toes
    controls = _controls_by_name(_result({"name": basemesh}))
    for name, control in controls.items():
        visible = any(collection.is_visible for collection in rig.data.bones[name].collections)
        assert control["hidden_by_default"] is (not visible), name


def test_the_rest_position_is_in_the_character_frame(human_toes):
    """commands.get_pose_controls on an unmoved generated rig: forward is -Y, left is +X"""
    basemesh, rig = human_toes
    controls = _controls_by_name(_result({"name": basemesh}))
    hand = rig.data.bones["hand_ik.L"].head_local
    assert controls["hand_ik.L"]["head"] == {
        "forward": round(-hand.y, 3) + 0.0, "left": round(hand.x, 3), "up": round(hand.z, 3)}
    assert controls["toe_fk.L"]["direction"]["forward"] > 0.5, "the toes point forward"


def test_switches_say_what_each_end_means_and_name_their_parents(human_toes):
    """commands.get_pose_controls' switches, against the generated rig_ui.py"""
    basemesh, rig = human_toes
    switches = {(switch["body_part"], switch["switch"]): switch
                for switch in _result({"name": basemesh})["switches"]}

    ik_fk = switches[("left_arm", "IK_FK")]
    assert ik_fk["bone"] == "upper_arm_parent.L"
    assert ik_fk["range"] == [0.0, 1.0]
    assert ik_fk["ends"][0].startswith("IK")
    assert switches[("left_arm", "pole_vector")]["range"] == [False, True]
    assert ("left_hand", "finger_curve") not in switches, \
        "finger_curve is on every finger master, so it is each control's setting"

    script = rig["rig_ui"].as_string()
    for (body_part, prop), switch in switches.items():
        if switch["type"] != "parent":
            continue
        assert switch["parent_names"], (body_part, prop)
        pattern = (r"props\.prop_bone = '{:s}'\s+props\.prop_id = '{:s}'\s+"
                   r"props\.parent_names = '(\[[^']*\])'").format(
                       re.escape(switch["bone"]), re.escape(prop))
        found = re.search(pattern, script)
        if found is None:
            # The script lists prop_bone and prop_id in either order.
            pattern = (r"props\.bone = '[^']*'\s+props\.prop_bone = '{:s}'\s+"
                       r"props\.prop_id = '{:s}'\s+props\.parent_names = '(\[[^']*\])'").format(
                           re.escape(switch["bone"]), re.escape(prop))
            found = re.search(pattern, script)
        assert found is not None, "rig_ui.py has no parent list for {!r}".format((body_part, prop))
        assert switch["parent_names"] == json.loads(found.group(1)), (body_part, prop)
        assert switch["range"] == [0, len(switch["parent_names"]) - 1]


def test_the_face_is_counted_always_and_listed_only_when_named(human_toes):
    """commands.get_pose_controls' body_parts filter"""
    basemesh, _rig = human_toes
    default = _result({"name": basemesh})
    assert "face" not in default["requested_body_parts"]
    assert "face" not in default["controls"]
    assert default["counts_by_body_part"]["face"] > 50
    assert set(default["counts_by_body_part"]) == set(
        ("root", "torso", "head", "face", "left_arm", "right_arm", "left_hand", "right_hand",
         "left_leg", "right_leg"))

    face = _result({"name": basemesh, "body_parts": ["face"]})
    assert list(face["controls"]) == ["face"]
    assert len(face["controls"]["face"]) == default["counts_by_body_part"]["face"]
    assert face["counts_by_body_part"] == default["counts_by_body_part"]
    assert {switch["body_part"] for switch in face["switches"]} <= {"face"}


def test_a_game_engine_rig_is_classified_without_collections(game_engine):
    """commands.get_pose_controls on MPFB's legacy convert-to-Rigify result"""
    basemesh, rig = game_engine
    answer = _result({"name": basemesh})

    assert answer["rig_identified_as"] == "rigify_generated.game_engine"
    assert answer["classified"] is True
    assert answer["unassigned_bones"] == []
    controls = _controls_by_name(answer)
    assert (controls["hand_ik_l"]["body_part"], controls["hand_ik_l"]["role"]) == \
        ("left_arm", "ik_control")
    assert controls["thigh_ik_target_r"]["role"] == "pole"
    assert controls["index_01_master_l"]["body_part"] == "left_hand"
    assert controls["upperarm_parent_l"]["role"] == "switches"
    assert all(control["hidden_by_default"] is False for control in controls.values()), \
        "Rigify generated every control into one visible collection"
    assert len(controls) == sum(1 for bone in rig.data.bones
                                if not bone.name.startswith(("DEF-", "MCH-", "ORG-", "VIS_")))


def test_helpers_are_listed_with_what_they_drive(default_with_helpers):
    """commands.get_pose_controls on a default rig carrying MPFB's helpers"""
    basemesh, _rig = default_with_helpers
    answer = _result({"name": basemesh, "body_parts": ["left_arm", "left_hand", "head"]})

    assert answer["rig_identified_as"] == "default"
    assert answer["helper_modes"] == {"arm_mode": "LOWERUPPER", "leg_mode": "LOWERUPPER",
                                      "finger_mode": "GRIP_AND_MASTER", "eye_mode": "IK"}
    assert answer["helpers_missing"] == []
    assert answer["switches"] == []
    controls = _controls_by_name(answer)
    assert controls["left_hand_ik"]["source"] == "mpfb_helper"
    assert controls["left_elbow_ik"]["role"] == "pole"
    assert controls["lowerarm01.L"]["driven_by"] == ["left_hand_ik"]
    assert controls["upperarm01.L"]["chain"] == "fk"
    assert "driven_by" in answer["message"]


def test_an_unclassified_rig_is_listed_and_never_guessed():
    """commands.get_pose_controls on a mixamo rig"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "mixamo")
        answer = _result({"name": character.basemesh.name})

        assert answer["classified"] is False
        assert answer["controls"] is None
        assert answer["counts_by_body_part"] is None
        assert "default" in answer["classified_rigs"]
        assert [bone["bone"] for bone in answer["bones"]] == [bone.name for bone in rig.data.bones]
        assert "body_part" not in answer["bones"][0]


def test_a_meta_rig_is_refused_naming_the_tool_that_generates():
    """commands.get_pose_controls on a character carrying only a Rigify meta-rig"""
    services = services_or_skip()
    with Character() as character:
        meta_rig = rigged_character(services, character, "rigify.human")
        answer = _result({"name": character.basemesh.name})

        assert answer["ready"] is False
        assert answer["blocked_by"] == "rigify_not_generated"
        assert answer["metarig_name"] == meta_rig.name
        assert "mpfb_generate_rigify_rig" in answer["message"]


def test_no_rig_is_refused_naming_the_tool_that_adds_one():
    """commands.get_pose_controls on a character with no rig"""
    services_or_skip()
    with Character() as character:
        answer = _result({"name": character.basemesh.name})
        assert answer["found"] is True
        assert answer["blocked_by"] == "rig_not_found"
        assert "mpfb_add_rig" in answer["message"]


def test_an_unknown_body_part_is_named_with_the_vocabulary(default_with_helpers):
    """commands.get_pose_controls with a body part that is not one"""
    basemesh, _rig = default_with_helpers
    answer = _result({"name": basemesh, "body_parts": ["left_arm", "elbows"]})
    assert answer["blocked_by"] == "unknown_body_parts"
    assert answer["unknown_body_parts"] == ["elbows"]
    assert "left_arm" in answer["known_body_parts"]


def test_a_missing_subject_is_subject_not_found():
    """commands.get_pose_controls on a name that is not an object"""
    services_or_skip()
    answer = _result({"name": "NoSuchPoseSubject"})
    assert answer["found"] is False
    assert answer["blocked_by"] == "subject_not_found"


def test_reading_changes_nothing(human_toes):
    """commands.get_pose_controls leaves mode, selection, active object and pose alone"""
    basemesh, rig = human_toes
    bystander = bpy.data.objects.new("PoseControlsBystander", None)
    bpy.context.scene.collection.objects.link(bystander)
    try:
        bpy.context.view_layer.objects.active = bystander
        bystander.select_set(True)
        before = posing_state(rig)
        envelope = dispatch("get_pose_controls", {"name": basemesh, "body_parts": [
            "root", "torso", "head", "face", "left_arm", "right_arm", "left_hand",
            "right_hand", "left_leg", "right_leg"]})
        assert envelope["status"] == "ok"
        assert posing_state(rig) == before
    finally:
        bpy.data.objects.remove(bystander, do_unlink=True)
