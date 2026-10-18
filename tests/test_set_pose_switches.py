# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_set_pose_switches tool: entry shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). Only the shape of
an entry is checked here: known keys, ``body_part`` and ``switch`` non-empty
strings named once as a pair, ``value`` a finite number or a ``bool``, and
``raw`` a real ``bool``. **Neither the body part nor the switch vocabulary is
checked here**, nor a value's type or range against the switch: those are the
live rig's properties.

Every snap in both directions with its ``snap_error``, the same switches raw,
the refusals and the chains checked against the generated ``rig_ui.py`` are
``bridge/test/tests/ddd_mutating/set_pose_switches_test.py``'s.

Run with::

    python -m unittest tests.test_set_pose_switches -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import set_pose_switches

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_pose_switches.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_set_pose_switches"].fn


class EntryShapeTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def _refused(self, switches):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(switches=switches)
        send_command.assert_not_called()

    def test_a_default_call_sends_an_empty_batch_for_the_active_object(self):
        self.assertEqual(self._sent(), {"name": None, "switches": []})

    def test_numbers_and_bools_reach_the_wire_as_given(self):
        switches = [{"body_part": "left_arm", "switch": "IK_FK", "value": 1.0},
                    {"body_part": "left_arm", "switch": "pole_vector", "value": True},
                    {"body_part": "left_leg", "switch": "IK_parent", "value": 2, "raw": True}]
        self.assertEqual(self._sent(name="Human", switches=switches)["switches"], switches)

    def test_an_unknown_switch_is_not_checked_here(self):
        sent = self._sent(switches=[{"body_part": "tail", "switch": "wag", "value": 1}])
        self.assertEqual(sent["switches"][0]["switch"], "wag")

    def test_a_badly_shaped_entry_is_refused(self):
        for entry in ({"body_part": "left_arm", "switch": "IK_FK"},
                      {"body_part": "left_arm", "switch": "IK_FK", "value": "1"},
                      {"body_part": "left_arm", "switch": "IK_FK", "value": float("nan")},
                      {"body_part": "left_arm", "switch": "IK_FK", "value": None},
                      {"body_part": "", "switch": "IK_FK", "value": 1},
                      {"body_part": "left_arm", "switch": 1, "value": 1},
                      {"body_part": "left_arm", "switch": "IK_FK", "value": 1, "raw": 1},
                      {"body_part": "left_arm", "switch": "IK_FK", "value": 1, "snap": True},
                      "IK_FK"):
            with self.subTest(entry=entry):
                self._refused([entry])

    def test_a_switch_named_twice_is_refused(self):
        self._refused([{"body_part": "left_arm", "switch": "IK_FK", "value": 1},
                       {"body_part": "left_arm", "switch": "IK_FK", "value": 0}])

    def test_the_same_switch_on_two_body_parts_is_two_switches(self):
        switches = [{"body_part": "left_arm", "switch": "IK_FK", "value": 1},
                    {"body_part": "right_arm", "switch": "IK_FK", "value": 1}]
        self.assertEqual(len(self._sent(switches=switches)["switches"]), 2)

    def test_switches_must_be_a_list(self):
        for switches in ("IK_FK", {"body_part": "left_arm"}, True):
            with self.subTest(switches=switches):
                self._refused(switches)


class SetPoseSwitchesOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_pose_switches": fake_bridge.ok_envelope(
                "set_pose_switches", {"found": True, "ready": False,
                                      "blocked_by": "rig_has_no_switches", "performed": False}),
        })

    def test_the_tool_sends_the_set_pose_switches_command(self) -> None:
        self.call(name="Human",
                  switches=[{"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}])

        self.assertEqual(self.bridge.commands()[-1], "set_pose_switches")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "switches": [{"body_part": "left_arm",
                                                         "switch": "IK_FK", "value": 1.0}]})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["blocked_by"], "rig_has_no_switches")
