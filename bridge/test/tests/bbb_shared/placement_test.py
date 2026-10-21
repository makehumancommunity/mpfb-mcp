"""
``shared/placement.py`` called directly: where a character is, and how it is moved.

Three claims, each one a way the place command could go wrong without any of
its own answers looking odd:

- **The root is the rig, else the body**, and a kept meta-rig is carried, not
  found below it.
- **Yaw and tilt read the same through every rotation mode.** MPFB normalises a
  rig's rotation mode and leaves a basemesh in Blender's ``XYZ``; a user may
  change either. The reading goes through the world matrix, so the mode must
  not matter, and a write must land in whatever mode the object already uses.
- **Scale is never written.** A placement keeps the scale channels exactly,
  and keeps the rotation channels exactly when no turn was asked for, so that
  writing a world matrix leaks no float noise into what it was not asked to
  change.

The objects are bare armatures and empties: all a reading needs is a world
matrix, and all a write changes is one.
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

MODES = ("XYZ", "ZXY", "QUATERNION", "AXIS_ANGLE")


def _placement():
    return bridge_module("shared.placement")


def _bare(name, kind="ARMATURE"):
    data = bpy.data.armatures.new(name + "Data") if kind == "ARMATURE" else None
    blender_object = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(blender_object)
    return blender_object


def _remove(*blender_objects):
    for blender_object in blender_objects:
        bpy.data.objects.remove(blender_object, do_unlink=True)


def _set_rotation(blender_object, mode, quaternion):
    blender_object.rotation_mode = mode
    _placement().set_local_rotation(blender_object, quaternion)
    bpy.context.view_layer.update()


def test_the_root_is_the_rig_else_the_body():
    """placement.root_of on an unrigged and a rigged character"""
    services = services_or_skip()
    placement = _placement()
    with Character() as character:
        assert placement.root_of(character.basemesh) is character.basemesh
        rig = rigged_character(services, character, "default")
        assert placement.root_of(character.basemesh) is rig
        assert placement.carried_with(services, rig) == [], \
            "only a generated Rigify rig carries anything with it"


def test_a_hidden_metarig_is_carried_rather_than_below_the_rig():
    """placement.carried_with on a generated human_toes rig with its meta-rig hidden"""
    services = services_or_skip()
    with Character() as character:
        generated = rigged_character(services, character, "generated:human_toes")
        carried = _placement().carried_with(services, generated)
        assert len(carried) == 1, carried
        assert carried[0] is services["ObjectService"].find_rigify_metarig_by_rig(generated)
        assert carried[0].parent is not generated, "Rigify leaves the meta-rig beside its rig"


def test_yaw_and_tilt_read_the_same_through_every_rotation_mode():
    """placement.Reading on one turn and one tilt, in four rotation modes"""
    rig = _bare("PlacementModes")
    try:
        for mode in MODES:
            _set_rotation(rig, mode, Quaternion(Vector((0.0, 0.0, 1.0)), math.radians(30.0)))
            reading = _placement().Reading(rig)
            assert reading.facing_answer() == 30.0, (mode, reading.facing)
            assert reading.tilted is False, (mode, reading.tilt_degrees)

            _set_rotation(rig, mode, Euler((math.radians(5.0), 0.0, math.radians(30.0))).to_quaternion())
            reading = _placement().Reading(rig)
            assert reading.tilted is True, mode
            assert abs(reading.tilt_degrees - 5.0) < 1e-3, (mode, reading.tilt_degrees)
    finally:
        _remove(rig)


def test_facing_is_folded_into_minus_180_to_180():
    """placement.place with turns past half a turn either way"""
    rig = _bare("PlacementFolding")
    try:
        for asked, answered in ((190.0, -170.0), (-180.0, 180.0), (540.0, 180.0), (-30.0, -30.0)):
            _placement().place(rig, [], facing=asked)
            assert _placement().Reading(rig).facing_answer() == answered, asked
    finally:
        _remove(rig)


def test_a_turn_is_written_in_the_mode_the_object_uses_and_scale_is_kept_exactly():
    """placement.place on a scaled object in each rotation mode"""
    rig = _bare("PlacementWrite")
    try:
        for mode in MODES:
            rig.rotation_mode = mode
            rig.scale = (0.1, 0.1, 0.1)
            scale_before = tuple(rig.scale)
            _placement().place(rig, [], position={"x": 2.0, "y": -1.0}, facing=45.0)

            assert rig.rotation_mode == mode, "a placement must not change the rotation mode"
            assert tuple(rig.scale) == scale_before, (mode, tuple(rig.scale))
            reading = _placement().Reading(rig)
            assert reading.position_answer() == {"x": 2.0, "y": -1.0, "z": 0.0}, mode
            assert reading.facing_answer() == 45.0, mode
            if mode == "QUATERNION":
                assert tuple(rig.rotation_euler) == (0.0, 0.0, 0.0), \
                    "a quaternion object is turned through its quaternion"
            _placement().place(rig, [], position={"x": 0.0, "y": 0.0}, facing=0.0)
    finally:
        _remove(rig)


def test_a_move_alone_keeps_every_rotation_channel_exactly():
    """placement.place with a position and no facing, on a tilted object"""
    rig = _bare("PlacementTilted")
    try:
        rig.rotation_euler = (0.3, -0.2, 1.1)
        bpy.context.view_layer.update()
        euler = tuple(rig.rotation_euler)
        _placement().place(rig, [], position={"z": 0.5})
        assert tuple(rig.rotation_euler) == euler
        assert _placement().Reading(rig).position_answer()["z"] == 0.5
    finally:
        _remove(rig)


def test_an_external_parent_is_placed_through_and_never_changed():
    """placement.place on an object parented to a moved and turned empty"""
    parent = _bare("PlacementGroup", kind="EMPTY")
    rig = _bare("PlacementChild")
    try:
        parent.location = (1.0, 2.0, 0.0)
        parent.rotation_euler = (0.0, 0.0, math.radians(60.0))
        rig.parent = parent
        bpy.context.view_layer.update()
        parent_world = parent.matrix_world.copy()

        _placement().place(rig, [], position={"x": -3.0, "y": 4.0, "z": 0.0}, facing=-90.0)

        assert parent.matrix_world == parent_world, "the parent is outside the character"
        reading = _placement().Reading(rig)
        assert reading.position_answer() == {"x": -3.0, "y": 4.0, "z": 0.0}
        assert reading.facing_answer() == -90.0
    finally:
        _remove(rig, parent)


def test_what_is_carried_moves_by_the_same_transform():
    """placement.place with a second object carried beside the root"""
    rig = _bare("PlacementRoot")
    metarig = _bare("PlacementBeside")
    try:
        metarig.location = (0.5, 0.0, 0.0)
        bpy.context.view_layer.update()
        _placement().place(rig, [metarig], position={"x": 1.0}, facing=90.0)
        moved = metarig.matrix_world.to_translation()
        assert (moved - Vector((1.0, 0.5, 0.0))).length < 1e-6, \
            "half a metre to the root's +X, turned 90 degrees, is half a metre to world +Y"
        assert _placement().Reading(metarig).facing_answer() == 90.0
    finally:
        _remove(rig, metarig)


def test_facing_toward_points_forward_at_the_target():
    """placement.facing_toward, and a target straight overhead"""
    placement = _placement()
    assert placement.facing_toward((0.0, 0.0, 0.0), (0.0, -5.0)) == 0.0
    assert abs(placement.facing_toward((0.0, 0.0, 0.0), (5.0, 0.0)) - 90.0) < 1e-9
    assert abs(placement.facing_toward((1.0, 1.0, 0.0), (1.0, 3.0)) - 180.0) < 1e-9
    assert placement.facing_toward((1.0, 1.0, 0.0), (1.0, 1.0002)) is None
