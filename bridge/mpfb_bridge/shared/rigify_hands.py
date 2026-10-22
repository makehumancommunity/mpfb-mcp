"""
A hand on a generated Rigify rig, as an amount per finger: how far it is curled and how far spread.

**Two users, which is what warrants a module**
([FR 047](../../../feature-requests/done/047-rigify-hand-shapes/README.md)):
``get_rigify_hand_shape`` reads a hand as per-finger ``curl`` and ``spread``,
and ``set_rigify_hand_shape`` writes exactly that shape, so a read-back is a
write. A reader and a writer that mapped amounts to channels separately would
disagree about what ``curl: 0.5`` is, which is the contradiction
[a summary is never a second opinion](../../../specifications/responses.md#a-summary-is-never-a-second-opinion)
exists to prevent. This module finds a hand's fingers, maps amounts to channels
and back, holds the calibration and the shape table, and measures the joints.

**Only rigs generated from MPFB's own Rigify meta-rigs** (:data:`SUPPORTED_RIGS`).
On both, every finger is Rigify's ``limbs.super_finger`` with
``primary_rotation_axis: "X"`` and no extra IK control, and each hand has a
``super_palm``. ``rigify_generated.game_engine`` also has ``super_finger``
fingers, made with Rigify's defaults by MPFB's legacy conversion; it is not
calibrated, and it is refused rather than guessed at.

**How a Rigify finger moves, read live rather than assumed**
(``rigify/rigs/limbs/super_finger.py``):

- the **first knuckle** follows the master's rotation: the first ``MCH-…_drv``
  bone copies it (``COPY_ROTATION``, local space);
- **every later joint** bends by ``(1 - scale.y) · π`` about the primary axis,
  through a driver on each later ``MCH-…_drv`` bone. :func:`find_hands` reads
  the axis and its sign off those drivers - the expression must be one of
  Rigify's ``axis_options`` (:data:`BEND_EXPRESSIONS`) - and refuses a finger
  whose drivers say anything else. The spread axis is the master's remaining
  one, perpendicular to the bend axis and to the bone;
- the per-segment controls sit on top of that chain, so a rotation left on a
  segment adds to whatever the master does. A written finger's segments are
  therefore put at rest, and a read finger with a posed segment is reported as
  not expressible.

**A curl and a spread compose in a fixed order**: the spread swings the finger
sideways at the first knuckle, and the curl bends it about its own, already
swung axis. So the master's rotation is ``spread @ curl`` in the bone's own
axes, and reading it back is the inverse - a swing about the spread axis, a
swing about the bend axis and a twist about the bone, which a written finger
never has.

**The spread's sign is anatomical, and so is found geometrically**, from the
rest positions of the hand's own bones rather than from a table per side: the
same ``spread`` must spread both hands alike, and the bone axes of a left and a
right hand are mirror images. Positive moves ``index``, ``ring`` and ``pinky``
away from the middle finger, ``middle`` toward the index, and the thumb away
from the palm side (the side a curling finger moves toward).

**The calibration is in degrees** (:data:`CALIBRATION`), which makes it
independent of the size of the body, and was set during FR 047 on a default
``human_toes`` character by its acceptance; that request's README says how each
number was found. ``curl`` 1.0 is the finger as it sits in a fist, with the
fingertip against the palm rather than inside it. The knuckle stops short of
90 degrees because the master's rotation is read back by swinging about the
bend axis, which is singular at exactly 90.

**Measured, not assumed.** ``joint_degrees`` comes from the deforming bones -
the angle at each joint, rest-relative, first knuckle first - and is what a
write's ``achieved`` is checked against; ``tip`` is where the last deforming
bone ends. The amounts a reader reports are derived from the control channels
and checked against that measurement (:data:`AMOUNTS_MEASURE`).

Like ``pose_writing``, it reads nothing out of MPFB and takes no ``services``.
"""

__all__ = (
    "AMOUNTS_MEASURE",
    "BEND_EXPRESSIONS",
    "CALIBRATION",
    "CURL_RANGE",
    "DEGREES_TOLERANCE",
    "FINGERS",
    "HANDS",
    "MATCH_TOLERANCE",
    "SHAPES",
    "SPREAD_RANGE",
    "SUPPORTED_RIGS",
    "Finger",
    "channel_amounts",
    "expected_degrees",
    "find_hands",
    "finger_entry",
    "hand_entry",
    "known_shapes",
    "matching_shape",
    "measure",
    "read_finger",
    "refusal",
    "shape_amounts",
    "write_finger",
)

import math
import re

from mathutils import Matrix  # pylint: disable=import-error
from mathutils import Quaternion  # pylint: disable=import-error
from mathutils import Vector  # pylint: disable=import-error

from . import pose_reading
from . import pose_writing

# ----------------------------------------------------------------------
# Vocabulary. The finger and shape names, and the two ranges, are this
# package's own; mpfb-mcp's tool module holds a copy, and a unit test there
# reads this file as data and requires the two to agree.

SUPPORTED_RIGS = ("rigify_generated.human", "rigify_generated.human_toes")

HANDS = ("left_hand", "right_hand")

FINGERS = ("thumb", "index", "middle", "ring", "pinky")

CURL_RANGE = (-0.2, 1.0)
SPREAD_RANGE = (-1.0, 1.0)

# The token Rigify's names carry for each finger: f_index.01_master.L.
_TOKENS = {"thumb": "thumb", "f_index": "index", "f_middle": "middle", "f_ring": "ring",
           "f_pinky": "pinky"}

# Per finger, in degrees: what the first knuckle turns and what every later
# joint bends at curl 1.0, and the sideways swing at spread 1.0. Set on a
# default human_toes character during FR 047, by its acceptance: a fist with
# every fingertip just clear of the palm, measured from the bones, the thumb
# across the index and middle fingers, a pinch within a centimetre and a grip
# around a 4 cm cylinder. Each number's origin is in that request's README.
CALIBRATION = {
    "thumb": {"knuckle_degrees": 10.0, "joint_degrees": 40.0, "spread_degrees": 40.0},
    "index": {"knuckle_degrees": 85.0, "joint_degrees": 35.0, "spread_degrees": 20.0},
    "middle": {"knuckle_degrees": 85.0, "joint_degrees": 45.0, "spread_degrees": 10.0},
    "ring": {"knuckle_degrees": 85.0, "joint_degrees": 40.0, "spread_degrees": 15.0},
    "pinky": {"knuckle_degrees": 85.0, "joint_degrees": 35.0, "spread_degrees": 25.0},
}

# Every shape is a row of per-finger amounts in the writer's own vocabulary, so
# every shape is something a reader can report and a caller can write by hand.
SHAPES = {
    "open": {
        "thumb": {"curl": 0.0, "spread": 0.0},
        "index": {"curl": 0.0, "spread": 0.0},
        "middle": {"curl": 0.0, "spread": 0.0},
        "ring": {"curl": 0.0, "spread": 0.0},
        "pinky": {"curl": 0.0, "spread": 0.0},
    },
    "relaxed": {
        "thumb": {"curl": 0.3, "spread": -0.2},
        "index": {"curl": 0.2, "spread": 0.0},
        "middle": {"curl": 0.25, "spread": 0.0},
        "ring": {"curl": 0.3, "spread": 0.0},
        "pinky": {"curl": 0.35, "spread": 0.0},
    },
    "fist": {
        "thumb": {"curl": 1.0, "spread": -0.5},
        "index": {"curl": 1.0, "spread": 0.0},
        "middle": {"curl": 1.0, "spread": 0.0},
        "ring": {"curl": 1.0, "spread": 0.0},
        "pinky": {"curl": 1.0, "spread": 0.0},
    },
    "pointing": {
        "thumb": {"curl": 1.0, "spread": -0.5},
        "index": {"curl": 0.0, "spread": 0.0},
        "middle": {"curl": 1.0, "spread": 0.0},
        "ring": {"curl": 1.0, "spread": 0.0},
        "pinky": {"curl": 1.0, "spread": 0.0},
    },
    "grip": {
        "thumb": {"curl": 0.8, "spread": -0.8},
        "index": {"curl": 0.7, "spread": 0.0},
        "middle": {"curl": 0.75, "spread": 0.0},
        "ring": {"curl": 0.7, "spread": 0.0},
        "pinky": {"curl": 0.6, "spread": 0.0},
    },
    "pinch": {
        "thumb": {"curl": 0.65, "spread": -0.5},
        "index": {"curl": 0.7, "spread": 0.5},
        "middle": {"curl": 0.25, "spread": 0.0},
        "ring": {"curl": 0.3, "spread": 0.0},
        "pinky": {"curl": 0.35, "spread": 0.0},
    },
}

# Rigify's super_finger.axis_options, by expression: the sign of the bend about
# the primary axis as the master's Y scale drops below 1. A bridge test checks
# this table against the one Rigify ships.
BEND_EXPRESSIONS = {"(1-sy)*pi": 1.0, "-((1-sy)*pi)": -1.0}

# A joint within half a degree of what the amounts ask for is where it was
# sent; pose_writing's ACHIEVED_DEGREES, and the same bound decides whether the
# channels a reader finds are a curl and a spread at all.
DEGREES_TOLERANCE = 0.5

# A hand matches a shape when every finger it has is within this of the row.
MATCH_TOLERANCE = 0.05

AMOUNTS_MEASURE = (
    "curl and spread: from each finger master's rotation and Y scale. joint_degrees and "
    "spread_degrees: measured on the deforming bones, from rest. expressible: the channels are "
    "a curl and a spread within {:g} degrees and no segment or palm is posed; if not, the "
    "amounts are a least-squares fit to the measurement. matches_shape: every amount within "
    "{:g}".format(DEGREES_TOLERANCE, MATCH_TOLERANCE))

_AMOUNT_DIGITS = 3
_DEGREE_DIGITS = 1

# Bone names, as Rigify generates them from MPFB's meta-rigs.
_NAME = re.compile(r"^(?P<token>[A-Za-z_]+)\.(?P<number>\d+)(?P<master>_master)?"
                   r"\.(?P<side>[LR])(?P<copy>\.\d{3})?$")
_DRIVER_PATH = re.compile(r'^pose\.bones\["((?:[^"\\]|\\.)*)"\]\.rotation_euler$')

_Y = Vector((0.0, 1.0, 0.0))


# ----------------------------------------------------------------------
# Finding the fingers


class Finger:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """One finger of one hand, as this module needs to know it.

    ``master`` and ``segments`` are controls; ``deforming`` is the ``DEF-``
    chain, first knuckle first; ``axes`` the matrix whose columns are the bend
    axis (signed so that a positive angle curls), the bone and the spread axis,
    in the master's own space; ``spread_sign`` turns a rotation about that
    spread axis into this finger's anatomical spread; ``moved_by_palm`` is the
    palm control whose rotation carries this finger's base, or ``None``.
    """

    def __init__(self, name, hand, master):
        self.name = name
        self.hand = hand
        self.master = master
        self.segments = []
        self.tip_control = None
        self.deforming = []
        self.ik_control = None
        self.axes = None
        self.spread_sign = 1.0
        self.moved_by_palm = None
        self.calibration = CALIBRATION[name]

    @property
    def joint_count(self):
        """How many joints the finger has: its first knuckle and one per later segment."""
        return len(self.deforming)


def _parsed(name):
    match = _NAME.match(name)
    if match is None or match.group("token") not in _TOKENS:
        return None
    return match


def _hand_controls(classification, hand):
    return [name for name, control in classification["controls"].items()
            if control["body_part"] == hand]


def _driven_bends(rig_object):
    """``{master: [(bone, axis_index, sign or None, expression)]}`` from the rig's drivers."""
    found = {}
    animation = rig_object.animation_data
    if animation is None:
        return found
    for fcurve in animation.drivers:
        match = _DRIVER_PATH.match(fcurve.data_path)
        if match is None:
            continue
        driver = fcurve.driver
        for variable in driver.variables:
            for target in variable.targets:
                path = getattr(target, "data_path", "") or ""
                master = re.match(r'^pose\.bones\["((?:[^"\\]|\\.)*)"\]\.scale\.y$', path)
                if master is None or target.id is not rig_object:
                    continue
                expression = re.sub(r"\s+", "", driver.expression).replace(variable.name, "sy")
                found.setdefault(master.group(1), []).append(
                    (match.group(1), fcurve.array_index, BEND_EXPRESSIONS.get(expression),
                     driver.expression))
    return found


def _copies_rotation_of(rig_object, master):
    for pose_bone in rig_object.pose.bones:
        if not pose_bone.name.startswith("MCH-"):
            continue
        for constraint in pose_bone.constraints:
            if (constraint.type == "COPY_ROTATION" and constraint.target is rig_object
                    and constraint.subtarget == master):
                return pose_bone.name
    return None


def _axes(bend_index, bend_sign):
    """The columns bend (signed), bone, spread, in the master's own space, as a ``Matrix``."""
    bend = Vector((0.0, 0.0, 0.0))
    bend[bend_index] = bend_sign
    spread = bend.cross(_Y)
    return Matrix((bend, _Y, spread)).transposed()


def _mechanism(rig_object, finger, bends):
    """Fill in ``finger``'s chain and axes from the live rig; why it cannot be, or ``None``."""
    bones = rig_object.data.bones
    for segment in finger.segments:
        deforming = "DEF-" + segment
        if deforming not in bones:
            return "the deforming bone '{:s}' that '{:s}' drives is missing".format(
                deforming, segment)
        finger.deforming.append(deforming)
    if len(finger.segments) < 2:
        return "'{:s}' has {:d} segment control(s); a Rigify finger has at least two".format(
            finger.master, len(finger.segments))
    if _copies_rotation_of(rig_object, finger.master) is None:
        return ("no MCH- bone copies the rotation of '{:s}', so it does not turn the first "
                "knuckle".format(finger.master))
    driven = bends.get(finger.master, [])
    if len(driven) != len(finger.segments) - 1:
        return ("{:d} driver(s) read the Y scale of '{:s}'; a Rigify finger of {:d} segments has "
                "{:d}".format(len(driven), finger.master, len(finger.segments),
                              len(finger.segments) - 1))
    unknown = [expression for _bone, _index, sign, expression in driven if sign is None]
    if unknown:
        return ("the driver expression {!r} on '{:s}' is not one of Rigify's ({:s})".format(
            unknown[0], finger.master, ", ".join(sorted(BEND_EXPRESSIONS))))
    if len(set((index, sign) for _bone, index, sign, _expression in driven)) != 1:
        return "the drivers of '{:s}' bend its joints about different axes".format(finger.master)
    _bone, index, sign, _expression = driven[0]
    if index == 1:
        return ("the drivers of '{:s}' bend its joints about the bone's own axis, which leaves "
                "no axis to spread about".format(finger.master))
    finger.axes = _axes(index, sign)
    return None


def _armature_axes(rig_object, finger):
    """The finger's bend, bone and spread axes in armature space, at rest."""
    rest = rig_object.data.bones[finger.master].matrix_local.to_3x3().normalized()
    columns = rest @ finger.axes
    return columns.col[0].copy(), columns.col[1].copy(), columns.col[2].copy()


def _spread_signs(rig_object, fingers):
    """Set each finger's ``spread_sign``; ``{finger: why not}`` where no neighbour defines it."""
    bones = rig_object.data.bones
    heads = {name: bones[finger.master].head_local.copy() for name, finger in fingers.items()}
    others = [name for name in ("index", "middle", "ring", "pinky") if name in fingers]
    errors = {}
    for name, finger in fingers.items():
        _bend, bone, spread = _armature_axes(rig_object, finger)
        motion = spread.cross(bone)  # where the tip goes for a positive turn about the axis
        reference = None
        if name == "thumb":
            palm_side = Vector()
            for other in others:
                other_bend, other_bone, _ = _armature_axes(rig_object, fingers[other])
                palm_side += other_bend.cross(other_bone)  # where a curling finger goes
            if palm_side.length > 0.0:
                reference = -palm_side
        elif name == "middle":
            if "index" in fingers:
                reference = heads["index"] - heads["middle"]
            elif any(other in fingers for other in ("ring", "pinky")):
                rest = [heads[other] for other in ("ring", "pinky") if other in fingers]
                reference = heads["middle"] - sum(rest, Vector()) / len(rest)
        else:
            if "middle" in fingers:
                reference = heads[name] - heads["middle"]
            else:
                rest = [heads[other] for other in others if other != name]
                if rest:
                    reference = heads[name] - sum(rest, Vector()) / len(rest)
        if reference is None or abs(motion.normalized().dot(reference.normalized())) < 0.2:
            errors[name] = ("no neighbouring finger on the hand says which way '{:s}' spreads"
                            .format(finger.master))
            continue
        finger.spread_sign = 1.0 if motion.dot(reference) > 0.0 else -1.0
    return errors


def _palm_carrying(rig_object, master, palm_controls):
    """The palm control whose constraint moves the bone ``master`` hangs from, or ``None``."""
    parent = rig_object.pose.bones[master].parent
    if parent is None:
        return None
    for constraint in parent.constraints:
        if getattr(constraint, "target", None) is rig_object and \
                getattr(constraint, "subtarget", "") in palm_controls:
            return constraint.subtarget
    return None


def find_hands(rig_object, classification):
    """Each hand's fingers, from FR 041's classification and the live rig.

    Returns ``{hand: {"fingers": {finger: Finger}, "errors": {finger: why},
    "palm_controls": [...]}}`` for both hands. A finger whose chain, drivers or
    spread cannot be read is in ``errors`` with a sentence naming what was
    looked for, never in ``fingers``; a finger the hand does not have is in
    neither.
    """
    bends = _driven_bends(rig_object)
    hands = {}
    for hand in HANDS:
        controls = _hand_controls(classification, hand)
        roles = classification["controls"]
        fingers = {}
        for name in controls:
            match = _parsed(name)
            if match is None:
                continue
            finger = _TOKENS[match.group("token")]
            if roles[name]["role"] == "finger_master" and match.group("master"):
                fingers[finger] = Finger(finger, hand, name)
        for name in sorted(controls):
            match = _parsed(name)
            if match is None or roles[name]["role"] != "finger_segment":
                continue
            finger = fingers.get(_TOKENS[match.group("token")])
            if finger is None:
                continue
            if match.group("copy"):
                finger.tip_control = name
            else:
                finger.segments.append(name)
        palm_controls = sorted(name for name in controls if name.startswith("palm")
                               and roles[name]["role"] not in ("finger_master", "finger_segment"))
        errors = {}
        for finger in list(fingers.values()):
            finger.segments.sort(key=lambda name: int(_parsed(name).group("number")))
            why = _mechanism(rig_object, finger, bends)
            if why is not None:
                errors[finger.name] = why
                del fingers[finger.name]
                continue
            ik_name = finger.segments[0].replace(".01.", ".01_ik.", 1)
            if ik_name in rig_object.pose.bones and "FK_IK" in rig_object.pose.bones[ik_name]:
                finger.ik_control = ik_name
            finger.moved_by_palm = _palm_carrying(rig_object, finger.master, palm_controls)
        for name, why in _spread_signs(rig_object, fingers).items():
            errors[name] = why
            del fingers[name]
        ordered = {name: fingers[name] for name in FINGERS if name in fingers}
        hands[hand] = {"fingers": ordered, "errors": {name: errors[name] for name in FINGERS
                                                       if name in errors},
                       "palm_controls": palm_controls}
    return hands


# ----------------------------------------------------------------------
# Amounts and channels


def _canonical(finger, quaternion):
    """A rotation in the master's own space, in the frame (bend, bone, spread)."""
    axes = finger.axes
    return (axes.transposed() @ quaternion.to_matrix() @ axes).to_quaternion()


def expected_degrees(finger, curl, spread):
    """``(joint_degrees, spread_degrees)`` that ``curl`` and ``spread`` ask of ``finger``."""
    calibration = finger.calibration
    joints = [curl * calibration["knuckle_degrees"]]
    joints += [curl * calibration["joint_degrees"]] * (finger.joint_count - 1)
    return (joints, spread * calibration["spread_degrees"])


def _fit(finger, joint_degrees):
    """The curl that best explains ``joint_degrees``, least squares over every joint."""
    expected, _ = expected_degrees(finger, 1.0, 0.0)
    return sum(e * m for e, m in zip(expected, joint_degrees)) / sum(e * e for e in expected)


def channel_amounts(rig_object, finger):
    """What the master's channels say: ``(curl, spread, reasons)``, unrounded.

    ``reasons`` lists why the channels are not a curl and a spread: the master
    moved, twisted about the bone, or its knuckle and later joints imply
    different curls. ``curl`` is then the least-squares fit to the channels'
    own angles, which is still what a restore must put back.
    """
    pose_bone = rig_object.pose.bones[finger.master]
    basis = pose_bone.matrix_basis
    reasons = []
    if any(abs(value) > pose_reading.OFF_REST_THRESHOLD for value in basis.to_translation()):
        reasons.append("master_moved")
    euler = _canonical(finger, basis.to_quaternion()).to_euler("YXZ")
    knuckle = math.degrees(euler.x)
    twist = math.degrees(euler.y)
    sideways = math.degrees(euler.z) * finger.spread_sign
    joint = (1.0 - float(pose_bone.scale[1])) * 180.0
    angles = [knuckle] + [joint] * (finger.joint_count - 1)
    curl = _fit(finger, angles)
    if abs(twist) > DEGREES_TOLERANCE:
        reasons.append("master_twisted")
    fitted, _ = expected_degrees(finger, curl, 0.0)
    if max(abs(f - a) for f, a in zip(fitted, angles)) > DEGREES_TOLERANCE:
        reasons.append("knuckle_and_joints_disagree")
    return (curl, sideways / finger.calibration["spread_degrees"], reasons)


def _orientation(rig_object, name, pose):
    if pose:
        return rig_object.pose.bones[name].matrix.to_3x3().normalized()
    return rig_object.data.bones[name].matrix_local.to_3x3().normalized()


def measure(rig_object, finger):
    """``(joint_degrees, spread_degrees)`` on the deforming bones, rest-relative, unrounded.

    **Each reading uses only what the deforming bones carry exactly.** Rigify's
    stretch constraints give the first deforming bone its direction but not the
    twist the master's rotation has, and give every later one its control's
    whole orientation. So the first knuckle is read as a direction in the bone's
    rest frame - a swing about the spread axis, then about the bend axis - and
    each later joint as the turn about its own bend axis that carries the
    previous bone's direction, seen from the later bone, back to where it is at
    rest. Neither depends on the twist the first bone lacks; a curl is positive.
    """
    names = finger.deforming
    first = rig_object.pose.bones[names[0]]
    rest_first = _orientation(rig_object, names[0], False)
    if first.parent is None:
        relative_now = _orientation(rig_object, names[0], True)
        relative_rest = rest_first
    else:
        relative_now = (first.parent.matrix.to_3x3().normalized().inverted()
                        @ _orientation(rig_object, names[0], True))
        relative_rest = first.parent.bone.matrix_local.to_3x3().normalized().inverted() @ rest_first
    axes_inverse = finger.axes.transposed()
    direction = axes_inverse @ (relative_rest.inverted() @ relative_now @ _Y)
    knuckle = math.degrees(math.asin(max(-1.0, min(1.0, direction.z))))
    sideways = math.degrees(math.atan2(-direction.x, direction.y)) * finger.spread_sign
    joints = [knuckle]
    for previous, current in zip(names, names[1:]):
        seen_now = axes_inverse @ (_orientation(rig_object, current, True).inverted()
                                   @ _orientation(rig_object, previous, True) @ _Y)
        seen_at_rest = axes_inverse @ (_orientation(rig_object, current, False).inverted()
                                       @ _orientation(rig_object, previous, False) @ _Y)
        joints.append(math.degrees(math.atan2(
            seen_now.y * seen_at_rest.z - seen_now.z * seen_at_rest.y,
            seen_now.y * seen_at_rest.y + seen_now.z * seen_at_rest.z)))
    return (joints, sideways)


def _clamped(value, bounds):
    return min(bounds[1], max(bounds[0], value))


def _rounded(value, digits):
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0.0 else rounded


def read_finger(frame, rig_object, finger):
    """Everything known about one finger now, unrounded, as a dict this module rounds later.

    Keys: ``curl``, ``spread`` (what is reported), ``channel_curl``,
    ``channel_spread`` (what the master holds, for a restore),
    ``channel_reasons``, ``reasons`` (every reason it is not expressible),
    ``joint_degrees``, ``spread_degrees`` and ``tip`` (a frame point).
    """
    curl, spread, channel_reasons = channel_amounts(rig_object, finger)
    joints, sideways = measure(rig_object, finger)
    reasons = list(channel_reasons)
    pose_bones = rig_object.pose.bones
    if any(pose_reading.off_rest(pose_bones[name])
           for name in finger.segments + ([finger.tip_control] if finger.tip_control else [])):
        reasons.append("segment_posed")
    if finger.moved_by_palm is not None and pose_reading.off_rest(pose_bones[finger.moved_by_palm]):
        reasons.append("palm_posed")
    reported_curl, reported_spread = curl, spread
    if reasons:
        reported_curl = _fit(finger, joints)
        reported_spread = sideways / finger.calibration["spread_degrees"]
    if (_clamped(reported_curl, CURL_RANGE) != reported_curl
            or _clamped(reported_spread, SPREAD_RANGE) != reported_spread):
        reasons.append("outside_range")
    tip = frame.armature_point(pose_bones[finger.deforming[-1]].tail)
    return {"curl": _clamped(reported_curl, CURL_RANGE),
            "spread": _clamped(reported_spread, SPREAD_RANGE),
            "channel_curl": curl, "channel_spread": spread, "channel_reasons": channel_reasons,
            "reasons": reasons, "joint_degrees": joints, "spread_degrees": sideways, "tip": tip}


def finger_entry(reading):
    """A :func:`read_finger` reading as an answer reports it: the writer's shape, plus the measurement."""
    entry = {"curl": _rounded(reading["curl"], _AMOUNT_DIGITS),
             "spread": _rounded(reading["spread"], _AMOUNT_DIGITS),
             "expressible": not reading["reasons"]}
    if reading["reasons"]:
        entry["not_expressible_because"] = list(reading["reasons"])
    entry["joint_degrees"] = [_rounded(value, _DEGREE_DIGITS) for value in reading["joint_degrees"]]
    entry["spread_degrees"] = _rounded(reading["spread_degrees"], _DEGREE_DIGITS)
    entry["tip"] = reading["tip"]
    return entry


def matching_shape(readings):
    """The first shape every finger of the hand matches within :data:`MATCH_TOLERANCE`, or ``None``."""
    if not readings or any(reading["reasons"] for reading in readings.values()):
        return None
    for shape, row in SHAPES.items():
        if all(abs(reading["curl"] - row[name]["curl"]) <= MATCH_TOLERANCE
               and abs(reading["spread"] - row[name]["spread"]) <= MATCH_TOLERANCE
               for name, reading in readings.items()):
            return shape
    return None


def known_shapes():
    """The shape table as an answer reports it: a copy, so no caller can change the module's."""
    return {shape: {name: dict(amounts) for name, amounts in row.items()}
            for shape, row in SHAPES.items()}


def shape_amounts(shape):
    """One shape's row, ``{finger: {"curl", "spread"}}``, copied."""
    return {name: dict(amounts) for name, amounts in SHAPES[shape].items()}


def _set_rotation(pose_bone, quaternion):
    mode = pose_bone.rotation_mode
    if mode == "QUATERNION":
        current = Quaternion(pose_bone.rotation_quaternion)
        if current.dot(quaternion) < 0.0:
            quaternion = -quaternion
        pose_bone.rotation_quaternion = quaternion
    elif mode == "AXIS_ANGLE":
        axis, angle = quaternion.to_axis_angle()
        pose_bone.rotation_axis_angle = (angle, axis[0], axis[1], axis[2])
    else:
        pose_bone.rotation_euler = quaternion.to_euler(mode, pose_bone.rotation_euler)


def write_finger(rig_object, finger, curl, spread, keep_scale=False):
    """Put ``finger``'s master where ``curl`` and ``spread`` say, and its segments at rest.

    Writes the master's own channels rather than going through
    ``pose_bone.matrix``: an amount is a local rotation and a scale, and
    computing it from a matrix would lose exactly what a restore must put
    back. ``keep_scale`` leaves the Y scale - the later joints - exactly as it
    is, for a write that asked only for a spread. The caller snapshots first,
    checks locks after, and evaluates.
    """
    calibration = finger.calibration
    swing = Quaternion((0.0, 0.0, 1.0),
                       math.radians(spread * calibration["spread_degrees"] * finger.spread_sign))
    bend = Quaternion((1.0, 0.0, 0.0), math.radians(curl * calibration["knuckle_degrees"]))
    axes = finger.axes
    local = (axes @ (swing @ bend).to_matrix() @ axes.transposed()).to_quaternion()
    pose_bone = rig_object.pose.bones[finger.master]
    pose_bone.location = (0.0, 0.0, 0.0)
    _set_rotation(pose_bone, local)
    if not keep_scale:
        pose_bone.scale = (pose_bone.scale[0],
                           1.0 - curl * calibration["joint_degrees"] / 180.0,
                           pose_bone.scale[2])
    for name in finger.segments:
        pose_writing.to_rest(rig_object.pose.bones[name])


# ----------------------------------------------------------------------
# What both commands answer


def refusal(resolved, body_parts, argument, not_done=""):
    """The first refusal FR 047 adds to FR 041's, in ``resolved``'s shape, or ``None``.

    A rig that is not generated from MPFB's own meta-rigs (``rig_not_supported``,
    naming ``mpfb_set_pose_bones`` as that rig's way to pose fingers), then a
    ``body_parts`` naming anything but a hand. One sentence for both commands,
    because both fall back to the same tool. ``not_done`` finishes it for a
    command that would have changed something.
    """
    identified = resolved["rig_identified_as"]
    refused: dict = dict(resolved)
    if identified not in SUPPORTED_RIGS:
        refused.update(
            blocked_by="rig_not_supported",
            extra={"supported_rigs": list(SUPPORTED_RIGS)},
            message="The rig '{:s}' is '{!s}', and the hand-shape tools work only on a rig "
                    "generated from MPFB's Rigify meta-rigs ({:s}){:s}. Pose this rig's fingers "
                    "with mpfb_set_pose_bones; mpfb_get_pose_controls lists them.".format(
                        resolved["rig"].name, identified, ", ".join(SUPPORTED_RIGS), not_done))
        return refused
    unknown = [part for part in body_parts or () if part not in HANDS]
    if unknown:
        refused.update(
            blocked_by="unknown_body_parts",
            extra={"unknown_body_parts": unknown, "known_body_parts": list(HANDS)},
            message="{:s} names {:s}, which {:s} not a hand{:s}. The hands are: {:s}.".format(
                argument, ", ".join(repr(part) for part in unknown),
                "is" if len(unknown) == 1 else "are", not_done, ", ".join(HANDS)))
        return refused
    return None


def hand_entry(rig_object, found, readings):
    """One hand as both commands report it: its fingers, the shape it is in, and what is off.

    ``fingers`` is keyed by the fingers the hand has, which is how an answer
    lists them; one the rig has but cannot be read is in ``finger_errors``.
    ``found`` is one hand of :func:`find_hands`; ``readings`` its fingers'
    :func:`read_finger` readings. ``settings_off_default`` is ``get_pose``'s
    reading of the masters' ``finger_curve``, which neither command writes.
    """
    pose_bones = rig_object.pose.bones
    masters = {finger.master: {"settings": [key for key in pose_bones[finger.master].keys()
                                            if key == "finger_curve"]}
               for finger in found["fingers"].values()}
    return {
        "fingers": {name: finger_entry(reading) for name, reading in readings.items()},
        "matches_shape": matching_shape(readings),
        "palm_off_rest": any(pose_reading.off_rest(pose_bones[name])
                             for name in found["palm_controls"]),
        "settings_off_default": pose_reading.settings_off_default(rig_object, masters),
        "finger_errors": dict(found["errors"]),
    }
