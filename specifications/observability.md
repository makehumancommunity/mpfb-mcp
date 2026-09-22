# Observability

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

How a call is made visible. The subject is narrow on purpose: mpfb-mcp's topology gives
diagnostics exactly one place to attach, and most of what follows is a consequence of that.

The concrete environment variables and what they write are in
[CLAUDE.md](../CLAUDE.md#commands); the structural reason there is a single attachment point is
[No direct dependency on MPFB](architecture.md#no-direct-dependency-on-mpfb-and-none-on-the-add-on-either).

## Diagnostics attach at the socket boundary, never inside Blender

Every tool sends a request across a socket and returns the envelope that comes back. That crossing
is therefore the only place diagnostics belong, and the rule is worth stating as a constraint
rather than as a preference: **if observing a call requires editing a tool module or a bridge
command, the design is wrong.** Twenty-four tools crossing one function —
`bridge_connection.send_command()` — is what makes a per-call record a change in one module; it is
also what stops "which tool called this" needing an extra argument.

The title used to say "never to the program", from a time when a request *was* a Python program
this package assembled. The rule it named is unchanged and is about not instrumenting inside
Blender: what is recorded is the request and the answer, not anything MPFB did in between.

- **The request is written before the socket call**, for the reason it always has been: a call that
  hangs, times out or takes Blender down still leaves behind what caused it. Writing both files
  after the response arrives would lose exactly the cases the record exists for.
- **The file is what went on the wire, byte for byte.** Unindented and unprettified, so it is the
  request that can be replayed rather than nearly it. A record that is *nearly* what was sent is a
  record that has to be argued with.
- **The tool's name comes from the command.** A request that names its command needs no device for
  saying what it is. Tool and command share a name by convention — `mpfb_list_objects` sends
  `list_objects` — so the index reads as a list of the tools that were called, which is what
  somebody opening it is looking for.
- **One index, one directory, in call order.** `index.tsv` columns are `seq`, `timestamp`, `tool`,
  `bytes`, `ms`, `status` and `response_bytes`, and `bytes` counts the request.
- **The handshake probe is a call and is recorded as one.** The first request to an address is
  preceded by a `get_status`, so a tool's own call is usually sequence `0002`. An index that
  quietly omitted the probe would misreport the order of what happened.
- **Nothing is instrumented inside Blender in order to observe a call.** Decomposing a round trip
  into transport, dispatch and MPFB's own work is not done from here; a command can report its own
  timings in its answer during a session that wants them.
- **mpfb-mcp's own settings carry an `MPFB_MCP_` prefix, and the add-on's address does not.**
  `MPFB_BRIDGE_HOST` / `MPFB_BRIDGE_PORT` name *the add-on being addressed*; `MPFB_MCP_RECORD_DIR`
  and `MPFB_MCP_LOG_LEVEL` say what this process does with a call it has already decided to make,
  and would mean nothing to the add-on. The bridge reads its address from its preferences rather
  than from the environment today — and if it ever reads the environment, those are the two names
  it should read.
- **A variable that stops being read says so.** `MPFB_MCP_BACKEND` chose between two transports
  and is now read for one purpose only: to put a line on this package's logger when it is set.
  Obeyed by nothing and reported by nothing is the expensive option, because a setting that is
  silently ignored is indistinguishable from one that is being honoured.
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
  [Response shape](responses.md#response-shape) says a tool returns the envelope it was given.
  A diagnostic may add to an *error* envelope, and only while the record that produced the
  information is enabled — because whoever reads a failure is usually an
  agent rather than the person who configured the record, and a failure that does not say where its
  own evidence landed wastes it. A success envelope is untouched in every configuration.
