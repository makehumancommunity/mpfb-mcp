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

See [specifications/vision.md](../specifications/vision.md#target-tool-catalog) for the rest of
the target tool catalog — `mpfb_get_human_summary` and `mpfb_list_assets` are the natural next
introspection tools, but neither has been scoped into a feature request yet. Of the efforts
below, only "Basic object finding and identification" is currently scoped, as
[FR 003](003-object-finding/README.md).

## Basic object finding and identification

Scoped as [FR 003](003-object-finding/README.md) (status: Accepted), which narrows the four
tools below to two parameterized ones — `mpfb_list_objects` and `mpfb_get_object_info`.

There are some fundamental tools which need to come into place, in order to find and identify
makehuman objects:

- A tool for listing the names of all objects identified as of type Basemesh
- A tool for listing the names of all objects identified as of type Skeleton
- A tool for identifying which makehuman type an object is (object specified by name)
- A tool for listing the names and types of all related objects (rigs, child meshes...) of a 
  makehuman object (any makehuman object, specified by name)

ObjectService has many of the necessary methods for finding and identifying makehuman objects.

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


