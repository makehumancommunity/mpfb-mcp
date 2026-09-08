# Trim the tool descriptions, and put the field names in

**Status:** Done

Measured for the first time by [FR 013](../013-live-verification/README.md): **20 tools, 66.7 KB
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
[specifications/](../../../specifications/) or behind the `mpfb_search_docs` tool
[vision.md](../../../specifications/vision.md) already plans.

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

**The 66.7 KB baseline is now about 68.2 KB.** [FR 014](../014-uniform-performed-flag/README.md)
added a short paragraph to each of the eleven mutating tools' docstrings, saying to branch on
`performed` and read the tool's own verb. That is the second goal above arriving early — a response
field named rather than described — so the addition stays and the budget is measured against the
new figure.

## Functional requirements

- **FR-1.** Each of the four largest descriptions is reduced, with the removed rationale moved to
  [specifications/](../../../specifications/) rather than deleted, and cross-referenced from the
  docstring in one line rather than restated.
- **FR-2.** Every tool's description names the response fields a caller branches on — at minimum
  the success flag (see [FR 014](../014-uniform-performed-flag/README.md)), the subject name, and
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

- **[specifications/vision.md](../../../specifications/vision.md)** — the natural destination for the
  per-tool rationale, whose catalog entries already carry much of it in shorter form.
- **[specifications/tool-interface.md](../../../specifications/tool-interface.md)** — the destination
  for rationale that is really an input convention, and the natural home for a new note that a tool
  description is a call-time instrument with a measured budget. Rationale that turns out to be a
  *response* convention belongs in [responses.md](../../../specifications/responses.md) instead; the
  split into per-topic specifications happened after this request was written.

## Tests

No unit tests can establish that a description is better. What can be tested, and should be, is the
budget: a test that asserts the total description size is under a stated ceiling, so the number
stops drifting silently between requests. FR 013 measured 66.7 KB against an FR 013-era estimate of
58.5 KB, which is how much it had grown unnoticed.

Live verification is not required.

## What happened

**70,352 B → 47,759 B of descriptions: a third of it, and the four largest are no longer the four
largest.** The schemas were untouched at 8,105 B, so an MCP client now preloads 55,864 B where it
preloaded 78,457 B. `mpfb_list_assets` went 6,246 → 3,309 and `mpfb_add_asset` 5,407 → 2,893;
`mpfb_create_human` grew 1,259 → 2,064, as FR-4 asks.

**FR-3 asked for "the same script that measured it here". There was none** — FR 013 measured by
hand and recorded the number, which is exactly how the figure had drifted 58.5 → 66.7 KB unnoticed
in the first place. So the measurement is now
[tests/test_description_budget.py](../../../tests/test_description_budget.py): a ceiling the suite
asserts, and a per-tool table when the module is run as a script. It measures
`mpfbmcp.build_server()` rather than a list of tools of its own, which meant splitting the server's
construction out of `main()` — so a tool registered without being thought about is inside the
budget rather than outside it.

**Three of the savings were not in the request, and together they are half of it.**

- **10 KB of the 70 was whitespace.** `Tool.from_function()` takes `fn.__doc__` verbatim, so every
  line of every description crossed the wire carrying the eight spaces it is indented by in the
  file. `build_server()` now dedents each description once, after registration. Nothing a reader
  of the source or of the response ever saw changed.
- **The conventions every tool was repeating moved to the server instructions**, which are sent
  once rather than twenty times: the envelope, the `name`/active-object subject convention, that a
  refusal is an answer carrying `found`/`ready`/`blocked_by`, the uniform `performed` flag, and
  that a capped listing always reports `truncated` and `total_count`. The instructions grew 2.7 KB
  → 3.9 KB and about 6 KB came out of the twenty descriptions. Each tool now says only where it
  differs from the convention — which is the part worth reading.
- **A strict application of this request's own test** — would a caller with no access to this
  repository act differently for having read this sentence? — took most of the rest. `object_type`
  echoing "since MPFB normalises the value", the enumeration of what a mislabelled asset type
  costs, the four things `proxy_extras` reports (they are in the response), the six-line refusal
  lists rewritten as one sentence naming the codes and keeping only the surprising ones
  (`already_rigged`, `not_a_mesh_asset`, `skin_failed`).

**It stopped at 47,759 rather than ~45,000, and that is a decision rather than a shortfall.** What
was left at that point was instruction: response field names, the argument vocabularies, and the
surprising facts this request explicitly protects. The ceiling in the test is 48,500, which leaves about a
paragraph of room: enough that a real addition fits, and not enough for a habit.

**FR-1's "cross-referenced from the docstring in one line" is read as the *module* docstring**, not
the tool's. A link to `specifications/` is for the maintainer standing in the file, and putting it
in the description would spend the budget on a path no caller can open. `list_assets.py` and
`list_targets.py` gained one such line each; everything else that came out already had a home in a
payload docstring — the `scale_assumption` bands, the label collision, `exclude_default` being
accepted and never read — which was checked before anything was deleted.

**What the trim nearly cost, and how it was caught.** Editing twenty docstrings by paragraph
surgery deleted three response-field bullet lists outright — `mpfb_get_object_info`'s,
`mpfb_list_rigs`', `mpfb_get_macro_details`' — each time by replacing a bullet *list* where a
bullet was meant. A token diff of every backtick-quoted identifier in each docstring against its
version in `HEAD` found all three, plus six mutating tools that had lost the word `performed`
FR 014 put there. That audit is worth repeating on any future pass over these files.

**Two standing specifications gained a section**, both for rationale that came out of a
description and had nowhere else to live:
[A tool description is call-time instruction with a budget](../../../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget)
and
[MPFB caches what it scans](../../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides).

## Verification status

Live verification was not required and the generated programs are unchanged — no payload, no
`assemble()` call and no argument was touched, only docstrings, the server instructions and the
construction of the server object. What was checked against the running Blender is that the server
still builds its twenty tools and that a call still round-trips *through them*:
`mpfbmcp.build_server()` dispatched `mpfb_list_objects` and `mpfb_get_status` against MPFB 2.0.17,
which is the path `main()` takes and the one the new `build_server()` split could have broken; and
`verification/check_fr004.py` was re-run, 11 items passed, no datablock left behind.

## References

- [FR 013's review](../013-live-verification/review.md#does-the-tool-surface-fit-its-consumer) —
  the measurement, the three-way split, and the three field names the harness got wrong.
