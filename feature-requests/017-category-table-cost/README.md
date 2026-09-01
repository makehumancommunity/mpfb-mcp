# The category-table rebuild, and the last unmigrated payload

**Status:** Proposed

[FR 013](../done/013-live-verification/README.md) measured, for the first time, where a call's time
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
[FR 008](../done/008-detail-targets/README.md)'s batching decision so strongly right. Thirty modifier
changes cost 3.6 s in one call and 98.4 s in thirty — and the 95 s difference is thirty rebuilds of
this table, not thirty round trips, which are only 7.5 s of it.

The same file is where the last unmigrated payload belongs.
[`payloads/list_targets.py`](../../src/mpfbmcp/codegen/payloads/list_targets.py) walks the same
directories by a different route, which [NEXT_STEPS.md](../NEXT_STEPS.md#modeling) has flagged as a
drift risk since FR 008 and which is cheapest to do while something else is touching that file.

## Goals

**Primary: stop paying ~2 s per call to rediscover something that does not change.**

**Secondary: migrate `payloads/list_targets.py` onto the fragment**, closing the last case of two
payloads walking the same directories by different routes.

**Explicitly not a goal:** making the table *correct* in some new way. It reproduces
`_modelsubpanels`' construction, quirks included — including the `.gz` naming divergence
[FR 008](../done/008-detail-targets/README.md#verification-status) confirmed live — and reproducing
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
  [FR 006](../done/006-list-targets/README.md) made `mpfb_list_targets` able to see, and a cache that
  silently loses that would be a regression.
- **FR-4.** `payloads/list_targets.py` is migrated onto the fragment, and the shape difference is
  reconciled rather than papered over: its scan is a flat user-target listing carrying
  `listed_in_mpfb_ui`, with no synthesized categories at all.
- **FR-5.** The four affected checklists are re-run and their records updated.
- **FR-6.** The cost is re-measured with
  [verification/measure.py](../../verification/measure.py) and the before/after recorded.

## Non-functional requirements

**Correctness over speed, and it is not close.** A wrong category table means a modifier written to
the wrong shape key. Any caching scheme whose failure mode is a silently stale answer to
`mpfb_set_targets` is worse than the 2 s it saves.

**No diagnostic setting may change the program.** The property
[FR 012](../done/012-observability/README.md)'s record depends on. If the cache is switchable, it is
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
[Reading module-level names MPFB does not publish](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish).
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

- **[specifications/architecture.md](../../specifications/architecture.md)** —
  [Shared fragments](../../specifications/architecture.md#shared-fragments), for the migration; and a
  decision about whether generated code may hold state inside Blender between calls, which is new
  and belongs beside
  [Reading module-level names MPFB does not publish](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish).
- **[specifications/vision.md](../../specifications/vision.md)** — `mpfb_list_targets`' catalog entry,
  if it gains `refresh`.

## Tests

Unit tests over the existing `tempfile` target tree, with one added case that is the whole risk: a
target written to the tree *between* two calls, asserting the documented behaviour — whether that
is "seen" or "seen only after refresh" is FR-3's decision, but it must be asserted either way.

**Live re-verification is required**, for the four checklists whose programs change
([FR 006](../done/006-list-targets/README.md), [FR 008](../done/008-detail-targets/README.md) and the two
target tools within it), plus a re-run of `verification/measure.py` for FR-6. One command each.

## References

- [FR 013's review](../done/013-live-verification/review.md#do-the-three-payload-count-driven-decisions-still-hold) —
  the measurements, including the batching table this cost explains.
- [NEXT_STEPS.md](../NEXT_STEPS.md#modeling) — the `list_targets` migration, flagged since FR 008.
