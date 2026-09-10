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
- The **live smoke run** ([verification/](../verification/)) answers *"does every tool still
  work at all?"* It needs a running Blender, takes well under a minute, and is described below.
  *"Does MPFB behave as we read it in its source?"* is a different question, answered once, by
  the effort making the claim — see [Where an exhaustive live check belongs](#where-an-exhaustive-live-check-belongs).

## The live harness is named and re-runnable, not a session

Exercising a tool against real MPFB requires a running Blender with MPFB and blender_mcp
installed and enabled. That is a verification step outside the unit suite — but a **named and
re-runnable** one, not a manual session. It lives in [verification/](../verification/) and is one
command.

That distinction is not cosmetic. Five consecutive requests reached `Done` without their live
check, each postponement justified by the cost of a session nothing of which survived to make the
next one cheaper — which is exactly the defect a re-runnable harness removes. The harness lives
outside `src/`, is not discovered by `unittest discover -s tests`, and is not shipped; nothing in
it may be imported by the package.

**What it re-runs is a smoke test.** One item per registered tool, called with the tool's own
defaults, asserting three shallow things: the envelope is not an error, the response carries the
keys the tool's own contract names as always present, and — for a mutating tool — `performed` is
true and agrees with that tool's verb. That last one is the single check the unit suite genuinely
cannot make, because there the flag and the verb are read out of the same stub run. It asserts
nothing about *values*.

Two properties of it are load-bearing rather than incidental. **Checks go through the tool
callables** of the server `build_server()` builds, not through hand-assembled `send_code()`
calls, or what is verified is a program no client will ever send — a large part of what is under
test is the tool module's own validation and defaulting. And **a comparison against "what MPFB's
own panel produces" is a diff, not a screenshot**: MPFB's panels are thin, so driving the scene
property behind a slider or calling the operator behind a button *is* pressing it, and the two
results can be compared field by field in one file. The second property now describes what an
*effort* does during its life cycle rather than what `verification/` holds — the smoke run makes
no such comparison.

Two rules bound its growth, and only one is mechanical. **Coverage is derived from the
registry**: a registered tool with no smoke item, or an item for a tool the server does not
register, stops the run, so the table can neither fall behind nor keep dead entries.
[tests/test_verification_smoke.py](../tests/test_verification_smoke.py) asserts the same without
a Blender. **The time is bounded by design** — one character, one call per tool, three
assertions — and kept honest by being printed on every run rather than by a threshold. Sixty
seconds is a target the run reports itself against and never enforces: wall clock against
somebody else's Blender is too install-dependent to gate on, and a check that fails for a reason
outside the repository is one people learn to ignore. This is deliberately weaker than
[test_description_budget.py](../tests/test_description_budget.py)'s ceiling, which measures bytes
this repository computes and which are the same on every machine.

What it does to the Blender it is pointed at, what it cannot put back, and how to run it are in
[verification/README.md](../verification/README.md).

## Where an exhaustive live check belongs

**In the feature request that needs it** — its own subdir, run during that effort, moved into
`done/` with it. What the effort adds to `verification/` is at most the one smoke item for a tool
it introduced.

This is [FR 023](../feature-requests/done/023-verification-smoke-test/README.md)'s rule, and it
exists because the alternative was tried. [FR 013](../feature-requests/done/013-live-verification/README.md)
was right that a live check must be a re-runnable script rather than a memory of a session, and
its instruction — put it in `verification/` — produced eight per-request checklists, 5,308 lines,
and a run that crossed the socket more than two hundred times and took minutes. Nothing in those
checklists was wrong. Their findings had all been folded into these specifications and into
[HISTORY.md](../feature-requests/HISTORY.md) long before, and what was left standing was a receipt
for a conclusion already written down.

Exhaustively proving one feature against a live Blender is worth doing **once**, by the effort
making the claim. It is not worth re-proving on every code change, and keeping the proof around
forever is what turns a good idea into an unbounded directory.

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
- Each fragment is also **assembled both ways** — concatenated, and executed out of Blender's
  session source cache — and asserted to compile in both, because a program that compiles
  concatenated is not evidence that one compiles with the fragment embedded in a string literal.
  The two constraints that embedding puts on a fragment (no `'''`, no trailing backslash) are
  asserted of every fragment rather than of the ones that happen to be cached today.
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
- **No stub can establish what a real MPFB has loaded.** `mpfb_list_urls` reads
  `<root>.ui.weburls` out of `sys.modules`, and the payload test executes it against a stub
  `sys.modules` carrying exactly such a module — which is to say the test is built out of the
  assumption under test and can only ever confirm it. Whether MPFB really imports its UI on a
  normal install is a question only a running Blender answers, and FR 024's own check is what
  asked it. This is the general shape of the trap: **a stub that reproduces a precondition cannot
  verify it.**

Every item on that list needs a live Blender, and a feature request whose primary goal lands in
one must say so in its own "Tests" section rather than leave it to be discovered.

**None of them is a standing check, and the spec should not imply one.** The smoke run in
`verification/` establishes that each tool runs and reports having done what it says; it does not
establish that a garment equipped through `mpfb_add_asset` matches the panel's, nor that any skin
type builds the right node tree. Each of those was established once, by the effort that claimed
it — the asset comparison by [FR 010](../feature-requests/done/010-mesh-assets/README.md), the
five skin types by [FR 011](../feature-requests/done/011-skin-and-materials/README.md), the rig
and its weights by [FR 009](../feature-requests/done/009-add-rig/README.md) — and a later change
in that area owes the same proof again, in its own subdir. See
[Where an exhaustive live check belongs](#where-an-exhaustive-live-check-belongs).

## A test may depend on a sibling checkout if it skips without one

Some data in this package is copied by hand out of another repository: `reference/urls.py` is a
copy of MPFB's `ui/weburls.py`, and `reference/docs.py` names paths in mpfb2's `docs/` tree. Both
go stale silently — a renamed document still looks like a path — and neither can be checked at run
time, since [mpfb-mcp opens no network connection](architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on).

On the machine where the editing actually happens there is a checkout of the source repository one
directory up. A test may use it, **under one condition: it skips when the checkout is absent**, so
the suite still passes anywhere. `tests/test_reference_drift.py` is the first of these.

This is a real cost and is accepted rather than waved through. A skipped test proves nothing, and
a suite that quietly proves less on one machine than another is worse than one that proves the
same everywhere. It is worth it because the alternatives are both worse — a hard dependency breaks
the suite for anyone without the checkout, and no check at all leaves the drift to be found by
whoever follows a dead link. Two things keep it honest:

- **Read the sibling, never execute it.** Parse the file rather than importing it: importing
  another repository's module to read a few string literals runs whatever else is in it.
- **Assert that the read found something**, so that "no differences" cannot pass vacuously because
  the parse returned nothing.

Such a test says the *vendored copy* needs updating, never that the sibling is wrong. And it does
not replace a live check: the checkout is whatever is checked out, while the extension is whatever
is installed, and an effort's own live check compares against the second.

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
