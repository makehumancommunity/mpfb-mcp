# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_add_rig tool: argument validation, and the generated code's
dispatch, pre-checks and reporting.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_command`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source executed
against the stub services and a real temporary rig tree
(tests/blender_stubs.py's RigTestCase). That third layer is **frozen**: it stays
while the payload stays, because the payload is half of what FR 032's live
comparison compares.

The rig tree is shared with tests/test_list_rigs.py deliberately - the point of
the shared rig_lookup rule is that the catalogue's prediction and this tool's
outcome cannot disagree, and that can only be asserted by running both against
the same disk. **Both halves of that pair are now on the bridge**, so the same
agreement is checked there against a real MPFB.

What layer 3 cannot say is that a rig added through this tool is
indistinguishable from one added through MPFB's own panel. That is now checked
in ``bridge/test/tests/ppp_mutating/add_rig_test.py``.

Run with::

    python -m unittest tests.test_add_rig -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import add_rig

from tests import fake_bridge




# Distinguishes "the test did not say" from "the test said: nothing is active".
_UNSET = object()


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    add_rig.register(mcp)
    return mcp._tool_manager._tools["mpfb_add_rig"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape only. Which rigs exist is a directory listing inside Blender."""

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **kwargs):
        """The command and the parameters that reached the wire."""
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_command.call_args[0]

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is carried through with its status and message intact and
        # an `error` slug added, which is the seam's one mapping: a caller
        # branches on `error` without having to learn which transport answered.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool(identifier="default")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")

    def test_a_missing_or_empty_identifier_is_rejected_locally(self):
        for bad in ("", "   ", None, 3, ["default"]):
            with self.subTest(identifier=bad):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(identifier=bad)
                send_command.assert_not_called()

    def test_an_explicitly_empty_name_is_never_read_as_an_omitted_one(self):
        for bad in ("", "   ", 7, []):
            with self.subTest(name=bad):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad, identifier="default")
                send_command.assert_not_called()

    def test_non_bool_import_weights_is_rejected_locally(self):
        # Truthiness would make import_weights="false" add a rig the mesh is
        # parented to but not deformed by, which is invisible until it is posed.
        for bad in (1, 0, "true", "false", None, []):
            with self.subTest(import_weights=bad):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(identifier="default", import_weights=bad)
                send_command.assert_not_called()

    def test_the_vocabulary_is_deliberately_not_validated_here(self):
        # A rig list kept on this side of the socket would drift from the
        # directories, so an unknown identifier has to reach Blender to be
        # refused there, with known_identifiers beside it.
        self.assertEqual(self._sent(identifier="no-such-rig")[1]["identifier"],
                         "no-such-rig")


class AddRigOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - which file loads, whose weights come with it, the ordering warning, the AssertionError path - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/add_rig_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "add_rig": fake_bridge.ok_envelope("add_rig", {"found": True, "added": True, "performed": True}),
        })

    def test_the_tool_sends_the_add_rig_command(self) -> None:
        self.call(identifier="default")

        self.assertEqual(self.bridge.commands()[-1], "add_rig")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params, {"name": None, "identifier": "default", "import_weights": True})

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(identifier="default")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("rig_lookup", str(request))

    def test_the_identifier_is_not_validated_against_a_vocabulary_here(self) -> None:
        # A rig list kept on this side of the socket would drift from the
        # directories, so an unknown identifier reaches the bridge to be refused
        # there, with known_identifiers beside it.
        self.call(identifier="no-such-rig")

        self.assertEqual(
            self.bridge.decoded_requests()[-1]["params"]["identifier"], "no-such-rig")

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        for value in ("", "   ", None, 3):
            with self.subTest(identifier=value):
                with self.assertRaises(ValueError):
                    self.call(identifier=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="add_rig", state="absent"))

        response = self.call(identifier="default")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
