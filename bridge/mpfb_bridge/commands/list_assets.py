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
rather than picking a winner quietly. ``license``, ``author`` and
``source_url`` come from the same join, through
[`shared/pack_attribution.py`](../shared/pack_attribution.py), which says where
it does not hold
([FR 046](../../../feature-requests/done/046-license-in-the-catalogues/README.md)).
Three choices around it are this command's:

- **``pack`` names the claimant the pack filter matched**, not merely the
  first: with ``hats01`` and ``hats01_cc0`` both claiming a hat,
  ``pack="_cc0"`` answering ``pack: "hats01"`` read as the filter failing.
  ``packs`` names them all.
- **The license filter is exact**, unlike the pack filter: ``"CC"`` matching
  both ``CC0`` and ``CC-BY`` would be a trap in a licensing question. An asset
  with no recorded license never matches, and the message says how many were
  excluded for that rather than checked.
- **``counts_by_license`` is taken before the license filter and the cap**, and
  ``matched_packs`` over the whole scan, so a narrowed answer still says what
  it narrowed from, and a pack registered with nothing on disk shows as ``0``.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_assets",
)

from ..log import get_logger
from ..shared import asset_sections
from ..shared import mpfb_surface
from ..shared import pack_attribution
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
    Param("license", TYPE_STRING, default=None, nullable=True,
          description="A license as pack metadata records it (\"CC0\", \"CC-BY\"), matched "
                      "exactly and case-insensitively. An asset with no recorded license never "
                      "matches."),
    Param("limit", TYPE_INTEGER, default=200, minimum=0, maximum=1000,
          description="How many assets to return. The answer always says whether it was cut."),
    Param("offset", TYPE_INTEGER, default=0, minimum=0,
          description="How many matching assets to skip. The order is deterministic."),
    Param("refresh", TYPE_BOOLEAN, default=False,
          description="Rescan the whole asset library before answering, invalidating MPFB's "
                      "alternative-material and pack-metadata caches on the way."),
)

SUMMARY = "List the installed assets, with the fragment and path an adding command takes."


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


def _entries_for_section(services, subdir, asset_type, object_type, roots, index):
    """Every asset MPFB's cached list holds for one section, attributed."""
    try:
        items = services["AssetService"].get_asset_list(subdir, asset_type) or dict()
    except Exception:  # pylint: disable=broad-except
        return []
    entries = []
    for item in items.values():
        name = str(item.get("name_without_ext") or "")
        if not name:
            continue
        path = mpfb_surface.as_path(item.get("full_path"))
        attribution = pack_attribution.attribute(index, path, roots)
        claimants = attribution["packs"]
        entries.append({
            "name": name,
            "label": str(item.get("label") or "") or None,
            "fragment": str(item.get("fragment") or "") or None,
            "path": path,
            "object_type": object_type,
            "asset_subdir": subdir,
            "file_type": asset_type,
            # Which claimant is reported is decided once the pack filter is
            # known; see _reported_pack().
            "pack": claimants[0] if claimants else None,
            "packs": claimants,
            "pack_ambiguous": len(claimants) > 1,
            "license": attribution["license"],
            "author": attribution["author"],
            "source_url": attribution["source_url"],
            # Deliberately not item["thumb"], which is a Blender preview object
            # rather than anything that survives JSON.
            "thumb_path": mpfb_surface.as_path(item.get("thumb_path")),
            # Not reported per row: whether the claimants disagree, and what each
            # says. A page's disagreements are reported once, beside it.
            "_attribution": attribution,
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
            # the user has since deleted. And against every claimant, so that a
            # filter cannot miss an asset whose first claimant is another pack.
            if not any(pack_pattern in claimant.lower() for claimant in entry["packs"]):
                continue
        matched.append(entry)

    # Deterministic before paging. MPFB's cached dict is insertion-ordered from
    # an rglob, whose order is filesystem-dependent, so an unsorted list would
    # silently skip and repeat entries between two pages of the same query.
    matched.sort(key=lambda entry: (entry["asset_subdir"], entry["name"].lower(), entry["name"]))
    return matched


def _license_counts(entries):
    """Recorded license -> how many of ``entries`` carry it, and how many carry none."""
    counts = dict()
    unknown = 0
    for entry in entries:
        if entry["license"] is None:
            unknown += 1
        else:
            counts[entry["license"]] = counts.get(entry["license"], 0) + 1
    return ({key: counts[key] for key in sorted(counts)}, unknown)


def _matched_packs(scanned, known_packs, pack_pattern):
    """Each installed pack the pattern matches, with how many scanned assets it claims.

    Over what this call scanned, and including a pack that claims nothing on
    disk - a pack registered with its assets missing shows as 0 rather than
    silently matching nothing.
    """
    matched = {name: 0 for name in known_packs if pack_pattern in name.lower()}
    for entry in scanned:
        for claimant in entry["packs"]:
            if claimant in matched:
                matched[claimant] += 1
    return matched


def _reported_pack(entry, pack_pattern):
    """The claimant ``pack`` names: the first matching the filter, else the first.

    So ``pack="_cc0"`` never answers with ``pack: "hats01"`` for an asset that
    ``hats01_cc0`` claims too.
    """
    if pack_pattern is not None:
        for claimant in entry["packs"]:
            if pack_pattern in claimant.lower():
                return claimant
    return entry["packs"][0] if entry["packs"] else None


def _message(requested, recognized, matched, licensed, page, unknown_excluded, index):
    parts = []
    if requested["asset_subdir"] is not None and not recognized["asset_subdir"]:
        parts.append("No asset subdir called '{:s}'. See 'known_asset_subdirs'.".format(
            str(requested["asset_subdir"])))
    elif requested["pack"] is not None and not recognized["pack"]:
        parts.append("No installed asset pack name contains '{:s}'. See 'known_packs'.".format(
            str(requested["pack"])))
    elif requested["license"] is not None and not recognized["license"]:
        parts.append("No installed pack records the license '{:s}'. See "
                     "'known_licenses'.".format(str(requested["license"])))
    else:
        parts.append("{:d} assets matched, {:d} returned".format(len(licensed), len(page)))
        if len(licensed) > len(page):
            parts.append(" - the rest were not returned, so this is not the whole library")
        parts.append(
            ". Each asset is named twice: 'path' is what an adding function takes, 'fragment' "
            "is the portable identifier MPFB records on the object it produces. 'pack' and "
            "'license' are derived from a directory name, not recorded.")
        if requested["license"] is not None:
            parts.append(
                " The license filter left out {:d} of {:d}; {:d} of those have no recorded "
                "license and were excluded, not checked.".format(
                    len(matched) - len(licensed), len(matched), unknown_excluded))
    if not index.entries_read:
        parts.append(" MPFB's pack metadata could not be read, so every license is null; "
                     "'pack' still comes from the pack names.")
    return "".join(parts)


def list_assets(params, resolution):  # pylint: disable=too-many-locals
    """Catalogue the installed assets, filtered, capped and paged."""
    services = resolution.services
    requested_subdir = params["asset_subdir"]
    requested_pack = params["pack"]
    requested_license = params["license"]
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

    index = pack_attribution.read_index(services)
    known_packs = index.pack_names

    # MPFB's own substring semantics, from get_asset_names_in_pack_pattern().
    pack_pattern = requested_pack.strip().lower() if requested_pack is not None else None
    pack_recognized = True
    if pack_pattern is not None:
        pack_recognized = any(pack_pattern in name.lower() for name in known_packs)

    # Exact and case-insensitive, against the metadata's own spelling.
    license_wanted = requested_license.strip().lower() if requested_license is not None else None
    license_recognized = True
    if license_wanted is not None:
        license_recognized = any(license_wanted == known.lower()
                                 for known in index.known_licenses)

    scanned = []
    counts_by_subdir = dict()
    asset_roots_searched = dict()
    for subdir, asset_type, object_type in sections:
        roots = _read_asset_roots(services, subdir)
        asset_roots_searched[subdir] = roots
        section_entries = _entries_for_section(
            services, subdir, asset_type, object_type, roots, index)
        # Ignores name_contains, pack and license, and ignores the cap: this is
        # what keeps an over-broad call informative rather than merely truncated.
        counts_by_subdir[subdir] = len(section_entries)
        scanned.extend(section_entries)

    needle = name_contains.strip().lower() if name_contains is not None else None
    matched = _matching(scanned, needle, pack_pattern)

    # After every other filter and before this one and the cap, so a call
    # filtered to one license still says how many it left out.
    counts_by_license, license_unknown_count = _license_counts(matched)
    licensed = matched
    if license_wanted is not None:
        # An asset with no recorded license never matches: it was not checked.
        licensed = [entry for entry in matched
                    if entry["license"] is not None and entry["license"].lower() == license_wanted]

    page = licensed[offset:offset + limit]
    conflicts = []
    for entry in page:
        entry["pack"] = _reported_pack(entry, pack_pattern)
        attribution = entry.pop("_attribution")
        if attribution["claims_disagree"]:
            conflicts.append({"path": entry["path"], "claims": attribution["claims"]})

    _LOG.debug("list_assets: %d scanned, %d matched, %d licensed, %d returned",
               len(scanned), len(matched), len(licensed), len(page))

    requested = {"asset_subdir": requested_subdir, "pack": requested_pack,
                 "license": requested_license}
    recognized = {"asset_subdir": subdir_recognized, "pack": pack_recognized,
                  "license": license_recognized}
    return {
        "assets": page,
        "count": len(page),
        "total_count": len(licensed),
        # Always present, and the field an agent has to read before concluding
        # the library lacks something: a capped answer must never look like a
        # complete one.
        "truncated": len(licensed) > len(page),
        "offset": offset,
        "limit": limit,
        "counts_by_asset_subdir": counts_by_subdir,
        "counts_by_license": counts_by_license,
        "license_unknown_count": license_unknown_count,
        "requested_asset_subdir": requested_subdir,
        "asset_subdir_recognized": subdir_recognized,
        "known_asset_subdirs": known_subdirs,
        "section_table_from_mpfb": sections_from_mpfb,
        "requested_pack": requested_pack,
        "pack_recognized": pack_recognized,
        "known_packs": known_packs,
        "matched_packs": (None if pack_pattern is None
                          else _matched_packs(scanned, known_packs, pack_pattern)),
        "requested_license": requested_license,
        "license_recognized": license_recognized,
        "known_licenses": index.known_licenses,
        "attribution_conflicts": conflicts,
        "asset_roots_searched": asset_roots_searched,
        "message": _message(requested, recognized, matched, licensed, page,
                            license_unknown_count if license_wanted is not None else 0, index),
    }
