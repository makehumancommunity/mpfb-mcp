"""
``apply_expressions``: put a character into one or more saved expressions.

Changes the applied-expressions stack MPFB keeps on the basemesh, then lets
MPFB re-derive the face from it - the same two steps every library change in
MPFB makes. **Batched**: MPFB's own path is one ``set_stack_weight`` call per
slider, and each re-reads, re-aggregates and rewrites the whole stack, so
reproducing a saved five-expression face one row at a time would be five
rebuilds. This makes one.

**``mode``.** ``"merge"`` (the default) upserts each fragment into the existing
stack, latest-wins per fragment, which is ``set_stack_weight``'s rule;
``"replace"`` makes the stack exactly the given rows. A weight of ``0.0``
**removes** a row, again ``set_stack_weight``'s rule, and ``replace`` with an
empty list is how everything is taken off. ``mode`` is this package's own
vocabulary rather than MPFB's - no MPFB function sees it - so it is checked on
mpfb-mcp's side as a shape, and here through the parameter's declared
``choices``, which make the dispatcher refuse it before this handler runs. An
unknown mode would otherwise have to fall back to one of the two, and either
fallback changes a character the caller did not describe.

**Everything is settled before anything is written**, per
[a batched mutating tool resolves before it writes](../../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes).
The subject, the mode, the ``faceunits01`` pack and every fragment a row would
add. MPFB's own ``apply_expression_file`` sets the precedent - it validates the
file "so we don't mutate the stack on a bad file" - and this follows it rather
than relying on it: ``aggregate_expression_stack`` warns and skips a row it
cannot resolve, so without the check a typo would come back as a success for a
face that did not change, and the row would stay on the stack claiming it had.

A fragment is resolved by ``AssetService.find_asset_absolute_path(..., "expressions")``,
which is how the rebuild will resolve it. That function matches by **basename**
across every root and falls back to the first match, so a fragment can resolve
to a file other than the one ``list_expressions`` lists under it; each
requested row reports ``resolved_path`` and ``listed_path``, and the answer says
so when they differ. A row at ``0.0`` is not resolved at all - removing a row
whose file is gone is exactly how a broken stack is cleaned up.

**The pack is a precondition, and a harder one than for the composer.** Without
``faceunits01`` the stack would be written, ``set_expression`` would find no
target for any unit, the face would not move, and the stack write **persists**:
the character would claim to wear an expression it has never displayed. So a
call that would add or raise any row is refused. A call that only removes rows
is not, since it claims nothing.

**It destroys composed work, and says so rather than refusing.** The rebuild's
``clear_expression`` is unconditional, so any unit composed on top of the stack
(``set_face_units``) is gone after this call - see
[`shared/expression_divergence.py`](../shared/expression_divergence.py). The
units the stack did not explain are measured *before* the write, and those the
rebuild then actually moved are returned as ``discarded_face_units``, with
``mpfb_save_expression`` named as what would have kept them. Both halves are
needed: FR 027's round-trip test found that predicting the loss from the first
half alone reports the save-then-replace sequence - the one that keeps
everything - as having discarded every composed unit. Refusing instead was considered and not done: an agent that
composes a face and then applies a library expression has, on the most natural
reading, changed its mind, and saving is the way not to lose the work. FR 027's
live check ran exactly this sequence to confirm the discard is real.

**The stack is written only through ``_write_applied_expressions``**, never by
setting the property directly - that function normalizes and sorts the rows,
and a stack MPFB's next write silently reorders is a stack two readers disagree
about. It is private; so is ``_read_applied_expressions``, and ``HumanService``
calls both across the underscore too. The rebuild is MPFB's own
``rebuild_expression_stack``.

**MPFB's panel is kept honest** by calling ``write_slider_values`` from its
``useexpression`` UI module, as MPFB's preset load does - see
[`shared/expression_panel.py`](../shared/expression_panel.py) for why a UI
module is reached at all, and how. ``panel_synced`` reports the outcome.

Refits per [`shared/refit_blocker.py`](../shared/refit_blocker.py), the sixth
command to, when the face actually changed. ``refit`` defaults to ``True``,
matching the expressions-library panel's own ``auto_refit``
(``ExpressionsLibraryProperties``, default ``True``).
"""

# The local bindings below are spelled with MPFB's own capitalisation. W0212 is
# the two private stack accessors the docstring explains.
# pylint: disable=invalid-name,protected-access

__all__ = (
    "MODES",
    "PARAMS",
    "SUMMARY",
    "apply_expressions",
)

import difflib
import json
import os

from ..log import get_logger
from ..shared import expression_panel
from ..shared import selection
from ..shared import subject_resolution
from ..shared.expression_divergence import TOLERANCE
from ..shared.expression_divergence import divergence
from ..shared.performed import with_performed
from ..shared.refit_blocker import rig_refit_is_blocked
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.applyexpressions")

MODES = ("merge", "replace")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("expressions", TYPE_ARRAY, default=(),
          description="One object per expression: {'fragment', 'weight'}, weight in 0.0-1.0. "
                      "A weight of 0.0 removes that expression from the stack."),
    Param("mode", TYPE_STRING, default="merge", choices=MODES,
          description="'merge' upserts each row into the existing stack; 'replace' makes the "
                      "stack exactly these rows. replace with an empty list clears it."),
    Param("refit", TYPE_BOOLEAN, default=True,
          description="Re-fit clothes and the rig afterwards. True is the expressions-library "
                      "panel's own auto_refit default."),
)

SUMMARY = "Apply saved expressions to a character through MPFB's applied-expressions stack."

# How many existing fragments a refusal names, per
# specifications/tool-interface.md: enough to correct a typo from, not a catalogue.
SUGGESTION_CAP = 50


def _entry_problem(position, entry):
    """Why one requested row cannot be read, or None. Defence in depth: mpfb-mcp checks this."""
    where = "expressions[{:d}]".format(position)
    if not isinstance(entry, dict):
        return "{:s} must be an object.".format(where)
    unknown = sorted(key for key in entry if key not in ("fragment", "weight"))
    if unknown:
        return "{:s} has unknown key(s): {:s}.".format(where, ", ".join(unknown))
    fragment = entry.get("fragment")
    if not isinstance(fragment, str) or not fragment.strip():
        return "{:s} fragment must be a non-empty string.".format(where)
    weight = entry.get("weight")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        return "{:s} weight must be a number.".format(where)
    if not 0.0 <= float(weight) <= 1.0:
        return "{:s} weight must be between 0.0 and 1.0.".format(where)
    return None


def _stack_as_rows(stack):
    """The stored stack as ``{fragment, weight}`` rows, the vocabulary of this package."""
    rows = []
    for row in stack:
        if isinstance(row, dict) and row.get("asset"):
            try:
                rows.append(dict(fragment=str(row["asset"]), weight=float(row.get("weight", 1.0))))
            except (TypeError, ValueError):
                continue
    return rows


def _resolve_fragment(services, fragment):
    """``(path, reason)``: the file a rebuild would load for ``fragment``, or why none."""
    FaceService = services["FaceService"]
    path = services["AssetService"].find_asset_absolute_path(fragment, asset_subdir="expressions")
    if not path or not os.path.isfile(path):
        return None, "not_found"
    try:
        FaceService.load_expression(path)
    except (IOError, ValueError, json.JSONDecodeError):
        return str(path), "unreadable"
    return str(path), None


def _rig_refit_blocker(services, rig):
    if not rig_refit_is_blocked(services, rig):
        return None
    return ("The rig '{:s}' is a generated Rigify rig and no meta rig is left in the scene, so "
            "it cannot be refitted to the new expression. Set the Rigify sub-panel's "
            "'Meta-rig' option to Keep or Hide before generating, to allow refitting "
            "afterwards.".format(rig.name))


def _new_stack(mode, before_rows, requested):
    """The stack after this call, as ``{asset, weight}`` rows MPFB's writer takes."""
    requested_fragments = set(entry["fragment"] for entry in requested)
    stack = []
    if mode == "merge":
        stack = [dict(asset=row["fragment"], weight=row["weight"]) for row in before_rows
                 if row["fragment"] not in requested_fragments]
    for entry in requested:
        if float(entry["weight"]) > 0.0:
            stack.append(dict(asset=entry["fragment"], weight=float(entry["weight"])))
    return stack


def _discarded(unexplained_before, after_live):
    """The composed units the rebuild actually overwrote, each with its value ``now``.

    Measured on both sides of the write, not predicted from the first: a unit
    the stack did not explain before this call is only *lost* if the rebuild
    moved it. The save-then-replace sequence ``save_expression`` recommends is
    the case that tells the two apart - every composed unit is unexplained
    before, and the new stack reproduces all of them, so nothing is discarded.
    """
    discarded = []
    for entry in unexplained_before:
        now = float(after_live.get(entry["face_unit"], 0.0))
        if abs(now - entry["live"]) > TOLERANCE:
            discarded.append(dict(entry, now=round(now, 6)))
    return discarded


def _action(before_by_fragment, fragment, weight):
    if weight <= 0.0:
        return "removed" if fragment in before_by_fragment else "absent"
    if fragment not in before_by_fragment:
        return "added"
    if abs(before_by_fragment[fragment] - weight) > 1e-9:
        return "updated"
    return "unchanged"


def _message_for(basemesh, mode, report, removed_by_replace, discarded, after, installed,
                 refit_requested, refit_performed, refit_incomplete_reason, panel_synced):
    counts = {}
    for row in report:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    parts = ["Stack on basemesh '{:s}' ({:s}): {:s}. It now holds {:d} expression(s).".format(
        basemesh.name, mode,
        ", ".join("{:d} {:s}".format(counts[action], action)
                  for action in ("added", "updated", "removed", "unchanged", "absent")
                  if action in counts) or "no rows requested",
        len(after["applied_expressions"]))]
    if removed_by_replace:
        parts.append(" replace took off {:d} row(s) not in this call: {:s}.".format(
            len(removed_by_replace), ", ".join(removed_by_replace)))
    elsewhere = [row["fragment"] for row in report
                 if row["resolved_path"] and row["listed_path"]
                 and row["resolved_path"] != row["listed_path"]]
    if elsewhere:
        parts.append(" {:d} fragment(s) resolved to a different file than mpfb_list_expressions "
                     "lists under that fragment, because MPFB matches expression files by "
                     "basename: {:s}.".format(len(elsewhere), ", ".join(elsewhere)))
    if discarded:
        parts.append(
            " {:d} face unit(s) composed on top of the previous stack were discarded, because "
            "every library change rebuilds the face from the stack; mpfb_save_expression "
            "before this call would have kept them.".format(len(discarded)))
    if after["clamped_face_units"]:
        parts.append(" {:d} face unit(s) sum past 1.0 across the stack and are clamped; see "
                     "clamped_face_units.".format(len(after["clamped_face_units"])))
    if not after["matches_stack"] and installed:
        parts.append(
            " {:d} face unit(s) still differ from the stack's aggregate after the rebuild, which "
            "means their target file could not be loaded - a partially installed faceunits01 "
            "pack.".format(len(after["unexplained_face_units"])))
    if not panel_synced:
        parts.append(" MPFB's expressions-library panel was not updated; see panel_sync_reason.")
    if refit_requested:
        if refit_performed:
            parts.append(" Assets and rig were refitted.")
        elif refit_incomplete_reason is not None:
            parts.append(" Mesh assets were refitted, but the rig was not: "
                         + refit_incomplete_reason)
    return "".join(parts)


class _Blocked:
    """The fields every refusal carries, so a caller can branch on ``blocked_by``."""

    def __init__(self, subject, subject_resolved_by, basemesh, mode, installed):
        self.base = dict(
            found=basemesh is not None,
            ready=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None if basemesh is None else basemesh.name,
            mode=mode,
            faceunits01_installed=installed,
            changed=False,
            requested=[],
            applied_expressions=[],
            discarded_face_units=[],
        )

    def __call__(self, reason, message, **extra):
        answer = dict(self.base)
        answer["blocked_by"] = reason
        answer["message"] = message
        answer.update(extra)
        return with_performed(answer, False)


def apply_expressions(params, resolution):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """Settle every precondition and fragment, then rewrite the stack once."""
    services = resolution.services
    FaceService = services["FaceService"]
    ObjectService = services["ObjectService"]

    requested_name = params["name"]
    requested = list(params["expressions"])
    mode = params["mode"]
    refit_requested = params["refit"]

    installed = bool(FaceService.is_faceunits01_installed())
    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name,
        not_done="nothing was changed",
        not_a_character="there is no face to change")
    blocked = _Blocked(subject, subject_resolved_by, basemesh, mode, installed)

    if basemesh is None:
        answer = blocked("subject_not_found", message)
        answer["found"] = False
        return answer
    if basemesh.mode != "OBJECT":
        return blocked(
            "not_object_mode",
            "The basemesh '{:s}' is in {:s} mode. Loading a face-unit target requires OBJECT "
            "mode, so nothing was changed. Leave edit mode and call again.".format(
                basemesh.name, str(basemesh.mode)))

    problems = [problem for problem in (_entry_problem(position, entry)
                                        for position, entry in enumerate(requested))
                if problem is not None]
    if problems:
        return blocked("invalid_entries", " ".join(problems) + " Nothing was changed.")
    fragments = [entry["fragment"] for entry in requested]
    duplicates = sorted(set(fragment for fragment in fragments if fragments.count(fragment) > 1))
    if duplicates:
        return blocked(
            "duplicate_fragments",
            "Each fragment may appear once per call, and these appear more than once: {:s}. "
            "Nothing was changed.".format(", ".join(duplicates)),
            duplicate_fragments=duplicates)

    adding = [entry for entry in requested if float(entry["weight"]) > 0.0]
    if adding and not installed:
        return blocked(
            "faceunits01_not_installed",
            "The faceunits01 asset pack does not appear to be installed, so nothing was "
            "changed. The stack would be written and would persist, but no face-unit target "
            "could load, so the character would claim an expression it never shows. Removing "
            "rows (weight 0.0) is still allowed.")

    listed = {str(fragment): str(path)
              for path, fragment, _metadata in FaceService.list_available_expressions()}
    resolved = {}
    unresolved = []
    for entry in adding:
        path, reason = _resolve_fragment(services, entry["fragment"])
        if reason is not None:
            unresolved.append(dict(
                fragment=entry["fragment"], reason=reason, path=path,
                closest=difflib.get_close_matches(entry["fragment"], list(listed), n=3,
                                                  cutoff=0.5)))
        else:
            resolved[entry["fragment"]] = path
    if unresolved:
        available = sorted(listed)
        return blocked(
            "unresolved_fragments",
            "{:d} fragment(s) could not be resolved to a readable expression file, so nothing "
            "was changed: {:s}. available_fragments lists {:d} of the {:d} that exist; "
            "mpfb_list_expressions lists them all.".format(
                len(unresolved), ", ".join(row["fragment"] for row in unresolved),
                min(len(available), SUGGESTION_CAP), len(available)),
            unresolved_fragments=unresolved,
            available_fragments=available[:SUGGESTION_CAP])

    # Everything is settled. Measure what the rebuild is about to destroy, then
    # write the stack once and let MPFB rebuild the face from it.
    before = divergence(services, basemesh)
    before_rows = _stack_as_rows(FaceService._read_applied_expressions(basemesh))
    before_by_fragment = {row["fragment"]: row["weight"] for row in before_rows}
    before_live = FaceService.read_current_expression(basemesh)

    new_stack = _new_stack(mode, before_rows, requested)
    FaceService._write_applied_expressions(basemesh, new_stack)
    FaceService.rebuild_expression_stack(basemesh)

    after_rows = _stack_as_rows(FaceService._read_applied_expressions(basemesh))
    after_fragments = set(row["fragment"] for row in after_rows)
    requested_fragments = set(entry["fragment"] for entry in requested)
    removed_by_replace = sorted(fragment for fragment in before_by_fragment
                                if fragment not in after_fragments
                                and fragment not in requested_fragments)

    panel_synced, panel_sync_reason = expression_panel.write_slider_values(
        resolution.module.__name__,
        [dict(asset=row["fragment"], weight=row["weight"]) for row in after_rows])

    after_live = FaceService.read_current_expression(basemesh)
    face_changed = any(abs(float(after_live.get(name, 0.0)) - float(value)) > 1e-9
                       for name, value in before_live.items())
    discarded = _discarded(before["unexplained_face_units"], after_live) if installed else []
    stack_changed = before_rows != after_rows

    refit_incomplete_reason = None
    refit_performed = False
    rig = ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
    if refit_requested and face_changed:
        refit_incomplete_reason = _rig_refit_blocker(services, rig)
        # refit() reaches bpy.ops through ClothesService. Put back what was
        # borrowed, as refit_human does: the user is looking at this scene.
        with selection.restored(basemesh):
            services["HumanService"].refit(basemesh)
        refit_performed = refit_incomplete_reason is None

    after = divergence(services, basemesh)
    mesh_assets = [asset.name for asset in ObjectService.find_related_mesh_assets(basemesh)]

    report = []
    for entry in requested:
        fragment = entry["fragment"]
        weight = float(entry["weight"])
        report.append(dict(
            fragment=fragment,
            weight=weight,
            action=_action(before_by_fragment, fragment, weight),
            previous_weight=before_by_fragment.get(fragment),
            resolved_path=resolved.get(fragment),
            listed_path=listed.get(fragment),
        ))

    _LOG.debug("apply_expressions: %s, %d requested, stack %d -> %d, discarded %d",
               mode, len(requested), len(before_rows), len(after_rows), len(discarded))

    result = dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        mode=mode,
        faceunits01_installed=installed,
        # The verb, beside `performed`: see shared/performed.py.
        changed=stack_changed or face_changed,
        requested=report,
        stack_before=before_rows,
        removed_by_replace=removed_by_replace,
        discarded_face_units=discarded,
        panel_synced=panel_synced,
        panel_sync_reason=panel_sync_reason,
        refit_requested=refit_requested,
        refit_performed=refit_performed,
        refit_incomplete_reason=refit_incomplete_reason,
        assets_possibly_stale=None if (refit_performed or not face_changed) else dict(
            mesh_assets=mesh_assets,
            mesh_asset_count=len(mesh_assets),
            rig_attached=rig is not None,
            rig_object_name=None if rig is None else rig.name,
        ),
        message=_message_for(basemesh, mode, report, removed_by_replace, discarded, after,
                             installed, refit_requested, refit_performed,
                             refit_incomplete_reason, panel_synced),
    )
    result.update(after)
    return with_performed(result, result["changed"])
