# A summary of the asset library

**Status:** Done

This scoped the NEXT_STEPS entry "A summary mode for the asset catalogue", which moved to
[HISTORY.md](../../HISTORY.md) when it landed.

**Sessions open with a question `mpfb_list_assets` answers at the wrong size:** what is in this
install at all? How many garments, hair, skins and poses are there, across which packs, under which
licenses? A caller who calls it with no arguments gets 200 rows, all `Clothes`, because `clothes`
sorts first. `truncated` is true and `total_count` honest, so nothing is wrong, and one session
still read it as "200 clothes and nothing else".

**Measured while scoping**, on this install of 926 assets in eleven subdirs. The cost is the
answer's size, not its time:

| Call | Size | Time |
|---|---|---|
| Sweeping every subdir at `limit=1000`, as a session has to for packs | **605 KB** | 0.07 s |
| `mpfb_list_assets()` | **128 KB** | 4 ms |
| `mpfb_list_assets(limit=0)` | 3.5 KB | Not separately timed |
| Subdir × pack × license for the whole library, 84 rows | **3.2 KB** | Computed from the sweep |
| Subdir × license | 332 B | Likewise |

**This corrects the entry in three ways.** `limit=0` already returns `counts_by_asset_subdir` and
`counts_by_license` with no rows, nothing says so, and it reports `truncated: true` and "this is not
the whole library". The preview-load cost the entry describes did not show up at all headless: the
whole sweep took 70 ms. A windowed Blender may differ, and the live check records it. And
`known_packs` is 1.65 KB of the 128 KB, so trimming it, as [Response bulk on the read-only
tools](../../NEXT_STEPS.md#response-bulk-on-the-read-only-tools) proposes, would not be noticed. The
rows, at 622 bytes each, are the cost.

## Goals

**Primary:** one small answer says what the library holds, across subdir, pack and license, in the
call a session makes first.

**Secondary:**

- **The easiest call is the right one.** A call naming nothing no longer returns 128 KB of one type.
- **A summary can be narrowed**, so "what is CC0" is the same call with a filter.

## Non-goals

- **Narrower rows.** A `fields` or `compact` argument would make listing cheaper, at 622 bytes a
  row. It stays in NEXT_STEPS, and nothing here depends on it.
- **Targets and saved poses.** `mpfb_list_targets` and [FR
  055](../../055-loading-and-saving-poses/README.md)'s `mpfb_list_saved_poses` have their own answers.
- **Alternative materials.** They are not in this catalogue.
- **A new tool.** Offered, and declined.

## Functional requirements

1. **`mpfb_list_assets` takes `summary`**, a real bool or null.
2. **`summary: true` answers with no rows.** `assets` is `[]` and `count` is 0. `offset` and `limit`
   stay in the answer, as null, so a caller reading the usual keys finds them.
3. **`facets` is the point of it:** one row per `{asset_subdir, pack, license, count}` that occurs,
   sorted by subdir and then by count, largest first. An asset with several claimants counts once,
   under the `pack` a row would report, and `pack_ambiguous_count` says how many did. An asset with
   no pack or no license has `null` there, and those rows are kept: 21 clothes here have no license,
   and that is worth seeing.
4. **`total_count`, `counts_by_asset_subdir`, `counts_by_license` and `license_unknown_count`
   remain**, meaning what they mean now.
5. **Filters narrow it.** `summary: true, license: "CC0"` counts the CC0 assets. `asset_subdir`,
   `name_contains`, `pack` and `license` all apply, and each `*_recognized` works as it does now.
6. **`truncated` is false in a summary**, and the `message` says it is a summary and how to get
   rows. No part of the library was cut, so the "not the whole library" sentence would be wrong.
7. **`limit` or `offset` with `summary: true` is refused here**, since a page of no rows is a
   mistake worth naming.
8. **`summary` left out or null decides by what was named.** No `asset_subdir`, `name_contains`,
   `pack`, `license`, `limit` or `offset`: a summary. Anything named: rows, exactly as today.
9. **`summary: false` gets today's 200 rows from a bare call**, so nothing is out of reach.
   `requested_summary` beside `summary` reports which applied and why.
10. **`limit=0` keeps its meaning**: counts and no rows, without `facets`. It is a page of no rows
    and it says so.
11. **`known_packs` and `asset_roots_searched` are left out of a summary**, unless a filter failed
    to be recognised. Both exist so a caller can correct itself, and neither is what a summary is
    for. The live check confirms the full answer stays under **8 KB** on this install, the summary's
    rollup limit, and records it.
12. **`refresh` works as now.**
13. **The server instructions' pointer to `mpfb_list_assets`** gains the summary, since it is where
    a session starts.

## Non-functional requirements

- **This changes what a bare call answers, on purpose.** Everything in this package's callers that
  relies on the rows has to name them. A caller outside the repository gets no error: `assets` is
  empty, the message says why, and `summary` says which applied. That is the risk, and it is
  accepted because this package is an early beta with no published release, and because the current
  answer misleads.
- **Never a second opinion.** `facets` is computed from the same scan and the same `pack` rule as a
  row, and a test sums it against the rows it stands for.
- **Description budget.** The tool's description grows by a sentence or two. The per-row field list
  is what could shrink, since a summary makes it less often needed.

## Architecture

- **Compute the facets in `commands/list_assets.py`**, after the filters and before the cap, where
  `counts_by_license` is taken. `pack` follows the same "the claimant the filter matched" rule,
  through `pack_attribution`.
- **Decide the default on the bridge side.** The tool module passes `summary` through as null, so
  the wrapper stays thin and the rule has one home. `Param("summary", TYPE_BOOLEAN, nullable=True)`.
  What was named has to be distinguishable from a default: `limit` and `offset` are declared with
  defaults at both ends, and a named `limit=200` must count as named. Pass `None` for an unnamed one
  across the socket, and apply today's 200 in the command.
- **`shared/asset_sections.py` is unchanged.**
- **Callers to update**, found by searching: `verification/smoke.py`'s item is a bare call, and its
  expected keys (`assets`, `count`, `total_count`, `truncated`, `offset`, `limit`) must all survive.
  `verification/fixtures.py` names a subdir and is unaffected.
  `bridge/test/tests/ccc_reading/list_assets_test.py` is where a bare call's tests need revisiting.
- **Pitfall:** the cache `get_asset_list()` fills is keyed by label, so counts under-report by what
  collapses. That is true today and stays true. The docstring already says so.

## Affected specifications

- [responses.md](../../../specifications/responses.md): a capped catalogue gains a summary as its first
  answer; `truncated` in that answer.
- [tool-interface.md](../../../specifications/tool-interface.md): the glossary (`summary`, `facets`); a
  null default decided by what was named, which is new and earns a sentence.
- [vision.md](../../../specifications/vision.md): no change.
- [architecture.md](../../../specifications/architecture.md): no change.

## Tests

- **Unit, `tests/test_list_assets.py`:** `summary`'s shape; `limit` and `offset` beside `summary:
  true` refused; an unnamed `limit` reaching the wire as null and a named one as itself.
- **`ccc_reading/list_assets_test.py`:** on `_fixtures.build_attributed_library()`: `facets` summing
  to `total_count` and to the rows; each filter narrowing; an asset with two claimants counted once;
  unknown license and pack kept; a bare call summarised; `summary: false` and any named argument
  giving rows; `limit=0` unchanged; an unrecognised filter bringing `known_packs` back.
- **Live check, a script in this subdir:** the sizes above against the real install, the summary's
  size, and the first call's time in a **windowed** Blender, which settles the preview cost.
- **The existing smoke item** is unchanged; its call now gets a summary, and its keys still hold.

## What landed, against the above

All thirteen requirements, verified by [`live_check.py`](live_check.py), 14 checks, 0 failures, run
twice against this install in temporary Blenders, and by 13 new bridge tests and 7 new unit tests.
Where the text above turned out wrong or short:

- **`facets` is 6.9 KB, not 3.2 KB**, and the whole summary 8,129 B: 84 rows at about 82 B each,
  where 3.2 KB allows 38 B a row, about what the four key names take alone. FR 11's 8 KB holds only
  as 8,192 B, by 63 B (7,367 B with no spaces), measured as the sizes above were, by `json.dumps` of
  the envelope. Nothing was cut to meet it, and the facets grow with the packs installed, so this
  is a line to watch rather than a margin.
- **The preview cost is settled, and it is small.** The first summary in a windowed Blender took 134
  and 128 ms in two runs, against 30 and 34 ms for the second and up to 66 ms for a `get_status`.
  Memory was not measured. The sentence calling the first call slow is gone from the description, and
  [mpfb-integration.md](../../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides)
  is corrected.
- **`attribution_conflicts` was not considered above**, and is reported over every match in a
  summary rather than left empty: `[]` would say there are none. On this install it is `[]` anyway.
- **`limit` or `offset` beside `summary: true` is refused on both sides**, not only here, since the
  socket is reachable by anything. The command's refusal is an answer with `reason:
  "invalid_arguments"`, as `mpfb_place_character`'s is.
- **`refresh` alone does not count as naming something**, since FR 8 does not list it: it says when to
  scan, not what to answer.
- **`arguments.validated_optional_flag`** replaces the private copies in
  `mpfb_create_human_from_preset` and `mpfb_write_mesh_asset`, since this would have been the third.
- **The schema ceiling rose by 150 B**, to 22,650, for three nullable arguments. The description
  ceiling did not move: dropping the slow-call sentence and the per-row glosses paid for the summary.

## Decisions taken while scoping

Asked on 2026-11-03:

- **A `summary` argument, and a bare call defaults to it.** Leaving the bare call alone, a separate
  `mpfb_describe_asset_library`, and only documenting `limit=0` plus a pack table on every answer
  were the alternatives.

*Not asked*, each argued where it is stated: the shape of `facets` (FR 3), whose 3.2 KB is why the
whole product fits; `limit` beside `summary` refused (FR 7); `known_packs` out of a summary (FR 11),
which is the one small piece of [Response
bulk](../../NEXT_STEPS.md#response-bulk-on-the-read-only-tools) worth taking.

## References

- [NEXT_STEPS: Response bulk on the read-only
  tools](../../NEXT_STEPS.md#response-bulk-on-the-read-only-tools).
- [FR 046](../046-license-in-the-catalogues/README.md): `counts_by_license` and the
  attribution.
