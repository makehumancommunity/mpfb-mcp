"""
``set_rigify_hand_shape``: give a hand of a generated Rigify rig a named shape, or curl and spread its fingers.

The writer half of [FR 047](../../../feature-requests/done/047-rigify-hand-shapes/README.md).
Before it, a fist was ``scale_to`` on every finger master, and the caller had
to know that a Rigify finger curls when its master is scaled on Y; a soft grip
curled, uncurled and curled again cost four calls of fourteen entries. Now it
is one entry per hand, in the vocabulary ``get_rigify_hand_shape`` reads back.

**An entry is a hand, a shape and its exceptions.** ``shape`` sets all five
fingers from the table (:data:`rigify_hands.SHAPES`); ``fingers`` is applied
after it, finger by finger and amount by amount, so "a fist with the index
straight" is one entry. Without ``shape`` only the fingers named are written,
and within a finger only the amounts named: **leaving something out means
"leave it alone", never "reset it"**, the rule ``mpfb_set_macro_details``
follows. ``symmetry`` copies the entry to the other hand without mirroring,
because a curl and a spread mean the same on both sides.

**A written finger is the whole finger.** Its segment controls are put at rest,
because a rotation left on a segment adds to the curl and would make the
answer's ``curl`` untrue; the ones that were posed are reported
(``segments_reset``) and are in ``restore_with``. A finger that is not written
is not touched, segments included.

**Only what is in charge is written, and all or nothing**, FR 042's rules
through ``pose_writing``: a finger whose IK control is in charge, a driven
channel and a name the rig does not have are refused before anything is
written; a locked channel is found after writing, and then the snapshot is put
back exactly. A finger's master is written through its own channels rather
than ``pose_bone.matrix``, since an amount *is* a local rotation and a scale
(:func:`rigify_hands.write_finger`). Nothing is borrowed: no mode, selection or
active object, and no operator.

**Requested beside achieved**: every written finger is measured on the
deforming bones afterwards and ``achieved`` is false, with ``deviation`` in
degrees, when a joint is more than half a degree from what the amounts ask.

**``restore_with`` is the way back**, per
[a tool that destroys state it did not create](../../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list):
the ``mpfb_set_rigify_hand_shape`` entries that put back each changed finger's
curl and spread, then the ``mpfb_set_pose_bones`` entries for the segments it
reset and for any master whose channels were not a curl and a spread at all (a
hook, a twist), to be sent in that order. A shape overwrites a hand someone may
have posed by hand, so the previous state is owed even though nothing is reset
to rest unless the caller asked for ``open``.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "set_rigify_hand_shape",
)

from ..log import get_logger
from ..shared import pose_controls
from ..shared import pose_reading
from ..shared import pose_writing
from ..shared import rigify_hands
from ..shared.character_frame import Frame
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import is_number
from ..validation import TYPE_ARRAY
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setrigifyhandshape")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("hands", TYPE_ARRAY, default=(),
          description="One object per hand: 'body_part' ({:s}), and 'shape' ({:s}) or "
                      "'fingers' (finger -> 'curl' and/or 'spread') or both, and "
                      "'symmetry'.".format(", ".join(rigify_hands.HANDS),
                                           ", ".join(rigify_hands.SHAPES))),
)

SUMMARY = ("Give a hand of a generated Rigify rig a named shape, or curl and spread any finger "
           "by an amount, as one all-or-nothing batch.")

_KEYS = ("body_part", "shape", "fingers", "symmetry")
_AMOUNTS = {"curl": rigify_hands.CURL_RANGE, "spread": rigify_hands.SPREAD_RANGE}

# How many digits a restore_with amount keeps: an amount rounded to a reading's
# three would put a finger back only to a tenth of a degree.
_RESTORE_DIGITS = 7


# ----------------------------------------------------------------------
# Shape. mpfb-mcp checks all of this too; other clients may not.


def _amounts_error(finger, amounts):
    if not isinstance(amounts, dict) or not amounts:
        return "fingers.{!s} must be an object with 'curl', 'spread' or both".format(finger)
    unknown = sorted(str(key) for key in amounts if key not in _AMOUNTS)
    if unknown:
        return "fingers.{!s} has unknown key(s) {:s}; its keys are curl, spread".format(
            finger, ", ".join(unknown))
    for key, value in amounts.items():
        low, high = _AMOUNTS[key]
        if not is_number(value) or not low <= value <= high:
            return "fingers.{!s}.{:s} must be a number from {:g} to {:g}".format(
                finger, key, low, high)
    return None


def _shape_error(entry):  # pylint: disable=too-many-return-statements
    """Why an entry is malformed, or ``None``."""
    if not isinstance(entry, dict):
        return "an entry must be an object"
    unknown = sorted(str(key) for key in entry if key not in _KEYS)
    if unknown:
        return "unknown key(s) {:s}; known keys are {:s}".format(
            ", ".join(unknown), ", ".join(_KEYS))
    if not isinstance(entry.get("body_part"), str) or not entry["body_part"].strip():
        return "'body_part' must be a non-empty string"
    if "shape" not in entry and "fingers" not in entry:
        return "the entry changes nothing; give 'shape', 'fingers' or both"
    if "shape" in entry and (not isinstance(entry["shape"], str) or not entry["shape"].strip()):
        return "'shape' must be a non-empty string"
    if "fingers" in entry:
        fingers = entry["fingers"]
        if not isinstance(fingers, dict) or not fingers:
            return "'fingers' must be an object keyed by finger name"
        for finger, amounts in fingers.items():
            error = _amounts_error(finger, amounts)
            if error:
                return error
    if "symmetry" in entry and not isinstance(entry["symmetry"], bool):
        return "'symmetry' must be a bool"
    return None


# ----------------------------------------------------------------------
# Resolution


def _error(index, entry, reason, message, **extra):
    error: dict = dict(index=index, reason=reason, message=message)
    if isinstance(entry, dict) and isinstance(entry.get("body_part"), str):
        error["body_part"] = entry["body_part"]
    error.update(extra)
    return error


def _other_hand(hand):
    return rigify_hands.HANDS[1 - rigify_hands.HANDS.index(hand)]


def _vocabulary_error(index, entry):
    """The entry names a hand, a shape or a finger this package does not have, or ``None``."""
    if entry["body_part"] not in rigify_hands.HANDS:
        return _error(index, entry, "unknown_body_part",
                      "'{:s}' is not a hand. The hands are: {:s}.".format(
                          entry["body_part"], ", ".join(rigify_hands.HANDS)),
                      known_body_parts=list(rigify_hands.HANDS))
    if "shape" in entry and entry["shape"] not in rigify_hands.SHAPES:
        return _error(index, entry, "unknown_shape",
                      "'{:s}' is not a shape. The shapes are: {:s}.".format(
                          entry["shape"], ", ".join(rigify_hands.SHAPES)),
                      known_shapes=list(rigify_hands.SHAPES))
    unknown = [finger for finger in entry.get("fingers", {}) if finger not in rigify_hands.FINGERS]
    if unknown:
        return _error(index, entry, "unknown_finger",
                      "{:s} {:s} not a finger. The fingers are: {:s}.".format(
                          ", ".join(repr(name) for name in unknown),
                          "is" if len(unknown) == 1 else "are", ", ".join(rigify_hands.FINGERS)),
                      known_fingers=list(rigify_hands.FINGERS))
    return None


def _requested(found, entry, before):
    """``(amounts, not_on_rig, missing)``: what each finger of one hand gets, filled in.

    ``missing`` lists the fingers ``fingers`` names that the hand does not have,
    and any finger, named or in a shape, that it has but cannot be read; a
    shape's fingers the hand does not have at all are ``not_on_rig``, which is
    not a mistake. An amount left out is the finger's current one, as read.
    """
    fingers = found["fingers"]
    asked = {}
    not_on_rig = []
    missing = []
    if "shape" in entry:
        for name, amounts in rigify_hands.shape_amounts(entry["shape"]).items():
            if name in fingers:
                asked[name] = amounts
            elif name in found["errors"]:
                missing.append(name)
            else:
                not_on_rig.append(name)
    for name, amounts in entry.get("fingers", {}).items():
        if name not in fingers:
            if name not in missing:
                missing.append(name)
            continue
        asked.setdefault(name, {}).update(amounts)
    complete = {}
    for name in rigify_hands.FINGERS:
        if name not in asked:
            continue
        reading = before[name]
        complete[name] = {"curl": float(asked[name].get("curl", reading["curl"])),
                          "spread": float(asked[name].get("spread", reading["spread"])),
                          # A spread alone leaves the later joints exactly as they are,
                          # when the master's channels are a curl to leave alone.
                          "keep_scale": "curl" not in asked[name]
                                        and not reading["channel_reasons"]}
    return (complete, not_on_rig, missing)


def _finger_refusal(rig, finger, driven, index, entry):
    """Why one finger cannot be written, as an error record, or ``None``."""
    if finger.ik_control is not None:
        value = float(rig.pose.bones[finger.ik_control]["FK_IK"])
        if value > 0.0:
            return _error(index, entry, "finger_ik_in_charge",
                          "{:s}'s IK control '{:s}' has FK_IK at {:g}, so it moves the finger and "
                          "a curl would not show. Set FK_IK to 0 first.".format(
                              finger.name, finger.ik_control, value),
                          finger=finger.name)
    blocked = sorted(driven.get(finger.master, set()) & {"location", "rotation", "scale"})
    if blocked:
        return _error(index, entry, "driven_channel",
                      "A driver sets the {:s} of '{:s}', so a write would be put back on the next "
                      "evaluation.".format(" and ".join(blocked), finger.master),
                      finger=finger.name, bone=finger.master, channels=blocked)
    for segment in finger.segments:
        posed = pose_writing.changed_kinds(rig.pose.bones[segment], pose_writing.REST_CHANNELS)
        blocked = sorted(driven.get(segment, set()) & set(posed))
        if blocked:
            return _error(index, entry, "driven_channel",
                          "A driver sets the {:s} of the segment '{:s}', which writing {:s} "
                          "would put at rest.".format(" and ".join(blocked), segment, finger.name),
                          finger=finger.name, bone=segment, channels=blocked)
    return None


def _resolve(rig, hands, before, entries):
    """``(plans, errors)``: one plan per hand to write, mirrored ones after their source."""
    plans = []
    errors = []
    named = [entry["body_part"] for entry in entries
             if isinstance(entry, dict) and isinstance(entry.get("body_part"), str)]
    driven = pose_writing.driven_kinds(rig)
    seen = set()
    for index, entry in enumerate(entries):
        shape = _shape_error(entry)
        if shape is not None:
            errors.append(_error(index, entry, "invalid_entry", shape))
            continue
        error = _vocabulary_error(index, entry)
        if error is not None:
            errors.append(error)
            continue
        hand = entry["body_part"]
        if hand in seen:
            errors.append(_error(index, entry, "duplicate_body_part",
                                 "'{:s}' is named twice in this call.".format(hand)))
            continue
        seen.add(hand)
        targets = [(hand, None)]
        if entry.get("symmetry", False):
            other = _other_hand(hand)
            if other in named:
                errors.append(_error(index, entry, "counterpart_named",
                                     "symmetry would also write '{:s}', which this call names "
                                     "itself. Name one hand with symmetry, or both "
                                     "without.".format(other), counterpart=other))
                continue
            targets.append((other, hand))
        for target, mirrored_from in targets:
            found = hands[target]
            amounts, not_on_rig, missing = _requested(found, entry, before[target])
            extra = {} if mirrored_from is None else {"mirrored_from": mirrored_from}
            if missing:
                broken = [name for name in missing if name in found["errors"]]
                errors.append(_error(
                    index, entry, "finger_not_as_generated" if broken else "finger_not_on_rig",
                    "{:s} on '{:s}': {:s}.".format(
                        target, rig.name, "; ".join(found["errors"].get(
                            name, "{:s} is not on this hand".format(name)) for name in missing)),
                    fingers=missing, fingers_found=list(found["fingers"]), **extra))
                continue
            refusals = [_finger_refusal(rig, found["fingers"][name], driven, index, entry)
                        for name in amounts]
            refusals = [refusal for refusal in refusals if refusal is not None]
            if refusals:
                for refusal in refusals:
                    refusal.update(extra)
                errors.extend(refusals)
                continue
            plans.append(dict(index=index, entry=entry, hand=target, mirrored_from=mirrored_from,
                              amounts=amounts, not_on_rig=not_on_rig))
    return (plans, errors)


# ----------------------------------------------------------------------
# The write, and the way back


def _bones_of(finger):
    return [finger.master] + list(finger.segments)


def _restore_with(rig, plans, before, changed_fingers):
    """The two calls that put back every finger this call changed, in the order to send them."""
    shape_entries = []
    bone_entries = []
    for plan in plans:
        fingers = {}
        for name in plan["amounts"]:
            if (plan["hand"], name) not in changed_fingers:
                continue
            reading = before[plan["hand"]][name]
            if not reading["channel_reasons"]:
                fingers[name] = {
                    "curl": round(reading["channel_curl"], _RESTORE_DIGITS) + 0.0,
                    "spread": round(reading["channel_spread"], _RESTORE_DIGITS) + 0.0}
            else:
                bone_entries.append(plan["restore_master"][name])
            bone_entries.extend(plan["restore_segments"][name])
        if fingers:
            shape_entries.append({"body_part": plan["hand"], "fingers": fingers})
    restore: dict = {}
    if shape_entries:
        restore["mpfb_set_rigify_hand_shape"] = {"name": rig.name, "hands": shape_entries}
    if bone_entries:
        restore["mpfb_set_pose_bones"] = {"name": rig.name, "bones": bone_entries}
    return restore


def _master_restore(frame, rig, finger):
    """The ``mpfb_set_pose_bones`` entry for a master whose channels are no curl and spread."""
    pose_bone = rig.pose.bones[finger.master]
    entry = pose_writing.restore_entry(frame, pose_bone) or {"bone": finger.master}
    entry.setdefault("rotate_to", {"axis": None, "degrees": 0.0})
    entry["scale_to"] = {"y": round(float(pose_bone.scale[1]), 6)}
    return entry


def _plan_undo(frame, rig, hands, plans):
    """Read, before writing, what each planned finger's restore needs from its bones."""
    for plan in plans:
        plan["restore_master"] = {}
        plan["restore_segments"] = {}
        plan["segments_posed"] = {}
        for name in plan["amounts"]:
            finger = hands[plan["hand"]]["fingers"][name]
            plan["restore_master"][name] = _master_restore(frame, rig, finger)
            posed = [segment for segment in finger.segments
                     if pose_reading.off_rest(rig.pose.bones[segment])]
            plan["segments_posed"][name] = [
                dict(finger=name, **pose_reading.posed_entry(frame, rig.pose.bones[segment]))
                for segment in posed]
            plan["restore_segments"][name] = [
                entry for entry in (pose_writing.restore_entry(frame, rig.pose.bones[segment])
                                    for segment in posed) if entry is not None]


def _write_all(rig, hands, plans):
    """Write every planned finger; the lock errors found after writing, as error records."""
    errors = []
    for plan in plans:
        for name, amounts in plan["amounts"].items():
            finger = hands[plan["hand"]]["fingers"][name]
            before = {bone: pose_writing.channels(rig.pose.bones[bone])
                      for bone in _bones_of(finger)}
            rigify_hands.write_finger(rig, finger, amounts["curl"], amounts["spread"],
                                      keep_scale=amounts["keep_scale"])
            for bone, channels in before.items():
                pose_bone = rig.pose.bones[bone]
                violated = pose_writing.lock_violations(pose_bone, channels)
                if violated:
                    errors.append(_error(
                        plan["index"], plan["entry"], "locked_channel",
                        "Writing {:s} would change the locked {:s} of '{:s}'.".format(
                            name, " and ".join(violated), bone),
                        finger=name, bone=bone, channels=violated,
                        mirrored_from=plan["mirrored_from"]))
                else:
                    pose_writing.hold_locks(pose_bone, channels)
    pose_reading.evaluated()
    return errors


# ----------------------------------------------------------------------
# The answer


def _achieved(finger, amounts, reading):
    expected, spread = rigify_hands.expected_degrees(finger, amounts["curl"], amounts["spread"])
    worst = max([abs(e - m) for e, m in zip(expected, reading["joint_degrees"])]
                + [abs(spread - reading["spread_degrees"])])
    if worst <= rigify_hands.DEGREES_TOLERANCE:
        return (True, None)
    return (False, {"degrees": round(worst, 1)})


def _hand_answer(rig, hands, plan, before_entry, after, after_entry, *, saved, animated):
    found = hands[plan["hand"]]
    fingers_after = after_entry["fingers"]
    for name, amounts in plan["amounts"].items():
        arrived, deviation = _achieved(found["fingers"][name], amounts, after[name])
        fingers_after[name]["achieved"] = arrived
        if deviation is not None:
            fingers_after[name]["deviation"] = deviation
    written_bones = [bone for name in plan["amounts"] for bone in _bones_of(found["fingers"][name])]
    overwritten = sorted(bone for bone in written_bones
                         if animated.get(bone, set()) & set(pose_writing.changed_kinds(
                             rig.pose.bones[bone], saved[bone])))
    answer: dict = dict(body_part=plan["hand"], shape=plan["entry"].get("shape"))
    if plan["mirrored_from"] is not None:
        answer["mirrored_from"] = plan["mirrored_from"]
    answer.update(
        fingers_written=list(plan["amounts"]),
        fingers_not_on_rig=plan["not_on_rig"],
        fingers_before=before_entry["fingers"],
        fingers_after=fingers_after,
        matches_shape_before=before_entry["matches_shape"],
        matches_shape_after=after_entry["matches_shape"],
        segments_reset=[segment for name in plan["amounts"]
                        for segment in plan["segments_posed"][name]],
        palm_off_rest=after_entry["palm_off_rest"],
        settings_off_default=after_entry["settings_off_default"],
    )
    if overwritten:
        answer["overwritten_on_frame_change"] = overwritten
    return answer


def _message(rig, answers, changed, restore, shown):
    if not changed:
        return ("Nothing changed: every finger named was already where it was asked to "
                "be.{:s}".format(pose_writing.rest_position_sentence(rig, shown)))
    parts = []
    for hand in answers:
        shape = hand["matches_shape_after"]
        parts.append("{:s}: {:d} finger(s) written{:s}".format(
            hand["body_part"], len(hand["fingers_written"]),
            ", now '{:s}'".format(shape) if shape else ""))
    sentence = "Wrote '{:s}' - {:s}.".format(rig.name, "; ".join(parts))
    missed = ["{:s} {:s}".format(hand["body_part"], name) for hand in answers
              for name, finger in hand["fingers_after"].items() if finger.get("achieved") is False]
    if missed:
        sentence += " {:s} did not end where asked; see deviation.".format(", ".join(missed))
    reset = sum(len(hand["segments_reset"]) for hand in answers)
    if reset:
        sentence += " {:d} posed segment control(s) were put at rest (segments_reset).".format(reset)
    if "mpfb_set_pose_bones" in restore:
        sentence += (" restore_with puts it back: send mpfb_set_rigify_hand_shape's arguments "
                     "first, then mpfb_set_pose_bones'." if "mpfb_set_rigify_hand_shape" in restore
                     else " restore_with is the mpfb_set_pose_bones call that puts it back.")
    else:
        sentence += " restore_with is the call that puts it back."
    return sentence + pose_writing.rest_position_sentence(rig, shown)


def _refused(answer, errors):
    answer.update(
        hands=[], changed=False, resolution_errors=errors, restore_with={},
        message="{:d} entr{:s} could not be written, so **nothing at all was applied**. Fix "
                "the entries in 'resolution_errors' and send the whole batch again.".format(
                    len(errors), "y" if len(errors) == 1 else "ies"))
    return with_performed(answer, False)


def _read(frame, rig, hands, hand):
    return {name: rigify_hands.read_finger(frame, rig, finger)
            for name, finger in hands[hand]["fingers"].items()}


def set_rigify_hand_shape(params, resolution):  # pylint: disable=too-many-locals
    """Resolve every entry, write every finger or none, and report each hand."""
    not_done = ", so nothing was changed"
    resolved = pose_controls.resolve_posing_subject(
        resolution.services, params["name"], None, not_done="nothing was changed")
    if resolved["blocked_by"] is None:
        resolved = (rigify_hands.refusal(resolved, None, "hands", not_done)
                    or pose_writing.edit_mode_refusal(resolved, not_done) or resolved)
    if resolved["blocked_by"] is not None:
        _LOG.debug("set_rigify_hand_shape: refused %r", resolved["blocked_by"])
        answer = pose_writing.blocked_answer(resolved)
        answer.update(hands=[], changed=False, resolution_errors=[], restore_with={})
        return with_performed(answer, False)

    rig = resolved["rig"]
    entries = list(params["hands"])
    with pose_writing.showing_pose(rig) as shown:
        frame = Frame(rig)
        classification = pose_controls.classify(
            resolution.module.__name__, rig, resolved["rig_identified_as"])
        answer = pose_writing.answer_base(resolved, frame, classification, shown)
        if not entries:
            answer.update(hands=[], changed=False, resolution_errors=[], restore_with={},
                          message="'hands' named nothing, so nothing was changed. Call "
                                  "mpfb_get_rigify_hand_shape to see the hands and the shapes.")
            return with_performed(answer, False)
        hands = rigify_hands.find_hands(rig, classification)
        before = {hand: _read(frame, rig, hands, hand) for hand in rigify_hands.HANDS}
        plans, errors = _resolve(rig, hands, before, entries)
        if errors:
            return _refused(answer, errors)

        before_entries = {plan["hand"]: rigify_hands.hand_entry(rig, hands[plan["hand"]],
                                                                before[plan["hand"]])
                          for plan in plans}
        _plan_undo(frame, rig, hands, plans)
        bones = [bone for plan in plans for name in plan["amounts"]
                 for bone in _bones_of(hands[plan["hand"]]["fingers"][name])]
        saved = pose_writing.snapshot(rig, bones)
        try:
            errors = _write_all(rig, hands, plans)
        except Exception:
            pose_writing.restore(rig, saved)
            raise
        if errors:
            pose_writing.restore(rig, saved)
            return _refused(answer, errors)

        animated = pose_writing.animated_kinds(rig)
        changed_fingers = set()
        for plan in plans:
            for name in plan["amounts"]:
                finger = hands[plan["hand"]]["fingers"][name]
                if any(pose_writing.changed_kinds(rig.pose.bones[bone], saved[bone])
                       for bone in _bones_of(finger)):
                    changed_fingers.add((plan["hand"], name))
        answers = []
        for plan in plans:
            after = _read(frame, rig, hands, plan["hand"])
            answers.append(_hand_answer(
                rig, hands, plan, before_entries[plan["hand"]], after,
                rigify_hands.hand_entry(rig, hands[plan["hand"]], after),
                saved=saved, animated=animated))
        restore = _restore_with(rig, plans, before, changed_fingers)
    changed = bool(changed_fingers)
    answer.update(hands=answers, changed=changed, resolution_errors=[], restore_with=restore,
                  amounts_measure=rigify_hands.AMOUNTS_MEASURE,
                  message=_message(rig, answers, changed, restore, shown))
    _LOG.debug("set_rigify_hand_shape: %d finger(s) changed on %r", len(changed_fingers), rig.name)
    return with_performed(answer, changed)
