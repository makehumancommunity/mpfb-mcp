"""
``list_assets``: which assets are installed here, and how to equip one.

**The field this exists for is ``fragment``**: the exact string an asset-adding
function takes, so that finding an asset and using it are one step apart rather
than two. Everything else is either what that fragment names, or a guard against
the two ways this answer can mislead - it is capped, and it is filtered, and
either can make a subset look like the whole library.

The section table it reports from is
[`shared/asset_sections.py`](../shared/asset_sections.py), shared with
``add_asset`` for a sharp reason: this reports an ``object_type`` and a
``fragment``, that command is handed the pair and has to turn it back into a
file, and the only thing mapping ``Clothes`` back to ``clothes`` is that table.
Two implementations of it could disagree, and an asset this command had just
listed would come back from the other as though it were not installed.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
 Its two costs are paid deliberately and documented rather than worked
around, and its two filters are quirks in their own right:

- ``AssetService.get_asset_list()`` **populates MPFB's own cache**, which loads
  a Blender preview image per thumbnailed asset. A real side effect, and
  exactly the one MPFB's asset panels already pay for.
- That cache is keyed by **label**, so two assets whose filenames differ only in
  case or underscores collapse into one entry and the counts here under-report
  by that much. Reaching around it would mean reimplementing
  ``update_asset_list()``.
- The **subdir** filter is exact and case-insensitive, unlike ``list_objects``'
  type filter. There is no MPFB matcher to mirror, and a substring match over
  eleven names that share words would be a trap rather than a convenience.
- The **pack** filter *is* a substring, because that is
  ``get_asset_names_in_pack_pattern()``'s own rule: "hair03" finds
  "hair03_ccby".

``pack`` itself is derived from a **directory naming convention** and is
recorded nowhere, which is why the answer says so and flags the ambiguous case
rather than picking a winner quietly.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_assets",
)

import os

from ..log import get_logger
from ..shared import asset_sections
from ..shared import mpfb_surface
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_INTEGER
from ..validation import TYPE_STRING

_LOG = get_logger("commands.listassets")

PARAMS = (
    Param("asset_subdir", TYPE_STRING, default=None, nullable=True,
          description="One of MPFB's asset subdirs, matched exactly and case-insensitively. "
                      "Omit to search every subdir."),
    Param("name_contains", TYPE_STRING, default=None, nullable=True,
          description="Case-insensitive substring matched against an asset's name and label."),
    Param("pack", TYPE_STRING, default=None, nullable=True,
          description="Case-insensitive substring matched against the installed pack names, "
                      "which is MPFB's own rule for a pack pattern."),
    Param("limit", TYPE_INTEGER, default=200, minimum=0, maximum=1000,
          description="How many assets to return. The answer always says whether it was cut."),
    Param("offset", TYPE_INTEGER, default=0, minimum=0,
          description="How many matching assets to skip. The order is deterministic."),
    Param("refresh", TYPE_BOOLEAN, default=False,
          description="Rescan the whole asset library before answering, invalidating MPFB's "
                      "alternative-material and pack-metadata caches on the way."),
)

SUMMARY = "List the installed assets, with the fragment and path an adding command takes."


def _read_pack_index(services):
    """Asset name -> the installed packs claiming it, built once per call.

    The names in pack metadata are the *directory* names a pack installs under,
    which is the whole basis of the attribution below. Building this per asset
    would be a metadata read per asset.
    """
    asset_service = services["AssetService"]
    names = []
    try:
        names = [str(name) for name in (asset_service.get_pack_names() or [])]
    except Exception:  # pylint: disable=broad-except
        names = []
    index = dict()
    for pack_name in names:
        try:
            asset_names = asset_service.get_asset_names_in_pack(pack_name) or []
        except Exception:  # pylint: disable=broad-except
            asset_names = []
        for asset_name in asset_names:
            index.setdefault(str(asset_name), []).append(pack_name)
    for key in index:
        index[key] = sorted(set(index[key]))
    return (sorted(names), index)


def _read_asset_roots(services, subdir):
    """Which roots are actually searched for this subdir.

    ``get_asset_roots()``, not ``get_available_data_roots()``: the difference is
    the diagnostic. A data root that is configured but holds no such subdir is
    not searched, and that is the usual explanation for "I installed it and it
    is not here".
    """
    try:
        roots = services["AssetService"].get_asset_roots(subdir) or []
    except Exception:  # pylint: disable=broad-except
        return []
    return [str(root) for root in roots]


def _packs_claiming(dirname, normalized_roots, pack_index):
    """Which packs claim the directory one asset sits in. A convention, not a record."""
    if not dirname:
        return []
    normalized = os.path.normpath(str(dirname))
    if normalized in normalized_roots:
        # An asset sitting directly in the asset root rather than in a directory
        # of its own - skins/default.mhmat and the ink layers are both like
        # this. Its containing directory is named for the *subdir*, so the join
        # would attribute it to whichever pack happened to ship an asset called
        # "skins". No directory name means no attribution.
        return []
    return pack_index.get(os.path.basename(normalized), [])


def _entries_for_section(services, subdir, asset_type, object_type, roots, pack_index):
    """Every asset MPFB's cached list holds for one section."""
    normalized_roots = [os.path.normpath(root) for root in roots]
    try:
        items = services["AssetService"].get_asset_list(subdir, asset_type) or dict()
    except Exception:  # pylint: disable=broad-except
        return []
    entries = []
    for item in items.values():
        name = str(item.get("name_without_ext") or "")
        if not name:
            continue
        claimants = _packs_claiming(item.get("dirname"), normalized_roots, pack_index)
        entries.append({
            "name": name,
            "label": str(item.get("label") or "") or None,
            "fragment": str(item.get("fragment") or "") or None,
            "path": mpfb_surface.as_path(item.get("full_path")),
            "object_type": object_type,
            "asset_subdir": subdir,
            "file_type": asset_type,
            "pack": claimants[0] if claimants else None,
            "pack_ambiguous": len(claimants) > 1,
            # Deliberately not item["thumb"], which is a Blender preview object
            # rather than anything that survives JSON.
            "thumb_path": mpfb_surface.as_path(item.get("thumb_path")),
            # Not reported: every pack claiming this asset. It is what the pack
            # filter below matches against, so that a filter cannot miss an
            # asset whose alphabetically-first claimant is a different pack.
            "_claimants": claimants,
        })
    return entries


def _matching(scanned, needle, pack_pattern):
    """The entries surviving the name and pack filters, in a deterministic order."""
    matched = []
    for entry in scanned:
        if needle is not None:
            haystacks = [entry["name"].lower(), (entry["label"] or "").lower()]
            if not any(needle in haystack for haystack in haystacks):
                continue
        if pack_pattern is not None:
            # Matched against the assets actually found on disk, never built
            # from pack metadata - a pack lists what it shipped, including files
            # the user has since deleted.
            if not any(pack_pattern in claimant.lower() for claimant in entry["_claimants"]):
                continue
        matched.append(entry)

    # Deterministic before paging. MPFB's cached dict is insertion-ordered from
    # an rglob, whose order is filesystem-dependent, so an unsorted list would
    # silently skip and repeat entries between two pages of the same query.
    matched.sort(key=lambda entry: (entry["asset_subdir"], entry["name"].lower(), entry["name"]))
    return matched


def _message(requested_subdir, subdir_recognized, requested_pack, pack_pattern,
             pack_recognized, matched, page):
    parts = []
    if requested_subdir is not None and not subdir_recognized:
        parts.append("No asset subdir called '{:s}'. See 'known_subdirs'.".format(
            str(requested_subdir)))
    elif pack_pattern is not None and not pack_recognized:
        parts.append("No installed asset pack name contains '{:s}'. See 'known_packs'.".format(
            str(requested_pack)))
    else:
        parts.append("{:d} assets matched, {:d} returned".format(len(matched), len(page)))
        if len(matched) > len(page):
            parts.append(" - the rest were not returned, so this is not the whole library")
        parts.append(
            ". Each asset is named twice: 'path' is what an adding function takes, 'fragment' "
            "is the portable identifier MPFB records on the object it produces. 'pack' is "
            "derived from a directory name, not recorded.")
    return "".join(parts)


def list_assets(params, resolution):  # pylint: disable=too-many-locals
    """Catalogue the installed assets, filtered, capped and paged."""
    services = resolution.services
    requested_subdir = params["asset_subdir"]
    requested_pack = params["pack"]
    name_contains = params["name_contains"]
    limit = params["limit"]
    offset = params["offset"]

    sections, sections_from_mpfb = asset_sections.read_sections(services)
    known_subdirs = [row[0] for row in sections]

    # Exact, case-insensitive, resolved back to MPFB's own spelling. See this
    # module's docstring for why this filter is not a substring match.
    subdir_recognized = True
    if requested_subdir is not None:
        matched_subdir = None
        for candidate in known_subdirs:
            if candidate.lower() == requested_subdir.strip().lower():
                matched_subdir = candidate
        subdir_recognized = matched_subdir is not None
        sections = [row for row in sections if row[0] == matched_subdir]

    if params["refresh"]:
        # The whole library, not the requested subdir, and it invalidates the
        # alternative-material and pack-metadata caches on the way. Called once,
        # before anything is read.
        services["AssetService"].update_all_asset_lists()

    known_packs, pack_index = _read_pack_index(services)

    # MPFB's own substring semantics, from get_asset_names_in_pack_pattern().
    pack_pattern = requested_pack.strip().lower() if requested_pack is not None else None
    pack_recognized = True
    if pack_pattern is not None:
        pack_recognized = any(pack_pattern in name.lower() for name in known_packs)

    scanned = []
    counts_by_subdir = dict()
    asset_roots_searched = dict()
    for subdir, asset_type, object_type in sections:
        roots = _read_asset_roots(services, subdir)
        asset_roots_searched[subdir] = roots
        section_entries = _entries_for_section(
            services, subdir, asset_type, object_type, roots, pack_index)
        # Ignores name_contains and pack, and ignores the cap: this is what
        # keeps an over-broad call informative rather than merely truncated.
        counts_by_subdir[subdir] = len(section_entries)
        scanned.extend(section_entries)

    needle = name_contains.strip().lower() if name_contains is not None else None
    matched = _matching(scanned, needle, pack_pattern)

    page = matched[offset:offset + limit]
    for entry in page:
        del entry["_claimants"]

    _LOG.debug("list_assets: %d scanned, %d matched, %d returned",
               len(scanned), len(matched), len(page))

    return {
        "assets": page,
        "count": len(page),
        "total_count": len(matched),
        # Always present, and the field an agent has to read before concluding
        # the library lacks something: a capped answer must never look like a
        # complete one.
        "truncated": len(matched) > len(page),
        "offset": offset,
        "limit": limit,
        "counts_by_subdir": counts_by_subdir,
        "requested_subdir": requested_subdir,
        "subdir_recognized": subdir_recognized,
        "known_subdirs": known_subdirs,
        "section_table_from_mpfb": sections_from_mpfb,
        "requested_pack": requested_pack,
        "pack_recognized": pack_recognized,
        "known_packs": known_packs,
        "asset_roots_searched": asset_roots_searched,
        "message": _message(requested_subdir, subdir_recognized, requested_pack,
                            pack_pattern, pack_recognized, matched, page),
    }
