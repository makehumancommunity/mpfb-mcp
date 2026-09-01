# File the confirmed MPFB defects against ../mpfb2

**Status:** Proposed

Five requests ended by naming things in MPFB that looked like defects, all read from source and
none observed. [FR 013](../done/013-live-verification/README.md)'s live session provoked each one
against a running install and, deliberately, wrote the provocations down as a script
([verification/check_mpfb_issues.py](../../verification/check_mpfb_issues.py)) rather than as prose.
Four of the seven were confirmed, two refuted outright, and one turned out worse and quieter than
described. A sixth was found by accident, and it is the most serious of the set.

Nothing has been filed. That is what this request is for, and it is deliberately separate: filing
an issue against somebody else's project is a communication task, not a code change, and folding it
into the effort that found the evidence would have made both worse.

**The one to file first**: a user target whose filename is over 56 characters **prevents MPFB from
loading at all**. `ui/model/_modelsubpanels.py` registers each synthesized modeling category as a
Scene property named `"custom_" + name` at module import time; Blender rejects an identifier over
63 characters with a `ValueError`; nothing catches it, so it propagates out of MPFB's `register()`.
FR 013 hit this by leaving a probe target on disk across a Blender restart, and MPFB did not come
back. The sharp form is that `TargetService`'s own name *encoding* starts above 60 characters while
registration breaks above 56 — so an encoded user target cannot exist in a scanned directory at
all.

## Goals

**Primary: file the five confirmed defects**, each with a reproduction that runs rather than a
description that has to be believed.

**Secondary: correct this repository where a refuted candidate is still cited as a reason.** Two of
the seven were wrong, and a decision whose stated reason is wrong is harder to revisit than one
that never gave a reason.

## Functional requirements

- **FR-1.** File, against [../mpfb2](../../../mpfb2), the five confirmed:
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
- **FR-2.** File, or decide not to, the two secondary observations: that
  `ObjectService.object_is_rigify_metarig()` reads `blender_object.pose.bones` without checking and
  raises for an armature whose `pose` is `None`; and that MPFB's proxy library operator
  reimplements `_check_add_proxy()` rather than calling it — a duplication that agrees today.
- **FR-3.** Each filed issue links or attaches the reproduction from
  `verification/check_mpfb_issues.py`, so it can be re-run against a future MPFB rather than
  re-argued.
- **FR-4.** The two refuted candidates are corrected wherever this repository still cites them:
  `RigService.identify_rig()` **cannot** return `None`, and the alternative-material cache **does**
  have an invalidator. Both have already been corrected in the verification records; check the
  payload docstrings and [specifications/](../../specifications/) too.

## Non-functional requirements

**A defect report is a claim about someone else's code and should be no stronger than the
evidence.** Two of seven were wrong. Each report says what was observed, on what version, and what
was inferred.

**Reproductions, not descriptions.** The script exists; use it.

## Architecture

No code change in this repository beyond FR-4's corrections. `verification/check_mpfb_issues.py`
is the artifact; it runs against the install it is pointed at and prints one line per defect with
the observed value.

**Note on the first one and this repository's own conduct.** The harness caused that outage on a
user's install. `verification/fixtures.py` now carries `SAFE_AT_STARTUP` and the long probe target
is installed and removed within a single checklist run. Anything this repository writes into an
MPFB data directory should be held to the same rule.

## Affected specifications

- **[specifications/architecture.md](../../specifications/architecture.md)** —
  [Where MPFB's own code paths disagree](../../specifications/architecture.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)
  already carries FR 013's correction that a candidate defect must be confirmed before it is filed.
  Expect no further change unless FR-4 finds a stale citation.

## Tests

No unit tests. `verification/check_mpfb_issues.py` is the test, and its assertions are written so
that a fixed MPFB makes them **fail** — which is the point: the day one of these is fixed upstream,
this repository should find out from a red line rather than from a changelog.

## References

- [FR 013's review](../done/013-live-verification/review.md#the-seven-candidate-mpfb-defects) — what
  was confirmed, what was refuted, and on what evidence.
- [FR 008](../done/008-detail-targets/README.md#verification-status) — the gzip divergence and the
  registration failure, both observed there.
