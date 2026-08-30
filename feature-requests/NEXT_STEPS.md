# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## Modeling

Most of the things in this section is done via TargetService. Macrodetails and phenotype landed as
[FR 007](done/007-macro-details/README.md) and detail targets as
[FR 008](done/008-detail-targets/README.md); see their entries in [HISTORY.md](HISTORY.md).
**Both landed without live verification**, and the outstanding checks overlap heavily — they need
the same dressed, rigged character and both compare against MPFB's own panel — so they are one
session's work rather than two. That session is the largest single piece of unfinished business in
this file.

What remains unscoped in this area:

- **Expressions and visemes**, the `!ex-` prefixed shape keys.
  [`mpfb_get_target_stack`](done/008-detail-targets/README.md) already reports them behind
  `include_expressions` and deliberately sets none of them: they are neither macro nor modeling
  targets, they are addressed through `TargetService.expression_name_to_shapekey_name()` rather than
  through any category, and MPFB drives them from its own pose/expression UI. A request of their own.
- **Randomization.** `RandomizationService` already implements this inside MPFB, including a second,
  more compact reading of the same `opposites`/side mechanics FR 008 reimplemented
  (`_detail_targets_for_category()`). A tool here should wrap that service rather than rebuild it.
- **Migrating `mpfb_list_targets` onto the shared category-table fragment.** FR 008 added
  `codegen/shared/target_categories.py` and deliberately left
  [`payloads/list_targets.py`](../src/mpfbmcp/codegen/payloads/list_targets.py) alone: it is
  live-verified, and its scan has a genuinely different shape — a flat user-target listing carrying
  `listed_in_mpfb_ui`, with no synthesized categories at all. The two now walk the same directories
  by different routes, which is a drift risk rather than a bug. Worth doing when something else
  needs to touch that payload anyway, and worth doing *with* a live re-verification.

## Loading / applying assets

The next logical step would be the ability to add assets to a character. All three bullets below
are now scoped into numbered requests, one per domain; the bullets are kept as the original
statement of what was wanted.

- Add rig, including a custom rig — [FR 009](009-add-rig/README.md)
- Add an MHCLO asset: needs to take asset type and material type as parameters —
  [FR 010](010-mesh-assets/README.md)
- Set skin: needs to take material type as parameter — [FR 011](011-skin-and-materials/README.md)

The split is by domain rather than by size: rigs go through a different, non-interchangeable pair
of `HumanService` functions; an MHCLO asset is an imported object; and a skin is a material applied
to objects that already exist. Three decisions taken across them are worth knowing about from here.

**Removing is in scope alongside adding**, for mesh assets. `HumanService.unload_mhclo_asset()` also
takes off the delete-group mask modifier and the garment's sub-rig, neither of which a plain object
deletion through generic blender_mcp would touch — so without it an agent that equips the wrong
garment has no correct way to take it off. Removing a *rig* is deliberately not in scope: MPFB has
no unload counterpart for it, and [FR 009](009-add-rig/README.md) refuses to add a second rig rather
than pretend otherwise.

**Ordering between the three is a real constraint that produces no error.**
`add_mhclo_asset()` rigs a garment only if a rig exists at that moment, and nothing re-rigs it
afterwards; Rigify generation has to come after the garments. MPFB's own character builder documents
this in comments. None of the tools can enforce it, so each reports when it can see the caller
violating it — a convention [FR 009](009-add-rig/README.md) proposes recording in
[architecture.md](../specifications/architecture.md).

**Adding is one asset per call**, not batched like
[FR 008](done/008-detail-targets/README.md)'s target setting: loading an MHCLO is seconds of mesh import and vertex fitting, so the ~1 s socket round trip
does not dominate and the argument that made batching mandatory there does not carry over.

### Still unscoped in this area

- **Poses.** `mpfb_list_assets` reports the `poses` subdir, so the catalogue currently names things
  no tool can apply. `AnimationService.import_bvh_file_as_pose()` is the operation; it is
  destructive (it changes bone rolls) and only works on the `default` rig, which makes it a request
  of its own rather than a fourth bullet above.
- **Ink layers.** Likewise listed by `mpfb_list_assets` (`ink_layers`) and likewise a different
  mechanism: `MaterialService.load_ink_layer()` adds a UV map and a layer to an existing MakeSkin or
  Layered skin material, works on no other material type, and is invisible when a body proxy is
  present.
- **Installing asset packs and targets** (`mpfb.load_pack`, `mpfb.install_target`) — the operations
  that put new entries into the catalogues in the first place.

## Observability

Logging should be added so that it is possible to see the exact python code sent to blender,
and the reponses that came back.

## Second backend: the community "blender mcp"

mpfb-mcp should also run against the community [blender-mcp](https://github.com/ahujasid/blender-mcp)
add-on, not only blender lab's, so that a user who already has that one installed does not have
to install a second. This is settled as a goal — see
[vision.md](../specifications/vision.md#resolved-which-blender-mcp-both) for the resolution and
for what comparing the two add-ons turned up: the substantive difference is the result channel
(the exec namespace's `result` dict, against captured stdout), so the seam is a backend adapter
below `send_code()` that translates transport and result channel together, leaving the tools,
the payloads and `codegen/` untouched. Not yet scoped into a numbered request.
