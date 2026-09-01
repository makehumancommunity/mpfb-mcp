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

from mpfbmcp import codegen
from mpfbmcp.connection import send_code

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


def _validated_flag(argument: str, value: object) -> bool:
    if not isinstance(value, bool):
        # Deliberately not truthiness: "false" and 0 are how a caller signals a
        # bool it did not manage to build, and accepting them quietly would make
        # `refit="false"` pay for a full asset refit.
        raise ValueError("{:s} must be a bool, got {!r}".format(argument, value))
    return value


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
        slider its current value is not the same as omitting it - it is reported
        in `changed` with `previous == new`.

        `name` is any object in the character's family - the basemesh, its rig,
        or a garment fitted to it. Omit it to use the active object. The
        basemesh is resolved from it and `basemesh_name` names the object that
        was actually modified.

        Sliders are 0.0-1.0, and the scale is not always linear or obvious:
        `age` runs 0.0 = baby, 0.1875 = child, 0.5 = young adult, 1.0 = old;
        `gender` 0.0 = fully female, 1.0 = fully male; `weight`, `muscle`,
        `height`, `proportions`, `cupsize` and `firmness` all run minimum to
        maximum with 0.5 in the middle.

        **The three race weights are independent, and MPFB does not normalize
        them.** Setting `race_asian` to 1.0 does not reduce the other two, and
        the default 0.33 each sums to 0.99. Set all three when changing one, or
        read `race_sum` in the response and decide.

        `prune` (default true, MPFB's own) deletes macro shape keys whose weight
        falls to zero, keeping the shape key list from growing as sliders move.
        `refit` (default false, MPFB's own) re-fits clothes and the rig to the
        new body shape. **The default is false because a refit is expensive, not
        because it is unnecessary**: changing the shape moves the body under
        everything fitted to it. When `refit` is false the response reports
        `assets_possibly_stale`; act on it by calling `mpfb_refit_human` once
        after a series of changes rather than paying for a refit per slider.

        Returns blender_mcp's response envelope. On `status: "ok"` and
        `found: true`, `result` carries `changed` (one `{name, previous, new}`
        per slider named), the full `macro_details` after the change,
        `race_sum`, `macro_shapekeys_before`/`_after` with `shapekeys_removed`
        and `shapekeys_added` - all four naming shape keys as the mesh stores
        them (`$md-$as-$fe-$yn`), so a name from here can be looked up rather
        than only read - `refit_performed`, and `basemesh_name`.

        Two situations answer rather than fail, both with `changed: []`: a
        subject that cannot be resolved to a basemesh (`found: false`), and a
        basemesh that is not ready to be modified - left in edit mode, or with
        no shape keys at all (`ready: false`, with `blocked_by` naming which).
        A call that names no slider at all also does nothing, deliberately: it
        answers immediately instead of paying for a full shape rebuild that
        would change nothing.
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

        code = codegen.assemble(
            "set_macro_details.py",
            bootstrap="raising",
            params={
                "name": _validated_name(name),
                "changes": changes,
                "prune": _validated_flag("prune", prune),
                "refit": _validated_flag("refit", refit),
            },
        )
        # `result` (built in codegen/payloads/set_macro_details.py) is plain
        # JSON-safe data - property values are coerced to float there - so
        # strict_json=True surfaces a clear error if that ever stops being true.
        return send_code(code, strict_json=True)
