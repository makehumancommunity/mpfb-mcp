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

How generated code *reaches* MPFB at all — the bootstrap, and the rule against importing its
submodules — is [architecture.md](architecture.md#resolving-mpfb-from-generated-code).

## Where MPFB's UI coerces or re-defaults a service argument, mpfb-mcp does the same and reports both

A service signature's default is not always the product's default, and a service's argument is not
always the one the product would have passed. `HumanService.set_character_skin()` defaults
`skin_type` to `ENHANCED_SSS`, while the settings panel every user actually sees defaults it to
`MAKESKIN`; and it accepts `material_instances=True` for a `MAKESKIN` skin, while
`loadlibraryskin.py` forces that flag to `False` for `MAKESKIN`, `LAYERED` and `GAMEENGINE` alike —
a coercion the service's own guard makes for only two of the three.

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
- **The coercion belongs in the payload, not in the stub.** The test has to be testing mpfb-mcp. A
  stub service that coerced would let the payload do nothing and still pass.
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
  directory, which the smoke run there never does.
- **Filing it changes nothing here.** A confirmed defect is written up in
  [`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../mpfb2/features/MCP_DISCOVERED_BUGS.md), one
  section each, and that is where the reporting ends: MPFB has its own priorities, so a reported
  defect may stand for a long time. The workaround, the coercion or the defensive check that copes
  with it stays exactly as it is, and it is removed when a **running** MPFB no longer needs it —
  which is what the script detects, since it is written to fail once a defect is gone.
- **Do not merge them.** Picking one and naming it is the rule; synthesizing a fourth behavior that
  matches none of MPFB's own would make the result unreproducible from inside Blender.
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
  them, and say in the payload docstring that they are reproductions rather than choices.

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

What follows for a tool:

- **A rescan is opt-in, never the default.** `refresh` writes MPFB's caches — the asset one
  rescans the *whole* library and invalidates the alternative-material and pack metadata along the
  way — and those are the same caches MPFB's own panels read. A default that rescanned would make
  a catalogue call a side effect on the user's UI.
- **Say in the docstring what the first call costs and what a rescan does**, since neither is
  visible from the response and both are surprising for a tool that changes nothing in the scene.
- **mpfb-mcp adds no fourth cache of MPFB's data, and that was a decision.** The obvious place for
  one is the modeling category table three tools rebuild on every call, and
  [FR 017](../feature-requests/done/017-category-table-cost/README.md) set out to build it. What it
  found on measuring was that the rebuild costs 4 ms and the *generated code describing it* costs
  a second on the wire, so what is kept inside Blender is that code and not its answer (see
  [Generated code may keep its own source inside Blender](architecture.md#generated-code-may-keep-its-own-source-inside-blender)).
  Everything above therefore still describes every cache under these tools, all of them MPFB's own:
  a tool answering from MPFB's data is answering from a scan it just did.
- **Where a cache cannot be refreshed at all, say that too.** A caller who cannot tell staleness
  from absence will read a missing asset as a missing file. FR 013 found that
  `AssetService.invalidate_alternative_materials_cache()` *does* exist and clears both dicts —
  nothing calls it — which is what makes
  [FR 018](../feature-requests/018-alternative-material-refresh/README.md) possible; until it
  lands, the tool says so.

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
  said out loud in the payload docstring and in the response, because a caller who meets one will
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
