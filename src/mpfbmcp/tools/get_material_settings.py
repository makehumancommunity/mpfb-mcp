"""
The ``mpfb_get_material_settings`` tool: the procedural material settings a preset saves.

The read half of the pair ``mpfb_set_material_settings`` completes
([FR 040](../../../feature-requests/done/040-procedural-material-settings/README.md)).
Three materials MPFB builds without a file - procedural eyes, the layered skin,
and the MakeSkin colour adjustment on hair and garments - are serialized into a
preset by ``HumanService``, and nothing else in this package could see them.
This tool reports them section for section **as the serializer would save
them**, which the bridge's own test checks by serializing the same character
and comparing.

**No socket or group name is known on this side of the socket.** They are
MPFB's, read off the live node every call, and they drift with MPFB - the eye
tree especially, which mpfb2's bug 306 work is reshaping. So the vocabulary is
in the answer and never in this description, per
[names inside MPFB's node trees are read live](../../../specifications/mpfb-integration.md#names-inside-mpfbs-node-trees-are-read-live-never-tabulated).

**``section`` was added because the answer was measured**, not in advance: a
character with procedural eyes, a layered skin and six mesh assets answers
22 KB, the skin's nine groups 16 KB of it. It is this package's own vocabulary
rather than MPFB's - the preset's three keys - so it is checked here, like
``mode``.
"""

from __future__ import annotations

__all__ = (
    "SECTIONS",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

# The preset's three keys, as both material settings tools name them.
SECTIONS = ("eyes", "skin", "color_adjustments")


def validated_section(value: object) -> str | None:
    """One of :data:`SECTIONS`, or ``None`` for all of them."""
    if value is None:
        return None
    if value not in SECTIONS:
        raise ValueError("section must be one of {} or omitted, got {!r}".format(
            ", ".join(SECTIONS), value))
    return value  # type: ignore[return-value]


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Material Settings",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_material_settings(name: str | None = None,
                                   section: str | None = None) -> dict[str, object]:
        """
        Read a MakeHuman character's procedural material settings - exactly
        what `mpfb_save_preset` saves for them - for
        `mpfb_set_material_settings` to change. Changes nothing.

        `result` has three sections: `eyes` (procedural eyes), `skin` (the
        LAYERED skin) and `color_adjustments` (one record per mesh asset, for
        the MakeSkin node on its Base Color). One that does not apply says
        `applies: false` and a `reason`. `section` (`"eyes"`, `"skin"` or
        `"color_adjustments"`) reads one and reports the others as `null`; a
        full answer can pass 20 KB.

        Per node - the eyes, each group in `skin.groups` (keyed `color`,
        `body`, `face`, ... as the preset keys them), each colour adjustment -
        keyed by MPFB's own socket names:
        - `settings`: each value as the preset holds it, a float or a colour
          as four **scene-linear** RGBA numbers. A write takes these as is.
        - `srgb_hex`: `#rrggbb` per colour socket, derived for reading only.
        - `ranges`: `[min, max]` where a float declares one, `null` for an
          open end; `values_outside_range` names any value already outside.
        - `linked`: sockets driven by another node (`from_node`,
          `from_socket`), which a write cannot change. Most layered region
          colours are linked from the `color` group.
        - `material_shared_with`: other objects a write would change too.

        A colour adjustment record also has `object_name`, `object_type`,
        `uuid` (the preset's key) and `node_name`: `diffuseIntensity`, or on
        an asset with an AO map `aoMix`, whose only writable socket is the AO
        strength - MPFB saves that node, and the tint is out of reach. The
        eyes never keep one. An unresolved subject is `found: false`.
        """
        return backend.send(
            "get_material_settings",
            params={
                "name": arguments.validated_subject(name),
                "section": validated_section(section),
            },
        )
