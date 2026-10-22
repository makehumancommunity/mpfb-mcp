# Hand shapes on a Rigify rig: named shapes, and a curl and spread per finger

**Status:** Proposed

This scopes the first gap left in [Posing support](../NEXT_STEPS.md#posing-support): **there is no
hand-shape helper.** [FR 042](../done/042-posing-bones-switches-and-reset/README.md) can make a
fist, but only by sending `scale_to` to every finger master, and the caller has to know that a
Rigify finger curls when its master is scaled on Y. Nothing in a tool description says so, and the
karate session found 0.45 by trial and error. The man-and-woman scene session measured what the
missing helper costs: four calls of fourteen entries each to curl, uncurl and curl again a soft
grip. That session also showed that **a curl has to be an amount**, not only a named shape. The
image needed a loose curl on one hand and none on the other, and none of `fist`, `open` or
`relaxed` would have given that.

**This request covers rigs generated from MPFB's Rigify meta-rigs, and nothing else**, and both
tool names say so. Those are the two that MPFB identifies as `rigify_generated.human` and
`rigify_generated.human_toes`, generated from `data/rigs/rigify/rig.human.json` and
`rig.human_toes.json`. On both, every finger is Rigify's `limbs.super_finger` with
`primary_rotation_axis: "X"` and no optional IK control, and each hand has a `super_palm`.
**`rigify_generated.game_engine` is out of scope** (see [Non-goals](#non-goals)), even though it is
also a generated Rigify rig. Reading `super_finger.py` while scoping showed how the finger moves,
and both tools are built on it:

- the **first knuckle** follows the master's **rotation**, through a `COPY_ROTATION` onto the first
  `MCH-…_drv` bone;
- **every later joint** bends by `(1 - scale.y) · π` about the primary axis, through a driver on
  each later `MCH-…_drv` bone. A Y scale above 1 bends them backwards. The master's X and Z scale
  are locked;
- the per-segment controls (`f_index.01.L`, `.02`, `.03`, FR 041's hidden `finger_segment` role)
  sit on top of that chain, so a rotation left on a segment adds to whatever the master does.

A curl therefore has two channels behind it, the master's rotation and its Y scale. A spread is a
rotation about the master's other axis. Neither is something a caller should have to know.

The default rig is where the 56-rotation cost was measured, and it is **not** in scope. It stays in
NEXT_STEPS as its own entry (see [Non-goals](#non-goals)).

## Goals

**Primary:** an agent can give either hand of a generated Rigify rig a **named shape** (`open`,
`relaxed`, `fist`, `pointing`, `grip`, `pinch`), and **curl, uncurl or spread any finger by an
amount**, in one call per change, without knowing which bone or which channel does it.

**Secondary:**

- **What the reader reports, the writer accepts.** A hand is read back as the same per-finger
  `curl` and `spread` the writer takes, so a read-back can be sent back unchanged. This is FR 042's
  rule for `rotate_to`, applied to hands.
- **A shape and its exceptions in one entry.** "A fist with the index straight" is
  `shape: "fist"` plus a `fingers` override. A shape is a starting point, not a closed list.
- **Measured, not assumed.** Every answer reports the joint angles the hand actually has and where
  each fingertip is. A constraint, a lock or an extreme body can stop a finger from ending where it
  was sent, and a caller checking a pinch needs the distance between the tips, not just
  `performed: true`.
- **Undoable across the socket**, as every posing write is: `restore_with` puts back what the call
  changed.

## Non-goals

- **Anything to do with the `game_engine` rig.** That includes `rigify_generated.game_engine`,
  which MPFB makes from a standard `game_engine` rig through its legacy convert-to-Rigify operator
  rather than from a Rigify meta-rig. It is refused (FR 2), it is not calibrated, it is not in the
  shape acceptance, and nothing in this request is designed around it. Its fingers do happen to be
  `super_finger`, but with Rigify's default parameters, `_l`/`_r` names, no palm control and every
  control in one `Bones` collection, which FR 041 needed a token table to classify. Supporting it
  would be a separate request with its own calibration. Until then, `mpfb_set_pose_bones`' `scale_to`
  on its finger masters is the way to curl its fingers.
- **The default rig, and every rig that is not generated Rigify.** Those rigs are refused, and the
  refusal names `mpfb_set_pose_bones` as the way to pose their fingers. A helper for the default
  rig, which is where the scene session's cost was measured, needs a different mechanism (three
  rotations per finger, with no master) and maybe MPFB's own finger helpers. It stays in
  [NEXT_STEPS](../NEXT_STEPS.md#posing-support).
- **Per-joint angles as an input.** This was asked and decided: the amount is a 0-1 `curl`. A
  "hook" (first knuckle straight, the later joints bent, which is what the karate session's
  scale-only fist was) or a 24/40/24-degree curl like the scene session's cannot be said exactly.
  `mpfb_set_pose_bones` on the master and segments is still the way to get those, and the reader
  reports them as not expressible (FR 13) rather than rounding them to a curl.
- **The shapes `spread`, `thumbs_up` and `peace`.** These were offered and left out of the first
  version. Per-finger `spread` is in scope, so each is one `fingers` dict away, and adding a shape
  later means adding a row to a table (see [Architecture](#architecture)).
- **User-defined or saved hand shapes**, and loading them from files. That belongs with
  [Loading poses](../NEXT_STEPS.md#loading-poses).
- **The palm control** (`palm.L`, Rigify's `super_palm`). It cups the metacarpals rather than
  moving a finger. It is not written.
  The reader reports it when it is off rest (FR 13).
- **Rigify's `finger_curve`** (the rubber-hose B-bone setting on each master). It is not written,
  and it is reported when it is off its default, as `mpfb_get_pose` already does.
- **Placing a hand at a point**, which is [its own NEXT_STEPS entry](../NEXT_STEPS.md#a-hand-cannot-be-placed-at-a-point-on-a-standard-rig);
  **detecting interpenetration** with a held object or the other hand, which is
  [its own entry](../NEXT_STEPS.md#nothing-reports-that-two-meshes-interpenetrate);
  **shapes that adapt to the body's proportions** (a shape is a table of amounts, and the answer
  measures the result so that a caller can adjust it); **toes**; **keyframes**.

## Functional requirements

### Both tools

1. **Subject, rig and refusals are FR 041's**, through `resolve_posing_subject()`. `name` is any
   object in the character's family, and `null` means the active object. The answer reports
   `rig_object_name` and `rig_identified_as`. `rig_not_found` and `rigify_not_generated` mean what
   they mean everywhere else.
2. **Only a rig generated from MPFB's Rigify meta-rigs is accepted**: `rig_identified_as` must be
   `rigify_generated.human` or `rigify_generated.human_toes`. Every other rig is refused with
   `blocked_by: "rig_not_supported"` and `supported_rigs` listing the two (spelling to be settled
   against the glossary). That covers the default rig, `mixamo`, a meta-rig not yet generated (which
   keeps FR 041's `rigify_not_generated`) and **`rigify_generated.game_engine`**. The refusal names
   `mpfb_set_pose_bones` as the way to pose that rig's fingers. An accepted rig is then also checked
   on the live bones: each finger needs its master, its segment chain and the driven `MCH-…_drv`
   bones Rigify builds. A rig that was edited after generation and fails the check gives a
   resolution error naming what is missing, never a guess.
3. **The vocabulary.** A hand is addressed as `body_part` `left_hand` or `right_hand`, FR 041's
   own names. A finger is one of `thumb`, `index`, `middle`, `ring`, `pinky`. On a rig that is
   missing a finger the hand is still accepted; only an entry that names the missing finger is a
   resolution error (`finger_not_on_rig`, spelling to be settled). Each answer lists the fingers
   found per hand.
4. **`curl`** is a number. `0.0` is the finger at rest (straight, as the rig was built) and `1.0`
   is fully closed, which is how the finger sits in `fist`. It maps linearly onto the finger's
   joints: the first knuckle turns by `curl × knuckle_degrees`, and every later joint by
   `curl × joint_degrees`, both per finger. Those two numbers are calibrated during the effort and
   recorded in the shared module (see [Architecture](#architecture)). The range is
   **`-0.2 … 1.0`**. The negative part bends the finger backwards, about 20° at each joint if
   full curl is 90-100°. That is enough for a splayed "stop" hand or fingers pressed flat against
   a surface, without joints that look broken. Anything outside the range is refused before
   sending, as `mpfb_set_macro_details`' 0-1 is.
5. **`spread`** is a number in `-1.0 … 1.0`. `0.0` is rest, and `1.0` is the finger's full natural
   sideways reach, calibrated per finger like the curl. The sign is defined per finger, and it is
   the same on both hands, so one value spreads both hands alike:
   - **`index`, `ring`, `pinky`**: positive moves the finger **away from the middle finger**.
   - **`middle`**: positive leans it **towards the index**, negative towards the ring finger.
   - **`thumb`**: positive swings it **away from the side of the palm** (abduction), negative
     brings it back against the palm.

   So a fanned hand is positive on every finger but the middle, and a peace sign is index
   `spread: 1` with middle `spread: -1`.
6. **A curl and a spread compose in a fixed order**: the spread swings the finger sideways at the
   first knuckle, and the curl then bends it about its own, already-swung axis, as a real knuckle
   does. Writing a curl never changes the spread, and the reverse holds too.

### `mpfb_get_rigify_hand_shape`

7. **Reads both hands by default**, or the ones named in `body_parts` (`left_hand`, `right_hand`).
   Naming any other body part is refused and the refusal lists the two it takes. It changes
   nothing, and it updates the depsgraph before it reads, as `mpfb_get_pose` does.
8. **Per hand**, `fingers` is keyed by finger name, and each finger carries `curl` and `spread`
   **in exactly the shape the writer takes**, plus what was measured: `joint_degrees` (the angle at
   each joint, read from the deforming bones, first knuckle first) and `tip` (where the fingertip
   is, in the character frame). The hand's answer is small enough that `compact` is not needed:
   about 3 KB for two hands is the target, and the actual size is measured.
9. **`curl` and `spread` are derived**, and the answer says how. They come from the master's
   rotation and Y scale through the inverse of FR 4-6, as a
   [derived fact](../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact).
   The derivation runs on the control channels. `joint_degrees` comes from the deforming bones,
   which is the ground truth the derivation can be checked against.
10. **`matches_shape`** per hand: the name of the shape whose amounts the hand matches within a
    stated tolerance, or `null`. A hand at rest matches `open`. This is how a caller learns that a
    character it did not pose is making a fist.
11. **`known_shapes`** is on every answer: the shapes and, for each, its per-finger amounts. It is
    the vocabulary a caller needs before writing. It costs little in an answer, and it would cost
    a lot in every tool description, which is the reasoning `mpfb_get_face_units` uses for its
    `known_face_units`.

### `mpfb_set_rigify_hand_shape`

12. **`hands`, a list of entries**, at most one per hand. Each entry has `body_part`, and at least
    one of:
    - `shape`: a name from `known_shapes`. All five fingers are set from the shape's table.
    - `fingers`: a dict keyed by finger name, each holding `curl`, `spread` or both. It is applied
      **after** `shape`, so it overrides the shape finger by finger. Without `shape`, only the
      fingers named are written, and within a finger only the amounts named are written. Leaving a
      finger or an amount out means "leave it alone", never "reset it", which is the rule
      `mpfb_set_macro_details` follows.

    `symmetry` per entry (default false) applies the same entry to the other hand. Curl and spread
    do not depend on the side (FR 5), so the instruction is copied without any mirroring. An entry
    for the other hand in the same call is a resolution error, as in FR 042.
13. **A written finger is the whole finger.** When a call writes a finger, that finger's segment
    controls are returned to rest, because a rotation left on a segment would add to the curl and
    make the answer's `curl` untrue. The segments' previous transforms are reported, and they go
    into `restore_with` (FR 16). A finger that is not written is not touched, segments included.
14. **Only what is in charge is written, and all or nothing.** FR 042's rules carry over, through
    `shared/pose_writing.py`. A locked channel, a driven channel, or a finger whose IK control is in
    charge (a Rigify finger built with `make_extra_ik_control` and its `FK_IK` above 0) is a
    resolution error naming the finger. Name-level checks run before anything is written. The rest
    use FR 042's snapshot, write, check and restore, so a batch that fails anywhere leaves every
    channel exactly as it was. Edit mode is refused (`rig_in_edit_mode`), and a rig showing its
    rest position is handled as FR 042 handles it. No mode, selection or active object is borrowed,
    and no operator is called.
15. **The answer, per hand**: the hand before and after, in FR 8's shape (`curl`, `spread`,
    `joint_degrees`, `tip` per finger), and `matches_shape` after. Per finger it also gives
    `achieved` and, when that is false, `deviation`, measured on `joint_degrees` against what the
    amounts ask for, with FR 042's 0.5° tolerance. Then `segments_reset`, and
    `overwritten_on_frame_change` where a channel is animated. Key spellings follow the glossary's
    whole-field `<field>_before` / `<field>_after` rule.
16. **`restore_with`**, keyed by the tool to call. It holds the `mpfb_set_rigify_hand_shape`
    entries that put back each changed finger's curl and spread and, when segments were reset, the
    `mpfb_set_pose_bones` entries (`rotate_to`, `scale_to`) that put them back too. This is FR 042's
    shape. A shape overwrites a hand someone else may have posed by hand, so the previous state is
    owed even though nothing is reset to rest unless the caller asked for `open`.

### The shapes

17. **Six shapes**: `open` (every finger at rest), `relaxed` (a light natural curl, increasing
    from index to pinky, with the thumb slightly in), `fist` (every finger at `curl` 1.0 and the
    thumb closed over the index and middle fingers), `pointing` (`fist`, with the index at 0.0),
    `grip` (curled around a cylinder of about 4 cm, the thumb opposed), and `pinch` (the thumb tip
    and the index tip meeting, the other fingers relaxed). Each is a row of per-finger amounts in
    FR 4-5's vocabulary, so **every shape is something the reader can report and a caller can
    write by hand**.
18. **Acceptance per shape**, on a default `human_toes` character, is checked in the live check:
    - `fist`: no fingertip inside the palm, judged by screenshot.
    - `pinch`: thumb and index tips within 1 cm, measured from `tip`.
    - `grip`: a 4 cm cylinder fits the hand, judged by screenshot.
    - `pointing`: the index's `joint_degrees` all under 5°.

    The same rows are then run on a generated `human` rig, and the result is written down. The two
    meta-rigs share their hands, so a shape that misses on `human` is a calibration finding, not a
    reason for a second table.

## Non-functional requirements

- **One concept, one spelling.** `body_part`, `symmetry`, `achieved`, `deviation`, `restore_with`
  and the character frame are already in the
  [glossary](../../specifications/tool-interface.md#the-glossary) and keep their meaning. The new
  words are `hands`, `shape`, `fingers`, `curl`, `spread`, `joint_degrees`, `tip`,
  `matches_shape`, `known_shapes` and `segments_reset`, and they are added to it. `shape` must not
  collide with anything: the census in `tests/test_vocabulary.py` checks one JSON type per
  argument name.
- **Both names say Rigify.** These are the first tools whose name carries the rig family. The
  reason is that the tool cannot work anywhere else, and a caller that picks a tool by its name
  should not reach for this one on a default rig. The other posing tools work on every rig and keep
  their names.
- **Cheap.** One call per change is the whole point. Through a windowed bridge every call costs
  about a second no matter what it does (FR 041), and the writes are 10 masters and at most 30
  segments. Both answers are measured, aiming at 3 KB for the reader and 8 KB for a two-hand write
  with `restore_with`. The description budget in `tests/test_description_budget.py` is re-measured
  with the two new tools.
- **Predictable.** A shape is a fixed table, an amount maps linearly, and nothing is inferred from
  what the caller might have meant. The only adaptation is in the report: the answer measures what
  happened.
- **Robust to an edited rig.** A missing finger, segment or `MCH-…_drv` bone is a resolution error
  that names what was looked for, never an exception.

## Architecture

- **Two bridge commands**, `get_rigify_hand_shape` and `set_rigify_hand_shape`, two tool modules,
  and the usual four touch points listed in [CLAUDE.md](../../CLAUDE.md).
- **One new shared module, `shared/rigify_hands.py`**, with two users, which is what
  [warrants one](../../specifications/architecture.md#shared-modules-and-what-warrants-one). It
  finds a hand's fingers (from FR 041's `finger_master` and `finger_segment` controls, grouped by
  the finger token in the name, `thumb`, `f_index`, `f_middle`, `f_ring`, `f_pinky`), maps amounts to channels and channels back to
  amounts, holds the calibration and the shape table, and measures `joint_degrees` and `tip`. It
  takes `services` for nothing, because none of this is MPFB's. Writing goes through
  `pose_writing.py`, the frame through `character_frame.py`, and classification through
  `pose_controls.py`. None of that is copied.
- **The finger mechanics are read live, by Rigify's conventions**, as
  [mpfb-integration.md](../../specifications/mpfb-integration.md#a-generated-rigify-rig-is-read-live-by-rigifys-conventions)
  requires. The bend axis and its sign are read from the driver on each finger's later
  `MCH-…_drv` bones (`(1-sy)*pi` on `+X`, which the meta-rigs' `primary_rotation_axis: "X"` gives),
  and are not assumed. The spread axis is the master's remaining axis, perpendicular to both the
  bend axis and the bone. A driver expression that is not one of Rigify's `axis_options` is a
  resolution error (FR 2). A bridge test checks the reading against `super_finger.py`'s table and
  against the meta-rigs' parameters, so that a change to either meta-rig shows up as a failing
  test.
- **The calibration is this package's data, and it is in degrees**, which is what makes it
  independent of the size of the body. Per finger there is `knuckle_degrees`, `joint_degrees` (the
  later joints all bend together, because Rigify drives them from one scale) and a spread maximum.
  One fact is already known and is the starting point: the karate session's `scale.y = 0.45` closed
  the fist with the later joints at `(1 - 0.45) · π ≈ 99°` and the knuckle at rest, which looked
  closed in a screenshot. The effort sets the numbers on `human_toes`, by the FR 18 acceptance, and
  writes them down with how each was found.
- **The thumb is a `super_finger` too**, but its first segment is the metacarpal, so its "knuckle"
  is the base of the thumb and its rest direction is not the other fingers'. It gets its own
  calibration row. Whether curl and spread alone can reach `pinch` and `grip` is settled by
  evidence during the effort, by a rule already decided (see
  [Decided by evidence during the effort](#decided-by-evidence-during-the-effort)).
- **The shape table** sits beside the calibration, one row per shape, each row a `fingers` dict.
  Shape and finger names are this package's own vocabulary, like `mode`, so they are checked on
  both ends. The tool side holds the names, and a unit test reads the bridge module's source as
  data and requires the two lists to agree, as `tests/test_bridge_connection.py` does for
  `PROTOCOL_VERSION`.
- **Deriving the amounts (FR 9)**: the master's rotation is split into a swing about the spread
  axis, a swing about the bend axis, and a twist about the bone, in FR 6's order. The Y scale gives
  the later joints. If the knuckle and the later joints imply different curls beyond tolerance, or
  there is twist, or a segment or the palm is off rest, the finger is reported with
  `expressible: false` and a reason. Its `curl` is then the best fit (least squares over
  `joint_degrees`), and it is labelled as a fit, never presented as exact.

## Affected specifications

- [tool-interface.md](../../specifications/tool-interface.md#the-glossary): the new words in
  [Non-functional requirements](#non-functional-requirements); `rig_not_supported` with
  `supported_rigs`, and `finger_not_on_rig`, under the posing refusals; a third user of
  `restore_with`; and, under "Kept on purpose", why these two tool names carry the rig family when
  the other posing tools do not.
- [mpfb-integration.md](../../specifications/mpfb-integration.md#a-generated-rigify-rig-is-read-live-by-rigifys-conventions):
  the finger mechanism, bend axis and sign read from the `MCH-…_drv` drivers, beside the
  collections, naming and switches it already lists.
- [responses.md](../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact):
  an amount derived from control channels, reported beside the measurement it can be checked
  against (`joint_degrees`), with `expressible: false` when the derivation does not fit.
- [mutating-tools.md](../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list):
  a write that silently resets controls it was not asked about (FR 13's segments) owes them in
  `restore_with`.
- [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one):
  `rigify_hands.py`.
- [vision.md](../../specifications/vision.md#target-tool-catalog): Introspection goes from 11 to 12
  tools, and Creation and modification from 24 to 25.
- The server instructions in [`__init__.py`](../../src/mpfbmcp/__init__.py): the posing sentence
  gains a clause naming the hand tools for Rigify rigs.

## Tests

- **Unit suite** (`tests/test_get_rigify_hand_shape.py`, `tests/test_set_rigify_hand_shape.py`),
  shape only:
  - `hands` is a non-empty list of dicts with known keys, and a misspelled `fingres` is refused;
  - each entry has `shape` or `fingers` or both, a finger has `curl` or `spread` or both, and
    nothing else;
  - `curl` and `spread` are finite numbers in range and not `bool`s, and `symmetry` is a real
    bool;
  - a literal `body_part` named twice is refused;
  - finger and shape names are checked against the tool's list, and that list is checked against
    the bridge's table;
  - `body_parts` in the reader is a list of distinct strings, through `arguments.validated_names`;
  - `body_part` values themselves are checked bridge-side, as in every posing tool.

  Add both tools to `test_vocabulary.py`, the description budget and `test_verification_smoke.py`.
- **Bridge suite**:
  - `bbb_shared/rigify_hands_test.py`: amounts to channels and back within 1e-6 for every finger,
    including negative curl and both spread signs; the axis and sign read from a driver for each
    of Rigify's `axis_options`; and `expressible: false` for a twisted master, an off-rest segment
    and a hook.
  - `ccc_reading/get_rigify_hand_shape_test.py`:
    - a hand at rest is `open`;
    - a master scaled to 0.45 on Y by plain `bpy` reads as the curl that scale implies, with
      `joint_degrees` within 0.5° of 99°;
    - `tip` holds on a rig object that has been moved and turned;
    - a default rig, `mixamo` and a generated `game_engine` rig are refused with
      `rig_not_supported`;
    - nothing changes.
  - `ddd_mutating/set_rigify_hand_shape_test.py`, on `human_toes` and `human`:
    - every shape reads back with `matches_shape` equal to itself;
    - one finger's curl changes and nothing else does, for curl and spread each;
    - `shape` plus a `fingers` override, and `symmetry`;
    - the segments are reset and restored through `restore_with`, and `restore_with` round-trips
      every channel within 1e-6;
    - the FR 14 refusals and the rollback;
    - nothing is borrowed.
- **Live check, in this subdir, as a script.** On a generated `human_toes` character moved and
  turned away from the origin, using only mpfb-mcp tools:
  - each shape on both hands, with a screenshot of the hands from the front and the side checked
    against the FR 18 acceptance;
  - the scene session's case in one call: a loose curl on one hand and none on the other;
  - `pointing` built as `fist` plus an override;
  - a reset with `mpfb_reset_pose` on `left_hand`, which must read back as `open`.

  Then the same rows once on a generated `human` rig, with the results and the final calibration
  table written down here.
- **Smoke items:** one per tool, and both skip on a rig that is not Rigify, as
  `mpfb_set_pose_switches`' does. The reader reads the run's character. The smoke run allows one
  call per item and should leave the pose as it found it, so the writer's item is `shape: "open"`
  on the left hand. On the run's character that hand is already at rest, so the call changes
  nothing and answers `performed: false`, which is a valid answer.

## Decisions taken while scoping

Asked on 2026-10-22:

- **Rigify only, and the tool names say so.** The default rig is a separate effort.
- **Only rigs generated from MPFB's Rigify meta-rigs** (`human`, `human_toes`). Anything to do with
  the `game_engine` rig, the Rigify conversion of it included, is out of scope and refused.
- **The amount is a 0-1 `curl`**, with 1.0 the fist's closed finger, and the answer reports the
  measured joint angles. Per-joint degrees as an input were offered and declined.
- **There is a reader tool**, whose per-finger answer is the writer's argument shape.
- **Spread is per finger.**
- **The first shapes are `open`, `relaxed`, `fist`, `pointing`, `grip` and `pinch`.** `spread`,
  `thumbs_up` and `peace` were offered and left out.
- **The spread sign** (FR 5): away from the middle finger for index, ring and pinky; towards the
  index for the middle finger; abduction for the thumb. A single direction for every finger, and no
  spread on the middle finger at all, were the alternatives.
- **`curl` goes down to `-0.2`** (FR 4). The alternatives were no negative curl, and a bound
  measured during the effort.
- **Thumb opposition is added only if the evidence needs it**
  ([below](#decided-by-evidence-during-the-effort)). The alternatives were adding it up front, and
  dropping any shape that curl and spread cannot reach.

*Not asked*, each argued where it is stated: shapes as a starting point with `fingers` overrides
(FR 12); unnamed fingers and amounts left alone (FR 12); a written finger's segments reset (FR 13);
the palm and `finger_curve` left alone and reported (Non-goals); the bend axis read from Rigify's
drivers and checked against the meta-rigs rather than assumed (Architecture); a calibration in degrees (Architecture);
shape and finger names checked on both ends (Architecture).

## Decided by evidence during the effort

None of the questions asked while scoping is still open. One decision has a fixed rule, but its
outcome depends on what the live rig shows:

- **Thumb opposition, only if needed.** A thumb that meets the index fingertip normally rotates
  about its own long axis as well. The effort first builds `pinch` and `grip` from curl and spread
  alone. If the thumb and index tips cannot get within FR 18's 1 cm that way, the thumb gains a
  third amount, **`opposition`** (`0.0 … 1.0`, thumb only, 0 at rest). It is added to the writer's
  argument and the reader's answer together, and the outcome is recorded here either way. This
  was preferred to a shape the reader's vocabulary cannot express.

## References

- [NEXT_STEPS: Posing support](../NEXT_STEPS.md#posing-support), the entry this scopes, with both
  sessions' numbers.
- [FR 041](../done/041-pose-controls-and-read-back/README.md) (`finger_master`, `finger_segment`,
  `finger_curve` as a setting, the frame) and
  [FR 042](../done/042-posing-bones-switches-and-reset/README.md) (`pose_writing.py`, the
  snapshot and restore, `achieved`, `restore_with`, and the fist through `scale_to`).
- Blender: `scripts/addons_core/rigify/rigs/limbs/super_finger.py`: `make_master_control` (`_master`,
  X/Z scale locked), `rig_mch_bend_bone` (the first `MCH-…_drv` copies the master's rotation, the
  later ones are driven by `(1-sy)*pi`), `axis_options`, `make_extra_ik_control` and `FK_IK`, and
  `finger_curve`; `super_palm.py` (the palm control, `human`/`human_toes` only).
- mpfb2: `src/mpfb/data/rigs/rigify/rig.human.json` and `rig.human_toes.json`
  (`limbs.super_finger`, `primary_rotation_axis: "X"`, no extra IK control);
  `src/mpfb/entities/rigging/rigifyhelpers/rigifyhelpers.py` (`_setup_fingers`: how the
  out-of-scope `game_engine` conversion makes its fingers, with Rigify's default parameters).
