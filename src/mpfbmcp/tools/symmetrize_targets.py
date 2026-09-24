"""
The ``mpfb_symmetrize_targets`` tool: repair a detail stack that has drifted.

**This has no MPFB equivalent.** MPFB's own ``symmetry`` setting only mirrors
changes made while it is switched on - its property description says in so many
words that toggling it does not affect previously set values - so a character
that is already asymmetric cannot be put right through MPFB's UI except by
dragging every slider by hand. This is therefore a deliberate addition rather
than a wrapper, which the tool docstring says out loud.

Deliberately *not* ``TargetService.symmetrize_shape_key()``, which mirrors
vertex coordinates inside one custom shape key using ``hm08.mirror`` and belongs
to MakeTarget and asset authoring rather than to modeling.

``direction`` is required rather than defaulted: which half of a character's
face is the good one is not something a tool can guess, and guessing wrong
destroys work. ``dry_run`` exists for the same reason - this operation
overwrites values the user may have set deliberately, and there is no undo
across the socket.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

_DIRECTIONS = ("left_to_right", "right_to_left")


def _validated_direction(direction: object) -> str:
    """One of two strings, and the only argument with no default.

    Validated by *shape* here, unlike a section name: the vocabulary is two
    fixed values this tool defines itself, not something read out of MPFB.
    """
    if direction not in _DIRECTIONS:
        raise ValueError(
            "direction must be one of {}, got {!r}".format(", ".join(_DIRECTIONS), direction))
    return direction


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Symmetrize Detail Targets",
            readOnlyHint=False,
            # Overwrites values the user may have set deliberately, and pruning
            # deletes shape keys. The most destructive tool in this package.
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_symmetrize_targets(direction: str,
                                name: str | None = None,
                                section: str | None = None,
                                dry_run: bool = False,
                                prune: bool = True,
                                refit: bool = False) -> dict[str, object]:
        """
        Make a MakeHuman character's detail targets left/right symmetric, by
        copying one side's modeling onto the other.

        **MPFB itself cannot do this.** Its `symmetry` setting only mirrors
        changes made while it is on and leaves previously set values alone, so
        a character that has already drifted asymmetric has no repair path in
        MPFB's UI. Call `mpfb_get_target_stack` first: its `asymmetries` field
        lists which categories differ and by how much.

        **This is destructive and there is no undo across the socket.** It
        overwrites values the user may have set on purpose. `direction` is
        required - `"left_to_right"` or `"right_to_left"` - because which half
        of a face is the good one is not something a tool can guess. **Run it
        with `dry_run: true` first**: the answer lists exactly the changes a
        real run would make, and writes nothing.

        `section` restricts the operation to one `target.json` section, so
        "make the eyes symmetric" does not also flatten deliberate asymmetry in
        the hands; omit it to cover every section. Only categories with
        `has_left_and_right: true` are considered, paired through
        `target.json`'s `opposites` table rather than by matching `l-`/`r-`
        name prefixes, which would be a guess.

        `prune` (default true, MPFB's own) deletes a target's shape key once
        its value reaches zero. `refit` (default false, MPFB's own) re-fits
        clothes and the rig afterwards; read `assets_possibly_stale` and call
        `mpfb_refit_human` when the modeling is done.

        `result` carries `changed` - per category, both sides' values before,
        the value after, and every target file touched, with `targets` being
        `null` rather than `[]` under `dry_run: true`, because which files a
        write would touch is only knowable by doing the write - plus
        `already_symmetric`, `basemesh_name`, and `skipped` for a category
        whose target file could not be found, since one unreachable target is
        reported rather than abandoning the rest of the body.

        Under `dry_run: true`, `performed` is false even though `changed` has
        entries in it: those are the writes that *would* happen. A subject that
        cannot be resolved (`found: false`) and a basemesh in edit mode or
        without shape keys (`ready: false`) are answers, not errors.
        """
        # `result` (built in bridge/mpfb_bridge/commands/symmetrize_targets.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "symmetrize_targets",
            params={
                "name": arguments.validated_subject(name),
                "direction": _validated_direction(direction),
                "section": arguments.validated_text(
                    section, "section", "omit it to cover every section"),
                # Not truthiness: dry_run="false" would write.
                "dry_run": arguments.validated_flag(dry_run, "dry_run"),
                "prune": arguments.validated_flag(prune, "prune"),
                "refit": arguments.validated_flag(refit, "refit"),
            },
        )
