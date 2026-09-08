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
[FR 008](done/008-detail-targets/README.md); the two rig tools as
[FR 009](done/009-add-rig/README.md), the two asset tools as
[FR 010](done/010-mesh-assets/README.md) and the three material tools as
[FR 011](done/011-skin-and-materials/README.md). **All five landed without live verification**, and
that debt — twelve tools, plus two catalogue verifications made stale by shared-fragment
migrations — was the largest single piece of unfinished business in this file for five requests
running.

**It is paid.** [FR 013](done/013-live-verification/README.md) ran all seven checklists in one
session, rewrote every verification record, found and fixed three defects nothing on this side of
the socket could have caught, and — the part that matters for this file — replaced the session with
[verification/](../verification/), where re-running a checklist after a fix is one command. See its
[entry in HISTORY.md](HISTORY.md) and its
[review](done/013-live-verification/review.md). Six requests were scoped out of it and are listed
below.

What remains unscoped in this area:

- **Expressions and visemes**, the `!ex-` prefixed shape keys.
  [`mpfb_get_target_stack`](done/008-detail-targets/README.md) already reports them behind
  `include_expressions` and deliberately sets none of them: they are neither macro nor modeling
  targets, they are addressed through `TargetService.expression_name_to_shapekey_name()` rather than
  through any category, and MPFB drives them from its own pose/expression UI. A request of their own.
- **Randomization.** `RandomizationService` already implements this inside MPFB, including a second,
  more compact reading of the same `opposites`/side mechanics FR 008 reimplemented
  (`_detail_targets_for_category()`). A tool here should wrap that service rather than rebuild it.

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
[A tool reports an ordering constraint it cannot enforce](../specifications/mutating-tools.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
— and [FR 010](done/010-mesh-assets/README.md) followed it from the other end, reporting
`rigged_to: null` beside `parented_to` for a garment attached to a character that had no rig at that
moment. [FR 011](done/011-skin-and-materials/README.md) turned out to add no ordering constraint of
its own — a skin can be applied at any point — but it did add the mirror image of one, and it is now
a standing convention:
[Where MPFB's UI coerces or re-defaults a service argument](../specifications/mpfb-integration.md#where-mpfbs-ui-coerces-or-re-defaults-a-service-argument-mpfb-mcp-does-the-same-and-reports-both).

**Adding is one asset per call**, not batched like
[FR 008](done/008-detail-targets/README.md)'s target setting: loading an MHCLO is seconds of mesh
import and vertex fitting, so the socket round trip does not dominate and the argument that made
batching mandatory there does not carry over. **Now measured**
([FR 013](done/013-live-verification/README.md)): equipping one asset takes **2.78 s** against a
round trip of **250 ms**, so the transport is 9% of the call and batching could save at most that.
Note the corrected baseline — the ~1.0 s this decision was originally argued against was measured
once, on one tool, and is four times too high; the decision survives on the real number.

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
[FR 012](done/012-observability/README.md)**; see its entry in
[HISTORY.md](HISTORY.md#fr-012--observability-seeing-what-crossed-the-socket).
`MPFB_MCP_RECORD_DIR` and `MPFB_MCP_LOG_LEVEL` are documented in
[CLAUDE.md](../CLAUDE.md#commands). Its one outstanding live check — that a traceback line number
resolves against the dumped program — was the first thing
[FR 013](done/013-live-verification/README.md) did, and it passed.

One piece was explicitly *not* in FR 012 and is now **partly answered**: splitting a call's
duration into transport, `exec`/compile and MPFB's own work. FR 012 refuses to let a diagnostic
setting change the program that is sent, which is the property its record depends on, so FR 013 took
the split ad hoc instead. The answer closed the question rather than opening a request: the socket
round trip is **250 ms** and compiling the largest generated program is **3.7 ms**, about a
thousandth of the call it belongs to. There is nothing left to instrument permanently. What the
split *did* find is a third component nobody was looking for, and it is
[FR 017](017-category-table-cost/README.md).

## Second backend: the community "blender mcp"

mpfb-mcp should also run against the community [blender-mcp](https://github.com/ahujasid/blender-mcp)
add-on, not only blender lab's, so that a user who already has that one installed does not have
to install a second. This is settled as a goal — see
[vision.md](../specifications/vision.md#resolved-which-blender-mcp-both) for the resolution and
for what comparing the two add-ons turned up: the substantive difference is the result channel
(the exec namespace's `result` dict, against captured stdout), so the seam is a backend adapter
below `send_code()` that translates transport and result channel together, leaving the tools,
the payloads and `codegen/` untouched. Not yet scoped into a numbered request.

## Scoped out of FR 013

Six requests, written while [FR 013](done/013-live-verification/README.md)'s findings were fresh and
deliberately kept out of it: folding a refactor into a bug hunt makes every finding ambiguous about
which change caused it. Each is grounded in something the run measured or observed.

- **[FR 014](014-uniform-performed-flag/README.md)** — a uniform `performed` flag beside each
  mutating tool's own verb. Five different names today, and FR 013's harness guessed wrong on three
  tools in one session, each time getting `None` rather than an error.
- **[FR 015](015-fourth-shared-fragment/README.md)** — a fourth shared code-generation fragment, for
  the two duplications whose divergence would be silent, plus the drift census that found them.
  Sixteen of nineteen duplicated payload helpers are byte-identical; nothing has drifted, and these
  two are the ones where it would matter.
- **[FR 016](016-trim-tool-descriptions/README.md)** — trim the tool descriptions from 66.7 KB
  toward ~45 KB by moving rationale into the specifications, and put the response *field names* in.
- **[FR 017](017-category-table-cost/README.md)** — the largest uncosted thing in the package: the
  three tools sharing `target_categories.py` rebuild MPFB's category table from disk on every call,
  at ~1.5-2 s each. Carries the `list_targets` migration below, since both touch that file.
- **[FR 018](018-alternative-material-refresh/README.md)** — `mpfb_list_asset_materials` should be
  able to rescan. The cache it documents as unfixable turns out to have an invalidator nobody calls.
- **[FR 019](019-file-mpfb-defects/README.md)** — file the five confirmed MPFB defects against
  `../mpfb2`, with the reproductions rather than descriptions. Includes the one FR 013 found by
  accident and which is the worst of the set: a user target whose filename is over 56 characters
  prevents MPFB from loading at all.
