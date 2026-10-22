# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

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
  forty-one tools" now, and changes with every tool added - an explicit `<a id="the-tools">` would
  stop the drift.
- `HISTORY.md` links to `NEXT_STEPS.md#should-the-bridge-serve-its-own-test-harness`.
- `specifications/mutating-tools.md` and `HISTORY.md` linked to
  `NEXT_STEPS.md#selection-restore-covers-one-object` after the entry was pruned;
  [FR 039](done/039-exporting-characters/README.md) restored it, with what is left of it.
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
existed before it remain this entry's. [FR 041](done/041-pose-controls-and-read-back/README.md)
tested two of its three there; `pose_reading.py` is tested through `get_pose` only.

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
[FR 027](done/027-expression-library/README.md)). **Loading and interpolating landed with
[FR 039](done/039-exporting-characters/README.md)**, on an export copy only:
`mpfb_create_export_copy` calls `load_targets` and `interpolate_targets` as MPFB's Export copy panel
does. What is left is visemes on a character being worked on rather than copied for export, and
`configure_lip_sync`.

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

The session that rendered the extensions-page line-up ([FULL_SESSION.md](FULL_SESSION.md))
needed this and did without: six characters were taken out of the A-pose by rotating
`upperarm01`, `lowerarm01` and `head` by hand through blender mcp. `mpfb_list_assets` already
lists `poses` as a subdir, so the catalogue half exists and only the acting tool is missing. The way
back to the rest pose exists since [FR 042](done/042-posing-bones-switches-and-reset/README.md)
(`mpfb_reset_pose`); each pose's license still belongs with it (see
[License in the catalogues](#license-in-the-catalogues)): the only CC0 standing poses installed
there are in `poses03`, which is not named as a CC0 pack.

<a id="posing-support"></a>

## Posing support

**Both parts have landed** ([HISTORY](HISTORY.md)):
[FR 041](done/041-pose-controls-and-read-back/README.md) added the read-only `mpfb_get_pose_controls`
and `mpfb_get_pose`, with the character frame and the posing vocabulary, and
[FR 042](done/042-posing-bones-switches-and-reset/README.md) added `mpfb_set_pose_bones`,
`mpfb_set_pose_switches` (snapping by default) and `mpfb_reset_pose`; its live check rebuilt the
karate stance below with mpfb-mcp tools alone. What is left of the entry is two gaps the karate
session found that neither request took:

- **There is no hand-shape helper.** The Rigify half is scoped as
  [FR 047](047-rigify-hand-shapes/README.md) (Proposed): `mpfb_get_rigify_hand_shape` and
  `mpfb_set_rigify_hand_shape`, with six named shapes and a 0-1 `curl` and a `spread` per finger.
  It covers only rigs generated from MPFB's Rigify meta-rigs (`human`, `human_toes`). **The default
  rig and `game_engine`, including its Rigify conversion, are not in it**, and those stay here. The
  56-rotation cost below was measured on `default_no_toes`, which FR 047 refuses.

  On Rigify, a fist comes from scaling the finger master bones
  on Y (0.45 for a closed fist), not from rotating them, and FR 042's `scale_to` reaches it. On the
  default rig it means rotating three bones per finger. A `hand` argument (`fist`, `open`,
  `relaxed`, or a 0-1 curl per finger) would hide the difference between rigs.

  **Confirmed, with a number.** The man-and-woman scene session needed a soft grip on two hands of a
  `default_no_toes` rig and spent **four calls of fourteen entries each** — 56 finger-segment
  rotations — to curl, uncurl and re-curl them while hunting for a pose that did not intersect. A
  `hand` argument would have made each of those one entry. It also has to be a *curl amount*, not
  just named shapes: what the image finally needed was a loose 24/40/24-degree curl on one hand and
  none on the other, and no preset of `fist`/`open`/`relaxed` would have landed there.
- **The pose libraries cannot reach a generated Rigify rig at all**, which makes
  [Loading poses](#loading-poses) narrower than that entry assumes. There is one JSON pose per FK
  rig type (`default_fk`, `game_engine_fk`, and so on), and MPFB's panel looks for
  `<identify_rig>_ik` on any rig with an `_ik` bone, so this rig would need
  `rigify_generated.human_toes_ik`, which does not exist. The 59 BVH poses are worse. Two of them,
  `culturalibre_cl_fight_01` and `gpedroso_boxing`, would have been a good starting point for this
  stance. But `import_bvh_file_as_pose` matches bones by default-rig names, and 35 of
  `cl_fight_01`'s 163 bones also exist on the generated Rigify rig (`root`, `head`, `jaw`, the
  eyes, the breasts and every toe). It would rewrite their rolls in edit mode and give a partly
  posed, broken character without any error. A pose-loading tool must refuse a rig the pose was not
  made for. Retargeting a default-rig pose onto Rigify controls would be a separate effort.

Pose loading is the natural next step, now that there is a reset to fall back on and a writer whose
`rotate_to` takes what a saved pose would hold. Like the posing tools, it is Blender-side logic in
bridge commands that reimplements what MPFB's UI does.

<a id="sub-rig-child-of-breaks-away-from-the-origin"></a>

## A garment's sub-rig is bound wrong when it is equipped away from the origin

Found by the line-up session, and **re-diagnosed by [FR 045](HISTORY.md#placing-a-character)**,
whose live check measured it: the anchor above keeps the old title's slug, which said "breaks away
from the origin", and that turned out to be the wrong cause. `ponytail01` ships a sub-rig, and its
`root` bone gets a `CHILD_OF` on the main rig's `head` with `set_inverse_pending = True`
(`mpfb2/src/mpfb/entities/rig.py:599`). Blender resolves that inverse while the new sub-rig still
stands at the world origin, before `ClothesService.set_up_rigging()` parents it to the rig. On a
character at the origin that is right, and **the binding then survives every move**. On a
character already placed, it is off by the rig's whole transform: the hair was dragged 5.7 m, and
stayed 5.7 m out after the character was moved back to the origin. `mpfb_refit_human` re-binds it,
and it then survives moves too. The line-up session had equipped the ponytail on a character it had
already moved; its hand repair (both spaces `WORLD`, inverse recomputed) then broke on the next move
because it was a different binding.

What FR 045 delivered: `mpfb_add_asset`, `mpfb_place_character` and the summary report each badly
bound sub-rig as `subrigs_broken`, measured, naming the refit; the tool description says to dress
before placing; the defect is filed in `mpfb2/features/MCP_DISCOVERED_BUGS.md`; and
`_fixtures.write_subrigged_mhclo()` is a real sub-rig fixture that reproduces it. **What is left is
small**: whether `add_asset` should re-bind a sub-rig itself - setting the inverse pending again once
the sub-rig is parented, which is what a refit does - rather than name the refit, and whether to
propose that one-line ordering change upstream.

<a id="windowed-bridge-answers-once-a-second"></a>

## A windowed bridge answers once a second when Blender has nothing to do

Measured during [FR 045](HISTORY.md#placing-a-character): in a windowed Blender whose event loop
was idle, a `bpy.app.timers` callback asking for 0.05 s fired once a second, so every tool took
1.0 s - the smoke run 52 s where a headless bridge takes 2.1 s - although the bridge's own idle
countdown was at its active rate. [architecture.md](../specifications/architecture.md#the-bridge)
records the measurement. What is not known is why: whether Blender's window manager sleeps between
events and wakes timers late, whether it depends on the window being focused or on the platform,
and whether anything an add-on may do (a modal operator, `wm.event_simulate`-style wakes, a
redraw) shortens it without costing CPU while idle. FR 029 and FR 030 measured 50-58 ms per call
through the same timer, so this has not always been so. Worth an effort only if agents drive a windowed
Blender for long sessions; the headless bridge is unaffected.

<a id="license-in-the-catalogues"></a>

## License in the catalogues

**The assets and their materials have landed** as
[FR 046](done/046-license-in-the-catalogues/README.md) ([HISTORY](HISTORY.md)): `license`,
`author`, `source_url` and `packs` on every row of `mpfb_list_assets` and
`mpfb_list_asset_materials`, a `license` filter with `counts_by_license`, and the license of an
equipped asset and its material in `mpfb_get_object_info` and the summary. Two catalogues are left:

- **Targets.** 211 pack entries are targets, but a target is a file in a category directory, so
  the directory join attributes nothing, and a stem join over target names has not been measured.
  `shared/pack_attribution.py`'s stem fallback is the mechanism; what is missing is the measurement
  that says it holds for targets, which FR 046's `live_check.py` did for the asset subdirs.
- **Poses**, when there is a pose catalogue (see [Loading poses](#loading-poses)). 149 pack entries
  are poses, and a pose is a file too.

<a id="a-garment-behind-a-sub-rig-is-missing-from-the-family"></a>

## A garment behind a sub-rig is missing from the family

Found by [FR 046](done/046-license-in-the-catalogues/README.md)'s live check. `ponytail01` carries
a sub-rig of its own, so it is parented to that `Subrig` rather than to the character's rig, and
MPFB's `ObjectService.find_related_objects()` does not walk past a `Subrig`. So `ponytail01` is in
neither `mpfb_get_object_info`'s `related_objects` for the basemesh nor the summary's
`equipped_assets`, though it is equipped and moves with the character. The two agree, so the
summary is not a second opinion, but a caller checking a finished character against a brief - by
license, or simply by what it wears - skips its hair.

Asked about the ponytail itself, `mpfb_get_object_info` lists the whole character, so the walk is
asymmetric rather than broken. The fix is in `shared/asset_info.py`'s `related_objects()`, which
would add each `Subrig`'s mesh children, and the question to settle first is whether MPFB's own
callers of `find_related_objects()` rely on the stop - in which case it is not MPFB's defect to
file, only this package's walk to extend.

<a id="eye-and-layered-skin-colours"></a>

## Enhanced skin settings, and MPFB's named material settings files

What [FR 040](done/040-procedural-material-settings/README.md) left out on purpose. It landed
`mpfb_get_material_settings` and `mpfb_set_material_settings` over the three procedural mechanisms
MPFB serializes into a preset - procedural eyes, the layered skin, and the MakeSkin colour
adjustment on hair, body parts and garments - see [HISTORY.md](HISTORY.md#procedural-material-settings).
Still open:

- **Enhanced skin settings**: the per-slot `colorMixIn`, roughness and pore inputs of an
  `ENHANCED`/`ENHANCED_SSS` skin (`skin_material_settings[<slot>]` in a preset). The same
  generic tools could take a fourth section; `shared/material_settings.py` is where it would be
  found, and the serializer's `"colorMixIn"` test is how.
- **MPFB's named settings files**: `eye_settings.<name>.json` and `enhanced_settings.<name>.json`
  in the user config directory, with their save/apply panels under Presets. That is a catalogue
  and an apply-by-name, and a save would be another file written outside the `.blend`.

<a id="create-human-takes-no-name"></a>

## `mpfb_create_human` takes no name, and no targets

Found by the line-up session. A cast of six is `Human` … `Human.005`, and its eyes are
`Human.high-poly` … `Human.high-poly.005`. That is harmless to the tools, which address by the
returned name, but a later session reading the scene cannot tell who is who. A `name` argument
would fix it, and the response already reports what Blender made of it, since Blender
uniquifies.

In the same session the stylised character got its rig before its targets, and had to be refitted.
`mpfb_set_targets` did say so in `assets_possibly_stale`. A `modifiers` argument on
`mpfb_create_human`, in the same shape `mpfb_set_targets` takes, would make building in the right
order the easy thing to do.

<a id="selection-restore-covers-one-object"></a>

## Selection restore covers one object

Ten mutating commands put the caller's selection back with `shared/selection.py`'s `restored()`,
which restores the active object and the **borrowed** object's own selection and nothing else, so an
object an operator selected on the way - a new armature, an imported garment - is left selected.
[FR 039](done/039-exporting-characters/README.md) added `restored_all()`, which records every
object's selection and the active object, puts them back however the block ends, and leaves what
the block created deselected; `mpfb_create_export_copy` and `mpfb_export_character` use it, the
first because MPFB's bake selects and deselects throughout, the second because an exporter writes
the selection. What is left is moving the other ten onto it. It changes what each leaves behind,
so each command's bridge test has to say what the selection is after a call, which none does today.

<a id="subdivision-on-mesh-assets-beside-shape-keys"></a>

## Subdivision on a mesh asset, beside the shape keys `interpolate` gave it

Found by [FR 039](done/039-exporting-characters/README.md)'s round trip. `mpfb_create_export_copy`'s
`subdiv_modifiers` and `mask_modifiers` act where MPFB's panel acts: on the basemesh, and when
baking on the body proxy. A garment or eyebrows keep the Subdivision `mpfb_add_asset` gave them,
and with visemes or face units interpolated onto them that is a topology-changing modifier beside
shape keys - which FBX resolves by dropping the keys. `mpfb_export_character`'s `readiness` names
each such mesh, and no tool removes the modifier. The options are an extension of the two strategies
to every copied mesh (a departure from the panel, to be named as one), or a modifier option on
`mpfb_export_character` that applies to the exporters only, where FBX's own `use_mesh_modifiers`
already lives. And the same refusal MPFB's proxy bake needs (`proxy_cannot_be_baked`) would apply
to any mesh baked under interpolated keys.

<a id="the-export-copys-bake-in-a-crowded-file"></a>

## The export copy's bake in a crowded file

[FR 039](done/039-exporting-characters/README.md) measured the worst case of `mpfb_create_export_copy`
at 7 s headless with one character and 77 s in a windowed Blender whose file held 1,876 objects:
MPFB's `ExportService._apply_modifiers_keep_shapekeys()` duplicates the body and runs
`bpy.ops.object.modifier_apply` once per shape key, and every operator pays for the whole file. 77 s
is under a third of mpfb-mcp's 300 s socket timeout, and a larger file is not. Rebuilding the keys
through the data API rather than an operator per key would be MPFB's change, worth proposing
upstream with these numbers; on this side, the choices are a longer timeout for this one command or
a progress-free warning in the answer when the shape key count and the file size predict a long
call.

<a id="viseme-pack-probes"></a>

## An install probe for the viseme packs, in MPFB

`FaceService.is_faceunits01_installed()` exists and is cached; nothing similar exists for
`visemes01` or `visemes02`, so [FR 039](done/039-exporting-characters/README.md) probes each with one
target, the silence viseme, resolved through `TargetService.target_full_path()` - the target MPFB's
`configure_lip_sync()` tests for. A request to MPFB, not a defect: `is_visemes01_installed()` and
`is_visemes02_installed()` beside the face units' probe would let this package use MPFB's own
definition, as [mpfb-integration.md](../specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack)
prefers.

<a id="no-way-to-verify-an-install-without-an-mcp-client"></a>

## No way to verify an install without an MCP client

Found by the man-and-woman scene session, which began with the server installed but not registered
with the client, and could not tell that apart from a broken one.

Everything needed to diagnose it exists, and none of it is reachable without a working MCP client
already in place. `mpfb_get_status` answers this question precisely — it is the tool whose whole
purpose is "is MPFB present, initialized and correctly configured?", and it is documented as the
one that "always answers rather than failing" — but calling it requires the client registration
that is the thing in doubt. The session's workaround was to hand-write a JSON-RPC stdio probe
(`initialize`, `notifications/initialized`, `tools/call`) against `.venv/bin/mpfb-mcp` to confirm
the server started, spoke the protocol, listed 42 tools and round-tripped to the bridge. That is
forty lines of client to answer a yes/no question, and nothing in [INSTALL.md](../INSTALL.md)
suggests it.

A `mpfb-mcp --selftest` (or `doctor`) subcommand on the existing console script would close this:
start the server in-process, run the same `mpfb_get_status` call, and print the protocol version
handshake, the tool count, the bridge host and port actually used, and whether the bridge answered
— then exit non-zero if it did not. It is the one command an install guide can end with, the one a
user can paste into a bug report, and the only way to separate "the bridge is not running" from
"the add-on is not enabled" from "the client never started the server" without a client. It needs
no new bridge command: the protocol-version check at connect time and `get_mpfb_status` already
carry every fact it would print.

Worth saying in `INSTALL.md` either way: the Blender half can be verified on its own, because the
bridge's port shows up in `ss -ltnp | grep 9877` when the add-on is enabled and not otherwise.
That single line distinguishes the two most common failures and costs nothing to document.

<a id="a-summary-mode-for-the-asset-catalogue"></a>

## A summary mode for the asset catalogue

Also from the scene session, and deliberately *not* an argument against the cap. `mpfb_list_assets`
is documented as "a filtering tool rather than a listing one", its answer is capped on purpose, and
`truncated` / `total_count` exist so a caller cannot mistake a page for the library. That design is
right for "find me a garment".

It is the wrong shape for the question a session actually opens with, which is *what is in this
install at all* — how many garments, hair, skins and poses there are, how they divide across packs,
and (per the entry above) how they divide by license. Answering that today costs one call per
`asset_subdir`, ten in this session's case, each returning up to 1000 full rows — name, label,
fragment, absolute path, thumb path — when the caller wants counts. The first call also pays MPFB's
one-preview-image-per-asset load for that subdir, so the cheapest possible phrasing of "what do I
have" is also among the most expensive calls the server offers.

A `summary=True` mode (or a separate `mpfb_describe_asset_library`) returning counts faceted by
`asset_subdir` × `pack` × `license`, and nothing else, would answer it in one call and read in a
dozen lines. [FR 046](done/046-license-in-the-catalogues/README.md) gave every call
`counts_by_license`, taken before the license filter and the cap, so "226 of 639 clothes are CC0"
is now one call per subdir; the faceting across subdirs and packs is what is left for this entry.

A smaller version of the same point: `mpfb_list_assets()` with no arguments returns 200 rows that
are all `Clothes`, because `clothes` sorts first and the default limit stops there. `truncated` is
true and `total_count` is honest, so the response is not wrong — but the shape of it invites the
reading "this install has 200 clothes and nothing else", which is what happened here before the
docstring was read. Defaulting a no-argument call to the summary above would be strictly more
informative than a truncated page of one type.

<a id="a-hand-cannot-be-placed-at-a-point-on-a-standard-rig"></a>

## A hand cannot be placed at a point on a standard rig

Found by the man-and-woman scene session, whose whole subject was two characters holding hands.
This is the single largest cost that session paid, and it is adjacent to
[Posing support](#posing-support) rather than covered by it: that entry is about hand *shape*, this
one is about where the hand *is*.

`mpfb_set_pose_bones` offers `move_to` ("where the head goes"), but a bone only accepts it when its
role is `ik_control`. On MPFB's standard rigs there are none: `mpfb_get_pose_controls` on
`default_no_toes` reports `helper_modes` of `{"arm_mode": "NONE", "leg_mode": "NONE",
"finger_mode": "NONE", "eye_mode": "NONE"}`, `counts_by_role` gives `ik_control: 0`, and every arm
control is `chain: "fk"`. So the only way to put a hand somewhere is to solve the chain by hand:
pick a direction for `upperarm01`, `lowerarm01` and `wrist`, write it, read `mpfb_get_pose`'s
`landmarks`, and iterate. That session did it roughly ten times per arm.

MPFB itself can do better and the bridge cannot reach it. MPFB's IK helpers are what `helper_modes`
is reporting on, but nothing turns them on from this side: `RigService` exposes only
`add_ik_constraint_to_pose_bone`, `add_ik_rotation_lock_to_pose_bone` and `set_ik_rotation_limits`,
the low-level pieces, while the helper *modes* are assembled in MPFB's UI operators. Building them
by hand from those three calls would be reimplementing an MPFB panel in the bridge, which is what
the posing commands already do for Rigify's snaps — so it is in scope, just not small.

Three ways out, cheapest first:
- **Say so.** `mpfb_set_pose_bones`' description should state that `move_to` and `move_by` need an
  `ik_control`, and that standard rigs have none until the helpers are switched on. Today the
  limitation is discoverable only by reading `counts_by_role` and inferring.
- **A tool that switches MPFB's IK helper modes on**, per limb, mirroring the panel. That is the
  real fix and it makes `move_to` work on the rig most characters get by default.
- **A solver argument**, e.g. `reach: {bone: "wrist.L", to: {...}}`, that does the FK iteration in
  the bridge and reports what it achieved. More work, but it is the thing a caller actually wants
  and it would work on every rig.

Worth noting for whoever takes this: Rigify was not a way out either. By the time the problem
appears the character is dressed, `mpfb_add_rig` refuses with `already_rigged`, and MPFB cannot swap
a rig — deleting it unrigs every garment and nothing rigs them retroactively. The rig choice is
effectively final at the moment it is made, which raises the cost of getting it wrong.

<a id="nothing-reports-that-two-meshes-interpenetrate"></a>

## Nothing reports that two meshes interpenetrate

The same session's other large cost, and the one with the clearest payoff.

The brief was to avoid the defect that sank the previous attempt at this image: two characters whose
hands passed through each other. Nothing in the forty-two tools can see that. `mpfb_set_pose_bones`
reports `achieved` per bone, `limbs_made_stretched` and `limbs_made_unreachable`;
`mpfb_place_character` reports a `footprint` box and `subrigs_broken`. All of them describe one
character. Two characters can occupy the same cubic centimetres and every tool reports success.

So the session wrote its own check: build a `BVHTree` per evaluated mesh in world space and call
`overlap()`, which returns intersecting face pairs, plus `find_nearest` for the minimum surface
distance. That turned an unanswerable aesthetic question into a number, and the number moved: the
first hand-holding pose scored **148 intersecting face pairs**; a pose-and-placement search drove it
to **0 with a 3.7 mm minimum gap**, which is what shipped. The same check then caught two problems
nobody was looking for — a boot shaft punching through a trouser leg (76 pairs, visible in the
render as dark ragged holes at the ankle) and a hand disappearing into the other character's skirt
(73 pairs) — both of which had already survived a visual pass.

What would help, in order:
- **`mpfb_check_intersections`**, read-only: given two subjects (or one, against itself), report
  intersecting face pairs and minimum surface distance per mesh pair, optionally restricted to a
  bounding box or a z-band. Thirty lines of `mathutils.bvhtree` in a bridge command, and it is the
  difference between "looks fine" and "0 pairs, 3.7 mm".
- **A clearance line in the mutating tools.** `mpfb_place_character` already computes a footprint;
  reporting whether that footprint overlaps another character's, and what the closest approach is,
  would catch the common case for free.
- A garment-vs-garment check on `mpfb_add_asset` would have caught the boots immediately. The boot
  and the trousers are both MPFB's own fitted assets; nothing warns that they do not fit together.

This is also the honest answer to "is the image deceptive". It is not: the hands are 3.7 mm apart
and touch nowhere, which is a measurement, not a judgement. No tool here could have produced it.

<a id="a-material-whose-textures-do-not-resolve-is-reported-as-applied"></a>

## A material whose textures do not resolve is reported as applied

`mpfb_set_asset_material` returned `applied: true`, named the file and listed what it destroyed,
for a material that rendered as black plastic with magenta streaks.

The asset is `ricardo2020_long_01_bronze`, shipped in `system_hair_materials03`. Its MHMAT names
three textures by paths relative to a MakeHuman data root that does not exist here —
`hair/long01/Material/long01_diffuse_straw.png` and `..._copper.png` resolve to nothing, and
`normalmapTexture hair/long01/long01_diffuse.png` resolves to the *colour* map, which MPFB duly
wired into the normal-map node. The resulting material has an empty `diffuseTexture` image node
feeding Base Color. Ten of the eleven other materials beside that asset use a bare filename and are
fine, so this is the asset author's bug, not MPFB's — but MPFB loaded it without a word and the tool
passed that silence on.

The fix is a `warnings` entry, which this tool already has a channel for: after building the
material, check each image node for a `None` image or a `filepath` that does not exist, and name
them. `mpfb_add_asset` wants the same check — it builds materials by the same path, and its
`material_created: true` carries the same false reassurance. It is cheap, it needs no new MPFB
capability, and it converts a render nobody can explain into one line in the response.

A smaller sibling, from the same session: MPFB's own layered-skin defaults put `NavelWidthMultiplier`
at `11` against a declared range of `[0.001, 0.2]`, which `mpfb_get_material_settings` duly reports
in `values_outside_range`. The reporting works; it is MPFB's default that is wrong, and worth
raising upstream rather than papering over here.

<a id="response-bulk-on-the-read-only-tools"></a>

## Response bulk on the read-only tools

Not a defect, and not urgent — recorded because one session hit all three and they share a shape:
the tools return everything they know rather than what was asked for, and the catalogues are now big
enough that it costs.

- **`mpfb_list_assets` echoes `known_packs` in every response.** On this install that is 118 pack
  names, repeated in full whether the call filtered by pack or not. It exists so a caller can
  correct a misspelling from the same response, which is right — but it could be sent only when
  `pack_recognized` is false, which is the only time it is needed.
- **A full `mpfb_get_material_settings` skin read is about 20 KB.** The docstring warns about it and
  `section` narrows it to one of three. Within `skin` there is no narrowing: ten groups come back
  with every socket, every range and every `linked` entry, when the caller usually wants
  `color.SkinColor`. A `groups=["color"]` argument would be the same shape as `section`, one level
  down.
- **`mpfb_add_asset` equips exactly one asset per call.** Dressing two characters took sixteen
  calls, each returning a full report. A batch form would cut the round trips, and — more useful —
  would give one place to enforce the ordering rule that the README states and no tool checks:
  rig before garments, Rigify generate after them, dress before placing.

<a id="what-the-all-or-nothing-batches-caught"></a>

## What the all-or-nothing batches caught (keep this)

A note in favour of an existing decision, so it does not get traded away later.

`mpfb_set_material_settings` and `mpfb_set_pose_bones` both refuse the whole call if any entry fails
to resolve, and both paid for themselves in one session:

- A write of `IrisColor` was refused with `unknown_socket` and `closest: ["IrisMinorColor",
  "IrisMajorColor", "IrisSection4Color"]`. The correct names came out of the refusal; nothing was
  half-written.
- A pose call naming `head` twice — once to turn it, once to tilt it — was refused with "bones[1]
  names 'head', already named earlier in this call". Silently applying both would have given a
  rotation that was neither, and it would have been diagnosed from a render much later.

Both are cases where a partial write would have been expensive to detect and impossible to undo
across the socket. Worth keeping, and worth extending to any future tool that writes a batch.
