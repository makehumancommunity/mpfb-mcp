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
Before starting any non-trivial change, read
[feature-requests/CLAUDE.md](feature-requests/CLAUDE.md): it defines the required process —
numbered `NNN-slug/README.md` subdirs, a `**Status:**` line, a fixed set of sections, and a
lifecycle that on completion folds durable decisions back into `specifications/`, moves the
subdir into `feature-requests/done/`, and moves the entry from
[NEXT_STEPS.md](feature-requests/NEXT_STEPS.md) to
[HISTORY.md](feature-requests/HISTORY.md). `NEXT_STEPS.md` is the list of active/remaining
efforts; `HISTORY.md` is the log of what has landed.

## Project status

Proof of concept. Two tools are implemented: `mpfb_create_human`, wrapping MPFB's
`HumanService.create_human()`, and `mpfb_get_status`, reporting whether MPFB is present,
initialized and how it is configured. See
[specifications/vision.md](specifications/vision.md#target-tool-catalog) for what's planned
beyond them, and [feature-requests/](feature-requests/) for work in progress.

## Commands

```bash
# Editable install (repo root). The system Python is PEP 668 externally-managed
# and has no `python` alias, so work inside a venv and use `python3`.
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# Run the server (stdio transport; talks to blender_mcp's add-on over TCP)
mpfb-mcp

# Run all tests (stdlib unittest, no live Blender required — the add-on socket
# is faked/mocked). Needs the package installed: every test module imports
# `mcp`, so a bare system-python run fails at import, not at assertion.
python3 -m unittest discover -s tests -v

# Run a single test
python3 -m unittest tests.test_create_human.CreateHumanToolTests.test_default_call_uses_mpfb_default_macro_dict -v
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
  inside Blender. The interesting part is the bootstrap: MPFB is a Blender *extension*, so it
  has no stable absolute import path (it depends on which extension repo the user installed from,
  e.g. `bl_ext.user_default.mpfb`). MPFB documents and itself uses a workaround for this in
  `mpfb/__init__.py` / `test/tests/__init__.py` (in `../mpfb2`): scan `sys.modules` for a module
  name ending in `"mpfb"`, then pull classes out of the `MPFB_CONTEXTUAL_INFORMATION["SERVICES"]`
  dict it publishes on that module. `_MPFB_MODULE_SCAN` is that scan, and two bootstraps are
  built on it — `_MPFB_BOOTSTRAP`, which raises `RuntimeError` unless MPFB is fully initialized
  (for tools that cannot proceed without it), and `_MPFB_STATUS_BOOTSTRAP`, which never raises and
  instead classifies the install as `absent`/`not_initialized`/`ok` (for `mpfb_get_status`). Reuse
  one of them for any future tool that needs an MPFB service class; never resolve a service by
  importing an MPFB submodule, since some have import-time side effects (`locationservice.py`
  creates directories). Note that a loaded `mpfb` module is *not* the same as an initialized one:
  `MPFB_CONTEXTUAL_INFORMATION` is `None` until `register()`'s last line, and `unregister()` never
  resets it. See
  [specifications/architecture.md](specifications/architecture.md#resolving-mpfb-from-generated-code).
- **[tools/](src/mpfbmcp/tools)** — one module per MCP tool, each with a `register(mcp)` function,
  following blender_mcp's own tool-module convention. `tools/create_human.py` validates inputs
  (0.0-1.0 macro sliders) *before* generating/sending code, so bad input fails locally rather than
  round-tripping to Blender. `tools/get_status.py` is the opposite shape: no input, and no
  interpretation of the response either — all of its state classification lives in the generated
  code, so "MPFB isn't there" comes back as a successful answer rather than an error envelope.
- **[__init__.py](src/mpfbmcp/__init__.py)** — `main()`: builds the `FastMCP` server, calls each
  tool module's `register()`, runs over stdio.

Tools return blender_mcp's response envelope as-is (`{"status": "ok"/"error", "result": ...}` or
`{"status": "error", "message": ...}`), the same convention blender_mcp's own tools use — callers
need to check `status` rather than assume success.

### Tests

Stdlib `unittest`, no pytest. Because MPFB is only ever reachable through generated code sent
into a live Blender, the suite can *never* exercise real MPFB behavior — it verifies what is on
this side of the socket:

- [tests/test_connection.py](tests/test_connection.py) — the wire protocol, against a throwaway
  local `socketserver.TCPServer` standing in for the blender_mcp add-on (framing, error
  envelopes, `BLENDER_MCP_HOST`/`BLENDER_MCP_PORT` handling).
- [tests/test_create_human.py](tests/test_create_human.py) — tool parameter validation and the
  generated source, with `mpfbmcp.tools.create_human.send_code` mocked out. It reaches the
  underlying sync callable via `mcp._tool_manager._tools[...].fn`, since `@mcp.tool` wraps it in
  a coroutine.
- [tests/test_get_status.py](tests/test_get_status.py) — same mocking approach, plus a set of
  tests that actually `exec()` the generated source against a stubbed `bpy` and stubbed `mpfb`
  entries injected into `sys.modules`. That exercises the three-state branching locally; it still
  proves nothing about the values real MPFB returns.

Anything needing real MPFB is a manual integration check against a running Blender (see
[Commands](#commands)), and feature requests are expected to say so explicitly.

### Code conventions in this repo

`from __future__ import annotations` and an explicit `__all__` in every module; `.format()`
rather than f-strings throughout; SPDX `GPL-3.0-or-later` header on test modules; module-level
docstrings that explain *why* (the MPFB-extension bootstrap, the deliberate protocol
duplication) rather than restate the code.

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
