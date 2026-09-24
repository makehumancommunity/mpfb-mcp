# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_symmetrize_targets tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. The wrapper carries the package's **only required
argument**: which half of a face is the good one is not something a tool can
guess, and guessing wrong destroys work with no undo across the socket.

The category walk, the dry run agreeing with the real run, and the write order -
the opposing target is zeroed first, or pruning deletes the wrong half of a
pair - are checked against a real MPFB in
``bridge/test/tests/ddd_mutating/symmetrize_targets_test.py``.

Run with::

    python -m unittest tests.test_symmetrize_targets -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import symmetrize_targets

from tests import fake_bridge




def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    symmetrize_targets.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_symmetrize_targets"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Shape checked here; the section vocabulary deliberately is not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_direction_has_no_default(self):
        # Which half of a face is the good one is not something a tool can
        # guess, and guessing wrong destroys work.
        with self.assertRaises(TypeError):
            self.tool()

    def test_an_unknown_direction_is_rejected_locally(self):
        for bad in ("left", "LEFT_TO_RIGHT", "l2r", None, True, 1, ""):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(direction=bad)
                send_command.assert_not_called()

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(direction="right_to_left", name="Human.rig", section="eyes",
                      dry_run=True, prune=False, refit=True)
        self.assertEqual(send_command.call_args[0][1], {
            "name": "Human.rig", "direction": "right_to_left", "section": "eyes",
            "dry_run": True, "prune": False, "refit": True})

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is this package's: `status` and `message` are unchanged,
        # and `error` is what a caller branches on whichever transport answered.
        # Since FR 031 this tool's fragments go through the seam rather than
        # around it, so the mapping applies to a cached-fragment call too.
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool(direction="left_to_right")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")

    def test_non_string_or_empty_text_arguments_are_rejected_locally(self):
        for argument in ("name", "section"):
            for bad in (1, True, [], object(), "", "   "):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(direction="left_to_right", **{argument: bad})
                    send_command.assert_not_called()

    def test_flags_must_be_real_bools(self):
        # dry_run="false" would otherwise write.
        for argument in ("dry_run", "prune", "refit"):
            for bad in ("false", "true", 0, 1, None):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(direction="left_to_right", **{argument: bad})
                    send_command.assert_not_called()

    def test_an_unknown_section_is_not_rejected_locally(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(direction="left_to_right", section="no-such-section")
        send_command.assert_called_once()


class SymmetrizeTargetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    The category walk, the dry run agreeing with the real run, and the write
    order are checked against a real MPFB in
    ``bridge/test/tests/ddd_mutating/symmetrize_targets_test.py``. What is left
    here is the one required argument in the package, and that it is refused
    before a transport is chosen - which is what keeps the most destructive
    tool here from guessing which half of a face to keep.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "symmetrize_targets": fake_bridge.ok_envelope(
                "symmetrize_targets", {"found": True, "changed": [], "performed": False}),
        })

    def test_the_tool_sends_the_symmetrize_targets_command(self) -> None:
        self.call(direction="left_to_right")

        self.assertEqual(self.bridge.commands()[-1], "symmetrize_targets")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["direction"], "left_to_right")
        self.assertEqual(params["dry_run"], False)
        self.assertEqual(params["prune"], True)

    def test_a_dry_run_is_carried_as_a_parameter_like_any_other(self) -> None:
        self.call(direction="right_to_left", dry_run=True, section="nose")

        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["dry_run"], True)
        self.assertEqual(params["section"], "nose")

    def test_the_required_direction_is_refused_before_a_transport_is_chosen(self) -> None:
        # The package's only required argument, and the reason is that guessing
        # wrong destroys work with no undo across the socket.
        for value in (None, "", "leftward", 3):
            with self.subTest(direction=value):
                with self.assertRaises(ValueError):
                    self.call(direction=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_the_request_is_the_arguments_and_nothing_else(self) -> None:
        # What `modifier_reading` models is imported by the command; nothing
        # about it is on the wire.
        self.call(direction="left_to_right")

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(set(request), {"command", "params", "protocol_version"})
        self.assertNotIn("modifier_reading", str(request))

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "TargetService.set_target_value() raised.",
                command="symmetrize_targets"))

        response = self.call(direction="left_to_right")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")
