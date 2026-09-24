# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_apply_expressions tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template). Entry *shape* is
checked here exhaustively - that ``expressions`` is a list of dicts, each with
exactly ``fragment`` and ``weight``, a weight a real number in 0.0-1.0, and no
fragment twice - and so is ``mode``, one of the narrow vocabularies checked on
this side. Whether a fragment names a real expression file is deliberately
*not* checked here (see ``test_an_unknown_fragment_is_not_rejected_locally``):
it is resolved in Blender, the way the rebuild will resolve it.

What the command does with a resolved batch - the refusal that leaves the stack
byte-identical, merge and replace, removal at 0.0, the pack-absent refusal,
clamping, and the composed units it discards - is checked against a real MPFB
in ``bridge/test/tests/ppp_mutating/apply_expressions_test.py``.

Run with::

    python -m unittest tests.test_apply_expressions -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import apply_expressions

from tests import fake_bridge


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    apply_expressions.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_apply_expressions"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Entry shape and ``mode`` checked here; the fragment vocabulary is not."""

    def setUp(self):
        self.tool = _tool_callable()

    def _refused(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError) as raised:
                self.tool(**arguments)
        send_command.assert_not_called()
        return str(raised.exception)

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        self.assertEqual(send_command.call_args[0][0], "apply_expressions")
        return send_command.call_args[0][1]

    def test_a_call_with_no_arguments_is_legal(self):
        self.assertEqual(self._sent(), {
            "name": None, "expressions": [], "mode": "merge", "refit": True})

    def test_replace_with_an_empty_list_is_legal_and_is_how_everything_comes_off(self):
        self.assertEqual(self._sent(expressions=[], mode="replace")["expressions"], [])

    def test_entries_are_normalized_before_they_cross_the_socket(self):
        self.assertEqual(
            self._sent(expressions=[{"fragment": "Wink.json", "weight": 1}])["expressions"],
            [{"fragment": "Wink.json", "weight": 1.0}])

    def test_a_weight_of_zero_is_legal_because_it_removes_a_row(self):
        self.assertEqual(
            self._sent(expressions=[{"fragment": "Wink.json", "weight": 0}])["expressions"],
            [{"fragment": "Wink.json", "weight": 0.0}])

    def test_mode_is_checked_here_against_its_two_values(self):
        for bad in ("Merge", "append", "", None, 1, True):
            with self.subTest(mode=bad):
                self._refused(mode=bad)
        for good in ("merge", "replace"):
            with self.subTest(mode=good):
                self.assertEqual(self._sent(mode=good)["mode"], good)

    def test_refit_must_be_a_real_bool(self):
        for bad in ("false", "true", 0, 1, None):
            with self.subTest(value=bad):
                self._refused(refit=bad)

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], object(), "", "   "):
            with self.subTest(value=bad):
                self._refused(name=bad)

    def test_expressions_must_be_a_list_of_objects(self):
        for bad in ("Wink.json", {"fragment": "Wink.json"}, 3, [1], ["x"], [None]):
            with self.subTest(value=bad):
                self._refused(expressions=bad)

    def test_an_unknown_key_is_rejected_and_named(self):
        message = self._refused(expressions=[{"fragmnet": "Wink.json", "weight": 0.5}])
        self.assertIn("fragmnet", message)

    def test_a_missing_key_is_rejected(self):
        self._refused(expressions=[{"fragment": "Wink.json"}])
        self._refused(expressions=[{"weight": 0.5}])

    def test_a_weight_must_be_a_number_in_zero_to_one(self):
        for bad in (-0.1, 1.5, True, False, "0.5", None, [0.5]):
            with self.subTest(value=bad):
                self._refused(expressions=[{"fragment": "Wink.json", "weight": bad}])

    def test_an_empty_fragment_is_rejected(self):
        for bad in ("", "   ", None, 3):
            with self.subTest(value=bad):
                self._refused(expressions=[{"fragment": bad, "weight": 0.5}])

    def test_a_repeated_fragment_is_rejected_and_the_entry_is_named(self):
        message = self._refused(expressions=[
            {"fragment": "Wink.json", "weight": 0.5},
            {"fragment": "Wink.json", "weight": 0.2}])
        self.assertIn("expressions[1]", message)

    def test_a_batch_above_the_ceiling_is_rejected(self):
        self._refused(expressions=[
            {"fragment": "e{}.json".format(index), "weight": 0.1}
            for index in range(apply_expressions.MAX_ENTRIES + 1)])

    def test_an_unknown_fragment_is_not_rejected_locally(self):
        # Whether a fragment resolves is answered in Blender, by the same
        # find_asset_absolute_path the rebuild will use - not by a copy here.
        self.assertEqual(
            self._sent(expressions=[{"fragment": "no-such.json", "weight": 0.5}])["expressions"],
            [{"fragment": "no-such.json", "weight": 0.5}])


class ApplyExpressionsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "apply_expressions": fake_bridge.ok_envelope(
                "apply_expressions", {"found": True, "ready": True, "performed": True}),
        })

    def test_the_tool_sends_the_apply_expressions_command(self) -> None:
        self.call(expressions=[{"fragment": "Wink.json", "weight": 0.4}], mode="replace")

        self.assertEqual(self.bridge.commands()[-1], "apply_expressions")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {
            "name": None, "expressions": [{"fragment": "Wink.json", "weight": 0.4}],
            "mode": "replace", "refit": True})

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(mode="append")

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")
