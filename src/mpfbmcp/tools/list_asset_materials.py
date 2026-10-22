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

``refresh`` lifts that, matching ``mpfb_list_rigs`` and ``mpfb_list_assets``.
``AssetService.invalidate_alternative_materials_cache()`` exists and clears the
cache **for every asset**, not only the one being listed - there is no
per-asset invalidator - so a refreshed call is a side effect on what any other
tool asking about a *different* asset will see next. The response says so
through ``cache_invalidated`` rather than leaving it implicit.
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
            title="List Asset Materials",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_list_asset_materials(name: str, refresh: bool = False) -> dict[str, object]:
        """
        List the alternative materials that ship beside one equipped MHCLO
        asset - the other colours of a hat - and name the one it is wearing
        now. Changes nothing about the character.

        **These are not in `mpfb_list_assets`' answer.** That tool lists MPFB's
        asset library sections; alternative materials live in the asset's own
        directory instead. This is the only catalogue for them, and it is what
        `mpfb_set_asset_material` consumes.

        `name` is the **asset's** own Blender object name, as
        `mpfb_list_objects` reports it or as `mpfb_add_asset` returned it in
        `asset_object_name`.

        **The answer is a snapshot.** MPFB caches this scan per asset and
        nothing invalidates that cache on its own, so a material added to the
        asset's directory after the first call for that asset - in this
        Blender session - will not appear. `refresh=true` clears the cache
        first, along with MPFB's pack metadata; `cache_invalidated` says
        whether it did. That clear is global -
        every asset's cached list is dropped, not only this one's - which is
        why the default stays `false`.

        `result` carries `asset_object_name`, `object_type`, `asset_source` and
        the `asset_subdir` searched; `default_material`, the absolute path the
        asset's own MHCLO names, with `exists` saying whether that file is
        there, or null with `default_material_reason` saying why not;
        `current_alternative_material`, the fragment recorded on the object
        now; `materials`, one entry per alternative with `path`, `fragment`,
        `name`, `is_default` and the attribution `mpfb_list_assets` reports
        (`license`, `author`, `source_url`, `packs`; null when no pack claims
        the file, which means unknown) - MPFB does **not** filter the asset's own
        material out of this scan, so the default usually appears and is
        flagged rather than removed; `count`; `search_roots`, the directories
        actually scanned, so "this hat has no other colours" is distinguishable
        from "the hat's asset source no longer resolves";
        `attribution_conflicts`; and `cache_invalidated`.

        An object that is not an asset comes back as `found: false`, or with an
        empty list and an explanation, never as an error.
        """
        # `result` (built in bridge/mpfb_bridge/commands/list_asset_materials.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "list_asset_materials",
            params={
                "name": arguments.validated_asset_name(
                    name, what="an equipped asset",
                    because=("Alternative materials are found in the asset's own directory, "
                             "so there is nothing to list without knowing which asset.")),
                # Not truthiness: refresh="false" would clear a cache every other asset relies on.
                "refresh": arguments.validated_flag(refresh, "refresh"),
            },
        )
