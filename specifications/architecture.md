# Architecture

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).
>
> **Rewritten by [FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md).** The
> machine described first is the **bridge**, which exists today as a proof of concept carrying one
> command. The machine every tool actually uses is the **generated-code path**, described in full
> under [The generated-code path](#the-generated-code-path-what-runs-today-and-is-being-retired)
> and plainly marked there. Both are documented because both are real; one is being retired, and
> the retirement is staged so that both work until the last tool has moved.

This document describes **the machine**: where mpfb-mcp's boundaries are, how it reaches MPFB
without importing it, what crosses the socket, and how the package is laid out. It exists to keep
mpfb-mcp installable and runnable without a local checkout of MPFB, and to keep it working across
MPFB installs regardless of how the extension was installed.

**What is not here.** Conventions about how a tool behaves used to live in this document and now
have their own, because they are decisions about the product rather than about its structure:

| For | See |
|-----|-----|
| Why the bridge rather than a third party's add-on | [vision.md](vision.md#approach-a-bridge-add-on-of-our-own) |
| What a tool accepts, and how it names an object or a catalogue entry | [tool-interface.md](tool-interface.md) |
| What a tool must say back, and what an empty answer may imply | [responses.md](responses.md) |
| How a tool that changes a character behaves | [mutating-tools.md](mutating-tools.md) |
| What to do when MPFB is inconsistent, undocumented or wrong | [mpfb-integration.md](mpfb-integration.md) |
| Where diagnostics attach, and what they may and may not do | [observability.md](observability.md) |
| How all of it is tested | [testing.md](testing.md) |

For the current, concrete module layout, see [CLAUDE.md](../CLAUDE.md#architecture).

## Readability and developer experience are prioritized

These are first-class, non-functional requirements, not a finishing touch. Where readability and
brevity or cleverness conflict, readability wins.

**Code that runs inside Blender is code**, wherever it is written. This started as a rule about
generated Python — that a payload must be editable as ordinary Python, in its own file, with
syntax highlighting, working editor indentation and a linter that mostly applies, and that a
payload written as an escaped string literal fails that standard however well it works. The rule
survives the pivot and gets easier to keep: bridge code *is* ordinary Python in an ordinary
add-on. What it stops being is a trade against the wire, since prose in an add-on is not sent
anywhere.

**The bridge is held to a stronger version of this rule**, for two reasons that do not apply to
the rest of the package. It will be read by reviewers at an extension platform, and by users
deciding whether to trust a program that opens a socket. And it must be **familiar to MPFB's
developers specifically** — readability and familiarity are not the same property, code can be
perfectly clear and still feel foreign, and foreign is what stops a contributor from touching it.
The bridge is the piece of this project most likely to attract a patch from someone who has worked
on MPFB and never on an MCP server. So `bridge/` follows MPFB's conventions rather than this
package's where the two disagree, and carries MPFB's own `.pylintrc` and pyright setup to enforce
it; the divergences are recorded in
[FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md#architecture).

**Adding a tool should mean adding files, not editing shared ones.** A structure where every new
tool edits a module that all the other tools depend on does not scale past a handful of them; see
[Code-generation layout](#code-generation-layout) for what this means concretely, and note that
the bridge inherits the requirement rather than the mechanism — a new command is a function and
one line in a table.

## The bridge

MPFB's Blender-side logic belongs in a Blender add-on, because that is where it runs. The **MPFB
Bridge** is a companion extension — `bridge/mpfb_bridge/` in this repository, `id = "mpfb_bridge"`,
`blender_version_min = "5.0.0"` — that listens on `127.0.0.1:9877` and dispatches a
closed vocabulary of named commands. It is deliberately *not* part of the pip package:
`pyproject.toml` packages `src/mpfbmcp` and a top-level `bridge/` is outside its search root
entirely, so the bridge needs neither a package-data glob nor a `namespaces` setting.

**Its Blender floor is its own decision, not MPFB's.** The bridge began at MPFB's `4.2.0`, on the
reasoning that there is no point supporting a Blender that cannot run MPFB. That is true and the
converse does not follow: MPFB is a general-purpose add-on with an installed base on older
Blenders, and the bridge is a companion whose entire audience installs it deliberately in order to
drive MPFB from an agent. Supporting Blenders none of them run costs testing surface on every
command and buys nothing — and the cost is paid once per command, of which there are to be
twenty-five. The narrowing is real and should be stated wherever the bridge is offered rather than
discovered at install time: a user on 4.2 with a working MPFB cannot install the bridge.

**The command vocabulary is closed, and that is the point.** The server looks a name up in a fixed
table and runs nothing else; there is no request shape by which a caller's string becomes Python.
Three structural consequences:

- **One tool is one command.** Not one command per MPFB service function — the unit stays the
  *intent*, exactly as [vision.md](vision.md#what-makes-something-a-tool) requires. Batching and
  multi-step reasoning stay inside a single command rather than becoming several round trips.
- **The table is a literal dict in a module that holds the table and nothing else.** The security
  claim is only worth making if it is cheap to check, and checking it must mean reading one short
  file rather than tracing decorators across a package. Each command's handler and parameter
  specification live in a module named for the command, mirroring `src/mpfbmcp/tools/` down to the
  naming, and `commands/table.py` imports them and spells the table out. **The table is written,
  never assembled**: no decorator, no `__init_subclass__`, no directory scan, no registration as an
  import side effect. A dict assembled by imports is a dict whose contents depend on import order,
  and a directory scan would make adding a command to this add-on a matter of dropping a file in a
  folder — very nearly the thing a closed vocabulary exists to deny. A command module not named in
  the table is dead code and must be unreachable.
- **A command declares what it takes, and the dispatcher enforces it.** Parameters are a tuple of
  `Param` records — type, bounds, choices, default, nullability — checked before the handler runs,
  so a handler that runs has already been given parameters of the right shape. A command also
  declares whether it needs MPFB, and one that does is refused with `mpfb_unavailable` rather than
  reaching a service that is not there. Both are properties of the table rather than habits each
  handler keeps, which is what stops the twenty-fifth command from validating differently from the
  first.
- **`bpy` is main-thread only, so every command runs on the main thread.** The socket is
  non-blocking and is drained from a `bpy.app.timers` callback in a windowed Blender and from a
  `select` loop in a headless one; a handler therefore executes exactly where a button press
  would. A server that answered from an accepted connection's own thread would be touching
  Blender's data from the wrong one, which does not reliably fail — it corrupts.

**The honest limitation is documented rather than papered over.** While the server is running, any
local process can drive it, exactly as with both existing MCP add-ons. The defences are that it
binds loopback only, that it is off until started from a preferences panel, and that what it will
do is a list a sceptic can read. A shared-secret token was considered and rejected for now: it
adds a configuration step to every client setup, which is the friction the pivot exists to remove.

**There are two drive mechanisms, and which one you get is decided by whether Blender has a
screen.** In a windowed Blender the socket is drained from a `bpy.app.timers` callback; in a
headless one it is drained from a blocking `select` loop reached through
`blender --background --command mpfb_bridge`. They differ in how they wait and in nothing else,
ending in the same dispatch, the same framing and the same table — **one protocol implemented
once**, which is a deliberate departure from the add-on the transport is modelled on, where the
background path is a second read loop beside the timer-driven one.

**The start operator still refuses background mode, and now says what to use instead.**
`bpy.app.timers` callbacks are driven by Blender's event loop and a `--background` Blender has
none, so a server started from the operator there binds a socket, registers a timer that can never
fire, and answers nothing while every client hangs until its own timeout. That is not a
hypothetical: it is what the bridge did before
[FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md)'s live verification found
it, and the guard belongs to the *operator* rather than to the server — a guard in `start()` would
make the CLI path refuse itself.

**What the headless path establishes, and what it does not.** It makes the *bridge* drivable
without a screen, which is how a pipeline would drive MPFB and — the reason it was built when it
was — the only way the bridge's own test suite can exercise its own transport, since that suite
runs inside `blender --background`. It establishes nothing about how much of MPFB works without a
screen. Two prerequisites are easy to miss: the add-on must be *enabled* in the Blender being run,
because a disabled extension registers no CLI command, and the loop owns the main thread until it
is interrupted.

**`bpy.app.online_access` does not gate a loopback bind, and the bridge does not consult it.**
Blender asks add-ons that declare a `network` permission to respect that flag, and blender lab's
add-on refuses to start its server when it is off — while conceding in its own source that
localhost is "arguably a grey area". Measured on Blender 5.1.0 during FR 028's verification: with
the flag off, the bind succeeds and a full round trip completes, so it is a policy signal rather
than enforcement. **The bridge binds anyway**, on the reading that a socket which cannot leave the
machine is not the "online access" a user turning that checkbox off is refusing. The failure
message still names the flag as a suspect, which costs nothing if some future Blender enforces it.
This is a defensible reading rather than an obviously correct one, and it is exactly the kind of
thing to put to extension review rather than settle here.

### The wire

A request is a JSON object terminated by a NUL byte; a response is the same. The shapes:

```
--> {"command": "get_status", "params": {...}, "protocol_version": 1}\0
<-- {"status": "ok",    "protocol_version": 1, "command": "get_status", "result": {...}}\0
<-- {"status": "error", "protocol_version": 1, "error": "<slug>", "message": "..."}\0
```

The slugs are `malformed_request`, `unknown_command`, `invalid_params`, `command_failed`,
`result_not_serializable`, `request_too_large`, `timeout`, `mpfb_unavailable` and
`protocol_mismatch`. Two of those carry most of the meaning a caller acts on:
**`invalid_params`** says the request was wrong and names the parameter, and
**`mpfb_unavailable`** says the request was fine and the install is not — distinct from
`command_failed` on purpose, because there is no bug and no traceback to read, there is an
install to fix.

- **Nothing is decoded before the frame boundary.** The receive buffer is a `bytearray` and the
  delimiter search is a byte search, so a multi-byte UTF-8 sequence split across two `recv()`
  calls is a non-issue rather than a bug waiting for the first non-ASCII asset name: NUL cannot
  occur inside a UTF-8 multi-byte sequence, whose continuation bytes are all `0x80`-`0xBF`. This
  is the single most important thing the bridge copies from blender lab's add-on.
- **The socket is drained until it would block**, not read one fixed-size chunk per tick, and a
  client's deadline is reset by every chunk that arrives rather than only by a completed request.
  Both are deliberate departures from the add-on the transport is otherwise modelled on, whose
  one-chunk-per-tick read is the tax described under
  [What a call costs is the size of its program](#what-a-call-costs-is-the-size-of-its-program).
  At parameter sizes neither would matter much, which is exactly why the bridge should not inherit
  a defect it was built to avoid.
- **A caller branches on `error`, never on `message`.** The slug is the contract and the sentence
  beside it may be reworded; an unknown command's refusal additionally carries the list of
  commands that *do* exist, because a closed vocabulary is only useful if it is discoverable.
  `list_commands` is the same catalogue asked for politely, and the two must agree — having to
  guess wrong in order to learn an interface is a poor way to publish one.
- **An unknown key in `params` is an error; an unknown key in the envelope is not.** The
  asymmetry is deliberate and worth stating, because it looks like an inconsistency. The envelope
  belongs to the protocol and is versioned, so a client may carry a key this bridge has not heard
  of and a future one may add `request_id` without breaking anything. `params` belongs to one
  command whose contract is declared, so a misspelled `catagory` there is a mistake — and one
  that, quietly dropped, produces a call that succeeds and does nothing, which is the most
  expensive kind of failure to diagnose from the far side of a socket.
- **A result is serialized before the server commits to an answer**, so a value that cannot be
  encoded fails as a clear error envelope rather than as an exception halfway through writing a
  response the caller has already begun reading.

**The client's half of the handshake**, which `bridge_connection` holds: every request declares its
`protocol_version`, which costs nothing and earns the bridge's own `protocol_mismatch` refusal for
free, and the **first call to a given address issues one `get_status`**. That probe is the only
thing that reads `min_supported_protocol_version`, and so the only thing that can tell a user
*which end to upgrade* rather than merely that two numbers differ; a version this client cannot
work with then fails every call to that address with one sentence naming both. Two constraints keep
it honest. **The probe must not become a round trip per call** — it is memoised per `(host, port)`,
which makes it a claim about what this process learned, exactly as `shared_cache`'s memo is, and
wrong in the same ordinary way when Blender restarts, so a connection failure drops it. And **the
probe is issued through the wire client directly, never through the seam**, or the first call in a
process would probe in order to probe. A bridge that answers but reports no version is talked to
anyway: a handshake exists to catch a mismatch, not to invent one.

**The bridge's `get_status` command and mpfb-mcp's `mpfb_get_status` tool are different things**,
and the collision is worth naming before somebody assumes the tool was migrated when the command
appeared. The command reports *the bridge* — its version, the protocol it speaks, and the state of
MPFB as the add-on sees it — and is what the handshake probes. The tool reports *MPFB*, in three
tiers including asset roots and configured paths, and is still on the generated path. The effort
that migrates it has to resolve the overlap properly rather than letting one answer stand in for
the other.

### Both ends validate, deliberately

mpfb-mcp keeps its local shape checks — the bool-strictness, the range rules, the non-negative
int that is not a `bool` — so a malformed call fails before the wire with a message naming the
argument. The bridge then validates again. **That duplication is a cost of the socket being
public, and must be stated wherever it is documented or it will be mistaken for an oversight and
removed.** A listening socket is reachable by anything on the machine, not only by mpfb-mcp, so
the add-on cannot assume its caller already checked; and mpfb-mcp cannot skip checking, because
[validating before crossing the socket](tool-interface.md#validate-before-crossing-the-socket) is
what turns a silent wrong answer into a named argument error.

The division of labour is unchanged by the pivot: **shape here, vocabulary there**. Whether
`limit` is a non-negative integer is knowable on this side; whether `"cinderella"` is an installed
rig is not, and guessing would make the catalogue and the acting tool disagree.

**On the bridge's side the rules are data rather than code**, which is what keeps the duplication
from becoming a divergence of its own. A command declares its parameters as `Param` records and
one function checks them, so the bool-strictness, the non-`bool` integer and the range bounds
exist once for twenty-five commands instead of once per command. The same specification is what
`list_commands` hands out, so what a caller is told and what is enforced cannot drift apart. The
type vocabulary is JSON Schema's — `string`, `integer`, `number`, `boolean`, `array`, `object` —
because the reader on the other end is describing JSON rather than Python; `number` additionally
rejects NaN and the infinities, which survive `json.loads` and compare false against every bound.

### Versioning

Every answer carries a `protocol_version`, and `get_status` additionally reports
`min_supported_protocol_version` — the oldest request version this bridge still understands — so
that a client can tell "too old" from "from the future" without guessing. A request *may* declare
its own `protocol_version`; one outside the accepted range is refused with `protocol_mismatch`
rather than misinterpreted, and one carrying none is served, deliberately, so that a client
written by hand at a terminal stays possible. MPFB, the bridge and mpfb-mcp are three separately
released pieces, and that matrix is a real cost of this packaging choice — the only cheap defence
is a handshake that exists from the first command.

**Both halves of the handshake now exist**: the bridge's, above, and the client's, in
[the wire](#the-wire). One number is duplicated across the two — `PROTOCOL_VERSION`, which
`bridge_connection` declares and the add-on serves — and it is kept in step by hand for the reason
`connection.py` duplicates blender_mcp's protocol: `bridge/` is a Blender extension that imports
`bpy`, and making the pip package depend on it would undo
[no direct dependency](#no-direct-dependency-on-mpfb-or-blender_mcp). A unit test reads the add-on's
source and asserts the two agree, skipping where that source is not beside the package. The
bridge's own version is reported too, and must equal the `version` in `blender_manifest.toml` —
kept in step by hand, since nothing in the extension format publishes one to the other, and
asserted by a test rather than by a comment.

## No direct dependency on MPFB or blender_mcp

mpfb-mcp never imports MPFB Python code directly, and is never run *inside* Blender. Every
interaction with MPFB crosses two boundaries:

1. mpfb-mcp → the add-on, over a TCP socket. mpfb-mcp maintains its own minimal client for the
   protocol rather than depending on the add-on's package, so it installs standalone. On the
   generated-code path that add-on is blender_mcp and the protocol is a deliberate **duplicate**
   of blender_mcp's, which means a change upstream must be mirrored here by hand; on the bridge
   it is our own protocol and the duplication problem goes away with it.
2. The add-on → MPFB, inside the Blender process: by `exec()`-ing generated source on the old
   path, and by calling ordinary add-on code on the new one.

**The consequence that shapes everything else is a testing one.** Because MPFB is reachable only
from inside Blender, mpfb-mcp's own suite can verify the wire protocol and the generated code and
nothing beyond it; anything that depends on what MPFB actually does is checked against a running
Blender. The bridge changes *where* that line falls rather than removing it — bridge code is
testable against a real MPFB, which is an improvement and a large rewrite at the same time. That
split, and the discipline it imposes, is [testing.md](testing.md).

## mpfb-mcp opens no network connection except the one to the add-on

The socket to the add-on is the only connection this package makes. It fetches no URL, resolves no
host, and consults no remote service — not to check a version, not to retrieve a document, not to
validate a link. The bridge makes none at all: it accepts a loopback connection and originates
nothing.

This became a decision rather than an accident when FR 024 added two tools whose entire subject is
addresses. **A tool may hand out a URL; it may not retrieve one.** Retrieving is the MCP client's
job, and the client is where the capability, the credentials and the user's consent already live.
Three things follow:

- **A tool that returns addresses returns them as data**, with enough beside each one — a title, a
  sentence, keywords — that a caller can choose without fetching to find out.
- **Vendored reference data is checked against a local source or not at all.** `reference/urls.py`
  is a copy of a file in the mpfb2 repository and `reference/docs.py` names paths in it; both drift,
  and neither may be validated by asking the network. What checks them is a test that reads a
  sibling checkout when there is one — see
  [testing.md](testing.md#a-test-may-depend-on-a-sibling-checkout-if-it-skips-without-one).
- **A degraded answer is still an answer.** A links tool that fails when its source is unreachable
  is useless in the one situation where the download link is what was wanted, so the fallback is
  part of the design rather than an error path.

**And a tool need not cross the socket at all.** `mpfb_list_docs` is a local table with a URL rule
over it: no payload, no generated code, no Blender, no MPFB. That is a legitimate shape for a tool
here and not a sign that something belongs elsewhere — the test is whether an agent driving MPFB
needs the answer, not whether the answer comes from Blender. It is the one tool for which the
`tools/<name>.py` / `payloads/<name>.py` / `tests/test_<name>.py` naming rule does not hold, and
the omission is stated where the payload list is kept rather than left to be read as a gap. It is
also the one tool the pivot does not touch, since it has nothing to migrate.

`mpfb_list_urls` sits between the two: it crosses the socket when it can, and answers from the
vendored copy when it cannot. It is the only tool that catches `ConnectionError` from the wire —
see
[a tool may answer from more than one source](responses.md#a-response-says-which-source-answered-it)
for what that obliges it to report, and note that the catch belongs in the tool module. Every
other tool depends on a connection failure being an error envelope, and this is one tool's
exception rather than a change to the wire layer. It survives the pivot unchanged in substance:
the download link is the answer precisely when nothing is running, and that is as true of an
unreachable bridge as of an unreachable blender_mcp.

## Supporting a second backend

**This seam was designed for a different second backend and was spent on the bridge instead.** The
original plan was an adapter that let mpfb-mcp drive the community
[blender-mcp](https://github.com/ahujasid/blender-mcp) add-on as well as blender lab's; that goal
is superseded (see
[vision.md](vision.md#superseded-which-blender-mcp-neither-in-the-end)), because once no program
crosses the socket there is no third-party add-on in the path to abstract over. What the analysis
established about *where the seam goes* carried forward unchanged, and
[FR 030](../feature-requests/done/030-backend-seam/README.md) built it:
`src/mpfbmcp/backend.py` is the seam and `src/mpfbmcp/bridge_connection.py` is the bridge's wire
client.

- **The seam is an adapter *below* the send, not a second connection module each tool picks
  between.** Backend choice is not visible above the socket boundary: tools stay unchanged, and
  [Response shape](responses.md#response-shape)'s rule that a tool returns the envelope it was
  given holds on both. If supporting a backend requires editing a tool, the seam is in the wrong
  place — the same test
  [Diagnostics attach at the socket boundary](observability.md#diagnostics-attach-at-the-socket-boundary-never-to-the-program)
  applies to observability. **The bridge is a backend behind exactly this seam**: a migrated tool
  sends a command and arguments instead of a program, `codegen/` is bypassed for it, and no tool
  module learns which transport it is talking to. A tool calls `backend.send()` with what it was
  already handing to `codegen.assemble()` — the payload's filename, its parameters, its bootstrap —
  and **the same parameters reach both sides, unreshaped**. There is deliberately no escape hatch
  for a tool whose two paths would want different ones; if one ever needs that, it is a design
  problem to surface in that tool's own effort rather than a flexibility to carry unused.
- **Backend selection is explicit configuration, never autodetection.** `MPFB_MCP_BACKEND` is
  `blender_mcp` (the default) or `bridge`, and `MPFB_BRIDGE_HOST` / `MPFB_BRIDGE_PORT` give the
  bridge's address. Both third-party add-ons default to port 9876 and the bridge answers on 9877,
  so the address distinguishes nothing reliably, and no single probe distinguishes them either — a
  NUL-terminated ping leaves the community add-on's parser waiting for the rest of a message, while
  an unterminated one leaves blender lab's doing the same. **An unrecognised backend name is an
  error, not a silent fallback**: a typo that quietly leaves every call on the old path is
  indistinguishable from the bridge not working, which is the most expensive shape a configuration
  mistake can take.
- **One table is the migration's progress bar.** The seam holds the payload-to-command mapping in
  one readable file. A tool in it goes over the configured transport; a tool not in it goes over the
  generated path in *both* configurations, because there is nothing else it could do. The last
  stage of the pivot deletes the table by emptying it.
- **The default configuration is the working system.** Somebody who upgrades and sets no variable
  must not be able to tell the seam exists. That is what replaces the reversibility the two
  preceding efforts could offer and this one could not: FR 030 is the first stage that changed
  `src/mpfbmcp/`, so `bridge/` is no longer removable without consequence.
- **Observability keeps its attachment point and changes its unit.** The per-call record hangs off
  the send and nowhere else, which does not change; what it records stops being a program and
  becomes a command and its parameters. See
  [observability.md](observability.md#diagnostics-attach-at-the-socket-boundary-never-to-the-program).

<a id="resolving-mpfb-from-generated-code"></a>

## Resolving MPFB

MPFB is a Blender *extension* with no stable, guessable absolute import path — the top-level
package name depends on which extension repository the user installed it from (e.g.
`bl_ext.user_default.mpfb`, `bl_ext.repo.mpfb`). Code that needs MPFB must never hardcode a guessed
path. Instead it uses the resolution mechanism MPFB itself documents and uses in its own test
suite (`mpfb2/src/mpfb/__init__.py`, `mpfb2/test/tests/__init__.py`): scan `sys.modules` for a
module whose name ends in `"mpfb"`, then read the classes it needs off the
`MPFB_CONTEXTUAL_INFORMATION["SERVICES"]` dict that module publishes.

**This section survives the pivot and matters more, not less.** It was written for generated code
and applies unchanged to the bridge, which has the same problem from the same position: a
companion add-on reaching another add-on, with no import path it may assume. Everything below is
binding on both, and the bridge must not invent a second resolution strategy any more than a
payload may.

One trap belongs to the bridge specifically. The scan matches names ending in `"mpfb"`, and the
bridge's own package is `mpfb_bridge` — which does **not** match, but is close enough that a
rename could break it silently, and the failure mode is the bridge cheerfully reporting itself as
a working MPFB. That is asserted in the bridge's own tests rather than left to inspection.

### Resolution is two steps, not one

Finding such a module says nothing about whether it is *usable*. MPFB declares
`MPFB_CONTEXTUAL_INFORMATION = None` at module level and only builds it inside `register()`,
assigning the `"SERVICES"` entry on that function's very last line; `unregister()` never resets
it. So the scan and the services check are separate questions, and must be treated separately:

1. **Is a module whose name ends in `"mpfb"` loaded?** If not, MPFB is not installed, or was
   never imported.
2. **Has that module completed `register()`?** If `MPFB_CONTEXTUAL_INFORMATION` is `None`, or is
   a dict without a `"SERVICES"` key, MPFB is installed but broken or half-registered — a state
   an unwary bootstrap surfaces as a bare `TypeError`/`KeyError`.

Two further consequences. The scan can match **more than one** module, meaning MPFB is installed
under two extension repositories (or a stale legacy addon lingers beside an extension install);
which one is picked is then arbitrary, so anything reporting on the install should report all
candidates rather than only the winner. And a *disabled* MPFB still passes both steps, since
`unregister()` leaves the dict populated in `sys.modules` — only
`bpy.context.preferences.addons` distinguishes it from a live one.

### Two bootstrap variants

The same two-step resolution serves two needs, so the logic exists once and the *reaction* to
failure differs:

- **Raising** — for anything that cannot do its job without MPFB anyway (e.g.
  `mpfb_create_human`). Fails with a `RuntimeError` naming the likely cause, distinguishing "not
  loaded" from "loaded but not initialized", and pointing at `mpfb_get_status`.
- **Non-raising** — for anything whose job is partly *to answer* whether MPFB is present (e.g.
  `mpfb_get_status`). Classifies the situation instead of failing, so absence and partial
  initialization come back as ordinary successful answers.

On the generated-code path these are two bootstrap fragments prepended to a payload. On the bridge
they are one resolver returning a state, and the caller decides — but the distinction is the same
one and for the same reason, and a bridge command whose whole purpose is to report on a broken
MPFB must not need a working MPFB to say so. That is why the bridge's logger is its own rather
than MPFB's `LogService`: the idiom is copied, the dependency is not.

### Never import MPFB submodules directly

Services are resolved **only** through the `SERVICES` dict. Reaching a service by importing its
module (`importlib.import_module(package + ".services.locationservice")`) is tempting when the dict
is unavailable, but several MPFB modules have import-time side effects —
`locationservice.py` ends with `LocationService = _LocationService()` followed by
`LocationService.ensure_relevant_directories_exist()`, which **creates directories on disk**.
Code that did this to work around a missing `SERVICES` dict would be writing to disk in
exactly the state where MPFB is already broken. When the services are unavailable, report only
what is readable off the module object itself (`VERSION`, `BUILD_INFO`, `__name__`) and from
`bpy`.

**The bridge does not get an exemption from this**, and the temptation there is sharper. Being an
add-on rather than a generated string, it *could* import an MPFB submodule — including the UI
operator module that `mpfb_set_asset_material` reimplements from services because importing it is
forbidden. The reasons not to are unchanged and the worst case is unchanged: a UI operator module
is the least stable thing in MPFB to depend on, and the import-time side effects are still there.

### Reading module-level names MPFB does not publish

Not everything needed is in the `SERVICES` dict. MPFB keeps some constants and some
entities at module level: `LOWEST_FUNCTIONAL_BLENDER_VERSION` in `systemservice.py`, the object
type vocabulary `_ALL_TYPES` / `_MESH_ASSET_TYPES` / `_SKELETON_TYPES` in `objectservice.py`, and
the `BlenderConfigSet` entities `GeneralObjectProperties` and `HumanObjectProperties`, which are
how custom properties such as `object_type`, `asset_source` and `material_source` are actually
read. These are reachable, under three rules:

- **Through a service's module, never a fresh import.** `sys.modules[SomeService.__module__]` is
  necessarily populated once that service resolved out of `SERVICES`, and reading it re-executes
  nothing — which is what keeps
  [Never import MPFB submodules directly](#never-import-mpfb-submodules-directly) intact. Pick a
  service whose module actually imports the name: `GeneralObjectProperties` is on
  `ObjectService`'s module, while `HumanObjectProperties` is not, and is on `HumanService`'s.
- **Always with a fallback.** These names are underscore-private or merely undocumented, and MPFB
  may rename them without notice. Read them with `getattr(module, name, default)` and degrade —
  a stale local copy of the type vocabulary is a better answer than a failed call.
- **Never as a substitute for a service.** If what is wanted is in `SERVICES`, take it from there.

The bridge may do these reads **once, at the point it resolves MPFB**, rather than on every call —
which is a genuine simplification the pivot buys, since a payload has no way to remember anything
between calls. The three rules are unchanged; only their frequency is.

#### A UI module with no service behind it

The three rules above are written around a *service's* module, because that is where every such
name lived until FR 024. `mpfb/ui/weburls.py` is not one: it is a UI module holding eleven string
constants, with no service on it and nothing in `SERVICES` that would drag it in. The rules still
apply, and the first of them is reached differently — `sys.modules.get("<root>.ui.weburls")`,
where the root comes from the module scan already done. **Not `importlib.import_module`**: MPFB
imports its UI during `register()`, so on an initialized install the module is already there and
reading it re-executes nothing, while importing it would run MPFB code inside an install that may
be exactly as broken as the tool was called to report on. A miss is therefore an ordinary answer
carrying a reason, not a case to fix by importing.

**Two conditions make a UI module readable, and `weburls` is the only one so far that meets
both.** It must be reachable without importing it — which means MPFB must already import it on a
normal install, a claim a stub cannot make and
[a live check has to](testing.md#what-the-suite-can-never-establish); FR 024's found it loaded
along with 308 other UI modules. And it must hold **data rather than a snapshot**: eleven string
literals with no computation at import time, so there is nothing in it that can be stale.

That second condition is what separates it from `ui/model/_modelsubpanels.py`, which
`mpfb_set_targets` deliberately does *not* read
([why](mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not)):
that module builds its table when Blender starts, so a tool reading it would be blind to a target
installed since. Reading a UI module is not a general licence — it is available where the module
is a constant table, and the fallback the second rule already required is what makes being wrong
about that survivable.

## The generated-code path: what runs today, and is being retired

**Everything in this part describes the machine that twenty-four of the twenty-five tools use,
and that all twenty-five use in the default configuration.** It is not historical and it is not
aspirational; it is what executes when a tool is called today. The exception is
`mpfb_list_objects`, which has a bridge command as well and takes it when the bridge is the
configured backend ([Supporting a second backend](#supporting-a-second-backend)) — its payload and
that command are maintained side by side until the generated path is retired, because they are the
two halves of the comparison that says the bridge answers the same. It is also what
[FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md) decided to replace, and it will
be deleted — `codegen/`, the session source cache and the shared fragments together — by the child
effort that migrates the last tool. Until then it is maintained, and a change to a tool that has
not moved belongs here.

A tool assembles a Python program in a fixed order — bootstrap, parameter prelude, optional shared
fragments, payload — and sends it to blender lab's `blender_mcp` add-on, which `exec()`s it inside
Blender and serializes back the `result` dict left in the exec namespace.

### What a call costs is the size of its program

**The add-on reads one 4 KB chunk of the request per timer tick, and does nothing else with that
tick.** A generated program therefore costs about **250 ms per 4 KB** against a Blender that has
been talked to in the last five seconds, and about **1 s per 4 KB** against one that has not —
because blender_mcp drops to a one-second tick after five seconds without a request *finishing*,
and bytes arriving do not count as work. A 50 KB program costs 3 s or 12 s, and it makes no
difference at all what the program computes. Measured, and predicted to within a few percent, by
[FR 013](../feature-requests/done/013-live-verification/README.md)'s cost measurements, and
consistent with [FR 023](../feature-requests/done/023-verification-smoke-test/README.md)'s smoke
run, whose three slowest items are its three largest programs.

Three consequences, and they are not small:

- **"The round trip is 250 ms" is wrong**, and four decisions in this package were argued against
  it. It is one *tick*. The empty program that produced the figure was one chunk long. The
  correction does not overturn those decisions —
  [FR 013](../feature-requests/done/013-live-verification/review.md) re-derived them on the real
  numbers — but it changes what the number is a measure of.
- **The prose in generated code is not free.** It is the price of
  [Readability and developer experience are prioritized](#readability-and-developer-experience-are-prioritized),
  and that requirement stands: a payload is code the next developer reads, and the diagnostic
  record [FR 012](../feature-requests/done/012-observability/README.md) keeps is only worth keeping
  because it is legible. But the price is known rather than assumed, and "this explanation is
  worth 250 ms on every call that carries it" is the question to ask of a paragraph in a payload.
- **Not sending something beats not doing it.** MPFB's modeling category table is the case that
  established this. It was assumed to be the package's largest avoidable cost because three tools
  rebuild it on every call; measured inside Blender, the rebuild takes **4 ms**, and the 18 KB of
  generated code that describes how to do it takes **1.1 s busy, 4.4 s idle** to arrive. The saving
  was never in the scan. See
  [Generated code may keep its own source inside Blender](#generated-code-may-keep-its-own-source-inside-blender).

**This section is the clearest single argument for the pivot.** The cost is a property of sending
a program at all, so no amount of trimming payloads removes it — the bridge does, by sending
parameters. The 4 KB chunk is a defect in blender_mcp rather than a law of nature: its
`_service_clients()` reads once per tick instead of draining the socket, and a loop there would
remove most of the cost from every tool in this package. It is not fixed here, because blender_mcp
is treated as external and unmodified, and once the migration completes it stops being this
project's problem at all — but it remains worth filing upstream for everyone else, which is the
entry
[in NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md#handle-the-4-kb-chunked-read-against-blender_mcp).

### Code-generation layout

This is what "adding a tool means adding files, not editing shared ones" amounts to concretely.

- **One payload per tool, as an ordinary `.py` file.** `codegen/payloads/<tool>.py`, named for its
  tool module, read as a package resource and never imported here — payloads reference `bpy` and
  MPFB's services, which do not exist on this side of the socket. Having no `__init__.py` is what
  keeps them out of package discovery, and `pyproject.toml` therefore has to ship them as package
  *data* and set `namespaces = false` so discovery does not sweep them up as namespace packages.
- **A payload is a real file so that it can be read like one.** Syntax highlighting, editor
  indentation and a linter that mostly applies are the point; a payload written as an escaped
  string literal would fail
  [Readability and developer experience are prioritized](#readability-and-developer-experience-are-prioritized)
  however well it worked, because it is the form the next developer copies. The price is that
  names bound by the assembler — `PARAMS`, `_MPFB_SERVICES`, `sys` — look undefined to a linter,
  so **each payload's docstring names them**.
- **One entry point, and a fixed order.** `codegen.assemble("<tool>.py", bootstrap=..., params=...,
  shared=[...])` concatenates bootstrap, parameter prelude, fragments, payload. Fragments come
  after the prelude so a fragment may read `PARAMS`, and before the payload so the payload can call
  the fragment's functions.
- **Adding a tool touches exactly three things**: a module in `tools/`, a payload in
  `codegen/payloads/`, and one `register()` call in `__init__.py`. No shared code-generation module
  is edited — a tool that wants a fragment names it in the `assemble()` call it was already making.
  **If a change to shared code is needed to add an ordinary tool, the layout has drifted.**
- **The bootstrap is the one shared part still written as a string**, because it is what runs
  before anything else has been arranged.

The bridge keeps the requirement and drops the mechanism: a new command is a handler function and
one line in the command table, with no assembly step at all.

### Generated code may keep its own source inside Blender

The add-on `exec()`s each request in a **fresh namespace**, so nothing a program binds survives it.
Generated code may nevertheless create a module of its own in `sys.modules` and keep things there —
and what it keeps is **the source of shared fragments, never what they computed**.

That distinction is the whole safety argument, and it is what makes the mechanism boring rather
than delicate:

- **A cache of code keyed by a hash of that code cannot be stale.** A cache of *answers* about the
  disk can, and the answer in question is the table that decides which shape key a modifier is
  written to. The fragment still runs on every call, so `mpfb_list_targets` still sees a target
  installed since Blender started — which MPFB's own panels cannot — and no tool needs a `refresh`
  argument for a cache that has nothing to go stale about.
- **It is our module, named as ours.** `mpfb_mcp_session_state`, created by the loader, holding
  nothing that is not rebuilt by sending a fragment again. Never an attribute grafted onto one of
  MPFB's modules, which is the read-only arrangement in
  [Reading module-level names MPFB does not publish](#reading-module-level-names-mpfb-does-not-publish)
  turned into a write.
- **Never on a datablock.** A scene or object custom property would reach the user's `.blend`, would
  set `bpy.data.is_dirty`, and would outlive the Blender session it describes.
- **Two servers against one Blender are safe by construction.** The key is `<file>@<hash>`, so two
  copies of a fragment are two entries; identical code shares a cache and different code never
  does, without either side knowing the other exists.
- **A fragment Blender does not hold is a request, not a failure.** The program that reuses a
  fragment is by definition not the program that carries it — carrying it is the cost being
  avoided — so the loader raises with a marker the tool side matches, and the tool re-sends with the
  source in it. Once, never twice: a second miss means the cache is not being written at all, and
  that error is more use to a caller than a loop. The handshake is visible in the record as an
  error envelope, which is honest — a call really did cross the socket and come back with nothing.
- **The source is embedded as readable Python, not as data.** A raw triple-quoted literal rather
  than a JSON string, so the program on disk in
  [FR 012](../feature-requests/done/012-observability/README.md)'s record is still something a
  developer can read, and so a traceback from inside a fragment reports that fragment's own name and
  line rather than an offset into the whole program — which is better than what concatenation gave.
  It costs two constraints on every fragment, both asserted rather than assumed: no `'''` in the
  source, and no trailing backslash.

**This mechanism exists only to manage the cost of sending a program**, and it is therefore the
clearest example of machinery the bridge makes unnecessary. It goes when `codegen/` goes.

### Shared fragments

A **fragment** is a fourth, optional part: an ordinary `.py` file under
`src/mpfbmcp/codegen/shared/`, named by a tool module in `assemble(..., shared=[...])` and
concatenated between the prelude and the payload. It exists for a *concept* two or more payloads
model identically. There are seven: `target_categories.py` rebuilds MPFB's `target.json` category
table, which `mpfb_list_targets`, `mpfb_get_target_stack`, `mpfb_set_targets` and
`mpfb_symmetrize_targets` all need in the same shape and none of them can import; `rig_lookup.py` answers "which rig file would MPFB
load for this identifier, and whose weights would come with it", which `mpfb_list_rigs` and
`mpfb_add_rig` need to answer *identically*; `asset_sections.py` holds MPFB's
`ASSET_LIBRARY_SECTIONS` table and what it maps between, which `mpfb_list_assets` reports *from* and
`mpfb_add_asset` resolves *with*; `performed.py` stamps the uniform
[`performed` flag](mutating-tools.md#the-flag-a-caller-branches-on-is-called-performed) onto the
answer of every one of the thirteen mutating payloads; `modifier_reading.py` computes what one
modeling category's slider reads, which `mpfb_get_target_stack` reports and
`mpfb_symmetrize_targets` acts on; `refit_blocker.py` answers whether `HumanService.refit()`
would silently leave the rig behind, which all four refitting payloads have to know; and
`preset_files.py` holds which characters a preset name may contain and how it becomes
`<user config>/human.<name>.json`, which `mpfb_list_presets`, `mpfb_save_preset` and
`mpfb_create_human_from_preset` must agree about exactly — two of them disagreeing would let a
preset be written under a name that cannot be loaded back.

`preset_files.py` is also the one fragment whose rule exists on **both** sides of the socket, which
is a shape to notice rather than to copy. The authoritative check is in `src/mpfbmcp/preset_names.py`
and runs before the program is built, because a name that becomes a path is a shape knowable here
([validate before crossing the socket](tool-interface.md#validate-before-crossing-the-socket)); the
fragment restates it as the last statement before `open()`. Two copies are warranted only because
the tool side cannot reach Blender at all and the consequence of a gap between them is silent, so
`tests/test_codegen.py` runs both over one table of names and compares the *sentences*, not only
the verdicts. A module of this package rather than a helper duplicated in two tool modules, which
is what the other small validators are: what separates the two cases is what a disagreement would
cost. **Note that this shape does not go away with the pivot** — it is the same duplication
[Both ends validate, deliberately](#both-ends-validate-deliberately) describes, and the bridge
inherits it for the same reason.

- **A fragment is warranted by duplication that must not drift, not by size.** Three copies of a
  hundred-line scan of the user's target directories are three chances for two tools to disagree
  about what is installed, and that disagreement is worse than either behavior on its own. Two
  payloads sharing a five-line helper are not a reason to reach for this.
- **Where a catalogue tool predicts what an acting tool will do, the prediction and the action are
  one implementation.** This is the sharper form of the rule above, and `rig_lookup.py` is the
  case: `mpfb_list_rigs` reports, per rig, which weights file adding it would load, and
  `mpfb_add_rig` then reports which one it did load. A caller who reads the catalogue and acts on
  it is entitled to get back what the catalogue promised. The overlap is about ten lines — small
  enough that duplication would be defensible on size alone, and not defensible at all on
  consequence: MPFB resolves weights through a *fallback table*, so `default_no_toes` legitimately
  loads `default`'s weights, and two implementations that disagree about that would make an
  ordinary rig look broken in one tool and fine in the other.
- **The same rule covers a catalogue's *vocabulary*, not only its predictions.**
  `asset_sections.py` is that case, and the consequence is sharper still: `mpfb_list_assets` reports
  an asset's `object_type` and its portable `fragment`, and `mpfb_add_asset` has to map the first
  back to an asset subdir before it can resolve the second, because
  `AssetService.find_asset_absolute_path()` takes a subdir rather than a type. Two copies of that
  table disagreeing would not produce a wrong answer — it would produce "not installed" for an asset
  the catalogue had just listed, which is the one failure a caller cannot diagnose.
- **A convention eleven payloads must agree about is the same case as a table three must.**
  `performed.py` is the smallest fragment by far — one function, no MPFB, nothing read from the
  bootstrap — and it clears the bar on consequence rather than size, like `rig_lookup.py`: the whole
  reason the flag exists is that eleven tools disagreed about what to call it, so eleven
  implementations of it would be the original problem in a new spelling. It also has no
  dependencies, which is what lets it be concatenated ahead of any payload without pulling anything
  in with it.
- **Where two tools report and act on one number, the number has one implementation.**
  `modifier_reading.py` is that case. A modeling category's slider value is computed from one or two
  shape keys, and an opposed category's negative target reads back *negated*; `mpfb_get_target_stack`
  reports that number and `mpfb_symmetrize_targets` decides what to copy from it. Two
  implementations disagreeing would not look like a bug in either tool — it would look like a
  character that is symmetric in one and asymmetric in the other, with nothing in either answer to
  say which to believe. The reconciliation is worth noting because the two copies differed in
  *shape* and not merely in text: one answered from a snapshot read once, the other from `key_blocks`
  on every question, because it writes between readings. What is shared is the rule; the pair of
  lookups is passed in, and the difference between them is stated where it is decided.
- **A fragment may share the condition and leave the wording alone.** `refit_blocker.py` is that
  case: `HumanService.refit()` cannot refit a generated Rigify rig with no meta rig left in the
  scene, reports it only through an `operator` no MCP tool has one of, and returns having refitted
  the mesh assets. Four payloads must detect that or claim a refit they did not perform — but
  `mpfb_refit_human` reports one that has already happened and the other three predict one they are
  about to attempt, so the sentences differ by tense and both are right for their call site. The
  fragment therefore exposes a predicate and each payload keeps a `rig_refit_blocker()` of its own
  that phrases the answer. Four copies of the condition is the `rig_lookup.py` failure exactly; four
  copies of the message is at worst four sentences that read slightly differently.
- **Being identical is not by itself a reason to merge.** A census of every function defined at
  module level in more than one payload — docstrings stripped, normalised through `ast.unparse` —
  found nineteen such names, of which sixteen were byte-identical and had not drifted at all. Only
  the two above were made into fragments. `blocked()`'s six variants were left alone deliberately:
  they are one convention applied six times, differing only in which of that tool's own fields each
  nulls out, and a mechanism for "this tool's null response" would be larger than the six copies.
  **"Have these drifted?" is asserted in [tests/test_codegen.py](../tests/test_codegen.py)**, on
  every unit run and with no Blender — for the two fragments where a second implementation would
  go wrong quietly rather than loudly: `refit_blocker.py` and `modifier_reading.py` each have a
  check that no payload using them keeps an implementation of its own. The other four are not
  covered that way, and a fragment added later should bring such a check with it.
- **Opting in is the payload's business, not the assembler's.** `assemble()` takes the list — as
  does `shared_cache.send()`, which is `assemble()` plus the decision about carrying the source —
  and there is no table anywhere mapping payloads to fragments. So the rule above still holds
  unchanged: adding an ordinary tool is still a tool module, a payload and a `register()` call, and
  a tool that wants a fragment names it in the call it was already making.
- **Fragments come after the prelude**, so a fragment may read `PARAMS`, and before the payload, so
  the payload can simply call the fragment's functions.
- **A fragment may be sent once per Blender session rather than once per call**, and which of the
  two a given call does is the tool's business rather than the fragment's: the file is identical
  either way, it is executed into the program's own globals either way, and a payload cannot tell
  the difference. What decides it is a memo of what this process has already sent to this address —
  see [Generated code may keep its own source inside Blender](#generated-code-may-keep-its-own-source-inside-blender)
  for why, and for what makes it safe.
- **Each fragment gets its own labelled seam**, `# --- shared: <name> ---` or
  `# --- cached shared: <name>@<hash> (carried|reused) ---`, for the same reason the payload does —
  and the second form additionally says, in the record, which of the two this call paid for.
- **Packaging has to be told about the directory separately.** A package-data glob does not
  descend, so `payloads/*.py` ships nothing from a subdirectory of `payloads/` — which is why
  fragments live in a sibling directory with a glob of their own rather than under `payloads/`.

**What a fragment becomes after the pivot** is worth stating, because it is the part of the
migration most likely to be under-estimated. A concept two payloads model identically becomes a
module two commands import — which is what a fragment was always trying to be, and is the reason
the seven of them are the clearest map of what the bridge's shared code should look like.

## One module per tool

Each MCP tool lives in its own module exposing a `register(mcp)` function that attaches the
tool to the passed `FastMCP` instance. This keeps tools independently testable and keeps the
server's own `main()` a flat list of `register()` calls. It is unaffected by the pivot: what
changes is what a tool module *does* below its validation, not how it is registered.
