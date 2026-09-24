# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

<a id="one-basemesh-resolver"></a>

## Basemesh resolver and other code duplications

Formulated as [FR 036](036-subject-resolver-and-duplication/README.md) (Accepted), with the scan
this entry asks for in its [census](036-subject-resolver-and-duplication/census.md). Because the
architecture's rule for shared code was set before the pivot, the request rewrites that rule first
and derives the census verdicts from the rewritten version.

Eighteen bridge commands resolve "any object in the character's family, or the active one" to a
basemesh through `ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")`,
each inside a wrapper of its own (`_resolve`, `_resolve_basemesh`), and the copies are not the same
code even with their messages stripped. [FR 034](done/034-character-summary/README.md) moved the
`get_macro_details` copy into `shared/macro_reading.py` as `resolve_basemesh()`, where
`get_character_summary` uses it too, and left the other seventeen alone. This effort would decide
whether they should all share that one, whether the variations between them are deliberate (some
mutating commands may rightly resolve differently), and would record the differences it finds
either way.

The same effort is the natural place for the one **reading** FR 034 left duplicated:
`set_macro_details` keeps its own `_as_float`, `_macro_details_of`, `_race_sum_of` and race-sum
tolerance, and reports `macro_details` and `race_sum` from them - so its answer and
`mpfb_get_macro_details`' can drift apart in exactly the way `shared/macro_reading.py` exists to
prevent. It was out of FR 034's scope because the summary does not read through it.

When formulating a feature request for this, a scan should be done for other code duplications
which could or should be abstracted to shared modules. 

<a id="direct-tests-of-the-bridges-shared-modules"></a>

## Direct tests of the bridge's shared modules

The thirteen modules in `bridge/mpfb_bridge/shared/` are tested **only through the commands that
use them**: every test that reaches one goes through dispatch. A fault in a shared module is
therefore reported as a failure in whichever command module happens to run first, and a branch no
command's fixture reaches is never reached at all.
[FR 035](done/035-bridge-test-layers/README.md) reserved the layer for this — `bbb_shared/`, which
runs after the add-on's own machinery and before any command — and did not create it, because
writing tests and moving files are different efforts and mixing them would have lost that
request's before-and-after proof. [FR 036](036-subject-resolver-and-duplication/README.md) creates
the directory for the shared modules *it* adds; the thirteen that exist remain this entry's.

Three of them read nothing out of MPFB's services and could be tested without a character, or
without MPFB at all: `artifact_names.py` (the name rule; its tool-side twin is already tested
exhaustively in `tests/test_save_preset.py`, the bridge copy only through the two save commands),
`performed.py`, and `expression_panel.py`, whose failure branches — the UI module absent from
`sys.modules`, a call that raises — are exactly the lines no command test reaches. The coverage
report after FR 035 put the shared modules between 73% and 100% line coverage, all of it through
dispatch; the uncovered lines are listed per module in `bridge/test/coverage/`, and are the place
to start.

## Visemes and lip sync

The rest of `FaceService`, deliberately excluded from both expression requests
([FR 026](done/026-face-units/README.md#not-visemes),
[FR 027](done/027-expression-library/README.md)): `MICROSOFT_VISEMES` and `META_VISEMES`,
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

## Exporting characters

Need to have a tool for exporting a character to, for example, fbx. This should involve 
similar procedures as is used in `src/mpfb/ui/operations/exportops` in MPFB.
