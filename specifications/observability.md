# Observability

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

How a call is made visible. The subject is narrow on purpose: mpfb-mcp's topology gives
diagnostics exactly one place to attach, and most of what follows is a consequence of that.

The concrete environment variables and what they write are in
[CLAUDE.md](../CLAUDE.md#commands); the structural reason there is a single attachment point is
[No direct dependency on MPFB or blender_mcp](architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp).

## Diagnostics attach at the socket boundary, never to the program

Every tool assembles a program, hands it to `send_code()` and returns the envelope. That single
function is therefore the only place diagnostics belong, and the rule is worth stating as a
constraint rather than as a preference: **if observing a call requires editing a tool module, a
payload or `codegen/`, the design is wrong.** Twenty tools crossing one function is what makes a
per-call record a change in one file; it is also what stops "which tool called this" needing an
extra argument, since the seam marker of
[Code-generation layout](architecture.md#code-generation-layout) already names the payload.

- **The generated program is never altered in order to observe it.** A diagnostic setting that
  changed the source would make "the exact program that ran" conditional on configuration, which is
  the one property the record exists to provide — a traceback's line number has nothing else to be
  resolved against. Decomposing a round trip into transport, `exec`/compile and MPFB's own work is
  therefore *not* done this way; a payload can print its own timings into the envelope's `stdout`
  during a session that wants them.
- **mpfb-mcp's own settings carry an `MPFB_MCP_` prefix.** `BLENDER_MCP_HOST` / `BLENDER_MCP_PORT`
  are shared with blender_mcp deliberately, because both processes address the same add-on and have
  to agree; anything blender_mcp knows nothing about is mpfb-mcp's own and is named accordingly.
  Keeping the two apart is also what lets `connection.py` go on describing itself as a faithful
  duplicate of blender_mcp's protocol: the additions are around the protocol, not in it.
- **Off means unchanged.** A diagnostic that is not enabled creates no directory, opens no file,
  formats nothing and puts the same bytes on the wire. An MCP server writing files nobody asked
  for, into a location nobody chose, is a surprise; and the disabled path is the one the whole test
  suite exercises, so a regression there is a regression in every tool at once.
- **A diagnostic never fails a call.** An unwritable directory, a full disk or a value that will
  not serialize produces one warning and is otherwise swallowed. A read-only tool that raises
  because a diagnostic directory was not writable is strictly worse than a tool with no
  diagnostics.
- **Stdout belongs to the transport.** The server runs `mcp.run(transport="stdio")`, so stdout *is*
  the JSON-RPC channel. A `print()` left in while debugging, or a `logging.StreamHandler()` at its
  default stream, corrupts the protocol and does not fail loudly — it surfaces as a client that
  hangs, drops the connection or reports a parse error nowhere near the cause. Every handler this
  package attaches names `stderr` or a file explicitly. Note also that the host has already
  configured logging by the time a tool runs: `FastMCP()` calls `logging.basicConfig()`, so the
  root logger is at `INFO` with a handler on it, which is why anything this package emits per call
  is gated on its own setting rather than on an ambient level.
- **What the record contains is diagnostic output about the user's machine** — absolute paths from
  their install, their asset library layout, the MHMAT and MHCLO files they have, the parameters of
  the character they are building. There are no credentials anywhere in this system, so no
  scrubbing is done, and that absence is a decision rather than an oversight. What follows from it:
  say so in the documentation, and never default such a directory to somewhere inside the
  repository.
- **The caller-visible surface stays narrow.**
  [Response shape](responses.md#response-shape) says tools return blender_mcp's envelope as-is.
  A diagnostic may add to an *error* envelope, and only while the record that produced the
  information is enabled — because whoever reads a failure is usually an
  agent rather than the person who configured the record, and a failure that does not say where its
  own evidence landed wastes it. A success envelope is untouched in every configuration.
