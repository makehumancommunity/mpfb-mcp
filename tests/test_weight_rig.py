# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_weight_rig tool: argument shape, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). ``method`` and ``direction`` are
this package's own vocabularies and are checked here, held to the bridge command's by reading
its source as data; each method's own argument is refused beside another method, and a method
without its own is refused. **No bone or rig vocabulary is checked here.** What each method
writes - the heat pass without the joint cubes, the exact, chain and ancestor matches against
``default_no_toes``, the mirror of a one-sided weighting and the fill's counts - is
``bridge/test/tests/ddd_mutating/weight_rig_test.py``'s.

Run with::

    python -m unittest tests.test_weight_rig -v
"""

__all__ = ()

import ast
import pathlib
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import weight_rig

from tests import fake_bridge

_COMMAND = (pathlib.Path(__file__).resolve().parent.parent / "bridge" / "mpfb_bridge"
            / "commands" / "weight_rig.py")


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    weight_rig.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_weight_rig"].fn


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
            with self.assertRaises(ValueError):
                self.tool(**arguments)
        send_command.assert_not_called()

    def test_method_is_required(self):
        with self.assertRaises(TypeError):
            self.tool()

    def test_an_unknown_method_is_refused(self):
        for bad in ("heat", "AUTOMATIC", "", None, 1):
            with self.subTest(method=bad):
                self._refused(method=bad)

    def test_the_automatic_call_reaches_the_wire(self):
        self.assertEqual(self._sent(method="automatic", exclude_bones=["root"]), {
            "name": None, "method": "automatic", "exclude_bones": ["root"], "from_rig": None,
            "direction": None, "fill_unweighted": True, "bone_names": None})

    def test_each_method_takes_its_own_argument(self):
        self.assertEqual(self._sent(method="transfer", from_rig="default_no_toes")["from_rig"],
                         "default_no_toes")
        self.assertEqual(self._sent(method="mirror", direction="right_to_left")["direction"],
                         "right_to_left")

    def test_a_method_missing_its_own_argument_is_refused(self):
        self._refused(method="transfer")
        self._refused(method="mirror")

    def test_another_methods_argument_is_refused(self):
        self._refused(method="automatic", from_rig="default")
        self._refused(method="automatic", direction="left_to_right")
        self._refused(method="transfer", from_rig="default", exclude_bones=["root"])
        self._refused(method="mirror", direction="left_to_right", from_rig="default")

    def test_shapes_are_refused_before_sending(self):
        for arguments in ({"method": "mirror", "direction": "left"},
                          {"method": "automatic", "exclude_bones": []},
                          {"method": "automatic", "exclude_bones": ["root", "root"]},
                          {"method": "automatic", "bone_names": "root"},
                          {"method": "automatic", "fill_unweighted": "false"},
                          {"method": "transfer", "from_rig": ""}):
            with self.subTest(arguments=arguments):
                self._refused(**arguments)

    def test_no_bone_or_rig_vocabulary_is_checked_here(self):
        sent = self._sent(method="transfer", from_rig="custom.not_installed",
                          bone_names=["no_such_bone"])
        self.assertEqual((sent["from_rig"], sent["bone_names"]),
                         ("custom.not_installed", ["no_such_bone"]))


@unittest.skipUnless(_COMMAND.exists(), "the add-on's source is not beside this checkout")
class DriftTests(unittest.TestCase):

    def _bridge_table(self, name):
        tree = ast.parse(_COMMAND.read_text(encoding="utf-8"))
        assigned = [node.value for node in tree.body if isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", None) == name]
        self.assertEqual(len(assigned), 1, "the parse must find {:s}".format(name))
        return ast.literal_eval(assigned[0])

    def test_both_sides_know_the_same_methods(self):
        self.assertEqual(self._bridge_table("METHODS"), weight_rig.METHODS)

    def test_both_sides_know_the_same_directions(self):
        self.assertEqual(self._bridge_table("DIRECTIONS"), weight_rig.DIRECTIONS)


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "weight_rig": fake_bridge.ok_envelope("weight_rig", {"weighted": True}),
        })
        envelope = _tool_callable()(method="automatic")
        self.assertEqual(envelope["result"], {"weighted": True})
        self.assertEqual(server.commands()[-1], "weight_rig")


if __name__ == "__main__":
    unittest.main()
