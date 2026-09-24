# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_list_objects tool, which was the first one migrated.

**This module is the template every other tool module follows**, and it has two
layers:

1. **The wrapper**, with ``send_command`` mocked below the seam. Argument
   validation, defaulting and the decision of what to send.
2. **The bridge path**, against ``tests/fake_bridge.py``. Deliberately thin,
   because it is only what cannot cross the socket: that the right command and
   the same parameters go on the wire, that the tool's own validation runs
   before anything is sent, and that an error envelope reaches the caller
   intact. **Nothing here asserts what MPFB answers.** Those assertions live in
   ``bridge/test/tests/ccc_reading/list_objects_test.py``, where they are made against
   a real MPFB in a headless Blender instead of against a stub written by
   whoever wrote the code under test.

There was a third layer until FR 033: the generated program ``exec()``-ed
against stub services and a stub scene. It was 27% of this module - the lowest
rate in the suite, since this tool's logic is a filter and a substring test -
and across the twenty-four migrated modules the rate averaged near 60%. See
``feature-requests/HISTORY.md`` for the measurements, which are the evidence
about what the pivot did to 14.2k lines of tests.

Run with::

    python -m unittest tests.test_list_objects -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import list_objects
from tests import fake_bridge




def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    list_objects.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_list_objects"]  # noqa: SLF001
    return tool.fn


class ListObjectsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_list_objects = _register_and_get_tool()

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_filter_is_passed_through_verbatim(self, mock_send_command: mock.Mock) -> None:
        mock_send_command.return_value = {"status": "ok", "result": {"count": 0}}

        self.mpfb_list_objects("Basemesh")

        (command, params), _kwargs = mock_send_command.call_args
        self.assertEqual(params, {"object_type": "Basemesh"})

    def test_blank_filter_is_rejected_locally(self) -> None:
        # An empty filter would substring-match every type rather than none, so
        # it must fail here rather than come back as a full listing.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for blank in ("", "   ", "\t"):
                with self.subTest(object_type=blank):
                    with self.assertRaises(ValueError):
                        self.mpfb_list_objects(blank)
            mock_send_command.assert_not_called()

    def test_non_string_filter_is_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            with self.assertRaises(ValueError):
                self.mpfb_list_objects(7)
            mock_send_command.assert_not_called()

    def test_unrecognized_filter_is_not_rejected_locally(self) -> None:
        # The vocabulary is MPFB's, and duplicating it here would let it drift.
        # A misspelling is answered by object_type_recognized, from inside Blender.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            mock_send_command.return_value = {"status": "ok", "result": {"count": 0}}
            self.mpfb_list_objects("Basemseh")
            mock_send_command.assert_called_once()

    def test_a_successful_response_is_passed_through_unchanged(self) -> None:
        envelope = {"status": "ok", "result": {"count": 0}}
        with mock.patch("mpfbmcp.bridge_connection.send_command", return_value=envelope):
            self.assertEqual(self.mpfb_list_objects(), envelope)

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self) -> None:
        # The envelope is this package's now: `status` and `message` are
        # unchanged, and `error` is what a caller branches on whichever
        # transport answered. The mapping itself is tests/test_backend.py's.
        with mock.patch("mpfbmcp.bridge_connection.send_command",
                        return_value={"status": "error", "error": "mpfb_unavailable",
                                      "message": "boom"}):
            response = self.mpfb_list_objects()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "boom")
        self.assertEqual(response["error"], "mpfb_unavailable")


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
