# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_objects tool, which is the migrated one.

**This module is what a migrated tool's tests look like during the
transition**, and it has three layers where every other tool module has two.
Two of them are permanent and one is not:

1. **The wrapper**, with ``send_code`` mocked. Argument validation, defaulting
   and the decision of what to send. Unchanged by the migration except for
   where the mock is attached - it patches ``mpfbmcp.backend.send_code`` now,
   because the seam is what assembles the program.
2. **The bridge path**, against ``tests/fake_bridge.py``. Deliberately thin,
   because it is only what cannot cross the socket: that the right command and
   the same parameters go on the wire, that the tool's own validation runs
   before a transport is chosen, and that an error envelope reaches the caller
   intact. **Nothing here asserts what MPFB answers.** Those assertions moved to
   ``bridge/test/tests/fff_list_objects_test.py``, where they are made against
   a real MPFB in a headless Blender instead of against a stub written by
   whoever wrote the code under test.
3. **The payload**, ``exec()``-ed against the stubs in
   ``tests/blender_stubs.py``. **Frozen.** It stays while the payload stays,
   because the payload is half of what FR 030's live comparison compares, and
   it is deleted with the payload when the generated path is retired. It is not
   extended and nothing is added to it - a new assertion about MPFB's behaviour
   belongs in the bridge's suite, however well it would pass here.

The share of this module that goes with the payload is worth knowing, since it
is the first real evidence about what the pivot does to 14.2k lines of tests:
``ListObjectsCodeTests`` and the stub scene it needs are 74 of 275 lines, 27%,
for a payload of 87 lines whose logic is a filter and a substring test. Read it
as a floor rather than a rate: this is the *dullest* tool in the package, and
the payloads with real branching in them are the ones stage 3 has to estimate.

Run with::

    python -m unittest tests.test_list_objects -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import backend
from mpfbmcp.tools import list_objects
from tests import fake_bridge
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

    @mock.patch("mpfbmcp.backend.send_code")
    def test_omitted_filter_is_sent_as_null(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"count": 0}}

        self.mpfb_list_objects()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertEqual(_params_in(code), {"object_type": None})

    @mock.patch("mpfbmcp.backend.send_code")
    def test_filter_is_passed_through_verbatim(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"count": 0}}

        self.mpfb_list_objects("Basemesh")

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code), {"object_type": "Basemesh"})

    def test_blank_filter_is_rejected_locally(self) -> None:
        # An empty filter would substring-match every type rather than none, so
        # it must fail here rather than come back as a full listing.
        with mock.patch("mpfbmcp.backend.send_code") as mock_send_code:
            for blank in ("", "   ", "\t"):
                with self.subTest(object_type=blank):
                    with self.assertRaises(ValueError):
                        self.mpfb_list_objects(blank)
            mock_send_code.assert_not_called()

    def test_non_string_filter_is_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.backend.send_code") as mock_send_code:
            with self.assertRaises(ValueError):
                self.mpfb_list_objects(7)
            mock_send_code.assert_not_called()

    def test_unrecognized_filter_is_not_rejected_locally(self) -> None:
        # The vocabulary is MPFB's, and duplicating it here would let it drift.
        # A misspelling is answered by type_recognized, from inside Blender.
        with mock.patch("mpfbmcp.backend.send_code") as mock_send_code:
            mock_send_code.return_value = {"status": "ok", "result": {"count": 0}}
            self.mpfb_list_objects("Basemseh")
            mock_send_code.assert_called_once()

    def test_a_successful_response_is_passed_through_unchanged(self) -> None:
        envelope = {"status": "ok", "result": {"count": 0}}
        with mock.patch("mpfbmcp.backend.send_code", return_value=envelope):
            self.assertEqual(self.mpfb_list_objects(), envelope)

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self) -> None:
        # The envelope is this package's now: `status` and `message` are
        # unchanged, and `error` is what a caller branches on whichever
        # transport answered. The mapping itself is tests/test_backend.py's.
        with mock.patch("mpfbmcp.backend.send_code",
                        return_value={"status": "error", "message": "boom"}):
            response = self.mpfb_list_objects()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "boom")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)


class ListObjectsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Deliberately four tests. Everything this tool *answers* - the substring
    match, the unrecognised type, the empty scene, the vocabulary and its
    fallback - is checked against a real MPFB in the bridge's own suite, and a
    copy of it here would be a check against a stub the author also wrote,
    passing for the same reason it always did.
    """

    def setUp(self) -> None:
        super().setUp()
        self.mpfb_list_objects = _register_and_get_tool()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })

    def test_the_tool_sends_the_list_objects_command(self) -> None:
        self.mpfb_list_objects()

        self.assertEqual(self.bridge.commands(), ["get_status", "list_objects"])
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"object_type": None})

    def test_a_filter_crosses_the_wire_verbatim(self) -> None:
        self.mpfb_list_objects("Basemesh")

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"object_type": "Basemesh"})

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        # The empty string is refused for MPFB's substring reason - an empty
        # filter matches every type rather than none - and that refusal is the
        # tool's, not the transport's, so configuring the bridge does not move
        # it. Nothing should reach the socket at all.
        for blank in ("", "   ", "\t"):
            with self.subTest(object_type=blank):
                with self.assertRaises(ValueError):
                    self.mpfb_list_objects(blank)

        with self.assertRaises(ValueError):
            self.mpfb_list_objects(7)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="list_objects", state="absent"))

        response = self.mpfb_list_objects()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
        self.assertEqual(response["state"], "absent")
        self.assertIn("MPFB", response["message"])


class ListObjectsCodeTests(GeneratedCodeTestCase):
    """The payload against the stubs. **Frozen**: see this module's docstring."""

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
