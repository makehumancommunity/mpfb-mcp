# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_create_human``, in two layers (see ``tests/test_list_objects.py``, the
template).

1. **The wrapper**, with ``send_command`` mocked below the seam: the eleven
   sliders' 0.0-1.0 rule, which is enforced here and nowhere else, and what
   goes on the wire as parameters.
2. **The bridge path**, against ``tests/fake_bridge.py``. Thin, and it carries
   the claim this tool was the first *mutating* one to make: a tool that
   changes a .blend sends exactly its already-validated arguments, and a
   locally invalid call reaches nothing.

What the character MPFB actually builds looks like is checked against a real
MPFB in ``bridge/test/tests/ddd_mutating/create_human_test.py``, which is where
it could never be checked from this side.

Run with::

    python -m unittest tests.test_create_human -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import create_human

from tests import fake_bridge




def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    create_human.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_create_human"]  # noqa: SLF001
    return tool.fn


class CreateHumanToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_create_human = _register_and_get_tool()

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_custom_values_are_passed_through(self, mock_send_command: mock.Mock) -> None:
        mock_send_command.return_value = {"status": "ok", "result": {}}

        self.mpfb_create_human(gender=1.0, age=0.2, scale=0.05)

        (command, params), _kwargs = mock_send_command.call_args
        params = params
        self.assertEqual(params["scale"], 0.05)
        self.assertEqual(params["macro_detail_dict"]["gender"], 1.0)
        self.assertEqual(params["macro_detail_dict"]["age"], 0.2)

    def test_out_of_range_macro_value_is_rejected_locally(self) -> None:
        # Should raise before ever touching the network.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            with self.assertRaises(ValueError):
                self.mpfb_create_human(gender=1.5)
            mock_send_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class CreateHumanOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *does* - that a basemesh appears, that it carries the
    phenotype it was given, that ``performed`` is true because creation either
    returns an object or raises - is checked against a real MPFB in
    ``bridge/test/tests/ddd_mutating/create_human_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _register_and_get_tool()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "create_human": fake_bridge.ok_envelope(
                "create_human", {"object_name": "Human", "performed": True}),
        })

    def test_the_tool_sends_the_create_human_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "create_human")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["scale"], 0.1)
        self.assertEqual(params["macro_detail_dict"]["gender"], 0.5)
        self.assertEqual(params["macro_detail_dict"]["race"],
                         {"asian": 0.33, "caucasian": 0.33, "african": 0.33})

    def test_the_eleven_sliders_arrive_as_mpfbs_nested_dict(self) -> None:
        # The tool's flat arguments are MPFB's nested ones by the time they
        # leave: the bridge receives exactly what the tool validated, and
        # have bound as PARAMS, unreshaped.
        self.call(gender=1.0, age=0.25, race_african=0.9)

        macro = self.bridge.decoded_requests()[-1]["params"]["macro_detail_dict"]
        self.assertEqual(macro["gender"], 1.0)
        self.assertEqual(macro["age"], 0.25)
        self.assertEqual(macro["race"]["african"], 0.9)

    def test_the_shared_fragment_does_not_reach_the_bridge(self) -> None:
        # `performed.py` is a property of how a *program* is assembled; on this
        # side of the seam the command imports the module that replaced it.
        self.call()

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("performed", str(request["params"]))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        # The 0.0-1.0 rule lives in the tool, because MPFB's macro properties
        # carry a default but no min/max and nothing on the far side clamps.
        with self.assertRaises(ValueError):
            self.call(gender=1.5)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="create_human", state="absent"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
