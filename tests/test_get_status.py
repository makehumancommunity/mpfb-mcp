# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_get_status tool, in two layers (see
``tests/test_list_objects.py``, the template).

1. **The wrapper**, with ``send_command`` mocked below the seam. This tool takes
   no arguments at all, so what is left here is the smallest a wrapper layer
   gets: that the envelope reaches the caller unreshaped.
2. **The bridge path**, against ``tests/fake_bridge.py``. Thin, and one of its
   tests exists only for this tool: the command it sends is ``get_mpfb_status``
   and **not** ``get_status``, which the bridge already uses for its own state.
   A tool that sent ``get_status`` would get a plausible-looking answer about
   the wrong piece of software.

Everything this tool *answers* - the three states, the tiers of fields, the
disabled-but-loaded case - is checked against a real MPFB in
``bridge/test/tests/ccc_reading/get_mpfb_status_test.py``, where it is asserted against
a real install rather than against stubs written by whoever wrote the code
under test. Half of this module used to be a third layer executing the payload
against stubbed ``sys.modules`` entries; FR 033 deleted the payload and the
layer with it.

Run with::

    python -m unittest tests.test_get_status -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import get_status
from tests import fake_bridge



def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    get_status.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_get_status"]  # noqa: SLF001
    return tool.fn


class GetStatusToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_get_status = _register_and_get_tool()

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_response_is_passed_through_unchanged(self, mock_send_command: mock.Mock) -> None:
        # The tool must not interpret or reshape the envelope: graceful absence
        # lives in the add-on, not in Python on this side of the socket.
        envelope = {"status": "ok", "result": {"state": "absent", "candidate_modules": []}}
        mock_send_command.return_value = envelope

        self.assertEqual(self.mpfb_get_status(), envelope)

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self) -> None:
        # `status` and `message` are unchanged and `error` is what a caller
        # branches on whichever transport answered. The mapping is
        # tests/test_backend.py's.
        with mock.patch("mpfbmcp.bridge_connection.send_command",
                        return_value={"status": "error", "error": "mpfb_unavailable",
                                      "message": "boom"}):
            response = self.mpfb_get_status()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "boom")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GetStatusOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the three states, the tiers of fields, the
    disabled-but-loaded case - is checked against a real MPFB in the bridge's
    own suite.
    """

    def setUp(self) -> None:
        super().setUp()
        self.mpfb_get_status = _register_and_get_tool()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_mpfb_status": fake_bridge.ok_envelope(
                "get_mpfb_status", {"state": "ok", "candidate_modules": []}),
        })

    def test_the_tool_sends_get_mpfb_status_and_not_get_status(self) -> None:
        # The one naming exception in MIGRATED_COMMANDS, asserted where it would
        # actually bite: `get_status` is the bridge's own state, and a tool
        # sending it would get a well-formed answer about the wrong software.
        self.mpfb_get_status()

        # The first `get_status` is the handshake probe, which every first call
        # to an address makes; the command this tool sent is the last one.
        self.assertEqual(self.bridge.commands()[-1], "get_mpfb_status")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {})

    def test_the_answer_reaches_the_caller_as_it_arrived(self) -> None:
        response = self.mpfb_get_status()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["state"], "ok")

    def test_absence_is_still_a_successful_answer_over_the_bridge(self) -> None:
        # The whole value of this tool, and the reason its command declares
        # requires_mpfb=False: a Blender with no MPFB answers rather than
        # refusing. The bridge's precondition would have produced an
        # mpfb_unavailable envelope instead.
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.ok_envelope("get_mpfb_status", {
                "state": "absent",
                "message": "MPFB is not loaded in this Blender instance",
                "candidate_modules": []}))

        response = self.mpfb_get_status()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["state"], "absent")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "The command raised while running inside Blender.",
                command="get_mpfb_status"))

        response = self.mpfb_get_status()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")
