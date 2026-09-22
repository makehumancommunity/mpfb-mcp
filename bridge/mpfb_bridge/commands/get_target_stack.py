"""
``get_target_stack``: what is actually on this character, in two views.

Changes nothing. In particular it never calls ``reapply_macro_details()`` or
``reapply_all_details()``: a character whose numbers and whose shape have
drifted apart is **reported** as drifted rather than quietly repaired by a
command the caller believed to be read-only.

**The shape keys are read from ``key_blocks`` directly rather than through
``TargetService.get_target_stack()``**, which excludes any shape key whose
lowercased name *contains* ``"basis"`` - not merely equals it. A user target
called ``basis-nose-widen`` is therefore invisible to ``has_target()``,
``get_target_value()`` and every write MPFB can perform on it. Suppressing it
here as well would hide a real shape key that is really deforming the mesh; so
it is listed, with ``visible_to_targetservice`` saying that MPFB cannot address
it. Every *write* still goes through ``TargetService``, or the read and the
write halves would disagree about what exists.

The answer has **two views of the same facts**. ``targets`` is one entry per
shape key, which is what ``set_targets``' raw ``targets`` list addresses.
``modifiers`` rolls those up into the ``target.json`` categories MPFB's own
sliders manipulate, computed the way ``_get_opposed_modifier_value()`` computes
them - by [`shared/modifier_reading.py`](../shared/modifier_reading.py), so
``symmetrize_targets`` cannot read a category differently - which is the view
that round-trips back into ``set_targets``' ``modifiers`` list and the view that
matches what the user sees in the panel. ``symmetrize_targets`` has not
migrated, so for now that agreement is kept by
``tests/test_fragment_drift.py`` rather than by the two sharing a module.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
, including the asymmetry that looks like an oversight: ``targets`` is
filtered, paged and capped while ``modifiers`` is none of those. The rollup is
small by construction - only a category with a non-zero reading appears - and it
is what a caller writes back, so cutting it would hand back something that is
not a description of the character.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_target_stack",
)

import bpy

from ..log import get_logger
from ..shared import target_categories
from ..shared.modifier_reading import modifier_reading
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_INTEGER
from ..validation import TYPE_STRING

_LOG = get_logger("commands.gettargetstack")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("include_macro", TYPE_BOOLEAN, default=False,
          description="Include the macro shape keys, which mpfb_get_macro_details reports "
                      "more usefully."),
    Param("include_expressions", TYPE_BOOLEAN, default=False,
          description="Include the expression shape keys, which are numerous on a rigged "
                      "face and rarely what a caller is looking for."),
    Param("name_contains", TYPE_STRING, default=None, nullable=True,
          description="Case-insensitive substring matched against a shape key's stored and "
                      "decoded names."),
    Param("limit", TYPE_INTEGER, default=200, minimum=0, maximum=1000,
          description="How many shape keys to return. The answer says whether it was cut."),
    Param("offset", TYPE_INTEGER, default=0, minimum=0,
          description="How many matching shape keys to skip."),
)

SUMMARY = "Read the shape keys on one character, and the modeling categories they roll up into."

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


def _shapekey_values(basemesh):
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


def _value_lookup(target_service, values):
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


def _build_modifiers(tables, present, value_of):
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


def _resolve_basemesh(services, requested_name):
    """The basemesh, the object asked about, and the sentence to say on a miss."""
    if requested_name is None:
        # The view layer rather than bpy.context.active_object: this runs from
        # a timer or a background loop, not from a viewport operator.
        subject = bpy.context.view_layer.objects.active
        if subject is None:
            return (None, None,
                    "No object name was given and no object is active in this Blender session. "
                    "Select a MakeHuman object, or call mpfb_list_objects and pass one of its "
                    "names.")
    else:
        subject = bpy.data.objects.get(requested_name)
        if subject is None:
            return (None, None,
                    "No object named '{:s}' exists in this .blend file. Call mpfb_list_objects "
                    "to see what the current scene holds.".format(str(requested_name)))

    # Any object in the character's family resolves to the basemesh that owns
    # the shape keys - the caller may well be holding the name of the rig or of
    # a garment, since that is what list_objects hands out.
    basemesh = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        subject, "Basemesh")
    if basemesh is None:
        return (None, subject,
                "'{:s}' has no MakeHuman basemesh among its nearest relatives, so it has no "
                "target stack. Call mpfb_get_object_info to see what it is related "
                "to.".format(subject.name))
    return (basemesh, subject, None)


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


def _nothing_found(subject, subject_resolved_by, message, offset, limit):
    return dict(
        found=False,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None,
        has_shapekeys=False,
        targets=[],
        modifiers=[],
        asymmetries=[],
        counts_by_kind=dict(),
        counts_by_section=dict(),
        count=0,
        total_count=0,
        truncated=False,
        offset=offset,
        limit=limit,
        message=message,
    )


def _message(basemesh, total_count, count, counts_by_kind, invisible,
             include_macro, include_expressions):
    parts = ["{:d} shape key(s) matched on basemesh '{:s}', {:d} returned".format(
        total_count, basemesh.name, count)]
    if total_count > count:
        parts.append(" - the rest were not returned, so this is not the whole stack")
    parts.append(
        ". 'modifiers' is the same information rolled up into the categories MPFB's own sliders "
        "manipulate, and is what mpfb_set_targets takes; 'targets' entries are addressed by "
        "'shapekey_name'.")
    if not include_macro and counts_by_kind.get("macro"):
        parts.append(
            " {:d} macro shape key(s) were left out; pass include_macro to see them, or call "
            "mpfb_get_macro_details.".format(counts_by_kind["macro"]))
    if not include_expressions and counts_by_kind.get("expression"):
        parts.append(
            " {:d} expression shape key(s) were left out; pass include_expressions to see "
            "them.".format(counts_by_kind["expression"]))
    if invisible:
        parts.append(
            " Note that {:d} shape key(s) contain 'basis' in their name and are therefore "
            "invisible to MPFB itself, which cannot read or change them: {:s}.".format(
                len(invisible), ", ".join(invisible)))
    return "".join(parts)


def get_target_stack(params, resolution):  # pylint: disable=too-many-locals
    """Read one character's shape keys, and roll them up into MPFB's categories."""
    services = resolution.services
    target_service = services["TargetService"]

    requested_name = params["name"]
    include_macro = params["include_macro"]
    include_expressions = params["include_expressions"]
    name_contains = params["name_contains"]
    limit = params["limit"]
    offset = params["offset"]
    needle = name_contains.strip().lower() if name_contains is not None else None

    subject_resolved_by = "active" if requested_name is None else "name"
    basemesh, subject, message = _resolve_basemesh(services, requested_name)
    if basemesh is None:
        _LOG.debug("get_target_stack: no basemesh resolved from %r", requested_name)
        return _nothing_found(subject, subject_resolved_by, message, offset, limit)

    tables = target_categories.build_tables(services)
    values = _shapekey_values(basemesh)
    present, value_of = _value_lookup(target_service, values)

    entries = []
    for shapekey_name, value in values:
        entry = _entry_for(target_service, tables, shapekey_name, value)
        if entry["kind"] == "basis":
            # Blender's own rest shape, not a target, and never addressable.
            continue
        entries.append(entry)

    # Counted over everything on the mesh, before any filter or cap, so a
    # filtered answer still says what it was filtered out of.
    counts_by_kind = dict()
    counts_by_section = dict()
    for entry in entries:
        counts_by_kind[entry["kind"]] = counts_by_kind.get(entry["kind"], 0) + 1
        section_key = entry["section"] or "(none)"
        counts_by_section[section_key] = counts_by_section.get(section_key, 0) + 1

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

    total_count = len(matched)
    paged = matched[offset:offset + limit]
    count = len(paged)

    modifiers, asymmetries = _build_modifiers(tables, present, value_of)
    invisible = [entry["shapekey_name"] for entry in entries
                 if not entry["visible_to_targetservice"]]

    _LOG.debug("get_target_stack: %d shape keys, %d modifiers, %d asymmetries",
               len(entries), len(modifiers), len(asymmetries))

    return dict(
        found=True,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        has_shapekeys=len(values) > 0,
        targets=paged,
        # Not paged, and deliberately not filtered by name_contains: this is the
        # rollup view, small by construction, and it is what a caller writes back.
        modifiers=modifiers,
        modifier_count=len(modifiers),
        asymmetries=asymmetries,
        counts_by_kind=counts_by_kind,
        counts_by_section=counts_by_section,
        count=count,
        total_count=total_count,
        # Always present, and the field to read before concluding a target is
        # not on this character: a capped answer must never look complete.
        truncated=total_count > count,
        offset=offset,
        limit=limit,
        message=_message(basemesh, total_count, count, counts_by_kind, invisible,
                         include_macro, include_expressions),
    )
