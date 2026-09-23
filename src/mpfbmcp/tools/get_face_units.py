"""
The ``mpfb_get_face_units`` tool: what a character's face is doing right now.

The read half of the face-unit pair completed by ``mpfb_set_face_units``. A
character these twenty-five other tools build has a phenotype, detail morphs,
a rig, garments and a skin - and, until this pair, one fixed neutral
expression, because the ``!ex-`` shape keys that drive an ARKit face were the
one part of MPFB's modelling surface no tool reached.

**Two things are reported whether or not a subject resolves**, because neither
depends on one: ``known_face_units``, the vocabulary the write tool accepts,
grouped by region so an agent learns it without downloading 52 names in this
description; and ``faceunits01_installed``, since an all-zero answer means two
different things - a neutral face, or an asset pack that was never installed -
and MPFB itself gives no way to tell them apart.

Validates nothing: this is a read, and it never loads a target or creates a
shape key.
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


def _validated_flag(argument: str, value: object) -> bool:
    if not isinstance(value, bool):
        # Deliberately not truthiness: "false" and 0 are how a caller signals a
        # bool it did not manage to build, and accepting them quietly would make
        # `refresh="false"` bust a cache it should have left alone.
        raise ValueError("{} must be a bool, got {!r}".format(argument, value))
    return value


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Face Units",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_face_units(name: str | None = None,
                            include_zero: bool = False,
                            refresh: bool = False) -> dict[str, object]:
        """
        Read the ARKit face units currently applied to a MakeHuman character's
        face - the live `!ex-` shape key values `mpfb_set_face_units` writes.
        Changes nothing.

        `result`'s `face_units` is one entry per face unit: `face_unit` (the bare ARKit
        name, e.g. `"jawOpen"`), `weight`, and `shapekey_present` - whether a
        real shape key backs this value or MPFB is reporting a default for a
        unit that has never been touched. Defaults to the non-zero units only;
        `include_zero` (default false) returns all 52.

        `known_face_units` is **always** present regardless of whether a
        subject resolves: every legal name `mpfb_set_face_units` will accept,
        grouped by facial region (brow, eye, cheek, jaw, mouth, nose, tongue)
        the way MPFB's own composer panel lays out its sliders.

        `faceunits01_installed` is **always** present too, and is the one
        thing that separates "a neutral face" from "the faceunits01 asset pack
        was never installed" - both read as every unit at `0.0`, and MPFB
        itself gives no other way to tell them apart. That check is cached for
        the Blender session; `refresh` (default false) busts the cache, which
        matters if the pack was installed after this Blender started.

        A subject that cannot be resolved to a basemesh is an answer, `found:
        false` with a sentence, not an error; `basemesh_name` names the object
        the answer was actually read from.
        """
        # `result` (built in bridge/mpfb_bridge/commands/get_face_units.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "get_face_units",
            params={
                "name": _validated_name(name),
                "include_zero": _validated_flag("include_zero", include_zero),
                "refresh": _validated_flag("refresh", refresh),
            },
        )
