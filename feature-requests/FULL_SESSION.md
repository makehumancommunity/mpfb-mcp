# Session log: image 1, "Character line-up — the hero"

**Date:** 2026-09-26
**Task:** render image 1 of the image brief for MPFB's extensions page (kept outside this
repository), using mpfb-mcp first and blender mcp only as a fallback. Constraints: multilayered (`LAYERED`)
skin, procedural eyes, CC0 assets only (the system assets pack or a `*_cc0` pack), 1920×1080.

**Result:** `01-character-lineup.png` (1920×1080, Cycles, 1024 samples, denoised, 34 s on one
GPU), with a copy of the scene beside it as `01-character-lineup.blend` (67 MB). The studio file
the session started from, `LightRoom5.blend`, was **not** saved.

## Summary of where the work went

| | mpfb-mcp | blender mcp |
|---|---|---|
| Calls | ~100 (80 in the build scripts, ~20 exploring) | 22 `execute_blender_code`, 1 screenshot |
| Errors | 0 | 3, all mine (a bad slice, a non-dict `result`, GPU out of memory) |
| What it did | every character: creation, phenotype, targets, rig, all 41 mesh assets, 6 alternative materials, 6 skins, 4 removals, 2 refits | placement, posing, eye colours, one skin tint, backdrop colour, lights, render, a broken sub-rig repaired, saving |

Character *content* came entirely from mpfb-mcp. Everything about *staging* came from blender
mcp, and three of those jobs are things MPFB's own UI can do, so they count as gaps in mpfb-mcp
(see [What was missing](#what-was-missing-in-mpfb-mcp)).

## 0. Reaching mpfb-mcp

**The mpfb-mcp tools were not attached to this Claude session.** The Blender side was fine: the
MPFB Bridge was listening on 127.0.0.1:9877 and blender mcp's add-on on 9876, both inside the one
Blender. But no `mcp__mpfb*` tool was among the session's tools, only `mcp__blender__*`.

Workaround: a 30-line stdio MCP client (`mcp.ClientSession` over `stdio_client`) that starts
`.venv/bin/mpfb-mcp` and calls tools by name. Every mpfb-mcp call in this session went through the
real server, its argument validation and its descriptions, just not through the host's tool list.
A second script (`build.py`) took a JSON cast description and made each character's calls in
order, logging every request and response to a JSONL file.

## 1. Discovery

- `mpfb_get_status`: MPFB 2.0.17 from source, Blender 5.1.0, 118 asset packs, system assets
  installed, Rigify available. `mpfb_list_objects`: empty scene as far as MPFB was concerned.
- blender mcp: the open file was a ready-made studio, `LightRoom5.blend`: a curved backdrop
  (`Background_change_color_if_necessary`, blue-grey), `Camera_do_not_change` (120 mm, at
  z = 3.05, 19 m back, looking down slightly), one small area light, a weak sun, an irradiance
  volume, a hidden sizing box (`Place_toon_inside_this_box`, 1.97 m) and a pouf (`Puff`) at the
  origin. It was already set to 1920×1080, Cycles on GPU. **I treated the camera's name as an
  instruction and did not touch the camera.** That decides the framing (see
  [Deviations](#deviations-from-the-brief)).

### Finding CC0 assets

**mpfb-mcp cannot answer "which of these are CC0?"** `mpfb_list_assets` returns `pack` but no
license, and `pack` is not a reliable proxy either:

- Every `*_cc0` pack I checked duplicates a non-CC0 pack (`hats01` / `hats01_cc0`,
  `equipment01` / `equipment01_cc0`, …), so `mpfb_list_assets(pack="_cc0")` returned 24 assets,
  18 of them attributed to the **non**-CC0 pack name with `pack_ambiguous: true`. The filter
  matched; the attribution in the answer then contradicted the filter.
- The license is recorded per asset in `data/packs/<pack>.json` (`"license": "CC0"`), and
  non-CC0-named packs contain CC0 assets too (for example all of `poses03`'s standing poses).
- `accessories01_cc0` is registered as installed and lists four capes, but no `culturalibre_*cape*`
  directory exists under `data/clothes`, and `mpfb_list_assets` does not list them. A pack being
  in `get_status`'s list does not mean its files are on disk, and nothing says so.

So I read the pack JSON files directly (a Python one-liner on the Blender host) and kept to the
brief's stricter reading: assets from `makehuman_system_assets`, the `system_*_materials*` packs
and the `*_cc0` packs, each of them verified to be `CC0` in its pack JSON. Alternative materials
got the same check: `mpfb_list_asset_materials` also has no license field, and the hair folders
mix CC0 materials with others (`system_eye_materials03` is CC-BY, for instance).

## 2. The cast

Built in this order and standing left to right. All phenotypes are macros plus, for two of them,
bundled `target.json` modifiers (shipped with MPFB, so not assets in the licensing sense). Every
character got a `default` rig, `high-poly` eyes with `PROCEDURAL_EYES`, and a `LAYERED` skin.

| | Character | Macros (non-default) | Targets | Hair (material) | Clothes | Skin mhmat | Iris |
|---|---|---|---|---|---|---|---|
| 1 | Older man | gender 1, age 0.92, muscle 0.4, weight 0.55, height 0.45, caucasian 0.9 | — | short02 (bogdan666_short_02_gray) | male_elegantsuit01 (toigo_male_elegant_suit_brown), shoes04, fedora01 | old_caucasian_male | grey-blue |
| 2 | Heavy-set man | gender 1, age 0.62, muscle 0.3, weight 1.0, height 0.42, african 0.9 | stomach-pregnant +0.7, torso-scale-horiz +0.4, hip-scale-horiz +0.4, neck-double +0.6, head-fat +0.6 | short01 | male_worksuit01, shoes02 | middleage_african_male | dark brown |
| 3 | Young woman | gender 0, age 0.42, weight 0.45, proportions 0.6, asian 0.9 | — | long01 (toigo_long_01_black) | female_elegantsuit01, shoes03 | young_asian_female | dark brown |
| 4 | Teenage boy | gender 1, age 0.3, weight 0.4, height 0.45, caucasian 0.9 | — | short04 (toigo_short_04_ginger) | male_casualsuit06, shoes05 | young_caucasian_male | green |
| 5 | Athletic woman | gender 0, age 0.5, muscle 0.85, weight 0.35, height 0.6, proportions 0.7, african 0.9 | — | afro01 | female_sportsuit01, shoes06 | young_african_female | brown |
| 6 | Stylised figure | gender 0.15, age 0.4, weight 0.4, height 0.2 | head-scale vert/horiz +1.0, depth +0.8; eye-scale +1.0 both sides; ear-shape-pointed +1.0 and ear-scale-vert +1.0 both sides; neck-scale-horiz −0.6 | ponytail01 (dariush086_ponytail01_pink) | male_casualsuit05, shoes05 | none: procedural base, tinted teal | gold / magenta |

Each character also has one of the system eyebrows and eyelashes. Teeth and tongue were left
off, since mouths are closed at this size.

### Build timings

The whole first build was 72 mpfb-mcp calls, 0 errors, **about 10 s of tool time for six dressed,
rigged and skinned characters.** `mpfb_create_human` 0.2–1.0 s, `mpfb_add_rig` ~0.15 s, a garment
0.15–0.55 s, a skin under 0.1 s. The responses were consistently useful: every `add_asset` named
the object it created, whether it was rigged and to what, and the missing-`.mhw` warning.

## 3. Iterations

Test renders at 960×540 and 48 samples took about 3 s each.

1. **First test render.** Six characters, but: the backdrop was blue-grey where the brief says
   mid-grey; lighting was one small hard key with strong shadows on the backdrop; three
   characters wore the same blue MakeHuman-logo top (`male_casualsuit04`, `female_casualsuit02`,
   and the sportsuit's crop top); the heavy-set man did not read as heavy under the overalls; and
   the stylised figure's `bob02` hid its face and ears.
2. **Fixes through mpfb-mcp** (`fix1.py`): `mpfb_set_macro_details` and `mpfb_set_targets` on the
   heavy-set man, then `mpfb_refit_human`; the athlete's height down to 0.6 (`refit: true`);
   `mpfb_remove_asset` ×4 and `mpfb_add_asset` ×3 to swap the teen's shirt, the stylised figure's
   outfit and hair, and drop its belt. All clean. The removal reports (mask modifiers removed,
   `Delete.*` vertex group left behind) were exactly what I needed to trust that no hole was left.
   I went looking for other colours of the female garments first, but
   `mpfb_list_asset_materials` found none that are CC0: `female_casualsuit02`, `male_casualsuit04`,
   `male_worksuit01` and `female_elegantsuit01` ship only their own material, and the sportsuit's
   only alternative is `smiley`.
3. **Staging through blender mcp**: backdrop base colour to neutral 0.28 grey; the existing `Area`
   light reused as a large soft key (4 × 2.5 m, 1500 W, front left); a new `Fill` (5 × 3 m, 400 W,
   front right) and `Rim` (6 × 1.2 m, 500 W, above and behind); `Puff` hidden.
4. **Second test render: the stylised figure's ponytail was stretched 2 m across the frame**
   toward the world origin. That is an MPFB defect, see [below](#mpfb-defect-sub-rig-child-of-breaks-once-a-character-is-not-at-the-origin).
5. **Framing.** Moving the row 1.8 m toward the camera cut the feet off: the fixed camera looks
   down, so the ground line drops out of frame. I settled on 0.6 m closer, with the gaps
   solved so all six are evenly spaced edge to edge (6 % of frame width each, 4.5 % margins).
6. **Final render** at 1920×1080, 1024 samples, denoised.

## 4. What had to be done in blender mcp, and why

### Placement
`mpfb_create_human` has no `location`, and `mpfb_add_rig` moves the basemesh back to the origin
anyway (*not so: the rig takes the basemesh's place, see [FR 045](done/045-placing-a-character/README.md)*), so all six characters were built on top of each other at the origin. **No mpfb-mcp tool
moves a character**, so each rig's location and a small ±4–8° turn were set by hand. The spacing
was computed with `world_to_camera_view` over each character's evaluated vertices, since only
Blender can say where things land in the frame.

### Posing
The brief asks for a relaxed stance, not MPFB's A-pose. **mpfb-mcp has no posing tool**: no
`mpfb_list_poses`/`mpfb_apply_pose`, even though `mpfb_list_assets` already lists `poses` as a
subdir. The only CC0 standing poses are in `poses03`, which is not a `*_cc0` pack, so under the
strict reading they were off limits anyway. Instead I rotated bones directly: `upperarm01.L/.R`
lowered 30–41° about the armature's front axis, `lowerarm01` bent slightly, and the head tilted
and turned a few degrees, all different per character. No pose asset is involved.

### Material parameters
- **Procedural eyes are all the same blue by default**, and no tool changes that. I set
  `IrisMajorColor`/`IrisMinorColor` on each `EnhancedEye` group node.
- **A `LAYERED` skin with no MHMAT gets MPFB's default skin colour**, and no tool changes that
  either. For the stylised figure I set `SkinColor` (teal) plus the lips, eyelid and fingernail
  colours with their `*Override` inputs on the `MpfbSkinMasterColor` group. The other five use a
  system skin MHMAT with `LAYERED`, which feeds the MHMAT's diffuse texture into the same group,
  and they needed nothing.

### MPFB defect: sub-rig CHILD_OF breaks once a character is not at the origin

*Corrected by [FR 045](done/045-placing-a-character/README.md#decisions-taken-during-the-effort),
which measured it:* a move breaks no sub-rig. Equipping one on a character that already stands away
from the origin binds it wrong, wherever the character goes after, and `mpfb_refit_human` re-binds
it. This session equipped the ponytail on a character it had already moved, which is that case.

`ponytail01` ships a sub-rig (`ponytail01.rig.json`), and `mpfb_add_asset` imported it as
`Human.ponytail01.rig`, object-parented to the main rig. Its `root` bone has a `CHILD_OF`
constraint targeting the main rig's `head`, with **`owner_space = POSE` and
`target_space = WORLD`**, and MPFB sets `set_inverse_pending = True`
([`mpfb2/src/mpfb/entities/rig.py:577`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/entities/rig.py#L577)). 2355 of the hair's 3718 vertices are in the
`mhmask-subrig` group, fully weighted to that `root`.

Mixing spaces like that is right only while the main rig's object transform is identity. This
character's rig had already been moved and turned before the hair was added, and was moved again
afterwards, so the sub-rig root was offset by the rig's own world transform and the tail was
dragged toward the world origin. Two findings from repairing it:

- Setting both spaces to `WORLD` with `inverse = (rig.matrix_world @ head.matrix_local)⁻¹` fixes
  it, **but only until the rig is moved again**. My first attempt was made before the final
  placement, and the ponytail then stuck out sideways toward the camera.
- Setting both spaces to `POSE` did not behave the way I expected either (the root ended up with
  no object transform at all), so I did not pursue it.

What shipped: `WORLD`/`WORLD` with the inverse computed **after** the final placement. This will
bite anyone who builds several characters side by side in MPFB and uses a hair or garment with a
sub-rig, which makes it worth an MPFB issue. Until MPFB is fixed, mpfb-mcp could at least warn
when `mpfb_add_asset` creates a sub-rig on a character whose rig is not at the origin.

## What was missing in mpfb-mcp

In order of how much each would have saved in this session:

1. **Placing a character.** A `location` (and `rotation`) on `mpfb_create_human`, or a
   `mpfb_move_character` that moves the rig or basemesh *and* keeps sub-rig constraints valid.
   Any multi-character image needs it, and done by hand it runs into the sub-rig defect above.
2. **Poses.** `mpfb_list_poses` and `mpfb_apply_pose`, over MPFB's BVH/JSON pose support, and
   ideally a way to reset to rest. Every image in the extensions-page brief except the UI screenshots wants a
   non-A pose, and image 6 is entirely about a pose.
3. **License in catalogues.** `license` (and `author`) per entry in `mpfb_list_assets` and
   `mpfb_list_asset_materials`, read from the pack JSON MPFB already has on disk, plus a
   `license` filter. This session's CC0-only constraint cost a detour to the filesystem that the
   MCP layer should have answered. Relatedly: when `pack` matches several packs, report all of
   them, not a coin toss that contradicts the filter the caller passed.
4. **Procedural eye and layered skin parameters.** A `mpfb_set_eye_color` (iris colours,
   optionally pupil size) and a way to set the `LAYERED` skin's master colours. MPFB's own UI
   exposes both (the eye and skin material panels). Without them, "procedural eyes" means six
   identical blue irises.
5. **Naming.** `mpfb_create_human` takes no `name`, so the cast is `Human` … `Human.005` and
   `Human.high-poly.003`. It is harmless, but a log or a later session reading the scene cannot
   tell who is who.
6. **Installed-but-empty packs.** `mpfb_get_status` lists `accessories01_cc0` as installed while
   none of its files are on disk. Reporting packs whose assets are not found would have saved a
   confused search.
7. Minor: `mpfb_set_targets` on a rigged character warns that the rig is now stale (it did, in
   `assets_possibly_stale`), but I still built the stylised figure's rig *before* its targets and
   had to refit. Setting targets in `mpfb_create_human`, or a `modifiers` argument there, would
   make the right order the easy one.

What worked well and needs no change: `mpfb_add_asset`'s reporting (object name, rig, delete
group, warnings), `mpfb_remove_asset`'s cleanup report, `mpfb_set_skin`'s explicit statement that
`material_instances` was forced off for `LAYERED`, `mpfb_list_targets`' categories, and the speed:
the entire cast in about ten seconds of tool time.

## Deviations from the brief

- **Camera height.** The brief asks for chest height; the studio's `Camera_do_not_change` sits
  higher and looks slightly down. I kept it, so the characters fill about the lower two thirds of
  the frame, with backdrop above them. Getting closer to the brief means lowering and re-aiming
  that camera, which is the file owner's decision.
- **The stylised figure** reads as stylised (teal skin, big head and eyes, pink hair, gold irises)
  but its pointed ears are small at this scale, and it wears an ordinary jacket and jeans. The
  CC0 pool has no fantasy garments beyond the `culturalibre` belts, helmets and weapons.
- **Stance variation** is modest: arm angles, head tilt and turn, and the body turn. There are no
  weight shifts or leg changes, because without a pose tool each extra bone is hand work.
- **Different outfits:** yes, all six. Two share `shoes05`, one pair visible, one mostly under
  jeans.

## Files

The image and the scene as rendered (studio, lights, six characters) were saved beside the brief,
outside this repository. Scene changes made through blender mcp, all saved in the copy and none in `LightRoom5.blend`:
backdrop colour, `Area` light repurposed, `Fill` and `Rim` added, `Puff` hidden, Cycles samples
and denoising. The camera is untouched.
