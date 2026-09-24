"""
The ``mpfb_set_macro_details`` tool: change a character's phenotype in place.

The first tool in this package that modifies an existing character, and the
write half of the pair completed by ``mpfb_get_macro_details``. Before it, an
agent asked to make a character older had to delete it and build a new one,
losing every asset, rig and detail target on it.

Every slider is optional, and an omitted one means "leave unchanged" - which is
the reason the eleven arguments are flat scalars rather than one nested
macro-detail dict. A dict cannot express "not mentioned" without a sentinel, and
a nested argument is a shape a caller gets subtly wrong (misspelling ``race``,
nesting ``cupsize`` under it) in ways a flat schema rejects for free. The
round trip is preserved on the *output* side instead: this tool and
``mpfb_get_macro_details`` both return the full nested dict MPFB itself uses.

The range check here is not belt and braces. MPFB's own macro properties are
**unclamped** - the definitions under ``entities/objectproperties/humanproperties``
carry a ``default`` but no ``min``/``max``, and it is the scene-level proxy
property behind MPFB's sliders that constrains them to 0.0-1.0. A value of 5.0
would be stored happily and produce an interpolation the macro table has no
corner cases for.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

# The tool's argument name paired with the MPFB property it writes. They differ
# for the three race weights: MPFB stores them as plain "asian"/"caucasian"/
# "african" properties, while the arguments carry the prefix that groups them -
# and that keeps them consistent with mpfb_create_human's own parameter names.
_ARGUMENT_TO_PROPERTY = (
    ("gender", "gender"),
    ("age", "age"),
    ("muscle", "muscle"),
    ("weight", "weight"),
    ("proportions", "proportions"),
    ("height", "height"),
    ("cupsize", "cupsize"),
    ("firmness", "firmness"),
    ("race_asian", "asian"),
    ("race_caucasian", "caucasian"),
    ("race_african", "african"),
)


def _validated_slider(argument: str, value: object) -> float:
    """MPFB stores these unclamped, so 0.0-1.0 is enforced here or nowhere."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # A bool is an int in Python, so True would otherwise be stored as 1.0
        # under the guise of a number the caller never wrote.
        raise ValueError(
            "{:s} must be a number between 0.0 and 1.0 or omitted, got {!r}".format(
                argument, value))
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(
            "{:s} must be between 0.0 and 1.0, got {!r}".format(argument, value))
    return float(value)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Macro Details",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_set_macro_details(
        name: str | None = None,
        gender: float | None = None,
        age: float | None = None,
        muscle: float | None = None,
        weight: float | None = None,
        proportions: float | None = None,
        height: float | None = None,
        cupsize: float | None = None,
        firmness: float | None = None,
        race_asian: float | None = None,
        race_caucasian: float | None = None,
        race_african: float | None = None,
        prune: bool = True,
        refit: bool = False,
    ) -> dict[str, object]:
        """
        Change a MakeHuman character's macro details - its phenotype sliders -
        and rebuild the shape from them, exactly as MPFB's own sliders do.

        **Every slider is optional and an omitted one is left alone**, so a
        relative change is one call: read the character with
        `mpfb_get_macro_details`, then pass only what should differ. Passing a
        slider its current value is not the same as omitting it - it is
        reported in `changes` with `previous == new`.

        Sliders are 0.0-1.0, and 0.5 is neutral for all but the three race
        weights, whose neutral is 0.33 each. `age` runs 0.0 = baby, 0.1875 =
        child, 0.5 = young adult, 1.0 = old; `gender` 0.0 = fully female, 1.0 =
        fully male. **The three race weights are independent and MPFB does not
        normalize them**: setting `race_asian` to 1.0 does not reduce the other
        two, and the default sums to 0.99. Set all three when changing one, or
        read `race_sum` in the response and decide.

        `prune` (default true, MPFB's own) deletes macro shape keys whose
        weight falls to zero, keeping the shape key list from growing as
        sliders move. `refit` (default false, MPFB's own) re-fits clothes and
        the rig to the new body shape. **The default is false because a refit
        is expensive, not because it is unnecessary**: leave it false, read
        `assets_possibly_stale`, and call `mpfb_refit_human` once after a
        series of changes rather than paying for a refit per slider.

        `result` carries `changes` (one `{name, previous, new}` per slider
        named), the full `macro_details` after the change, `race_sum`,
        `macro_shapekeys_before`/`_after` with `shapekeys_removed` and
        `shapekeys_added` - all four naming shape keys as the mesh stores them
        (`$md-$as-$fe-$yn`), so a name from here can be looked up rather than
        only read - plus `recalculated`, `refit_performed`,
        `assets_possibly_stale` and `basemesh_name`.

        Two situations answer rather than fail, both with `changes: []`: a
        subject that resolves to no basemesh (`found: false`), and a basemesh
        that is not ready to be modified - left in edit mode, or with no shape
        keys at all (`ready: false`, `blocked_by` naming which). A call that
        names no slider also does nothing, deliberately, rather than paying for
        a shape rebuild that would change nothing; it comes back `performed:
        false`.
        """
        supplied = (
            gender, age, muscle, weight, proportions, height, cupsize, firmness,
            race_asian, race_caucasian, race_african,
        )
        changes = [
            {"argument": argument, "property": prop,
             "value": _validated_slider(argument, value)}
            for (argument, prop), value in zip(_ARGUMENT_TO_PROPERTY, supplied)
            if value is not None
        ]

        # `result` (built in bridge/mpfb_bridge/commands/set_macro_details.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "set_macro_details",
            params={
                "name": arguments.validated_subject(name),
                "changes": changes,
                "prune": arguments.validated_flag(prune, "prune"),
                # Not truthiness: refit="false" would pay for a full asset refit.
                "refit": arguments.validated_flag(refit, "refit"),
            },
        )
