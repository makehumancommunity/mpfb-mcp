"""
The ``mpfb_check_intersections`` tool: how much meshes intersect, and how close they come.

Nothing in this package could see two meshes pass through each other, and a session
that needed to wrote the same thirty lines of ``mathutils.bvhtree`` each time. It
was the difference between "looks fine" and "0 pairs, 3.7 mm"
([FR 048](../../../feature-requests/done/048-measuring-mesh-assets/README.md)).

What is counted is explained in the bridge's ``shared/mesh_overlap.py``. What is
checked here is shape, and only ``region`` has any: an object of ``min`` and ``max``,
each an object of ``x``, ``y`` and ``z``, with finite numbers and a lower bound not
above its upper one. An axis may be left open, and a box open on every side is
refused, since it would be no box at all and only a mistake can have produced it.
**No object name is checked here**, since which objects exist is answered inside
Blender.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

_AXES = ("x", "y", "z")
_BOUNDS = ("min", "max")


def _validated_bound(region: dict, bound: str) -> dict[str, float]:
    """One side of the box, its numbers as floats, or empty when it was left out."""
    side = region.get(bound)
    if side is None:
        return {}
    if not isinstance(side, dict):
        raise ValueError("region's {:s} must be an object of x, y and z, got {!r}".format(
            bound, side))
    unknown = sorted(str(key) for key in side if key not in _AXES)
    if unknown:
        raise ValueError("region's {:s} knows only x, y and z, got {:s}".format(
            bound, ", ".join(unknown)))
    for axis, value in side.items():
        if not arguments.is_finite_number(value):
            raise ValueError("region's {:s}.{:s} must be a finite number, got {!r}".format(
                bound, axis, value))
    return {axis: float(value) for axis, value in side.items()}


def _validated_region(region: object) -> dict[str, dict[str, float]] | None:
    """The box, with every axis it names, or ``None`` when there is none."""
    if region is None:
        return None
    if not isinstance(region, dict):
        raise ValueError("region must be an object with min and max, or omitted, got {!r}".format(
            region))
    unknown = sorted(str(key) for key in region if key not in _BOUNDS)
    if unknown:
        raise ValueError("region knows only min and max, got {:s}".format(", ".join(unknown)))
    lowest = _validated_bound(region, "min")
    highest = _validated_bound(region, "max")
    if not lowest and not highest:
        raise ValueError(
            "region must bound at least one axis, for example {'min': {'z': 0.9}}; omit it to "
            "count everywhere")
    for axis in _AXES:
        if axis in lowest and axis in highest and lowest[axis] > highest[axis]:
            raise ValueError("region's min.{0:s} is above its max.{0:s}".format(axis))
    return {"min": lowest, "max": highest}


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Check Intersections",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_check_intersections(
        name: str | None = None,
        other: str | None = None,
        include_self: bool = False,
        region: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, object]:
        """
        Measure how much meshes intersect and how close they come, as they
        stand: evaluated, in world space, posed and placed. Changes nothing, so
        it is safe to call after every change. **No threshold makes a count a
        pass or a fail**: a finished garment that renders cleanly can have
        hundreds of pairs against the unmasked body, hidden under it.

        `name` is any object in a character's family, or a mesh belonging to no
        character, such as a held prop. Without `other`, every pair inside that
        family is measured; with `other`, resolved the same way, every pair
        across the two. `include_self` adds each mesh against itself, leaving
        out faces that share a vertex. `region` is a world-space box,
        `{"min": {"x", "y", "z"}, "max": {...}}`, any axis left open, so
        `{"min": {"z": 0.9}, "max": {"z": 1.1}}` is a band: a face counts if its
        centre is inside.

        In `result`, `pairs` has a row per pair, largest count first, capped
        with `pairs_truncated`: `object_name`, `other_object_name`, `face_pairs`,
        `region` (the world box of the intersecting faces), `min_distance`, and
        `subdiv_levels`/`other_subdiv_levels`, the viewport level measured at,
        which may not be what renders. `pairs_measured`, `pairs_clear` and
        `closest_pair` cover every pair, including those cut. `not_measured`
        names meshes Blender has no evaluated geometry for.

        **A count on a masked body is blind.** A delete group's mask removes the
        skin under a garment, so `face_pairs` cannot see through it. A row with a
        body or body proxy in it therefore also has `face_pairs_unmasked`,
        `region_unmasked` and `min_distance_unmasked`, with every mask off but
        the one hiding MPFB's helper geometry. Skin poking through on another
        body or in a pose shows there first. Masks are put back exactly.

        `face_pairs` counts triangle pairs, so it measures extent rather than
        faces: a quad counts as two. `min_distance` is metres, 0.0 when they
        intersect, `null` for a self row, and an **upper bound**, being from
        vertices to the other surface.

        Refusals: `subject_not_found`, `other_not_found`, `no_meshes`.
        """
        return backend.send(
            "check_intersections",
            params={
                "name": arguments.validated_subject(name),
                "other": arguments.validated_text(other, "other", "omit it to measure inside "
                                                  "the first subject"),
                "include_self": arguments.validated_flag(include_self, "include_self"),
                "region": _validated_region(region),
            },
        )
