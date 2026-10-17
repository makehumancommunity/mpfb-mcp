# Posing a character: moving its controls, setting Rigify's switches, and returning to rest

**Status:** Accepted

This is the second part of [Posing support](../NEXT_STEPS.md#posing-support), and it depends on
the first. [FR 041](../done/041-pose-controls-and-read-back/README.md) adds the read-only tools: which
controls a rig has, what each one does, what the pose is now, and whether a limb is stretched.
This request adds the tools that change a pose.

The karate session that NEXT_STEPS describes did all of its posing through
`execute_blender_code`, with a helper that set `pose_bone.matrix` from a world-space move or
rotation and updated the depsgraph after each bone. It found three problems that a tool should
take off the caller's hands. Every move had to be worked out by hand in bone-local axes, which mix
four rotation modes and arbitrary rolls. Rigify's switches are hidden custom properties, and
setting one changes the pose: the elbows splayed until `pole_vector` was turned on, and the fists
stayed in the air when the hips were lowered, because `IK_parent` attaches the hands to `root`. And
there was no way back to rest, other than remembering what had been moved.

This request adds three mutating tools:

- `mpfb_set_pose_bones`: a batch of transforms, each a move, a rotation or an aim and a scale,
  given in the character frame FR 041 defines.
- `mpfb_set_pose_switches`: a batch of Rigify switch changes, and by default each one **keeps the
  limb where it is**, as Rigify's own UI buttons do.
- `mpfb_reset_pose`: a way back to rest, by body part. Its answer is the call that puts the pose
  back.

Reading Rigify's source while scoping turned up one fact that shapes all of this. **Rigify's snap
operators cannot be relied on from a bridge command.** Each generated rig gets operators named
after its `rig_id` (`pose.rigify_limb_ik2fk_<rig_id>`, `pose.rigify_switch_parent_<rig_id>`,
`pose.rigify_limb_toggle_pole_<rig_id>`). They are registered by the `rig_ui.py` text block that
generation writes into the `.blend`. After the file is reopened, that text block runs only if
Python auto-run is allowed, and it runs at all only in a Blender with a UI that registered it. The
bone chains each operator works on are stored as operator properties in that same script, not on
the rig. So snapping is reimplemented in the bridge (see [Architecture](#architecture)).

## Goals

**Primary:** an agent can pose a character with a generated Rigify rig into a stance like the
karate session's, using only mpfb-mcp tools: no `execute_blender_code`, no hand-computed matrices,
and no limb that jumps when a switch changes.

**Secondary:**

- **Every pose write can be undone across the socket.** Blender's undo stack does not record a
  bridge command's writes, so `mpfb_reset_pose` and the before values in each answer are the undo.
- **What `mpfb_get_pose` reports, `mpfb_set_pose_bones` accepts.** A rotation is read back as an
  axis and degrees in the character frame, and it is written in exactly that shape. A read-back can
  therefore be fed back into a write unchanged, and that is what makes the reset answer a call that
  restores the pose.
- **Report what was achieved beside what was asked.** A constraint, an IK chain or a parent can
  stop a bone from ending where it was sent, and the answer measures where it did end up.
- **Work on every rig that FR 041 can list**, including unclassified ones, for plain transforms
  and the reset. The switches and the "is this bone in charge" check exist only where FR 041
  classifies.

## Non-goals

- **Hand shapes as named presets** (`fist`, `open`, `relaxed`, a curl per finger). `scale_to` on
  the finger masters is enough for a fist on Rigify. A helper that hides the difference between
  Rigify and the default rig stays in [NEXT_STEPS](../NEXT_STEPS.md#posing-support) as its own
  effort.
- **Keyframes.** No tool here inserts, deletes or edits a keyframe. A write to an animated channel
  is reported, not refused (FR 9).
- **Saving and loading poses** ([Loading poses](../NEXT_STEPS.md#loading-poses)) and retargeting.
- **Adding or removing MPFB's IK helpers** on the default rig. That changes the rig, not the pose.
  The helpers are respected (FR 7) but not managed.
- **Garment sub-rigs**, as in FR 041.
- **Applying a pose as the rest pose** (`RigService.apply_pose_as_rest_pose`). That changes the
  rig, and every fitted asset with it.

## Functional requirements

### All three tools

1. **Subject, rig and refusals are FR 041's.** `name` is any object in the character's family,
   `null` is the active object, and the rig is the armature that the basemesh's armature modifier
   points at. A missing subject is `subject_not_found`. A missing rig is `no_rig`, naming
   `mpfb_add_rig`. An ungenerated meta-rig is FR 041's meta-rig refusal, naming
   `mpfb_generate_rigify_rig`. Each answer reports `rig_object_name` and `rig_identified_as`.
2. **Preconditions.** A rig in edit mode is refused (`blocked_by` spelling to be settled against
   the glossary). Pose mode and object mode are both fine, because nothing here goes through an
   operator. An armature showing its **rest position** (`pose_position == "REST"`) is not refused,
   because the writes are stored either way. But every answer reports `pose_position`, because a
   pose that does not show in the viewport is exactly what an agent checking with a screenshot
   would misread.
3. **Nothing is borrowed.** No mode, selection or active object changes, and no operator is
   called. The bridge tests check all four before and after, as FR 041's do.
4. **The character frame is FR 041's** (`forward`, `left`, `up`, measured from the rig object's
   origin), and it comes from `shared/character_frame.py`, not from a second implementation. A
   vector in an argument is an object with any of the three keys, and a missing key means 0.0.

### `mpfb_set_pose_bones`

5. **One entry per bone.** It takes `bones`, a list of entries, and each entry names a `bone` (the
   pose bone name, as FR 041 reports it) plus at most one change of each kind:
   - **position**, as one of `move_by` (an offset in metres, in the character frame) or `move_to`
     (where the bone's head should be, in the character frame);
   - **rotation**, as one of `rotate_by` (`{"axis": <vector>, "degrees": <number>}`, about the
     bone's head, in the character frame), `rotate_to` (the rotation from rest, in exactly the
     shape `mpfb_get_pose` reports it), or `aim` (the direction head to tail should point, in the
     character frame) with an optional `twist` in degrees about the bone's own axis;
   - **scale**, as `scale_to`: factors relative to rest, keyed `x`, `y` and `z` in the **bone's
     own** axes, where `y` is along the bone. A key that is left out means that axis is not
     changed. This is the one input that is not in the character frame, because scale only means
     something along a bone, and the description says so.

   An entry with no change at all, an entry that names two changes of the same kind, and a bone
   named twice in one call are refused before anything is sent.
6. **`symmetry` per entry** (default false) also applies the entry to the bone's counterpart. The
   counterpart's name comes from `bpy.utils.flip_name()`. On a classified rig it must have the
   mirrored body part and the same role. **What is mirrored is the instruction, not the result**:
   `move_by` and `move_to` negate `left`, `rotate_by` and `rotate_to` mirror the axis and keep the
   degrees as a mirrored rotation, `aim` negates `left`, and `twist` negates. From a symmetric
   start, this gives a symmetric pose. A bone with no counterpart, or a counterpart that is also
   named in the same call, is a resolution error. A mirrored write is reported as its own change,
   with `mirrored_from`.
7. **Only a bone that is in charge can be written.** On a classified rig, the batch is refused
   with `resolution_errors` naming the entry when:
   - the bone is not a control (`DEF-`, `ORG-`, `MCH-` on Rigify), with `write_instead` naming the
     control that moves it where Rigify's naming makes that derivable;
   - the bone belongs to a limb chain that is not in charge, such as an FK bone while `IK_FK` is
     0.0, or an IK control while it is 1.0. `write_instead` then names the
     `mpfb_set_pose_switches` entry that would put it in charge;
   - the bone is an FK bone driven by one of MPFB's helpers on the default rig. `write_instead`
     then names the helper bone (FR 041's `driven_by`);
   - the write would change a **locked** channel. Blender's `pose_bone.matrix` setter ignores
     locks, so the tool enforces them itself;
   - the channel is driven by a **driver**, which would overwrite the write right away.

   On an unclassified rig, only locks and drivers are checked. Any bone can be written, because
   nothing is known about which bones are in charge.
8. **All or nothing, including geometry.** Name-level checks run before anything is written. Some
   checks can only run after the write. For example, whether the basis needed for `move_to`
   touches a locked channel depends on where the parents ended up. So the command snapshots the
   `matrix_basis` of every bone it will touch, writes, checks, and **restores the snapshot** if
   any entry fails. Pose basis data is plain data and can be put back exactly, which a mesh rebuild
   cannot. The answer says nothing was applied, as `mpfb_set_targets`' does.
9. **Application order is parent before child**, whatever order the request lists them in, and
   the depsgraph is updated after each bone. That way a child's `move_to` still holds after its
   parent moves in the same call. Changes are **reported in request order**. Relative inputs
   (`move_by`, `rotate_by`) are relative to the bone's pose at the moment it is written, after its
   parents.
10. **The answer, per change**: `bone`, `body_part` and `role` (FR 041's, or `null` when
    unclassified); the head position and the rotation from rest, before and after; the scale
    before and after where either is not 1; and `achieved`. `achieved` is false when the bone ended
    more than 1 mm or 0.5° from what was asked, because of a constraint, an IK chain or a limit,
    and then the answer also gives the deviation. These are
    [derived facts](../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact),
    and the answer says how they were measured. An entry whose channels an action animates is
    flagged `overwritten_on_frame_change` (spelling to be settled), because the next frame change
    puts the keyed value back.
11. **What changed as a consequence.** Moving a bone moves the body. The answer gives FR 041's
    landmarks (head, hands, feet, hips, measured on the deforming bones) before and after. It also
    gives FR 041's per-limb reach and stretch after the write, under `mpfb_get_pose`'s own keys
    and computed by the same shared code. **A limb that this call made stretched or unreachable is
    named.** That is the over-reach the karate session found only by looking.

### `mpfb_set_pose_switches`

12. **Entries address a switch by limb.** It takes `switches`, a list of
    `{"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}`. `switch` is Rigify's property
    name exactly as FR 041 reports it. `value` is a number, or a boolean for `pole_vector`, and
    its range is checked against the live property. The bone the property lives on
    (`upper_arm_parent.L`) is a Rigify detail that the answer reports but the caller does not need.
    Only generated Rigify rigs have switches. Any other rig is refused before anything is written,
    and the refusal says which rigs have them.
13. **Snap by default.** Each entry takes `raw` (default false). Without `raw`, a switch that
    Rigify's UI offers a snap for keeps the limb's world pose:
    - `IK_FK` to 1.0: the FK controls take the pose of the IK result;
    - `IK_FK` to 0.0: the IK control, and the pole when `pole_vector` is on, take the pose of the
      FK result;
    - `pole_vector`: the IK chain keeps its pose while the pole is turned on or off;
    - `IK_parent` and `pole_parent`: the control keeps its world matrix under the new parent.

    `IK_Stretch`, `FK_limb_follow` and an `IK_FK` value strictly between 0 and 1 have no snap. They
    are written raw, and the answer says `snapped: false` and why. `raw: true` always writes the
    bare value.
14. **The answer, per change**: `body_part`, `switch`, the bone it lives on, `previous_value` and
    `new_value`, `snapped`, and the limb's end (hand or foot, on the deforming bones) before and
    after. When `snapped` is true, the distance between the two is reported as `snap_error`, so a
    snap that failed shows up as a number. It also reports FR 11's reach, stretch and landmarks,
    because a raw switch moves the body.
15. **A batch, all or nothing, in request order.** Switches are applied in the order given,
    because they interact: a pole toggled on before an `IK_FK` change to 0.0 changes what that snap
    computes. A switch named twice in one call is refused before anything is sent.

### `mpfb_reset_pose`

16. **Back to rest, by body part.** `body_parts` defaults to **every part, `face` included**.
    That is unlike FR 041's read default, on purpose: FR 041 leaves the face out to keep an answer
    small, while a reset that silently leaves the face posed would not be a reset. The description
    says so. On an unclassified rig, `body_parts` must be `null`, and every pose bone is reset.
17. **What is reset.** Every control in the chosen parts goes to an identity `matrix_basis`, MPFB's
    helper bones included. Bones that are not controls are not touched. If any of them are off
    rest, they are reported (`left_off_rest`), because on a generated rig that means something
    other than this package moved them.
18. **`switches`** (default false) also returns each switch of the chosen limbs to its default.
    The default is read live from the property (`id_properties_ui(...).as_dict()["default"]`), not
    from a table. Switches are reset raw and before the transforms, so snapping is moot.
19. **The answer is a way back.** This tool destroys a pose it did not create, so per
    [what that owes the caller](../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list)
    it returns `restore_with`: the `mpfb_set_pose_bones` arguments (with `move_to`, `rotate_to`
    and `scale_to`) and, when `switches` was set, the `mpfb_set_pose_switches` arguments (with
    `raw: true`) that put back what it reset. This follows `mpfb_save_expression`'s `apply_with`.
    A character already at rest gets `performed: false`, an empty `restore_with`, and no sentence
    about it.

## Non-functional requirements

- **Cheap enough to call often.** The karate stance took a few dozen bone writes. A batch of 30
  entries on a generated `human_toes` rig, with one depsgraph update per bone, is measured during
  the effort, and so is each answer's size. `mpfb_set_pose_bones`' answer aims at FR 041's 8 KB
  for `mpfb_get_pose`. `mpfb_reset_pose`'s `restore_with` is not capped, because a capped
  `restore_with` would not restore anything. Its worst case (every Rigify control posed, face
  included) is measured and written down with the measurement.
- **Predictable before clever.** One way to say each change, no inference about what the caller
  "meant", and symmetry that mirrors the instruction and not the result. An agent that is
  surprised by a pose can find out why from the answer.
- **The vocabulary is FR 041's.** `body_part`, `role`, `chain` and the frame's axis names are not
  redefined here. The only Rigify names in an argument are `bone` and `switch`, and both are
  identifiers that FR 041 hands out.
- **Robust to a rig that was edited after generation.** A renamed bone or a missing switch is a
  resolution error naming what was looked for, never an exception.

## Architecture

- **Three bridge commands**, `set_pose_bones`, `set_pose_switches` and `reset_pose`, and the three
  tool modules, with the usual touch points listed in [CLAUDE.md](../../CLAUDE.md). There is no
  MPFB service to wrap: `RigService.set_pose_from_dict()` goes through `bpy.ops.pose.select_all`
  and `transforms_clear`, which need pose mode and a selection. That makes this, like
  `mpfb_set_asset_material`, a reimplementation, and this time it is of **Rigify's** UI as well as
  MPFB's.
- **What FR 041 provides is consumed, not copied.** `shared/character_frame.py` converts between
  the frame and armature space, both ways (`world_point`, `world_vector`). `shared/pose_controls.py`
  gives each bone's body part, role, chain, source and `driven_by`, each switch's bone, type, range
  and live `default` (FR 18), and each limb's switch bone, IK control and pole; and
  `resolve_posing_subject()` is FR 1's subject, rig and refusals, taking a `not_done` phrase for a
  command that would have changed something. `shared/pose_reading.py` - a third module FR 041 added
  - computes FR 11's landmarks, reach and stretch, reports each limb's `in_charge` (`ik`, `fk` or
  `blend`, from `IK_FK` or the default rig's helpers), which is what FR 7's "in charge" check can
  read, and `off_rest()`, which is FR 17's `left_off_rest` test.
  [A summary is never a second opinion](../../specifications/responses.md#a-summary-is-never-a-second-opinion)
  applies just as much to a mutating tool's after-report.
- **A new shared module, `pose_writing.py`**, used by all three commands: writing a bone from a
  frame-space target through `pose_bone.matrix` with a depsgraph update, the snapshot and restore
  of FR 8, the lock and driver checks, and the before and after measurement. Ordering parents
  before children (FR 9) also lives here.
- **The snaps are ported from Rigify, not called.** The math is in Rigify's
  `rig_ui_template.py` (`UTILITIES_FUNC_COMMON_IK_FK`: `get_chain_transform_matrices`,
  `match_pole_target`, `set_transform_from_matrix`), `rigs/limbs/limb_rigs.py`
  (`RigifyLimbIk2FkBase`, `RigifyLimbTogglePoleBase`) and `utils/switch_parent.py`. It lives in
  the `set_pose_switches` command module, since it has one user. Rigify is GPL-2.0-or-later, which
  is compatible with the bridge's licence, and the module docstring credits it. **The pitfall is
  the chains, not the math.** Rigify's operators get their FK chain, IK result chain, tail and
  extra controls as JSON-encoded operator properties baked into `rig_ui.py`. FR 041 classifies
  controls, but not the `MCH-` chains a snap reads. It does derive each limb's `ORG-` chain from its
  FK controls (`upper_arm_fk.L` is `ORG-upper_arm.L`, `upperarm_fk_l` is `ORG-upperarm_l`), and
  found that a generated `game_engine` rig has every control in one collection, `Bones`, so nothing
  there can come from collections. The effort has to establish whether
  those chains follow from Rigify's naming on a generated `human_toes` and a generated
  `game_engine` rig. If they do, a bridge test checks the derived chains against the ones in the
  generated `rig_ui.py`, in the way FR 041 checks its default-rig table against MPFB's helpers. If
  they do not, reading `rig_ui.py` **as data** (never executing it) is the fallback. It is then a
  decision this request has to record, because FR 041 ruled out parsing that script at runtime.
- **Locks and drivers are checked by the bridge**, because `pose_bone.matrix` assignment writes
  the whole basis. Interactive transforms respect locks, while this setter does not.
- **No keyframes, by construction.** Data writes do not trigger auto-keying, and since no
  operator is called, nothing in this request can insert a key, whatever
  `use_keyframe_insert_auto` says. Whether a channel is animated is read from the rig's action
  and its F-curve data paths.
- **Rigify's `IK_parent` is an integer**, 0 to N, and the property's description says only
  "Switch parent of hand_ik.L". `value` is therefore the integer. FR 041 found the names of the
  parents on the property itself, as its `items` (Rigify's `SwitchParentBuilder` passes them to
  `make_property()`), checked against `rig_ui.py` by a bridge test; its switch listing maps each
  integer to its parent's name, or reports `parent_names: null` where a property carries none, so a
  caller picks the integer from a named list.
- **`rotate_to` takes `mpfb_get_pose`'s `rotation` as it is**, and that is the rotation taking the
  bone's rest orientation to its current one **including what its parents did**, so a write
  reproduces it through `pose_bone.matrix` with parents written first (FR 9). A rotation under a
  tenth of a degree reads `{"axis": null, "degrees": 0.0}`, which a `rotate_to` must accept as "at
  rest".
- **Through a windowed Blender's bridge every call takes about a second** (measured during FR 041;
  each handler takes milliseconds, the rest is the timer driving the server), which is one more
  reason the writers are batched.

## Affected specifications

- [mutating-tools.md](../../specifications/mutating-tools.md):
  - [a batch resolves before it writes](../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes)
    gains its second form: snapshot, write, check, restore. That form is allowed only where what
    is written can be put back exactly, and pose basis data can be;
  - a write that **preserves** a derived state (the snap) reports the measured error, not only
    that it ran;
  - `write_instead` can name an entry for **another tool**, which is new;
  - the case where neither Blender's undo stack nor MPFB records the change, and the tool's own
    answer is the undo (`restore_with`).
- [tool-interface.md](../../specifications/tool-interface.md#the-glossary): `move_by`, `move_to`,
  `rotate_by`, `rotate_to`, `aim`, `twist`, `scale_to`, `raw`, `snapped`, `switch`,
  `restore_with`, and `symmetry` as a per-entry flag beside `mpfb_set_targets`' call-level one
  (the same concept, so the same spelling). Also the new `blocked_by` values.
- [responses.md](../../specifications/responses.md): requested beside achieved, with a tolerance,
  as the rule for any tool whose write a constraint can deflect.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): reimplementing a third-party
  add-on's UI operators (Rigify's) and not only MPFB's, and why calling them is not an option.
- [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one):
  `pose_writing.py`.
- [vision.md](../../specifications/vision.md#target-tool-catalog): Creation and modification goes
  from 18 tools to 21. The area's "undo a mistake" gains its first tool built for that purpose.

## Tests

- **Unit suite** (`tests/test_set_pose_bones.py`, `tests/test_set_pose_switches.py`,
  `tests/test_reset_pose.py`), shape only:
  - an entry is a dict with known keys, and a misspelled `move_too` is refused;
  - at most one change of each kind, at least one change, and no bone or switch twice;
  - vectors are objects with only `forward`/`left`/`up`, every number finite, `degrees` and
    `twist` real numbers, `scale_to` factors positive;
  - `aim` is not the zero vector, and `twist` comes only with `aim`;
  - `raw`, `symmetry` and `switches` are real booleans.

  **No bone, body part or switch vocabulary is checked here**, per
  [validate the shape, never the vocabulary](../../specifications/tool-interface.md#validate-before-crossing-the-socket).
  Add all three tools to `test_vocabulary.py` and the description budget.
- **Bridge suite** (`bridge/test/tests/ddd_mutating/`), against FR 041's fixtures:
  - each kind of change on a rig object that has been **moved and turned**, which is what tests
    the frame;
  - parent-before-child order with a child's `move_to`;
  - symmetry, with a mirrored pair checked for mirror-equality from rest;
  - every FR 7 refusal, and the FR 8 rollback, with the rig's basis data identical before and after
    a failed batch;
  - `achieved: false` on an IK chain pulled past reach with stretch off;
  - `overwritten_on_frame_change` on a bone with an action;
  - on a generated `human_toes` rig, every snap in both directions, with `snap_error` under 1 mm,
    and the same switches with `raw: true`, which must move the limb;
  - the reset with and without `switches`, with its `restore_with` fed back into the other two
    tools to restore the pose exactly;
  - an unclassified `mixamo` rig getting transforms and a reset, and its switch call being refused.

  A direct test of `pose_writing.py` goes in `bbb_shared/`.
- **Live check, in this subdir, as a script.** The request is met when the karate stance can be
  rebuilt with **only** mpfb-mcp tools, on a generated `human_toes` character that has been moved
  and turned away from the origin. That means lowering the hips with the fists following (via
  `IK_parent`, snapped), the pole turned on with the elbows in, closed fists through `scale_to`,
  and a guard with the arms not stretched (via `IK_Stretch`, checked through FR 11). The script
  then compares one screenshot against the read-back, resets, and restores from `restore_with`.
  It also checks a generated `game_engine` rig once, which settles the chain question in
  [Architecture](#architecture).
- **Smoke items:** one per tool. The smoke run's character has a rig. `mpfb_set_pose_bones` moves
  one control and `mpfb_reset_pose` puts it back, so the run leaves the pose as it found it. The
  switch item needs a generated Rigify rig, which the smoke character may not have, and the
  effort decides whether that tool's item is a refusal check instead.

## Decisions taken while scoping

All asked on 2026-10-17 unless marked otherwise.

- **Three tools**, not one tool with entries of two kinds. Each schema stays small, and a switch
  and a transform never share a batch. That also keeps the "in charge" check in FR 7 stable for
  the whole of a `mpfb_set_pose_bones` call. The cost is that "switch to FK, then rotate the
  forearm" takes two calls.
- **Reset to rest, symmetry and scale are in scope.** Named hand shapes are not.
- **Switches snap by default**, reimplemented in the bridge, with `raw: true` as the way out.
  Calling Rigify's generated operators was rejected because they are missing whenever `rig_ui.py`
  has not run.
- **Both relative and absolute transforms.** `move_to` exists for IK controls, and `rotate_to`
  for feeding a read-back into a write.
- **Animated channels are written and reported**, never refused, and keyframing is out of scope.
- **An FK write while the limb is in IK is refused** with `write_instead`, not written and
  flagged. The same goes for a bone driven by an MPFB helper.
- **The reset leaves the switches alone by default**, and `switches: true` restores them too.
- *Not asked:* parent-before-child application order, snapshot-and-rollback for checks that can
  only be made after a write, symmetry mirroring the instruction and not the result, the reset
  defaulting to every body part including `face`, and reporting (not refusing) a rig that shows
  its rest position. Each is argued in the requirement that states it.

## Open questions

- **Where the snap chains come from** (see [Architecture](#architecture)): naming conventions
  checked against `rig_ui.py` in a test, or `rig_ui.py` read as data at runtime. FR 041 faces the
  same question for the parent switches' names and is settled first. Its answer should be this
  one's.
- **Whether `scale_to` should exist on rigs other than Rigify.** On the default rig, scaling a
  finger bone deforms the finger, and does not curl it. It is still a legitimate write. The
  question is whether the description should say so.

## References

- [NEXT_STEPS: Posing support](../NEXT_STEPS.md#posing-support), and
  [FR 041](../done/041-pose-controls-and-read-back/README.md), which this builds on.
- Blender: `scripts/addons_core/rigify/rigs/limbs/limb_rigs.py` (`make_property` for `IK_FK`,
  `IK_Stretch`, `pole_vector` and `FK_limb_follow`; `add_global_buttons`; `RigifyLimbIk2FkBase`;
  `RigifyLimbTogglePoleBase`), `scripts/addons_core/rigify/utils/switch_parent.py` (`IK_parent`
  as an integer, `POSE_OT_rigify_switch_parent`, `parent_names` held only in the panel),
  `scripts/addons_core/rigify/utils/animation.py` (`POSE_OT_rigify_generic_snap`),
  `scripts/addons_core/rigify/rig_ui_template.py` (the snap utilities copied into `rig_ui.py`).
- mpfb2: `src/mpfb/services/rigservice.py` (`set_pose_from_dict`, which goes through
  `bpy.ops.pose`; `get_pose_as_dict`; `apply_pose_as_rest_pose`).
- Blender API: `PoseBone.matrix` (armature space, after constraints; assigning it ignores locks),
  `bpy.utils.flip_name`, `rna_idprop_ui` / `id_properties_ui` for a property's default and range.
