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

## Strange naming of bridge tests

Formulated as [FR 035](035-bridge-test-layers/README.md) (Accepted).

The test module names in bridge/test/tests adopted a three letter prefix ("aaa", "bbb"...) without
any understanding of the purpose. This was probably inspired from MPFB's test hierarchy.

The three letter prefix should only be used on folders grouping tests by what they cover. The
idea is to run primitives and shared code tests first while running larger code aggregate tests later.
The hypothesis is that if a primitive fails, there's no idea to run a test on an aggregate anyway.

The tests should be grouped accordingly in a very limited set of folders with three letter prefixes,
causing the **folders** to be run in order. The test module files themselves do not need to have
the prefix.

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
