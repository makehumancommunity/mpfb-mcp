"""
Payload for ``mpfb_set_asset_material``: swap an asset's material, MPFB's way.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag four names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, ``path``,
  ``fragment`` and ``restore_default``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap, and used here to reach
  ``GeneralObjectProperties``, the object-type vocabulary, and the two
  *entities* MPFB keeps at module level: ``MakeSkinMaterial`` and ``Mhclo``.
- ``with_performed()`` - from the shared fragment ``performed.py``, named by
  every mutating payload. It stamps the uniform ``performed`` flag onto the
  finished answer, in the last line of this file.

**Nothing here calls a service function that does this job, because there is
none.** Alternative materials exist only in
``mpfb/ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py``, as two
module-level helpers, ``_apply_mhmat()`` and ``_find_default_material()``. Both
are reimplemented below from services - never imported, per
``specifications/architecture.md``'s rule about MPFB submodules, of which a UI
operator module is the worst case. This is the sharpest form of
"where MPFB's own code paths disagree, mpfb-mcp picks one and names it": here
there is no service path to prefer, only a panel's behaviour to reproduce.

Three of that operator's quirks are reproduced rather than tidied up, because
tidying any of them would make this tool's result differ from what the user sees
after using the panel:

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
from ``mpfb_set_skin``, and ``materials_destroyed`` here means "removed from the
object", not "destroyed".

**The display colour is keyed on the object's ``object_type``**, through
``MaterialService.get_diffuse_colors()``, with ``(0.8, 0.8, 0.8, 1.0)`` when the
type is not in that table. So an asset mislabelled when it was equipped gets the
wrong viewport colour here too, which is why ``diffuse_color_from`` is reported.

**The asset subdir is ``str(object_type).lower()``**, which is what that
operator does and what ``payloads/get_object_info.py`` already does when it
resolves an ``alternative_material`` back to a file. It is *not*
``asset_sections.py``'s ``subdir_for_object_type()``. The two agree for every
type an MHCLO asset can be, and the read and the write halves of one property
agreeing matters more here than authority does; the day they stop agreeing, this
is the line to revisit.

**``Mhclo.load()`` is called with ``only_metadata=True``**, as that operator does
- the vertex tables are the bulk of an MHCLO and the ``material`` line is in the
header. Note what it yields: ``mhclo.material`` is an **absolute path**, joined
against the MHCLO's own directory, not a fragment. It can name a file that is not
there, which is the ``restore_default`` failure branch.
"""

import os

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
HumanService = _MPFB_SERVICES["HumanService"]
MaterialService = _MPFB_SERVICES["MaterialService"]
AssetService = _MPFB_SERVICES["AssetService"]

OBJECTSERVICE_MODULE = sys.modules[ObjectService.__module__]
HUMANSERVICE_MODULE = sys.modules[HumanService.__module__]

GeneralObjectProperties = getattr(OBJECTSERVICE_MODULE, "GeneralObjectProperties", None)
SKELETON_TYPES = getattr(OBJECTSERVICE_MODULE, "_SKELETON_TYPES", ("Skeleton", "Subrig"))

# Two entities rather than services, so neither is in the SERVICES dict. Both
# are imported by humanservice.py, which is why its module is where they are
# read from, and both are read with a fallback of None so a renamed entity
# degrades into a sentence rather than a traceback.
MakeSkinMaterial = getattr(HUMANSERVICE_MODULE, "MakeSkinMaterial", None)
Mhclo = getattr(HUMANSERVICE_MODULE, "Mhclo", None)

# The three MPFB's own alternative-material panel refuses. The first two have a
# skin rather than an asset material - that is mpfb_set_skin's job - and the
# third is not a mesh at all.
REFUSED_TYPES = ("Basemesh", "Proxymeshes") + tuple(SKELETON_TYPES)

# loadlibrarymaterial.py's own fallback when the object's type is not in
# MaterialService's colour table.
FALLBACK_DIFFUSE_COLOR = (0.8, 0.8, 0.8, 1.0)

MATERIAL_NAME = "makeskinmaterial"


def as_path(path):
    """Coerce at the point a path enters the response.

    Several AssetService helpers hand back pathlib.Path, and one of those in the
    response fails strict_json and takes the whole answer down with it.
    """
    if not path:
        return None
    return str(path)


def property_value(config_set, property_name, blender_object):
    """One custom property, or None when it was never set (it reads back as "")."""
    if config_set is None or blender_object is None:
        return None
    try:
        value = config_set.get_value(property_name, entity_reference=blender_object)
    except Exception:  # pylint: disable=broad-except
        return None
    if not value:
        return None
    return str(value)


def material_names(blender_object):
    names = []
    if blender_object is None:
        return names
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        if material is not None:
            names.append(str(material.name))
    return names


def find_default_material(blender_object, asset_subdir):
    """``_find_default_material()``, reimplemented from services.

    Returns (path, reason): the absolute MHMAT the asset's own MHCLO names, or
    None with a reason naming which of the three ways it failed - no
    ``asset_source`` recorded, the MHCLO itself not installed, or the MHCLO
    naming no material at all. One undifferentiated None would make three quite
    different situations look alike.
    """
    source = property_value(GeneralObjectProperties, "asset_source", blender_object)
    if not source:
        return (None, "asset_source_missing")
    try:
        mhclo_path = as_path(AssetService.find_asset_absolute_path(source, asset_subdir))
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
    return (as_path(material), None)


def apply_mhmat(blender_object, mhmat_path):
    """``_apply_mhmat()``, reimplemented from services, quirks included.

    Returns (material_name, diffuse_color_from). See this module's docstring for
    why the slots are popped rather than deleted, why the result is always a
    MakeSkin material under one fixed name, and why the colour is keyed on the
    object's recorded type.
    """
    if MaterialService.has_materials(blender_object):
        # Popping rather than delete_all_materials(): the operator does it this
        # way, so the previous material's node groups stay in the file.
        while len(blender_object.data.materials) > 0:
            blender_object.data.materials.pop(index=0)

    material = MaterialService.create_empty_material(MATERIAL_NAME, blender_object)

    makeskin_material = MakeSkinMaterial()
    makeskin_material.populate_from_mhmat(mhmat_path)
    makeskin_material.apply_node_tree(material)

    object_type = str(ObjectService.get_object_type(blender_object)).lower().capitalize()
    colors = MaterialService.get_diffuse_colors()
    color = FALLBACK_DIFFUSE_COLOR
    diffuse_color_from = None
    if object_type in colors:
        color = colors[object_type]
        diffuse_color_from = object_type
    material.diffuse_color = color

    return (str(material.name), diffuse_color_from)


def blocked(asset, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=asset is not None,
        ready=False,
        applied=False,
        blocked_by=reason,
        asset_object_name=None if asset is None else asset.name,
        object_type=object_type,
        asset_subdir=asset_subdir,
        resolved_by=resolved_by,
        resolved_path=None,
        alternative_material=previous_alternative_material,
        previous_alternative_material=previous_alternative_material,
        materials_destroyed=[],
        material_name=None,
        diffuse_color_from=None,
        restore_default=restore_default,
        message=message,
    )
    answer.update(extra)
    return answer


requested_name = PARAMS["name"]
requested_path = PARAMS["path"]
requested_fragment = PARAMS["fragment"]
restore_default = PARAMS["restore_default"]

resolved_by = None
if restore_default:
    resolved_by = "default"
elif requested_path is not None:
    resolved_by = "path"
elif requested_fragment is not None:
    resolved_by = "fragment"

asset = bpy.data.objects.get(requested_name)
object_type = None if asset is None else (ObjectService.get_object_type(asset) or None)
# MPFB's own derivation, in the operator this reimplements and in
# payloads/get_object_info.py's read of the same property. See the docstring.
asset_subdir = None if object_type is None else str(object_type).lower()
previous_alternative_material = property_value(
    GeneralObjectProperties, "alternative_material", asset)

resolved_path = None
default_material_reason = None
if asset is not None and object_type is not None and object_type not in REFUSED_TYPES:
    if restore_default:
        resolved_path, default_material_reason = find_default_material(asset, asset_subdir)
    elif requested_path is not None:
        resolved_path = as_path(requested_path)
    elif asset_subdir is not None:
        try:
            resolved_path = as_path(
                AssetService.find_asset_absolute_path(requested_fragment, asset_subdir))
        except Exception:  # pylint: disable=broad-except
            resolved_path = None

if asset is None:
    result = blocked(
        None, "not_found",
        ("No object named '" + str(requested_name) + "' exists in this .blend file, so no "
         "material was changed. Call mpfb_list_objects to see what the current scene holds; "
         "this tool wants the asset's own name, not the character's."))
elif object_type is None:
    result = blocked(
        asset, "not_an_mpfb_object",
        ("'" + asset.name + "' carries no MPFB object_type, so it is not an asset MPFB equipped "
         "and it has no default material to fall back to. Call mpfb_get_object_info to see what "
         "this object is."))
elif object_type in REFUSED_TYPES:
    result = blocked(
        asset, "type_not_supported",
        ("'" + asset.name + "' is of type " + str(object_type) + ", which MPFB's own "
         "alternative-material panel refuses along with " + ", ".join(REFUSED_TYPES) + ". A "
         "basemesh and a body proxy carry a *skin* rather than an asset material - use "
         "mpfb_set_skin for those - and an armature carries no material at all."),
        refused_types=list(REFUSED_TYPES))
elif MakeSkinMaterial is None:
    result = blocked(
        asset, "makeskin_unavailable",
        ("MPFB's MakeSkinMaterial entity was not found on this install, so no material node tree "
         "can be built. Every alternative material is applied as a MakeSkin material, so there "
         "is no second path to fall back to. Call mpfb_get_status to check the install."))
elif restore_default and default_material_reason == "asset_source_missing":
    result = blocked(
        asset, "asset_source_missing",
        ("'" + asset.name + "' records no asset_source, so the MHCLO it came from cannot be "
         "found and neither can the material that MHCLO names. Nothing was changed. This "
         "happens to an object whose property was cleared or which was not equipped through "
         "MPFB at all."))
elif restore_default and resolved_path is None:
    if default_material_reason == "mhclo_names_no_material":
        reason_sentence = (
            "the asset's MHCLO names no material at all, so there is no default to restore")
    elif default_material_reason == "mhclo_not_installed":
        reason_sentence = (
            "the MHCLO recorded as this asset's source is not installed under this Blender's '"
            + str(asset_subdir) + "' asset roots, so the material it names cannot be read")
    elif default_material_reason == "mhclo_entity_unavailable":
        reason_sentence = (
            "MPFB's Mhclo entity was not found on this install, so the asset's own MHCLO cannot "
            "be parsed")
    else:
        reason_sentence = "the asset's MHCLO could not be read"
    result = blocked(
        asset, "default_material_not_found",
        ("Nothing was changed: " + reason_sentence + ". Call mpfb_list_asset_materials for '"
         + asset.name + "' to see what it does know about."),
        default_material_reason=default_material_reason)
elif not restore_default and (resolved_path is None or not os.path.isfile(resolved_path)):
    if requested_path is not None:
        not_found_message = (
            "No file exists at '" + str(requested_path) + "', so no material was changed. Pass "
            "a 'path' from mpfb_list_asset_materials for this asset.")
    else:
        not_found_message = (
            "The fragment '" + str(requested_fragment) + "' resolved to no file under this "
            "Blender's '" + str(asset_subdir) + "' asset roots, so no material was changed. "
            "Alternative materials are resolved against the asset type's own subdir; call "
            "mpfb_list_asset_materials for '" + asset.name + "' to see which files it can use.")
    result = blocked(asset, "material_not_found", not_found_message,
                     resolved_path=resolved_path)
elif restore_default and not os.path.isfile(resolved_path):
    result = blocked(
        asset, "default_material_not_found",
        ("The asset's MHCLO names the material '" + str(resolved_path) + "', but no file exists "
         "there, so nothing was changed. The asset's pack may be partially installed."),
        resolved_path=resolved_path,
        default_material_reason="file_missing")
elif asset.mode != "OBJECT" or bpy.context.mode != "OBJECT":
    result = blocked(
        asset, "not_object_mode",
        ("Blender is in " + str(bpy.context.mode) + " mode and '" + asset.name + "' is in "
         + str(asset.mode) + " mode. Building a material node tree requires OBJECT mode, so "
         "nothing was changed. Leave edit mode and call again."))
else:
    # Read before the slots are popped: afterwards there is nothing left to name.
    materials_destroyed = material_names(asset)

    previous_active = bpy.context.view_layer.objects.active
    asset_was_selected = bool(asset.select_get())

    failure_message = None
    material_name = None
    diffuse_color_from = None
    try:
        ObjectService.activate_blender_object(asset)
        material_name, diffuse_color_from = apply_mhmat(asset, resolved_path)
    except Exception as error:  # pylint: disable=broad-except
        # Broad on purpose, for the same reason mpfb_set_skin's is: the slots
        # are popped before the node tree is built, so a failure part-way
        # through leaves the object with no material and the caller needs to be
        # told which one it lost rather than handed a traceback.
        failure_message = (
            "MPFB raised while building a material from '"
            + os.path.basename(str(resolved_path)) + "': " + str(error))
    finally:
        if not asset_was_selected:
            asset.select_set(False)
        # Put back what was borrowed: the user is looking at this scene.
        bpy.context.view_layer.objects.active = previous_active

    if failure_message is not None:
        result = blocked(
            asset, "material_failed",
            failure_message + (
                " The asset's previous material was already removed from the object when this "
                "happened; materials_destroyed names it."),
            resolved_path=resolved_path,
            materials_destroyed=materials_destroyed)
    else:
        # The recorded fragment, written for an alternative and cleared for a
        # restore - exactly as the operator does, so mpfb_get_object_info reads
        # back what MPFB's own panel would have left.
        recorded_fragment = ""
        if not restore_default:
            try:
                recorded_fragment = str(AssetService.path_to_fragment(
                    resolved_path, asset_subdir=asset_subdir))
            except Exception:  # pylint: disable=broad-except
                recorded_fragment = ""
        if GeneralObjectProperties is not None:
            try:
                GeneralObjectProperties.set_value(
                    "alternative_material", recorded_fragment, entity_reference=asset)
            except Exception:  # pylint: disable=broad-except
                pass

        alternative_material = property_value(
            GeneralObjectProperties, "alternative_material", asset)

        message_parts = []
        if restore_default:
            message_parts.append(
                "Restored the material '" + os.path.basename(str(resolved_path)) + "' named by '"
                + asset.name + "'s own MHCLO, and cleared its recorded alternative_material.")
        else:
            message_parts.append(
                "Applied '" + os.path.basename(str(resolved_path)) + "' to '" + asset.name
                + "'.")
        if materials_destroyed:
            message_parts.append(
                " " + str(len(materials_destroyed)) + " material slot(s) were removed from the "
                "object first; MPFB pops the slots rather than destroying the materials, so any "
                "node groups they used are still in the file.")
        message_parts.append(
            " The new material is a MakeSkin material named '" + str(material_name)
            + "', which is what MPFB's own panel builds whatever the asset had before.")
        if diffuse_color_from is None:
            message_parts.append(
                " The object type " + str(object_type) + " is not in MPFB's viewport colour "
                "table, so the neutral grey fallback was used.")

        result = dict(
            found=True,
            ready=True,
            applied=True,
            blocked_by=None,
            asset_object_name=asset.name,
            object_type=object_type,
            asset_subdir=asset_subdir,
            resolved_by=resolved_by,
            resolved_path=resolved_path,
            restore_default=restore_default,
            alternative_material=alternative_material,
            previous_alternative_material=previous_alternative_material,
            materials_destroyed=materials_destroyed,
            material_name=material_name,
            diffuse_color_from=diffuse_color_from,
            message="".join(message_parts),
        )


# The verb is "applied". See codegen/shared/performed.py.
result = with_performed(result, result.get("applied", False))
