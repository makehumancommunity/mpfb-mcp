"""
What a character's pose is now: what is off rest, where the body is, and whether a limb is
stretched.

**A third shared module beside the two FR 041 named**, for the reason the other
two exist: [FR 042](../../../feature-requests/042-posing-bones-switches-and-reset/README.md)'s
writing tools report the same reach, stretch and landmarks after every write,
"under ``mpfb_get_pose``'s own keys and computed by the same shared code", and
its reset reports what is still off rest by the same test. A read-back and a
write report that disagreed about whether an arm is stretched would be the
contradiction [a summary is never a second opinion](../../../specifications/responses.md#a-summary-is-never-a-second-opinion)
forbids. :mod:`pose_controls` says what each bone *is*; this module says what
the pose *is*.

**"Off rest" is MPFB's test, plus scale.** :func:`off_rest` uses
``RigService.get_pose_as_dict()``'s threshold, 0.0001 on each channel in the
bone's own rotation mode, so that this package and MPFB agree on what is posed.
It departs from MPFB on purpose in one way: it checks **scale** too, which
``get_pose_as_dict()`` does not record. A Rigify fist is made by scaling the
finger masters on Y, and a read-back that did not see scale would report a
clenched hand as at rest (see
[where MPFB's own code paths disagree](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)).

**Where the body is, is measured on deforming bones.** On Rigify those are the
``DEF-`` bones; on the default rig, the bones themselves. Measuring the
controls instead would report where ``hand_ik.L`` is rather than where the hand
is, and the two differ exactly when a limb is in FK or cannot reach.

**Reach and stretch are derived, and their tolerances are part of their
definition**
([a derived rather than recorded fact](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact)).
Nothing records either. :data:`LIMB_MEASURES` is the sentence each answer
carries to say how they were computed, and the tolerances below are the only
place the numbers live:

- ``reach_ratio``: the distance from the limb's root (the head of its first
  deforming segment, now) to its IK control's head, over the chain's rest
  length - the rest lengths of its upper and lower segments summed. Above 1.0
  the control is further away than a straight limb reaches.
- ``stretched``: the deforming chain is more than :data:`STRETCH_TOLERANCE`
  longer now than at rest. With Rigify's ``IK_Stretch`` at 1.0, its default,
  this is how an over-reach shows up: the arm grows rather than falling short.
- ``target_unreachable``: the IK control is in charge, the limb's tip is more
  than :data:`REACH_TOLERANCE` from it, and the control is at least as far
  from the root as the chain is long. This is how an over-reach shows up with
  stretch off, or on a default rig with MPFB's helpers.

**Reading is preceded by a depsgraph update** (:func:`evaluated`), because a
reading made right after another tool's write must reflect that write; until
the update, ``pose_bone.matrix`` still holds the previous evaluation. It
changes no data, selection, mode or pose - it makes what is already true
readable - and the bridge tests read all four before and after.

Like ``character_frame``, it reads nothing out of MPFB and takes no
``services``; what it needs about the rig arrives as :mod:`pose_controls`'
classification.
"""

__all__ = (
    "LIMB_MEASURES",
    "OFF_REST_THRESHOLD",
    "REACH_TOLERANCE",
    "STRETCH_TOLERANCE",
    "evaluated",
    "landmarks",
    "limbs",
    "off_rest",
    "posed_entry",
    "settings_off_default",
    "switch_values",
)

import bpy

# get_pose_as_dict()'s threshold, per channel.
OFF_REST_THRESHOLD = 0.0001

# A chain longer than its rest length by more than this has stretched. One
# millimetre: well above float noise on a 0.6 m arm, well below a stretch a
# viewer would notice.
STRETCH_TOLERANCE = 0.001

# A limb tip further than this from its IK control has not reached it. One
# centimetre, so that an IK solver's ordinary convergence error is not reported
# as a failure to reach.
REACH_TOLERANCE = 0.01

_RATIO_DIGITS = 3

LIMB_MEASURES = {
    "reach_ratio": "limb root to IK control, over the chain's rest length",
    "stretched": "chain longer than at rest by over {:g} m".format(STRETCH_TOLERANCE),
    "target_unreachable": "IK in charge, tip over {:g} m from the IK control, control at "
                          "least a chain length from the root".format(REACH_TOLERANCE),
}


def evaluated():
    """Bring every pose matrix up to date with the last write, from whichever tool made it."""
    bpy.context.view_layer.update()


def _rotation_off_rest(pose_bone):
    mode = pose_bone.rotation_mode
    if mode == "QUATERNION":
        quaternion = pose_bone.rotation_quaternion
        return (abs(quaternion[0] - 1.0) > OFF_REST_THRESHOLD
                or any(abs(value) > OFF_REST_THRESHOLD for value in quaternion[1:]))
    if mode == "AXIS_ANGLE":
        return abs(pose_bone.rotation_axis_angle[0]) > OFF_REST_THRESHOLD
    return any(abs(value) > OFF_REST_THRESHOLD for value in pose_bone.rotation_euler)


def off_rest(pose_bone):
    """Whether a bone's own location, rotation or scale differs from rest."""
    return (any(abs(value) > OFF_REST_THRESHOLD for value in pose_bone.location)
            or _rotation_off_rest(pose_bone)
            or any(abs(value - 1.0) > OFF_REST_THRESHOLD for value in pose_bone.scale))


def posed_entry(frame, pose_bone, labels=None):
    """One off-rest bone, as ``get_pose`` reports it.

    ``head`` is where its head is now and ``moved_by`` how far that is from
    rest, both in the character frame. ``rotation`` is the rotation that takes
    the bone's rest orientation to its current one, in the character frame - so
    it includes what its parents did, which is what a write with ``rotate_to``
    must reproduce. ``scale`` is in the bone's own axes, ``y`` along it, and is
    ``null`` when it is 1 on every axis. ``labels``, a classified control,
    adds its ``role``; the caller groups entries by body part.
    """
    bone = pose_bone.bone
    rest_head = frame.armature_world(bone.head_local)
    now_head = frame.armature_world(pose_bone.head)
    rest_rotation = bone.matrix_local.to_quaternion()
    now_rotation = pose_bone.matrix.to_quaternion()
    entry = {"bone": pose_bone.name}
    if labels is not None:
        entry["role"] = labels["role"]
    entry["head"] = frame.point(now_head)
    entry["moved_by"] = frame.offset(now_head - rest_head)
    entry["rotation"] = frame.rotation(now_rotation @ rest_rotation.inverted())
    scale = pose_bone.scale
    if any(abs(value - 1.0) > OFF_REST_THRESHOLD for value in scale):
        entry["scale"] = {axis: round(float(value), 3) for axis, value in zip("xyz", scale)}
    else:
        entry["scale"] = None
    return entry


def landmarks(frame, rig_object, landmark_bones):
    """Each landmark's deforming bone and its head, now and at rest, in the character frame."""
    bones = rig_object.data.bones
    answer = {}
    for name, bone_name in landmark_bones.items():
        if bone_name is None or bone_name not in bones:
            answer[name] = None
            continue
        answer[name] = {
            "bone": bone_name,
            "now": frame.armature_point(rig_object.pose.bones[bone_name].head),
            "rest": frame.armature_point(bones[bone_name].head_local),
        }
    return answer


def _length_now(rig_object, names):
    return sum((rig_object.pose.bones[name].tail - rig_object.pose.bones[name].head).length
               for name in names)


def _length_at_rest(rig_object, names):
    return sum((rig_object.data.bones[name].tail_local - rig_object.data.bones[name].head_local)
               .length for name in names)


def _in_charge(rig_object, limb):
    """``"ik"``, ``"fk"`` or ``"blend"``: which chain moves the limb now."""
    switch_bone = limb["switch_bone"]
    if switch_bone is not None:
        pose_bone = rig_object.pose.bones[switch_bone]
        if "IK_FK" in pose_bone.keys():
            value = float(pose_bone["IK_FK"])
            if value <= 0.0:
                return "ik"
            if value >= 1.0:
                return "fk"
            return "blend"
    # A default rig: MPFB's helper, when installed, has taken the chain over.
    return "ik" if limb["ik_control"] is not None else "fk"


def _limb(frame, rig_object, limb):
    segments = limb["segments"]
    if not segments or limb["tip"] is None:
        return None
    pose_bones = rig_object.pose.bones
    rest_length = _length_at_rest(rig_object, segments)
    length = _length_now(rig_object, segments)
    root = frame.armature_world(pose_bones[segments[0]].head)
    tip = frame.armature_world(pose_bones[limb["tip"]].head)
    in_charge = _in_charge(rig_object, limb)
    answer = {
        "in_charge": in_charge,
        "ik_control": limb["ik_control"],
        "rest_length": round(rest_length, 3),
        "length": round(length, 3),
        "stretched": length - rest_length > STRETCH_TOLERANCE,
        "reach_ratio": None,
        "target_unreachable": None,
    }
    if limb["ik_control"] is not None and rest_length > 0.0:
        target = frame.armature_world(pose_bones[limb["ik_control"]].head)
        reach = (target - root).length
        answer["reach_ratio"] = round(reach / rest_length, _RATIO_DIGITS)
        if in_charge == "ik":
            answer["target_unreachable"] = bool(
                (tip - target).length > REACH_TOLERANCE
                and reach >= length - STRETCH_TOLERANCE)
    return answer


def limbs(frame, rig_object, limb_table):
    """Reach and stretch for each limb, in the order of ``limb_table``."""
    return {part: _limb(frame, rig_object, limb) for part, limb in limb_table.items()}


def switch_values(rig_object, switches, body_parts):
    """``(values, parents)``: each switch's value, and each parent switch's parent, by body part.

    Two maps keyed ``body_part`` then ``switch`` - the address
    ``mpfb_set_pose_switches`` takes - rather than a list of records, because
    this is read after every pose change and a map says the same in half the
    bytes. ``parents`` names the parent a parent switch's integer selects, or
    ``None`` where the property carries no list of names.
    """
    values = {}
    parents = {}
    for switch in switches:
        if switch["body_part"] not in body_parts:
            continue
        value = rig_object.pose.bones[switch["bone"]][switch["switch"]]
        if switch["type"] == "bool":
            value = bool(value)
        elif switch["type"] in ("parent", "int"):
            value = int(value)
        else:
            value = round(float(value), 3)
        values.setdefault(switch["body_part"], {})[switch["switch"]] = value
        if switch["type"] == "parent":
            names = switch["parent_names"]
            parents.setdefault(switch["body_part"], {})[switch["switch"]] = (
                names[value] if names and 0 <= value < len(names) else None)
    return (values, parents)


def settings_off_default(rig_object, controls):
    """Per-control settings (``finger_curve``, ``rubber_tweak``...) not at their default."""
    answer = []
    for name, control in controls.items():
        for prop in control["settings"] or ():
            pose_bone = rig_object.pose.bones[name]
            try:
                default = pose_bone.id_properties_ui(prop).as_dict().get("default")
            except (TypeError, KeyError):
                default = None
            value = pose_bone[prop]
            if default is None or abs(float(value) - float(default)) > OFF_REST_THRESHOLD:
                answer.append({"bone": name, "setting": prop,
                               "value": round(float(value), 3),
                               "default": None if default is None else round(float(default), 3)})
    return answer
