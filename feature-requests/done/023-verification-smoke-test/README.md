# The live verification becomes a smoke test

**Status:** Done

[FR 013](../013-live-verification/README.md) built `verification/` to clear a backlog: five
requests had reached `Done` with no live check because a live check was a session nobody wanted to
repeat. It worked — the backlog cleared, defects in both mpfb-mcp and MPFB fell out of it, and
re-running a checklist after a fix became one command. But what it built was *the backlog*,
written down: one script per feature request, each exhaustively re-proving that request's claims,
and every one of them kept and re-run forever afterwards.

That is now the wrong shape, in two measurable ways. The directory is **5,308 lines across
fourteen Python files** — larger than any single spec, and growing by one `check_fr0NN.py` per
effort with nothing ever leaving. And a full run crosses the socket **more than two hundred
times**: 209 call sites across the eight checklists and their fixtures before any loop, including
fifty character builds, six Rigify generations and a twelve-collection snapshot taken twice per
checklist. It also writes three probe targets into MPFB's user config and removes them again,
moves a settings file aside and restores it, and writes a `.mhmat` beside an asset. Minutes, not
seconds, and fragile in proportion.

The intent was never that. Tests run without the live connection; `tests/` is what a change is
expected to keep green, and it does that in nine seconds. The live run should answer one much
smaller question — **does each tool, called the way an MCP client would call it with default
settings, still work against a real MPFB at all?** — and answer it fast enough that there is no
reason to skip it. Exhaustively proving one feature against a live Blender is worth doing *once*,
during that feature's own life cycle, by the effort that is making the claim. It is not worth
re-proving on every code change, and keeping the proof around forever is what turned a good idea
into an unbounded directory.

## Goals

**Primary: `verification/` becomes a smoke test that runs in under a minute.** One item per tool,
default arguments, checking that the call comes back a non-error envelope and reports having done
what it says. **Under 60 seconds of wall clock for all twenty tools, against a correctly
configured Blender, is the outcome this effort is aiming at** — the number that says the pivot
worked. It is a design target, not a gate: the run reports its own timing so the number stays
visible, and does not fail on it.

**Primary: the directory stops growing.** A new tool adds exactly one line to a table and no new
file. The set of files in `verification/` is fixed at four, and the set of run-level items that
are not per-tool checks is fixed at three.

**Secondary: most of what is there now is deleted.** Roughly 4,600 of the 5,308 lines go. This is
the point of the effort, not a side effect of it: the eight per-request checklists have already
delivered their findings into `specifications/` and
[HISTORY.md](../../HISTORY.md), and keeping the scripts that produced them is keeping a receipt for a
conclusion that is already written down. Git holds them if a question ever needs re-asking.

**Secondary: the rule about where a live check belongs is written down**, so the directory cannot
regrow by the same mechanism. An exhaustive live check belongs to the feature request that needs
it, lives in that request's own subdir, and goes to `done/` with it.

## Functional requirements

- **FR-1. One smoke item per tool, derived from the registry.** The item list is built by asking
  the built server which tools are registered — the same `tools()` path the harness already uses —
  and each registered tool must have exactly one smoke entry. A tool with no entry is a **failure
  of the smoke run**, not a silent omission, so adding a tool without a smoke item cannot pass.
  An entry that names a tool the server does not register is likewise a failure.

- **FR-2. Each item calls its tool the way an MCP client would**, through the tool callable, with
  the tool's own defaults wherever the tool has one. Where an argument is required
  (`mpfb_symmetrize_targets`' `direction`, `mpfb_add_asset`'s `asset_type`, `mpfb_set_skin`'s
  subject) the item supplies the least interesting legal value and nothing more. **The smoke run
  does not explore a tool's parameter space.** One call, defaults, does it come back.

- **FR-3. What an item asserts is deliberately shallow**, and it is exactly three things:
  1. the envelope is not an error;
  2. the response carries the keys the tool's own contract names as always present — read from the
     response, not from a copy of the contract kept here;
  3. for a mutating tool, `performed` is `true` and agrees with that tool's verb, which is the
     existing `MUTATING_VERBS` audit and the one check the unit suite genuinely cannot make.

  It asserts nothing about *values*. Whether a garment equipped through the tool is
  indistinguishable from one equipped through MPFB's panel is FR 010's claim, established once by
  FR 010, and not re-established here.

- **FR-4. Three run-level items, and no fourth.** Beside the per-tool items the run performs, and
  the set is closed:
  1. **the install gate** — MPFB present and initialized, checked before anything else, so a
     missing install is one clear line rather than twenty tracebacks;
  2. **the leak compare** — one snapshot of the twelve datablock collections plus `is_dirty`
     before the run and one after cleanup, so "the harness put back what it made" stays an
     assertion. Once per run, not once per checklist;
  3. **the traceback item** — one deliberately failing call, asserting that the line number in the
     traceback resolves against the recorded program. This is FR 012's inherited check and the
     only part of the record that a test on this side of the socket cannot make. It skips when
     `MPFB_MCP_RECORD_DIR` is unset; the run does not require the variable.

- **FR-5. The run reports its own timing, and aims at 60 seconds.** The run times each item and
  the whole, and prints the total and the three slowest items as part of its summary. **Sixty
  seconds is the target the design is built to hit, not a limit the run enforces**: exceeding it
  does not fail the run and does not change its exit code, which is decided by the checks alone.
  An over-target total is a prompt to look, and the summary should say so in those terms, naming
  blender_mcp's `timer_interval_active` first, since a Blender left at the 0.25 s default is by
  far the likeliest cause and is a configuration mistake rather than a regression (see
  [CLAUDE.md](../../../CLAUDE.md#commands)). Wall clock against a live Blender is too noisy and too
  install-dependent to gate on, and a check that fails for a reason outside the repository is one
  people learn to ignore — which would cost more than the minute it was protecting.

- **FR-6. The run works on any adequate install, and names what it could not exercise.** It must
  not require a specific garment, rig or skin by filename: it asks the catalogue tools what this
  install has and uses the first workable answer. Where the install genuinely lacks a
  prerequisite — Rigify disabled, no custom rig, no skins, no MHCLO assets — the affected items
  report **`skipped` with the reason**, the run still passes, and the summary names every tool
  that was not exercised. A skip must never read as a pass.

- **FR-7. Deletions.** The following go, and the request is not complete while any of them
  remains:
  - `check_fr004.py`, `check_fr005.py`, `check_fr007.py`, `check_fr008.py`, `check_fr009.py`,
    `check_fr010.py`, `check_fr011.py`, `check_fr012.py` — 3,122 lines. Their findings are in
    `specifications/`, in [HISTORY.md](../../HISTORY.md) and in each request's own README under `done/`.
    FR 012's one live claim survives as FR-4's traceback item.
  - `measure.py` — 368 lines. It takes minutes, nothing depends on it, and the cost model it
    produced is written down in
    [architecture.md](../../../specifications/architecture.md#what-a-call-costs-is-the-size-of-its-program).
    It is FR-time instrumentation for an effort that is over.
  - `census.py` — 244 lines. Its recurring value — *have the fragments and their payloads
    drifted?* — is already asserted per fragment in `tests/test_codegen.py`, on every run, with no
    Blender. Its remaining value is exploratory: finding the *next* migration candidate, which is
    an FR-time activity by the same logic as the checklists.
  - `run_all.py` — replaced by the smoke script itself.
  - `results/` is gitignored and needs no action beyond the new script writing its own.

- **FR-8. `check_mpfb_issues.py` is moved, not deleted — and the move now leaves this
  repository.** It is not a check of mpfb-mcp's tools at all: it provokes defects in *MPFB*. It
  moves into `feature-requests/done/019-file-mpfb-defects/`, which is where FR 019 landed, and
  every citation of the old path is re-pointed.

  **FR 019 changed what that costs.** The filed report,
  [`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../../../mpfb2/features/MCP_DISCOVERED_BUGS.md),
  cites `verification/check_mpfb_issues.py` **by path, from another repository**, once per defect,
  and names a function inside it per section; it also links `verification/check_fr010.py`, which
  FR-7 deletes, for the proxy comparison. So this request must either keep those two paths valid
  or update that document as part of landing — and a path in somebody else's repository is not
  something a link check here would catch. Deleting `check_fr010.py` without rewriting the
  report's "Reproduction" line for the proxy item leaves a filed defect report pointing at
  nothing, which is exactly the failure FR 019's "reproductions, not descriptions" requirement
  exists to prevent.

  This is the first application of FR-10's rule.

- **FR-9. Four files, and the count is the ceiling.** `harness.py` (the tool callables, the
  scratch scene, the snapshot/compare, the probe, the `performed` audit and the report),
  `fixtures.py` (the install gate and the one character), `smoke.py` (the item table and the run),
  `README.md`. Adding a fifth file to `verification/` means the pivot has been undone and should
  be argued as its own request.

- **FR-10. The rule is written down where a future effort will read it.**
  [feature-requests/CLAUDE.md](../../CLAUDE.md)'s "Tests" section currently instructs an effort to put
  its live check in `verification/` as a script. That is what produced eight checklists, and it
  becomes: an exhaustive live check belongs in **the feature request's own subdir**, is run during
  that effort, and moves to `done/` with it; what the effort adds to `verification/` is at most
  the one smoke item for a tool it introduced.

## Non-functional requirements

- **Speed is the feature.** It is what every other choice here is traded against, and the reason
  the assertions are shallow and the character is built once. A verification that takes minutes is
  one that gets skipped, which is precisely the failure FR 013 was written to fix — it is being
  repeated at a different scale, not avoided. Note that this is a claim about how the run is
  *designed*, not about a number it polices: see FR-5 for why the target is reported rather than
  enforced.

- **Bounded growth, and only one part of it is mechanical.** FR-1's registry-derived coverage is
  the hard bound: a tool without exactly one smoke item fails the run, so the item table cannot
  fall behind and cannot hold entries for tools that no longer exist. The *time* is bounded by
  design instead — one character, one call per tool, three assertions — and kept honest by being
  printed on every run rather than by a threshold. This is a weaker mechanism than
  [test_description_budget.py](../../../tests/test_description_budget.py)'s ceiling, and deliberately
  so: that one measures bytes computed on this side of the socket, which are the same on every
  machine, where this one would be measuring somebody else's Blender.

- **Diagnosability is not sacrificed to speed.** The run keeps the per-item report with the
  observed value beside each outcome, and keeps working with `MPFB_MCP_RECORD_DIR` so a failure
  still leaves the exact program and envelope behind. What is dropped is breadth, not detail.

- **Portability.** FR-6's "no filename is required" is what lets this run on a developer's Blender
  rather than on the one Blender FR 013 was written against. Hard-coded asset names were a
  reasonable cost for a one-off session and are not one for a check meant to run often.

- **Honest reporting.** A skipped tool is reported as skipped, by name, in the summary. Twenty
  passes and four skips must not be presentable as twenty-four passes.

## Architecture

**The whole run is one character.** Build it once, in the `MPFBMCP_VERIFY` scene, and let every
subsequent item act on it. The current run's cost is dominated by repetition: each checklist built
its own character because each had to be independently runnable, and independence was worth paying
for when a checklist was a re-run-after-a-fix unit. With one script there is nothing to be
independent of.

**The ordering constraint is real and the item table has to respect it.** `mpfb_add_rig` before
`mpfb_add_asset`, and `mpfb_generate_rigify_rig` after — the same ordering the tools report and do
not enforce ([README.md](../../../README.md)). `mpfb_generate_rigify_rig` also needs the rig added to
have been a Rigify meta rig, and it is the one tool that cannot restore the caller's selection. A
second character is permitted **only** if a precondition genuinely cannot be satisfied on the
first, and if one is built the README says what it cost in seconds.

**Measure first, then write.** The implementation's first task is to measure the twenty default
calls and see what the sum actually is, because the target is only reachable by knowing where the
time goes. If the sum does not fit, cut in this order: (1) drop any second character; (2) cap the
catalogue calls with `limit` and leave `refresh` at its default `false`, so no tool rescans the
disk; (3) make the dominating tool's smoke call cheaper. **Excluding a tool is not on that list.**
If one tool turns out to dominate and cannot be made cheaper, it stays in the run and the run
takes longer than a minute; the README then records what it costs, so the overrun is a documented
fact about MPFB rather than a gap in the coverage. Twenty tools checked in ninety seconds is a
better outcome than nineteen checked in fifty.

**Three fixtures go away with the checklists that needed them**, and each removal is also a
correctness gain:
- the **probe targets** written into MPFB's user `custom` directory. One of the three prevents
  MPFB from loading if it is still on disk when Blender starts — which is how that MPFB defect was
  found, and which makes this the single riskiest thing the harness does to a developer's install.
  It belongs with FR 019, alongside `check_mpfb_issues.py`.
- **`enhanced_settings.default.json` moved aside and restored** — FR 011's specific question about
  creation, asked and answered.
- **the `.mhmat` written beside an asset** — the cache-staleness observation, which is
  [FR 018](../018-alternative-material-refresh/README.md)'s subject and should move there if that
  effort still wants it.

After this, `verification/` changes nothing outside the `.blend` at all, which is a materially
better thing to hand somebody than the current list of three deliberate exceptions.

**What `harness.py` keeps** is most of what it is: `tools()`, `probe()`, the scratch scene,
`snapshot`/`diff_snapshots`, `MUTATING_VERBS` and the `performed` wrapper, and `Report`. What it
sheds is whatever only a deleted checklist called. `fixtures.py` shrinks hardest — from 519 lines
to an install gate and one `ensure_character` — because FR-6 replaces its table of named assets
with a question put to the catalogue tools.

**Target size: under 700 lines across four files**, from 5,308 across fourteen. If the result is
much above that, something exhaustive has survived that should not have.

**Pitfall: do not let the smoke items grow assertions.** Every one of the eight checklists began
as a handful of items. The pressure to add "and while we are here, check that…" is what this
request exists to resist, and FR-3's three-things list is the thing to point at when it comes up.

## Affected specifications

- **[specifications/testing.md](../../../specifications/testing.md)** — the substantive fold-back, and
  it is a change of meaning rather than an addition:
  - *"The live harness is named and re-runnable, not a session"* is rewritten. The harness is still
    named and re-runnable; what it now answers is **"does every tool still work at all?"**, in
    under a minute, once per tool. The two load-bearing properties stay true and stay stated —
    checks go through the tool callables, and a comparison against MPFB's own panel is a diff and
    not a screenshot — but the second one now describes what an *effort* does during its life
    cycle, not what `verification/` holds.
  - The line at the head of the document, *"The live harness answers 'does MPFB do what we read in
    its source?'"*, becomes narrower: the smoke run answers "does the tool run"; "does MPFB behave
    as we read it" is answered once, by the effort making the claim.
  - **"What the suite can never establish"** needs its closing sentence corrected, and this is the
    honest cost of the pivot. It currently reads that every item on that list is `verification/`'s
    job. After this request it is not: the smoke run does not establish that a garment equipped
    through the tool matches the panel's, nor that any skin type builds the right node tree. Those
    were established once, by FR 010 and FR 011, and the spec should say so — naming the effort
    that established each — rather than implying a standing check that no longer exists.
- **[specifications/architecture.md](../../../specifications/architecture.md)** — two dangling pointers.
  The transport cost model cites `verification/measure.py` as where it was measured; that citation
  becomes a citation of FR 013 and this request's own measurements. The shared-fragments section
  says the census "is kept as `verification/census.py` so that the question stays a command"; that
  claim stops being true and should be replaced by what is actually true — the drift question is
  asserted per fragment in `tests/test_codegen.py`, on every unit run.
- **[specifications/mpfb-integration.md](../../../specifications/mpfb-integration.md)** — "Each is
  provoked by a script under `verification/`" is re-pointed at FR 019's subdir, per FR-8.
- **[feature-requests/CLAUDE.md](../../CLAUDE.md)** — not under `specifications/`, but the document that
  will produce the next eight checklists if it is left alone. Its "Tests" section changes per
  FR-10, and its `Done (live verification outstanding)` paragraph should say what "verified" now
  means: the effort's own exhaustive check ran during the effort, and the tool has a smoke item.
- **[README.md](../../../README.md)** and **[CLAUDE.md](../../../CLAUDE.md)** — the map, edited because the
  layout and the commands genuinely changed (one script, one command, a reported time), not
  narrated at length. The root CLAUDE.md's "Project status" paragraph and its `verification/`
  mentions; README's "All twenty have been run against a real Blender", which stays true and gains
  the sharper claim that re-checking all twenty is now one short command. Whatever the run is
  measured at, quote that number rather than the target — a documentation claim about speed should
  be the observation, not the aspiration.
- **[verification/README.md](../../../verification/README.md)** — rewritten, and it is the one document
  where the new purpose is stated in full: what the run is for, what it deliberately does *not*
  check, the four files, the timing the run was last measured at, and where an exhaustive check
  goes instead.

## Tests

**This effort's subject is the live check, so it is verified live, by construction.** The
acceptance evidence is a full smoke run against a real Blender: all twenty tools exercised or
explicitly skipped, zero failures, and the total wall clock printed. Record that number in
`verification/README.md` together with the machine and the `timer_interval_active` it was taken
at — a baseline nobody wrote down is the reason the current run's cost went unnoticed until it was
minutes. If the recorded number is above 60 seconds the effort is not thereby incomplete, but the
request should say why, since that is the finding.

Two things must be verified by making them fail, not by observing them pass — the same discipline
FR 013 used on its own harness:
- **FR-1's coverage check**: register a tool with no smoke item and confirm the run fails.
- **FR-6's skip path**: point the run at an install lacking one prerequisite (or simulate the
  catalogue coming back empty) and confirm the affected tools report `skipped` with a reason, the
  run still passes, and the summary names them.

`tests/` gains nothing from this effort directly, with one candidate worth considering: the item
table's shape — one entry per registered tool, no unknown tool named — is checkable on this side
of the socket, since it needs only the built server. If it can be asserted in `tests/` without
importing anything from `verification/` into `src/`, it should be, because a coverage rule that
only fires when a Blender is running is a coverage rule that fires late. Note that
`unittest discover -s tests` does not reach `verification/`, so such a test imports the item table
by path rather than as a package sibling — and if that turns out to require plumbing, drop it: the
live check in FR-1 is sufficient and this is a convenience.

## References

- [FR 013](../013-live-verification/README.md) — built `verification/`, and its
  non-functional requirements are where the two things the harness cannot put back are recorded.
  Nothing in it was wrong; its shape was right for clearing a backlog and wrong for standing
  service.
- [FR 016](../016-trim-tool-descriptions/README.md) and
  [tests/test_description_budget.py](../../../tests/test_description_budget.py) — the precedent for a
  measured ceiling that fails a run. FR-5 deliberately stops short of copying it, and the
  non-functional requirements say why: that ceiling measures bytes this repository computes, and
  this one would be measuring the machine MPFB happens to be running on.
- [FR 019](../019-file-mpfb-defects/README.md) — **Done**. Its deliverable,
  [`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../../../mpfb2/features/MCP_DISCOVERED_BUGS.md),
  cites `verification/check_mpfb_issues.py` and `verification/check_fr010.py` by path from another
  repository; FR-8 says what this request owes them.
- [FR 018](../018-alternative-material-refresh/README.md) — Proposed; the cache-staleness fixture
  this request removes is its subject, and it should take the fixture if it wants it.
- [FR 020](../020-trim-claude-md/README.md) — the same disease in the documentation: growth by
  accumulation until copies drift. Worth reading before writing the replacement README, since the
  failure mode being cured here is that one wearing different clothes.

## Verification status

**Verified live.** Blender 5.1.0, MPFB 2.0.17 `FROM_SOURCE`, 909 assets across 112 packs,
blender_mcp's `timer_interval_active` at its **0.25 s default** — the slow configuration, which is
the honest one to quote.

```
--- mpfb-mcp smoke run - twenty tools, default arguments: 23 passed, 0 failed, 0 skipped, 42.6s
    slowest: mpfb_set_targets 7.8s, mpfb_add_asset 4.5s, mpfb_set_skin 3.8s
```

All twenty tools exercised, none skipped, the leak compare identical, the traceback item resolved.
**42.6 s against the 60 s target**, and the cut list in the Architecture section was never needed —
the first measurement of the twenty default calls came in at 34 s of tool time, so no second
character was ever built and no catalogue call had to be capped beyond the `limit=1` the
prerequisite lookups already use.

The two things FR 023's Tests section says must be verified **by making them fail** were, by
[`check_negatives.py`](check_negatives.py) — this effort's own check, in this effort's own subdir,
which is the first application of FR-10's rule:

```
--- FR 023 - the two properties verified by making them fail: 6 passed, 0 failed, 0 skipped
```

FR-1's coverage check was provoked in all three directions (a registered tool with no item stops
the run with exit code 2; an item removed from the table is named; an item for a tool that is not
registered is named). FR-6's skip path was provoked by making the asset catalogue answer empty:
five tools reported `skipped` with a reason, the summary named every one of them, and the run
still passed with exit code 0.

`tests/` gained the candidate the request called optional —
[test_verification_smoke.py](../../../tests/test_verification_smoke.py), five tests, importing the
item table by path. The plumbing turned out to be four lines, so the coverage rule now also fires
in the nine-second unit run. 742 tests became 747.

### Three things the implementation found

**The 700-line target was too low, and nothing exhaustive survived to explain the difference.**
The four files come to **1,163 lines** — `smoke.py` 509, `harness.py` 440, `fixtures.py` 87,
`README.md` 127. In Python alone the fourteen files were 5,308 and the three that remain are
1,036, so **4,272 lines of Python went**, close to FR-7's estimate of 4,600 but leaving more
standing than the 700 target allowed for. The estimate assumed `harness.py` would shed more than
it could: FR-4's leak compare needs the snapshot, the cleanup and the scratch scene, which are
~130 lines of embedded Blender source that no trimming touches, and twenty item definitions cost
about seven lines each. Of the 1,036 Python lines, 546 are code and the rest is prose and blank
lines. The pitfall the request warned about — items growing assertions — did not materialise; the
assertions are the three FR-3 names, and nothing else.

**FR-3's "read from the response, not from a copy of the contract kept here" needed a mechanism,
not just a habit.** There is no machine-readable contract to read: what a tool promises is prose
in its docstring. So each item names its contract keys, and `_keys_the_tool_names()` holds that
tuple to **the description the MCP client actually downloads** — every backticked span in it,
reduced to its leading identifier. A key the description stops naming fails the item. The check
found two mistakes on its first live run (`blender`, which the description writes as
`blender.version`, and `found`, which it writes as `found: false`), which is what a drift check
existing is for.

**Two fragments have a drift check, not six.** FR-7 justified deleting `census.py` on the grounds
that its recurring question is "already asserted per fragment in `tests/test_codegen.py`". It is
asserted for `refit_blocker.py` and `modifier_reading.py`, and not for the other four —
`performed.py`'s tests exercise the fragment but do not assert that no payload keeps a copy. The
deletion still stands (the census was exploratory, and its output is quoted in
[architecture.md](../../../specifications/architecture.md#shared-fragments) where it matters), but the
justification was overstated and
[architecture.md](../../../specifications/architecture.md#shared-fragments) now says which two are
covered and that a fragment added later should bring such a check with it.

### What was left alone deliberately

Eight `done/` request READMEs link a `check_frNNN.py` that no longer exists. They are historical
records of what that effort did, the links were valid when written, and several of them already
link a `verification/review.md` that was removed long before this effort. Git holds the scripts.
[verification/README.md](../../../verification/README.md) says so in as many words rather than
leaving the dangling links unexplained.
