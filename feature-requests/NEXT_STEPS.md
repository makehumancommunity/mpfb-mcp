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
**Neither landed with live verification**, and neither did [FR 009](done/009-add-rig/README.md)'s
two rig tools. The outstanding checks overlap heavily — they all need the same dressed, rigged
character and all compare against MPFB's own panel — so they are **one session's work rather than
three**, and that session is the largest single piece of unfinished business in this file. It has
four parts:

- [FR 007](done/007-macro-details/README.md#verification-status) — phenotype sliders, refit, and the
  generated-Rigify-with-no-meta-rig branch of `mpfb_refit_human`.
- [FR 008](done/008-detail-targets/README.md#verification-status) — that a modifier set through
  `mpfb_set_targets` reads back on MPFB's own slider.
- [FR 009](done/009-add-rig/README.md#verification-status) — that rigging after dressing really does
  leave the clothes unrigged, and the full Rigify sequence in both orders.
- **A re-check of [FR 004](done/004-list-rigs/README.md)**, whose live verification FR 009 made
  stale: `payloads/list_rigs.py` was migrated onto the shared `rig_lookup.py` fragment, so the
  program sent into Blender is a different program even though the unit tests see no behavior
  change. Cheap to redo — it is a read-only call — and it belongs in the same session because
  FR 009's own weights checks compare against its output.

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

- ~~Add rig, including a custom rig~~ — landed as [FR 009](done/009-add-rig/README.md); see its
  [entry in HISTORY.md](HISTORY.md)
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
no unload counterpart for it, and [FR 009](done/009-add-rig/README.md) refuses to add a second rig
rather than pretend otherwise. That refusal is now implemented, so an agent that rigs a character
wrongly has to delete the armature through generic blender_mcp and start again — worth revisiting if
it turns out to bite.

**Ordering between the three is a real constraint that produces no error.**
`add_mhclo_asset()` rigs a garment only if a rig exists at that moment, and nothing re-rigs it
afterwards; Rigify generation has to come after the garments. MPFB's own character builder documents
this in comments. None of the tools can enforce it, so each reports when it can see the caller
violating it. [FR 009](done/009-add-rig/README.md) landed that as a standing convention —
[A tool reports an ordering constraint it cannot enforce](../specifications/architecture.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
— so FR 010 and FR 011 follow it rather than restate it.

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
