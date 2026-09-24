# Testing

> **Visionary specification.** This describes the *intended* discipline, not a description of
> every test currently written; where the suite diverges, the intent stated here governs. See
> [Status of these documents](README.md#status-of-these-documents). For what each test module
> actually covers, see the module's own docstring and the table in
> [CLAUDE.md](../CLAUDE.md#tests).

mpfb-mcp is in an unusual position for a test suite: the thing it exists to drive is reachable
only from inside a running Blender, and never from a test process. That single fact shapes
everything below. See
[No direct dependency on MPFB](architecture.md#no-direct-dependency-on-mpfb-and-none-on-the-add-on-either)
for why the boundary is where it is.

**The harness has no private channel into Blender either**, and that is deliberate rather than an
oversight: the smoke run in `verification/` used to send Python of its own to make a scratch scene
and clean up after itself, the bridge executes nothing, and
[FR 033](../feature-requests/done/033-retire-the-generated-code-path/README.md) chose to narrow the
instrument rather than give the add-on an `exec` command for a test's benefit. What that cost is
written down where a passing run is read — see
[verification/README.md](../verification/README.md#what-fr-033-cost-this-instrument).

There are two kinds of check, and they answer different questions:

- The **unit suite** (`tests/`) answers *"is this the request we meant to send, and does it do
  the right thing with the answers it gets back?"* It runs anywhere, in seconds, and it is what a
  change is expected to keep green.
- The **live smoke run** ([verification/](../verification/)) answers *"does every tool still
  work at all?"* It needs a running Blender, takes well under a minute, and is described below.
  *"Does MPFB behave as we read it in its source?"* is a different question, answered once, by
  the effort making the claim — see [Where an exhaustive live check belongs](#where-an-exhaustive-live-check-belongs).
- The **bridge suite** (`bridge/test/`) answers *"does the add-on behave?"* It runs pytest
  **inside a headless Blender**, because the add-on under test is a Blender extension. It is a
  second harness in one repository, deliberately, and the reasons are in
  [Two harnesses, split at the directory boundary](#two-harnesses-split-at-the-directory-boundary).

## The live harness is named and re-runnable, not a session

Exercising a tool against real MPFB requires a running Blender with MPFB and the MPFB Bridge
installed and enabled, and the bridge's command server started. That is a verification step outside
the unit suite — but a **named and re-runnable** one, not a manual session. It lives in [verification/](../verification/) and is one
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
callables** of the server `build_server()` builds, not through hand-assembled requests, or what is
verified is something no client will ever send — a large part of what is under test is the tool
module's own validation and defaulting. And **a comparison against "what MPFB's
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

### Two patterns for a claim about more than one command

[FR 034](../feature-requests/done/034-character-summary/README.md) moved the reading code of three
commands into shared modules and added a fourth command that reports a subset of all three. Two
claims came with it that no single command's tests can make, and each has a way of being checked
worth reusing:

- **"Two commands agree" is tested by dispatching both.** For one subject in one state, dispatch
  the summary and each detailed command and assert every shared field equal
  (`bridge/test/tests/eee_composite/get_character_summary_test.py`; FR 027's
  `eee_composite/expression_divergence_test.py` is the same shape for three commands). A copy of a
  reading grown inside one command passes that command's own tests; only asking both catches it.
  When the fixtures cannot make every section interesting at once, ask in each state that makes
  one interesting, rather than weakening the comparison.
- **"This refactor changes no answer" is tested by a snapshot diff.** The request's live check
  took a `--snapshot` of every affected command's answer — on its worst-case character, under
  several argument sets, including the misses — to one JSON file with sorted keys, before the
  first move and after each one. A `diff` of two snapshots is empty or names exactly the intended
  change, which is a sharper instrument than the bridge tests, since those assert what someone
  thought to assert. It lives in the request's own subdir and moves to `done/` with it.

## Two harnesses, split at the directory boundary

[FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md) added a second test harness
to this repository, and a second harness is exactly the kind of thing that reads as drift unless
the reason is written down next to it.

`tests/` uses stdlib `unittest`, `tests/test_<name>.py`, `TestCase` classes, and no Blender
anywhere. `bridge/test/` uses **MPFB's** arrangement: pytest called from inside a headless
Blender, `<name>_test.py`, plain module functions, bare `assert` with a message, a docstring
naming what is under test, and alphabetical prefixes on directories to force order.

**In `bridge/test/tests/` the prefix goes only on directories, and a directory is a layer** that
assumes every earlier layer passed. The harness runs pytest with `-x`, so the first failure stops
the run, and the layering is right if and only if a failure in one layer makes a failure in a later
one uninteresting: a fault in the transport should be reported once, not as thirty symptoms in
thirty command modules. The layers, in run order, are `aaa_addon/` (the add-on itself, with no MPFB
subject), `bbb_shared/` (direct tests of `mpfb_bridge/shared/` — **reserved and not yet created**,
since every shared module is today tested only through the commands that use it), `ccc_reading/`
(one module per read-only command), `ddd_mutating/` (one per command that changes a `.blend`) and
`eee_composite/` (a claim about several commands at once, which means nothing asserted about one).
Modules inside a layer are unprefixed and named `<subject>_test.py` — for a command module, the
command name exactly — and **their order carries no meaning**. A new module goes into the layer its
subject belongs to, never under the next free letter; if two modules in one layer turn out to need
a particular order, the layer is two layers, and the modules do not get their prefixes back. With
only directories collectable at the top, the order is also the same whichever way a pytest version
sorts files against directories. MPFB's own layout is the model (`bbb_services/`, `ccc_data/`,
`ddd_entities/`, `eee_ui/`), one step further: it keeps one flat prefixed module at the top, and
this has none. [FR 035](../feature-requests/done/035-bridge-test-layers/README.md) replaced the
arrangement before it, in which a prefix on each module recorded the order modules were written
in, read-only commands ran after mutating ones, and the one prefixed directory existed only because
the letters were running out.

**The split is not a compromise; each side is right for what it tests.** `tests/` tests a package
that never imports `bpy`, and its whole value is that it runs anywhere in seconds. `bridge/` is
`bpy` code, so its tests need a real Blender — which is precisely what MPFB's harness provides
and what `tests/` structurally cannot. Adopting MPFB's harness for `bridge/` also pays for itself
twice: it is the arrangement that works, and it is the one an MPFB contributor already knows.

**A bridge test that mutates owes the suite a cleanup, and that is new since FR 032.** A read-only
command could not leave anything behind. These add rigs, equip assets, create materials and write
preset files, and a *failing* test is the one most likely to leave something. Two rules follow and
every module in `ddd_mutating/` and `eee_composite/` keeps both: what a test made, the fixture removes, however the test
ends — which `Character`'s snapshot-and-delete already does for objects, so a test that adds a rig
inside that block needs no cleanup code of its own; and a test that writes **outside the `.blend`**
writes somewhere redirected, never into the developer's own MPFB config directory.

A third rule is not about cleanup and was found by FR 032's spike rather than reasoned out: **a
fixture asset tree must be a redirected data root**, not merely a temporary directory with an MHCLO
in it. `ClothesService.fit_clothes_to_human()` re-reads a garment's MHCLO through `AssetService`,
which searches the roots — so a garment equipped from outside them can be equipped and then never
refitted. No read-only command re-reads an asset, which is why nothing before FR 032 could have
found it.

**Since FR 029 the bridge harness can test the bridge's transport, which it could not before.**
That is the single largest change to what this repository is able to check, and it is worth
recording where the split is explained rather than left as a fact about one test module. The
suite runs inside `blender --background`, where `bpy.app.timers` never fire and the start
operator refuses — so until the headless drive mechanism existed, every test in it called into a
module and none of them made a socket round trip. The add-on's own protocol was the one part of
it the tests could not reach. Now a test starts the server on an OS-assigned port, runs a client
on a thread and drives `poll_blocking()` from the main one, which is the same concurrency shape
the add-on has in production and needs no second Blender process.

**What that does not remove is the line between the two harnesses**, only where it falls. A
bridge test still needs a real Blender; `tests/` still must run on a machine that has none. And
the bridge's suite still cannot exercise the *timer-driven* path, since there is no event loop to
drive it — so whether a windowed Blender and a headless one answer the same is a claim no unit
test can make, and it belongs to an effort's own live check.

**One hard constraint falls out of it, and it is not negotiable.** `python3 -m unittest discover
-s tests` must keep discovering exactly what it discovers today, on a machine with no Blender
installed. A bridge test imports `bpy` and would fail at *import*, not at assertion — which is
the worst kind of failure, because it looks like a broken suite rather than a misplaced file. So
bridge tests live under `bridge/` and never under `tests/`, and the two are discovered by two
different commands that share nothing.

**Coverage is wired up in the bridge harness**, as of the effort that first migrated a command.
MPFB produces its report by having an `a1_coverage.pth` in Blender's `site-packages` start
`coverage` *before* the add-on is imported, which is what makes `class` and `def` lines count as
covered; the bridge does the same, with the one part that is not a copy written here — no script in
the mpfb2 repository creates that `.pth`, so `bridge/test/run_to_install_pytest.py` does, guarded
so that it does nothing unless `COVERAGE_PROCESS_START` is set and survives a Blender whose Python
has no coverage. Three properties are worth keeping when it is next touched:

- **A missing coverage tool must never fail a passing suite.** The report is produced after
  Blender exits and the run's exit code is the tests', not the reporting step's.
- **An existing `.pth` is left alone.** The file is shared with anything else measuring coverage in
  that Blender — MPFB's own harness installs one — and overwriting somebody's working arrangement
  to install an equivalent would be rude and invisible.
- **Nothing is excluded by pattern.** The uncovered lines in `timer.py` and `ui.py` are a true
  statement about what a headless suite can reach, and hiding them would make the number
  comforting rather than useful.

## The unit suite is one layer, and the bridge's suite is the other

Stdlib `unittest`, no pytest. A tool's test module exercises **the wrapper**: argument validation,
defaulting and the decision of *what to send*, with `send_command` mocked below the seam, plus a
thin class checking what actually reaches a fake bridge. The sync callable behind the tool is
reached via `mcp._tool_manager._tools[...].fn`, since `@mcp.tool` wraps it in a coroutine.

It was two layers until
[FR 033](../feature-requests/done/033-retire-the-generated-code-path/README.md): the second
`exec()`'d an assembled Python program against stub Blender and stub MPFB services, because that
program was where a tool's real branching lived and there was nowhere else to run it. There is
somewhere else now.

### A tool is tested where it runs

**Everything that can be checked on the add-on side is checked there**, in `bridge/test/`, against
a real MPFB in a headless Blender. This is the largest thing the pivot bought and the least
visible, and it is a rule rather than a preference because the alternative decays: deciding case by
case is how twenty-four commands end up with twenty-four different answers.

What stays in `tests/` is a **closed list** — what genuinely cannot cross the socket:

- the tool's own local argument validation, which runs before anything is sent;
- what goes on the wire for a given call;
- the seam, the wire protocol and the handshake;
- the record;
- the two vendored reference tables, which are never sent anywhere;
- **the preset-name rule as a two-way check**, because it is the one rule this package keeps on
  both sides of the socket and a disagreement between the copies would let a preset be written
  under a name that cannot be loaded back. It is about two files in this repository and reaches no
  Blender at all.

**A new client-side test asserting something about MPFB's behaviour is a test in the wrong harness,
however well it passes.** Which type names match, what an empty scene answers, what
`get_object_type()` returns for an untyped object: all of that belongs to the bridge's suite,
because a check against a real install is better evidence than the same check against a stub
written by whoever wrote the code under test.

**What the move cost and what it returned was measured**, tool by tool, and the numbers are in
[HISTORY.md](../feature-requests/HISTORY.md) rather than here: roughly three-fifths of a client
test module went with each tool's program, with two informative outliers. What is worth keeping in
a standing specification is the shape rather than the arithmetic — **a migration makes the suite
bigger before it makes it smaller**, because the bridge's own modules are added while the client's
are still needed, and the whole saving arrives in one effort at the end.

## A fixture reproduces the install, never a convenient one

This is the central rule of both harnesses, and the one most easily broken by someone trying to
make a test pass.

A fixture exists to make a branch reachable. If it presents the situation that would be
*convenient*, the branch the code wrote to handle MPFB's actual behaviour is never taken, and the
test passes while asserting nothing. So a fixture reproduces the awkward case: a rig tree with a
rig that has no weights file of its own, a weights file with no rig, and a rig with no entry in the
UI enum; a target tree with a section present in *both* the bundled index and a user directory, a
`.target.gz` where MPFB's own scan matches only `*.target`, and a name long enough that its shape
key name is encoded; an asset library with two roots holding the same `fedora.mhclo`.

**This rule is not a preference. It is the finding of [FR 013](../feature-requests/done/013-live-verification/README.md).**
The stub basemesh of the day had no modifiers at all, where every basemesh MPFB creates carries a
`Hide helpers` MASK modifier on the vertex group `body`. That group is *also* the one the
`Hide base mesh` modifier a body proxy needs uses; the two differ only in `invert_vertex_group`.
Because the fixture had neither, `mpfb_add_asset`'s guard — which could not tell them apart —
passed the suite through two rounds of review while failing against a real Blender. Adding the real
modifier broke three existing tests, two of which turned out to be the tests being kind.

**The pivot did not retire that rule; it moved where the rule bites.** A command's test runs
against a real MPFB, so MPFB's own behaviour is no longer something a fixture can get wrong — but
what the *install* holds still is. `bridge/test/tests/_fixtures.py` builds real target trees, real
MHCLO files and a real character and points MPFB's own `LocationService` at them, and every
asymmetry above is there because leaving it out is how a branch stops being tested.

**When a live finding can be pushed down into a fixture, it must be.** A defect found by a run
against a real Blender that a fixture could have exposed is a gap in the fixture, and closing it is
part of the fix rather than follow-up work.

## What the suite can never establish

Stated once here rather than repeated in every module, because the list is a property of the
architecture and not of any one test.

**It is a list about the *unit suite*, and the pivot emptied most of it.** Every item below was
written when everything Blender-side was out of reach from any harness in this repository. That
stopped being true: a tool's logic is add-on code, the bridge's suite runs against a real MPFB, and
each item stopped being a limitation and became a test somebody had to write.

**All twenty-four tools that cross the socket moved**, and the claims they carried were not merely
re-asserted — **nine of them turned out differently than a stub or a comment had said**, which is
the clearest evidence there is that the move was worth making:

- `object_is()` really is a case-insensitive substring test and `get_object_type()` really answers
  `""` for an untyped object (FR 030);
- MPFB's **default race weights are the literal `0.33` each**, so they sum to 0.99 and *every*
  default character trips `mpfb_get_macro_details`' "that scales the phenotype" warning;
- `HumanService.create_human()` builds a character of **one object** — no rig, no clothes, no
  relatives at all;
- a custom rig file is accepted by `get_custom_rigs()` only if it carries `identifying_bones`, and
  the skip is silent;
- `_get_opposed_modifier_value()` asks whether the positive target is **present**, not whether it
  is non-zero, so a category whose `incr` shape key exists at 0.0 reads 0.0 however far `decr` is
  pushed;
- `update_list_of_human_presets()` does a bare `os.listdir()` and **raises** on a missing config
  directory, which is why `mpfb_list_presets` checks the directory before asking MPFB anything;
- (FR 032) `HumanService.add_builtin_rig()` does **not** decide the armature modifier with
  `import_weights`. `Rig.create_armature_and_fit_to_basemesh()` adds it either way, so the comment
  claiming otherwise described a reading of MPFB's source the running install did not support. The
  reported field was always an observation off the object, so the answer was right and only the
  reasoning was wrong — which is exactly the shape FR 013 warned about and exactly the shape only a
  real MPFB finds;
- (FR 032) `ObjectService.find_rigify_metarig_by_rig()` returns `None` for **every** generated
  Rigify rig on current Rigify, because it reads an ID property that Rigify now stores as an RNA
  property. That is an MPFB defect, [filed rather than fixed](../feature-requests/NEXT_STEPS.md#file-upstream-mpfb-cannot-find-a-rigify-meta-rig-any-more),
  and the bridge test asserts agreement with MPFB's own lookup rather than a value so that it keeps
  passing when the defect is;
- (FR 032) MPFB's active-slot fixup matches a material name **ending in** `body`, and Blender
  uniquifies a name already taken — so a second character in one session gets `Human.body.002` and
  the fixup silently matches nothing.

Read what follows as the list for the *unit* suite, which is what it has always been. Every item is
now answered in `bridge/test/`, and each is named here with where:

- **No stub builds a node tree.** Nothing in the unit suite establishes that any of the five skin
  types produces the material MPFB's own skin library panel produces —
  `ddd_mutating/set_skin_test.py` asks MPFB's own `identify_material()` instead.
- **No stub is MPFB.** Nothing establishes that a character modified through
  `mpfb_set_macro_details` matches one modified on MPFB's phenotype slider, that a garment
  equipped through `mpfb_add_asset` matches one from the asset library panel, or that a rig
  added through `mpfb_add_rig` matches one from the rig panel — the three
  `ddd_mutating/` modules of those names do the modification for real.
- **No stub has geometry.** Nothing establishes that rigging after dressing leaves the clothes
  unrigged — the claim
  [A tool reports an ordering constraint it cannot enforce](mutating-tools.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce)
  rests on. `ddd_mutating/add_rig_test.py` puts a real relative on a real character and reads the
  enumeration back.
- **No stub can establish what a real MPFB has loaded.** `mpfb_list_urls` reads
  `<root>.ui.weburls` out of `sys.modules`, and the test of the day executed it against a stub
  `sys.modules` carrying exactly such a module — which is to say the test was built out of the
  assumption under test and could only ever confirm it. This is the general shape of the trap:
  **a fixture that reproduces a precondition cannot verify it.** `ccc_reading/list_urls_test.py`
  asks the module MPFB really loaded.

**What neither harness establishes**, and FR 032's spike named rather than discovered:

- **A Blender with Rigify disabled.** `mpfb_generate_rigify_rig`'s `rigify_unavailable` refusal
  and `mpfb_add_rig`'s are skips-with-a-reason wherever Rigify is on, which it is on a developer's
  machine. Only an install without it answers the question.
- **That the *timer-driven* server answers the same as the blocking dispatch.** There is no event
  loop in a headless Blender to drive a timer, so `bridge/test/` compares what `dispatch()`
  returns and never what arrives over a socket that a timer drained. That belongs to a feature
  request's own live check, and FR 032's
  [`check_creation_migration.py`](../feature-requests/done/032-creation-and-modification-migrated/check_creation_migration.py)
  is the one that made it for all twenty-four. The smoke run in [verification/](../verification/)
  makes it again, incidentally and on every run, since it goes over the real socket.

An item needing a live Blender belongs to the feature request that needs it, which must say so in
its own "Tests" section rather than leave it to be discovered.

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

- The **ordering** — the request on disk before the add-on answers — is asserted by having the
  fake bridge look at the filesystem *while it holds the request*. An implementation that wrote
  both files after the response would pass every other test in the module.
- **Off means unchanged**, asserted by comparing the bytes that reached the fake with the record
  on and the record off. A diagnostic that alters the call it describes is worse than none.

The same principle applies to any future component that does not cross the socket: if it can be
tested properly, it must be.
