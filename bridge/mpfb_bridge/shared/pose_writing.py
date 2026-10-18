"""
How a pose is written: one bone at a time, through ``pose_bone.matrix``, and undoably.

**One implementation for the three commands that change a pose**
([FR 042](../../../feature-requests/done/042-posing-bones-switches-and-reset/README.md)):
``set_pose_bones`` writes transforms, ``set_pose_switches`` writes the bones a
snap moves, and ``reset_pose`` writes rest and hands back the call that undoes
it. All three need the same five things, and a second copy of any of them would
let one command honour a lock the other ignores:

- **The write.** :func:`write` takes a target in armature space - a head, an
  orientation, scale factors - and reaches it through ``pose_bone.matrix``,
  which is the only setter that accepts "where the bone should be" rather than
  "what its own channels hold". Blender computes the bone's own channels from
  its parent's *current* pose, so :func:`parents_first` orders a batch parent
  before child - and after whatever a constraint on it or an ancestor reads -
  and the depsgraph is updated after every bone; a child's
  ``move_to`` therefore still holds after its parent moved in the same call. A
  kind of change the caller did not ask for is put back channel for channel
  afterwards, so asking for a rotation never nudges a location by float noise.
- **Locks, which that setter ignores.** Interactive transforms respect
  ``lock_location``/``lock_rotation``/``lock_scale``; ``pose_bone.matrix``
  writes the whole basis whatever they say. :func:`lock_violations` is how a
  writer finds out it changed a locked channel, read the way Rigify's own
  ``set_transform_from_matrix`` reads them: a quaternion or axis-angle bone is
  locked per component only with ``lock_rotations_4d``, and otherwise only when
  all three of ``lock_rotation`` are set. A connected bone's location is locked
  by construction - its head is its parent's tail - and is treated as such. A
  locked channel counts as changed only beyond ``achieved``'s own tolerance,
  and a smaller drift is put back by :func:`hold_locks`: a twist sent with an
  axis read back to three decimals leaks about 5e-4 rad into a locked Euler
  component, and refusing that would refuse the read-back the writer is meant
  to accept.
- **Drivers and animation**, read off the rig's own data paths.
  :func:`driven_kinds` is what a write must not touch, since the driver puts
  its value back on the next evaluation; :func:`animated_kinds` is what a write
  is flagged for, since the next frame change does the same. Neither is a
  guess: both parse ``pose.bones["<name>"].<channel>`` paths.
- **The undo.** Blender's undo stack does not record a bridge command, so the
  writers keep their own: :func:`snapshot` copies every channel of the bones a
  call will touch, and :func:`restore` puts them back **exactly** - pose basis
  data is plain numbers, which a rebuilt mesh is not. That is what lets
  ``set_pose_bones`` check after writing, where a check can only be made
  after writing, and still answer "nothing was applied". :func:`restore_entry`
  is the other undo: the ``set_pose_bones`` entry that recreates one bone's
  own transform, which is what ``reset_pose``'s ``restore_with`` is made of.
- **Who is in charge.** :func:`charge_refusal` says why a bone is not one a
  write should move: not a control, a limb chain the ``IK_FK`` switch has
  handed to the other chain, or an FK bone one of MPFB's helpers drives. Its
  ``write_instead`` names the write that would work - for a chain out of
  charge, an entry for **another tool** (``mpfb_set_pose_switches``).

**The three answers share a shape**, so this module also builds what each of
them starts with: the refusal (:func:`blocked_answer`, :func:`edit_mode_refusal`
for a rig in edit mode), the keys of a call allowed to write
(:func:`answer_base`), and what a write did to the body
(:func:`consequences`): the landmarks before and after, and each limb's reach
and stretch after, read by ``pose_reading`` under ``get_pose``'s own keys, with
the limbs this call made stretched or unable to reach named.

**Achieved is measured, with a tolerance that is part of its definition**
([a derived rather than recorded fact](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact)).
A constraint, an IK chain or a limit can stop a bone short of where it was
sent, and nothing records that it did; :func:`achieved` compares the bone's
evaluated matrix with the target, and :data:`ACHIEVED_MEASURE` is the sentence
every answer carries to say so.

**Nothing is borrowed.** No mode, selection or active object is touched and no
operator is called, so nothing here can insert a keyframe, whatever
``use_keyframe_insert_auto`` says. The one thing a write must change for a
moment is an armature showing its rest position: :func:`showing_pose` puts
``pose_position`` to ``"POSE"`` while matrices are computed, because in
``"REST"`` every ``pose_bone.matrix`` *is* the rest matrix and a target worked
out from it would be wrong, and puts it back however the block ends.

Like ``character_frame`` and ``pose_reading``, it reads nothing out of MPFB and
takes no ``services``.
"""

__all__ = (
    "ACHIEVED_DEGREES",
    "ACHIEVED_DISTANCE",
    "ACHIEVED_MEASURE",
    "ACHIEVED_SCALE",
    "KINDS",
    "REST_CHANNELS",
    "achieved",
    "animated_kinds",
    "animated_paths",
    "answer_base",
    "blocked_answer",
    "changed_kinds",
    "channels",
    "charge_refusal",
    "consequences",
    "driven_kinds",
    "edit_mode_refusal",
    "hold_locks",
    "limb_sentences",
    "lock_violations",
    "locks",
    "own_matrix",
    "parents_first",
    "rest_position_sentence",
    "restore",
    "restore_entry",
    "showing_pose",
    "snapshot",
    "switch_value",
    "to_rest",
    "write",
    "write_switch",
)

import contextlib
import math
import re

from mathutils import Matrix  # pylint: disable=import-error
from mathutils import Quaternion  # pylint: disable=import-error
from mathutils import Vector  # pylint: disable=import-error

from . import pose_reading

# A bone ended where it was sent when it is this close. One millimetre and half
# a degree: well above float noise and an IK solver's ordinary convergence,
# well below anything a viewer would see.
ACHIEVED_DISTANCE = 0.001
ACHIEVED_DEGREES = 0.5
ACHIEVED_SCALE = 0.001

ACHIEVED_MEASURE = (
    "achieved: after every write in the call, the bone's evaluated head is within {:g} m of "
    "what was asked, its orientation within {:g} degrees, and each scale factor asked for "
    "within {:g}; otherwise deviation says by how much".format(
        ACHIEVED_DISTANCE, ACHIEVED_DEGREES, ACHIEVED_SCALE))

# The three kinds of change, and the channels each one is held in.
KINDS = ("location", "rotation", "scale")

_CHANNELS = ("location", "rotation_quaternion", "rotation_euler", "rotation_axis_angle", "scale")

_ROTATION_CHANNEL = {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}

# get_pose_as_dict()'s threshold, which is also what "changed" means for a channel.
_CHANNEL_TOLERANCE = pose_reading.OFF_REST_THRESHOLD

_BONE_PATH = re.compile(
    r'^pose\.bones\["((?:[^"\\]|\\.)*)"\]\.'
    r'(location|rotation_quaternion|rotation_euler|rotation_axis_angle|scale)$')

# How many digits a restore_with value keeps. Finer than a read-back's
# millimetre and tenth of a degree, because a restore rounded to those would
# put a pose back only roughly.
_RESTORE_POSITION_DIGITS = 6
_RESTORE_DEGREE_DIGITS = 4


# ----------------------------------------------------------------------
# Channels, and the undo made of them


def _rotation_channel(pose_bone):
    return _ROTATION_CHANNEL.get(pose_bone.rotation_mode, "rotation_euler")


def channels(pose_bone):
    """Every transform channel of one pose bone, as plain tuples."""
    return {channel: tuple(float(value) for value in getattr(pose_bone, channel))
            for channel in _CHANNELS}


def snapshot(rig_object, names=None):
    """Every channel of the named bones (every bone when ``names`` is ``None``)."""
    pose_bones = rig_object.pose.bones
    if names is None:
        names = [pose_bone.name for pose_bone in pose_bones]
    return {name: channels(pose_bones[name]) for name in names}


def restore(rig_object, saved):
    """Put back exactly what :func:`snapshot` copied, and evaluate."""
    pose_bones = rig_object.pose.bones
    for name, values in saved.items():
        for channel, value in values.items():
            setattr(pose_bones[name], channel, value)
    pose_reading.evaluated()


# Every channel of a bone at rest: an identity matrix_basis, whatever its mode.
REST_CHANNELS = {
    "location": (0.0, 0.0, 0.0),
    "rotation_quaternion": (1.0, 0.0, 0.0, 0.0),
    "rotation_euler": (0.0, 0.0, 0.0),
    "rotation_axis_angle": (0.0, 0.0, 1.0, 0.0),
    "scale": (1.0, 1.0, 1.0),
}


def to_rest(pose_bone):
    """Put one bone at rest: :data:`REST_CHANNELS`."""
    for channel, value in REST_CHANNELS.items():
        setattr(pose_bone, channel, value)


def switch_value(rig_object, switch):
    """A switch's current value as its property holds it: a bool, an int or a float."""
    value = rig_object.pose.bones[switch["bone"]][switch["switch"]]
    if switch["type"] == "bool":
        return bool(value)
    if switch["type"] in ("parent", "int"):
        return int(value)
    return float(value)


def write_switch(rig_object, bone, prop, value):
    """Set one switch, the way Rigify's ``set_custom_property_value`` does, without a keyframe.

    ``rna_idprop_ui_prop_update`` tags what depends on the property, so the
    drivers reading it see the new value on the next evaluation.
    """
    from rna_prop_ui import rna_idprop_ui_prop_update  # pylint: disable=import-outside-toplevel,import-error
    pose_bone = rig_object.pose.bones[bone]
    pose_bone[prop] = value
    rna_idprop_ui_prop_update(pose_bone, prop)


def _constraint_targets(rig_object, pose_bone):
    """The bones of this rig that a constraint on ``pose_bone`` reads."""
    targets = []
    for constraint in pose_bone.constraints:
        if getattr(constraint, "target", None) == rig_object:
            targets.append(getattr(constraint, "subtarget", ""))
        if getattr(constraint, "pole_target", None) == rig_object:
            targets.append(getattr(constraint, "pole_subtarget", ""))
        for target in getattr(constraint, "targets", ()):
            if getattr(target, "target", None) == rig_object:
                targets.append(getattr(target, "subtarget", ""))
    return [name for name in targets if name]


def parents_first(rig_object, names):
    """``names`` ordered so that whatever moves a bone is written before it.

    That is its parent, and every bone a constraint on it or on one of its
    ancestors reads: a Rigify pole hangs from an ``MCH-`` bone that a parent
    switch moves by constraint after ``chest``, which is no ancestor of it, and
    a pole written before ``chest`` would be carried off by the chest's write.
    Otherwise the order given is kept.
    """
    pose_bones = rig_object.pose.bones
    depth = {}

    def depth_of(name, visiting):
        if name in depth:
            return depth[name]
        if name in visiting or name not in pose_bones:
            # A cycle, which Blender would refuse to evaluate, or a target that
            # is gone: nothing to order by.
            return 0
        visiting.add(name)
        pose_bone = pose_bones[name]
        found = 0
        if pose_bone.parent is not None:
            found = depth_of(pose_bone.parent.name, visiting) + 1
        for target in _constraint_targets(rig_object, pose_bone):
            found = max(found, depth_of(target, visiting) + 1)
        visiting.discard(name)
        depth[name] = found
        return found

    for name in names:
        depth_of(name, set())
    return sorted(names, key=lambda name: depth[name])


@contextlib.contextmanager
def showing_pose(rig_object):
    """Evaluate the rig in its pose for the block, whatever ``pose_position`` it shows."""
    armature = rig_object.data
    shown = armature.pose_position
    if shown != "POSE":
        armature.pose_position = "POSE"
    pose_reading.evaluated()
    try:
        yield shown
    finally:
        if armature.pose_position != shown:
            armature.pose_position = shown
            pose_reading.evaluated()


# ----------------------------------------------------------------------
# Locks, drivers and animation


def locks(pose_bone):
    """``{kind: [locked, ...]}``, one flag per component of the channel each kind lives in.

    Rigify's reading (``get_4d_rot_lock``): a quaternion or axis-angle bone's
    rotation is locked per component only under ``lock_rotations_4d``, and
    otherwise as a whole, when all three of ``lock_rotation`` are set. A
    connected bone's location is locked whatever its flags say.
    """
    if pose_bone.bone.use_connect:
        location = [True, True, True]
    else:
        location = [bool(flag) for flag in pose_bone.lock_location]
    if _rotation_channel(pose_bone) == "rotation_euler":
        rotation = [bool(flag) for flag in pose_bone.lock_rotation]
    elif pose_bone.lock_rotations_4d:
        rotation = [bool(pose_bone.lock_rotation_w)] + [bool(flag)
                                                        for flag in pose_bone.lock_rotation]
    else:
        rotation = [all(pose_bone.lock_rotation)] * 4
    return {"location": location, "rotation": rotation,
            "scale": [bool(flag) for flag in pose_bone.lock_scale]}


def _kind_values(pose_bone, values, kind):
    if kind == "location":
        return values["location"]
    if kind == "scale":
        return values["scale"]
    return values[_rotation_channel(pose_bone)]


def _aligned(pose_bone, before, after):
    """A quaternion read the same way round as ``before``, so q and -q compare equal."""
    if _rotation_channel(pose_bone) != "rotation_quaternion":
        return after
    if sum(b * a for b, a in zip(before, after)) < 0.0:
        return tuple(-value for value in after)
    return after


def _changed_components(pose_bone, before, after, kind, tolerance=_CHANNEL_TOLERANCE):
    old = _kind_values(pose_bone, before, kind)
    new = _kind_values(pose_bone, after, kind)
    if kind == "rotation":
        new = _aligned(pose_bone, old, new)
    return [abs(o - n) > tolerance for o, n in zip(old, new)]


# How far a locked channel may drift before a write counts as changing it: the
# tolerance achieved() allows, in each channel's own units. A rotation sent with
# an axis read back to three decimals moves a locked Euler component by about
# 5e-4 rad, which is noise from rounding, not a request to unlock it. A
# quaternion component is the sine of half the angle, hence the half.
_LOCK_TOLERANCE = {
    "location": ACHIEVED_DISTANCE,
    "rotation_euler": math.radians(ACHIEVED_DEGREES),
    "rotation_quaternion": math.radians(ACHIEVED_DEGREES) / 2.0,
    "rotation_axis_angle": math.radians(ACHIEVED_DEGREES),
    "scale": ACHIEVED_SCALE,
}


def _lock_tolerance(pose_bone, kind):
    if kind == "rotation":
        return _LOCK_TOLERANCE[_rotation_channel(pose_bone)]
    return _LOCK_TOLERANCE[kind]


def changed_kinds(pose_bone, before, after=None):
    """Which kinds of channel differ between two :func:`channels` readings."""
    after = channels(pose_bone) if after is None else after
    return [kind for kind in KINDS if any(_changed_components(pose_bone, before, after, kind))]


def lock_violations(pose_bone, before, after=None):
    """The kinds whose **locked** components differ between ``before`` and ``after``.

    Beyond ``achieved``'s tolerance, not the off-rest threshold: a smaller drift
    is rounding in what the caller sent, and :func:`hold_locks` puts it back.
    """
    after = channels(pose_bone) if after is None else after
    locked = locks(pose_bone)
    return [kind for kind in KINDS
            if any(change and lock for change, lock in
                   zip(_changed_components(pose_bone, before, after, kind,
                                           _lock_tolerance(pose_bone, kind)), locked[kind]))]


def hold_locks(pose_bone, before):
    """Put every locked component back to its value in ``before``, exactly."""
    locked = locks(pose_bone)
    for kind in KINDS:
        if not any(locked[kind]):
            continue
        channel = {"location": "location", "scale": "scale"}.get(kind) or \
            _rotation_channel(pose_bone)
        values = list(getattr(pose_bone, channel))
        for index, lock in enumerate(locked[kind]):
            if lock:
                values[index] = before[channel][index]
        setattr(pose_bone, channel, values)


def _unquoted(name):
    return re.sub(r"\\(.)", r"\1", name)


def _kinds_by_bone(fcurves):
    answer: dict = {}
    for fcurve in fcurves:
        match = _BONE_PATH.match(fcurve.data_path)
        if match is None:
            continue
        channel = match.group(2)
        kind = "rotation" if channel.startswith("rotation") else channel
        answer.setdefault(_unquoted(match.group(1)), set()).add(kind)
    return answer


def driven_kinds(rig_object):
    """``{bone: {kind, ...}}`` for every transform channel a driver on the rig sets."""
    animation = rig_object.animation_data
    if animation is None:
        return {}
    return _kinds_by_bone(animation.drivers)


def _action_fcurves(rig_object):
    animation = rig_object.animation_data
    if animation is None or animation.action is None:
        return []
    action = animation.action
    # Blender 4.4 made actions layered and 5.0 dropped Action.fcurves; the
    # F-curves of the slot this rig is animated by are in a channelbag.
    try:
        from bpy_extras import anim_utils  # pylint: disable=import-outside-toplevel
        channelbag = anim_utils.action_get_channelbag_for_slot(
            action, getattr(animation, "action_slot", None))
    except (ImportError, AttributeError):
        channelbag = None
    if channelbag is not None:
        return list(channelbag.fcurves)
    return list(getattr(action, "fcurves", ()))


def animated_kinds(rig_object):
    """``{bone: {kind, ...}}`` for every transform channel the rig's action animates."""
    return _kinds_by_bone(_action_fcurves(rig_object))


def animated_paths(rig_object):
    """Every data path the rig's action animates, for a write that is not a transform."""
    return set(fcurve.data_path for fcurve in _action_fcurves(rig_object))


# ----------------------------------------------------------------------
# The write


def own_matrix(pose_bone):
    """The bone's own transform in armature space, before its own constraints.

    What its channels put it at, given where its parent is now; on a control
    with no constraints it is ``pose_bone.matrix``. A relative change starts
    from this, so that a constraint's effect - an IK solver's rotation of the
    chain's first bone - is never baked into the bone's channels.
    """
    return pose_bone.id_data.convert_space(
        pose_bone=pose_bone, matrix=pose_bone.matrix_basis, from_space="LOCAL", to_space="POSE")


def write(pose_bone, head=None, orientation=None, scale=None):
    """Move one bone to a target in armature space, and evaluate.

    ``head`` is where its head should be (a ``Vector``) and ``orientation``
    its absolute orientation (a ``Quaternion``, the rotation part of
    ``pose_bone.matrix``); either may be ``None``, meaning that kind is not
    changed. ``scale`` maps ``"x"``/``"y"``/``"z"`` to a factor relative to
    rest, in the bone's own axes, and a missing axis is left as it is.
    """
    before = channels(pose_bone)
    if head is not None or orientation is not None:
        current_head, current_orientation, current_scale = own_matrix(pose_bone).decompose()
        pose_bone.matrix = Matrix.LocRotScale(
            current_head if head is None else head,
            current_orientation if orientation is None else orientation,
            current_scale)
        # Put back what was not asked for, channel for channel: the setter
        # rewrites the whole basis, and a value recomputed from a matrix is
        # never quite the value that was there.
        if head is None:
            pose_bone.location = before["location"]
        if orientation is None:
            for channel in ("rotation_quaternion", "rotation_euler", "rotation_axis_angle"):
                setattr(pose_bone, channel, before[channel])
        pose_bone.scale = before["scale"]
    if scale:
        pose_bone.scale = tuple(float(scale[axis]) if axis in scale else float(value)
                                for axis, value in zip("xyz", pose_bone.scale))
    pose_reading.evaluated()


def achieved(frame, pose_bone, head=None, orientation=None, scale=None):
    """``(achieved, deviation)``: whether the bone ended where it was sent, and if not by how much.

    Measured on the evaluated pose, so a constraint, an IK chain or a limit that
    stopped the bone short shows here. ``deviation`` has a key per kind asked
    for: ``distance`` (metres), ``degrees`` and ``scale`` (the largest factor
    error), and is ``None`` when the bone arrived.
    """
    deviation = {}
    matrix = pose_bone.matrix
    if head is not None:
        distance = (frame.armature_world(matrix.to_translation())
                    - frame.armature_world(head)).length
        if distance > ACHIEVED_DISTANCE:
            deviation["distance"] = round(distance, 4)
    if orientation is not None:
        difference = orientation.rotation_difference(matrix.to_quaternion()).angle
        degrees = math.degrees(min(difference, 2.0 * math.pi - difference))
        if degrees > ACHIEVED_DEGREES:
            deviation["degrees"] = round(degrees, 1)
    if scale:
        # The evaluated matrix in the bone's own space, so a constraint that
        # limits scale shows; the channels themselves always hold what was set.
        evaluated = pose_bone.id_data.convert_space(
            pose_bone=pose_bone, matrix=matrix, from_space="POSE", to_space="LOCAL").to_scale()
        error = max(abs(float(evaluated["xyz".index(axis)]) - float(factor))
                    for axis, factor in scale.items())
        if error > ACHIEVED_SCALE:
            deviation["scale"] = round(error, 4)
    return (not deviation, deviation or None)


# ----------------------------------------------------------------------
# Who may be written


def _control_for_internal(controls, name):
    """The control a ``DEF-``/``ORG-``/``MCH-`` bone is named for, by Rigify's naming, or ``None``."""
    for prefix in ("DEF-", "ORG-", "MCH-"):
        if not name.startswith(prefix):
            continue
        base = name[len(prefix):]
        # A numbered segment of a deforming bone: DEF-upper_arm.L.001.
        unsegmented = re.sub(r"\.\d{3}$", "", base)
        candidates = []
        for stem in (base, unsegmented):
            candidates.append(stem)
            match = re.match(r"^(.*?)((?:[._][LRlr])?(?:\.\d{3})?)$", stem)
            if match and match.group(1):
                candidates.append(match.group(1) + "_fk" + match.group(2))
        for candidate in candidates:
            if candidate in controls:
                return candidate
    return None


def charge_refusal(classification, in_charge, name):
    """Why a write must not move this bone on a classified rig, or ``None``.

    ``in_charge`` maps a limb's body part to ``"ik"``, ``"fk"`` or ``"blend"``,
    as :func:`pose_reading.limbs` reports it. Returns ``(reason, message,
    write_instead)``; ``write_instead`` is ``None``, ``{"bone": ...}``, or
    ``{"tool": ..., "switches": [...]}`` naming an entry for another tool.
    """
    controls = classification["controls"]
    control = controls.get(name)
    if control is None:
        instead = _control_for_internal(controls, name)
        pointer = ""
        if instead is not None:
            # A finger segment or the FK spine is named here, and the default
            # mpfb_get_pose_controls listing leaves both out (FR 043, R12).
            pointer = " Write '{:s}' instead.{:s}".format(
                instead, " It is hidden by default; mpfb_get_pose_controls lists it with "
                         "include_hidden." if controls[instead]["hidden_by_default"] else "")
        return ("not_a_control",
                "'{:s}' is not a control: the rig moves it itself, from its controls, and a "
                "write would be overwritten on the next evaluation.{:s}".format(name, pointer),
                None if instead is None else {"bone": instead})
    if control["driven_by"]:
        helper = control["driven_by"][0]
        return ("driven_by_helper",
                "'{name:s}' is driven by MPFB's helper '{helper:s}', whose constraint puts it "
                "back on the next evaluation. Move '{helper:s}' instead.".format(
                    name=name, helper=helper),
                {"bone": helper})
    limb = classification["limbs"].get(control["body_part"]) if classification["limbs"] else None
    if limb is None or limb["switch_bone"] is None or control["chain"] is None:
        return None
    now = in_charge.get(control["body_part"])
    if control["chain"] == "fk" and now == "ik":
        wanted, value = "FK", 1.0
    elif control["chain"] == "ik" and now == "fk":
        wanted, value = "IK", 0.0
    else:
        return None
    return ("chain_not_in_charge",
            "'{name:s}' is in {part:s}'s {chain:s} chain, and {part:s} is in {now:s}, so "
            "moving it would change nothing you can see. Switch the limb to {wanted:s} first "
            "with mpfb_set_pose_switches (it keeps the limb where it is), then write "
            "'{name:s}'.".format(name=name, part=control["body_part"],
                                 chain=control["chain"].upper(), now=now.upper(),
                                 wanted=wanted),
            {"tool": "mpfb_set_pose_switches",
             "switches": [{"body_part": control["body_part"], "switch": "IK_FK",
                           "value": value}]})


# ----------------------------------------------------------------------
# The undo a reset hands back


def _precise_point(frame, armature_point):
    world = frame.armature_world(armature_point) - frame.origin
    return {name: round(frame.axes[name].dot(world), _RESTORE_POSITION_DIGITS) + 0.0
            for name in frame.axes}


def restore_entry(frame, pose_bone):
    """The ``set_pose_bones`` entry that puts this bone's own transform back after a reset.

    Read **before the bone's own constraints** (:func:`own_matrix`): that is exactly the matrix the setter turns
    back into these channels once the parents are where they were, so the
    restore is exact. On a control with no constraints it equals what
    ``get_pose`` reports. Only the kinds that are off rest are named, and
    ``None`` comes back for a bone at rest. Values keep more digits than a
    read-back does, because a restore rounded to a millimetre would be one.
    """
    entry: dict = {"bone": pose_bone.name}
    threshold = pose_reading.OFF_REST_THRESHOLD
    unconstrained = own_matrix(pose_bone)
    if any(abs(value) > threshold for value in pose_bone.location):
        entry["move_to"] = _precise_point(frame, unconstrained.to_translation())
    rest = Vector(channels(pose_bone)[_rotation_channel(pose_bone)])
    at_rest = Vector((1.0, 0.0, 0.0, 0.0)) if len(rest) == 4 else Vector((0.0, 0.0, 0.0))
    if _rotation_channel(pose_bone) == "rotation_axis_angle":
        rotated = abs(rest[0]) > threshold
    elif len(rest) == 4:
        rotated = min((rest - at_rest).length, (rest + at_rest).length) > threshold
    else:
        rotated = (rest - at_rest).length > threshold
    if rotated:
        rest_orientation = pose_bone.bone.matrix_local.to_quaternion()
        rotation = unconstrained.to_quaternion() @ rest_orientation.inverted()
        entry["rotate_to"] = _precise_rotation(frame, rotation)
    scale = {axis: round(float(value), _RESTORE_POSITION_DIGITS)
             for axis, value in zip("xyz", pose_bone.scale) if abs(value - 1.0) > threshold}
    if scale:
        entry["scale_to"] = scale
    return entry if len(entry) > 1 else None


def _precise_rotation(frame, armature_rotation):
    quaternion = Quaternion(armature_rotation).normalized()
    if quaternion.w < 0.0:
        quaternion.negate()
    axis, angle = quaternion.to_axis_angle()
    degrees = round(math.degrees(angle), _RESTORE_DEGREE_DIGITS)
    if degrees == 0.0:
        return {"axis": None, "degrees": 0.0}
    world_axis = (frame.armature_world(Vector(axis)) - frame.armature_world(Vector()))
    world_axis.normalize()
    return {"axis": {name: round(frame.axes[name].dot(world_axis), _RESTORE_POSITION_DIGITS)
                     + 0.0 for name in frame.axes},
            "degrees": degrees}


# ----------------------------------------------------------------------
# What every writer's answer shares


def consequences(frame, rig, classification, landmarks_before, limbs_before) -> dict:
    """Landmarks before and after, limbs after, and the limbs this call stretched or overreached.

    Built from ``pose_reading``, so that it is ``get_pose``'s reading and not a
    second one.
    """
    if not classification["classified"]:
        return dict(landmarks=None, limbs=None, limb_measures=None,
                    limbs_made_stretched=[], limbs_made_unreachable=[])
    after = pose_reading.landmarks(frame, rig, classification["landmarks"])
    landmarks = {}
    for name, reading in after.items():
        if reading is None:
            landmarks[name] = None
            continue
        landmarks[name] = {"bone": reading["bone"],
                           "before": landmarks_before[name]["now"], "after": reading["now"]}
    limbs = pose_reading.limbs(frame, rig, classification["limbs"])
    stretched = [part for part, limb in limbs.items()
                 if limb and limb["stretched"] and not (limbs_before[part] or {}).get("stretched")]
    unreachable = [part for part, limb in limbs.items()
                   if limb and limb["target_unreachable"]
                   and not (limbs_before[part] or {}).get("target_unreachable")]
    return dict(landmarks=landmarks, limbs=limbs, limb_measures=dict(pose_reading.LIMB_MEASURES),
                limbs_made_stretched=stretched, limbs_made_unreachable=unreachable)


def blocked_answer(resolved) -> dict:
    """One shape for every refusal of a pose writer, so a caller can branch on ``blocked_by``."""
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
        message=resolved["message"],
    )
    answer.update(resolved["extra"])
    return answer


def edit_mode_refusal(resolved, not_done):
    """The rig is in edit mode, as a refusal of ``resolved``'s shape, or ``None``."""
    rig = resolved["rig"]
    if rig.mode != "EDIT":
        return None
    refused: dict = dict(resolved)
    refused.update(blocked_by="rig_in_edit_mode", extra={},
                   message="The rig '{:s}' is in edit mode, where its bones are edit bones and "
                           "have no pose{:s}. Leave edit mode and call again.".format(
                               rig.name, not_done))
    return refused


def answer_base(resolved, frame, classification, shown) -> dict:
    """The keys every pose writer's answer starts with, when it was allowed to write."""
    rig = resolved["rig"]
    return dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=resolved["subject"].name,
        subject_resolved_by=resolved["resolved_by"],
        basemesh_name=resolved["basemesh"].name,
        rig_object_name=rig.name,
        rig_identified_as=resolved["rig_identified_as"],
        classified=classification["classified"],
        pose_position=shown,
        character_frame=frame.describe(),
    )


def rest_position_sentence(rig, shown):
    """The sentence an answer carries when the armature does not show its pose."""
    if shown == "POSE":
        return ""
    return (" '{:s}' is showing its rest position, so none of this shows in the viewport "
            "until the armature's pose position is set back to Pose.".format(rig.name))


def limb_sentences(consequence):
    """What a write did to the limbs, as sentences for a message."""
    parts = []
    for part in consequence["limbs_made_stretched"]:
        limb = consequence["limbs"][part]
        parts.append(" This made {:s} stretch, {:d} mm longer than at rest.".format(
            part, int(round((limb["length"] - limb["rest_length"]) * 1000))))
    for part in consequence["limbs_made_unreachable"]:
        parts.append(" {:s} can no longer reach {:s}.".format(
            part, consequence["limbs"][part]["ik_control"]))
    return "".join(parts)
