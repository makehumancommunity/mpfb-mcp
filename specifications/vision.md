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
- `mpfb_get_human_summary` — for a given/active human: macro details, equipped assets, rig,
  skin, active targets. Takes its subject from `mpfb_list_objects` / `mpfb_get_object_info`
  rather than assuming one is already known.
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
  `mask_helpers`/`detailed_helpers`/`extra_vertex_groups`/`feet_on_ground`).
- `mpfb_set_macro_details` — gender/age/weight/muscle/height/proportions via `TargetService`
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

## Open design question: which "blender mcp"?

There are two unrelated projects called "blender mcp": blender lab's implementation (the
intended backend, at `../../blender_mcp`, which this project piggybacks on) and a separate,
more feature-rich [community implementation](https://github.com/ahujasid/blender-mcp), a local
clone of which is available at `../../ahujasid-blender-mcp` for reference/comparison. Some
users may have the latter installed instead of the former. Whether to support both as
backends — and if so, how mpfb-mcp would detect which one it's talking to — is unresolved.
