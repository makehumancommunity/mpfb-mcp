"""
``symmetrize_targets``: copy one side's modeling onto the other.

**MPFB has no equivalent of this operation.** Its ``symmetry`` setting only
affects changes made while it is switched on - its own property description says
in so many words that toggling it does not affect previously set values - so a
character that has already drifted asymmetric cannot be repaired through MPFB's
UI except by dragging every slider by hand. This is therefore a deliberate
addition rather than a wrapper, which makes it the one command here whose
behaviour is not a reading of MPFB's.

**The most destructive command in the package**, and the shape of it follows
from that. ``direction`` is the package's only **required** argument: which half
of a face is the good one is not something a command can guess, and guessing
wrong destroys work with no undo across the socket. ``dry_run`` exists for the
same reason, and it is why ``performed`` is written from the verb *and* the flag
at the call site - a dry run returns a populated ``changed`` list having written
nothing, which is the one case where the verb alone would lie.

**The walk is over categories, not over shape key names.** Pairing ``l-foo``
with ``r-foo`` by string manipulation would be a guess; the ``opposites`` table
names all four targets of a sided category explicitly, and a category with
``has_left_and_right: false`` has no partner at all. So the categories are
walked and the shape keys are consulted only for their values - through
[`shared/modifier_reading.py`](../shared/modifier_reading.py), which is the same
rule ``get_target_stack`` reports through, so the value this command copies is
the value that one shows.

**Everything is measured before anything is written**, so that a dry run and a
real run report the same set of changes. Writing then follows MPFB's
``_set_opposed_modifier_value()`` statement for statement, the same as
``set_targets``: the opposing target is zeroed first - both of them when the
value is at zero - and only then is the selected one set or loaded.

Unlike ``set_targets``, a category whose file cannot be found is **skipped
rather than fatal**, and the difference is deliberate. That command is asked to
apply a specific list, so one bad entry invalidates the batch; this one is asked
to make a character symmetric, so one unreachable target is a fact to report
about that category rather than a reason to leave the rest of the body
asymmetric.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "symmetrize_targets",
)

from ..log import get_logger
from ..shared import selection
from ..shared import subject_resolution
from ..shared import target_categories
from ..shared import target_rollup
from ..shared.modifier_reading import modifier_reading
from ..shared.performed import with_performed
from ..shared.refit_blocker import rig_refit_is_blocked
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.symmetrizetargets")

DIRECTIONS = ("left_to_right", "right_to_left")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("direction", TYPE_STRING, required=True, choices=DIRECTIONS,
          description="Which side is the one to keep. Required, and deliberately: which half of "
                      "a face is the good one is not something this can guess, and guessing "
                      "wrong destroys work with no undo."),
    Param("section", TYPE_STRING, default=None, nullable=True,
          description="Limit the walk to one target section. Omit for every section."),
    Param("dry_run", TYPE_BOOLEAN, default=False,
          description="Report exactly what would be changed and write nothing."),
    Param("prune", TYPE_BOOLEAN, default=True,
          description="Delete a shape key whose value falls to zero. MPFB's own default."),
    Param("refit", TYPE_BOOLEAN, default=False,
          description="Re-fit clothes and the rig afterwards. False is MPFB's own default."),
)

SUMMARY = "Copy one side of a character's detail modeling onto the other."

# MPFB's own threshold, from _set_opposed_modifier_value() and prune_shapekeys().
EPSILON = 0.0001


def _modifier_value(target_service, basemesh, category, side):
    """One category's slider reading, taken from the mesh as it stands.

    The rule is ``modifier_reading()`` from the shared module, the same one
    ``get_target_stack`` reports through; what is passed in is a lookup that
    goes to ``key_blocks`` on every question rather than to a snapshot, since
    this command reads a category again after writing to it and a snapshot taken
    beforehand would report the value it just replaced.
    """
    present, current_value = target_rollup.live_lookup(target_service, basemesh)
    return modifier_reading(category, side, present, current_value)


def _write_side(target_service, tables, basemesh, section_name, category, side, value, prune):
    """Apply one value to one side, in MPFB's order. Returns the targets touched."""
    touched = []
    if target_categories.category_is_opposed(category):
        positive = target_categories.target_names_for(category, side, "positive")
        negative = target_categories.target_names_for(category, side, "negative")

        if value < EPSILON:
            stored = target_rollup.present_name(target_service, basemesh, positive)
            if stored is not None:
                previous = target_rollup.stored_value(basemesh, stored)
                target_service.set_target_value(
                    basemesh, stored, 0.0, delete_target_on_zero=prune)
                touched.append({
                    "target": positive, "polarity": "positive",
                    "previous_value": previous,
                    "new_value": target_rollup.stored_value(
                        basemesh, target_rollup.present_name(target_service, basemesh, positive)),
                    "loaded_from": None,
                })
        if value > -EPSILON:
            stored = target_rollup.present_name(target_service, basemesh, negative)
            if stored is not None:
                previous = target_rollup.stored_value(basemesh, stored)
                target_service.set_target_value(
                    basemesh, stored, 0.0, delete_target_on_zero=prune)
                touched.append({
                    "target": negative, "polarity": "negative",
                    "previous_value": previous,
                    "new_value": target_rollup.stored_value(
                        basemesh, target_rollup.present_name(target_service, basemesh, negative)),
                    "loaded_from": None,
                })

        wanted = []
        if value > 0.0:
            wanted.append(("positive", positive, value))
        if value < 0.0:
            wanted.append(("negative", negative, abs(value)))
    else:
        wanted = [("positive",
                   target_categories.target_names_for(category, side, "positive"), value)]

    for polarity, target_name, weight in wanted:
        stored = target_rollup.present_name(target_service, basemesh, target_name)
        if stored is None:
            path, _resolved_by = target_categories.resolve_target_path(
                tables, section_name, category, target_name)
            target_service.load_target(basemesh, path, weight=weight, name=target_name)
            touched.append({
                "target": target_name, "polarity": polarity,
                "previous_value": None,
                "new_value": target_rollup.stored_value(
                    basemesh, target_rollup.present_name(target_service, basemesh, target_name)),
                "loaded_from": path,
            })
        else:
            previous = target_rollup.stored_value(basemesh, stored)
            target_service.set_target_value(
                basemesh, stored, weight, delete_target_on_zero=prune)
            touched.append({
                "target": target_name, "polarity": polarity,
                "previous_value": previous,
                "new_value": target_rollup.stored_value(
                    basemesh, target_rollup.present_name(target_service, basemesh, target_name)),
                "loaded_from": None,
            })
    return touched


def _loadable(target_service, tables, basemesh, section_name, category, side, value):
    """Whether every file this write might need is reachable.

    Checked before anything is written, so that a category whose target file is
    missing is reported as skipped rather than raising an IOError out of
    ``load_target()`` with half the body already mirrored.
    """
    if target_categories.category_is_opposed(category):
        wanted = []
        if value > 0.0:
            wanted.append(target_categories.target_names_for(category, side, "positive"))
        if value < 0.0:
            wanted.append(target_categories.target_names_for(category, side, "negative"))
    else:
        wanted = [target_categories.target_names_for(category, side, "positive")]
    for target_name in wanted:
        if not target_name:
            return False
        if target_rollup.present_name(target_service, basemesh, target_name) is not None:
            continue
        path, _resolved_by = target_categories.resolve_target_path(
            tables, section_name, category, target_name)
        if path is None:
            return False
    return True


def _rig_refit_blocker(services, rig):
    """Why HumanService.refit() would leave this rig untouched, or ``None``."""
    if not rig_refit_is_blocked(services, rig):
        return None
    return ("The rig '{:s}' is a generated Rigify rig and no meta rig is left in the scene, so it "
            "cannot be refitted to the new body shape. Set the Rigify sub-panel's 'Meta-rig' "
            "option to Keep or Hide before generating, to allow refitting "
            "afterwards.".format(rig.name))


def _precondition(target_service, basemesh, requested_section, section_recognized):
    """Which state blocks a write, and the sentence for it."""
    if not section_recognized:
        return ("unknown_section",
                "No target section called '{!s}', so nothing was changed. See "
                "'known_sections'.".format(requested_section))
    if basemesh.mode != "OBJECT":
        return ("not_object_mode",
                "The basemesh '{:s}' is in {:s} mode. Loading a target requires OBJECT mode - "
                "MPFB asserts on it - so nothing was changed. Leave edit mode and call "
                "again.".format(basemesh.name, str(basemesh.mode)))
    if not target_service.has_any_shapekey(basemesh):
        return ("no_shapekeys",
                "The basemesh '{:s}' has no shape keys at all, so there is nothing to symmetrize. "
                "This mesh carries MPFB properties but was not built by MPFB.".format(
                    basemesh.name))
    return (None, None)


def _message_for(dry_run, source_side, destination_side, basemesh, changed, already_symmetric,
                 skipped, refit_requested, refit_performed, refit_incomplete_reason,
                 mesh_assets, rig):
    """What happened, said once, in the order a reader wants it."""
    parts = []
    if dry_run:
        parts.append(
            "Dry run: {:d} category/categories would be changed, {:d} are already symmetric. "
            "**Nothing was written.** Call again without dry_run to apply exactly these "
            "changes.".format(len(changed), len(already_symmetric)))
    else:
        parts.append(
            "Copied {:s} to {:s} for {:d} category/categories on basemesh '{:s}'; {:d} were "
            "already symmetric.".format(source_side, destination_side, len(changed),
                                        basemesh.name, len(already_symmetric)))
    if skipped:
        parts.append(
            " {:d} category/categories were skipped because the target file that would have to "
            "be loaded could not be found.".format(len(skipped)))
    if not dry_run and not changed and refit_requested:
        # Nothing moved, so nothing is out of fit. Saying so is cheaper than
        # letting the caller wonder why refit_performed came back false.
        parts.append(" No refit was needed, because nothing was changed.")
    if not dry_run and changed:
        if refit_performed:
            parts.append(" Assets and rig were refitted to the new shape.")
        elif refit_incomplete_reason is not None:
            parts.append(" Mesh assets were refitted, but the rig was not: "
                         + refit_incomplete_reason)
        elif mesh_assets or rig is not None:
            parts.append(
                " Nothing was refitted, so the {:d} mesh asset(s){:s} on this character are now "
                "fitted to the old shape. Call mpfb_refit_human when the modeling is "
                "done.".format(len(mesh_assets), " and the rig" if rig is not None else ""))
    return "".join(parts)


def symmetrize_targets(params, resolution):  # pylint: disable=too-many-locals,too-many-branches
    """Measure both sides everywhere, then copy one onto the other - or say what it would."""
    services = resolution.services
    object_service = services["ObjectService"]
    target_service = services["TargetService"]

    requested_name = params["name"]
    direction = params["direction"]
    requested_section = params["section"]
    dry_run = params["dry_run"]
    prune = params["prune"]
    refit_requested = params["refit"]

    source_side = "left" if direction == "left_to_right" else "right"
    destination_side = "right" if direction == "left_to_right" else "left"

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name,
        not_done="nothing was changed",
        not_a_character="there is nothing to symmetrize")

    if basemesh is None:
        _LOG.debug("symmetrize_targets: no basemesh resolved from %r", requested_name)
        return with_performed(dict(
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
        ), False)

    tables = target_categories.build_tables(services)

    matched_section = None
    section_recognized = True
    if requested_section is not None:
        matched_section = target_categories.find_section(tables, requested_section)
        section_recognized = matched_section is not None

    blocked_by, blocked_message = _precondition(
        target_service, basemesh, requested_section, section_recognized)
    if blocked_by is not None:
        return with_performed(dict(
            found=True,
            ready=False,
            blocked_by=blocked_by,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            direction=direction,
            section=requested_section,
            section_recognized=section_recognized,
            known_sections=tables.known_sections,
            dry_run=dry_run,
            changed=[],
            already_symmetric=[],
            skipped=[],
            message=blocked_message,
        ), False)

    section_names = tables.known_sections
    if matched_section is not None:
        section_names = [matched_section]

    # Everything is measured before anything is written, so that a dry run and a
    # real run report the same set of changes.
    planned = []
    already_symmetric = []
    skipped = []
    for section_name in section_names:
        for category in tables.sections[section_name]["categories"]:
            if not category.get("has_left_and_right"):
                continue
            source_value = _modifier_value(target_service, basemesh, category, source_side)
            destination_value = _modifier_value(
                target_service, basemesh, category, destination_side)
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
            if not _loadable(target_service, tables, basemesh, section_name, category,
                             destination_side, source_value):
                entry["reason"] = "target_file_not_found"
                skipped.append(entry)
                continue
            planned.append((entry, section_name, category, source_value))

    changed = []
    refit_incomplete_reason = None
    refit_performed = False
    rig = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
    shapekeys_before = target_rollup.shapekey_names(basemesh)
    shapekeys_after = list(shapekeys_before)

    if dry_run:
        for entry, _section_name, _category, source_value in planned:
            reported = dict(entry)
            reported["destination_value_after"] = round(source_value, 6)
            # Null and not an empty list. Which target files a write would touch
            # is only knowable by doing the write - a category's opposing target
            # may or may not already be on the mesh - so a dry run has not
            # computed this. An empty list would say "no shape keys would be
            # touched", which is a different and false claim; see the
            # response-shape rule in specifications/architecture.md.
            reported["targets"] = None
            changed.append(reported)
    elif planned:
        with selection.restored(basemesh):
            object_service.activate_blender_object(basemesh)
            for entry, section_name, category, source_value in planned:
                touched = _write_side(target_service, tables, basemesh, section_name, category,
                                      destination_side, source_value, prune)
                reported = dict(entry)
                reported["destination_value_after"] = round(
                    _modifier_value(target_service, basemesh, category, destination_side), 6)
                reported["targets"] = touched
                changed.append(reported)
            if refit_requested:
                refit_incomplete_reason = _rig_refit_blocker(services, rig)
                services["HumanService"].refit(basemesh)
                refit_performed = refit_incomplete_reason is None
        shapekeys_after = target_rollup.shapekey_names(basemesh)

    mesh_assets = [asset.name for asset in object_service.find_related_mesh_assets(basemesh)]

    _LOG.debug("symmetrize_targets: %d changed, %d already symmetric, %d skipped, dry_run=%r",
               len(changed), len(already_symmetric), len(skipped), dry_run)

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
        known_sections=tables.known_sections,
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
        message=_message_for(dry_run, source_side, destination_side, basemesh, changed,
                             already_symmetric, skipped, refit_requested, refit_performed,
                             refit_incomplete_reason, mesh_assets, rig),
    )

    # The one command whose verb is not enough on its own: a dry run reports the
    # changes it would make in "changed" and writes none of them. See
    # shared/performed.py.
    return with_performed(result, result["changed"] and not result["dry_run"])
