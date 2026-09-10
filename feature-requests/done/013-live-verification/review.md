# Architectural review, after the first live run

Written after the session [FR 013](README.md) scopes, and citing it rather than arguing from
first principles. Twenty tools, ~10,600 lines of package code plus 303 KB of payload source, and
66.7 KB of tool descriptions existed before any of it had been measured or, for twelve of the
tools, run at all. This is the review
[FR-7](README.md#fr-7-produce-the-architectural-review) asks for. Every recommendation is
classified — **fixed here**, **request NNN**, or **rejected** with the reason — and all
twenty-two are collected in
[one table at the end](#every-recommendation-in-one-place).

Numbers come from [FR 012](../012-observability/README.md)'s per-call record (~1,400 calls) and
from [verification/measure.py](../../../verification/measure.py); everything about behaviour comes
from the eight checklists under [verification/](../../../verification/), whose full results are in
`verification/results/`. The final run was 78 checks passed, 0 failed, 2 skipped against a freshly
restarted Blender 5.1.0 with MPFB 2.0.17.

**The short version.** The tools are, overwhelmingly, correct: three claims that had only ever been
readings of MPFB's source turned out to hold exactly, and the three defects the run did find are
each a small mistake in reporting or guarding rather than anything structural. What the review has
to say is mostly about the *reasons* rather than the code — four decisions were argued against a
round-trip figure four times too high, two were justified by readings of MPFB that the running
install does not support, and two open questions about cost turn out to have had answers all along.
Every one of the decisions survives; several now have a better reason than they were given.

## What the run found, before anything else

Three defects, all in mpfb-mcp and all **fixed here** with a unit test that fails without the
fix. They are listed first because they are the answer to the question the whole request
opens with — whether twelve tools that had never run were actually correct.

**1. A body proxy did not hide the base mesh.**
[`payloads/add_asset.py`](../../../src/mpfbmcp/codegen/payloads/add_asset.py) guarded its
`Hide base mesh` modifier with `has_mask_for(basemesh, "body")`, an idempotence check that was
always satisfied: every basemesh MPFB creates already carries a `Hide helpers` MASK modifier on
the vertex group `body`. The two differ only in `invert_vertex_group`. So the guard fired on
every call, the modifier was never added, and a character wearing a body proxy was rendered
with both meshes overlapping — while `proxy_extras.basemesh_hide_modifier_present` reported
`true`, which is the same mistake told back to the caller as reassurance. Nothing on this side
of the socket could have caught it, because the stub basemesh had no modifiers at all; the stub
now carries `Hide helpers`, and the existing proxy test failed the moment it did.

This is also the only finding that contradicted a *documented decision*: the payload's
docstring says it follows `HumanService._check_add_proxy()`, and it did not.

**2. `mpfb_get_macro_details` reported two lists in two vocabularies and told the caller to
compare them.** `macro_target_stack[].shapekey_name` was encoded (`$md-$as-$fe-$yn`);
`current_macro_shapekeys` was decoded (`macrodetail-asian-female-young`). The docstring says
"Compare with `macro_target_stack`: if they disagree, the properties have been changed without
a recalculation" — a comparison that reported drift on every healthy character in existence.
Both now report the names the shape keys are actually stored under, with
`current_macro_shapekeys_decoded` alongside for reading. `mpfb_set_macro_details`'
`macro_shapekeys_before`/`_after` and the `shapekeys_added`/`_removed` derived from them moved
the same way, and for an additional reason: a name from those fields should be one a caller can
look up on the mesh.

**3. Two `[]`s that meant "not computed".** `mpfb_symmetrize_targets` under `dry_run: true`
reported `targets: []` per changed category, where the real run reports the shape keys it
touched — which files a write would touch is only knowable by doing the write. And
`mpfb_remove_asset`'s `mask_modifiers_present`, the field a caller reads when told to remove an
orphaned mask by hand, listed *every* MASK modifier on the basemesh, which on a real character
means MPFB's own `Hide helpers` and, with a proxy, `Hide base mesh` — modifiers that must never
be deleted, named beside the one that should be. The first is now `null`; the second is
filtered to the `Delete.` prefix `unload_mhclo_asset()` itself derives.

Both are the same rule, and it is
[FR 006](../006-list-targets/README.md)'s: `[]` means "none of them" and `null` means "not
known". It survived twelve tools' worth of review and broke twice in practice, which is an
argument for stating it in
[Response shape](../../../specifications/responses.md#response-shape) rather than leaving it as
a habit. **Fixed here**, in the specification as well as in the code.

## Does the response shape work in practice?

Yes, with two qualifications, both about *naming* rather than about structure.

Twelve mutating tools report a prior state, a new state and a list of consequences, and having
read all twelve off real characters, the structure earned its cost every time: the fields the
checklists actually used were the consequence lists (`materials_destroyed`, `warnings`,
`mesh_assets_not_rigged`, `shapekeys_removed`, `proxy_extras`, `delete_group_applied_to`), and
they were used because they say things no caller could otherwise see. `warnings` in particular
carried the two most useful sentences of the whole run — that a garment was attached with no
rig, and that a generated Rigify rig will not re-handle an asset added afterwards.

**The "it happened" flag has five different names.** `added` (`mpfb_add_asset`,
`mpfb_add_rig`), `applied` (`mpfb_set_skin`, `mpfb_set_asset_material`, `mpfb_set_targets`),
`removed` (`mpfb_remove_asset`), `generated` (`mpfb_generate_rigify_rig`), `refit_performed`
(`mpfb_refit_human`). Each reads well in its own response and the set does not read well at
all: the harness got it wrong three times in one afternoon, on three different tools, and each
time the wrong answer was `None` rather than an error. `found`/`ready`/`blocked_by` are uniform
and were never mis-read. **Recommendation: a uniform `performed` boolean beside the tool's own
verb, not instead of it** — scoped as a request, because adding a field to twelve responses is
exactly the kind of change FR 013 says must not be folded into a bug hunt. **Request: deferred,
see [What this run leaves scoped](#what-this-run-leaves-scoped).**

**`asset_info.material_source` is one key filled from two different properties.** For a skin it
is `material_source`; for anything else it is `alternative_material`, resolved against a
different asset subdir. A caller reading it back after `mpfb_set_asset_material` — which
[FR 011](../011-skin-and-materials/README.md)'s checklist explicitly asks for — has to know
the object's type to know which property they are looking at. It is documented in the payload
and not in the tool docstring. **Fixed here**, in the docstring.

On `null` versus `[]`: distinguishable everywhere the run looked, *after* the two fixes above.
`delete_group_name: null` for an MHCLO declaring no delete vertices, `rigged_to: null` for a
garment attached before there was a rig, and `pack: null` for an asset lying directly in an
asset root are all live-observed and all correct — those three are the cases the rule was
written for, and they held.

## Is the duplication a risk or an economy?

Countable, and now diffed rather than counted. Across the twenty payloads: subject resolution
appears in 11, the active-object/selection restore in 8, the `bpy.context.mode` precondition in
6, a `blocked()` helper in 6, a `property_value()` helper in 6, and three shared fragments exist
for the cases already judged worth sharing.

FR-7 asks the right question — not whether the code repeats but whether any two copies have
**drifted** — so every function defined at module level in more than one payload was parsed,
stripped of its docstring, normalised through `ast.unparse` and compared. Nineteen names have
two or more copies. **Sixteen are byte-identical after normalisation**: `as_path` (7 copies),
`property_value` (6), `object_names` (3), `mesh_assets_of` (3), `encoded` (3), and eleven
others. Three differ, and none of the three is drift in the sense that matters:

- **`blocked()`, six variants.** Every one has the same shape — `found`, `ready`, the tool's own
  verb set to false, `blocked_by`, `message` — and differs only in which of that tool's own
  fields it nulls out. That is not duplication of a concept; it is one convention applied six
  times, and merging it would require a mechanism for "this tool's null response" that is
  bigger than the six copies. **Rejected.**
- **`rig_refit_blocker()`, four copies, two message variants.** The *condition* — a generated
  Rigify rig with no meta rig left — is identical in all four. The message differs by tense
  between `refit_human.py` ("could not be refitted; its mesh assets were") and the three tools
  that predict rather than report ("cannot be refitted to the new body shape ... before
  generating"). Both are correct for their call site. This is the closest thing to a real
  fragment candidate in the census: one condition, four copies, and a message that must vary.
- **`modifier_value()`, two implementations.** `get_target_stack.py` threads a `present`/
  `value_of` pair of closures; `symmetrize_targets.py` resolves the stored name directly. Both
  handle the encoded-name case, and the run confirmed they agree where it matters: FR 008's
  round trip set a modifier through `mpfb_set_targets`, read it on MPFB's own slider, moved the
  slider, and read it back through `mpfb_get_target_stack` — 0.62 and 0.4 respectively, both
  exact. Two implementations of one reading, agreeing today.

So: **an economy, not a risk, today** — with one qualification the census makes precise. Nothing
has drifted, but `rig_refit_blocker` and `modifier_value` are the two places where a fourth
shared fragment would pay, and both are one careless edit away from the failure
`rig_lookup.py` was created to prevent. FR 013's [one exception](README.md#what-this-effort-may-change)
does not apply — the copies still agree — so this is **a request, not a fix here**.

The census itself is worth keeping: it is thirty lines of `ast` and it turns "have these
drifted?" from an afternoon into a command. **Request**, with the census script.

## Does the tool surface fit its consumer?

Measured: **20 tools, 66.7 KB of descriptions plus 8.9 KB of parameter schemas — 75.6 KB, about
18,900 tokens** loaded by an MCP client before any work happens. The four largest are
`mpfb_list_assets` (6.2 KB), `mpfb_list_targets` (5.3 KB), `mpfb_add_asset` (5.1 KB) and
`mpfb_get_object_info` (4.7 KB). FR 013 estimated 58.5 KB and ~14,600 tokens; it has grown since.

Reading them against what the run actually needed, the descriptions divide into three kinds:

- **Needed at call time, and load-bearing.** Which of `path` and `fragment` to pass and that
  exactly one is required; that `asset_type` is required and MPFB's own default mislabels six of
  eight types; that `skin_type` defaults to `MAKESKIN` and not to the signature's
  `ENHANCED_SSS`; that `direction` has no default; the ordering constraint. Every one of these
  was needed by the harness, which is a fair proxy for a caller, and several were needed
  *because the answer is surprising*. Keep.
- **Needed at call time, and currently missing.** Three tools' key names cost the harness a
  round trip each because the description names the concept and not the key — `objects_removed`,
  `rig_object_name`, `asset_info.material_source`. The descriptions are long and still do not
  reliably name the fields. That is an argument about *what* they contain, not about size.
- **Rationale, and it does not belong here.** Roughly a third of the largest four is explanation
  of MPFB's behaviour rather than instruction for the call: why the label collision happens, why
  `refresh` is cheaper than it looks, what `pack_ambiguous` means about the asset packs, how
  `_modelsubpanels` builds its category names. All of it is true, all of it is useful, and none
  of it changes what a caller passes. It belongs in
  [specifications/](../../../specifications/) or behind the `mpfb_search_docs` tool
  [vision.md](../../../specifications/vision.md) already plans.

**Recommendation: trim rationale out of the four largest descriptions and put the field names
in, targeting roughly 45 KB.** Explicitly *not* done here — FR 013 defers description trimming,
and rightly: it is a change to twenty strings whose effect is only observable against a real
client. **Request: deferred.**

## Is the tool granularity right?

Building Character A takes seven calls: create, macro, targets, rig, clothes, generate, skin.
The run says two things about that.

**No pair is always called together except one, and it is already documented rather than
composed.** `mpfb_add_rig` with a `rigify.*` identifier is *always* followed by
`mpfb_generate_rigify_rig`, and the two are deliberately separate because the clothes go on
between them — which the run confirmed is not merely a rule but the difference between a
garment with 285 weighted vertices and one with none. A composite would have to take the asset
list as an argument, at which point it is a character builder and not a tool. **Rejected**, and
the reason is now observed rather than argued.

**The one composite worth considering is `mpfb_create_human` + `mpfb_set_macro_details`.** Every
character in this session was created and then immediately given a phenotype, and
`mpfb_create_human` already takes the macro dict — so the composite exists; what is missing is
that the two tools' argument shapes differ. That is a docstring problem, not a catalogue one.
**Rejected**, with the note that `mpfb_create_human`'s description (930 bytes, the smallest of
the twenty) is the one that could usefully grow.

## The seven candidate MPFB defects

[FR-6](README.md#fr-6-confirm-the-seven-candidate-mpfb-issues-before-filing-them) asks for each to
be confirmed against the running install before being filed.
[verification/check_mpfb_issues.py](../../../verification/check_mpfb_issues.py) provokes each one, so
this is re-runnable against a future MPFB rather than a snapshot of an opinion.

**The one found by accident, and the worst of the set.** A user target whose filename is over 56
characters **prevents MPFB from loading at all**. `_modelsubpanels.py` registers each synthesized
modeling category as a Scene property named `"custom_" + name` at module import time; Blender
rejects an identifier over 63 characters with a `ValueError`; nothing catches it, so it propagates
out of MPFB's `register()`. This session hit it by leaving a probe target on disk across the Blender
restart the session needed — MPFB did not come back. The sharp form is that `TargetService`'s own
name *encoding* starts above 60 characters while registration breaks above 56, so an encoded user
target cannot exist in a scanned directory at startup at all.

Two things follow. It is the first thing [FR 019](../019-file-mpfb-defects/README.md) should
file. And it is a hazard this repository created on somebody's install, so
`verification/fixtures.py` now carries `SAFE_AT_STARTUP`, the long probe is installed and removed
within a single checklist run, and the defect is reproduced by attempting the registration directly
rather than by breaking an add-on.

**Confirmed from the original seven, and worth filing:**

- **A gzipped custom target is addressed under two different names.** For
  `mpfbmcp_probe_vwide.target.gz`, `ui/model/_modelsubpanels.py`'s
  `os.path.basename(target).replace(".target", "")` yields `mpfbmcp_probe_vwide.gz` while
  `TargetService.filename_to_shapekey_name()` yields `mpfbmcp_probe_vwide`. Confirmed in full,
  against a Blender restarted with the file installed: setting MPFB's own slider to 0.5 and the
  catalogue's name to 0.7 leaves **both** shape keys on one mesh, at two values. One file, two
  targets.
- **`unload_mhclo_asset()` deletes whatever object it is handed.** Handed an ordinary cube that is
  not a MakeHuman object at all, it deleted it without complaint and without raising. This is why
  `mpfb_remove_asset` refuses by type before calling it.
- **`set_character_skin()`'s five-`if` dispatch destroys materials on a typo — and is quieter than
  FR 011 described.** `"MAKSKIN"`, one letter wrong, deleted every material on the character and
  built nothing. FR 011 expected a `ValueError` from `create_and_assign_material_slots()`; that
  happens only when `material_instances` is on, and arrives as `AttributeError: 'NoneType' object
  has no attribute 'copy'`. With instancing off — the default for three of the five types,
  `MAKESKIN` included — it raises **nothing at all**. A silent destruction, not a misleading
  traceback, which is a stronger argument for the vocabulary check `mpfb_set_skin` puts in the tool
  module than the one that motivated it.
- **`alternative_materials_for_asset()`'s `exclude_default` is accepted and never read.** Identical
  results with and without it, the asset's own material present in both.

**Refuted outright, twice.** `RigService.identify_rig()` **cannot** return `None`: it ends with an
`if guessed_rig is None:` block assigning `"unknown"`, `"rigify.unknown"` or
`"rigify_generated.unknown"`, and provoked against an armature matching nothing it returned
`"unknown"` while `MPFB_OT_GenerateRigifyRigOperator.poll()` returned `False` rather than raising.
And `AssetService.invalidate_alternative_materials_cache()` **exists** and clears both cache dicts —
the staleness is real because nothing calls it, not because it cannot be cleared, which is what
makes [FR 018](../../018-alternative-material-refresh/README.md) possible at all.

A third defect was found while provoking the first of those, and is worth filing on its own:
`ObjectService.object_is_rigify_metarig()` reads `blender_object.pose.bones` without checking, and
an armature object created through `bpy.data.objects.new()` has `pose` set to `None` until the
depsgraph has seen it — so `identify_rig()` raises `AttributeError` on it.

**Refuted in part, and it costs this project a documented reason:** *"three disagreeing proxy code paths"*
is two, not three. `add_mhclo_asset()` alone and `HumanService._check_add_proxy()` genuinely
differ, and visibly: no `Hide base mesh` modifier, six fewer vertex groups, and `scale_factor` left
at `1.0` instead of the character's `0.1`. But `_check_add_proxy()` and the asset library's proxy
operator produced **identical state on every field compared** — masks, modifiers, vertex-group
count, materials, scale factor, object type, `asset_source`, corrective shape keys. The operator is
a *duplicated* implementation, not a divergent one.

The decision that rested on this survives, and for a better reason than it had: what makes
following `_check_add_proxy()` load-bearing is not that three paths disagree but that the *obvious*
implementation — the service function whose name matches the operation — is the one that produces
a different character. That is a stronger argument, and
[Where MPFB's own code paths disagree](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)
is corrected to say it. **Fixed here**, in the specification.

The proxy-operator duplication is still worth filing, as duplication rather than as divergence:
two implementations that agree today are one edit from not agreeing, which is the same argument
this project made for `codegen/shared/rig_lookup.py`.

## What the harness cost, and what it is worth

[verification/](../../../verification/) is about 2,400 lines: a harness, a fixture module, eight
checklist scripts, a measurement script and a runner. FR 013 calls it "enabling, and not a goal
in itself", and the run bears that out in a specific way worth recording, because it is the
argument for building it at all.

**Roughly a third of the first-pass failures were the harness's own**, and every one of them was
a wrong *field name* — `rig_added` for `added`, `rig_name` for `rig_object_name`,
`removed_object_name` for `objects_removed`, `changes` for `changed`, `material_name` for
`fragment`, `shapekeys` for `targets`, `asset_info.alternative_material` for
`asset_info.material_source`. A human doing this by hand would have made the same mistakes and
would have had no way to tell them from real failures except by looking. That is the strongest
evidence in this session for [FR-1](README.md#fr-1-a-harness-that-can-be-run-again): a wrong
field name in a script fails loudly and is fixed once; the same mistake in a manual session is
indistinguishable from a defect, and is what makes such a session expensive.

**Three checks failed because the stubs were kinder than Blender**, which is the other half of
the same point. The basemesh stub had no modifiers at all, so the `Hide base mesh` defect could
not be expressed; adding MPFB's real `Hide helpers` to it broke three existing tests, two of
which were the tests being kind and one of which was the defect. The discipline that a stub
reproduces MPFB's behaviour including the inconvenient parts is not a style preference — it is
the only thing that lets a live finding be pushed back down into the suite.

**Two checks cannot be automated and are not pretending to be.** Anything depending on
`ui/model/_modelsubpanels.py`'s category table needs a Blender started with the file already in
place, since the table is built at module import time. Both are marked `[ ]` with the reason
rather than approximated, per FR 013's requirement that a half-finished checklist honestly marked
beats a fully-ticked one where two items were inferred.

## Do the three payload-count-driven decisions still hold?

All three, and one of them by a much larger margin than the argument that produced it. The
numbers below are from [verification/measure.py](../../../verification/measure.py) (three runs,
median reported, first call separate) and from ~1,400 recorded calls in FR 012's index.

**Every figure here was taken twice, on either side of a Blender restart, and they agree**: the
empty round trip 250 ms and 252 ms, `mpfb_get_status` 506 ms and 506 ms, the batched thirty
3,639 ms and 3,625 ms against 98,428 ms and 98,322 ms unbatched, one asset 2,779 ms both times, and
the five skin types within 33 ms of each other in both runs. The figures below are the fresh-Blender
run; the first run's are within 1% of them except where noted.

### The round-trip baseline, re-measured

**FR 005's ~1.0 s is roughly four times too high.** An empty program — a `result = dict(ok=True)`
sent through the same `send_code()` every tool uses — round-trips in **250 ms**, with a spread of
2 ms across four runs. `mpfb_get_status`, which does real work but no geometry, is **506 ms**;
`mpfb_list_objects` **504 ms**; `mpfb_create_human` **383 ms** as a mean over 282 recorded calls.

FR 005's figure was taken once, on one tool, on a cold asset library, and every decision citing
"the ~1.0 s socket round trip" was therefore arguing against a number that is mostly *not* the
socket. **The socket is 250 ms.** That does not reverse any of the three decisions — as below,
each survives on the corrected number — but it is worth saying plainly, because "the round trip
dominates" was the shape of the argument and it is false.

One caution the record itself supplies. Midway through the session, `add_rig` moved from ~2.2 s to
~8.0 s for about fifteen minutes and then back, with small probes unaffected throughout and no
change to the program. Every figure here is a median taken outside that window, and the maxima in
the index (`add_rig` max 8.1 s against a mean of 2.8 s over 114 calls) are what it looks like.

### Where a call's time goes

| Payload | Program | Compile | Share of a real call |
|---|---|---|---|
| `create_human.py` | 2.3 KB, 60 lines | **0.10 ms** | 0.03% of 383 ms |
| `get_status.py` | 7.3 KB, 152 lines | **0.30 ms** | 0.06% of 506 ms |
| `add_asset.py` | 41.2 KB, 867 lines | **1.99 ms** | 0.07% of 2,773 ms |
| `set_targets.py` | 50.4 KB, 1,176 lines | **3.09 ms** | 0.09% of 3,288 ms |

**Compile time is negligible and the question is closed.** The largest program mpfb-mcp sends —
1,176 lines, most of it comments and docstrings — compiles in under four milliseconds, about a
thousandth of the call it belongs to.
[Readability and developer experience are prioritized](../../../specifications/architecture.md#readability-and-developer-experience-are-prioritized)
cost 0.1%, and FR 013 asked for this to stop being an open question. It has.

What is *not* negligible is a third component neither FR 012 nor FR 013 anticipated. The three
tools that share `codegen/shared/target_categories.py` are the three slowest non-import tools in
the catalogue — `mpfb_set_targets` 3,288 ms, `mpfb_symmetrize_targets` 2,614 ms,
`mpfb_get_target_stack` 2,275 ms (means over the session) — while `mpfb_get_macro_details`, which
reads comparable data through no fragment at all, is **720 ms**. The fragment rebuilds MPFB's
category table by walking the target directories on **every call**, because
`ui/model/_modelsubpanels.py` builds its own copy at module import time and cannot be asked. That
is ~1.5-2 s per call, and it is the largest single cost in this package that is neither transport
nor MPFB doing geometry. **Request**, not a fix here: the obvious answer is a per-session cache
inside Blender, and caching is exactly the kind of change that must not be made during a bug hunt.

### The batching claim

Thirty modifier changes, one call against thirty:

| | Cold (targets not yet on the mesh) | Warm |
|---|---|---|
| One `mpfb_set_targets` call | **3,625 ms** | 3,451 ms |
| Thirty calls | **98,322 ms** | 98,409 ms |

**Twenty-seven times, and the reason is not the one the decision gave.** Thirty round trips are
30 × 250 ms = 7.5 s of transport; the other 91 s is thirty rebuilds of the category table above.
FR 008 made batching mandatory on the grounds that "a round trip costs ~1 s and setting a target
costs milliseconds" — the conclusion is right and the premise was wrong, and the corrected premise
makes it *more* forceful, not less. Reading target files off disk is **174 ms** of the cold batch,
so the disk is a rounding error here too.

**Decision holds**, and
[A batched mutating tool resolves before it writes](../../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes)
now has a measured reason.

### Per skin type

| `skin_type` | First call | Median |
|---|---|---|
| `MAKESKIN` | 2,271 ms | **2,271 ms** |
| `ENHANCED` | 2,505 ms | **2,292 ms** |
| `ENHANCED_SSS` | 2,517 ms | **2,295 ms** |
| `LAYERED` | 2,283 ms | **2,285 ms** |
| `GAMEENGINE` | 2,271 ms | **2,267 ms** |

**`LAYERED` is not the outlier**, and FR 011 expected it to be, on the strength of MPFB documenting
it as unsuitable for animation. All five are within 28 ms of each other (33 ms in the first run). What MPFB warns about is
*render* cost, not build cost, and `mpfb_set_skin`'s docstring should not imply otherwise. The two
enhanced types are ~30 ms slower and pay another ~220 ms on their first call, which is the
settings-file copy and the node-group import. **Fixed here**, in the docstring.

### One asset per call

**2,779 ms median** to equip one garment (four assets, 2,566-3,008 ms), identical to the digit in
both runs, against a 250 ms round trip. The transport is **9%** of the call, so batching asset loads would save at most that — and
would cost the all-or-nothing semantics `mpfb_set_targets` needs a `resolution_errors` channel to
provide. **Decision holds**, on the corrected baseline rather than the one it was argued against.

### The refit-by-default in `mpfb_set_macro_details`

A macro change with `refit: false` is **1,265 ms**; with `refit: true`, **1,268 ms** on an
undressed character. A bare `mpfb_refit_human` is **759 ms**, of which 250 ms is transport. So on a
bare character the refit is nearly free and the default costs nothing; on a dressed one it is the
difference between a character that looks right and one that does not (FR 010's run: the garment's
vertex fingerprint does not move until the refit runs). **Decision holds**, and it was the one of
the three least in doubt.

## What this run leaves scoped

Five requests, written before this one closes so the moment is not lost. None is a fix, and all
five were deliberately kept out of this effort: folding a refactor into a bug hunt makes every
finding ambiguous about which change caused it.

1. **A uniform "it happened" flag across the twelve mutating tools.** Five different names today;
   the harness got it wrong three times. Add `performed` beside each tool's own verb.
2. **A fourth shared code-generation fragment**, for `rig_refit_blocker()` (4 copies) and
   `modifier_value()` (2 implementations), plus the drift census script that found them.
3. **Trimming the tool descriptions**, from 66.7 KB toward ~45 KB, by moving rationale into
   [specifications/](../../../specifications/) and putting the response *field names* in.
4. **Migrating `payloads/list_targets.py` onto `codegen/shared/target_categories.py`** — already
   in [NEXT_STEPS.md](../../NEXT_STEPS.md#modeling), and cheapest now that re-verifying it is one
   command rather than a session.
5. **Filing the six confirmed MPFB defects** against `../mpfb2`, with the reproduction script
   rather than a description.

## Every recommendation, in one place

| # | Recommendation | Classification |
|---|---|---|
| 1 | The body-proxy hide modifier is never added | **Fixed here** |
| 2 | `mpfb_get_macro_details`' two lists are not comparable | **Fixed here** |
| 3 | A dry run's `targets` is `[]` where it means `null` | **Fixed here** |
| 4 | `mask_modifiers_present` names modifiers a caller must not delete | **Fixed here** |
| 5 | `scale_assumption` for an ordinary character is `METER`, not `DECIMETER` | **Fixed here** (four places) |
| 6 | "Three disagreeing proxy code paths" is two | **Fixed here** (specification) |
| 7 | `null` vs `[]` stated in [Response shape](../../../specifications/responses.md#response-shape) | **Fixed here** (specification) |
| 8 | A candidate MPFB defect must be confirmed before it is filed | **Fixed here** (specification) |
| 9 | `asset_info.material_source` is one key from two properties | **Fixed here** (docstring) |
| 10 | `LAYERED` is not slower to build than the other four | **Fixed here** (docstring) |
| 11 | Live verification is a named, re-runnable step | **Fixed here** ([verification/](../../../verification/)) |
| 11b | A probe target that can stop MPFB loading must never be left on disk | **Fixed here** (`fixtures.SAFE_AT_STARTUP`) |
| 12 | A uniform "it happened" flag across twelve tools | **[FR 014](../014-uniform-performed-flag/README.md)** |
| 13 | A fourth shared fragment, and the drift census | **[FR 015](../015-fourth-shared-fragment/README.md)** |
| 14 | Trim the tool descriptions from 66.7 KB toward ~45 KB | **[FR 016](../016-trim-tool-descriptions/README.md)** |
| 15 | The category-table rebuild costs ~2 s per call | **[FR 017](../017-category-table-cost/README.md)** |
| 16 | `mpfb_list_asset_materials` should be able to rescan | **[FR 018](../../018-alternative-material-refresh/README.md)** |
| 17 | File the five confirmed MPFB defects, including the one that stops MPFB loading | **[FR 019](../019-file-mpfb-defects/README.md)** |
| 18 | Merge `blocked()`'s six variants | **Rejected** — one convention applied six times, not one concept duplicated |
| 19 | A composite `add_rig` + `generate_rigify_rig` | **Rejected** — the clothes go between them, which the run confirmed matters |
| 20 | A composite `create_human` + `set_macro_details` | **Rejected** — the gap is a docstring, not a tool |
| 21 | Batch `mpfb_add_asset` | **Rejected** — transport is 9% of the call |
| 22 | Instrument the generated program to split a call's time | **Rejected** — measured ad hoc instead, and the answer closed the question |
