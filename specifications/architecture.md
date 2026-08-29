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

The same holds for the *shape* of a string argument: reject a non-string, or an empty or
whitespace-only one, and never quietly treat an explicitly empty value as an omitted one, since
the two arise from different mistakes. But validate only the shape, never the **vocabulary**. A
list of valid MPFB type names, asset names or target names kept on this side of the socket would
drift silently from MPFB's own. Send the value across instead and let the generated code answer
authoritatively, reporting alongside the result both whether the value was recognized and what the
valid values actually are — so a caller can correct itself from the same response rather than
needing a second tool or a hardcoded list.

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
  catalogue exists to remove.
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

## Response shape

Tools return blender_mcp's response envelope largely as-is: `{"status": "ok", "result": ...}`
or `{"status": "error", "message": ...}` (optionally `stdout`/`stderr`). Callers — including
future mpfb-mcp tools composing on top of others — must check `status` rather than assume
success. This mirrors blender_mcp's own tools and avoids inventing a second error convention.
