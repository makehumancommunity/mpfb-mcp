# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## A larger pivot: an MPFB-specific bridge add-on

**[FR 028](done/028-pivot-to-specific-addon/README.md) is done — see
[HISTORY.md](HISTORY.md#fr-028--the-pivot-to-a-bridge-add-on-decided-and-proved) for what it
landed. It made the decision and proved the transport, and
[FR 029](done/029-bridge-transport-and-skeleton/README.md) grew the add-on into something
twenty-five commands can be added to, and [FR 030](done/030-backend-seam/README.md) built the
seam on mpfb-mcp's side and migrated the first tool across it. The four efforts below are what
remains, and they run in order.**

The fundamental principle of the solution changed: instead of assembling Python programs and
sending them over a third party's MCP add-on socket, MPFB's Blender-side logic moves into a
companion add-on of our own — the **MPFB Bridge**, in [`bridge/`](../bridge) — with a closed
command vocabulary and its own socket, and mpfb-mcp becomes a thin client. FR 028 *planned* that
pivot: it proved the transport, rewrote [vision.md](../specifications/vision.md) and
[architecture.md](../specifications/architecture.md), and migrated no tool. What runs today is the
generated-code path for twenty-four tools and for all twenty-five in the default configuration,
documented as such in
[The generated-code path](../specifications/architecture.md#the-generated-code-path-what-runs-today-and-is-being-retired).

**Every one of these lands with both paths still working.** That is the property the whole staged
route is built on: the bridge and the generated-code path are comparable side by side on a real
Blender at every stage, and the old one is deleted only when nothing uses it. Numbers are
assigned when a request is started, not here.

<a id="1-bridge-transport-and-skeleton"></a>

### ~~1. Bridge transport and skeleton~~ — done

**[FR 029](done/029-bridge-transport-and-skeleton/README.md) landed it** — see
[HISTORY.md](HISTORY.md#fr-029--the-bridge-grows-a-skeleton-and-a-second-way-to-drive-it).
The declarative parameter contract, the `mpfb_unavailable` precondition, `list_commands`, the
handshake, a diagnostic panel, one module per command, a `5.0.0` Blender floor, and the headless
drive mechanism. The bridge's suite went from 7 tests to 35 and, for the first time, makes a real
socket round trip.

**Three things it settled that the efforts below inherit.** A command is a record in
`commands/table.py` with a handler, a parameter specification and a `requires_mpfb` flag, and a
migrated tool adds one module and one entry — nothing else. The wire's slugs are fixed, and
`mpfb_unavailable` is the one every migrated command depends on. And the two drive mechanisms are
verified to give identical answers, so nothing below has to test both.

**What it explicitly did not establish**: anything about the twenty-three commands still to be
written, or about how much of MPFB works in a headless Blender.

<a id="2-the-server-side-backend-seam"></a>

### ~~2. The server-side backend seam~~ — done

**[FR 030](done/030-backend-seam/README.md) landed it** — see
[HISTORY.md](HISTORY.md#fr-030--the-backend-seam-and-the-first-migrated-tool). The seam
(`src/mpfbmcp/backend.py`), the bridge's wire client and the client half of the handshake
(`src/mpfbmcp/bridge_connection.py`), `MPFB_MCP_BACKEND` / `MPFB_BRIDGE_HOST` / `MPFB_BRIDGE_PORT`,
the record's unit becoming a request rather than a program, and **one tool migrated** —
`mpfb_list_objects`, chosen for being dull.

**Four things it settled that the efforts below inherit.** The two paths were compared field by
field against one Blender and agree, which is the claim every stage below rests on and which had never
been checked. The migration's cost is known: 4,664 bytes of program against 83 bytes of JSON,
461 ms against 58 ms at the add-on's default tick. Where a migrated tool is tested is now a rule
rather than a judgement — everything the add-on side can check is checked there, against a real
MPFB, and what stays in `tests/` is a closed list
([testing.md](../specifications/testing.md#a-migrated-tool-is-tested-where-it-runs)). And the
seam's table is the migration's progress bar: **the stages below add lines to it and the last one
empties it.**

**What it explicitly did not establish**: anything about a batched, mutating, fragment-carrying or
file-writing tool, and nothing about what happens to 14.2k lines of tests when a payload with real
logic in it becomes add-on code. The one measurement it could offer was a floor — the migrated
tool's payload layer was 27% of its test module, for 87 lines of payload whose logic is a filter
and a substring test. **FR 031 answered the fragment and test questions**; the mutating, batched
and file-writing ones are still open and belong to the stage below.

**One transitional cost it created**, which every stage below lives with: a `verification/` run in the
bridge configuration needs *both* add-ons enabled and both servers started in one Blender, because
the harness's own scene bookkeeping goes over `send_code()`. It is written down in
[verification/README.md](../verification/README.md) and it goes away with the generated path.

### ~~3. Creation and modification migrated~~ — done

**Landed as [FR 032](done/032-creation-and-modification-migrated/README.md); see
[HISTORY.md](HISTORY.md#fr-032--creation-and-modification-migrated).** The last fourteen tools
crossed the seam, so `backend.MIGRATED_COMMANDS` holds twenty-four entries — every tool that
crosses the socket — and **the default backend is the bridge**. The two things this text left open
were settled: the flip happened in that effort's last commit, after its own live check compared
all fourteen on both transports against one Blender; and the bridge suite's alphabetical prefixes
ran out exactly as predicted, answered by prefixing a *directory* (`ppp_mutating/`), which is
MPFB's own way out.

What it hands to stage 4, beyond the obvious: the 60% rate held at **58%** over fourteen more
modules, with `mpfb_list_urls` (24%) and `mpfb_create_human` (no payload layer at all) as the two
informative outliers; the seven shared fragments all have counterparts, so
[tests/test_fragment_drift.py](../tests/test_fragment_drift.py) straddles nothing and is now
guarding two copies until one is deleted; and `mpfb_set_asset_material` kept its reimplementation,
with the rule against importing MPFB's UI operator module restated in the command's own docstring
rather than left to the specification — being an add-on made that import possible for the first
time, which is precisely when a rule has to say why it still holds.

### 4. Retire the generated-code path

**Scoped as [FR 033](033-retire-the-generated-code-path/README.md) (Accepted), and stage 3 is
complete, so it can start.** Its first requirement is the check that says so, and FR 032's own
live check already asserts it: twenty-four payloads, twenty-four commands, `mpfb_list_docs` the
one legitimate exception. Four decisions it
settles that this text left open: the seam survives as a single-transport `send()` rather than
being deleted, `verification/`'s harness is rewritten on commands that already exist rather than
the bridge growing instrument-serving ones, the frozen payload test layers are deleted without
re-examination, and filing the 4 KB chunked read upstream is **not** part of it (see below).

Delete `codegen/`, the session source cache and the seven shared fragments; empty the seam's
`MIGRATED_COMMANDS` table and with it the last branch that knows there were two transports; fold
what they taught into the specifications rather than losing it; drop blender_mcp from the install
instructions — including the transitional two-add-on prerequisite
[verification/README.md](../verification/README.md) now carries. Each payload deleted takes its
frozen stub-executed test layer with it, which stage 2 measured at 27% of one test module for the
dullest tool in the package, FR 031 measured at roughly 60% across nine more and FR 032 at 58%
across the remaining fourteen. `tests/generated_path.py` goes with them: it exists only because
twenty-five modules had to say they were about a path that is no longer the default.
[tests/test_fragment_drift.py](../tests/test_fragment_drift.py) goes here too, and it goes for a
good reason rather than a tidy one: it exists because a concept lives in two places at once, and
after this stage it lives in one.
This is also when
[The generated-code path](../specifications/architecture.md#the-generated-code-path-what-runs-today-and-is-being-retired)
stops being a section of architecture.md and becomes something HISTORY.md remembers.

Worth filing upstream on the way out, for everyone else's benefit rather than ours: see
[Handle the 4 KB chunked read](#handle-the-4-kb-chunked-read-against-blender_mcp) below.

### 5. Publish and document

An extension-platform listing for the bridge, and a page on makehumancommunity.org stating
plainly that it is local, that it is optional, and that nothing is uploaded. Both belong to the
stage where the bridge is worth installing, and neither is an engineering problem.

Two questions FR 028 recorded as open are answered here or not at all, because they are not
engineering questions: what extension review makes of a listening socket, and what MPFB's users
actually want. A forum post describing the bridge costs nothing and would replace guesswork with
evidence.

## Expressions

**Scoped as two requests, in this order: [FR 026](026-face-units/README.md) (Accepted) for the
face-unit layer, then [FR 027](027-expression-library/README.md) (Accepted) for the saved-expression
library and the stack that applies it. FR 027 extends FR 026's tools; see
[the dependency](027-expression-library/README.md#the-dependency-and-what-happens-if-the-order-reverses).**

These are the `!ex-` prefixed shape keys. They depend on particular asset packs being installed.
Expressions should be a mix of functionality from the `src/mpfb/ui/create_assets/makeexpression`
and `src/mpfb/ui/apply_assets/useexpression` UI code hierarchies in MPFB. TargetService has
some functionality for working with expressions.

## Saving expressions

Queued behind [FR 027](027-expression-library/README.md), which reads and applies expressions but
writes none. An `mpfb_save_expression` would close the gap named in
[FR 026](026-face-units/README.md#a-composed-face-is-transient): a face composed from ARKit units
survives nothing today — not a preset save (a preset serializes the applied-expressions *stack*, and
a composed face has no stack rows), and not the next library call, which clears every `!ex-` key
before rebuilding.

`FaceService.save_expression` already exists and already does the filtering, rounding and metadata
defaulting. The tool writes outside the `.blend`, which is now a settled shape rather than an open
question: follow
[a tool whose effect is outside the `.blend`](../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more),
landed by [FR 025](done/025-character-presets/README.md) — name and never a path, the name validated
on this side of the socket, `overwrite: False`, the absolute path in every answer — writing to
`LocationService.get_user_data("expressions")`. Whether the name rule can be *reused* rather than
restated is the effort's to decide: `src/mpfbmcp/preset_names.py` and
`codegen/shared/preset_files.py` are written around `human.<name>.json` in the user config
directory, so a second artifact in a different directory either generalises them or copies them,
and FR 025's own reason for two copies (a silent gap between two sides of the socket) does not by
itself argue for a third. It comes after FR 027 because what it writes is read back through the
library.

## Visemes and lip sync

The rest of `FaceService`, deliberately excluded from both expression requests (see
[Not visemes](026-face-units/README.md#not-visemes)): `MICROSOFT_VISEMES` and `META_VISEMES`,
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
unblocking it: **mpfb-mcp opens no network connection except the one to the blender_mcp add-on**
is now a [standing constraint](../specifications/architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on).
So this effort cannot simply fetch a pack. Either the retrieval happens on the *Blender* side, in
generated code, which is a different thing from mpfb-mcp opening a socket and needs to be argued
explicitly rather than assumed; or the client is handed the address and the tool installs what the
user has already downloaded. There is an operator for loading a pack from zip in MPFB which can be
used as inspiration for the second half either way.

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

## Handle the 4 KB chunked read against blender_mcp

**The largest single cost in this package is one line in an add-on we do not own.**
blender_mcp's `mcp_to_blender_server._service_clients()` does exactly one `conn.recv(4096)` per
timer tick and then returns, so a request arrives at one 4 KB chunk per tick — 250 ms each while
the add-on is busy, and 1 s each once five seconds have passed without a request *finishing*, since
bytes arriving do not reset its idle countdown. A generated program therefore costs about 250 ms
per 4 KB, or 1 s per 4 KB against the idle Blender an agent actually meets, **regardless of what
the program does**: a 50 KB call is 3 s or 12 s of waiting before Blender has read the request.

**Since [FR 028](done/028-pivot-to-specific-addon/README.md) this is no longer our problem to solve,
only ours to report.** The bridge sends parameters rather than programs, so once the migration
completes there is no generated program whose size this tax is charged against — and the bridge's
own transport already drains its socket per tick rather than reading one chunk, precisely so it
does not inherit the defect. What remains worth doing is **filing it upstream**: it is a real
defect costing every other user of that add-on the same thing it cost this project, the fix is a
loop, and reporting it is cheap. Do that on the way out, in
[the retirement stage of the pivot](#4-retire-the-generated-code-path), rather than letting it disappear with
the code that suffered from it.

The related question — whether the community add-on has the same problem — is now moot for this
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

**Two findings from that comparison outlive the plan**, and both are load-bearing now. The seam
it designed — an adapter *below* the send, invisible to tools — is where the bridge is being
fitted; see
[Supporting a second backend](../specifications/architecture.md#supporting-a-second-backend),
which keeps its name for exactly that reason. And its conclusion that **backend selection must be
explicit configuration, never autodetection** matters more with three candidate ports than it did
with two. The substantive difference it identified between the two add-ons — the result channel,
the exec namespace's `result` dict against captured stdout — is now a fact about software this
project no longer talks to.

See [vision.md](../specifications/vision.md#superseded-which-blender-mcp-neither-in-the-end).

