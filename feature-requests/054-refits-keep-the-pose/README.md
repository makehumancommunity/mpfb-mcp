# A refit keeps the pose, and reaches a character its view layer excludes

**Status:** Proposed

Two entries in NEXT_STEPS, one request, because both are a refit doing the wrong thing without being
asked and both are fixed in the same place: around the call.

**[A refit silently resets a generated Rigify rig's pose and
switches](../NEXT_STEPS.md#refit-resets-a-rigify-pose).** The photo studio session posed a character
and then composed its smile. `mpfb_set_face_units` refits by default, the refit regenerated the rig,
and every control went to rest and every `IK_FK` back to 0. The answer said `refit_performed: true`.
It showed up only when a later write was refused with `chain_not_in_charge`. The cost was three
characters re-posed, about nine calls and a wasted render.

**[Refits raise on a character whose collection is excluded from the view
layer](../NEXT_STEPS.md#refit-raises-on-excluded-collection).** One collection per character, all
but one excluded, is the easy way to manage several characters at the origin. A refit then fails
with a raw traceback, and `mpfb_set_face_units` had already written its shape keys when it did.

**Measured while scoping**, headless:

| Case | Result |
|---|---|
| Refit, posed `default_no_toes` | **Nothing lost.** Wrist moved 0.0 mm. NEXT_STEPS' Rigify scope is right |
| Refit, posed generated `human_toes` | Every control at rest, `IK_FK` 0. `DEF-hand.L` moved 181 mm, in 0.55 s |
| Snapshot before, restore after, same rig | **0.0 mm** on every bone checked, 23 ms for all 1090 bones |
| The same after a body change (`height` 0.95, `muscle` 0.9) | Controls and `IK_FK` back exactly. The hand stands somewhere new, because the body changed |
| Excluded, `refit_human`, rigged | Raises `ViewLayer 'ViewLayer' does not contain object 'Human.rig'` |
| Excluded, `refit_human`, no rig | Works |
| Excluded, `add_asset` | Raises `Object 'Human' cannot be selected because it is not in View Layer` |
| Excluded, `place_character`, `get_character_summary`, `get_pose`, `save_preset` | Work |
| Include, refit or add, exclude again | Works on both rig families; include and exclude measured under 1 ms each |

**That run also showed three things the design must deal with.** The new asset followed the active
collection: `Collection` in one run and the character's own in the other, so it can land outside the
excluded collection and stay visible when the character is not. A selected bystander object ended
the sequence deselected, which the commands' own selection handling is the likeliest cause of. And
one of two runs lost an object's `hide_set()` across the exclude, which may be the exclude itself
rather than anything a tool does: the effort has to settle that.

## Goals

**Primary:** no refitting tool loses a pose without being told to, and none fails because of how the
user organised the scene.

**Secondary:**

- **A body change's real consequence is reported:** the pose is kept, and where that now puts a limb
  is measured.
- **The view layer is the user's.** It ends the call exactly as it began, and the answer says it was
  touched.

## Non-goals

- **Keeping a limb at the same place in the world after a body change.** A hand-target's value is
  kept, and its world position is not. Snapping to the old world positions is another feature, if a
  session wants it.
- **A tool to include or exclude a collection.** Nothing here needs one.
- **Other view-layer states.** A collection with `hide_viewport` on, or in another scene, is refused
  if it stops the work, and no more than that.
- **Fixing it in MPFB.** A refit that keeps the pose would be better there. FR 12 proposes it.

## Functional requirements

### The pose

1. **All six refitting commands keep the pose by default:** `mpfb_refit_human`,
   `mpfb_set_macro_details`, `mpfb_set_targets`, `mpfb_symmetrize_targets`, `mpfb_set_face_units`
   and `mpfb_apply_expressions`, each when it does refit.
2. **Any rig, decided by what happened rather than by its type.** Everything is read before the
   refit and compared after, and only what changed is written back. A default rig writes nothing. If
   a future rig family also loses its pose, it is already covered.
3. **What is kept:** every channel of every bone, rotation mode, and each numeric custom property,
   including `IK_FK`, `IK_Stretch`, `IK_parent` and `pole_parent`. Restored values are written
   directly, with no snapping: both chains go back to what they held, so nothing needs to be carried
   over.
4. **`keep_pose: false`** gives MPFB's behaviour on any of the six. A real bool, checked on this
   side.
5. **Every answer from a refit that happened reports it:** `pose_after_refit` is `"unchanged"`,
   `"kept"` or `"reset"`.
   - `kept` adds `pose_kept_count`, plus `limbs_made_stretched` and `limbs_made_unreachable` as
     `mpfb_set_pose_bones` reports them, since a changed body can put a target out of reach. A bone
     that no longer exists goes in `bones_not_restored`.
   - `reset` adds `restore_with`, built as `mpfb_reset_pose` builds it and never capped.
6. **A refit that raises still restores what it can**, in a `finally`, and the failure envelope is
   otherwise unchanged.
7. **A refit blocked by `rig_refit_is_blocked()`** (a generated rig with no meta-rig) left the rig
   untouched, so reports `"unchanged"`.

### The view layer

8. **A refit, `mpfb_add_asset` and every other command that needs the character selectable
   temporarily includes its collection.** The live check scans every mutating command against an
   excluded character and writes down which need it. Commands that work today are not wrapped:
   scoping found at least four.
9. **Only what is needed, and always put back.** The excluded layer collections holding the
   character's family, and excluded parents of those, are included, and exactly those excluded again
   in a `finally`.
10. **The answer's `temporarily_included`** names them, and the message says so. It is `[]` on an
    ordinary call.
11. **A created object joins the character.** During an inclusion, what a command creates is linked
    to the basemesh's collection and unlinked from wherever the active collection put it, and
    `objects_moved_to_collection` names it. Otherwise a garment stands visible at the origin beside
    an excluded character. Calls with no inclusion keep today's behaviour.
12. **Selection, the active object and each family object's `hide_set()` state are put back**, using
    `selection.restored_all()` rather than `restored()`, because scoping lost a bystander's
    selection. The effort records whether the hide state is lost by the exclude itself, and reports
    it only if the tool is the cause.
13. **What cannot be included is still a refusal:** `blocked_by: "not_in_view_layer"`, naming the
    collection, checked before anything is written. This covers an object in another scene, or in no
    collection at all. `mpfb_set_face_units`' keys are then not written.

### Upstream

14. **Propose both to MPFB**, in `mpfb2/features/MCP_DISCOVERED_BUGS.md`: `refit()` regenerating a
    rig loses its pose, and a refit needs its rig in the view layer. The bridge keeps working either
    way.

## Non-functional requirements

- **An answer can always be trusted about the pose.** Today's silence is the defect. Even with
  `keep_pose: false`, the caller is told and handed the undo.
- **Cheap.** 23 ms beside a 550 ms refit needs no opt-out on performance grounds, and the live check
  records it on a dressed, face-rigged character.
- **Robust against the failure path.** The view layer is a user's setting, and the `finally` is the
  whole reason this is acceptable. An induced failure inside the block has a test.

## Architecture

- **`shared/refit_pose.py`** holds the snapshot, the comparison and the restore.
  `shared/pose_writing.py`'s `snapshot()` and `restore()` are the channel half; custom properties
  are the addition. `refit_blocker.py` is the precedent: a rule six commands must agree about, with
  wording left at the call site.
- **Six commands call one context manager**, around their `refit()`, as they do
  `selection.restored`.
- **`shared/view_layer.py`** holds the inclusion, as a context manager on the outside of the
  selection restore: an object must be in the view layer before its selection can be recorded. Layer
  collections are found by walking `view_layer.layer_collection`.
- **`shared/selection.py`'s `restored_all()`** already leaves what the block created deselected,
  which is what FR 11's new objects want.
- **The new asset's collection** comes from the basemesh's `users_collection`. An object in two
  collections has no single answer, so the first included one is used and the answer names it.
- **Pitfall:** a Rigify regenerate may replace bones' identity while keeping the object and its
  name, so the restore finds bones by name, after the refit, never by a reference held across it.
- **Pitfall:** `exclude` changes need a `view_layer.update()` before the first selection.
- **This overlaps [Selection restore covers one
  object](../NEXT_STEPS.md#selection-restore-covers-one-object)** for the wrapped commands only. The
  other commands stay in that entry.

## Affected specifications

- [mutating-tools.md](../../specifications/mutating-tools.md): "Restore what was borrowed" gains the
  view layer; a refit's pose as a consequence reported; `keep_pose` and `restore_with`.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): an MPFB call that loses state is
  wrapped rather than reported only.
- [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one): the
  two new shared modules.
- [tool-interface.md](../../specifications/tool-interface.md): the glossary (`keep_pose`,
  `pose_after_refit`, `temporarily_included`).
- [vision.md](../../specifications/vision.md): no change.

## Tests

- **Unit:** `keep_pose` is a real bool on all six, and what reaches the wire.
- **`bbb_shared/refit_pose_test.py`, `view_layer_test.py`:** direct, including a failure inside each
  block, nested exclusion, and an object in two collections.
- **`ddd_mutating/`:** for each of the six: on generated Rigify with a pose and a switch, `kept`,
  `reset` with a `restore_with` that puts it back, and on a default rig `unchanged` with nothing
  written.
- **`eee_composite/`:** the photo studio sequence (pose, switch, `mpfb_set_face_units`, then a write
  that used to be refused); and a table-driven scan of every mutating command against an excluded
  character, which must never produce `command_failed`.
- **Live check, a script in this subdir:** on a dressed character with a sub-rig, posed, in a body
  change and on one of several excluded characters. Records the timings and FR 12's finding, and
  renders one before and one after.
- **No smoke item.** No tool is added.

## Decisions taken while scoping

Asked on 2026-11-03:

- **Restore by default, with an opt-out.** Reporting only, and restoring with no opt-out, were the
  alternatives.
- **Include temporarily, rather than refuse.** The NEXT_STEPS entry asked for a refusal naming the
  collection. A refusal would leave a caller with no MPFB tool to continue, and the
  one-collection-per-character workflow is why this hurts. A refusal by default with an opt-in was
  also offered. This is a deliberate change to what the entry proposed, and FR 13 keeps that refusal
  for what cannot be included.

*Not asked*, each argued where it is stated: both entries in one request (the opening); decided by
comparison rather than by rig type (FR 2); moving a new object to the character's collection (FR
11), found by scoping and otherwise a new silent defect.

## References

- [NEXT_STEPS: A refit silently resets](../NEXT_STEPS.md#refit-resets-a-rigify-pose), [Refits
  raise](../NEXT_STEPS.md#refit-raises-on-excluded-collection).
- `interacting_with_blender/PHOTO_STUDIO_TEMPLATE.md`.
- mpfb2: `services/humanservice.py` (`refit`), `services/rigservice.py` (`refit_existing_armature`).
- `bridge/mpfb_bridge/shared/refit_blocker.py`, `selection.py`, `pose_writing.py`.
