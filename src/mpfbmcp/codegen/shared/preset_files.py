"""
Shared fragment: where a preset lives, what it may be called, and what is there.

Not a module of this package - this file is never imported here. It is read as
a resource and concatenated ahead of a payload (see ``mpfbmcp.codegen.assemble``
and its ``shared`` argument), on top of the raising bootstrap. A linter will
flag two names as undefined because the assembler binds them ahead of this file:

- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap (unused here, but bound).

This exists because three payloads have to agree about two things, and the
second of them is a filesystem.

**Which characters may appear in a preset name.** ``mpfb_save_preset`` decides
whether a name may become a file and ``mpfb_create_human_from_preset`` decides
whether a name may be looked up; if the two ever disagree, a preset can be
written under a name that cannot be loaded back, which is the worst shape this
effort could take. ``mpfb_list_presets`` needs the same rule from the other
direction - it reports what MPFB lists, and MPFB's own panel accepts names this
package will not, so a listed preset can be one the load tool refuses. It says
so per entry (``addressable``) rather than leaving the caller to find out.

**Where the file is and how the name becomes one.** All three build
``<user config>/human.<name>.json``, which is the namespace MPFB's own panels
read and write. A second namespace would be two lists that disagree.

The rule itself is a **whitelist**, and it is deliberately stricter than MPFB's.
``savenewpresets.py`` rejects only an empty name and one containing a space; it
does not reject ``/``, ``\\``, ``..`` or a leading dot, and
``os.path.join(confdir, "human." + name + ".json")`` will happily escape the
config directory with any of them. Strictness runs one way only: every name
accepted here is one MPFB's panel would also accept, so the two never disagree
about what exists. The space is rejected for exactly that reason rather than
because a space in a filename is a problem.

``mpfbmcp.preset_names`` carries the same rule for the tool side of the socket,
where requirement 8 puts the authoritative check - a name that becomes a path is
a *shape*, and it is knowable before the program is built. This copy is not
redundancy for its own sake: it is the last statement before ``open()``, and
``tests/test_codegen.py`` runs the two implementations over one table of names
so they cannot drift.

Nothing here writes anything, creates a directory or populates an MPFB cache.
``update_list_of_human_presets()`` does a bare ``os.listdir(confdir)``, so a
missing config directory would raise from inside MPFB; on a working install it
cannot be missing - ``LocationService`` calls
``ensure_relevant_directories_exist()`` at import time, and the user config
directory is on that list - but it is guarded rather than assumed, because a
broken install is one of the things a tool is for reporting.
"""

import datetime
import fnmatch
import os
import re

LocationService = _MPFB_SERVICES["LocationService"]
HumanService = _MPFB_SERVICES["HumanService"]

PRESET_PREFIX = "human."
PRESET_SUFFIX = ".json"

# Long enough for any name a human types, short enough that the assembled path
# cannot be the reason a write fails on a filesystem with a name limit.
PRESET_NAME_MAX_LENGTH = 64

# Letters, digits, underscore, hyphen, dot. Everything a path separator could be
# made of is outside it, on every platform, which is what makes the escape
# unreachable rather than merely unlikely.
PRESET_NAME_PATTERN = "^[A-Za-z0-9_.-]+$"


def preset_name_rejection(name):
    """Why this name may not become a preset file, as a sentence, or None.

    A sentence rather than a bool: every caller of this puts the answer straight
    into a refusal, and "invalid" on its own tells an agent nothing about which
    character to drop.
    """
    if not isinstance(name, str):
        return "A preset name must be a string, not " + type(name).__name__ + "."
    if not name:
        return "A preset name must not be empty."
    if len(name) > PRESET_NAME_MAX_LENGTH:
        return ("A preset name must be at most " + str(PRESET_NAME_MAX_LENGTH)
                + " characters; this one is " + str(len(name)) + ".")
    if name in (".", ".."):
        return "'" + name + "' names a directory rather than a preset."
    if name.startswith("."):
        return "A preset name must not start with a dot."
    if re.match(PRESET_NAME_PATTERN, name) is None:
        # Named individually: an agent that built the name by joining a
        # character's display name will otherwise retry with the same space.
        illegal = sorted(set(
            character for character in name
            if re.match(PRESET_NAME_PATTERN, character) is None))
        return ("A preset name may hold only letters, digits, '_', '-' and '.', so that it "
                "cannot become a path. This one also holds: "
                + ", ".join(repr(character) for character in illegal) + ".")
    return None


def config_directory():
    """MPFB's user config directory, where every preset lives, or None.

    Coerced with ``str()`` at the point it enters a response: MPFB's path
    getters are annotated as returning ``str`` and do not always do so, and a
    ``pathlib.Path`` fails ``strict_json`` and takes the whole response down
    with it.
    """
    try:
        confdir = LocationService.get_user_config()
    except Exception:  # pylint: disable=broad-except
        return None
    if not confdir:
        return None
    return str(confdir)


def preset_filename(name):
    """``human.<name>.json`` - the filename, with no directory in front of it."""
    return PRESET_PREFIX + str(name) + PRESET_SUFFIX


def preset_path(confdir, name):
    """The absolute file a name addresses, or None when there is no directory.

    Callers check ``preset_name_rejection()`` first. This does not, because the
    two answers are reported separately: a bad name is a refusal about the
    argument, and a missing config directory is a refusal about the install.
    """
    if confdir is None:
        return None
    return os.path.join(confdir, preset_filename(name))


def name_from_filename(filename):
    """The ``<name>`` in ``human.<name>.json``, or None if this is not one.

    Reproduces ``update_list_of_human_presets()``'s own two-step match - an
    ``fnmatch`` against ``human.*.json`` and then a regex whose group must be
    non-empty - rather than a simplification of it, so that a file this reports
    is a file MPFB would report too. Note what the pair excludes: ``human.json``
    (nothing between the dots), ``humans.foo.json`` (wrong prefix) and
    ``human.foo.json.bak`` (wrong suffix), all three of which really do turn up
    in a config directory that has been used.
    """
    if not fnmatch.fnmatch(filename, PRESET_PREFIX + "*" + PRESET_SUFFIX):
        return None
    # MPFB's own regex, unescaped dots included: the dots match themselves in
    # every filename this can be reached with, and repairing it here would make
    # this report a name MPFB's list does not hold.
    match = re.search(r'^human.(.*).json$', filename)
    if match and match.group(1):
        return match.group(1)
    return None


def scan_preset_names(confdir):
    """Every preset name on disk right now, sorted, without touching MPFB.

    The counterpart to ``mpfb_presets()`` below, and the reason both exist: that
    function answers from a module global MPFB never invalidates, so the two
    disagree exactly when a preset has been written or deleted since anything
    last scanned. ``mpfb_list_presets`` reports the difference rather than
    hiding it behind a ``refresh`` the caller has no reason to pass.
    """
    if confdir is None or not os.path.isdir(confdir):
        return []
    try:
        filenames = os.listdir(confdir)
    except OSError:
        return []
    names = []
    for filename in filenames:
        name = name_from_filename(filename)
        if name is not None:
            names.append(name)
    names.sort()
    return names


def mpfb_presets(refresh):
    """``HumanService.get_list_of_human_presets()``, as names, copied.

    Copied deliberately: that function hands back the module-level
    ``_EXISTING_PRESETS`` list itself, so anything sorting or filtering the
    answer in place would be editing MPFB's own state - and it is the same list
    MPFB's preset dropdown is built from.

    ``use_cache=False`` is what ``refresh`` selects. The cache is populated on
    first use and invalidated by nothing except a save, so on a Blender that has
    been open for a while it can be arbitrarily old.
    """
    names = HumanService.get_list_of_human_presets(as_list_enum=False, use_cache=not refresh)
    return list(names or [])


def modified_iso(mtime):
    """An mtime as local-time ISO 8601 with an offset, or None.

    With the offset rather than as a bare timestamp: a preset's age is the
    reason a caller reads this field at all, and a naive local time is a claim
    nobody can check against their own clock.
    """
    try:
        moment = datetime.datetime.fromtimestamp(mtime).astimezone()
    except (OverflowError, OSError, ValueError):
        return None
    return moment.isoformat(timespec="seconds")


def file_facts(path):
    """``os.stat`` facts about one preset file, as a dict.

    Every field here is **derived from the filesystem**, not recorded by MPFB
    and not read out of the JSON: MPFB's own list is bare names and knows
    nothing about size or age. ``exists: false`` is an ordinary answer - MPFB's
    cached list can name a preset whose file has since been deleted.
    """
    facts = dict(exists=False, size_bytes=None, modified=None)
    if path is None:
        return facts
    try:
        stat = os.stat(path)
    except OSError:
        return facts
    facts["exists"] = True
    facts["size_bytes"] = int(stat.st_size)
    facts["modified"] = modified_iso(stat.st_mtime)
    return facts


def preset_record(confdir, name):
    """One catalogue entry: the identifier, the file, and whether it is usable.

    ``addressable`` is the field that keeps this tool from contradicting the
    other two. MPFB's panel accepts names this package refuses, so a preset a
    user saved by hand can be listed here and refused by
    ``mpfb_create_human_from_preset`` - which is a surprise worth having in the
    listing rather than in the refusal.
    """
    path = preset_path(confdir, name)
    rejection = preset_name_rejection(name)
    record = dict(
        name=name,
        path=path,
        addressable=rejection is None,
        not_addressable_reason=rejection,
    )
    record.update(file_facts(path))
    return record
