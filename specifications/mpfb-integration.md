# MPFB integration

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

**What to do when MPFB is inconsistent, undocumented, or wrong.** mpfb-mcp wraps a large addon
that was not written to be wrapped, and the recurring problem is not that MPFB is hard to call —
it is that there is often more than one answer to "what does MPFB do here", and the differences
are invisible from the response unless a tool says so.

The standing bar throughout is the one [FR 007](../feature-requests/done/007-macro-details/README.md)
set: **a character mpfb-mcp produces must be reproducible through MPFB's own UI**, and where it
cannot be, the tool says which path it took and why.

How a command *reaches* MPFB at all — the `sys.modules` scan, and the rule against importing its
submodules — is [architecture.md](architecture.md#resolving-mpfb).

## Where MPFB's UI coerces or re-defaults a service argument, mpfb-mcp does the same and reports both

A service signature's default is not always the product's default, and a service's argument is not
always the one the product would have passed. `HumanService.set_character_skin()` defaults
`skin_type` to `ENHANCED_SSS`, while the settings panel every user actually sees defaults it to
`MAKESKIN`; and it accepts `material_instances=True` for a `MAKESKIN` skin, while
`loadlibraryskin.py` forces that flag to `False` for `MAKESKIN`, `LAYERED` and `GAMEENGINE` alike —
a coercion the service's own guard makes for only two of the three.

A third instance says the pattern is not peculiar to skins. `get_default_deserialization_settings()`
gives `material_instances` as `NEVER`, while `ui/new_human/newhuman/properties/material_instances.json`
— the panel behind MPFB's "create human from save file" button — defaults it to `ENHANCED`. So
`mpfb_create_human_from_preset` takes `ENHANCED` as the meaning of an omitted argument, and reports
`material_instances_used` beside `material_instances_service_default`. Both figures were read off
the running install rather than the source.

A fourth is not about a character at all. `FaceService.save_expression()` writes an empty `license`
when none is given, while the composer panel behind MPFB's own "save expression" button pre-fills
`CC0` ([`properties/license.json`](../../mpfb2/src/mpfb/ui/create_assets/makeexpression/properties/license.json)).
`mpfb_save_expression` defaults `license` to `CC0` and reports the metadata it wrote, read back from
the file. [FR 027](../feature-requests/done/027-expression-library/README.md) asked whether a licence
- a statement made on the user's behalf - was a default an agent should apply silently, and kept it:
the tool description names the default, so an agent applying it has read it, and a user saving
through MPFB's own panel gets the same value unless they change it.

**Where a tool departs from the panel's default, it says why, and the reason has to be true.**
`mpfb_set_face_units` defaults `refit` to `true`. FR 026 wrote that this matched the composer
panel's `auto_refit`; it does not - the composer's defaults to `false`, and it is the *library*
panel's (`ExpressionsLibraryProperties`) that defaults to `true`. FR 027 found the error, kept the
default on its merits - a human drags a composer slider through dozens of values and each would
refit, while composing across MCP is one batched call, and garments do not follow the face without
a refit - and corrected every place that gave the wrong reason. `mpfb_apply_expressions` follows
the library panel's `true` directly. A default whose stated reason is wrong is harder to revisit
than one that never gave a reason, which is why the correction was worth an effort's time.

Passing the signature's value in either case would produce a character that **cannot be reproduced
through MPFB's own UI**, which is the same quality bar
[FR 007](../feature-requests/done/007-macro-details/README.md) sets for macro details: the goal is
that the value reads back on MPFB's own slider.

- **Follow the UI, not the signature.** The panel is what the user saw and what a character loaded
  from a `.mhm` was made with. A signature default is an implementation detail of one function.
- **Say so in the docstring, naming both values.** "Defaults to `MAKESKIN`, which is MPFB's settings
  panel's default rather than the function's `ENHANCED_SSS`" is checkable; a bare default is not.
- **Report `*_requested` beside `*_used`, with a sentence when they differ.** A silent coercion is
  indistinguishable from a bug: a caller who asks for material instances, gets none, and is told
  nothing will conclude the tool is broken. `mpfb_set_skin` returns
  `material_instances_requested` and `material_instances_used` on every call, not only when they
  disagree — for the same reason
  [A mutating tool reports before and after](mutating-tools.md#a-mutating-tool-reports-before-and-after) reports a
  field the caller named even when it was already so.
- **The coercion belongs on the far side of the socket, not in the stub.** The test has to be
  testing mpfb-mcp. A stub service that coerced would let the code under test do nothing and still
  pass. Each of these rules was checked across the move to the add-on rather than assumed to
  survive it, by [FR 032](../feature-requests/done/032-creation-and-modification-migrated/README.md),
  which had both implementations running side by side to compare. All three held:
  `mpfb_set_skin`'s three-type coercion, `mpfb_create_human_from_preset`'s panel default of
  `ENHANCED` over the service's `NEVER`, and `mpfb_add_asset`'s per-type material default. The
  check is that effort's own
  [live comparison](../feature-requests/done/032-creation-and-modification-migrated/check_creation_migration.py),
  which compares the two answers field by field — so `material_instances_used` disagreeing between
  the transports would have been a failure rather than something to notice later.
- **This is not the same as picking between code paths.**
  [Where MPFB's own code paths disagree](#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)
  is about two implementations of an operation; this is about one implementation whose *arguments*
  the UI fills in differently from its signature. The remedy is different too: there, name the path
  you took; here, apply the coercion and report both values.

## Where MPFB's own code paths disagree, mpfb-mcp picks one and names it

Sometimes there is no single MPFB implementation to wrap. Adding a topology proxy has three:
`HumanService.add_mhclo_asset()` imports and fits it and stops there;
`HumanService._check_add_proxy()` calls that and then hides the basemesh, copies the scale factor,
creates the proxy's extra vertex groups and runs a corrective pass; and the asset library's proxy
operator does not call `add_mhclo_asset()` at all and carries a third implementation gated on its
own scene settings. Nothing documents which is canonical.

**Measured** (FR 013's live run), the picture is sharper than "the three disagree", and the
sharper version is the better argument. `add_mhclo_asset()` alone and `_check_add_proxy()` really
do produce visibly different characters: no `Hide base mesh` modifier, 124 vertex groups against
130, and `scale_factor` left at `1.0` rather than copied from the character's `0.1`. But
`_check_add_proxy()` and the library operator produced **identical** state on every field compared.
So the operator is a duplicated implementation rather than a divergent one — and what makes the
choice load-bearing is not that three paths disagree but that the *obvious* implementation, the
service function whose name matches the operation, is the one that differs. A rule that only fired
when three implementations visibly disagreed would not have fired here, and would have been wrong
not to.

**The sharpest instance is two paths that write the same thing, one destroying the other's work.**
MPFB's expression composer writes the 52 `!ex-` shape keys directly (`FaceService.set_expression`,
wrapped by `mpfb_set_face_units`); its expression library keeps a stack of `{asset, weight}` rows on
the basemesh and re-derives the face from it on every change, clearing first
(`mpfb_apply_expressions`, and every preset load). Neither is wrong, and a user in MPFB's UI copes
because the panels are in different tabs and sliders visibly move. Across MCP nothing moves. So
mpfb-mcp does not pick one here - it exposes both - and instead **computes the comparison MPFB never
makes**: whether the stack explains the face
([`shared/expression_divergence.py`](../bridge/mpfb_bridge/shared/expression_divergence.py)),
reported by every tool on either side, with the one bridge between them - saving a composed face as
an expression file - named whenever there is something to lose. See
[a tool that destroys state it did not create](mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list).

The same pair produced a smaller instance of the rule below. MPFB's composer save operator builds
the file from the composer panel's scene properties (`MPFB_EX_<unit>`), which the composer's own
UI keeps in step with the face but `set_expression()` does not touch. `mpfb_save_expression` saves
the **shape keys** (`read_current_expression()`), because the panel's sliders are stale for a face
composed across MCP, and its command docstring says so.

This is the sharper, more general form of
[When mpfb-mcp models a concept MPFB's UI has but its services do not](#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not),
whose last clause — document the divergence rather than normalizing it away — extends here from "UI
versus services" to *any* two MPFB code paths.

- **Follow the service-layer path.** It is what `deserialize_from_mhm()` uses, so it is what a
  caller comparing against a loaded `.mhm` will expect, and it is what other services are written
  against. A UI operator's variant is the behavior of one panel, not of MPFB.
- **Say which one in the docstring, and name the one you did not take.** "This matches `.mhm`
  loading rather than the proxy library panel" is something a caller can check; silence is not.
- **Report the parts that differ, individually.** `proxy_extras` names each of the four things
  `_check_add_proxy()` does beyond the plain add, so a caller who sees a difference against MPFB's
  panel can see exactly where it comes from.
- **Record the divergence as a candidate mpfb2 issue — and then confirm it before filing.** Three
  implementations of one operation is a problem in MPFB that mpfb-mcp is working around, not a fact
  about mpfb-mcp. But a candidate defect read from source is a hypothesis: of the seven FR 008
  through FR 011 recorded, the live run confirmed four, refuted two outright
  (`RigService.identify_rig()` cannot return `None`; the alternative-material cache *does* have an
  invalidator) and found the fifth to be worse and quieter than described. Each is provoked by
  [`check_mpfb_issues.py`](../feature-requests/done/019-file-mpfb-defects/check_mpfb_issues.py),
  which lives beside the report it backs, so a claim about MPFB is re-checkable against a future
  MPFB rather than frozen as an opinion. It is deliberately not in `verification/`: it provokes
  defects in MPFB rather than checking mpfb-mcp's tools, and it writes into MPFB's user data
  directory. FR 025's [`check_presets.py`](../feature-requests/done/025-character-presets/check_presets.py)
  is the second of these and confirmed the `save_clothes` defect the same way — by serializing one
  dressed character twice, with the argument as the only difference, rather than by reading the
  function. The smoke run writes outside the `.blend` too now, but exactly one file, always the
  same one, and [verification/README.md](../verification/README.md) names it.
- **Filing it changes nothing here.** A confirmed defect is written up in
  [`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../mpfb2/features/MCP_DISCOVERED_BUGS.md), one
  section each, and that is where the reporting ends: MPFB has its own priorities, so a reported
  defect may stand for a long time. The workaround, the coercion or the defensive check that copes
  with it stays exactly as it is, and it is removed when a **running** MPFB no longer needs it —
  which is what the script detects, since it is written to fail once a defect is gone.
- **Do not merge them.** Picking one and naming it is the rule; synthesizing a fourth behavior that
  matches none of MPFB's own would make the result unreproducible from inside Blender.
- **Not reproducing something MPFB's UI does is the same decision and carries the same burden**, so
  it is justified in the module docstring rather than merely noted. Two of them are in the preset
  tools. MPFB's two saving operators emit a `WARNING` whenever `identify_rig()` contains
  `"generated"`; `mpfb_save_preset` does not, because the warning overstates what happens —
  `_populate_human_info_with_rig_info()` is built for the case, infers the meta rig, falls back to
  `rigify.human_toes`, and records that. Nothing fails. What is true is that a generated rig does
  not round-trip, which the *description* says once and the response shows on the call where it
  happened, as `rig_identified_as` beside `rig_saved_as`. A warning emitted on every save of a
  Rigify character is noise an agent learns to ignore. And `mpfb.human_from_presets` ends by
  entering **edit mode** twice to preselect a vertex group, setting an active material index from
  it, and optionally running Rigify generation; `mpfb_create_human_from_preset` reproduces none of
  the three. Entering edit mode across the socket is a hazard rather than a nicety — every later
  `bpy.ops` call polls on the context mode, and a program that fails between the two `mode_set`
  calls leaves Blender in edit mode — and Rigify generation is a tool of its own precisely because
  it cannot be undone.
- **The inverse also happens: MPFB's message can be wrong, and then it must not reach the agent.**
  `_populate_human_info_with_rig_info()` raises `ValueError("Could not identify rig type. Custom
  rigs cannot be serialized.")`, which is false — a custom rig still present in user data
  serializes as `custom.<name>`. `mpfb_save_preset` checks the condition itself, before anything is
  written, and refuses with the real cause: the armature is not one MPFB recognises, which for a
  custom rig means its definition is no longer in user data. Passing MPFB's text through would send
  a caller looking for a limitation that does not exist.
- **The limiting case is no service path at all.** Setting an alternative material on an equipped
  asset exists only in `ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py`, as two
  module-level helpers. There is nothing to prefer, so the panel's behavior *is* the specification,
  and it is reimplemented from services rather than imported — quirks included, because every quirk
  is a way the result would otherwise differ from what the user gets from the panel. Three of them
  are reproduced deliberately in `mpfb_set_asset_material`: the replacement is always a MakeSkin
  material under the fixed name `makeskinmaterial`, whatever the asset had before; the slots are
  *popped* rather than deleted, so the previous material's node groups survive (unlike the skin
  path, which destroys them); and the viewport colour is keyed on the object's recorded
  `object_type`, so an asset mislabelled at equip time gets the wrong colour here too. Reproduce
  them, and say in the command's docstring that they are reproductions rather than choices.

## Reading MPFB's data files directly

Not everything a tool needs is behind a service. `mpfb_list_targets` reports `target.json`, the
bundled index of modeling targets, which MPFB has no accessor for at all — its own consumers build
the path and `json.load()` it. Where a tool has to read a bundled data file, three rules:

- **Locate it through `LocationService`, never by assembling a path from a module's location.**
  `get_mpfb_data("targets")` is the only thing that knows where an extension install put its data;
  a path derived from `__file__` or from the package name is a guess that breaks on the next
  install method.
- **Guard the read, and treat a missing or unparsable file as an answer.** A broken install is one
  of the things a tool is for reporting, so it comes back as `target_json_exists: false` plus an
  explanatory message and whatever else the tool could still gather — not as a failed call. This is
  the same rule as `mpfb_get_status`' three-state classification, applied to a file.
- **Report where it is rather than what is in it, when it is large.** `target.json` is ~140 KB, far
  more than a response should carry, and a client sharing a filesystem with Blender can parse it
  itself. Reporting the path, an overview, and a way to page through the contents is strictly more
  useful than truncating the file.

## MPFB caches what it scans, and a tool says what that costs and what it hides

Three of MPFB's own caches sit under this package's catalogue tools, and each one changes what an
answer means rather than merely how fast it arrives.

- **The asset list.** The first scan of a subdir loads a Blender preview image for every
  thumbnailed asset — the slow, memory-hungry part of `mpfb_list_assets`, paid once per subdir per
  Blender session, and shared with MPFB's own asset panels, so a session where those were opened
  has already paid it. Worse, the cache is keyed by a *label* derived from the filename alone, so
  two assets whose filenames differ only in case or underscores collapse into one entry: a count
  from here can under-report, and one of the two is missing entirely rather than merely
  mislabelled. That is a limitation of MPFB's cache and not of the filters, and it is why a
  listing count may disagree with a count of files on disk.
- **The custom rig list**, cached for the lifetime of the Blender session, so a rig installed after
  Blender started does not appear until something rescans.
- **The alternative materials of one asset**, cached per `(asset_source, asset_subdir)` — the case
  where [the tool is the stale one](responses.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show).
  `mpfb_list_asset_materials`' `refresh` clears it via
  `AssetService.invalidate_alternative_materials_cache()`, which is global — it drops every asset's
  cached scan, not only the one named in the call — reported through `cache_invalidated` rather
  than left implicit ([FR 018](../feature-requests/done/018-alternative-material-refresh/README.md)).
- **The list of saved character presets**, in the module global `_EXISTING_PRESETS`, which exactly
  one thing invalidates: a save through `serialize_to_json_file()`. A preset written by MPFB's panel
  in another Blender, by hand, or by an earlier session is invisible until something rescans.
- **Whether the `faceunits01` asset pack is installed**, in `FaceService`'s module global
  `_FACEUNITS01_INSTALLED` — the third instance of the pattern, and the first one gating a whole
  capability rather than one listing's freshness (see
  [below](#a-capability-that-depends-on-an-optional-asset-pack)). `mpfb_get_face_units`' `refresh`
  busts it via `force_recheck=True`, as do `mpfb_list_expressions`' and `mpfb_get_expression`'s;
  the two writing tools (`mpfb_set_face_units`, `mpfb_apply_expressions`) read the cached answer,
  since a caller who wants a fresh probe before writing reads one through a read tool first.
  Nothing in MPFB invalidates it on a pack install, which is filed as item 10 of
  `mpfb2/features/MCP_DISCOVERED_BUGS.md`. `list_available_expressions()`, by contrast, is **not**
  cached - it walks the disk on every call - so `mpfb_list_expressions`' `refresh` is about the pack
  probe only, and its description says which.

What follows for a tool:

- **A rescan is opt-in, never the default.** `refresh` writes MPFB's caches — the asset one
  rescans the *whole* library and invalidates the alternative-material and pack metadata along the
  way — and those are the same caches MPFB's own panels read. A default that rescanned would make
  a catalogue call a side effect on the user's UI.
- **Say in the docstring what the first call costs and what a rescan does**, since neither is
  visible from the response and both are surprising for a tool that changes nothing in the scene.
- **mpfb-mcp adds no cache of MPFB's data, and that was a decision.** The obvious place for one is
  the modeling category table four commands rebuild on every dispatch, and
  [FR 017](../feature-requests/done/017-category-table-cost/README.md) set out to build it. What it
  found on measuring was that the rebuild costs **4 ms**, which is not worth a cache of any kind —
  and what a cache would cost is the property that makes these tools better than MPFB's own panels:
  a target installed since Blender started is visible here and is not there. So every cache under
  these tools is MPFB's own, and a tool answering from MPFB's data is answering from a scan it just
  did.
- **Where the tool can see past the cache cheaply, it does, rather than handing the caller a flag
  instead of an answer.** `refresh` is opt-in for the reason above, but a caller who has to pass it
  in order to find out whether it would change anything has not been told much.
  `mpfb_list_presets` answers from MPFB's cached list — that is the list MPFB's own dropdown is
  built from, so a name in it is a name the user sees there — and *also* lists the directory, which
  is one `os.listdir` of some tens of files, reporting the difference as `missing_from_mpfb_list`.
  This is affordable precisely because the collection is small; it is not a general licence to
  second-guess a cache whose rescan is the expensive thing being avoided.
- **Where a cache cannot be refreshed at all, say that too.** A caller who cannot tell staleness
  from absence will read a missing asset as a missing file. FR 013 found that
  `AssetService.invalidate_alternative_materials_cache()` *does* exist and clears both dicts —
  nothing called it until
  [FR 018](../feature-requests/done/018-alternative-material-refresh/README.md) wired it up as
  `mpfb_list_asset_materials`' `refresh`, which is why that tool no longer says so.

## A capability that depends on an optional asset pack

[FR 026](../feature-requests/done/026-face-units/README.md) is the first tool pair whose whole
capability depends on an asset pack that may not be installed — the 52 ARKit face units, every one
of which needs a target file from `faceunits01` — and it is not the last: poses, further asset
packs and the extra-target packs all have the same shape. The generalisation is the durable part of
that effort:

- **MPFB reports the absence of an optional pack to nobody.** Without `faceunits01`,
  `FaceService.set_expression()` logs a warning per unit ("Target file not found for face unit,
  skipping") and returns normally, having moved nothing. MPFB's own panels handle this by not
  drawing themselves — `poll()` returns `False`, the operators are unreachable — which is a UI-layer
  guard an MCP tool inherits nothing from. **Probe the pack's own installed-check, and report it in
  every response that depends on it**, not only in a refusal: `mpfb_get_face_units` carries
  `faceunits01_installed` whether or not a subject even resolves, because a caller reading an
  all-zero answer needs to know whether that means "neutral" or "not installed" before it means
  anything at all.
- **Refuse a write outright when the probe fails, rather than succeeding emptily.** MPFB's own
  behaviour — warn and continue — turns a pack-absent call into what looks like a successful no-op.
  `mpfb_set_face_units` checks the probe before writing anything and answers `blocked_by:
  "faceunits01_not_installed"`, per [preconditions are
  answers](mutating-tools.md#preconditions-are-answers).
- **The probe is not a verification, and a per-item resolution failure stays separately
  reportable even after the probe passed.** `is_faceunits01_installed()` tests exactly one target
  (`cheekPuff`); a pack installed halfway — a partial download, a manual copy that missed a file —
  passes that probe and still has individual targets missing. `mpfb_set_face_units`'
  `could_not_load` is what a caller reads when the probe said yes and one specific unit said no
  anyway: checked per requested unit, at write time, never folded into the up-front refusal.
- **Where the write outlives the missing pack, the refusal matters more, and it covers only what
  would claim something.** `mpfb_apply_expressions` writes a stack that *persists* on the basemesh:
  without the pack, the character would go on claiming an expression it has never displayed, and a
  preset would carry the claim to another machine. So it refuses any call that adds or raises a row
  - FR 027 applied this rule rather than extending it - but lets a call that only removes rows
  through, since taking an expression off claims nothing and is how a stack from another machine
  is cleaned up. A catalogue of things that depend on the pack (`mpfb_list_expressions`) reports
  the probe on every answer for the same reason the read tool does: its list is a list of things
  that cannot be applied when the answer is `false`.
- **Use MPFB's own install-check rather than inventing a second definition.** `faceunits01` has no
  service function whose name says "is this pack here" other than the one `FaceService` already
  exposes; a tool inventing its own (checking for a specific file, say) risks disagreeing with what
  MPFB itself will and will not do.

## When mpfb-mcp models a concept MPFB's UI has but its services do not

Not every concept a tool needs is a service concept. A modeling *modifier* — a slider from -1.0 to
+1.0, built from a pair of opposing targets, optionally with left and right variants — is not a
`TargetService` idea at all: it lives in `target.json` and in `mpfb/ui/model/_modelsubpanels.py`.
`mpfb_set_targets` lifts it out of the UI into the tool layer, because without it a caller could
address individual shape keys but could not express anything MPFB's own sliders express.

- **Reproduce the mechanics from MPFB's UI code rather than reinventing them**, statement for
  statement where the order matters. `_set_opposed_modifier_value()` zeroes the opposing target
  *first* and only then sets or loads the selected one; doing it the other way leaves both halves
  of a pair briefly non-zero and, with pruning on, deletes the wrong one.
- **Still never import the UI module**, for the reason in
  [Never import MPFB submodules directly](architecture.md#never-import-mpfb-submodules-directly)
  — and here for a second reason: `_modelsubpanels` builds its table at *module import time*, so
  it is a snapshot from when Blender started, and a tool built on it would be blind to a target that
  `mpfb_list_targets` — which scans per call — can see.
- **Document the divergences rather than silently normalizing them.** MPFB's two setter functions
  disagree about the file extension, one trying `.target.gz` then `.target` and the other only the
  first; and MPFB's category name for a gzipped custom target does not strip `.gz`, so its shape key
  is not called what `mpfb_list_targets` reports. Both are reproduced or repaired deliberately, and
  said out loud in the command's docstring and in the response, because a caller who meets one will
  otherwise read it as a bug here.
- **The goal is that the value reads back on MPFB's own slider.** Where reproducing a quirk and
  tidying it up would give different answers in MPFB's panel, reproduce the quirk.

The general case — two MPFB *code paths* that disagree, rather than a UI concept the services lack —
is [Where MPFB's own code paths disagree, mpfb-mcp picks one and names it](#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).

### Sometimes reading the UI module is the right answer

The modifier case above ends in "never import the UI module", and that reads as a rule about UI
modules. It is not — it is a rule about *snapshots*. `_modelsubpanels` builds its table when
Blender starts, so anything built on it is blind to a target installed since, and mpfb-mcp
reimplements the concept from `target.json` instead.

`mpfb/ui/weburls.py` is the second instance of the same situation and comes out the other way. It
is again a concept MPFB's UI has and its services do not — the community addresses, which MPFB
gathers there "so that the same link does not have to be maintained in several panels" — but it
holds eleven string literals and computes nothing. There is no snapshot in it, so `mpfb_list_urls`
reads it out of `sys.modules` rather than keeping a second copy that MPFB's own edits would not
reach. The mechanics and the two conditions that make a UI module readable are in
[architecture.md](architecture.md#a-ui-module-with-no-service-behind-it).

The distinction worth carrying: **reimplement a UI concept that is computed, read a UI table that
is constant.** Both keep the rule the two cases actually share — MPFB's value is the authority,
and a copy of it is a fallback that must say it is one
([and say so in the response](responses.md#a-response-says-which-source-answered-it)).
