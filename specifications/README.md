# Specifications

This directory holds the structured specifications for mpfb-mcp.

## Status of these documents

**These specifications are visionary.** They describe the **desired end state** of the
system — the design we are building *toward* — not necessarily how it is implemented today.
The codebase is a small, early-stage proof of concept and will, in places, diverge from what
is written here: a spec may describe tools, behavior, or conventions that do not exist yet.

When the two disagree:

- For **what the system should become**, the specifications express the intent.
- For **how the system currently behaves**, the code is the reference (see the repo
  [CLAUDE.md](../CLAUDE.md), particularly its Architecture section).

Read these documents as a target to implement and to keep updated as the system catches up —
not as documentation of the running server.

## How these documents work

- **Format:** structured prose, with tables where useful (e.g. a tool catalog).
- Where a document describes something not yet built, say so explicitly (e.g. "not yet
  implemented") rather than leaving it ambiguous whether it's current or planned.

## Which machine these documents describe

**A second answer is needed here since [FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md).**
"Visionary" above meant "the design we are building toward"; it now also means a *specific,
named* transition, and a reader must not be left guessing which side of it a given paragraph is
on.

mpfb-mcp's Blender-side logic is moving out of generated Python sent over a third party's add-on
socket and into a companion add-on of our own, the **MPFB Bridge**, with a closed command
vocabulary. `vision.md` and `architecture.md` were rewritten to describe the bridge; the
generated-code path is **what twenty-four of the twenty-five tools use today**, and what all
twenty-five use unless the backend is configured otherwise, and it is documented — not merely
mentioned — under
[The generated-code path](architecture.md#the-generated-code-path-what-runs-today-and-is-being-retired),
where it is plainly marked as being retired. The other six documents are largely indifferent to
which transport is underneath, and say so where they are not.

Neither half is aspirational prose about a machine nobody has built: the bridge exists, answers
one migrated tool's calls and has been compared field by field against the path it replaces, and
the generated-code path runs the other twenty-four. What is *planned* is the migration
between them, and that lives in
[NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md#a-larger-pivot-an-mpfb-specific-bridge-add-on)
rather than here.

## Index

| Document | Purpose |
|----------|---------|
| [vision.md](vision.md) | Why this project exists, the bridge add-on and why it rather than a third party's, what runs today, what makes something a tool, and the capability areas the surface is meant to cover. |
| [architecture.md](architecture.md) | The machine: the bridge and its wire, the two-ended validation, the network boundary, the backend seam, resolving MPFB, and — plainly marked — the generated-code path that runs today and is being retired. |
| [tool-interface.md](tool-interface.md) | What a tool accepts: the description budget, validating before the socket, addressing an object, and the contract between a catalogue and the tool that acts on its identifiers. |
| [responses.md](responses.md) | What a tool says back: the envelope, `null` versus `[]`, bounding a large answer, saying which source answered it, and reporting a derived, curated or unrecorded fact. |
| [mutating-tools.md](mutating-tools.md) | The extra obligations of a tool that changes a character: its subject, its preconditions, before-and-after reporting, ordering, and batching. |
| [mpfb-integration.md](mpfb-integration.md) | Coping with MPFB: UI coercions, disagreeing code paths, reading its data files, what its caches cost and hide, and modelling a concept its services lack. |
| [observability.md](observability.md) | Where diagnostics attach, and what they may and may not do. |
| [testing.md](testing.md) | How this system is tested: the two-layer unit suite, the stub-fidelity rule, the second harness that runs inside Blender, the live harness, tests that lean on a sibling checkout, and what only a running Blender can establish. |
