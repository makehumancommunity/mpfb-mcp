# MakeSkin materials: building, reading and storing them

**Status:** Proposed

The second of four requests scoping
[The MakeClothes and MakeSkin workflows](../NEXT_STEPS.md#the-makeclothes-and-makeskin-workflows).
It depends on nothing else here, though [FR 050](../050-writing-mesh-assets/README.md) shares its way
of writing textures.

**An agent cannot build a MakeSkin material from textures it generated.** In the gi session this meant
writing an MHMAT by hand, calling `populate_from_mhmat()` and `apply_node_tree()`, and setting metadata
through two config classes. Working out how took reading `mpfb.import_makeskin_material` first, because
that operator needs a file dialog and a "replace" scene property. Nothing reads the result back either:
`mpfb_get_material_settings` reports only `diffuseIntensity` for a garment, so which maps are wired, at
what strength and in which colour space is unknown without a script.

**The store half is what makes this useful beyond one garment.** MakeSkin's panel stores a material as
an alternate beside an asset or as a body skin. The gi's own README says another belt colour "would be
an alternative material", and no tool can make one.

## Goals

**Primary:** an agent can give a mesh a MakeSkin material from image files or Blender images, read back
what it got, and store it where `mpfb_list_asset_materials` or `mpfb_set_skin` will find it.

**Secondary:**

- **What the reader reports, the writer accepts**, as in
  [FR 047](../done/047-rigify-hand-shapes/README.md).
- **A source texture is never changed.** MPFB's save path re-encodes it in place; this one does not.

## Non-goals

- **The template material with blank images to paint on** (`mpfb.create_makeskin_material`). An agent
  does not paint in Blender's image editor. Offered and declined.
- **Saving a free-standing MHMAT to an arbitrary file** (`Save as MHMAT`). A garment's MHMAT is written
  by [FR 050](../050-writing-mesh-assets/README.md). Alternates and skins are written here.
- **Generating textures, unwrapping, packing.** General Blender and image work, and it went fine through
  generic code. FR 050 documents the recipe.
- **The enhanced, layered and procedural materials.** `mpfb_set_skin` and `mpfb_set_material_settings`
  own those.

## Functional requirements

### `mpfb_set_makeskin_material`

1. **`name`** is the mesh, `null` meaning the active object. Any mesh is accepted, as MakeSkin's panel
   accepts any mesh. **`material_name`** names the material.
2. **`textures`** maps a slot to its source: `{"diffuse": {"path": "/abs/file.png"}}` or
   `{"diffuse": {"image": "name in bpy.data"}}`, exactly one of the two. Slot names are MPFB's own
   (`diffuse`, `normalmap`, `roughnessmap` and so on), checked bridge-side and reported as `known_slots`.
3. **A `path` is absolute, read-only, and has an image extension.** Shape is checked on this side of
   the socket. Whether the file exists and loads is settled bridge-side before anything changes.
4. **An `image` names one already in the file**, so that a texture baked or edited in Blender can be
   used before it has a file. It has none until it is stored, and the answer says so.
5. **`values`** holds the numbers: `diffuseColor`, `roughness`, `metallic`, `ior`, `diffuseIntensity`,
   `normalmapIntensity`, `bumpmapIntensity` and the displacement intensity. Anything outside what the
   node tree reads is refused by name.
6. **`metadata`** holds what an MHMAT carries as text (`description`, `license`, `author`, `tag`) and
   what it carries as settings (`backfaceCull` and so on). These are set on the object's MakeSkin
   properties, since that is where `populate_from_object()` reads them when the material is stored. The
   effort's round trip (below) decides which keys actually survive, and only those are accepted.
7. **All or nothing.** Every texture, slot and value resolves before any material is touched, per
   [the batch rule](../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes).
8. **`specularmap` with `roughnessmap` is refused**, as the panel refuses it.
9. **An existing material is refused unless `replace: true`**, matching the panel's default of `false`,
   and a replacing call lists `materials_destroyed`. Where the material is shared with another object,
   `material_shared_with` says so.
10. **Colour space follows the slot:** non-colour for everything but `diffuse` and emission colour,
    as `_NONCOLOR` says. Changing it on a named image that something else uses is reported.
11. **A regenerated texture shows its new pixels.** A path Blender has already loaded is reloaded, and
    the answer says `reloaded`. Without this a second call quietly keeps the old pixels, which is why
    `apply_material.py` removes its images first.
12. **A texture that fails to resolve is a refusal**, unlike the silent case in
    [A material whose textures do not resolve](../NEXT_STEPS.md#a-material-whose-textures-do-not-resolve-is-reported-as-applied).

### `mpfb_get_makeskin_material`

13. **Per slot:** whether it is wired, the image, the resolved path and whether it exists, size, colour
    space, packed or unsaved, and strength where the slot has one.
14. **`values`**, with `in_effect` on each: `roughness 0.7` beside a roughness map is not in effect, and
    nothing today says so. This answers the third item under *Worth raising in MPFB* for a reader.
15. **The answer's `textures` and `values` can be sent to the setter unchanged.** Each texture entry
    carries `path` when it has a file and `image` when it does not, plus read-only facts the setter ignores.
16. **A material that is not MakeSkin is `not_makeskin`**, naming what MPFB identifies it as. An
    untextured MakeSkin material must be accepted, although `identify_material()` calls it `gameengine`
    ([why](../../specifications/mpfb-integration.md)). So recognition uses the template's named nodes.

### `mpfb_store_makeskin_material`

17. **`store_as`** is `"alternate"` or `"skin"`, required. **`material_name`** is a name, never a path.
18. **An alternate lands where MPFB's panel puts it**, `<asset dir>/<name>/<name>.mhmat`, and needs an
    `asset_source` that resolves. A body or body proxy is refused for `alternate`, and everything else
    for `skin`, as the panels' polls do. `asset_not_in_library` refuses an asset
    [FR 050](../050-writing-mesh-assets/README.md) wrote to the export directory, since there would be
    nowhere MPFB would look.
19. **A skin lands in `<user data>/skins/<name>/<name>.mhmat`.**
20. **The properties in the [obligation](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)
    hold:** `overwrite: false`, `path` in every answer, a refusal carrying the existing file's size and
    time, `name_shadowed` when a higher-priority root would hide the file, and no directory created
    before the last refusal has been passed. MPFB's operators create the directory first and overwrite
    without asking.
21. **The name survives MPFB's normalisation unchanged:** lower case letters, digits and `_`, since the
    panel lowercases and turns spaces into underscores. Both sides of the socket check it, in
    `artifact_names.py`, with a noun of its own.
22. **Textures reach the destination without touching their sources** (see Architecture), named as MPFB
    names them, `<name>_<slot>.<ext>`. `textures_written` gives each one's source, whether it was
    `copied` or `saved_from_blender`, and its size.
23. **`license` and `author` default from the object**, and `license_resolved_by` and
    `author_resolved_by` say whether that was `"argument"`, `"object"` or `"mpfb_default"`.
24. **The answer says how to use it:** `apply_with` is the `mpfb_set_asset_material` or `mpfb_set_skin`
    call, and that entry's cache is invalidated so that `mpfb_list_asset_materials` lists it at once.
25. **`dry_run`** does everything but write, so that a smoke run leaves nothing behind.

## Non-functional requirements

- **Fidelity:** a stored material applied through MPFB's own panel looks the same as the one set here.
  A round trip through `mpfb_set_makeskin_material`, store, and `mpfb_set_asset_material` must read back
  equal, and a skin through `mpfb_set_skin`.
- **Honesty about paths.** Reading from a path breaks no rule, since the
  [name-not-a-path obligation](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)
  is about where a tool *writes*. `mpfb_add_asset` has always taken an absolute read path. The
  specification says this explicitly rather than leaving it implied.

## Architecture

- **`MPFB_OT_*` operators are not called.** They read scene properties, need a file dialog, and report
  `{'ERROR'}` then return `{'FINISHED'}`. Build from `MaterialService` and `MakeSkinMaterial`, as
  `set_asset_material` does.
- **`populate_from_mhmat()` takes a path and there is no string form.** Write the MHMAT to a temporary
  file outside any asset directory and let MPFB's own parser read it, so its aliases and coercions
  apply, then remove it.
- **A named Blender image has no filename for the template.** Build with `has_<slot>` true and an empty
  filename, as `create_makeskin_template_material()` does, then assign `node.image`.
- **`shared/texture_writing.py` is what FR 049 and FR 050 share**, and it replaces MPFB's
  `check_that_all_textures_are_saved()`, which re-encoded the gi's diffuse from 2.5 to 3.2 MB and its
  normal map from 17.0 to 18.2 MB. An image with a file and no unsaved changes is **copied byte for
  byte**. An image with unsaved changes or no file is written with
  `image.save(filepath=dest, save_copy=True)`, which Blender 5.1's API provides and which leaves the
  image's own path and state alone. `export_to_disk()` then finds source and destination equal and
  copies nothing.
- **This departs from MPFB's panel on purpose**, and the
  [integration rule](../../specifications/mpfb-integration.md#where-a-service-falls-short-of-what-its-own-code-says-it-does-follow-the-stated-intent)
  covers it: the operator's docstring warns only that images are saved "alongside the MHMAT file". The
  behaviour is filed upstream when provoked.
- **Reaching `_TEXTURE_NAMES` and `_NONCOLOR`:** both are private to `makeskinmaterial.py`. Read them
  with `mpfb_surface.required_module_level`, so that a slot MPFB adds appears here without an edit.
- **Pitfall:** `_NODE_SOCKET_VALUES` writes the displacement strength under `displacementmapIntensity`,
  while the MHMAT key is `displacementMapIntensity`, so that value never reaches a written file, by
  MPFB's own comment. The round trip must cover it and say what it found.
- **Pitfall:** an alternate written beside a pack's asset lands in a directory the pack owns. FR 046's
  attribution will then claim it for that pack. The answer should say so, and the effort decides whether
  a warning is enough.

## Affected specifications

- [mutating-tools.md](../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more):
  a read path is not a write path; a source file is never changed.
- [mpfb-integration.md](../../specifications/mpfb-integration.md): the panel's re-encoding as a named
  departure; the MakeSkin store operators reimplemented from services.
- [tool-interface.md](../../specifications/tool-interface.md): `known_slots`; `path` and `image` as a
  source; the new name rule.
- [responses.md](../../specifications/responses.md): `in_effect`.
- [vision.md](../../specifications/vision.md#target-tool-catalog): three more tools.

## Tests

- **Unit, in `tests/`:** the source shape, `path` absolute with an image extension, the entry shapes, and
  the store name rule over a shared table on both sides. No slot vocabulary is checked here.
- **`bbb_shared/`:** `texture_writing.py` with a real file, proving by hash and modification time that
  the source is untouched, and with a dirty image and an unsaved one.
- **`ddd_mutating/`:** every refusal and that it wrote nothing; replace; reload after a file changes;
  colour space per slot.
- **`eee_composite/`:** the round trips in both directions and through both destinations.
- **Live check, a script in this subdir:** rebuild the gi's material from its three textures and store it
  as an alternate of the written `taido_gi`, then confirm `mpfb_list_asset_materials` lists it and that
  it renders the same in a headless Cycles still. The source hashes are compared before and after.
- **Smoke items** for all three. The store uses `dry_run`, so
  [verification/](../../verification/README.md)'s file list does not grow.

## Decisions taken while scoping

Asked on 2026-11-03:

- **Set, get and store.** Set and get only, and the whole panel including blank templates, were the
  alternatives.
- **A source is a path or a Blender image.** Absolute paths alone, and names in a human-chosen directory,
  were the alternatives.
- **Sources are never changed**, rather than reproducing MPFB and reporting it, or fixing MPFB first and
  depending on that release.
- **`license` and `author` default from the object and are reported**, as in
  [FR 050](../050-writing-mesh-assets/README.md#decisions-taken-while-scoping). Requiring them was offered.

*Not asked*, each argued where it is stated: `replace` defaulting to false as the panel's does (FR 9);
reloading a regenerated path (FR 11); recognising MakeSkin by node names (FR 16); `dry_run` (FR 25).

## References

- [NEXT_STEPS: The MakeClothes and MakeSkin workflows](../NEXT_STEPS.md#the-makeclothes-and-makeskin-workflows).
- `interacting_with_blender/taido/gi/tools/apply_material.py`.
- mpfb2: `entities/material/makeskinmaterial.py`, `entities/material/mhmaterial.py`,
  `ui/create_assets/makeskin/operators/` (`importmaterial.py`, `writelibrary.py`, `writealternate.py`),
  `data/node_trees/makeskin.json`, `docs/ui/create_assets/makeskin.md`.
- Blender 5.1 Python API: `bpy.types.Image.save(filepath, quality, save_copy)`.
