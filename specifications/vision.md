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
  that can be added.
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
  by label, so same-named assets in different directories collapse into one entry.

- `mpfb_list_targets` — which modeling targets could be set, and under what name?
  **Implemented.** Answers from two sources that are different in kind: the bundled targets are
  indexed by a ~140 KB `target.json` that is far too large to return, so its *path* is reported and
  its sections are browsable one at a time; the user data directories have no index and are scanned
  per call. Each user target carries the `shapekey_name` a later `mpfb_set_target_value` must be
  given — derived by MPFB from the filename, and **not** equal to it once a name passes 60
  characters, where a caller using the filename addresses nothing at all. Capped and paged (see
  [How tools bound a large answer](architecture.md#how-tools-bound-a-large-answer)). Reports what
  the index leaves out (`unindexed_system_target_dirs`), which directories were scanned, and two
  facts MPFB's own UI does not show: a target installed since Blender started, and a `*.target.gz`
  in a user targets directory, which MPFB's scan there does not match (`listed_in_mpfb_ui`). A
  section can be `"system"`, `"user"` or `"both"` — MPFB merges a user directory into a bundled
  section of the same name rather than keeping the two apart. Macro details and phenotype are not
  here: those are basemesh attributes rather than target files.

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
  it, so that a character modified here matches one modified through MPFB's phenotype panel.
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
- `mpfb_set_target_value` — arbitrary named target. Takes its name from `mpfb_list_targets`:
  the `shapekey_name` of a user target, or a name out of a `target.json` category's `targets`
  or `opposites`. Not a filename — the two differ for a long name.
- `mpfb_add_asset` — clothes/proxy via `add_mhclo_asset()`. Takes its `path` (or a `fragment`
  to resolve) and its `asset_type` from `mpfb_list_assets`.
- `mpfb_set_skin` — via `set_character_skin()`. Takes its `path` from `mpfb_list_assets`'
  `skins` subdir; a skin is a material rather than a mesh asset, so it is not
  `mpfb_add_asset`'s job.
- `mpfb_add_rig` — builtin or custom. Takes its `identifier` and the function to dispatch
  on from `mpfb_list_rigs`, the same way the tools above take their subject from
  `mpfb_list_objects` / `mpfb_get_object_info`.

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
