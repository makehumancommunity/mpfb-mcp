"""
Payload for ``mpfb_list_targets``: which modeling targets this Blender could set.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``section``,
  ``name_contains``, ``limit``, ``offset``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap (unused here, but bound).

The field this exists for is ``shapekey_name``. A target is addressed by the
name of the shape key it becomes, which is derived from its filename by
``TargetService.filename_to_shapekey_name()`` - and that derivation is not the
identity function, since a name over 60 characters is *encoded* to fit Blender's
shape key name limit. Reporting the filename alone would hand the caller
something that silently addresses nothing.

Two sources, genuinely different in kind. ``target.json`` is a curated index of
the bundled targets, too large to return and exactly the sort of file a caller
can read for itself, so its *path* is reported and its sections are browsable
one at a time. The user data directories have no index at all: they are scanned
here, per call, which makes this deliberately more current than MPFB's own
modeling panels - those scan at module import time and so only ever see what
existed when Blender started.

This reimplements ``mpfb.ui.model._modelsubpanels``' scan rather than importing
it, for both of those reasons: importing an MPFB submodule is forbidden (see
specifications/architecture.md) precisely because of import-time work like that
scan. The module remains the reference for *what* to scan.

Nothing is loaded into the scene, no MPFB cache is populated and no preview is
loaded: this is a handful of directory walks and one JSON read.
"""

import json
import os

LocationService = _MPFB_SERVICES["LocationService"]
AssetService = _MPFB_SERVICES["AssetService"]
TargetService = _MPFB_SERVICES["TargetService"]

# Bundled targets under here are driven by basemesh attributes rather than by
# loading a target file, which is mpfb_set_macro_details' territory rather than
# mpfb_set_target_value's. Excluded from the unindexed-directory report so that
# it does not read as something to go and set.
MACRODETAILS_DIRECTORY = "macrodetails"

TARGET_EXTENSIONS = (".target", ".target.gz")


def as_path(path):
    # Coerce at the point a path enters the response.
    # AssetService.find_asset_files_matching_pattern() returns pathlib.Path
    # objects, and this payload handles those directly rather than through
    # MPFB's cached asset items - so one uncoerced value here fails strict_json
    # and takes the whole answer down with it.
    if not path:
        return None
    return str(path)


def is_target_file(filename):
    lowered = str(filename).lower()
    for extension in TARGET_EXTENSIONS:
        if lowered.endswith(extension):
            return True
    return False


def target_file_type(filename):
    # "target.gz" rather than "gz": the pair a caller cares about is the one
    # MPFB's user-directory scan discriminates on.
    if str(filename).lower().endswith(".target.gz"):
        return "target.gz"
    return "target"


def strip_target_extension(basename):
    # The display name only. The *addressable* name is shapekey_name, which
    # comes from MPFB rather than from here.
    name = str(basename)
    if name.lower().endswith(".target.gz"):
        return name[:-len(".target.gz")]
    if name.lower().endswith(".target"):
        return name[:-len(".target")]
    return name


def shapekey_name_for(full_path):
    # Never reimplemented here. filename_to_shapekey_name() strips .gz and
    # .target/.ptarget case-insensitively and then encodes names over 60
    # characters to fit Blender's shape key name limit, and it is the function
    # that decides what the shape key is actually called. macrodetail=False is
    # passed explicitly because macro details are out of scope for this tool;
    # the argument is keyword-only.
    try:
        return str(TargetService.filename_to_shapekey_name(full_path, macrodetail=False))
    except Exception:  # pylint: disable=broad-except
        # A derivation that fails is reported as missing rather than guessed at:
        # a plausible-looking name that addresses nothing is worse than none.
        return None


def read_target_json(target_json_path):
    # Read directly rather than through a service - MPFB has no accessor for it,
    # and its own consumers json.load() this same path. Guarded, so a missing or
    # broken index is an answer rather than a failed call.
    if not target_json_path or not os.path.isfile(target_json_path):
        return (None, "not_found")
    try:
        with open(target_json_path, "r") as json_file:
            sections = json.load(json_file)
    except Exception:  # pylint: disable=broad-except
        return (None, "unreadable")
    if not isinstance(sections, dict):
        return (None, "unreadable")
    return (sections, "ok")


def count_targets_below(directory):
    total = 0
    for _root, _dirs, files in os.walk(directory):
        for filename in files:
            if is_target_file(filename):
                total = total + 1
    return total


def find_unindexed_dirs(system_targets_dir, indexed_names):
    # Diffed, never hardcoded: target.json has 22 sections while the directory
    # holds more, and a pair named here would drift the moment MPFB adds a
    # directory. Directories holding no target file at all (_images) drop out by
    # the count rather than by a name check.
    if not system_targets_dir or not os.path.isdir(system_targets_dir):
        return []
    unindexed = []
    try:
        entries = sorted(os.listdir(system_targets_dir))
    except Exception:  # pylint: disable=broad-except
        return []
    for entry in entries:
        if entry in indexed_names or entry == MACRODETAILS_DIRECTORY:
            continue
        directory = os.path.join(system_targets_dir, entry)
        if not os.path.isdir(directory):
            continue
        count = count_targets_below(directory)
        if count < 1:
            continue
        unindexed.append({
            "name": entry,
            "path": as_path(directory),
            "target_count": count,
        })
    return unindexed


def files_matching(roots, pattern):
    try:
        return list(AssetService.find_asset_files_matching_pattern(roots, pattern) or [])
    except Exception:  # pylint: disable=broad-except
        return []


def user_target_entry(found):
    # Built only after the duplicates are gone, so shapekey_name_for() - the one
    # call here that crosses into MPFB - happens once per target rather than
    # once per way of reaching it.
    full_path, section, listed_in_mpfb_ui = found
    basename = os.path.basename(full_path)
    return {
        "name": strip_target_extension(basename),
        "shapekey_name": shapekey_name_for(full_path),
        "path": as_path(full_path),
        "section": section,
        "file_type": target_file_type(basename),
        # False is a real MPFB scan asymmetry rather than anything decided here:
        # its user-targets scan matches only "*.target", so a gzipped target in
        # a user targets directory is on disk, loadable, and invisible in MPFB's
        # own modeling panels.
        "listed_in_mpfb_ui": listed_in_mpfb_ui,
    }


def scan_custom_targets():
    # AssetService.get_asset_roots() spans *every* data root, the bundled MPFB
    # one included, not just the user one - so both extensions from both places
    # land in one synthesized "custom" section, exactly as MPFB's panel does it.
    roots = []
    for subdir in ("custom", "targets/custom"):
        try:
            roots.extend(AssetService.get_asset_roots(subdir) or [])
        except Exception:  # pylint: disable=broad-except
            continue
    roots = [str(root) for root in roots]
    found = []
    for pattern in ("*.target", "*.target.gz"):
        # MPFB matches both extensions here, so both are listed in its UI.
        found.extend((str(path), "custom", True) for path in files_matching(roots, pattern))
    return (roots, found)


def scan_user_targets_dir():
    # <user data>/targets/<section>/*.target, the section being the containing
    # directory's basename. MPFB matches only "*.target" here; both extensions
    # are reported, with the difference flagged rather than papered over.
    try:
        directory = as_path(LocationService.get_user_data("targets"))
    except Exception:  # pylint: disable=broad-except
        return ([], [])
    if directory is None or not os.path.isdir(directory):
        return ([], [])
    found = []
    for pattern, listed in (("*.target", True), ("*.target.gz", False)):
        for path in files_matching([directory], pattern):
            full_path = str(path)
            section = str(os.path.basename(os.path.dirname(full_path)))
            found.append((full_path, section, listed))
    return ([directory], found)


def scan_user_targets():
    custom_roots, custom_found = scan_custom_targets()
    targets_roots, targets_found = scan_user_targets_dir()
    seen = set()
    entries = []
    # Deduped by path: the two scans overlap whenever a data root holds both
    # locations, and the same file reported twice would inflate every count.
    # The custom scan comes first, so a file reachable both ways keeps the
    # section MPFB's own custom scan would have given it.
    for found in custom_found + targets_found:
        key = os.path.normpath(found[0])
        if key in seen:
            continue
        seen.add(key)
        entries.append(user_target_entry(found))
    roots = []
    for root in custom_roots + targets_roots:
        if root not in roots:
            roots.append(root)
    return (roots, entries)


def system_section_entries(sections):
    # One entry per section in target.json, with its categories left as MPFB
    # wrote them: the "opposites" table is what tells a caller that setting one
    # target meaningfully means clearing its opposite, and rebuilding it here
    # would only be a chance to get it wrong.
    entries = dict()
    for name, section in (sections or dict()).items():
        if not isinstance(section, dict):
            continue
        categories = section.get("categories") or []
        entries[str(name)] = {
            "label": str(section.get("label") or name),
            "categories": [category for category in categories if isinstance(category, dict)],
        }
    return entries


def category_for_response(category):
    return {
        "name": str(category.get("name") or ""),
        "label": str(category.get("label") or ""),
        "has_left_and_right": bool(category.get("has_left_and_right")),
        "targets": [str(target) for target in (category.get("targets") or [])],
        "opposites": category.get("opposites") or dict(),
    }


def category_matches(category, needle):
    if needle is None:
        return True
    haystacks = [str(category.get("name") or "").lower(), str(category.get("label") or "").lower()]
    for target in category.get("targets") or []:
        haystacks.append(str(target).lower())
    for haystack in haystacks:
        if needle in haystack:
            return True
    return False


def target_matches(entry, needle):
    if needle is None:
        return True
    haystacks = [str(entry["name"]).lower(), str(entry["shapekey_name"] or "").lower()]
    for haystack in haystacks:
        if needle in haystack:
            return True
    return False


requested_section = PARAMS["section"]
name_contains = PARAMS["name_contains"]
limit = PARAMS["limit"]
offset = PARAMS["offset"]

needle = name_contains.strip().lower() if name_contains is not None else None

system_targets_dir = as_path(LocationService.get_mpfb_data("targets"))
target_json_path = None
if system_targets_dir is not None:
    target_json_path = os.path.join(system_targets_dir, "target.json")

# Singular "target.json", inside the "targets" directory. The plural spelling is
# an easy mistake whose failure mode is reporting the index as missing on a
# perfectly good install.
raw_sections, target_json_state = read_target_json(target_json_path)
system_sections = system_section_entries(raw_sections)

user_target_dirs, user_targets = scan_user_targets()

user_counts = dict()
for entry in user_targets:
    user_counts[entry["section"]] = user_counts.get(entry["section"], 0) + 1

# One entry per section *name*, not per source. A user directory can share its
# name with a bundled section - and MPFB's own panel merges the two rather than
# keeping them apart, appending user categories into the existing section - so a
# name present in both is one section with source "both" rather than two
# same-named entries a caller could not tell apart when asking for one.
section_names = sorted(set(list(system_sections.keys()) + list(user_counts.keys())))
sections_overview = []
for name in section_names:
    in_system = name in system_sections
    in_user = name in user_counts
    if in_system and in_user:
        source = "both"
    elif in_system:
        source = "system"
    else:
        source = "user"
    sections_overview.append({
        "name": name,
        "label": system_sections[name]["label"] if in_system else name,
        "source": source,
        "category_count": len(system_sections[name]["categories"]) if in_system else 0,
        "target_count": user_counts.get(name, 0),
    })

known_sections = [entry["name"] for entry in sections_overview]

section_recognized = True
matched_section = None
if requested_section is not None:
    wanted = requested_section.strip().lower()
    for candidate in known_sections:
        if candidate.lower() == wanted:
            matched_section = candidate
    section_recognized = matched_section is not None

# The user targets reported: every one of them, or only the requested section's.
# Note the merge case - asking for a name present in both sources returns that
# section's bundled categories *and* the user targets sitting in the directory
# of the same name.
if matched_section is not None:
    listed_targets = [entry for entry in user_targets if entry["section"] == matched_section]
else:
    listed_targets = list(user_targets)
listed_targets = [entry for entry in listed_targets if target_matches(entry, needle)]
listed_targets.sort(key=lambda entry: (entry["section"], entry["name"].lower(), entry["name"]))

# The categories of the requested section, when it has any. A section that is
# only a user directory has none, which is not the same as having none that
# matched.
categories = None
if matched_section is not None and matched_section in system_sections:
    categories = [
        category_for_response(category)
        for category in system_sections[matched_section]["categories"]
        if category_matches(category, needle)
    ]
    categories.sort(key=lambda category: (category["name"].lower(), category["name"]))

# Whichever list this call is really about is the one that is paged: a system
# section's categories when one was asked for, the user targets otherwise. The
# other list is small by construction and comes back whole.
if categories is not None:
    total_count = len(categories)
    categories = categories[offset:offset + limit]
    count = len(categories)
else:
    total_count = len(listed_targets)
    listed_targets = listed_targets[offset:offset + limit]
    count = len(listed_targets)

indexed_names = sorted(system_sections.keys())
unindexed_system_target_dirs = find_unindexed_dirs(system_targets_dir, indexed_names)

message_parts = []
if requested_section is not None and not section_recognized:
    message_parts.append(
        "No target section called '" + str(requested_section) + "'. See 'known_sections'.")
else:
    if target_json_state == "not_found":
        message_parts.append(
            "No target.json at '" + str(target_json_path) + "', so no bundled sections are "
            "reported; the user target directories were still scanned. ")
    elif target_json_state == "unreadable":
        message_parts.append(
            "target.json at '" + str(target_json_path) + "' could not be parsed, so no bundled "
            "sections are reported; the user target directories were still scanned. ")
    if categories is not None:
        message_parts.append(
            str(total_count) + " categories matched in section '" + str(matched_section)
            + "', " + str(count) + " returned")
    else:
        message_parts.append(
            str(total_count) + " user targets matched, " + str(count) + " returned")
    if total_count > count:
        message_parts.append(" - the rest were not returned, so this is not the whole list")
    message_parts.append(
        ". Set a target by its 'shapekey_name', not by 'name': the two differ for a long name. "
        "The bundled targets are indexed in target.json rather than listed here.")

result = {
    "target_json_path": as_path(target_json_path),
    "target_json_exists": target_json_state == "ok",
    "system_targets_dir": system_targets_dir,
    "sections": sections_overview,
    "categories": categories,
    "user_targets": listed_targets,
    "unindexed_system_target_dirs": unindexed_system_target_dirs,
    "user_target_dirs": user_target_dirs,
    "requested_section": requested_section,
    "section_recognized": section_recognized,
    "known_sections": known_sections,
    "count": count,
    "total_count": total_count,
    # Always present, and the field an agent has to read before concluding a
    # target does not exist: a capped answer must never look like a complete one.
    "truncated": total_count > count,
    "offset": offset,
    "limit": limit,
    "message": "".join(message_parts),
}
