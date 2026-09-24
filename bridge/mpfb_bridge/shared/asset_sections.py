"""
MPFB's asset-library section table, and what it maps between.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/`` and what the ``services`` argument is doing there.

This exists for the same reason ``rig_lookup`` does, and the consequence of
getting it wrong is sharper. ``list_assets`` reports, per asset, the
``object_type`` that doubles as ``add_mhclo_asset()``'s ``asset_type`` and the
portable ``fragment`` MPFB records on the object it produces. ``add_asset`` is
then handed that pair and has to turn it back into a file:
``AssetService.find_asset_absolute_path()`` takes an **asset subdir**, and the
only thing that maps ``Clothes`` back to ``clothes`` is this table. Two copies
of it disagreeing would make an asset the catalogue just listed unfindable by
the command the catalogue exists to feed - a failure that would read as "the
asset is not installed".

The table itself is a module-level name in ``assetservice.py``: not a member of
``AssetService`` and not in the ``SERVICES`` dict, so it is reached through the
module a resolved service already came from. **Being add-on code makes
``from ... import ASSET_LIBRARY_SECTIONS`` possible here for the first time and
leaves it forbidden** -
[never import MPFB submodules directly](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
survives the pivot. Unlike the underscore-private constants other commands read
it is public, but the rule is the same: read it with a fallback and degrade,
since a stale local table is a better answer than a failed call.
``sections_from_mpfb`` is how a caller learns which of the two it got.

Note what the table is *not*: a list of things that can be equipped. Three of
its rows carry an ``object_type`` no object in a scene can have - skins are
``Material``, poses are ``Pose``, ink layers are ``Other`` - so the vocabulary
of MHCLO asset types is the table intersected with ObjectService's own
``_MESH_ASSET_TYPES``, which is what :func:`mesh_asset_types` does. Deriving
those eight rather than listing them here is what keeps this file from becoming
a third opinion about what MPFB supports.
"""

# The local bindings below are spelled with MPFB's own capitalisation -
# ``LocationService = services["LocationService"]`` - rather than snake_case,
# so that a body here reads the way MPFB's own source reads and can be
# compared with it line for line. That is the whole reason for the disable.
# pylint: disable=invalid-name

__all__ = (
    "FALLBACK_MESH_ASSET_TYPES",
    "FALLBACK_SECTIONS",
    "mesh_asset_types",
    "normalize_asset_type",
    "read_sections",
    "subdir_for_object_type",
)

import sys


# MPFB's ASSET_LIBRARY_SECTIONS, as a literal, used only when it cannot be read
# off AssetService's module. Each row is (asset_subdir, asset_type,
# object_type), which is three of the fields mpfb_list_assets reports per asset
# - the reason no mapping table of our own is written anywhere else. Note the
# three rows whose object_type is not a type any object in a scene carries.
FALLBACK_SECTIONS = (
    ("proxymeshes", "proxy", "Proxymeshes"),
    ("skins", "mhmat", "Material"),
    ("ink_layers", "json", "Other"),
    ("eyes", "mhclo", "Eyes"),
    ("eyebrows", "mhclo", "Eyebrows"),
    ("eyelashes", "mhclo", "Eyelashes"),
    ("hair", "mhclo", "Hair"),
    ("teeth", "mhclo", "Teeth"),
    ("tongue", "mhclo", "Tongue"),
    ("clothes", "mhclo", "Clothes"),
    ("poses", "bvh", "Pose"),
)

# ObjectService's own vocabulary of the types an MHCLO asset can end up as,
# read the way every other module-level name is read and with the same fallback.
FALLBACK_MESH_ASSET_TYPES = (
    "Proxymeshes", "Clothes", "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair",
)


def read_sections(services):
    """MPFB's section table as (asset_subdir, asset_type, object_type) rows.

    Returns the rows and whether they came from MPFB itself, so that a response
    built on the fallback can say so rather than quietly claiming authority.
    """
    AssetService = services["AssetService"]
    module = sys.modules.get(AssetService.__module__)
    table = getattr(module, "ASSET_LIBRARY_SECTIONS", None)
    rows = []
    try:
        for section in table or []:
            rows.append((
                str(section["asset_subdir"]),
                str(section["asset_type"]),
                str(section["object_type"]),
            ))
    except Exception:  # pylint: disable=broad-except
        rows = []
    if rows:
        return (rows, True)
    return (list(FALLBACK_SECTIONS), False)


def mesh_asset_types(services, sections):
    """The object types an MHCLO asset can be added as, in table order.

    The intersection of the section table with ObjectService's own
    ``_MESH_ASSET_TYPES``, rather than a list kept here: the rows this drops are
    exactly the ones that would fail deep inside ``add_mhclo_asset()`` - a skin
    is a material, a pose is a BVH file, and neither is an object it could
    import.
    """
    ObjectService = services["ObjectService"]
    objectservice_module = sys.modules.get(ObjectService.__module__)
    known = getattr(objectservice_module, "_MESH_ASSET_TYPES", None) or FALLBACK_MESH_ASSET_TYPES
    lowered = set(str(name).lower() for name in known)
    types = []
    for row in sections:
        object_type = row[2]
        if str(object_type).lower() in lowered and object_type not in types:
            types.append(object_type)
    return types


def subdir_for_object_type(sections, object_type):
    """The asset subdir ``find_asset_absolute_path()`` wants for this type.

    Case-insensitive, because the caller got the type from a catalogue that
    reports MPFB's spelling but ``add_mhclo_asset()`` normalises whatever it is
    given - so "eyes" and "Eyes" must resolve alike here too, or a fragment
    would be looked up under a subdir that does not exist and come back as
    "not installed".
    """
    if not object_type:
        return None
    wanted = str(object_type).strip().lower()
    for subdir, _asset_type, candidate in sections:
        if str(candidate).lower() == wanted:
            return subdir
    return None


def normalize_asset_type(value):
    """MPFB's own normalisation of the ``asset_type`` argument.

    ``add_mhclo_asset()`` stores ``str(asset_type).lower().capitalize()`` on the
    object, so "eyes", "Eyes" and "EYES" all become ``Eyes`` and the *subdir*
    name works as well as the object type for every current section. Reproduced
    rather than relied upon: a tool that echoed the caller's spelling would
    report something other than what was recorded, and the coincidence between
    the two vocabularies breaks the day a two-word type appears.
    """
    return str(value).lower().capitalize()
