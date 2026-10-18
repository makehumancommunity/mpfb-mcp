"""
``get_pose_controls``: which bones move a character, what each one does, and where it rests.

The first of the posing commands
([FR 041](../../../feature-requests/done/041-pose-controls-and-read-back/README.md)), and
read-only. An agent posing a character with no prior knowledge of its rig needs
to know which of a generated Rigify rig's 1090 bones are the ones to move, and
this is the answer: the **controls**, grouped by body part, each with a role,
its chain, its rest position and direction in the character frame, how it
rotates and which channels are locked. Everything about *what a bone is* comes
from [`shared/pose_controls.py`](../shared/pose_controls.py) and every position
from [`shared/character_frame.py`](../shared/character_frame.py), which
``get_pose`` and the writing tools read too.

**The rig is the armature the basemesh's armature modifier points at**, so a
character carrying both a meta-rig and the rig generated from it is answered
about the one that moves the body. Two refusals name the tool that fixes them:
``rig_not_found`` (``mpfb_add_rig``) and ``rigify_not_generated``
(``mpfb_generate_rigify_rig``). Listing a meta-rig's bones would make posing it
look supported, and it never is.

**An unclassified rig is answered, never guessed at.** Its bones come back as
a plain hierarchy - name, parent, whether it deforms, rest head and direction,
rotation mode - with ``classified: false`` and ``classified_rigs`` naming what
would be classified, so the caller can decide to switch rigs.

**``body_parts`` defaults to everything but the face.** A generated Rigify
rig has about a hundred face controls, and MPFB characters make expressions
with shape keys instead. Following
[how tools bound a large answer](../../../specifications/responses.md#how-tools-bound-a-large-answer),
``counts_by_body_part`` covers **every** part whatever was asked, so a caller
that never asked for ``face`` can still see that it exists and how large it is,
and ``requested_body_parts`` echoes the filter that was applied. Switches are
filtered with their body part.

**Three narrower cuts go across body parts**
([FR 043](../../../feature-requests/done/043-narrower-pose-controls/README.md)),
because most of a default answer was controls a first pass never touches.
``include_hidden`` (default false) leaves out what ``hidden_by_default`` marks,
which is what Rigify's own UI does; ``roles`` lists only controls of the named
roles; ``compact`` keeps only what names a control and says what it is for. The
filters intersect: naming ``finger_segment`` does not override the hidden
default. Every cut stays visible as a number - ``counts_by_body_part``
(every part, unfiltered), ``counts_by_role`` (the requested parts, before the
role and hidden filters) and ``hidden_by_body_part`` (what passed the role
filter and is hidden) - and every filter is echoed, so no short ``controls``
reads as complete. **Switches follow ``body_parts``, and ``switch_names`` when
the caller names them**, never ``roles`` or ``include_hidden``: an agent placing
``hand_ik.L`` must learn that ``IK_FK`` puts the arm in IK without having
thought to ask for the ``switches`` role, so only a caller that names switches
gets fewer. A compact entry *drops* keys rather
than nulling them, because the caller chose the shape and the echo says which;
``driven_by`` stays on the default rig, since it is what says a rotation will
not last. ``unknown_roles`` is checked here, after
``pose_controls.resolve_posing_subject()``, which the writers share and which
takes no roles.

**``switch_names`` names the rig's switches, not a fixed list**
([FR 044](../../../feature-requests/done/044-switches-filter/README.md)):
``human_toes`` has ``parent_switch`` and ``game_engine`` does not. So
``unknown_switch_names`` can only be checked after ``classify()``, later than
``unknown_roles``, and refuses only a name the rig has nowhere; a name the rig
has outside the requested parts lists nothing and counts 0.
``counts_by_switch`` covers the requested parts before the name filter, keyed
by every switch name the rig has, which makes the filter as discoverable as
``counts_by_role`` makes ``roles``. On a rig with no switches - the default rig,
an unclassified one - the filter is neither applied nor refused, so one call
sent across characters with different rigs fails only for a real mistake. A
compact switch entry drops ``bone`` (reported, never asked for), ``default``
(what a reset puts back) and ``description`` (Rigify's text, which ``ends`` and
``parent_names`` say better), and keeps everything ``mpfb_set_pose_switches``
needs. The filter and the projection live here rather than in
``shared/pose_controls.py``, because ``get_pose`` and the writers read the same
switch records unprojected.

**Switches are listed with what each end means.** Rigify keeps them as custom
properties on hidden-looking bones, and its own description says what a switch
is but never which end is which; ``ends`` says that ``IK_FK`` 0.0 is IK. A
parent switch is an integer, and ``parent_names`` maps each value to the
parent it selects, read live off the property's own ``items`` (Rigify writes
them there as well as into the generated ``rig_ui.py``, which is not read).

**What MPFB's helpers drive is listed and labelled.** On a default rig with an
arm helper, ``lowerarm02.L`` is still a control, ``driven_by`` names
``left_hand_ik``, and rotating it directly does nothing that lasts: the IK
constraint puts it back on the next evaluation.

Changes nothing: reads bone data and custom properties. Rest positions come
from ``bone.matrix_local``, never from edit bones, so no mode is entered.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_pose_controls",
)

from ..log import get_logger
from ..shared import pose_controls
from ..shared.character_frame import Frame
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getposecontrols")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("body_parts", TYPE_ARRAY, default=None, nullable=True,
          description="Which body parts to list, from: {:s}. Omit for every part except "
                      "face.".format(", ".join(pose_controls.BODY_PARTS))),
    Param("roles", TYPE_ARRAY, default=None, nullable=True,
          description="Which roles to list, from: {:s}. Omit for every role.".format(
              ", ".join(pose_controls.ROLES))),
    Param("switch_names", TYPE_ARRAY, default=None, nullable=True,
          description="Which switches to list, by name (IK_FK, IK_parent, ...), from the rig's "
                      "own switches. Omit for every switch of the requested body parts."),
    Param("include_hidden", TYPE_BOOLEAN, default=False,
          description="Also list the controls marked hidden_by_default."),
    Param("compact", TYPE_BOOLEAN, default=False,
          description="List each control by name and labels only, without its rest position, "
                      "rotation mode, locks or settings."),
)

SUMMARY = ("List the controls that pose a character, grouped by body part, with each one's "
           "role and rest position in the character frame.")


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
        message=resolved["message"],
    )
    answer.update(resolved["extra"])
    return answer


def _locked(pose_bone):
    """The locked channels as axis letters, only those that are locked: ``{"rotation": "xz"}``."""
    locked = {}
    location = "".join(axis for axis, lock in zip("xyz", pose_bone.lock_location) if lock)
    rotation = "".join(axis for axis, lock in zip("xyz", pose_bone.lock_rotation) if lock)
    if pose_bone.rotation_mode in ("QUATERNION", "AXIS_ANGLE") and pose_bone.lock_rotation_w \
            and pose_bone.lock_rotations_4d:
        rotation = "w" + rotation
    scale = "".join(axis for axis, lock in zip("xyz", pose_bone.lock_scale) if lock)
    for channel, axes in (("location", location), ("rotation", rotation), ("scale", scale)):
        if axes:
            locked[channel] = axes
    return locked


def _rest(frame, bone):
    """A bone's rest head and direction (head to tail), in the character frame."""
    return {
        "head": frame.armature_point(bone.head_local),
        "direction": frame.armature_direction(bone.tail_local - bone.head_local),
    }


def _control_entry(frame, rig_object, name, control, family, compact):
    entry = {"bone": name, "role": control["role"], "chain": control["chain"],
             "source": control["source"]}
    if compact:
        entry["hidden_by_default"] = control["hidden_by_default"]
        if family == "default":
            entry["driven_by"] = control["driven_by"]
        return entry
    bone = rig_object.data.bones[name]
    pose_bone = rig_object.pose.bones[name]
    entry.update(_rest(frame, bone))
    entry["rotation_mode"] = pose_bone.rotation_mode
    entry["locked"] = _locked(pose_bone)
    entry["hidden_by_default"] = control["hidden_by_default"]
    if family == "default":
        entry["driven_by"] = control["driven_by"]
    else:
        entry["settings"] = control["settings"]
    return entry


def _bone_entry(frame, bone, pose_bone, compact):
    entry = {"bone": bone.name, "parent": None if bone.parent is None else bone.parent.name,
             "deform": bool(bone.use_deform)}
    if compact:
        return entry
    entry.update(_rest(frame, bone))
    entry["rotation_mode"] = pose_bone.rotation_mode
    return entry


_SWITCH_NAMES_NOT_APPLIED = (" switch_names is not applied: only a generated Rigify rig has "
                             "switches.")


def _has_switches(classification):
    """Whether the rig is one whose switches are listed: generated Rigify, of either family."""
    return classification["family"] not in (None, "default")


def _message_for(rig, identified, classification, tally, switch_names):
    if not classification["classified"]:
        return ("'{:s}' is identified as '{!s}', which these tools do not classify, so its {:d} "
                "bones are listed as a hierarchy with no body part or role, and neither roles "
                "nor include_hidden is applied.{:s} Classified rigs are {:s}.".format(
                    rig.name, identified, len(rig.data.bones),
                    "" if switch_names is None else _SWITCH_NAMES_NOT_APPLIED,
                    ", ".join(pose_controls.CLASSIFIED_RIGS)))
    counts = tally["counts_by_body_part"]
    requested = tally["requested"]
    parts = ["'{:s}' ({:s}) has {:d} control(s); {:d} listed for {:s}.".format(
        rig.name, identified, sum(counts.values()), tally["listed"], ", ".join(requested))]
    if "face" not in requested and counts["face"]:
        parts.append(" {:d} face control(s) are left out unless body_parts names 'face'.".format(
            counts["face"]))
    if tally["other_roles"]:
        parts.append(" {:d} control(s) of other roles are left out; counts_by_role says which "
                     "roles they have.".format(tally["other_roles"]))
    hidden = sum(tally["hidden_by_body_part"].values())
    if hidden and not tally["include_hidden"]:
        parts.append(" {:d} hidden control(s) are left out; pass include_hidden to list "
                     "them.".format(hidden))
    if tally["other_switches"]:
        parts.append(" {:d} switch(es) of other names are left out; counts_by_switch says "
                     "which.".format(tally["other_switches"]))
    if classification["family"] == "default":
        if switch_names is not None:
            parts.append(_SWITCH_NAMES_NOT_APPLIED)
        modes = classification["helper_modes"] or {}
        installed = [mode for mode, value in modes.items() if value != "NONE"]
        if installed:
            parts.append(" MPFB's helpers are installed ({:s}): an FK bone with driven_by set is "
                         "held by its helper, so move the helper instead; rotating the bone "
                         "itself does nothing that lasts.".format(", ".join(installed)))
        if classification["helpers_missing"]:
            parts.append(" {:d} helper bone(s) MPFB records as installed are missing from the "
                         "rig; see helpers_missing.".format(
                             len(classification["helpers_missing"])))
    if classification["unassigned"]:
        parts.append(" {:d} bone(s) fit no body part and are listed in "
                     "unassigned_bones.".format(len(classification["unassigned"])))
    return "".join(parts)


def _unknown_roles(resolved, roles):
    """``resolved`` turned into the ``unknown_roles`` refusal, or ``None`` when every role is one."""
    unknown = pose_controls.unknown_roles(roles)
    if not unknown:
        return None
    blocked = dict(resolved)
    blocked.update(
        blocked_by="unknown_roles",
        message="roles names {:s}, which {:s} not a role. The roles are: {:s}.".format(
            ", ".join(repr(role) for role in unknown), "is" if len(unknown) == 1 else "are",
            ", ".join(pose_controls.ROLES)),
        extra={"unknown_roles": unknown, "known_roles": list(pose_controls.ROLES)})
    return blocked


def _unknown_switch_names(resolved, classification, switch_names):
    """``resolved`` turned into the ``unknown_switch_names`` refusal, or ``None``.

    Only a generated Rigify rig has switches to check against; on any other the
    filter is not applied, and so nothing in it can be a mistake.
    """
    if switch_names is None or not _has_switches(classification):
        return None
    known = _switch_names(classification)
    unknown = [name for name in switch_names if name not in known]
    if not unknown:
        return None
    blocked = dict(resolved)
    blocked.update(
        blocked_by="unknown_switch_names",
        message="switch_names names {:s}, which {:s} not a switch anywhere on '{:s}'. Its "
                "switches are: {:s}.".format(
                    ", ".join(repr(name) for name in unknown),
                    "is" if len(unknown) == 1 else "are", resolved["rig"].name,
                    ", ".join(known)),
        extra={"unknown_switch_names": unknown, "known_switch_names": known})
    return blocked


def _switch_names(classification):
    """Every switch name the rig has, in any body part, sorted."""
    return sorted(set(switch["switch"] for switch in classification["switches"]))


def _switch_entry(switch, compact):
    """A switch as listed: whole, or without what ``mpfb_set_pose_switches`` never needs."""
    if not compact:
        return switch
    return {key: value for key, value in switch.items()
            if key not in ("bone", "default", "description")}


def _switch_listing(classification, params, requested):
    """``switches`` and ``counts_by_switch``, filtered by body part and then by name."""
    switch_names = params["switch_names"]
    counts = {name: 0 for name in _switch_names(classification)}
    listed = []
    for switch in classification["switches"]:
        if switch["body_part"] not in requested:
            continue
        counts[switch["switch"]] += 1
        if switch_names is None or switch["switch"] in switch_names:
            listed.append(_switch_entry(switch, params["compact"]))
    return listed, counts


def _listing(frame, rig, classification, params, requested):
    """``controls`` and the counts that explain whatever it leaves out, filtered as asked."""
    roles = params["roles"]
    include_hidden = params["include_hidden"]
    counts = {part: 0 for part in pose_controls.BODY_PARTS}
    by_role = {role: 0 for role in pose_controls.ROLES}
    hidden = {part: 0 for part in requested}
    grouped = {part: [] for part in requested}
    other_roles = 0
    for name, control in classification["controls"].items():
        part = control["body_part"]
        counts[part] += 1
        if part not in grouped:
            continue
        by_role[control["role"]] += 1
        if roles is not None and control["role"] not in roles:
            other_roles += 1
            continue
        if control["hidden_by_default"]:
            hidden[part] += 1
            if not include_hidden:
                continue
        grouped[part].append(_control_entry(frame, rig, name, control, classification["family"],
                                            params["compact"]))
    switches, by_switch = _switch_listing(classification, params, requested)
    return {"controls": grouped, "counts_by_body_part": counts, "counts_by_role": by_role,
            "hidden_by_body_part": hidden, "other_roles": other_roles, "requested": requested,
            "include_hidden": include_hidden,
            "listed": sum(len(entries) for entries in grouped.values()),
            "switches": switches, "counts_by_switch": by_switch,
            "other_switches": sum(by_switch.values()) - len(switches)}


def get_pose_controls(params, resolution):  # pylint: disable=too-many-locals
    """List one character's controls, or its bones when its rig is not classified."""
    resolved = pose_controls.resolve_posing_subject(
        resolution.services, params["name"], params["body_parts"])
    if resolved["blocked_by"] is None:
        resolved = _unknown_roles(resolved, params["roles"]) or resolved
    if resolved["blocked_by"] is not None:
        _LOG.debug("get_pose_controls: refused %r", resolved["blocked_by"])
        return _blocked(resolved)
    basemesh = resolved["basemesh"]
    subject = resolved["subject"]
    rig = resolved["rig"]
    identified = resolved["rig_identified_as"]

    classification = pose_controls.classify(resolution.module.__name__, rig, identified)
    blocked = _unknown_switch_names(resolved, classification, params["switch_names"])
    if blocked is not None:
        _LOG.debug("get_pose_controls: refused %r", blocked["blocked_by"])
        return _blocked(blocked)
    frame = Frame(rig)
    answer: dict = dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=resolved["resolved_by"],
        basemesh_name=basemesh.name,
        rig_object_name=rig.name,
        rig_identified_as=identified,
        classified=classification["classified"],
        classified_rigs=list(pose_controls.CLASSIFIED_RIGS),
        character_frame=frame.describe(),
        compact=params["compact"],
    )

    if not classification["classified"]:
        answer.update(
            requested_body_parts=None,
            requested_roles=None,
            requested_switch_names=None,
            include_hidden=None,
            counts_by_body_part=None,
            counts_by_role=None,
            counts_by_switch=None,
            hidden_by_body_part=None,
            controls=None,
            switches=None,
            helper_modes=None,
            helper_modes_reason=None,
            helpers_missing=None,
            unassigned_bones=None,
            bones=[_bone_entry(frame, bone, rig.pose.bones[bone.name], params["compact"])
                   for bone in rig.data.bones],
            message=_message_for(rig, identified, classification, None,
                                 params["switch_names"]),
        )
        return answer

    requested = pose_controls.requested_body_parts(params["body_parts"])
    tally = _listing(frame, rig, classification, params, requested)
    has_switches = _has_switches(classification)
    answer.update(
        requested_body_parts=list(requested),
        requested_roles=None if params["roles"] is None else [
            role for role in pose_controls.ROLES if role in params["roles"]],
        requested_switch_names=None if params["switch_names"] is None or not has_switches
        else sorted(params["switch_names"]),
        include_hidden=params["include_hidden"],
        counts_by_body_part=tally["counts_by_body_part"],
        counts_by_role=tally["counts_by_role"],
        counts_by_switch=tally["counts_by_switch"] if has_switches else None,
        hidden_by_body_part=tally["hidden_by_body_part"],
        controls=tally["controls"],
        switches=tally["switches"],
        helper_modes=classification["helper_modes"],
        helper_modes_reason=classification["helper_modes_reason"],
        helpers_missing=classification["helpers_missing"],
        unassigned_bones=classification["unassigned"],
        bones=None,
        message=_message_for(rig, identified, classification, tally, params["switch_names"]),
    )
    _LOG.debug("get_pose_controls: %d controls, %d listed", len(classification["controls"]),
               tally["listed"])
    return answer
