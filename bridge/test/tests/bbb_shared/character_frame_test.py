"""
``shared/character_frame.py`` called directly: the frame every posing command reports in.

Two claims, and the second is the one FR 041 refused to assume:

- **The conversions are each other's inverse and follow the rig object**, not
  the world: a rig object moved and turned away from the origin reports the
  same frame coordinates for the same bone, and a world point taken into the
  frame and back is the point it started as. FR 042's writers convert the other
  way through these functions, so a disagreement would be a silent defect.
- **MPFB's rigs face local -Y with their ``.L`` side on local +X.** The frame
  is built on that, and it is asserted against freshly built characters here
  rather than written down as a belief: a default rig and a Rigify meta-rig,
  read through their own bones - the toes point forward, the left hand is on
  the left, the head is up. ``get_pose_controls_test.py`` asserts the same of a
  generated rig.
"""

import math

import bpy
from mathutils import Euler
from mathutils import Quaternion
from mathutils import Vector

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import rigged_character
from .._fixtures import services_or_skip


def _frame_module():
    return bridge_module("shared.character_frame")


def _empty_rig(name):
    """An armature object with no bones: all the frame reads is its world matrix."""
    rig = bpy.data.objects.new(name, bpy.data.armatures.new(name + "Data"))
    bpy.context.scene.collection.objects.link(rig)
    return rig


def _close(first, second, tolerance=0.0011):
    return all(abs(first[key] - second[key]) <= tolerance for key in ("forward", "left", "up"))


def test_an_unmoved_rig_object_is_the_world_turned_to_face_minus_y():
    """character_frame.Frame on a rig object at the origin, unrotated"""
    rig = _empty_rig("FrameAtOrigin")
    try:
        described = _frame_module().Frame(rig).describe()
        assert described == {"origin": [0.0, 0.0, 0.0], "forward": [0.0, -1.0, 0.0],
                             "left": [1.0, 0.0, 0.0], "up": [0.0, 0.0, 1.0]}
    finally:
        bpy.data.objects.remove(rig, do_unlink=True)


def test_the_frame_follows_the_rig_object_and_round_trips():
    """character_frame.Frame on a rig object moved and turned 90 degrees"""
    rig = _empty_rig("FrameTurned")
    try:
        rig.location = (2.0, 1.0, 0.5)
        rig.rotation_euler = Euler((0.0, 0.0, math.radians(90.0)))
        bpy.context.view_layer.update()
        frame = _frame_module().Frame(rig)

        assert frame.describe()["forward"] == [1.0, 0.0, 0.0], \
            "turned 90 degrees about up, the character faces world +X"
        # A point one metre in front of the character and half a metre to its left.
        world = frame.world_point({"forward": 1.0, "left": 0.5})
        assert _close(frame.point(world), {"forward": 1.0, "left": 0.5, "up": 0.0})
        # The same armature-space point reads the same however the object stands.
        assert _close(frame.armature_point(Vector((0.3, -0.2, 1.0))),
                      {"forward": 0.2, "left": 0.3, "up": 1.0})
        assert frame.armature_direction(Vector((0.0, -2.0, 0.0))) == \
            {"forward": 1.0, "left": 0.0, "up": 0.0}
    finally:
        bpy.data.objects.remove(rig, do_unlink=True)


def test_a_rotation_is_an_axis_in_the_frame_and_degrees_the_short_way():
    """character_frame.Frame.rotation"""
    rig = _empty_rig("FrameRotation")
    try:
        frame = _frame_module().Frame(rig)
        quarter_turn = Quaternion(Vector((0.0, 0.0, 1.0)), math.radians(90.0))
        assert frame.rotation(quarter_turn) == {"axis": {"forward": 0.0, "left": 0.0, "up": 1.0},
                                                "degrees": 90.0}
        # 270 degrees one way is 90 the other: an agent is told the short way.
        long_way = Quaternion(Vector((0.0, 0.0, 1.0)), math.radians(270.0))
        assert frame.rotation(long_way) == {"axis": {"forward": 0.0, "left": 0.0, "up": -1.0},
                                            "degrees": 90.0}
        assert frame.rotation(Quaternion()) == {"axis": None, "degrees": 0.0}
    finally:
        bpy.data.objects.remove(rig, do_unlink=True)


def _assert_mpfb_convention(frame, bones, left_hand, left_toe, head):
    hand = frame.armature_point(bones[left_hand].head_local)
    assert hand["left"] > 0.3, "the .L hand is on the character's left: {!r}".format(hand)
    toe = frame.armature_direction(bones[left_toe].tail_local - bones[left_toe].head_local)
    assert toe["forward"] > 0.5, "the toes point forward: {!r}".format(toe)
    top = frame.armature_point(bones[head].head_local)
    assert top["up"] > 1.0, "the head is up: {!r}".format(top)


def test_a_default_rig_faces_minus_y_with_its_left_side_on_plus_x():
    """character_frame against MPFB's default rig, as add_rig builds it"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "default")
        frame = _frame_module().Frame(rig)
        _assert_mpfb_convention(frame, rig.data.bones, "wrist.L", "foot.L", "head")


def test_a_rigify_meta_rig_faces_minus_y_with_its_left_side_on_plus_x():
    """character_frame against MPFB's human_toes meta-rig, which Rigify generates from"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "rigify.human_toes")
        frame = _frame_module().Frame(rig)
        _assert_mpfb_convention(frame, rig.data.bones, "hand.L", "toe.L", "spine.006")
