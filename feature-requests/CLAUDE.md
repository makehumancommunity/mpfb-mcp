# CLAUDE.md

This directory contains feature requests.

## What This Is

A feature request is a specification for a planned development effort. It is most relevant
while planning and implementing the feature; once the work lands it is marked finished and
kept as a record of what was planned and decided (see [Lifecycle](#lifecycle)).

Feature requests are deliberately distinct from the standing
[specifications/](../specifications/), which describe the *long term vision*. A feature
request describes a *change*, conceptually bringing the system closer to the intended state.
See [Lifecycle](#lifecycle) for how the two relate over time.

When creating a new feature request, the [specifications](../specifications/) directory
should be consulted so that the request ends up following common guidelines and does not
work against the overall goal.

## Format

Each feature request lives in a subdir whose name starts with a zero-padded sequence
number followed by a short descriptive slug. The number gives a stable identifier (so a
request can be referenced from commits and PRs) and a natural chronological ordering.
The request itself lives in a file `README.md` in that subdir.

As a hypothetical example, a feature request for adding a doc-search tool could live in a
directory

    <repo root>/feature-requests/002-search-docs-tool/README.md

Pick the next unused number when creating a request. Related files, such as images and
analysis documents, live beside the README in the subdir.

Active requests (`Proposed`, `Accepted`, `In progress`) live directly under
`feature-requests/`. When a request is finished its subdir is moved — keeping its number and
slug — into `feature-requests/done/`, so the top level stays a short list of what is still in
flight (see [Lifecycle](#lifecycle)). `Rejected` requests are kept at the top level, since a
rejection is a visible decision about active scope rather than completed work.

A copy-paste skeleton is available in [TEMPLATE.md](TEMPLATE.md).

### Sections inside the README.md file

The README.md file should start with a title which briefly states what the feature is
about.

Immediately under the title there should be a single status line of the form:

    **Status:** Proposed

The status is one of: `Proposed`, `Accepted`, `In progress`, `Done`, `Rejected`.

**A `Done` whose live verification is still outstanding must say so on the status line**, not
only in a section further down. The form is:

    **Status:** Done (live verification outstanding)

This exists because five consecutive efforts reached plain `Done` with every character-modifying
tool unverified against a running Blender; the fact was recorded honestly each time, in a
`## Verification status` section nobody reading the status line would see, and the debt compounded
until it was one large session rather than five small ones (see
[FR 013](done/013-live-verification/README.md)). The cost of that session is now much lower — the
checks are scripts under [verification/](../verification/) and re-running one is a command — so
the qualifier should be rare. When it is used, the request must name what is outstanding and why,
and the effort that clears it rewrites the section rather than adding a second one.

Then there should be up to 20 lines of text (a soft guideline) describing the background,
for example why the feature or change is desirable or what problem it intends to solve.

Then there should be the following sections, each under a level 2 heading (for example
"## Goals"):

- "Goals": Short description of primary and secondary goals.
- "Functional requirements": What needs to be objectively fulfilled for this feature to
  be complete. This describes functionality, not code details.
- "Non-functional requirements": Which quality attributes are important and why? For
  example "usability", "robustness".
- "Architecture": Architectural pointers, such as where in the code things should be
  implemented, technical details which needs to be taken into account, and warnings
  about potential pitfalls.
- "Affected specifications": A list of links to the documents under
  [specifications/](../specifications/) that this effort extends or modifies. This makes
  it clear up front which standing specs will need to be updated when the work lands (see
  [Lifecycle](#lifecycle)). If the effort genuinely touches no existing spec, say so
  explicitly.
- "Tests" (optional, when relevant): Pointers about how and where unit tests should be
  added. Note that mpfb-mcp's unit tests cannot exercise real MPFB behavior (see
  [architecture.md](../specifications/architecture.md)) — if the effort needs verification
  against a real Blender/MPFB instance, say so explicitly here rather than leaving it to be
  discovered during implementation. Where it does, the live check belongs in
  [verification/](../verification/) as a script rather than in this file as a list of things
  somebody should do by hand: a checklist that can be re-run after a fix is the difference
  between a verification and a memory of one.
- "References" (optional, when relevant): Web links, references to earlier commits,
  references to other local code repos or similar things.

## Lifecycle

A feature request moves through its status values as work proceeds. When the effort is
**complete**:

1. Fold the durable parts of the request — new or changed functional requirements,
   architectural decisions, vocabulary, etc. — into the relevant documents under
   [specifications/](../specifications/). A decision folded in should say what it rests on:
   FR 013 found two standing decisions justified by readings of MPFB's source that the running
   install did not support, and a decision whose stated reason is wrong is harder to revisit
   than one that never gave a reason.
2. Set the request's status line to `**Status:** Done` and **move the subdir into
   `feature-requests/done/`** (keeping its number and slug). The subdir is **kept**, not
   deleted: it stays as a record of what was planned and decided. Because `done/` is one
   directory level deeper, re-point the moved README's relative links so they still resolve —
   add one `../` to links that leave the subdir (specs, top-level files, still-active sibling
   requests); links to other requests that also live under `done/` need no change. The
   standing [specifications/](../specifications/) remain the source of truth for current
   behavior; a finished feature request is a historical artifact, not a description of the
   system as it is now.
3. If the effort is listed in [NEXT_STEPS.md](NEXT_STEPS.md), **move it out of
   NEXT_STEPS.md and into [HISTORY.md](HISTORY.md)**. NEXT_STEPS.md tracks only the
   remaining/active efforts; HISTORY.md is the running log of completed ones. Add an entry to
   HISTORY.md describing what actually landed (ordered by feature-request number), remove the
   effort from NEXT_STEPS.md, and keep the two files cross-linked. If only part of a broader
   effort finished, record the finished feature request in HISTORY.md and leave the remaining
   work in NEXT_STEPS.md, cross-linking between them.
4. Read through the feature requests which are in status "Proposed" or "Accepted". Check if
   anything needs to be adjusted in the text of these feature requests in consequence of
   the implemented change.

A finished request stays in place but is no longer active work. Treat the
`feature-requests/` directory as the project's running log of efforts rather than a queue
that empties — a `Done` (or `Rejected`) entry is simply an inactive one.

Rejected requests are likewise kept and marked `**Status:** Rejected` so the decision
stays visible, without any fold-back into the specifications.
