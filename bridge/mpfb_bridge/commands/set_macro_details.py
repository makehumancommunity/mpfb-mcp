"""
``set_macro_details``: write the phenotype sliders, then rebuild the shape once.

The writing half of the macro pair, and the first command here whose work is
**two steps that must not be separated**. Setting a macro property changes a
number and nothing moves; the shape is derived from all eleven values together
by ``TargetService.reapply_macro_details()``. So every named property is written
first and the recalculation runs **once** - which is what MPFB's own slider
callback (``ui/model/_macrosubpanel.py``) does, and N times less work than
recalculating per property.

``reapply_macro_details()`` and never ``reapply_all_details()``: the latter also
tears down and reloads the *detail* target stack from disk, where a shape key
whose name was encoded no longer resolves back to a file and is dropped with a
log warning, and where the path lookup falls back to a prefix match that can
silently load a different target. A macro change does not require detail targets
to be reloaded at all.

**Three preconditions are answers rather than failures**, each a state an agent
will hit: the basemesh must be in OBJECT mode, because
``TargetService.create_shape_key()`` opens with a bare ``assert`` that would come
back as a traceback with no message; it must have shape keys, because
``reapply_macro_details()`` merely logs "somewhat surprising" and carries on; and
the property set must be reachable at all. A fourth case - a call naming **no**
slider - answers immediately rather than paying seconds for a rebuild that would
change nothing, and it is the reason ``performed`` is written from the verb at
the call site rather than guessed.

**A change that is not refitted says so.** ``refit`` defaults to false, as MPFB's
own panel does, because a refit is expensive - not because it is unnecessary. A
command that moves a body under fitted clothes and says nothing has told its
caller something false by omission, so ``assets_possibly_stale`` names what is
now fitted to the old shape whenever the fit was not brought up to date,
including after a *partial* refit.

**``changes`` arrives as an opaque list, and that asymmetry is deliberate.** The
eleven sliders are flat arguments on ``mpfb_set_macro_details`` and are validated
there - 0.0-1.0, and the property name comes from a fixed table - because
MPFB's macro properties carry a default but no ``min``/``max`` and the clamping a
user gets from a slider comes from a scene-level proxy property that neither
transport goes near. :data:`PARAMS` below cannot express a rule about the inside
of a list, and reshaping the parameters per transport is exactly what the seam
forbids: both sides receive the tool's already-validated arguments. Written down
here rather than left to be rediscovered; see ``commands/create_human.py`` for
the same asymmetry in its other shape.

**The phenotype it reports is read by [`shared/macro_reading.py`](../shared/macro_reading.py)**,
the implementation ``get_macro_details`` reports from, so ``macro_details`` and
``race_sum`` after a write are what that command would read on the next call
([FR 036](../../../feature-requests/done/036-subject-resolver-and-duplication/README.md)).

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
    "set_macro_details",
)

from ..log import get_logger
from ..shared import macro_reading
from ..shared import mpfb_surface
from ..shared import selection
from ..shared import subject_resolution
from ..shared.performed import with_performed
from ..shared.refit_blocker import rig_refit_is_blocked
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setmacrodetails")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family - the basemesh, its rig, a garment. "
                      "Omit or pass null to use whatever object is currently active."),
    Param("changes", TYPE_ARRAY, default=(),
          description="One object per slider to write: 'argument' (the caller's name for it), "
                      "'property' (MPFB's) and 'value' (0.0-1.0). An empty list changes nothing "
                      "and recalculates nothing, deliberately."),
    Param("prune", TYPE_BOOLEAN, default=True,
          description="Delete macro shape keys whose weight falls to zero. True is MPFB's own "
                      "default and keeps the shape key list from growing as sliders move."),
    Param("refit", TYPE_BOOLEAN, default=False,
          description="Re-fit clothes and the rig to the new body shape. False is MPFB's own "
                      "default: a refit is expensive, so make a series of changes and call "
                      "refit_human once."),
)

SUMMARY = "Write a character's macro phenotype sliders and rebuild the shape from them."


def _flat_value(macro_details, property_name):
    """One property out of the nested dict, whichever level it lives on."""
    if property_name in macro_reading.RACE_NAMES:
        return macro_details.get("race", dict()).get(property_name)
    return macro_details.get(property_name)


def _macro_shapekeys_of(target_service, basemesh):
    """The macro shape keys on the mesh, under the names they are stored with.

    Undecoded, for the reason ``get_macro_details`` gives: these feed
    ``shapekeys_added`` and ``shapekeys_removed``, and a name a caller cannot
    look up on the mesh is a worse answer than a less readable one.
    """
    return [
        str(name) for name in target_service.get_current_macro_targets(basemesh,
                                                                       decode_names=False)
    ]


def _rig_refit_blocker(services, rig):
    """Why HumanService.refit() would leave this rig untouched, or ``None``.

    The condition is ``rig_refit_is_blocked()`` from the shared module, which
    every command that refits asks; the wording is this command's own, because
    here the refit has not happened yet and the sentence is a prediction rather
    than a report. Asking at all is what keeps the command from claiming a
    refit it did not perform.
    """
    if not rig_refit_is_blocked(services, rig):
        return None
    return ("The rig '{:s}' is a generated Rigify rig and no meta rig is left in the scene, so it "
            "cannot be refitted to the new body shape. Set the Rigify sub-panel's 'Meta-rig' "
            "option to Keep or Hide before generating, to allow refitting "
            "afterwards.".format(rig.name))


def _precondition(services, target_service, basemesh):
    """Which of the three states blocks a write, and the sentence for it."""
    if mpfb_surface.human_object_properties(services) is None:
        return ("properties_unavailable",
                "MPFB's HumanObjectProperties could not be reached, so no macro property can be "
                "written. Call mpfb_get_status to check how this MPFB is installed.")
    if basemesh.mode != "OBJECT":
        return ("not_object_mode",
                "The basemesh '{:s}' is in {:s} mode. Rebuilding the macro shape requires OBJECT "
                "mode - MPFB asserts on it - so nothing was changed. Leave edit mode and call "
                "again.".format(basemesh.name, str(basemesh.mode)))
    if not target_service.has_any_shapekey(basemesh):
        return ("no_shapekeys",
                "The basemesh '{:s}' has no shape keys at all, so there is no macro target stack "
                "to rebuild and nothing was changed. This mesh carries MPFB properties but was "
                "not built by MPFB.".format(basemesh.name))
    return (None, None)


def _message_for(basemesh, changed, refit_performed, refit_incomplete_reason,
                 mesh_assets, rig, race_sum):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Changed {:d} macro detail(s) on basemesh '{:s}' and rebuilt the macro target "
             "stack.".format(len(changed), basemesh.name)]
    if refit_performed:
        parts.append(" Assets and rig were refitted to the new shape.")
    elif refit_incomplete_reason is not None:
        parts.append(" Mesh assets were refitted, but the rig was not: "
                     + refit_incomplete_reason)
    elif mesh_assets or rig is not None:
        parts.append(
            " Nothing was refitted, so the {:d} mesh asset(s){:s} on this character are now "
            "fitted to the old shape. Call mpfb_refit_human when the modeling is done.".format(
                len(mesh_assets), " and the rig" if rig is not None else ""))
    if abs(race_sum - 1.0) > macro_reading.RACE_SUM_TOLERANCE:
        parts.append(
            " The three race weights now sum to {:s} rather than 1.0. MPFB treats them as "
            "independent and does not normalize them.".format(str(race_sum)))
    return "".join(parts)


def set_macro_details(params, resolution):  # pylint: disable=too-many-locals
    """Write the named sliders, rebuild the shape once, and report both."""
    services = resolution.services
    object_service = services["ObjectService"]
    target_service = services["TargetService"]

    requested_name = params["name"]
    changes = list(params["changes"])
    prune = params["prune"]
    refit_requested = params["refit"]

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name,
        not_done="nothing was changed",
        not_a_character="there are no macro details to change")

    if basemesh is None:
        _LOG.debug("set_macro_details: no basemesh resolved from %r", requested_name)
        return with_performed(dict(
            found=False,
            ready=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            changed=[],
            recalculated=False,
            message=message,
        ), False)

    blocked_by, blocked_message = _precondition(services, target_service, basemesh)
    if blocked_by is not None:
        macro_details = macro_reading.macro_details_of(target_service, basemesh)
        return with_performed(dict(
            found=True,
            ready=False,
            blocked_by=blocked_by,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            changed=[],
            recalculated=False,
            macro_details=macro_details,
            race_sum=macro_reading.race_sum_of(macro_details),
            message=blocked_message,
        ), False)

    if not changes:
        # A no-op call is a common mistake, and a full macro reapply costs
        # seconds. Answering immediately is both cheaper and clearer than
        # rebuilding a shape that would come out identical.
        macro_details = macro_reading.macro_details_of(target_service, basemesh)
        race_sum = macro_reading.race_sum_of(macro_details)
        return with_performed(dict(
            found=True,
            ready=True,
            blocked_by=None,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            changed=[],
            recalculated=False,
            macro_details=macro_details,
            race_sum=race_sum,
            race_normalized=abs(race_sum - 1.0) <= macro_reading.RACE_SUM_TOLERANCE,
            refit_requested=refit_requested,
            refit_performed=False,
            message="No macro detail was named, so nothing was changed and no shape was "
                    "recalculated. Pass at least one slider - the current values are in "
                    "macro_details.",
        ), False)

    HumanObjectProperties = mpfb_surface.human_object_properties(services)
    details_before = macro_reading.macro_details_of(target_service, basemesh)
    shapekeys_before = _macro_shapekeys_of(target_service, basemesh)

    # MPFB's own slider callback activates the basemesh before recalculating.
    # Nothing in reapply_macro_details() obviously requires it, but the refit
    # below reaches bpy.ops through ClothesService, so follow MPFB - and put
    # back what was borrowed: the user is looking at this scene.
    with selection.restored(basemesh):
        for change in changes:
            HumanObjectProperties.set_value(
                change["property"], change["value"], entity_reference=basemesh)

        object_service.activate_blender_object(basemesh)
        # Once, after every write: the stack is derived from all eleven values
        # together, so recalculating per property would be N times the work for
        # the same result.
        target_service.reapply_macro_details(basemesh, remove_zero_weight_targets=prune)

        rig = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
        refit_incomplete_reason = None
        refit_performed = False
        if refit_requested:
            refit_incomplete_reason = _rig_refit_blocker(services, rig)
            services["HumanService"].refit(basemesh)
            refit_performed = refit_incomplete_reason is None

    details_after = macro_reading.macro_details_of(target_service, basemesh)
    shapekeys_after = _macro_shapekeys_of(target_service, basemesh)
    race_sum = macro_reading.race_sum_of(details_after)

    changed = [
        dict(
            name=change["argument"],
            property=change["property"],
            previous=_flat_value(details_before, change["property"]),
            new=_flat_value(details_after, change["property"]),
        )
        for change in changes
    ]

    mesh_assets = [asset.name for asset in object_service.find_related_mesh_assets(basemesh)]

    _LOG.debug("set_macro_details: %d change(s) on %r, refit_performed=%r",
               len(changed), basemesh.name, refit_performed)

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
        race_normalized=abs(race_sum - 1.0) <= macro_reading.RACE_SUM_TOLERANCE,
        macro_shapekeys_before=shapekeys_before,
        macro_shapekeys_after=shapekeys_after,
        shapekeys_removed=[name for name in shapekeys_before if name not in shapekeys_after],
        shapekeys_added=[name for name in shapekeys_after if name not in shapekeys_before],
        refit_requested=refit_requested,
        refit_performed=refit_performed,
        refit_incomplete_reason=refit_incomplete_reason,
        # Reported whenever the fit was not brought up to date, including the
        # partial refit above: a command that moves a body under fitted clothes
        # and says nothing has told the caller something false by omission.
        assets_possibly_stale=None if refit_performed else dict(
            mesh_assets=mesh_assets,
            mesh_asset_count=len(mesh_assets),
            rig_attached=rig is not None,
            rig_object_name=None if rig is None else rig.name,
        ),
        message=_message_for(basemesh, changed, refit_performed, refit_incomplete_reason,
                             mesh_assets, rig, race_sum),
    )

    # The verb is "recalculated", which is false in every refusal and in the
    # no-op call that named no slider. See shared/performed.py.
    return with_performed(result, result["recalculated"])
