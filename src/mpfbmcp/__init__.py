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
            "or a rig to add, use mpfb_list_assets or mpfb_list_rigs: both name "
            "each entry the way the adding function will want it."
        ),
    )

    from mpfbmcp.tools import (
        create_human, get_object_info, get_status, list_assets, list_objects,
        list_rigs)
    create_human.register(mcp)
    get_object_info.register(mcp)
    get_status.register(mcp)
    list_assets.register(mcp)
    list_objects.register(mcp)
    list_rigs.register(mcp)

    mcp.run(transport="stdio")
    return 0
