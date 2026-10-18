"""
The ``mpfb_set_material_settings`` tool: write procedural material settings, all or nothing.

The write half of ``mpfb_get_material_settings``
([FR 040](../../../feature-requests/done/040-procedural-material-settings/README.md)),
and the third batched tool after ``mpfb_set_targets`` and
``mpfb_set_face_units``. Three optional lists mirror the preset's three keys,
and every entry is resolved inside Blender before any is written.

**Validated here is shape only.** Each entry is an object with exactly the
keys its section takes; ``socket`` - and ``group`` or ``object_name`` - are
non-empty strings; exactly one of ``value`` (a finite number, not a ``bool``)
and ``color`` (four finite, non-negative numbers, not ``bool``s) is present;
and no socket is named twice in one call, which is refused here as
``mpfb_apply_expressions`` refuses a repeated fragment. **Whether a group or a
socket exists is not checked here**, nor which of ``value`` and ``color`` a
socket takes, nor a float's range: those are MPFB's node trees, read live and
answered as ``resolution_errors``. A copy of the vocabulary here would drift
the first time MPFB reshaped a tree.

``value`` and ``color`` are two keys rather than one carrying either a number
or a list, because no name in this package carries two JSON types
(``tests/test_vocabulary.py``). A three-number ``color`` is refused with a
sentence saying alpha is required; a negative component because Blender would
store it as zero; a component above 1.0 is allowed, since Blender keeps it.
"""

from __future__ import annotations

__all__ = (
    "MAX_ENTRIES",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

# What each section's entries address a socket by, besides the socket itself.
_OWNER_KEYS = {"eyes": None, "skin": "group", "color_adjustments": "object_name"}

# Generous: the layered skin's nine groups hold about two hundred sockets.
MAX_ENTRIES = 400


def _validated_color(where: str, color: object) -> list[float]:
    if not isinstance(color, list) or not all(arguments.is_finite_number(channel) for channel in color):
        raise ValueError(
            "{} color must be a list of four finite numbers, scene-linear RGBA, got {!r}".format(
                where, color))
    if len(color) != 4:
        raise ValueError(
            "{} color must have four components, scene-linear RGBA; alpha is required, "
            "got {} component(s)".format(where, len(color)))
    if any(channel < 0 for channel in color):
        raise ValueError(
            "{} color components must not be negative, since Blender would store zero; "
            "got {!r}".format(where, color))
    return [float(channel) for channel in color]


def _validated_value(where: str, entry: dict) -> dict[str, object]:
    """``{"value": float}`` or ``{"color": [four floats]}``, exactly one of them."""
    if ("value" in entry) == ("color" in entry):
        raise ValueError(
            "{} needs exactly one of value (a float socket) and color (a colour "
            "socket)".format(where))
    if "color" in entry:
        return {"color": _validated_color(where, entry["color"])}
    if not arguments.is_finite_number(entry["value"]):
        raise ValueError("{} value must be a finite number, got {!r}".format(
            where, entry["value"]))
    return {"value": float(entry["value"])}


def _validated_entries(section: str, value: object, seen: set) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("{} must be a list of objects or omitted, got {!r}".format(
            section, value))

    owner = _OWNER_KEYS[section]
    names = ("socket",) if owner is None else (owner, "socket")
    allowed = names + ("value", "color")
    checked = []
    for position, entry in enumerate(value):
        where = "{}[{}]".format(section, position)
        if not isinstance(entry, dict):
            raise ValueError("{} must be an object, got {!r}".format(where, entry))
        unknown = sorted(key for key in entry if key not in allowed)
        if unknown:
            raise ValueError("{} has unknown key(s) {}; known keys are {}".format(
                where, ", ".join(unknown), ", ".join(allowed)))

        normalized: dict[str, object] = {}
        for key in names:
            text = entry.get(key)
            if not isinstance(text, str):
                raise ValueError("{} {} must be a string, got {!r}".format(where, key, text))
            if not text.strip():
                raise ValueError("{} {} must not be empty or whitespace".format(where, key))
            normalized[key] = text

        normalized.update(_validated_value(where, entry))

        key = (section,) + tuple(normalized[name] for name in names)
        if key in seen:
            raise ValueError("{} names a socket already named earlier in this call".format(
                where))
        seen.add(key)
        checked.append(normalized)
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Material Settings",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_set_material_settings(name: str | None = None,
                                   eyes: list[dict] | None = None,
                                   skin: list[dict] | None = None,
                                   color_adjustments: list[dict] | None = None,
                                   ) -> dict[str, object]:
        """
        Change a MakeHuman character's procedural material settings - iris
        colours, the LAYERED skin, the tint of hair and garments - as one
        all-or-nothing batch that survives `mpfb_save_preset` and
        `mpfb_create_human_from_preset`. Take section, group and socket names
        from `mpfb_get_material_settings`.

        - `eyes`: `{socket, value | color}`
        - `skin`: `{group, socket, value | color}`, `group` as the read keys it
        - `color_adjustments`: `{object_name, socket, value | color}`

        Exactly one of `value` (a float socket) and `color` (a colour socket).
        **A `color` is four scene-linear RGBA numbers**, like the read's
        `settings`, not sRGB: a colour picked by eye comes out too light
        unless converted.

        **Nothing is written unless every entry resolves**; `resolution_errors`
        gives each failure's `reason`: section not applicable, unknown group
        or socket (with `closest`), wrong key for the socket's kind, a float
        outside its range, or a **linked** socket, which a write cannot change.
        Most layered region colours are linked from the `color` group, and
        `write_instead` names the socket to set.

        On the layered skin, `color`'s `SkinColor` shows fully with no diffuse
        texture and over one only as far as `SkinOverride` raises it; each
        region colour has its own `*Override`. A colour adjustment mixes
        `Color1` with the texture by `Factor`, so a low `Factor` is flat
        colour without texture detail.

        `mpfb_set_skin`, `mpfb_set_asset_material` and re-adding the eyes
        rebuild a material from MPFB's defaults, discarding these settings.

        `result`'s `changes` lists each socket in request order with
        `previous_value`/`new_value` and `previous_srgb_hex`/`new_srgb_hex`;
        `materials_written` names other objects sharing a written material,
        which changed too.
        """
        subject = arguments.validated_subject(name)
        seen: set = set()
        entries = {
            "eyes": _validated_entries("eyes", eyes, seen),
            "skin": _validated_entries("skin", skin, seen),
            "color_adjustments": _validated_entries(
                "color_adjustments", color_adjustments, seen),
        }
        if len(seen) > MAX_ENTRIES:
            raise ValueError("a call may name at most {} sockets, got {}".format(
                MAX_ENTRIES, len(seen)))
        return backend.send(
            "set_material_settings",
            params={"name": subject, **entries},
        )
