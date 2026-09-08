# One more shared code-generation fragment, and the census that found it

**Status:** Proposed

[FR 013](../done/013-live-verification/README.md) asked the right question about the duplication in
`codegen/payloads/`: not whether the code repeats — it does, in nineteen module-level helpers with
two or more copies — but whether any two copies have **drifted**, because drift is what turns
duplication into a bug. It answered it by parsing every payload, stripping docstrings, normalising
through `ast.unparse` and comparing. **Sixteen of the nineteen are byte-identical.** Nothing has
drifted, so FR 013's
[one exception](../done/013-live-verification/README.md#what-this-effort-may-change) did not fire and
nothing was merged during that effort.

Two of the three that differ are worth a fragment anyway, and for the reason `rig_lookup.py`
exists: not size, but consequence. `rig_refit_blocker()` has four copies whose *condition* is
identical and whose message differs by tense between the tool that reports a refit that happened
and the three that predict one that has not; `modifier_value()` has two implementations of one
reading, agreeing today and confirmed live to agree. Both are one careless edit from the failure
`rig_lookup.py` was created to prevent — a character that looks broken in one tool and fine in
another.

The census itself is thirty lines and should be kept, because it turns "have these drifted?" from
an afternoon into a command.

## Goals

**Primary: remove the two duplications whose divergence would be silent**, by adding one shared
fragment, without merging the sixteen that are identical and harmless.

**Secondary: keep the census**, as a script beside the harness, so the next request can answer the
same question in seconds rather than by reading twenty files.

**Explicitly not a goal:** deduplicating for its own sake. `blocked()`'s six variants are one
convention applied six times and merging them would cost more than it saves — see
[the review](../done/013-live-verification/review.md#is-the-duplication-a-risk-or-an-economy).

## Functional requirements

- **FR-1.** A fragment under `codegen/shared/` holding the generated-Rigify-without-meta-rig
  condition, consumed by `refit_human.py`, `set_macro_details.py`, `set_targets.py` and
  `symmetrize_targets.py`. The *condition* is shared; the message is not, since one call site
  reports and three predict. The fragment should expose the condition and let each payload phrase
  it, rather than exposing a message with a tense argument.
- **FR-2.** The same fragment, or a second one, holding the category reading `modifier_value()`
  computes, consumed by `get_target_stack.py` and `symmetrize_targets.py`. Note the two current
  implementations differ in *shape* — one threads a pair of closures, one resolves the stored name
  directly — so this is a genuine reconciliation rather than a copy-paste removal.
- **FR-3.** A census script under `verification/`, printing every module-level function defined in
  more than one payload with its copies and whether they are identical after normalisation.
- **FR-4.** The affected checklists are re-run and their verification records updated. A refactor
  whose unit tests see no behaviour change still makes a live verification stale, because a
  different program is sent — the lesson FR 009 and FR 010 both paid for. This is now one command
  per checklist.

## Non-functional requirements

**No behaviour change.** Both reconciliations must produce the same answers the current copies
produce; where the two implementations differ in shape, the choice between them is a readability
decision, and whichever is chosen must be checked against the other's tests rather than replacing
them.

**The fragment must earn its place.** `codegen/shared/` has four files and a stated bar: a
concept two or more payloads model identically, where two implementations disagreeing would be a
bug rather than an inconsistency. Anything that does not clear that bar stays duplicated.
(The directory slug still says "fourth": the fourth was
[FR 014](../done/014-uniform-performed-flag/README.md)'s `performed.py`, which landed first. This one
would be the fifth, and the slug is kept because a request keeps its number and slug.)

## Architecture

See [Shared fragments](../../specifications/architecture.md#shared-fragments) for the mechanism: a
fragment is named in the `assemble(..., shared=[...])` call a tool module already makes, so adding
one touches no shared code-generation module. Note the packaging detail — a package-data glob does
not descend, so `shared/` is a sibling of `payloads/` with a glob of its own.

**Pitfall: `target_categories.py` is already large** (18 KB, 443 lines) and is assembled into three
programs. [FR 017](../017-category-table-cost/README.md) is about its *cost*; anything added here
should not make that worse, and the two efforts should agree on which one touches that file.

**Pitfall: the payload brace rule**, enforced by `tests/test_codegen.py`.

## Affected specifications

- **[specifications/architecture.md](../../specifications/architecture.md)** —
  [Shared fragments](../../specifications/architecture.md#shared-fragments) gains this fragment
  and, more usefully, the census result: that sixteen duplications are identical and that being
  identical is not by itself a reason to merge.

## Tests

Unit tests, with the existing per-payload tests kept and one added that runs both consumers of each
new fragment against the same fixture and asserts they agree — the shape of the test that already
pins `rig_lookup.py` (`test_add_rig.py` runs `list_rigs.py` and `add_rig.py` over one tree and
compares their weights answers).

The census script is an instrument, not a test, and is not discovered by the test runner.

**Live re-verification is required** for the four checklists whose programs change:
[FR 007](../done/007-macro-details/README.md), [FR 008](../done/008-detail-targets/README.md) and the
`mpfb_get_target_stack`/`mpfb_symmetrize_targets` halves. One command each.

## References

- [FR 013's review](../done/013-live-verification/review.md#is-the-duplication-a-risk-or-an-economy) —
  the census, its numbers, and the reasoning for what is and is not worth merging.
- [codegen/shared/rig_lookup.py](../../src/mpfbmcp/codegen/shared/rig_lookup.py) — the fragment whose
  justification this one follows.
