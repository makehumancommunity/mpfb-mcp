# Specifications

This directory holds the structured specifications for mpfb-mcp.

## Status of these documents

**These specifications are visionary.** They describe the **desired end state** of the
system — the design we are building *toward* — not necessarily how it is implemented today.
The codebase is in early beta and will, in places, diverge from what is written here: a spec
may describe tools, behavior, or conventions that do not exist yet.

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

**One machine, and there is no longer a transition to be on one side of.** mpfb-mcp's
Blender-side logic lives in a companion add-on of our own, the **MPFB Bridge**, with a closed
command vocabulary; a tool names a command and hands over its parameters.

It was two machines between
[FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md), which decided that, and
[FR 033](../feature-requests/done/033-retire-the-generated-code-path/README.md), which deleted the
older one — Python assembled here and sent to a third party's add-on to be executed. These
documents describe what runs. **What that path was, what it cost and what it taught belongs to
[HISTORY.md](../feature-requests/HISTORY.md)**, which is where a finding outlives the code it was
measured on; a standing specification that kept describing a deleted machine would be the
[FR 020](../feature-requests/done/020-trim-claude-md/README.md) failure mode with extra steps.

## Index

| Document | Purpose |
|----------|---------|
| [vision.md](vision.md) | Why this project exists, the bridge add-on and why it rather than a third party's, what runs today, what makes something a tool, and the capability areas the surface is meant to cover. |
| [architecture.md](architecture.md) | The machine: the bridge and its wire, the two-ended validation, the network boundary, the seam, resolving MPFB, and what warrants a shared module. |
| [tool-interface.md](tool-interface.md) | What a tool accepts: the description budget, validating before the socket, addressing an object, and the contract between a catalogue and the tool that acts on its identifiers. |
| [responses.md](responses.md) | What a tool says back: the envelope, `null` versus `[]`, bounding a large answer, saying which source answered it, and reporting a derived, curated or unrecorded fact. |
| [mutating-tools.md](mutating-tools.md) | The extra obligations of a tool that changes a character: its subject, its preconditions, before-and-after reporting, ordering, and batching. |
| [mpfb-integration.md](mpfb-integration.md) | Coping with MPFB: UI coercions, disagreeing code paths, reading its data files, what its caches cost and hide, and modelling a concept its services lack. |
| [observability.md](observability.md) | Where diagnostics attach, and what they may and may not do. |
| [testing.md](testing.md) | How this system is tested: the one-layer unit suite, the fixture-fidelity rule, the second harness that runs inside Blender, the live harness, tests that lean on a sibling checkout, and what only a running Blender can establish. |
