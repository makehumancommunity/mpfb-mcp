# Adding a rig to a character

**Status:** Proposed

[FR 004](../done/004-list-rigs/README.md) built the catalogue of rigs that could be added, and gave
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

Also: close the loop [FR 004](../done/004-list-rigs/README.md) left open — every `identifier` that
catalogue reports must be one this tool accepts, and dispatching on `add_function` must be this
tool's job rather than the caller's.

## Functional requirements

Two tools.

### `mpfb_add_rig`

Mutating. Arguments:

- `name` (optional string) — a Blender object name, resolved to the character's basemesh as in
  [FR 007](../done/007-macro-details/README.md). Omitted means the active object.
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
  [Validate before crossing the socket](../../specifications/architecture.md#validate-before-crossing-the-socket).
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
  failure [FR 007](../done/007-macro-details/README.md) documents from the other end: with no meta rig in
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
library and any other BVH work (see [NEXT_STEPS.md](../NEXT_STEPS.md)); bone-level manipulation, rig
helpers and IK/FK cycles; `RigService.refit_existing_armature()` on its own, which
[FR 007](../done/007-macro-details/README.md)'s `mpfb_refit_human` already covers; and sub-rigs shipped
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

- Two tool modules under [`src/mpfbmcp/tools/`](../../src/mpfbmcp/tools), two payloads under
  [`src/mpfbmcp/codegen/payloads/`](../../src/mpfbmcp/codegen/payloads), two `register()` calls, per
  [the code-generation layout](../../specifications/architecture.md#code-generation-layout).
  **Raising bootstrap** for both; `HumanService`, `ObjectService`, `RigService` and `SystemService`
  are all in the `SERVICES` dict.
- **Dispatch on the prefix, never let the caller choose the function.** `identifier.startswith("custom.")`
  selects `add_custom_rig()`; everything else goes to `add_builtin_rig()`, which handles the
  `rigify.` prefix itself. Crossing the two does not fail legibly, and
  [How tools name things that can be added](../../specifications/architecture.md#how-tools-name-things-that-can-be-added)
  records why: `add_builtin_rig("custom.my_rig")` looks for `rig.custom.my_rig.json`, and
  `add_custom_rig()` strips the first seven characters of whatever it is given.
- **Pre-check existence the way the two functions resolve it**, so a bad identifier is an answer and
  not an exception. A built-in rig is `<mpfb data>/rigs/{standard,rigify}/rig.<bare name>.json`; a
  custom one is a `name` in `AssetService.get_custom_rigs()`. Both are the checks
  [`payloads/list_rigs.py`](../../src/mpfbmcp/codegen/payloads/list_rigs.py) already performs, and the
  two payloads must not drift. [FR 008](../done/008-detail-targets/README.md) faced the same problem
  at a larger scale and answered it by *factoring* rather than duplicating: `codegen.assemble()` now
  takes an optional `shared=[...]` naming fragment files concatenated ahead of the payload, and the
  convention is recorded under
  [Shared fragments](../../specifications/architecture.md#shared-fragments). Duplicating a few lines
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

- [vision.md](../../specifications/vision.md#target-tool-catalog) — the `mpfb_add_rig` entry under
  "Creation and modification" exists and should be marked **Implemented** and described.
  `mpfb_generate_rigify_rig` is a **new entry**. The `mpfb_list_rigs` entry should gain a line saying
  that its `identifier` and `add_function` are consumed here, the same pairing
  [FR 008](../done/008-detail-targets/README.md) draws between `mpfb_list_targets` and its setter.
- [architecture.md](../../specifications/architecture.md) — conventions to follow, and one candidate
  addition.
  - **To follow:**
    [How tools name things that can be added](../../specifications/architecture.md#how-tools-name-things-that-can-be-added),
    which this tool is the first consumer of, and
    [How generated code addresses objects](../../specifications/architecture.md#how-generated-code-addresses-objects).
  - **Plus the three conventions [FR 007](../done/007-macro-details/README.md) landed**, which this
    request now *follows* rather than proposes:
    [How a mutating tool takes its subject](../../specifications/architecture.md#how-a-mutating-tool-takes-its-subject),
    [A mutating tool reports before and after](../../specifications/architecture.md#a-mutating-tool-reports-before-and-after)
    and
    [Preconditions are answers](../../specifications/architecture.md#preconditions-are-answers).
  - **New — a tool reports an ordering constraint it cannot enforce.** MPFB's services have implicit
    sequencing (rig before assets, assets before Rigify generation, and see
    [FR 010](../010-mesh-assets/README.md) for the same problem with proxies and clothes) which no
    single call can validate and which produces no error when violated. The rule worth recording:
    where a tool can *observe* that the caller is about to violate one, it reports the observation in
    the response — naming the objects affected — rather than either failing or staying silent. This
    is the sequencing counterpart of "an empty answer must never be ambiguous".

## Tests

Two layers, as established: argument validation with each tool module's `send_code` mocked, then the
generated source `exec()`d against stubs in [tests/blender_stubs.py](../../tests/blender_stubs.py).

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

**Live verification against a running Blender is required**, with the [FR 004](../done/004-list-rigs/README.md)–006
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
  [FR 007](../done/007-macro-details/README.md)'s `mpfb_refit_human` unable to refit the rig —
  which it should report as `refit_performed: false` rather than silently. FR 007 landed without
  live verification, so this is also the first live check of that branch.
- The `rigify_colors` assertion path, if it can be provoked at all; if it cannot, say so.
- Cost against [FR 005](../done/005-list-assets/README.md)'s ~1.0 s socket round-trip baseline: how
  long adding a weighted rig takes, and how long Rigify generation takes on a dressed character.
  Generation is expected to be much the slowest operation mpfb-mcp performs.

Record the outcome in a `## Verification status` section here.

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
- [FR 004](../done/004-list-rigs/README.md) — the catalogue whose `identifier`, `add_function` and
  weights prediction this request consumes, and its Verification status section.
