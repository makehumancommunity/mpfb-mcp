# Vision

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

## Goal

MPFB (MakeHuman Plugin For Blender) exposes a rich Python service layer
(`HumanService`, `TargetService`, `AssetService`, etc. — see `../mpfb2/`) for creating and
editing MakeHuman characters, but that layer is only reachable from *inside* a running
Blender process. mpfb-mcp's goal is to make MPFB's capabilities available to LLM agents (and
other MCP clients) as a normal set of MCP tools, without requiring any change to MPFB or to
the Blender MCP tooling it relies on.

## Approach: piggyback, don't fork

mpfb-mcp is a normal Python package, installed like any other MCP server, that runs as its
own MCP server process. It talks to the *existing, unmodified*
[blender_mcp](../../blender_mcp) add-on over the same TCP socket blender_mcp itself uses,
sending it generated Python code to execute inside Blender:

```
Claude / other MCP client
   |
   |-- stdio --> blender_mcp  (generic Blender tools)   --\
   |                                                       >-- TCP :9876 --> blender_mcp add-on --> exec() in Blender
   |-- stdio --> mpfb-mcp     (MPFB-specific tools)     --/                                            |
                                                                                                        v
                                                                                             MPFB services (bl_ext.*.mpfb)
```

The user enables MPFB and the blender_mcp add-on in Blender as usual, starts blender_mcp's
socket server from its preferences, and configures **two** MCP servers in their client. No new
Blender extension, no fork of blender_mcp, and no coordination of install order between MPFB
and blender_mcp is required. See [architecture.md](architecture.md) for how this is
implemented.

## Target tool catalog

These are the intended tools; only those marked **Implemented** exist today (see
[CLAUDE.md](../CLAUDE.md)). Naming and grouping below is indicative, not committed — each
tool should get its own feature request when scoped.

**Introspection (read-only)**

- `mpfb_get_status` — MPFB present? version? data roots configured? asset packs installed?
  **Implemented.** Takes no arguments and always answers, classifying the install as `absent`,
  `not_initialized` (loaded but `register()` did not complete) or `ok`; when `ok` it also
  reports version, install path, configured paths, the data roots MPFB will actually search,
  installed asset packs, and Blender version/platform/compatibility. The tool to reach for
  first when another MPFB tool fails unexpectedly.
- `mpfb_list_objects` — which MakeHuman objects are in the current scene, and of what type?
  **Implemented.** Optionally filtered by MPFB object type, using MPFB's own substring
  matching rather than equality. Reports each object's name, MPFB type and Blender type, plus
  MPFB's full type vocabulary and whether the requested filter named a type MPFB knows — so an
  empty list is never ambiguous. Cheap enough to call before anything else: a scene iteration
  and property reads, with no file lookups.
- `mpfb_get_object_info` — what is this object, what was it made from, and what belongs with
  it? **Implemented.** Takes a Blender object name, or the active object when given none, and
  answers rather than fails when neither resolves. Reports the MPFB and Blender types, whether
  the object is linked into the current scene, the asset behind it (`asset_info`), and its
  MakeHuman and non-MakeHuman relatives. Also reports a `rigify_role` on the subject and on
  every untyped relative, since a Rigify rig can drive a character while carrying none of
  MPFB's own properties. That field is *not* gated on the object lacking an MPFB type: MPFB
  tags the rig it generates through Rigify as a `Skeleton`, so the commonest generated rig
  there is would otherwise be the one case that never reported the field.
- `mpfb_list_rigs` — which rigs could be added to a character, and under what name?
  **Implemented.** Takes no required arguments and always answers, listing MPFB's bundled
  standard and Rigify rigs alongside the custom rigs found in the user's data roots. Each entry
  carries the `identifier` an adding function takes and the `add_function` that takes it (see
  [How tools name things that can be added](architecture.md#how-tools-name-things-that-can-be-added)),
  plus what adding it would do about weights — MPFB resolves those through a fallback table
  rather than by filename, so two rigs legitimately borrow another's. Reports `rigify_available`,
  the directories scanned and the files MPFB silently refused, so an absent rig is explainable
  rather than merely absent. Its vocabulary overlaps `mpfb_get_object_info`'s `rig_type` without
  matching it: `rigify_generated.*` and `unknown` describe an existing armature and name nothing
  that can be added. **Its `identifier` and `add_function` are consumed by `mpfb_add_rig`**, which
  dispatches on the prefix so the caller never picks the function — the same pairing
  `mpfb_list_targets` has with `mpfb_set_targets`. The weights prediction here and the weights
  outcome there are one implementation (see
  [Shared fragments](architecture.md#shared-fragments)), so the catalogue cannot promise what the
  adder does not deliver.
- `mpfb_get_macro_details` — what is this character's phenotype? **Implemented.** Reads the
  eleven macro sliders off a character named by *any* object in its family (see
  [How a mutating tool takes its subject](architecture.md#how-a-mutating-tool-takes-its-subject),
  which the read half follows too), and reports the values in MPFB's own nested shape beside
  the defaults, so a deliberately average character is distinguishable from an untouched one.
  Reports the three race weights raw with their `race_sum`, since MPFB treats them as
  independent and does not normalize them. Reports two things that can disagree: the macro
  target stack the current values *imply*, each entry named both as the file fragment MPFB
  loads and as the shape key it becomes, and the macro shape keys actually on the mesh — a
  difference between them is a character whose numbers and whose shape have drifted apart.
  `has_shapekeys` distinguishes a real MPFB character from an imported mesh that merely carries
  the properties. Changes nothing, and in particular does not repair the drift it reports.
- `mpfb_get_human_summary` — for a given/active human: macro details, equipped assets, rig,
  skin, active targets. Takes its subject from `mpfb_list_objects` / `mpfb_get_object_info`
  rather than assuming one is already known. The macro-detail half of its answer is
  `mpfb_get_macro_details`', and should be produced by calling into the same read rather than
  by a second implementation that can diverge from it.
- `mpfb_list_assets` — what could be put on a character, and under what name?
  **Implemented.** Lists the assets installed under every subdir in MPFB's own asset-library
  table — proxymeshes, skins, ink layers, eyes, eyebrows, eyelashes, hair, teeth, tongue,
  clothes and poses — filtered by subdir, by a substring of the name or label, and by asset
  pack, then capped and paged (see
  [How tools bound a large answer](architecture.md#how-tools-bound-a-large-answer)): the
  library runs to hundreds of entries on an ordinary install, so the answer is a subset by
  design and `truncated` says so. Each entry carries the absolute `path` the adding functions
  take, the portable `fragment` MPFB records on the resulting object, and the `object_type`
  that doubles as `add_mhclo_asset()`'s `asset_type` argument. `pack` is **derived from a
  directory-name convention, not recorded** (see
  [How tools report a derived rather than recorded fact](architecture.md#how-tools-report-a-derived-rather-than-recorded-fact)),
  hence `pack_ambiguous` beside it. Two costs are documented rather than hidden: the first
  call for a subdir loads a Blender preview per thumbnailed asset, and MPFB's cache is keyed
  by label, so same-named assets in different directories collapse into one entry. Its three
  identifiers each feed a specific argument elsewhere: `path` **or** `fragment` becomes
  `mpfb_add_asset`'s (exactly one of the two), and `object_type` becomes its **required**
  `asset_type` — which also decides the subdir a `fragment` is resolved against, so the two travel
  together. For a skin the same pair feeds `mpfb_set_skin` instead, under the `object_type`
  `Material`. **One thing is deliberately not in this answer and the gap is invisible from here:**
  an asset's *alternative* materials, which do not live in a library section at all but in the
  asset's own directory. `mpfb_list_asset_materials` is the catalogue for those.

- `mpfb_list_asset_materials` — which other materials does this equipped asset have?
  **Implemented**, and it is a tool of its own rather than a filter on `mpfb_list_assets` for one
  reason: alternative materials are **not an asset library section**. They are MHMAT files sitting
  in the asset's own directory, found by scanning the asset type's roots for `*.mhmat` whose path
  contains the asset's parent directory as a segment. Reports both identifiers per entry, the
  asset's own default material and whether it is installed, the fragment recorded on the object now,
  and the roots that were actually searched — so an asset with no alternatives is explainable rather
  than merely empty. Two facts belong in its answer rather than being smoothed away: MPFB does not
  filter the asset's own material out of the scan despite taking an `exclude_default` argument, so
  it is *flagged* rather than removed; and the scan is cached per asset with no invalidation, so the
  answer is a snapshot and a material installed later in the same Blender session will not appear.

- `mpfb_list_targets` — which modeling targets could be set, and under what name?
  **Implemented.** Answers from two sources that are different in kind: the bundled targets are
  indexed by a ~140 KB `target.json` that is far too large to return, so its *path* is reported and
  its sections are browsable one at a time; the user data directories have no index and are scanned
  per call. Each user target carries the `shapekey_name` `mpfb_set_targets` must be given —
  derived by MPFB from the filename, and **not** equal to it once a name passes 60 characters,
  where a caller using the filename addresses nothing at all. Capped and paged (see
  [How tools bound a large answer](architecture.md#how-tools-bound-a-large-answer)). Reports what
  the index leaves out (`unindexed_system_target_dirs`), which directories were scanned, and two
  facts MPFB's own UI does not show: a target installed since Blender started, and a `*.target.gz`
  in a user targets directory, which MPFB's scan there does not match (`listed_in_mpfb_ui`). A
  section can be `"system"`, `"user"` or `"both"` — MPFB merges a user directory into a bundled
  section of the same name rather than keeping the two apart. Macro details and phenotype are not
  here: those are basemesh attributes rather than target files. **Each identifier it reports feeds
  a different level of `mpfb_set_targets`**: a section name plus a category name out of
  `target.json` is a `modifiers` entry, and a user target's `shapekey_name` is a `targets` entry.
  That pairing is the whole contract between the catalogue and the setter.

- `mpfb_get_target_stack` — which modeling targets are on this character, and what sliders do
  they add up to? **Implemented.** Reads the shape keys off a character named by *any* object in
  its family, and answers in the two shapes the two levels are addressed by: `targets`, one entry
  per shape key with its raw `shapekey_name`, its readable `decoded_name`, its `kind` and where it
  sits in `target.json`; and `modifiers`, the same information rolled up per category with a value
  in -1.0..+1.0, computed as `_get_opposed_modifier_value()` computes it, which is both what MPFB's
  panel shows and what `mpfb_set_targets` takes back. Also reports `asymmetries`, the left/right
  categories whose two sides differ — a fact MPFB's own UI surfaces nowhere, and what makes
  `mpfb_symmetrize_targets` an informed operation. Macro and expression shape keys are excluded by
  default but always counted. Capped and paged (see
  [How tools bound a large answer](architecture.md#how-tools-bound-a-large-answer)). Reads
  `key_blocks` directly rather than through `TargetService`, so it can see a shape key whose name
  contains "basis" — which MPFB itself can neither read nor change (see
  [A tool may report a fact MPFB's own UI does not show](architecture.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show)).
  Changes nothing, and in particular does not repair a stack it reports as drifted.

**Creation and modification**

Every tool below except `mpfb_create_human` acts on an object that already exists, and names it
the way `mpfb_list_objects` and `mpfb_get_object_info` report it.

- `mpfb_create_human` — wraps `HumanService.create_human()` plus a macro-detail dict.
  **Implemented**, as a proof of concept covering scale + the macro-detail dict only (not
  `mask_helpers`/`detailed_helpers`/`extra_vertex_groups`/`feet_on_ground`). It takes the macro
  detail as eleven flat sliders and assembles MPFB's nested dict itself; whether it should take
  the dict directly instead is **settled: it should not**, for the reasons under
  [Validate before crossing the socket](architecture.md#validate-before-crossing-the-socket).
- `mpfb_set_macro_details` — change a character's phenotype in place. **Implemented.** Takes the
  same eleven flat sliders as `mpfb_create_human` (see
  [Validate before crossing the socket](architecture.md#validate-before-crossing-the-socket) for
  why they are flat rather than a nested dict), with every one optional and an omitted one meaning
  "leave unchanged" — which is what makes a relative change a single call. Writes every named
  property, then recalculates the macro target stack **once** through
  `TargetService.reapply_macro_details()`: MPFB's own interpolation, never a reimplementation of
  it, so that a character modified here matches one modified through MPFB's phenotype panel —
  **verified live**, and exactly: the same 21 shape keys at the same values to six decimals as the
  panel's own slider produces.
  Reports the prior value beside the new one per slider, the shape keys removed and added, and —
  when `refit` was left at MPFB's own default of false — what is now fitted to the old shape (see
  [A mutating tool reports before and after](architecture.md#a-mutating-tool-reports-before-and-after)).
  A call that names no slider recalculates nothing, and a basemesh in edit mode or without shape
  keys comes back as a sentence rather than an assertion (see
  [Preconditions are answers](architecture.md#preconditions-are-answers)).
- `mpfb_refit_human` — re-fit everything on a character to the current shape of its basemesh.
  **Implemented.** Wraps `HumanService.refit()`, and exists because `refit` defaults to *false* on
  every modeling tool here, as it does in MPFB's own model panel: a refit is expensive enough that
  MPFB does not want it per slider drag, and without a standalone one that default would leave an
  agent able to deform a dressed character with no way to put it right. Reports the mesh assets,
  rig and sub-rigs it touched, and separates two outcomes `refit()` itself does not: a missing
  basemesh, which it raises on, and a generated Rigify rig with no meta rig left in the scene,
  which it reports only through an `operator` an MCP tool cannot give it — refitting the mesh
  assets and silently leaving the rig.
- `mpfb_set_targets` — change a character's detail targets. **Implemented**, and it supersedes the
  single-target `mpfb_set_target_value` this catalog used to list: what a modeling slider actually
  manipulates is a `target.json` **category** — a modifier from -1.0 to +1.0 built from a pair of
  opposing targets, with left and right variants on about a third of them — and a tool that set one
  shape key at a time would produce characters MPFB's own UI cannot represent. So it works at both
  levels: `modifiers` for the category level, which is what keeps a character consistent, and
  `targets` for the raw shape-key level, which is the only way to reach a user-installed target and
  which takes the `shapekey_name` `mpfb_list_targets` reports (not the filename — the two differ
  for a long name, silently). **Batched**, and by a larger margin than that decision claimed:
  thirty modifier changes cost 3.6 s in one call and 98.4 s in thirty, of which only 7.5 s is
  transport — most of the rest is thirty rebuilds of MPFB's category table. **All-or-nothing**: everything is resolved before anything is
  written, and one bad entry applies none of them (see
  [A batched mutating tool resolves before it writes](architecture.md#a-batched-mutating-tool-resolves-before-it-writes)).
  Follows `_set_opposed_modifier_value()` statement for statement, including its ordering, so the
  value reads back on MPFB's own slider (see
  [When mpfb-mcp models a concept MPFB's UI has but its services do not](architecture.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not)).
  `symmetry`, `prune` and `refit` inherit MPFB's own defaults, and the response reports what is now
  stale the same way `mpfb_set_macro_details` does.
- `mpfb_symmetrize_targets` — make an already-asymmetric detail stack symmetric, in a named
  direction. **Implemented**, and a deliberate *addition* rather than a wrapper: MPFB's `symmetry`
  setting only mirrors changes made while it is on and explicitly leaves previously set values
  alone, so a character that has drifted has no repair path in MPFB's UI. `direction` is required,
  because which half of a face is the good one is not something a tool can guess, and `dry_run`
  reports exactly what a real run would do without writing. Walks the categories rather than the
  shape key names, so the left/right pairing comes from `target.json`'s `opposites` table and never
  from an `l-`/`r-` prefix match. A category whose target file cannot be found is skipped and
  reported rather than abandoning the rest of the body.
- `mpfb_add_asset` — equip one MHCLO asset via `add_mhclo_asset()`. **Implemented**, and for all
  eight of the types that function accepts rather than only clothes and proxies: `Clothes`,
  `Proxymeshes`, `Eyes`, `Eyebrows`, `Eyelashes`, `Hair`, `Teeth` and `Tongue`. Takes its `path`
  **or** its `fragment` from `mpfb_list_assets` — exactly one, both accepted, and `resolved_path`
  always reported, because resolving a fragment matches on basename and is lossy (see
  [An acting tool accepts every identifier its catalogue reports](architecture.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports)).
  Its `asset_type` is **required**, taken from that catalogue's `object_type`: MPFB's own default of
  `"Clothes"` is wrong for six of the eight and mislabels a body part permanently and silently, and
  a defaulted argument that changes what the character *is* must not be defaulted. `material_type`
  is defaulted **per asset type** instead — `NONE` for `Proxymeshes`, `MAKESKIN` otherwise, matching
  MPFB's settings panel rather than the function signature — and the choice is echoed back. **One
  asset per call**, because loading an MHCLO is seconds of mesh import and vertex fitting and the
  batching argument behind `mpfb_set_targets` does not carry over. Reports what the caller could not
  otherwise see: the object's actual name (Blender uniquifies a second copy to `…hat.001`, and that
  name is what `mpfb_remove_asset` needs), the delete group and which objects got a mask for it,
  whether a material was built at all, the sub-rig, and a `warnings` list for the four things MPFB
  only logs. **Verified live**: a garment equipped this way is identical to one equipped through
  MPFB's asset library panel down to the vertex positions, and all eight asset types were added. It is the other end of
  [A tool reports an ordering constraint it cannot enforce](architecture.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
  from `mpfb_add_rig`: `rigged_to` is `null` with `parented_to` beside it when the character had no
  rig at the moment of attachment. For a `Proxymeshes` asset it follows `_check_add_proxy()` — the
  `.mhm` loading path — rather than the proxy library operator, reporting the four extras in
  `proxy_extras` and naming the divergence (see
  [Where MPFB's own code paths disagree, mpfb-mcp picks one and names it](architecture.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)).
- `mpfb_remove_asset` — take one MHCLO asset off a character via `unload_mhclo_asset()`.
  **Implemented**, and in scope alongside adding for one reason: without it an agent that equips the
  wrong garment has no correct way to take it off, since deleting the object leaves the body's mask
  modifier and the garment's sub-rig behind. `name` is **required** — no active-object fallback,
  because this deletes an object. Refuses a `Basemesh` or a `Skeleton` outright, since the
  underlying function checks nothing and would delete either, and refuses an asset whose
  `asset_source` is empty, since the delete group's name is derived from it and removal would
  otherwise be silently partial. Distinguishes four fates rather than claiming one clean outcome:
  the mask modifiers removed, the sub-rig, the `Delete.*` vertex groups MPFB leaves behind, and the
  orphaned mesh datablock.
- `mpfb_set_skin` — via `set_character_skin()`. **Implemented.** Takes its `path` **or** its
  `fragment` from `mpfb_list_assets`' `skins` subdir — exactly one, both accepted, and
  `resolved_path` always reported, per
  [An acting tool accepts every identifier its catalogue reports](architecture.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports).
  A skin is a *material* rather than a mesh asset, so it is not `mpfb_add_asset`'s job: it is
  applied to objects that already exist, and to two of them, since MPFB gives the body proxy the
  same skin and nothing else would tell the caller a second object changed. The dimension the
  original one-line entry did not mention at all is `skin_type`: `MAKESKIN`, `GAMEENGINE`,
  `ENHANCED`, `ENHANCED_SSS` or `LAYERED`, which are five entirely different node trees built from
  the same MHMAT — **verified live**: each produces the node tree MPFB's own skin library panel
  produces for the same file, node for node. The choice is about the look and not about the cost:
  all five build within 33 ms of each other, and MPFB's warning that `LAYERED` is unsuitable for
  animation is about render time. Two of MPFB's defaults are followed
  from its **settings panel rather than the function signature**, per
  [Where MPFB's UI coerces or re-defaults a service argument](architecture.md#where-mpfbs-ui-coerces-or-re-defaults-a-service-argument-mpfb-mcp-does-the-same-and-reports-both):
  `skin_type` defaults to `MAKESKIN` and not `ENHANCED_SSS`, and `material_instances` is coerced
  off for three of the five types — so `material_instances_requested` and `_used` are both reported.
  `LAYERED` is the one type that may name no file at all. Three things are reported that nothing in
  Blender would show: `materials_destroyed`, because the call deletes every material on the body and
  the proxy, node groups included, with no undo across the socket; `settings_file_created`, the one
  file this package ever writes outside the `.blend`; and `scale_assumption`, which the enhanced
  types derive from the character's `scale_factor` and which changes the subsurface radii — `METER`
  for a character MPFB built, whose `scale_factor` is 0.1, whatever the property's declared default
  says.
- `mpfb_set_asset_material` — swap an equipped asset's material for one of the alternatives shipped
  beside it, or put its own back. **Implemented**, and the one tool here with **no service function
  to wrap**: the mechanism lives entirely in MPFB's asset library operator, so both of its helpers
  are reimplemented from services and its quirks reproduced rather than tidied up (see
  [Where MPFB's own code paths disagree](architecture.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)).
  `name` is **required** and is the asset's own object name — no active-object fallback, because
  this destroys that object's material — and it refuses a `Basemesh`, a `Proxymeshes` and a
  `Skeleton`, exactly as MPFB's own panel does; the first two carry a skin, which is
  `mpfb_set_skin`'s job.
- `mpfb_add_rig` — builtin or custom. **Implemented.** Takes its `identifier` from
  `mpfb_list_rigs`, the same way the tools above take their subject from `mpfb_list_objects` /
  `mpfb_get_object_info`, and **dispatches on the `custom.` prefix itself** rather than letting the
  caller name the function: `add_builtin_rig()` and `add_custom_rig()` are not interchangeable and
  crossing them does not fail legibly. Calls MPFB's own functions and reimplements none of the
  naming, parenting, weight-fallback or Rigify bookkeeping, so the result matches what MPFB's three
  "Add ... rig" buttons produce — **verified live**: the same 163 bones, the same bone names, the
  same vertex-group count, the same total vertex weight and the same parenting as
  `mpfb.add_standard_rig` produces. Reports what the caller could not otherwise see: which weights
  file was actually used and whose it was, whether an armature modifier was added, and that both
  adding functions **move the basemesh to the origin** and hand the armature its old location. Its
  five refusals are answers rather than exceptions (see
  [Preconditions are answers](architecture.md#preconditions-are-answers)) — most importantly a
  character that already has a rig, since MPFB has no way to swap one and adding a second silently
  orphans the first. And it is the first consumer of
  [A tool reports an ordering constraint it cannot enforce](architecture.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce):
  it rigs a dressed character without complaint but names, in `mesh_assets_not_rigged`, every asset
  it has just failed to rig.
- `mpfb_generate_rigify_rig` — turn a Rigify meta rig into a generated rig. **Implemented.** A tool
  of its own rather than a flag on `mpfb_add_rig`, because that is the only way the correct order —
  meta rig, then clothes, then generate — can be expressed at all. Unlike every other character
  tool it resolves its subject to the **meta rig** rather than the basemesh, and it distinguishes
  "already generated" from "not a Rigify rig" by classifying every `Skeleton` relative, since
  generation re-parents the character onto its result and leaves the meta rig outside the family.
  Two things it reports that MPFB cannot: that a **rejected** generation is not a no-op — the meta
  rig has already been renamed, everything deselected and Rigify's face upgrade possibly run before
  the validity gate — and that `meta_rig_action: "delete"` permanently forecloses refitting, which
  `mpfb_refit_human` can otherwise only discover afterwards. It is also the one tool here that
  cannot restore the caller's selection, and says so.

**Documentation**

- `mpfb_search_docs` — ranked search over bundled MPFB documentation, mirroring how blmcp
  exposes Blender's RST reference. Likely sourced from `../../makehuman-static-website`.

## Resolved: which "blender mcp"? Both

There are two unrelated projects called "blender mcp": blender lab's implementation (the
primary backend, at `../../blender_mcp`, which this project piggybacks on) and a separate,
more feature-rich [community implementation](https://github.com/ahujasid/blender-mcp), a local
clone of which is available at `../../ahujasid-blender-mcp`. Some users have the latter
installed instead of the former.

**Supporting both as backends is a goal.** blender lab's stays the reference one — it is what
the tools are written and live-verified against — but a user who already runs the community
add-on should be able to point mpfb-mcp at it rather than install a second one.

Comparing the two add-ons shows this to be a contained change. They differ in the request shape
and framing (`{"type": "execute", ..., "strict_json": bool}` with NUL delimiters, against
`{"type": "execute_code", "params": {...}}` framed by parsing until the JSON is complete), in
the envelope they answer with, and — the difference that matters — in the *result channel*:
blender lab's add-on serializes the `result` dict left in the exec namespace, while the
community one discards the namespace and returns only what the code printed to stdout.

The seam is therefore an adapter *below* `send_code()`, not a second connection module that
each tool picks between. The adapter translates the transport and the result channel together:
on the community backend it wraps the assembled program so that the payload's `result` is
printed as JSON between sentinel markers, and parses it back out into blender lab's envelope
shape. The markers are required rather than defensive, since MPFB's own `LogService` prints to
stdout and would otherwise land inside the answer. Tools, payloads and `codegen/` stay
unchanged, and the convention that a tool returns blender_mcp's envelope as-is holds on both.

Backend selection is explicit configuration, not autodetection: both add-ons default to port
9876, so the address distinguishes nothing, and no single probe distinguishes them either — a
NUL-terminated ping leaves the community add-on's parser waiting for the rest of a message,
while an unterminated one leaves blender lab's doing the same.

Two things are known to be worse on the community backend, and are accepted rather than solved:
`strict_json` becomes a client-side check inside the wrapper instead of an add-on one, and
stderr is lost, since its `execute_code` redirects only stdout. Error text is recovered by the
wrapper, which formats the traceback itself rather than accepting the bare `str(e)` the add-on
would report.

The work itself is not scoped into a feature request yet; see
[NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md#second-backend-the-community-blender-mcp).
