# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_refit_human``, in two layers (see ``tests/test_list_objects.py``, the
template).

1. **The wrapper**, with ``send_command`` mocked below the seam: argument
   validation, and what goes on the wire.
2. **The bridge path**, against ``tests/fake_bridge.py``.

What this tool adds over ``HumanService.refit()`` is the reporting around the
call: a missing basemesh comes back as an answer rather than the ``ValueError``
refit() raises, and a generated Rigify rig with no meta rig is reported rather
than passed off as a successful refit. That, and whether a refit visibly puts
clothes back on a deformed body, are checked against a real MPFB in
``bridge/test/tests/ddd_mutating/refit_human_test.py``, which builds a
character, equips a garment from a redirected data root, deforms the body and
refits it.

Run with::

    python -m unittest tests.test_refit_human -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import refit_human

from tests import fake_bridge




def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    refit_human.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_refit_human"]  # noqa: SLF001
    return tool.fn


class RefitHumanToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_refit_human = _register_and_get_tool()

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_name_is_passed_through_verbatim(self, mock_send_command: mock.Mock) -> None:
        mock_send_command.return_value = {"status": "ok", "result": {"found": True}}

        self.mpfb_refit_human("Human.rig")

        (command, params), _kwargs = mock_send_command.call_args
        self.assertEqual(params, {"name": "Human.rig"})

    def test_blank_and_non_string_names_are_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for bad in ("", "   ", "\t", 1, True, ["Human"]):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        self.mpfb_refit_human(bad)
            mock_send_command.assert_not_called()


class RefitHumanOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - what was refitted, what a generated Rigify
    rig with no meta rig does to ``refit_performed``, that the caller's
    selection comes back - is checked against a real MPFB in
    ``bridge/test/tests/ddd_mutating/refit_human_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _register_and_get_tool()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "refit_human": fake_bridge.ok_envelope(
                "refit_human", {"found": True, "refit_performed": True, "performed": True}),
        })

    def test_the_tool_sends_the_refit_human_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "refit_human")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": None})

    def test_a_named_subject_is_passed_through_verbatim(self) -> None:
        self.call(name="Human.rigify")

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": "Human.rigify"})

    def test_neither_shared_fragment_reaches_the_bridge(self) -> None:
        # Two fragments rather than one, which is what makes this worth
        # asserting separately from `list_presets`: `shared` is a property of
        # how a program is assembled, and the bridge assembles nothing.
        self.call()

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("refit_blocker", str(request))
        self.assertNotIn("performed", str(request["params"]))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        for value in ("", "   ", 17):
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
                "command_failed", "HumanService.refit() raised.",
                command="refit_human"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")
