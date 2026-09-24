"""
What a preset or a saved expression may be called, checked before anything is sent.

The two arguments in this package that become a **path**. ``mpfb_save_preset``
and ``mpfb_create_human_from_preset`` take ``name`` and resolve it to
``<user config>/human.<name>.json``; ``mpfb_save_expression`` takes ``name`` and
writes ``<user data>/expressions/<name>.json``. A name carrying ``/``, ``\\`` or
``..`` would address a file outside the directory MPFB owns - and on the saving
side it would *write* one. That is a shape rather than a vocabulary, it is
entirely knowable on this side of the socket, and the consequence of getting it
wrong is a file somewhere nobody will look for it. So it is checked here, per
[validate before crossing the socket](../../specifications/tool-interface.md#validate-before-crossing-the-socket).

**One rule for both artifacts, with the noun as an argument.** The pattern, the
length bound and the dot rules are the same for a preset and an expression,
because the reason for them is the same: a name that becomes a filename in a
directory MPFB owns. What differs is only the word in the sentence a caller is
shown and where the file ends up, so :func:`name_rejection` takes the noun and
each ``validated_*`` function adds its own sentence about where the file is.
[FR 027](../../feature-requests/done/027-expression-library/README.md)
generalised this module from ``preset_names.py`` rather than copying it: two
copies of one rule per side of the socket is already justified only by what a
gap would cost, and a third and fourth would have had no such justification.

A module of its own rather than a function in [arguments.py](arguments.py),
where the other shape rules are, because this one is about what a name becomes:
a file. And a disagreement would cost more here than anywhere: two tool modules
that accepted different characters would let a preset be written under a name
that cannot be loaded back, silently, and only for the names in the gap between
them.

The rule is deliberately **stricter than MPFB's**, and strict in one direction
only. ``savenewpresets.py`` rejects an empty name and a name containing a space,
and nothing else; the expression composer's save operator rejects ``/``,
``\\``, ``.`` and ``..`` and nothing else. Every name accepted here is one
MPFB's own panels would also accept, so the two never disagree about what
exists. The reverse does not hold, and that is visible rather than hidden:
``mpfb_list_presets`` flags a preset MPFB holds and this rule refuses as
``addressable: false``.

``bridge/mpfb_bridge/shared/artifact_names.py`` carries the same rule for the
far side of the socket, where it is the last statement before ``open()``.
``tests/test_save_preset.py`` runs the two over one table of names and both
nouns, so they cannot drift apart.
"""

from __future__ import annotations

__all__ = (
    "NAME_MAX_LENGTH",
    "NAME_PATTERN",
    "name_rejection",
    "preset_name_rejection",
    "validated_expression_name",
    "validated_preset_name",
)

import re

# Long enough for any name a human types, short enough that the assembled path
# cannot be the reason a write fails on a filesystem with a name limit.
NAME_MAX_LENGTH = 64

# Letters, digits, underscore, hyphen, dot. Everything a path separator could be
# made of is outside it, on every platform, which is what makes the escape
# unreachable rather than merely unlikely.
NAME_PATTERN = "^[A-Za-z0-9_.-]+$"


def name_rejection(name: object, noun: str) -> str | None:
    """Why this name may not become a ``noun`` file, as a sentence, or ``None``.

    A sentence rather than a bool, because it is what the caller is shown: an
    agent that built the name out of a character's display name needs to be told
    which character to drop, not that the name was rejected.
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
        illegal = sorted(set(
            character for character in name
            if re.match(NAME_PATTERN, character) is None))
        return ("A {:s} name may hold only letters, digits, '_', '-' and '.', so that it "
                "cannot become a path. This one also holds: {:s}.".format(
                    noun, ", ".join(repr(character) for character in illegal)))
    return None


def preset_name_rejection(name: object) -> str | None:
    """:func:`name_rejection` for a character preset."""
    return name_rejection(name, "preset")


def _validated(name: object, noun: str, where: str) -> str:
    """The name, or ``ValueError`` saying what is wrong with it and where files go.

    Not stripped first. A name with a trailing space is a different name from
    the one without it, the file MPFB writes would carry the space, and quietly
    trimming would mean the file written is not the file asked for - the same
    reason the rest of this package never treats an explicitly empty string as
    an omitted one.
    """
    rejection = name_rejection(name, noun)
    if rejection is not None:
        raise ValueError("{:s} {:s}".format(rejection, where))
    return name  # type: ignore[return-value]


def validated_preset_name(name: object) -> str:
    """A preset name, or ``ValueError``."""
    return _validated(
        name, "preset",
        "Presets are addressed by name, never by path: the file is always "
        "human.<name>.json in MPFB's user config directory. Call mpfb_list_presets to "
        "see the names that exist.")


def validated_expression_name(name: object) -> str:
    """An expression name, or ``ValueError``."""
    return _validated(
        name, "expression",
        "Expressions are saved by name, never by path: the file is always <name>.json "
        "in the expressions directory of MPFB's user data. Call mpfb_list_expressions to "
        "see what exists.")
