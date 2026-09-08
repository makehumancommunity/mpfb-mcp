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

## Index

| Document | Purpose |
|----------|---------|
| [vision.md](vision.md) | Why this project exists, the piggyback approach, what makes something a tool, and the capability areas the surface is meant to cover. |
| [architecture.md](architecture.md) | The machine: the piggyback transport and its boundaries, supporting a second backend, resolving MPFB from generated code, the code-generation layout, and the module structure. |
| [tool-interface.md](tool-interface.md) | What a tool accepts: validating before the socket, addressing an object, and the contract between a catalogue and the tool that acts on its identifiers. |
| [responses.md](responses.md) | What a tool says back: the envelope, `null` versus `[]`, bounding a large answer, and reporting a derived or unrecorded fact. |
| [mutating-tools.md](mutating-tools.md) | The extra obligations of a tool that changes a character: its subject, its preconditions, before-and-after reporting, ordering, and batching. |
| [mpfb-integration.md](mpfb-integration.md) | Coping with MPFB: UI coercions, disagreeing code paths, reading its data files, and modelling a concept its services lack. |
| [observability.md](observability.md) | Where diagnostics attach, and what they may and may not do. |
| [testing.md](testing.md) | How this system is tested: the two-layer unit suite, the stub-fidelity rule, the live harness, and what only a running Blender can establish. |
