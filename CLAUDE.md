# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

**This file is a map, not a manual.** It carries the concrete layout, the commands, and the
handful of facts that live nowhere else. Rationale lives elsewhere, in places that are maintained
and none of which is summarized here:

| For | Read |
|-----|------|
| Why a tool is written the way it is | that tool's module docstring in [tools/](src/mpfbmcp/tools), and its command's in [commands/](bridge/mpfb_bridge/commands) |
| How a tool must take its input and name things | [specifications/tool-interface.md](specifications/tool-interface.md) |
| What a tool's response must contain | [specifications/responses.md](specifications/responses.md) |
| What a tool that *changes* a character owes its caller | [specifications/mutating-tools.md](specifications/mutating-tools.md) |
| What to do when MPFB is inconsistent or wrong | [specifications/mpfb-integration.md](specifications/mpfb-integration.md) |
| How the system is structured | [specifications/architecture.md](specifications/architecture.md) |
| Why a test or a fixture is written the way it is | that module's docstring, and [specifications/testing.md](specifications/testing.md) |
| What an effort decided, and what it found | [feature-requests/HISTORY.md](feature-requests/HISTORY.md) |

## Environment

Read `local_environment.md` if it exists: it says where Blender, MPFB's source and MPFB's user
data are on this machine, and whether this is the maintainer's checkout. It is gitignored, since it
is only relevant per machine; [local_environment.example.md](local_environment.example.md) is the
template to copy it from. If it is missing and a task needs one of those paths, ask for it rather
than guessing, and do not write a machine's paths into a tracked file.

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

Early beta, and **the pivot is complete**: the Blender-side logic lives in a companion add-on
of our own, the MPFB Bridge in [bridge/](bridge), and there is one way to reach Blender.
[FR 028](feature-requests/done/028-pivot-to-specific-addon/README.md) landed the decision and a
working transport; [FR 030](feature-requests/done/030-backend-seam/README.md) built the **seam**
below the send ([backend.py](src/mpfbmcp/backend.py)) and migrated one tool;
[FR 031](feature-requests/done/031-introspection-and-catalogues-migrated/README.md) migrated the
nine other read-only ones;
[FR 032](feature-requests/done/032-creation-and-modification-migrated/README.md) migrated the last
fourteen and flipped the default; and
[FR 033](feature-requests/done/033-retire-the-generated-code-path/README.md) deleted the path that
had been carrying nothing since. What that path was is in
[HISTORY.md](feature-requests/HISTORY.md) and nowhere else in this repository.

**Forty-two tools are implemented, and all forty-two have been run against a
real Blender.** [README.md](README.md) lists them by purpose;
[HISTORY.md](feature-requests/HISTORY.md) tells the story of each effort, including what the live
run found; [vision.md](specifications/vision.md#target-tool-catalog) says what is planned beyond
them; [NEXT_STEPS.md](feature-requests/NEXT_STEPS.md) is the active queue.
[FR 026](feature-requests/done/026-face-units/README.md) added `mpfb_get_face_units` and
`mpfb_set_face_units`, the first pair to depend on an asset pack that may not be installed
(`faceunits01`) and the first to establish that pattern in
[mpfb-integration.md](specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack).
[FR 041](feature-requests/done/041-pose-controls-and-read-back/README.md) added the first two
posing tools, both read-only, and the character frame every posing tool reports in;
[FR 042](feature-requests/done/042-posing-bones-switches-and-reset/README.md) added the three that
change a pose, with Rigify's snaps reimplemented in the bridge.
[FR 039](feature-requests/done/039-exporting-characters/README.md) added the two that take a
character out of Blender, and the first bridge preference a command reads: the export directory.
[FR 045](feature-requests/done/045-placing-a-character/README.md) added the one that places a
character in the scene.

The live verification is a **smoke run**: one call per tool with default arguments, one command,
under 2.5 s for all forty-two against a headless Blender. It lives in [verification/](verification/) —
see [verification/README.md](verification/README.md). It writes **three** files outside the `.blend`,
always the same three (a preset, a saved expression and an export), and since FR 033 it also **leaves in the scene everything it builds**, because
the bridge executes nothing on a harness's behalf and is not growing a command that would; that
README says what the narrowing cost. An *exhaustive* live check belongs to the feature request that
needs it, in that request's own subdir, and moves to `done/` with it.

## Version control

The default branch is `master`, and changes reach it through a pull request from a branch.

**The maintainer's checkout is the exception**, and says so in the "Version control" section of
its `local_environment.md`. There, commit directly to `master`, and do not create a branch or open
a pull request unless asked: the project has had a single developer, every change so far has been
a straight-line addition to `master`, and branching and review would add ceremony without adding a
reviewer. This overrides any general "branch before committing to the default branch" default. It
is the maintainer's to revisit once there is more than one person committing, a release users
depend on, or a change large enough to need review before landing.

## Commands

```bash
# Editable install (repo root). The system Python is PEP 668 externally-managed
# and has no `python` alias, so work inside a venv and use `python3`.
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# Run the server (stdio transport; talks to the MPFB Bridge add-on over TCP)
mpfb-mcp

# Run all tests (stdlib unittest, no live Blender required — the add-on socket
# is faked/mocked). Needs the package installed: every test module imports
# `mcp`, so a bare system-python run fails at import, not at assertion.
python3 -m unittest discover -s tests -v

# Run a single test
python3 -m unittest tests.test_create_human.CreateHumanToolTests.test_default_call_uses_mpfb_default_macro_dict -v

# Run the bridge's own tests. Different harness, different command: pytest inside a
# headless Blender, because the add-on under test is a Blender extension. Needs the
# add-on enabled and symlinked to this checkout, and pytest in Blender's own Python
# (bridge/test/README.md). `unittest discover -s tests` must never find these.
# Writes a coverage report into bridge/test/coverage/ when Blender's Python has
# coverage and the a1_coverage.pth; without them the tests run unchanged.
BLENDER_EXE=$(which blender) bridge/test/execute_tests_headless.bash

# Run the bridge in a Blender with no screen. The GUI start operator refuses
# background mode (timers never fire there); this is the other drive mechanism,
# and the add-on must be enabled in that Blender for the command to exist.
# --export-dir sets where mpfb_export_character writes, over the add-on's
# export_directory preference; a named directory must exist.
blender --background --command mpfb_bridge
blender --background --command mpfb_bridge --export-dir /path/to/exports
```

`mcp[cli]` is pinned to `<2` ([pyproject.toml](pyproject.toml)) — mcp 2.x renamed `FastMCP` to
`MCPServer` and changed other APIs this code is written against.

**`MPFB_BRIDGE_HOST` / `MPFB_BRIDGE_PORT` address the add-on**, defaulting to `127.0.0.1` and
`9877`. There is no backend to choose any more: `MPFB_MCP_BACKEND` chose between the bridge and the
generated path, and is read today only so that a value left in somebody's MCP client configuration
produces one WARNING on the `mpfbmcp` logger rather than being silently ignored.

To exercise a tool against real Blender: start Blender with MPFB and the MPFB Bridge add-on
installed and enabled, start the bridge's command server from its preferences panel (default
`127.0.0.1:9877`), then run `mpfb-mcp` and call the tool from an MCP client. For a Blender with no
window, `blender --background --command mpfb_bridge` is the other drive mechanism and takes
`--port`. To confirm that all forty-two still work rather than exercise one, use
[verification/](verification/README.md#running).

Two further environment variables, both **off by default**, make a call visible
([observability.py](src/mpfbmcp/observability.py)). They carry the `MPFB_MCP_` prefix rather than
`MPFB_BRIDGE_`, because those two name *the add-on being addressed* while these say what this
process does with a call it has already decided to make:

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
direct Python dependency on MPFB, and none on the add-on either — everything crosses a TCP socket:

<a id="the-bridge"></a>

```
mpfb-mcp tool  →  backend.send()  →  {"command": ..., "params": {...}}  →  TCP 127.0.0.1:9877
                                                                  ↓
                                          mpfb_bridge: look the name up in a fixed table
                                                                  ↓
                                                          MPFB HumanService, etc.
```

`bridge/` holds the MPFB Bridge, a Blender extension of our own that dispatches named commands and
executes nothing a caller sends. It is **not** part of the pip package — `pyproject.toml` searches
`src/` only, so a top-level `bridge/` is outside its root entirely and needs no packaging change —
and it has its own linting, typing and test setup, taken from MPFB rather than from this
repository:

| Path | What it is |
|------|------------|
| [bridge/mpfb_bridge/](bridge/mpfb_bridge) | The add-on. `command_server.py` is the socket, the framing and the dispatch, and imports no `bpy`; `commands/table.py` is the closed vocabulary and is the one file to read to know everything the add-on can be asked to do, with one module per command beside it; `validation.py` is what a command declares it takes; `mpfb_resolution.py` is the `sys.modules` scan; `stats.py` is what the panel paints; `export_directory.py` is where an export goes, the one setting a command reads, written by the preference in `ui.py` or `--export-dir` in `cli.py` and never by a request; `ui.py`, `timer.py` and `cli.py` are the Blender-facing halves — `timer.py` drives the server in a windowed Blender and `cli.py` in a headless one. Operator ids are prefixed `mpfb_bridge.`, **never** `mpfb.` |
| [bridge/mpfb_bridge/shared/](bridge/mpfb_bridge/shared) | **Twenty-three modules, and none of them is a command.** What two or more commands must agree about, or would otherwise each write for themselves — the file-name rule, MPFB's asset section table, the modeling category scan, whether the expression stack explains the face, the phenotype, asset and target-stack readings a summary shares with its detailed tools, and since FR 036 the subject resolver (`subject_resolution.py`), the selection restore (`selection.py`), how a name MPFB does not publish is read (`mpfb_surface.py`) and plain Blender reads (`blender_data.py`, which since FR 039 also walks a character's family, so that the export copy and the export agree on it), since FR 040 how a procedural material setting is found, read and turned into sRGB hex (`material_settings.py`), and since FR 041 the character frame (`character_frame.py`), which rig moves a character and what each bone is for (`pose_controls.py`) and what the pose is now (`pose_reading.py`), and since FR 042 how a pose is written, checked and undone (`pose_writing.py`), and since FR 045 where a character stands, how it is moved and whether its garments' sub-rigs are bound to it (`placement.py`, which takes `services` for the meta-rig and sub-rig questions only MPFB answers). The count follows from a rule, not the other way round. Nothing here is reachable from the wire, which is why `commands/table.py`'s claim survives a second directory beside it. MPFB arrives as a leading `services` parameter rather than being resolved at import, so a disabled-and-re-enabled MPFB cannot leave a stale dict behind; `target_categories.py` additionally takes a per-call `tables` record, because a scan taken at startup would be blind to a target installed since; `asset_info.py` takes a per-call `Lookup` built from `services` instead. `pose_controls.py`' classification takes MPFB's root package name instead, for the one name it reads off a UI module. `performed.py`, `artifact_names.py`, `expression_panel.py`, `selection.py`, `blender_data.py`, `character_frame.py`, `pose_reading.py` and `pose_writing.py` take neither and read nothing out of MPFB's services ([rationale](specifications/architecture.md#shared-modules-and-what-warrants-one)) |
| [bridge/test/](bridge/test) | Its harness: pytest in a headless Blender, MPFB's arrangement. Not discovered by `unittest discover -s tests`, and must never be. It also produces a coverage report, through a `.coveragerc` here and an `a1_coverage.pth` that `run_to_install_pytest.py` writes into Blender's own site-packages. `tests/_fixtures.py` is what its command modules share: dispatch, the MPFB skip, a character, real rig/target/asset trees, target files that are real MPFB target data and an MHCLO a command can actually equip. `tests/` holds **only prefixed directories, each a layer run in order** — `aaa_addon/`, `bbb_shared/` (direct tests of the shared modules FR 036 added), `ccc_reading/`, `ddd_mutating/` (the twenty-three commands that change a `.blend`), `eee_composite/` — and unprefixed `<subject>_test.py` modules inside them ([rationale](specifications/testing.md#two-harnesses-split-at-the-directory-boundary)) |
| `bridge/.pylintrc`, `bridge/pyrightconfig.json`, `bridge/requirements-dev.txt` | MPFB's, copied and retargeted. Where this repository's conventions and MPFB's disagree about add-on code, MPFB's win |

The principles behind this layout are in
[specifications/architecture.md](specifications/architecture.md); the table below is the concrete
map, and carries only what is not stated there or in its sibling specifications.

| Module | What it is, and the local detail |
|--------|----------------------------------|
| [backend.py](src/mpfbmcp/backend.py) | **The seam**, and the one file a tool goes through to reach Blender. `send(command, params=...)` and nothing else: thirty tool modules importing the wire client directly would put the command name, the framing, the handshake and the address variables inside every one of them. It reads `MPFB_MCP_BACKEND` for exactly one purpose — a value left in somebody's client configuration gets one WARNING on the `mpfbmcp` logger saying it is no longer read, once per process, never on stdout. ([rationale](specifications/architecture.md#supporting-a-second-backend)) |
| [bridge_connection.py](src/mpfbmcp/bridge_connection.py) | **The wire**: JSON + NUL framing, one request per connection, `MPFB_BRIDGE_HOST`/`MPFB_BRIDGE_PORT`, and **the client half of the handshake** — every request declares `protocol_version`, and the first call per `(host, port)` probes `get_status` for `min_supported_protocol_version`, memoised thereafter and dropped on a connection failure. Its `PROTOCOL_VERSION` is a hand-kept duplicate of the add-on's, because importing `bridge/` would pull `bpy` into a process that has no Blender. ([rationale](specifications/architecture.md#the-wire)) |
| [observability.py](src/mpfbmcp/observability.py) | The per-call record and this package's logger. Hangs off `send_command()` and nowhere else; `begin_command()` opens a record, into one directory and one index in call order. The request is written to disk **before** the socket call, so a call that hangs, times out or takes Blender down still leaves behind what caused it. The handshake probe is a call and is recorded as one, so a tool's own request is usually sequence `0002`. **Never write to stdout from anywhere in this package** — it is the JSON-RPC channel. ([rationale](specifications/observability.md#diagnostics-attach-at-the-socket-boundary-never-inside-blender)) |
| [reference/](src/mpfbmcp/reference) | The two vendored tables the lookup tools hand out: `urls.py` (a copy of MPFB's `ui/weburls.py`, plus this package's own ecosystem links and the prose for both) and `docs.py` (nineteen curated paths into mpfb2's `docs/` tree, with the rule that builds two URLs from each). Imported here and never sent anywhere. Both drift and neither can be checked without the network, so `tests/test_reference_drift.py` checks them against a sibling `../mpfb2` and skips without one. ([rationale](specifications/architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on)) |
| [arguments.py](src/mpfbmcp/arguments.py) | **The shape validators every tool calls**: an optional subject name, a required asset name, a real `bool`, a non-negative count that is not a `bool`, optional non-empty text, and `mode` (`merge`/`replace`), which two tools take. Also `refuse_undeclared()` and `RETIRED_ARGUMENTS`, the one rule no tool calls: the server refuses an argument the called tool does not declare, naming a retired spelling's replacement. Beside `tools/` rather than in it, because a module there is a tool. The wording a tool owns is an argument at its call site, and why truthiness would harm a given flag is a comment there. ([rationale](specifications/tool-interface.md#validate-before-crossing-the-socket)) |
| [artifact_names.py](src/mpfbmcp/artifact_names.py) | The three arguments in this package that become a **path**: which characters a preset's, a saved expression's or an export's name may hold, checked before anything is sent. One rule, the noun in the refusal its only argument. A module rather than a helper copied into the four tool modules that take one, because a disagreement between them would let a file be written under a name that cannot be addressed back. `bridge/mpfb_bridge/shared/artifact_names.py` carries the same rule for the far side; `tests/test_save_preset.py` runs the two over one table of names, as all three nouns. ([rationale](specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)) |
| [tools/](src/mpfbmcp/tools) | One module per MCP tool, each with `register(mcp)`. See the tool table below. ([rationale](specifications/architecture.md#one-module-per-tool)) |
| [__init__.py](src/mpfbmcp/__init__.py) | `build_server()`: builds the server, calls each tool module's `register()`, and dedents every description once (FastMCP sends `fn.__doc__` verbatim). The server is a `FastMCP` subclass whose `call_tool` refuses an undeclared argument, since FastMCP drops one before any tool sees it. `main()` runs it over stdio. |

**Adding a tool touches exactly four things**: a module in `tools/`, one `register()` call in
`__init__.py`, a module in `bridge/mpfb_bridge/commands/`, and one entry in
`bridge/mpfb_bridge/commands/table.py`. Nothing shared is edited — a command that wants a shared
module imports it. If a change to shared code is needed to add an ordinary tool, the layout has
drifted. A tool that answers without Blender at all touches two of the four: `mpfb_list_docs` has
no command.

### The forty-two tools

Tool module, **bridge command** and test module all share a name: `mpfb_set_skin` is
`tools/set_skin.py`, `bridge/mpfb_bridge/commands/set_skin.py` and `tests/test_set_skin.py`.
**Two exceptions**, both deliberate: `mpfb_list_docs` has no command, because it never crosses the
socket — so there are forty-one commands for forty-two tools; and `mpfb_get_status`'s command
is `get_mpfb_status`, because `get_status` is the bridge's own state and two commands answering
"status" about two different pieces of software is a collision that is cheap now and permanent
later.

**The module docstring is where the reasoning lives**; the line below is only enough to find the
right one.

| Tool | The distinctive thing about it |
|------|-------------------------------|
| `mpfb_get_status` | Absence is an answer: classifies the install `absent`/`not_initialized`/`ok` rather than failing. The only user of `MPFB_STATUS_BOOTSTRAP`. |
| `mpfb_create_human` | Wraps `HumanService.create_human()`. Eleven flat macro sliders rather than a nested dict. |
| `mpfb_list_objects` | Which MakeHuman objects are in the scene. Validates argument *shape*, never the type vocabulary — the far side answers that with `object_type_recognized`/`known_object_types`. **The first migrated tool** (FR 030) and the template the other twenty-three followed, which is why its test module is the one to read first. |
| `mpfb_get_object_info` | What an object is, what it was made from, what belongs with it. Three `asset_info` shapes, three resolution outcomes each. |
| `mpfb_list_rigs` | Catalogue. Predicts, per rig, which file would load and whose weights come with it — via `rig_lookup.py`, so `mpfb_add_rig` cannot disagree. |
| `mpfb_list_assets` | Catalogue, and the first answer that does not fit: filtered, capped and paged. Reports `pack` (from a directory convention) and both the passable `path` and the portable `fragment`. |
| `mpfb_list_targets` | Catalogue. The one tool that is genuinely side-effect-free — no MPFB cache populated, no preview loaded, hence no `refresh`. Reports `shapekey_name` from MPFB, since a name over 60 characters is encoded. Its scan of the user's target directories is per call, which is what lets it see a target installed since Blender started. |
| `mpfb_list_asset_materials` | Catalogue for something that is **not** an asset library section, so `mpfb_list_assets` cannot name it. Its answer is stale by design: MPFB caches that scan and nothing invalidates it by default. `refresh` clears the cache via MPFB's own (previously uncalled) invalidator — global to every asset, not only this one, which is why the response says so through `cache_invalidated` rather than leaving it implicit. |
| `mpfb_get_macro_details` | Reads a character's phenotype. Subject resolved from any object in the character's family. |
| `mpfb_set_macro_details` | Writes it. Sliders default to `None`, not `0.5` — "not mentioned" and "set to the default" are different requests. Writes every property, then recalculates **once**. |
| `mpfb_refit_human` | Refits everything to a changed body. Detects the generated-Rigify-rig-with-no-meta-rig case, which `HumanService.refit()` reports only through an `operator` an MCP tool has none of. |
| `mpfb_get_target_stack` | Reads modeling targets. Reads `key_blocks` directly, since `TargetService` cannot see a shape key whose name contains "basis" — confirmed against a real MPFB by its bridge tests. |
| `mpfb_get_face_units` | Reads the 52 ARKit `!ex-` shape keys. Reports `known_face_units` (grouped by region) and `faceunits01_installed` on **every** answer, since neither depends on resolving a subject — the vocabulary that costs nothing to send in a response and a lot to send in every tool description. |
| `mpfb_set_targets` | The one **batched** tool: lists of dicts, because a round trip costs ~250 ms and a target costs milliseconds. Resolves every entry before writing any. |
| `mpfb_symmetrize_targets` | Copies one side onto the other. Zeroes the opposing target first, or pruning deletes the wrong half of a pair. |
| `mpfb_set_face_units` | Composes a face from ARKit units, batched like `mpfb_set_targets`. **The first tool gated on an optional asset pack** (`faceunits01`) rather than on MPFB itself; refuses up front when it is absent and reports `could_not_load` per unit when the pack's own install probe passed but a specific target file still had not shipped. `refit` defaults to **true**, unlike every other refitting tool and unlike the composer panel (FR 026 said it matched; FR 027 found it does not and kept the default on its merits). What it writes is transient, and **every answer says whether the expression stack still explains the face** (`matches_stack`) — the two-mechanism model is explained in this tool's description and nowhere else. |
| `mpfb_list_expressions` | Catalogue of saved expressions, the files MPFB's expressions-library panel draws sliders from. `fragment` is the address. Reports what MPFB's own scan drops: `unreadable` files and **`shadowed`** ones — a user-data file hidden behind a same-named file in a higher-priority root, which MPFB's panel claims cannot happen. `refresh` is the pack probe only; the file scan is never cached. |
| `mpfb_get_material_settings` | The procedural eye, LAYERED skin and MakeSkin colour-adjustment settings, **exactly as `HumanService`'s serializer saves them** — found its way, keyed its way, and checked against it by the bridge tests. No socket name is known on either side of the socket: they are read off the live node, via `shared/material_settings.py`. Reports `linked`, `ranges`, `srgb_hex` (derived) and `material_shared_with` beside each value; `section` exists because the whole answer measured 21 KB. |
| `mpfb_get_expression` | Reads the applied-expressions stack and answers what MPFB never does: **does the stack explain the face?** `matches_stack`/`unexplained_face_units` come from `shared/expression_divergence.py`, the one implementation all three expression-aware tools report through. Does not restate the 52 live values — that is `mpfb_get_face_units`. |
| `mpfb_get_character_summary` | One character in one call: phenotype, rig, assets, skin, target rollup, face. **Never a second opinion** — each section is read by the shared module its detailed tool uses (`macro_reading.py`, `asset_info.py`, `target_rollup.py`, `expression_divergence.py`) and carries a subset of that tool's fields under the same names. Reports no fact a detailed tool does not; `macro_drift` was added to `mpfb_get_macro_details` so that stays true. The rollup is **capped** (25 modifiers, 8 asymmetries, largest kept, `rollup_truncated`) to keep the worst case under 8 KB. |
| `mpfb_get_pose_controls` | Which bones pose a character, by **body part** and **role**, rest positions in the **character frame** (`forward`/`left`/`up` from the rig object, so a moved or turned character reads the same). The rig is the armature the basemesh's modifier points at; a meta-rig is refused (`rigify_not_generated`). Generated Rigify is classified **live** from bone collections and Rigify's naming, `game_engine` from a token table (it has no collections), the default rig from a table checked against MPFB's helpers; any other rig is listed unclassified, never guessed. Switches carry what each end means and a parent switch its `parent_names`, read off the property. `face` only when named, always counted; **`hidden_by_default` controls left out unless `include_hidden`** (on `game_engine` the flag is derived by role, checked against `human_toes`' collections), `roles`, `switch_names` (the rig's own names, so checked bridge-side) and `compact` (switch entries too) narrow further, and `counts_by_role`/`hidden_by_body_part`/`counts_by_switch` count every cut. Explains the posing vocabulary for every later posing tool. |
| `mpfb_get_pose` | What is off rest **including scale**, which MPFB's `get_pose_as_dict()` does not record (a Rigify fist is scale). Each posed control's current `head` beside `moved_by`, rotation as axis-and-degrees in the frame; landmarks on **deforming** bones; per limb `stretched`, `reach_ratio`, `target_unreachable`, derived with tolerances in `shared/pose_reading.py`, which FR 042's writers share. Updates the depsgraph before reading. |
| `mpfb_set_pose_bones` | Moves, rotates, aims and scales controls, batched, in the **character frame** and in exactly the shape `mpfb_get_pose` reads back, so a read-back is a write. Parent first, depsgraph per bone. Refuses a bone that is not in charge (not a control, a chain `IK_FK` handed away, an FK bone an MPFB helper drives) with `write_instead` — for the switch, **an entry for another tool**. Checks locks after writing, since `pose_bone.matrix` ignores them, and **rolls the batch back exactly** on any failure. Reports `achieved` with `deviation`, measured. |
| `mpfb_set_pose_switches` | Rigify's switches by `body_part` and `switch`. **Snaps by default** — IK/FK both ways, the pole, parent switches — through a **port of Rigify's snap code**, because the generated operators live in `rig_ui.py` and are missing whenever it has not run; the chains come from Rigify's naming, checked against `rig_ui.py` by a bridge test. `snap_error` measures every snap; `raw: true` writes the bare value. Refuses any rig but generated Rigify (`rig_has_no_switches`). |
| `mpfb_reset_pose` | Back to rest by body part, **the face included by default**, `include_switches` optional. `restore_with` is the `mpfb_set_pose_switches` and `mpfb_set_pose_bones` calls that put back exactly what it reset — the undo Blender's own stack cannot give — and `not_restorable` names reset bones those tools would refuse, none of which moved the body. |
| `mpfb_apply_expressions` | Changes the stack, batched, and lets MPFB rebuild the face — which **discards anything composed on top**; `discarded_face_units` names what the rebuild actually moved, measured on both sides of the write. `merge`/`replace`, weight 0.0 removes, `replace` with `[]` clears. Resolves every fragment first; refuses without `faceunits01` except for removals. Keeps MPFB's library panel in step by calling into its `useexpression` UI module (`panel_synced`). |
| `mpfb_save_expression` | The second tool to write **outside the `.blend`**, and the only way a composed face crosses into the library: saves the live **shape keys** (not MPFB's stale composer sliders) as `<name>.json` in user data. Refuses a name a higher-priority root would shadow. Changes nothing on the character; `apply_with` is the `replace` call that makes the face durable. |
| `mpfb_add_rig` | First consumer of a catalogue's identifiers. **Dispatches on the `custom.` prefix itself**, because MPFB's two adding functions are not interchangeable and neither miss reads as a mistake. Names every asset it just failed to rig. **Moves a turned basemesh's rotation to the rig**, as MPFB moves its location, since MPFB drops it and fits a rig facing the other way. |
| `mpfb_generate_rigify_rig` | Finishes a Rigify meta rig. The only mutating tool that **cannot restore the caller's selection** — the operator selects its own result — so it reports `active_object_after`. Gives the generated rig the meta rig's place in the world, which Rigify's generation drops. |
| `mpfb_add_asset` | Equips an MHCLO asset. Takes the catalogue's `path` *or* its `fragment`, exactly one, and always reports which file it landed on. `object_type` (MPFB's `asset_type`) is **required**: MPFB's `"Clothes"` default is wrong for six of the eight types and mislabels a body part silently. |
| `mpfb_remove_asset` | Takes it off properly — deleting the object would leave the body's mask modifier and the garment's sub-rig behind. |
| `mpfb_set_skin` | Five material models. Follows **MPFB's settings panel rather than the function signature**: `skin_type` defaults to `MAKESKIN`, and `material_instances` is coerced off for three types — so the *default call creates no material instances*. Reports requested beside used. |
| `mpfb_list_urls` | The community addresses, read out of MPFB's `ui/weburls.py` by prefix. The only tool that **catches a connection failure and answers anyway** — from a vendored copy, saying so — because the download link is the answer precisely when nothing is running. Its command is the third declaring `requires_mpfb=False`. One narrow case differs between the transports on purpose: a protocol handshake refusal is an error rather than a fallback, because a version mismatch is a fault to fix rather than a circumstance to paper over. |
| `mpfb_list_docs` | Addresses for mpfb2's `docs/` tree, which the extension does not ship. The only tool with **no bridge command**: a local table and a URL rule, no socket, no Blender, no MPFB. |
| `mpfb_list_presets` | Catalogue of **files**, not of anything MPFB computes: size and age come from `os.stat` and exist nowhere else. Uncapped, and reports what MPFB's cached list would gain from a rescan without being asked to rescan. Its name rule (`artifact_names.py`) exists **twice** — tool side and bridge module — and `test_save_preset.py` runs both over one table of names. |
| `mpfb_save_preset` | The first tool to write **outside the `.blend`**, which is where `overwrite: False`, the name-not-a-path rule and the absolute path in every answer come from. Collapses MPFB's two operators into one, and deliberately does not emit their generated-Rigify warning. |
| `mpfb_create_human_from_preset` | Named for the hazard: it **creates** a character rather than loading into one. Builds every settings dict from `get_default_deserialization_settings()`, since MPFB reads eight of its keys with `[]`. The one tool whose failure is not a no-op — a character is built in stages, so `objects_created` names what a mid-way failure left behind. |
| `mpfb_set_material_settings` | The third **batched** tool: `eyes`, `skin` and `color_adjustments`, keyed like the preset, resolved in full before anything is written. `value` for a float socket, `color` (four scene-linear numbers) for a colour one. Refuses a **linked** socket, naming the `color` group's socket as `write_instead`; enforces a declared range except where MPFB's own value contradicts it. Writes through the deserializer's own functions and borrows no selection or mode. |
| `mpfb_set_asset_material` | Has **no service function to wrap at all**; the mechanism exists only in a UI operator, reimplemented from services with three of its quirks reproduced rather than tidied up. Being an add-on made importing that operator possible for the first time, which is why its command's docstring restates the rule against it rather than pointing at the specification. |
| `mpfb_create_export_copy` | MPFB's Export copy panel **rebuilt from services**, its eleven options and defaults, plus a GameEngine swap the panel lacks; **the original is not changed**. **Repairs MPFB's own copy** where it falls short of its comment - a sub-rig's garment not copied, `Armature PV` and Rigify's armature-data drivers left on the original - and lists each in `copy_repairs`. Reports a baked face (`face_baked_into_mesh`), the three pack probes on every answer (the viseme packs have no MPFB probe), and refuses the one combination MPFB fails on part way (`proxy_cannot_be_baked`). Puts back **every** object's selection (`selection.restored_all`). |
| `mpfb_export_character` | One character to one self-contained `.fbx`, `.glb` or `.usdz`. Takes a **name only**: the directory is the human's, read by `export_directory.py`, and `path_resolved_by` says who chose it. Four engine presets, every value cited in the command docstring. `readiness` reports what another application will lose - measured by re-importing - and never refuses. Selects the family (`blender_data.with_descendants`) and puts every selection back. |
| `mpfb_place_character` | Where a character stands (`position`, world metres, a key left out kept) and which way it faces (`facing`, degrees from world -Y, or `face_toward` a point or an object). Moves the **root** - the rig, else the body - and a hidden meta-rig beside a generated rig. **Yaw only**: a tilted root is refused a turn. Reports `footprint` for spacing and `restore_with`; read back by the summary's `placement`, from the same `shared/placement.py`. `subrigs_broken` is **measured**: a move breaks no sub-rig, equipping one away from the origin does, and `mpfb_refit_human` re-binds it. |

### What is validated on this side of the socket

The rule is [validate the shape, never the vocabulary](specifications/tool-interface.md#validate-before-crossing-the-socket).
The general shape rules - a real `bool` not merely a truthy value, a count that is not a `bool`,
an empty string that is not an omission - are in [arguments.py](src/mpfbmcp/arguments.py), with
their reasons. These are the checks particular to a tool, and each exists because the alternative
fails silently:

- **`mpfb_set_macro_details` enforces 0.0-1.0 here or nowhere.** MPFB's macro properties carry a
  default but no `min`/`max`; it is the scene-level proxy property behind MPFB's sliders that
  clamps, and a command does not go through it.
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
  authoritative check stays in the command either way; see
  [the exception in architecture.md](specifications/tool-interface.md#validate-before-crossing-the-socket)
  for what earns one. `mode` (`mpfb_apply_expressions`, `mpfb_set_face_units`) is checked locally
  too, by `arguments.validated_mode`, and is **not** a third: no MPFB function sees it, so it is
  this package's own vocabulary and a shape.
- **`mpfb_apply_expressions` takes `fragment` only, never `path`**, and a fragment at most once per
  call. A stack row *is* a fragment; a path would have to be turned back into one, lossily.

## Tests

Stdlib `unittest`, no pytest, 584 tests. **Two layers per tool that crosses the socket** — the
wrapper with `send_command` mocked below the seam, and the bridge path against `fake_bridge`.
Everything about what a tool *answers* is checked against a real MPFB in `bridge/test/`, which is
[where a tool is tested](specifications/testing.md#a-tool-is-tested-where-it-runs). FR 033 deleted
the third layer, which executed an assembled Python program against stub Blender and stub MPFB
services, along with the program it was about: 1059 tests became 353.
**`bridge/` has a second harness of its own** — pytest inside a headless Blender, MPFB's
arrangement rather than this one — and the split is at the directory boundary: a bridge test
imports `bpy` and would fail at import, so `unittest discover -s tests` must never find one. See
[testing.md](specifications/testing.md#two-harnesses-split-at-the-directory-boundary) and
[bridge/test/README.md](bridge/test/README.md).
**Read [specifications/testing.md](specifications/testing.md) before adding or changing a
test** — in particular the rule that a fixture reproduces the install rather than a convenient
one, and the list of what the suite can never establish.

| Module | What it covers |
|--------|----------------|
| [fake_bridge.py](tests/fake_bridge.py) | No tests. The throwaway `socketserver.TCPServer` standing in for the add-on, plus the env-var bookkeeping (`EnvVarTestCase`) every test that points mpfb-mcp at it needs. Five abilities, each load-bearing for at least one test: answer differently per request, answer nothing and close, keep the raw request bytes, answer in chunks, and answer raw bytes that are not a well-formed frame. |
| [test_bridge_connection.py](tests/test_bridge_connection.py) | The bridge's wire protocol and the handshake: framing across a split `recv()`, a refused connection naming the preferences panel, one probe per address rather than one per call, a mismatch in both directions naming which end to upgrade, and the hand-kept `PROTOCOL_VERSION` read out of the add-on's source (skipped where that source is absent). |
| [test_backend.py](tests/test_backend.py) | The seam: that a call reaches the bridge under the command it named, that the parameters arrive unreshaped, that the frame's keys are exactly `command`/`params`/`protocol_version`, that an envelope comes back as the add-on wrote it, and that a set `MPFB_MCP_BACKEND` gets one WARNING and one only. Asserted by *what arrived at a fake server*, not by which mock was called. |
| [test_observability.py](tests/test_observability.py) | The one component fully testable on this side of the socket, and held to a higher bar accordingly. |
| [test_description_budget.py](tests/test_description_budget.py) | What an MCP client downloads before any work happens, measured against a ceiling. Run as a script it prints the per-tool table instead. |
| [test_vocabulary.py](tests/test_vocabulary.py) | The argument vocabulary across all forty-two, on the server that ships: every tool refuses an undeclared argument before sending, and a real in-memory MCP client sees that as an `isError` result; the retired spellings table is coherent; no argument name carries two JSON types, an array of names and an array of objects counting as two. |
| [test_create_human.py](tests/test_create_human.py) | The eleven sliders' 0.0-1.0 rule, enforced here and nowhere else, and what reaches the wire. |
| [test_get_status.py](tests/test_get_status.py) | The smallest wrapper layer there is — this tool takes no arguments — plus the one bridge-path test that exists only for it: the command sent is `get_mpfb_status` and **not** `get_status`. |
| [test_list_objects.py](tests/test_list_objects.py), [test_get_object_info.py](tests/test_get_object_info.py) | Argument shape, and what reaches the wire. `test_list_objects` was the first migrated one and reads as the template the other twenty-three followed — a wrapper class and a thin bridge-path class, with everything about what MPFB answers in `bridge/test/tests/ccc_reading/list_objects_test.py`. |
| [test_list_rigs.py](tests/test_list_rigs.py) | `refresh` must be a real bool, and what reaches the wire. The rig tree with its asymmetries — a rig with no weights of its own, a weights file with no rig, a rig absent from the UI enum — is `bridge/test/`'s, over MPFB's own `LocationService`. |
| [test_list_targets.py](tests/test_list_targets.py) | Argument shape and paging. The two-source merge, the `.target.gz` MPFB's own scan misses and the name long enough to be encoded are asked of a real MPFB in `bridge/test/tests/ccc_reading/list_targets_test.py`. |
| [test_list_assets.py](tests/test_list_assets.py) | The cap-and-page rules, which are about the size of an *answer* and are enforced here. |
| [test_get_macro_details.py](tests/test_get_macro_details.py), [test_set_macro_details.py](tests/test_set_macro_details.py), [test_refit_human.py](tests/test_refit_human.py) | The 0.0-1.0 rule, which MPFB's macro properties carry no `min`/`max` for, and the rule that an unnamed slider is left alone rather than defaulted. |
| [test_get_target_stack.py](tests/test_get_target_stack.py), [test_set_targets.py](tests/test_set_targets.py), [test_symmetrize_targets.py](tests/test_symmetrize_targets.py) | `mpfb_set_targets`' two different ranges and its rejection of an unknown key, and `mpfb_symmetrize_targets`' `direction` — the package's only required argument. The category walk and the write order are `bridge/test/tests/ddd_mutating/`'s. |
| [test_get_face_units.py](tests/test_get_face_units.py), [test_set_face_units.py](tests/test_set_face_units.py) | Entry shape for `mpfb_set_face_units`, and that the ARKit vocabulary is deliberately *not* checked here — it is answered by the payload against MPFB's own `ARKIT_FACEUNITS`, per `bridge/test/tests/ddd_mutating/set_face_units_test.py`, which is also where the pack-absent refusal, the partial-install `could_not_load` case and the `merge`/`replace` semantics are checked against a real install carrying the `faceunits01` pack. |
| [test_list_expressions.py](tests/test_list_expressions.py), [test_get_expression.py](tests/test_get_expression.py), [test_apply_expressions.py](tests/test_apply_expressions.py), [test_save_expression.py](tests/test_save_expression.py) | Entry shape and `mode` for `mpfb_apply_expressions`, a repeated fragment refused locally, and that the fragment vocabulary is *not* checked here; the name rule for `mpfb_save_expression` over the preset tests' table, and each metadata argument's type. Everything the four answer is `bridge/test/tests/`'s: `ccc_reading/list_expressions_test.py`, `ccc_reading/get_expression_test.py`, the two command modules in `ddd_mutating/`, and `eee_composite/expression_divergence_test.py`, which asks all three divergence users about one character and runs the compose-save-apply round trip. |
| [test_get_character_summary.py](tests/test_get_character_summary.py) | Only the one argument's shape and what reaches the wire, which is right. The claim the tool exists for — every shared field equals its detailed command's answer — is `bridge/test/tests/eee_composite/get_character_summary_test.py`'s, by dispatching both. |
| [test_get_pose_controls.py](tests/test_get_pose_controls.py), [test_get_pose.py](tests/test_get_pose.py) | `body_parts`', `roles`' and `switch_names`' shape - a non-empty list of distinct strings, one rule in `arguments.validated_names` - and that no such vocabulary is checked here; `include_hidden` and `compact` real bools; what reaches the wire. The classification of every family, the hidden default and the counts that cover each filter, the frame, the switches against the generated `rig_ui.py`, reach and stretch with `IK_Stretch` on and off, the scale-only fist and read-only-ness are `bridge/test/tests/ccc_reading/get_pose_controls_test.py`'s and `get_pose_test.py`'s; the frame's axes, the default-rig table against MPFB's helper classes and `game_engine`'s hidden-by-role rule against `human_toes` are `bbb_shared/`'s. |
| [test_set_pose_bones.py](tests/test_set_pose_bones.py), [test_set_pose_switches.py](tests/test_set_pose_switches.py), [test_reset_pose.py](tests/test_reset_pose.py) | Entry shape only: known keys (a misspelled `move_too` fails here), at most one change of each kind and at least one, frame vectors of finite numbers, rotations of exactly `axis` and `degrees`, positive scale factors, real bools, nothing named twice. **No bone, body part or switch vocabulary is checked here.** Every change kind on a moved and turned rig, every refusal and the rollback, every snap in both directions against `snap_error`, the snap chains against `rig_ui.py` on `human_toes` and `game_engine`, and `restore_with` restoring a pose exactly are `ddd_mutating/`'s; `pose_writing.py` itself is `bbb_shared/`'s. |
| [test_add_rig.py](tests/test_add_rig.py), [test_generate_rigify_rig.py](tests/test_generate_rigify_rig.py) | That the rig identifier vocabulary is deliberately *not* checked here, and that `meta_rig_action` is — one of the two vocabularies that earn a local check, since MPFB silently falls back to `"hide"`. |
| [test_add_asset.py](tests/test_add_asset.py), [test_remove_asset.py](tests/test_remove_asset.py) | That `object_type` is required and that exactly one of `path`/`fragment` is allowed, both refused before anything is sent. |
| [test_create_export_copy.py](tests/test_create_export_copy.py), [test_export_character.py](tests/test_export_character.py) | Every argument's shape before sending: nine real bools, `KEEP`/`REMOVE`/`BAKE`, `material_type`, `suffix`'s bound, `format` and `target_engine` - all this package's own vocabularies, so shapes - and `export_name` over the preset tests' table of names; that no directory can be named; and that a preset/format pair is the command's to judge. Everything the two write and copy is `ddd_mutating/create_export_copy_test.py`'s, `ddd_mutating/export_character_test.py`'s and `eee_composite/export_roundtrip_test.py`'s, which re-imports every format. |
| [test_place_character.py](tests/test_place_character.py) | Shape only: `position` and a `face_toward` point are objects of known keys and finite numbers, `face_toward` is an object name alone or a point with `x` and `y`, `facing` is finite, `facing` and `face_toward` never both, and a call naming none of the three is refused. **No object name is checked here.** Every rig family, the meta-rig that moves along, `get_pose` unchanged by a move, `restore_with`, an external parent, the tilted refusal, the footprint and the sub-rig sequence are `ddd_mutating/place_character_test.py`'s; the reading and the write are `bbb_shared/placement_test.py`'s. |
| [test_get_material_settings.py](tests/test_get_material_settings.py), [test_set_material_settings.py](tests/test_set_material_settings.py) | `section` checked locally, being the preset's keys rather than MPFB's; each entry's shape, one of `value`/`color`, four finite non-negative colour components, and a repeated socket refused. **No socket or group vocabulary is checked here.** Everything the two answer — every section, serializer agreement key for key, the linked, kind and range refusals, borrowing nothing — is `ccc_reading/get_material_settings_test.py`'s and `ddd_mutating/set_material_settings_test.py`'s, and the preset round trip in both orderings of tint and alternative material is `eee_composite/material_settings_roundtrip_test.py`'s. |
| [test_set_skin.py](tests/test_set_skin.py), [test_set_asset_material.py](tests/test_set_asset_material.py), [test_list_asset_materials.py](tests/test_list_asset_materials.py) | `skin_type` is the other locally checked vocabulary, and this is where the defaulting that follows MPFB's settings panel rather than the function signature is pinned. |
| [test_list_presets.py](tests/test_list_presets.py), [test_save_preset.py](tests/test_save_preset.py), [test_create_human_from_preset.py](tests/test_create_human_from_preset.py) | The name whitelist, exercised exhaustively **before** anything is sent, since that is where it lives and a name that escapes the config directory must never cross the socket at all. `test_save_preset` also holds the **two-way drift check** between `artifact_names.py` and `bridge/mpfb_bridge/shared/artifact_names.py`, run for presets, saved expressions and exports alike, moved here when FR 033 deleted the third copy. |
| [test_list_urls.py](tests/test_list_urls.py) | The four states that must all be successful answers — live, MPFB absent, MPFB present without its `weburls`, Blender unreachable — and the one that must not be: a command that failed inside Blender. The merge runs against hand-built answers carrying an extra `URL_` key and a missing one, so enumerate-by-prefix and the staleness report are tested rather than assumed. |
| [test_list_docs.py](tests/test_list_docs.py) | Entirely local, and the only tool module with no bridge-path layer: URL construction from `path`, both filters, and that `curated`/`tree_document_count`/`tree_url` are on every answer including the empty one. |
| [test_arguments.py](tests/test_arguments.py) | The shape validators called directly, with every refusal sentence pinned word for word, including the parts a tool passes in. The tool modules' own tests assert `ValueError` and almost never its text. |
| [test_reference_drift.py](tests/test_reference_drift.py) | The two vendored tables against a sibling `../mpfb2` checkout, `skipUnless` it exists. Parses `weburls.py` with `ast` rather than importing another repository's module, and asserts the parse found something so that "no differences" cannot pass vacuously. ([why a skipping test is worth having](specifications/testing.md#a-test-may-depend-on-a-sibling-checkout-if-it-skips-without-one)) |
| [test_verification_smoke.py](tests/test_verification_smoke.py) | The one test that reaches outside `src/`: `verification/smoke.py`'s item table, imported by path, must have exactly one entry per registered tool and name no key the tool's own description does not. A coverage rule that only fires with a Blender running is one that fires late. |

Anything needing real MPFB is verified against a running Blender, and a feature request is
expected to say so explicitly — in **its own subdir**, as a script that runs during the effort and
moves to `done/` with it. What it adds to [verification/](verification/) is at most one smoke item.
That directory is a sibling of `tests/`, four files, not discovered by `unittest discover -s tests`
and not shipped; it changes nothing outside the `.blend`. See
[verification/README.md](verification/README.md) for how to run it and the two things it cannot
put back.

**One harness process at a time**: two against one Blender interleave, and the second fails in
ways that look like tool defects.

## Code conventions in this repo

`from __future__ import annotations` and an explicit `__all__` in every module; `.format()`
rather than f-strings throughout; readability and developer experience treated as prioritized
non-functional requirements, the add-on's code included (see
[specifications/architecture.md](specifications/architecture.md#readability-and-developer-experience-are-prioritized));
SPDX `GPL-3.0-or-later` header on test modules; module-level docstrings that explain *why* (the
MPFB-extension bootstrap, the deliberate protocol duplication) rather than restate the code.

## Relationship to sibling projects

- **[mpfb2](https://github.com/makehumancommunity/mpfb2)** — the actual MPFB Blender addon this server drives. Its
  `bl_ext.*.mpfb` services (`HumanService`, `TargetService`, asset/skin/rig functions, etc.) are
  what the MCP tools wrap. `docs/services/humanservice.md` documents `HumanService`'s full API.
- **[blender_mcp](https://projects.blender.org/lab/blender_mcp)** — the generic Blender MCP server this project's
  Blender-side logic used to be executed by, and which `bridge/mpfb_bridge/command_server.py` took
  its socket and framing from. Nothing depends on it now; it is kept as the model the bridge was
  copied from, and as what the `blender_mcp` in an old commit message means.
- **[makehuman-static-website](https://github.com/makehumancommunity/makehuman-static-website)** — likely source for bundled MPFB
  documentation if a `mpfb_search_docs` tool is implemented.

## Backends

**There is one, and it is ours**: the MPFB Bridge in [bridge/](#the-bridge). There were two in
code between FR 030 and FR 033, chosen by `MPFB_MCP_BACKEND`, and the variable survives only to
report that it is no longer read.

Supporting *two third-party* add-ons used to be the plan — there are two unrelated projects called
"blender mcp" — and it is not any more.
[FR 028](feature-requests/done/028-pivot-to-specific-addon/README.md) replaced that plan with a
companion add-on of our own, which removes the third-party add-on from the path rather than
abstracting over which one it is. See
[vision.md](specifications/vision.md#superseded-which-blender-mcp-neither-in-the-end) for the
decision and
[NEXT_STEPS.md](feature-requests/NEXT_STEPS.md#superseded-second-backend-the-community-blender-mcp)
for the superseded entry, which is kept rather than deleted.
