# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_expression tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). What the tool
*answers* - the stack rows, a row whose file is gone, the aggregate, clamping,
and above all ``matches_stack`` / ``unexplained_face_units`` - is checked against
a real MPFB in ``bridge/test/tests/ttt_get_expression_test.py``, together with
the rule that it does not restate ``mpfb_get_face_units``' 52 live values.

Run with::

    python -m unittest tests.test_get_expression -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_expression

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_expression.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_expression"].fn


class ArgumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.tool = _tool_callable()

    def test_a_call_with_no_arguments_is_legal(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertEqual(send_command.call_args[0],
                         ("get_expression", {"name": None, "refresh": False}))

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], object(), "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()

    def test_refresh_must_be_a_real_bool(self):
        for bad in ("false", "true", 0, 1, None):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(refresh=bad)
                send_command.assert_not_called()

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.rig", refresh=True)
        self.assertEqual(send_command.call_args[0][1], {"name": "Human.rig", "refresh": True})


class GetExpressionOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_expression": fake_bridge.ok_envelope(
                "get_expression", {"found": True, "matches_stack": True}),
        })

    def test_the_tool_sends_the_get_expression_command(self) -> None:
        self.call(name="Human")

        self.assertEqual(self.bridge.commands()[-1], "get_expression")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "refresh": False})

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="get_expression", state="absent"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
