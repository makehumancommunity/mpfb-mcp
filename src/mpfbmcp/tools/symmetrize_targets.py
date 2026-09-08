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

from mpfbmcp import codegen
from mpfbmcp.connection import send_code

_DIRECTIONS = ("left_to_right", "right_to_left")


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


def _validated_section(section: object) -> str | None:
    if section is None:
        return None
    if not isinstance(section, str):
        raise ValueError("section must be a string or omitted, got {!r}".format(section))
    if not section.strip():
        # An explicitly empty value and an omitted one arise from different
        # mistakes, so the empty one is never quietly treated as the omission.
        raise ValueError(
            "section must not be empty or whitespace; omit it to cover every section")
    return section


def _validated_direction(direction: object) -> str:
    """One of two strings, and the only argument with no default.

    Validated by *shape* here, unlike a section name: the vocabulary is two
    fixed values this tool defines itself, not something read out of MPFB.
    """
    if direction not in _DIRECTIONS:
        raise ValueError(
            "direction must be one of {}, got {!r}".format(", ".join(_DIRECTIONS), direction))
    return direction


def _validated_flag(argument: str, value: object) -> bool:
    if not isinstance(value, bool):
        # Deliberately not truthiness: `dry_run="false"` would otherwise write.
        raise ValueError("{} must be a bool, got {!r}".format(argument, value))
    return value


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
        changes made while it is on and explicitly leaves previously set values
        alone, so a character that has already drifted asymmetric has no repair
        path in MPFB's UI. Call `mpfb_get_target_stack` first: its `asymmetries`
        field lists exactly which categories differ and by how much.

        **This is destructive and there is no undo across the socket.** It
        overwrites values the user may have set on purpose. `direction` is
        required - `"left_to_right"` or `"right_to_left"` - because which half
        of a face is the good one is not something a tool can guess, and
        guessing wrong destroys work. **Run it with `dry_run: true` first**: the
        answer lists exactly the changes a real run would make, and writes
        nothing.

        `name` is any object in the character's family - the basemesh, its rig,
        or a garment fitted to it. Omit it to use the active object.

        `section` restricts the operation to one `target.json` section, so
        "make the eyes symmetric" does not also flatten deliberate asymmetry in
        the hands. Omit it to cover every section.

        `prune` (default true, MPFB's own) deletes a target's shape key once its
        value reaches zero. `refit` (default false, MPFB's own) re-fits clothes
        and the rig afterwards; read `assets_possibly_stale` and call
        `mpfb_refit_human` when the modeling is done.

        Only categories with `has_left_and_right: true` are considered - the
        pairing comes from `target.json`'s `opposites` table, never from
        matching `l-`/`r-` name prefixes, which would be a guess.

        Returns blender_mcp's response envelope. `result` carries `changed` (per
        category: both sides' values before, the value after, and every target
        file touched - `targets` is `null` rather than `[]` under
        `dry_run: true`, because which files a write would touch is only
        knowable by doing the write), `already_symmetric`, and `skipped` for a
        category whose
        target file could not be found - one unreachable target is reported
        rather than abandoning the rest of the body. A subject that cannot be
        resolved (`found: false`) and a basemesh in edit mode or without shape
        keys (`ready: false`) are answers, not errors.

        **Branch on `performed`.** Every mutating tool here reports that field
        under the same name, a real boolean, true exactly when the character was
        changed. Under `dry_run: true` it is false even though `changed` has
        entries in it: those are the writes that *would* happen.
        """
        code = codegen.assemble(
            "symmetrize_targets.py",
            bootstrap="raising",
            shared=["target_categories.py", "performed.py"],
            params={
                "name": _validated_name(name),
                "direction": _validated_direction(direction),
                "section": _validated_section(section),
                "dry_run": _validated_flag("dry_run", dry_run),
                "prune": _validated_flag("prune", prune),
                "refit": _validated_flag("refit", refit),
            },
        )
        # `result` (built in codegen/payloads/symmetrize_targets.py) is plain
        # JSON-safe data - values and paths are coerced there - so
        # strict_json=True surfaces a clear error if that ever stops being true.
        return send_code(code, strict_json=True)
