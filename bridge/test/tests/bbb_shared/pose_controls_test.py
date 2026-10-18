"""
``shared/pose_controls.py`` called directly: the default-rig table against MPFB, and the helpers.

**The drift test the FR asked for lives here.** The default rig is classified
from a hand-kept table, because it has one bone collection and nothing to read a
body part off. The add-on may not import MPFB's helper modules
([never import MPFB submodules directly](../../../../specifications/architecture.md#never-import-mpfb-submodules-directly)),
so the table cannot be built from them; this test reads them out of
``sys.modules`` - where MPFB's own add-helpers operator put them - and checks
the table against what they name, the way ``tests/test_reference_drift.py``
checks the vendored URL table. A bone MPFB renames fails here rather than
silently unclassifying a limb.

The rest is what the table cannot show on its own: that every bone of a real
default rig is classified, that the helpers MPFB adds are recognised and what
they drive is read off the constraints, and that a helper MPFB records as
installed but which is missing from the armature is reported.

**The rule that hides controls on a ``game_engine`` rig is checked against the
rig where Rigify hides them**
([FR 043](../../../../feature-requests/done/043-narrower-pose-controls/README.md)).
``human_toes`` reads ``hidden_by_default`` off its collections and
``game_engine`` derives it by role; on ``human_toes``, outside the face, the
two must agree control for control, or the flag would mean different things on
the two families. FR 043 found they did not agree on the roles alone: the
spine's FK controls are in ``Torso (Tweak)``, which is why
``hidden_by_role()`` names them.
"""

import json
import os
import sys

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import mpfb_root
from .._fixtures import mpfb_ui_module
from .._fixtures import rigged_character
from .._fixtures import services_or_skip
from .._fixtures import with_helpers


def _pose_controls():
    return bridge_module("shared.pose_controls")


def _helper_class(relative, class_name):
    module = sys.modules.get(mpfb_root() + ".entities.rigging.righelpers." + relative)
    if module is None or not hasattr(module, class_name):
        pytest.skip("MPFB's {:s} is not loaded in this Blender".format(class_name))
    return getattr(module, class_name)


def _unsided(names):
    return set(name[:-2] for name in names)


@pytest.mark.parametrize("name, side", [
    ("hand_ik.L", "left"), ("hand_ik_l", "left"), ("f_index.01.L.001", "left"),
    ("upper_arm_tweak.R.001", "right"), ("thigh_parent_r", "right"),
    ("left_hand_ik", "left"), ("right_finger2_grip", "right"),
    ("torso", None), ("spine_fk.001", None), ("eye_ik", None),
])
def test_a_side_is_read_off_every_naming_convention_in_use(name, side):
    """pose_controls.side_of"""
    assert _pose_controls().side_of(name) == side


def test_the_default_table_covers_every_chain_mpfbs_helpers_name():
    """pose_controls._DEFAULT_TABLE against DefaultArmHelpers, DefaultLegHelpers, DefaultFingerHelpers"""
    services_or_skip()
    table = _pose_controls()._DEFAULT_TABLE  # pylint: disable=protected-access
    arm = _helper_class("armhelpers.defaultarmhelpers", "DefaultArmHelpers")("left", {})
    leg = _helper_class("leghelpers.defaultleghelpers", "DefaultLegHelpers")("left", {})
    finger = _helper_class("fingerhelpers.defaultfingerhelpers", "DefaultFingerHelpers")("left", {})

    for name in _unsided(arm.get_reverse_list_of_bones_in_arm(True, True, True, True)):
        assert table.get(name) == ("arm", "fk"), name
    for name in _unsided(leg.get_reverse_list_of_bones_in_leg(True, True, True, True)):
        assert table.get(name) == ("leg", "fk"), name
    for number in range(1, 6):
        for name in _unsided(finger.get_reverse_list_of_bones_in_finger(number)):
            assert table.get(name) == ("hand", "finger_segment"), name
        parent = finger.get_immediate_parent_name_of_finger(number)[:-2]
        assert table.get(parent) in (("hand", "fk"), ("arm", "fk")), parent
    assert table.get(arm.get_shoulders_immediate_parent()) == ("torso", "fk")


def test_the_default_limbs_are_mpfbs_arm_and_leg_chains():
    """pose_controls._DEFAULT_LIMBS against the helpers' chains and tips"""
    services_or_skip()
    limbs = _pose_controls()._DEFAULT_LIMBS  # pylint: disable=protected-access
    arm = _helper_class("armhelpers.defaultarmhelpers", "DefaultArmHelpers")("left", {})
    leg = _helper_class("leghelpers.defaultleghelpers", "DefaultLegHelpers")("left", {})

    arm_segments, arm_tip, _ik, _pole = limbs["arm"]
    # "reverse" in MPFB's name notwithstanding, the list runs root to tip.
    assert [name + ".L" for name in arm_segments] == \
        arm.get_reverse_list_of_bones_in_arm(False, True, True, False)
    assert arm_tip + ".L" == arm.get_hand_name()
    leg_segments, leg_tip, _ik, _pole = limbs["leg"]
    assert [name + ".L" for name in leg_segments] == \
        leg.get_reverse_list_of_bones_in_leg(False, True, True, False)
    assert leg_tip + ".L" == leg.get_foot_name()


def test_every_recorded_helper_mode_is_one_mpfbs_panel_offers():
    """pose_controls._HELPERS_BY_MODE against the helper-type enums MPFB defines"""
    services_or_skip()
    panel = mpfb_ui_module("ui.rigging.standardrig")
    directory = os.path.join(os.path.dirname(panel.__file__), "helperproperties")
    by_mode = _pose_controls()._HELPERS_BY_MODE  # pylint: disable=protected-access
    for mode, filename in (("arm_mode", "arm_helpers_type.json"),
                           ("leg_mode", "leg_helpers_type.json"),
                           ("finger_mode", "finger_helpers_type.json")):
        with open(os.path.join(directory, filename), encoding="utf-8") as handle:
            offered = set(item[0] for item in json.load(handle)["items"]) - {"NONE"}
        assert set(by_mode[mode]) == offered, mode


def test_every_bone_of_a_default_rig_is_classified():
    """pose_controls.classify on a plain default rig"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "default")
        classification = _pose_controls().classify(mpfb_root(), rig, "default")

        assert classification["classified"] is True
        assert classification["unassigned"] == []
        assert set(classification["controls"]) == set(bone.name for bone in rig.data.bones)
        assert classification["helper_modes"] == dict.fromkeys(
            ("arm_mode", "leg_mode", "finger_mode", "eye_mode"), "NONE")
        assert classification["limbs"]["left_arm"]["ik_control"] is None
        assert classification["landmarks"]["left_hand"] == "wrist.L"


@pytest.mark.parametrize("arm", ["LOWERUPPER", "LOWERUPPERSHOULDER", "ARMCHAIN", "SHOULDERCHAIN"])
def test_each_arm_helper_mode_is_recognised_with_what_it_drives(arm):
    """pose_controls.classify on a default rig carrying each arm helper and the master grip"""
    services = services_or_skip()
    with Character() as character:
        rig = with_helpers(rigged_character(services, character, "default"),
                           arm=arm, finger="MASTER", eye=True)
        classification = _pose_controls().classify(mpfb_root(), rig, "default")
        controls = classification["controls"]

        assert classification["unassigned"] == []
        assert classification["helper_modes"]["arm_mode"] == arm
        assert classification["helper_modes"]["finger_mode"] == "MASTER"
        assert classification["helpers_missing"] == []
        assert controls["left_hand_ik"]["source"] == "mpfb_helper"
        assert controls["left_hand_ik"]["role"] == "ik_control"
        assert controls["left_hand_ik"]["body_part"] == "left_arm"
        assert controls["left_master_grip"]["role"] == "finger_master"
        assert controls["eye_ik"]["role"] == "look_target"
        # Read off the constraints: the lower arm is in the hand IK's chain,
        # every finger segment is bent by the master grip.
        assert "left_hand_ik" in controls["lowerarm02.L"]["driven_by"]
        assert "left_master_grip" in controls["finger3-2.L"]["driven_by"]
        assert controls["eye.L"]["driven_by"] == ["left_eye_ik"]
        helpers = [name for name, control in controls.items()
                   if control["source"] == "mpfb_helper"]
        assert set(helpers) == set(bone.name for bone in rig.data.bones) - set(
            name for name, control in controls.items() if control["source"] == "rig")


def test_a_recorded_helper_whose_bone_is_missing_is_reported():
    """pose_controls.classify where MPFB's record and the armature disagree"""
    services = services_or_skip()
    with Character() as character:
        rig = with_helpers(rigged_character(services, character, "default"), arm="LOWERUPPER")
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        rig.data.edit_bones.remove(rig.data.edit_bones["left_elbow_ik"])
        bpy.ops.object.mode_set(mode="OBJECT")

        classification = _pose_controls().classify(mpfb_root(), rig, "default")

        assert classification["helper_modes"]["arm_mode"] == "LOWERUPPER"
        assert classification["helpers_missing"] == ["left_elbow_ik"]


def test_helper_modes_are_unknown_rather_than_guessed_without_mpfbs_ui():
    """pose_controls.classify when RigHelpersProperties cannot be read"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "default")
        classification = _pose_controls().classify("no.such.root", rig, "default")

        assert classification["helper_modes"] is None
        assert "RigHelpersProperties" in classification["helper_modes_reason"]
        assert classification["helpers_missing"] == []


def test_the_hidden_rule_is_what_rigify_hides_on_human_toes_outside_the_face():
    """pose_controls.hidden_by_role against human_toes' collection qualifiers"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        controls = _pose_controls().classify(
            mpfb_root(), rig, "rigify_generated.human_toes")["controls"]

        outside_the_face = {name: control for name, control in controls.items()
                            if control["body_part"] != "face"}
        by_collection = {name for name, control in outside_the_face.items()
                         if control["hidden_by_default"]}
        by_role = {name for name, control in outside_the_face.items()
                   if _pose_controls().hidden_by_role(name, control["body_part"], control["role"])}
        assert by_collection == by_role
        assert len(by_collection) == 109
        assert {"spine_fk", "spine_fk.004"} <= by_collection
        assert not {"torso", "hips", "chest", "breast.L"} & by_collection


def test_the_hidden_flag_on_game_engine_follows_the_role():
    """pose_controls.classify on a generated game_engine rig, which has no collections to read"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:game_engine")
        controls = _pose_controls().classify(
            mpfb_root(), rig, "rigify_generated.game_engine")["controls"]

        hidden_roles = set(_pose_controls().HIDDEN_ROLES)
        for name, control in controls.items():
            expected = control["role"] in hidden_roles or (
                control["body_part"] == "torso" and control["role"] == "fk")
            assert control["hidden_by_default"] is expected, name
        assert {control["role"] for control in controls.values()
                if control["hidden_by_default"]} == {"tweak", "finger_segment", "fk"}
