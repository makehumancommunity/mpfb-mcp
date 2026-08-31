"""
Socket client for communicating with the blender_mcp add-on.

This is a small, standalone re-implementation of blender_mcp's wire protocol
(see ``blmcp.tools_helpers.connection`` in the ../blender_mcp repo), kept as a
plain duplicate rather than a dependency so that mpfb-mcp installs and runs
without needing a checkout of blender_mcp on the Python path. It talks to the
*same*, unmodified blender_mcp add-on socket server — same environment
variables, same JSON + NUL-delimited framing, same "execute" request shape.

If blender_mcp's protocol changes, this needs to be updated to match.

``send_code()`` is also the one function every tool crosses, so it is where
mpfb-mcp's own diagnostics attach: ``MPFB_MCP_RECORD_DIR`` keeps the exact
program and the exact envelope on disk, and ``MPFB_MCP_LOG_LEVEL`` puts a line
per call on stderr. Both are off by default, both live in ``observability`` so
that this module stays a protocol client, and neither carries the
``BLENDER_MCP_`` prefix - those two are shared with blender_mcp because both
processes address the same add-on, while these are mpfb-mcp's own. The
additions are around the protocol rather than in it: the bytes on the wire are
the same in every configuration.
"""

from __future__ import annotations

__all__ = (
    "get_connection_params",
    "send_code",
)

import json
import os
import socket

from mpfbmcp import observability

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 9876
_TIMEOUT = 300.0
_RECV_BUFFER_SIZE = 65536


def get_connection_params() -> tuple[str, int]:
    """Read the blender_mcp add-on's host/port from the environment.

    Uses the same ``BLENDER_MCP_HOST`` / ``BLENDER_MCP_PORT`` variables as
    blender_mcp itself, since both talk to the same add-on socket server.
    """
    host = os.environ.get("BLENDER_MCP_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("BLENDER_MCP_PORT", str(_DEFAULT_PORT)))
    return host, port


def send_code(code: str, strict_json: bool = True) -> dict[str, object]:
    """
    Send Python code to the blender_mcp add-on socket server for execution.

    Returns the full response dict from the add-on, containing ``status``
    (``"ok"`` or ``"error"``), ``result`` (on success), ``message`` (on
    error), and optionally ``stdout``/``stderr`` captured during execution.

    Raises ``ConnectionError`` when Blender is unreachable, times out, or
    returns a response that cannot be parsed.
    """
    host, port = get_connection_params()
    request = json.dumps({
        "type": "execute",
        "code": code,
        "strict_json": strict_json,
    }) + "\0"

    # Opened before the socket block, because that is what writes the program
    # to disk: a call that hangs, times out or takes Blender down has to leave
    # behind the program that did it. Does nothing at all unless asked to.
    record = observability.begin(code)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(_TIMEOUT)
            sock.connect((host, port))
            sock.sendall(request.encode("utf-8"))

            buf = bytearray()
            while True:
                chunk = sock.recv(_RECV_BUFFER_SIZE)
                if not chunk:
                    break
                buf.extend(chunk)
                if b"\0" in buf:
                    break
    except ConnectionRefusedError as ex:
        record.failed(ex)
        raise ConnectionError(
            "Cannot connect to Blender at {:s}:{:d}. Ensure Blender is running with the "
            "blender_mcp add-on enabled and its server started.".format(host, port)
        ) from ex
    except socket.timeout as ex:
        record.failed(ex)
        raise ConnectionError(
            "Blender connection timed out at {:s}:{:d}".format(host, port)
        ) from ex
    except OSError as ex:
        record.failed(ex)
        raise ConnectionError(
            "Socket error communicating with Blender at {:s}:{:d}: {:s}".format(host, port, str(ex))
        ) from ex

    if not buf:
        empty = ConnectionError("Empty response from Blender")
        record.failed(empty)
        raise empty

    line, _sep, _rest = buf.partition(b"\0")
    try:
        response: dict[str, object] = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        record.failed(ex)
        raise ConnectionError(
            "Invalid response from Blender at {:s}:{:d}: {:s}".format(host, port, str(ex))
        ) from ex

    record.finished(response)
    # A no-op unless this is an error envelope and the record is enabled; see
    # observability._CallRecord.annotate().
    return record.annotate(response)
