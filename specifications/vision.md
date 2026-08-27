# Vision

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

## Goal

MPFB (MakeHuman Plugin For Blender) exposes a rich Python service layer
(`HumanService`, `TargetService`, `AssetService`, etc. — see `../mpfb2/`) for creating and
editing MakeHuman characters, but that layer is only reachable from *inside* a running
Blender process. mpfb-mcp's goal is to make MPFB's capabilities available to LLM agents (and
other MCP clients) as a normal set of MCP tools, without requiring any change to MPFB or to
the Blender MCP tooling it relies on.

## Approach: piggyback, don't fork

mpfb-mcp is a normal Python package, installed like any other MCP server, that runs as its
own MCP server process. It talks to the *existing, unmodified*
[blender_mcp](../../blender_mcp) add-on over the same TCP socket blender_mcp itself uses,
sending it generated Python code to execute inside Blender:

```
Claude / other MCP client
   |
   |-- stdio --> blender_mcp  (generic Blender tools)   --\
   |                                                       >-- TCP :9876 --> blender_mcp add-on --> exec() in Blender
   |-- stdio --> mpfb-mcp     (MPFB-specific tools)     --/                                            |
                                                                                                        v
                                                                                             MPFB services (bl_ext.*.mpfb)
```

The user enables MPFB and the blender_mcp add-on in Blender as usual, starts blender_mcp's
socket server from its preferences, and configures **two** MCP servers in their client. No new
Blender extension, no fork of blender_mcp, and no coordination of install order between MPFB
and blender_mcp is required. See [architecture.md](architecture.md) for how this is
implemented.

## Target tool catalog

These are the intended tools; only those marked **Implemented** exist today (see
[CLAUDE.md](../CLAUDE.md)). Naming and grouping below is indicative, not committed — each
tool should get its own feature request when scoped.

**Introspection (read-only)**

- `mpfb_get_status` — MPFB present? version? data roots configured? asset packs installed?
  **Implemented.** Takes no arguments and always answers, classifying the install as `absent`,
  `not_initialized` (loaded but `register()` did not complete) or `ok`; when `ok` it also
  reports version, install path, configured paths, the data roots MPFB will actually search,
  installed asset packs, and Blender version/platform/compatibility. The tool to reach for
  first when another MPFB tool fails unexpectedly.
- `mpfb_get_human_summary` — for a given/active human: macro details, equipped assets, rig,
  skin, active targets
- `mpfb_list_assets` — clothes / skins / proxies / poses, optionally filtered by pack

**Creation and modification**

- `mpfb_create_human` — wraps `HumanService.create_human()` plus a macro-detail dict.
  **Implemented**, as a proof of concept covering scale + the macro-detail dict only (not
  `mask_helpers`/`detailed_helpers`/`extra_vertex_groups`/`feet_on_ground`).
- `mpfb_set_macro_details` — gender/age/weight/muscle/height/proportions via `TargetService`
- `mpfb_set_target_value` — arbitrary named target
- `mpfb_add_asset` — clothes/proxy via `add_mhclo_asset()`
- `mpfb_set_skin` — via `set_character_skin()`
- `mpfb_add_rig` — builtin or custom

**Documentation**

- `mpfb_search_docs` — ranked search over bundled MPFB documentation, mirroring how blmcp
  exposes Blender's RST reference. Likely sourced from `../../makehuman-static-website`.

## Open design question: which "blender mcp"?

There are two unrelated projects called "blender mcp": blender lab's implementation (the
intended backend, at `../../blender_mcp`, which this project piggybacks on) and a separate,
more feature-rich [community implementation](https://github.com/ahujasid/blender-mcp). Some
users may have the latter installed instead of the former. Whether to support both as
backends — and if so, how mpfb-mcp would detect which one it's talking to — is unresolved.
