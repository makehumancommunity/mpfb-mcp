"""
The seam: the one function every tool's call to Blender goes through.

**A tool says what it wants done; this module is where the saying becomes a
socket call.** With one transport left that looks like an indirection with
nothing to indirect, and it earns its place for a different reason than the one
it was built for. What a tool module contains is a description, an argument
contract, local validation and one call; what it must *not* contain is a
protocol. Twenty-four modules importing ``bridge_connection`` directly would
put the wire's vocabulary - the command name, the framing, the handshake, the
address variables - inside every tool, and the next change to any of it would
be twenty-four edits made twenty-four times. There is one place that knows a
call leaves this process, and this is it. See
[Supporting a second backend](../../specifications/architecture.md#supporting-a-second-backend)
for how the seam was chosen and what happened to the second backend that named
it.

**A command name, and the parameters a tool has already validated.** Both sides
receive the tool's arguments unreshaped - there is deliberately no escape hatch
for a tool that would want to send something other than what it was given. If
one ever does, that is a design problem to surface in that tool's own effort
rather than a flexibility to carry here unused.

**The envelope is this package's, and the bridge writes it.** ``status``,
``result`` and ``message`` keep their spellings and their meanings; a failure
additionally carries ``error``, the short slug a caller branches on, and
``protocol_version``. Nothing is synthesised or rewritten on the way through -
every error envelope is built by one function in the add-on
([command_server.py](../../bridge/mpfb_bridge/command_server.py)'s ``_error``),
which is why there is nothing for this module to fill in.

**One variable is read here that nothing acts on.** ``MPFB_MCP_BACKEND`` chose
between two transports until FR 033 deleted the second, and a value left behind
in somebody's MCP client configuration would otherwise be obeyed by nothing and
reported by nothing. It gets one line on this package's logger instead, which
is the whole of its remaining behaviour - and never on stdout, which is the
JSON-RPC channel.
"""

from __future__ import annotations

__all__ = (
    "BACKEND_VARIABLE",
    "send",
)

import os

from mpfbmcp import bridge_connection, observability

# Read only to say that it is no longer read. Kept as a named constant rather
# than a string in one function because the test that asserts the warning fires
# should be naming the same thing the docstring above does.
BACKEND_VARIABLE = "MPFB_MCP_BACKEND"

_LOG = observability.get_logger(__name__)

# Whether the warning below has been emitted in this process. A stale variable
# does not become less stale during a session, and a line per call would be its
# own kind of damage - the same reasoning observability._warn_once() is built on.
_warned_about_backend_variable = False


def send(command: str, *, params: dict[str, object] | None = None) -> dict[str, object]:
    """Perform one tool's call: name a command, hand over its parameters.

    ``command`` is a key of the add-on's closed vocabulary
    ([commands/table.py](../../bridge/mpfb_bridge/commands/table.py)), which is
    the one file that says everything this package can ask Blender to do. Tool
    module, command module and test module share a name - ``mpfb_set_skin`` is
    ``tools/set_skin.py``, ``commands/set_skin.py`` and ``tests/test_set_skin.py``
    - with one deliberate exception: ``mpfb_get_status`` sends ``get_mpfb_status``,
    because the bridge has a ``get_status`` of its own reporting the *add-on*,
    and two commands answering "status" about two different pieces of software
    is a collision that is cheap now and permanent later.

    Raises ``ConnectionError`` when the bridge cannot be reached at all, rather
    than returning an envelope: an unreachable add-on is a different kind of
    fact from a command that failed, and ``mpfb_list_urls`` is the one tool that
    catches it and answers anyway.
    """
    _warn_if_backend_variable_is_set()
    return bridge_connection.send_command(command, params or {})


def _warn_if_backend_variable_is_set() -> None:
    """Say once that ``MPFB_MCP_BACKEND`` is set and is not read any more.

    The silent alternative is the expensive one. Somebody who pinned the
    variable to ``blender_mcp`` while the generated path existed would otherwise
    get a working server that ignores the setting, and would have no way to tell
    that from a setting that is being honoured - which is the same argument that
    made an *unrecognised* value an error rather than a fallback while there
    were still two backends to choose between.
    """
    global _warned_about_backend_variable  # pylint: disable=global-statement
    if _warned_about_backend_variable:
        return
    configured = os.environ.get(BACKEND_VARIABLE, "").strip()
    if not configured:
        return
    _warned_about_backend_variable = True
    _LOG.warning(
        "%s=%s is set, and is no longer read: the generated-code path it chose between was "
        "removed in FR 033 and every tool talks to the MPFB Bridge. Use MPFB_BRIDGE_HOST and "
        "MPFB_BRIDGE_PORT to address the bridge, and unset this.",
        BACKEND_VARIABLE, configured)
