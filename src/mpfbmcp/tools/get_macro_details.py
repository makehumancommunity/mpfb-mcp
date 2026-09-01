"""
The ``mpfb_get_macro_details`` tool: a character's phenotype, as MPFB sees it.

The read half of the pair completed by ``mpfb_set_macro_details``, and the first
tool that reports a *character's* state rather than the install's or the scene's.
Its subject may be any object in the character's family - the rig, a shirt, the
basemesh itself - because that is what ``mpfb_list_objects`` will have shown the
caller; the basemesh is resolved from it and named in the answer.

Two pairs of fields exist because a macro slider and the shape it produces are
not the same thing and can disagree. ``macro_target_stack`` is what the current
property values *mean* in target terms, and ``current_macro_shapekeys`` is what
is actually on the mesh; a difference between them is a character whose numbers
and whose shape have drifted apart, which is the state ``mpfb_set_macro_details``
repairs. Likewise ``macro_details`` beside ``default_macro_details``: without
the latter there is no way to tell a deliberately average character from an
untouched one without hardcoding 0.5.

Nothing here is validated against a vocabulary on this side of the socket, and
nothing is normalized. In particular the three race weights are reported exactly
as MPFB stores them, summed rather than scaled - see ``race_sum``.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import codegen
from mpfbmcp.connection import send_code


def _validated_name(name: object) -> str | None:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValueError("name must be a string or omitted, got {!r}".format(name))
    if not name.strip():
        # An explicitly empty name and an omitted one arise from different
        # mistakes, so the empty one is never quietly treated as "use the
        # active object": that would answer a question the caller did not ask.
        raise ValueError(
            "name must not be empty or whitespace; omit it to use the active object")
    return name


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Macro Details",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_macro_details(name: str | None = None) -> dict[str, object]:
        """
        Read a MakeHuman character's macro details - its phenotype sliders:
        gender, age, muscle, weight, proportions, height, cupsize, firmness and
        the three race weights. Changes nothing.

        Call this before `mpfb_set_macro_details`: that tool leaves unnamed
        sliders alone, so knowing the current values is what makes a relative
        change ("a bit older") possible.

        `name` is any object in the character's family - the basemesh, its rig,
        or a garment fitted to it - as reported by `mpfb_list_objects`. The
        basemesh is resolved from it, and `basemesh_name` says which object was
        actually read. Omit `name` to use the active object. An unresolvable
        name, nothing active, or an object with no basemesh among its relatives
        each come back as `found: false` with a `message`, not as an error.

        Returns blender_mcp's response envelope. On `status: "ok"` and
        `found: true`, `result` carries:

          - `macro_details`: the current values, in MPFB's own nested shape
            (`gender`, `age`, ..., plus `race` holding `asian`, `caucasian` and
            `african`). `mpfb_set_macro_details` returns the same shape, but
            takes its arguments flat: `race.asian` is set as `race_asian`.
          - `default_macro_details`: what MPFB considers neutral - every slider
            0.5, every race weight 0.33.
          - `race_sum` and `race_normalized`: **the three race weights are
            independent 0.0-1.0 properties and MPFB does not normalize them.**
            The default sums to 0.99; setting `race_asian` to 1.0 and leaving
            the others alone gives a character built from weights summing to
            1.66, which is legal and probably not what was wanted.
          - `macro_target_stack` and `macro_target_count`: what those values
            mean in target terms, each entry carrying the `target_fragment`
            MPFB loads from disk and the `shapekey_name` it becomes. **Neither
            is a name any tool accepts as input**; they explain the shape, they
            do not address it.
          - `current_macro_shapekeys`: the macro shape keys actually on the mesh
            now, under the names they are stored with - which is the same
            vocabulary as `macro_target_stack`'s `shapekey_name`, so the two
            can be compared directly. If they disagree, the properties have been
            changed without a recalculation, and `mpfb_set_macro_details` will
            repair it. `current_macro_shapekeys_decoded` is the same list in
            MPFB's readable form (`macrodetail-asian-female-young` rather than
            `$md-$as-$fe-$yn`); it is for reading, not for comparing.
          - `has_shapekeys` and `is_human_project`: a mesh tagged as a basemesh
            but never built by MPFB reads back a full set of macro properties
            that mean nothing. These two are how that is told apart.
          - `basemesh_name`, `subject_name` and `subject_resolved_by`
            ("name" or "active").

        The answer describes one character at one moment. Re-read rather than
        cache it, and note that an active-object answer is stale as soon as the
        user clicks elsewhere.
        """
        code = codegen.assemble(
            "get_macro_details.py",
            bootstrap="raising",
            params={"name": _validated_name(name)},
        )
        # `result` (built in codegen/payloads/get_macro_details.py) is plain
        # JSON-safe data - the property values are coerced to float there - so
        # strict_json=True surfaces a clear error if that ever stops being true.
        return send_code(code, strict_json=True)
