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
            "extension installed and enabled in that Blender instance."
        ),
    )

    from mpfbmcp.tools import create_human
    create_human.register(mcp)

    mcp.run(transport="stdio")
    return 0
