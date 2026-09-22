# verification/

**A smoke test.** One item per tool, called the way an MCP client would call it with default
arguments, against a real Blender. It answers one question — *does every tool still work at
all?* — and it answers it in well under a minute, so there is no reason to skip it.

One item reaches no Blender at all: `mpfb_list_docs` is a local table, so its item establishes only
that the tool is registered and still answers with the keys its description promises. It is a
per-tool item anyway, because coverage is derived from the registry and the run-level set is closed
at three.

Not part of the installed package, not discovered by `python3 -m unittest discover -s tests`, and
not shipped: `pyproject.toml` declares package data by explicit glob under `src/`, so a top-level
directory outside it cannot be picked up.

## Running

```bash
MPFB_MCP_RECORD_DIR=~/mpfb-mcp-records PYTHONPATH=. python3 verification/smoke.py
```

That is the whole interface. `MPFB_MCP_RECORD_DIR` is optional: with it, every call leaves the
exact program, the exact envelope and a duration behind, which is what makes a failure diagnosable
rather than merely visible — and one run-level item, the traceback check, needs it and skips
without it. The run also writes its full result — the printed lines are capped, the file is not —
into `verification/results/`, overridable with `MPFB_MCP_VERIFICATION_RESULTS`.

**Requirements: one Blender with MPFB, blender_mcp *and* the MPFB Bridge enabled, and both socket
servers started (9876 and 9877) — in the default configuration.** That is new since
[FR 032](../feature-requests/done/032-creation-and-modification-migrated/README.md) flipped the
default backend to the bridge, and it is worth saying plainly rather than leaving to be met as a
puzzle.

The reason is one-sided. Every one of the twenty-four tools that crosses the socket now has a
bridge command, so the *tools* need only the bridge — but this harness's own scene bookkeeping (the
scratch scene, the snapshots, the cleanup) goes through `send_code()` directly, because it is
instrument rather than tool. So the run needs blender_mcp for its own plumbing whichever backend
the tools are on.

**This is the last effort in which that is true.** [FR 033](../feature-requests/033-retire-the-generated-code-path/README.md)
retires the generated path and rewrites this harness's bookkeeping with it, after which a run needs
the bridge alone.

The two configurations must both pass, and the run is otherwise identical:

```bash
PYTHONPATH=. python3 verification/smoke.py
MPFB_MCP_BACKEND=blender_mcp PYTHONPATH=. python3 verification/smoke.py
```

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

**So where does an exhaustive live check go?** Into the feature request that needs it — its own
subdir, run during that effort, moved into `done/` with it. What an effort adds *here* is at most
the one smoke item for a tool it introduced. [FR 023](../feature-requests/done/023-verification-smoke-test/README.md)
is the request that made this the rule, and its own check,
[`check_negatives.py`](../feature-requests/done/023-verification-smoke-test/check_negatives.py),
is the first thing written under it.

## Timing

The run reports its own total and its three slowest items. **Sixty seconds is a design target, not
a gate**: exceeding it does not fail the run and does not change the exit code, which is decided
by the checks alone. Wall clock against somebody else's Blender is too noisy and too
install-dependent to gate on, and a check that fails for a reason outside the repository is one
people learn to ignore.

Last measured at **3.9 s** on the bridge and **48.5 s** on the generated path, 28 items, 0 failed,
1 skipped — Blender 5.1.0, MPFB 2.0.17 `FROM_SOURCE`, 909 assets across 112 packs, and
blender_mcp's `timer_interval_active` at its **0.25 s default**. The twelvefold gap between the two
is the pivot's whole point measured on one machine in one session, and it is the 4 KB chunked read
rather than anything either add-on computes: the bridge sends parameters where the generated path
sends programs. Everything below is about the slow path, and stops applying on the day FR 033
deletes it. That last number matters more than the machine: the add-on reads one 4 KB
chunk of a request per timer tick, so it is the dominant cost of every call here and 0.05 s makes
the whole run several times faster (see [CLAUDE.md](../CLAUDE.md#commands) and
[architecture.md](../specifications/architecture.md#what-a-call-costs-is-the-size-of-its-program)).
The figure above is therefore the slow configuration, which is the honest one to quote. If a run
goes over target, that setting is the first thing to check.

The three slowest items on that run were `mpfb_set_targets` (7.8 s, two extra catalogue calls to
find a left/right category plus the write), `mpfb_add_asset` (4.5 s) and `mpfb_set_skin` (3.8 s).
`mpfb_create_human_from_preset` is the fourth at 3.2 s, and it is the one item whose cost is
irreducible: it builds a whole second character, which is the only honest way to call that tool.

## What it does to the Blender it is pointed at

- Builds in a scene of its own, `MPFBMCP_VERIFY`, created on first use. Nothing outside it is
  touched, and **the `.blend` is never saved by anything here**.
- Snapshots twelve datablock collections plus `bpy.data.is_dirty` before the run and compares
  after cleanup. The compare is itself an item, so a leak is a failure rather than a footnote.
- **Exactly one file is written outside the `.blend`**, and it is the same file on every run:
  `human.mpfbmcp_smoke_run.json` in MPFB's user config directory, left there by the
  `mpfb_save_preset` item (FR 025). The name says where it came from and is constant, so repeated
  runs leave one file rather than a growing pile, and the item passes `overwrite=True` — the only
  argument in the whole table that is not left at its default — because the default is correct and
  would make the item pass once and fail forever after. Delete it by hand if you want it gone;
  nothing here does. Before FR 025 this line said *nothing* outside the `.blend` was written, which
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
| `harness.py` | The tool callables, the scratch scene, snapshot/compare, the probe channel into Blender, and the report |
| `fixtures.py` | The install gate and the one character the whole run acts on |
| `README.md` | This |

Two rules bound the growth, and only one is mechanical. **Coverage is derived from the registry**:
the item table is matched against the built server before anything runs, so a registered tool with
no item — or an item for a tool that is gone — stops the run with exit code 2.
[tests/test_verification_smoke.py](../tests/test_verification_smoke.py) asserts the same without a
Blender, so the rule also fires in the nine-second unit run. **The time is bounded by design**
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
