# Procedural material settings: iris colour, layered skin colour and MakeSkin colour adjustments

**Status:** Proposed

Two materials MPFB builds without a file come out the same every time, and no tool changes them.
With `PROCEDURAL_EYES` every character gets the same blue irises. A `LAYERED` skin with no MHMAT
gets MPFB's default skin colour. The extensions-page line-up session
([NEXT_STEPS](../NEXT_STEPS.md#eye-and-layered-skin-colours)) set these by hand, through blender
mcp. It wrote `IrisMajorColor`/`IrisMinorColor` on the eye group node, and `SkinColor` plus the
lips, eyelid and nail colours on `MpfbSkinMasterColor`. There is a third gap of the same kind:
hair, eyebrows and garments carry a MakeSkin material whose colour can be tinted, and MPFB saves
that tint in a preset, but nothing here can read or write it.

What these three have in common is that **MPFB already serializes all of them** when it saves a
preset, and restores them when it loads one (`HumanService` in mpfb2):

- **Procedural eyes**: every colour and float input on the eye material's group node, saved as
  `eyes_material_settings`, restored by `_set_eyes()`.
- **Layered skin**: the inputs on nine group nodes named `<group>group` (`color`, `body`, `face`,
  `ears`, `lips`, `aureolae`, `genitals`, `fingernails`, `toenails`), saved as
  `skin_material_settings[<group>]`, restored through `set_character_skin(slot_overrides=...)`.
- **MakeSkin colour adjustment**: the inputs of whichever node feeds the Principled BSDF's Base
  Color, normally the `diffuseIntensity` mix, saved per asset as `color_adjustments[<uuid>]` for
  body parts other than the eyes, and for garments. Restored by
  `MaterialService.apply_color_adjustment()` when the asset is loaded. **MPFB has no UI for this
  one.** A user edits the node in Blender's shader editor, and MPFB carries the result.

So this request wraps behaviour MPFB already has and does not invent any. It does so with **one
generic read and one generic write**, keyed the way the preset is. Socket names are read from the
live node, not tabulated here. These are MPFB's node trees, so they drift with MPFB, and the eye
tree is likely to change soon: mpfb2's bug 306 work is reworking how the procedural eye material
renders on Blender 5.

Reading MPFB turned up four things this request has to deal with, not inherit:

- **Most of the layered skin's region colours do nothing when written.** `bodygroup`'s `SkinColor`,
  `facegroup`'s `EyelidColor`, the nail groups' `NailsColor` and twelve more are **linked** from
  `colorgroup` (`MpfbSkinMasterColor`). Writing a linked socket's default value succeeds and
  changes nothing. MPFB's serializer saves them anyway. The same goes for `diffuseIntensity`'s
  `Color2`, which is linked from the diffuse texture.
- **Two MPFB code paths identify these materials differently.** `MaterialService.identify_material()`
  recognizes eyes by `IrisSection4Color` and layered skin by `NavelCenterOverride`. The serializer
  recognizes eyes by `IrisMinorColor` and layered skin by the node names.
- **With an AO map, the node on Base Color is `aoMix`, not `diffuseIntensity`**, and
  `find_color_adjustment()`/`apply_color_adjustment()` read and write whichever node is there. A
  "colour adjustment" on such an asset means something different, and nothing says so.
- **The eyes are excluded from colour adjustment** by the serializer, even when they have a
  MakeSkin material. So is a MakeSkin *body*. A tint on either would not survive a preset.

## Goals

**Primary:** an agent can give a character its own eye colour and skin colour, and tint its hair
and garments, and the result survives `mpfb_save_preset` → `mpfb_create_human_from_preset`
unchanged.

**Secondary:**

- **Read MPFB's names from the live node, never from a table here.** A socket MPFB renames shows up
  as a different key in the read and a resolution error in the write, not as a silent no-op.
- **Agree with MPFB's serializer exactly.** What the read reports as a setting is what
  `HumanService.serialize_to_json_string()` would save, under the same keys, so an agent can reason
  about a preset from a read, and the bridge tests can check the two against each other.
- **Make the linked-socket trap visible**: report which sockets are linked and from where, and
  refuse to write one.
- **Make colour space explicit.** The sockets hold scene-linear RGBA. An agent thinking in sRGB
  would pick colours that come out too light, so every colour read carries an sRGB hex beside it.

## Functional requirements

Two phases, each shippable on its own: **A** is the read, **B** is the write and the preset round
trip. The request is `Done` when both have landed.

### Phase A: `mpfb_get_material_settings`

1. **Subject.** Takes `name`: any object in the character's family, with `null` meaning the active
   object. It is resolved through `shared/subject_resolution.py`. A miss is
   `blocked_by: "subject_not_found"` ([FR 038](../done/038-subject-not-found-everywhere/README.md)).
2. **Three sections, always present**: `eyes`, `skin` and `color_adjustments`. A section that does
   not apply says why, rather than being absent or empty: no eyes; eyes whose material is not
   procedural; no skin material; a skin that is not layered. Each carries the object and material it
   read and `material_identified_as` from `identify_material()`, the discriminator the existing
   tools already report (see [Decisions](#decisions-taken-while-scoping)).
3. **Per socket, what a preset holds and what it does not show.** For every socket MPFB's
   serializer would save (colour, float and float-factor inputs, as
   `NodeService.get_socket_default_values()` selects them):
   - the value exactly as the preset holds it: a float, or a scene-linear RGBA list of four;
   - its kind (colour or float);
   - an **sRGB hex** for a colour, derived from the linear value (clamped, alpha dropped), and
     reported as derived per
     [responses.md](../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact);
   - the declared range for a float, where the socket has one;
   - whether it is **linked**, and from which node and socket.

   The layout is settled during the effort. One constraint: the preset-shaped values must be
   extractable without reshaping, so an agent can copy a read's values into a write.
4. **`skin`** reports the layered skin's groups keyed as the preset keys them (`color`, `body`, …,
   not the node names `colorgroup`, …). The groups are found in the live material, not from the
   nine-name list MPFB hard-codes twice. A group MPFB's list names that is missing, or a `*group`
   node the list does not name, is reported as a fact.
5. **`color_adjustments`** has one record per mesh asset that MPFB's serializer would record: body
   parts other than the eyes, and garments. Each record has the object name, its `object_type`,
   its `uuid` (the preset's key), `material_identified_as`, and **which node was read**
   (`diffuseIntensity` or otherwise). An asset whose material is not MakeSkin, or has no node on
   Base Color, is listed with the reason and no settings.
6. **Shared materials are reported.** When a material that was read is used by objects outside
   what the section names (another character, or an export copy per
   [FR 039](../039-exporting-characters/README.md)), the section says which. A write would change
   them too.
7. **Size.** The answer for a character with procedural eyes, a layered skin, hair, eyebrows,
   eyelashes and one garment is measured during the effort. If it is over roughly 16 KB, the tool
   gains a filter argument naming one section, per
   [how tools bound a large answer](../../specifications/responses.md#how-tools-bound-a-large-answer).
   The filter is not added speculatively.
8. **`mpfb_get_character_summary`** gains the sRGB hex of the irises (`IrisMajorColor`,
   `IrisMinorColor`) and of the layered skin's `SkinColor`, under the names the detailed tool uses
   and read by the same shared module, per
   [a summary is never a second opinion](../../specifications/responses.md#a-summary-is-never-a-second-opinion).
   Nothing else from this tool goes into the summary. Proposed while writing this request, not
   asked; drop it if it threatens the summary's 8 KB cap.

### Phase B: `mpfb_set_material_settings`

9. **Subject** as in requirement 1.
10. **Three batched arguments, mirroring the preset's three keys**, all optional:
    - `eyes`: a list of `{socket, value | color}`;
    - `skin`: a list of `{group, socket, value | color}`, where `group` is the preset's key
      (`color`, `body`, …);
    - `color_adjustments`: a list of `{object_name, socket, value | color}`, where `object_name`
      is a mesh asset in the subject's family.

    **`value` for a float socket, `color` for a colour socket, exactly one per entry.** One key
    carrying either a number or a list would break the rule that no name carries two JSON types.
    A `color` is four finite numbers, scene-linear RGBA, as the read reports it. Three numbers are
    refused, with the refusal saying that alpha is required.
11. **Resolve every entry before writing any**, per
    [a batched mutating tool resolves before it writes](../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes).
    An entry fails resolution when:
    - its section does not apply (eyes not procedural, skin not layered, asset not MakeSkin or not
      in the family);
    - its group or socket does not exist on the live node;
    - its socket is **linked**. The error names what drives the socket. For the layered skin that
      is almost always "set `color`'s `<X>Color` instead";
    - its key does not match the socket's kind;
    - a float is outside the socket's declared range.

    Any failure writes nothing and returns `resolution_errors` per entry.
12. **The write is MPFB's**: `NodeService.set_socket_default_values()` for eyes and skin groups, and
    `MaterialService.apply_color_adjustment()` for assets. These are the functions the deserializer
    uses, so what the tool writes and what a preset restores cannot diverge.
13. **The answer**: `performed`, and `changes` in request order, each with `previous_value` /
    `new_value` (with the sRGB hex beside each colour). Also `change_count`, and the shared-material
    fact from requirement 6 for every material written.
14. **A call naming nothing answers immediately**, saying nothing was named, per
    [do only what was asked](../../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after).
15. **Nothing is borrowed, so nothing is restored.** Writing a socket's default value needs no
    active object, selection or mode. The command must not change any of them, and the bridge
    tests check that.
16. **The round trip holds**: after a write, `mpfb_save_preset` then `mpfb_create_human_from_preset`
    (with clothes loaded) gives a character whose `mpfb_get_material_settings` values equal the
    original's. If MPFB breaks this, the effort records where and files it; the tool does not
    patch it (see the eyes' `blend_method` and bug 306 in [References](#references)).
17. **What discards these settings is named in the description**: `mpfb_set_skin` rebuilds the skin
    material, `mpfb_set_asset_material` rebuilds an asset's, and re-adding eyes rebuilds theirs.
    Each starts again from MPFB's defaults.

## Non-functional requirements

- **Drift shows up as an answer.** No socket name, group name or node name specific to these
  materials is hard-coded on either side of the socket, beyond what MPFB's own code uses to find
  the node. The unit tests pin no socket vocabulary.
- **Faithfulness to the serializer over tidiness.** Where the serializer's choices look arbitrary
  (eyes excluded from colour adjustment, `aoMix` read when present), the tool follows them and
  names them. A tidier choice would make the tool disagree with the preset.
- **Description budget.** The socket vocabulary is in the read's answer, never in a description.
  The write's description names the three sections and states the colour-space rule, the
  linked-socket rule and requirement 17. It also has one sentence on what makes a flat skin colour
  visible over a texture (see the pitfalls below). `tests/test_description_budget.py`'s ceiling is
  raised only after trimming.
- **Cheap.** Neither tool loads a file, refits or recalculates anything. Both should be well under
  100 ms on the bridge.

## Architecture

- **Four things per tool**: `tools/get_material_settings.py`, `tools/set_material_settings.py`,
  two `register()` calls, `bridge/mpfb_bridge/commands/get_material_settings.py` and
  `.../set_material_settings.py`, and two entries in `commands/table.py`.
- **One shared module**, `shared/material_settings.py`, because both commands, and the summary if
  requirement 8 stands, must agree on how each section's node is found, which sockets count, what
  "linked" means and how linear becomes sRGB hex. It takes `services` as its first parameter, like
  its siblings. This is the one shared addition. If anything else shared has to change, stop and
  say why.
- **Finding the node, by section**, reusing MPFB's own lookups:
  - eyes: the eyes object via `ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh,
    "Eyes")`, slot 0, first `ShaderNodeGroup` (as the serializer does);
  - skin: the basemesh's slot 0, every `ShaderNodeGroup` named `*group`;
  - assets: `MaterialService`'s own route to the node linked to Base Color, the one
    `find_color_adjustment()` takes, so the node read is the node MPFB will serialize.
- **Ranges.** A group node instance's input does not carry its own min/max. The range is on the
  node group's interface item. A built-in node's factor socket carries its range in its subtype.
  Read both, and treat a socket with neither as unbounded.
- **Linked** means the input has a link. Report the link's `from_node.name` and
  `from_socket.name`.
- **Pitfalls for the live check to settle:**
  - **What makes a layered `SkinColor` visible.** `create_v2_skin_material()` sets
    `DiffuseTextureStrength` to 0.0 and raises it only when the MHMAT has a diffuse texture. The
    `*Override` inputs presumably blend a flat colour over the texture per region. Establish this
    against a real install and put one sentence in the write's description.
  - **Out-of-range writes.** Whether Blender clamps a group input assigned beyond its interface
    range, and whether a colour socket accepts components above 1.0. The first decides whether
    requirement 11's range check is protecting against a clamp or against nothing. The second
    decides the colour validation.
  - **`aoMix`.** Find an asset in the installed library whose MHMAT has an AO map. Record what that
    node's inputs are and what writing them does, and state it in the tool's docstring.
  - **The colour adjustment is a mix, not a multiply.** `diffuseIntensity` blends `Color1` (the
    MHMAT's diffuse colour) with the texture by `Fac`. A low `Fac` gives a flat colour with no
    texture detail. The preset does not carry the node's blend type, so changing it is out of scope.
    Say so in the description rather than offering a tint that does not survive.
  - **The preset round trip for colour adjustments** depends on `add_mhclo_asset()` applying them
    only in its MakeSkin branch, after any alternative material. Check both orderings.

## Affected specifications

- [mpfb-integration.md](../../specifications/mpfb-integration.md): a new principle, **names inside
  MPFB's node trees are read live, never tabulated**, with this request as its first case. Two
  additions to
  [where MPFB's own code paths disagree](../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it):
  `identify_material()` against the serializer's discriminators, and the serializer's exclusions
  (eyes, a MakeSkin body).
- [tool-interface.md — the glossary](../../specifications/tool-interface.md#the-glossary): `socket`
  and `group`; `value` broadened from "what a shape key holds" to include a float socket; `color`
  for a colour socket; the sRGB hex key's spelling. [Kept on
  purpose](../../specifications/tool-interface.md#kept-on-purpose) gains **socket names are MPFB's
  data and pass through verbatim**, including `AurolaeOverride` (MPFB's spelling), the way a shape
  key name does. The glossary does not rename data.
- [responses.md](../../specifications/responses.md): the sRGB hex as a derived fact; the linked flag
  and the shared-material fact as instances of
  [a tool may report a fact MPFB's own UI does not show](../../specifications/responses.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show).
- [mutating-tools.md](../../specifications/mutating-tools.md): the third batched tool, and a
  refusal that names a different, writable target (linked socket → `color`) as the fix.
- [vision.md — Target tool catalog](../../specifications/vision.md#target-tool-catalog): the counts.
- [testing.md](../../specifications/testing.md): only if the serializer-agreement check below is a
  pattern it does not already describe. It is close to "never a second opinion", but against MPFB
  rather than against another command.

## Tests

- **Wrapper tests** (`tests/test_get_material_settings.py`, `tests/test_set_material_settings.py`):
  the subject's shape; each list's entry shape; unknown keys refused (a misspelled `sokcet` is
  otherwise silent); exactly one of `value`/`color`; a `color` of four finite non-bool numbers; a
  repeated `(section, group or object_name, socket)` refused locally, as `mpfb_apply_expressions`
  refuses a repeated fragment; and that **no socket or group vocabulary** is checked here.
  `tests/test_verification_smoke.py` and `tests/test_vocabulary.py` pick both tools up unedited.
- **Bridge tests**. The fixture is one character with procedural eyes, a `LAYERED` skin, and a
  loadable MakeSkin hair and garment from `_fixtures.py`:
  - `ccc_reading/get_material_settings_test.py`: every section, every "does not apply" reason
    (no eyes, MakeSkin eyes, non-layered skin, a GameEngine garment); linked flags on the layered
    region colours and on `diffuseIntensity`'s `Color2`; and **agreement with MPFB's serializer**:
    `serialize_to_json_string()`'s `eyes_material_settings`, `skin_material_settings` and
    `color_adjustments` equal the read's values, key for key.
  - `ddd_mutating/set_material_settings_test.py`: each section written and read back; one bad entry
    in a batch writes nothing; linked, kind-mismatch and out-of-range refusals; a shared material
    reported; selection, active object and mode unchanged.
  - `eee_composite/`: requirement 16's round trip, through the preset commands.
- **The live check**, in this subdir as a script: the round trip on a real install; the pitfalls
  above (override semantics, clamping, `aoMix`, colour ceiling); the answer size for requirement 7;
  and confirmation of any MPFB defect candidate before it goes into
  `mpfb2/features/MCP_DISCOVERED_BUGS.md`. It cannot judge whether a colour *looks* right. A render
  is optional evidence, not a pass criterion.
- **Two smoke items** in [verification/](../../verification/), default arguments. The write with
  default arguments is the no-op answer of requirement 14.

## Decisions taken while scoping

- **Three mechanisms: eyes, layered skin and MakeSkin colour adjustment.** The enhanced skin's
  per-slot settings (`colorMixIn`, roughness, pores on `ENHANCED`/`ENHANCED_SSS`) are left out,
  and stay in [NEXT_STEPS](../NEXT_STEPS.md#eye-and-layered-skin-colours). The "colour mix-in"
  NEXT_STEPS attributed to MakeSkin is the enhanced skin's `colorMixIn`. MakeSkin has none, and its
  analogue is the colour adjustment, which is in.
- **One generic read and one generic write**, keyed like the preset. Rejected:
  per-concept tools (`mpfb_set_eye_color`, `mpfb_set_skin_color`), which would hard-code MPFB's
  socket names into the argument list, and a generic pair plus a thin eye tool. A convenience tool
  can be added later if agents are seen struggling with the generic one.
- **Scene-linear colours in, linear plus sRGB hex out.** Rejected: linear only, which leaves an
  agent's sRGB intuition silently wrong; and accepting hex on writes, which needs a second key per
  entry and a conversion the read could not round-trip exactly.
- **MPFB's named settings files are left out**: `eye_settings.<name>.json` and
  `enhanced_settings.<name>.json`, with their save/apply panels. They stay in NEXT_STEPS. No new
  file is written outside the `.blend`.
- *Proposed while writing this request, not asked:*
  - `value`/`color` as two keys;
  - linked sockets refused rather than written;
  - `identify_material()` as the discriminator reported, with the serializer's own test used
    to decide what counts as a setting;
  - the serializer's exclusions followed rather than extended;
  - requirement 8's three summary fields.

## References

- The serializer and deserializer: `mpfb2/src/mpfb/services/humanservice.py`:
  `_populate_human_info_with_skin_info`, `_populate_human_info_with_eye_material_info`,
  `_populate_human_info_with_bodyparts_info`, `_populate_human_info_with_clothes_info`,
  `_set_skin`, `_set_eyes`, `set_character_skin(slot_overrides=...)`,
  `add_mhclo_asset(color_adjustments=...)`.
- `mpfb2/src/mpfb/services/materialservice.py` (`identify_material`, `find_color_adjustment`,
  `apply_color_adjustment`, `create_v2_skin_material`) and `nodeservice.py`
  (`get_socket_default_values`, `set_socket_default_values`).
- The node trees: `mpfb2/src/mpfb/data/node_trees/procedural_eyes.json`, `makeskin.json`;
  `entities/nodemodel/v2/materials/nodewrapperskin.py` (the layered skin's links) and
  `entities/nodemodel/v2/composites/nodewrappermpfb*.py` (its groups' inputs).
  `data/settings/eye_settings.default.json` is a readable list of the eye inputs and their defaults.
- MPFB's panels for the two left-out file types: `mpfb2/src/mpfb/ui/presets/eyesettings/`,
  `.../enhancedsettings/`.
- mpfb2 bug 306 (`mpfb2/features/bug_306_fix_eyes*.md`): the procedural eye material's rendering
  on Blender 5, and the reason to expect its node tree to change.
- Precedents here: [FR 011](../done/011-skin-and-materials/README.md) (`mpfb_set_skin`),
  [FR 025](../done/025-character-presets/README.md) (the preset tools the round trip goes through),
  `mpfb_set_targets` and `mpfb_set_face_units` (batched writes resolved first),
  [FR 034](../done/034-character-summary/README.md) (the summary rule).
