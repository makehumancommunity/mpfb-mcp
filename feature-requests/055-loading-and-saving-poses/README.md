# Loading and saving poses

**Status:** Proposed

This scopes [Loading poses](../NEXT_STEPS.md#loading-poses) and what [Posing
support](../NEXT_STEPS.md#posing-support) added to it. There are 59 BVH poses in this install, every
session starts in the A-pose, and `mpfb_list_assets` already lists them with their license. The
line-up session took six characters out of the A-pose by rotating bones by hand, with a
`gpedroso_boxing` it could have started from sitting in the catalogue. Now that `mpfb_reset_pose`
gives a way back and `mpfb_set_pose_bones` can refine, loading is the step between them.

**There are two kinds of pose, and they share almost nothing.**

| | BVH | Saved (JSON) |
|---|---|---|
| Where | `poses/<name>/<name>.bvh` | `poses/<rig>_fk`, `_ik` or `_partial`, by name |
| Catalogue | `mpfb_list_assets`, today | None |
| Installed here | 59, all CC0 | 5, all `t-pose`, one per rig family |
| MPFB's loader | `AnimationService.import_bvh_file_as_pose()` | An operator, around `RigService.set_pose_from_dict()` |
| Rigs | Default rigs only | The rig it was saved for |

**Measured while scoping**, headless, on `default_no_toes`:

| Finding | Number |
|---|---|
| Bone rolls MPFB's BVH loader rewrites | **124 of 137** |
| A JSON `t-pose` loaded after a BVH pose, against the same `t-pose` on a clean rig | **606 mm** off at the wrist, 57 mm at the foot |
| Left behind by each BVH load | One armature datablock and one action, orphaned |
| What a BVH rewrites | Every bone on the rig: all 137 are among the 163-197 bones of each of the three files tested |
| A lying pose (`drednicolson_prostrate`), since the file's root movement is dropped | Lowest vertex **44 cm above the floor** |
| A standing pose (`callharvey3d_standingnatural`), likewise | **2.6 cm through the floor** |
| The fix, moving the `root` bone | 0.0 mm in all three tested; a measurement takes 5 ms |
| BVH on a rig with helpers on, against one without | **367 mm** off at the wrist; the helpers' constraints win |
| BVH on generated `human_toes` | 35 of 197 bones share a name (root, head, jaw, eyes, breasts, toes): a broken pose, no error |

**The rolls are why a load must have a choice.** MPFB's docstring calls this destructive, and it is:
rewriting them is how it makes a local rotation mean the right thing. Applying each bone's change
from rest in armature space instead leaves every roll alone, at 0.4 s per load. Against MPFB's
result that differs by **0.9-7.8 mm** on `callharvey3d_standingnatural` and **1.4-14.5 mm** on
`drednicolson_prostrate`. On `gpedroso_boxing` it differs by up to **52 mm**, and that file has 197
bones, with `__` prefixed bones in the hierarchy that MPFB's copy ignores. Which is right on that
file is not known, and the live check has to look.

## Goals

**Primary:** an agent can load any installed pose that fits its rig, save a pose it worked hard on,
and load that onto another character, without touching the rest of what the character can do.

**Secondary:**

- **Loading never breaks a later load**, by default.
- **A pose stands on the floor**, or says how far it is from it.
- **A pose that does not fit is refused**, by name, rather than producing a broken character with no
  error.

## Non-goals

- **Retargeting a default-rig pose onto Rigify.** It stays in [Posing
  support](../NEXT_STEPS.md#posing-support), and it is what would open the 59 poses to Rigify. It
  was offered and left out. A pose saved *on* a Rigify rig does load back on one (FR 18), so Rigify
  gets a library of its own.
- **Animation.** A pose is one frame. The live check reports any installed file holding more, and
  which frame a load reads.
- **Pose thumbnails**, and **a license on a saved pose**. A BVH already has both through
  `mpfb_list_assets`, and a saved pose is the user's own.
- **Editing poses in a file.**

## Functional requirements

### `mpfb_load_bvh_pose`

1. **It takes `name`, and either `path` or `fragment` from `mpfb_list_assets`**, exactly one, as
   [`mpfb_add_asset`
   does](../../specifications/tool-interface.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports).
   A file outside the library is refused, and `path_resolved_by` reports which form was used.
2. **Default rigs only.** Anything else is `blocked_by: "rig_not_supported"`, saying how many of the
   file's bones the rig shares and that it would give a broken pose. This is the one MPFB's panel
   makes, and NEXT_STEPS' "a tool must refuse a rig the pose was not made for". A meta-rig is
   refused too.
3. **A rig with helpers on is refused** (`helpers_active`), naming [FR
   053](../053-rig-helpers/README.md)'s tool as the way to take them off.
4. **The BVH importer being off is refused** (`bvh_importer_unavailable`), via
   `SystemService.check_for_bvh()`.
5. **By default, no roll changes.** Each bone's change from rest is applied in armature space, and
   every roll stays as it was.
6. **`mpfb_exact: true` uses MPFB's own loader**, for the same result as MPFB's panel. The answer
   then reports `rolls_changed` with a count, and says that later rotations and saved poses will be
   read against new rolls. The default's description says what it gives up, and the tool's docstring
   names the departure from the panel.
7. **Neither path leaves anything behind.** The imported armature, its data and its action are
   removed, in a `finally`, and object and datablock counts are as they were. For `mpfb_exact`, that
   goes further than MPFB, and the result is unchanged.
8. **The answer names what the file did not cover:** `bones_written`, `bones_not_in_file` and
   `file_bones_not_on_rig`. A default rig with no toes and a file with them is normal, and that
   should read as normal.
9. **It carries `license`, `author` and `source_url`** from `shared/pack_attribution.py`, as an
   equipped asset's report does.

### `mpfb_list_saved_poses`

10. **Read-only. It lists the JSON poses** under `LocationService.get_user_data("poses")`, including
    the copies `RigService.ensure_global_poses_are_available()` puts there. Per pose: `pose_name`,
    `rig_identified_as`, `pose_kind` (`full`, `partial`), its mode (`fk`, `ik`), `bones` counted,
    size and modification time.
11. **`name` is optional.** With one, each row says `applies_to_this_rig`, by MPFB's own rule: the
    rig type with `default*` collapsed to `default`, and `_ik` if the rig has any `_ik` bone.
    Without one, nothing is resolved.
12. **Unreadable files are listed as such**, as `mpfb_list_expressions` does.

### `mpfb_load_saved_pose`

13. **It takes `name` and `pose_name`**, plus `pose_kind` when a name exists as both. A name is a
    name and never a path, under the same rule as a preset.
14. **A pose that does not match the rig is refused** (`pose_not_for_this_rig`), naming the
    directory it would need. This is what stops MPFB's unchecked `default` branch, whose `spine05`
    lookup raises on any other rig.
15. **A full pose starts from rest; a partial one changes only the bones it names**, as MPFB's two
    operators do.
16. **Rolls that have changed are refused** (`rolls_changed`) rather than producing a pose 606 mm
    out. The check compares each bone's roll with the rig definition, which holds a `roll` per bone,
    and can be read from `bone.matrix_local` with no mode change. The effort finds what puts them
    back, and the refusal names it. If nothing does, it says that too.

### `mpfb_save_pose`

17. **It takes `name` and `pose_name`, and `overwrite: false` by default.** With `body_parts`, using
    `mpfb_get_pose_controls`' vocabulary, it saves a partial pose. It follows [every rule for
    writing outside the
    `.blend`](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more),
    and the absolute `path` is in every answer. The file goes where MPFB's save operator would put
    it.
18. **A saved pose comes back exactly, including what MPFB's format drops.**
    `RigService.get_pose_as_dict()` does not record scale, which is what a Rigify fist is, or
    Rigify's switches. Those go under extra keys that MPFB's reader ignores, so its panel still
    loads the file, without them. `mpfb_load_saved_pose` reads them. The live check measures the
    round trip on both rig families, and `not_read_by_mpfb_panel` names what its panel would miss.
19. **`artifact_names` gets a fourth noun, `pose`**, on both sides of the socket, under the one
    table of names.

### What all the loaders share

20. **`restore_with` puts the previous pose back**, as `mpfb_reset_pose`'s does: exact, never
    capped, and naming `not_restorable`.
21. **The answer reports `floor_offset`:** the lowest point of the character's meshes relative to
    the rig's origin, in the frame's `up`, plus `floor_offset_object`, since shoes sit below feet.
22. **`ground: true` moves the `root` bone by that much**, and reports the `floor_offset` before and
    after. It defaults to false, since a falling or leaping pose may mean to be off the ground. It
    is a bone and not the object, so `mpfb_reset_pose` undoes it and `mpfb_place_character` is
    unaffected. A rig with no single root is refused this option.
23. **`limbs`, `landmarks` and `rig_identified_as`** are reported as `mpfb_get_pose` reports them,
    from the same shared module.
24. **Selection, active object and mode are put back**, using `selection.restored_all()`.

## Non-functional requirements

- **Honesty about the choice.** The default departs from MPFB's panel, on purpose, and it says so in
  the description, the docstring and
  [mpfb-integration.md](../../specifications/mpfb-integration.md).
- **A file nobody can address is not written.** The loader, the catalogue and the writer agree on
  one rule for where a pose lives, in one module.
- **Readable by MPFB.** A file saved here loads in MPFB's own panel, and a test confirms it.

## Architecture

- **`shared/pose_library.py`** holds the directory rule (rig type, `default` collapse, mode,
  `_partial`), which MPFB repeats in three UI modules. The catalogue, loader and writer share it.
  `shared/pose_writing.py` writes, so locks and the snapshot apply.
- **The BVH importer is an operator**, so it needs a view-layer collection and it selects.
  Everything it makes is deleted. If the character is excluded, [FR
  054](../054-refits-keep-the-pose/README.md)'s `view_layer.included()` applies.
- **The default's write** is, for each bone parent first: `delta = source_pose @ source_rest⁻¹` and
  `dest_pose = delta @ dest_rest`, on rotation only, keeping the bone's head. Scoping updated the
  depsgraph per bone at 0.4 s. Check whether that can be one pass, computing children from a stored
  parent.
- **Translations:** MPFB copies none from a BVH, and scoping confirmed the `root` file channel goes
  unused. FR 22 is the way to the floor rather than interpreting that channel, whose units and rest
  offset differ per file.
- **`set_pose_from_dict()` needs pose mode, selection and an active object.** Use it for the JSON
  loaders, as the operators do, because it carries the proportion scaling of `root`'s translation.
  Rewriting that would be a second opinion.
- **Pitfall:** poses share one user directory with BVH directories. A scan of `*_fk` and similar
  must not read a BVH pose whose name happens to end that way (`cmu_mb_fk` is a JSON directory; a
  BVH named `x_fk` would look the same). Look at the contents.
- **Pitfall:** rolls: `bpy.types.Bone.AxisRollFromMatrix()` gives one from `matrix_local`. The
  bridge test should compare it with a fresh rig's first, since the JSON's `roll` is the
  definition's rather than necessarily what fitting produced.
- **File upstream** in `mpfb2/features/MCP_DISCOVERED_BUGS.md`: the orphaned armature and action per
  load, and the missing check that a pose suits its rig.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog): four more tools.
- [mutating-tools.md](../../specifications/mutating-tools.md): `mpfb_save_pose` as the fourth writer
  outside the `.blend`; `artifact_names`' fourth noun.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): a deliberate departure, with the
  numbers it rests on; an additive file format an MPFB reader ignores.
- [tool-interface.md](../../specifications/tool-interface.md): the glossary (`pose_name`,
  `mpfb_exact`, `pose_kind`, `floor_offset`).
- [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one):
  `pose_library.py`.

## Tests

- **Unit, one module per tool:** exactly one of `path` and `fragment`; `pose_name` over the preset
  tests' table; real bools; `body_parts`' shape. No rig, bone or pose vocabulary.
  `test_save_preset.py`'s drift check covers the fourth noun.
- **`bbb_shared/pose_library_test.py`:** the directory rule against MPFB's panel; the near-miss
  directory; a BVH beside the JSON.
- **`ddd_mutating/`:** each refusal; rolls untouched by default and changed by `mpfb_exact`, nothing
  left behind by either; a JSON pose after each; `restore_with`; `ground`; partial leaving other
  bones alone; `overwrite`, with a file MPFB's own loader then reads.
- **`eee_composite/`:** the save-reset-load round trip on default and generated Rigify, a fist's
  scale and an `IK_FK` included; and `mpfb_set_pose_bones` refining a loaded pose.
- **Live check, a script in this subdir:** all 59 BVH poses, both methods, recording the largest
  differences by file, the floor offsets, and a contact sheet of renders to settle `gpedroso_boxing`
  and any others with `__` bones. Numbers and a decision go in the Outcome. **If the default proves
  wrong on those files, the default changes before this lands.**
- **Four smoke items**, one call each. `mpfb_save_pose` is a fourth file the run writes outside the
  `.blend`, and the verification README and CLAUDE.md say "three".

## Decisions taken while scoping

Asked on 2026-11-03:

- **Two load tools, plus a catalogue.** One tool taking either form, and BVH alone for now, were the
  alternatives.
- **Non-destructive by default, MPFB's loader by `mpfb_exact`.** Reproducing MPFB alone and
  departing from it alone were offered. This is the one place this package departs from a working
  MPFB call on the default path, and 606 mm is why.
- **Saving, partial poses and the floor are in.** **Retargeting to Rigify is out.** It would open
  all 59 poses to the rig most recent sessions use, and it is a separate, harder mapping.

*Not asked*, each argued where it is stated: `ground` defaulting to false (FR 22); moving a bone
rather than the object (FR 22); refusing a rig with changed rolls (FR 16); extra keys in MPFB's file
format (FR 18).

## References

- [NEXT_STEPS: Loading poses](../NEXT_STEPS.md#loading-poses), [Posing
  support](../NEXT_STEPS.md#posing-support), [License in the
  catalogues](../NEXT_STEPS.md#license-in-the-catalogues).
- mpfb2: `services/animationservice.py` (`import_bvh_file_as_pose`), `services/rigservice.py`
  (`set_pose_from_dict`, `get_pose_as_dict`, `ensure_global_poses_are_available`),
  `ui/rigging/applypose/`, `ui/create_assets/makepose/operators/savepose.py`,
  `ui/apply_assets/assetlibrary/operators/loadlibrarypose.py`.
