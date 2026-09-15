# History of completed efforts

A running log of development efforts that have **landed**. It is the finished counterpart to
[NEXT_STEPS.md](NEXT_STEPS.md), which tracks only the remaining/active work. When an effort is
completed its entry moves here (see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

Entries are ordered by feature-request number. Each notes what was actually built; the
individual `NNN-*/README.md` subdirs remain the authoritative record of what was planned and
decided, and the standing [specifications/](../specifications/) remain the source of truth for
current behavior.

The initial `mpfb_create_human` proof of concept predates this feature-request process and
has no numbered entry here or in `done/`; see [CLAUDE.md](../CLAUDE.md) for what it covers.

## [FR 001](done/001-mpfb-get-status/README.md) — `mpfb_get_status`

Landed the first introspection tool: `mpfb_get_status`, which takes no arguments and always
answers, classifying the connected Blender's MPFB install as `absent`, `not_initialized`
(loaded but `register()` never completed) or `ok`, and — when `ok` — reporting version, build
info, install path, configured paths, the data roots MPFB will actually search, installed asset
packs, Rigify availability and Blender version/platform/compatibility.

Beyond the tool itself, the effort split `mpfb_codegen.py`'s `sys.modules` scan out of the
raising bootstrap into a shared helper with two variants built on it — one that raises when MPFB
is unusable, one that classifies instead — and established two rules now recorded in
[architecture.md](../specifications/architecture.md#resolving-mpfb-from-generated-code):
resolving MPFB is two steps rather than one, and generated code must never reach a service by
importing an MPFB submodule, because some of them have import-time side effects.

**Landed without the manual verification pass its own Tests section calls for.** Live testing
against a running Blender was explicitly out of scope for the implementation, so the documented
field values rest on reading MPFB's source rather than on observation; unit tests cover the
generated code's branching by executing it against a stubbed `bpy` and stubbed `sys.modules`
entries. The outstanding checks are listed under "Verification status" in
[the request itself](done/001-mpfb-get-status/README.md#verification-status).

## [FR 002](done/002-codegen-structure/README.md) — code generation restructured into per-tool payload files

Replaced the single, central `mpfb_codegen.py` with a `src/mpfbmcp/codegen/` package: the shared
MPFB bootstrap in `bootstrap.py` (moved across byte-for-byte, so FR 001's decisions are untouched),
and one ordinary `.py` payload file per tool under `payloads/`. A payload is now editable as normal
Python — no escaped newlines, no doubled braces, no `.format()` placeholders — because nothing is
substituted into it: parameters arrive as data, through a prelude that binds `PARAMS` from a JSON
literal, which also means a caller-supplied string can never alter the structure of a program the
system is about to `exec()`. Payload files are deliberately not importable (no `__init__.py`; read
as package resources) and are declared as package data so a non-editable install still ships them.

Adding a tool now touches only a tool module, a payload file, and one `register()` call — no shared
code-generation module. Two standing rules were recorded in
[architecture.md](../specifications/architecture.md#readability-and-developer-experience-are-prioritized):
readability and developer experience are prioritized non-functional requirements, generated code
included; and the
[code-generation layout](../specifications/architecture.md#code-generation-layout) new tools follow.

A behavior-preserving refactor: no tool signature, docstring or response envelope changed, and a
characterization diff against the pre-refactor output confirmed the only differences are the
prelude, the seam comment, the payload docstrings and `create_human`'s inlined literals becoming
`PARAMS` lookups. **Landed without the real-Blender smoke pass its own Tests section calls for**
— out of scope for the implementation, and recorded under "Verification status" in
[the request itself](done/002-codegen-structure/README.md#verification-status). The
installed-package check that requirement 6 asks for *was* run, since it needs no Blender, and
turned up something the request had not anticipated: package data alone is not enough, because
setuptools' package discovery treats a directory without an `__init__.py` as a namespace package
by default and ships its files as modules. Both halves are now set in `pyproject.toml` and stated
in the spec.

## [FR 003](done/003-object-finding/README.md) — object finding and identification

Landed the layer every later tool needs in order to name its subject: `mpfb_list_objects`, which
names the MakeHuman objects in the current scene and optionally filters them by MPFB object type,
and `mpfb_get_object_info`, which identifies one object — named, or simply the one that is active —
reports what asset it was made from, and lists what else belongs with it. Both are read-only and
touch none of `ObjectService`'s destructive or selection-mutating methods; in particular nothing is
selected or activated in order to be inspected.

Two things kept an empty or absent answer from being ambiguous, which was the request's stated
quality attribute throughout. `mpfb_list_objects` reports `type_recognized` and MPFB's full
`known_types` beside the list, so "no basemeshes here" and "you asked for `Basemseh`" are different
answers, and a caller can correct itself from the same response. `mpfb_get_object_info` treats an
unresolvable subject as a successful answer rather than an error, the same stance
[FR 001](done/001-mpfb-get-status/README.md) took for a missing MPFB. The type vocabulary is read
out of MPFB rather than duplicated here, since a list copied into mpfb-mcp drifts silently and this
one is guidance an agent acts on.

Three standing conventions were recorded in
[architecture.md](../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish):
reading module-level names MPFB does not publish — now covering non-`SERVICES` *entities* such as
`GeneralObjectProperties`, not only constants — via `sys.modules[Service.__module__]`, never a
fresh import, always with a fallback;
[how generated code addresses objects](../specifications/tool-interface.md#how-generated-code-addresses-objects),
by Blender object name, listing scoped to the scene while resolution is scoped to the file, with
"exists elsewhere" a distinct answer; and
[how tools report the asset behind an object](../specifications/responses.md#how-tools-report-the-asset-behind-an-object),
the fragment-plus-absolute-path pairing and the type-varying rather than unioned shape.
[Validate before crossing the socket](../specifications/tool-interface.md#validate-before-crossing-the-socket)
gained the distinction this effort turned on: validate a string argument's *shape* locally, never
its *vocabulary*.

Reading MPFB's source closely to write the payloads turned up several places where the request had
the API wrong, all corrected in the request text: there is no `HumanService.set_skin()` (it is
`set_character_skin()`); `get_object_type()` returns `""` rather than `None`, and
`object_is_any_makehuman_object()` and `object_is_generated_rigify_rig()` return strings rather
than bools, so the response has to coerce; `identify_rig()`'s vocabulary is nearly twice as long as
listed, and never returns `None`; and the `pathlib.Path` of commit `631989c` comes specifically
from `get_mpfb_root()`. The consequential one was scope creep in the opposite direction from
expected: the request anticipated only Rigify's pairing helpers reaching outside the current scene,
but `ObjectService.get_list_of_children()` walks `bpy.data.objects` too, and *every* relative is
found through it. Rather than filter those out — which would silently drop a real relationship —
every `related_objects` and `other_related_objects` entry carries its own `in_current_scene`, which
is the remedy the request had already named for the narrower case.

Adding the two tools touched no shared code-generation module, as
[the layout](../specifications/architecture.md#code-generation-layout) requires: two tool modules,
two payload files, and two `register()` calls. The only shared edits were to `tests/test_codegen.py`,
which hardcodes the payload list twice. Unit tests grew from 32 to 82, over a shared
`tests/blender_stubs.py` that reimplements the MPFB behaviors above rather than returning
convenient values — the stubs are the reason those API corrections surfaced as test failures rather
than as live surprises. Landed without the live verification its own Tests section calls for, which
for this effort was a larger gap than for FR 001 or FR 002: every `asset_info` value comes from an
MPFB property or helper whose real content the stubs assert nothing about.

**That verification has since been run** against Blender 5.1.0 with MPFB 2.0.17 and 108 asset
packs, on a scene holding two rigged, dressed characters. Every `asset_info` value the stubs could
not vouch for checked out against real MPFB — every resolved path exists on disk, and all 31
objects in the file survive `strict_json`. It found one defect: `rigify_role` was reported for an
untyped *relative* but never for the *subject*, so an agent that followed a name out of
`other_related_objects` got less back than the entry that sent it there, under a `message` calling
a Rigify rig "a plain Blender object". Fixed, with regression coverage in `SubjectRigifyRoleTests`;
unit tests grew to 89. The run also corrected a premise this request, the tool docstring and the
stubs all shared — MPFB *does* tag the rig it generates through Rigify, as a `Skeleton` — which is
why the fix reports `rigify_role` whatever the object's type. Details, including a checklist item
that was itself wrong rather than the code, are under "Verification status" in
[the request itself](done/003-object-finding/README.md#verification-status).

## [FR 004](done/004-list-rigs/README.md) — `mpfb_list_rigs`

Landed the first of the three "finding available assets" efforts: `mpfb_list_rigs`, which takes no
required arguments and always answers, listing every rig this Blender could add to a basemesh —
MPFB's bundled standard and Rigify rigs, enumerated from the directories rather than hardcoded, plus
the custom rigs `AssetService.get_custom_rigs()` finds in the user data roots.

Its reason to exist is the `identifier` field. A rig's bare name is not what an adding function
takes (`human` is added as `rigify.human`, `my_rig` as `custom.my_rig`), and the two functions that
take them are not interchangeable — hence `add_function` beside it. Each entry also reports what
adding it would do about weights, resolved by mirroring `add_builtin_rig()`'s walk of
`RigService.get_rig_weight_fallbacks()` rather than by testing for `weights.<name>.json`: two of
MPFB's rigs ship no weights file of their own and are not unweighted. Absence is made explainable
through `rigify_available`, the directories actually scanned, and the files `get_custom_rigs()`
silently refused.

The convention behind all of that is now standing, as
[How tools name things that can be added](../specifications/tool-interface.md#how-tools-name-things-that-can-be-added)
— the catalogue counterpart to FR 003's rules for naming an object, which FR 005 and FR 006 inherit.

Three files added and three shared ones touched, as
[the layout](../specifications/architecture.md#code-generation-layout) requires. Unit tests grew
from 89 to 129, over stubs extended to carry MPFB's real weights fallback table and the
`pathlib.Path`/`str` split in `get_mpfb_root()`.

**Live verification was run as part of the effort**, not deferred. Every one of the 13 identifiers
the tool reported was actually added to a scratch basemesh through the function the entry named, and
every one produced a parented, weighted armature; the scene compares identical before and after and
the `.blend` was never saved. It confirmed a defect that had been caught during planning rather than
in the field: the request's set difference for `unrecognized_custom_rig_files` reports the
`weights.*.json` companion of every custom rig, on every install that has one. It also turned up a
sharper justification for `add_function` than the request had — `add_custom_rig()` strips seven
characters from whatever it is given, so a built-in name comes back missing under a name that never
existed. Details, and three smaller corrections to the request, are under "Verification status" in
[the request itself](done/004-list-rigs/README.md#verification-status).

## [FR 005](done/005-list-assets/README.md) — `mpfb_list_assets`

Landed the second of the three "finding available assets" efforts, and the answer to the question
FR 003 left inverted: not "what is this object made from" but "what could I put on this character".
One tool listing the assets installed under every subdir in MPFB's own `ASSET_LIBRARY_SECTIONS` —
proxymeshes, skins, ink layers, eyes, eyebrows, eyelashes, hair, teeth, tongue, clothes and poses —
filtered by subdir, by a substring of the name or label, and by asset pack, with the filters
combining and every argument optional.

It is a *filtering* tool rather than a listing one because the library does not fit: the install it
was verified against holds 730 assets, and an unfiltered listing is not something an agent can
afford to read. So the answer is capped, paged and deterministically ordered, and reports
`total_count` and an always-present `truncated` beside `counts_by_subdir`, which is what turns an
over-broad call from merely truncated into a map of where to look next. That is now standing as
[How tools bound a large answer](../specifications/responses.md#how-tools-bound-a-large-answer),
the convention [FR 006](done/006-list-targets/README.md) inherits.

Each entry names the asset three ways, and the live pass sharpened what each is for: `path` is what
`add_mhclo_asset()` and `set_character_skin()` actually take, `fragment` is the portable identifier
MPFB writes onto the resulting object as `asset_source` — confirmed string-equal for every asset
added — and `object_type` doubles as `add_mhclo_asset()`'s `asset_type` argument, which defaults to
`"Clothes"` and so silently turns hair into clothes when omitted. FR 004's
[naming convention](../specifications/tool-interface.md#how-tools-name-things-that-can-be-added) grew
a clause for that.

`pack` is the project's first *derived* field: MPFB records no link from an installed file back to
the pack that installed it, so the attribution is a match of the asset's containing directory name
against the installed packs' metadata. That earned the second new convention,
[How tools report a derived rather than recorded fact](../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact),
and the live numbers are why: 9% of this install's assets are claimed by more than one pack, so
`pack_ambiguous` is ordinary rather than rare, and the packs' own `type` metadata cannot break the
tie.

Three files added and four shared ones touched. Unit tests grew from 129 to 165, over stubs that
now reproduce `get_asset_list()`'s item building quirk for quirk — keyed by label, with a `thumb`
value JSON cannot encode — so the cache's under-reporting is pinned by a test rather than only
described.

**Live verification was run as part of the effort.** Assets the tool reported were applied to a
scratch basemesh through both adding functions and then removed, with all nine datablock
collections comparing identical before and after and the `.blend` never saved. It corrected four
things the request had assumed: the pack filter had to match *any* claiming pack, or an installed
asset in two packs is reported absent; an asset lying directly in an asset root has no directory
name to attribute by and must come back `pack: null`; `fragment` is not what the adding functions
take; and `refresh` is far cheaper than feared — 0.015 s, since previews already loaded are not
loaded again. Details are under "Verification status" in
[the request itself](done/005-list-assets/README.md#verification-status).

## [FR 006](done/006-list-targets/README.md) — `mpfb_list_targets`

Landed the last of the three "finding available assets" efforts, and the catalogue a later
`mpfb_set_target_value` has to be able to read: an agent asked to widen a nose had no way to find
out what the morph is called, or whether the name it guessed exists.

Two sources, answered differently, which is what makes this more than a directory listing. The
bundled targets are indexed by a ~140 KB `target.json` that no response should carry, so the tool
reports its *path* — the cheapest possible answer when the client shares a filesystem with Blender —
and lets a caller page through one section's categories at a time, `opposites` table included. The
user data directories have no index at all and are scanned per call.

The field the whole tool exists for is `shapekey_name`. A target is addressed by the name of the
shape key it becomes, derived from the filename by `TargetService.filename_to_shapekey_name()`, and
that derivation is not the identity function: above 60 characters MPFB *encodes* the name to fit
Blender's limit. The live pass pinned this end to end — a 76-character target loaded as
`$yn-$fe-$av-$ca-$un-$pr-$wg-$hg-experiment`, that name read back the value that had been set, and
the same target addressed by its **filename** read back `0.0`. Silently. That failure is why the
identifier is its own field, and it sharpened
[How tools name things that can be added](../specifications/tool-interface.md#how-tools-name-things-that-can-be-added)
with a clause about identifiers that usually equal something the caller already has.

The one thing the request had wrong was sections. It assumed a section is either a `target.json` one
or a synthesized user one; on the verification install **8 of 27 are both**, and MPFB's own panel
merges a user directory into the bundled section of the same name rather than keeping the two apart.
So `source` took a third value, `"both"`, and asking for such a section returns its bundled
categories *and* that directory's user targets.

Two conventions were folded back, both new:
[Reading MPFB's data files directly](../specifications/mpfb-integration.md#reading-mpfbs-data-files-directly)
— locate through `LocationService`, guard the read, treat a missing file as an answer, and report
where a large file is rather than what is in it — and
[A tool may report a fact MPFB's own UI does not show](../specifications/responses.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show),
which this tool does twice over: it scans per call, so it sees a target installed since Blender
started that MPFB's import-time snapshot cannot, and it reports a `*.target.gz` in a user targets
directory that MPFB's `*.target`-only scan there does not match. Both are real, both were observed
rather than inferred, and both are in the docstring, because the user will otherwise read the
discrepancy as the tool being wrong.

Three files added and four shared ones touched. Unit tests grew from 165 to 208, over a real
temporary target tree — the payload's job is `os.walk()` and `os.listdir()`, so mocking the
filesystem away would leave nothing under test — plus a new `StubTargetService` reproducing MPFB's
name encoding rather than only its extension stripping.

**Live verification was run as part of the effort**, against 221 user targets across 27 sections.
Targets the tool reported were loaded onto a scratch basemesh and their values set and read back,
and a gzipped target was briefly written into a user targets directory to observe the scan
asymmetry rather than infer it from the code. Everything was then removed: all twelve datablock
collections compare identical before and after, the active object was restored, and the `.blend` was
never saved. No code changed as a result of the live pass. Details are under "Verification status"
in [the request itself](done/006-list-targets/README.md#verification-status).

## [FR 007](done/007-macro-details/README.md) — macro details, refit, and the first mutating tools

Three tools: `mpfb_get_macro_details` reads a character's eleven phenotype sliders,
`mpfb_set_macro_details` changes any subset of them and rebuilds the shape, and `mpfb_refit_human`
puts the character's clothes and rig back in fit afterwards. Before them a character was frozen at
creation: "make her a bit older" meant deleting it and building a new one, losing every asset, rig
and detail target on it.

**Live verification is outstanding, and this entry is flagged rather than finished in the way
[FR 004](done/004-list-rigs/README.md) through [FR 006](done/006-list-targets/README.md) were.**
Those each landed with a run against a real Blender behind them; this one was scoped without it.
The gap matters here more than it would have for a read-only tool, because the request's first
non-functional requirement — that a character modified through this tool ends up with the same
shape keys at the same weights as one modified through MPFB's own phenotype panel — is exactly the
claim that cannot be established from this side of the socket. The unit tests cover the branching
around that call and nothing about the call's result. The checklist is under
["Verification status" in the request](done/007-macro-details/README.md#verification-status).

The interesting part is not reading or writing the properties, which is trivial, but that writing
one does nothing: the visible shape is a stack of macro *targets* MPFB recomputes from all eleven
values together. So the payload writes every named property and then calls
`TargetService.reapply_macro_details()` **once** — MPFB's own interpolation, never a
reimplementation of it, since the corner-case naming and the encoded `$md-` names are MPFB's
business and would drift the moment MPFB changed them. Deliberately not `reapply_all_details()`,
which also reloads the *detail* stack from disk through a prefix-matching path lookup that can
silently load a different target.

Three conventions were folded into
[architecture.md](../specifications/architecture.md), all new and all about mutation rather than
reading:
[how a mutating tool takes its subject](../specifications/mutating-tools.md#how-a-mutating-tool-takes-its-subject)
— it accepts any object in the character's family and names the one it actually modified, because
an agent that got a name out of `mpfb_list_objects` has no way to know which member owns a given
property;
[a mutating tool reports before and after](../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after)
— the mutation-side counterpart of "an empty answer must never be ambiguous", covering the prior
values, the shape keys pruning removed, and what is now fitted to the old shape; and
[preconditions are answers](../specifications/mutating-tools.md#preconditions-are-answers) — edit
mode and a mesh with no shape keys are ordinary situations, and MPFB meets the first with a bare
`assert` and the second with a log line saying it is "somewhat surprising".

A fourth clause settles a question `NEXT_STEPS.md` had carried since the start: whether
`mpfb_create_human` should take a macro-detail dict instead of eleven flat sliders. **It should
not**, and the reasoning is general enough to sit under
[Validate before crossing the socket](../specifications/tool-interface.md#validate-before-crossing-the-socket)
rather than in the request: a flat scalar is what an MCP schema validates and a client fills in
reliably, and only flat arguments can express "leave this one alone". Round-tripping is preserved
on the output side, where both macro tools return MPFB's nested dict.

Two premises of the request were corrected by reading MPFB's source while implementing. The refit
default rests on `mpfb_refit_human` existing, and the case that tool exists for is a generated
Rigify rig with no meta rig in the scene, which `HumanService.refit()` reports only through an
`operator` an MCP tool cannot give it — but it does *not* "return having refitted nothing", as the
request assumed: the mesh assets are refitted first and only the rig is skipped. So the tools
detect the condition, still call `refit()`, and report `refit_performed: false` with a
`refit_incomplete_reason` naming the rig, rather than refusing the call and leaving the garments
stale as well. The other correction is smaller: MPFB stores the race weights as plain
`asian`/`caucasian`/`african` properties, while the arguments keep `mpfb_create_human`'s
`race_`-prefixed names, so the mapping is explicit in the tool module.

Six files added and six shared ones touched. Unit tests grew from 208 to 278, over stubs extended
with the macro half of `TargetService` — an unclamped property store (matching a real property
whose definition carries a default but no min/max, which is why the range check lives in the tool
module), a `reapply_macro_details()` that really adds and removes shape keys including the
sub-0.0001 prune, and a `create_shape_key()` carrying MPFB's own OBJECT-mode assert. The one
deliberate departure is the macro interpolation itself, which is a stand-in table rather than
MPFB's corner cases: no payload depends on which targets come out, only on the shape of the answer.

## [FR 008](done/008-detail-targets/README.md) — detail targets, and the batched mutating tool

Three tools: `mpfb_get_target_stack` reads the modeling morphs on a character,
`mpfb_set_targets` changes them in batches, and `mpfb_symmetrize_targets` repairs a stack that has
drifted asymmetric. Before them mpfb-mcp could create a character, describe it, and list the
thousand-odd morphs that could be applied to it — and apply none of them. Everything below the
phenotype level, which is where a character stops being a mannequin, was unreachable.

The shape of the setter is the interesting part, and it is dictated by what a modeling slider
actually is. It is not "set shape key X to value Y": a slider corresponds to a `target.json`
**category**, a modifier running from -1.0 to +1.0 built from a *pair* of opposing targets, where
the sign selects which of the two is loaded and the other is driven to zero — and 66 of the 203
bundled categories additionally have separate `l-` and `r-` variants, giving four target files
behind one conceptual control. Shape keys cannot express that, because Blender clamps a shape key
value to 0.0-1.0, so "flaring -0.4" has no representation except "flaring-decr at 0.4, flaring-incr
at 0.0". A tool built the naive way would produce characters MPFB's own UI cannot represent. So the
tools work at **two levels**: the category level, which is what an agent should normally use, and
the raw shape-key level, which is the only way to reach a user-installed target and which takes the
`shapekey_name` [FR 006](done/006-list-targets/README.md) exists to report. That pairing —
which reported identifier feeds which level — is the whole contract between the catalogue and the
setter, and it is now written down in both.

Two conventions were folded into
[architecture.md](../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes),
both new.
[A batched mutating tool resolves before it writes](../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes):
a batch of thirty changes with one typo in it applies **zero** of them, because a half-applied batch
leaves a character in a state neither the agent nor the user can describe and the response format
cannot usefully say which half landed. Batching itself is not a preference — a socket round trip
costs about a second while setting a target costs milliseconds — and the convention names
[FR 010](done/010-mesh-assets/README.md) as the case where that argument does *not* carry over, since
loading an MHCLO is seconds of real work.
[When mpfb-mcp models a concept MPFB's UI has but its services do not](../specifications/mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not):
a modifier is not a `TargetService` idea at all, it lives in `target.json` and in a UI module, and
when a tool lifts one out of the UI the mechanics are reproduced statement for statement rather than
reinvented — `_set_opposed_modifier_value()` zeroes the opposing target *first*, and doing it the
other way deletes the wrong half of a pair when pruning is on.

Two existing conventions were amended.
[Validate before crossing the socket](../specifications/tool-interface.md#validate-before-crossing-the-socket)
gained the one exception to its "flat scalars, not a nested dict" clause: a batch is irreducibly a
list, and what compensates for a shape no schema checks is per-entry validation in the tool module —
including rejecting an unknown key, which is the commonest way a caller gets a dict-shaped argument
wrong and is otherwise silent — plus a per-entry `resolution_errors` channel in the response.
[A tool may report a fact MPFB's own UI does not show](../specifications/responses.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show)
gained a third and sharper case: `TargetService.get_target_stack()` excludes any shape key whose
name *contains* `"basis"`, not merely equals it, so a user target called `basis-nose-widen` is on
the mesh, is deforming it, and is invisible to every read and write MPFB can perform.
`mpfb_get_target_stack` reads `key_blocks` directly rather than inheriting the blind spot, and
flags what it finds; every *write* still goes through `TargetService`, or the two halves of the same
tool would disagree about what exists.

The effort also changed `codegen/` for the first time since
[FR 002](done/002-codegen-structure/README.md) — deliberately, and against the request's own
recommendation. FR 008 was written expecting *two* payloads to need MPFB's category table and
concluded that duplicating the scan was the safer first move. It is three, and three copies of a
hundred-line scan of the user's target directories are three chances for two mpfb-mcp tools to
disagree about what is installed, which is the very inconsistency the request rejects elsewhere. So
`assemble()` grew an optional `shared=[...]`, the table lives in
`codegen/shared/target_categories.py`, and
[Shared fragments](../specifications/architecture.md#shared-fragments) records when one is
warranted. FR 002's objective test still holds and was kept as the test of the design: adding an
ordinary tool is still a tool module, a payload and a `register()` call, and a tool that wants a
fragment names it in the `assemble()` call it was already making. `mpfb_list_targets` was
deliberately not migrated onto it — it is live-verified and its scan has a different shape — and
that migration is listed in [NEXT_STEPS.md](NEXT_STEPS.md).

Reading MPFB's source closely turned up four things the request did not know. A **gzipped custom
target is named two different ways**: MPFB's category name is a substring replace that does not
strip `.gz`, so `vwide.target.gz` becomes `vwide.gz`, while the catalogue reports `vwide` — the two
address different shape keys for the same file. The tools write MPFB's name at the category level,
because the point of that level is that the value reads back on MPFB's own slider, and report the
divergence; it is a candidate mpfb2 issue. Every bundled category **without** `opposites` is
unsided and every sided one carries all four `l-`/`r-` entries, so `_set_simple_modifier_value()`'s
`l-`/`r-` prefixing is dead code on stock data. `measure` is a real section with zero categories.
And all 1258 bundled target files are `.target.gz`, which makes the two reference setters'
disagreement about the file extension a genuinely latent crash rather than a rare one.

Nine files added — three tool modules, three payloads, one shared fragment and three test modules —
and eight shared ones touched. Unit tests grew from 278 to 419, over stubs extended with the write
half of `TargetService`: a `set_target_value()` that is a silent no-op for an absent name, a
`get_target_value()` that returns `0.0` for one, a `has_target()` that checks the encoded name while
the writers do not, a `load_target()` that raises `IOError`, a `target_full_path()` with its
prefix fallback, and a shape key value clamped to 0.0-1.0 on assignment — each reproducing the
quirk a payload exists to work around, since a helpful stub would make the workaround look
unnecessary. The packaging half of the codegen change *was* verified, since it needs no Blender: a
real non-editable install ships all thirteen payloads and the fragment, which is the failure
FR 002's own verification pass caught.

**Live verification is outstanding, as it was for [FR 007](done/007-macro-details/README.md).** That
is now two consecutive mutating efforts landing that way, and the debt is compound rather than
isolated: the claim that cannot be established from this side of the socket — that a modifier set
through the tool produces the same result MPFB's own slider does — is the same *kind* of claim
FR 007 left open, and the session that would settle one would settle both. The checklist is under
["Verification status" in the request](done/008-detail-targets/README.md#verification-status), and
[NEXT_STEPS.md](NEXT_STEPS.md) now names that session as the largest piece of unfinished business
in the file.

## [FR 009](done/009-add-rig/README.md) — adding a rig, and the ordering constraint nothing enforces

Two tools. `mpfb_add_rig` attaches any rig [FR 004](done/004-list-rigs/README.md)'s catalogue names,
and `mpfb_generate_rigify_rig` turns a Rigify meta rig into a generated one. Before them mpfb-mcp
could name every rig in the install and attach none of them, so every character it produced was a
static mesh — the catalogue had been reporting an `identifier` and an `add_function` since FR 004
with nothing on the other end of either.

The interesting half is not the wrapping. MPFB's services have **implicit sequencing that produces
no error when it is violated**: `add_mhclo_asset()` rigs a garment only if a rig exists at the
moment the garment is attached, and nothing re-rigs it afterwards — `refit()` deliberately passes
`set_parent=False`. Rigify makes that three steps rather than two, since `add_builtin_rig()` on a
`rigify.*` identifier produces only a *meta rig* and generation has to run after the clothes. An
agent that dresses a character and then rigs it gets clothes that do not follow the armature and
finds out when someone moves a bone. No call can validate a sequence, so the standing rule recorded
in
[A tool reports an ordering constraint it cannot enforce](../specifications/mutating-tools.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
is that a tool which can *observe* the violation reports it, naming the objects — `mpfb_add_rig`
rigs a dressed character without complaint and returns `mesh_assets_not_rigged`. Splitting
generation out into its own tool rather than making it a flag is part of the same decision: the
correct order cannot be written as one call.

`codegen/` gained its second shared fragment, `rig_lookup.py`, and this time an existing payload was
migrated onto it — [FR 006](done/006-list-targets/README.md)'s `list_targets.py` was deliberately
left alone in the same situation, so the difference is worth stating. `mpfb_list_rigs` *predicts*,
per rig, which weights file adding it would load; `mpfb_add_rig` then does it and reports the
outcome. A caller who reads the catalogue and acts on it is entitled to get back what the catalogue
promised, and MPFB resolves weights through a *fallback table* rather than by filename, so two
implementations disagreeing would make an ordinary rig look broken in one tool and fine in the
other. The overlap is about ten lines: too small to justify a fragment on size, and not justifiable
as duplication on consequence. [Shared fragments](../specifications/architecture.md#shared-fragments)
now records that sharper rule, and one test asserts it directly by running both payloads against the
same rig tree and comparing their answers.

Three conventions were extended rather than added.
[How a mutating tool takes its subject](../specifications/mutating-tools.md#how-a-mutating-tool-takes-its-subject)
gained the case where the resolved object is *not* the basemesh — `mpfb_generate_rigify_rig`
narrows to the character's `Skeleton` — and the case where the whole set is needed rather than the
first match. [A mutating tool reports before and after](../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after)'s
"restore what was borrowed" gained its one honest exception: `generate_rigify_rig()`'s own final act
is to select and activate its result, so there is no state to restore to and the response says what
the selection now is.

Reading MPFB's source turned up four things the request did not know. `weights_from` is always a
**bare** name, so comparing it against the identifier reports `rigify.human_toes` as borrowing from
itself. `bpy.context.mode` has to be checked as well as the basemesh's, because building the
armature runs `bpy.ops` calls that poll on the context — an unrelated object in edit mode blocks a
basemesh that looks fine. `RigService.identify_rig()` can return `None`, not merely `"unknown"`,
which makes MPFB's own generate operator's `poll()` raise (a candidate mpfb2 issue). And after
generation the meta rig is **not a relative of the character at all** —
`adjust_children_for_rigify()` re-parents everything onto the generated rig — which is why "already
generated" is a distinct answer from "that is not a meta rig", and why the payload classifies every
skeleton relative rather than taking the first.

Four files added — two tool modules, two payloads — plus one shared fragment and two test modules,
with `list_rigs.py`, its tool module and its tests migrated onto the fragment. Unit tests grew from
419 to 492, over stubs extended with the rig half of `HumanService` and the write half of
`RigService`: adders that **raise** for an unknown rig with no operator, a missing weights file that
is reported through an operator and otherwise silent, an armature registered in the file *before*
the Rigify colour assertion so the stray it leaves behind is real, and a `generate_rigify_rig()`
that renames, deselects and activates before the validity gate so that "a failed generation is not a
no-op" is genuinely under test.

**Live verification is outstanding**, as for [FR 007](done/007-macro-details/README.md) and
[FR 008](done/008-detail-targets/README.md) — and this effort adds a new kind of debt to that
session: refactoring `list_rigs.py` onto the shared fragment means **FR 004's live verification is
stale**, since the program sent into Blender is a different program even though its behavior is
unchanged as far as the unit tests can see. The claim nothing on this side of the socket can
establish is the one the whole request is built on: that a rig added after the clothes really does
leave them unrigged. The checklist is under
["Verification status" in the request](done/009-add-rig/README.md#verification-status), and
[NEXT_STEPS.md](NEXT_STEPS.md) folds it into the same outstanding session.

## [FR 010](done/010-mesh-assets/README.md) — equipping and removing mesh assets

Landed the two tools that finally *consume* [FR 005](done/005-list-assets/README.md)'s catalogue.
`mpfb_add_asset` equips one MHCLO asset through `HumanService.add_mhclo_asset()` — all eight types it
accepts, not only the clothes and proxies the vision document had listed — and `mpfb_remove_asset`
takes one off through `unload_mhclo_asset()`. Removal was in scope from the start for one reason:
deleting the object through generic blender_mcp leaves the body's mask modifier and the garment's
sub-rig behind, so without it an agent that equips the wrong garment has no correct way to undo it.

Two of `add_mhclo_asset()`'s arguments are handled rather than passed through, and both are the same
kind of mistake. `asset_type` is **required** here, because MPFB's default of `"Clothes"` is wrong
for six of the eight types and wrong in a way nothing reports — hair added without it *becomes*
clothes, with the wrong colour, the wrong delete-group handling and a permanently wrong
`object_type`. `material_type` is defaulted **per asset type** instead of globally, matching MPFB's
settings panel and `_check_add_proxy()` rather than the function signature, with the chosen value
echoed back because it was usually not the caller's.

Two conventions were added to
[architecture.md](../specifications/architecture.md). **An acting tool accepts every identifier its
catalogue reports**: `mpfb_add_asset` takes the absolute `path` and the portable `fragment` alike,
requires exactly one, and always reports `resolved_path` — because
`AssetService.find_asset_absolute_path()` matches on *basename* and falls back to the first hit, so
two packs shipping `hat.mhclo` resolve to a coin toss. That is the acting-tool counterpart of
`mpfb_list_assets`' `pack_ambiguous`. And **where MPFB's own code paths disagree, mpfb-mcp picks one
and names it**: adding a proxy has three implementations in MPFB and they produce visibly different
characters, so this follows the *service-layer* one (`_check_add_proxy()`, which is what `.mhm`
loading uses), reports its four extras individually in `proxy_extras`, and says so in the docstring
rather than normalising the divergence away. That generalises
[FR 008](done/008-detail-targets/README.md)'s "UI versus services" clause to any two MPFB code paths.

`codegen/` gained its third shared fragment, `asset_sections.py`, and — as with
[FR 009](done/009-add-rig/README.md)'s `rig_lookup.py` — an existing payload was migrated onto it.
The reason is the sharper form of the catalogue/actor rule: `mpfb_list_assets` reports an asset's
`object_type` and `fragment`, and `mpfb_add_asset` has to map the first back to an asset subdir
before it can resolve the second, because `find_asset_absolute_path()` takes a subdir rather than a
type. Two copies of that table disagreeing would not produce a wrong answer — it would produce "not
installed" for an asset the catalogue had just listed, which is the one failure a caller cannot
diagnose.

Reading MPFB's source turned up four things the request did not know. **A delete group is not
guaranteed**: `update_delete_group()` returns before creating either the vertex group or the mask
modifier when the MHCLO declares no delete vertices, so those fields are observed from the objects
rather than derived from the filename. **`bpy.context.mode` has to be checked as well as the
basemesh's**, the same lesson FR 009 learned, because `add_mhclo_asset()` calls
`bpy.ops.object.shade_smooth()`. **A sub-rig is removed only when the asset is genuinely deformed by
it** — `unload_mhclo_asset()` gates on `find_deformed_child_meshes()`, which wants an armature
modifier and not merely a parent link. And **that function matches the mask modifier by its `name`,
not by its `vertex_group`**, so one renamed by hand survives the unload with its group intact; that
is reported as `mask_modifiers_left_behind` rather than left to be discovered.

Four files added — two tool modules, two payloads — plus one shared fragment and two test modules,
with `list_assets.py`, its tool module and its tests migrated onto the fragment. Unit tests grew from
492 to 559, over stubs extended with modifier and vertex-group collections that can really be added
to and removed from, a `find_asset_absolute_path()` that reproduces MPFB's basename matching over a
real two-root library on disk, and an `add_mhclo_asset()` that reproduces the observable results
quirk-first: the material skipped entirely when the MHCLO names none, the delete group not built
when it declares no delete vertices, the body-proxy interpolation keyed on the *raw* asset_type, and
Blender's `.001` uniquifying of a repeated name.

**Live verification is outstanding**, as for [FR 007](done/007-macro-details/README.md),
[FR 008](done/008-detail-targets/README.md) and FR 009 — and more so here than for any of them,
since almost everything this request is about is MPFB doing real geometry work that no stub
reproduces. The migration also makes **FR 005's live verification stale**, exactly as FR 009's made
FR 004's. The checklist is under
["Verification status" in the request](done/010-mesh-assets/README.md#verification-status), and
[NEXT_STEPS.md](NEXT_STEPS.md) folds both into the same outstanding session.

## [FR 011](done/011-skin-and-materials/README.md) — skins, asset materials, and the UI's own defaults

Three tools, and the end of grey characters. `mpfb_set_skin` wraps
`HumanService.set_character_skin()`; `mpfb_set_asset_material` swaps an equipped garment's material
for one of the alternatives shipped beside it, or puts its own back; and
`mpfb_list_asset_materials` is the small catalogue the second one had to have, because nothing else
names those files. Before them mpfb-mcp could list every skin on the machine and apply none of them,
so every character it produced looked like clay — [FR 005](done/005-list-assets/README.md) had been
reporting the `skins` subdir since the catalogue was built, with nothing on the other end.

A skin is not an asset in the sense [FR 010](done/010-mesh-assets/README.md) uses the word. It is a
*material*, applied to objects that already exist rather than imported as one, and to **two** of
them — MPFB gives the body proxy the same skin, and the response is the only place a caller learns
a second object changed. It also carries a parameter that matters more than the file does:
`skin_type` picks between five entirely different node trees built from the same MHMAT, and the
one-line entry in `vision.md` had not mentioned it at all.

The interesting half is not the wrapping. **A service signature's default is not always the
product's default**, and `set_character_skin()` disagrees with MPFB's own settings panel twice:
`skin_type` defaults to `ENHANCED_SSS` in the signature and `MAKESKIN` in the panel, and
`material_instances` is accepted as `True` for a `MAKESKIN` skin that `loadlibraryskin.py` would
have forced to `False`. Passing the signature's values would produce characters that **cannot be
reproduced through MPFB's own UI** — the same bar [FR 007](done/007-macro-details/README.md) sets
for macro details. So the tool follows the panel both times and reports
`material_instances_requested` beside `material_instances_used`, which is the new standing
convention in [architecture.md](../specifications/mpfb-integration.md#where-mpfbs-ui-coerces-or-re-defaults-a-service-argument-mpfb-mcp-does-the-same-and-reports-both):
where MPFB's UI coerces or re-defaults a service argument, mpfb-mcp coerces the same way and reports
both values, because a silent coercion is indistinguishable from a bug.

`mpfb_set_asset_material` is the limiting case of FR 010's other convention. Where that request
picked between three MPFB implementations of adding a proxy, this one has **none to pick from**:
setting an alternative material exists only in a UI operator, as two module-level helpers with no
service behind them. Both are reimplemented from services — importing an MPFB submodule is
forbidden, and a UI operator module is the worst case of it — and three of the operator's quirks are
reproduced rather than tidied up, because each is a way the result would otherwise differ from what
the panel gives the user: the replacement is always a MakeSkin material under the fixed name
`makeskinmaterial`, the slots are *popped* rather than deleted so the old node groups survive, and
the viewport colour is keyed on the object's recorded `object_type`.

`mpfb_list_asset_materials` exists because alternative materials are not an asset library section —
they are MHMAT files in the asset's own directory — so `mpfb_list_assets` cannot report them and the
gap was invisible from its answer. It also inherits `mpfb_list_targets`' staleness convention *from
the other side*: MPFB caches that scan per asset with no invalidation, so here it is mpfb-mcp that
reports a snapshot, and the docstring says so.

Reading MPFB's source turned up ten things the request did not know; three changed the design.
**`set_character_skin()` tests its five types with five separate `if` statements, after deleting
every material on the character** — so an unrecognised `skin_type` destroys the skin, builds
nothing, and raises from a function that never saw the bad argument. That is why the vocabulary is
checked in the payload before anything is destroyed and, uniquely in this package, in the tool
module as well; it is now recorded as the one exception to
[validate the shape, never the vocabulary](../specifications/tool-interface.md#validate-before-crossing-the-socket).
**The enhanced-settings file copy is gated on `material_instances`, not on the skin type**, so the
default call writes nothing outside the `.blend` at all. And **`scale_factor` defaults to `1.0`
while the first threshold is `> 0.9`**, so an ordinary character is treated as decimetre-scaled —
which `scale_assumption` reports precisely because a caller would expect `METER`.

Six files added — three tool modules, three payloads — plus three test modules, and no shared
fragment: `asset_sections.py` gained a second consumer but was not edited, so **no existing live
verification was made stale**. Unit tests grew from 559 to 654, over stubs whose material model was
rebuilt: `material_slots` is now derived from `data.materials` the way Blender derives it, since the
skin path deletes materials and the alternative-material path pops slots and the two must not look
alike. `set_character_skin()` reproduces MPFB's ordering quirk-first — the source fragment recorded
before the deletion and only when a file was given, the five-`if` dispatch that builds nothing for
an unknown type — and the `material_instances` coercion is **deliberately absent from the stub**, so
the payload is what performs it and the test is testing mpfb-mcp.

**Live verification is outstanding**, as for [FR 007](done/007-macro-details/README.md),
[FR 008](done/008-detail-targets/README.md), [FR 009](done/009-add-rig/README.md) and FR 010 — and
the stubs establish less here than anywhere: a material *is* a node tree, and nothing in the suite
builds one, so the primary goal ("the same result MPFB's own skin library produces") rests entirely
on reading source. The checklist is under
["Verification status" in the request](done/011-skin-and-materials/README.md#verification-status),
and [NEXT_STEPS.md](NEXT_STEPS.md) folds it into the same outstanding session as the other five.

## [FR 012](done/012-observability/README.md) — observability: seeing what crossed the socket

The first effort since the proof of concept that adds **no tool at all**. Twenty tools do the same
three things — assemble a program, hand it to `send_code()`, return the envelope — and until now
nothing kept any of it. A failure inside Blender arrived as a traceback naming a line number in a
program that existed on neither side of the socket, and mapping that line back to a file was
guesswork twice over: a payload's own line 40 lands near line 300 of what actually ran, and the
programs run from about 4 KB to about 52 KB. There was no timing either, while four design
decisions cite a ~1.0 s round trip measured once, by hand, on one tool, a year of development ago.

`MPFB_MCP_RECORD_DIR` names a directory and each call leaves three things in a per-run subdirectory
of it: the exact program in a `.py`, the full envelope in a `.json`, and one tab-separated line in
`index.tsv` — sequence, timestamp, tool, program bytes, milliseconds, envelope status, response
bytes. `MPFB_MCP_LOG_LEVEL` attaches a `stderr` handler to a `logging` hierarchy that otherwise has
none. Both are off by default, and off means literally off: no directory created, no file opened,
nothing formatted, the same bytes on the wire — which matters beyond tidiness, since the disabled
path is the one the entire test suite exercises.

Two structural points are the interesting half. **The tool name was already in the program.**
`codegen` labels the payload seam so that a Blender traceback's line number can be traced back to a
file; the same marker says which tool the program belongs to, so `send_code()` needed no extra
argument and **no tool module, no payload and no `codegen/` module was edited**. That created a new
coupling — a format written by one module and parsed by another, two modules that previously had
nothing to do with each other — which is now pinned by tests on both sides rather than by a
comment. And **the program is written before the socket call**, not with the response afterwards:
writing both together is the easy version and silently loses every case the record exists for, a
timeout, a crash, a call that never returns.

Reading the host turned up the thing the request did not know. **`FastMCP()` calls
`logging.basicConfig()`**, so in the real server the root logger is at `INFO` with a handler on it
before any tool runs. An ordinary `logger.isEnabledFor(INFO)` gate would therefore have switched
per-call timing and formatting on in every session that never asked for it, making "no handler by
default" true in letter and false in effect; the per-call line is gated on this package's own
variable instead, and propagation is off while its own handler is attached, or each line prints
twice. mcp's handler turns out to be a `RichHandler` on a `Console(stderr=True)`, so the transport
was never actually at risk — but the margin was one library default, which is why
[Stdout belongs to the transport](../specifications/observability.md#diagnostics-attach-at-the-socket-boundary-never-to-the-program)
is now a standing rule rather than a warning in one docstring.

The one caller-visible change is deliberately narrow, and was the request's own open question: an
**error** envelope, and only while the record is enabled, gains an `mpfb_mcp_record` key naming the
two files. Whoever reads a failure is usually an agent rather than the person who set the variable,
and a failure that does not say where its own evidence landed wastes the record. A success envelope
is untouched in every configuration.

Two files added — `src/mpfbmcp/observability.py` and `tests/test_observability.py` — plus
`tests/fake_addon.py`, the throwaway add-on server pulled out of `test_connection.py` so both
modules could share it, now able to answer per request, answer nothing, and keep the raw request
bytes. Unit tests grew from 654 to 681, and unusually for this repo that number covers most of the
request: the mechanism is entirely on this side of the socket. **One live check is outstanding** —
that a traceback line number from a real add-on failure resolves to the right line of the dumped
program, which is the one thing no stub can establish. It is the first item of
[FR 013](done/013-live-verification/README.md)'s session, recorded in
["Verification status"](done/012-observability/README.md#verification-status).

## [FR 013](done/013-live-verification/README.md) — the live verification, and the harness that makes the next one cheap

The debt this cleared was five requests and twelve tools deep. FR 007 through FR 011 each reached
`Done` with their live check outstanding, each postponement honestly recorded and each justified by
the same thing: the check was one large manual session, and nothing from the previous one survived
to make the next one cheaper. FR 006's run built a character by hand, snapshotted twelve datablock
collections by hand, compared them by hand and threw all of it away. That — not laziness — is why a
five-request backlog was not five times as easy to face as a one-request one, and it is the defect
this effort was really about.

**All eight checklists ran and all eight are green**: FR 012's inherited item, the two stale
catalogue re-checks (FR 004 and FR 005, both made stale by shared-fragment migrations), and FR 007
through FR 011. Every one of the seven affected requests carries a rewritten
`## Verification status` with the observed value beside each item.

**Three claims that had only ever been readings of MPFB's source are now observations.** A
character built through `mpfb_set_macro_details` ends with the same 21 shape keys at the same
values as one built on MPFB's own phenotype slider. A garment equipped through `mpfb_add_asset` is
identical to one equipped through MPFB's asset library panel down to the vertex positions. And
rigging after dressing really does leave the clothes unrigged — 0 weighted vertices against 285 —
which is the claim
[A tool reports an ordering constraint it cannot enforce](../specifications/mutating-tools.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
rests on. None of the three needed a screenshot: MPFB's panels are thin enough that driving the
scene property behind a slider or calling the operator behind a button *is* pressing it, so each
comparison is a diff of two objects in one file.

**Three defects were found and fixed, none of which anything on this side of the socket could have
caught.** A body proxy did not hide the base mesh, because `mpfb_add_asset`'s idempotence guard
could not tell MPFB's own `Hide helpers` mask from the `Hide base mesh` one it was looking for —
they differ only in `invert_vertex_group`, and the response reported the mistake back as
reassurance. `mpfb_get_macro_details` reported two lists in two different name spaces while its
docstring told callers to compare them, so the drift check it offered was false on every character
there is. And two fields returned `[]` where they meant "not computed" — a dry run's per-target
list, and a refusal that named every MASK modifier on the body including two the user must never
delete. The stubs could express all three once they stopped being kind: the stub basemesh had no
modifiers at all, and adding MPFB's real one broke three existing tests, two of which were the
tests being wrong.

**Four decisions were argued against a round-trip figure that is four times too high.** FR 005's
~1.0 s was measured once, on one tool, on a cold asset library. The socket round trip is **250 ms**.
All four decisions survive on the corrected number — and the batching one survives by a much larger
margin than its own argument claimed: thirty modifier changes cost **3.6 s** in one call and
**98.4 s** in thirty, because what batching saves is not the transport but thirty rebuilds of
MPFB's category table. Two open questions closed: compile time for a 50 KB generated program is
**3.7 ms**, about a thousandth of the call, so
[readability over program size](../specifications/architecture.md#readability-and-developer-experience-are-prioritized)
costs 0.1% and is no longer a tradeoff worth discussing; and all five skin types build within 33 ms
of each other, so `LAYERED` is not the outlier MPFB's own documentation implies (its warning is
about render cost).

**Of seven candidate MPFB defects carried forward from FR 008-FR 011, four were confirmed, two
refuted and one turned out worse than described.** `RigService.identify_rig()` cannot return `None`
— it falls through to `"unknown"` — and the alternative-material cache *does* have an invalidator;
both were readings of source that the running install did not support. `set_character_skin()`'s
five-`if` dispatch is confirmed and is quieter than feared: with `material_instances` off, which is
the default for three of the five types, a one-letter typo deletes every material on the character
and raises **nothing at all**. And "three disagreeing proxy code paths" is two: the library operator
agreed with `_check_add_proxy()` on every field compared. The decision that rested on it survives
with a better reason, now in the specification — what makes the choice load-bearing is that the
*obvious* implementation is the one that differs.

The enabling half is [verification/](../verification/): a harness, a fixture builder, eight
checklist scripts, a measurement script and a runner, outside `src/`, not discovered by the test
runner and not shipped. Re-running a whole checklist after a fix is one command. Its worth showed
up immediately — roughly a third of the first-pass failures were the harness's own, every one a
wrong response *field name*, and in a manual session each would have been indistinguishable from a
defect. Two comparisons are marked as needing a restarted Blender rather than approximated, because
`ui/model/_modelsubpanels.py` builds its table at module import time.

Alongside it, [review.md](done/013-live-verification/review.md): the architectural review, written
after the run so it could cite it, with every recommendation classified as fixed-here, scoped as a
request, or rejected with a reason. It found no drift among nineteen duplicated payload helpers —
sixteen are byte-identical and the three that differ do so for reasons — and it found the largest
uncosted thing in the package, which is that the three tools sharing `target_categories.py` rebuild
MPFB's category table from disk on every call, at ~1.5-2 s each.

The lifecycle changed too, since this effort is the one with standing to propose it:
[a `Done` whose live verification is outstanding must say so on the status line](CLAUDE.md#sections-inside-the-readmemd-file),
not only in a section further down. That is how five requests reached `Done` without anyone
noticing the debt compounding.

## [FR 014](done/014-uniform-performed-flag/README.md) — one name for "it happened", across the eleven mutating tools

The first of the six requests scoped out of FR 013, and the smallest one whose justification is a
measurement rather than a judgement. Every mutating tool already reported whether it had done the
thing, under its own name: `added`, `applied`, `removed`, `generated`, `changed`, `recalculated`,
`refit_performed`. Each reads well on its own. The set does not — reaching for the wrong name
yields `None` rather than an error, so getting it wrong is silent, and
[FR 013](done/013-live-verification/README.md)'s harness, written with the source open, guessed
wrong on **three tools in one session**, each wrong guess turning a passing check into what looked
like a tool defect. The refusal fields `found`, `ready` and `blocked_by` were uniform already and
were never mis-read, which is what says the problem was the variation rather than the naming.

Every mutating tool now also reports **`performed`**, a real boolean, true exactly when the
character was changed. Nothing was renamed and nothing removed: a caller written against `added`
still works, and `added: true` beside `asset_object_name` still reads better than `performed: true`
would. The convention is
[a section of its own in mutating-tools.md](../specifications/mutating-tools.md#the-flag-a-caller-branches-on-is-called-performed).

**The request's own count was wrong, and correcting it is the interesting part.** It said twelve
mutating tools and named nine verbs; there are **eleven** tools, and the two the list missed are
exactly the two where the flag is *not* a rename of an existing field. `mpfb_create_human` has no
verb at all — it creates a character or comes back as an error envelope. `mpfb_set_macro_details`'s
verb is `recalculated`, and a call that names no slider returns `ready: true` having recalculated
nothing, because [do only what was asked](../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after)
makes a no-op a success rather than a refusal. A third case the request did anticipate:
`mpfb_symmetrize_targets` under `dry_run: true` returns a populated `changed` and has written
nothing. A fourth nobody anticipated turned up while the tests were written: `mpfb_set_targets`
fails a whole batch on one bad entry and answers `ready: true` with an empty `applied`, which is
the first thing a flag derived from `ready` alone would get wrong.

So the flag is genuinely not the verb, four times over, and that is what makes this a request
rather than a rename.

**One place, not eleven.** `codegen/shared/performed.py` is the fourth shared fragment, and the
first that binds nothing from the bootstrap and reads nothing out of MPFB — one function over a
dict the payload has already finished building, which is what lets it be concatenated ahead of any
payload. Each payload calls it once, on its last line, stamping the flag onto whichever answer the
branches above it built: `set_asset_material.py` constructs eleven refusals and one success, and a
key written twelve times is twelve chances to write it wrong in the branches nobody re-reads. The
two universal falsehoods — a refusal and an unresolved subject are never performed — live in the
fragment, so no call site has to remember them. Eleven `shared=[...]` arguments were added to
`assemble()` calls the tool modules were already making; no shared code-generation module was
edited, which is the property [architecture.md](../specifications/architecture.md#shared-fragments)
asks a fragment to preserve. It also earns its place there on the same ground `rig_lookup.py` does:
consequence, not size. Eleven implementations of the flag would be the original problem in a new
spelling.

**The verification is an audit rather than a checklist item.** The flag is computed on the near
side of the socket, so the 701-test suite (up from 685) carries all of it — ten per-tool checks
that `performed` matches that tool's verb, four exercising the fragment's function directly, and
two in `test_codegen.py` pinning *which* payloads stamp it, in both directions. What unit tests
cannot establish is that the variable a payload stamps from is the one live MPFB sets, since the
stubs feed the verb and the flag from the same run. So `verification/harness.py` now wraps every
mutating tool callable in an audit that compares the two on **every call any checklist already
makes**, reported by `Report.summary()` as one more item per checklist. No check script was edited:
the request asked for something "nearly free", and this is stronger than a per-call-site assertion
would have been, because it also covers the calls a checklist makes as setup rather than as its
subject.

The eleven tool docstrings gained a short paragraph saying to branch on `performed` and read the
verb — about 1.5 KB against the description budget
[FR 016](done/016-trim-tool-descriptions/README.md) wants to shrink, which is the trade that request
already names: rationale out, field names in.

## [FR 015](done/015-fourth-shared-fragment/README.md) — the two duplications that would have drifted silently, and the census that keeps the question cheap

**Status: landed in full.** The two live checklists it left outstanding were re-run by
[FR 017](done/017-category-table-cost/README.md), which changed the assembled source of the same
payloads and had to run them anyway; the qualifier on its status line is cleared.

[FR 013's review](done/013-live-verification/review.md#is-the-duplication-a-risk-or-an-economy) had
already done the counting: nineteen module-level helpers with two or more copies across the twenty
payloads, **sixteen byte-identical** after normalisation, nothing drifted. This effort merged
**two**, and the interesting part is which two and why the other seventeen were left alone.

`codegen/shared/refit_blocker.py` holds the condition four payloads need: a generated Rigify rig
with no meta rig left cannot be refitted, and `HumanService.refit()` says so only through an
`operator` no MCP tool has one of. The fragment exposes a **predicate**, not a message. Each
payload keeps a `rig_refit_blocker()` that phrases the answer, because `mpfb_refit_human` reports
a refit that already happened and the other three predict one they are about to attempt — a
fragment taking a tense argument would have been worse than four sentences written where they are
read. Four copies of the *condition* is the `rig_lookup.py` failure exactly; four copies of the
*message* is at worst four sentences that read slightly differently.

`codegen/shared/modifier_reading.py` holds one modeling category's slider reading, which
`mpfb_get_target_stack` reports and `mpfb_symmetrize_targets` acts on. This was a genuine
reconciliation rather than a copy-paste removal: the two implementations differed in **shape**,
one answering from a snapshot read once and the other from `key_blocks` on every question, because
it writes between readings. The rule is now shared and the *lookup* is the parameter — a
`present`/`value_of` pair, two callables rather than one because MPFB's `has_target()` matches the
encoded name and `get_target_value()` does not. Both payloads keep the lookup that suits them, and
neither can read a category differently from the other.

The agreement is asserted the way `rig_lookup.py`'s is: one test runs both payloads over **one**
character in `DetailTargetTestCase` and compares every category reading, including the asymmetric
pair at +0.4 against -0.25 where the negative side reads back negated. It was checked by making
one of the two diverge on purpose and watching it fail. `test_codegen.py` gained a class per
fragment — run directly, against a namespace holding the handful of names each binds — plus a
**drift check per fragment** asserting no payload keeps an implementation of its own: no refitting
payload calls `object_is_generated_rigify_rig()`, neither reading payload negates a value. 701
tests to 714.

**What was deliberately not merged**, and the reason it is worth recording: `blocked()`'s six
variants, which the census reports as six copies in six variants — one convention applied six
times, differing only in which of that tool's own fields each nulls out, where a mechanism for
"this tool's null response" would be bigger than the six copies. Being identical is likewise not a
reason: `property_value()`'s six copies and `as_path()`'s four are harmless and stayed.

The census became `verification/census.py`, the one script there that needed no Blender (deleted
by [FR 023](done/023-verification-smoke-test/README.md) as FR-time instrumentation; git holds it). It gained something the hand-run version did not have: it reads which fragments
each payload is actually assembled with out of the `assemble(..., shared=[...])` calls in the tool
modules, so it can separate a payload that **shadows** a fragment it names — a real defect, since
the fragment is concatenated first and its copy is then dead — from one that merely defines the
same name without using that fragment. The first pass, before the pairings were read, reported
five shadowings and every one was a false alarm. What the weaker signal does show is a migration
candidate: `list_targets.py` defines `files_matching()` and `read_target_json()` that
`target_categories.py` already has, which is the
[migration](NEXT_STEPS.md#modeling) FR 017 carries.

The census also shows this effort's own effect: `modifier_value()` is gone from the list, and
`rig_refit_blocker()` is 4 copies in **2** variants — which is now the deliberate tense split
rather than drift, and is the one entry a future reader should not "fix".

## [FR 016](done/016-trim-tool-descriptions/README.md) — the tool descriptions trimmed, and the budget that keeps them trimmed

**70,352 B of descriptions to 47,759 B**, with the parameter schemas untouched at 8,105 B: an MCP
client now preloads 55,864 B where it preloaded 78,457 B, before a single call is made.
`mpfb_list_assets` went 6,246 → 3,309, `mpfb_add_asset` 5,407 → 2,893, and `mpfb_create_human`
*grew* 1,259 → 2,064, because the entry point was the one description that said nothing about how
it relates to `mpfb_set_macro_details`.

The request's own framing was that a third of the four largest descriptions was rationale rather
than instruction, and that is what came out. But **half the saving was in three things the request
had not identified**, and the first of them is the one worth remembering:

**10 KB of the 70 was whitespace.** `Tool.from_function()` takes `fn.__doc__` verbatim, so every
line of every description crossed the wire carrying the eight spaces it is indented by in the
source file — about 500 bytes per tool that no reader of the source, and no reader of the
response, ever saw. `build_server()` dedents each description once after registration. It is the
kind of cost that only exists because nobody had measured the thing.

**The conventions twenty tools were each repeating moved to the server instructions**, which are
sent once: the response envelope, the `name`/active-object subject convention, that a refusal is
an answer carrying `found`/`ready`/`blocked_by`, the uniform `performed` flag from
[FR 014](done/014-uniform-performed-flag/README.md), and that a capped listing always reports
`truncated` and `total_count`. The instructions grew 1.2 KB and about 6 KB came out of the
descriptions. A tool now says only where it *differs* from the convention — `mpfb_symmetrize_targets`
returning `performed: false` under `dry_run` with a populated `changed`, `mpfb_refit_human` deriving
the flag from `refit_performed` — which is the part a caller actually needs.

**And a strict application of the request's own test** — would a caller with no access to this
repository act differently for having read this sentence? — took most of the rest. The six-line
refusal enumerations became one sentence naming the codes and keeping only the surprising ones
(`already_rigged`, because MPFB cannot swap a rig; `not_a_mesh_asset`, because the underlying
function would delete a basemesh; `skin_failed`, because the materials are gone by then).

**FR-3 asked for "the same script that measured it here", and there was none.** FR 013 measured by
hand — which is exactly how the figure had drifted from an estimated 58.5 KB to a measured 66.7 KB
without anyone noticing. The measurement is now
[tests/test_description_budget.py](../tests/test_description_budget.py), a ceiling the suite
asserts and a per-tool table when the module is run as a script. It measures the server
`mpfbmcp.build_server()` actually builds rather than a list of its own, which is why the server's
construction is now split out of `main()`: a tool registered without being thought about lands
inside the budget rather than outside it. The ceiling is 48,500, which leaves about a paragraph of
room: enough that a real addition fits, and not enough for a habit.

**It stopped at 47,759 rather than the ~45,000 the request aimed at.** What remained at that point
was instruction: response field names, argument vocabularies, and the surprising facts the request
explicitly protects. Trimming further would have been compressing instruction, which the request
rules out in its own goals.

**What the trim nearly cost.** Paragraph-by-paragraph editing across twenty docstrings deleted
three whole response-field bullet lists — `mpfb_get_object_info`'s, `mpfb_list_rigs`',
`mpfb_get_macro_details`' — each time by replacing a bullet *list* where a bullet was meant, and
six mutating tools lost the word `performed` that FR 014 had put there. All nine were caught by
diffing every backtick-quoted identifier in each docstring against its version in `HEAD`, which is
the check any future pass over these files should repeat: the budget test can see that a
description shrank, and cannot see that it lost the field a caller branches on.

Two standing specifications gained a section, both for rationale that came out of a description
and had nowhere else to live:
[A tool description is call-time instruction with a budget](../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget),
which states the test, the budget and where a repeated convention belongs; and
[MPFB caches what it scans](../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides),
which collects the three MPFB caches under the catalogue tools — the asset list keyed by label, the
session-lifetime custom rig list, and the alternative materials with no invalidator anyone calls.

## [FR 017](done/017-category-table-cost/README.md) — what a call actually costs, and the fragment sent once per session

**The request was wrong about where the time went, and finding that out is the result.** It was
written against a solid observation — the three tools sharing `codegen/shared/target_categories.py`
are the slowest non-import tools in the catalogue, and the fragment does rebuild MPFB's category
table on every call — and a wrong inference from it. Timed inside Blender, that rebuild takes
**4.0 ms**. The `os.walk` the request blamed takes 1.1 ms of it.

What the 1,500 ms is, is **transport, charged by the byte**. blender_mcp's add-on reads exactly one
`conn.recv(4096)` per timer tick and then returns, and its tick is 0.25 s while busy and 1.0 s once
five seconds have passed without a request *finishing* — bytes arriving do not reset that countdown.
So a program costs about **250 ms per 4 KB busy and 1 s per 4 KB idle, whatever it does**: an empty
program 254 ms, 40 KB of comments 2,780 ms busy and 10,087 ms idle, predicted from the chunk count
to within a few percent. This also corrects the figure four decisions in this package were argued
against: "the round trip is 250 ms" is one tick, measured on a one-chunk program. FR 013 re-derived
those decisions on real numbers and they stand, but the number means something else now.

**So the thing worth caching was the code, not the answer.** `codegen/shared_loader.py` keeps a
shared fragment's source inside Blender in a `sys.modules` module of ours, keyed by
`<file>@<sha256[:12]>`; `mpfbmcp/shared_cache.py` decides whether a call carries that source or
names it, and re-sends once if Blender turns out not to hold it. Steady-state programs, measured
live: `mpfb_get_target_stack` 37.5 KB → **17.9 KB** (−1,519 ms), `mpfb_set_targets` 57.2 KB →
**35.6 KB** (−1,533 ms), `mpfb_symmetrize_targets` 50.7 KB → **25.2 KB** (−1,775 ms),
`mpfb_list_targets` 19.3 KB → **17.0 KB**. Against an idle Blender — the one an agent that thinks
between calls actually meets — the same four saved **4.0 / 6.0 / 6.0 / 7.0 s** per call.

A cache of the *table* was built first, complete with a directory-mtime signature, a `refresh`
argument on four tools and a `category_table` field in four answers, and was thrown away when it
was measured: the accessors and the cache machinery it needed on every call came to as many bytes
as the scan it stopped sending. Caching source turned out to be both the larger saving and the
safer one, and those are the same fact — **a cache of code keyed by a hash of that code cannot be
stale**. The scan still runs on every call, so `mpfb_list_targets` still sees a target installed
since Blender started, no tool gained an argument, and the description budget is unchanged at
47,759 B. `tests/test_shared_cache.py` asserts the installed-between-two-calls case directly, which
is the one thing the discarded design would have had to work to keep.

The secondary goal landed too: `payloads/list_targets.py` takes its scan from the fragment, so the
catalogue and the three tools that act on it read one implementation, and
the census no longer reported `files_matching()` or
`read_target_json()` against `target_categories.py`. Two shape differences were reconciled in the
open — the `custom` section is now labelled as MPFB labels it, and a `target.json` category with no
`name` is dropped rather than listed. The cost is that this one tool's *first* call carries 18 KB it
never used to, which is stated rather than hidden.

Live: `run_all.py` in full, **85 passed, 0 failed, 3 skipped** — which also clears FR 015's
outstanding re-verification. `verification/measure.py` gained
`transport_by_program_size`, the measurement this effort turned out to be about, and
`shared_source_cache`, its before/after. The 4 KB chunk itself is a one-line defect in an add-on
this project does not own, and removing it there would take most of this cost out of every tool at
once: that is
[in NEXT_STEPS.md](NEXT_STEPS.md#file-the-4-kb-chunked-read-against-blender_mcp), and meanwhile the
add-on's `timer_interval_active` preference is a four-to-five-times speedup a user can apply today,
which [CLAUDE.md](../CLAUDE.md#commands) now says.

## [FR 019](done/019-file-mpfb-defects/README.md) — the confirmed MPFB defects, written up where MPFB's own effort will read them

**The first effort whose deliverable is in another repository**, and the first that changes no
behaviour at all. Five requests had ended by naming things in MPFB that looked like defects, all
read from source; [FR 013](done/013-live-verification/README.md) provoked them against a running
install and left the provocations as a script. This request wrote the result up.

The report is [`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../mpfb2/features/MCP_DISCOVERED_BUGS.md),
256 lines, six defects worst-first, each with the code path, the observed values and the name of
the function in [check_mpfb_issues.py](done/019-file-mpfb-defects/check_mpfb_issues.py) that
provokes it. What
"filing" means was settled when the request was accepted: a document handed to that project, not an
issue in a tracker.

**Nine candidates went in and six came out, and that ratio is the reason the request existed
separately from the effort that found the evidence.** Worst first: a user target whose filename
exceeds 56 characters takes the whole add-on down at `register()`, because
`_modelsubpanels.py` builds a Scene property named `custom_<filename>` at import time and Blender
rejects an identifier over 63; `TargetService`'s own name encoding starts at 60, so a target long
enough to trigger MPFB's encoding cannot sit in a scanned directory at startup at all. Then: a
`.target.gz` becomes **two** shape keys, at two values, on one mesh, from one file, because the
panel's `replace(".target", "")` is a substring replace and `filename_to_shapekey_name()`'s is an
anchored regex. `set_character_skin()` deletes every material before testing `skin_type` against
five `if`s with no `else`, and with `material_instances` off — the default for three of the five
types — it raises **nothing**. `unload_mhclo_asset()` deletes whatever object it is handed;
confirmed against an ordinary cube. `alternative_materials_for_asset()`'s `exclude_default` appears
in the signature and the docstring and nowhere else, and its cache key does not include it, which
constrains any fix. And `object_is_rigify_metarig(check_bones=True)` dereferences `.pose.bones`
under a `typing.cast` that does nothing at runtime.

FR-2 left the two secondary observations to the effort's judgement and both were written up, in
different registers: the metarig `AttributeError` as the sixth defect, and the proxy-operator
duplication under a heading saying **it is not a defect** — FR 013 measured `_check_add_proxy()`
and the library operator producing identical state on every field, so what is reportable is that
two implementations agree today, and that the *obvious* entry point, `add_mhclo_asset()`, is the
one that gives a different character. The report ends with the **two candidates that were wrong**,
named as such, because both had been written into this repository as reasons for decisions.

**FR-4 is the requirement worth remembering: filing is not fixing.** Nothing was removed. MPFB has
its own priorities and a reported defect may stand for a long time, so every workaround, coercion
and defensive check that copes with these six stays exactly where it is —
`mpfb_remove_asset`'s type refusal, `mpfb_set_skin`'s local `skin_type` vocabulary, the
`data.bones` guard in `generate_rigify_rig.py`. A workaround goes when a **running** MPFB no longer
needs it, which is what `check_mpfb_issues.py` detects: its assertions are written so that a fixed
MPFB makes them fail.

**FR-5 cost more than filing did.** The two refuted candidates were still cited as reasons in six
places, three of them load-bearing prose: `generate_rigify_rig.py`'s docstring said
`identify_rig()` can return `None` and that MPFB's `poll()` would raise on that (it returns
`"unknown"`, and the `poll()` returned `False`); `list_asset_materials.py`, its payload, the root
CLAUDE.md and `specifications/responses.md` all said the alternative-material cache has no
invalidation, and `responses.md` and the tool description went further and told the caller that no
`refresh` argument could ever help. That last one was downloaded by every MCP client on every
connection. The corrections say what was checked and no more, and `responses.md` gained the reason
in general form: **a limitation attributed to MPFB is a claim about MPFB**, and carries the same
burden of evidence a defect report does. The code the wrong reasons had justified was left alone,
per FR-4, with the docstrings now saying which guard is necessary and which is belt and braces.

[mpfb-integration.md](../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)
gained the standing rule — where a confirmed defect is written down, and that writing it there
changes nothing about what a tool does. [FR 018](018-alternative-material-refresh/README.md) shrank
as a result, since half of what it set out to correct is now corrected, and
[FR 023](done/023-verification-smoke-test/README.md) grew a constraint it did not have: its FR-7 deletes
`check_fr010.py` and its FR-8 moves `check_mpfb_issues.py`, and both are now cited by path **from
another repository**, where no link check here would catch the break.

## [FR 020](done/020-trim-claude-md/README.md) — the root CLAUDE.md trimmed, and the rule that keeps it trimmed

The second effort that adds no tool. The root [CLAUDE.md](../CLAUDE.md) had reached **704 lines**
from 92 at the proof of concept, growing once per landed request and never shrinking — 214 after
FR 003, 316 after FR 007, 451 after FR 009, 586 after FR 011, 704 after FR 013, about +65 per
effort. Six requests were open, so it would have passed 1000 lines around FR 018.

Length was the symptom. The finding was that the file had become **a second copy of documentation
that exists elsewhere, and the copies had begun to disagree** — five times, each error surviving
for the same reason:

- **The shared-fragment count.** CLAUDE.md said "There is exactly one so far", then described two.
  Three exist; [architecture.md](../specifications/architecture.md#shared-fragments) said three and
  carried a bullet on `asset_sections.py` that CLAUDE.md's `shared/` bullet lacked entirely.
- **A three-way contradiction about local vocabulary validation.** CLAUDE.md called
  `generate_rigify_rig.py` "the only tool here that validates a vocabulary locally" and, eighty
  lines later, said the same of `set_skin.py`; architecture.md said `mpfb_set_skin`'s `skin_type`
  was "the only current case". The code settles it — both validate locally — so the standing
  specification was wrong too, and is now corrected to name **two** cases with the criterion that
  earns one: the damage must precede MPFB's own check.
- **The root [README.md](../README.md) still said twelve tools were unverified.** FR 013 updated
  CLAUDE.md's claim and left README.md's, so the repository's two front doors disagreed about the
  single fact a reader arrives wanting.
- **A retired measurement lived on in one of the two copies.** FR 013 measured the socket round
  trip at 250 ms; architecture.md's batching argument still read "about a second", the very figure
  FR 013 retired. It now carries FR 013's real numbers, which make the argument stronger than the
  guess did.
- **The standing test discipline had no home under `specifications/`** at all.

That last gap is now [specifications/testing.md](../specifications/testing.md): the two-layer unit
suite, the rule that **stubs reproduce MPFB's real behaviour rather than convenient values** —
carrying FR 013's `Hide helpers` evidence, which is the strongest argument for it that exists —
what the suite can *never* establish, and the two mechanics every stub-executing module inherits
that until now were only comments in `blender_stubs.py`.

CLAUDE.md is now **268 lines** and a map rather than a manual: the pipeline diagram, a
module-layout table, a twenty-row tool table, a twenty-row test table, and the residue of facts
that live in no other file — the strict-`bool` rules, `set_targets`' two value ranges, the three
bootstrap identifier names, the `assemble()` signature, that the observability record writes the
program *before* the socket call. Twenty-nine such facts were enumerated before the rewrite and
checked afterwards; nothing was lost. Everything else became a pointer to the copy that is
maintained: a tool's reasoning to its own module docstring, an effort's story to this file, a
principle to architecture.md.

The lifecycle changed, because a trim that FR 021-025 undo is not worth doing.
[Step 2](CLAUDE.md#lifecycle) now says a finished effort does **not** add a narrative paragraph to
the root CLAUDE.md — durable decisions go to `specifications/`, the story comes here, a tool's
reasoning goes in its docstring, and CLAUDE.md is edited only when the layout, the commands or the
conventions actually change. A new tool is one row in each table. Step 1 also gained a sentence
this effort earned: **check the claim you are replacing**, rather than only adding beside it.

## [FR 021](done/021-split-architecture-spec/README.md) — architecture.md split into per-topic specifications

FR 020's sibling, one level down. [architecture.md](../specifications/architecture.md) had reached
870 lines across 24 top-level sections, of which six were about the system's structure and
eighteen were standing conventions about how a tool behaves — how it takes its input, what it must
say back, what it owes a caller when it changes a character, what to do when MPFB is inconsistent.
All real decisions; none of them architecture; all of them filed under a title that said they were.

Two measurements made that a finding rather than an opinion. The document **already delegated
twice** — its preamble sent readers to CLAUDE.md for the module layout, and 24 of the 37 lines of
its "No direct dependency" section described the test suite and the live harness, which
[FR 020](done/020-trim-claude-md/README.md) had just made
[testing.md](../specifications/testing.md)'s subject and which testing.md declined to restate
*because that copy existed*. And **the citations were already section-level**: 195 anchored inbound
links across 27 files, three of them Python modules under `src/`, against 41 anchorless ones.
Nobody was linking to "the architecture"; they were linking to `#preconditions-are-answers`. The
document was being used as five documents and had no way to say so.

It is now seven. `architecture.md` is **221 lines** and describes only the machine — the two
boundaries, resolving MPFB from generated code, the code-generation layout, one module per tool.
[tool-interface.md](../specifications/tool-interface.md) holds what a tool accepts and how a
catalogue's identifiers bind the tool that consumes them;
[responses.md](../specifications/responses.md) what it says back, including `null` versus `[]`;
[mutating-tools.md](../specifications/mutating-tools.md) the extra obligations of changing a
character; [mpfb-integration.md](../specifications/mpfb-integration.md) coping with MPFB's
disagreeing code paths and UI coercions; and
[observability.md](../specifications/observability.md) where diagnostics attach — its own document
because FR 012 was a whole effort about exactly it. None exceeds 180 lines.

**Section text moved verbatim.** One mapping table drove both the split and the link rewrite, and
the move is checkable rather than asserted: all 24 sections parse out on both sides with identical
bodies once link targets are normalized away, and all 29 headings anything ever cited resolve in
exactly one document. The only prose that changed is the section that was deliberately shortened.

Two pitfalls are recorded in the request because both were hit. The **21 intra-document
`](#anchor)` references** do not look like file links, and a rewrite that only handles
`architecture.md#…` misses every one of them. And **`specifications/` must not be exempted from the
rewrite** to protect the freshly-split files: `vision.md` had 21 links in that directory and
`testing.md` two, and the first pass skipped both.

The link checker grew to cover `.py` files, and immediately earned it. FR 020's version scanned
`.md` only — so four markdown links inside `src/mpfbmcp/tools/` docstrings had pointed at
`../../specifications/`, one directory level too shallow, since [FR 011](done/011-skin-and-materials/README.md),
and nothing had ever looked. It now checks 805 links across 125 files, markdown links and the
repo-root-relative prose mentions `.py` docstrings use alike.

Three open requests were retargeted, as lifecycle step 5 requires: FR 014 to `mutating-tools.md`
and `responses.md`, FR 018 to `responses.md`, FR 019 to `mpfb-integration.md`. FR 016 named
`architecture.md` without an anchor and now names `tool-interface.md`, with a note that the split
happened after it was written. FR 015 and FR 017 cite sections that stayed and needed no change.

## [FR 022](done/022-trim-vision/README.md) — vision.md made about the vision

The third and last of the documentation efforts, and the one where the pathology is clearest.
[vision.md](../specifications/vision.md) was 374 lines, of which **296 were the "Target tool
catalog"** — 79% of a document whose subject is why the project exists.

The catalog had been kept scrupulously up to date, which was the problem rather than the defence.
**21 of its 23 entries were marked Implemented**, each grown from a one-line intention into a
paragraph naming the tool's response fields: `mpfb_set_skin` at 25 lines describing
`material_instances_requested`, `settings_file_created` and `scale_assumption`; `mpfb_add_asset`
at 25 lines explaining `proxy_extras` and Blender's `.001` uniquifying. That is reference
documentation, and it was the **third** copy — checked before anything was deleted: all **50**
identifiers named in the catalog appear in at least two other files, the tool's own module and
the feature request that added it, and every live measurement quoted was also in
[FR 013's review](done/013-live-verification/review.md) and in this file.

A forward-looking document that is 91% backward-looking cannot do its job. The two tools that
genuinely do not exist — `mpfb_get_human_summary` and `mpfb_search_docs` — were four lines buried
at 96 and 332.

vision.md is now **137 lines**. The catalog states four capability areas and what an agent must
be able to do in each, which does not need editing when a tool ships, and then names only what is
still missing and why it is worth having. The `## Target tool catalog` heading is kept
deliberately: 15 links point at that slug, 14 of them from finished requests.

Two things were rescued rather than cut. **What makes something a tool** is a new section, and it
is the part of the old catalog that was genuinely vision — a tool is named for a user intent
rather than a service function; a catalogue and its acting tool are designed as a pair; MPFB's
own UI is the fidelity bar; a concept MPFB's UI has but its services lack can still be a tool; a
tool may report what MPFB shows nowhere, since an agent cannot look at the viewport; splitting a
tool can be what makes an order expressible. And the Goal section gained the sentence the whole
project turns on: an agent with a generic code-execution tool can already do anything, so the
measure is not how much of MPFB is reachable but **how few round trips, and how little
source-reading, a competent agent needs to get a character right**.

The backend section was split along the same line the two previous efforts used. The *decision* —
support both, blender lab's stays the reference — is vision and stayed; the adapter's design is
[Supporting a second backend](../specifications/architecture.md#supporting-a-second-backend) in
architecture.md, because "the seam goes below `send_code()`, so tools, payloads and `codegen/`
stay unchanged" is a claim about structure. Its slug is kept too.

Across FR 020-022 the three documents that had become append-targets went from 704, 870 and 374
lines to 268, 256 and 137, and the standing specifications went from two documents to eight, each
named for its subject.

## [FR 023](done/023-verification-smoke-test/README.md) — the live verification becomes a smoke test

[FR 013](done/013-live-verification/README.md) was right that a live check must be a re-runnable
script rather than a memory of a session. Its instruction — put the script in `verification/` —
was the part that did not survive contact with eight efforts. What it produced was **the backlog,
written down**: one exhaustive checklist per feature request, each re-proving that request's claims
forever, 5,308 lines across fourteen files, and a run crossing the socket more than two hundred
times. Minutes, not seconds, and fragile in proportion — which is the same failure FR 013 existed
to fix, repeated at a different scale.

`verification/` is now a **smoke test**: one item per tool, called with the tool's own defaults,
asserting three shallow things — the envelope is not an error, the response carries the keys the
tool's own contract names as always present, and for a mutating tool `performed` is true and agrees
with that tool's verb. It asserts nothing about *values*. Four files, one command, and **42.6 s for
all twenty tools** against Blender 5.1.0 with MPFB 2.0.17, measured at blender_mcp's slow 0.25 s
tick. Beside the twenty there are three run-level items and the set is closed: the install gate,
the leak compare, and FR 012's traceback check.

**3,822 lines were deleted outright** — the eight `check_frNNN.py` checklists, `measure.py`,
`census.py` and `run_all.py` — because their findings had already been folded into
[specifications/](../specifications/) and into this file, and keeping the scripts was keeping a
receipt for a conclusion already written down. `check_mpfb_issues.py` moved rather than went: it
provokes defects in *MPFB* rather than checking mpfb-mcp's tools, so it now lives in
[FR 019's subdir](done/019-file-mpfb-defects/) beside the report it backs, carrying the three
probe targets with it — and with the two paths
[`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../mpfb2/features/MCP_DISCOVERED_BUGS.md) cites
from the other repository re-pointed, which was this request's one obligation outside its own tree.

Two mechanisms keep the directory from regrowing. **Coverage is derived from the registry**: a
registered tool with no smoke item, or an item for a tool that is gone, stops the run — asserted
live and again, without a Blender, in the new
[test_verification_smoke.py](../tests/test_verification_smoke.py). And **the rule about where a
live check belongs is written down** in [CLAUDE.md](CLAUDE.md) and
[testing.md](../specifications/testing.md): an exhaustive live check belongs to the feature request
that needs it, lives in that request's own subdir, and goes to `done/` with it. This request's own
[`check_negatives.py`](done/023-verification-smoke-test/check_negatives.py) is the first thing
written under that rule, and it is what proved the coverage check and the skip path by making them
fail rather than by watching them pass.

Two corrections fell out. FR-3's "not a copy of the contract kept here" needed a mechanism rather
than a habit, since there is no machine-readable contract to read: each item's key list is now held
to the *description an MCP client downloads*, and that check caught two wrong keys on its first
live run. And FR-7's justification for deleting `census.py` — that the drift question is "asserted
per fragment" in `tests/test_codegen.py` — turned out to be true of two fragments out of six;
[architecture.md](../specifications/architecture.md#shared-fragments) now says which two.

`verification/` is 1,163 lines rather than the 700 the request estimated — 4,272 lines of Python
went, close to the 4,600 predicted, but more was left standing than the target allowed for. The
difference is not survival of anything exhaustive: the leak compare needs ~130 lines of embedded
Blender source that no trimming touches, and twenty item definitions cost about seven lines each. It also now changes
**nothing outside the `.blend`** — FR 013's three deliberate exceptions all left with the
checklists that needed them.

## [FR 024](done/024-documentation-urls/README.md) — links to documentation and other online resources

The first entry in the one capability area [vision.md](../specifications/vision.md#target-tool-catalog)
had nothing in: an agent could ask what was installed and what a character was made of, but could
not look anything *up*, and the failure mode was not an error but a guessed URL presented as fact.
Deliberately the small half of that area. `mpfb_list_urls` reports the community addresses —
downloads, asset packs, documentation, forum, issue tracker — read live out of MPFB's
`ui/weburls.py`; `mpfb_list_docs` reports addresses for the nineteen most useful of the 105
developer documents in the mpfb2 repository, which the extension does not ship. The ranked search
over documentation content that vision.md calls `mpfb_search_docs` stays a separate, later effort,
now narrowed to the half an address cannot do.

**Two tools, two shapes neither of which existed here before.** `mpfb_list_urls` is the only tool
that **catches a connection failure and answers anyway**: a links tool that fails when MPFB is
missing is useless in the one situation where the download link is what was wanted, so all four
states — live, MPFB absent, MPFB loaded without its `weburls`, Blender unreachable — are successful
envelopes naming what degraded. Two things about that catch are load-bearing and are recorded as
such: it catches `ConnectionError` only, so a payload that raised *inside* Blender still surfaces
as an error rather than being hidden behind a cheerful fallback forever; and it lives in the tool
module, because the other twenty-one tools depend on a connection failure being an error and this
is one tool's exception rather than a change to the wire layer. `mpfb_list_docs` is the first tool
here with **no payload at all** — a local table and a URL rule, no generated code, no socket, no
Blender, no MPFB — which is a real exception to the module/payload/test naming rule and is now
stated where the payload list is kept rather than left to read as an oversight.

**Reading a UI module became a rule rather than a one-off.** `weburls` is reached through
`sys.modules`, never imported, and
[architecture.md](../specifications/architecture.md#a-ui-module-with-no-service-behind-it) now says
what makes that legitimate: the module must already be imported on a normal install, and it must
hold **data rather than a snapshot**. That second condition is exactly what separates it from
`_modelsubpanels`, which `mpfb_set_targets` deliberately reimplements instead — so
[mpfb-integration.md](../specifications/mpfb-integration.md#sometimes-reading-the-ui-module-is-the-right-answer)
now carries both instances and the distinction between them: *reimplement a UI concept that is
computed, read a UI table that is constant.*

**A standing constraint was settled rather than left implicit**: mpfb-mcp opens no network
connection except the one to the blender_mcp add-on. A tool may hand out a URL; it may not
retrieve one. That is what makes the vendored tables in the new `src/mpfbmcp/reference/`
sub-package uncheckable at run time, which in turn produced
[the first test that depends on a sibling checkout](../specifications/testing.md#a-test-may-depend-on-a-sibling-checkout-if-it-skips-without-one)
and skips without one — accepted with its cost stated, since the alternatives are breaking the
suite everywhere else or letting a renamed document be found by whoever follows the dead link.

Two response conventions came out of it.
[A response says which source answered it](../specifications/responses.md#a-response-says-which-source-answered-it):
where a tool has a live source and a local fallback, `source_of_truth` names which one it got, the
live value wins every disagreement in **both** directions, the disagreement is reported by kind
rather than as one "stale" bit, and "they agree" is not spelled the same way as "we could not
compare" — the `null`-versus-`[]` rule applied to a comparison. And
[a deliberately partial answer carries the size of the whole](../specifications/responses.md#a-deliberately-partial-answer-carries-the-size-of-the-whole):
a *curated* list has no cap and no `total_count` to warn a caller with, so it carries `curated`,
the size of the collection it was drawn from and the address of the whole — nineteen of nineteen
reads as complete, nineteen of 105 with a link reads as a selection.

**The description ceiling was raised deliberately, from 48,500 to 52,200**, with the reason in the
test's own comment and in
[tool-interface.md](../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget):
740 B of headroom against a 400 B per-tool floor cannot absorb two tools, and trimming twenty
descriptions to pay for two would have spent the effort's judgement on the wrong tools. Both
newcomers came in around 1,900 B against a 2,387 B average, and the paragraph of headroom is still
a paragraph.

**The live check found the request's own arithmetic wrong twice, in the harmless direction.** MPFB
publishes **eleven** `URL_*` constants, not the thirteen the request said, and the candidate
document set is **nineteen**, not the eighteen it counted — neither of which matters, because the
constants are enumerated by prefix rather than by a list kept here and the curated count is
computed rather than written down. The request's cost estimate was wrong in a more interesting
way: it predicted "a few hundred bytes" for the program, which is true of the logic and false of
the program, since the payload's docstring dominates it as it dominates every payload here. At
6.8 KB assembled it is the third-smallest of twenty-one, and what the test asserts is the decision
that actually mattered — the vendored table is **not** in the program, because the alternative
design would have put ~3 KB on every call to compute what a local function already computes.

Verified two ways. The effort's own
[`check_weburls.py`](done/024-documentation-urls/check_weburls.py) established the one claim no
stub can — `<root>.ui.weburls` really is in `sys.modules` on a working install, alongside 308
other UI modules, with the vendored copy matching the installed extension exactly — and provoked
the fallback with a **really refused socket** rather than a mocked exception, which is the whole
novel mechanism end to end. Both tools then gained a smoke item: 25 items, 0 failed, 0 skipped,
43.4 s, against Blender 5.1.0 and MPFB 2.0.17 at blender_mcp's slow 0.25 s tick. The unit suite
went from 747 tests to 799.

## [FR 025](done/025-character-presets/README.md) — saving, listing and loading character presets

An agent driving the previous twenty-two tools could build a character and change it, but could not
**keep** one: everything it assembled existed only in the running `.blend`. Three tools close that.
`mpfb_list_presets` names the presets in MPFB's user config directory, `mpfb_save_preset` writes the
current character into that namespace, and `mpfb_create_human_from_preset` builds a new character
from one. MHM stayed out of scope, as the request said and as NEXT_STEPS had asked: it needs two
settings keys `get_default_deserialization_settings()` does not contain and its asset matching is a
different problem.

**The durable part is the first tool in the package whose effect outlives the `.blend`.** Everything
before this was undoable with Blender's undo stack or by deleting an object; a preset file is
neither, there is no confirmation channel across MCP, and a caller cannot see the directory. So
[mutating-tools.md](../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)
gained the section that says what such a tool owes: address the artifact by **name, never a path**;
validate that name on this side of the socket, because a name that becomes a path is a shape and
not a vocabulary; refuse to overwrite by default, carrying the existing file's size and age so the
decision can be made from the response; and put the absolute path in **every** answer, refusals
included. The third reason for name-not-a-path was the one that would otherwise have been found the
hard way, and the live check confirmed it: `deserialize_from_json_file()` extracts the name with a
regex whose match it never checks, so any other path shape raises `AttributeError: 'NoneType'
object has no attribute 'group'` from inside MPFB, with nothing in the message about what the
caller did wrong.

**One rule now lives on both sides of the socket, which is new and is meant to stay rare.**
`src/mpfbmcp/preset_names.py` holds the name whitelist for the tool modules and
`codegen/shared/preset_files.py` restates it as the last statement before `open()`; two copies are
warranted only because the tool side cannot reach Blender and a gap between them would be silent —
a preset written under a name that cannot be loaded back. `tests/test_codegen.py` runs both over one
table of names and compares the *sentences*, not only the verdicts. The rule is deliberately
stricter than MPFB's, which rejects only an empty name and one containing a space, and strictness
runs one way: every name accepted here is one MPFB's panel would accept too. Where the reverse
fails — a preset saved by hand under a name these tools refuse — `mpfb_list_presets` flags it as
`addressable: false` rather than leaving a caller to meet it as a refusal.

**Three MPFB behaviours were followed rather than improved on, and one message was not.** The
`material_instances` default follows MPFB's preset *panel* (`ENHANCED`) rather than
`get_default_deserialization_settings()` (`NEVER`) — a third instance of the coercion rule FR 011
established for skins, with both values reported. The generated-Rigify `WARNING` MPFB's two saving
operators emit is deliberately **not** reproduced: `_populate_human_info_with_rig_info()` handles
the case, infers the meta rig and records that, so nothing fails; the description says once that a
generated rig does not round-trip and the response shows `rig_identified_as` beside `rig_saved_as`
on the call where it happened. `mpfb.human_from_presets`' three UI conveniences were dropped, and
entering edit mode across the socket is the reason for two of them rather than a preference. What
was *not* followed is MPFB's error text: `ValueError("Could not identify rig type. Custom rigs
cannot be serialized.")` is false — a custom rig still in user data serializes as `custom.<name>` —
so the condition is checked before anything is written and refused with the real cause.

**A seventh shared fragment, and the reason a mid-way failure is reported rather than prevented.**
`preset_files.py` is what keeps the three tools agreeing about names and paths. What was considered
and rejected is a pre-flight rig check: `_check_add_rig()` raises for a rig this Blender does not
have, *after* `create_human()` has run, so the failure leaves a naked character in the scene —
preventing it would mean either duplicating `rig_lookup.py`'s resolution or paying its 8.5 KB on
every call, for one of several failure modes. So the whole deserialization runs inside a `try` and
`objects_created` names what was left behind, which covers the rig case and every other partial
failure with it. Likewise an asset a preset names and this Blender lacks: MPFB logs a warning and
carries on, so every asset is resolved *before* the call and `unresolved_assets` reports the misses.

**The description ceiling was raised from 52,200 to 59,200** and the schema ceiling from 9,000 to
10,400, both with the reason beside them. The catalogue tool came in at 1,885 B against a 2,341 B
average, as a catalogue tool should; the two acting tools did not, and
[tool-interface.md](../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget)
now records what an above-average description has to be able to say for itself —
`mpfb_create_human_from_preset` is the only tool in the package with seven optional arguments, each
of which changes what is built and none of which a caller can discover from a response.

**The `save_clothes` defect was confirmed and filed.** `serialize_to_json_string(basemesh,
save_clothes=False)` never reads the argument, so clothes are always saved and the documented
default describes behaviour that does not exist. Provoked rather than read, per FR 019's rule: one
dressed character serialized twice in the same call, with the argument as the only difference,
produced **byte-identical strings** both carrying the garment. It is item 7 in
[`MCP_DISCOVERED_BUGS.md`](../../mpfb2/features/MCP_DISCOVERED_BUGS.md), with the note that changing
the default to `True` alongside the implementation would keep every existing caller where it is.
Of the request's two lesser candidates, one was confirmed and **not** filed —
`get_default_deserialization_settings()` really does omit the two override keys
`deserialize_from_dict()` honours, which reads as a distinction between required and optional keys
rather than as an omission — and the other became the third reason for name-not-a-path above.

Verified two ways. The effort's own
[`check_presets.py`](done/025-character-presets/check_presets.py) ran the full round trip against
Blender 5.1.0 and MPFB 2.0.17 — a character with a rig, a garment, a body part and a non-default
`ENHANCED` skin, saved, listed, rebuilt, and compared field by field through the package's own read
tools — plus the two claims no stub can reach: that MPFB's own preset list holds the name this
package wrote and that `deserialize_from_json_file()` rebuilds a character from the same file with
no tool in the path. 31 passed, 0 failed, 0 skipped, 49.5 s, and every preset it wrote deleted
again. All three tools then gained a smoke item: 28 items, 0 failed, 0 skipped, 50.2 s. The unit
suite went from 799 tests to 886.

That run also found a **pre-existing bug in the smoke harness's own cleanup**, which is worth
recording because nothing before this effort could have provoked it: `verification/harness.py`
drained its six datablock collections in turn, and an `ENHANCED` skin's texture is held by a node
group held by a material, so the image only reached zero users after `images` had already been
swept. The fix is a sweep that repeats over all six until a pass removes nothing; the ordering is
not fixable by reordering.
