# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_face_units tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. What MPFB actually answers - the zero-for-missing
convention, the region grouping, the installed-pack probe and its cache - is
checked against a real MPFB in
``bridge/test/tests/rrr_get_face_units_test.py``.

Run with::

    python -m unittest tests.test_get_face_units -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_face_units

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_face_units.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_get_face_units"].fn


class ArgumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.tool = _tool_callable()

    def test_a_call_with_no_arguments_is_legal(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertEqual(send_command.call_args[0][1], {
            "name": None, "include_zero": False, "refresh": False})

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], object(), "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()

    def test_flags_must_be_real_bools(self):
        # "false" is a true value, so include_zero="false" would otherwise
        # return all 52 units instead of the non-zero ones.
        for argument in ("include_zero", "refresh"):
            for bad in ("false", "true", 0, 1, None):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.rig", include_zero=True, refresh=True)
        self.assertEqual(send_command.call_args[0][1], {
            "name": "Human.rig", "include_zero": True, "refresh": True})

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GetFaceUnitsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    What MPFB reports for a real character - the entries, the region grouping,
    the probe - is checked against a real MPFB in
    ``bridge/test/tests/rrr_get_face_units_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_face_units": fake_bridge.ok_envelope(
                "get_face_units", {"found": True, "face_units": [], "known_face_units": {}}),
        })

    def test_the_tool_sends_the_get_face_units_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "get_face_units")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["include_zero"], False)
        self.assertEqual(params["refresh"], False)

    def test_the_request_is_the_arguments_and_nothing_else(self) -> None:
        self.call()

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(set(request), {"command", "params", "protocol_version"})

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "FaceService.read_current_expression() raised.",
                command="get_face_units"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")
