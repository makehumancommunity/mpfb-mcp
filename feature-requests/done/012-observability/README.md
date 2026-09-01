# Observability: seeing the program that was sent and the response that came back

**Status:** Done

Every tool in this package does the same three things: assemble a Python program, hand it to
`send_code()`, and return whatever comes off the wire. Nothing keeps the program afterwards, and
nothing records the response. When a call fails, what reaches the caller is the add-on's envelope —
often a traceback naming a line number in a program that no longer exists anywhere on this side of
the socket, and that was never written to disk on the other side either. Mapping that line back to
the file it came from is guesswork twice over: the assembled program is bootstrap, prelude, shared
fragments and payload concatenated in that order, so a payload's own line 40 lands somewhere near
line 300 of what actually ran, and the programs run from about 4 KB (`create_human.py`) to about
52 KB (`set_targets.py`).

There is no timing either. FR 005 measured a round trip at roughly one second, once, by hand, on one
tool — and four separate design decisions now cite that number: the refit-by-default in
`mpfb_set_macro_details`, the batching in `mpfb_set_targets`, one-asset-per-call in
`mpfb_add_asset`, and the deliberate retention of comments and docstrings inside generated programs.
None of them can be re-checked today without repeating the hand measurement.

This is the [Observability entry in NEXT_STEPS.md](../../NEXT_STEPS.md#observability), scoped whole. It
was previously scoped only as a subset, inside the live-verification request; it is pulled out here
because it is a change to the package rather than an instrument for one session, because it is
worth having whether or not that session happens, and because it should land *before* it, not
alongside it. [FR 013](../013-live-verification/README.md) depends on this request for its
diagnostics and for its cost measurements.

## Goals

**Primary: make a failed call diagnosable after the fact.** The exact string that was sent, the
exact envelope that came back, recoverable from disk without reproducing the failure. "Exact"
carries the weight here — a reconstruction is not good enough, because the only thing an add-on
traceback's line number can be resolved against is the real assembled source.

**Secondary: make the cost of a call measurable rather than narratable.** A wall-clock duration per
call, recorded next to the byte count of the program, so the four decisions above rest on a number
that can be taken again.

**Tertiary: give the package a conventional log.** Levels, one logger hierarchy, no handler
attached unless asked. This is the part of the NEXT_STEPS entry that is not about the socket at all,
and it is small, but leaving it out would mean the next person who wants to see what a tool decided
locally reaches for `print()` — which, on a stdio transport, breaks the server (see
[Architecture](#never-stdout)).

**Explicitly not a goal:** a telemetry pipeline, log rotation, aggregation, or anything that
uploads. The record is files in a directory the user named, read with a text editor.

## Functional requirements

### FR-1: A per-call record on disk

When enabled, each call through `send_code()` leaves:

- **the program**, byte-for-byte as handed to `send_code()`, in a `.py` file — written **before**
  the socket call, so a call that hangs, times out or takes Blender down still leaves behind the
  program that did it;
- **the response envelope**, in full, in a `.json` file beside it, written after the call returns.
  A call that raises `ConnectionError` instead of returning leaves no response file, and the index
  says so rather than the file being absent without explanation;
- **an index line**, appended per call: sequence number, ISO timestamp, tool name, program size in
  bytes, round-trip duration, envelope status, response size.

Files are named so the order of calls is recoverable from the directory listing alone, and so the
tool is identifiable without opening the file. A zero-padded monotonic sequence number satisfies
both; a timestamp does not, since two calls can share a second.

### FR-2: Off by default, and off means unchanged

Enabled by an environment variable naming the directory to write into. Unset — the normal case, and
the case every current test exercises — means no directory is created, no file is opened, nothing is
formatted, and the bytes on the wire are identical to today's. This is not merely a performance
point: an MCP server writing files nobody asked for, into a location nobody chose, is a surprise.

### FR-3: A conventional log alongside it

A `logging` hierarchy rooted at one logger name, one child per module, with **no handler attached by
default** — the ordinary discipline for a library, and here also the thing that keeps a quiet server
quiet. A second environment variable naming a level attaches a `stderr` handler and sets it. At
`INFO`, one line per call (tool, bytes, duration, status). At `DEBUG`, the decisions taken locally
before the socket — which is where the tool modules' validation work becomes visible, and it is
currently invisible in every tool.

The index file of [FR-1](#fr-1-a-per-call-record-on-disk) **is** the structured log; the `stderr`
log is for a human watching a session. Two structured logs would be one too many, and the NEXT_STEPS
entry's "a structured log" is considered satisfied by the index rather than by a second mechanism.

### FR-4: What, if anything, reaches the MCP caller

Tools return blender_mcp's envelope as-is, and that is a standing convention of this package rather
than an accident. So the answer here is deliberately narrow: **only on an error envelope, and only
while the record of [FR-1](#fr-1-a-per-call-record-on-disk) is enabled**, add one key naming the
files that were written. A success envelope is untouched in every configuration.

The reason to do it at all is that the person reading the failure is usually an agent, not the
person who set the environment variable, and a failure that does not say where its own evidence
landed wastes the record. The reason to keep it this narrow is that a field which appears only
sometimes is exactly the kind of thing
[Response shape](../../../specifications/architecture.md#response-shape) exists to discipline. If the
tension cannot be resolved in favour of the narrow version, the correct outcome is to add nothing
and say so.

### FR-5: Logging never fails a call

Every part of the record is best-effort. An unwritable directory, a full disk, a response that will
not serialize — none of them may turn a working call into a failed one. They may produce one warning
on the logger, once. The failure mode being avoided is concrete: a read-only tool that raises
because a diagnostic directory was not writable is strictly worse than a tool with no diagnostics.

### FR-6: State what the files contain, and keep them out of the repo

The record contains absolute paths from the user's install, their asset library layout, MHMAT and
MHCLO paths, and the parameters of the character they are building. There are no credentials
anywhere in this system, so **no scrubber is warranted and none should be built** — saying so
explicitly is part of this requirement, so that the absence is a decision rather than an oversight.
What is warranted: the documentation says plainly that this is diagnostic output about a user's
machine, the directory is never defaulted to somewhere inside the repository, and if a conventional
in-repo location is offered at all it carries a `.gitignore` entry.

## Non-functional requirements

**Zero cost when off**, in the literal sense: the disabled path performs no formatting, no
`time.perf_counter()` bracketing that feeds nothing, and no directory probing per call. Reading the
environment once at import is fine; doing work per call for a feature nobody enabled is not.

**One place, not twenty.** The whole mechanism lives at the single function every tool already
crosses. If implementing this requires editing tool modules, payloads or `codegen/`, the design is
wrong — see [Architecture](#recovering-the-tool-name-without-changing-a-signature).

**Fidelity over tidiness.** The logged program is the string that was sent, not a prettified,
truncated or re-wrapped version of it. A 52 KB file is fine; a 52 KB file with the middle elided is
useless for the one job it has.

**Readability of the record**, on the same footing as
[readability of the code](../../../specifications/architecture.md#readability-and-developer-experience-are-prioritized).
The index is meant to be read in a terminal and grepped; the program files are meant to be opened in
an editor and jumped to by line number.

## Architecture

### Where it goes

[connection.py](../../../src/mpfbmcp/connection.py)'s `send_code()`, and nowhere else. That module
already reads `BLENDER_MCP_HOST` / `BLENDER_MCP_PORT`, so environment-driven configuration is an
established shape there.

**The variable names should not use the `BLENDER_MCP_` prefix.** Those two are deliberately shared
with blender_mcp because both processes talk to the same add-on and must agree; these are mpfb-mcp's
own settings and blender_mcp knows nothing about them. An `MPFB_MCP_`-prefixed pair keeps that
distinction visible, and the module docstring's claim that this is a faithful duplicate of
blender_mcp's protocol stays true — the additions are around the protocol, not in it.

### Recovering the tool name without changing a signature

`send_code(code, strict_json)` does not know which tool called it, and the obvious fix — an extra
argument — would touch all twenty tool modules and quietly amend the rule that adding a tool touches
a tool module, a payload and a `register()` call.

It is not needed. [codegen.assemble()](../../../src/mpfbmcp/codegen/__init__.py) already labels every
seam, and the last one is `# --- payload: <name> ---`, put there so a line number reported from
inside Blender can be traced back to its file. The same marker identifies the tool: scan the code
for it and take the name. A program with no marker — something assembled by hand, or a future call
that is not a payload — is recorded under a neutral name rather than rejected.

The coupling this creates is real and worth naming: the marker format is now written by `codegen`
and parsed by `connection`, two modules that had nothing to do with each other. It should be pinned
by a test on both sides rather than left as a comment.

### Never stdout

The server runs `mcp.run(transport="stdio")`. **Stdout is the JSON-RPC channel.** Anything written
there — a `print()` added while debugging, a `logging.StreamHandler()` left at its default stream —
corrupts the protocol, and it does not fail loudly: it surfaces as a client that hangs, drops the
connection, or reports a parse error nowhere near the code that caused it. Every handler this
package attaches writes to `stderr` or to a file. This is the single most likely way to break the
server while adding observability to it, and it belongs in the module docstring, not only here.

### What this measures, and what it cannot

The duration recorded is the **wall-clock round trip**, taken with `time.perf_counter()` around the
socket block. It therefore includes transport, the add-on's `exec()` of the program, and MPFB's own
work, and separates none of them.

Decomposing it further would mean instrumenting the generated program — a timing stanza in the
bootstrap, most plausibly — and that is deliberately **out of scope here**, for a reason worth
stating: it changes the program that is sent. The one thing this request must not do is make "the
exact program that ran" conditional on a diagnostic setting, which would undermine both
[FR-1](#fr-1-a-per-call-record-on-disk) and every live verification that cites a logged program.

The decomposition is still reachable when it is actually wanted: the add-on's envelope already
carries `stdout`, so a payload can print its own timings during a session without any change to this
mechanism. [FR 013](../013-live-verification/README.md)'s cost measurements should take the
round-trip and the byte count from this record and get the split, if it needs one, that way.

### Pitfalls

- **A response that will not serialize.** FR 005 already found a value `json` cannot encode
  (`get_asset_list()`'s `thumb`). The response *file* must therefore tolerate an envelope it cannot
  round-trip — `default=repr` or an equivalent — or the record will be missing precisely on the
  calls that most need it. Per [FR-5](#fr-5-logging-never-fails-a-call) this must never propagate.
- **Two servers at once.** More than one MCP client can run `mpfb-mcp` against the same Blender.
  The per-run directory needs to carry the process id as well as a timestamp, or two sessions
  interleave into one index and the sequence numbers stop meaning anything.
- **Writing the program before the call is the whole point.** It is easy to write both files
  together after the response arrives, and that version silently loses every case this exists for:
  a timeout, a crash, a call that never returns.
- **The disabled path is what the existing 654 tests exercise.** A regression there is a regression
  in every tool at once, which argues for keeping the enabled path entirely inside a branch taken on
  a value read once.

## Affected specifications

- **[specifications/architecture.md](../../../specifications/architecture.md)** — this adds a standing
  convention and there is currently no section for it. The natural placement is beside
  [No direct dependency on MPFB or blender_mcp](../../../specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp),
  which is where the socket boundary is described, saying: everything crosses one function,
  diagnostics attach there and nowhere else, the generated program is never altered to observe it,
  and stdout belongs to the transport. The note under
  [Code-generation layout](../../../specifications/architecture.md#code-generation-layout) about seams
  being labelled for line-number tracing gains a second consumer and should say so.
- **[specifications/vision.md](../../../specifications/vision.md)** — untouched. This adds no tool and
  changes no tool's answer; the one caller-visible effect
  ([FR-4](#fr-4-what-if-anything-reaches-the-mcp-caller)) is confined to an error envelope while
  the record is enabled.
- **[CLAUDE.md](../../../CLAUDE.md#commands)** — not a specification, but the Commands section
  documents `BLENDER_MCP_HOST` / `BLENDER_MCP_PORT` and is where the new variables have to be
  documented for anyone to find them.

## Tests

Unusually for this repo, **almost all of this is testable on this side of the socket**, because it
is entirely on this side of the socket. [tests/test_connection.py](../../../tests/test_connection.py)
already stands up a throwaway local `socketserver.TCPServer` in place of the add-on, which is the
right instrument for all of the below.

- **The disabled path writes nothing.** With the variables unset: no directory created, no file
  opened, and the request bytes identical to those the existing tests assert.
- **The program file exists before the response does.** Assert it against a stub server that
  accepts the request and then fails or never answers — the case the ordering requirement exists
  for, and the one a naive implementation passes every other test while getting wrong.
- **Byte-for-byte fidelity.** Compare the file to the string passed in, on a program containing the
  things that tempt an implementation to normalize: non-ASCII, CRLF, trailing whitespace, a very
  long line.
- **Tool-name extraction**, against a real `codegen.assemble()` output rather than a hand-written
  marker — that is the coupling worth pinning — plus the no-marker case.
- **The index line's fields**, including the `ConnectionError` case where there is a program and a
  duration but no response.
- **Failure is swallowed.** Point the directory at an unwritable path and assert the call still
  returns its normal result, and that the returned envelope is unchanged.
- **Nothing reaches stdout** in any configuration, asserted by capture rather than by inspection.
- **No handler by default**, and the level variable attaching one to `stderr`.

**One thing needs a live run, and it is the thing the request exists for:** that a traceback line
number from a real add-on failure resolves to the right line of the dumped program. Force a failure
in a real Blender — a payload edited to raise, or a tool called against a character that does not
meet its preconditions — and check the line by hand. That is the first item of
[FR 013](../013-live-verification/README.md)'s session, and this request should land before it so
the rest of that session is diagnosable.

## References

- [NEXT_STEPS.md](../../NEXT_STEPS.md#observability) — the entry this request scopes.
- [FR 013](../013-live-verification/README.md) — the consumer: its diagnostics and its cost
  measurements both come from this record.
- [FR 005](../005-list-assets/README.md) — the source of the ~1.0 s round-trip figure that four
  decisions cite, and of the `strict_json` encoding failure this record has to tolerate.
- [connection.py](../../../src/mpfbmcp/connection.py) — the one function everything crosses.
- [codegen/\_\_init\_\_.py](../../../src/mpfbmcp/codegen/__init__.py) — the seam markers, and why the
  payload name is already in the program.

## Verification status

**Implemented, unit-tested and live-verified (2026-09-01).** The module, the two hooks in
`send_code()` and the tests landed on 2026-08-31 with one item outstanding: that a traceback line
number from a real add-on failure resolves to the right line of the dumped program. It was the
first thing [FR 013](../013-live-verification/README.md)'s session did, and it passed.

**The check.** A program shaped exactly as `codegen.assemble()` builds one — the same bootstrap,
the same JSON prelude, the same labelled payload seam, a real payload file underneath — with a
raise appended on a line the check computed. Blender answered
`File "<string>", line 182 ... RuntimeError`, and **line 182 of the dumped `.py` is the raising
line**. It was then repeated with `get_status.py`'s program and confirmed again at line 152. The
error envelope carried `mpfb_mcp_record` naming the two files, and the index line carried the tool
name, the byte count, a real duration and `error`.

It is now a script rather than a one-off:
[verification/check_fr012.py](../../../verification/check_fr012.py), which also re-asserts that the
disabled path writes nothing while the call still works.

**One note about the failure that was used.** The first attempt edited
`payloads/refit_human.py` to raise, which is what this request's own text suggested, and it worked
— but the script does not do that: no tool in this package has an uncaught path, which is the
property the package is written for, and a payload edited to raise leaves the working tree dirty if
the run is interrupted. Building a program of the same shape tests the same coupling without that
risk.

### What the session added to the record

The record itself was the session's main instrument, and two things about it are worth recording
from the other side of the socket.

**Its per-call log line is gated on either variable, not only on `MPFB_MCP_LOG_LEVEL`.** With
`MPFB_MCP_RECORD_DIR` set and `MPFB_MCP_LOG_LEVEL` unset, the `INFO` line still appears — because
a `_Call` object exists and `FastMCP()` has already put a handler on the root logger. That is
defensible (turning the record on *is* asking for diagnostics) and it is what the whole session
ran with, but it is not what
[Zero cost when off](#non-functional-requirements) literally says. The property that matters — both
unset means nothing is constructed, formatted or written — is unaffected and is still asserted by
`tests/test_observability.py`.

**The `ms` column measures the round trip and includes whatever else the machine is doing.**
Midway through the session, `add_rig` moved from ~2.2 s to ~8.0 s for about fifteen minutes and
then back, with small probes unaffected throughout. Nothing in the program changed. That is not a
defect in the record — it is the record doing its job — but it is why
[FR-8's measurements](../013-live-verification/review.md#do-the-three-payload-count-driven-decisions-still-hold)
report medians and say which figures are stable.

Everything else on the request's [Tests](#tests) list was already asserted by the unit suite and
still is.

### What changed against this request

**`FastMCP()` calls `logging.basicConfig()`.** This was not known when the request was written and
it changes two things. In the real server the *root* logger is therefore already at `INFO` with a
handler attached before any tool runs, so [FR-3](#fr-3-a-conventional-log-alongside-it)'s "no
handler attached by default" would have been true in letter and false in effect: an ordinary
`logger.isEnabledFor(INFO)` gate would have switched the per-call line — and its
`perf_counter()` bracketing and formatting — on for every session, which is exactly what
[Zero cost when off](#non-functional-requirements) forbids. The per-call line is consequently gated
on the environment rather than on the logger. And propagation is turned off while this package's
own handler is attached, or a user who opts in gets every line twice. Worth recording for its own
sake: mcp's handler is a `RichHandler` on a `Console(stderr=True)`, so the host is *not* itself a
threat to the transport — but [Never stdout](#never-stdout) was one library-default away from being
violated by code this request never touches.

**The mechanism lives in a new `src/mpfbmcp/observability.py`, not inside `connection.py`.**
[Where it goes](#where-it-goes) says "`connection.py`'s `send_code()`, and nowhere else", and the
*attachment point* is exactly that — two calls and a `record.annotate()` on the return. The
mechanism itself is a sibling module, because putting ~300 lines of record-keeping into the file
whose docstring calls it a faithful duplicate of blender_mcp's protocol would have made that claim
awkward to defend. The requirement the placement actually served —
[One place, not twenty](#non-functional-requirements) — is met and testable: no tool module, no
payload and no `codegen/` module was edited.

**[FR-4](#fr-4-what-if-anything-reaches-the-mcp-caller) resolved in favour of the narrow version.**
An error envelope, while the record is enabled, gains `mpfb_mcp_record` naming the program and the
response file. A success envelope is untouched in every configuration, and both cases are asserted.

**The payload marker is parsed tolerantly.** The first version of the regex required the line to
end immediately after ` ---`, which the byte-fidelity test broke by handing `send_code()` a program
with a CRLF in it — the tool name silently became `unnamed`. Trailing whitespace and a carriage
return are now allowed, since the marker has to be found in whatever was handed to `send_code()`
rather than only in what `codegen` produced.

**The response-serialization pitfall is real but not reachable from here.** The envelope
`send_code()` records has by definition just come out of `json.loads()`, so it always re-encodes.
The failure the request anticipated is on the *Blender* side — `strict_json` rejecting a value like
`get_asset_list()`'s `thumb` — and arrives as an error envelope, which the record handles like any
other. `default=repr` is kept regardless, and is tested against the recorder directly rather than
through a call, since no call can produce the case.

**`tests/fake_addon.py` was extracted.** The throwaway add-on server moved out of
`test_connection.py` so two modules could share it, and grew three abilities each test here needed:
answering per request (the ordering test has the fake add-on look at the filesystem while it holds
the request), answering nothing and closing (the no-response index line), and keeping the raw
request bytes (so "off means the same bytes on the wire" is an assertion).

