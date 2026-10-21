# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_place_character tool: argument shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). Everything here
is shape: ``position`` and a ``face_toward`` point are objects of known keys
holding finite numbers, ``face_toward`` names an object alone or is a point
with ``x`` and ``y``, ``facing`` is a finite number, ``facing`` and
``face_toward`` are never both given, and a call naming none of the three is
refused, since it would change nothing. **No object name is checked here**:
whether ``face_toward``'s object exists is the far side's
``face_toward_not_found``.

The moves themselves - every rig family, the meta-rig that moves along, the
frame's invariance under a move, ``restore_with``, an external parent, the
tilted refusal, the footprint and the sub-rigs a move breaks - are
``bridge/test/tests/ddd_mutating/place_character_test.py``'s.

Run with::

    python -m unittest tests.test_place_character -v
"""

__all__ = ()

import math
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import place_character

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    place_character.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_place_character"].fn


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

    def test_a_position_alone_reaches_the_wire_as_floats(self):
        self.assertEqual(self._sent(name="Human", position={"x": 2, "z": 0.5}),
                         {"name": "Human", "position": {"x": 2.0, "z": 0.5},
                          "facing": None, "face_toward": None})

    def test_facing_alone_reaches_the_wire(self):
        self.assertEqual(self._sent(facing=-90)["facing"], -90.0)

    def test_face_toward_a_point_or_an_object_reaches_the_wire(self):
        self.assertEqual(self._sent(face_toward={"x": 1, "y": 2})["face_toward"],
                         {"x": 1.0, "y": 2.0})
        self.assertEqual(self._sent(face_toward={"x": 1, "y": 2, "z": 3})["face_toward"],
                         {"x": 1.0, "y": 2.0, "z": 3.0})
        self.assertEqual(self._sent(face_toward={"object": "Camera"})["face_toward"],
                         {"object": "Camera"})

    def test_an_unknown_object_name_is_not_checked_here(self):
        self.assertEqual(self._sent(face_toward={"object": "NoSuchThing"})["face_toward"],
                         {"object": "NoSuchThing"})

    def test_a_call_naming_nothing_is_refused(self):
        self.assertIn("would change nothing", self._refused())
        self.assertIn("would change nothing", self._refused(name="Human"))

    def test_facing_and_face_toward_together_are_refused(self):
        self.assertIn("not both", self._refused(facing=10.0, face_toward={"x": 1, "y": 1}))

    def test_a_badly_shaped_position_is_refused(self):
        for bad in ([1, 2, 3], {}, {"x": "1"}, {"x": True}, {"x": math.nan},
                    {"x": math.inf}, "x=1"):
            with self.subTest(value=bad):
                self._refused(position=bad)

    def test_an_unknown_key_in_position_is_named(self):
        self.assertIn("forward", self._refused(position={"x": 1.0, "forward": 1.0}))

    def test_facing_must_be_a_finite_number(self):
        for bad in ("90", True, math.nan, -math.inf, [90]):
            with self.subTest(value=bad):
                self._refused(facing=bad)

    def test_a_badly_shaped_face_toward_is_refused(self):
        for bad in ({"x": 1.0}, {"y": 1.0}, {"object": ""}, {"object": 3},
                    {"object": "Camera", "x": 1.0}, {"x": 1.0, "y": "2"}, ["Camera"],
                    "Camera", {}):
            with self.subTest(value=bad):
                self._refused(face_toward=bad)

    def test_an_unknown_key_in_face_toward_is_named(self):
        self.assertIn("name", self._refused(face_toward={"name": "Camera"}))

    def test_the_subject_name_is_checked_as_every_tool_checks_it(self):
        self._refused(name="", position={"x": 1.0})


class PlaceCharacterOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "place_character": fake_bridge.ok_envelope(
                "place_character", {"found": True, "ready": True, "placed": True,
                                    "restore_with": {"mpfb_place_character": {}},
                                    "performed": True}),
        })

    def test_the_tool_sends_the_place_character_command(self) -> None:
        self.call(name="Human", position={"y": 1.0}, face_toward={"object": "Camera"})

        self.assertEqual(self.bridge.commands()[-1], "place_character")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human", "position": {"y": 1.0}, "facing": None,
                          "face_toward": {"object": "Camera"}})

    def test_the_answer_comes_back_as_the_add_on_wrote_it(self) -> None:
        response = self.call(facing=45.0)

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["restore_with"], {"mpfb_place_character": {}})
