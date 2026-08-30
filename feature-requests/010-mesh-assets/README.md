# Equipping and removing mesh assets

**Status:** Proposed

[FR 005](../done/005-list-assets/README.md) built the asset catalogue and closed with the field it
exists for: the `path` an adding function takes, the portable `fragment` MPFB records, and the
`object_type` that doubles as `add_mhclo_asset()`'s `asset_type` argument. Nothing consumes any of
them. mpfb-mcp can list every garment, proxy, eye, hair and tooth on the machine and put none of them
on a character.

`HumanService.add_mhclo_asset()` is the one function behind all of it — clothes, body parts and
topology proxies are the same MHCLO pipeline with a different `asset_type` — and it does a great deal
per call: import the mesh, record `asset_source` and `object_type`, build a material, fit the mesh to
the body, build a delete group and mask the body under it, rig the result if a rig is there, and add
a subdivision modifier. Two of its arguments are the ones that get characters wrong. `asset_type`
defaults to `"Clothes"`, so hair added without it *becomes* clothes — wrong colour, wrong delete-group
handling, and an `object_type` property that is wrong from then on. And `material_type` defaults to
`"MAKESKIN"`, which is right for clothes, wrong for a topology proxy (which wants no material at all)
and merely one of three options for eyes.

Removing matters as much as adding, and for the same reason: an agent that equips the wrong garment
has no correct way to take it off. Deleting the object through generic blender_mcp leaves the mask
modifier on the body and the garment's sub-rig in the file. `HumanService.unload_mhclo_asset()` is
the operation that does it properly.

## Goals

Primary: attach any MHCLO asset `mpfb_list_assets` reports to a character, with the same result
MPFB's own asset library produces, and remove one cleanly.

Secondary: make the parameters that silently mislabel a character impossible to get wrong by
accident — `asset_type` required rather than defaulted, `material_type` defaulted per asset type
rather than globally.

Also: settle what a *proxy* is, since MPFB has three code paths for adding one and they disagree.

## Functional requirements

Two tools.

### `mpfb_add_asset`

Mutating, **one asset per call**. Loading an MHCLO is seconds of mesh import and vertex fitting, so
the ~1.0 s round trip does not dominate the way it does for
[FR 008](../008-detail-targets/README.md)'s target setting, and per-asset failures stay legible.
Arguments:

- `name` (optional string) — a Blender object name, resolved to the character's basemesh as in
  [FR 007](../007-macro-details/README.md). Omitted means the active object.
- `path` (optional string) — the absolute `path` `mpfb_list_assets` reports.
- `fragment` (optional string) — the `fragment` it reports instead, e.g. `"fedora/fedora.mhclo"`,
  resolved through `AssetService.find_asset_absolute_path(fragment, asset_subdir)`. Exactly one of
  `path` and `fragment` must be given. Both are catalogue outputs, and a tool that accepted only one
  of them would make the other half of every catalogue entry decorative.
- `asset_type` (**required** string) — the `object_type` `mpfb_list_assets` reports for the entry:
  `Clothes`, `Proxymeshes`, `Eyes`, `Eyebrows`, `Eyelashes`, `Hair`, `Teeth`, `Tongue`. Required
  rather than defaulted, because MPFB's default of `"Clothes"` is wrong for six of the eight and
  wrong in a way nothing reports.
- `material_type` (optional string) — `MAKESKIN`, `GAMEENGINE`, `PROCEDURAL_EYES` or `NONE`.
  Defaulted **per asset type**, matching MPFB's own settings panel rather than the function
  signature: `MAKESKIN` for clothes and body parts, `NONE` for `Proxymeshes` (which is what
  `HumanService._check_add_proxy()` passes), and `PROCEDURAL_EYES` accepted only for `Eyes`. The
  chosen value is echoed in the response, since it was usually not the caller's.
- `subdiv_levels` (optional int, default `1`) — `0` means no subdivision modifier at all. MPFB's own
  default is 1 with the modifier's viewport level at 0, so this affects render only.
- `set_up_rigging`, `interpolate_weights`, `import_subrig`, `import_weights` (optional bools, default
  `true`) — passed straight through; MPFB's own defaults.

`result` carries `basemesh_name`, `subject_resolved_by`, `found`, `message`, and:

- `asset_object_name` — the object actually created. MPFB names it
  `<basemesh name up to the first dot>.<mhclo basename>`, and Blender uniquifies a collision, so
  equipping two copies of the same garment gives `…hat` and `…hat.001`. Reported, not predicted:
  it is the address `mpfb_remove_asset` and every later tool will need.
- `resolved_path` and `asset_source` — the absolute path that was loaded and the fragment MPFB
  recorded on the object, per
  [How tools report the asset behind an object](../../specifications/architecture.md#how-tools-report-the-asset-behind-an-object).
  When the caller passed a `fragment`, `resolved_by: "fragment"` and the path it resolved to, because
  `find_asset_absolute_path()` matches on **basename only** and falls back to the first match when
  several files share a name — a real ambiguity the response must expose rather than absorb.
- `object_type_recorded` and `material_type_used`.
- `material_created` (bool) and `material_name`. `material_type: "NONE"` on an asset whose MHCLO
  names a material still **deletes** the imported mesh's materials and creates nothing; that is
  MPFB's proxy path and it is not obvious from the argument name.
- `rigged_to` — the rig the asset was set up against, or `null` with `parented_to` naming the basemesh
  instead. `add_mhclo_asset()` rigs only if a `Skeleton` relative exists *at this moment*; see
  [FR 009](../009-add-rig/README.md) for the ordering constraint, which this response is the other
  half of.
- `subrig_object_name` — a sub-rig imported from a `.mpfbskel` beside the MHCLO, when `import_subrig`
  found one.
- `delete_group_name` and `delete_group_applied_to` — the `Delete.<basename>` vertex group and the
  objects that got a mask modifier for it (the basemesh, and a body proxy when the asset is
  `Clothes`). This is the mechanism that makes the body disappear under a garment, and it is what
  removal has to undo.
- `subdiv_modifier_added` (bool).
- `proxy_extras` — for `Proxymeshes` only: whether the basemesh got its "Hide base mesh" mask, whether
  the scale factor was copied, which extra vertex groups were created, and whether the corrective pass
  ran. See the proxy note under Architecture.
- `warnings` — a list, for the things MPFB only logs: no material in the MHCLO, `set_up_rigging`
  requested with no rig present, `import_weights` requested with no weights file beside the asset.

Preconditions come back as answers with `added: false`:

- No basemesh resolves. `add_mhclo_asset()` does not check its `basemesh` argument and would fail
  deep inside `ClothesService.fit_clothes_to_human()` with a traceback that names nothing useful.
- `path` names no file, or `fragment` resolves to nothing.
- Both or neither of `path` and `fragment` given.
- `asset_type` is not one MPFB knows — answered with the vocabulary from the same
  `ASSET_LIBRARY_SECTIONS` table `mpfb_list_assets` reads, not from a list kept here.
- `material_type` is not valid for this `asset_type`.
- The basemesh is not in OBJECT mode.

### `mpfb_remove_asset`

Mutating. Wraps `HumanService.unload_mhclo_asset()`. Arguments:

- `name` (required string) — the Blender object name of the asset to remove, as
  `mpfb_list_objects` and `mpfb_add_asset` report it. Required rather than defaulting to the active
  object: this deletes an object, and "whatever happens to be selected" is not an acceptable way to
  choose which.

`result` carries `removed` (bool), `message`, and:

- `asset_object_name`, `object_type`, `asset_source` — what was removed, read *before* removing it.
- `basemesh_name` — the character it came off.
- `mask_modifiers_removed` — the delete-group mask modifiers taken off the basemesh and body proxy.
- `subrig_removed` — the asset's sub-rig, when it had one and nothing else was deformed by it.
- `vertex_groups_left_behind` — the `Delete.<basename>` vertex groups themselves, which
  `unload_mhclo_asset()` does **not** remove; only the modifiers referencing them go. Harmless, and
  invisible unless reported.
- `mesh_data_orphaned` — `bpy.data.objects.remove()` leaves the mesh datablock with no users until
  the file is saved and reloaded. Also harmless, also invisible.

Preconditions as answers: the name resolves to nothing; it resolves to something that is not a mesh
asset (a `Basemesh` or a `Skeleton` must be refused outright, since `unload_mhclo_asset()` would
happily delete either); no basemesh relative can be found, which matters because the mask cleanup
needs it.

**Not in scope.** Skins and alternative materials, which are
[FR 011](../011-skin-and-materials/README.md) — a skin is a material rather than an object and does
not go through this function at all. Ink layers and poses, which are in `mpfb_list_assets`' answer
but are neither MHCLO nor mesh (see [NEXT_STEPS.md](../NEXT_STEPS.md)). Installing asset packs
(`mpfb.load_pack`) or targets (`mpfb.install_target`). Batch equipping — see the note above.
`color_adjustments` and `alternative_materials`, both of which `add_mhclo_asset()` accepts as
uuid-keyed dicts; the alternative-material half is reachable after the fact through
[FR 011](../011-skin-and-materials/README.md)'s `mpfb_set_asset_material`, which is a better shape
for a tool argument than a dict keyed by a uuid the caller has no way to know.

## Non-functional requirements

- **The same result MPFB's own asset library produces**, with one documented exception (proxies,
  below). Call `add_mhclo_asset()` and `unload_mhclo_asset()`; do not reimplement the fitting, the
  delete group or the material.
- **A defaulted argument that changes what the character *is* must not be defaulted.** `asset_type`
  is required for that reason alone. This is a deliberate divergence from MPFB's own signature and
  the docstring must say so.
- **Removal must be complete, or must say what it left.** The mask modifiers, the sub-rig, the vertex
  groups and the orphaned mesh data are four different fates and the response distinguishes them.
- **Destructive operations announce themselves**, as
  [FR 008](../008-detail-targets/README.md) requires: `mpfb_remove_asset` deletes objects, and
  `mpfb_add_asset` with `material_type: "NONE"` deletes materials.
- **Preconditions are answers**, per [FR 007](../007-macro-details/README.md).
- **Restore what was borrowed.** `add_mhclo_asset()` calls `bpy.ops.object.shade_smooth()` and the
  fitting code changes the active object; the payload restores the previous active object and
  selection before returning.

## Architecture

- Two tool modules, two payloads, two `register()` calls, per
  [the code-generation layout](../../specifications/architecture.md#code-generation-layout).
  **Raising bootstrap** for both.
- **`GeneralObjectProperties` is not a service.** It lives on `ObjectService`'s module and is read
  the way
  [Reading module-level names MPFB does not publish](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish)
  prescribes — already done in
  [`payloads/get_object_info.py`](../../src/mpfbmcp/codegen/payloads/get_object_info.py). It is needed
  for reading back `asset_source`, `object_type` and `uuid`.
- **`ASSET_LIBRARY_SECTIONS` is the vocabulary**, read off `AssetService`'s module with the same
  fallback table [`payloads/list_assets.py`](../../src/mpfbmcp/codegen/payloads/list_assets.py)
  carries. It maps `asset_subdir` ↔ `object_type`, which is what turns a `fragment` into a resolvable
  path: `find_asset_absolute_path()` needs the subdir, and the caller supplied the object type.
- **Pitfall — `asset_type` is normalised, and the normalisation hides a mismatch.**
  `add_mhclo_asset()` stores `str(asset_type).lower().capitalize()`, so `"eyes"`, `"Eyes"` and
  `"EYES"` all become `Eyes`, and the asset *subdir* name works as well as the object type for every
  current section. Validate against the table anyway and echo what was recorded; relying on the
  coincidence would break the day a two-word type appears.
- **Pitfall — the `clothes` branch is keyed on the raw argument.** The delete-group interpolation onto
  a body proxy runs under `if str(asset_type).lower() == "clothes"`, so a garment labelled `Hair`
  does not get it. That is correct behaviour, and it is exactly why the argument must be right.
- **Proxies: MPFB has three code paths and they disagree.** `add_mhclo_asset()` alone imports the
  proxy and fits it, but does *not* hide the basemesh, copy the scale factor, create the proxy's extra
  vertex groups or run the corrective pass. `HumanService._check_add_proxy()` calls
  `add_mhclo_asset(..., material_type="NONE")` and then does all four. The library's
  `MPFB_OT_Load_Library_Proxy_Operator` does not call `add_mhclo_asset()` at all and duplicates a
  third variant, gated on its own scene settings. **Follow `_check_add_proxy()`**: it is the service
  layer's own answer, it is what `deserialize_from_mhm()` uses, and it is the one a caller comparing
  against a loaded `.mhm` would expect. Concretely, after the call: the `Hide base mesh` MASK modifier
  on the basemesh with vertex group `body` inverted; `scale_factor` copied from basemesh to proxy;
  vertex groups from `ALL_EXTRA_GROUPS[uuid]` (a module-level name on `HumanService`'s module, read
  with the usual fallback); and `HumanService._proxy_corrective(proxy)`. Report each in
  `proxy_extras`, and say in the docstring that the result matches `.mhm` loading rather than the
  library panel.
- **Reaching `_proxy_corrective()` is reaching a private name**, which is the one place this request
  bends
  [the rule about module-level names](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish).
  It is a member of a service resolved from `SERVICES`, not a fresh import, so it costs nothing at
  import time; read it with `getattr(HumanService, "_proxy_corrective", None)` and degrade to
  reporting `corrective_applied: false` if it has been renamed. Reimplementing it here would mean
  parsing `proxy_corrective.json` and rewriting vertex weights, which is not a thing to duplicate.
- **Pitfall — `find_asset_absolute_path()` matches basenames.** It walks the asset roots for a file
  with the fragment's *basename*, prefers a match whose parent directory also matches, and otherwise
  returns the first hit. Two packs shipping `hat.mhclo` therefore resolve to a coin toss. Report
  `resolved_path` always, so the coin toss is visible; this is the acting-tool counterpart of
  `mpfb_list_assets`' `pack_ambiguous`.
- **Pitfall — `add_mhclo_asset()` has no `fit_to_body` or `delete_group` switch.** MPFB's settings
  panel has both, and the library operator honours them, but the service function always fits and
  always builds a specific delete group. So `mpfb_add_asset` cannot offer them, and the docstring says
  so rather than leaving a caller looking for the argument.
- **Pitfall — a missing MHCLO material is only logged.** `if mhclo.material is not None` guards the
  whole material block, so an MHCLO with no material line produces an object with no material and no
  complaint. That is the `warnings` list's first entry.
- **Removal: read before deleting.** Everything reported about the removed asset — its name, type and
  `asset_source` — must be read before `unload_mhclo_asset()` runs, since the object is gone
  afterwards and `asset_source` is what the modifier names are derived from.
- **Pitfall — `unload_mhclo_asset()` derives the delete-group name from `asset_source`.** An asset
  whose `asset_source` property was never set, or was edited, leaves its mask modifier behind. Detect
  the empty-property case up front and report it instead of silently half-removing.
- Input validation per
  [Validate before crossing the socket](../../specifications/architecture.md#validate-before-crossing-the-socket):
  shape only — strings non-empty, `subdiv_levels` a non-`bool` int ≥ 0, the four flags real bools,
  exactly one of `path`/`fragment`. The `asset_type` and `material_type` **vocabularies** are checked
  inside Blender against MPFB's own table, not against a list kept here.
- Response envelope unchanged: `send_code(...)` as-is with `strict_json=True`.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog) — the `mpfb_add_asset` entry under
  "Creation and modification" should be marked **Implemented** and rewritten: the planned entry says
  "clothes/proxy", and what is proposed covers all eight MHCLO types with a required `asset_type` and
  a per-type `material_type` default. `mpfb_remove_asset` is a **new entry**. The `mpfb_list_assets`
  entry should gain a line naming which of its three identifiers feeds which argument here.
- [architecture.md](../../specifications/architecture.md) — conventions to follow, and two candidates.
  - **To follow:**
    [How tools name things that can be added](../../specifications/architecture.md#how-tools-name-things-that-can-be-added)
    and
    [How tools report the asset behind an object](../../specifications/architecture.md#how-tools-report-the-asset-behind-an-object),
    which this tool both consumes and produces — it is handed a `path`/`fragment` pair and records the
    fragment that a later `mpfb_get_object_info` reads back.
  - **Plus [FR 007](../007-macro-details/README.md)'s three additions** and
    [FR 009](../009-add-rig/README.md)'s ordering-constraint rule.
  - **New — an acting tool accepts every identifier its catalogue reports.** `mpfb_list_assets` gives
    a `path` and a `fragment` for a reason: one is passable and one is portable. A tool that took only
    the path would make a stored character description unusable, and one that took only the fragment
    would pay an `os.walk` per call. Take both, require exactly one, and report which resolved and to
    what — because the resolution itself is lossy.
  - **New — where MPFB's own code paths disagree, mpfb-mcp picks one and names it.** The proxy case
    above: three implementations, no documentation of which is canonical. The rule is to follow the
    *service-layer* path (it is what `.mhm` loading uses and what other services expect), to say so in
    the docstring, and to record the divergence as a candidate mpfb2 issue rather than silently
    inheriting whichever was read first. Related to, but sharper than,
    [FR 008](../008-detail-targets/README.md)'s "when mpfb-mcp models a concept MPFB's UI has but its
    services do not".

## Tests

Two layers, as established, with the stubs in
[tests/blender_stubs.py](../../tests/blender_stubs.py) extended rather than duplicated —
`StubAssetService` already exists from [FR 005](../done/005-list-assets/README.md) and needs
`find_asset_absolute_path()` added, reproducing behavior rather than convenience:

- `find_asset_absolute_path()` that matches on **basename**, prefers the directory-matching candidate
  and otherwise returns the first — with a fixture where two roots hold the same filename, so the
  ambiguity `resolved_path` exists to expose is genuinely under test.
- A `StubHumanService.add_mhclo_asset()` that reproduces the observable results rather than the work:
  it creates a stub object, sets `asset_source` and the **capitalised** `object_type`, builds the
  `Delete.<basename>` group, rigs only when a `Skeleton` relative is present, and skips the material
  entirely when the stub MHCLO has none. A stub that always produced a material would hide the first
  entry in `warnings`.
- `unload_mhclo_asset()` that removes only the modifiers, leaving the vertex groups — the claim
  `vertex_groups_left_behind` makes.
- Stub MHCLO fixtures: one with a material and a uuid, one with neither, one with a `.mpfbskel`
  beside it.

Cases worth naming: `asset_type` omitted is rejected in the tool module before any code is generated;
`path` and `fragment` both given, and neither given, are both rejected; a `fragment` that resolves
ambiguously still reports the path it chose; `material_type` defaults to `NONE` for `Proxymeshes` and
`MAKESKIN` for `Hair`; `PROCEDURAL_EYES` on `Hair` is refused; `subdiv_levels: 0` adds no modifier;
adding to a character with no rig reports `rigged_to: null` and `parented_to` the basemesh; adding a
`Clothes` asset to a character with a body proxy applies the delete mask to both; `mpfb_remove_asset`
refuses a `Basemesh` and a `Skeleton` by name; and an asset with an empty `asset_source` reports the
mask modifier it could not identify.

**Live verification against a running Blender is required** — more than for any earlier request, since
almost everything here is MPFB doing real geometry work that no stub reproduces. Full
[FR 004](../done/004-list-rigs/README.md)–006 revert discipline, and a fresh file per case.
Specifically:

- That a garment equipped through the tool is indistinguishable from the same garment equipped through
  MPFB's asset library panel with matching settings: same object name, same `asset_source`, same
  material, same vertex fit, same delete group, same modifiers.
- Each of the eight `asset_type` values at least once, since the delete-group and colour branches are
  keyed on it.
- **The proxy divergence, observed.** Add the same proxy through `mpfb_add_asset`, through MPFB's
  proxy library operator and through a `.mhm` load, and diff the three. This is the claim the
  Architecture section rests on, and it is currently read from source rather than measured.
- `material_type: "NONE"` on an asset whose MHCLO names a material — confirm the object really ends
  up with no material at all.
- Equipping two copies of the same asset, to confirm the `.001` naming and that removal takes the
  right one off.
- Removal end to end: the mask modifier is gone from the basemesh *and* from the body proxy, the
  sub-rig is gone, the vertex group remains, and the character looks as it did before the asset was
  added.
- Interaction with [FR 009](../009-add-rig/README.md): equip, then rig, and confirm `rigged_to: null`
  was telling the truth — the garment does not follow the armature.
- Interaction with [FR 007](../007-macro-details/README.md): change a macro detail after equipping and
  confirm `mpfb_refit_human` re-fits the garment.
- Cost against [FR 005](../done/005-list-assets/README.md)'s ~1.0 s baseline: how long equipping a
  garment actually takes, split between mesh import and fitting. This is the number the
  one-asset-per-call decision rests on, and it should be recorded rather than assumed.

Record the outcome in a `## Verification status` section here.

## References

- MPFB `services/humanservice.py` — `add_mhclo_asset()` (the whole of it: naming, `asset_source`,
  the material branches, the delete group, the `clothes`-only proxy interpolation, rigging and
  subdivision), `unload_mhclo_asset()`, `_check_add_proxy()` and `_proxy_corrective()`,
  `_check_add_bodyparts()` and `_check_add_clothes()` — the last two being MPFB's own answer to
  "which `material_type` for which asset type".
- MPFB `ui/apply_assets/assetlibrary/operators/` — `loadlibraryclothes.py` and `loadlibraryproxy.py`,
  the two UI paths, and `unloadlibraryclothes.py`, which is how the unload function is meant to be
  driven.
- MPFB `ui/apply_assets/assetlibrary/properties/` — the settings the library panel exposes, including
  the four (`fit_to_body`, `mask_base_mesh`, `delete_group`, `specific_delete_group`) that
  `add_mhclo_asset()` has no argument for.
- MPFB `services/clothesservice.py` — `fit_clothes_to_human()`, `set_up_rigging()`,
  `update_delete_group()`, `interpolate_vertex_group_from_basemesh_to_clothes()`.
- MPFB `services/assetservice.py` — `find_asset_absolute_path()` with its basename matching,
  `path_to_fragment()`, and `ASSET_LIBRARY_SECTIONS`.
- MPFB `entities/socketobject.py` — `ALL_EXTRA_GROUPS`, the proxy vertex-group table.
- [FR 005](../done/005-list-assets/README.md) — the catalogue whose `path`, `fragment` and
  `object_type` this request consumes, and its Verification status section.
