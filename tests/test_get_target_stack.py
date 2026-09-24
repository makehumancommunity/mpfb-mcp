# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_get_target_stack tool: argument validation, and what crosses
the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``. The wrapper's own share is the paging rule and the
bool-not-truthy rule, both of which are enforced here and nowhere else.

What is genuinely hard about this tool is the *reverse* mapping, and it is
asserted where it runs. A shape key carries no metadata at all, so placing
"r-lowerarm-scale-depth-decr" back into its category, side and polarity means
rebuilding MPFB's category table and looking the name up in it - and rolling the
stack up into modifier values means reproducing
``_get_opposed_modifier_value()``, including its rule that the positive target
wins and the negative one is reported negated. That, and the agreement between
this tool's category reading and ``mpfb_symmetrize_targets``', are checked
against a real MPFB in ``bridge/test/tests/ccc_reading/get_target_stack_test.py``.

Run with::

    python -m unittest tests.test_get_target_stack -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from tests import fake_bridge

from mpfbmcp import bridge_connection
from mpfbmcp.tools import get_target_stack





def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_target_stack.register(mcp)
    return mcp._tool_manager._tools["mpfb_get_target_stack"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape checked here, vocabulary deliberately not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_default_call_sends_the_documented_defaults(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        command, params = send_command.call_args[0]
        self.assertEqual(command, "get_target_stack")
        self.assertEqual(params, {
            "name": None, "include_macro": False, "include_expressions": False,
            "name_contains": None, "limit": 200, "offset": 0})

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.rig", include_macro=True, include_expressions=True,
                      name_contains="nose", limit=5, offset=10)
        self.assertEqual(send_command.call_args[0][1], {
            "name": "Human.rig", "include_macro": True, "include_expressions": True,
            "name_contains": "nose", "limit": 5, "offset": 10})

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

    def test_non_string_or_empty_text_arguments_are_rejected_locally(self):
        for argument in ("name", "name_contains"):
            for bad in (1, True, [], object(), "", "   ", "\t"):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_flags_must_be_real_bools(self):
        # Not truthiness: include_macro="false" would otherwise return the macro
        # stack the caller was trying to exclude.
        for argument in ("include_macro", "include_expressions"):
            for bad in ("false", "true", 0, 1, None, []):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_bad_limit_and_offset_are_rejected_locally(self):
        for bad in (True, False, -1, "10", 1.5, None):
            for argument in ("limit", "offset"):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_limit_above_the_ceiling_is_rejected_locally(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(limit=get_target_stack.MAX_LIMIT + 1)
        send_command.assert_not_called()


class GetTargetStackOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the two views, the "basis" exclusion, how a
    category reads - is checked against a real MPFB in
    ``bridge/test/tests/ccc_reading/get_target_stack_test.py``.
    """

    def setUp(self):
        super().setUp()
        self.tool = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_target_stack": fake_bridge.ok_envelope("get_target_stack", {"count": 0}),
        })

    def test_the_tool_sends_the_get_target_stack_command(self):
        self.tool()

        self.assertEqual(self.bridge.commands()[-1], "get_target_stack")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {
            "name": None, "include_macro": False, "include_expressions": False,
            "name_contains": None, "limit": 200, "offset": 0})

    def test_the_two_cached_fragments_do_not_reach_the_bridge(self):
        # Two fragments rather than one, and neither crosses: on the bridge
        # they are modules the command imports.
        self.tool(name="Human", include_macro=True, limit=5)

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(request["params"]["name"], "Human")
        self.assertEqual(request["params"]["include_macro"], True)
        self.assertNotIn("target_categories", str(request))
        self.assertNotIn("modifier_reading", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self):
        for arguments in ({"include_macro": "true"}, {"include_expressions": 1},
                          {"limit": True}, {"limit": -1}, {"name": "  "}):
            with self.subTest(**arguments):
                with self.assertRaises(ValueError):
                    self.tool(**arguments)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self):
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="get_target_stack", state="absent"))

        response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
