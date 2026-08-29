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
