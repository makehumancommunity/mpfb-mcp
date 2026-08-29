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

Proof of concept. Six tools are implemented: `mpfb_create_human`, wrapping MPFB's
`HumanService.create_human()`; `mpfb_get_status`, reporting whether MPFB is present, initialized
and how it is configured; the object-finding pair `mpfb_list_objects` and
`mpfb_get_object_info`, which is how every later tool is meant to name the object it acts on; and
two catalogue tools, `mpfb_list_rigs` and `mpfb_list_assets` — what could be *added*, rather than
what is already there, each entry named by the identifier the adding function will want.
`mpfb_list_assets` is also the first tool whose answer does not fit, so it is filtered, capped and
paged. See
[specifications/vision.md](specifications/vision.md#target-tool-catalog) for what's planned
beyond them, and [feature-requests/](feature-requests/) for work in progress.

## Version control

**Commit directly to `master`.** Do not create a branch for a change, and do not open a pull
request. The project is a single-developer proof of concept where every change so far has been a
straight-line addition to `master`; branching and review would add ceremony without adding a
reviewer. This overrides any general "branch before committing to the default branch" default.

Revisit this once the project has grown enough to merit it — more than one person committing,
a release that users depend on, or changes large enough that they need review before landing. Until
then, a branch is only warranted if explicitly asked for.

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
mpfb-mcp tool  →  assemble Python source (codegen/)  →  send_code() over TCP :9876
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
- **[codegen/](src/mpfbmcp/codegen)** — assembles the Python source executed inside Blender, out
  of three parts in a fixed order: a shared bootstrap, a parameter prelude, and a per-tool payload
  file. `codegen.assemble("create_human.py", bootstrap="raising", params={...})` is the single
  entry point; adding a tool adds a payload file rather than editing anything here.
  - **[codegen/bootstrap.py](src/mpfbmcp/codegen/bootstrap.py)** — the only shared, still-a-string
    part, and the interesting one: MPFB is a Blender *extension*, so it has no stable absolute
    import path (it depends on which extension repo the user installed from, e.g.
    `bl_ext.user_default.mpfb`). MPFB documents and itself uses a workaround for this in
    `mpfb/__init__.py` / `test/tests/__init__.py` (in `../mpfb2`): scan `sys.modules` for a module
    name ending in `"mpfb"`, then pull classes out of the `MPFB_CONTEXTUAL_INFORMATION["SERVICES"]`
    dict it publishes on that module. `_MPFB_MODULE_SCAN` is that scan, and two bootstraps are
    built on it — `MPFB_BOOTSTRAP`, which raises `RuntimeError` unless MPFB is fully initialized
    (for tools that cannot proceed without it), and `MPFB_STATUS_BOOTSTRAP`, which never raises and
    instead classifies the install as `absent`/`not_initialized`/`ok` (for `mpfb_get_status`).
    Reuse one of them for any future tool that needs an MPFB service class; never resolve a service
    by importing an MPFB submodule, since some have import-time side effects
    (`locationservice.py` creates directories). Note that a loaded `mpfb` module is *not* the same
    as an initialized one: `MPFB_CONTEXTUAL_INFORMATION` is `None` until `register()`'s last line,
    and `unregister()` never resets it. See
    [specifications/architecture.md](specifications/architecture.md#resolving-mpfb-from-generated-code).
  - **[codegen/payloads/](src/mpfbmcp/codegen/payloads)** — one ordinary `.py` file per tool,
    holding the code that does the actual work. These are *not* modules of this package and are
    never imported here (they reference `bpy` and MPFB services): the directory has no
    `__init__.py`, and they are read as package resources. `pyproject.toml` therefore both
    declares them as package data — or a non-editable install ships no payloads — and sets
    `namespaces = false`, or setuptools' discovery picks `payloads/` up as a namespace package and
    ships them as modules instead of data. Parameters reach a payload as data —
    the prelude binds `PARAMS` from a JSON literal — so a payload contains no placeholders and no
    escaping, and no caller-supplied value can alter the structure of the generated program. Each
    payload's docstring names the assembler-bound names it relies on, since a linter flags those
    as undefined. See
    [specifications/architecture.md](specifications/architecture.md#code-generation-layout).
- **[tools/](src/mpfbmcp/tools)** — one module per MCP tool, each with a `register(mcp)` function,
  following blender_mcp's own tool-module convention. `tools/create_human.py` validates inputs
  (0.0-1.0 macro sliders) *before* generating/sending code, so bad input fails locally rather than
  round-tripping to Blender. `tools/get_status.py` is the opposite shape: no input, and no
  interpretation of the response either — all of its state classification lives in the generated
  code, so "MPFB isn't there" comes back as a successful answer rather than an error envelope.
  `tools/list_objects.py` and `tools/get_object_info.py` sit between the two: they validate the
  *shape* of their string arguments locally (non-string, empty or whitespace-only is rejected, and
  an explicitly empty value is never quietly treated as an omitted one), but deliberately not the
  *vocabulary* — a list of valid MPFB type names kept here would drift from MPFB's own, so the
  generated code answers that with `type_recognized` and `known_types` instead. Like
  `get_status.py`, they treat absence as an answer: an unresolvable object name comes back as
  `found: false`, not as an error envelope. `tools/list_rigs.py` is the strictest of them about
  its one argument — `refresh` must be a real `bool`, not a truthy value, since `refresh="false"`
  would otherwise rescan the disk — and its payload does all the rest, including the two things
  that cannot be derived from a filename: which of `add_builtin_rig()` / `add_custom_rig()` takes
  a given identifier, and which rig's weights file would actually be loaded.
  `tools/list_assets.py` is the widest, at six arguments, and still validates only shapes: the
  string filters as above, `limit`/`offset` as non-negative ints that are not `bool`
  (`isinstance(True, int)` is `True`, so `limit=True` would otherwise page one entry at a time),
  and the same strict `refresh`. Its payload carries the rest, including the two things a filename
  cannot say — which pack an asset came from, derived from a directory-name convention and flagged
  when two packs claim it, and the difference between the `path` an adding function takes and the
  `fragment` MPFB records on the object it produces.
- **[__init__.py](src/mpfbmcp/__init__.py)** — `main()`: builds the `FastMCP` server, calls each
  tool module's `register()`, runs over stdio. Together with a tool module and a payload file,
  this `register()` call is the *whole* of what adding a tool touches — no shared
  code-generation module is edited.

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
- [tests/test_codegen.py](tests/test_codegen.py) — assembly: that every payload file compiles on
  its own (nothing imports them, so a syntax error would otherwise surface only inside Blender),
  that the right bootstrap is selected, and that `PARAMS` round-trips — including for a value
  full of quotes, newlines and `"""`, asserted by executing the prelude and comparing values
  rather than by matching source text.
- [tests/test_create_human.py](tests/test_create_human.py) — tool parameter validation and the
  generated source, with `mpfbmcp.tools.create_human.send_code` mocked out. It reaches the
  underlying sync callable via `mcp._tool_manager._tools[...].fn`, since `@mcp.tool` wraps it in
  a coroutine.
- [tests/test_get_status.py](tests/test_get_status.py) — same mocking approach, plus a set of
  tests that actually `exec()` the generated source against a stubbed `bpy` and stubbed `mpfb`
  entries injected into `sys.modules`. That exercises the three-state branching locally; it still
  proves nothing about the values real MPFB returns.
- [tests/blender_stubs.py](tests/blender_stubs.py) — holds no tests. It is the stub Blender scene
  and stub MPFB services that the two object-finding tools' generated code is executed against,
  shared because both need the same scene. The stubs deliberately reimplement MPFB's *actual*
  behavior rather than returning convenient values — `""` and not `None` from
  `get_object_type()`, a non-bool `object_is_any_makehuman_object()`, a `find_related_objects()`
  that yields the object it was asked about, a `get_list_of_children()` that walks the whole file
  — because those quirks are the reason the payloads are written as they are.
- [tests/test_list_objects.py](tests/test_list_objects.py) and
  [tests/test_get_object_info.py](tests/test_get_object_info.py) — argument validation with
  `send_code` mocked, then the generated code run against those stubs: subject resolution by name
  and by active object (including the no-active-object branch, which is what crashes on
  `None.name` if missed), the relationship walk, and all three `asset_info` shapes with all three
  resolution outcomes each. Note the two mechanics these inherit from `test_get_status.py`: a stub
  service module's name must not end in `"mpfb"`, or the bootstrap's candidate scan claims it, and
  the stub class's `__module__` is reassigned by hand so the payload's
  `sys.modules[Service.__module__]` lookup lands on it.
- [tests/test_list_rigs.py](tests/test_list_rigs.py) — the same two layers, but run against a real
  `tempfile` rig tree rather than a mocked filesystem: the payload's job *is* `os.listdir()` and
  `os.path.isfile()`, so mocking those away would leave nothing under test. The tree reproduces the
  asymmetries a real MPFB install has — a rig with no weights file of its own, a weights file with
  no rig, a rig absent from the UI enum — because each one is a branch the payload exists to get
  right.
- [tests/test_list_assets.py](tests/test_list_assets.py) — the same two layers, and the opposite
  choice about the filesystem: this payload asks `AssetService` rather than walking the disk, so
  what needs reproducing is that service. `blender_stubs.py`'s `get_asset_list()` therefore builds
  its items exactly as MPFB's `update_asset_list()` does, quirks first — keyed by *label*, so two
  files whose names differ only in case or underscores really do collapse into one entry, and with
  a `thumb` value JSON cannot encode, so a payload that leaked it would fail here rather than in
  Blender. The stub library also carries an asset claimed by two packs, one claimed by none, a pack
  listing an asset that is not installed, and an asset lying directly in an asset root rather than
  in a directory of its own: each is a branch, and the last is the one that would otherwise
  attribute a skin to whichever pack shipped an asset called "skins". Note this adds a *third*
  stub service module — `ASSET_LIBRARY_SECTIONS` is module-level in `assetservice.py`, so
  `StubAssetService.__module__` is reassigned the same way the object-service stub's is.

Anything needing real MPFB is a manual integration check against a running Blender (see
[Commands](#commands)), and feature requests are expected to say so explicitly.

### Code conventions in this repo

`from __future__ import annotations` and an explicit `__all__` in every module; `.format()`
rather than f-strings throughout; readability and developer experience treated as prioritized
non-functional requirements, generated code included (see
[specifications/architecture.md](specifications/architecture.md#readability-and-developer-experience-are-prioritized)); SPDX `GPL-3.0-or-later` header on test modules; module-level
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
