# Testing

> **Visionary specification.** This describes the *intended* discipline, not a description of
> every test currently written; where the suite diverges, the intent stated here governs. See
> [Status of these documents](README.md#status-of-these-documents). For what each test module
> actually covers, see the module's own docstring and the table in
> [CLAUDE.md](../CLAUDE.md#tests).

mpfb-mcp is in an unusual position for a test suite: the thing it exists to drive is reachable
only from inside a running Blender, and never from a test process. That single fact shapes
everything below. See
[No direct dependency on MPFB or blender_mcp](architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp)
for why the boundary is where it is.

There are two kinds of check, and they answer different questions:

- The **unit suite** (`tests/`) answers *"is this the program we meant to send, and does it do
  the right thing with the answers it gets back?"* It runs anywhere, in about nine seconds, and
  it is what a change is expected to keep green.
- The **live harness** ([verification/](../verification/)) answers *"does MPFB do what we read
  in its source?"* It needs a running Blender, and it is described below.

## The live harness is named and re-runnable, not a session

Exercising a tool against real MPFB requires a running Blender with MPFB and blender_mcp
installed and enabled. That is a verification step outside the unit suite — but a **named and
re-runnable** one, not a manual session. It lives in [verification/](../verification/): a
snapshot/compare helper over twelve datablock collections, a fixture builder, and one script per
checklist, each driving the real tool callables the way an MCP client would and each printing one
pass/fail/skipped line per item with the observed value beside it. Re-running a whole checklist
after a code fix is one command.

That distinction is not cosmetic. Five consecutive requests reached `Done` without their live
check, each postponement justified by the cost of a session nothing of which survived to make the
next one cheaper — which is exactly the defect a re-runnable harness removes. The harness lives
outside `src/`, is not discovered by `unittest discover -s tests`, and is not shipped; nothing in
it may be imported by the package.

Two properties of it are load-bearing rather than incidental. **Checks go through the tool
callables**, not through hand-assembled `send_code()` calls, or what is verified is a program no
client will ever send — a large part of what is under test is the tool module's own validation
and defaulting. And **a comparison against "what MPFB's own panel produces" is a diff, not a
screenshot**: MPFB's panels are thin, so driving the scene property behind a slider or calling
the operator behind a button *is* pressing it, and the two results can be compared field by field
in one file.

What it changes outside the `.blend` and puts back, what it cannot put back, and how to run it
are in [verification/README.md](../verification/README.md).

## The unit suite is two layers

Stdlib `unittest`, no pytest. Each tool's test module exercises the same tool twice:

1. **The wrapper**, with `send_code` mocked. This is where argument validation, defaulting and
   the decision of *what to send* are tested. The sync callable behind the tool is reached via
   `mcp._tool_manager._tools[...].fn`, since `@mcp.tool` wraps it in a coroutine.
2. **The generated program**, `exec()`'d against stub Blender and stub MPFB services
   ([tests/blender_stubs.py](../tests/blender_stubs.py)). This is where the payload's real
   branching is tested — subject resolution, relationship walks, filtering and paging,
   precondition handling, write ordering.

Both layers are needed because the interesting logic is split across them by design (see
[Validate before crossing the socket](tool-interface.md#validate-before-crossing-the-socket)):
the tool module knows shapes, the payload knows MPFB.

## Stubs reproduce MPFB's behaviour, never convenient values

This is the central rule of the suite, and the one most easily broken by someone trying to make
a test pass.

A stub exists to make a payload's branches reachable. If it returns the value that would be
*convenient*, the branch the payload wrote to handle MPFB's actual behaviour is never taken, and
the test passes while asserting nothing. So a stub reproduces the quirk: `get_object_type()`
answers `""` and never `None`; `object_is_any_makehuman_object()` returns a string rather than a
bool; `find_related_objects()` yields the object it was asked about; `get_list_of_children()`
walks the whole file rather than the current scene; `set_target_value()` is a silent no-op for a
target that is not on the mesh; `has_target()` matches an encoded name the writers do not;
`TargetService.set_value()` stores **unclamped**, matching a property whose definition carries no
`min`/`max`; and `StubShapeKey.value` clamps to 0.0-1.0 on assignment, because Blender does.

**This rule is not a preference. It is the finding of [FR 013](../feature-requests/done/013-live-verification/README.md).**
The stub basemesh had no modifiers at all, where every basemesh MPFB creates carries a
`Hide helpers` MASK modifier on the vertex group `body`. That group is *also* the one the
`Hide base mesh` modifier a body proxy needs uses; the two differ only in
`invert_vertex_group`. Because the stub had neither, `mpfb_add_asset`'s guard — which could not
tell them apart — passed the suite through two rounds of review while failing against a real
Blender. Adding the real modifier to the stub broke three existing tests, two of which turned
out to be the tests being kind.

Two corollaries:

- **When a live finding can be pushed down into the stubs, it must be.** A defect the live
  harness found and the suite could have found is a gap in the stubs, and closing it is part of
  the fix rather than follow-up work.
- **Where mpfb-mcp compensates for MPFB, the compensation belongs in the payload and its
  absence in the stub.** `HumanService.set_character_skin()` does not coerce
  `material_instances`; MPFB's UI does. So the stub does not coerce either, the payload is what
  performs the coercion, and a test asserts the stub was handed `False` for a call that
  requested `True`. A coercing stub would let the payload do nothing and still pass.

## Choose a real filesystem when the payload's job is the filesystem

Two shapes of fixture, and the choice is not stylistic:

- **A real `tempfile` tree**, when the payload itself walks the disk. `payloads/list_rigs.py`'s
  job *is* `os.listdir()` and `os.path.isfile()`; `payloads/list_targets.py`'s is `os.walk()`.
  Mocking those away would leave nothing under test. The tree must carry the asymmetries a real
  install has — a rig with no weights file of its own, a weights file with no rig, a section
  present in both the bundled index and a user directory — because each is a branch.
- **A reproduced service**, when the payload asks MPFB rather than the disk.
  `payloads/list_assets.py` calls `AssetService`, so what needs reproducing is that service,
  quirks first: `get_asset_list()` keys its items by *label*, so two files differing only in
  case really do collapse into one entry, and each item's `thumb` holds something JSON cannot
  encode.

Some fixtures need both — the detail-target and mesh-asset cases walk the disk *and* write to a
stub character — which is what the shared `TestCase` subclasses in `blender_stubs.py` are for.
A fixture is shared rather than copied when two tools must agree about it: `RigTestCase` exists
so that one test can run `mpfb_list_rigs` and `mpfb_add_rig` against the same disk and assert
their weights answers are equal, which means nothing if it is two trees. `DetailTargetTestCase`
now carries the same shape for [`modifier_reading.py`](architecture.md#shared-fragments): one test
runs `mpfb_get_target_stack` and `mpfb_symmetrize_targets` over *one* character and asserts every
category reading matches, and it was checked by making one of the two diverge on purpose and
watching it fail.

**Every shared fragment owes the suite two things**, since a fragment exists precisely so that two
payloads cannot disagree:

- The fragment run **directly**, where it can be — `performed.py`, `refit_blocker.py` and
  `modifier_reading.py` are executed in `tests/test_codegen.py` against a namespace holding the
  handful of names each binds, rather than reached through a payload inside a stub Blender. A
  fragment that reads MPFB tables or the disk (`target_categories.py`, `rig_lookup.py`,
  `asset_sections.py`) is exercised through its payloads instead.
- A **drift check** that no payload keeps an implementation of its own — the thing the fragment
  was created to prevent, asserted against the payload source rather than trusted. Whichever line
  is the rule's signature move is the one to look for: for `refit_blocker.py` it is that no
  refitting payload calls `object_is_generated_rigify_rig()` itself, and for
  `modifier_reading.py` that neither reading payload negates a value.

## Two mechanics every stub-executing module inherits

Both follow from the bootstrap described in
[Resolving MPFB from generated code](architecture.md#resolving-mpfb-from-generated-code), and
both are silent when got wrong:

- **A stub service module's name must not end in `"mpfb"`**, or the bootstrap's candidate scan
  claims it as an MPFB install of its own.
- **The stub class's `__module__` is reassigned by hand**, because a payload reaching a
  module-level name MPFB does not publish looks it up via `sys.modules[Service.__module__]`.

## What the suite can never establish

Stated once here rather than repeated in every module, because the list is a property of the
architecture and not of any one test:

- **No stub builds a node tree.** Nothing in the suite establishes that any of the five skin
  types produces the material MPFB's own skin library panel produces.
- **No stub is MPFB.** Nothing establishes that a character modified through
  `mpfb_set_macro_details` matches one modified on MPFB's phenotype slider, that a garment
  equipped through `mpfb_add_asset` matches one from the asset library panel, or that a rig
  added through `mpfb_add_rig` matches one from the rig panel.
- **No stub has geometry.** Nothing establishes that rigging after dressing leaves the clothes
  unrigged — the claim
  [A tool reports an ordering constraint it cannot enforce](mutating-tools.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
  rests on.

Every item on that list is `verification/`'s job, and a feature request whose primary goal lands
in it must say so in its own "Tests" section rather than leave it to be discovered.

## The exception: what is entirely on this side of the socket

One part of the package is fully testable here, because it never crosses:
[observability.py](../src/mpfbmcp/observability.py). Its tests are held to a higher bar
accordingly, and two of them are load-bearing rather than routine:

- The tool name is extracted from a **real `codegen.assemble()` output for every payload**,
  never from a hand-written marker, because the marker format is a coupling between two modules
  that otherwise have nothing to do with each other.
- The **ordering** — the program on disk before the add-on answers — is asserted by having the
  fake add-on look at the filesystem *while it holds the request*. An implementation that wrote
  both files after the response would pass every other test in the module.

The same principle applies to any future component that does not cross the socket: if it can be
tested properly, it must be.
