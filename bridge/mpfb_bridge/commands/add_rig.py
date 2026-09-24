"""
``add_rig``: attach a rig, and report what that cost.

**The first consumer of a catalogue's identifiers.** ``list_rigs`` predicts,
per rig, which file would load and whose weights come with it; this does it. The
two read one implementation - [`shared/rig_lookup.py`](../shared/rig_lookup.py)
- because a caller who reads the catalogue and then acts on it is entitled to
get back what the catalogue promised, and the only way to guarantee that is for
the prediction and the action to be one rule rather than two that happen to
match today.

**Dispatch is on the prefix and nothing else**, exactly as
``HumanService._check_add_rig()`` does it: ``custom.`` selects
``add_custom_rig()`` and everything else goes to ``add_builtin_rig()``, which
handles the ``rigify.`` prefix itself. The caller never names the function.
Crossing the two does not fail legibly - ``add_builtin_rig("custom.my_rig")``
looks for a file called ``rig.custom.my_rig.json``, and ``add_custom_rig()``
strips the first seven characters of whatever it is given.

**Everything is checked before anything is added**, because ``operator=None`` -
which is what a command has - changes the failure mode of both adding functions:
they report through the operator when they have one and *raise* when they do
not. A missing built-in rig file is an ``IOError``, an unknown custom rig a
``ValueError``, and a Rigify rig with Rigify disabled a ``NotImplementedError``.
Each of those is an ordinary situation an agent will reach, and each comes back
here as a sentence.

There is one exception, and it is why this catches ``AssertionError``:
``add_builtin_rig()`` carries a bare ``assert
len(armature_object.data.rigify_colors) > 0`` for a Rigify rig, downstream of
the ``check_for_rigify()`` guard and so not pre-checkable. It fires *after* the
armature has been created and named but *before* it is parented, so the failure
leaves a stray armature behind - which is reported rather than left for the user
to find. That is a **mutating command whose failure is not a no-op**, and
``partial_objects_created`` is what makes it recoverable.

The other silent path is weights. ``add_builtin_rig()`` reports a missing
weights file through the operator only, so with none it adds an unweighted rig
and says nothing at all. ``weights_loaded`` is how that becomes visible.

Finally, the ordering constraint this command exists to make visible.
``HumanService.add_mhclo_asset()`` rigs a garment only if a ``Skeleton``
relative exists at the moment the garment is attached, and nothing re-rigs it
afterwards - ``HumanService.refit()`` deliberately passes ``set_parent=False``.
So a character dressed before it was rigged has clothes that will not follow the
armature, with no error anywhere. The mesh assets and sub-rigs are therefore
enumerated *before* the rig is added, which is what makes the claim precise:
these are the assets that were attached while there was no rig.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "add_rig",
)

import os

import bpy

from ..log import get_logger
from ..shared import blender_data
from ..shared import mpfb_surface
from ..shared import rig_lookup
from ..shared import selection
from ..shared import subject_resolution
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.addrig")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("identifier", TYPE_STRING, required=True,
          description="A rig identifier as list_rigs reports it - 'default', 'rigify.human', "
                      "'custom.my_rig'. Pass the 'identifier', never the 'name'."),
    Param("import_weights", TYPE_BOOLEAN, default=True,
          description="Load the rig's vertex weights. False parents the mesh to the armature "
                      "without deforming it, which is invisible until the character is posed."),
)

SUMMARY = "Attach a rig to a character, and report what was and was not weighted."

RIGIFY_MISSING_REASON = (
    "Rigify is not enabled in this Blender. HumanService.add_builtin_rig() raises "
    "NotImplementedError for a rigify rig rather than degrading, so no rig was added. Enable the "
    "Rigify add-on in Blender's preferences, or pick a standard rig from mpfb_list_rigs."
)

NEXT_STEP_AFTER_METARIG = (
    "This is a Rigify *meta* rig, not a finished rig. Attach the character's clothes and other "
    "mesh assets now, and only then call mpfb_generate_rigify_rig - generation re-parents and "
    "re-weights whatever is on the character at the time it runs, so anything added afterwards "
    "will not be handled."
)


def _known_builtin_identifiers(rigs_dir, family_subdir, prefix):
    """Every identifier ``add_builtin_rig()`` could load out of one subdir.

    The directory is the authority, not MPFB's UI enum: a rig file with no enum
    entry is still addable, and telling a caller it does not exist would be
    wrong. Same rule as ``list_rigs``' scan, and the same filter - the weights
    files live in these directories too.
    """
    identifiers = []
    if rigs_dir is None:
        return identifiers
    subdir_path = os.path.join(rigs_dir, family_subdir)
    if not os.path.isdir(subdir_path):
        return identifiers
    for filename in sorted(os.listdir(subdir_path)):
        if not filename.startswith("rig.") or not filename.endswith(".json"):
            continue
        bare = filename[len("rig."):-len(".json")]
        if bare:
            identifiers.append(prefix + bare)
    return identifiers


def _location_of(blender_object):
    return [float(value) for value in blender_object.location]


def _is_origin(location):
    for value in location:
        if abs(value) > 1e-06:
            return False
    return True


def _armature_modifier_for(mesh_object, armature_object):
    """Whether an ARMATURE modifier on this mesh points at this armature.

    **An observation, not a prediction, and the difference was found here.** The
    program this replaced carried a comment saying that
    ``RigService.ensure_armature_modifier()`` is called only when
    ``import_weights`` is true. Put to a running MPFB by
    ``bridge/test/tests/ddd_mutating/add_rig_test.py`` it turned out to be
    false: ``Rig.create_armature_and_fit_to_basemesh()`` adds the modifier
    itself, with ``add_modifier`` defaulting to true, so the modifier is there
    either way and ``add_builtin_rig()``'s own ``ensure_armature_modifier()``
    call merely finds it already present.

    The reported field is unchanged, because it was always read off the object
    rather than derived from the argument - which is exactly why the correction
    costs a comment rather than a behaviour. What ``import_weights`` really
    decides is whether *weights* were loaded, and that is ``weights_loaded``.
    """
    for modifier in getattr(mesh_object, "modifiers", None) or []:
        if getattr(modifier, "type", None) != "ARMATURE":
            continue
        if getattr(modifier, "object", None) is armature_object:
            return True
    return False


def _rig_resolution(services, requested_identifier, requested_family):
    """Which file would load, whose weights come with it, and what else was there.

    Done before anything is touched, and through the same module ``list_rigs``
    predicted it with, so the catalogue and the action cannot disagree.
    """
    rigs_dir = rig_lookup.rigs_directory(services)
    resolution = {
        "rigs_dir": rigs_dir,
        "rig_definition_path": None,
        "weights_available": False,
        "weights_path": None,
        "weights_from": None,
        "known_identifiers": [],
        "identifier_exists": False,
        # The name this rig's *own* weights file would carry - the bare name for
        # a built-in, the short name for a custom one. ``weights_from`` is always
        # a bare name, so comparing it against the identifier would report
        # rigify.human_toes as borrowing from itself.
        "own_weights_name": None,
    }

    if requested_family == "custom":
        short_name = rig_lookup.custom_short_name(requested_identifier)
        custom_records = rig_lookup.custom_rig_records(services, False)
        resolution["known_identifiers"] = sorted(
            "custom." + str(record.get("name") or "")
            for record in custom_records or [] if record.get("name"))
        resolution["own_weights_name"] = short_name
        record = rig_lookup.custom_rig_record(custom_records, short_name)
        if record is not None:
            resolution["identifier_exists"] = True
            resolution["rig_definition_path"] = mpfb_surface.as_path(record.get("path"))
            (resolution["weights_available"], resolution["weights_path"],
             resolution["weights_from"]) = rig_lookup.custom_weights(
                 resolution["rig_definition_path"], short_name)
        return resolution

    subdir, bare_name = rig_lookup.builtin_subdir(requested_identifier)
    resolution["own_weights_name"] = bare_name
    prefix = "rigify." if requested_family == "rigify" else ""
    resolution["known_identifiers"] = _known_builtin_identifiers(rigs_dir, subdir, prefix)
    candidate = rig_lookup.builtin_rig_file(rigs_dir, requested_identifier)
    if candidate is not None and os.path.isfile(candidate):
        resolution["identifier_exists"] = True
        resolution["rig_definition_path"] = candidate
        (resolution["weights_available"], resolution["weights_path"],
         resolution["weights_from"]) = rig_lookup.builtin_weights(
             services, requested_identifier, os.path.join(rigs_dir, subdir))
    return resolution


def _blocked(subject, basemesh, subject_resolved_by, requested_identifier, requested_family,
             reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=basemesh is not None,
        ready=False,
        added=False,
        blocked_by=reason,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        identifier=requested_identifier,
        family=requested_family,
        rig_object_name=None,
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _refusal(services, subject, basemesh, subject_resolved_by, requested_identifier,
             requested_family, resolution, existing_rig, message):
    """The first refusal that applies, or ``None``.

    In a fixed order: the argument first, then the world. An identifier that
    names nothing is a mistake the caller can fix without looking at the scene,
    so it is worth reporting even when the scene would also have refused.
    """
    def blocked(reason, text, **extra):
        return _blocked(subject, basemesh, subject_resolved_by, requested_identifier,
                        requested_family, reason, text, **extra)

    if basemesh is None:
        return blocked("subject_not_found", message,
                       known_identifiers=resolution["known_identifiers"])
    if requested_family == "rigify" and not services["SystemService"].check_for_rigify():
        return blocked("rigify_unavailable", RIGIFY_MISSING_REASON, rigify_available=False)
    if not resolution["identifier_exists"]:
        return blocked(
            "unknown_identifier",
            "No {:s} rig is identified by '{!s}', so no rig was added. known_identifiers lists "
            "what this Blender could add in that family; call mpfb_list_rigs for all three "
            "families with their labels. Pass a rig's 'identifier', not its 'name'.".format(
                requested_family, requested_identifier),
            known_identifiers=resolution["known_identifiers"])
    if existing_rig is not None:
        # MPFB's own panels hide the add button in this state. Adding a second
        # rig re-parents the basemesh to it and silently orphans the first,
        # which is why this refuses rather than offering a force flag: the
        # recovery is to delete the existing rig, and that is not this command's
        # job.
        return blocked(
            "already_rigged",
            "The character '{:s}' already has the rig '{:s}', so no rig was added. MPFB has no "
            "way to swap a rig: adding a second one re-parents the basemesh to it and leaves the "
            "first orphaned. Delete '{:s}' first if the rig really should be replaced.".format(
                basemesh.name, existing_rig.name, existing_rig.name),
            existing_rig_object_name=existing_rig.name,
            existing_rig_type=services["RigService"].identify_rig(existing_rig)
            if existing_rig.type == "ARMATURE" else None)
    if basemesh.mode != "OBJECT" or bpy.context.mode != "OBJECT":
        # Two checks rather than one, and both are needed. Building the armature
        # runs bpy.ops.object.armature_add() and bpy.ops.object.mode_set(),
        # which poll on the *context* mode - so an unrelated object left in edit
        # mode fails the operator even though the basemesh itself looks fine.
        return blocked(
            "not_object_mode",
            "Blender is in {:s} mode and the basemesh '{:s}' is in {:s} mode. Building an "
            "armature runs operators that require OBJECT mode, so no rig was added. Leave edit "
            "mode and call again.".format(
                str(bpy.context.mode), basemesh.name, str(basemesh.mode)))
    return None


def _message_for(requested_family, requested_identifier, basemesh, rig_object, import_weights,
                 resolution, mesh_assets_not_rigged, subrigs_not_rigged,
                 basemesh_location_before, is_metarig):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Added the {:s} rig '{!s}' to '{:s}' as '{:s}'.".format(
        requested_family, requested_identifier, basemesh.name,
        rig_object.name if rig_object is not None else "?")]
    if not import_weights:
        parts.append(" Weights were not imported, so the mesh is parented to the armature but "
                     "not deformed by it.")
    elif not resolution["weights_available"]:
        parts.append(" No weights file exists for this rig, so the character has no vertex "
                     "weights and will not deform when posed. MPFB reports this only through an "
                     "operator, and there is none here.")
    elif (resolution["weights_from"] is not None
          and resolution["weights_from"] != resolution["own_weights_name"]):
        parts.append(" Weights were loaded from '{!s}' through MPFB's fallback table, which is "
                     "normal for this rig.".format(resolution["weights_from"]))
    if not _is_origin(basemesh_location_before):
        parts.append(" The basemesh was moved to the origin and the armature took its previous "
                     "location, which is what both adding functions do.")
    if mesh_assets_not_rigged or subrigs_not_rigged:
        parts.append(
            " {:d} asset(s) were already on this character before the rig existed and are NOT "
            "rigged: add_mhclo_asset() rigs a garment only if a rig is present when it is "
            "attached, and nothing re-rigs it afterwards - mpfb_refit_human will not either. "
            "Remove and re-add them, or accept that they will not follow the armature.".format(
                len(mesh_assets_not_rigged) + len(subrigs_not_rigged)))
    if is_metarig:
        parts.append(" " + NEXT_STEP_AFTER_METARIG)
    return "".join(parts)


def add_rig(params, resolution_context):  # pylint: disable=too-many-locals
    """Attach one rig to one character, having checked everything first."""
    services = resolution_context.services
    object_service = services["ObjectService"]

    requested_name = params["name"]
    requested_identifier = params["identifier"]
    import_weights = params["import_weights"]

    requested_family = rig_lookup.family_of(requested_identifier)
    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name,
        not_done="no rig was added",
        not_a_character="there is nothing to rig, since rigs attach to a basemesh")

    resolution = _rig_resolution(services, requested_identifier, requested_family)

    existing_rig = None
    if basemesh is not None:
        existing_rig = object_service.find_object_of_type_amongst_nearest_relatives(
            basemesh, "Skeleton")

    refused = _refusal(services, subject, basemesh, subject_resolved_by, requested_identifier,
                       requested_family, resolution, existing_rig, message)
    if refused is not None:
        _LOG.debug("add_rig: refused %r for %r", refused["blocked_by"], requested_identifier)
        return refused

    # Read before the rig exists, which is what makes the claim below precise:
    # these are the assets that were attached while there was no rig, and
    # nothing will rig them retroactively.
    mesh_assets_not_rigged = [
        asset.name for asset in object_service.find_related_mesh_assets(basemesh)
    ]
    subrigs_not_rigged = [
        subrig.name for subrig in
        object_service.find_all_objects_of_type_amongst_nearest_relatives(basemesh, "Subrig")
    ]

    basemesh_location_before = _location_of(basemesh)
    names_before = blender_data.object_names()

    rig_object = None
    assertion_message = None
    with selection.restored(basemesh):
        try:
            # MPFB's own operators run with the basemesh active, and the armature is
            # created through bpy.ops, which reads the context.
            object_service.activate_blender_object(basemesh)
            if requested_family == "custom":
                rig_object = services["HumanService"].add_custom_rig(
                    basemesh, requested_identifier, import_weights=import_weights)
            else:
                rig_object = services["HumanService"].add_builtin_rig(
                    basemesh, requested_identifier, import_weights=import_weights)
        except AssertionError:
            # add_builtin_rig()'s bare `assert len(armature_object.data.rigify_colors) > 0`,
            # which carries no message at all. It fires after the armature has been
            # created and named and before it is parented, so there is a stray
            # object to account for.
            assertion_message = (
                "Blender has Rigify enabled but its colour sets did not initialise, so MPFB's "
                "internal check on the new armature failed. This is an AssertionError with no "
                "message inside HumanService.add_builtin_rig(). The rig was not attached to the "
                "character.")

    if assertion_message is not None:
        stray = sorted(blender_data.object_names() - names_before)
        return _blocked(
            subject, basemesh, subject_resolved_by, requested_identifier, requested_family,
            "rigify_colors_missing",
            assertion_message + (
                (" A partly built armature was left behind: " + ", ".join(stray)
                 + ". Delete it before trying again.") if stray else ""),
            partial_objects_created=stray)

    if rig_object is None:
        # Neither function returns None with operator=None - they raise - but
        # MPFB's own rigify operator carries this same fallback, and a response
        # that said "added" with no name would be worse than one that looked the
        # rig up a second way.
        rig_object = object_service.find_object_of_type_amongst_nearest_relatives(
            basemesh, "Skeleton")

    is_metarig = requested_family == "rigify"
    weights_loaded = bool(import_weights and resolution["weights_available"])
    armature_modifier_added = bool(
        rig_object is not None and _armature_modifier_for(basemesh, rig_object))
    basemesh_location_after = _location_of(basemesh)

    _LOG.debug("add_rig: added %r as %r, weights_loaded=%r",
               requested_identifier, None if rig_object is None else rig_object.name,
               weights_loaded)

    result = dict(
        found=True,
        ready=True,
        added=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        identifier=requested_identifier,
        family=requested_family,
        add_function_used=(
            "add_custom_rig" if requested_family == "custom" else "add_builtin_rig"),
        rig_definition_path=resolution["rig_definition_path"],
        # Read off the created object rather than predicted: Blender uniquifies
        # a name that is already taken, so a second character in the same file
        # gets '<basemesh>.rig.001'.
        rig_object_name=None if rig_object is None else rig_object.name,
        is_metarig=is_metarig,
        next_step=NEXT_STEP_AFTER_METARIG if is_metarig else None,
        import_weights=import_weights,
        weights_loaded=weights_loaded,
        weights_from=resolution["weights_from"] if weights_loaded else None,
        weights_path=resolution["weights_path"] if weights_loaded else None,
        armature_modifier_added=armature_modifier_added,
        basemesh_location_before=basemesh_location_before,
        basemesh_moved_to_origin=(
            not _is_origin(basemesh_location_before) and _is_origin(basemesh_location_after)),
        rig_location=None if rig_object is None else _location_of(rig_object),
        mesh_assets_not_rigged=mesh_assets_not_rigged,
        subrigs_not_rigged=subrigs_not_rigged,
        message=_message_for(requested_family, requested_identifier, basemesh, rig_object,
                             import_weights, resolution, mesh_assets_not_rigged,
                             subrigs_not_rigged, basemesh_location_before, is_metarig),
    )

    # The verb is "added". See shared/performed.py.
    return with_performed(result, result["added"])
