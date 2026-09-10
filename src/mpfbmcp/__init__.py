"""
MCP server for MPFB (MakeHuman Plugin For Blender).

Proof-of-concept: exposes MPFB-specific tools that run inside a running
Blender instance, by sending generated Python code to the *existing,
unmodified* blender_mcp add-on over its TCP socket (see connection.py).

This requires:
  - Blender running with MPFB and the blender_mcp add-on installed & enabled.
  - The blender_mcp add-on's socket server started (from its preferences panel).
  - This server's client configuring BLENDER_MCP_HOST / BLENDER_MCP_PORT to
    match, if not using the defaults (localhost:9876).
"""

from __future__ import annotations

__all__ = (
    "build_server",
    "main",
)

import inspect

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module


def _shipped_without_source_indentation(mcp: FastMCP) -> None:
    """Send the docstrings the way a reader of the source sees them.

    ``Tool.from_function()`` takes ``fn.__doc__`` verbatim, so every line of
    every tool description would otherwise cross the wire carrying the eight
    spaces it is indented by in the file: about 500 bytes per tool, 11 KB across
    the twenty-two, of whitespace an MCP client downloads before any work happens.
    ``inspect.cleandoc`` is what ``help()`` shows and what the docstrings are
    written to look like.

    Guarded rather than assumed, because it is the one place in this package
    that reaches into FastMCP's tool manager. If a future mcp release moves it,
    descriptions merely arrive indented again - and
    ``tests/test_description_budget.py`` is what fails, rather than a user's
    server at startup.
    """
    manager = getattr(mcp, "_tool_manager", None)
    list_tools = getattr(manager, "list_tools", None)
    if list_tools is None:
        return
    for tool in list_tools():
        if tool.description:
            tool.description = inspect.cleandoc(tool.description)


def build_server() -> FastMCP:
    """The configured server, built but not run.

    Separate from ``main()`` so that the tool surface can be inspected without
    starting a stdio transport: ``tests/test_description_budget.py`` measures
    what an MCP client downloads before any work happens, and measuring the real
    server rather than a list of its own is what keeps a newly registered tool
    inside the budget rather than outside it.
    """
    mcp = FastMCP(
        "mpfb-mcp",
        instructions=(
            "Tools for creating MakeHuman characters via the MPFB Blender add-on. "
            "Requires the blender_mcp add-on's socket server to be running inside "
            "Blender (see BLENDER_MCP_HOST / BLENDER_MCP_PORT), with the MPFB "
            "extension installed and enabled in that Blender instance. When an "
            "MPFB tool fails unexpectedly, call mpfb_get_status first: it reports "
            "whether MPFB is present, initialized and correctly configured. To act "
            "on a character this session did not create, find it with "
            "mpfb_list_objects and identify it with mpfb_get_object_info rather "
            "than guessing from Blender object names. To find an asset to apply "
            "or a rig to add, use mpfb_list_assets or mpfb_list_rigs, and "
            "mpfb_list_targets for the modeling morphs: each names its entries "
            "the way the acting function will want them. Order matters when "
            "building a character and MPFB reports no error when it is wrong: "
            "add the rig with mpfb_add_rig BEFORE attaching any clothes, since "
            "a garment is rigged only if a rig exists when it is attached and "
            "nothing rigs it afterwards. A rigify.* rig is only a meta rig when "
            "mpfb_add_rig returns; attach the clothes with mpfb_add_asset "
            "and then finish it with mpfb_generate_rigify_rig, which is not "
            "undoable. mpfb_add_asset equips one garment, body part or "
            "topology proxy per call and requires an asset_type - pass "
            "mpfb_list_assets' object_type, since MPFB's own default "
            "silently turns hair into clothes. Take an asset off with "
            "mpfb_remove_asset rather than by deleting the object, or the "
            "body stays masked under something that is no longer there. "
            "A character with no skin is grey: give it one with mpfb_set_skin, "
            "whose skin_type picks between five entirely different materials "
            "and defaults to MAKESKIN as MPFB's own panel does, not to the "
            "ENHANCED_SSS its service function defaults to. Applying a skin "
            "deletes every material already on the body, and on the body proxy "
            "too. To recolour a garment rather than the body, list its "
            "alternatives with mpfb_list_asset_materials - they are not in "
            "mpfb_list_assets' answer - and apply one with "
            "mpfb_set_asset_material. To change an existing "
            "character rather than create one, read its phenotype with "
            "mpfb_get_macro_details first and change only what should differ "
            "with mpfb_set_macro_details, which leaves unnamed sliders alone. "
            "For the individual morphs below the phenotype level, read "
            "mpfb_get_target_stack and write mpfb_set_targets - which is "
            "batched, so send a whole series of modeling changes as one call "
            "rather than one call each, and which applies nothing at all if any "
            "entry fails to resolve. mpfb_symmetrize_targets repairs a "
            "left/right asymmetry that MPFB itself has no way to undo; run it "
            "with dry_run first. "
            "Changing a body's shape moves it out from under everything fitted "
            "to it, so finish a series of modeling changes with one call to "
            "mpfb_refit_human. "
            "Neither of the two lookup tools acts on Blender at all: they hand "
            "out addresses for the client to retrieve, and neither fetches "
            "anything itself. mpfb_list_urls gives the community sites - where "
            "to download MPFB, get asset packs, ask on the forum, file a bug - "
            "and answers even when MPFB or Blender is unreachable, which is "
            "when those links matter most. mpfb_list_docs gives MPFB's "
            "developer documentation, one document per service and per file "
            "format, for when a tool response does not say how MPFB actually "
            "does something. Use them rather than composing a URL. "
            "Conventions every tool here shares, so that no single tool's "
            "description repeats them. Each returns blender_mcp's envelope: "
            "check `status` (\"ok\" or \"error\"), then read `result`. A tool "
            "acting on an existing character takes `name` - any object in that "
            "character's family, the basemesh, its rig or a garment fitted to "
            "it - or omit `name` to use whatever is active in Blender, and the "
            "response names the object actually worked on. A tool that cannot "
            "do what was asked answers rather than failing, so read `found` "
            "(the subject could not be resolved), `ready` and `blocked_by` (the "
            "world was not in a fit state, and which way) before concluding a "
            "call went wrong. Every tool that changes a character reports "
            "`performed`, a real boolean, true exactly when something changed; "
            "each keeps its own verb beside it (`added`, `applied`, `removed`, "
            "`generated`, `recalculated`, `refit_performed`) for the sentence, "
            "and the tool says where the two can differ. A capped listing "
            "always reports `truncated`, `total_count`, `offset` and `limit`: "
            "check `truncated` before concluding something is not installed."
        ),
    )

    from mpfbmcp.tools import (
        add_asset, add_rig, create_human, generate_rigify_rig, get_macro_details,
        get_object_info, get_status, get_target_stack, list_asset_materials, list_assets,
        list_docs, list_objects, list_rigs, list_targets, list_urls, refit_human, remove_asset,
        set_asset_material, set_macro_details, set_skin, set_targets, symmetrize_targets)
    add_asset.register(mcp)
    add_rig.register(mcp)
    create_human.register(mcp)
    generate_rigify_rig.register(mcp)
    get_macro_details.register(mcp)
    get_object_info.register(mcp)
    get_status.register(mcp)
    get_target_stack.register(mcp)
    list_asset_materials.register(mcp)
    list_assets.register(mcp)
    list_docs.register(mcp)
    list_objects.register(mcp)
    list_rigs.register(mcp)
    list_targets.register(mcp)
    list_urls.register(mcp)
    refit_human.register(mcp)
    remove_asset.register(mcp)
    set_asset_material.register(mcp)
    set_macro_details.register(mcp)
    set_skin.register(mcp)
    set_targets.register(mcp)
    symmetrize_targets.register(mcp)

    _shipped_without_source_indentation(mcp)
    return mcp


def main() -> int:
    build_server().run(transport="stdio")
    return 0
