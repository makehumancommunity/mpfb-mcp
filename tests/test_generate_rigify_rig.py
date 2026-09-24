# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_generate_rigify_rig tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the tool wrapper
with ``send_command`` mocked below the seam, and the **bridge path** against
``tests/fake_bridge.py``. ``meta_rig_action`` is one of the two closed
vocabularies this package checks locally, and it earns the exception: MPFB warns
and silently falls back to "hide", on the single argument here whose wrong value
cannot be undone.

What this cannot say is that the generated rig deforms the character the way
Rigify's own does, that a failed generation is not a no-op, or that
``meta_rig_action="delete"`` really leaves ``mpfb_refit_human`` unable to refit.
All three are checked against a real Rigify in
``bridge/test/tests/ddd_mutating/generate_rigify_rig_test.py``, which the FR 032
spike established can run in a Blender with no window.

Run with::

    python -m unittest tests.test_generate_rigify_rig -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import generate_rigify_rig

from tests import fake_bridge



# Distinguishes "the test did not say" from "the test said: nothing is active".
_UNSET = object()


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    generate_rigify_rig.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_generate_rigify_rig"].fn


class ArgumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **kwargs):
        """The command and the parameters that reached the wire."""
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_command.call_args[0]

    def test_the_defaults_are_mpfbs_own(self):
        command, params = self._sent()
        self.assertEqual(command, "generate_rigify_rig")
        self.assertEqual(params, {"name": None, "rig_name": None, "meta_rig_action": "hide"})

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is carried through with its status and message intact and
        # an `error` slug added, which is the seam's one mapping: a caller
        # branches on `error` without having to learn which transport answered.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")

    def test_every_meta_rig_action_mpfb_knows_is_accepted(self):
        for action in ("keep", "hide", "delete"):
            with self.subTest(meta_rig_action=action):
                self.assertEqual(
                    self._sent(meta_rig_action=action)[1],
                    {"name": None, "rig_name": None, "meta_rig_action": action})

    def test_an_unknown_meta_rig_action_is_rejected_locally(self):
        # The one closed vocabulary this package validates on this side of the
        # socket: MPFB warns and silently falls back to "hide", which would make
        # a typo indistinguishable from a choice - on the single argument whose
        # wrong value cannot be undone.
        for bad in ("Hide", "remove", "", None, True, ["hide"]):
            with self.subTest(meta_rig_action=bad):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(meta_rig_action=bad)
                send_command.assert_not_called()

    def test_an_explicitly_empty_name_or_rig_name_is_rejected(self):
        for kwargs in ({"name": ""}, {"name": "  "}, {"rig_name": ""}, {"rig_name": "  "},
                       {"name": 3}, {"rig_name": 3}):
            with self.subTest(**kwargs):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(**kwargs)
                send_command.assert_not_called()


class GenerateRigifyRigOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the four refusals, what a rejected meta rig leaves behind, and ``active_object_after`` - is checked against a real MPFB
    in ``bridge/test/tests/ddd_mutating/generate_rigify_rig_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "generate_rigify_rig": fake_bridge.ok_envelope("generate_rigify_rig", {"found": True, "generated": True, "performed": True}),
        })

    def test_the_tool_sends_the_generate_rigify_rig_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "generate_rigify_rig")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(
            params, {"name": None, "rig_name": None, "meta_rig_action": "hide"})

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call()

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("performed", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        for value in ("Hide", "remove", "", None):
            with self.subTest(meta_rig_action=value):
                with self.assertRaises(ValueError):
                    self.call(meta_rig_action=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="generate_rigify_rig", state="absent"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
