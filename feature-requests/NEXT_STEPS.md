# Next steps

This file contains remaining, not-yet-finished development efforts. Those a feature request already
scopes come first, in request order, and an entry a request covers only in part says so. The rest
follow by apparent impact, which is a judgement rather than a measurement, and each would become a
numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md)) when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## Contents

**With a feature request**, in request order:

- [The MakeClothes and MakeSkin workflows](#the-makeclothes-and-makeskin-workflows): FR 049-051
- [A hand cannot be placed at a point on a standard rig](#a-hand-cannot-be-placed-at-a-point-on-a-standard-rig): FR 052 and FR 053
- [Hand-to-hand contact on a Rigify rig](#hand-to-hand-contact-on-rigify): FR 052, in part
- [A refit silently resets a generated Rigify rig's pose and switches](#refit-resets-a-rigify-pose): FR 054
- [Refits raise on a character whose collection is excluded from the view layer](#refit-raises-on-excluded-collection): FR 054
- [Selection restore covers one object](#selection-restore-covers-one-object): FR 054, in part
- [Loading poses](#loading-poses): FR 055
- [A summary mode for the asset catalogue](#a-summary-mode-for-the-asset-catalogue): FR 056
- [Response bulk on the read-only tools](#response-bulk-on-the-read-only-tools): FR 056, in part
- [No way to verify an install without an MCP client](#no-way-to-verify-an-install-without-an-mcp-client): FR 057

**Without one**, by apparent impact:

- [A windowed bridge answers once a second when Blender has nothing to do](#windowed-bridge-answers-once-a-second)
- [Posing support](#posing-support)
- [A material whose textures do not resolve is reported as applied](#a-material-whose-textures-do-not-resolve-is-reported-as-applied)
- [The Rigify `fist` shape intersects itself, and "straight" is out of reach](#rigify-fist-intersects-itself)
- [`mpfb_create_human` takes no name, and no targets](#create-human-takes-no-name)
- [Whether `mpfb_add_asset` should measure intersections by default](#add-asset-intersections-by-default)
- [A clearance line in `mpfb_place_character`](#a-clearance-line-in-place-character)
- [Garment fit intersections that no MPFB tool can fix](#garment-fit-intersections)
- [A garment behind a sub-rig is missing from the family](#a-garment-behind-a-sub-rig-is-missing-from-the-family)
- [Trying an asset without touching the scene](#trying-an-asset-without-touching-the-scene)
- [Visemes and lip sync](#visemes-and-lip-sync)
- [Subdivision on a mesh asset, beside the shape keys `interpolate` gave it](#subdivision-on-mesh-assets-beside-shape-keys)
- [Enhanced skin settings, and MPFB's named material settings files](#eye-and-layered-skin-colours)
- [Layered skin: what `mpfb_set_material_settings` cannot reach](#layered-skin-sockets-out-of-reach)
- [`tongue01` does not follow `jawOpen`](#tongue-does-not-follow-jaw-open)
- [License in the catalogues](#license-in-the-catalogues)
- [Direct tests of the bridge's shared modules](#direct-tests-of-the-bridges-shared-modules)
- [A garment's sub-rig is bound wrong when it is equipped away from the origin](#sub-rig-child-of-breaks-away-from-the-origin)
- [`mpfb_set_skin` renames another character's node groups to `.unused`](#set-skin-renames-another-characters-node-groups)
- [The export copy's bake in a crowded file](#the-export-copys-bake-in-a-crowded-file)
- [Stale anchor links in the documentation](#stale-anchor-links-in-the-documentation)
- [An install probe for the viseme packs, in MPFB](#viseme-pack-probes)
- [What the all-or-nothing batches caught (keep this)](#what-the-all-or-nothing-batches-caught)

<a id="the-makeclothes-and-makeskin-workflows"></a>

## The MakeClothes and MakeSkin workflows

**Scoped on 2026-11-03 as four requests.**
[FR 048](done/048-measuring-mesh-assets/README.md) (`mpfb_check_mesh_asset` and `mpfb_check_intersections`)
has landed; [HISTORY.md](HISTORY.md) has it. Not yet implemented:
[FR 049](049-makeskin-materials/README.md) (set, get and store a MakeSkin material),
[FR 050](050-writing-mesh-assets/README.md) (`mpfb_write_mesh_asset`, and the try-on recipe) and
[FR 051](051-delete-groups/README.md) (`mpfb_generate_delete_group`, behind a spike). They rename the
tools proposed below, since the [glossary](../specifications/tool-interface.md) keeps "clothes" for
quoting MPFB. Item 5 below stayed out of them: see
[Trying an asset without touching the scene](#trying-an-asset-without-touching-the-scene).

**No tool touches asset authoring.** Everything MPFB's Create assets panels do was driven through
`execute_blender_code` and `from bl_ext.repo.mpfb...` imports, which is exactly the "read MPFB's
source to know what to call" the [vision](../specifications/vision.md) exists to remove.

The evidence is one session (2026-11-01), taking a draft gi to a finished asset: new belt geometry,
a re-cut unwrap, three 4096 px textures, and an MHCLO written, then loaded on another character.
Scripts and renders are in `interacting_with_blender/taido/gi/`, with the task record in its
`README.md`. Only four MPFB tools were called in the whole session, all read-only, and two of those
gave misleading answers because the object's source record was stale (below).

| Step | How it was done | What it cost |
|---|---|---|
| Is this mesh ready for MakeClothes? | `ClothesService.mesh_is_valid_as_clothes()` by hand; metadata through three config classes | The answer was `all_checks_ok: true` for a mesh with real defects (below) |
| Build the material | Wrote an MHMAT by hand, then `populate_from_mhmat()` and `apply_node_tree()` | Reading the operator first, because `mpfb.import_makeskin_material` needs a file dialog and a "replace" scene property |
| Write the MHCLO | `bpy.ops.mpfb.write_makeclothes_clothes(filepath=...)`, selecting exactly the basemesh and garment first | 2.2 s to run. It leaves the selection cleared and reports only through `self.report` |
| Delete group | A ray-casting script | **Eleven runs** |
| Try the asset on someone else | `HumanService.add_mhclo_asset()` in a headless Blender on a posed template scene | 14 s per pose, and it found every defect that mattered |

### Proposed tools, in order of what they would have saved

**1. `mpfb_check_clothes`.** Landed as `mpfb_check_mesh_asset`, in
[FR 048](done/048-measuring-mesh-assets/README.md).

**2. `mpfb_write_clothes_asset`.** Takes a garment and writes MHCLO + OBJ + MHMAT + textures, following
the [mutating-tools rules](../specifications/mutating-tools.md):
- a name and never a path;
- `overwrite: false` by default;
- selection restored;
- `blocked_by` for a missing xref cache (`mpfb.basemesh_xref` builds it) and a failed check;
- `path`, sizes and match counts in the answer.

The logic sits in the `ClothesCommon` operator mixin rather than a service, so like
`mpfb_set_asset_material` this has to reproduce a panel. Destination is a design question: the
library is the natural "where the result can be found", but a work-in-progress may not belong there.
This session wrote to a project directory, and **"Store in library" is untested**. It must also say
that it rewrites source textures (below).

**3. `mpfb_set_makeskin_material`.** Takes a name, a map of `{diffuse, normalmap, roughnessmap, ...}`
to image paths, and values, and builds the node tree through MPFB's own template. Agents generate
textures outside Blender, so this is one tool that has to accept input paths. It needs a matching
read: which maps are wired, at what strength, in which colour space. `mpfb_get_material_settings`
reports only `diffuseIntensity` for a garment.

**4. `mpfb_generate_delete_group`.** This was the longest part of the session, and it is a real
algorithm rather than a call:
- `mpfb.makeclothes_gendelete` calls its own result "very rough" and, by its source, refuses any
  garment with a modifier. MPFB's own Subdivision modifier is one.
- The group went from 2563 to 3209 vertices.
- A fixed margin at the V-neck is wrong both ways: 3.5 cm left dark slits inside the lapel on the
  authoring body, and 7.5 cm left skin poking through the coat on the posed template.
- What worked was a sight-line test, plus a collar of three rings because a mask takes the whole
  face. See `taido/gi/tools/extend_delete_group.py`.
- Its answer should give masked-skin-still-visible and unmasked-skin-under-garment counts.

**5. A way to try an asset without touching the scene.** Every poke-through appeared only on the
template's other body shape, in a pose. The authoring scene showed zero overlaps throughout. A
headless `mpfb_try_asset` on a preset would give an agent that loop. Even without it,
`mpfb_add_asset`'s answer should carry the intersection counts already asked for under
[Garment fit intersections](#garment-fit-intersections). `mpfb_add_asset`
was not itself tried here, since it would have left a `Delete.*` group on the user's character.

**Not tools.** Unwrapping, packing and texture generation are general Blender and image work, and
went fine through generic code. A short recipe would serve better: rasterize UV triangles into
per-texel position and island maps, build a height field in metres, derive the normal map. That took
about 500 lines to write and 20 s to run.

### Traps worth documenting now, whatever gets built

- **An overlap count on a masked body is blind.** Once the delete group grew, the masked skin was no
  longer in the evaluated mesh, so `coat/body` stayed at 0 while it poked through on the next
  character. It also silently disabled this session's own clearance step, which measured against the
  evaluated body. Measure with the masks off.
- **Subdivision can warp a straight texture pattern.** MPFB adds Subdivision with Blender's default
  `uv_smooth` (`PRESERVE_BOUNDARIES`). A narrow strip with one face across its width, as a belt
  naturally is, renders its stitching as a ripple. It is perfectly straight with subdivision off, and
  worse with `uv_smooth: NONE`. Margin strips along both long edges fixed it. A band-like part is a
  common garment feature, so this deserves a line in MPFB's docs or a check.
- **Mixed faces are refused.** `all_faces_same_type` means an all-triangle draft forces any added
  geometry to triangles too. The message is clear; the restriction is worth knowing before modelling.
- **A garment changes behaviour once it has a material of its own.** Nothing updates `asset_source`,
  so this gi still answers as `nurse_uniform_with_pants`. `mpfb_get_object_info` gives
  `mhclo_path: null`, `mpfb_list_asset_materials` says `mhclo_not_installed`, and by its source
  "Store as alternate" would fail for the same reason.

### Worth raising in MPFB

- `generic_execute` reports an image error with `{'ERROR'}` and then returns `{'FINISHED'}`, and
  `mpfb.import_makeskin_material` does the same when a material already exists. Called from code,
  both read as success. Any tool wrapping them has to check for itself.
- `check_that_all_textures_are_saved` calls `image.save()` on every texture, which **re-encodes the
  source files in place**: here the diffuse went from 2.5 to 3.2 MB and the normal map from 17.0 to
  18.2 MB. Nothing says so, and it is a surprise if those files are generated or under version
  control.
- The MHMAT writer emits `bumpmapIntensity 1.0` with no bump map and `roughness 0.7` beside a roughness
  map. Both are harmless, but a reader can't tell which values are in effect.

<a id="garment-fit-intersections"></a>

## Garment fit intersections that no MPFB tool can fix

[FR 048](done/048-measuring-mesh-assets/README.md) made these counts something a tool answers.
What it could not do stays here: the fitted offset, and the `license` filter over alternative materials.

From four single, unposed-then-relaxed characters (scripted check:
`interacting_with_blender/photo_studio_verification/check_intersections.py`). Pose changes drove
arms-vs-trunk and hands-vs-garment overlaps to 0-2 face pairs. What pose cannot reach is
asset fit, and MPFB has no offset control for it:

| Pair | Face pairs | Where |
|---|---|---|
| `long01` hair x `mindfront_f_dress_02` | 198 | back of the dress, under the hair |
| `mindfront_male_trousers_1` x `mindfront_shoes_oxford_male` | 93 | trouser hems inside the shoe collars |
| `mindfront_m_suit_01` (black) x body | 43 | collar at the neck (122 before a scene-level +4 mm Displace) |
| `mindfront_m_suit_01` x `mindfront_shoes_oxford_male` | 36 | hems inside shoes |
| `mindfront_f_dress_03` x body | 32 | sleeve at the armpit (97 before the same Displace) |
| `o4saken_curly01` x `mindfront_knitted_hat_01` | 7903 | hat swallowed by the hair; replaced |

A per-asset "offset along normal" in the fitting step (MakeHuman's `z_depth`, or a fitted-offset
slider) would turn most of these into a tool call. A garment-vs-garment report on `mpfb_add_asset`
would have caught the hat on the first call instead of after a render.

More from the second man-and-woman session (2026-10-24, CC0 only, script:
`interacting_with_blender/man_and_woman_holding_hands/check_intersections.py`). Layered separates
are where this bites hardest; the session ended up choosing garments by BVH count rather than look:

| Pair | Face pairs | Outcome |
|---|---|---|
| `toigo_turtle_neck` x `toigo_wool_pants` | 557 | waistband through the sweater; both dropped |
| `toigo_fisherman_sweater` x `toigo_long_full_skirt` | 502 | same; both dropped |
| `male_casualsuit01` x body | 171 | ~85 at the collar, unfixable; dropped |
| every male sock-shoe (`shoes01`-`06`) x any CC0 one-piece jeans | 28-120 | `shoes03` x `male_casualsuit03` kept: 28, all inside the trouser leg, invisible |
| `toigo_ballet_flats` / `toigo_flats` x body | 148 / 972 | foot through the sole; `toigo_mj_cloth_shoes` scored 0 |
| `toigo_keyhole_neck_dress` x body | 0 | the only CC0 one-piece female outfit tested that fits cleanly |

An intersection count in `mpfb_add_asset`'s answer would have saved most of this, and now exists when
asked for. The rest is a `license` filter that also covers alternative materials, since every candidate
had to be joined against the pack JSONs by hand.

<a id="add-asset-intersections-by-default"></a>

## Whether `mpfb_add_asset` should measure intersections by default

**It is opt-in, by [FR 048](done/048-measuring-mesh-assets/README.md#intersections-is-opt-in-and-this-is-the-number)'s
own rule**: always on unless it costs more than a quarter of the call, and it costs a mean of 36 %. That line
assumed equipping takes seconds. On a headless Blender it takes 20-60 ms for anything small, and the field's 9-47
ms is what looks large beside it; nothing removes the floor of reading the body twice.

The case for reversing it: the sessions behind the request wanted the count on the call that caused the problem,
and nobody asks for what they do not know they need. Against a windowed Blender's round trip, the share would fall
well under the line. **It needs someone to decide, and flipping it is one default in two files.** The evidence
to weigh is a measurement of the same calls on a windowed Blender, which that request did not make.

<a id="a-clearance-line-in-place-character"></a>

## A clearance line in `mpfb_place_character`

`mpfb_place_character` already computes a footprint. Reporting whether that footprint overlaps another
character's, and what the closest approach is, would catch the common case without a second call.
`shared/mesh_overlap.py` has the measurement, so what is left is deciding when it is worth what it costs on a call
that is otherwise nearly free: the question [FR 048](done/048-measuring-mesh-assets/README.md) just answered
for `mpfb_add_asset` the other way.

More from the action image session (2026-11-03, script:
`interacting_with_blender/action_image_with_normal_map_skins/fit_tools.py`). Two things here are new.
`mpfb_add_asset`'s default subdivision can itself cause the intersection, and an overlap count does
not say whether anything shows:

| Pair | Face pairs | Outcome |
|---|---|---|
| `cortu_cargo_pants` (196 faces) x body, at rest, subdivision 1 | 284 and 148 | Skin through both thighs in the render |
| Same, at rest, subdivision 0 | 28 and 12 | Faceted outline, far less skin |
| Same, posed, subdivision 0 | 33 and 21 | 448 px of skin visible on one man, 0 on the other |
| `short01`, `short02`, `short03` under `mindfront_patrol_cap` | 1501, 425, 186 vertices through | No short CC0 hair fits; hair asset dropped |
| `jaldmic_akm_base` x the hand holding it | 468 | The asset's fixed position runs it through the palm; not visible |

The visible figure took a pixel test: cast a camera ray per pixel and count where the body is hit
before the pants, which needs `calc_loop_triangles`, because `BVHTree.FromPolygons` triangulates
non-planar quads differently from the renderer and the two disagreed by whole patches. Per-vertex and
per-face versions reported 0 for a patch plainly visible in the render. Usable hip and thigh poses
only got 448 px to 224 px (an extreme thigh angle with a 20-degree twist reached 32 px);
`upperleg-muscle` −0.7 on the body brought it to 88 px. A "does this show from this camera" answer
beside the overlap count would have replaced most of that search.

<a id="a-hand-cannot-be-placed-at-a-point-on-a-standard-rig"></a>

## A hand cannot be placed at a point on a standard rig

**Scoped on 2026-11-03 as two requests, not yet implemented:** [FR 052](052-reaching-and-orienting/README.md) (`reach_to` and `orient`
on `mpfb_set_pose_bones`) and [FR 053](053-rig-helpers/README.md) (`mpfb_set_rig_helpers`). Those are the second and third ways out
below, and FR 052 takes the first.

Found by the man-and-woman scene session, whose whole subject was two characters holding hands.
This is the single largest cost that session paid, and it is adjacent to
[Posing support](#posing-support) rather than covered by it: that entry is about hand *shape*, this
one is about where the hand *is*.

`mpfb_set_pose_bones` offers `move_to` ("where the head goes"), but a bone only accepts it when its
role is `ik_control`. On MPFB's standard rigs there are none: `mpfb_get_pose_controls` on
`default_no_toes` reports `helper_modes` of `{"arm_mode": "NONE", "leg_mode": "NONE",
"finger_mode": "NONE", "eye_mode": "NONE"}`, `counts_by_role` gives `ik_control: 0`, and every arm
control is `chain: "fk"`. So the only way to put a hand somewhere is to solve the chain by hand:
pick a direction for `upperarm01`, `lowerarm01` and `wrist`, write it, read `mpfb_get_pose`'s
`landmarks`, and iterate. That session did it roughly ten times per arm.

MPFB itself can do better and the bridge cannot reach it. MPFB's IK helpers are what `helper_modes`
is reporting on, but nothing turns them on from this side: `RigService` exposes only
`add_ik_constraint_to_pose_bone`, `add_ik_rotation_lock_to_pose_bone` and `set_ik_rotation_limits`,
the low-level pieces, while the helper *modes* are assembled in MPFB's UI operators. Building them
by hand from those three calls would be reimplementing an MPFB panel in the bridge, which is what
the posing commands already do for Rigify's snaps — so it is in scope, just not small.

Three ways out, cheapest first:
- **Say so.** `mpfb_set_pose_bones`' description should state that `move_to` and `move_by` need an
  `ik_control`, and that standard rigs have none until the helpers are switched on. Today the
  limitation is discoverable only by reading `counts_by_role` and inferring.
- **A tool that switches MPFB's IK helper modes on**, per limb, mirroring the panel. That is the
  real fix and it makes `move_to` work on the rig most characters get by default.
- **A solver argument**, e.g. `reach: {bone: "wrist.L", to: {...}}`, that does the FK iteration in
  the bridge and reports what it achieved. More work, but it is the thing a caller actually wants
  and it would work on every rig.

Worth noting for whoever takes this: Rigify was not a way out either. By the time the problem
appears the character is dressed, `mpfb_add_rig` refuses with `already_rigged`, and MPFB cannot swap
a rig — deleting it unrigs every garment and nothing rigs them retroactively. The rig choice is
effectively final at the moment it is made, which raises the cost of getting it wrong.

<a id="hand-to-hand-contact-on-rigify"></a>

## Hand-to-hand contact on a Rigify rig

**The `orient` entry is scoped in [FR 052](052-reaching-and-orienting/README.md).** The rest stays here.

A cost data point beside [A hand cannot be placed at a point on a standard rig](#a-hand-cannot-be-placed-at-a-point-on-a-standard-rig)
and [FR 048](done/048-measuring-mesh-assets/README.md),
this time on `rigify.human_toes`, where `move_to` on `hand_ik` does work. Placing the hand was easy;
**orienting** it was not. `aim` plus `twist` does not say what twist 0 is relative to: on the same
hand, twist 0, -90, +90 and 180 gave "back of hand forward", "palm forward", "hands crossed" and
"palms facing", which does not read as 90-degree steps from the caller's side. What worked was
setting the control's world matrix in bpy from a palm normal and a finger direction, measured on
`DEF-hand` (palm normal is local +X on `.L`, -X on `.R`).

The hold itself then needed a search: about 500 placements were scored with a BVH overlap count
plus "his vertices within 5 mm of her surface" as a proxy for a grip, with the hand shapes set by
`mpfb_set_rigify_hand_shape` (his fingers curl ~0.6 and thumb spread 0.9 so they wrap the pinky edge
of her hand; hers ~0.45). Result: 0 intersecting face pairs, 0.6 mm closest approach. Two
additions would have saved most of the hour:

- An `orient` entry on `mpfb_set_pose_bones` taking the palm normal and finger direction in the
  character frame (or world), resolved against the deforming hand bone.
- `mpfb_set_rigify_hand_shape`'s answer is ~2.5 KB per call, mostly unchanged fingers' before/after
  tips; a written-fingers-only mode would make iterating on curls cheap.

Also worth saying in the tool description: negative thumb `spread` brings the thumb across the palm,
out of the palm plane and toward whatever the palm faces; positive brings it back beside the index.

<a id="refit-resets-a-rigify-pose"></a>

## A refit silently resets a generated Rigify rig's pose and switches

**Scoped on 2026-11-03 as [FR 054](054-refits-keep-the-pose/README.md), not yet implemented.** Measured: a default rig keeps its pose
through a refit, so this is Rigify's alone, and snapshot and restore puts one back at 0.0 mm in 23 ms.

Found by the photo studio template session (`interacting_with_blender/PHOTO_STUDIO_TEMPLATE.md`).
`mpfb_set_face_units` refits by default, and so do `mpfb_refit_human`,
`mpfb_apply_expressions` and `mpfb_set_macro_details(refit=True)`. On a generated Rigify rig the
refit leaves every control at rest **and every limb's `IK_FK` back at 0 (IK)**. Nothing in the
response says so: `refit_performed: true` and the pose is gone. Character A had been posed
(switches, arms, head) before its smile was composed. The pose vanished, and it showed up only
when a later `mpfb_set_pose_bones` call on C and D was refused with `chain_not_in_charge`,
because their height changes had refitted them too. The cost: three characters re-posed, about
nine extra calls, and one wasted test render.

Two cheap improvements:

- Every refitting tool reports `pose_reset: true` with `restore_with`, built the way
  `mpfb_reset_pose` already builds it, when the rig was off rest before the refit.
- Better: capture the pose and switches before the refit and re-apply them after it, behind an
  argument that defaults to on.

<a id="refit-raises-on-excluded-collection"></a>

## Refits raise on a character whose collection is excluded from the view layer

**Scoped on 2026-11-03 in [FR 054](054-refits-keep-the-pose/README.md), which includes the collection temporarily rather than refusing
as proposed below.** It keeps the refusal for what cannot be included. `mpfb_add_asset` raises the same way, and is in scope.

Several characters at the origin are easiest to manage one collection each, with all but one
excluded from the view layer. Any refit then fails with a raw traceback
(`RuntimeError: ViewLayer 'ViewLayer' does not contain object 'TestB_Human.metarig'`, from
`RigService._do_refit_existing_armature` setting the active object). Three
`mpfb_set_face_units` calls failed this way in one batch. This should be a refusal like the
others (`blocked_by: "not_in_view_layer"`, naming the collection), checked before anything is
written. `mpfb_set_face_units` had already written the shape keys when the refit raised.

<a id="selection-restore-covers-one-object"></a>

## Selection restore covers one object

**[FR 054](054-refits-keep-the-pose/README.md) moves the commands it wraps onto `restored_all()`.** The others stay here.

Ten mutating commands put the caller's selection back with `shared/selection.py`'s `restored()`,
which restores the active object and the **borrowed** object's own selection and nothing else, so an
object an operator selected on the way - a new armature, an imported garment - is left selected.
`restored_all()`, which `mpfb_create_export_copy` and `mpfb_export_character` use, records every
object's selection and the active object, puts them back however the block ends, and leaves what
the block created deselected. What is left is moving the other ten onto it. It changes what each leaves behind,
so each command's bridge test has to say what the selection is after a call, which none does today.

## Loading poses

**Scoped on 2026-11-03 as [FR 055](055-loading-and-saving-poses/README.md), not yet implemented**, with saving, partial poses
and the floor added. Scoping measured why a load needs a choice: MPFB's BVH loader rewrites 124 of 137 bone rolls, after which a JSON
pose lands 606 mm off at the wrist, and each load orphans an armature and an action.

These come in two variants: BVH-style poses found via AssetService and json-style poses found
in the user config dir. The latter is loaded in an operator in the rigging ui hierarchy.

Both types should be supported, probably with different tool calls. 

The session that rendered the extensions-page line-up ([FULL_SESSION.md](FULL_SESSION.md))
needed this and did without: six characters were taken out of the A-pose by rotating
`upperarm01`, `lowerarm01` and `head` by hand through blender mcp. `mpfb_list_assets` already
lists `poses` as a subdir, so the catalogue half exists and only the acting tool is missing.

<a id="a-summary-mode-for-the-asset-catalogue"></a>

## A summary mode for the asset catalogue

**Scoped on 2026-11-03 as [FR 056](056-asset-library-summary/README.md), not yet implemented.** Measured, against what is below: the cost is
the answer's size (605 KB for a sweep, 128 KB for a bare call, 3.2 KB for the faceting), not the time, since the preview load did
not show up headless. `limit=0` already gives the counts with no rows, and says nothing about it.

From the man-and-woman scene session, and deliberately *not* an argument against the cap. `mpfb_list_assets`
is documented as "a filtering tool rather than a listing one", its answer is capped on purpose, and
`truncated` / `total_count` exist so a caller cannot mistake a page for the library. That design is
right for "find me a garment".

It is the wrong shape for the question a session actually opens with, which is *what is in this
install at all* — how many garments, hair, skins and poses there are, how they divide across packs,
and how they divide by license. Answering that today costs one call per
`asset_subdir`, ten in this session's case, each returning up to 1000 full rows — name, label,
fragment, absolute path, thumb path — when the caller wants counts. The first call also pays MPFB's
one-preview-image-per-asset load for that subdir, so the cheapest possible phrasing of "what do I
have" is also among the most expensive calls the server offers.

A `summary=True` mode (or a separate `mpfb_describe_asset_library`) returning counts faceted by
`asset_subdir` × `pack` × `license`, and nothing else, would answer it in one call and read in a
dozen lines. [FR 046](done/046-license-in-the-catalogues/README.md) gave every call
`counts_by_license`, taken before the license filter and the cap, so "226 of 639 clothes are CC0"
is now one call per subdir; the faceting across subdirs and packs is what is left for this entry.

A smaller version of the same point: `mpfb_list_assets()` with no arguments returns 200 rows that
are all `Clothes`, because `clothes` sorts first and the default limit stops there. `truncated` is
true and `total_count` is honest, so the response is not wrong — but the shape of it invites the
reading "this install has 200 clothes and nothing else", which is what happened here before the
docstring was read. Defaulting a no-argument call to the summary above would be strictly more
informative than a truncated page of one type.

<a id="response-bulk-on-the-read-only-tools"></a>

## Response bulk on the read-only tools

**Measured while scoping [FR 056](056-asset-library-summary/README.md):** `known_packs` is 1.65 KB of a 128 KB answer, so its bullet below
is worth little on its own. The rows, at 622 bytes each, are the cost. FR 056 drops it from a summary only.

Not a defect, and not urgent — recorded because one session hit all three and they share a shape:
the tools return everything they know rather than what was asked for, and the catalogues are now big
enough that it costs.

- **`mpfb_list_assets` echoes `known_packs` in every response.** On this install that is 118 pack
  names, repeated in full whether the call filtered by pack or not. It exists so a caller can
  correct a misspelling from the same response, which is right — but it could be sent only when
  `pack_recognized` is false, which is the only time it is needed.
- **A full `mpfb_get_material_settings` skin read is about 20 KB.** The docstring warns about it and
  `section` narrows it to one of three. Within `skin` there is no narrowing: ten groups come back
  with every socket, every range and every `linked` entry, when the caller usually wants
  `color.SkinColor`. A `groups=["color"]` argument would be the same shape as `section`, one level
  down.
- **`mpfb_add_asset` equips exactly one asset per call.** Dressing two characters took sixteen
  calls, each returning a full report. A batch form would cut the round trips, and — more useful —
  would give one place to enforce the ordering rule that the README states and no tool checks:
  rig before garments, Rigify generate after them, dress before placing.

<a id="no-way-to-verify-an-install-without-an-mcp-client"></a>

## No way to verify an install without an MCP client

**Scoped on 2026-11-03 as [FR 057](057-install-selftest/README.md), not yet implemented.** One claim below does not hold: "the bridge is
not running" and "the add-on is not enabled" cannot be told apart from outside Blender, where both are nothing listening.

Found by the man-and-woman scene session, which began with the server installed but not registered
with the client, and could not tell that apart from a broken one.

Everything needed to diagnose it exists, and none of it is reachable without a working MCP client
already in place. `mpfb_get_status` answers this question precisely — it is the tool whose whole
purpose is "is MPFB present, initialized and correctly configured?", and it is documented as the
one that "always answers rather than failing" — but calling it requires the client registration
that is the thing in doubt. The session's workaround was to hand-write a JSON-RPC stdio probe
(`initialize`, `notifications/initialized`, `tools/call`) against `.venv/bin/mpfb-mcp` to confirm
the server started, spoke the protocol, listed 42 tools and round-tripped to the bridge. That is
forty lines of client to answer a yes/no question, and nothing in [INSTALL.md](../INSTALL.md)
suggests it.

A `mpfb-mcp --selftest` (or `doctor`) subcommand on the existing console script would close this:
start the server in-process, run the same `mpfb_get_status` call, and print the protocol version
handshake, the tool count, the bridge host and port actually used, and whether the bridge answered
— then exit non-zero if it did not. It is the one command an install guide can end with, the one a
user can paste into a bug report, and the only way to separate "the bridge is not running" from
"the add-on is not enabled" from "the client never started the server" without a client. It needs
no new bridge command: the protocol-version check at connect time and `get_mpfb_status` already
carry every fact it would print.

Worth saying in `INSTALL.md` either way: the Blender half can be verified on its own, because the
bridge's port shows up in `ss -ltnp | grep 9877` when the add-on is enabled and not otherwise.
That single line distinguishes the two most common failures and costs nothing to document.

<a id="windowed-bridge-answers-once-a-second"></a>

## A windowed bridge answers once a second when Blender has nothing to do

Measured during [FR 045](HISTORY.md#placing-a-character): in a windowed Blender whose event loop
was idle, a `bpy.app.timers` callback asking for 0.05 s fired once a second, so every tool took
1.0 s - the smoke run 52 s where a headless bridge takes 2.1 s - although the bridge's own idle
countdown was at its active rate. [architecture.md](../specifications/architecture.md#the-bridge)
records the measurement. What is not known is why: whether Blender's window manager sleeps between
events and wakes timers late, whether it depends on the window being focused or on the platform,
and whether anything an add-on may do (a modal operator, `wm.event_simulate`-style wakes, a
redraw) shortens it without costing CPU while idle. FR 029 and FR 030 measured 50-58 ms per call
through the same timer, so this has not always been so. Worth an effort only if agents drive a windowed
Blender for long sessions; the headless bridge is unaffected.

<a id="posing-support"></a>

## Posing support

Two gaps the karate session found, which the posing requests did not take:

- **There is no hand-shape helper for the default rig or `game_engine`, including its Rigify
  conversion.** [FR 047](done/047-rigify-hand-shapes/README.md)'s `mpfb_set_rigify_hand_shape` covers
  rigs generated from MPFB's Rigify meta-rigs only, and refuses these with `rig_not_supported`. The
  56-rotation cost below was measured on `default_no_toes`.

  On the default rig a curl means rotating three bones per finger, with no master, and maybe MPFB's
  own finger helpers. A helper there needs its own mechanism and its own calibration; FR 047's
  degrees (`shared/rigify_hands.py`) are a starting point, not a table to reuse, since they were
  set on Rigify's coupling of the two later joints. The `game_engine` conversion's fingers are
  `super_finger` with Rigify's defaults, `_l`/`_r` names and no palm control, so supporting it would
  be a calibration and a classification effort rather than a mechanism one.

  **Confirmed, with a number.** The man-and-woman scene session needed a soft grip on two hands of a
  `default_no_toes` rig and spent **four calls of fourteen entries each** — 56 finger-segment
  rotations — to curl, uncurl and re-curl them while hunting for a pose that did not intersect. It
  also has to be a *curl amount*, not just named shapes: what the image finally needed was a loose
  24/40/24-degree curl on one hand and none on the other. On Rigify a per-joint curl like that is
  not expressible, by decision, and stays `mpfb_set_pose_bones`' job.
- **The pose libraries cannot reach a generated Rigify rig at all** ([FR 055](055-loading-and-saving-poses/README.md) refuses it, and a
  pose saved on such a rig loads back; retargeting stays here), which makes
  [Loading poses](#loading-poses) narrower than that entry assumes. There is one JSON pose per FK
  rig type (`default_fk`, `game_engine_fk`, and so on), and MPFB's panel looks for
  `<identify_rig>_ik` on any rig with an `_ik` bone, so the karate session's rig would need
  `rigify_generated.human_toes_ik`, which does not exist. The 59 BVH poses are worse. Two of them,
  `culturalibre_cl_fight_01` and `gpedroso_boxing`, would have been a good starting point for that
  session's stance. But `import_bvh_file_as_pose` matches bones by default-rig names, and 35 of
  `cl_fight_01`'s 163 bones also exist on the generated Rigify rig (`root`, `head`, `jaw`, the
  eyes, the breasts and every toe). It would rewrite their rolls in edit mode and give a partly
  posed, broken character without any error. A pose-loading tool must refuse a rig the pose was not
  made for. Retargeting a default-rig pose onto Rigify controls would be a separate effort.

<a id="a-material-whose-textures-do-not-resolve-is-reported-as-applied"></a>

## A material whose textures do not resolve is reported as applied

[FR 049](049-makeskin-materials/README.md) refuses this in its own new tool; the two tools below stay
here.

`mpfb_set_asset_material` returned `applied: true`, named the file and listed what it destroyed,
for a material that rendered as black plastic with magenta streaks.

The asset is `ricardo2020_long_01_bronze`, shipped in `system_hair_materials03`. Its MHMAT names
three textures by paths relative to a MakeHuman data root that does not exist here —
`hair/long01/Material/long01_diffuse_straw.png` and `..._copper.png` resolve to nothing, and
`normalmapTexture hair/long01/long01_diffuse.png` resolves to the *colour* map, which MPFB duly
wired into the normal-map node. The resulting material has an empty `diffuseTexture` image node
feeding Base Color. Ten of the eleven other materials beside that asset use a bare filename and are
fine, so this is the asset author's bug, not MPFB's — but MPFB loaded it without a word and the tool
passed that silence on.

The fix is a `warnings` entry, which this tool already has a channel for: after building the
material, check each image node for a `None` image or a `filepath` that does not exist, and name
them. `mpfb_add_asset` wants the same check — it builds materials by the same path, and its
`material_created: true` carries the same false reassurance. It is cheap, it needs no new MPFB
capability, and it converts a render nobody can explain into one line in the response.

<a id="rigify-fist-intersects-itself"></a>

## The Rigify `fist` shape intersects itself, and "straight" is out of reach

Found by the Taido gedan-gamae session (`interacting_with_blender/taido/CLAUDE.md`, "Posing"), on
`rigify_generated.human_toes`. Two gaps in `mpfb_set_rigify_hand_shape`:

- **`shape: "fist"` gives 86–123 intersecting face pairs** within the hand itself (BVH overlap
  between finger groups classified by dominant `DEF-` vertex group). The index and middle fingertip
  segments cross, and the thumb sits inside the index. Spread changes through the tool moved the
  count (71 → 91 → 36) without clearing it. A clean fist needed a coordinate-descent search over the
  masters' euler X/Z and Y scale in bpy, about 70 evaluations and 3 s in all. The best clean
  result (curls 0.8/0.8/0.87/0.92, thumb 0.65/−48°) is visibly looser than the preset, because every
  tighter thumb went into the fingers (22–86 pairs). Wanted: a `fist` that is clean on MPFB's own
  meshes, or an `avoid_intersections` flag that backs each curl off until the hand's self-overlap is
  zero, reporting what it gave up.
- **A flat, straight open hand cannot be expressed.** The rest fingers curl about 26° toward the
  palm, and the tool's floor of `curl −0.2` leaves 5–10°. A curl range down to about −0.3, or a
  `flat` shape calibrated to put the fingers in line with the hand bone, would cover the open hands
  of martial-arts kamae (and a salute, a blade hand, a wave).

A note for whoever searches finger poses directly in bpy: on `.R` the masters' Z rotation is the
*negated* spread (the tool reads a raw +9° as spread −0.45), so the tool's "same on both hands"
holds. A more positive index `spread` made the index–middle overlap worse in a curled fist
(71 → 91) because of the fist's geometry, not the sign.

<a id="create-human-takes-no-name"></a>

## `mpfb_create_human` takes no name, and no targets

Found by the line-up session. A cast of six is `Human` … `Human.005`, and its eyes are
`Human.high-poly` … `Human.high-poly.005`. That is harmless to the tools, which address by the
returned name, but a later session reading the scene cannot tell who is who. A `name` argument
would fix it, and the response already reports what Blender made of it, since Blender
uniquifies.

In the same session the stylised character got its rig before its targets, and had to be refitted.
`mpfb_set_targets` did say so in `assets_possibly_stale`. A `modifiers` argument on
`mpfb_create_human`, in the same shape `mpfb_set_targets` takes, would make building in the right
order the easy thing to do.

<a id="a-garment-behind-a-sub-rig-is-missing-from-the-family"></a>

## A garment behind a sub-rig is missing from the family

Found by [FR 046](done/046-license-in-the-catalogues/README.md)'s live check. `ponytail01` carries
a sub-rig of its own, so it is parented to that `Subrig` rather than to the character's rig, and
MPFB's `ObjectService.find_related_objects()` does not walk past a `Subrig`. So `ponytail01` is in
neither `mpfb_get_object_info`'s `related_objects` for the basemesh nor the summary's
`equipped_assets`, though it is equipped and moves with the character. The two agree, so the
summary is not a second opinion, but a caller checking a finished character against a brief - by
license, or simply by what it wears - skips its hair.

Asked about the ponytail itself, `mpfb_get_object_info` lists the whole character, so the walk is
asymmetric rather than broken. The fix is in `shared/asset_info.py`'s `related_objects()`, which
would add each `Subrig`'s mesh children, and the question to settle first is whether MPFB's own
callers of `find_related_objects()` rely on the stop - in which case it is not MPFB's defect to
file, only this package's walk to extend.

<a id="trying-an-asset-without-touching-the-scene"></a>

## Trying an asset without touching the scene

What [FR 050](050-writing-mesh-assets/README.md) left out when it settled on a recipe of existing
tools: `mpfb_create_human_from_preset`, `mpfb_add_asset`, pose, `mpfb_check_intersections`. In the gi
session that loop found every defect that mattered. Two things are missing from it:

- **No tool removes a character.** The recipe leaves its test character in the user's scene, and
  deleting one by hand leaves rigs, sub-rigs and masks to think about. A `mpfb_remove_character` would
  be the smallest fix. It is destructive, so it needs the same care as `mpfb_remove_asset`.
- **`mpfb_try_asset` itself**, which would not touch the scene at all. It was weighed as a headless
  subprocess (the project's first, needing the binary's location and results passed between processes,
  beside a bridge that "executes nothing a caller sends") and as a temporary scene in the running file
  (MPFB reads `context.scene`, and a failure part way leaves debris in the user's file). Neither earned
  its cost before the recipe had been used. A second authoring session should say whether it still does.

## Visemes and lip sync

The rest of `FaceService`, deliberately excluded from both expression requests
([FR 026](done/026-face-units/README.md#not-visemes),
[FR 027](done/027-expression-library/README.md)): visemes on a character being worked on rather than
copied for export, which `mpfb_create_export_copy` already covers, and `configure_lip_sync`.

This is speech animation rather than expression — a different vocabulary, different asset packs
(`visemes01` / `visemes02`), and a different propagation mechanism: `interpolate_targets` transfers
shape keys to child meshes through MHCLO vertex correspondence, which is not what a refit does. Note
that it matches shape keys by **bare** name, so it has never propagated the `!ex-` prefixed
expression keys.

`configure_lip_sync` additionally depends on the third-party `lip-sync` addon, maintained outside
the MakeHuman ecosystem, which is a dependency no tool in this package has yet.

<a id="subdivision-on-mesh-assets-beside-shape-keys"></a>

## Subdivision on a mesh asset, beside the shape keys `interpolate` gave it

Found by [FR 039](done/039-exporting-characters/README.md)'s round trip. `mpfb_create_export_copy`'s
`subdiv_modifiers` and `mask_modifiers` act where MPFB's panel acts: on the basemesh, and when
baking on the body proxy. A garment or eyebrows keep the Subdivision `mpfb_add_asset` gave them,
and with visemes or face units interpolated onto them that is a topology-changing modifier beside
shape keys - which FBX resolves by dropping the keys. `mpfb_export_character`'s `readiness` names
each such mesh, and no tool removes the modifier. The options are an extension of the two strategies
to every copied mesh (a departure from the panel, to be named as one), or a modifier option on
`mpfb_export_character` that applies to the exporters only, where FBX's own `use_mesh_modifiers`
already lives. And the same refusal MPFB's proxy bake needs (`proxy_cannot_be_baked`) would apply
to any mesh baked under interpolated keys.

<a id="eye-and-layered-skin-colours"></a>

## Enhanced skin settings, and MPFB's named material settings files

What [FR 040](done/040-procedural-material-settings/README.md) left out on purpose, beside the three
procedural mechanisms `mpfb_get_material_settings` and `mpfb_set_material_settings` cover
([HISTORY.md](HISTORY.md#procedural-material-settings)):

- **Enhanced skin settings**: the per-slot `colorMixIn`, roughness and pore inputs of an
  `ENHANCED`/`ENHANCED_SSS` skin (`skin_material_settings[<slot>]` in a preset). The same
  generic tools could take a fourth section; `shared/material_settings.py` is where it would be
  found, and the serializer's `"colorMixIn"` test is how.
- **MPFB's named settings files**: `eye_settings.<name>.json` and `enhanced_settings.<name>.json`
  in the user config directory, with their save/apply panels under Presets. That is a catalogue
  and an apply-by-name, and a save would be another file written outside the `.blend`.

<a id="layered-skin-sockets-out-of-reach"></a>

## Layered skin: what `mpfb_set_material_settings` cannot reach

Found by the second man-and-woman session, whose brief asked for a natural, not overly glossy
layered skin and asked explicitly what was missing. Roughness and the procedural bump strengths per
region (`body`, `face`, `ears`, `lips`) are all writable, and that was enough to go from MPFB's
default `Roughness` 0.35 (wet-looking) to 0.50-0.58. What is not reachable:

- **The skin's normal-map strength.** The `masternormal` Normal Map node sits at the top level of
  the material, outside every group the tool serializes, so a skin that ships a normal map
  (`mindfront_aksel_skin`) can only be taken at strength 1.0.
- **Specular level and IOR.** Each region group wraps a Principled BSDF with `Specular IOR Level`
  0.5 and `IOR` 1.5 set inside the group, not exposed as group inputs. Skin wants ~1.4; roughness is
  the only lever for gloss.
- Neither is in MPFB's preset serializer either, so this is an MPFB-side gap first; the tool can
  only follow.

The action image session (2026-11-03) needed the normal strength for real:
`mindfront_skin_male_african_middleage`'s author recommends about 0.7, and 1.0 looked gritty on the
chest. It was set to 0.75 through `execute_blender_code`, which also means it does not survive
`mpfb_save_preset`. That session also found a default worth changing in MPFB: with the body group's
`SSSRadiusMultiplyer` at 0.7, an open mouth's interior renders saturated red even with the key light
off, because the cavity uses the body shader. A multiplier of 0.12 clears it. The socket is writable,
so this needed no tool, only several test renders to find.

<a id="tongue-does-not-follow-jaw-open"></a>

## `tongue01` does not follow `jawOpen`

Found by the action image session. With `jawOpen` at 0.85 and a refit, `tongue01` stays near its rest
position and floats mid-mouth, covering the upper teeth as a pink slab; the teeth do follow. The
asset was removed. `mpfb_set_face_units` says nothing about it, since the unit was applied correctly.
Either the tongue wants jaw weighting in MPFB, or the tool's answer could warn when a `Tongue` asset
is equipped and `jawOpen` is above about 0.3.

<a id="license-in-the-catalogues"></a>

## License in the catalogues

[FR 046](done/046-license-in-the-catalogues/README.md) attributed the assets and their materials.
**Targets** are the catalogue left: 211 pack entries are targets, but a target is a file in a category
directory, so the directory join attributes nothing, and a stem join over target names has not been
measured. `shared/pack_attribution.py`'s stem fallback is the mechanism; what is missing is the
measurement that says it holds for targets, which FR 046's `live_check.py` did for the asset subdirs.

<a id="direct-tests-of-the-bridges-shared-modules"></a>

## Direct tests of the bridge's shared modules

Fifteen of the twenty-five modules in `bridge/mpfb_bridge/shared/` are tested **only through the
commands that use them**: `artifact_names`, `asset_info`, `asset_sections`, `expression_divergence`,
`expression_panel`, `macro_reading`, `material_settings`, `modifier_reading`, `performed`,
`pose_reading`, `preset_files`, `refit_blocker`, `rig_lookup`, `target_categories` and
`target_rollup`. Every test that reaches one goes through dispatch. A fault in a shared module is
therefore reported as a failure in whichever command module happens to run first, and a branch no
command's fixture reaches is never reached at all. The layer for direct tests is `bbb_shared/`, which
runs after the add-on's own machinery and before any command, and which already holds the other ten.

Three of them read nothing out of MPFB's services and could be tested without a character, or
without MPFB at all: `artifact_names.py` (the name rule; its tool-side twin is already tested
exhaustively in `tests/test_save_preset.py`, the bridge copy only through the two save commands),
`performed.py`, and `expression_panel.py`, whose failure branches — the UI module absent from
`sys.modules`, a call that raises — are exactly the lines no command test reaches. The coverage
report after FR 035 put the shared modules between 73% and 100% line coverage, all of it through
dispatch; the uncovered lines are listed per module in `bridge/test/coverage/`, and are the place
to start.

<a id="sub-rig-child-of-breaks-away-from-the-origin"></a>

## A garment's sub-rig is bound wrong when it is equipped away from the origin

Found by the line-up session, and **re-diagnosed by [FR 045](HISTORY.md#placing-a-character)**,
whose live check measured it: the anchor above keeps the old title's slug, which said "breaks away
from the origin", and that turned out to be the wrong cause. `ponytail01` ships a sub-rig, and its
`root` bone gets a `CHILD_OF` on the main rig's `head` with `set_inverse_pending = True`
(`mpfb2/src/mpfb/entities/rig.py:599`). Blender resolves that inverse while the new sub-rig still
stands at the world origin, before `ClothesService.set_up_rigging()` parents it to the rig. On a
character at the origin that is right, and **the binding then survives every move**. On a
character already placed, it is off by the rig's whole transform: the hair was dragged 5.7 m, and
stayed 5.7 m out after the character was moved back to the origin. `mpfb_refit_human` re-binds it,
and it then survives moves too. The line-up session had equipped the ponytail on a character it had
already moved; its hand repair (both spaces `WORLD`, inverse recomputed) then broke on the next move
because it was a different binding.

The tools already report each badly bound sub-rig as `subrigs_broken`, naming the refit, and the
defect is filed in `mpfb2/features/MCP_DISCOVERED_BUGS.md`. **What is left is small**: whether `add_asset` should re-bind a sub-rig itself - setting the inverse pending again once
the sub-rig is parented, which is what a refit does - rather than name the refit, and whether to
propose that one-line ordering change upstream.

<a id="set-skin-renames-another-characters-node-groups"></a>

## `mpfb_set_skin` renames another character's node groups to `.unused`

Two characters with `LAYERED` skins share the layered node groups (`MpfbBody`, `MpfbFace`,
`MpfbSkinMasterColor`, ...): the second skin built reuses the first one's. Re-skinning the *first*
character with `mpfb_set_skin` then renamed the groups the *second* character still used to
`MpfbBody.unused`, `MpfbNails.unused.unused` and so on, and built fresh ones for the first. The
render is unaffected (each `.unused` group still has its one user) and MPFB's
`MaterialService.identify_material` still answers `layered_skin` for both, so this is cosmetic
today. But `.unused` is MPFB's marker for "delete me", and anything that later purges by that marker
will break the other character's skin. `materials_destroyed` reports only the subject's materials, so
nothing in the response hints that a second character was touched.

<a id="the-export-copys-bake-in-a-crowded-file"></a>

## The export copy's bake in a crowded file

[FR 039](done/039-exporting-characters/README.md) measured the worst case of `mpfb_create_export_copy`
at 7 s headless with one character and 77 s in a windowed Blender whose file held 1,876 objects:
MPFB's `ExportService._apply_modifiers_keep_shapekeys()` duplicates the body and runs
`bpy.ops.object.modifier_apply` once per shape key, and every operator pays for the whole file. 77 s
is under a third of mpfb-mcp's 300 s socket timeout, and a larger file is not. Rebuilding the keys
through the data API rather than an operator per key would be MPFB's change, worth proposing
upstream with these numbers; on this side, the choices are a longer timeout for this one command or
a progress-free warning in the answer when the shape key count and the file size predict a long
call.

## Stale anchor links in the documentation

Found by a link check while [FR 037](done/037-one-word-per-concept/README.md) closed. These relative
links point at an anchor that no longer exists: the file is there, the heading is not. All but the
last predate FR 037.

- `specifications/vision.md` and `CLAUDE.md` link to
  `NEXT_STEPS.md#superseded-second-backend-the-community-blender-mcp`, which has no heading or
  `<a id>` of that name any more.
- `specifications/testing.md` links to
  `NEXT_STEPS.md#file-upstream-mpfb-cannot-find-a-rigify-meta-rig-any-more`.
- `specifications/architecture.md` links to `CLAUDE.md#the-twenty-five-tools`; the heading is "The
  forty-four tools" now, and changes with every tool added - an explicit `<a id="the-tools">` would
  stop the drift.
- `HISTORY.md` links to `NEXT_STEPS.md#should-the-bridge-serve-its-own-test-harness`.
- `HISTORY.md`'s FR 036 entry links to `NEXT_STEPS.md#resolved-from-and-subject-resolved-by`, the
  entry FR 037 closed and removed. HISTORY is not rewritten, so this one may be left, or repointed at
  FR 037's entry.

The fix is to repoint each at the heading it meant, or drop the anchor where the section is gone. A
small script that checks every `](path#anchor)` against GitHub-style heading slugs and `<a id>` tags
would find the next one, and could become a test beside `tests/test_reference_drift.py` if drift
here turns out to recur.

<a id="viseme-pack-probes"></a>

## An install probe for the viseme packs, in MPFB

`FaceService.is_faceunits01_installed()` exists and is cached; nothing similar exists for
`visemes01` or `visemes02`, so [FR 039](done/039-exporting-characters/README.md) probes each with one
target, the silence viseme, resolved through `TargetService.target_full_path()` - the target MPFB's
`configure_lip_sync()` tests for. A request to MPFB, not a defect: `is_visemes01_installed()` and
`is_visemes02_installed()` beside the face units' probe would let this package use MPFB's own
definition, as [mpfb-integration.md](../specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack)
prefers.

<a id="what-the-all-or-nothing-batches-caught"></a>

## What the all-or-nothing batches caught (keep this)

A note in favour of an existing decision, so it does not get traded away later.

`mpfb_set_material_settings` and `mpfb_set_pose_bones` both refuse the whole call if any entry fails
to resolve, and both paid for themselves in one session:

- A write of `IrisColor` was refused with `unknown_socket` and `closest: ["IrisMinorColor",
  "IrisMajorColor", "IrisSection4Color"]`. The correct names came out of the refusal; nothing was
  half-written.
- A pose call naming `head` twice — once to turn it, once to tilt it — was refused with "bones[1]
  names 'head', already named earlier in this call". Silently applying both would have given a
  rotation that was neither, and it would have been diagnosed from a render much later.

Both are cases where a partial write would have been expensive to detect and impossible to undo
across the socket. Worth keeping, and worth extending to any future tool that writes a batch.
