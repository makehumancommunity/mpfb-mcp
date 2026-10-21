"""
``place_character``: where a character stands in the world, and which way it faces.

No MPFB function places a character; ``HumanService.create_human()`` builds one
at the origin, and every one after it lands on top of the first. Placing is
plain Blender - the character's root object's world matrix - and what this
command owes is the rest of
[FR 045](../../../feature-requests/done/045-placing-a-character/README.md): to
move everything that belongs to the character, to leave alone what it was not
asked to change, to say what is wrong with the character where it now stands,
and to answer with the call that puts it back.

**Every reading and every write is [`shared/placement.py`](../shared/placement.py)'s**,
which ``get_character_summary``'s ``placement`` section and ``add_asset``'s
``subrigs_broken`` read too, so the three cannot disagree about where a
character is or whether its garments are bound to it. **A move breaks no
sub-rig**, measured: what breaks one is equipping it while the character stands
away from the origin, and ``subrigs_broken`` reports that wherever the
character has been moved since, with ``mpfb_refit_human`` as the repair. What is here is the call: the arguments, the order of the
refusals, and the answer.

- ``position`` is a world point ``{"x", "y", "z"}``, any key of which may be
  left out to keep its value, so ``{"x": 2}`` slides a character along without
  lifting it off the floor.
- ``facing`` is degrees about world up from ``-Y``, counter-clockwise from
  above. ``face_toward`` is the alternative: a world point ``{"x", "y"}`` (a
  ``z`` is accepted and ignored) or ``{"object": <name>}``, whose world
  location is used. The turn is computed from where this call's ``position``
  puts the character, so one call can move a character and turn it to the
  camera.

**The subject may have no basemesh**, as in ``export_character``: a character
whose basemesh an export copy removed is found through its body proxy.

**Refusals, in order, and nothing is written by any of them**: the arguments'
shape (mpfb-mcp checks it first; another client may not), the subject, a
``face_toward`` object that does not exist (``face_toward_not_found``), a turn
asked of a tilted root (``character_tilted`` - a ``position`` alone is still
applied to one), and a ``face_toward`` target straight above or below the
character (``face_toward_has_no_direction``).

**Cheap on purpose**: one matrix write and one depsgraph update, no MPFB
recalculation, so placing six characters is six short round trips. The cost
that remains is the footprint, which reads the evaluated vertices of the body
and its assets.

**Nothing is borrowed**: no mode, selection or active object, and no operator.
Blender's undo stack does not see a bridge command's write, so the answer's
``restore_with`` is the undo, as ``reset_pose``'s is.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "place_character",
)

import bpy

from ..log import get_logger
from ..shared import placement
from ..shared import subject_resolution
from ..shared.character_frame import Frame
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_NUMBER
from ..validation import TYPE_OBJECT
from ..validation import TYPE_STRING
from ..validation import is_number

_LOG = get_logger("commands.placecharacter")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("position", TYPE_OBJECT, default=None, nullable=True,
          description="Where the root goes, in world metres: any of 'x', 'y', 'z'. A key left "
                      "out keeps its current value."),
    Param("facing", TYPE_NUMBER, default=None, nullable=True,
          description="Degrees about world up; 0 faces world -Y, positive turns "
                      "counter-clockwise seen from above. Not with face_toward."),
    Param("face_toward", TYPE_OBJECT, default=None, nullable=True,
          description="Turn to face a world point {'x', 'y'} or an object {'object': name}, "
                      "from where 'position' puts the character. Not with facing."),
)

SUMMARY = ("Place a character in the scene: its world position, and the way it faces, absolutely "
           "or toward a point or an object.")

_POSITION_KEYS = ("x", "y", "z")
_POINT_KEYS = ("x", "y", "z")


# ----------------------------------------------------------------------
# Shape. mpfb-mcp checks all of this too; other clients may not.


def _shape_problem(params):
    """Why the arguments cannot be a placement, or ``None``."""
    position = params["position"]
    facing = params["facing"]
    face_toward = params["face_toward"]
    if position is None and facing is None and face_toward is None:
        return "Name at least one of position, facing and face_toward."
    if facing is not None and face_toward is not None:
        return "Give facing or face_toward, not both."
    if position is not None:
        unknown = sorted(key for key in position if key not in _POSITION_KEYS)
        if not position or unknown:
            return "position must be an object with any of x, y, z{:s}.".format(
                "" if not unknown else "; it has unknown key(s) " + ", ".join(unknown))
        if not all(is_number(value) for value in position.values()):
            return "position must hold finite numbers."
    if face_toward is not None:
        if "object" in face_toward:
            if set(face_toward) != {"object"} or not isinstance(face_toward["object"], str) \
                    or not face_toward["object"].strip():
                return ("face_toward must be either {'object': <a name>} alone or a point "
                        "{'x', 'y'}.")
        else:
            unknown = sorted(key for key in face_toward if key not in _POINT_KEYS)
            if unknown or "x" not in face_toward or "y" not in face_toward:
                return ("face_toward must be either {{'object': <a name>}} or a point with x "
                        "and y{:s}.".format("" if not unknown else
                                        "; it has unknown key(s) " + ", ".join(unknown)))
            if not all(is_number(value) for value in face_toward.values()):
                return "face_toward's point must hold finite numbers."
    return None


# ----------------------------------------------------------------------
# The character


def _resolve(services, requested_name):
    """``(subject, resolved_by, basemesh, body, message)``; ``body`` falls back to a body proxy."""
    object_service = services["ObjectService"]
    subject, resolved_by, message = subject_resolution.resolve_subject(
        requested_name, not_done="nothing was moved")
    if subject is None:
        return (None, resolved_by, None, None, message)
    basemesh = object_service.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    body = basemesh
    if body is None:
        body = object_service.find_object_of_type_amongst_nearest_relatives(subject, "Proxymeshes")
    if body is None:
        # The shared sentence's shape (subject_resolution.resolve_basemesh), with
        # the proxy this command also accepts said in the middle of it, as
        # export_character says it.
        return (subject, resolved_by, None, None,
                "'{:s}' has no MakeHuman basemesh among its nearest relatives, so - with no body "
                "proxy either - there is no character to place, and nothing was moved. Call "
                "mpfb_get_object_info to see what it is related to.".format(subject.name))
    return (subject, resolved_by, basemesh, body, None)


def _target_point(face_toward):
    """``(point, object_name)`` for a ``face_toward``; ``point`` is ``None`` for a missing object."""
    if face_toward is None:
        return (None, None)
    if "object" in face_toward:
        target = bpy.data.objects.get(face_toward["object"])
        if target is None:
            return (None, face_toward["object"])
        return (target.matrix_world.to_translation(), target.name)
    return ((float(face_toward["x"]), float(face_toward["y"])), None)


# ----------------------------------------------------------------------
# The answer


def _blocked(subject, resolved_by, basemesh, root, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=root is not None,
        ready=False,
        placed=False,
        blocked_by=reason,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        root_name=None if root is None else root.name,
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _message_for(root, moved_with, external_parent, before, after, face_toward_name,
                 subrigs_broken):
    parts = ["Placed '{:s}' at x {:.3f}, y {:.3f}, z {:.3f}".format(
        root.name, after["position"]["x"], after["position"]["y"], after["position"]["z"])]
    if after["facing"] is not None:
        parts.append(", facing {:.1f} degrees".format(after["facing"]))
    if face_toward_name is not None:
        parts.append(" (toward '{:s}')".format(face_toward_name))
    parts.append(".")
    if moved_with:
        parts.append(" The meta-rig {:s} moved with it, so a refit or a regeneration builds "
                     "where the character is.".format(", ".join("'" + name + "'"
                                                                for name in moved_with)))
    if external_parent is not None:
        parts.append(" Its parent '{:s}' is outside the character and was not changed; the "
                     "values are in world space.".format(external_parent.name))
    if before.tilted:
        parts.append(" The root is tilted, which this tool neither changes nor reproduces, so "
                     "only its position was written.")
    if subrigs_broken:
        parts.append(
            " {:d} garment sub-rig(s) are bound wrong - equipped while the character stood away "
            "from the origin - so in a render their sub-rig-weighted vertices are dragged up to "
            "{:.2f} m away: {:s}. Moving the character neither causes nor cures that; "
            "mpfb_refit_human re-binds them.".format(
                len(subrigs_broken),
                max(record["displacement"] for record in subrigs_broken),
                ", ".join("'{!s}'".format(record["asset_object_name"]
                                          or record["subrig_object_name"])
                          for record in subrigs_broken)))
    return "".join(parts)


def place_character(params, resolution):  # pylint: disable=too-many-locals
    """Place one character, having settled every refusal first."""
    services = resolution.services

    problem = _shape_problem(params)
    if problem is not None:
        return _blocked(None, None, None, None, "invalid_arguments",
                        problem + " Nothing was moved.")

    subject, resolved_by, basemesh, body, message = _resolve(services, params["name"])
    if body is None:
        return _blocked(subject, resolved_by, None, None, "subject_not_found", message)

    root = placement.root_of(body)
    point, face_toward_name = _target_point(params["face_toward"])
    if params["face_toward"] is not None and point is None:
        return _blocked(
            subject, resolved_by, basemesh, root, "face_toward_not_found",
            "No object named '{!s}' exists in this .blend file, so there is nothing to face and "
            "nothing was moved. Call mpfb_list_objects for the scene's objects, or pass a point "
            "{{'x', 'y'}} instead.".format(face_toward_name))

    before = placement.Reading(root)
    turning = params["facing"] is not None or params["face_toward"] is not None
    if turning and before.tilted:
        return _blocked(
            subject, resolved_by, basemesh, root, "character_tilted",
            "'{:s}' is turned about more than world up (its up axis leans {:.1f} degrees), and "
            "this tool writes only a turn about world up, so it would have to straighten the "
            "character and could not put the tilt back. Nothing was moved. A position alone is "
            "still accepted.".format(root.name, before.tilt_degrees),
            tilted=True)

    position = before.position.copy()
    for index, key in enumerate(_POSITION_KEYS):
        if params["position"] is not None and key in params["position"]:
            position[index] = float(params["position"][key])

    facing = params["facing"]
    if params["face_toward"] is not None:
        facing = placement.facing_toward(position, point)
        if facing is None:
            return _blocked(
                subject, resolved_by, basemesh, root, "face_toward_has_no_direction",
                "The face_toward target is straight above or below where the character will "
                "stand (within {:.0f} mm horizontally), which gives no direction to face, so "
                "nothing was moved.".format(placement.NO_DIRECTION_METRES * 1000.0))

    carried = placement.carried_with(services, root)
    external_parent = root.parent
    restore_with = {"mpfb_place_character": placement.restore_arguments(before)}

    placement.place(root, carried, position=params["position"], facing=facing)

    after = placement.describe(services, root)
    moved_with = [blender_object.name for blender_object in carried]

    _LOG.debug("place_character: %r to %r facing %r", root.name, after["position"],
               after["facing"])

    result = dict(
        found=True,
        ready=True,
        placed=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        root_name=root.name,
        moved_with=moved_with,
        external_parent_name=None if external_parent is None else external_parent.name,
        requested_position=params["position"],
        requested_facing=params["facing"],
        requested_face_toward=params["face_toward"],
        position_before=before.position_answer(),
        position_after=after["position"],
        facing_before=before.facing_answer(),
        facing_after=after["facing"],
        tilted=after["tilted"],
        character_frame=Frame(root).describe(),
        footprint=after["footprint"],
        subrigs_broken=after["subrigs_broken"],
        restore_with=restore_with,
        message=_message_for(root, moved_with, external_parent, before, after,
                             face_toward_name if point is not None else None,
                             after["subrigs_broken"]),
    )

    # The verb is "placed". See shared/performed.py.
    return with_performed(result, result["placed"])
