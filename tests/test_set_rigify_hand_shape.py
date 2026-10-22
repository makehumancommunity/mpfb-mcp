# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_set_rigify_hand_shape tool: entry shape, names, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. Checked here: known keys (``fingres`` fails), at
least one of ``shape`` and ``fingers``, a finger holding ``curl``, ``spread``
or both and nothing else, the two amounts finite, in range and not ``bool``,
``symmetry`` a real ``bool``, and a ``body_part`` named once.

**Shape and finger names are checked here too**, being this package's own
vocabulary (like ``mode``) rather than the rig's; ``ShapeTableDriftTests``
reads the bridge's ``shared/rigify_hands.py`` as data and requires its tables
to be the ones this module holds, as ``tests/test_bridge_connection.py`` does
for ``PROTOCOL_VERSION``. **``body_part`` values are not checked here**: they
are the posing tools' vocabulary, answered bridge-side.

Everything the tool does - every shape reading back as itself, one finger
changed and nothing else, a shape with an override and ``symmetry``, the
segments reset and restored, every refusal and the rollback - is checked
against a real MPFB in ``bridge/test/tests/ddd_mutating/set_rigify_hand_shape_test.py``.

Run with::

    python -m unittest tests.test_set_rigify_hand_shape -v
"""

__all__ = ()

import ast
import os
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import set_rigify_hand_shape

from tests import fake_bridge

_BRIDGE_SOURCE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bridge", "mpfb_bridge", "shared", "rigify_hands.py")


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_rigify_hand_shape.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_set_rigify_hand_shape"].fn


class EntryShapeTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def _refused(self, hands):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(hands=hands)
        send_command.assert_not_called()

    def test_a_default_call_sends_an_empty_batch_for_the_active_object(self):
        # The bridge answers "named nothing" itself, so that it is said in one place.
        self.assertEqual(self._sent(), {"name": None, "hands": []})

    def test_a_shape_with_overrides_reaches_the_wire_as_numbers(self):
        sent = self._sent(name="Human", hands=[
            {"body_part": "left_hand", "shape": "fist", "fingers": {"index": {"curl": 0}},
             "symmetry": True},
            {"body_part": "right_hand", "fingers": {"thumb": {"spread": -1, "curl": 1}}},
        ])
        self.assertEqual(sent["hands"][0], {"body_part": "left_hand", "shape": "fist",
                                            "fingers": {"index": {"curl": 0.0}},
                                            "symmetry": True})
        self.assertIsInstance(sent["hands"][0]["fingers"]["index"]["curl"], float)
        self.assertEqual(sent["hands"][1]["fingers"], {"thumb": {"spread": -1.0, "curl": 1.0}})

    def test_the_range_ends_are_taken(self):
        sent = self._sent(hands=[{"body_part": "left_hand", "fingers": {
            "index": {"curl": -0.2, "spread": -1.0}, "pinky": {"curl": 1.0, "spread": 1.0}}}])
        self.assertEqual(sent["hands"][0]["fingers"]["index"], {"curl": -0.2, "spread": -1.0})

    def test_a_body_part_that_is_not_a_hand_is_not_checked_here(self):
        self.assertEqual(self._sent(hands=[{"body_part": "left_foot", "shape": "open"}])[
            "hands"][0]["body_part"], "left_foot")

    def test_a_misspelled_key_is_refused(self):
        self._refused([{"body_part": "left_hand", "fingres": {"index": {"curl": 1}}}])

    def test_an_entry_changing_nothing_is_refused(self):
        self._refused([{"body_part": "left_hand"}])
        self._refused([{"body_part": "left_hand", "symmetry": True}])

    def test_shape_and_finger_names_are_checked_here(self):
        for entry in ({"body_part": "left_hand", "shape": "peace"},
                      {"body_part": "left_hand", "shape": 1},
                      {"body_part": "left_hand", "fingers": {"pinkie": {"curl": 1}}},
                      {"body_part": "left_hand", "fingers": {"f_index": {"curl": 1}}}):
            with self.subTest(entry=entry):
                self._refused([entry])

    def test_a_finger_holds_curl_spread_or_both_and_nothing_else(self):
        for fingers in ({}, {"index": {}}, {"index": 0.5}, {"index": {"bend": 0.5}},
                        {"index": {"curl": 0.5, "twist": 1}}, ["index"]):
            with self.subTest(fingers=fingers):
                self._refused([{"body_part": "left_hand", "fingers": fingers}])

    def test_amounts_are_finite_numbers_in_range_and_not_bools(self):
        for amounts in ({"curl": -0.21}, {"curl": 1.01}, {"spread": -1.5}, {"spread": 2},
                        {"curl": True}, {"spread": False}, {"curl": "0.5"},
                        {"curl": float("nan")}, {"spread": float("inf")}, {"curl": None}):
            with self.subTest(amounts=amounts):
                self._refused([{"body_part": "left_hand", "fingers": {"index": amounts}}])

    def test_symmetry_is_a_real_bool(self):
        for bad in ("true", 1, None):
            with self.subTest(value=bad):
                self._refused([{"body_part": "left_hand", "shape": "open", "symmetry": bad}])

    def test_a_body_part_named_twice_is_refused(self):
        self._refused([{"body_part": "left_hand", "shape": "open"},
                       {"body_part": "left_hand", "shape": "fist"}])

    def test_hands_and_body_part_must_be_shaped(self):
        for hands in ("left_hand", {"body_part": "left_hand"}, ["left_hand"],
                      [{"body_part": "", "shape": "open"}], [{"body_part": 1, "shape": "open"}],
                      [{"body_part": "a", "shape": "open"}, {"body_part": "b", "shape": "open"},
                       {"body_part": "c", "shape": "open"}]):
            with self.subTest(hands=hands):
                self._refused(hands)

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()


def _bridge_tables():
    """The bridge module's ``FINGERS``, ``SHAPES`` keys and ranges, read as data."""
    with open(_BRIDGE_SOURCE, encoding="utf-8") as stream:
        tree = ast.parse(stream.read())
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id in ("FINGERS", "CURL_RANGE", "SPREAD_RANGE"):
            found[target.id] = ast.literal_eval(node.value)
        elif target.id == "SHAPES":
            found["SHAPES"] = tuple(ast.literal_eval(key) for key in node.value.keys)
            found["SHAPE_ROWS"] = ast.literal_eval(node.value)
    return found


class ShapeTableDriftTests(unittest.TestCase):
    """The vocabulary this tool checks and the bridge's tables, kept in step by hand."""

    @unittest.skipUnless(os.path.isfile(_BRIDGE_SOURCE),
                         "the bridge add-on's source is not beside this package")
    def test_the_names_and_ranges_are_the_bridges(self) -> None:
        # Read rather than imported: the add-on imports bpy and mathutils.
        tables = _bridge_tables()

        self.assertEqual(tables.get("FINGERS"), set_rigify_hand_shape.FINGERS)
        self.assertEqual(tables.get("SHAPES"), set_rigify_hand_shape.SHAPES)
        self.assertEqual(tables.get("CURL_RANGE"), set_rigify_hand_shape.CURL_RANGE)
        self.assertEqual(tables.get("SPREAD_RANGE"), set_rigify_hand_shape.SPREAD_RANGE)

    @unittest.skipUnless(os.path.isfile(_BRIDGE_SOURCE),
                         "the bridge add-on's source is not beside this package")
    def test_every_shape_row_is_an_entry_this_tool_accepts(self) -> None:
        # Every shape is something a caller can write by hand: each row, sent
        # as `fingers`, must pass this tool's own validation.
        rows = _bridge_tables()["SHAPE_ROWS"]
        tool = _tool_callable()
        for shape, row in rows.items():
            with self.subTest(shape=shape):
                self.assertEqual(set(row), set(set_rigify_hand_shape.FINGERS))
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    send_command.return_value = {"status": "ok", "result": {}}
                    tool(hands=[{"body_part": "left_hand", "fingers": row}])
                send_command.assert_called_once()


class SetRigifyHandShapeOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_rigify_hand_shape": fake_bridge.ok_envelope(
                "set_rigify_hand_shape", {"found": True, "ready": False,
                                          "blocked_by": "rig_not_supported",
                                          "performed": False}),
        })

    def test_the_tool_sends_the_set_rigify_hand_shape_command(self) -> None:
        self.call(name="Human", hands=[{"body_part": "right_hand", "shape": "grip"}])

        self.assertEqual(self.bridge.commands()[-1], "set_rigify_hand_shape")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "hands": [{"body_part": "right_hand",
                                                      "shape": "grip"}]})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["blocked_by"], "rig_not_supported")


if __name__ == "__main__":
    unittest.main()
