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

The `list_targets` migration this section has flagged as a drift risk since FR 008 is also done:
[FR 017](done/017-category-table-cost/README.md) pointed `payloads/list_targets.py` at
`codegen/shared/target_categories.py`, so the catalogue and the three tools that act on it now read
one scan of the user target directories rather than two.

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
batching mandatory there does not carry over. **That reasoning is now known to be wrong, and the
decision needs re-taking.** FR 013 measured one asset at **2.78 s** against a "round trip" of
250 ms and concluded transport was 9% of the call.
[FR 017](done/017-category-table-cost/README.md) then measured what a round trip actually is:
250 ms per 4 KB of program against a busy Blender, 1 s per 4 KB against an idle one. The
`mpfb_add_asset` program is 44.7 KB — eleven chunks, about 2.75 s busy — so the 2.78 s was
**almost entirely transport**, and MPFB's mesh import and vertex fitting are a few hundred
milliseconds of it at most. Batching two garments into one call would therefore save close to a
whole call, not 9% of one. Nothing has been changed on the strength of this: it is a measurement
that reopens a decision, and re-taking it is a request of its own — one that should also weigh
sending `asset_sections.py` once per session, which is the cheaper half of the same saving and is
[listed below](#scoped-out-of-fr-013).

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

One piece was explicitly *not* in FR 012 and is now **answered**: splitting a call's duration into
transport, `exec`/compile and MPFB's own work. FR 012 refuses to let a diagnostic setting change the
program that is sent, which is the property its record depends on, so FR 013 took the split ad hoc
instead, and [FR 017](done/017-category-table-cost/README.md) finished it. Compiling the largest
generated program is **3.7 ms**, about a thousandth of the call. Transport is not a constant at all:
it is **250 ms per 4 KB of program** against a busy Blender and **1 s per 4 KB** against an idle one,
because the add-on reads one 4 KB chunk per timer tick — so for most tools here it is not one
component of the call but nearly all of it, and MPFB's own work is the small remainder. There is
still nothing left to instrument permanently, for the same reason: the duration is predictable from
`len(program)`, which the record already holds.

## File the 4 KB chunked read against blender_mcp

**The largest single cost in this package is one line in an add-on we do not own.**
blender_mcp's `mcp_to_blender_server._service_clients()` does exactly one `conn.recv(4096)` per
timer tick and then returns, so a request arrives at one 4 KB chunk per tick — 250 ms each while
the add-on is busy, and 1 s each once five seconds have passed without a request *finishing*, since
bytes arriving do not reset its idle countdown. A generated program therefore costs about 250 ms
per 4 KB, or 1 s per 4 KB against the idle Blender an agent actually meets, **regardless of what
the program does**: a 50 KB call is 3 s or 12 s of waiting before Blender has read the request.
Measured, and predicted to within a few percent, by
[verification/measure.py](../verification/measure.py)'s `transport_by_program_size`; the model and
its consequences are in
[architecture.md](../specifications/architecture.md#what-a-call-costs-is-the-size-of-its-program).

Draining the socket in a loop until it would block, instead of reading once, would remove most of
that from every tool here and from every other client of that add-on. It is not fixed here because
blender_mcp is treated as external and unmodified (see
[No direct dependency](../specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp)),
so this is a bug report to write, with the measurement attached — the same shape as
[FR 019](019-file-mpfb-defects/README.md), which files five MPFB defects with their reproductions
rather than their descriptions. [FR 017](done/017-category-table-cost/README.md) worked around it
where it could, by sending each shared fragment once per Blender session; the workaround stays
worth having afterwards, an order of magnitude smaller.

Worth doing at the same time: the same file's `_MAX_REQUEST_BYTES` and the add-on's
`timer_interval_active` preference are the two other numbers a user can be told about today. Setting
that preference to its module default of 0.05 s makes every call in this package four to five times
faster, which is worth a sentence in [CLAUDE.md](../CLAUDE.md) whether or not the upstream fix
lands.

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
which change caused it. Each is grounded in something the run measured or observed. **Three have
landed**: [FR 014](done/014-uniform-performed-flag/README.md) gave every mutating tool a uniform
`performed` flag beside its own verb, as `codegen/shared/performed.py`, and
[FR 015](done/015-fourth-shared-fragment/README.md) added the fifth and sixth fragments —
`refit_blocker.py` and `modifier_reading.py` — plus the drift census, now
[verification/census.py](../verification/census.py). See their
[entries in HISTORY.md](HISTORY.md); and [FR 016](done/016-trim-tool-descriptions/README.md) took
the tool descriptions from 70.4 KB to 47.5 KB and left `tests/test_description_budget.py` behind,
so the next drift is a failing test rather than a discovery.

**[FR 017](done/017-category-table-cost/README.md) has landed too**, and it did not find what it
went looking for: MPFB's category table costs 4 ms to rebuild, and the 1.5-2 s it was blamed for is
the *transport of the code describing it*, at 250 ms per 4 KB against a busy Blender and 1 s per
4 KB against an idle one. What it built is a session cache of fragment **source** rather than of the
table, which is why no tool gained a `refresh` and the description budget did not move. Its live run
also cleared **FR 015's outstanding re-verification**. Two remain.
- **[FR 018](018-alternative-material-refresh/README.md)** — `mpfb_list_asset_materials` should be
  able to rescan. The cache it documents as unfixable turns out to have an invalidator nobody calls.
- **[FR 019](019-file-mpfb-defects/README.md)** — file the five confirmed MPFB defects against
  `../mpfb2`, with the reproductions rather than descriptions. Includes the one FR 013 found by
  accident and which is the worst of the set: a user target whose filename is over 56 characters
  prevents MPFB from loading at all.

One follow-up FR 017 leaves behind, small and deliberately not done there: **only the four tools
that share `target_categories.py` go through `shared_cache.send()`**. `mpfb_add_asset` and
`mpfb_set_skin` carry `asset_sections.py` on every call, and the two rig tools carry
`rig_lookup.py`; nothing about those is different in kind, and each is one line in a tool module.
