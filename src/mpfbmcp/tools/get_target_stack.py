"""
The ``mpfb_get_target_stack`` tool: what is actually shaping this character.

The read half of the detail-target pair completed by ``mpfb_set_targets``, and
the counterpart of ``mpfb_get_macro_details`` one level down: that one reads the
eleven phenotype numbers, this one reads the modeling targets stacked on top of
them.

The answer carries two views of the same facts, because the two levels are
addressed differently. ``targets`` is one entry per shape key, addressed by
``shapekey_name`` - the level at which a user-installed target is reachable and
the level ``mpfb_set_targets``' ``targets`` list takes. ``modifiers`` rolls those
up into the ``target.json`` categories MPFB's own sliders manipulate, which is
what ``mpfb_set_targets``' ``modifiers`` list takes and what the user sees in the
modeling panel.

Nothing here validates a section or category name, and this tool takes none: the
vocabulary is partly synthesized from the user's own target directories and is
answered from inside Blender.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

# A dressed, heavily modeled character can carry several hundred shape keys, and
# the macro stack alone is typically a dozen. The ceiling is here so that an
# unbounded call is capped rather than answered with the whole stack.
MAX_LIMIT = 1000


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Target Stack",
            # Reads shape keys off the mesh. Nothing is loaded, activated,
            # selected or recalculated.
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_target_stack(name: str | None = None,
                              include_macro: bool = False,
                              include_expressions: bool = False,
                              name_contains: str | None = None,
                              limit: int = 200,
                              offset: int = 0) -> dict[str, object]:
        """
        Read the modeling targets currently applied to a MakeHuman character -
        every shape key on its basemesh, and the modeling sliders they add up
        to. Changes nothing.

        **`result` has two views of the same facts, addressed differently.**

          - `targets` - one entry per shape key: `shapekey_name` (the raw
            Blender name, and the address `mpfb_set_targets`' `targets` list
            takes), `decoded_name` (readable; a name over 60 characters is
            stored encoded, and only the raw one works as an address), `value`,
            `kind` (`macro`/`expression`/`detail`/`unknown`), and where the
            target sits in MPFB's index: `section`, `category`, `side`,
            `polarity`, `listed_in_target_json`, all null for a user target
            belonging to no category.
          - `modifiers` - the same information rolled up per `target.json`
            category, each `{section, category, side, value}` with `value` in
            -1.0..+1.0. This is the view MPFB's own sliders show and the one
            that feeds straight back into `mpfb_set_targets`' `modifiers` list.
            Only categories with a non-zero reading appear; never paged, never
            filtered by `name_contains`.

        `asymmetries` lists the left/right categories whose two sides differ -
        which MPFB's own UI does not surface anywhere - and is what makes
        `mpfb_symmetrize_targets` an informed operation rather than a blind
        one. `basemesh_name` names the object the stack was read from.

        `include_macro` (default false) adds the `$md-` phenotype shape keys,
        which are `mpfb_get_macro_details`' subject; `include_expressions`
        (default false) adds the `!ex-` expression ones. `counts_by_kind`
        reports both counts whether or not they were included.

        **The answer is capped.** `limit` defaults to 200 and cannot exceed
        1000. Read `truncated` and `total_count` before concluding a target is
        not on this character, and narrow with `name_contains` rather than
        paging blindly; `counts_by_section` says where the entries are.

        **This tool sees one thing MPFB itself cannot.** MPFB excludes any
        shape key whose name *contains* "basis", not merely equals it, so a
        user target called `basis-nose-widen` is real, is deforming the mesh,
        and is invisible to every MPFB read and write. It is listed here with
        `visible_to_targetservice: false`, and it cannot be changed through
        `mpfb_set_targets` either.

        A subject that cannot be resolved to a basemesh is an answer, `found:
        false` with a sentence, not an error. A character whose macro numbers
        and macro shape keys have drifted apart is reported as it is, not
        repaired.
        """
        # `result` (built in bridge/mpfb_bridge/commands/get_target_stack.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "get_target_stack",
            params={
                "name": arguments.validated_subject(name),
                # Not truthiness: include_macro="false" would return the macro stack anyway.
                "include_macro": arguments.validated_flag(include_macro, "include_macro"),
                "include_expressions": arguments.validated_flag(
                    include_expressions, "include_expressions"),
                "name_contains": arguments.validated_text(
                    name_contains, "name_contains", "omit it to match every shape key"),
                "limit": arguments.validated_count(limit, "limit", MAX_LIMIT),
                "offset": arguments.validated_count(offset, "offset", None),
            },
        )
