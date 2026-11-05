# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_write_mesh_asset tool: the name rule, every argument's shape, and what crosses.

Two layers (see ``tests/test_list_objects.py``, the template). **The name is checked on both sides
of the socket, and this is where the two are held together**, over one table of names, as
``tests/test_store_makeskin_material.py`` does for a material's. A name that escapes the directory
must never cross, and one MPFB's panel would rewrite could be written and then not be found. **No
``object_type`` vocabulary is checked here**: what is written, and every refusal about the mesh, is
``bridge/test/tests/ddd_mutating/write_mesh_asset_test.py``'s.

Run with::

    python -m unittest tests.test_write_mesh_asset -v
"""

__all__ = ()

import ast
import pathlib
import re
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import artifact_names
from mpfbmcp import bridge_connection
from mpfbmcp.tools import write_mesh_asset

from tests import fake_bridge

_BRIDGE = pathlib.Path(__file__).resolve().parent.parent / "bridge" / "mpfb_bridge"

ACCEPTED = ("taido_gi", "a", "_", "1", "Gi2", "MyGi", "_lead", "trail_", "a" * 64)
REFUSED = ("my-gi", "my.gi", "a__b", "__", "my gi", "gi/top", "gi\\top", "..", ".", ".hidden", "",
           " ", "a" * 65, "naïve", "trailing ", "c:nope", "null\x00byte", None, 3, True, 1.5,
           [], {})

_DEFAULTS = {
    "name": None, "basemesh": None, "asset_name": "taido_gi", "object_type": None,
    "destination": "library", "overwrite": False, "dry_run": False, "license": None, "author": None,
    "description": None, "delete_group": None, "allow_exact_matching": None, "write_material": True,
}


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    write_mesh_asset.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_write_mesh_asset"].fn


def _panel_normalisation(name):
    """What writeclotheslibrary.py does to a name before using it."""
    cleaned = str(name).strip().replace(" ", "_")
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", cleaned)
    return re.sub(r"_+", "_", cleaned)


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        arguments.setdefault("asset_name", "taido_gi")
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def _refused(self, **arguments):
        arguments.setdefault("asset_name", "taido_gi")
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError) as raised:
                self.tool(**arguments)
            send_command.assert_not_called()
        return str(raised.exception)

    def test_the_default_call_reaches_the_wire(self):
        self.assertEqual(self._sent(), _DEFAULTS)

    def test_every_argument_reaches_the_wire(self):
        arguments = dict(
            name="gi", basemesh="Human", asset_name="other", object_type="Hair",
            destination="export_directory", overwrite=True, dry_run=True, license="CC-BY",
            author="Somebody", description="A gi.", delete_group="Delete.gi",
            allow_exact_matching=False, write_material=False)
        self.assertEqual(self._sent(**arguments), arguments)

    def test_destination_is_one_of_two_and_neither_is_a_path(self):
        for value in ("elsewhere", "/tmp/somewhere", "", None, 1):
            with self.subTest(destination=value):
                self.assertIn("destination", self._refused(destination=value))

    def test_the_flags_are_real_bools(self):
        self.assertIn("overwrite", self._refused(overwrite="false"))
        self.assertIn("dry_run", self._refused(dry_run=1))
        self.assertIn("write_material", self._refused(write_material=None))
        self.assertIn("allow_exact_matching", self._refused(allow_exact_matching="yes"))

    def test_allow_exact_matching_left_out_is_not_false(self):
        # Null follows MakeClothes' setting on the scene, which is a different request.
        self.assertIsNone(self._sent()["allow_exact_matching"])
        self.assertIs(self._sent(allow_exact_matching=False)["allow_exact_matching"], False)

    def test_the_text_arguments_are_one_line_when_given(self):
        for argument in ("license", "author", "description"):
            with self.subTest(argument=argument):
                self.assertIn(argument, self._refused(**{argument: ""}))
                self.assertIn(argument, self._refused(**{argument: 3}))
                self.assertIn("one line", self._refused(**{argument: "a\nuuid forged"}))
                self.assertIn("one line", self._refused(**{argument: "a\rb"}))

    def test_an_empty_string_is_not_an_omission(self):
        for argument in ("basemesh", "object_type", "delete_group", "name"):
            with self.subTest(argument=argument):
                self.assertIn(argument, self._refused(**{argument: " "}))

    def test_no_vocabulary_of_mpfbs_is_checked_here(self):
        self.assertEqual(self._sent(object_type="Basemesh")["object_type"], "Basemesh")
        self.assertEqual(self._sent(license="WTFPL")["license"], "WTFPL")
        self.assertEqual(self._sent(delete_group="nope")["delete_group"], "nope")

    def test_what_would_not_reach_a_file_is_not_an_argument(self):
        for argument in ("homepage", "tags", "z_depth"):
            with self.subTest(argument=argument):
                with self.assertRaises(TypeError):
                    self.tool(asset_name="taido_gi", **{argument: "x"})

    def test_a_name_that_is_refused_never_crosses(self):
        for name in REFUSED:
            with self.subTest(name=name):
                self.assertIn("mesh asset", self._refused(asset_name=name))

    def test_a_name_that_is_accepted_crosses_as_given(self):
        for name in ACCEPTED:
            with self.subTest(name=name):
                self.assertEqual(self._sent(asset_name=name)["asset_name"], name)


@unittest.skipUnless(_BRIDGE.exists(), "the add-on's source is not beside this checkout")
class BothSidesTests(unittest.TestCase):
    """One rule, run on both sides of the socket over one table."""

    def setUp(self):
        namespace: dict = {}
        path = _BRIDGE / "shared" / "artifact_names.py"
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
        self.bridge_rejection = namespace["asset_name_rejection"]
        self.bridge_pattern = namespace["ASSET_NAME_PATTERN"]

    def test_both_give_the_same_verdict_and_the_same_sentence(self):
        for name in ACCEPTED + REFUSED:
            with self.subTest(name=name):
                self.assertEqual(artifact_names.asset_name_rejection(name),
                                 self.bridge_rejection(name))

    def test_the_pattern_is_the_same_on_both(self):
        self.assertEqual(artifact_names.ASSET_NAME_PATTERN, self.bridge_pattern)

    def test_the_table_says_what_it_means(self):
        for name in ACCEPTED:
            self.assertIsNone(artifact_names.asset_name_rejection(name), name)
        for name in REFUSED:
            self.assertIsNotNone(artifact_names.asset_name_rejection(name), name)

    def test_every_name_accepted_survives_the_panels_normalisation_unchanged(self):
        for name in ACCEPTED:
            self.assertEqual(_panel_normalisation(name), name)

    def test_every_string_refused_for_the_narrower_rule_is_one_the_panel_would_change(self):
        # The hyphen, the dot and the double underscore are why this rule is narrower than an
        # export's, and each is here because the panel would have written something else.
        for name in ("my-gi", "my.gi", "a__b", "__"):
            self.assertNotEqual(_panel_normalisation(name), name)

    def test_every_name_accepted_is_also_one_the_wider_rule_accepts(self):
        for name in ACCEPTED:
            self.assertIsNone(artifact_names.name_rejection(name, "mesh asset"))

    def test_both_sides_know_the_same_destinations(self):
        tree = ast.parse((_BRIDGE / "commands" / "write_mesh_asset.py").read_text(
            encoding="utf8"))
        assigned = [node.value for node in tree.body
                    if isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", None) == "DESTINATIONS"]
        self.assertEqual(len(assigned), 1, "the parse must find the table")
        self.assertEqual(ast.literal_eval(assigned[0]), write_mesh_asset.DESTINATIONS)


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "write_mesh_asset": fake_bridge.ok_envelope("write_mesh_asset", {"written": True}),
        })
        envelope = _tool_callable()(asset_name="taido_gi", dry_run=True)
        self.assertEqual(envelope["result"], {"written": True})
        self.assertEqual(server.commands()[-1], "write_mesh_asset")


if __name__ == "__main__":
    unittest.main()
