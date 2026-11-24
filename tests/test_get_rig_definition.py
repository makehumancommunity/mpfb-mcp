# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_rig_definition tool: argument shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). Shape only: ``rig`` optional
non-empty text, ``bone_names`` an optional non-empty list of distinct names, two real bools.
**No rig or bone vocabulary is checked here.** That a read-back is a write, the three places a
definition is read from, and that a read changes nothing are
``bridge/test/tests/ccc_reading/get_rig_definition_test.py``'s and
``bridge/test/tests/eee_composite/rig_roundtrip_test.py``'s.

Run with::

    python -m unittest tests.test_get_rig_definition -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_rig_definition

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_rig_definition.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_rig_definition"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def test_the_default_call_reaches_the_wire(self):
        self.assertEqual(self._sent(), {"name": None, "rig": None, "bone_names": None,
                                        "include_joints": False, "compact": False})

    def test_every_argument_reaches_the_wire(self):
        self.assertEqual(
            self._sent(name="Human", rig="default_no_toes", bone_names=["root", "spine05"],
                       include_joints=True, compact=True),
            {"name": "Human", "rig": "default_no_toes", "bone_names": ["root", "spine05"],
             "include_joints": True, "compact": True})

    def test_a_bad_shape_is_refused_before_sending(self):
        for arguments in ({"rig": ""}, {"rig": 3}, {"bone_names": []}, {"bone_names": "root"},
                          {"bone_names": ["a", "a"]}, {"bone_names": [""]},
                          {"include_joints": "true"}, {"compact": 1}, {"name": ""}):
            with self.subTest(arguments=arguments):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(**arguments)
                send_command.assert_not_called()

    def test_no_rig_vocabulary_is_checked_here(self):
        self.assertEqual(self._sent(rig="custom.not_installed")["rig"], "custom.not_installed")


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_rig_definition": fake_bridge.ok_envelope("get_rig_definition", {"bones": []}),
        })
        envelope = _tool_callable()(rig="default")
        self.assertEqual(envelope["result"], {"bones": []})
        self.assertEqual(server.commands()[-1], "get_rig_definition")


if __name__ == "__main__":
    unittest.main()
