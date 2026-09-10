# Saving, listing and loading character presets

**Status:** Accepted

An agent driving these twenty tools can build a character and change it, but it cannot **keep**
one. Everything it assembles — phenotype, detail morphs, rig, garments, skin, eye materials, ink
layers — exists only in the running `.blend`, and the agent has no way to put it somewhere it can
be brought back from, nor to start from something a user built earlier by hand. A preset is MPFB's
answer to both, and it is a core part of the addon rather than an accessory: the "save file" is how
MPFB users move a character between scenes, between projects and between machines.

This request scopes three tools around
[`HumanService`](../../../mpfb2/src/mpfb/services/humanservice.py)'s serialization half: one to
list the presets that exist, one to write the current character into that namespace, and one to
build a character from a preset. It is the first entry in the
[Creation and modification](../../specifications/vision.md#target-tool-catalog) area that both
reads and writes a file MPFB owns, and it is the first time an mpfb-mcp tool causes a write outside
the `.blend`.

Two boundaries are drawn deliberately and are not up for rediscovery during the effort:

- **MHM is out of scope.** `HumanService.deserialize_from_mhm()` is right there and would be
  tempting to accept alongside a preset name, but MakeHuman's native format matters only in legacy
  pipelines, it needs two settings keys (`clothes_deep_search`, `bodypart_deep_search`) that
  `get_default_deserialization_settings()` does not contain, and its asset matching is a different
  problem — UUID and filename lookup against the installed library, with its own failure modes.
  The [NEXT_STEPS entry](../NEXT_STEPS.md#saving-listing-and-loading-character-presets) says to
  leave it; this request agrees and says why.
- **A preset is named, never a path.** See [Path policy](#a-preset-is-a-name-not-a-path).

Two queued efforts touch the same JSON and are deliberately separate.
[Expressions](../NEXT_STEPS.md#expressions) are serialized into a preset today
(`_populate_human_info_with_expression_info`, and `_apply_expressions_from_human_info` on the way
back), so they round-trip through these tools for free without this request implementing anything
about them. [Loading poses](../NEXT_STEPS.md#loading-poses) is unrelated: a preset stores no pose.

## Goals

**Primary:** an agent can save the character it just built under a name, find out later what names
exist, and rebuild the character from one — with no file paths, and with the same on-disk result a
user clicking MPFB's own panels would get.

**Secondary:**

- Give the queued efforts a durable subject. Anything that builds a character over several calls
  benefits from being able to checkpoint it.
- Establish what a tool that **writes outside the `.blend`** owes its caller, since there has not
  been one, and record it as a standing convention rather than as three tools' private habits.
- Confirm and file the `save_clothes` defect below, in the shape
  [FR 019](../done/019-file-mpfb-defects/README.md) established.

## Functional requirements

### `mpfb_list_presets` — what has been saved

1. Returns one entry per preset in MPFB's user config directory, each carrying `name` (the
   `<name>` in `human.<name>.json`, which is the identifier the other two tools take), `path` (the
   absolute file, for a human reading the response), `size_bytes` and `modified` (ISO 8601). The
   file is not parsed.
2. **Reports the directory it scanned** (`config_dir`) whether or not anything was found, so an
   empty answer is an answer rather than an ambiguity. An empty list with a named directory says
   "nothing is saved"; the same list with no directory would leave the agent unable to tell that
   from "the tool looked in the wrong place".
3. Takes `refresh` (a real `bool`, default `False`), which selects `use_cache=False` on
   `HumanService.get_list_of_human_presets()`. MPFB caches the scan in a module global
   (`_EXISTING_PRESETS`) and nothing invalidates it, so a preset written by another means since
   Blender started is invisible until a refresh — the
   [MPFB caches what it scans](../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides)
   obligation, and the tool says both halves.
4. **Not capped, not paged.** A user's preset collection is tens of files, not thousands. The
   docstring says so, so a caller does not look for `truncated`.
5. Reports `mtime`-derived fields from `os.stat`, not from MPFB, and says so per the
   [derived-fact convention](../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact).
   MPFB's own list is bare names.

### `mpfb_save_preset` — write the current character

6. Takes `name` (required) and the standard optional subject argument, resolving the basemesh from
   any object in the character's family exactly as the existing mutating tools do
   ([how a mutating tool takes its subject](../../specifications/mutating-tools.md#how-a-mutating-tool-takes-its-subject)).
   MPFB's own operator walks `find_object_of_type_amongst_nearest_relatives(..., "Basemesh")` from
   the active object; this is the same walk the package already implements.
7. Takes `overwrite` (a real `bool`, default `False`). **This collapses MPFB's two operators into
   one tool.** `mpfb.save_new_human_presets` refuses when the file exists and
   `mpfb.overwrite_human_presets` refuses when it does not; the two differ in nothing else, and a
   pair of MCP tools distinguished only by a precondition is a pair an agent will pick wrongly.
   With `overwrite: False` and the file present, the tool **refuses** — `ready: false`,
   `blocked_by` naming the existing preset, `performed: false`, nothing written — per
   [preconditions are answers](../../specifications/mutating-tools.md#preconditions-are-answers).
8. **Validates the name locally, and more strictly than MPFB does.** MPFB rejects only an empty
   name and one containing a space. It does not reject `/`, `\`, `..` or a leading dot, so
   `os.path.join(confdir, "human." + name + ".json")` will happily escape the config directory.
   This is the one place where the
   [validate the shape, never the vocabulary](../../specifications/tool-interface.md#validate-before-crossing-the-socket)
   rule and a filesystem meet: the *shape* of a preset name is knowable here, and the consequence
   of getting it wrong is a file written somewhere nobody will look for it. The check is a
   whitelist — letters, digits, `_`, `-`, `.` — with no path separator, no `..`, and a length
   bound. It rejects a space too, so that a name accepted here is a name MPFB's own panel would
   also accept and the two never disagree about what exists.
9. **Always reports the absolute file it wrote**, and whether it replaced an existing one
   (`overwrote: true/false`, with the previous file's size and mtime when it did). A write is not
   reversible across the socket and the caller cannot see the disk.
10. `performed` is stamped from `saved`, via [`performed.py`](../../src/mpfbmcp/codegen/shared/performed.py),
    like the other eleven mutating tools.
11. **Passes `save_clothes=True`**, matching both of MPFB's operators, which pass `True`
    positionally. See [the defect](#the-save_clothes-parameter-is-accepted-and-ignored) — the
    argument is dead today, so this is a bet on it starting to work rather than a behavioural
    choice, and the payload should carry a comment saying exactly that.
12. **Does not warn about a generated Rigify rig.** MPFB's operators report a `WARNING` when
    `identify_rig()` contains `"generated"`; this tool does not reproduce it, because the warning
    overstates the problem. `_populate_human_info_with_rig_info` handles the case: it infers the
    meta rig the generated rig came from (`RigService.infer_metarig_type_from_generated`), or falls
    back to `rigify.human_toes`, and records *that* in the preset. Nothing fails. What is true, and
    what the **tool description** should say once rather than the response saying it every call, is
    that a generated rig does not round-trip: reloading the preset yields the meta rig, and
    `mpfb_generate_rigify_rig` finishes the job. This is a
    [deliberate divergence from MPFB's UI](../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)
    and the module docstring must justify it, not merely note it.
13. **A rig `identify_rig()` cannot name is a different case and must not be silent.**
    `_populate_human_info_with_rig_info` raises `ValueError("Could not identify rig type. Custom
    rigs cannot be serialized.")` — a message that is misleading, since a custom rig present in
    user data *is* serialized, as `custom.<name>`. The payload catches this and turns it into a
    resolution refusal naming the armature object and saying the real cause (the rig is not one
    MPFB recognises, which for a `custom.` rig means its file is no longer in user data), rather
    than letting MPFB's text reach the agent.
14. Refuses, as a resolution error rather than an exception, when the subject is not an MPFB human
    project — `HumanObjectProperties.is_human_project` is false, which is what MPFB checks and is
    the case for an imported or hand-built mesh.

### `mpfb_create_human_from_preset` — build a character from one

15. Takes `name` (required), validated by the same whitelist as requirement 8, and refuses with
    `found: false` when no such preset exists — **naming the presets that do**, capped, per
    [how tools name things that can be added](../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added).
    A misspelled name is the likeliest failure and the response should end the guessing.
16. **The name says what the tool does.** This is not "load into the current character": it is a
    creation tool. `deserialize_from_dict` calls `create_human()` unconditionally, so a call adds a
    *new* character to the scene and changes no existing one. The description must state this in
    its first sentence, because "load a preset" reads to an agent like "restore over what is there".
17. Exposes the overrides that change the outcome, each defaulting to `None` meaning *use what the
    preset says*, in the
    [`mpfb_set_macro_details` idiom](../../specifications/tool-interface.md) where "not mentioned"
    and "set to the default" are different requests:

    | Argument | Effect |
    |---|---|
    | `override_rig` | `"NONE"` for no rig, or any identifier `mpfb_list_rigs` reports, including `custom.<name>` |
    | `override_skin_model` | Sets `skin_material_type`; same vocabulary as `mpfb_set_skin`'s `skin_type` |
    | `override_clothes_model` | Material model for clothes |
    | `override_eyes_model` | Material model for eyes |
    | `load_clothes` | Skip the garments and build the body only |
    | `scale` | `0.1` / `1.0` / `10.0`, MPFB's meter / decimeter / centimeter |
    | `material_instances` | Same three-valued setting `mpfb_set_skin` already models |

    The helper and vertex-group flags (`mask_helpers`, `detailed_helpers`, `extra_vertex_groups`,
    `feet_on_ground`, `subdiv_levels`) are **not** exposed. They are `create_human()` arguments an
    agent has no reason to reach for at load time, and each costs description budget that
    requirement 22 has very little of.

18. **Every settings dict starts from `HumanService.get_default_deserialization_settings()`.**
    `deserialize_from_dict` reads seven keys with `[]` rather than `.get()` — `mask_helpers`,
    `detailed_helpers`, `extra_vertex_groups`, `feet_on_ground`, `scale`, `subdiv_levels`,
    `load_clothes`, `material_instances` — so a partial dict is a `KeyError` from inside MPFB. The
    payload builds the default and overwrites into it; it never constructs one from literals. Note
    that `override_clothes_model` and `override_eyes_model` are **not** in that default dict even
    though `deserialize_from_dict` honours them (with `in` guards) and MPFB's own panel supplies
    them — so the vocabulary is wider than the defaults, and the payload must add rather than
    assume.
19. **Reports what was actually built**: the created basemesh's name, the rig object and its
    identified type, the equipped body parts and clothes, the skin material — and, beside each
    override the caller passed, the value the preset held. A preset that turned out to reference an
    asset that is no longer installed must be visible in the response rather than discovered later
    as a missing garment, so anything MPFB failed to resolve is listed.
20. **Reports the selection it leaves behind** (`active_object_after`). Deserialization ends with
    MPFB having created and activated objects, and there is no prior state to restore to — the same
    exception `mpfb_generate_rigify_rig` has and for the same reason, per
    [restore what was borrowed](../../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after).
21. **Does not reproduce the operator's UI conveniences.** `mpfb.human_from_presets` toggles edit
    mode to preselect a vertex group, sets an active material index by name suffix, and optionally
    runs Rigify generation. None of that belongs here: the vertex-group preselection is a
    modelling-workflow nicety with no meaning to an agent, entering edit mode across the socket is
    a hazard, and `mpfb_generate_rigify_rig` already exists and should be called explicitly. The
    module docstring should say each of these was considered and dropped, so the omission is not
    read later as an oversight.

## Non-functional requirements

**The description budget is again the binding constraint, and this effort has less room than
FR 024.** Three tools, and `mpfb_create_human_from_preset` alone has seven optional arguments to
instruct about. The ceiling must be raised deliberately, with the reason recorded beside it in
[`test_description_budget.py`](../../tests/test_description_budget.py), and the two catalogue-ish
tools held well under the average — `mpfb_list_presets` in particular instructs about almost
nothing. Where a vocabulary is already documented by an existing tool (skin models, rig
identifiers), the description **names that tool** instead of restating the list.

**Robustness: a refusal must never be a partial write.** Every precondition — the name's shape, the
file's existence under `overwrite: False`, the subject being an MPFB human, the rig being
identifiable — is settled before `serialize_to_json_file` is called. MPFB's own path is safe here
(`serialize_to_json_string` runs to completion before the file is opened), but the payload must not
rely on that: it validates, then writes.

**This is the first tool that writes outside the `.blend`, and that is the durable part of the
effort.** Everything else the package does is undoable with Blender's undo stack or by deleting an
object. A preset file is not, there is no confirmation channel across MCP, and a caller cannot see
the directory. That is why `overwrite` defaults to `False` and why the response always names the
absolute path. It is also why arbitrary paths are excluded.

**Cost.** All three programs are small — well under one 4 KB chunk, so one timer tick each. The
work is inside Blender: a save is fast, a load is seconds (it builds a whole character, equips
assets and fits clothes), and the description should not pretend otherwise.

## Architecture

### A preset is a name, not a path

The three tools address presets **only** by `<name>` within
`LocationService.get_user_config()`, resolving to `human.<name>.json`. No tool accepts a file path,
in either direction. Three reasons, and the third is the one that would otherwise be found the hard
way:

- Writing is confined to a directory MPFB owns. An MCP tool that writes to a caller-supplied path
  writes anywhere the Blender process can.
- It is the same namespace MPFB's panels use, so a preset saved through these tools appears in
  MPFB's dropdown and vice versa. Two namespaces would be two lists that disagree.
- `deserialize_from_json_file` extracts the name with
  `re.search(r'human\.([^/\\]*)\.json$', filename).group(1)` and **does not check the match**. Any
  path not of that exact shape raises `AttributeError: 'NoneType' object has no attribute 'group'`
  from inside MPFB — an error message with nothing in it about what the caller did wrong. Confining
  the input makes that unreachable rather than merely unlikely.

`update_list_of_human_presets` does a bare `os.listdir(confdir)`. Whether the config directory can
be absent on a fresh install is worth ten seconds of checking during the effort; if it can, the
list payload creates nothing and reports the absence as an empty list with `config_dir_exists:
false`.

### Three tool modules, three payloads

`tools/list_presets.py`, `tools/save_preset.py`, `tools/create_human_from_preset.py`, each with
the same-named payload and test module — the ordinary shape, no exceptions like FR 024's
payload-less tool. Three `register()` calls in [`__init__.py`](../../src/mpfbmcp/__init__.py).

**Is there a shared fragment here?** Probably one, and the effort should decide rather than assume:
the *preset name validation and path construction* is used by all three payloads, and the
`config_dir` reporting by all three. That is the bar
[`codegen/shared/`](../../src/mpfbmcp/codegen/shared) sets — a concept two or more payloads model
identically. Against it: the fragment would be perhaps fifteen lines, and
[FR 015](../done/015-fourth-shared-fragment/README.md) and [FR 017](../done/017-category-table-cost/README.md)
both found that a fragment earns its keep when payloads would otherwise *disagree*, not merely when
they repeat. Two payloads disagreeing about which characters are legal in a name is exactly the
kind of drift that matters, so the presumption is in favour — but the decision is the effort's, and
`test_codegen.py`'s drift check should follow it either way.

Use `MPFB_BOOTSTRAP` (the raising one) for all three. None of these tools is meaningful without a
working MPFB, so none of them is a case for `MPFB_STATUS_BOOTSTRAP`.

### The `save_clothes` parameter is accepted and ignored

`HumanService.serialize_to_json_string(basemesh, save_clothes=False)` never reads `save_clothes`.
The body calls `_populate_human_info_with_clothes_info(human_info, basemesh)` unconditionally, and
a `grep` for the name across `src/mpfb/` finds it in the two signatures, the two docstrings and one
pass-through — and nowhere else. Clothes are therefore always saved, and the documented default of
`False` describes behaviour that does not exist.

Nobody has noticed because both UI operators pass `True`. This is a defect in the
[FR 019](../done/019-file-mpfb-defects/README.md) sense and should be filed in
[`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../../mpfb2/features/MCP_DISCOVERED_BUGS.md) —
**after** confirming it against the running install rather than from source alone, which is FR 013's
correction and the reason FR 019 exists in the form it does. It is a small enough report that it
belongs in this effort rather than in a request of its own.

Two lesser candidates surfaced beside it, both worth a look during the effort and neither obviously
worth filing on its own:

- `_populate_human_info_with_rig_info`'s error text, *"Custom rigs cannot be serialized"*, is
  wrong: a custom rig in user data serializes as `custom.<name>`. The message fires when
  `identify_rig()` returns `None`/`"unknown"`/`"unkown"` — note that MPFB checks both spellings,
  which suggests the typo is load-bearing somewhere.
- `get_default_deserialization_settings()` omits `override_clothes_model` and
  `override_eyes_model` even though `deserialize_from_dict` honours them and MPFB's own panel
  passes them, so "the defaults" are not the full vocabulary. Requirement 18 works around this;
  whether it is a defect or a deliberate distinction between required and optional keys is a
  question for the effort, and the answer determines whether it is filed or merely documented.

### Naming

`mpfb_create_human_from_preset` rather than `mpfb_load_preset`, mirroring `mpfb_create_human` and
MPFB's own panel ("From save file" → "Create human"). It is longer, and it costs a few bytes in
every tool listing an MCP client downloads — but requirement 16 is the whole hazard of this tool,
and a name that states it is cheaper than a description paragraph that has to undo the wrong
reading. If the effort reverses this, the reversal belongs in the module docstring.

## Affected specifications

- [mutating-tools.md](../../specifications/mutating-tools.md) — **a mutating tool whose effect is
  outside the `.blend`**: what it owes the caller (name the absolute artifact; default to refusing
  an overwrite; never partially write on a refusal), and why Blender's undo stack does not cover
  it. This is the genuinely new standing rule.
- [tool-interface.md](../../specifications/tool-interface.md) — the
  [validate before crossing the socket](../../specifications/tool-interface.md#validate-before-crossing-the-socket)
  section gains the filesystem case: a name that becomes a path is a *shape* this side can and must
  check, and more strictly than MPFB does. Also the description-budget ceiling change and its
  reason.
- [mpfb-integration.md](../../specifications/mpfb-integration.md) — two entries. Under
  [where MPFB's own code paths disagree](../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it):
  the generated-Rigify warning MPFB's operators emit and these tools deliberately do not, and the
  UI conveniences requirement 21 drops. Under
  [MPFB caches what it scans](../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides):
  `_EXISTING_PRESETS`, which is a third instance of the same pattern.
- [responses.md](../../specifications/responses.md) — a response reporting a **filesystem** fact
  (`size_bytes`, `modified`, `config_dir`) is derived rather than recorded, and the existing
  convention covers it; check whether it needs extending or only an example.
- [vision.md](../../specifications/vision.md#target-tool-catalog) — the *Creation and modification*
  count goes from 11 to 14, and persistence becomes something the catalogue can claim.
- [architecture.md](../../specifications/architecture.md) — only if the shared fragment is created;
  the [shared fragments](../../specifications/architecture.md#shared-fragments) list is enumerated
  there and would go from six to seven.

## Tests

- **`tests/test_list_presets.py`** — over a real `tempfile` config directory, in the idiom
  `test_list_rigs.py` established for a payload whose job is `os.listdir`. Carries a file matching
  the pattern, one that does not (`human.json`, `humans.foo.json`, `human.foo.txt`) and must be
  ignored, an empty directory, and a missing directory. The `refresh` path asserts that
  `use_cache=False` reaches the stub service.
- **`tests/test_save_preset.py`** — name validation exhaustively on this side of the socket, which
  is where requirement 8 lives: `..`, `/`, `\`, a leading dot, a space, an empty string, a
  non-string, and an over-long name are each rejected **before** `send_code`. Then the payload
  against a stub character: a clean save, a refused overwrite (asserting the file on disk is
  byte-identical afterwards), an accepted overwrite, a non-human subject, and the unidentifiable
  rig turning into a refusal rather than a `ValueError`.
- **`tests/test_create_human_from_preset.py`** — a missing preset naming the ones that exist; each
  override reaching the settings dict and `None` leaving the preset's value alone; and the one
  test that matters most, that the dict handed to `deserialize_from_dict` **contains all seven
  keys MPFB reads with `[]`**. The stub must reproduce that access pattern — subscripting, not
  `.get()` — per [testing.md](../../specifications/testing.md)'s rule that stubs reproduce MPFB's
  real behaviour rather than convenient values. A stub that tolerates a partial dict would make the
  suite pass on exactly the bug this requirement exists to prevent.
- **A round trip in the stub world**: save a stub character, then load what was written, and assert
  the reconstruction requested the same phenotype, rig and assets. This is worth having even though
  both ends are stubs — it is the only place the two payloads' shared assumptions about the JSON
  are checked against each other.
- **`tests/test_codegen.py`** — three payload entries; plus the fragment and its drift check if one
  is created.
- **`tests/test_description_budget.py`** — ceiling raised, reason in the comment.
- **`tests/test_verification_smoke.py` and `verification/smoke.py`** — three items. Note that a
  smoke item for `mpfb_save_preset` **writes a file into the user's config directory**, which is
  the first time a smoke run leaves anything behind outside the `.blend`;
  [verification/README.md](../../verification/README.md)'s list of what the run cannot put back
  needs a line about it, and the item should use a name obviously belonging to the harness.

**This effort needs a real Blender, and for more than one claim.** Three of them cannot be reached
from this side: that `save_clothes` is ignored in the running install and not only in the source
read here (requirement 11 and the defect report both rest on it); that a preset written by
`mpfb_save_preset` is the one MPFB's own panel offers and loads; and that a full round trip —
build, save, load, compare — reproduces the character, which is the only check that establishes
these tools are useful rather than merely well-formed. A script in this subdir does all three
against a character carrying a rig, a garment, a body part and a non-default skin, prints what
differed, and moves to `done/` with the request. What stays behind is the three smoke items.

## References

- [`mpfb2/src/mpfb/services/humanservice.py`](../../../mpfb2/src/mpfb/services/humanservice.py) —
  `serialize_to_json_string` / `_to_json_file`, `deserialize_from_dict` / `_from_json_file`,
  `get_default_deserialization_settings`, `get_list_of_human_presets`,
  `update_list_of_human_presets`.
- [`mpfb2/docs/services/humanservice.md`](../../../mpfb2/docs/services/humanservice.md) — the
  Serialization, Deserialization and Presets sections. Note that it documents `save_clothes` as
  working.
- [`mpfb2/docs/fileformats/human_preset.md`](../../../mpfb2/docs/fileformats/human_preset.md) —
  what is actually in the JSON, key by key, including the asset-path-relative-to-any-asset-root
  convention the tools' responses must not mangle. This document is in
  [FR 024](../024-documentation-urls/README.md)'s candidate curated set, partly for this effort.
- MPFB's own UI, which these tools collapse:
  [`savenewpresets.py`](../../../mpfb2/src/mpfb/ui/presets/humanpresets/operators/savenewpresets.py),
  [`overwritepresets.py`](../../../mpfb2/src/mpfb/ui/presets/humanpresets/operators/overwritepresets.py),
  [`humanfrompresets.py`](../../../mpfb2/src/mpfb/ui/new_human/newhuman/operators/humanfrompresets.py),
  [`frompresetspanel.py`](../../../mpfb2/src/mpfb/ui/new_human/newhuman/frompresetspanel.py).
- [NEXT_STEPS: Saving, listing and loading character presets](../NEXT_STEPS.md#saving-listing-and-loading-character-presets)
  — the entry this request scopes.
- [FR 019](../done/019-file-mpfb-defects/README.md) — the established shape for a defect report,
  and the rule that a candidate is confirmed against a running install before it is filed.
- [FR 011](../done/011-skin-and-materials/README.md) — where `material_instances` and the skin-model
  vocabulary were settled; requirement 17 reuses both rather than restating them.
