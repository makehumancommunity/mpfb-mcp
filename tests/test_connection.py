# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for mpfbmcp.connection's wire protocol.

Runs a tiny local TCP server standing in for the blender_mcp add-on, so the
framing (JSON + NUL-delimiter) and error paths are exercised without needing
Blender. Run with::

    python -m unittest tests.test_connection -v
"""

__all__ = ()

import json
import os
import socket
import socketserver
import threading
import unittest

from mpfbmcp import connection


class _EchoRequestHandler(socketserver.BaseRequestHandler):
    """Reads one NUL-terminated request and replies with the server's canned response."""

    def handle(self) -> None:
        buf = bytearray()
        while b"\0" not in buf:
            chunk = self.request.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
        json.loads(buf.partition(b"\0")[0].decode("utf-8"))  # validate the request parses
        response = self.server.response  # type: ignore[attr-defined]
        self.request.sendall((json.dumps(response) + "\0").encode("utf-8"))


class _FakeAddonServer(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, response: dict[str, object]) -> None:
        super().__init__(("localhost", 0), _EchoRequestHandler)
        self.response = response


def _restore_env_var(name: str, old_value: str | None) -> None:
    if old_value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = old_value


class _EnvVarConnectionTestCase(unittest.TestCase):
    """Points BLENDER_MCP_HOST/PORT at a given address for the duration of a test."""

    def _set_env_var(self, name: str, value: str | None) -> None:
        self.addCleanup(_restore_env_var, name, os.environ.get(name))
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    def _point_env_at(self, host: str, port: int) -> None:
        self._set_env_var("BLENDER_MCP_HOST", host)
        self._set_env_var("BLENDER_MCP_PORT", str(port))


class SendCodeTests(_EnvVarConnectionTestCase):
    def _run_fake_server(self, response: dict[str, object]) -> tuple[str, int]:
        server = _FakeAddonServer(response)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        return server.server_address

    def test_round_trip_ok_response(self) -> None:
        host, port = self._run_fake_server({"status": "ok", "result": {"object_name": "Human"}})
        self._point_env_at(host, port)

        response = connection.send_code("result = {}", strict_json=True)

        self.assertEqual(response, {"status": "ok", "result": {"object_name": "Human"}})

    def test_round_trip_error_response(self) -> None:
        host, port = self._run_fake_server({"status": "error", "message": "boom"})
        self._point_env_at(host, port)

        response = connection.send_code("raise RuntimeError('boom')")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "boom")

    def test_get_connection_params_defaults(self) -> None:
        self._set_env_var("BLENDER_MCP_HOST", None)
        self._set_env_var("BLENDER_MCP_PORT", None)
        self.assertEqual(connection.get_connection_params(), ("localhost", 9876))

    def test_connection_refused_raises_connection_error(self) -> None:
        # Bind and immediately close, so the port is very likely free but was just valid.
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("localhost", 0))
        free_port = probe.getsockname()[1]
        probe.close()

        self._point_env_at("localhost", free_port)

        with self.assertRaises(ConnectionError):
            connection.send_code("result = {}")


if __name__ == "__main__":
    unittest.main()
