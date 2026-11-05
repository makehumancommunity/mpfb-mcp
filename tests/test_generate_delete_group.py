# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_generate_delete_group tool: argument shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). ``margins``' keys are this package's
own vocabulary, so they are checked here and again on the far side, and a test below holds the two
lists together by reading the bridge's as data. **No object or group is checked here.** What is
generated and measured is ``bridge/test/tests/bbb_shared/delete_group_test.py``'s and
``ddd_mutating/generate_delete_group_test.py``'s, and that it holds on the gi is the request's own
live check.

Run with::

    python -m unittest tests.test_generate_delete_group -v
"""

__all__ = ()

import ast
import math
import pathlib
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import generate_delete_group

from tests import fake_bridge

_SHARED_SOURCE = (pathlib.Path(__file__).resolve().parent.parent
                  / "bridge" / "mpfb_bridge" / "shared" / "delete_group.py")


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    generate_delete_group.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_generate_delete_group"].fn


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
        self.assertEqual(self._sent(), {"name": None, "basemesh": None, "delete_group": None,
                                        "mode": "merge", "margins": None, "dry_run": False})

    def test_every_argument_reaches_the_wire(self):
        self.assertEqual(
            self._sent(name="Gi", basemesh="Human", delete_group="delete", mode="replace",
                       margins={"hem": 0.2, "cuff": 1}, dry_run=True),
            {"name": "Gi", "basemesh": "Human", "delete_group": "delete", "mode": "replace",
             "margins": {"hem": 0.2, "cuff": 1}, "dry_run": True})

    def test_an_empty_name_basemesh_or_group_is_refused(self):
        self.assertIn("name", self._refused(name=""))
        self.assertIn("basemesh", self._refused(basemesh=" "))
        self.assertIn("delete_group", self._refused(delete_group=""))

    def test_mode_is_merge_or_replace(self):
        self.assertIn("mode", self._refused(mode="add"))

    def test_dry_run_must_be_a_real_bool(self):
        self.assertIn("dry_run", self._refused(dry_run="yes"))
        self.assertIn("dry_run", self._refused(dry_run=1))

    def test_margins_must_be_an_object_of_known_kinds(self):
        self.assertIn("object", self._refused(margins=[0.1]))
        self.assertIn("must not be empty", self._refused(margins={}))
        self.assertIn("neck", self._refused(margins={"neck": 0.1}))

    def test_a_margin_must_be_a_finite_number_above_zero(self):
        for bad in (0, -0.1, math.inf, math.nan, True, "0.1", None):
            self.assertIn("hem", self._refused(margins={"hem": bad}), repr(bad))


@unittest.skipUnless(_SHARED_SOURCE.exists(), "the add-on's source is not beside this checkout")
class KindDriftTests(unittest.TestCase):
    """The kinds exist on both sides of the socket, and are read here rather than imported."""

    def test_both_sides_know_the_same_kinds(self):
        tree = ast.parse(_SHARED_SOURCE.read_text(encoding="utf8"))
        constants = dict()
        margins = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and hasattr(node.targets[0], "id"):
                if node.targets[0].id == "DEFAULT_MARGINS":
                    margins = node.value
                elif isinstance(node.value, ast.Constant):
                    constants[node.targets[0].id] = node.value.value
        self.assertIsNotNone(margins, "the parse must find the table")
        self.assertEqual(sorted(constants[key.id] for key in margins.keys),
                         sorted(generate_delete_group.MARGIN_KINDS))


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "generate_delete_group": fake_bridge.ok_envelope("generate_delete_group", {"found": True}),
        })
        envelope = _tool_callable()(name="Gi", dry_run=True)
        self.assertEqual(envelope["result"], {"found": True})
        self.assertEqual(server.commands()[-1], "generate_delete_group")


if __name__ == "__main__":
    unittest.main()
