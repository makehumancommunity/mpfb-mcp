# Trim the root CLAUDE.md, and stop it regrowing

**Status:** Done

The root [CLAUDE.md](../../../CLAUDE.md) is 704 lines. It has grown once per landed feature request
and has never shrunk: 92 lines at the proof of concept, 214 after FR 003, 316 after FR 007, 451
after FR 009, 586 after FR 011, 669 after FR 012, 704 after FR 013 — about +65 lines per request
since FR 007. Six requests are already open, so on the current trajectory it passes 1000 lines
around FR 018.

Size alone would not be worth a request. What makes it one is that the file is now **mostly a
second copy of documentation that exists elsewhere, and the two copies have begun to disagree**.
[architecture.md](../../../specifications/architecture.md)'s own preamble says its job is the
standing principles and CLAUDE.md's is "the current, concrete module layout" — but CLAUDE.md's
Architecture section is 269 lines of principle and per-tool rationale, which is the other
document's job done second and worse. Meanwhile every tool module carries a 100-350 word "why"
docstring, every payload 90-620 words, `tests/blender_stubs.py` a 776-word one enumerating more
reproduced MPFB quirks than CLAUDE.md's Tests section does, and
[HISTORY.md](../../HISTORY.md) a per-effort narrative that is a superset of CLAUDE.md's "Project
status". One paragraph of CLAUDE.md's verification section is word-for-word identical to
`architecture.md`'s.

Five factual errors have already resulted, each surviving because two documents said the same
thing and only one was updated. They are listed under [the five divergences](#the-five-divergences) below.

## The five divergences

1. **The shared-fragment count is stale.** CLAUDE.md says "There is exactly one so far", then
   describes two. Three exist on disk — `target_categories.py`, `rig_lookup.py`,
   `asset_sections.py` — and `architecture.md` correctly says three and carries a bullet on
   `asset_sections.py` that CLAUDE.md's `shared/` bullet lacks entirely.
2. **A three-way contradiction about local vocabulary validation.** CLAUDE.md says
   `generate_rigify_rig.py` "is the only tool here that validates a **vocabulary** locally", and
   then eighty lines later says `set_skin.py` is "the **only tool here that validates a
   vocabulary locally**". `architecture.md` says "`mpfb_set_skin`'s `skin_type` is the only
   current case". The code settles it: `tools/generate_rigify_rig.py` validates
   `_META_RIG_ACTIONS` and `tools/set_skin.py` validates `SKIN_TYPES`, both before the socket.
   **There are two, and the standing specification is wrong as well.**
3. **The root [README.md](../../../README.md) still says twelve tools are unverified.** FR 013 made
   that false and CLAUDE.md contradicts it directly, in the same repository, two files apart.
4. **A retired measurement lived on in one of the two copies.** FR 013 measured the socket round
   trip at 250 ms and FR 017 recorded it, but `architecture.md`'s batching argument still read
   "about a second" — the figure FR 013 explicitly retired. Corrected here, with FR 013's actual
   numbers, since the argument is stronger with them than it was with the guess.
5. **The standing test discipline has no home in `specifications/`.** The rule that stubs
   reproduce MPFB's real behaviour rather than convenient values — the rule FR 013 vindicated
   when a stub basemesh with no modifiers turned out to have hidden a real defect through two
   rounds of review — exists only in CLAUDE.md's prose. `architecture.md` carries one bullet
   about a stub and nothing else.

## Goals

**Primary:** reduce CLAUDE.md to a map — the concrete layout `architecture.md` delegates to it,
plus the facts that have no other home — at roughly 250 lines, without losing a single fact that
exists nowhere else.

**Secondary:** give the standing test discipline a home in `specifications/`; fix the five
divergences rather than carrying them forward; and change the feature-request lifecycle so the
file stops regrowing, since a trim that is undone by FR 021-025 is not worth doing.

## Functional requirements

- CLAUDE.md is between 230 and 270 lines and keeps its `## Commands` and `## Architecture`
  headings, which are inbound anchor targets from `verification/README.md` and
  `specifications/architecture.md`.
- CLAUDE.md still names, in one line each, all twenty tools and every test module, so it reads
  as a self-contained map rather than a directory listing.
- Every fact that currently exists **only** in CLAUDE.md survives, in CLAUDE.md or in a
  specification. The known list is in [Architecture](#architecture) below.
- A new `specifications/testing.md` holds the standing test discipline, and
  `specifications/README.md`'s index names it.
- `specifications/architecture.md`'s vocabulary-validation exception names both current cases.
- The root README.md no longer claims twelve tools are unverified.
- [feature-requests/CLAUDE.md](../../CLAUDE.md)'s lifecycle says where a finished effort's prose
  goes, and that CLAUDE.md is not it.
- No intra-repository markdown link or anchor is left dangling.

## Non-functional requirements

**Accuracy over completeness.** The point of the change is that a second copy drifts. Where
this effort removes prose, it must remove it in favour of a pointer to the copy that is
maintained, never leave a summary that will drift again.

**No fourth copy.** The live-verification harness is already described in three places
(CLAUDE.md, `verification/README.md`, `architecture.md`). `testing.md` links to those; it does
not restate them.

**A new tool must be one row.** After this, landing a tool adds a row to CLAUDE.md's tool table
and a row to its test table — not a paragraph. If a future effort finds itself writing a
paragraph here, the paragraph belongs in its own module docstring or in HISTORY.md.

## Architecture

Six files change and two are new.

**`specifications/testing.md`** (new, ~120 lines) takes: the two-layer suite (tool wrapper with
`send_code` mocked, then assembled source `exec()`'d against stubs; stdlib `unittest`, no
pytest); the rule that stubs reproduce MPFB's real behaviour rather than convenient values, with
the FR 013 `Hide helpers` evidence that earns it; what the suite can *never* prove, stated once
rather than per module; the two mechanics every stub-executing test module inherits (a stub
service module's name must not end in `"mpfb"`, and `__module__` is reassigned by hand), which
today are only code comments in `tests/blender_stubs.py`; and when to build a real `tempfile`
tree rather than reproduce a service.

**`specifications/architecture.md`** gets one correction, in "Validate before crossing the
socket": the vocabulary exception has two cases, not one. `mpfb_set_skin`'s `skin_type` because
`set_character_skin()` deletes every material before testing it, and
`mpfb_generate_rigify_rig`'s `meta_rig_action` because `generate_rigify_rig()` silently falls
back to `"hide"`, on the one argument whose wrong value cannot be undone.

**`CLAUDE.md`** keeps Documentation, Version control, Commands, Code conventions and Sibling
projects nearly as they are — those are the sections with no second copy. Project status drops
to about twelve lines pointing at README.md, HISTORY.md and vision.md. Architecture becomes the
pipeline diagram, a module-layout table, a twenty-row tool table, and a short block of what is
validated on this side of the socket. Tests becomes a two-layer sentence and a test-module
table. Backends becomes a pointer.

The residue — the facts that exist in no other file and that the trim would otherwise lose — is:
the strict-`bool` rule for `refresh`/`prune`/`refit` and the not-`bool` rule for
`limit`/`offset`; that `set_macro_details`' 0.0-1.0 is enforced locally or nowhere, because
MPFB's macro properties carry a default but no `min`/`max`; `set_targets`' two ranges
(-1.0..+1.0 for a modifier, 0.0..1.0 for a target) and that which one applies is only knowable
inside Blender; that `symmetrize_targets`' `direction` is the package's only required argument;
the `:9876` port and the pipeline diagram; the three bootstrap identifier names; the full
`assemble()` signature; that `connection.py` must be updated by hand if blender_mcp's protocol
changes; that the observability record writes the program **before** the socket call, so a hang
or a crash still leaves it; the code-conventions block; and the `docs/services/humanservice.md`
pointer into `../mpfb2`.

**`feature-requests/CLAUDE.md`** gains a lifecycle step: durable decisions go to
`specifications/`, the effort's story goes to HISTORY.md, a tool's rationale goes in its own
module docstring, and CLAUDE.md is edited only when the layout, the commands or the conventions
actually change. Step 1 also gains a sentence about checking the claim being replaced, since
this effort found five errors that survived exactly because nobody did.

**`README.md`** and **`specifications/README.md`** get one edit each.

## Affected specifications

- [specifications/testing.md](../../../specifications/testing.md) — **new.** The standing test and
  stub discipline, which currently has no home under `specifications/`.
- [specifications/architecture.md](../../../specifications/architecture.md) — the
  "Validate before crossing the socket" vocabulary exception is corrected from one case to two.
- [specifications/README.md](../../../specifications/README.md) — an index row for `testing.md`.

## Tests

**No unit tests change, and none are added.** This effort touches only Markdown; the suite is
run once to confirm nothing under `src/` or `tests/` was edited by accident.

**No live verification is required**, and this is a genuine exception rather than the deferral
[feature-requests/CLAUDE.md](../../CLAUDE.md) warns about: nothing here reaches Blender, changes a
generated program, or alters a tool's behaviour. There is nothing a running MPFB could observe.

The checks that do apply are documentation-integrity ones, and they are run from the repo root:
every `CLAUDE.md#anchor` referenced from another file still resolves; no intra-repository link
is left dangling; each fact in the residue list above appears in the new CLAUDE.md or in
`testing.md`; and the five divergences are gone.

## References

- Growth measured with `git log --format=%h --reverse -- CLAUDE.md`, then
  `git show <commit>:CLAUDE.md | wc -l` per commit.
- [FR 013](../013-live-verification/README.md) — the source of the `Hide helpers` evidence
  for the stub-fidelity rule that moves into `testing.md`.
- [FR 016](../../016-trim-tool-descriptions/README.md) — the same problem one level down: prose
  that grew past the point where a reader benefits from it.
