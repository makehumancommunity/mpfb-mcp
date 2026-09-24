"""
``set_targets``: resolve the whole batch, then apply it - or apply none of it.

**The one batched command in the package**, and the reason it is batched is that
a round trip used to cost ~250 ms while writing a target costs milliseconds.
The bridge removes that cost, and the batching stays anyway, because the second
reason outlived the first: a caller shaping a face makes thirty related changes,
and thirty independent calls is thirty chances to leave the character half
changed.

**Two phases, and the split is the point.** Everything is resolved first -
sections, categories, sides, ranges and the file each target would be loaded
from - and only if *nothing* failed does anything get written. A batch of thirty
changes with one typo in it applies zero of them: a half-applied batch leaves a
character in a state neither the agent nor the user can describe, and the
response format cannot usefully report which half landed. That is FR 032's
requirement 3 in its sharpest form, and it is a property of the *code* rather
than of the transport - nothing below the socket would enforce it.

The application follows MPFB's ``_set_opposed_modifier_value()`` statement for
statement, because its order matters. The opposing target is zeroed **first** -
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

The category table, the path resolution and the target index come from
[`shared/target_categories.py`](../shared/target_categories.py), the same module
``list_targets`` and ``get_target_stack`` read, so a category this command
refuses is not one that catalogue offered.

**Per-entry ranges are checked on mpfb-mcp's side as well as here**, and the two
checks are not the same check. The tool rejects a modifier outside -1.0..+1.0
and a raw target outside 0.0..1.0 without knowing which applies to a given
category; *which* range a category takes is only knowable inside Blender, and
that narrower check is :func:`_resolve_modifier`'s, reported as a resolution
error rather than raised.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
"""

# The local bindings below are spelled with MPFB's own capitalisation, which is
# what the program this replaced used, which is in turn what MPFB's own
# source uses.
# pylint: disable=invalid-name

__all__ = (
    "PARAMS",
    "SUMMARY",
    "set_targets",
)

from ..log import get_logger
from ..shared import selection
from ..shared import subject_resolution
from ..shared import target_categories
from ..shared import target_rollup
from ..shared.performed import with_performed
from ..shared.refit_blocker import rig_refit_is_blocked
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.settargets")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("modifiers", TYPE_ARRAY, default=(),
          description="One object per category slider: 'section', 'category', optional 'side' "
                      "('left', 'right' or 'unsided') and 'value'. The range depends on the "
                      "category and is reported as a resolution error when it is wrong."),
    Param("targets", TYPE_ARRAY, default=(),
          description="One object per raw shape key: 'shapekey_name' and 'value' (0.0-1.0). Use "
                      "the 'shapekey_name' list_targets reports, which for a name over 60 "
                      "characters is not the filename."),
    Param("symmetry", TYPE_BOOLEAN, default=False,
          description="Apply each sided category to both sides. MPFB's own symmetry setting."),
    Param("prune", TYPE_BOOLEAN, default=True,
          description="Delete a shape key whose value falls to zero. MPFB's own default."),
    Param("refit", TYPE_BOOLEAN, default=False,
          description="Re-fit clothes and the rig afterwards. False is MPFB's own default: a "
                      "refit is expensive, so make a batch of changes and call refit_human once."),
)

SUMMARY = "Set detail morph targets on a character, as one all-or-nothing batch."

# MPFB's own threshold, from _set_opposed_modifier_value() and prune_shapekeys().
EPSILON = 0.0001


def _touch_record(target_name, side, polarity, previous_value, present_before,
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


def _sides_to_apply(category, side, symmetry):
    """The requested side, plus its mirror when symmetry is on.

    MPFB consults its own 'symmetry' setting only inside
    ``_set_opposed_modifier_value()``, so a sided category without 'opposites'
    would not be mirrored there. On stock data that difference cannot be
    observed - every sided category in target.json carries an opposites table,
    and every synthesized user category is unsided - so the mirror is applied to
    any sided category here rather than reproducing a distinction with no cases.
    """
    if not symmetry or not category.get("has_left_and_right"):
        return [side]
    if side == "left":
        return ["left", "right"]
    if side == "right":
        return ["right", "left"]
    return [side]


def _resolve_modifier(tables, index, entry, symmetry):
    """One requested category change, resolved to the writes it implies."""
    section_name = target_categories.find_section(tables, entry.get("section"))
    if section_name is None:
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "unknown_section",
            "section": entry.get("section"),
            "category": entry.get("category"),
            "message": "No target section called '{!s}'. See 'known_sections'.".format(
                entry.get("section")),
            "known_sections": tables.known_sections,
        })

    category = target_categories.find_category(tables, section_name, entry.get("category"))
    if category is None:
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "unknown_category",
            "section": section_name,
            "category": entry.get("category"),
            "message": "Section '{:s}' has no category called '{!s}'. See "
                       "'known_categories_in_section'.".format(
                           section_name, entry.get("category")),
            "known_categories_in_section": {
                section_name: target_categories.category_names_in(tables, section_name)},
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
            "message": "Category '{:s}' in section '{:s}' has separate left and right targets, so "
                       "'side' must be 'left' or 'right'. Defaulting it would be a coin "
                       "flip.".format(str(category["name"]), section_name),
        })
    if not sided and requested_side != "unsided":
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "side_not_applicable",
            "section": section_name,
            "category": str(category["name"]),
            "message": "Category '{:s}' in section '{:s}' has no left and right variants, so "
                       "'side' must be omitted or 'unsided'.".format(
                           str(category["name"]), section_name),
        })

    low, high = target_categories.category_value_range(category)
    value = float(entry.get("value"))
    if value < low or value > high:
        return (None, {
            "index": index,
            "kind": "modifier",
            "reason": "value_out_of_range",
            "section": section_name,
            "category": str(category["name"]),
            "message": "Category '{:s}' takes a value between {!s} and {!s} - it is {:s} - but "
                       "{!s} was given.".format(
                           str(category["name"]), low, high,
                           "a pair of opposing targets"
                           if target_categories.category_is_opposed(category)
                           else "a single target with no opposite",
                           value),
        })

    # Which files might have to be read off disk. Resolved now rather than at
    # write time, so a missing file is a resolution error rather than an IOError
    # half way through a batch.
    plan = []
    for side in _sides_to_apply(category, requested_side, symmetry):
        if target_categories.category_is_opposed(category):
            positive = target_categories.target_names_for(category, side, "positive")
            negative = target_categories.target_names_for(category, side, "negative")
            wanted = []
            if value > 0.0:
                wanted.append(("positive", positive, value))
            if value < 0.0:
                wanted.append(("negative", negative, abs(value)))
            zeroed = [("positive", positive), ("negative", negative)]
        else:
            single = target_categories.target_names_for(category, side, "positive")
            # MPFB loads a simple target even at zero, when it is not already on
            # the mesh; reproduced rather than optimised away, since the point
            # of this command is that the slider reads back the same value
            # afterwards.
            wanted = [("positive", single, value)]
            zeroed = []

        step = {"side": side, "wanted": [], "zeroed": zeroed,
                "opposed": target_categories.category_is_opposed(category)}
        for polarity, target_name, weight in wanted:
            if not target_name:
                return (None, {
                    "index": index,
                    "kind": "modifier",
                    "reason": "no_such_target_in_category",
                    "section": section_name,
                    "category": str(category["name"]),
                    "message": "Category '{:s}' names no {:s} target for side '{:s}'.".format(
                        str(category["name"]), polarity, side),
                })
            path, resolved_by = target_categories.resolve_target_path(
                tables, section_name, category, target_name)
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
        "opposed": target_categories.category_is_opposed(category),
        "plan": plan,
        # True when MPFB's own category name for this file is not the name
        # list_targets reports - which happens for a gzipped custom target,
        # since MPFB's naming does not strip '.gz'.
        "name_diverges_from_catalogue": bool(category.get("name_diverges_from_catalogue")),
        "catalogue_shapekey_name": category.get("shapekey_name"),
    }, None)


def _resolve_raw_target(services, tables, target_service, index, entry, basemesh):
    """One requested shape-key-level change, resolved to a write or a load."""
    shapekey_name = str(entry.get("shapekey_name"))
    value = float(entry.get("value"))

    stored = target_rollup.present_name(target_service, basemesh, shapekey_name)
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

    found = target_categories.lookup_target(services, tables, shapekey_name)
    if found is None or not found.get("path"):
        return (None, {
            "index": index,
            "kind": "target",
            "reason": "unknown_target",
            "shapekey_name": shapekey_name,
            "message": "No shape key called '{:s}' is on this basemesh, and no target file of "
                       "that name could be found to load. Call mpfb_list_targets and use the "
                       "'shapekey_name' it reports - for a name over 60 characters that is not "
                       "the filename.".format(shapekey_name),
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


def _write_value(target_service, basemesh, stored_name, value, prune):
    """``set_target_value()`` on a name known to be on the mesh."""
    target_service.set_target_value(basemesh, stored_name, value, delete_target_on_zero=prune)


def _load_value(target_service, basemesh, path, value, target_name):
    """``load_target()`` under an explicit name, as MPFB's own panel does.

    The name is passed rather than derived, because deriving it would go through
    ``filename_to_shapekey_name()``, which strips '.gz' - while MPFB's category
    name for a gzipped custom target does not. Passing it keeps the shape key
    called what MPFB's own slider expects it to be called.
    """
    target_service.load_target(basemesh, path, weight=value, name=target_name)


def _apply_modifier(target_service, basemesh, resolved, prune):
    """``_set_opposed_modifier_value()`` / ``_set_simple_modifier_value()``, per side."""
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
                stored = target_rollup.present_name(target_service, basemesh, positive)
                if stored is not None:
                    previous = target_rollup.stored_value(basemesh, stored)
                    _write_value(target_service, basemesh, stored, 0.0, prune)
                    touched.append(_touch_record(
                        positive, side, "positive", previous, True,
                        target_rollup.stored_value(
                            basemesh, target_rollup.present_name(target_service, basemesh, positive)),
                        None, prune))
            if value > -EPSILON:
                stored = target_rollup.present_name(target_service, basemesh, negative)
                if stored is not None:
                    previous = target_rollup.stored_value(basemesh, stored)
                    _write_value(target_service, basemesh, stored, 0.0, prune)
                    touched.append(_touch_record(
                        negative, side, "negative", previous, True,
                        target_rollup.stored_value(
                            basemesh, target_rollup.present_name(target_service, basemesh, negative)),
                        None, prune))

        for wanted in step["wanted"]:
            target_name = wanted["target"]
            weight = wanted["weight"]
            stored = target_rollup.present_name(target_service, basemesh, target_name)
            if stored is None:
                _load_value(target_service, basemesh, wanted["path"], weight, target_name)
                touched.append(_touch_record(
                    target_name, side, wanted["polarity"], None, False,
                    target_rollup.stored_value(
                        basemesh, target_rollup.present_name(target_service, basemesh, target_name)),
                    wanted["path"], False))
            else:
                previous = target_rollup.stored_value(basemesh, stored)
                _write_value(target_service, basemesh, stored, weight, prune)
                after_name = target_rollup.present_name(target_service, basemesh, target_name)
                touched.append(_touch_record(
                    target_name, side, wanted["polarity"], previous, True,
                    target_rollup.stored_value(basemesh, after_name), None,
                    prune and after_name is None))
    return touched


def _apply_raw_target(target_service, basemesh, resolved, prune):
    shapekey_name = resolved["shapekey_name"]
    value = resolved["value"]
    stored = target_rollup.present_name(target_service, basemesh, shapekey_name)
    if stored is None:
        _load_value(target_service, basemesh, resolved["path"], value, shapekey_name)
        return [_touch_record(
            shapekey_name, None, None, None, False,
            target_rollup.stored_value(
                basemesh, target_rollup.present_name(target_service, basemesh, shapekey_name)),
            resolved["path"], False)]
    previous = target_rollup.stored_value(basemesh, stored)
    _write_value(target_service, basemesh, stored, value, prune)
    after_name = target_rollup.present_name(target_service, basemesh, shapekey_name)
    return [_touch_record(
        shapekey_name, None, None, previous, True,
        target_rollup.stored_value(basemesh, after_name), None, prune and after_name is None)]


def _rig_refit_blocker(services, rig):
    """Why HumanService.refit() would leave this rig untouched, or ``None``.

    The condition is ``rig_refit_is_blocked()`` from the shared module, which
    every command that refits asks; the wording is this command's own, because
    here the refit has not happened yet and the sentence is a prediction rather
    than a report.
    """
    if not rig_refit_is_blocked(services, rig):
        return None
    return ("The rig '{:s}' is a generated Rigify rig and no meta rig is left in the scene, so it "
            "cannot be refitted to the new body shape. Set the Rigify sub-panel's 'Meta-rig' "
            "option to Keep or Hide before generating, to allow refitting "
            "afterwards.".format(rig.name))


def _precondition(target_service, basemesh):
    """Which state blocks a write, and the sentence for it."""
    if basemesh.mode != "OBJECT":
        return ("not_object_mode",
                "The basemesh '{:s}' is in {:s} mode. Loading a target requires OBJECT mode - "
                "MPFB asserts on it - so nothing was changed. Leave edit mode and call "
                "again.".format(basemesh.name, str(basemesh.mode)))
    if not target_service.has_any_shapekey(basemesh):
        return ("no_shapekeys",
                "The basemesh '{:s}' has no shape keys at all, so it has no target stack to "
                "change and nothing was changed. This mesh carries MPFB properties but was not "
                "built by MPFB.".format(basemesh.name))
    return (None, None)


def _unreachable_targets(target_service, basemesh, resolved):
    """Target names this entry would have to read from a file that is not there."""
    unreachable = []
    if resolved["kind"] != "modifier":
        return unreachable
    for step in resolved["plan"]:
        for wanted in step["wanted"]:
            if wanted["path"] is not None:
                continue
            if target_rollup.present_name(target_service, basemesh, wanted["target"]) is not None:
                # Already on the mesh, so nothing has to be read.
                continue
            unreachable.append(wanted["target"])
    return unreachable


def _message_for(basemesh, applied, refit_performed, refit_incomplete_reason,
                 mesh_assets, rig, diverging):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Applied {:d} change(s) to basemesh '{:s}', touching {:d} target(s).".format(
        len(applied), basemesh.name, sum(len(entry["targets"]) for entry in applied))]
    if refit_performed:
        parts.append(" Assets and rig were refitted to the new shape.")
    elif refit_incomplete_reason is not None:
        parts.append(" Mesh assets were refitted, but the rig was not: " + refit_incomplete_reason)
    elif mesh_assets or rig is not None:
        parts.append(
            " Nothing was refitted, so the {:d} mesh asset(s){:s} on this character are now "
            "fitted to the old shape. Call mpfb_refit_human when the modeling is done.".format(
                len(mesh_assets), " and the rig" if rig is not None else ""))
    if diverging:
        parts.append(
            " Note that {:d} of these categories is a gzipped custom target, which MPFB names "
            "without stripping '.gz' - so the shape key is not called what mpfb_list_targets "
            "reports as its 'shapekey_name'. The name MPFB's own slider uses was "
            "written.".format(len(diverging)))
    return "".join(parts)


def set_targets(params, resolution):  # pylint: disable=too-many-locals,too-many-branches
    """Resolve every requested change, then apply all of them or none."""
    services = resolution.services
    object_service = services["ObjectService"]
    target_service = services["TargetService"]

    requested_name = params["name"]
    requested_modifiers = list(params["modifiers"])
    requested_targets = list(params["targets"])
    symmetry = params["symmetry"]
    prune = params["prune"]
    refit_requested = params["refit"]

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name,
        not_done="nothing was changed",
        not_a_character="there are no targets to set")

    if basemesh is None:
        _LOG.debug("set_targets: no basemesh resolved from %r", requested_name)
        return with_performed(dict(
            found=False,
            ready=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            applied=[],
            resolution_errors=[],
            message=message,
        ), False)

    blocked_by, blocked_message = _precondition(target_service, basemesh)
    if blocked_by is not None:
        return with_performed(dict(
            found=True,
            ready=False,
            blocked_by=blocked_by,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            applied=[],
            resolution_errors=[],
            message=blocked_message,
        ), False)

    if not requested_modifiers and not requested_targets:
        return with_performed(dict(
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
            message="Neither 'modifiers' nor 'targets' named anything, so nothing was changed. "
                    "Call mpfb_get_target_stack to see what is currently set, and "
                    "mpfb_list_targets to see what could be.",
        ), False)

    tables = target_categories.build_tables(services)

    # Phase one: resolve everything, write nothing.
    resolved_entries = []
    resolution_errors = []
    for index, entry in enumerate(requested_modifiers):
        resolved, error = _resolve_modifier(tables, index, entry, symmetry)
        if error is not None:
            resolution_errors.append(error)
        else:
            resolved_entries.append(resolved)
    for index, entry in enumerate(requested_targets):
        resolved, error = _resolve_raw_target(
            services, tables, target_service, index, entry, basemesh)
        if error is not None:
            resolution_errors.append(error)
        else:
            resolved_entries.append(resolved)

    # A file that has to be read but is not there is a resolution failure too,
    # not an IOError half way through the batch. Rebuilt rather than removed
    # from in place: two unreachable targets in one entry must produce two
    # errors and drop that entry exactly once.
    still_resolved = []
    for resolved in resolved_entries:
        unreachable = _unreachable_targets(target_service, basemesh, resolved)
        for target_name in unreachable:
            resolution_errors.append({
                "index": resolved["index"],
                "kind": "modifier",
                "reason": "target_file_not_found",
                "section": resolved["section"],
                "category": resolved["category"],
                "message": "Target '{!s}' is not on this basemesh and no '.target.gz' or "
                           "'.target' file for it was found under section '{!s}'.".format(
                               target_name, resolved["section"]),
            })
        if not unreachable:
            still_resolved.append(resolved)
    resolved_entries = still_resolved

    if resolution_errors:
        # All or nothing. Twenty-nine of thirty changes would leave a character
        # in a state the response cannot describe and the caller cannot retry
        # from.
        return with_performed(dict(
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
            message="{:d} of {:d} requested change(s) could not be resolved, so **nothing at all "
                    "was applied**. Fix the entries listed in 'resolution_errors' and call again "
                    "with the whole batch.".format(
                        len(resolution_errors),
                        len(requested_modifiers) + len(requested_targets)),
        ), False)

    shapekeys_before = target_rollup.shapekey_names(basemesh)

    applied = []
    # MPFB's own slider callback activates the basemesh before writing, and the
    # refit below reaches bpy.ops through ClothesService. Put back what was
    # borrowed: the user is looking at this scene.
    with selection.restored(basemesh):
        object_service.activate_blender_object(basemesh)
        for resolved in resolved_entries:
            if resolved["kind"] == "modifier":
                touched = _apply_modifier(target_service, basemesh, resolved, prune)
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
                    "name_diverges_from_catalogue": resolved["name_diverges_from_catalogue"],
                    "catalogue_shapekey_name": resolved["catalogue_shapekey_name"],
                })
            else:
                touched = _apply_raw_target(target_service, basemesh, resolved, prune)
                applied.append({
                    "kind": "target",
                    "index": resolved["index"],
                    "shapekey_name": resolved["shapekey_name"],
                    "value": resolved["value"],
                    "path_resolved_by": resolved["path_resolved_by"],
                    "targets": touched,
                })

        rig = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
        refit_incomplete_reason = None
        refit_performed = False
        if refit_requested:
            refit_incomplete_reason = _rig_refit_blocker(services, rig)
            services["HumanService"].refit(basemesh)
            refit_performed = refit_incomplete_reason is None

    shapekeys_after = target_rollup.shapekey_names(basemesh)
    mesh_assets = [asset.name for asset in object_service.find_related_mesh_assets(basemesh)]
    diverging = [entry for entry in applied if entry.get("name_diverges_from_catalogue")]

    _LOG.debug("set_targets: applied %d change(s) to %r, refit_performed=%r",
               len(applied), basemesh.name, refit_performed)

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
        shapekeys_removed=[name for name in shapekeys_before if name not in shapekeys_after],
        shapekeys_added=[name for name in shapekeys_after if name not in shapekeys_before],
        refit_requested=refit_requested,
        refit_performed=refit_performed,
        refit_incomplete_reason=refit_incomplete_reason,
        # Reported whenever the fit was not brought up to date: a command that
        # moves a body under fitted clothes and says nothing has told the caller
        # something false by omission.
        assets_possibly_stale=None if refit_performed else dict(
            mesh_assets=mesh_assets,
            mesh_asset_count=len(mesh_assets),
            rig_attached=rig is not None,
            rig_object_name=None if rig is None else rig.name,
        ),
        message=_message_for(basemesh, applied, refit_performed, refit_incomplete_reason,
                             mesh_assets, rig, diverging),
    )

    # The verb is "applied", one entry per change, and it is empty in every
    # branch that wrote nothing - including the all-or-nothing resolution
    # failure. See shared/performed.py.
    return with_performed(result, result["applied"])
