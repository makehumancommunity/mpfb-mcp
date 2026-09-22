# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_remove_asset tool: argument validation, and the generated
code's refusals, its read-before-deleting, and what it reports being left with.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_command`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source executed
against the stub services and the same temporary asset library
tests/test_add_asset.py uses. That third layer is **frozen**: it stays while the
payload stays, because the payload is half of what FR 032's live comparison
compares.

Several of layer 3's cases equip an asset with mpfb_add_asset's payload first
and then remove it, because the interesting claims - which mask modifiers went,
which vertex groups stayed - are only meaningful about state that MPFB's own
loading path produced. ``bridge/test/tests/ppp_mutating/remove_asset_test.py``
does the same thing against a real MPFB, which is where the claim that a
character comes back to what it was now lives.

Run with::

    python -m unittest tests.test_remove_asset -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import remove_asset

from tests import fake_bridge




def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    remove_asset.register(mcp)
    return mcp._tool_manager._tools["mpfb_remove_asset"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape only. Whether the name is an asset is answered inside Blender."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_the_name_crosses_the_socket(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.fedora")
        command, params = send_command.call_args[0]
        self.assertEqual(command, "remove_asset")
        self.assertEqual(params, {"name": "Human.fedora"})

    def test_the_name_is_required(self):
        # No active-object fallback anywhere: this deletes an object, and
        # "whatever happens to be selected" is not a way to choose which.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(TypeError):
                self.tool()
            with self.assertRaises(ValueError):
                self.tool(name="  ")
            with self.assertRaises(ValueError):
                self.tool(name=None)
        send_command.assert_not_called()

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is carried through with its status and message intact and
        # an `error` slug added, which is the seam's one mapping: a caller
        # branches on `error` without having to learn which transport answered.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool(name="Human.fedora")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")


class RemoveAssetOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the four fates a removal can have, and the two things MPFB leaves behind - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/remove_asset_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "remove_asset": fake_bridge.ok_envelope("remove_asset", {"found": True, "removed": True, "performed": True}),
        })

    def test_the_tool_sends_the_remove_asset_command(self) -> None:
        self.call(name="Human.fedora")

        self.assertEqual(self.bridge.commands()[-1], "remove_asset")
        self.assertEqual(
            self.bridge.decoded_requests()[-1]["params"], {"name": "Human.fedora"})

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(name="Human.fedora")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("performed", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        for value in ("", "   "):
            with self.subTest(name=value):
                with self.assertRaises(ValueError):
                    self.call(name=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="remove_asset", state="absent"))

        response = self.call(name="Human.fedora")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
