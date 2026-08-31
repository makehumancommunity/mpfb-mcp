# Live verification of the twelve character-modifying tools, and a review of the tool surface

**Status:** Accepted

[FR 001](../done/001-mpfb-get-status/README.md) through [FR 006](../done/006-list-targets/README.md) were
each checked against a running Blender before being marked Done.
[FR 007](../done/007-macro-details/README.md) through [FR 011](../done/011-skin-and-materials/README.md)
were not — five consecutive requests, twelve tools, every one of which *changes* a character. The
suite passes (681 tests) and proves the branching around each call; none of it touches MPFB. On top
of that, two verifications that *were* run are now stale: FR 009 migrated
`payloads/list_rigs.py` onto `codegen/shared/rig_lookup.py` and FR 010 migrated
`payloads/list_assets.py` onto `codegen/shared/asset_sections.py`, so in both cases the program sent
into Blender is a different program than the one FR 004 and FR 005 verified.

The postponement was deliberate each time, and each time for the same reason: the check is one large
manual session, and nothing from the previous one survives to make the next one cheaper. FR 006's
run built a scratch basemesh, loaded four targets, snapshotted twelve datablock collections and
compared them afterwards — all by hand, all thrown away. Nothing of it can be re-run today. That is
the actual defect, and it is why the debt compounded rather than being paid down: a five-request
backlog is not five times as easy to face as a one-request one.

So this request has two halves. Run the checks and fix what they find — every outstanding claim in
[NEXT_STEPS.md](../NEXT_STEPS.md)'s seven-part list, in one session, on one shared character. And
remove the reasons the run is expensive, so that the next tool does not land unverified for the same
reason these twelve did. Alongside that, and because a first live run is the only moment where the
whole surface is being exercised at once, take the measurements that four already-made decisions
rest on and review the structure they produced.

**[FR 012](../done/012-observability/README.md) has landed**, and this request's prerequisite is
therefore met: the other reason the run was expensive is that a live failure surfaced as a traceback
naming a line in a program nobody kept, and the cost measurements below need a recorded duration per
call rather than a stopwatch. Both were originally scoped here; they are a change to the package
rather than an instrument for one session, they are worth having whether or not this session
happens, and folding them in made this request two efforts wearing one number.

Concretely, what this session now has. Run the server with `MPFB_MCP_RECORD_DIR` set — see
[CLAUDE.md](../../CLAUDE.md#commands) — and every call leaves the exact program in a `.py`, the full
envelope in a `.json`, and one line in `index.tsv` carrying the tool, the program size in bytes and
the round-trip duration in milliseconds. Those two columns are the input to
[FR-8](#fr-8-measure-what-four-decisions-rest-on), and the `.py` is what a traceback's line number
is resolved against. `MPFB_MCP_LOG_LEVEL=DEBUG` puts a line per call on stderr while watching. Note
also that **FR 012 inherited one live check into this session, and it should be the first thing
done**: that a line number from a real add-on failure really does resolve to the right line of the
dumped program. Everything else here is easier to diagnose once that is confirmed, and worth
distrusting until it is.

## Goals

**Primary: find and fix outright bugs.** The twelve character-modifying tools have never run against
real MPFB. Everything the unit tests establish is *around* the MPFB call — nothing establishes that
the call does what its docstring says, and every non-functional requirement those five requests
opened with ("indistinguishable from what MPFB's own panel produces") is precisely the claim nothing
on this side of the socket can make. Bugs found in mpfb-mcp are fixed in this effort.

**Secondary: evaluate the tool surface and say what should change.** Twenty tools, ~10,600 lines,
~58 KB of tool descriptions and a mean assembled program of ~23 KB now exist, all written without
one measurement of what any of it costs. Produce a written review, grounded in numbers taken during
the run rather than in argument, with each recommendation classified as fix-here, new-request, or
rejected-with-a-reason.

**Enabling, and not a goal in itself: make the next verification cheap.** A re-runnable harness,
standing on [FR 012](../done/012-observability/README.md)'s per-call record for the diagnostics. It
exists to serve the two goals above and should not grow past that.

**Explicitly not a goal:** new tools, new capability, or the structural refactors the review
recommends. Those are separate requests (see [What this effort may change](#what-this-effort-may-change)).

## Functional requirements

### FR-1: A harness that can be run again

A `verification/` directory at repo root — a sibling of `tests/`, not part of the installed package
and not discovered by `python3 -m unittest discover -s tests` — holding:

- a **snapshot/compare helper** capturing the twelve datablock collections FR 006's run named
  (objects, meshes, materials, images, node groups, armatures, actions, shape keys, collections,
  textures, brushes, worlds) plus `bpy.data.is_dirty`, and diffing two snapshots into a report;
- a **fixture builder** producing the characters of [FR-2](#fr-2-two-characters-one-session);
- **one runnable script per checklist**, each printing one pass/fail/skipped line per checklist item
  with the observed value beside it.

The requirement that makes this worth building: after a code fix, re-running a whole checklist is
one command. Drive everything through the real tool callables
(`mcp._tool_manager._tools[...].fn`, the way the unit tests reach them), not through hand-written
`send_code()` calls — FR 006's precedent, and the only way what is verified is the tool an MCP
client would actually call.

### FR-2: Two characters, one session

The seven checklists want the same dressed, rigged character; building it once is most of the saving.
Build two:

- **Character A**, in MPFB's documented order — create, macro details, detail targets, rig, clothes,
  Rigify generation, skin. This is the character FR 007, FR 008, FR 010 and FR 011 check against.
- **Character B**, in the wrong order — clothes first, then the rig — for one purpose only: to
  observe that the garments are not rigged. That claim is what
  [A tool reports an ordering constraint it cannot enforce](../../specifications/architecture.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
  is built on, and it is currently a reading of MPFB's source.

State the install the run needs, and check it before starting rather than discovering it halfway:
at least one custom rig, Rigify enabled, a skin MHMAT, one asset with alternative materials beside
it, and one asset whose MHCLO declares no delete vertices. FR 008 additionally needs three targets
that do not ship with MPFB — a `.target.gz` under the user `custom` directory, a target with a name
over 60 characters, and one whose name contains `"basis"` — which the harness installs and removes
again, as FR 006's run did with its gzipped probe.

### FR-3: Run the seven checklists, in an order where each pays for the next

The checklists themselves are not restated here; they live in their own requests and are the
authority. What this request fixes is the **order**, because several settle each other:

0. **[FR 012](../done/012-observability/README.md)'s inherited check**, before anything else and on
   whatever call is convenient: force a failure in Blender and confirm the traceback's line number
   resolves to the right line of the dumped program. It is one deliberate failure, and everything
   below is harder to diagnose until it is confirmed.
1. **[FR 004](../done/004-list-rigs/README.md)** and **[FR 005](../done/005-list-assets/README.md)**
   re-checks. Read-only, cheap, and first because FR 009's weights answers and FR 010's
   `resolved_path` are compared against their output.
2. **[FR 007](../done/007-macro-details/README.md#verification-status)** and
   **[FR 008](../done/008-detail-targets/README.md#verification-status)** on Character A before it is
   dressed — phenotype sliders, the modifier round trip through MPFB's own panel, and FR 008's check
   that a macro change leaves the detail stack intact.
3. **[FR 010](../done/010-mesh-assets/README.md#verification-status)**, dressing Character A. The
   largest of the seven, and the one that pays for two others: it settles FR 009's ordering claim
   from the equipping end, and a refit on a dressed character is the first live evidence that
   FR 007's `mpfb_refit_human` does anything at all.
4. **[FR 009](../done/009-add-rig/README.md#verification-status)** across both characters, including the
   full Rigify sequence in both orders and `meta_rig_action: "delete"` foreclosing the refit.
5. **[FR 011](../done/011-skin-and-materials/README.md#verification-status)** last, on the finished
   character — all five `skin_type` values against MPFB's own skin library panel, both directions of
   `mpfb_set_asset_material`, and the alternative-material cache staleness.

Destructive-by-design checks — a rejected `skin_type`, `meta_rig_action: "delete"`, removing an
asset whose `asset_source` was blanked — go last within their checklist, or into a separate Blender
session. Cache-dependent checks (the alternative-material cache, MPFB's asset list, and
`_modelsubpanels`' import-time snapshot) are re-run against a **restarted** Blender rather than by
trying to invalidate a cache MPFB gives no way to invalidate.

### FR-4: Rewrite each source request's verification record, honestly

Each of the seven gets its `## Verification status` section rewritten in place, in
`feature-requests/done/`, following [FR 006](../done/006-list-targets/README.md#verification-status)'s
shape, which is the model: the date and the install it ran against; a `[x]`/`[ ]` checklist with the
**observed value** beside each item; a "What changed against this request" section wherever the run
contradicted what was written; and an explicit statement of the revert result.

An item that was not reached stays `[ ]` with a sentence saying why. The failure mode this whole
request exists to correct is a `Done` that outran its evidence; producing a second one would be
worse than producing none.

### FR-5: Classify every finding, and fix only one class here

Four buckets, decided as each finding appears rather than afterwards:

- **an mpfb-mcp defect** — fixed in this effort, with a unit test that fails before the fix. Where
  the stubs cannot express the failure (a node tree, a fitted vertex, a real cache), say so in the
  commit and in the record rather than writing a test that passes for the wrong reason;
- **an MPFB defect** — recorded and filed against `../mpfb2`, not fixed here;
- **the request or the specification was wrong** — corrected in
  [specifications/](../../specifications/), as FR 006's run corrected `source` into a three-valued
  field;
- **a design gap needing more than a fix** — a new numbered request, not absorbed into this one.

A fix changes the program, so checks already run against the old one no longer say anything. Record
which checks were re-run after which fix; a checklist that was green before a mid-session fix and
never re-run is an unreached item, not a passed one.

### FR-6: Confirm the seven candidate MPFB issues before filing them

FR 008 through FR 011 each ended by naming things that look like MPFB bugs, all of them read from
source and none observed. Confirm each against the running install, then file the ones that hold:

- a gzipped custom target is addressed as `vwide.gz` by `_modelsubpanels` and as `vwide` by
  `TargetService.filename_to_shapekey_name()` — two shape keys for one file ([FR 008](../done/008-detail-targets/README.md));
- `RigService.identify_rig()` can return `None`, on which
  `MPFB_OT_GenerateRigifyRigOperator.poll()` raises rather than returning `False` ([FR 009](../done/009-add-rig/README.md));
- three disagreeing proxy code paths, and `unload_mhclo_asset()` deleting whatever object it is
  handed without checking it is a mesh asset ([FR 010](../done/010-mesh-assets/README.md));
- `set_character_skin()`'s five-`if` dispatch, which turns a typo into destroyed materials;
  `alternative_materials_for_asset()`'s never-read `exclude_default`; that function's
  uninvalidatable module-level cache ([FR 011](../done/011-skin-and-materials/README.md)).

The proxy divergence is the one that is not merely a tidiness point: the Architecture section of
FR 010 justifies which code path `mpfb_add_asset` follows on those three paths differing, so if they
do not differ, a documented decision loses its reason.

### FR-7: Produce the architectural review

A `review.md` beside this README, written after the run so it can cite it. It answers, with numbers
where a number exists:

- **Does the response shape work in practice?** Twelve mutating tools now report a prior state, a
  new state and a list of consequences. Having read twelve real responses off a real character,
  say which fields were used, which were never looked at, and which were ambiguous — in particular
  whether `null` and `[]` stayed distinguishable everywhere, as
  [FR 006](../done/006-list-targets/README.md) insisted they should.
- **Is the duplication a risk or an economy?** It is countable today: subject resolution appears in
  10 payloads, active-object/selection restore in 8, the `bpy.context.mode` precondition in 6, and
  three shared fragments exist for the cases judged worth sharing. The question the review must
  answer is not whether the code repeats — it does — but whether any two copies have **drifted**,
  because drift is what turns duplication into a bug. Diff them.
- **Does the tool surface fit its consumer?** ~58.5 KB of tool descriptions, roughly 14,600 tokens,
  is what an MCP client loads before any work happens; the four largest are `mpfb_list_assets`
  (5.5 KB), `mpfb_list_targets` (4.7 KB), `mpfb_add_asset` (4.6 KB) and `mpfb_get_object_info`
  (4.2 KB). Say which of that is needed *at call time* and which is rationale that belongs in
  [specifications/](../../specifications/) or behind a future `mpfb_search_docs`.
- **Is the tool granularity right?** Building Character A takes one round trip per step. Now that
  the number of steps and the cost of each are known, say whether any pair of tools is always called
  together, and whether a composite belongs in the catalog — noting that
  [FR 008](../done/008-detail-targets/README.md) already took the batching argument once, for one tool,
  and gave a cost-based reason.
- **Do the three payload-count-driven decisions still hold?** The refit-by-default in
  `mpfb_set_macro_details`, the batching in `mpfb_set_targets`, and one-asset-per-call in
  `mpfb_add_asset` were each argued against FR 005's ~1.0 s round trip. Two of the three are now
  measurable ([FR-8](#fr-8-measure-what-four-decisions-rest-on)).

Every recommendation carries a classification: fixed here, scoped as request NNN, or rejected with
the reason.

### FR-8: Measure what four decisions rest on

Taken from [FR 012](../done/012-observability/README.md)'s per-call record — the `ms` and `bytes`
columns of `index.tsv`, under `MPFB_MCP_RECORD_DIR` — three runs each, median reported, first call
to a tool reported separately since it pays for MPFB's caches:

- the **round-trip baseline** itself, re-measured — FR 005's ~1.0 s is the number four decisions
  cite, and it was measured once, on one tool, a year of development ago;
- **where a call's time goes**: transport, `exec`/compile of the generated program, and MPFB's own
  work. FR 012 records the round trip undivided, and deliberately does not instrument the generated
  program to split it — so take the split during this session the way that request points at, by
  having a payload print its own timings into the envelope's `stdout`. Programs run from 4 KB
  (`create_human.py`) to 52 KB (`set_targets.py`), mean ~23 KB, most of
  it comments and docstrings that
  [Readability and developer experience are prioritized](../../specifications/architecture.md#readability-and-developer-experience-are-prioritized)
  deliberately keeps. If compile time is negligible the tradeoff stops being an open question; if it
  is not, that is a finding;
- **the batching claim**: thirty modifier changes in one `mpfb_set_targets` call against thirty
  calls, and how much of the difference is target files coming off disk rather than round trips;
- **per-skin-type cost** for all five values, since MPFB documents `LAYERED` as heavy enough to be
  unsuitable for animation, and **the cost of adding one asset**, which is what one-asset-per-call
  rests on.

## Non-functional requirements

**Truthfulness of the record, above completeness of it.** This request exists because five `Done`
statuses outran their evidence. A half-finished checklist honestly marked is a success; a
fully-ticked one where two items were inferred is the failure being corrected. Where a check cannot
be run at all on the available install, say that, and say what install would run it.

**Revert discipline, stricter than FR 004–006's, because this is mutation.** Work in a scratch
`.blend`, snapshot before, compare after, restore the active object, never save. Name up front what
*cannot* be reverted, so it is a decision rather than a surprise: MPFB's asset-list cache and loaded
previews (FR 005 already hit this), the alternative-material cache, and
`enhanced_settings.default.json`, which `mpfb_set_skin` writes into the **user config directory** —
outside the `.blend` entirely — whenever `material_instances` is on.

**Repeatability.** A second run of the harness against a freshly started Blender must produce the
same lines. A check that passes intermittently is not evidence, and determinism matters more here
than breadth: an item that cannot be made deterministic should be marked as a manual observation
rather than automated into a flaky one.

**Efficiency of the session, not only of the code.** The characters are built once and reused; the
read-only checks run first because later ones compare against their output; a Blender restart is
budgeted where a cache demands one rather than avoided.

**No new abstractions in the package as a side effect of testing it.** The harness lives outside
`src/`, and the only addition inside it — FR 012's record — is one gated change at the single point
everything already funnels through. If verifying a tool requires changing that tool's structure,
that is a finding for the review, not a change to make quietly during the run.

## Architecture

### Where the harness goes

**`verification/`**, a sibling of `tests/`. It must not be picked up by
`unittest discover -s tests`, and it must not be shipped:
[pyproject.toml](../../pyproject.toml) already sets `namespaces = false` and declares package data by
explicit glob, so a top-level directory outside `src/` is not shipped — but check, because that
file has been edited twice for exactly this class of accident (payloads shipped as modules, then
payloads not shipped at all).

### Pitfalls the run will hit

- **`strict_json`.** Anything a payload leaves in `result` has to be JSON-encodable, and FR 005
  already found a value that is not (`get_asset_list()`'s `thumb`). Such a failure surfaces as an
  envelope error rather than a payload error, and [FR 012](../done/012-observability/README.md)'s record
  is what distinguishes the two.
  Expect at least one, in the tools whose responses no live call has ever serialized.
- **`bpy.context.mode`, not just the object's.** Both [FR 009](../done/009-add-rig/README.md) and
  [FR 010](../done/010-mesh-assets/README.md) learned this from source: an unrelated object left in
  edit mode fails an operator on a subject that looks perfectly fine. The harness should assert a
  clean context *before* each checklist item, or a good fraction of the failures will be the
  harness's own.
- **The payload brace rule.** A payload file may contain no empty brace pair anywhere — that is what
  a substitution point looks like — which is why payloads build messages by concatenation rather
  than with `.format()`. [tests/test_codegen.py](../../tests/test_codegen.py) enforces it, so any fix
  written into a payload during the run has to respect it; the suite will catch it, but knowing why
  saves the detour.
- **A fix invalidates what came before it.** FR 009 and FR 010 both demonstrated the sharper version:
  a refactor whose unit tests see *no* behavior change still makes a live verification stale,
  because a different program is sent. The same applies within this session.
- **Two checks cannot be automated and should not pretend to be.** "The same shape keys at the same
  weights as MPFB's own slider produces" and "indistinguishable from a garment equipped through the
  asset library panel" are comparisons against a UI. Do them as UI-then-tool-then-diff on a
  snapshot, and record them as manual observations with the snapshot kept.

### What this effort may change

**Fixed here:** defects in mpfb-mcp; corrections to
[specifications/](../../specifications/) and to the seven verification records; the harness.
Observability is *not* fixed here: it is [FR 012](../done/012-observability/README.md), and if the run
finds it insufficient the correction belongs to that request rather than to this one.

**Deferred to their own requests**, with the requests *written before this one closes* so the
moment is not lost: a fourth and fifth shared fragment if the census argues for one; the
`mpfb_list_targets` migration onto `target_categories.py`, which
[NEXT_STEPS.md](../NEXT_STEPS.md#modeling) says should be done *with* a live re-verification and which
is therefore cheapest while the harness is warm; and any trimming of the tool descriptions. These
are deferred rather than dropped because folding a refactor into a bug hunt makes every finding
ambiguous about which change caused it.

**One exception.** If the duplication census finds that two payloads have actually **drifted** —
that two copies of the subject resolution, the selection restore or a mode precondition no longer
agree — the fragment that removes the drift is a bug fix and lands here, with the divergent
behavior recorded as the reason. That is the same test `rig_lookup.py` passed and
`list_targets.py` did not.

## Affected specifications

- **[specifications/architecture.md](../../specifications/architecture.md)** — the paragraph under
  [No direct dependency on MPFB or blender_mcp](../../specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp)
  currently says live verification is "a manual/integration verification step"; with a harness it
  becomes a named, re-runnable one. Expect edits wherever the run contradicts a standing convention
  — the likely candidates are
  [Preconditions are answers](../../specifications/architecture.md#preconditions-are-answers),
  [A mutating tool reports before and after](../../specifications/architecture.md#a-mutating-tool-reports-before-and-after)
  and [Response shape](../../specifications/architecture.md#response-shape), all three of which were
  written from source rather than from observation.
- **[specifications/vision.md](../../specifications/vision.md)** — the catalog entries for the twelve
  character-modifying tools carry claims phrased as fact ("the result matches what MPFB's three
  'Add ... rig' buttons produce"). Each is a reading of source. Every one that the run confirms
  should say so; every one it contradicts is a correction.
- **[feature-requests/CLAUDE.md](../CLAUDE.md)** — the [Lifecycle](../CLAUDE.md#lifecycle) says nothing
  about live verification, which is how five requests reached `Done` without it. This effort is the
  one with standing to propose what `Done` should require: at minimum that a request whose live
  check is outstanding says so in its status line rather than only in a section further down.
- The `## Verification status` sections of [FR 004](../done/004-list-rigs/README.md),
  [FR 005](../done/005-list-assets/README.md), [FR 007](../done/007-macro-details/README.md),
  [FR 008](../done/008-detail-targets/README.md), [FR 009](../done/009-add-rig/README.md),
  [FR 010](../done/010-mesh-assets/README.md) and [FR 011](../done/011-skin-and-materials/README.md) —
  records rather than specifications, but rewritten by this effort and listed here so the scope is
  visible.

## Tests

The usual sentence is inverted for this request: **the live verification is not a footnote at the end,
it is the work.** Nothing here is complete on a green unit run.

- The existing suite (681 tests, `python3 -m unittest discover -s tests`) is the regression net for
  every fix. A fix lands with a test that fails before it, wherever the stubs can express the
  failure — and with an explicit note where they cannot, which will be common: no stub builds a node
  tree, imports a mesh, fits a vertex or reproduces a real MPFB cache.
- Where a live finding *can* be pushed down into the stubs, it should be, following the standing
  discipline that a stub reproduces MPFB's behavior including the inconvenient parts. A quirk
  observed live and left only in prose is a quirk the next refactor will break.
- The harness under `verification/` is **not** unit-tested and must not be discovered by the test
  runner. It is an instrument, and its own correctness is established by the fact that its checks
  fail when pointed at a deliberately broken call — worth doing once per checklist, since a harness
  that cannot fail proves nothing.
- Live verification of *this* request means: every checklist in FR-3 run, every result recorded per
  FR-4, and the harness re-run once from scratch to prove FR-1's repeatability requirement.

## References

- [NEXT_STEPS.md](../NEXT_STEPS.md#modeling) — the seven-part description of this session, which this
  request scopes.
- [FR 012](../done/012-observability/README.md) — the prerequisite: the per-call record this session's
  diagnostics and cost measurements both read from.
- [FR 006](../done/006-list-targets/README.md#verification-status) — the model for a good verification
  record: what was run, what it changed about the request, and what could not be reverted.
- [CLAUDE.md](../../CLAUDE.md#commands) — how to bring up Blender with MPFB and the blender_mcp add-on,
  and the `BLENDER_MCP_HOST`/`BLENDER_MCP_PORT` overrides.
- [../mpfb2](../../../mpfb2) — where the confirmed MPFB defects from FR-6 get filed.
