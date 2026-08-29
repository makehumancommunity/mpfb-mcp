"""
Payload for ``mpfb_list_assets``: which assets are installed and addable here.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``asset_subdir``,
  ``name_contains``, ``pack``, ``limit``, ``offset``, ``refresh``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap, and used here to reach
  ``ASSET_LIBRARY_SECTIONS`` off AssetService's module.

The field this exists for is ``fragment``: the exact string an asset-adding
function takes, so that finding an asset and using it are one step apart rather
than two. Everything else is either what that fragment names, or a guard against
the two ways this answer can mislead - it is capped, and it is filtered, and
either can make a subset look like the whole library.

Two costs are paid deliberately and are documented in the tool docstring rather
than worked around. ``AssetService.get_asset_list()`` populates MPFB's own cache,
which loads a Blender preview image per thumbnailed asset - a real side effect,
and exactly the one MPFB's asset panels already pay for. And that cache is keyed
by *label*, so two assets whose filenames differ only in case or underscores
collapse into one entry and the counts here under-report by that much. Reaching
around it would mean reimplementing ``update_asset_list()`` here.
"""

import os

AssetService = _MPFB_SERVICES["AssetService"]
LocationService = _MPFB_SERVICES["LocationService"]

# MPFB's ASSET_LIBRARY_SECTIONS, as a literal, used only when it cannot be read
# off AssetService's module. Each row is (asset_subdir, asset_type,
# object_type), which is three of the fields reported per asset - the reason no
# mapping table of our own is written here. Note the three rows whose
# object_type is not a type any object in a scene carries: skins are "Material",
# poses are "Pose" and ink layers are "Other".
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


def as_path(path):
    # Coerce at the point a path enters the response. The cached items' paths
    # are str, but several AssetService helpers hand back pathlib.Path, and one
    # of those in the response fails strict_json and takes the whole answer
    # down with it.
    if not path:
        return None
    return str(path)


def read_sections():
    # ASSET_LIBRARY_SECTIONS is a module-level name in assetservice.py: not a
    # member of AssetService and not in the SERVICES dict, so it is reached
    # through the module a resolved service already came from (see
    # specifications/architecture.md). Unlike the underscore-private constants
    # other payloads read it is public, but the rule is the same - read it with
    # a fallback and degrade, since a stale local table is a better answer than
    # a failed call.
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


def read_pack_index():
    # Name -> the installed packs claiming it, built once per call. The names in
    # pack metadata are the *directory* names a pack installs under, which is
    # the whole basis of the attribution below. Building this per asset would be
    # a metadata read per asset.
    names = []
    try:
        names = [str(name) for name in (AssetService.get_pack_names() or [])]
    except Exception:  # pylint: disable=broad-except
        names = []
    index = dict()
    for pack_name in names:
        try:
            asset_names = AssetService.get_asset_names_in_pack(pack_name) or []
        except Exception:  # pylint: disable=broad-except
            asset_names = []
        for asset_name in asset_names:
            index.setdefault(str(asset_name), []).append(pack_name)
    for key in index:
        index[key] = sorted(set(index[key]))
    return (sorted(names), index)


def read_asset_roots(subdir):
    # get_asset_roots(), not get_available_data_roots(): the difference is the
    # diagnostic. A data root that is configured but holds no such subdir is not
    # searched, and that is the usual explanation for "I installed it and it is
    # not here".
    try:
        roots = AssetService.get_asset_roots(subdir) or []
    except Exception:  # pylint: disable=broad-except
        return []
    return [str(root) for root in roots]


def packs_claiming(dirname, normalized_roots, pack_index):
    # The join: the basename of an asset's containing directory, looked up in
    # the pack index. Derived from a naming convention, never recorded anywhere,
    # which is why the response says so and flags the ambiguous case.
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


def entries_for_section(subdir, asset_type, object_type, roots, pack_index):
    normalized_roots = [os.path.normpath(root) for root in roots]
    try:
        items = AssetService.get_asset_list(subdir, asset_type) or dict()
    except Exception:  # pylint: disable=broad-except
        return []
    entries = []
    for item in items.values():
        name = str(item.get("name_without_ext") or "")
        if not name:
            continue
        claimants = packs_claiming(item.get("dirname"), normalized_roots, pack_index)
        entries.append({
            "name": name,
            "label": str(item.get("label") or "") or None,
            "fragment": str(item.get("fragment") or "") or None,
            "path": as_path(item.get("full_path")),
            "object_type": object_type,
            "asset_subdir": subdir,
            "file_type": asset_type,
            "pack": claimants[0] if claimants else None,
            "pack_ambiguous": len(claimants) > 1,
            # Deliberately not item["thumb"], which is a Blender preview object
            # rather than anything that survives JSON.
            "thumb_path": as_path(item.get("thumb_path")),
            # Not reported: every pack claiming this asset. It is what the pack
            # filter below matches against, so that a filter cannot miss an
            # asset whose alphabetically-first claimant is a different pack.
            "_claimants": claimants,
        })
    return entries


requested_subdir = PARAMS["asset_subdir"]
requested_pack = PARAMS["pack"]
name_contains = PARAMS["name_contains"]
limit = PARAMS["limit"]
offset = PARAMS["offset"]

sections, sections_from_mpfb = read_sections()
known_subdirs = [row[0] for row in sections]

# Exact, case-insensitive, resolved back to MPFB's own spelling. Unlike
# mpfb_list_objects' type filter there is no MPFB matcher to mirror here, and a
# substring match over eleven names that share words would be a trap rather than
# a convenience.
subdir_recognized = True
if requested_subdir is not None:
    matched_subdir = None
    for candidate in known_subdirs:
        if candidate.lower() == requested_subdir.strip().lower():
            matched_subdir = candidate
    subdir_recognized = matched_subdir is not None
    sections = [row for row in sections if row[0] == matched_subdir]

if PARAMS["refresh"]:
    # The whole library, not the requested subdir, and it invalidates the
    # alternative-material and pack-metadata caches on the way. Called once,
    # before anything is read.
    AssetService.update_all_asset_lists()

known_packs, pack_index = read_pack_index()

# MPFB's own substring semantics, from get_asset_names_in_pack_pattern(): a
# pattern matches a pack name if it appears anywhere in it, case-insensitively.
# So "hair03" finds "hair03_ccby".
pack_pattern = requested_pack.strip().lower() if requested_pack is not None else None
pack_recognized = True
if pack_pattern is not None:
    pack_recognized = any(pack_pattern in name.lower() for name in known_packs)

scanned = []
counts_by_subdir = dict()
asset_roots_searched = dict()
for subdir, asset_type, object_type in sections:
    roots = read_asset_roots(subdir)
    asset_roots_searched[subdir] = roots
    section_entries = entries_for_section(subdir, asset_type, object_type, roots, pack_index)
    # Ignores name_contains and pack, and ignores the cap: this is what keeps an
    # over-broad call informative rather than merely truncated. It covers the
    # subdirs actually scanned, so a call naming one subdir counts that one.
    counts_by_subdir[subdir] = len(section_entries)
    scanned.extend(section_entries)

needle = name_contains.strip().lower() if name_contains is not None else None

matched = []
for entry in scanned:
    if needle is not None:
        haystacks = [entry["name"].lower(), (entry["label"] or "").lower()]
        if not any(needle in haystack for haystack in haystacks):
            continue
    if pack_pattern is not None:
        # Matched against the assets actually found on disk, never built from
        # pack metadata - a pack lists what it shipped, including files the user
        # has since deleted.
        if not any(pack_pattern in claimant.lower() for claimant in entry["_claimants"]):
            continue
    matched.append(entry)

# Deterministic before paging. MPFB's cached dict is insertion-ordered from an
# rglob, whose order is filesystem-dependent, so an unsorted list would silently
# skip and repeat entries between two pages of the same query.
matched.sort(key=lambda entry: (entry["asset_subdir"], entry["name"].lower(), entry["name"]))

page = matched[offset:offset + limit]
for entry in page:
    del entry["_claimants"]

message_parts = []
if requested_subdir is not None and not subdir_recognized:
    message_parts.append(
        "No asset subdir called '" + str(requested_subdir) + "'. See 'known_subdirs'.")
elif pack_pattern is not None and not pack_recognized:
    message_parts.append(
        "No installed asset pack name contains '" + str(requested_pack)
        + "'. See 'known_packs'.")
else:
    message_parts.append(
        str(len(matched)) + " assets matched, " + str(len(page)) + " returned")
    if len(matched) > len(page):
        message_parts.append(
            " - the rest were not returned, so this is not the whole library")
    message_parts.append(
        ". Each asset is named twice: 'path' is what an adding function takes, 'fragment' is the "
        "portable identifier MPFB records on the object it produces. 'pack' is derived from a "
        "directory name, not recorded.")

result = {
    "assets": page,
    "count": len(page),
    "total_count": len(matched),
    # Always present, and the field an agent has to read before concluding the
    # library lacks something: a capped answer must never look like a complete
    # one.
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
    "message": "".join(message_parts),
}
