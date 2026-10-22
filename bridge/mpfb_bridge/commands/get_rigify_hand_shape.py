"""
``get_rigify_hand_shape``: each hand of a generated Rigify rig as a curl and a spread per finger.

The reader half of [FR 047](../../../feature-requests/done/047-rigify-hand-shapes/README.md).
Each finger is reported **in exactly the shape** ``set_rigify_hand_shape``
takes - ``curl`` and ``spread`` - so a read-back can be sent back unchanged,
which is FR 042's rule for ``rotate_to`` applied to hands. Beside the amounts
are what was measured on the deforming bones, ``joint_degrees`` and
``spread_degrees``, and where the fingertip is (``tip``, in the character
frame).

**The amounts are derived, and the answer says how**
([a derived rather than recorded fact](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact)):
from the finger master's rotation and Y scale, through the inverse of what the
writer does (:mod:`rigify_hands`). Nothing records that a hand is "curled
0.5"; a hand posed by hand, through ``mpfb_set_pose_bones`` or in the viewport,
may hold channels that are not a curl and a spread at all - a hook, a twisted
master, a posed segment or palm. Such a finger says so
(``expressible: false``, ``not_expressible_because``) and its amounts are the
least-squares fit to the measurement, never presented as exact.
``amounts_measure`` is the sentence that carries this on every answer.

**``matches_shape``** names the shape a hand is in, within a stated tolerance,
so a caller learns that a character it did not pose is making a fist.
**``known_shapes``** is on every answer, the vocabulary a caller needs before
writing - cheap in an answer and dear in every tool description, the reasoning
``mpfb_get_face_units`` uses for ``known_face_units``.

**Only rigs generated from MPFB's own Rigify meta-rigs**; every other rig is
refused with ``rig_not_supported`` and ``supported_rigs``, naming
``mpfb_set_pose_bones`` as the way to pose that rig's fingers. A meta-rig keeps
FR 041's ``rigify_not_generated``. A finger whose bones were edited after
generation is reported under its hand's ``finger_errors``, naming what is
missing, never guessed at.

**The depsgraph is updated before reading**, and a rig showing its rest
position is read in its pose for the moment of the call, as the writers do; it
changes nothing else.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_rigify_hand_shape",
)

from ..log import get_logger
from ..shared import pose_controls
from ..shared import pose_writing
from ..shared import rigify_hands
from ..shared.character_frame import Frame
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getrigifyhandshape")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("body_parts", TYPE_ARRAY, default=None, nullable=True,
          description="Which hands to read, from: {:s}. Omit for both.".format(
              ", ".join(rigify_hands.HANDS))),
)

SUMMARY = ("Read each hand of a generated Rigify rig as a curl and a spread per finger, with the "
           "joint angles and fingertips measured, and the shape it matches.")


def _read_hands(frame, rig, hands, wanted):
    answer = {}
    for hand in wanted:
        found = hands[hand]
        readings = {name: rigify_hands.read_finger(frame, rig, finger)
                    for name, finger in found["fingers"].items()}
        answer[hand] = rigify_hands.hand_entry(rig, found, readings)
    return answer


def _message(rig, answer_hands):
    parts = []
    for hand, entry in answer_hands.items():
        shape = entry["matches_shape"]
        odd = [name for name, finger in entry["fingers"].items() if not finger["expressible"]]
        sentence = "{:s} is {:s}".format(hand, "in '{:s}'".format(shape) if shape else
                                         "in no named shape")
        if odd:
            sentence += "; {:s} {:s} not a plain curl and spread (see not_expressible_because)".format(
                ", ".join(odd), "is" if len(odd) == 1 else "are")
        if entry["finger_errors"]:
            sentence += "; {:s} could not be read (finger_errors)".format(
                ", ".join(entry["finger_errors"]))
        parts.append(sentence)
    return "'{:s}': {:s}.".format(rig.name, ". ".join(parts))


def get_rigify_hand_shape(params, resolution):
    """Read the requested hands of one character, in the writer's own vocabulary."""
    resolved = pose_controls.resolve_posing_subject(resolution.services, params["name"], None)
    if resolved["blocked_by"] is None:
        resolved = rigify_hands.refusal(resolved, params["body_parts"], "body_parts") or resolved
    if resolved["blocked_by"] is not None:
        _LOG.debug("get_rigify_hand_shape: refused %r", resolved["blocked_by"])
        answer = pose_writing.blocked_answer(resolved)
        answer.update(hands=None, known_shapes=rigify_hands.known_shapes())
        return answer

    rig = resolved["rig"]
    wanted = [hand for hand in rigify_hands.HANDS
              if params["body_parts"] is None or hand in params["body_parts"]]
    with pose_writing.showing_pose(rig) as shown:
        frame = Frame(rig)
        classification = pose_controls.classify(
            resolution.module.__name__, rig, resolved["rig_identified_as"])
        hands = rigify_hands.find_hands(rig, classification)
        answer_hands = _read_hands(frame, rig, hands, wanted)
    answer: dict = dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=resolved["subject"].name,
        subject_resolved_by=resolved["resolved_by"],
        basemesh_name=resolved["basemesh"].name,
        rig_object_name=rig.name,
        rig_identified_as=resolved["rig_identified_as"],
        pose_position=shown,
        character_frame=frame.describe(),
        hands=answer_hands,
        known_shapes=rigify_hands.known_shapes(),
        amounts_measure=rigify_hands.AMOUNTS_MEASURE,
        message=_message(rig, answer_hands) + pose_writing.rest_position_sentence(rig, shown),
    )
    _LOG.debug("get_rigify_hand_shape: read %s of %r", ", ".join(wanted), rig.name)
    return answer
