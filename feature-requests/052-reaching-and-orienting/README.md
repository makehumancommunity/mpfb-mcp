# Reaching a point and orienting a hand, on the rig a character already has

**Status:** Proposed

This is one of two requests scoping [A hand cannot be placed at a point on a standard
rig](../NEXT_STEPS.md#a-hand-cannot-be-placed-at-a-point-on-a-standard-rig). [FR
053](../053-rig-helpers/README.md) is the other, and switches on MPFB's helper bones for a caller
who wants live IK controls.

**On MPFB's standard rigs nothing can say "put the hand there".** `mpfb_set_pose_bones` offers
`move_to`, and it needs a bone whose role is `ik_control`. A `default_no_toes` rig has none, so a
caller picks directions for `upperarm01`, `lowerarm01` and `wrist`, reads `mpfb_get_pose`'s
landmarks and tries again. The man-and-woman session did that about ten times per arm, the largest
single cost it paid. And the rig cannot be swapped by then: `mpfb_add_rig` refuses with
`already_rigged` once the character is dressed.

**Placing is only half of it, as the second session found on Rigify**, where `move_to` on `hand_ik`
does work ([Hand-to-hand contact on a Rigify rig](../NEXT_STEPS.md#hand-to-hand-contact-on-rigify)).
`aim` plus `twist` does not say what twist 0 is relative to: on one hand, 0, -90, +90 and 180 gave
"back of hand forward", "palm forward", "hands crossed" and "palms facing". What worked was setting
a world matrix in bpy from a palm normal and a finger direction. That was most of an hour.

**Measured while scoping**, headless, on an unposed `default_no_toes`, with a throwaway IK
constraint on `lowerarm02.L` (`chain_count` 4, stretch off) whose result was copied into the four FK
bones and the constraint removed:

| Target | Wrist error | Time | Note |
|---|---|---|---|
| In front of the chest | 0.01 mm | 19 ms | Elbow pointed forward, level with the shoulder |
| Across the body | 0.01 mm | 17 ms | |
| Overhead, slightly too far | 48 mm | 18 ms | The honest shortfall: as far as it goes |
| Far out of reach | 1052 mm | 18 ms | Likewise |

So the mechanism works, and the elbow is what is left to design. Setting `wrist.L`'s orientation
through `pose_bone.matrix` from a palm normal and a finger direction reached 0.0 degrees on both, in
3 ms.

## Goals

**Primary:** one entry puts a limb's tip at a point, and one entry says which way a hand faces, on
the rig the character already has, in one call rather than ten.

**Secondary:**

- **The rig is left as it was found**, so `mpfb_get_pose`, `mpfb_reset_pose`'s `restore_with`, pose
  loading and exports go on working unchanged. What gets written is ordinary FK channels.
- **`move_to`'s limit is stated where it is met**, in the tool description and in its refusal.

## Non-goals

- **Live IK controls.** That is [FR 053](../053-rig-helpers/README.md).
- **Finding a pose that does not intersect.** The 500-placement search that made a hand hold stays a
  caller's job, with [FR 048](../done/048-measuring-mesh-assets/README.md)'s `mpfb_check_intersections`
  as its score.
- **Bending the spine or stepping** to extend a reach. A limb that cannot get there says so.
- **Joint limits.** The solver can produce an elbow no arm has. FR 8 makes it visible rather than
  impossible, and limits can follow if a session shows they are needed.
- **The written-fingers-only mode and the thumb note** from the same NEXT_STEPS entry. They stay
  there.

## Functional requirements

### `reach_to`

1. **`reach_to` is a third kind of position change on a `mpfb_set_pose_bones` entry**, beside
   `move_by` and `move_to`, and excludes them. It names where the entry's bone's head should go,
   reached by turning the chain above it.
2. **The bone is a limb's tip, on any rig whose FK chain is in charge:** `wrist.*` and `foot.*` on a
   default rig, the same limbs on `game_engine`, and Rigify's FK tips when `IK_FK` has the limb in
   FK.
3. **A tip that an IK control moves is refused**, with `write_instead` naming the `move_to` that
   would work: `hand_ik.L` on Rigify in IK, `left_hand_ik` with FR 053's helpers on. Any other bone
   is refused as not a limb's tip.
4. **The point says its own frame.** `{forward, left, up}` is the character frame, as
   `mpfb_get_pose`'s `head` is. `{x, y, z}` is world space, as `mpfb_place_character`'s `position`
   is. Mixed keys are refused on this side of the socket. Reaching for another character's hand is
   the reason for the second form: a caller otherwise has to convert between two frames, by hand,
   for the common case.
5. **`bend_toward`, optional and only with `reach_to`, is a direction the middle joint should
   point**, in the same two forms. When it is omitted, the elbow goes outward and down and the knee
   forward, and the answer reports the direction used. The scoping run's elbow pointed forward with
   nothing to steer it, and that is not a pose anyone means.
6. **Out of reach is not a refusal.** The limb goes as far as it can, and `achieved` reports the
   `deviation`, as it does for every other write. It is a measurement a caller can act on, and
   refusing would hide how far short it fell.
7. **The answer lists every bone written** for the entry (`chain_written`), since the caller named
   only the tip. All of them are in `mpfb_reset_pose`'s reach, and the snapshot and rollback of FR
   042 cover them.
8. **Each reach reports `bend_degrees`**, the angle at the middle joint against its rest angle, so
   that an elbow bent backwards can be seen in the answer rather than in a render.
9. **Naming a chain bone elsewhere in the same call is refused**, since which write wins would be
   arbitrary. `symmetry: true` mirrors a character-frame `reach_to` and is refused with a world
   point.

### `orient`

10. **`orient` is a kind of rotation change**, beside `rotate_by`, `rotate_to` and `aim`, and
    excludes them. It takes `fingers`, the direction the fingers point, and `palm`, the direction
    the palm faces, each in either form from FR 4.
11. **`fingers` is kept exactly and `palm` made perpendicular to it**, the answer reporting the
    `palm` used. Parallel directions are refused.
12. **What it means is defined on the deforming hand bone, and it is written to the control in
    charge.** On a default rig those are one bone. On Rigify and with helpers, the offset between
    the two is read from the rest pose, never tabulated.
13. **Which way the palm faces is computed from the hand's own bones**, the direction along the hand
    crossed with index-to-pinky and signed by side. Scoping found the local +X of `wrist.L` and
    `DEF-hand.L` agrees with that to within 3 degrees, and -X on `.R`, but `hand_l` on `game_engine`
    has no such axis (0.67 on X and 0.74 on Z). A table of axes would have been wrong for one
    family.
14. **A bone that is not a hand is refused** (`orient_not_a_hand`).
15. **`achieved` reports `fingers_error_degrees` and `palm_error_degrees`**, measured on the
    deforming bone.
16. **An entry may carry `reach_to` and `orient` together**, which is how a hand gets put somewhere
    facing some way. The reach is solved first, since it moves everything below it.

### What it says about `move_to`

17. **`mpfb_set_pose_bones`' description says that `move_to` needs an `ik_control`**, and that
    standard rigs have none unless FR 053's helpers are on. This was NEXT_STEPS' "say so", and it is
    worth having whatever else lands.
18. **Where `move_to` on a limb's FK tip is refused, the refusal's `write_instead` names
    `reach_to`.**

## Non-functional requirements

- **Nothing is left behind.** The throwaway constraint and its target are gone however the call
  ends, including through an exception, and the object count, the constraint count and the selection
  are as they were.
- **One call instead of ten.** A live check on the man-and-woman case must place both hands with one
  `mpfb_set_pose_bones` call per attempt.
- **Readable description.** This adds two kinds and one option to a tool that already explains
  itself at length, so the description budget needs watching, and the worked detail belongs in the
  docstring. Since [FR 059](../done/059-what-a-session-pays-for/README.md) that description also
  carries the limb and `achieved` definitions the answers no longer restate, and the answer's
  `landmarks` and `limbs` hold only what a call moved, measured, naming the rest - which a reach
  moves, so a reach is reported in full without anything here changing.

## Architecture

- **`shared/limb_solver.py`** holds the solve, so a later tool can share it. It takes the rig, a
  limb's chain from the limb tables already in `shared/pose_controls.py` (`_DEFAULT_LIMBS`,
  `_rigify_limbs`), a point and a bend, and returns the matrices. `shared/pose_writing.py` writes
  them, so locks, drivers, `parents_first`, the snapshot and `lock_violations` all apply unchanged.
- **The constraint is the measured way, not the only one.** It needs an object as its target: an
  Empty linked to the scene for the duration, removed in a `finally`. If the effort finds that an
  update in a crowded file makes this expensive, an iterative solve in `mathutils` needs no scene
  object. Record which was used, and why.
- **Steer the elbow after solving rather than through `pole_angle`.** Swinging the solved chain
  about the root-to-target line keeps the tip where it is and needs no per-rig angle. This has not
  been measured yet, and is the first thing the effort should check.
- **A world-space point goes through `Frame`**, in `shared/character_frame.py`, which is where the
  conversion already lives.
- **The near side checks shape only:** the keys of a point, finite numbers, `bend_toward` only
  beside `reach_to`, and what kinds may be combined. **No bone vocabulary**, as for every other
  entry.
- **Pitfall:** `pose_bone.matrix` reads parents' current pose, so a depsgraph update is needed per
  bone, as `parents_first` already arranges.
- **Pitfall:** `wrist` is a child of the arm chain, so a reach alone also turns the hand. FR 16
  exists for this, and the description says so.

## Affected specifications

- [tool-interface.md](../../specifications/tool-interface.md): the glossary (`reach_to`,
  `bend_toward`, `orient`, `chain_written`), and a point's keys saying its frame.
- [responses.md](../../specifications/responses.md#a-position-on-a-character-is-in-the-character-frame):
  the one exception to reporting in the character frame, which is what a caller may *send*.
- [mutating-tools.md](../../specifications/mutating-tools.md): a write naming one bone and changing
  a chain owes the list; a measured deviation rather than a refusal for an unreachable target.
- [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one):
  `limb_solver.py`.
- [vision.md](../../specifications/vision.md): no change; this is within posing.

## Tests

- **Unit, `tests/test_set_pose_bones.py`:** both forms of a point, mixed keys refused, `bend_toward`
  without `reach_to` refused, `reach_to` beside `move_to` refused, `orient`'s two directions and
  their shape. No bone vocabulary.
- **`bridge/test/tests/bbb_shared/limb_solver_test.py`:** known geometry; a reachable point within a
  tolerance, an unreachable one by the expected shortfall, the steering keeping the tip fixed, and
  nothing left in the scene after an induced failure.
- **`ddd_mutating/set_pose_bones_test.py`:** both rig families on a moved and turned rig; every
  refusal; `chain_written`; rollback when another entry in the batch fails; `mpfb_reset_pose`
  undoing a reach; `orient` on both sides of every family, against the palm direction computed from
  the geometry.
- **Live check, a script in this subdir:** the man-and-woman case rebuilt: two characters on
  `default_no_toes`, hands at a shared point through the world-space form, palms facing. Record the
  calls it took, the errors, and a render.
- **No smoke item.** No tool is added, and the existing item's default call is unchanged.

## Decisions taken while scoping

Asked on 2026-11-03:

- **Both mechanisms, in two requests.** The solver here and helpers in FR 053. Either alone, one
  request for both, and only documenting the limit were the alternatives.
- **`orient` belongs here**, rather than staying in NEXT_STEPS, because a placed hand with an
  arbitrary orientation is what cost the hour on Rigify.

*Not asked*, each argued where it is stated: entries on `mpfb_set_pose_bones` rather than a new
tool, because a whole stance is one call; a point's keys naming its frame (FR 4); out of reach as a
measurement (FR 6); computing the palm rather than tabulating it (FR 13); no joint limits yet
(Non-goals).

## References

- [NEXT_STEPS: A hand cannot be placed at a point on a standard
  rig](../NEXT_STEPS.md#a-hand-cannot-be-placed-at-a-point-on-a-standard-rig), [Hand-to-hand contact
  on a Rigify rig](../NEXT_STEPS.md#hand-to-hand-contact-on-rigify).
- [FR 042](../done/042-posing-bones-switches-and-reset/README.md): the writer, its snapshot and
  `write_instead`.
- `interacting_with_blender/man_and_woman_holding_hands/`.
- mpfb2: `services/rigservice.py` (`add_ik_constraint_to_pose_bone`).
