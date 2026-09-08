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
| [vision.md](vision.md) | Why this project exists, its goals, and the target tool catalog. |
| [architecture.md](architecture.md) | Standing architectural principles: the piggyback transport, code-generation approach, and conventions new tools should follow. |
| [testing.md](testing.md) | How this system is tested: the two-layer unit suite, the stub-fidelity rule, and what only a running Blender can establish. |
