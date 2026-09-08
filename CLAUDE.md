# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

**This file is a map, not a manual.** It carries the concrete layout, the commands, and the
handful of facts that live nowhere else. Rationale lives elsewhere, in places that are maintained
and none of which is summarized here:

| For | Read |
|-----|------|
| Why a tool is written the way it is | that tool's module docstring in [tools/](src/mpfbmcp/tools), and its payload's in [payloads/](src/mpfbmcp/codegen/payloads) |
| How a tool must take its input and name things | [specifications/tool-interface.md](specifications/tool-interface.md) |
| What a tool's response must contain | [specifications/responses.md](specifications/responses.md) |
| What a tool that *changes* a character owes its caller | [specifications/mutating-tools.md](specifications/mutating-tools.md) |
| What to do when MPFB is inconsistent or wrong | [specifications/mpfb-integration.md](specifications/mpfb-integration.md) |
| How the system is structured | [specifications/architecture.md](specifications/architecture.md) |
| Why a test or a stub is written the way it is | that module's docstring, and [specifications/testing.md](specifications/testing.md) |
| What an effort decided, and what it found | [feature-requests/HISTORY.md](feature-requests/HISTORY.md) |

## Documentation

The [specifications directory](specifications/) describes the system. **These specifications are
visionary** — they describe the *desired end state*, not necessarily how it is built today. Where
the code diverges, the specs express the intent. For how the system *currently* works, rely on the
code and the [Architecture](#architecture) section below. [vision.md](specifications/vision.md) is
the entry point, and [specifications/README.md](specifications/README.md) indexes the seven
documents: `architecture.md` for the machine, `tool-interface.md` / `responses.md` /
`mutating-tools.md` for what a tool takes, says and changes, `mpfb-integration.md` for coping with
MPFB, `observability.md` for diagnostics, and `testing.md` for how all of it is checked.

The [feature-requests directory](feature-requests) describes planned and completed development
efforts. **Before starting any non-trivial change, read
[feature-requests/CLAUDE.md](feature-requests/CLAUDE.md)**: it defines the required process —
numbered `NNN-slug/README.md` subdirs, a `**Status:**` line, a fixed set of sections, and a
lifecycle that on completion folds durable decisions into `specifications/`, moves the subdir into
`feature-requests/done/`, and moves the entry from
[NEXT_STEPS.md](feature-requests/NEXT_STEPS.md) (active/remaining) to
[HISTORY.md](feature-requests/HISTORY.md) (what has landed).

## Project status

Proof of concept. **Twenty tools are implemented, and all twenty have been run against a real
Blender.** [README.md](README.md) lists them by purpose;
[HISTORY.md](feature-requests/HISTORY.md) tells the story of each effort, including what the live
run found; [vision.md](specifications/vision.md#target-tool-catalog) says what is planned beyond
them; [NEXT_STEPS.md](feature-requests/NEXT_STEPS.md) is the active queue.

The live verification is no longer a manual session. It lives in [verification/](verification/) as
one script per checklist, and re-running a whole checklist after a fix is one command — see
[verification/README.md](verification/README.md).

## Version control

**Commit directly to `master`.** Do not create a branch for a change, and do not open a pull
request. The project is a single-developer proof of concept where every change so far has been a
straight-line addition to `master`; branching and review would add ceremony without adding a
reviewer. This overrides any general "branch before committing to the default branch" default.

Revisit this once the project has grown enough to merit it — more than one person committing, a
release that users depend on, or changes large enough that they need review before landing. Until
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

To exercise a tool against real Blender: start Blender with MPFB and the blender_mcp add-on
installed and enabled, start the add-on's socket server from its preferences panel (default
`localhost:9876`), then run `mpfb-mcp` and call the tool from an MCP client. `BLENDER_MCP_HOST` /
`BLENDER_MCP_PORT` override the address if the add-on isn't on the default. For a whole checklist
rather than one call, use [verification/](verification/README.md#running).

Two further environment variables, both **off by default**, make a call visible
([observability.py](src/mpfbmcp/observability.py)). They are mpfb-mcp's own, which is why they do
*not* carry the `BLENDER_MCP_` prefix the two above share with blender_mcp:

```bash
# Keep a per-call record: for every call, the exact program in a .py written BEFORE the
# socket call, the full response envelope in a .json written after, and one tab-separated
# line in index.tsv (seq, timestamp, tool, bytes, ms, status, response bytes). Files land in
# a per-run subdirectory named for the timestamp and the pid, so two servers against one
# Blender do not interleave.
MPFB_MCP_RECORD_DIR=~/mpfb-mcp-records mpfb-mcp

# Attach a stderr handler to the mpfbmcp logger hierarchy (which otherwise has none).
# INFO is one line per call; DEBUG shows what a tool decided locally before the socket.
MPFB_MCP_LOG_LEVEL=DEBUG mpfb-mcp
```

Unset, no directory is created, no file is opened, nothing is formatted and the bytes on the wire
are identical — which is also the path the whole test suite exercises. **The record is diagnostic
output about the machine it ran on**: absolute paths from the install, the asset library layout,
MHMAT and MHCLO paths, and the parameters of the character being built. There are no credentials
anywhere in this system, so nothing is scrubbed and nothing should be — but do not point the
directory inside this repository, and read a record before sharing it. While the record is
enabled, an **error** envelope gains an `mpfb_mcp_record` key naming the two files it wrote; a
success envelope is untouched in every configuration.

## Architecture

This package is a thin MCP-tool layer; MPFB itself only ever runs inside Blender. There is no
direct Python dependency on MPFB or on blender_mcp — everything crosses via generated code sent
over a TCP socket:

```
mpfb-mcp tool  →  assemble Python source (codegen/)  →  send_code() over TCP :9876
                                                                  ↓
                                                   blender_mcp add-on: exec() in Blender
                                                                  ↓
                                                          MPFB HumanService, etc.
```

The principles behind this layout are in
[specifications/architecture.md](specifications/architecture.md); the table below is the concrete
map, and carries only what is not stated there or in its sibling specifications.

| Module | What it is, and the local detail |
|--------|----------------------------------|
| [connection.py](src/mpfbmcp/connection.py) | The wire client: JSON request + NUL-delimiter framing, `BLENDER_MCP_HOST`/`BLENDER_MCP_PORT`. A deliberate standalone **duplicate** of blender_mcp's protocol, not an import of it, so mpfb-mcp installs without a blender_mcp checkout. **If blender_mcp's wire protocol changes, this must be updated to match by hand.** ([rationale](specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp)) |
| [observability.py](src/mpfbmcp/observability.py) | The per-call record and this package's logger. Hangs off `send_code()` and nowhere else. The program is written to disk **before** the socket call, so a call that hangs, times out or takes Blender down still leaves the program that did it. **Never write to stdout from anywhere in this package** — it is the JSON-RPC channel. ([rationale](specifications/observability.md#diagnostics-attach-at-the-socket-boundary-never-to-the-program)) |
| [codegen/](src/mpfbmcp/codegen) | Assembles the source executed inside Blender, in a fixed order: bootstrap, parameter prelude, optional shared fragments, payload. One entry point: `codegen.assemble("create_human.py", bootstrap="raising", params={...}, shared=["rig_lookup.py"])`. ([rationale](specifications/architecture.md#code-generation-layout)) |
| [codegen/bootstrap.py](src/mpfbmcp/codegen/bootstrap.py) | The only shared part still written as a string. `_MPFB_MODULE_SCAN` is the `sys.modules` scan that finds MPFB whatever extension repo it was installed from; `MPFB_BOOTSTRAP` raises unless MPFB is fully initialized, `MPFB_STATUS_BOOTSTRAP` never raises and classifies the install instead. Reuse one of the two for any new tool; **never resolve a service by importing an MPFB submodule.** ([rationale](specifications/architecture.md#resolving-mpfb-from-generated-code)) |
| [codegen/payloads/](src/mpfbmcp/codegen/payloads) | One ordinary `.py` per tool, named for its tool module. Not modules of this package, never imported here, read as package resources — the directory has no `__init__.py` and `pyproject.toml` declares them as package data *and* sets `namespaces = false`. Each payload's docstring names the assembler-bound names it relies on, since a linter flags those as undefined. ([rationale](specifications/architecture.md#code-generation-layout)) |
| [codegen/shared/](src/mpfbmcp/codegen/shared) | **Six fragments**, for concepts two or more payloads model identically: `target_categories.py` (MPFB's modeling-category table, used by the three detail-target tools), `rig_lookup.py` (which rig file and whose weights, used by `list_rigs` and `add_rig`), `asset_sections.py` (MPFB's `ASSET_LIBRARY_SECTIONS` table, used by the asset and material tools), `performed.py` (the uniform `performed` flag, named by all eleven mutating tools and the only fragment that binds nothing from the bootstrap), `modifier_reading.py` (what one modeling category's slider reads, used by `get_target_stack` and `symmetrize_targets`), `refit_blocker.py` (whether a refit would silently leave the rig behind, used by all four refitting tools, which each phrase the message themselves). A *sibling* of `payloads/` with a package-data glob of its own, because such a glob does not descend. ([rationale](specifications/architecture.md#shared-fragments)) |
| [tools/](src/mpfbmcp/tools) | One module per MCP tool, each with `register(mcp)`. See the tool table below. ([rationale](specifications/architecture.md#one-module-per-tool)) |
| [__init__.py](src/mpfbmcp/__init__.py) | `build_server()`: builds the `FastMCP` server, calls each tool module's `register()`, and dedents every description once (FastMCP sends `fn.__doc__` verbatim). `main()` runs it over stdio. |

**Adding a tool touches exactly three things**: a module in `tools/`, a payload in
`codegen/payloads/`, and one `register()` call in `__init__.py`. No shared code-generation module
is edited — a tool that wants a fragment names it in the `assemble()` call it was already making.
If a change to shared code is needed to add an ordinary tool, the layout has drifted.

### The twenty tools

Tool module, payload and test module all share a name: `mpfb_set_skin` is
`tools/set_skin.py`, `codegen/payloads/set_skin.py` and `tests/test_set_skin.py`. **The module
docstring is where the reasoning lives**; the line below is only enough to find the right one.

| Tool | The distinctive thing about it |
|------|-------------------------------|
| `mpfb_get_status` | Absence is an answer: classifies the install `absent`/`not_initialized`/`ok` rather than failing. The only user of `MPFB_STATUS_BOOTSTRAP`. |
| `mpfb_create_human` | Wraps `HumanService.create_human()`. Eleven flat macro sliders rather than a nested dict. |
| `mpfb_list_objects` | Which MakeHuman objects are in the scene. Validates argument *shape*, never the type vocabulary — the payload answers that with `type_recognized`/`known_types`. |
| `mpfb_get_object_info` | What an object is, what it was made from, what belongs with it. Three `asset_info` shapes, three resolution outcomes each. |
| `mpfb_list_rigs` | Catalogue. Predicts, per rig, which file would load and whose weights come with it — via `rig_lookup.py`, so `mpfb_add_rig` cannot disagree. |
| `mpfb_list_assets` | Catalogue, and the first answer that does not fit: filtered, capped and paged. Reports `pack` (from a directory convention) and both the passable `path` and the portable `fragment`. |
| `mpfb_list_targets` | Catalogue. The one tool that is genuinely side-effect-free — no cache populated, no preview loaded, hence no `refresh`. Reports `shapekey_name` from MPFB, since a name over 60 characters is encoded. |
| `mpfb_list_asset_materials` | Catalogue for something that is **not** an asset library section, so `mpfb_list_assets` cannot name it. Its answer is stale by design: MPFB caches that scan with no invalidation. |
| `mpfb_get_macro_details` | Reads a character's phenotype. Subject resolved from any object in the character's family. |
| `mpfb_set_macro_details` | Writes it. Sliders default to `None`, not `0.5` — "not mentioned" and "set to the default" are different requests. Writes every property, then recalculates **once**. |
| `mpfb_refit_human` | Refits everything to a changed body. Detects the generated-Rigify-rig-with-no-meta-rig case, which `HumanService.refit()` reports only through an `operator` an MCP tool has none of. |
| `mpfb_get_target_stack` | Reads detail morphs. Reads `key_blocks` directly, since `TargetService` cannot see a shape key whose name contains "basis". |
| `mpfb_set_targets` | The one **batched** tool: lists of dicts, because a round trip costs ~250 ms and a target costs milliseconds. Resolves every entry before writing any. |
| `mpfb_symmetrize_targets` | Copies one side onto the other. Zeroes the opposing target first, or pruning deletes the wrong half of a pair. |
| `mpfb_add_rig` | First consumer of a catalogue's identifiers. **Dispatches on the `custom.` prefix itself**, because MPFB's two adding functions are not interchangeable and neither miss reads as a mistake. Names every asset it just failed to rig. |
| `mpfb_generate_rigify_rig` | Finishes a Rigify meta rig. The only mutating tool that **cannot restore the caller's selection** — the operator selects its own result — so it reports `active_object_after`. |
| `mpfb_add_asset` | Equips an MHCLO asset. Takes the catalogue's `path` *or* its `fragment`, exactly one, and always reports which file it landed on. `asset_type` is **required**: MPFB's `"Clothes"` default is wrong for six of the eight types and mislabels a body part silently. |
| `mpfb_remove_asset` | Takes it off properly — deleting the object would leave the body's mask modifier and the garment's sub-rig behind. |
| `mpfb_set_skin` | Five material models. Follows **MPFB's settings panel rather than the function signature**: `skin_type` defaults to `MAKESKIN`, and `material_instances` is coerced off for three types — so the *default call creates no material instances*. Reports requested beside used. |
| `mpfb_set_asset_material` | Has **no service function to wrap at all**; the mechanism exists only in a UI operator, reimplemented from services with three of its quirks reproduced rather than tidied up. |

### What is validated on this side of the socket

The rule is [validate the shape, never the vocabulary](specifications/tool-interface.md#validate-before-crossing-the-socket).
These are the specific local checks, and each exists because the alternative fails silently:

- **`refresh`, `prune` and `refit` must be a real `bool`**, not merely truthy. `refresh="false"`
  is a true value, and would rescan the disk.
- **`limit` and `offset` are non-negative ints that are not `bool`.** `isinstance(True, int)` is
  `True`, so `limit=True` would otherwise page one entry at a time.
- **`mpfb_set_macro_details` enforces 0.0-1.0 here or nowhere.** MPFB's macro properties carry a
  default but no `min`/`max`; it is the scene-level proxy property behind MPFB's sliders that
  clamps, and generated code does not go through it.
- **`mpfb_set_targets` enforces two different ranges**: -1.0..+1.0 for a `modifiers` entry, since
  a category may be a pair of opposites, and 0.0..1.0 for a `targets` entry, since that is a raw
  shape key value and Blender clamps one to that range. Which range applies to a given category is
  only knowable inside Blender, and comes back as a resolution error. Per-entry validation also
  rejects an **unknown key**, because a misspelled `catagory` is otherwise silent.
- **`mpfb_symmetrize_targets`' `direction` is the package's only required argument.** Which half
  of a face is the good one is not something a tool can guess, and guessing wrong destroys work
  with no undo across the socket — which is also why it has `dry_run`.
- **Two vocabularies are checked locally**, both narrow exceptions:
  `mpfb_set_skin`'s `skin_type` and `mpfb_generate_rigify_rig`'s `meta_rig_action`. The
  authoritative check stays in the payload either way; see
  [the exception in architecture.md](specifications/tool-interface.md#validate-before-crossing-the-socket)
  for what earns one.

## Tests

Stdlib `unittest`, no pytest, 719 tests. Two layers per tool: the wrapper with `send_code`
mocked, then the assembled source `exec()`'d against stub Blender and stub MPFB services.
**Read [specifications/testing.md](specifications/testing.md) before adding or changing a
test** — in particular the rule that stubs reproduce MPFB's real behaviour rather than
convenient values, and the list of what the suite can never establish.

| Module | What it covers |
|--------|----------------|
| [fake_addon.py](tests/fake_addon.py) | No tests. The throwaway `socketserver.TCPServer` standing in for the add-on, plus env-var bookkeeping. Can answer differently per request, answer nothing and close, and keep the raw request bytes. |
| [blender_stubs.py](tests/blender_stubs.py) | No tests. The stub scene and stub services every payload below is executed against, plus the shared `GeneratedCodeTestCase`, `DetailTargetTestCase`, `RigTestCase` and `MeshAssetTestCase`. Its docstring enumerates every MPFB quirk it reproduces and why. |
| [test_connection.py](tests/test_connection.py) | The wire protocol: framing, error envelopes, host/port env vars. |
| [test_observability.py](tests/test_observability.py) | The one component fully testable on this side of the socket, and held to a higher bar accordingly. |
| [test_description_budget.py](tests/test_description_budget.py) | What an MCP client downloads before any work happens, measured against a ceiling. Run as a script it prints the per-tool table instead. |
| [test_codegen.py](tests/test_codegen.py) | Assembly: every payload compiles standalone, the right bootstrap is selected, `PARAMS` round-trips. Also the three fragments that can be run directly — `performed.py`, `refit_blocker.py`, `modifier_reading.py` — and, for each, the drift check that no payload keeps an implementation of its own. |
| [test_create_human.py](tests/test_create_human.py) | Parameter validation and generated source, `send_code` mocked. |
| [test_get_status.py](tests/test_get_status.py) | The three-state branching, `exec()`'d against stubbed `bpy` and `sys.modules` entries. |
| [test_list_objects.py](tests/test_list_objects.py), [test_get_object_info.py](tests/test_get_object_info.py) | Subject resolution by name and by active object, the relationship walk, three `asset_info` shapes. |
| [test_list_rigs.py](tests/test_list_rigs.py) | Over a real `tempfile` rig tree — the payload's job *is* `os.listdir()`. Carries a rig with no weights of its own, a weights file with no rig, a rig absent from the UI enum. |
| [test_list_targets.py](tests/test_list_targets.py) | Over a real `tempfile` target tree, carrying the two-source merge, the `.target.gz` MPFB's own scan misses, and a name long enough to be encoded. |
| [test_list_assets.py](tests/test_list_assets.py) | The opposite choice: this payload asks `AssetService`, so the *service* is what the stub reproduces, quirks first. |
| [test_get_macro_details.py](tests/test_get_macro_details.py), [test_set_macro_details.py](tests/test_set_macro_details.py), [test_refit_human.py](tests/test_refit_human.py) | The macro half of `TargetService`, incl. unclamped storage and the sub-0.0001 prune. Fixtures parent garments to the **rig**, as MPFB does on a rigged character. |
| [test_get_target_stack.py](tests/test_get_target_stack.py), [test_set_targets.py](tests/test_set_targets.py), [test_symmetrize_targets.py](tests/test_symmetrize_targets.py) | `DetailTargetTestCase`: a real target tree *and* a stub character. Four category shapes, a sided category missing its right half, an over-60-character name, a name containing "basis". One test runs the stack payload and the symmetrize payload over *one* character and asserts every category reading agrees, which is what `modifier_reading.py` exists for. |
| [test_add_rig.py](tests/test_add_rig.py), [test_generate_rigify_rig.py](tests/test_generate_rigify_rig.py) | `RigTestCase`, shared with `test_list_rigs` so one test can assert the catalogue's weights prediction equals the adder's outcome — which means nothing unless it is the same disk. |
| [test_add_asset.py](tests/test_add_asset.py), [test_remove_asset.py](tests/test_remove_asset.py) | `MeshAssetTestCase`: a real asset library plus a stub character. Two roots hold the same `fedora.mhclo`, so the basename ambiguity is under test. Removal equips through `add_asset`'s own payload. |
| [test_set_skin.py](tests/test_set_skin.py), [test_set_asset_material.py](tests/test_set_asset_material.py), [test_list_asset_materials.py](tests/test_list_asset_materials.py) | The same fixture plus a skins root and a real MPFB data directory. `material_slots` is derived from `data.materials` the way Blender derives it, so the two material paths cannot look alike. |

Anything needing real MPFB is verified against a running Blender, and a feature request is
expected to say so explicitly. That check lives in [verification/](verification/), a sibling of
`tests/` that is not discovered by `unittest discover -s tests` and is not shipped. See
[verification/README.md](verification/README.md) for how to run it, what it changes outside the
`.blend` and puts back, and the two things it cannot put back.

**One harness process at a time**: two against one Blender interleave, and the second fails in
ways that look like tool defects.

## Code conventions in this repo

`from __future__ import annotations` and an explicit `__all__` in every module; `.format()`
rather than f-strings throughout; readability and developer experience treated as prioritized
non-functional requirements, generated code included (see
[specifications/architecture.md](specifications/architecture.md#readability-and-developer-experience-are-prioritized));
SPDX `GPL-3.0-or-later` header on test modules; module-level docstrings that explain *why* (the
MPFB-extension bootstrap, the deliberate protocol duplication) rather than restate the code.

## Relationship to sibling projects

- **[../mpfb2](../mpfb2)** — the actual MPFB Blender addon this server drives. Its
  `bl_ext.*.mpfb` services (`HumanService`, `TargetService`, asset/skin/rig functions, etc.) are
  what the MCP tools wrap. `docs/services/humanservice.md` documents `HumanService`'s full API.
- **[../blender_mcp](../blender_mcp)** — the generic Blender MCP server this project piggy-backs
  on for the TCP transport into Blender. Treated as external/unmodified; not a code dependency
  (see `connection.py` above).
- **[../makehuman-static-website](../makehuman-static-website)** — likely source for bundled MPFB
  documentation if a `mpfb_search_docs` tool is implemented.

## Backends

There are two unrelated projects called "blender mcp"; mpfb-mcp piggybacks on blender lab's
implementation, not the more feature-rich community one some users may have installed instead.
Supporting **both** is a goal, with blender lab's remaining the reference backend. Nothing of it
is implemented yet. See
[vision.md](specifications/vision.md#resolved-which-blender-mcp-both) for the resolution and the
shape the second backend would take, and
[NEXT_STEPS.md](feature-requests/NEXT_STEPS.md#second-backend-the-community-blender-mcp) for the
entry.
