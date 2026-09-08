# Split architecture.md into per-topic specifications

**Status:** Done

[specifications/architecture.md](../../../specifications/architecture.md) had grown to 870 lines
across 24 top-level sections. Six of them describe the system's structure. The other eighteen are
standing conventions about how a tool takes its input, what it must say back, how it behaves when
it changes a character, and how it copes with MPFB being inconsistent — real decisions, worth
having, but not architecture, and hard to find inside a document whose title says otherwise.

Two things made that concrete rather than a matter of taste.

**The document already delegated twice.** Its preamble sent readers to
[CLAUDE.md](../../../CLAUDE.md#architecture) for the module layout. And 24 of the 37 lines of its "No
direct dependency" section described the unit suite and the live harness — which became
[testing.md](../../../specifications/testing.md)'s subject in
[FR 020](../020-trim-claude-md/README.md), and which testing.md explicitly declined to restate
*because* this copy existed. A document that has to say what it is not about, twice, has more than
one subject.

**Everything cites it, and the citations were already section-level.** Measured before the split:
**195 anchored inbound links across 27 files**, three of them Python modules under `src/`, against
only 41 anchorless ones. Nobody was linking to "the architecture" — they were linking to
`#preconditions-are-answers` and `#how-tools-bound-a-large-answer`. The document was being used as
five documents and could not say so.

## Goals

**Primary:** `architecture.md` describes only the machine — boundaries, resolving MPFB from
generated code, the code-generation layout, module structure — at roughly 200 lines. Every other
standing convention lives in a document named for its subject.

**Secondary:** make "Affected specifications" in a feature request a meaningful line. Under one
850-line document every effort named the same file; under six, naming `responses.md` says
something. And close the duplication FR 020 left behind, by moving the harness prose to the
document that now owns it.

## Functional requirements

- `architecture.md` retains only the five structural sections and is under 230 lines.
- Five new documents hold the other nineteen sections: `tool-interface.md`, `responses.md`,
  `mutating-tools.md`, `mpfb-integration.md`, `observability.md`.
- **Section text moves verbatim.** This effort re-files; it does not rewrite. The only prose
  written fresh is each document's preamble and the one shortened section.
- Every anchor that anything ever linked to still resolves, in exactly one document.
- No dangling link anywhere in the repository, `.py` docstrings included.
- [specifications/README.md](../../../specifications/README.md)'s index names all seven documents,
  and [CLAUDE.md](../../../CLAUDE.md)'s router table sends a reader to the right one.
- Open feature requests whose "Affected specifications" named a moved section are retargeted.

## Non-functional requirements

**Findability over brevity.** Total prose grows by about 90 lines — six preambles, and pointers
where a section used to sit. That is the cost of the change, not a failure of it.

**Each document says what it is *not* about.** Every preamble carries a pointer to its siblings.
Without that, the next effort puts a response convention back into `architecture.md`, which is
exactly how the situation arose.

**The link rewrite is mechanical.** 195 links is past the point where doing it by eye is
honest work. One mapping table drives both the split and the rewrite, so a section cannot move
without its inbound links moving with it.

## Architecture

The split is by *subject*, and the axis is "is this about the machine, or about how a tool
behaves?":

| Document | Sections | Subject |
|---|---|---|
| `architecture.md` | 5 | Boundaries, the MPFB bootstrap, code generation, module layout |
| `tool-interface.md` | 4 | What a tool accepts; addressing an object; catalogue identifiers and the acting tool's duty to accept them all |
| `responses.md` | 5 | The envelope, `null` vs `[]`, bounding a large answer, derived and unrecorded facts |
| `mutating-tools.md` | 5 | Subject resolution, preconditions, before/after, ordering, batching |
| `mpfb-integration.md` | 4 | UI coercions, disagreeing code paths, reading data files, modelling a UI-only concept |
| `observability.md` | 1 | Where diagnostics attach and what they may not do |

`observability.md` is its own document rather than a section of `architecture.md` because
[FR 012](../012-observability/README.md) was a whole effort about exactly it and
`observability.py` is its own module; the attachment point is architectural, but the seven rules
that follow from it are policy.

Two pitfalls, both hit during implementation and both worth recording:

- **The 21 intra-document `](#anchor)` references.** When a section moves, a relative anchor
  inside it either stays relative or must gain a filename, depending on where its *target* went.
  These do not look like file links and a rewrite that only handles `architecture.md#…` misses
  every one.
- **Do not exempt `specifications/` from the rewrite.** The freshly split files have correct
  links already, but `vision.md` (21 links) and `testing.md` (2) sit in the same directory and
  do not.

## Affected specifications

- [specifications/architecture.md](../../../specifications/architecture.md) — reduced to the five
  structural sections; gains a table naming its siblings.
- [specifications/tool-interface.md](../../../specifications/tool-interface.md) — **new.**
- [specifications/responses.md](../../../specifications/responses.md) — **new.**
- [specifications/mutating-tools.md](../../../specifications/mutating-tools.md) — **new.**
- [specifications/mpfb-integration.md](../../../specifications/mpfb-integration.md) — **new.**
- [specifications/observability.md](../../../specifications/observability.md) — **new.**
- [specifications/testing.md](../../../specifications/testing.md) — absorbs the live-harness prose
  from `architecture.md`'s "No direct dependency" section.
- [specifications/README.md](../../../specifications/README.md) — the index gains five rows.
- [specifications/vision.md](../../../specifications/vision.md) — 21 retargeted links; no prose change.

## Tests

**No unit tests change.** Three tool modules are edited, for links inside their docstrings, so
running the suite is not vacuous — but nothing executable changes.

**No live verification is required.** Nothing here reaches Blender, alters a generated program, or
changes a tool's behaviour.

The checks are documentation-integrity ones, and two of them are worth keeping as scripts rather
than as a memory of having looked:

- **Every anchor that was ever cited resolves in exactly one document.** Take the 29 headings from
  the pre-split `architecture.md` and assert each is a heading in exactly one of the seven files.
  This is what catches a heading silently reworded during the move.
- **Nothing was lost.** Parse the pre-split file and the seven post-split files into sections and
  compare bodies with link targets normalized away. Only the deliberately shortened section may
  differ.

Note what the FR 020 link checker missed and this one must not: it scanned `.md` only, so four
markdown links inside `src/mpfbmcp/tools/*.py` docstrings had been pointing at
`../../specifications/` — one level too shallow — since FR 011, and nothing noticed. The checker
now covers `.py` files, both their markdown links and their repo-root-relative prose mentions.

## References

- Inbound-link census: `grep -rno "architecture\.md#[a-z0-9_-]*" --include=*.md --include=*.py .`
- [FR 020](../020-trim-claude-md/README.md) — the same problem one level up, and the source of
  both the duplication closed here and the link checker extended here.
