# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_objects tool: argument validation, and the generated
code's filtering and type-vocabulary reporting.

The generated code cannot be run against real MPFB from here (see
specifications/architecture.md), so it is executed against the stubs in
tests/blender_stubs.py. That checks the branching and the shape of ``result``;
it says nothing about whether real MPFB returns the values we assume, which
remains a manual check against a running Blender.

Run with::

    python -m unittest tests.test_list_objects -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import list_objects
from tests.blender_stubs import GeneratedCodeTestCase, StubObject


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    list_objects.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_list_objects"]  # noqa: SLF001
    return tool.fn


def _scene():
    """A small scene, plus one typed object that is not linked into it."""
    skeleton = StubObject("Human.rig", blender_type="ARMATURE", object_type="Skeleton")
    basemesh = StubObject("Human", parent=skeleton, object_type="Basemesh")
    fedora = StubObject("Fedora", parent=basemesh, object_type="Clothes")
    proxy = StubObject("Proxy", parent=basemesh, object_type="Proxymeshes")
    cube = StubObject("Cube")
    unlinked = StubObject("Orphan", object_type="Hair")
    scene_objects = [skeleton, basemesh, fedora, proxy, cube]
    return scene_objects, scene_objects + [unlinked]


class ListObjectsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_list_objects = _register_and_get_tool()

    @mock.patch("mpfbmcp.tools.list_objects.send_code")
    def test_omitted_filter_is_sent_as_null(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"count": 0}}

        self.mpfb_list_objects()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertEqual(_params_in(code), {"object_type": None})

    @mock.patch("mpfbmcp.tools.list_objects.send_code")
    def test_filter_is_passed_through_verbatim(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"count": 0}}

        self.mpfb_list_objects("Basemesh")

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code), {"object_type": "Basemesh"})

    def test_blank_filter_is_rejected_locally(self) -> None:
        # An empty filter would substring-match every type rather than none, so
        # it must fail here rather than come back as a full listing.
        with mock.patch("mpfbmcp.tools.list_objects.send_code") as mock_send_code:
            for blank in ("", "   ", "\t"):
                with self.subTest(object_type=blank):
                    with self.assertRaises(ValueError):
                        self.mpfb_list_objects(blank)
            mock_send_code.assert_not_called()

    def test_non_string_filter_is_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.tools.list_objects.send_code") as mock_send_code:
            with self.assertRaises(ValueError):
                self.mpfb_list_objects(7)
            mock_send_code.assert_not_called()

    def test_unrecognized_filter_is_not_rejected_locally(self) -> None:
        # The vocabulary is MPFB's, and duplicating it here would let it drift.
        # A misspelling is answered by type_recognized, from inside Blender.
        with mock.patch("mpfbmcp.tools.list_objects.send_code") as mock_send_code:
            mock_send_code.return_value = {"status": "ok", "result": {"count": 0}}
            self.mpfb_list_objects("Basemseh")
            mock_send_code.assert_called_once()

    def test_response_is_passed_through_unchanged(self) -> None:
        envelope = {"status": "error", "message": "boom"}
        with mock.patch("mpfbmcp.tools.list_objects.send_code", return_value=envelope):
            self.assertEqual(self.mpfb_list_objects(), envelope)


class ListObjectsCodeTests(GeneratedCodeTestCase):
    def _run(self, object_type=None):
        scene_objects, all_objects = _scene()
        return self.run_payload(
            "list_objects.py", {"object_type": object_type},
            scene_objects=scene_objects, all_objects=all_objects)

    def test_no_filter_lists_every_makehuman_object_in_the_scene(self) -> None:
        result = self._run()

        # The plain cube is excluded because it has no MPFB type; Orphan is
        # excluded because it is not linked into the scene.
        self.assertEqual(
            [entry["name"] for entry in result["objects"]],
            ["Human.rig", "Human", "Fedora", "Proxy"])
        self.assertEqual(result["count"], 4)
        self.assertIsNone(result["requested_type"])
        self.assertTrue(result["type_recognized"])
        # The tool sends this with strict_json=True, so anything left in result
        # that json cannot encode turns the whole call into an error envelope.
        json.dumps(result)

    def test_entries_carry_both_types(self) -> None:
        skeleton = self._run()["objects"][0]

        self.assertEqual(skeleton["object_type"], "Skeleton")
        self.assertEqual(skeleton["blender_type"], "ARMATURE")

    def test_filter_uses_mpfb_substring_matching(self) -> None:
        # MPFB matches a requested type as a substring of the stored one, so
        # "mesh" is Basemesh and Proxymeshes both. Inheriting that rather than
        # inventing stricter equality is deliberate.
        self.assertEqual(
            [entry["name"] for entry in self._run("mesh")["objects"]], ["Human", "Proxy"])
        self.assertEqual(
            [entry["name"] for entry in self._run("Basemesh")["objects"]], ["Human"])

    def test_known_types_come_from_mpfb(self) -> None:
        result = self._run()

        self.assertIn("Basemesh", result["known_types"])
        self.assertIn("Subrig", result["known_types"])

    def test_unrecognized_type_is_flagged_beside_the_empty_list(self) -> None:
        # The pairing is the whole point: without type_recognized, a misspelling
        # is indistinguishable from a scene that genuinely has no basemeshes.
        result = self._run("Basemseh")

        self.assertEqual(result["objects"], [])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["requested_type"], "Basemseh")
        self.assertFalse(result["type_recognized"])

    def test_recognized_type_matching_nothing_stays_recognized(self) -> None:
        result = self._run("Eyebrows")

        self.assertEqual(result["objects"], [])
        self.assertTrue(result["type_recognized"])


def _params_in(code: str) -> dict:
    """The PARAMS the generated source will bind, by executing its prelude."""
    prelude, _sep, _payload = code.partition("# --- payload:")
    # The prelude sits behind the raising bootstrap, which would fail here with
    # no MPFB loaded, so run only the two lines that bind PARAMS.
    namespace: dict = {}
    exec(prelude[prelude.index("import json"):], namespace)  # noqa: S102
    return namespace["PARAMS"]


if __name__ == "__main__":
    unittest.main()
