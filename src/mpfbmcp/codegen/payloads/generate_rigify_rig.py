"""
Payload for ``mpfb_generate_rigify_rig``: turn a meta rig into a real one.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap and the
``performed.py`` shared fragment (see ``mpfbmcp.codegen.assemble``). A linter
will flag four names as undefined because the assembler binds them ahead of
this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name`` (the subject),
  ``rig_name`` (the generated rig's basename, or None) and ``meta_rig_action``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap (unused here, but bound).
- ``with_performed()`` - from the shared fragment ``performed.py``, named by
  every mutating payload. It stamps the uniform ``performed`` flag onto the
  finished answer, in the last line of this file.

**The subject is the meta rig, not the basemesh**, which makes this the one
mutating tool here that does not resolve to a ``Basemesh``. It still accepts any
object in the character's family, but it narrows to a ``Skeleton`` and then asks
``RigService.identify_rig()`` which kind it found. Two details make that a scan
of *all* the skeleton relatives rather than a single lookup:

- ``identify_rig()`` can return ``None``. It starts from ``guessed_rig = None``
  and matches on bone names, so an armature MPFB does not recognise falls
  straight through - and MPFB's own operator ``poll()`` would raise on that.
- After a previous generation, the basemesh's ``Skeleton`` relative is the
  *generated* rig, not the meta rig. ``RigifyHelpers.adjust_children_for_rigify()``
  re-parents the basemesh and every garment onto the generated rig, leaving the
  meta rig outside the family entirely. So "already generated" is a distinct
  answer from "that is not a meta rig", and a single
  ``find_object_of_type_amongst_nearest_relatives()`` could not tell them apart.

**A failed generation is not a no-op**, which is the other reason this payload
exists. ``RigService.generate_rigify_rig()`` renames a meta rig whose name ends
in ``.rig``, may set ``rigify_rig_basename``, deselects everything, activates
the meta rig and runs ``bpy.ops.pose.rigify_upgrade_face()`` when that polls
true - and only *then* asks Rigify's own ``is_valid_metarig()`` and returns
``None``. Reporting that as an error envelope would tell the caller nothing
changed, which is false.

**Nothing is restored afterwards, and the response says so.** Every other
mutating tool here puts the previous active object and selection back in a
``finally``. This one cannot: the operator's own final act is to select and
activate the rig it generated, so there is no state left to restore to.
``active_object_after`` is what the caller gets instead.

Finally, ``meta_rig_action`` has a consequence that outlives this call.
``"delete"`` removes the meta rig, and a generated Rigify rig with no meta rig
in the scene is precisely the state ``HumanService.refit()`` cannot handle: it
refits the mesh assets, tries to report the rig failure through an ``operator``
an MCP tool does not have, and returns. ``mpfb_refit_human`` detects that after
the fact; this is where it is knowable in advance, as
``refit_will_be_possible``.
"""

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
RigService = _MPFB_SERVICES["RigService"]
SystemService = _MPFB_SERVICES["SystemService"]

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


def rig_kind(armature_object):
    """What ``identify_rig()`` makes of an armature: metarig, generated, other.

    Guarded because the real function returns None for an armature it cannot
    place, and because a Skeleton-typed object that is not an armature at all
    would have no ``data.bones`` to match against.
    """
    if armature_object is None or armature_object.type != "ARMATURE":
        return (None, "other")
    rig_type = RigService.identify_rig(armature_object)
    if not rig_type:
        return (rig_type, "other")
    if rig_type.startswith("rigify_generated."):
        return (rig_type, "generated")
    if rig_type.startswith("rigify."):
        return (rig_type, "metarig")
    return (rig_type, "other")


def active_object_name():
    active = bpy.context.view_layer.objects.active
    return None if active is None else active.name


def blocked(subject, reason, message, **extra):
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
        active_object_after=active_object_name(),
        message=message,
    )
    answer.update(extra)
    return answer


requested_name = PARAMS["name"]
requested_rig_name = PARAMS["rig_name"]
meta_rig_action = PARAMS["meta_rig_action"]

subject_resolved_by = "active" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        message = ("No object name was given and no object is active in this Blender session, so "
                   "nothing was generated. Select a MakeHuman object, or call mpfb_list_objects "
                   "and pass one of its names.")
else:
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        message = ("No object named '" + str(requested_name) + "' exists in this .blend file, so "
                   "nothing was generated. Call mpfb_list_objects to see what the current scene "
                   "holds.")

skeletons = []
meta_rig = None
generated_present = []
other_skeletons = []

if subject is not None:
    skeletons = list(ObjectService.find_all_objects_of_type_amongst_nearest_relatives(
        subject, "Skeleton"))
    for skeleton in skeletons:
        rig_type, kind = rig_kind(skeleton)
        if kind == "metarig" and meta_rig is None:
            meta_rig = skeleton
        elif kind == "generated":
            generated_present.append({"name": skeleton.name, "rig_type": rig_type})
        elif kind != "metarig":
            other_skeletons.append({"name": skeleton.name, "rig_type": rig_type})

if subject is None:
    result = blocked(None, "subject_not_found", message)
elif not SystemService.check_for_rigify():
    result = blocked(subject, "rigify_unavailable", RIGIFY_MISSING_REASON,
                     rigify_available=False)
elif meta_rig is None and generated_present:
    # adjust_children_for_rigify() moved the basemesh and every garment onto the
    # generated rig, so the meta rig is no longer a relative of anything here.
    # Generating twice is not a thing to attempt: the second run would build a
    # second rig from a meta rig that is no longer connected to the character.
    result = blocked(
        subject, "already_generated",
        ("This character already carries the generated Rigify rig '"
         + generated_present[0]["name"] + "', so nothing was generated. Generation re-parents the "
           "character onto the generated rig, which is why its meta rig is no longer among its "
           "relatives. There is nothing left to generate from."),
        generated_rigs=generated_present)
elif meta_rig is None and other_skeletons:
    result = blocked(
        subject, "not_a_metarig",
        ("'" + subject.name + "' is rigged, but with '" + str(other_skeletons[0]["rig_type"])
         + "' rather than a Rigify meta rig, so nothing was generated. Only a rig added from a "
           "'rigify.*' identifier can be generated; mpfb_list_rigs reports which those are."),
        skeletons=other_skeletons)
elif meta_rig is None:
    result = blocked(
        subject, "no_armature_found",
        ("'" + subject.name + "' has no armature among its nearest relatives, so there is no meta "
         "rig to generate from. Add one first with mpfb_add_rig and a 'rigify.*' identifier."))
elif meta_rig.mode != "OBJECT" or bpy.context.mode != "OBJECT":
    # Generation drives bpy.ops throughout - select_all, mode_set,
    # rigify_upgrade_face, rigify_generate - and every one of them polls on the
    # context mode, not on this armature's.
    result = blocked(
        subject, "not_object_mode",
        ("Blender is in " + str(bpy.context.mode) + " mode and the meta rig '" + meta_rig.name
         + "' is in " + str(meta_rig.mode) + " mode. Rigify generation runs operators that require "
           "OBJECT mode, so nothing was generated. Leave edit or pose mode and call again."),
        metarig_name=meta_rig.name)
else:
    # Read before generating: attaching mesh assets afterwards is the second
    # half of the ordering problem mpfb_add_rig reports the first half of.
    # Generation handles exactly what is on the character when it runs.
    mesh_assets_present = [
        asset.name for asset in ObjectService.find_related_mesh_assets(meta_rig)
    ]
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(meta_rig, "Basemesh")
    metarig_name_before = meta_rig.name

    rig_object = RigService.generate_rigify_rig(
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
        # MPFB defaults an unrecognised value to hide, but the tool module has
        # already rejected anything outside the three.
        disposition = "hidden"

    refit_will_be_possible = not metarig_deleted

    # Built by concatenation rather than the repo's usual .format(): a payload
    # file must contain no empty brace pair anywhere, since that is what a
    # substitution point looks like. tests/test_codegen.py enforces it.
    message_parts = []
    if generated:
        message_parts.append(
            "Generated the Rigify rig '" + rig_object.name + "' from the meta rig '"
            + metarig_name_before + "', and re-parented " + str(len(mesh_assets_present))
            + " mesh asset(s) onto it.")
        if disposition == "deleted":
            message_parts.append(" The meta rig was deleted. " + REFIT_IMPOSSIBLE_REASON)
        elif disposition == "hidden":
            message_parts.append(
                " The meta rig was hidden from the viewport and renders but kept in the scene, so "
                "the rig can still be refitted and re-generated.")
        else:
            message_parts.append(" The meta rig was left visible in the scene.")
    else:
        message_parts.append(
            "Rigify rejected the meta rig '" + metarig_name_before + "' as invalid, so no rig was "
            "generated. **This was not a no-op**: MPFB deselected everything, made the meta rig "
            "active and may have renamed it or run Rigify's face upgrade before the validity check "
            "ran.")
        if metarig_name_after != metarig_name_before:
            message_parts.append(
                " The meta rig is now called '" + str(metarig_name_after) + "'.")
        message_parts.append(
            " Check that the Rigify bone configuration on the meta rig is intact.")
    if generated and not mesh_assets_present:
        message_parts.append(
            " This character had no mesh assets at generation time. Anything attached from now on "
            "is fitted to the generated rig, which is the right order.")

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
        # mutating tool here there is nothing to restore. Saying what the
        # selection now is beats silently leaving the user's scene rearranged.
        active_object_after=active_object_name(),
        selection_restored=False,
        message="".join(message_parts),
    )


# The verb is "generated", which is false when Rigify rejected the meta rig -
# a ready: true answer that changed the scene without producing a rig. See
# codegen/shared/performed.py.
result = with_performed(result, result.get("generated", False))
