# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## Modeling

Most of the things in this section is done via TargetService. Both subsections below are now
scoped into numbered requests; the bullets are kept as the original statement of what was wanted.

### Macrodetails / phenotype — [FR 007](007-macro-details/README.md)

While macro details can be specified at human creation time, there are no tools for modifying
them afterwards. Things such as the following are needed:

- Getting the default macro dict (from TargetService)
- Getting the current macro details as a dict (from a named human or from active human)
- Modifying the macro detail settings and recalculating the macro stack

Scoped as [FR 007](007-macro-details/README.md): `mpfb_get_macro_details`,
`mpfb_set_macro_details` and — added there, because a shape change invalidates the fit of every
asset on the character and MPFB's own auto-refit defaults to off — `mpfb_refit_human`.

The question of whether `mpfb_create_human` should move from separate parameters to a macro detail
dict is **answered there: it should not.** Flat scalar parameters are what an MCP tool schema
describes and validates well, and `mpfb_set_macro_details` mirrors the same eleven names with every
one optional, which is a distinction ("leave unchanged") a dict cannot express. Round-tripping is
preserved on the output side instead, since both tools return the full nested dict. See
[FR 007](007-macro-details/README.md#the-mpfb_create_human-parameter-shape-question).

### Detail targets — [FR 008](008-detail-targets/README.md)

There is currently no tool at all for working with detail targets. Things such as the following
are needed:

- Inspecting the target stack (optionally filtering out macro details)
- Applying a single target
- Modifying the value of a single target
- Ensuring left-right symmetry
- Batch loading targets

Scoped as [FR 008](008-detail-targets/README.md): `mpfb_get_target_stack`, `mpfb_set_targets` and
`mpfb_symmetrize_targets`. Three decisions taken there are worth knowing about from here. Applying
a target and changing its value are the *same* operation in MPFB and are one tool argument, not two.
Targets are addressable at two levels — the `target.json` category level, a modifier in -1..+1 built
from a pair of opposing targets with optional left/right sides, which is what MPFB's own sliders
manipulate; and the raw shape-key level, which is the only way to reach a user-installed target.
And batching is not a separate "batch load" tool but the shape of the mutating tool itself, since a
socket round trip costs about a second and the work inside it costs milliseconds.

## Loading / applying assets

The next logical step would be the ability to add assets to a character. All three bullets below
are now scoped into numbered requests, one per domain; the bullets are kept as the original
statement of what was wanted.

- Add rig, including a custom rig — [FR 009](009-add-rig/README.md)
- Add an MHCLO asset: needs to take asset type and material type as parameters —
  [FR 010](010-mesh-assets/README.md)
- Set skin: needs to take material type as parameter — [FR 011](011-skin-and-materials/README.md)

The split is by domain rather than by size: rigs go through a different, non-interchangeable pair
of `HumanService` functions; an MHCLO asset is an imported object; and a skin is a material applied
to objects that already exist. Three decisions taken across them are worth knowing about from here.

**Removing is in scope alongside adding**, for mesh assets. `HumanService.unload_mhclo_asset()` also
takes off the delete-group mask modifier and the garment's sub-rig, neither of which a plain object
deletion through generic blender_mcp would touch — so without it an agent that equips the wrong
garment has no correct way to take it off. Removing a *rig* is deliberately not in scope: MPFB has
no unload counterpart for it, and [FR 009](009-add-rig/README.md) refuses to add a second rig rather
than pretend otherwise.

**Ordering between the three is a real constraint that produces no error.**
`add_mhclo_asset()` rigs a garment only if a rig exists at that moment, and nothing re-rigs it
afterwards; Rigify generation has to come after the garments. MPFB's own character builder documents
this in comments. None of the tools can enforce it, so each reports when it can see the caller
violating it — a convention [FR 009](009-add-rig/README.md) proposes recording in
[architecture.md](../specifications/architecture.md).

**Adding is one asset per call**, not batched like [FR 008](008-detail-targets/README.md)'s target
setting: loading an MHCLO is seconds of mesh import and vertex fitting, so the ~1 s socket round trip
does not dominate and the argument that made batching mandatory there does not carry over.

### Still unscoped in this area

- **Poses.** `mpfb_list_assets` reports the `poses` subdir, so the catalogue currently names things
  no tool can apply. `AnimationService.import_bvh_file_as_pose()` is the operation; it is
  destructive (it changes bone rolls) and only works on the `default` rig, which makes it a request
  of its own rather than a fourth bullet above.
- **Ink layers.** Likewise listed by `mpfb_list_assets` (`ink_layers`) and likewise a different
  mechanism: `MaterialService.load_ink_layer()` adds a UV map and a layer to an existing MakeSkin or
  Layered skin material, works on no other material type, and is invisible when a body proxy is
  present.
- **Installing asset packs and targets** (`mpfb.load_pack`, `mpfb.install_target`) — the operations
  that put new entries into the catalogues in the first place.

## Observability

Logging should be added so that it is possible to see the exact python code sent to blender,
and the reponses that came back.

## Second backend: the community "blender mcp"

mpfb-mcp should also run against the community [blender-mcp](https://github.com/ahujasid/blender-mcp)
add-on, not only blender lab's, so that a user who already has that one installed does not have
to install a second. This is settled as a goal — see
[vision.md](../specifications/vision.md#resolved-which-blender-mcp-both) for the resolution and
for what comparing the two add-ons turned up: the substantive difference is the result channel
(the exec namespace's `result` dict, against captured stdout), so the seam is a backend adapter
below `send_code()` that translates transport and result channel together, leaving the tools,
the payloads and `codegen/` untouched. Not yet scoped into a numbered request.
