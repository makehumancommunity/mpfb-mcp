# Generating a delete group

**Status:** Done

The last of four requests scoping
[The MakeClothes and MakeSkin workflows](../../NEXT_STEPS.md#the-makeclothes-and-makeskin-workflows). It
uses [FR 048](../048-measuring-mesh-assets/README.md)'s overlap module, and its result reaches a file
through [FR 050](../050-writing-mesh-assets/README.md).

**The delete group was the longest part of the gi session: eleven runs of a ray-casting script.** A delete
group hides the body under a garment, and it can fail in two opposite ways. Too small, and skin pokes through
on another body or in a pose. Too large, and dark slits open where someone can see in through an opening.
At the gi's V-neck, a fixed margin was wrong both ways: 3.5 cm left dark slits inside the lapel on the
authoring body, and 7.5 cm left skin poking through the coat on the posed template. The group went from 2,563
to 3,209 vertices.

**MPFB's own operator can't help.** `mpfb.makeclothes_gendelete` calls its result "very rough", tells the user
to edit it by hand, and refuses any garment with a modifier, which includes MPFB's own Subdivision.

**This is a real algorithm, and it carries research risk that the other three requests do not.**
`extend_delete_group.py` proves the idea, not the generality: it hard-codes the gi's openings as world-space
thresholds (`abs(x) > 0.3` is a cuff, `z < 0.2` a hem, `z > 1.24` the neck) and reads a `gi_part` attribute that
only that session created. So this request opens with a spike, and may stop there.

## Goals

**Primary:** one call gives a garment a usable delete group on a body, with no margins to find by trial and
error, and two numbers saying how each failure mode stands.

**Secondary:**

- **Rerunnable.** The session's script kept the draft's group so that every run started from it, because a
  group that only grows cannot be tuned.
- **Visible before it is applied**, through `dry_run`.

## Non-goals

- **Guaranteeing a result on every body and pose.** The group is computed on the authoring body, and skin
  appearing on another body is found by [FR 050's recipe](../050-writing-mesh-assets/README.md#documentation).
  The margins exist to make that rare.
- **Wrapping `mpfb.makeclothes_gendelete`.** Offered as a lower-risk start and declined. Its result is what
  this replaces.
- **Writing the group into a file.** [FR 050](../050-writing-mesh-assets/README.md) does that.
- **Editing a group by hand or by a vertex list.** Generic Blender work remains the way, and the two measures
  below report on any group, however it was made.

## The spike

**Before any tool code, a script in this subdir answers one question: can a garment's openings be classified
automatically?** The algorithm has to treat them differently: at a neck the body stays still relative to the
opening and visibility decides, while at a cuff or hem the limb moves inside the wide sleeve and a margin
decides.

- **Find the openings:** the garment's boundary edges joined into loops. This part is straightforward.
- **Classify them.** Candidate signals, for the spike to compare:
  - which rig weights dominate the body vertices nearest a loop, which needs a rig;
  - the basemesh's `joint-*` helper groups near it, which do not;
  - how loose the opening is, from the gap between the loop and the body.
- **Against at least three garments:** the gi draft, as ground truth, with its group of 3,209; and two of
  different construction with authored delete groups already in the library, a one-piece dress
  (`toigo_keyhole_neck_dress`, which fits cleanly) and a suit with a collar (`mindfront_m_suit_01`). Both MHCLOs
  carry `delete_verts`. An authored group is a sanity check rather than ground truth, since it was made by a
  person with other goals.

**If no signal classifies all three, the request stops and says so in its Outcome.** The fallback would be
caller-supplied margins per opening, which was offered and declined as a first choice. Choosing it then is a
decision to bring back to the maintainer, not one to take during implementation.

## Functional requirements

1. **`name`** is the garment; **`basemesh`** is optional and found by `subject_resolution.resolve_asset_body()`, as in FR 048 and FR 050. **`delete_group`** defaults to
   the object's `MC_delete_group`.
2. **Modifiers are no obstacle.** It works on the garment's stripped mesh, unlike MPFB's operator.
3. **A candidate is a `body` vertex whose normal ray hits the garment** within a maximum gap (0.14 m in the
   script). Helper geometry is never considered.
4. **Near an opening the body keeps, it asks what can be seen:** a body vertex stays visible if a sight line
   from it reaches open air without crossing the garment, tested over a set of directions (240 in the script)
   that face away from the skin by at least a minimum. Such a vertex stays out of the group.
5. **A collar of skin stays around anything visible** (three rings in the script), because of how a mask removes
   faces (see Architecture).
6. **Near a limb's opening, a margin keeps skin in play**, large enough for a limb to move inside the sleeve (7
   cm at the cuffs and 16 cm at the hems in the script).
7. **Single-vertex holes are filled**, since each would leave faces standing.
8. **`dry_run`** computes and reports everything and writes nothing.
9. **`mode`** is the package's existing word: `merge` (default) keeps members from before the first run, as the
   script did, and `replace` starts empty. The group as it was before the first run is kept as a vertex group
   named `<group>.original`, so that a second run starts from there, and is reported as `original_kept_as`.
10. **The answer:**
    - `vertices_before`, `vertices_after`, `added` and `removed`;
    - **`masked_skin_still_visible`** and **`unmasked_skin_under_garment`**, counted on what the loaded asset
      would actually mask (below). These are the request's two failure modes as numbers;
    - **`openings`**: each with its kind, its centre, the margin used, and the reason it was classified that
      way, so that a wrong classification can be seen rather than inferred;
    - `mask_modifier_present` for the group on this body. The tool adds no modifier, as the panel adds none.
11. **Optional `margins`** override a kind's margin, for a garment the defaults do not suit. They override and
    never replace the classification.

## Non-functional requirements

- **Time:** a sight-line test per vertex near an opening is the costly part. The live check records it on the
  gi, and a call over 10 s on a typical garment is a defect to fix before landing. The script's 240 directions
  are a starting point rather than a requirement.
- **Determinism:** the same mesh gives the same group, so that a rerun's differences mean something. The
  direction set is fixed.
- **Explainability:** the answer says why, because this is the tool most likely to be wrong in a way that shows
  only on another body.

## Architecture

- **`shared/delete_group.py`**, using `mesh_overlap.py` for the unmasked body and its BVH. The constants live at
  the top under names that say what each is for, with the gi as their provenance.
- **An authoring body and a loaded asset mask differently. Read from source, to be provoked.** On the authoring
  body a Mask modifier removes any face touching a group member. When MPFB loads an asset,
  `ClothesService._conservative_mask()` first removes from the group every vertex in a partly covered face,
  moving the boundary inward by about a ring. So the group that looks right in the authoring scene is not the
  one the next character gets. The answer's two counts use the second, reimplementing the rule, with a bridge
  test against MPFB's private function so that drift is noticed.
- **The measure must not be blind.** Masks off, by
  [FR 048's rule](../048-measuring-mesh-assets/README.md#what-is-measured-for-all-three), which is what silently
  disabled the session's own clearance step.
- **A mutation with no undo across the socket.** The group is on the basemesh and may be large (3,209 vertices,
  about 20 KB as a list), so `restore_with` as a vertex list is not reasonable. `<group>.original` is the undo,
  and [the rule for destroying state](../../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list)
  is met by naming it. Live-check that the extra group reaches no export or MHCLO.
- **Group names differ in practice:** the gi's is `delete`, MPFB's default is `Delete`, and an equipped asset's is
  `Delete.<name>`. All are honoured as given, and none is assumed.
- **A posed or turned character, which [FR 050](../050-writing-mesh-assets/README.md) established for matching.**
  A posed body baked into an MHCLO: one thigh changed 793 of 2,674 lines. A turned one too, since offsets are in world
  axes: 2,670 of them at 90 degrees. Whether sight lines suffer the same way is this request's to provoke; if they do,
  refuse as it does, with `rig_not_at_rest` and `character_turned`, reading `pose_reading.deforming_bones_off_rest()`.

## Affected specifications

- [mutating-tools.md](../../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list):
  a kept copy as the undo for something too large to return.
- [mpfb-integration.md](../../../specifications/mpfb-integration.md): a tool that replaces an MPFB operator's result
  rather than reproducing it, and why the "reproduce quirks" rule does not apply.
- [vision.md](../../../specifications/vision.md#target-tool-catalog): one more authoring tool.
- [tool-interface.md](../../../specifications/tool-interface.md): the two count names, and `<group>.original`.

## Tests

- **Unit, in `tests/`:** argument shape, `mode`, `margins`' keys and finite positive values, and what reaches the
  wire.
- **`bbb_shared/`:** `delete_group.py` on constructed cases with known answers: a tube around a cylinder with one
  open end, proving a visible band at the opening and full coverage beyond it; a collar's width; a hole being
  filled; the conservative-mask rule against MPFB's private function.
- **`ddd_mutating/`:** on a real character with a mesh extracted from a helper group: `dry_run` changes nothing;
  `merge` from `<group>.original` across two runs; `replace`; helper vertices never included.
- **Live check, a script in this subdir, on the three garments of the spike:** starting from the gi's draft group
  of 2,563, the result must be of the order of 3,209, with no dark slits on the authoring body and no skin on the
  posed template, verified by `mpfb_check_intersections` after the write and by renders kept in this subdir. The
  masked and unmasked counts on all three go in the Outcome.
- **Smoke item** with `dry_run`.

## Outcome

**Landed: `mpfb_generate_delete_group`, one tool and a shared module, and the spike did not stop it.** On the gi, from
the draft's 2,563, it gives **3,199 vertices in 0.59 s**, every one of them a member of the session's 3,209,
with the V, both cuffs and both hems found by reading the mesh rather than by `abs(x) > 0.3` and `z > 1.24`. The session
took eleven runs. Renders are in `renders/`, clean on the authoring body and in both of the Taido template's poses. The
check is [`live_check.py`](live_check.py), 39 of 39, reading the gi, the template and the two library garments.

### The spike

[`spike.py`](spike.py), run by [`spike_run.py`](spike_run.py), results in
[`spike_results.json`](spike_results.json). Over the 24 loops longer than 10 cm on the three garments, against a
person's labels:

| Signal | Right | Where it fails |
|---|---|---|
| Which `joint-*` chain passes through the loop | **24 of 24** | |
| Which rig weights dominate | 22 of 24 | a sleeveless armhole reads as a cuff. It also needs a rig, and the gi has none |
| How loose the opening is | 18 of 24 | the suit's trouser hems and shirt cuffs fit like a neck |

So the chains, with no rig needed. **An arm's chain starts at the shoulder joint**, which is what keeps an armhole out.

**It also found what the request had not asked**, on the first run: a boundary loop is not always an opening. The gi's
waistband lies over the coat, the suit's jacket over its shirt, and its buttons' rims on the jacket. So two questions come
first, per vertex: is there garment between it and the skin, and can it see open air? Only a vertex passing both sets a
margin or a sight zone, and a loop with none is `covered`. On the gi's coat that leaves 64% of the loop, which is what the
script's `z > 1.24` was doing by hand.

**A closed shell has no boundary at all.** Four of the eleven garments tried are shells: gloves, boots, a scrub top and a
sweater. Nothing says where their openings are, so skin under one is sight-tested wherever it is, no margin applies, and the
answer warns (`closed_components`). That errs toward keeping skin.

### The counts

Faces, on the bodies the garments were authored on or loaded on. `visible` and `under` are
`masked_skin_still_visible` and `unmasked_skin_under_garment`, counted as a loaded asset masks, and `here` is
`masked_skin_still_visible_authoring`.

| Garment | Group | Vertices | Visible | Under | Here |
|---|---|---:|---:|---:|---:|
| Gi | the draft | 2,563 | 59 | 971 | 79 |
| Gi | the session's | 3,209 | 101 | 411 | 145 |
| Gi | **generated, `merge` from the draft** | **3,199** | **101** | **421** | **145** |
| Dress | authored | 1,330 | 38 | 150 | 78 |
| Dress | generated, `merge` | 1,376 | 43 | 113 | 91 |
| Dress | generated, `replace` | 974 | 9 | 456 | 35 |
| Suit | authored | 3,432 | 138 | 377 | 140 |
| Suit | generated, `merge` | 3,444 | 138 | 372 | 140 |
| Suit | generated, `replace` | 2,246 | 5 | 1,625 | 8 |

**Generated from nothing, a group errs toward leaving skin**: far fewer slits than a person's and a good deal more skin
under the cloth, which only shows if it pokes through elsewhere. Which is right depends on the garment, and `merge` is the
default because a person's group is usually a better start. Nonzero is normal: the finished gi renders clean at 101 and 145,
of which the draft's own members are 59 and 79, under layers a sight line just slips between.

**Worn in a pose**, `mpfb_check_intersections`, masked and unmasked pairs, against the session's own asset on the same scene:
`chudan_gamae` 160 and 876 against 157 and 876, `gedan_gamae` 114 and 1,249 against 107 and 1,249. On the authoring body it
is 11 and 627. In `chudan_gamae`'s side view a dark sliver shows inside the far lapel, on the session's asset and this one
alike, the two renders differing by 0.09%: whatever it is, this group did not bring it.

### What landed differently

- **A third count, `masked_skin_still_visible_authoring`.** The first full run, with every check passing, rendered **black
  wedges on the authoring body's chest**. The request's two counts are of a loaded asset, a ring smaller, and did not move
  by one. So a group has two lives and the answer now counts both. The renders are what found this, which is why they stayed
  in the check.
- **The wedges were a defect of generalising the script.** It measured a margin to each edge's midpoint and sight-tested
  what got through. Measured to the edge, nearly everything beside a lapel was kept untested and grew no collar. A vertex
  a margin keeps is now tested too, and FR 5's collar grows from it. `bbb_shared/delete_group_test.py` holds that.
- **One sight line, as asked, after trying two.** One in five of the vertices eroding the suit's group did so by a single
  line, and before the collar was fixed two lines gave it 2,671 vertices from empty rather than 2,262, but opened the gi's
  wedges wider. With the collar fixed two is clean on the gi as well, and adds 34 vertices the session's group does not have.
  With one it adds none, so the request's rule stands, and the suit's erosion is what `unmasked_skin_under_garment` is for.
- **What is masked once loaded is not `_conservative_mask()` alone.** `Mhclo.load()` appends the first index of each `a - b`
  range twice and the function removes one occurrence per partly covered face, so a vertex starting a run survives one
  such face. The gi's 3,209 leave **2,698** on a character where the rule says 2,680. Reproduced, held to a loaded asset by
  a bridge test, and compared with the two posed scenes by the live check. Filed.
- **Skin in front of the garment is not a slit.** Within 20 cm of the trunk openings sight lines alone called 103 of the gi's
  faces slits, and 45 of those were at its waist and back, where the hakama lies just under the skin: removing them shows the
  hakama, which is what a mask is for. A slit now needs the garment's nearest point on its outward side.
- **`masked_skin_still_visible` stops 20 cm from an opening.** Further up a trouser leg a sight line needs an eye on the floor,
  and with no such limit they were most of the count: 285 faces rather than 103, for a group rendering clean.
- **A turned character is not refused**, which the request left to be provoked. Sight lines are read in the body's own frame,
  so a turn changes nothing, measured on a tube and a character. A pose does change the group, so `rig_not_at_rest` stands.
- **`cuff`, `hem`, `trunk`, and `covered` beside them.** The script's "neck" would have named an armhole and a keyhole wrongly.
- **Budgets.** Descriptions to 104,700 B and schemas to 22,000 B, for one tool of 2,800 B.

### What was not done

- **A group is judged on one body at rest**, as the request says. A garment on a different shape is the recipe's to find.
- **Skin poking out of the garment on the authoring body is not added** unless already a member, because a candidate is a
  vertex whose normal hits the garment (FR 3). `mpfb_check_intersections` is what finds it.
- **A low-rise waist could read as a hem**, if both leg chains start above it. None of the eleven does. `reason` and `limbs`
  would show it, and `margins` soften it.
- **`<group>.original` has no tool to put it back**, which the request accepted: it is generic Blender work.

## Decisions taken while scoping

Asked on 2026-11-03:

- **A generalised sight-line test with automatic classification**, behind a spike that may stop the request.
  Caller-supplied margins, and measuring first while wrapping MPFB's rough result, were the alternatives.
- **Its own request**, so that the research risk cannot hold up FR 048-050.

*Not asked*, each argued where it is stated: `<group>.original` as the undo (Architecture); `merge` by default
(FR 9); counting on what the loaded asset would mask rather than on the authoring body (Architecture); adding no
modifier (FR 10).

## References

- [NEXT_STEPS: The MakeClothes and MakeSkin workflows](../../NEXT_STEPS.md#the-makeclothes-and-makeskin-workflows).
- `interacting_with_blender/taido/gi/tools/extend_delete_group.py`, the algorithm's only implementation, with
  every constant above.
- mpfb2: `ui/create_assets/makeclothes/operators/gendelete.py`, `services/clothesservice.py`
  (`create_new_delete_group`, `update_delete_group`, `_conservative_mask`).
