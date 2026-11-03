# Checking an install without an MCP client

**Status:** Proposed

This scopes [No way to verify an install without an MCP
client](../NEXT_STEPS.md#no-way-to-verify-an-install-without-an-mcp-client).

**The tool that diagnoses an install can only be reached through a working install.**
`mpfb_get_status` answers precisely whether MPFB is present, initialized and correctly configured,
and calling it needs the client registration that is the thing in doubt. The man-and-woman session
began with the server installed but not registered, could not tell that from a broken one, and
hand-wrote forty lines of JSON-RPC over stdio to find out. [INSTALL.md](../../INSTALL.md) step 4
says not to run the command by hand, because it sits waiting for a client, and step 7 starts from a
client.

Nothing needs inventing. The pieces already exist: `bridge_connection` does the handshake,
`build_server()` builds what a client talks to, `tests/test_vocabulary.py` already runs a real MCP
client against it in memory, and `mpfb_get_status` carries the rest.

**What it can honestly separate differs from what the entry hoped.** It asked to tell "the bridge is
not running" from "the add-on is not enabled". From outside Blender those are one fact: nothing is
listening on that address. Stopped, disabled, not installed, on a different port and no Blender at
all look the same, and the check should say that rather than guess. What it can separate:

| Stage | What fails | Who can tell today |
|---|---|---|
| The package runs and builds | A broken venv, a wrong `mcp` version | Only a traceback in a client's log |
| A client can talk to it | A tool that fails to register | Only a client |
| Something is listening | Nothing at that address | `ss`, on Linux |
| That something is the bridge | The other Blender MCP add-ons, on a port typed wrongly | Nobody |
| Same protocol | Halves from different checkouts | The first tool call |
| MPFB is there | `absent`, `not_initialized` | `mpfb_get_status` |

"The client never started the server" cannot be seen from here either. But a passing self-test makes
it the remaining explanation, and it can say that.

## Goals

**Primary:** one command, ending the install guide, says which link in the chain is broken and what
to do about it.

**Secondary:**

- **A script can use it**, through its exit code.
- **A user can paste it into a bug report**, with what a maintainer would ask for.

## Non-goals

- **Checking the client's configuration.** Clients differ, their files move, and `claude mcp list`
  exists. The output points there.
- **Changing anything.** It builds no character, and is safe against a Blender with work in it.
  [verification/](../../verification/README.md) is the check that builds things and wants a Blender
  to throw away.
- **Starting Blender, or looking inside one from outside.** Nothing here reads Blender's add-on
  state from disk.
- **A new tool or bridge command.** Nothing crosses the socket that does not already.
- **A general CLI.** One flag, not subcommands.

## Functional requirements

1. **`mpfb-mcp --selftest`** runs the checks, prints the result and exits.
2. **`mpfb-mcp` with no arguments is exactly what it is today**: stdio, and no parsing visible to a
   client. An unknown argument exits with a usage message on stderr rather than starting a server
   that nothing will talk to.
3. **The stages run in order, and each says what it found:**
   1. **Package:** this package's version and location, the Python, the `mcp` version.
   2. **Server:** `build_server()` builds, a real MCP client session in memory initializes, and
      `list_tools` answers. Reports the tool count.
   3. **Address:** the host and port used and where they came from
      (`MPFB_BRIDGE_HOST`/`MPFB_BRIDGE_PORT`, or the default). Whether anything accepts a
      connection.
   4. **Bridge:** `get_status` answers as the bridge, with both protocol versions.
   5. **MPFB:** `mpfb_get_status` through that same in-memory client, reporting `state` and MPFB's
      and Blender's versions.
4. **Stages after a failure are reported as not run**, rather than left out, so nobody reads a short
   list as a clean one. Stage 2 does not depend on stage 3: a server that builds without a Blender
   is a useful fact.
5. **A failure says what to do next**, in one sentence, naming the matching row of
   [INSTALL.md](../../INSTALL.md#troubleshooting). Nothing listening says all of what it could be:
   not started, add-on not enabled, a different port, no Blender.
6. **Something listening that is not the bridge is its own finding**, since a typed port can reach
   another add-on. It answers a request with something other than this protocol, or not at all,
   within the timeout.
7. **A short timeout.** The tools' 300 s would make the command look hung. 5 s per stage,
   overridable with `--timeout`. A busy Blender is a possible cause and the message says so.
8. **The last line is a verdict**, `OK` or the stage that failed. On success it adds that if the
   client still shows no tools, the client's registration is what is left, and how to check it.
9. **Exit codes:** `0` all stages passed; `1` the package or server (stages 1-2); `2` nothing
   listening or not the bridge (3-4); `3` a protocol mismatch; `4` MPFB `absent` or
   `not_initialized`. Named constants, and the guide lists them.
10. **`MPFB_MCP_BACKEND` left in the environment** gets its existing WARNING, on stderr, and that
    stays visible here, since this is where somebody would look.
11. **Read-only on the far side.** Only `get_status` and `get_mpfb_status`. It changes nothing in
    Blender, and the description says so.
12. **`MPFB_MCP_RECORD_DIR` works as for any call**, because the calls go through the same path.

### The install guide

13. **[INSTALL.md](../../INSTALL.md) step 7 begins with it**, before asking a client for anything.
    Step 4's "do not run it by hand" stays, with the flag as the exception.
14. **The Troubleshooting table's first row points at it.**
15. **The one-liner the entry wanted written down either way:** on Linux `ss -ltnp | grep 9877`, on
    macOS `lsof -iTCP:9877 -sTCP:LISTEN`, on Windows `netstat -ano | findstr 9877`. **The Linux line
    comes from the session that found this**, and the other two must be tried or marked as untried.

## Non-functional requirements

- **Readable by a person who has just had an install fail.** Plain text, one line per finding, no
  traceback unless a stage raised unexpectedly.
- **Nothing on stdout from the server path.** [The rule](../../specifications/observability.md) is
  that stdout is the JSON-RPC channel. `--selftest` never serves, so it may print there, and only
  that code path does. A test holds the no-argument path to nothing on stdout.
- **Safe to paste.** It prints paths from the install and versions, and there are no credentials in
  this system. The output is the same class of data as the record directory, and the guide says to
  read it first.
- **Fast when things are fine:** well under a second past import against a running bridge, apart
  from a windowed Blender's [one answer a
  second](../NEXT_STEPS.md#windowed-bridge-answers-once-a-second).

## Architecture

- **`src/mpfbmcp/selftest.py`**, beside `observability.py` rather than in `tools/`, since a module
  there is a tool. `main()` in `__init__.py` parses `sys.argv` and dispatches. `argparse` is stdlib,
  and this package adds no dependency.
- **Use the in-memory client** (`mcp.shared.memory.create_connected_server_and_client_session`), as
  `tests/test_vocabulary.py` does. That is the point: it exercises `initialize`, `list_tools` and
  `tools/call` on the server that ships. It is not a stable public API in the same way the rest of
  `mcp` is. The `<2` pin in [pyproject.toml](../../pyproject.toml) contains that, and a failure of
  the import itself is a stage-1 finding, not a crash.
- **Handshake details are `bridge_connection`'s.** Use its calls and its errors rather than opening
  a second socket client. If telling "refused" from "not the bridge" needs an exception it does not
  raise, add it there.
- **Its memoised probe** is dropped on failure already, so a selftest process has no state to worry
  about.
- **`from __future__ import annotations`, `__all__` and `.format()`**, as everywhere here.
- **Pitfall:** `asyncio.run()` around the in-memory session, and the tool calls inside it, must not
  leave a pending task producing noise on exit.
- **Pitfall:** on Windows the console script is an `.exe` wrapper. Exit codes pass through it, and
  that has not been checked here.

## Affected specifications

- [observability.md](../../specifications/observability.md): a diagnostic that is not per-call, and
  the one sanctioned use of stdout.
- [architecture.md](../../specifications/architecture.md): the entry point now has a second mode.
  The rule that nothing opens a network connection except to the add-on still holds.
- [testing.md](../../specifications/testing.md): no change.
- [vision.md](../../specifications/vision.md): no change. It adds no tool.

## Tests

- **Unit, `tests/test_selftest.py`, against `fake_bridge`:** each exit code, a stage after a failure
  reported as not run, the protocol mismatch in both directions, a listener speaking something else
  (`fake_bridge` already answers raw bytes), a listener that never answers within `--timeout`,
  `absent` and `not_initialized`, and each failure's sentence.
- **`tests/test_selftest.py`, the entry point:** no arguments starts the server path and prints
  nothing on stdout (mocked); an unknown argument exits with usage.
- **Live check, a script in this subdir:** against a real headless Blender: all well, wrong port,
  killed Blender, MPFB disabled, and the add-on disabled. It records the output of each and the
  time, and pastes one into the Outcome.
- **No smoke item, and no bridge test.** No tool or command is added, and `test_verification_smoke`
  should not notice.

## Decisions taken while scoping

Asked on 2026-11-03:

- **This took the fifth place** from missing-texture warnings, a name and targets on
  `mpfb_create_human`, and `mpfb_remove_character`. All three stay in NEXT_STEPS.

*Not asked*, each argued where it is stated: `--selftest` rather than a `doctor` subcommand, because
one flag on a command with no others does not need subcommands; text and an exit code rather than
`--json` (Goals), which can follow if anyone scripts more than the exit code; what cannot be told
apart from outside Blender (the opening), which corrects the NEXT_STEPS entry.

## References

- [NEXT_STEPS: No way to verify an install without an MCP
  client](../NEXT_STEPS.md#no-way-to-verify-an-install-without-an-mcp-client).
- [INSTALL.md](../../INSTALL.md), steps 4 and 7 and Troubleshooting.
- `src/mpfbmcp/bridge_connection.py`, `tests/test_vocabulary.py`, `tests/fake_bridge.py`.
