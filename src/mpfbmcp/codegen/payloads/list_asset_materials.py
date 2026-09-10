"""
Payload for ``mpfb_list_asset_materials``: the alternatives beside one asset.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap, and used here to reach
  ``GeneralObjectProperties`` and the ``Mhclo`` entity, both of which MPFB keeps
  at module level rather than on a service.

**The scan is MPFB's.** ``AssetService.alternative_materials_for_asset()`` does
the work: it resolves the asset's own MHCLO, takes its parent directory name and
returns every ``*.mhmat`` under the asset type's roots whose path contains that
directory as a segment. What is here is the addressing around it - the two
identifiers each result needs, the default material it does *not* separate out,
and the search roots that make an empty answer explainable.

Three things about that function shape this payload.

**It caches, per ``(asset_source, asset_subdir)``, in a module-level dict that
nothing invalidates automatically.** So this tool reports a snapshot from the
first time anything in this Blender session asked about this asset, and a
material dropped into the directory afterwards is applicable and invisible.
Said out loud in the tool docstring, since a caller who meets it would otherwise
read it as a bug here.

FR 011 read that cache as having no invalidator at all, and FR 019 corrects it:
``AssetService.invalidate_alternative_materials_cache()`` exists and clears both
of MPFB's dicts. The staleness is real - nothing calls it - but it is the kind a
``refresh`` argument could lift, which is what FR 018 is for. Until that lands
this payload does not call the invalidator, and the answer is a snapshot.

**Its ``exclude_default`` argument is accepted and never used.** The asset's own
material is *not* filtered out of the result, so it normally appears in the list.
It is flagged with ``is_default`` rather than removed, because removing it would
be this tool inventing a behaviour MPFB does not have - and because "apply the
default" is what ``mpfb_set_asset_material``'s ``restore_default`` is for.

**The asset subdir is ``str(object_type).lower()``**, matching the operator
``mpfb_set_asset_material`` reimplements and matching what
``payloads/get_object_info.py`` already does when resolving an
``alternative_material`` back to a file - not ``asset_sections.py``'s section
table. The read and the write halves of one property have to agree about where a
fragment is looked up; that matters more here than authority does.

Reading the default material duplicates ``mpfb_set_asset_material``'s
``find_default_material()`` in outline. It is six lines and it is deliberately
not a shared fragment: the two answers are allowed to be phrased differently -
this one reports a reason string as data, that one turns the same reason into a
refusal - and neither predicts the other's behaviour, which is what
``specifications/architecture.md`` requires before a fragment is warranted.
"""

import os

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
HumanService = _MPFB_SERVICES["HumanService"]
AssetService = _MPFB_SERVICES["AssetService"]

OBJECTSERVICE_MODULE = sys.modules[ObjectService.__module__]
HUMANSERVICE_MODULE = sys.modules[HumanService.__module__]

GeneralObjectProperties = getattr(OBJECTSERVICE_MODULE, "GeneralObjectProperties", None)
Mhclo = getattr(HUMANSERVICE_MODULE, "Mhclo", None)


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


def default_material_for(asset_source, asset_subdir):
    """The absolute MHMAT the asset's own MHCLO names, or a reason it is unknown.

    Reported as data rather than as a refusal, which is the difference between
    this tool and ``mpfb_set_asset_material``: here "the MHCLO names no material"
    is a fact about the asset worth knowing, not a reason to do nothing.
    """
    if not asset_source:
        return (None, "asset_source_missing")
    try:
        mhclo_path = as_path(AssetService.find_asset_absolute_path(asset_source, asset_subdir))
    except Exception:  # pylint: disable=broad-except
        mhclo_path = None
    if not mhclo_path:
        return (None, "mhclo_not_installed")
    if Mhclo is None:
        return (None, "mhclo_entity_unavailable")
    try:
        mhclo = Mhclo()
        # only_metadata skips the vertex tables, which are the bulk of the file.
        mhclo.load(mhclo_path, only_metadata=True)
    except Exception:  # pylint: disable=broad-except
        return (None, "mhclo_unreadable")
    material = getattr(mhclo, "material", None)
    if not material:
        return (None, "mhclo_names_no_material")
    return (as_path(material), None)


def fragment_for(path, asset_subdir):
    """The portable identifier beside the passable one.

    Both are reported for every entry, per
    ``specifications/architecture.md``'s rule about naming things that can be
    added: ``path`` is what the acting tool takes today, ``fragment`` is what
    survives being written down and moved to another machine.
    """
    try:
        return str(AssetService.path_to_fragment(path, asset_subdir=asset_subdir))
    except Exception:  # pylint: disable=broad-except
        return None


def search_roots_for(asset_subdir):
    try:
        roots = AssetService.get_asset_roots(asset_subdir)
    except Exception:  # pylint: disable=broad-except
        return []
    return [as_path(root) for root in (roots or []) if as_path(root) is not None]


requested_name = PARAMS["name"]

asset = bpy.data.objects.get(requested_name)
object_type = None if asset is None else (ObjectService.get_object_type(asset) or None)
# MPFB's own derivation - see this module's docstring.
asset_subdir = None if object_type is None else str(object_type).lower()
asset_source = property_value(GeneralObjectProperties, "asset_source", asset)
current_alternative_material = property_value(
    GeneralObjectProperties, "alternative_material", asset)

if asset is None:
    result = dict(
        found=False,
        asset_object_name=None,
        object_type=None,
        asset_source=None,
        asset_subdir=None,
        default_material=None,
        default_material_reason=None,
        current_alternative_material=None,
        materials=[],
        count=0,
        search_roots=[],
        message=("No object named '" + str(requested_name) + "' exists in this .blend file. "
                 "Call mpfb_list_objects to see what the current scene holds; this tool wants "
                 "the asset's own name, not the character's."))
elif object_type is None:
    result = dict(
        found=True,
        asset_object_name=asset.name,
        object_type=None,
        asset_source=None,
        asset_subdir=None,
        default_material=None,
        default_material_reason=None,
        current_alternative_material=None,
        materials=[],
        count=0,
        search_roots=[],
        message=("'" + asset.name + "' carries no MPFB object_type, so it was not equipped by "
                 "MPFB and has no asset directory to look in. Call mpfb_get_object_info to see "
                 "what this object is."))
else:
    default_material, default_material_reason = default_material_for(asset_source, asset_subdir)

    materials = []
    scan_failed = False
    if asset_source:
        try:
            # MPFB's own scan, cached per (asset_source, asset_subdir). See the
            # docstring: nothing invalidates that cache, so this is a snapshot.
            found_paths = AssetService.alternative_materials_for_asset(
                asset_source, asset_subdir)
        except Exception:  # pylint: disable=broad-except
            found_paths = []
            scan_failed = True
        for found in found_paths or []:
            path = as_path(found)
            if path is None:
                continue
            materials.append(dict(
                path=path,
                fragment=fragment_for(path, asset_subdir),
                name=os.path.splitext(os.path.basename(path))[0],
                # MPFB does not filter the asset's own material out of this scan,
                # despite alternative_materials_for_asset() taking an
                # exclude_default argument it never reads. Flagged rather than
                # removed, so the list is MPFB's list.
                is_default=bool(
                    default_material is not None
                    and os.path.normcase(os.path.normpath(path))
                    == os.path.normcase(os.path.normpath(default_material))),
            ))
        materials.sort(key=lambda entry: entry["path"])

    search_roots = search_roots_for(asset_subdir)

    message_parts = []
    if not asset_source:
        message_parts.append(
            "'" + asset.name + "' records no asset_source, so there is no asset directory to "
            "scan for alternative materials. Nothing is claimed about whether any exist.")
    elif scan_failed:
        message_parts.append(
            "MPFB's alternative-material scan raised for asset_source '" + str(asset_source)
            + "', so no materials could be listed.")
    elif not materials:
        message_parts.append(
            "No alternative materials ship beside '" + str(asset_source) + "'. "
            + str(len(search_roots)) + " asset root(s) were searched; search_roots names them.")
    else:
        message_parts.append(
            str(len(materials)) + " material(s) ship beside '" + str(asset_source) + "'.")
    if materials:
        message_parts.append(
            " This list is a cached snapshot: MPFB caches it per asset and nothing invalidates "
            "that cache, so a material installed after the first call for this asset in this "
            "Blender session will not appear.")
    if default_material is None and asset_source:
        message_parts.append(
            " The asset's own default material is not known ("
            + str(default_material_reason) + "), so no entry is flagged as the default and "
            "mpfb_set_asset_material's restore_default would refuse.")

    result = dict(
        found=True,
        asset_object_name=asset.name,
        object_type=object_type,
        asset_source=asset_source,
        asset_subdir=asset_subdir,
        default_material=(
            None if default_material is None
            else dict(path=default_material,
                      fragment=fragment_for(default_material, asset_subdir),
                      exists=os.path.isfile(default_material))),
        default_material_reason=default_material_reason,
        current_alternative_material=current_alternative_material,
        materials=materials,
        count=len(materials),
        search_roots=search_roots,
        message="".join(message_parts),
    )
