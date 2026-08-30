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
    "main",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module


def main() -> int:
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
            "mpfb_add_rig returns; attach the clothes and then finish it with "
            "mpfb_generate_rigify_rig, which is not undoable. To change an existing "
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
            "mpfb_refit_human."
        ),
    )

    from mpfbmcp.tools import (
        add_rig, create_human, generate_rigify_rig, get_macro_details,
        get_object_info, get_status, get_target_stack, list_assets, list_objects,
        list_rigs, list_targets, refit_human, set_macro_details, set_targets,
        symmetrize_targets)
    add_rig.register(mcp)
    create_human.register(mcp)
    generate_rigify_rig.register(mcp)
    get_macro_details.register(mcp)
    get_object_info.register(mcp)
    get_status.register(mcp)
    get_target_stack.register(mcp)
    list_assets.register(mcp)
    list_objects.register(mcp)
    list_rigs.register(mcp)
    list_targets.register(mcp)
    refit_human.register(mcp)
    set_macro_details.register(mcp)
    set_targets.register(mcp)
    symmetrize_targets.register(mcp)

    mcp.run(transport="stdio")
    return 0
