"""
``set_pose_switches``: change a generated Rigify rig's switches, keeping each limb where it is.

The second pose writer ([FR 042](../../../feature-requests/done/042-posing-bones-switches-and-reset/README.md)).
Rigify's switches are custom properties on bones that look like nothing, and
setting one moves the body: the karate session's elbows splayed until
``pole_vector`` was turned on, and its fists stayed in the air when the hips
were lowered, because ``IK_parent`` hung the hands on ``root``. Each entry
names a switch the way ``get_pose_controls`` lists it, by ``body_part`` and
``switch``; the bone the property lives on is reported, never asked for.

**By default a switch keeps the limb where it is, as Rigify's own UI buttons
do** - but not by calling them. Each generated rig gets operators named after
its ``rig_id`` (``pose.rigify_limb_ik2fk_<rig_id>`` and so on), registered by
the ``rig_ui.py`` text block generation writes into the file. That block runs
after a reload only if Python auto-run is allowed, and at all only in a Blender
with a UI; the chains each operator works on are baked into it as operator
properties rather than stored on the rig. So the snaps are **ported** here, and
this module is their one user:

- ``IK_FK`` to 1.0: the FK controls take the pose of the IK result -
  ``RigifyGenericSnapBase`` in ``utils/animation.py``;
- ``IK_FK`` to 0.0: the IK control, the IK chain's first bone and (with
  ``pole_vector`` on) the pole take the pose of the FK result -
  ``RigifyLimbIk2FkBase`` in ``rigs/limbs/limb_rigs.py``, with the helpers it
  uses from ``rig_ui_template.py``'s ``UTILITIES_FUNC_COMMON_IK_FK``
  (``match_pole_target``, ``correct_rotation``, ``correct_scale``) and
  ``utils/animation.py``'s ``set_transform_from_matrix``;
- ``pole_vector``: the IK chain keeps its pose while the pole is turned on or
  off - ``RigifyLimbTogglePoleBase``;
- ``IK_parent`` and ``pole_parent``: the control keeps its world matrix under
  its new parent - ``RigifySwitchParentBase`` in ``utils/switch_parent.py``,
  which keeps only a pole's location, as Rigify's own builder does for a pole
  (``locks`` ``(False, True, True)``).

Rigify is GPL-2.0-or-later (Blender Foundation, 2019-2022), compatible with
this add-on's licence; the functions below are adaptations of its code, written
to this repository's conventions and changed in four places. Three avoid a
side effect the original has in Rigify's own UI and that a command must not:
no keyframe is ever inserted, a quaternion IK base is twisted through its
quaternion rather than being switched to ``ZXY`` for good, and the middle
controls of a chain longer than three are not handled because MPFB's limbs have
none (their absence is a resolution error, not an assumption). The fourth is
accuracy: ``correct_rotation``'s search stops at a tenth of a degree rather than
at one, since a degree of twist is several millimetres at the elbow.

**The chains come from Rigify's naming, checked against ``rig_ui.py`` by a
bridge test, never read out of the script.** That was FR 042's open question,
and FR 041's answer for the parent names is the same one. A limb's FK controls,
root to tip, are ``pose_controls``' ``fk_chain``; from the first two FK names
Rigify's ``make_derived_name`` gives the IK chain (``upper_arm_fk.L`` ->
``upper_arm_ik.L``; ``forearm_fk.L`` -> ``MCH-forearm_ik.L``; and
``MCH-upper_arm_ik_target.L``, the IK result's end), and the toe a leg may have
(``toe_fk.L`` -> ``toe_ik.L``) is its tail. The heel and spin controls are the
extra controls an IK->FK snap returns to rest. The same rule holds on
``human_toes`` (``.L``) and ``game_engine`` (``_l``), which the bridge test
establishes against both generated scripts. A bone the rule names that the rig
does not have is a resolution error naming it - a rig edited after generation
is answered, never guessed at.

**``IK_Stretch``, ``FK_limb_follow``, the follow switches and an ``IK_FK``
strictly between 0 and 1 have no snap** in Rigify either, and are written raw
with ``snapped: false`` and the reason. ``raw: true`` always writes the bare
value. Switches are applied **in request order**, because they interact: a pole
turned on before ``IK_FK`` goes to 0.0 changes what that snap computes.

**A snap that preserves the limb reports how well it did**, as ``snap_error``:
the furthest any joint of the limb's deforming chain (on the ``DEF-`` bones)
moved, so a snap that failed shows up as a number rather than being taken on
trust. The limb's end - the hand or the foot - is reported before and after.

**All or nothing.** Every entry is resolved first; then every pose bone's
channels and every switch are copied, and if anything raises part way through
they are put back. No mode, selection or active object is touched, no operator
is called, and so no keyframe can be inserted.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "set_pose_switches",
)

import math

from mathutils import Matrix  # pylint: disable=import-error
from mathutils import Vector  # pylint: disable=import-error

from ..log import get_logger
from ..shared import pose_controls
from ..shared import pose_reading
from ..shared import pose_writing
from ..shared.character_frame import Frame
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import is_number
from ..validation import TYPE_ARRAY
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setposeswitches")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("switches", TYPE_ARRAY, default=(),
          description="One object per switch: 'body_part', 'switch' (as mpfb_get_pose_controls "
                      "lists it), 'value', and 'raw' (default false: keep the limb where it "
                      "is)."),
)

SUMMARY = ("Change a generated Rigify rig's switches (IK/FK, pole, parents, stretch), keeping "
           "each limb where it is unless asked not to.")

_KEYS = ("body_part", "switch", "value", "raw")
_SNAPPING_RIGS = ("rigify", "rigify_game_engine")
_ROTATION_CHANNELS = ("rotation_quaternion", "rotation_euler", "rotation_axis_angle")


def _shape_error(entry):
    if not isinstance(entry, dict):
        return "an entry must be an object"
    unknown = sorted(key for key in entry if key not in _KEYS)
    if unknown:
        return "unknown key(s) {:s}; known keys are {:s}".format(
            ", ".join(unknown), ", ".join(_KEYS))
    for key in ("body_part", "switch"):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            return "'{:s}' must be a non-empty string".format(key)
    if "value" not in entry:
        return "'value' is required"
    if not isinstance(entry["value"], bool) and not is_number(entry["value"]):
        return "'value' must be a number, or a bool for an on/off switch"
    if "raw" in entry and not isinstance(entry["raw"], bool):
        return "'raw' must be a bool"
    return None


def _error(index, entry, reason, message, **extra):
    error: dict = dict(index=index, reason=reason, message=message)
    if isinstance(entry, dict):
        for key in ("body_part", "switch"):
            if isinstance(entry.get(key), str):
                error[key] = entry[key]
    error.update(extra)
    return error


# ----------------------------------------------------------------------
# The chains a snap reads and writes, from Rigify's naming


def _ik_name(fk_name, suffix="_ik"):
    return fk_name.replace("_fk", suffix, 1)


def snap_chains(rig, classification, body_part):
    """``(chains, missing)``: the bones Rigify's snaps for one limb would name.

    ``chains`` has ``fk`` (the FK controls, root to tip, a leg's toe included),
    ``ik`` (the IK result chain: the IK chain's first bone, the ``MCH-`` lower
    segment and the ``MCH-`` end), ``ctrl`` (the first bone, the pole and the IK
    control), ``tail`` (the toe's IK control, or nothing) and ``extra`` (the
    heel and spin controls). ``missing`` names every bone the rule gave that the
    rig does not have; ``chains`` is ``None`` then.
    """
    limb = classification["limbs"].get(body_part)
    if limb is None or not limb.get("fk_chain") or len(limb["fk_chain"]) < 3:
        return (None, ["the FK chain of {:s}".format(body_part)])
    fk = list(limb["fk_chain"])
    ik = [_ik_name(fk[0]), "MCH-" + _ik_name(fk[1]), "MCH-" + _ik_name(fk[0], "_ik_target")]
    ctrl = [ik[0], limb["pole"], limb["ik_control"]]
    tail = []
    if len(fk) > 3 and _ik_name(fk[3]) in rig.pose.bones:
        tail = [_ik_name(fk[3])]
    fk = fk[:3 + len(tail)]
    controls = classification["controls"]
    extra = sorted(name for name, control in controls.items()
                   if control["body_part"] == body_part and control["role"] == "foot_roll"
                   and name not in tail)
    missing = [name for name in ik + ctrl + tail if name is None or name not in rig.pose.bones]
    if missing:
        return (None, [str(name) for name in missing])
    return ({"fk": fk, "ik": ik, "ctrl": ctrl, "tail": tail, "extra": extra}, [])


# ----------------------------------------------------------------------
# Rigify's snapping utilities, ported (see the module docstring)


def _evaluate():
    pose_reading.evaluated()


def _set_transform_from_matrix(rig, name, matrix, *, space="POSE",
                               no_loc=False, no_rot=False, no_scale=False):
    """Rigify's ``set_transform_from_matrix``: assign a matrix, keeping locked channels."""
    pose_bone = rig.pose.bones[name]
    old = pose_writing.channels(pose_bone)
    if space != "LOCAL":
        matrix = rig.convert_space(pose_bone=pose_bone, matrix=matrix, from_space=space,
                                   to_space="LOCAL")
    pose_bone.matrix_basis = matrix
    locked = pose_writing.locks(pose_bone)

    def keep(channel, extra_lock, flags):
        if extra_lock or all(flags):
            setattr(pose_bone, channel, old[channel])
        elif any(flags):
            values = list(getattr(pose_bone, channel))
            for index, flag in enumerate(flags):
                if flag:
                    values[index] = old[channel][index]
            setattr(pose_bone, channel, values)

    keep("location", no_loc, locked["location"])
    active = {"QUATERNION": "rotation_quaternion",
              "AXIS_ANGLE": "rotation_axis_angle"}.get(pose_bone.rotation_mode, "rotation_euler")
    for channel in _ROTATION_CHANNELS:
        if channel != active:
            setattr(pose_bone, channel, old[channel])
    keep(active, no_rot, locked["rotation"])
    keep("scale", no_scale, locked["scale"])


def _set_pose_rotation(pose_bone, matrix):
    """Rigify's ``set_pose_rotation``: a local matrix's rotation, in the bone's own mode."""
    quaternion = matrix.to_quaternion()
    if pose_bone.rotation_mode == "QUATERNION":
        pose_bone.rotation_quaternion = quaternion
    elif pose_bone.rotation_mode == "AXIS_ANGLE":
        axis, angle = quaternion.to_axis_angle()
        pose_bone.rotation_axis_angle = (angle, axis[0], axis[1], axis[2])
    else:
        pose_bone.rotation_euler = quaternion.to_euler(pose_bone.rotation_mode)


def _twist(pose_bone):
    """The angle Rigify's ``correct_rotation`` searches over: ``rotation_euler[1]``."""
    if pose_bone.rotation_mode in ("QUATERNION", "AXIS_ANGLE"):
        return pose_bone.matrix_basis.to_quaternion().to_euler("ZXY")[1]
    return pose_bone.rotation_euler[1]


def _set_twist(pose_bone, angle):
    """Set that angle. Rigify switches a quaternion bone to ``ZXY`` for good; this does not."""
    if pose_bone.rotation_mode in ("QUATERNION", "AXIS_ANGLE"):
        euler = pose_bone.matrix_basis.to_quaternion().to_euler("ZXY")
        euler[1] = angle
        _set_pose_rotation(pose_bone, euler.to_matrix().to_4x4())
    else:
        pose_bone.rotation_euler[1] = angle


def _find_min_range(function, start, delta=math.pi / 8):
    angle = start
    while start - 2 * math.pi < angle < start + 2 * math.pi:
        left, centre, right = function(angle - delta), function(angle), function(angle + delta)
        if min(left, centre, right) == centre:
            return (angle - delta, angle + delta)
        angle += delta
    return (start - math.pi, start + math.pi)


def _ternary_search(function, left, right, precision):
    while abs(right - left) >= precision:
        left_third = left + (right - left) / 3
        right_third = right - (right - left) / 3
        if function(left_third) > function(right_third):
            left = left_third
        else:
            right = right_third
    return (left + right) / 2


# A tenth of a degree, where Rigify's correct_rotation stops at one: a degree of
# twist at the shoulder is several millimetres at the elbow, more than the
# millimetre a snap is held to.
_TWIST_PRECISION = math.pi / 1800


def _correct_rotation(bone_ik, target_matrix, ctrl_ik):
    """Rigify's ``correct_rotation``: twist the IK chain's first bone to match an FK bone."""
    axis = target_matrix.to_3x3().col[1].normalized()

    def distance(angle):
        _set_twist(ctrl_ik, angle)
        _evaluate()
        return -(bone_ik.vector.normalized().dot(axis))

    low, high = _find_min_range(distance, _twist(ctrl_ik))
    _set_twist(ctrl_ik, _ternary_search(distance, low, high, _TWIST_PRECISION))
    _evaluate()


def _correct_scale(bone_ik, target_matrix, ctrl_ik):
    """Rigify's ``correct_scale``."""
    wanted = target_matrix.to_scale()
    for _ in range(3):
        current = bone_ik.matrix.to_scale()
        ctrl_ik.scale = [value * want / now
                         for value, want, now in zip(bone_ik.scale, wanted, current)]
        _evaluate()
        if all(abs((now - want) / want) < 0.01 for want, now in zip(wanted, current)):
            break


def _perpendicular(vector):
    other = Vector((1, 0, 0)) if abs(vector[0]) < abs(vector[1]) else Vector((0, 1, 0))
    return vector.cross(other)


def _rotation_difference(first, second):
    angle = math.acos(min(1, max(-1, first.to_quaternion().dot(second.to_quaternion())))) * 2
    return 2 * math.pi - angle if angle > math.pi else angle


def _match_pole_target(rig, ik_first, ik_last, pole, *, match_matrix, length):
    """Rigify's ``match_pole_target``: place the pole so the chain's first bone matches."""
    start = ik_first.matrix.to_translation()
    chain = ik_last.matrix.to_translation() + ik_last.vector - start
    offset = _perpendicular(chain).normalized() * length

    def set_pole(vector):
        location = start + chain / 2 + vector
        local = rig.convert_space(pose_bone=pole, matrix=Matrix.Translation(location),
                                  from_space="POSE", to_space="LOCAL")
        pole.location = local.to_translation()
        _evaluate()

    set_pole(offset)
    angle = _rotation_difference(ik_first.matrix, match_matrix)
    one = Matrix.Rotation(angle, 4, chain) @ offset
    set_pole(one)
    first_angle = _rotation_difference(ik_first.matrix, match_matrix)
    other = Matrix.Rotation(-angle, 4, chain) @ offset
    set_pole(other)
    if first_angle < _rotation_difference(ik_first.matrix, match_matrix):
        set_pole(one)


def _compute_base_rotation(rig, chains, matrices, use_pole):
    _evaluate()
    bones = rig.pose.bones
    ik = [bones[name] for name in chains["ik"]]
    ctrl = [bones[name] for name in chains["ctrl"]]
    if use_pole:
        _match_pole_target(rig, ik[0], ik[1], ctrl[1], match_matrix=matrices[0],
                           length=ik[0].length + ik[1].length)
    else:
        _correct_rotation(ik[0], matrices[0], ctrl[0])


def _snap_fk_to_ik(rig, chains):
    """``RigifyGenericSnapBase``: the FK controls take the IK result's pose."""
    bones = rig.pose.bones
    matrices = [bones[name].matrix.copy() for name in chains["ik"] + chains["tail"]]
    for name, matrix in zip(chains["fk"], matrices):
        _set_transform_from_matrix(rig, name, matrix)
        _evaluate()


def _snap_ik_to_fk(rig, chains, use_pole):
    """``RigifyLimbIk2FkBase.apply_frame_state``: the IK controls take the FK result's pose."""
    bones = rig.pose.bones
    every = [bones[name].matrix.copy() for name in chains["fk"]]
    matrices = every[:len(chains["ik"])]
    tail_matrices = every[len(chains["ik"]):]
    ik = [bones[name] for name in chains["ik"]]
    ctrl = [bones[name] for name in chains["ctrl"]]
    for name in chains["extra"]:
        _set_transform_from_matrix(rig, name, Matrix.Identity(4), space="LOCAL")
    _evaluate()
    end = matrices[-1] @ ik[-1].matrix.inverted() @ ctrl[-1].matrix
    _set_transform_from_matrix(rig, chains["ctrl"][-1], end)
    ctrl[0].matrix_basis = Matrix.Identity(4)
    _set_transform_from_matrix(rig, chains["ctrl"][0], matrices[0], no_scale=True,
                               no_rot=use_pole)
    _compute_base_rotation(rig, chains, matrices, use_pole)
    _correct_scale(ik[0], matrices[0], ctrl[0])
    for name, matrix in zip(chains["tail"], tail_matrices):
        _evaluate()
        _set_transform_from_matrix(rig, name, matrix)
    _evaluate()


def _toggle_pole(rig, chains, switch_bone, use_pole):
    """``RigifyLimbTogglePoleBase.apply_frame_state``: the chain keeps its pose."""
    bones = rig.pose.bones
    matrices = [bones[name].matrix.copy() for name in chains["ik"]]
    pose_writing.write_switch(rig, switch_bone, "pole_vector", use_pole)
    _set_pose_rotation(bones[chains["ctrl"][0]], Matrix.Identity(4))
    _compute_base_rotation(rig, chains, matrices, use_pole)


def _switch_parent(rig, switch, controlled, value, locks):
    """``RigifySwitchParentBase.apply_frame_state``: the control keeps its world matrix."""
    pose_bone = rig.pose.bones[controlled]
    old = rig.convert_space(pose_bone=pose_bone, matrix=pose_bone.matrix_basis,
                            from_space="LOCAL", to_space="POSE")
    pose_writing.write_switch(rig, switch["bone"], switch["switch"], value)
    _evaluate()
    _set_transform_from_matrix(rig, controlled, old, no_loc=locks[0], no_rot=locks[1],
                               no_scale=locks[2])
    _evaluate()


# ----------------------------------------------------------------------
# Switch values


def _stored(switch, value):
    """The value as the property holds it: a bool, an int or a float."""
    if switch["type"] == "bool":
        return bool(value)
    if switch["type"] in ("parent", "int"):
        return int(value)
    return float(value)


def _value_error(switch, value):
    """Why ``value`` does not fit the live property, or ``None``."""
    kind = switch["type"]
    low, high = switch["range"]
    if kind == "bool":
        if not isinstance(value, bool):
            return "'{:s}' is on or off, so 'value' must be true or false".format(
                switch["switch"])
        return None
    if isinstance(value, bool):
        return "'{:s}' is a number, so 'value' must be a number rather than a bool".format(
            switch["switch"])
    if kind in ("parent", "int") and float(value) != int(value):
        return "'{:s}' takes a whole number".format(switch["switch"])
    if (low is not None and value < low) or (high is not None and value > high):
        return "'{:s}' takes {!s} to {!s}, and {!r} is outside it".format(
            switch["switch"], low, high, value)
    return None


# ----------------------------------------------------------------------
# Resolution and application


def _snap_kind(switch):
    if switch["switch"] == "IK_FK":
        return "ik_fk"
    if switch["switch"] == "pole_vector":
        return "pole"
    if switch["type"] == "parent":
        return "parent"
    return None


def _resolve(rig, classification, entries):
    """``(plans, errors)``, every entry checked against the live rig before anything is written."""
    by_key = {(switch["body_part"], switch["switch"]): switch
              for switch in classification["switches"]}
    plans = []
    errors = []
    seen = set()
    for index, entry in enumerate(entries):
        shape = _shape_error(entry)
        if shape is not None:
            errors.append(_error(index, entry, "invalid_entry", shape))
            continue
        key = (entry["body_part"], entry["switch"])
        if key in seen:
            errors.append(_error(index, entry, "duplicate_switch",
                                 "The same switch is named twice in this call."))
            continue
        seen.add(key)
        switch = by_key.get(key)
        if switch is None:
            known = sorted(name for part, name in by_key if part == entry["body_part"])
            errors.append(_error(
                index, entry, "unknown_switch",
                "{:s} has no switch called '{:s}' on this rig.".format(*key),
                known_switches=known,
                known_body_parts=sorted(set(part for part, _name in by_key))))
            continue
        problem = _value_error(switch, entry["value"])
        if problem is not None:
            errors.append(_error(index, entry, "invalid_value", problem,
                                 range=switch["range"]))
            continue
        plan: dict = dict(index=index, entry=entry, switch=switch, kind=_snap_kind(switch),
                    chains=None, controlled=None)
        if not entry.get("raw", False) and plan["kind"] in ("ik_fk", "pole"):
            chains, missing = snap_chains(rig, classification, entry["body_part"])
            if chains is None:
                errors.append(_error(
                    index, entry, "snap_chain_not_found",
                    "Keeping {:s} in place needs {:s}, which this rig does not have; it was "
                    "probably edited after generation. Send the entry with raw: true to write "
                    "the bare value.".format(entry["body_part"], ", ".join(missing)),
                    missing_bones=missing))
                continue
            plan["chains"] = chains
        if not entry.get("raw", False) and plan["kind"] == "parent":
            controlled = pose_controls.parent_switch_target(switch["description"])
            if controlled is None or controlled not in rig.pose.bones:
                errors.append(_error(
                    index, entry, "snap_chain_not_found",
                    "The switch does not say which bone it moves ('{!s}'), so it cannot be kept "
                    "in place. Send the entry with raw: true to write the bare value.".format(
                        switch["description"]),
                    missing_bones=[str(controlled)]))
                continue
            plan["controlled"] = controlled
        plans.append(plan)
    return (plans, errors)


def _joints(classification, plan):
    """The deforming joints a snap is judged by, and the bone standing for the limb's end."""
    limb = (classification["limbs"] or {}).get(plan["entry"]["body_part"])
    if limb is not None and limb["segments"] and limb["tip"] is not None:
        return (list(limb["segments"]) + [limb["tip"]], limb["tip"])
    if plan["controlled"] is not None:
        return ([plan["controlled"]], plan["controlled"])
    return ([], None)


def _apply(rig, classification, plan, previous):
    """Write one switch; ``(snapped, reason)``."""
    entry = plan["entry"]
    switch = plan["switch"]
    value = _stored(switch, entry["value"])
    if value == previous:
        return (False, "already_at_value")
    if entry.get("raw", False):
        pose_writing.write_switch(rig, switch["bone"], switch["switch"], value)
        _evaluate()
        return (False, "raw")
    if plan["kind"] == "ik_fk" and value in (0.0, 1.0):
        if value == 1.0:
            _snap_fk_to_ik(rig, plan["chains"])
        else:
            use_pole = bool(rig.pose.bones[switch["bone"]].get("pole_vector", False))
            _snap_ik_to_fk(rig, plan["chains"], use_pole)
        pose_writing.write_switch(rig, switch["bone"], switch["switch"], value)
        _evaluate()
        return (True, None)
    if plan["kind"] == "pole":
        _toggle_pole(rig, plan["chains"], switch["bone"], value)
        _evaluate()
        return (True, None)
    if plan["kind"] == "parent":
        control = classification["controls"].get(plan["controlled"])
        role = None if control is None else control["role"]
        # Rigify's builder keeps only a pole's location (no_fix_rotation and
        # no_fix_scale), which the bridge test checks against rig_ui.py.
        locks = (False, True, True) if role == "pole" else (False, False, False)
        _switch_parent(rig, switch, plan["controlled"], value, locks)
        return (True, None)
    pose_writing.write_switch(rig, switch["bone"], switch["switch"], value)
    _evaluate()
    return (False, "blend" if plan["kind"] == "ik_fk" else "no_snap")


_REASONS = {
    "already_at_value": "the switch already had this value, so nothing was written",
    "raw": "raw: true, so the bare value was written and the limb may have moved",
    "blend": "an IK_FK strictly between 0 and 1 blends the two chains, which has no snap",
    "no_snap": "Rigify offers no snap for this switch, so the bare value was written",
}


def _change(frame, rig, classification, plan, *, previous, snapped, reason, joints_before,
            animated_paths):
    switch = plan["switch"]
    joints, end = _joints(classification, plan)
    pose_bones = rig.pose.bones
    after = {name: frame.armature_world(pose_bones[name].head) for name in joints}
    change: dict = dict(body_part=switch["body_part"], switch=switch["switch"], bone=switch["bone"],
                  previous_value=previous, new_value=pose_writing.switch_value(rig, switch),
                  snapped=snapped)
    if not snapped:
        change["snap_reason"] = _REASONS[reason]
    change["end_bone"] = end
    change["end_before"] = None if end is None else frame.point(joints_before[end])
    change["end_after"] = None if end is None else frame.point(after[end])
    if snapped:
        change["snap_error"] = round(max(
            ((after[name] - joints_before[name]).length for name in joints), default=0.0), 4)
    path = 'pose.bones["{:s}"]["{:s}"]'.format(switch["bone"], switch["switch"])
    if path in animated_paths:
        change["overwritten_on_frame_change"] = True
    return change


def _message(rig, changes, consequence, shown):
    snapped = [change for change in changes if change["snapped"]]
    parts = ["Changed {:d} switch(es) on '{:s}'".format(
        sum(1 for change in changes if change["previous_value"] != change["new_value"]),
        rig.name)]
    if snapped:
        worst = max(change["snap_error"] for change in snapped)
        parts.append(", {:d} snapped to keep the limb in place (largest joint movement "
                     "{:.1f} mm)".format(len(snapped), worst * 1000))
    parts.append(".")
    parts.append(pose_writing.limb_sentences(consequence))
    parts.append(pose_writing.rest_position_sentence(rig, shown))
    return "".join(parts)


def _no_switches_refusal(resolved, classification):
    refused: dict = dict(resolved)
    family = classification["family"]
    refused.update(
        blocked_by="rig_has_no_switches", extra={},
        message="'{:s}' is a {:s} rig. Only a generated Rigify rig has switches "
                "(rigify_generated.human, .human_toes and .game_engine), so nothing was "
                "changed.{:s}".format(
                    resolved["rig"].name, str(resolved["rig_identified_as"]),
                    " MPFB's helpers on a default rig are bones: move them with "
                    "mpfb_set_pose_bones." if family == "default" else ""))
    return refused


def set_pose_switches(params, resolution):  # pylint: disable=too-many-locals
    """Resolve every switch, then apply them in request order, snapping unless raw."""
    not_done = ", so nothing was changed"
    resolved = pose_controls.resolve_posing_subject(
        resolution.services, params["name"], None, not_done="nothing was changed")
    if resolved["blocked_by"] is None:
        resolved = pose_writing.edit_mode_refusal(resolved, not_done) or resolved
    classification = None
    if resolved["blocked_by"] is None:
        classification = pose_controls.classify(
            resolution.module.__name__, resolved["rig"], resolved["rig_identified_as"])
        if classification["family"] not in _SNAPPING_RIGS:
            resolved = _no_switches_refusal(resolved, classification)
    if resolved["blocked_by"] is not None:
        _LOG.debug("set_pose_switches: refused %r", resolved["blocked_by"])
        answer = pose_writing.blocked_answer(resolved)
        answer.update(changes=[], change_count=0, resolution_errors=[])
        return with_performed(answer, False)

    rig = resolved["rig"]
    assert classification is not None, "set whenever the subject was not refused"
    entries = list(params["switches"])
    with pose_writing.showing_pose(rig) as shown:
        frame = Frame(rig)
        answer = pose_writing.answer_base(resolved, frame, classification, shown)
        if not entries:
            answer.update(changes=[], change_count=0, resolution_errors=[],
                          message="'switches' named nothing, so nothing was changed. "
                                  "mpfb_get_pose_controls lists the switches.")
            return with_performed(answer, False)
        plans, errors = _resolve(rig, classification, entries)
        if errors:
            answer.update(
                changes=[], change_count=0, resolution_errors=errors,
                message="{:d} entr{:s} could not be resolved, so **nothing at all was "
                        "written**. Fix the entries in 'resolution_errors' and send the whole "
                        "batch again.".format(len(errors), "y" if len(errors) == 1 else "ies"))
            return with_performed(answer, False)

        limbs_before = pose_reading.limbs(frame, rig, classification["limbs"])
        landmarks_before = pose_reading.landmarks(frame, rig, classification["landmarks"])
        saved = pose_writing.snapshot(rig)
        saved_switches = [(switch, pose_writing.switch_value(rig, switch)) for switch in classification["switches"]]
        animated_paths = pose_writing.animated_paths(rig)
        changes = []
        try:
            for plan in plans:
                joints, _end = _joints(classification, plan)
                joints_before = {name: frame.armature_world(rig.pose.bones[name].head)
                                 for name in joints}
                previous = pose_writing.switch_value(rig, plan["switch"])
                snapped, reason = _apply(rig, classification, plan, previous)
                changes.append(_change(frame, rig, classification, plan, previous=previous,
                                       snapped=snapped, reason=reason,
                                       joints_before=joints_before,
                                       animated_paths=animated_paths))
        except Exception:
            for switch, value in saved_switches:
                pose_writing.write_switch(rig, switch["bone"], switch["switch"], value)
            pose_writing.restore(rig, saved)
            raise
        consequence = pose_writing.consequences(frame, rig, classification, landmarks_before,
                                                limbs_before)
    answer.update(changes=changes, change_count=len(changes), resolution_errors=[])
    answer.update(consequence)
    answer["message"] = _message(rig, changes, consequence, shown)
    _LOG.debug("set_pose_switches: %d change(s) to %r", len(changes), rig.name)
    performed = any(change["previous_value"] != change["new_value"] for change in changes)
    return with_performed(answer, performed)
