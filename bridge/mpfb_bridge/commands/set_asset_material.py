"""
``set_asset_material``: swap an asset's material, MPFB's way.

**Nothing here calls a service function that does this job, because there is
none.** Alternative materials exist only in
``mpfb/ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py``, as two
module-level helpers, ``_apply_mhmat()`` and ``_find_default_material()``. Both
are reimplemented below from services - never imported.

**Being an add-on makes importing that module possible at all, and that is
exactly why this paragraph exists.** The rule in
[architecture.md](../../../specifications/architecture.md#a-ui-module-with-no-service-behind-it)
predates this add-on, from a time when nothing here *could* reach that module;
it is kept now that a command *could*, for the same two reasons it was written:
importing an MPFB
submodule runs MPFB code (several of them create directories on import), and a
UI operator module is the worst case of a name MPFB does not publish and is free
to move. This is the sharpest form of "where MPFB's own code paths disagree,
mpfb-mcp picks one and names it": here there is no service path to prefer, only
a panel's behaviour to reproduce.

Three of that operator's quirks are reproduced rather than tidied up, because
tidying any of them would make this command's result differ from what the user
sees after using the panel:

**It always builds a MakeSkin material, named literally ``makeskinmaterial``.**
Whatever the asset's current material was - MakeSkin, GameEngine, procedural
eyes - the replacement is a ``MakeSkinMaterial`` node tree under that one name.
It does not follow the object's own naming convention the way skins do
(``<basemesh>.body``), and it does not consult the material type the asset was
equipped with.

**It pops the slots rather than deleting the materials.** ``_apply_mhmat()``
runs ``obj.data.materials.pop(index=0)`` in a loop instead of calling
``MaterialService.delete_all_materials(..., also_destroy_groups=True)``, so the
previous material's node *groups* survive in the file. That is a real difference
from ``set_skin``, and ``materials_destroyed`` here means "removed from the
object", not "destroyed".

**The display colour is keyed on the object's ``object_type``**, through
``MaterialService.get_diffuse_colors()``, with ``(0.8, 0.8, 0.8, 1.0)`` when the
type is not in that table. So an asset mislabelled when it was equipped gets the
wrong viewport colour here too, which is why ``diffuse_color_from`` is reported.

**The asset subdir is ``str(object_type).lower()``**, which is what that
operator does and what ``get_object_info`` already does when it resolves an
``alternative_material`` back to a file. It is *not* ``asset_sections.py``'s
``subdir_for_object_type()``. The two agree for every type an MHCLO asset can
be, and the read and the write halves of one property agreeing matters more here
than authority does; the day they stop agreeing, this is the line to revisit.

**``Mhclo.load()`` is called with ``only_metadata=True``**, as that operator does
- the vertex tables are the bulk of an MHCLO and the ``material`` line is in the
header. Note what it yields: ``mhclo.material`` is an **absolute path**, joined
against the MHCLO's own directory, not a fragment. It can name a file that is
not there, which is the ``restore_default`` failure branch.

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
    "set_asset_material",
)

import os

import bpy

from ..log import get_logger
from ..shared import mpfb_surface
from ..shared import selection
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setassetmaterial")

# loadlibrarymaterial.py's own fallback when the object's type is not in
# MaterialService's colour table.
FALLBACK_DIFFUSE_COLOR = (0.8, 0.8, 0.8, 1.0)

MATERIAL_NAME = "makeskinmaterial"

_SKELETON_TYPES_FALLBACK = ("Skeleton", "Subrig")

PARAMS = (
    Param("name", TYPE_STRING, required=True,
          description="The asset object's own name, as list_objects reports it - not the "
                      "character's."),
    Param("path", TYPE_STRING, default=None, nullable=True,
          description="Absolute path to the MHMAT, as list_asset_materials reports it."),
    Param("fragment", TYPE_STRING, default=None, nullable=True,
          description="The portable fragment, resolved against the asset type's own subdir."),
    Param("restore_default", TYPE_BOOLEAN, default=False,
          description="Put back the material the asset's own MHCLO names, and clear the "
                      "recorded alternative_material - which is what MPFB's panel does."),
)

SUMMARY = "Apply an alternative material to an equipped asset, or restore its default."


def _refused_types(services):
    """The three MPFB's own alternative-material panel refuses.

    The first two have a skin rather than an asset material - that is
    ``set_skin``'s job - and the third is not a mesh at all.
    """
    skeleton_types = mpfb_surface.module_level(
        services, "ObjectService", "_SKELETON_TYPES", fallback=_SKELETON_TYPES_FALLBACK)
    return ("Basemesh", "Proxymeshes") + tuple(skeleton_types)


def _entities(services):
    """``MakeSkinMaterial`` and ``Mhclo``, or ``None`` each.

    Two entities rather than services, so neither is in the SERVICES dict. Both
    are imported by humanservice.py, which is why its module is where they are
    read from, and both are read with a fallback of None so a renamed entity
    degrades into a sentence rather than a traceback.
    """
    return (mpfb_surface.module_level(services, "HumanService", "MakeSkinMaterial", fallback=None),
            mpfb_surface.module_level(services, "HumanService", "Mhclo", fallback=None))


def _material_names(blender_object):
    names = []
    if blender_object is None:
        return names
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        if material is not None:
            names.append(str(material.name))
    return names


def _find_default_material(services, blender_object, asset_subdir):
    """``_find_default_material()``, reimplemented from services.

    Returns ``(path, reason)``: the absolute MHMAT the asset's own MHCLO names,
    or ``None`` with a reason naming which of the ways it failed - no
    ``asset_source`` recorded, the MHCLO itself not installed, or the MHCLO
    naming no material at all. One undifferentiated ``None`` would make several
    quite different situations look alike.
    """
    _makeskin, Mhclo = _entities(services)
    source = mpfb_surface.property_value(
        mpfb_surface.general_object_properties(services), "asset_source", blender_object)
    if not source:
        return (None, "asset_source_missing")
    try:
        mhclo_path = mpfb_surface.as_path(
            services["AssetService"].find_asset_absolute_path(source, asset_subdir))
    except Exception:  # pylint: disable=broad-except
        mhclo_path = None
    if not mhclo_path:
        return (None, "mhclo_not_installed")
    if Mhclo is None:
        return (None, "mhclo_entity_unavailable")
    try:
        mhclo = Mhclo()
        # only_metadata skips the vertex tables, which are the bulk of the file;
        # the material line is in the header. Same flag MPFB's operator uses.
        mhclo.load(mhclo_path, only_metadata=True)
    except Exception:  # pylint: disable=broad-except
        return (None, "mhclo_unreadable")
    material = getattr(mhclo, "material", None)
    if not material:
        return (None, "mhclo_names_no_material")
    return (mpfb_surface.as_path(material), None)


def _apply_mhmat(services, blender_object, mhmat_path):
    """``_apply_mhmat()``, reimplemented from services, quirks included.

    Returns ``(material_name, diffuse_color_from)``. See this module's docstring
    for why the slots are popped rather than deleted, why the result is always a
    MakeSkin material under one fixed name, and why the colour is keyed on the
    object's recorded type.
    """
    material_service = services["MaterialService"]
    MakeSkinMaterial, _mhclo = _entities(services)

    if material_service.has_materials(blender_object):
        # Popping rather than delete_all_materials(): the operator does it this
        # way, so the previous material's node groups stay in the file.
        while len(blender_object.data.materials) > 0:
            blender_object.data.materials.pop(index=0)

    material = material_service.create_empty_material(MATERIAL_NAME, blender_object)

    makeskin_material = MakeSkinMaterial()
    makeskin_material.populate_from_mhmat(mhmat_path)
    makeskin_material.apply_node_tree(material)

    object_type = str(
        services["ObjectService"].get_object_type(blender_object)).lower().capitalize()
    colors = material_service.get_diffuse_colors()
    color = FALLBACK_DIFFUSE_COLOR
    diffuse_color_from = None
    if object_type in colors:
        color = colors[object_type]
        diffuse_color_from = object_type
    material.diffuse_color = color

    return (str(material.name), diffuse_color_from)


class _Request:
    """One call's resolved arguments, so the refusals can be read in one place."""

    __slots__ = ("asset", "object_type", "asset_subdir", "previous_alternative_material",
                 "resolved_by", "resolved_path", "default_material_reason")


def _resolve_arguments(services, params):
    """The asset, its type, its subdir and the file. Nothing is touched yet."""
    request = _Request()
    restore_default = params["restore_default"]

    request.resolved_by = None
    if restore_default:
        request.resolved_by = "default"
    elif params["path"] is not None:
        request.resolved_by = "path"
    elif params["fragment"] is not None:
        request.resolved_by = "fragment"

    object_service = services["ObjectService"]
    request.asset = bpy.data.objects.get(params["name"])
    request.object_type = (None if request.asset is None
                           else (object_service.get_object_type(request.asset) or None))
    # MPFB's own derivation, in the operator this reimplements and in
    # get_object_info's read of the same property. See the docstring.
    request.asset_subdir = (None if request.object_type is None
                            else str(request.object_type).lower())
    request.previous_alternative_material = mpfb_surface.property_value(
        mpfb_surface.general_object_properties(services), "alternative_material", request.asset)

    request.resolved_path = None
    request.default_material_reason = None
    if (request.asset is not None and request.object_type is not None
            and request.object_type not in _refused_types(services)):
        if restore_default:
            request.resolved_path, request.default_material_reason = _find_default_material(
                services, request.asset, request.asset_subdir)
        elif params["path"] is not None:
            request.resolved_path = mpfb_surface.as_path(params["path"])
        elif request.asset_subdir is not None:
            try:
                request.resolved_path = mpfb_surface.as_path(
                    services["AssetService"].find_asset_absolute_path(
                        params["fragment"], request.asset_subdir))
            except Exception:  # pylint: disable=broad-except
                request.resolved_path = None
    return request


def _blocked(params, request, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    asset = request.asset
    answer = dict(
        found=asset is not None,
        ready=False,
        applied=False,
        blocked_by=reason,
        asset_object_name=None if asset is None else asset.name,
        object_type=request.object_type,
        asset_subdir=request.asset_subdir,
        resolved_by=request.resolved_by,
        resolved_path=None,
        alternative_material=request.previous_alternative_material,
        previous_alternative_material=request.previous_alternative_material,
        materials_destroyed=[],
        material_name=None,
        diffuse_color_from=None,
        restore_default=params["restore_default"],
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _default_reason_sentence(request):
    """Which of the four ways the default lookup failed, as a clause."""
    if request.default_material_reason == "mhclo_names_no_material":
        return "the asset's MHCLO names no material at all, so there is no default to restore"
    if request.default_material_reason == "mhclo_not_installed":
        return ("the MHCLO recorded as this asset's source is not installed under this Blender's "
                "'{!s}' asset roots, so the material it names cannot be read".format(
                    request.asset_subdir))
    if request.default_material_reason == "mhclo_entity_unavailable":
        return ("MPFB's Mhclo entity was not found on this install, so the asset's own MHCLO "
                "cannot be parsed")
    return "the asset's MHCLO could not be read"


def _refusal(services, params, request):  # pylint: disable=too-many-return-statements
    """The first refusal that applies, or ``None``. Eleven of them, in order."""
    asset = request.asset
    restore_default = params["restore_default"]
    MakeSkinMaterial, _mhclo = _entities(services)
    refused_types = _refused_types(services)

    def blocked(reason, text, **extra):
        return _blocked(params, request, reason, text, **extra)

    if asset is None:
        return blocked(
            "not_found",
            "No object named '{!s}' exists in this .blend file, so no material was changed. Call "
            "mpfb_list_objects to see what the current scene holds; this tool wants the asset's "
            "own name, not the character's.".format(params["name"]))
    if request.object_type is None:
        return blocked(
            "not_an_mpfb_object",
            "'{:s}' carries no MPFB object_type, so it is not an asset MPFB equipped and it has "
            "no default material to fall back to. Call mpfb_get_object_info to see what this "
            "object is.".format(asset.name))
    if request.object_type in refused_types:
        return blocked(
            "type_not_supported",
            "'{:s}' is of type {!s}, which MPFB's own alternative-material panel refuses along "
            "with {:s}. A basemesh and a body proxy carry a *skin* rather than an asset "
            "material - use mpfb_set_skin for those - and an armature carries no material at "
            "all.".format(asset.name, request.object_type, ", ".join(refused_types)),
            refused_types=list(refused_types))
    if MakeSkinMaterial is None:
        return blocked(
            "makeskin_unavailable",
            "MPFB's MakeSkinMaterial entity was not found on this install, so no material node "
            "tree can be built. Every alternative material is applied as a MakeSkin material, so "
            "there is no second path to fall back to. Call mpfb_get_status to check the install.")
    if restore_default and request.default_material_reason == "asset_source_missing":
        return blocked(
            "asset_source_missing",
            "'{:s}' records no asset_source, so the MHCLO it came from cannot be found and "
            "neither can the material that MHCLO names. Nothing was changed. This happens to an "
            "object whose property was cleared or which was not equipped through MPFB at "
            "all.".format(asset.name))
    if restore_default and request.resolved_path is None:
        return blocked(
            "default_material_not_found",
            "Nothing was changed: {:s}. Call mpfb_list_asset_materials for '{:s}' to see what it "
            "does know about.".format(_default_reason_sentence(request), asset.name),
            default_material_reason=request.default_material_reason)
    if not restore_default and (request.resolved_path is None
                                or not os.path.isfile(request.resolved_path)):
        if params["path"] is not None:
            not_found_message = (
                "No file exists at '{!s}', so no material was changed. Pass a 'path' from "
                "mpfb_list_asset_materials for this asset.".format(params["path"]))
        else:
            not_found_message = (
                "The fragment '{!s}' resolved to no file under this Blender's '{!s}' asset roots, "
                "so no material was changed. Alternative materials are resolved against the asset "
                "type's own subdir; call mpfb_list_asset_materials for '{:s}' to see which files "
                "it can use.".format(params["fragment"], request.asset_subdir, asset.name))
        return blocked("material_not_found", not_found_message,
                       resolved_path=request.resolved_path)
    if restore_default and not os.path.isfile(request.resolved_path):
        return blocked(
            "default_material_not_found",
            "The asset's MHCLO names the material '{!s}', but no file exists there, so nothing "
            "was changed. The asset's pack may be partially installed.".format(
                request.resolved_path),
            resolved_path=request.resolved_path,
            default_material_reason="file_missing")
    if asset.mode != "OBJECT" or bpy.context.mode != "OBJECT":
        return blocked(
            "not_object_mode",
            "Blender is in {:s} mode and '{:s}' is in {:s} mode. Building a material node tree "
            "requires OBJECT mode, so nothing was changed. Leave edit mode and call "
            "again.".format(str(bpy.context.mode), asset.name, str(asset.mode)))
    return None


def _message_for(params, request, materials_destroyed, material_name, diffuse_color_from):
    """What happened, said once, in the order a reader wants it."""
    parts = []
    if params["restore_default"]:
        parts.append(
            "Restored the material '{:s}' named by '{:s}'s own MHCLO, and cleared its recorded "
            "alternative_material.".format(
                os.path.basename(str(request.resolved_path)), request.asset.name))
    else:
        parts.append("Applied '{:s}' to '{:s}'.".format(
            os.path.basename(str(request.resolved_path)), request.asset.name))
    if materials_destroyed:
        parts.append(
            " {:d} material slot(s) were removed from the object first; MPFB pops the slots "
            "rather than destroying the materials, so any node groups they used are still in the "
            "file.".format(len(materials_destroyed)))
    parts.append(
        " The new material is a MakeSkin material named '{!s}', which is what MPFB's own panel "
        "builds whatever the asset had before.".format(material_name))
    if diffuse_color_from is None:
        parts.append(
            " The object type {!s} is not in MPFB's viewport colour table, so the neutral grey "
            "fallback was used.".format(request.object_type))
    return "".join(parts)


def set_asset_material(params, resolution):  # pylint: disable=too-many-locals
    """Apply one alternative material, or put the asset's own back."""
    services = resolution.services
    object_service = services["ObjectService"]
    general_properties = mpfb_surface.general_object_properties(services)

    request = _resolve_arguments(services, params)

    refused = _refusal(services, params, request)
    if refused is not None:
        _LOG.debug("set_asset_material: refused %r", refused["blocked_by"])
        return refused

    asset = request.asset
    # Read before the slots are popped: afterwards there is nothing left to name.
    materials_destroyed = _material_names(asset)

    failure_message = None
    material_name = None
    diffuse_color_from = None
    with selection.restored(asset):
        try:
            object_service.activate_blender_object(asset)
            material_name, diffuse_color_from = _apply_mhmat(
                services, asset, request.resolved_path)
        except Exception as error:  # pylint: disable=broad-except
            # Broad on purpose, for the same reason set_skin's is: the slots are
            # popped before the node tree is built, so a failure part-way through
            # leaves the object with no material and the caller needs to be told
            # which one it lost rather than handed a traceback.
            failure_message = "MPFB raised while building a material from '{:s}': {:s}".format(
                os.path.basename(str(request.resolved_path)), str(error))

    if failure_message is not None:
        return _blocked(
            params, request, "material_failed",
            failure_message + (
                " The asset's previous material was already removed from the object when this "
                "happened; materials_destroyed names it."),
            resolved_path=request.resolved_path,
            materials_destroyed=materials_destroyed)

    # The recorded fragment, written for an alternative and cleared for a
    # restore - exactly as the operator does, so get_object_info reads back what
    # MPFB's own panel would have left.
    recorded_fragment = ""
    if not params["restore_default"]:
        try:
            recorded_fragment = str(services["AssetService"].path_to_fragment(
                request.resolved_path, asset_subdir=request.asset_subdir))
        except Exception:  # pylint: disable=broad-except
            recorded_fragment = ""
    if general_properties is not None:
        try:
            general_properties.set_value(
                "alternative_material", recorded_fragment, entity_reference=asset)
        except Exception:  # pylint: disable=broad-except
            pass

    alternative_material = mpfb_surface.property_value(
        general_properties, "alternative_material", asset)

    _LOG.debug("set_asset_material: %r on %r, restore_default=%r",
               request.resolved_path, asset.name, params["restore_default"])

    result = dict(
        found=True,
        ready=True,
        applied=True,
        blocked_by=None,
        asset_object_name=asset.name,
        object_type=request.object_type,
        asset_subdir=request.asset_subdir,
        resolved_by=request.resolved_by,
        resolved_path=request.resolved_path,
        restore_default=params["restore_default"],
        alternative_material=alternative_material,
        previous_alternative_material=request.previous_alternative_material,
        materials_destroyed=materials_destroyed,
        material_name=material_name,
        diffuse_color_from=diffuse_color_from,
        message=_message_for(params, request, materials_destroyed, material_name,
                             diffuse_color_from),
    )

    # The verb is "applied". See shared/performed.py.
    return with_performed(result, result["applied"])
