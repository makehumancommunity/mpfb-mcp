"""
``set_pose_switches`` against a real MPFB, on generated ``human_toes`` and ``game_engine`` rigs.

What only a real rig can establish, and so is asserted here:

- **The snap chains follow from Rigify's naming**, on both families: every
  limb's FK, IK result, control, tail and extra chains as
  ``set_pose_switches.snap_chains()`` derives them equal the ones Rigify baked
  into the generated ``rig_ui.py`` - read as data, searched and never executed -
  for the IK->FK and FK->IK operators, and a parent switch's kept channels equal
  the script's ``locks``. That is FR 042's open question, answered the way FR 041
  answered it for the parent names.
- **Every snap keeps the limb in place**, in both directions, on a posed arm and
  a posed leg (with its toe), with the pole off and on, and across a parent
  switch: ``snap_error`` under a millimetre. The same switches with ``raw: true``
  move the limb.
- **Switches without a snap** are written as given and say why.
- **Refusals change nothing**: an unknown switch, a value of the wrong type or
  outside the live range, a switch named twice, and a rig that has no switches
  at all (a default rig, ``mixamo``).
"""

import json
import math
import re

import bpy
import pytest
from mathutils import Vector

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import posing_state
from .._fixtures import rest_pose
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip

_MM = 0.001


def _result(params):
    return _fixture_result("set_pose_switches", params)


def _classification(rig, identified):
    root = bridge_module("mpfb_resolution").resolve().module.__name__
    return bridge_module("shared.pose_controls").classify(root, rig, identified)


def _snap_chains(rig, classification, part):
    return bridge_module("commands.set_pose_switches").snap_chains(rig, classification, part)


def _move(rig, bone, offset):
    """Move one pose bone by an armature-space offset, in plain bpy."""
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
        rig.location = (-1.0, 2.0, 0.0)
        rig.rotation_euler = (0.0, 0.0, math.radians(-60.0))
        bpy.context.view_layer.update()
        yield character.basemesh.name, rig


@pytest.fixture(name="rigify")
def _rigify(human_toes):
    rest_pose(human_toes[1])
    yield human_toes
    rest_pose(human_toes[1])


def _ik2fk_operators(script):
    """Each IK->FK operator's chains in rig_ui.py, by the bone carrying the switch."""
    pattern = re.compile(
        r"operator\('pose\.rigify_limb_ik2fk_[^']+'[^\n]*\n"
        r"\s+props\.prop_bone = '(?P<bone>[^']+)'\n"
        r"\s+props\.fk_bones = '(?P<fk>[^']*)'\n"
        r"\s+props\.ik_bones = '(?P<ik>[^']*)'\n"
        r"\s+props\.ctrl_bones = '(?P<ctrl>[^']*)'\n"
        r"\s+props\.tail_bones = '(?P<tail>[^']*)'\n"
        r"\s+props\.extra_ctrls = '(?P<extra>[^']*)'")
    return {match.group("bone"): {key: json.loads(match.group(key))
                                  for key in ("fk", "ik", "ctrl", "tail", "extra")}
            for match in pattern.finditer(script)}


def _fk2ik_operators(script):
    pattern = re.compile(
        r"operator\('pose\.rigify_generic_snap_[^']+'[^\n]*\n"
        r"\s+props\.output_bones = '(?P<output>[^']*)'\n"
        r"\s+props\.input_bones = '(?P<input>[^']*)'")
    return [(json.loads(match.group("output")), json.loads(match.group("input")))
            for match in pattern.finditer(script)]


def _parent_locks(script):
    pattern = re.compile(
        r"props\.bone = '(?P<bone>[^']+)'\n\s+props\.prop_bone = '[^']+'\n"
        r"\s+props\.prop_id = '[^']+'\n\s+props\.parent_names = '[^']*'\n"
        r"\s+props\.locks = \((?P<locks>[^)]*)\)")
    return {match.group("bone"): tuple(part.strip() == "True"
                                       for part in match.group("locks").split(","))
            for match in pattern.finditer(script)}


def _check_chains_against_the_script(rig, identified):
    classification = _classification(rig, identified)
    script = rig["rig_ui"].as_string()
    ik2fk = _ik2fk_operators(script)
    fk2ik = _fk2ik_operators(script)
    for part in ("left_arm", "right_arm", "left_leg", "right_leg"):
        chains, missing = _snap_chains(rig, classification, part)
        assert missing == [], (part, missing)
        switch_bone = classification["limbs"][part]["switch_bone"]
        baked = ik2fk[switch_bone]
        assert chains["fk"] == baked["fk"], part
        assert chains["ik"] == baked["ik"], part
        assert chains["ctrl"] == baked["ctrl"], part
        assert chains["tail"] == baked["tail"], part
        assert sorted(chains["extra"]) == sorted(baked["extra"]), part
        assert (chains["fk"], chains["ik"] + chains["tail"]) in fk2ik, part
    return classification, script


def test_the_snap_chains_are_rigifys_own_on_human_toes(human_toes):
    """set_pose_switches.snap_chains() against the generated rig_ui.py, human_toes"""
    _basemesh, rig = human_toes
    classification, script = _check_chains_against_the_script(
        rig, "rigify_generated.human_toes")
    locks = _parent_locks(script)
    for part in ("left_arm", "left_leg"):
        limb = classification["limbs"][part]
        assert locks[limb["ik_control"]] == (False, False, False)
        assert locks[limb["pole"]] == (False, True, True), \
            "a pole's parent switch keeps only its location, as the command assumes"


def test_the_snap_chains_are_rigifys_own_on_game_engine_and_its_snaps_hold():
    """set_pose_switches on a generated game_engine rig, with its _l/_r names"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:game_engine")
        _check_chains_against_the_script(rig, "rigify_generated.game_engine")
        _move(rig, "hand_ik_l", (0.1, -0.2, 0.25))
        _move(rig, "foot_ik_r", (0.0, -0.2, 0.15))
        name = character.basemesh.name
        for value in (1.0, 0.0):
            answer = _result({"name": name, "switches": [
                {"body_part": "left_arm", "switch": "IK_FK", "value": value},
                {"body_part": "right_leg", "switch": "IK_FK", "value": value}]})
            for change in answer["changes"]:
                assert change["snapped"] is True
                assert change["snap_error"] < _MM, change


def _snapped(answer):
    for change in answer["changes"]:
        assert change["snapped"] is True, change
        assert change["snap_error"] < _MM, change
    return answer


def test_ik_to_fk_and_back_keeps_a_posed_arm_and_leg_in_place(rigify):
    """commands.set_pose_switches: IK_FK both ways on a posed arm and a posed leg with its toe"""
    basemesh, rig = rigify
    # Within reach. A limb IK_Stretch has stretched snaps back to IK with its
    # elbow a millimetre or two out, because Blender's stretching IK does not
    # share the stretch between the segments the way the FK chain carries it;
    # snap_error reports that rather than hiding it.
    _move(rig, "hand_ik.L", (-0.1, -0.2, 0.15))
    _move(rig, "foot_ik.L", (0.0, -0.2, 0.25))
    limbs = _fixture_result("get_pose", {"name": basemesh})["limbs"]
    assert not limbs["left_arm"]["stretched"] and not limbs["left_leg"]["stretched"]
    rig.pose.bones["toe_ik.L"].rotation_euler = (0.4, 0.0, 0.0)
    bpy.context.view_layer.update()
    answer = _snapped(_result({"name": basemesh, "switches": [
        {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0},
        {"body_part": "left_leg", "switch": "IK_FK", "value": 1.0}]}))
    assert answer["performed"] is True
    arm = answer["changes"][0]
    assert (arm["bone"], arm["previous_value"], arm["new_value"]) == \
        ("upper_arm_parent.L", 0.0, 1.0)
    assert arm["end_bone"] == "DEF-hand.L" and arm["end_before"] == arm["end_after"]
    assert answer["limbs"]["left_arm"]["in_charge"] == "fk"
    # Now bend the FK arm and go back: the IK controls follow the FK pose.
    rig.pose.bones["forearm_fk.L"].rotation_euler = (0.6, 0.0, 0.2)
    rig.pose.bones["upper_arm_fk.L"].rotation_quaternion = (0.97, 0.1, 0.0, 0.2)
    bpy.context.view_layer.update()
    _snapped(_result({"name": basemesh, "switches": [
        {"body_part": "left_arm", "switch": "IK_FK", "value": 0.0},
        {"body_part": "left_leg", "switch": "IK_FK", "value": 0.0}]}))


def test_the_pole_keeps_the_chain_and_order_matters(rigify):
    """commands.set_pose_switches: pole_vector on and off, then IK_FK with the pole on"""
    basemesh, rig = rigify
    _move(rig, "hand_ik.R", (-0.1, -0.3, 0.35))
    rig.pose.bones["upper_arm_ik.R"].rotation_euler = (0.0, 0.7, 0.0)
    bpy.context.view_layer.update()
    _snapped(_result({"name": basemesh, "switches": [
        {"body_part": "right_arm", "switch": "pole_vector", "value": True}]}))
    _snapped(_result({"name": basemesh, "switches": [
        {"body_part": "right_arm", "switch": "pole_vector", "value": False}]}))
    _snapped(_result({"name": basemesh, "switches": [
        {"body_part": "right_arm", "switch": "IK_FK", "value": 1.0}]}))
    rig.pose.bones["upper_arm_fk.R"].rotation_quaternion = (0.95, 0.2, 0.1, 0.2)
    bpy.context.view_layer.update()
    # Pole first, then back to IK: the snap places the pole too.
    answer = _snapped(_result({"name": basemesh, "switches": [
        {"body_part": "right_arm", "switch": "pole_vector", "value": True},
        {"body_part": "right_arm", "switch": "IK_FK", "value": 0.0}]}))
    assert answer["changes"][0]["snap_error"] < _MM


def test_a_parent_switch_keeps_the_control_where_it_is(rigify):
    """commands.set_pose_switches: IK_parent and pole_parent, snapped and raw"""
    basemesh, rig = rigify
    _move(rig, "torso", (0.0, 0.0, -0.3))
    switches = _fixture_result("get_pose_controls", {"name": basemesh,
                                                     "body_parts": ["left_arm"]})["switches"]
    names = next(switch for switch in switches if switch["switch"] == "IK_parent")[
        "parent_names"]
    torso = names.index("Torso")
    answer = _snapped(_result({"name": basemesh, "switches": [
        {"body_part": "left_arm", "switch": "IK_parent", "value": torso},
        {"body_part": "left_arm", "switch": "pole_parent", "value": torso}]}))
    assert answer["changes"][0]["new_value"] == torso
    rest_pose(rig)
    _move(rig, "torso", (0.0, 0.0, -0.3))
    raw = _result({"name": basemesh, "switches": [
        {"body_part": "left_arm", "switch": "IK_parent", "value": torso, "raw": True}]})
    (change,) = raw["changes"]
    assert change["snapped"] is False and "raw" in change["snap_reason"]
    assert change["end_before"]["up"] - change["end_after"]["up"] > 0.25, \
        "raw, the hand follows its new parent down"


def test_raw_moves_the_limb(rigify):
    """commands.set_pose_switches: IK_FK with raw: true, on a posed arm"""
    basemesh, rig = rigify
    _move(rig, "hand_ik.L", (0.15, -0.25, 0.3))
    answer = _result({"name": basemesh, "switches": [
        {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0, "raw": True}]})
    (change,) = answer["changes"]
    assert change["snapped"] is False and "snap_error" not in change
    assert (Vector(tuple(change["end_after"].values()))
            - Vector(tuple(change["end_before"].values()))).length > 0.1


def test_a_switch_without_a_snap_is_written_as_given(rigify):
    """commands.set_pose_switches: IK_Stretch, a blended IK_FK, and a value already there"""
    basemesh, rig = rigify
    answer = _result({"name": basemesh, "switches": [
        {"body_part": "left_arm", "switch": "IK_Stretch", "value": 0.0},
        {"body_part": "right_arm", "switch": "IK_FK", "value": 0.5},
        {"body_part": "left_leg", "switch": "IK_FK", "value": 0.0}]})
    stretch, blend, same = answer["changes"]
    assert stretch["snapped"] is False and "no snap" in stretch["snap_reason"]
    assert rig.pose.bones["upper_arm_parent.L"]["IK_Stretch"] == 0.0
    assert blend["snapped"] is False and "between 0 and 1" in blend["snap_reason"]
    assert same["previous_value"] == same["new_value"] == 0.0
    assert "already" in same["snap_reason"]
    assert answer["performed"] is True


def test_a_refused_batch_changes_nothing(rigify):
    """commands.set_pose_switches: unknown switch, wrong type, out of range, named twice"""
    basemesh, rig = rigify
    _move(rig, "hand_ik.L", (0.1, 0.0, 0.2))
    before = posing_state(rig)
    answer = _result({"name": basemesh, "switches": [
        {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0},
        {"body_part": "left_arm", "switch": "IK_FKK", "value": 1.0},
        {"body_part": "left_arm", "switch": "pole_vector", "value": 1},
        {"body_part": "left_arm", "switch": "IK_Stretch", "value": 2.5},
        {"body_part": "left_arm", "switch": "IK_parent", "value": 99},
        {"body_part": "left_arm", "switch": "IK_FK", "value": 0.0}]})
    assert answer["performed"] is False and answer["changes"] == []
    reasons = [(error["index"], error["reason"]) for error in answer["resolution_errors"]]
    assert reasons == [(1, "unknown_switch"), (2, "invalid_value"), (3, "invalid_value"),
                       (4, "invalid_value"), (5, "duplicate_switch")]
    assert "IK_FK" in answer["resolution_errors"][0]["known_switches"]
    assert posing_state(rig) == before


@pytest.mark.parametrize("rig_name", ["default", "mixamo"])
def test_a_rig_without_switches_is_refused(rig_name):
    """commands.set_pose_switches on a default and a mixamo rig"""
    services = services_or_skip()
    with Character() as character:
        rigged_character(services, character, rig_name)
        answer = _result({"name": character.basemesh.name, "switches": [
            {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}]})
        assert (answer["ready"], answer["blocked_by"]) == (False, "rig_has_no_switches")
        assert "generated Rigify" in answer["message"]
        assert answer["performed"] is False
