# verification/

The live-verification harness. Not part of the installed package, not discovered by
`python3 -m unittest discover -s tests`, and not shipped: `pyproject.toml` declares package
data by explicit glob under `src/`, so a top-level directory outside it cannot be picked up.

It exists because [FR 013](../feature-requests/done/013-live-verification/README.md) found that the
reason five requests landed unverified was not laziness but cost: FR 006's live session built a
character by hand, snapshotted twelve datablock collections by hand, compared them by hand, and
then threw all of it away. Re-running a checklist after a code fix is now one command.

## Requirements

A running Blender with MPFB and the blender_mcp add-on enabled and its socket server started
(see [CLAUDE.md](../CLAUDE.md#commands)). `run_all.py` checks the install before it starts
rather than discovering a gap halfway through: MPFB initialized, Rigify enabled, at least one
custom rig, at least one skin, and the specific assets the checklists name.

**One harness process at a time.** Two of them against one Blender interleave - both build
objects called `Human` and both delete what they find - so the second one fails in ways that
look like tool defects.

## Running

```bash
# Everything, in the order where each checklist pays for the next.
MPFB_MCP_RECORD_DIR=~/mpfb-mcp-records PYTHONPATH=. python3 verification/run_all.py

# One checklist, after a fix.
MPFB_MCP_RECORD_DIR=~/mpfb-mcp-records PYTHONPATH=. python3 verification/check_fr010.py

# FR-8's cost measurements. Minutes, and nothing depends on them.
PYTHONPATH=. python3 verification/measure.py

# The confirmed and refuted MPFB defects, provoked against this install.
PYTHONPATH=. python3 verification/check_mpfb_issues.py
```

`MPFB_MCP_RECORD_DIR` is optional but wanted: with it, every call leaves the exact program, the
exact envelope and a duration behind, which is what makes a failure diagnosable rather than
merely visible. `check_fr012.py` needs it and skips its main item without it. Each script also
writes its full result - the printed lines are capped, the file is not - into
`verification/results/`, overridable with `MPFB_MCP_VERIFICATION_RESULTS`.

## What it does to the Blender it is pointed at

- Builds in a scene of its own, `MPFBMCP_VERIFY`, created on first use. Nothing outside it is
  touched, and **the `.blend` is never saved by anything here**.
- Snapshots twelve datablock collections plus `bpy.data.is_dirty` before each checklist and
  compares afterwards; the compare is itself a checklist item, so a leak is a failure rather
  than a footnote.
- Three things it changes outside the `.blend`, each deliberate and each put back:
  three probe targets written into MPFB's user `custom` directory and removed again
  (`fixtures.install_probe_targets`) — **read the note beside `PROBE_TARGETS` before changing
  them**, because one of the three prevents MPFB from loading if it is left on disk when Blender
  starts, which is how that MPFB defect was found;
  `enhanced_settings.default.json` moved aside and restored,
  which is the only way to observe the creation FR 011 asks about; and one `.mhmat` written
  beside an asset and deleted, for the cache-staleness item.
- Two things it **cannot** put back, both documented in FR 013's non-functional requirements:
  MPFB's asset-list cache and loaded previews, and
  `AssetService.alternative_materials_for_asset()`'s module-level cache. Both need a restarted
  Blender, not a call.

## Layout

| File | What it is |
|------|------------|
| `harness.py` | Tool callables, the scratch scene, snapshot/compare, the probe channel into Blender, and the pass/fail report. The mutating tool callables come back wrapped in the `performed` audit, so every checklist gets that check on the calls it already makes and reports it in its summary |
| `fixtures.py` | The install check, the probe targets, and the characters - `ensure_character_a` is idempotent, so a checklist run alone builds exactly as much as it needs |
| `check_fr0NN.py` | One script per checklist, each self-sufficient |
| `measure.py` | FR-8's four measurements |
| `check_mpfb_issues.py` | The MPFB defects, provoked rather than described. Its assertions are written so that a **fixed** MPFB makes them fail |
| `run_all.py` | The sequence, and the install gate |

## A note on what the checks compare against

Where a checklist says "the same as MPFB's own panel", the check is a diff and not a
screenshot. MPFB's panels are thin: the phenotype slider is a `FloatProperty` whose setter
calls `TargetService.reapply_macro_details()`, the asset library button calls
`HumanService.add_mhclo_asset()`, the rig button calls `add_builtin_rig()`. Driving those
properties and operators from a probe *is* pressing the button, so the comparison is between
two objects in one file rather than between a tool and a memory of a UI.

Two comparisons are genuinely not automatable this way and are marked as such rather than
approximated: anything depending on `ui/model/_modelsubpanels.py`'s category table, which is
built at module import time and therefore cannot see a target installed after Blender started.
