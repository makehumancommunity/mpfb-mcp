"""
What a file this add-on writes by name may be called.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/``.

Three artifacts are addressed by a name that becomes a filename in a directory
nobody on the far side of the socket chose: a character preset
(``<user config>/human.<name>.json``, written by ``save_preset`` and read by
``create_human_from_preset``), a saved expression
(``<user data>/expressions/<name>.json``, written by ``save_expression``) and,
since [FR 039](../../../feature-requests/done/039-exporting-characters/README.md),
an export (``<export directory>/<name>.<fbx|glb|usdz>``, written by
``export_character`` into the directory the bridge's user set). The rule for
which characters such a name may hold is the same for all three, because the
reason is the same - a name carrying ``/``, ``\\`` or ``..`` would escape the
directory - so it lives here once, with the noun the refusal names as its only
argument. What stays per artifact is the path, in ``preset_files.py``,
``save_expression`` and ``export_character`` respectively.
[FR 027](../../../feature-requests/done/027-expression-library/README.md) moved
it here out of ``preset_files.py`` rather than copying it into a second module.

The rule is a **whitelist**, and it is deliberately stricter than MPFB's.
``savenewpresets.py`` rejects only an empty name and one containing a space; the
expression composer's save operator rejects only ``/``, ``\\``, ``.`` and ``..``.
Strictness runs one way only: every name accepted here is one MPFB's own panels
would also accept, so the two never disagree about what exists.

**This is the second copy of that rule and that is deliberate.**
``mpfbmcp.artifact_names`` carries it on the far side of the socket, where the
authoritative check runs before anything is sent. This copy is **the last
statement before ``open()``**, and it is here because a listening socket is
reachable by anything on this machine, not only by mpfb-mcp. The two are run
over one table of names and all three nouns by ``tests/test_save_preset.py``, which
executes this file's source directly - so it imports nothing but the standard
library.

It also holds the two ``os.stat`` helpers that report what is already at such
a path - the ``file_before`` all three writing commands refuse and report with -
because "what is there" is the other half of "what may it be called". Reads
nothing out of MPFB, so like ``performed`` it takes no ``services``.
"""

__all__ = (
    "NAME_MAX_LENGTH",
    "NAME_PATTERN",
    "file_facts",
    "modified_iso",
    "name_rejection",
)

import datetime
import os
import re

# Long enough for any name a human types, short enough that the assembled path
# cannot be the reason a write fails on a filesystem with a name limit.
NAME_MAX_LENGTH = 64

# Letters, digits, underscore, hyphen, dot. Everything a path separator could be
# made of is outside it, on every platform, which is what makes the escape
# unreachable rather than merely unlikely.
NAME_PATTERN = "^[A-Za-z0-9_.-]+$"


def name_rejection(name, noun):
    """Why this name may not become a ``noun`` file, as a sentence, or None.

    A sentence rather than a bool: every caller of this puts the answer straight
    into a refusal, and "invalid" on its own tells an agent nothing about which
    character to drop.
    """
    if not isinstance(name, str):
        return "A {:s} name must be a string, not {:s}.".format(noun, type(name).__name__)
    if not name:
        return "A {:s} name must not be empty.".format(noun)
    if len(name) > NAME_MAX_LENGTH:
        return "A {:s} name must be at most {:d} characters; this one is {:d}.".format(
            noun, NAME_MAX_LENGTH, len(name))
    if name in (".", ".."):
        return "'{:s}' names a directory rather than a {:s}.".format(name, noun)
    if name.startswith("."):
        return "A {:s} name must not start with a dot.".format(noun)
    if re.match(NAME_PATTERN, name) is None:
        # Named individually: an agent that built the name by joining a
        # character's display name will otherwise retry with the same space.
        illegal = sorted(set(
            character for character in name
            if re.match(NAME_PATTERN, character) is None))
        return ("A {:s} name may hold only letters, digits, '_', '-' and '.', so that it "
                "cannot become a path. This one also holds: {:s}.".format(
                    noun, ", ".join(repr(character) for character in illegal)))
    return None


def modified_iso(mtime):
    """An mtime as local-time ISO 8601 with an offset, or None.

    With the offset rather than as a bare timestamp: a file's age is the
    reason a caller reads this field at all, and a naive local time is a claim
    nobody can check against their own clock.
    """
    try:
        moment = datetime.datetime.fromtimestamp(mtime).astimezone()
    except (OverflowError, OSError, ValueError):
        return None
    return moment.isoformat(timespec="seconds")


def file_facts(path):
    """``os.stat`` facts about one file written by name, as a dict.

    Every field here is **derived from the filesystem**, not recorded by MPFB
    and not read out of the JSON: MPFB's own lists are bare names and know
    nothing about size or age. This is the ``file_before`` shape both
    ``save_preset`` and ``save_expression`` refuse and report with.
    ``exists: false`` is an ordinary answer - MPFB's cached preset list can
    name a preset whose file has since been deleted.
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
