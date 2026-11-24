"""
What a preset, a saved expression or an export may be called, checked before anything is sent.

The three arguments in this package that become a **path**. ``mpfb_save_preset``
and ``mpfb_create_human_from_preset`` take ``preset_name`` and resolve it to
``<user config>/human.<preset_name>.json``; ``mpfb_save_expression`` takes
``expression_name`` and writes ``<user data>/expressions/<expression_name>.json``;
and ``mpfb_export_character`` takes ``export_name`` and writes
``<export directory>/<export_name>.<fbx|glb|usdz>``, in a directory the human
running the bridge chose
([FR 039](../../feature-requests/done/039-exporting-characters/README.md)).
A name carrying ``/``, ``\\`` or ``..`` would address a file outside the
directory MPFB owns - and on the saving side it would *write* one. That is a
shape rather than a vocabulary, it is entirely knowable on this side of the
socket, and the consequence of getting it wrong is a file somewhere nobody will
look for it. So it is checked here, per
[validate before crossing the socket](../../specifications/tool-interface.md#validate-before-crossing-the-socket).

**One rule for every artifact, with the noun as an argument.** The pattern, the
length bound and the dot rules are the same for a preset, an expression and an export,
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
``tests/test_save_preset.py`` runs the two over one table of names and all three
nouns, so they cannot drift apart.

**A stored MakeSkin material has a narrower rule of its own**
([FR 049](../../feature-requests/done/049-makeskin-materials/README.md)), which
:func:`material_name_rejection` states and ``tests/test_store_makeskin_material.py``
holds to the far side's copy. Everything it accepts this rule accepts too. **So does a
written mesh asset** ([FR 050](../../feature-requests/done/050-writing-mesh-assets/README.md)),
for the same reason, by :func:`asset_name_rejection`, held together in
``tests/test_write_mesh_asset.py``.
"""

from __future__ import annotations

__all__ = (
    "ASSET_NAME_PATTERN",
    "MATERIAL_NAME_PATTERN",
    "NAME_MAX_LENGTH",
    "NAME_PATTERN",
    "RIG_NAME_PATTERN",
    "asset_name_rejection",
    "material_name_rejection",
    "name_rejection",
    "rig_name_rejection",
    "preset_name_rejection",
    "validated_asset_name",
    "validated_export_name",
    "validated_expression_name",
    "validated_material_name",
    "validated_preset_name",
    "validated_rig_name",
)

import re

# Long enough for any name a human types, short enough that the assembled path
# cannot be the reason a write fails on a filesystem with a name limit.
NAME_MAX_LENGTH = 64

# Letters, digits, underscore, hyphen, dot. Everything a path separator could be
# made of is outside it, on every platform, which is what makes the escape
# unreachable rather than merely unlikely.
NAME_PATTERN = "^[A-Za-z0-9_.-]+$"

# What a stored MakeSkin material may be called. Narrower than the above: see
# material_name_rejection().
MATERIAL_NAME_PATTERN = "^[a-z0-9_]+$"

# What a written mesh asset may be called. Narrower too: see asset_name_rejection().
ASSET_NAME_PATTERN = "^[a-zA-Z0-9_]+$"

# What a stored rig may be called: MPFB's own rule, which its custom-rig scan applies to every
# file it finds and its save-to-library operator to every name it is given. See
# rig_name_rejection().
RIG_NAME_PATTERN = "^[a-zA-Z0-9_]+$"


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


def material_name_rejection(name: object) -> str | None:
    """Why this name may not become a stored MakeSkin material, as a sentence, or ``None``.

    Stricter than :func:`name_rejection`, for one reason: MakeSkin's two store
    operators lowercase a name and turn its spaces into underscores before
    using it, so a name holding either would be written under a name other than
    the one given, and be looked up under the other by anyone reading the panel.
    The hyphen and the dot go for the same reason of being read back: the file is
    ``<name>/<name>.mhmat`` beside textures called ``<name>_<slot>.<ext>``, and
    only what survives MPFB's normalisation unchanged is addressable both ways.
    """
    rejection = name_rejection(name, "material")
    if rejection is not None:
        return rejection
    if re.match(MATERIAL_NAME_PATTERN, name) is None:
        illegal = sorted(set(
            character for character in name
            if re.match(MATERIAL_NAME_PATTERN, character) is None))
        return ("A material name may hold only lower case letters, digits and '_', which is "
                "what survives MPFB's normalisation unchanged. This one also holds: {:s}.".format(
                    ", ".join(repr(character) for character in illegal)))
    return None


def asset_name_rejection(name: object) -> str | None:
    """Why this name may not become a written mesh asset, as a sentence, or ``None``.

    Stricter than :func:`name_rejection`, because MakeClothes' "Store in library"
    turns anything outside ``[a-zA-Z0-9_]`` into ``_`` and then collapses runs of
    ``_``, so ``my-gi`` would land as ``my_gi`` and ``a__b`` as ``a_b``. A name that
    survives that unchanged is one the panel and this agree about, which is
    the promise of this module's docstring.
    """
    rejection = name_rejection(name, "mesh asset")
    if rejection is not None:
        return rejection
    if re.match(ASSET_NAME_PATTERN, name) is None:  # type: ignore[arg-type]
        illegal = sorted(set(
            character for character in name
            if re.match(ASSET_NAME_PATTERN, character) is None))
        return ("A mesh asset name may hold only letters, digits and '_', which is what "
                "survives MPFB's normalisation unchanged. This one also holds: {:s}.".format(
                    ", ".join(repr(character) for character in illegal)))
    if "__" in name:
        return ("A mesh asset name must not hold '__', which MPFB's normalisation collapses "
                "to one '_'.")
    return None


def rig_name_rejection(name: object) -> str | None:
    """Why this name may not become a stored rig, as a sentence, or ``None``.

    Exactly MPFB's rule, ``^[a-zA-Z0-9_]+$``, and nothing stricter beyond the length bound
    every name here has: ``AssetService.get_custom_rigs()`` skips any rig file whose name
    fails it, so a rig stored under one would be written and never found
    ([FR 060](../../feature-requests/done/060-authoring-rigs/README.md)). MPFB rejects rather than
    normalises, so unlike a mesh asset's a doubled ``_`` is fine.
    """
    rejection = name_rejection(name, "rig")
    if rejection is not None:
        return rejection
    if re.match(RIG_NAME_PATTERN, name) is None:  # type: ignore[arg-type]
        illegal = sorted(set(
            character for character in name
            if re.match(RIG_NAME_PATTERN, character) is None))
        return ("A rig name may hold only letters, digits and '_', which is MPFB's own rule for "
                "a custom rig. This one also holds: {:s}.".format(
                    ", ".join(repr(character) for character in illegal)))
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


def validated_material_name(name: object) -> str:
    """A stored MakeSkin material's name, or ``ValueError``."""
    rejection = material_name_rejection(name)
    if rejection is not None:
        raise ValueError(
            "{:s} Materials are stored by name, never by path: the file is always "
            "<name>/<name>.mhmat, beside the asset or among MPFB's user skins.".format(rejection))
    return name  # type: ignore[return-value]


def validated_asset_name(name: object) -> str:
    """A written mesh asset's name, or ``ValueError``."""
    rejection = asset_name_rejection(name)
    if rejection is not None:
        raise ValueError(
            "{:s} A mesh asset is written by name, never by path: the file is always "
            "<name>/<name>.mhclo, or .proxy, under the destination.".format(rejection))
    return name  # type: ignore[return-value]


def validated_export_name(name: object) -> str:
    """An export's name, or ``ValueError``."""
    return _validated(
        name, "export",
        "Exports are written by name, never by path: the file is always "
        "<export_name>.<extension> in the export directory, which the person running "
        "the MPFB Bridge chooses in its preferences.")


def validated_rig_name(name: object) -> str:
    """A stored rig's name, or ``ValueError``."""
    rejection = rig_name_rejection(name)
    if rejection is not None:
        raise ValueError(
            "{:s} A rig is stored by name, never by path: the files are always "
            "rigs/<name>.json and rigs/weights.<name>.json in MPFB's user data.".format(rejection))
    return name  # type: ignore[return-value]
