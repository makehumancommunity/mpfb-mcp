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

## What a call costs is the size of its program

**The add-on reads one 4 KB chunk of the request per timer tick, and does nothing else with that
tick.** A generated program therefore costs about **250 ms per 4 KB** against a Blender that has
been talked to in the last five seconds, and about **1 s per 4 KB** against one that has not —
because blender_mcp drops to a one-second tick after five seconds without a request *finishing*,
and bytes arriving do not count as work. A 50 KB program costs 3 s or 12 s, and it makes no
difference at all what the program computes. Measured, and predicted to within a few percent, by
[verification/measure.py](../verification/measure.py)'s `transport_by_program_size`.

Three consequences, and they are not small:

- **"The round trip is 250 ms" is wrong**, and four decisions in this package were argued against
  it. It is one *tick*. The empty program that produced the figure was one chunk long. The
  correction does not overturn those decisions —
  [FR 013](../feature-requests/done/013-live-verification/review.md) re-derived them on the real
  numbers — but it changes what the number is a measure of.
- **The prose in generated code is not free.** It is the price of
  [Readability and developer experience are prioritized](#readability-and-developer-experience-are-prioritized),
  and that requirement stands: a payload is code the next developer reads, and the diagnostic
  record [FR 012](../feature-requests/done/012-observability/README.md) keeps is only worth keeping
  because it is legible. But the price is now known rather than assumed, and "this explanation is
  worth 250 ms on every call that carries it" is the question to ask of a paragraph in a payload.
- **Not sending something beats not doing it.** MPFB's modeling category table is the case that
  established this. It was assumed to be the package's largest avoidable cost because three tools
  rebuild it on every call; measured inside Blender, the rebuild takes **4 ms**, and the 18 KB of
  generated code that describes how to do it takes **1.1 s busy, 4.4 s idle** to arrive. The saving
  was never in the scan. See
  [Generated code may keep its own source inside Blender](#generated-code-may-keep-its-own-source-inside-blender).

**The 4 KB chunk is a defect in blender_mcp, not a law of nature.** Its `_service_clients()` reads
once per tick instead of draining the socket, and a loop there would remove most of the cost
described above from every tool in this package. It is not fixed here: blender_mcp is treated as
external and unmodified (see [No direct dependency](#no-direct-dependency-on-mpfb-or-blender_mcp)),
so the entry is
[in NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md#file-the-4-kb-chunked-read-against-blender_mcp)
to be filed upstream. Everything above holds meanwhile, and would still hold, an order of
magnitude smaller, afterwards.

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

## Supporting a second backend

There are two unrelated projects called "blender mcp", and supporting both as backends is a goal
(see [vision.md](vision.md#resolved-which-blender-mcp-both) for the decision and why). What
follows is where the seam goes, which is the architectural half of that.

The two add-ons differ in the request shape and framing (`{"type": "execute", ...,
"strict_json": bool}` with NUL delimiters, against `{"type": "execute_code", "params": {...}}`
framed by parsing until the JSON is complete), in the envelope they answer with, and — the
difference that matters — in the **result channel**: blender lab's add-on serializes the `result`
dict left in the exec namespace, while the community one discards the namespace and returns only
what the code printed to stdout.

- **The seam is an adapter *below* `send_code()`, not a second connection module each tool picks
  between.** Backend choice must not be visible above the socket boundary: tools, payloads and
  `codegen/` stay unchanged, and [Response shape](responses.md#response-shape)'s rule that a tool
  returns blender_mcp's envelope as-is holds on both. If supporting a backend requires editing a
  tool, the seam is in the wrong place — the same test
  [Diagnostics attach at the socket boundary](observability.md#diagnostics-attach-at-the-socket-boundary-never-to-the-program)
  applies to observability.
- **The adapter translates the transport and the result channel together.** On the community
  backend it wraps the assembled program so the payload's `result` is printed as JSON between
  sentinel markers, and parses it back out into blender lab's envelope shape. The markers are
  required rather than defensive: MPFB's own `LogService` prints to stdout and would otherwise
  land inside the answer.
- **Backend selection is explicit configuration, never autodetection.** Both add-ons default to
  port 9876, so the address distinguishes nothing, and no single probe distinguishes them either
  — a NUL-terminated ping leaves the community add-on's parser waiting for the rest of a message,
  while an unterminated one leaves blender lab's doing the same.
- **Two things are known to be worse on the community backend, and are accepted rather than
  solved.** `strict_json` becomes a client-side check inside the wrapper instead of an add-on
  one, and stderr is lost, since its `execute_code` redirects only stdout. Error text is
  recovered by the wrapper, which formats the traceback itself rather than accepting the bare
  `str(e)` the add-on would report.

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

### Generated code may keep its own source inside Blender

The add-on `exec()`s each request in a **fresh namespace**, so nothing a program binds survives it.
Generated code may nevertheless create a module of its own in `sys.modules` and keep things there —
and what it keeps is **the source of shared fragments, never what they computed**.

That distinction is the whole safety argument, and it is what makes the mechanism boring rather
than delicate:

- **A cache of code keyed by a hash of that code cannot be stale.** A cache of *answers* about the
  disk can, and the answer in question is the table that decides which shape key a modifier is
  written to. The fragment still runs on every call, so `mpfb_list_targets` still sees a target
  installed since Blender started — which MPFB's own panels cannot — and no tool needs a `refresh`
  argument for a cache that has nothing to go stale about.
- **It is our module, named as ours.** `mpfb_mcp_session_state`, created by the loader, holding
  nothing that is not rebuilt by sending a fragment again. Never an attribute grafted onto one of
  MPFB's modules, which is the read-only arrangement in
  [Reading module-level names MPFB does not publish](#reading-module-level-names-mpfb-does-not-publish)
  turned into a write.
- **Never on a datablock.** A scene or object custom property would reach the user's `.blend`, would
  set `bpy.data.is_dirty`, and would outlive the Blender session it describes.
- **Two servers against one Blender are safe by construction.** The key is `<file>@<hash>`, so two
  copies of a fragment are two entries; identical code shares a cache and different code never
  does, without either side knowing the other exists.
- **A fragment Blender does not hold is a request, not a failure.** The program that reuses a
  fragment is by definition not the program that carries it — carrying it is the cost being
  avoided — so the loader raises with a marker the tool side matches, and the tool re-sends with the
  source in it. Once, never twice: a second miss means the cache is not being written at all, and
  that error is more use to a caller than a loop. The handshake is visible in the record as an
  error envelope, which is honest — a call really did cross the socket and come back with nothing.
- **The source is embedded as readable Python, not as data.** A raw triple-quoted literal rather
  than a JSON string, so the program on disk in
  [FR 012](../feature-requests/done/012-observability/README.md)'s record is still something a
  developer can read, and so a traceback from inside a fragment reports that fragment's own name and
  line rather than an offset into the whole program — which is better than what concatenation gave.
  It costs two constraints on every fragment, both asserted rather than assumed: no `'''` in the
  source, and no trailing backslash.

### Shared fragments

A **fragment** is a fourth, optional part: an ordinary `.py` file under
`src/mpfbmcp/codegen/shared/`, named by a tool module in `assemble(..., shared=[...])` and
concatenated between the prelude and the payload. It exists for a *concept* two or more payloads
model identically. There are six: `target_categories.py` rebuilds MPFB's `target.json` category
table, which `mpfb_list_targets`, `mpfb_get_target_stack`, `mpfb_set_targets` and
`mpfb_symmetrize_targets` all need in the same shape and none of them can import; `rig_lookup.py` answers "which rig file would MPFB
load for this identifier, and whose weights would come with it", which `mpfb_list_rigs` and
`mpfb_add_rig` need to answer *identically*; `asset_sections.py` holds MPFB's
`ASSET_LIBRARY_SECTIONS` table and what it maps between, which `mpfb_list_assets` reports *from* and
`mpfb_add_asset` resolves *with*; `performed.py` stamps the uniform
[`performed` flag](mutating-tools.md#the-flag-a-caller-branches-on-is-called-performed) onto the
answer of every one of the eleven mutating payloads; `modifier_reading.py` computes what one
modeling category's slider reads, which `mpfb_get_target_stack` reports and
`mpfb_symmetrize_targets` acts on; and `refit_blocker.py` answers whether `HumanService.refit()`
would silently leave the rig behind, which all four refitting payloads have to know.

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
- **A convention eleven payloads must agree about is the same case as a table three must.**
  `performed.py` is the smallest fragment by far — one function, no MPFB, nothing read from the
  bootstrap — and it clears the bar on consequence rather than size, like `rig_lookup.py`: the whole
  reason the flag exists is that eleven tools disagreed about what to call it, so eleven
  implementations of it would be the original problem in a new spelling. It also has no
  dependencies, which is what lets it be concatenated ahead of any payload without pulling anything
  in with it.
- **Where two tools report and act on one number, the number has one implementation.**
  `modifier_reading.py` is that case. A modeling category's slider value is computed from one or two
  shape keys, and an opposed category's negative target reads back *negated*; `mpfb_get_target_stack`
  reports that number and `mpfb_symmetrize_targets` decides what to copy from it. Two
  implementations disagreeing would not look like a bug in either tool — it would look like a
  character that is symmetric in one and asymmetric in the other, with nothing in either answer to
  say which to believe. The reconciliation is worth noting because the two copies differed in
  *shape* and not merely in text: one answered from a snapshot read once, the other from `key_blocks`
  on every question, because it writes between readings. What is shared is the rule; the pair of
  lookups is passed in, and the difference between them is stated where it is decided.
- **A fragment may share the condition and leave the wording alone.** `refit_blocker.py` is that
  case: `HumanService.refit()` cannot refit a generated Rigify rig with no meta rig left in the
  scene, reports it only through an `operator` no MCP tool has one of, and returns having refitted
  the mesh assets. Four payloads must detect that or claim a refit they did not perform — but
  `mpfb_refit_human` reports one that has already happened and the other three predict one they are
  about to attempt, so the sentences differ by tense and both are right for their call site. The
  fragment therefore exposes a predicate and each payload keeps a `rig_refit_blocker()` of its own
  that phrases the answer. Four copies of the condition is the `rig_lookup.py` failure exactly; four
  copies of the message is at worst four sentences that read slightly differently.
- **Being identical is not by itself a reason to merge.** A census of every function defined at
  module level in more than one payload — docstrings stripped, normalised through `ast.unparse` —
  found nineteen such names, of which sixteen were byte-identical and had not drifted at all. Only
  the two above were made into fragments. `blocked()`'s six variants were left alone deliberately:
  they are one convention applied six times, differing only in which of that tool's own fields each
  nulls out, and a mechanism for "this tool's null response" would be larger than the six copies.
  The census is kept as [verification/census.py](../verification/census.py) so that the question
  "have these drifted?" stays a command rather than an afternoon; it also reports a payload that
  redefines a name from a fragment *it names*, which is a real defect, since the fragment is
  concatenated first and its copy would be silently dead.
- **Opting in is the payload's business, not the assembler's.** `assemble()` takes the list — as
  does `shared_cache.send()`, which is `assemble()` plus the decision about carrying the source —
  and there is no table anywhere mapping payloads to fragments. So the rule above still holds
  unchanged: adding an ordinary tool is still a tool module, a payload and a `register()` call, and
  a tool that wants a fragment names it in the call it was already making.
- **Fragments come after the prelude**, so a fragment may read `PARAMS`, and before the payload, so
  the payload can simply call the fragment's functions.
- **A fragment may be sent once per Blender session rather than once per call**, and which of the
  two a given call does is the tool's business rather than the fragment's: the file is identical
  either way, it is executed into the program's own globals either way, and a payload cannot tell
  the difference. What decides it is a memo of what this process has already sent to this address —
  see [Generated code may keep its own source inside Blender](#generated-code-may-keep-its-own-source-inside-blender)
  for why, and for what makes it safe.
- **Each fragment gets its own labelled seam**, `# --- shared: <name> ---` or
  `# --- cached shared: <name>@<hash> (carried|reused) ---`, for the same reason the payload does —
  and the second form additionally says, in the record, which of the two this call paid for.
- **Packaging has to be told about the directory separately.** A package-data glob does not
  descend, so `payloads/*.py` ships nothing from a subdirectory of `payloads/` — which is why
  fragments live in a sibling directory with a glob of their own rather than under `payloads/`.

## One module per tool

Each MCP tool lives in its own module exposing a `register(mcp)` function that attaches the
tool to the passed `FastMCP` instance, following blender_mcp's own tool-module convention.
This keeps tools independently testable and keeps the server's own `main()` a flat list of
`register()` calls.
