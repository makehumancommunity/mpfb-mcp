# `mpfb_list_asset_materials` should be able to rescan

**Status:** Done

> **The pivot has landed in full, and this request predates it.** MPFB's Blender-side logic lives
> in the MPFB Bridge add-on ([`bridge/`](../../../bridge)); a tool names a command from a closed
> vocabulary and hands over its parameters.
> [FR 033](../033-retire-the-generated-code-path/README.md) deleted the generated-code path
> and everything under it, so **wherever the text below says *payload*, read *command*, and
> wherever it names `codegen/`, `send_code()` or a *shared fragment*, read
> `bridge/mpfb_bridge/commands/`, `backend.send()` and `bridge/mpfb_bridge/shared/`.** The request
> has not been rewritten — a request is a record of what was planned — and the translation is
> mechanical.
>
> Three things that are genuinely different rather than renamed, and each changes work this
> request estimates:
>
> - **A new tool is a tool module, one `register()` call, a command module and one line in
>   [`commands/table.py`](../../../bridge/mpfb_bridge/commands/table.py).** There is no payload to
>   write, no assembler to call and no fragment to name in an `assemble()` call; a command imports
>   a shared module the way it imports `os`.
> - **Assertions about what a tool *answers* go in `bridge/test/`**, against a real MPFB in a
>   headless Blender, not against stubs in `tests/` — see
>   [testing.md](../../../specifications/testing.md#a-tool-is-tested-where-it-runs).
>   [`bridge/test/tests/_fixtures.py`](../../../bridge/test/tests/_fixtures.py) holds what such a test
>   needs. What stays in `tests/` is the tool's own validation and what reaches the wire.
> - **Program size is no longer a cost.** Any argument below that weighs how much generated source
>   a design would send is arguing about a tax this shape does not levy; see
>   [HISTORY.md](../../HISTORY.md#fr-033--the-generated-code-path-retired) for what that tax was.


[FR 011](../011-skin-and-materials/README.md) documented the alternative-material listing as
unavoidably stale: `AssetService.alternative_materials_for_asset()` caches per
`(asset_source, asset_subdir)` and, as the request read it, never invalidates. The tool says so in
its docstring, and [FR 013](../013-live-verification/README.md) confirmed the staleness
behaviourally — a new `.mhmat` written into an asset's directory between two calls is not seen.

But the same session refuted the premise. **`AssetService.invalidate_alternative_materials_cache()`
exists**, and clears both `_ALTERNATIVE_MATERIALS` and `_ALTERNATIVE_MATERIAL_TILES`. Nothing calls
it, so the staleness is real; "cannot be invalidated" is not. That makes this the smallest
outstanding item in the catalogue: a tool documents a limitation that MPFB does not have.

**Half of that is already fixed.** [FR 019](../019-file-mpfb-defects/README.md)'s FR-5 struck the
false half of the claim wherever this repository stated it — the tool docstring, the payload,
`specifications/responses.md` and the root `CLAUDE.md` no longer say the cache cannot be cleared or
that no `refresh` argument could help. What is left for this request is the argument itself, which
is the whole of its primary goal; the secondary goal below is now a smaller edit than it was.

## Goals

**Primary: `mpfb_list_asset_materials` gains a `refresh` argument**, matching the one
`mpfb_list_rigs` and `mpfb_list_assets` already have, so a user who has just installed a material
can see it.

**Secondary: finish correcting the docstring.** FR 019 removed the false claim; what remains is
that the docstring still offers a restarted Blender as the only remedy, because at the time it was
written that was true of this tool.

## Functional requirements

- **FR-1.** `refresh` is a strict `bool` — not a truthy value — following `mpfb_list_rigs`'
  precedent, where `refresh="false"` would otherwise rescan the disk.
- **FR-2.** With `refresh: true`, `AssetService.invalidate_alternative_materials_cache()` is called
  before the scan, and the response says the cache was cleared. Note this clears the cache for
  **every** asset, not only the one being listed, which is a side effect on other tools' answers
  and must be reported rather than hidden.
- **FR-3.** The docstring stops offering a Blender restart as the remedy and names the argument
  instead. It already describes the staleness correctly — a cache nothing invalidates
  automatically — since FR 019 corrected that much.
- **FR-4.** The default stays `false`. A listing that rescans by default would make the cheap call
  expensive and would clear a cache other tools benefit from.

## Non-functional requirements

**Honesty about the blast radius.** The invalidator is global. A tool whose `refresh` quietly
resets state other tools depend on is worse than one that cannot refresh at all, so the response
has to name what it did.

**Consistent vocabulary.** `refresh` means the same thing in three tools after this change, which
is worth more than a more precise name here.

## Architecture

The tool is `src/mpfbmcp/tools/list_asset_materials.py` and its payload
`src/mpfbmcp/codegen/payloads/list_asset_materials.py`. The invalidator is a plain static method on
`AssetService`, which is already in the `SERVICES` dict, so no module-level read is needed — unlike
the cache dicts themselves, which are module-level in `assetservice.py`.

**The docstring has a budget.** [FR 016](../016-trim-tool-descriptions/README.md) brought the
descriptions to a third of their size, and `tests/test_description_budget.py` has capped them ever
since; [FR 024](../024-documentation-urls/README.md) raised that ceiling to 52,200 B for two
new tools and [FR 025](../025-character-presets/README.md) to 59,200 B for three more, each
leaving the same paragraph of room it always leaves — 58,529 B across twenty-five tools.
So FR-3's rewrite has about 670 B of headroom. It should not need any: the paragraph it replaces
is longer than "`refresh` rescans; it clears the cache for every asset, and `cache_invalidated`
says so" is. The measured figure has moved twice already; run
`python3 tests/test_description_budget.py` for the current one rather than trusting the numbers
above.

**Pitfall: `exclude_default` is still dead.** The same function accepts and never reads it, which
[FR 013](../013-live-verification/README.md) also confirmed. `mpfb_list_asset_materials` flags the
asset's own material rather than removing it, and that stays: removing it would be this package
inventing a behaviour MPFB does not have.

## Affected specifications

- **[specifications/responses.md](../../../specifications/responses.md)** —
  [How tools bound a large answer](../../../specifications/responses.md#how-tools-bound-a-large-answer)
  is where `refresh` is described for the other two catalogue tools, and
  [A tool may report a fact MPFB's own UI does not show](../../../specifications/responses.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show)
  carries the "the tool is the stale one" clause this change makes conditional.
- **[specifications/mpfb-integration.md](../../../specifications/mpfb-integration.md)** —
  [MPFB caches what it scans](../../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides),
  added by [FR 016](../016-trim-tool-descriptions/README.md), lists this cache as the one with no
  caller for its invalidator and names this request as the fix. Its last bullet — "until it lands,
  the tool says so" — is what stops being true here.

## Tests

Unit tests: the stub `alternative_materials_for_asset()` already caches per
`(asset_source, asset_subdir)` and never invalidates, and one test already writes a new MHMAT
between two calls to assert the staleness. The stub needs the invalidator added — reproducing
MPFB's, which clears *both* dicts — and that same test gains a `refresh: true` third call which
does see the new file.

**Live verification is required**, and since
[FR 023](../023-verification-smoke-test/README.md) it belongs **in this request's own subdir** as
a script, not in `verification/` — which is now a smoke run of one default call per tool and
asserts nothing about values. What that script has to do is small and is already written down: the
deleted `check_fr011.py` wrote a probe `.mhmat` beside an installed asset between two calls to
`mpfb_list_asset_materials` and asserted the second answer did not change; this effort's version
adds a third call with `refresh: true` that does see the new file, and deletes the probe afterwards.
Git holds the original if the exact fixture is wanted back. `verification/` gains nothing from this
effort — `mpfb_list_asset_materials` already has its smoke item, and a new argument does not earn a
second one.

## References

- [FR 013's review](../013-live-verification/review.md#the-seven-candidate-mpfb-defects) — where
  the invalidator was found, and the other refuted candidate defect beside it.

## Verification status

Done and verified. `mpfb_list_asset_materials` gained `refresh` (default `false`) exactly as
FR-1 through FR-4 describe: rejected locally unless a real `bool`
([`list_asset_materials.py`](../../../src/mpfbmcp/tools/list_asset_materials.py)); when `true`,
[the bridge command](../../../bridge/mpfb_bridge/commands/list_asset_materials.py) calls
`AssetService.invalidate_alternative_materials_cache()` before scanning and reports it through a
new `cache_invalidated` field, named in the response message along with the fact that the clear is
global; the docstring no longer offers a Blender restart as the remedy. The unit suite
(`tests/test_list_asset_materials.py`) and the bridge's own headless suite
(`bridge/test/tests/mmm_list_asset_materials_test.py`, which now asserts the refreshed call sees a
probe material a plain call still misses) both pass. This effort's own live check,
[`check_fr018.py`](check_fr018.py), ran twice against a real Blender with an equipped MHCLO asset —
writing and removing a probe `.mhmat` beside it on disk each time — and passed both times,
including once where MPFB's cache already held a stale entry from the prior run, which the global
`refresh` cleared as documented. No new smoke item: `mpfb_list_asset_materials` already has one,
and a new argument does not earn a second.
