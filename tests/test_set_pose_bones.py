# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_set_pose_bones tool: entry shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. Only the shape of an entry is checked here - known
keys, at most one change of each kind and at least one, vectors of finite
numbers keyed by the frame's axes, rotations of exactly ``axis`` and
``degrees``, positive scale factors, a real ``bool`` for ``symmetry``, a bone
named once. **No bone vocabulary is checked here**, per
[validate the shape, never the vocabulary](../specifications/tool-interface.md#validate-before-crossing-the-socket):
which bones exist and which a write may move is the rig's.

Everything the tool answers - each change kind on a moved and turned rig,
parent-before-child order, symmetry, every refusal and the rollback, achieved
against an IK chain past reach - is checked against a real MPFB in
``bridge/test/tests/ddd_mutating/set_pose_bones_test.py``.

Run with::

    python -m unittest tests.test_set_pose_bones -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import set_pose_bones

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_pose_bones.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_set_pose_bones"].fn


class EntryShapeTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def _refused(self, bones):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(bones=bones)
        send_command.assert_not_called()

    def test_a_default_call_sends_an_empty_batch_for_the_active_object(self):
        # The bridge answers "named nothing" itself, so that it is said in one place.
        self.assertEqual(self._sent(), {"name": None, "bones": []})

    def test_every_change_kind_reaches_the_wire_as_numbers(self):
        bones = [
            {"bone": "hand_ik.L", "move_by": {"up": 1}},
            {"bone": "hand_ik.R", "move_to": {"forward": 0.2, "left": -0.4, "up": 1.1}},
            {"bone": "torso", "rotate_by": {"axis": {"up": 1}, "degrees": 30}},
            {"bone": "chest", "rotate_to": {"axis": None, "degrees": 0}},
            {"bone": "head", "aim": {"forward": 1}, "twist": -5},
            {"bone": "f_index.01_master.L", "scale_to": {"y": 0.5}, "symmetry": True},
        ]
        sent = self._sent(name="Human", bones=bones)["bones"]
        self.assertEqual(sent[0], {"bone": "hand_ik.L", "move_by": {"up": 1.0}})
        self.assertIsInstance(sent[0]["move_by"]["up"], float)
        self.assertEqual(sent[2]["rotate_by"], {"axis": {"up": 1.0}, "degrees": 30.0})
        self.assertEqual(sent[3]["rotate_to"], {"axis": None, "degrees": 0.0},
                         "rotate_to takes a read-back of a bone at rest")
        self.assertEqual(sent[4], {"bone": "head", "aim": {"forward": 1.0}, "twist": -5.0})
        self.assertEqual(sent[5]["symmetry"], True)

    def test_an_unknown_bone_is_not_checked_here(self):
        self.assertEqual(self._sent(bones=[{"bone": "elbow", "move_by": {"up": 0.1}}])
                         ["bones"][0]["bone"], "elbow")

    def test_a_misspelled_key_is_refused(self):
        self._refused([{"bone": "hand_ik.L", "move_too": {"up": 0.1}}])

    def test_two_changes_of_one_kind_or_none_are_refused(self):
        for entry in ({"bone": "a", "move_by": {"up": 1}, "move_to": {"up": 1}},
                      {"bone": "a", "rotate_by": {"axis": {"up": 1}, "degrees": 1},
                       "aim": {"up": 1}},
                      {"bone": "a"},
                      {"bone": "a", "symmetry": True}):
            with self.subTest(entry=entry):
                self._refused([entry])

    def test_a_bone_named_twice_is_refused(self):
        self._refused([{"bone": "a", "move_by": {"up": 1}}, {"bone": "a", "scale_to": {"y": 2}}])

    def test_a_badly_shaped_vector_is_refused(self):
        for vector in ({}, {"x": 1}, {"up": "1"}, {"up": True}, {"up": float("nan")},
                       {"up": float("inf")}, [0, 0, 1], None):
            with self.subTest(vector=vector):
                self._refused([{"bone": "a", "move_by": vector}])

    def test_a_badly_shaped_rotation_is_refused(self):
        for rotation in ({"axis": {"up": 1}}, {"degrees": 10},
                         {"axis": {"up": 1}, "degrees": True},
                         {"axis": {"up": 0}, "degrees": 10},
                         {"axis": {"up": 1}, "degrees": 10, "extra": 1}):
            with self.subTest(rotation=rotation):
                self._refused([{"bone": "a", "rotate_by": rotation}])
        # Only rotate_to takes axis null: a relative rotation needs an axis.
        self._refused([{"bone": "a", "rotate_by": {"axis": None, "degrees": 10}}])

    def test_aim_twist_and_scale_are_checked(self):
        for entry in ({"bone": "a", "aim": {"up": 0}},
                      {"bone": "a", "move_by": {"up": 1}, "twist": 5},
                      {"bone": "a", "aim": {"up": 1}, "twist": "5"},
                      {"bone": "a", "scale_to": {"y": 0}},
                      {"bone": "a", "scale_to": {"y": -1}},
                      {"bone": "a", "scale_to": {"w": 1}},
                      {"bone": "a", "scale_to": {}},
                      {"bone": "a", "scale_to": {"y": 1}, "symmetry": "true"}):
            with self.subTest(entry=entry):
                self._refused([entry])

    def test_bones_and_bone_must_be_shaped(self):
        for bones in ("hand_ik.L", {"bone": "a"}, ["a"], [{"bone": ""}],
                      [{"bone": 1, "move_by": {"up": 1}}]):
            with self.subTest(bones=bones):
                self._refused(bones)

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()


class SetPoseBonesOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_pose_bones": fake_bridge.ok_envelope(
                "set_pose_bones", {"found": True, "ready": False, "blocked_by": "rig_not_found",
                                   "performed": False}),
        })

    def test_the_tool_sends_the_set_pose_bones_command(self) -> None:
        self.call(name="Human", bones=[{"bone": "torso", "move_by": {"up": -0.3}}])

        self.assertEqual(self.bridge.commands()[-1], "set_pose_bones")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "bones": [{"bone": "torso",
                                                      "move_by": {"up": -0.3}}]})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["blocked_by"], "rig_not_found")
