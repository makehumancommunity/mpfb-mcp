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
- **Surprising facts are instruction, and they stay in full.** That `asset_type` is required
  because MPFB's own default mislabels six of eight types, that `skin_type` follows the settings
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

**A vocabulary this package defines is not an exception at all.** `mpfb_apply_expressions`' `mode`
(`"merge"` or `"replace"`) is checked locally, and
[FR 027](../feature-requests/done/027-expression-library/README.md) planned it as a third case of
the exception above - but no MPFB function ever receives it. It selects between two ways the command
builds the stack, so it cannot drift from anything MPFB or the user's disk holds, and the reason not
to validate a vocabulary here does not apply to it. It is a shape, checked on both sides like any
other: locally, and in the command's parameter contract (`choices`), which the dispatcher enforces
before the handler runs.

**An argument that becomes a path is a shape, not a vocabulary, and it is checked here.**
`mpfb_save_preset` and `mpfb_create_human_from_preset` take a preset `name` that resolves to
`human.<name>.json` in MPFB's user config directory, and `mpfb_save_expression` takes an expression
`name` that resolves to `<name>.json` in the expressions directory of MPFB's user data - one rule
for both, in `mpfbmcp.artifact_names`, with the noun in the refusal as its only argument; and a name carrying `/`, `\` or `..` would
address — and on the saving side *write* — a file outside it. Which characters may appear in a
filename cannot drift from anything on the user's disk, so this is the ordinary rule rather than an
exception to it, and it is deliberately stricter than MPFB's own panel (which rejects only an empty
name and one containing a space; the expression composer's save operator rejects only a path
separator, `.` and `..`). Strictness runs one way only: every name accepted must be one
MPFB would also accept, so the two never disagree about what exists — and where the reverse fails,
the catalogue tool flags it (`mpfb_list_presets`' `addressable`) rather than letting a caller meet
it as a refusal. The rule is also restated on the add-on side, as the last statement before
`open()`, because a listening socket is reachable by anything on the machine; the two
implementations are run over one table of names, as both nouns, by `tests/test_save_preset.py` so
they cannot drift. What that buys is in
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
  quality attribute as `mpfb_list_objects`' `type_recognized`: an agent that reads a short list as
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
  is always in the response, beside a `resolved_by` saying which identifier was used. This is the
  acting-tool counterpart of `mpfb_list_assets`' `pack_ambiguous`: the derivation is unsafe in a
  minority of cases, and the caller cannot tell which case they are in unless the tool says.
- **An identifier hiding as a description is still an identifier.** `add_mhclo_asset()`'s
  `asset_type` takes exactly the `object_type` the catalogue reports, and defaults to `"Clothes"` —
  so hair added without it *becomes* clothes, permanently and silently. Where a defaulted argument
  changes what the character *is*, the tool requires it rather than inheriting the default, and says
  in its docstring that it diverges from MPFB's own signature for that reason.
- **Where what the tool writes *is* one of the identifiers, it takes that one only.**
  `mpfb_apply_expressions` takes `fragment` and not `path`, although `mpfb_list_expressions` reports
  both. The tool does not load a file; it writes a stack row, and a stack row is a fragment. A path
  would have to be converted back, and MPFB's own conversion
  (`_compute_expression_library_relative_path()`) returns the bare basename for a file outside
  every root - a row that would then resolve to some other file, or to none, on the next rebuild.
  Taking the path would make the tool accept something it cannot store faithfully. The resolution
  is still reported (`resolved_path` beside `listed_path`, per row), for the reason the clause
  above gives.
