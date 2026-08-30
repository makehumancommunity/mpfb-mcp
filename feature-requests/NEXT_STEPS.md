# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## Modeling

Most of the things in this section is done via TargetService.

### Macrodetails / phenotype

While macro details can be specified at human creation time, there are no tools for modifying
them afterwards. Things such as the following are needed:

- Getting the default macro dict (from TargetService)
- Getting the current macro details as a dict (from a named human or from active human)
- Modifying the macro detail settings and recalculating the macro stack

Consider whether the create human tool should move from separate parameters to instead 
using the macro detail dict as input. It is not obvious that this is a good idea, but it should
be considered.

### Detail targets

There is currently no tool at all for working with detail targets. Things such as the following
are needed:

- Inspecting the target stack (optionally filtering out macro details)
- Applying a single target
- Modifying the value of a single target
- Ensuring left-right symmetry
- Batch loading targets

## Adding assets

The next logical step would be the ability to add assets:

- Add rig, including a custom rig
- Add an MHCLO asset: needs to take asset type and material type as parameters
- Set skin: needs to take material type as parameter 

## Observability

Logging should be added so that it is possible to see the exact python code sent to blender,
and the reponses that came back.

## Second backend: the community "blender mcp"

mpfb-mcp should also run against the community [blender-mcp](https://github.com/ahujasid/blender-mcp)
add-on, not only blender lab's, so that a user who already has that one installed does not have
to install a second. This is settled as a goal — see
[vision.md](../specifications/vision.md#resolved-which-blender-mcp-both) for the resolution and
for what comparing the two add-ons turned up: the substantive difference is the result channel
(the exec namespace's `result` dict, against captured stdout), so the seam is a backend adapter
below `send_code()` that translates transport and result channel together, leaving the tools,
the payloads and `codegen/` untouched. Not yet scoped into a numbered request.
