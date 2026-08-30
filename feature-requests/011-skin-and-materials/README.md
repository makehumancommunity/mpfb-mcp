# Skin and asset materials

**Status:** Proposed

A character with no skin is grey. `mpfb_create_human` builds a basemesh with whatever material
`create_human()` leaves on it, and nothing in mpfb-mcp can change that, so every character it produces
looks like clay. [FR 005](../done/005-list-assets/README.md) already lists the `skins` subdir — the
catalogue names the skins and nothing applies them.

A skin is not an asset in the sense [FR 010](../done/010-mesh-assets/README.md) uses the word. It is a
**material**, applied to objects that already exist rather than imported as one, and MPFB reaches it
through `HumanService.set_character_skin()` rather than `add_mhclo_asset()`. It also has a parameter
that changes the result more than the file does: `skin_type` picks between five entirely different
node trees built from the same MHMAT — a plain PBR material for export, MakeSkin's, the enhanced one
with and without subsurface scattering, and the multilayered one. Which one to use is a real decision
with real cost, and MPFB's own default (`MAKESKIN` in the settings panel) is not the same as the
function's (`ENHANCED_SSS`).

The same distinction shows up one level down. A garment or a body part is equipped with the material
its MHCLO names, and MPFB lets the user swap it for any other MHMAT that ships beside the asset — a
hat in three colours is one mesh and three materials. That mechanism lives entirely in a UI operator,
has no service function of its own, and its catalogue is not part of `mpfb_list_assets`' answer,
because alternative materials do not live in an asset library section: they sit beside the asset they
belong to.

## Goals

Primary: set a character's skin from any MHMAT the catalogue reports, with any of the five skin types,
and get the same material MPFB's own skin library produces.

Secondary: make an equipped asset's material changeable and restorable, and give that operation the
catalogue it currently lacks.

Also: expose the choices MPFB's UI silently makes on the user's behalf — the `material_instances`
coercion, the body-proxy resolution, and the fact that applying a skin destroys every material already
on the body.

## Functional requirements

Three tools: one setter for the character's skin, one setter for an equipped asset's material, and
the small read-only catalogue the second one needs.

### `mpfb_set_skin`

Mutating. Wraps `HumanService.set_character_skin()`. Arguments:

- `name` (optional string) — a Blender object name, resolved to the character's basemesh as in
  [FR 007](../done/007-macro-details/README.md). Omitted means the active object.
- `path` (optional string) / `fragment` (optional string) — the MHMAT, addressed either way, exactly
  as in [FR 010](../done/010-mesh-assets/README.md); resolved against the `skins` subdir. This is now
  the standing rule
  [An acting tool accepts every identifier its catalogue reports](../../specifications/architecture.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports),
  so follow it rather than restate it — including its third clause: always report `resolved_path`,
  since `find_asset_absolute_path()` matches on basename and a skin resolved from a fragment can
  land on a different file than the caller meant. Exactly one, and
  **both may be omitted only when `skin_type` is `LAYERED`**, which is the one type that builds a
  material from nothing. `codegen/shared/asset_sections.py` already exists and already knows that
  `Material` maps to the `skins` subdir, so the lookup is a call rather than a table.
- `skin_type` (optional string, default `"MAKESKIN"`) — `MAKESKIN`, `GAMEENGINE`, `ENHANCED`,
  `ENHANCED_SSS` or `LAYERED`. The default follows MPFB's **settings panel**, not the function
  signature's `ENHANCED_SSS`; the divergence is named in the docstring, since a caller comparing
  against the UI would otherwise get a different material than the one they saw.
- `material_instances` (optional bool, default `true`) — whether to create per-vertex-group material
  slots (fingernails, lips, and so on). MPFB's own default, with MPFB's own coercion: the UI forces it
  to `false` for `LAYERED`, `GAMEENGINE` and `MAKESKIN`, and this tool does the same rather than
  passing a value that would produce something the UI cannot.

`result` carries `basemesh_name`, `subject_resolved_by`, `found`, `message`, and:

- `resolved_path` and `material_source` — the file loaded and the fragment MPFB recorded, per
  [How tools report the asset behind an object](../../specifications/architecture.md#how-tools-report-the-asset-behind-an-object).
  Note that `set_character_skin()` records `material_source` **only when an MHMAT was given**, so a
  `LAYERED` skin with no file leaves the property at whatever it was — an inconsistency worth
  reporting rather than papering over.
- `skin_type_used`, `material_instances_requested` and `material_instances_used`, with a sentence when
  the two differ. A silent coercion is the kind of thing that makes a tool look broken.
- `bodyproxy_name` — the `Proxymeshes` relative the skin was also applied to, or `null`. The function
  resolves this itself when passed `None`, so the response is the only place the caller learns that a
  second object was modified.
- `materials_destroyed` — the names of the materials that were on the basemesh and body proxy
  beforehand. `set_character_skin()` opens with
  `MaterialService.delete_all_materials(..., also_destroy_groups=True)`, so a hand-built material on
  the body is gone and there is no undo across the socket. This list is that fact, made visible.
- `material_slots` — the slots that exist afterwards, which is how `material_instances: true` differs
  observably from `false`.
- `settings_file_created` (bool) — `ENHANCED` and `ENHANCED_SSS` copy
  `enhanced_settings.default.json` into the user config directory when it is not already there. A tool
  that writes a file outside the `.blend` says so.
- `scale_assumption` — `METER`/`DECIMETER`/`CENTIMETER`, which the enhanced types derive from the
  character's `scale_factor` and which changes the SSS radii. Reported because a wrongly scaled
  character gets a subtly wrong skin and nothing else would explain it.

Preconditions come back as answers with `applied: false`: no basemesh resolves; `path`/`fragment`
resolves to nothing; both given; neither given with a non-`LAYERED` `skin_type`; unknown `skin_type`,
answered with the vocabulary; not in OBJECT mode.

### `mpfb_set_asset_material`

Mutating. Replaces the material on an equipped MHCLO asset with an alternative MHMAT, or puts the
asset's own back. Arguments:

- `name` (required string) — the Blender object name of the **asset**, as `mpfb_list_objects` and
  [FR 010](../done/010-mesh-assets/README.md)'s `mpfb_add_asset` report it. Required, not defaulted to the
  active object, for the same reason removal's is: this destroys the object's current material.
- `path` / `fragment` (optional strings) — the MHMAT to apply, as reported by
  `mpfb_list_asset_materials` below.
- `restore_default` (optional bool, default `false`) — put back the material the asset's own MHCLO
  names, and clear the recorded `alternative_material`. Mutually exclusive with `path`/`fragment`.

`result` carries `asset_object_name`, `object_type`, `message`, and: `resolved_path`;
`alternative_material` (the fragment recorded on the object afterwards, empty when the default was
restored); `previous_alternative_material`; `materials_destroyed`; `material_name`; and
`diffuse_color_from` — the object type the display colour was taken from, since MPFB keys that on
`object_type` and an asset mislabelled at equip time gets the wrong one here too.

Preconditions as answers: the name resolves to nothing; the object has no MPFB `object_type`; it is a
`Basemesh`, `Proxymeshes` or `Skeleton` (MPFB's own panel refuses all three — the first two have a
skin, not an asset material, and that is `mpfb_set_skin`'s job); it has no `asset_source`, so its
default material cannot be found; `restore_default` given together with a path.

### `mpfb_list_asset_materials`

Read-only, always answers. The catalogue `mpfb_set_asset_material` consumes, and the reason it is here
rather than in [FR 005](../done/005-list-assets/README.md): alternative materials are not an asset
library section. They are MHMAT files sitting in the asset's own directory, discovered by scanning the
asset type's roots for `*.mhmat` whose path contains the asset's parent directory name. Nothing in
`mpfb_list_assets`' answer names them. Arguments:

- `name` (required string) — the equipped asset object.

`result` carries the subject fields plus: `asset_source` and the `asset_subdir` it was searched under;
`default_material` (path and whether it exists on disk); `current_alternative_material`; `materials` —
one entry per alternative, each with `path`, `fragment` and `name`; `count`; and `search_roots`, so an
asset with no alternatives is explainable rather than merely empty, per
[How tools name things that can be added](../../specifications/architecture.md#how-tools-name-things-that-can-be-added).

**Not in scope.** Ink layers, which are in `mpfb_list_assets`' answer and are a different mechanism
again — `MaterialService.load_ink_layer()` adds a UV map and a layer to an existing MakeSkin or
Layered material, works on no other material type, and is invisible when a body proxy is present; they
deserve their own request and are listed in [NEXT_STEPS.md](../NEXT_STEPS.md). Also out:
`slot_overrides` for `LAYERED` skins and the enhanced-skin per-slot settings, which are nested
dictionaries of node socket values and are a poor fit for a tool argument; MakeSkin authoring (editing
or saving an MHMAT); node-tree manipulation of any kind; texture baking; and `color_adjustments`, the
uuid-keyed dict `add_mhclo_asset()` accepts.

## Non-functional requirements

- **The same result MPFB's own skin library produces.** Call `set_character_skin()`; reproduce the
  UI's coercions (`material_instances`, the body-proxy lookup, the active body material slot) rather
  than the UI's code.
- **Destructive operations announce themselves.** Both setters delete every existing material on their
  target, and one of them does it to two objects. `materials_destroyed` is not decoration.
- **Side effects outside the `.blend` are reported.** The enhanced skin types write a settings file
  into the user's config directory on first use. Nothing else in mpfb-mcp writes to disk, so this is
  worth a field.
- **Preconditions are answers**, per [FR 007](../done/007-macro-details/README.md), including the three
  object types `mpfb_set_asset_material` refuses.
- **An empty catalogue must be explainable.** `mpfb_list_asset_materials` reports the roots it searched
  and the asset source it searched for, so "this hat has no other colours" is distinguishable from
  "the hat's asset source no longer resolves".
- **Restore what was borrowed** — previous active object and selection, and the previously active
  material slot where the tool did not deliberately change it.

## Architecture

- Three tool modules, three payloads, three `register()` calls, per
  [the code-generation layout](../../specifications/architecture.md#code-generation-layout).
  **Raising bootstrap** for all three; `HumanService`, `MaterialService`, `AssetService` and
  `ObjectService` are in the `SERVICES` dict.
- **`mpfb_set_asset_material` has no service function to call, and must not import the one that
  exists.** The logic lives in
  `mpfb/ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py` as two module-level helpers,
  `_apply_mhmat()` and `_find_default_material()`. Importing an MPFB submodule is forbidden
  ([architecture.md](../../specifications/architecture.md#never-import-mpfb-submodules-directly)), and
  a UI operator module is the worst case of it. Reimplement both from services, as
  [FR 006](../done/006-list-targets/README.md) and [FR 008](../done/008-detail-targets/README.md) do for
  the modeling panels, and say so in the payload docstring. The pieces are all service-level:
  `MaterialService.has_materials()`, `create_empty_material()`, `get_diffuse_colors()`,
  `AssetService.find_asset_absolute_path()`, `path_to_fragment()`, and `MakeSkinMaterial`, which is an
  **entity** rather than a service — reached as
  `getattr(sys.modules[HumanService.__module__], "MakeSkinMaterial", None)`, since `humanservice.py`
  imports it, per
  [Reading module-level names MPFB does not publish](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish).
  Degrade with a plain message if it is not there rather than guessing at an import path.
- **`Mhclo` is needed too, and only for its metadata.** `restore_default` reads the asset's MHCLO for
  its `material` line; MPFB's operator does it with `mhclo.load(path, only_metadata=True)`, which skips
  the vertex tables and is the difference between a fast read and parsing a large file. Use the same
  flag. `Mhclo` is likewise an entity on `HumanService`'s module.
- **Pitfall — `set_character_skin()`'s defaults disagree with MPFB's UI, in two places.**
  `skin_type` defaults to `ENHANCED_SSS` in the signature and `MAKESKIN` in the settings panel; and
  `material_instances` defaults to `True` in the signature while the UI forces it `False` for three of
  the five types. This tool follows the UI both times, because the UI is what the user sees and what a
  character loaded from a `.mhm` was made with. Both choices belong in the docstring.
- **Pitfall — `LAYERED` accepts no MHMAT.** `MaterialService.create_v2_skin_material()` takes
  `mhmat_file=None`, and `HumanService._set_skin()` explicitly returns early for a missing MHMAT
  *unless* the type is `LAYERED`. That is the only reason `path`/`fragment` can be omitted, and only
  then.
- **Pitfall — the enhanced types write to the user config directory.** `set_character_skin()` copies
  `enhanced_settings.default.json` from MPFB's data into `LocationService.get_user_config(...)` when it
  is absent. Detect its absence before the call so `settings_file_created` is a fact and not a guess.
- **Pitfall — `delete_all_materials(..., also_destroy_groups=True)`.** The node *groups* go too, not
  only the material slots. Read the material names off both objects before calling.
- **Body proxy resolution happens twice, so do it once and report it.** `set_character_skin()` resolves
  the `Proxymeshes` relative itself when passed `None`; the payload needs the same object anyway, for
  `materials_destroyed` and for the active-slot fixup. Resolve it in the payload, pass it explicitly,
  and report it.
- **The active-material-slot fixup is UI behaviour worth copying.** After loading, MPFB's operator
  selects the slot whose material name ends in `body`, on both the basemesh and the proxy. Without it
  the user's material properties panel is looking at a fingernail material. Cheap, and it is part of
  "the same result the UI produces".
- **`alternative_materials_for_asset()` is cached, per `(asset_source, asset_subdir)`.**
  `mpfb_list_asset_materials` therefore reports a snapshot: a material dropped into the asset's
  directory after the first call for that asset is not seen. Say so in the docstring, the way
  `mpfb_list_targets` reports where MPFB's own view is stale — this is the same convention seen from
  the other side, since here it is *mpfb-mcp* that would be stale.
- Input validation per
  [Validate before crossing the socket](../../specifications/architecture.md#validate-before-crossing-the-socket):
  shape only — non-empty strings, real bools, the mutual exclusions. `skin_type`'s vocabulary is small
  and stable enough to check locally *as well*, but the authoritative check stays inside Blender, and
  the response reports `known_skin_types` on a miss.
- Response envelope unchanged: `send_code(...)` as-is with `strict_json=True`.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog) — the `mpfb_set_skin` entry under
  "Creation and modification" should be marked **Implemented** and gain the `skin_type` dimension,
  which the current one-line entry does not mention at all. `mpfb_set_asset_material` and
  `mpfb_list_asset_materials` are **new entries**, the latter under "Introspection (read-only)". The
  `mpfb_list_assets` entry should gain a sentence saying that alternative materials are *not* part of
  its answer and where they are instead, since that gap is invisible from the catalogue.
- [architecture.md](../../specifications/architecture.md) — conventions to follow, and one candidate.
  - **To follow:**
    [How tools report the asset behind an object](../../specifications/architecture.md#how-tools-report-the-asset-behind-an-object)
    (`material_source` and `alternative_material` are exactly the recorded-fragment case it describes),
    [How tools name things that can be added](../../specifications/architecture.md#how-tools-name-things-that-can-be-added)
    for the small catalogue, and
    [A tool may report a fact MPFB's own UI does not show](../../specifications/architecture.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show)
    for `materials_destroyed` and `scale_assumption`.
  - **Plus the three conventions [FR 007](../done/007-macro-details/README.md) landed** —
    [How a mutating tool takes its subject](../../specifications/architecture.md#how-a-mutating-tool-takes-its-subject),
    [A mutating tool reports before and after](../../specifications/architecture.md#a-mutating-tool-reports-before-and-after)
    and
    [Preconditions are answers](../../specifications/architecture.md#preconditions-are-answers) —
    and — now that [FR 010](../done/010-mesh-assets/README.md) has landed it as a standing convention —
    [An acting tool accepts every identifier its catalogue reports](../../specifications/architecture.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports),
    which this request **follows** rather than proposes. Note also
    [Where MPFB's own code paths disagree, mpfb-mcp picks one and names it](../../specifications/architecture.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it),
    which FR 010 landed for the proxy case and which the alternative-material half of this request
    is a candidate for: that mechanism lives entirely in a UI operator and has no service function
    at all.
  - **New — where MPFB's UI coerces or re-defaults a service argument, mpfb-mcp coerces the same way
    and reports both values.** A service signature's default is not always the product's default; the
    `skin_type` and `material_instances` cases here are the first two, and silently passing the
    signature's value would produce characters that cannot be reproduced through the UI — the same
    quality bar [FR 007](../done/007-macro-details/README.md) sets for macro details. Reporting
    `*_requested` beside `*_used` is what keeps the coercion from looking like a bug.

## Tests

Two layers, as established. [FR 010](../done/010-mesh-assets/README.md) has since grown
[tests/blender_stubs.py](../../tests/blender_stubs.py) part of the way there — `StubMaterialService`
now has `has_materials()`, `delete_all_materials()` and `create_empty_material()`, objects carry real
modifier and vertex-group collections, and `MeshAssetTestCase` provides a real asset library on disk
with a character to put it on. Extend those rather than adding a second fixture. What is still
missing is the skin half, reproducing behavior rather than convenience:

- `set_character_skin()` that **deletes every material on both objects first**, records
  `material_source` only when given a file, and creates a different stub material per `skin_type` —
  so `materials_destroyed` and `skin_type_used` are asserted against something.
- The `material_instances` coercion left *out* of the stub service, so that the payload is what
  performs it and the test is testing mpfb-mcp rather than the stub.
- `alternative_materials_for_asset()` that caches per `(asset_source, asset_subdir)` as the real one
  does, with a case that adds a file after the first call — the staleness the docstring claims.
- A stub `Mhclo` honouring `only_metadata=True`, and a fixture asset whose MHCLO names a material that
  does **not** exist on disk, which is the `restore_default` failure branch.
- `get_diffuse_colors()` keyed by object type, with an asset whose type is not in the table, so the
  `(0.8, 0.8, 0.8, 1.0)` fallback is exercised.
- A stub scene with a character that has a body proxy and one that does not.

Cases worth naming: `skin_type` omitted defaults to `MAKESKIN` and not to the signature's
`ENHANCED_SSS`; `material_instances: true` with `skin_type: "LAYERED"` reports requested `true` and
used `false`; `LAYERED` with no path is accepted and every other type with no path is refused; a skin
applied to a character with a body proxy reports both objects' destroyed materials; `ENHANCED_SSS`
reports `settings_file_created` exactly when the file was absent; `mpfb_set_asset_material` refuses a
`Basemesh`, a `Proxymeshes` and a `Skeleton` by name; `restore_default` on an asset with no
`asset_source` is refused with an explanation; and `mpfb_list_asset_materials` reports its search roots
when it finds nothing.

**Live verification against a running Blender is required** — materials are node trees, and no stub
says anything about whether the right one was built. Full [FR 004](../done/004-list-rigs/README.md)–006
revert discipline, fresh file per case. Specifically:

- **All five `skin_type` values**, each compared against the same skin applied through MPFB's own skin
  library panel: same node tree, same slot layout, same recorded `material_source`.
- That `material_instances: true` with an enhanced skin really does produce the extra slots
  (fingernails, lips, and the rest), and that they carry the settings from
  `enhanced_settings.default.json`.
- The settings-file creation, observed on a profile where the file does not yet exist — and confirmed
  *not* repeated on the second call.
- `scale_assumption` on a character created at a non-default scale, since the SSS radii depend on it
  and nothing else in the response would reveal a wrong guess.
- A skin applied to a character wearing a body proxy: the proxy must get it too, and the basemesh's
  hand-built material must be reported as destroyed.
- `LAYERED` with no MHMAT at all.
- `mpfb_set_asset_material` on a multi-colour asset, both directions, plus `restore_default`, with
  `mpfb_get_object_info` read back afterwards to confirm the recorded `alternative_material` matches.
- The alternative-material cache staleness, by dropping an MHMAT into an asset directory between two
  calls.
- Cost against [FR 005](../done/005-list-assets/README.md)'s ~1.0 s baseline: how long each skin type
  takes to build, since `LAYERED` is documented by MPFB itself as heavy enough to be unsuitable for
  animation.

Record the outcome in a `## Verification status` section here.

## References

- MPFB `services/humanservice.py` — `set_character_skin()` (all five type branches, the
  `delete_all_materials` opening, the `material_source` recording, the enhanced-settings file copy and
  the scale detection) and `_set_skin()`, which is how `.mhm` loading calls it.
- MPFB `services/materialservice.py` — `delete_all_materials()`, `create_empty_material()`,
  `create_v2_skin_material()`, `create_and_assign_material_slots()`, `get_diffuse_colors()`,
  `identify_material()`, `has_materials()`, and `load_ink_layer()` for what is deliberately not here.
- MPFB `services/assetservice.py` — `alternative_materials_for_asset()` and its module-level cache,
  `alternative_material_tiles_for_asset()` (the UI wrapper, which loads previews and is deliberately
  not used), `find_asset_absolute_path()`, `path_to_fragment()`.
- MPFB `ui/apply_assets/assetlibrary/operators/loadlibraryskin.py` — the UI's coercion of
  `material_instances` and the active-body-slot fixup.
- MPFB `ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py` — `_apply_mhmat()` and
  `_find_default_material()`, the two helpers `mpfb_set_asset_material` reimplements.
- MPFB `ui/apply_assets/assetlibrary/alternativematerialpanel.py` — which object types the UI allows
  an alternative material on, which is where this request's three refusals come from.
- MPFB `ui/apply_assets/assetlibrary/properties/skin_type.json` — the five types, their labels and the
  panel default this request follows.
- [FR 005](../done/005-list-assets/README.md) — the catalogue that reports the `skins` subdir, and
  whose answer does *not* include alternative materials.
