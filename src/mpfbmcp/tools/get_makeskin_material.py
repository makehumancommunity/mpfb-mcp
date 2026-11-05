"""
The ``mpfb_get_makeskin_material`` tool: what a MakeSkin material holds.

``mpfb_get_material_settings`` reports only ``diffuseIntensity`` for a garment, since
that is all a preset saves, so which maps are wired, at what strength and in which
colour space was unknown without a script
([FR 049](../../../feature-requests/done/049-makeskin-materials/README.md)).

Takes one optional subject, so there is nothing to check here but its shape. The
reading is the bridge's ``shared/makeskin.py``, and what it answers is held to the
writer by ``bridge/test/tests/eee_composite/makeskin_roundtrip_test.py``.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get MakeSkin Material",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_makeskin_material(name: str | None = None) -> dict[str, object]:
        """
        Read the MakeSkin material in a mesh's first slot: which maps are wired,
        from which files, and which numbers actually do anything. Any mesh is
        accepted. Changes nothing.

        **`textures`, `values` and `metadata` can be sent to
        `mpfb_set_makeskin_material` unchanged.** `result`:

        - `textures`, keyed by slot, for each slot holding an image: `path` when
          the file holds what the image holds, otherwise `image`, the name in
          this file (no file, unsaved changes or packed pixels). Beside it, which
          the writer ignores: `image_name`, `wired`, `resolved_path`,
          `file_exists`, `size`, `color_space`, `packed`, `unsaved_changes`, and
          `strength` with `strength_value` naming the value that holds it.
        - `empty_slots`: slots whose node holds no image.
        - `values`: `{"value": n}`, with `range`, or `{"color": [r, g, b, a]}`,
          scene-linear, with `srgb_hex`. **`in_effect`** on each: `roughness`
          beside a roughness map is not, and `overridden_by` names the slot;
          `needs_slot` names a missing map the value would scale.
        - `values_absent`: what this tree has no socket for, each with the slots
          that would give it one.
        - `metadata`: what an MHMAT would carry from this object, with
          `metadata_unset` listing the keys still at MPFB's default.
        - `material_name`, `material_slots`, `material_shared_with`,
          `known_slots`, `material_identified_as` and `recognized_by`.

        MPFB identifies an untextured MakeSkin material as `gameengine`, so
        `recognized_by` is `template_nodes` when a material was accepted by
        holding only the nodes MakeSkin's template names.

        Refusals: `subject_not_found`, `not_a_mesh`, `no_material`, and
        `not_makeskin` with `material_identified_as`.
        """
        return backend.send(
            "get_makeskin_material",
            params={"name": arguments.validated_subject(name)},
        )
