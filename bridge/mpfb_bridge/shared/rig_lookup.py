"""
Which rig file MPFB would actually load, and which weights come with it.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/`` and what the ``services`` argument is doing there.

This exists because two commands have to agree about the same thing.
``list_rigs`` *predicts*, per entry, which file an adding function would load
and where its weights would come from; ``add_rig`` then *does* it and reports
the outcome. A caller who reads the catalogue and then acts on it is entitled to
get back what the catalogue promised, and the only way to guarantee that is for
the prediction and the action to be one implementation rather than two that
happen to match today. Both halves are commands, both import this, and
``bridge/test/`` runs them against one disk.

Everything here is lifted from ``HumanService.add_builtin_rig()`` and
``HumanService.add_custom_rig()``, whose rules differ in ways that are easy to
get wrong from the outside:

- A built-in rig lives in ``<mpfb data>/rigs/standard`` or
  ``<mpfb data>/rigs/rigify``, and the ``rigify.`` prefix that selects the
  second is stripped before the filename is assembled. So ``rigify.human`` is
  the identifier and ``rig.human.json`` is the file.
- Built-in **weights** are resolved through
  ``RigService.get_rig_weight_fallbacks()``, not by filename: ``default_no_toes``
  legitimately borrows ``default``'s weights and ``rigify.human`` borrows
  ``rigify.human_toes``'. Testing ``weights.<name>.json`` alone would report
  both of those as unweighted, which is wrong in the one direction that matters
  - it would make an ordinary rig look broken.
- A custom rig uses **no fallback table at all**: ``add_custom_rig()`` looks
  only for ``weights.<short name>.json`` beside the rig file, so reporting a
  fallback for one would promise weights that would never be loaded.

Nothing here touches the scene, and nothing here decides anything: it answers
"which path would be used" so that a missing rig can be an answer rather than
the ``IOError`` / ``ValueError`` the adding functions raise when they are given
no operator to report through.
"""

# The local bindings below are spelled with MPFB's own capitalisation -
# ``LocationService = services["LocationService"]`` - rather than snake_case,
# so that a body here reads the way MPFB's own source reads and can be
# compared with it line for line. That is the whole reason for the disable.
# pylint: disable=invalid-name

__all__ = (
    "BUILTIN_FAMILIES",
    "CUSTOM_PREFIX",
    "FAMILIES",
    "as_path",
    "builtin_rig_file",
    "builtin_subdir",
    "builtin_weights",
    "custom_rig_record",
    "custom_rig_records",
    "custom_short_name",
    "custom_weights",
    "family_of",
    "rigs_directory",
)

import os

# One tuple per built-in family: the family name, its subdirectory under
# <mpfb data>/rigs, and the prefix HumanService.add_builtin_rig() expects in
# front of the bare name. Both come from that function's own path assembly, so
# a name found here is a name it can load.
BUILTIN_FAMILIES = (
    ("standard", "standard", ""),
    ("rigify", "rigify", "rigify."),
)

CUSTOM_PREFIX = "custom."

# The three families a rig identifier can belong to, in the order the catalogue
# reports them.
FAMILIES = ("standard", "rigify", "custom")


def as_path(path):
    # Coerce at the point a path enters a response. MPFB's path getters are
    # annotated as returning str, but LocationService.get_mpfb_root() hands back
    # a pathlib.Path when called with no sub-path, which fails strict_json and
    # takes the entire response down with it (commit 631989c).
    if not path:
        return None
    return str(path)


def rigs_directory(services):
    """``<mpfb data>/rigs``, or None on an install whose data dir is unknown."""
    LocationService = services["LocationService"]
    return as_path(LocationService.get_mpfb_data("rigs"))


def family_of(identifier):
    """Which of the three families an identifier addresses, from its prefix.

    This is the same dispatch ``HumanService._check_add_rig()`` performs, and it
    is deliberately prefix-only: crossing the two adding functions does not fail
    legibly, since ``add_builtin_rig("custom.my_rig")`` looks for a file called
    ``rig.custom.my_rig.json`` and ``add_custom_rig()`` strips the first seven
    characters of whatever it is given as though they were a ``custom.`` prefix.
    """
    if identifier.startswith(CUSTOM_PREFIX):
        return "custom"
    if identifier.startswith("rigify."):
        return "rigify"
    return "standard"


def builtin_subdir(identifier):
    """The subdirectory name and the bare rig name inside it, for a built-in."""
    for family, subdir, prefix in BUILTIN_FAMILIES:
        if prefix and identifier.startswith(prefix):
            return (subdir, identifier[len(prefix):])
    return (BUILTIN_FAMILIES[0][1], identifier)


def builtin_rig_file(rigs_dir, identifier):
    """The ``rig.<bare name>.json`` path ``add_builtin_rig()`` would look for.

    Returns None only when the path cannot be assembled at all - an unknown data
    directory, or an identifier that is nothing but a prefix. Whether the file
    *exists* is the caller's check, because the two callers want different
    things from the answer: the catalogue lists what it finds, and the adding
    tool turns a miss into a sentence.
    """
    if rigs_dir is None:
        return None
    subdir, bare = builtin_subdir(identifier)
    if not bare:
        return None
    return os.path.join(rigs_dir, subdir, "rig." + bare + ".json")


def builtin_weights(services, identifier, subdir_path):
    """Which weights file ``add_builtin_rig()`` would load, and whose it is.

    Mirrors that function's weights loop exactly: walk the fallback list, strip
    a ``rigify.`` prefix from each candidate, take the first weights file that
    exists in the same subdir. Returns ``(has_weights, path, weights_from)``.
    """
    RigService = services["RigService"]
    for candidate in RigService.get_rig_weight_fallbacks(identifier):
        bare = candidate[len("rigify."):] if candidate.startswith("rigify.") else candidate
        weights_file = os.path.join(subdir_path, "weights." + bare + ".json")
        if os.path.isfile(weights_file):
            return (True, weights_file, bare)
    return (False, None, None)


def custom_short_name(identifier):
    """The name ``add_custom_rig()`` looks up, which is the prefix stripped.

    Stripped by length rather than by ``removeprefix``, matching MPFB's own
    ``rig_name[7:]``: an identifier that does not carry the prefix is not
    something this should be asked about, and ``family_of()`` is how a caller
    finds out.
    """
    if identifier.startswith(CUSTOM_PREFIX):
        return identifier[len(CUSTOM_PREFIX):]
    return identifier


def custom_rig_record(records, short_name):
    """The ``get_custom_rigs()`` record for a short name, or None.

    ``add_custom_rig()`` builds a dict keyed by ``name`` and reports a miss
    through its operator or, with none, by raising ``ValueError``. Looking it up
    first is what turns that into an answer.
    """
    for record in records or []:
        if str(record.get("name") or "") == short_name:
            return record
    return None


def custom_weights(rig_path, short_name):
    """Which weights file ``add_custom_rig()`` would load, and whose it is.

    Deliberately *not* the fallback walk above: that function looks only for
    ``weights.<short name>.json`` beside the rig file. Returns the same triple
    as ``builtin_weights()`` so a caller can report the two the same way, with
    ``weights_from`` always the rig's own name when there is one at all.
    """
    if rig_path is None:
        return (False, None, None)
    weights_file = os.path.join(os.path.dirname(rig_path), "weights." + short_name + ".json")
    if os.path.isfile(weights_file):
        return (True, weights_file, short_name)
    return (False, None, None)


def custom_rig_records(services, refresh):
    """``AssetService.get_custom_rigs()``, optionally rescanning the disk first.

    ``get_custom_rigs()`` caches in a module global that survives until it is
    invalidated, so a rig installed after Blender started is invisible by
    default. ``use_cache=False`` rescans and repopulates in one call, where
    ``invalidate_custom_rig_cache()`` would leave the global at None for the
    custom-rig UI panel that reads the same one. The fallback covers the keyword
    going away; a TypeError from deeper inside would be misread here, which is
    the price of not inspecting the signature.
    """
    AssetService = services["AssetService"]
    if not refresh:
        return AssetService.get_custom_rigs()
    try:
        return AssetService.get_custom_rigs(use_cache=False)
    except TypeError:
        AssetService.invalidate_custom_rig_cache()
        return AssetService.get_custom_rigs()
