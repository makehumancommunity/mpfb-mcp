"""
Which rig moves a character, what kind of rig it is, and what each of its bones is for.

**One classification, read by both posing commands.** ``get_pose_controls``
lists what can be moved and ``get_pose`` labels what has been; per
[a summary is never a second opinion](../../../specifications/responses.md#a-summary-is-never-a-second-opinion)
the two must not classify separately, or a bone could be ``left_hand`` in one
answer and nothing in the other. The transform tool
([FR 042](../../../feature-requests/042-posing-bones-switches-and-reset/README.md))
reads it too, to decide which bones are in charge.

**The vocabulary is for an agent, not a rigger.** A bone is labelled with a
``body_part`` (:data:`BODY_PARTS`), a ``role`` (:data:`ROLES`), a ``chain``
(``"ik"``, ``"fk"`` or ``None``, for a limb only) and a ``source``
(``"rigify"``, ``"rig"`` or ``"mpfb_helper"``). ``Arm.L (IK)`` and ``MCH-``
never appear; the Rigify and MPFB names appear only as the bone's own name,
which is what a caller passes back.

**Three families are classified, every other rig is not**
([FR 041](../../../feature-requests/done/041-pose-controls-and-read-back/README.md),
requirement 5). A wrong ``left_hand`` is worse than none, so an unrecognised rig
gets ``classified: false`` and its bones as a plain hierarchy - never a guess.

- **Generated Rigify with bone collections** (``rigify_generated.human`` and
  ``.human_toes``) is read from the live armature, not from a table. Body part
  and chain come from the collections MPFB's meta-rig defines and Rigify
  carries through: ``Arm.L (IK)`` is the left arm's IK chain, ``Fingers`` the
  hands, the side taken from the bone. The parenthesised qualifiers Rigify
  hides - ``(Tweak)``, ``(Detail)``, ``(Primary)``, ``(Secondary)`` - are what
  ``hidden_by_default`` reports; the meta-rig MPFB adds has exactly those
  collections invisible, which the bridge test checks. Three refinements are
  made by name, because the collections lump them where an agent would not look:
  ``neck`` and ``head`` (and their direct children) are the ``head``, not the
  ``torso``; ``shoulder.L`` is the left arm, as the default rig's clavicle is;
  and the eye target and the eyes are the ``head``'s ``look_target``, not the
  face's, since where a character looks is posing rather than expression.
- **A generated ``game_engine`` rig has no such collections.** MPFB's legacy
  convert-to-Rigify workflow generates every control into one collection,
  ``Bones``, with ``_l``/``_r`` sides (established live during FR 041, which is
  what its "do collections and suffixes suffice" question was for: they do
  not). Its body parts come from :data:`_GAME_ENGINE_BODY_PARTS`, keyed on the
  meta-rig bone a control is named for - the names in MPFB's
  ``rig.game_engine.json`` - and nothing is hidden by default, because Rigify
  hid nothing.
- **The default rig** (``default``, ``default_no_toes``) has one collection,
  ``Bones``, so it is classified from :data:`_DEFAULT_TABLE`: the arm, leg and
  finger chains MPFB's ``Default*Helpers`` name, plus the spine, neck and head.
  Everything else below ``head`` is the face. The bridge code may not import
  those helper modules, so ``bbb_shared/pose_controls_test.py`` checks the
  table against them, as ``tests/test_reference_drift.py`` checks the vendored
  URL table: a bone MPFB renames fails a test rather than silently
  unclassifying a limb.

**Roles on Rigify come from Rigify's own naming**, which is the same on both
generated families: ``_fk``, ``_tweak``/``tweak_``, ``_master``, ``_parent``
(the bone carrying a limb's switches), ``_ik_target`` (a pole). Which ``_ik``
bone is a limb's IK control and which is its pole are read off the switches
themselves: Rigify describes ``IK_parent`` as ``"Switch parent of hand_ik.L"``
and ``pole_parent`` likewise, which names the bone exactly and on both families.

**MPFB's helpers on a default rig are detected two ways and the two are
compared.** The modes MPFB records on the armature - ``arm_mode``, ``leg_mode``,
``finger_mode``, ``eye_mode``, through ``RigHelpersProperties`` read via
:mod:`mpfb_surface` - say what was installed; the bones say what is there. A
mode whose bones are missing is reported (``helpers_missing``), not resolved
silently. Which FK bones a helper drives is read off the constraints, never
tabulated: a bone is ``driven_by`` a helper when one of its constraints targets
it, or when it lies inside the chain of an IK constraint that does.

**Rest positions never need edit mode**: everything here reads ``bone`` data
(``matrix_local``, ``head_local``), not edit bones, and changes nothing.

:func:`find_rig` takes ``services`` first, like the rest of this directory,
because it asks ``RigService.identify_rig()`` and ``ObjectService`` about the
character. :func:`classify` takes MPFB's root package name instead, for the one
thing it reads out of MPFB: ``RigHelpersProperties`` lives on a UI module, not
on a service's (:func:`mpfb_surface.rig_helpers_properties`).
"""

__all__ = (
    "BODY_PARTS",
    "CLASSIFIED_RIGS",
    "DEFAULT_BODY_PARTS",
    "ROLES",
    "classify",
    "find_rig",
    "requested_body_parts",
    "resolve_posing_subject",
    "side_of",
    "unknown_body_parts",
)

import re

from . import mpfb_surface
from . import subject_resolution

# ----------------------------------------------------------------------
# Vocabulary

BODY_PARTS = (
    "root", "torso", "head", "face",
    "left_arm", "right_arm", "left_hand", "right_hand", "left_leg", "right_leg",
)

# Every body part but the face, which a generated Rigify rig has hundreds of
# controls for and which MPFB characters express with shape keys instead.
DEFAULT_BODY_PARTS = tuple(part for part in BODY_PARTS if part != "face")

ROLES = (
    "root",            # the bone everything hangs from; moves the whole character
    "body",            # Rigify's torso, hips and chest controls
    "fk",              # rotated directly, one segment of the body
    "ik_control",      # an IK target: where a hand or foot (or a helper's joint) should be
    "pole",            # aims the middle joint of a limb: the elbow or the knee
    "ik_chain",        # the first bone of a Rigify IK chain; twists the limb about its axis
    "foot_roll",       # Rigify's heel, spin and toe controls on an IK foot
    "switches",        # carries a limb's switches; every channel is locked
    "finger_master",   # bends a whole finger (or all of them) at once
    "finger_segment",  # one segment of one finger
    "toe_master",      # bends a whole toe at once
    "toe_segment",     # one segment of one toe
    "tweak",           # a fine adjustment on top of the IK/FK result; hidden by default
    "look_target",     # where the eyes look, or an eye itself
    "face_control",    # anything in the face
)

# What identify_rig() answers, mapped to how the rig is classified.
_RIGIFY = "rigify"
_RIGIFY_GAME_ENGINE = "rigify_game_engine"
_DEFAULT = "default"

CLASSIFIED_RIGS = {
    "rigify_generated.human": _RIGIFY,
    "rigify_generated.human_toes": _RIGIFY,
    "rigify_generated.game_engine": _RIGIFY_GAME_ENGINE,
    "default": _DEFAULT,
    "default_no_toes": _DEFAULT,
}

# A bone with one of these prefixes is never a control on a generated rig.
# VIS_ bones draw the line to a pole and cannot be selected.
_RIGIFY_INTERNAL_PREFIXES = ("DEF-", "MCH-", "ORG-", "VIS_")

# ----------------------------------------------------------------------
# Sides

_COPY_SUFFIX = re.compile(r"\.\d{3,}$")
_SIDE_SUFFIX = re.compile(r"(?:[._\- ])(L|R|l|r)$")
_SIDE_PREFIX = re.compile(r"^(left|right)_")


def _without_copy_suffix(name):
    return _COPY_SUFFIX.sub("", name)


def side_of(name):
    """``"left"``, ``"right"`` or ``None``, from Blender's naming conventions.

    ``hand_ik.L``, ``hand_ik_l``, ``f_index.01.L.001`` (a numbered copy) and
    MPFB's helper ``left_hand_ik`` are all on the left.
    """
    base = _without_copy_suffix(name)
    match = _SIDE_SUFFIX.search(base)
    if match:
        return "left" if match.group(1) in ("L", "l") else "right"
    match = _SIDE_PREFIX.match(base)
    if match:
        return match.group(1)
    return None


def _unsided(name):
    """The name with its numbered-copy suffix and its side removed."""
    base = _without_copy_suffix(name)
    base = _SIDE_SUFFIX.sub("", base)
    return _SIDE_PREFIX.sub("", base)


def _sided_part(kind, side):
    """``"arm"`` and ``"left"`` as ``"left_arm"``, or ``None`` without a side."""
    if side is None:
        return None
    return "{:s}_{:s}".format(side, kind)


# ----------------------------------------------------------------------
# Finding the rig


def find_rig(services, basemesh):
    """The armature that moves ``basemesh``, what MPFB identifies it as, and any meta-rig.

    **The rig is the armature the basemesh's armature modifier points at**, so
    a character carrying both a meta-rig and the rig generated from it is
    answered about the one that actually moves the body. Returns
    ``(rig_object, rig_identified_as, metarig)``: ``metarig`` is set when the
    rig that moves the body *is* a Rigify meta-rig, or when there is none and a
    meta-rig is among the character's relatives - posing a meta-rig is always a
    mistake, and the caller refuses it.
    """
    rig_service = services["RigService"]
    for modifier in basemesh.modifiers:
        target = getattr(modifier, "object", None)
        if modifier.type == "ARMATURE" and target is not None and target.type == "ARMATURE":
            identified = rig_service.identify_rig(target)
            if _is_metarig(identified):
                return (None, identified, target)
            return (target, identified, None)
    for skeleton in services["ObjectService"].find_all_objects_of_type_amongst_nearest_relatives(
            basemesh, "Skeleton"):
        if skeleton.type == "ARMATURE":
            identified = rig_service.identify_rig(skeleton)
            if _is_metarig(identified):
                return (None, identified, skeleton)
    return (None, None, None)


def _is_metarig(identified):
    return bool(identified) and identified.startswith("rigify.")


def requested_body_parts(body_parts):
    """The body parts a call asked for, in :data:`BODY_PARTS` order; ``None`` is the default."""
    if body_parts is None:
        return DEFAULT_BODY_PARTS
    return tuple(part for part in BODY_PARTS if part in body_parts)


def unknown_body_parts(body_parts):
    """Whatever in ``body_parts`` is not a body part, as given, in order."""
    if body_parts is None:
        return []
    return [part for part in body_parts if not isinstance(part, str) or part not in BODY_PARTS]


def _so(not_done):
    return "" if not_done is None else ", so {:s}".format(not_done)


def resolve_posing_subject(services, requested_name, body_parts, not_done=None):
    """The character, its rig and the first refusal that applies, as one dict.

    **One implementation for every posing command**, because FR 042's writers
    take "subject, rig and refusals" from FR 041 by name, and a writer that
    refused a meta-rig the readers listed would be the contradiction a shared
    module exists to prevent. Like :mod:`subject_resolution` it raises nothing
    and the command builds its own answer from what comes back: ``blocked_by``
    is ``None`` when the command may go ahead, and otherwise one of
    ``subject_not_found``, ``rigify_not_generated``, ``rig_not_found`` and
    ``unknown_body_parts``, in that order, with ``message`` saying which tool
    fixes it. ``not_done`` finishes a refusal's sentence for a command that
    would have changed something, as in :mod:`subject_resolution`.

    ``extra`` holds what each refusal names beyond the subject:
    ``metarig_name``, or ``unknown_body_parts`` with ``known_body_parts``.
    """
    answer = {"basemesh": None, "subject": None, "resolved_by": None, "rig": None,
              "rig_identified_as": None, "blocked_by": None, "message": None, "extra": {}}
    basemesh, subject, resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name, not_a_character="it has no rig to pose", not_done=not_done)
    answer.update(basemesh=basemesh, subject=subject, resolved_by=resolved_by)
    if basemesh is None:
        answer.update(blocked_by="subject_not_found", message=message)
        return answer
    rig, identified, metarig = find_rig(services, basemesh)
    answer.update(rig=rig, rig_identified_as=identified)
    if metarig is not None:
        answer.update(
            blocked_by="rigify_not_generated",
            message="'{:s}' is rigged with the Rigify meta-rig '{:s}' ({:s}), which is a "
                    "template for generating a rig rather than a rig to pose{:s}. Call "
                    "mpfb_generate_rigify_rig first, then pose the rig it generates.".format(
                        basemesh.name, metarig.name, identified, _so(not_done)),
            extra={"metarig_name": metarig.name})
        return answer
    if rig is None:
        answer.update(
            blocked_by="rig_not_found",
            message="'{:s}' has no rig: no armature modifier on the basemesh points at an "
                    "armature{:s}. Add one with mpfb_add_rig.".format(
                        basemesh.name, _so(not_done)))
        return answer
    unknown = unknown_body_parts(body_parts)
    if unknown:
        answer.update(
            blocked_by="unknown_body_parts",
            message="body_parts names {:s}, which {:s} not a body part{:s}. The body parts "
                    "are: {:s}.".format(", ".join(repr(part) for part in unknown),
                                        "is" if len(unknown) == 1 else "are", _so(not_done),
                                        ", ".join(BODY_PARTS)),
            extra={"unknown_body_parts": unknown, "known_body_parts": list(BODY_PARTS)})
    return answer


# ----------------------------------------------------------------------
# Rigify, read off collections


_COLLECTION_NAME = re.compile(r"^(?P<base>.+?)(?: \((?P<qualifier>[^)]+)\))?$")
_HIDDEN_QUALIFIERS = ("Tweak", "Detail", "Primary", "Secondary")
_LOOK_TARGETS = ("eye_common", "eye")


def _collection_reading(bone):
    """``(kind, side, chain, hidden, base)`` from the first collection that says anything.

    ``kind`` is ``"root"``, ``"torso"``, ``"face"``, ``"hand"``, ``"toes"``,
    ``"arm"`` or ``"leg"``; ``side`` comes from the collection when it names one
    (``Arm.L``) and is otherwise ``None``.
    """
    for collection in bone.collections:
        match = _COLLECTION_NAME.match(collection.name)
        if not match:
            continue
        base = match.group("base")
        qualifier = match.group("qualifier")
        chain = {"IK": "ik", "FK": "fk"}.get(qualifier)
        hidden = qualifier in _HIDDEN_QUALIFIERS
        simple = {"Root": "root", "Torso": "torso", "Face": "face",
                  "Fingers": "hand", "Toes": "toes"}.get(base)
        if simple is not None:
            return (simple, None, chain, hidden, base)
        limb = re.match(r"^(Arm|Leg)\.(L|R)$", base)
        if limb:
            return (limb.group(1).lower(), "left" if limb.group(2) == "L" else "right",
                    chain, hidden, base)
    return (None, None, None, False, None)


def _rigify_collection_body_part(bone):
    """``(body_part, chain, hidden_by_default)`` for one control on a collections rig."""
    kind, side, chain, hidden, _base = _collection_reading(bone)
    name = _unsided(bone.name)
    side = side or side_of(bone.name)
    if kind is None:
        return (None, None, False)
    if kind == "torso":
        parent = bone.parent.name if bone.parent is not None else None
        if name in ("neck", "head") or parent in ("neck", "head"):
            return ("head", None, hidden)
        if name == "shoulder":
            return (_sided_part("arm", side), None, hidden)
        return ("torso", None, hidden)
    if kind == "face":
        if name in _LOOK_TARGETS:
            return ("head", None, hidden)
        return ("face", None, hidden)
    if kind == "hand":
        return (_sided_part("hand", side), None, hidden)
    if kind == "toes":
        return (_sided_part("leg", side), None, hidden)
    if kind in ("arm", "leg"):
        return (_sided_part(kind, side), chain, hidden)
    return (kind, None, hidden)


# The meta-rig bone a game_engine control is named for, by its first word, and
# the body part it belongs to. These are MPFB's own names, from
# data/rigs/standard/rig.game_engine.json, as Rigify carries them through:
# upperarm_fk_l, tweak_spine_03, index_01_master_l, foot_heel_ik_l.
_GAME_ENGINE_BODY_PARTS = {
    "root": "root",
    "torso": "torso", "hips": "torso", "chest": "torso",
    "pelvis": "torso", "spine": "torso", "breast": "torso",
    "neck": "head", "head": "head",
    "clavicle": "arm", "upperarm": "arm", "lowerarm": "arm", "hand": "arm",
    "thumb": "hand", "index": "hand", "middle": "hand", "ring": "hand", "pinky": "hand",
    "thigh": "leg", "calf": "leg", "foot": "leg", "ball": "leg",
}


def _game_engine_body_part(bone):
    """``(body_part, chain, hidden_by_default)`` for one control on a game_engine rig."""
    name = _unsided(bone.name)
    if name.startswith("tweak_"):
        name = name[len("tweak_"):]
    kind = _GAME_ENGINE_BODY_PARTS.get(name.split("_")[0])
    if kind in ("arm", "hand", "leg"):
        kind = _sided_part(kind, side_of(bone.name))
    chain = None
    if kind is not None and kind.endswith(("_arm", "_leg")):
        if "_fk" in name:
            chain = "fk"
        elif "_ik" in name:
            chain = "ik"
    return (kind, chain, False)


def _switch_targets(pose_bones):
    """The bones Rigify names as a limb's IK control and pole, from the switches' own text.

    Rigify writes ``description=f"Switch parent of {ctrl_bone}"`` for
    ``IK_parent`` and ``pole_parent``. Returns ``(ik_controls, poles)``, each a
    dict from the controlled bone to the bone carrying the switch.
    """
    ik_controls = {}
    poles = {}
    for pose_bone in pose_bones:
        for prop, found in (("IK_parent", ik_controls), ("pole_parent", poles)):
            if prop not in pose_bone.keys():
                continue
            description = _property_ui(pose_bone, prop).get("description") or ""
            match = re.match(r"^Switch parent of (.+)$", str(description))
            if match and match.group(1) in pose_bones:
                found[match.group(1)] = pose_bone.name
    return (ik_controls, poles)


def _rigify_role(name, body_part, pose_bone, ik_controls, poles):
    """One generated Rigify control's role, from Rigify's naming conventions."""
    # pylint: disable=too-many-return-statements
    base = _unsided(name)
    if base == "root":
        return "root"
    if base in ("torso", "hips", "chest"):
        return "body"
    if body_part == "head" and base in _LOOK_TARGETS:
        return "look_target"
    if name in ik_controls:
        return "ik_control"
    if name in poles or base.endswith("_ik_target"):
        return "pole"
    if base.endswith("_parent") and "IK_FK" in pose_bone.keys():
        return "switches"
    if "tweak" in base:
        return "tweak"
    if base.endswith("_ik"):
        if "heel" in base or "spin" in base or base.startswith("toe"):
            return "foot_roll"
        return "ik_chain"
    if base.endswith("_master"):
        if body_part in ("left_hand", "right_hand"):
            return "finger_master"
        if body_part in ("left_leg", "right_leg"):
            return "toe_master"
    if base.endswith("_fk"):
        return "fk"
    return _fallback_role(body_part, base)


def _fallback_role(body_part, base):
    if body_part == "face":
        return "face_control"
    if body_part in ("left_hand", "right_hand") and not base.startswith("palm"):
        return "finger_segment"
    if body_part in ("left_leg", "right_leg") and base.startswith("toe"):
        return "toe_segment"
    return "fk"


# ----------------------------------------------------------------------
# The default rig, from a table


# Three segments per finger; the big toe has two and the others three, as on
# the rig itself.
_FINGER_SEGMENTS = tuple("finger{:d}-{:d}".format(finger, segment)
                         for finger in range(1, 6) for segment in range(1, 4))
_TOE_SEGMENTS = ("toe1-1", "toe1-2") + tuple("toe{:d}-{:d}".format(toe, segment)
                                             for toe in range(2, 6) for segment in range(1, 4))


# Unsided name -> (kind, role). A kind of "arm", "hand" or "leg" is sided by the
# bone's own ".L"/".R". These are the bones MPFB's DefaultArmHelpers,
# DefaultLegHelpers and DefaultFingerHelpers name, plus the spine, neck and head;
# bbb_shared/pose_controls_test.py checks the three chains against them.
_DEFAULT_TABLE = {}
_DEFAULT_TABLE.update({"root": ("root", "root")})
_DEFAULT_TABLE.update({name: ("torso", "fk") for name in (
    "spine05", "spine04", "spine03", "spine02", "spine01", "breast")})
_DEFAULT_TABLE.update({name: ("head", "fk") for name in ("neck01", "neck02", "neck03", "head")})
_DEFAULT_TABLE.update({"eye": ("head", "look_target")})
_DEFAULT_TABLE.update({name: ("arm", "fk") for name in (
    "clavicle", "shoulder01", "upperarm01", "upperarm02", "lowerarm01", "lowerarm02", "wrist")})
_DEFAULT_TABLE.update({name: ("hand", "fk") for name in (
    "metacarpal1", "metacarpal2", "metacarpal3", "metacarpal4")})
_DEFAULT_TABLE.update({name: ("hand", "finger_segment")
                       for name in _FINGER_SEGMENTS})
_DEFAULT_TABLE.update({name: ("leg", "fk") for name in (
    "pelvis", "upperleg01", "upperleg02", "lowerleg01", "lowerleg02", "foot")})
_DEFAULT_TABLE.update({name: ("leg", "toe_segment") for name in _TOE_SEGMENTS})

# MPFB's helper bones, by unsided name, and what each is. The side is the
# "left_"/"right_" prefix MPFB gives them; eye_ik has none.
_DEFAULT_HELPERS = {
    "hand_ik": ("arm", "ik_control"),
    "elbow_ik": ("arm", "pole"),
    "shoulder_ik": ("arm", "ik_control"),
    "foot_ik": ("leg", "ik_control"),
    "knee_ik": ("leg", "pole"),
    "hip_ik": ("leg", "ik_control"),
    "master_grip": ("hand", "finger_master"),
    "eye_ik": ("head", "look_target"),
}
_DEFAULT_HELPERS.update({"finger{:d}_grip".format(n): ("hand", "finger_master")
                         for n in range(1, 6)})
_DEFAULT_HELPERS.update({"finger{:d}_point_ik".format(n): ("hand", "ik_control")
                         for n in range(1, 6)})

# Which helper bones each recorded mode installs, per side (eyes: once). From
# the _apply_* methods of MPFB's ArmHelpers, LegHelpers, FingerHelpers and
# EyeHelpers.
HELPER_MODES = ("arm_mode", "leg_mode", "finger_mode", "eye_mode")
_HELPERS_BY_MODE = {
    "arm_mode": {
        "LOWERUPPER": ("hand_ik", "elbow_ik"),
        "LOWERUPPERSHOULDER": ("hand_ik", "elbow_ik", "shoulder_ik"),
        "ARMCHAIN": ("hand_ik",),
        "SHOULDERCHAIN": ("hand_ik",),
    },
    "leg_mode": {
        "LOWERUPPER": ("foot_ik", "knee_ik"),
        "LOWERUPPERHIP": ("foot_ik", "knee_ik", "hip_ik"),
    },
    "finger_mode": {
        "POINT": tuple("finger{:d}_point_ik".format(n) for n in range(1, 6)),
        "GRIP": tuple("finger{:d}_grip".format(n) for n in range(1, 6)),
        "MASTER": ("master_grip",),
        "GRIP_AND_MASTER": tuple("finger{:d}_grip".format(n) for n in range(1, 6))
                           + ("master_grip",),
    },
}
_EYE_HELPERS = ("eye_ik", "left_eye_ik", "right_eye_ik")


def _default_helper(name):
    """``(kind, role)`` for an MPFB helper bone, or ``None``."""
    if name in ("left_eye_ik", "right_eye_ik"):
        return ("head", "look_target")
    return _DEFAULT_HELPERS.get(_SIDE_PREFIX.sub("", name))


def _descends_from(bone, ancestor_name):
    parent = bone.parent
    while parent is not None:
        if parent.name == ancestor_name:
            return True
        parent = parent.parent
    return False


def _default_reading(bone):
    """``(body_part, role, chain, source)`` for one default-rig bone, or ``None``."""
    side = side_of(bone.name)
    helper = _default_helper(bone.name)
    if helper is not None:
        kind, role = helper
        part = _sided_part(kind, side) if kind in ("arm", "hand", "leg") else kind
        chain = "ik" if kind in ("arm", "leg") else None
        return (part, role, chain, "mpfb_helper")
    entry = _DEFAULT_TABLE.get(_unsided(bone.name))
    if entry is not None:
        kind, role = entry
        part = _sided_part(kind, side) if kind in ("arm", "hand", "leg") else kind
        # The bones MPFB's arm and leg helpers take over; toes and fingers are
        # not in a limb's chain.
        chain = "fk" if kind in ("arm", "leg") and role == "fk" else None
        return (part, role, chain, "rig")
    if _descends_from(bone, "head"):
        return ("face", "face_control", None, "rig")
    return None


def _helper_modes(root_name, rig_object):
    """The four recorded modes (``"NONE"`` when unset), or ``None`` and why not."""
    config_set = mpfb_surface.rig_helpers_properties(root_name)
    if config_set is None:
        return (None, "MPFB's RigHelpersProperties could not be read (its standard rig UI "
                      "module is not loaded), so the helper modes are unknown. The helper "
                      "bones are still recognised by name.")
    modes = {}
    for mode in HELPER_MODES:
        value = mpfb_surface.property_value(config_set, mode, rig_object)
        modes[mode] = value.strip() if value and value.strip() else "NONE"
    return (modes, None)


def _helpers_missing(modes, bone_names):
    """Helper bones a recorded mode says are installed and the armature does not have."""
    missing = []
    if modes is None:
        return missing
    for mode in ("arm_mode", "leg_mode", "finger_mode"):
        for unsided in _HELPERS_BY_MODE[mode].get(modes[mode], ()):
            for side in ("left", "right"):
                name = "{:s}_{:s}".format(side, unsided)
                if name not in bone_names:
                    missing.append(name)
    if modes["eye_mode"] not in ("NONE", ""):
        missing.extend(name for name in _EYE_HELPERS if name not in bone_names)
    return missing


def _driven_by(pose_bones, helpers):
    """Each FK bone a helper drives, and which helpers drive it.

    Read off the constraints rather than tabulated: a constraint that targets a
    helper drives its own bone, and an IK constraint drives every bone in its
    chain as well (``chain_count`` bones up from the constrained one, or the
    whole parent chain when it is 0).
    """
    driven = {}

    def mark(bone_name, helper_name):
        names = driven.setdefault(bone_name, [])
        if helper_name not in names:
            names.append(helper_name)

    for pose_bone in pose_bones:
        for constraint in pose_bone.constraints:
            subtarget = getattr(constraint, "subtarget", "")
            if subtarget not in helpers or constraint.mute or constraint.influence <= 0.0:
                continue
            mark(pose_bone.name, subtarget)
            if constraint.type == "IK":
                remaining = constraint.chain_count - 1 if constraint.chain_count else -1
                parent = pose_bone.parent
                while parent is not None and remaining != 0:
                    mark(parent.name, subtarget)
                    parent = parent.parent
                    remaining -= 1
    return driven


# ----------------------------------------------------------------------
# Switches


def _property_ui(pose_bone, prop):
    try:
        return pose_bone.id_properties_ui(prop).as_dict()
    except (TypeError, KeyError, AttributeError):
        return {}


# What each end of a known switch's range means. Rigify's own description says
# what a property is ("IK/FK Switch"), never which end is which, and an agent
# setting IK_FK needs to know that 0.0 is IK. Read from Rigify's source:
# limb_rigs.py for the limb switches, where FK_limb_follow drives a
# copy-rotation of root at influence = value; spine_rigs.py for the follow
# switches, where the influence is 1 - value, which is why their ends read the
# other way round.
SWITCH_ENDS = {
    "IK_FK": ("IK: the IK controls move the limb", "FK: the FK controls move the limb"),
    "IK_Stretch": ("the IK chain never grows past its rest length",
                   "the IK chain stretches to reach its IK control"),
    "pole_vector": ("no pole: the elbow or knee is aimed by twisting the IK chain's first bone",
                    "the pole control aims the elbow or knee"),
    "FK_limb_follow": ("the FK limb turns with the body",
                       "the FK limb keeps its orientation relative to the root bone"),
    "neck_follow": ("the neck keeps its orientation relative to the root bone",
                    "the neck turns with the chest"),
    "head_follow": ("the head keeps its orientation relative to the root bone",
                    "the head turns with the neck"),
    "mouth_lock": ("the mouth opens with the jaw", "the mouth stays closed when the jaw opens"),
}


def _value_kind(value, ui):
    if isinstance(value, bool):
        return "bool"
    if "items" in ui:
        return "parent"
    if isinstance(value, int):
        return "int"
    return "float"


def _switch_record(body_part, pose_bone, prop):
    """One switch, as ``get_pose_controls`` lists it."""
    value = pose_bone[prop]
    ui = _property_ui(pose_bone, prop)
    kind = _value_kind(value, ui)
    record = {
        "body_part": body_part,
        "switch": prop,
        "bone": pose_bone.name,
        "type": kind,
        "default": ui.get("default"),
        "description": ui.get("description"),
    }
    if kind == "bool":
        record["range"] = [False, True]
    elif kind == "parent":
        items = ui.get("items") or []
        record["range"] = [0, max(len(items) - 1, 0)]
    else:
        record["range"] = [ui.get("min"), ui.get("max")]
    ends = SWITCH_ENDS.get(prop)
    record["ends"] = list(ends) if ends else None
    if kind == "parent":
        names = [str(item[1]) for item in (ui.get("items") or [])]
        record["parent_names"] = names or None
        if not names:
            record["parent_names_reason"] = (
                "The property carries no list of its parents, which Rigify has written beside "
                "every parent switch since it moved into Blender's core add-ons. This rig was "
                "probably generated by an older Rigify; the parents are listed only in its "
                "rig_ui.py script, which this tool does not read.")
    else:
        record["parent_names"] = None
    return record


def _switchable(pose_bone, prop):
    if prop.startswith("_") or prop.startswith("rigify"):
        return False
    value = pose_bone[prop]
    return isinstance(value, (bool, int, float))


def _collect_switches(rig_object, controls):
    """``(switches, settings)``: one switch per body part and name, and the per-bone rest.

    FR 042 addresses a switch by ``body_part`` and ``switch``, so a property
    name that occurs on several controls of one body part - ``finger_curve`` on
    every finger master, ``rubber_tweak`` on every tweak, ``lid_follow`` on both
    eyes - cannot be a switch: it is a setting of each control instead, and is
    reported on the control.
    """
    occurrences = {}
    for name, control in controls.items():
        pose_bone = rig_object.pose.bones[name]
        for prop in pose_bone.keys():
            if _switchable(pose_bone, prop) and control["body_part"] is not None:
                occurrences.setdefault((control["body_part"], prop), []).append(name)
    switches = []
    settings = {}
    for (body_part, prop), names in occurrences.items():
        if len(names) == 1:
            switches.append(_switch_record(body_part, rig_object.pose.bones[names[0]], prop))
        else:
            for name in names:
                settings.setdefault(name, []).append(prop)
    switches.sort(key=lambda record: (BODY_PARTS.index(record["body_part"]), record["switch"]))
    return (switches, settings)


# ----------------------------------------------------------------------
# Limbs and landmarks


# The deforming bone that stands for the hips and the head, per family. Hands
# and feet come from each limb's own chain instead. Checked by the bridge tests
# against freshly built rigs of each family.
_LANDMARK_BONES = {
    _RIGIFY: {"hips": "DEF-spine", "head": "DEF-spine.006"},
    _RIGIFY_GAME_ENGINE: {"hips": "DEF-pelvis", "head": "DEF-head"},
    _DEFAULT: {"hips": "spine05", "head": "head"},
}

# The default rig's limbs: the deforming segments root to tip, then the tip.
# These are DefaultArmHelpers' and DefaultLegHelpers' chains without the
# shoulder and the hip, which is what "the chain" means for reach.
_DEFAULT_LIMBS = {
    "arm": (("upperarm01", "upperarm02", "lowerarm01", "lowerarm02"), "wrist",
            "hand_ik", "elbow_ik"),
    "leg": (("upperleg01", "upperleg02", "lowerleg01", "lowerleg02"), "foot",
            "foot_ik", "knee_ik"),
}

def _rigify_limbs(rig_object, controls):
    """Each limb of a generated Rigify rig, read off its FK controls and switches.

    The FK controls name the limb's original bones: ``upper_arm_fk.L`` is
    ``ORG-upper_arm.L``, ``upperarm_fk_l`` is ``ORG-upperarm_l``. Ordered by
    their depth in the ORG hierarchy, the first two are the chain whose reach is
    measured and the third is its tip; their deforming bones are ``DEF-`` plus
    the same name, and Rigify's numbered segments (``DEF-upper_arm.L.001``).
    """
    bones = rig_object.data.bones
    limbs = {}
    for part in ("left_arm", "right_arm", "left_leg", "right_leg"):
        members = [name for name, control in controls.items() if control["body_part"] == part]
        switch = next((name for name in members if controls[name]["role"] == "switches"), None)
        ik_control = next((name for name in members if controls[name]["role"] == "ik_control"),
                          None)
        pole = next((name for name in members if controls[name]["role"] == "pole"), None)
        orgs = []
        for name in members:
            if controls[name]["role"] != "fk" or controls[name]["chain"] != "fk":
                continue
            org = "ORG-" + name.replace("_fk", "", 1)
            if org in bones:
                orgs.append(org)
        orgs.sort(key=lambda org: _depth(bones[org]))
        segments = []
        for org in orgs[:2]:
            stem = "DEF-" + org[len("ORG-"):]
            segments.extend(sorted(bone.name for bone in bones
                                   if bone.name == stem or bone.name.startswith(stem + ".")))
        tip = None
        if len(orgs) >= 3 and "DEF-" + orgs[2][len("ORG-"):] in bones:
            tip = "DEF-" + orgs[2][len("ORG-"):]
        limbs[part] = {
            "switch_bone": switch,
            "ik_control": ik_control,
            "pole": pole,
            "segments": [name for name in segments if bones[name].use_deform],
            "tip": tip,
        }
    return limbs


def _depth(bone):
    depth = 0
    while bone.parent is not None:
        depth += 1
        bone = bone.parent
    return depth


def _default_limbs(rig_object):
    bones = rig_object.data.bones
    limbs = {}
    for side, suffix in (("left", ".L"), ("right", ".R")):
        for kind, (segments, tip, ik_control, pole) in _DEFAULT_LIMBS.items():
            ik_name = "{:s}_{:s}".format(side, ik_control)
            pole_name = "{:s}_{:s}".format(side, pole)
            limbs["{:s}_{:s}".format(side, kind)] = {
                "switch_bone": None,
                "ik_control": ik_name if ik_name in bones else None,
                "pole": pole_name if pole_name in bones else None,
                "segments": [name + suffix for name in segments if name + suffix in bones],
                "tip": tip + suffix if tip + suffix in bones else None,
            }
    return limbs


def _landmarks(family, rig_object, limbs):
    """Landmark name -> the deforming bone whose head is that landmark, or ``None``."""
    bones = rig_object.data.bones
    landmarks = {}
    for name, bone_name in _LANDMARK_BONES[family].items():
        landmarks[name] = bone_name if bone_name in bones else None
    for side in ("left", "right"):
        landmarks[side + "_hand"] = limbs[side + "_arm"]["tip"]
        landmarks[side + "_foot"] = limbs[side + "_leg"]["tip"]
    return landmarks


# ----------------------------------------------------------------------
# The classification


def _control(body_part, role, chain, source, hidden):
    return {"body_part": body_part, "role": role, "chain": chain, "source": source,
            "hidden_by_default": hidden, "driven_by": None, "settings": None}


def _classify_rigify(rig_object, family):
    pose_bones = rig_object.pose.bones
    ik_controls, poles = _switch_targets(pose_bones)
    controls = {}
    unassigned = []
    for bone in rig_object.data.bones:
        if bone.name.startswith(_RIGIFY_INTERNAL_PREFIXES):
            continue
        if family == _RIGIFY:
            body_part, chain, hidden = _rigify_collection_body_part(bone)
        else:
            body_part, chain, hidden = _game_engine_body_part(bone)
        if body_part is None:
            unassigned.append(bone.name)
            continue
        role = _rigify_role(bone.name, body_part, pose_bones[bone.name], ik_controls, poles)
        if role in ("switches",):
            chain = None
        elif role in ("ik_control", "pole", "ik_chain", "foot_roll") and \
                body_part.endswith(("_arm", "_leg")):
            chain = "ik"
        if role == "tweak":
            chain = None
        controls[bone.name] = _control(body_part, role, chain, "rigify", hidden)
    return (controls, unassigned)


def _classify_default(rig_object):
    controls = {}
    unassigned = []
    for bone in rig_object.data.bones:
        reading = _default_reading(bone)
        if reading is None:
            unassigned.append(bone.name)
            continue
        body_part, role, chain, source = reading
        controls[bone.name] = _control(body_part, role, chain, source, False)
    helpers = set(name for name, control in controls.items()
                  if control["source"] == "mpfb_helper")
    for name, helper_names in _driven_by(rig_object.pose.bones, helpers).items():
        if name in controls and name not in helpers:
            controls[name]["driven_by"] = helper_names
    return (controls, unassigned)


def classify(root_name, rig_object, rig_identified_as):
    """Everything both posing commands need to know about one rig, as one dict.

    Keys: ``classified``, ``family`` (``None`` when unclassified),
    ``controls`` (bone name -> its labels, in the armature's bone order),
    ``unassigned`` (bones of a classified rig that fit no body part),
    ``switches`` and ``limbs`` and ``landmarks`` (``None`` for anything but
    Rigify, ``limbs``/``landmarks`` ``None`` when unclassified),
    ``helper_modes``, ``helper_modes_reason`` and ``helpers_missing`` (default
    rig only, otherwise ``None``).
    """
    family = CLASSIFIED_RIGS.get(rig_identified_as)
    answer = {
        "classified": family is not None,
        "family": family,
        "controls": {},
        "unassigned": [],
        "switches": None,
        "limbs": None,
        "landmarks": None,
        "helper_modes": None,
        "helper_modes_reason": None,
        "helpers_missing": None,
    }
    if family is None:
        return answer
    if family == _DEFAULT:
        controls, unassigned = _classify_default(rig_object)
        modes, reason = _helper_modes(root_name, rig_object)
        answer["helper_modes"] = modes
        answer["helper_modes_reason"] = reason
        answer["helpers_missing"] = _helpers_missing(
            modes, set(bone.name for bone in rig_object.data.bones))
        limbs = _default_limbs(rig_object)
        answer["switches"] = []
    else:
        controls, unassigned = _classify_rigify(rig_object, family)
        switches, settings = _collect_switches(rig_object, controls)
        for name, props in settings.items():
            controls[name]["settings"] = sorted(props)
        answer["switches"] = switches
        limbs = _rigify_limbs(rig_object, controls)
    answer["controls"] = controls
    answer["unassigned"] = unassigned
    answer["limbs"] = limbs
    answer["landmarks"] = _landmarks(family, rig_object, limbs)
    return answer
