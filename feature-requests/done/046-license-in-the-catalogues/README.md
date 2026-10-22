# License in the catalogues: who made an asset, and under what terms

**Status:** Done

Two sessions in a row were briefed to use CC0 assets only, and neither could find out through this
server which assets those were. The line-up session ([FULL_SESSION.md](../../FULL_SESSION.md)) read
`data/packs/*.json` by hand. The man-and-woman scene session did the same thing again from scratch:
ten `mpfb_list_assets` calls, then a join against the pack files. So the cost is paid once per
session, not once per project. On this install the answer matters. Of 639 installed garments, 226
are CC0, 392 are CC-BY and 21 have no pack metadata at all. **About two thirds of the library cannot
be used under a CC0 brief**, and no answer from this server says which two thirds.

MPFB already has the fact. Every pack JSON under the user data `packs/` directory records, per
asset, a `license`, an `author` and a `source` page: 1,606 entries on this install, all with all
three keys, 1,016 `CC0` and 590 `CC-BY`. `mpfb_list_assets` reads those same files to derive
`pack`. It joins an asset's containing directory name against the asset names the packs claim
([responses.md](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact)),
and then throws away everything else in the entry it matched.

**The alternative materials are the worse half.** They are not in `mpfb_list_assets`' answer, so a
hand-made join against that answer cannot reach them. `mpfb_list_asset_materials` reports `path`,
`fragment`, `name` and `is_default`, and nothing about who made the file. The scene session recoloured
two characters' hair with five alternatives by four authors. It could check them only by grepping
the pack files for each name. They were CC0, but a garment recoloured with a CC-BY material would
have looked just as compliant.

**Scoping corrected one claim in the NEXT_STEPS entry.** That entry says the 21 garments without
metadata are "the MakeHuman system assets, CC0 by provenance". They are not. The system assets have
a pack file of their own, `makehuman_system_assets.json`, with 94 entries, all CC0. The 21 are
community assets installed without a pack (`toigo_diamond_ring_1_5_carat_right`,
`nurse_uniform_coat_clothsim`, `elvaerwyn_heart_belly_jewel`, ...). Their license is unknown, and
this request must report it as unknown rather than guess it.

## Goals

- **Primary:** every row in `mpfb_list_assets` and `mpfb_list_asset_materials` says what license
  the asset is under and who made it, wherever pack metadata records that, and says plainly when it
  does not.
- **Primary:** `mpfb_list_assets` takes a `license` filter, so "CC0 garments" is one call, and it
  counts by license, so a caller can see what the filter costs ("226 of 639") before narrowing.
- **Primary:** a pack filter no longer contradicts itself. When several packs claim an asset, the
  answer names all of them, and a `pack` filter reports the claimant it matched.
- **Secondary:** an equipped asset reports its license through `mpfb_get_object_info`, and its
  alternative material reports one too, so a finished character can be checked against a brief
  without going back to the catalogue. `mpfb_get_character_summary` carries the same fields in its
  assets section.
- **Secondary:** a registered pack whose assets are not on disk is visible as such.
- **Not a goal:** a pose catalogue (there is none yet; the shared module this adds is what one
  would use). Nor license on `mpfb_list_targets` (211 pack entries are targets, but a target file
  is not in a directory named for it, so the join below does not hold for targets; see
  [Decisions taken while scoping](#decisions-taken-while-scoping)). Nor a summary mode for the
  asset catalogue, which is
  [its own entry](../../NEXT_STEPS.md#a-summary-mode-for-the-asset-catalogue). This request gives
  that entry its license facet and nothing else. Nor any judgement about what a license permits:
  the tools report what the metadata says, and never say "safe to use".

## Functional requirements

### The attribution

1. **One reading of pack metadata, shared by every command that reports a license.** It resolves an
   installed file to the packs that claim it, and to each claim's `license`, `author` and `source`.
   It is the derivation `list_assets` already does for `pack`, moved out of that command and
   extended.
2. **The join keys on the file's containing directory, as `pack` does today**, with the existing
   exception: a file lying directly in an asset root is not attributed. Where that directory claims
   nothing, a fallback to the **file stem** is considered. Eye materials need it:
   `eyes/materials/brown.mhmat` sits in a directory called `materials`, while
   `makehuman_system_assets.json` claims it as `brown`. On this install the fallback would
   attribute exactly nine files, all under `eyes/materials/`, and nothing else. Stems do repeat
   (`teeth` seven times, `green` three times), but every repeat sits in a directory that is already
   claimed, so the fallback never reaches them. The effort confirms this with its live check before
   adopting the fallback (see [Tests](#tests)), and the docstring states the condition it rests on.
3. **A material in its asset's own directory takes the asset's attribution.** A material in a
   directory of its own takes that directory's. On this install that is 747 and 184 material files
   respectively. The first case is right when the garment's author shipped the material. It cannot
   be told apart from a material someone dropped into that directory by hand. The docstring says so.
4. **`license` is reported only when every claimant agrees.** If two packs claim one asset under
   different licenses, `license` is `null` and every claim is reported. None disagree on this
   install: 92 assets are claimed by more than one pack, and all 92 agree on license and author.
   That is why `pack_ambiguous` does not make `license` ambiguous. The rule still has to exist,
   because the next install may differ.
5. **An asset with no claim reports `license: null` and `author: null`**, and this is an ordinary
   answer, not a failure. It is never filled in from the pack's name, from the asset's subdir, or
   from a `license` line in the asset file (see
   [Decisions taken while scoping](#decisions-taken-while-scoping)).

### `mpfb_list_assets`

6. **Each row gains `license`, `author` and `source`.** `source` is the asset's page on the
   community site. A CC-BY asset needs it, because attributing the asset means naming the author and
   linking the work.
7. **Each row gains `packs`**: every installed pack that claims the asset, sorted. `pack` stays. When
   a `pack` filter was passed, `pack` is the first claimant that **matched the filter**, so
   `pack="_cc0"` never answers with `pack: "hats01"`. With no filter it is the first claimant, as
   today. `pack_ambiguous` stays and stays `len(packs) > 1`. The responses specification uses it as
   its example of a flag that marks an unsafe derivation, and `mpfb_add_asset` mirrors it.
8. **A `license` argument filters rows**, case-insensitively and by exact match against the
   recorded string (`"cc0"` finds `CC0` and does not find `CC-BY`). It is optional text, checked for
   shape on the tool side. Its vocabulary is the metadata's own, so it is checked on the bridge side:
   an unknown value is answered with `license_recognized: false` and `known_licenses`, read from the
   installed metadata. This is the same treatment `pack` gets. An asset with no recorded license
   never matches a `license` filter.
9. **The answer counts by license**: `counts_by_license` holds every recorded license, plus a count
   of assets with none. It is computed after the subdir, name and pack filters and before the
   `license` filter and the cap, so a call filtered to CC0 still says how many it left out.
10. **A `pack` filter reports what it matched**: the installed pack names that contain the pattern,
    each with the number of installed assets this scan attributed to it. A pack registered with
    nothing on disk then shows as `0` and does not silently match nothing. That is the
    `accessories01_cc0` case, where four capes are in the metadata and none are on disk.

### `mpfb_list_asset_materials`

11. **Each material, and the `default_material`, gains `license`, `author`, `source` and `packs`**,
    through the same attribution.
12. **`refresh` also invalidates MPFB's pack metadata cache**, and says so. Today it clears only the
    alternative-material cache, so a pack installed since Blender started would show its materials
    as attributed to nothing until `mpfb_list_assets(refresh=True)` happened to run. The pack
    metadata rescan is a reread of a hundred small JSON files, which is cheap.

### Equipped assets (secondary)

13. **`mpfb_get_object_info`'s `asset_info` gains `license`, `author` and `packs`** for the file the
    object was loaded from, and the same three for its `alternative_material` when it has one. This
    uses the same attribution, so the answer cannot disagree with the catalogue that listed the file.
14. **`mpfb_get_character_summary`'s assets section carries `license` per asset**, and per
    alternative material where one is set. As always it is a subset of the detailed tool's fields
    under the same names
    ([never a second opinion](../../../specifications/responses.md#a-summary-is-never-a-second-opinion)).
    The effort measures what this adds to the 8 KB worst case. If the field does not fit, the summary
    carries a count by license instead.

## Non-functional requirements

- **Honesty over coverage.** A field that looks recorded will be quoted back to the user as fact,
  and here that fact may end up in a licensing decision. Every `null` stays `null`, every derivation
  is described as one in the docstring, and the message of a `license`-filtered answer says that
  assets with no recorded license were excluded, not that they were checked.
- **Response size.** Up to 200 rows, each gaining three or four fields, one of them a URL. The
  effort measures a default `mpfb_list_assets()` page and a 1000-row page before and after and
  records both. If the growth is significant, `source` may move behind an argument. That is a
  decision for the measurement, not one to make in advance.
- **Description budget.** Two tool descriptions grow, and `tests/test_description_budget.py`
  holds the ceiling. What `license` means belongs in the descriptions in one sentence. The
  derivation's caveats belong in the bridge docstrings.
- **No new cost on a call that already paid.** The pack metadata is already read on every
  `list_assets` call. Attribution must reuse that read, not add a second one per row or per
  material.

## Architecture

- **A new shared module in `bridge/mpfb_bridge/shared/`**, called something like
  `pack_attribution.py`. It takes `services` and answers "which claims cover this file". `list_assets`,
  `list_asset_materials`, `get_object_info` (through `shared/asset_info.py`) and
  `get_character_summary` all need it, and two of them reporting different licenses for one file is
  exactly the disagreement the
  [shared-module rule](../../../specifications/architecture.md#shared-modules-and-what-warrants-one)
  exists for. `list_assets`' `_read_pack_index` and `_packs_claiming` move into it. Build the index
  once per call and pass it down, as `list_assets` does now. Do not rebuild it per row.
- **How the metadata is read.** MPFB publishes the pack names and the asset names in each pack
  (`get_pack_names()`, `get_asset_names_in_pack()`), but **not the entries themselves**. The parsed
  JSON lives in `assetservice.py`'s module global `_PACKS`. There are two ways to reach it:
  - Read `_PACKS` through `mpfb_surface.module_level()` on `AssetService`'s module, after
    `get_pack_names()` has populated it. Names and licenses then come from one scan, and
    `refresh` keeps its present meaning. The fallback when the name is missing is attribution
    without license: `pack` and `packs` are still reported, and `license` is `null` with a message
    saying why.
  - Read the JSON files directly, located through `LocationService.get_user_data("packs")`, under
    [the rules for reading MPFB's data files](../../../specifications/mpfb-integration.md#reading-mpfbs-data-files-directly).
    This bypasses MPFB's cache, so `pack` (cached) and `license` (fresh) could describe two
    different scans.

  **The first is recommended.** The effort should also propose a public getter upstream, such as
  `AssetService.get_pack_metadata(pack_name)`, in `mpfb2/features/MCP_DISCOVERED_BUGS.md` or as a
  change to MPFB. If that getter is present, the module uses it before the private read.
- **`list_asset_materials` has a different subdir rule** from `list_assets`
  (`str(object_type).lower()`, not the section table; see its docstring). Attribution must not care
  about that: it takes a file path and the roots to treat as asset roots, and the caller supplies
  both.
- **The `pack` filter today matches against `_claimants`**, every claimant, and then reports the
  first. Requirement 7 only changes which claimant is reported. The match itself is already right.
- **Pitfall: an asset under a non-user data root.** Pack metadata exists only under the user data
  root, so an asset installed elsewhere cannot be attributed even if it came from a pack. That is
  already true of `pack`. It becomes more visible with `license`, and the docstring should say so
  next to the `null` case.

## Affected specifications

- [responses.md](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact):
  the derived-fact section uses `pack` as its example. It gains license as the second derived field
  read from the same join, the agree-or-null rule for several claimants, and the stem fallback if
  the effort adopts it.
- [mpfb-integration.md](../../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides):
  pack metadata becomes a cache that two tools invalidate, and the list of caches should say which.
  If `_PACKS` is read, it is a new name read past `SERVICES`, recorded where
  [architecture.md](../../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish)
  lists them.
- [tool-interface.md](../../../specifications/tool-interface.md#the-glossary): `license`, `author`,
  `source`, `packs` and `known_licenses` are new names for arguments and answer keys. `source` is
  not in the glossary yet, but `asset_source` is an object property that several answers already
  report, and the two mean different things. If `source` reads as a short form of `asset_source`,
  use `source_url` instead.
- [architecture.md](../../../specifications/architecture.md#shared-modules-and-what-warrants-one): one
  more shared module, and the count in [CLAUDE.md](../../../CLAUDE.md) goes with it.

## Tests

- **Tool side** (`tests/test_list_assets.py`): `license` is optional non-empty text through
  `arguments.py`; it reaches the wire unchanged; no license vocabulary is checked here.
  `tests/test_vocabulary.py` covers the new argument automatically. Check that `license` has one
  JSON type everywhere it appears.
- **Bridge side**, against a real MPFB:
  - `bbb_shared/` tests the new module directly. Its fixture is a `packs/` directory that
    reproduces this install's shapes rather than a convenient one
    ([testing.md](../../../specifications/testing.md)): two packs claiming one asset (the
    `hats01`/`hats01_cc0` shape), an asset in an asset root, an asset no pack claims, a material
    in its asset's directory, a material in a directory of its own, an eye-style material keyed by
    file stem, and two claimants that disagree on license, which this install does not have and
    the rule must still handle.
  - `ccc_reading/list_assets_test.py`: the `license` filter, `counts_by_license`, `packs`, the
    filter-aware `pack`, and a matched pack with nothing installed.
    `ccc_reading/list_asset_materials_test.py`: attribution of both material placements, and
    `refresh` making a newly written pack file visible.
  - `ccc_reading/get_object_info_test.py` and `eee_composite/get_character_summary_test.py`:
    the equipped asset's license equals the catalogue's for the same file, by dispatching both.
- **Live check, in this subdir**, run once against the maintainer's full community install:
  - `mpfb_list_assets(asset_subdir="clothes", license="CC0")` returns 226, and the counts by
    license reproduce the 226 / 392 / 21 split above.
  - The number of `null` licenses per subdir with and without the stem fallback, and every asset
    the fallback would attribute differently from the directory. This is how requirement 2 is
    decided.
  - `pack="_cc0"` reports no row whose `pack` lacks `_cc0`.
  - The five hair materials the scene session used are attributed `CC0` to their
    `system_hair_materials0N` packs.
  - Response sizes for requirement 6, before and after.
- **Smoke**: no new tool, so no new smoke item. The existing `mpfb_list_assets` and
  `mpfb_list_asset_materials` items may add `counts_by_license` and `known_licenses` to the keys
  they expect.

## Decisions taken while scoping

- **The asset file's own `license` line is not a source.** 633 of 639 installed MHCLOs mention a
  license, but only in a free-text comment. The most common one, in 102 files, is
  `# license AGPL3 (see also ...external_tools_license.html)`, which is MakeClothes' boilerplate
  about the tool, not the asset. The rest are spelled at least seven ways (`CC BY 4.0`, `CC_by`,
  `CC-0`, ...). MHMATs carry a real `license` key in 22 of 721 garment materials, and one of those
  disagrees with its pack (`janexx_old_female_sweater/Worn_out_sweater.mhmat` says CC0, the pack
  says CC-BY). Also, MPFB's `MHMAT_KEYS` defaults `license` to `CC0` when the line is missing, so
  reading it through MPFB would report a missing license as CC0. That is the worst wrong answer
  this request could give. Pack metadata is the source; a file's own line is not consulted.
- **Not `mpfb_get_status`.** The NEXT_STEPS entry suggested that status should report a registered
  pack with no assets on disk. Working that out takes a scan of the asset library, and status is
  meant to be the cheap call that always answers. A directory check over this install suggests the
  case is common: about forty packs have entries that are not on disk as directories. Some of those
  are false alarms, though, because target and pose packs install files, not directories. The
  honest place for this fact is the catalogue that has just done the scan (requirement 10).
- **Not targets, yet.** `mpfb_list_targets` could carry license for its 211 claimed targets, but
  a target is a file in a category directory, so the directory join attributes nothing, and the
  stem join over target names has not been measured. It is left in NEXT_STEPS rather than built on
  an unmeasured convention.

## Decisions taken during the effort

- **The stem fallback is adopted.** The live check walked every `.mhclo`, `.mhmat` and `.proxy`
  file under nine subdirs' asset roots through the bridge's own module: with the fallback, 1,745
  of 1,809 files are attributed, without it 1,736. The nine it adds are exactly
  `eyes/materials/{blue,bluegreen,brown,brownlight,deepblue,green,grey,ice,lightblue}.mhmat`, and
  it changes the attribution of no file the directory join already attributed (it is only tried
  where the directory claims nothing). The condition it rests on is in `pack_attribution.py`'s
  docstring and in [responses.md](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact).
- **`source_url`, not `source`.** The glossary already has `asset_source`, a fragment; `source`
  read as its short form. The metadata's own key is `source`, and the module maps it.
- **Every field follows the agree-or-null rule, not only `license`.** `author` and `source_url`
  are reported when every claimant agrees on them too, and a field one claim leaves empty while
  another fills it counts as a disagreement. A disagreement is reported once per answer, in
  `attribution_conflicts` (each with `path` and every claim), not as a key on every row; it is
  `[]` on this install. `mpfb_list_asset_materials` carries it too.
- **The count of unlicensed assets is `license_unknown_count`, beside `counts_by_license`**,
  since `null` cannot be a JSON key and a sentinel such as `"none"` could collide with a license
  of that name. "Unknown" rather than "unlicensed", which would be a claim about the asset.
- **`matched_packs` is `null` without a `pack` filter**, and counts over the whole scan (after the
  subdir filter, before the name filter), so a registered pack with nothing on disk shows `0`
  whatever else was asked. On this install `accessories01_cc0` is the one `_cc0` pack at 0. The
  request suspected about forty packs with entries not on disk; a catalogue filter only reveals
  the ones a caller asks about, which is the decision taken while scoping.
- **`source_url` stays on every row.** A default page measured 102,241 B before and 127,898 B
  after (+25%), and a 1000-row page (938 rows on this install) 459,970 B before and 578,827 B after.
  `source_url` is 11,900 B of the default page's 25,657 B growth. It stays, because crediting a
  CC-BY asset needs it, and putting it behind an argument would cost a description line, a schema
  entry and a second call exactly when a caller has decided to use the asset. The call time did not
  move: 53 ms for the default page, 55 ms for 1,000 rows, one pack read for the whole call.
- **The summary carries `license` and `material_license` per asset, and `material_license` on the
  skin**, not a count by license. A dressed character with eight assets grew from 3,414 B to
  3,792 B; with the rollup at its caps (FR 034's ~105 B per modifier, ~115 B per asymmetry) that
  is about 7,340 B, under the 8 KB target. `author` and `packs` stay in `mpfb_get_object_info`.
- **The skin is attributed as well**, since `asset_info`'s `mhmat_path` is the skin on a basemesh
  and the alternative material on an asset, and one `material_license` covers both. A mesh asset
  wearing its own default material has `material_license: null`, as its `material_source` is.
- **`get_object_info` reads the pack metadata lazily**, on the first mesh asset or material it
  attributes, and once per call; a rig's answer reads nothing.
- **`mpfb_list_assets`' description and the two others grew 825 B**, and the description ceiling
  moved from 85,500 to 86,350, the schema ceiling from 17,100 to 17,200 (89 B for the argument).
  `tests/test_description_budget.py` says what each tool spent.
- **The upstream getter is proposed** as `AssetService.get_pack_metadata(pack_name)`, in
  `mpfb2/features/MCP_DISCOVERED_BUGS.md`, and the module already prefers it when present.
- **Found, and not this request's: a garment behind a sub-rig is missing from the summary.**
  `ponytail01` carries its own sub-rig, and MPFB's `find_related_objects()` does not walk past a
  `Subrig`, so it is in neither the basemesh's `related_objects` nor the summary's
  `equipped_assets`. The two agree, so "never a second opinion" holds, but a character checked
  against a brief through the summary would skip its hair. Recorded in
  [NEXT_STEPS.md](../../NEXT_STEPS.md#a-garment-behind-a-sub-rig-is-missing-from-the-family).

## Verification

Both halves of "verified" hold. The bridge suite has 24 new tests (611):
`bbb_shared/pack_attribution_test.py` (13: `_PACKS` read off MPFB's scan, two agreeing claimants,
both material placements, the stem fallback, the asset-root rule against a pack claiming `skins`,
an unclaimed asset, two disagreeing claimants, the public getter preferred, the names-only
fallback, the cache until invalidated, and the rule on a hand-built index), five in
`ccc_reading/list_assets_test.py`, three in `list_asset_materials_test.py`, one in
`get_object_info_test.py` and one in `eee_composite/get_character_summary_test.py`, each asserting
an equipped asset's attribution equal to its catalogue's by dispatching both.
`_fixtures.build_attributed_library()` writes a `packs/` tree in the install's shapes. The unit
suite has one new test (585). The smoke run is 44 of 44, its two catalogue items now expecting
`counts_by_license`, `known_licenses` and `attribution_conflicts`.

The live check, [live_check.py](live_check.py), ran on 2026-10-22 against a windowed Blender 5.1
with MPFB, the bridge (reloaded to pick the change up) and the community blender-mcp add-on, on
the maintainer's full community install, and passed all 30 checks: `license="CC0"` over `clothes`
is 226 and the counts are 226 / 392 / 21, case-insensitively; the stem fallback above;
`pack="_cc0"` reports no row whose `pack` lacks `_cc0` (20 of its rows would have, under the old
first-claimant rule) and shows `accessories01_cc0` at 0; the five hair materials - the four of the
line-up and `ricardo2020_long_01_bronze`, by four authors - are `CC0` in their
`system_hair_materials01`/`03` pack, in `mpfb_list_asset_materials` and, once applied, in
`mpfb_get_object_info`; nine equipped assets report their catalogue row's attribution; and the
summary's licenses are `mpfb_get_object_info`'s. The 21 garments with no license are listed in its
output; they are the community assets installed without a pack the scoping named.

## References

- [NEXT_STEPS.md: License in the catalogues](../../NEXT_STEPS.md#license-in-the-catalogues), the
  entry this request scopes, with both sessions' findings.
- `mpfb2/src/mpfb/services/assetservice.py`: `_PACKS`, `rescan_pack_metadata()`,
  `get_pack_names()`, `get_asset_names_in_pack()`, `update_all_asset_lists()` (which invalidates
  the pack cache) and `invalidate_alternative_materials_cache()` (which does not).
- `mpfb2/src/mpfb/entities/material/mhmatkeys.py`: the `license` key defaulting to `CC0`.
- [FR 005](../005-list-assets/README.md), which introduced `pack` and `pack_ambiguous`.
- [FR 018](../018-alternative-material-refresh/README.md), which introduced
  `mpfb_list_asset_materials`' `refresh`.
