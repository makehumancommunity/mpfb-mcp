# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_store_makeskin_material tool: the name rule, and what crosses.

Two layers (see ``tests/test_list_objects.py``, the template). **The name is checked on both
sides of the socket, and this is where the two are held together**, over one table of names,
as ``tests/test_save_preset.py`` does for the wider rule. A name that escapes the directory
must never cross, and a name MPFB's normalisation would change could be written and then not
be found. What is written is ``bridge/test/tests/ddd_mutating/store_makeskin_material_test.py``'s.

Run with::

    python -m unittest tests.test_store_makeskin_material -v
"""

__all__ = ()

import ast
import pathlib
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import artifact_names
from mpfbmcp import bridge_connection
from mpfbmcp.tools import store_makeskin_material

from tests import fake_bridge

_BRIDGE = pathlib.Path(__file__).resolve().parent.parent / "bridge" / "mpfb_bridge"

ACCEPTED = ("belt_blue", "a", "_", "1", "belt2", "a" * 64)
REFUSED = ("Belt", "belt blue", "belt-blue", "belt.blue", "belt/blue", "belt\\blue", "..", ".",
           ".hidden", "", " ", "a" * 65, "na\u00efve", "trailing ", "c:nope", "null\x00byte",
           None, 3, True, 1.5, [], {})


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    store_makeskin_material.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_store_makeskin_material"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        arguments.setdefault("store_as", "alternate")
        arguments.setdefault("material_name", "belt_blue")
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def _refused(self, **arguments):
        arguments.setdefault("store_as", "alternate")
        arguments.setdefault("material_name", "belt_blue")
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError) as raised:
                self.tool(**arguments)
            send_command.assert_not_called()
        return str(raised.exception)

    def test_the_default_call_reaches_the_wire(self):
        self.assertEqual(self._sent(), {
            "name": None, "store_as": "alternate", "material_name": "belt_blue",
            "overwrite": False, "dry_run": False, "license": None, "author": None})

    def test_every_argument_reaches_the_wire(self):
        self.assertEqual(
            self._sent(name="Human", store_as="skin", material_name="my_skin", overwrite=True,
                       dry_run=True, license="CC-BY", author="Somebody"),
            {"name": "Human", "store_as": "skin", "material_name": "my_skin", "overwrite": True,
             "dry_run": True, "license": "CC-BY", "author": "Somebody"})

    def test_store_as_is_required_and_is_one_of_two(self):
        for value in ("library", "", None, 1):
            with self.subTest(store_as=value):
                self.assertIn("store_as", self._refused(store_as=value))

    def test_the_two_flags_are_real_bools(self):
        self.assertIn("overwrite", self._refused(overwrite="false"))
        self.assertIn("dry_run", self._refused(dry_run=1))

    def test_license_and_author_are_one_line_of_text_when_given(self):
        self.assertIn("license", self._refused(license=""))
        self.assertIn("author", self._refused(author=3))
        self.assertIn("one line", self._refused(author="a\nroughness 0.1"))
        self.assertIn("one line", self._refused(license="a\rb"))

    def test_no_license_vocabulary_is_checked_here(self):
        self.assertEqual(self._sent(license="WTFPL")["license"], "WTFPL")

    def test_a_name_that_is_refused_never_crosses(self):
        for name in REFUSED:
            with self.subTest(name=name):
                self.assertIn("material", self._refused(material_name=name))

    def test_a_name_that_is_accepted_crosses_as_given(self):
        for name in ACCEPTED:
            with self.subTest(name=name):
                self.assertEqual(self._sent(material_name=name)["material_name"], name)


@unittest.skipUnless(_BRIDGE.exists(), "the add-on's source is not beside this checkout")
class BothSidesTests(unittest.TestCase):
    """One rule, run on both sides of the socket over one table."""

    def setUp(self):
        namespace: dict = {}
        path = _BRIDGE / "shared" / "artifact_names.py"
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
        self.bridge_rejection = namespace["material_name_rejection"]

    def test_both_give_the_same_verdict_and_the_same_sentence(self):
        for name in ACCEPTED + REFUSED:
            with self.subTest(name=name):
                self.assertEqual(artifact_names.material_name_rejection(name),
                                 self.bridge_rejection(name))

    def test_the_table_says_what_it_means(self):
        for name in ACCEPTED:
            self.assertIsNone(artifact_names.material_name_rejection(name), name)
        for name in REFUSED:
            self.assertIsNotNone(artifact_names.material_name_rejection(name), name)

    def test_every_name_accepted_survives_mpfbs_normalisation(self):
        # writelibrary.py and writealternate.py: replace(" ", "_").lower().
        for name in ACCEPTED:
            self.assertEqual(name.replace(" ", "_").lower(), name)

    def test_every_name_accepted_is_also_one_the_wider_rule_accepts(self):
        for name in ACCEPTED:
            self.assertIsNone(artifact_names.name_rejection(name, "material"))

    def test_both_sides_know_the_same_destinations(self):
        tree = ast.parse((_BRIDGE / "commands" / "store_makeskin_material.py").read_text(
            encoding="utf8"))
        assigned = [node.value for node in tree.body
                    if isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", None) == "STORE_AS"]
        self.assertEqual(len(assigned), 1, "the parse must find the table")
        self.assertEqual(ast.literal_eval(assigned[0]), store_makeskin_material.STORE_AS)


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "store_makeskin_material": fake_bridge.ok_envelope("store_makeskin_material",
                                                               {"saved": True}),
        })
        envelope = _tool_callable()(store_as="skin", material_name="my_skin")
        self.assertEqual(envelope["result"], {"saved": True})
        self.assertEqual(server.commands()[-1], "store_makeskin_material")


if __name__ == "__main__":
    unittest.main()
