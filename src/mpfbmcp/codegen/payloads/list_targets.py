"""
Payload for ``mpfb_list_targets``: which modeling targets this Blender could set.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap and the
``target_categories.py`` shared fragment (see ``mpfbmcp.codegen.assemble``, and
``mpfbmcp.target_table``, which is what assembles this one). A linter will flag
as undefined both the assembler-bound names - ``PARAMS`` (``section``,
``name_contains``, ``limit``, ``offset``) and ``sys`` - and the fragment-bound
ones: ``TARGET_SECTIONS``, ``SYSTEM_TARGETS_DIR``, ``TARGET_JSON_PATH``,
``TARGET_JSON_STATE``, ``SCANNED_TARGET_ROOTS``, ``MACRODETAILS_DIRECTORY``
and ``as_path``.

The field this exists for is ``shapekey_name``. A target is addressed by the
name of the shape key it becomes, which is derived from its filename by
``TargetService.filename_to_shapekey_name()`` - and that derivation is not the
identity function, since a name over 60 characters is *encoded* to fit Blender's
shape key name limit. Reporting the filename alone would hand the caller
something that silently addresses nothing.

Two sources, genuinely different in kind. ``target.json`` is a curated index of
the bundled targets, too large to return and exactly the sort of file a caller
can read for itself, so its *path* is reported and its sections are browsable
one at a time. The user data directories have no index at all: they are scanned,
which makes this deliberately more current than MPFB's own modeling panels -
those scan at module import time and so only ever see what existed when Blender
started.

**The scan is the fragment's, not this payload's.** It used to be written out
here a second time, by a different route than
``codegen/shared/target_categories.py`` took, which was two chances to disagree
about what is installed. What the fragment produces is a *category* table, and
what this tool reports is a flat listing of user target files; the reconciliation
is that a synthesized category is exactly one user target file, so the listing
below is the fragment's synthesized categories turned back into files, and the
bundled sections are the ones it did not synthesize. Two consequences are worth
knowing: the ``custom`` section is now labelled as MPFB labels it ("Custom
targets") rather than by its directory name, and a ``target.json`` category with
no ``name`` is dropped rather than listed, since it could not be addressed.

Nothing is loaded into the scene and no MPFB cache is populated: this is a
handful of directory walks and one JSON read, done on every call. What is
cached between calls is the fragment's *source*, not its answer, so this stays
as current as it was when it did its own scanning.
"""

import os

# Whether a directory below the bundled targets directory is one target.json
# never mentions is answered by walking it, and that walk is this payload's
# alone: nothing else needs it, so it is not in the fragment and is not cached.
TARGET_EXTENSIONS_FOR_COUNTING = (".target", ".target.gz")


def is_target_file(filename):
    lowered = str(filename).lower()
    for extension in TARGET_EXTENSIONS_FOR_COUNTING:
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
    # The display name only, and deliberately not MPFB's own category naming,
    # which is a substring replace that leaves ".gz" behind. The *addressable*
    # name is shapekey_name, which comes from MPFB rather than from here.
    name = str(basename)
    if name.lower().endswith(".target.gz"):
        return name[:-len(".target.gz")]
    if name.lower().endswith(".target"):
        return name[:-len(".target")]
    return name


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


def is_synthesized(category):
    # The fragment's marker for "MPFB made this category out of one file on
    # disk", which is precisely a user target rather than a bundled one.
    return "full_path" in category


def user_target_entry(section_name, category):
    """One synthesized category, reported as the target file it was made from."""
    full_path = str(category["full_path"])
    basename = os.path.basename(full_path)
    return {
        "name": strip_target_extension(basename),
        "shapekey_name": category.get("shapekey_name"),
        "path": as_path(full_path),
        "section": section_name,
        "file_type": target_file_type(basename),
        # False is a real MPFB scan asymmetry rather than anything decided here:
        # its user-targets scan matches only "*.target", so a gzipped target in
        # a user targets directory is on disk, loadable, and invisible in MPFB's
        # own modeling panels.
        "listed_in_mpfb_ui": bool(category.get("listed_in_mpfb_ui")),
    }


def category_for_response(category):
    # The "opposites" table is what tells a caller that setting one target
    # meaningfully means clearing its opposite, and is passed through as MPFB
    # wrote it rather than rebuilt.
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

# The fragment's merged table, split back into the two kinds this tool reports.
# One entry per section *name*, not per source: a user directory can share its
# name with a bundled section, and MPFB's own panel merges the two rather than
# keeping them apart, which is what the fragment's "both" records.
bundled_categories = dict()
user_targets = []
for section_name in sorted(TARGET_SECTIONS.keys()):
    section = TARGET_SECTIONS[section_name]
    bundled_categories[section_name] = [
        category for category in section["categories"] if not is_synthesized(category)]
    for category in section["categories"]:
        if is_synthesized(category):
            user_targets.append(user_target_entry(section_name, category))

sections_overview = []
for section_name in sorted(TARGET_SECTIONS.keys()):
    section = TARGET_SECTIONS[section_name]
    sections_overview.append({
        "name": section_name,
        "label": section["label"],
        "source": section["source"],
        "category_count": len(bundled_categories[section_name]),
        "target_count": sum(1 for entry in user_targets if entry["section"] == section_name),
    })

known_sections = [entry["name"] for entry in sections_overview]
# The sections target.json itself carries, whether or not a user directory of
# the same name was merged into them. A bundled section with no categories at
# all - "measure" is one - still answers "that section has no matches" rather
# than falling through to the user-target listing.
bundled_section_names = [entry["name"] for entry in sections_overview
                         if entry["source"] in ("system", "both")]

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
if matched_section is not None and matched_section in bundled_section_names:
    categories = [
        category_for_response(category)
        for category in bundled_categories[matched_section]
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

unindexed_system_target_dirs = find_unindexed_dirs(SYSTEM_TARGETS_DIR, bundled_section_names)

message_parts = []
if requested_section is not None and not section_recognized:
    message_parts.append(
        "No target section called '" + str(requested_section) + "'. See 'known_sections'.")
else:
    if TARGET_JSON_STATE == "not_found":
        message_parts.append(
            "No target.json at '" + str(TARGET_JSON_PATH) + "', so no bundled sections are "
            "reported; the user target directories were still scanned. ")
    elif TARGET_JSON_STATE == "unreadable":
        message_parts.append(
            "target.json at '" + str(TARGET_JSON_PATH) + "' could not be parsed, so no bundled "
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
    "target_json_path": TARGET_JSON_PATH,
    "target_json_exists": TARGET_JSON_STATE == "ok",
    "system_targets_dir": SYSTEM_TARGETS_DIR,
    "sections": sections_overview,
    "categories": categories,
    "user_targets": listed_targets,
    "unindexed_system_target_dirs": unindexed_system_target_dirs,
    "user_target_dirs": SCANNED_TARGET_ROOTS,
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
