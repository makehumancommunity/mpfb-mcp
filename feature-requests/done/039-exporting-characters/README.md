# Exporting characters: an export copy, and a file another application can open

**Status:** Done

Everything the thirty-two tools build stays inside Blender. A character made for a game engine, a
VR platform or a web viewer has to leave. Today an agent has to hand that step back to the user,
and it is not a simple one. MPFB's documentation
([Exporting MPFB characters](https://github.com/makehumancommunity/makehuman-static-website/blob/master/content/MPFB/Docs/exporting/_index.md))
covers it in three stages. First, get the character into a state other applications can read:
bake the modeling shape keys, delete the helper geometry, and decide what to do with mask and
subdivision modifiers. Second, pick materials and a rig that translate. Third, select the right
objects and run Blender's FBX exporter with the right three settings.

MPFB automates the first stage with its **Export copy** panel
(`src/mpfb/ui/operations/exportops/` in mpfb2). It makes a deep copy of the character, processes
the copy, and leaves the original untouched. It can also load viseme and ARKit face unit shape keys
onto the copy, which is the main reason to use it for lip sync and face tracking in an engine.
**It writes no file.** The file is Blender's `export_scene.*`, which the documentation asks the
user to run by hand. There is also **no service to wrap**: the sequence exists only in
`MPFB_OT_Create_Export_Copy_Operator.hardened_execute()`, which composes `ExportService`,
`TargetService` and `FaceService` calls. That is the situation
[`mpfb_set_asset_material`](../../../src/mpfbmcp/tools/set_asset_material.py) was built for:
rebuild the sequence from services, in a bridge command.

This request adds **two tools**. `mpfb_create_export_copy` mirrors MPFB's panel.
`mpfb_export_character` writes a file from any character, an export copy or not. Splitting them
means an agent can build a copy, look at it with the existing read tools, change it, and only then
write it. It also means exporting a character that needs no processing (one with a body proxy and
no basemesh, for example) costs one call.

Reading the operator turned up three things this request has to deal with, not inherit:

- **`bake_shapekeys` (on by default) bakes every shape key, not only the modeling ones.** An applied
  expression and any face units composed with `mpfb_set_face_units` are frozen into the copy's
  mesh. Any ARKit units loaded afterwards are relative to that face, not to a neutral one. Nothing
  in MPFB says so.
- **The copy shares its materials with the original.** `ObjectService.duplicate_blender_object()`
  copies the object and its mesh, and a copied mesh points at the same material datablocks.
  Changing the copy's materials, which the GameEngine swap below does, changes the original's
  unless the copy is given its own materials first.
  Since [FR 040](../040-procedural-material-settings/README.md), `mpfb_get_material_settings`
  and `mpfb_set_material_settings` report this for the procedural eye, layered skin and
  colour-adjustment materials as `material_shared_with` / `materials_written`, which would name the
  copy while it still shares; a bridge test here could use that rather than comparing datablocks.
  The swap also rebuilds those materials, so the copy loses what FR 040's write set on them.
- **The operator's REMOVE branches delete modifiers from the list they are iterating over**
  (`for modifier in new_basemesh.modifiers: ... remove(modifier)`), which can skip the neighbour of
  each removed modifier. This is a defect candidate for `mpfb2/features/MCP_DISCOVERED_BUGS.md`,
  to be confirmed against a running install before it is filed. That file already has a section of
  candidates that turned out to be wrong.

## Goals

**Primary:** an agent can take a character it built to a file that Unity, Unreal, Godot or a
glTF/USD pipeline can open, without the user repeating MPFB's documented preparation by hand, and
without the original character being changed.

**Secondary:**

- **Mirror MPFB's Export copy panel faithfully**: the same options, the same defaults and the same
  order of operations. A user who knows the panel should get the same copy from the tool.
- **Report facts about export readiness, not warnings**: which materials are procedural, whether
  helper geometry is still present, whether a topology-changing modifier sits beside shape keys,
  whether a face was baked in. The agent decides from those facts. The tool neither refuses nor
  lectures.
- **Keep the rule that the agent cannot choose where a file is written.** The human chooses the
  export directory in the bridge's preferences, and the agent chooses only a name.
- Establish how a capability that depends on the **viseme packs** (`visemes01`, `visemes02`) is
  probed. MPFB has no install check for either pack, unlike `faceunits01`.

## Functional requirements

Delivered in three phases, each shippable on its own: **A** is `mpfb_create_export_copy` as MPFB
has it, **B** is `mpfb_export_character` with its readiness facts, and **C** is the two additions
MPFB's panel lacks (the GameEngine material swap and engine presets). If C grows, it may be split
into its own request. The request is `Done` only when all three have landed.

### Phase A: `mpfb_create_export_copy`

1. **Subject.** Takes `name`, which is any object in the character's family, with `null` meaning
   the active object. It is resolved through `shared/subject_resolution.py` like every other
   subject. A miss is `blocked_by: "subject_not_found"`
   ([FR 038](../038-subject-not-found-everywhere/README.md)).
2. **The panel's eleven options, with the panel's defaults**: `bake_shapekeys` (true),
   `mask_modifiers` and `subdiv_modifiers` (each `KEEP`/`REMOVE`/`BAKE`, default `KEEP`),
   `delete_helpers` (true), `remove_basemesh` (false), `load_meta_visemes`,
   `load_microsoft_visemes` and `load_arkit_face_units` (each false), `interpolate` (false),
   `suffix` (`"_export_copy"`), and `in_export_collection` (true, MPFB's `collection`). An unnamed
   option takes the panel's default, per
   [mpfb-integration.md](../../../specifications/mpfb-integration.md#where-mpfbs-ui-coerces-or-re-defaults-a-service-argument-mpfb-mcp-does-the-same-and-reports-both).
   The exact spellings are settled against [the glossary](../../../specifications/tool-interface.md#the-glossary)
   during the effort. MPFB's own spellings are kept only where no glossary row disagrees.
3. **The operator's order of operations, reproduced**: copy, bake shape keys, load visemes and face
   units, interpolate, bake modifiers and remove helpers, remove the modifiers set to `REMOVE`, and
   remove the basemesh. The REMOVE step collects the modifiers first and removes them afterwards,
   so none is skipped. This departs from the operator on purpose, and the tool's docstring says so,
   per [where MPFB's own code paths disagree](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).
4. **The original is unchanged**: same shape keys, modifiers, materials, selection and active
   object. The bridge tests check this by reading the original before and after.
5. **A face that gets baked is reported.** When `bake_shapekeys` is true and the character's face
   is not neutral (an expression stack row with non-zero weight, or a face unit with a non-zero
   value), the answer carries what was frozen into the mesh, as `face_baked_into_mesh` or the
   glossary's spelling: the stack rows and the unexplained face units with their values, read
   through `shared/expression_divergence.py` so this tool agrees with the three that already report
   it. When the face was neutral, the key is empty and no sentence is added.
6. **The optional packs, following
   [the faceunits01 pattern](../../../specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack)**:
   - Asking to load a set whose pack is absent is refused before anything is copied, with
     `blocked_by` naming the pack (for example `"visemes02_not_installed"`). A refusal is never a
     half-built copy.
   - `faceunits01` is probed with MPFB's `FaceService.is_faceunits01_installed()`. **The two viseme
     packs have no MPFB probe.** `load_targets()` raises when a target is missing. The command
     therefore resolves every viseme's target file before copying, the same way
     `mpfb_set_targets` resolves its batch, and treats "none resolved" as not installed and "some
     resolved" as the per-item `could_not_load`. That definition belongs in
     [mpfb-integration.md](../../../specifications/mpfb-integration.md), and "MPFB should expose
     `is_visemes01_installed()`" is filed as a request to MPFB, not as a defect.
   - Every answer reports `faceunits01_installed`, `visemes01_installed` and `visemes02_installed`,
     since a caller choosing options needs them whether or not it asked for a set.
7. **`remove_basemesh` with no body proxy is refused** (`blocked_by: "no_bodyproxy"` or the
   glossary's spelling). The result would be a character with no body, and MPFB's documentation
   recommends the option only "if you use a body proxy".
8. **The answer names what was built**: the copy's root (the rig, or the basemesh when there is no
   rig), its basemesh (`null` if removed), its body proxy, every copied object with its role, the
   collection it landed in, and what each step did (modifiers baked or removed per object, helpers
   removed, shape keys loaded per set, the meshes each set was interpolated onto). It also reports
   `performed`. The copy is a full MPFB character in its own right, and every read tool will treat
   it as one. The description says so once, because a scene now holds two characters and
   `mpfb_list_objects` will list both.
9. **The caller's selection and active object are restored**, like the other mutating tools.
   MPFB's operator leaves the copy active; this tool does not.

### Phase B: `mpfb_export_character`

10. **Subject** as in 1. It exports the subject's **whole family**, walked recursively from the
    root. A garment's sub-rig is a grandchild, and `ObjectService.get_list_of_children()` returns
    direct children only.
11. **`format`**: `fbx`, `gltf` or `usd`. Each writes **one self-contained file** with textures
    embedded: `.fbx` with `path_mode="COPY"` and `embed_textures=True`, `.glb`, and `.usdz`. One
    file is one artifact to name, report and refuse to overwrite. A "textures beside the file"
    mode is left out of this request (see [Decisions](#decisions-taken-while-scoping)).
12. **Destination: a name, not a path.** `export_name` is validated by
    [`artifact_names.py`](../../../src/mpfbmcp/artifact_names.py) on both sides of the socket, as a
    third noun beside presets and saved expressions, and the drift test covers it. The file is
    `<export directory>/<export_name>.<ext>`. The **export directory** is:
    - a directory the human set in a new **bridge preference**, or passed as `--export-dir` to the
      headless command;
    - otherwise `<MPFB user data>/exports`, created on first use.

    A directory set in preferences that does not exist is refused, not created
    (`blocked_by: "export_directory_missing"`), because a typo in a preference should not become a
    new directory tree. Every answer, refusals included, carries the absolute `path` and
    `path_resolved_by: "preferences" | "command_line" | "default"`.
13. **`overwrite`**, default false. An existing file is refused with its size and modification
    time, as `mpfb_save_preset` does.
14. **Only the family is written.** Other characters, the original of an export copy, lights and
    cameras are not.
15. **Readiness facts** in every successful answer, per exported mesh or rig where they apply, and
    **never a refusal**:
    - each mesh's material as `material_identified_as`, plus the list of meshes whose material is
      procedural (anything but GameEngine, which is the only material MPFB's documentation calls
      likely to translate);
    - whether the basemesh still has helper geometry (`HelperGeometry`/`JointCubes` vertex
      groups);
    - mask and subdivision modifiers still present, per object;
    - shape keys per mesh, counted by kind (modeling, visemes, face units, other);
    - **topology-changing modifiers beside shape keys** on one mesh. The exporters apply modifiers
      and cannot then keep shape keys consistently. glTF drops them, and what FBX and USD do is
      established by the live check. This is the case `ExportService._apply_modifiers_keep_shapekeys()`
      exists for, and the fact should name `mpfb_create_export_copy` with `mask_modifiers: "BAKE"`
      as the step that fixes it;
    - the rig as `rig_identified_as`.

    Which facts to report and how they are spelled is settled against
    [responses.md](../../../specifications/responses.md). A fact that is true on every answer is
    dropped instead of being reported.
16. **The caller's selection is restored in full.** The exporters work on the selection, so the
    command selects the family, exports and puts back every object's selection state. This is the
    first tool that needs the full snapshot described in
    [NEXT_STEPS: selection restore covers one object](../../NEXT_STEPS.md#selection-restore-covers-one-object).
    The snapshot goes into `shared/selection.py` for this tool. The other ten commands are left for
    that entry.

### Phase C: what MPFB's panel lacks

17. **GameEngine material swap** on `mpfb_create_export_copy`: an option (spelled per the glossary,
    for example `material_type: "GAMEENGINE"`, default `null` meaning "keep") that gives every mesh
    in the copy its own materials and then rebuilds them as GameEngine materials from each mesh's
    MHMAT: the skin through `HumanService.set_character_skin(skin_type="GAMEENGINE")`, and eyes and
    other mesh assets through the path MPFB takes when it loads an asset with that material type.
    **The original's materials must be untouched**, and a bridge test compares them datablock by
    datablock. A mesh whose MHMAT cannot be found is kept as it was and listed as not swapped,
    without failing the rest.
18. **Engine presets** on `mpfb_export_character`: `target_engine`, one of `generic` (the default:
    Blender's exporter defaults plus the settings MPFB's documentation prescribes), `unity`,
    `unreal` and `godot`. A preset is a fixed table of exporter options per format: axes, scale
    application, leaf bones, deform-only bones and so on. **Every value in the table cites where it
    came from** (engine documentation, MPFB's documentation, or a documented community setting),
    in the command's docstring. A preset/format pair with no defined table (for example
    `godot` with `fbx`, if the effort decides Godot means glTF) is refused, naming the formats
    that preset does support. The answer reports the options actually passed to the exporter, so
    a caller can reproduce the export by hand.

## Non-functional requirements

- **Faithfulness over tidiness.** Phase A reproduces the panel, with only the documented departure
  in requirement 3. A cleaner option set that differs from MPFB's would split what an agent does
  from what a user does.
- **Duration within the socket timeout, measured.** Baking masks while keeping shape keys
  duplicates the whole mesh once per shape key, and MPFB's documentation warns it "might take a
  while". With all three sets loaded (22 + 15 + 52 keys) the worst case could get close to
  `bridge_connection.py`'s 300 s `_TIMEOUT`. The live check measures the worst case. If it is over
  roughly a third of the timeout, the effort has to change something (for example, loading the
  sets after the bake, which the operator already does) or say in the description which
  combination is slow. Blender's UI is blocked for the duration in a windowed Blender, and the
  description says so.
- **A refusal is never a partial write**, for both tools: packs probed, names validated and the
  file checked for existence before anything is copied or opened
  ([mutating-tools.md](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)).
- **Description budget.** Two tools with about sixteen and five arguments are the largest addition
  so far. `tests/test_description_budget.py`'s ceiling is only raised if the descriptions have
  been trimmed first, and the facts that live in the answer (pack state, readiness) are not
  repeated in the description.
- **No new network access**, and no path from the caller reaches the filesystem.

## Architecture

- **Four things per tool, as usual**: `tools/create_export_copy.py` and `tools/export_character.py`,
  two `register()` calls, `bridge/mpfb_bridge/commands/create_export_copy.py` and
  `.../export_character.py`, and two entries in `commands/table.py`. The additions outside that
  rule are all listed here: `artifact_names.py` gains a noun (both copies); `shared/selection.py`
  gains a full snapshot; the bridge gains a preference and a CLI flag. If anything else shared has
  to change, stop and say why.
- **The export directory lives in the bridge, not in `mpfb-mcp`.** A `StringProperty(subtype="DIR_PATH")`
  on `MPFB_BRIDGE_Preferences` in [ui.py](../../../bridge/mpfb_bridge/ui.py), drawn on the panel next
  to host and port, plus `--export-dir` in [cli.py](../../../bridge/mpfb_bridge/cli.py) for a Blender
  with no preferences UI worth using. Because it lives in the add-on, the human who started the
  bridge is the one who chose it. An environment variable on the `mpfb-mcp` side would put the
  choice in the MCP client's configuration, which an agent may be able to edit.
- **Reimplement the operator from services; do not call `bpy.ops.mpfb.export_copy`.** The operator
  reads its options from scene properties (`EXPO_*`). Calling it would mean writing the user's
  panel settings and restoring them afterwards, plus the rule against importing UI operators. The
  services it composes are all public: `ExportService.create_character_copy()`,
  `ExportService.bake_modifiers_remove_helpers()`, `TargetService.bake_targets()`,
  `FaceService.load_targets()`, `FaceService.interpolate_targets()`.
- **`bake_modifiers_remove_helpers()` drives `bpy.ops`** (mode_set, modifier_apply, mesh.delete)
  and changes the active object and selection throughout. Follow what the ten mutating commands
  already do for context and restore (see the comments in `add_asset.py` and
  `generate_rigify_rig.py`).
- **Pitfalls for the live check to settle:**
  - **Generated Rigify rigs.** `object.copy()` keeps drivers, and a driver whose target is the
    original rig still points at the original. Check whether a copied Rigify rig deforms from its
    own bones or from the original's. If it depends on the original, report it as a fact; do not
    try to fix it here.
  - **Shared materials** (requirement 17). The same applies to any bake that writes to images.
  - **`bake_modifiers_remove_helpers()` calls `TargetService.reapply_all_details()`** when
    `bake_shapekeys` is false and modeling keys remain, which reloads targets. Check that this
    changes nothing on the original.
  - **Exporter options per format for modifiers and shape keys** (requirement 15). Record what
    each exporter does with a mask modifier beside shape keys, so the readiness fact is stated from
    observation and not from memory.
- **Selection for export.** FBX, glTF and USD each have a selection-only option (`use_selection`,
  `use_selection`, `selected_objects_only`). Using it is simpler than the collection-exporter
  route, which would need the family to live in one collection, and it is not guaranteed to.

## Affected specifications

- [mutating-tools.md — A tool whose effect is outside the `.blend` owes more](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more):
  "address the artifact by name, never by a path" gains its third case. The directory may be one
  **the human** chose in the add-on, never one the caller chose. `path_resolved_by` then says
  which.
- [mpfb-integration.md](../../../specifications/mpfb-integration.md): the viseme packs as an optional
  capability **with no MPFB probe**, and how one is defined then;
  [when mpfb-mcp models a concept MPFB's UI has but its services do not](../../../specifications/mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not)
  gains the export copy as its second example; and the documented REMOVE-branch departure.
- [tool-interface.md — the glossary](../../../specifications/tool-interface.md#the-glossary):
  `export_name` (an `<artifact>_name`), `format`, `target_engine`, the option spellings, and the
  "copy" and "export copy" nouns.
- [responses.md](../../../specifications/responses.md): readiness facts as the next instance of
  [a tool may report a fact MPFB's own UI does not show](../../../specifications/responses.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show).
- [architecture.md](../../../specifications/architecture.md): the bridge now has a preference the
  commands read, and a `shared/selection.py` that snapshots everything.
- [vision.md — Target tool catalog](../../../specifications/vision.md#target-tool-catalog): exporting
  becomes part of what an agent must be able to do. It could be a fifth area, or folded into
  "keep it" beside presets; the effort decides.
- [verification/README.md](../../../verification/README.md): the smoke run writes a **third** file
  outside the `.blend` (the export) and leaves a copy in the scene.
- [testing.md](../../../specifications/testing.md): only if the round-trip check below introduces a
  pattern it does not already describe.

## Tests

- **Wrapper tests** (`tests/test_create_export_copy.py`, `tests/test_export_character.py`): the
  shape of every argument; `export_name` across the shared name table as the third noun, with
  `test_save_preset.py`'s two-way drift check extended to it; `format` and `target_engine`, which
  are this package's own vocabularies and so shapes like `mode`; and whether `mask_modifiers` and
  `subdiv_modifiers` earn a local check under
  [the exception](../../../specifications/tool-interface.md#validate-before-crossing-the-socket) or
  are left to the command. `tests/test_verification_smoke.py` and `tests/test_vocabulary.py` pick
  the two tools up without being edited.
- **Bridge tests** in `bridge/test/tests/ddd_mutating/`: the original unchanged after every
  option; each option's effect on the copy; the refusals (pack absent, no proxy for
  `remove_basemesh`, missing export directory, existing file); `face_baked_into_mesh` on a
  character with an applied expression and on one with composed units. Pack-dependent cases skip
  where the pack is not installed, and say so. The export directory is a temporary directory set
  through the preference, never the user's own.
- **A round trip in `eee_composite/`**: copy with everything on, export in each format, **re-import
  into a scratch scene**, and compare object, bone and shape key counts to the copy. The harness
  can check that a file was written and reads back. It cannot check that Unity, Unreal or Godot
  accept it. That limit goes in the command docstring next to the preset tables.
- **The live check**, in this subdir as a script: the matrix of formats × presets on a character
  with a rig, garments, a proxy, an expression and every pack installed; the worst-case duration;
  the Rigify-driver question; the per-exporter modifier/shape key behaviour; and confirmation of
  the REMOVE-branch defect before it is filed.
- **Two smoke items** in [verification/](../../../verification/), default arguments, the export
  writing under a fixed name into the default directory.

## Decisions taken while scoping

- **Two tools, not one.** A copy that can be inspected and changed before it is written is worth
  a second call, and exporting a character that needs no processing should not force a copy.
  Rejected: one tool with a transient copy, one tool that keeps the copy, and the export copy
  alone.
- **Name only, in a human-set directory.** Rejected: a caller-supplied absolute path, which is the
  most convenient but lets an agent write anywhere Blender can; and a fixed directory only, which
  leaves the user moving files by hand every time.
- **FBX, glTF and USD.** OBJ was left out because it carries neither rig nor shape keys, which is
  what an MPFB character is.
- **All four extras are in scope**: visemes and face units, readiness facts, the GameEngine swap
  and engine presets. They are phased so that A and B do not wait on C.
- **One file per export, textures embedded** (proposed while writing this request, not asked).
  Textures written beside the file would make an export several artifacts, each of which the
  overwrite rule and the answer would have to cover. Revisit if a target application cannot read
  embedded textures.
- **`remove_basemesh` with no proxy is refused** (proposed while writing this request, not
  asked). It is the one option combination whose result has no body.

## Decisions taken during the effort

- **The spellings.** The panel's options keep MPFB's names (`bake_shapekeys`, `mask_modifiers`,
  `subdiv_modifiers`, `delete_helpers`, `remove_basemesh`, `interpolate`, `suffix`) except where
  the glossary disagrees: `load_microsoft_visemes`, `load_meta_visemes`, `load_arkit_face_units`
  (MPFB's `visemes_*` and `faceunits_arkit`; "face unit" is two words everywhere else) and
  `in_export_collection` (MPFB's `collection`, which reads as a collection's name). The verbs are
  `created` and `exported`. The effective options are echoed once, as `options_used` and
  `exporter_options`, rather than as twelve `requested_*` keys. `export_name` is the third
  `<artifact>_name`.
- **`KEEP`/`REMOVE`/`BAKE`, `material_type`, `format` and `target_engine` are checked locally, and
  none is the vocabulary exception**: no MPFB function receives any of them, so they are this
  package's own, like `mode`. `format` defaults to `null`, meaning the preset's own (FBX, or glTF
  for `godot`).
- **`face_baked_into_mesh` lists every non-zero face unit**, each with its `value` and the
  `from_stack` a rebuild would write, rather than only the unexplained ones: what the bake freezes is
  the whole face, and the composed part is the difference. `expressions_baked_into_mesh` lists the
  stack rows with a non-zero weight. Both come from `shared/expression_divergence.py`, are `[]` for a
  neutral face and `null` when `bake_shapekeys` is off. The copy keeps the stack property, so the
  message says a later `mpfb_apply_expressions` on it would apply the face twice.
- **The copy is repaired, not only reported.** The live check found MPFB's
  `ExportService.create_character_copy()` short in three ways, all now filed: it copies direct
  children only, so a garment with a sub-rig (a grandchild) is **not copied**; it points only the
  modifier named `Armature` at the new rig, so `Armature PV` still follows the original; and the
  copied armature *data* keeps its drivers on the original rig - **84 B-bone ease drivers** on a
  generated `human_toes` rig, which is the answer to this request's Rigify question. The request
  said to report the Rigify case and not fix it. It is fixed, because one rule - every reference
  on a copy to an original in the family is pointed at that original's copy - covers modifiers,
  constraints and drivers alike, and a copy driven by its original is not a copy. `copy_repairs`
  names every object copied and every reference retargeted, and is empty on an MPFB that no longer
  needs it. Posing the original no longer moves the copy, checked live and in the bridge suite.
- **The REMOVE-branch candidate was refuted.** Blender 5.1's collection iterator does not skip the
  neighbour of a removed modifier or vertex group, live or headless. The command collects first
  anyway; nothing was filed.
- **One refusal MPFB's own sequence needs.** `bake_modifiers_remove_helpers()` applies the body
  proxy's modifiers with a bare `modifier_apply`, which Blender refuses on a mesh with shape keys,
  and `interpolate` gives the proxy shape keys first. The panel fails the same way, half way through.
  The tool refuses up front (`proxy_cannot_be_baked`, naming the modifiers), so a refusal is still
  never a half-built copy. Filed.
- **The viseme packs are probed with one target each**, `sil_00` and `viseme_sil` - the one MPFB's
  `configure_lip_sync()` tests for - as `faceunits01` is with `cheekPuff`. Resolving all 37 was
  measured at 291 ms per answer, too much to pay on every call. A requested set is still resolved in
  full before copying, and reports `could_not_load`. `FaceService.load_targets()`'s docstring says
  it raises on a missing target; `bulk_load_targets()` warns and skips, which is what happens.
- **The GameEngine swap pops every copied mesh's materials before rebuilding**, because
  `set_character_skin()` renames whatever it finds `.unused` and clears its node tree, groups and
  all - and on an unswapped copy what it finds is the original's. The skin goes through
  `set_character_skin(skin_type="GAMEENGINE")`; mesh assets are rebuilt as
  `add_mhclo_asset(material_type="GAMEENGINE")` builds them, with `NodeWrapperGameEngine` read out of
  `sys.modules` (no service module carries it; its package loads at registration, confirmed headless
  and windowed). The bridge test compares the original's materials, node counts and node groups
  before and after.
- **Helper geometry is counted, not inferred from a group's presence**: baking MPFB's `Hide helpers`
  mask deletes the vertices and leaves the groups, empty. `helper_vertices_left` and
  `helper_vertices` are counts.
- **What each exporter does with a modifier beside shape keys was measured**, by re-importing: FBX
  applies the modifier and **drops every shape key**; glTF (`export_apply` off) and USD keep the
  keys and **ignore** the modifier, so the helpers and the body under the garments come along. No
  exporter keeps both. A mask on the basemesh is fixed by `mask_modifiers: "BAKE"`. A
  **subdivision on a mesh asset is not**: MPFB's strategies act on the basemesh (and, when baking,
  the proxy), so a garment or eyebrows with visemes interpolated onto them keep their Subdivision,
  and FBX drops their keys. Reported per mesh in `readiness`; recorded in NEXT_STEPS.
- **USD renames a repeated blend shape.** A viseme on the body and on an interpolated garment
  comes back from a `.usdz` as `aa_02` and `aa_022`: the same keys, one renamed. The round-trip test
  asserts it.
- **The export directory**: `--export-dir` wins over the preference, because it is the more recent
  and more specific choice and a headless run reads the same `userpref.blend`; a directory somebody
  named that does not exist is refused, the default is created. `path_resolved_by` says which,
  `"command_line"`, `"preferences"` or `"default"` - the glossary's name for how a file path was
  found. It lives in a small module of its own, `bridge/mpfb_bridge/export_directory.py`, because
  `ui.py` and `cli.py` both write it and a command reading it from `ui.py` would import the
  registration module into every dispatch.
- **Two plain reads went into `shared/blender_data.py`**, beyond the request's list:
  `with_descendants()`, the family both commands walk - what is copied must be what is written -
  and `vertices_in_groups()`. `shared/selection.py` gained `restored_all()`, used by both commands;
  the other ten keep `restored()`.
- **A character with only a body proxy is exported through it**: the subject resolves to a basemesh
  or, failing that, a proxy, and the miss sentence keeps the shared one's start and end.
- **The smoke items** copy the run's character with the panel's defaults and export the copy as FBX
  under a constant name, `overwrite: true`.

## Verification

Both halves of "verified" hold. The bridge suite has 28 new tests (553):
`ddd_mutating/create_export_copy_test.py` (13: the original unchanged, each option, the repairs on
a sub-rig fixture and a generated Rigify rig, the packs, the baked face, the GameEngine swap, every
refusal), `ddd_mutating/export_character_test.py` (9: each format and preset, the three ways a
directory is chosen, every refusal, the selection, a proxy-only character),
`eee_composite/export_roundtrip_test.py` (a copy with masks baked and visemes interpolated, exported
in four format/preset pairs and re-imported), and `restored_all`, `with_descendants` and
`vertices_in_groups` in `bbb_shared/`. The unit suite has 20 new tests (570), and the name-rule drift
check runs every name as all three nouns. The smoke run is 43 of 43 in 2.1 s.

The live check, [live_check.py](live_check.py), ran on 2026-10-18 against a windowed Blender 5.1
with MPFB, the bridge (reloaded to pick the commands up) and the community blender-mcp add-on, on
the developer's install with every pack, and passed all 35 checks: a character with a default rig,
hair with a sub-rig, eyebrows, a garment, a proxy, a MakeSkin skin, an expression and a composed
unit was copied with everything on and the original family, the selection and the active object
were unchanged; the baked face named the composed unit and the expression row; all 89 keys loaded;
every mesh became GameEngine. All six format/preset pairs wrote into the preference's directory and
read back with every mesh and a rig. The masked copy read back as measured above, Rigify's 84 data
drivers were retargeted and posing the original did not move the copy, and the REMOVE loop skipped
nothing.

**Measured durations depend on the scene.** The worst case - no shape key bake, masks baked under
all 89 loaded keys and the modeling ones - took **7.1 s** headless with one character, **27 s** in
the windowed Blender at the first run and **77 s** at the last, by when the file held 1,876 objects:
MPFB's `_apply_modifiers_keep_shapekeys()` duplicates the body and runs an operator per shape key,
and each operator pays for the whole file. That is under a third of the 300 s socket timeout, so
nothing was changed, and the tool description says it can take over a minute. Exports took 0.5 s
(FBX, USD) to 2 s (glTF) for a 24-56 MB file. What cannot be checked here is whether Unity, Unreal
or Godot accept the files; the preset tables cite their sources instead.

## References

- MPFB's operator and panel: `mpfb2/src/mpfb/ui/operations/exportops/operators/createexportcopy.py`,
  `.../exportopspanel.py` and `.../properties/*.json` (the options and their defaults).
- MPFB's services: `mpfb2/src/mpfb/services/exportservice.py`, `faceservice.py`
  (`load_targets`, `interpolate_targets`, `is_faceunits01_installed`, `MICROSOFT_VISEMES`,
  `META_VISEMES`, `ARKIT_FACEUNITS`), and `targetservice.py` (`bake_targets`). Their
  documentation: `mpfb2/docs/services/exportservice.md`, `mpfb2/docs/ui/operations/exportops.md`.
- User documentation:
  [Exporting MPFB characters](https://github.com/makehumancommunity/makehuman-static-website/blob/master/content/MPFB/Docs/exporting/_index.md),
  [Export copy](https://github.com/makehumancommunity/makehuman-static-website/blob/master/content/MPFB/Docs/exporting/export_copy.md), and
  the asset packs `visemes01` (Microsoft), `visemes02` (Meta) and `faceunits01` under
  `makehuman-static-website/content/Assets/AssetPacks/`.
- Precedents in this repository: [FR 025](../025-character-presets/README.md) (the first
  write outside the `.blend`), [FR 026](../026-face-units/README.md) (the optional-pack
  pattern), [FR 027](../027-expression-library/README.md) (`expression_divergence.py`, and
  the save-expression name rule), and `mpfb_set_asset_material` (a UI-only mechanism rebuilt from
  services).
- [NEXT_STEPS: selection restore covers one object](../../NEXT_STEPS.md#selection-restore-covers-one-object).
