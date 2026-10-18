# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_pose_controls tool: argument validation, and what crosses the
socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. Only the shape of the arguments is checked here.
``body_parts``, ``roles`` and ``switch_names`` are lists of distinct non-empty
strings, and **their vocabulary is deliberately not checked**, per
[validate the shape, never the vocabulary](../specifications/tool-interface.md#validate-before-crossing-the-socket):
the body parts and roles are the bridge's, which names them when one is wrong,
and the switch names are the rig's own
([FR 044](../feature-requests/done/044-switches-filter/README.md)).
``include_hidden`` and ``compact`` are real bools
([FR 043](../feature-requests/done/043-narrower-pose-controls/README.md)).

Everything the tool answers - the classification of every rig family, the character frame, the switches with their parent names, the helpers and what they drive, the filters and the counts that explain them, the refusals, and that nothing is changed - is checked against a real MPFB in
``bridge/test/tests/ccc_reading/get_pose_controls_test.py``.

Run with::

    python -m unittest tests.test_get_pose_controls -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_pose_controls

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_pose_controls.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_pose_controls"].fn


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
        # The hidden default and the full entry are the bridge's too, but
        # false/false is sent rather than left out, so the wire says what was
        # asked.
        self.assertEqual(self._sent(), {"name": None, "body_parts": None, "roles": None,
                                        "switch_names": None, "include_hidden": False,
                                        "compact": False})

    def test_body_parts_reach_the_wire_as_given(self):
        self.assertEqual(self._sent(name="Human", body_parts=["left_arm", "face"]),
                         {"name": "Human", "body_parts": ["left_arm", "face"], "roles": None,
                          "switch_names": None, "include_hidden": False, "compact": False})

    def test_the_narrowing_arguments_reach_the_wire_as_given(self):
        self.assertEqual(
            self._sent(roles=["ik_control", "pole"], switch_names=["IK_FK", "IK_parent"],
                       include_hidden=True, compact=True),
            {"name": None, "body_parts": None, "roles": ["ik_control", "pole"],
             "switch_names": ["IK_FK", "IK_parent"], "include_hidden": True, "compact": True})

    def test_an_unknown_body_part_is_not_checked_here(self):
        # The vocabulary is the bridge's: "elbows" crosses the socket and comes
        # back as unknown_body_parts with known_body_parts beside it.
        self.assertEqual(self._sent(body_parts=["elbows"])["body_parts"], ["elbows"])

    def test_an_unknown_role_is_not_checked_here(self):
        # As with body parts: "elbow" comes back as unknown_roles with
        # known_roles beside it.
        self.assertEqual(self._sent(roles=["elbow"])["roles"], ["elbow"])

    def test_an_unknown_switch_name_is_not_checked_here(self):
        # The switch names are the rig's: human_toes has parent_switch and
        # game_engine does not, so there is no list here to check against, and
        # "IK_FKK" comes back as unknown_switch_names with known_switch_names.
        self.assertEqual(self._sent(switch_names=["IK_FKK"])["switch_names"], ["IK_FKK"])

    def test_a_badly_shaped_switch_names_is_rejected_locally(self):
        for bad in ("IK_FK", [], ["IK_FK", "IK_FK"], [""], ["  "], [1], [None],
                    True, {"IK_FK": True}, [{"switch": "IK_FK"}]):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(switch_names=bad)
                send_command.assert_not_called()

    def test_a_badly_shaped_roles_is_rejected_locally(self):
        for bad in ("pole", [], ["pole", "pole"], [""], ["  "], [1], [None],
                    True, {"pole": True}):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(roles=bad)
                send_command.assert_not_called()

    def test_the_two_flags_must_be_real_bools(self):
        for argument in ("include_hidden", "compact"):
            for bad in ("false", "true", 0, 1, None, []):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

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


class GetPoseControlsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_pose_controls": fake_bridge.ok_envelope(
                "get_pose_controls", {"found": True, "ready": False, "blocked_by": "rig_not_found"}),
        })

    def test_the_tool_sends_the_get_pose_controls_command(self) -> None:
        self.call(name="Human", body_parts=["left_hand"])

        self.assertEqual(self.bridge.commands()[-1], "get_pose_controls")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "body_parts": ["left_hand"], "roles": None,
                          "switch_names": None, "include_hidden": False, "compact": False})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["blocked_by"], "rig_not_found")
