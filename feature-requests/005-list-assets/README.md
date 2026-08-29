# Finding and filtering assets in the asset subdirs

**Status:** Proposed

FR 003 answered "what is this object made from" — given a `Clothes` mesh, `mpfb_get_object_info`
reports the `.mhclo` it came from. The inverse question is still unanswerable: *what could I put on
this character?* An agent asked for "a fedora and some jeans" has no way to find out whether either
is installed, what the asset is called, or what string `HumanService.add_mhclo_asset()` will want.

MPFB organizes this as eleven asset *subdirs* — `clothes`, `hair`, `eyes`, `skins`, `poses` and so
on — each searched across every configured data root, each with its own file extension and its own
MakeHuman object type. `AssetService.ASSET_LIBRARY_SECTIONS` is the table that ties those three
together, and it is what MPFB's own asset-library panels are built from. Almost nothing needs
inventing; the work is choosing what to expose and surviving the scale.

Scale is the real problem. A user with the community asset packs installed has thousands of files
across those subdirs, so an unfiltered listing is not something an agent can afford to read. That
is why this tool is a *filtering* tool and not merely a listing one, and why its response is
capped with the truncation always visible.

The second problem is attribution. "Only assets from a certain asset pack" is a stated requirement,
but MPFB records no per-file link back to the pack that installed it. What it has is pack metadata
listing asset *names*, and a directory-naming convention that lets the two be matched — a
derivation this request has to make explicit rather than let a caller assume it is authoritative.

## Goals

Primary: let a caller find the assets installed in this Blender, narrowed by subdir, by a keyword in
the name and by asset pack, and for each one report the fragment that a later `mpfb_add_asset` /
`mpfb_set_skin` will need — so that finding an asset and using it are one step apart, not two.

Also: never let a filtered answer be mistaken for a complete one. A cap that silently drops entries,
or a pack name that matched nothing looking like a pack that is empty, both produce an agent that
reports the wrong thing confidently.

Secondary: make the shape of the library visible in one call. An unfiltered call should still be
useful — per-subdir counts and the installed pack names are a small answer to "what do I have",
from which the caller can pick a filter for the next call.

## Functional requirements

One tool, `mpfb_list_assets`. Every argument is optional and it always answers.

Arguments:

- `asset_subdir` (optional string) — one of MPFB's asset subdirs. Omitted means every subdir.
  Validated as a *shape* locally, never against a vocabulary kept here; see
  [Architecture](#architecture).
- `name_contains` (optional string) — case-insensitive substring match against the asset name and
  label. This is the "keyword in their name" requirement.
- `pack` (optional string) — matched against installed pack names with MPFB's own substring
  semantics, so `"hair03"` finds `hair03_ccby`.
- `limit` (optional int, default `200`, max `1000`) and `offset` (optional int, default `0`) —
  paging over the matched set.
- `refresh` (optional bool, default `false`) — rescan the library before answering. See
  [Architecture](#architecture) for what this costs.

Filters combine with AND.

`result` carries:

- `assets`: the matched entries for this page, each with:
  - `name` — the asset's filename without its extension (`"fedora"`). This is what pack metadata
    and the directory convention key on.
  - `label` — MPFB's own display label for it (`"Fedora"`), as shown in its asset panels.
  - `fragment` — `"<dirname>/<filename>"`, e.g. `"fedora/fedora.mhclo"`. **The value a later tool
    needs**, and the same form MPFB stores in an object's `asset_source` / `material_source` and
    accepts in `AssetService.find_asset_absolute_path()`. It is not a path; see the fragment rule in
    [architecture.md](../../specifications/architecture.md#how-tools-report-the-asset-behind-an-object).
  - `path` — the absolute path. Absolute or `null`, never a fragment.
  - `object_type` — the MakeHuman type from MPFB's own table (`"Hair"`, `"Clothes"`,
    `"Proxymeshes"`, and note `"Material"` for skins and `"Pose"` for poses, which are *not* object
    types any object in a scene carries).
  - `asset_subdir` — which subdir it was found in. Needed because `object_type` is not a
    round-trip: `skins` and `ink_layers` do not map onto a scene object type at all.
  - `file_type` — `"mhclo"`, `"mhmat"`, `"proxy"`, `"bvh"` or `"json"`. Reported because the
    extension does not follow the type: a `Proxymeshes` asset is a `.proxy` file, and FR 003
    already warns callers not to infer from the suffix.
  - `pack` — the pack this asset appears to come from, or `null`. **Derived, not recorded** — see
    [Architecture](#architecture). `null` means "no installed pack claims this name", which is the
    ordinary case for a hand-installed asset and is not a failure.
  - `pack_ambiguous` — `true` when more than one installed pack claims the name, in which case
    `pack` holds the first alphabetically. Rare, but silently picking one would make a wrong
    attribution indistinguishable from a right one.
  - `thumb_path` — absolute path of the asset's `.thumb` image, or `null`. Free, since MPFB has
    already resolved it, and it is what a client with filesystem access needs to show the user
    what an asset looks like.
- `count`: entries in `assets` (this page).
- `total_count`: entries matching the filters *before* `limit`/`offset`.
- `truncated`: whether `total_count` exceeds what this page returned. **An agent must check this
  before concluding it has seen the whole library**; the field exists so that a capped answer can
  never be read as a complete one.
- `offset` / `limit`: echoed, so the next page can be requested without the caller tracking state.
- `counts_by_subdir`: total assets found per subdir, ignoring `name_contains` and `pack` but
  ignoring the cap too. This is what makes an unfiltered call useful rather than merely truncated.
- `requested_subdir` / `subdir_recognized` / `known_subdirs`: the same self-correction machinery as
  `mpfb_list_objects`' `type_recognized` / `known_types`, and for the same reason — a misspelled
  subdir and an empty subdir are otherwise the same empty list.
- `requested_pack` / `pack_recognized` / `known_packs`: likewise. `known_packs` is the installed
  pack names, which is also a useful answer on its own.
- `asset_roots_searched`: the absolute directories actually scanned, per subdir. A root that is
  configured but does not contain the subdir is not searched, and that is the usual explanation for
  "I installed it and it is not here".
- `message`: one human-readable sentence.

**Not in scope.** Adding an asset to a human (`mpfb_add_asset`, `mpfb_set_skin`); alternative
materials for an asset (`AssetService.alternative_materials_for_asset()` is the natural follow-up
and is deliberately left out here, since it costs a second full scan for `*.mhmat` per asset);
returning thumbnail image data rather than a path; and anything about what is currently *on* a
character, which is FR 003's and `mpfb_get_human_summary`'s question.

## Non-functional requirements

- **A filtered or capped answer must never look complete.** `truncated`, `total_count`,
  `subdir_recognized` and `pack_recognized` all exist for this, and it is the single most important
  attribute here — the response is by design a subset, and an agent that treats a subset as the
  library will tell the user an asset does not exist when it does.
- **A derived value must be labelled as derived.** `pack` is a name match, not a record. The
  docstring must say so, and `pack_ambiguous` must exist, or a plausible-looking attribution will be
  taken as fact.
- **Bounded response size.** The cap is the mechanism; `counts_by_subdir` is what keeps an
  over-broad call informative instead of merely truncated.
- **Not read-only in the strictest sense, and that is a deliberate, documented cost.** Populating
  MPFB's asset cache loads a Blender preview image per asset that has a thumbnail, and mutates
  MPFB's module globals. See [Architecture](#architecture) — this is what MPFB's own panels do, so
  the cost is normally already paid by the user's session, but a first call against a large,
  never-opened library is slow and memory-hungry, and `refresh=true` pays it again.
- **Not cacheable across sessions.** A pack can be installed at any time. Within a session the
  answer is stable unless `refresh` is used, which is precisely the trade `refresh` exists to let
  the caller make.

## Architecture

- One tool module `src/mpfbmcp/tools/list_assets.py`, one payload
  `src/mpfbmcp/codegen/payloads/list_assets.py`, one `register()` call in
  [`__init__.py`](../../src/mpfbmcp/__init__.py).
- **Use the raising bootstrap** (`bootstrap="raising"`). `AssetService` and `LocationService` are
  both in the `SERVICES` dict.
- **The subdir vocabulary is `AssetService.ASSET_LIBRARY_SECTIONS`, read from MPFB.** It is a
  module-level list in `assetservice.py`, not a member of `AssetService` and not in `SERVICES`, so
  reach it via `sys.modules[AssetService.__module__]` — the pattern
  [architecture.md](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish)
  already sanctions. Unlike the constants FR 001 and FR 003 read, this one is **not**
  underscore-private, so it is a slightly safer bet; still read it with `getattr(..., default)` and
  fall back to a literal table rather than raising. Each entry gives `asset_subdir`, `asset_type`
  (the file extension) and `object_type` — which is exactly the three fields per asset that this
  tool reports, and the reason no mapping table is written here.
- **Use `AssetService.get_asset_list(asset_subdir, asset_type)`.** It returns MPFB's cached dict of
  items, each already carrying `full_path`, `basename`, `dirname`, `fragment`, `name_without_ext`,
  `label` and `thumb_path` — every field this tool needs, computed by MPFB rather than reassembled
  here. Do **not** put the item's `thumb` value in the response: it is a Blender preview object, not
  JSON.
- **Pitfall — the cached list is keyed by label, so same-named assets in different packs overwrite
  each other.** `update_asset_list()` ends with `asset_list[label] = item`, and `label` is derived
  only from the filename (lowercased, underscores to spaces, capitalized). Two packs each shipping a
  `fedora.mhclo` produce one entry, not two, and `total_count` will therefore under-report.
  This is a **known, accepted limitation of using MPFB's cache**, and the tool docstring must say
  so plainly rather than let the count read as authoritative. The right resolution is upstream —
  keying `_ASSETS` by `fragment` and keeping `label` as a field — and it should be raised as an
  mpfb2 issue rather than forked here; `AssetService.find_asset_files_matching_pattern()` is the
  fallback if it turns out to bite badly before that lands.
- **Pitfall — populating the cache loads Blender previews.** `update_asset_list()` calls
  `bpy.utils.previews.new()` and loads an image for every asset with a `.thumb` beside it. That is
  a genuine side effect in the user's Blender and, on a large library, a slow and memory-hungry one.
  It is the price of the caching decision; it is also exactly what MPFB's asset panels do, so a
  session where the user has opened those panels has already paid it. Do not attempt to suppress it
  — reaching around `update_asset_list()` to avoid the previews means reimplementing it here.
- **`refresh` invalidates, it does not bypass.** `refresh=true` calls
  `AssetService.update_all_asset_lists()`, which rescans every subdir and also invalidates the
  alternative-material and pack-metadata caches. That is the whole library, not the requested
  subdir, and on a large install it is the most expensive thing this tool can do — so it is opt-in,
  and the docstring should say what it costs. The default path calls `get_asset_list()`, which
  scans only a subdir that has not been scanned yet.
- **Pack attribution is a name match against pack metadata, and its derivation must be exact.**
  `AssetService.get_pack_names()` lists installed packs (JSON files in
  `LocationService.get_user_data("packs")`), and `get_asset_names_in_pack(name)` lists the asset
  names in one. Those names are the *directory* names a pack installs under — an asset ships as
  `<root>/<subdir>/<name>/<name>.<ext>` — so the join is:
  **the basename of an asset's containing directory, matched against the union of pack asset
  names.** Build the reverse index (name → packs) once per call from `get_pack_names()` plus
  `get_asset_names_in_pack()`, then look each asset up in it; do not call per asset.
  Three consequences the docstring must carry: an asset installed by hand matches nothing and gets
  `pack: null`; a name claimed by two packs gets `pack_ambiguous: true`; and pack metadata lives
  only under the *user* data root, so an asset under the second root or the MakeHuman user data dir
  cannot be attributed even when it did come from a pack.
- **Filtering by pack must intersect with files actually found, not report from metadata.** Pack
  metadata lists what the pack contains, including assets the user later deleted. Filter the scanned
  list by the derived `pack` field; never build the response from `get_asset_names_in_pack()`
  directly, or the tool will report assets that are not installed.
- **Pack name matching uses MPFB's substring semantics.** `get_asset_names_in_pack_pattern()` does
  `pattern.lower() in name.lower()` over pack names, so mirror that for the `pack` filter rather
  than requiring exact equality — and set `pack_recognized` from whether any installed pack name
  contains the pattern, so a typo is distinguishable from an empty pack.
- **`asset_roots_searched` is `AssetService.get_asset_roots(subdir)`,** which is the data roots that
  actually contain that subdir — not `get_available_data_roots()`. The difference is the diagnostic.
- **Ordering must be deterministic.** MPFB's cached dict is insertion-ordered from an `rglob`, whose
  order is filesystem-dependent. Sort the matched list (by subdir, then name) before applying
  `offset`/`limit`, or paging will silently skip and repeat entries between calls.
- **Every value must survive `strict_json`.** The cached items' `full_path` and `dirname` are `str`,
  but `AssetService`'s `list_*_assets()` helpers return `pathlib.Path` and
  `LocationService.get_mpfb_root()` has been caught returning one despite its annotation. Coerce
  every path with `str()` where it enters the response.
- Input validation, per
  [Validate before crossing the socket](../../specifications/architecture.md#validate-before-crossing-the-socket):
  reject a non-string or empty/whitespace-only `asset_subdir`, `name_contains` or `pack`; reject a
  `limit`/`offset` that is not a non-negative int, and a `limit` above the maximum. Do **not**
  validate `asset_subdir` or `pack` against a vocabulary held here — `subdir_recognized` and
  `pack_recognized` answer that authoritatively from inside Blender.
- Response envelope unchanged: return `send_code(...)` as-is with `strict_json=True`.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog) — the catalog's `mpfb_list_assets`
  entry currently reads "clothes / skins / proxies / poses, optionally filtered by pack". Replace it
  with what this actually is: every subdir in MPFB's own section table, filtered by subdir, name and
  pack, capped and paged, reporting the fragment later tools need. Mark it **Implemented** when this
  lands, and note that `mpfb_add_asset` / `mpfb_set_skin` take their `fragment` from it.
- [architecture.md](../../specifications/architecture.md) — one convention to *follow* and two
  candidate additions.
  - **Already standing, since [FR 004](../done/004-list-rigs/README.md) landed:**
    [How tools name things that can be added](../../specifications/architecture.md#how-tools-name-things-that-can-be-added).
    `fragment` is this tool's identifier under that convention, and `mpfb_add_asset` /
    `mpfb_set_skin` are the functions that consume it. Follow it rather than restate it; the only
    thing left to check is its "say which function consumes it when there is more than one" clause,
    which applies here — a skin and an mhclo asset are applied by different functions.
  - **How tools bound a large answer.** This is the first tool whose natural answer does not fit:
    the cap plus `total_count` plus a `truncated` flag that is always present, and the rule that a
    filtered call still reports the totals it filtered out of. `mpfb_list_targets`
    ([FR 006](../006-list-targets/README.md)) needs the same convention, which is what makes it
    spec material rather than a local choice.
  - **How tools report a derived rather than recorded fact.** `pack` is inferred from a naming
    convention. FR 003 already drew the line between *identified* and *recorded* values for
    `rig_type` and `material_type`; this adds a third category, and the same rule applies — say in
    the docstring which it is, and give the caller a way to see when the derivation is unsafe.
- The [fragment/path convention](../../specifications/architecture.md#how-tools-report-the-asset-behind-an-object)
  needs no change: this effort is its first use in the *forward* direction (naming an asset to be
  applied) rather than the backward one (naming what an object was made from), which is a
  confirmation of the convention rather than a modification.

## Tests

Two-layer, as [tests/test_get_status.py](../../tests/test_get_status.py) and FR 003's tests:
argument validation with `mpfbmcp.tools.list_assets.send_code` mocked, then the generated source
`exec()`d against stubs in [tests/blender_stubs.py](../../tests/blender_stubs.py).

The stub `AssetService` must reproduce MPFB's real behavior, including the parts that are
inconvenient — that discipline is why the existing stubs exist. One specific thing to check, from
[FR 004](../done/004-list-rigs/README.md#verification-status): a scanned directory holds more than the
files a listing wants. FR 004's diff of "files MPFB refused" reported the `weights.*.json` companion
of every custom rig until it excluded them, and that was only visible against a *real* install. Any
listing here that enumerates a directory rather than asking a service should be checked against real
asset roots, where thumbnails, materials and other companions sit beside the asset file.

- `get_asset_list()` returning items with MPFB's exact key set, keyed by label, **including a
  label collision** so the under-reporting limitation is pinned by a test rather than only
  described in prose.
- `ASSET_LIBRARY_SECTIONS` as a module-level list on the stub module, reached the same way the
  payload reaches it, plus a test that the payload falls back gracefully when it is absent.
- `get_asset_roots()` returning fewer roots than `get_available_data_roots()`, so
  `asset_roots_searched` is tested against the right one.
- Pack metadata with: an asset in one pack, an asset claimed by two packs, and an asset in no pack —
  covering `pack`, `pack_ambiguous` and `pack: null`; plus a pack listing an asset that is not on
  disk, proving the intersection rule.
- Paging: assert deterministic ordering, that `offset`/`limit` do not skip or repeat across two
  calls, and that `total_count` and `truncated` describe the matched set rather than the page.
- A `Proxymeshes` entry with a `.proxy` extension and a skin entry with `object_type: "Material"`,
  so the two non-obvious rows of MPFB's table are covered.
- The usual two mechanics: the stub service module's name must not end in `"mpfb"`, and the stub
  classes' `__module__` must be reassigned by hand.

**Live verification against a running Blender is required.** Unit tests cannot show that a real
asset library behaves as assumed. Specifically: that the directory-name-to-pack-name join actually
holds for the published community packs; that `get_asset_list()`'s items carry the keys this
request depends on for every one of the eleven subdirs (the non-mhclo ones are the risk); how long
a cold `get_asset_list()` and a `refresh=true` take on a full library, and how badly the preview
loading bites; and whether the label collision is common enough in practice to force the fallback.
Record the outcome in a `## Verification status` section here, as FR 001–003 do.

## References

- MPFB `services/assetservice.py` — `ASSET_LIBRARY_SECTIONS` (the subdir/extension/type table),
  `get_asset_list()` / `update_asset_list()` (the cache, its item shape, its label keying and its
  preview loading), `get_asset_roots()`, `find_asset_absolute_path()` (what a fragment is resolved
  by), `get_pack_names()` / `get_asset_names_in_pack()` / `get_asset_names_in_pack_pattern()`.
- [../../../asset_packs_staging](../../../asset_packs_staging) — `src/staging/assetpack.py` builds
  the pack metadata that lands in `<user_data>/packs/`, keyed by each asset's `final_name`, which is
  also the directory it is installed under. This is the source of the naming convention the pack
  attribution relies on, and the place to check if that attribution turns out to be wrong.
- [FR 003](../done/003-object-finding/README.md) — `asset_info`, the fragment/path pairing, and the
  warning against inferring an asset's kind from its file extension.
