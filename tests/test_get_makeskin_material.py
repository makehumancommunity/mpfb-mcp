# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_makeskin_material tool: one argument's shape, and what crosses.

Two layers (see ``tests/test_list_objects.py``, the template). Everything it answers is
``bridge/test/tests/ccc_reading/get_makeskin_material_test.py``'s, against materials MPFB
built itself.

Run with::

    python -m unittest tests.test_get_makeskin_material -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_makeskin_material

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_makeskin_material.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_makeskin_material"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def test_the_name_crosses_the_socket(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.belt")
        self.assertEqual(send_command.call_args[0], ("get_makeskin_material",
                                                     {"name": "Human.belt"}))

    def test_an_omitted_name_is_the_active_object(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertIsNone(send_command.call_args[0][1]["name"])

    def test_a_bad_name_never_crosses(self):
        for name in ("", "   ", 3):
            with self.subTest(name=name):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=name)
                send_command.assert_not_called()


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_makeskin_material": fake_bridge.ok_envelope("get_makeskin_material",
                                                             {"found": True}),
        })
        envelope = _tool_callable()(name="Human.belt")
        self.assertEqual(envelope["result"], {"found": True})
        self.assertEqual(server.commands()[-1], "get_makeskin_material")


if __name__ == "__main__":
    unittest.main()
