"""
Where a character stands in the scene, which way it faces, and how much room it takes up.

**Three commands must agree about it**
([FR 045](../../../feature-requests/done/045-placing-a-character/README.md)):
``place_character`` writes a placement and reports it, ``get_character_summary``
reports it under the same keys in its ``placement`` section, and ``add_asset``
reports the garment sub-rigs that are bound wrong. A summary that put a character
somewhere other than where the place command had just left it would be the
second opinion [a summary must never be](../../../specifications/responses.md#a-summary-is-never-a-second-opinion),
so :func:`describe` is the one reading all three answer from. ``add_rig``
uses :func:`local_rotation` and :func:`set_local_rotation` to carry a turned
basemesh's rotation over to its new rig, which is the same write in a smaller
form.

**The root is the rig if there is one, and the body otherwise** (:func:`root_of`):
the armature the body is parented to, which is where MPFB's adding functions
put a rig, else the body itself. On a generated Rigify rig that is the
generated rig. Everything else in the character hangs below the root, so moving
the root moves them; a **kept or hidden meta-rig** does not, because Rigify's
generation leaves it beside the rig rather than below it, and it is moved by
the same transform (:func:`carried_with`). If it stayed behind, the next refit
would fit bones to a body at the old position, and the next generation would
build there. The meta-rig is the one ``ObjectService.find_rigify_metarig_by_rig()``
finds, because that is the one ``HumanService.refit()`` refits.

**Everything here is in world terms**, because placement is about the scene: a
root parented to something outside the character (an empty the user grouped
characters under) is placed by its world matrix, and the parent is never
touched. ``position`` is the root's world origin in metres, ``facing`` the
degrees about world up that the character frame's ``forward`` is turned from
world ``-Y`` (MPFB builds every character facing ``-Y``), counter-clockwise
seen from above, as Blender turns about ``Z``, normalised to ``(-180, 180]``.

**What is written is location and yaw, and nothing else.** A placement composes
the root's new world matrix from the location, a rotation about world up and
the root's *existing* world scale, and assigns it; Blender writes the channels
back in whatever rotation mode the object uses. The scale channels are then put
back exactly as they were, and so are the rotation channels when no turn was
asked for, so that a write cannot leak float noise into what it was not asked
to change. A root turned about anything but world up is **tilted**, and a turn
is refused on it by the command: yaw is all a placement can express, so it
could neither keep the tilt nor offer a ``restore_with`` that puts it back.
:data:`TILT_TOLERANCE_DEGREES` is the frame's own rounding.

**``footprint`` is the evaluated geometry, in world axes.** The body and every
equipped mesh asset as they are drawn now - posed, with MPFB's ``Hide helpers``
mask applied, so helper geometry is not counted - and not the rig, nor anything
hidden. World ``x`` and ``y`` rather than the character's own axes, because it
is for spacing characters in a scene; a caller wanting the character's own
extent turns it to ``facing`` 0 first. ``null`` when nothing visible has a
vertex.

**A sub-rig is measured, never presumed broken by where the character is.**
MPFB binds a garment's sub-rig root to the character's rig with a ``CHILD_OF``
whose inverse is set pending, and Blender resolves it while the new sub-rig
still stands at the world origin - before ``ClothesService.set_up_rigging()``
parents it to the rig. On a character at the origin that is the right inverse;
on one placed anywhere else it is off by the rig's own transform, and the
sub-rig-weighted vertices are dragged that far, wherever the character goes
next, the origin included. FR 045's live check measured it on ``ponytail01``:
added at the origin and then moved, the hair stayed on the head; added to a
character at ``(-4, -4)`` turned 60 degrees, it was dragged 5.7 m, still 5.7 m
after moving to the origin, and right again after ``mpfb_refit_human``, which
sets the inverse pending once everything is in place. So a move neither breaks
nor repairs one, and the request's reading - broken whenever the character is
away from the origin - was wrong both ways. :func:`subrigs_broken` measures
each sub-rig's root: where its ``CHILD_OF`` target says it should be, the
target's pose taken from its rest, against where it is, and reports any further
apart than :data:`SUBRIG_TOLERANCE_METRES` with that ``displacement``. Posing
the head, or the sub-rig itself, moves both together and is not a break. A
sub-rig is an armature MPFB typed ``Subrig``
(``Rig.create_armature_and_fit_to_basemesh()``), asked of
``ObjectService.get_object_type()``.

Unlike ``character_frame``, this takes ``services``: the two questions above -
which meta-rig refit will use, and which armature is a sub-rig - are MPFB's to
answer, and a second answer here could disagree with it. Rounding is
``character_frame``'s, so a position here and a frame origin there cannot
disagree in the last digit.
"""

__all__ = (
    "NO_DIRECTION_METRES",
    "TILT_TOLERANCE_DEGREES",
    "Reading",
    "carried_with",
    "describe",
    "facing_toward",
    "footprint",
    "local_rotation",
    "place",
    "restore_arguments",
    "root_of",
    "set_local_rotation",
    "SUBRIG_TOLERANCE_METRES",
    "subrigs_broken",
)

import math

import bpy
import numpy
from mathutils import Matrix  # pylint: disable=import-error
from mathutils import Quaternion  # pylint: disable=import-error
from mathutils import Vector  # pylint: disable=import-error

from . import blender_data
from .character_frame import rounded_degrees
from .character_frame import rounded_metres

# How far a root's up axis may lean from world up and still count as turned
# about it alone: the frame's own rounding of an angle. FR 045's live check
# measured what a rig turned by hand in the viewport carries; see its README.
TILT_TOLERANCE_DEGREES = 0.1

# How close to straight above or below the character a face_toward target may
# be before it gives no direction: the millimetre every position is rounded to.
NO_DIRECTION_METRES = 0.001

# How far a sub-rig's root may be from where its CHILD_OF target puts it before
# the binding counts as broken. A wrong binding is off by the rig's whole
# placement - metres; a right one measured 0.0 posed and unposed.
SUBRIG_TOLERANCE_METRES = 0.01

# What restore_with is kept to: finer than a read-back, so that putting a
# character back is exact rather than a millimetre out (as pose_writing's
# restore entries are). An angle to four decimals, not six: Blender stores a
# rotation channel as a 32-bit float, so 170 degrees reads back as 169.99998,
# and the fifth decimal is storage noise rather than a turn.
_RESTORE_DIGITS = 6
_RESTORE_DEGREE_DIGITS = 4

_AXIS_NAMES = ("x", "y", "z")
_FORWARD = Vector((0.0, -1.0, 0.0))
_UP = Vector((0.0, 0.0, 1.0))


# ----------------------------------------------------------------------
# Which objects


def root_of(body):
    """The object a placement moves: the armature ``body`` is parented to, else ``body``."""
    parent = body.parent
    if parent is not None and parent.type == "ARMATURE":
        return parent
    return body


def carried_with(services, root):
    """What must move with ``root`` without being below it: a kept or hidden meta-rig.

    ``[]`` unless ``root`` is a generated Rigify rig whose meta-rig MPFB can
    find; a meta-rig that is somehow below the root moves anyway and is not
    listed.
    """
    object_service = services["ObjectService"]
    if not object_service.object_is_generated_rigify_rig(root):
        return []
    metarig = object_service.find_rigify_metarig_by_rig(root)
    if metarig is None or metarig in blender_data.with_descendants(root):
        return []
    return [metarig]


# ----------------------------------------------------------------------
# Reading


def _normalised_degrees(degrees):
    """``degrees`` folded into ``(-180, 180]``."""
    folded = math.fmod(degrees, 360.0)
    if folded <= -180.0:
        folded += 360.0
    elif folded > 180.0:
        folded -= 360.0
    return folded


def _facing_of(world_direction):
    """Degrees about world up from ``-Y`` to the horizontal part of a direction, or ``None``."""
    if math.hypot(world_direction.x, world_direction.y) < 1e-9:
        return None
    return _normalised_degrees(math.degrees(math.atan2(world_direction.x, -world_direction.y)))


class Reading:
    """Where one root stands, unrounded: ``position`` (a ``Vector``), ``facing``, ``tilted``.

    ``facing`` is ``None`` only for a root whose ``forward`` points straight up
    or down, which has no direction about world up to report.
    """

    __slots__ = ("root", "position", "facing", "tilt_degrees", "tilted")

    def __init__(self, root):
        world = root.matrix_world
        rotation = world.to_3x3().normalized()
        self.root = root
        self.position = world.to_translation()
        self.facing = _facing_of(rotation @ _FORWARD)
        up = (rotation @ _UP).normalized()
        self.tilt_degrees = math.degrees(math.acos(max(-1.0, min(1.0, up.z))))
        self.tilted = self.tilt_degrees > TILT_TOLERANCE_DEGREES

    def position_answer(self):
        """``{"x", "y", "z"}`` in metres, rounded as every position is."""
        return {name: rounded_metres(value) for name, value in zip(_AXIS_NAMES, self.position)}

    def facing_answer(self):
        """Degrees, rounded as every angle is, in ``(-180, 180]``; ``None`` if there is none."""
        if self.facing is None:
            return None
        rounded = rounded_degrees(math.radians(self.facing))
        return 180.0 if rounded == -180.0 else rounded


def footprint(root):
    """The evaluated world bounding box of what is visible in ``root``'s family, or ``None``.

    ``{"min": {x, y, z}, "max": {x, y, z}, "width", "depth", "height"}`` in
    metres, the last three along world X, Y and Z.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lowest = None
    highest = None
    for blender_object in blender_data.with_descendants(root):
        if blender_object.type != "MESH" or not _visible(blender_object):
            continue
        evaluated = blender_object.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            count = len(mesh.vertices)
            if count == 0:
                continue
            local = numpy.empty(count * 3, dtype=numpy.float32)
            mesh.vertices.foreach_get("co", local)
            matrix = numpy.array(evaluated.matrix_world, dtype=numpy.float64)
            world = local.reshape(count, 3).astype(numpy.float64) @ matrix[:3, :3].T + matrix[:3, 3]
        finally:
            evaluated.to_mesh_clear()
        low = world.min(axis=0)
        high = world.max(axis=0)
        lowest = low if lowest is None else numpy.minimum(lowest, low)
        highest = high if highest is None else numpy.maximum(highest, high)
    if lowest is None or highest is None:
        return None
    extent = highest - lowest
    return {
        "min": {name: rounded_metres(value) for name, value in zip(_AXIS_NAMES, lowest)},
        "max": {name: rounded_metres(value) for name, value in zip(_AXIS_NAMES, highest)},
        "width": rounded_metres(extent[0]),
        "depth": rounded_metres(extent[1]),
        "height": rounded_metres(extent[2]),
    }


def _visible(blender_object):
    """Whether Blender draws the object in the current view layer."""
    try:
        return bool(blender_object.visible_get())
    except RuntimeError:
        return False


def _binding_displacement(subrig):
    """How far the sub-rig's parentless bones are from where their ``CHILD_OF`` puts them, or ``None``.

    The target bone's pose relative to its rest, applied to the owner's rest
    and its own pose channels, is where a correctly bound bone is; a muted,
    partial or object-targeted constraint is not measured.
    """
    worst = None
    for pose_bone in subrig.pose.bones:
        if pose_bone.parent is not None:
            continue
        for constraint in pose_bone.constraints:
            if (constraint.type != "CHILD_OF" or constraint.mute or constraint.influence < 1.0
                    or constraint.target is None or constraint.target.type != "ARMATURE"):
                continue
            target_bone = constraint.target.pose.bones.get(constraint.subtarget)
            if target_bone is None:
                continue
            target_world = constraint.target.matrix_world
            follows = ((target_world @ target_bone.matrix)
                       @ (target_world @ target_bone.bone.matrix_local).inverted_safe())
            expected = (follows @ subrig.matrix_world @ pose_bone.bone.matrix_local
                        @ pose_bone.matrix_basis).to_translation()
            actual = (subrig.matrix_world @ pose_bone.matrix).to_translation()
            distance = (expected - actual).length
            worst = distance if worst is None else max(worst, distance)
    return worst


def subrigs_broken(services, root):
    """One record per sub-rig in ``root``'s family whose binding is off, or ``[]``.

    Each is ``{"subrig_object_name", "asset_object_name", "displacement"}``,
    the garment being the sub-rig's mesh child (``null`` if it has none) and
    ``displacement`` the metres its root is from where it should be, sorted by
    sub-rig name. Reads the depsgraph as it is; a caller that has just written
    something updates it first.
    """
    get_object_type = services["ObjectService"].get_object_type
    records = []
    for blender_object in blender_data.with_descendants(root)[1:]:
        if blender_object.type != "ARMATURE" or get_object_type(blender_object) != "Subrig":
            continue
        displacement = _binding_displacement(blender_object)
        if displacement is None or displacement <= SUBRIG_TOLERANCE_METRES:
            continue
        garments = sorted(child.name for child in blender_object.children if child.type == "MESH")
        records.append({"subrig_object_name": blender_object.name,
                        "asset_object_name": garments[0] if garments else None,
                        "displacement": rounded_metres(displacement)})
    records.sort(key=lambda record: record["subrig_object_name"])
    return records


def describe(services, root):
    """Where the character stands, as every answer reports it under these six keys."""
    reading = Reading(root)
    return {
        "root_name": root.name,
        "position": reading.position_answer(),
        "facing": reading.facing_answer(),
        "tilted": reading.tilted,
        "footprint": footprint(root),
        "subrigs_broken": subrigs_broken(services, root),
    }


def restore_arguments(reading):
    """The ``mpfb_place_character`` arguments that put a root back where ``reading`` was taken.

    Position and facing, kept to more digits than a read-back. A tilted root
    gets position alone: a turn would be refused on it, and the tilt is not
    something a placement changes.
    """
    arguments = {"name": reading.root.name,
                 "position": {name: round(float(value), _RESTORE_DIGITS) + 0.0
                              for name, value in zip(_AXIS_NAMES, reading.position)}}
    if not reading.tilted and reading.facing is not None:
        arguments["facing"] = round(reading.facing, _RESTORE_DEGREE_DIGITS) + 0.0
    return arguments


def facing_toward(position, target):
    """The facing that turns a character at ``position`` toward ``target``, or ``None``.

    Both are world points; only ``x`` and ``y`` count. ``None`` when the target
    is within :data:`NO_DIRECTION_METRES` of straight above or below.
    """
    delta_x = float(target[0]) - float(position[0])
    delta_y = float(target[1]) - float(position[1])
    if math.hypot(delta_x, delta_y) < NO_DIRECTION_METRES:
        return None
    return _facing_of(Vector((delta_x, delta_y, 0.0)))


# ----------------------------------------------------------------------
# Writing


def local_rotation(blender_object):
    """An object's own rotation channels, whatever its rotation mode, as a ``Quaternion``."""
    return blender_object.matrix_basis.decompose()[1]


def set_local_rotation(blender_object, quaternion):
    """Write a rotation into an object's own channels, in the rotation mode it already uses."""
    mode = blender_object.rotation_mode
    quaternion = Quaternion(quaternion)
    if mode == "QUATERNION":
        blender_object.rotation_quaternion = quaternion
    elif mode == "AXIS_ANGLE":
        axis, angle = quaternion.to_axis_angle()
        blender_object.rotation_axis_angle = (angle, axis.x, axis.y, axis.z)
    else:
        blender_object.rotation_euler = quaternion.to_euler(mode, blender_object.rotation_euler)


def _channels(blender_object):
    return (blender_object.scale.copy(), blender_object.rotation_euler.copy(),
            blender_object.rotation_quaternion.copy(), tuple(blender_object.rotation_axis_angle))


def _put_back(blender_object, channels, rotation):
    scale, euler, quaternion, axis_angle = channels
    blender_object.scale = scale
    if rotation:
        blender_object.rotation_euler = euler
        blender_object.rotation_quaternion = quaternion
        blender_object.rotation_axis_angle = axis_angle


def place(root, carried, position=None, facing=None):
    """Move ``root``, and ``carried`` by the same transform, then update the depsgraph.

    ``position`` is a dict with any of ``x``, ``y``, ``z`` (a key left out keeps
    its value); ``facing`` is degrees, or ``None`` to keep the rotation as it
    is. The caller refuses a turn on a tilted root before calling this.
    """
    before = root.matrix_world.copy()
    translation = before.to_translation()
    for index, name in enumerate(_AXIS_NAMES):
        if position is not None and name in position:
            translation[index] = float(position[name])
    if facing is None:
        linear = before.to_3x3()
    else:
        scale = [column.length for column in before.to_3x3().col]
        linear = Matrix.Rotation(math.radians(float(facing)), 3, "Z") @ Matrix.Diagonal(scale)
    after = Matrix.Translation(translation) @ linear.to_4x4()
    delta = after @ before.inverted_safe()

    keep_rotation = facing is None
    for blender_object, world in [(root, after)] + [
            (other, delta @ other.matrix_world) for other in carried]:
        channels = _channels(blender_object)
        blender_object.matrix_world = world
        _put_back(blender_object, channels, keep_rotation)
    bpy.context.view_layer.update()
