"""
``set_pose_bones``: move, rotate, aim and scale a character's controls, as one all-or-nothing batch.

The first pose writer ([FR 042](../../../feature-requests/done/042-posing-bones-switches-and-reset/README.md)).
The session it comes from posed a karate stance through ``execute_blender_code``
with a helper that set ``pose_bone.matrix`` from a world-space move, and worked
every move out by hand in bone-local axes that mix four rotation modes and
arbitrary rolls. This takes the move in **the character frame**
([`shared/character_frame.py`](../shared/character_frame.py)) instead, in
exactly the shape ``get_pose`` reads back: a position as ``{forward, left,
up}``, a rotation as ``{"axis": ..., "degrees": ...}``.

**One entry per bone, at most one change of each kind**: a position
(``move_by`` or ``move_to``), a rotation (``rotate_by``, ``rotate_to`` or
``aim`` with an optional ``twist``) and ``scale_to``. ``move_to`` and
``rotate_to`` take ``get_pose``'s ``head`` and ``rotation`` unchanged, which is
what makes a read-back, and ``reset_pose``'s ``restore_with``, a write.
``rotate_to`` is the orientation from rest **including what the parents did**,
as the read-back reports it. ``move_by`` and ``rotate_by`` are relative to the
bone's own transform before its constraints, which on a control without any -
every Rigify control - is where it is; a constraint's effect, such as an IK
solver's rotation of a chain's first bone, is therefore never baked into the
bone's channels. ``aim`` swings the bone from its **rest**
orientation, not its current one, so one ``aim`` and ``twist`` always give the
same orientation. ``scale_to`` is the one input not in the frame: factors
relative to rest in the bone's own axes, ``y`` along it, because scale only
means something along a bone. On the default rig a finger scaled is a finger
deformed, not curled; it is still a legitimate write, and Rigify's fist is
exactly that on its finger masters.

**Who may be written is decided before anything is**
([`shared/pose_writing.py`](../shared/pose_writing.py)'s ``charge_refusal``).
On a classified rig a bone that is not a control, an FK bone while ``IK_FK``
hands the limb to IK (or an IK control while it hands it to FK), and an FK bone
one of MPFB's helpers drives are each refused, with ``write_instead`` naming
the write that would work - for the switch, an entry for
``mpfb_set_pose_switches``, which is the first refusal here to name another
tool's argument. A channel a driver sets is refused on every rig, since the
driver would put it back at once. An unclassified rig gets only the lock and
driver checks: nothing is known about which of its bones are in charge.

**Locks are checked after writing, and that is why the batch is snapshotted.**
``pose_bone.matrix`` ignores ``lock_location``/``lock_rotation``/``lock_scale``,
and whether a ``move_to`` touches a locked channel depends on where the parents
ended up, which is only known once they have been written. So every bone the
call will touch is copied, the batch is written parent before child with the
depsgraph updated after each bone, every lock is checked, and **on any failure
the copy is put back exactly** - the second form of
[a batched mutating tool resolves before it writes](../../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes),
allowed only because pose basis data can be put back exactly. A connected
bone's location counts as locked: its head is its parent's tail.

**``symmetry`` mirrors the instruction, not the result.** The counterpart is
``bpy.utils.flip_name()``'s; on a classified rig it must be a control with the
mirrored body part and the same role. A position negates ``left``; a rotation
``{axis, degrees}`` becomes ``{(-forward, left, -up), degrees}``, which is the
mirror image of that rotation; ``aim`` negates ``left`` and ``twist`` negates.
From a symmetric start, that gives a symmetric pose. A mirrored write is its own
change, reported straight after its source with ``mirrored_from``.

**Requested beside achieved.** A constraint, an IK chain or a limit can stop a
bone short, so every change reports where it did end up, ``achieved`` and, when
it did not arrive, ``deviation`` - measured after the whole batch, with the
tolerance ``achieved_measure`` states. A write to a channel the rig's action
animates is made and flagged ``overwritten_on_frame_change``, because the next
frame change puts the keyed value back; keyframes are never touched.

**What moved as a consequence** is reported by
[`shared/pose_reading.py`](../shared/pose_reading.py), the code ``get_pose``
reads with: the landmarks before and after, and each limb's reach and stretch
after, under ``get_pose``'s keys, with ``limbs_made_stretched`` and
``limbs_made_unreachable`` naming what this call did.

**Nothing is borrowed**: no mode, selection or active object, and no operator.
An armature showing its rest position is posed anyway and says so
(``pose_position``), since a pose that does not show is exactly what a caller
checking with a screenshot would misread. There is no MPFB service to wrap:
``RigService.set_pose_from_dict()`` goes through ``bpy.ops.pose`` and needs pose
mode and a selection.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "set_pose_bones",
)

import difflib
import math

import bpy
from mathutils import Quaternion  # pylint: disable=import-error
from mathutils import Vector  # pylint: disable=import-error

from ..log import get_logger
from ..shared import pose_controls
from ..shared import pose_reading
from ..shared import pose_writing
from ..shared.character_frame import AXES
from ..shared.character_frame import Frame
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import is_number
from ..validation import TYPE_ARRAY
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setposebones")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("bones", TYPE_ARRAY, default=(),
          description="One object per bone: 'bone', at most one of 'move_by'/'move_to', at "
                      "most one of 'rotate_by'/'rotate_to'/'aim' (with 'twist'), 'scale_to', "
                      "and 'symmetry'."),
)

SUMMARY = ("Move, rotate, aim and scale a character's pose controls in the character frame, as "
           "one all-or-nothing batch.")

_POSITIONS = ("move_by", "move_to")
_ROTATIONS = ("rotate_by", "rotate_to", "aim")
_KEYS = ("bone",) + _POSITIONS + _ROTATIONS + ("twist", "scale_to", "symmetry")


# ----------------------------------------------------------------------
# Shape. mpfb-mcp checks all of this too; other clients may not.


def _vector_error(key, value, nonzero):
    if not isinstance(value, dict) or not value:
        return "'{:s}' must be an object with any of {:s}".format(key, ", ".join(AXES))
    unknown = sorted(name for name in value if name not in AXES)
    if unknown:
        return "'{:s}' has unknown key(s) {:s}; its keys are {:s}".format(
            key, ", ".join(unknown), ", ".join(AXES))
    if not all(is_number(component) for component in value.values()):
        return "'{:s}' must hold finite numbers".format(key)
    if nonzero and all(float(component) == 0.0 for component in value.values()):
        return "'{:s}' must not be the zero vector".format(key)
    return None


def _rotation_error(key, value):
    if not isinstance(value, dict) or set(value) != {"axis", "degrees"}:
        return "'{:s}' must be an object with exactly 'axis' and 'degrees'".format(key)
    if not is_number(value["degrees"]):
        return "'{:s}' degrees must be a finite number".format(key)
    if value["axis"] is None and key == "rotate_to":
        # get_pose reports a bone at rest as {"axis": null, "degrees": 0.0}.
        return None
    return _vector_error(key + " axis", value["axis"], nonzero=True)


def _shape_error(entry):  # pylint: disable=too-many-return-statements
    """Why an entry is malformed, or ``None``."""
    if not isinstance(entry, dict):
        return "an entry must be an object"
    unknown = sorted(key for key in entry if key not in _KEYS)
    if unknown:
        return "unknown key(s) {:s}; known keys are {:s}".format(
            ", ".join(unknown), ", ".join(_KEYS))
    if not isinstance(entry.get("bone"), str) or not entry["bone"].strip():
        return "'bone' must be a non-empty string"
    if sum(key in entry for key in _POSITIONS) > 1:
        return "at most one of move_by and move_to"
    if sum(key in entry for key in _ROTATIONS) > 1:
        return "at most one of rotate_by, rotate_to and aim"
    if not any(key in entry for key in _POSITIONS + _ROTATIONS + ("scale_to",)):
        return "the entry changes nothing; give a position, a rotation or scale_to"
    if "twist" in entry and "aim" not in entry:
        return "'twist' is only taken with 'aim'"
    if "twist" in entry and not is_number(entry["twist"]):
        return "'twist' must be a finite number of degrees"
    for key in _POSITIONS:
        if key in entry:
            error = _vector_error(key, entry[key], nonzero=False)
            if error:
                return error
    for key in ("rotate_by", "rotate_to"):
        if key in entry:
            error = _rotation_error(key, entry[key])
            if error:
                return error
    if "aim" in entry:
        error = _vector_error("aim", entry["aim"], nonzero=True)
        if error:
            return error
    if "scale_to" in entry:
        scale = entry["scale_to"]
        if not isinstance(scale, dict) or not scale or any(axis not in "xyz" or len(axis) != 1
                                                            for axis in scale):
            return "'scale_to' must be an object with any of x, y, z"
        if not all(is_number(factor) and factor > 0.0 for factor in scale.values()):
            return "'scale_to' factors must be finite positive numbers"
    if "symmetry" in entry and not isinstance(entry["symmetry"], bool):
        return "'symmetry' must be a bool"
    return None


# ----------------------------------------------------------------------
# Mirroring the instruction


def _mirrored_vector(vector):
    return {axis: (-value if axis == "left" else value) for axis, value in vector.items()}


def _mirrored_rotation(rotation):
    """The mirror image of ``{axis, degrees}`` across the character's own sagittal plane."""
    if rotation["axis"] is None:
        return dict(rotation)
    axis = {name: (value if name == "left" else -value)
            for name, value in rotation["axis"].items()}
    return {"axis": axis, "degrees": rotation["degrees"]}


def _mirrored(entry, counterpart):
    mirrored: dict = {"bone": counterpart}
    for key in _POSITIONS + ("aim",):
        if key in entry:
            mirrored[key] = _mirrored_vector(entry[key])
    for key in ("rotate_by", "rotate_to"):
        if key in entry:
            mirrored[key] = _mirrored_rotation(entry[key])
    if "twist" in entry:
        mirrored["twist"] = -entry["twist"]
    if "scale_to" in entry:
        mirrored["scale_to"] = dict(entry["scale_to"])
    return mirrored


def _mirrored_part(body_part):
    if body_part.startswith("left_"):
        return "right_" + body_part[len("left_"):]
    if body_part.startswith("right_"):
        return "left_" + body_part[len("right_"):]
    return body_part


# ----------------------------------------------------------------------
# Resolution


def _error(index, entry, reason, message, **extra):
    error: dict = dict(index=index, reason=reason, message=message)
    if isinstance(entry, dict) and isinstance(entry.get("bone"), str):
        error["bone"] = entry["bone"]
    error.update(extra)
    return error


def _requested_kinds(entry):
    kinds = []
    if any(key in entry for key in _POSITIONS):
        kinds.append("location")
    if any(key in entry for key in _ROTATIONS):
        kinds.append("rotation")
    if "scale_to" in entry:
        kinds.append("scale")
    return kinds


def _bone_refusal(rig, classification, in_charge, driven, *, index, entry):
    """Why the bone an entry names cannot be written, as an error record, or ``None``."""
    name = entry["bone"]
    if name not in rig.pose.bones:
        return _error(index, entry, "unknown_bone",
                      "'{:s}' has no bone called '{:s}'.".format(rig.name, name),
                      closest=difflib.get_close_matches(
                          name, [bone.name for bone in rig.pose.bones], n=3, cutoff=0.6))
    if classification["classified"]:
        refusal = pose_writing.charge_refusal(classification, in_charge, name)
        if refusal is not None:
            reason, message, instead = refusal
            return _error(index, entry, reason, message, write_instead=instead)
    blocked = sorted(set(_requested_kinds(entry)) & driven.get(name, set()))
    if blocked:
        return _error(index, entry, "driven_channel",
                      "A driver sets the {:s} of '{:s}', so a write would be put back on the "
                      "next evaluation.".format(" and ".join(blocked), name),
                      channels=blocked)
    return None


def _counterpart_refusal(rig, classification, index, entry, named):
    """``(counterpart, error)`` for an entry with ``symmetry``."""
    name = entry["bone"]
    counterpart = bpy.utils.flip_name(name)
    if counterpart == name or counterpart not in rig.pose.bones:
        return (None, _error(index, entry, "no_counterpart",
                             "'{:s}' has no mirrored counterpart on this rig, so symmetry cannot "
                             "apply.".format(name), counterpart=None))
    if counterpart in named:
        return (None, _error(index, entry, "counterpart_named",
                             "symmetry would also write '{:s}', which this call names itself. "
                             "Name one side with symmetry, or both without.".format(counterpart),
                             counterpart=counterpart))
    if classification["classified"]:
        mine = classification["controls"][name]
        theirs = classification["controls"].get(counterpart)
        if (theirs is None or theirs["role"] != mine["role"]
                or theirs["body_part"] != _mirrored_part(mine["body_part"])):
            return (None, _error(
                index, entry, "no_counterpart",
                "'{:s}' is not '{:s}''s mirror image on this rig (not a control of {:s} with "
                "role {:s}), so symmetry cannot apply.".format(
                    counterpart, name, _mirrored_part(mine["body_part"]), mine["role"]),
                counterpart=counterpart))
    return (counterpart, None)


def _resolve(rig, classification, in_charge, driven, bones):
    """``(plans, errors)``: one plan per bone to write, mirrored ones included, request order."""
    plans = []
    errors = []
    named = set()
    for entry in bones:
        if isinstance(entry, dict) and isinstance(entry.get("bone"), str):
            named.add(entry["bone"])
    seen = set()
    for index, entry in enumerate(bones):
        shape = _shape_error(entry)
        if shape is not None:
            errors.append(_error(index, entry, "invalid_entry", shape))
            continue
        if entry["bone"] in seen:
            errors.append(_error(index, entry, "duplicate_bone",
                                 "'{:s}' is named twice in this call.".format(entry["bone"])))
            continue
        seen.add(entry["bone"])
        refusal = _bone_refusal(rig, classification, in_charge, driven, index=index, entry=entry)
        if refusal is not None:
            errors.append(refusal)
            continue
        plans.append(dict(index=index, entry=entry, mirrored_from=None))
        if not entry.get("symmetry", False):
            continue
        counterpart, error = _counterpart_refusal(rig, classification, index, entry, named)
        if error is None:
            mirrored = _mirrored(entry, counterpart)
            error = _bone_refusal(rig, classification, in_charge, driven, index=index,
                                  entry=mirrored)
            if error is not None:
                error["mirrored_from"] = entry["bone"]
        if error is not None:
            errors.append(error)
            continue
        plans.append(dict(index=index, entry=mirrored, mirrored_from=entry["bone"]))
    return (plans, errors)


# ----------------------------------------------------------------------
# Targets, from the pose at the moment a bone is written


def _targets(frame, pose_bone, entry):
    """``(head, orientation, scale)`` in armature space for one entry; ``None`` for "unchanged".

    A relative change starts from the bone's own transform, before its
    constraints (``pose_writing.own_matrix``), and an absolute one is where the
    bone should end up; ``achieved`` then measures the evaluated result.
    """
    matrix = pose_writing.own_matrix(pose_bone)
    head = None
    if "move_by" in entry:
        head = matrix.to_translation() + frame.to_armature_vector(entry["move_by"])
    elif "move_to" in entry:
        head = frame.to_armature_point(entry["move_to"])
    rest = pose_bone.bone.matrix_local.to_quaternion()
    orientation = None
    if "rotate_by" in entry:
        orientation = frame.to_armature_rotation(entry["rotate_by"]) @ matrix.to_quaternion()
    elif "rotate_to" in entry:
        orientation = frame.to_armature_rotation(entry["rotate_to"]) @ rest
    elif "aim" in entry:
        direction = frame.to_armature_direction(entry["aim"])
        rest_direction = rest @ Vector((0.0, 1.0, 0.0))
        orientation = rest_direction.rotation_difference(direction) @ rest
        if entry.get("twist"):
            orientation = Quaternion(direction, math.radians(float(entry["twist"]))) @ orientation
    return (head, orientation, entry.get("scale_to"))


def _write_all(rig, frame, plans):
    """Write every plan parent first; ``(targets, errors)``, the errors from the after-checks."""
    by_bone = {plan["entry"]["bone"]: plan for plan in plans}
    targets = {}
    errors = []
    for name in pose_writing.parents_first(rig, list(by_bone)):
        plan = by_bone[name]
        pose_bone = rig.pose.bones[name]
        before = pose_writing.channels(pose_bone)
        head, orientation, scale = _targets(frame, pose_bone, plan["entry"])
        pose_writing.write(pose_bone, head, orientation, scale)
        targets[name] = (head, orientation, scale)
        violated = pose_writing.lock_violations(pose_bone, before)
        if not violated:
            # Within tolerance: rounding in what was sent, put back exactly.
            pose_writing.hold_locks(pose_bone, before)
            pose_reading.evaluated()
        if violated:
            connected = "location" in violated and pose_bone.bone.use_connect
            errors.append(_error(
                plan["index"], plan["entry"], "locked_channel",
                "Writing '{:s}' would change its locked {:s}{:s}.".format(
                    name, " and ".join(violated),
                    " (it is connected to its parent, so its head cannot move on its own)"
                    if connected else ""),
                channels=violated, mirrored_from=plan["mirrored_from"]))
    return (targets, errors)


# ----------------------------------------------------------------------
# The answer


def _labels(classification, name):
    control = classification["controls"].get(name) if classification["classified"] else None
    return (None, None) if control is None else (control["body_part"], control["role"])


def _change(frame, rig, classification, plan, *, before, targets, animated):
    name = plan["entry"]["bone"]
    pose_bone = rig.pose.bones[name]
    after = pose_reading.posed_entry(frame, pose_bone)
    body_part, role = _labels(classification, name)
    change: dict = dict(bone=name, body_part=body_part, role=role)
    if plan["mirrored_from"] is not None:
        change["mirrored_from"] = plan["mirrored_from"]
    change.update(head_before=before["head"], head_after=after["head"],
                  rotation_before=before["rotation"], rotation_after=after["rotation"])
    if before["scale"] is not None or after["scale"] is not None:
        change.update(scale_before=before["scale"], scale_after=after["scale"])
    arrived, deviation = pose_writing.achieved(frame, pose_bone, *targets[name])
    change["achieved"] = arrived
    if deviation is not None:
        change["deviation"] = deviation
    overwritten = sorted(set(_requested_kinds(plan["entry"])) & animated.get(name, set()))
    if overwritten:
        change["overwritten_on_frame_change"] = overwritten
    return change


def _message(rig, changes, consequence, shown):
    missed = [change["bone"] for change in changes if not change["achieved"]]
    parts = ["Wrote {:d} bone(s) of '{:s}'.".format(len(changes), rig.name)]
    if missed:
        parts.append(" {:d} did not end where asked ({:s}); see deviation.".format(
            len(missed), ", ".join(missed)))
    parts.append(pose_writing.limb_sentences(consequence))
    animated = [change["bone"] for change in changes if "overwritten_on_frame_change" in change]
    if animated:
        parts.append(" The rig's action animates {:s}, so the next frame change puts the keyed "
                     "values back.".format(", ".join(animated)))
    parts.append(pose_writing.rest_position_sentence(rig, shown))
    return "".join(parts)


def _refused(answer, errors):
    answer.update(
        changes=[], change_count=0, resolution_errors=errors,
        message="{:d} entr{:s} could not be written, so **nothing at all was applied**. Fix "
                "the entries in 'resolution_errors' and send the whole batch again.".format(
                    len(errors), "y" if len(errors) == 1 else "ies"))
    return with_performed(answer, False)


def set_pose_bones(params, resolution):  # pylint: disable=too-many-locals
    """Resolve every entry, write all of them parent first or none, and report each."""
    not_done = ", so nothing was changed"
    resolved = pose_controls.resolve_posing_subject(
        resolution.services, params["name"], None, not_done="nothing was changed")
    if resolved["blocked_by"] is None:
        resolved = pose_writing.edit_mode_refusal(resolved, not_done) or resolved
    if resolved["blocked_by"] is not None:
        _LOG.debug("set_pose_bones: refused %r", resolved["blocked_by"])
        answer = pose_writing.blocked_answer(resolved)
        answer.update(changes=[], change_count=0, resolution_errors=[])
        return with_performed(answer, False)

    rig = resolved["rig"]
    bones = list(params["bones"])
    with pose_writing.showing_pose(rig) as shown:
        frame = Frame(rig)
        classification = pose_controls.classify(
            resolution.module.__name__, rig, resolved["rig_identified_as"])
        answer = pose_writing.answer_base(resolved, frame, classification, shown)
        if not bones:
            answer.update(changes=[], change_count=0, resolution_errors=[],
                          message="'bones' named nothing, so nothing was changed. Call "
                                  "mpfb_get_pose_controls to see what can be posed.")
            return with_performed(answer, False)

        limbs_before = (pose_reading.limbs(frame, rig, classification["limbs"])
                        if classification["classified"] else {})
        in_charge = {part: limb["in_charge"] for part, limb in limbs_before.items() if limb}
        plans, errors = _resolve(rig, classification, in_charge,
                                 pose_writing.driven_kinds(rig), bones)
        if errors:
            return _refused(answer, errors)
        names = [plan["entry"]["bone"] for plan in plans]
        saved = pose_writing.snapshot(rig, names)
        before = {name: pose_reading.posed_entry(frame, rig.pose.bones[name]) for name in names}
        landmarks_before = (pose_reading.landmarks(frame, rig, classification["landmarks"])
                            if classification["classified"] else None)
        try:
            targets, errors = _write_all(rig, frame, plans)
        except Exception:
            pose_writing.restore(rig, saved)
            raise
        if errors:
            pose_writing.restore(rig, saved)
            return _refused(answer, errors)

        animated = pose_writing.animated_kinds(rig)
        changes = [_change(frame, rig, classification, plan,
                           before=before[plan["entry"]["bone"]], targets=targets,
                           animated=animated) for plan in plans]
        consequence = pose_writing.consequences(frame, rig, classification, landmarks_before,
                                                 limbs_before)
    answer.update(changes=changes, change_count=len(changes), resolution_errors=[],
                  achieved_measure=pose_writing.ACHIEVED_MEASURE)
    answer.update(consequence)
    answer["message"] = _message(rig, changes, consequence, shown)
    _LOG.debug("set_pose_bones: %d change(s) to %r", len(changes), rig.name)
    return with_performed(answer, changes)
