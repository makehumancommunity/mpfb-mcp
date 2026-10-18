# verification/

**A smoke test.** One item per tool, called the way an MCP client would call it with default
arguments, against a real Blender. It answers one question — *does every tool still work at
all?* — and it answers it in a couple of seconds, so there is no reason to skip it.

One item reaches no Blender at all: `mpfb_list_docs` is a local table, so its item establishes only
that the tool is registered and still answers with the keys its description promises. It is a
per-tool item anyway, because coverage is derived from the registry and the run-level set is closed
at two.

Not part of the installed package, not discovered by `python3 -m unittest discover -s tests`, and
not shipped: `pyproject.toml` declares package data by explicit glob under `src/`, so a top-level
directory outside it cannot be picked up.

## Running

```bash
MPFB_MCP_RECORD_DIR=~/mpfb-mcp-records PYTHONPATH=. python3 verification/smoke.py
```

That is the whole interface, and since [FR 033](../feature-requests/done/033-retire-the-generated-code-path/README.md)
there is only one configuration to run it in. `MPFB_MCP_RECORD_DIR` is optional: with it, every
call leaves the exact request, the exact envelope and a duration behind, which is what makes a
failure diagnosable rather than merely visible. The run also writes its full result — the printed
lines are capped, the file is not — into `verification/results/`, overridable with
`MPFB_MCP_VERIFICATION_RESULTS`.

**Requirements: one Blender with MPFB and the MPFB Bridge enabled, and the bridge's socket server
started (9877).** Nothing else. `MPFB_BRIDGE_HOST` / `MPFB_BRIDGE_PORT` point the run at a bridge
that is not on the default address.

**Point it at a Blender you are willing to throw away.** That is new advice and it is the
consequence of the paragraph below: the run no longer puts back what it builds. A headless Blender
started for the purpose is the cheapest way to get one, and it needs no window and no clicking:

```bash
blender --background --command mpfb_bridge --port 9900
```

then `MPFB_BRIDGE_PORT=9900 PYTHONPATH=. python3 verification/smoke.py` against it. Kill the
Blender when the run is done and everything the run made goes with it.

Where the install lacks a prerequisite — no MHCLO assets, no skins, Rigify disabled — the affected tools report
`skipped` **with the reason**, the run still passes, and the summary names every tool it could not
exercise. A skip never reads as a pass.

**One harness process at a time.** Two against one Blender interleave, and the second fails in
ways that look like tool defects.

## What it checks, and what it deliberately does not

Each item asserts exactly three things:

1. the envelope is not an error;
2. the response carries the keys the tool's own contract names as always present — and those keys
   are held to the description the MCP client actually downloads, so the list here cannot become a
   private second copy of the contract;
3. for a mutating tool, `performed` is true and agrees with that tool's own verb. This is the one
   check the unit suite genuinely cannot make: there the flag and the verb are read out of the
   same stub run, and here they come out of a real Blender.

It asserts **nothing about values**. Whether a garment equipped through the tool is
indistinguishable from one equipped through MPFB's panel, whether each of the five skin types
builds the right node tree, whether a weights prediction matches the weights actually loaded —
those were established once, by the efforts that claimed them ([FR 009](../feature-requests/done/009-add-rig/README.md),
[FR 010](../feature-requests/done/010-mesh-assets/README.md),
[FR 011](../feature-requests/done/011-skin-and-materials/README.md)), and re-proving them on every
code change is what turned this directory into 5,308 lines and a run of minutes.

### What FR 033 cost this instrument

Read this beside a passing run rather than instead of one. Until FR 033 the harness had a private
channel into Blender: it sent Python of its own to an add-on that executed it, and that is how it
made a scratch scene, compared twelve `bpy.data` collections plus `bpy.data.is_dirty` before and
after, deleted everything it had built and purged the orphans. **The bridge executes nothing**, and
FR 033 decided that a verification harness is not a reason to give it an `exec` command — that
would reintroduce precisely the property the pivot exists to remove. So the channel has no
replacement, and four things went with it:

- **The scratch scene is gone.** The run used to build in a scene of its own, `MPFBMCP_VERIFY`,
  and now builds in whatever scene the Blender it is pointed at has open.
- **The cleanup is gone, so the run leaves what it built.** Five *MakeHuman* objects on a full
  run — a basemesh, its meta rig, the generated Rigify rig, and the second character
  `mpfb_create_human_from_preset` builds with its rig — plus, and this is the larger number,
  roughly **500 `WGT-` bone-widget objects** and two `WGTS_` collections that Rigify generation
  creates. None of the widgets is a MakeHuman object, so the compare below does not see them: what
  the item names as left behind is the five, and the real figure is two orders of magnitude
  larger. **The `.blend` is still never saved by anything here**, so closing without saving is a
  complete undo; running repeatedly against one long-lived Blender is what accumulates.
- **The datablock snapshot is gone**, and with it `is_dirty`. `mpfb_list_objects` is the only
  window into the scene the bridge's vocabulary offers, so what the run can see before and after
  is *the MakeHuman objects in the current scene, by name and type* — not meshes, materials,
  images, node groups, actions or collections. An orphan image datablock of the kind FR 025's
  check actually found would not be noticed today.
- **The traceback item is gone.** It resolved a line number reported from inside Blender against
  the program the record had written, and there are no programs.

What the compare still asserts, and it is worth having: **nothing that was in the scene before the
run disappeared** — no tool here is entitled to remove a MakeHuman object it did not create, and a
run that took one of the user's characters with it is the worst thing this instrument could fail
to notice — and **the asset the run equipped is gone again**, which is the one thing the run does
still put back, through `mpfb_remove_asset` rather than through any cleanup of its own. Everything
the run added is named in the item's output, so a passing line says what was left behind rather
than implying nothing was.

Restoring more than that means giving the bridge commands that serve an instrument rather than a
tool. That is a real option and a real cost, and it is
[in NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md) as its own question rather than settled here.

### Where an exhaustive live check goes

Into the feature request that needs it — its own subdir, run during that effort, moved into
`done/` with it. What an effort adds *here* is at most the one smoke item for a tool it introduced.
[FR 023](../feature-requests/done/023-verification-smoke-test/README.md)
is the request that made this the rule, and its own check,
[`check_negatives.py`](../feature-requests/done/023-verification-smoke-test/check_negatives.py),
is the first thing written under it.

## Timing

The run reports its own total and its three slowest items. **Sixty seconds is a design target, not
a gate**: exceeding it does not fail the run and does not change the exit code, which is decided
by the checks alone. Wall clock against somebody else's Blender is too noisy and too
install-dependent to gate on, and a check that fails for a reason outside the repository is one
people learn to ignore.

Last measured at **1.5 s**, 36 items, 0 failed, 0 skipped (FR 040) — a headless Blender 5.1.0,
MPFB `FROM_SOURCE`, blender_mcp disabled in that process. That run started the bridge through the
add-on's own `cli.cli_execute()` from `--python-expr` rather than with `--command mpfb_bridge`,
because the add-on was installed in two extension repositories on that machine, both symlinks to
this checkout, and Blender refuses a command registered twice. The measurement before it was
1.5 s for 27 items with 938 assets across the library. The same run in a windowed Blender on the same machine took 4.9 s. For
scale: the last measurement of the generated code path this harness used to run on was **48.5 s**
for the same twenty-five tools, and the twelvefold gap is the pivot's whole point measured in one
session. It was never about what either add-on computed — the bridge sends parameters where the
generated path sent programs, and the add-on on the other end read one 4 KB chunk of a request per
timer tick.

The three slowest items are now `mpfb_create_human_from_preset` (0.4 s), `mpfb_add_asset` (0.3 s)
and `mpfb_generate_rigify_rig` (0.3 s). The first is the one item whose cost is irreducible: it
builds a whole second character, which is the only honest way to call that tool.

## What it does to the Blender it is pointed at

- Builds in whatever scene that Blender has open, and **leaves what it built there** — see
  [what FR 033 cost this instrument](#what-fr-033-cost-this-instrument). **The `.blend` is never
  saved by anything here**, so nothing is permanent unless the user saves it.
- Compares the MakeHuman objects in the scene before and after: nothing that predates the run may
  disappear, and the equipped asset must be gone again. The compare is itself an item, so both are
  failures rather than footnotes.
- **Exactly three files are written outside the `.blend`**, and they are the same three on every
  run: `human.mpfbmcp_smoke_run.json` in MPFB's user config directory, left there by the
  `mpfb_save_preset` item (FR 025), `mpfbmcp_smoke_run.json` in the expressions directory of
  MPFB's user data, left there by the `mpfb_save_expression` item (FR 027), and
  `mpfbmcp_smoke_run.fbx` in the export directory - the MPFB Bridge's preference or `--export-dir`,
  else `<MPFB user data>/exports` - left there by the `mpfb_export_character` item (FR 039). The
  names say where they came from and are constant, so repeated runs leave three files rather than
  a growing pile, and all three items pass `overwrite=True` — with one exception below, the only arguments in the whole
  table not left at their default — because the default is correct and would make each item pass once and fail forever
  after. **The expression is visible in MPFB's own expressions-library panel**, which the preset
  is too, in MPFB's preset dropdown. FR 027 weighed keeping its item refusal-only instead and
  did not: a mutating item must come back `performed: true`, and a smoke item that never writes
  would never find out that writing broke. Delete them by hand if you want them gone; nothing here
  does.
- **The `mpfb_set_material_settings` item names one socket**, the other non-default argument in the
  table: the call naming nothing - what FR 040 planned as its item - answers `performed: false`,
  which the rule above does not allow. It writes the first writable float on the first colour
  adjustment the read reports, back to the value it already holds, so the scene is left as it was
  found. Which socket that is comes from the read, since the names are MPFB's.
- **One item leaves a whole second character**: `mpfb_create_export_copy` copies the run's
  character with MPFB's Export copy panel's defaults, into an "export copy" collection, and the
  copy stays, as everything else the run builds does. The export item writes that copy.
- **One item leaves a custom property on the character**: `mpfb_apply_expressions` writes MPFB's
  applied-expressions stack (`mpfb_applied_expressions`) on the run's basemesh, which the
  `mpfb_save_preset` item then serializes. It is inside the `.blend` and goes with the character. Before FR 025 this line said *nothing* outside the `.blend` was written, which
  had been true since FR 013's three deliberate exceptions — probe targets in MPFB's user `custom`
  directory, `enhanced_settings.default.json` moved aside, a `.mhmat` written beside an asset —
  left with the checklists that needed them. The probe targets went to
  [FR 019](../feature-requests/done/019-file-mpfb-defects/), which is where they belong: one of
  them prevents MPFB from loading if it is left on disk when Blender starts.
- Two things it still **cannot** put back, both from FR 013's non-functional requirements: MPFB's
  asset-list cache and loaded previews, and `AssetService.alternative_materials_for_asset()`'s
  module-level cache. Both need a restarted Blender, not a call.

## Layout

**Four files, and the count is the ceiling.** A fifth means the pivot has been undone and should
be argued as its own feature request.

| File | What it is |
|------|------------|
| `smoke.py` | The item table and the run. A new tool adds one entry here and no new file |
| `harness.py` | The tool callables, the scene compare, and the report |
| `fixtures.py` | The install gate and the one character the whole run acts on |
| `README.md` | This |

Two rules bound the growth, and only one is mechanical. **Coverage is derived from the registry**:
the item table is matched against the built server before anything runs, so a registered tool with
no item — or an item for a tool that is gone — stops the run with exit code 2.
[tests/test_verification_smoke.py](../tests/test_verification_smoke.py) asserts the same without a
Blender, so the rule also fires in the unit run. **The time is bounded by design**
instead — one character, one call per tool, three assertions — and kept honest by being printed on
every run rather than by a threshold.

## Where the old checklists went

FR 013 built eight `check_frNNN.py` scripts, a cost-measurement script and a duplication census.
FR 023 deleted them. Their findings are folded into [specifications/](../specifications/), into
[HISTORY.md](../feature-requests/HISTORY.md) and into each request's own README under
`feature-requests/done/`; git holds the scripts themselves if a question ever needs re-asking. A
`done/` request whose README links one of them is linking into history, which is what a finished
request is.

One survived, because it was never a check of mpfb-mcp's tools: `check_mpfb_issues.py` provokes
defects in *MPFB*, and it moved to
[feature-requests/done/019-file-mpfb-defects/](../feature-requests/done/019-file-mpfb-defects/),
beside the report it backs.
