"""
Payload for ``mpfb_set_macro_details``: write the sliders, rebuild the shape.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, ``changes``
  (a list of argument/property/value dicts, empty when the caller named no
  slider), ``prune`` and ``refit``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap.

Writing a macro property is only the first of two steps: it changes a number and
nothing moves until ``TargetService.reapply_macro_details()`` recomputes the
macro target stack from every property at once. So every named property is
written first and the recalculation runs *once*, which is both what MPFB's own
slider callback (``ui/model/_macrosubpanel.py``) does and N times less work than
recalculating per property.

``reapply_macro_details()`` and never ``reapply_all_details()``: the latter also
tears down and reloads the *detail* target stack from disk, where a shape key
whose name was encoded no longer resolves back to a file and is dropped with a
log warning, and where the path lookup falls back to a prefix match that can
silently load a different target. A macro change does not require detail targets
to be reloaded at all.

Three preconditions are checked here and answered as sentences rather than left
to fail inside MPFB: the basemesh must be in OBJECT mode, because
``TargetService.create_shape_key()`` opens with a bare ``assert`` that would come
back as a traceback with no message; it must have shape keys, because
``reapply_macro_details()`` merely logs "somewhat surprising" and carries on;
and the property set must be reachable at all.
"""

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
TargetService = _MPFB_SERVICES["TargetService"]
HumanService = _MPFB_SERVICES["HumanService"]

# HumanObjectProperties is a BlenderConfigSet living on humanservice.py's module
# rather than a service in SERVICES, so it is reached through the module of a
# service that already imported it - never by importing an MPFB submodule, some
# of which create directories on import. Unlike the read-only macro tool, this
# payload genuinely needs it: TargetService has no setter.
HUMANSERVICE_MODULE = sys.modules[HumanService.__module__]
HumanObjectProperties = getattr(HUMANSERVICE_MODULE, "HumanObjectProperties", None)

RACE_NAMES = ("asian", "caucasian", "african")


def as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def macro_details_of(basemesh):
    """The nested dict MPFB itself uses, with every value coerced to a float."""
    raw = TargetService.get_macro_info_dict_from_basemesh(basemesh)
    details = dict()
    for key in raw:
        if key == "race":
            details["race"] = dict(
                (race_name, as_float(raw["race"].get(race_name)))
                for race_name in raw["race"]
            )
        else:
            details[key] = as_float(raw[key])
    return details


def flat_value(macro_details, property_name):
    """One property out of the nested dict, whichever level it lives on."""
    if property_name in RACE_NAMES:
        return macro_details.get("race", dict()).get(property_name)
    return macro_details.get(property_name)


def race_sum_of(macro_details):
    total = 0.0
    for race_name in RACE_NAMES:
        weight = macro_details.get("race", dict()).get(race_name)
        if weight is not None:
            total += weight
    return round(total, 6)


def macro_shapekeys_of(basemesh):
    return [
        str(name) for name in TargetService.get_current_macro_targets(basemesh, decode_names=True)
    ]


def mesh_assets_of(basemesh):
    return [asset.name for asset in ObjectService.find_related_mesh_assets(basemesh)]


def rig_refit_blocker(rig):
    """Why HumanService.refit() would leave this rig untouched, or None.

    refit() reports this case through an ``operator`` it will not be given here,
    and otherwise returns having refitted the mesh assets but not the rig. So
    the condition is detected on this side instead - a generated Rigify rig with
    no meta rig left in the scene - and reported, rather than letting the tool
    claim a refit it did not perform.
    """
    if rig is None:
        return None
    if not ObjectService.object_is_generated_rigify_rig(rig):
        return None
    if ObjectService.find_rigify_metarig_by_rig(rig) is not None:
        return None
    return ("The rig '" + rig.name + "' is a generated Rigify rig and no meta rig is left in the "
            "scene, so it cannot be refitted to the new body shape. Set the Rigify sub-panel's "
            "'Meta-rig' option to Keep or Hide before generating, to allow refitting afterwards.")


requested_name = PARAMS["name"]
changes = PARAMS["changes"]
prune = PARAMS["prune"]
refit_requested = PARAMS["refit"]

subject_resolved_by = "active" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        message = ("No object name was given and no object is active in this Blender session, so "
                   "nothing was changed. Select a MakeHuman object, or call mpfb_list_objects and "
                   "pass one of its names.")
else:
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        message = ("No object named '" + str(requested_name) + "' exists in this .blend file, so "
                   "nothing was changed. Call mpfb_list_objects to see what the current scene "
                   "holds.")

basemesh = None
if subject is not None:
    # The same call MPFB's own macro panel makes: the caller may name the rig or
    # a garment - the names mpfb_list_objects hands out - and the object that is
    # actually modified is reported back rather than the argument echoed.
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if basemesh is None:
        message = ("'" + subject.name + "' has no MakeHuman basemesh among its nearest relatives, "
                   "so there are no macro details to change. Call mpfb_get_object_info to see "
                   "what it is related to.")

if basemesh is None:
    result = dict(
        found=False,
        ready=False,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None,
        changed=[],
        recalculated=False,
        message=message,
    )
else:
    # Preconditions. Each is a state an agent will hit, and each becomes a
    # sentence naming the problem rather than an assertion or a warning buried
    # in Blender's console.
    blocked_by = None
    if HumanObjectProperties is None:
        blocked_by = "properties_unavailable"
        message = ("MPFB's HumanObjectProperties could not be reached, so no macro property can "
                   "be written. Call mpfb_get_status to check how this MPFB is installed.")
    elif basemesh.mode != "OBJECT":
        blocked_by = "not_object_mode"
        message = ("The basemesh '" + basemesh.name + "' is in " + str(basemesh.mode) + " mode. "
                   "Rebuilding the macro shape requires OBJECT mode - MPFB asserts on it - so "
                   "nothing was changed. Leave edit mode and call again.")
    elif not TargetService.has_any_shapekey(basemesh):
        blocked_by = "no_shapekeys"
        message = ("The basemesh '" + basemesh.name + "' has no shape keys at all, so there is no "
                   "macro target stack to rebuild and nothing was changed. This mesh carries MPFB "
                   "properties but was not built by MPFB.")

    if blocked_by is not None:
        macro_details = macro_details_of(basemesh)
        result = dict(
            found=True,
            ready=False,
            blocked_by=blocked_by,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            changed=[],
            recalculated=False,
            macro_details=macro_details,
            race_sum=race_sum_of(macro_details),
            message=message,
        )
    elif not changes:
        # A no-op call is a common mistake, and a full macro reapply costs
        # seconds. Answering immediately is both cheaper and clearer than
        # rebuilding a shape that would come out identical.
        macro_details = macro_details_of(basemesh)
        result = dict(
            found=True,
            ready=True,
            blocked_by=None,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            changed=[],
            recalculated=False,
            macro_details=macro_details,
            race_sum=race_sum_of(macro_details),
            race_normalized=abs(race_sum_of(macro_details) - 1.0) <= 0.001,
            refit_requested=refit_requested,
            refit_performed=False,
            message=("No macro detail was named, so nothing was changed and no shape was "
                     "recalculated. Pass at least one slider - the current values are in "
                     "macro_details."),
        )
    else:
        details_before = macro_details_of(basemesh)
        shapekeys_before = macro_shapekeys_of(basemesh)

        # MPFB's own slider callback activates the basemesh before recalculating.
        # Nothing in reapply_macro_details() obviously requires it, but the refit
        # below reaches bpy.ops through ClothesService, so follow MPFB - and put
        # back what was borrowed: the user is looking at this scene.
        previous_active = bpy.context.view_layer.objects.active
        basemesh_was_selected = bool(basemesh.select_get())

        try:
            for change in changes:
                HumanObjectProperties.set_value(
                    change["property"], change["value"], entity_reference=basemesh)

            ObjectService.activate_blender_object(basemesh)
            # Once, after every write: the stack is derived from all eleven
            # values together, so recalculating per property would be N times
            # the work for the same result.
            TargetService.reapply_macro_details(basemesh, remove_zero_weight_targets=prune)

            rig = ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
            refit_incomplete_reason = None
            refit_performed = False
            if refit_requested:
                refit_incomplete_reason = rig_refit_blocker(rig)
                HumanService.refit(basemesh)
                refit_performed = refit_incomplete_reason is None
        finally:
            if not basemesh_was_selected:
                basemesh.select_set(False)
            bpy.context.view_layer.objects.active = previous_active

        details_after = macro_details_of(basemesh)
        shapekeys_after = macro_shapekeys_of(basemesh)
        race_sum = race_sum_of(details_after)

        changed = [
            dict(
                name=change["argument"],
                property=change["property"],
                previous=flat_value(details_before, change["property"]),
                new=flat_value(details_after, change["property"]),
            )
            for change in changes
        ]

        mesh_assets = mesh_assets_of(basemesh)

        # Built by concatenation rather than the repo's usual .format(): a
        # payload file must contain no empty brace pair anywhere, since that is
        # what a substitution point looks like. tests/test_codegen.py enforces it.
        message_parts = [
            "Changed " + str(len(changed)) + " macro detail(s) on basemesh '" + basemesh.name
            + "' and rebuilt the macro target stack."]
        if refit_performed:
            message_parts.append(
                " Assets and rig were refitted to the new shape.")
        elif refit_incomplete_reason is not None:
            message_parts.append(
                " Mesh assets were refitted, but the rig was not: " + refit_incomplete_reason)
        elif mesh_assets or rig is not None:
            message_parts.append(
                " Nothing was refitted, so the " + str(len(mesh_assets)) + " mesh asset(s)"
                + (" and the rig" if rig is not None else "")
                + " on this character are now fitted to the old shape. Call mpfb_refit_human when "
                  "the modeling is done.")
        if abs(race_sum - 1.0) > 0.001:
            message_parts.append(
                " The three race weights now sum to " + str(race_sum) + " rather than 1.0. MPFB "
                "treats them as independent and does not normalize them.")

        result = dict(
            found=True,
            ready=True,
            blocked_by=None,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            changed=changed,
            recalculated=True,
            prune=prune,
            macro_details=details_after,
            race_sum=race_sum,
            race_normalized=abs(race_sum - 1.0) <= 0.001,
            macro_shapekeys_before=shapekeys_before,
            macro_shapekeys_after=shapekeys_after,
            shapekeys_removed=[name for name in shapekeys_before if name not in shapekeys_after],
            shapekeys_added=[name for name in shapekeys_after if name not in shapekeys_before],
            refit_requested=refit_requested,
            refit_performed=refit_performed,
            refit_incomplete_reason=refit_incomplete_reason,
            # Reported whenever the fit was not brought up to date, including
            # the partial refit above: a tool that moves a body under fitted
            # clothes and says nothing has told the caller something false by
            # omission.
            assets_possibly_stale=None if refit_performed else dict(
                mesh_assets=mesh_assets,
                mesh_asset_count=len(mesh_assets),
                rig_attached=rig is not None,
                rig_name=None if rig is None else rig.name,
            ),
            message="".join(message_parts),
        )
