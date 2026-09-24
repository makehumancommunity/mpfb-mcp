"""
The ``mpfb_get_expression`` tool: what a character is wearing, and whether that
explains its face.

Reads MPFB's applied-expressions stack off the basemesh and answers the one
question nothing in MPFB answers: **does the stack account for the face?** MPFB
has two mechanisms writing one set of shape keys - the composer
(``mpfb_set_face_units``) writes them directly, and the library
(``mpfb_apply_expressions``, a preset load) rebuilds them from the stack,
clearing first. Composed work is therefore destroyed by the next library change,
silently. ``matches_stack`` and ``unexplained_face_units`` are that comparison;
the same shared computation answers it in ``mpfb_apply_expressions`` and
``mpfb_set_face_units``, so the three cannot disagree.

**The live face-unit values are not restated** - they are
``mpfb_get_face_units``' answer, and two tools reporting the same 52 numbers is
two answers that can drift apart. The boundary is stated in both descriptions.

The two-mechanism model is explained once, in ``mpfb_set_face_units``' own
description, and pointed at from here rather than repeated, per FR 027's
description-budget requirement.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import backend


def _validated_name(name: object) -> str | None:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValueError("name must be a string or omitted, got {!r}".format(name))
    if not name.strip():
        raise ValueError(
            "name must not be empty or whitespace; omit it to use the active object")
    return name


def _validated_refresh(refresh: object) -> bool:
    if not isinstance(refresh, bool):
        # Deliberately not truthiness: `refresh="false"` is a true value.
        raise ValueError("refresh must be a bool, got {!r}".format(refresh))
    return refresh


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Expression",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_expression(name: str | None = None,
                            refresh: bool = False) -> dict[str, object]:
        """
        Read which saved expressions a MakeHuman character is wearing (MPFB's
        applied-expressions stack) and whether they explain its live face.
        Changes nothing. For the raw live face-unit values, call
        `mpfb_get_face_units`; this tool reports only how they differ from the
        stack.

        `result`'s `applied_expressions` is one row per expression: `fragment`,
        `weight`, `resolved` and `path`. A row whose file cannot be found or
        read (`resolved: false`, counted in `unresolved_count`) contributes
        nothing to the face. `aggregate` is the face the stack produces;
        `clamped_face_units` names units whose sum across rows passed 1.0.

        **`matches_stack`** is false when the live face differs from
        `aggregate`; `unexplained_face_units` then lists each such unit with
        its `live` and `from_stack` values. That is composed work (see
        `mpfb_set_face_units`) that the next `mpfb_apply_expressions` call or
        preset load will overwrite; `mpfb_save_expression` keeps it.

        `faceunits01_installed` is always present; `refresh` re-probes for it.
        An unresolvable subject is `found: false`, not an error;
        `basemesh_name` names the object actually read.
        """
        # `result` (built in bridge/mpfb_bridge/commands/get_expression.py) is
        # plain JSON-safe data.
        return backend.send(
            "get_expression",
            params={
                "name": _validated_name(name),
                "refresh": _validated_refresh(refresh),
            },
        )
