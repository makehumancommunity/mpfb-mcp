"""
``get_pose``: what a character's pose is now - what is off rest, where the body is, and
whether a limb is stretched or cannot reach.

The read-back half of [FR 041](../../../feature-requests/done/041-pose-controls-and-read-back/README.md),
meant to be called after every pose change, **instead of a screenshot**. The
session FR 041 came from posed a karate stance through ``execute_blender_code``
and checked each change by looking, and found the arms stretching and the fists
left in the air only that way. Each of those is now a field here.

**Four readings, each from a shared module the writing tools will also use**
([FR 042](../../../feature-requests/042-posing-bones-switches-and-reset/README.md)):

- ``posed``: every control off rest, by MPFB's own threshold **plus scale**,
  which ``RigService.get_pose_as_dict()`` does not record. A Rigify fist is
  made by scaling the finger masters, so following MPFB here would report a
  clenched hand as at rest; this is
  [where MPFB's own code paths disagree](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it),
  and :mod:`pose_reading` is where the choice is made. Each entry reports the
  current ``head`` beside ``moved_by``, so a read-back can be written back
  with FR 042's ``move_to`` unchanged, and ``rotation`` as an axis in the
  character frame plus degrees, which an agent can read and a quaternion in a
  bone's local axes it cannot.
- ``switches``: the current value of every switch ``get_pose_controls``
  lists, with a parent switch's parent named; and ``settings_off_default`` for
  the per-control settings (``finger_curve``, ``rubber_tweak``) that are not
  at their default.
- ``landmarks``: the hips, head, hands and feet, now and at rest, measured on
  the **deforming** bones - where the body is, not where a control sits.
- ``limbs``: reach and stretch per limb, which are derived rather than
  recorded; ``limb_measures`` says how each was computed and with what
  tolerance.

**Classification is ``get_pose_controls``', not a second opinion**: both read
[`shared/pose_controls.py`](../shared/pose_controls.py), so a bone that is
``left_hand``/``finger_master`` in one is the same in the other. The same
``body_parts`` filter applies, with the same default (everything but the face)
and the same always-complete ``counts_by_body_part`` - here, how many controls
in each part are posed. ``at_rest`` is about the whole character, filter or
not, so a posed face behind the default filter still reads as not at rest.

**An unclassified rig** gets every off-rest bone without ``body_part`` or
``role``, and ``switches``, ``landmarks`` and ``limbs`` as ``null`` - the
``null`` of "not computed", not the ``[]`` of "none".

**The depsgraph is updated before reading**, so a reading taken straight after
another tool's write sees that write. That makes the evaluated pose readable
and changes nothing else: no data, mode, selection or active object.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_pose",
)

from ..log import get_logger
from ..shared import pose_controls
from ..shared import pose_reading
from ..shared.character_frame import Frame
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getpose")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("body_parts", TYPE_ARRAY, default=None, nullable=True,
          description="Which body parts' posed controls to list, from: {:s}. Omit for every "
                      "part except face.".format(", ".join(pose_controls.BODY_PARTS))),
)

SUMMARY = ("Read a character's current pose: what is off rest, where the hands, feet, hips and "
           "head are, the switches, and whether a limb is stretched or out of reach.")


def _blocked(resolved):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    subject = resolved["subject"]
    answer: dict = dict(
        found=subject is not None and resolved["basemesh"] is not None,
        ready=False,
        blocked_by=resolved["blocked_by"],
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=resolved["resolved_by"],
        basemesh_name=None if resolved["basemesh"] is None else resolved["basemesh"].name,
        rig_object_name=None if resolved["rig"] is None else resolved["rig"].name,
        rig_identified_as=resolved["rig_identified_as"],
        at_rest=None,
        message=resolved["message"],
    )
    answer.update(resolved["extra"])
    return answer


def _message_for(rig, posed_total, listed, requested, limbs):
    if posed_total == 0:
        return "'{:s}' is in its rest pose.".format(rig.name)
    parts = ["{:d} control(s) of '{:s}' are off rest".format(posed_total, rig.name)]
    if requested is not None and listed != posed_total:
        parts.append(", {:d} of them in the body parts asked for".format(listed))
    parts.append(".")
    for part, limb in (limbs or {}).items():
        if limb and limb["stretched"]:
            parts.append(" {:s} is {:d} mm longer than at rest.".format(
                part, int(round((limb["length"] - limb["rest_length"]) * 1000))))
        if limb and limb["target_unreachable"]:
            parts.append(" {:s} cannot reach {:s}.".format(part, limb["ik_control"]))
    return "".join(parts)


def _classified_reading(frame, rig, classification, requested):
    """``(posed, counts, posed_total)`` for a classified rig; ``posed`` grouped by body part."""
    controls = classification["controls"]
    counts = {part: 0 for part in pose_controls.BODY_PARTS}
    posed = {part: [] for part in requested}
    for name, control in controls.items():
        pose_bone = rig.pose.bones[name]
        if not pose_reading.off_rest(pose_bone):
            continue
        counts[control["body_part"]] += 1
        if control["body_part"] in posed:
            posed[control["body_part"]].append(
                pose_reading.posed_entry(frame, pose_bone, control))
    return (posed, counts, sum(counts.values()))


def get_pose(params, resolution):
    """Read one character's pose, in the character frame."""
    resolved = pose_controls.resolve_posing_subject(
        resolution.services, params["name"], params["body_parts"])
    if resolved["blocked_by"] is not None:
        _LOG.debug("get_pose: refused %r", resolved["blocked_by"])
        return _blocked(resolved)
    rig = resolved["rig"]
    identified = resolved["rig_identified_as"]

    pose_reading.evaluated()
    frame = Frame(rig)
    classification = pose_controls.classify(resolution.module.__name__, rig, identified)
    answer: dict = dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=resolved["subject"].name,
        subject_resolved_by=resolved["resolved_by"],
        basemesh_name=resolved["basemesh"].name,
        rig_object_name=rig.name,
        rig_identified_as=identified,
        classified=classification["classified"],
        character_frame=frame.describe(),
    )

    if not classification["classified"]:
        posed = [pose_reading.posed_entry(frame, pose_bone) for pose_bone in rig.pose.bones
                 if pose_reading.off_rest(pose_bone)]
        answer.update(
            requested_body_parts=None, counts_by_body_part=None,
            at_rest=not posed, posed_count=len(posed), posed=None, posed_bones=posed,
            switch_values=None, switch_parents=None, settings_off_default=None,
            landmarks=None, limbs=None, limb_measures=None,
            message=_message_for(rig, len(posed), len(posed), None, None)
            + " The rig is '{!s}', which is not classified, so there are no body parts, "
              "switches, landmarks or limbs to report.".format(identified),
        )
        return answer

    requested = pose_controls.requested_body_parts(params["body_parts"])
    posed, counts, posed_total = _classified_reading(frame, rig, classification, requested)
    listed = sum(len(entries) for entries in posed.values())
    limbs = pose_reading.limbs(frame, rig, classification["limbs"])
    switch_values, switch_parents = pose_reading.switch_values(
        rig, classification["switches"], requested)
    answer.update(
        requested_body_parts=list(requested),
        counts_by_body_part=counts,
        at_rest=posed_total == 0,
        posed_count=posed_total,
        posed=posed,
        posed_bones=None,
        switch_values=switch_values,
        switch_parents=switch_parents,
        settings_off_default=pose_reading.settings_off_default(rig, classification["controls"]),
        landmarks=pose_reading.landmarks(frame, rig, classification["landmarks"]),
        limbs=limbs,
        limb_measures=dict(pose_reading.LIMB_MEASURES),
        message=_message_for(rig, posed_total, listed, requested, limbs),
    )
    _LOG.debug("get_pose: %d posed, %d listed", posed_total, len(posed))
    return answer
