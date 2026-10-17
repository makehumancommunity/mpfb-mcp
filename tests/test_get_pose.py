# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_pose tool: argument validation, and what crosses the
socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. Only the shape of the two arguments is checked here.
``body_parts`` is a list of distinct non-empty strings, and **its vocabulary is
deliberately not checked**, per
[validate the shape, never the vocabulary](../specifications/tool-interface.md#validate-before-crossing-the-socket):
the body parts are the bridge's, which names them when one is wrong.

Everything the tool answers - what is off rest (scale included), the landmarks on deforming bones, reach and stretch with stretch on and off, the character frame on a moved and turned rig, and that nothing is changed - is checked against a real MPFB in
``bridge/test/tests/ccc_reading/get_pose_test.py``.

Run with::

    python -m unittest tests.test_get_pose -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_pose

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_pose.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_pose"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def test_a_default_call_asks_about_the_active_object_with_the_default_body_parts(self):
        # None, not a list: the default (every part but the face) is the
        # bridge's to fill in, so that it is defined in one place.
        self.assertEqual(self._sent(), {"name": None, "body_parts": None})

    def test_body_parts_reach_the_wire_as_given(self):
        self.assertEqual(self._sent(name="Human", body_parts=["left_arm", "face"]),
                         {"name": "Human", "body_parts": ["left_arm", "face"]})

    def test_an_unknown_body_part_is_not_checked_here(self):
        # The vocabulary is the bridge's: "elbows" crosses the socket and comes
        # back as unknown_body_parts with known_body_parts beside it.
        self.assertEqual(self._sent(body_parts=["elbows"])["body_parts"], ["elbows"])

    def test_a_badly_shaped_body_parts_is_rejected_locally(self):
        for bad in ("left_arm", [], ["left_arm", "left_arm"], [""], ["  "], [1], [None],
                    True, {"left_arm": True}):
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

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable", "message": "no MPFB"}
            response = self.tool()
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GetPoseOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_pose": fake_bridge.ok_envelope(
                "get_pose", {"found": True, "ready": False, "blocked_by": "rig_not_found"}),
        })

    def test_the_tool_sends_the_get_pose_command(self) -> None:
        self.call(name="Human", body_parts=["left_hand"])

        self.assertEqual(self.bridge.commands()[-1], "get_pose")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "body_parts": ["left_hand"]})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["blocked_by"], "rig_not_found")
