# File the confirmed MPFB defects against ../mpfb2

**Status:** Done

Five requests ended by naming things in MPFB that looked like defects, all read from source and
none observed. [FR 013](../013-live-verification/README.md)'s live session provoked each one
against a running install and, deliberately, wrote the provocations down as a script
([check_mpfb_issues.py](check_mpfb_issues.py)) rather than as prose.
Four of the seven were confirmed, two refuted outright, and one turned out worse and quieter than
described. A sixth was found by accident, and it is the most serious of the set.

Nothing has been filed. That is what this request is for, and it is deliberately separate: filing
a defect against somebody else's project is a communication task, not a code change, and folding it
into the effort that found the evidence would have made both worse.

**What "filing" means here.** Not an issue in a tracker: it means writing a summary of the
confirmed defects to
[../mpfb2/features/MCP_DISCOVERED_BUGS.md](../../../../mpfb2/features/MCP_DISCOVERED_BUGS.md), one
section per defect, in the directory where that project already keeps its own investigations. That
is the whole deliverable — a document handed to MPFB's own effort, not a promise from it.

**Filing is not fixing, and this repository should not plan as if it were.** MPFB has its own
priorities and none of these defects is owed a fix on any particular timescale; several may stand
for a long time, and one of them may be judged rare enough not to be worth the change. So **every
workaround mpfb-mcp carries for these defects stays exactly where it is**, and a section appearing
in `MCP_DISCOVERED_BUGS.md` is not a reason to remove one. A workaround goes when a *running* MPFB
no longer needs it — which is precisely what `check_mpfb_issues.py` is built to
detect, by failing the day a defect is gone.

**The one to file first**: a user target whose filename is over 56 characters **prevents MPFB from
loading at all**. `ui/model/_modelsubpanels.py` registers each synthesized modeling category as a
Scene property named `"custom_" + name` at module import time; Blender rejects an identifier over
63 characters with a `ValueError`; nothing catches it, so it propagates out of MPFB's `register()`.
FR 013 hit this by leaving a probe target on disk across a Blender restart, and MPFB did not come
back. The sharp form is that `TargetService`'s own name *encoding* starts above 60 characters while
registration breaks above 56 — so an encoded user target cannot exist in a scanned directory at
all.

## Goals

**Primary: file the five confirmed defects** in `MCP_DISCOVERED_BUGS.md`, each with a
reproduction that runs rather than a description that has to be believed.

**Secondary: correct this repository where a refuted candidate is still cited as a reason.** Two of
the seven were wrong, and a decision whose stated reason is wrong is harder to revisit than one
that never gave a reason.

## Functional requirements

- **FR-1.** Write, to
  [../mpfb2/features/MCP_DISCOVERED_BUGS.md](../../../../mpfb2/features/MCP_DISCOVERED_BUGS.md), one
  section for each of the five confirmed:
  1. **A long-named user target prevents registration.** The one above. Severity is the argument:
     it disables the add-on, and the trigger is a file the user put in a directory MPFB told them
     to use.
  2. **A gzipped custom target is addressed under two names.** `_modelsubpanels` builds
     `vwide.gz` (a substring `.replace(".target", "")` that does not strip `.gz`);
     `TargetService.filename_to_shapekey_name()` builds `vwide`. FR 013 observed **both shape keys
     on one mesh at different values**, from one file.
  3. **`set_character_skin()` destroys materials on an unrecognised `skin_type`.** Five `if`
     statements with no `else`, after `delete_all_materials()`. With `material_instances` off —
     the default for three of the five types — it raises **nothing**, leaving a character with no
     materials and no error.
  4. **`unload_mhclo_asset()` deletes whatever object it is handed**, without checking it is a mesh
     asset. Confirmed against an ordinary cube.
  5. **`alternative_materials_for_asset()`'s `exclude_default` is accepted and never read.**
- **FR-2.** File in the same document, or decide not to, the two secondary observations: that
  `ObjectService.object_is_rigify_metarig()` reads `blender_object.pose.bones` without checking and
  raises for an armature whose `pose` is `None`; and that MPFB's proxy library operator
  reimplements `_check_add_proxy()` rather than calling it — a duplication that agrees today.
- **FR-3.** Each section names the reproduction in `check_mpfb_issues.py` that
  provokes it, so it can be re-run against a future MPFB rather than re-argued.
- **FR-4.** **No workaround, coercion or defensive check in this repository is removed by this
  effort.** Filing changes nothing about what MPFB does today, and the tools go on coping with
  every one of these defects exactly as they do now.
- **FR-5.** The two refuted candidates are corrected wherever this repository still cites them:
  `RigService.identify_rig()` **cannot** return `None`, and the alternative-material cache **does**
  have an invalidator. Both have already been corrected in the verification records; check the
  payload docstrings and [specifications/](../../../specifications/) too.

## Non-functional requirements

**A defect report is a claim about someone else's code and should be no stronger than the
evidence.** Two of seven were wrong. Each section says what was observed, on what version, and
what was inferred.

**The document is written for a reader who did not run the session.** `MCP_DISCOVERED_BUGS.md`
lands in a repository whose developers have no access to this one's verification records, so each
section stands on its own: the symptom, the code path, what was observed, and what a fix would have
to change.

**Reproductions, not descriptions.** The script exists; use it.

## Architecture

No code change in this repository beyond FR-5's corrections. `check_mpfb_issues.py`
is the artifact; it runs against the install it is pointed at and prints one line per defect with
the observed value. Outside this repository the effort writes a single Markdown file,
`../mpfb2/features/MCP_DISCOVERED_BUGS.md`, and nothing else.

**Note on the first one and this repository's own conduct.** The harness caused that outage on a
user's install. `verification/fixtures.py` now carries `SAFE_AT_STARTUP` and the long probe target
is installed and removed within a single checklist run. Anything this repository writes into an
MPFB data directory should be held to the same rule.

## Affected specifications

- **[specifications/mpfb-integration.md](../../../specifications/mpfb-integration.md)** —
  [Where MPFB's own code paths disagree](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)
  already carries FR 013's correction that a candidate defect must be confirmed before it is filed.
  It gains one sentence naming where a confirmed defect is written down — and saying that writing
  it down there neither removes the workaround nor changes what a tool does, since MPFB may not fix
  it for a long time. Expect no further change unless FR-5 finds a stale citation.

## Tests

No unit tests. `check_mpfb_issues.py` is the test, and its assertions are written so
that a fixed MPFB makes them **fail** — which is the point: the day one of these is fixed upstream,
this repository should find out from a red line rather than from a changelog.

## References

- [FR 013's review](../013-live-verification/review.md#the-seven-candidate-mpfb-defects) — what
  was confirmed, what was refuted, and on what evidence.
- [FR 008](../008-detail-targets/README.md#verification-status) — the gzip divergence and the
  registration failure, both observed there.
- [NEXT_STEPS.md](../../NEXT_STEPS.md#file-the-4-kb-chunked-read-against-blender_mcp) — a **sixth**
  defect to report, in the same shape as these five and against a different project:
  [FR 017](../017-category-table-cost/README.md) measured that blender_mcp's add-on reads one
  4 KB chunk of a request per timer tick, which is the dominant cost of every tool here. It is kept
  separate deliberately, since this request's scope is `../mpfb2`, but whoever writes these five is
  the right person to write that one.

---

**Note added by [FR 023](../023-verification-smoke-test/README.md):** `check_mpfb_issues.py` moved
out of `verification/` and into this subdir. It was never a check of mpfb-mcp's tools — it provokes
defects in MPFB, on behalf of the report above — and it writes into MPFB's user `custom` directory,
which the smoke run in `verification/` never does. The three probe targets came with it, including
the long-named one that prevents MPFB from loading if it is left on disk when Blender starts. The
paths [`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../../../mpfb2/features/MCP_DISCOVERED_BUGS.md)
cites were re-pointed in the same change.

The Architecture note above says `verification/fixtures.py` carries `SAFE_AT_STARTUP`. It no longer
exists: it was there for a checklist that wanted a probe target to survive a restart, and that
checklist is gone. The rule it encoded still holds and is now the only rule — the three probe
targets are installed and removed inside one run of `check_mpfb_issues.py`, and nothing else in
this project writes into an MPFB data directory at all.
