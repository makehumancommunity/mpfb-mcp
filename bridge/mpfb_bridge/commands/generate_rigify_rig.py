"""
``generate_rigify_rig``: turn a Rigify meta rig into a real one.

**The subject is the meta rig, not the basemesh**, which makes this the one
mutating command here that does not resolve to a ``Basemesh``. It still accepts
any object in the character's family, but it narrows to a ``Skeleton`` and then
asks ``RigService.identify_rig()`` which kind it found. Two details make that a
scan of *all* the skeleton relatives rather than a single lookup:

- ``identify_rig()`` answers for an armature it does not recognise rather than
  refusing to. It matches on bone names and falls through to ``"unknown"``,
  ``"rigify.unknown"`` or ``"rigify_generated.unknown"``, so "not a meta rig" is
  a string this has to read, not an exception it could let through.
- After a previous generation, the basemesh's ``Skeleton`` relative is the
  *generated* rig, not the meta rig. ``RigifyHelpers.adjust_children_for_rigify()``
  re-parents the basemesh and every garment onto the generated rig, leaving the
  meta rig outside the family entirely. So "already generated" is a distinct
  answer from "that is not a meta rig", and a single
  ``find_object_of_type_amongst_nearest_relatives()`` could not tell them apart.

**A failed generation is not a no-op**, which is the other reason this command
exists. ``RigService.generate_rigify_rig()`` renames a meta rig whose name ends
in ``.rig``, may set ``rigify_rig_basename``, deselects everything, activates the
meta rig and runs ``bpy.ops.pose.rigify_upgrade_face()`` when that polls true -
and only *then* asks Rigify's own ``is_valid_metarig()`` and returns ``None``.
Reporting that as a ``command_failed`` envelope would tell the caller nothing
changed, which is false.

**Nothing is restored afterwards, and the response says so.** Every other
mutating command here puts the previous active object and selection back in a
``finally``. This one cannot: the operator's own final act is to select and
activate the rig it generated, so there is no state left to restore to.
``active_object_after`` is what the caller gets instead - and
[the spike](../../../feature-requests/done/032-creation-and-modification-migrated/SPIKE.md)
confirmed that is exactly what happens in a Blender with no window, which is
where this command's own tests run.

Finally, ``meta_rig_action`` has a consequence that outlives this call.
``"delete"`` removes the meta rig, and a generated Rigify rig with no meta rig
in the scene is precisely the state ``HumanService.refit()`` cannot handle: it
refits the mesh assets, tries to report the rig failure through an ``operator``
a command does not have, and returns. ``refit_human`` detects that after the
fact; this is where it is knowable in advance, as ``refit_will_be_possible``.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "generate_rigify_rig",
)

import bpy

from ..log import get_logger
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.generaterigifyrig")

META_RIG_ACTIONS = ("hide", "delete", "keep")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("rig_name", TYPE_STRING, default=None, nullable=True,
          description="Basename for the generated rig. Omit for MPFB's own naming."),
    Param("meta_rig_action", TYPE_STRING, default="hide", choices=META_RIG_ACTIONS,
          description="What to do with the meta rig afterwards. 'delete' makes the character "
                      "permanently unrefittable, which the answer says in so many words."),
)

SUMMARY = "Generate a real Rigify rig from a character's Rigify meta rig."

RIGIFY_MISSING_REASON = (
    "Rigify is not enabled in this Blender, so nothing could be generated. Enable the Rigify "
    "add-on in Blender's preferences and call again; the meta rig is unchanged."
)

REFIT_IMPOSSIBLE_REASON = (
    "The meta rig was deleted, so this character's rig can no longer be refitted to a changed body "
    "shape. HumanService.refit() can only refit a generated Rigify rig through its meta rig; with "
    "none in the scene it refits the mesh assets, leaves the rig alone and reports nothing. "
    "mpfb_refit_human will answer refit_performed: false from now on. Finish the modeling before "
    "generating, or use meta_rig_action 'hide'."
)


def _rig_kind(rig_service, armature_object):
    """What ``identify_rig()`` makes of an armature: metarig, generated, other.

    The ``data.bones`` guard is the necessary one: a Skeleton-typed object that
    is not an armature at all has none for ``identify_rig()`` to match against.
    The falsy-``rig_type`` guard is belt and braces - MPFB 2.0.17 answers
    ``"unknown"`` rather than ``None`` for an armature it cannot place - and is
    kept because both readings end in the same answer and the cheaper one is
    the one that survives MPFB changing its mind.
    """
    if armature_object is None or armature_object.type != "ARMATURE":
        return (None, "other")
    rig_type = rig_service.identify_rig(armature_object)
    if not rig_type:
        return (rig_type, "other")
    if rig_type.startswith("rigify_generated."):
        return (rig_type, "generated")
    if rig_type.startswith("rigify."):
        return (rig_type, "metarig")
    return (rig_type, "other")


def _active_object_name():
    active = bpy.context.view_layer.objects.active
    return None if active is None else active.name


def _blocked(subject, subject_resolved_by, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=subject is not None,
        ready=False,
        generated=False,
        blocked_by=reason,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        metarig_name=None,
        rig_object_name=None,
        metarig_disposition=None,
        refit_will_be_possible=True,
        active_object_after=_active_object_name(),
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _resolve(requested_name):
    """The object asked about, and the sentence on a miss."""
    if requested_name is None:
        subject = bpy.context.view_layer.objects.active
        if subject is None:
            return (None,
                    "No object name was given and no object is active in this Blender session, so "
                    "nothing was generated. Select a MakeHuman object, or call mpfb_list_objects "
                    "and pass one of its names.")
        return (subject, None)
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        return (None,
                "No object named '{:s}' exists in this .blend file, so nothing was generated. "
                "Call mpfb_list_objects to see what the current scene holds.".format(
                    str(requested_name)))
    return (subject, None)


def _survey(services, subject):
    """Every Skeleton relative of the subject, sorted into the three kinds."""
    rig_service = services["RigService"]
    meta_rig = None
    generated_present = []
    other_skeletons = []
    skeletons = list(
        services["ObjectService"].find_all_objects_of_type_amongst_nearest_relatives(
            subject, "Skeleton"))
    for skeleton in skeletons:
        rig_type, kind = _rig_kind(rig_service, skeleton)
        if kind == "metarig" and meta_rig is None:
            meta_rig = skeleton
        elif kind == "generated":
            generated_present.append({"name": skeleton.name, "rig_type": rig_type})
        elif kind != "metarig":
            other_skeletons.append({"name": skeleton.name, "rig_type": rig_type})
    return (meta_rig, generated_present, other_skeletons)


def _refusal(services, subject, subject_resolved_by, message,
             meta_rig, generated_present, other_skeletons):
    """The first refusal that applies, or ``None``."""
    def blocked(reason, text, **extra):
        return _blocked(subject, subject_resolved_by, reason, text, **extra)

    if subject is None:
        return blocked("subject_not_found", message)
    if not services["SystemService"].check_for_rigify():
        return blocked("rigify_unavailable", RIGIFY_MISSING_REASON, rigify_available=False)
    if meta_rig is None and generated_present:
        # adjust_children_for_rigify() moved the basemesh and every garment onto
        # the generated rig, so the meta rig is no longer a relative of anything
        # here. Generating twice is not a thing to attempt: the second run would
        # build a second rig from a meta rig that is no longer connected to the
        # character.
        return blocked(
            "already_generated",
            "This character already carries the generated Rigify rig '{:s}', so nothing was "
            "generated. Generation re-parents the character onto the generated rig, which is why "
            "its meta rig is no longer among its relatives. There is nothing left to generate "
            "from.".format(generated_present[0]["name"]),
            generated_rigs=generated_present)
    if meta_rig is None and other_skeletons:
        return blocked(
            "not_a_metarig",
            "'{:s}' is rigged, but with '{!s}' rather than a Rigify meta rig, so nothing was "
            "generated. Only a rig added from a 'rigify.*' identifier can be generated; "
            "mpfb_list_rigs reports which those are.".format(
                subject.name, other_skeletons[0]["rig_type"]),
            skeletons=other_skeletons)
    if meta_rig is None:
        return blocked(
            "no_armature_found",
            "'{:s}' has no armature among its nearest relatives, so there is no meta rig to "
            "generate from. Add one first with mpfb_add_rig and a 'rigify.*' "
            "identifier.".format(subject.name))
    if meta_rig.mode != "OBJECT" or bpy.context.mode != "OBJECT":
        # Generation drives bpy.ops throughout - select_all, mode_set,
        # rigify_upgrade_face, rigify_generate - and every one of them polls on
        # the context mode, not on this armature's.
        return blocked(
            "not_object_mode",
            "Blender is in {:s} mode and the meta rig '{:s}' is in {:s} mode. Rigify generation "
            "runs operators that require OBJECT mode, so nothing was generated. Leave edit or "
            "pose mode and call again.".format(
                str(bpy.context.mode), meta_rig.name, str(meta_rig.mode)),
            metarig_name=meta_rig.name)
    return None


def _message_for(generated, rig_object, metarig_name_before, metarig_name_after,
                 disposition, mesh_assets_present):
    """What happened, said once, in the order a reader wants it."""
    parts = []
    if generated:
        parts.append(
            "Generated the Rigify rig '{:s}' from the meta rig '{:s}', and re-parented {:d} mesh "
            "asset(s) onto it.".format(
                rig_object.name, metarig_name_before, len(mesh_assets_present)))
        if disposition == "deleted":
            parts.append(" The meta rig was deleted. " + REFIT_IMPOSSIBLE_REASON)
        elif disposition == "hidden":
            parts.append(" The meta rig was hidden from the viewport and renders but kept in the "
                         "scene, so the rig can still be refitted and re-generated.")
        else:
            parts.append(" The meta rig was left visible in the scene.")
    else:
        parts.append(
            "Rigify rejected the meta rig '{:s}' as invalid, so no rig was generated. **This was "
            "not a no-op**: MPFB deselected everything, made the meta rig active and may have "
            "renamed it or run Rigify's face upgrade before the validity check ran.".format(
                metarig_name_before))
        if metarig_name_after != metarig_name_before:
            parts.append(" The meta rig is now called '{!s}'.".format(metarig_name_after))
        parts.append(" Check that the Rigify bone configuration on the meta rig is intact.")
    if generated and not mesh_assets_present:
        parts.append(" This character had no mesh assets at generation time. Anything attached "
                     "from now on is fitted to the generated rig, which is the right order.")
    return "".join(parts)


def generate_rigify_rig(params, resolution):  # pylint: disable=too-many-locals
    """Generate one Rigify rig, and say what happened even when nothing was generated."""
    services = resolution.services
    object_service = services["ObjectService"]

    requested_name = params["name"]
    requested_rig_name = params["rig_name"]
    meta_rig_action = params["meta_rig_action"]

    subject_resolved_by = "active" if requested_name is None else "name"
    subject, message = _resolve(requested_name)

    meta_rig = None
    generated_present = []
    other_skeletons = []
    if subject is not None:
        meta_rig, generated_present, other_skeletons = _survey(services, subject)

    refused = _refusal(services, subject, subject_resolved_by, message,
                       meta_rig, generated_present, other_skeletons)
    if refused is not None:
        _LOG.debug("generate_rigify_rig: refused %r", refused["blocked_by"])
        return refused

    # Read before generating: attaching mesh assets afterwards is the second
    # half of the ordering problem add_rig reports the first half of. Generation
    # handles exactly what is on the character when it runs.
    mesh_assets_present = [
        asset.name for asset in object_service.find_related_mesh_assets(meta_rig)
    ]
    basemesh = object_service.find_object_of_type_amongst_nearest_relatives(meta_rig, "Basemesh")
    metarig_name_before = meta_rig.name

    rig_object = services["RigService"].generate_rigify_rig(
        meta_rig,
        name=requested_rig_name or "",
        meta_rig_action=meta_rig_action,
    )

    generated = rig_object is not None
    metarig_deleted = bool(generated and meta_rig_action == "delete")
    # Readable in every case but one: with "delete" the datablock is gone by the
    # time control returns here, and the rename that preceded it cannot be
    # observed from outside.
    metarig_name_after = None if metarig_deleted else meta_rig.name

    if not generated:
        disposition = "kept"
    elif meta_rig_action == "delete":
        disposition = "deleted"
    elif meta_rig_action == "keep":
        disposition = "kept"
    else:
        # MPFB defaults an unrecognised value to hide, but the parameter
        # contract has already rejected anything outside the three.
        disposition = "hidden"

    refit_will_be_possible = not metarig_deleted

    _LOG.debug("generate_rigify_rig: generated=%r disposition=%r", generated, disposition)

    result = dict(
        found=True,
        ready=True,
        generated=generated,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        metarig_name=metarig_name_before,
        metarig_name_after=metarig_name_after,
        metarig_renamed=bool(metarig_name_after is not None
                             and metarig_name_after != metarig_name_before),
        rig_object_name=None if rig_object is None else rig_object.name,
        rig_name_requested=requested_rig_name,
        meta_rig_action=meta_rig_action,
        metarig_disposition=disposition,
        refit_will_be_possible=refit_will_be_possible,
        refit_impossible_reason=None if refit_will_be_possible else REFIT_IMPOSSIBLE_REASON,
        mesh_assets_present=mesh_assets_present,
        # Generation selects and activates its own result, so unlike every other
        # mutating command here there is nothing to restore. Saying what the
        # selection now is beats silently leaving the user's scene rearranged.
        active_object_after=_active_object_name(),
        selection_restored=False,
        message=_message_for(generated, rig_object, metarig_name_before, metarig_name_after,
                             disposition, mesh_assets_present),
    )

    # The verb is "generated", which is false when Rigify rejected the meta
    # rig - a ready: true answer that changed the scene without producing a rig.
    # See shared/performed.py.
    return with_performed(result, result["generated"])
