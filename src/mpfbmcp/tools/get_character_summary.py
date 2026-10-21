"""
The ``mpfb_get_character_summary`` tool: one character, one answer.

What an agent needs to know before it changes a character - phenotype, rig,
equipped assets, skin, modeling targets, face - in one call rather than the five or
six it replaces, and small enough to read every time.

**It is never a second opinion.** Each section is read inside Blender by the
same implementation its detailed tool uses, and carries a subset of that
tool's fields under the same names, so a field learned from one reads the same
in the other and the two cannot disagree about one character in one state. That
is also why the summary reports no fact a detailed tool does not: it selects
and it counts, and the one thing it cuts - the target rollup, past a cap - it
says it cut. Since there is no map from section to tool in the response, the
description names the detailed tool behind each section, once.

It takes one argument and validates only its shape. Everything about what the
answer holds is decided, and tested, in
``bridge/mpfb_bridge/commands/get_character_summary.py``.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Character Summary",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_character_summary(name: str | None = None) -> dict[str, object]:
        """
        Summarize one MakeHuman character before changing it, in one call:
        what it is, what it wears, and what its face is doing. Changes
        nothing. Call this first; call a detailed tool only for what the
        summary leaves out.

        `result` carries one section per detailed tool: a subset of its
        fields under the same names, read by the same code, so the two never
        disagree.

          - `phenotype` - `mpfb_get_macro_details`.
          - `rig` - `mpfb_get_object_info` on the rig; `null` when there is
            none. `rigify_role` says whether it is a meta rig or generated.
          - `equipped_assets` - `mpfb_get_object_info`'s related objects: every
            equipped garment, body part and body proxy, by type then name. Not
            capped.
          - `skin` - `mpfb_get_object_info` on the basemesh.
          - `targets` - `mpfb_get_target_stack` with its defaults: the
            `modifiers` rollup, `asymmetries` and the counts. **Capped**: if
            `rollup_truncated`, only the largest entries are here, and
            `modifier_count`/`asymmetry_count` give the whole.
          - `face` - `mpfb_get_face_units` (non-zero units only) and
            `mpfb_get_expression` (`applied_expressions`, `matches_stack`,
            `unexplained_face_units`). A non-empty `unexplained_face_units` is
            composed work the next `mpfb_apply_expressions` call destroys.
          - `placement` - `mpfb_place_character`'s `root_name`, `position`,
            `facing`, `tilted`, `footprint` and `subrigs_broken`.

        On a miss `found` is false and every section is `null` or empty.
        """
        # `result` (built in bridge/mpfb_bridge/commands/get_character_summary.py)
        # is plain JSON-safe data, serialized by the bridge before it answers.
        return backend.send(
            "get_character_summary",
            params={"name": arguments.validated_subject(name)},
        )
