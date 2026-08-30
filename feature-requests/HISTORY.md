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
[how generated code addresses objects](../specifications/architecture.md#how-generated-code-addresses-objects),
by Blender object name, listing scoped to the scene while resolution is scoped to the file, with
"exists elsewhere" a distinct answer; and
[how tools report the asset behind an object](../specifications/architecture.md#how-tools-report-the-asset-behind-an-object),
the fragment-plus-absolute-path pairing and the type-varying rather than unioned shape.
[Validate before crossing the socket](../specifications/architecture.md#validate-before-crossing-the-socket)
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
[How tools name things that can be added](../specifications/architecture.md#how-tools-name-things-that-can-be-added)
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
[How tools bound a large answer](../specifications/architecture.md#how-tools-bound-a-large-answer),
the convention [FR 006](done/006-list-targets/README.md) inherits.

Each entry names the asset three ways, and the live pass sharpened what each is for: `path` is what
`add_mhclo_asset()` and `set_character_skin()` actually take, `fragment` is the portable identifier
MPFB writes onto the resulting object as `asset_source` — confirmed string-equal for every asset
added — and `object_type` doubles as `add_mhclo_asset()`'s `asset_type` argument, which defaults to
`"Clothes"` and so silently turns hair into clothes when omitted. FR 004's
[naming convention](../specifications/architecture.md#how-tools-name-things-that-can-be-added) grew
a clause for that.

`pack` is the project's first *derived* field: MPFB records no link from an installed file back to
the pack that installed it, so the attribution is a match of the asset's containing directory name
against the installed packs' metadata. That earned the second new convention,
[How tools report a derived rather than recorded fact](../specifications/architecture.md#how-tools-report-a-derived-rather-than-recorded-fact),
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
[How tools name things that can be added](../specifications/architecture.md#how-tools-name-things-that-can-be-added)
with a clause about identifiers that usually equal something the caller already has.

The one thing the request had wrong was sections. It assumed a section is either a `target.json` one
or a synthesized user one; on the verification install **8 of 27 are both**, and MPFB's own panel
merges a user directory into the bundled section of the same name rather than keeping the two apart.
So `source` took a third value, `"both"`, and asking for such a section returns its bundled
categories *and* that directory's user targets.

Two conventions were folded back, both new:
[Reading MPFB's data files directly](../specifications/architecture.md#reading-mpfbs-data-files-directly)
— locate through `LocationService`, guard the read, treat a missing file as an answer, and report
where a large file is rather than what is in it — and
[A tool may report a fact MPFB's own UI does not show](../specifications/architecture.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show),
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
[how a mutating tool takes its subject](../specifications/architecture.md#how-a-mutating-tool-takes-its-subject)
— it accepts any object in the character's family and names the one it actually modified, because
an agent that got a name out of `mpfb_list_objects` has no way to know which member owns a given
property;
[a mutating tool reports before and after](../specifications/architecture.md#a-mutating-tool-reports-before-and-after)
— the mutation-side counterpart of "an empty answer must never be ambiguous", covering the prior
values, the shape keys pruning removed, and what is now fitted to the old shape; and
[preconditions are answers](../specifications/architecture.md#preconditions-are-answers) — edit
mode and a mesh with no shape keys are ordinary situations, and MPFB meets the first with a bare
`assert` and the second with a log line saying it is "somewhat surprising".

A fourth clause settles a question `NEXT_STEPS.md` had carried since the start: whether
`mpfb_create_human` should take a macro-detail dict instead of eleven flat sliders. **It should
not**, and the reasoning is general enough to sit under
[Validate before crossing the socket](../specifications/architecture.md#validate-before-crossing-the-socket)
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
[architecture.md](../specifications/architecture.md#a-batched-mutating-tool-resolves-before-it-writes),
both new.
[A batched mutating tool resolves before it writes](../specifications/architecture.md#a-batched-mutating-tool-resolves-before-it-writes):
a batch of thirty changes with one typo in it applies **zero** of them, because a half-applied batch
leaves a character in a state neither the agent nor the user can describe and the response format
cannot usefully say which half landed. Batching itself is not a preference — a socket round trip
costs about a second while setting a target costs milliseconds — and the convention names
[FR 010](done/010-mesh-assets/README.md) as the case where that argument does *not* carry over, since
loading an MHCLO is seconds of real work.
[When mpfb-mcp models a concept MPFB's UI has but its services do not](../specifications/architecture.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not):
a modifier is not a `TargetService` idea at all, it lives in `target.json` and in a UI module, and
when a tool lifts one out of the UI the mechanics are reproduced statement for statement rather than
reinvented — `_set_opposed_modifier_value()` zeroes the opposing target *first*, and doing it the
other way deletes the wrong half of a pair when pruning is on.

Two existing conventions were amended.
[Validate before crossing the socket](../specifications/architecture.md#validate-before-crossing-the-socket)
gained the one exception to its "flat scalars, not a nested dict" clause: a batch is irreducibly a
list, and what compensates for a shape no schema checks is per-entry validation in the tool module —
including rejecting an unknown key, which is the commonest way a caller gets a dict-shaped argument
wrong and is otherwise silent — plus a per-entry `resolution_errors` channel in the response.
[A tool may report a fact MPFB's own UI does not show](../specifications/architecture.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show)
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
[A tool reports an ordering constraint it cannot enforce](../specifications/architecture.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
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
[How a mutating tool takes its subject](../specifications/architecture.md#how-a-mutating-tool-takes-its-subject)
gained the case where the resolved object is *not* the basemesh — `mpfb_generate_rigify_rig`
narrows to the character's `Skeleton` — and the case where the whole set is needed rather than the
first match. [A mutating tool reports before and after](../specifications/architecture.md#a-mutating-tool-reports-before-and-after)'s
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
