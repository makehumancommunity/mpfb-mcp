# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

`mpfb_get_status`, the first introspection tool, has landed —
see [FR 001](done/001-mpfb-get-status/README.md) and its
[entry in HISTORY.md](HISTORY.md#fr-001--mpfb_get_status). Its manual verification against a
running Blender is still outstanding and is tracked in the request itself, under
[Verification status](done/001-mpfb-get-status/README.md#verification-status), rather than as
an effort here.

The code-structure and readability rework has also landed — see
[FR 002](done/002-codegen-structure/README.md) and its
[entry in HISTORY.md](HISTORY.md#fr-002--code-generation-restructured-into-per-tool-payload-files).
Its real-Blender smoke pass is likewise still outstanding, tracked under
[Verification status](done/002-codegen-structure/README.md#verification-status) in the request.

Basic object finding and identification has landed too, as `mpfb_list_objects` and
`mpfb_get_object_info` — see [FR 003](done/003-object-finding/README.md) and its
[entry in HISTORY.md](HISTORY.md#fr-003--object-finding-and-identification). Its live
verification is the largest outstanding one of the three, since every `asset_info` value rests
on reading MPFB's source rather than on observation; it is tracked under
[Verification status](done/003-object-finding/README.md#verification-status) in the request.

See [specifications/vision.md](../specifications/vision.md#target-tool-catalog) for the rest of
the target tool catalog — `mpfb_get_human_summary` and `mpfb_list_assets` are the natural next
introspection tools, and both can now take their subject from FR 003's tools rather than
assuming one is known, but neither has been scoped into a feature request yet. None of the
efforts below is currently scoped.

## Observability

Logging should be added so that it is possible to see the exact python code sent to blender,
and the reponses that came back.

## Get available detail targets

In order to model, the LLM needs to know which targets are available. These come from two
distinct sources: `targets.json` in the system data directory and the targets installed 
in the user data directory.

A new tool should be added for getting information about available targets. It should return:

- The absolute path to target.json (which the LLM can then parse outside the MCP pipeline)
- A list of targets available in the user data directory.

Note that macrodetails/phenotype is a separate question, as that is handled via attributes
on the basemesh rather than by loading target files specifically.


