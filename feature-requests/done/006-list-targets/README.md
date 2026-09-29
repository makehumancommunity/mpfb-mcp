# Getting available detail targets

**Status:** Done

Modeling a character in MPFB means setting *targets* — named morphs like `l-eye-bag-in` or
`nose-scale-depth-incr` — and the catalog planned for `mpfb_set_target_value` presupposes that the
caller knows which ones exist. It cannot: there are over a thousand bundled targets, they are
organized by a JSON index the caller has never seen, and a user's own installed targets are not in
that index at all.

The two sources are genuinely different in kind. `target.json`, in MPFB's system data directory, is
a curated index of the bundled modeling targets — 22 sections, each holding categories that pair
opposing targets (`decr`/`incr`) and mark which have separate left and right variants. It is ~140 KB
of JSON, far too much to return in a tool response, but exactly the sort of file an LLM can read for
itself. The user data directory, by contrast, has no index: it is scanned at runtime, and MPFB
synthesizes sections from the directory names it finds.

Two things make this more than a directory listing. First, MPFB's own scan happens at **module
import time** in a UI module, so its panels only see targets that existed when Blender started —
the install operator says as much to the user. A tool that scans on each call is therefore more
current than MPFB's own UI, which is worth having and worth stating. Second, the name that
identifies a target to `TargetService` is a *shapekey* name derived from the filename, not the
filename itself, and the derivation is not the identity function. Reporting the filename alone would
hand the caller something that does not work.

Macro details and phenotype are **out of scope** here, as they are driven by attributes on the
basemesh rather than by loading target files — that is `mpfb_set_macro_details`' territory.

## Goals

Primary: tell a caller where the bundled target index is, let it explore that index without having
to read the whole file, and list every target installed in the user's data directories — each with
the name that a later `mpfb_set_target_value` will actually accept.

Also: work when the client cannot read the Blender host's filesystem. Returning a path assumes the
MCP client and Blender share a disk, which `BLENDER_MCP_HOST` makes optional. The path stays — it is
the cheapest answer when co-located — but it is not the only way to get at the contents.

Secondary: make what is *not* in the index visible. Several directories of bundled targets have no
`target.json` section at all, so an agent that treats the index as the complete list of targets will
conclude that targets it could actually load do not exist.

## Functional requirements

One tool, `mpfb_list_targets`. Every argument is optional and it always answers.

Arguments:

- `section` (optional string) — a section name, either from `target.json` or one of the synthesized
  user-target sections. Omitted means the overview.
- `name_contains` (optional string) — case-insensitive substring filter on target names, applied to
  both the section listing and the user targets. Not asked for in
  [NEXT_STEPS.md](../../NEXT_STEPS.md), but suggested here as in scope: with over a thousand targets,
  "find me something to widen the nose" is the actual question, and the alternative is the caller
  pulling whole sections to grep them.
- `limit` (optional int, default `200`, max `1000`) and `offset` (optional int, default `0`) — the
  paging convention [FR 005](../005-list-assets/README.md) established, now standing as
  [How tools bound a large answer](../../../specifications/responses.md#how-tools-bound-a-large-answer).
  Follow it rather than re-deciding it: `total_count` counted before the cap, `truncated` always
  present, `offset`/`limit` echoed, and the listing sorted before it is paged.

`result` carries, always:

- `target_json_path`: the absolute path of `target.json`, and `target_json_exists`. The file is the
  bundled index of modeling targets; a caller with access to the same filesystem can parse it
  directly and skip the rest of this tool.
- `system_targets_dir`: the absolute path of MPFB's bundled `targets` directory.
- `sections`: one entry per section, each `{name, label, source, category_count, target_count}`.
  `source` is `"system"` for a `target.json` section and `"user"` for one synthesized from the user
  data directories. This is the overview an unfiltered call returns, and it is small — around thirty
  entries — so it is always present regardless of `section`.
- `unindexed_system_target_dirs`: directories under `system_targets_dir` holding target files but
  having no `target.json` section — today `asym` (62 targets) and `expression` (102), with
  `macrodetails` excluded as out of scope. Each with its name, absolute path and target count.
  Without this, `target.json` reads as the complete list of bundled targets and it is not.
- `user_target_dirs`: the absolute directories scanned for user targets, so a user whose target did
  not appear can see where it was looked for.
- `known_sections`, `section_recognized`, `requested_section`: the self-correction machinery
  `mpfb_list_objects` established. A misspelled section and an empty one must not be the same
  answer.
- `count`, `total_count`, `truncated`, `offset`, `limit`: paging over whichever list the call
  returned, following FR 005's convention. `truncated` must always be present, and an agent must
  check it before concluding it has seen everything.
- `message`: one human-readable sentence.

And, when `section` was given, the contents of that section:

- For a **system section**: `categories`, each `{name, label, has_left_and_right, targets,
  opposites}` straight from `target.json`. `opposites` is the `decr`/`incr` and left/right pairing
  MPFB's modeling sliders are built from, and is what tells a caller that setting one target
  meaningfully means clearing its opposite.
- For a **user section**: `targets`, the entries described below.

`user_targets`: every target file found in the user data directories, returned whether or not
`section` was given (filtered to the section when it was), each with:

- `name` — the filename with `.target` / `.target.gz` stripped.
- `shapekey_name` — **the name `TargetService` will use, and therefore the one a later
  `mpfb_set_target_value` must be given.** It is derived from the filename by
  `TargetService.filename_to_shapekey_name()`, which strips the extensions and then, for a name over
  60 characters, *encodes* it to fit Blender's shape key name limit. For most targets it equals
  `name`; for a long one it does not, and a caller using `name` there would silently address
  nothing.
- `path` — absolute path.
- `section` — the synthesized section it belongs to.
- `file_type` — `"target"` or `"target.gz"`.
- `listed_in_mpfb_ui` — whether MPFB's own modeling panels would show it. This is `false` for a
  gzipped target in a user `targets/<section>/` directory, because MPFB's scan of that location
  matches only `*.target`. Suggested as in scope rather than requested: without it, the tool
  reporting a target the user cannot find in Blender's UI looks like a bug in the tool.

**Not in scope.** Setting a target value (`mpfb_set_target_value`); macro details and phenotype,
which are basemesh attributes rather than target files (`mpfb_set_macro_details`); which targets are
currently *applied* to a character, which is `mpfb_get_human_summary`'s question; and returning
target file contents, which are vertex-offset data of no use to a caller.

## Non-functional requirements

- **Read-only and side-effect-free.** Directory scans and one JSON read. Unlike
  [FR 005](../005-list-assets/README.md), nothing here populates an MPFB cache or loads a Blender
  preview, so this tool is genuinely side-effect-free and needs no `refresh` argument.
- **Bounded response size.** ~140 KB of index, over a thousand bundled targets and an unbounded
  number of user ones. The overview is small by construction; everything else is capped and paged,
  with `truncated` always visible.
- **Correct over convenient in what it calls a target's name.** `shapekey_name` beside `name` is the
  point: a response that looks usable and is not is worse than one that admits a gap.
- **An incomplete picture must be visible as one.** `unindexed_system_target_dirs`,
  `user_target_dirs`, `listed_in_mpfb_ui` and `section_recognized` all exist for this. It is the
  same attribute FR 003 stated as "an empty answer must never be ambiguous".
- **More current than MPFB's own UI, deliberately.** Scanning per call rather than at import time
  means a target installed since Blender started is reported. That is correct, and it is also a
  discrepancy the user will see against the Blender UI, so the docstring must explain it.

## Architecture

- One tool module `src/mpfbmcp/tools/list_targets.py`, one payload
  `src/mpfbmcp/codegen/payloads/list_targets.py`, one `register()` call in
  [`__init__.py`](../../../src/mpfbmcp/__init__.py).
- **Use the raising bootstrap** (`bootstrap="raising"`). `LocationService`, `AssetService` and
  `TargetService` are all in the `SERVICES` dict.
- **Do not import `mpfb.ui.model._modelsubpanels`, even though it does exactly this scan.** Its
  scan runs at *module level*, so its results are a snapshot from when Blender started, and
  importing MPFB submodules is forbidden by
  [architecture.md](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
  precisely because of import-time side effects like this one. Reimplement the scan in the payload.
  The module remains the reference for *what* to scan — read it, follow it, do not import it.
- **The three user-target locations, and their asymmetry.** MPFB's panel builds its list from:
  1. `AssetService.get_asset_roots("custom")` and `get_asset_roots("targets/custom")`, matched for
     both `*.target` and `*.target.gz`, synthesized into a single `"custom"` section. Note
     `get_asset_roots()` spans *every* data root — the bundled MPFB data root included — not just
     the user one.
  2. `LocationService.get_user_data("targets")`, matched for `*.target` **only**, with each
     containing directory's basename becoming a section name. A `.target.gz` here is invisible to
     MPFB, which is what `listed_in_mpfb_ui` reports.

  Reproduce both, report both extensions from both, and flag the difference rather than papering
  over it or silently matching MPFB's narrower behavior. This asymmetry looks like an oversight in
  MPFB and is worth raising as an mpfb2 issue; until it is resolved, the tool describes what is on
  disk and says which part of it MPFB's UI will show.
- **`shapekey_name` must come from `TargetService.filename_to_shapekey_name()`,** called with the
  full path. Do not strip extensions by hand: the function strips `.gz` and `.target`/`.ptarget`
  case-insensitively, detects a macrodetail from the path, and applies
  `encode_shapekey_name()` above 60 characters. Reimplementing that here would drift from the
  function that decides what the shape key is actually called. Pass `macrodetail=False` explicitly
  — the default `None` triggers a path sniff for `/mpfb/data/targets/macrodetails/`, which is out of
  scope here anyway, and being explicit documents that choice.
- **`target.json` is read directly, not through a service.** There is no `TargetService` accessor
  for it; MPFB's own consumers build the path as
  `os.path.join(LocationService.get_mpfb_data("targets"), "target.json")` and `json.load()` it. Do
  the same, guarded — report `target_json_exists: false` and an explanatory `message` rather than
  raising, so a broken or missing install is an answer.
- **Pitfall — the file is `target.json`, singular.**
  [NEXT_STEPS.md](../../NEXT_STEPS.md) calls it `targets.json`; the file on disk and every reference in
  MPFB is `target.json`, inside the `targets/` directory. Easy to get wrong, and the failure mode is
  a tool that reports the index as missing on a perfectly good install.
- **Pitfall — `target.json` is not a complete list of the bundled targets.** It has 22 sections;
  the directory has entries with no section at all (`asym`, `expression`, and `macrodetails` which
  is out of scope), and one section (`measure`) with zero categories. `unindexed_system_target_dirs`
  exists because of this. Derive it by diffing the directory names under `system_targets_dir`
  against the index's section names — never by hardcoding `asym` and `expression`, which would drift
  the moment MPFB adds a directory.
- **Do not enumerate the bundled target *files*.** There are ~1258 of them and the index already
  names the ones a caller should be setting. For the unindexed directories report a count, not a
  listing; if a later effort needs to browse those, it belongs behind an explicit argument.
- **Ordering must be deterministic** — sort sections and targets by name before paging, for the same
  reason as FR 005: `rglob` order is filesystem-dependent, and unstable ordering makes `offset`
  paging skip and repeat entries.
- **Every path must be `str()`-coerced.** `AssetService.find_asset_files_matching_pattern()` returns
  `pathlib.Path` objects, and this payload handles them directly rather than through the cached
  asset items — so this is the most likely place in the three new tools for a `Path` to reach
  `strict_json` and take the response down.
- Input validation, per
  [Validate before crossing the socket](../../../specifications/tool-interface.md#validate-before-crossing-the-socket):
  reject a non-string or empty/whitespace-only `section` or `name_contains`, and a `limit`/`offset`
  that is not a non-negative int. Do **not** validate `section` against a vocabulary held here —
  the sections are partly synthesized from the user's own directories and cannot be known on this
  side of the socket at all; `section_recognized` and `known_sections` answer it from inside
  Blender.
- Response envelope unchanged: return `send_code(...)` as-is with `strict_json=True`.

## Affected specifications

- [vision.md](../../../specifications/vision.md#target-tool-catalog) — the "Introspection (read-only)"
  list has no target-listing entry. Add `mpfb_list_targets` and mark it **Implemented** when this
  lands. The `mpfb_set_target_value` entry ("arbitrary named target") should be amended to say the
  name it takes is the `shapekey_name` this tool reports, not a filename.
- [architecture.md](../../../specifications/architecture.md) — one convention to *follow* and two
  candidate additions.
  - **Already standing, since [FR 004](../004-list-rigs/README.md) landed:**
    [How tools name things that can be added](../../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added).
    `shapekey_name` is this tool's identifier under that convention, consumed by
    `mpfb_set_target_value`. Its last clause is the one to read closely here: a catalogue vocabulary
    and an identification vocabulary overlap without matching, which is exactly the relationship
    between a target's `shapekey_name` and its filename.
  - **The capped-and-paged response convention. Decided and already standing**, since
    [FR 005](../005-list-assets/README.md) landed first:
    [How tools bound a large answer](../../../specifications/responses.md#how-tools-bound-a-large-answer).
    Follow it; nothing about it needs restating here. Note its "a filtered call still reports what
    it filtered out of" clause, which for this tool means the per-section counts rather than
    FR 005's `counts_by_subdir`.
  - **Also standing since FR 005:**
    [How tools report a derived rather than recorded fact](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact).
    Worth reading against `shapekey_name`, which is derived from a filename by a convention rather
    than recorded anywhere, and against `listed_in_mpfb_ui`.
  - **Reading MPFB's data files directly.** This is the first tool to read a bundled *data* file
    (`target.json`) rather than call a service. The rule worth recording is the one this request
    follows: locate it through `LocationService`, never by assembling a path from the module
    location, guard the read, and treat a missing file as an answer rather than an error.
- A third, smaller point may belong in either document: **a tool may report a fact MPFB's own UI
  does not show** (a target installed since startup, or a gzipped one in a user targets directory).
  Where it does, the docstring must say so, because the user will otherwise read the discrepancy as
  the tool being wrong.

## Tests

Two-layer, as in [tests/test_get_status.py](../../../tests/test_get_status.py) and FR 003's tests:
argument validation with `mpfbmcp.tools.list_targets.send_code` mocked, then the generated source
`exec()`d against stubs in [tests/blender_stubs.py](../../../tests/blender_stubs.py).

The stubs need a temp-directory tree rather than only fake services, since most of this payload is
filesystem logic:

- A stub system targets dir with a small `target.json` (a section with a left/right category and its
  `opposites` table, plus an empty section standing in for `measure`), and target directories both
  with and without a matching section — so `unindexed_system_target_dirs` is tested against a real
  diff rather than a hardcoded pair.
- A missing `target.json`, asserting `target_json_exists: false` and a successful response.
- User target dirs covering all three locations, including **a `.target.gz` under
  `targets/<section>/`** so `listed_in_mpfb_ui: false` is pinned, and a target whose name exceeds 60
  characters so `shapekey_name` provably differs from `name`.
- A stub `TargetService.filename_to_shapekey_name()` reproducing MPFB's real behavior — the
  extension stripping *and* the encoding above the length threshold. Reproducing only the easy half
  would make the test pass while hiding the bug it exists to catch.
- A stub `AssetService.find_asset_files_matching_pattern()` returning `pathlib.Path` objects, since
  that is the real return type and the coercion needs to be under test.
- Paging and ordering, as in FR 005: deterministic order, no skips or repeats across pages,
  `total_count` describing the matched set rather than the page.
- The usual two mechanics: the stub service module's name must not end in `"mpfb"`, and the stub
  classes' `__module__` must be reassigned by hand.

**Live verification against a running Blender is required.** Specifically: that `target.json` is at
the path this request assumes and parses into the section shape described; that
`filename_to_shapekey_name()` returns names that `TargetService.set_target_value()` actually
accepts on a real basemesh — the single most important check here, since the whole value of
`shapekey_name` rests on it; that the user-directory scan finds a target installed through MPFB's
own install operator; and that the `.target.gz` asymmetry is real rather than an artifact of
reading the code. Record the outcome in a `## Verification status` section here, as FR 001–003 do.

## Verification status

**Implemented and live-verified** (2026-08-29), against the Blender instance running MPFB
`FROM_SOURCE` out of `../mpfb2`, driven through the real tool callable over the blender_mcp socket.
The install is a well-populated one for this purpose: 22 bundled sections plus 12 user target
directories holding 212 `.target` files, and 9 more in the user `custom` directory — 221 user
targets in all.

Every scene mutation made for the test was reverted. A scratch basemesh was created, four targets
loaded onto it and their values set, and then every datablock that had appeared was removed and the
file purged of orphans, compared against a snapshot taken first. All twelve collections — objects,
meshes, materials, images, node groups, armatures, actions, shape keys, collections, textures,
brushes, worlds — compare **identical** before and after, the active object was restored,
`bpy.data.is_dirty` was `false` throughout, and the `.blend` was never saved. Unlike
[FR 005](../005-list-assets/README.md) there is nothing that *could not* be reverted: this tool
populates no MPFB cache and loads no preview.

### What changed against this request

**A section can be both a system and a user section, and MPFB merges the two.** This request says
`source` is `"system"` for a `target.json` section and `"user"` for a synthesized one. On this
install **8 of 27 sections are both** — `arms`, `breast`, `cheek`, `chin`, `ears`, `hands`, `neck`,
`nose` all exist as bundled sections *and* as user target directories — and `_modelsubpanels.py`
appends the user categories into the existing section (`if dirn not in _sections`) rather than
making a second one. Two same-named entries would also make `section` ambiguous as an argument.
So the response reports **one entry per section name**, with `source` taking a third value
`"both"`, and carries `category_count` and `target_count` side by side. Asking for such a section
returns its bundled `categories` *and* the user targets in the directory of the same name, both
filtered by `name_contains`.

**`filename_to_shapekey_name()`'s `macrodetail` default is already `False`, not `None`.** This
request says to pass it explicitly because "the default `None` triggers a path sniff". The path
sniff exists, but only when `None` is passed deliberately; the declared default is `False`. Passing
it explicitly is still right — it documents that macro details are out of scope — and the argument
is **keyword-only**, which is the part that would actually break a payload passing it positionally.

**`measure` has no directory, and `_images` has no targets.** Both are real, and both are handled by
construction rather than by name: the unindexed diff counts target *files* under each directory, so
`_images` drops out at zero, and a section is never assumed to have a directory. Confirmed live —
`measure` comes back `source: "system"`, `category_count: 0`, and `_images` appears nowhere.

**`target.json`'s section labels are just the section names.** The request specifies `label` per
section, and it is reported, but on this install every bundled label is the lowercase section name
(`"arms"`, not `"Arms"`). The field is kept because it is MPFB's own, not because it adds anything
today. Category labels are likewise equal to category names.

**Nothing else in the request needed changing**, and no code changed as a result of the live pass.

### Checklist

- [x] `target_json_path` resolves to `<mpfb data>/targets/target.json` — singular — parses, and
      yields the section/category/`opposites` shape described. 22 bundled sections, of which
      `measure` has zero categories.
- [x] The section overview is 27 entries: 14 `"system"`, 5 `"user"` (`animal`, `cartoon`, `custom`,
      `faceunits`, `visemes`) and 8 `"both"`. Present regardless of the `section` argument.
- [x] `unindexed_system_target_dirs` is computed by diffing, and reports exactly `asym` (62) and
      `expression` (102). `macrodetails` (348) is excluded as out of scope and `_images` falls out
      on its zero count, neither by a hardcoded name.
- [x] **`shapekey_name` is a name `TargetService` actually accepts.** Three user targets from three
      different sections were loaded onto a scratch basemesh with `load_target()`: in each case the
      shape key created was **string-equal** to the `shapekey_name` this tool had reported, and
      `set_target_value()` / `get_target_value()` round-tripped `0.75` on it. A made-up name read
      back `0.0`, so the check is not vacuous.
- [x] **The >60-character encoding is real and `name` genuinely does not work.** A 76-character
      target loaded as `$yn-$fe-$av-$ca-$un-$pr-$wg-$hg-experiment`; setting that name read back
      `0.5`, while reading the same target by its *filename* read back `0.0` — silently, which is
      the failure `shapekey_name` exists to prevent. The same string comes back from
      `filename_to_shapekey_name()` given a path that does not exist, so the derivation needs no
      file. The basemesh's own macro-detail keys (`$md-$ca-$fe-$yn`) are encoded the same way.
- [x] Targets installed through MPFB's own install operator are found: all 9 files in
      `<user data>/custom` are listed in the synthesized `custom` section, and one of them was among
      the three loaded above.
- [x] **The `.target.gz` asymmetry was observed, not inferred.** A gzipped target was written into
      `<user data>/targets/animal/`; MPFB's own `*.target` scan of that tree did not see it (212
      files, unchanged) while the `*.target.gz` scan did, and the tool listed it with
      `listed_in_mpfb_ui: false`. It also loaded onto the basemesh and took a value, confirming the
      flag means "invisible in MPFB's panels", not "unusable". The file was then deleted and the
      directory listing compared identical.
- [x] The same probe confirms the **scan is more current than MPFB's UI**: the file appeared in the
      tool's answer without restarting Blender, which is precisely what MPFB's import-time snapshot
      cannot do.
- [x] A misspelled section (`armz` → `section_recognized: false`), an empty system section
      (`measure` → recognized, `categories: []`), and a user-only section (`visemes` → recognized,
      `categories: null`) are three distinguishable answers. `null` and `[]` are different claims and
      stay so.
- [x] Paging over the real 221-entry listing: three pages of 100 concatenate to exactly the unpaged
      listing, in the same order. An offset past the end answers rather than fails. `truncated` is
      true on a middle *and* a final page, matching FR 005's convention that it describes the
      matched set rather than the remainder.
- [x] Filters: `name_contains` case-insensitive over target names and `shapekey_name`, and over
      category names *and the target names inside a category* — `"nose-scale-depth-incr"` finds the
      category that sets it. Combines with `section` by AND, including across a merged section,
      where it narrows the categories and the user targets together.
- [x] Whole response survives `strict_json` with real data: 54 KB for all 221 entries, every `path`
      a `str` despite `find_asset_files_matching_pattern()` handing back `pathlib.Path`.
- [x] Cost: 4.2 s cold, 1.26 s warm, against FR 005's ~1.0 s socket round-trip baseline — so roughly
      0.3 s of actual work, and no cache or preview side effect to pay for once.

## References

- MPFB `services/targetservice.py` — `filename_to_shapekey_name()` and `encode_shapekey_name()`
  (the name derivation), `target_full_path()` (the same three user locations, searched in
  precedence order), `set_target_value()` / `get_target_value()` (what the reported name has to
  work with).
- MPFB `ui/model/_modelsubpanels.py` — the module-level scan this payload reimplements: how
  `target.json` is loaded, how the `custom` section is synthesized, and how `<user_data>/targets/`
  subdirectory names become sections. The `*.target` / `*.target.gz` asymmetry is visible here.
- MPFB `ui/apply_assets/assetlibrary/operators/installtarget.py` — installs into
  `LocationService.get_user_data("custom")`, and tells the user Blender must be restarted, which is
  the import-time snapshot this tool deliberately does not inherit.
- MPFB `data/targets/` — `target.json` and the sibling directories, including the unindexed `asym`
  and `expression` and the out-of-scope `macrodetails`.
- [extra-targets](https://github.com/makehumancommunity/extra-targets) — generates viseme and ARKit face-unit target
  packs intended to be installed into the user data directory, and is therefore the most likely
  real-world source of the user targets this tool lists.
