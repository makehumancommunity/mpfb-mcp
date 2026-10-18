# Narrower pose controls: hidden controls left out, a roles filter, and a compact form

**Status:** Accepted

[FR 041](../done/041-pose-controls-and-read-back/README.md) measured `mpfb_get_pose_controls` at
63 KB by default on a generated `human_toes` rig, 92 KB with the face, and 46 KB on a generated
`game_engine` rig. The request allowed this because the answer is read once per character. But
`body_parts` is the only way to narrow it, and most of what a caller pays for is controls it will
never touch. On `human_toes`, 109 of the 180 controls outside the face are `hidden_by_default`:
the tweaks and the finger and toe segments. Rigify hides those collections because a person posing
the rig is meant to start without them. The description already says "start with the others", but
the answer still sends them.

Three cuts go across body parts, and each answers a different caller:

- **Leave hidden controls out by default.** This is what Rigify's own UI does, and it is the
  biggest cut that drops nothing a first pass needs. On `game_engine` it currently cuts nothing,
  because Rigify hid nothing there. This request derives the flag by role on that rig, so that both
  generated families hide the same kinds of control.
- **Filter by role.** `ik_control` and `pole` are the handful of bones that place hands and feet,
  and they are enough for a first blocking pass of a pose.
- **A compact form.** It drops rest positions, locks, rotation modes and settings, for a caller
  that only needs to know which bones exist and what they are for. It is also the only cut that
  helps an unclassified rig, whose answer lists every bone.

All three keep the [bounded-answer rules](../../specifications/responses.md#how-tools-bound-a-large-answer):
whatever a filter leaves out is still visible as a number, and the filter as applied is echoed
back. Listed in [NEXT_STEPS](../NEXT_STEPS.md#narrower-pose-controls).

## Goals

- **Primary:** the default `mpfb_get_pose_controls` answer lists only the controls a person posing
  the rig starts with, on both generated Rigify families. It still says, by number, what it left
  out.
- **Primary:** an agent can ask for the controls of a particular kind (`roles`) and for just the
  names and labels (`compact`). A first blocking pass of a pose should then cost a few kilobytes
  rather than sixty.
- **Secondary:** `hidden_by_default` means the same thing on `human_toes` and `game_engine`, and
  the rule that makes it so is asserted against the rig where Rigify sets it.
- **Not a goal:** narrowing `mpfb_get_pose`. It lists only what is posed, and it is already near its
  8 KB line, which `body_parts` holds. Nor is it a goal to change what any writer accepts: every
  filter here changes what is *listed*, never what a tool will *act on*.

## Functional requirements

### Leaving hidden controls out

1. **`include_hidden`**, a real bool, defaults to **false**. When it is false, a control with
   `hidden_by_default: true` is not listed under `controls`. The name follows the glossary's
   `include_<part>` row.
2. **"Hidden" is the static flag, never live visibility.** It is the existing `hidden_by_default`,
   decided by the rig: on `human_toes`, membership of a `(Tweak)`, `(Detail)`, `(Primary)` or
   `(Secondary)` collection. It is never whether a collection or a bone is visible in the viewport
   right now. One rig gives one answer, whatever the user has toggled.
3. **On a generated `game_engine` rig, `hidden_by_default` is derived by role**: it is true for
   `tweak`, `finger_segment` and `toe_segment`, and false otherwise. This is the set Rigify hides
   on `human_toes` outside the face. The rule rests on that equivalence, so the equivalence is
   **asserted on `human_toes`** (see [Tests](#tests)). If it does not hold there, the effort
   records where it fails and settles the rule before writing it. **The default rig is
   unchanged**: MPFB shows every bone there, and nothing on it is hidden.
4. **The face follows the same rule when it is named.** `body_parts: ["face"]` lists the face
   controls that are not hidden, unless `include_hidden` is true.

### Filtering by role

5. **`roles`** is an optional, non-empty list of distinct role names from the existing fifteen
   (`root`, `body`, `fk`, `ik_control`, `pole`, `ik_chain`, `foot_roll`, `switches`,
   `finger_master`, `finger_segment`, `toe_master`, `toe_segment`, `tweak`, `look_target`,
   `face_control`). When it is omitted, every role is listed. **Only the shape is checked on this
   side** of the socket. A name that is not a role is refused inside Blender with
   `blocked_by: "unknown_roles"` and `known_roles`, in the same way as `unknown_body_parts`. That
   refusal comes after `unknown_body_parts` in the refusal order.
6. **The filters combine strictly.** A control is listed only when its body part was requested,
   its role was requested, and it is not hidden or `include_hidden` is true. Naming a role does not
   override the hidden default. `roles: ["finger_segment"]` without `include_hidden` lists nothing
   on `human_toes`, and the counts and the message (FR 9, 10) say how many were left out and which
   argument brings them back.
7. **`switches` follows `body_parts` only**, never `roles`, `include_hidden` or `compact`. An agent
   placing `hand_ik.L` has to know that `IK_FK` puts the arm in IK, and it would not think to ask
   for the `switches` role to find out. The `switches`-role *bone* is a control like any other, and
   the filters apply to it.

### The compact form

8. **`compact`**, a real bool, defaults to false. When it is true, each listed control carries only
   `bone`, `role`, `chain`, `source` and `hidden_by_default`. On the default rig it also keeps
   `driven_by`, because that field is what says that rotating the bone does nothing that lasts.
   Rest `head` and `direction`, `rotation_mode`, `locked` and `settings` are dropped. **A dropped
   key is absent, not `null`**, and the description says which keys a compact entry has.
   `mpfb_set_pose_bones` checks locks after it writes, so a caller that never read `locked` is
   refused rather than misled. On an **unclassified** rig, compact applies to `bones`: each one
   keeps `bone`, `parent` and `deform`.

### What every answer says

9. **Counts for whatever is left out.** On a classified rig:
   - `counts_by_body_part` keeps its meaning exactly: every control in every one of the ten parts,
     whatever was asked;
   - **`counts_by_role`** is new. It counts the controls in the *requested body parts* per role,
     before the role and hidden filters, and every role in the vocabulary is present, as 0 if need
     be. This makes `roles` discoverable in the way `counts_by_body_part` makes `body_parts`
     discoverable;
   - **`hidden_by_body_part`** is new. For each requested body part, it gives the number of
     controls that pass the role filter and are `hidden_by_default`. It is present whatever
     `include_hidden` is, so a caller can see how big the cut is as well as that it happened.

   These three are always present on a classified rig, and `null` on an unclassified one.
10. **The filters echoed back:** `requested_body_parts` (as today), `requested_roles` (the list as
    applied, or `null` when omitted), `include_hidden` and `compact`. On an unclassified rig,
    `requested_roles` and `include_hidden` are `null`, meaning not applied, as `requested_body_parts`
    already is, and the message says why. `compact` is echoed there too, because it does apply.
11. **The message says what was left out**, after the sentence it has today for the face. For
    example: "109 hidden control(s) are left out; pass include_hidden to list them."

### Unchanged

12. `mpfb_get_pose`, `mpfb_set_pose_bones`, `mpfb_set_pose_switches` and `mpfb_reset_pose` take no
    new argument and answer exactly as before. A hidden control is still a control: a writer
    accepts it, `mpfb_get_pose` reports it when it is posed, and `restore_with` may name it. The
    effort checks that no refusal's `write_instead` points at a bone the default listing leaves
    out without saying so, and records the result.

## Non-functional requirements

- **Answer size.** These are measured on the rigs FR 041 measured and recorded beside FR 041's
  figures. The default call on `human_toes` is expected at about 25 KB (71 of 180 non-face
  controls, plus switches). The target for a blocking pass, `roles: ["ik_control", "pole"]` with
  `compact: true` over the default body parts, is **8 KB**: the line `mpfb_get_character_summary`
  holds. If the switches alone put it over, record that rather than trimming what the switch tool
  needs.
- **Usability: the default is what a person starts with.** Every bone the karate session moved by
  hand (FR 041's `KARATE_BONES`) must appear in the default answer. A default that leaves out a
  bone somebody actually needed is the wrong default.
- **No silent cut.** No combination of arguments may produce an answer that reads as complete when
  it is not: the counts in FR 9 have to make every empty or short `controls` explainable.
- **Description budget.** The description gains three arguments and loses the "~60 KB" warning.
  If `tests/test_description_budget.py`'s ceiling has to rise, the commit says by how much and why.

## Architecture

- **Tool side** ([tools/get_pose_controls.py](../../src/mpfbmcp/tools/get_pose_controls.py)):
  three new parameters. `include_hidden` and `compact` go through the existing real-`bool`
  validator. `roles` needs the shape check `body_parts` has. Generalise
  `arguments.validated_body_parts` into a list-of-distinct-names validator that takes the argument
  name for its refusal, and keep `validated_body_parts` as the call the posing tools already make,
  so that the two refusals cannot drift apart. The vocabulary is **not** checked here.
- **Bridge command** ([commands/get_pose_controls.py](../../bridge/mpfb_bridge/commands/get_pose_controls.py)):
  three new `Param`s. Filtering, counting and the compact projection belong in the command, because
  no other command lists controls. `_control_entry` takes `compact`, and so does `_bone_entry` for
  the unclassified case. The `unknown_roles` check goes in the command after
  `pose_controls.resolve_posing_subject()`, **not inside it**. That resolver is shared with FR 042's
  writers, which take no `roles`, and adding an argument they would all pass as `None` widens a
  shared signature for one caller. `pose_controls` should export the role vocabulary and an
  `unknown_roles()` beside `unknown_body_parts()`, so that the list and the check live in one
  place.
- **Classification** ([shared/pose_controls.py](../../bridge/mpfb_bridge/shared/pose_controls.py)):
  `_game_engine_body_part` returns `False` for hidden today, and its module docstring says that is
  "because Rigify hid nothing". The hidden flag on that family moves to after the role is known, in
  `_classify_rigify`, and is derived from a named tuple of hidden roles. **Rewrite that docstring
  paragraph rather than adding a second one beside it.** `human_toes` keeps reading the flag off
  the collections. That is the source the derived rule is checked against, and switching
  `human_toes` to the role rule as well would leave nothing to check it against.
- **Pitfall: `counts_by_role` and the face.** It counts over the *requested* body parts, so on the
  default call it never mentions the hundred `face_control` bones. `counts_by_body_part` already
  covers those, and the description has to say that `counts_by_role` covers only what was
  requested.
- **Pitfall: an entry's shape now varies with `compact`.** Two shapes of one record would be a
  response-shape problem anywhere else. Here the caller chose it, and the echo says which. The
  description lists the compact keys so that a caller does not have to infer them.
- **Smoke run:** the existing item keeps working (`root` is never hidden). Adding `counts_by_role`
  to its asserted keys is the one change it warrants, and `tests/test_verification_smoke.py` will
  require the description to name it.

## Affected specifications

- [responses.md](../../specifications/responses.md#how-tools-bound-a-large-answer): the
  pose-controls paragraph gains a second hidden-by-default filter, `counts_by_role` and
  `hidden_by_body_part` as the counts that cover it, and the new measurements beside FR 041's. It
  should also record the rule that a caller-chosen compact form may *drop* keys rather than null
  them, with its reason, or a reason to do otherwise.
- [tool-interface.md](../../specifications/tool-interface.md): the glossary gains `roles` (the
  argument, beside `role` in an answer), `include_hidden` under the `include_<part>` row, `compact`,
  and the `unknown_roles`/`known_roles` refusal.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): the FR 041 section says
  `hidden_by_default` comes from Rigify's collection qualifiers. It has to say that on
  `game_engine` the flag is derived by role, from the set those qualifiers produce on
  `human_toes`, and that this is checked.
- The root [CLAUDE.md](../../CLAUDE.md): the `mpfb_get_pose_controls` row ("`face` only when named,
  always counted") gains the hidden default, and the test-table row gains the new arguments'
  shapes. These are map edits only.

## Tests

- **Unit, [tests/test_get_pose_controls.py](../../tests/test_get_pose_controls.py):** `roles` shape
  (absent, empty, not a list, a non-string, a repeat), all refused before sending; a role name that
  is not one *reaches the wire*; `include_hidden` and `compact` must be real bools; the defaults
  arrive as `false`/`false`/`null`. [tests/test_arguments.py](../../tests/test_arguments.py) pins
  the generalised validator's refusal sentences for both argument names.
  [tests/test_vocabulary.py](../../tests/test_vocabulary.py) needs nothing new. It is worth
  confirming that `roles` carries one JSON type across the server.
- **Bridge, `ccc_reading/get_pose_controls_test.py`**, on one character per family: no hidden
  control is listed by default and all of them are with `include_hidden`; `counts_by_body_part` is
  identical across every combination of filters; `counts_by_role` and `hidden_by_body_part` add up
  to what is listed plus what is left out; strict intersection (`finger_segment` alone lists
  nothing and counts the hidden ones); `unknown_roles` with `known_roles`; switches unchanged by
  `roles` and `compact`; compact entries carry exactly their keys (and `driven_by` on a default rig
  with helpers); on an unclassified rig, compact `bones` plus `null` echoes.
- **Bridge, `bbb_shared/pose_controls_test.py`:** on `human_toes`, outside the face, the set of
  hidden controls equals the set whose role is `tweak`, `finger_segment` or `toe_segment`. This is
  the assertion FR 3 rests on. On `game_engine`, the derived flag follows the role.
- **Live check, `live_check.py` in this subdir**, against a running Blender, reusing FR 041's
  karate character: every `KARATE_BONES` entry appears in the default answer with its role; the
  sizes in the non-functional requirements, measured on `human_toes`, `game_engine` and the default
  rig, for the default call, `include_hidden`, `compact`, and the blocking-pass call; reading still
  changes nothing.

## References

- [FR 041](../done/041-pose-controls-and-read-back/README.md): the tool, the role vocabulary,
  `hidden_by_default`, and the 63/92/46 KB measurements; its
  [live_check.py](../done/041-pose-controls-and-read-back/live_check.py) has the karate bones.
- [FR 042](../done/042-posing-bones-switches-and-reset/README.md): the writers this must leave
  unchanged, and `write_instead`.
- [NEXT_STEPS: More filters on `mpfb_get_pose_controls`](../NEXT_STEPS.md#narrower-pose-controls).
