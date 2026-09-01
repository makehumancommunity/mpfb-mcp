# Adding a rig to a character

**Status:** Done

[FR 004](../004-list-rigs/README.md) built the catalogue of rigs that could be added, and gave
each entry the two things an acting tool would need: the `identifier` an adding function takes, and
the `add_function` that takes it. That acting tool does not exist. mpfb-mcp can name every rig in
the install and attach none of them, so every character it produces is a static mesh.

Adding a rig is the smallest of the three asset efforts in code and the largest in consequence,
because it is the one with an **ordering constraint attached to it**. `HumanService.add_mhclo_asset()`
looks for a `Skeleton` relative at the moment a garment is attached and rigs the garment only if it
finds one; nothing re-rigs it afterwards, and `HumanService.refit()` deliberately passes
`set_parent=False`. MPFB's own character builder documents this in a comment — the rig is added
before the body parts, and Rigify generation happens after them. An agent that dresses a character
and then adds a rig gets clothes that do not follow the armature, with no error anywhere.

Rigify makes that a three-step sequence rather than two. `add_builtin_rig("rigify.human")` produces
only a **meta rig**; MPFB's panel then offers a separate Generate button, and the randomizer runs it
last, after the clothes, so that their weights and sub-rigs exist when the meta rig becomes the real
one. Exposing generation as its own tool rather than as a flag on adding is what lets an agent
follow that order.

## Goals

Primary: attach any rig `mpfb_list_rigs` reports to a character, with the same result MPFB's own
"Add standard rig" / "Add rigify rig" / "Add custom rig" buttons produce, and turn a Rigify meta rig
into a generated rig.

Secondary: make the ordering constraint visible. A rig added to an already-dressed character is a
mistake the tool can *see* being made, and reporting it is cheaper than the user discovering it when
they move a bone.

Also: close the loop [FR 004](../004-list-rigs/README.md) left open — every `identifier` that
catalogue reports must be one this tool accepts, and dispatching on `add_function` must be this
tool's job rather than the caller's.

## Functional requirements

Two tools.

### `mpfb_add_rig`

Mutating. Arguments:

- `name` (optional string) — a Blender object name, resolved to the character's basemesh as in
  [FR 007](../007-macro-details/README.md). Omitted means the active object.
- `identifier` (required string) — exactly as `mpfb_list_rigs` reports it: a bare name for a standard
  rig, `rigify.<name>` for a Rigify one, `custom.<name>` for a user one. Not a filename, and not the
  `name` field beside it.
- `import_weights` (optional bool, default `true`) — MPFB's own default in all three UI operators.

`result` carries `basemesh_name`, `subject_resolved_by`, `found`, `message`, and:

- `rig_object_name` — the armature actually created, which is `<basemesh>.rig` or, for Rigify,
  `<basemesh>.metarig`. Blender will uniquify it if that name is taken, so the created name is
  reported rather than predicted.
- `add_function_used` — `"add_builtin_rig"` or `"add_custom_rig"`, and `family`
  (`standard`/`rigify`/`custom`). This says which of `mpfb_list_rigs`' two dispatch paths was taken,
  so a caller can see that the identifier was understood the way they meant it.
- `is_metarig` (bool) and, when true, `next_step` — a sentence naming `mpfb_generate_rigify_rig` and
  saying that assets should be attached *before* generating. A Rigify rig is not finished when this
  tool returns and the response must not read as though it were.
- `weights_loaded` (bool), `weights_from` and `weights_path` — which rig's weights file was actually
  used. MPFB resolves this through `RigService.get_rig_weight_fallbacks()`, so a rig legitimately
  borrowing another's weights is normal and a rig with none at all is not; `mpfb_list_rigs` already
  predicts this per entry and the two must agree.
- `armature_modifier_added` (bool) — only added when `import_weights` is true, which is the
  difference between a parented mesh and a deformed one.
- `basemesh_moved_to_origin` (bool) and `rig_location` — both adding functions move the basemesh to
  `(0, 0, 0)` and give the armature its old location. On a character standing anywhere but the
  origin this visibly moves things, and it is not obvious from "a rig was added".
- `mesh_assets_not_rigged` — the names of mesh assets already attached to this character, which this
  tool has just failed to rig, plus a sentence saying they were attached before the rig and will not
  follow it. Empty on the normal path. This is the ordering constraint, reported.
- `subrigs_not_rigged` — likewise for any `Subrig` relative already present.

Preconditions come back as answers with `added: false`, never as tracebacks:

- The subject resolves to no basemesh, or nothing is active.
- The character **already has a `Skeleton` relative**. MPFB's own panels hide the add button in this
  state, and adding a second rig re-parents the basemesh to it, silently orphaning the first. Report
  the existing rig's name and refuse; there is no `force` argument, because the recovery is to delete
  the existing rig, which is outside this tool.
- `identifier` names no rig. With `operator=None` — which is what generated code has — MPFB raises
  `IOError` for a missing built-in rig file and `ValueError` for an unknown custom rig. Check first,
  and answer with `known_identifiers` for the family that was addressed, per
  [Validate before crossing the socket](../../../specifications/architecture.md#validate-before-crossing-the-socket).
- `identifier` starts with `rigify.` and Rigify is not enabled. `add_builtin_rig()` raises
  `NotImplementedError` rather than degrading; `SystemService.check_for_rigify()` is the same check
  `mpfb_list_rigs` already reports as `rigify_available`.
- The basemesh is not in OBJECT mode.

### `mpfb_generate_rigify_rig`

Mutating. Wraps `RigService.generate_rigify_rig()`. Arguments:

- `name` (optional string) — subject. Resolved to the character's `Skeleton` relative rather than to
  its basemesh, since the meta rig is what is operated on; passing the basemesh, the meta rig itself
  or a garment must all work.
- `rig_name` (optional string) — the generated rig's basename. Omitted means MPFB's own fallback,
  which derives a unique name from the meta rig's.
- `meta_rig_action` (optional string, default `"hide"`) — `"keep"`, `"hide"` or `"delete"`, MPFB's
  own vocabulary and default.

`result` carries `metarig_name`, `subject_resolved_by`, `message`, and:

- `generated` (bool) and `rig_object_name`. `generate_rigify_rig()` returns `None` when Rigify's own
  `is_valid_metarig()` rejects the meta rig, **having already renamed the meta rig and deselected
  everything** — a partial effect that must be reported rather than presented as "nothing happened".
- `metarig_disposition` — what became of the meta rig (`kept`, `hidden`, `deleted`).
- `refit_will_be_possible` (bool) plus an explanatory `message` when it is false. This is the same
  failure [FR 007](../007-macro-details/README.md) documents from the other end: with no meta rig in
  the scene, `HumanService.refit()` logs a warning, tries to report through an operator it does not
  have, and **returns having refitted the mesh assets but not the rig** (FR 007 corrected its own
  "refitted nothing" while implementing — the asset loop runs before the rig block). Implemented,
  `mpfb_refit_human` detects the condition and answers `refit_performed: false` with a
  `refit_incomplete_reason`. `meta_rig_action: "delete"` is precisely what creates that state, so
  this tool is where the consequence is knowable in advance.
- `mesh_assets_present` — the mesh assets that existed at generation time, since generating before
  attaching them is the second half of the ordering problem.
- `active_object_after` — generation deselects everything and leaves the generated rig active. Unlike
  every other mutating tool here, the previous selection cannot be restored (the operator's own
  final act is to select its result), so the response says what the selection now is.

Preconditions as answers: no armature found; the armature is not a Rigify meta rig
(`RigService.identify_rig()` does not return something starting with `rigify.`); Rigify not enabled;
not in OBJECT mode.

**Not in scope.** Removing a rig — MPFB has no unload counterpart to `add_builtin_rig()`, and doing
it correctly means removing the armature modifier from the basemesh and from every fitted asset,
re-parenting them, and dealing with sub-rigs; that is its own request, and until it exists the
"already has a rig" refusal above is the honest answer. Also out: pose loading from the `poses`
library and any other BVH work (see [NEXT_STEPS.md](../../NEXT_STEPS.md)); bone-level manipulation, rig
helpers and IK/FK cycles; `RigService.refit_existing_armature()` on its own, which
[FR 007](../007-macro-details/README.md)'s `mpfb_refit_human` already covers; and sub-rigs shipped
with clothing, which are [FR 010](../010-mesh-assets/README.md)'s `import_subrig`.

## Non-functional requirements

- **The same result MPFB's own buttons produce.** Call `add_builtin_rig()` / `add_custom_rig()` /
  `generate_rigify_rig()` and dispatch between them exactly as `HumanService._check_add_rig()` does —
  on the `custom.` prefix, nothing else. None of the naming, parenting, weight-fallback or Rigify
  bookkeeping is reimplemented here.
- **Ordering is reported, not enforced.** The tool does not refuse to add a rig to a dressed
  character — that is a legitimate thing to do when the clothes are decorative — but it must never
  let the caller believe the clothes are rigged. Silence here is the failure mode this request exists
  to prevent.
- **Preconditions are answers.** Every one of the five refusals above is a state an agent will
  actually reach, and each has a one-sentence explanation. The bar is that `mpfb_get_status` should
  not be needed to understand a refusal.
- **A half-finished Rigify character must look half-finished.** `is_metarig` and `next_step` exist so
  that "the rig was added" is not mistaken for "the character is rigged".
- **Restore what was borrowed**, where it is possible. `mpfb_add_rig` restores the previous active
  object and selection; `mpfb_generate_rigify_rig` cannot and says so instead.

## Architecture

- Two tool modules under [`src/mpfbmcp/tools/`](../../../src/mpfbmcp/tools), two payloads under
  [`src/mpfbmcp/codegen/payloads/`](../../../src/mpfbmcp/codegen/payloads), two `register()` calls, per
  [the code-generation layout](../../../specifications/architecture.md#code-generation-layout).
  **Raising bootstrap** for both; `HumanService`, `ObjectService`, `RigService` and `SystemService`
  are all in the `SERVICES` dict.
- **Dispatch on the prefix, never let the caller choose the function.** `identifier.startswith("custom.")`
  selects `add_custom_rig()`; everything else goes to `add_builtin_rig()`, which handles the
  `rigify.` prefix itself. Crossing the two does not fail legibly, and
  [How tools name things that can be added](../../../specifications/architecture.md#how-tools-name-things-that-can-be-added)
  records why: `add_builtin_rig("custom.my_rig")` looks for `rig.custom.my_rig.json`, and
  `add_custom_rig()` strips the first seven characters of whatever it is given.
- **Pre-check existence the way the two functions resolve it**, so a bad identifier is an answer and
  not an exception. A built-in rig is `<mpfb data>/rigs/{standard,rigify}/rig.<bare name>.json`; a
  custom one is a `name` in `AssetService.get_custom_rigs()`. Both are the checks
  [`payloads/list_rigs.py`](../../../src/mpfbmcp/codegen/payloads/list_rigs.py) already performs, and the
  two payloads must not drift. [FR 008](../008-detail-targets/README.md) faced the same problem
  at a larger scale and answered it by *factoring* rather than duplicating: `codegen.assemble()` now
  takes an optional `shared=[...]` naming fragment files concatenated ahead of the payload, and the
  convention is recorded under
  [Shared fragments](../../../specifications/architecture.md#shared-fragments). Duplicating a few lines
  and saying so in both docstrings is still the right answer for a small overlap; a rig-existence
  check shared by two payloads is a judgement call to make when the code is in front of you. What is
  no longer acceptable is silent duplication.
- **`operator=None` changes the failure mode, and that is the whole reason for pre-checking.** Both
  adding functions take an optional operator and report through it when they have one; with `None`
  they raise instead — except in one place, where `add_builtin_rig()` reports a missing *weights*
  file through the operator and otherwise carries on silently. So a rig can be added with no weights
  and no complaint; `weights_loaded` is how that becomes visible.
- **Existing-rig detection.** `ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh,
  "Skeleton")` — the same call the three rig panels make in their `draw()` to decide whether to offer
  the button at all.
- **Detecting assets that will not be rigged.** `ObjectService.find_related_mesh_assets(basemesh)`
  for the meshes and `find_all_objects_of_type_amongst_nearest_relatives(basemesh, "Subrig")` for the
  sub-rigs, both before adding. After the rig is parented these are still reachable, but reading them
  first keeps the claim precise: these are the assets that were attached *before* the rig existed.
- **Pitfall — the Rigify assertion.** `add_builtin_rig()` contains
  `assert len(armature_object.data.rigify_colors) > 0` for a Rigify rig, which on a Blender where
  Rigify is enabled but the colour sets did not initialise comes back as a bare `AssertionError` with
  no message. It is downstream of the `check_for_rigify()` guard, so it cannot be pre-checked
  usefully; catch it and translate rather than letting the traceback stand as the answer.
- **Pitfall — generation is not idempotent and not undoable.** `generate_rigify_rig()` renames the
  meta rig, may set `rigify_rig_basename`, runs `bpy.ops.pose.rigify_upgrade_face()` when it polls
  true, and only then asks `is_valid_metarig()`. A `None` return therefore does not mean "nothing
  changed". Report `generated: false` together with what did happen, rather than an error envelope
  that implies a no-op.
- **Pitfall — `meta_rig_action: "delete"` is the state FR 007 cannot recover from.** It is worth a
  sentence in the tool docstring and a field in the response, not just a note here.
- **`bpy.ops` is available in this execution context** — `mpfb_create_human` already calls
  `bpy.ops.object.transform_apply` — and `generate_rigify_rig()` manages its own selection and mode.
  `mpfb_add_rig` should still activate the basemesh and restore afterwards, following MPFB's own
  operators.
- Response envelope unchanged: return `send_code(...)` as-is with `strict_json=True`.

## Affected specifications

- [vision.md](../../../specifications/vision.md#target-tool-catalog) — the `mpfb_add_rig` entry under
  "Creation and modification" exists and should be marked **Implemented** and described.
  `mpfb_generate_rigify_rig` is a **new entry**. The `mpfb_list_rigs` entry should gain a line saying
  that its `identifier` and `add_function` are consumed here, the same pairing
  [FR 008](../008-detail-targets/README.md) draws between `mpfb_list_targets` and its setter.
- [architecture.md](../../../specifications/architecture.md) — conventions to follow, and one candidate
  addition.
  - **To follow:**
    [How tools name things that can be added](../../../specifications/architecture.md#how-tools-name-things-that-can-be-added),
    which this tool is the first consumer of, and
    [How generated code addresses objects](../../../specifications/architecture.md#how-generated-code-addresses-objects).
  - **Plus the three conventions [FR 007](../007-macro-details/README.md) landed**, which this
    request now *follows* rather than proposes:
    [How a mutating tool takes its subject](../../../specifications/architecture.md#how-a-mutating-tool-takes-its-subject),
    [A mutating tool reports before and after](../../../specifications/architecture.md#a-mutating-tool-reports-before-and-after)
    and
    [Preconditions are answers](../../../specifications/architecture.md#preconditions-are-answers).
  - **New — a tool reports an ordering constraint it cannot enforce.** MPFB's services have implicit
    sequencing (rig before assets, assets before Rigify generation, and see
    [FR 010](../010-mesh-assets/README.md) for the same problem with proxies and clothes) which no
    single call can validate and which produces no error when violated. The rule worth recording:
    where a tool can *observe* that the caller is about to violate one, it reports the observation in
    the response — naming the objects affected — rather than either failing or staying silent. This
    is the sequencing counterpart of "an empty answer must never be ambiguous".

## Tests

Two layers, as established: argument validation with each tool module's `send_code` mocked, then the
generated source `exec()`d against stubs in [tests/blender_stubs.py](../../../tests/blender_stubs.py).

The stubs need a `StubHumanService` with the rig half of the real one and a `StubRigService`,
reproducing behavior rather than convenience:

- `add_builtin_rig()` / `add_custom_rig()` that **raise** on an unknown rig when given no operator,
  as the real ones do — a stub that returned `None` would make the pre-checks look unnecessary.
- `add_builtin_rig()` that reports a missing weights file *only* through an operator, so the silent
  no-weights path is exercised.
- `get_rig_weight_fallbacks()` reproducing the real fallback table, so `weights_from` is asserted
  against MPFB's resolution rather than against a filename.
- `generate_rigify_rig()` that renames the meta rig **before** returning `None` for an invalid one,
  so the "a failed generation is not a no-op" claim is actually tested.
- A stub scene, reusing the existing one, with a character that has a rig and one that does not, and
  one with clothes attached but no rig — the `mesh_assets_not_rigged` case.

Cases worth naming: `custom.` dispatches to `add_custom_rig` and nothing else does; a `rigify.`
identifier with Rigify unavailable is refused before any code touches MPFB; an existing `Skeleton`
relative refuses with the rig's name; the subject resolves from a garment's name as well as from the
basemesh's; `import_weights: false` reports no armature modifier; `mpfb_generate_rigify_rig` resolves
a meta rig from the basemesh; `meta_rig_action: "delete"` reports `refit_will_be_possible: false`; and
an invalid meta rig reports `generated: false` with the rename that did happen.

**Live verification against a running Blender is required**, with the [FR 004](../004-list-rigs/README.md)–006
revert discipline (snapshot every datablock collection, compare after, never save the `.blend`) —
and here the mutations are large, so a fresh file per case is the practical form of it. Specifically:

- That a standard rig added through the tool is indistinguishable from one added through MPFB's
  panel: same bone count, same weights, same parenting, same object names.
- The weight fallback on a rig that has no weights file of its own — FR 004 predicted the fallback
  from the table; this is where the prediction is checked against what actually got loaded.
- **The ordering constraint, observed rather than inferred.** Dress a character, then add a rig, and
  confirm the clothes do not follow the armature; then do it in the other order and confirm they do.
  This is the claim the whole request is built on and nothing on this side of the socket establishes
  it.
- The full Rigify sequence: add meta rig, attach a garment, generate, and confirm the garment is
  handled by `adjust_children_for_rigify()`. Then the wrong order, to see what it costs.
- `meta_rig_action` in all three values, and that `"delete"` really does leave
  [FR 007](../007-macro-details/README.md)'s `mpfb_refit_human` unable to refit the rig —
  which it should report as `refit_performed: false` rather than silently. FR 007 landed without
  live verification, so this is also the first live check of that branch.
- The `rigify_colors` assertion path, if it can be provoked at all; if it cannot, say so.
- Cost against [FR 005](../005-list-assets/README.md)'s ~1.0 s socket round-trip baseline: how
  long adding a weighted rig takes, and how long Rigify generation takes on a dressed character.
  Generation is expected to be much the slowest operation mpfb-mcp performs.

Record the outcome in a `## Verification status

**Implemented, unit-tested and live-verified (2026-09-01)**, by
[FR 013](../013-live-verification/README.md)'s session, against Blender 5.1.0 with MPFB 2.0.17
running `FROM_SOURCE` out of `../mpfb2`, with Rigify enabled and three real custom rigs installed.
It is now a script: [verification/check_fr009.py](../../../verification/check_fr009.py).

[FR 004](../004-list-rigs/README.md)'s verification, which this effort's `rig_lookup.py` migration
made stale, was re-run in the same session and is green again; see
[its status](../004-list-rigs/README.md#verification-status).

Every scene mutation was reverted — all twelve datablock collections plus `bpy.data.is_dirty`
compare **identical** before and after — including the `WGTS_<rig>` widget collection Rigify
generation leaves behind, which the harness purges along with the widget objects. The `.blend` was
never saved.

### What changed against this request

**The ordering constraint is confirmed, and it is the sharpest result of the session.** Character
B was dressed and *then* rigged; Character A's counterpart was rigged and then dressed. The
garment on the wrongly-ordered character has **no armature modifier and 0 weighted vertices**; the
correctly-ordered one has an `Armature` modifier and **285 weighted vertices**. That claim — that
MPFB rigs a garment only if a rig exists at the moment it is attached, and nothing rigs it
afterwards — is what
[A tool reports an ordering constraint it cannot enforce](../../../specifications/architecture.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
is built on, and until now it was a reading of MPFB's source. It is now an observation. Recorded
from the other end in [FR 010's status](../010-mesh-assets/README.md#verification-status) too,
since that is the checklist that produced the fixture.

**One candidate mpfb2 defect this request filed is refuted.** `RigService.identify_rig()` cannot
return `None`: it ends with an `if guessed_rig is None:` block that assigns `"unknown"`,
`"rigify.unknown"` or `"rigify_generated.unknown"`. Provoked against an armature whose only bone
matches nothing MPFB knows, it returned `"unknown"`, and
`MPFB_OT_GenerateRigifyRigOperator.poll()` returned `False` rather than raising. The
`not_a_metarig` handling in `payloads/generate_rigify_rig.py` is still right — it is the answer for
`"unknown"` — but the reason given for it was wrong.

A *different* defect was found while provoking it, and is worth filing:
`ObjectService.object_is_rigify_metarig()` reads `blender_object.pose.bones` without checking, and
an armature object created through `bpy.data.objects.new()` has `pose` set to `None` until the
depsgraph has seen it, so `identify_rig()` raises `AttributeError` on it.

**The `rigify_colors` assertion cannot be provoked from outside MPFB.** This request asked
whether it can be at all. On an install with Rigify enabled, the colour set is populated by
Rigify's own theme code during armature creation — 6 colours were observed on a freshly added meta
rig — so `assert len(...rigify_colors) > 0` cannot fail; and with Rigify disabled,
`mpfb_add_rig` refuses before reaching it. The stray-object report the payload carries remains
correct and remains unreachable, which is the honest description of it.

### Checklist

- [x] **A rig added through this tool is indistinguishable from one added through MPFB's panel.**
      `mpfb.add_standard_rig` and `mpfb_add_rig` were each given `default` on a fresh character:
      identical bone count (163), identical bone-name set, identical vertex-group count, identical
      total vertex weight (65237.992), same armature modifier name, same parenting, same basemesh
      location.
- [x] **The ordering constraint, observed.** Dressed-then-rigged: `armature_modifier: null`, 0
      weighted vertices. Rigged-then-dressed: `Armature`, 285 weighted vertices, and
      `mpfb_add_asset` reported `rigged_to: "RightOrderCharacter.rig"`.
- [x] A second rig is refused rather than added: `added: false`,
      `blocked_by: "already_rigged"`, and the character still has exactly one armature.
- [x] **The full Rigify sequence in both orders.** Meta rig → clothes → generate: the garment is
      re-parented onto the generated rig and its armature modifier retargeted to it, and
      `is_metarig`/`next_step` said so in advance. Generate → clothes: the asset is rigged to the
      generated rig but `warnings` names the real problem — that
      `RigifyHelpers.adjust_children_for_rigify()` handled only what was present at generation and
      will not run again.
- [x] The `rigify_colors` assertion: **not provokable on this install**, for the reason above.
      Reported rather than ticked off as an untested branch.
- [x] `meta_rig_action: "delete"` forecloses the refit: `refit_will_be_possible: false`, and the
      following `mpfb_refit_human` returns `refit_performed: false` with an
      `refit_incomplete_reason` naming the generated rig — while still reporting the one mesh asset
      it did refit. This is also the first live check of that branch of
      [FR 007](../007-macro-details/README.md).
- [x] An armature `identify_rig()` cannot place is refused rather than crashing:
      `generated: false`, `blocked_by: "not_a_metarig"`, with a message naming what it found.
- [x] Cost: adding `default` 2169 ms, adding `rigify.human_toes` 2214 ms, generating on a dressed
      character 1429 ms — see
      [FR-8's measurements](../013-live-verification/review.md#do-the-three-payload-count-driven-decisions-still-hold).
- [x] Revert: all twelve datablock collections identical, `is_dirty` false before and after.

## References

- MPFB `services/humanservice.py` — `add_builtin_rig()`, `add_custom_rig()`, `_check_add_rig()` (the
  reference for dispatching on the `custom.` prefix), and `refit()`, whose generated-Rigify branch is
  what `refit_will_be_possible` predicts.
- MPFB `services/rigservice.py` — `generate_rigify_rig()`, `get_rig_weight_fallbacks()`,
  `load_weights()`, `ensure_armature_modifier()`, `identify_rig()`.
- MPFB `ui/rigging/standardrig/`, `ui/rigging/rigifyrig/`, `ui/rigging/customrig/` — the three add
  operators and the `generate_rigify_rig` operator, their `BASEMESH_ACTIVE` poll strategy, and the
  panels' `draw()` methods, which are where "a rig already exists" becomes a hidden button.
- MPFB `ui/new_human/randomize/characterbuilder.py` — the ordering comments this request is built
  around: the rig before the body parts, Rigify generation after the clothes.
- [FR 004](../004-list-rigs/README.md) — the catalogue whose `identifier`, `add_function` and
  weights prediction this request consumes, and its Verification status section.

## Verification status

**Implemented and unit-tested; live verification is outstanding.** Both tools, their payloads, the
shared code-generation fragment, the migration of `mpfb_list_rigs` onto it and the tests landed
together, and the whole suite passes — 492 tests, up from 419. As with
[FR 007](../007-macro-details/README.md) and [FR 008](../008-detail-targets/README.md), and unlike
[FR 001](../001-mpfb-get-status/README.md) through [FR 006](../006-list-targets/README.md), this
request was **not** checked against a running Blender before being marked Done.

That debt is now compound in a new way. This effort refactored
[`payloads/list_rigs.py`](../../../src/mpfbmcp/codegen/payloads/list_rigs.py) onto the shared
fragment, so **[FR 004](../004-list-rigs/README.md)'s live verification is stale**: the payload's
behavior is unchanged as far as the unit tests can tell — they run the same 40 assertions against
the same temporary rig tree — but the program sent into Blender is a different program. Re-running
FR 004's live check is now part of the same outstanding session as FR 007's and FR 008's.

### What the unit tests do establish

The stubs reproduce MPFB's real behavior rather than a convenient version, and each quirk is there
because leaving it out would make a test pass vacuously:

- `add_builtin_rig()` and `add_custom_rig()` **raise** for an unknown rig when given no operator —
  `IOError` and `ValueError` respectively — which is what generated code always gets. A stub
  returning `None` would make the pre-checks look like belt and braces.
- `add_builtin_rig()` reports a missing *weights* file through the operator only, so with none it
  adds an unweighted rig in silence. That is the path `weights_loaded` exists for, and the fixture's
  `undocumented_rig` walks it.
- The Rigify colour assertion fires **after** the armature has been created and registered and
  **before** it is parented, so the stray-object report has something real to report.
- `get_rig_weight_fallbacks()` is MPFB's table verbatim, so `weights_from` is asserted against
  MPFB's resolution rather than against a filename — and one test runs `list_rigs.py` and
  `add_rig.py` against the same tree and compares their answers directly, which is the whole point
  of the shared fragment.
- `generate_rigify_rig()` renames the meta rig, deselects everything and activates the meta rig
  **before** the validity gate, then returns `None`. Without that ordering, "a failed generation is
  not a no-op" could not be tested at all.
- Generation re-parents the character onto the generated rig and sets Rigify's `rigify_target_rig`
  back-link, which is what makes `already_generated` a reachable state rather than a hypothetical.

Covered: `custom.` dispatches to `add_custom_rig` and nothing else does; an unknown identifier is
refused with `known_identifiers` for the family addressed and nothing else; a `rigify.` identifier
with Rigify off is refused before MPFB is touched; an existing `Skeleton` refuses with the rig's
name; the subject resolves from a garment; `import_weights: false` reports no armature modifier; a
rig borrowing another's weights says whose, and a rigify rig is not reported as borrowing from
itself; a character not at the origin reports the move; the previous active object and selection are
restored; `mesh_assets_not_rigged` and `subrigs_not_rigged` are non-empty exactly when they should
be; the meta rig resolves from the basemesh, from itself and from a garment; `meta_rig_action` in
all three values, with `"delete"` reporting `refit_will_be_possible: false`; an invalid meta rig
reporting `generated: false` together with the rename that did happen; and an armature
`identify_rig()` cannot place being refused rather than crashing.

### What the unit tests cannot establish

Everything the request is actually about. The live checklist under [Tests](#tests) stands unchanged;
in particular:

- That a rig added through this tool is indistinguishable from one added through MPFB's panel —
  same bone count, weights, parenting and object names.
- **The ordering constraint, observed rather than inferred.** Dress a character, then rig it, and
  confirm the clothes do not follow the armature; then the other way round. Nothing on this side of
  the socket establishes the claim the whole request is built on.
- The full Rigify sequence in both orders, and whether the `rigify_colors` assertion can be provoked
  at all.
- That `meta_rig_action: "delete"` really does leave [FR 007](../007-macro-details/README.md)'s
  `mpfb_refit_human` reporting `refit_performed: false` — which is also the first live check of that
  branch, since FR 007 landed without one.
- Cost against [FR 005](../005-list-assets/README.md)'s ~1.0 s round-trip baseline, for adding a
  weighted rig and for generating on a dressed character.

### What reading MPFB's source turned up

Four things the request did not know, all now reflected in the code:

- **`weights_from` is always a bare name**, so comparing it against the identifier to decide whether
  a fallback was used reports `rigify.human_toes` as borrowing from itself. The payload compares
  against the rig's own bare name instead.
- **`bpy.context.mode` has to be checked as well as `basemesh.mode`.** Building the armature runs
  `bpy.ops.object.armature_add()` and `mode_set()` through `Rig.create_armature_and_fit_to_basemesh()`,
  and those poll on the *context* mode — so an unrelated object left in edit mode fails the operator
  on a basemesh that looks perfectly fine. The request's precondition list named only the basemesh.
- **`RigService.identify_rig()` can return `None`**, not just `"unknown"`: it starts from
  `guessed_rig = None` and matches on bone names. MPFB's own `MPFB_OT_GenerateRigifyRigOperator.poll()`
  would raise `AttributeError` on that. `mpfb_generate_rigify_rig` treats it as `not_a_metarig`.
- **After generation the meta rig is not a relative of the character at all.**
  `adjust_children_for_rigify()` re-parents the basemesh and every garment onto the generated rig,
  and `rigify_object.parent = meta_rig.parent`. So resolving "the character's Skeleton" after a
  generation finds the generated rig, which is why the payload classifies every skeleton relative
  rather than taking the first — and why `already_generated` is a distinct answer.

**Candidate mpfb2 improvement**, noted rather than acted on here: `identify_rig()` returning `None`
makes `MPFB_OT_GenerateRigifyRigOperator.poll()` raise rather than return `False`, which disables
the Rigify sub-panel's Generate button with a traceback in the console when an unrecognised armature
is selected.
