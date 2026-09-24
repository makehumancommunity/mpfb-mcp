# History of completed efforts

A running log of development efforts that have **landed**. It is the finished counterpart to
[NEXT_STEPS.md](NEXT_STEPS.md), which tracks only the remaining/active work. When an effort is
completed its entry moves here (see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

Entries are ordered by feature-request number and are deliberately terse: each says what landed
and what is worth remembering about it. The individual `NNN-*/README.md` subdirs remain the
authoritative record of what was planned, decided and verified, and the standing
[specifications/](../specifications/) remain the source of truth for current behavior.

The initial `mpfb_create_human` proof of concept predates this feature-request process and
has no numbered entry here or in `done/`; see [CLAUDE.md](../CLAUDE.md) for what it covers.

## [FR 001](done/001-mpfb-get-status/README.md) — `mpfb_get_status`

The first introspection tool: takes no arguments and always answers, classifying the connected
Blender's MPFB install as `absent`, `not_initialized` or `ok` and — when `ok` — reporting version,
paths, data roots, asset packs, Rigify availability and Blender version. It also split the
`sys.modules` MPFB scan into a shared helper with two variants, one raising and one classifying.
Landed without live verification; the outstanding checks were cleared by
[FR 013](done/013-live-verification/README.md).

## [FR 002](done/002-codegen-structure/README.md) — code generation restructured into per-tool payload files

Replaced the central `mpfb_codegen.py` with a `codegen/` package: one ordinary-Python payload file
per tool, with parameters arriving as data rather than substituted into the source, so a
caller-supplied string could never alter a program about to be `exec()`'d. It established that
readability and developer experience are prioritized non-functional requirements, generated code
included. The whole path was deleted by [FR 033](done/033-retire-the-generated-code-path/README.md).

## [FR 003](done/003-object-finding/README.md) — object finding and identification

`mpfb_list_objects` and `mpfb_get_object_info`, the layer every later tool needs in order to name
its subject. Both are read-only and neither selects or activates anything. The theme is that an
empty or absent answer must never be ambiguous: `type_recognized` beside MPFB's own `known_types`,
an unresolvable subject as a successful answer, and every relative carrying `in_current_scene`.
It recorded how a tool addresses an object and how it reports the asset behind one. Its live pass
came later, and found one defect: `rigify_role` was reported for a relative but not for the subject.

## [FR 004](done/004-list-rigs/README.md) — `mpfb_list_rigs`

The first catalogue, and the reason it exists is the `identifier` field: a rig's bare name is not
what an adding function takes, and the two adding functions are not interchangeable — hence
`add_function` beside it. Each entry also predicts which weights adding it would load, by mirroring
MPFB's fallback table rather than testing for a file, since two bundled rigs ship no weights of
their own and are not unweighted. It recorded how tools name things that can be added. Live-verified
during the effort: all 13 identifiers added cleanly to a scratch basemesh.

## [FR 005](done/005-list-assets/README.md) — `mpfb_list_assets`

The catalogue for what can be put *on* a character, and the first answer that did not fit — the
verification install holds 730 assets — so it is filtered, capped, paged and reports `total_count`
and `truncated`. That became the standing rule for bounding a large answer. Each entry names the
asset three ways: the passable `path`, the portable `fragment` MPFB writes onto the object, and
`object_type`, which doubles as `add_mhclo_asset()`'s `asset_type`. `pack` is the project's first
*derived* field — 9% of assets are claimed by more than one pack, so `pack_ambiguous` is ordinary.

## [FR 006](done/006-list-targets/README.md) — `mpfb_list_targets`

The morph catalogue a setter has to be able to read. Bundled targets are indexed by a ~140 KB
`target.json` no response should carry, so the tool reports its *path* and pages through one
section at a time; user directories have no index and are scanned per call, which is what lets it
see a target installed since Blender started. The field it exists for is `shapekey_name`: above 60
characters MPFB *encodes* the name, and addressing such a target by filename reads back `0.0`
silently. A section's `source` can be `"both"` — 8 of 27 are, which the request had not expected.

## [FR 007](done/007-macro-details/README.md) — macro details, refit, and the first mutating tools

`mpfb_get_macro_details`, `mpfb_set_macro_details` and `mpfb_refit_human`. Before them a character
was frozen at creation. Writing a macro property does nothing on its own — the shape is a stack
MPFB recomputes from all eleven values — so the tools write every named property and call
`reapply_macro_details()` **once**, never reimplementing the interpolation. It recorded how a
mutating tool takes its subject, that it reports before and after, and that preconditions are
answers; and it settled that `mpfb_create_human` keeps flat sliders rather than a nested dict.

## [FR 008](done/008-detail-targets/README.md) — detail targets, and the batched mutating tool

`mpfb_get_target_stack`, `mpfb_set_targets` and `mpfb_symmetrize_targets`. A modeling slider is not
a shape key: it is a category running −1.0 to +1.0 built from a pair of opposing targets, so the
tools work at both the category level and the raw shape-key level. `mpfb_set_targets` is the one
batched tool and **resolves every entry before writing any**. Symmetrize zeroes the opposing target
first, or pruning deletes the wrong half of a pair, and `mpfb_get_target_stack` reads `key_blocks`
directly, because `TargetService` cannot see a shape key whose name *contains* "basis".

## [FR 009](done/009-add-rig/README.md) — adding a rig, and the ordering constraint nothing enforces

`mpfb_add_rig` and `mpfb_generate_rigify_rig`, the first consumers of FR 004's catalogue. The
interesting half is that MPFB's services have implicit sequencing that produces no error when
violated: a garment is rigged only if a rig exists when it is attached, and nothing re-rigs it
later. No call can validate a sequence, so the standing rule is that a tool which can *observe* the
violation reports it — `mpfb_add_rig` returns `mesh_assets_not_rigged`. Generation is a separate
tool for the same reason: the correct order cannot be written as one call.

## [FR 010](done/010-mesh-assets/README.md) — equipping and removing mesh assets

`mpfb_add_asset` and `mpfb_remove_asset`. Removal was in scope from the start because deleting the
object leaves the body's mask modifier and the garment's sub-rig behind. `asset_type` is
**required**, since MPFB's `"Clothes"` default is wrong for six of the eight types and wrong
silently. Two rules came out of it: an acting tool accepts every identifier its catalogue reports
(`path` or `fragment`, always echoing `resolved_path`), and where MPFB's own code paths disagree,
mpfb-mcp picks one and names it.

## [FR 011](done/011-skin-and-materials/README.md) — skins, asset materials, and the UI's own defaults

`mpfb_set_skin`, `mpfb_set_asset_material` and `mpfb_list_asset_materials` — the end of grey
characters. The durable finding is that **a service signature's default is not always the product's
default**: `set_character_skin()` disagrees with MPFB's own panel about `skin_type` and
`material_instances`, so the tools follow the panel and report requested beside used.
`mpfb_set_asset_material` has no service function at all and reimplements a UI operator, keeping
three of its quirks; `skin_type` is checked locally because a bad value destroys every material.

## [FR 012](done/012-observability/README.md) — observability: seeing what crossed the socket

The first effort that adds no tool. `MPFB_MCP_RECORD_DIR` keeps a per-call record and
`MPFB_MCP_LOG_LEVEL` attaches a stderr handler; both are off by default, and off means no directory
created and identical bytes on the wire. The request is written **before** the socket call, so a
hang, a timeout or a crash still leaves behind what caused it. `FastMCP()` calls
`logging.basicConfig()`, so gating on the root logger would have switched this on for everyone —
which is why [stdout belongs to the transport](../specifications/observability.md#diagnostics-attach-at-the-socket-boundary-never-inside-blender) is a standing rule.

## [FR 013](done/013-live-verification/README.md) — the live verification, and the harness that makes the next one cheap

Cleared a debt five requests and twelve tools deep: all eight outstanding checklists ran green.
Three claims that had only been readings of MPFB's source became observations, three defects were
found that nothing on this side of the socket could have caught, four decisions had been argued
against a round-trip figure four times too high, and of seven candidate MPFB defects four were
confirmed and two refuted. Its lasting contribution is procedural: a live check is a re-runnable
script, and a `Done` with verification outstanding says so on its status line.

## [FR 014](done/014-uniform-performed-flag/README.md) — one name for "it happened", across the eleven mutating tools

Every mutating tool reported success under its own verb — `added`, `applied`, `removed`,
`generated` — and reaching for the wrong one yields `None` rather than an error. FR 013's harness
guessed wrong on three tools in one session. Every mutating tool now also reports **`performed`**, a
real boolean; nothing was renamed. The flag is genuinely not the verb in four cases, including a
dry run and a batch that fails on one entry, which is what made this a request rather than a rename.

## [FR 015](done/015-fourth-shared-fragment/README.md) — the two duplications that would have drifted silently, and the census that keeps the question cheap

Of nineteen duplicated helpers across the payloads, sixteen were byte-identical and nothing had
drifted; **two** were merged. The criterion is consequence, not size: four copies of the
refit-blocker *condition* would be a real hazard, four copies of the *message* phrasing would not,
so the fragment exposes a predicate and each caller phrases its own answer. The modifier-reading
merge was a genuine reconciliation — the two implementations differed in shape — and one test runs
both over one character and compares every category reading.

## [FR 016](done/016-trim-tool-descriptions/README.md) — the tool descriptions trimmed, and the budget that keeps them trimmed

**70,352 B of descriptions to 47,759 B**, so an MCP client preloads 55,864 B rather than 78,457 B.
Half the saving was in things the request had not identified: **10 KB was whitespace**, because
`Tool.from_function()` takes `fn.__doc__` verbatim and every line carried its source indentation,
and the conventions twenty tools each repeated moved to the server instructions, which are sent
once. The measurement became [test_description_budget.py](../tests/test_description_budget.py), a
ceiling the suite asserts against the server `build_server()` actually builds.

## [FR 017](done/017-category-table-cost/README.md) — what a call actually costs, and the fragment sent once per session

**The request was wrong about where the time went, and finding that out was the result.** The
category-table rebuild it blamed takes 4.0 ms; the cost was transport, charged by the byte, at
roughly 250 ms per 4 KB busy and 1 s per 4 KB idle whatever the program did. So the thing worth
caching was the code, not the answer: a shared fragment's source was kept inside Blender keyed by a
hash of itself, cutting the three heaviest tools by 1.5-1.8 s per call. A cache of the *table*, with
a directory-mtime signature, was built first and thrown away when it was measured.

## [FR 018](done/018-alternative-material-refresh/README.md) — `mpfb_list_asset_materials` gains `refresh`

FR 011 documented the alternative-material listing as unfixably stale; FR 013 found that half false
- `AssetService.invalidate_alternative_materials_cache()` exists, nothing called it. This effort
wired it up as `refresh` (default `false`, rejected locally unless a real `bool`), reported back
through a new `cache_invalidated` field because the invalidator is global - it clears every asset's
cached scan, not only the one named in the call - and a tool whose `refresh` quietly resets state
other tools depend on has to say so. The docstring dropped its "restart Blender" remedy. Live
verification ([`check_fr018.py`](done/018-alternative-material-refresh/check_fr018.py)) equipped an
MHCLO asset, wrote a probe `.mhmat` beside it on disk, and confirmed a plain call still misses it
while `refresh=true` clears the cache and sees it - twice, once against a cache a prior run had
already warmed, which the global clear reached anyway.

## [FR 019](done/019-file-mpfb-defects/README.md) — the confirmed MPFB defects, written up where MPFB's own effort will read them

The first effort whose deliverable is in another repository and the first that changes no behaviour:
[`MCP_DISCOVERED_BUGS.md`](../../mpfb2/features/MCP_DISCOVERED_BUGS.md), six confirmed defects
worst-first, each with the code path, the observed values and the probe that provokes it. Nine
candidates went in and six came out, which is why this was separate from the effort that found the
evidence. **Filing is not fixing**: every workaround stays until a running MPFB no longer needs it.
Correcting the two refuted candidates cost more — they were cited as reasons in six places.

## [FR 020](done/020-trim-claude-md/README.md) — the root CLAUDE.md trimmed, and the rule that keeps it trimmed

The root [CLAUDE.md](../CLAUDE.md) had grown from 92 to **704 lines** at about +65 per effort.
Length was the symptom; the finding was that it had become a second copy of documentation held
elsewhere, and the copies had begun to disagree — five factual errors, each surviving because only
one of two copies was ever updated. It is now **268 lines** and a map rather than a manual, and the
standing test discipline gained a home in [testing.md](../specifications/testing.md). The lifecycle
changed with it: a finished effort adds no narrative paragraph to CLAUDE.md.

## [FR 021](done/021-split-architecture-spec/README.md) — architecture.md split into per-topic specifications

`architecture.md` had reached 870 lines, of which eighteen sections were standing conventions about
tool behaviour rather than architecture. Two measurements made that a finding: the document already
delegated twice, and its 195 anchored inbound links were section-level — nobody linked to "the
architecture". It is now seven documents, none over 180 lines, with section text moved verbatim and
the move checked rather than asserted. The link checker grew to cover `.py` files and immediately
found four docstring links that had been one directory level too shallow since FR 011.

## [FR 022](done/022-trim-vision/README.md) — vision.md made about the vision

374 lines, of which **296 were the target tool catalog** — 79% of a document about why the project
exists, and 21 of its 23 entries described shipped tools in a third copy of their own reference
documentation. It is now **137 lines**: capability areas that do not need editing when a tool ships,
plus what is still missing. Two things were rescued rather than cut — *what makes something a tool*,
and the sentence the project turns on: the measure is not how much of MPFB is reachable but how few
round trips and how little source-reading a competent agent needs to get a character right.

## [FR 023](done/023-verification-smoke-test/README.md) — the live verification becomes a smoke test

FR 013 was right that a live check must be a script; putting every script in `verification/` was the
part that did not survive eight efforts — 5,308 lines re-proving forever claims already folded into
the specifications. `verification/` is now one item per tool, default arguments, three shallow
assertions, **3,822 lines deleted**. Two mechanisms keep it from regrowing: coverage is derived from
the tool registry, and an exhaustive live check now belongs to the feature request that needs it, in
that request's own subdir, moving to `done/` with it.

## [FR 024](done/024-documentation-urls/README.md) — links to documentation and other online resources

`mpfb_list_urls` reads MPFB's community addresses out of `ui/weburls.py`; `mpfb_list_docs` reports
addresses for nineteen curated documents the extension does not ship. Two shapes new to the package:
`list_urls` is the only tool that **catches a connection failure and answers anyway**, from a
vendored copy, because the download link is the answer precisely when nothing is running; and
`list_docs` reaches no Blender at all. A standing constraint was settled — mpfb-mcp opens no network
connection except the one to the add-on, so a tool may hand out a URL but never retrieve one.

## [FR 025](done/025-character-presets/README.md) — saving, listing and loading character presets

`mpfb_list_presets`, `mpfb_save_preset` and `mpfb_create_human_from_preset`. The durable part is
that this is the first effect that outlives the `.blend`, which is where the rules come from:
address the artifact by **name, never a path**, validate that name on this side of the socket,
refuse to overwrite by default, and put the absolute path in every answer including refusals. The
name rule lives on both sides of the socket deliberately, since a gap would let a preset be written
under a name that cannot be loaded back. The `save_clothes` argument that is never read was filed.

## [FR 028](done/028-pivot-to-specific-addon/README.md) — the pivot to a bridge add-on, decided and proved

The project changed its mind about where the Blender-side logic belongs: from generated Python
`exec()`'d by a third party's add-on to a companion extension of our own dispatching a closed
vocabulary. The liabilities escaped are an eight-step install, arbitrary code execution by
construction, and a wire cost proportional to program size. FR 028 decided it, proved the transport
and **migrated no tool**. Its live check found that `bpy.app.timers` never fire in `--background`,
so the start operator now refuses it; and that `bpy.app.online_access` does not gate a loopback bind.

## [FR 029](done/029-bridge-transport-and-skeleton/README.md) — the bridge grows a skeleton, and a second way to drive it

Built everything a *second* command would have wanted. A command is now a record — handler,
parameter tuple, `requires_mpfb` — and `dispatch()` applies all three before the handler runs, so
MPFB's absence is the `mpfb_unavailable` refusal rather than somebody else's traceback.
`commands/table.py` is written out rather than assembled by decorators or a scan, which keeps the
vocabulary closed and readable. `blender --background --command mpfb_bridge` was built now because
the bridge's own suite runs headless: 7 tests became 35. The Blender floor was raised to 5.0.0.

## [FR 030](done/030-backend-seam/README.md) — the backend seam, and the first migrated tool

The stage where mpfb-mcp learned to talk to the bridge. `backend.send()` is an adapter below the
send, and the test of that is a diff: the migrated tool shows its send call replaced and nothing
else, the other twenty-four show no diff at all. It also landed the client half of the handshake —
one `get_status` probe per address, which is the only thing that can say *which end* to upgrade.
`mpfb_list_objects` was migrated, chosen for being dull, and with it the largest question this
effort settled: [a tool is tested where it runs](../specifications/testing.md#a-tool-is-tested-where-it-runs).

## [FR 031](done/031-introspection-and-catalogues-migrated/README.md) — introspection and catalogues migrated

The other nine read-only tools, and with them the shared fragments. A shared concept on the bridge
is a module and visibly not a command; what the bootstrap used to bind became a parameter, so a
disabled-and-re-enabled MPFB cannot leave a stale dict behind and a category table is never a
snapshot taken at startup. **Six claims about MPFB turned out differently than the stubs asserted**,
and none was repaired, since a tidy-up during a migration is indistinguishable from a migration
defect. The cost was measured: tens of KB of program became tens of bytes, seconds became one tick.

## [FR 032](done/032-creation-and-modification-migrated/README.md) — creation and modification migrated

The remaining fourteen tools, and in its last commit **the default flipped to the bridge**. A spike
went first and retired the largest risk: everything works headless, Rigify included. A mutating tool
cannot be compared by calling it twice, so the live check used *same starting state, one call each,
compare the answer and the scene* — which is also how the preset file turned out to be starting
state rather than an expected difference. Three more claims about MPFB were corrected, one a real
defect filed upstream, and `mpfb_list_urls`' handshake refusal is deliberately an error.

## [FR 033](done/033-retire-the-generated-code-path/README.md) — the generated-code path retired

Deleted `codegen/` entire — the assembler, the bootstraps, twenty-four payloads, seven shared
fragments — plus `shared_cache.py`, `connection.py` and every test that exercised any of it. **The
unit suite went from 1,059 tests to 353** and lost about 23,800 lines, while nothing a tool answers
changed. It began with a precondition check, since a payload removed while its tool still needs it
is caught by no test that survives the same commit. Keeping the seam proved its own point: no tool
module ever learned which transport it was on, so none had to learn there was now one.

**What the path cost**, since this is the only record of it. blender_mcp's add-on read one 4 KB
chunk per timer tick and did nothing else with it, so a generated program cost about **250 ms per
4 KB** against a recently-used Blender and **1 s per 4 KB** against an idle one, whatever it
computed. Hence "the round trip is 250 ms" was a measure of one *tick*; prose in code sent over a
wire was the one place readability was a trade rather than a straight win; and **not sending
something beats not doing it** — MPFB's category table took 4 ms to rebuild and 1.1 s to describe.
The session cache that coped with this cached *source*, keyed by a hash of itself, because a cache
of code keyed by a hash of that code cannot be stale where a cache of answers about the disk can.

**What verification lost, and it is not nothing.** `verification/harness.py` had a private channel
into Blender and used it to make a scratch scene, snapshot twelve `bpy.data` collections, clean up
and compare. The bridge executes nothing, and a harness is not a reason to give it an `exec`
command, so the channel has no replacement: a run now leaves five MakeHuman objects and ~500 Rigify
widgets behind, which `mpfb_list_objects` cannot even see.
[verification/README.md](../verification/README.md#what-fr-033-cost-this-instrument) carries this
where a passing run will be read, and whether the bridge should serve its own harness is
[an open question](NEXT_STEPS.md#should-the-bridge-serve-its-own-test-harness).

## [FR 026](done/026-face-units/README.md) — `mpfb_get_face_units` and `mpfb_set_face_units`

The first tools to reach the `!ex-` shape keys that drive an ARKit face: `mpfb_get_face_units`
reads the live 52-unit expression, always reporting `known_face_units` (grouped by region) and
`faceunits01_installed` regardless of whether a subject resolves; `mpfb_set_face_units` composes
one, batched like `mpfb_set_targets`, refusing the whole call on an unrecognised name (with
closest-match suggestions) or on the `faceunits01` asset pack being absent. **The first tool pair
gated on an optional asset pack rather than on MPFB itself**, which
[mpfb-integration.md](../specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack)
now states as a standing pattern: probe the pack's own installed-check, report it on every
dependent answer, refuse a write rather than succeeding emptily, and keep a per-item resolution
failure (`could_not_load`) separately reportable even after the probe passes, since the probe tests
one target and a partially installed pack passes it anyway. `refit` defaults to **true** here,
unlike every other refitting tool — said here at the time to match MPFB's composer-panel default,
which [FR 027](done/027-expression-library/README.md) found to be wrong: the composer's `auto_refit`
is `false`, and the default was kept on its own merits. What it writes is
transient — not saved by `mpfb_save_preset`, destroyed by anything that rebuilds MPFB's
applied-expressions stack — which [mutating-tools.md](../specifications/mutating-tools.md#a-tool-whose-effect-is-known-in-advance-to-be-transient)
now covers as its own case. A live check confirmed three things this side of the socket could not:
`set_expression()` returns normally rather than raising with the pack absent; `mpfb_set_targets`
cannot create a `!ex-` shape key from nothing but can write one that already exists; and refitting
after composing an expression really does move a fitted eyebrow asset further than not refitting.
Queued behind it: [FR 027](done/027-expression-library/README.md), the saved-expression library and
the stack that applies it.

## [FR 027](done/027-expression-library/README.md) — listing, applying and saving expressions

Four tools over the *library* half of `FaceService`: `mpfb_list_expressions` (the installed
expression files, addressed by `fragment`, with the files MPFB's scan drops reported as
`unreadable` and `shadowed`), `mpfb_get_expression` (the applied-expressions stack on a character),
`mpfb_apply_expressions` (change the stack, batched, `merge` or `replace`, and let MPFB rebuild the
face) and `mpfb_save_expression` (keep the live face as an expression file). Thirty-one tools,
thirty commands. **The effort turned on one comparison MPFB never makes**: the composer writes the
`!ex-` shape keys directly, the library rebuilds them from the stack and clears first, so composed
work dies silently on the next library change. `shared/expression_divergence.py` compares the
stack's aggregate with the live face, and `mpfb_get_expression`, `mpfb_apply_expressions` and an
extended `mpfb_set_face_units` all report it — `matches_stack`, `unexplained_face_units` — replacing
the fixed "transient" sentence FR 026 put in every answer. Saving is the bridge between the halves,
and the round trip it makes possible — compose, save, apply `replace`, preset — was run end to end
and returned the composed face to within the file's four-decimal rounding.

Decisions worth finding later. **`mpfb_save_expression` saves the shape keys, not the composer's
sliders**, which MPFB's own save operator reads and `mpfb_set_face_units` never writes. **It
refuses a name a higher-priority data root would hide** (`name_shadowed`): MPFB keeps the first
root's file, user data is third, and MPFB's composer panel and data README both say the opposite —
the live check confirmed the code. **MPFB's panel is kept honest** by calling `write_slider_values()`
and `refresh_expression_sliders()` from its `useexpression` UI module, through `sys.modules`, which
[architecture.md](../specifications/architecture.md#a-ui-module-with-no-service-behind-it) now
records as a third case of reaching a UI module: calling one, where MPFB makes the same call after
the same change. **The name rule was generalised rather than copied**: `preset_names.py` became
`artifact_names.py` on both sides of the socket, the noun its only argument, and the drift test
runs every name as a preset and as an expression. That touched shared code on both sides, a
deliberate exception to "adding a tool touches exactly four things"; so did two new shared modules
(`expression_divergence.py`, `expression_panel.py`), taking `shared/` from seven to ten.
**`mode` is not a local-vocabulary exception** as the request planned: no MPFB function sees it, so
it is a shape. **`mpfb_apply_expressions` takes `fragment` only**, because a stack row is one and a
path converts back lossily.

What the effort found by running things. A bridge round-trip test showed that
`discarded_face_units`, as first written — the divergence measured *before* the call — reported the
save-then-replace sequence as losing every composed unit, when it loses none; it is now the units the
rebuild actually moved, measured on both sides. FR 026's reason for `mpfb_set_face_units`' `refit`
default was wrong (the composer's `auto_refit` is `false`) and was corrected everywhere it was
stated. `mpfb_set_face_units` also lacked the selection restore every other refitting command has
around `refit()`; it was added to it and to `mpfb_apply_expressions`, though no disturbance could be
provoked on this install even with a garment equipped, and the test that pins it says so. Three
`FaceService` defects were filed as items 8-10 of `mpfb2/features/MCP_DISCOVERED_BUGS.md` — the
shadowing, and FR 026's two (`set_expression()` cannot report failure; the pack probe's cache is
never invalidated). Three candidates were deliberately not filed; the request says why.

Verified by [`live_check.py`](done/027-expression-library/live_check.py) (23 checks, through the
real tools over the socket to a headless Blender), 42 new bridge tests (349 in all), 42 new unit
tests (423) and four smoke items; the smoke run is 33 items in 1.5 s, and now leaves a second file
outside the `.blend`, which [verification/README.md](../verification/README.md) names.

## [FR 034](done/034-character-summary/README.md) — `mpfb_get_character_summary`

One call that tells an agent enough about one character to plan a change — phenotype, rig,
equipped assets, skin, target rollup, face — replacing the five or six an agent used to make.
Thirty-two tools, thirty-one commands. **The effort was mostly an extraction**: the request's rule
was that the summary is never a second opinion, so the reading code of `get_macro_details`,
`get_object_info` and `get_target_stack` moved into `shared/macro_reading.py`, `asset_info.py` and
`target_rollup.py` (ten shared modules become thirteen), one command per commit, and the summary
reads every section through those and FR 027's `expression_divergence.py`. The basemesh resolver
moved with the macro reading, because the summary promises to resolve its subject as
`mpfb_get_macro_details` does; the other seventeen copies were left, and `set_macro_details`' own
copy of the phenotype reading was found and queued beside them in
[NEXT_STEPS.md](NEXT_STEPS.md#one-basemesh-resolver).

**Each move was proven by a snapshot diff, not only by the bridge tests.** The live check's
`--snapshot` writes every detailed command's answer on its worst-case character — under three
argument sets for `get_target_stack`, and the misses — to one sorted JSON file; taken before the
first move and after each, the three diffs were two added `macro_drift` lines and then nothing.
[testing.md](../specifications/testing.md#two-patterns-for-a-claim-about-more-than-one-command) now
names that, and the agreement test (dispatch the summary beside each detailed command, assert every
shared field equal), as patterns.

Decisions worth finding later. **`macro_drift` compares weights as well as names**: moving a slider
without a recalculation usually changes only weights, so the names-only comparison the request
described would have missed the commonest drift; it is false at the sliders' extremes and on
preset-loaded characters, and was added to `mpfb_get_macro_details` so the summary still reports
nothing a detailed tool does not. **The rig is MPFB's own answer** —
`find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")` — never a garment's subrig.
**`skin.material_type` is MPFB's `identify_material()` name** (`enhanced_skin`, `layered_skin`), not
`mpfb_set_skin`'s `skin_type` vocabulary as the request assumed.

**The request's 8 KB target could not be met uncapped.** On the worst case — every macro moved, a
generated Rigify rig, all eight asset types, 41 categories set with every sided one lopsided, an
expression and two composed units — `get_target_stack`'s rollup alone was 61 modifiers and 20
asymmetries, about 8.8 KB. As the request prescribed for that case, the rollup is capped, at 25 and
8: the entries furthest from zero, in the detailed tool's own order so a capped list is a sub-list,
with `modifier_count`, `asymmetry_count` and an always-present `rollup_truncated` — not `truncated`,
which `get_target_stack` already uses for its paging. The summary contract is now
[a section of responses.md](../specifications/responses.md#a-summary-is-never-a-second-opinion).
Measured on the wire: **7,440 B**, and **14 ms** against **20.6 ms** for the six calls it replaces.
The request's premise of ~250 ms per round trip belonged to the deleted generated-code path; on the
bridge a round trip is a millisecond or less, so the saving is mostly in what an agent reads, not in
latency.

Verified by [`live_check.py`](done/034-character-summary/live_check.py) (57 checks, over the socket
to a headless Blender) and, for the timer-driven path the headless runs cannot reach, the same
comparisons against the two preset-built characters in a windowed Blender (46 checks, about 4.6 KB
each). Ten new bridge tests (359 in all), five new unit tests (428) and one smoke item; the smoke run
is 34 items in 1.5 s.

## [FR 035](done/035-bridge-test-layers/README.md) — bridge tests grouped into ordered layers

The bridge's test modules had carried MPFB's three-letter prefix without its purpose: the letter
recorded the order modules were written in, read-only commands ran after the sixteen mutating
ones, and the one prefixed directory sorted between flat files only because pytest 8 sorts files and
directories together. **Now only directories are prefixed, and each is a layer** that assumes
every earlier one passed — `aaa_addon/`, `ccc_reading/`, `ddd_mutating/`, `eee_composite/`, with
`bbb_shared/` reserved and not created — so `-x` stops a run at the lowest layer that is broken
instead of letting thirty command modules report one transport fault thirty times. Modules inside
are unprefixed and named after their subject, for a command the command name exactly, and their
order means nothing; a layer that needs an internal order is two layers. The rule is in
[testing.md](../specifications/testing.md#two-harnesses-split-at-the-directory-boundary), the
per-layer obligations in each layer's `__init__.py`, and `TEST_MODULE` now takes a layer as well
as a module ([bridge/test/README.md](../bridge/test/README.md#running)).

The two modules whose claim spans several commands — the character summary beside its detailed
commands, and the three expression-aware commands agreeing — went to `eee_composite/` rather than
staying with the commands they dispatch. `list_urls`, one of three commands declaring
`requires_mpfb=False`, went to `ccc_reading/` rather than `aaa_addon/`, because its subject is
still what MPFB answers. `ddd_mutating/__init__.py` kept its cleanup rules and lost its reason for
existing, which had been running short of letters; testing.md carried the same claim and was
corrected with it.

Verified by [`compare_runs.py`](done/035-bridge-test-layers/compare_runs.py), which compares two
saved `-v` logs as the set of (module name without its prefix, test, outcome) and checks the layer
order of the second: before and after, **359 passed, none skipped, identical**, every layer's node
IDs ahead of the next. `TEST_MODULE=tests/ddd_mutating` ran 166 and
`TEST_MODULE=tests/ccc_reading/list_rigs_test.py` 11. No test was added or removed; the 428 unit
tests changed only in docstrings. Direct tests for the thirteen shared modules are queued in
[NEXT_STEPS.md](NEXT_STEPS.md#direct-tests-of-the-bridges-shared-modules).
