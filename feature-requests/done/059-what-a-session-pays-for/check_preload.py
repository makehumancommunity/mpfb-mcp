# SPDX-License-Identifier: GPL-3.0-or-later

"""
What a client receives from ``mpfb-mcp`` before any work happens, read as a client reads it.

FR 059's requirements are held by ``tests/test_description_budget.py`` and
``tests/test_vocabulary.py`` on the server ``build_server()`` builds. This is the other half:
it starts the installed ``mpfb-mcp`` command as a subprocess over stdio, the way an MCP client
configuration does, and prints what crossed the pipe - the instructions' length and where the
conventions end, the published schema total, and whether an explicit ``null`` and a wrong type
are treated as the tests say. ``mpfb_list_docs`` needs no Blender, so none is needed here.

It cannot say what a *particular* client then shows a model; that takes a fresh session of that
client, which the request records by hand.

Run from the repository root, with the package installed::

    python3 feature-requests/059-what-a-session-pays-for/check_preload.py
"""

from __future__ import annotations

__all__ = ()

import asyncio
import json
import shutil
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_CONVENTIONS_END = "named in `temporarily_included`."


async def _check() -> int:
    command = shutil.which("mpfb-mcp")
    if command is None:
        print("mpfb-mcp is not on PATH; install the package first (pip install -e .)")
        return 2
    failures = []
    async with stdio_client(StdioServerParameters(command=command, args=[])) as streams:
        async with ClientSession(*streams) as session:
            initialized = await session.initialize()
            text = initialized.instructions or ""
            end = text.find(_CONVENTIONS_END)
            end = -1 if end < 0 else end + len(_CONVENTIONS_END)
            print("server {:s} {:s}".format(initialized.serverInfo.name,
                                            initialized.serverInfo.version))
            print("instructions: {:d} characters, {:d} bytes; the conventions end at {:d}".format(
                len(text), len(text.encode("utf-8")), end))
            if len(text) > 4000:
                failures.append("instructions over 4,000 characters")
            if not 0 < end <= 2048:
                failures.append("conventions do not end within 2,048 characters")

            tools = (await session.list_tools()).tools
            schemas = sum(len(json.dumps(tool.inputSchema, separators=(",", ":")).encode())
                          for tool in tools)
            descriptions = sum(len((tool.description or "").encode()) for tool in tools)
            longest = max(tools, key=lambda tool: len(tool.description or ""))
            print("{:d} tools: {:d} B of descriptions (longest {:s}, {:d} characters), "
                  "{:d} B of input schemas".format(
                      len(tools), descriptions, longest.name, len(longest.description or ""),
                      schemas))
            generated = [tool.name for tool in tools
                         if '"title"' in json.dumps(tool.inputSchema)
                         or '{"type": "null"}' in json.dumps(tool.inputSchema)]
            print("schemas still carrying a title or a null option: {!r}".format(generated))
            if generated:
                failures.append("generated schema keys published")
            missing_output = [tool.name for tool in tools if tool.outputSchema is None]
            if missing_output:
                failures.append("tools without an outputSchema: {!r}".format(missing_output))

            accepted = await session.call_tool("mpfb_list_docs", {"topic": None})
            refused = await session.call_tool("mpfb_list_docs", {"topic": 5})
            print("explicit null: {:s}; wrong type: {:s}".format(
                "refused" if accepted.isError else "accepted",
                "refused" if refused.isError else "accepted"))
            if accepted.isError:
                failures.append("an explicit null was refused: {:s}".format(
                    accepted.content[0].text))
            if not refused.isError:
                failures.append("a wrong type was accepted")
    for failure in failures:
        print("FAIL: " + failure)
    print("ok" if not failures else "{:d} failure(s)".format(len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_check()))
