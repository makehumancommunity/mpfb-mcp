# MPFB MCP

This is currently only an idea: create a MCP server with MPFB tools, which piggy-backs on 
the [existing blender mcp](../blender_mcp) implementation, using it's tcp connection to
execute MPFB-related code.

## Shape

A normal Python package, published to PyPI and/or installed from git, that runs as its **own MCP
server**. It talks to the *existing, unmodified* blender_mcp add-on over the same TCP socket.

```
Claude / other MCP client
   |
   |-- stdio --> blender_mcp  (generic Blender tools)   --\
   |                                                       >-- TCP :9876 --> blender_mcp add-on --> exec() in Blender
   |-- stdio --> mpfb-mcp     (MPFB-specific tools)     --/                                            |
                                                                                                       v
                                                                                            MPFB services (bl_ext.*.mpfb)
```

The user enables MPFB and the MCP add-on in Blender as usual, starts the MCP server from the
add-on preferences, and configures two MCP servers in their client. No new Blender extension, no
fork of blender_mcp, no coordination of install order.

## Hypothetical tool set

These are just ideas at the moment

**Introspection (read-only)**

- `mpfb_get_status` — MPFB present? version? data roots configured? asset packs installed?
- `mpfb_get_human_summary` — for a given/active human: macro details, equipped assets, rig,
  skin, active targets
- `mpfb_list_assets` — clothes / skins / proxies / poses, optionally filtered by pack

**Creation and modification**

- `mpfb_create_human` — wraps `HumanService.create_human()` plus a macro-detail dict
- `mpfb_set_macro_details` — gender/age/weight/muscle/height/proportions via `TargetService`
- `mpfb_set_target_value` — arbitrary named target
- `mpfb_add_asset` — clothes/proxy via `add_mhclo_asset()`
- `mpfb_set_skin` — via `set_character_skin()`
- `mpfb_add_rig` — builtin or custom

**Documentation**

- `mpfb_search_docs` — ranked search over bundled MPFB documentation, mirroring how blmcp exposes
  Blender's RST reference. Likely sourced from `makehuman-static-website`.

## Unanswered questions

The idea is to piggyback on [blender lab's mcp](../blender_mcp). However, there is 
[another MCP implementation](https://github.com/ahujasid/blender-mcp) which is also called "blender mcp".
This is unrelated to blender lab's implementation. Chances are some users will have opted for installing
this instead, since it has a richer feature set. Maybe it'd be possible to support both as backends? 

