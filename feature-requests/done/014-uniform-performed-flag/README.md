# A uniform "it happened" flag across the mutating tools

**Status:** Done

Every mutating tool reports whether it did the thing, and each one names that field differently:
`added` (`mpfb_add_asset`, `mpfb_add_rig`), `applied` (`mpfb_set_skin`, `mpfb_set_asset_material`,
`mpfb_set_targets`), `removed` (`mpfb_remove_asset`), `generated` (`mpfb_generate_rigify_rig`),
`refit_performed` (`mpfb_refit_human`), `changed` (`mpfb_symmetrize_targets`). Each reads well in
its own response. The set does not: a caller writing against more than one tool has to look each
name up, and getting it wrong produces `None` rather than an error.

That is not a hypothetical.
[FR 013](../013-live-verification/README.md)'s harness — written by someone with the source open
— guessed wrong on three tools in one session, and each wrong guess silently made a passing check
into a failing one that looked like a tool defect. An LLM caller reading twenty tool descriptions
has strictly less context than that.

The refusal fields are uniform already: `found`, `ready` and `blocked_by` mean the same thing
everywhere and were never mis-read. It is only the success flag that varies, which suggests the
convention was never stated rather than deliberately relaxed.

## Goals

**Primary: one field name that means "the operation was performed", present on every mutating
tool.** (There are **eleven**, not the twelve this request originally counted: the nine named
above, plus `mpfb_create_human`, which has no verb at all, and `mpfb_set_macro_details`, whose verb
is `recalculated` and was missed when the list was written. Corrected here rather than left to be
rediscovered.) Additive — each tool keeps its own verb, because `added: true` beside `asset_object_name`
reads better than `performed: true` does and the docstrings are written around it.

**Secondary: state the convention** in
[A mutating tool reports before and after](../../../specifications/mutating-tools.md#a-mutating-tool-reports-before-and-after),
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
- **FR-4.** The eleven tool docstrings say `performed` is the field to branch on and the verb is
  the field to read.

## Non-functional requirements

**Additive, not corrective.** This is a response-shape change to eleven tools at once, which is the
kind of change that must not be able to break a caller. If any part of it requires removing or
renaming an existing field, that part is out of scope.

**One place, not twelve.** Eleven payloads each building one more dict key is eleven chances to get
the `dry_run` case wrong. Prefer a shared fragment or a helper each payload already has.

## Architecture

The natural home is the `blocked()` helper six payloads already carry (see
[FR 013's review](../013-live-verification/review.md#is-the-duplication-a-risk-or-an-economy)):
it is where every refusal is built, and it already sets the tool's own verb to false. The success
path has no equivalent single point, which is the actual work here.

**Pitfall: the flag is not always the verb.** `mpfb_symmetrize_targets` under `dry_run: true`
returns `changed: [...]` with entries in it and has written nothing, so `performed` must be false
while `changed` is non-empty. `mpfb_set_macro_details` with no sliders named returns successfully
having recalculated nothing. Both are the cases that make this a request rather than a rename.

**Pitfall: the payload brace rule.** A payload file may contain no empty brace pair anywhere;
`tests/test_codegen.py` enforces it.

## Affected specifications

- **[specifications/mutating-tools.md](../../../specifications/mutating-tools.md)** —
  the convention landed as a section of its own,
  [The flag a caller branches on is called `performed`](../../../specifications/mutating-tools.md#the-flag-a-caller-branches-on-is-called-performed),
  rather than as a bullet under *A mutating tool reports before and after* as planned: it needed the
  three cases where the flag is not the verb, which is more than that list would carry.
- **[specifications/responses.md](../../../specifications/responses.md)** —
  [Response shape](../../../specifications/responses.md#response-shape) gains a sentence pointing at
  it.
- **[specifications/vision.md](../../../specifications/vision.md)** — the catalog entries do not name
  these fields individually, so no change is expected. **Confirmed: unchanged.**
- **[specifications/architecture.md](../../../specifications/architecture.md)** — not foreseen when
  this was written, and required once the shape of the answer became a shared fragment:
  [Shared fragments](../../../specifications/architecture.md#shared-fragments) said "there are three"
  and now says four, with the bar `performed.py` clears stated as consequence rather than size.

## Tests

Unit tests can carry all of this: the flag is computed on this side of the socket from state the
stubs already produce. One test per mutating tool asserting `performed` matches that tool's verb,
plus the three cases where it must not: a dry run, a no-op call, and a refusal.

Live verification is **not** required — but [verification/](../../../verification/) should gain an
assertion that `performed` agrees with each tool's verb wherever a checklist already calls one,
which is nearly free and is what would catch a payload that sets it from the wrong variable.

## References

- [FR 013's review](../013-live-verification/review.md#does-the-response-shape-work-in-practice) —
  where this was measured, and the three tools the harness got wrong.

## Verification status

**Implemented and unit-tested (2026-09-08); no live verification of its own.** The flag is computed
on the near side of the socket from state the payload has already built, so the whole of it is
reachable by the existing two-layer suite: 701 tests, up from 685, with ten new per-tool checks that
`performed` matches that tool's verb, four that exercise `with_performed()` directly, and two in
`test_codegen.py` that pin *which* payloads stamp it — both halves, so a read-only tool growing a
meaningless `performed: false` fails as loudly as a mutating one losing it.

The three cases the request called out are each pinned by name:
`test_symmetrize_targets.py`'s dry run (`changed` populated, `performed: false`),
`test_set_macro_details.py`'s no-op call (`ready: true`, nothing recalculated), and every module's
refusal. `test_set_targets.py` adds a fourth the request did not anticipate: the all-or-nothing
resolution failure, which is `ready: true` with an empty `applied` and would be the first thing a
flag derived from `ready` alone got wrong. `test_refit_human.py` covers the generated-Rigify-rig-
with-no-meta-rig case, where FR-3's "set from, not beside" is what stops the two fields disagreeing.

**What the unit tests cannot establish**, per
[testing.md](../../../specifications/testing.md): that the verb a payload stamps the flag from is the
one the *live* MPFB sets. The stubs feed both the verb and the flag from the same run, so a payload
reading the wrong variable could still look self-consistent. That is what the harness change covers:
`verification/harness.py` now wraps every mutating tool callable in an audit that compares
`performed` against that tool's verb on **every call any checklist already makes**, and
`Report.summary()` reports the result as one more item on every checklist. No check script was
edited, which is what the request meant by "nearly free" — and it is stronger than an assertion at
each call site would have been, because it also covers the calls a checklist makes as setup rather
than as its subject.

## What landed

- **`codegen/shared/performed.py`**, a fourth shared fragment holding one function,
  `with_performed(result, done)`. It is the only fragment that binds nothing from the bootstrap and
  reads nothing out of MPFB, which is what lets it be concatenated ahead of any payload.
- **One line at the bottom of each of the eleven mutating payloads**, stamping the flag onto
  whichever answer the branches above it built — rather than a key added to each of the up-to-twelve
  dicts a payload constructs. The two universal falsehoods (`found: false` and `ready: false` are
  never performed) live in the fragment; the tool-specific expression lives at the call site,
  because for three tools the flag is genuinely not the verb.
- **Eleven `shared=[...]` arguments**, in the tool modules, added to the `assemble()` call each was
  already making. No shared code-generation module was edited, per
  [architecture.md](../../../specifications/architecture.md#shared-fragments).

**What it costs on the wire**, measured rather than assumed, since
[FR 017](../../017-category-table-cost/README.md) is about exactly this kind of cost: the fragment
is **2.9 KB**, most of it docstring, and it is now concatenated into eleven programs. Against the
payloads it joins — 31.7 KB for `set_targets.py`, 33.5 KB for `add_asset.py`, 20.8 KB for
`symmetrize_targets.py` — that is under 10%. The one where it is not is `create_human.py`, a 1.6 KB
payload whose program roughly doubles. It was kept anyway: the alternative is a twelfth spelling of
the flag in the one tool a caller is most likely to reach for first, and
[FR 013](../013-live-verification/README.md) measured a round trip at ~250 ms against a per-call
setup cost that dwarfs transport. The repo's standing choice to
[keep comments and docstrings in generated code](../../../specifications/architecture.md#readability-and-developer-experience-are-prioritized)
is what makes the fragment mostly prose, and that choice is unchanged here.
- **A paragraph in each of the eleven tool docstrings** saying to branch on `performed` and read the
  verb. This grows the description budget [FR 016](../016-trim-tool-descriptions/README.md) wants to
  shrink, by roughly 1.5 KB across the eleven — which is the trade that request already names: it
  wants rationale out and *field names* in.
