# Mutating tools

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

**Tools that change a character.** Everything a read-only tool owes its caller
([responses.md](responses.md)) still applies; this document is the additional obligations that
come with changing something the caller cannot undo across the socket.

They fall into a sequence: take the subject, check that the world is ready, do only what was
asked, put back what was borrowed, and report what changed — including what changed as a
consequence, and what the change has now invalidated. Two further sections cover the cases MPFB
makes hard: an ordering constraint nothing enforces, and a batch that must be all-or-nothing.

## How a mutating tool takes its subject

A tool that changes a character accepts **any object in that character's family** — the basemesh,
its rig, a garment fitted to it — and resolves from there to the object it will actually modify,
through `ObjectService.find_object_of_type_amongst_nearest_relatives()`. That is the same call
MPFB's own panels make, and the reason for it is
[how tools name things](tool-interface.md#how-generated-code-addresses-objects):
an agent got the name it is holding out of `mpfb_list_objects`, which does not say which member
of a family owns a given property.
Requiring the caller to know that would make every mutating tool need a lookup step first.

- **The response names the object that was modified, not the argument.** `basemesh_name` beside
  `subject_name`, so a caller that passed a rig can see what the change actually landed on.
- **The walk is MPFB's, not a reimplementation.** It descends through children, ascends through
  parents, and takes each parent's other branches on the way — which is what finds a garment from
  the basemesh on a rigged character, since MPFB parents garments to the *rig*.
- **The object resolved to is not always the basemesh.** It is for every phenotype and modeling
  tool, and for `mpfb_add_rig`, because that is what carries what they change. It is not for
  `mpfb_generate_rigify_rig`, which narrows to the character's `Skeleton` and then asks
  `RigService.identify_rig()` which kind it found — the meta rig is the thing being operated on.
  Resolve to whatever owns the change, name it in the response (`metarig_name` rather than
  `basemesh_name` there), and take the subject from anywhere in the family either way.
- **A narrowing step can need the whole set rather than the first match.**
  `find_object_of_type_amongst_nearest_relatives()` returns one object; where two objects of the
  same MPFB type mean different things, take them all and classify. After Rigify generation a
  character's `Skeleton` relative is the *generated* rig, since `adjust_children_for_rigify()`
  re-parents the character onto it — so "already generated" and "that is not a meta rig" are
  different answers that a single lookup could not tell apart.
- **Failing to resolve is an answer**, `found: false` with a sentence, exactly as for the read-only
  tools.

## A mutating tool reports before and after

The mutation-side counterpart of "an empty answer must never be ambiguous": a tool that changes
something and reports only that it succeeded has told the caller very little, and a tool that
changes something with side effects and mentions none of them has told the caller something false
by omission.

- **Report the prior value beside the new one**, per changed field, so the change is verifiable
  without a second round trip — and report a field the caller named even when the value it already
  had was the one requested. "You asked for this and it was already so" is not the same claim as
  not mentioning it.
- **Report what changed as a consequence**, not only what was asked for. `mpfb_set_macro_details`
  returns the macro shape keys before and after, and the removed and added lists, because pruning
  deletes shape keys the caller never mentioned and would otherwise see vanish unexplained.
- **Report what is now stale.** Changing a body's shape invalidates the fit of everything on it,
  and MPFB's own auto-refit defaults to off. So the tool reports `refit_performed`, and when it is
  false, what is left needing attention (`assets_possibly_stale`) and which tool addresses it. An
  expensive default left off is defensible only when the response says what it left undone.
- **Do only what was asked.** A call that names nothing to change must not "helpfully" recalculate:
  it answers immediately, saying that nothing was named. A no-op is a common agent mistake, and a
  full macro rebuild costs seconds.
- **Restore what was borrowed.** Where the payload has to activate or select an object to do its
  work — MPFB's own slider callback does — put the previous active object and selection back, in a
  `finally`, so a failure part-way through does not leave the user's scene rearranged. Where it
  genuinely *cannot* — `RigService.generate_rigify_rig()`'s own final act is to select and activate
  the rig it produced, so there is no state left to restore to — say what the selection now is
  (`active_object_after`) rather than quietly leaving the caller to assume nothing moved.

## Preconditions are answers

Related to, but distinct from, [FR 001](../feature-requests/done/001-mpfb-get-status/README.md)'s
"absence is an answer": there the request named something that is not there, while here the request
is well-formed and the **world** is not ready. Check in the payload and return a sentence naming the
problem, rather than letting MPFB's own guard surface as a traceback in an error envelope.

- **OBJECT mode.** `TargetService.create_shape_key()` opens with a bare `assert
  blender_object.mode == "OBJECT"`, reached whenever a macro target has to be loaded. An
  `AssertionError` with no message is the worst possible form of a very ordinary situation: the
  user left the mesh in edit mode.
- **Presence of shape keys.** `reapply_macro_details()` on a mesh with none logs "somewhat
  surprising" and carries on, producing a partial result. It is what an imported mesh tagged as a
  basemesh looks like, and it should be reported as that rather than half-done.
- **Reachability of what the payload needs**, such as a property set read off a service's module
  (see [Reading module-level names MPFB does not publish](architecture.md#reading-module-level-names-mpfb-does-not-publish)).
- **A vocabulary MPFB validates *after* it destroys something.** This is the sharpest case, and it
  is the one exception to
  [validate the shape, never the vocabulary](tool-interface.md#validate-before-crossing-the-socket).
  `HumanService.set_character_skin()` opens with
  `MaterialService.delete_all_materials(..., also_destroy_groups=True)` on the basemesh and the body
  proxy, and only then tests its five skin types — with five separate `if` statements rather than a
  chain with an `else`. An unrecognised value therefore deletes the character's materials, builds
  nothing, and surfaces as a `ValueError` raised from `create_and_assign_material_slots()` about a
  mesh with no materials: a traceback from a function that never saw the bad argument, after damage
  that cannot be undone across the socket. Where a vocabulary is checked late and the check is
  preceded by destruction, check it in the payload first — and, where the vocabulary is small,
  closed and MPFB's own enum rather than a scan of the user's disk, check it in the tool module too,
  so a typo never crosses the socket at all. Report `known_*` alongside either way: the local check
  is belt and braces, and the authoritative answer still comes from Blender.

Report which precondition blocked (`ready: false` plus a `blocked_by` naming it) rather than only a
sentence, so a caller can branch on it; and make sure the tool changed nothing on the way to
finding out.

## A tool reports an ordering constraint it cannot enforce

MPFB's services have **implicit sequencing**, and violating it produces no error anywhere. The rig
has to be added before the mesh assets, because `HumanService.add_mhclo_asset()` rigs a garment only
if a `Skeleton` relative exists at the moment the garment is attached and nothing re-rigs it
afterwards — `HumanService.refit()` deliberately passes `set_parent=False`. Rigify generation has to
come after the mesh assets, because `RigifyHelpers.adjust_children_for_rigify()` handles exactly
what is on the character when it runs. MPFB's own character builder documents both in comments, and
its randomizer follows them; nothing enforces them. An agent that dresses a character and then rigs
it gets clothes that do not follow the armature, and finds out when someone moves a bone.

No single call can validate a sequence. But a tool can often *observe* that the caller is about to
break one, and where it can, **it reports the observation in its response, naming the objects
affected** — rather than either failing or staying silent.

- **Report, do not refuse.** Rigging an already-dressed character is a legitimate thing to do when
  the clothes are decorative. `mpfb_add_rig` adds the rig and returns `mesh_assets_not_rigged`
  listing what it has just failed to rig; it does not second-guess the caller.
- **Name the objects, not the rule.** "Some assets may not be rigged" is advice; `["Shirt",
  "Shoes"]` is something an agent can act on. This is the sequencing counterpart of
  [an empty answer must never be ambiguous](responses.md#how-tools-report-the-asset-behind-an-object).
- **Observe before acting, so the claim is precise.** The assets are enumerated *before* the rig is
  added. Afterwards they are still reachable, but the answer would then be "assets on this
  character" rather than "assets that were attached while there was no rig".
- **A half-finished sequence must look half-finished.** `mpfb_add_rig` on a `rigify.*` identifier
  produces only a meta rig, so it returns `is_metarig: true` and a `next_step` naming
  `mpfb_generate_rigify_rig` and saying that assets come first. "The rig was added" must not read as
  "the character is rigged".
- **Where a step forecloses a later one, say so at the point of decision.**
  `mpfb_generate_rigify_rig`'s `meta_rig_action: "delete"` leaves a character that can never be
  refitted again, which `mpfb_refit_human` can only report after the fact. `refit_will_be_possible`
  is that same fact, knowable in advance.
- **Splitting a tool can be what makes the order expressible.** Rigify generation is a tool of its
  own rather than a flag on `mpfb_add_rig` precisely because the correct order — meta rig, then
  clothes, then generate — cannot be written as a single call.

## A batched mutating tool resolves before it writes

Where a tool changes many things at once, **every entry is resolved and validated before anything
is written, and if any entry fails, none of them are applied.**

- **A half-applied batch is a state nothing can describe.** Thirty changes with one typo in them
  must apply zero, not twenty-nine: the character is then in a condition neither the agent nor the
  user can name, and the response format cannot usefully say which half landed or which half to
  retry. Failing the whole batch leaves the caller with one action — fix the entry and resend.
- **Resolve the expensive, failure-prone part up front.** For `mpfb_set_targets` that means
  locating the file each change *might* have to load, during resolution, so a missing target is a
  `resolution_errors` entry rather than an `IOError` raised half way through the writes.
- **Report per entry once application starts**, in request order, including what changed as a
  consequence — one sided change with `symmetry` on touches up to four shape keys, and the response
  has to be able to say so.
- **Batch because per-call cost dominates, not on principle.** A socket round trip costs about
  250 ms — measured by [FR 013](../feature-requests/done/013-live-verification/README.md), which
  also retired the ~1.0 s figure this decision was originally argued against — while setting a
  modeling target costs milliseconds. Transport alone would make thirty calls 7.5 s of waiting for
  a fraction of a second of work. The measured gap is far larger: thirty modifier changes cost
  3.6 s in one call and 98.4 s in thirty, and the 95 s difference is mostly *not* transport but
  per-call setup the payload redoes each time. Where the work inside the call is itself expensive —
  loading an MHCLO asset is seconds of mesh import and vertex fitting — the argument does not carry
  over, and one-per-call is the better shape.
