"""
``list_targets``: which modeling targets this Blender could set, and by what name.

**The field this exists for is ``shapekey_name``.** A target is addressed by the
name of the shape key it becomes, which is derived from its filename by
``TargetService.filename_to_shapekey_name()`` - and that derivation is not the
identity function, since a name over 60 characters is *encoded* to fit Blender's
shape key name limit. Reporting the filename alone would hand the caller
something that silently addresses nothing.

Two sources, genuinely different in kind. ``target.json`` is a curated index of
the bundled targets, too large to return and exactly the sort of file a caller
can read for itself, so its *path* is reported and its sections are browsable
one at a time. The user data directories have no index at all: they are
scanned, which makes this deliberately more current than MPFB's own modeling
panels - those scan at module import time and so only ever see what existed when
Blender started.

**The scan is [`shared/target_categories.py`](../shared/target_categories.py)'s,
not this command's**, and that module builds its table **per call** for exactly
the reason above. What it produces is a *category* table and what this reports
is a flat listing of user target files; the reconciliation is that a synthesized
category is exactly one user target file, so the listing below is its
synthesized categories turned back into files, and the bundled sections are the
ones it did not synthesize. Two consequences are worth knowing: the ``custom``
section is labelled as MPFB labels it ("Custom targets") rather than by its
directory name, and a ``target.json`` category with no ``name`` is dropped
rather than listed, since it could not be addressed.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
, including the two things about it that look inconsistent:

- **Which list is paged depends on what was asked.** A bundled section's
  categories when one was named, the user targets otherwise. The other list is
  small by construction and comes back whole.
- **``listed_in_mpfb_ui: false`` is MPFB's asymmetry, not a judgement here.**
  Its user-targets scan matches only ``*.target``, so a gzipped target in a user
  targets directory is on disk, loadable, and invisible in MPFB's own panels.

Nothing is loaded into the scene and no MPFB cache is populated: a handful of
directory walks and one JSON read, on every call. This is the one command in
the package that is genuinely side-effect free.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_targets",
)

import os

from ..log import get_logger
from ..shared import target_categories
from ..validation import Param
from ..validation import TYPE_INTEGER
from ..validation import TYPE_STRING

_LOG = get_logger("commands.listtargets")

PARAMS = (
    Param("section", TYPE_STRING, default=None, nullable=True,
          description="One target section, matched exactly and case-insensitively. Omit for "
                      "the overview of every section."),
    Param("name_contains", TYPE_STRING, default=None, nullable=True,
          description="Case-insensitive substring matched against names, labels and the "
                      "target files a category names."),
    Param("limit", TYPE_INTEGER, default=200, minimum=0, maximum=1000,
          description="How many entries to return. The answer always says whether it was cut."),
    Param("offset", TYPE_INTEGER, default=0, minimum=0,
          description="How many matching entries to skip."),
)

SUMMARY = "List the modeling target sections, categories and user targets, with addressable names."

# Whether a directory below the bundled targets directory is one target.json
# never mentions is answered by walking it, and that walk is this command's
# alone: nothing else needs it, so it is not in the shared module.
TARGET_EXTENSIONS_FOR_COUNTING = (".target", ".target.gz")


def _is_target_file(filename):
    lowered = str(filename).lower()
    for extension in TARGET_EXTENSIONS_FOR_COUNTING:
        if lowered.endswith(extension):
            return True
    return False


def _target_file_type(filename):
    """"target.gz" rather than "gz": the pair MPFB's user scan discriminates on."""
    if str(filename).lower().endswith(".target.gz"):
        return "target.gz"
    return "target"


def _strip_target_extension(basename):
    """The display name only, and deliberately not MPFB's own category naming.

    That naming is a substring replace which leaves ``.gz`` behind. The
    *addressable* name is ``shapekey_name``, which comes from MPFB rather than
    from here.
    """
    name = str(basename)
    if name.lower().endswith(".target.gz"):
        return name[:-len(".target.gz")]
    if name.lower().endswith(".target"):
        return name[:-len(".target")]
    return name


def _count_targets_below(directory):
    total = 0
    for _root, _dirs, files in os.walk(directory):
        for filename in files:
            if _is_target_file(filename):
                total = total + 1
    return total


def _find_unindexed_dirs(system_targets_dir, indexed_names):
    """Bundled target directories ``target.json`` never mentions.

    Diffed, never hardcoded: ``target.json`` has 22 sections while the directory
    holds more, and a pair named here would drift the moment MPFB adds a
    directory. Directories holding no target file at all (``_images``) drop out
    by the count rather than by a name check.
    """
    if not system_targets_dir or not os.path.isdir(system_targets_dir):
        return []
    unindexed = []
    try:
        entries = sorted(os.listdir(system_targets_dir))
    except Exception:  # pylint: disable=broad-except
        return []
    for entry in entries:
        if entry in indexed_names or entry == target_categories.MACRODETAILS_DIRECTORY:
            continue
        directory = os.path.join(system_targets_dir, entry)
        if not os.path.isdir(directory):
            continue
        count = _count_targets_below(directory)
        if count < 1:
            continue
        unindexed.append({
            "name": entry,
            "path": target_categories.as_path(directory),
            "target_count": count,
        })
    return unindexed


def _is_synthesized(category):
    """The shared module's marker for "MPFB made this out of one file on disk"."""
    return "full_path" in category


def _user_target_entry(section_name, category):
    """One synthesized category, reported as the target file it was made from."""
    full_path = str(category["full_path"])
    basename = os.path.basename(full_path)
    return {
        "name": _strip_target_extension(basename),
        "shapekey_name": category.get("shapekey_name"),
        "path": target_categories.as_path(full_path),
        "section": section_name,
        "file_type": _target_file_type(basename),
        # False is a real MPFB scan asymmetry rather than anything decided here
        # - see this module's docstring.
        "listed_in_mpfb_ui": bool(category.get("listed_in_mpfb_ui")),
    }


def _category_for_response(category):
    """One bundled category, passed through as MPFB wrote it.

    The ``opposites`` table is what tells a caller that setting one target
    meaningfully means clearing its opposite, so it is passed through rather
    than rebuilt.
    """
    return {
        "name": str(category.get("name") or ""),
        "label": str(category.get("label") or ""),
        "has_left_and_right": bool(category.get("has_left_and_right")),
        "targets": [str(target) for target in (category.get("targets") or [])],
        "opposites": category.get("opposites") or dict(),
    }


def _category_matches(category, needle):
    if needle is None:
        return True
    haystacks = [str(category.get("name") or "").lower(),
                 str(category.get("label") or "").lower()]
    for target in category.get("targets") or []:
        haystacks.append(str(target).lower())
    for haystack in haystacks:
        if needle in haystack:
            return True
    return False


def _target_matches(entry, needle):
    if needle is None:
        return True
    haystacks = [str(entry["name"]).lower(), str(entry["shapekey_name"] or "").lower()]
    for haystack in haystacks:
        if needle in haystack:
            return True
    return False


def _split(tables):
    """The merged category table, split back into the two kinds this reports.

    One entry per section *name*, not per source: a user directory can share its
    name with a bundled section, and MPFB's own panel merges the two rather than
    keeping them apart - which is what the shared module's ``"both"`` records.
    """
    bundled_categories = dict()
    user_targets = []
    for section_name in tables.known_sections:
        section = tables.sections[section_name]
        bundled_categories[section_name] = [
            category for category in section["categories"] if not _is_synthesized(category)]
        for category in section["categories"]:
            if _is_synthesized(category):
                user_targets.append(_user_target_entry(section_name, category))
    return (bundled_categories, user_targets)


def _overview(tables, bundled_categories, user_targets):
    sections_overview = []
    for section_name in tables.known_sections:
        section = tables.sections[section_name]
        sections_overview.append({
            "name": section_name,
            "label": section["label"],
            "source": section["source"],
            "category_count": len(bundled_categories[section_name]),
            "target_count": sum(
                1 for entry in user_targets if entry["section"] == section_name),
        })
    return sections_overview


def _message(tables, requested_section, section_recognized, matched_section,
             categories, total_count, count):
    parts = []
    if requested_section is not None and not section_recognized:
        parts.append("No target section called '{:s}'. See 'known_sections'.".format(
            str(requested_section)))
        return "".join(parts)

    if tables.target_json_state == "not_found":
        parts.append(
            "No target.json at '{:s}', so no bundled sections are reported; the user target "
            "directories were still scanned. ".format(str(tables.target_json_path)))
    elif tables.target_json_state == "unreadable":
        parts.append(
            "target.json at '{:s}' could not be parsed, so no bundled sections are reported; "
            "the user target directories were still scanned. ".format(
                str(tables.target_json_path)))
    if categories is not None:
        parts.append("{:d} categories matched in section '{:s}', {:d} returned".format(
            total_count, str(matched_section), count))
    else:
        parts.append("{:d} user targets matched, {:d} returned".format(total_count, count))
    if total_count > count:
        parts.append(" - the rest were not returned, so this is not the whole list")
    parts.append(
        ". Set a target by its 'shapekey_name', not by 'name': the two differ for a long name. "
        "The bundled targets are indexed in target.json rather than listed here.")
    return "".join(parts)


def list_targets(params, resolution):  # pylint: disable=too-many-locals
    """Catalogue the target sections, one section's categories, and the user targets."""
    tables = target_categories.build_tables(resolution.services)

    requested_section = params["section"]
    name_contains = params["name_contains"]
    limit = params["limit"]
    offset = params["offset"]
    needle = name_contains.strip().lower() if name_contains is not None else None

    bundled_categories, user_targets = _split(tables)
    sections_overview = _overview(tables, bundled_categories, user_targets)

    known_sections = [entry["name"] for entry in sections_overview]
    # The sections target.json itself carries, whether or not a user directory
    # of the same name was merged into them. A bundled section with no
    # categories at all - "measure" is one - still answers "that section has no
    # matches" rather than falling through to the user-target listing.
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

    # Note the merge case - asking for a name present in both sources returns
    # that section's bundled categories *and* the user targets sitting in the
    # directory of the same name.
    if matched_section is not None:
        listed_targets = [entry for entry in user_targets
                          if entry["section"] == matched_section]
    else:
        listed_targets = list(user_targets)
    listed_targets = [entry for entry in listed_targets if _target_matches(entry, needle)]
    listed_targets.sort(key=lambda entry: (entry["section"], entry["name"].lower(),
                                           entry["name"]))

    # The categories of the requested section, when it has any. A section that
    # is only a user directory has none, which is not the same as having none
    # that matched.
    categories = None
    if matched_section is not None and matched_section in bundled_section_names:
        categories = [
            _category_for_response(category)
            for category in bundled_categories[matched_section]
            if _category_matches(category, needle)
        ]
        categories.sort(key=lambda category: (category["name"].lower(), category["name"]))

    # Whichever list this call is really about is the one that is paged.
    if categories is not None:
        total_count = len(categories)
        categories = categories[offset:offset + limit]
        count = len(categories)
    else:
        total_count = len(listed_targets)
        listed_targets = listed_targets[offset:offset + limit]
        count = len(listed_targets)

    unindexed = _find_unindexed_dirs(tables.system_targets_dir, bundled_section_names)

    _LOG.debug("list_targets: %d sections, %d user targets, %d returned",
               len(sections_overview), len(user_targets), count)

    return {
        "target_json_path": tables.target_json_path,
        "target_json_exists": tables.target_json_state == "ok",
        "system_targets_dir": tables.system_targets_dir,
        "sections": sections_overview,
        "categories": categories,
        "user_targets": listed_targets,
        "unindexed_system_target_dirs": unindexed,
        "user_target_dirs": tables.scanned_roots,
        "requested_section": requested_section,
        "section_recognized": section_recognized,
        "known_sections": known_sections,
        "count": count,
        "total_count": total_count,
        # Always present, and the field an agent has to read before concluding a
        # target does not exist: a capped answer must never look like a complete
        # one.
        "truncated": total_count > count,
        "offset": offset,
        "limit": limit,
        "message": _message(tables, requested_section, section_recognized, matched_section,
                            categories, total_count, count),
    }
