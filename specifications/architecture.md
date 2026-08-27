# Architecture

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents). For the
> current, concrete module layout, see [CLAUDE.md](../CLAUDE.md)'s Architecture section.

These are the standing architectural principles new tools are expected to follow. They exist
to keep mpfb-mcp installable and runnable without a local checkout of either MPFB or
blender_mcp, and to keep it working across MPFB installs regardless of how the extension was
installed.

## No direct dependency on MPFB or blender_mcp

mpfb-mcp never imports MPFB or blender_mcp Python code directly, and is never run *inside*
Blender. Every interaction with MPFB crosses two boundaries:

1. mpfb-mcp → blender_mcp add-on, over blender_mcp's existing TCP socket protocol (JSON
   request + NUL-delimited response, `BLENDER_MCP_HOST`/`BLENDER_MCP_PORT`). mpfb-mcp
   maintains its own minimal client for this protocol rather than depending on blender_mcp's
   package, so it installs standalone.
2. blender_mcp add-on → MPFB, inside the Blender process, by `exec()`-ing Python source that
   mpfb-mcp generated and sent as a string.

A consequence: mpfb-mcp's own test suite cannot exercise real MPFB behavior — it can only
verify the wire protocol and the generated code (see the "Tests" section of individual
feature requests). Exercising a tool against real MPFB requires a running Blender with MPFB
and blender_mcp installed and enabled, and is a manual/integration verification step, not
part of the unit test suite.

## Resolving MPFB from generated code

MPFB is a Blender *extension* with no stable, guessable absolute import path — the top-level
package name depends on which extension repository the user installed it from (e.g.
`bl_ext.user_default.mpfb`, `bl_ext.repo.mpfb`). Generated code must never hardcode a guessed
path. Instead it uses the resolution mechanism MPFB itself documents and uses in its own test
suite (`mpfb2/mpfb/__init__.py`, `mpfb2/test/tests/__init__.py`): scan `sys.modules` for a
module whose name ends in `"mpfb"`, then read the classes it needs off the
`MPFB_CONTEXTUAL_INFORMATION["SERVICES"]` dict that module publishes. Every tool that needs
an MPFB service class should reuse this same bootstrap rather than inventing another
resolution strategy.

## One module per tool

Each MCP tool lives in its own module exposing a `register(mcp)` function that attaches the
tool to the passed `FastMCP` instance, following blender_mcp's own tool-module convention.
This keeps tools independently testable and keeps the server's own `main()` a flat list of
`register()` calls.

## Validate before crossing the socket

Where a tool takes structured input (e.g. macro-detail sliders, which are only meaningful in
`0.0`-`1.0`), validate it in the tool function *before* generating and sending code. A bad
call should fail fast and locally, not round-trip to Blender to fail there.

## Response shape

Tools return blender_mcp's response envelope largely as-is: `{"status": "ok", "result": ...}`
or `{"status": "error", "message": ...}` (optionally `stdout`/`stderr`). Callers — including
future mpfb-mcp tools composing on top of others — must check `status` rather than assume
success. This mirrors blender_mcp's own tools and avoids inventing a second error convention.
