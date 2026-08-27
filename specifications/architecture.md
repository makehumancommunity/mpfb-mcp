# Architecture

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents). For the
> current, concrete module layout, see [CLAUDE.md](../CLAUDE.md)'s Architecture section.

These are the standing architectural principles new tools are expected to follow. They exist
to keep mpfb-mcp installable and runnable without a local checkout of either MPFB or
blender_mcp, and to keep it working across MPFB installs regardless of how the extension was
installed.

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

## Code-generation layout

A generated program is assembled from three parts, in a fixed order: the shared **bootstrap**
above, a **parameter prelude**, and a per-tool **payload**.

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
  assembled string, not in a payload file, so the order of the three parts is fixed and the seam
  is marked with a comment naming the payload.

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
