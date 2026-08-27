# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started; some already have one (linked below).

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

## Introspection tools

- [FR 001](001-mpfb-get-status/README.md) (Accepted) — `mpfb_get_status`: MPFB presence,
  version, addon install path, and configured/available data roots and asset packs. The
  natural first introspection tool from the [target
  catalog](../specifications/vision.md#target-tool-catalog), and the tool an agent should
  reach for first when any other MPFB tool call fails unexpectedly.

Beyond FR 001, see [specifications/vision.md](../specifications/vision.md#target-tool-catalog)
for the rest of the target tool catalog — nothing else has been scoped into a feature request
yet.
