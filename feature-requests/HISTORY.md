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
