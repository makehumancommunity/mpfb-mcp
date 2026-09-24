# One word per concept across the tool surface

**Status:** Accepted

The specifications already have the rule: "A field that means the same thing in two tools is
spelled the same way in both"
([responses.md](../../specifications/responses.md#response-shape)). The rule holds for `found`,
`ready`, `blocked_by`, `performed`, the paging keys and the `requested_X` / `X_recognized` /
`known_Xs` echo. It does not hold across the whole surface. Thirty-six efforts named each tool
locally, and a read of all thirty-two descriptions and input schemas found two kinds of
divergence:

- **One name, different meanings.** `name` is the character in about sixteen tools and a preset
  or an expression file in three. `applied` is a success flag in two tools and a list of writes
  in two others. `changed` is a list in two tools and a bool in one. `material_instances` is a
  bool in one tool and a three-value string in another. `material_type` is MPFB's material-model
  enum when `mpfb_add_asset` takes it, and `identify_material()`'s lowercase vocabulary when
  `mpfb_get_object_info` reports it.
- **One meaning, different names.** The basemesh is `object_name` in one tool and `basemesh_name`
  in the rest. `identify_rig()`'s answer is `rig_type` in some tools and `rig_identified_as` in
  others. Adding versus replacing is `clear_first` in one tool and `mode` in another.

The caller is a language model. It generalizes from one tool to the next, and none of these
divergences fails when it generalizes wrongly. Several descriptions spend sentences explaining a
divergence, for example "not by `name` as every other tool here does" and "is exactly the
`object_type`". Those sentences cost part of a description budget that has about 500 B of
headroom left.

Checking what a rename would cost turned up one more fact. **The MCP layer ignores an argument
it does not know.** A call to `mpfb_list_docs` with `topc` misspelled returns every document,
not a refusal. The bridge refuses an unknown key ([validation.py](../../bridge/mpfb_bridge/validation.py)),
but FastMCP drops the key before the bridge ever sees it. Every rename in this request would turn
the old spelling into exactly that kind of silent no-op.

## Goals

**Primary:** no argument name, response key or refusal slug means two different things in two
tools.

**Primary:** each concept in the glossary has one spelling. Every deliberate exception is listed,
with its reason, so that the next reader confirms the decision instead of reopening it.

**Primary:** a tool refuses an argument it does not declare, so that a retired spelling (or a
misspelling) fails legibly rather than falling back to a default.

**Primary:** the glossary lives in the specifications, and the part that can be checked
mechanically is checked by a test.

**Secondary:** the sentences that exist only to explain a naming difference are deleted, and the
description ceiling is lowered by what they free.

**Secondary:** the [`resolved_from` / `subject_resolved_by`](../NEXT_STEPS.md#resolved-from-and-subject-resolved-by)
entry in NEXT_STEPS.md is closed.

**Not a goal:** changing what any tool does. Renaming tools, even where the prose says
"character" and the tool name says `human`. Changing MPFB's own vocabularies (object types, skin
types, the `$md-` and `!ex-` prefixes) or the keys of MPFB's own files read back verbatim, such as
`save_preset`'s `contents.skin_mhmat`. Changing the error envelope's nine slugs.

## Functional requirements

1. **A census comes first, and the renames come from it.** A `census.py` in this subdir lists
   every argument (name, JSON type, default, tool) from `build_server()`, every response key and
   refusal slug the bridge commands write, and every backticked term in the descriptions. A
   `census.md` gives each divergence a verdict: rename, or keep with a reason. The tables below
   are the starting point, taken from reading the descriptions. They are not the census. Where the
   census finds more, it goes in the tables. Where it contradicts them, the census wins.
2. **The glossary is written into the specifications.** It is a new section of
   [tool-interface.md](../../specifications/tool-interface.md). It covers the argument and
   response spellings in the rules below, and the prose terms in requirement 7. Each deliberate
   exception is listed with its reason.
3. **The collisions are removed.** Every row of [Collisions](#collisions) is resolved.
4. **The divergent spellings are unified.** Every row of [Divergent spellings](#divergent-spellings)
   is either renamed or moved to [Kept, with a reason](#kept-with-a-reason) by the census.
5. **An undeclared argument is refused.** Every tool refuses an argument its signature does not
   declare. The refusal names the argument and lists the ones that are accepted, in the same form
   as the bridge's refusal. For a retired spelling it also names the new spelling. It is refused
   before anything is sent, as every other shape rule is. **This lands first**, before any rename,
   so that no rename is ever silent for a caller still using the old spelling.
6. **The wire says the protocol changed.** Renamed command parameters are a change to the
   bridge's protocol. `PROTOCOL_VERSION` goes up on both sides, and `MIN_SUPPORTED_PROTOCOL_VERSION`
   goes up with it, so an old mpfb-mcp talking to a new bridge (or the reverse) gets the
   handshake's "upgrade X" refusal rather than a per-command `invalid_params`. It is **a straight
   rename**: there is no transition period in which both spellings are reported or accepted. The
   project is a proof of concept with no released users, and requirement 5 makes a stale spelling
   fail loudly, which is what a transition period would otherwise be for.
7. **The prose uses the glossary.** The descriptions and specifications use one term per concept:
   - *subject* is what the caller named;
   - *character* is the family of objects;
   - *basemesh* is the body object;
   - one term (*macro details* or *phenotype*) for the eleven sliders, with the other defined once;
   - one term for the per-category sliders and raw morphs, which are currently called *detail
     targets*, *modeling targets* and *detail morphs*;
   - one term each for *garment*, *body part*, *proxy* and *mesh asset*, and their relationship.
8. **Nothing that was true becomes false elsewhere.** The root [CLAUDE.md](../../CLAUDE.md)'s
   tool table, the specifications, module docstrings and the smoke items use the new spellings.
   [HISTORY.md](../HISTORY.md) and the `done/` requests are not rewritten. They record what was
   true when they were written.

### The rules the renames follow

- **R1. `name` is the object a tool operates on**, always a Blender object name. An argument that
  names a file-backed artifact is `<artifact>_name`.
- **R2. An object named in a response is `<role>_name`**, as in `basemesh_name`, `metarig_name`
  and `bodyproxy_name`. It becomes **`<role>_object_name` when the role also has a catalogue
  name** that could be mistaken for it: a rig has an `identifier` and a `name` in
  `mpfb_list_rigs`, and an asset has a `name` in `mpfb_list_assets`. Hence `rig_object_name` and
  `asset_object_name`.
- **R3. A tool's own success verb stays** beside `performed`, as
  [mutating-tools.md](../../specifications/mutating-tools.md#the-flag-a-caller-branches-on-is-called-performed)
  requires. A key that is some tool's verb is never a list in another tool. The per-entry list of
  writes is `changes`. The bool "did anything move" is `changed`.
- **R4. An identification is `<thing>_identified_as`.** It is not `<thing>_type`, which is
  reserved for the enum a caller passes. The two vocabularies are different sets, as
  [tool-interface.md](../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added)
  already says.
- **R5. A value before and after a write** is `previous_value` / `new_value` inside a per-entry
  record, and `<field>_before` / `<field>_after` for a whole field.
- **R6. The same choice has the same argument.** Merge versus replace is `mode`, and MPFB's type
  string is `object_type`.
- **R7. Where MPFB's own spelling disagrees with the glossary, the glossary wins.** The tool's
  description names MPFB's spelling once, where a caller reading MPFB's source would otherwise
  lose their bearings. MPFB is not consistent with itself: it uses `material_instances` both as a
  bool and as a string, and calls the material model `material_type` in one function and
  `material_model` in another. Mirroring it would bring those inconsistencies into these tools.
  This rule goes into [mpfb-integration.md](../../specifications/mpfb-integration.md), beside the
  existing rules for coping with MPFB.

### Collisions

| Where | Today | Proposed |
|---|---|---|
| `mpfb_save_preset`, `mpfb_save_expression` | `name` is the file, and `subject` is the character | `preset_name` / `expression_name`, and `name` is the character (R1) |
| `mpfb_create_human_from_preset` | `name` is the preset | `preset_name` (R1) |
| `mpfb_set_targets`, `mpfb_set_face_units` | `applied` is a list of writes, but it is `set_skin`'s and `set_asset_material`'s verb | `changes` (R3) |
| `mpfb_set_macro_details`, `mpfb_symmetrize_targets` | `changed` is a list, but it is a bool in `mpfb_apply_expressions` | `changes`. `apply_expressions` keeps `changed` (R3) |
| `mpfb_get_object_info`'s `asset_info`, and so `mpfb_get_character_summary` | `material_type` is `identify_material()`'s `makeskin`/`enhanced_skin`/…, but `mpfb_add_asset`'s `material_type` is `MAKESKIN`/`GAMEENGINE`/… | `material_identified_as`, as `mpfb_set_skin` already reports it (R4) |
| `mpfb_create_human_from_preset` | `material_instances` is `NEVER`/`ENHANCED`/`ENHANCEDMS`, but it is a bool in `mpfb_set_skin` | A new name (R7). `set_skin` keeps the bool. See [open question 2](#open-questions) |
| `mpfb_refit_human`, `mpfb_save_preset` | `rig_name` is the rig object, but it is an input to `mpfb_generate_rigify_rig` | `rig_object_name` (R2) |
| `mpfb_generate_rigify_rig` | `rig_name` is the name to give the generated rig | See [open question 1](#open-questions) |

### Divergent spellings

| Concept | Today | Proposed |
|---|---|---|
| The basemesh a tool made or changed | `object_name` in `mpfb_create_human`, `basemesh_name` elsewhere | `basemesh_name` |
| How the subject was resolved | `resolved_from: "active_object" \| "name"` in `mpfb_get_object_info`, `subject_resolved_by: "active" \| "name"` in seventeen others | `subject_resolved_by` |
| The addressed object does not exist | `not_found` in `mpfb_remove_asset` and `mpfb_set_asset_material`, `subject_not_found` elsewhere | `subject_not_found` |
| `identify_rig()`'s answer | `rig_type` in `mpfb_get_object_info`, the summary and `mpfb_generate_rigify_rig`'s refusal detail, `rig_identified_as` in the preset tools | `rig_identified_as` (R4) |
| MPFB's type string | `asset_type` (with `unknown_asset_type`/`known_asset_types`) in `mpfb_add_asset`, `object_type` everywhere else | `object_type` (R6, R7) |
| Merge versus replace | `clear_first: bool` in `mpfb_set_face_units`, `mode: "merge" \| "replace"` in `mpfb_apply_expressions` | `mode` (R6) |
| The material model | `material_type` / `skin_type`, and `override_skin_model` / `override_clothes_model` / `override_eyes_model` | `override_skin_type` / `override_clothes_material_type` / `override_eyes_material_type` (R7) |
| A per-entry before and after | `previous` / `new` in `mpfb_set_macro_details`, `previous_value` / `new_value` elsewhere | `previous_value` / `new_value` (R5) |
| A field before a write | `stack_before`, `material_source_before`, but `previous_alternative_material` | `alternative_material_before` (R5). The census lists the rest |
| The mesh assets on a character | `mesh_assets`, `mesh_assets_present`, `equipped_assets`, the summary's `assets` | The census decides. Some of these may be different sets under the same noun |

### Kept, with a reason

These go into the glossary as deliberate exceptions, so the next census confirms them:

- **`refresh`** always means "bypass a cache this tool reads". Which cache that is, and what it
  costs, is per tool and is said in each description. In three tools the cache is the
  `faceunits01` probe. That is still a cache, not a second meaning.
- **The tool's own verb beside `performed`** (`added`, `saved`, `generated`, and the others) is
  specified in mutating-tools.md.
- **`path` / `fragment` / `identifier`** are different identifiers for different kinds of thing,
  and tool-interface.md says why.
- **`shapekey_name` beside `name`** in the target tools exists because the two differ above 60
  characters.
- **`refit` defaulting to true in `mpfb_set_face_units`** was decided in FR 027.
- **Tool names**: a renamed tool breaks every client configuration and every saved transcript,
  which a renamed key does not.

## Non-functional requirements

- **Usability for the caller is the point.** The measure is whether a caller that has learned one
  tool reads the next one correctly without its description. A rename that makes a spelling
  consistent but less clear is worse than the inconsistency.
- **Robustness at the boundary.** Requirement 5 is what makes the renames safe. Without it, a
  caller still using `clear_first` gets an additive face and no error.
- **The description budget does not grow.** The ceilings in
  [test_description_budget.py](../../tests/test_description_budget.py) are not raised. Longer
  argument names cost schema bytes. The deleted explanations free description bytes. If the total
  falls, the ceiling is lowered to match, as that test's docstring asks.
- **One rename is one commit, across both sides of the socket.** A commit that renames a key in a
  command but not in its tool, its tests or its smoke item leaves `master` wrong. Grouping by rule
  (all of R3 in one commit) is fine.

## Architecture

- **Where requirement 5 goes.** FastMCP (mcp 1.29, pinned `<2`) builds each tool's argument model
  from the function signature, and that model ignores extra keys. `build_server()` in
  [__init__.py](../../src/mpfbmcp/__init__.py) already post-processes every registered tool once
  (it dedents the descriptions), so forbidding extra keys belongs there, in one place, and not in
  thirty-two tool modules. Check how the refusal reaches the client. It must be a tool error with
  the argument named, not a protocol-level failure the client hides. Check too that no MCP client
  sends extra arguments of its own. MCP's `_meta` travels in the request, not in `arguments`.
- **Every rename touches the same set of places**, which is why a rename has to follow the
  checklist rather than a search-and-replace:
  - the tool module's signature and description;
  - the command's `Param` and its answer;
  - the shared module, if the key comes from one (`asset_info.py` for R4, and `macro_reading.py` or
    `target_rollup.py` if the census finds more);
  - both test harnesses;
  - the smoke item;
  - the specifications that quote the key.
  [test_verification_smoke.py](../../tests/test_verification_smoke.py) catches a smoke item that
  names a key the description no longer does.
- **`mpfb_get_character_summary` has to rename in the same commit** as the detailed tool whose
  fields it carries. Its bridge test asserts that every shared field equals the detailed command's
  answer, so a half-done rename fails there. That is the test working, not a nuisance.
- **R1 swaps the meaning of `name` in `save_preset` and `save_expression`.** It does not just
  rename it. A caller using the old spelling passes the preset name as `name`, which now means the
  subject. That gives `subject_not_found` (or, worse, resolves to an object that happens to have
  that name) rather than an unknown-argument refusal. The refusal for a `name` that resolves to
  nothing should mention `preset_name` in these two tools.
- **`asset_info`'s keys are also the specification's example** in
  [responses.md](../../specifications/responses.md#how-tools-report-the-asset-behind-an-object).
  Renaming `material_type` and `rig_type` there changes the example too.

## Affected specifications

- [tool-interface.md](../../specifications/tool-interface.md): the glossary (new section), the
  argument-refusal rule, and the addressing section's note on `resolved_from`.
- [responses.md](../../specifications/responses.md): the "spelled the same way in both" rule
  points at the glossary, and the `asset_info` example is renamed.
- [mutating-tools.md](../../specifications/mutating-tools.md): R3 (a verb is never a list), and any
  key it quotes.
- [architecture.md](../../specifications/architecture.md#the-wire): the protocol version bump.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): R7, where MPFB's spelling
  disagrees with the glossary.
- [testing.md](../../specifications/testing.md), if the vocabulary test sets a precedent worth
  stating.

## Tests

- **A vocabulary test in `tests/`** (`test_vocabulary.py`) built on `build_server()`, the same way
  the description-budget test is:
  - no argument name has two JSON types across tools;
  - no retired spelling is an argument name anywhere;
  - every tool refuses an undeclared argument, and a retired spelling's refusal names its
    replacement.

  None of these needs a Blender.
- **Response keys are checked by `census.py --check`**, as FR 036's census was, and not by a
  permanent test. Answers are built bridge-side as dicts and keyword arguments. A denylist over
  that source would also match internal dictionaries, such as `remove_asset`'s
  `record["object_name"]`.
- **The existing tests are renamed with their keys**, on both harnesses. Few should change beyond
  spelling. A test that needs more than a spelling change is a sign that the rename changed
  behavior.
- **Live verification is the smoke run** ([verification/](../../verification/README.md)), plus a
  script in this subdir that calls every renamed argument once against a running Blender and
  asserts every renamed key is present and every retired one is absent. The bridge's unit tests
  already run against a real MPFB, but only a live run proves that both halves agree.

## Open questions

The request was accepted with these three still open. They are naming details that do not block
the effort. Each is decided when its rename lands, folded into the text above, and removed from
this list. Four questions were settled before acceptance: a straight rename with a protocol bump
(requirement 6), the glossary over MPFB's spellings (R7), refusing undeclared arguments in this
effort and first (requirement 5), and the prose in scope (requirement 7).

1. **What is `mpfb_generate_rigify_rig`'s input called?** It names an object that does not exist
   yet, and MPFB may uniquify it. Candidates are `new_rig_name`, `generated_rig_name`, or
   `rig_object_name` (the same key as the output that reports what it became).
2. **What is `mpfb_create_human_from_preset`'s `material_instances` called?** It chooses which skin
   types get per-region slots (`NEVER`, `ENHANCED`, `ENHANCEDMS`), while `mpfb_set_skin`'s bool
   asks for them on the one skin it builds. The candidate is `material_instances_mode`.
   `material_instances_used` and `material_instances_service_default` follow whatever it becomes.
3. **Face units: `weight` or `value`?** An `!ex-` shape key's number is `value` in
   `mpfb_get_target_stack` and `weight` in `mpfb_get_face_units`, `mpfb_set_face_units` and the
   expression tools. `weight` is MPFB's term for an expression row, which sums and clamps. A face
   unit read off a shape key is the same number the target stack calls `value`. The proposal is to
   keep `weight` for expression rows and face units, and to record why.

## References

- [FR 036](../done/036-subject-resolver-and-duplication/README.md), whose census is the model for
  this one and which recorded `resolved_from` rather than fixing it.
- [NEXT_STEPS: `resolved_from` and `subject_resolved_by`](../NEXT_STEPS.md#resolved-from-and-subject-resolved-by).
- MPFB's `HumanService.add_mhclo_asset()`, `set_character_skin()`, the `material_instances`
  handling in `HumanService` deserialization, and `MaterialService.identify_material()`, in
  `../mpfb2/src/mpfb/services/`.
