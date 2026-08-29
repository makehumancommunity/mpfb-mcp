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
the target tool catalog. `mpfb_get_human_summary` is the natural next introspection tool and can
now take its subject from FR 003's tools rather than assuming one is known, but it has not been
scoped into a feature request yet.

## Finding available assets

**Complete.** All three halves have landed — the rig one as `mpfb_list_rigs`
([FR 004](done/004-list-rigs/README.md)), the asset one as `mpfb_list_assets`
([FR 005](done/005-list-assets/README.md)) and the target one as `mpfb_list_targets`
([FR 006](done/006-list-targets/README.md)) — each with its live verification run as part of the
effort rather than left outstanding, unlike FR 001-003. See
[HISTORY.md](HISTORY.md#fr-004--mpfb_list_rigs) onwards for what each turned out to be.

Four conventions came out of them and now stand in
[architecture.md](../specifications/architecture.md):
[How tools name things that can be added](../specifications/architecture.md#how-tools-name-things-that-can-be-added)
from FR 004,
[How tools bound a large answer](../specifications/architecture.md#how-tools-bound-a-large-answer)
and
[How tools report a derived rather than recorded fact](../specifications/architecture.md#how-tools-report-a-derived-rather-than-recorded-fact)
from FR 005, and from FR 006 both
[Reading MPFB's data files directly](../specifications/architecture.md#reading-mpfbs-data-files-directly)
and
[A tool may report a fact MPFB's own UI does not show](../specifications/architecture.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show).
Follow them rather than restating them in a new request.

One thing FR 006 turned up is worth raising **upstream with mpfb2** rather than working around here:
MPFB's scan of `<user data>/targets/<section>/` matches only `*.target`, while its `custom` scan
matches both `*.target` and `*.target.gz`, so a gzipped target in a user targets directory is
loadable but invisible in MPFB's own modeling panels. `mpfb_list_targets` reports it with
`listed_in_mpfb_ui: false`; the asymmetry itself looks like an oversight in MPFB.

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
