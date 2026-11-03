# Writing a mesh asset

**Status:** Proposed

The third of four requests scoping
[The MakeClothes and MakeSkin workflows](../NEXT_STEPS.md#the-makeclothes-and-makeskin-workflows).
It needs [FR 048](../048-measuring-mesh-assets/README.md)'s report and shares
[FR 049](../049-makeskin-materials/README.md)'s texture writing, so it lands after both.

**Writing an asset took `bpy.ops.mpfb.write_makeclothes_clothes(filepath=...)` with exactly the
basemesh and garment selected.** It leaves the selection cleared, reports only through `self.report`,
and can say `{'ERROR'}` and still return `{'FINISHED'}`. An agent has no way to mark a mesh as an asset
or set its metadata without three config classes. Nothing tells it what to do next.

**Reading the operators while scoping found more than the section lists:**

- **"Store in library" overwrites an existing asset without asking**, and creates the asset's directory
  before running the check, so a refused write leaves an empty directory behind.
- **MPFB's exporter writes a mesh the MHCLO does not describe when viewport subdivision is on.**
  Provoked on the gi: with its Subdivision at viewport level 0 the OBJ has 2,027 vertices, matching the
  mesh; at level 1 it has **11,862**. The MHCLO's matching strips `SUBSURF`, so it has 2,027 lines
  either way. The gi escaped because MPFB's modifier sat at level 0.
- **Three of the panel's fields never reach the file.** `Mhclo` has no `homepage`, `write_mhclo()` writes
  no tags, and `z_depth` is always 50, because the operator passes neither the property nor the
  attribute's real name, `zdepth`.
- **An untextured MakeSkin material is not written**, since the operator requires `makeskin` and MPFB
  [identifies that material as `gameengine`](../../specifications/mpfb-integration.md).
- **`disable_exact_strategy` defaults to true** in the panel, so a call to the matching function with its
  own default gets a different match from the panel's.

## Goals

**Primary:** one call turns a checked mesh into a complete asset (MHCLO, OBJ, MHMAT, textures), in a
location an agent can then try it from, and says exactly what it wrote.

**Secondary:**

- **The asset can be iterated on** without filling the library, through `destination`.
- **The mesh knows what it became.** After a library write, `mpfb_get_object_info` and the alternates in
  [FR 049](../049-makeskin-materials/README.md) work on the object.
- **An agent is told how to try it on another body**, with the tools that already exist.

## Non-goals

- **`mpfb_try_asset`.** The session's most useful loop was a posed character on another body, but a tool
  that does not touch the scene would be the project's first subprocess, or a temporary scene that can
  leave debris in the user's file. This request documents a recipe instead (FR 18). NEXT_STEPS keeps the
  tool, and the missing piece of the recipe, as their own entry.
- **Refusing on a measured defect.** Inverted normals and overlaps are reported, not enforced
  (see Decisions).
- **Modelling, unwrapping, weight painting.** The mesh arrives from generic Blender work, as the gi did.
- **`Extract clothes` from a helper group** and **`Import legacy`.** The first may deserve a tool once a
  session starts from a helper mesh rather than a draft.
- **Fixing MPFB**. What is provoked here gets filed upstream (see Tests).

## Functional requirements

### Arguments

1. **`name`** is the mesh. **`basemesh`** is optional, found the way MPFB's panels find it and refused when
   ambiguous. **`asset_name`** is a name, never a path.
2. **`object_type`** is MPFB's (`Clothes`, `Hair`, `Eyes` and so on), and is set on the object as
   `mpfb.mark_makeclothes_clothes` does. It is required when the mesh has none. `Basemesh` is refused. MakeClothes'
   enum spells the body proxy `Proxymesh`, while the glossary has `Proxymeshes`: the effort accepts whatever
   `mpfb_add_asset` accepts and says which is stored.
3. **`destination`** is `"library"` (the default) or `"export_directory"`. The first is
   `<user data>/<type>/<asset_name>/`, as the panel's "Store in library"; the second is
   `<export directory>/<asset_name>/`, using [FR 039](../done/039-exporting-characters/README.md)'s
   human-chosen directory, with `path_resolved_by` and `export_directory_missing` as there.
4. **`overwrite`** is false by default. **`dry_run`** does everything but write.
5. **`license`, `author` and `description`** default from the object, and `license_resolved_by` and
   `author_resolved_by` say `"argument"`, `"object"` or `"mpfb_default"`. An argument is also set on the
   object, so that MPFB's panel shows it. Any license is checked against MPFB's own enum (`CC0`, `CC-BY`,
   `AGPL`). A value that is MPFB's default rather than something somebody chose adds a `warnings` entry.
6. **`delete_group`** defaults to the object's `MC_delete_group`. Named and absent is a refusal rather than
   MPFB's log line, and a mesh with no such group is written with `delete_vertices: 0`, saying so.
7. **`allow_exact_matching`** follows the panel's `disable_exact_strategy`, whose default of true makes this
   false. It is reported in the answer. **`write_material`** defaults to true, as the panel's `save_material`.
8. **No argument exists for `homepage`, tags or `z_depth`**, because they would not reach the file.
   Offering them would be a lie, and the description says what happened to them.

### Refusals, all before anything is written

9. **`blocked_by: "not_valid_as_asset"`** when MPFB's own validator fails, carrying the validator's report.
   **This is the only check that blocks**, since it is what MPFB's write would refuse too. Everything else
   measured is reported.
10. **`asset_exists`** (with size and time), **`name_shadowed`** in a library write when a higher-priority
    root holds the same fragment, **`not_in_object_mode`** and **`basemesh_ambiguous`**.
11. **A failure while matching leaves no file and no directory.** Matching runs first, and nothing is
    written if it raises.

### What it does

12. **Builds a missing xref cache and reports `xref_cache_built`.** It is MPFB's own, generic to every base
    mesh and takes about 30 s, against a client timeout of 300 s. NEXT_STEPS proposed `blocked_by` here, but
    a refusal whose only remedy is an operator the agent has no tool for is not useful, and adding a tool
    for it would be worse.
13. **A `uuid` is generated if the object has none**, and reported, since MPFB keys alternate materials and
    colour adjustments by it. An existing one is kept across an overwrite.
14. **The OBJ matches the MHCLO.** It is exported without modifiers applied (see Architecture).
15. **The material's MHMAT and textures are written whenever it is MakeSkin**, untextured ones included, and
    through [FR 049](../049-makeskin-materials/README.md)'s module, so no source file changes. Other material
    types write none, and `material_written: false` says why. Proxies get none, as the panel gives them none.
16. **Overwriting replaces this asset's own files only.** Alternates in subdirectories, weights files and a
    thumbnail beside it are not removed. Files are written first to a temporary directory beside the
    destination and then moved one by one, so that a failure while writing cannot leave half an asset.
17. **A library write updates `asset_source`** on the object to the new fragment and refreshes MPFB's asset
    lists, and the answer says `asset_source_updated`. An export-directory write leaves it alone and reports
    the value, since MPFB's catalogue could not resolve a location outside its roots.

### The answer

18. **`path`** on every answer, and `files` with each one's size and action. **`match_counts`** (exact and
    offset), `delete_vertices`, `max_pole`, `allow_exact_matching`, `selection` restored.
    **`check`** is a summary of [FR 048](../048-measuring-mesh-assets/README.md)'s report: per component, the
    lowest `outward_fraction` and largest overlap counts. **`try_with`** gives the recipe's next calls:
    `mpfb_create_human_from_preset`, `mpfb_add_asset` with this asset's `fragment` or `path`, and
    `mpfb_check_intersections`.

### Documentation

19. **The recipe is written down**, in [README.md](../../README.md), with one sentence in the server's
    instructions: author on one character, write, then build a second from a preset, pose it, equip the asset
    and measure with masks off. The README also holds the texture recipe the session recommended instead of a
    tool (rasterize UV triangles into per-texel position and island maps, build a height field in metres,
    derive the normal map) and the traps: a masked overlap count is blind; mixed faces are refused, so an
    all-triangle draft stays triangles; subdivision's `uv_smooth` ripples a band one face wide.

## Non-functional requirements

- **No partial writes** across every refusal and failure. This is
  [the obligation's](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)
  general rule, and MPFB's path does not provide it.
- **Fidelity to the panel, by result.** An asset written here and one written by MPFB's panel from the same
  mesh must load identically through `mpfb_add_asset`. Departures are listed in the docstring and in
  Architecture.
- **Selection is unchanged**, where MPFB's exporter leaves it cleared.

## Architecture

- **`ClothesCommon` is an operator mixin, with no service behind it, so it is reimplemented from services**
  as [`set_asset_material`](../../bridge/mpfb_bridge/commands/set_asset_material.py) and the export copy
  were: `ClothesService.mesh_is_valid_as_clothes()`, `create_mhclo_from_clothes_matching()`,
  `get_reference_scale()`, `Mhclo.write_mhclo()`. It never calls `bpy.ops.mpfb.write_makeclothes_*`.
- **Departures from the panel**, all in the docstring and answer: a source texture is never rewritten; the OBJ
  is written without modifiers; `asset_source` is updated; an untextured MakeSkin material is written; nothing
  is overwritten by default.
- **`save_wavefront_file()` exports with `wm.obj_export`'s default `apply_modifiers=True`.** The OBJ cannot
  simply be left to a separate export: `write_mhclo(also_export_obj=False)` also drops the MHCLO's `obj_file`
  line. So keep MPFB's call and turn the garment's modifiers off in the viewport around it, putting them back
  in a `finally`, along with the selection. The live check confirms the file then matches at any level.
- **`write_mhclo()` derives the `obj_file` and `material` lines from the file name it is given**, so FR 16's
  temporary location must be a directory holding the final names, never temporary names.
- **The asset name's rule is stricter than exports'.** The panel turns anything outside `[a-zA-Z0-9_]` into `_`
  and collapses runs, so `my-gi` would land as `my_gi`, breaking the rule that
  [every accepted name is one MPFB's panel would accept unchanged](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more).
  `artifact_names.py` gains a noun and a pattern for this, on both sides of the socket.
- **Unverified: telling "never set" from "chose CC0"**, which FR 5's `"mpfb_default"` depends on.
  `BlenderConfigSet.has_key_with_value()` cannot do it, since it reads through to the default. Try Blender's
  `is_property_set()` on the property's full name (`MC_license`). If that cannot tell either, `"mpfb_default"` is
  dropped, and FR 5's warning fires whenever a `CC0` came from the object rather than an argument.
- **`MeshCrossRef`** is in `entities`. Read it off `clothesservice`'s module through `mpfb_surface`, for the
  cache build, as other names are read. It writes under `LocationService.get_user_cache("basemesh_xref")`.
- **Unverified pitfall, for the live check: a posed body.** `MeshCrossRef(after_modifiers=True)` strips only
  `MASK` and `SUBSURF`, so an armature modifier appears to stay. Matching against a posed character may then
  bake the pose into the offsets. Provoke it: if it does, it is a refusal (`rig_not_at_rest`) naming
  `mpfb_reset_pose`.
- **`generic_execute` also reads `basemesh` from the selection and `clothes` as "the other selected thing".**
  Taking both by name removes that ambiguity, which is the reason for FR 1.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog): **authoring as a fifth capability area**,
  naming FR 048-051's tools.
- [mutating-tools.md](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more):
  a choice of two destinations, neither chosen by path; the fourth writer's obligations; no partial asset.
- [mpfb-integration.md](../../specifications/mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not):
  the third reimplemented panel, and its departures.
- [responses.md](../../specifications/responses.md): `license_resolved_by` and `author_resolved_by`, beside
  `path_resolved_by`.
- [tool-interface.md](../../specifications/tool-interface.md): the name rule's new noun.
- [verification/README.md](../../verification/README.md): the smoke item uses `dry_run`, so it stays three
  files.

## Tests

- **Unit, in `tests/`:** every argument's shape, `destination`, the name rule on both sides over one table
  (extending `test_save_preset.py`'s drift check), and what reaches the wire. No `object_type` vocabulary is
  checked here.
- **`ddd_mutating/`:**
  - a mesh built by `ObjectService.extract_vertex_group_to_new_object()` from a helper group, written to both
    destinations and equipped back with `mpfb_add_asset` on a second character;
  - every refusal leaving no file and no directory;
  - overwrite keeping a neighbouring alternate;
  - the OBJ's vertex count equal to the MHCLO's with the viewport subdivision raised;
  - `asset_source` before and after each destination;
  - selection unchanged;
  - `license_resolved_by`'s three values.
- **`eee_composite/`:** writing by this tool and by MPFB's operator from one mesh and comparing the two
  MHCLOs, the differences being exactly the listed departures.
- **Live check, a script in this subdir:** this is **the first run of "Store in library"**, which the section
  calls untested. From `taido_gi_v2.blend`: write to both destinations, then the recipe on a second body in a
  pose, through tools alone, recording its counts beside the session's 159 and 105. Those were taken on the Taido
  template's own poses, so they are a reference and not a target. It must also show that `mpfb_get_object_info`
  and `mpfb_list_asset_materials` no longer report `mhclo_not_installed`. It provokes the posed-body pitfall and
  removes everything it wrote.
- **Filing upstream:** whatever the live check provokes goes in `mpfb2/features/MCP_DISCOVERED_BUGS.md`, with
  the OBJ mismatch, the dropped fields, the silent overwrite and the `{'ERROR'}`-then-`{'FINISHED'}` return.
- **Smoke item** with `dry_run`.

## Decisions taken while scoping

Asked on 2026-11-03:

- **`destination` is `library` or `export_directory`**. Library only, a human-chosen directory only, and a
  separate `asset_directory` preference were the alternatives.
- **Only MPFB's validator blocks a write.** The alternatives were also blocking on an unresolved texture or
  inverted normals, with an override, and blocking on any failed check with a `force` flag. The gi shipped with
  flap pairs that never show, so no threshold on a count would be objective.
- **`license` and `author` default from the object, and the answer reports where each came from.** Making them
  required, or requiring only `license`, were offered. Worth noting for whoever reads this later: MPFB's default
  is CC0, so a mesh nobody labelled is written as CC0, which is why FR 5 adds a warning for it and FR 046's
  catalogues will show that license afterwards.
- **`asset_source` is updated after a library write only**, rather than always, or never.
- **Trying an asset is a recipe with existing tools**, not a tool that spawns a headless Blender or a temporary
  scene.

*Not asked*, each argued where it is stated: `mpfb_write_mesh_asset` as the name; building the xref cache on
demand, against NEXT_STEPS' suggestion (FR 12); generating a missing `uuid` (FR 13); the OBJ without modifiers
(Architecture); no arguments for the fields that do not reach a file (FR 8).

## References

- [NEXT_STEPS: The MakeClothes and MakeSkin workflows](../NEXT_STEPS.md#the-makeclothes-and-makeskin-workflows).
- `interacting_with_blender/taido/gi/README.md` and `tools/test_on_template.py`.
- mpfb2: `ui/create_assets/makeclothes/operators/` (`clothescommon.py`, `writeclothes.py`,
  `writeclotheslibrary.py`, `bmxref.py`, `genuuid.py`, `markclothes.py`), `services/clothesservice.py`,
  `services/objectservice.py` (`save_wavefront_file`), `entities/clothes/mhclo.py`,
  `docs/ui/create_assets/makeclothes.md`.
