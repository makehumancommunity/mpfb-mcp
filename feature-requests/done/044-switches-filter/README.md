# A switches filter for mpfb_get_pose_controls, and compact switch entries

**Status:** Done

[FR 043](../043-narrower-pose-controls/README.md) cut the default `mpfb_get_pose_controls`
answer on a generated `human_toes` rig from 63 KB to 31 KB. Its blocking pass is
`roles: ["ik_control", "pole"]` with `compact: true`, and it lists eight controls. It still came to
**10.9 KB against an 8 KB target, and 8.0 KB of that is the switches**. FR 043's requirement 7
makes the switches follow `body_parts` alone, and FR 043 recorded the overrun rather than cutting
what `mpfb_set_pose_switches` needs. Its verification named a switches filter as the next cut.
This is that cut.

On either generated Rigify family there are 27 or 28 switches outside the face. Twenty-four of
them sit on the four limbs: `IK_FK`, `IK_Stretch`, `IK_parent`, `pole_vector`, `pole_parent` and
`FK_limb_follow`, once per limb. The rest belong to the torso and head (`torso_parent`,
`neck_follow`, `head_follow`, and `parent_switch` on `human_toes` only). Measured on the live rigs:

| Blocking pass on `human_toes` | Switches | Whole answer |
|-------------------------------|----------|--------------|
| as FR 043 left it | 7,979 B | 10,863 B |
| every switch, compact entries (no `bone`, `description`, `default`) | 5,703 B | 8,587 B |
| `IK_FK`, `IK_parent`, `pole_vector`, full entries | 3,446 B | 6,330 B |
| those three, compact entries | 2,438 B | 5,322 B |

`game_engine` is within 350 B of each figure. Compact entries alone do not reach the line. Naming
the switches does, and the two together leave room. Both are still opt-in. FR 043's reason for
requirement 7 still holds for the default: an agent placing `hand_ik.L` has to learn that `IK_FK`
puts the arm in IK without having thought to ask.

## Goals

- **Primary:** a blocking pass that names the switches it needs fits in 8 KB on both generated
  Rigify families, and still says how many switches it left out.
- **Primary:** `compact` reaches the switches. It keeps everything `mpfb_set_pose_switches` needs
  and drops what Rigify says about a switch that `ends` and `parent_names` already say better.
- **Not a goal:** changing the default. A call that names neither `switch_names` nor `compact`
  lists every switch of the requested body parts, in full, as it does today. Nor is it a goal to
  move `ends` out of the entries into a table once per switch name. That would save about 1.25 KB
  more, but a switch entry would then need another key before it could be read, and the name
  filter already saves more than that (see [Architecture](#architecture)).
- **Not a goal:** a way to ask for no switches at all. A list of names cannot be empty
  ([`arguments.validated_names`](../../../src/mpfbmcp/arguments.py)). A caller that wants no switches
  is posing a part with none, such as a hand, and gets none already.

## Functional requirements

### The filter

1. **`switch_names`** is an optional, non-empty list of distinct switch names: Rigify's property
   names, as a `switch` entry reports them (`IK_FK`, `IK_parent`, ...). When it is omitted, every
   switch of the requested body parts is listed, as today. **Only the shape is checked** on this
   side of the socket.
2. **The argument is not called `switches`.** `switches` is already `mpfb_set_pose_switches`' list
   of objects, and it is the key of this answer. One argument name with two shapes is what FR 042
   renamed `include_switches` to avoid, and `tests/test_vocabulary.py` cannot see it, since both
   would be JSON arrays. The echo is `requested_switch_names`, sorted, as `known_switch_names`
   is, so two calls naming the same switches echo the same list.
3. **The vocabulary belongs to the rig, not to this package.** `human_toes` has `parent_switch`
   and `game_engine` does not, so there is no fixed list to check against. On a generated Rigify
   rig, a name that is not a switch anywhere on the rig is refused with
   `blocked_by: "unknown_switch_names"`, `unknown_switch_names` and `known_switch_names` (every
   switch name the rig has, sorted). That refusal comes after `unknown_roles`. A name the rig has
   but the requested body parts do not is not a mistake. It lists nothing and is counted as 0
   (requirement 5).
4. **The filter combines strictly with `body_parts`**, and is still independent of `roles`,
   `include_hidden` and the `switches`-role bone, as FR 043's requirement 7 has it. A switch is
   listed only when its body part was requested and, if `switch_names` was given, its name was
   named.

### What the answer says about what was left out

5. **`counts_by_switch`** counts the switches of the *requested body parts* per switch name,
   before the name filter, and has every switch name the rig has, as 0 if need be. That makes
   `switch_names` discoverable in the way `counts_by_role` makes `roles` discoverable. It is
   present on a generated Rigify rig whatever is asked.
6. **Where switches do not apply, neither does the filter.** On a default rig, which has none, and
   on an unclassified rig, `switch_names` is not applied and not refused. `requested_switch_names`
   and `counts_by_switch` are `null`, `switches` stays `[]` on the default rig and `null` on an
   unclassified one, and the message says why when `switch_names` was given. A caller sending one
   call across characters with different rigs is then refused only for a real mistake.
7. **The message says what was left out**, after FR 043's sentences. For example: "16 switch(es)
   of other names are left out; counts_by_switch says which."

### Compact switch entries

8. **`compact: true` now reaches `switches`.** Each entry keeps `body_part`, `switch`, `type`,
   `range`, `ends` and `parent_names`, plus `parent_names_reason` when `parent_names` is `null`,
   because that reason explains the `null`. It drops `bone`, `default` and `description`, and **a
   dropped key is absent, not `null`**, by
   [the rule FR 043 recorded](../../../specifications/responses.md#how-tools-bound-a-large-answer).
   - `bone` is reported and never asked for: the glossary addresses a switch by `body_part` and
     `switch`.
   - `default` is what `mpfb_reset_pose` with `include_switches` puts back.
   - `description` is Rigify's text. `ends` says which end is which, and `parent_names` says what
     each value selects. Neither is ever in Rigify's description.
9. **A compact entry is enough to write the switch.** Every `(body_part, switch)` in a compact
   answer is accepted by `mpfb_set_pose_switches`, and `range` with `type` says what `value` may
   be.

### Unchanged

10. A call that names neither `switch_names` nor `compact` answers as it does now, key for key,
    apart from the new `counts_by_switch` and `requested_switch_names`. `mpfb_get_pose`, whose
    `switch_values` and `switch_parents` are maps of current values, and every writer take no new
    argument and answer exactly as before.

## Non-functional requirements

- **Answer size.** Measured on `human_toes` and `game_engine`, and recorded beside FR 043's
  figures. The blocking pass,
  `roles: ["ik_control", "pole"], switch_names: ["IK_FK", "IK_parent", "pole_vector"], compact: true`,
  is expected at about 5.3 KB, and the target is **8 KB**. Compact without `switch_names` is
  expected at about 8.6 KB. That is recorded, not a target, since it is the case requirement 7's
  default protects.
- **No silent cut.** With `counts_by_switch`, every short `switches` has to be explainable from the
  answer alone: what is listed plus what is left out is every switch of the requested body parts.
- **Description budget.** One argument, one count and the compact switch keys, in about 200 B. The
  sentence that names `IK_FK`, `IK_Stretch`, `pole_vector` and `IK_parent` already lists the names
  a blocking pass wants. If `tests/test_description_budget.py`'s ceilings have to rise, the commit
  says by how much and why.

## Architecture

- **Tool side** ([tools/get_pose_controls.py](../../../src/mpfbmcp/tools/get_pose_controls.py)):
  one new parameter, checked by `arguments.validated_names(switch_names, "switch_names",
  "every switch")`. That is FR 043's generalised rule, so the three list refusals cannot drift
  apart. The vocabulary is **not** checked here.
- **Bridge command** ([commands/get_pose_controls.py](../../../bridge/mpfb_bridge/commands/get_pose_controls.py)):
  one new `Param`. The switch filter, `counts_by_switch` and the compact switch projection belong
  in the command, next to FR 043's `_listing()`, since no other command lists switch definitions.
  The `unknown_switch_names` check needs the rig's switches, so it runs **after `classify()`**,
  later than `unknown_roles`, which runs before it. It stays in the command, because the shared
  resolver takes neither argument.
- **Classification is untouched.** `pose_controls._collect_switches` already produces the records;
  this request only filters and projects them. `mpfb_get_pose` and the writers read the same
  records, which is the other reason the projection belongs in the command and not in the shared
  module.
- **Pitfall: `counts_by_switch` is not `counts_by_role`.** Its keys are the rig's switch names, so
  they differ between `human_toes` and `game_engine`. The description should say that it names the
  rig's switches, not promise a fixed list.
- **Pitfall: requirement 7 is being narrowed, not reversed.** The specification sentence "the
  switches are cut by `body_parts` alone" becomes "by `body_parts`, and by `switch_names` when the
  caller names them". The reason given for it stays, because the default still holds it.
- **Why not hoist `ends`:** measured, `ends` is 2.0 KB of the 8.0 KB and repeats per limb. Once per
  switch name it would be 0.76 KB. But a compact entry that has to be joined against a second key
  before it can be read is a different response shape, not a shorter one. Three named switches
  save 4.5 KB without it.
- **Smoke run:** nothing changes. The existing item calls with default arguments and does not
  assert `switches`.

## Affected specifications

- [responses.md](../../../specifications/responses.md#how-tools-bound-a-large-answer): the
  pose-controls paragraphs gain `switch_names` and `counts_by_switch` as the count that covers
  them. The sentence on switches being cut by `body_parts` alone is narrowed as above. The compact
  paragraph says it reaches switch entries and which keys they keep. The new measurements go
  beside FR 043's table.
- [tool-interface.md](../../../specifications/tool-interface.md): the glossary gains `switch_names`
  (the argument, beside `switch` in an entry, and why it is not `switches`), `counts_by_switch`,
  and the `unknown_switch_names`/`known_switch_names` refusal, with the note that its vocabulary
  is the rig's. The "A Rigify switch, addressed" row already says the bone is reported and never
  asked for, and that is why compact drops it.
- The root [CLAUDE.md](../../../CLAUDE.md): the `mpfb_get_pose_controls` row and its test-table row
  gain the argument. These are map edits only.

## Tests

- **Unit, [tests/test_get_pose_controls.py](../../../tests/test_get_pose_controls.py):**
  `switch_names` shape (absent, empty, not a list, a non-string, a repeat), all refused before
  sending. A name that is not a switch *reaches the wire*. The default arrives as `null`.
  [tests/test_arguments.py](../../../tests/test_arguments.py) needs nothing new, because the rule is
  FR 043's. `tests/test_vocabulary.py` should confirm that `switch_names` is a new name, not a
  second type for an old one.
- **Bridge, `ccc_reading/get_pose_controls_test.py`**, on `human_toes` and `game_engine`:
  - the filter lists exactly the named switches of the requested parts;
  - `counts_by_switch` has every switch name of the rig and adds up to what is listed plus what is
    left out;
  - a name the rig lacks is refused as `unknown_switch_names`, with `known_switch_names`;
    `parent_switch` is known on `human_toes` and refused on `game_engine`;
  - a name in an unrequested part lists nothing and counts 0;
  - `roles` and `include_hidden` still leave switches alone;
  - compact switch entries carry exactly their keys;
  - a call with neither new argument has the same `switches` as before;
  - on a default rig with helpers and on `mixamo`, `switch_names` is not applied, and the echoes
    are `null`.
- **Bridge, `ddd_mutating/set_pose_switches_test.py`:** every `(body_part, switch)` in a compact
  answer is accepted, written back at its current value with `raw: true` so that nothing moves.
  This is requirement 9.
- **Live check, `live_check.py` in this subdir**, against a running Blender, reusing FR 043's
  check and FR 041's karate character. It covers:
  - the sizes in the non-functional requirements, on `human_toes` and `game_engine`;
  - no silent cut on every call measured;
  - a blocking pass driven by its own answer: place the hands with `mpfb_set_pose_bones`, after
    `mpfb_set_pose_switches` sets `IK_parent` and `pole_vector` from what the compact entries say;
  - reading still changes nothing.

## Verification

Both halves of "verified" hold. The bridge suite gained twelve tests, 525 in all. In
`ccc_reading/get_pose_controls_test.py`, on both generated families: the switches of a call with
neither new argument are the shared module's records, whole; `switch_names` lists exactly the
named switches of the requested parts, `counts_by_switch` names every switch the rig has and adds
up to what is listed plus what is left out, and the count does not move with the filter; a name in
a part not requested lists nothing and counts 0; a compact switch carries exactly its keys. Once:
`parent_switch` is listed on `human_toes` and refused on `game_engine` with `known_switch_names`;
`unknown_roles` is refused first; a default rig and `mixamo` neither apply nor refuse the filter.
FR 043's "switches follow body parts alone" test became "roles and include_hidden leave the
switches alone", since `compact` now reaches them. In `ddd_mutating/set_pose_switches_test.py`,
requirement 9: every `(body_part, switch)` of a compact every-part listing, on both families, is
written back at its current value with `raw: true`, accepted with no resolution error and no change
to the pose. The unit suite gained three (550), and `tests/test_vocabulary.py` now tells an array of
names from an array of objects, so a `switches` list of names would be caught as the collision it
is. The smoke run is 41 of 41.

The live check, [live_check.py](live_check.py), ran on 2026-10-18 against a windowed Blender 5.1
with MPFB, the bridge (reloaded to pick the change up) and the community blender-mcp add-on, and
passed all 28 checks. On every call measured on both families, the controls and the switches
listed plus what the counts say was left out are everything in the requested parts. Reading
changed nothing. Driven by its own compact answer, the blocking pass set `IK_parent` to the index
of `Torso` in `parent_names` and `pole_vector` to the end whose `ends` says the pole aims the
elbow, placed the hands with `mpfb_set_pose_bones` and lowered the hips 0.4 m: the hands went down
0.400 m with them and neither arm stretched (`reach_ratio` 0.794), where FR 041's karate session
had fists left in the air and both arms stretched to 1.119.

Measured, as JSON envelopes:

| Rig | default | `compact` | FR 043's blocking pass | FR 044's blocking pass |
|-----|---------|-----------|------------------------|------------------------|
| `human_toes` | 31.2 KB, switches 8.0 KB | 15.6 KB, switches 5.7 KB | 8.8 KB, switches 5.7 KB | **5.7 KB**, switches 2.4 KB (12) |
| `game_engine` | 25.2 KB, switches 7.7 KB | 13.2 KB, switches 5.5 KB | 8.6 KB, switches 5.5 KB | **5.6 KB**, switches 2.4 KB (12) |

The blocking pass is about 350 B over the 5.3 KB estimated, which is `counts_by_switch` (every
switch name of the rig, on every Rigify answer) and the echo, and 2.5 KB under the line. FR 043's
pass with compact switches came in at the 8.6 KB estimated for `game_engine` and 8.8 KB for
`human_toes`, recorded rather than a target. The description grew 198 B (2,438 to 2,636 B) and fit
under the existing ceiling; the schema ceiling rose 100 B, to 15,000, for the `switch_names` list.

## References

- [FR 043](../043-narrower-pose-controls/README.md): requirement 7, the compact rule, the
  blocking pass, and the measurement that found the switches were 8.0 KB of it. Its
  [live_check.py](../043-narrower-pose-controls/live_check.py) is the one to extend.
- [FR 042](../042-posing-bones-switches-and-reset/README.md): `mpfb_set_pose_switches`, how a
  switch is addressed, and why `include_switches` is not called `switches`.
- [FR 041](../041-pose-controls-and-read-back/README.md): the switch records, `ends` and
  `parent_names`, and the karate session that needed `IK_parent` and `pole_vector`.
- Bridge: `shared/pose_controls.py` (`_collect_switches`, `_switch_record`, `SWITCH_ENDS`).
- [HISTORY: FR 044](../../HISTORY.md#switches-filter), which replaced NEXT_STEPS' "A switches filter
  on `mpfb_get_pose_controls`".
