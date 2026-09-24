# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_set_face_units tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. Entry *shape* is checked here - that an entry is a
dict, that its keys are known, that a weight is a real number in 0.0-1.0. The
ARKit vocabulary is deliberately not checked here (see
``test_an_unknown_face_unit_is_not_rejected_locally``): whether "browDownLeft"
is real is answered by the payload against MPFB's own ``ARKIT_FACEUNITS``.

What the payload does with a resolved batch - the all-or-nothing vocabulary
refusal, the pack-absent refusal, on-demand loading, the
zero-weight-absent-shape-key skip, and the refit - is checked against a real
MPFB in ``bridge/test/tests/ddd_mutating/set_face_units_test.py``.

Run with::

    python -m unittest tests.test_set_face_units -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import set_face_units

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_face_units.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_set_face_units"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Entry *shape* checked here; the ARKit vocabulary is not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_a_call_with_no_face_units_is_legal(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertEqual(send_command.call_args[0][1], {
            "name": None, "face_units": [], "clear_first": False, "refit": True})

    def test_entries_are_normalized_before_they_cross_the_socket(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(face_units=[{"face_unit": "jawOpen", "weight": 1}])
        self.assertEqual(send_command.call_args[0][1]["face_units"],
                         [{"face_unit": "jawOpen", "weight": 1.0}])

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], object(), "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()

    def test_flags_must_be_real_bools(self):
        for argument in ("clear_first", "refit"):
            for bad in ("false", "true", 0, 1, None):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_face_units_must_be_a_list_of_objects(self):
        for bad in ("jawOpen", {"face_unit": "jawOpen"}, 3, [1], ["x"], [None]):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(face_units=bad)
                send_command.assert_not_called()

    def test_an_unknown_key_in_an_entry_is_rejected_locally(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError) as raised:
                self.tool(face_units=[{"faceunit": "jawOpen", "weight": 0.5}])
        send_command.assert_not_called()
        self.assertIn("faceunit", str(raised.exception))

    def test_the_error_names_the_offending_entry_by_position(self):
        with self.assertRaises(ValueError) as raised:
            self.tool(face_units=[
                {"face_unit": "jawOpen", "weight": 0.5},
                {"face_unit": "mouthLeft", "weight": 5.0}])

        self.assertIn("face_units[1]", str(raised.exception))

    def test_a_missing_key_is_rejected_locally(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(face_units=[{"face_unit": "jawOpen"}])
            with self.assertRaises(ValueError):
                self.tool(face_units=[{"weight": 0.5}])
        send_command.assert_not_called()

    def test_a_weight_must_be_a_number_in_zero_to_one(self):
        # 0.0-1.0 and not wider: a raw shape key value, which Blender clamps to
        # that range. A negative here would silently store 0.0.
        for bad in (-0.4, 1.5, True, False, "0.5", None, [0.5]):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(face_units=[{"face_unit": "jawOpen", "weight": bad}])
                send_command.assert_not_called()

    def test_an_empty_face_unit_name_is_rejected_locally(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(face_units=[{"face_unit": "  ", "weight": 0.5}])
        send_command.assert_not_called()

    def test_a_batch_above_the_ceiling_is_rejected_locally(self):
        entries = [{"face_unit": "jawOpen", "weight": 0.1}] * (
            set_face_units.MAX_ENTRIES + 1)
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(face_units=entries)
        send_command.assert_not_called()

    def test_an_unknown_face_unit_is_not_rejected_locally(self):
        # Whether "browDownLeft" is real ARKit vocabulary is answered by the
        # payload against MPFB's own ARKIT_FACEUNITS, not by a copy here.
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(face_units=[{"face_unit": "no-such-unit", "weight": 0.5}])
        send_command.assert_called_once()

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")


class SetFaceUnitsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    The all-or-nothing vocabulary check, the pack-absent refusal and the write
    order are checked against a real MPFB in
    ``bridge/test/tests/ddd_mutating/set_face_units_test.py``. What is left
    here is the per-entry validation this tool does before any transport is
    chosen.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_face_units": fake_bridge.ok_envelope(
                "set_face_units", {"found": True, "applied": [], "performed": False}),
        })

    def test_the_tool_sends_the_set_face_units_command(self) -> None:
        self.call(face_units=[{"face_unit": "jawOpen", "weight": 0.4}])

        self.assertEqual(self.bridge.commands()[-1], "set_face_units")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["face_units"], [{"face_unit": "jawOpen", "weight": 0.4}])
        self.assertEqual(params["clear_first"], False)
        self.assertEqual(params["refit"], True)

    def test_refit_defaults_to_true_unlike_every_other_refitting_tool(self) -> None:
        self.call()

        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["refit"], True)

    def test_the_request_is_the_arguments_and_nothing_else(self) -> None:
        self.call()

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(set(request), {"command", "params", "protocol_version"})

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "FaceService.set_expression() raised.",
                command="set_face_units"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")
