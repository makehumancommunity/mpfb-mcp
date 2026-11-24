# Authoring a rig

**Status:** Proposed

This scopes [Rig authoring is outside the tool surface](../NEXT_STEPS.md#rig-authoring-is-outside-the-tool-surface)
and [Nothing in MPFB weights a new rig](../NEXT_STEPS.md#nothing-weights-a-new-rig), and the half of
[What a saved custom rig loses](../NEXT_STEPS.md#what-a-saved-custom-rig-loses) that a tool can report.
[A custom rig is unclassified for the posing tools](../NEXT_STEPS.md#a-custom-rig-is-unclassified-for-posing)
stays where it is (see Non-goals).

**An agent can apply a rig but cannot make one.** `mpfb_list_rigs` and `mpfb_add_rig` handle every rig in
the catalogue, `custom.*` ones included. Building one took `bpy.ops.mpfb.load_rig`,
`bpy.ops.mpfb.auto_transfer_weights`, `bpy.ops.mpfb.truncate_weights` and `bpy.ops.mpfb.save_rig_to_library`,
driven through the generic Blender MCP. That route works end to end: the 27-bone `claude_demo` rig was
written as a version-110 definition, loaded, weighted, saved, and refitted onto a second, deliberately
different body (left elbow at z = 1.140 on the first body and 0.992 on the second, 0 of 19,158 vertices
unweighted). The gap is reach, not feasibility.

**Reading MPFB while scoping found more than the entries say:**

- **`RigService.identify_rig` looks at custom rigs last and takes the first match.** It reaches them only
  when no built-in rig matched. It then walks them in `os.listdir` order, taking the first whose identifying
  bones are all present. A new rig whose identifying bones include another custom rig's set can therefore
  be saved with no warning and identified as the other rig. The other direction is just as silent. This
  library already holds four custom rigs (`claude_demo`, `gurgel`, `meh`, `yada`).
- **The loader reads only from a file.** `Rig.from_json_file_and_basemesh` takes a filename, and the
  position info it builds evaluates shape keys. The trap the NEXT_STEPS entry warns about (joint-cube
  centres from `mesh.vertices[].co` are centimetres off on a modelled body) is avoided by letting MPFB fit
  the bones, never by computing positions in a command.
- **Mask groups are rarer than the entry suggests.** Of MPFB's shipped weights files, only
  `rigify/weights.human_toes.json` carries any (`mhmask-preserve-volume`, `mhmask-no-smooth`). None of the
  `standard/` rigs' weights files does. So a custom rig that cannot carry masks is unlike one shipped rig,
  not "the built-in rigs" as a whole.
- **Weight symmetry is unimplemented in MPFB.** `RigService.symmetrize_all_bone_weights` walks the bones
  and calls two mirror methods that do nothing. The vertex mirror table it would need already exists:
  `TargetService` loads `mesh_metadata/hm08.mirror` for `symmetrize_shape_key`.

## Goals

**Primary:** an agent can make a rig other characters can use, without a panel or a selection. It can
describe a skeleton against the base mesh's joints, put it on a character, weight it, and store it in the
user library as a `custom.*` rig that `mpfb_add_rig` applies and `identify_rig` recognises.

**Secondary:**

- **Every rig can be read in the shape the builder takes**, so a shipped rig can be the starting point and
  a read-back is a write, as with poses.
- **Weighting is good enough to pose**, with helper geometry covered. That way a rig does not look right
  only until eyes, hair or a garment are equipped.
- **A rig derived from a shipped one inherits its weights**, through a transfer that understands merged
  chains. MPFB's transfer understands only renames.
- **A stored rig is found as itself**: the store refuses an identification that would collide.

## Non-goals

- **Classifying a custom rig for the posing tools.** It stays in NEXT_STEPS. `mpfb_set_pose_bones` already
  works on an unclassified rig, so only the reading side is blind.
- **Sub-rigs for garments** (MakeRig's `rig_subrig`), and **Rigify meta-rigs**. Both rest on MakeRig's
  developer path, but each has its own consumers and failure modes.
- **Constraints, IK, bendy bones and Rigify parameters in the builder.** It builds a deform skeleton. The
  reader reports what a read rig carries beyond that, so a rig derived from one loses it knowingly.
- **A `use_deform` key in the rig format.** That was decided against (see Decisions): the store reports
  the loss, and the key is filed upstream.
- **Hand weight painting**, writing a weights file to an arbitrary path, and removing a rig from the
  library.
- **Fixing MPFB.** What this request provokes gets filed (see Tests).

## Functional requirements

### `mpfb_get_rig_definition`: a rig, read as a bone table

1. **`name`** is the character. By default the tool reads the rig that moves it. Given **`rig`**, a
   catalogue identifier from `mpfb_list_rigs`, it instead fits that definition **in memory** to this
   character's body and reads it. Nothing is created in the scene. FR 9's transfer needs the same in-memory
   fit.
2. Each bone is reported in **exactly the shape `mpfb_create_rig` takes** (FR 5): `name`, `parent`,
   `head`, `tail`, `roll`, `deform`, `connect` and `collections`. Each end also carries its resolved
   `position` in the character frame, which the builder ignores on input. MPFB's `DEFAULT` and `XYZ`
   strategies have no builder form. They are reported as they are, with `expressible: false`.
3. **`features_not_carried`**, per bone, names what the builder would drop: constraints, bendy bones,
   Rigify parameters, custom properties. The rig-level `rig_identified_as` and `version` come with it.
4. **`include_joints`** (default false) adds every joint cube by name, with its centre in the character
   frame, **evaluated as MPFB evaluates it at fit time** (shape keys included). This is the vocabulary the
   builder's `joint` takes. With the joints, a shipped rig's bones answer at around 25 KB, so `bones`
   (names) and `compact` (no `position`, no `features_not_carried`) narrow the answer. The default answer
   is held under the size budget of the read-only tools.

### `mpfb_create_rig`: a bone table, built onto a character

5. **`bones`** is a list, **resolved in full before anything is built**, all or nothing. Each entry has a
   `name`, a `parent` (empty or another entry's name), and a `head` and a `tail`. Each end is exactly one
   of:
   - `joint` (a joint cube name);
   - `vertex` (an index);
   - `mean` (two or more indices);
   - `position` (`forward`/`left`/`up`, metres, in the character frame). This **snaps by default** to the
     nearest joint within MPFB's own `_MAX_ALLOWED_DIST`, else to the nearest vertex, and reports what it
     snapped to. With `snap: false` it stays a fixed position, which will not follow a refit, and the
     answer says so.

   Any end may carry an `offset` in the same frame. Further optional fields are `roll`
   (`align_z_world_z`, `align_x_world_x` or `degrees`), `deform` (default true), `connect` and
   `collections`.
6. **The character must have no rig**, else `blocked_by: "already_rigged"`. **`replace: true`** rebuilds
   over a rig that was built by this tool or identified as `unknown`. A shipped or library rig is refused
   (`rig_not_authored`). On a rebuild, the vertex groups of bones whose name and both strategies are
   unchanged are **kept**, and the rest are dropped. Both are listed (`weights_kept`, `weights_dropped`).
7. **MPFB fits the bones** (`Rig` and `create_armature_and_fit_to_basemesh(for_developer=True)`), so the
   strategies are stored on the bones the way MPFB's save expects them. The armature modifier and
   parenting are done as `mpfb_add_rig` does them. That includes moving a turned basemesh's rotation to the
   rig.
8. The answer has the bones with resolved positions, a `snapped_to` per snapped end, and
   `ends_not_following_body`. Every asset already equipped is named in `assets_not_rigged`, since nothing
   rigs an asset after the fact. `next_with` points at `mpfb_weight_rig`.

### `mpfb_weight_rig`: weights for an authored rig

9. **`method`** is required, and takes one of three values:
   - **`automatic`**: Blender's heat weighting (`parent_set(type='ARMATURE_AUTO')`) over the deforming
     bones, with the parenting, the modifier stack and the selection put back afterwards. **`exclude_bones`**
     names bones to leave out of the pass, `root` being the usual one. They are set non-deforming, and the
     answer says so.
   - **`transfer`**, from **`from_rig`**, a catalogue identifier. That rig is fitted to this body in memory
     (FR 1), and its weights file is read via `shared/rig_lookup.py`, so `default_no_toes` takes `default`'s,
     as `mpfb_add_rig` would. Weights are per base-mesh vertex index, so nothing is interpolated between
     meshes. Each target bone reports `matched_by`:
     - `exact`: both ends within 1 mm of one source bone, as in MPFB's operator.
     - `chain`: its head on a source bone's head and its tail on a descendant's tail along one chain. The
       chain's weights are summed. This is `upperarm.L` taking `upperarm01.L` and `upperarm02.L`.
     - `ancestor`: a source bone that no target bone covers gives its weights to the target bone matched by
       its nearest matched ancestor. This keeps each vertex's total, for example fingers into `hand.L`.
     - `none`.

     The answer also gives the nearest miss and its distance for every `none`.
   - **`mirror`**, with a required **`direction`** (`left_to_right` or `right_to_left`, as
     `mpfb_symmetrize_targets` takes it). The weights are copied through `hm08.mirror`. Bones are paired by
     side suffix (`.L`/`.R`, `_l`/`_r`), and a centre bone is mirrored onto itself. A bone with no partner is
     named, not guessed.
10. **`fill_unweighted`** (default true, ignored by `mirror`) runs after the pass. Every base-mesh vertex
    with no deform weight takes the weights of the nearest **body** vertex. The answer counts the vertices
    before and after, split into `body`, `helper` and `joint_cube`. A non-zero `body` count before the fill
    is the one that means the pass itself went wrong.
11. **`bones`** (optional) limits the pass to those bones. The vertex groups it writes are replaced, and
    every group it replaced that it had not itself written is listed (`groups_replaced`), per [a tool that
    destroys state it did not create](../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list).
    The rig must be at rest (`rig_not_at_rest`). Per bone, the answer gives `vertex_count`, so a root that
    took the thighs is visible without a render.

### `mpfb_store_rig`: an authored rig, into the user library

12. **`rig_name`** follows MPFB's rule (`^[a-zA-Z0-9_]+$`), checked on both sides of the socket over one
    table of names. The tool writes `rigs/<rig_name>.json` and, unless `include_weights: false`,
    `weights.<rig_name>.json` in MPFB's user data. Both are staged and moved as one artifact. MPFB's custom
    rig cache is then invalidated, so `mpfb_list_rigs` and `mpfb_add_rig` see the rig at once.
    **`overwrite`** is false by default, there is a **`dry_run`**, and `path` is in every answer, per [a tool
    whose effect is outside the `.blend`](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more).
13. **`identifying_bones`** is optional. When it is left out, the command picks the smallest set of the
    rig's bones that no built-in rig and no installed custom rig has, and reports it.
14. **Identification is settled before writing.** The tool refuses in three cases:
    - a built-in rig would claim the armature (`identified_as_builtin`), since built-ins are checked first;
    - another custom rig's identifying bones are all present in this one (`identification_shadowed`, with
      `shadowed_by`), since list order then decides;
    - this rig's identifying bones are all present in another custom rig (`would_shadow`).

    It also refuses a same-named rig in another data root (`name_shadowed`).
15. **Masks are excluded by default**, as MPFB's panel excludes them. **`include_masks: true`** writes the
    body's `mhmask-*` groups. The answer always gives `masks_on_body` and `masks_written`, so an author
    can see what was left out either way.
16. **What the round trip loses is reported.** `deform_flags_lost` names every non-deforming bone that will
    come back deforming. `features_not_carried` comes from FR 3. `unweighted_bones` lists deforming bones
    with no group. `try_with` is the recipe to try the rig on a different body: `mpfb_create_human`, then
    `mpfb_add_rig` with `custom.<rig_name>`.

### Documentation

17. The four descriptions carry the order (create, weight, store, then `mpfb_add_rig` elsewhere), and the
    server instructions gain one sentence for it in the authoring line.

## Non-functional requirements

- **Correct positions on a modelled body.** No command computes a bone or joint position from
  `mesh.vertices[].co`. Every position comes from MPFB's own position info, which evaluates shape keys. A
  bridge test holds this on a body where the two differ.
- **All-or-nothing writes.** `bones` and `exclude_bones` resolve in full before the first write, per
  [what the all-or-nothing batches caught](../NEXT_STEPS.md#what-the-all-or-nothing-batches-caught). A
  build that fails part way removes its armature.
- **Readability.** The translation between the bone-table shape and MPFB's format is one module, used in
  both directions. A disagreement between reader and builder would break the read-back-is-a-write claim.
- **Description budget.** Four descriptions are what an MCP client downloads before any work happens.
  `tests/test_description_budget.py`'s ceilings are raised only by what these four measure, and the server
  instructions stay under FR 059's 4,000 characters.

## Architecture

- **Four tool modules and four commands**, named as usual: `get_rig_definition`, `create_rig`, `weight_rig`
  and `store_rig`. They are `create` rather than `add`, because `mpfb_add_rig` applies a catalogue entry.
- **One new shared module, `shared/rig_definition.py`.** It holds the bone-table shape in both directions,
  the in-memory fit (FRs 1 and 9), and the joint-cube reading (FR 4). Three commands use it, which meets
  the [shared-module rule](../../specifications/architecture.md#shared-modules-and-what-warrants-one). It
  builds a `Rig(basemesh)`, assigns `rig_header` and `rig_definition`, and calls
  `build_basemesh_position_info()`. It does not write a temporary file for `from_json_file_and_basemesh`.
  The upgrade step that function runs is version-gated and a no-op for a version-110 dictionary. That claim
  is checked by a bridge test rather than assumed.
- **MPFB's operators are reimplemented, never called**, per
  [mpfb-integration.md](../../specifications/mpfb-integration.md#a-third-party-add-ons-ui-operators-are-reimplemented-never-called).
  `save_rig_to_library`'s body is `Rig.from_given_armature_context`, `RigService.get_weights` and two
  `json.dump`s. Transfer replaces `auto_transfer_weights` rather than reproducing it. The departures are
  listed in the command docstrings, as FR 050 listed MakeClothes'.
- **Heat weighting is a Blender operator, not MPFB's.** It needs an object-mode context with exactly the
  body and the rig selected. It reparents and adds a modifier, both of which are put back. The operator
  reports "failed to find solution" through the window manager only, so a bone that got nothing is found
  by counting the groups, not by reading a report.
- **`shared/rig_lookup.py`** already predicts which weights file a rig loads. Transfer uses it, so it
  cannot disagree with `mpfb_list_rigs` or `mpfb_add_rig`.
- **Pitfall: helper shells and joint cubes.** Heat weighting fails on the disconnected interior shells,
  which is why the fill exists. It finds the nearest *body* vertex with a KD-tree over the vertices outside
  every `helper-*` and `joint-*` group, evaluated in rest position.
- **Pitfall: the root.** A bone from `joint-ground` to `joint-pelvis` takes the thighs under heat
  weighting. `exclude_bones` is where the caller says so. After a library round trip, the flag no longer
  protects against re-weighting, so `mpfb_weight_rig` names, in its answer, any deforming bone whose head
  sits on `joint-ground`.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog): the Authoring area gains rigs (seven
  tools become eleven), and the "what makes something a tool" reasoning gains a rig as the second kind of
  authored asset.
- [tool-interface.md](../../specifications/tool-interface.md#the-glossary): the bone-table shape and the
  end kinds (`joint`, `vertex`, `mean`, `position`, `offset`, `snap`), `matched_by`, the fill counts, and
  the store's refusals.
- [mutating-tools.md](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more):
  the sixth tool to write outside the `.blend`, and the first refusal that is about **identification**
  rather than about a name. The `name_shadowed` paragraph gains its sibling.
- [mpfb-integration.md](../../specifications/mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not):
  MakeRig's departures, next to MakeSkin's and MakeClothes'. It also gets the mask default and what it rests
  on.
- [testing.md](../../specifications/testing.md): no new rule is expected.

## Tests

- **Unit, this side**, shape only. Distinct bone names, a parent that is another entry, no cycle, exactly
  one end kind, finite numbers, `offset` and `position` as frame objects, known keys (`tial` refused),
  `method` and `direction` as this package's own vocabularies, and `rig_name` over the table both sides
  share. **No joint, bone or rig vocabulary is checked here.**
- **Bridge, `bbb_shared/rig_definition_test.py`**: a shipped rig's definition, read and then rebuilt, gives
  the same strategies. Positions on a modelled body differ from `vertices[].co`, and the in-memory fit
  creates no object.
- **Bridge, `ccc_reading/` and `ddd_mutating/`**: one module per command. Every refusal; the rebuild's kept
  and dropped groups; `exact`, `chain` and `ancestor` measured against `default_no_toes`, on a reduced rig
  whose answers are known; the mirror against a deliberately one-sided weighting; the fill's counts; the
  store into a temporary user data root, with each identification collision built from two small rigs.
- **Bridge, `eee_composite/rig_roundtrip_test.py`**: create, weight, store, then `mpfb_add_rig custom.*` on
  a different body. That rig is identified as itself, and its `mpfb_get_rig_definition` equals the table it
  was built from.
- **Live, `060-authoring-rigs/live_check.py`**: the `claude_demo` session again, through the four tools.
  The elbow is refitted on the second body, 0 vertices are unweighted after the fill (1,384 before it), a
  90-degree elbow and shoulder bend are read through `mpfb_get_pose`, and transfer is compared against
  MPFB's own operator on the same pair. That last check is the 8 matched and 19 unmatched, which `chain` and
  `ancestor` should bring to 0.
- **Smoke**: one item per tool. The store's runs as `dry_run`, so the smoke still writes only its three
  files and the library does not gain a rig on every run.
- **Upstream**, against the mpfb2 templates and only once confirmed against a running install:
  - a feature request for `use_deform` in the rig format, with the loader defaulting it to true;
  - a feature request for a masks checkbox on save-to-library, like `save_masks` on the other save path;
  - a defect report for `identify_rig`'s first-match over an unordered directory listing, if a collision
    is provoked.

## Decisions taken while scoping

Asked on 2026-11-24:

- **Four tools, a reader among them**, not the entry's three, so that a shipped rig can be the starting
  point and a read-back is a write.
- **`use_deform`: upstream only.** The store names what will come back deforming (FR 16). The format is
  not extended here, and `mpfb_add_rig` is not changed.
- **Transfer and mirror weighting are in scope. Posing classification and sub-rigs are not.**
- **Whether excluding masks is deliberate was left to the scoping.** The finding: `all_masks=False` has
  been in `savetolibrary.py` since the commit that introduced custom rigs (`6ad303c7`, "First draft of
  custom rigs support"), with no comment. `get_weights` defaults it to true, and MakeRig's other save path
  exposes it as `save_masks`. Only one shipped rig carries masks. So the request **keeps MPFB's default and
  adds the opt-in** (FR 15). An `mhmask-*` group on an authoring body is as likely to be left over from a
  rig that body once had as to be chosen. Including it by default would ship a preserve-volume modifier the
  author never asked for. Whether a stray mask can outlive its rig is a question for the live check, and
  its answer goes into the upstream feature request.

*Not asked*, each argued where it is stated: snapping `position` by default (FR 5); refusing a collision
rather than warning, as MPFB does (FR 14); picking identifying bones when none are named (FR 13); `mirror`
as a method rather than a flag, so that a weighting and its mirror are two answers (FR 9).

## References

- NEXT_STEPS: [Rig authoring is outside the tool surface](../NEXT_STEPS.md#rig-authoring-is-outside-the-tool-surface),
  [Nothing in MPFB weights a new rig](../NEXT_STEPS.md#nothing-weights-a-new-rig),
  [What a saved custom rig loses](../NEXT_STEPS.md#what-a-saved-custom-rig-loses).
- mpfb2: `entities/rig.py` (`from_json_file_and_basemesh`, `create_armature_and_fit_to_basemesh`,
  `build_basemesh_position_info`, `from_given_armature_context`); `services/rigservice.py` (`get_weights`,
  `apply_weights`, `identify_rig`, `symmetrize_all_bone_weights`); `services/assetservice.py`
  (`get_custom_rigs`, `invalidate_custom_rig_cache`); `services/targetservice.py` (`_load_mirror_table`);
  `ui/create_assets/makerig/operators/` and `ui/create_assets/makeweight/operators/`.
- mpfb2 docs: `docs/fileformats/rig.md` and `docs/fileformats/weights.md`. Write against the code, not
  those pages: see `mpfb2/efforts/bugs/local/rig-authoring-docs-mismatches.md`, `truncate-weights-wipes-group.md`
  and `symmetrize-weights-not-implemented.md`.
- [FR 050](../done/050-writing-mesh-assets/README.md), the pattern for an authored asset written whole into
  the library with a `try_with`.
