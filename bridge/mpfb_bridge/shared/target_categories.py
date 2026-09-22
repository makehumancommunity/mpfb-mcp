"""
MPFB's modeling **category** table, rebuilt per call rather than at import.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside ``commands/``
and what the ``services`` and ``tables`` arguments are doing there.

A *category* is the thing behind one of MPFB's modeling sliders, and it is not a
``TargetService`` concept at all: it lives in ``target.json`` and in
``mpfb.ui.model._modelsubpanels``. A category names a pair of opposing targets
(``nose-flaring-decr`` / ``nose-flaring-incr``) so that one slider can run from
-1.0 to +1.0, and about a third of them additionally have separate ``l-`` and
``r-`` variants, giving four target files behind one conceptual control. Shape
keys cannot express that on their own: Blender clamps a shape key value to
0.0-1.0, so "flaring -0.4" only exists as "flaring-decr at 0.4, flaring-incr at
0.0".

**This rebuilds what ``_modelsubpanels`` builds at module import time rather
than importing it, and being add-on code does not weaken that rule** -
[never import MPFB submodules directly](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
survives the pivot. The temptation is concrete here, because this add-on runs
inside Blender and *could* simply import that UI module. It must not, and the
second reason is the stronger one: that scan is a snapshot from when Blender
started, so a target installed since would be invisible to a command that
imported it and visible to ``list_targets``, which scans per call.

**That is also why the table is a per-call record rather than module state.**
A module imported once at add-on registration that built it at import would
answer every request from a scan taken at startup - the precise defect the
paragraph above rejects. So :func:`build_tables` returns a :class:`Tables`, a
command builds one per dispatch, and the functions that read it take it as
their first argument.

Two quirks of MPFB's own scan are reproduced deliberately rather than tidied up,
because the point of this table is that a value set through it reads back
correctly on MPFB's own slider:

- A synthesized category's ``name`` is ``basename.replace(".target", "")``,
  which is a *substring* replace and does not strip ``.gz``. So a custom target
  file ``foo.target.gz`` becomes a category named ``foo.gz``, and that is the
  name MPFB loads the shape key under - while
  ``TargetService.filename_to_shapekey_name()``, which is what ``list_targets``
  reports, strips ``.gz`` first and yields ``foo``. Both are recorded here, as
  ``name`` and ``shapekey_name``, and a category where they differ is flagged
  with ``name_diverges_from_catalogue``.
- The user-directory scan matches only ``*.target``, while the custom scan
  matches both extensions. A gzipped target sitting in a user targets directory
  is therefore loadable but absent from MPFB's panels, exactly as
  ``list_targets`` reports through ``listed_in_mpfb_ui``.

The file-extension handling here is deliberately *not* a verbatim copy of
either reference function, because the two disagree:
``_set_simple_modifier_value()`` tries ``<name>.target.gz`` and falls back to
``<name>.target``, while ``_set_opposed_modifier_value()`` builds
``<name>.target.gz`` only and would hand a non-existent path to
``load_target()``, which raises ``IOError``. Every bundled target happens to be
gzipped, so it never bites in practice, but a copy of the opposed function would
inherit a latent crash. :func:`resolve_target_path` tries both, for both kinds
of category.
"""

# The local bindings below are spelled with MPFB's own capitalisation -
# ``LocationService = services["LocationService"]`` - rather than snake_case,
# so that a body here reads the way MPFB's own source reads and can be
# compared with it line for line. That is the whole reason for the disable.
# pylint: disable=invalid-name

__all__ = (
    "CUSTOM_SECTION",
    "MACRODETAILS_DIRECTORY",
    "TARGET_EXTENSIONS",
    "Tables",
    "as_path",
    "build_sections",
    "build_tables",
    "build_target_index",
    "catalogue_shapekey_name",
    "category_is_opposed",
    "category_names_in",
    "category_value_range",
    "files_matching",
    "find_category",
    "find_section",
    "lookup_target",
    "mpfb_category_name",
    "read_target_json",
    "resolve_target_path",
    "scan_custom_categories",
    "scan_user_categories",
    "synthesized_category",
    "target_names_for",
)

import json
import os

# Bundled targets under here are driven by basemesh attributes rather than by
# loading a target file, which is mpfb_set_macro_details' territory. They are
# not in target.json and are never reachable as a category.
MACRODETAILS_DIRECTORY = "macrodetails"

# The name MPFB gives the section it synthesizes from the custom asset roots.
CUSTOM_SECTION = "custom"

TARGET_EXTENSIONS = (".target.gz", ".target")


def as_path(path):
    # Coerce at the point a path enters the table.
    # AssetService.find_asset_files_matching_pattern() returns pathlib.Path
    # objects, and one uncoerced value would fail strict_json on the way out.
    if not path:
        return None
    return str(path)


def mpfb_category_name(full_path):
    """MPFB's own naming: a substring replace that does not strip '.gz'."""
    return str(os.path.basename(str(full_path))).replace(".target", "")


def catalogue_shapekey_name(services, full_path):
    """What mpfb_list_targets reports for the same file, or None.

    Never reimplemented here: filename_to_shapekey_name() strips '.gz' and
    '.target'/'.ptarget' case-insensitively and then encodes a name over 60
    characters to fit Blender's shape key name limit. macrodetail=False is
    passed explicitly, and the argument is keyword-only.
    """
    TargetService = services["TargetService"]
    try:
        return str(TargetService.filename_to_shapekey_name(full_path, macrodetail=False))
    except Exception:  # pylint: disable=broad-except
        # A derivation that fails is reported as missing rather than guessed at.
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


def files_matching(services, roots, pattern):
    AssetService = services["AssetService"]
    try:
        return list(AssetService.find_asset_files_matching_pattern(roots, pattern) or [])
    except Exception:  # pylint: disable=broad-except
        return []


def synthesized_category(services, full_path, listed_in_mpfb_ui):
    """One user or custom target, shaped as the single-target category MPFB makes of it."""
    path = str(full_path)
    name = mpfb_category_name(path)
    shapekey_name = catalogue_shapekey_name(services, path)
    return {
        "has_left_and_right": False,
        "label": name.replace("_", " "),
        "name": name,
        "targets": [path],
        "full_path": path,
        # Not MPFB's own keys - added here so a command can report the two
        # facts a caller cannot otherwise see.
        "shapekey_name": shapekey_name,
        "name_diverges_from_catalogue": shapekey_name is not None and shapekey_name != name,
        "listed_in_mpfb_ui": listed_in_mpfb_ui,
        "source": "user",
    }


def scan_custom_categories(services):
    """The 'custom' section, from every data root's custom/ and targets/custom/."""
    AssetService = services["AssetService"]
    roots = []
    for subdir in (CUSTOM_SECTION, "targets/custom"):
        try:
            roots.extend(AssetService.get_asset_roots(subdir) or [])
        except Exception:  # pylint: disable=broad-except
            continue
    roots = [str(root) for root in roots]
    found = []
    # MPFB matches both extensions here, so both are listed in its UI.
    for pattern in ("*.target", "*.target.gz"):
        found.extend(str(path) for path in files_matching(services, roots, pattern))
    return (roots, found)


def scan_user_categories(services):
    """<user data>/targets/<section>/, the section being the directory's name.

    MPFB matches only '*.target' here. The gzipped ones are collected too and
    flagged, rather than being silently dropped or silently promoted: they are
    on disk and loadable, and mpfb_list_targets already reports them.
    """
    LocationService = services["LocationService"]
    try:
        directory = as_path(LocationService.get_user_data("targets"))
    except Exception:  # pylint: disable=broad-except
        return ([], [])
    if directory is None or not os.path.isdir(directory):
        return ([], [])
    found = []
    for pattern, listed in (("*.target", True), ("*.target.gz", False)):
        for path in files_matching(services, [directory], pattern):
            full_path = str(path)
            section = str(os.path.basename(os.path.dirname(full_path)))
            found.append((full_path, section, listed))
    return ([directory], found)


def build_sections(services):
    """target.json merged with the synthesized custom and user sections."""
    LocationService = services["LocationService"]
    system_targets_dir = as_path(LocationService.get_mpfb_data("targets"))
    target_json_path = None
    if system_targets_dir is not None:
        # Singular "target.json", inside the "targets" directory. The plural
        # spelling reports the index as missing on a perfectly good install.
        target_json_path = os.path.join(system_targets_dir, "target.json")

    raw_sections, state = read_target_json(target_json_path)

    sections = dict()
    for name, section in (raw_sections or dict()).items():
        if not isinstance(section, dict):
            continue
        sections[str(name)] = {
            "label": str(section.get("label") or name),
            "source": "system",
            "categories": [
                category for category in (section.get("categories") or [])
                if isinstance(category, dict) and category.get("name")
            ],
        }

    seen_paths = set()
    scanned_roots = []

    custom_roots, custom_found = scan_custom_categories(services)
    scanned_roots.extend(custom_roots)
    custom_categories = []
    for full_path in custom_found:
        key = os.path.normpath(full_path)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        custom_categories.append(synthesized_category(services, full_path, True))
    if custom_categories:
        # MPFB only creates this section when it found something, and a caller
        # asking for an empty "custom" should get "no such section" rather than
        # an empty list that reads like "installed but nothing matched".
        sections[CUSTOM_SECTION] = {
            "label": "Custom targets",
            "source": "user",
            "categories": custom_categories,
        }

    user_roots, user_found = scan_user_categories(services)
    scanned_roots.extend(user_roots)
    for full_path, section_name, listed in user_found:
        key = os.path.normpath(full_path)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        if section_name not in sections:
            sections[section_name] = {
                "label": section_name,
                "source": "user",
                "categories": [],
            }
        elif sections[section_name]["source"] == "system":
            # MPFB appends user categories into a bundled section of the same
            # name rather than keeping the two apart. mpfb_list_targets calls
            # that section "both"; so does this.
            sections[section_name]["source"] = "both"
        sections[section_name]["categories"].append(
            synthesized_category(services, full_path, listed))

    return (sections, system_targets_dir, target_json_path, state, scanned_roots)




def category_is_opposed(category):
    """True when the category is a pair of opposing targets, as MPFB tests it."""
    return "opposites" in category


def category_value_range(category):
    """The range MPFB's own scene property would carry for this category."""
    if category_is_opposed(category):
        return (-1.0, 1.0)
    return (0.0, 1.0)


def find_section(tables, section_name):
    """Resolve a section name case-insensitively, or None."""
    KNOWN_SECTIONS = tables.known_sections
    if section_name is None:
        return None
    wanted = str(section_name).strip().lower()
    for candidate in KNOWN_SECTIONS:
        if candidate.lower() == wanted:
            return candidate
    return None


def category_names_in(tables, section_name):
    TARGET_SECTIONS = tables.sections
    section = TARGET_SECTIONS.get(section_name)
    if section is None:
        return []
    return sorted(str(category["name"]) for category in section["categories"])


def find_category(tables, section_name, category_name):
    """Resolve a category within a section, case-insensitively, or None.

    Matched on 'name' rather than on 'label': the label is what MPFB's panel
    shows and is not unique across a section for synthesized categories, whose
    label has underscores turned into spaces.
    """
    TARGET_SECTIONS = tables.sections
    section = TARGET_SECTIONS.get(section_name)
    if section is None or category_name is None:
        return None
    wanted = str(category_name).strip().lower()
    for category in section["categories"]:
        if str(category["name"]).lower() == wanted:
            return category
    return None


def target_names_for(category, side, polarity):
    """The target file name this category uses for one side and polarity, or ''.

    For an opposed category that is the opposites table, which names all four
    targets of a sided category explicitly - pairing 'l-foo' with 'r-foo' by
    string manipulation would be a guess. For a simple category it is MPFB's
    own 'l-'/'r-' prefixing, which no bundled category actually exercises (every
    category lacking 'opposites' is unsided) but which is reproduced anyway
    rather than assumed away.
    """
    if category_is_opposed(category):
        return str((category.get("opposites") or dict()).get(polarity + "-" + side) or "")
    if polarity != "positive":
        return ""
    name = str(category["name"])
    if side == "left":
        return "l-" + name
    if side == "right":
        return "r-" + name
    return name


def resolve_target_path(tables, section_name, category, target_name):
    """Where the file for one target of one category is, and how that was decided.

    Returns (path, resolved_by), with resolved_by one of "category_full_path",
    "section_dir" or None. Never TargetService.target_full_path(): that prefers
    an exact basename match but falls back to any file whose name merely starts
    with the requested string, so 'nose-scale-depth' can resolve to
    'nose-scale-depth-decr'. Paths are built explicitly from the category data,
    as MPFB's own panel does.
    """
    SYSTEM_TARGETS_DIR = tables.system_targets_dir
    if not target_name:
        return (None, None)
    if "full_path" in category:
        # A synthesized category carries its own file and has exactly one.
        path = str(category["full_path"])
        if os.path.exists(path):
            return (path, "category_full_path")
        return (None, None)
    if SYSTEM_TARGETS_DIR is None:
        return (None, None)
    for extension in TARGET_EXTENSIONS:
        path = os.path.join(SYSTEM_TARGETS_DIR, section_name, str(target_name) + extension)
        if os.path.exists(path):
            return (path, "section_dir")
    return (None, None)


def build_target_index(tables):
    """Every target this Blender could load, keyed by the name it would take.

    Two keys per bundled target - the target's own name, which is what a
    category refers to and what the shape key is called - and, for a
    synthesized category, both MPFB's category name and the catalogue's
    shapekey_name, since those differ for a gzipped custom target and a caller
    may legitimately hold either.
    """
    TARGET_SECTIONS = tables.sections
    KNOWN_SECTIONS = tables.known_sections
    index = dict()

    def record(key, entry):
        if not key or key in index:
            return
        index[key] = entry

    for section_name in KNOWN_SECTIONS:
        section = TARGET_SECTIONS[section_name]
        for category in section["categories"]:
            if "full_path" in category:
                entry = {
                    "section": section_name,
                    "category": category["name"],
                    "path": str(category["full_path"]),
                    "resolved_by": "category_full_path",
                    "side": "unsided",
                    "polarity": "positive",
                    # A category MPFB synthesized from a file on disk, so it is
                    # a modifier MPFB's panel shows but target.json never
                    # mentions.
                    "synthesized": True,
                }
                record(str(category["name"]), entry)
                record(category.get("shapekey_name"), entry)
                continue
            for side in ("unsided", "left", "right"):
                for polarity in ("positive", "negative"):
                    target_name = target_names_for(category, side, polarity)
                    if not target_name:
                        continue
                    path, resolved_by = resolve_target_path(
                        tables, section_name, category, target_name)
                    record(target_name, {
                        "section": section_name,
                        "category": category["name"],
                        "path": path,
                        "resolved_by": resolved_by,
                        "side": side,
                        "polarity": polarity,
                        "synthesized": False,
                    })
    return index


def lookup_target(services, tables, target_name):
    """One target by the name a shape key would carry, or None.

    Falls back to TargetService.target_full_path() only when the table above
    knows nothing - which is how an unindexed bundled directory such as 'asym'
    stays reachable at the raw level. The fallback's prefix matching is why the
    resolved path is reported back rather than merely used.
    """
    TargetService = services["TargetService"]
    TARGET_INDEX = tables.index
    if not target_name:
        return None
    found = TARGET_INDEX.get(str(target_name))
    if found is not None:
        return found
    try:
        path = TargetService.target_full_path(str(target_name))
    except Exception:  # pylint: disable=broad-except
        path = None
    if not path:
        return None
    return {
        "section": None,
        "category": None,
        "path": str(path),
        "resolved_by": "target_full_path",
        "side": None,
        "polarity": None,
        "synthesized": False,
    }


class Tables:
    """One scan of this Blender's target directories, built per dispatched command.

    Seven fields - ``sections``, ``system_targets_dir``, ``target_json_path``,
    ``target_json_state``, ``scanned_roots``, ``known_sections`` and ``index``.
    A command builds one and hands it to every
    function below that needs it; nothing here is cached between calls, which is
    what keeps a target installed since Blender started visible.
    """

    __slots__ = ("sections", "system_targets_dir", "target_json_path", "target_json_state",
                 "scanned_roots", "known_sections", "index")

    def __init__(self, sections, system_targets_dir, target_json_path,
                 target_json_state, scanned_roots):
        self.sections = sections
        self.system_targets_dir = system_targets_dir
        self.target_json_path = target_json_path
        self.target_json_state = target_json_state
        self.scanned_roots = scanned_roots
        self.known_sections = sorted(sections.keys())
        # Filled in by build_tables(), because building it needs the record.
        self.index = dict()


def build_tables(services):
    """Scan the target directories and index what was found. One per call.

    Two phases because the index is built *from* the table:
    :func:`build_target_index` reads ``sections`` and ``known_sections``, which
    is why the record exists before the index does.
    """
    tables = Tables(*build_sections(services))
    tables.index = build_target_index(tables)
    return tables
