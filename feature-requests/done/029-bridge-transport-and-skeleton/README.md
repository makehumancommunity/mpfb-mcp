# Bridge transport and skeleton

**Status:** Done

[FR 028](../028-pivot-to-specific-addon/README.md) proved the transport with one command that
takes no parameters, answers from `bpy` alone, and cannot fail in a way a caller needs to
distinguish. That was the right thing to prove and it is not much to build twenty-four more
commands on. This is
[stage 1 of the pivot](../../NEXT_STEPS.md#1-bridge-transport-and-skeleton): grow the proof of
concept into an add-on a migration can add commands to without each command re-deriving the
conventions.

**The gap is not the socket.** The framing, the timer dispatch and the closed table all work and
are verified. What is missing is everything a *second* command would have wanted and the first one
did not need: a way to declare and validate parameters, a way to fail when MPFB is not there, a
version handshake somebody actually checks, and a panel that says what is happening rather than
only what is configured.

**And one thing the stage-1 text does not mention, which turns out to be the largest item here.**
The bridge's own suite runs inside `blender --background`, where `bpy.app.timers` never fire and
the start operator therefore refuses. So none of its seven tests makes a socket round trip: the
transport this add-on exists to provide is the one part of it the suite cannot reach. A headless
drive mechanism — named in NEXT_STEPS as "the obvious candidate for real work here" and in
[architecture.md](../../../specifications/architecture.md#the-bridge) as "a legitimate thing to add
later" — is what closes that, and it is worth roughly fifty lines. Landing twenty-four commands on
a transport the bridge's own harness has never exercised end to end is a bad trade for fifty lines.

Nothing that works today changes. `src/mpfbmcp/` is untouched, as in FR 028, and the client half
of the handshake belongs to [stage 2](../../NEXT_STEPS.md#2-the-server-side-backend-seam).

## Goals

**Primary.** Make the command table something twenty-five entries can be added to mechanically.
A command should declare what it takes and whether it needs MPFB, and get uniform validation,
uniform errors and uniform MPFB resolution for free — so that the effort migrating a tool spends
its thinking on the tool rather than on how to report a bad argument.

**Primary.** Let the bridge's own suite test the bridge's own transport. Today it cannot, and the
reason is fixable rather than structural.

**Secondary.** Ship the headless drive mechanism as the feature it is, not as a test fixture. A
pipeline driving MPFB without a screen is a real use, it is how MPFB is most plausibly used from
CI, and the mechanism is the same one the tests need.

**Secondary.** Make the preferences panel diagnostic rather than write-only. The commonest failure
in this whole system is MPFB not being where the bridge looked, and today you learn that by making
a call and reading the answer.

**Explicitly not a goal.** Migrating any tool, or touching `src/mpfbmcp/`. Both are stage 2's, and
the reversibility property FR 028 established — everything the pivot has produced so far can be
deleted without affecting a working system — should survive one more stage intact.

## Functional requirements

1. **A command declares its parameters, and the dispatcher validates them.** A command's entry in
   the table carries a parameter specification — name, type, required or defaulted, and a range
   where one applies — and `dispatch()` checks a request against it *before* the handler runs,
   answering `invalid_params` with a message naming the offending argument. A handler that runs
   has already been given parameters of the right shape. The checks reproduce
   [mpfb-mcp's own rules](../../../CLAUDE.md#what-is-validated-on-this-side-of-the-socket) exactly,
   bool strictness and the non-`bool` integer included, because both ends validate deliberately
   and two ends that disagree about what a `bool` is are worse than one end.
2. **Each command lives in its own module from the start.** `commands.py` becomes a `commands/`
   package: one file per command, plus one short file holding nothing but the table. Twenty-five
   commands stacked into a single module is the shape this repository already rejected on the
   other side of the socket — `src/mpfbmcp/tools/` is one module per tool, and
   [one module per tool](../../../specifications/architecture.md#one-module-per-tool) says why. Doing
   it now rather than at the tenth command means no migration effort has to stop and reorganise,
   and no command's reasoning ends up in a docstring shared with four others. **The security
   argument survives the split intact, and is arguably improved**: what a sceptic must read is
   still one short file, and it is now a file containing the table and nothing else.
3. **An unknown parameter key is refused, not ignored.** FR 028's live run found that a `code` key
   smuggled into `params` was silently dropped, which was the right *security* outcome and is the
   wrong *usability* one: a misspelled `catagory` must fail with a message rather than be quietly
   discarded, for the same reason `mpfb_set_targets` rejects one on the other side of the socket.
4. **A command declares whether it needs MPFB, and the dispatcher resolves it.** A command marked
   as needing MPFB is not called when the install is `absent` or `not_initialized`; the caller gets
   a new `mpfb_unavailable` error slug carrying the state and the same sentence
   `mpfb_resolution.STATE_MESSAGES` already holds. A command so marked receives the resolved
   services rather than resolving them itself. Twenty-four of the twenty-five commands to come need
   this, and without it each of them fails as a `command_failed` with a traceback.
5. **The vocabulary is discoverable without provoking an error.** Today the only way to learn what
   the bridge answers is to ask for something it does not. A `list_commands` command reports every
   name with its parameter specification and its MPFB requirement. A closed vocabulary that can
   only be enumerated by guessing wrong is closed in the wrong sense.
6. **The protocol handshake exists on the bridge's side and is checkable.** A request may carry a
   `protocol_version`; a version the bridge cannot serve is refused with a `protocol_mismatch`
   slug rather than misinterpreted, and a request that carries none is served as today so that a
   hand-written client stays easy to write. `get_status` reports the version it speaks and the
   oldest it accepts. **The client half is stage 2's**, and this requirement is met when the
   bridge's behaviour is defined and tested, not when something checks it.
7. **The bridge runs headless, through a CLI command.**
   `blender --background scene.blend --command mpfb_bridge [--host H] [--port P]` binds the socket
   and serves requests from a blocking loop until interrupted, answering every command exactly as
   the timer-driven path does. The GUI start operator keeps refusing background mode and its
   message now names the alternative instead of conceding there is none.
8. **The preferences panel reports MPFB and recent activity.** It paints the resolution result —
   state, package, version, whether the add-on is enabled — and, once the server is running, the
   number of requests served, the last command and when, and the last error. What it configures is
   unchanged.
9. **`BRIDGE_VERSION` and `blender_manifest.toml` agree, and a test says so.** They are kept in
   step by hand today with a comment explaining that nothing in the extension format publishes one
   to the other. A comment is not a check, and the version is about to start being load-bearing.
10. **The add-on's `blender_version_min` is raised to `"5.0.0"`.** FR 028 set it to `"4.2.0"` to
    match MPFB's own floor, on the reasoning that there is no point supporting a Blender that
    cannot run MPFB. That reasoning is sound and the floor is nonetheless being raised: **the
    bridge is not MPFB and need not inherit its compatibility obligations.** MPFB is a
    general-purpose add-on with an installed base on older Blenders; the bridge is a companion
    nobody is running yet, whose whole audience installs it deliberately to drive MPFB from an
    agent. Supporting Blenders nobody will use it on costs testing surface and buys nothing, and
    the cost is paid by every one of the twenty-four commands still to be written. Two
    consequences, one of them immediate: it **settles the CLI question** in
    [Architecture](#architecture) below — `bpy.utils.register_cli_command` is unambiguously
    present on 5.0 — and it means a user on 4.2 with a working MPFB cannot install the bridge,
    which is a real narrowing and should be stated plainly wherever the bridge is documented
    rather than left to be discovered at install time.
11. **Nothing that works today stops working.** `src/mpfbmcp/` unmodified, all **886** tests passing
    unchanged, [verification/](../../../verification/) untouched, and `get_status`'s answer keeps every
    field it has.

    **This requirement said FR 028's [`check_bridge.py`](../028-pivot-to-specific-addon/check_bridge.py)
    must still pass unedited, and it cannot.** Four of its assertions fail, all from one cause,
    and the cause is requirement 3 doing exactly what it says. Three of its framing checks send
    `params={"note": ...}` and its closed-vocabulary section asserts that
    `params={"unexpected": True}` is tolerated — so refusing an unknown parameter key refuses
    those payloads. Nothing about the framing changed, which is checkable: the same three shapes
    pass with a payload that puts the extra key in the envelope instead, and the bridge's own
    suite now carries all three. The requirement is therefore **the script must still pass except
    for the assertions requirement 3 deliberately invalidates, and those must be exactly the four
    named above.** A fifth failure would be a regression. The script is not edited: it lives in
    `done/` and is a historical artifact.
12. **The bridge's suite makes at least one real socket round trip**, headless, through the
    mechanism requirement 7 adds.

### Out of scope, deliberately

- **Migrating any tool.** Stage 2 does that, and does it with one dull tool so the two paths can be
  compared. A command added here is infrastructure — `list_commands` — not a tool's command.
- **The client end of the handshake, and anything in `src/mpfbmcp/`.** Stage 2. Saying "checked at
  both ends" while only one end exists would be the kind of half-claim the specifications are
  careful about elsewhere.
- **A bridge-side per-call record**, the equivalent of `MPFB_MCP_RECORD_DIR`. The panel's request
  counter and last-error line cover the immediate need, which is "is it alive and what did it last
  do". A real record is worth having when there are commands worth recording, and its design
  question — what the unit of the record is — is
  [already stage 2's](../../../specifications/observability.md), which is where it should be answered
  once rather than twice.
- **Autostart on Blender launch.** blender lab's add-on has one and the temptation is real. It is
  refused here because "the server is off until started" is a stated posture in both
  [ui.py](../../../bridge/mpfb_bridge/ui.py) and
  [architecture.md](../../../specifications/architecture.md#the-bridge): a listening socket that
  appears because software was installed is exactly what this pivot claims to improve on, and
  "installation is the consent" only holds while starting it is a second, separate act. Adding it
  means reversing a documented decision, which is a request of its own and not a panel tweak.
- **A shared-secret token.** Settled in FR 028 and not reopened here.
- **Exposing the idle interval and idle delay in preferences.** They exist in
  `command_server.py` and are not settable. They are tuning knobs nobody has needed; the panel
  additions this request makes are the diagnostic ones, and a panel of knobs is not the same thing
  as a panel that tells you something.
- **Coverage in the bridge harness.** Deferred by FR 028 to "the effort that first migrates a
  command", recorded in
  [testing.md](../../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary), and
  that is still the right effort — not this one.

## Non-functional requirements

- **One short file must remain readable as the security argument.** This is the constraint both
  the parameter specification and the `commands/` split are under, and it is a real risk from two
  directions: a declarative spec is one refactor away from being a framework, and a package of
  twenty-five modules is one convenience away from a registry assembled at import time. If reading
  one short file stops telling a sceptic everything the add-on can be asked to do, the structure
  has failed no matter how much boilerplate it saved. The table stays a literal dict of literal
  records, in a module that holds the table and its imports and nothing else. **If a reviewer has
  to follow a decorator to learn what a command takes, back it out.**
- **One dispatch, two drive mechanisms.** The headless loop and the timer differ in how they wait
  for a socket and in nothing else. They must share `dispatch()`, the framing and the error
  envelope. blender lab's add-on does *not* do this — its `_handle_blocking_client` is a second
  read loop beside the timer-driven one — and a second implementation of the framing is a second
  place for the UTF-8-across-`recv()` bug to come back.
- **Uniformity of failure.** A caller branches on the slug, never the sentence. Two new slugs are
  added here and they must be as boring as the seven that exist.
- **Reversibility.** Unchanged and still worth stating: delete `bridge/` and the system that runs
  today is unaffected.
- **Familiarity to MPFB's developers.** Unchanged from FR 028, and the new modules are held to it:
  MPFB's `.pylintrc`, no `from __future__`, `.format()`, `__all__`, module-level `_LOG`,
  `mpfb_bridge.` operator ids.
- **Honesty about what headless mode does not fix.** It makes the bridge drivable without a
  screen. It does not make MPFB fully usable without one — some of MPFB's own behaviour depends on
  UI context, and this request establishes nothing about which parts. Say so rather than implying
  a headless pipeline is now supported end to end.

## Architecture

**Where the new code goes.** New modules under `bridge/mpfb_bridge/`, one existing module turned
into a package, and edits to three others. Two rows below were not in this table when it was
written and are recorded rather than quietly absorbed: `version.py`, because three places need
the add-on's version and none of them is a natural owner for it, and `commands/command.py`,
because the record a table entry *is* turned out to want a home of its own:

| Module | What it is |
|---|---|
| `validation.py` (new) | The parameter specification type and the validators. No `bpy`, so it is readable and testable outside Blender like `command_server` and `mpfb_resolution` already are. |
| `cli.py` (new) | `argparse` over `--host` / `--port`, starting the server and running the blocking loop. Modelled on `../blender_mcp/addon/blender_mcp_addon/cli.py`, which is 57 lines. |
| `stats.py` (new) | Requests served, last command, last error, last timestamp. `bpy` stays out of it: the panel reads it, the server never draws. |
| `version.py` (new) | `BRIDGE_VERSION`, which must equal the manifest's. A module of its own because the status command, the panel and the table all need it. |
| `commands/command.py` (new) | The `Command` record: handler, parameter spec, `requires_mpfb`, summary. It carries no behaviour — a record that could validate itself would be one each command could quietly opt out of. |
| `commands/` (was `commands.py`) | A package: `table.py` holds `COMMANDS`, mapping a name to a record — handler, parameter spec, `requires_mpfb`, one-line summary — rather than to a bare function; `get_status.py` and `list_commands.py` hold one command each. See below. |
| `command_server.py` | `dispatch()` applies the spec and the MPFB requirement before the handler; `poll_blocking()` is added for the headless loop; two new slugs. Also `bound_address()`, so the panel and the tests can ask what port was really bound when 0 was requested — and the client deadline becomes wall-clock rather than a count of ticks, since the two drive mechanisms tick at different rates and a client should not get ten times longer to dawdle because Blender happens to be headless. |
| `ui.py` | The panel additions, and the background-mode message now names the CLI command. |
| `__init__.py` | `register_cli_command` / `unregister_cli_command`, in `register()` / `unregister()`. |
| `mpfb_resolution.py` | `resolve()` returns a `Resolution` record rather than a four-tuple, because it is now handed to every handler and `resolution.state` is legible where `resolution[0]` is not. |

**How the `commands/` package is laid out, and the one rule that makes the split safe.** One
module per command, named for the command: `commands/get_status.py`, `commands/list_commands.py`,
and in due course `commands/set_asset_material.py`. The table lives in `commands/table.py`, which
imports each module and maps a name to its record — so the file a sceptic reads is a list of
imports followed by a literal dict, which is *more* legible than today's file where the table sits
under a hundred lines of handler. `commands/__init__.py` re-exports `COMMANDS` and nothing else.

**The rule: the table is built by `table.py` reading each module, never by a module registering
itself.** No decorator, no `__init_subclass__`, no directory scan, no import-time side effect. A
command module that is not named in `table.py` is dead code and must be unreachable, because the
security claim is that the dict is the whole vocabulary — and a dict assembled by imports is a
dict whose contents depend on import order. That is also why the handler modules are imported
explicitly rather than discovered: a scan would make adding a command to this add-on a matter of
dropping a file in a directory, which is very nearly the property the closed vocabulary exists to
deny.

This mirrors `src/mpfbmcp/tools/` deliberately, down to the naming: **tool module, payload,
bridge command module and test module should all share a name**, so that during the migration a
tool and the command it becomes are findable from each other. `mpfb_set_skin` is `tools/set_skin.py`
and `codegen/payloads/set_skin.py` today and should be `commands/set_skin.py` tomorrow. The one
difference is `register()`: an mpfb-mcp tool module registers itself with FastMCP, and a bridge
command module does not register anything at all — for the reason in the paragraph above.

**Do not cache the resolved MPFB services across calls.** This is the trap in requirement 4 and it
is worth naming before someone optimises into it. `mpfb_resolution.resolve()` is a `sys.modules`
scan and a couple of `getattr`s; resolving per dispatch costs nothing worth measuring. Caching it
costs correctness, because **MPFB can be disabled and re-enabled inside one Blender session** and
its `unregister()` leaves `MPFB_CONTEXTUAL_INFORMATION` populated — which is precisely why
`get_status` reports `enabled` separately in the first place. A cached services dict surviving a
disable is exactly the stale state nobody diagnoses. FR 028's observation that "the bridge can do
that once" was about the four undocumented module-level names `mpfb_set_asset_material` reads with
`getattr` fallbacks on every call; that is a memo keyed on a module object, it is still a good
idea, and it belongs to
[the effort that migrates that tool](../../NEXT_STEPS.md#4-creation-and-modification-migrated).

**`list_commands` is a command that is not a tool, and that is allowed.**
[architecture.md](../../../specifications/architecture.md#the-bridge) says "one tool is one command",
which a reader will notice this violating. The rule is about *not splitting a tool across several
commands* — the unit stays the intent, batching and multi-step reasoning stay inside one command.
It says nothing about the bridge having infrastructure of its own, and `get_status` is already
such a command in everything but name. Write the distinction down rather than leaving the next
reader to re-derive it.

**`bpy.utils.register_cli_command` needs no version guard, and that is requirement 10's doing.**
Against the old `"4.2.0"` floor this was an open question: the API is documented in
[the 5.1 reference](../../../../blender_python_reference_5_1/bpy.utils.html), blender lab's add-on
uses it but declares `blender_version_min = "5.1.0"` and so is no evidence about 4.2, and the
alternative would have been a `hasattr` guard leaving headless mode quietly unavailable on some
installs. At `"5.0.0"` the API is simply there. Write the registration unguarded — a `hasattr`
check against a floor that already guarantees the attribute is noise that outlives the reason for
it.

**The background-mode guard belongs to the operator, not to the server.** It is in `ui.py` today,
which is correct and must stay that way: `command_server.start()` knowing about `bpy.app.background`
would make the CLI path refuse itself. Worth checking rather than assuming when the CLI lands,
because the guard reads like a property of the server.

**Two pitfalls in the blocking loop**, both visible in the reference implementation:

- **`select` on the listening socket, and a `finally` that stops the server.** A `KeyboardInterrupt`
  must leave no bound socket behind; the CLI handler returns an exit code and Blender then exits,
  but an unclosed socket in a `finally`-less path is a confusing failure on the next run.
- **A blocking client must be serviced to completion, not one chunk per pass.** The whole argument
  for this transport is that a request's cost is not a function of its length; a headless path that
  reintroduced chunk-per-tick behaviour would make that claim true only in the GUI.

**Panel cost.** `draw()` runs often, and requirement 8 puts a `sys.modules` scan in it. That is
almost certainly fine — `find_candidates()` iterates a list of module names — but it is the kind of
thing that is fine until an install has three thousand modules loaded. Measure it during the
effort; if it is not free, the answer is a refresh button, **not** a timer. A background timer that
exists to keep a panel fresh is a listening add-on doing work nobody asked for.

**One documentation fix in passing**, since this request owns `bridge/`:
[bridge/test/README.md](../../../bridge/test/README.md) says "the five tests that currently exist" and
there are seven. FR 028 noticed and corrected the same drift in its own requirement text; the
README kept the old number.

## Affected specifications

Rewritten by **this** request:

- [specifications/architecture.md](../../../specifications/architecture.md) — five places, three of
  them because a sentence there is about to become false.
  [The bridge](../../../specifications/architecture.md#the-bridge)'s paragraph beginning "The server
  runs only in a GUI Blender, and refuses to start anywhere else" states that a headless command
  loop is "a legitimate thing to add later" and that "until it exists the refusal is the honest
  answer"; it exists after this request and that paragraph becomes a description of two drive
  mechanisms and why the operator still refuses. The same section's opening states
  `blender_version_min = "4.2.0"` **to match MPFB's** — requirement 10 changes both the number and
  the reasoning, and the reasoning is the part worth rewriting: the bridge's floor is now its own
  decision rather than an inherited one, and the spec should say why a companion add-on need not
  carry MPFB's compatibility obligations. Its bullet **"The table is a literal dict in a module of
  its own"** survives in substance and must change in wording: after requirement 2 the module of
  its own holds the table and only the table, which is what that bullet was reaching for.
  [The wire](../../../specifications/architecture.md#the-wire) gains the two new slugs, the
  request-side `protocol_version`, and the rule that an unknown parameter key is an error.
  [Both ends validate, deliberately](../../../specifications/architecture.md#both-ends-validate-deliberately)
  gains the declarative specification as the mechanism on the bridge's side — the *principle* is
  already written and correct, so this is a mechanism paragraph rather than a rewrite.
- [specifications/testing.md](../../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary)
  — what the bridge harness can establish changes materially: it can drive a real round trip
  rather than only call into modules. That is the single biggest change to what this repository is
  able to test, and it should be recorded where the split is explained. The coverage deferral in
  that section stays deferred, and stays pointed at the first migration.

**Explicitly not this request's**, and named so the debt stays where FR 028 put it:
[observability.md](../../../specifications/observability.md),
[responses.md](../../../specifications/responses.md) and
[tool-interface.md](../../../specifications/tool-interface.md) are rewritten by the backend seam,
because all three are about what happens on *mpfb-mcp's* side of the socket and this request does
not touch that side. [vision.md](../../../specifications/vision.md) needs nothing: it describes the
end state, and the end state has not changed.
[mpfb-integration.md](../../../specifications/mpfb-integration.md) is untouched for the reason FR 028
gave — what MPFB does wrong does not depend on how the call arrives.

[CLAUDE.md](../../../CLAUDE.md) gains the headless command under Commands, and its `bridge/` table
rows change for `commands.py` — now a package — and `command_server.py`. It states no Blender
version and should not start. Map edits only; no narrative paragraph.

**One comment is load-bearing and will be missed.** `bridge/mpfb_bridge/blender_manifest.toml`
justifies its floor in place — "Matches MPFB's own floor. MPFB is what this add-on exists to
drive, so there is no point supporting a Blender that cannot run MPFB." Requirement 10 makes that
comment false while leaving it true-looking, which is the failure mode
[the lifecycle warns about](../../CLAUDE.md#lifecycle): a decision whose stated reason is wrong is
harder to revisit than one that never gave a reason. Rewrite it, do not just change the number.

## Tests

**The bridge's own suite is where this effort is checked**, and for the first time it can check
the thing that matters. `bridge/test/tests/` grows, in MPFB's style — module functions, bare
`assert` with a message, a docstring naming what is under test:

- **A real round trip, headless.** The test starts the server on an OS-assigned port, spawns a
  client thread that connects and sends a framed request, drives `poll_blocking()` from the main
  thread until the answer is written, and joins. That arrangement — client on a thread, dispatch
  on the main thread — is the one thing to get right, and it is also exactly the concurrency shape
  the add-on has in production. It needs no second Blender process.
- **Validation, table-driven.** One table of (spec, params, expected outcome), covering the cases
  the rules exist for: `"false"` is not a `bool`, `True` is not an acceptable `limit`, a negative
  offset, a range violation at each end, a missing required parameter, an unknown key. Each of
  these exists on mpfb-mcp's side because the alternative fails silently, and each must fail the
  same way here.
- **The MPFB requirement.** A command marked `requires_mpfb` gets `mpfb_unavailable` rather than
  running, in both non-`ok` states. The bridge's suite runs against a Blender that may or may not
  have MPFB installed, so this has to be driven by stubbing the resolution rather than by hoping —
  `mpfb_resolution` imports no `bpy` and is a module function, which makes it straightforward.
- **`list_commands` agrees with `COMMANDS`.** Every name, every spec. A discoverability command
  that can drift from the table it describes is worse than none.
- **`protocol_mismatch`**, and that a request carrying no `protocol_version` is still served.
- **`BRIDGE_VERSION` equals the manifest's `version`**, parsed from the TOML rather than repeated
  in the test.
- **The seven existing tests keep passing unchanged**, the background-mode refusal included. It is
  still correct: the operator refuses, the CLI command is the alternative.

**The test layout follows the command layout**, in MPFB's naming rather than this repository's:
one command module gets one `bridge/test/tests/<name>_test.py`. That is the same correspondence
`tests/test_<name>.py` already keeps with `tools/<name>.py` on the other side of the socket, and
starting it at two commands costs nothing, where starting it at fifteen is a reorganisation
nobody schedules. The shared infrastructure — validation, dispatch, the round trip, the
handshake — is tested per-concern rather than per-command and does not follow this rule.

**`python3 -m unittest discover -s tests` must find exactly what it finds today**, on a machine
with no Blender. 886, unchanged. If a test under `tests/` needs editing, this request has exceeded
its scope.

**Live verification, in this subdir, as a script.** `check_bridge_skeleton.py`, extending rather
than replacing FR 028's [`check_bridge.py`](../028-pivot-to-specific-addon/check_bridge.py) —
which must also still pass unedited, since requirement 11 says the wire format did not change under
it. What the new script adds beyond the unit tests:

- **Both drive mechanisms give identical answers.** The script is run twice against the same
  requests — once against a GUI Blender with the server started from the panel, once against
  `blender --background --command mpfb_bridge` — and the answers are compared field by field
  rather than merely asserted successful. That equality is the whole claim of requirement 7 and it
  is the one thing no unit test can establish, since a unit test only ever sees one of the two.
- **The closed vocabulary still holds**, re-running FR 028's four attack shapes against the new
  dispatcher. Adding a validation layer in front of the handler table is exactly the kind of change
  that could open a hole, and the check already exists.
- **A `requires_mpfb` command against a Blender with no MPFB**, which is a `--factory-startup` run
  and was already part of FR 028's procedure.

**No smoke item is added** to [verification/](../../../verification/). It holds one item per
registered MCP tool, this request registers none, and
[tests/test_verification_smoke.py](../../../tests/test_verification_smoke.py) enforces exactly that
correspondence.

**What this effort will not establish**, stated now rather than discovered later: nothing about the
behaviour of the twenty-four commands still to be written, nothing about performance under a
realistic payload — `list_commands` is not a batched `mpfb_set_targets` — and nothing about whether
MPFB is fully usable from a headless Blender. Requirement 7 makes the *bridge* drivable without a
screen; how much of MPFB works there is a question for whichever effort first needs the answer.

### Verification status

**Run against Blender 5.1.0 on 2026-09-15**, with the bridge symlinked into
`~/.config/blender/5.1/extensions/user_default/`. Everything passes.

| Check | Result |
|---|---|
| Bridge suite, `bridge/test/execute_tests_headless.bash` | **35 passed** (was 7) |
| [`check_bridge_skeleton.py`](check_bridge_skeleton.py), GUI Blender, server started from the panel | **45 passed, 0 failed** |
| [`check_bridge_skeleton.py --compare`](check_bridge_skeleton.py), headless, against the GUI run | **54 passed, 0 failed** |
| FR 028's [`check_bridge.py`](../028-pivot-to-specific-addon/check_bridge.py), both paths | **30 passed, 4 failed** — the four named in requirement 11 and no others |
| Unit suite, `unittest discover -s tests`, unchanged | **886 passed** |
| `git status --porcelain src/mpfbmcp verification tests` | **empty** |
| pylint against MPFB's unmodified rcfile | **9.38/10** |

**What the live run established that no test could:**

- **The two drive mechanisms are the same bridge.** Seven recorded answers compared field by
  field between a windowed Blender running the timer and a background one running the blocking
  loop: **every field identical except `result.blender.background`**. That is requirement 7's
  whole claim, and the comparison also fails when handed two runs of the same kind — it asserts
  that something *did* differ, so it cannot pass vacuously. The bridge's own suite cannot make
  this claim at all, because it runs headless and the timer cannot fire there.
- **The cost of the two paths differs, and in the direction it should.** 25 sequential calls at
  **50 ms each** through the timer at a 0.05 s interval — one tick, matching FR 028's 52 ms — and
  **under 1 ms each** headless, where `select` wakes on the connection rather than on a clock. The
  headless number is the more interesting one: it is what a pipeline would see, and it is not a
  number the GUI path can reach at any timer setting.
- **The closed vocabulary survived growing a validation layer.** FR 028's four attack shapes were
  re-run against the new dispatcher on both paths. All refused, and the `params`-smuggling one is
  now refused rather than ignored, which is strictly better.
- **The CLI command works as documented**, including the prerequisite that the add-on must be
  enabled in the Blender being run: `blender --background --factory-startup --python-expr
  "...addon_enable..." --command mpfb_bridge --port 9977`.

**Two things this effort did not establish**, stated because a verification that oversells itself
is worse than none. Nothing about the behaviour of the twenty-three commands still to be written:
the two in the table take no parameters and one boolean between them, so the parameter contract is
proved against synthetic specifications in the unit suite rather than against a real command. And
nothing about how much of *MPFB* works in a headless Blender — requirement 7 makes the bridge
drivable without a screen and says nothing about what it can then drive. The MPFB used during
verification was `absent` throughout, deliberately: every command in the table declares
`requires_mpfb=False`, so an `ok` install would have exercised nothing extra, and the
`mpfb_unavailable` path has no command to reach it from outside yet.

## References

- [FR 028](../028-pivot-to-specific-addon/README.md) — the decision, the proof of concept, and
  the conventions this request inherits. Its
  [What the proof of concept does not establish](../028-pivot-to-specific-addon/README.md#what-the-proof-of-concept-does-not-establish)
  is the list this request is working down.
- [NEXT_STEPS.md, stage 1](../../NEXT_STEPS.md#1-bridge-transport-and-skeleton) — the entry this
  request implements, including the headless mechanism it names as the candidate for real work.
- `../blender_mcp/addon/blender_mcp_addon/cli.py` and `execute_blocking.py` — the headless drive
  mechanism to model, 57 and 32 lines. `mcp_to_blender_server.poll_blocking()` is the select-based
  wait; `_handle_blocking_client()` beside it is the duplication **not** to copy.
- `../blender_mcp/addon/blender_mcp_addon/__init__.py`, around `register_cli_command` — how the
  command is registered and unregistered, and the pattern of refusing the GUI operator in
  background mode while pointing at the CLI.
- `../blender_python_reference_5_1/bpy.utils.html` — `register_cli_command(id, execute)`: the id
  must pass `str.isidentifier`, the callback takes the argument list after the id and returns an
  int, and the returned handle is opaque and only for unregistering.
- [CLAUDE.md, what is validated on this side of the socket](../../../CLAUDE.md#what-is-validated-on-this-side-of-the-socket)
  — the rules the bridge's validators must reproduce, each with the silent failure that motivates
  it.
- `../mpfb2/src/mpfb/__init__.py` — `MPFB_CONTEXTUAL_INFORMATION`, and the reason a resolved
  services dict must not be cached across a disable.
