# Composing face units

**Status:** Accepted

> **The pivot has now reached part of what this request touches.**
> [FR 028](../done/028-pivot-to-specific-addon/README.md) decided that MPFB's Blender-side logic
> moves into a bridge add-on, [FR 029](../done/029-bridge-transport-and-skeleton/README.md) built
> the add-on out to where commands can be added to it,
> [FR 030](../done/030-backend-seam/README.md) built the seam on mpfb-mcp's side and migrated one
> tool across it, and [FR 031](../done/031-introspection-and-catalogues-migrated/README.md)
> migrated the other nine read-only ones. **Ten tools now have a bridge command beside their
> payload**, and fifteen — every mutating tool and the two documentation ones — do not. In the
> default configuration all twenty-five still take the generated path, so a payload, a shared
> fragment and `send_code()` all still mean what they mean here.
>
> **One tool this request touches has migrated**: `mpfb_get_target_stack`, which already sees the
> `!ex-` shape keys behind `include_expressions`, is now a bridge command as well as a payload. If
> this request changes what that tool *answers*, it must change both for as long as both exist —
> and the assertions about what it answers now belong in
> `bridge/test/tests/ooo_get_target_stack_test.py` rather than in the frozen payload layer (see
> [testing.md](../../specifications/testing.md#a-migrated-tool-is-tested-where-it-runs)). The two
> tools this request *adds* are mutating and are stage 3's territory, untouched so far.
>
> Two things to weigh either way. **Scheduling**: a tool that lands before
> [the migration](../NEXT_STEPS.md#a-larger-pivot-an-mpfb-specific-bridge-add-on) reaches its
> capability area is a tool the migration then has to carry — a reason to sequence, not a reason
> to wait. And **a new tool can now be written as a bridge command from the start**, registered in
> `backend.MIGRATED_COMMANDS`, rather than as a payload to be migrated later; FR 031 left nine
> worked examples of what such a command looks like, and
> [`bridge/test/tests/_fixtures.py`](../../bridge/test/tests/_fixtures.py) holds what its tests
> would need.


A character these twenty-five tools build has a face that cannot do anything. It has a phenotype, detail
morphs, a rig, garments and a skin — and one fixed, neutral expression, because the `!ex-` shape
keys that drive an ARKit face are the one part of MPFB's modelling surface no tool reaches.
`mpfb_get_target_stack` can already *see* them, behind an `include_expressions` flag, and nothing
can set them meaningfully.

This request scopes two tools over the **face-unit** half of
[`FaceService`](../../../mpfb2/src/mpfb/services/faceservice.py): one to read the 52 ARKit units a
character's face is currently holding, one to write them. It is the first effort to depend on an
**asset pack that may not be installed**, which is the durable part of it.

MPFB models expressions at two levels and this request is deliberately only the lower one. The
upper level — saved expression files and the persistent stack that applies them — is
[FR 027](../027-expression-library/README.md), which is written to follow this one and extends both
tools here. See [Why this is only half the subject](#why-this-is-only-half-the-subject).

Three further boundaries are drawn deliberately and are not up for rediscovery during the effort:

- **Authoring is out of scope.** No tool writes an expression file. See
  [A composed face is transient](#a-composed-face-is-transient), which states what an agent
  therefore cannot do, so the omission is not read later as an oversight.
- **Visemes and lip sync are out of scope.** See [Not visemes](#not-visemes).
- **`mpfb_set_targets` is left alone.** See [The overlap that stays](#the-overlap-that-stays).

## Goals

**Primary:** an agent can read what a character's face is doing and compose a new one from the 52
ARKit face units, in one call, without reading MPFB's source and without a silent partial success
when the asset pack behind those units is missing.

**Secondary:**

- Establish what a tool owes its caller when the capability it wraps **depends on an asset pack**.
  There has not been one, `mpfb_get_status` sets the idiom for absence being an answer, and three
  more queued efforts (expressions proper, poses, asset packs) will need the same shape.
- Give [FR 027](../027-expression-library/README.md) a face-unit layer to build on, so the library
  half is not obliged to reimplement reading and writing units on its way to the stack.
- Confirm and, if warranted, file the defects below in the shape
  [FR 019](../done/019-file-mpfb-defects/README.md) established.

## Functional requirements

### `mpfb_get_face_units` — what the face is doing now

1. Resolves the basemesh from any object in the character's family, exactly as the existing reading
   tools do, and answers `found: false` with a sentence rather than raising when it cannot.
2. Returns the live `!ex-` shape key values, from `FaceService.read_current_expression()`. That call
   always returns all 52 `ARKIT_FACEUNITS` keys, reporting a missing shape key as `0.0`, so a unit
   that has never been touched and a unit explicitly set to zero are indistinguishable in the
   answer — and the payload does not invent a distinction MPFB does not keep.
3. **Reports the vocabulary, without paying for it in every description.** `face_units` defaults to
   the non-zero units only; `include_zero` (a real `bool`, default `False`) returns all 52. The full
   list of names, grouped by `FACEUNIT_REGIONS`, is returned **always** as a bare `known_face_units`
   mapping of region to names — roughly 700 bytes, and it is how an agent learns what
   `mpfb_set_face_units` will accept, which is otherwise 52 names in a tool description that every
   MCP client downloads on every connection. `FACEUNIT_DESCRIPTIONS` is **not** returned; it is
   another 4 KB and its content is the public ARKit reference, which an agent already knows.
4. **Reports `faceunits01_installed`.** A neutral face and a face whose targets are not installed
   read identically — all 52 units at `0.0` — and only this flag separates them. See
   [The asset pack is a precondition, and MPFB reports its absence to nobody](#the-asset-pack-is-a-precondition-and-mpfb-reports-its-absence-to-nobody).
5. Takes `refresh` (a real `bool`, default `False`), which passes `force_recheck=True` to
   `is_faceunits01_installed()`. That probe caches in a module global `_FACEUNITS01_INSTALLED` which
   nothing invalidates, so a pack installed since Blender started reads as absent forever — the
   [MPFB caches what it scans](../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides)
   obligation, and the **third** instance of the pattern after `AssetService` and FR 025's
   `_EXISTING_PRESETS`. `refresh` means that one narrow thing here and the description says so.
6. **Reports which units are backed by a shape key that exists**, not merely their value. A unit at
   `0.0` because its shape key is absent behaves differently under
   [requirement 12](#mpfb_set_face_units--compose-a-face-directly) than one at `0.0` because it was
   zeroed, and an agent reading before writing should be able to predict which of its entries will
   touch the disk.

### `mpfb_set_face_units` — compose a face directly

7. **Batched**, in the [`mpfb_set_targets` idiom](../done/008-detail-targets/README.md): takes
   `face_units`, a list of `{face_unit, weight}` dicts. A round trip costs ~250 ms and a face unit
   costs microseconds; a face is normally composed from six or eight units at once, and eight round
   trips to build one smile is the wrong shape.
8. **Validates the shape here and the vocabulary in the payload**, per
   [validate before crossing the socket](../../specifications/tool-interface.md#validate-before-crossing-the-socket):
   each entry is a dict with exactly the keys `face_unit` (a non-empty string) and `weight` (a real
   number in 0.0-1.0 — a raw shape key value, which Blender clamps to that range, so this is
   `mpfb_set_targets`' `targets` range and not its `modifiers` range). An **unknown key** is
   rejected, because a misspelled `faceunit` is otherwise silent. Whether `browDownLeft` is a real
   face unit is answered by the payload against `ARKIT_FACEUNITS`.
9. **Resolves every entry before writing any**, as `mpfb_set_targets` does.
   `FaceService.set_expression` warns and skips an unknown name, so a list of eight units with one
   typo applies seven and reports success. The payload checks all names against `ARKIT_FACEUNITS`
   first and refuses the whole call, naming the bad ones and — per
   [how tools name things that can be added](../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added)
   — the closest legal names.
10. Takes `clear_first` (a real `bool`, default `False`). `set_expression` is **additive**: units not
    mentioned keep their current value. `clear_first` runs `clear_expression()` before writing,
    which is the difference between "smile a bit more" and "make this face and nothing else". The
    default is `False` because additive is what MPFB's own composer does.
11. **Refuses when the pack is absent**, per
    [preconditions are answers](../../specifications/mutating-tools.md#preconditions-are-answers).
    Without `faceunits01`, `set_expression` finds no target file for any unit, warns once per unit
    to a log nobody reads, and returns; every signal an MCP tool has says it worked and the face did
    not move.
12. **Reports what it actually wrote, and what it had to load to write it.** `set_expression` loads
    a target from disk on demand when the shape key does not yet exist, so a call can add up to 52
    shape keys to the basemesh and touch the filesystem. `loaded_from_disk` lists the units for
    which that happened, and `could_not_load` the units whose target file was missing anyway — the
    pack probe in requirement 11 tests one target, so a partially installed pack passes it and fails
    here. Note the asymmetry the payload must not paper over: a unit with weight `0.0` whose shape
    key is absent is **skipped entirely** rather than created, so "set everything to zero" and
    "clear" reach the same state by different routes and neither loads anything.
13. Takes `refit` (a real `bool`, default `True`, matching MPFB's composer panel `auto_refit`) and
    uses [`refit_blocker.py`](../../src/mpfbmcp/codegen/shared/refit_blocker.py) — see
    [This is the fifth refitting tool](#this-is-the-fifth-refitting-tool).
14. `performed` is stamped via [`performed.py`](../../src/mpfbmcp/codegen/shared/performed.py), like
    the other eleven mutating tools.
15. **Says that what it wrote is transient.** Once, in the tool description rather than in every
    response: a composed face is not saved by a preset and is destroyed by anything that rebuilds
    the expression stack. See [A composed face is transient](#a-composed-face-is-transient). When
    [FR 027](../027-expression-library/README.md) lands it replaces that static sentence with a
    computed one; until then the static sentence is the only warning an agent gets, and it is
    accurate.

## Non-functional requirements

16. **Absence must be a first-class answer, not an error and not a silent success.** This is the
    quality attribute the effort turns on. Two separate things can be missing — the pack, and an
    individual face-unit target — and MPFB's response to both is a log warning and a normal return.
    Both have to become something an agent can read.
17. **Robustness: a refusal is never a partial write.** The pack check and every face-unit name are
    settled before `set_expression` or `clear_expression` is called. MPFB's own
    `apply_expression_file` sets the precedent (it validates up-front "so we don't mutate the stack
    on a bad file"); this payload follows it and does not rely on it.
18. **Cost.** Both programs are small — one 4 KB chunk each, one timer tick. Inside Blender reading
    is instant, and a first `mpfb_set_face_units` on a fresh character may load up to 52 targets from
    disk, which the description should not flatten into "fast".
19. **Description budget.** Two tools, and requirement 3 deliberately moves the largest cost — the
    52 names — out of the descriptions and into a response. The ceiling change, if one is needed at
    all, is recorded with its reason beside it in
    [`test_description_budget.py`](../../tests/test_description_budget.py).

## Architecture

### Why this is only half the subject

MPFB composes an expression in two unrelated ways, and this request implements the lower one.

The **composer** (`ui/create_assets/makeexpression`) writes the 52 `!ex-` shape keys directly, via
`set_expression` / `clear_expression` / `read_current_expression`. That is what these two tools
wrap. Its load operator says in a comment that composer loads are transient and that "the
`mpfb_applied_expressions` stack and the expressions-library panel sliders are deliberately not
touched here."

The **library** (`ui/apply_assets/useexpression`) never writes a shape key from a user action at
all. It maintains a stack of `{asset, weight}` rows in a custom property on the basemesh, and every
change re-derives the whole face: aggregate the stack → `clear_expression` → `set_expression`. That
is [FR 027](../027-expression-library/README.md).

The split matters here for one reason: **the library destroys what the composer writes**, because
`clear_expression` runs unconditionally in the rebuild. That is true today, without FR 027 existing,
because [FR 025](../done/025-character-presets/README.md)'s `mpfb_create_human_from_preset` triggers the
same rebuild through `HumanService._apply_expressions_from_human_info`. So requirement 15 is not
anticipating a future tool; it is describing a hazard an agent can already reach.

**This request does not compute divergence** — whether the live face agrees with the stack that
claims to explain it — because doing so requires resolving and aggregating every expression file in
the stack, which is the whole of FR 027's machinery. FR 027 owns that computation and, as one of its
requirements, adds the computed answer to `mpfb_set_face_units`' response. The two efforts are
ordered but each is independently useful: this one is complete on its own, and if FR 027 landed
first it would find no face-unit tools to extend and would have to carry a reduced form of them.

### A composed face is transient

Authoring is out of scope by decision, and that decision has a consequence which requirement 15 must
state in the tool description rather than let an agent find:

**A composed face survives nothing.** It is not saved by
[FR 025](../done/025-character-presets/README.md)'s `mpfb_save_preset` —
`_populate_human_info_with_expression_info` serializes the applied-expressions stack, and a composed
state has no stack rows. It is not restored by `mpfb_create_human_from_preset`; that call rebuilds
from the stack and clears everything else. It lives in the `.blend` and nowhere else.

This is a real gap rather than a tidy boundary, and the honest place for it is a **new NEXT_STEPS
entry** — an `mpfb_save_expression` following FR 025's name-not-a-path convention and its
`overwrite: False` default, writing to `LocationService.get_user_data("expressions")` via
`FaceService.save_expression`, which already exists and already does the filtering and rounding.
That entry should be added when this request is accepted, cross-linked from here, so the gap is
queued rather than merely noted. It belongs after FR 027, since what it saves is read back through
the library.

### The asset pack is a precondition, and MPFB reports its absence to nobody

`faceunits01` is an optional asset pack. Without it every `!ex-` target file is missing, and MPFB's
behaviour in that state is the problem: `set_expression` logs `"Target file not found for face
unit, skipping"` per unit and returns normally. Nothing raises. Nothing in a return value differs.
MPFB's panels handle this by not drawing themselves — `poll()` returns `False`, the operators are
unreachable — which is a UI-layer guard an MCP tool inherits nothing from. This is the same class of
problem as `refit()` reporting through an `operator`
([mpfb-integration.md](../../specifications/mpfb-integration.md)), and it needs the same treatment:
detect the condition on this side and answer it.

`is_faceunits01_installed()` probes exactly one target (`cheekPuff`) through
`TargetService.target_full_path`. That is MPFB's own definition of installed and these tools use it
rather than inventing a second one — but it is a *probe*, not a verification, and a partially
installed pack passes it. Requirement 12's `could_not_load` is the counterpart: a per-unit
resolution failure at write time is its own reportable outcome, not an impossibility ruled out by
the probe.

**The generalisation is the durable part of this effort.** Probe MPFB's own installed-check; report
it in every response that depends on it; refuse rather than succeed emptily; and treat a per-item
resolution failure as separately reportable even when the probe passed. Poses, asset packs and the
extra-target packs all have the same shape, and the rule belongs in
[mpfb-integration.md](../../specifications/mpfb-integration.md) rather than in these two modules'
docstrings.

### This is the fifth refitting tool

Expression shape keys deform the face; garments, eyelashes, eyebrows and hair are fitted to the
basemesh and do not follow on their own. MPFB's composer panel carries an `auto_refit` toggle
defaulting to `True`, and **no `FaceService` function refits** — `apply_expression_file`'s docstring
says the refit "belongs to the operator layer, which knows the panel's `auto_refit` toggle". This
tool is that layer.

So `mpfb_set_face_units` joins `refit_human`, `set_macro_details`, `set_targets` and
`symmetrize_targets` as a consumer of
[`refit_blocker.py`](../../src/mpfbmcp/codegen/shared/refit_blocker.py), taking that fragment from
four payloads to five. Per that fragment's own docstring the **condition is shared and the wording
is not**: this payload keeps a `rig_refit_blocker()` of its own. It predicts a refit it is about to
attempt, so it is closer to `set_targets`' tense than to `refit_human`'s.

One fact from the viseme code makes this load-bearing rather than a convenience:
`interpolate_targets` matches shape keys by **bare** name against the three viseme/face-unit
vocabularies, and expression keys on the basemesh are `!ex-` prefixed — so it does not propagate
them and never has. Refit is the only propagation face units get.

### The overlap that stays

`mpfb_get_target_stack` already reports `!ex-` keys as `kind: "expression"` behind
`include_expressions`, and `mpfb_set_targets`' `targets` list addresses a raw `shapekey_name` — so
it can, in all likelihood, write `!ex-jawOpen` directly, bypassing the pack check and the
`ARKIT_FACEUNITS` vocabulary.

**By decision, `mpfb_set_targets` is not changed.** It is a live-verified tool, and refusing a name
it currently accepts is a behavioural change to something outside this effort's subject. The overlap
is handled in documentation instead: `mpfb_set_face_units`' description states that it is the tool
for face units, and `mpfb_get_face_units` is named as the way to see the result. The effort should
still **confirm** during its live run whether such a write actually lands, and record the answer —
if it turns out `mpfb_set_targets` cannot reach them (its resolution path may filter by category
membership, which no `!ex-` key has), the documentation says something simpler and truer.

### Not visemes

`FaceService` also carries `MICROSOFT_VISEMES`, `META_VISEMES`, `load_targets`,
`interpolate_targets` and `configure_lip_sync`. None is in scope, here or in FR 027. Visemes are
speech animation: a different vocabulary, a different asset pack (`visemes01` / `visemes02`), a
different propagation mechanism (`interpolate_targets` transfers shape keys to child meshes through
MHCLO vertex correspondence, which is not what a refit does), and in `configure_lip_sync`'s case a
dependency on a third-party addon maintained outside the MakeHuman ecosystem. They deserve their own
request; a NEXT_STEPS entry should be added saying so, cross-linked from here.

### Two tool modules, two payloads

`tools/get_face_units.py` and `tools/set_face_units.py`, each with the same-named payload and test
module — the ordinary shape. Two `register()` calls in
[`__init__.py`](../../src/mpfbmcp/__init__.py).

**No shared fragment.** Both payloads need the ARKit vocabulary and `FACEUNIT_REGIONS`, and both
should read them off `FaceService` through the handle the bootstrap already provides rather than
carry a copy. Reading MPFB's own table is strictly better than a fragment reproducing it — it cannot
drift — and it is why `asset_sections.py` exists in the form it does rather than as a literal.

Use `MPFB_BOOTSTRAP` (the raising one) for both. Neither tool is meaningful without a working MPFB.

### Defect candidates

Each to be confirmed against the running install before filing, per
[FR 019](../done/019-file-mpfb-defects/README.md), in
[`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../../mpfb2/features/MCP_DISCOVERED_BUGS.md):

- **`set_expression` cannot report failure.** It warns and skips on an unknown name and on a missing
  target file, and returns `None` either way. A caller cannot distinguish "applied eight units" from
  "applied none because the pack is absent". A return value — the units actually written — would
  cost nothing and would make the UI-layer `poll()` guard unnecessary for correctness. This is the
  substantive one, and requirements 9, 11 and 12 all exist to work around it.
- **`is_faceunits01_installed`'s cache is a session-long lie after an install.** `force_recheck`
  exists, but nothing in the install path appears to call it, so installing the pack from MPFB's own
  asset-pack UI would not make the expression panels appear until Blender restarts. Worth checking
  whether the install path already busts it somewhere; if it does not, this is small and real.

## Affected specifications

- [mpfb-integration.md](../../specifications/mpfb-integration.md) — the main change, and the durable
  one: a new standing rule for **a capability that depends on an asset pack**, in the shape stated
  under [the asset pack is a precondition](#the-asset-pack-is-a-precondition-and-mpfb-reports-its-absence-to-nobody).
  Plus one entry under
  [MPFB caches what it scans](../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides)
  for `_FACEUNITS01_INSTALLED`, the third instance of that pattern.
- [tool-interface.md](../../specifications/tool-interface.md) — the pattern of **returning a
  vocabulary in a response** instead of spending description bytes on it, which requirement 3 makes
  deliberate rather than incidental; and the description-budget ceiling if it moves.
- [mutating-tools.md](../../specifications/mutating-tools.md) — whether the refitting family growing
  to five changes anything stated there, and a tool whose effect is **known in advance to be
  transient** (requirement 15), which is new.
- [responses.md](../../specifications/responses.md) — `loaded_from_disk` and `could_not_load` report
  facts MPFB does not return; the
  [derived-fact convention](../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact)
  likely covers it, so check whether it needs extending or only an example.
- [vision.md](../../specifications/vision.md#target-tool-catalog) — *Introspection* 5 → 6,
  *Creation and modification* 14 → 15 (taking FR 025's landed count as the baseline).

## Tests

- **`tests/test_get_face_units.py`** — subject resolution by name and by active object; a character
  with no shape keys at all; one with a mix of present and absent units; `include_zero` both ways;
  `known_face_units` present regardless and covering all 52 names exactly once across the seven
  regions. The pack-absent path asserts `faceunits01_installed: false` reaches the response.
- **`tests/test_set_face_units.py`** — shape validation exhaustively on this side of the socket: a
  non-list, an entry that is not a dict, an unknown key, a missing key, a non-numeric weight, a
  weight outside 0.0-1.0, `clear_first` and `refit` as the string `"false"`. Then the payload against
  a stub character: an unknown face-unit name refusing the **whole** batch with nothing written;
  on-demand target loading reported; the zero-weight-absent-shape-key case that loads nothing; a
  partially installed pack producing `could_not_load` rather than a silent success; and `clear_first`
  both ways.
- **A read-after-write test running both payloads over one character**, asserting that what
  `mpfb_set_face_units` reported writing is what `mpfb_get_face_units` reports reading. Two payloads
  over one stub character is the shape `test_get_target_stack.py` and `test_symmetrize_targets.py`
  already use, and it is the only place the two tools' assumptions meet.
- **Stubs reproduce MPFB's skipping, not a convenient version of it.** Per
  [testing.md](../../specifications/testing.md), the stub `FaceService.set_expression` must warn and
  skip an unknown name and a missing target file, and return `None` — a stub that raised would make
  the suite pass without requirements 9 and 12 being implemented at all.
- **`tests/test_codegen.py`** — two payload entries.
- **`tests/test_verification_smoke.py` and `verification/smoke.py`** — two items. Note that the
  mutating one **requires the `faceunits01` pack**, which no smoke item has needed before; the item
  must degrade to asserting the honest pack-absent answer rather than failing, or
  [verification/README.md](../../verification/README.md) grows a prerequisite. The effort decides
  which, and the smoke run must stay one command.

**This effort needs a real Blender, and for more than one claim.** Three cannot be reached from this
side: that `set_expression` really does return normally with the pack absent (requirement 11 and the
first defect report both rest on it); that composing units and refitting really does carry eyelashes
and eyebrows with the face, which is the whole justification for requirement 13; and whether
`mpfb_set_targets` can in fact write an `!ex-` key. A script in this subdir does all three against a
character carrying a rig and a garment, prints what differed, and moves to `done/` with the request.
What stays behind is the two smoke items.

## References

- [`mpfb2/src/mpfb/services/faceservice.py`](../../../mpfb2/src/mpfb/services/faceservice.py) —
  `ARKIT_FACEUNITS`, `FACEUNIT_REGIONS`, `FACEUNIT_DESCRIPTIONS`, `set_expression`,
  `clear_expression`, `read_current_expression`, `is_faceunits01_installed`; and, for the excluded
  half, `MICROSOFT_VISEMES`, `META_VISEMES`, `load_targets`, `interpolate_targets`,
  `configure_lip_sync`.
- [`mpfb2/src/mpfb/services/targetservice.py`](../../../mpfb2/src/mpfb/services/targetservice.py) —
  `expression_name_to_shapekey_name` / `shapekey_name_to_expression_name`, the `!ex-` prefix, and
  `target_full_path`, which is what the pack probe rides on.
- MPFB's own composer UI, which these two tools collapse:
  [`makeexpressionpanel.py`](../../../mpfb2/src/mpfb/ui/create_assets/makeexpression/makeexpressionpanel.py)
  and its [`operators/`](../../../mpfb2/src/mpfb/ui/create_assets/makeexpression/operators) —
  `load.py`'s comment on why a composer load is transient is the clearest statement of the two-layer
  split in MPFB's source.
- [FR 027](../027-expression-library/README.md) — the other half: saved expression files, the
  applied-expressions stack, and the divergence computation that extends `mpfb_set_face_units`.
- [FR 025](../done/025-character-presets/README.md) — why a composed face does not round-trip through a
  preset, and the `mpfb_create_human_from_preset` path that destroys one today.
- [FR 008](../done/008-detail-targets/README.md) — where the batched-tool idiom and the
  resolve-everything-before-writing-anything rule were settled; requirements 7 and 9 reuse both.
- [FR 019](../done/019-file-mpfb-defects/README.md) — the established shape for a defect report, and
  the rule that a candidate is confirmed against a running install before it is filed.
- [NEXT_STEPS: Expressions](../NEXT_STEPS.md#expressions) — the entry this request and FR 027 split
  between them.
