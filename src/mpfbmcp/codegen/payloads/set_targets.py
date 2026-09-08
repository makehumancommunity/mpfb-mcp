"""
Payload for ``mpfb_set_targets``: resolve the whole batch, then apply it.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap and the
``target_categories.py``, ``refit_blocker.py`` and ``performed.py`` shared
fragments (see ``mpfbmcp.codegen.assemble``). A linter will flag several names
as undefined because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, ``modifiers``,
  ``targets``, ``symmetry``, ``prune`` and ``refit``.
- ``_MPFB_SERVICES`` and ``sys`` - from the raising bootstrap.
- ``TARGET_SECTIONS``, ``KNOWN_SECTIONS``, ``find_section``, ``find_category``,
  ``category_names_in``, ``category_is_opposed``, ``category_value_range``,
  ``target_names_for``, ``resolve_target_path``, ``lookup_target`` - from the
  shared fragment, whose docstring explains what a category is.
- ``with_performed()`` - from the shared fragment ``performed.py``, named by
  every mutating payload. It stamps the uniform ``performed`` flag onto the
  finished answer, in the last line of this file.
- ``rig_refit_is_blocked()`` - from the shared fragment ``refit_blocker.py``,
  named by every payload that refits. It answers whether
  ``HumanService.refit()`` would leave the rig untouched; the sentence saying
  so is written here, since this tool's tense is not the others'.

**Two phases, and the split is the point.** Everything is resolved first -
sections, categories, sides, ranges and the file each target would be loaded
from - and only if *nothing* failed does anything get written. A batch of thirty
changes with one typo in it applies zero of them: a half-applied batch leaves a
character in a state neither the agent nor the user can describe, and the
response format cannot usefully report which half landed.

The application follows ``_set_opposed_modifier_value()`` statement for
statement, because its order matters. The opposing target is zeroed *first* -
both of them when the value is near zero - and only then is the selected one set
or loaded. Doing it the other way leaves both halves of a pair briefly non-zero
and, with pruning on, deletes the wrong one.

Three quirks of MPFB's own writing path are worked around here rather than
inherited:

- ``set_target_value()`` on a shape key that is not on the mesh is a **silent
  no-op**: it walks the key blocks looking for an exact name match and does
  nothing when there is none. It neither loads the target nor raises. So every
  set is preceded by a presence check and, when absent, a ``load_target()`` with
  the value as its ``weight``.
- ``has_target()`` also matches the *encoded* form of a name, while
  ``set_target_value()`` and ``get_target_value()`` match the raw name only. So
  the presence check reports *which* name is actually on the mesh, and that name
  is what gets written.
- ``get_target_value()`` returns ``0.0`` for a name that does not exist, which is
  indistinguishable from a target that exists at zero. Existence is therefore
  reported separately from value, as ``present_before``.

``reapply_all_details()`` is deliberately never called. It resolves every stack
entry back to a file through ``target_full_path()``, which cannot resolve an
encoded name and which falls back to a prefix match - so it can silently drop a
target or load a differently-named one. Nothing here needs it.
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
    """The name this target is actually stored under on the mesh, or None.

    has_target() answers the yes/no question the same way, but a caller that
    only knows "yes" cannot then write, because set_target_value() matches the
    raw name only and would silently do nothing for an encoded one.
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


def write_value(basemesh, stored_name, value, prune):
    """set_target_value() on a name known to be on the mesh."""
    TargetService.set_target_value(basemesh, stored_name, value, delete_target_on_zero=prune)


def load_value(basemesh, path, value, target_name):
    """load_target() under an explicit name, as MPFB's own panel does.

    The name is passed rather than derived, because deriving it would go through
    filename_to_shapekey_name(), which strips '.gz' - while MPFB's category name
    for a gzipped custom target does not. Passing it keeps the shape key called
    what MPFB's own slider expects it to be called.
    """
    TargetService.load_target(basemesh, path, weight=value, name=target_name)


def touch_record(target_name, side, polarity, previous_value, present_before,
                 new_value, loaded_from, pruned):
    return {
        "target": target_name,
        "side": side,
        "polarity": polarity,
        "present_before": present_before,
        "previous_value": previous_value,
        "new_value": new_value,
        "loaded_from": loaded_from,
        "pruned": pruned,
    }


def sides_to_apply(category, side, symmetry):
    """The requested side, plus its mirror when symmetry is on.

    MPFB consults its own 'symmetry' setting only inside
    _set_opposed_modifier_value(), so a sided category without 'opposites' would
    not be mirrored there. On stock data that difference cannot be observed -
    every sided category in target.json carries an opposites table, and every
    synthesized user category is unsided - so the mirror is applied to any sided
    category here rather than reproducing a distinction with no cases.
    """
    if not symmetry or not category.get("has_left_and_right"):
        return [side]
    if side == "left":
        return ["left", "right"]
    if side == "right":
        return ["right", "left"]
    return [side]


def resolve_modifier(index, entry):
    """One requested category change, resolved to the writes it implies."""
    section_name = find_section(entry.get("section"))
    if section_name is None:
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "unknown_section",
            "section": entry.get("section"),
            "category": entry.get("category"),
            "message": ("No target section called '" + str(entry.get("section"))
                        + "'. See 'known_sections'."),
            "known_sections": KNOWN_SECTIONS,
        })

    category = find_category(section_name, entry.get("category"))
    if category is None:
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "unknown_category",
            "section": section_name,
            "category": entry.get("category"),
            "message": ("Section '" + section_name + "' has no category called '"
                        + str(entry.get("category")) + "'. See "
                        "'known_categories_in_section'."),
            "known_categories_in_section": {section_name: category_names_in(section_name)},
        })

    sided = bool(category.get("has_left_and_right"))
    requested_side = entry.get("side")
    if requested_side is None:
        requested_side = "unsided" if not sided else None

    if sided and (requested_side is None or requested_side == "unsided"):
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "side_required",
            "section": section_name,
            "category": str(category["name"]),
            "message": ("Category '" + str(category["name"]) + "' in section '" + section_name
                        + "' has separate left and right targets, so 'side' must be 'left' or "
                          "'right'. Defaulting it would be a coin flip."),
        })
    if not sided and requested_side != "unsided":
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "side_not_applicable",
            "section": section_name,
            "category": str(category["name"]),
            "message": ("Category '" + str(category["name"]) + "' in section '" + section_name
                        + "' has no left and right variants, so 'side' must be omitted or "
                          "'unsided'."),
        })

    low, high = category_value_range(category)
    value = float(entry.get("value"))
    if value < low or value > high:
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "value_out_of_range",
            "section": section_name,
            "category": str(category["name"]),
            "message": ("Category '" + str(category["name"]) + "' takes a value between "
                        + str(low) + " and " + str(high) + " - it is "
                        + ("a pair of opposing targets" if category_is_opposed(category)
                           else "a single target with no opposite")
                        + " - but " + str(value) + " was given."),
        })

    # Which files might have to be read off disk. Resolved now rather than at
    # write time, so a missing file is a resolution error rather than an IOError
    # half way through a batch.
    plan = []
    for side in sides_to_apply(category, requested_side, symmetry):
        if category_is_opposed(category):
            positive = target_names_for(category, side, "positive")
            negative = target_names_for(category, side, "negative")
            wanted = []
            if value > 0.0:
                wanted.append(("positive", positive, value))
            if value < 0.0:
                wanted.append(("negative", negative, abs(value)))
            zeroed = [("positive", positive), ("negative", negative)]
        else:
            single = target_names_for(category, side, "positive")
            # MPFB loads a simple target even at zero, when it is not already on
            # the mesh; reproduced rather than optimised away, since the point of
            # this tool is that the slider reads back the same value afterwards.
            wanted = [("positive", single, value)]
            zeroed = []

        step = {"side": side, "wanted": [], "zeroed": zeroed,
                "opposed": category_is_opposed(category)}
        for polarity, target_name, weight in wanted:
            if not target_name:
                return (None, {
                    "index": index,
                    "kind": "modifier",
                    "reason": "no_such_target_in_category",
                    "section": section_name,
                    "category": str(category["name"]),
                    "message": ("Category '" + str(category["name"]) + "' names no "
                                + polarity + " target for side '" + side + "'."),
                })
            path, resolved_by = resolve_target_path(section_name, category, target_name)
            step["wanted"].append({
                "polarity": polarity,
                "target": target_name,
                "weight": weight,
                "path": path,
                "path_resolved_by": resolved_by,
            })
        plan.append(step)

    return ({
        "index": index,
        "kind": "modifier",
        "section": section_name,
        "category": str(category["name"]),
        "category_object": category,
        "side": requested_side,
        "value": value,
        "opposed": category_is_opposed(category),
        "plan": plan,
        # True when MPFB's own category name for this file is not the name
        # mpfb_list_targets reports - which happens for a gzipped custom target,
        # since MPFB's naming does not strip '.gz'.
        "name_diverges_from_catalogue": bool(
            category.get("name_diverges_from_catalogue")),
        "catalogue_shapekey_name": category.get("shapekey_name"),
    }, None)


def resolve_raw_target(index, entry, basemesh):
    """One requested shape-key-level change, resolved to a write or a load."""
    shapekey_name = str(entry.get("shapekey_name"))
    value = float(entry.get("value"))

    stored = present_name(basemesh, shapekey_name)
    if stored is not None:
        return ({
            "index": index,
            "kind": "target",
            "shapekey_name": shapekey_name,
            "stored_name": stored,
            "value": value,
            "path": None,
            "path_resolved_by": None,
        }, None)

    found = lookup_target(shapekey_name)
    if found is None or not found.get("path"):
        return (None, {
            "index": index,
            "kind": "target",
            "reason": "unknown_target",
            "shapekey_name": shapekey_name,
            "message": ("No shape key called '" + shapekey_name + "' is on this basemesh, and no "
                        "target file of that name could be found to load. Call mpfb_list_targets "
                        "and use the 'shapekey_name' it reports - for a name over 60 characters "
                        "that is not the filename."),
        })
    return ({
        "index": index,
        "kind": "target",
        "shapekey_name": shapekey_name,
        "stored_name": None,
        "value": value,
        "path": found["path"],
        "path_resolved_by": found["resolved_by"],
    }, None)


def apply_modifier(basemesh, resolved, prune):
    """_set_opposed_modifier_value() / _set_simple_modifier_value(), per side."""
    touched = []
    for step in resolved["plan"]:
        side = step["side"]
        value = resolved["value"]

        if step["opposed"]:
            positive = None
            negative = None
            for polarity, target_name in step["zeroed"]:
                if polarity == "positive":
                    positive = target_name
                else:
                    negative = target_name

            # Order matters, and this is MPFB's: clear the opposing target
            # first - both of them when the value is at zero - and only then set
            # or load the selected one.
            if value < EPSILON:
                stored = present_name(basemesh, positive)
                if stored is not None:
                    previous = value_of(basemesh, stored)
                    write_value(basemesh, stored, 0.0, prune)
                    touched.append(touch_record(
                        positive, side, "positive", previous, True,
                        value_of(basemesh, present_name(basemesh, positive)),
                        None, prune))
            if value > -EPSILON:
                stored = present_name(basemesh, negative)
                if stored is not None:
                    previous = value_of(basemesh, stored)
                    write_value(basemesh, stored, 0.0, prune)
                    touched.append(touch_record(
                        negative, side, "negative", previous, True,
                        value_of(basemesh, present_name(basemesh, negative)),
                        None, prune))

        for wanted in step["wanted"]:
            target_name = wanted["target"]
            weight = wanted["weight"]
            stored = present_name(basemesh, target_name)
            if stored is None:
                load_value(basemesh, wanted["path"], weight, target_name)
                touched.append(touch_record(
                    target_name, side, wanted["polarity"], None, False,
                    value_of(basemesh, present_name(basemesh, target_name)),
                    wanted["path"], False))
            else:
                previous = value_of(basemesh, stored)
                write_value(basemesh, stored, weight, prune)
                after_name = present_name(basemesh, target_name)
                touched.append(touch_record(
                    target_name, side, wanted["polarity"], previous, True,
                    value_of(basemesh, after_name), None,
                    prune and after_name is None))
    return touched


def apply_raw_target(basemesh, resolved, prune):
    shapekey_name = resolved["shapekey_name"]
    value = resolved["value"]
    stored = present_name(basemesh, shapekey_name)
    if stored is None:
        load_value(basemesh, resolved["path"], value, shapekey_name)
        return [touch_record(
            shapekey_name, None, None, None, False,
            value_of(basemesh, present_name(basemesh, shapekey_name)),
            resolved["path"], False)]
    previous = value_of(basemesh, stored)
    write_value(basemesh, stored, value, prune)
    after_name = present_name(basemesh, shapekey_name)
    return [touch_record(
        shapekey_name, None, None, previous, True,
        value_of(basemesh, after_name), None, prune and after_name is None)]


def mesh_assets_of(basemesh):
    return [asset.name for asset in ObjectService.find_related_mesh_assets(basemesh)]


def rig_refit_blocker(rig):
    """Why HumanService.refit() would leave this rig untouched, or None.

    The condition is ``rig_refit_is_blocked()`` from the shared fragment, which
    every tool that refits asks; the wording is this tool's own, because here
    the refit has not happened yet and the sentence is a prediction rather than
    a report. Asking at all is what keeps the tool from claiming a refit it did
    not perform.
    """
    if not rig_refit_is_blocked(rig):
        return None
    return ("The rig '" + rig.name + "' is a generated Rigify rig and no meta rig is left in the "
            "scene, so it cannot be refitted to the new body shape. Set the Rigify sub-panel's "
            "'Meta-rig' option to Keep or Hide before generating, to allow refitting afterwards.")


requested_name = PARAMS["name"]
requested_modifiers = PARAMS["modifiers"]
requested_targets = PARAMS["targets"]
symmetry = PARAMS["symmetry"]
prune = PARAMS["prune"]
refit_requested = PARAMS["refit"]

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
                   "so there are no targets to set. Call mpfb_get_object_info to see what it is "
                   "related to.")

if basemesh is None:
    result = dict(
        found=False,
        ready=False,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None,
        applied=[],
        resolution_errors=[],
        message=message,
    )
else:
    blocked_by = None
    if basemesh.mode != "OBJECT":
        blocked_by = "not_object_mode"
        message = ("The basemesh '" + basemesh.name + "' is in " + str(basemesh.mode) + " mode. "
                   "Loading a target requires OBJECT mode - MPFB asserts on it - so nothing was "
                   "changed. Leave edit mode and call again.")
    elif not TargetService.has_any_shapekey(basemesh):
        blocked_by = "no_shapekeys"
        message = ("The basemesh '" + basemesh.name + "' has no shape keys at all, so it has no "
                   "target stack to change and nothing was changed. This mesh carries MPFB "
                   "properties but was not built by MPFB.")

    if blocked_by is not None:
        result = dict(
            found=True,
            ready=False,
            blocked_by=blocked_by,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            applied=[],
            resolution_errors=[],
            message=message,
        )
    elif not requested_modifiers and not requested_targets:
        result = dict(
            found=True,
            ready=True,
            blocked_by=None,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            applied=[],
            resolution_errors=[],
            refit_requested=refit_requested,
            refit_performed=False,
            message=("Neither 'modifiers' nor 'targets' named anything, so nothing was changed. "
                     "Call mpfb_get_target_stack to see what is currently set, and "
                     "mpfb_list_targets to see what could be."),
        )
    else:
        # Phase one: resolve everything, write nothing.
        resolved_entries = []
        resolution_errors = []
        for index, entry in enumerate(requested_modifiers or []):
            resolved, error = resolve_modifier(index, entry)
            if error is not None:
                resolution_errors.append(error)
            else:
                resolved_entries.append(resolved)
        for index, entry in enumerate(requested_targets or []):
            resolved, error = resolve_raw_target(index, entry, basemesh)
            if error is not None:
                resolution_errors.append(error)
            else:
                resolved_entries.append(resolved)

        # A file that has to be read but is not there is a resolution failure
        # too, not an IOError half way through the batch. Rebuilt rather than
        # removed from in place: two unreachable targets in one entry must
        # produce two errors and drop that entry exactly once.
        still_resolved = []
        for resolved in resolved_entries:
            unreachable = []
            if resolved["kind"] == "modifier":
                for step in resolved["plan"]:
                    for wanted in step["wanted"]:
                        if wanted["path"] is not None:
                            continue
                        if present_name(basemesh, wanted["target"]) is not None:
                            # Already on the mesh, so nothing has to be read.
                            continue
                        unreachable.append(wanted["target"])
            for target_name in unreachable:
                resolution_errors.append({
                    "index": resolved["index"],
                    "kind": "modifier",
                    "reason": "target_file_not_found",
                    "section": resolved["section"],
                    "category": resolved["category"],
                    "message": ("Target '" + str(target_name) + "' is not on this basemesh and "
                                "no '.target.gz' or '.target' file for it was found under "
                                "section '" + str(resolved["section"]) + "'."),
                })
            if not unreachable:
                still_resolved.append(resolved)
        resolved_entries = still_resolved

        if resolution_errors:
            # All or nothing. Twenty-nine of thirty changes would leave a
            # character in a state the response cannot describe and the caller
            # cannot retry from.
            result = dict(
                found=True,
                ready=True,
                blocked_by=None,
                subject_name=subject.name,
                subject_resolved_by=subject_resolved_by,
                basemesh_name=basemesh.name,
                applied=[],
                resolution_errors=resolution_errors,
                refit_requested=refit_requested,
                refit_performed=False,
                message=(str(len(resolution_errors)) + " of "
                         + str(len(requested_modifiers or []) + len(requested_targets or []))
                         + " requested change(s) could not be resolved, so **nothing at all was "
                           "applied**. Fix the entries listed in 'resolution_errors' and call "
                           "again with the whole batch."),
            )
        else:
            shapekeys_before = shapekey_names(basemesh)

            # MPFB's own slider callback activates the basemesh before writing,
            # and the refit below reaches bpy.ops through ClothesService. Put
            # back what was borrowed: the user is looking at this scene.
            previous_active = bpy.context.view_layer.objects.active
            basemesh_was_selected = bool(basemesh.select_get())

            applied = []
            try:
                ObjectService.activate_blender_object(basemesh)
                for resolved in resolved_entries:
                    if resolved["kind"] == "modifier":
                        touched = apply_modifier(basemesh, resolved, prune)
                        applied.append({
                            "kind": "modifier",
                            "index": resolved["index"],
                            "section": resolved["section"],
                            "category": resolved["category"],
                            "side": resolved["side"],
                            "value": resolved["value"],
                            "opposed": resolved["opposed"],
                            "symmetry_applied": len(resolved["plan"]) > 1,
                            "targets": touched,
                            "name_diverges_from_catalogue":
                                resolved["name_diverges_from_catalogue"],
                            "catalogue_shapekey_name": resolved["catalogue_shapekey_name"],
                        })
                    else:
                        touched = apply_raw_target(basemesh, resolved, prune)
                        applied.append({
                            "kind": "target",
                            "index": resolved["index"],
                            "shapekey_name": resolved["shapekey_name"],
                            "value": resolved["value"],
                            "path_resolved_by": resolved["path_resolved_by"],
                            "targets": touched,
                        })

                rig = ObjectService.find_object_of_type_amongst_nearest_relatives(
                    basemesh, "Skeleton")
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

            shapekeys_after = shapekey_names(basemesh)
            mesh_assets = mesh_assets_of(basemesh)
            diverging = [entry for entry in applied
                         if entry.get("name_diverges_from_catalogue")]

            # Built by concatenation rather than the repo's usual .format(): a
            # payload file must contain no empty brace pair anywhere, since that
            # is what a substitution point looks like. tests/test_codegen.py
            # enforces it.
            message_parts = [
                "Applied " + str(len(applied)) + " change(s) to basemesh '" + basemesh.name
                + "', touching " + str(sum(len(entry["targets"]) for entry in applied))
                + " target(s)."]
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
            if diverging:
                message_parts.append(
                    " Note that " + str(len(diverging)) + " of these categories is a gzipped "
                    "custom target, which MPFB names without stripping '.gz' - so the shape key "
                    "is not called what mpfb_list_targets reports as its 'shapekey_name'. The "
                    "name MPFB's own slider uses was written.")

            result = dict(
                found=True,
                ready=True,
                blocked_by=None,
                subject_name=subject.name,
                subject_resolved_by=subject_resolved_by,
                basemesh_name=basemesh.name,
                applied=applied,
                resolution_errors=[],
                prune=prune,
                symmetry=symmetry,
                shapekeys_before=shapekeys_before,
                shapekeys_after=shapekeys_after,
                shapekeys_removed=[name for name in shapekeys_before
                                   if name not in shapekeys_after],
                shapekeys_added=[name for name in shapekeys_after
                                 if name not in shapekeys_before],
                refit_requested=refit_requested,
                refit_performed=refit_performed,
                refit_incomplete_reason=refit_incomplete_reason,
                # Reported whenever the fit was not brought up to date: a tool
                # that moves a body under fitted clothes and says nothing has
                # told the caller something false by omission.
                assets_possibly_stale=None if refit_performed else dict(
                    mesh_assets=mesh_assets,
                    mesh_asset_count=len(mesh_assets),
                    rig_attached=rig is not None,
                    rig_name=None if rig is None else rig.name,
                ),
                message="".join(message_parts),
            )


# The verb is "applied", one entry per change, and it is empty in every branch
# that wrote nothing - including the all-or-nothing resolution failure. See
# codegen/shared/performed.py.
result = with_performed(result, result.get("applied"))
