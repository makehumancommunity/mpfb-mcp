# SPDX-License-Identifier: GPL-3.0-or-later

"""
The MPFB Bridge add-on, faked well enough to exercise the client.

Holds no tests. It is to ``bridge_connection`` what ``fake_addon.py`` is to
``connection``: a throwaway local TCP server plus the environment-variable
bookkeeping every test that points mpfb-mcp at it needs. A sibling rather than
an extension of that module, for the reason the two clients are siblings - the
protocols differ, and a fake that served both would have to be told which one
it was being today.

It can do the three things a canned response cannot, and each is load-bearing
for at least one test here:

- **answer differently per request**, so that the ``get_status`` handshake probe
  and the command under test can be answered differently, which is what makes
  "the probe happens once per address" assertable at all;
- **answer nothing and close**, which is how a call that leaves a record but no
  response is provoked;
- **keep the raw request bytes**, so a test can assert what actually went on the
  wire rather than what the client meant to send.

The canned answers below are the bridge's own shapes, copied from
``bridge/mpfb_bridge/command_server.py``. They are duplicated rather than
imported for the same reason ``bridge_connection`` duplicates the protocol
itself: ``bridge/`` is a Blender extension that imports ``bpy``, and this suite
must keep running on a machine with no Blender installed.
"""

from __future__ import annotations

__all__ = (
    "BridgeTestCase",
    "FakeBridgeServer",
    "error_envelope",
    "ok_envelope",
    "status_result",
)

import json
import socketserver
import threading

from mpfbmcp import bridge_connection
from tests import fake_addon

_RECV_BUFFER_SIZE = 65536

# The bridge's own protocol version, as the fake reports it. Deliberately read
# from the client rather than hardcoded: a test wanting a *mismatch* says so by
# passing a different number, and one wanting agreement should not have to be
# edited when the protocol is bumped.
DEFAULT_PROTOCOL_VERSION = bridge_connection.PROTOCOL_VERSION


def status_result(protocol_version: int | None = None,
                  min_supported: int | None = None) -> dict[str, object]:
    """What ``get_status`` answers, trimmed to the keys the handshake reads."""
    if protocol_version is None:
        protocol_version = DEFAULT_PROTOCOL_VERSION
    if min_supported is None:
        min_supported = protocol_version
    return {
        "state": "ok",
        "message": "MPFB is loaded and initialized.",
        "candidate_modules": ["bl_ext.user_default.mpfb"],
        "bridge_version": "0.0.1",
        "protocol_version": protocol_version,
        "min_supported_protocol_version": min_supported,
    }


def ok_envelope(command: str, result: object,
                protocol_version: int | None = None) -> dict[str, object]:
    return {
        "status": "ok",
        "protocol_version": DEFAULT_PROTOCOL_VERSION
                            if protocol_version is None else protocol_version,
        "command": command,
        "result": result,
    }


def error_envelope(slug: str, message: str = "boom",
                   **extra: object) -> dict[str, object]:
    envelope: dict[str, object] = {
        "status": "error",
        "protocol_version": DEFAULT_PROTOCOL_VERSION,
        "error": slug,
        "message": message,
    }
    envelope.update(extra)
    return envelope


class _RequestHandler(socketserver.BaseRequestHandler):
    """Reads one NUL-terminated request and lets the server decide the reply."""

    def handle(self) -> None:
        buf = bytearray()
        while b"\0" not in buf:
            chunk = self.request.recv(_RECV_BUFFER_SIZE)
            if not chunk:
                break
            buf.extend(chunk)
        raw = bytes(buf)
        self.server.requests.append(raw)  # type: ignore[attr-defined]
        request = json.loads(raw.partition(b"\0")[0].decode("utf-8"))
        response = self.server.respond_to(request)  # type: ignore[attr-defined]
        if response is None:
            # Closes the connection having sent nothing, which is how a call
            # that leaves a record but no response is provoked.
            return
        # Raw bytes are passed through untouched, which is how a test says
        # "answer something that is not a well-formed frame" - invalid JSON, or
        # bytes after the delimiter. Anything else is encoded as the bridge
        # encodes it.
        encoded = (response if isinstance(response, bytes)
                   else (json.dumps(response) + "\0").encode("utf-8"))
        for start in range(0, len(encoded), self.server.chunk_size):  # type: ignore[attr-defined]
            self.request.sendall(encoded[start:start + self.server.chunk_size])  # type: ignore[attr-defined]


class FakeBridgeServer(socketserver.TCPServer):
    """A canned answer, or a callable deciding one per request.

    ``chunk_size`` exists for one test: an answer delivered in pieces, so that
    the client's read loop is exercised rather than assumed. The default sends
    it in one go, which is what a real bridge does for an answer this small.
    """

    allow_reuse_address = True

    def __init__(self, response: dict[str, object] | None = None,
                 responder=None, chunk_size: int = 1 << 20) -> None:
        super().__init__(("127.0.0.1", 0), _RequestHandler)
        self.response = response
        self.responder = responder
        self.chunk_size = chunk_size
        self.requests: list[bytes] = []

    def respond_to(self, request: dict[str, object]) -> dict[str, object] | None:
        if self.responder is not None:
            return self.responder(request)
        return self.response

    def decoded_requests(self) -> list[dict[str, object]]:
        """What arrived, as JSON. The bytes are kept; this is the convenience."""
        return [json.loads(raw.partition(b"\0")[0].decode("utf-8")) for raw in self.requests]

    def commands(self) -> list[str]:
        """The command names in the order they were asked for."""
        return [str(request.get("command")) for request in self.decoded_requests()]


class BridgeTestCase(fake_addon.EnvVarTestCase):
    """Points the bridge client at a fake, and forgets the handshake memo.

    The memo is process-wide and deliberately so - it is what stops a probe
    becoming a round trip per call - which means a test that left one behind
    would decide the outcome of the next test. Cleared in ``setUp`` *and*
    through a cleanup, because a test may install one on purpose.
    """

    def setUp(self) -> None:
        super().setUp()
        bridge_connection.forget_handshakes()
        self.addCleanup(bridge_connection.forget_handshakes)

    def point_env_at_bridge(self, host: str, port: int) -> None:
        self.set_env_var(bridge_connection.BRIDGE_HOST_VARIABLE, host)
        self.set_env_var(bridge_connection.BRIDGE_PORT_VARIABLE, str(port))

    def run_fake_bridge(self, response: dict[str, object] | None = None,
                        responder=None, chunk_size: int = 1 << 20) -> FakeBridgeServer:
        """Start a fake bridge on a free port and point the environment at it."""
        server = FakeBridgeServer(response=response, responder=responder,
                                  chunk_size=chunk_size)
        # A short poll interval because ``shutdown()`` waits for the loop to
        # notice, and the default half-second per server is paid by every test
        # in this file. The suite's value is that it runs in seconds.
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01},
                                  daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        host, port = server.server_address
        self.point_env_at_bridge(host, port)
        return server

    def run_answering_bridge(self, answers: dict[str, object]) -> FakeBridgeServer:
        """A fake bridge answering per command name.

        ``answers`` maps a command to the envelope it gets. A command with no
        entry is answered as an unknown command, which is what the real bridge
        does and what keeps a test from passing on a command it never declared.
        """
        def responder(request: dict[str, object]) -> dict[str, object]:
            command = str(request.get("command"))
            if command in answers:
                return answers[command]  # type: ignore[return-value]
            return error_envelope(
                "unknown_command", "There is no command named {!r}.".format(command),
                command=command, known_commands=sorted(answers))

        return self.run_fake_bridge(responder=responder)
