"""
Payload for ``mpfb_symmetrize_targets``: copy one side's modeling onto the other.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap and the
``target_categories.py`` shared fragment (see ``mpfbmcp.codegen.assemble``). A
linter will flag several names as undefined because the assembler binds them
ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``,
  ``direction``, ``section``, ``dry_run``, ``prune`` and ``refit``.
- ``_MPFB_SERVICES`` and ``sys`` - from the raising bootstrap.
- ``TARGET_SECTIONS``, ``KNOWN_SECTIONS``, ``find_section``,
  ``category_is_opposed``, ``target_names_for``, ``resolve_target_path`` - from
  the shared fragment, whose docstring explains what a category is.

**MPFB has no equivalent of this operation.** Its ``symmetry`` setting only
affects changes made while it is switched on - its own property description says
in so many words that toggling it does not affect previously set values - so a
character that has already drifted asymmetric cannot be repaired through MPFB's
UI except by dragging every slider by hand. This is therefore a deliberate
addition rather than a wrapper.

**The walk is over categories, not over shape key names.** Pairing ``l-foo``
with ``r-foo`` by string manipulation would be a guess; the ``opposites`` table
names all four targets of a sided category explicitly, and a category with
``has_left_and_right: false`` has no partner at all. So the categories are
walked and the shape keys are consulted only for their values.

Writing follows ``_set_opposed_modifier_value()`` statement for statement, the
same as ``set_targets.py``: the opposing target is zeroed first - both of them
when the value is at zero - and only then is the selected one set or loaded.

Unlike ``mpfb_set_targets``, a category whose file cannot be found is **skipped
rather than fatal**. This tool is asked to make a character symmetric rather
than to apply a specific list, so one unreachable target is a fact to report
about that category, not a reason to leave the rest of the body asymmetric.
"""

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
TargetService = _MPFB_SERVICES["TargetService"]
HumanService = _MPFB_SERVICES["HumanService"]

# MPFB's own threshold, from _set_opposed_modifier_value() and prune_shapekeys().
EPSILON = 0.0001


def encoded(name):
    try:
        return str(TargetService.encode_shapekey_name(name))
    except Exception:  # pylint: disable=broad-except
        return str(name)


def key_blocks_of(basemesh):
    keys = basemesh.data.shape_keys
    if keys is None or keys.key_blocks is None:
        return []
    return list(keys.key_blocks)


def present_name(basemesh, target_name):
    """The name this target is stored under on the mesh, or None.

    has_target() answers the same question, but a caller that only knows "yes"
    cannot then write: set_target_value() matches the raw name only, while
    has_target() also matches the encoded one.
    """
    if not target_name:
        return None
    names = set(str(block.name) for block in key_blocks_of(basemesh))
    if str(target_name) in names:
        return str(target_name)
    encoded_name = encoded(target_name)
    if encoded_name in names:
        return encoded_name
    return None


def value_of(basemesh, stored_name):
    if not stored_name:
        return None
    for block in key_blocks_of(basemesh):
        if str(block.name) == stored_name:
            return float(block.value)
    return None


def shapekey_names(basemesh):
    return [str(block.name) for block in key_blocks_of(basemesh)]


def modifier_value(basemesh, category, side):
    """One category's slider reading, as _get_opposed_modifier_value() computes it."""
    if category_is_opposed(category):
        positive = target_names_for(category, side, "positive")
        negative = target_names_for(category, side, "negative")
        stored = present_name(basemesh, positive)
        if stored is not None:
            return value_of(basemesh, stored)
        stored = present_name(basemesh, negative)
        if stored is not None:
            return -value_of(basemesh, stored)
        return 0.0
    stored = present_name(basemesh, target_names_for(category, side, "positive"))
    if stored is None:
        return 0.0
    return value_of(basemesh, stored)


def write_side(basemesh, section_name, category, side, value, prune):
    """Apply one value to one side, in MPFB's order. Returns the targets touched."""
    touched = []
    if category_is_opposed(category):
        positive = target_names_for(category, side, "positive")
        negative = target_names_for(category, side, "negative")

        if value < EPSILON:
            stored = present_name(basemesh, positive)
            if stored is not None:
                previous = value_of(basemesh, stored)
                TargetService.set_target_value(
                    basemesh, stored, 0.0, delete_target_on_zero=prune)
                touched.append({
                    "target": positive, "polarity": "positive",
                    "previous_value": previous,
                    "new_value": value_of(basemesh, present_name(basemesh, positive)),
                    "loaded_from": None,
                })
        if value > -EPSILON:
            stored = present_name(basemesh, negative)
            if stored is not None:
                previous = value_of(basemesh, stored)
                TargetService.set_target_value(
                    basemesh, stored, 0.0, delete_target_on_zero=prune)
                touched.append({
                    "target": negative, "polarity": "negative",
                    "previous_value": previous,
                    "new_value": value_of(basemesh, present_name(basemesh, negative)),
                    "loaded_from": None,
                })

        wanted = []
        if value > 0.0:
            wanted.append(("positive", positive, value))
        if value < 0.0:
            wanted.append(("negative", negative, abs(value)))
    else:
        wanted = [("positive", target_names_for(category, side, "positive"), value)]

    for polarity, target_name, weight in wanted:
        stored = present_name(basemesh, target_name)
        if stored is None:
            path, _resolved_by = resolve_target_path(section_name, category, target_name)
            TargetService.load_target(basemesh, path, weight=weight, name=target_name)
            touched.append({
                "target": target_name, "polarity": polarity,
                "previous_value": None,
                "new_value": value_of(basemesh, present_name(basemesh, target_name)),
                "loaded_from": path,
            })
        else:
            previous = value_of(basemesh, stored)
            TargetService.set_target_value(
                basemesh, stored, weight, delete_target_on_zero=prune)
            touched.append({
                "target": target_name, "polarity": polarity,
                "previous_value": previous,
                "new_value": value_of(basemesh, present_name(basemesh, target_name)),
                "loaded_from": None,
            })
    return touched


def loadable(basemesh, section_name, category, side, value):
    """Whether every file this write might need is reachable.

    Checked before anything is written, so that a category whose target file is
    missing is reported as skipped rather than raising an IOError out of
    load_target() with half the body already mirrored.
    """
    if category_is_opposed(category):
        wanted = []
        if value > 0.0:
            wanted.append(target_names_for(category, side, "positive"))
        if value < 0.0:
            wanted.append(target_names_for(category, side, "negative"))
    else:
        wanted = [target_names_for(category, side, "positive")]
    for target_name in wanted:
        if not target_name:
            return False
        if present_name(basemesh, target_name) is not None:
            continue
        path, _resolved_by = resolve_target_path(section_name, category, target_name)
        if path is None:
            return False
    return True


def mesh_assets_of(basemesh):
    return [asset.name for asset in ObjectService.find_related_mesh_assets(basemesh)]


def rig_refit_blocker(rig):
    """Why HumanService.refit() would leave this rig untouched, or None.

    refit() reports this case through an ``operator`` it will not be given here,
    and otherwise returns having refitted the mesh assets but not the rig.
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
direction = PARAMS["direction"]
requested_section = PARAMS["section"]
dry_run = PARAMS["dry_run"]
prune = PARAMS["prune"]
refit_requested = PARAMS["refit"]

source_side = "left" if direction == "left_to_right" else "right"
destination_side = "right" if direction == "left_to_right" else "left"

subject_resolved_by = "active" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
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
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if basemesh is None:
        message = ("'" + subject.name + "' has no MakeHuman basemesh among its nearest relatives, "
                   "so there is nothing to symmetrize. Call mpfb_get_object_info to see what it "
                   "is related to.")

if basemesh is None:
    result = dict(
        found=False,
        ready=False,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None,
        direction=direction,
        dry_run=dry_run,
        changed=[],
        already_symmetric=[],
        skipped=[],
        message=message,
    )
else:
    matched_section = None
    section_recognized = True
    if requested_section is not None:
        matched_section = find_section(requested_section)
        section_recognized = matched_section is not None

    blocked_by = None
    if not section_recognized:
        blocked_by = "unknown_section"
        message = ("No target section called '" + str(requested_section) + "', so nothing was "
                   "changed. See 'known_sections'.")
    elif basemesh.mode != "OBJECT":
        blocked_by = "not_object_mode"
        message = ("The basemesh '" + basemesh.name + "' is in " + str(basemesh.mode) + " mode. "
                   "Loading a target requires OBJECT mode - MPFB asserts on it - so nothing was "
                   "changed. Leave edit mode and call again.")
    elif not TargetService.has_any_shapekey(basemesh):
        blocked_by = "no_shapekeys"
        message = ("The basemesh '" + basemesh.name + "' has no shape keys at all, so there is "
                   "nothing to symmetrize. This mesh carries MPFB properties but was not built "
                   "by MPFB.")

    if blocked_by is not None:
        result = dict(
            found=True,
            ready=False,
            blocked_by=blocked_by,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            direction=direction,
            section=requested_section,
            section_recognized=section_recognized,
            known_sections=KNOWN_SECTIONS,
            dry_run=dry_run,
            changed=[],
            already_symmetric=[],
            skipped=[],
            message=message,
        )
    else:
        section_names = KNOWN_SECTIONS
        if matched_section is not None:
            section_names = [matched_section]

        # Everything is measured before anything is written, so that a dry run
        # and a real run report the same set of changes.
        planned = []
        already_symmetric = []
        skipped = []
        for section_name in section_names:
            for category in TARGET_SECTIONS[section_name]["categories"]:
                if not category.get("has_left_and_right"):
                    continue
                source_value = modifier_value(basemesh, category, source_side)
                destination_value = modifier_value(basemesh, category, destination_side)
                entry = {
                    "section": section_name,
                    "category": str(category["name"]),
                    "source_side": source_side,
                    "destination_side": destination_side,
                    "source_value": round(source_value, 6),
                    "destination_value_before": round(destination_value, 6),
                }
                if abs(source_value - destination_value) <= EPSILON:
                    already_symmetric.append(entry)
                    continue
                if not loadable(basemesh, section_name, category, destination_side, source_value):
                    entry["reason"] = "target_file_not_found"
                    skipped.append(entry)
                    continue
                planned.append((entry, section_name, category, source_value))

        changed = []
        refit_incomplete_reason = None
        refit_performed = False
        rig = ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
        shapekeys_before = shapekey_names(basemesh)
        shapekeys_after = list(shapekeys_before)

        if dry_run:
            for entry, _section_name, _category, source_value in planned:
                reported = dict(entry)
                reported["destination_value_after"] = round(source_value, 6)
                reported["targets"] = []
                changed.append(reported)
        elif planned:
            previous_active = bpy.context.view_layer.objects.active
            basemesh_was_selected = bool(basemesh.select_get())
            try:
                ObjectService.activate_blender_object(basemesh)
                for entry, section_name, category, source_value in planned:
                    touched = write_side(basemesh, section_name, category,
                                         destination_side, source_value, prune)
                    reported = dict(entry)
                    reported["destination_value_after"] = round(
                        modifier_value(basemesh, category, destination_side), 6)
                    reported["targets"] = touched
                    changed.append(reported)
                if refit_requested:
                    refit_incomplete_reason = rig_refit_blocker(rig)
                    HumanService.refit(basemesh)
                    refit_performed = refit_incomplete_reason is None
            finally:
                if not basemesh_was_selected:
                    basemesh.select_set(False)
                bpy.context.view_layer.objects.active = previous_active
            shapekeys_after = shapekey_names(basemesh)

        mesh_assets = mesh_assets_of(basemesh)

        # Built by concatenation rather than the repo's usual .format(): a
        # payload file must contain no empty brace pair anywhere, since that is
        # what a substitution point looks like. tests/test_codegen.py enforces it.
        message_parts = []
        if dry_run:
            message_parts.append(
                "Dry run: " + str(len(changed)) + " category/categories would be changed, "
                + str(len(already_symmetric)) + " are already symmetric. **Nothing was "
                "written.** Call again without dry_run to apply exactly these changes.")
        else:
            message_parts.append(
                "Copied " + source_side + " to " + destination_side + " for "
                + str(len(changed)) + " category/categories on basemesh '" + basemesh.name
                + "'; " + str(len(already_symmetric)) + " were already symmetric.")
        if skipped:
            message_parts.append(
                " " + str(len(skipped)) + " category/categories were skipped because the target "
                "file that would have to be loaded could not be found.")
        if not dry_run and not changed and refit_requested:
            # Nothing moved, so nothing is out of fit. Saying so is cheaper than
            # letting the caller wonder why refit_performed came back false.
            message_parts.append(
                " No refit was needed, because nothing was changed.")
        if not dry_run and changed:
            if refit_performed:
                message_parts.append(" Assets and rig were refitted to the new shape.")
            elif refit_incomplete_reason is not None:
                message_parts.append(
                    " Mesh assets were refitted, but the rig was not: " + refit_incomplete_reason)
            elif mesh_assets or rig is not None:
                message_parts.append(
                    " Nothing was refitted, so the " + str(len(mesh_assets)) + " mesh asset(s)"
                    + (" and the rig" if rig is not None else "")
                    + " on this character are now fitted to the old shape. Call mpfb_refit_human "
                      "when the modeling is done.")

        result = dict(
            found=True,
            ready=True,
            blocked_by=None,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            direction=direction,
            source_side=source_side,
            destination_side=destination_side,
            section=requested_section,
            section_recognized=section_recognized,
            known_sections=KNOWN_SECTIONS,
            dry_run=dry_run,
            prune=prune,
            changed=changed,
            changed_count=len(changed),
            already_symmetric=already_symmetric,
            already_symmetric_count=len(already_symmetric),
            skipped=skipped,
            shapekeys_before=shapekeys_before,
            shapekeys_after=shapekeys_after,
            shapekeys_removed=[name for name in shapekeys_before if name not in shapekeys_after],
            shapekeys_added=[name for name in shapekeys_after if name not in shapekeys_before],
            refit_requested=refit_requested,
            refit_performed=refit_performed,
            refit_incomplete_reason=refit_incomplete_reason,
            assets_possibly_stale=None if (refit_performed or dry_run or not changed) else dict(
                mesh_assets=mesh_assets,
                mesh_asset_count=len(mesh_assets),
                rig_attached=rig is not None,
                rig_name=None if rig is None else rig.name,
            ),
            message="".join(message_parts),
        )
