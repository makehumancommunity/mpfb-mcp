# FR 037 census: every name on the tool surface, judged

**Outcome.** Every rename below landed, one commit per group, and `census.py --check` reports
62 renames and 0 outstanding. Run again at the end, the census finds 65 argument names (the same
count, differently spelled), 448 answer keys, 52 refusal slugs (two fewer: `not_found` and
`properties_unreachable` merged into the spellings they duplicated) and 643 backticked terms, and
no argument name with two JSON types. [live_check.py](live_check.py) called every renamed argument
once against a headless Blender 5.1 with MPFB 2.0.17 and passed all 50 of its checks
([live_check_result.txt](live_check_result.txt)). Two things changed in the census itself while the
effort ran, and both are recorded where they apply below: it now also reads the two tool modules
that build an answer on this side of the socket, and one rename had to be marked as leaving its old
spelling behind, because a census of keys cannot see nesting.

The input to [FR 037](README.md), taken on 2026-09-24 at `38c0514` by running
[census.py](census.py) and by reading the code behind every divergence it showed. The census found
**65 argument names** over the 32 tools, **439 keys** in the bridge's answers (an over-count,
since internal dicts are included), **54 refusal slugs** and **646 backticked terms** in the
descriptions and the server instructions.

The README's tables were the starting point. Where the census found more, it is added here; where
it contradicts them, this document wins, and the README's tables are corrected to match when the
rename lands. `census.py`'s `RENAMES` holds every rename below as data, and `census.py --check`
lists those still outstanding. It must exit 0 when the effort ends.

Each divergence gets one of three verdicts:

- **Rename**, under one of the README's rules (R1–R7), or under a rule this census adds and
  states.
- **Kept, with a reason**. These go into the glossary as deliberate exceptions, so that the next
  census confirms them instead of reopening them.
- **Out of scope**. Real, but not a naming question. These go to NEXT_STEPS.

## What the census found beyond the README

1. **`rig_name` is the rig object in seven answers, not two.** `assets_possibly_stale` carries it
   in the five commands that report it (`apply_expressions`, `set_face_units`,
   `set_macro_details`, `set_targets`, `symmetrize_targets`), beside `refit_human` and
   `save_preset`. `add_rig` also has an `existing_rig_name` and an `existing_rig_type`.
2. **Two echoes use a shorter name than their argument.** `mpfb_list_objects` takes `object_type`
   and echoes `requested_type` / `type_recognized` / `known_types`. `mpfb_list_assets` takes
   `asset_subdir` and echoes `requested_subdir` / `subdir_recognized` / `known_subdirs`. Every
   other echo is `requested_X` / `X_recognized` / `known_Xs` with `X` the argument's own name,
   which is the rule the README cites as holding.
3. **`resolved_by` sits beside `subject_resolved_by`** in `add_asset`, `set_asset_material` and
   `set_skin`. It says whether the asset *file* was found from `path` or from `fragment`. In
   `set_targets` the same idea, how a file path was found, is `path_resolved_by`.
4. **`properties_unavailable` and `properties_unreachable` are one condition.** Both mean
   `mpfb_surface.human_object_properties(services) is None`, in `set_macro_details` and
   `save_preset` respectively.
5. **`applied` is also a number.** `clamped_face_units` entries are `{face_unit, sum, applied}`,
   where `applied` is the aggregate MPFB clamped to. `unexplained_face_units` calls exactly the same
   number, `aggregate.get(name)`, `from_stack`.
6. **`assets` means a catalogue in one tool and a character's equipment in another.**
   `mpfb_list_assets` answers `assets` from the library. `mpfb_get_character_summary` answers
   `assets` for what the character wears, the same set that `mpfb_create_human_from_preset` calls
   `equipped_assets`.
7. **Adding versus replacing has two result keys too.** `set_face_units`' `cleared` names the units
   `clear_first` zeroed. `apply_expressions`' `removed_by_replace` names the rows `mode: "replace"`
   dropped. Once the argument is `mode` in both tools, the result key follows it.
8. **`previous_file` / `current_file`** in the two save tools are a whole field before and after
   the write, which R5 spells `<field>_before` / `<field>_after`.
9. **`weight` is also a macro slider**, body weight, in `mpfb_create_human` and
   `mpfb_set_macro_details`. See [Kept](#kept-with-a-reason).
10. **Five mutating tools answer an unresolved subject with no `blocked_by`.** See
    [Out of scope](#out-of-scope).

## Renames

Grouped by rule, one commit per group, in this order. The first commit that changes the wire
raises `PROTOCOL_VERSION` and `MIN_SUPPORTED_PROTOCOL_VERSION` on both sides (requirement 6).
Every retired **argument** spelling goes into `arguments.py`'s `RETIRED_ARGUMENTS` in the same
commit, so that a caller still sending it is told the new spelling.

### R1: `name` is the object a tool operates on

| Tool | Today | Renamed |
|---|---|---|
| `mpfb_save_preset` | `name` is the preset, `subject` the character | `preset_name`, and `name` is the character. `subject` retired → `name` |
| `mpfb_save_expression` | `name` is the expression file, `subject` the character | `expression_name`, and `name` is the character. `subject` retired → `name` |
| `mpfb_create_human_from_preset` | `name` is the preset | `preset_name`. `name` retired → `preset_name` |

`name` is swapped in the two save tools, not retired, so a caller who still passes the preset
there is not refused as undeclared. Instead, the `subject_not_found` sentence in those two tools
names `preset_name` / `expression_name` (README, Architecture). The server instructions' sentence
"mpfb_save_preset is the one tool here whose `name` is NOT the subject" is deleted.

### R2: an object named in an answer is `<role>_name`, or `<role>_object_name`

| Where | Today | Renamed |
|---|---|---|
| `mpfb_create_human` | `object_name` (the basemesh) | `basemesh_name` |
| `refit_human`, `save_preset`, and `assets_possibly_stale` in five commands | `rig_name` (the rig object) | `rig_object_name` |
| `save_preset`'s `rig_not_identifiable` refusal | `rig_name` | `rig_object_name` |
| `add_rig`'s `already_rigged` refusal | `existing_rig_name` | `existing_rig_object_name` |
| `remove_asset` | `body_proxy_name` | `bodyproxy_name`, as `set_skin` spells it |
| `mpfb_generate_rigify_rig` argument | `rig_name` | `generated_rig_name`. Retired → `generated_rig_name` |
| `generate_rigify_rig` echo | `rig_name_requested` | `generated_rig_name_requested` |

### R3: a verb is never a list or a number elsewhere

| Where | Today | Renamed |
|---|---|---|
| `set_targets`, `set_face_units` | `applied`, a list of writes | `changes` |
| `set_macro_details`, `symmetrize_targets` | `changed`, a list of writes | `changes`. `apply_expressions` keeps the bool `changed` |
| `set_face_units` / `symmetrize_targets` | `applied_count` / `changed_count` | `change_count` |
| `clamped_face_units` entries (`shared/expression_divergence.py`) | `applied`, a number | `from_stack`, as `unexplained_face_units` spells the same number |

After this group, `performed` is the only flag in those four tools. Their verb was a list, and a
list does not answer "did it happen" by itself: `symmetrize_targets`' list is populated under
`dry_run`. mutating-tools.md's list of verbs changes to match.

### R4: an identification is `<thing>_identified_as`

| Where | Today | Renamed |
|---|---|---|
| `asset_info` (`shared/asset_info.py`), and so `mpfb_get_object_info` and the summary's `rig` | `rig_type` | `rig_identified_as` |
| `asset_info`, and so the summary's asset rows | `material_type` | `material_identified_as` |
| `generate_rigify_rig`'s `not_a_metarig` refusal detail | `rig_type` per skeleton | `rig_identified_as` |
| `add_rig`'s `already_rigged` refusal | `existing_rig_type` | `existing_rig_identified_as` |

The example in responses.md ("How tools report the asset behind an object") is renamed with it.

### R5: before and after

| Where | Today | Renamed |
|---|---|---|
| `set_macro_details` per-entry records | `previous` / `new` | `previous_value` / `new_value` |
| `set_asset_material` | `previous_alternative_material` | `alternative_material_before` |
| `save_preset`, `save_expression` | `previous_file` / `current_file` | `file_before` / `file_after` |

### R6: the same choice has the same argument, and the echo follows it

| Where | Today | Renamed |
|---|---|---|
| `mpfb_add_asset` argument | `asset_type` | `object_type`. Retired → `object_type` |
| `add_asset` answer and slug | `requested_asset_type`, `known_asset_types`, `unknown_asset_type` | `requested_object_type`, `known_object_types`, `unknown_object_type` |
| `mpfb_list_objects` echo | `requested_type`, `type_recognized`, `known_types` | `requested_object_type`, `object_type_recognized`, `known_object_types` |
| `mpfb_list_assets` echo | `requested_subdir`, `subdir_recognized`, `known_subdirs`, `counts_by_subdir` | `requested_asset_subdir`, `asset_subdir_recognized`, `known_asset_subdirs`, `counts_by_asset_subdir` |
| `mpfb_set_face_units` argument and echo | `clear_first: bool` | `mode: "merge" \| "replace"`, checked locally as `apply_expressions`' is. Retired → `mode` |
| `set_face_units` answer | `cleared` | `removed_by_replace`, as `apply_expressions` spells it |

The server instructions' "requires an asset_type - pass mpfb_list_assets' object_type" becomes
"requires the object_type mpfb_list_assets reports".

### R7: the glossary over MPFB's spelling

| Where | Today | Renamed |
|---|---|---|
| `mpfb_create_human_from_preset` argument | `material_instances` | `material_instances_policy`. Retired → `material_instances_policy` |
| its answer and slug | `material_instances_requested`, `_used`, `_service_default`, `known_material_instances`, `unknown_material_instances` | the same with `material_instances_policy`, `known_material_instances_policies`, `unknown_material_instances_policy` |
| `mpfb_create_human_from_preset` arguments | `override_skin_model`, `override_clothes_model`, `override_eyes_model` | `override_skin_type`, `override_clothes_material_type`, `override_eyes_material_type`. Each is retired → its new spelling, and `overrides` is keyed by the new names |

`mpfb_set_skin` keeps its bool `material_instances`. `override_clothes_material_type` keeps
MPFB's word "clothes" rather than "garment" on purpose: MPFB applies `clothes_material_type` to
every body part except the eyes (`humanservice.py:672`), so the setting covers more than garments.
Its description already says so.

### A face unit's number is `value`

| Where | Today | Renamed |
|---|---|---|
| `mpfb_set_face_units` entries (input) | `{face_unit, weight}` | `{face_unit, value}`. The per-entry unknown-key refusal names `value` for `weight` |
| `set_face_units` per-entry answer | `{face_unit, weight, previous_value, new_value}` | `{face_unit, value, previous_value, new_value}`, the shape of a `set_targets` entry |
| `get_face_units` entries, the summary's `face.face_units` rows | `weight` | `value` |

`weight` stays on expression rows. See [Kept](#kept-with-a-reason).

### How something was resolved, and what was not found

| Where | Today | Renamed |
|---|---|---|
| `mpfb_get_object_info` | `resolved_from: "active_object" \| "name"` | `subject_resolved_by: "active" \| "name"`. This closes the NEXT_STEPS entry |
| `add_asset`, `set_asset_material`, `set_skin` | `resolved_by: "path" \| "fragment"` | `path_resolved_by`, as `set_targets` spells how a file path was found. A bare `resolved_by` beside `subject_resolved_by` does not say what was resolved |
| `remove_asset`, `set_asset_material` slug | `not_found` | `subject_not_found` |
| `save_preset` slug | `properties_unreachable` | `properties_unavailable`, as `set_macro_details` spells the same test |

### The mesh assets on a character

| Where | Today | Renamed |
|---|---|---|
| `mpfb_get_character_summary` | `assets` (records) | `equipped_assets`, as the preset tool spells it. `assets` stays `mpfb_list_assets`' catalogue |
| `create_human_from_preset`'s `equipped_assets` records | `object_name` | `name`, as every other record *of* an object spells it (`list_objects`, `related_objects`, the summary's rows) |

The census found four spellings, and they turn out to be two concepts plus qualifiers:

- **`mesh_assets`** is a list of the object names of the mesh assets on a character. The qualified
  forms `mesh_assets_present` (`generate_rigify_rig`, at the moment of generation),
  `mesh_assets_not_rigged` (`add_rig`) and `mesh_asset_count` are subsets or counts of it, and the
  qualifier says which. Kept.
- **`equipped_assets`** is a list of records, one per mesh asset, carrying what the tool knows
  about each one.

**The record rule this adds:** in a record *of* an object the object is `name`. In a record *about
something on* an object (`set_skin`'s `materials_destroyed`, `remove_asset`'s
`vertex_groups_left_behind`) it is `object_name`, which is why those two stay.

## Kept, with a reason

The README's six, confirmed: `refresh` (always "bypass a cache this tool reads"), the tool's own
verb beside `performed`, `path` / `fragment` / `identifier`, `shapekey_name` beside `name`, `refit`
defaulting to true (now in *two* tools, `mpfb_set_face_units` and `mpfb_apply_expressions`, both
FR 027 decisions) and the tool names. The census adds:

- **`weight` as a macro slider** in `mpfb_create_human` and `mpfb_set_macro_details`. It is one of
  MPFB's eleven macro names, which this effort does not change (README, Not a goal). It is a number
  input like the other ten, never a list entry, so it cannot be confused with an expression row.
- **`weight` on an expression row** (`mpfb_apply_expressions`, `mpfb_get_expression`, the summary's
  stack rows, `save_expression`'s `apply_with`). It is a multiplier that MPFB applies to a whole
  expression before summing, not a shape key's value.
- **`macro_target_stack[].weight`** in `mpfb_get_macro_details`. It is what MPFB *computed* a macro
  target's shape key should hold, and `macro_drift` exists to compare it with the value actually
  read off the key. One name for both sides would hide which side a number came from.
- **`previous_weight`** in `apply_expressions`' per-entry records, beside `weight`. It is R5's
  per-entry form with the field's own name. `previous_value` beside `weight` would pair names that
  do not match.
- **`source_value`, `destination_value_before`, `destination_value_after`** in
  `symmetrize_targets`. A symmetrize entry has two sides, and the side is part of the name. That is
  R5's whole-field form, `<field>_before` / `<field>_after`, where the field is `destination_value`.
- **`live`, `from_stack`, `now`** in `discarded_face_units` entries. These are one face unit read
  three times, named by where each reading came from: the live face, the stack's aggregate, and
  after the rebuild. `live` and `from_stack` are shared with `unexplained_face_units`, whose
  entries `discarded_face_units` extends.
- **`loaded_from`** (`set_targets`, `symmetrize_targets`: the path a target was loaded from, per
  entry) **and `loaded_from_disk`** (`set_face_units`: the names of units that had to be loaded).
  These are two concepts with two shapes, and neither name is used for the other.
- **`requested`** in `apply_expressions` (a list of per-entry outcomes) and in
  `create_human_from_preset`'s `overrides` records (a value). Both are "what the caller asked for".
- **`requested_name`** in `remove_asset`. It is the echo of the asset `name`, which is required and
  never resolved from the active object, so it is not a `subject_name`.
- **`kind`** in `create_human_from_preset`'s records. Its values are the preset file's own keys
  (`eyebrows`, …, `proxy`, `clothes`), which a caller matches against `save_preset`'s `contents`.
  They are not MPFB's object types.
- **`allowed_material_types`** in `add_asset`. It is the subset for *this* asset's type, not the
  whole vocabulary a `known_` key would list.
- **`load_clothes`**. It selects objects of MPFB's `Clothes` type and is MPFB's deserialization
  setting, and MPFB's type names are out of scope.
- **`save_preset`'s `contents`**. These are MPFB's file keys, read back verbatim (README, Not a
  goal).
- **`create_human_from_preset`'s `settings_used`** is MPFB's deserialization settings dict,
  reported as it was handed to MPFB. So after R7 it still says `material_instances` and
  `override_skin_model`, while `overrides` says `material_instances_policy` and
  `override_skin_type`. The two answer different questions: `overrides` is keyed by what the
  caller passed, and `settings_used` by what MPFB read. The description says so once.
- **The `<x>_reason` keys** (`refit_incomplete_reason`, `unavailable_reason`,
  `default_material_reason`, …) and a bare `reason` inside a per-entry record. `reason` always
  means "why this entry was not done", and a top-level reason always names what it explains.

## Prose (requirement 7)

Counted over the 32 descriptions plus the server instructions (`desc`) and `specifications/`
(`specs`).

| Concept | Spellings today (desc / specs) | Verdict |
|---|---|---|
| What the caller named | *subject* 26 / 51 | *subject* |
| The family of objects | *character* 78 / 66, *human* 9 / 32 | *character*. "human" survives only in tool names and MPFB's `is_human_project` |
| The body object | *basemesh* 50 / 16, *base mesh* 0 / 2 | *basemesh* |
| The eleven sliders | *phenotype* 11 / 5, *macro details* 3 / 1 | *phenotype*. The instructions say once that MPFB calls them macro details, which is what the tool names and the `macro_details` key carry |
| Per-category sliders and raw morphs, together | *detail targets* 2, *modeling targets* 2, *detail morphs* 1, *modeling morphs* 1, bare *morphs* 6 | *modeling targets*. A **modifier** is a per-category slider that drives one or two targets. A **target** is one morph, a `.target` file and the shape key it becomes. These match `mpfb_set_targets`' two arguments. "detail" is dropped because it collides with *macro details* |
| One worn item | *garment* 19 / 13, *clothes* 21 / 12 | *garment*. "clothes" stays only where MPFB's word is being quoted (`Clothes`, `load_clothes`, `override_clothes_material_type`) |
| Eyes, hair, teeth and the rest | *body part* 7, *bodypart* 1 | *body part*, and `bodyparts` only as the preset file's key |
| The topology replacement | *proxy* 21 / 7, *body proxy* 4 / 1, *topology proxy* 3 / 1 | *body proxy*, as `bodyproxy_name` spells it |
| Any of the three | *mesh asset* 4 / 4 | *mesh asset*: a garment, a body part or the body proxy, each equipped from an MHCLO |

## Found while the renames landed

- **Two tools build an answer without the bridge**, `mpfb_list_docs` entirely and `mpfb_list_urls`
  by merging, and the first census did not read them. It does now; neither diverges.
- **`name` stays in `create_human_from_preset`'s answer, one level down.** The top-level echo of
  the preset became `preset_name` (R1), and the `equipped_assets` records gained `name` (the mesh
  assets rule). `RENAMES` marks the first `old_stays` for that command.
- **R7 changed how `overrides` is read**, from one spelling for argument and setting to a table
  between them, and no test pinned it. The preset command's bridge test now does.
- **The face units' `weight` was also an entry key the tool validates itself**, not an argument,
  so it is refused with its replacement by the tool's own per-entry check rather than by
  `RETIRED_ARGUMENTS`.

## Out of scope

- **Five mutating tools answer an unresolved subject with no `blocked_by` key at all.** They are
  `refit_human`, `set_macro_details`, `set_targets`, `symmetrize_targets` and `set_face_units`.
  They return `found: false`, `ready: false` and no slug, while the other nine mutating tools add
  `blocked_by: "subject_not_found"`. That is a missing key, not a second spelling, so adding it
  changes a response's shape and is not a rename. It goes to NEXT_STEPS.
