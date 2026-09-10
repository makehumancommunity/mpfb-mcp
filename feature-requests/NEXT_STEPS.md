# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## Saving, listing and loading character presets

**Scoped as [FR 025](025-character-presets/README.md) (Accepted).**

Humans are stored in presets ("save files"), which are simple json structures. Handling these
is a core functionality of MPFB.

The MHM path can be left alone for now, it's only relevant in legacy MakeHuman pipelines.

## Expressions

**Scoped as two requests, in this order: [FR 026](026-face-units/README.md) (Accepted) for the
face-unit layer, then [FR 027](027-expression-library/README.md) (Accepted) for the saved-expression
library and the stack that applies it. FR 027 extends FR 026's tools; see
[the dependency](027-expression-library/README.md#the-dependency-and-what-happens-if-the-order-reverses).**

These are the `!ex-` prefixed shape keys. They depend on particular asset packs being installed.
Expressions should be a mix of functionality from the `src/mpfb/ui/create_assets/makeexpression`
and `src/mpfb/ui/apply_assets/useexpression` UI code hierarchies in MPFB. TargetService has
some functionality for working with expressions.

## Saving expressions

Queued behind [FR 027](027-expression-library/README.md), which reads and applies expressions but
writes none. An `mpfb_save_expression` would close the gap named in
[FR 026](026-face-units/README.md#a-composed-face-is-transient): a face composed from ARKit units
survives nothing today — not a preset save (a preset serializes the applied-expressions *stack*, and
a composed face has no stack rows), and not the next library call, which clears every `!ex-` key
before rebuilding.

`FaceService.save_expression` already exists and already does the filtering, rounding and metadata
defaulting. The tool should follow [FR 025](025-character-presets/README.md)'s name-not-a-path
convention and its `overwrite: False` default, writing to
`LocationService.get_user_data("expressions")`. It comes after FR 027 because what it writes is read
back through the library.

## Visemes and lip sync

The rest of `FaceService`, deliberately excluded from both expression requests (see
[Not visemes](026-face-units/README.md#not-visemes)): `MICROSOFT_VISEMES` and `META_VISEMES`,
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

## Finding, downloading and installing asset packs

**The URL is no longer the open question.** `mpfb_list_urls` reports `URL_ASSET_PACKS` (and
`URL_SYSTEM_ASSETS`), read live out of MPFB's own constants — see
[FR 024](done/024-documentation-urls/README.md), which landed for exactly this dependency.

What remains is the downloading and installing, and FR 024 changed its shape rather than only
unblocking it: **mpfb-mcp opens no network connection except the one to the blender_mcp add-on**
is now a [standing constraint](../specifications/architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on).
So this effort cannot simply fetch a pack. Either the retrieval happens on the *Blender* side, in
generated code, which is a different thing from mpfb-mcp opening a socket and needs to be argued
explicitly rather than assumed; or the client is handed the address and the tool installs what the
user has already downloaded. There is an operator for loading a pack from zip in MPFB which can be
used as inspiration for the second half either way.

## Exporting characters

Need to have a tool for exporting a character to, for example, fbx. This should involve 
similar procedures as is used in `src/mpfb/ui/operations/exportops` in MPFB.

## Handle the 4 KB chunked read against blender_mcp

**The largest single cost in this package is one line in an add-on we do not own.**
blender_mcp's `mcp_to_blender_server._service_clients()` does exactly one `conn.recv(4096)` per
timer tick and then returns, so a request arrives at one 4 KB chunk per tick — 250 ms each while
the add-on is busy, and 1 s each once five seconds have passed without a request *finishing*, since
bytes arriving do not reset its idle countdown. A generated program therefore costs about 250 ms
per 4 KB, or 1 s per 4 KB against the idle Blender an agent actually meets, **regardless of what
the program does**: a 50 KB call is 3 s or 12 s of waiting before Blender has read the request.

It should be investigated if the other blender mcp solution (mentioned in "Second backend" below)
would be a better fit or if it has the same problem.

## Second backend: the community "blender mcp"

mpfb-mcp should also run against the community [blender-mcp](https://github.com/ahujasid/blender-mcp)
add-on, not only blender lab's, so that a user who already has that one installed does not have
to install a second. This is settled as a goal — see
[vision.md](../specifications/vision.md#resolved-which-blender-mcp-both) for the resolution and
for what comparing the two add-ons turned up: the substantive difference is the result channel
(the exec namespace's `result` dict, against captured stdout), so the seam is a backend adapter
below `send_code()` that translates transport and result channel together, leaving the tools,
the payloads and `codegen/` untouched. Not yet scoped into a numbered request.

