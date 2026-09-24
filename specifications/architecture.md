# Architecture

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).
>
> **There is one machine, and this document describes it.** It was two:
> [FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md) decided that MPFB's
> Blender-side logic belonged in an add-on of our own rather than in Python assembled here and
> sent to a third party's add-on to be executed, and
> [FR 033](../feature-requests/done/033-retire-the-generated-code-path/README.md) deleted the
> older one. What that path was, what it cost and what it taught is in
> [HISTORY.md](../feature-requests/HISTORY.md), not here: a standing specification describes what
> runs.

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

**Code that runs inside Blender is code**, wherever it is written. The rule began as one about
Python this package assembled and sent into Blender: it had to be editable as ordinary Python, in
its own file, with syntax highlighting, working editor indentation and a linter that mostly
applies, because that is the form the next developer copies. It outlived that machine and is
easier to keep now that add-on code *is* ordinary Python in an ordinary add-on. What it stopped
being is a trade against the wire: an explanation used to cost roughly 250 ms per 4 KB on every
call that carried it, and prose in an add-on is not sent anywhere.

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
tool edits a module that all the other tools depend on does not scale past a handful of them.
Concretely: a new tool is a module in `tools/`, one `register()` call, a module in
`bridge/mpfb_bridge/commands/`, and one line in `commands/table.py`. Nothing shared is edited, and
if a change to shared code is needed to add an ordinary tool, the layout has drifted.

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
  one-chunk-per-tick read cost this project about 250 ms per 4 KB of request for its whole first
  year — [what that was and how it was measured](../feature-requests/HISTORY.md#fr-033--the-generated-code-path-retired).
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
which makes it a claim about what *this process* learned rather than about what is running, and
wrong in the ordinary way when Blender restarts under it, so a connection failure drops it. And **the
probe is issued through the wire client directly, never through the seam**, or the first call in a
process would probe in order to probe. A bridge that answers but reports no version is talked to
anyway: a handshake exists to catch a mismatch, not to invent one.

**`get_status` and `get_mpfb_status` are two commands about two different pieces of software**,
and the names are the resolution of a collision rather than an accident. `get_status` reports *the
bridge* — its version, the protocol it speaks, and the state of MPFB as the add-on sees it — and
is what the handshake probes. `get_mpfb_status` reports *MPFB*, in three tiers including asset
roots and configured paths, and is what `mpfb_get_status` became when
[FR 031](../feature-requests/done/031-introspection-and-catalogues-migrated/README.md) migrated it.

This is the **one** place where a tool's command is not named after the tool, and the exception is
deliberate: two commands answering "status" about two different things is a collision that is
cheap to avoid while there is one caller and permanent once there are several. It is written into
`backend.send()`'s docstring, into `commands/table.py` beside the entry, and into each command's
`list_commands` summary, so that a reader meeting either one learns which is which without finding
this paragraph. Both declare `requires_mpfb=False`, for the same reason: a status
command gated on the thing it reports about answers only the question nobody needs to ask.

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

**Both halves of the handshake exist**: the bridge's, above, and the client's, in
[the wire](#the-wire). One number is duplicated across the two — `PROTOCOL_VERSION`, which
`bridge_connection` declares and the add-on serves — and it is kept in step by hand because
`bridge/` is a Blender extension that imports `bpy`, so making the pip package depend on it would
undo [no direct dependency](#no-direct-dependency-on-mpfb-and-none-on-the-add-on-either). A unit test reads the add-on's
source and asserts the two agree, skipping where that source is not beside the package. The
bridge's own version is reported too, and must equal the `version` in `blender_manifest.toml` —
kept in step by hand, since nothing in the extension format publishes one to the other, and
asserted by a test rather than by a comment.

## No direct dependency on MPFB, and none on the add-on either

mpfb-mcp never imports MPFB Python code directly, and is never run *inside* Blender. Every
interaction with MPFB crosses two boundaries:

1. mpfb-mcp → the bridge add-on, over a TCP socket. **mpfb-mcp does not import the add-on
   either**, though both live in this repository: `bridge/` is a Blender extension whose modules
   import `bpy`, so importing one would pull Blender into a process that has none. The wire client
   is therefore standalone, and the protocol version it declares is a hand-kept duplicate of the
   add-on's — the one place the two halves have to be changed together, and the one a test reads
   the add-on's source to check.
2. The add-on → MPFB, inside the Blender process, by calling ordinary add-on code.

**The consequence that shapes everything else is a testing one.** Because MPFB is reachable only
from inside Blender, mpfb-mcp's own suite can verify the wire protocol, the seam and what a tool
decides before sending, and nothing beyond it; anything that depends on what MPFB actually does is
checked against a real MPFB in the bridge's own suite, which runs inside a headless Blender. That
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
over it: no command, no Blender, no MPFB. That is a legitimate shape for a tool here and not a sign
that something belongs elsewhere — the test is whether an agent driving MPFB needs the answer, not
whether the answer comes from Blender. It is the one tool for which the `tools/<name>.py` /
`commands/<name>.py` / `tests/test_<name>.py` naming rule does not hold, and the omission is
stated in [CLAUDE.md](../CLAUDE.md#the-twenty-five-tools) rather than left to be read as a gap.

`mpfb_list_urls` sits between the two: it crosses the socket when it can, and answers from the
vendored copy when it cannot. It is the only tool that catches `ConnectionError` from the wire —
see
[a tool may answer from more than one source](responses.md#a-response-says-which-source-answered-it)
for what that obliges it to report, and note that the catch belongs in the tool module. Every
other tool depends on a connection failure being an error envelope, and this is one tool's
exception rather than a change to the wire layer. The reason is unchanged whatever is on the other
end of the socket: the download link is the answer precisely when nothing is running.

## Supporting a second backend

**This seam was designed for a different second backend, was spent on the bridge, and now has one
transport under it.** The original plan was an adapter letting mpfb-mcp drive the community
[blender-mcp](https://github.com/ahujasid/blender-mcp) add-on as well as blender lab's; that goal
is superseded (see
[vision.md](vision.md#superseded-which-blender-mcp-neither-in-the-end)), because once no program
crosses the socket there is no third-party add-on in the path to abstract over. The section keeps
its name because what the analysis established was about *where a seam goes*, and that outlived
both backends it was argued over.

- **The seam is an adapter *below* the send, not a second connection module each tool picks
  between.** That is the decision, and it is why `backend.send()` survived the deletion of the
  thing it used to choose between: what a tool module contains is a description, an argument
  contract, local validation and one call, and what it must *not* contain is a protocol.
  Twenty-four modules importing the wire client directly would put the command name, the framing,
  the handshake and the address variables inside every tool, and the next change to any of them
  would be twenty-four edits made twenty-four times. If supporting a transport ever requires
  editing a tool, the seam is in the wrong place — the same test
  [Diagnostics attach at the socket boundary](observability.md#diagnostics-attach-at-the-socket-boundary-never-inside-blender)
  applies to observability.
- **The same parameters reach both sides, unreshaped.** A tool hands `backend.send()` a command
  name and the arguments it has already validated, and nothing between there and the wire
  rewrites them. There is deliberately no escape hatch for a tool that would want to send
  something other than what it was given; if one ever needs that, it is a design problem to
  surface in that tool's own effort rather than a flexibility to carry unused.
- **Backend selection was explicit configuration, never autodetection, and that mattered.**
  `MPFB_MCP_BACKEND` chose between the bridge and the generated path, an unrecognised value was an
  **error rather than a silent fallback**, and the default moved to the bridge only once every
  tool had a command and the two paths had been compared answer by answer *and scene by scene*
  against one Blender. The variable is read today for one purpose: a value left in somebody's
  client configuration gets one line on this package's logger saying it is no longer read.
  Obeyed by nothing and reported by nothing is the expensive option, and it is the same argument
  that made a typo an error while there were still two backends.
- **A second transport would be added the same way it was removed.** Nothing about the seam
  assumes there is one: `send()` is a function with a command name and a dict, and the thing that
  made two transports cheap was that no tool module ever learned which it was on. What made the
  *removal* cheap was the same property, which is the strongest thing that can be said for putting
  a seam where this one is.
- **Observability keeps its attachment point.** The per-call record hangs off the send and nowhere
  else. See
  [observability.md](observability.md#diagnostics-attach-at-the-socket-boundary-never-inside-blender).

<a id="resolving-mpfb-from-generated-code"></a>

## Resolving MPFB

MPFB is a Blender *extension* with no stable, guessable absolute import path — the top-level
package name depends on which extension repository the user installed it from (e.g.
`bl_ext.user_default.mpfb`, `bl_ext.repo.mpfb`). Code that needs MPFB must never hardcode a guessed
path. Instead it uses the resolution mechanism MPFB itself documents and uses in its own test
suite (`mpfb2/src/mpfb/__init__.py`, `mpfb2/test/tests/__init__.py`): scan `sys.modules` for a
module whose name ends in `"mpfb"`, then read the classes it needs off the
`MPFB_CONTEXTUAL_INFORMATION["SERVICES"]` dict that module publishes.

**This is binding on everything that reaches MPFB**, and the bridge has the problem in its
sharpest form: a companion add-on reaching another add-on, with no import path it may assume. It
must not invent a second resolution strategy. The rule was written for a machine that sent Python
into Blender and survived that machine's deletion unchanged, which is a fair sign it is about MPFB
rather than about a transport.

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

These are one resolver returning a state and a caller that decides, expressed in the command
table as `requires_mpfb`: a command declaring `True` is refused with `mpfb_unavailable` before its
handler runs, and one declaring `False` gets to answer. Three commands declare `False`, and each
is a case of the second kind — `get_status` reports the *add-on*, `list_commands` reports what it
can be asked to do, and `get_mpfb_status` and `list_urls` are most valuable exactly when MPFB is
broken. **A command whose whole purpose is to report on a broken MPFB must not need a working MPFB
to say so.** That is also why the bridge's logger is its own rather than MPFB's `LogService`: the
idiom is copied, the dependency is not.

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

**The bridge does not get an exemption from this**, and the temptation there is sharper than it
was for code that could not import anything at all. Being ordinary add-on code, it *could* import
an MPFB submodule — including the UI operator module that `mpfb_set_asset_material` reimplements
from services because importing it is forbidden. The reasons not to are unchanged and the worst
case is unchanged: a UI operator module is the least stable thing in MPFB to depend on, and the
import-time side effects are still there.

**FR 032 put that under real pressure for the first time and it held**, in the two places it could
have given way. `set_asset_material`'s command reimplements `_apply_mhmat()` and
`_find_default_material()` from services, with the operator module sitting one `import` away; and
`list_urls`' command reads `<root>.ui.weburls` out of `sys.modules` where an import would be
shorter. Both say so in their own docstrings rather than relying on a reader finding this page — the rule
predates an add-on that *could* reach those modules, and a rule whose circumstances have changed
is one that has to restate itself where it is being applied.

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

These reads may be done **once, at the point MPFB is resolved**, rather than on every call — a
genuine simplification of being an add-on, since code sent into Blender per call had no way to
remember anything between them. The three rules are unchanged; only their frequency is. What may
*not* be cached that way is anything derived from the disk: see the per-call category table in
`bridge/mpfb_bridge/shared/target_categories.py`, whose whole point is that a target installed
since Blender started is visible.

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

**Calling a UI module is a third case, and FR 027 is where it was decided.** MPFB's
expressions-library panel draws one slider per expression file, registered as a scene property
**once, when `ui/apply_assets/useexpression` is imported**; `write_slider_values()` in that module
syncs the sliders to a stack and `refresh_expression_sliders()` registers sliders for files that
appeared since. `mpfb_apply_expressions` and `mpfb_save_expression` call them, through
[`shared/expression_panel.py`](../bridge/mpfb_bridge/shared/expression_panel.py). That module is
*not* a constant table — its map is exactly the import-time snapshot the `_modelsubpanels` case
refuses to depend on — so the second condition above is not met, and what makes the call acceptable
is different:

- **MPFB itself does exactly this, from exactly these places.** Its preset loader calls
  `write_slider_values()` after writing a stack, and its composer's save operator calls
  `refresh_expression_sliders()` after writing a file. A command that changed the stack or the
  library *without* the call would be the one path in or out of MPFB that left its panel showing
  something the character does not have.
- **The snapshot is not read to answer anything.** Nothing a tool reports comes out of the slider
  map; the call is how the snapshot is *corrected*, which is the opposite of relying on it.
- **Every rule for reaching it still holds.** Found with `sys.modules.get("<root>.ui.apply_assets.useexpression")`,
  never imported — FR 027's live check found it loaded in both a windowed and a headless Blender; a
  miss is an ordinary answer; each call is wrapped the way MPFB wraps it, because MPFB treats a
  failure there as cosmetic; and the outcome is **reported**, as `panel_synced` with a
  `panel_sync_reason`, rather than left implicit.

This is not a general licence either. It covers calling a UI function whose only effect is on
MPFB's own UI state, where MPFB makes the same call after the same change.

## Shared modules, and what warrants one

`bridge/mpfb_bridge/shared/` holds the concepts two or more commands model identically. **Nothing
in it is reachable from the wire** — no handler, no `PARAMS`, no entry in `COMMANDS` — which is
what lets [commands/table.py](../bridge/mpfb_bridge/commands/table.py) go on being the one file a
sceptic reads to know everything this add-on can be asked to do.

There are thirteen, and the warrant for each is the same shape: **duplication that must not drift,
not size.** Three copies of a hundred-line scan of the user's target directories are three chances
for two commands to disagree about what is installed, and that disagreement is worse than either
behaviour on its own. Two commands sharing a five-line helper are not a reason to reach for this.

- **Where a catalogue predicts what an acting command will do, the prediction and the action are
  one implementation.** `rig_lookup.py` is the case: `mpfb_list_rigs` reports, per rig, which
  weights file adding it would load, and `mpfb_add_rig` then reports which one it did load. A
  caller who reads the catalogue and acts on it is entitled to get back what the catalogue
  promised. The overlap is about ten lines — small enough that duplication would be defensible on
  size alone, and not defensible at all on consequence: MPFB resolves weights through a *fallback
  table*, so `default_no_toes` legitimately loads `default`'s weights, and two implementations
  disagreeing about that would make an ordinary rig look broken in one tool and fine in the other.
- **The same rule covers a catalogue's *vocabulary*, not only its predictions.**
  `asset_sections.py` is that case, and the consequence is sharper still: `mpfb_list_assets`
  reports an asset's `object_type` and its portable `fragment`, and `mpfb_add_asset` has to map the
  first back to an asset subdir before it can resolve the second, because
  `AssetService.find_asset_absolute_path()` takes a subdir rather than a type. Two copies of that
  table disagreeing would not produce a wrong answer — it would produce "not installed" for an
  asset the catalogue had just listed, which is the one failure a caller cannot diagnose.
- **A convention thirteen commands must agree about is the same case as a table three must.**
  `performed.py` is the smallest by far — one function, reading nothing out of MPFB — and it
  clears the bar on consequence rather than size: the whole reason the
  [`performed` flag](mutating-tools.md#the-flag-a-caller-branches-on-is-called-performed) exists is
  that thirteen tools disagreed about what to call it, so thirteen implementations of it would be
  the original problem in a new spelling.
- **Where two commands report and act on one number, the number has one implementation.**
  `modifier_reading.py` is that case. A modeling category's slider value is computed from one or
  two shape keys, and an opposed category's negative target reads back *negated*;
  `mpfb_get_target_stack` reports that number and `mpfb_symmetrize_targets` decides what to copy
  from it. Two implementations disagreeing would not look like a bug in either tool — it would look
  like a character that is symmetric in one and asymmetric in the other, with nothing in either
  answer to say which to believe. What is shared is the rule; the pair of lookups is passed in,
  because one command answers from a snapshot read once and the other from `key_blocks` on every
  question, since it writes between readings.
- **`expression_divergence.py` is the same case for the face.** Whether the applied-expressions
  stack explains the live face is a comparison MPFB makes nowhere, and three commands report it:
  `mpfb_get_expression`, which exists to answer it; `mpfb_apply_expressions`, which names the
  composed units its rebuild destroyed; and `mpfb_set_face_units`, which says whether what it just
  composed is now at risk. One of them saying "nothing to lose" while another says "this will be
  discarded" is the failure; `ppp_mutating/expression_divergence_test.py` asks all three about one
  character. `mpfb_get_character_summary` reads through it as well, which makes four.
- **A summary and its detailed tool are one implementation.** `macro_reading.py`, `asset_info.py`
  and `target_rollup.py` share this one warrant, which is why it is stated once rather than three
  times. [FR 034](../feature-requests/done/034-character-summary/README.md) moved the reading of
  the phenotype out of `get_macro_details`, of what an object was made from and which objects
  belong with it out of `get_object_info`, and of the target stack and its rollup out of
  `get_target_stack`, so that `mpfb_get_character_summary` reports a subset of each answer under
  the same names **without a second reading**. The failure it prevents is the one a summary is
  most prone to: an agent that reads "no rig" in the summary and "rig `default`" from
  `mpfb_get_object_info` has been handed a contradiction it cannot resolve, and acts on whichever
  it read last. The basemesh resolution moved into `macro_reading.py` with the rest, because the
  summary promises to resolve its subject exactly as `mpfb_get_macro_details` does and one function
  is the only way that stays true; the other resolvers were not consolidated (see
  [NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md#one-basemesh-resolver)). The face-unit read was
  **not** moved: `get_face_units` reads straight off `FaceService` and the non-zero filter is one
  line, which is below the bar. `bridge/test/tests/uuu_get_character_summary_test.py` dispatches
  the summary beside each detailed command on one character and asserts every shared field equal —
  the test that keeps them agreeing after the reason is forgotten.
- **A shared module may share the condition and leave the wording alone.** `refit_blocker.py` is
  that case: `HumanService.refit()` cannot refit a generated Rigify rig with no meta rig left in
  the scene, reports it only through an `operator` no MCP tool has one of, and returns having
  refitted the mesh assets. Six commands must detect that or claim a refit they did not
  perform — `mpfb_refit_human`, the three body-shape writers, and since FR 026 and FR 027
  `mpfb_set_face_units` and `mpfb_apply_expressions` — but `mpfb_refit_human` reports one that has
  already happened and the others predict one they are about to attempt, so the sentences differ
  by tense and both are right for their call site. The module therefore exposes a predicate and
  each command phrases the answer. Six copies of the condition is the `rig_lookup.py` failure
  exactly; six copies of the message is at worst six sentences that read slightly differently.
- **`target_categories.py` is the largest and is rebuilt per call**, which is a rule about
  *freshness* rather than about sharing: `mpfb_list_targets`, `mpfb_get_target_stack`,
  `mpfb_set_targets` and `mpfb_symmetrize_targets` all need MPFB's `target.json` category table in
  the same shape, and a module-level scan would answer every request from a snapshot taken when
  Blender started — blind to a target installed since, which MPFB's own panels already are.
- **`artifact_names.py` is the one whose rule exists on both sides of the socket**, which is a
  shape to notice rather than to copy. The authoritative check is in `src/mpfbmcp/artifact_names.py`
  and runs before anything is sent, because a name that becomes a path is a shape knowable there
  ([validate before crossing the socket](tool-interface.md#validate-before-crossing-the-socket));
  this module restates it as the last statement before `open()`, because a listening socket is
  reachable by anything on the machine and not only by mpfb-mcp. Two copies are warranted only
  because the consequence of a gap is silent — a file written under a name that cannot be addressed
  back — so `tests/test_save_preset.py` runs both over one table of names and compares the
  *sentences*, not only the verdicts. It is the same duplication
  [Both ends validate, deliberately](#both-ends-validate-deliberately) describes, for the same
  reason. **It covers two artifacts, and the noun is its argument.** Until FR 027 the rule lived in
  `preset_names.py` and `preset_files.py` and said "preset"; saved expressions needed exactly the
  same rule for exactly the same reason, and copying it would have made four copies of something
  whose two-copy form is justified only by the cost of a gap. So it was generalised once on each
  side, the drift test runs every name as both nouns, and what stays per artifact is the path —
  `preset_files.py` keeps `human.<name>.json` in the config directory, and `save_expression`
  builds `<name>.json` in `user_data/expressions/`.
- **`expression_panel.py` is where two commands reach a UI module the same way.**
  `mpfb_apply_expressions` and `mpfb_save_expression` both keep MPFB's expressions-library panel in
  step (see [a UI module with no service behind it](#a-ui-module-with-no-service-behind-it)); how
  the module is found, what a miss means and what `panel_synced` reports must not differ between
  them, and the rules for reaching the module belong in one place a reader can check.

**Being identical is not by itself a reason to merge.** A census of every function defined at
module level in more than one of the programs these commands replaced — docstrings stripped,
normalised through `ast.unparse` — found nineteen such names, of which sixteen were byte-identical
and had not drifted at all. Only the ones above were made shared. `blocked()`'s six variants were
left alone deliberately: they are one convention applied six times, differing only in which of that
tool's own fields each nulls out, and a mechanism for "this tool's null response" would be larger
than the six copies.

**What the bootstrap used to bind above a fragment is a parameter here.** A shared module is
*handed* `services`, because a module that resolved MPFB at import would hold a services dict
across a disable and re-enable — the stale state `mpfb_resolution.resolve()` is called per dispatch
to avoid. `target_categories.py` takes a `tables` record for the freshness reason above.
`asset_info.py` takes a `Lookup` built from `services` once per call instead, because it also reads
four module-level names MPFB does not publish as services (two type vocabularies, two property
sets), and gathering them in one object keeps that `sys.modules` reach in one place.
Three take neither, because they read nothing out of MPFB's services: `performed.py` works on a
dict the command has finished building, `artifact_names.py` on a name and a path, and
`expression_panel.py` on MPFB's root package name, since the module it reaches is addressed by
where MPFB lives rather than by anything a service knows.

## One module per tool

Each MCP tool lives in its own module exposing a `register(mcp)` function that attaches the
tool to the passed `FastMCP` instance. This keeps tools independently testable and keeps the
server's own `main()` a flat list of `register()` calls. It was unaffected by the pivot, which is
itself worth noticing: what changed underneath was everything a tool module does below its
validation, and not one `register()` call moved.
