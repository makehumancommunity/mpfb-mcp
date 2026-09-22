# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_list_rigs tool: argument validation, and what crosses the
socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``.

This tool's whole job is ``os.listdir()`` and ``os.path.isfile()`` over MPFB's
rig directories, so it can only be checked against a real tree.
``bridge/test/tests/kkk_list_rigs_test.py`` builds one and points MPFB's own
``LocationService`` at it, reproducing the asymmetries a real install has - a
rig with no weights file of its own, a weights file with no rig, a rig with no
entry in the UI enum - and it is also where the claim that this catalogue's
weights prediction equals ``mpfb_add_rig``'s outcome is anchored, since both
halves of that pair are now commands running against one disk.

Run with::

    python -m unittest tests.test_list_rigs -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from tests import fake_bridge

from mpfbmcp.tools import list_rigs





def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_rigs.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_rigs"].fn  # pylint: disable=protected-access


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


class RefreshValidationTests(unittest.TestCase):
    """The one argument, validated before anything crosses the socket."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_default_call_sends_refresh_false(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        command, params = send_command.call_args[0]
        self.assertEqual(command, "list_rigs")
        self.assertEqual(params, {"refresh": False})

    def test_refresh_true_is_carried_across(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(refresh=True)
        self.assertEqual(send_command.call_args[0][1], {"refresh": True})

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")

    def test_non_bool_refresh_is_rejected_locally(self):
        # A truthy int or the string "false" is how a caller signals a bool it
        # failed to build; accepting either would make refresh="false" rescan.
        for bad in (1, 0, "true", "false", None, [], object()):
            with self.subTest(refresh=bad):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(refresh=bad)
                send_command.assert_not_called()


class ListRigsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - which files are listed, which weights the
    fallback table resolves to, what happens when Rigify is off - is checked
    against a real MPFB in ``bridge/test/tests/kkk_list_rigs_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.tool = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_rigs": fake_bridge.ok_envelope("list_rigs", {"count": 0}),
        })

    def test_the_tool_sends_the_list_rigs_command(self):
        self.tool()

        self.assertEqual(self.bridge.commands()[-1], "list_rigs")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"refresh": False})

    def test_the_shared_fragment_does_not_reach_the_bridge(self):
        # rig_lookup.py is a property of how a *program* is assembled. On the
        # bridge it is a module the command imports, so the request is exactly
        # the parameters.
        self.tool(refresh=True)

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(request["params"], {"refresh": True})
        self.assertNotIn("rig_lookup", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self):
        for bad in (1, 0, "true", "false", None, [], object()):
            with self.subTest(refresh=bad):
                with self.assertRaises(ValueError):
                    self.tool(refresh=bad)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self):
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="list_rigs", state="absent"))

        response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
