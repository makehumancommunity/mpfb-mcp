# A uniform "it happened" flag across the twelve mutating tools

**Status:** Proposed

Every mutating tool reports whether it did the thing, and each one names that field differently:
`added` (`mpfb_add_asset`, `mpfb_add_rig`), `applied` (`mpfb_set_skin`, `mpfb_set_asset_material`,
`mpfb_set_targets`), `removed` (`mpfb_remove_asset`), `generated` (`mpfb_generate_rigify_rig`),
`refit_performed` (`mpfb_refit_human`), `changed` (`mpfb_symmetrize_targets`). Each reads well in
its own response. The set does not: a caller writing against more than one tool has to look each
name up, and getting it wrong produces `None` rather than an error.

That is not a hypothetical.
[FR 013](../done/013-live-verification/README.md)'s harness — written by someone with the source open
— guessed wrong on three tools in one session, and each wrong guess silently made a passing check
into a failing one that looked like a tool defect. An LLM caller reading twenty tool descriptions
has strictly less context than that.

The refusal fields are uniform already: `found`, `ready` and `blocked_by` mean the same thing
everywhere and were never mis-read. It is only the success flag that varies, which suggests the
convention was never stated rather than deliberately relaxed.

## Goals

**Primary: one field name that means "the operation was performed", present on every mutating
tool.** Additive — each tool keeps its own verb, because `added: true` beside `asset_object_name`
reads better than `performed: true` does and the docstrings are written around it.

**Secondary: state the convention** in
[A mutating tool reports before and after](../../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after),
so the thirteenth mutating tool does not invent a seventh name.

## Functional requirements

- **FR-1.** Every tool that changes anything reports `performed`, a real boolean, true exactly when
  the operation completed. It is false in every refusal (`ready: false`), false when the subject
  could not be resolved (`found: false`), and false when the tool completed without doing anything
  it was asked to do — `mpfb_symmetrize_targets` with `dry_run: true`, and
  `mpfb_set_macro_details` called with no sliders named.
- **FR-2.** The existing verb fields are unchanged. Nothing is renamed and nothing is removed; a
  caller written against `added` keeps working.
- **FR-3.** `mpfb_refit_human`'s `refit_performed` is the one existing field that already means
  this. It stays, and `performed` is set from it rather than beside it, so the two cannot disagree.
- **FR-4.** The twelve tool docstrings say `performed` is the field to branch on and the verb is
  the field to read.

## Non-functional requirements

**Additive, not corrective.** This is a response-shape change to twelve tools at once, which is the
kind of change that must not be able to break a caller. If any part of it requires removing or
renaming an existing field, that part is out of scope.

**One place, not twelve.** Twelve payloads each building one more dict key is twelve chances to get
the `dry_run` case wrong. Prefer a shared fragment or a helper each payload already has.

## Architecture

The natural home is the `blocked()` helper six payloads already carry (see
[FR 013's review](../done/013-live-verification/review.md#is-the-duplication-a-risk-or-an-economy)):
it is where every refusal is built, and it already sets the tool's own verb to false. The success
path has no equivalent single point, which is the actual work here.

**Pitfall: the flag is not always the verb.** `mpfb_symmetrize_targets` under `dry_run: true`
returns `changed: [...]` with entries in it and has written nothing, so `performed` must be false
while `changed` is non-empty. `mpfb_set_macro_details` with no sliders named returns successfully
having recalculated nothing. Both are the cases that make this a request rather than a rename.

**Pitfall: the payload brace rule.** A payload file may contain no empty brace pair anywhere;
`tests/test_codegen.py` enforces it.

## Affected specifications

- **[specifications/mutating-tools.md](../../specifications/mutating-tools.md)** —
  [A mutating tool reports before and after](../../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after)
  gains the convention.
- **[specifications/responses.md](../../specifications/responses.md)** —
  [Response shape](../../specifications/responses.md#response-shape) gains a sentence pointing at
  it.
- **[specifications/vision.md](../../specifications/vision.md)** — the catalog entries do not name
  these fields individually, so no change is expected.

## Tests

Unit tests can carry all of this: the flag is computed on this side of the socket from state the
stubs already produce. One test per mutating tool asserting `performed` matches that tool's verb,
plus the three cases where it must not: a dry run, a no-op call, and a refusal.

Live verification is **not** required — but [verification/](../../verification/) should gain an
assertion that `performed` agrees with each tool's verb wherever a checklist already calls one,
which is nearly free and is what would catch a payload that sets it from the wrong variable.

## References

- [FR 013's review](../done/013-live-verification/review.md#does-the-response-shape-work-in-practice) —
  where this was measured, and the three tools the harness got wrong.
