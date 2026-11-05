# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_check_intersections tool: argument shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). Only ``region`` has a
shape worth checking: known keys, finite numbers, a lower bound not above its upper
one, and at least one axis bound. **No object name is checked here.** What is counted,
and every number in the answer, is ``bridge/test/tests/bbb_shared/mesh_overlap_test.py``'s
on meshes with known answers, and ``ccc_reading/check_intersections_test.py``'s on a
real character.

Run with::

    python -m unittest tests.test_check_intersections -v
"""

__all__ = ()

import math
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import check_intersections

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    check_intersections.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_check_intersections"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def _refused(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError) as raised:
                self.tool(**arguments)
            send_command.assert_not_called()
        return str(raised.exception)

    def test_the_default_call_reaches_the_wire(self):
        self.assertEqual(self._sent(), {"name": None, "other": None, "include_self": False,
                                        "region": None})

    def test_every_argument_reaches_the_wire(self):
        self.assertEqual(
            self._sent(name="Human", other="Woman", include_self=True,
                       region={"min": {"z": 1}, "max": {"x": 2.5, "z": 3}}),
            {"name": "Human", "other": "Woman", "include_self": True,
             "region": {"min": {"z": 1.0}, "max": {"x": 2.5, "z": 3.0}}})

    def test_one_side_of_a_box_is_filled_in_with_nothing(self):
        self.assertEqual(self._sent(region={"max": {"z": 1.0}})["region"],
                         {"min": {}, "max": {"z": 1.0}})

    def test_no_object_name_is_checked_here(self):
        self.assertEqual(self._sent(name="not an object", other="nor this")["other"], "nor this")

    def test_an_empty_name_or_other_is_refused(self):
        self.assertIn("name", self._refused(name=" "))
        self.assertIn("other", self._refused(other=""))

    def test_include_self_must_be_a_real_bool(self):
        for bad in ("true", 1, None):
            self.assertIn("include_self", self._refused(include_self=bad))

    def test_region_must_be_an_object(self):
        self.assertIn("region", self._refused(region=[0, 0, 0]))
        self.assertIn("min", self._refused(region={"min": 1.0}))

    def test_a_misspelled_key_is_refused_at_either_level(self):
        self.assertIn("mix", self._refused(region={"mix": {"z": 1.0}}))
        self.assertIn("w", self._refused(region={"min": {"w": 1.0}}))

    def test_a_coordinate_must_be_a_finite_number(self):
        for bad in (True, "1", math.nan, math.inf, None):
            self.assertIn("min.z", self._refused(region={"min": {"z": bad}}))

    def test_a_box_bounding_nothing_is_refused(self):
        self.assertIn("at least one axis", self._refused(region={}))
        self.assertIn("at least one axis", self._refused(region={"min": {}, "max": {}}))

    def test_a_box_inside_out_is_refused(self):
        self.assertIn("above", self._refused(region={"min": {"z": 2.0}, "max": {"z": 1.0}}))

    def test_a_box_of_no_height_is_a_box(self):
        self.assertEqual(self._sent(region={"min": {"z": 1.0}, "max": {"z": 1.0}})["region"],
                         {"min": {"z": 1.0}, "max": {"z": 1.0}})


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "check_intersections": fake_bridge.ok_envelope("check_intersections", {"found": True}),
        })
        envelope = _tool_callable()(name="Human")
        self.assertEqual(envelope["result"], {"found": True})
        self.assertEqual(server.commands()[-1], "check_intersections")


if __name__ == "__main__":
    unittest.main()
