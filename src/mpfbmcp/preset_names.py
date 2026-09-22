"""
What a preset may be called, checked before the program is built.

The one argument in this package that becomes a **path**. ``mpfb_save_preset``
and ``mpfb_create_human_from_preset`` both take ``name`` and both resolve it to
``<user config>/human.<name>.json``, so a name carrying ``/``, ``\\`` or ``..``
would address a file outside the directory MPFB owns - and on the saving side it
would *write* one. That is a shape rather than a vocabulary, it is entirely
knowable on this side of the socket, and the consequence of getting it wrong is
a file somewhere nobody will look for it. So it is checked here, per
[validate before crossing the socket](../../specifications/tool-interface.md#validate-before-crossing-the-socket).

A module rather than a helper copied into two tool modules, which is what the
other small validators here are. The difference is what a disagreement would
cost: two tool modules that accept different characters would let a preset be
written under a name that cannot be loaded back, silently, and only for the
names in the gap between them. The small validators can differ without anything
happening.

The rule is deliberately **stricter than MPFB's**, and strict in one direction
only. ``savenewpresets.py`` rejects an empty name and a name containing a space,
and nothing else. Every name accepted here is one MPFB's own panel would also
accept, so the two never disagree about what exists; the space is rejected for
that reason rather than because a space in a filename is a problem. The reverse
does not hold, and that is visible rather than hidden: ``mpfb_list_presets``
flags a preset MPFB holds and this rule refuses as ``addressable: false``.

``bridge/mpfb_bridge/shared/preset_files.py`` carries the same rule for the far side of the
socket, where it is the last statement before ``open()``.
``tests/test_save_preset.py`` runs the two over one table of names, so they cannot
drift apart.
"""

from __future__ import annotations

__all__ = (
    "PRESET_NAME_MAX_LENGTH",
    "PRESET_NAME_PATTERN",
    "preset_name_rejection",
    "validated_preset_name",
)

import re

# Long enough for any name a human types, short enough that the assembled path
# cannot be the reason a write fails on a filesystem with a name limit.
PRESET_NAME_MAX_LENGTH = 64

# Letters, digits, underscore, hyphen, dot. Everything a path separator could be
# made of is outside it, on every platform, which is what makes the escape
# unreachable rather than merely unlikely.
PRESET_NAME_PATTERN = "^[A-Za-z0-9_.-]+$"


def preset_name_rejection(name: object) -> str | None:
    """Why this name may not become a preset file, as a sentence, or ``None``.

    A sentence rather than a bool, because it is what the caller is shown: an
    agent that built the name out of a character's display name needs to be told
    which character to drop, not that the name was rejected.
    """
    if not isinstance(name, str):
        return "A preset name must be a string, not {:s}.".format(type(name).__name__)
    if not name:
        return "A preset name must not be empty."
    if len(name) > PRESET_NAME_MAX_LENGTH:
        return "A preset name must be at most {:d} characters; this one is {:d}.".format(
            PRESET_NAME_MAX_LENGTH, len(name))
    if name in (".", ".."):
        return "'{:s}' names a directory rather than a preset.".format(name)
    if name.startswith("."):
        return "A preset name must not start with a dot."
    if re.match(PRESET_NAME_PATTERN, name) is None:
        illegal = sorted(set(
            character for character in name
            if re.match(PRESET_NAME_PATTERN, character) is None))
        return ("A preset name may hold only letters, digits, '_', '-' and '.', so that it "
                "cannot become a path. This one also holds: {:s}.".format(
                    ", ".join(repr(character) for character in illegal)))
    return None


def validated_preset_name(name: object) -> str:
    """The name, or ``ValueError`` saying what is wrong with it.

    Not stripped first. A name with a trailing space is a different name from
    the one without it, MPFB's ``human.<name>.json`` would carry the space, and
    quietly trimming would mean the preset written is not the preset asked for -
    the same reason the rest of this package never treats an explicitly empty
    string as an omitted one.
    """
    rejection = preset_name_rejection(name)
    if rejection is not None:
        raise ValueError(
            "{:s} Presets are addressed by name, never by path: the file is always "
            "human.<name>.json in MPFB's user config directory. Call mpfb_list_presets to "
            "see the names that exist.".format(rejection))
    return name  # type: ignore[return-value]
