"""
``list_asset_materials``: the alternative materials shipped beside one asset.

**The scan is MPFB's.** ``AssetService.alternative_materials_for_asset()`` does
the work: it resolves the asset's own MHCLO, takes its parent directory name and
returns every ``*.mhmat`` under the asset type's roots whose path contains that
directory as a segment. What is here is the addressing around it - the two
identifiers each result needs, the default material it does *not* separate out,
and the search roots that make an empty answer explainable.

**This is not an asset library section**, which is why ``list_assets`` cannot
name it and why this command exists at all: the materials beside a hat live in
the hat's own directory, not in a subdir MPFB catalogues.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration. Three of MPFB's behaviours shape it and all three look wrong:

- **The answer is stale by design, and FR 018 is what lifts it.** That
  function caches per ``(asset_source, asset_subdir)`` in a module-level dict
  that nothing invalidates automatically, so a plain call reports a snapshot
  from the first time anything in this Blender session asked about this
  asset. ``refresh=True`` calls
  ``AssetService.invalidate_alternative_materials_cache()`` before scanning,
  which clears **both** caching dicts - and every other asset's cached
  entry along with this one's, since the invalidator takes no arguments and
  there is no per-asset variant. ``cache_invalidated`` says whether this call
  did that, and the message says so too when it did not, since a caller who
  met the staleness would otherwise read it as a bug here. Since FR 046 it
  also clears MPFB's **pack metadata** cache, which the license on every entry
  is read from: without that, a pack installed since Blender started would
  show its materials as attributed to nothing until ``list_assets`` happened to
  be refreshed. That rescan rereads about a hundred small JSON files.
- **``exclude_default`` is accepted by MPFB and never used.** The asset's own
  material is not filtered out, so it normally appears in the list. It is
  flagged with ``is_default`` rather than removed, because removing it would be
  this command inventing a behaviour MPFB does not have.
- **The asset subdir is ``str(object_type).lower()``**, matching the operator
  ``set_asset_material`` reimplements and matching what ``get_object_info``
  already does when resolving an ``alternative_material`` back to a file - and
  **not** [`shared/asset_sections.py`](../shared/asset_sections.py)'s section
  table. The read and the write halves of one property have to agree about
  where a fragment is looked up; that matters more here than authority does,
  which is why this is the one catalogue command in this batch that does not
  use the shared table.

**Every entry, and the default material, carries ``list_assets``' attribution**
- ``license``, ``author``, ``source_url`` and ``packs`` - from
[`shared/pack_attribution.py`](../shared/pack_attribution.py), judged against
``search_roots``, so the two catalogues cannot disagree about one file
([FR 046](../../../feature-requests/done/046-license-in-the-catalogues/README.md)).
Alternative materials are the half a hand-made join against ``list_assets``
could never reach. A material in its asset's own directory takes the asset's
attribution, and one in a directory of its own (``system_hair_materials01``)
takes that directory's.

Reading the default material duplicates ``set_asset_material``'s
``find_default_material()`` in outline. It is six lines and it is deliberately
not a shared module: the two answers are allowed to be phrased differently -
this one reports a reason string as data, that one turns the same reason into a
refusal - and neither predicts the other's behaviour, which is what
[architecture.md](../../../specifications/architecture.md#shared-modules-and-what-warrants-one)
requires before sharing is warranted.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_asset_materials",
)

import os

import bpy

from ..log import get_logger
from ..shared import mpfb_surface
from ..shared import pack_attribution
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.listassetmaterials")

PARAMS = (
    Param("name", TYPE_STRING, required=True,
          description="The name of the equipped asset object - the hat, not the character."),
    Param("refresh", TYPE_BOOLEAN, default=False,
          description="Clear AssetService's alternative-materials and pack-metadata caches "
                      "before scanning. MPFB caches both and nothing invalidates them "
                      "automatically; the clear is global, affecting every asset, not only "
                      "this one."),
)

SUMMARY = "List the alternative materials that ship beside one equipped asset."


def _mpfb_entities(services):
    """``GeneralObjectProperties`` and ``Mhclo``, which are module-level in MPFB.

    Both are reached through the module of a service that already imported them
    - never by importing an MPFB submodule, several of which create directories
    on import - and both are read with a fallback of ``None``.
    """
    return (mpfb_surface.general_object_properties(services),
            mpfb_surface.module_level(services, "HumanService", "Mhclo", fallback=None))


def _default_material_for(services, mhclo_entity, asset_source, asset_subdir):
    """The absolute MHMAT the asset's own MHCLO names, or a reason it is unknown.

    Reported as data rather than as a refusal, which is the difference between
    this command and ``set_asset_material``: here "the MHCLO names no material"
    is a fact about the asset worth knowing, not a reason to do nothing.
    """
    if not asset_source:
        return (None, "asset_source_missing")
    try:
        mhclo_path = mpfb_surface.as_path(
            services["AssetService"].find_asset_absolute_path(asset_source, asset_subdir))
    except Exception:  # pylint: disable=broad-except
        mhclo_path = None
    if not mhclo_path:
        return (None, "mhclo_not_installed")
    if mhclo_entity is None:
        return (None, "mhclo_entity_unavailable")
    try:
        mhclo = mhclo_entity()
        # only_metadata skips the vertex tables, which are the bulk of the file.
        mhclo.load(mhclo_path, only_metadata=True)
    except Exception:  # pylint: disable=broad-except
        return (None, "mhclo_unreadable")
    material = getattr(mhclo, "material", None)
    if not material:
        return (None, "mhclo_names_no_material")
    return (mpfb_surface.as_path(material), None)


def _fragment_for(services, path, asset_subdir):
    """The portable identifier beside the passable one.

    Both are reported for every entry: ``path`` is what the acting command takes
    today, ``fragment`` is what survives being written down and moved to another
    machine.
    """
    try:
        return str(services["AssetService"].path_to_fragment(path, asset_subdir=asset_subdir))
    except Exception:  # pylint: disable=broad-except
        return None


def _attribution(index, path, search_roots, conflicts):
    """The attribution fields one material entry carries, as list_assets reports them.

    A disagreement between claimants is appended to ``conflicts`` rather than
    carried on the entry, as ``list_assets`` reports it.
    """
    attribution = pack_attribution.attribute(index, path, search_roots)
    # The default material is usually in the list as well; report it once.
    if attribution["claims_disagree"] and all(entry["path"] != path for entry in conflicts):
        conflicts.append(dict(path=path, claims=attribution["claims"]))
    return {key: attribution[key] for key in pack_attribution.FIELDS}


def _search_roots_for(services, asset_subdir):
    try:
        roots = services["AssetService"].get_asset_roots(asset_subdir)
    except Exception:  # pylint: disable=broad-except
        return []
    return [mpfb_surface.as_path(root) for root in (roots or [])
            if mpfb_surface.as_path(root) is not None]


def _not_found(requested_name, cache_invalidated):
    return dict(
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
        attribution_conflicts=[],
        cache_invalidated=cache_invalidated,
        message="No object named '{:s}' exists in this .blend file. Call mpfb_list_objects to "
                "see what the current scene holds; this tool wants the asset's own name, not "
                "the character's.".format(str(requested_name)))


def _not_an_asset(asset, cache_invalidated):
    return dict(
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
        attribution_conflicts=[],
        cache_invalidated=cache_invalidated,
        message="'{:s}' carries no MPFB object_type, so it was not equipped by MPFB and has no "
                "asset directory to look in. Call mpfb_get_object_info to see what this object "
                "is.".format(asset.name))


def _message(asset, asset_source, scan_failed, materials, search_roots,
             default_material, default_material_reason, cache_invalidated):
    parts = []
    if not asset_source:
        parts.append(
            "'{:s}' records no asset_source, so there is no asset directory to scan for "
            "alternative materials. Nothing is claimed about whether any exist.".format(
                asset.name))
    elif scan_failed:
        parts.append(
            "MPFB's alternative-material scan raised for asset_source '{:s}', so no materials "
            "could be listed.".format(str(asset_source)))
    elif not materials:
        parts.append(
            "No alternative materials ship beside '{:s}'. {:d} asset root(s) were searched; "
            "search_roots names them.".format(str(asset_source), len(search_roots)))
    else:
        parts.append("{:d} material(s) ship beside '{:s}'.".format(
            len(materials), str(asset_source)))
    if cache_invalidated:
        parts.append(
            " The alternative-materials and pack-metadata caches were cleared before this scan "
            "(refresh=True), so this list and its licenses reflect the current files. That "
            "clear is global - it also affects the next call for every other asset, not only "
            "this one.")
    elif materials:
        parts.append(
            " This list is a cached snapshot: MPFB caches it per asset and nothing invalidates "
            "that cache, so a material installed after the first call for this asset in this "
            "Blender session will not appear. Pass refresh=True to clear the cache first.")
    if materials:
        parts.append(" 'license' is derived from the directory a material sits in, not "
                     "recorded; a material in its asset's own directory takes the asset's.")
    if default_material is None and asset_source:
        parts.append(
            " The asset's own default material is not known ({:s}), so no entry is flagged as "
            "the default and mpfb_set_asset_material's restore_default would refuse.".format(
                str(default_material_reason)))
    return "".join(parts)


def list_asset_materials(params, resolution):
    """Name the materials beside one equipped asset, and which of them is its own."""
    services = resolution.services
    general_properties, mhclo_entity = _mpfb_entities(services)
    requested_name = params["name"]
    cache_invalidated = bool(params["refresh"])

    if cache_invalidated:
        # Global: this clears every asset's cached scan, not only the one
        # named here. There is no per-asset invalidator to reach for instead.
        # The pack metadata goes with it, or a pack installed since Blender
        # started would show its materials as attributed to nothing.
        services["AssetService"].invalidate_alternative_materials_cache()
        services["AssetService"].invalidate_pack_metadata_cache()

    asset = bpy.data.objects.get(requested_name)
    if asset is None:
        return _not_found(requested_name, cache_invalidated)

    object_type = services["ObjectService"].get_object_type(asset) or None
    if object_type is None:
        return _not_an_asset(asset, cache_invalidated)

    # MPFB's own derivation - see this module's docstring for why it is this and
    # not the shared section table.
    asset_subdir = str(object_type).lower()
    asset_source = mpfb_surface.property_value(general_properties, "asset_source", asset)
    current_alternative_material = mpfb_surface.property_value(
        general_properties, "alternative_material", asset)

    default_material, default_material_reason = _default_material_for(
        services, mhclo_entity, asset_source, asset_subdir)
    search_roots = _search_roots_for(services, asset_subdir)
    # Once for the call, and before anything is attributed.
    index = pack_attribution.read_index(services)
    conflicts = []

    materials = []
    scan_failed = False
    if asset_source:
        try:
            # MPFB's own scan, cached per (asset_source, asset_subdir). See the
            # docstring: nothing invalidates that cache, so this is a snapshot.
            found_paths = services["AssetService"].alternative_materials_for_asset(
                asset_source, asset_subdir)
        except Exception:  # pylint: disable=broad-except
            found_paths = []
            scan_failed = True
        for found in found_paths or []:
            path = mpfb_surface.as_path(found)
            if path is None:
                continue
            materials.append(dict(
                path=path,
                fragment=_fragment_for(services, path, asset_subdir),
                name=os.path.splitext(os.path.basename(path))[0],
                **_attribution(index, path, search_roots, conflicts),
                # MPFB does not filter the asset's own material out of this
                # scan, despite alternative_materials_for_asset() taking an
                # exclude_default argument it never reads. Flagged rather than
                # removed, so the list is MPFB's list.
                is_default=bool(
                    default_material is not None
                    and os.path.normcase(os.path.normpath(path))
                    == os.path.normcase(os.path.normpath(default_material))),
            ))
        materials.sort(key=lambda entry: entry["path"])

    _LOG.debug("list_asset_materials: %d beside %r in %r",
               len(materials), asset_source, asset_subdir)

    return dict(
        found=True,
        asset_object_name=asset.name,
        object_type=object_type,
        asset_source=asset_source,
        asset_subdir=asset_subdir,
        default_material=(
            None if default_material is None
            else dict(path=default_material,
                      fragment=_fragment_for(services, default_material, asset_subdir),
                      exists=os.path.isfile(default_material),
                      **_attribution(index, default_material, search_roots, conflicts))),
        default_material_reason=default_material_reason,
        current_alternative_material=current_alternative_material,
        materials=materials,
        count=len(materials),
        search_roots=search_roots,
        attribution_conflicts=conflicts,
        cache_invalidated=cache_invalidated,
        message=_message(asset, asset_source, scan_failed, materials, search_roots,
                         default_material, default_material_reason, cache_invalidated),
    )
