# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_macro_details tool, in two layers (see
``tests/test_list_objects.py``, the template).

1. **The wrapper**, with ``send_command`` mocked below the seam: argument
   validation, and what goes on the wire.
2. **The bridge path**, against ``tests/fake_bridge.py``. Thin on purpose.

The cases the tool exists for - resolving the basemesh from *any* member of the
character's family, reporting the raw race sum rather than a normalized one,
and reporting the derived target stack beside the shape keys actually on the
mesh so that a drifted character is visible - are asserted against a real MPFB
in ``bridge/test/tests/iii_get_macro_details_test.py``.

Run with::

    python -m unittest tests.test_get_macro_details -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import get_macro_details
from tests import fake_bridge




def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    get_macro_details.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_get_macro_details"]  # noqa: SLF001
    return tool.fn


class GetMacroDetailsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_get_macro_details = _register_and_get_tool()

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_name_is_passed_through_verbatim(self, mock_send_command: mock.Mock) -> None:
        mock_send_command.return_value = {"status": "ok", "result": {"found": True}}

        self.mpfb_get_macro_details("Human")

        (command, params), _kwargs = mock_send_command.call_args
        self.assertEqual(params, {"name": "Human"})

    def test_blank_name_is_rejected_locally(self) -> None:
        # An explicitly empty name and an omitted one arise from different
        # mistakes, so the empty one never falls back to the active object.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for blank in ("", "   ", "\t"):
                with self.subTest(name=blank):
                    with self.assertRaises(ValueError):
                        self.mpfb_get_macro_details(blank)
            mock_send_command.assert_not_called()

    def test_non_string_name_is_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for bad in (1, 1.5, True, ["Human"]):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        self.mpfb_get_macro_details(bad)
            mock_send_command.assert_not_called()


class GetMacroDetailsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - what resolves to a basemesh, what the
    macro dict holds, how the stack is derived and when drift is reported - is
    checked against a real MPFB in the bridge's own suite.
    """

    def setUp(self) -> None:
        super().setUp()
        self.mpfb_get_macro_details = _register_and_get_tool()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_macro_details": fake_bridge.ok_envelope("get_macro_details", {"found": False}),
        })

    def test_the_tool_sends_the_get_macro_details_command(self) -> None:
        self.mpfb_get_macro_details()

        self.assertEqual(self.bridge.commands()[-1], "get_macro_details")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": None})

    def test_a_name_crosses_the_wire_verbatim(self) -> None:
        self.mpfb_get_macro_details("Human.body")

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": "Human.body"})

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        # A blank name and an omitted one arise from different mistakes, so the
        # blank one is refused rather than treated as "use the active object" -
        # and that refusal is the tool's, not the transport's.
        for blank in ("", "   ", "\t"):
            with self.subTest(name=blank):
                with self.assertRaises(ValueError):
                    self.mpfb_get_macro_details(blank)

        with self.assertRaises(ValueError):
            self.mpfb_get_macro_details(12)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="get_macro_details", state="absent"))

        response = self.mpfb_get_macro_details()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
        self.assertEqual(response["state"], "absent")
