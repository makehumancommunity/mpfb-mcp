"""
What is actually on a character, one shape key at a time and rolled up.

**One implementation, imported by both commands that report it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/``. ``get_target_stack`` reports all of it, filtered and paged as its
caller asks; ``get_character_summary`` reports the rollup, the asymmetries and
the counts that ``get_target_stack`` gives for its **default** arguments, under
the same names
([FR 034](../../../feature-requests/done/034-character-summary/README.md)). Two
readings of one stack that disagreed would look like a bug in neither.

**The shape keys are read from ``key_blocks`` directly rather than through
``TargetService.get_target_stack()``**, which excludes any shape key whose
lowercased name *contains* ``"basis"`` - not merely equals it. A user target
called ``basis-nose-widen`` is therefore invisible to ``has_target()``,
``get_target_value()`` and every write MPFB can perform on it. Suppressing it
here as well would hide a real shape key that is really deforming the mesh; so
it is listed, with ``visible_to_targetservice`` saying that MPFB cannot address
it. Every *write* still goes through ``TargetService``, or the read and the
write halves would disagree about what exists.

There are **two views of the same facts**. One entry per shape key
(:func:`shapekey_entries`) is what ``set_targets``' raw ``targets`` list
addresses. The rollup (:func:`build_modifiers`) groups those into the
``target.json`` categories MPFB's own sliders manipulate, computed the way
``_get_opposed_modifier_value()`` computes them - by
[`modifier_reading.py`](modifier_reading.py), so ``symmetrize_targets`` cannot
read a category differently - which is the view that round-trips back into
``set_targets``' ``modifiers`` list and the view that matches what the user
sees in the panel. Only a category with a non-zero reading is in it, which is
what keeps it small.

**Both views come from one snapshot**, read once by :func:`shapekey_values`
and answered from by :func:`value_lookup`. ``modifier_reading`` takes the
lookup as an argument because ``symmetrize_targets`` writes between readings
and must read live; a read-only command must not, or its two views would be two
reads rather than two views of one.
"""

__all__ = (
    "EPSILON",
    "EXPRESSION_PREFIX",
    "MACRO_PREFIX",
    "build_modifiers",
    "counts_of",
    "matching",
    "shapekey_entries",
    "shapekey_values",
    "value_lookup",
)

from . import target_categories
from .modifier_reading import modifier_reading

MACRO_PREFIX = "$md"
EXPRESSION_PREFIX = "!ex-"

# MPFB's own threshold, from _set_opposed_modifier_value() and prune_shapekeys().
EPSILON = 0.0001


def _encoded(target_service, name):
    try:
        return str(target_service.encode_shapekey_name(name))
    except Exception:  # pylint: disable=broad-except
        return str(name)


def _decoded(target_service, name):
    try:
        return str(target_service.decode_shapekey_name(name))
    except Exception:  # pylint: disable=broad-except
        return str(name)


def shapekey_values(basemesh):
    """Every shape key on the mesh, in order, as ``(name, value)`` pairs.

    Read straight off ``key_blocks`` - see this module's docstring for why not
    through ``TargetService``.
    """
    pairs = []
    keys = basemesh.data.shape_keys
    if keys is None or keys.key_blocks is None:
        return pairs
    for block in keys.key_blocks:
        pairs.append((str(block.name), float(block.value)))
    return pairs


def _kind_of(target_service, shapekey_name, known_to_target_json):
    if shapekey_name.lower() == "basis":
        return "basis"
    if shapekey_name.startswith(MACRO_PREFIX):
        return "macro"
    if shapekey_name.startswith(EXPRESSION_PREFIX):
        return "expression"
    if known_to_target_json:
        return "detail"
    try:
        if target_service.shapekey_is_target(shapekey_name):
            return "detail"
    except Exception:  # pylint: disable=broad-except
        pass
    return "unknown"


def value_lookup(target_service, values):
    """A ``has_target()``/``get_target_value()`` pair over an already-read stack.

    ``has_target()`` checks the encoded name as well as the given one, while
    ``get_target_value()`` matches the raw name only - so the two are reproduced
    separately rather than collapsed into one helper that would paper over the
    difference.
    """
    by_name = dict(values)

    def present(target_name):
        if not target_name:
            return False
        if target_name in by_name:
            return True
        return _encoded(target_service, target_name) in by_name

    def value_of(target_name):
        if not target_name:
            return 0.0
        if target_name in by_name:
            return by_name[target_name]
        encoded_name = _encoded(target_service, target_name)
        if encoded_name in by_name:
            return by_name[encoded_name]
        return 0.0

    return (present, value_of)


def _sides_of(category):
    if category.get("has_left_and_right"):
        return ("left", "right")
    return ("unsided",)


def build_modifiers(tables, present, value_of):
    """Every category with a non-zero reading, plus the sided ones that differ."""
    modifiers = []
    asymmetries = []
    for section_name in tables.known_sections:
        section = tables.sections[section_name]
        for category in section["categories"]:
            readings = dict()
            for side in _sides_of(category):
                readings[side] = modifier_reading(category, side, present, value_of)
            for side in _sides_of(category):
                if abs(readings[side]) > EPSILON:
                    modifiers.append({
                        "section": section_name,
                        "category": str(category["name"]),
                        "side": side,
                        "value": round(readings[side], 6),
                        "opposed": target_categories.category_is_opposed(category),
                    })
            if category.get("has_left_and_right"):
                difference = readings["left"] - readings["right"]
                if abs(difference) > EPSILON:
                    asymmetries.append({
                        "section": section_name,
                        "category": str(category["name"]),
                        "left": round(readings["left"], 6),
                        "right": round(readings["right"], 6),
                        "difference": round(difference, 6),
                    })
    return (modifiers, asymmetries)


def _entry_for(target_service, tables, shapekey_name, value):
    """One shape key, placed in the category table where the table knows it."""
    placement = tables.index.get(shapekey_name)
    return {
        "shapekey_name": shapekey_name,
        "decoded_name": _decoded(target_service, shapekey_name),
        "value": round(value, 6),
        "kind": _kind_of(target_service, shapekey_name, placement is not None),
        "section": None if placement is None else placement["section"],
        "category": None if placement is None else placement["category"],
        "side": None if placement is None else placement["side"],
        "polarity": None if placement is None else placement["polarity"],
        # True only for a category the bundled index really names: a synthesized
        # user category is a modifier MPFB's panel shows but target.json has
        # never heard of.
        "listed_in_target_json": placement is not None and not placement["synthesized"],
        # False means MPFB itself cannot see this shape key: its
        # get_target_stack() excludes any name *containing* "basis", so every
        # write and every value read through TargetService misses it.
        "visible_to_targetservice": "basis" not in shapekey_name.lower(),
    }


def shapekey_entries(target_service, tables, values):
    """One entry per shape key in ``values``, in order, Blender's rest shape left out."""
    entries = []
    for shapekey_name, value in values:
        entry = _entry_for(target_service, tables, shapekey_name, value)
        if entry["kind"] == "basis":
            # Blender's own rest shape, not a target, and never addressable.
            continue
        entries.append(entry)
    return entries


def counts_of(entries):
    """``(counts_by_kind, counts_by_section)`` over every entry, before any filter.

    Counted over everything on the mesh, so that a filtered answer still says
    what it was filtered out of.
    """
    counts_by_kind = dict()
    counts_by_section = dict()
    for entry in entries:
        counts_by_kind[entry["kind"]] = counts_by_kind.get(entry["kind"], 0) + 1
        section_key = entry["section"] or "(none)"
        counts_by_section[section_key] = counts_by_section.get(section_key, 0) + 1
    return (counts_by_kind, counts_by_section)


def matching(entries, include_macro=False, include_expressions=False, needle=None):
    """The entries a listing reports, sorted; the defaults are ``get_target_stack``'s.

    ``needle`` is already stripped and lowercased, and matched against a shape
    key's stored and decoded names.
    """
    matched = []
    for entry in entries:
        if entry["kind"] == "macro" and not include_macro:
            continue
        if entry["kind"] == "expression" and not include_expressions:
            continue
        if needle is not None:
            haystacks = [entry["shapekey_name"].lower(), entry["decoded_name"].lower()]
            if not any(needle in haystack for haystack in haystacks):
                continue
        matched.append(entry)

    # Sorted before paging: key_blocks order is insertion order, so two pages of
    # one query would otherwise skip and repeat entries as the stack changes.
    matched.sort(key=lambda entry: (
        entry["kind"], entry["section"] or "", entry["category"] or "",
        entry["shapekey_name"]))
    return matched
