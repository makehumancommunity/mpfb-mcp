# Placing a character: where it stands and which way it faces

**Status:** Proposed

No tool puts a character anywhere but the origin. The line-up session
([FULL_SESSION.md](../FULL_SESSION.md#placement)) built six characters on top of each other and
spread them out by hand through blender mcp, setting each rig's location and a ±4–8° turn. Any
scene with more than one character starts with that step. To space them, the session also computed
each character's extent from its evaluated vertices, because no tool says how much room a character
takes up.

**The NEXT_STEPS entry is partly wrong, and this request corrects it.** It says `mpfb_add_rig`
"moves the basemesh back to the origin anyway". Both of MPFB's adding functions set the armature's
location to the basemesh's and then zero the basemesh's own location
(`humanservice.py:1683`, `:1738`). The basemesh is parented to the armature, so the character
stays where it was in the world. The bridge's `add_rig` already reports this as
`basemesh_moved_to_origin`, and its message says the armature took the old location. **What the
functions do not carry over is rotation.** `Rig.create_armature_and_fit_to_basemesh()` adds the
armature at the basemesh's location with no rotation and fits the bones to the basemesh's *local*
vertex coordinates. The basemesh keeps its own rotation under an unrotated parent. From reading the
source, a turned character that has no rig yet would therefore get a rig that does not match the
mesh. This has not been observed. It is the first thing the effort checks, because a placing tool
is what would create such characters.

**A garment's sub-rig breaks when its character is moved**
([its own entry](../NEXT_STEPS.md#sub-rig-child-of-breaks-away-from-the-origin)). Repairing that is
a separate effort. This request only makes sure the break is reported rather than silent. The
character frame ([FR 041](../done/041-pose-controls-and-read-back/README.md)) already makes every
posing tool independent of where the character stands, so moving a posed character changes no
posing answer.

## Goals

- **Primary:** one call places a character: where it stands in the world, and which way it faces,
  absolutely or toward something. Everything that belongs to the character moves with it,
  including a hidden meta-rig.
- **Primary:** an agent can find out where a character is and how much room it takes up, so that
  several characters can be spaced without measuring through blender mcp.
- **Secondary:** every tool that adds to a character (`mpfb_add_rig`, `mpfb_generate_rigify_rig`,
  `mpfb_add_asset`, `mpfb_refit_human`) leaves a placed character where it was and facing the way
  it was. Each one is checked on a placed character, not assumed.
- **Secondary:** a move that leaves a sub-rig broken says so, naming the garment.
- **Not a goal:** repairing sub-rigs, which is
  [its own entry](../NEXT_STEPS.md#sub-rig-child-of-breaks-away-from-the-origin). Nor relative moves
  (`move_by`/`turn_by`), a full 3D rotation, scaling, placement arguments on the creating tools,
  arranging several characters in one call, finding a floor surface or framing a camera (see
  [Decisions taken while scoping](#decisions-taken-while-scoping)).

## Functional requirements

### The tool

1. **A new tool, `mpfb_place_character`**, mutating. It resolves its subject through the shared
   resolver from any object in the character's family, as every subject-taking tool does.
2. **It takes `position`, an object `{"x", "y", "z"}`**, in world metres, and moves the
   character's root object there. Any key left out keeps its current value. So `{"x": 2.0}` slides
   the character sideways without lifting it off the floor.
3. **It takes `facing`, degrees about the world's up axis.** `0` faces world `-Y`, the way MPFB
   builds every character (the [character frame's](../../specifications/responses.md#a-position-on-a-character-is-in-the-character-frame)
   `forward` on an unturned rig). Positive values turn counter-clockwise seen from above, which is
   Blender's own sign for a rotation about Z. The answer normalises it to `(-180, 180]`.
4. **It takes `face_toward` as the alternative to `facing`**: either a world point `{"x", "y"}` or
   an object name, `{"object": "Camera"}`. An object's world location is used. The character turns
   about its own vertical axis until `forward` points at the target's horizontal projection. The
   answer reports the resulting `facing` like any other turn. The turn is computed from the
   character's position **after** this call's `position` is applied, so a single call can move a
   character and turn it toward the camera.
5. **The argument shapes are checked before anything is sent**: `facing` and `face_toward`
   together are refused, a call with none of `position`, `facing` and `face_toward` is refused, and
   so is an unknown key in `position` or `face_toward`. An unknown object name in `face_toward` is
   an answer from the far side (`blocked_by: "face_toward_not_found"`). So is a target that is
   directly above or below the character, which gives no direction
   (`blocked_by: "face_toward_has_no_direction"`).
6. **The root is the rig object if there is one, and the basemesh otherwise.** On a generated
   Rigify rig the root is the generated rig. A **meta-rig kept or hidden** beside it
   (`meta_rig_action` `keep`/`hide`) moves with it as well, by the same transform. If it did not, a
   later refit or regeneration would build from a meta-rig left behind at the old position.
7. **A root parented to something outside the character**, such as an empty the user grouped
   characters under, is placed in world terms: `position` and `facing` are world values both in
   and out. The parent is reported as `external_parent_name` and is never changed.
8. **A tilted root is refused for turning, never silently straightened.** If the root's rotation
   is anything but a turn about world up, a `facing` or `face_toward` is refused with
   `blocked_by: "character_tilted"`, and nothing is written. A `position` alone is still applied.
   The tool writes only yaw, so it cannot express the rotation it would be replacing, and its
   `restore_with` could not put it back.

### What the answer says

9. **Before and after**, per the [mutating-tools rule](../../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after):
   `position_before`/`position_after`, `facing_before`/`facing_after`, the `root_name` that was
   moved, and the objects that moved with it as `moved_with` (a kept meta-rig; an empty list
   otherwise).
10. **The character frame after the move**, as `Frame.describe()` reports it, so that a caller
    can convert a frame position from `mpfb_get_pose` to a world one without a second call.
11. **`footprint`**: the character's evaluated world-space bounding box after the move, with
    `min` and `max` as `{"x", "y", "z"}` and `width`/`depth`/`height` in metres. It covers the body
    and every equipped mesh asset in their current pose, and leaves out helpers, the rig and hidden
    objects. Width and depth are along world X and Y, not the character's own axes, because the
    footprint is for spacing characters in a scene. This is the number the line-up session computed
    by hand to space six characters edge to edge.
12. **`restore_with`**: the `mpfb_place_character` call that puts the character back, keyed by the
    tool as [the glossary](../../specifications/tool-interface.md#arguments-and-answer-keys) says.
    It always uses `position` and `facing`, never `face_toward`.
13. **`subrigs_broken_by_move`**: one record per sub-rig on the character, with
    `subrig_object_name` and the garment's `asset_object_name`, whenever the character's root ends
    up anywhere but the origin facing `0`. It is an empty list when there are none, never absent.
    The answer's message says what will happen in a render: the garment's sub-rig-weighted vertices
    are dragged toward the world origin. The tool does not repair this, and the description says
    so in one sentence. A sub-rig is an armature whose `object_type` is `Subrig` (`rig.py:247`).
14. **`mpfb_add_asset` reports the same `subrigs_broken_by_move` when it adds a sub-rig to a
    character that is not at the origin facing `0`.** That is the other order in which the defect
    is reached, and today it is silent too.

### Reading where a character is

15. **`mpfb_get_character_summary` gains a `placement` section**: `position`, `facing`, `tilted`,
    `root_name`, `footprint` and `subrigs_broken_by_move`, under the same names as the place tool's
    answer and read by the same shared module. That keeps the summary's rule of never giving a
    second opinion. A caller laying out a scene reads each character once, and the summary stays
    under its 8 KB line.

### What other tools owe a placed character

16. **`mpfb_add_rig` on a turned, unrigged character** leaves it facing the way it did, with a rig
    that fits the mesh. If the live check confirms the suspicion in the background, the bridge's
    `add_rig` carries the rotation over itself, as MPFB carries the location: it zeroes the
    basemesh's rotation before adding, then gives the rig that rotation. It reports this the way it
    reports `basemesh_moved_to_origin` today.
17. **`mpfb_generate_rigify_rig`, `mpfb_refit_human`, `mpfb_add_asset` and `mpfb_remove_asset`**
    each leave a placed character's root where it was, facing the way it did. Each is checked live
    on a character that has been moved and turned. Any that does not gets the same treatment as
    requirement 16, and is named in [HISTORY](../HISTORY.md) when this lands.

## Non-functional requirements

- **Honest about what it cannot fix.** A placed character must look the same as the same character
  at the origin. Where it cannot, which today means a sub-rig, the answer says so. The session's
  ponytail was a visible defect that no answer reported.
- **Cheap.** A move is one round trip with no MPFB recalculation. Placing six characters should
  take well under two seconds. That is why no batched form is proposed: a batch is justified by
  per-call cost ([mutating-tools.md](../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes)),
  and this tool has little.
- **Small description.** Three arguments besides `name`. The description says what `facing` `0`
  means and that a sub-rig is not repaired, and leaves the frame to the specification it links.

## Architecture

- **The usual four files**: `tools/place_character.py`, a `register()` line,
  `bridge/mpfb_bridge/commands/place_character.py` and an entry in `commands/table.py`. Plus the
  summary's new section and `add_asset`'s new key.
- **A new shared module, `shared/placement.py`.** It finds the character's root (rig, else
  basemesh, plus a kept meta-rig), reads `position`, `facing`, `tilted`, `footprint` and the
  sub-rigs a move breaks, and writes a placement. It has three users: the place command, the
  summary's `placement` section and `add_asset`'s report. Like `character_frame.py`, it reads
  nothing out of MPFB and takes no `services`. The future sub-rig request will extend its
  sub-rig half, or move it to a module of its own.
- **Write `matrix_world`, then update the depsgraph before reading anything back.** That is how
  requirement 7's external parent stays untouched, and how the footprint is read from the moved
  character rather than the old one.
- **The root's rotation mode varies.** MPFB normalises a rig's rotation mode
  (`RigService.normalize_rotation_mode`), but a basemesh is left in Blender's default `XYZ` Euler,
  and a user may have changed either one. Read the rotation through the matrix, and write it back
  in whatever mode the object already uses.
- **Scale is never written.** A rig object with a scale other than one already reports metres
  through the frame. Writing a placement must keep the scale exactly as it was. That means
  composing the new matrix from location, yaw and the *existing* scale, not decomposing and
  recomposing a matrix that might shear.
- **"Tilted" needs a tolerance**, as `pose_reading.py`'s limb readings have. A rig turned by hand
  in the viewport carries float noise in X and Y. A threshold of 0.1°, the frame's own rounding, is
  the starting point, and the effort records what a hand-turned rig actually measures.
- **`RigService.find_pose_bone_head_world_location()` and its `_tail_` twin add only the armature
  object's location**, ignoring its rotation (`rigservice.py:487`, `:503`). Nothing in the bridge
  calls them, and nothing should start to. The defect belongs upstream. MPFB's own OpenPose export
  uses the neighbouring `get_world_space_location_of_pose_bone`, which the effort checks for the
  same fault and reports alongside.
- **The test fixtures have no sub-rig.** `_fixtures.py`'s `ponytail.mhclo` is a plain MHCLO.
  Requirements 13–14 need an MHCLO with a `.rig.json` beside it, written as real MPFB sub-rig data
  rather than a convenient stand-in ([testing.md](../../specifications/testing.md)). That fixture is
  built here, and the sub-rig request will need it too.

## Affected specifications

- [tool-interface.md](../../specifications/tool-interface.md#the-glossary): a new glossary row,
  **"Where a character stands in the scene"**: `position` as world `{"x","y","z"}`, `facing` in
  degrees with its zero and sign, and `face_toward`. The existing row that says "not a world-space
  `[x, y, z]`" is about a position *on* a character. Both rows must say which one they cover, so
  that neither reads as contradicting the other. The new `blocked_by` values `character_tilted`,
  `face_toward_not_found` and `face_toward_has_no_direction`, and `subrigs_broken_by_move`.
- [responses.md](../../specifications/responses.md#a-position-on-a-character-is-in-the-character-frame):
  the frame's origin is now something a tool moves, and `footprint` is world-space by necessity.
- [mutating-tools.md](../../specifications/mutating-tools.md): `restore_with` gains a second user.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): the rotation the adding
  functions drop (if confirmed) and how it is carried over, the sub-rig defect as a reported
  circumstance, and the location-only world helpers.
- [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one):
  `shared/placement.py` and the rule it rests on.
- [vision.md](../../specifications/vision.md#target-tool-catalog): the new tool.

## Tests

- **Wrapper side** (`tests/test_place_character.py`): `position` and `face_toward` keys and finite
  numbers, an unknown key refused, `facing` and `face_toward` together refused, an empty call
  refused, and `facing` finite. No object-name vocabulary is checked here.
- **Bridge side** (`ddd_mutating/place_character_test.py`), against a real MPFB:
  - a character with no rig, one with the default rig, and one with a generated Rigify rig, the
    last with its meta-rig hidden and checked to move along;
  - `face_toward` a point and an object, combined with a `position` in the same call, and both
    refusals;
  - **`mpfb_get_pose` gives the same answer before and after a move** on a posed character. This
    is the frame's invariance, asserted rather than assumed;
  - `restore_with` puts the character back exactly;
  - an external parent left untouched, and a tilted root refused for turning and allowed to move;
  - the footprint against the evaluated vertices of the body and its assets;
  - `subrigs_broken_by_move` on a character carrying the sub-rig fixture, from both the place
    tool and `add_asset`, and empty again once the character is back at the origin.
- **`bbb_shared/placement_test.py`**: the root rule, yaw and tilt read through every rotation mode,
  and scale preserved exactly.
- **The summary's `placement` section equals the place tool's answer** for the same character, in
  `eee_composite/get_character_summary_test.py`, as every other section does.
- **Placed-character cases for the other tools** (requirements 16–17), each in its own existing
  test module.
- **Live check, in this subdir.** A script rebuilds a three-character line-up with mpfb-mcp tools
  alone, spaced edge to edge from their footprints and turned toward the scene camera with
  `face_toward`. One of them carries the real `ponytail01`, and the script checks that it is
  reported. Before anything else is written, the script runs `mpfb_add_rig` on a turned, unrigged
  character, which settles requirement 16's premise.
- **One smoke item** in [verification/](../../verification/) for `mpfb_place_character`.

## Decisions taken while scoping

- **A dedicated tool only.** Rejected: `position`/`facing` on `mpfb_create_human` and
  `mpfb_create_human_from_preset` as well. That would save one ~250 ms round trip per character, at
  the cost of the same vocabulary in three descriptions.
- **Yaw only, absolutely or toward a target.** `facing` and `face_toward`. Rejected: a full 3D
  rotation, which needs a vocabulary of its own and would remove requirement 8's protection. Also
  rejected: the relative forms `move_by` (in the character frame) and `turn_by`. A caller can add
  to `position_after` and `facing_after` itself.
- **Sub-rigs are reported, not repaired.** The repair, including whether a binding exists that
  survives a move made by hand, stays in
  [its own entry](../NEXT_STEPS.md#sub-rig-child-of-breaks-away-from-the-origin), which this
  request updates to point here. Rejected: repairing them in this effort, and fixing MPFB's
  `rig.py` in the same effort.
- **Placement is read from the summary**, not from a new layout tool. A no-op move cannot stand in
  for a read, since a call that changes nothing is refused.

## References

- [FULL_SESSION.md](../FULL_SESSION.md): the line-up session, its placement step and the sub-rig
  defect.
- `mpfb2/src/mpfb/services/humanservice.py:1683`, `:1738`: the adding functions moving the location
  to the rig.
- `mpfb2/src/mpfb/entities/rig.py:241`: the armature added at the basemesh's location, with no
  rotation.
- `mpfb2/src/mpfb/entities/rig.py:428`, `:599`: `set_inverse_pending = True` on every `CHILD_OF`.
- `mpfb2/src/mpfb/services/rigservice.py:1265`: the generated Rigify rig takes the meta-rig's
  parent.
- [`bridge/mpfb_bridge/shared/character_frame.py`](../../bridge/mpfb_bridge/shared/character_frame.py):
  the frame every position on a character is converted through.
