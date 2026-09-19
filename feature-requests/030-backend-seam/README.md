# The server-side backend seam

**Status:** Accepted

[FR 028](../done/028-pivot-to-specific-addon/README.md) decided that MPFB's Blender-side logic
belongs in a companion add-on and proved the transport;
[FR 029](../done/029-bridge-transport-and-skeleton/README.md) grew that add-on into something
twenty-five commands can be added to. Neither touched `src/mpfbmcp/`, deliberately, and the
consequence is that **nothing on mpfb-mcp's side has ever spoken to the bridge**. This is
[stage 2 of the pivot](../NEXT_STEPS.md#2-the-server-side-backend-seam): mpfb-mcp learns to.

**The seam is an adapter below the send.**
[Supporting a second backend](../../specifications/architecture.md#supporting-a-second-backend)
already says where it goes, having been designed for a different second backend and spent on this
one instead. The property it exists to preserve is that no tool module learns which transport it
is on — and the test of that is a diff, not an argument.

**Three things land here that are nobody else's.** The client half of the protocol handshake, which
FR 029 built the bridge's half of and left to "whoever first speaks to it". Backend selection,
which must be explicit configuration because no probe distinguishes the three candidate ports.
And one tool migrated — **chosen for being dull rather than representative** — so that both paths
can be run side by side against one Blender and their answers *compared* rather than assumed equal.

**This is the first stage that cannot be deleted without consequence**, and that is worth saying
plainly rather than discovering. FR 028 and FR 029 both ended with `bridge/` removable and the
running system untouched. After this one, `src/mpfbmcp/` has changed. What replaces reversibility
is a default: a user who upgrades and configures nothing gets exactly the system they had, because
the configured backend defaults to `blender_mcp` and twenty-four tools have no other path anyway.

**And this is where the testing centre of gravity starts moving, which is the largest thing the
pivot buys and the least visible.** MPFB is reachable only from inside Blender, so for twenty-five
tools the Blender-side logic has been checked by `exec()`-ing a generated payload against a stub
`bpy` and stub services — a harness that can prove the code does what its author expected and can
prove nothing whatever about MPFB. As add-on code, that same logic is ordinary Python in an
extension, exercisable against a **real** MPFB in a headless Blender. **The end state is that
almost everything is tested there, and that what remains on mpfb-mcp's side is only what genuinely
cannot cross the socket.** One tool is migrated here; the discipline is established here too,
because a precedent set at the first tool is what the remaining twenty-three copy.

Three specifications are rewritten here, all three because a sentence in them is about to become
false: [observability.md](../../specifications/observability.md), whose record's unit stops being a
program; [responses.md](../../specifications/responses.md) and
[tool-interface.md](../../specifications/tool-interface.md), whose "returns blender_mcp's envelope
as-is" needs a new referent. A fourth is rewritten because
[stage 3's own text](../NEXT_STEPS.md#3-introspection-and-catalogues-migrated) assigns it to
"whichever effort migrates the first tool", and that turns out to be this one — see
[Affected specifications](#affected-specifications).

## Goals

**Primary.** Make the bridge reachable from mpfb-mcp, behind a seam that sits below `send_code()`
and is invisible above it. A tool says what it wants done; the seam decides how the request
travels.

**Primary.** Migrate exactly one tool, and prove the two paths agree by measuring it. "The bridge
returns the same answer" is the claim the remaining three stages rest on, and it has never been
checked for any tool.

**Primary.** Close the handshake. FR 029 defined what the bridge does with a version it cannot
serve; nothing has ever declared one.

**Primary.** Establish where a migrated tool is tested: on the add-on side, in a headless Blender,
against a real MPFB — everything that can be. This effort writes one tool's worth of it and the
rule that says so, and the rule is worth more than the tool.

**Secondary.** Keep the per-call record useful across the transition. The record's attachment point
does not move — it never could, the socket is still the only boundary — but what it writes stops
being a `.py` and the design has to say so before there are two kinds of call and one file format.

**Secondary.** Wire up coverage in the bridge harness, which FR 028 deferred to "the effort that
first migrates a command" and this is.

**Explicitly not a goal.** A second migrated tool, deleting anything on the generated path, or
moving the other twenty-four tools onto the seam. All three are later stages, and each of them is
cheaper for this one having stayed small.

## Functional requirements

1. **The backend is chosen by configuration and never by probing.** `MPFB_MCP_BACKEND` names it:
   `blender_mcp` (the default) or `bridge`. `MPFB_BRIDGE_HOST` and `MPFB_BRIDGE_PORT` give the
   bridge's address, defaulting to `127.0.0.1` and `9877`. **An unrecognised backend name is an
   error, not a silent fallback** — a typo that quietly leaves every call on the old path is
   indistinguishable from the bridge not working, which is the most expensive shape a
   configuration mistake can take. No autodetection of any kind: both third-party add-ons answer
   on 9876, the bridge on 9877, and no single probe distinguishes any of them, since a
   NUL-terminated ping leaves the community add-on's parser waiting while an unterminated one
   leaves blender lab's doing the same.

2. **Routing is per tool, driven by that preference.** The seam holds one table of the tools that
   have a bridge command. A tool in that table goes over the bridge when the bridge is preferred,
   and over the generated path otherwise; a tool not in it always goes over the generated path,
   in both configurations. That table is the list of what has been migrated, it lives in one
   readable file, and stage 5 deletes it by emptying it.

3. **No tool module learns which transport it is on, and the check is a diff.** After this effort,
   `git diff` on the migrated tool module shows its send call replaced and nothing else — no
   branch on a backend, no second params dict, no import of a bridge client. The other twenty-four
   tool modules show no diff at all. If supporting the bridge required editing a tool's logic, the
   seam is in the wrong place and the requirement has failed regardless of what works.

4. **Every bridge request declares `protocol_version`, and the first one per address probes.**
   The declaration is free and gets the bridge's own `protocol_mismatch` refusal for nothing. The
   probe is one `get_status` on the first bridge call in a process, per `(host, port)`, cached
   thereafter and dropped on a connection failure; it is what reads
   `min_supported_protocol_version` and so the only thing that can tell the caller **which end to
   upgrade** rather than merely that two numbers differ. A version this client cannot work with
   fails every bridge call with one sentence naming both versions and the end to change.
   **The probe must not become a round trip per call**; the memo is a claim about what this
   process learned, exactly as `shared_cache._PRIMED` is, and is wrong in exactly the same
   ordinary way when Blender restarts.

5. **The envelope becomes ours, and both backends produce it.** `status`, `result` and `message`
   keep their present meanings and their present spellings, so no existing caller or test changes.
   The bridge's `error` slug becomes part of the contract, and a generated-code **error** envelope
   is given `error: "command_failed"` by the seam — which is a statement of fact rather than a
   guess, since a blender_mcp error envelope is always a program that raised inside Blender. A
   success envelope is untouched on both paths. Nothing else is synthesised: `protocol_version` is
   a fact about the bridge's protocol and is absent from a generated-code answer rather than
   invented for it.

6. **`mpfb_list_objects` is the migrated tool, and the bridge gains a `list_objects` command.**
   It was chosen for being dull: one optional string parameter, read-only, no shared fragments, a
   result of five keys, and `requires_mpfb` — which makes it the **first command in the table for
   which that flag is `True`**, so FR 029's `mpfb_unavailable` precondition is exercised from
   outside for the first time. The command reproduces the payload's behaviour rather than tidying
   it: `_ALL_TYPES` read off the service's module with the stale local vocabulary as fallback,
   MPFB's case-insensitive **substring** type matching, `get_object_type()`'s `""` coerced to
   `null`, and only `bpy.context.scene.objects` searched.

7. **Everything that can be tested on the add-on side is tested there, in a headless Blender.**
   This is the testing end state the whole pivot is for, and it is established with
   `mpfb_list_objects` rather than merely described. The logic that answers the call is add-on
   code now, so it is checked against a **real** MPFB in `bridge/test/`, under
   `blender --background` — not against a stub `bpy` and stub services, which is the only thing
   the client side was ever able to offer and which can establish nothing about MPFB.

   **What stays on mpfb-mcp's side is only what genuinely cannot cross the socket**: the tool's
   own local argument validation, which runs before any transport is chosen; what goes on the
   wire for a given call; the seam's routing, handshake and envelope mapping; and the record. A
   *new* client-side test asserting something about **MPFB's behaviour** — which type names
   match, what an empty scene answers, what `get_object_type()` returns for an untyped object —
   is a test in the wrong harness after this effort, however well it passes.

   The payload's existing stub-executed layer is the one exception and it is a bounded one: it
   stays while the payload stays, because the payload is half of what requirement 8 compares, and
   it is **frozen** — not extended, not added to, and deleted with the payload in stage 5.

8. **The two paths are compared field by field against one Blender, and the comparison cannot pass
   vacuously.** A script in this subdir calls the tool once per backend against the same scene and
   asserts the results equal, for the empty scene and for a scene with a character in it, filtered
   and unfiltered, and for the recognised-type and unrecognised-type cases. Following FR 029's
   arrangement, the comparison must **fail** when handed two runs of the same backend, so that
   "identical" cannot mean "the second run was never made".

9. **A bridge that is not there says so as well as blender_mcp does.** A refused connection raises
   a `ConnectionError` naming the bridge by name, the address tried, and the fact that its server
   is started from the add-on's preferences panel and is off until it is. This is the commonest
   failure this system has, and the message is the whole of the diagnosis.

10. **The record's unit stops being a program.** A bridge call writes its request — the command and
   its parameters — as JSON before the socket call, exactly as a program is written before one
   today and for the same reason: a call that hangs or takes Blender down still leaves behind what
   caused it. The tool name comes from the command rather than from a payload seam marker.
   `index.tsv` keeps its columns and its meaning, with `bytes` counting the request either way.
   The generated path's records are unchanged, byte for byte, and **off still means unchanged**:
   no directory, no file, no formatting, identical bytes on the wire.

11. **Nothing that works today stops working.** With nothing configured, every one of the
    twenty-five tools behaves exactly as it does now, including `mpfb_list_objects`. The unit
    suite still runs to completion on a machine with no Blender and no bridge; its count moves
    only upward, by the tests this effort adds. [verification/](../../verification/) passes in the
    default configuration with no edit to `smoke.py`, and its coverage rule still derives from the
    registry — no tool is added or removed here.

12. **The smoke run is executed in both configurations, and the transitional prerequisite is
    written down.** This is the sharp consequence of migrating one tool out of twenty-five:
    [verification/harness.py](../../verification/harness.py) builds its scratch scene, its
    snapshots and its cleanup through `send_code()` directly, so a run in which `mpfb_list_objects`
    crosses the bridge needs **both** add-ons enabled and both servers started in one Blender.
    That is fine and temporary, and it must be stated in
    [verification/README.md](../../verification/README.md) rather than met as a puzzle. The harness's
    own probes stay on `send_code()`: they are scene bookkeeping, not tool calls, and they go away
    with the generated path in stage 5.

13. **The second install path is documented.** [CLAUDE.md](../../CLAUDE.md) gains the two new
    environment variables under Commands, and the transitional arrangement — both add-ons, two
    ports, one Blender — stated once where the existing setup instructions are.

### Out of scope, deliberately

- **A second migrated tool.** The whole value of one is that a disagreement between the paths is
  attributable. Two tools migrated together, one of which disagrees, is a worse position than one
  tool migrated and understood.
- **Moving the other twenty-four tools onto the seam.** Mechanically it is a small change — the
  seam would route them all to the generated path — and it would make stages 3 and 4 pure
  additions to one table. It is refused here because it touches twenty-four tool modules and their
  tests for no behavioural change, in the one stage whose job is to establish that the seam works
  at all. Stage 3 may do it in bulk if it prefers; nothing here prevents that.
- **Deleting anything on the generated path.** `codegen/`, `shared_cache.py`, the seven fragments
  and `mpfb_list_objects`' own payload all stay, and the payload's test layer stays with them.
  That is not tidiness deferred: the payload is half of what requirement 8 compares. Stage 5
  deletes them.
- **`shared_cache.send()` routing through the seam.** It is generated-path machinery whose entire
  reason for existing — a program costs ~250 ms per 4 KB — has no counterpart on the bridge. It
  dies with the path it serves.
- **A `backend` field in a success envelope.** Considered and refused: a success envelope is
  untouched in every configuration
  ([observability.md](../../specifications/observability.md)), and adding the field to
  `mpfb_get_status`' answer would mean editing an unmigrated tool, which requirement 3 exists to
  forbid. Which backend answered is in the log line and in the record, which is where a question
  about the transport belongs. Note the tension with
  [a response says which source answered it](../../specifications/responses.md#a-response-says-which-source-answered-it)
  and resolve it in the spec: that rule is about **two sources of an answer**, MPFB and a vendored
  copy, not about two routes to the same source.
- **A bridge-side per-call record.** FR 029 deferred it to whenever there are commands worth
  recording. One is not enough, and the design question it asked — what the unit of the record is
  — is answered here for the client, which is the half that has one.
- **`mpfb_list_urls`' connection-failure fallback over the bridge.** It is the one tool that
  catches `ConnectionError` and answers anyway, it is stage 4's, and it is not made harder by
  anything here: the seam raises the same exception type from either path, which is worth
  asserting in a test now so stage 4 inherits it rather than discovers it.

## Non-functional requirements

- **The seam is below the send or it is nothing.** Stated as the first requirement and repeated
  here as a quality attribute because it is the one thing a reviewer should check first: the value
  of this design is entirely in tools not knowing, and a seam that leaks one `if backend ==` into
  one tool has already failed for all twenty-five.
- **`connection.py` stays a faithful duplicate of blender_mcp's protocol.** Its docstring makes
  that claim and the claim is load-bearing: it is why a change upstream can be mirrored by hand.
  So the envelope mapping of requirement 5 happens **in the seam**, not in `connection.py` — the
  additions stay around the protocol rather than in it, exactly as the observability additions did.
- **The default configuration is the working system.** A user who upgrades and sets no variable
  must not be able to tell this effort happened. This is what replaces the reversibility FR 028
  and FR 029 could offer and this one cannot.
- **Uniformity of failure, across two protocols.** A caller branches on `status` and now on
  `error`, never on `message`, and that must be true whichever path answered. Two transports with
  two error vocabularies visible to callers would undo the main benefit of having a seam.
- **One diagnostic surface.** `MPFB_MCP_RECORD_DIR` and `MPFB_MCP_LOG_LEVEL` keep their names,
  their semantics and their off-by-default behaviour, and a run that mixes the two backends
  produces one index in one directory in call order. A second record format for a second transport
  would make the transition the thing hardest to observe, at the moment observation is worth most.
- **Tested where it runs.** A test belongs in the harness that can reach the thing it is about,
  and after a migration that harness is the bridge's. The quality attribute this protects is not
  tidiness but *evidence*: a stub-executed payload test passes because the stub agrees with the
  author, and thirteen efforts' worth of live verification exists precisely because that is not
  the same as MPFB agreeing. Moving a check from a stub to a real install strengthens it even
  when the assertions are copied across unchanged — and the migration is the only moment at
  which the move is free.
- **Honesty about what the comparison establishes.** One tool, one shape of answer, read-only, no
  shared fragments, no mutation, no file written outside the `.blend`. It establishes that the
  seam works and that one dull tool agrees with itself. It establishes nothing about a batched
  tool, a mutating one, or one whose payload is 26 KB of shared fragments — and the request should
  say so where somebody planning stage 3 will read it.

## Architecture

**Where the new code goes.** Two new modules on the client side, one new command on the bridge
side, and edits to three existing files. Nothing shared is restructured:
[adding a tool touches exactly three things](../../CLAUDE.md#architecture) and migrating one should
touch no more.

| Module | What it is |
|---|---|
| `src/mpfbmcp/bridge_connection.py` (new) | The bridge wire client: JSON + NUL framing, `send_command(name, params)`, `MPFB_BRIDGE_HOST` / `MPFB_BRIDGE_PORT`, the `protocol_version` declaration and the handshake memo. Sibling of `connection.py` and deliberately not a modification of it — the two protocols are different and one module pretending to serve both is how a faithful duplicate stops being faithful. |
| `src/mpfbmcp/backend.py` (new) | The seam. Reads `MPFB_MCP_BACKEND`, holds the payload-to-command table, chooses the route, maps the generated path's error envelope up to the common shape. The one file that knows there are two transports. |
| `src/mpfbmcp/observability.py` | `begin()` gains a way to open a record for a command rather than a program; `tool_name_from_program()` stays, unused by the new path, because the old path still needs it. |
| `src/mpfbmcp/tools/list_objects.py` | One call changed. Its local validation, its docstring and its parameter shape are untouched. |
| `bridge/mpfb_bridge/commands/list_objects.py` (new) | The command: `PARAMS`, `SUMMARY`, handler. |
| `bridge/mpfb_bridge/commands/table.py` | One entry, and the first `requires_mpfb=True` in the table. |

**What a migrated tool's call looks like, and why the tool names neither backend.** The seam takes
what the tool was already passing to `codegen.assemble()` — the payload's filename, the params
dict, the bootstrap — and holds the mapping from payload name to command name itself:

```python
return backend.send("list_objects.py", params={"object_type": ...}, bootstrap="raising")
```

The params dict is the same on both paths, because both sides receive the tool's already-validated
arguments and neither reshapes them. **Do not build an escape hatch for the case where they
differ.** If a later tool needs different parameters per path that is a fact worth surfacing as a
design problem in that tool's own effort, not a flexibility worth carrying through three stages
unused.

**The handshake, and the two ways to get it wrong.** The memo is keyed on `(host, port)` and
cleared when a call to that address raises `ConnectionError`, for the reason `shared_cache`'s memo
is: it records what this process learned, not what Blender is, and Blender restarting invalidates
it without telling anyone. The trap is recursion — **the probe is itself a bridge call**, so it is
issued through `bridge_connection` directly and never through the seam, or the first call in a
process probes in order to probe. The second trap is cost: a probe per call would double the round
trips of the cheapest tool in the package, which is precisely the tool being migrated.

**The bridge's `get_status` and mpfb-mcp's `mpfb_get_status` are different things**, and this is
the effort in which somebody first has to hold both in mind. The command reports the bridge — its
version, the protocol it speaks, the state of MPFB as the *add-on* sees it. The tool reports MPFB
in three tiers including asset roots and configured paths, and is not migrated here. Say so in
[the wire](../../specifications/architecture.md#the-wire) rather than leaving the collision to be
re-derived; stage 4 has to resolve it properly when the tool moves.

**The command must not import MPFB's submodules, and this is the first command where the
temptation is concrete.** `_ALL_TYPES` is a module-level name in `objectservice.py`, not a member
of `ObjectService` and not in `SERVICES`, and as add-on code the bridge *could* simply import it.
It must not:
[never import MPFB submodules directly](../../specifications/architecture.md#never-import-mpfb-submodules-directly)
survives the pivot unchanged, and the supported route is the one the payload already uses —
`sys.modules[ObjectService.__module__]` with a `getattr` fallback, which is
[reading module-level names MPFB does not publish](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish)
verbatim. The fallback matters for the same reason it does today: reporting last year's type list
is a better answer than failing the call.

**Timeouts are not shared between the two clients.** `connection.py` waits 300 s, which is right
for a generated program that may do a Rigify generate inside Blender, and stays. The bridge client
should have its own constant and its own reasoning rather than inheriting a number chosen for a
different transport — note that the bridge's own `_CLIENT_TIMEOUT` of 10 s is a *read* deadline for
one request's bytes and is not the same quantity.

**Environment variable naming, and the rule it follows.**
[observability.md](../../specifications/observability.md) says mpfb-mcp's own settings carry the
`MPFB_MCP_` prefix and that `BLENDER_MCP_HOST` / `BLENDER_MCP_PORT` are spelled the way they are
because both processes address the same add-on. Applying that rule: which backend to use is
mpfb-mcp's own decision, so `MPFB_MCP_BACKEND`; the bridge's address names the add-on being
addressed, the same logic that names `BLENDER_MCP_HOST`, so `MPFB_BRIDGE_HOST` and
`MPFB_BRIDGE_PORT`. This is a judgement call rather than a derivation — the bridge add-on reads
its address from preferences and not from the environment today — and if the bridge ever does read
the environment, these are the two names it should read.

**One configuration mistake is worth a sentence somewhere and no code.** A user who has set
`BLENDER_MCP_PORT=9877` and then enables the bridge points the generated-code client at an add-on
that does not execute programs. The failure is loud and the message is the bridge's
`malformed_request`, which is legible enough; a guard against it would be autodetection by another
name.

**Anchors.** [FR 028](../done/028-pivot-to-specific-addon/README.md) found that heading anchors in
`architecture.md` are linked from `src/mpfbmcp/` docstrings and from finished requests, so a
rewrite that renames a heading breaks links it cannot see. Three of the four specs rewritten here
carry anchors referenced elsewhere. Check before renaming, and use an explicit `<a id>` where the
heading text must change — which is what FR 028 did twice.

## Affected specifications

Rewritten by **this** request:

- [observability.md](../../specifications/observability.md) — named by the stage text, and the
  rewrite is narrower than it sounds. The attachment point does not move and cannot: the socket is
  still the only boundary every tool crosses, and
  [Diagnostics attach at the socket boundary, never to the program](../../specifications/observability.md#diagnostics-attach-at-the-socket-boundary-never-to-the-program)
  is more true after this, not less. What changes is the *unit*: "every tool assembles a program,
  hands it to `send_code()`" becomes two sentences, and the bullet about a retry leaving two
  records stays as a fact about the generated path rather than about the record in general. The
  paragraph on `MPFB_MCP_` prefixes gains the two new variables and keeps its reasoning.
- [responses.md](../../specifications/responses.md) — "The envelope is blender_mcp's and is not
  negotiable" is about to be false in its first clause and true in its second.
  [Response shape](../../specifications/responses.md#response-shape) becomes a description of
  *this package's* envelope, with `error` in it, the mapping rule for the generated path, and the
  unchanged instruction that a caller checks `status`. The `null` versus `[]` rule and everything
  below it is untouched.
- [tool-interface.md](../../specifications/tool-interface.md) — the "returns blender_mcp's envelope
  as-is" referent, and nothing else.
  [Validate before crossing the socket](../../specifications/tool-interface.md#validate-before-crossing-the-socket)
  is unaffected in substance and gains one clarification: the rule now holds in front of two
  sockets, and the bridge validating again is
  [deliberate](../../specifications/architecture.md#both-ends-validate-deliberately) rather than
  redundant.
- [testing.md](../../specifications/testing.md) — **this is the effort that first migrates a
  tool**, which means two deferrals land here rather than in stage 3.
  [Stage 3's own text](../NEXT_STEPS.md#3-introspection-and-catalogues-migrated) says "testing.md is
  rewritten by whichever effort migrates the first tool" and was written assuming that would be
  stage 3; stage 2 migrates one, so it is this. The change to
  [The unit suite is two layers](../../specifications/testing.md#the-unit-suite-is-two-layers) is
  the substantive one: a migrated tool has a *third* layer for the duration of the transition and
  one layer afterwards, and where its Blender-side logic is tested moves from stubs to a real
  install. **The rule requirement 7 states is what should be folded in**, in the plainest form it
  can be given: after a tool is migrated, everything that can be checked on the add-on side is
  checked there, and what remains on mpfb-mcp's side is named as a closed list rather than left to
  each effort's judgement.
  [What the suite can never establish](../../specifications/testing.md#what-the-suite-can-never-establish)
  needs the other half of that edit — it is a list written when *everything* Blender-side was out
  of reach, and for a migrated tool most of it stops being true. The second deferral is the bridge
  harness's coverage, in
  [Two harnesses, split at the directory boundary](../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary),
  which FR 028 pointed at "the effort that first migrates a command".
- [architecture.md](../../specifications/architecture.md) — two sections.
  [Supporting a second backend](../../specifications/architecture.md#supporting-a-second-backend)
  stops describing a seam that was designed and starts describing one that exists, names the two
  variables, and keeps its heading and its anchor.
  [The generated-code path](../../specifications/architecture.md#the-generated-code-path-what-runs-today-and-is-being-retired)
  gains the fact that one tool no longer uses it. [The wire](../../specifications/architecture.md#the-wire)
  gains the client's side of the handshake and the sentence distinguishing the bridge's
  `get_status` command from the `mpfb_get_status` tool.

**Explicitly not this request's.**
[mpfb-integration.md](../../specifications/mpfb-integration.md) is untouched for the reason FR 028
and FR 029 both gave: what MPFB does wrong does not depend on how the call arrives.
[mutating-tools.md](../../specifications/mutating-tools.md) is untouched because the migrated tool
mutates nothing — the first mutating tool to cross the bridge is stage 4's, and that is the effort
that should check whether anything there assumes a program.
[vision.md](../../specifications/vision.md) needs nothing: the end state has not changed.

[CLAUDE.md](../../CLAUDE.md) gains the two environment variables and the transitional two-add-on
setup under Commands, two rows in its module table, and an amendment to the `mpfb_list_objects`
row in the tool table saying which path it now takes. Map edits only; no narrative paragraph
([why](../CLAUDE.md#lifecycle)).

## Tests

Both harnesses grow, and the split holds:
`python3 -m unittest discover -s tests` must still find nothing that imports `bpy`, and the bridge's
suite must still be reached only by its own command.

**They do not grow symmetrically, and that is requirement 7.** The bridge's suite takes everything
about what the tool *answers*, against a real MPFB in a headless Blender. What `tests/` gets for
the migrated tool is what cannot cross the socket: local validation, the bytes on the wire, the
seam, the record. Where a check could plausibly live on either side, it goes to the bridge — a
check against a real install is better evidence than the same check against a stub the author also
wrote, and deciding case by case here is how twenty-three later migrations end up with
twenty-three different answers.

**In `tests/`, with no Blender anywhere:**

- **`tests/fake_bridge.py`** (new) — the bridge faked, as `fake_addon.py` fakes blender_mcp, and
  for the same three reasons: it must answer differently per request (so a `get_status` probe and
  the command under test can differ), answer nothing and close, and keep the raw request bytes so a
  test can assert what went on the wire. It must be able to answer a `protocol_mismatch` and each
  of FR 029's other slugs on demand.
- **`tests/test_bridge_connection.py`** (new) — framing across a split `recv()`, the NUL
  delimiter, the error envelope, `MPFB_BRIDGE_HOST` / `MPFB_BRIDGE_PORT`, a refused connection's
  message naming the preferences panel, and that a `ConnectionError` is raised for the same
  situations `connection.py` raises one for — which is what stage 4 inherits for
  `mpfb_list_urls`.
- **`tests/test_backend.py`** (new) — the seam: the default is `blender_mcp`, an unrecognised
  value fails rather than falls back, a tool in the table routes by preference and one outside it
  never does, the error-envelope mapping adds `error: "command_failed"` and only to an error
  envelope, a success envelope is byte-identical on both paths, the probe happens once per address
  and not per call, and a `ConnectionError` drops the memo so the next call probes again.
- **`tests/test_list_objects.py`** — and this is the module requirement 7 is really about. What
  is **added** here is deliberately thin, because it is all that cannot cross the socket: that
  the wrapper sends `list_objects` with the right params to a fake bridge, that `object_type`'s
  local validation runs *before* a transport is chosen and refuses the empty string for MPFB's
  substring reason, and that a bridge error envelope reaches the caller intact. Nothing added
  here asserts what MPFB answers. The existing wrapper layer stays as it is; the payload layer
  stays **frozen** for as long as the payload does, and when stage 5 deletes the payload this
  module should lose roughly the share of itself that was ever about MPFB — which is a number
  worth recording during the effort, since it is the first real evidence about what the pivot
  does to 14.2k lines of tests.
- **`tests/test_observability.py`** — a recorded bridge call writes its request as JSON, names the
  record for the command, and appends one index line with the same columns; a run mixing the two
  backends produces one index in call order; and the disabled path still puts identical bytes on
  both wires.

**In `bridge/test/`, inside a headless Blender:**

- **`list_objects`** — the first command with real MPFB behind it, the first test in that suite
  whose subject is MPFB rather than the transport, and **where the bulk of this effort's testing
  weight belongs**. It covers everything the payload's tests cover today, for the same reasons and
  now against a real install: the substring type match, an unrecognised type, `""` coerced to
  `null`, a scene with no MakeHuman objects, and the `_ALL_TYPES` fallback when the private name
  is absent. It should also cover what the stub-executed layer never could — that MPFB's real
  `ObjectService.object_is()` agrees with the substring semantics the tool's docstring promises a
  caller, which is a claim about MPFB that has until now rested on a reading of its source.
  **How the command behaves in a Blender with no MPFB is part of the test, not an obstacle to
  it** — FR 029's arrangement of stubbing `mpfb_resolution` is the route.

  Two practical things this is the effort to settle, since twenty-three commands inherit them:
  **how a test builds a character to look at** in a headless Blender (MPFB's own suite is the
  model, and how much of MPFB works without a screen is
  [explicitly unestablished](../done/029-bridge-transport-and-skeleton/README.md)), and **what a
  test does when the install it runs against lacks a prerequisite** — skip with a reason, never
  pass quietly, which is the rule [verification/](../../verification/) already follows.
- **Coverage**, per the deferral above: the `a1_coverage.pth` that starts `coverage` before the
  add-on is imported, a `.coveragerc`, and the combine-and-report pass. No script in mpfb2 creates
  that file, so this is an adaptation rather than a copy.

**Live verification, in this subdir, as a script.** `check_backend_seam.py`, run against a Blender
with MPFB, the bridge and blender_mcp all enabled. What it establishes that no unit test can:

- **The two paths agree**, field by field, over the cases in requirement 8 — and the comparison
  fails when handed two runs of the same backend, so it cannot pass vacuously.
- **The handshake against a real bridge**: a well-formed call succeeds, a request declaring an
  impossible version is refused as `protocol_mismatch`, and the client's own refusal names both
  versions.
- **`mpfb_unavailable` reaches the tool as a legible failure**, run against a `--factory-startup`
  Blender with the bridge enabled and no MPFB — the first time that error path is exercised from
  outside the add-on.
- **The cost of the two paths**, measured rather than assumed. FR 029 measured the bridge at 50 ms
  through the timer and under 1 ms headless for a command taking no parameters; the interesting
  number here is the same tool over both transports from the same client, which is the first
  like-for-like comparison this project can make.

**No smoke item is added.** [verification/](../../verification/) holds one item per registered
tool, this effort registers none, and
[tests/test_verification_smoke.py](../../tests/test_verification_smoke.py) enforces exactly that
correspondence. What `verification/README.md` gains is the transitional prerequisite of
requirement 12, and the run is performed twice — once per backend — with both passing.

**What this effort will not establish**, stated now rather than discovered in stage 3: nothing
about a batched tool, a mutating tool, a tool carrying shared fragments, or a tool writing outside
the `.blend`; nothing about what happens to the 14.2k lines of tests when a payload with real
logic in it becomes add-on code, since the payload migrated here is eighty lines and half of them
are a comment; and nothing about performance under a realistic answer, since a scene listing is
small by construction.

## References

- [NEXT_STEPS.md, stage 2](../NEXT_STEPS.md#2-the-server-side-backend-seam) — the entry this
  request implements, including the three items it names as belonging here.
- [FR 028](../done/028-pivot-to-specific-addon/README.md) — the decision, and
  [its analysis of where the seam goes](../../specifications/architecture.md#supporting-a-second-backend),
  which was written for a different second backend and is spent on this one.
- [FR 029](../done/029-bridge-transport-and-skeleton/README.md) — the bridge's half of everything
  this request completes: the parameter contract, `requires_mpfb`, `list_commands`, the version
  handshake, and the two drive mechanisms proved to give identical answers.
- [`bridge/mpfb_bridge/command_server.py`](../../bridge/mpfb_bridge/command_server.py) —
  `dispatch()`, `_check_protocol_version()`, `PROTOCOL_VERSION` and
  `MIN_SUPPORTED_PROTOCOL_VERSION`, and the nine error slugs a client must be ready for.
- [`src/mpfbmcp/connection.py`](../../src/mpfbmcp/connection.py) — the client to model and the
  claim not to break: a faithful duplicate of blender_mcp's protocol, with the additions around it
  rather than in it.
- [`src/mpfbmcp/shared_cache.py`](../../src/mpfbmcp/shared_cache.py) — the memo pattern the
  handshake cache follows, including why a miss is an ordinary outcome rather than a contradiction.
- [`src/mpfbmcp/codegen/payloads/list_objects.py`](../../src/mpfbmcp/codegen/payloads/list_objects.py)
  — what the new command must reproduce, quirks included.
