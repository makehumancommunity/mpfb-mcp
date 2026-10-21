"""
Where "forward", "left" and "up" are, for one character.

**Every position and direction a posing command reports or takes is in this
frame**, never in world space
([FR 041](../../../feature-requests/done/041-pose-controls-and-read-back/README.md),
requirement 3): metres along ``forward``, ``left`` and ``up``, measured from
the rig object's origin. ``left`` is the character's own left, the ``.L`` side.
A character that has been moved and turned away from the world origin still
has its hand ``0.4`` to the ``left``, which is the number an agent can reason
with; a world position would change every time the character is placed.

**The frame comes from the rig object's world matrix, not from the pose.** A
character whose torso is twisted still faces where its rig object faces, so
``forward`` stays put while the character is being posed. That is the only
definition under which a later relative move (``move_by: {"forward": 0.2}``)
means the same thing at the start and the end of a posing session, and it is
why this module exists before it has a second user: the transform tool
([FR 042](../../../feature-requests/done/042-posing-bones-switches-and-reset/README.md))
converts the other way through these same functions, and a ``forward`` that
disagreed between reading and writing would be a silent and very visible
defect.

**Which local axes are forward and left is MPFB's convention, confirmed rather
than assumed.** Every rig MPFB builds - the standard rigs, a Rigify meta-rig
and what Rigify generates from it - faces local ``-Y`` with its ``.L`` side on
local ``+X``: a ``rigify_generated.human_toes`` rig puts ``nose_master`` at
``y = -0.13`` and ``hand_ik.L`` at ``x = +0.40``, a ``default`` rig puts
``foot.L``'s tail at ``y = -0.08`` and ``wrist.L`` at ``x = +0.45``.
``bbb_shared/character_frame_test.py`` asserts it against a freshly built
character of each kind, so a change in MPFB fails a test rather than mirroring
every answer.

**The three axes are unit vectors, the origin is in world space**, and both are
reported on every answer (:meth:`Frame.describe`), so a world position is one
transform away for a caller who wants one. A rig object with a scale other
than one still reports metres: the axes are normalised, so a frame coordinate
is a world distance, not an armature-space one.

**Rounding happens here, once.** Positions to the millimetre, unit vectors to
three decimals, angles to a tenth of a degree. A command that rounded for itself
would make two answers about one bone disagree in the last digit.

Like ``selection`` and ``blender_data``, it reads nothing out of MPFB and takes
no ``services``.
"""

__all__ = (
    "AXES",
    "Frame",
    "rounded_degrees",
    "rounded_metres",
)

import math

from mathutils import Quaternion  # pylint: disable=import-error
from mathutils import Vector  # pylint: disable=import-error

# The frame's three axis names, in the order every vector in an answer lists them.
AXES = ("forward", "left", "up")

# Which local axis of an MPFB rig object each frame axis is. See the module
# docstring for how this was established.
_LOCAL_AXES = {
    "forward": Vector((0.0, -1.0, 0.0)),
    "left": Vector((1.0, 0.0, 0.0)),
    "up": Vector((0.0, 0.0, 1.0)),
}

_POSITION_DIGITS = 3
_DIRECTION_DIGITS = 3
_DEGREE_DIGITS = 1


def _clean(value, digits):
    """``round()``, with ``-0.0`` turned into ``0.0`` so an answer never shows it."""
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0.0 else rounded


def rounded_degrees(radians):
    """An angle in radians as degrees, rounded the way every angle here is."""
    return _clean(math.degrees(radians), _DEGREE_DIGITS)


def rounded_metres(value):
    """A distance or a world coordinate in metres, rounded the way every position here is.

    Public since FR 045, whose placement answers are in world space rather than
    in the frame and are still rounded here, once.
    """
    return _clean(value, _POSITION_DIGITS)


class Frame:
    """One character's frame: an origin and three unit axes, all in world space."""

    def __init__(self, rig_object):
        world = rig_object.matrix_world
        self.rig_object = rig_object
        self.origin = world.to_translation()
        rotation = world.to_3x3()
        self.axes = {}
        for name in AXES:
            axis = rotation @ _LOCAL_AXES[name]
            # A degenerate (zero-scaled) rig object has no direction to give.
            # Falling back to the unrotated axis keeps the answer finite and is
            # no less true than anything else about an object of zero size.
            self.axes[name] = axis.normalized() if axis.length > 0.0 else _LOCAL_AXES[name].copy()
        self._armature_to_world = world.copy()

    # ------------------------------------------------------------------
    # World space <-> frame

    def _components(self, world_vector):
        return [self.axes[name].dot(world_vector) for name in AXES]

    def point(self, world_point):
        """A world-space position as ``{forward, left, up}`` in metres, to the millimetre."""
        offset = Vector(world_point) - self.origin
        return {name: _clean(value, _POSITION_DIGITS)
                for name, value in zip(AXES, self._components(offset))}

    def offset(self, world_vector):
        """A world-space displacement as ``{forward, left, up}`` in metres."""
        return {name: _clean(value, _POSITION_DIGITS)
                for name, value in zip(AXES, self._components(Vector(world_vector)))}

    def direction(self, world_vector):
        """A world-space direction as a unit ``{forward, left, up}``, or ``None`` if it has none."""
        vector = Vector(world_vector)
        if vector.length == 0.0:
            return None
        return {name: _clean(value, _DIRECTION_DIGITS)
                for name, value in zip(AXES, self._components(vector.normalized()))}

    def world_point(self, frame_point):
        """``{forward, left, up}`` (any key may be missing, meaning 0.0) as a world position."""
        return self.origin + self.world_vector(frame_point)

    def world_vector(self, frame_vector):
        """``{forward, left, up}`` as a world-space vector; a missing key means 0.0."""
        vector = Vector((0.0, 0.0, 0.0))
        for name in AXES:
            vector += self.axes[name] * float(frame_vector.get(name, 0.0))
        return vector

    # ------------------------------------------------------------------
    # Armature space -> frame. Bone data (``bone.matrix_local``,
    # ``pose_bone.matrix``) is in the rig object's own space.

    def armature_point(self, armature_point):
        """A position in the rig's armature space, in the frame."""
        return self.point(self._armature_to_world @ Vector(armature_point))

    def armature_world(self, armature_point):
        """A position in the rig's armature space, in world space. Unrounded."""
        return self._armature_to_world @ Vector(armature_point)

    def armature_direction(self, armature_vector):
        """A direction in the rig's armature space, in the frame."""
        return self.direction(self._armature_to_world.to_3x3() @ Vector(armature_vector))

    def rotation(self, armature_rotation):
        """An armature-space rotation as ``{"axis": {forward, left, up}, "degrees": d}``.

        ``armature_rotation`` is anything ``mathutils`` turns into a
        ``Quaternion``. The angle is the short way round, 0 to 180 degrees, and
        a rotation too small to have an axis reports ``axis: null`` and
        ``degrees: 0.0``.
        """
        quaternion = Quaternion(armature_rotation).normalized()
        if quaternion.w < 0.0:
            # The same rotation, the short way round.
            quaternion.negate()
        axis, angle = quaternion.to_axis_angle()
        degrees = rounded_degrees(angle)
        if degrees == 0.0:
            return {"axis": None, "degrees": 0.0}
        return {"axis": self.armature_direction(axis), "degrees": degrees}

    # ------------------------------------------------------------------
    # Frame -> armature space, for the writers. Unrounded: a value a caller
    # sent is used as sent.

    def to_armature_point(self, frame_point):
        """``{forward, left, up}`` (a missing key is 0.0) as a position in armature space."""
        return self._armature_to_world.inverted() @ self.world_point(frame_point)

    def to_armature_vector(self, frame_vector):
        """``{forward, left, up}`` as a displacement in armature space, metres for metres."""
        return self._armature_to_world.inverted().to_3x3() @ self.world_vector(frame_vector)

    def to_armature_direction(self, frame_vector):
        """``{forward, left, up}`` as a unit direction in armature space, or ``None`` if zero.

        Through the rig object's rotation alone, so a scaled rig object does not
        skew a direction; :meth:`armature_direction` is the inverse.
        """
        vector = self._armature_rotation().inverted() @ self.world_vector(frame_vector)
        if vector.length == 0.0:
            return None
        return vector.normalized()

    def to_armature_rotation(self, frame_rotation):
        """``{"axis": {forward, left, up} | None, "degrees": d}`` as an armature-space ``Quaternion``.

        The inverse of :meth:`rotation`: an ``axis`` of ``null`` (or ``degrees``
        of 0) is no rotation at all, which is how a read-back reports a bone at
        rest.
        """
        axis = frame_rotation.get("axis")
        degrees = float(frame_rotation.get("degrees", 0.0))
        if axis is None or degrees == 0.0:
            return Quaternion()
        direction = self.to_armature_direction(axis)
        if direction is None:
            return Quaternion()
        return Quaternion(direction, math.radians(degrees))

    def _armature_rotation(self):
        return self._armature_to_world.to_quaternion()

    def describe(self):
        """The frame itself, in world space: what every answer reports as ``character_frame``."""
        answer = {"origin": [_clean(value, _POSITION_DIGITS) for value in self.origin]}
        for name in AXES:
            answer[name] = [_clean(value, _DIRECTION_DIGITS) for value in self.axes[name]]
        return answer
