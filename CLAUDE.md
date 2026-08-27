# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation

There is a [specifications directory](specifications/) which describes the system. **Note
that these specifications are visionary** — they describe the *desired end state* of the
system, not necessarily how it is built today. Where the code diverges, the specs express the
intent, not a description of current behavior. For how the system *currently* works, rely on
the code and the [Architecture](#architecture) section below. The [vision
document](specifications/vision.md) is the entry point and outlines goals and the target tool
catalog.

There is a [directory](feature-requests) with descriptions of planned development efforts.

## Project status

Proof of concept. One tool is implemented: `mpfb_create_human`, wrapping MPFB's
`HumanService.create_human()`. See [specifications/vision.md](specifications/vision.md#target-tool-catalog)
for what's planned beyond it, and [feature-requests/](feature-requests/) for work in progress.

## Commands

```bash
# Editable install (repo root)
pip install -e .

# Run the server (stdio transport; talks to blender_mcp's add-on over TCP)
mpfb-mcp

# Run all tests (stdlib unittest, no live Blender required — the add-on socket
# is faked/mocked)
python -m unittest discover -s tests -v

# Run a single test
python -m unittest tests.test_create_human.CreateHumanToolTests.test_default_call_uses_mpfb_default_macro_dict -v
```

`mcp[cli]` is pinned to `<2` ([pyproject.toml](pyproject.toml)) — mcp 2.x renamed `FastMCP` to
`MCPServer` and changed other APIs this code (and the currently-on-disk blender_mcp) is written
against. Check whether blender_mcp has migrated before bumping this.

To exercise `mpfb_create_human` against real Blender: start Blender with MPFB and the blender_mcp
add-on installed and enabled, start the add-on's socket server from its preferences panel (default
`localhost:9876`), then run `mpfb-mcp` and call the tool from an MCP client. `BLENDER_MCP_HOST` /
`BLENDER_MCP_PORT` override the address if the add-on isn't on the default.

## Architecture

This package is a thin MCP-tool layer; MPFB itself only ever runs inside Blender. There is no
direct Python dependency on MPFB or on blender_mcp — everything crosses via generated code sent
over a TCP socket, [connection.py](src/mpfbmcp/connection.py):

```
mpfb-mcp tool  →  build Python source (mpfb_codegen.py)  →  send_code() over TCP :9876
                                                                      ↓
                                                       blender_mcp add-on: exec() in Blender
                                                                      ↓
                                                              MPFB HumanService, etc.
```

- **[connection.py](src/mpfbmcp/connection.py)** — the wire client: JSON request + NUL-delimiter
  framing, `BLENDER_MCP_HOST`/`BLENDER_MCP_PORT` env vars. This is a deliberate, standalone
  duplicate of blender_mcp's `blmcp.tools_helpers.connection` protocol (see the module docstring),
  not an import of it — mpfb-mcp installs and runs without a blender_mcp checkout on the path.
  If blender_mcp's wire protocol changes, this needs to be updated to match by hand.
- **[mpfb_codegen.py](src/mpfbmcp/mpfb_codegen.py)** — builds the Python source string executed
  inside Blender. The interesting part is `_MPFB_BOOTSTRAP`: MPFB is a Blender *extension*, so it
  has no stable absolute import path (it depends on which extension repo the user installed from,
  e.g. `bl_ext.user_default.mpfb`). MPFB documents and itself uses a workaround for this in
  `mpfb/__init__.py` / `test/tests/__init__.py` (in `../mpfb2`): scan `sys.modules` for a module
  name ending in `"mpfb"`, then pull classes out of the `MPFB_CONTEXTUAL_INFORMATION["SERVICES"]`
  dict it publishes on that module. `_MPFB_BOOTSTRAP` reproduces that same pattern so generated
  code can resolve `HumanService` (or other services) without knowing MPFB's install path. Reuse
  this bootstrap for any future tool that needs another MPFB service class.
- **[tools/](src/mpfbmcp/tools)** — one module per MCP tool, each with a `register(mcp)` function,
  following blender_mcp's own tool-module convention. `tools/create_human.py` validates inputs
  (0.0-1.0 macro sliders) *before* generating/sending code, so bad input fails locally rather than
  round-tripping to Blender.
- **[__init__.py](src/mpfbmcp/__init__.py)** — `main()`: builds the `FastMCP` server, calls each
  tool module's `register()`, runs over stdio.

Tools return blender_mcp's response envelope as-is (`{"status": "ok"/"error", "result": ...}` or
`{"status": "error", "message": ...}`), the same convention blender_mcp's own tools use — callers
need to check `status` rather than assume success.

## Relationship to sibling projects

- **[../mpfb2](../mpfb2)** — the actual MPFB Blender addon this server drives. Its
  `bl_ext.*.mpfb` services (`HumanService`, `TargetService`, asset/skin/rig functions, etc.) are
  what the MCP tools wrap. `docs/services/humanservice.md` documents `HumanService`'s full API.
- **[../blender_mcp](../blender_mcp)** — the generic Blender MCP server this project piggy-backs
  on for the TCP transport into Blender. Treated as external/unmodified; not a code dependency
  (see `connection.py` above).
- **[../makehuman-static-website](../makehuman-static-website)** — likely source for bundled MPFB
  documentation if a `mpfb_search_docs` tool is implemented.

## Open design question

There are two unrelated projects called "blender mcp"; mpfb-mcp piggybacks on blender lab's
implementation, not the more feature-rich community one some users may have installed
instead. See [specifications/vision.md](specifications/vision.md#open-design-question-which-blender-mcp)
for details — whether to support both as backends is unresolved.
