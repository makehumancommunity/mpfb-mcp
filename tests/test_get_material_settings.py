# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_material_settings tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. Only the two arguments' shape is checked here, and
``section`` is checked as a vocabulary because it is this package's own - the
preset's three keys - rather than MPFB's.

Everything the tool answers - every section and every reason it may not
apply, the linked flags, the ranges, and agreement with MPFB's serializer key
for key - is checked against a real MPFB in
``bridge/test/tests/ccc_reading/get_material_settings_test.py``.

Run with::

    python -m unittest tests.test_get_material_settings -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_material_settings

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_material_settings.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_material_settings"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def test_a_default_call_reads_every_section_of_the_active_object(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertEqual(send_command.call_args[0][1], {"name": None, "section": None})

    def test_each_section_is_accepted(self):
        for section in ("eyes", "skin", "color_adjustments"):
            with self.subTest(section=section):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    send_command.return_value = {"status": "ok", "result": {}}
                    self.tool(section=section)
                self.assertEqual(send_command.call_args[0][1]["section"], section)

    def test_an_unknown_section_is_rejected_locally(self):
        # The preset's keys, not the node names or a singular: "eye", "colour"
        # and the node name "colorgroup" are all plausible and all wrong.
        for bad in ("eye", "Eyes", "colour_adjustments", "colorgroup", "", 1, True, []):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(section=bad)
                send_command.assert_not_called()

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable", "message": "no MPFB"}
            response = self.tool()
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GetMaterialSettingsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_material_settings": fake_bridge.ok_envelope(
                "get_material_settings", {"found": True, "eyes": None, "skin": None,
                                          "color_adjustments": None}),
        })

    def test_the_tool_sends_the_get_material_settings_command(self) -> None:
        self.call(name="Human", section="skin")

        self.assertEqual(self.bridge.commands()[-1], "get_material_settings")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "section": "skin"})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["eyes"], None)
