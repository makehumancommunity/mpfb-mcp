# Tool interface

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

**What a tool accepts, and how things are named on the way in.** Two questions run through this
document. What may a tool decide for itself before the socket, and what must it leave to the far
side of it? And when a tool hands the caller an identifier, what obligation does that create for
the tool that consumes it?

"The far side" is a bridge command. A tool does not know what carries its call — that is the whole
of [Supporting a second backend](architecture.md#supporting-a-second-backend) — so a rule about
what a tool may decide is a rule about the tool, and it survived the transport underneath it being
replaced and then deleted without a word of it changing.

The counterpart document is [responses.md](responses.md), which covers what comes back;
[mutating-tools.md](mutating-tools.md) covers the extra obligations of a tool that changes
something, including how it resolves its subject.

## A tool description is call-time instruction with a budget

A tool's description is not documentation about the tool — it is the instruction the caller
reasons from, and an MCP client downloads all twenty-five of them before any work happens. That
makes it the one piece of prose in this repository with a **cost per session**, and it is measured:
[FR 013](../feature-requests/done/013-live-verification/review.md#does-the-tool-surface-fit-its-consumer)
found 66.7 KB of descriptions against an estimate of 58.5 KB, having grown unnoticed across five
requests because nothing counted it. `tests/test_description_budget.py` counts it now, against a
ceiling, so the next drift is a failing test rather than a discovery.

- **The test to apply to a sentence: would a caller with no access to this repository act
  differently for having read it?** If not, it is specification text, and it belongs here or in
  the tool module's or the command's docstring — where the maintainer who needs it is already
  standing. Why
  MPFB's label collision happens explains; *check `total_count` before concluding an asset is
  absent* instructs.
- **Surprising facts are instruction, and they stay in full.** That `mpfb_add_asset`'s `object_type`
  is required because MPFB's own default mislabels six of eight types, that `skin_type` follows the settings
  panel rather than the function signature, that exactly one of `path` and `fragment` may be
  given: each of these changes what a caller passes, and each is needed *because* the answer is
  surprising. Trimming is for rationale, never for these.
- **Name the response fields a caller branches on** — at minimum the success flag, the subject
  name, and the field carrying the thing the tool produced. FR 013's harness, written with the
  source open, cost itself a round trip on each of three tools whose description named the
  concept and not the key (`objects_removed`, `rig_object_name`, `asset_info.material_source`).
  A shorter description a caller has to guess against is worse than a long one.
- **What every tool would otherwise repeat belongs in the server instructions**, which are sent
  once rather than twenty-five times: the response envelope — including that a failure carries a
  short `error` slug to branch on beside the human `message` — the `name`/active-object subject
  convention, that a refusal is an answer carrying `found`, `ready` and `blocked_by`, the uniform
  `performed` flag, and that a capped listing always reports `truncated` and `total_count`. A
  tool then says only where it differs from the convention — which is the part worth reading.
- **Raising the ceiling is a decision, and it is made in the commit that needs the space.** FR 024
  raised it from 48,500 to 52,200 for two new tools: 740 B of headroom against a 400 B per-tool
  floor cannot absorb two, and trimming twenty descriptions to pay for two would have spent the
  effort's judgement on the wrong tools. What keeps that from being a licence is the *shape* of
  what was added — both newcomers came in around 1,900 B against a 2,387 B average, because a
  lookup tool instructs about a small static vocabulary and most of what its caller needs is
  visible in the response itself. A description that arrives at the average is carrying rationale;
  the ceiling moves by roughly what the new tools cost, and the paragraph of headroom stays a
  paragraph. FR 025 raised it again, from 52,200 to 59,200 for three tools, and its own numbers say
  what the rule is really asking for: the catalogue tool came in at 1,885 B, well under the 2,341 B
  average, while the two acting tools did not — `mpfb_create_human_from_preset` is the only tool in
  the package with seven optional arguments, each of which changes what is built and none of which
  a caller can discover from a response. An above-average description needs a reason of that kind,
  and it is not "the tool is important". [FR 027](../feature-requests/done/027-expression-library/README.md)
  raised it to 68,300 for four tools that all came in **under** the average (921 to 1,660 B),
  because it explained the one hard idea they share - that composing a face and applying a saved
  expression write the same shape keys, and the second erases the first - **once**, in
  `mpfb_set_face_units`' description, which grew by about 300 B to hold it, and had the other three
  point there. A concept several tools share is explained in the tool a caller meets it in first,
  not in each.
- **The docstring crosses the wire verbatim**, indentation included: FastMCP takes `fn.__doc__`
  as it is written. `mpfbmcp.build_server()` dedents every description once, after registration,
  because eight spaces per line across twenty-five tools is twelve kilobytes of whitespace an agent
  pays for and nobody reads.

## Validate before crossing the socket

Where a tool takes structured input (e.g. macro-detail sliders, which are only meaningful in
`0.0`-`1.0`), validate it in the tool function *before* anything is sent. A bad call should fail
fast and locally, not round-trip to Blender to fail there.

**The rule now stands in front of two sockets, and is unchanged by that.** Local validation runs
before a transport is even chosen, which is what keeps a migrated tool's refusals identical to an
unmigrated one's. The bridge then validates again, and that duplication is
[deliberate rather than redundant](architecture.md#both-ends-validate-deliberately): a listening
socket is reachable by anything on the machine and the add-on cannot assume its caller checked,
while mpfb-mcp cannot skip checking because that is what turns a silent wrong answer into a named
argument error. The division of labour is the same on both sides of both sockets — **shape here,
vocabulary there**.

**The shape rules live in one module on this side**, [`src/mpfbmcp/arguments.py`](../src/mpfbmcp/arguments.py):
an optional subject name, a required asset name, a real `bool`, a non-negative count that is not a
`bool`, and optional non-empty text. Every tool calls them and none keeps a copy
([FR 036](../feature-requests/done/036-subject-resolver-and-duplication/README.md)). The wording a
tool owns is passed at its call site — which asset a required name means and why it is required,
what an empty filter should have been instead — and why truthiness would do harm for a particular
flag is a comment at that flag's call site. A rule one tool alone needs, or whose body differs per
tool, stays in that tool's module.

**An argument a tool does not declare is refused**, naming the argument and listing the ones the
tool accepts — the same form as the bridge's refusal of an unknown parameter. FastMCP's argument
model ignores a key it has no field for, so without this `mpfb_list_docs` called with `topc`
answered with every document, and a renamed argument's old spelling reached its tool as the
default. The tool never sees such a key, so the check is made once for every tool, by the server
`build_server()` builds, before the call is handed to FastMCP, and it reaches the client as a tool
error like any other shape refusal. A spelling retired by a rename is listed per tool in
`arguments.py`'s `RETIRED_ARGUMENTS`, and its refusal also names what it became. That, rather than
a period in which both spellings are accepted, is what makes a rename safe for a caller that still
uses the old one ([FR 037](../feature-requests/done/037-one-word-per-concept/README.md)).

The same holds for the *shape* of a string argument: reject a non-string, or an empty or
whitespace-only one, and never quietly treat an explicitly empty value as an omitted one, since
the two arise from different mistakes. But validate only the shape, never the **vocabulary**. A
list of valid MPFB type names, asset names or target names kept on this side of the socket would
drift silently from MPFB's own. Send the value across instead and let the command answer
authoritatively, reporting alongside the result both whether the value was recognized and what the
valid values actually are — so a caller can correct itself from the same response rather than
needing a second tool or a hardcoded list.

There is one narrow exception: a vocabulary that is small, closed, MPFB's own enum rather than
anything derived from the user's disk, **and** which MPFB itself checks only after the damage is
done. There are two current cases:

- **`mpfb_set_skin`'s `skin_type`.** `set_character_skin()` deletes every material on the
  character *before* testing the value, and tests it with five separate `if` statements rather
  than a chain with an `else` — so an unrecognized value destroys the skin, builds nothing, and
  surfaces as a `ValueError` from a function that never saw the bad argument. See
  [Preconditions are answers](mutating-tools.md#preconditions-are-answers).
- **`mpfb_generate_rigify_rig`'s `meta_rig_action`.** `generate_rigify_rig()` silently falls back
  to `"hide"` for anything it does not recognize, which would make a typo indistinguishable from a
  choice — on the one argument (`"delete"`) whose wrong value cannot be undone.

In both cases the authoritative check stays in the command, ahead of anything destructive, and the
response still reports the valid values; the local check only means a typo never travels. Adding a
third case needs the same argument: naming the enum is not enough, the damage must precede the
check.

**A vocabulary this package defines is not an exception at all.** `mode` (`"merge"` or
`"replace"`), in `mpfb_apply_expressions` and, since
[FR 037](../feature-requests/done/037-one-word-per-concept/README.md), in `mpfb_set_face_units`
where it replaced a `clear_first` bool, is checked locally, and
[FR 027](../feature-requests/done/027-expression-library/README.md) planned it as a third case of
the exception above - but no MPFB function ever receives it. It selects between two ways the command
builds the stack, so it cannot drift from anything MPFB or the user's disk holds, and the reason not
to validate a vocabulary here does not apply to it. It is a shape, checked on both sides like any
other: locally, and in the command's parameter contract (`choices`), which the dispatcher enforces
before the handler runs. `mpfb_get_material_settings`' `section` is the second such vocabulary: its
three values are the preset's own keys as this package names them, not a name MPFB's node trees
hold ([FR 040](../feature-requests/done/040-procedural-material-settings/README.md)).
[FR 039](../feature-requests/done/039-exporting-characters/README.md) added four more:
`mpfb_create_export_copy`'s `mask_modifiers` and `subdiv_modifiers` (`KEEP`, `REMOVE`, `BAKE`)
and `material_type`, and `mpfb_export_character`'s `format` and `target_engine`. The first two look
like MPFB's - they are the Export copy panel's enum, spelled as it spells them - but no MPFB function
receives them: the panel's operator branches on them, and so does the command that reproduces it.
What decides the case is who consumes the value, not where its spelling came from.

**An argument that becomes a path is a shape, not a vocabulary, and it is checked here.**
`mpfb_save_preset` and `mpfb_create_human_from_preset` take a `preset_name` that resolves to
`human.<preset_name>.json` in MPFB's user config directory, `mpfb_save_expression` takes an
`expression_name` that resolves to `<expression_name>.json` in the expressions directory of MPFB's
user data, and `mpfb_export_character` takes an `export_name` that resolves to
`<export_name>.fbx`, `.glb` or `.usdz` in the export directory - one rule
for all three, in `mpfbmcp.artifact_names`, with the noun in the refusal as its only argument; and a name carrying `/`, `\` or `..` would
address — and on the saving side *write* — a file outside it. Which characters may appear in a
filename cannot drift from anything on the user's disk, so this is the ordinary rule rather than an
exception to it, and it is deliberately stricter than MPFB's own panel (which rejects only an empty
name and one containing a space; the expression composer's save operator rejects only a path
separator, `.` and `..`). Strictness runs one way only: every name accepted must be one
MPFB would also accept, so the two never disagree about what exists — and where the reverse fails,
the catalogue tool flags it (`mpfb_list_presets`' `addressable`) rather than letting a caller meet
it as a refusal. The rule is also restated on the add-on side, as the last statement before
`open()`, because a listening socket is reachable by anything on the machine; the two
implementations are run over one table of names, as all three nouns, by `tests/test_save_preset.py` so
they cannot drift. **No tool takes a directory**: where an export lands is chosen by the person
running the bridge, so the only part of a path a caller supplies is a name. What that buys is in
[a tool whose effect is outside the `.blend`](mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more).

**Structured input is taken as flat scalar arguments, not as a nested dict.** `mpfb_create_human`
takes eleven separate macro sliders rather than the `macro_detail_dict` MPFB's own
`create_human()` wants, and `mpfb_set_macro_details` takes the same eleven names. That is
deliberate and general: a flat scalar is what an MCP tool schema describes and validates well, and
what a client fills in reliably, while a nested dict-of-dicts is a shape an LLM gets subtly wrong —
misspelling a container key, omitting one, nesting a field under the wrong parent — and it pushes
per-field validation into a hand-written dict walk that no schema checks. Flat arguments also
express something a dict cannot without a sentinel: on a mutating tool, an *omitted* argument means
"leave this alone", which is what makes a relative change ("a bit older") a single call.

Round-tripping is preserved on the **output** side instead: a tool returns the nested dict in
MPFB's own shape, so a caller can read a character, hand the dict elsewhere, and map it back onto
flat arguments mechanically. Assemble MPFB's structure in the tool function, from the flat
arguments, immediately before generating code.

**The one exception is a batch, which is irreducibly a list.** `mpfb_set_targets` takes
`modifiers` and `targets` as lists of dicts, because the alternative to a batch is thirty round
trips (see [A batched mutating tool resolves before it writes](mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes)),
and a list of one repeated shape is not the dict-of-dicts the clause above rules out. What the
clause is really protecting against — a shape no schema checks — still applies, so a batch carries
two compensations:

- **Validate every entry's shape here, entry by entry, and name the position that failed.** That an
  entry is an object, that its keys are all known — a misspelled key is the commonest way a caller
  gets a dict-shaped argument wrong, and it is silent unless checked — that a value is a real number
  in range, that an enumerated string is one of its values. `modifiers[1] has unknown key(s)
  catagory` is a message a caller can act on; a silently ignored key is not.
- **Give the response a per-entry error channel**, so the half of the validation that can only
  happen inside Blender comes back the same way: which entry, why, and what the valid values were.
- **One key per JSON type, even when that means two keys for one idea.**
  `mpfb_set_material_settings` writes either a float socket or a colour socket, and takes `value`
  for the first and `color` for the second, exactly one per entry, rather than one key carrying
  either a number or a list. A three-number `color` is refused with a sentence saying alpha is
  required, and a negative component because Blender stores it as zero; a component above 1.0 is
  kept, because Blender keeps it.

## How a tool addresses an object

Tools name a Blender object by its **Blender object name**. Names are unique across the whole
`.blend`, which is what makes them a usable address, but that has consequences a tool must not
paper over:

- **Listing is scoped to the current scene** (`bpy.context.scene.objects`), so results match what
  the user is looking at, while **resolution is scoped to the file** (`bpy.data.objects`). A name
  can therefore resolve to an object that a listing did not mention. Report that as a distinct
  answer — an `in_current_scene` flag — rather than as "not found", which would be false, or
  silently, which would make two tools look as if they contradict each other.
- **Every object in a response carries that flag, not only the subject.** MPFB's relationship walk
  reaches relatives through `ObjectService.get_list_of_children()`, which iterates
  `bpy.data.objects`, and several of its Rigify helpers do the same. A relative can sit outside the
  current scene, and filtering it out would silently drop a real relationship.
- **A subject may also be "whatever is active"**, read as `bpy.context.view_layer.objects.active`
  rather than `bpy.context.active_object`: a command runs from a socket rather than from a viewport
  operator, and the view-layer form does not depend on which UI area happens to be current. It is `None` whenever nothing is active, which is an ordinary answer rather than a
  failure. A response should say which way its subject was resolved, because the two have very
  different lifetimes: a name stays valid until the object is renamed or deleted, while an
  active-object answer is stale the moment the user clicks elsewhere.
- **All of this is read in one place.** The twenty commands that take a subject resolve it
  through [`shared/subject_resolution.py`](../bridge/mpfb_bridge/shared/subject_resolution.py):
  the view layer's active object or a name looked up in the file, then any member of the family to
  its basemesh the way MPFB's own panels find it, and how the subject was resolved. Each command
  still phrases its own misses. All twenty report `subject_resolved_by: "active" | "name"`.
  `mpfb_get_object_info` said `resolved_from: "active_object"` until
  [FR 037](../feature-requests/done/037-one-word-per-concept/README.md) renamed it, which
  [refusing an undeclared argument](#validate-before-crossing-the-socket) and the protocol version
  made safe to do without a period of reporting both.

Object addresses are never cacheable. Unlike `mpfb_get_status`'s output they are things later
mutating tools will act on, so a stale one is worse than a missing one.

## How tools name things that can be added

[How tools report the asset behind an object](responses.md#how-tools-report-the-asset-behind-an-object) covers
naming something that already exists. A *catalogue* tool — one listing what could be added, such as
`mpfb_list_rigs` — has the parallel problem, and it is not solved by reporting a name:

- **Report the exact identifier the acting tool will need**, as its own field, never a display name
  or a filename the caller must transform. A rig is *called* `human` and *added* as
  `rigify.human`; a custom one is added as `custom.my_rig`. Any part of that string the caller has
  to assemble is a part they can assemble wrongly, and reassembling it is precisely the guesswork a
  catalogue exists to remove. The sharpest case is `mpfb_list_targets`' `shapekey_name`, which
  equals the target's filename for most targets and, above 60 characters, does not — and addressing
  a target by the wrong one of the two does not fail, it reads back `0.0`. Where an identifier
  *usually* equals something the caller already has, report it anyway: the exceptions are exactly
  where a caller would not think to look.
- **An entry may need more than one identifier, and the portable one is not always the one the
  function takes.** `HumanService.add_mhclo_asset()` takes an absolute *path*, while the value MPFB
  records on the resulting object, and the one that survives a move to another machine, is the
  *fragment*. Report both, and say which is which: a catalogue whose identifier cannot be stored is
  as awkward as one whose identifier cannot be passed. The same entry can also carry a second
  identifier hiding as a description — that function's `asset_type` argument takes exactly the
  `object_type` string the catalogue reports, and defaults to `"Clothes"`, so hair added without it
  becomes clothes.
- **Say which function consumes it, when there is more than one.** `HumanService` adds rigs through
  `add_builtin_rig()` and `add_custom_rig()`, and they are not interchangeable. Crossing them does
  not fail legibly: `add_builtin_rig("custom.my_rig")` looks for a file called
  `rig.custom.my_rig.json`, while `add_custom_rig()` strips the first seven characters of whatever
  it is given as though they were a `custom.` prefix, so a built-in name comes back missing under a
  mangled one. A later acting tool has to dispatch on this, and a caller reading the response should
  be able to see why.
- **Report what acting on the entry would do, where that is not implied by the entry.** A rig with
  no weights produces an unweighted character, and MPFB resolves weights through a fallback table
  rather than by filename — so an entry whose weights come from a *different* rig is normal, and one
  with no weights at all is not. Mirror the acting function's own resolution rather than guessing
  from filenames, and report the outcome.
- **An absent entry must be explainable.** Report the directories that were actually scanned (not
  every configured data root — MPFB does not look in all of them for everything), anything a scan
  silently refused, and any precondition that makes a whole family unusable. This is the same
  quality attribute as `mpfb_list_objects`' `object_type_recognized`: an agent that reads a short list as
  the whole truth will conclude rather than investigate.
- **A catalogue vocabulary and an identification vocabulary are not the same set**, even when they
  overlap. `RigService.identify_rig()` reports `rigify_generated.*` and `unknown`, neither of which
  names anything addable. Where a tool's values overlap another tool's without matching them, the
  docstring must say so, or a caller will read a legitimate miss as a failure.

## An acting tool accepts every identifier its catalogue reports

[How tools name things that can be added](#how-tools-name-things-that-can-be-added) requires a
catalogue to report more than one identifier per entry, because the passable one and the portable
one are not the same string. The obligation on the *acting* tool is the other half of that: **it
takes them all, requires exactly one, and reports which one resolved and to what.**

- **Taking only one of them makes the other half of every catalogue entry decorative.**
  `mpfb_add_asset` accepts the absolute `path` and the `fragment` alike. A tool that took only the
  path would make a stored character description — which is what a fragment is *for*, since it
  survives a move to another machine — unusable without a lookup step the caller has to invent. One
  that took only the fragment would pay an `os.walk` of the asset roots on every call, including the
  calls where the caller already had the file.
- **Exactly one, never both, and never neither.** They can name different files. Silently preferring
  one would attach an asset the caller did not ask for, and there is no reading of "both" that is
  more likely to be right than refusing. An exception to "never neither" needs a reason of its own,
  not a relaxation of the rule: `mpfb_set_skin` accepts neither identifier when — and only when —
  `skin_type` is `LAYERED`, which is the single skin type that has a material to build from no file
  at all. "Neither" is a meaningful request there and a mistake everywhere else, so it is refused
  everywhere else.
- **Report the resolution, because it is lossy.** `find_asset_absolute_path()` matches on the
  fragment's *basename*, prefers a candidate whose parent directory also matches, and otherwise
  returns the first hit — so two packs shipping `hat.mhclo` resolve to a coin toss. `resolved_path`
  is always in the response, beside a `path_resolved_by` saying which identifier was used. This is the
  acting-tool counterpart of `mpfb_list_assets`' `pack_ambiguous`: the derivation is unsafe in a
  minority of cases, and the caller cannot tell which case they are in unless the tool says.
- **An identifier hiding as a description is still an identifier.** `add_mhclo_asset()`'s
  `asset_type` takes exactly the `object_type` the catalogue reports, and defaults to `"Clothes"` —
  so hair added without it *becomes* clothes, permanently and silently. Where a defaulted argument
  changes what the character *is*, the tool requires it rather than inheriting the default, and says
  in its docstring that it diverges from MPFB's own signature for that reason. `mpfb_add_asset`
  takes it under the catalogue's name, `object_type`, rather than MPFB's.
- **Where what the tool writes *is* one of the identifiers, it takes that one only.**
  `mpfb_apply_expressions` takes `fragment` and not `path`, although `mpfb_list_expressions` reports
  both. The tool does not load a file; it writes a stack row, and a stack row is a fragment. A path
  would have to be converted back, and MPFB's own conversion
  (`_compute_expression_library_relative_path()`) returns the bare basename for a file outside
  every root - a row that would then resolve to some other file, or to none, on the next rebuild.
  Taking the path would make the tool accept something it cannot store faithfully. The resolution
  is still reported (`resolved_path` beside `listed_path`, per row), for the reason the clause
  above gives.

## The glossary

**One concept has one spelling across every tool, and one spelling means one concept.** The caller
is a language model that generalizes one tool's names to the next, and none of the divergences
this section removes failed when it generalized wrongly: a misspelled argument used to be dropped
silently, and a key read under another tool's name comes back `None`.
[FR 037](../feature-requests/done/037-one-word-per-concept/README.md) took a census of every argument,
answer key, refusal slug and backticked description term and renamed what diverged; this is what
it settled, and each exception below is listed with its reason so that the next census confirms it
rather than reopening it.

The mechanical part is checked by `tests/test_vocabulary.py`: every tool refuses an undeclared
argument (see [above](#validate-before-crossing-the-socket)), `arguments.RETIRED_ARGUMENTS` is
coherent with what each tool declares, and no argument name carries two JSON types - an array
counted by what it holds, so a list of names and a list of objects under one name are two
([FR 044](../feature-requests/done/044-switches-filter/README.md)). Answer keys are
built bridge-side as dicts, and a permanent check over that source would also match internal
dictionaries, so they were checked by the FR's own `census.py --check` instead.

### Arguments and answer keys

| Concept | Spelling | Not |
|---|---|---|
| The object a tool operates on | `name` — always a Blender object name, and optional wherever the active object will do | a file's name |
| A file-backed artifact the tool reads or writes by name | `<artifact>_name`: `preset_name`, `expression_name`, `export_name` | `name` |
| An object that does not exist yet | `generated_rig_name`, a basename the answer's `rig_object_name` reports the outcome of | `rig_name` |
| An object named in an answer | `<role>_name`: `basemesh_name`, `metarig_name`, `bodyproxy_name`, `subject_name` | `object_name` |
| …when the role also has a catalogue name | `<role>_object_name`: `rig_object_name`, `asset_object_name`, `subrig_object_name` | `rig_name` |
| An object inside a record *of* objects | `name` (`list_objects`, `related_objects`, `equipped_assets`) | `object_name` |
| An object inside a record *about something on* it | `object_name` (`materials_destroyed`, `vertex_groups_left_behind`) | |
| How the subject was resolved | `subject_resolved_by: "active" \| "name"` | `resolved_from` |
| How a file path was found | `path_resolved_by`, beside `resolved_path` (which identifier: `"path"`, `"fragment"`), or beside `path` for an export (who chose the directory: `"command_line"`, `"preferences"`, `"default"`) | a bare `resolved_by` |
| The subject could not be resolved | `blocked_by: "subject_not_found"` | `not_found` |
| A tool's success | its verb beside `performed` ([mutating-tools.md](mutating-tools.md#the-flag-a-caller-branches-on-is-called-performed)) | |
| A batch tool's per-entry writes | `changes`, with `change_count` | `applied`, `changed` — both are other tools' verbs |
| What MPFB identified an object as | `<thing>_identified_as`: `rig_identified_as`, `material_identified_as` | `rig_type`, `material_type` |
| MPFB's type string for an object | `object_type`, wherever it is passed or reported | `asset_type` |
| A value before and after, in a per-entry record | `previous_value` / `new_value` | `previous` / `new` |
| A reference moved from one object to another, in a per-entry record | `previous_object_name` / `new_object_name` (`copy_repairs.references_retargeted`) | `from` / `to` |
| The effective value of every option a tool takes many of | `options_used` (`mpfb_create_export_copy`, keyed by argument name), `exporter_options` (`mpfb_export_character`, keyed as Blender's exporter takes them) | twelve `requested_*` keys |
| A file format, and the engine a preset is for | `format`: `"fbx"`, `"gltf"`, `"usd"`, echoed as `requested_format` beside the `format` used; `target_engine`: `"generic"`, `"unity"`, `"unreal"`, `"godot"`, with `known_formats_for_target_engine` | `file_type`, `engine`, `glb` |
| Load a set of shape keys onto an export copy | `load_microsoft_visemes`, `load_meta_visemes`, `load_arkit_face_units` - "face unit" is two words, as everywhere else | MPFB's `visemes_microsoft`, `faceunits_arkit` |
| Put the copy in MPFB's "export copy" collection | `in_export_collection`, a bool | MPFB's `collection`, which reads as a collection's name |
| An export copy's processing of a modifier type | `mask_modifiers`, `subdiv_modifiers`: `"KEEP"`, `"REMOVE"`, `"BAKE"`, the panel's own spelling | lower case |
| A whole field before and after | `<field>_before` / `<field>_after` | `previous_<field>`, `current_<field>` |
| Adding to what is there, or making it exactly this | `mode: "merge" \| "replace"`, and what a replace dropped is `removed_by_replace` | `clear_first` |
| The echo of an argument `X` | `requested_X`, `X_recognized`, `known_Xs` — `X` the argument's own name | a shortened `X` |
| What a shape key holds, a face unit included, and a float socket | `value` | `weight` |
| A colour socket's value, four scene-linear RGBA numbers | `color` | a hex string, or `value` carrying a list |
| An sRGB rendering of a colour, derived and never accepted back | `srgb_hex`; per-entry `previous_srgb_hex` / `new_srgb_hex` | `hex`, `srgb` |
| An input on one of MPFB's node groups, by its live name | `socket` | `input` |
| A layered skin group, by the preset's key (`color`, `body`, ...) | `group` | the node name `colorgroup` |
| A multiplier over a whole expression | `weight`, on an expression row | |
| The object names of a character's mesh assets | `mesh_assets`, qualified by moment or subset (`mesh_assets_present`, `mesh_assets_not_rigged`) | |
| One record per mesh asset on a character | `equipped_assets` | `assets`, which is `mpfb_list_assets`' catalogue |
| Who made an installed file and under what terms, as pack metadata records it ([FR 046](../feature-requests/done/046-license-in-the-catalogues/README.md)) | `license`, `author`, `source_url` (the asset's community page) and `packs` (every claimant, sorted), beside `pack` (one claimant, the one a `pack` filter matched); on an equipped asset's `asset_info`, `material_license`/`material_author`/`material_packs` for its material. `license` is also `mpfb_list_assets`' exact, case-insensitive filter, echoed as `requested_license`/`license_recognized`/`known_licenses`; `counts_by_license` with `license_unknown_count` beside it, since `null` is no JSON key; `matched_packs`, per pack a `pack` filter matched, the installed files it claims; `attribution_conflicts`, claimants that disagree | `source`, which reads as a short form of `asset_source` - a fragment, a different concept |
| A part of the body a posing tool groups bones by | `body_part` in an answer, `body_parts` the argument; one of `root`, `torso`, `head`, `face`, `left_arm`, `right_arm`, `left_hand`, `right_hand`, `left_leg`, `right_leg` — feet and toes belong to the leg | Rigify's collection names (`Arm.L (IK)`), `limb` |
| What a control is for, on a classified rig | `role` in an answer, `roles` the argument (a filter, `mpfb_get_pose_controls` only); one of `root`, `body`, `fk`, `ik_control`, `pole`, `ik_chain`, `foot_roll`, `switches`, `finger_master`, `finger_segment`, `toe_master`, `toe_segment`, `tweak`, `look_target`, `face_control` | `type`, `kind` |
| A control a person posing the rig starts without | `hidden_by_default`, a static flag decided by the rig - never whether a collection is visible now ([FR 043](../feature-requests/done/043-narrower-pose-controls/README.md)) | `visible`, `hidden` |
| The shorter form of a listing, chosen by the caller | `compact`, a bool, echoed back; its entries drop keys rather than null them ([why](responses.md#how-tools-bound-a-large-answer)) | `brief`, `summary` |
| Which of a limb's chains a control belongs to | `chain`: `"ik"`, `"fk"`, or `null` off a limb | `mode` |
| A position or direction **on** a character | an object with `forward`, `left`, `up`, in metres from the rig object's origin ([the character frame](responses.md#a-position-on-a-character-is-in-the-character-frame)); a rotation is `{"axis": <that>, "degrees": n}` | a world-space `[x, y, z]` - which is the next row's, and only for where the character itself stands |
| Where a character **stands** in the scene ([FR 045](../feature-requests/done/045-placing-a-character/README.md)) | `position`, an object with any of `x`, `y`, `z` in world metres (the root's origin); `facing`, degrees about world up, `0` facing world -Y as MPFB builds characters, positive counter-clockwise seen from above, answered in `(-180, 180]`; `face_toward`, a point `{"x", "y"}` or `{"object": <name>}`, instead of `facing`. Read back by `mpfb_get_character_summary`'s `placement` and as `position_before`/`position_after`, `facing_before`/`facing_after` by `mpfb_place_character`; `footprint` is the visible geometry's world box, `min`/`max` and `width`/`depth`/`height` along world X/Y/Z | `location`, `rotation`, `yaw`, a frame vector |
| What a placement cannot express or aim at | `blocked_by: "character_tilted"` (turned about more than world up; a `position` alone is still taken) / `"face_toward_not_found"` / `"face_toward_has_no_direction"` (straight above or below) | |
| A garment's sub-rig bound wrong | `subrigs_broken`: per sub-rig, `subrig_object_name`, `asset_object_name` and the measured `displacement` in metres; `[]` when none is | `subrigs_broken_by_move`, as scoped - a move breaks none |
| A change to a pose bone, in an entry of `bones` | a position as `move_by` (an offset) or `move_to` (where the head goes, as `mpfb_get_pose` reports `head`); a rotation as `rotate_by` (about the head), `rotate_to` (from rest, as `mpfb_get_pose` reports `rotation`) or `aim` (head-to-tail direction) with `twist` (degrees about the bone's own axis); `scale_to`, factors keyed `x`/`y`/`z` in the bone's own axes. At most one of each kind | `translate`, `location`, `rotation` as an argument |
| Also apply to the other side | `symmetry`, a bool: call-level in `mpfb_set_targets`, per entry in `mpfb_set_pose_bones` - one concept, one spelling | `mirror` |
| A Rigify switch, addressed | `body_part` and `switch` (Rigify's property name, as `mpfb_get_pose_controls` lists it); its value `value`; `raw: true` to skip the snap | the bone it lives on, which is reported and never asked for - which is why a compact switch entry drops it |
| Which switches to list, by name | `switch_names` (`mpfb_get_pose_controls` only, [FR 044](../feature-requests/done/044-switches-filter/README.md)), echoed sorted as `requested_switch_names`, counted by `counts_by_switch` under every switch name the rig has. Its vocabulary is the rig's own, not this package's: `human_toes` has `parent_switch` and `game_engine` does not | `switches`, which is `mpfb_set_pose_switches`' list of objects and the key of the answer - one name, one JSON type, as with `include_switches` |
| Whether a write kept the limb where it was, and how well | `snapped`, with `snap_reason` when false, and `snap_error` (metres) when true | |
| Whether a write ended where it was sent | `achieved`, with `deviation` when false and `achieved_measure` saying how it was measured | |
| The arguments that undo what a tool did | `restore_with`, keyed by the tool to call (`apply_with` is the save's: the call that makes something durable). Two users: `mpfb_reset_pose` and `mpfb_place_character` | `undo` |
| Also do or list the optional part | `include_<part>`: `include_switches` (a reset) - FR 042 named it `switches`, which `mpfb_set_pose_switches` already takes as a list, and one name carries one JSON type; `include_hidden` (`mpfb_get_pose_controls`, FR 043) | `switches` as a bool, `show_hidden` |
| A rig a writer cannot act on | `blocked_by: "rig_in_edit_mode"` / `"rig_has_no_switches"` (only a generated Rigify rig has them) / `"rig_not_classified"` (a reset by body part on a rig with none) | |
| The character has no rig to pose / only a Rigify meta-rig / a body part that is not one / a role that is not one / a switch name the rig has nowhere | `blocked_by: "rig_not_found"` / `"rigify_not_generated"` / `"unknown_body_parts"`, with `known_body_parts` / `"unknown_roles"`, with `known_roles`, refused after `unknown_body_parts` / `"unknown_switch_names"`, with `known_switch_names` (every switch name the rig has, sorted), refused after `unknown_roles` and only on a rig that has switches; a name the rig has outside the requested parts is not a mistake and counts 0 | `no_rig`, `no_armature_found` (which `mpfb_generate_rigify_rig` keeps for a different question: no armature at all among the relatives) |

Where MPFB's own spelling disagrees with a row here, the row wins;
[mpfb-integration.md](mpfb-integration.md#where-mpfbs-spelling-disagrees-with-the-glossary-the-glossary-wins)
says why, and which of MPFB's spellings are kept.

### Words in descriptions and specifications

- **subject**: what the caller named, or the active object when they named nothing.
- **character**: the family of objects a subject belongs to. "Human" survives in tool names, which
  are not renamed, and in MPFB's `is_human_project`.
- **basemesh**: the body object at the root of a character.
- **phenotype**: the eleven sliders — gender, age, muscle, weight, height, proportions, cup size,
  firmness and the three race weights — that MPFB calls **macro details**, which is why the tools
  that read and write them are `mpfb_get_macro_details` and `mpfb_set_macro_details` and the key is
  `macro_details`.
- **modeling targets**: everything below the phenotype that shapes the body. A **target** is one
  morph, a `.target` file and the shape key it becomes; a **modifier** is a per-category slider
  that drives one target or a pair of opposites. These are `mpfb_set_targets`' two arguments. Not
  "detail targets" or "detail morphs": "detail" collides with macro details.
- **rig**, in a posing tool: the armature the basemesh's armature modifier points at, so a
  character carrying a meta-rig and the rig generated from it is answered about the one that moves
  the body. A **control** is a bone of it an animator would grab; `DEF-`, `MCH-` and `ORG-` bones
  are not controls.
- **character frame**: `forward`, `left` (the character's own, the `.L` side) and `up`, taken from
  the rig object and not from the pose; see
  [responses.md](responses.md#a-position-on-a-character-is-in-the-character-frame).
- **copy**, **export copy**: a character duplicated by `mpfb_create_export_copy` - every object in
  the family, under the `suffix` - and processed for another application. It is a character of its
  own, which every other tool treats as one; the **original** is the character it was made from,
  which the copy never changes. Not "duplicate", which is Blender's word for one object.
- **export**: one file `mpfb_export_character` writes, holding one character.
- **mesh asset**: anything equipped on a character from an MHCLO file, which is one of three kinds:
  a **garment** (MPFB's `Clothes` type), a **body part** (eyes, eyebrows, eyelashes, hair, teeth,
  tongue) or the **body proxy** (`Proxymeshes`). "Clothes" appears only where MPFB's own word is
  quoted: the type, `load_clothes`, and `override_clothes_material_type`, whose MPFB setting covers
  every body part but the eyes as well as garments.

### Kept on purpose

Each of these looks like a divergence and is not:

- **`bake_shapekeys`**: MPFB's panel's option, kept whole. "Shapekey" is one word here as in
  `shapekey_name`, which is MPFB's spelling too; the answer keys say `shape_keys_baked` and
  `shape_keys_loaded`, Blender's two words, because they report what is on the mesh.
- **`refresh`** always means "bypass a cache this tool reads"; which cache, and what it costs, is
  per tool and is said in each description.
- **`path` / `fragment` / `identifier`** are different identifiers for different things
  ([above](#how-tools-name-things-that-can-be-added)).
- **`shapekey_name` beside `name`** in the target tools, because the two differ above 60 characters.
- **`refit` defaulting to true** in `mpfb_set_face_units` and `mpfb_apply_expressions`, where
  composing is normally one call.
- **`weight` as a macro slider** in `mpfb_create_human` and `mpfb_set_macro_details`: it is one of
  MPFB's eleven names, and a number input like the other ten.
- **`macro_target_stack[].weight`** in `mpfb_get_macro_details`: what MPFB *computed* a macro
  target's shape key should hold, which `macro_drift` compares with the value read off the key. One
  name for both would hide which side a number came from.
- **`previous_weight`** beside an expression row's `weight`: the per-entry before-and-after form,
  with the field's own name.
- **`source_value`, `destination_value_before` / `_after`** in `mpfb_symmetrize_targets`: an entry
  has two sides, and the side is part of the name.
- **`live`, `from_stack`, `now`** in `discarded_face_units`: one face unit read three times, named
  by where each reading came from.
- **`loaded_from`** (a path, per target) and **`loaded_from_disk`** (the face units that had to be
  loaded): two concepts with two shapes.
- **`requested`** in `mpfb_apply_expressions` (per-entry outcomes) and in the preset tool's
  `overrides` records (a value): both are what the caller asked for.
- **`requested_name`** in `mpfb_remove_asset`: the echo of a required asset `name`, which is never
  the active object and so is not a `subject_name`.
- **`kind`** in `equipped_assets` records: the preset file's own keys, not MPFB's object types.
- **`allowed_material_types`** in `mpfb_add_asset`: the subset for this asset's type, not the whole
  vocabulary a `known_` key would list.
- **`settings_used`** and **`contents`**: MPFB's own dicts, reported in MPFB's spelling.
- **Socket names are MPFB's data and pass through verbatim**, as a shape key name does, including
  `AurolaeOverride` beside `AureolaeColor` on the layered skin's colour group - MPFB's spelling, not
  a typo here to correct. The glossary does not rename data
  ([names inside MPFB's node trees are read live](mpfb-integration.md#names-inside-mpfbs-node-trees-are-read-live-never-tabulated)).
- **`settings`** in `mpfb_get_material_settings`: a node's values keyed as the preset keys them,
  which is MPFB's `get_socket_default_values()` dict as it is.
- **`applies`** and a bare **`reason`** on a material settings section or colour adjustment
  record: whether the preset saves anything for it, and why not.
- **`<x>_reason`** keys, and a bare `reason` inside a per-entry record, which always means "why this
  entry was not done".
- **`head`** as a body part and as the key holding a bone's head position in the posing tools:
  the first is this package's vocabulary, the second is Blender's own name for the point a bone
  rotates about, which is what FR 042's `move_to` takes. One is a value, the other a key, and
  renaming Blender's term would cost every reader who knows it.
- **`switches`** in `mpfb_get_pose_controls` and **`switch_values`** / **`switch_parents`** in
  `mpfb_get_pose`: the first is a list of definitions (range, ends, parent names), the others are
  the current values as maps keyed by body part and switch, read after every pose change. One name
  for both would carry two shapes.
- **`value` in a `mpfb_set_pose_switches` entry is a number or a bool**, because the switches are:
  `pole_vector` is on or off and the rest are numbers. It is inside an entry, not an argument, and
  the rule that an argument name carries one JSON type is about arguments.
- **`head_before`/`head_after`, `rotation_before`/`rotation_after`, `scale_before`/`scale_after`**
  in a pose change: the whole-field form, since each is an object rather than a value.
- **Tool names.** A renamed tool breaks every client configuration and saved transcript, which a
  renamed key does not.
