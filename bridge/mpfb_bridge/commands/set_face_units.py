"""
``set_face_units``: compose a character's face directly, from ARKit units.

Wraps ``FaceService.set_expression()``, which is **additive** - a face unit not
named in a call is left exactly as it was - and, unlike ``mpfb_set_targets``,
takes its whole batch as one dict rather than resolving entries one at a time,
so this command resolves the vocabulary and the asset pack up front and then
makes one call into MPFB rather than fifty.

**The vocabulary is checked here, not on mpfb-mcp's side of the socket.**
``ARKIT_FACEUNITS`` is MPFB's own list, read off the ``FaceService`` handle the
bootstrap already provides; a copy on the tool side could drift. Every
requested name is checked against it **before anything is written** - a batch
of eight units with one typo applies zero of them, because
``FaceService.set_expression`` itself only warns and skips an unrecognised name,
which would otherwise silently apply seven and report success. An unresolvable
name is refused together with the closest legal ones
(:func:`difflib.get_close_matches`), per
[how tools name things that can be added](../../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added).

**The asset pack is a precondition, checked the same way.** Without
``faceunits01`` every ``!ex-`` target file is missing, and
``set_expression`` still returns normally, having warned to a log nobody reads
and moved nothing - MPFB's panels handle this by not drawing themselves, which
this command inherits nothing from. So the probe
(``FaceService.is_faceunits01_installed()``, MPFB's own and cached exactly the
way it is elsewhere - see ``get_face_units`` for the cache and ``refresh``,
which this command does not take, since a caller who wants a fresh probe reads
one there first) is checked before any write, and the whole call is refused
when it fails. **That probe tests one target and a partially installed pack
passes it anyway** - so a per-unit resolution failure at write time is its own
reportable outcome (``could_not_load``), never folded into the up-front refusal.

**What actually happens to a requested unit, worked out before calling
``set_expression`` rather than inferred from what changed afterward:**

- Already backed by a shape key: this is an ordinary value write, reported
  under ``applied``.
- Not backed by a shape key and requested at ``0.0``: ``set_expression`` itself
  skips loading a target just to write a zero into it, so the unit is left
  entirely alone - not created, not touched - and reported separately
  (``skipped_absent_at_zero``) so that "set everything to zero" and "clear
  first" can be told apart even though both reach the same mesh state.
- Not backed by a shape key, requested non-zero, and a target file exists:
  loaded from disk, reported under ``loaded_from_disk``.
- Not backed by a shape key, requested non-zero, and no target file exists:
  ``could_not_load``, which is the partial-install case the up-front probe
  cannot catch.

``clear_first`` runs ``FaceService.clear_expression()`` before any of the above
is measured, which is why the presence check happens after it: a call that
clears and then re-requests the same units at their old values should not see
them as "already present with the old value" versus "cleared".

Refits per [`shared/refit_blocker.py`](../shared/refit_blocker.py), the fifth
command to. ``refit`` defaults to ``True`` here, unlike every other refitting
command in this package *and unlike MPFB's composer panel*, whose ``auto_refit``
defaults to ``False``. FR 026 wrote that the default matched that panel, and it
did not: it is the *library* panel's ``auto_refit`` that defaults to ``True``.
[FR 027](../../../feature-requests/done/027-expression-library/README.md) kept
the default on its own merits and corrected the reason: the panel defaults to
``False`` because a human drags a slider through dozens of values and each would
refit, whereas composing across MCP is normally one batched call, and
expression shape keys deform the face while garments and hair do not follow
without a refit.

**Every answer says whether the stack still explains the face**, through
[`shared/expression_divergence.py`](../shared/expression_divergence.py) - the
same comparison ``get_expression`` and ``apply_expressions`` report. What this
command writes is transient: the next library change (``apply_expressions``, a
preset load) rebuilds the face from the applied-expressions stack, clearing
first. FR 026 said so in a fixed sentence in every answer; the computed
``matches_stack`` and ``unexplained_face_units`` replaced it, per
[a tool whose effect is known in advance to be transient](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-known-in-advance-to-be-transient),
so that the normal case - an empty stack and nothing composed - reads as
nothing to worry about, and the case with something to lose names
``mpfb_save_expression`` as what keeps it.

The behaviours above are **MPFB's, reproduced rather than tidied up** where
they come from ``FaceService`` at all: the additive semantics, the
zero-into-absent skip, and the pack probe are established against a real
install and not tidied up under cover of wrapping them.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "set_face_units",
)

import difflib
import sys

import bpy

from ..log import get_logger
from ..shared.expression_divergence import divergence
from ..shared.performed import with_performed
from ..shared.refit_blocker import rig_refit_is_blocked
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setfaceunits")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("face_units", TYPE_ARRAY, default=(),
          description="One object per face unit: {'face_unit', 'weight'} with weight in "
                      "0.0-1.0. Every name is checked against ARKIT_FACEUNITS before anything "
                      "is written; one unrecognised name refuses the whole call."),
    Param("clear_first", TYPE_BOOLEAN, default=False,
          description="Zero every ARKit face unit before applying this call's entries. "
                      "FaceService.set_expression is additive by default: a unit not "
                      "mentioned is left untouched."),
    Param("refit", TYPE_BOOLEAN, default=True,
          description="Re-fit clothes and the rig afterwards. True, unlike every other "
                      "refitting command here and unlike the composer panel: composing across "
                      "MCP is one batched call rather than a dragged slider."),
)

SUMMARY = "Compose a character's face from ARKit face units, directly and transiently."


def _resolve(services, requested_name):
    """The basemesh to work on, the object asked about, and the sentence on a miss."""
    if requested_name is None:
        subject = bpy.context.view_layer.objects.active
        if subject is None:
            return (None, None,
                    "No object name was given and no object is active in this Blender session, "
                    "so nothing was changed. Select a MakeHuman object, or call "
                    "mpfb_list_objects and pass one of its names.")
    else:
        subject = bpy.data.objects.get(requested_name)
        if subject is None:
            return (None, None,
                    "No object named '{:s}' exists in this .blend file, so nothing was changed. "
                    "Call mpfb_list_objects to see what the current scene holds.".format(
                        str(requested_name)))

    basemesh = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        subject, "Basemesh")
    if basemesh is None:
        return (None, subject,
                "'{:s}' has no MakeHuman basemesh among its nearest relatives, so there is no "
                "face to compose.".format(subject.name))
    return (basemesh, subject, None)


def _precondition(basemesh):
    if basemesh.mode != "OBJECT":
        return ("not_object_mode",
                "The basemesh '{:s}' is in {:s} mode. Loading a face-unit target requires "
                "OBJECT mode, so nothing was changed. Leave edit mode and call "
                "again.".format(basemesh.name, str(basemesh.mode)))
    return (None, None)


def _unknown_names(arkit_faceunits, requested):
    """Every requested name not in ``arkit_faceunits``, each with close matches."""
    unknown = []
    for entry in requested:
        name = entry["face_unit"]
        if name in arkit_faceunits:
            continue
        unknown.append(dict(
            face_unit=name,
            closest=difflib.get_close_matches(name, arkit_faceunits, n=3, cutoff=0.5),
        ))
    return unknown


def _shapekey_present(target_service, basemesh, face_unit_name):
    shape_key_name = target_service.expression_name_to_shapekey_name(face_unit_name)
    if basemesh.data.shape_keys is None or basemesh.data.shape_keys.key_blocks is None:
        return None
    block = basemesh.data.shape_keys.key_blocks.get(shape_key_name)
    return None if block is None else float(block.value)


def _rig_refit_blocker(services, rig):
    if not rig_refit_is_blocked(services, rig):
        return None
    return ("The rig '{:s}' is a generated Rigify rig and no meta rig is left in the scene, so "
            "it cannot be refitted to the new face shape. Set the Rigify sub-panel's 'Meta-rig' "
            "option to Keep or Hide before generating, to allow refitting "
            "afterwards.".format(rig.name))


def _message_for(basemesh, applied, loaded_from_disk, could_not_load, skipped_absent_at_zero,
                 clear_first, installed, refit_requested, refit_performed,
                 refit_incomplete_reason, compared):
    parts = []
    if not installed:
        parts.append(
            "The faceunits01 asset pack does not appear to be installed, so nothing was "
            "changed. ")
    else:
        parts.append(
            "{:s}pplied {:d} face unit(s) to basemesh '{:s}'{:s}.".format(
                "Cleared every face unit, then a" if clear_first else "A",
                len(applied) + len(loaded_from_disk), basemesh.name,
                ", loading {:d} from disk".format(len(loaded_from_disk))
                if loaded_from_disk else ""))
        if could_not_load:
            parts.append(
                " {:d} unit(s) could not be loaded because their target file was not found, "
                "even though the pack passed its own install probe: {:s}.".format(
                    len(could_not_load), ", ".join(could_not_load)))
        if skipped_absent_at_zero:
            parts.append(
                " {:d} unit(s) were requested at 0.0 with no shape key on the mesh yet, so "
                "nothing was created for them.".format(len(skipped_absent_at_zero)))
        if compared is not None and not compared["matches_stack"]:
            parts.append(
                " {:d} face unit(s) are not explained by the character's applied-expressions "
                "stack, so the next mpfb_apply_expressions call or preset load will overwrite "
                "them; mpfb_save_expression keeps them.".format(
                    len(compared["unexplained_face_units"])))
        if refit_requested:
            if refit_performed:
                parts.append(" Assets and rig were refitted.")
            elif refit_incomplete_reason is not None:
                parts.append(" Mesh assets were refitted, but the rig was not: "
                             + refit_incomplete_reason)
    return "".join(parts)


def set_face_units(params, resolution):  # pylint: disable=too-many-locals,too-many-branches
    """Resolve the whole batch and the asset pack, then compose - or refuse cleanly."""
    services = resolution.services
    face_service = services["FaceService"]
    faceservice_module = sys.modules[face_service.__module__]
    target_service = services["TargetService"]
    object_service = services["ObjectService"]

    requested_name = params["name"]
    requested = list(params["face_units"])
    clear_first = params["clear_first"]
    refit_requested = params["refit"]

    subject_resolved_by = "active" if requested_name is None else "name"
    basemesh, subject, message = _resolve(services, requested_name)

    if basemesh is None:
        _LOG.debug("set_face_units: no basemesh resolved from %r", requested_name)
        return with_performed(dict(
            found=False,
            ready=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            applied=[],
            loaded_from_disk=[],
            could_not_load=[],
            skipped_absent_at_zero=[],
            cleared=[],
            unknown_face_units=[],
            message=message,
        ), False)

    blocked_by, blocked_message = _precondition(basemesh)
    if blocked_by is not None:
        return with_performed(dict(
            found=True,
            ready=False,
            blocked_by=blocked_by,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            applied=[],
            loaded_from_disk=[],
            could_not_load=[],
            skipped_absent_at_zero=[],
            cleared=[],
            unknown_face_units=[],
            message=blocked_message,
        ), False)

    unknown = _unknown_names(faceservice_module.ARKIT_FACEUNITS, requested)
    if unknown:
        return with_performed(dict(
            found=True,
            ready=False,
            blocked_by="unknown_face_units",
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            applied=[],
            loaded_from_disk=[],
            could_not_load=[],
            skipped_absent_at_zero=[],
            unknown_face_units=unknown,
            message="{:d} face unit name(s) are not recognised, so nothing was changed: "
                    "{:s}.".format(
                        len(unknown),
                        ", ".join(entry["face_unit"] for entry in unknown)),
        ), False)

    installed = bool(face_service.is_faceunits01_installed())
    if not installed and requested:
        return with_performed(dict(
            found=True,
            ready=False,
            blocked_by="faceunits01_not_installed",
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            applied=[],
            loaded_from_disk=[],
            could_not_load=[],
            skipped_absent_at_zero=[],
            cleared=[],
            unknown_face_units=[],
            message="The faceunits01 asset pack does not appear to be installed, so nothing "
                    "was changed. Every ARKit face-unit target file would be missing.",
        ), False)

    cleared = []
    if clear_first:
        # Read before clearing, not after: a unit already at 0.0 was not
        # "cleared" by this call and should not be reported as a change.
        before_expression = face_service.read_current_expression(basemesh)
        cleared = [name for name, value in before_expression.items() if value != 0.0]
        face_service.clear_expression(basemesh)

    applied = []
    loaded_from_disk = []
    could_not_load = []
    skipped_absent_at_zero = []
    expression_dict = {}
    previous_values = {}
    for entry in requested:
        face_unit_name = entry["face_unit"]
        weight = float(entry["weight"])
        previous_value = _shapekey_present(target_service, basemesh, face_unit_name)
        present_before = previous_value is not None

        if not present_before and weight == 0.0:
            skipped_absent_at_zero.append(face_unit_name)
            continue
        if not present_before:
            if target_service.target_full_path(face_unit_name) is None:
                could_not_load.append(face_unit_name)
                continue
            loaded_from_disk.append(face_unit_name)
        else:
            applied.append(face_unit_name)
        previous_values[face_unit_name] = previous_value
        expression_dict[face_unit_name] = weight

    if expression_dict:
        face_service.set_expression(basemesh, expression_dict)

    applied_entries = []
    for face_unit_name in applied + loaded_from_disk:
        applied_entries.append(dict(
            face_unit=face_unit_name,
            weight=round(float(expression_dict[face_unit_name]), 6),
            previous_value=previous_values[face_unit_name],
            new_value=round(
                _shapekey_present(target_service, basemesh, face_unit_name) or 0.0, 6),
        ))

    refit_incomplete_reason = None
    refit_performed = False
    changed_something = bool(applied_entries) or bool(cleared)
    rig = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
    if refit_requested and changed_something:
        refit_incomplete_reason = _rig_refit_blocker(services, rig)
        # refit() reaches bpy.ops through ClothesService. Put back what was
        # borrowed, as refit_human does: the user is looking at this scene.
        previous_active = bpy.context.view_layer.objects.active
        basemesh_was_selected = bool(basemesh.select_get())
        try:
            services["HumanService"].refit(basemesh)
        finally:
            if not basemesh_was_selected:
                basemesh.select_set(False)
            bpy.context.view_layer.objects.active = previous_active
        refit_performed = refit_incomplete_reason is None

    mesh_assets = [asset.name for asset in object_service.find_related_mesh_assets(basemesh)]
    compared = divergence(services, basemesh)

    _LOG.debug(
        "set_face_units: %d applied, %d loaded, %d could_not_load, %d skipped-absent-at-zero",
        len(applied), len(loaded_from_disk), len(could_not_load), len(skipped_absent_at_zero))

    result = dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        faceunits01_installed=installed,
        clear_first=clear_first,
        applied=applied_entries,
        applied_count=len(applied_entries),
        loaded_from_disk=loaded_from_disk,
        could_not_load=could_not_load,
        skipped_absent_at_zero=skipped_absent_at_zero,
        cleared=cleared,
        unknown_face_units=[],
        matches_stack=compared["matches_stack"],
        unexplained_face_units=compared["unexplained_face_units"],
        applied_expression_count=len(compared["applied_expressions"]),
        refit_requested=refit_requested,
        refit_performed=refit_performed,
        refit_incomplete_reason=refit_incomplete_reason,
        assets_possibly_stale=None if (refit_performed or not changed_something) else dict(
            mesh_assets=mesh_assets,
            mesh_asset_count=len(mesh_assets),
            rig_attached=rig is not None,
            rig_name=None if rig is None else rig.name,
        ),
        message=_message_for(
            basemesh, applied, loaded_from_disk, could_not_load, skipped_absent_at_zero,
            clear_first, installed, refit_requested, refit_performed, refit_incomplete_reason,
            compared),
    )

    return with_performed(result, changed_something)
