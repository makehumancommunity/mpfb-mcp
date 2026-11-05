"""
The ``mpfb_check_mesh_asset`` tool: whether a mesh is ready to be written as an asset.

MPFB's ``ClothesService.mesh_is_valid_as_clothes()`` said ``all_checks_ok: true`` for a
draft whose coat had inward normals, 77 face pairs through the hakama's waist, 25
through the body and 14 of one flap through the other. The inverted normals were found
only by plotting the mesh outside Blender. This reports MPFB's answer unchanged beside
the numbers that would have found them
([FR 048](../../../feature-requests/done/048-measuring-mesh-assets/README.md)).

**Named for what MakeClothes writes**, all three kinds of mesh asset, since the
[glossary](../../../specifications/tool-interface.md#the-glossary) keeps "clothes" for
quoting MPFB.

``sections`` is this package's own vocabulary, like ``section`` on
``mpfb_get_material_settings``, and is checked here as well as there. Everything about
what is measured is in the bridge's ``shared/mesh_asset_report.py``.
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

SECTIONS = ("validator", "components", "uv", "textures", "metadata", "write_state")


def _validated_sections(value: object) -> list[str] | None:
    """A list of distinct :data:`SECTIONS`, or ``None`` for all of them."""
    checked = arguments.validated_names(value, "sections", "all of them")
    if checked is None:
        return None
    unknown = [name for name in checked if name not in SECTIONS]
    if unknown:
        raise ValueError("sections knows only {}, got {}".format(
            ", ".join(SECTIONS), ", ".join(unknown)))
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Check Mesh Asset",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_check_mesh_asset(
        name: str | None = None,
        basemesh: str | None = None,
        sections: list[str] | None = None,
    ) -> dict[str, object]:
        """
        Measure whether a mesh is ready to be written as a mesh asset: a
        garment, hair, or any other. Changes nothing, so it is safe to call
        after every change. **It gives numbers, not a verdict.**

        `name` is the mesh, which need not be marked as an asset yet;
        `object_type` says what it is marked as, if anything. `basemesh` is the
        body, otherwise found among the mesh's relatives, then the selection,
        then the file; `basemesh_resolved_by` says which.

        `sections` narrows the answer, the others being `null`; omit it for all
        six. With no xref cache built, `validator` takes several seconds.
        `result`:

        - `validator`: MPFB's report unchanged. Its `all_checks_ok` covers
          **vertex groups, scale and face type only**, and is not this tool's
          answer: a coat with inward normals passes.
        - `components`: per connected component, largest first, capped
          (`component_count`, `components_truncated`) in `rows`: `faces`,
          `vertices`, `vertex_groups`, `bounds`; **`outward_fraction`**, the
          share of faces whose normal agrees with the nearest body surface's,
          so near 1.0 is right for a single layer, near 0 is inside out and near
          0.5 is a closed shell with thickness; `fit_offset`, signed
          `min` and `max` metres from the unmasked body, negative being inside
          it; and `overlap`, with `body` (`face_pairs`, `face_pairs_unmasked`,
          as `mpfb_check_intersections` means them), `self` and
          `other_components`. A garment's flap through another flap is `self`
          when the two are connected. Measured at the viewport's `subdiv_levels`.
        - `uv`: `islands`, `overlapping_islands` with `overlapping_pairs`,
          `faces_outside_unit_square`, `texels_per_metre` over the islands
          (`min`, `max`) against the largest image, and `lowest_islands`.
          `applies: false` with no UV map.
        - `textures`: a row per image node: `slot`, `image_name`, `path`,
          `file_exists`, `size`, `color_space`, `packed`, `unsaved_changes`.
        - `metadata`: `makeclothes`, `makeskin` and `general`, each key with
          its `value` and `set`, false meaning MPFB's default rather than a
          choice. `warnings` names a `license` or `author` the first two would
          write differently.
        - `write_state`: `xref_cache_exists`, `asset_source` and
          `asset_source_resolves`, `delete_group` (`name`, `exists_on_basemesh`,
          `vertices`) and the subdivision levels; `warnings` says when a viewport
          level above 0 would make MPFB's exporter write an OBJ its MHCLO does
          not describe.

        Refusals: `subject_not_found`, `not_a_mesh`, `subject_is_basemesh`,
        `basemesh_not_found`, `not_a_basemesh`, `unknown_section` and
        `basemesh_ambiguous` with `candidates`.
        """
        return backend.send(
            "check_mesh_asset",
            params={
                "name": arguments.validated_subject(name),
                "basemesh": arguments.validated_text(
                    basemesh, "basemesh", "omit it to have the body found"),
                "sections": _validated_sections(sections),
            },
        )
