# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

<a id="selection-restore-covers-one-object"></a>

## Selection restore covers one object

Found by FR 036's census and asserted, as a gap, by `bbb_shared/selection_test.py`. The ten
mutating commands that activate something put back the active object and the *borrowed* object's
own selection, through `shared/selection.py`. An operator that selects *other* objects - a new
armature from `mpfb_add_rig`, an imported garment from `mpfb_add_asset` - leaves them selected, so
the user's selection after the call is not the one they had. Closing it means snapshotting every
object's selection on the way in, which changes what several commands leave behind and is a
behaviour change to announce, not a refactoring. `mpfb_generate_rigify_rig` is a separate case
already: it reports `active_object_after` because it cannot restore.

<a id="one-helper-for-the-tool-under-test"></a>

## One helper for the tool under test

Found by FR 036's census, which did not search `tests/`. Twenty-nine functions in `tests/` reach
into FastMCP's private `mcp._tool_manager._tools` to get the callable behind a tool
(`_tool_callable` twenty times, `_register_and_get_tool` nine), and every copy differs only in
which tool it names. Under the rule for shared code
([rule 2](../specifications/architecture.md#shared-modules-and-what-warrants-one)) that is plainly
one concept, and one helper would also put the reach into a *private* attribute of a pinned
dependency in one place rather than twenty-nine, which matters the day `mcp` is upgraded. The
bridge suite has the same shape in `_result`, seventeen copies, one per module, each unwrapping a
dispatch envelope for its own command. A test-harness effort, and a small one.

<a id="create-human-typeerror"></a>

## `mpfb_create_human` refuses a non-number with a `TypeError`

Found by FR 036's `tool_refusals.py`. Every other tool refuses a bad argument shape with a
`ValueError` whose sentence names the argument; `mpfb_create_human`'s slider check compares the
value with `0.0 <= value <= 1.0` before checking its type, so `age="x"` fails with
`TypeError: '<=' not supported between instances of 'float' and 'str'`, and `age=None` the same
way. FastMCP reports either as a tool error, so nothing is sent, but the sentence tells an agent
nothing it can act on. The fix is a type check before the range check; its refusal sentences then
belong in a unit test, which is where FR 036 found none.

<a id="stale-anchor-links"></a>

## Stale anchor links in the documentation

Found by a link check while [FR 037](done/037-one-word-per-concept/README.md) closed. These relative
links point at an anchor that no longer exists: the file is there, the heading is not. All but the
last predate FR 037.

- `specifications/vision.md` and `CLAUDE.md` link to
  `NEXT_STEPS.md#superseded-second-backend-the-community-blender-mcp`, which has no heading or
  `<a id>` of that name any more.
- `specifications/testing.md` links to
  `NEXT_STEPS.md#file-upstream-mpfb-cannot-find-a-rigify-meta-rig-any-more`.
- `specifications/architecture.md` links to `HISTORY.md#fr-033--the-generated-code-path-retired`.
  That heading contains a markdown link, so its generated anchor is not the one written; an explicit
  `<a id>` above it would fix this and any other link to it.
- `specifications/architecture.md` links to `CLAUDE.md#the-twenty-five-tools`; the heading is "The
  thirty-two tools" now.
- `HISTORY.md` links to `NEXT_STEPS.md#should-the-bridge-serve-its-own-test-harness`.
- `bridge/mpfb_bridge/commands/list_asset_materials.py` links to
  `specifications/architecture.md#shared-fragments`, a section that was renamed when shared
  fragments became shared modules.
- `HISTORY.md`'s FR 036 entry links to `NEXT_STEPS.md#resolved-from-and-subject-resolved-by`, the
  entry FR 037 closed and removed. HISTORY is not rewritten, so this one may be left, or repointed at
  FR 037's entry.

The fix is to repoint each at the heading it meant, or drop the anchor where the section is gone. A
small script that checks every `](path#anchor)` against GitHub-style heading slugs and `<a id>` tags
would find the next one, and could become a test beside `tests/test_reference_drift.py` if drift
here turns out to recur.

<a id="direct-tests-of-the-bridges-shared-modules"></a>

## Direct tests of the bridge's shared modules

The thirteen modules in `bridge/mpfb_bridge/shared/` are tested **only through the commands that
use them**: every test that reaches one goes through dispatch. A fault in a shared module is
therefore reported as a failure in whichever command module happens to run first, and a branch no
command's fixture reaches is never reached at all.
[FR 035](done/035-bridge-test-layers/README.md) reserved the layer for this — `bbb_shared/`, which
runs after the add-on's own machinery and before any command — and did not create it, because
writing tests and moving files are different efforts and mixing them would have lost that
request's before-and-after proof. [FR 036](done/036-subject-resolver-and-duplication/README.md)
created the directory, with direct tests of the four shared modules it added; the thirteen that
existed before it remain this entry's.

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
