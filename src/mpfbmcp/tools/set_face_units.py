"""
The ``mpfb_set_face_units`` tool: compose a character's face directly.

The write half of the face-unit pair started by ``mpfb_get_face_units``. It
wraps ``FaceService.set_expression()`` - MPFB's composer, not its expression
*library* - to set the 52 ARKit ``!ex-`` shape keys directly, in one batched
call, the ``mpfb_set_targets`` idiom: a round trip costs about as much as
applying fifty units, so send a whole face as one call.

**Validated here is shape only.** Each entry is a dict with exactly
`face_unit` (a non-empty string) and `value` (0.0-1.0, the range Blender
clamps a shape key to). It is the shape key's value, and `value` is what
``mpfb_get_target_stack`` and ``mpfb_set_targets`` call the same number; it
was ``weight`` until FR 037, and ``weight`` is now only an expression row's
multiplier, in the expression tools. Whether `face_unit` names a real ARKit unit is checked
in the payload against MPFB's own `ARKIT_FACEUNITS`, per
[validate before crossing the socket](../../../specifications/tool-interface.md#validate-before-crossing-the-socket) -
a copy kept here could drift, and the payload's refusal comes back naming the
closest legal spellings.

**A composed face is transient.** It is not saved by `mpfb_save_preset` and is
destroyed by anything that rebuilds MPFB's expression-library stack
(`mpfb_apply_expressions`, loading a preset). It lives in the `.blend` and
nowhere else until `mpfb_save_expression` writes it to an expression file. This
description is where the two-mechanism model is explained for every expression
tool, per FR 027's description-budget requirement; the others point here. Every
answer carries the computed `matches_stack` / `unexplained_face_units` rather
than a fixed warning, so the common case - nothing on the stack - reads as
nothing to worry about.

**`refit` defaults to true**, unlike every other refitting tool and unlike
MPFB's composer panel (whose `auto_refit` is false; FR 026 said otherwise, and
FR 027 corrected it). Composing across MCP is one batched call rather than a
dragged slider, and garments do not follow the face without a refit.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

_ENTRY_KEYS = ("face_unit", "value")

# An entry key renamed by FR 037, and what it became. The per-entry counterpart
# of arguments.RETIRED_ARGUMENTS: a caller still sending `weight` is told the new
# spelling rather than only that the key is unknown.
_RETIRED_ENTRY_KEYS = {"weight": "value"}

# Generous, but not unbounded: MPFB only has 52 face units, so a caller sending
# more than this made a mistake worth catching locally.
MAX_ENTRIES = 200


def _validated_face_units(value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("face_units must be a list of objects or omitted, got {!r}".format(
            value))
    if len(value) > MAX_ENTRIES:
        raise ValueError(
            "face_units must hold at most {} entries, got {}".format(MAX_ENTRIES, len(value)))

    checked = []
    for position, entry in enumerate(value):
        where = "face_units[{}]".format(position)
        if not isinstance(entry, dict):
            raise ValueError("{} must be an object, got {!r}".format(where, entry))
        unknown = sorted(key for key in entry if key not in _ENTRY_KEYS)
        if unknown:
            raise ValueError(
                "{} has unknown key(s) {}; known keys are {}".format(
                    where,
                    ", ".join(
                        "{} (now called {})".format(key, _RETIRED_ENTRY_KEYS[key])
                        if key in _RETIRED_ENTRY_KEYS else key
                        for key in unknown),
                    ", ".join(_ENTRY_KEYS)))

        face_unit = entry.get("face_unit")
        if not isinstance(face_unit, str):
            raise ValueError("{} face_unit must be a string, got {!r}".format(where, face_unit))
        if not face_unit.strip():
            raise ValueError("{} face_unit must not be empty or whitespace".format(where))

        value = entry.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            # A bool is an int in Python, so True would otherwise be stored as
            # 1.0 under the guise of a number the caller never wrote.
            raise ValueError(
                "{} value must be a number between 0.0 and 1.0, got {!r}".format(where, value))
        # 0.0..1.0 and not wider: a raw shape key value, which Blender clamps
        # to that range. A negative here would silently store 0.0.
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(
                "{} value must be between 0.0 and 1.0, got {!r}".format(where, value))

        checked.append({"face_unit": face_unit, "value": float(value)})
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Face Units",
            readOnlyHint=False,
            # mode "replace" zeroes every unit not named in this call, and a
            # composed face survives nothing anyway (see the module docstring).
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_set_face_units(name: str | None = None,
                            face_units: list[dict] | None = None,
                            mode: str = "merge",
                            refit: bool = True) -> dict[str, object]:
        """
        Compose a MakeHuman character's face from ARKit face units - the same
        52-unit vocabulary `mpfb_get_face_units` reads and MPFB's own composer
        panel edits, applied directly to the `!ex-` shape keys.

        **Send the whole expression as one call.** `face_units` is a list of
        `{face_unit, value}`, `value` in 0.0-1.0. Call `mpfb_get_face_units`
        first if you need the exact 52 legal names, grouped by region in
        `known_face_units`.

        **Nothing is written unless every name resolves.** Every `face_unit` is
        checked against MPFB's own vocabulary before anything is touched; one
        misspelled name refuses the whole call and `unknown_face_units` names
        it together with the closest legal spellings. This tool also refuses
        outright when the `faceunits01` asset pack is not installed, since
        every target file would then be missing - check
        `mpfb_get_face_units`' `faceunits01_installed` first if unsure.

        **`mode` is `"merge"` by default**, matching MPFB: a face unit not
        mentioned in `face_units` is left exactly as it was. `"replace"` zeroes
        every one of the 52 units before applying this call's entries, which is
        the difference between "smile a bit more" and "make this face and
        nothing else"; `removed_by_replace` names what it zeroed.

        `refit` (default **true**, unlike every other refitting tool here:
        composing is normally one call) re-fits the mesh assets and the rig afterwards.

        **A composed face is transient.** MPFB has two mechanisms over one set
        of shape keys: this tool writes them directly, while saved expressions
        live on a stack (`mpfb_get_expression`) that `mpfb_apply_expressions`
        and preset loads rebuild the face from, **discarding anything composed
        here**. `result`'s `matches_stack` is false when the face now differs
        from the stack, and `unexplained_face_units` lists what the next rebuild
        would overwrite. `mpfb_save_expression` keeps a composed face.

        `result` carries `changes` - one entry per unit actually written, with
        `previous_value` and `new_value` - plus `loaded_from_disk` (units whose
        shape key had to be created from a target file on this call),
        `could_not_load` (a unit whose target file was missing even though the
        pack passed its own install probe - a partially installed pack), and
        `skipped_absent_at_zero` (a unit requested at `0.0` with no shape key
        yet, which is left alone rather than created). `basemesh_name` names
        the object actually changed. A subject that cannot be resolved
        (`found: false`) and a basemesh in edit mode (`ready: false`) are
        answers, not errors.
        """
        # `result` (built in bridge/mpfb_bridge/commands/set_face_units.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "set_face_units",
            params={
                "name": arguments.validated_subject(name),
                "face_units": _validated_face_units(face_units),
                # Checked here as well as in Blender: "replace" zeroes the whole face,
                # and no misspelling of either word is safe to guess at.
                "mode": arguments.validated_mode(mode),
                "refit": arguments.validated_flag(refit, "refit"),
            },
        )
