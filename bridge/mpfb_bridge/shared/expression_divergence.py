"""
Whether a character's applied-expressions stack explains its face.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/`` and what the ``services`` argument is doing there.

MPFB has **two mechanisms writing one set of shape keys**. The composer
(``FaceService.set_expression``, which ``set_face_units`` wraps) writes the 52
``!ex-`` keys directly. The library keeps a stack of ``{asset, weight}`` rows in
a custom property on the basemesh and, on every change, re-derives the whole
face from it: ``aggregate_expression_stack`` then ``clear_expression`` then
``set_expression``. The clear is unconditional, so anything composed on top of
the stack is **destroyed by the next library call** - an application, a weight
change, a preset load - and nothing in MPFB, its UI included, ever compares the
two to say so.

This module is that comparison, and it is cheap: aggregate the stack, read the
live units, subtract. Three commands report it - ``get_expression``, which
exists to answer it; ``apply_expressions``, which names what a call discarded;
and ``set_face_units``, which says whether what it just composed is now at risk
- and they must give **the same answer**, since a disagreement between them
would look like a bug in neither. That is the bar
[shared modules, and what warrants one](../../../specifications/architecture.md#shared-modules-and-what-warrants-one)
sets. ``get_character_summary``
([FR 034](../../../feature-requests/done/034-character-summary/README.md)) is a
fourth user: it reports a subset of :func:`divergence`'s answer rather than
growing a copy of it.

**What "unexplained" means, precisely.** A unit is unexplained when its live
value differs from what a rebuild of the stack *would write now* - the
aggregate of the rows that still resolve - by more than
:data:`TOLERANCE`. That is deliberately the rebuild's view rather than the
stack's intent: a row whose file is gone contributes nothing to a rebuild, so it
contributes nothing here either, and the set this module reports is then exactly
the change a rebuild would make to the face. A composed unit raised above the
stack is in it; so is a stack unit composed back *down*; so, when the
``faceunits01`` pack is absent and no shape key can exist, is every unit the
stack claims - which is why the commands report ``faceunits01_installed``
beside it.

**The private accessor is called, and that is a choice.**
``FaceService._read_applied_expressions`` carries a leading underscore, and it
is what decodes the property tolerantly - it may hold a JSON string *or* a list,
and an undecodable one reads as empty. ``HumanService`` calls it too, with a
lint suppression. Reimplementing the decode here would be a second
implementation that can drift from the one every MPFB write goes through; the
underscore is the smaller hazard.
"""

# The local bindings below are spelled with MPFB's own capitalisation -
# ``FaceService = services["FaceService"]`` - rather than snake_case, so that a
# body here reads the way MPFB's own source reads. W0212 is the private
# accessor this module's docstring explains.
# pylint: disable=invalid-name,protected-access

__all__ = (
    "TOLERANCE",
    "divergence",
    "raw_sums",
    "stack_rows",
)

import json
import os

from . import mpfb_surface

# How far a live shape key value may sit from the stack's aggregate and still
# count as explained. A shape key stores a 32-bit float, so a value written as
# 0.12 reads back as 0.11999999731779099; an expression file stores four
# decimals, so a composed face saved and re-applied differs from what was
# composed by up to 0.00005. 0.0001 covers both, and is well below any value an
# agent composes on purpose.
TOLERANCE = 0.0001


def stack_rows(services, basemesh):
    """The stack on ``basemesh``, one row per entry, each resolved against the disk.

    Each row is ``{fragment, weight, resolved, path, unresolved_reason}``, in
    the stored order - which is sorted by fragment, because every MPFB write
    goes through ``_write_applied_expressions``, which sorts.

    Resolution is ``aggregate_expression_stack``'s own: ``find_asset_absolute_path``
    under ``expressions``, then ``load_expression``. A row that fails either is
    one a rebuild silently skips, so it is reported here as ``resolved: false``
    with ``unresolved_reason`` of ``"not_found"`` or ``"unreadable"`` rather
    than being dropped the way MPFB drops it. A row MPFB could not read at all -
    not a dict, no asset, a weight that is not a number - is kept with a
    ``"malformed"`` reason, since it is on the character and a rebuild skips it
    just the same.
    """
    FaceService = services["FaceService"]
    AssetService = services["AssetService"]

    rows = []
    for row in FaceService._read_applied_expressions(basemesh):
        asset = row.get("asset") if isinstance(row, dict) else None
        try:
            weight = float(row.get("weight", 1.0)) if isinstance(row, dict) else None
        except (TypeError, ValueError):
            weight = None
        if not asset or weight is None:
            rows.append(dict(fragment=None if not asset else str(asset), weight=weight,
                             resolved=False, path=None, unresolved_reason="malformed"))
            continue

        path = AssetService.find_asset_absolute_path(str(asset), asset_subdir="expressions")
        if not path or not os.path.isfile(path):
            rows.append(dict(fragment=str(asset), weight=weight, resolved=False, path=None,
                             unresolved_reason="not_found"))
            continue
        try:
            FaceService.load_expression(path)
        except (IOError, ValueError, json.JSONDecodeError):
            rows.append(dict(fragment=str(asset), weight=weight, resolved=False,
                             path=str(path), unresolved_reason="unreadable"))
            continue
        rows.append(dict(fragment=str(asset), weight=weight, resolved=True, path=str(path),
                         unresolved_reason=None))
    return rows


def raw_sums(services, rows):
    """Per unit, the stack's sum **before** MPFB clamps it to ``[0, 1]``.

    ``aggregate_expression_stack`` sums ``file_weight * row_weight`` per unit
    and clamps, and returns only the clamped result - so two expressions that
    both open the jaw saturate, and a caller raising one of them sees no change
    and has no way to find out why. This redoes the sum over the rows
    :func:`stack_rows` resolved, without the clamp, so a caller can be told.
    """
    FaceService = services["FaceService"]
    arkit = mpfb_surface.required_module_level(services, "FaceService", "ARKIT_FACEUNITS")
    sums = {}
    for row in rows:
        if not row["resolved"]:
            continue
        expression_dict, _metadata = FaceService.load_expression(row["path"])
        for name, value in expression_dict.items():
            if name not in arkit:
                continue
            sums[name] = sums.get(name, 0.0) + float(value) * row["weight"]
    return sums


def _rounded(value):
    return round(float(value), 6)


def divergence(services, basemesh, rows=None):
    """Compare the stack's aggregate with the live face.

    Returns a dict every caller reports verbatim, so that the three agree:

    - ``applied_expressions`` - :func:`stack_rows`;
    - ``unresolved_count`` - how many of those a rebuild would skip;
    - ``aggregate`` - ``FaceService.aggregate_expression_stack`` over the
      stored stack, exactly as MPFB would compute it;
    - ``clamped_face_units`` - units whose unclamped sum left ``[0, 1]``;
    - ``matches_stack`` - whether every one of the 52 live values is within
      :data:`TOLERANCE` of the aggregate;
    - ``unexplained_face_units`` - the ones that are not, each with its
      ``live`` value and the value ``from_stack`` a rebuild would write.

    ``rows`` may be passed when the caller has just read them, which saves a
    second walk of the expressions roots per row.
    """
    FaceService = services["FaceService"]
    if rows is None:
        rows = stack_rows(services, basemesh)

    # The stored stack, handed to MPFB's own aggregation exactly as a rebuild
    # hands it: the aggregate reported is MPFB's number, not a recomputation.
    aggregate = FaceService.aggregate_expression_stack(
        FaceService._read_applied_expressions(basemesh))
    live = FaceService.read_current_expression(basemesh)

    unexplained = []
    for name in mpfb_surface.required_module_level(services, "FaceService", "ARKIT_FACEUNITS"):
        live_value = float(live.get(name, 0.0))
        from_stack = float(aggregate.get(name, 0.0))
        if abs(live_value - from_stack) > TOLERANCE:
            unexplained.append(dict(face_unit=name, live=_rounded(live_value),
                                    from_stack=_rounded(from_stack)))

    clamped = []
    for name, total in sorted(raw_sums(services, rows).items()):
        if total > 1.0 or total < 0.0:
            clamped.append(dict(face_unit=name, sum=_rounded(total),
                                applied=_rounded(aggregate.get(name, 0.0))))

    return dict(
        applied_expressions=rows,
        unresolved_count=sum(1 for row in rows if not row["resolved"]),
        aggregate={name: _rounded(value) for name, value in sorted(aggregate.items())},
        clamped_face_units=clamped,
        matches_stack=not unexplained,
        unexplained_face_units=unexplained,
    )
