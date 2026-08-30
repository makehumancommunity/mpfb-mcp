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

Proof of concept. Fifteen tools are implemented: `mpfb_create_human`, wrapping MPFB's
`HumanService.create_human()`; `mpfb_get_status`, reporting whether MPFB is present, initialized
and how it is configured; the object-finding pair `mpfb_list_objects` and
`mpfb_get_object_info`, which is how every later tool is meant to name the object it acts on; and
three catalogue tools, `mpfb_list_rigs`, `mpfb_list_assets` and `mpfb_list_targets` — what could be
*added*, rather than what is already there, each entry named by the identifier the adding function
will want. `mpfb_list_assets` is also the first tool whose answer does not fit, so it is filtered,
capped and paged, a convention `mpfb_list_targets` inherits. Finally, three tools that act on a
character that already exists — `mpfb_get_macro_details`, `mpfb_set_macro_details` and
`mpfb_refit_human` — which is where the conventions for *mutation* come from: a subject resolved
from any object in the character's family, a response reporting the prior state and the
consequences, and a not-ready world answered with a sentence rather than an exception. And below
the phenotype level, three more that reach the individual morphs: `mpfb_get_target_stack`,
`mpfb_set_targets` and `mpfb_symmetrize_targets`. Those are where two further conventions come
from — a *batched* mutating tool that resolves every entry before writing any of them, and what to
do when mpfb-mcp has to model a concept (a modeling *modifier*) that lives in MPFB's UI rather than
in any of its services. And two that put a *rig* on a character: `mpfb_add_rig`, the first consumer
of a catalogue tool's identifiers — it dispatches on the `custom.` prefix itself rather than letting
the caller pick between MPFB's two non-interchangeable adding functions — and
`mpfb_generate_rigify_rig`, which finishes the Rigify meta rig the first one produces. Those are
where the last convention comes from: **a tool reports an ordering constraint it cannot enforce**.
MPFB rigs a garment only if a rig exists when the garment is attached and never afterwards, so
`mpfb_add_rig` on a dressed character names every asset it has just failed to rig rather than
either refusing or staying silent; and generation is a separate tool precisely because "meta rig,
then clothes, then generate" cannot be written as one call. **The eight character-modifying tools
are the part of the code that has never been run against a real Blender** (see
[FR 007's](feature-requests/done/007-macro-details/README.md#verification-status),
[FR 008's](feature-requests/done/008-detail-targets/README.md#verification-status) and
[FR 009's verification status](feature-requests/done/009-add-rig/README.md#verification-status)).
See [specifications/vision.md](specifications/vision.md#target-tool-catalog) for what's planned
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
  - **[codegen/shared/](src/mpfbmcp/codegen/shared)** — the same kind of file, but for a concept
    two or more payloads model identically, named by the tool module in
    `assemble(..., shared=["target_categories.py"])` and concatenated between the prelude and the
    payload with its own labelled seam. There is exactly one so far:
    `target_categories.py` rebuilds MPFB's `target.json` category table plus the sections it
    synthesizes from the user's own target directories, which `mpfb_get_target_stack`,
    `mpfb_set_targets` and `mpfb_symmetrize_targets` all need in the same shape and none of them can
    import (`mpfb/ui/model/_modelsubpanels.py` builds it at *module import time*, so it is a
    snapshot from when Blender started). It exists because three copies of that scan would be three
    chances for two mpfb-mcp tools to disagree about what is installed, not because it is long.
    `rig_lookup.py` is the second, and it is there for the sharper version of the same reason:
    `mpfb_list_rigs` *predicts*, per rig, which file would be loaded and whose weights would come
    with it, and `mpfb_add_rig` then does it and reports the outcome. The overlap is about ten
    lines — too small to warrant a fragment on size, and not defensible as duplication on
    consequence, since MPFB resolves weights through a *fallback table* and two implementations
    disagreeing would make an ordinary rig look broken in one tool and fine in the other. Note this
    one was retrofitted: `payloads/list_rigs.py` was migrated onto it, which is the opposite call
    from the one made for `list_targets.py` (still listed in `NEXT_STEPS.md`) and which invalidated
    FR 004's live verification.
    Note the packaging detail: a package-data glob does not descend, so this is a *sibling* of
    `payloads/` with a glob of its own rather than a subdirectory of it. FR 002's rule is
    unchanged — adding an ordinary tool still touches only a tool module, a payload and a
    `register()` call. See
    [specifications/architecture.md](specifications/architecture.md#shared-fragments).
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
  `tools/list_targets.py` is the same shape minus `refresh` — it is the one catalogue tool that is
  genuinely side-effect-free, populating no MPFB cache and loading no preview — and it deliberately
  does not validate `section` against a vocabulary, since half the sections are synthesized from the
  user's own directories and could not be known here even in principle. Its payload holds the two
  things the request exists for: `shapekey_name`, taken from
  `TargetService.filename_to_shapekey_name()` rather than derived locally, because a name over 60
  characters is encoded and a caller using the filename addresses nothing *silently*; and the
  reimplementation (never the import) of `mpfb.ui.model._modelsubpanels`' user-target scan, which is
  what lets the tool see a target installed since Blender started.
  `tools/get_macro_details.py`, `tools/set_macro_details.py` and `tools/refit_human.py` are the
  first three that act on a *character* rather than on the install or the scene, and the first two
  that change one. Their subject is resolved the same way in all three — any object in the
  character's family, narrowed to the basemesh by
  `find_object_of_type_amongst_nearest_relatives()` inside the payload, with the resolved name
  reported back — so `name` validation here is the same shape check as everywhere else.
  `set_macro_details.py` is the one that validates *values*: MPFB's macro properties carry a
  default but no `min`/`max` (it is the scene-level proxy property behind MPFB's sliders that
  clamps), so 0.0-1.0 is enforced here or nowhere, and `prune`/`refit` get the same strict `bool`
  treatment `list_rigs.py` gives `refresh`. Its eleven sliders are `None` by default rather than
  `0.5`, because "not mentioned" and "set to the default" are different requests; only what the
  caller named crosses the socket, and the payload's ordering — write every property, then
  recalculate **once** — is what keeps a five-slider change the same cost as a one-slider one.
  Three things live in those payloads that could not live here: the preconditions (OBJECT mode,
  presence of shape keys), which MPFB meets with a bare `assert` and a log line respectively; the
  restoration of the previous active object and selection, in a `finally`; and the detection of a
  generated Rigify rig with no meta rig, which `HumanService.refit()` reports only through an
  `operator` an MCP tool has none of — it refits the mesh assets, silently skips the rig, and
  returns, so all three tools would otherwise claim a refit that half happened.
  `tools/get_target_stack.py`, `tools/set_targets.py` and `tools/symmetrize_targets.py` go one
  level below the phenotype, and all three share the `target_categories.py` fragment because a
  modeling *modifier* is not a `TargetService` concept at all. `set_targets.py` is the odd one out
  in this package's argument conventions and knows it: it takes **lists of dicts**, which
  [Validate before crossing the socket](specifications/architecture.md#validate-before-crossing-the-socket)
  otherwise rules out, because batching is not optional here — a round trip costs ~1 s and setting
  a target costs milliseconds. What pays for that is per-entry validation in the tool module,
  including rejecting an *unknown key* (a misspelled `catagory` is silent otherwise) and naming the
  failing entry by position, plus the payload's `resolution_errors` channel for the half that can
  only be answered inside Blender. Note the two different value ranges it enforces: -1.0..+1.0 for
  a `modifiers` entry, since a category *may* be a pair of opposites, and 0.0..1.0 for a `targets`
  entry, because that is a raw shape key value and Blender clamps one to that range. Which of the
  two ranges actually applies to a given category is only knowable inside Blender and comes back as
  a resolution error. `symmetrize_targets.py` is the only tool here with a **required** argument:
  `direction` has no default because which half of a face is the good one is not something a tool
  can guess, and guessing wrong destroys work with no undo across the socket — which is also why it
  has `dry_run`. Four things live in those payloads that could not live here: MPFB's write ordering
  (zero the opposing target first, or pruning deletes the wrong half of a pair); the resolve-then-
  apply split that makes a batch all-or-nothing; the fact that `set_target_value()` is a silent
  no-op for a target that is not on the mesh while `has_target()` matches an encoded name the
  writers do not, so each write first resolves *which* name a target is stored under; and the
  decision to read `key_blocks` directly in the read tool, since `TargetService` cannot see a shape
  key whose name contains "basis".
  `tools/add_rig.py` and `tools/generate_rigify_rig.py` are the first tools that *consume* a
  catalogue: `add_rig.py` takes `mpfb_list_rigs`' `identifier` verbatim and **dispatches on the
  `custom.` prefix itself** — the caller never names the function, because
  `add_builtin_rig("custom.my_rig")` would look for `rig.custom.my_rig.json` and `add_custom_rig()`
  strips the first seven characters of whatever it is given, and neither miss reads as the mistake
  it is. Its payload shares `rig_lookup.py` with `payloads/list_rigs.py` so the catalogue's weights
  prediction and this tool's weights outcome are one implementation. `generate_rigify_rig.py` is
  the odd one in two ways worth knowing: it is the only tool here that validates a **vocabulary**
  locally (`meta_rig_action` is a closed enum of MPFB's own, and `generate_rigify_rig()` silently
  falls back to `"hide"` for anything else, which would make a typo indistinguishable from a choice
  on the one argument whose wrong value cannot be undone), and it is the only mutating tool that
  **cannot restore the caller's selection** — the operator's own final act is to select and
  activate its result, so the response reports `active_object_after` instead. Six things live in
  those two payloads that could not live here: the prefix dispatch itself; the pre-checks that turn
  `add_builtin_rig()`'s `IOError`, `add_custom_rig()`'s `ValueError` and the `NotImplementedError`
  for a Rigify rig with Rigify disabled into sentences, which matter because `operator=None` — what
  generated code always has — is exactly what makes those functions raise instead of report; the
  translation of `add_builtin_rig()`'s bare, message-less `assert len(...rigify_colors) > 0`, which
  fires after the armature exists and before it is parented and so leaves a stray object to name;
  the enumeration of mesh assets and sub-rigs *before* the rig is added, which is what makes
  "attached while there was no rig" a precise claim rather than a guess; the check on
  `bpy.context.mode` as well as the object's, since building an armature runs `bpy.ops` calls that
  poll on the context; and the classification of *every* `Skeleton` relative rather than the first,
  because after generation the character's skeleton relative is the generated rig — Rigify
  generation re-parents the character onto its result — so "already generated" and "that is not a
  meta rig" are answers a single lookup could not tell apart.
- **[__init__.py](src/mpfbmcp/__init__.py)** — `main()`: builds the `FastMCP` server, calls each
  tool module's `register()`, runs over stdio. Together with a tool module and a payload file,
  this `register()` call is the *whole* of what adding a tool touches — no shared
  code-generation module is edited (a tool that wants a shared fragment names it in the
  `assemble()` call it was already making, which is not an edit to `codegen/` either).

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
  and stub MPFB services that the generated code of every tool below is executed against,
  shared because they need the same scene. The stubs deliberately reimplement MPFB's *actual*
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
- [tests/test_list_targets.py](tests/test_list_targets.py) — the same two layers, over a real
  `tempfile` target tree for the same reason as `test_list_rigs.py`: this payload's job is
  `os.walk()` and `os.listdir()`. The tree carries the cases the payload exists for — a section name
  present in *both* the bundled index and a user directory (MPFB merges those), a section with no
  categories, bundled directories with no section, a directory with no targets, a `.target.gz` where
  MPFB's own scan matches only `*.target`, a target reachable by two scans at once, and a name long
  enough to be encoded. The stub `TargetService.filename_to_shapekey_name()` reproduces MPFB's
  encoding table and not only its extension stripping; reproducing the easy half alone would make
  the test pass while hiding the bug it exists to catch. `find_asset_files_matching_pattern()` hands
  back `pathlib.Path`, as the real one does, so the payload's `str()` coercion is under test.
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
- [tests/test_get_macro_details.py](tests/test_get_macro_details.py),
  [tests/test_set_macro_details.py](tests/test_set_macro_details.py) and
  [tests/test_refit_human.py](tests/test_refit_human.py) — the same two layers, over stubs rather
  than a filesystem, since these payloads ask services rather than walking disk. What the stubs had
  to grow is the macro half of `TargetService`, and every part of it is there because leaving it out
  would make a test pass vacuously: `set_value()` stores **unclamped**, matching a property whose
  definition carries no `min`/`max` — a clamping stub would hide why the tool validates locally;
  `get_macro_info_dict_from_basemesh()` reads back through that same store, so the write-then-read
  round trip is genuinely under test; `reapply_macro_details()` really adds and removes stub shape
  keys, including the sub-0.0001 prune, so `shapekeys_removed`/`_added` are asserted against
  something that changed; and `create_shape_key()` carries MPFB's own OBJECT-mode `assert`. One
  thing is deliberately *not* reproduced: the macro interpolation is a stand-in table rather than
  MPFB's corner cases, because no payload depends on which targets come out, only on the shape of
  the answer. The fixtures parent garments to the **rig** rather than to the basemesh, as MPFB does
  on a rigged character, which is what makes the relationship walk do real work. Note also that
  these tests can say nothing at all about the thing the tools exist for — that a character
  modified here matches one modified through MPFB's own phenotype panel.
- [tests/test_get_target_stack.py](tests/test_get_target_stack.py),
  [tests/test_set_targets.py](tests/test_set_targets.py) and
  [tests/test_symmetrize_targets.py](tests/test_symmetrize_targets.py) — the same two layers, over
  a shared `DetailTargetTestCase` in `blender_stubs.py` that combines both earlier approaches: a
  real `tempfile` target tree *and* a stub character, because these payloads both walk the disk and
  write shape keys. The tree carries the four category shapes that matter (unsided with
  `opposites`, sided with all four `l-`/`r-` entries, no `opposites` at all, and a synthesized user
  category with a `full_path`) plus one bundled target that ships uncompressed, a sided category
  whose right-hand files are missing, an over-60-character user target, a target whose name
  contains "basis", and a gzipped custom target. Each of those is a branch, and the last two are
  divergences rather than mere edge cases. `StubTargetService` grew the write half, and every part
  of it reproduces a quirk rather than a convenience: `set_target_value()` is a **silent no-op**
  for an absent name (a raising stub would make the `has_target`-then-`load_target` logic look
  unnecessary), `get_target_value()` returns `0.0` for one, `has_target()` checks the encoded name
  while the writers do not, `load_target()` raises `IOError` for a missing path so the
  `.target.gz`/`.target` fallback is genuinely exercised, and `target_full_path()` carries its
  prefix fallback. `StubShapeKey.value` is now **clamped to 0.0-1.0 on assignment**, as Blender
  clamps a real one — which is the whole reason the category level exists, and which makes a
  payload that tried to store a negative modifier value fail in the suite rather than in Blender.

- [tests/test_add_rig.py](tests/test_add_rig.py) and
  [tests/test_generate_rigify_rig.py](tests/test_generate_rigify_rig.py) — the same two layers, over
  `blender_stubs.py`'s `RigTestCase`, which holds the real `tempfile` rig tree that used to live in
  `test_list_rigs.py`. It is shared rather than copied for the same reason `rig_lookup.py` is: one
  test runs `list_rigs.py` and `add_rig.py` against the same tree and asserts their weights answers
  are equal, which only means anything if it is the same disk. The tree keeps FR 004's asymmetries
  (`default_no_toes` with no weights of its own, `weights.orphan.json` with no rig,
  `undocumented_rig` absent from the UI enum) because each is a branch. `StubHumanService` grew the
  rig half and `StubRigService` the write half, and as elsewhere every part reproduces a quirk
  rather than a convenience: the adders **raise** for an unknown rig when given no operator (a stub
  returning `None` would make the pre-checks look like belt and braces); a missing *weights* file is
  reported through an operator and otherwise **silent**, which is the path `weights_loaded` exists
  for; the armature is registered in the file *before* the Rigify colour assertion, so the stray
  object the failure leaves behind is a real one; and `generate_rigify_rig()` renames the meta rig,
  deselects everything and activates it **before** the validity gate, without which "a failed
  generation is not a no-op" could not be tested at all. Note also what these tests cannot say: that
  a rig added here matches one added through MPFB's panel, or that rigging after dressing really
  does leave the clothes unrigged — the claim the whole effort is built on.

Anything needing real MPFB is a manual integration check against a running Blender (see
[Commands](#commands)), and feature requests are expected to say so explicitly. FR 001 through
FR 006 each had that check run before being marked Done; **FR 007, FR 008 and FR 009 did not**, so
all eight character-modifying tools are unverified against real MPFB. Their verification-status
sections
([FR 007](feature-requests/done/007-macro-details/README.md#verification-status),
[FR 008](feature-requests/done/008-detail-targets/README.md#verification-status),
[FR 009](feature-requests/done/009-add-rig/README.md#verification-status)) say exactly what is
outstanding, and all three checklists want the same dressed, rigged character — so they are one
session's work rather than three. **FR 004's live verification is stale on top of that**: FR 009
migrated `payloads/list_rigs.py` onto a shared fragment, so the program sent into Blender is a
different program even though the unit tests see no behavior change. Re-running it is cheap (a
read-only call) and belongs in the same session, since FR 009's weights checks compare against its
output. Treat all of this as work owed rather than as a new precedent.

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

## Backends

There are two unrelated projects called "blender mcp"; mpfb-mcp piggybacks on blender lab's
implementation, not the more feature-rich community one some users may have installed instead.
Supporting **both** is a goal, with blender lab's remaining the reference backend — see
[specifications/vision.md](specifications/vision.md#resolved-which-blender-mcp-both) for the
resolution and the shape the second backend would take (an adapter below `send_code()`, since
the community add-on returns captured stdout rather than the exec namespace's `result` dict).
Nothing of it is implemented yet; it is listed in
[feature-requests/NEXT_STEPS.md](feature-requests/NEXT_STEPS.md#second-backend-the-community-blender-mcp).
