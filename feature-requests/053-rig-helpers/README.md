# Switching MPFB's rig helpers on and off

**Status:** Proposed

This is the other half of [A hand cannot be placed at a point on a standard
rig](../NEXT_STEPS.md#a-hand-cannot-be-placed-at-a-point-on-a-standard-rig), beside [FR
052](../052-reaching-and-orienting/README.md). FR 052 places a limb once and leaves the rig alone.
This one gives a default rig IK controls that stay.

**MPFB can already do this, and only its panel can ask.** `mpfb_get_pose_controls` reports
`helper_modes`, classifies `left_hand_ik` as an `ik_control`, and `mpfb_set_pose_bones`'
`driven_by_helper` refusal already names the helper to move. Everything downstream exists. Nothing
turns them on: `RigService` has only the low-level pieces, and the modes are assembled by
`ArmHelpers`, `LegHelpers`, `FingerHelpers` and `EyeHelpers` under the `mpfb.add_helpers` operator,
which reads its settings from scene properties.

**Measured while scoping**, headless, on `default_no_toes`, through that operator with
`arm_helpers_type: LOWERUPPER`:

| What | Result |
|---|---|
| Adding them | 137 bones become 141 (`left_hand_ik`, `left_elbow_ik`, and the right pair), in 0.09 s |
| `identify_rig` afterwards | Still `default_no_toes` |
| `mpfb_get_pose_controls` afterwards | `ik_control: 2`, `pole: 2`, `arm_mode: LOWERUPPER` |
| `move_by` on `left_hand_ik` | The wrist followed by 433 mm, 0.0 mm from the control |
| A posed arm when they are added | The wrist did not move, with `preserve_fk` on or off |
| `mpfb_refit_human` afterwards | Performed; helpers and their offset kept |
| `mpfb.remove_helpers` | 141 bones back to 137, 10 constraints to 0, nothing left hidden |

**Two costs, both measured, are why this is a choice rather than the default.** MPFB's JSON pose
loader looks for `<rig>_ik` on any rig with an `_ik` bone, and `default_ik` does not exist in this
install's poses. And a BVH pose loaded onto a rig with helpers ended **367 mm** from the same pose
without them, because the constraints win over what the loader wrote to the FK bones. [FR
055](../055-loading-and-saving-poses/README.md) refuses that combination.

## Goals

**Primary:** a caller can give a default rig the IK controls its panel offers, choose which, and
take them off again.

**Secondary:**

- **The caller's pose survives both directions**, measured in the answer.
- **The tool says what having helpers will cost**, at the point of decision, in the way
  `mpfb_generate_rigify_rig` reports `refit_will_be_possible`.

## Non-goals

- **Helpers on other rigs.** MPFB refuses anything without `levator03.L`, and so does this.
- **Finger shapes.** [Posing support](../NEXT_STEPS.md#posing-support)'s default-rig hand shape is a
  separate effort, and finger helpers are a separate mechanism from it.
- **Reimplementing the helpers.** MPFB's own classes build the bones.

## Functional requirements

1. **One tool, `mpfb_set_rig_helpers`**, taking the usual `name`, and `arms`, `legs`, `fingers` and
   `eyes`.
2. **A group not named is left alone.** `arms: "LOWERUPPER"` on a rig with leg helpers keeps them. A
   call naming nothing does nothing and says so, per [do only what was
   asked](../../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after).
3. **`"NONE"` removes a group.** Naming a different mode replaces it, removing the old one first,
   because MPFB's helpers for one group have to come off with the mode that put them on.
4. **The vocabulary is MPFB's and is read live** from its helper property definitions: `LOWERUPPER`,
   `LOWERUPPERSHOULDER`, `ARMCHAIN`, `SHOULDERCHAIN` for arms and so on. The check is in the
   command, since an unknown value otherwise does nothing at all without saying so. A refusal
   carries `known_modes`. `eyes` is a boolean, as MPFB's `eye_ik` is.
5. **`options` takes the panel's other settings**, keyed by MPFB's own names (`hide_fk`,
   `arm_parenting_strategy`, `arm_target_rotates_hand` and the rest), with the panel's defaults.
   `options_used` reports all of them.
6. **It does not touch the user's panel settings.** The scene properties the operator reads are not
   left changed.
7. **Adding keeps the visible pose.** Scoping measured 0.0 mm, and each answer reports what it
   measures.
8. **Removing keeps the visible pose by default.** The FK bones are written from where the helpers
   had put them before the helpers go. Removal without that has not been measured, and a pose held
   only by a helper would otherwise be lost silently. `keep_pose: false` gives MPFB's behaviour.
   `deviation` reports what was achieved.
9. **The answer has `helper_modes` before and after**, in `mpfb_get_pose_controls`' shape, plus
   `controls_added`, `controls_removed` and the rest of the usual mutating fields.
10. **The answer says what helpers cost, when they are on:**
    - `saved_poses_directory`, whether it exists and how many poses it holds, since MPFB's loader
      changes directory;
    - that BVH poses are refused while helpers are on, per FR 055;
    - `exports_carry_helpers`, once the effort has measured it. A helper bone in an FBX is not what
      a game engine expects, and `mpfb_export_character`'s `readiness` should name it if so.
11. **Refusals:** `rig_not_supported` (no `levator03.L`, naming what the rig was identified as),
    `rig_not_found`, a meta-rig, and an object not in the view layer as [FR
    054](../054-refits-keep-the-pose/README.md) settles it.
12. **Selection, active object and mode are put back**, using `selection.restored_all()`.

## Non-functional requirements

- **Indistinguishable from the panel.** The bridge test compares bones, constraints and
  `helper_modes` against what `bpy.ops.mpfb.add_helpers` produces (`_fixtures.with_helpers()`
  already does it that way), for each mode.
- **No surprise in the description.** It states the two costs above, since a caller reads them
  before calling, and points at `reach_to` for a caller who only wants to place a limb once.

## Architecture

- **Call MPFB's classes, not the operator.** The operator takes its settings from scene properties,
  so calling it means writing the user's panel state and restoring it.
  `ArmHelpers.get_instance(side, settings).apply_ik(rig)` takes them as a dict. Then
  `RigHelpersProperties.set_value()` and `RigService.normalize_rotation_mode()`, as the operator
  does. If the operator's other steps matter, the panel-parity test will say so.
- **These are not services.** The helper classes live under `entities/rigging/righelpers/` and
  `RigHelpersProperties` on a UI module, already read through `mpfb_surface.rig_helpers_properties`.
  Reach them with `sys.modules.get()`: [both
  conditions](../../specifications/architecture.md#a-ui-module-with-no-service-behind-it) should
  hold, since the operator module imports them at registration. **The bridge test must confirm
  that**, and a miss is an ordinary answer with a reason.
- **`remove_ik()` needs the recorded mode**, read from `RigHelpersProperties` on the armature, as
  the operator does.
- **`shared/pose_writing.py`** does FR 8's write. The bones are in `shared/pose_controls.py`'s
  `driven_by`.
- **Pitfall:** `normalize_rotation_mode()` can change a bone's rotation mode. A `restore_with` taken
  before the helpers went on has to survive that, and a test should show it does.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog): one more
  creation-and-modification tool.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): calling MPFB's entity classes
  rather than a service.
- [architecture.md](../../specifications/architecture.md#a-ui-module-with-no-service-behind-it):
  another readable module, with what it rests on.
- [mutating-tools.md](../../specifications/mutating-tools.md): a step that forecloses a later one,
  said at the point of decision.

## Tests

- **Unit, `tests/test_set_rig_helpers.py`:** shape only; a mode must be a non-empty string, `eyes` a
  real bool, `options` an object. No mode vocabulary here.
- **`ddd_mutating/set_rig_helpers_test.py`:** panel parity per mode; a group left alone; replacing a
  mode; both directions keeping a pose; every refusal; the user's panel settings unchanged;
  selection and mode.
- **`eee_composite/`:** `mpfb_get_pose_controls`, `mpfb_set_pose_bones` and `mpfb_reset_pose` over a
  rig the tool gave helpers, and a refit.
- **Live check, a script in this subdir:** measures FR 8, exports a rig with helpers to settle FR
  10, and checks whether a preset carries them. Numbers go in the Outcome.
- **One smoke item**, `arms: "LOWERUPPER"` on the smoke character's default rig. It needs the rig
  fixture the pose items already use.

## Decisions taken while scoping

Asked on 2026-11-03:

- **A tool for the helpers as well as FR 052's solver**, in a request of its own so that a problem
  here does not hold back the solver.

*Not asked*, each argued where it is stated: one tool rather than an add and a remove (FR 3); MPFB's
classes rather than its operator (Architecture); keeping the pose on removal by default (FR 8),
which is the same call FR 054 makes for a refit.

## References

- [NEXT_STEPS: A hand cannot be placed at a point on a standard
  rig](../NEXT_STEPS.md#a-hand-cannot-be-placed-at-a-point-on-a-standard-rig).
- mpfb2: `ui/rigging/standardrig/operators/addhelpers.py`, `removehelpers.py`,
  `ui/rigging/standardrig/helperproperties/`, `entities/rigging/righelpers/`.
- `bridge/test/tests/_fixtures.py` (`with_helpers`), `bridge/mpfb_bridge/shared/pose_controls.py`
  (`_DEFAULT_HELPERS`).
