# `mpfb_get_character_summary`: one character, one answer

**Status:** Done

Before an agent changes a character it has to know what the character already is: its
phenotype, whether it has a rig and which kind, what it is wearing, what skin it has, which
detail morphs are on it, and what its face is doing. Today that is **five or six calls** —
`mpfb_get_macro_details`, `mpfb_get_object_info` on the basemesh, `mpfb_get_target_stack`,
`mpfb_get_face_units`, `mpfb_get_expression` ([FR 027](../027-expression-library/README.md)),
and usually `mpfb_list_objects` first to find a name. That is five or six
round trips at roughly 250 ms each, and five or six answers written for different questions, most of
whose bytes the agent did not need.
[vision.md](../../../specifications/vision.md#target-tool-catalog) names the missing tool and sets one
condition on it: its macro half must come from **the same read `mpfb_get_macro_details` uses**, not
a second implementation that can diverge.

This request takes that condition as the design rather than a detail of it, and applies it to
**every** section. A summary is only worth having if it is **never a second opinion**: an agent that
reads "no rig" here and "rig `default`" from `mpfb_get_object_info` has been handed a contradiction
it cannot resolve, and will act on whichever it read last. So each section of the summary is
produced by the implementation its detailed tool already uses, which in the bridge means lifting that
implementation out of the detailed command into
[bridge/mpfb_bridge/shared/](../../../bridge/mpfb_bridge/shared). That is the
[duplication that must not drift](../../../specifications/architecture.md#shared-modules-and-what-warrants-one)
case, three or four times over.

It follows from this that **the summary reports no fact a detailed tool does not.** It selects and
it counts; it does not derive. Cross-section conclusions ("the rig cannot be refitted *and* there
are garments on it") were considered and left out; see
[Decisions taken while scoping](#decisions-taken-while-scoping).

It is read-only and changes nothing: no recalculation, no refit, no selection change, and no cache
populated that a detailed tool would not also populate.

**Ordered after FR 027, which has landed.** Its `face` section carries FR 027's expression stack,
read through `stack_rows()` and `divergence()` in
[`shared/expression_divergence.py`](../../../bridge/mpfb_bridge/shared/expression_divergence.py), which
FR 027 put there with this request in mind.

## Goals

**Primary:** one call tells an agent enough about one character to plan a modification — phenotype,
rig, equipped assets, skin, detail morphs and face — in an answer small enough to read every time,
and never in disagreement with the detailed tool for any of those facts.

**Secondary:**

- Make the agreement **structural rather than tested-for**: each fact the summary shares with a
  detailed tool comes from one implementation, so the two cannot drift even when nobody remembers the
  summary exists.
- Leave every existing tool's answer **byte-for-byte unchanged**. The extraction into `shared/` is a
  refactor of three or four commands, and their bridge tests are what prove it was one.

## Functional requirements

### Subject

1. Takes one optional argument, `name`: **any object in the character's family**, `null` meaning
   the active object — resolved exactly as `mpfb_get_macro_details` resolves it, and reporting
   `subject_name`, `subject_resolved_by` and `basemesh_name` the same way.
2. Failing to resolve a basemesh is a **successful answer** with `found: false` and a sentence, per
   [preconditions are answers](../../../specifications/mutating-tools.md#preconditions-are-answers)
   and the introspection promise in [vision.md](../../../specifications/vision.md#target-tool-catalog).
   Every section key is present on a miss, `null` or empty, so a caller does not branch on key
   presence.
3. Every object named anywhere in the answer carries `in_current_scene`, per
   [how a tool addresses an object](../../../specifications/tool-interface.md#how-a-tool-addresses-an-object).

### Sections

Each section carries a **subset** of the named detailed tool's fields, under the **same names**, so a
caller that learned a field from one tool can read it in the other.

4. **`phenotype`** — from `mpfb_get_macro_details`: the eleven `macro_details`, `race_sum`,
   `race_normalized`, and a `macro_drift` boolean for "the macro shape keys on the mesh are not the
   ones these values imply". The two shape-key lists that establish drift are **not** repeated.

   `macro_drift` is the one field that is not already a field of the detailed tool, which reports
   the two lists and leaves the comparison to the caller. It qualifies because the comparison moves
   into the shared module and `mpfb_get_macro_details` gains the same boolean — so the detailed tool
   still reports everything the summary does.
5. **`rig`** — from `mpfb_get_object_info`'s skeleton `asset_info` and related-object walk: `null`
   when there is none; otherwise the rig object's `name`, `rig_type`, `rig_definition_path` and
   `rigify_role` (`metarig`, `generated_rig` or `null`).
6. **`assets`** — from `mpfb_get_object_info`'s related-object walk: one row per equipped mesh asset
   (clothes, eyes, eyebrows, eyelashes, hair, teeth, tongue, proxy), with `name`, `object_type`,
   `asset_source`, `material_type`, `material_source` and `in_current_scene`. Ordered by
   `object_type`, then name. **Not capped**: a character wears tens of things, not thousands, and
   the docstring says so, so a caller does not look for `truncated`.
7. **`skin`** — from `mpfb_get_object_info`'s basemesh `asset_info`: `material_type` (one of the
   five `mpfb_set_skin` accepts, or MPFB's name for whatever else is there), `material_source` and
   `mhmat_path`.
8. **`targets`** — from `mpfb_get_target_stack` with its default arguments: the **`modifiers`
   rollup** (non-zero categories only, as that tool reports it), `asymmetries`, `counts_by_kind`, and
   `total_count`. **Not** the per-shape-key `targets` list, which is the paged half of that tool and
   the half that does not fit. Macro and expression shape keys are excluded exactly as that tool's
   defaults exclude them.
9. **`face`** — two halves, each from its own detailed tool:
   - from `mpfb_get_face_units`: `faceunits01_installed`, and the **non-zero** face units only, as
     `{face_unit, weight}`. Not `known_face_units`: the vocabulary is 52 names the summary has no
     reason to pay for on every call.
   - from FR 027's `mpfb_get_expression`: `applied_expressions` (`{fragment, weight, resolved}` per
     stack row), `matches_stack`, and `unexplained_face_units`. The last is the one fact in this
     answer that nothing in MPFB's own interface shows, and it is exactly what the next
     `mpfb_apply_expressions` call would destroy — which is why it earns a place in a summary read
     before modifying.

### What it deliberately does not do

10. **No filtering, paging or `include_*` switches.** The summary is fixed-shape; a caller that
    wants a slice calls the detailed tool. An `include` argument would turn one question into
    dozens and make the description budget pay for each of them.
11. **No `refresh`.** The only cache it touches is the `faceunits01` probe, and a caller who
    suspects that one calls `mpfb_get_face_units` with `refresh: true`.
12. **No scene-wide mode.** `name: null` means the active object, as everywhere else in this
    package; a summary of every character in the scene is `mpfb_list_objects` followed by one call
    each.
13. **No fact no detailed tool reports.** No cross-section findings, no "is this garment rigged",
    no refit-blocked prediction, no map from section to tool in the response. See
    [Decisions taken while scoping](#decisions-taken-while-scoping).

## Non-functional requirements

- **Bounded size.** The answer for a fully dressed, rigged, heavily morphed character with an
  expression applied must fit comfortably in an agent's working context: the target is **under
  8 KB** of JSON, measured on the live check's worst-case character and recorded in HISTORY. If the
  `targets` rollup exceeds that on a real character, cap it with `total_count`/`truncated` per
  [how tools bound a large answer](../../../specifications/responses.md#how-tools-bound-a-large-answer)
  rather than dropping entries silently.
- **One round trip, and not much slower than the slowest detailed tool.** The point is latency. A
  summary that costs as much as the calls it replaces has not replaced them.
- **Never a second opinion.** For every field the summary shares with a detailed tool, the two agree
  on the same character in the same state. The architecture makes this true by construction; the
  bridge test in [Tests](#tests) checks that it stays true.
- **Description budget.** The description says what the summary is *for* and **names the detailed
  tool behind each section**, since there is no map in the response to do that. Field-level
  explanation stays in the detailed tools' descriptions, which the client has already downloaded.

## Architecture

**Tool and command.** `src/mpfbmcp/tools/get_character_summary.py`,
`bridge/mpfb_bridge/commands/get_character_summary.py`, one `register()` call, one `table.py` entry
— the four-thing rule. The command declares `requires_mpfb=True`. The tool-side module validates
`name`'s shape and nothing else.

**The extraction is most of the work**, which is why this request is larger than a new read tool
usually is. Each section's reading moves out of its detailed command into a shared module, and the
detailed command is rewritten to call it:

| Shared module | Extracted from | Used by |
|---|---|---|
| `macro_reading.py` (new) | `get_macro_details`: `_macro_details_of`, `_race_sum_of`, the stack and current-shape-key reads, and the drift comparison this request adds | `get_macro_details`, `get_character_summary` |
| `asset_info.py` (new) | `get_object_info`: `_asset_info_for`, its helpers, and the related-object walk | `get_object_info`, `get_character_summary` |
| `target_rollup.py` (new), or an extension of `modifier_reading.py` | `get_target_stack`: `_shapekey_values`, `_build_modifiers`, the kind classification | `get_target_stack`, `get_character_summary` |
| `expression_divergence.py` (FR 027's; the stack read is already there as `stack_rows()`, so nothing moves) | — | `get_expression`, `apply_expressions`, `set_face_units`, `get_character_summary` |

`get_face_units` reads straight off `FaceService`, and the non-zero filter is a line; there is nothing
there that clears the shared-module bar. If a live run shows the two disagreeing, that verdict is
wrong and it moves too.

Each extraction must leave its source command's answer **unchanged**, including every quirk its
docstring says is reproduced rather than tidied up — and the docstrings that explain those quirks
move with the code, since the shared module is now where a reader stands when they need them. The
commands' bridge tests in [bridge/test/tests/](../../../bridge/test/tests) are the proof: run them
before and after each move, **one command per commit**. The one intended change to an existing
answer is `mpfb_get_macro_details` gaining `macro_drift` (requirement 4).

**Pitfalls.**

- **Do not compose by calling other commands' handlers.** It is the shortest route, and it makes the
  summary's shape the union of five answers it then has to prune, couples it to their parameter
  defaults, and makes one command a client of another — which `table.py`'s claim to be the whole
  vocabulary does not survive.
- **`get_target_stack` computes its rollup from a snapshot read once**, and `symmetrize_targets`
  from `key_blocks` per call; `modifier_reading.py` already takes the lookup as an argument for that
  reason. The summary is the snapshot case.
- **Basemesh resolution is written eighteen times.** Eighteen commands reach the basemesh through
  `ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")`, each inside a
  wrapper of its own, and even the three read-only `_resolve_basemesh` copies (`get_macro_details`,
  `get_target_stack`, `get_face_units`) differ from one another with their strings stripped. The
  summary uses the one `get_macro_details` uses, since requirement 1 promises that tool's
  resolution, and **moves it into `macro_reading.py` with the rest of that command's reading** —
  that much is needed for requirement 1 to be true by construction. Consolidating the other seventeen
  is [a separate entry in NEXT_STEPS.md](../../NEXT_STEPS.md#one-basemesh-resolver) and is not done
  here.
- **The count of shared modules** goes from FR 027's ten to thirteen. The list in
  [architecture.md](../../../specifications/architecture.md#shared-modules-and-what-warrants-one) says
  what warrants each; these three share one warrant, which is worth stating once rather than three
  times.

## Affected specifications

- [vision.md](../../../specifications/vision.md#target-tool-catalog) — the tool moves from "still
  missing" to the Introspection count, and the tool and command totals each go up by one on top of
  FR 027's four. The name there was `mpfb_get_human_summary` and was changed to this request's name
  when it was scoped.
- [architecture.md](../../../specifications/architecture.md#shared-modules-and-what-warrants-one) — the
  shared-module list gains three entries and a new warrant: **a summary and its detailed tool are
  one implementation.**
- [responses.md](../../../specifications/responses.md) — a new section on the summary contract: a
  summary shares its detailed tool's field names, never disagrees with it, reports nothing the
  detailed tool does not, and names it.
- [testing.md](../../../specifications/testing.md) — only if the agreement test below establishes a
  pattern worth naming.

## Tests

- **Unit (`tests/test_get_character_summary.py`)** — the usual two layers: the wrapper with
  `send_command` mocked (the one argument's shape, what reaches the wire), and the bridge path
  against `fake_bridge`. There is almost nothing to validate locally, which is right.
- **Bridge (`bridge/test/tests/`)** — a new module for the command, against a real MPFB: the miss;
  a bare basemesh; a rigged, dressed, morphed character with an expression applied and a face unit
  composed on top of it. And the test this request is really about: **for the same character, every
  field the summary shares with a detailed command equals that command's answer**, asserted by
  dispatching both. That test is what stops the two drifting after the extraction is forgotten.
- **Extraction** — no new tests for `get_macro_details`, `get_object_info`, `get_target_stack` or
  `get_expression` beyond `macro_drift`. Their existing bridge tests passing unchanged is the claim.
- **Live** — a script in this subdir, run during the effort, that builds the worst-case character
  (full macro set, a Rigify rig generated, eight asset types, a non-default skin, a few dozen targets,
  an expression and a face unit), calls the summary and each detailed tool, compares them field by
  field, and records the answer size and the latency against the total of the calls it replaces.
  Plus **one smoke item** in [verification/](../../../verification/) and its
  `tests/test_verification_smoke.py` entry.
- `tests/test_description_budget.py` ceilings move by what the description costs, and the commit
  says why.

## Verification status

All of it ran, against Blender 5.1.0 with MPFB 2.0.17 from source.

- **[`live_check.py`](live_check.py)**, in this subdir: 57 checks, through the **real tools over the
  real socket** to a headless Blender the script starts itself. It builds the worst case named in
  [Tests](#tests) — every macro moved, a Rigify rig generated after all eight mesh asset types were
  attached, an `ENHANCED` skin, 41 modeling categories with every sided one lopsided, `Wink.json`
  at 0.8 and two units composed on top — then a bare basemesh and a miss, and compares every field
  the summary shares with `mpfb_get_macro_details`, `mpfb_get_object_info` (basemesh and rig),
  `mpfb_get_target_stack`, `mpfb_get_face_units` and `mpfb_get_expression`. All passed. Worst case:
  **7,440 B** on the wire, **14.0 ms** best of three, against **20.6 ms** for the six calls it
  replaces (0.7 + 8.4 + 6.3 + 4.9 + 0.1 + 0.2).
- **`live_check.py --snapshot`**, before the first extraction and after each of the three: the
  detailed commands' answers on the same character, diffed. The first move added the two
  `macro_drift` lines (worst case and bare) and nothing else; the second and third, nothing.
- **The windowed half.** The headless runs cannot reach the timer-driven path, so the same
  comparisons ran against the two preset-built characters in the developer's GUI Blender, over its
  own bridge server: 46 checks, all passed, about 4.6 KB per answer; `macro_drift` false on both.
  Nothing in that scene was changed, and the server was stopped again afterwards.
- **Bridge tests**: `uuu_get_character_summary_test.py` (7), and three for `macro_drift` in
  `iii_get_macro_details_test.py`. **359** in all, green, and green after each extraction.
- **Unit tests**: `tests/test_get_character_summary.py` (5), **428** in all, green; the description
  ceiling raised to 69,600 and the schema ceiling to 12,300, reasons in
  `tests/test_description_budget.py`.
- **One smoke item**, placed just before the preset save so it reads the fullest character the run
  builds; the run is 34 items, all passing, in 1.5 s.

### What landed differently from the text above, and why

- **The rollup is capped**, which [Non-functional requirements](#non-functional-requirements)
  allowed for: uncapped, the worst case's rollup alone was about 8.8 KB. 25 modifiers and 8
  asymmetries, the ones furthest from zero, in `mpfb_get_target_stack`'s order. The flag is
  `rollup_truncated`, not `total_count`/`truncated` as the requirement put it, because
  `mpfb_get_target_stack` already uses both names for its shape-key paging and
  the same-names rule under [Sections](#sections) forbids one name meaning two things; the totals are
  `modifier_count` (that tool's own name) and `asymmetry_count`.
- **`macro_drift` compares weights as well as names.** Requirement 4 described it as the comparison
  of the two shape-key lists, but moving one slider without a recalculation usually changes no name,
  only weights, so a names-only flag would miss the commonest drift. Its bridge tests pin it false at
  the sliders' extremes and true after exactly that slider move.
- **`skin.material_type` is MPFB's `identify_material()` name** (`enhanced_skin`, `layered_skin`,
  `makeskin`...), which is what `mpfb_get_object_info` reports; requirement 7 assumed the
  `mpfb_set_skin` vocabulary.
- **The rig is `find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")`**, MPFB's own
  answer, which requirement 5 left open.
- **`subject_in_current_scene` and `basemesh_in_current_scene`** were added for requirement 3.
- **`target_rollup.py` is new**, rather than an extension of `modifier_reading.py`: the rollup
  needs the per-shape-key entries and counts too, which are not a slider reading.
- **`set_macro_details` keeps a copy of the phenotype reading.** Found during the extraction and
  out of scope, since the summary does not read through it; queued beside
  [the basemesh resolver](../../NEXT_STEPS.md#one-basemesh-resolver).
- **The latency premise is out of date.** The ~250 ms per round trip in the background was the
  generated-code path's; on the bridge the saving is a few milliseconds, and the case for the tool
  rests on the answer being one small read rather than six long ones.

## Decisions taken while scoping

- **Every section is shared, not only the macro one.** The vision required it of the macro half;
  the same argument applies to every other half, and reimplementing four readings for the summary
  would give four chances to disagree in exchange for leaving three commands untouched.
- **No cross-section findings.** A `findings` list (rig refit blocked, meta rig not generated,
  garment not deformed by the rig, race weights unnormalized) was proposed and left out. It would be
  the one part of the answer no detailed tool could confirm, so a finding would be unverifiable by the
  caller. The per-section facts it would have been derived from are all present; joining them is the
  agent's. `shared/refit_blocker.py` makes a refit-blocked prediction cheap if a later effort wants
  one, and that effort should decide which tool reports it.
- **No `detail_tools` map in the response.** The description names the detailed tool per section,
  once, rather than every response paying for it.
- **Face units and the expression stack are both in scope**, the second making this request depend
  on FR 027. `unexplained_face_units` is the justification: it is the state most likely to be lost by
  the next modification, and nothing else shows it.
- **Named `mpfb_get_character_summary`**, not the vision's `mpfb_get_human_summary`: this package
  says "character" in its descriptions and responses, and MPFB's `HumanService` is not a name an
  agent reading the tool list has any reason to know.
- **The basemesh resolver's fourteen other copies are left alone** and queued separately.

## References

- [vision.md — What is still missing](../../../specifications/vision.md#target-tool-catalog)
- [FR 027](../027-expression-library/README.md) — `mpfb_get_expression`, `expression_divergence.py`,
  and the definitions of `matches_stack` and `unexplained_face_units`.
- Commands whose reading is extracted:
  [get_macro_details.py](../../../bridge/mpfb_bridge/commands/get_macro_details.py),
  [get_object_info.py](../../../bridge/mpfb_bridge/commands/get_object_info.py),
  [get_target_stack.py](../../../bridge/mpfb_bridge/commands/get_target_stack.py); and read without
  extraction: [get_face_units.py](../../../bridge/mpfb_bridge/commands/get_face_units.py).
- [shared/modifier_reading.py](../../../bridge/mpfb_bridge/shared/modifier_reading.py) — the
  snapshot-or-live lookup argument the target rollup must respect.
- [FR 030](../030-backend-seam/README.md) — `mpfb_list_objects` as the template for a read
  tool on the bridge.
