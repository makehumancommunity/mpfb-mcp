# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## Expressions

**Scoped as two requests, in this order: [FR 026](done/026-face-units/README.md) (Done) landed the
face-unit layer — `mpfb_get_face_units` and `mpfb_set_face_units`. What remains is
[FR 027](027-expression-library/README.md) (Accepted): the saved-expression library, the stack that
applies it, and `mpfb_save_expression`, which turns a composed face into a file the library can
carry. Saving was queued here as a separate entry behind FR 027 and has been folded into it, since
neither half is useful without the other; see
[its requirements](027-expression-library/README.md#mpfb_save_expression--keep-a-composed-face).**

These are the `!ex-` prefixed shape keys. They depend on particular asset packs being installed.
Expressions should be a mix of functionality from the `src/mpfb/ui/create_assets/makeexpression`
and `src/mpfb/ui/apply_assets/useexpression` UI code hierarchies in MPFB. TargetService has
some functionality for working with expressions.

## Character summary

**Scoped as [FR 034](034-character-summary/README.md) (Accepted), ordered after FR 027.**
`mpfb_get_character_summary` answers in one call what currently takes five or six: phenotype, rig,
equipped assets, skin, the target rollup, and the face (face units and the expression stack). Each
section is read by the same implementation as its detailed tool, which means moving the reading
code of `get_macro_details`, `get_object_info` and `get_target_stack` into `bridge/.../shared/`.

<a id="one-basemesh-resolver"></a>

## One basemesh resolver

Fifteen bridge commands resolve "any object in the character's family, or the active one" to a
basemesh through `ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")`,
each inside a wrapper of its own (`_resolve`, `_resolve_basemesh`), and the copies are not the same
code even with their messages stripped. [FR 034](034-character-summary/README.md) moves the
`get_macro_details` copy into `shared/macro_reading.py` and leaves the other fourteen alone. This
effort would decide whether they should all share one resolver, whether the variations between them
are deliberate (some mutating commands may rightly resolve differently), and would record the
differences it finds either way.

## Visemes and lip sync

The rest of `FaceService`, deliberately excluded from both expression requests (see
[Not visemes](done/026-face-units/README.md#not-visemes)): `MICROSOFT_VISEMES` and `META_VISEMES`,
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
