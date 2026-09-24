# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## Expressions

**Scoped as two requests, in this order: [FR 026](done/026-face-units/README.md) (Done) landed the
face-unit layer — `mpfb_get_face_units` and `mpfb_set_face_units`. What remains is
[FR 027](027-expression-library/README.md) (Accepted): the saved-expression library, the stack that
applies it, and `mpfb_save_expression`, which turns a composed face into a file the library can
carry. Saving was queued here as a separate entry behind FR 027 and has been folded into it, since
neither half is useful without the other; see
[its requirements](027-expression-library/README.md#mpfb_save_expression--keep-a-composed-face).**

These are the `!ex-` prefixed shape keys. They depend on particular asset packs being installed.
Expressions should be a mix of functionality from the `src/mpfb/ui/create_assets/makeexpression`
and `src/mpfb/ui/apply_assets/useexpression` UI code hierarchies in MPFB. TargetService has
some functionality for working with expressions.

## Character summary

**Scoped as [FR 034](034-character-summary/README.md) (Accepted), ordered after FR 027.**
`mpfb_get_character_summary` answers in one call what currently takes five or six: phenotype, rig,
equipped assets, skin, the target rollup, and the face (face units and the expression stack). Each
section is read by the same implementation as its detailed tool, which means moving the reading
code of `get_macro_details`, `get_object_info` and `get_target_stack` into `bridge/.../shared/`.

<a id="one-basemesh-resolver"></a>

## One basemesh resolver

Fifteen bridge commands resolve "any object in the character's family, or the active one" to a
basemesh through `ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")`,
each inside a wrapper of its own (`_resolve`, `_resolve_basemesh`), and the copies are not the same
code even with their messages stripped. [FR 034](034-character-summary/README.md) moves the
`get_macro_details` copy into `shared/macro_reading.py` and leaves the other fourteen alone. This
effort would decide whether they should all share one resolver, whether the variations between them
are deliberate (some mutating commands may rightly resolve differently), and would record the
differences it finds either way.

## Visemes and lip sync

The rest of `FaceService`, deliberately excluded from both expression requests (see
[Not visemes](done/026-face-units/README.md#not-visemes)): `MICROSOFT_VISEMES` and `META_VISEMES`,
`load_targets`, `interpolate_targets` and `configure_lip_sync`.

This is speech animation rather than expression — a different vocabulary, different asset packs
(`visemes01` / `visemes02`), and a different propagation mechanism: `interpolate_targets` transfers
shape keys to child meshes through MHCLO vertex correspondence, which is not what a refit does. Note
that it matches shape keys by **bare** name, so it has never propagated the `!ex-` prefixed
expression keys.

`configure_lip_sync` additionally depends on the third-party `lip-sync` addon, maintained outside
the MakeHuman ecosystem, which is a dependency no tool in this package has yet.

## Loading poses

These come in two variants: BVH-style poses found via AssetService and json-style poses found
in the user config dir. The latter is loaded in an operator in the rigging ui hierarchy.

Both types should be supported, probably with different tool calls. 

## Finding, downloading and installing asset packs

**The URL is no longer the open question.** `mpfb_list_urls` reports `URL_ASSET_PACKS` (and
`URL_SYSTEM_ASSETS`), read live out of MPFB's own constants — see
[FR 024](done/024-documentation-urls/README.md), which landed for exactly this dependency.

What remains is the downloading and installing, and FR 024 changed its shape rather than only
unblocking it: **mpfb-mcp opens no network connection except the one to the add-on** is now a
[standing constraint](../specifications/architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on).
So this effort cannot simply fetch a pack. Two options, and the first is a bigger decision than it
looks: retrieval happens on the *Blender* side, which now means **a bridge command that opens an
outbound connection** — the add-on currently accepts a loopback connection and originates nothing,
so this would change what the extension does and what an extension reviewer is being asked to
approve, and it has to be argued explicitly rather than assumed. Or the client is handed the
address and the tool installs what the user has already downloaded. There is an operator for
loading a pack from zip in MPFB which can be used as inspiration for the second half either way.

## Exporting characters

Need to have a tool for exporting a character to, for example, fbx. This should involve 
similar procedures as is used in `src/mpfb/ui/operations/exportops` in MPFB.

<a id="mpfb-cannot-find-a-rigify-meta-rig-any-more"></a>

## File upstream: MPFB cannot find a Rigify meta rig any more

**`ObjectService.find_rigify_metarig_by_rig()` returns `None` for every generated Rigify rig on
current Rigify**, so MPFB believes no generated rig can be refitted — including one whose meta rig
is sitting in the scene, hidden, exactly as MPFB's own panel recommends.

The cause is one method call. MPFB scans for an armature whose
`data.get("rigify_target_rig")` is the generated rig, which is an **ID-property** lookup; Rigify
now stores `rigify_target_rig` as an **RNA property** on the armature data, so `data.keys()` is
empty and the scan matches nothing. `getattr(armature.data, "rigify_target_rig", None)` finds it.
Observed on Blender 5.1 with MPFB 2.x, generating through
`RigService.generate_rigify_rig(meta, meta_rig_action="hide")`.

The visible effect is that `mpfb_refit_human` answers `refit_performed: false` with
`refit_incomplete_reason` naming a missing meta rig, for a character that has one — and the three
modeling tools predict the same blocker when they refit. The answer is *conservative* rather than
wrong in the dangerous direction: it under-claims a refit rather than claiming one that did not
happen, which is the way round this package would choose if it had to choose.

**Found while migrating `refit_human` in
[FR 032](done/032-creation-and-modification-migrated/README.md), and deliberately not fixed
there**: that effort's rule is reproduction over improvement, because a tidy-up made during a
migration is indistinguishable from a defect in the comparison the migration rests on.
`bridge/test/tests/ppp_mutating/refit_human_test.py` asserts that the command **agrees with MPFB's
own lookup** rather than asserting a value, so it keeps passing when this is fixed and keeps
saying what it found in the meantime.

What to do: file it against mpfb2, and decide separately whether this package should route around
it. Routing around means reading the RNA property here, which is a rule about Rigify's data
layout living in two places — the thing `shared/refit_blocker.py` exists to prevent.

<a id="file-the-4-kb-chunked-read-against-blender_mcp"></a>

## File upstream: blender_mcp's 4 KB chunked read

**A standalone item, and no longer attached to anything.** It was to be filed "on the way out" in
the retirement stage; [FR 033](done/033-retire-the-generated-code-path/README.md) declined to carry
it, on the grounds that it is not an engineering task, gates nothing, and would be the half of a
deletion effort most likely to be dropped. It is worth doing on its own terms or not at all.

**What to report.** blender_mcp's `mcp_to_blender_server._service_clients()` does exactly one
`conn.recv(4096)` per timer tick and then returns, so a request arrives at one 4 KB chunk per
tick — 250 ms each while the add-on is busy, and 1 s each once five seconds have passed without a
request *finishing*, since bytes arriving do not reset its idle countdown. A request therefore
costs about 250 ms per 4 KB, or 1 s per 4 KB against the idle Blender an agent actually meets,
**regardless of what it asks for**: a 50 KB call is 3 s or 12 s of waiting before Blender has
read it. The fix is a loop.

**Why file it at all, now that it costs this project nothing.** It was the largest single cost in
this package for its whole first year — the full measurement and how it was taken are in
[HISTORY.md](HISTORY.md#fr-033--the-generated-code-path-retired) — and it costs every other user of
that add-on the same thing. The bridge's own transport drains its socket per tick rather than
reading one chunk, precisely so as not to inherit the defect, which is also the patch.

The related question — whether the community add-on has the same problem — is moot for this
project's purposes; see the superseded entry below.

<a id="second-backend-the-community-blender-mcp"></a>

## Superseded: second backend, the community "blender mcp"

**This is not going to be built, and the entry is kept rather than deleted so the decision stays
visible.** The goal was that mpfb-mcp should run against the community
[blender-mcp](https://github.com/ahujasid/blender-mcp) add-on as well as blender lab's, so a user
who already had that one installed did not have to install a second.
[FR 028](done/028-pivot-to-specific-addon/README.md) removed the dependency the adapter existed to
abstract: once no program crosses the socket, there is no third-party add-on in the path to
choose between, and a user running either one is pointed at the bridge instead — one extension
rather than two, and one that does not execute what it is sent.

**Two findings from that comparison outlive the plan**, and both proved their worth. The seam it
designed — an adapter *below* the send, invisible to tools — is where the bridge was fitted; see
[Supporting a second backend](../specifications/architecture.md#supporting-a-second-backend),
which keeps its name for exactly that reason, and note that the same property made the *removal*
of a transport cheap as well as its addition. And its conclusion that **backend selection must be
explicit configuration, never autodetection** is what made a typo an error rather than a silent
fallback for as long as there was a choice to get wrong. The substantive difference it identified
between the two add-ons — the result channel, the exec namespace's `result` dict against captured
stdout — is now a fact about software this project no longer talks to.

See [vision.md](../specifications/vision.md#superseded-which-blender-mcp-neither-in-the-end).

<a id="should-the-bridge-serve-its-own-test-harness"></a>

## Should the bridge serve its own test harness?

**Raised by [FR 033](done/033-retire-the-generated-code-path/README.md), which declined to answer
it.** The smoke run in [verification/](../verification/) used to make a scratch scene, build in it,
snapshot twelve `bpy.data` collections plus `is_dirty`, delete everything it had made and compare —
all by sending Python to an add-on that executed it. The bridge executes nothing, so all of that
went: the run now builds in whatever scene it finds, **leaves five MakeHuman objects and roughly
500 Rigify bone widgets behind**, and can compare only what `mpfb_list_objects` sees.
[verification/README.md](../verification/README.md#what-fr-033-cost-this-instrument) says so where
somebody reading a passing run will see it.

FR 033 decided that *a verification harness is not a reason to reopen the hole the whole pivot
exists to close*, and that is still the right default. The open question is whether a small,
named, non-`exec` vocabulary — "make a scene", "delete these objects", "list these datablock
collections" — is worth adding anyway. **It is not an obvious no.** Those are ordinary Blender
operations, they carry no caller-supplied code, and they would restore an assertion the project
had for twenty efforts. **It is not an obvious yes either**: every command is something an
extension reviewer has to be shown, `commands/table.py`'s claim is that a reader of one file knows
everything the add-on can be asked to do, and a delete command is the first entry in that table
that exists for a test rather than for a user.

Whoever takes this should weigh it as an extension-surface decision rather than a testing one, and
should cost the alternative first: the run is 1.5 s against a headless Blender started for the
purpose, and killing that Blender is already a complete cleanup.
