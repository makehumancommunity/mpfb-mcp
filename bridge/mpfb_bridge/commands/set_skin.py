"""
``set_skin``: apply a skin, and say what it destroyed on the way.

**The work itself is MPFB's.** ``HumanService.set_character_skin()`` deletes the
old materials, records the source fragment, builds one of five node trees and
optionally creates the per-region material slots. None of that is reimplemented.
What is here is everything around it, and five things in particular.

**The vocabulary check has to happen before the call, not inside it.** That
function tests its five types with five separate ``if`` statements, *after*
opening with ``delete_all_materials(..., also_destroy_groups=True)`` on both
objects. An unrecognised ``skin_type`` therefore destroys the character's
materials, builds nothing, and then raises from
``create_and_assign_material_slots()`` about a mesh with no materials. So the
type is checked here first and refused as an answer.

**The UI's ``material_instances`` coercion is the UI's alone.**
``loadlibraryskin.py`` forces the flag to ``False`` for ``LAYERED``,
``GAMEENGINE`` *and* ``MAKESKIN``; the service's own guard names only the first
two. Following the panel is deliberate - it is what the user sees and what a
character loaded from a ``.mhm`` was made with - and both values are reported,
because a silent coercion looks like a bug. ``MAKESKIN`` is also the default
type, which is why **the default call creates no material instances**.

**The body proxy is resolved here and passed explicitly.**
``set_character_skin()`` would resolve it itself when handed ``None``, but this
needs the same object anyway - for ``materials_destroyed``, for the active-slot
fixup and for the response, which is the only place a caller learns that a
second object was modified at all.

**Everything reported as destroyed is read before the call.** The materials are
gone the moment that function's first statement runs, and with
``also_destroy_groups=True`` their node groups go too. That is also why the call
is wrapped in a broad ``except``: by the time anything inside can raise, the old
materials are already deleted, so a ``command_failed`` envelope would leave the
caller with a stripped character and no record of what was on it.

**The active-material-slot fixup is UI behaviour with no service behind it.**
After loading, MPFB's operator selects the slot whose material name ends in
``body``, on the basemesh and on the proxy, so the user's material properties
panel is not looking at a fingernail. Reproduced statement for statement, last
match winning, exactly as ``loadlibraryskin.py`` does.

Two facts are reported that nothing in Blender shows. The enhanced types copy
``enhanced_settings.default.json`` into the user config directory when it is
absent - the only file this add-on ever writes outside the ``.blend`` - and the
copy is gated on ``material_instances`` rather than on the skin type, so the
default call writes nothing. And the enhanced types derive a scale name from the
character's ``scale_factor``, which changes the subsurface radii; note where the
bands fall, since the property's declared default of ``1.0`` is misleading and
``create_human()`` writes ``0.1`` onto every character it makes.

The skins subdir comes from [`shared/asset_sections.py`](../shared/asset_sections.py),
which is what keeps this command looking where ``list_assets`` reported from.

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
    "set_skin",
)

import os
import sys

import bpy

from ..log import get_logger
from ..shared import asset_sections
from ..shared import subject_resolution
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setskin")

# MPFB's five skin models, from the same enum its settings panel is built on.
SKIN_TYPES = ("MAKESKIN", "GAMEENGINE", "ENHANCED", "ENHANCED_SSS", "LAYERED")

# The three the UI refuses to instance materials for. The service guard names
# only LAYERED and GAMEENGINE; MAKESKIN is the panel's own decision, and since
# MAKESKIN is the default type it is the reason the default call instances
# nothing.
NO_MATERIAL_INSTANCES = ("LAYERED", "GAMEENGINE", "MAKESKIN")

# The two that build EnhancedSkinMaterial, and so the two that read a scale.
ENHANCED_TYPES = ("ENHANCED", "ENHANCED_SSS")

# The one type that can be applied with no MHMAT at all.
NEEDS_NO_FILE = "LAYERED"

ENHANCED_SETTINGS_FILE = "enhanced_settings.default.json"

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("path", TYPE_STRING, default=None, nullable=True,
          description="Absolute path to the MHMAT, as list_assets reports it."),
    Param("fragment", TYPE_STRING, default=None, nullable=True,
          description="The portable '<pack>/<file>.mhmat' fragment, resolved against this "
                      "Blender's 'skins' asset roots."),
    Param("skin_type", TYPE_STRING, default="MAKESKIN", choices=SKIN_TYPES,
          description="Which of MPFB's five node trees to build from the MHMAT. MAKESKIN is "
                      "MPFB's settings-panel default, not the function signature's."),
    Param("material_instances", TYPE_BOOLEAN, default=True,
          description="Create the per-region material slots. Forced off for LAYERED, GAMEENGINE "
                      "and MAKESKIN, as MPFB's own panel does - so the default call creates "
                      "none. Both values are reported."),
)

SUMMARY = "Give a character a skin, in one of MPFB's five material models."


def _module_level(services, service_name, attribute):
    """One name MPFB keeps on a service's module rather than on the service.

    ``material_source`` is a *human* property and ``scale_factor`` a general
    one, so the two config sets live on different modules. Both are read through
    the module of a service that has already resolved - never by importing an
    MPFB submodule.
    """
    module = sys.modules[services[service_name].__module__]
    return getattr(module, attribute, None)


def _property_value(config_set, property_name, blender_object):
    """One custom property, or ``None`` when it was never set.

    An unset string property reads back as "" rather than None, and "" means
    "nothing was recorded" - it must not be reported as a fragment.
    """
    if config_set is None or blender_object is None:
        return None
    try:
        value = config_set.get_value(property_name, entity_reference=blender_object)
    except Exception:  # pylint: disable=broad-except
        return None
    if not value:
        return None
    return str(value)


def _material_names(blender_object):
    """Every material name on an object, read off its slots.

    Read *before* the call, because ``delete_all_materials()`` is the first
    thing ``set_character_skin()`` does, and it takes the node groups with it.
    """
    names = []
    if blender_object is None:
        return names
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        if material is not None:
            names.append(str(material.name))
    return names


def _material_slot_records(blender_object):
    """The slots as they are now, which is how instancing differs observably."""
    if blender_object is None:
        return None
    slots = []
    index = 0
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        slots.append(dict(
            slot_index=int(getattr(slot, "slot_index", index)),
            material_name=None if material is None else str(material.name),
        ))
        index = index + 1
    return dict(
        object_name=blender_object.name,
        slots=slots,
        active_material_index=int(getattr(blender_object, "active_material_index", 0) or 0),
    )


def _activate_body_slot(blender_object):
    """MPFB's operator does this and the service does not.

    Without it the user's material properties panel is left looking at whichever
    slot happens to be index 0 - a fingernail material, on an instanced skin.
    The loop takes the *last* match rather than breaking on the first, exactly
    as ``loadlibraryskin.py`` does.
    """
    if blender_object is None:
        return None
    chosen = None
    index = 0
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        if material is not None and str(material.name).lower().endswith("body"):
            blender_object.active_material_index = int(getattr(slot, "slot_index", index))
            chosen = str(material.name)
        index = index + 1
    return chosen


def _scale_assumption_for(services, basemesh):
    """MPFB's own scale detection, reproduced only to be able to report it.

    ``set_character_skin()`` runs exactly these comparisons inside its enhanced
    branch and feeds the answer to the subsurface radii. Note where they fall on
    a real character: ``create_human()`` writes a ``scale_factor`` of 0.1, which
    is below the first threshold, so an ordinary character is treated as
    metre-scaled. The property's *declared* default of 1.0 would give
    ``DECIMETER`` and no character MPFB builds has it. Reported because a
    wrongly scaled character gets a subtly wrong skin and nothing else in the
    response would explain it.
    """
    general_properties = _module_level(services, "ObjectService", "GeneralObjectProperties")
    if general_properties is None or basemesh is None:
        return None
    try:
        scale_factor = general_properties.get_value("scale_factor", entity_reference=basemesh)
    except Exception:  # pylint: disable=broad-except
        return None
    if scale_factor is None:
        return None
    scale_name = "METER"
    if scale_factor > 0.9:
        scale_name = "DECIMETER"
    if scale_factor > 9:
        scale_name = "CENTIMETER"
    return scale_name


def _enhanced_settings_path(services):
    """Where MPFB would copy its default enhanced-skin settings to.

    Read before and after the call so ``settings_file_created`` is an
    observation rather than a guess about which branch ran.
    """
    try:
        return asset_sections.as_path(
            services["LocationService"].get_user_config(ENHANCED_SETTINGS_FILE))
    except Exception:  # pylint: disable=broad-except
        return None


class _Request:
    """One call's resolved arguments, so the refusals can be read in one place."""

    __slots__ = ("skin_type", "file_requested", "resolved_by", "resolved_path",
                 "asset_subdir", "sections_from_mpfb")


def _resolve_arguments(services, params):
    """The skin type, then the file. Nothing is touched yet."""
    request = _Request()
    request.skin_type = str(params["skin_type"]).strip().upper()
    request.file_requested = params["path"] is not None or params["fragment"] is not None
    request.resolved_by = None
    if params["path"] is not None:
        request.resolved_by = "path"
    elif params["fragment"] is not None:
        request.resolved_by = "fragment"

    # "Material" is the object_type MPFB's section table gives the skins
    # section, and asking that table is what keeps this command looking in the
    # same place list_assets reported from.
    sections, request.sections_from_mpfb = asset_sections.read_sections(services)
    request.asset_subdir = asset_sections.subdir_for_object_type(sections, "Material")

    request.resolved_path = None
    if params["path"] is not None:
        request.resolved_path = asset_sections.as_path(params["path"])
    elif params["fragment"] is not None and request.asset_subdir is not None:
        # find_asset_absolute_path() matches on *basename*, prefers a candidate
        # whose parent directory also matches, and otherwise returns the first
        # hit, so whatever it chooses is reported rather than assumed.
        try:
            request.resolved_path = asset_sections.as_path(
                services["AssetService"].find_asset_absolute_path(
                    params["fragment"], request.asset_subdir))
        except Exception:  # pylint: disable=broad-except
            request.resolved_path = None
    return request


def _blocked(subject, basemesh, subject_resolved_by, params, request, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=basemesh is not None,
        ready=False,
        applied=False,
        blocked_by=reason,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        bodyproxy_name=None,
        resolved_by=request.resolved_by,
        resolved_path=None,
        skin_type_used=None,
        material_instances_requested=params["material_instances"],
        material_instances_used=None,
        materials_destroyed=[],
        # Always present, on every refusal as well as on success: a caller that
        # got the vocabulary wrong should be able to correct itself from the
        # same response, and one that got something *else* wrong should not have
        # to guess whether the omission means anything.
        known_skin_types=list(SKIN_TYPES),
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _refusal(subject, basemesh, subject_resolved_by, params, request, message):
    """The first refusal that applies, or ``None``."""
    def blocked(reason, text, **extra):
        return _blocked(subject, basemesh, subject_resolved_by, params, request,
                        reason, text, **extra)

    if basemesh is None:
        return blocked("subject_not_found", message)
    if request.skin_type not in SKIN_TYPES:
        # Checked before anything is destroyed, which is the whole point: the
        # function this wraps deletes every material on the character and only
        # then looks at this value. The parameter contract also carries the
        # vocabulary, so this branch is reachable only through a spelling the
        # contract accepted and ``.upper()`` did not fix.
        return blocked(
            "unknown_skin_type",
            "'{!s}' is not a skin type MPFB knows, so nothing was changed. known_skin_types "
            "lists the five; they are five different node trees built from the same MHMAT. Note "
            "that MPFB's own function would have deleted this character's materials before "
            "discovering this, so the check happens here instead.".format(params["skin_type"]))
    if not request.file_requested and request.skin_type != NEEDS_NO_FILE:
        return blocked(
            "no_material_given",
            "skin_type '{:s}' builds its node tree from an MHMAT file, and neither path nor "
            "fragment was given, so nothing was changed. Call mpfb_list_assets for the 'skins' "
            "subdir and pass an entry's 'path' or 'fragment'. Only skin_type '{:s}' can build a "
            "material with no file at all.".format(request.skin_type, NEEDS_NO_FILE))
    if request.file_requested and (request.resolved_path is None
                                   or not os.path.isfile(request.resolved_path)):
        if params["path"] is not None:
            not_found_message = (
                "No file exists at '{!s}', so nothing was changed. Pass the 'path' "
                "mpfb_list_assets reports for an installed skin, or its 'fragment' to have this "
                "Blender's asset roots searched.".format(params["path"]))
        else:
            not_found_message = (
                "The fragment '{!s}' resolved to no file under this Blender's '{!s}' asset roots, "
                "so nothing was changed. The skin may not be installed here, or the fragment may "
                "name an asset of another kind - fragments are resolved per subdir, and a skin's "
                "is always 'skins'.".format(params["fragment"], request.asset_subdir))
        return blocked("skin_not_found", not_found_message,
                       asset_subdir=request.asset_subdir,
                       resolved_path=request.resolved_path,
                       section_table_from_mpfb=request.sections_from_mpfb)
    if basemesh.mode != "OBJECT" or bpy.context.mode != "OBJECT":
        # Two checks rather than one, the same lesson add_rig and add_asset
        # learned: creating the per-region material slots runs
        # bpy.ops.object.material_slot_assign() in edit mode, and bpy.ops polls
        # on the *context* mode.
        return blocked(
            "not_object_mode",
            "Blender is in {:s} mode and the basemesh '{:s}' is in {:s} mode. Building a skin's "
            "material slots runs operators that require OBJECT mode, so nothing was changed. "
            "Leave edit mode and call again.".format(
                str(bpy.context.mode), basemesh.name, str(basemesh.mode)))
    return None


def _message_for(request, params, basemesh, body_proxy, material_instances_used,
                 materials_destroyed, settings_file_created):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Applied a {:s} skin to '{:s}'".format(request.skin_type, basemesh.name)]
    if request.resolved_path is not None:
        parts.append(" from '{:s}'".format(os.path.basename(request.resolved_path)))
    parts.append(".")
    if body_proxy is not None:
        parts.append(" The body proxy '{:s}' was given it too.".format(body_proxy.name))
    if material_instances_used != params["material_instances"]:
        parts.append(
            " material_instances was requested as {:s} but used as {:s}: MPFB's skin library "
            "forces it off for {:s}, and this tool follows the panel rather than the function "
            "signature.".format(
                "true" if params["material_instances"] else "false",
                "true" if material_instances_used else "false",
                ", ".join(NO_MATERIAL_INSTANCES)))
    destroyed_count = sum(len(entry["materials"]) for entry in materials_destroyed)
    if destroyed_count:
        parts.append(" {:d} existing material(s) were deleted, node groups included; "
                     "materials_destroyed names them.".format(destroyed_count))
    if request.resolved_path is None:
        parts.append(" No MHMAT was given, so MPFB recorded no material_source and the previous "
                     "value is left in place.")
    if settings_file_created:
        parts.append(" {:s} was created in your MPFB user config directory; it did not exist "
                     "before this call.".format(ENHANCED_SETTINGS_FILE))
    return "".join(parts)


def set_skin(params, resolution):  # pylint: disable=too-many-locals,too-many-statements
    """Apply one skin, having checked the type and the file before anything is destroyed."""
    services = resolution.services
    object_service = services["ObjectService"]
    material_service = services["MaterialService"]
    HumanObjectProperties = _module_level(services, "HumanService", "HumanObjectProperties")

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, params["name"],
        not_done="no skin was applied",
        not_a_character="there is nothing to give a skin to, since a skin is a material on the body")
    request = _resolve_arguments(services, params)

    refused = _refusal(subject, basemesh, subject_resolved_by, params, request, message)
    if refused is not None:
        _LOG.debug("set_skin: refused %r", refused["blocked_by"])
        return refused

    # Resolved here rather than left to set_character_skin(), which would do it
    # itself when passed None: this command needs the same object for the
    # destroyed-material list and the slot fixup, and the response is the only
    # place a caller learns a second object was modified.
    body_proxy = object_service.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Proxymeshes")

    # MPFB's UI coercion, reproduced rather than the signature's default passed
    # through. See this module's docstring.
    material_instances_used = bool(
        params["material_instances"] and request.skin_type not in NO_MATERIAL_INSTANCES)

    # Everything below is observed *before* the call, which is what makes the
    # claims afterwards precise rather than reconstructed.
    materials_destroyed = [dict(object_name=basemesh.name, materials=_material_names(basemesh))]
    if body_proxy is not None:
        materials_destroyed.append(
            dict(object_name=body_proxy.name, materials=_material_names(body_proxy)))

    material_source_before = _property_value(HumanObjectProperties, "material_source", basemesh)

    settings_path = _enhanced_settings_path(services)
    settings_file_existed = bool(settings_path is not None and os.path.exists(settings_path))

    scale_assumption = None
    if request.skin_type in ENHANCED_TYPES:
        scale_assumption = _scale_assumption_for(services, basemesh)

    previous_active = bpy.context.view_layer.objects.active
    basemesh_was_selected = bool(basemesh.select_get())

    failure_message = None
    try:
        # MPFB's own operator runs with the character active, and the material
        # slot assignment goes through bpy.ops, which reads the context.
        object_service.activate_blender_object(basemesh)
        services["HumanService"].set_character_skin(
            request.resolved_path,
            basemesh,
            bodyproxy=body_proxy,
            skin_type=request.skin_type,
            material_instances=material_instances_used)
    except Exception as error:  # pylint: disable=broad-except
        # Broad on purpose. By the time anything in there can raise, the old
        # materials are already deleted - so a command_failed envelope would
        # leave the caller with a character stripped of materials and no record
        # of what was on it. This is reported as an answer instead, with
        # materials_destroyed intact.
        failure_message = "MPFB raised while building a {:s} skin: {:s}".format(
            request.skin_type, str(error))
    finally:
        if not basemesh_was_selected:
            basemesh.select_set(False)
        # Put back what was borrowed: the user is looking at this scene.
        bpy.context.view_layer.objects.active = previous_active

    if failure_message is not None:
        return _blocked(
            subject, basemesh, subject_resolved_by, params, request, "skin_failed",
            failure_message + (
                " The character's previous materials were already deleted when this happened and "
                "cannot be restored across the socket; materials_destroyed names them."),
            bodyproxy_name=None if body_proxy is None else body_proxy.name,
            resolved_path=request.resolved_path,
            skin_type_used=request.skin_type,
            material_instances_used=material_instances_used,
            materials_destroyed=materials_destroyed,
            material_slots=[record for record in
                            (_material_slot_records(basemesh),
                             _material_slot_records(body_proxy))
                            if record is not None])

    # The UI's fixup, after the load and before anything is read back.
    active_body_slot = dict(
        basemesh=_activate_body_slot(basemesh),
        bodyproxy=_activate_body_slot(body_proxy),
    )

    material_source = _property_value(HumanObjectProperties, "material_source", basemesh)
    settings_file_created = bool(
        settings_path is not None
        and not settings_file_existed
        and os.path.exists(settings_path))

    # Identified from the node tree that is now there rather than from the
    # argument: this is the one field that says the requested tree was actually
    # built. It is a heuristic of MPFB's own, not an authority.
    try:
        material_identified_as = material_service.identify_material(
            material_service.get_material(basemesh, 0))
    except Exception:  # pylint: disable=broad-except
        material_identified_as = None

    _LOG.debug("set_skin: applied %r to %r, instances=%r",
               request.skin_type, basemesh.name, material_instances_used)

    result = dict(
        found=True,
        ready=True,
        applied=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        bodyproxy_name=None if body_proxy is None else body_proxy.name,
        resolved_by=request.resolved_by,
        resolved_path=request.resolved_path,
        asset_subdir=request.asset_subdir,
        material_source=material_source,
        material_source_before=material_source_before,
        skin_type_used=request.skin_type,
        known_skin_types=list(SKIN_TYPES),
        material_instances_requested=params["material_instances"],
        material_instances_used=material_instances_used,
        materials_destroyed=materials_destroyed,
        material_slots=[record for record in
                        (_material_slot_records(basemesh), _material_slot_records(body_proxy))
                        if record is not None],
        material_identified_as=material_identified_as,
        active_body_slot=active_body_slot,
        settings_file_created=settings_file_created,
        settings_file_path=settings_path,
        scale_assumption=scale_assumption,
        message=_message_for(request, params, basemesh, body_proxy, material_instances_used,
                             materials_destroyed, settings_file_created),
    )

    # The verb is "applied". See shared/performed.py.
    return with_performed(result, result["applied"])
