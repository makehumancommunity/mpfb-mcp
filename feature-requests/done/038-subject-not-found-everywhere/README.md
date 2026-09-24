# An unresolved subject is `subject_not_found` in every mutating tool

**Status:** Done

Found by [FR 037](../037-one-word-per-concept/README.md)'s census and queued in NEXT_STEPS.md. When
the subject cannot be resolved, nine mutating tools answered `found: false`, `ready: false` and
`blocked_by: "subject_not_found"`. Five of them answered `found: false` and `ready: false` with no
`blocked_by` key at all: `mpfb_refit_human`, `mpfb_set_macro_details`, `mpfb_set_targets`,
`mpfb_symmetrize_targets` and `mpfb_set_face_units`.

The server instructions tell a caller to read `found`, `ready` and `blocked_by` before concluding a
call went wrong, and a caller that branches on `blocked_by` alone read those five answers as
`None`. FR 037 left this for later because it is a missing key rather than a second spelling, so
fixing it changes those answers' shape, which FR 037 had set out not to do.

## Goals

**Primary:** every mutating tool refuses an unresolved subject the same way, with
`blocked_by: "subject_not_found"`.

**Secondary:** a test that asks it of every mutating command, so a sixth cannot drift.

## Functional requirements

1. The five tools add `blocked_by: "subject_not_found"` to the answer they already give when the
   subject resolves to no basemesh, in all three miss states: nothing active, a name that is no
   object, and an object with no basemesh among its relatives.
2. Nothing else in those answers changes. `found`, `ready`, `performed` and the message stay as
   they were.
3. Each of the five descriptions names the slug where it already describes the miss, as the nine
   others do in their refusal lists.

## Non-functional requirements

- **One key, not a rename.** An added key breaks no caller that did not read it, so the protocol
  version stays at 2. [architecture.md](../../../specifications/architecture.md#the-wire) raises it
  for a renamed parameter or key.
- **The description budget.** 140 B of descriptions, inside the ceiling.

## Architecture

One keyword in each command's `basemesh is None` branch. The shared resolver is unchanged: it
returns the sentence, and each command builds its own answer. That is why five of them could leave
the key out without anything else noticing.

## Affected specifications

- [mutating-tools.md](../../../specifications/mutating-tools.md): "failing to resolve is an answer"
  now says what that answer carries in a mutating tool.
- [tool-interface.md](../../../specifications/tool-interface.md#the-glossary): unchanged. Its
  glossary already said an unresolved subject is `blocked_by: "subject_not_found"`, and is now true
  of every tool it covers.

## Tests

`bridge/test/tests/eee_composite/subject_resolution_test.py` already dispatches all eighteen
commands that take a subject in each of the three miss states. It now also requires
`blocked_by: "subject_not_found"` and `performed: false` from every answer that carries
`performed`, which is every mutating command. With the key taken out of the five again, it fails,
on `set_macro_details` in the "nothing active" state (the harness stops at the first failure), and
it passes with the key in.

## Verification

Unit suite 459, bridge suite 390, and the smoke run 34 of 34 against a headless Blender 5.1 with
MPFB 2.0.17. The composite test is where the new claim is checked. It runs against a real MPFB, so
no separate live script was needed for one key.

## References

- [FR 037](../037-one-word-per-concept/README.md), whose census found it.
- [FR 036](../036-subject-resolver-and-duplication/README.md), which gave the eighteen commands one
  resolver and the composite test this extends.
