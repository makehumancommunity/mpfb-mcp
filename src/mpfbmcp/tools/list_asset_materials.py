"""
The ``mpfb_list_asset_materials`` tool: which other materials does this asset have?

The catalogue ``mpfb_set_asset_material`` consumes, and the reason it is a tool
of its own rather than a filter on ``mpfb_list_assets``: **alternative materials
are not an asset library section.** They are MHMAT files sitting in the asset's
own directory, found by scanning the asset type's roots for ``*.mhmat`` whose
path contains the asset's parent directory name. Nothing in ``mpfb_list_assets``'
answer names them, and nothing could - it lists sections, and this is not one.

Read-only, and it always answers. An asset with no alternatives and an asset
whose recorded source no longer resolves are different situations, so the
response reports the roots that were actually searched and the ``asset_source``
they were searched for, per
[How tools name things that can be added](../../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added).

One caution belongs in the tool docstring rather than only here:
``AssetService.alternative_materials_for_asset()`` **caches per**
``(asset_source, asset_subdir)`` in a module-level dict that nothing invalidates
automatically, so this answer is a snapshot taken the first time any tool asked
about this asset in this Blender session. A material dropped into the asset's directory afterwards is
on disk and applicable and will not appear here. That is the mirror image of
``mpfb_list_targets``' staleness note: there MPFB's own panels are stale and this
package is current, and here it is this package that is stale.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import codegen
from mpfbmcp.connection import send_code


def _validated_name(name: object) -> str:
    """Shape only. Whether the name is an equipped asset is answered in Blender."""
    if not isinstance(name, str):
        raise ValueError("name must be a string, got {!r}".format(name))
    if not name.strip():
        raise ValueError(
            "name must be the Blender object name of an equipped asset, as mpfb_list_objects or "
            "mpfb_add_asset reports it. Alternative materials are found in the asset's own "
            "directory, so there is nothing to list without knowing which asset.")
    return name


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List Asset Materials",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_list_asset_materials(name: str) -> dict[str, object]:
        """
        List the alternative materials that ship beside one equipped MHCLO
        asset - the other colours of a hat - and name the one it is wearing
        now. Changes nothing.

        **These are not in `mpfb_list_assets`' answer.** That tool lists MPFB's
        asset library sections; alternative materials live in the asset's own
        directory instead. This is the only catalogue for them, and it is what
        `mpfb_set_asset_material` consumes.

        `name` is the **asset's** own Blender object name, as
        `mpfb_list_objects` reports it or as `mpfb_add_asset` returned it in
        `asset_object_name`.

        **The answer is a snapshot.** MPFB caches this scan per asset and
        nothing invalidates that cache, so a material added to the asset's
        directory after the first call for that asset - in this Blender
        session - will not appear. Restart Blender if a newly installed
        material is missing.

        `result` carries `asset_object_name`, `object_type`, `asset_source` and
        the `asset_subdir` searched; `default_material`, the absolute path the
        asset's own MHCLO names, with `exists` saying whether that file is
        there, or null with `default_material_reason` saying why not;
        `current_alternative_material`, the fragment recorded on the object
        now; `materials`, one entry per alternative with `path`, `fragment`,
        `name` and `is_default` - MPFB does **not** filter the asset's own
        material out of this scan, so the default usually appears and is
        flagged rather than removed; `count`; and `search_roots`, the
        directories actually scanned, so "this hat has no other colours" is
        distinguishable from "the hat's asset source no longer resolves".

        An object that is not an asset comes back as `found: false`, or with an
        empty list and an explanation, never as an error.
        """
        code = codegen.assemble(
            "list_asset_materials.py",
            bootstrap="raising",
            params={
                "name": _validated_name(name),
            },
        )
        # `result` (built in codegen/payloads/list_asset_materials.py) is plain
        # JSON-safe data, so strict_json=True surfaces a clear error if that ever
        # stops being true.
        return send_code(code, strict_json=True)
