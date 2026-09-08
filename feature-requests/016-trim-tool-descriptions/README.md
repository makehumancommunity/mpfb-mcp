# Trim the tool descriptions, and put the field names in

**Status:** Proposed

Measured for the first time by [FR 013](../done/013-live-verification/README.md): **20 tools, 66.7 KB
of descriptions plus 8.9 KB of parameter schemas — 75.6 KB, about 18,900 tokens** that an MCP client
loads before any work happens. The four largest are `mpfb_list_assets` (6.2 KB),
`mpfb_list_targets` (5.3 KB), `mpfb_add_asset` (5.1 KB) and `mpfb_get_object_info` (4.7 KB).

The interesting half of that finding is not the size. Reading the descriptions against what a real
consumer needed — FR 013's harness, which is a fair proxy — they divide into three kinds. Some are
load-bearing *because the answer is surprising*: that `asset_type` is required because MPFB's
default mislabels six of eight types, that `skin_type` follows the panel rather than the function
signature, that exactly one of `path` and `fragment` must be given. Some is rationale about MPFB's
behaviour that explains but does not instruct — why the label collision happens, how
`_modelsubpanels` builds a category name — and belongs in
[specifications/](../../specifications/) or behind the `mpfb_search_docs` tool
[vision.md](../../specifications/vision.md) already plans.

And some of what a caller needs is **missing**. Three tools cost FR 013's harness a round trip each
because the description names the concept and not the key: `objects_removed`, `rig_object_name`,
`asset_info.material_source`. The descriptions are long and still do not reliably name the fields a
caller has to read.

## Goals

**Primary: reduce the preloaded description budget toward ~45 KB**, by moving rationale out rather
than by compressing instruction.

**Secondary, and the reason this is worth doing at all: name the response fields.** A shorter
description that a caller can act on is the point; a shorter one they have to guess against is
worse than what exists.

**Explicitly not a goal:** removing the surprising facts. Every warning that exists because MPFB
does something unexpected stays, in full.

**The 66.7 KB baseline is now about 68.2 KB.** [FR 014](../done/014-uniform-performed-flag/README.md)
added a short paragraph to each of the eleven mutating tools' docstrings, saying to branch on
`performed` and read the tool's own verb. That is the second goal above arriving early — a response
field named rather than described — so the addition stays and the budget is measured against the
new figure.

## Functional requirements

- **FR-1.** Each of the four largest descriptions is reduced, with the removed rationale moved to
  [specifications/](../../specifications/) rather than deleted, and cross-referenced from the
  docstring in one line rather than restated.
- **FR-2.** Every tool's description names the response fields a caller branches on — at minimum
  the success flag (see [FR 014](../done/014-uniform-performed-flag/README.md)), the subject name, and
  the field carrying the thing the tool produced.
- **FR-3.** The total is measured before and after, by the same script that measured it here, and
  the number is recorded.
- **FR-4.** `mpfb_create_human`'s description is the smallest of the twenty at 930 bytes and is the
  one that should *grow*: it is the entry point, it takes the same macro dict
  `mpfb_set_macro_details` takes in a different shape, and it says nothing about the difference.

## Non-functional requirements

**Nothing that only a maintainer needs stays in a description.** The test to apply to a sentence:
would a caller with no access to this repository act differently because of it? If not, it is
specification text.

**Reversibility.** Description text is what an LLM caller reasons from and there is no test that
can tell a worse one from a better one. Trim in reviewable pieces, one tool at a time, rather than
in one pass over twenty files.

## Architecture

The descriptions are the tool functions' docstrings in `src/mpfbmcp/tools/`. Note that
`FastMCP` also derives ~8.9 KB of parameter schema from the signatures and their annotations, which
is not docstring text and is not in scope.

**Pitfall: the server instructions are separate**, in `src/mpfbmcp/__init__.py`'s `FastMCP(...)`
call, and are not counted in the 66.7 KB. They carry the ordering constraint and the
"which tool for what" map, and they are the right home for some of what comes out of the individual
descriptions.

## Affected specifications

- **[specifications/vision.md](../../specifications/vision.md)** — the natural destination for the
  per-tool rationale, whose catalog entries already carry much of it in shorter form.
- **[specifications/tool-interface.md](../../specifications/tool-interface.md)** — the destination
  for rationale that is really an input convention, and the natural home for a new note that a tool
  description is a call-time instrument with a measured budget. Rationale that turns out to be a
  *response* convention belongs in [responses.md](../../specifications/responses.md) instead; the
  split into per-topic specifications happened after this request was written.

## Tests

No unit tests can establish that a description is better. What can be tested, and should be, is the
budget: a test that asserts the total description size is under a stated ceiling, so the number
stops drifting silently between requests. FR 013 measured 66.7 KB against an FR 013-era estimate of
58.5 KB, which is how much it had grown unnoticed.

Live verification is not required.

## References

- [FR 013's review](../done/013-live-verification/review.md#does-the-tool-surface-fit-its-consumer) —
  the measurement, the three-way split, and the three field names the harness got wrong.
