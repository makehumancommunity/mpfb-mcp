# SPDX-License-Identifier: GPL-3.0-or-later

"""
The blender_mcp add-on, faked well enough to exercise the wire protocol.

Holds no tests. It is the throwaway local TCP server that stands in for the
add-on's socket server, plus the environment-variable bookkeeping every test
that points mpfb-mcp at it needs. It lives here rather than in one test module
because two modules now need it: ``test_connection`` for the framing and the
error paths, and ``test_observability`` for what is written to disk around a
call.

The server is deliberately able to do three things a canned response cannot:
answer differently per request (``responder``), answer *nothing* and close the
connection, and keep the raw request bytes so that a test can assert the bytes
on the wire did not change.
"""

from __future__ import annotations

__all__ = (
    "EnvVarTestCase",
    "FakeAddonServer",
)

import json
import os
import socketserver
import threading
import unittest

_RECV_BUFFER_SIZE = 65536


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
            # that leaves a program on disk but no response is provoked.
            return
        self.request.sendall((json.dumps(response) + "\0").encode("utf-8"))


class FakeAddonServer(socketserver.TCPServer):
    """A canned response, or a callable deciding one per request."""

    allow_reuse_address = True

    def __init__(self, response: dict[str, object] | None = None,
                 responder=None) -> None:
        super().__init__(("localhost", 0), _RequestHandler)
        self.response = response
        self.responder = responder
        self.requests: list[bytes] = []

    def respond_to(self, request: dict[str, object]) -> dict[str, object] | None:
        if self.responder is not None:
            return self.responder(request)
        return self.response


def _restore_env_var(name: str, old_value: str | None) -> None:
    if old_value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = old_value


class EnvVarTestCase(unittest.TestCase):
    """Sets environment variables for the duration of a test, and restores them."""

    def set_env_var(self, name: str, value: str | None) -> None:
        self.addCleanup(_restore_env_var, name, os.environ.get(name))
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def point_env_at(self, host: str, port: int) -> None:
        self.set_env_var("BLENDER_MCP_HOST", host)
        self.set_env_var("BLENDER_MCP_PORT", str(port))

    def run_fake_server(self, response: dict[str, object] | None = None,
                        responder=None) -> FakeAddonServer:
        """Start a fake add-on on a free port and point the environment at it."""
        server = FakeAddonServer(response=response, responder=responder)
        # A short poll interval because ``shutdown()`` waits for the loop to
        # notice, and the default half-second is paid once per test that starts
        # one of these. That was a rounding error while two modules used this
        # and is not one now that a test can start a fake add-on *and* a fake
        # bridge to assert which of them was spoken to.
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01},
                                  daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        host, port = server.server_address
        self.point_env_at(host, port)
        return server
