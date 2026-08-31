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

## Diagnostics attach at the socket boundary, never to the program

Every tool assembles a program, hands it to `send_code()` and returns the envelope. That single
function is therefore the only place diagnostics belong, and the rule is worth stating as a
constraint rather than as a preference: **if observing a call requires editing a tool module, a
payload or `codegen/`, the design is wrong.** Twenty tools crossing one function is what makes a
per-call record a change in one file; it is also what stops "which tool called this" needing an
extra argument, since [Code-generation layout](#code-generation-layout)'s seam marker already
names the payload.

- **The generated program is never altered in order to observe it.** A diagnostic setting that
  changed the source would make "the exact program that ran" conditional on configuration, which is
  the one property the record exists to provide — a traceback's line number has nothing else to be
  resolved against. Decomposing a round trip into transport, `exec`/compile and MPFB's own work is
  therefore *not* done this way; a payload can print its own timings into the envelope's `stdout`
  during a session that wants them.
- **mpfb-mcp's own settings carry an `MPFB_MCP_` prefix.** `BLENDER_MCP_HOST` / `BLENDER_MCP_PORT`
  are shared with blender_mcp deliberately, because both processes address the same add-on and have
  to agree; anything blender_mcp knows nothing about is mpfb-mcp's own and is named accordingly.
  Keeping the two apart is also what lets `connection.py` go on describing itself as a faithful
  duplicate of blender_mcp's protocol: the additions are around the protocol, not in it.
- **Off means unchanged.** A diagnostic that is not enabled creates no directory, opens no file,
  formats nothing and puts the same bytes on the wire. An MCP server writing files nobody asked
  for, into a location nobody chose, is a surprise; and the disabled path is the one the whole test
  suite exercises, so a regression there is a regression in every tool at once.
- **A diagnostic never fails a call.** An unwritable directory, a full disk or a value that will
  not serialize produces one warning and is otherwise swallowed. A read-only tool that raises
  because a diagnostic directory was not writable is strictly worse than a tool with no
  diagnostics.
- **Stdout belongs to the transport.** The server runs `mcp.run(transport="stdio")`, so stdout *is*
  the JSON-RPC channel. A `print()` left in while debugging, or a `logging.StreamHandler()` at its
  default stream, corrupts the protocol and does not fail loudly — it surfaces as a client that
  hangs, drops the connection or reports a parse error nowhere near the cause. Every handler this
  package attaches names `stderr` or a file explicitly. Note also that the host has already
  configured logging by the time a tool runs: `FastMCP()` calls `logging.basicConfig()`, so the
  root logger is at `INFO` with a handler on it, which is why anything this package emits per call
  is gated on its own setting rather than on an ambient level.
- **What the record contains is diagnostic output about the user's machine** — absolute paths from
  their install, their asset library layout, the MHMAT and MHCLO files they have, the parameters of
  the character they are building. There are no credentials anywhere in this system, so no
  scrubbing is done, and that absence is a decision rather than an oversight. What follows from it:
  say so in the documentation, and never default such a directory to somewhere inside the
  repository.
- **The caller-visible surface stays narrow.** [Response shape](#response-shape) says tools return
  blender_mcp's envelope as-is. A diagnostic may add to an *error* envelope, and only while the
  record that produced the information is enabled — because whoever reads a failure is usually an
  agent rather than the person who configured the record, and a failure that does not say where its
  own evidence landed wastes it. A success envelope is untouched in every configuration.

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
  [Diagnostics attach at the socket boundary](#diagnostics-attach-at-the-socket-boundary-never-to-the-program)).
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

## Validate before crossing the socket

Where a tool takes structured input (e.g. macro-detail sliders, which are only meaningful in
`0.0`-`1.0`), validate it in the tool function *before* generating and sending code. A bad
call should fail fast and locally, not round-trip to Blender to fail there.

The same holds for the *shape* of a string argument: reject a non-string, or an empty or
whitespace-only one, and never quietly treat an explicitly empty value as an omitted one, since
the two arise from different mistakes. But validate only the shape, never the **vocabulary**. A
list of valid MPFB type names, asset names or target names kept on this side of the socket would
drift silently from MPFB's own. Send the value across instead and let the generated code answer
authoritatively, reporting alongside the result both whether the value was recognized and what the
valid values actually are — so a caller can correct itself from the same response rather than
needing a second tool or a hardcoded list.

There is exactly one exception, and it is narrow: a vocabulary that is small, closed, MPFB's own
enum rather than anything derived from the user's disk, **and** validated by MPFB only after it has
destroyed something. `mpfb_set_skin`'s `skin_type` is the only current case; see
[Preconditions are answers](#preconditions-are-answers) for why. Even there the authoritative check
stays in the payload and the response still reports `known_skin_types`; the local check only means
a typo never travels.

**Structured input is taken as flat scalar arguments, not as a nested dict.** `mpfb_create_human`
takes eleven separate macro sliders rather than the `macro_detail_dict` MPFB's own
`create_human()` wants, and `mpfb_set_macro_details` takes the same eleven names. That is
deliberate and general: a flat scalar is what an MCP tool schema describes and validates well, and
what a client fills in reliably, while a nested dict-of-dicts is a shape an LLM gets subtly wrong —
misspelling a container key, omitting one, nesting a field under the wrong parent — and it pushes
per-field validation into a hand-written dict walk that no schema checks. Flat arguments also
express something a dict cannot without a sentinel: on a mutating tool, an *omitted* argument means
"leave this alone", which is what makes a relative change ("a bit older") a single call.

Round-tripping is preserved on the **output** side instead: a tool returns the nested dict in
MPFB's own shape, so a caller can read a character, hand the dict elsewhere, and map it back onto
flat arguments mechanically. Assemble MPFB's structure in the tool function, from the flat
arguments, immediately before generating code.

**The one exception is a batch, which is irreducibly a list.** `mpfb_set_targets` takes
`modifiers` and `targets` as lists of dicts, because the alternative to a batch is thirty round
trips (see [A batched mutating tool resolves before it writes](#a-batched-mutating-tool-resolves-before-it-writes)),
and a list of one repeated shape is not the dict-of-dicts the clause above rules out. What the
clause is really protecting against — a shape no schema checks — still applies, so a batch carries
two compensations:

- **Validate every entry's shape here, entry by entry, and name the position that failed.** That an
  entry is an object, that its keys are all known — a misspelled key is the commonest way a caller
  gets a dict-shaped argument wrong, and it is silent unless checked — that a value is a real number
  in range, that an enumerated string is one of its values. `modifiers[1] has unknown key(s)
  catagory` is a message a caller can act on; a silently ignored key is not.
- **Give the response a per-entry error channel**, so the half of the validation that can only
  happen inside Blender comes back the same way: which entry, why, and what the valid values were.

## How generated code addresses objects

Tools name a Blender object by its **Blender object name**. Names are unique across the whole
`.blend`, which is what makes them a usable address, but that has consequences a tool must not
paper over:

- **Listing is scoped to the current scene** (`bpy.context.scene.objects`), so results match what
  the user is looking at, while **resolution is scoped to the file** (`bpy.data.objects`). A name
  can therefore resolve to an object that a listing did not mention. Report that as a distinct
  answer — an `in_current_scene` flag — rather than as "not found", which would be false, or
  silently, which would make two tools look as if they contradict each other.
- **Every object in a response carries that flag, not only the subject.** MPFB's relationship walk
  reaches relatives through `ObjectService.get_list_of_children()`, which iterates
  `bpy.data.objects`, and several of its Rigify helpers do the same. A relative can sit outside the
  current scene, and filtering it out would silently drop a real relationship.
- **A subject may also be "whatever is active"**, read as `bpy.context.view_layer.objects.active`
  rather than `bpy.context.active_object`: generated code runs in the add-on's execution context,
  not from a viewport operator, and the view-layer form does not depend on which UI area happens to
  be current. It is `None` whenever nothing is active, which is an ordinary answer rather than a
  failure. A response should say which way its subject was resolved, because the two have very
  different lifetimes: a name stays valid until the object is renamed or deleted, while an
  active-object answer is stale the moment the user clicks elsewhere.

Object addresses are never cacheable. Unlike `mpfb_get_status`'s output they are things later
mutating tools will act on, so a stale one is worse than a missing one.

## How tools report the asset behind an object

MPFB records what an object was made from as a short *fragment* — `"fedora/fedora.mhclo"`, one
directory level plus a filename — which is resolved to a file by walking the configured asset
roots. Any tool reporting that follows three conventions:

- **Report the fragment and the resolved path as separate fields**, and make every `*_path` either
  an absolute path or `null`, never a fragment. A fragment looks path-shaped, and a caller that
  hands one to a file-opening tool gets a confusing failure far from here.
- **Keeping both is also what tells two situations apart.** A `null` fragment means the object
  records no such asset: it was built rather than imported, or it is using a default. A fragment
  with a `null` path means the asset *is* recorded but is not installed under any asset root this
  Blender can see — the user moved or uninstalled the pack. The first is ordinary; the second is
  something a caller may want to raise with the user, and one undifferentiated `null` would hide it.
- **Let the keys vary by object type rather than unioning them and nulling what does not apply.**
  `mhclo_path: null` on a skeleton reads as "we looked for its mhclo and failed", a different and
  much more alarming claim than "a skeleton does not have one". The keys present say which question
  was asked; their values say whether it could be answered.

Two cautions belong in the docstring of any tool reporting these. Values *identified* from the
object as it is now — which rig the bone names look like, which material the node tree looks like —
can disagree with values *recorded* when something was loaded, because nothing rewrites a record
when the object is later edited by hand; where they disagree, the identified value describes
reality, and both are heuristics rather than authorities. And resolving a fragment is an `os.walk`
of the asset roots, so it must happen only when there is a fragment to resolve.

## How tools name things that can be added

[How tools report the asset behind an object](#how-tools-report-the-asset-behind-an-object) covers
naming something that already exists. A *catalogue* tool — one listing what could be added, such as
`mpfb_list_rigs` — has the parallel problem, and it is not solved by reporting a name:

- **Report the exact identifier the acting tool will need**, as its own field, never a display name
  or a filename the caller must transform. A rig is *called* `human` and *added* as
  `rigify.human`; a custom one is added as `custom.my_rig`. Any part of that string the caller has
  to assemble is a part they can assemble wrongly, and reassembling it is precisely the guesswork a
  catalogue exists to remove. The sharpest case is `mpfb_list_targets`' `shapekey_name`, which
  equals the target's filename for most targets and, above 60 characters, does not — and addressing
  a target by the wrong one of the two does not fail, it reads back `0.0`. Where an identifier
  *usually* equals something the caller already has, report it anyway: the exceptions are exactly
  where a caller would not think to look.
- **An entry may need more than one identifier, and the portable one is not always the one the
  function takes.** `HumanService.add_mhclo_asset()` takes an absolute *path*, while the value MPFB
  records on the resulting object, and the one that survives a move to another machine, is the
  *fragment*. Report both, and say which is which: a catalogue whose identifier cannot be stored is
  as awkward as one whose identifier cannot be passed. The same entry can also carry a second
  identifier hiding as a description — that function's `asset_type` argument takes exactly the
  `object_type` string the catalogue reports, and defaults to `"Clothes"`, so hair added without it
  becomes clothes.
- **Say which function consumes it, when there is more than one.** `HumanService` adds rigs through
  `add_builtin_rig()` and `add_custom_rig()`, and they are not interchangeable. Crossing them does
  not fail legibly: `add_builtin_rig("custom.my_rig")` looks for a file called
  `rig.custom.my_rig.json`, while `add_custom_rig()` strips the first seven characters of whatever
  it is given as though they were a `custom.` prefix, so a built-in name comes back missing under a
  mangled one. A later acting tool has to dispatch on this, and a caller reading the response should
  be able to see why.
- **Report what acting on the entry would do, where that is not implied by the entry.** A rig with
  no weights produces an unweighted character, and MPFB resolves weights through a fallback table
  rather than by filename — so an entry whose weights come from a *different* rig is normal, and one
  with no weights at all is not. Mirror the acting function's own resolution rather than guessing
  from filenames, and report the outcome.
- **An absent entry must be explainable.** Report the directories that were actually scanned (not
  every configured data root — MPFB does not look in all of them for everything), anything a scan
  silently refused, and any precondition that makes a whole family unusable. This is the same
  quality attribute as `mpfb_list_objects`' `type_recognized`: an agent that reads a short list as
  the whole truth will conclude rather than investigate.
- **A catalogue vocabulary and an identification vocabulary are not the same set**, even when they
  overlap. `RigService.identify_rig()` reports `rigify_generated.*` and `unknown`, neither of which
  names anything addable. Where a tool's values overlap another tool's without matching them, the
  docstring must say so, or a caller will read a legitimate miss as a failure.

## An acting tool accepts every identifier its catalogue reports

[How tools name things that can be added](#how-tools-name-things-that-can-be-added) requires a
catalogue to report more than one identifier per entry, because the passable one and the portable
one are not the same string. The obligation on the *acting* tool is the other half of that: **it
takes them all, requires exactly one, and reports which one resolved and to what.**

- **Taking only one of them makes the other half of every catalogue entry decorative.**
  `mpfb_add_asset` accepts the absolute `path` and the `fragment` alike. A tool that took only the
  path would make a stored character description — which is what a fragment is *for*, since it
  survives a move to another machine — unusable without a lookup step the caller has to invent. One
  that took only the fragment would pay an `os.walk` of the asset roots on every call, including the
  calls where the caller already had the file.
- **Exactly one, never both, and never neither.** They can name different files. Silently preferring
  one would attach an asset the caller did not ask for, and there is no reading of "both" that is
  more likely to be right than refusing. An exception to "never neither" needs a reason of its own,
  not a relaxation of the rule: `mpfb_set_skin` accepts neither identifier when — and only when —
  `skin_type` is `LAYERED`, which is the single skin type that has a material to build from no file
  at all. "Neither" is a meaningful request there and a mistake everywhere else, so it is refused
  everywhere else.
- **Report the resolution, because it is lossy.** `find_asset_absolute_path()` matches on the
  fragment's *basename*, prefers a candidate whose parent directory also matches, and otherwise
  returns the first hit — so two packs shipping `hat.mhclo` resolve to a coin toss. `resolved_path`
  is always in the response, beside a `resolved_by` saying which identifier was used. This is the
  acting-tool counterpart of `mpfb_list_assets`' `pack_ambiguous`: the derivation is unsafe in a
  minority of cases, and the caller cannot tell which case they are in unless the tool says.
- **An identifier hiding as a description is still an identifier.** `add_mhclo_asset()`'s
  `asset_type` takes exactly the `object_type` the catalogue reports, and defaults to `"Clothes"` —
  so hair added without it *becomes* clothes, permanently and silently. Where a defaulted argument
  changes what the character *is*, the tool requires it rather than inheriting the default, and says
  in its docstring that it diverges from MPFB's own signature for that reason.

## Where MPFB's UI coerces or re-defaults a service argument, mpfb-mcp does the same and reports both

A service signature's default is not always the product's default, and a service's argument is not
always the one the product would have passed. `HumanService.set_character_skin()` defaults
`skin_type` to `ENHANCED_SSS`, while the settings panel every user actually sees defaults it to
`MAKESKIN`; and it accepts `material_instances=True` for a `MAKESKIN` skin, while
`loadlibraryskin.py` forces that flag to `False` for `MAKESKIN`, `LAYERED` and `GAMEENGINE` alike —
a coercion the service's own guard makes for only two of the three.

Passing the signature's value in either case would produce a character that **cannot be reproduced
through MPFB's own UI**, which is the same quality bar
[FR 007](../feature-requests/done/007-macro-details/README.md) sets for macro details: the goal is
that the value reads back on MPFB's own slider.

- **Follow the UI, not the signature.** The panel is what the user saw and what a character loaded
  from a `.mhm` was made with. A signature default is an implementation detail of one function.
- **Say so in the docstring, naming both values.** "Defaults to `MAKESKIN`, which is MPFB's settings
  panel's default rather than the function's `ENHANCED_SSS`" is checkable; a bare default is not.
- **Report `*_requested` beside `*_used`, with a sentence when they differ.** A silent coercion is
  indistinguishable from a bug: a caller who asks for material instances, gets none, and is told
  nothing will conclude the tool is broken. `mpfb_set_skin` returns
  `material_instances_requested` and `material_instances_used` on every call, not only when they
  disagree — for the same reason
  [A mutating tool reports before and after](#a-mutating-tool-reports-before-and-after) reports a
  field the caller named even when it was already so.
- **The coercion belongs in the payload, not in the stub.** The test has to be testing mpfb-mcp. A
  stub service that coerced would let the payload do nothing and still pass.
- **This is not the same as picking between code paths.**
  [Where MPFB's own code paths disagree](#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)
  is about two implementations of an operation; this is about one implementation whose *arguments*
  the UI fills in differently from its signature. The remedy is different too: there, name the path
  you took; here, apply the coercion and report both values.

## Where MPFB's own code paths disagree, mpfb-mcp picks one and names it

Sometimes there is no single MPFB implementation to wrap. Adding a topology proxy has three:
`HumanService.add_mhclo_asset()` imports and fits it and stops there;
`HumanService._check_add_proxy()` calls that and then hides the basemesh, copies the scale factor,
creates the proxy's extra vertex groups and runs a corrective pass; and the asset library's proxy
operator does not call `add_mhclo_asset()` at all and carries a third variant gated on its own scene
settings. Nothing documents which is canonical, and the three produce visibly different characters.

This is the sharper, more general form of
[When mpfb-mcp models a concept MPFB's UI has but its services do not](#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not),
whose last clause — document the divergence rather than normalizing it away — extends here from "UI
versus services" to *any* two MPFB code paths.

- **Follow the service-layer path.** It is what `deserialize_from_mhm()` uses, so it is what a
  caller comparing against a loaded `.mhm` will expect, and it is what other services are written
  against. A UI operator's variant is the behavior of one panel, not of MPFB.
- **Say which one in the docstring, and name the one you did not take.** "This matches `.mhm`
  loading rather than the proxy library panel" is something a caller can check; silence is not.
- **Report the parts that differ, individually.** `proxy_extras` names each of the four things
  `_check_add_proxy()` does beyond the plain add, so a caller who sees a difference against MPFB's
  panel can see exactly where it comes from.
- **Record the divergence as a candidate mpfb2 issue.** Three implementations of one operation is a
  problem in MPFB that mpfb-mcp is working around, not a fact about mpfb-mcp.
- **Do not merge them.** Picking one and naming it is the rule; synthesizing a fourth behavior that
  matches none of MPFB's own would make the result unreproducible from inside Blender.
- **The limiting case is no service path at all.** Setting an alternative material on an equipped
  asset exists only in `ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py`, as two
  module-level helpers. There is nothing to prefer, so the panel's behavior *is* the specification,
  and it is reimplemented from services rather than imported — quirks included, because every quirk
  is a way the result would otherwise differ from what the user gets from the panel. Three of them
  are reproduced deliberately in `mpfb_set_asset_material`: the replacement is always a MakeSkin
  material under the fixed name `makeskinmaterial`, whatever the asset had before; the slots are
  *popped* rather than deleted, so the previous material's node groups survive (unlike the skin
  path, which destroys them); and the viewport colour is keyed on the object's recorded
  `object_type`, so an asset mislabelled at equip time gets the wrong colour here too. Reproduce
  them, and say in the payload docstring that they are reproductions rather than choices.

## How tools bound a large answer

Some answers do not fit. `mpfb_list_assets` reports an asset library that runs to hundreds or
thousands of entries on an ordinary install, and an unfiltered listing is not something an agent can
afford to read. Such a tool caps its answer, and the cap brings one obligation: **a capped or
filtered response must never be readable as a complete one.**

- **Always report the size of the matched set, not only the page.** A `total_count` counted before
  the cap is applied, and a `truncated` flag that is **always present** — not omitted when false,
  since a caller that has to infer the field's absence will not.
- **Echo the paging back.** `offset` and `limit` in the response, so the next page can be asked for
  without the caller tracking state it did not send.
- **Order deterministically before paging.** The underlying listing usually comes from a directory
  walk, whose order is filesystem-dependent. Sorting after paging, or not at all, makes two pages of
  one query silently skip and repeat entries.
- **A filtered call still reports what it filtered out of.** `counts_by_subdir` is what turns an
  over-broad call from merely truncated into informative: it says where the entries are, so the
  caller can pick a narrower filter for the next call rather than paging blindly through everything.
- **Say in the docstring which field to check before concluding something is absent.** The failure
  this whole convention guards against is an agent reporting that an asset is not installed because
  it was not on page one.

## How tools report a derived rather than recorded fact

[How tools report the asset behind an object](#how-tools-report-the-asset-behind-an-object) draws a
line between values *identified* from an object as it is now and values *recorded* when it was
loaded. A third kind turns up in catalogue tools: a value **derived from a convention**, where
neither MPFB nor the file records the fact at all. `mpfb_list_assets`' `pack` is one — MPFB stores
no link from an installed file back to the pack that installed it, so the attribution is a match of
the asset's containing directory name against the asset names in the installed packs' metadata.

- **Say in the docstring that it is derived, and from what.** A field that looks recorded will be
  quoted back to the user as fact.
- **Give the caller a way to see when the derivation is unsafe**, rather than only documenting that
  it might be. `pack_ambiguous` is that: when two packs claim a name, the reported one is a coin
  toss, and without the flag a wrong attribution is indistinguishable from a right one. Measured on
  a real install, 9% of assets are ambiguous — "rare" is not a safe assumption about a convention.
- **Report the miss as ordinary.** A derivation that finds nothing (`pack: null` for a
  hand-installed asset) is not a failure and must not be reported as one.
- **Never let the derivation become the source of truth.** Filter and count the things actually
  found, then derive; do not answer from the metadata the derivation reads. Pack metadata lists
  assets a user may since have deleted, and building the response from it would report assets that
  are not installed.
- **Know where the convention does not hold.** The join above keys on a containing directory, so an
  asset lying directly in an asset root has no directory of its own to key on, and pack metadata
  lives only under the user data root, so an asset under another root cannot be attributed even when
  it did come from a pack. Both are cases to detect and report as `null`, not cases to guess at.

## Reading MPFB's data files directly

Not everything a tool needs is behind a service. `mpfb_list_targets` reports `target.json`, the
bundled index of modeling targets, which MPFB has no accessor for at all — its own consumers build
the path and `json.load()` it. Where a tool has to read a bundled data file, three rules:

- **Locate it through `LocationService`, never by assembling a path from a module's location.**
  `get_mpfb_data("targets")` is the only thing that knows where an extension install put its data;
  a path derived from `__file__` or from the package name is a guess that breaks on the next
  install method.
- **Guard the read, and treat a missing or unparsable file as an answer.** A broken install is one
  of the things a tool is for reporting, so it comes back as `target_json_exists: false` plus an
  explanatory message and whatever else the tool could still gather — not as a failed call. This is
  the same rule as `mpfb_get_status`' three-state classification, applied to a file.
- **Report where it is rather than what is in it, when it is large.** `target.json` is ~140 KB, far
  more than a response should carry, and a client sharing a filesystem with Blender can parse it
  itself. Reporting the path, an overview, and a way to page through the contents is strictly more
  useful than truncating the file.

## A tool may report a fact MPFB's own UI does not show

Where a tool's answer can legitimately disagree with what the user sees in Blender, **the docstring
must say so**, or the discrepancy will be read as the tool being wrong. Two of these turn up in
`mpfb_list_targets`, and both are worth reporting rather than suppressing:

- **The tool is more current than MPFB.** MPFB's modeling panels build their target list at *module
  import time*, so they only ever show what existed when Blender started. A tool that scans per call
  reports a target installed since — which is correct, and is a difference the user will notice.
- **The tool is less selective than MPFB.** MPFB's scan of `<user data>/targets/` matches only
  `*.target`, so a `*.target.gz` sitting there is on disk and loadable but absent from its panels.
  Report it, with a field saying which ones MPFB will show. Silently matching MPFB's narrower
  behavior would hide a real file; reporting it without the flag would look like a bug here.

A third turns up in `mpfb_get_target_stack`, and it is the sharpest of them:

- **The tool can see something MPFB cannot address at all.** `TargetService.get_target_stack()`
  excludes any shape key whose lowercased name *contains* `"basis"`, not merely equals it, so a
  user target called `basis-nose-widen` is on the mesh, is deforming it, and is invisible to
  `has_target()`, `get_target_value()` and every write MPFB can perform. The read tool goes to
  `key_blocks` directly rather than inheriting the blind spot, and flags what it found with
  `visible_to_targetservice: false`. Every **write** still goes through `TargetService`, or the
  read and write halves of the same tool would disagree about what exists.

And the same convention has a fourth form, seen from the other side:

- **The tool can be the stale one, and must say so.**
  `AssetService.alternative_materials_for_asset()` caches its scan per `(asset_source,
  asset_subdir)` in a module-level dict with no invalidation, so `mpfb_list_asset_materials` reports
  a snapshot taken the first time anything in that Blender session asked about the asset. A material
  installed afterwards is on disk, is applicable, and will not appear — and no `refresh` argument
  could change that, because there is nothing to call. Where the staleness is *ours* rather than
  MPFB's, the obligation is the same: name it in the docstring and in the response, so a caller who
  meets it does not read it as a bug.

Prefer describing what is actually on disk, and label the part MPFB will not show — rather than
either papering over the difference or quietly inheriting the limitation. Where the difference is
a limitation of MPFB rather than of the tool, that is worth recording as a candidate mpfb2 issue
as well as reporting.

## How a mutating tool takes its subject

A tool that changes a character accepts **any object in that character's family** — the basemesh,
its rig, a garment fitted to it — and resolves from there to the object it will actually modify,
through `ObjectService.find_object_of_type_amongst_nearest_relatives()`. That is the same call
MPFB's own panels make, and the reason for it is
[how tools name things](#how-generated-code-addresses-objects): an agent got the name it is holding
out of `mpfb_list_objects`, which does not say which member of a family owns a given property.
Requiring the caller to know that would make every mutating tool need a lookup step first.

- **The response names the object that was modified, not the argument.** `basemesh_name` beside
  `subject_name`, so a caller that passed a rig can see what the change actually landed on.
- **The walk is MPFB's, not a reimplementation.** It descends through children, ascends through
  parents, and takes each parent's other branches on the way — which is what finds a garment from
  the basemesh on a rigged character, since MPFB parents garments to the *rig*.
- **The object resolved to is not always the basemesh.** It is for every phenotype and modeling
  tool, and for `mpfb_add_rig`, because that is what carries what they change. It is not for
  `mpfb_generate_rigify_rig`, which narrows to the character's `Skeleton` and then asks
  `RigService.identify_rig()` which kind it found — the meta rig is the thing being operated on.
  Resolve to whatever owns the change, name it in the response (`metarig_name` rather than
  `basemesh_name` there), and take the subject from anywhere in the family either way.
- **A narrowing step can need the whole set rather than the first match.**
  `find_object_of_type_amongst_nearest_relatives()` returns one object; where two objects of the
  same MPFB type mean different things, take them all and classify. After Rigify generation a
  character's `Skeleton` relative is the *generated* rig, since `adjust_children_for_rigify()`
  re-parents the character onto it — so "already generated" and "that is not a meta rig" are
  different answers that a single lookup could not tell apart.
- **Failing to resolve is an answer**, `found: false` with a sentence, exactly as for the read-only
  tools.

## A mutating tool reports before and after

The mutation-side counterpart of "an empty answer must never be ambiguous": a tool that changes
something and reports only that it succeeded has told the caller very little, and a tool that
changes something with side effects and mentions none of them has told the caller something false
by omission.

- **Report the prior value beside the new one**, per changed field, so the change is verifiable
  without a second round trip — and report a field the caller named even when the value it already
  had was the one requested. "You asked for this and it was already so" is not the same claim as
  not mentioning it.
- **Report what changed as a consequence**, not only what was asked for. `mpfb_set_macro_details`
  returns the macro shape keys before and after, and the removed and added lists, because pruning
  deletes shape keys the caller never mentioned and would otherwise see vanish unexplained.
- **Report what is now stale.** Changing a body's shape invalidates the fit of everything on it,
  and MPFB's own auto-refit defaults to off. So the tool reports `refit_performed`, and when it is
  false, what is left needing attention (`assets_possibly_stale`) and which tool addresses it. An
  expensive default left off is defensible only when the response says what it left undone.
- **Do only what was asked.** A call that names nothing to change must not "helpfully" recalculate:
  it answers immediately, saying that nothing was named. A no-op is a common agent mistake, and a
  full macro rebuild costs seconds.
- **Restore what was borrowed.** Where the payload has to activate or select an object to do its
  work — MPFB's own slider callback does — put the previous active object and selection back, in a
  `finally`, so a failure part-way through does not leave the user's scene rearranged. Where it
  genuinely *cannot* — `RigService.generate_rigify_rig()`'s own final act is to select and activate
  the rig it produced, so there is no state left to restore to — say what the selection now is
  (`active_object_after`) rather than quietly leaving the caller to assume nothing moved.

## Preconditions are answers

Related to, but distinct from, [FR 001](../feature-requests/done/001-mpfb-get-status/README.md)'s
"absence is an answer": there the request named something that is not there, while here the request
is well-formed and the **world** is not ready. Check in the payload and return a sentence naming the
problem, rather than letting MPFB's own guard surface as a traceback in an error envelope.

- **OBJECT mode.** `TargetService.create_shape_key()` opens with a bare `assert
  blender_object.mode == "OBJECT"`, reached whenever a macro target has to be loaded. An
  `AssertionError` with no message is the worst possible form of a very ordinary situation: the
  user left the mesh in edit mode.
- **Presence of shape keys.** `reapply_macro_details()` on a mesh with none logs "somewhat
  surprising" and carries on, producing a partial result. It is what an imported mesh tagged as a
  basemesh looks like, and it should be reported as that rather than half-done.
- **Reachability of what the payload needs**, such as a property set read off a service's module
  (see [Reading module-level names MPFB does not publish](#reading-module-level-names-mpfb-does-not-publish)).
- **A vocabulary MPFB validates *after* it destroys something.** This is the sharpest case, and it
  is the one exception to
  [validate the shape, never the vocabulary](#validate-before-crossing-the-socket).
  `HumanService.set_character_skin()` opens with
  `MaterialService.delete_all_materials(..., also_destroy_groups=True)` on the basemesh and the body
  proxy, and only then tests its five skin types — with five separate `if` statements rather than a
  chain with an `else`. An unrecognised value therefore deletes the character's materials, builds
  nothing, and surfaces as a `ValueError` raised from `create_and_assign_material_slots()` about a
  mesh with no materials: a traceback from a function that never saw the bad argument, after damage
  that cannot be undone across the socket. Where a vocabulary is checked late and the check is
  preceded by destruction, check it in the payload first — and, where the vocabulary is small,
  closed and MPFB's own enum rather than a scan of the user's disk, check it in the tool module too,
  so a typo never crosses the socket at all. Report `known_*` alongside either way: the local check
  is belt and braces, and the authoritative answer still comes from Blender.

Report which precondition blocked (`ready: false` plus a `blocked_by` naming it) rather than only a
sentence, so a caller can branch on it; and make sure the tool changed nothing on the way to
finding out.

## A tool reports an ordering constraint it cannot enforce

MPFB's services have **implicit sequencing**, and violating it produces no error anywhere. The rig
has to be added before the mesh assets, because `HumanService.add_mhclo_asset()` rigs a garment only
if a `Skeleton` relative exists at the moment the garment is attached and nothing re-rigs it
afterwards — `HumanService.refit()` deliberately passes `set_parent=False`. Rigify generation has to
come after the mesh assets, because `RigifyHelpers.adjust_children_for_rigify()` handles exactly
what is on the character when it runs. MPFB's own character builder documents both in comments, and
its randomizer follows them; nothing enforces them. An agent that dresses a character and then rigs
it gets clothes that do not follow the armature, and finds out when someone moves a bone.

No single call can validate a sequence. But a tool can often *observe* that the caller is about to
break one, and where it can, **it reports the observation in its response, naming the objects
affected** — rather than either failing or staying silent.

- **Report, do not refuse.** Rigging an already-dressed character is a legitimate thing to do when
  the clothes are decorative. `mpfb_add_rig` adds the rig and returns `mesh_assets_not_rigged`
  listing what it has just failed to rig; it does not second-guess the caller.
- **Name the objects, not the rule.** "Some assets may not be rigged" is advice; `["Shirt",
  "Shoes"]` is something an agent can act on. This is the sequencing counterpart of
  [an empty answer must never be ambiguous](#how-tools-report-the-asset-behind-an-object).
- **Observe before acting, so the claim is precise.** The assets are enumerated *before* the rig is
  added. Afterwards they are still reachable, but the answer would then be "assets on this
  character" rather than "assets that were attached while there was no rig".
- **A half-finished sequence must look half-finished.** `mpfb_add_rig` on a `rigify.*` identifier
  produces only a meta rig, so it returns `is_metarig: true` and a `next_step` naming
  `mpfb_generate_rigify_rig` and saying that assets come first. "The rig was added" must not read as
  "the character is rigged".
- **Where a step forecloses a later one, say so at the point of decision.**
  `mpfb_generate_rigify_rig`'s `meta_rig_action: "delete"` leaves a character that can never be
  refitted again, which `mpfb_refit_human` can only report after the fact. `refit_will_be_possible`
  is that same fact, knowable in advance.
- **Splitting a tool can be what makes the order expressible.** Rigify generation is a tool of its
  own rather than a flag on `mpfb_add_rig` precisely because the correct order — meta rig, then
  clothes, then generate — cannot be written as a single call.

## A batched mutating tool resolves before it writes

Where a tool changes many things at once, **every entry is resolved and validated before anything
is written, and if any entry fails, none of them are applied.**

- **A half-applied batch is a state nothing can describe.** Thirty changes with one typo in them
  must apply zero, not twenty-nine: the character is then in a condition neither the agent nor the
  user can name, and the response format cannot usefully say which half landed or which half to
  retry. Failing the whole batch leaves the caller with one action — fix the entry and resend.
- **Resolve the expensive, failure-prone part up front.** For `mpfb_set_targets` that means
  locating the file each change *might* have to load, during resolution, so a missing target is a
  `resolution_errors` entry rather than an `IOError` raised half way through the writes.
- **Report per entry once application starts**, in request order, including what changed as a
  consequence — one sided change with `symmetry` on touches up to four shape keys, and the response
  has to be able to say so.
- **Batch because latency dominates, not on principle.** A socket round trip costs about a second
  while setting a modeling target costs milliseconds, so thirty calls would be half a minute of
  waiting for a fraction of a second of work. Where the work inside the call is itself expensive —
  loading an MHCLO asset is seconds of mesh import and vertex fitting — the argument does not carry
  over, and one-per-call is the better shape.

## When mpfb-mcp models a concept MPFB's UI has but its services do not

Not every concept a tool needs is a service concept. A modeling *modifier* — a slider from -1.0 to
+1.0, built from a pair of opposing targets, optionally with left and right variants — is not a
`TargetService` idea at all: it lives in `target.json` and in `mpfb/ui/model/_modelsubpanels.py`.
`mpfb_set_targets` lifts it out of the UI into the tool layer, because without it a caller could
address individual shape keys but could not express anything MPFB's own sliders express.

- **Reproduce the mechanics from MPFB's UI code rather than reinventing them**, statement for
  statement where the order matters. `_set_opposed_modifier_value()` zeroes the opposing target
  *first* and only then sets or loads the selected one; doing it the other way leaves both halves
  of a pair briefly non-zero and, with pruning on, deletes the wrong one.
- **Still never import the UI module**, for the reason in
  [Never import MPFB submodules directly](#never-import-mpfb-submodules-directly) — and here for a
  second reason: `_modelsubpanels` builds its table at *module import time*, so it is a snapshot
  from when Blender started, and a tool built on it would be blind to a target that
  `mpfb_list_targets` — which scans per call — can see.
- **Document the divergences rather than silently normalizing them.** MPFB's two setter functions
  disagree about the file extension, one trying `.target.gz` then `.target` and the other only the
  first; and MPFB's category name for a gzipped custom target does not strip `.gz`, so its shape key
  is not called what `mpfb_list_targets` reports. Both are reproduced or repaired deliberately, and
  said out loud in the payload docstring and in the response, because a caller who meets one will
  otherwise read it as a bug here.
- **The goal is that the value reads back on MPFB's own slider.** Where reproducing a quirk and
  tidying it up would give different answers in MPFB's panel, reproduce the quirk.

The general case — two MPFB *code paths* that disagree, rather than a UI concept the services lack —
is [Where MPFB's own code paths disagree, mpfb-mcp picks one and names it](#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).

## Response shape

Tools return blender_mcp's response envelope largely as-is: `{"status": "ok", "result": ...}`
or `{"status": "error", "message": ...}` (optionally `stdout`/`stderr`). Callers — including
future mpfb-mcp tools composing on top of others — must check `status` rather than assume
success. This mirrors blender_mcp's own tools and avoids inventing a second error convention.
