# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for mpfbmcp.connection's wire protocol.

Runs a tiny local TCP server standing in for the blender_mcp add-on, so the
framing (JSON + NUL-delimiter) and error paths are exercised without needing
Blender. The server and the environment-variable bookkeeping live in
``tests/fake_addon.py``, shared with ``tests/test_observability.py``. Run with::

    python -m unittest tests.test_connection -v
"""

__all__ = ()

import socket
import unittest

from mpfbmcp import connection
from tests import fake_addon


class SendCodeTests(fake_addon.EnvVarTestCase):
    def test_round_trip_ok_response(self) -> None:
        self.run_fake_server({"status": "ok", "result": {"object_name": "Human"}})

        response = connection.send_code("result = {}", strict_json=True)

        self.assertEqual(response, {"status": "ok", "result": {"object_name": "Human"}})

    def test_round_trip_error_response(self) -> None:
        self.run_fake_server({"status": "error", "message": "boom"})

        response = connection.send_code("raise RuntimeError('boom')")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "boom")

    def test_get_connection_params_defaults(self) -> None:
        self.set_env_var("BLENDER_MCP_HOST", None)
        self.set_env_var("BLENDER_MCP_PORT", None)
        self.assertEqual(connection.get_connection_params(), ("localhost", 9876))

    def test_connection_refused_raises_connection_error(self) -> None:
        # Bind and immediately close, so the port is very likely free but was just valid.
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("localhost", 0))
        free_port = probe.getsockname()[1]
        probe.close()

        self.point_env_at("localhost", free_port)

        with self.assertRaises(ConnectionError):
            connection.send_code("result = {}")

    def test_a_closed_connection_with_no_reply_raises_connection_error(self) -> None:
        self.run_fake_server(responder=lambda request: None)

        with self.assertRaises(ConnectionError):
            connection.send_code("result = {}")


if __name__ == "__main__":
    unittest.main()
