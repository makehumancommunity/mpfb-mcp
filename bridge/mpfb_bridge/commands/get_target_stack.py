"""
``get_target_stack``: what is actually on this character, in two views.

Changes nothing. In particular it never calls ``reapply_macro_details()`` or
``reapply_all_details()``: a character whose numbers and whose shape have
drifted apart is **reported** as drifted rather than quietly repaired by a
command the caller believed to be read-only.

**How the stack is read, and how it rolls up, is in
[`shared/target_rollup.py`](../shared/target_rollup.py)**: why the shape keys
come off ``key_blocks`` rather than through ``TargetService``, and the two
views of one snapshot this answer carries - ``targets``, one entry per shape
key, and ``modifiers``, the categories MPFB's sliders manipulate. It moved
there so that ``get_character_summary`` reports this command's rollup for its
default arguments without a second reading
([FR 034](../../../feature-requests/done/034-character-summary/README.md)).

The asymmetry between the two views looks like an oversight and is a decision:
``targets`` is filtered, paged and capped while ``modifiers`` is none of those.
The rollup is small by construction - only a category with a non-zero reading
appears - and it is what a caller writes back, so cutting it would hand back
something that is not a description of the character.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_target_stack",
)

import bpy

from ..log import get_logger
from ..shared import target_categories
from ..shared import target_rollup
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
    values = target_rollup.shapekey_values(basemesh)
    present, value_of = target_rollup.value_lookup(target_service, values)

    entries = target_rollup.shapekey_entries(target_service, tables, values)
    counts_by_kind, counts_by_section = target_rollup.counts_of(entries)
    matched = target_rollup.matching(entries, include_macro, include_expressions, needle)

    total_count = len(matched)
    paged = matched[offset:offset + limit]
    count = len(paged)

    modifiers, asymmetries = target_rollup.build_modifiers(tables, present, value_of)
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
