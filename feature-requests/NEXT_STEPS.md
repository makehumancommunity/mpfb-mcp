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
two rig tools, [FR 010](done/010-mesh-assets/README.md)'s two asset tools or
[FR 011](done/011-skin-and-materials/README.md)'s three material tools. The outstanding checks
overlap heavily — they all need the same dressed, rigged character and all compare against MPFB's
own panel — so they are **one session's work rather than six**, and that session is by far the
largest single piece of unfinished business in this file. It has seven parts, and it is now scoped
as [FR 013](013-live-verification/README.md), which also carries a re-runnable harness — one of the
two things that would stop the postponement repeating. The other, being able to see the exact
program sent into Blender and the response that came back, was pulled out of it and **has landed**
as [FR 012](done/012-observability/README.md); see [Observability](#observability) below. The seven
parts are kept below as the original statement of what is wanted:

- [FR 007](done/007-macro-details/README.md#verification-status) — phenotype sliders, refit, and the
  generated-Rigify-with-no-meta-rig branch of `mpfb_refit_human`.
- [FR 008](done/008-detail-targets/README.md#verification-status) — that a modifier set through
  `mpfb_set_targets` reads back on MPFB's own slider.
- [FR 009](done/009-add-rig/README.md#verification-status) — that rigging after dressing really does
  leave the clothes unrigged, and the full Rigify sequence in both orders.
- [FR 010](done/010-mesh-assets/README.md#verification-status) — the largest of the six, and the
  one where the stubs establish least: that a garment equipped through `mpfb_add_asset` is
  indistinguishable from one equipped through MPFB's asset library panel, each of the eight
  `asset_type` values at least once, the **proxy divergence measured rather than read from source**,
  and removal end to end. It also settles FR 009's ordering claim from the other end, and doubles as
  the first live evidence that FR 007's refit does anything at all — so **whichever of the two gets
  there first settles it for both**.
- [FR 011](done/011-skin-and-materials/README.md#verification-status) — the three material tools,
  and the part of the session with the least stub backing of all: a material *is* a node tree, and
  nothing in the suite builds one. All five `skin_type` values against MPFB's own skin library
  panel, the material-instance slots and their settings, the settings file created once and not
  twice, `scale_assumption` at a non-default scale, a body-proxy character, `LAYERED` with no MHMAT,
  both directions of `mpfb_set_asset_material` plus `restore_default`, the alternative-material
  cache staleness, and per-skin-type cost against FR 005's baseline. It needs the same dressed
  character as the four above, with a skin installed to put on it.
- **A re-check of [FR 004](done/004-list-rigs/README.md)**, whose live verification FR 009 made
  stale: `payloads/list_rigs.py` was migrated onto the shared `rig_lookup.py` fragment, so the
  program sent into Blender is a different program even though the unit tests see no behavior
  change. Cheap to redo — it is a read-only call — and it belongs in the same session because
  FR 009's own weights checks compare against its output.
- **A re-check of [FR 005](done/005-list-assets/README.md)**, stale for exactly the same reason:
  FR 010 migrated `payloads/list_assets.py` onto the shared `asset_sections.py` fragment. Also a
  read-only call, and also in the same session, since FR 010's `resolved_path` is compared against
  its output.

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
  Note that this is now the **only** payload left unmigrated: [FR 009](done/009-add-rig/README.md)
  migrated `list_rigs.py` onto `rig_lookup.py` and [FR 010](done/010-mesh-assets/README.md) migrated
  `list_assets.py` onto `asset_sections.py`, both at the price of a stale live verification. The
  same price applies here, and the difference remains that this payload's overlap is a *shape*
  difference rather than a vocabulary two tools have to agree on.

## Loading / applying assets

The next logical step would be the ability to add assets to a character. All three bullets below
are now scoped into numbered requests, one per domain; the bullets are kept as the original
statement of what was wanted. All three have landed.

- ~~Add rig, including a custom rig~~ — landed as [FR 009](done/009-add-rig/README.md); see its
  [entry in HISTORY.md](HISTORY.md)
- ~~Add an MHCLO asset: needs to take asset type and material type as parameters~~ — landed as
  [FR 010](done/010-mesh-assets/README.md), which also covers *removing* one; see its
  [entry in HISTORY.md](HISTORY.md)
- ~~Set skin: needs to take material type as parameter~~ — landed as
  [FR 011](done/011-skin-and-materials/README.md), which also covers swapping an equipped asset's
  material and the small catalogue that had to exist for it; see its
  [entry in HISTORY.md](HISTORY.md)

The split is by domain rather than by size: rigs go through a different, non-interchangeable pair
of `HumanService` functions; an MHCLO asset is an imported object; and a skin is a material applied
to objects that already exist. Three decisions taken across them are worth knowing about from
here.

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
— and [FR 010](done/010-mesh-assets/README.md) followed it from the other end, reporting
`rigged_to: null` beside `parented_to` for a garment attached to a character that had no rig at that
moment. [FR 011](done/011-skin-and-materials/README.md) turned out to add no ordering constraint of
its own — a skin can be applied at any point — but it did add the mirror image of one, and it is now
a standing convention:
[Where MPFB's UI coerces or re-defaults a service argument](../specifications/architecture.md#where-mpfbs-ui-coerces-or-re-defaults-a-service-argument-mpfb-mcp-does-the-same-and-reports-both).

**Adding is one asset per call**, not batched like
[FR 008](done/008-detail-targets/README.md)'s target setting: loading an MHCLO is seconds of mesh import and vertex fitting, so the ~1 s socket round trip
does not dominate and the argument that made batching mandatory there does not carry over. That
decision is implemented but not yet *measured*; the cost check is part of FR 010's outstanding live
verification above.

### Still unscoped in this area

- **Poses.** `mpfb_list_assets` reports the `poses` subdir, so the catalogue currently names things
  no tool can apply. `AnimationService.import_bvh_file_as_pose()` is the operation; it is
  destructive (it changes bone rolls) and only works on the `default` rig, which makes it a request
  of its own rather than a fourth bullet above.
- **Ink layers.** Likewise listed by `mpfb_list_assets` (`ink_layers`) and likewise a different
  mechanism: `MaterialService.load_ink_layer()` adds a UV map and a layer to an existing MakeSkin or
  Layered skin material, works on no other material type, and is invisible when a body proxy is
  present. [FR 011](done/011-skin-and-materials/README.md) excluded them **explicitly** rather than
  by omission, and it is also what makes them reachable: an ink layer needs a MakeSkin or Layered
  skin to attach to, and `mpfb_set_skin` is what puts one there. This is the next material request,
  and its dependency has landed.
- **Installing asset packs and targets** (`mpfb.load_pack`, `mpfb.install_target`) — the operations
  that put new entries into the catalogues in the first place.

## Observability

The original entry — "logging should be added so that it is possible to see the exact python code
sent to blender, and the reponses that came back" — **landed as
[FR 012](done/012-observability/README.md)**; see its entry in [HISTORY.md](HISTORY.md#fr-012--observability-seeing-what-crossed-the-socket).
`MPFB_MCP_RECORD_DIR` and `MPFB_MCP_LOG_LEVEL` are documented in
[CLAUDE.md](../CLAUDE.md#commands). One live check of it is still owed and is the first item of
[FR 013](013-live-verification/README.md)'s session.

One piece was explicitly *not* in FR 012 and stays unscoped here: **splitting a call's duration into
transport, `exec`/compile and MPFB's own work.** Doing that means instrumenting the generated
program, and FR 012 refuses to let a diagnostic setting change the program that is sent — which is
the one property its record depends on. FR 013 takes the split ad hoc instead, through the
envelope's `stdout`. If it turns out to be wanted permanently, it is a request of its own.

## Second backend: the community "blender mcp"

mpfb-mcp should also run against the community [blender-mcp](https://github.com/ahujasid/blender-mcp)
add-on, not only blender lab's, so that a user who already has that one installed does not have
to install a second. This is settled as a goal — see
[vision.md](../specifications/vision.md#resolved-which-blender-mcp-both) for the resolution and
for what comparing the two add-ons turned up: the substantive difference is the result channel
(the exec namespace's `result` dict, against captured stdout), so the seam is a backend adapter
below `send_code()` that translates transport and result channel together, leaving the tools,
the payloads and `codegen/` untouched. Not yet scoped into a numbered request.
