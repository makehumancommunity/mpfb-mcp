# Introspection and catalogues migrated

**Status:** Accepted

[FR 030](../done/030-backend-seam/README.md) built the seam and migrated one tool across it,
chosen for being dull. This is [stage 3 of the pivot](../NEXT_STEPS.md#3-introspection-and-catalogues-migrated):
the rest of the read-only half of the package follows it, and the dullness stops.

**Nine tools move here, not eight.** The stage text counted nine and subtracted
`mpfb_list_objects`; the arithmetic that produced "nine" quietly left `mpfb_get_status` in stage 4,
where it was counted among "the fourteen mutating tools" and is not one. It belongs with the
introspection tools it is an introspection tool alongside, and moving it here is also the moment
the collision FR 030 flagged has to be settled: the bridge's own `get_status` command reports the
*bridge*, and `mpfb_get_status` reports *MPFB*. So: eight catalogue and introspection tools plus
`mpfb_get_status`, and stage 4 inherits thirteen mutating tools plus the two documentation ones.

**What stage 2 migrated was 87 lines; this is roughly 3,400.** Nine payloads totalling 2,250 lines
and five shared fragments totalling 1,113 become add-on code, against nine client-side test modules
totalling 3,679 lines that mostly stop being the place the claim is checked. This is the effort
NEXT_STEPS says is most likely to be under-estimated, and the estimate it warns against reading off
`mpfb_list_objects` is the only one anybody has.

**Two things the stage text gets wrong and this request has to fix before it can start.** It names
four straddling fragments and there are five — `preset_files.py` is used by `mpfb_list_presets`
here and by both preset writers in stage 4, and it is the one fragment whose rule is deliberately
duplicated on *this* side of the socket too. And `backend.send()` **cannot carry a shared fragment
at all**: it takes `payload`, `params` and `bootstrap`, and five of the nine tools carry fragments,
three of them through `shared_cache.send()`, which FR 030 explicitly kept off the seam. No
fragment-carrying tool can be migrated until that is fixed, which makes it this effort's first
requirement rather than a detail of its fourth.

## Goals

**Primary.** Migrate nine tools: `mpfb_get_status`, `mpfb_get_object_info`,
`mpfb_get_macro_details`, `mpfb_list_presets`, `mpfb_list_rigs`, `mpfb_list_assets`,
`mpfb_list_asset_materials`, `mpfb_list_targets` and `mpfb_get_target_stack`. After this effort
`MIGRATED_COMMANDS` has ten lines and every read-only tool that crosses the socket has a bridge
command.

**Primary.** Teach the seam to carry shared fragments, and give the bridge somewhere for a shared
concept to live that is visibly not a command. This is the plumbing every remaining stage needs and
nothing has yet.

**Primary.** Keep the pairing guarantee alive across the stage boundary. Five fragments will exist
twice for the duration — a bridge module and a codegen fragment — and "these two agree" has to be
asserted rather than intended.

**Primary.** Settle what a bridge-side test does for data: it builds its own fixture tree. Nine
commands establish the convention that the remaining fourteen copy.

**Secondary.** Measure what the pivot is actually worth. `mpfb_list_targets` carries 26 KB of
fragments and is the tool the session source cache was built for; the like-for-like number for it
is the headline evidence of the whole pivot and nobody has it.

**Explicitly not a goal.** Migrating any mutating tool, `mpfb_list_urls` or `mpfb_list_docs`;
deleting anything on the generated path; changing the default backend; moving the sixteen
unmigrated tools onto `backend.send()` in bulk (see [Out of scope](#out-of-scope-deliberately)).

## Functional requirements

1. **The seam carries fragments, and a tool still does not know which transport it is on.**
   `backend.send()` gains what `codegen.assemble()` and `shared_cache.send()` already take —
   `shared` and `cached_shared` — and routes them: to the generated path they are what they are
   today, and on the bridge path they are **ignored**, because a fragment is a property of how a
   program is assembled and the bridge assembles nothing. A migrated tool therefore passes the
   same call on both paths, exactly as FR 030 required for `params`, and requirement 3 of that
   effort still holds verbatim: a `git diff` on a migrated tool module shows its send call
   replaced and nothing else.

2. **`shared_cache.send()` routes through the seam rather than around it.** FR 030 kept it off
   deliberately and deferred it here. The three tools that use it —
   `mpfb_list_targets`, `mpfb_get_target_stack` and two stage-4 tools — must be migratable without
   losing the session source cache for the tools that stay behind. The arrangement to reach for is
   that a tool calls `backend.send()` and the seam decides, on the generated path only, whether
   this call carries its fragments' source; `shared_cache` keeps its memo, its retry and its
   docstring, and stops being something a tool module imports. **It is still generated-path
   machinery and it still dies with that path** — nothing here should make it look permanent.

3. **A shared concept on the bridge is a module, and visibly not a command.** The five fragments
   that migrate become modules in a new `bridge/mpfb_bridge/shared/`, a sibling of `commands/`
   named to mirror `codegen/shared/` for the reason `commands/` mirrors `tools/`: during the
   migration a fragment and its replacement must be findable from each other. **Nothing in that
   directory is reachable from the wire**, which is the property `commands/table.py` exists to
   make checkable, and the table's own docstring must say so rather than leave a reader to notice
   that a second directory has appeared beside the one it describes.

4. **A fragment and the bridge module replacing it are checked against each other, on every unit
   run, with no Blender.** This is what keeps the pairing guarantee — `mpfb_list_rigs` predicts
   which weights `mpfb_add_rig` will load, `mpfb_list_assets` reports the vocabulary
   `mpfb_add_asset` resolves with — true while one half has migrated and the other has not.
   The check parses both files with `ast` and compares the functions that embody the rule,
   docstrings stripped and normalised through `ast.unparse`, which is the technique
   [architecture.md's payload census](../../specifications/architecture.md#shared-fragments) already
   used and `tests/test_reference_drift.py` already uses against another repository.
   **It must not claim more than it checks.** A fragment reads `_MPFB_SERVICES`, bound by the
   bootstrap, where a bridge module reads `resolution.services`; functions differing by that are
   compared after one declared substitution, and any function the check cannot cover is **named in
   the test** rather than silently skipped. A drift check that passes because it compared nothing
   is worse than none, which is why `test_reference_drift.py` asserts its parse found something.

5. **Nine commands, one per migrated tool, each reproducing its payload rather than tidying it.**
   FR 030's rule is unchanged and now applies to payloads with real branching in them: a
   reimplementation that "fixes" a quirk breaks the comparison requirement 9 rests on. The quirks
   are documented in each payload's docstring and each tool's, and the specific ones that must
   survive include `mpfb_list_assets`' cap-and-page and its `pack` directory convention,
   `mpfb_list_targets`' two-source merge and its over-60-character shapekey encoding,
   `mpfb_get_target_stack` reading `key_blocks` directly because `TargetService` cannot see a
   shape key whose name contains "basis", `mpfb_list_asset_materials`' answer being stale by
   design, and `mpfb_get_object_info`'s three `asset_info` shapes with three resolution outcomes
   each.

6. **`mpfb_get_status` keeps working when MPFB does not, and its command is not called
   `get_status`.** It is the tool whose whole value is that absence is a successful answer, so its
   command declares `requires_mpfb=False` — the second in the table to do so, and the first
   migrated tool — and the dispatcher's `mpfb_unavailable` precondition must not fire for it.
   The three tiers it answers in map onto `Resolution`'s progressive fields exactly
   (`bpy` alone / `resolution.module` / `resolution.services`), so this is a translation of the
   non-raising bootstrap rather than a redesign of it. **The name breaks the payload-to-command
   convention deliberately**: `get_mpfb_status`, because `get_status` is taken by the command that
   reports the bridge, and two commands answering "status" about two different pieces of software
   is the kind of collision that is cheap now and permanent later. The table, `list_commands`'
   summaries and [the wire](../../specifications/architecture.md#the-wire) must all say which is
   which.

7. **The tools move in four batches, in this order, and each batch is complete before the next
   starts.** A batch is a capability area, which is what makes a batch's bridge tests share one
   fixture tree and one set of MPFB quirks:

   | Batch | Tools | Fragments | Why here |
   |---|---|---|---|
   | A | `mpfb_get_status`, `mpfb_get_object_info`, `mpfb_get_macro_details` | none | No fragment, so requirement 1 is not on their critical path; and `get_status` first because it is what diagnoses every later failure, and because its naming decision should be visible early rather than discovered in review. |
   | B | `mpfb_list_presets` | `preset_files.py` | One tool, one fragment, a 125-line payload: the cheapest possible proof that requirements 1 to 4 work, and the fragment with a client-side twin, so the two-sided duplication is confronted at the smallest scale. |
   | C | `mpfb_list_rigs`, `mpfb_list_assets`, `mpfb_list_asset_materials` | `rig_lookup.py`, `asset_sections.py` | The asset library, one fixture tree, and the two fragments whose whole purpose is that a catalogue and an acting tool agree. |
   | D | `mpfb_list_targets`, `mpfb_get_target_stack` | `target_categories.py`, `modifier_reading.py` | Largest last: 656 lines of payload over 512 of fragment, the two heaviest test modules in the suite, and the only tools whose migration removes the session source cache's reason for existing. |

8. **Everything the add-on side can check is checked there, per
   [the rule FR 030 landed](../../specifications/testing.md#a-migrated-tool-is-tested-where-it-runs),
   and the closed list is not reopened.** What stays in `tests/` for a migrated tool is its local
   validation, what goes on the wire, the seam and the record — plus, new here, the fragment drift
   check of requirement 4, which is about two files in this repository and reaches no Blender at
   all. Everything else about what these nine tools *answer* moves to `bridge/test/`.

9. **The nine tools are compared field by field across both paths against one Blender, and the
   comparison cannot pass vacuously.** One script in this subdir, covering every tool in
   requirement 7, with `--self-compare` failing when handed two runs of one backend, as FR 029's
   arrangement and FR 030's script both do.

   **Two things make this harder than FR 030's and must be handled rather than discovered.**
   Several of these tools take `refresh`, and a first call that rescans changes what the second
   sees — so the script either fixes `refresh` per pair or compares the *second* call on each path,
   and says which it did. And `mpfb_list_asset_materials` is **stale by design**: MPFB caches that
   scan and nothing invalidates it, so the first of two calls in one Blender warms a cache the
   second reads. A difference there is a fact about MPFB, not a migration defect, and the script
   must be able to tell the two apart.

10. **The cost of each tool is measured on both paths, cold and warm.** Request bytes and
    milliseconds, per tool, per transport, at the add-on's default tick and at 0.05 s — FR 030's
    table extended to nine rows. The fragment-carrying tools are the point: `mpfb_list_targets`
    carries 26 KB of shared source on a cold call, which is the number
    [`shared_cache.py`](../../src/mpfbmcp/shared_cache.py) exists because of, and the warm/cold
    pair on the generated path against a single JSON request on the bridge is the clearest
    statement the pivot can make about what it buys.

11. **Nothing that works today stops working.** With nothing configured, all twenty-five tools
    behave exactly as they do now. The unit suite still runs to completion with no Blender and no
    bridge. [verification/](../../verification/) passes in **both** configurations with no edit to
    `smoke.py` — no tool is added or removed here, so
    [tests/test_verification_smoke.py](../../tests/test_verification_smoke.py)'s correspondence rule
    is unaffected — and the bridge-configuration run now sends ten of twenty-five tools over the
    bridge, still needing both add-ons for the reason
    [verification/README.md](../../verification/README.md) already records.

12. **The transition's arithmetic is written down where it is read.** `MIGRATED_COMMANDS` is the
    progress bar; [CLAUDE.md](../../CLAUDE.md)'s tool table says which tools take which path;
    [NEXT_STEPS.md](../NEXT_STEPS.md)'s stage 4 entry is corrected from "the fourteen mutating
    tools" to what is actually left.

### Out of scope, deliberately

- **Any mutating tool, and the two documentation tools.** Stage 4's, unchanged.
  `mpfb_list_urls`' connection-failure fallback in particular stays there: FR 030 already asserted
  that the seam raises the same exception type from either path, so it is inherited rather than
  discovered.
- **Moving the sixteen unmigrated tools onto `backend.send()` in bulk.** NEXT_STEPS makes this
  this effort's call and the call is **no**. The only thing it would buy is that stage 4 becomes
  one table line per tool — but stage 4 has to write a command module for each of those tools
  anyway, and changing that tool's send call is one line inside work it is already doing. Against
  that, the bulk move rewrites 134 `send_code` patch targets across the test suite for no
  behavioural change, in the effort that already has the largest test rewrite in the project's
  history. The nine tools migrating here move onto the seam because they must; the other sixteen
  move when they migrate.
- **Deleting any payload, fragment, stub or frozen test layer.** The payload is half of what
  requirement 9 compares, and the frozen layer is where the two cross-tool agreement tests that
  straddle this stage boundary keep running — `test_list_rigs`/`test_add_rig`'s claim that the
  catalogue's weights prediction equals the adder's outcome, and
  `test_get_target_stack`/`test_symmetrize_targets`' claim that every category reading agrees. Both
  halves of both pairs are still payloads after this effort, so both survive untouched; stage 5
  deletes them and the bridge's shared modules make them structurally true instead. **This effort
  therefore makes the test suite bigger, not smaller**, and saying so now is cheaper than
  explaining it later.
- **Changing the default backend.** It stays `blender_mcp` until the last tool has moved. Ten of
  twenty-five is not a reason to flip a default; an empty `MIGRATED_COMMANDS` is.
- **A bridge-side per-call record.** Deferred by FR 029 and again by FR 030. Ten commands is a
  better case for one than one command was, but it is not this effort's, and the client-side
  record already covers every call these tools make.

## Non-functional requirements

- **The seam stays below the send, with nine more chances to leak.** FR 030 made this the first
  thing a reviewer checks and it matters more here: nine tool modules are edited, five of them
  carry fragments, and the temptation to let one tool "just handle the bridge case" arrives nine
  times. One `if backend ==` in one tool module fails the requirement for all twenty-five.
- **A quirk reproduced is worth more than a quirk fixed.** Every one of these payloads carries
  behaviour that looks wrong and is deliberate, documented in a docstring that must move with the
  code. A tidy-up during a migration is indistinguishable, in the comparison, from a migration
  defect — and it destroys the one moment at which the two implementations can be checked against
  each other.
- **Evidence, not tidiness, is why the tests move.** A stub-executed payload test passes because
  the stub agrees with its author; FR 030 found two such claims about MPFB that had never been put
  to MPFB, in the dullest tool in the package. These nine tools make far larger claims —
  what MPFB's category table contains, how it resolves a rig's weights, what its asset sections map
  between — and every one of them is currently checked against a stub written by whoever wrote the
  code under test.
- **A fixture tree is deterministic or it is not a fixture.** The bridge suite's trees are built by
  the test and pointed at through MPFB's own configuration, never read from whatever the developer
  happens to have installed. A suite whose result depends on which asset packs a machine has is a
  suite that cannot fail usefully.
- **Honesty about what nine tools establish.** Read-only, no mutation, nothing written outside the
  `.blend`, no batched argument. This effort establishes that catalogues agree across both paths
  and that fragments survive becoming modules. It establishes nothing about a tool that changes a
  character, and stage 4 should be planned as though this effort had not happened in that respect.

## Architecture

**Where the new code goes.** Four client-side files touched, one new directory on the bridge, and
nine command modules. Nothing else is restructured.

| Module | What happens to it |
|---|---|
| [`src/mpfbmcp/backend.py`](../../src/mpfbmcp/backend.py) | `send()` gains `shared` / `cached_shared` and nine lines in `MIGRATED_COMMANDS`. Still the one file that knows there are two transports. |
| [`src/mpfbmcp/shared_cache.py`](../../src/mpfbmcp/shared_cache.py) | Stops being a tool-facing entry point and becomes what the seam consults on the generated path. Memo, retry and reasoning unchanged. |
| `src/mpfbmcp/tools/*.py` (nine) | One send call each. Validation, docstrings and parameter shapes untouched. |
| `tests/test_fragment_drift.py` (new) | Requirement 4. Client-side, no Blender, no `bpy`. |
| `bridge/mpfb_bridge/shared/` (new) | Five modules, one per migrating fragment. Unreachable from the wire. |
| `bridge/mpfb_bridge/commands/*.py` (nine new) | `PARAMS`, `SUMMARY`, handler, per FR 029's contract. |
| `bridge/mpfb_bridge/commands/table.py` | Nine entries, eight `requires_mpfb=True` and one `False`. |
| `bridge/test/` | A fixtures module and nine test modules. |

**What a fragment becomes, concretely.** A fragment is standalone source concatenated ahead of a
payload, reading `_MPFB_SERVICES` bound by the bootstrap; a bridge module is imported and is handed
MPFB through `resolution.services`, which every command handler already receives. That is the whole
of the mechanical difference for four of the five. The exception is `target_categories.py`, whose
`build_sections()` rebuilds what MPFB's `_modelsubpanels` builds at import time — the reason for
which is
[never import MPFB submodules directly](../../specifications/architecture.md#never-import-mpfb-submodules-directly),
and **being add-on code does not weaken that rule**. The temptation is concrete and it is the same
one FR 030 named for `_ALL_TYPES`: the bridge runs inside Blender and *could* simply import the UI
module. It must not, and the second reason is the stronger one here — that scan is a snapshot from
when Blender started, so a target installed since would be invisible to a command that imported it
and visible to `mpfb_list_targets`, which scans per call.

**`preset_files.py` is the one that also exists on this side, and it stays that way.**
[`src/mpfbmcp/preset_names.py`](../../src/mpfbmcp/preset_names.py) is the authoritative check and
runs before any transport is chosen; the bridge module restates it as the last statement before
`open()`. Two copies are warranted because the consequence of a gap is silent, and
[architecture.md already says this survives the pivot](../../specifications/architecture.md#shared-fragments).
So after this batch there are briefly **three**: `preset_names.py`, the codegen fragment that
stage-4 tools still carry, and the bridge module. `tests/test_codegen.py` already runs two of them
over one table of names and compares the *sentences*; extending it to the third is the cheap move,
and is a better answer than generalising anything.

**The command-name mapping, and the one place it breaks.** `MIGRATED_COMMANDS` is keyed by payload
filename, so it can express any mapping, and eight of the nine are the obvious one
(`get_object_info.py` → `get_object_info`). `get_status.py` → `get_mpfb_status` is the break, for
requirement 6's reason. Write the exception into the table's own comment: a reader looking for why
one line differs should not have to find this request.

**Where the bridge suite's fixture trees come from.** `tests/` already builds exactly these trees —
a real `tempfile` rig tree in `test_list_rigs`, a target tree in `test_list_targets`, an asset
library with two roots holding the same `fedora.mhclo` in `MeshAssetTestCase`, a config directory
of presets in `PresetTestCase`. Those constructions are the asset worth moving, and they should be
moved rather than reinvented: what changes is that MPFB's `LocationService` is pointed at the tree
for real instead of a stub reporting it. **How much of MPFB works without a screen is still
[explicitly unestablished](../done/029-bridge-transport-and-skeleton/README.md)**, and batch A is
where that gets answered, since `mpfb_get_object_info` and `mpfb_get_macro_details` need a
character in the scene. FR 030's rule holds for whatever is found: a test whose prerequisite is
missing **skips with a reason and never passes quietly**.

**A trap worth naming once.** `mpfb_list_assets` caps and pages its answer, and
`mpfb_list_targets` can return thousands of entries. The bridge reads a request with a 10 s
deadline and writes a response; nothing here is near either limit, but these are the first
commands whose *response* is large, and if a size limit exists anywhere in the framing it will be
found by one of these rather than by anything in stage 4.

**Anchors.** Unchanged from FR 028 and FR 030: heading anchors in `architecture.md` are linked from
`src/mpfbmcp/` docstrings and from finished requests. Check before renaming, and use an explicit
`<a id>` where the text must change.

## Affected specifications

- [architecture.md](../../specifications/architecture.md) — three sections.
  [Shared fragments](../../specifications/architecture.md#shared-fragments) currently ends with one
  paragraph predicting what a fragment becomes after the pivot; five of them have become it, so
  that paragraph is replaced by what actually happened, including where a bridge shared module
  lives and why it is not in `commands/`.
  [Supporting a second backend](../../specifications/architecture.md#supporting-a-second-backend)
  gains the fragment-carrying call and `shared_cache`'s move below the seam.
  [The wire](../../specifications/architecture.md#the-wire) gains the `get_status` /
  `get_mpfb_status` distinction as a resolved fact rather than a flagged collision.
- [testing.md](../../specifications/testing.md) — the rule was landed by FR 030 and is **applied**
  here, not rewritten. What it gains is the fixture-tree convention of requirement 8 and the
  drift check of requirement 4, which is a genuinely new *kind* of client-side test and belongs in
  the closed list explicitly rather than by implication.
  [What the suite can never establish](../../specifications/testing.md#what-the-suite-can-never-establish)
  needs its second pass: FR 030 edited it for one tool, and after this effort most of it is untrue
  for ten.
- [responses.md](../../specifications/responses.md) —
  [a response says which source answered it](../../specifications/responses.md#a-response-says-which-source-answered-it)
  should be checked against these nine rather than assumed to hold: `mpfb_list_asset_materials`'
  staleness and `mpfb_list_presets`' "what a rescan would gain" are both statements about the
  *source* of an answer, and they now cross a different transport.
- [observability.md](../../specifications/observability.md) — small: the record's unit already
  became a request, and what changes is that a fragment-carrying call's record stops existing for
  nine tools. The `# --- cached shared: <name>@<hash> (carried|reused) ---` seam is a
  generated-path artefact and the spec should say it is one.

**Explicitly not this request's.**
[mutating-tools.md](../../specifications/mutating-tools.md) — nothing migrating here mutates.
[mpfb-integration.md](../../specifications/mpfb-integration.md) — what MPFB does wrong does not
depend on how the call arrives, for the third time.
[vision.md](../../specifications/vision.md) — the end state has not changed.
[tool-interface.md](../../specifications/tool-interface.md) — FR 030 gave it its new referent and
no tool's interface changes here.

[CLAUDE.md](../../CLAUDE.md) gains: nine amended rows in the tool table saying which path each now
takes, one row for `tests/test_fragment_drift.py`, one for the bridge's `shared/` directory in the
bridge table, and the corrected count wherever "one tool migrated" is written. Map edits only; no
narrative paragraph ([why](../CLAUDE.md#lifecycle)).

## Tests

Both harnesses grow and the split holds: `python3 -m unittest discover -s tests` must still find
nothing that imports `bpy`.

**In `tests/`, with no Blender anywhere.** Per requirement 8 what is *added* is thin and what is
*moved* is large. Nine test modules lose their payload layer's reason to exist without losing the
layer, which stays frozen; what each gains is the seam-side minimum — that the right command and
params go on the wire, that local validation runs before a transport is chosen, that an error
envelope arrives intact. New: `tests/test_fragment_drift.py`, which must name the functions it
could not compare rather than skipping them silently. `tests/test_codegen.py` gains the third
preset-name copy. **Record, for each of the nine, what share of its module was ever about MPFB** —
FR 030 measured 27% for a tool whose logic is a filter and a substring test, and called it a floor.
These nine are where the rate is actually learned, and it is the only number stage 5 can be
estimated from.

**In `bridge/test/`, inside a headless Blender.** One module per command, plus a fixtures module
holding the trees of requirement 8 — moved from `tests/blender_stubs.py`'s constructions, not
reinvented. This is where the bulk of the effort's testing weight belongs, and where claims that
have until now rested on readings of MPFB's source get put to MPFB: what its category table
contains and how `target.json` merges with the user's targets; how a rig identifier resolves to a
weights file through the fallback table; what `ASSET_LIBRARY_SECTIONS` maps between; that a shape
key whose name contains "basis" is invisible to `TargetService`; that a name over 60 characters is
encoded. Expect some of these to turn out differently than the stubs assert. That is the effort
working, not failing — and each one found should be recorded in the request, as FR 030 recorded its
two.

**Live verification, in this subdir, as a script.** `check_catalogue_migration.py`, run against a
Blender with MPFB, the bridge and blender_mcp all enabled, establishing what no unit test can: the
nine field-by-field comparisons of requirement 9 including their refresh and staleness hazards; the
cost table of requirement 10; and that `get_mpfb_status` answers correctly against a
`--factory-startup` Blender with **no MPFB**, which is the one tool for which that is a success
case rather than an error path — FR 030's `serve_without_mpfb.py` is the arrangement to reuse.

**No smoke item is added.** [verification/](../../verification/) holds one item per registered tool
and this effort registers none; the run is performed in both configurations and both must pass.

## References

- [NEXT_STEPS.md, stage 3](../NEXT_STEPS.md#3-introspection-and-catalogues-migrated) — the entry
  this request implements, including the two counts it corrects.
- [FR 030](../done/030-backend-seam/README.md) — the seam, the first migration, the testing rule,
  and the four deferrals landing here: `shared_cache` routing, the `get_status` naming collision,
  how a headless test builds a character, and what a test does with a missing prerequisite.
- [FR 029](../done/029-bridge-transport-and-skeleton/README.md) — the command contract every one of
  these nine follows, and the unestablished question of how much MPFB works without a screen.
- [`src/mpfbmcp/backend.py`](../../src/mpfbmcp/backend.py) and
  [`src/mpfbmcp/shared_cache.py`](../../src/mpfbmcp/shared_cache.py) — the two modules requirements
  1 and 2 change.
- [`src/mpfbmcp/codegen/shared/`](../../src/mpfbmcp/codegen/shared) — the five fragments that
  migrate, and the two that stay behind with the mutating tools that use them.
- [`bridge/mpfb_bridge/commands/table.py`](../../bridge/mpfb_bridge/commands/table.py) — the closed
  vocabulary, and the argument a `shared/` sibling must not weaken.
