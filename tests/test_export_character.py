# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_export_character``: the name rule and two vocabularies here, the file over there.

Two layers (see ``tests/test_list_objects.py``, the template), and as in
``tests/test_save_preset.py`` the first carries the weight: ``export_name``
becomes a **path**, so the whitelist is exercised over the same table of names
the preset and expression tools are held to, before anything is sent. The drift
check between the two copies of the rule is ``tests/test_save_preset.py``'s,
which runs every name as all three nouns. There is no directory argument to
test, and that is the point: the tool cannot be told where to write.

``format`` and ``target_engine`` are this package's own vocabularies. Which
preset has which format is the command's, beside the tables and their sources,
so a pair with no table (``godot`` with ``fbx``) is **sent** and refused there.

What the export writes - the file in a redirected export directory, the
overwrite and missing-directory refusals, the selection put back, only the
family selected, each format read back into Blender - is checked against a real
MPFB in ``bridge/test/tests/ddd_mutating/export_character_test.py`` and
``eee_composite/export_roundtrip_test.py``.

Run with::

    python -m unittest tests.test_export_character -v
"""

from __future__ import annotations

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import export_character

from tests import fake_bridge
from tests.test_save_preset import ACCEPTED_NAMES
from tests.test_save_preset import REFUSED_NAMES


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    export_character.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_export_character"].fn


class ExportCharacterValidationTests(unittest.TestCase):
    """The name rule and the two vocabularies, before anything is sent."""

    def setUp(self) -> None:
        self.call = _tool_callable()

    def _run(self, **arguments):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args[0][0], "export_character")
            return send.call_args[0][1]

    def _refused(self, **arguments):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            with self.assertRaises(ValueError) as raised:
                self.call(**arguments)
            self.assertEqual(send.call_count, 0)
        return str(raised.exception)

    def test_every_dangerous_or_malformed_name_is_refused_before_the_socket(self) -> None:
        for name, why in REFUSED_NAMES:
            with self.subTest(name=name, why=why):
                self._refused(export_name=name)

    def test_every_legal_name_is_accepted_and_sent_as_given(self) -> None:
        for name in ACCEPTED_NAMES + ("hero_unity", "anna.v2"):
            with self.subTest(name=name):
                self.assertEqual(self._run(export_name=name)["export_name"], name)

    def test_a_refusal_speaks_of_an_export_and_says_who_chooses_the_directory(self) -> None:
        message = self._refused(export_name="../escape")
        self.assertIn("export name", message)
        self.assertIn("export directory", message)

    def test_the_default_call(self) -> None:
        self.assertEqual(self._run(export_name="hero"), {
            "export_name": "hero", "name": None, "format": None, "target_engine": "generic",
            "overwrite": False})

    def test_there_is_no_way_to_name_a_directory(self) -> None:
        with self.assertRaises(TypeError):
            # pylint: disable-next=unexpected-keyword-arg
            self.call(export_name="hero", directory="/tmp")

    def test_format_is_null_or_one_of_three(self) -> None:
        for value in export_character.FORMATS:
            with self.subTest(format=value):
                self.assertEqual(self._run(export_name="hero", format=value)["format"], value)
        for bad in ("FBX", "glb", "obj", "", 3):
            with self.subTest(format=bad):
                self._refused(export_name="hero", format=bad)

    def test_target_engine_is_one_of_four(self) -> None:
        for value in export_character.TARGET_ENGINES:
            with self.subTest(target_engine=value):
                self.assertEqual(self._run(export_name="hero", target_engine=value)
                                 ["target_engine"], value)
        for bad in ("Unity", "blender", "", None):
            with self.subTest(target_engine=bad):
                self._refused(export_name="hero", target_engine=bad)

    def test_a_preset_format_pair_is_not_judged_here(self) -> None:
        # The tables live in the command, beside their sources; this side checks
        # only that each is one of its own vocabulary.
        params = self._run(export_name="hero", format="fbx", target_engine="godot")
        self.assertEqual((params["format"], params["target_engine"]), ("fbx", "godot"))

    def test_overwrite_must_be_a_real_bool(self) -> None:
        for value in ("false", "true", 1, 0, None):
            with self.subTest(overwrite=value):
                self._refused(export_name="hero", overwrite=value)

    def test_the_subject_is_optional_and_shape_checked(self) -> None:
        self.assertEqual(self._run(export_name="hero", name="Human")["name"], "Human")
        self._refused(export_name="hero", name="")
        self._refused(export_name="hero", name=3)


class ExportCharacterOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "export_character": fake_bridge.ok_envelope(
                "export_character", {"found": True, "exported": True, "performed": True}),
        })

    def test_the_tool_sends_the_export_character_command(self) -> None:
        self.call(export_name="hero", format="gltf", target_engine="godot")

        self.assertEqual(self.bridge.commands()[-1], "export_character")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual((params["export_name"], params["format"], params["target_engine"]),
                         ("hero", "gltf", "godot"))

    def test_a_name_that_could_become_a_path_reaches_no_backend(self) -> None:
        for name in ("../escape", "with space", "", "a/b", ".hidden", "/abs/path"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.call(export_name=name)
        self.assertEqual(self.bridge.requests, [])
