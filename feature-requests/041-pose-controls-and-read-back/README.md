# Pose controls and pose read-back: what can be moved on a character's rig, and where it is now

**Status:** Proposed

This is the first part of [Posing support](../NEXT_STEPS.md#posing-support). That entry came from
a session that posed a character with a generated Rigify rig into a karate stance. The mpfb-mcp
tools could say which object was the rig and what MPFB identified it as, and nothing more. The
session had to know from memory which of the rig's 1090 bones were the ones to move. It checked
every change with a screenshot, because no tool reads a pose back. All of this went through
`execute_blender_code`.

This request adds the two **read-only** tools that the later posing tools build on.
`mpfb_get_pose_controls` says what can be moved: the controls grouped by body part, each control's
role, its rest position relative to the character, how it rotates, and which Rigify switches
exist. `mpfb_get_pose` says what the pose is now: which controls are off rest and by how much,
where the head, hands and feet are, the current value of each switch, and whether a limb is
stretched or cannot reach its target. Writing a pose is left out on purpose. The transform tool
(`mpfb_set_pose_bones` in NEXT_STEPS) has the right to its own request, and it will rely on the
names, the vocabulary and the character frame this request establishes.

Reading MPFB's source while scoping showed that the NEXT_STEPS entry claims more than MPFB has:

- **MPFB has no list of a generated Rigify rig's controls.** `RigifyHelpers.get_list_of_*_bones`
  names **meta-rig** bones, and is used only to convert a standard rig into a meta-rig. Control
  names such as `torso`, `hand_ik.L`, `upper_arm_ik_target.L` and `f_index.01_master.L` follow
  from Rigify's own naming for each `rigify_type`. What MPFB *does* supply is the **bone
  collections** of its meta-rig (`data/rigs/rigify/rig.human_toes.json`): `Torso`, `Arm.L (IK)`,
  `Arm.L (FK)`, `Arm.L (Tweak)`, `Fingers`, `Fingers (Detail)`, `Face (Primary)`, `Root`, and so on.
  These carry through to the generated rig, so they group the controls by body part on the live
  armature.
- **MPFB's IK helpers exist for the default rig only.** `ArmHelpers.get_instance()` returns a real
  implementation only for `"Default"`. The helpers add `left_hand_ik`, `left_elbow_ik`,
  `left_foot_ik`, `eye_ik` and similar bones, and they record each helper mode (`arm_mode`,
  `leg_mode`, `finger_mode`, `eye_mode`) on the armature through `RigHelpersProperties`. That makes
  them detectable. The `Default*Helpers` classes also name the default rig's arm, leg and finger
  chains, and carry the rotation limits MPFB applies.
- **`RigService.get_pose_as_dict()` does not record scale.** A Rigify fist is made by scaling the
  finger masters on Y, so saving that pose through MPFB loses the fist. This matters for the read-back
  here (see FR 9) and for any later pose-saving tool.

## Goals

**Primary:** an agent can find out, with no prior knowledge of the rig type, which bones to move to
pose a character, what each one does, and whether the pose it made is the one it meant to make.
It does this without `execute_blender_code` and without a screenshot.

**Secondary:**

- **Fix the vocabulary and the character frame that the posing tools share.** That covers body
  parts, roles, and what "forward", "left" and "up" mean for a character that has been moved and
  turned. The transform tool, hand shapes and pose loading inherit these, so they are settled here,
  once, in a shared module.
- **Answer for every rig, and classify the rigs MPFB builds posing tools for:** generated Rigify
  (`rigify_generated.human`, `.human_toes`, `.game_engine`), and `default` / `default_no_toes` with
  or without MPFB's IK helpers. Any other rig gets an honest unclassified listing instead of a
  refusal or a guess.
- **Report stretching and reach as facts.** The karate session found the arms stretching with no
  warning (`IK_Stretch` is 1.0 by default). This is the read-back that would have caught it.

## Non-goals

- Changing anything: transforms, switches, hand shapes, or a reset to rest. These belong to the
  transform tool's request, which this one comes before.
- Saving or loading a pose (see [Loading poses](../NEXT_STEPS.md#loading-poses)), and retargeting.
- **Garment sub-rigs** (`ponytail01` and the like). Both tools answer about the rig that deforms
  the basemesh, and they do not list sub-rigs or their bones.
- Classifying `game_engine`, `game_engine_with_breast`, `mixamo`, `mixamo_unity`, `cmu_mb`,
  `openpose` and custom rigs as standard rigs. They get the unclassified listing (FR 5).

## Functional requirements

### Both tools

1. **Subject.** `name` can be any object in the character's family, and `null` means the active
   object. It is resolved through `shared/subject_resolution.py`, and a miss is
   `blocked_by: "subject_not_found"`. **The rig is the armature that the basemesh's armature
   modifier points at.** When a character has both a meta-rig and a generated rig, the answer is
   therefore about the rig that actually moves the body. The answer reports `rig_object_name` and
   `rig_identified_as` (`RigService.identify_rig()`).
2. **Refusals, each naming the tool that fixes it:**
   - no rig: `blocked_by: "no_rig"`, naming `mpfb_add_rig`;
   - a Rigify **meta-rig** with no generated rig: `blocked_by: "rigify_not_generated"` (spelling to
     be settled against the glossary), naming `mpfb_generate_rigify_rig`. Posing a meta-rig is
     always a mistake, and listing its bones would make the mistake look supported.
3. **The character frame.** Every position and direction in both answers is given in the
   character's frame, not in world space: metres along `forward`, `left` and `up`, measured from
   the rig object's origin. `left` means the character's own left, the `.L` side. The frame comes
   from the rig object's world matrix, **not from the pose**, so a character whose torso is twisted
   still faces where its rig object faces. Every answer reports the frame itself (`origin`, and the
   three unit vectors in world space), so a world position is one transform away. Before this
   becomes a specification, the effort confirms against a real install which local axes MPFB's rig
   object uses for forward and for the character's left. It is believed to be −Y and +X, and it is
   not assumed. Positions are rounded to the millimetre.

### `mpfb_get_pose_controls`

4. **Classified rigs: controls grouped by body part.** The body parts are `root`, `torso`, `head`,
   `face`, `left_arm`, `right_arm`, `left_hand`, `right_hand`, `left_leg` and `right_leg`. Feet and
   toes belong to their leg. Each control reports:
   - `bone`: the pose bone name;
   - `role`: one of a small fixed vocabulary, settled during the effort. The proposal is
     `root`, `body` (Rigify's `torso`/`hips`/`chest`), `fk`, `ik_control` (a hand or foot IK
     target), `pole`, `finger_master`, `finger_segment`, `tweak` and `look_target`;
   - `chain`: for a limb, whether the control belongs to its IK or its FK chain, so an agent knows
     which bones the `IK_FK` switch (FR 6) puts in charge;
   - `source`: `rigify`, `mpfb_helper` or `rig`, so a helper bone MPFB added is told apart from a
     bone the rig file defines;
   - its rest `head` and its rest direction (head to tail, as a unit vector), in the character
     frame;
   - `rotation_mode` and the locked location, rotation and scale channels. The rig mixes
     `QUATERNION`, `XYZ`, `ZXY` and `YXZ`, and the transform tool will need these;
   - `hidden_by_default` for controls in a collection Rigify hides (the `(Tweak)` and `(Detail)`
     collections), so an agent can tell the controls it is meant to start with.
5. **Unclassified rigs** get `classified: false` and their bones as a hierarchy: name, parent,
   `deform`, rest head and direction in the character frame, and `rotation_mode`, with no body
   part and no role. **They are never guessed.** A wrong `left_hand` is worse than none. The
   answer says what *would* be classified, so the caller can decide to switch rigs.
6. **Rigify switches**, per limb: each custom property Rigify's limb rigs create (`IK_FK`,
   `IK_Stretch`, `pole_vector`, `IK_parent`, plus `FK_limb_follow` and others where they exist),
   given as the bone it lives on, the property name, its range, Rigify's own description, and what
   each end of the range means (for example, `IK_FK` 0.0 is IK). This tool reports **that the
   switch exists**. The current value belongs to FR 10. The properties are found on the live rig,
   not looked up in a table (see [Architecture](#architecture)).
7. **MPFB's helpers on a default rig.** Every answer for a default rig reports the four helper
   modes (`arm_mode`, `leg_mode`, `finger_mode`, `eye_mode`; `NONE` when unset), and the helper
   bones appear as controls with `source: "mpfb_helper"`. Once a helper is installed, the FK bones
   it drives are still listed, with `driven_by` naming the helper. Rotating them directly does
   nothing that lasts, and the answer has to say so.
8. **`body_parts` filter.** It takes a list of body parts and **defaults to every part except
   `face`**. A generated Rigify rig has a large number of face controls, and expressions on MPFB
   characters are made with shape keys
   ([FR 026](../done/026-face-units/README.md), [FR 027](../done/027-expression-library/README.md)).
   Following [How tools bound a large answer](../../specifications/responses.md#how-tools-bound-a-large-answer),
   the answer echoes `requested_body_parts` and always reports `counts_by_body_part` for **every**
   part, the omitted ones included. A caller that never asked for `face` can still see that it
   exists and how large it is. The description says that `face` must be named explicitly.

### `mpfb_get_pose`

9. **What is off rest.** Every control whose location, rotation or **scale** differs from rest,
   using `get_pose_as_dict()`'s threshold (0.0001) so the two agree on "posed". For each one:
   - `bone`, `body_part` and `role`, as in FR 4;
   - the location offset in the character frame;
   - the rotation from rest as an axis in the character frame plus degrees. An agent can read that,
     but not a quaternion in a bone's local axes;
   - the scale where it is not 1.

   Reporting scale departs from `get_pose_as_dict()` on purpose. The command docstring says why, per
   [where MPFB's own code paths disagree](../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).
   `at_rest: true` and an empty list mean the character is in its rest pose. The same
   `body_parts` filter as FR 8, with the same default and the same counts, applies here.
10. **The current value of every switch** from FR 6, per limb.
11. **Where the character is now.** The head, both hands and both feet, plus the hips. Each is
    given as its current position and its rest position in the character frame, measured on the
    **deforming** bones, so the result reports where the body actually is and not where a control
    happens to sit.
12. **Reach and stretch, per limb**, on classified rigs:
    - `reach_ratio`: the distance from the limb's root to its IK control, divided by the chain's
      rest length;
    - `stretched`: true when the deforming chain is longer than at rest. With `IK_Stretch` at 1.0
      this is how an over-reach shows up;
    - `target_unreachable`: true when the chain is fully extended and the IK control is still
      beyond its tip. This is how an over-reach shows up with stretch off, or on a default rig with
      helpers.

    These are [derived facts](../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact),
    and the response says how each one was computed.
13. **Unclassified rigs** get FR 9 without `body_part` and `role`, and leave out FR 10–12 as
    `null`. That is the `null` rule for "not computed", not `[]`, which would mean "none".

## Non-functional requirements

- **Read-only, and verifiably so.** Neither tool changes the pose, a mode, the selection or the
  active object. The bridge tests read all four before and after. Reading a rest position must not
  enter edit mode: rest data comes from `bone.matrix_local` on the armature data, not from edit
  bones.
- **Cheap enough to call after every pose change.** `mpfb_get_pose` is meant to be what an agent
  calls instead of `look`. Its default answer on a generated `human_toes` rig, posed, is measured
  during the effort, with a target of **8 KB**: the line `mpfb_get_character_summary` holds. The
  controls answer is called once per character and can be larger. It is measured too, and its
  ceiling is written down with the measurement, not before it.
- **Robust to rigs MPFB did not make**, and to a rig whose bones were renamed after generation: an
  unclassified answer, never an exception.
- **The vocabulary is for an agent, not a rigger.** `left_hand` and `ik_control`, never `Arm.L (IK)`
  or `MCH-`. The Rigify and MPFB names appear only as `bone`, which is what an agent passes back.

## Architecture

- **Two bridge commands**, `get_pose_controls` and `get_pose`, plus the two tool modules and the
  four other touch points listed in [CLAUDE.md](../../CLAUDE.md). Both tools are introspection
  tools in the sense of [vision.md](../../specifications/vision.md#target-tool-catalog).
- **Two shared modules, because the transform tool will need both:**
  - `character_frame.py`: the frame in FR 3, and conversion in both directions. It is a shared
    module before it has a second user, because a later `move_by: {"forward": 0.2}` that disagreed
    with this request's `forward` would be a silent and very visible defect.
  - `pose_controls.py`: classification. It reports which rig family the rig is, and gives each bone
    its body part, role, chain and source. `get_pose` uses it to label what is posed. Per
    [a summary is never a second opinion](../../specifications/responses.md#a-summary-is-never-a-second-opinion),
    the two commands must not classify separately.
- **Generated Rigify is classified from the live armature, not from a table.** Body part and chain
  come from the **bone collections** (`Arm.L (IK)` gives `left_arm` and IK). Role within a
  collection comes from Rigify's naming conventions (`_ik`, `_ik_target`, `_fk`, `_parent`,
  `_master`, `_tweak`). The switches come from the custom properties on the generated rig's
  `*_parent` bones. Rigify creates these through `make_property()` with a description and a range,
  so both can be read live. This follows the spirit of
  [names inside MPFB's node trees are read live](../../specifications/mpfb-integration.md#names-inside-mpfbs-node-trees-are-read-live-never-tabulated).
  The effort has to establish, against a real generated `human_toes` **and** a generated
  `game_engine` rig, whether collections plus suffixes are enough. The game engine meta-rig names
  its sides `_l`/`_r`, so suffix rules that work for `.L` may not work there. If they are not
  enough, the fallback is the `rig_ui.py` text Rigify writes into the file. That text is evidence to
  read during the effort, **not** something to parse at runtime.
- **The default rig is classified from a table, checked against MPFB.** The default rig has no
  meaningful collections, so a hand-kept table in `pose_controls.py` maps its bones to body parts.
  The table is the arm, leg and finger chains MPFB's `Default*Helpers` name, plus spine, neck, head
  and face. The bridge code may not import those helper modules
  ([never import MPFB submodules directly](../../specifications/architecture.md#never-import-mpfb-submodules-directly)).
  A bridge test therefore checks the table against them, in the way `tests/test_reference_drift.py`
  checks the vendored URL table, so a renamed bone in MPFB fails a test and does not silently
  unclassify a limb. The effort decides whether `_ROTATION_LIMITS` and `_ROTATION_LOCKS` are worth
  reporting as well. They are what the helpers enforce, but they are not on the bones until helpers
  are installed.
- **Helper detection** reads `RigHelpersProperties` on the armature, through
  `mpfb_surface.py`, which is how [module-level names MPFB does not publish](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish)
  are read. It is confirmed by the bones being present. If the property says a helper is
  installed and the bone is missing, that is reported, not resolved silently.
- **Rest versus current.** Rest positions come from `bone.matrix_local` and the rig object's world
  matrix. Current positions come from `pose_bone.matrix` after an evaluated depsgraph. `get_pose`
  reads after `view_layer.update()`, because a reading made right after another tool's write must
  reflect that write. The effort checks whether that update counts as a side effect anyone could
  observe.
- **What "deforming bone" means per family:** `DEF-` bones on Rigify, and on the default rig the
  bones themselves. FR 11 and FR 12 measure on these. On Rigify, measuring the controls instead
  would report where `hand_ik.L` is and not where the hand is, and those two differ exactly when a
  limb is in FK.

## Affected specifications

- [tool-interface.md](../../specifications/tool-interface.md#the-glossary): new glossary rows for
  `body_part`/`body_parts`, `role`, `chain`, the character frame's `forward`/`left`/`up`, and the
  two new `blocked_by` values.
- [responses.md](../../specifications/responses.md): the character frame as a standing rule for how
  any tool reports a position on a character (answers so far have reported none). It also extends
  [how tools bound a large answer](../../specifications/responses.md#how-tools-bound-a-large-answer)
  with a default filter that leaves a part out, which `section` on `mpfb_get_material_settings`
  does not.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): reading Rigify's generated
  structure live, which is the first time this package depends on **Rigify's** conventions and not
  only MPFB's, and the scale divergence from `get_pose_as_dict()`.
- [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one):
  `character_frame.py`, as a shared module created ahead of its second user, and why.
- [vision.md](../../specifications/vision.md#target-tool-catalog): Introspection goes from 9 tools
  to 11.

## Tests

- **Unit suite** (`tests/test_get_pose_controls.py`, `tests/test_get_pose.py`): argument shape
  only. `body_parts` is a list of strings, and its *vocabulary* is not checked here, per
  [validate the shape, never the vocabulary](../../specifications/tool-interface.md#validate-before-crossing-the-socket).
  Also what reaches the wire, and the bridge-path layer against `fake_bridge`. Add both to
  `test_vocabulary.py`'s coverage and to the description budget.
- **Bridge suite** (`bridge/test/tests/ccc_reading/`): one character per classified family. That is
  a default rig, a default rig with each arm helper mode and the master finger helper, and a
  generated `human_toes`, so the fixtures need Rigify enabled in the headless Blender, as
  `generate_rigify_rig`'s tests already do. Also one unclassified rig (`mixamo`), the meta-rig
  refusal, and the drift test for the default-rig table against MPFB's helpers. `get_pose` needs
  poses set *by the test* through plain `bpy`: an IK hand pulled past reach with stretch on and with
  stretch off, a finger master scaled on Y, and a rotated and translated rig object, which is what
  checks the character frame. A direct test of `character_frame.py` goes in `bbb_shared/`.
- **Live check, in this subdir, as a script.** Rebuild the karate session's starting point (a
  generated `human_toes` character, moved and turned away from the origin). Confirm that every bone
  the session moved by hand appears as a control with the role it was used for. Confirm that the
  frame's `forward` agrees with what a screenshot shows. Then pose the hands and lower the hips
  through `execute_blender_code`, and confirm that `mpfb_get_pose` reports the fists left in the
  air and the stretched arms the session found by looking. A generated `game_engine` rig, measured
  once, settles the suffix question in [Architecture](#architecture).
- **Smoke items:** one per tool in [verification/](../../verification/), on the smoke run's
  character, which has a rig.

## Decisions taken while scoping

- **Read-back is in this request**, not in the transform tool's (asked 2026-10-17). Both tools are
  read-only and share a classification. The transform tool's request then has a way to verify its
  own writes on day one.
- **Classified rigs are generated Rigify and default/default_no_toes, with or without helpers**
  (asked 2026-10-17). These are the rigs MPFB itself builds posing machinery for. The rest are
  listed unclassified.
- **Face controls are reported only on request**, through `body_parts` (asked 2026-10-17), and they
  are always counted.
- **Garment sub-rigs are ignored** by both tools (asked 2026-10-17).
- **The character frame comes from the rig object, not the pose.** This was not asked. It is the
  only definition under which `forward` stays put while the character is being posed, which the
  transform tool's relative offsets depend on.

## References

- [NEXT_STEPS: Posing support](../NEXT_STEPS.md#posing-support), the session this request comes from.
- mpfb2: `src/mpfb/services/rigservice.py` (`identify_rig`, `get_pose_as_dict`,
  `get_world_space_location_of_pose_bone`, `find_leg_length`, `find_arm_length`);
  `src/mpfb/entities/rigging/righelpers/` (the `Default*Helpers` chains and rotation limits);
  `src/mpfb/entities/rigging/rigifyhelpers/rigifyhelpers.py` (meta-rig names only);
  `src/mpfb/ui/rigging/standardrig/helperproperties/` (the helper modes);
  `src/mpfb/data/rigs/rigify/rig.human_toes.json` (`collections`, `rigify_ui`).
- Blender: `scripts/addons_core/rigify/rigs/limbs/limb_rigs.py` (`IK_FK`, `IK_Stretch`,
  `IK_parent` via `make_property`), `scripts/addons_core/rigify/ui.py` (`pole_vector`),
  `scripts/addons_core/rigify/generate.py` (`rig_id`, the generated `rig_ui` script).
