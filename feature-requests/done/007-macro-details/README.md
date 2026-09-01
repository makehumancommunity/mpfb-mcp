# Macro details and phenotype

**Status:** Done

`mpfb_create_human` can set a character's macro details — gender, age, muscle, weight, height,
proportions, cupsize, firmness and the three race weights — but only at the moment of creation.
After that the character is frozen: there is no tool that reads back what those values are, and none
that changes them. An agent asked to "make her a bit older" has to delete the character and build a
new one, losing every asset, rig and detail target on it.

The values themselves are ordinary custom properties on the basemesh (`HumanObjectProperties`, prefix
`HUM_`), so reading and writing them is trivial. What is *not* trivial is that writing one does
nothing on its own. The visible shape comes from a stack of macro *targets* — shape keys named
`$md-...` — that MPFB recomputes from the properties by interpolating between corner cases
(`macrodetails/caucasian-female-young`, `macrodetails/universal-male-old-averagemuscle-maxweight`,
…) and loading each one it needs from disk. `TargetService.reapply_macro_details()` is that
recalculation, and MPFB's own sliders do exactly three things: write the property, call it, and
optionally refit.

Changing a character's shape also invalidates everything fitted to it. MPFB's model panel exposes
that as an "Auto refit assets" toggle which is **off** by default, plus a manual refit button — the
refit walks every clothes and proxy object and re-runs the vertex fit, which is expensive enough
that MPFB does not want it on every slider drag. mpfb-mcp inherits that split, which means a refit
tool has to exist for the default to be defensible.

## Goals

Primary: let a caller read a character's current macro details, change any subset of them, and have
the shape actually update — with the same result MPFB's own phenotype sliders would produce.

Secondary: make the *consequences* of a change visible rather than implicit. A macro change moves
the body under any clothes fitted to it and under the rig; the response should say so, and there
should be a way to act on it without leaving the tool layer.

Also: settle the question [NEXT_STEPS.md](../../NEXT_STEPS.md) raises about `mpfb_create_human`'s
parameter shape, and record the answer, so it stops being an open question.

## Functional requirements

Three tools.

### `mpfb_get_macro_details`

Read-only, always answers. Arguments:

- `name` (optional string) — a Blender object name. Omitted means the active object, per
  [How generated code addresses objects](../../../specifications/architecture.md#how-generated-code-addresses-objects).

`result` carries:

- `basemesh_name` — the object the values were actually read from, and `subject_resolved_by`
  (`"name"` / `"active"`). The argument may name a rig, a shirt or the basemesh itself; the payload
  resolves to the related basemesh, and the response says which object that turned out to be.
- `found` (bool) and `message` — an unresolvable name or "nothing is active" is a successful answer,
  not an error, the stance [FR 001](../001-mpfb-get-status/README.md) and
  [FR 003](../003-object-finding/README.md) established.
- `macro_details` — the current values, in exactly the nested shape `TargetService` uses
  (`{"gender": …, …, "race": {"asian": …, "caucasian": …, "african": …}}`), read through
  `get_macro_info_dict_from_basemesh()` rather than by reading the properties by hand.
- `default_macro_details` — `TargetService.get_default_macro_info_dict()`. Requested explicitly in
  [NEXT_STEPS.md](../../NEXT_STEPS.md), and worth having beside the current values: it is what "neutral"
  means, and it is the only way for a caller to tell a deliberately-average character from a default
  one without hardcoding 0.5.
- `race_sum` and `race_normalized` (bool) — see the race note under Architecture. MPFB does not
  normalize the three race weights, and a caller that sets one to 1.0 and leaves the others at 0.33
  gets a phenotype built from weights summing to 1.66. Reporting the sum is how that stops being
  invisible.
- `macro_target_stack` — the `[name, weight]` list
  `TargetService.calculate_target_stack_from_macro_info_dict()` derives from the current values, and
  `macro_target_count`. This is what the sliders *mean* in target terms, and it is the only way to
  explain why a change did or did not move anything.
- `current_macro_shapekeys` — what is actually on the mesh right now, from
  `get_current_macro_targets(decode_names=True)`, with the decoded names. Reported beside the
  derived stack deliberately: if the two disagree, the character's properties and its shape have
  drifted apart, which is exactly the state `mpfb_set_macro_details` repairs.
- `is_human_project` (bool) and `has_shapekeys` (bool) — an imported mesh with no shape keys reads
  back a full set of macro properties that mean nothing, and this is what distinguishes it.

### `mpfb_set_macro_details`

Mutating. Arguments — **flat and all optional**, an omitted one meaning "leave unchanged":

- `name` (optional string) — subject, as above.
- `gender`, `age`, `muscle`, `weight`, `proportions`, `height`, `cupsize`, `firmness`,
  `race_asian`, `race_caucasian`, `race_african` (optional floats, 0.0–1.0) — the same names and
  the same range `mpfb_create_human` already uses.
- `prune` (optional bool, default `true`) — passed to `reapply_macro_details()` as
  `remove_zero_weight_targets`. MPFB's own default; leaving it on keeps the shape key list from
  growing without bound as sliders move.
- `refit` (optional bool, default `false`) — MPFB's own default too. See `mpfb_refit_human` below.

`result` carries `basemesh_name`, `subject_resolved_by`, `message`, and:

- `changed` — one entry per property the call actually altered, each `{name, previous, new}`.
  Properties the caller did not name do not appear; a property set to the value it already had
  appears with `previous == new`, which is not the same claim as not being mentioned at all.
- `macro_details` — the full dict after the change, in the same shape `mpfb_get_macro_details`
  returns, so the two round-trip.
- `race_sum`, `race_normalized` — as above, recomputed after the change.
- `macro_shapekeys_before`, `macro_shapekeys_after` and `shapekeys_removed` / `shapekeys_added` —
  the visible effect of the recalculation. With `prune` on, a macro target that fell below 0.0001 is
  deleted, and a caller comparing two `mpfb_get_target_stack` calls would otherwise see shape keys
  vanish with no explanation.
- `refit_performed` (bool) and, when it was not, `assets_possibly_stale` — the count of fitted mesh
  assets and whether a rig is attached. A `false` here is the tool telling the caller it has work
  left to do; see the non-functional requirement about not hiding consequences.

If nothing was named, the tool must not recalculate: it answers `changed: []` with a `message`
saying so, rather than silently doing a full macro reapply. A no-op call is a common agent mistake
and it should be cheap and obvious rather than a several-second shape rebuild.

### `mpfb_refit_human`

Mutating, wraps `HumanService.refit()`. Arguments: `name` (optional string). Reports which basemesh
and rig were found, how many mesh assets and subrigs were refitted, and — the case that matters —
the generated-Rigify-with-no-metarig situation, which `refit()` reports through an `operator` it
will not have here and otherwise passes over in silence. (Reading `humanservice.py` while
implementing corrected this: the mesh assets are refitted *before* the rig block is reached, so what
`refit()` silently skips in that case is the **rig**, not everything. The implemented tools
therefore still call `refit()` — the garments do need refitting — and report `refit_performed:
false` with a `refit_incomplete_reason` naming the rig, rather than refusing to call it at all.)

Suggested as in scope rather than requested in [NEXT_STEPS.md](../../NEXT_STEPS.md). The justification is
that `refit` defaults to `false` on both mutating tools in this request and on
[FR 008](../008-detail-targets/README.md)'s: without a standalone refit, that default leaves an agent
able to deform a dressed character and no way to fix it. The alternative — defaulting `refit` to
true — pays a full asset refit on every one of the twenty slider changes a modeling session makes.

**Not in scope.** Detail targets, which are [FR 008](../008-detail-targets/README.md);
`mpfb_get_human_summary`, which is a wider read spanning assets, skin and rig and which should
*call into* the same macro read rather than duplicate it; expressions and visemes (`!ex-` shape
keys), which are neither macro nor modeling targets; randomization, which MPFB now has a whole
`RandomizationService` for and which deserves its own request; and changing `is_human_project`.

## Non-functional requirements

- **The same result MPFB's own sliders produce.** The single most important attribute here. A
  character modified through this tool and the same character modified through MPFB's phenotype
  panel must end up with the same shape keys at the same weights. That means calling
  `reapply_macro_details()`, not reimplementing the interpolation — the corner-case naming, the
  0.01 cutoff and the encoded `$md-` names are MPFB's business and would drift the moment MPFB
  changes them.
- **Consequences must be visible, not implicit.** This is the read-only projects' "an empty answer
  must never be ambiguous", restated for mutation: a tool that changes a body under fitted clothes
  and says nothing has told the caller something false by omission. Hence `refit_performed`,
  `assets_possibly_stale` and the removed/added shape key lists.
- **Idempotent and re-runnable.** Calling with the same values twice must be a no-op in effect.
  `reapply_macro_details()` is written to be re-entrant, and the tools must not add state of their
  own that breaks that.
- **Preconditions are answers, not tracebacks.** Wrong object type, no shape keys, not in OBJECT
  mode — each is a thing an agent will hit, and each should come back as a plain sentence naming the
  problem. See the Architecture pitfalls.
- **Restore what was borrowed.** If the payload activates an object (see below), it must put the
  previous active object and selection back. The user is looking at this scene.

## Architecture

- Three tool modules under [`src/mpfbmcp/tools/`](../../../src/mpfbmcp/tools), three payloads under
  [`src/mpfbmcp/codegen/payloads/`](../../../src/mpfbmcp/codegen/payloads), three `register()` calls in
  [`__init__.py`](../../../src/mpfbmcp/__init__.py). Nothing shared is edited, per
  [the code-generation layout](../../../specifications/architecture.md#code-generation-layout).
- **Raising bootstrap** (`bootstrap="raising"`) for all three. `TargetService`, `HumanService` and
  `ObjectService` are all in the `SERVICES` dict.
- **`HumanObjectProperties` is not a service.** It is a `BlenderConfigSet` living on
  `mpfb.entities.objectproperties`, reached as
  `getattr(sys.modules[HumanService.__module__], "HumanObjectProperties", None)` — the convention in
  [Reading module-level names MPFB does not publish](../../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish),
  and already done exactly this way in
  [`payloads/get_object_info.py`](../../../src/mpfbmcp/codegen/payloads/get_object_info.py). Prefer
  `TargetService.get_macro_info_dict_from_basemesh()` for reading anyway; the property set is only
  needed for *writing*.
- **Writing a property is only the first of two steps.** `HumanObjectProperties.set_value(...)`
  changes a number; the mesh does not move until `TargetService.reapply_macro_details(basemesh,
  remove_zero_weight_targets=prune)` runs. `mpfb/ui/model/_macrosubpanel.py`'s
  `_general_set_target_value()` is the reference implementation and is nine lines long — follow it.
  Write **every** named property first, then recalculate **once**; recalculating per property would
  be N times the work for the same result.
- **Use `reapply_macro_details()`, never `reapply_all_details()`.** The latter also tears down and
  reloads the *detail* target stack from disk, resolving each entry through
  `TargetService.target_full_path()`. Two things go wrong there: a shape key whose name was encoded
  (over 60 characters) will not resolve back to a file and is dropped with only a log warning, and
  `target_full_path()` falls back to a *prefix* match, so a near-miss silently loads a different
  target. Macro changes do not require detail targets to be reloaded at all.
- **Subject resolution.** `ObjectService.find_object_of_type_amongst_nearest_relatives(obj,
  "Basemesh")` — the same call MPFB's own panels make. This is what lets a caller pass the name of
  the rig or of a shirt, which is what `mpfb_list_objects` will have shown them. Resolve the active
  object as `bpy.context.view_layer.objects.active`, per
  [How generated code addresses objects](../../../specifications/architecture.md#how-generated-code-addresses-objects),
  and treat `None` as an ordinary answer.
- **Validate the sliders locally, because MPFB does not.** The property definitions in
  `entities/objectproperties/humanproperties/*.json` carry a `default` but **no `min`/`max`**, and
  `BlenderConfigSet._create_property_by_type()` only passes those through when present — so the
  object properties are unclamped, and it is the *scene-level* proxy property in
  `_macrosubpanel.py` that carries `min=0.0, max=1.0`. A value of 5.0 will be stored happily and
  produce an interpolation the macro table has no corner cases for. Reject outside 0.0–1.0 in the
  tool module, as `mpfb_create_human` already does, per
  [Validate before crossing the socket](../../../specifications/architecture.md#validate-before-crossing-the-socket).
- **The race weights are not normalized, and must not be normalized here.** MPFB treats `asian`,
  `caucasian` and `african` as three independent 0–1 properties — the default is 0.33 each, summing
  to 0.99, and `calculate_target_stack_from_macro_info_dict()` multiplies each race's raw value
  straight into the target weight. Normalizing in mpfb-mcp would produce a character that MPFB's own
  sliders cannot reproduce, which violates the first non-functional requirement. Report `race_sum`
  and let the caller decide; say in the docstring that the three are independent and that setting
  one does not reduce the others.
- **Pitfall — OBJECT mode is asserted, not checked.** `TargetService.create_shape_key()` begins with
  `assert blender_object.mode == "OBJECT"`, and `reapply_macro_details()` reaches it whenever it
  needs to load a macro target that is not present yet. If the user left the basemesh in edit mode,
  the payload gets a bare `AssertionError` with no message. Check `basemesh.mode` up front and
  answer with a sentence instead.
- **Pitfall — `reapply_macro_details()` on a mesh with no shape keys.** It logs a warning
  ("Basemesh has no shape keys at this point. This is somewhat surprising.") and carries on. That
  happens on an imported mesh tagged as a basemesh but never built by `create_human()`. Check
  `TargetService.has_any_shapekey()` first — it is what MPFB's own macro panel polls on — and report
  it rather than producing a confusing partial result.
- **Activation.** `_general_set_target_value()` calls
  `ObjectService.activate_blender_object(basemesh)` before recalculating. Nothing in
  `reapply_macro_details()` obviously requires it — it uses `shape_key_add` / `shape_key_remove`,
  not `bpy.ops` — but `HumanService.refit()` *does* reach `bpy.ops.object.mode_set` through
  `ClothesService.fit_clothes_to_human()`, which needs the clothes object active (that function sets
  and restores it itself). Follow MPFB and activate, then restore the previous active object and
  selection before returning. `bpy.ops` is known to work in this execution context —
  `create_human()` already calls `bpy.ops.object.transform_apply` through
  [`payloads/create_human.py`](../../../src/mpfbmcp/codegen/payloads/create_human.py).
- **`refit()`'s silent branch.** When the rig is a generated Rigify rig with no meta rig in the
  scene, `HumanService.refit()` logs a warning, calls `operator.report()` if it was given an
  operator, and **returns having refitted the mesh assets but not the rig** — the asset loop runs
  first, and only `RigService.refit_existing_armature()` raises. There is no operator here. Detect
  the condition before calling — a `Skeleton` relative for which
  `ObjectService.object_is_generated_rigify_rig()` is true and `find_rigify_metarig_by_rig()` finds
  nothing — and report it, or the tool will cheerfully answer `refit_performed: true` over a rig it
  did not touch. Detecting it is *not* a reason to skip the call: the garments still need
  refitting, so the implementation calls `refit()` and reports the partial outcome.
- **`macro_target_stack` entries are file fragments, not shape key names.**
  `calculate_target_stack_from_macro_info_dict()` returns names like
  `macrodetails/caucasian-female-young`; the shape key MPFB creates from one is
  `macrodetail_filename_to_shapekey_name(name, encode_name=True)`, e.g. `$md-$ca-$fe-$yn`. Report
  both, and never present the fragment as something `mpfb_set_target_value` could be given — the
  distinction is the one
  [How tools name things that can be added](../../../specifications/architecture.md#how-tools-name-things-that-can-be-added)
  exists for.
- Response envelope unchanged: return `send_code(...)` as-is with `strict_json=True`.

### The `mpfb_create_human` parameter-shape question

[NEXT_STEPS.md](../../NEXT_STEPS.md) asks whether `mpfb_create_human` should stop taking eleven flat
sliders and take a macro-detail dict instead. **Decided: it should not.** Flat scalar parameters are
what an MCP tool schema describes and validates well, and what a client fills in reliably; a nested
dict-of-dict argument is a shape an LLM gets subtly wrong (misspelling `race`, omitting a key,
nesting `cupsize` under `race`) and which forces per-field validation into a hand-written dict walk.

`mpfb_set_macro_details` therefore takes the **same eleven flat names**, with the difference that
every one is optional and an omitted one means "leave unchanged" — a distinction a dict cannot
express without a sentinel. Round-tripping is preserved on the *output* side instead: both tools
return the full nested `macro_details` dict in `TargetService`'s own shape, so a caller can read a
character, hand the dict to something else, and map it back onto flat arguments mechanically.

This decision should be folded into
[architecture.md](../../../specifications/architecture.md#validate-before-crossing-the-socket) when the
work lands, since it is a general statement about tool signatures rather than about macro details.

## Affected specifications

- [vision.md](../../../specifications/vision.md#target-tool-catalog) — `mpfb_set_macro_details` is
  already listed under "Creation and modification"; mark it **Implemented** and describe what it
  actually does. `mpfb_get_macro_details` and `mpfb_refit_human` are **new entries** and need adding
  (the former under "Introspection (read-only)"). The `mpfb_get_human_summary` entry should be
  amended to say the macro-detail half of its answer is this tool's, so the two do not diverge.
- [architecture.md](../../../specifications/architecture.md) — one convention to follow and three
  candidate additions.
  - **To follow:**
    [How generated code addresses objects](../../../specifications/architecture.md#how-generated-code-addresses-objects)
    and
    [Validate before crossing the socket](../../../specifications/architecture.md#validate-before-crossing-the-socket).
  - **New — how a mutating tool takes its subject.** Everything so far has been read-only. The rule
    worth recording: a mutating tool accepts any object in the character's family and resolves to
    the object it will actually modify through
    `find_object_of_type_amongst_nearest_relatives()`, and the response names that object rather
    than echoing the argument. An agent that got a name out of `mpfb_list_objects` should not have
    to know which member of the family owns the property being changed.
  - **New — a mutating tool reports before and after.** Enough of the prior state to verify the
    change without a second round trip, and enough of the *consequences* (stale asset fits, removed
    shape keys) that a caller is not misled by silence. This is the mutation-side counterpart of
    "an empty answer must never be ambiguous".
  - **New — preconditions are answers.** OBJECT mode, presence of shape keys, object type: check
    them in the payload and return a sentence, rather than letting MPFB's `assert` or a `ValueError`
    come back as a traceback in an error envelope. Related to, but distinct from,
    [FR 001](../001-mpfb-get-status/README.md)'s "absence is an answer": here the *request* is
    well-formed and the *world* is not ready.
  - The flat-parameters-over-dicts decision above, probably as a clause under
    [Validate before crossing the socket](../../../specifications/architecture.md#validate-before-crossing-the-socket).

## Tests

Two layers, as established: argument validation with each tool module's `send_code` mocked, then the
generated source `exec()`d against stubs in [tests/blender_stubs.py](../../../tests/blender_stubs.py).

The stubs need a `StubTargetService` with the macro half of the real one — this repo already has one
for the name-encoding half, added by [FR 006](../006-list-targets/README.md), and it should be
extended rather than duplicated. Reproduce behavior, not convenience:

- `get_macro_info_dict_from_basemesh()` reading from the same stub property store
  `set_value()` writes to, so the write-then-read round trip is genuinely under test.
- `reapply_macro_details()` that actually *removes* stub shape keys below 0.0001 when
  `remove_zero_weight_targets` is true and adds the ones the derived stack calls for, since
  `shapekeys_removed` / `shapekeys_added` are otherwise asserted against nothing.
- A stub `HumanObjectProperties` that stores whatever it is given **without clamping**, matching the
  unclamped real property — a stub that clamps would hide the reason the tool validates locally.
- A stub basemesh with `mode` settable, so the edit-mode precondition is tested rather than assumed,
  and one with no shape keys at all.
- A `create_shape_key` stand-in that asserts on non-OBJECT mode exactly as MPFB's does.

Cases worth naming: an omitted parameter leaves the property untouched (not "sets it to its
default"); a value equal to the current one appears in `changed` with `previous == new`; a call
naming nothing recalculates nothing; out-of-range values are rejected in the tool module before any
code is generated; race weights are stored raw and `race_sum` reflects it; the subject resolves from
a rig name and from a clothes name, not only from the basemesh's own; and the generated-Rigify
no-metarig branch reports rather than claiming a refit.

**Live verification against a running Blender is required**, and this is the first request where the
verification is of *mutation*, so the FR 004–006 discipline of reverting everything applies in full
(snapshot every datablock collection, compare after, never save the `.blend`). Specifically:

- That a character modified through `mpfb_set_macro_details` ends up with the **same shape keys at
  the same weights** as the same character modified through MPFB's own phenotype sliders. Set the
  slider in the UI, snapshot; undo; set it through the tool; compare. This is the whole point of the
  request and nothing on this side of the socket can establish it.
- That the properties and the mesh are actually in sync afterwards — `macro_target_stack` derived
  from the new values matches `current_macro_shapekeys` read off the mesh.
- That `prune` genuinely removes macro shape keys, and that with `prune: false` they accumulate.
- That a refit after a macro change visibly re-fits clothes: change gender or weight substantially
  on a dressed, rigged character, confirm the clothes are wrong, refit, confirm they are right.
- The edit-mode and no-shape-keys preconditions, observed rather than inferred.
- The generated-Rigify-without-metarig branch, since it is the one failure `refit()` reports only
  through a channel this layer does not have.
- Cost, against FR 005's ~1.0 s socket round-trip baseline: how long a single macro change takes with
  and without prune, and how long a refit takes on a character with several clothes items. The refit
  default rests on that number being large.

Record the outcome in a `## Verification status

**Implemented, unit-tested and live-verified (2026-09-01)**, by
[FR 013](../013-live-verification/README.md)'s session, against Blender 5.1.0 with MPFB 2.0.17
running `FROM_SOURCE` out of `../mpfb2`. This request landed on 2026-08-29 without that check;
what follows is what running it actually established, and it is now a script rather than a
session: [verification/check_fr007.py](../../../verification/check_fr007.py).

Every scene mutation was reverted — all twelve datablock collections plus `bpy.data.is_dirty`
compare **identical** before and after, and the `.blend` was never saved.

### What changed against this request

**The first non-functional requirement is met exactly, and it was automatable after all.** This
request wrote the check as "set the slider in the UI, snapshot; undo; set it through the tool;
compare", which reads like an eyeballing exercise. It is not: MPFB's phenotype panel draws
`scene.mpfb_macropanel_<target>`, a `FloatProperty` whose setter writes the object property,
calls `TargetService.reapply_macro_details()` and optionally refits. Assigning that scene property
*is* moving the slider. Two fresh characters — one driven through that property, one through
`mpfb_set_macro_details`, with `gender=0.9, age=0.75, weight=0.7` — ended with **21 shape keys
each, the same 21 names at the same values to six decimal places**, no key present in one and not
the other. Two characters rather than one-then-undone, because there is no undo across this
socket.

**One defect was found and fixed** ([FR 013](../013-live-verification/README.md)'s
[review](../013-live-verification/review.md)). `macro_target_stack[].shapekey_name` was
reported **encoded** (`$md-$as-$fe-$yn`) while `current_macro_shapekeys` was reported **decoded**
(`macrodetail-asian-female-young`), and the docstring told a caller to compare the two and read a
difference as drift. The comparison could never succeed on any character. Both now report the
names the shape keys are stored under, `mpfb_get_macro_details` gains
`current_macro_shapekeys_decoded` for reading, and `mpfb_set_macro_details`'
`macro_shapekeys_before`/`_after`, `shapekeys_added` and `shapekeys_removed` moved the same way,
so a name in any of them can be looked up on the mesh. Regression tests in
`tests/test_get_macro_details.py` and `tests/test_set_macro_details.py`.

**The refit costs almost as much as the macro change it follows**, which the request assumed but
did not know: a macro change with `refit: false` is ~1.26 s and a bare `mpfb_refit_human` on an
undressed character is ~0.76 s, against a socket round trip that is itself most of the latter.
See [FR-8's measurements](../013-live-verification/review.md#do-the-three-payload-count-driven-decisions-still-hold).

### Checklist

- [x] **The same shape keys at the same weights as MPFB's own phenotype slider.** 21 keys each,
      identical names, identical values; `only_in_ui` and `only_in_tool` both empty and
      `differing_values` empty.
- [x] Properties and mesh in sync — 42 entries in `macro_target_stack`, 42 macro shape keys on the
      mesh, the two sets equal. (Equal only *after* the naming fix above; before it, the two lists
      shared no element.)
- [x] `prune` genuinely removes macro shape keys and `prune: false` keeps them: 9 keys before, 9
      after a `prune: false` change with four of them at zero weight, 5 after the same change with
      `prune: true` and none at zero. The four removed are named in `shapekeys_removed`.
- [x] An omitted slider is left alone rather than defaulted — `gender` and `age` unchanged across a
      call that named only `muscle`.
- [x] The OBJECT-mode precondition, observed: `ready: false`, `blocked_by: "not_object_mode"`, and
      nothing changed. MPFB's own `create_shape_key()` meets this with a bare `assert`.
- [x] The no-shape-keys precondition, observed on a basemesh whose keys were cleared by hand:
      `ready: false`, `blocked_by: "no_shapekeys"`.
- [x] **A refit visibly re-fits clothes on a dressed, rigged character** — observed in
      [FR 010's run](../010-mesh-assets/README.md#verification-status) rather than here, since that
      is where the dressed character exists. A macro change with `refit: false` leaves the garment's
      vertex fingerprint at `733.5443`; `mpfb_refit_human` moves it to `734.1956` and reports
      `refit_performed: true`. This is the first live evidence that the refit does anything at all.
- [x] **The generated-Rigify-without-meta-rig branch** — observed in
      [FR 009's run](../009-add-rig/README.md#verification-status), which is where a generated rig
      exists. `meta_rig_action: "delete"` gives `refit_will_be_possible: false`, and the following
      `mpfb_refit_human` returns `refit_performed: false` with a `refit_incomplete_reason` naming
      the generated rig — while still reporting the one mesh asset it *did* refit. The corrected
      premise holds: the mesh assets are refitted and the rig is not.
- [x] Cost against a re-measured baseline: macro change with `prune: true` 1265 ms (median of 3),
      with `prune: false` 1263 ms — pruning is free at this size — with `refit: true` 1268 ms, and
      `mpfb_refit_human` alone 759 ms.
- [x] Revert: all twelve datablock collections identical, `is_dirty` false before and after.

### What this run could not establish

Nothing on this checklist. The two items marked as observed elsewhere were observed, not inferred;
they are recorded under the request whose fixture produced them so that a re-run of *that*
checklist re-establishes them.

## References

- MPFB `services/targetservice.py` — `get_default_macro_info_dict()`,
  `get_macro_info_dict_from_basemesh()`, `calculate_target_stack_from_macro_info_dict()`,
  `get_current_macro_targets()`, `reapply_macro_details()` (and `reapply_all_details()`, which this
  request deliberately avoids), `macrodetail_filename_to_shapekey_name()`.
- MPFB `ui/model/_macrosubpanel.py` — the reference implementation of a macro slider:
  `_general_set_target_value()` and `_general_get_target_value()`, and the `_MACROTARGETS` grouping
  the tool's parameter names should stay consistent with.
- MPFB `ui/model/modelpanel.py` and `ui/model/properties/` — the `prune`, `refit`, `symmetry`,
  `only_active` scene settings and their defaults (`prune` true, the other two false).
- MPFB `services/humanservice.py` — `create_human()` (the same write-then-reapply sequence, at
  creation time) and `refit()`.
- MPFB `entities/objectproperties/humanproperties/*.json` — the eleven property definitions, their
  defaults, their descriptions (worth lifting into the tool docstring: age 0.0=baby, 0.1875=child,
  0.5=young, 1.0=old is not guessable) and their conspicuous lack of `min`/`max`.
- MPFB `services/blenderconfigset.py` — `_create_property_by_type()`, which is why that lack matters.

## Verification status

**Implemented and unit-tested; live verification is outstanding.** The three tools, their payloads
and their tests landed together, and the whole suite passes — 278 tests, up from 208 — but unlike
[FR 001](../001-mpfb-get-status/README.md) through [FR 006](../006-list-targets/README.md), this
request was **not** checked against a running Blender before being marked Done. That was a
deliberate scoping decision, not an oversight, and it matters more here than it would have for the
read-only tools: these are the first tools that *change* a character, and the request's own first
non-functional requirement — that a character modified through `mpfb_set_macro_details` ends up
identical to one modified through MPFB's phenotype panel — is precisely the claim nothing on this
side of the socket can establish.

What the unit tests do establish is the branching around the call: subject resolution from a rig
and from a garment, the preconditions, that an omitted slider is left alone rather than defaulted,
that a slider set to its current value is still reported, that a call naming nothing recalculates
nothing, that every property is written before a *single* recalculation, that race weights are
stored raw, that pruning removes shape keys and that `prune: false` keeps them, that the active
object and the selection are restored even when the refit raises, and that the
generated-Rigify-without-metarig case is reported rather than claimed. The stubs reproduce MPFB's
behavior for all of that — an unclamped property store, a `reapply_macro_details()` that really
adds and removes shape keys, a `create_shape_key()` that asserts on non-OBJECT mode — with one
deliberate exception: the macro interpolation itself is a stand-in table rather than MPFB's corner
cases, since no payload depends on which targets come out.

**Still to be done, against a running Blender**, in the request's own words:

- That a character modified through `mpfb_set_macro_details` ends up with the **same shape keys at
  the same weights** as the same character modified through MPFB's own phenotype sliders. Set the
  slider in the UI, snapshot; undo; set it through the tool; compare.
- That the properties and the mesh are in sync afterwards — the derived `macro_target_stack`
  matching `current_macro_shapekeys`.
- That `prune` genuinely removes macro shape keys, and that with `prune: false` they accumulate.
- That a refit after a macro change visibly re-fits clothes on a dressed, rigged character.
- The edit-mode and no-shape-keys preconditions, observed rather than inferred.
- The generated-Rigify-without-metarig branch, including the corrected premise above: that the mesh
  assets *are* refitted while the rig is not.
- Cost against [FR 005](../005-list-assets/README.md)'s ~1.0 s socket round-trip baseline: a macro
  change with and without prune, and a refit on a character with several clothes items. The refit
  default rests on that number being large.

The FR 004–006 discipline applies in full when that run happens, and more strictly, since this is
mutation: snapshot every datablock collection, compare after, restore the active object, never save
the `.blend`.
