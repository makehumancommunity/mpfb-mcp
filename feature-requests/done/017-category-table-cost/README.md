# The category-table rebuild, and the last unmigrated payload

**Status:** Done

[FR 013](../013-live-verification/README.md) measured, for the first time, where a call's time
goes. Two of the three components were reassuring — the socket round trip is 250 ms, not the ~1.0 s
four decisions were argued against, and compiling a 50 KB generated program costs 3.7 ms, about a
thousandth of the call. The third was not.

**The three tools that share `codegen/shared/target_categories.py` are the three slowest non-import
tools in the catalogue.** `mpfb_set_targets` 3,288 ms, `mpfb_symmetrize_targets` 2,614 ms,
`mpfb_get_target_stack` 2,275 ms — means over ~1,400 recorded calls — while
`mpfb_get_macro_details`, which reads comparable data through no fragment at all, is **720 ms**.
The fragment rebuilds MPFB's modeling-category table by walking the target directories on **every
call**, because `ui/model/_modelsubpanels.py` builds its own copy at module import time and cannot
be asked for it. That is ~1.5-2 s per call, and it is the largest single cost in this package that
is neither transport nor MPFB doing geometry.

It also has a second effect worth naming: it is what makes
[FR 008](../008-detail-targets/README.md)'s batching decision so strongly right. Thirty modifier
changes cost 3.6 s in one call and 98.4 s in thirty — and the 95 s difference is thirty rebuilds of
this table, not thirty round trips, which are only 7.5 s of it.

The same file is where the last unmigrated payload belongs.
[`payloads/list_targets.py`](../../../src/mpfbmcp/codegen/payloads/list_targets.py) walks the same
directories by a different route, which [NEXT_STEPS.md](../../NEXT_STEPS.md#modeling) has flagged as a
drift risk since FR 008 and which is cheapest to do while something else is touching that file.

## Goals

**Primary: stop paying ~2 s per call to rediscover something that does not change.**

**Secondary: migrate `payloads/list_targets.py` onto the fragment**, closing the last case of two
payloads walking the same directories by different routes.

**Explicitly not a goal:** making the table *correct* in some new way. It reproduces
`_modelsubpanels`' construction, quirks included — including the `.gz` naming divergence
[FR 008](../008-detail-targets/README.md#verification-status) confirmed live — and reproducing
that is the point.

## Functional requirements

- **FR-1.** The table is built at most once per Blender session per tool invocation chain, not once
  per call. Where the cache lives is the interesting question: it cannot live in mpfb-mcp, which
  runs in a different process, so it has to be a module-level or scene-level cache **inside
  Blender**, established by generated code.
- **FR-2.** The cache is invalidatable, and there is a way for a caller to ask for a rescan. This
  is what `mpfb_list_rigs` and `mpfb_list_assets` already offer as `refresh`, and the vocabulary
  should match theirs rather than inventing a second one.
- **FR-3.** A stale answer must be **visible**, not merely possible. A target installed since the
  cache was built is exactly the case
  [FR 006](../006-list-targets/README.md) made `mpfb_list_targets` able to see, and a cache that
  silently loses that would be a regression.
- **FR-4.** `payloads/list_targets.py` is migrated onto the fragment, and the shape difference is
  reconciled rather than papered over: its scan is a flat user-target listing carrying
  `listed_in_mpfb_ui`, with no synthesized categories at all.
  [verification/census.py](../../../verification/census.py) names the two functions this closes —
  `files_matching()` and `read_target_json()`, reported under REIMPLEMENTED against
  `target_categories.py` — and running it afterwards is how FR-4 is shown to be done.
  [FR 015](../015-fourth-shared-fragment/README.md) landed **without touching
  `target_categories.py`**, so the concern that the two efforts would collide over that file is
  settled: this one owns it.
- **FR-5.** The four affected checklists are re-run and their records updated.
- **FR-6.** The cost is re-measured with
  [verification/measure.py](../../../verification/measure.py) and the before/after recorded.

## Non-functional requirements

**Correctness over speed, and it is not close.** A wrong category table means a modifier written to
the wrong shape key. Any caching scheme whose failure mode is a silently stale answer to
`mpfb_set_targets` is worse than the 2 s it saves.

**No diagnostic setting may change the program.** The property
[FR 012](../012-observability/README.md)'s record depends on. If the cache is switchable, it is
switchable by an argument that is part of the call, not by an environment variable read on this
side.

**A cache inside Blender outlives the mpfb-mcp process.** Two servers against one Blender, or a
server restarted mid-session, must not see each other's stale table. Key it on something that makes
that safe, or accept a per-call check cheap enough to be free.

## Architecture

`codegen/shared/target_categories.py` is 18 KB and 443 lines, assembled into three programs. The
scan it performs is `os.walk()` over MPFB's bundled targets directory plus the user target
directories, plus a read of `target.json`.

**The obvious mechanism is a module-level dict on a module MPFB already has loaded**, reached the
way payloads already reach `ASSET_LIBRARY_SECTIONS` and `ALL_EXTRA_GROUPS` — see
[Reading module-level names MPFB does not publish](../../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish).
Writing one is a different matter from reading one, and this request should decide explicitly
whether mpfb-mcp may put state into MPFB's process, or whether the cache belongs somewhere it owns.

**Pitfall: `_modelsubpanels` is itself a snapshot.** MPFB's own panel cannot see a target installed
since Blender started, which is why this fragment reimplements the scan rather than importing it.
A cache here re-introduces exactly that staleness unless FR-3 is taken seriously.

**Pitfall: measure before optimising.** The ~2 s figure is the difference between two tools, not a
profile. The first task is to confirm the cost is the directory walk rather than the `target.json`
parse or the shape-key enumeration — a payload printing its own timings into the envelope's
`stdout`, which is how FR 013 took its split.

## Affected specifications

- **[specifications/architecture.md](../../../specifications/architecture.md)** —
  [Shared fragments](../../../specifications/architecture.md#shared-fragments), for the migration; and a
  decision about whether generated code may hold state inside Blender between calls, which is new
  and belongs beside
  [Reading module-level names MPFB does not publish](../../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish).
- **[specifications/mpfb-integration.md](../../../specifications/mpfb-integration.md)** —
  [MPFB caches what it scans](../../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides)
  is where the three caches a tool already has to explain are collected, and a cache of *ours*
  inside Blender is the first one that is not MPFB's. FR-2's `refresh` and FR-3's visible staleness
  are the same obligations stated there. If a tool's description grows to say so, note that
  [FR 016](../016-trim-tool-descriptions/README.md) left about 700 B of room under the ceiling
  `tests/test_description_budget.py` asserts.

## Tests

Unit tests over the existing `tempfile` target tree, with one added case that is the whole risk: a
target written to the tree *between* two calls, asserting the documented behaviour — whether that
is "seen" or "seen only after refresh" is FR-3's decision, but it must be asserted either way.

**Live re-verification is required**, for the four checklists whose programs change
([FR 006](../006-list-targets/README.md), [FR 008](../008-detail-targets/README.md) and the two
target tools within it), plus a re-run of `verification/measure.py` for FR-6. One command each.

## References

- [FR 013's review](../013-live-verification/review.md#do-the-three-payload-count-driven-decisions-still-hold) —
  the measurements, including the batching table this cost explains.
- [NEXT_STEPS.md](../../NEXT_STEPS.md#modeling) — the `list_targets` migration, flagged since FR 008.


## Outcome

**The diagnosis in this request was wrong, and finding that out is most of what it produced.**

The three tools sharing `target_categories.py` really are the slowest non-import tools in the
catalogue, and the fragment really is rebuilt on every call. But the rebuild was never the cost.
Timed inside Blender, the whole table — `target.json`, the custom scan, the user-directory scan and
the 766-entry index — takes **4.0 ms**, and `os.walk` over the three roots takes **1.1 ms** of that.
The ~1,500 ms difference between `mpfb_set_targets` and `mpfb_get_macro_details` is entirely
explained by something else:

**blender_mcp's add-on reads one 4 KB chunk of a request per timer tick**
(`mcp_to_blender_server._service_clients()` calls `conn.recv(4096)` once and returns). Its
preference for that tick is 0.25 s, and it drops to 1.0 s after five seconds without a request
*finishing* — bytes arriving do not count as work. So a generated program costs about **250 ms per
4 KB** against a busy Blender and **1 s per 4 KB** against an idle one, and it makes no difference
at all what the program computes:

| program | chunks | busy | idle |
|---------|--------|------|------|
| empty | 1 | 254 ms | 67 ms |
| 10 KB | 3 | 757 ms | 2,063 ms |
| 20 KB | 6 | 1,519 ms | 5,081 ms |
| 40 KB | 11 | 2,780 ms | 10,087 ms |

Which also corrects the number four decisions in this package were argued against: "the round trip
is 250 ms" is not a round trip, it is one tick, measured on a one-chunk program.
[FR 013](../013-live-verification/review.md) re-derived those decisions on real numbers and
they survive, but the figure means something different now.

### What was built instead

**The session cache holds fragment source, not the table.** `codegen/shared_loader.py` emits a
loader that keeps a fragment's source in a `sys.modules` module of ours inside Blender, keyed by
`<file>@<sha256[:12]>`; `mpfbmcp/shared_cache.py` decides whether a given call carries the source or
names it, and re-sends once if Blender turns out not to hold it. The first attempt at this request
did build a cache of the *table* — two fragments, a directory-mtime signature, a `refresh` argument
on four tools and a `category_table` field in four responses — and it was thrown away when it was
measured: it saved nothing, because the accessors and the cache machinery it needed on every call
came to as many bytes as the scan it stopped sending, and it made `mpfb_list_targets` slower.
Caching the source is both the larger saving and the safer one, and the two are the same fact —
what a call pays for is the description, not the work.

| tool | before | first call | later calls |
|------|--------|-----------|-------------|
| `mpfb_list_targets` | 19,338 B / 5 chunks | 34,950 B / 9 | **16,970 B / 5** |
| `mpfb_get_target_stack` | 37,537 B / 10 | 39,767 B / 10 | **17,877 B / 5** |
| `mpfb_set_targets` | 57,196 B / 14 | 59,581 B / 15 | **35,612 B / 9** |
| `mpfb_symmetrize_targets` | 50,716 B / 13 | 53,119 B / 13 | **25,240 B / 7** |

Measured against the live Blender, busy interval: **1,020 / 1,519 / 1,533 / 1,775 ms saved per
call** respectively. Against an idle Blender — which is what an agent that thinks between calls
meets — the same four saved **4.0 / 6.0 / 6.0 / 7.0 s** — the `shared_source_cache` block that
[verification/measure.py](../../../verification/measure.py) writes into its (gitignored) results
directory.
The chunk counts are the durable half of that: what a chunk costs is
`transport_by_program_size`, and the two multiply.

`mpfb_list_targets` is the one that merely breaks even in steady state, and is 9 chunks rather than
5 on its *first* call — the price of FR-4, which moved 18 KB of fragment into a program that
previously carried none. It is stated rather than hidden.

### Against the functional requirements

- **FR-1** — met, in a stronger form than asked: the table is built *every* call (4 ms), and what
  happens at most once per Blender session is sending the code that builds it.
- **FR-2 and FR-3** — met by removing the possibility rather than by adding an argument. A cache of
  source keyed by a hash of that source cannot be stale, so there is nothing for a `refresh` to
  refresh and no staleness to make visible; `mpfb_list_targets` still sees a target installed since
  Blender started, and `tests/test_shared_cache.py` asserts exactly that across two calls. Four
  tools therefore gained no argument and no response field, and the tool-description budget is
  unchanged at 47,759 B.
- **FR-4** — met. `payloads/list_targets.py` now takes its scan from the fragment, and
  [verification/census.py](../../../verification/census.py) no longer reports `files_matching()` or
  `read_target_json()` under REIMPLEMENTED. Two shape differences were reconciled rather than
  papered over, both noted in that payload's docstring: the `custom` section is now labelled as
  MPFB labels it ("Custom targets") rather than by its directory name, and a `target.json` category
  with no `name` is dropped rather than listed.
- **FR-5** — met. `verification/run_all.py` in full: 85 passed, 0 failed, 3 skipped (the three that
  need a restarted Blender, unchanged).
- **FR-6** — met. `verification/measure.py` gained `transport_by_program_size`, which is the
  measurement this request turned out to be about, and `shared_source_cache`, which is its
  before/after.

### What this leaves

**The 4 KB chunk is a defect in blender_mcp, not a law of nature**, and fixing it there would
remove most of the cost from every tool in this package — a loop draining the socket instead of one
`recv` per tick. It is not fixed here, because blender_mcp is external and unmodified; the entry is
[in NEXT_STEPS.md](../../NEXT_STEPS.md#file-the-4-kb-chunked-read-against-blender_mcp). Until then the
add-on's own `timer_interval_active` preference is a four-to-five-times speedup a user can apply
today, which [CLAUDE.md](../../../CLAUDE.md#commands) now says.

**The mechanism generalises and has been applied narrowly.** Only the four tools here go through
`shared_cache.send()`; `mpfb_add_asset` and `mpfb_set_skin` carry `asset_sections.py` on every call
and the two rig tools carry `rig_lookup.py`, and nothing about those is different in kind. That is
a follow-up rather than scope creep here, and it is deliberately not a large one.
