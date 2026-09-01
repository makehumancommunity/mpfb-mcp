# Finding available rigs

**Status:** Done

`mpfb_get_object_info` can already say which rig an *existing* armature looks like — FR 003 reports
`rig_type` and `rig_definition_path` for every `Skeleton` and `Subrig` it finds. Nothing says which
rigs are *available to add*. An agent asked to "put a game engine rig on this character" has to
guess the string `HumanService.add_builtin_rig()` wants, and a user who dropped a MakeRig export
into their user data has no way to tell the agent it is there.

The two vocabularies are also not the same, which is the trap this request has to close.
`RigService.identify_rig()` — the source of FR 003's `rig_type` — returns values like
`rigify_generated.human` and `custom.my_rig`, and only some of those are strings that can be handed
back to a rig-adding function. `rigify_generated.*` never is: it names a rig Rigify built, not a
definition on disk. So "the name of the rig this object has" and "the name to use when adding a rig"
overlap without being interchangeable, and a tool listing available rigs has to be explicit about
which of the two it is reporting.

Everything needed is on disk and already reachable. Built-in rigs are `rig.<name>.json` files in
MPFB's own data directory, split into `standard/` and `rigify/`; custom rigs are found by
`AssetService.get_custom_rigs()`, which already scans the user data roots and parses each file.
Adding rigs is explicitly **out of scope** — that is `mpfb_add_rig`, a later effort.

## Goals

Primary: let a caller discover every rig that this Blender could add to a basemesh, and for each one
report the exact identifier a rig-adding tool will need, so no part of that string has to be guessed
or assembled by the caller.

Also: say what would happen if it *were* added. A rig with no weights file produces an unweighted
character, and MPFB resolves weights through a fallback table rather than by filename — so
`default_no_toes` borrows `default`'s weights and `rigify.human` borrows `rigify.human_toes`'s.
Reporting that up front is the difference between an agent choosing a rig and an agent choosing one
and being surprised.

Secondary: make a missing rig explainable. Rigify rigs are listed even when Rigify is disabled, and
`AssetService.get_custom_rigs()` silently skips user files it does not like — both must be visible
in the response rather than showing up as an unexplained absence.

## Functional requirements

One tool, `mpfb_list_rigs`. It takes no required arguments and always answers.

Arguments:

- `refresh` (optional bool, default `false`) — rescan the custom-rig cache before answering. See
  [Architecture](#architecture) for why this is opt-in rather than always-on.

No type/family filter. The full list is on the order of a dozen entries, and paying a filter
argument's ambiguity (see FR 003's `type_recognized` machinery) to shorten a list that short is a
bad trade.

`result` carries:

- `rigs`: one entry per available rig, each with:
  - `name` — the bare rig name (`"default_no_toes"`, `"human"`, `"my_rig"`).
  - `identifier` — **what to pass when adding this rig**, and the reason this tool exists.
    It is not always `name`: `"default_no_toes"` for a standard rig, `"rigify.human"` for a
    Rigify one, `"custom.my_rig"` for a custom one.
  - `family` — `"standard"`, `"rigify"` or `"custom"`.
  - `path` — absolute path of the rig definition JSON. Always absolute or `null`, per
    [architecture.md](../../../specifications/architecture.md#how-tools-report-the-asset-behind-an-object).
  - `label` / `description` — human-readable text from MPFB's own UI enums where there is any,
    `null` otherwise (custom rigs have none). This is what lets an agent map "the game engine rig"
    onto `game_engine` without a hardcoded table here.
  - `has_weights` (bool), `weights_path` (absolute or `null`) and `weights_from` — the rig name
    whose weights file would actually be used. `weights_from` differs from `name` for exactly the
    entries in MPFB's fallback table, and an entry where it differs is not broken; an entry where
    `has_weights` is `false` will produce a rig with no vertex weights.
  - `add_function` — `"add_builtin_rig"` or `"add_custom_rig"`. These are two different
    `HumanService` functions and they are not interchangeable: passing `"custom.my_rig"` to
    `add_builtin_rig()` makes it look for `rig.custom.my_rig.json` and fail. A later `mpfb_add_rig`
    needs to dispatch on this, and a caller reading the response should be able to see why.
  - `available` (bool) and `unavailable_reason` (string or `null`) — `false` for a Rigify rig when
    Rigify is not enabled, since `HumanService.add_builtin_rig()` raises rather than degrades in
    that case. Everything else is `true`.
- `count`: length of `rigs`.
- `rigify_available`: whether Rigify is enabled in this Blender. Reported once at the top level as
  well as per entry, because it is the single fact that explains a whole family being unusable.
- `rig_dirs`: the directories that were scanned — the bundled `standard/` and `rigify/` dirs and
  each user `rigs/` dir — so a user who expected their custom rig to appear can see where it was
  looked for.
- `unrecognized_custom_rig_files`: `.json` files sitting in a scanned user `rigs/` dir that did not
  become an entry. `AssetService.get_custom_rigs()` drops a file whose stem is not
  `[A-Za-z0-9_]+` or which has no `identifying_bones` key, and it does so silently. Without this
  field, "I put the file there and MPFB does not see it" is undiagnosable from the tool.
- `families`: the family vocabulary, echoed for the same reason `mpfb_list_objects` echoes
  `known_types`.
- `message`: one human-readable sentence.

**Relationship to `mpfb_get_object_info`'s `rig_type`.** The tool docstring must state that the two
vocabularies overlap but are not the same: `identify_rig()` can report `rigify_generated.*` and
`unknown`, neither of which appears here, because neither is something that can be added. A caller
comparing "what rig does this character have" against this list must expect misses that are not
errors.

## Non-functional requirements

- **Read-only.** A directory listing, a handful of `os.path.isfile()` calls, and at most two small
  JSON reads for the UI labels. Nothing is loaded into the scene and no object is touched.
- **Cheap.** Comparable to `mpfb_list_objects` — no asset-root `os.walk`, because rigs do not live
  in the asset subdirs that `AssetService.find_asset_absolute_path()` searches. The one cost is
  `get_custom_rigs()` parsing each custom rig JSON on a cold cache, which is bounded by the number
  of files in the user `rigs/` dirs.
- **An absent rig must be explainable.** `rigify_available`, `rig_dirs` and
  `unrecognized_custom_rig_files` all exist for this. It is the same quality attribute as FR 003's
  `type_recognized`: an agent that reads a short list as the whole truth will conclude rather than
  investigate.
- **Mostly stable, but not cacheable across sessions.** Built-in rigs change only when MPFB is
  upgraded; custom rigs change when the user drops in a file. Since the tool is cheap, callers
  should re-call rather than cache.

## Architecture

- One tool module `src/mpfbmcp/tools/list_rigs.py`, one payload
  `src/mpfbmcp/codegen/payloads/list_rigs.py`, one `register()` call in
  [`__init__.py`](../../../src/mpfbmcp/__init__.py) — the shape
  [architecture.md](../../../specifications/architecture.md#code-generation-layout) requires.
- **Use the raising bootstrap** (`bootstrap="raising"`). Without `LocationService` there is nothing
  to answer, and its `RuntimeError` already points at `mpfb_get_status`.
- Services needed — `LocationService`, `AssetService`, `RigService`, `SystemService` — are all in
  the `SERVICES` dict and resolve through the standard bootstrap.
- **Built-in rigs: scan the directory, do not hardcode the list.** `HumanService.add_builtin_rig()`
  builds its path as `LocationService.get_mpfb_data("rigs")` + `rigify` or `standard` +
  `rig.<name>.json`. Enumerate exactly those two directories for `rig.*.json` and strip the prefix
  and suffix to get `name`. The two dirs also contain `weights.*.json` files — filter on the
  `rig.` prefix or they will be listed as rigs.
- **Labels come from MPFB's UI property JSONs, and are optional decoration.**
  `<mpfb_root>/ui/rigging/standardrig/properties/standard_rig.json` and
  `<mpfb_root>/ui/rigging/rigifyrig/properties/rigify_rig.json` each hold an `items` list of
  `[identifier, label, description, index]`. Read them with `LocationService.get_mpfb_root(...)`,
  wrapped in try/except, and fall back to `label: null` — these are UI resource files, not an API,
  and their location may move. Do **not** import the UI modules to get at them: MPFB UI modules run
  scans at import time (see [FR 006](../006-list-targets/README.md), where that behavior is the
  central pitfall), and
  [architecture.md](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
  forbids it anyway. Note the enum is not the authority on what exists — the directory is; a rig
  file present with no enum entry is still addable and must be listed.
- **Pitfall — `get_mpfb_root()` returns a `pathlib.Path`, not a `str`,** despite its annotation
  (commit `631989c`; `get_mpfb_data()` is unaffected). Coerce with `str()` at the point any path
  enters the response, per FR 003's rule.
- **Custom rigs: use `AssetService.get_custom_rigs()`, not a hand-rolled scan.** It returns
  `[{"name", "path", "identifying_bones"}]` and already applies MPFB's own acceptance rules. Do not
  put `identifying_bones` in the response — it is a bone-name table used for identification, not
  something a caller acts on. Note it scans **only** `LocationService.get_user_data()` and
  `get_second_root()`, *not* the MakeHuman user data dir, so a custom rig placed there is invisible
  to MPFB; `rig_dirs` should therefore list what was actually scanned rather than every data root.
- **`refresh` and the custom-rig cache.** `get_custom_rigs()` caches in a module global
  (`_CUSTOM_RIGS_CACHE`) that survives until `invalidate_custom_rig_cache()` is called, so a rig
  installed after Blender started will not appear. `refresh=true` calls the invalidator first. It
  is opt-in because invalidating mutates MPFB global state that the custom-rig UI panel also reads;
  the default path reads the cache and mutates nothing.
- **`unrecognized_custom_rig_files` is a diff, not a second implementation of the rules.** List
  `*.json` in each scanned `rigs/` dir, subtract `<name>.json` for every entry `get_custom_rigs()`
  returned, and report the remainder. Re-deriving MPFB's acceptance rules here would drift from
  them; a set difference cannot.
- **Weights resolution must go through `RigService.get_rig_weight_fallbacks()`.** It returns the
  ordered list of rig names to try, and `add_builtin_rig()` takes the first whose
  `weights.<name>.json` exists in the same subdir (stripping the `rigify.` prefix as it goes).
  Mirror that loop rather than testing `weights.<name>.json` alone: `default_no_toes` and
  `rigify.human` both have no weights file of their own and would be reported as unweighted, which
  is wrong. Custom rigs are the exception — `add_custom_rig()` does not use the fallback table at
  all, it looks only for `weights.<short_name>.json` beside the rig file.
- **Do not parse the rig definition files.** A standard `rig.*.json` is a large flat bone table, and
  nothing in the response needs its contents. `is_subrig` (present in the Rigify definitions) is
  tempting and is deliberately left out; if a later effort wants it, it should be behind an
  argument.
- **`rigify_available` is `SystemService.check_for_rigify()`.** The same check
  `add_builtin_rig()` makes before raising `NotImplementedError`. Coerce to a real bool.
- Input validation, per
  [Validate before crossing the socket](../../../specifications/architecture.md#validate-before-crossing-the-socket):
  `refresh` must be a real bool, rejected locally otherwise. There is no vocabulary to validate.
- Response envelope unchanged: return `send_code(...)` as-is with `strict_json=True`.

## Affected specifications

- [vision.md](../../../specifications/vision.md#target-tool-catalog) — the "Introspection (read-only)"
  list has no rig-listing entry. Add `mpfb_list_rigs` and mark it **Implemented** when this lands.
  The `mpfb_add_rig` entry ("builtin or custom") should be amended to say it takes its `identifier`
  from this tool, the same way the modification tools take their subject from FR 003's pair.
- [architecture.md](../../../specifications/architecture.md) — one candidate addition, worth deciding
  at implementation time: **how tools name things that can be added.** FR 003 established how a
  tool names an *object*; this effort establishes the parallel convention for a *catalogue entry* —
  report the exact identifier the acting tool will need, never a display name or a filename the
  caller must transform, and say which function consumes it when there is more than one. FR 005 and
  FR 006 both follow the same rule with `fragment` and `shapekey_name`, which is what makes it a
  convention rather than a local choice. **Decided: added**, as
  [How tools name things that can be added](../../../specifications/architecture.md#how-tools-name-things-that-can-be-added),
  with two clauses this request did not anticipate — report what acting on an entry would do where
  the entry does not imply it (the weights fallback), and say explicitly where a catalogue
  vocabulary overlaps an identification vocabulary without matching it.

## Tests

Follow [tests/test_get_status.py](../../../tests/test_get_status.py)'s two-layer approach: argument
validation with `mpfbmcp.tools.list_rigs.send_code` mocked, then the generated source `exec()`d
against stubs.

The stubs belong in [tests/blender_stubs.py](../../../tests/blender_stubs.py) beside the existing
scene stubs, and must reproduce MPFB's actual behavior rather than convenient values — the same
discipline that module already applies:

- A fake `LocationService` returning a temp-dir tree with `rigs/standard/` and `rigs/rigify/`
  populated with the real filename pattern, including the **asymmetry that matters**: a
  `rig.default_no_toes.json` with no `weights.default_no_toes.json`, so the fallback path is
  actually exercised, and a stray `weights.*.json` with no matching `rig.*.json` to prove it is not
  listed as a rig.
- `get_mpfb_root()` returning a `pathlib.Path` rather than a `str`, so the coercion is tested.
- A fake `AssetService.get_custom_rigs()` plus a `rigs/` dir containing one accepted file, one with
  an invalid stem and one lacking `identifying_bones`, so `unrecognized_custom_rig_files` is tested
  against a real diff.
- `SystemService.check_for_rigify()` in both states, asserting Rigify rigs are still listed when it
  is `false` and carry `available: false` with a reason.
- The stub service module's name must not end in `"mpfb"` (the bootstrap's candidate scan would
  claim it) and its classes' `__module__` must be reassigned by hand — both mechanics inherited
  from `test_get_status.py`.

**Live verification against a running Blender is required** and cannot be substituted for. Unit
tests prove the payload's branching, not that MPFB's rig directory looks the way this request
assumes. Specifically: that every `identifier` reported is actually accepted by
`HumanService.add_builtin_rig()` / `add_custom_rig()`; that the UI property JSONs are where this
request says and parse into the labels shown; that `get_mpfb_root()` still misbehaves as described;
and that the custom-rig path works with a real MakeRig export. Record the outcome in a
`## Verification status

**Live-verified twice: 2026-08-29 originally, and re-verified 2026-09-01** by
[FR 013](../013-live-verification/README.md)'s session, against Blender 5.1.0 with MPFB 2.0.17
running `FROM_SOURCE` out of `../mpfb2`. The re-run was owed because
[FR 009](../009-add-rig/README.md) migrated `payloads/list_rigs.py` onto the shared
`codegen/shared/rig_lookup.py` fragment: the unit tests saw no behavior change, but the program
sent into Blender was a different program, so the 2026-08-29 verification no longer said anything
about the code that runs today.

It is now a script rather than a session:
[verification/check_fr004.py](../../../verification/check_fr004.py), re-runnable in one command.

The install was the same one: all 8 standard rigs, both Rigify rigs and three custom rigs
(`gurgel`, `meh`, `yada`) in `~/makehuman/mpfb/data/rigs`, each with a weights file beside it.
Every scene mutation was reverted — all twelve datablock collections plus `bpy.data.is_dirty`
compare **identical** before and after, and the `.blend` was never saved.

### What changed against the 2026-08-29 record

Nothing. Every item below produced the same answer as it did before the migration, which is the
whole point of re-running it. The three corrections that record carried
(`unrecognized_custom_rig_files` excluding the `weights.*` companions, `refresh` using
`get_custom_rigs(use_cache=False)`, `rig_dirs` entries being objects) still hold and are still
what the payload does.

### Checklist

- [x] Every rig on disk listed and nothing else — 13 entries: 8 standard, 2 rigify, 3 custom.
      `unrecognized_custom_rig_files` is `[]`, so the `weights.*.json` files sharing those
      directories are still correctly excluded rather than reported as malformed rigs.
- [x] Labels resolve from MPFB's real UI property JSONs — 10 of 13 labelled, the three custom
      ones `null`. MPFB's own rigify labels still read as swapped (`rigify.human` is labelled
      "Default (no toes)"); reported verbatim.
- [x] Weights fallbacks — `default_no_toes` reports `weights_from: "default"` and `rigify.human`
      reports `human_toes`, and both load real weights when added.
- [x] **Every one of the 13 `identifier`s was actually added**, each to its own scratch basemesh,
      through the `add_function` the entry named, and the weights that arrived matched the
      prediction in every case. Observed per rig (bones / vertex groups carrying a non-zero
      weight): `cmu_mb` 31/182, `default` 163/290, `default_no_toes` 137/264, `game_engine`
      53/203, `game_engine_with_breast` 55/205, `mixamo` 52/203, `mixamo_unity` 64/214,
      `openpose` 24/173, `rigify.human` 185/332, `rigify.human_toes` 213/360, `custom.gurgel`
      1/152, `custom.meh` 1/152, `custom.yada` 53/203. All 13 parented the basemesh and got an
      armature modifier targeting the new armature. All 13 were then deleted, leaving nothing.
- [x] The negative that justifies `add_function`, both ways.
      `add_builtin_rig("custom.gurgel")` raises `OSError: Could not find the rig file:
      .../rigs/standard/rig.custom.gurgel.json`; `add_custom_rig("default_no_toes")` raises
      `ValueError: Custom rig '_no_toes' not found in user data.` — an error naming a rig that
      never existed. Both still in the tool docstring.
- [x] `refresh=true` returns the same 13 identifiers in the same order, without disturbing the
      cache global.
- [x] `rigify_available` is `true` on this install; the `available: false` branch remains
      unit-tests-only.
- [x] `rig_dirs` names the two bundled dirs under the source-dist MPFB and the one user rigs dir,
      all three flagged as existing.
- [x] Whole response survives `strict_json` with real data.
- [x] Revert: all twelve datablock collections identical, `is_dirty` false before and after.

### What this re-run added to the record

**A rig added through `mpfb_add_rig` is byte-for-byte the rig MPFB's own "Add standard rig"
button produces.** That is FR 009's claim rather than this request's, but it was checked over
this same rig tree and it is what makes the catalogue's `add_function` prediction meaningful;
see [FR 009's verification status](../009-add-rig/README.md#verification-status).

## Verification status

**Implemented and live-verified** (2026-08-29), against Blender 5.1.0 with MPFB running
`FROM_SOURCE` out of `../mpfb2`, driven through the real tool callable over the blender_mcp
socket. The install held all 8 standard rigs, both Rigify rigs and three real custom rigs
(`gurgel`, `meh`, `yada`) in `~/makehuman/mpfb/data/rigs`, each with a weights file beside it.

Every scene mutation made for the test was reverted: a snapshot of object, mesh, armature, action
and collection counts, the scene's object names, the active object and the dirty flag compares
**identical** before and after. The `.blend` was never saved.

### What changed against this request

**`unrecognized_custom_rig_files` had to exclude the `weights.*.json` companions.** The set
difference as specified here reports them: `weights.gurgel.json` and friends are `.json` files in a
scanned user `rigs/` dir, and their stems fail `get_custom_rigs()`'s `^[A-Za-z0-9_]+$` test, so it
drops them exactly as it drops a genuinely malformed file. Confirmed live — the naive diff returns
`["weights.gurgel.json", "weights.meh.json", "weights.yada.json"]` on this install, and would do so
on every install that has a custom rig at all, burying the one file a user actually needs to see.
The payload therefore subtracts the `weights.` prefix that `add_custom_rig()` itself defines. The
remainder of the field is still a pure difference against what `get_custom_rigs()` accepted, not a
second implementation of its rules. A second, smaller version of the same mistake was caught in
unit tests before it ran: the difference must be taken over the *user* rigs dirs only, or every
`rig.*.json` MPFB ships is reported as an unrecognized custom rig.

**`refresh` uses `get_custom_rigs(use_cache=False)`, not `invalidate_custom_rig_cache()`.** The
keyword exists and is not mentioned above. It rescans and repopulates the same module global in one
call, where invalidating leaves it at `None` for the custom-rig UI panel that reads it. The
invalidator remains as a fallback if the keyword ever goes away.

**`rig_dirs` entries are objects, not strings** — `path`, `family` and `exists`. A directory that
does not exist is still reported, flagged. Listing only the dirs actually scanned would have left a
user whose `rigs/` dir is missing with no answer at all, which is the case the field exists for.

**The `get_mpfb_root()` pitfall is narrower than described.** It returns a `pathlib.Path` only when
called with no sub-path; with one, `os.path.join()` turns it back into a `str`. This payload always
passes a sub-path, so the coercion is belt-and-braces here rather than load-bearing. The stub
reproduces both forms.

### Checklist

- [x] Every rig on disk listed and nothing else — 13 entries: 8 standard, 2 rigify, 3 custom. The
      `weights.*.json` files sharing those directories are not listed as rigs.
- [x] Labels resolve from MPFB's real UI property JSONs, at the paths this request names, so the
      `label: null` fallback was *not* what was being observed. Note MPFB's own rigify labels read
      as swapped (`human_toes` is the one it calls "Default"); they are reported verbatim.
- [x] Weights fallbacks — `default_no_toes` reports `weights_from: "default"` and `rigify.human`
      reports `human_toes`, and both really do load weights when added. Testing
      `weights.<name>.json` alone would have called both unweighted.
- [x] **Every one of the 13 `identifier`s was actually added**, each to its own scratch basemesh,
      through the `add_function` the entry named. All 13 returned an armature, parented the
      basemesh, got an armature modifier targeting it, and came back with real non-zero vertex
      weights. All 13 were then deleted, leaving nothing behind.
- [x] The negative that justifies `add_function`, both ways. `add_builtin_rig("custom.gurgel")`
      raises `OSError: Could not find the rig file: .../rigs/standard/rig.custom.gurgel.json`. The
      reverse is worse and was not anticipated here: `add_custom_rig("default_no_toes")` strips the
      first seven characters unconditionally and reports `Custom rig '_no_toes' not found` — an
      error naming a rig that never existed. Both are now in the tool docstring.
- [x] `refresh=true` returns the same list, twice in a row, without disturbing the cache global.
- [x] `rigify_available` is `true` on this install, so the `available: false` branch was exercised
      only in unit tests; the flag itself is `SystemService.check_for_rigify()` coerced to a bool.
- [x] `rig_dirs` names the two bundled dirs under the source-dist MPFB and the one real user rigs
      dir, all three flagged as existing.
- [x] Whole response survives `strict_json` with real data.

## References

- MPFB `services/humanservice.py` — `add_builtin_rig()` (path assembly, Rigify guard, weights
  fallback loop) and `add_custom_rig()` (the separate custom path, and its non-fallback weights
  lookup).
- MPFB `services/rigservice.py` — `get_rig_weight_fallbacks()` (the fallback table) and
  `identify_rig()` (the *other* vocabulary, reported by FR 003).
- MPFB `services/assetservice.py` — `get_custom_rigs()`, its acceptance rules and its cache.
- MPFB `ui/rigging/` — `standardrig/properties/standard_rig.json`,
  `rigifyrig/properties/rigify_rig.json` (labels), `customrig/operators/addcustomrig.py` (where the
  `custom.` prefix is added).
- [FR 003](../003-object-finding/README.md) — `rig_type` / `rig_definition_path` in
  `asset_info`, the other half of the rig vocabulary.
