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
  thirty-nine tools" now.
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

- **There is no hand-shape helper.** On Rigify, a fist comes from scaling the finger master bones
  on Y (0.45 for a closed fist), not from rotating them, and FR 042's `scale_to` reaches it. On the
  default rig it means rotating three bones per finger. A `hand` argument (`fist`, `open`,
  `relaxed`, or a 0-1 curl per finger) would hide the difference between rigs.
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

<a id="placing-a-character"></a>

## Placing a character

Scoped as [FR 045](045-placing-a-character/README.md) (Proposed): `mpfb_place_character`, which
sets a character's world `position` and its `facing` (or turns it to `face_toward` a point or an
object), and reports a `footprint` for spacing characters. It also adds a `placement` section to
`mpfb_get_character_summary`. Found by the line-up session ([FULL_SESSION.md](FULL_SESSION.md)),
which built six characters at the origin and spread them out by hand through blender mcp. Scoping
corrected one claim made here: `mpfb_add_rig` does not send the character back to the origin. The
rig takes the basemesh's location. What it may drop is the basemesh's *rotation*, which the request
checks first. Sub-rigs are reported by that request, not repaired; the repair stays
[below](#sub-rig-child-of-breaks-away-from-the-origin).

<a id="sub-rig-child-of-breaks-away-from-the-origin"></a>

## A garment's sub-rig breaks when its character is away from the origin

Found by the line-up session. This is an MPFB defect, and belongs upstream as well as here.
`ponytail01` ships a sub-rig, and its `root` bone gets a `CHILD_OF` constraint on the main rig's
`head` with `owner_space = POSE`, `target_space = WORLD` and `set_inverse_pending = True`
(`mpfb2/src/mpfb/entities/rig.py:599`). That is right only while the main rig's object transform
is identity. On a character that had been moved and turned, 2355 of the hair's 3718 vertices were
dragged two metres toward the world origin. Setting both spaces to `WORLD` and recomputing the
inverse fixed it, but only until the rig was moved again. [FR 045](045-placing-a-character/README.md) makes
the break visible but does not repair it: `mpfb_place_character` and `mpfb_add_asset` both report
`subrigs_broken_by_move`, and FR 045 builds a sub-rig test fixture this effort can reuse. What is
left here is the repair itself, in the bridge and upstream. Its first question is whether a binding
exists, `POSE`/`POSE` being the candidate, that survives a move made by hand rather than only by the
tool.

<a id="license-in-the-catalogues"></a>

## License in the catalogues

Found by the line-up session, whose brief allowed CC0 assets only. No catalogue says what an
asset's license is, yet MPFB has it on disk: every pack JSON in `data/packs/` records a `license`
per asset. The session had to read those files directly. `mpfb_list_assets`,
`mpfb_list_asset_materials` and a future pose catalogue should report `license` (and `author`)
per entry, and take a `license` filter. Two related findings:

- `pack` is not a stand-in for license. Every `*_cc0` pack checked duplicates a non-CC0 one
  (`hats01` / `hats01_cc0`), so `mpfb_list_assets(pack="_cc0")` returned 24 assets, 18 of them
  attributed to the *non*-CC0 name with `pack_ambiguous: true`. The answer then contradicted the
  filter the caller passed. When several packs claim an asset, report all of them.
- `mpfb_get_status` listed `accessories01_cc0` as installed while none of its four capes were on
  disk. Reporting a registered pack whose assets cannot be found would have saved a confused
  search.

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

## Exporting characters

Scoped as [FR 039](039-exporting-characters/README.md) (Proposed):
`mpfb_create_export_copy`, which mirrors MPFB's Export copy panel (`src/mpfb/ui/operations/exportops`),
and `mpfb_export_character`, which writes FBX, glTF or USD into a directory the human sets in
the bridge's preferences.
