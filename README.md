# MPFB MCP

An MCP server with MPFB tools, which piggy-backs on the [existing blender
mcp](../blender_mcp) implementation, using its TCP connection to execute
MPFB-related code.

## Status

Proof of concept. Four tools are implemented:

- `mpfb_create_human` — wraps MPFB's `HumanService.create_human()`.
- `mpfb_get_status` — is MPFB present, initialized and correctly configured?
- `mpfb_list_objects` — which MakeHuman objects are in the current scene?
- `mpfb_get_object_info` — what is this object, what was it made from, and what belongs with it?

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
