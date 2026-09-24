# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_set_targets tool: argument validation, and what crosses the
socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. The wrapper carries an unusual amount, because this is
the **batched** tool: every entry is shape-checked, range-checked against one of
two different ranges, and rejected for an unknown key before anything is sent,
since a misspelled ``catagory`` is otherwise silent.

That every entry is resolved before any is written - so a batch with one bad
entry applies nothing at all - is checked against a real MPFB in
``bridge/test/tests/ddd_mutating/set_targets_test.py``.

Run with::

    python -m unittest tests.test_set_targets -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import set_targets

from tests import fake_bridge



_ENCODED_LONG_NAME = "$yn-$fe-$av-$ca-$un-$pr-$wg-$hg-experiment"


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_targets.register(mcp)
    return mcp._tool_manager._tools["mpfb_set_targets"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Entry *shape* checked here; section and category vocabulary is not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_entries_are_normalized_before_they_cross_the_socket(self):
        # An omitted side arrives as an explicit null, and an int value as a
        # float, so the command never has to guess what a missing key meant.
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(modifiers=[{"section": "nose", "category": "c", "value": 1}],
                      targets=[{"shapekey_name": "vwide", "value": 0}])
        self.assertEqual(send_command.call_args[0][1], {
            "name": None,
            "modifiers": [{"section": "nose", "category": "c", "value": 1.0, "side": None}],
            "targets": [{"shapekey_name": "vwide", "value": 0.0}],
            "symmetry": False, "prune": True, "refit": False})

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is this package's: `status` and `message` are unchanged,
        # and `error` is what a caller branches on whichever transport answered.
        # Since FR 031 this tool's fragments go through the seam rather than
        # around it, so the mapping applies to a cached-fragment call too.
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], object(), "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_command.assert_not_called()

    def test_flags_must_be_real_bools(self):
        for argument in ("symmetry", "prune", "refit"):
            for bad in ("false", "true", 0, 1, None):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_a_list_argument_must_be_a_list_of_objects(self):
        for bad in ("modifiers", {"section": "nose"}, 3, [1], ["x"], [None]):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(modifiers=bad)
                send_command.assert_not_called()

    def test_an_unknown_key_in_an_entry_is_rejected_locally(self):
        # A misspelled key is the commonest way a caller gets a dict-shaped
        # argument wrong, and it is silent unless it is checked.
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError) as raised:
                self.tool(modifiers=[
                    {"section": "nose", "catagory": "c", "value": 0.1}])
        send_command.assert_not_called()
        self.assertIn("catagory", str(raised.exception))

    def test_the_error_names_the_offending_entry_by_position(self):
        with self.assertRaises(ValueError) as raised:
            self.tool(modifiers=[
                {"section": "nose", "category": "c", "value": 0.1},
                {"section": "nose", "category": "c", "value": 5.0}])

        self.assertIn("modifiers[1]", str(raised.exception))

    def test_a_modifier_value_must_be_a_number_in_minus_one_to_one(self):
        for bad in (True, False, "0.5", None, 1.5, -1.5, [0.5]):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(modifiers=[
                            {"section": "nose", "category": "c", "value": bad}])
                send_command.assert_not_called()

    def test_a_raw_target_value_must_be_a_number_in_zero_to_one(self):
        # Narrower than a modifier's on purpose: Blender clamps a shape key
        # value to 0.0-1.0, so a negative here would silently store 0.0.
        for bad in (-0.4, 1.5, True, "0.5", None):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(targets=[{"shapekey_name": "x", "value": bad}])
                send_command.assert_not_called()

    def test_a_side_must_be_one_of_three_strings_or_omitted(self):
        for bad in ("l", "Left", 1, True, ""):
            with self.subTest(value=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(modifiers=[
                            {"section": "nose", "category": "c", "value": 0.1, "side": bad}])
                send_command.assert_not_called()

    def test_empty_entry_strings_are_rejected_locally(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(modifiers=[{"section": "  ", "category": "c", "value": 0.1}])
            with self.assertRaises(ValueError):
                self.tool(targets=[{"shapekey_name": "", "value": 0.1}])
        send_command.assert_not_called()

    def test_a_batch_above_the_ceiling_is_rejected_locally(self):
        entries = [{"section": "nose", "category": "c", "value": 0.1}] * (
            set_targets.MAX_ENTRIES + 1)
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(modifiers=entries)
        send_command.assert_not_called()

    def test_an_unknown_section_or_category_is_not_rejected_locally(self):
        # Half the sections are synthesized from the user's own directories, so
        # a vocabulary kept here could not be right even in principle.
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(modifiers=[
                {"section": "no-such-section", "category": "no-such-category",
                 "value": 0.5}])
        send_command.assert_called_once()


class SetTargetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    The all-or-nothing resolution phase, the write order and what a category
    resolves to are all checked against a real MPFB in
    ``bridge/test/tests/ddd_mutating/set_targets_test.py``. What is left here is
    the per-entry validation the tool does before any transport is chosen, and
    the fact that a **cached** fragment list leaves nothing on the bridge's
    wire - which is this tool's own claim, since it is the heaviest carrier of
    fragment source in the package.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_targets": fake_bridge.ok_envelope(
                "set_targets", {"found": True, "changes": [], "performed": False}),
        })

    def test_the_tool_sends_the_set_targets_command(self) -> None:
        self.call(modifiers=[{"section": "nose", "category": "nose-scale-depth-decr-incr",
                              "value": 0.4}])

        self.assertEqual(self.bridge.commands()[-1], "set_targets")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["modifiers"][0]["category"], "nose-scale-depth-decr-incr")
        self.assertEqual(params["symmetry"], False)
        self.assertEqual(params["prune"], True)
        self.assertEqual(params["refit"], False)

    def test_the_request_is_the_entries_and_nothing_else(self) -> None:
        # This tool used to carry 26 KB of shared source on a cold call, and
        # the whole of what it sends now is what the caller passed. What the
        # shared modules model is imported by the command, on the far side.
        self.call(targets=[{"shapekey_name": "chin-triangle", "value": 0.5}])

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(set(request), {"command", "params", "protocol_version"})
        self.assertNotIn("target_categories", str(request))

    def test_per_entry_validation_runs_before_a_transport_is_chosen(self) -> None:
        # A misspelled key is otherwise silent, and the two ranges differ: a
        # modifier may be negative because a category can be a pair of
        # opposites, while a raw shape key value cannot.
        with self.assertRaises(ValueError):
            self.call(modifiers=[{"section": "nose", "catagory": "x", "value": 0.1}])
        with self.assertRaises(ValueError):
            self.call(targets=[{"shapekey_name": "chin-triangle", "value": -0.5}])

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "TargetService.load_target() raised.",
                command="set_targets"))

        response = self.call(targets=[{"shapekey_name": "chin-triangle", "value": 0.5}])

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")
