# MPFB MCP

An MCP server with MPFB tools. Its Blender-side half is a companion add-on of our own, the
**MPFB Bridge** in [bridge/](bridge), which dispatches a closed vocabulary of named commands
rather than executing code.

## Status

Proof of concept. Thirty-one tools are implemented.

**All thirty tools that cross the socket speak to the bridge**, and there is nothing else
for them to speak to. The odd one out, `mpfb_list_docs`, answers from a local table and reaches
no Blender at all.

It was not always one machine. Until
[FR 033](feature-requests/done/033-retire-the-generated-code-path/README.md) a tool assembled a
Python program per call and sent it to blender lab's [blender_mcp](../blender_mcp) add-on to
`exec()`; the two ran side by side through four efforts so that they could be compared against a
real Blender before the old one was deleted. On one Blender in one session the same smoke run
takes **4.9 s on the bridge and took 48.5 s on the path it replaced**, and the Blender-side logic
is now testable against a real MPFB, which it never was.
See [CLAUDE.md](CLAUDE.md#commands) for the environment variables and
[NEXT_STEPS.md](feature-requests/NEXT_STEPS.md) for what remains.

**Introspection** — read-only, and each of them always answers rather than failing:

- `mpfb_get_status` — is MPFB present, initialized and correctly configured?
- `mpfb_list_objects` — which MakeHuman objects are in the current scene?
- `mpfb_get_object_info` — what is this object, what was it made from, and what belongs with it?
- `mpfb_get_macro_details` — what is this character's phenotype?
- `mpfb_get_target_stack` — which detail morphs are on this character, and how strong?
- `mpfb_get_face_units` — what is this character's face doing, in ARKit face units?
- `mpfb_get_expression` — which saved expressions is this character wearing, and do they explain
  its face?

**Catalogues** — what could be added, each entry named the way the acting tool will want it:

- `mpfb_list_rigs` — which armatures could be attached?
- `mpfb_list_assets` — which clothes, body parts, proxies and skins are installed?
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
- `mpfb_set_targets` — set detail morphs, batched.
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
- `mpfb_save_preset` / `mpfb_create_human_from_preset` — keep a character past this Blender
  session, and build a new one from a saved character. These and `mpfb_save_expression` are the
  only tools here that write a file, and nothing in Blender can undo it, so both saving tools
  refuse to overwrite unless told to.

**Order matters and MPFB reports no error when it is wrong**: add the rig before the clothes, and
generate a Rigify rig after them. The tools report the violation they can see rather than
enforcing it.

**All thirty-one have been run against a real Blender, and re-checking all of them is one short
command.** [verification/](verification/) is a smoke run — one call per tool with default
arguments, measured at 1.5 s for the whole set against a headless Blender — so confirming that
nothing has stopped working is a command rather than a session. It leaves what it builds in the
scene, which is the price of the add-on having no way to execute code on a harness's behalf; point
it at a Blender you are willing to throw away, and read
[verification/README.md](verification/README.md#what-fr-033-cost-this-instrument). Each tool was
also proved exhaustively once, by the effort that added it; see
[HISTORY.md](feature-requests/HISTORY.md) for what each of those runs found.

See [src/mpfbmcp](src/mpfbmcp) and [CLAUDE.md](CLAUDE.md) for how they work and how to run them.

## Documentation

The structured specifications for the project live in the
[specifications/](specifications/) directory. Start with its
[index](specifications/README.md). Highlights:

- [Vision](specifications/vision.md) — why this project exists, why a bridge add-on of our own,
  and the target tool catalog.
- [Architecture](specifications/architecture.md) — standing architectural principles new
  tools should follow.

To install every part from this checkout — MPFB, the bridge add-on, the server and an MCP client
configuration — follow [INSTALL.md](INSTALL.md). Developer setup and commands are documented in
[CLAUDE.md](CLAUDE.md). Planned and in-progress
development efforts are tracked in [feature-requests/](feature-requests/).
