# MPFB MCP

An MCP server with MPFB tools. Its Blender-side half is a companion add-on of our own, the
**MPFB Bridge** in [bridge/](bridge), which dispatches a closed vocabulary of named commands
rather than executing code.

## Status

Proof of concept. Twenty-five tools are implemented.

**All twenty-four tools that cross the socket speak to the bridge**, and that is what an
unconfigured install uses. The twenty-fifth, `mpfb_list_docs`, answers from a local table and
reaches no Blender at all.

The older arrangement — assembling a Python program per call and sending it to blender lab's
[blender_mcp](../blender_mcp) add-on to `exec()` — still works and is one variable away
(`MPFB_MCP_BACKEND=blender_mcp`). It is kept for one more effort because it is the other half of
the comparison that says the bridge answers the same thing; retiring it is
[FR 033](feature-requests/033-retire-the-generated-code-path/README.md). On one Blender in one
session the same smoke run takes **3.9 s on the bridge and 48.5 s on the generated path**.
See [CLAUDE.md](CLAUDE.md#commands) for the environment variables and
[NEXT_STEPS.md](feature-requests/NEXT_STEPS.md) for what remains.

**Introspection** — read-only, and each of them always answers rather than failing:

- `mpfb_get_status` — is MPFB present, initialized and correctly configured?
- `mpfb_list_objects` — which MakeHuman objects are in the current scene?
- `mpfb_get_object_info` — what is this object, what was it made from, and what belongs with it?
- `mpfb_get_macro_details` — what is this character's phenotype?
- `mpfb_get_target_stack` — which detail morphs are on this character, and how strong?

**Catalogues** — what could be added, each entry named the way the acting tool will want it:

- `mpfb_list_rigs` — which armatures could be attached?
- `mpfb_list_assets` — which clothes, body parts, proxies and skins are installed?
- `mpfb_list_targets` — which modeling targets could be set?
- `mpfb_list_asset_materials` — which other materials ship beside this equipped asset?
- `mpfb_list_presets` — which characters have been saved?

**Documentation** — addresses to look something up, and neither of them fetches anything:

- `mpfb_list_urls` — where to download MPFB, get asset packs, ask on the forum, file a bug.
  Answers even when MPFB or Blender is unreachable, which is when those links matter most.
- `mpfb_list_docs` — MPFB's developer documentation, one document per service and file format.

**Creation and modification:**

- `mpfb_create_human` — wraps MPFB's `HumanService.create_human()`.
- `mpfb_set_macro_details` — change a character's phenotype in place.
- `mpfb_set_targets` — set detail morphs, batched.
- `mpfb_symmetrize_targets` — copy one side of a character onto the other.
- `mpfb_refit_human` — refit everything to a changed body.
- `mpfb_add_rig` / `mpfb_generate_rigify_rig` — attach an armature, and finish a Rigify meta rig.
- `mpfb_add_asset` / `mpfb_remove_asset` — equip an MHCLO asset, and take it off properly.
- `mpfb_set_skin` — give the character a skin, in any of MPFB's five material models.
- `mpfb_set_asset_material` — recolour an equipped asset, or restore its own material.
- `mpfb_save_preset` / `mpfb_create_human_from_preset` — keep a character past this Blender
  session, and build a new one from a saved character. The only tool here that writes a file, and
  nothing in Blender can undo it, so it refuses to overwrite unless told to.

**Order matters and MPFB reports no error when it is wrong**: add the rig before the clothes, and
generate a Rigify rig after them. The tools report the violation they can see rather than
enforcing it.

**All twenty-five have been run against a real Blender, and re-checking all of them is one short
command.** [verification/](verification/) is a smoke run — one call per tool with default
arguments, measured at 50.2 s for the whole set — so confirming that nothing has stopped working
is a command rather than a session. Each tool was also proved exhaustively once, by the effort
that added it; see [HISTORY.md](feature-requests/HISTORY.md) for what each of those runs found.

See [src/mpfbmcp](src/mpfbmcp) and [CLAUDE.md](CLAUDE.md) for how they work and how to run them.

## Documentation

The structured specifications for the project live in the
[specifications/](specifications/) directory. Start with its
[index](specifications/README.md). Highlights:

- [Vision](specifications/vision.md) — why this project exists, the piggyback approach, and
  the target tool catalog.
- [Architecture](specifications/architecture.md) — standing architectural principles new
  tools should follow.

Developer setup and commands are documented in [CLAUDE.md](CLAUDE.md). Planned and in-progress
development efforts are tracked in [feature-requests/](feature-requests/).
