"""
``reset_pose``: put a character's controls back at rest, by body part, and hand back the way back.

The third pose writer ([FR 042](../../../feature-requests/done/042-posing-bones-switches-and-reset/README.md)),
and the first tool built for "undo a mistake". The karate session had no way
back to rest other than remembering what it had moved, and Blender's undo stack
does not record a bridge command's writes, so this is what undoes them.

**Every control in the chosen body parts goes to an identity ``matrix_basis``**,
MPFB's helper bones included; bones that are not controls are not touched, and
any of them still off rest afterwards are named (``left_off_rest``), since on a
generated rig that means something other than this package moved them. A
channel a driver sets is not counted there: Rigify's finger drivers move
``MCH-`` bones as a fist closes, and put them back by themselves.

**``body_parts`` defaults to every part, the face included**, which is unlike
the readers' default on purpose: they leave the face out to keep an answer
small, and a reset that silently left the face posed would not be a reset. An
unclassified rig has no body parts, so ``body_parts`` must be omitted there and
every pose bone is reset.

**``include_switches``** (default false) also returns each switch of the
chosen parts to its default, read live off the property (``id_properties_ui(...)`` ``default``)
rather than from a table, raw and before the transforms, so that snapping is
moot. FR 042 called it ``switches``; it is ``include_switches`` because
``mpfb_set_pose_switches`` takes ``switches`` as a list, and one argument name
carries one JSON type across the package.

**The answer is a way back**, per
[a tool that destroys state it did not create](../../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list):
``restore_with`` holds the ``mpfb_set_pose_switches`` arguments (``raw: true``,
when ``include_switches`` was set) and the ``mpfb_set_pose_bones`` arguments
(``move_to``, ``rotate_to``, ``scale_to``) that put back what was reset, to be
sent in that order - as ``mpfb_save_expression``'s ``apply_with`` is the call
that makes a face durable. It is never capped, because a capped restore would
not restore anything. Each entry is read before the bone's own constraints
([`pose_writing.restore_entry`](../shared/pose_writing.py)) and keeps more
digits than a read-back, so the pose comes back exactly rather than to the
millimetre.

**A reset bone ``mpfb_set_pose_bones`` would refuse is named rather than put in
``restore_with``** (``not_restorable``), because one refused entry fails that
tool's whole batch and the restore would restore nothing. That is a bone in the
chain ``IK_FK`` had handed away, an FK bone one of MPFB's helpers drives, and a
bone whose off-rest channel is locked or driven. None of those had a visible
effect on the body when the reset ran - which chain is in charge is the same
before the reset and after the restore - so the visible pose comes back whole.

A character already at rest gets ``performed: false``, an empty ``restore_with``
and no sentence about it. The verb beside ``performed`` is ``reset``, a bool
rather than the list ``bones_reset``, because a reset of switches alone resets
no bone and is still a reset. Nothing is borrowed: no mode, selection or active
object, and no operator.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "reset_pose",
)

from ..log import get_logger
from ..shared import pose_controls
from ..shared import pose_reading
from ..shared import pose_writing
from ..shared.character_frame import Frame
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.resetpose")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("body_parts", TYPE_ARRAY, default=None, nullable=True,
          description="Which body parts to reset, from: {:s}. Omit for every part, the face "
                      "included.".format(", ".join(pose_controls.BODY_PARTS))),
    Param("include_switches", TYPE_BOOLEAN, default=False,
          description="Also return the chosen parts' switches to their defaults."),
)

SUMMARY = ("Put a character's controls back at rest by body part, optionally its switches too, "
           "and answer with the calls that restore what was reset.")


def _switch_default(rig, switch):
    try:
        default = rig.pose.bones[switch["bone"]].id_properties_ui(
            switch["switch"]).as_dict().get("default")
    except (TypeError, KeyError):
        default = None
    if default is None:
        return None
    if switch["type"] == "bool":
        return bool(default)
    if switch["type"] in ("parent", "int"):
        return int(default)
    return float(default)


def _switch_resets(rig, classification, parts):
    """Each switch of the chosen parts that is off its default: ``(switch, value, default)``."""
    resets = []
    for switch in classification["switches"] or ():
        if switch["body_part"] not in parts:
            continue
        default = _switch_default(rig, switch)
        value = pose_writing.switch_value(rig, switch)
        if default is not None and value != default:
            resets.append((switch, value, default))
    return resets


def _bones_to_reset(rig, classification, parts):
    if not classification["classified"]:
        return [pose_bone.name for pose_bone in rig.pose.bones]
    return [name for name, control in classification["controls"].items()
            if control["body_part"] in parts]


def _not_restorable(pose_bone, classification, in_charge, driven):
    """Why ``mpfb_set_pose_bones`` would refuse to restore this bone, or ``None``."""
    if classification["classified"]:
        refusal = pose_writing.charge_refusal(classification, in_charge, pose_bone.name)
        if refusal is not None:
            return refusal[0]
    now = pose_writing.channels(pose_bone)
    rest = pose_writing.REST_CHANNELS
    if set(pose_writing.changed_kinds(pose_bone, rest, now)) & driven.get(pose_bone.name, set()):
        return "driven_channel"
    if pose_writing.lock_violations(pose_bone, rest, now):
        return "locked_channel"
    return None


def _left_off_rest(rig, classification, driven):
    """Bones that are not controls and are off rest in a channel no driver sets."""
    if not classification["classified"]:
        return []
    controls = classification["controls"]
    left = []
    for pose_bone in rig.pose.bones:
        if pose_bone.name in controls or not pose_reading.off_rest(pose_bone):
            continue
        off = pose_writing.changed_kinds(pose_bone, pose_writing.REST_CHANNELS,
                                         pose_writing.channels(pose_bone))
        if set(off) - driven.get(pose_bone.name, set()):
            left.append(pose_bone.name)
    return left


def _restore_with(rig, entries, switch_resets):
    restore: dict = {}
    if switch_resets:
        restore["mpfb_set_pose_switches"] = {
            "name": rig.name,
            "switches": [{"body_part": switch["body_part"], "switch": switch["switch"],
                          "value": value, "raw": True}
                         for switch, value, _default in switch_resets]}
    if entries:
        restore["mpfb_set_pose_bones"] = {"name": rig.name, "bones": entries}
    return restore


def _message(rig, reset, switch_resets, *, not_restorable, left_off_rest, consequence, shown):
    parts = ["Reset {:d} control(s) of '{:s}' to rest".format(len(reset), rig.name)]
    if switch_resets:
        parts.append(" and {:d} switch(es) to their defaults".format(len(switch_resets)))
    parts.append(". restore_with puts it back: send mpfb_set_pose_switches' arguments first, "
                 "then mpfb_set_pose_bones'." if switch_resets else
                 ". restore_with is the mpfb_set_pose_bones call that puts it back.")
    if not_restorable:
        parts.append(" {:d} reset bone(s) had no visible effect and are not in restore_with "
                     "(not_restorable).".format(len(not_restorable)))
    if left_off_rest:
        parts.append(" {:d} bone(s) that are not controls are still off rest "
                     "(left_off_rest): something other than the posing tools moved "
                     "them.".format(len(left_off_rest)))
    parts.append(pose_writing.limb_sentences(consequence))
    parts.append(pose_writing.rest_position_sentence(rig, shown))
    return "".join(parts)


def _unclassified_refusal(resolved):
    refused: dict = dict(resolved)
    refused.update(
        blocked_by="rig_not_classified", extra={},
        message="'{:s}' is a {!s} rig, which is not classified, so it has no body parts to "
                "choose from and nothing was changed. Omit body_parts to reset every bone.".format(
                    resolved["rig"].name, resolved["rig_identified_as"]))
    return refused


def reset_pose(params, resolution):  # pylint: disable=too-many-locals
    """Reset the chosen parts to rest, switches first when asked, and answer with the way back."""
    not_done = ", so nothing was changed"
    resolved = pose_controls.resolve_posing_subject(
        resolution.services, params["name"], params["body_parts"],
        not_done="nothing was changed")
    if resolved["blocked_by"] is None:
        resolved = pose_writing.edit_mode_refusal(resolved, not_done) or resolved
    classification = None
    if resolved["blocked_by"] is None:
        classification = pose_controls.classify(
            resolution.module.__name__, resolved["rig"], resolved["rig_identified_as"])
        if not classification["classified"] and params["body_parts"] is not None:
            resolved = _unclassified_refusal(resolved)
    if resolved["blocked_by"] is not None:
        _LOG.debug("reset_pose: refused %r", resolved["blocked_by"])
        answer = pose_writing.blocked_answer(resolved)
        answer.update(reset=False, bones_reset=[], restore_with={})
        return with_performed(answer, False)

    rig = resolved["rig"]
    assert classification is not None, "set whenever the subject was not refused"
    parts = (pose_controls.BODY_PARTS if params["body_parts"] is None
             else pose_controls.requested_body_parts(params["body_parts"]))
    with pose_writing.showing_pose(rig) as shown:
        frame = Frame(rig)
        answer = pose_writing.answer_base(resolved, frame, classification, shown)
        answer["requested_body_parts"] = list(parts) if classification["classified"] else None
        driven = pose_writing.driven_kinds(rig)
        switch_resets = (_switch_resets(rig, classification, parts)
                         if params["include_switches"] and classification["classified"] else [])
        limbs_before = (pose_reading.limbs(frame, rig, classification["limbs"])
                        if classification["classified"] else {})
        in_charge = {part: limb["in_charge"] for part, limb in limbs_before.items() if limb}
        landmarks_before = (pose_reading.landmarks(frame, rig, classification["landmarks"])
                            if classification["classified"] else None)

        names = pose_writing.parents_first(rig, _bones_to_reset(rig, classification, parts))
        posed = [name for name in names if pose_reading.off_rest(rig.pose.bones[name])]
        entries = []
        not_restorable = []
        for name in posed:
            pose_bone = rig.pose.bones[name]
            reason = _not_restorable(pose_bone, classification, in_charge, driven)
            if reason is not None:
                not_restorable.append({"bone": name, "reason": reason})
                continue
            entry = pose_writing.restore_entry(frame, pose_bone)
            if entry is not None:
                entries.append(entry)

        if not posed and not switch_resets:
            answer.update(reset=False, bones_reset=[], reset_count=0, switches_reset=[], restore_with={},
                          not_restorable=[], left_off_rest=_left_off_rest(rig, classification,
                                                                         driven),
                          message="'{:s}' is already at rest.".format(rig.name))
            return with_performed(answer, False)

        saved = pose_writing.snapshot(rig, posed)
        try:
            for switch, _value, default in switch_resets:
                pose_writing.write_switch(rig, switch["bone"], switch["switch"], default)
            for name in posed:
                pose_writing.to_rest(rig.pose.bones[name])
            pose_reading.evaluated()
        except Exception:
            for switch, value, _default in switch_resets:
                pose_writing.write_switch(rig, switch["bone"], switch["switch"], value)
            pose_writing.restore(rig, saved)
            raise
        consequence = pose_writing.consequences(frame, rig, classification, landmarks_before,
                                                limbs_before)
        left = _left_off_rest(rig, classification, driven)

    answer.update(
        reset=True,
        bones_reset=posed,
        reset_count=len(posed),
        switches_reset=[{"body_part": switch["body_part"], "switch": switch["switch"],
                         "bone": switch["bone"], "previous_value": value, "new_value": default}
                        for switch, value, default in switch_resets],
        restore_with=_restore_with(rig, entries, switch_resets),
        not_restorable=not_restorable,
        left_off_rest=left,
    )
    answer.update(consequence)
    answer["message"] = _message(rig, posed, switch_resets, not_restorable=not_restorable,
                                 left_off_rest=left, consequence=consequence, shown=shown)
    _LOG.debug("reset_pose: %d bone(s), %d switch(es) on %r", len(posed), len(switch_resets),
               rig.name)
    return with_performed(answer, True)
