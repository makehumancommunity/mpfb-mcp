# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_list_expressions tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. The tool takes one argument, so the first layer is
small. What MPFB actually answers - first-root precedence, the shadowed and
unreadable files its scan drops, the label fallback and the pack probe - is
checked against a real MPFB in ``bridge/test/tests/sss_list_expressions_test.py``.

Run with::

    python -m unittest tests.test_list_expressions -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import list_expressions

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_expressions.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_list_expressions"].fn


class ArgumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.tool = _tool_callable()

    def test_a_call_with_no_arguments_is_legal(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertEqual(send_command.call_args[0], ("list_expressions", {"refresh": False}))

    def test_refresh_must_be_a_real_bool(self):
        # "false" is a true value, and would re-probe for the pack on every call.
        for bad in ("false", "true", 0, 1, None):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(refresh=bad)
                send_command.assert_not_called()

    def test_refresh_is_carried_across(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(refresh=True)
        self.assertEqual(send_command.call_args[0][1], {"refresh": True})


class ListExpressionsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_expressions": fake_bridge.ok_envelope(
                "list_expressions", {"expressions": [], "count": 0, "roots": []}),
        })

    def test_the_tool_sends_the_list_expressions_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "list_expressions")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"refresh": False})

    def test_an_envelope_reaches_the_caller_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["roots"], [])
