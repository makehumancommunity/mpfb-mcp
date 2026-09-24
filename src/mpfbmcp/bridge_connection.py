"""
Socket client for the MPFB Bridge, the companion add-on this project ships.

**The one place in this package that knows what goes on a wire.** A request
names a command from the add-on's closed vocabulary, carries its parameters as
data, and gets back an answer carrying ``status``, ``result`` or ``message``,
``protocol_version``, the command's own name and, on a failure, a slug. The
framing is JSON terminated by a NUL byte, one request per connection.

It had a sibling until FR 033, ``connection.py``, speaking a third party's
protocol for a transport that sent Python to be ``exec()``-ed. Two modules
rather than one because a *faithful duplicate* of somebody else's protocol
stops being faithful the moment it is also serving another; the other protocol
is gone, and this one is what is left.

The socket is the only boundary every call crosses, which is why
``observability`` attaches here and nowhere else: a call records the request it
sent, byte for byte as it went on the wire.

**The handshake lives here, and it is one probe per address per process.** FR
029 built the bridge's half: every answer carries ``protocol_version``,
``get_status`` additionally reports ``min_supported_protocol_version``, and a
request declaring a version outside the accepted range is refused with
``protocol_mismatch``. This is the other half. Every request declares its
version, which is free and earns the bridge's own refusal for nothing; and the
first call to a given address asks ``get_status``, which is the only thing that
can read ``min_supported_protocol_version`` and so the only thing that can say
**which end to upgrade** rather than merely that two numbers differ.

Two traps, both avoided here rather than documented elsewhere. The probe is
itself a bridge call, so it is issued through this module's own ``_request()``
and never through ``backend.send()``, or the first call in a process would
probe in order to probe. And the memo is per ``(host, port)`` and is dropped
whenever a call to that address fails to connect, because it is a claim about
what *this process* learned rather than about what is running - and wrong in the
ordinary way when Blender restarts under it.
"""

from __future__ import annotations

__all__ = (
    "BRIDGE_HOST_VARIABLE",
    "BRIDGE_PORT_VARIABLE",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "PROTOCOL_VERSION",
    "forget_handshakes",
    "get_connection_params",
    "send_command",
)

import json
import os
import socket

from mpfbmcp import observability

BRIDGE_HOST_VARIABLE = "MPFB_BRIDGE_HOST"
BRIDGE_PORT_VARIABLE = "MPFB_BRIDGE_PORT"

DEFAULT_HOST = "127.0.0.1"
# Not 9876, which is what both projects called "blender mcp" default to. This
# add-on is neither of them, and a user may well have one of them running.
DEFAULT_PORT = 9877

# The protocol version this client speaks and declares on every request. A
# duplicate of the bridge's own ``command_server.PROTOCOL_VERSION``, kept in
# step by hand because ``bridge/`` is a Blender extension, is not part of the
# pip package, and must not become an import dependency of it - importing it
# here would pull ``bpy`` into a process that has no Blender.
# ``tests/test_bridge_connection.py`` reads the add-on's source and asserts the
# two agree, skipping where the source is not beside this package.
PROTOCOL_VERSION = 2

# Bounds the whole round trip: how long Blender's main thread may be busy
# before this client gives up. The transport itself contributes nothing
# measurable - a request is a few hundred bytes of JSON - so effectively all of
# it is headroom for what a command does inside Blender. It is generous on
# purpose: the failure a short deadline produces is a *mutating* command that ran to
# completion being reported to its caller as a connection error, which is the
# worst answer this system can give. Note that the bridge's own
# ``_CLIENT_TIMEOUT`` of 10 s is a different quantity - it bounds silence while
# one request's bytes arrive, not the work the request asks for.
_TIMEOUT = 300.0

_RECV_BUFFER_SIZE = 65536

# The one slug this module produces itself. Every other slug in an envelope
# returned from here was written by the bridge.
_ERROR_PROTOCOL_MISMATCH = "protocol_mismatch"

_LOG = observability.get_logger(__name__)


class _Handshake:
    """What one probe of one address learned, and whether it permits calls."""

    __slots__ = ("compatible", "message", "bridge_protocol_version",
                 "min_supported_protocol_version")

    def __init__(self, compatible: bool, message: str = "",
                 bridge_protocol_version: object = None,
                 min_supported_protocol_version: object = None) -> None:
        self.compatible = compatible
        self.message = message
        self.bridge_protocol_version = bridge_protocol_version
        self.min_supported_protocol_version = min_supported_protocol_version

    def refusal(self) -> dict[str, object]:
        """This handshake as the error envelope every call to it answers with."""
        return {
            "status": "error",
            "error": _ERROR_PROTOCOL_MISMATCH,
            "message": self.message,
            "protocol_version": self.bridge_protocol_version,
            "min_supported_protocol_version": self.min_supported_protocol_version,
            "client_protocol_version": PROTOCOL_VERSION,
        }


# (host, port) -> _Handshake. A claim about what this process learned, not
# about what is running: see the module docstring.
_HANDSHAKES: dict[tuple[str, int], _Handshake] = {}


def forget_handshakes() -> None:
    """Drop every memo, so the next call to any address probes again.

    Exists for the tests, and for a caller that knows Blender restarted. The
    ordinary invalidation needs nobody to call anything: a refused connection
    drops the memo for that address by itself.
    """
    _HANDSHAKES.clear()


def get_connection_params() -> tuple[str, int]:
    """Read the bridge's host/port from the environment.

    ``MPFB_BRIDGE_HOST`` / ``MPFB_BRIDGE_PORT`` rather than anything carrying
    the ``MPFB_MCP_`` prefix: these name *the add-on being addressed*, where an
    ``MPFB_MCP_`` variable would say what this process does with a call it has
    already decided to make. The bridge add-on reads its own address from its
    preferences rather than from the environment; if it ever reads the
    environment, these are the two names it should read.
    """
    host = os.environ.get(BRIDGE_HOST_VARIABLE, DEFAULT_HOST)
    port = int(os.environ.get(BRIDGE_PORT_VARIABLE, str(DEFAULT_PORT)))
    return host, port


def send_command(command: str, params: dict[str, object] | None = None) -> dict[str, object]:
    """Ask the bridge to run one named command, and return its envelope.

    The answer is the bridge's own: ``status``, ``result`` or ``message``,
    ``error`` on a failure, and ``protocol_version``. Nothing here reshapes a
    successful one.

    Raises ``ConnectionError`` when the bridge is unreachable, times out, or
    answers something that cannot be parsed. An unreachable add-on is a
    different kind of fact from a command that failed, which is what
    ``mpfb_list_urls`` - the one tool that catches this - depends on.
    """
    host, port = get_connection_params()

    handshake = _handshake_for(host, port)
    if not handshake.compatible:
        # Every call fails the same way and none of them reaches Blender: two
        # ends that cannot agree on the protocol have nothing to say to each
        # other, and the sentence naming both versions is the whole diagnosis.
        return handshake.refusal()

    return _request(host, port, command, params or {})


def _handshake_for(host: str, port: int) -> _Handshake:
    """The memo for this address, probing once if there is none."""
    key = (host, port)
    remembered = _HANDSHAKES.get(key)
    if remembered is not None:
        return remembered

    answer = _request(host, port, "get_status", {})
    handshake = _handshake_from(host, port, answer)
    _HANDSHAKES[key] = handshake
    if not handshake.compatible:
        _LOG.warning("%s", handshake.message)
    return handshake


def _handshake_from(host: str, port: int, answer: dict[str, object]) -> _Handshake:
    """Read a probe's answer into a verdict about talking to this bridge.

    Three shapes of answer reach here. A ``get_status`` that succeeded carries
    both version numbers in its ``result``. A refusal carrying
    ``protocol_mismatch`` carries them at the top level, because the bridge
    puts them there - the probe declared a version the bridge will not serve,
    which is the same disagreement seen from the other side. Anything else
    means a bridge answered and said nothing about versions, and is treated as
    compatible: a handshake exists to catch a *mismatch*, and refusing to talk
    to something that never claimed a version would be the handshake inventing
    a failure rather than finding one.
    """
    if answer.get("status") == "ok":
        result = answer.get("result")
        if isinstance(result, dict):
            return _compatibility(host, port, result.get("protocol_version"),
                                  result.get("min_supported_protocol_version"))
        return _Handshake(True)

    if answer.get("error") == _ERROR_PROTOCOL_MISMATCH:
        return _compatibility(host, port, answer.get("protocol_version"),
                              answer.get("min_supported_protocol_version"))

    return _Handshake(True)


def _compatibility(host: str, port: int, bridge_version: object,
                   minimum: object) -> _Handshake:
    """Compare this client's version against the pair the bridge reports."""
    if not isinstance(bridge_version, int) or isinstance(bridge_version, bool):
        return _Handshake(True)
    if not isinstance(minimum, int) or isinstance(minimum, bool):
        minimum = bridge_version

    address = "{:s}:{:d}".format(host, port)
    if PROTOCOL_VERSION < minimum:
        return _Handshake(
            False,
            "This mpfb-mcp speaks MPFB Bridge protocol version {:d}, and the bridge at {:s} "
            "accepts nothing older than version {:d} (it speaks {:d}). Upgrade mpfb-mcp.".format(
                PROTOCOL_VERSION, address, minimum, bridge_version),
            bridge_version, minimum)
    if PROTOCOL_VERSION > bridge_version:
        return _Handshake(
            False,
            "This mpfb-mcp speaks MPFB Bridge protocol version {:d}, and the bridge at {:s} "
            "speaks version {:d} (accepting requests from {:d} upwards). Upgrade the MPFB "
            "Bridge add-on.".format(PROTOCOL_VERSION, address, bridge_version, minimum),
            bridge_version, minimum)
    return _Handshake(True, "", bridge_version, minimum)


def _request(host: str, port: int, command: str,
             params: dict[str, object]) -> dict[str, object]:
    """One request, one connection, one answer. The whole protocol is here.

    ``protocol_version`` is declared on every request rather than only on the
    probe: it costs nothing and it is what makes the bridge's own
    ``protocol_mismatch`` refusal reachable for a client whose memo is stale.
    """
    request = json.dumps({
        "command": command,
        "params": params,
        "protocol_version": PROTOCOL_VERSION,
    })

    # Opened before the socket block, for the reason the generated path opens
    # its record there: a call that hangs, times out or takes Blender down has
    # to leave behind the request that did it. The exact string that goes on
    # the wire is what is recorded, so the record cannot drift from the call.
    record = observability.begin_command(command, request)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(_TIMEOUT)
            sock.connect((host, port))
            sock.sendall((request + "\0").encode("utf-8"))

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
        _HANDSHAKES.pop((host, port), None)
        raise ConnectionError(
            "Cannot connect to the MPFB Bridge at {:s}:{:d}. The bridge is a Blender add-on of "
            "its own, separate from MPFB: it must be installed and enabled, and its command "
            "server started from the add-on's preferences panel, which it is not until somebody "
            "starts it.".format(host, port)
        ) from ex
    except socket.timeout as ex:
        record.failed(ex)
        _HANDSHAKES.pop((host, port), None)
        raise ConnectionError(
            "The MPFB Bridge at {:s}:{:d} did not answer within {:.0f} seconds".format(
                host, port, _TIMEOUT)
        ) from ex
    except OSError as ex:
        record.failed(ex)
        _HANDSHAKES.pop((host, port), None)
        raise ConnectionError(
            "Socket error communicating with the MPFB Bridge at {:s}:{:d}: {:s}".format(
                host, port, str(ex))
        ) from ex

    if not buf:
        empty = ConnectionError(
            "Empty response from the MPFB Bridge at {:s}:{:d}".format(host, port))
        record.failed(empty)
        _HANDSHAKES.pop((host, port), None)
        raise empty

    line, _sep, _rest = buf.partition(b"\0")
    try:
        # json.loads takes bytes, so the frame is never decoded by hand - a
        # multi-byte character split across two recv() calls is a non-issue
        # rather than a bug waiting for the first non-ASCII asset name.
        response: dict[str, object] = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        record.failed(ex)
        _HANDSHAKES.pop((host, port), None)
        raise ConnectionError(
            "Invalid response from the MPFB Bridge at {:s}:{:d}: {:s}".format(
                host, port, str(ex))
        ) from ex

    record.finished(response)
    # A no-op unless this is an error envelope and the record is enabled; see
    # observability._CallRecord.annotate().
    return record.annotate(response)
