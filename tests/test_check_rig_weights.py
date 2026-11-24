# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_check_rig_weights tool: argument shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). ``sections`` is this package's own
vocabulary, so it is checked here and again on the far side, and a test below holds the two lists
together by reading the bridge's as data. **No object, bone or helper is checked here.** Every
reading is ``bridge/test/tests/bbb_shared/rig_weights_test.py``'s, against MPFB's shipped weights,
and what a call reads and puts back, the bend included, is ``ccc_reading/check_rig_weights_test.py``'s.

Run with::

    python -m unittest tests.test_check_rig_weights -v
"""

__all__ = ()

import ast
import pathlib
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import check_rig_weights

from tests import fake_bridge

_COMMAND_SOURCE = (pathlib.Path(__file__).resolve().parent.parent
                   / "bridge" / "mpfb_bridge" / "commands" / "check_rig_weights.py")


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    check_rig_weights.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_check_rig_weights"].fn


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
        self.assertEqual(self._sent(), {"name": None, "sections": None})

    def test_every_argument_reaches_the_wire(self):
        self.assertEqual(self._sent(name="Human", sections=["bend", "coverage"]),
                         {"name": "Human", "sections": ["bend", "coverage"]})

    def test_an_empty_name_is_refused(self):
        self.assertIn("name", self._refused(name=""))

    def test_sections_must_be_a_list_of_distinct_known_names(self):
        self.assertIn("list", self._refused(sections="bend"))
        self.assertIn("must not be empty", self._refused(sections=[]))
        self.assertIn("more than once", self._refused(sections=["bend", "bend"]))
        self.assertIn("weights", self._refused(sections=["bend", "weights"]))

    def test_every_section_is_accepted(self):
        for section in check_rig_weights.SECTIONS:
            self.assertEqual(self._sent(sections=[section])["sections"], [section])

    def test_no_bone_or_helper_vocabulary_is_checked_here(self):
        self.assertEqual(self._sent(name="not_a_character")["name"], "not_a_character")


@unittest.skipUnless(_COMMAND_SOURCE.exists(), "the add-on's source is not beside this checkout")
class SectionDriftTests(unittest.TestCase):
    """The list exists on both sides of the socket, and is read here rather than imported."""

    def test_both_sides_know_the_same_sections(self):
        tree = ast.parse(_COMMAND_SOURCE.read_text(encoding="utf8"))
        assigned = [node.value for node in tree.body
                    if isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", None) == "SECTIONS"]
        self.assertEqual(len(assigned), 1, "the parse must find the table")
        self.assertEqual(ast.literal_eval(assigned[0]), check_rig_weights.SECTIONS)


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "check_rig_weights": fake_bridge.ok_envelope("check_rig_weights", {"found": True}),
        })
        envelope = _tool_callable()(name="Human", sections=["bend"])
        self.assertEqual(envelope["result"], {"found": True})
        self.assertEqual(server.commands()[-1], "check_rig_weights")


if __name__ == "__main__":
    unittest.main()
