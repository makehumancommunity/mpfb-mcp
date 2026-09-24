# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_character_summary tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template), and there is
almost nothing to validate locally, which is right: the tool takes one optional
name. What the tool *answers* - and above all that every field it shares with a
detailed tool equals that tool's answer on the same character - is checked
against a real MPFB in ``bridge/test/tests/eee_composite/get_character_summary_test.py``,
by dispatching both.

Run with::

    python -m unittest tests.test_get_character_summary -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_character_summary

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_character_summary.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_character_summary"].fn


class ArgumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.tool = _tool_callable()

    def test_a_call_with_no_arguments_is_legal(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertEqual(send_command.call_args[0], ("get_character_summary", {"name": None}))

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], object(), "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()

    def test_the_name_is_carried_across_unchanged(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.rigify")
        self.assertEqual(send_command.call_args[0][1], {"name": "Human.rigify"})


class GetCharacterSummaryOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_character_summary": fake_bridge.ok_envelope(
                "get_character_summary", {"found": True, "rig": None, "assets": []}),
        })

    def test_the_tool_sends_the_get_character_summary_command(self) -> None:
        response = self.call(name="Human")

        self.assertEqual(self.bridge.commands()[-1], "get_character_summary")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": "Human"})
        self.assertEqual(response["result"], {"found": True, "rig": None, "assets": []})

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="get_character_summary", state="absent"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
