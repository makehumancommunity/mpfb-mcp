# FR 036 census: what is written more than once

The input to [FR 036](README.md), taken on 2026-09-24 at `7449d36` by running
[census.py](census.py) over `bridge/mpfb_bridge/commands/`, `bridge/mpfb_bridge/shared/` and
`src/mpfbmcp/tools/`, and by reading every group it reported. A second pass over both test
suites was done by hand and is summarised at the end.

The script finds two kinds of duplication. **By name** means one module-level function name
defined in several modules. **By shape** means one pattern written under several names or inline,
which a census by name cannot see. The subject resolver is both kinds at once.

Each group gets one of five verdicts. They are derived from the rule as
[the README restates it](README.md#the-rule-restated), and not from the current text of
[architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one). The
current text puts the burden on sharing, and that burden was set when a shared fragment was pasted
into every program that used it. If review changes the restated rule, these verdicts are derived
again before any code moves.

- **Shared, because drift would mislead** (rule 1). If two copies drifted apart, a caller would
  get two answers that contradict each other, or one wrong answer it cannot detect.
- **Shared as one concept** (rule 2). The copies are identical, or deliberately different in a way
  a parameter can carry, and someone can name what they are.
- **Kept, a convention** (rule 3). One idea applied per tool, with a body that differs per tool.
- **Kept, with a reason** (rule 2's burden, met). Rule 2 would share it, and a specific reason
  says not to.
- **Out of scope.** Real, but not in the code this census searched. It goes to NEXT_STEPS.

## Shared, because drift would mislead

| Group | Copies | Where | Why it must not drift |
|-------|--------|-------|-----------------------|
| [Subject resolution](#subject-resolution) | 16 local + 1 shared, used by 18 commands | 14 `_resolve`/`_resolve_basemesh`, 2 inline in `_Request` builders (`save_preset`, `save_expression`), `get_object_info._resolve` and `generate_rigify_rig._resolve` (subject only), `shared/macro_reading.resolve_basemesh` | Every tool that takes a subject promises the same rules for it: the view layer and not `bpy.context`, the file and not the scene, any object in the family. It also says how the subject was resolved. |
| [The phenotype reading in `set_macro_details`](#the-phenotype-reading-in-set_macro_details) | 3 functions + 1 constant, twice | `set_macro_details` and `shared/macro_reading.py` | `set_macro_details` reports `macro_details` and `race_sum` after a write. `mpfb_get_macro_details` reports the same fields from a separate copy of the same code. |
| [Where a target lives on the mesh](#where-a-target-lives-on-the-mesh) | 5 functions twice, and the name rule a third time | `set_targets`, `symmetrize_targets` (byte-identical); `target_rollup._encoded` and `value_lookup` | Whether a target is on the mesh under its raw name or under its encoded one is a single rule. `mpfb_get_target_stack` and `mpfb_symmetrize_targets` must agree about it, which is the `modifier_reading.py` case. |
| [MPFB's unpublished surface](#mpfbs-unpublished-surface) | 18 `sys.modules` reaches in 15 modules, 6 helper names; `_property_value` ×6; `_as_path`/`as_path` ×7 | see below | Each copy carries a rule from [architecture.md](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish). A copy that breaks it does not fail. It quietly takes the fallback and answers with less. |
| [The caller's selection, restored](#the-callers-selection-restored) | 10 `finally` blocks | ten of the sixteen mutating commands. The two creators, the two savers, `remove_asset` and `generate_rigify_rig` have none | [mutating-tools.md](../../specifications/mutating-tools.md#where-these-rules-are-enforced) states it as a rule for every mutating command. Today ten copies enforce it. |

### Subject resolution

The **code** is the same in all sixteen copies: the view layer's active object or
`bpy.data.objects.get(name)`, and then `find_object_of_type_amongst_nearest_relatives(subject,
"Basemesh")`. The census puts fourteen of them into a single shape once string literals are
blanked. The remaining two, `save_preset` and `save_expression`, differ only in that they assign
to a `_Request`. **The differences are all in wording**, and they fall into three kinds:

1. **What did not happen.** A mutating command says so in its first two misses (`, so nothing was
   changed`, `nothing was refitted`, `no skin was applied`, `nothing was equipped`, `no rig was
   added`, `nothing was saved`, `nothing was generated`). A reading command does not.
2. **What the missing basemesh means.** The end of the third miss is per command: `so it has no
   target stack`, `so there is no face to compose`, and so on. `add_asset`, `add_rig` and
   `set_skin` add a clause explaining what attaches to a basemesh.
3. **Whether the third miss points at `mpfb_get_object_info`.** Eleven do. Five do not:
   `get_face_units`, `get_expression`, `set_face_units`, `apply_expressions` and
   `save_expression`, which are all FR 026 and FR 027 commands. **No reason for this was found**, so
   it looks like a copy taken from a copy rather than a decision.

Two differences are more than wording:

- **The vocabulary.** Seventeen commands report `subject_resolved_by: "active" | "name"`, and each
  computes it on its own line next to the resolver call. `get_object_info` reports
  `resolved_from: "active_object" | "name"`. This key is part of a response, so changing it would
  break callers. FR 036 records the difference and does not change it. See
  [README, Architecture](README.md#architecture).
- **The count in NEXT_STEPS was off.** It said eighteen commands resolve *to a basemesh* and
  seventeen were left. In fact eighteen resolve a *subject*, and sixteen of those go on to a
  basemesh: fourteen locally and two through `macro_reading`. `get_object_info` and
  `generate_rigify_rig` stop at the subject. `generate_rigify_rig` then narrows to a `Skeleton`,
  as [mutating-tools.md](../../specifications/mutating-tools.md#how-a-mutating-tool-takes-its-subject)
  describes. That leaves sixteen copies to replace, not seventeen.

**Nothing in the census suggests any command resolves differently on purpose.** The
NEXT_STEPS entry asked about this directly, whether some mutating commands might rightly resolve
differently. The ones that do something different do it *after* resolution: `add_rig` checks the
rig identifier before it refuses on the subject, `generate_rigify_rig` narrows to a skeleton, and
`remove_asset` and `set_asset_material` do not take a family member at all. A required asset name
is a different contract. Those two are not in the table above, and FR 036 does not touch them.

### The phenotype reading in `set_macro_details`

`_as_float`, `_macro_details_of`, `_race_sum_of` and `_RACE_SUM_TOLERANCE = 0.001` are
byte-identical to their counterparts in `shared/macro_reading.py`, except that `macro_reading.py`
spells the constant as a public `RACE_SUM_TOLERANCE`. FR 034 left them in place because the
summary does not read through `set_macro_details`. The warrant is the same one FR 034 used, applied
to a before/after report instead of a summary. The phenotype the setter reports after a write
should be the reading `mpfb_get_macro_details` would give on the next call, and one implementation
is the only way to guarantee that.

`_human_object_properties` in the same module is a different matter, covered under the
[unpublished surface](#mpfbs-unpublished-surface). `TargetService` has no setter, so the setter
genuinely needs it.

### Where a target lives on the mesh

`set_targets` and `symmetrize_targets` each define `_encoded`, `_key_blocks_of`, `_present_name`,
`_value_of` and `_shapekey_names`, and the two sets are byte-identical after docstrings are
stripped. `_present_name` looks for the raw name first and then for the name
`TargetService.encode_shapekey_name()` produces. A target name longer than 60 characters is stored
encoded. `target_rollup.value_lookup()` applies the same raw-then-encoded rule to a snapshot, and
`target_rollup._encoded` is the third copy of `_encoded`.

This is the case [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one)
states for `modifier_reading.py`: "what is shared is the rule; the pair of lookups is passed in".
The rule currently exists once for the snapshot and twice for the live mesh. If the two forms
drifted, a long-named target would be present in `mpfb_get_target_stack` and absent in
`mpfb_symmetrize_targets`.

### MPFB's unpublished surface

[Reading module-level names MPFB does not publish](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish)
sets three rules: read through a service's module and never import one fresh, always with a
fallback, and choose the service whose module actually imports the name. Fifteen modules
implement those rules themselves, 18 times. Six of them use a helper, and there are six helper
names for it: `_module_level`, `_objectservice_module`, `_humanservice_module`,
`_faceservice_module`, `_general_object_properties` and `_human_object_properties`. The rest reach
inline, from `get_character_summary`, `get_mpfb_status`, `list_asset_materials`, `set_face_units`,
`expression_divergence` and `macro_reading`. `asset_info.py`'s `Lookup` already gathers its own
reaches in one place, and the specification cites that as the reason `Lookup` exists.

The third rule is the one that fails silently. `HumanObjectProperties` is on `HumanService`'s
module and not on `ObjectService`'s. A copy that picks the wrong module gets the `None` fallback
and answers with less, and it does so without raising.

**The second rule has already drifted.** Four reaches read `FaceService`'s module-level
vocabulary as a plain attribute with no fallback:

- `get_face_units` (`ARKIT_FACEUNITS` and `FACEUNIT_REGIONS`)
- `set_face_units`
- `get_character_summary._face`
- `expression_divergence._arkit_faceunits`

If MPFB renamed `ARKIT_FACEUNITS`, those four would raise `AttributeError` inside the handler.
Every other reach would degrade instead. It may be right that these have no fallback, since a face
command without the vocabulary has nothing it can answer. But nobody decided that. The copies just
differ. FR 036 has to decide it one way or the other.

Two smaller helpers go with it, because they are how a value read off that surface gets into a
response:

- **`_property_value`**, six byte-identical copies, one of them private in `shared/asset_info.py`.
  It turns an unset `BlenderConfigSet` string (`""`) into `None`. If a copy drifted, one tool
  would report `asset_source: ""` and another `None` for the same object. That is the
  kind of contradiction the
  [summary rule](../../specifications/responses.md#a-summary-is-never-a-second-opinion) rules out,
  here between two tools of which neither is a summary.
- **`_as_path` / `as_path`**, seven byte-identical copies. Three of them are *public* exports of
  three different shared modules: `asset_sections`, `rig_lookup` and `target_categories`. It
  coerces a `pathlib.Path` that MPFB has been caught returning. A forgotten coercion does not give
  a wrong answer. It fails the whole call with `result_not_serializable`.

### The caller's selection, restored

The ten `finally` blocks have one shape: put back the resolved object's own selection state, then
put back the active object. The comments differ. What goes inside the `try` also differs, and has
to. `set_asset_material` restores the asset rather than the basemesh. FR 036 does not change
*what* is restored. The census records one gap for the effort to state in the specification rather
than fix: only the resolved object's selection is restored. An operator that selects *other*
objects, such as a new armature or an imported garment, leaves them selected.

## Shared as one concept

These are the groups the old restraint kept and the restated rule shares. None of them would
mislead a caller if it drifted. What they have in common is that each is one thing someone can
name, written several times, where an `import` now costs nothing.

| Group | Copies | Where | The concept, and what the variants need |
|-------|--------|-------|------------------------------------------|
| `_object_names` | 4, two variants | `add_asset`, `add_rig`, `remove_asset`, `create_human_from_preset` | Every object in the file as a set of names, used to find what an operation created. `create_human_from_preset` wraps each name in `str()`. Keep the `str()`: it is the stricter form, and a name is already a `str`. |
| `_vertex_group_names` | 2, identical | `add_asset`, `remove_asset` | The vertex group names on an object. It shares a home with `_object_names`: plain Blender data, read without MPFB. |
| `_material_names` | 2, identical | `set_asset_material`, `set_skin` | The material slot names on an object. Same home. |
| `_dotted` | 3, two variants | `get_status` (the bridge's version), `get_mpfb_status` and `list_urls` (MPFB's) | A version tuple as a dotted string. `get_status` checks for a tuple or a list, and the other two check only for `None`. Adopt the stricter check. If no module is a natural home for one function, this becomes **kept, with a reason** under rule 2. |
| Tool side: the optional subject name | 18, four variants | `_validated_name` in every tool that takes a subject | 15 copies are identical. Three tools make `name` required and say why: `remove_asset`, `set_asset_material` and `list_asset_materials`. The why is a phrase passed at the call site. |
| Tool side: a real `bool` | 16, one rule | `_validated_flag` ×10 in two spellings, `_validated_refresh` ×6 | One rule under two names. `refresh` is just a flag called `refresh`, and all the messages already format the same way. Several copies carry a comment explaining why truthiness would do harm *for that flag*, such as `import_weights`, `refit` or `overwrite`. That comment stays at the call site, where it is true. |
| Tool side: a non-negative count that is not a `bool` | 3, identical | `_validated_count` in `get_target_stack`, `list_assets`, `list_targets` | Unchanged. |
| Tool side: optional non-empty text | 8, one rule under two names | `_validated_text` ×4 (excluding `save_expression`'s, which is a different function) and `_validated_optional_text` ×4 | Seven copies return the value as given. `create_human_from_preset` returns it stripped, which is deliberate, because there the value decides whether the preset's own value is used. Strip at that call site. |
| Tool side: `_validated_subject`, `_validated_overwrite` | 2, 2, identical | `save_preset`, `save_expression` | Both fold into the rules above. The subject validator names its argument `subject` rather than `name`, so the argument name has to be a parameter. |

**What changed from the first draft of this census.** It kept all of these, saying a drifted copy
could not make two tools disagree. That argument answers rule 1 and says nothing about rule 2.

## Kept, a convention

| Group | Copies | Why it stays |
|-------|--------|--------------|
| `_blocked`, `_refusal` | 9, 8 | [architecture.md](../../specifications/architecture.md#shared-modules-and-what-warrants-one) calls these "one convention applied six times, differing only in which of that tool's own fields each nulls out". There are nine now, and the reasoning holds for all nine. It never depended on code generation. |
| `_message_for`, `_message`, `_precondition`, `_resolve_arguments`, `_entry` | 20, 6, 4, 3, 2 | One name for a role each command plays. Every body is different. |
| `_rig_refit_blocker` | 6, one shape | This is rule 4: [refit_blocker.py](../../bridge/mpfb_bridge/shared/refit_blocker.py) says "the condition is here; the wording is not". The census confirms that every copy asks the shared predicate. |
| The refit sequence (rig lookup, blocker, `refit()`, `refit_performed`) | 6, inline | Five lines around the shared predicate, interleaved with the command's own writes. This is closer to a convention than a helper, and the part whose drift would mislead a caller is already shared. |

## Kept, with a reason

| Group | Copies | Why it stays |
|-------|--------|--------------|
| `_shapekey_present` | 2 | These are not copies. The name is shared by two different functions: `get_face_units`' version returns a bool and `set_face_units`' returns a value. Renaming one would stop it appearing in the census, and that rename is worth doing if it reads better. |

## Out of scope

- **`tests/`: 29 copies of reaching into `mcp._tool_manager._tools`** (`_tool_callable` ×20,
  `_register_and_get_tool` ×9). Every copy differs only in which tool it names. Under rule 2 this
  is plainly one concept, and a single helper would also put the reach into a *private* FastMCP
  attribute in one place instead of 29. The census did not search `tests/`, so this is left to a
  test-harness effort. It goes to NEXT_STEPS.
- **`bridge/test/tests/`: `_result` ×17**, one per module, each unwrapping a dispatch envelope for
  its own command. [FR 035](../done/035-bridge-test-layers/README.md) has since moved every one of
  these files into its layers. Any consolidation would belong to the same test-harness effort.
