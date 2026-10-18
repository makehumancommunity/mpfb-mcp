# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_reset_pose tool: argument shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). ``body_parts`` is
the posing tools' shared argument, and its vocabulary is not checked here;
``include_switches`` must be a real ``bool``. The default - every body part,
the face included - is the bridge's to fill in, so ``None`` is what is sent.

The reset with and without switches, ``restore_with`` fed back into the other
two tools to restore the pose exactly, ``not_restorable`` and an unclassified
rig are ``bridge/test/tests/ddd_mutating/reset_pose_test.py``'s.

Run with::

    python -m unittest tests.test_reset_pose -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import reset_pose

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    reset_pose.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_reset_pose"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def test_a_default_call_resets_everything_but_the_switches(self):
        self.assertEqual(self._sent(),
                         {"name": None, "body_parts": None, "include_switches": False})

    def test_arguments_reach_the_wire_as_given(self):
        self.assertEqual(self._sent(name="Human", body_parts=["face"], include_switches=True),
                         {"name": "Human", "body_parts": ["face"], "include_switches": True})

    def test_an_unknown_body_part_is_not_checked_here(self):
        self.assertEqual(self._sent(body_parts=["tail"])["body_parts"], ["tail"])

    def test_include_switches_must_be_a_real_bool(self):
        for bad in ("false", 0, 1, None):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(include_switches=bad)
                send_command.assert_not_called()

    def test_a_badly_shaped_body_parts_is_rejected_locally(self):
        for bad in ("face", [], ["face", "face"], [""], [1]):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(body_parts=bad)
                send_command.assert_not_called()


class ResetPoseOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "reset_pose": fake_bridge.ok_envelope(
                "reset_pose", {"found": True, "ready": True, "reset": False,
                               "restore_with": {}, "performed": False}),
        })

    def test_the_tool_sends_the_reset_pose_command(self) -> None:
        self.call(name="Human", include_switches=True)

        self.assertEqual(self.bridge.commands()[-1], "reset_pose")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "body_parts": None, "include_switches": True})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["restore_with"], {})
