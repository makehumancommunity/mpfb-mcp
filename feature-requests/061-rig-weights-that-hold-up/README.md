# Rig weights that hold up, measured

**Status:** Proposed

This follows [FR 060](../060-authoring-rigs/README.md) on
[Nothing in MPFB weights a new rig, and automatic weights miss the helpers](../NEXT_STEPS.md#nothing-weights-a-new-rig).
FR 060's `mpfb_weight_rig` gets an authored rig weighted at all: heat weighting, a transfer that understands
merged chains, a mirror, and a fill for every vertex the pass missed. This request is about whether those
weights are **right**, and about saying so with numbers rather than a render. It changes two behaviours of
`mpfb_weight_rig`, adds a cleaning step, and adds one read-only tool.

**Reading MPFB's shipped weights and Blender's heat weighting while scoping found:**

- **A nearest-body-vertex fill puts the eyes on the eyelids.** In `weights.default.json`, each eyeball
  helper (72 vertices) is 100% `eye.L`/`eye.R`. The lower teeth are 100% `jaw`, the upper teeth 100% `head`,
  and the tongue is spread over the tongue bones. The body vertex nearest an eyeball is on the eyelid, which
  that rig weights to `orbicularis03`/`04`. A filled eye would therefore close with the lid and never turn.
  The eyelash, hair, genital, skirt and tights helpers *are* weighted as their nearest skin is, and the fill
  suits them.
- **Heat weighting tests line of sight against the whole mesh.** `heat_ray_source_visible`
  (`blender/source/blender/editors/armature/meshlaplacian.cc`) casts a ray from each vertex to the closest
  point on each bone, through a BVH of every triangle. The base mesh carries 125 joint cubes
  (1,000 vertices) sitting exactly on the bone ends. It also carries 4,778 helper vertices, including the
  eyes, teeth and tongue inside the head. Interior geometry can hide a bone from the skin it should weight.
  Whether that happens here has not been measured.
- **Heat weighting fits the body it runs on, but a weights file is reused on every body.** `claude_demo`
  was weighted on the authoring character as modelled, and its file then loaded onto a male, old, heavy,
  short body. Weights are per base-mesh vertex, so they carry over without interpolation. They also carry
  whatever proportions the authoring body had.
- **The shipped files disagree about influences and normalisation:**
  - **Influences.** `default` has up to 8 influences per vertex, with 4,025 vertices over 4.
    `rigify/human_toes` has up to 11. Even `game_engine` has 981 vertices over 4.
  - **Normalisation.** Three files are unnormalised: `mixamo` (9,858 vertices), `mixamo_unity` (2,562) and
    `openpose` (12,293, with totals up to 3.77). `game_engine_with_breast` is unnormalised on 751 vertices.
  - **Where it shows.** Blender normalises at deform time (`armature_deform.cc`), so none of this is
    visible in Blender. It is visible to an engine that takes weights as given, and in any comparison of
    two rigs' files.
- **Nothing in MPFB reads a weighting back.** MakeWeight's Truncate empties the group
  ([`truncate-weights-wipes-group.md`](../../../mpfb2/efforts/bugs/local/truncate-weights-wipes-group.md)), and
  its symmetrize does nothing
  ([`symmetrize-weights-not-implemented.md`](../../../mpfb2/efforts/bugs/local/symmetrize-weights-not-implemented.md)).
  The only evidence that the NEXT_STEPS weights "hold up" is a 90-degree bend, looked at in a render.

## Goals

**Primary:** an authored rig's weights are good enough to animate on any body, including the helper
geometry that garments, hair and eyes are fitted to. An agent can tell whether they are by measuring, not
by looking.

**Secondary:**

- **Weights authored on any character are the same weights.** The authoring body's proportions do not
  leak into a file meant for every body.
- **There is one reading of a weighting.** The tool that writes weights, the tool that checks them and the
  store all use it, so the three cannot disagree.
- **A shipped rig is measurable with the same tool**, so it can be the baseline a custom rig is compared
  against.
- **Influences can be capped and normalised for an engine** without MPFB's Truncate.

## Non-goals

- **Re-weighting a shipped or library rig.** `mpfb_weight_rig` keeps FR 060's scope, which is authored rigs
  only. The report reads every rig.
- **A verdict.** The report measures; deciding what is good enough is the caller's job, done against a
  shipped rig's numbers, as `mpfb_check_intersections` leaves it.
- **Corrective shape keys, dual-quaternion skinning, and a preserve-volume setup.** The bend test reports
  what the armature modifier does with these weights, as it is configured. FR 060's `include_masks` covers
  what a stored rig carries for preserve volume.
- **Capping influences at export.** That stays with the exporters and with
  [FR 039](../done/039-exporting-characters/README.md)'s engine presets. A cap applied here goes into the
  library file and so reaches every body.
- **Hand weight painting and smoothing brushes.**
- **Fixing MPFB.** What this request provokes gets filed (see Tests).

## Functional requirements

### Changes to `mpfb_weight_rig` (FR 060's FRs 9 to 11)

1. **`automatic` weights the neutral base mesh, never the character as modelled.**
   1. The command builds a temporary copy of the base mesh with no shape keys. It fits the rig to that copy
      through FR 060's fit, so the `CUBE`, `VERTEX` and `MEAN` ends land where they would on an unmodelled
      body.
   2. It heat-weights the copy and writes the groups back to the character by vertex index.
   3. It removes both temporaries and their data blocks.

   The answer carries `weighted_on: "neutral_base_mesh"`. It also names every end that does not follow the
   body, which is FR 060's `position` with `snap: false`. Such an end sits at the same coordinates on the
   neutral body, which is not necessarily where the author meant it.
2. **Exactly one heat pass ships, and the live check chooses it** (Tests). The two candidates are a pass
   over the skin only (the `body` group, with helpers and joint cubes removed from the temporary copy) and
   a pass over the whole mesh. The pass that loses is not kept behind an argument.
3. **The fill applies a rule per helper**, taken from one table keyed by MPFB's group names:
   - **`rigid`**: the eyes and both sets of teeth.
     - **What it does:** the whole helper goes to one deforming bone at weight 1.0.
     - **Candidates:** the deforming bones whose head is on the helper's anchor joint. An eye's anchor is
       `joint-l-eye` or `joint-r-eye`, and the lower teeth's is `joint-mouth`. The upper teeth have no
       anchor.
     - **The choice:**
       - one candidate is chosen outright;
       - among several, the one whose name carries the anchor's word (`eye`, `jaw`) is chosen;
       - otherwise the choice falls to `nearest_dominant`: the bone carrying the most weight over the
         helper's nearest body vertices.
     - **On `default`**, this picks `eye.L` over `orbicularis03.L`/`04.L`, `jaw` over `special03`, and
       `head` for the upper teeth.
     - **`helper_bones`** (optional, `{helper group: bone}`) overrides any of these choices. Per helper,
       the answer gives the bone, `chosen_by` and the other `candidates`.
   - **`interior_chain`**: the tongue. Each vertex blends the two nearest deforming bones that lie wholly
     inside the tongue helper's bounds, weighted by distance. With no such bone, the tongue follows the
     lower teeth's bone as a whole.
   - **`nearest`**: the eyelashes, hair, genital, skirt and tights helpers, the joint cubes, and any helper
     group the table does not name (which the answer reports). Each vertex takes an inverse-distance blend
     of its `k` nearest body vertices' weights. `k` is a named constant that the live check settles. The
     skirt decides it: it hangs between the legs, so with `k = 1` it splits down the middle.

   FR 060's fill counts stay (`body`, `helper` and `joint_cube`, before and after). The answer adds
   `helpers`: per group, the `rule`, the `bone` or `bones`, and the `vertex_count`.
4. **Every method ends by cleaning.** Each vertex's deform weights are normalised to 1.0. Two arguments
   control the rest:
   - **`min_weight`** (default 0.0001, MPFB's `exclude_weights_below`) drops weights below it;
   - **`max_influences`** (optional, a positive count, no cap by default) keeps each vertex's largest
     weights.

   A fourth method, **`clean`**, applies only this step to the existing weights. **Only the groups of
   deforming bones are touched.** `mhmask-*`, `helper-*`, `joint-*` and every other group that is not a bone
   are never counted, trimmed or normalised.

   The answer gives the influence histogram before and after, `vertices_trimmed`, `vertices_normalised` and
   `max_weight_removed`. The last of these says whether a cap of 4 cost anything visible. Normalising
   rescales groups the pass did not otherwise write, so those are listed as **`groups_rescaled`**, beside
   FR 060's `groups_replaced`.
5. `next_with` points at `mpfb_check_rig_weights` instead of going straight to `mpfb_store_rig`.

### `mpfb_check_rig_weights`: a weighting, measured

6. **`name`** is the character. The tool reads the weights of whichever rig moves it, shipped, library or
   authored, so a shipped rig on a similar body can serve as the baseline. It changes nothing. The `bend`
   section puts back what it moves (FR 11).
7. **`sections`** narrows the answer, as in `mpfb_check_mesh_asset`. Every section except `bend` is on by
   default:
   - **`coverage`**: unweighted vertices, split into `body`, each helper group, and `joint_cube`. It also
     lists `unweighted_bones` (deforming bones with no group) and `orphan_groups` (groups named after no
     deforming bone).
   - **`influences`**: the histogram of influences per vertex and `max_influences`. It also counts the
     vertices whose total is outside 1 ± 0.01, keeping the worst.
   - **`bones`**: per deforming bone, `vertex_count`, `weight_sum` and `reach`. `reach` is the farthest any
     vertex weighted above a threshold sits from the bone's segment. `far_vertices` counts the vertices
     beyond a limit relative to the bone's length, which is how a root that took the thighs shows up
     without a render. The list is capped largest first, with totals that cover the cut.
   - **`helpers`**: per helper group, the dominant bone and its share, and `rigid` (one bone at 0.99 or
     more). An eye on its eyelid shows here.
   - **`symmetry`**: per `.L`/`.R` pair, the largest and mean weight difference between mirrored vertices,
     through `hm08.mirror`. Bones with no partner are named, and the worst pairs are kept.

   All thresholds and limits are named constants.
8. **One reading.** `mpfb_weight_rig`'s counts and FR 060's `unweighted_bones` in `mpfb_store_rig` come from
   the same module as these sections, so a character weighted and then checked gets the same counts twice.
9. **No verdict.** The description says to compare against a shipped rig on a similar body.

### The bend test

10. **`bend`** is opt-in. It poses a fixed set of movements one at a time from rest, and measures each one
    on the evaluated base mesh:
    - **The movements:** elbow and knee flexed 90°, shoulder abducted 90°, hip flexed 90° and abducted 45°,
      wrist flexed 60°, neck turned 45°, and spine bent 30°.
    - **The axes** come from a table in the **character frame**, derived from the parent bone's rest
      direction and the frame's axes. They are never taken from the moved bone's local axes, so a custom
      rig's roll cannot change what is tested.
    - **The bone moved** is the deforming bone whose head sits on that joint's cube (`joint-l-elbow` and
      so on). Several candidates are resolved as the rigid helpers' are.
    - **A joint with no such bone** is reported as `not_tested`.
11. **Four measurements per movement**, taken over the region within a radius of the joint (a named
    constant scaled by the bone's length):
    - **`collapse`**: the region's mean distance to the bone line, bent divided by rest. Values under 1.0
      mean pinching or candy-wrapping.
    - **`edge_stretch`**: the 99th-percentile and maximum ratio of edge length, bent to rest.
    - **`self_intersections`**: face pairs in the region that intersect, counted through
      `shared/mesh_overlap.py`.
    - **`stray`**: vertices that moved more than 1 mm but lie farther than the reach limit from every bone
      in the moved chain. A left elbow that moves the torso is counted here.

    The armature modifier's `use_deform_preserve_volume` is reported beside the numbers, since it changes
    them.
12. **Measured clean and put back exactly.** Every modifier except the armature is off for the
    measurement, masks included, as in `mpfb_check_intersections`. The pose goes back through
    `shared/pose_writing.py`. A rig that is not at rest is refused (`rig_not_at_rest`), and so is a base
    mesh with no armature modifier.

### Documentation

13. **`mpfb_weight_rig`'s description** gains the helper rules and `clean`.
14. **`mpfb_check_rig_weights`' description** says to compare against a shipped rig.
15. **The server instructions' authoring line** puts `mpfb_check_rig_weights` between weighting and storing.

## Non-functional requirements

- **Positions come from the right body.** The report and the bend test read the character at rest with its
  shape keys evaluated, which is the body that will be posed. The automatic pass reads the neutral copy,
  where `vertices[].co` is correct by construction. This is the only exception to FR 060's rule, and a
  bridge test holds both halves.
- **Nothing is left behind.** The temporaries and their meshes, armatures and objects are removed. The bend
  test restores the pose, modifiers, selection, mode and frame. A bridge test compares the `bpy.data`
  counts before and after.
- **Size and time.** The default answer (no `bend`) stays inside the read-only tools' size budget. The live
  check measures the bend section's time on `default`, and the description states it.
- **Description budget.** One new description and two longer ones. `tests/test_description_budget.py`'s
  ceilings are raised only by what they measure, and the server instructions stay under FR 059's
  4,000 characters.

## Architecture

- **The tool and its command.** There is one new tool module and one new command, `check_rig_weights`. The
  existing change is to FR 060's `weight_rig` command.
- **One new shared module, `shared/rig_weights.py`.** It holds:
  - the deform-only reading of a weighting, which is the one place that decides what counts as a bone
    weight;
  - the coverage, influence, bone, helper and symmetry readings;
  - `clean`;
  - the helper rule table and its fill.

  `weight_rig`, `check_rig_weights` and `store_rig` use it, which meets the
  [shared-module rule](../../specifications/architecture.md#shared-modules-and-what-warrants-one). The bend
  test has one user and stays in its command. That command imports `pose_writing.py`, `mesh_overlap.py`
  and `character_frame.py`.
- **The group vocabulary is MPFB's.** `helper-*`, `joint-*` and `body` come from
  `mesh_metadata/basemesh_vertex_groups.json` as MPFB reads it, never from a list here. A helper group the
  rule table does not name falls to `nearest`, and the answer reports it.
- **The mirror table** is `TargetService._load_mirror_table`, which is private. It is read through
  `shared/mpfb_surface.py`, the same way FR 060's `mirror` reads it.
- **The neutral copy, in order:**
  1. Copy the base mesh without shape keys.
  2. Fit the armature to it while the joint groups still exist.
  3. Stamp each vertex's original index into a temporary integer attribute.
  4. Remove the non-skin vertices, if the skin-only pass is the one that ships.
  5. Run the heat pass, using the same context handling as FR 060.
  6. Map the groups back through the attribute.
  7. Remove everything.
- **The rigid candidates are not geometric.** On `default`, `eye.L`, `orbicularis03.L` and
  `orbicularis04.L` all have their head on `joint-l-eye`, and `jaw` and `special03` both have theirs on
  `joint-mouth`. No distance rule separates them, which is why the name tie-break and `helper_bones` exist.
  A joint with a candidate comes from the bone's stored `CUBE` strategy, through `shared/rig_definition.py`,
  and not from a distance test.
- **Pitfall: normalising a mask breaks it.** The mask modifiers MPFB reads from `mhmask-*` groups depend on
  their exact values. The deform-only filter is the module's single entry point, and a bridge test equips
  masks and checks they come through `clean` unchanged.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog): Authoring gains one more tool beyond
  FR 060's four.
- [tool-interface.md](../../specifications/tool-interface.md#the-glossary): the fill rules (`rigid`,
  `interior_chain`, `nearest`), `chosen_by`, `clean`, `min_weight` and `max_influences`, the report's
  sections, and the bend measurements.
- [mutating-tools.md](../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list):
  `groups_rescaled` is a second kind of change to state the call did not create, alongside
  `groups_replaced`.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): MakeWeight's Truncate and symmetrize are
  replaced, not called. The group vocabulary is taken from MPFB's file, and the mirror table is read
  through a private name.
- [testing.md](../../specifications/testing.md): no new rule is expected.

## Tests

- **Unit, this side**, shape only:
  - `method` gains `clean`;
  - `max_influences` is a positive count and not a `bool`;
  - `min_weight` is finite and in [0, 1);
  - `helper_bones` is an object of non-empty strings;
  - `sections` are distinct known names, read from the bridge as data.

  **No bone or helper vocabulary is checked here.**
- **Bridge, `bbb_shared/rig_weights_test.py`**, against the shipped files, where the answers are known:
  - `default`: 0 unweighted, at most 8 influences, normalised, rigid eyes, near-zero asymmetry;
  - `mixamo`: exactly 9,858 unnormalised;
  - the rigid choices on `default` (`eye.L` by name, `jaw` by name, `head` by `nearest_dominant`);
  - `clean` on groups with a known result;
  - masks left unchanged.
- **Bridge, `ddd_mutating/weight_rig_test.py`**, added to FR 060's module:
  - two differently modelled characters carrying one authored rig get the same groups from `automatic`
    (the claim behind FR 1);
  - the `bpy.data` counts are unchanged afterwards;
  - `groups_rescaled` is reported.
- **Bridge, `ccc_reading/check_rig_weights_test.py`**:
  - the tool is read-only, `bend` included;
  - `far_vertices` and `stray` catch a deliberately bad weighting (thigh vertices put on a root);
  - an eye put on its eyelid shows as not `rigid`;
  - a rig with no elbow bone gives `not_tested`.
- **Bridge, `eee_composite/`**: weighting and then checking gives the same counts, and so does the store.
- **Live, `061-rig-weights-that-hold-up/live_check.py`**, on `claude_demo` and on the shipped `default` and
  `game_engine` as baselines on the same body:
  1. **Skin-only against whole-mesh heat** (FR 2): unweighted body vertices, then the bend numbers. Pick
     one.
  2. **Neutral against modelled authoring**: how much the groups differ, and the bend numbers on a third
     body.
  3. **`k` for `nearest`**: the skirt with the hips abducted.
  4. **`clean` to 4 influences on `default`**: `max_weight_removed`, and the bend numbers before and after.
  5. **The bend section's time.**
- **Smoke**: one item, `mpfb_check_rig_weights` with default arguments and no bend.
- **Upstream**: nothing is expected. The unnormalised shipped files are harmless in Blender. They are
  filed, as an mpfb2 feature request, only once an export is seen to pass them on.

## Decisions taken while scoping

Asked on 2026-11-24:

- **A follow-up to FR 060, not a split.** FR 060 keeps `mpfb_weight_rig`, and this request revises its fill
  and the body it weights. If this request is accepted before FR 060 is implemented, FR 060's FRs 9 and 10
  are implemented as revised here, rather than as written there and then changed.
- **The neutral base mesh, always**, and not an argument.
- **Rigid helpers plus a nearest-body fill**, not nearest everywhere.
- **In scope:** the report, the limit and normalise step, and the bend test. **Not in scope:** re-weighting
  any rig other than an authored one.

*Not asked*, each argued where it is stated:

- **The live check chooses between skin-only and whole-mesh heat** (FR 2). It is an empirical question.
- **The bend test is a section of the report** rather than a tool of its own: one description and one
  reading.
- **`clean` is a method**, as `mirror` is.
- **Rigid candidates are found by anchor joint, with a name tie-break and an override**, because no
  geometric rule separates the eye bone from the eyelid bones on `default`.

## References

- NEXT_STEPS: [Nothing in MPFB weights a new rig](../NEXT_STEPS.md#nothing-weights-a-new-rig).
- [FR 060](../060-authoring-rigs/README.md), whose `mpfb_weight_rig`, `shared/rig_definition.py` and
  `mpfb_store_rig` this builds on.
- mpfb2:
  - `data/mesh_metadata/basemesh_vertex_groups.json` and `data/mesh_metadata/hm08.mirror`;
  - `data/rigs/standard/weights.*.json` and `data/rigs/rigify/weights.human_toes.json`;
  - `services/rigservice.py` (`get_weights`, `exclude_weights_below`);
  - `services/targetservice.py` (`_load_mirror_table`);
  - `ui/create_assets/makeweight/operators/`.
- Blender:
  - `source/blender/editors/armature/meshlaplacian.cc` (`heat_ray_source_visible`,
    `heat_bone_weighting`);
  - `source/blender/blenkernel/intern/armature_deform.cc` (normalisation by `contrib`).
- [FR 048](../done/048-measuring-mesh-assets/README.md), whose "count, put back exactly, no verdict" this
  report follows.
