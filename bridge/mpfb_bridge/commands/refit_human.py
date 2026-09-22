"""
``refit_human``: MPFB's ``HumanService.refit()``, plus the one failure it
cannot report to a caller that is not an operator.

Refitting is what makes a dressed, rigged character survive a change to its
body: every garment is re-fitted to the new shape and the rig is rebuilt to
match. MPFB does the work. What this command adds is the part MPFB has no way to
tell anybody about.

**A precondition is an answer, not an exception**, and this is the command that
establishes the rule for the twelve that follow. ``refit()`` cannot refit a
*generated* Rigify rig with no meta rig left in the scene - only the meta rig
carries the MakeHuman vertex data it needs - so it refits the mesh assets, logs
a warning, tries to report through an ``operator`` a command has none of, and
returns. Nothing in its return value says so. The detection is
[`shared/refit_blocker.py`](../shared/refit_blocker.py), shared with the three
commands that refit after changing the body; the **sentence** is written here,
because this is the one place where the refit has already been attempted and the
mesh assets really were refitted, and the other three are predicting one they
are about to make. The answer stays a successful envelope carrying
``refit_performed: false``.

**``refit()`` raises ``ValueError`` when it cannot find a basemesh.** The
basemesh is therefore resolved here first, so that "this object is not part of a
character" comes back as an ordinary ``found: false`` rather than as a
``command_failed`` envelope with a traceback in it.

**What was refitted is enumerated before the call**, with the same two lookups
``refit()`` itself makes - from the rig when there is one, from the basemesh
otherwise, children only. Enumerating afterwards would describe what is there
now rather than what was touched, and enumerating with different rules would be
a second, differently-scoped answer wearing the same field names.

**The caller's selection and active object are restored**, in a ``finally``, as
twelve of the thirteen mutating commands do. ``ClothesService`` restores the
active object itself, but only around its own edit-mode excursion; this covers
the whole call, and the user is looking at this scene.

This reproduces ``codegen/payloads/refit_human.py`` rather than tidying it up.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "refit_human",
)

import bpy

from ..log import get_logger
from ..shared.performed import with_performed
from ..shared.refit_blocker import rig_refit_is_blocked
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.refithuman")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family - the basemesh, its rig, a garment. "
                      "Omit or pass null to use whatever object is currently active."),
)

SUMMARY = "Refit a character's assets and rig to its current body shape."


def _rig_refit_blocker(services, rig):
    """Why refit() would leave this rig untouched, or ``None``.

    The condition is ``rig_refit_is_blocked()`` from the shared module, which
    the three commands that refit after a change ask as well; the wording is
    this command's own, because this is the one place where the refit has
    already been attempted and the mesh assets really were refitted. Answering
    it at all is what keeps this command from reporting ``refit_performed:
    true`` over a rig it never touched.
    """
    if not rig_refit_is_blocked(services, rig):
        return None
    return ("The rig '{:s}' is a generated Rigify rig and no meta rig is left in the scene, so it "
            "could not be refitted. Its mesh assets were. Regenerate the rig with the Rigify "
            "sub-panel's 'Meta-rig' option set to Keep or Hide to allow refitting.".format(
                rig.name))


def _stamped(result):
    """The uniform flag, set from ``refit_performed`` and never beside it.

    One function rather than a ``with_performed()`` call in each of the three
    branches that build an answer, because "refit_performed" already means
    exactly what "performed" means here and the two must not be able to
    disagree about the generated-Rigify-rig-with-no-meta-rig case. See
    shared/performed.py for why the flag is stamped onto a finished answer
    rather than written into each branch.
    """
    return with_performed(result, result["refit_performed"])


def _resolve(services, requested_name):
    """The basemesh to refit, the object asked about, and the sentence on a miss."""
    if requested_name is None:
        # The view layer rather than bpy.context.active_object: this runs from a
        # timer in the add-on's own context, not from a viewport operator.
        subject = bpy.context.view_layer.objects.active
        if subject is None:
            return (None, None,
                    "No object name was given and no object is active in this Blender session, so "
                    "nothing was refitted. Select a MakeHuman object, or call mpfb_list_objects "
                    "and pass one of its names.")
    else:
        subject = bpy.data.objects.get(requested_name)
        if subject is None:
            return (None, None,
                    "No object named '{:s}' exists in this .blend file, so nothing was refitted. "
                    "Call mpfb_list_objects to see what the current scene holds.".format(
                        str(requested_name)))

    # refit() makes this same call and raises when it comes back None. Making it
    # here first turns that into an answer.
    basemesh = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        subject, "Basemesh")
    if basemesh is None:
        return (None, subject,
                "'{:s}' has no MakeHuman basemesh among its nearest relatives, so there is "
                "nothing to refit it to. Call mpfb_get_object_info to see what it is related "
                "to.".format(subject.name))
    return (basemesh, subject, None)


def _message_for(basemesh, mesh_assets, rig, subrigs, refit_incomplete_reason):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Refitted {:d} mesh asset(s) to basemesh '{:s}'.".format(
        len(mesh_assets), basemesh.name)]
    if refit_incomplete_reason is not None:
        parts.append(" " + refit_incomplete_reason)
    elif rig is None:
        parts.append(" This character has no rig.")
    else:
        parts.append(" The rig '{:s}' and {:d} sub-rig(s) were refitted as well.".format(
            rig.name, len(subrigs)))
    return "".join(parts)


def refit_human(params, resolution):
    """Refit one character, and say honestly what could not be refitted."""
    services = resolution.services
    object_service = services["ObjectService"]

    requested_name = params["name"]
    subject_resolved_by = "active" if requested_name is None else "name"
    basemesh, subject, message = _resolve(services, requested_name)

    if basemesh is None:
        _LOG.debug("refit_human: no basemesh resolved from %r", requested_name)
        return _stamped(dict(
            found=False,
            ready=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            refit_performed=False,
            message=message,
        ))

    if basemesh.mode != "OBJECT":
        # Fitting reaches bpy.ops.object.mode_set through ClothesService, which
        # is not a thing to attempt while the user has the basemesh open in edit
        # mode.
        return _stamped(dict(
            found=True,
            ready=False,
            blocked_by="not_object_mode",
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            refit_performed=False,
            message="The basemesh '{:s}' is in {:s} mode. Refitting requires OBJECT mode, so "
                    "nothing was refitted. Leave edit mode and call again.".format(
                        basemesh.name, str(basemesh.mode)),
        ))

    rig = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")

    # refit() walks from the rig when there is one and from the basemesh
    # otherwise, and takes only children. Enumerating with the same rules is
    # what makes these lists a report of what was touched rather than a
    # separate, differently-scoped answer.
    parent_object = basemesh if rig is None else rig
    mesh_assets = [
        asset.name for asset in object_service.find_related_mesh_assets(
            parent_object, only_children=True)
    ]
    subrigs = [
        subrig.name for subrig in
        object_service.find_all_objects_of_type_amongst_nearest_relatives(
            parent_object, "Subrig", only_children=True)
    ]

    refit_incomplete_reason = _rig_refit_blocker(services, rig)

    previous_active = bpy.context.view_layer.objects.active
    basemesh_was_selected = bool(basemesh.select_get())
    try:
        services["HumanService"].refit(basemesh)
    finally:
        # ClothesService restores the active object itself, but only around its
        # own edit-mode excursion. Restoring here covers the whole call, and the
        # user is looking at this scene.
        if not basemesh_was_selected:
            basemesh.select_set(False)
        bpy.context.view_layer.objects.active = previous_active

    _LOG.debug("refit_human: %d mesh asset(s), rig=%r, blocked=%r",
               len(mesh_assets), None if rig is None else rig.name,
               refit_incomplete_reason is not None)

    result = dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        basemesh_has_shapekeys=bool(services["TargetService"].has_any_shapekey(basemesh)),
        rig_name=None if rig is None else rig.name,
        mesh_assets=mesh_assets,
        mesh_asset_count=len(mesh_assets),
        subrigs=subrigs,
        subrig_count=len(subrigs),
        refit_performed=refit_incomplete_reason is None,
        refit_incomplete_reason=refit_incomplete_reason,
        message=_message_for(basemesh, mesh_assets, rig, subrigs, refit_incomplete_reason),
    )

    return _stamped(result)
