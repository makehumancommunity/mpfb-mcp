# Measuring meshes: intersections, and whether a mesh is ready to be an asset

**Status:** Done

This is the first of four requests scoping
[The MakeClothes and MakeSkin workflows](../../NEXT_STEPS.md#the-makeclothes-and-makeskin-workflows),
and the one the others build on: [FR 049](../../049-makeskin-materials/README.md) reports through it,
[FR 050](../../050-writing-mesh-assets/README.md) carries its summary and
[FR 051](../051-delete-groups/README.md) uses its overlap module.

**MPFB's clothes check passed a garment with real defects, and nothing in the forty-four tools can
see two meshes pass through each other.** `ClothesService.mesh_is_valid_as_clothes()` checks vertex
groups, scale and face type. It gave `all_checks_ok: true` for the gi draft, which had a coat with
inward normals (sleeves 8 % outward, back panel 0 %), 77 face pairs of coat through the hakama's
waist, 25 through the body and 14 of one flap through the other. The inverted normals were found only
by plotting the mesh outside Blender.

The same gap appears outside authoring, and three more sessions paid for it
([Nothing reports that two meshes interpenetrate](../../NEXT_STEPS.md#nothing-reports-that-two-meshes-interpenetrate),
[Garment fit intersections](../../NEXT_STEPS.md#garment-fit-intersections)). A hand-holding pose went
from 148 pairs to 0 with a 3.7 mm gap only once a script could count them. A hat buried in hair, at
7903 pairs, was found from a render. So this request builds the measurement once and exposes it
three ways: a general tool, a garment report, and a line in `mpfb_add_asset`'s answer.

**Measured while scoping**, on `/export/3d/taido/taido_gi_v2.blend`, headless, unposed, with
viewport subdivision at level 0: body BVH (26,756 triangles) 18 ms to build, garment BVH (3,905
triangles) 2 ms, `overlap()` about 1 ms. A count is cheap, which is what makes FR 13 reasonable. The
same finished garment scored **6 pairs against the masked body and 613 against the unmasked one**,
and it renders cleanly. That is why both numbers are reported and neither is judged.

## Goals

**Primary:** an agent can ask how much two meshes intersect and how close they come, and can ask
whether a mesh is ready to be written as an asset, getting numbers instead of having to look at a
render.

**Secondary:**

- **`mpfb_add_asset` says when a garment does not fit**, on the call that caused it.
- **A number that cannot be misread.** A count on a masked body sees nothing under the mask, so the
  answer always carries the unmasked count beside it and says which is which.

## Non-goals

- **A verdict.** No threshold turns a count into pass or fail. The finished gi has 613 unmasked pairs
  and is fine.
- **Fixing a fit**, or the fitted-offset slider
  [Garment fit intersections](../../NEXT_STEPS.md#garment-fit-intersections) asks for.
- **A clearance line in `mpfb_place_character`** and the footprint-overlap idea from the same entry.
  Both stay there.
- **Trying an asset on another body.** That is the recipe in
  [FR 050](../../050-writing-mesh-assets/README.md), which uses `mpfb_check_intersections`.
- **A check for the narrow-strip texture warp** (a band one face wide ripples under subdivision). It
  stays a documented trap until a second garment shows that a check would catch it.

## Functional requirements

### What is measured, for all three

1. **Geometry is the evaluated mesh in world space**, so a posed or placed character measures as it
   stands. The answer reports the subdivision level measured at. MPFB's Subdivision modifier was at
   viewport level 0 and render level 1 on the gi, so what is counted is not necessarily what renders.
2. **A body is counted twice:** `face_pairs` with its masks as they are, and `face_pairs_unmasked`
   with the delete-group masks off. **The mask that hides MPFB's helper geometry stays on in both.**
   It is found by its `vertex_group` being `body`, not by its name (`Hide helpers`), because helper
   geometry is not skin and would swamp the count. A mesh that is not a body has `face_pairs` only.
3. **Masks are put back exactly, including after an exception.** A call changes nothing that can be
   observed afterwards, selection and active object included.
4. **Each row says where.** `region` is the world-space box of the intersecting faces, which is what
   `check_gi.py` printed as a z range and what made its numbers actionable.
5. **`min_distance` is the closest approach between the two surfaces**, in metres, and 0.0 when they
   intersect. It is computed from vertices to the other surface, and the description says it is
   therefore an upper bound.
6. **Self-overlap excludes faces that share a vertex**, since every neighbouring pair would count
   otherwise.

### `mpfb_check_intersections`

7. **`name`** is any object in a character's family, `null` meaning the active object. A mesh belonging
   to no character is a subject of one mesh, so a held prop can be measured.
8. **`other`** is optional and resolved the same way. Without it, every pair inside the subject's
   family is measured: the body against each asset, and each asset against each other. With it, every
   pair across the two.
9. **`include_self`** adds each mesh against itself (default false). **`region`**, a box in world
   space, counts only faces inside it.
10. **The answer is capped.** Rows are sorted by count, largest first, with a cap and `pairs_truncated`
    following the summary's rollup. `pairs_measured`, `pairs_clear` and `closest_pair` always cover
    every pair, including those cut.

### `mpfb_add_asset`

11. **Every successful answer gains `intersections`:** a row per pair for the new asset against the
    body and against each other equipped asset, in FR 4's shape, without `min_distance`.
12. **It never refuses.** The asset is equipped and the count reported, and `mpfb_add_asset`'s other
    fields are unchanged.
13. **Always on, subject to the effort's own measurement.** The live check measures the added time on
    a rigged, fully dressed character. If it exceeds a quarter of the call, the field becomes opt-in
    and the request's Outcome says so with the number.

### `mpfb_check_mesh_asset`

14. **`name`** is the mesh being checked; **`basemesh`** is optional and otherwise found the way MPFB's
    panels find it, refused when ambiguous. The mesh need not be marked as an asset yet, and
    `object_type` reports what it is marked as, if anything.
15. **`validator` is MPFB's report unchanged**, with `all_checks_ok` at its top level so that nobody
    mistakes it for this tool's whole answer. MPFB's validator returns early on mixed faces. Everything
    below is still measured.
16. **Per connected component:**
    - faces, vertices and vertex groups;
    - `outward_fraction`: the share of faces whose normal agrees with the nearest body surface's;
    - `fit_offset`: signed `min` and `max` distance from the unmasked body;
    - overlap against the body (both counts), against each other component, and against itself.

    The draft has two components, hakama and coat, with sleeves and flaps all in the second. So
    "under flap through top flap" is that component's self-overlap, and it must be found there.
17. **`uv`:** islands, overlapping islands, faces outside 0..1, and texels per metre as a range and for
    the lowest islands. Reported only when the mesh has a UV map.
18. **`textures`:** every image node's slot, image name, resolved path, whether that file exists, size
    in pixels, colour space, and whether the image is packed or has unsaved changes.
19. **`metadata`:** the three groups a written asset draws on (MakeClothes', MakeSkin's, MPFB's general
    object properties), each value beside whether it was set or is MPFB's default, where
    [that can be told](../../050-writing-mesh-assets/README.md#architecture). MakeClothes and MakeSkin each
    hold their own `license` and `author`, and a disagreement is a `warnings` entry.
20. **`write_state`:** whether the xref cache exists, `asset_source` and whether it still resolves, and
    the named delete group with its vertex count. A viewport subdivision above level 0 is reported
    too, since [FR 050](../../050-writing-mesh-assets/README.md#architecture) found that it changes what
    MPFB's exporter writes.
21. **`sections`** narrows the answer, as `section` does in `mpfb_get_material_settings`. The live
    check measures the full answer on the gi and records it.

## Non-functional requirements

- **Honesty about the mask.** The description of each tool says what a masked count cannot see, since
  that is the trap that disabled the session's own clearance step.
- **Read-only in effect.** All three are safe at any point, which is what makes an agent willing to
  call them after every change. Each tool's description says so.
- **Cheap enough to call in a loop.** The numbers above suggest tens of milliseconds per pair. The
  live check records them posed and subdivided.

## Architecture

- **`shared/mesh_overlap.py`** holds the BVH building, the mask handling, the pair counting, the region
  and the distance. FR 050 and FR 051 import it. It takes `services` only if it has to, because it is
  otherwise plain Blender.
- **`shared/mesh_asset_report.py`** holds the per-component and UV measurements, so that FR 050's write
  answer can carry a summary of the same reading rather than a second opinion. This is the rule
  `mpfb_get_character_summary` already follows.
- **MPFB's property sets for MakeClothes and MakeSkin live on UI modules**
  (`ui.create_assets.makeclothes`, `ui.create_assets.makeskin`). Reach them with `sys.modules.get()` in
  `mpfb_surface.py`, as `RigHelpersProperties` is reached. Both
  [conditions](../../../specifications/architecture.md#a-ui-module-with-no-service-behind-it) hold: MPFB
  imports them while registering its panels, and what they hold is definitions read from JSON, with
  values on the object. A miss is an ordinary answer with a reason.
- **`mesh_is_valid_as_clothes()` creates and deletes temporary objects** through `MeshCrossRef`. The
  bridge tests must show that this leaves the selection and the object list as they were.
- **BVH trees are built from triangulated evaluated meshes**, and a quad face counted as two triangles
  is why a count is a measure of extent and not of faces. The description says "face pairs" and the
  docstring says this.
- **Pitfall:** a depsgraph update is needed after a mask changes and again after it is put back,
  before any later read.

## Affected specifications

- [vision.md](../../../specifications/vision.md#target-tool-catalog): the two read tools, under
  Introspection. Authoring as an area is added by [FR 050](../../050-writing-mesh-assets/README.md).
- [responses.md](../../../specifications/responses.md): reporting a measurement beside what it cannot
  see; `face_pairs` and `face_pairs_unmasked` as vocabulary.
- [tool-interface.md](../../../specifications/tool-interface.md): the glossary (`face_pairs`, `region`,
  `min_distance`).
- [architecture.md](../../../specifications/architecture.md#a-ui-module-with-no-service-behind-it): the
  two property sets as further cases of a readable UI module.
- [testing.md](../../../specifications/testing.md): no change expected.

## Tests

- **Unit, in `tests/`:** argument shape for `mpfb_check_intersections` and `mpfb_check_mesh_asset`, and
  what reaches the wire. No object vocabulary is checked here.
- **`bridge/test/tests/bbb_shared/`:** direct tests of both shared modules, on meshes built with known
  answers: two cubes overlapping by a known amount, a separated pair with a known distance, a mesh with
  faces flipped by a known share, and a mask left exactly as found after an induced failure.
- **`bridge/test/tests/ccc_reading/`:** a real character, proving helper geometry is never counted and
  that a delete group's mask changes `face_pairs` and not `face_pairs_unmasked`.
- **`bridge/test/tests/ddd_mutating/add_asset_test.py`:** the new field, and that it is not a refusal.
- **Live check, a script in this subdir:** `mpfb_check_mesh_asset` on `/export/3d/taido/taido_gi.blend`
  must find the defects in the table above: the coat's low `outward_fraction`, the hakama's near 1.0,
  and coat-versus-hakama, coat-versus-body and coat-self counts of the recorded order. `taido_gi_v2.blend`
  must show them gone. The script skips if the files are absent, and the numbers go in the Outcome. It
  also records `mpfb_add_asset`'s added time (FR 13).
- **Smoke items** for both tools, default arguments, nothing written.

## Outcome

Both tools and the field landed on the two shared modules the request named. Verified by
[`live_check.py`](live_check.py), 26 checks with no failures, on Blender 5.1.0 headless; 744 bridge tests,
630 unit tests, and the smoke run at 48 of 48 in 2.4 s. What the effort settled, found and changed from
the text above:

### `intersections` is opt-in, and this is the number

**FR 13's condition was not met, so the field is opt-in, through a new `measure_intersections` argument
defaulting to false.** On a rigged character dressed with nine assets, timing the function behind the field
inside Blender:

| Asset | The call | The field | Share |
|---|---|---|---|
| Eyes | 44 ms | 10.9 ms | 25 % |
| Eyebrows | 20 ms | 8.6 ms | 44 % |
| Eyelashes | 21 ms | 9.5 ms | 44 % |
| Teeth | 53 ms | 13.0 ms | 24 % |
| Tongue | 24 ms | 10.9 ms | 46 % |
| Hair | 51 ms | 17.8 ms | 35 % |
| Dress | 343 ms | 37.5 ms | 11 % |
| Hat, 2,250 pairs through the hair | 59 ms | 38.5 ms | 65 % |
| Sweater | 151 ms | 47.0 ms | 31 % |

A mean of **36 %, against the line of 25 %**. That was after the work below brought it down from 38 %.

**What the line assumed turned out not to be so.** The request was written from a session where equipping
took seconds, and on a headless Blender it takes 20-60 ms for anything small. The field itself is cheap in
absolute terms, 9-47 ms, and its floor is evaluating and reading the body twice, which no optimisation here
removes. This is the maintainer's to revisit: the call's own share would fall well under the line on a windowed
Blender, where a round trip costs far more, and flipping the default is one word. It is left as the request
says, and NEXT_STEPS records the question.

**The tree is now built only from what can intersect.** Two different surfaces can only intersect inside the box
they share, so a hat asks about a few hundred of the body's triangles and two meshes whose boxes do not meet build
no tree at all. A test holds the limited trees to the whole ones' answer. It took a dressed character's 45 pairs
from 225 ms to 146 ms.

### The draft is not in the file the request named

**`taido_gi.blend` has no inverted coat.** The tool answered 1.0 for its coat, and that was checked three
independent ways before it was believed, because the request said the file had the defect: the polygons' own
normals against the body's agree on 925 of 925 faces. The coat with inward normals is **`gi_draft_mesh`, a mesh
the session stashed inside `taido_gi_v2.blend`**, which is what `build_gi_mesh.py` starts from on every run. The
finished coat's vertices are that file's mirrored in X, which is why a reversed winding reads the same way out
in both. The gi's README calling `taido_gi.blend` "the draft as it was on disk" is true of the file and not of
the mesh the numbers came from. The live check puts the stash on the garment in memory and never saves.

| On the real draft | Measured | Recorded |
|---|---|---|
| Coat `outward_fraction` | **0.0** | sleeves 8 %, back panel 0 % |
| Hakama `outward_fraction` | 0.981 | legs 100 % |
| Coat through the hakama | **77** | 77 |
| Coat through itself | 9 | 14 |
| Coat through the body | 4 masked, 412 unmasked | 25 |
| MPFB's `all_checks_ok` | `true` | `true` |

The 77 is exact. The other two are of the recorded order: the stash meets the delete group as it finished, at
3,209 vertices rather than 2,563, and the recorded 14 and 25 came from a script reading the mesh unevaluated. On
`taido_gi_v2.blend` the hakama and coat read 0.98 and 0.998, and nothing of the coat passes through the hakama.
**The body scores 7 masked and 627 unmasked**, against the 6 and 613 recorded while scoping.

### What the requirements did not anticipate

- **The helper mask needs more than its vertex group (FR 2).** A proxied character's `Hide base mesh` is a `MASK`
  on `body` too, inverted, so finding the helper mask by its group would have left a proxied body reading as
  nothing even "unmasked". It is the group and not inverted, and the inverted one comes off with the delete groups,
  so "unmasked" means the body the garment was fitted to.
- **`min_distance_unmasked` and `region_unmasked` were added**, since the request's trap applies to them as much as
  to the count. The session's own clearance step was disabled by exactly this.
- **A closed shell reads about 0.5 whichever way it faces**, because half of it faces the body. The finished belt
  reads 0.36 to 0.71 and is right. The description says so, or a correct belt reads as a defect.
- **`bpy_extras.mesh_utils.mesh_linked_uv_islands()` was tried first and is wrong for this.** It joins polygons
  holding one UV coordinate in common, whether or not a vertex or edge is shared, so two unrelated islands
  packed corner to corner read as one. Islands are worked out from shared edges instead.
- **A mesh hidden with the eye icon is measured** (FR 1). It is evaluated, measured on a live file, so
  `placement.footprint`'s `visible_get()` test would have dropped real geometry here. One in an excluded collection
  or with `hide_viewport` is reported in `not_measured`, since `evaluated_get()` quietly hands back the original.
- **A region counts a face by its centre.** The request left this open. It also bounds `min_distance`.
- **`metadata`'s "set" is `is_property_set()`**, which answers [FR 050](../../050-writing-mesh-assets/README.md#architecture)'s
  open question: it tells a chosen `CC0` from MPFB's default on the gi.

### MPFB's validator has side effects, confirmed and undone

Provoked on a running install with the cache redirected to an empty directory, and filed in
`mpfb2/efforts/bugs/local/mcp-discovered-bugs.md`:

- **It creates `basemesh_xref` when absent**, because `MeshCrossRef` does for any `cache_dir` it is given, and MPFB's
  panel and writer check only that the directory exists. So after a check, MPFB believes an empty directory is a cache.
  The command removes a directory it caused and `write_state` looks inside rather than at the name.
- **It leaves orphaned meshes behind**: two per call here, `base.001` and `g.001`, since `MeshCrossRef` deletes its copy's
  object and not the copied data. They are removed after the call.
- **It takes 7.9 s with no cache** rather than the 30 s FR 050 gives for building one, and the description says so.

### Sizes and times

The full `mpfb_check_mesh_asset` answer is **6.8 KB on the draft, 11.5 KB on the finished gi, at 650 and 980 ms**. So
`sections` narrows an answer under the 16 KB line, and it exists because the request asked for it rather than because
that was crossed. `mpfb_check_intersections` on the gi takes about 30 ms; on the dressed character, with 45 pairs at 7.5
KB, 146 ms, and 211 ms posed.

## Decisions taken while scoping

Asked on 2026-11-03:

- **Two tools in one request, on one module**, rather than `mpfb_check_intersections` in its own earlier
  request or left in NEXT_STEPS.
- **`mpfb_add_asset` reports intersections always**, measured first and falling back to opt-in if
  expensive. Opt-in from the start and leaving it out were the alternatives.

*Not asked*, each argued where it is stated: the name `mpfb_check_mesh_asset`, since the
[glossary](../../../specifications/tool-interface.md) reserves "clothes" for quoting MPFB and MakeClothes
writes all three kinds of mesh asset; both counts rather than the unmasked one alone (FR 2); no verdict
(Non-goals); per connected component plus self-overlap, measured against the draft's real two
components (FR 16).

## References

- [NEXT_STEPS: The MakeClothes and MakeSkin workflows](../../NEXT_STEPS.md#the-makeclothes-and-makeskin-workflows),
  [Nothing reports that two meshes interpenetrate](../../NEXT_STEPS.md#nothing-reports-that-two-meshes-interpenetrate),
  [Garment fit intersections](../../NEXT_STEPS.md#garment-fit-intersections).
- `interacting_with_blender/taido/gi/tools/check_gi.py`, and the scripted checks under
  `interacting_with_blender/photo_studio_verification/` and `man_and_woman_holding_hands/`.
- mpfb2: `services/clothesservice.py` (`mesh_is_valid_as_clothes`), `services/humanservice.py`
  (the `Hide helpers` mask), `entities/meshcrossref.py`.
