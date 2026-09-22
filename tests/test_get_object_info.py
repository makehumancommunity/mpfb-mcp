# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_object_info tool, in two layers (see
``tests/test_list_objects.py``, the template).

1. **The wrapper**, with ``send_command`` mocked below the seam: argument
   validation, and what goes on the wire.
2. **The bridge path**, against ``tests/fake_bridge.py``. Thin, and deliberately
   so - nothing here asserts what MPFB answers.

The three ``asset_info`` shapes and their three resolution outcomes each, the
relationship walk, and the MPFB behaviours this tool is written around - ``""``
for an untyped object, a non-bool ``object_is_any_makehuman_object()``, a
``find_related_objects()`` that yields the subject itself - are asserted
against a real install in ``bridge/test/tests/hhh_get_object_info_test.py``.

Run with::

    python -m unittest tests.test_get_object_info -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import get_object_info
from tests import fake_bridge



_SKIN_FRAGMENT = "young_caucasian_female/young_caucasian_female.mhmat"
_FEDORA_FRAGMENT = "fedora/fedora.mhclo"


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    get_object_info.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_get_object_info"]  # noqa: SLF001
    return tool.fn


class GetObjectInfoToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_get_object_info = _register_and_get_tool()

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_name_is_passed_through_verbatim(self, mock_send_command: mock.Mock) -> None:
        mock_send_command.return_value = {"status": "ok", "result": {"found": True}}

        self.mpfb_get_object_info("Human.003")

        (command, params), _kwargs = mock_send_command.call_args
        self.assertEqual(params, {"name": "Human.003"})

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_a_name_full_of_quotes_survives_as_data(self, mock_send_command: mock.Mock) -> None:
        # Parameters are carried as JSON data rather than interpolated into the
        # source, so a hostile object name cannot restructure the program.
        mock_send_command.return_value = {"status": "ok", "result": {"found": False}}
        hostile = "'\"\"\"\nresult = {}\n#"

        self.mpfb_get_object_info(hostile)

        (command, params), _kwargs = mock_send_command.call_args
        self.assertEqual(params, {"name": hostile})

    def test_blank_name_is_rejected_rather_than_treated_as_omitted(self) -> None:
        # The two come from different mistakes: answering about whatever happens
        # to be selected, when the caller believed they named something, is
        # worse than failing.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for blank in ("", "   ", "\n"):
                with self.subTest(name=blank):
                    with self.assertRaises(ValueError):
                        self.mpfb_get_object_info(blank)
            mock_send_command.assert_not_called()

    def test_non_string_name_is_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            with self.assertRaises(ValueError):
                self.mpfb_get_object_info(12)
            mock_send_command.assert_not_called()

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self) -> None:
        # `status` and `message` are unchanged and `error` is what a caller
        # branches on whichever transport answered.
        with mock.patch("mpfbmcp.bridge_connection.send_command",
                        return_value={"status": "error", "error": "mpfb_unavailable",
                                      "message": "boom"}):
            response = self.mpfb_get_object_info()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "boom")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GetObjectInfoOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the three ``asset_info`` shapes, the
    relationship walk, the untyped neighbourhood, what resolves from what - is
    checked against a real MPFB in the bridge's own suite.
    """

    def setUp(self) -> None:
        super().setUp()
        self.mpfb_get_object_info = _register_and_get_tool()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_object_info": fake_bridge.ok_envelope("get_object_info", {"found": False}),
        })

    def test_the_tool_sends_the_get_object_info_command(self) -> None:
        self.mpfb_get_object_info()

        self.assertEqual(self.bridge.commands()[-1], "get_object_info")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": None})

    def test_a_name_crosses_the_wire_verbatim(self) -> None:
        self.mpfb_get_object_info("Human.body")

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": "Human.body"})

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        # A blank name and an omitted one arise from different mistakes, so the
        # blank one is refused rather than treated as "use the active object" -
        # and that refusal is the tool's, not the transport's.
        for blank in ("", "   ", "\t"):
            with self.subTest(name=blank):
                with self.assertRaises(ValueError):
                    self.mpfb_get_object_info(blank)

        with self.assertRaises(ValueError):
            self.mpfb_get_object_info(12)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="get_object_info", state="absent"))

        response = self.mpfb_get_object_info()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
        self.assertEqual(response["state"], "absent")
