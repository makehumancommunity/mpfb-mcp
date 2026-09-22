"""
The ``mpfb_get_status`` tool: reports whether MPFB is present and usable.

Deliberately does no interpretation on this side of the socket. All the
classification lives in the generated code (see
``mpfbmcp.codegen.payloads.get_status``), so that
"MPFB isn't there" and "MPFB is there but broken" come back as ordinary
successful answers rather than as an error envelope a caller has to guess at.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import backend


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get MPFB Status",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_status() -> dict[str, object]:
        """
        Report whether MPFB is loaded and usable in the connected Blender, and
        how it is configured. Takes no arguments, changes nothing.

        Call this first when any other MPFB tool fails unexpectedly: those
        tools fail with a bare error when MPFB is missing or broken, and this
        one tells the two apart.

        `result` always carries:

          - `state`: "absent" (MPFB not loaded), "not_initialized" (loaded, but
            registration did not complete - installed and broken, or
            half-registered) or "ok". All three are normal answers, not errors.
          - `message`: one sentence naming the state and the likely next step,
            suitable for showing to a user verbatim.
          - `candidate_modules`: every loaded module name ending in "mpfb".
            Normally one; two or more means MPFB is installed twice, which
            explains erratic behavior from the other MPFB tools.
          - `package`, `enabled`, `blender.version`.

        With `state` "not_initialized" or "ok" it also carries `version` and
        `build_info`. With `state` "ok" it additionally carries
        `is_source_dist`, `addon_installation_path`, `paths` (each entry a
        `path` plus a `configured` flag), `asset_roots`, `asset_packs`,
        `rigify_available`, and `blender.platform` /
        `blender.meets_mpfb_minimum` / `blender.mpfb_minimum_version`.

        Parts of the result (`paths.second_root` and anything derived from it)
        are scene-scoped and change when a different .blend is loaded. Re-call
        rather than cache.
        """
        # `result` (built in bridge/mpfb_bridge/commands/get_mpfb_status.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send("get_mpfb_status")
