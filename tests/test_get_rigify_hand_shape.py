# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_rigify_hand_shape tool: argument validation, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. ``body_parts`` goes through
``arguments.validated_body_parts``, as every posing tool's does, and **which
names are hands is deliberately not checked here**: ``left_arm`` crosses the
socket and comes back as ``unknown_body_parts``, as it would from any posing
tool.

Everything the tool answers - a hand at rest is ``open``, a scaled master read
as the curl it implies and as a hook, ``tip`` on a moved and turned rig, every
rig that is refused, and that nothing changes - is checked against a real MPFB
in ``bridge/test/tests/ccc_reading/get_rigify_hand_shape_test.py``.

Run with::

    python -m unittest tests.test_get_rigify_hand_shape -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_rigify_hand_shape

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_rigify_hand_shape.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_rigify_hand_shape"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def test_a_default_call_reads_both_hands_of_the_active_object(self):
        # None rather than both names: the default is the bridge's, defined once.
        self.assertEqual(self._sent(), {"name": None, "body_parts": None})

    def test_body_parts_reach_the_wire_as_given(self):
        self.assertEqual(self._sent(name="Human", body_parts=["right_hand"]),
                         {"name": "Human", "body_parts": ["right_hand"]})

    def test_a_body_part_that_is_not_a_hand_is_not_checked_here(self):
        self.assertEqual(self._sent(body_parts=["left_arm"])["body_parts"], ["left_arm"])

    def test_a_badly_shaped_body_parts_is_rejected_locally(self):
        for bad in ("left_hand", [], ["left_hand", "left_hand"], [""], [1], True):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(body_parts=bad)
                send_command.assert_not_called()

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()


class GetRigifyHandShapeOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_rigify_hand_shape": fake_bridge.ok_envelope(
                "get_rigify_hand_shape",
                {"found": True, "ready": False, "blocked_by": "rig_not_supported",
                 "supported_rigs": ["rigify_generated.human", "rigify_generated.human_toes"]}),
        })

    def test_the_tool_sends_the_get_rigify_hand_shape_command(self) -> None:
        self.call(name="Human", body_parts=["left_hand"])

        self.assertEqual(self.bridge.commands()[-1], "get_rigify_hand_shape")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "body_parts": ["left_hand"]})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["blocked_by"], "rig_not_supported")


if __name__ == "__main__":
    unittest.main()
