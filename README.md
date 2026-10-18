# MPFB MCP

An MCP server with MPFB tools. Its Blender-side half is a companion add-on of our own, the
**MPFB Bridge** in [bridge/](bridge), which dispatches a closed vocabulary of named commands
rather than executing code.

In practice, you will most likely want to use this in parallel with a Blender MCP bridge such as
either of:

- Blender Lab's [Blender MCP](https://projects.blender.org/lab/blender_mcp)
- Ahujasid's [MCP for Blender](https://github.com/ahujasid/mcp-for-blender)

In fact, you can control MPFB solely by using either of these, but it will then be an inefficient
and token-heavy thing. By steering MPFB-specific operation to the MPFB specific bridge, 
you can speed up things and save some tokens.

## Status

Early beta. Forty-one tools are implemented.

**Introspection** — read-only, and each of them always answers rather than failing:

- `mpfb_get_status` — is MPFB present, initialized and correctly configured?
- `mpfb_get_character_summary` — what is this character, in one call: phenotype, rig, assets,
  skin, morphs and face, each exactly as the detailed tool below would report it?
- `mpfb_list_objects` — which MakeHuman objects are in the current scene?
- `mpfb_get_object_info` — what is this object, what was it made from, and what belongs with it?
- `mpfb_get_macro_details` — what is this character's phenotype?
- `mpfb_get_target_stack` — which modeling targets are on this character, and how strong?
- `mpfb_get_face_units` — what is this character's face doing, in ARKit face units?
- `mpfb_get_expression` — which saved expressions is this character wearing, and do they explain
  its face?
- `mpfb_get_material_settings` — what are this character's iris colours, layered skin and hair and
  garment tints, exactly as a preset would save them?
- `mpfb_get_pose_controls` — which bones pose this character, by body part, what does each do, and
  where does it rest?
- `mpfb_get_pose` — what is this character's pose now: what is off rest, where are its hands, feet,
  hips and head, and is a limb stretched or out of reach?

**Catalogues** — what could be added, each entry named the way the acting tool will want it:

- `mpfb_list_rigs` — which armatures could be attached?
- `mpfb_list_assets` — which garments, body parts, body proxies and skins are installed?
- `mpfb_list_targets` — which modeling targets could be set?
- `mpfb_list_asset_materials` — which other materials ship beside this equipped asset?
- `mpfb_list_presets` — which characters have been saved?
- `mpfb_list_expressions` — which saved expressions are installed?

**Documentation** — addresses to look something up, and neither of them fetches anything:

- `mpfb_list_urls` — where to download MPFB, get asset packs, ask on the forum, file a bug.
  Answers even when MPFB or Blender is unreachable, which is when those links matter most.
- `mpfb_list_docs` — MPFB's developer documentation, one document per service and file format.

**Creation and modification:**

- `mpfb_create_human` — wraps MPFB's `HumanService.create_human()`.
- `mpfb_set_macro_details` — change a character's phenotype in place.
- `mpfb_set_targets` — set modeling targets, batched.
- `mpfb_symmetrize_targets` — copy one side of a character onto the other.
- `mpfb_set_face_units` — compose a character's face from ARKit face units. Transient: not saved
  by a preset, and overwritten by the next expression applied.
- `mpfb_apply_expressions` — put a character into saved expressions, blended at chosen weights,
  or take them all off.
- `mpfb_save_expression` — keep a composed face as an expression file, which is what makes it
  survive: apply the file, and presets carry it.
- `mpfb_refit_human` — refit everything to a changed body.
- `mpfb_add_rig` / `mpfb_generate_rigify_rig` — attach an armature, and finish a Rigify meta rig.
- `mpfb_add_asset` / `mpfb_remove_asset` — equip an MHCLO asset, and take it off properly.
- `mpfb_set_skin` — give the character a skin, in any of MPFB's five material models.
- `mpfb_set_asset_material` — recolour an equipped asset, or restore its own material.
- `mpfb_set_material_settings` — change iris colours, the layered skin and the tint of hair and
  garments, batched, in a way a preset keeps.
- `mpfb_set_pose_bones` — pose a character: move, rotate, aim and scale its controls in the
  character's own forward, left and up, batched, and say where each one actually ended up.
- `mpfb_set_pose_switches` — change a generated Rigify rig's IK/FK, pole, parent and stretch
  switches, keeping each limb where it is as Rigify's own buttons do.
- `mpfb_reset_pose` — put a character back at rest, and answer with the calls that put the pose
  back: Blender's own undo does not see what these tools do.
- `mpfb_save_preset` / `mpfb_create_human_from_preset` — keep a character past this Blender
  session, and build a new one from a saved character.
- `mpfb_create_export_copy` / `mpfb_export_character` — take a character to a game engine or
  another application: a processed copy, as MPFB's Export copy panel makes one, with visemes, ARKit
  face units and GameEngine materials if asked; then one FBX, glTF or USD file, with presets for
  Unity, Unreal and Godot. The file goes in a directory set in the MPFB Bridge's preferences, never
  one the agent picks.

`mpfb_save_preset`, `mpfb_save_expression` and `mpfb_export_character` are the only tools here
that write a file, and nothing in Blender can undo it, so each refuses to overwrite unless told to.

**Order matters and MPFB reports no error when it is wrong**: add the rig before the garments, and
generate a Rigify rig after them. The tools report the violation they can see rather than
enforcing it.

See [src/mpfbmcp](src/mpfbmcp) and [CLAUDE.md](CLAUDE.md) for how they work and how to run them.

## Documentation

The structured specifications for the project live in the [specifications/](specifications/) directory.
 Start with its [index](specifications/README.md). Highlights:

- [Vision](specifications/vision.md) — why this project exists, why a bridge add-on of our own,
  and the target tool catalog.
- [Architecture](specifications/architecture.md) — standing architectural principles new
  tools should follow.

To install every part from this checkout — MPFB, the bridge add-on, the server and an MCP client
configuration — follow [INSTALL.md](INSTALL.md). Developer setup and commands are documented in
[CLAUDE.md](CLAUDE.md). Planned and in-progress development efforts are tracked 
in [feature-requests/](feature-requests/).
