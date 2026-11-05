"""
What a refit does to a pose, kept or reported, whichever the caller asked for.

``HumanService.refit()`` re-runs Rigify on a generated rig: it rebuilds the bones in the same object,
and every control comes back at rest and every ``IK_FK`` at its default. Nothing in its return value
says so, and the photo studio session found out from a ``chain_not_in_charge`` refused three
characters later ([FR 054](../../../feature-requests/done/054-refits-keep-the-pose/README.md)). On a
default rig a refit moves edit bones, and the pose comes through untouched.

**Six commands call :func:`kept` around their ``refit()``**, as they do ``selection.restored_all``,
because this is a rule they must agree about and a seventh copy of "which bones came back different" is
how one of them would call a lost pose ``unchanged``. See [`__init__.py`](__init__.py) for why this
directory exists.

**Decided by what happened, not by the rig's type.** Everything is read before the refit and compared
after it, and only what differs is written back, so a default rig has nothing written to it and a rig
family that starts losing its pose tomorrow is already covered. FR 054 measured 23 ms for all 1,090
bones of a generated rig beside a 550 ms refit, so there is no case for predicting instead of looking.

**What is read:** every channel of every bone, its rotation mode and each numeric custom property,
which is where ``IK_FK``, ``IK_Stretch``, ``IK_parent`` and ``pole_parent`` live. A channel a driver
sets is left out of the comparison and out of the write: Rigify's finger drivers set ``MCH-`` bones, and
those values follow the controls by themselves. Restored values are written directly, with no snapping,
because both chains go back to what they held. Also the armature's ``pose_position``: with a sub-rig,
``refit()`` sets it to ``"POSE"`` however it found it.

**Bones are found by name, after the refit.** Rigify rebuilds them, so a ``PoseBone`` held across the
call is a reference to something that no longer exists. A bone that is gone is named in
``bones_not_restored``, and a property that is gone from a bone that survived is named there too, as
``bone["property"]``.

**``keep_pose: false`` is told what it chose.** MPFB's result stands, ``pose_after_refit`` is
``"reset"``, and ``restore_with`` is the calls that would put it back, built by the functions
``reset_pose`` uses and never capped. It is built **after** the refit, by writing the old values back
for a moment and reading them, because a call read before a body change would send each control to where
it used to stand rather than give it the value it held, and those are what ``kept`` restores. So the two
agree, on any body. Only this path pays for that.

**A refit that raises still restores what it can**, in the ``finally``, and whatever that restore meets
is logged rather than raised, since the refit's own exception is the failure to report. A sub-rig's
pose is not read: no tool poses one, and FR 054's live check measured that a refit leaves it alone.
"""

__all__ = (
    "RefitPose",
    "answered",
    "kept",
    "no_refit",
)

import contextlib

import bpy

from ..log import get_logger
from . import pose_controls
from . import pose_reading
from . import pose_writing
from .character_frame import Frame

_LOG = get_logger("shared.refitpose")


class RefitPose:
    """What one refit did to a pose, as the keys and the sentence an answer carries."""

    def __init__(self, after_refit=None):
        self.after_refit = after_refit
        self.details = {}
        self.sentence = ""

    def answer(self):
        """The keys for an answer: ``pose_after_refit``, and what that value owes."""
        answer = dict(pose_after_refit=self.after_refit)
        answer.update(self.details)
        return answer

    def add_to(self, result):
        """Add these keys to a finished answer and this sentence to its message."""
        result.update(self.answer())
        result["message"] = result["message"] + self.sentence
        return result


def no_refit():
    """The outcome when no refit happened: ``null``, since nothing was looked at."""
    return RefitPose()


def answered(result):
    """``result``, with ``pose_after_refit`` null if the command refused before any refit."""
    result.setdefault("pose_after_refit", None)
    return result


def _bone_state(pose_bone):
    return dict(
        rotation_mode=pose_bone.rotation_mode,
        channels=pose_writing.channels(pose_bone),
        properties={key: pose_bone[key] for key in pose_bone.keys()
                    if isinstance(pose_bone[key], (bool, int, float))},
    )


def _read(armature):
    return {pose_bone.name: _bone_state(pose_bone) for pose_bone in armature.pose.bones}


def _kind_of(channel):
    return "rotation" if channel.startswith("rotation") else channel


def _differs(saved, now, driven_here):
    if saved["rotation_mode"] != now["rotation_mode"]:
        return True
    if any(value != now["channels"][channel] for channel, value in saved["channels"].items()
           if _kind_of(channel) not in driven_here):
        return True
    return any(key in now["properties"] and value != now["properties"][key]
               for key, value in saved["properties"].items())


def _compared(before, after, driven):
    """``(bones whose values differ, what is gone)``: the second names bones and properties."""
    differing = []
    gone = []
    for name, saved in before.items():
        now = after.get(name)
        if now is None:
            gone.append(name)
            continue
        gone.extend('{:s}["{:s}"]'.format(name, key) for key in saved["properties"]
                    if key not in now["properties"])
        if _differs(saved, now, driven.get(name, ())):
            differing.append(name)
    return (differing, gone)


def _put_back(armature, states, names, driven):
    """Write ``states`` of the named bones where they differ, and evaluate.

    The mode first, because the setter converts the rotation channels to it, and the channels after
    that hold what the bone held in that mode.
    """
    for name in names:
        pose_bone = armature.pose.bones[name]
        saved = states[name]
        if pose_bone.rotation_mode != saved["rotation_mode"]:
            pose_bone.rotation_mode = saved["rotation_mode"]
        driven_here = driven.get(name, ())
        for channel, value in saved["channels"].items():
            if _kind_of(channel) not in driven_here \
                    and pose_writing.channels(pose_bone)[channel] != value:
                setattr(pose_bone, channel, value)
        for key, value in saved["properties"].items():
            if key in pose_bone and pose_bone[key] != value:
                pose_writing.write_switch(armature, name, key, value)
    pose_reading.evaluated()


def _limbs_now(armature, classification):
    if not classification or not classification["classified"]:
        return {}
    with pose_writing.showing_pose(armature):
        return pose_reading.limbs(Frame(armature), armature, classification["limbs"])


def _newly(limbs_now, limbs_before, key):
    return [part for part, limb in limbs_now.items()
            if limb and limb[key] and not (limbs_before.get(part) or {}).get(key)]


def _kept_outcome(outcome, armature, differing, gone, classification, limbs_before):
    limbs_now = _limbs_now(armature, classification)
    outcome.after_refit = "kept"
    outcome.details = dict(
        pose_kept_count=len(differing),
        limbs_made_stretched=_newly(limbs_now, limbs_before, "stretched"),
        limbs_made_unreachable=_newly(limbs_now, limbs_before, "target_unreachable"),
        bones_not_restored=gone,
    )
    sentences = [" The refit reset the pose of '{:s}', and {:d} bone(s) were put back as they "
                 "were.".format(armature.name, len(differing))]
    sentences.extend(" {:s} now has to stretch to reach its target.".format(part)
                     for part in outcome.details["limbs_made_stretched"])
    sentences.extend(" {:s} can no longer reach its target.".format(part)
                     for part in outcome.details["limbs_made_unreachable"])
    if gone:
        sentences.append(" {:d} are gone from the rebuilt rig (bones_not_restored).".format(
            len(gone)))
    outcome.sentence = "".join(sentences)


def _switch_writes(armature, classification, left):
    """Each switch the refit changed, as ``reset_pose`` lists them: ``(switch, value, left at)``."""
    writes = []
    for switch in classification["switches"] or ():
        value = pose_writing.switch_value(armature, switch)
        now = left.get(switch["bone"], {}).get("properties", {}).get(switch["switch"], value)
        if now != value:
            writes.append((switch, value, now))
    return writes


def _reset_outcome(outcome, armature, before, differing, gone, classification, driven):
    """Leave MPFB's result standing, and say how to get the pose back.

    The way back is read with the old values in place on the new rig, and what MPFB left is then
    written over them, so what this call leaves is exactly what the refit left.
    """
    left = _read(armature)
    _put_back(armature, before, differing, driven)
    entries = []
    not_restorable = []
    switch_writes = []
    with pose_writing.showing_pose(armature):
        frame = Frame(armature)
        in_charge = {}
        if classification["classified"]:
            limbs = pose_reading.limbs(frame, armature, classification["limbs"])
            in_charge = {part: limb["in_charge"] for part, limb in limbs.items() if limb}
            switch_writes = _switch_writes(armature, classification, left)
        entries, not_restorable = pose_writing.restorable_entries(
            frame, armature, classification,
            pose_writing.controls_of(armature, classification), in_charge,
            pose_writing.driven_kinds(armature))
    _put_back(armature, left, differing, driven)
    outcome.after_refit = "reset"
    outcome.details = dict(
        pose_reset_count=len(differing),
        restore_with=pose_writing.restore_with(armature, entries, switch_writes),
        not_restorable=not_restorable,
        bones_not_restored=gone,
    )
    outcome.sentence = (" The refit reset the pose of '{:s}', and keep_pose is false, so it stays "
                        "reset: restore_with puts it back, mpfb_set_pose_switches' arguments "
                        "first.".format(armature.name))


def _settle(outcome, armature_name, keep_pose, before, shown, classification, limbs_before):
    """Compare what the refit left with what was there, and act on the difference."""
    armature = bpy.data.objects.get(armature_name)
    if armature is None or armature.type != "ARMATURE":
        outcome.after_refit = "reset"
        outcome.details = dict(pose_reset_count=0, restore_with={}, not_restorable=[],
                               bones_not_restored=sorted(before))
        outcome.sentence = " The rig '{:s}' is gone after the refit, so no pose could be kept.".format(
            armature_name)
        return
    pose_reading.evaluated()
    driven = pose_writing.driven_kinds(armature)
    differing, gone = _compared(before, _read(armature), driven)
    if differing or gone:
        if keep_pose:
            _put_back(armature, before, differing, driven)
            _kept_outcome(outcome, armature, differing, gone, classification, limbs_before)
        else:
            _reset_outcome(outcome, armature, before, differing, gone, classification, driven)
    else:
        outcome.after_refit = "unchanged"
    if armature.data.pose_position != shown:
        armature.data.pose_position = shown
        pose_reading.evaluated()


@contextlib.contextmanager
def kept(resolution, basemesh, keep_pose):
    """Run a refit, then keep the pose or report it. Yields the :class:`RefitPose` to answer with.

    The armature is the one the basemesh's modifier points at, or an ungenerated meta-rig: what
    ``pose_controls.find_rig`` calls the rig, so that the pose this keeps is the one ``mpfb_get_pose``
    reads. A character with no rig has nothing to lose and answers ``unchanged``.
    """
    rig, identified, metarig = pose_controls.find_rig(resolution.services, basemesh)
    armature = rig if rig is not None else metarig
    outcome = RefitPose()
    if armature is None:
        outcome.after_refit = "unchanged"
        yield outcome
        return

    armature_name = armature.name
    shown = armature.data.pose_position
    before = _read(armature)
    classification = pose_controls.classify(resolution.module.__name__, armature, identified)
    limbs_before = _limbs_now(armature, classification)
    finished = False
    try:
        yield outcome
        finished = True
    finally:
        if not finished and keep_pose:
            _restore_what_it_can(armature_name, before, shown)
    _settle(outcome, armature_name, keep_pose, before, shown, classification, limbs_before)


def _restore_what_it_can(armature_name, before, shown):
    """After a refit that raised: whatever this meets must not replace the refit's own exception."""
    try:
        armature = bpy.data.objects.get(armature_name)
        if armature is None:
            return
        driven = pose_writing.driven_kinds(armature)
        differing, _gone = _compared(before, _read(armature), driven)
        _put_back(armature, before, differing, driven)
        armature.data.pose_position = shown
    except Exception as error:  # pylint: disable=broad-except
        _LOG.warning("could not put the pose of %r back after a refit raised: %s",
                  armature_name, error)
