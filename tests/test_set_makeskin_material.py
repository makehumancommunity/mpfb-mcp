# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_set_makeskin_material tool: the entries' shape, and what crosses.

Two layers (see ``tests/test_list_objects.py``, the template). A source's shape is checked
here, and that it exists and loads on the far side. **No slot, value or metadata vocabulary
is checked here**, which a test below holds it to. Everything the tool does is
``bridge/test/tests/ddd_mutating/set_makeskin_material_test.py``'s, and that a reading can be
sent back unchanged is ``eee_composite/makeskin_roundtrip_test.py``'s.

Run with::

    python -m unittest tests.test_set_makeskin_material -v
"""

__all__ = ()

import ast
import pathlib
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import set_makeskin_material

from tests import fake_bridge

_SHARED = pathlib.Path(__file__).resolve().parent.parent / "bridge" / "mpfb_bridge" / "shared"


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_makeskin_material.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_set_makeskin_material"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        arguments.setdefault("material_name", "belt")
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def _refused(self, **arguments):
        arguments.setdefault("material_name", "belt")
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError) as raised:
                self.tool(**arguments)
            send_command.assert_not_called()
        return str(raised.exception)

    def test_the_default_call_reaches_the_wire(self):
        self.assertEqual(self._sent(), {
            "name": None, "material_name": "belt", "textures": None, "values": None,
            "metadata": None, "replace": False})

    def test_every_argument_reaches_the_wire(self):
        self.assertEqual(
            self._sent(name="Gi", material_name="any Text at all", replace=True,
                       textures={"diffuse": {"path": "/abs/d.PNG"},
                                 "normalmap": {"image": "baked"}},
                       values={"roughness": {"value": 1},
                               "diffuseColor": {"color": [0.1, 0.2, 2.0, 1.0]}},
                       metadata={"license": "CC-BY", "backfaceCull": False}),
            {"name": "Gi", "material_name": "any Text at all", "replace": True,
             "textures": {"diffuse": {"path": "/abs/d.PNG"}, "normalmap": {"image": "baked"}},
             "values": {"roughness": {"value": 1.0},
                        "diffuseColor": {"color": [0.1, 0.2, 2.0, 1.0]}},
             "metadata": {"license": "CC-BY", "backfaceCull": False}})

    def test_material_name_must_be_text(self):
        for material_name in ("", "   ", None, 3):
            with self.subTest(material_name=material_name):
                self.assertIn("material_name", self._refused(material_name=material_name))

    def test_a_windows_path_is_absolute_too(self):
        # Blender need not be on this machine's platform.
        self.assertEqual(
            self._sent(textures={"diffuse": {"path": "C:\\tex\\d.png"}})["textures"],
            {"diffuse": {"path": "C:\\tex\\d.png"}})

    def test_a_source_is_exactly_one_of_two_keys(self):
        self.assertIn("exactly one", self._refused(textures={"diffuse": {}}))
        self.assertIn("exactly one", self._refused(
            textures={"diffuse": {"path": "/a.png", "image": "b"}}))
        self.assertIn("object", self._refused(textures={"diffuse": "/a.png"}))
        self.assertIn("object", self._refused(textures=["diffuse"]))

    def test_a_path_is_absolute_and_ends_in_an_image_extension(self):
        self.assertIn("absolute", self._refused(textures={"diffuse": {"path": "d.png"}}))
        self.assertIn("absolute", self._refused(textures={"diffuse": {"path": "../d.png"}}))
        self.assertIn("extension", self._refused(textures={"diffuse": {"path": "/d.txt"}}))
        self.assertIn("extension", self._refused(textures={"diffuse": {"path": "/d"}}))
        self.assertIn("non-empty", self._refused(textures={"diffuse": {"path": ""}}))
        self.assertIn("non-empty", self._refused(textures={"diffuse": {"path": 3}}))

    def test_every_extension_is_accepted(self):
        for extension in set_makeskin_material.IMAGE_EXTENSIONS:
            path = "/tex/d" + extension
            self.assertEqual(self._sent(textures={"diffuse": {"path": path}})["textures"],
                             {"diffuse": {"path": path}})

    def test_an_image_name_is_text(self):
        self.assertIn("non-empty", self._refused(textures={"diffuse": {"image": ""}}))
        self.assertIn("non-empty", self._refused(textures={"diffuse": {"image": 3}}))

    def test_a_misspelled_source_key_is_refused(self):
        self.assertIn("pth", self._refused(textures={"diffuse": {"pth": "/a.png"}}))

    def test_a_reading_crosses_as_its_source_alone(self):
        sent = self._sent(textures={"diffuse": {
            "path": "/a.png", "image_name": "a.png", "wired": True, "resolved_path": "/a.png",
            "file_exists": True, "size": [2, 2], "color_space": "sRGB", "packed": False,
            "unsaved_changes": False, "strength": 1.0, "strength_value": "diffuseIntensity"}},
            values={"roughness": {"value": 0.7, "in_effect": True, "overridden_by": None,
                                  "needs_slot": None, "range": [0.0, 1.0]},
                    "diffuseColor": {"color": [0.5, 0.5, 0.5, 1.0], "srgb_hex": "#bcbcbc",
                                     "in_effect": False, "overridden_by": "diffuse",
                                     "needs_slot": None}})
        self.assertEqual(sent["textures"], {"diffuse": {"path": "/a.png"}})
        self.assertEqual(sent["values"], {"roughness": {"value": 0.7},
                                          "diffuseColor": {"color": [0.5, 0.5, 0.5, 1.0]}})

    def test_a_plain_number_is_refused_and_says_what_to_send(self):
        message = self._refused(values={"roughness": 0.5})
        self.assertIn('{"value": number}', message)
        self.assertIn("mpfb_get_makeskin_material", message)

    def test_a_value_holds_exactly_one_of_two_keys(self):
        self.assertIn("exactly one", self._refused(values={"roughness": {}}))
        self.assertIn("exactly one", self._refused(
            values={"roughness": {"value": 1.0, "color": [0, 0, 0, 1]}}))
        self.assertIn("unknown key", self._refused(values={"roughness": {"valu": 1.0}}))

    def test_a_number_is_a_real_finite_number(self):
        for value in (True, "0.5", None, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertIn("finite number", self._refused(values={"roughness": {"value": value}}))

    def test_a_color_is_four_finite_non_negative_numbers_with_an_opaque_alpha(self):
        for color in ([1, 1, 1], "red", [1, 1, 1, 1, 1], [1, 1, float("nan"), 1], [1, True, "x", 1]):
            with self.subTest(color=color):
                self.assertIn("four finite", self._refused(
                    values={"diffuseColor": {"color": color}}))
        self.assertIn("negative", self._refused(
            values={"diffuseColor": {"color": [-0.1, 0, 0, 1]}}))
        self.assertIn("alpha", self._refused(values={"diffuseColor": {"color": [0, 0, 0, 0.5]}}))

    def test_metadata_is_text_or_a_flag_on_one_line(self):
        self.assertIn("object", self._refused(metadata="CC0"))
        self.assertIn("text or true", self._refused(metadata={"author": 3}))
        self.assertIn("one line", self._refused(metadata={"description": "a\nroughness 0.1"}))
        self.assertIn("one line", self._refused(metadata={"description": "a\rb"}))

    def test_replace_is_a_real_bool(self):
        self.assertIn("replace", self._refused(replace="true"))

    def test_no_vocabulary_is_checked_here(self):
        sent = self._sent(textures={"made_up_slot": {"image": "x"}},
                          values={"made_up_value": {"value": 1.0}},
                          metadata={"made_up_key": "x"})
        self.assertIn("made_up_slot", sent["textures"])
        self.assertIn("made_up_value", sent["values"])
        self.assertIn("made_up_key", sent["metadata"])


def _assigned(path: pathlib.Path, name: str) -> object:
    tree = ast.parse(path.read_text(encoding="utf8"))
    found = [node.value for node in tree.body
             if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == name]
    assert len(found) == 1, "the parse must find {}".format(name)
    return ast.literal_eval(found[0])


@unittest.skipUnless(_SHARED.exists(), "the add-on's source is not beside this checkout")
class DriftTests(unittest.TestCase):
    """Three lists exist on both sides of the socket, and are read here rather than imported."""

    def test_both_sides_know_the_same_read_only_keys(self):
        for name in ("READ_ONLY_TEXTURE_KEYS", "READ_ONLY_VALUE_KEYS"):
            self.assertEqual(_assigned(_SHARED / "makeskin.py", name),
                             getattr(set_makeskin_material, name))

    def test_both_sides_know_the_same_extensions(self):
        self.assertEqual(_assigned(_SHARED / "texture_writing.py", "IMAGE_EXTENSIONS"),
                         set_makeskin_material.IMAGE_EXTENSIONS)


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_makeskin_material": fake_bridge.ok_envelope("set_makeskin_material",
                                                             {"applied": True}),
        })
        envelope = _tool_callable()(material_name="belt")
        self.assertEqual(envelope["result"], {"applied": True})
        self.assertEqual(server.commands()[-1], "set_makeskin_material")


if __name__ == "__main__":
    unittest.main()
