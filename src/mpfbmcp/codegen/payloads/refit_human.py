"""
Payload for ``mpfb_refit_human``: MPFB's ``HumanService.refit()``, plus the
one failure it cannot report to a caller that is not an operator.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, which is None
  when the caller wants whatever object is currently active.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap.

``refit()`` raises ``ValueError`` when it cannot find a basemesh; the basemesh is
resolved here first so that this comes back as an ordinary "no" rather than as a
traceback in an error envelope.

What is refitted is enumerated *before* the call, with the same two lookups
``refit()`` itself makes, so the answer describes what was actually touched
rather than what was found afterwards.
"""

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
TargetService = _MPFB_SERVICES["TargetService"]
HumanService = _MPFB_SERVICES["HumanService"]


def rig_refit_blocker(rig):
    """Why refit() would leave this rig untouched, or None.

    A generated Rigify rig can only be refitted through its meta rig. With no
    meta rig left in the scene, refit() logs a warning, tries to report through
    an ``operator`` it was not given, and returns - having refitted the mesh
    assets, which happen first, but not the rig. Detecting the condition here is
    what keeps this tool from answering refit_performed: true over a rig it
    never touched.
    """
    if rig is None:
        return None
    if not ObjectService.object_is_generated_rigify_rig(rig):
        return None
    if ObjectService.find_rigify_metarig_by_rig(rig) is not None:
        return None
    return ("The rig '" + rig.name + "' is a generated Rigify rig and no meta rig is left in the "
            "scene, so it could not be refitted. Its mesh assets were. Regenerate the rig with "
            "the Rigify sub-panel's 'Meta-rig' option set to Keep or Hide to allow refitting.")


requested_name = PARAMS["name"]
subject_resolved_by = "active" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        message = ("No object name was given and no object is active in this Blender session, so "
                   "nothing was refitted. Select a MakeHuman object, or call mpfb_list_objects "
                   "and pass one of its names.")
else:
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        message = ("No object named '" + str(requested_name) + "' exists in this .blend file, so "
                   "nothing was refitted. Call mpfb_list_objects to see what the current scene "
                   "holds.")

basemesh = None
if subject is not None:
    # refit() makes this same call and raises when it comes back None. Making it
    # here first turns that into an answer.
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if basemesh is None:
        message = ("'" + subject.name + "' has no MakeHuman basemesh among its nearest relatives, "
                   "so there is nothing to refit it to. Call mpfb_get_object_info to see what it "
                   "is related to.")

if basemesh is None:
    result = dict(
        found=False,
        ready=False,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None,
        refit_performed=False,
        message=message,
    )
elif basemesh.mode != "OBJECT":
    # Fitting reaches bpy.ops.object.mode_set through ClothesService, which is
    # not a thing to attempt while the user has the basemesh open in edit mode.
    result = dict(
        found=True,
        ready=False,
        blocked_by="not_object_mode",
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        refit_performed=False,
        message=("The basemesh '" + basemesh.name + "' is in " + str(basemesh.mode) + " mode. "
                 "Refitting requires OBJECT mode, so nothing was refitted. Leave edit mode and "
                 "call again."),
    )
else:
    rig = ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")

    # refit() walks from the rig when there is one and from the basemesh
    # otherwise, and takes only children. Enumerating with the same rules is
    # what makes these lists a report of what was touched rather than a
    # separate, differently-scoped answer.
    parent_object = basemesh if rig is None else rig
    mesh_assets = [
        asset.name for asset in ObjectService.find_related_mesh_assets(
            parent_object, only_children=True)
    ]
    subrigs = [
        subrig.name for subrig in ObjectService.find_all_objects_of_type_amongst_nearest_relatives(
            parent_object, "Subrig", only_children=True)
    ]

    refit_incomplete_reason = rig_refit_blocker(rig)

    previous_active = bpy.context.view_layer.objects.active
    basemesh_was_selected = bool(basemesh.select_get())
    try:
        HumanService.refit(basemesh)
    finally:
        # ClothesService restores the active object itself, but only around its
        # own edit-mode excursion. Restoring here covers the whole call, and the
        # user is looking at this scene.
        if not basemesh_was_selected:
            basemesh.select_set(False)
        bpy.context.view_layer.objects.active = previous_active

    # Built by concatenation rather than the repo's usual .format(): a payload
    # file must contain no empty brace pair anywhere, since that is what a
    # substitution point looks like. tests/test_codegen.py enforces it.
    message_parts = [
        "Refitted " + str(len(mesh_assets)) + " mesh asset(s) to basemesh '" + basemesh.name
        + "'."]
    if refit_incomplete_reason is not None:
        message_parts.append(" " + refit_incomplete_reason)
    elif rig is None:
        message_parts.append(" This character has no rig.")
    else:
        message_parts.append(
            " The rig '" + rig.name + "' and " + str(len(subrigs)) + " sub-rig(s) were refitted "
            "as well.")

    result = dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        basemesh_has_shapekeys=bool(TargetService.has_any_shapekey(basemesh)),
        rig_name=None if rig is None else rig.name,
        mesh_assets=mesh_assets,
        mesh_asset_count=len(mesh_assets),
        subrigs=subrigs,
        subrig_count=len(subrigs),
        refit_performed=refit_incomplete_reason is None,
        refit_incomplete_reason=refit_incomplete_reason,
        message="".join(message_parts),
    )
