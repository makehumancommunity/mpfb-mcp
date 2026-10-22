"""
``shared/rigify_hands.py`` called directly, on a generated ``human_toes`` rig.

What the two hand-shape commands rest on, each a way they could disagree with
the rig without any answer looking odd:

- **Amounts go to channels and come back**, for every finger of both hands,
  negative curl and both spread signs included - and the deforming bones
  measure what the amounts ask for.
- **The bend axis and its sign come from Rigify's drivers**: every expression
  in Rigify's own ``axis_options`` is in :data:`BEND_EXPRESSIONS` with the sign
  its ``id`` gives; a rig whose driver is rewritten to each X and Z option is
  read with that axis; the Y options and an expression Rigify never writes are
  refused, naming the finger. And MPFB's two meta-rigs ask for exactly what the
  module was calibrated on, so a change to either fails here.
- **The spread's sign is anatomical**: the same ``spread`` moves both hands'
  fingers the same way, away from the middle finger and the thumb away from
  the palm, read off the bones rather than assumed per side.
- **What is not a curl and a spread says so**: a twisted master, a posed
  segment, a hook (the karate session's scale-only fist) and a posed palm.

``mathutils`` computes in single precision, so a round trip through a master's
Euler channels is exact to about 2e-6 of an amount, not to 1e-6; the bound
below is 1e-5, which is still a thousandth of a degree on the widest joint.
"""

import json
import math
import os
import sys

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import mpfb_root
from .._fixtures import rest_pose
from .._fixtures import rigged_character
from .._fixtures import services_or_skip

_AMOUNT = 1e-5
_DEGREES = 0.01


def _hands_module():
    return bridge_module("shared.rigify_hands")


def _classified(rig):
    return bridge_module("shared.pose_controls").classify(
        mpfb_root(), rig, "rigify_generated.human_toes")


def _hands(rig):
    return _hands_module().find_hands(rig, _classified(rig))


@pytest.fixture(scope="module", name="human_toes")
def _human_toes():
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        rig.location = (-1.0, 2.0, 0.0)
        rig.rotation_euler = (0.0, 0.0, math.radians(-70.0))
        bpy.context.view_layer.update()
        yield rig


@pytest.fixture(name="rig")
def _rig(human_toes):
    rest_pose(human_toes)
    bpy.context.view_layer.update()
    yield human_toes
    rest_pose(human_toes)


def test_every_finger_of_both_hands_is_found_with_its_chain(rig):
    """rigify_hands.find_hands on a generated human_toes rig"""
    hands = _hands(rig)
    assert set(hands) == {"left_hand", "right_hand"}
    for hand, side in (("left_hand", "L"), ("right_hand", "R")):
        found = hands[hand]
        assert found["errors"] == {}
        assert list(found["fingers"]) == ["thumb", "index", "middle", "ring", "pinky"]
        index = found["fingers"]["index"]
        assert index.master == "f_index.01_master." + side
        assert index.segments == ["f_index.0{:d}.{:s}".format(k, side) for k in (1, 2, 3)]
        assert index.tip_control == "f_index.01.{:s}.001".format(side)
        assert index.deforming == ["DEF-f_index.0{:d}.{:s}".format(k, side) for k in (1, 2, 3)]
        assert index.ik_control is None, "MPFB's meta-rigs make no extra finger IK control"
        assert found["palm_controls"] == ["palm." + side]
        assert found["fingers"]["index"].moved_by_palm is None
        assert found["fingers"]["ring"].moved_by_palm == "palm." + side


@pytest.mark.parametrize("curl,spread", [(0.0, 0.0), (1.0, 0.0), (-0.2, 0.0), (0.4, 1.0),
                                         (0.7, -1.0), (-0.2, -0.5), (1.0, 1.0)])
def test_amounts_go_to_channels_and_come_back(rig, curl, spread):
    """rigify_hands.write_finger then channel_amounts and measure, every finger"""
    module = _hands_module()
    hands = _hands(rig)
    for found in hands.values():
        for finger in found["fingers"].values():
            module.write_finger(rig, finger, curl, spread)
    bpy.context.view_layer.update()
    for found in hands.values():
        for finger in found["fingers"].values():
            read_curl, read_spread, reasons = module.channel_amounts(rig, finger)
            assert reasons == [], finger.master
            assert abs(read_curl - curl) < _AMOUNT, finger.master
            assert abs(read_spread - spread) < _AMOUNT, finger.master
            joints, sideways = module.measure(rig, finger)
            expected, expected_spread = module.expected_degrees(finger, curl, spread)
            assert max(abs(e - m) for e, m in zip(expected, joints)) < _DEGREES, finger.master
            assert abs(expected_spread - sideways) < _DEGREES, finger.master


def test_rigifys_axis_options_are_the_ones_the_module_reads():
    """BEND_EXPRESSIONS against super_finger.Rig.axis_options"""
    services_or_skip()
    super_finger = pytest.importorskip("rigify.rigs.limbs.super_finger")
    expressions = _hands_module().BEND_EXPRESSIONS
    for name, option in super_finger.Rig.axis_options.items():
        assert option["expr"] in expressions, name
        assert expressions[option["expr"]] == (-1.0 if option["id"].startswith("-") else 1.0), name


def test_mpfbs_meta_rigs_ask_for_what_the_module_was_calibrated_on():
    """every super_finger in rig.human.json and rig.human_toes.json"""
    services_or_skip()
    for meta_rig in ("rig.human.json", "rig.human_toes.json"):
        path = os.path.join(os.path.dirname(sys.modules[mpfb_root()].__file__),
                            "data", "rigs", "rigify", meta_rig)
        with open(path, encoding="utf-8") as stream:
            bones = json.load(stream)["bones"]
        # human_toes builds its toes with super_finger too; only the hands are ours.
        fingers = {name: bone["rigify"] for name, bone in bones.items()
                   if bone.get("rigify", {}).get("rigify_type") == "limbs.super_finger"
                   and name.startswith(("thumb.", "f_index.", "f_middle.", "f_ring.",
                                        "f_pinky."))}
        assert len(fingers) == 10, meta_rig
        for name, rigify in fingers.items():
            parameters = rigify.get("rigify_parameters", {})
            assert parameters.get("primary_rotation_axis") == "X", (meta_rig, name)
            assert not parameters.get("make_extra_ik_control", False), (meta_rig, name)
        palms = [name for name, bone in bones.items()
                 if bone.get("rigify", {}).get("rigify_type") == "limbs.super_palm"]
        assert sorted(palms) == ["palm.01.L", "palm.01.R"], meta_rig


def _index_drivers(rig, side="L"):
    master = "f_index.01_master." + side
    return [fcurve for fcurve in rig.animation_data.drivers
            if any(target.data_path == 'pose.bones["{:s}"].scale.y'.format(master)
                   for variable in fcurve.driver.variables for target in variable.targets)]


@pytest.mark.parametrize("option,axis_index,sign,outcome", [
    ("X", 0, 1.0, "read"), ("-X", 0, -1.0, "read"),
    ("Z", 2, 1.0, "no spread"), ("-Z", 2, -1.0, "no spread"),
    ("Y", 1, 1.0, "own axis"), ("-Y", 1, -1.0, "own axis"), ("bogus", 0, None, "not Rigify's")])
def test_the_bend_axis_and_sign_are_read_off_the_drivers(rig, option, axis_index, sign, outcome):
    """rigify_hands.find_hands with the index drivers rewritten to each axis option

    A Z option is accepted as an axis and then refused for its spread: on these
    bones, built to bend about X, a turn about the axis left over moves the tip
    the way a curl does, so no neighbouring finger says which way is "away" -
    which is the answer an edited rig should get rather than a guessed sign.
    """
    expressions = {"X": "(1-sy)*pi", "-X": "-((1-sy)*pi)", "Z": "(1-sy)*pi",
                   "-Z": "-((1-sy)*pi)", "Y": "(1-sy)*pi", "-Y": "-((1-sy)*pi)",
                   "bogus": "(1-sy)*2"}
    drivers = _index_drivers(rig)
    assert len(drivers) == 2
    saved = [(fcurve.array_index, fcurve.driver.expression) for fcurve in drivers]
    try:
        for fcurve in drivers:
            fcurve.array_index = axis_index
            fcurve.driver.expression = expressions[option]
        found = _hands(rig)["left_hand"]
        if outcome != "read":
            assert "index" not in found["fingers"]
            assert "f_index.01_master.L" in found["errors"]["index"]
            assert {"no spread": "which way", "own axis": "own axis",
                    "not Rigify's": "not one of Rigify's"}[outcome] in found["errors"]["index"]
        else:
            axes = found["fingers"]["index"].axes
            bend = axes.col[0]
            assert abs(bend[axis_index] - sign) < 1e-9
            assert abs(axes.col[1][1] - 1.0) < 1e-9
            spread = axes.col[2]
            assert abs(spread[2 - axis_index]) == pytest.approx(1.0)
    finally:
        for fcurve, (index, expression) in zip(drivers, saved):
            fcurve.array_index = index
            fcurve.driver.expression = expression


def test_a_missing_deforming_bone_is_named_not_guessed(rig):
    """rigify_hands.find_hands on a rig whose pinky lost a DEF- bone"""
    bones = rig.data.bones
    original = "DEF-f_pinky.02.R"
    assert original in bones
    bones[original].name = "renamed_for_test"
    try:
        found = _hands(rig)["right_hand"]
        assert "pinky" not in found["fingers"]
        assert original in found["errors"]["pinky"]
        assert list(found["fingers"]) == ["thumb", "index", "middle", "ring"]
    finally:
        bones["renamed_for_test"].name = original


def test_the_same_spread_moves_both_hands_the_same_way(rig):
    """rigify_hands spread signs, measured on fingertips in the character frame"""
    module = _hands_module()
    hands = _hands(rig)
    frame = bridge_module("shared.character_frame").Frame(rig)
    rest = {hand: {name: module.read_finger(frame, rig, finger)["tip"]
                   for name, finger in found["fingers"].items()}
            for hand, found in hands.items()}
    for found in hands.values():
        for finger in found["fingers"].values():
            module.write_finger(rig, finger, 0.0, 1.0)
    bpy.context.view_layer.update()
    for hand, outward in (("left_hand", 1.0), ("right_hand", -1.0)):
        found = hands[hand]
        tips = {name: module.read_finger(frame, rig, finger)["tip"]
                for name, finger in found["fingers"].items()}
        # Mirror images: a left tip moved by +left is a right tip moved by -left.
        assert (tips["pinky"]["forward"] - rest[hand]["pinky"]["forward"]) < 0.0, \
            "the pinky spreads backward, away from the middle finger"
        assert (tips["index"]["forward"] - rest[hand]["index"]["forward"]) > 0.0, \
            "the index spreads forward, away from the middle finger"
        del outward
    left = {name: module.read_finger(frame, rig, finger)["tip"]
            for name, finger in hands["left_hand"]["fingers"].items()}
    right = {name: module.read_finger(frame, rig, finger)["tip"]
             for name, finger in hands["right_hand"]["fingers"].items()}
    for name in left:
        assert left[name]["forward"] == pytest.approx(right[name]["forward"], abs=0.002), name
        assert left[name]["up"] == pytest.approx(right[name]["up"], abs=0.002), name
        assert left[name]["left"] == pytest.approx(-right[name]["left"], abs=0.002), name


def test_what_is_not_a_curl_and_a_spread_says_why(rig):
    """rigify_hands.read_finger: a twist, a posed segment, a hook and a posed palm"""
    module = _hands_module()
    hands = _hands(rig)
    frame = bridge_module("shared.character_frame").Frame(rig)
    index = hands["left_hand"]["fingers"]["index"]
    ring = hands["left_hand"]["fingers"]["ring"]
    pose_bones = rig.pose.bones

    module.write_finger(rig, index, 0.3, 0.0)
    pose_bones[index.master].rotation_euler[1] += 0.2
    bpy.context.view_layer.update()
    assert module.read_finger(frame, rig, index)["reasons"] == ["master_twisted"]

    module.write_finger(rig, index, 0.5, 0.0)
    pose_bones["f_index.02.L"].rotation_euler[0] = 0.3
    bpy.context.view_layer.update()
    reading = module.read_finger(frame, rig, index)
    assert reading["reasons"] == ["segment_posed"]
    assert reading["joint_degrees"][1] == pytest.approx(0.5 * 35.0 + math.degrees(0.3), abs=0.05)

    module.write_finger(rig, index, 0.0, 0.0)
    pose_bones[index.master].scale[1] = 0.45
    bpy.context.view_layer.update()
    hook = module.read_finger(frame, rig, index)
    assert hook["reasons"] == ["knuckle_and_joints_disagree"]
    assert hook["joint_degrees"][0] == pytest.approx(0.0, abs=0.01)
    assert hook["joint_degrees"][1] == pytest.approx(99.0, abs=0.5)
    assert 0.0 < hook["curl"] < 1.0, "a hook's curl is a fit, not the 2.8 its scale implies"

    pose_bones[index.master].scale[1] = 1.0
    pose_bones["palm.L"].rotation_mode = "QUATERNION"
    pose_bones["palm.L"].rotation_quaternion = (0.98, 0.2, 0.0, 0.0)
    bpy.context.view_layer.update()
    assert "palm_posed" in module.read_finger(frame, rig, ring)["reasons"]
    assert module.read_finger(frame, rig, index)["reasons"] == [], \
        "the palm control does not carry the index's base"


def test_a_hand_at_rest_is_open_and_every_shape_matches_itself(rig):
    """rigify_hands.matching_shape over the shape table"""
    module = _hands_module()
    hands = _hands(rig)
    frame = bridge_module("shared.character_frame").Frame(rig)
    found = hands["left_hand"]
    readings = {name: module.read_finger(frame, rig, finger)
                for name, finger in found["fingers"].items()}
    assert module.matching_shape(readings) == "open"
    for shape in module.SHAPES:
        for name, amounts in module.shape_amounts(shape).items():
            module.write_finger(rig, found["fingers"][name], amounts["curl"], amounts["spread"])
        bpy.context.view_layer.update()
        readings = {name: module.read_finger(frame, rig, finger)
                    for name, finger in found["fingers"].items()}
        assert module.matching_shape(readings) == shape
