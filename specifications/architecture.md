# Architecture

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

This document describes **the machine**: where mpfb-mcp's boundaries are, how it reaches MPFB
without importing it, how the program that runs inside Blender is assembled, and how the package
is laid out. It exists to keep mpfb-mcp installable and runnable without a local checkout of
either MPFB or blender_mcp, and to keep it working across MPFB installs regardless of how the
extension was installed.

**What is not here.** Conventions about how a tool behaves used to live in this document and now
have their own, because they are decisions about the product rather than about its structure:

| For | See |
|-----|-----|
| What a tool accepts, and how it names an object or a catalogue entry | [tool-interface.md](tool-interface.md) |
| What a tool must say back, and what an empty answer may imply | [responses.md](responses.md) |
| How a tool that changes a character behaves | [mutating-tools.md](mutating-tools.md) |
| What to do when MPFB is inconsistent, undocumented or wrong | [mpfb-integration.md](mpfb-integration.md) |
| Where diagnostics attach, and what they may and may not do | [observability.md](observability.md) |
| How all of it is tested | [testing.md](testing.md) |

For the current, concrete module layout, see [CLAUDE.md](../CLAUDE.md#architecture).

## Readability and developer experience are prioritized

These are first-class, non-functional requirements, not a finishing touch. Where readability and
brevity or cleverness conflict, readability wins.

**Generated code is code.** The Python that mpfb-mcp builds and sends into Blender is where the
actual work happens, so it is held to the same standard as the rest of the repo: it must be
editable as ordinary Python, in its own file, with syntax highlighting, working editor
indentation and a linter that mostly applies. A payload written as an escaped string literal —
`\n` separators, doubled braces, `.format()` placeholders — fails this standard however well it
works, because it is the form the next developer copies.

**Adding a tool should mean adding files, not editing shared ones.** A structure where every new
tool edits a module that all the other tools depend on does not scale past a handful of them; see
[Code-generation layout](#code-generation-layout) for what this means concretely.

## No direct dependency on MPFB or blender_mcp

mpfb-mcp never imports MPFB or blender_mcp Python code directly, and is never run *inside*
Blender. Every interaction with MPFB crosses two boundaries:

1. mpfb-mcp → blender_mcp add-on, over blender_mcp's existing TCP socket protocol (JSON
   request + NUL-delimited response, `BLENDER_MCP_HOST`/`BLENDER_MCP_PORT`). mpfb-mcp
   maintains its own minimal client for this protocol rather than depending on blender_mcp's
   package, so it installs standalone.
2. blender_mcp add-on → MPFB, inside the Blender process, by `exec()`-ing Python source that
   mpfb-mcp generated and sent as a string.

**The consequence that shapes everything else is a testing one.** Because MPFB is reachable only
from inside Blender, mpfb-mcp's own suite can verify the wire protocol and the generated code and
nothing beyond it; anything that depends on what MPFB actually does is checked against a running
Blender by a separate, re-runnable harness. That split, and the discipline it imposes on both
halves, is [testing.md](testing.md).

## Resolving MPFB from generated code

MPFB is a Blender *extension* with no stable, guessable absolute import path — the top-level
package name depends on which extension repository the user installed it from (e.g.
`bl_ext.user_default.mpfb`, `bl_ext.repo.mpfb`). Generated code must never hardcode a guessed
path. Instead it uses the resolution mechanism MPFB itself documents and uses in its own test
suite (`mpfb2/mpfb/__init__.py`, `mpfb2/test/tests/__init__.py`): scan `sys.modules` for a
module whose name ends in `"mpfb"`, then read the classes it needs off the
`MPFB_CONTEXTUAL_INFORMATION["SERVICES"]` dict that module publishes. Every tool that needs an
MPFB service class should reuse this same bootstrap rather than inventing another resolution
strategy.

### Resolution is two steps, not one

Finding such a module says nothing about whether it is *usable*. MPFB declares
`MPFB_CONTEXTUAL_INFORMATION = None` at module level and only builds it inside `register()`,
assigning the `"SERVICES"` entry on that function's very last line; `unregister()` never resets
it. So the scan and the services check are separate questions, and generated code must treat
them separately:

1. **Is a module whose name ends in `"mpfb"` loaded?** If not, MPFB is not installed, or was
   never imported.
2. **Has that module completed `register()`?** If `MPFB_CONTEXTUAL_INFORMATION` is `None`, or is
   a dict without a `"SERVICES"` key, MPFB is installed but broken or half-registered — a state
   an unwary bootstrap surfaces as a bare `TypeError`/`KeyError`.

Two further consequences. The scan can match **more than one** module, meaning MPFB is installed
under two extension repositories (or a stale legacy addon lingers beside an extension install);
which one a bootstrap picks is then arbitrary, so any tool reporting on the install should report
all candidates rather than only the winner. And a *disabled* MPFB still passes both steps, since
`unregister()` leaves the dict populated in `sys.modules` — only
`bpy.context.preferences.addons` distinguishes it from a live one.

### Two bootstrap variants

Both are built on the same shared `sys.modules` scan, so the resolution logic exists once:

- **Raising** — for tools that cannot do their job without MPFB anyway (e.g.
  `mpfb_create_human`). Fails with a `RuntimeError` naming the likely cause, distinguishing "not
  loaded" from "loaded but not initialized", and pointing at `mpfb_get_status`.
- **Non-raising** — for tools whose job is partly *to answer* whether MPFB is present (e.g.
  `mpfb_get_status`). Classifies the situation instead of failing, so absence and partial
  initialization come back as ordinary successful answers.

### Never import MPFB submodules directly

Generated code resolves services **only** through the `SERVICES` dict. Reaching a service by
importing its module (`importlib.import_module(package + ".services.locationservice")`) is
tempting when the dict is unavailable, but several MPFB modules have import-time side effects —
`locationservice.py` ends with `LocationService = _LocationService()` followed by
`LocationService.ensure_relevant_directories_exist()`, which **creates directories on disk**.
A tool that did this to work around a missing `SERVICES` dict would be writing to disk in
exactly the state where MPFB is already broken. When the services are unavailable, report only
what is readable off the module object itself (`VERSION`, `BUILD_INFO`, `__name__`) and from
`bpy`.

### Reading module-level names MPFB does not publish

Not everything a tool needs is in the `SERVICES` dict. MPFB keeps some constants and some
entities at module level: `LOWEST_FUNCTIONAL_BLENDER_VERSION` in `systemservice.py`, the object
type vocabulary `_ALL_TYPES` / `_MESH_ASSET_TYPES` / `_SKELETON_TYPES` in `objectservice.py`, and
the `BlenderConfigSet` entities `GeneralObjectProperties` and `HumanObjectProperties`, which are
how custom properties such as `object_type`, `asset_source` and `material_source` are actually
read. These are reachable, under three rules:

- **Through a service's module, never a fresh import.** `sys.modules[SomeService.__module__]` is
  necessarily populated once that service resolved out of `SERVICES`, and reading it re-executes
  nothing — which is what keeps
  [Never import MPFB submodules directly](#never-import-mpfb-submodules-directly) intact. Pick a
  service whose module actually imports the name: `GeneralObjectProperties` is on
  `ObjectService`'s module, while `HumanObjectProperties` is not, and is on `HumanService`'s.
- **Always with a fallback.** These names are underscore-private or merely undocumented, and MPFB
  may rename them without notice. Read them with `getattr(module, name, default)` and degrade —
  a stale local copy of the type vocabulary is a better answer than a failed call.
- **Never as a substitute for a service.** If what is wanted is in `SERVICES`, take it from there.

## Code-generation layout

A generated program is assembled from three parts, in a fixed order: the shared **bootstrap**
above, a **parameter prelude**, and a per-tool **payload** — plus, optionally, one or more
**shared fragments** between the last two (see [Shared fragments](#shared-fragments)).

- **One payload file per tool**, `src/mpfbmcp/codegen/payloads/<tool>.py`, written as ordinary
  Python containing no placeholders and no escaping. This is what makes the requirement in
  [Readability and developer experience are prioritized](#readability-and-developer-experience-are-prioritized)
  concrete for generated code. A payload reads its arguments from `PARAMS` and leaves `result`
  bound.
- **Parameters are injected as data, never as source.** The prelude binds a single name from a
  JSON literal (`PARAMS = json.loads('...')`, built as `repr(json.dumps(params))`). A
  caller-supplied value is therefore parsed by `json.loads()` at run time and never by the Python
  parser, so it cannot alter the structure of the generated program — which matters in a system
  whose entire job is to `exec()` code it built. A tool taking a string argument (an asset name,
  a target name) would otherwise be an injection hole.
- **Payloads are read, never imported.** They reference `bpy` and MPFB's services, so importing
  one on the mpfb-mcp side would fail. The payload directory deliberately has no `__init__.py`,
  and payloads are loaded as package resources. Packaging has to be told this twice: declare the
  payloads as package data, or a real (non-editable) install ships a package with no payloads in
  it; *and* turn off namespace-package discovery, or the build back end picks the directory up as
  a package anyway and ships the payloads as modules rather than as data.
- **Adding a tool must not require editing a shared code-generation module.** A new tool is a new
  tool module, a new payload file, and one `register()` call. This is the objective test of the
  layout: if a change to shared code is needed to add an ordinary tool, the layout has drifted.
- **Assembly keeps failures traceable.** A traceback from inside Blender reports a line in the
  assembled string, not in a payload file, so the order of the three parts is fixed and every seam
  is marked with a comment naming the file below it. The payload seam has a second consumer: it is
  also how a call is attributed to a tool without `send_code()` taking an extra argument (see
  [Diagnostics attach at the socket boundary](observability.md#diagnostics-attach-at-the-socket-boundary-never-to-the-program)).
  Its format is consequently written by one module and parsed by another, and is pinned by tests on
  both sides rather than by convention.

### Shared fragments

A **fragment** is a fourth, optional part: an ordinary `.py` file under
`src/mpfbmcp/codegen/shared/`, named by a tool module in `assemble(..., shared=[...])` and
concatenated between the prelude and the payload. It exists for a *concept* two or more payloads
model identically. There are three: `target_categories.py` rebuilds MPFB's `target.json` category
table, which `mpfb_get_target_stack`, `mpfb_set_targets` and `mpfb_symmetrize_targets` all need in
the same shape and none of them can import; `rig_lookup.py` answers "which rig file would MPFB
load for this identifier, and whose weights would come with it", which `mpfb_list_rigs` and
`mpfb_add_rig` need to answer *identically*; and `asset_sections.py` holds MPFB's
`ASSET_LIBRARY_SECTIONS` table and what it maps between, which `mpfb_list_assets` reports *from* and
`mpfb_add_asset` resolves *with*.

- **A fragment is warranted by duplication that must not drift, not by size.** Three copies of a
  hundred-line scan of the user's target directories are three chances for two tools to disagree
  about what is installed, and that disagreement is worse than either behavior on its own. Two
  payloads sharing a five-line helper are not a reason to reach for this.
- **Where a catalogue tool predicts what an acting tool will do, the prediction and the action are
  one implementation.** This is the sharper form of the rule above, and `rig_lookup.py` is the
  case: `mpfb_list_rigs` reports, per rig, which weights file adding it would load, and
  `mpfb_add_rig` then reports which one it did load. A caller who reads the catalogue and acts on
  it is entitled to get back what the catalogue promised. The overlap is about ten lines — small
  enough that duplication would be defensible on size alone, and not defensible at all on
  consequence: MPFB resolves weights through a *fallback table*, so `default_no_toes` legitimately
  loads `default`'s weights, and two implementations that disagree about that would make an
  ordinary rig look broken in one tool and fine in the other.
- **The same rule covers a catalogue's *vocabulary*, not only its predictions.**
  `asset_sections.py` is that case, and the consequence is sharper still: `mpfb_list_assets` reports
  an asset's `object_type` and its portable `fragment`, and `mpfb_add_asset` has to map the first
  back to an asset subdir before it can resolve the second, because
  `AssetService.find_asset_absolute_path()` takes a subdir rather than a type. Two copies of that
  table disagreeing would not produce a wrong answer — it would produce "not installed" for an asset
  the catalogue had just listed, which is the one failure a caller cannot diagnose.
- **Opting in is the payload's business, not the assembler's.** `assemble()` takes the list; there
  is no table here mapping payloads to fragments. So the rule above still holds unchanged: adding
  an ordinary tool is still a tool module, a payload and a `register()` call, and a tool that wants
  a fragment names it in the same `assemble()` call it was already making.
- **Fragments come after the prelude**, so a fragment may read `PARAMS`, and before the payload, so
  the payload can simply call the fragment's functions.
- **Each fragment gets its own labelled seam**, `# --- shared: <name> ---`, for the same reason the
  payload does.
- **Packaging has to be told about the directory separately.** A package-data glob does not
  descend, so `payloads/*.py` ships nothing from a subdirectory of `payloads/` — which is why
  fragments live in a sibling directory with a glob of their own rather than under `payloads/`.

## One module per tool

Each MCP tool lives in its own module exposing a `register(mcp)` function that attaches the
tool to the passed `FastMCP` instance, following blender_mcp's own tool-module convention.
This keeps tools independently testable and keeps the server's own `main()` a flat list of
`register()` calls.
