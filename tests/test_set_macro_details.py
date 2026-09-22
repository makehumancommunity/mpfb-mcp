# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_set_macro_details``, in two layers (see ``tests/test_list_objects.py``,
the template).

1. **The wrapper**, with ``send_command`` mocked below the seam: the 0.0-1.0
   rule, which is enforced here and nowhere else because MPFB's macro
   properties carry a default but no ``min``/``max``, and the rule that an
   unnamed slider is left alone rather than set to its default.
2. **The bridge path**, against ``tests/fake_bridge.py``.

That every named property is written before anything is recalculated - once,
not once per slider - and what MPFB does with an out-of-range value it is handed
anyway, are checked against a real MPFB in
``bridge/test/tests/ppp_mutating/set_macro_details_test.py``.

Run with::

    python -m unittest tests.test_set_macro_details -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import set_macro_details

from tests import fake_bridge




def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    set_macro_details.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_set_macro_details"]  # noqa: SLF001
    return tool.fn


class SetMacroDetailsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_set_macro_details = _register_and_get_tool()

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_only_named_sliders_are_sent(self, mock_send_command: mock.Mock) -> None:
        # The distinction a nested macro-detail dict could not express without a
        # sentinel, and the reason the arguments are flat.
        mock_send_command.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details(name="Human", age=0.75)

        (command, params), _kwargs = mock_send_command.call_args
        params = params
        self.assertEqual(params["name"], "Human")
        self.assertEqual(params["changes"], [
            {"argument": "age", "property": "age", "value": 0.75}])

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_race_arguments_map_onto_mpfbs_property_names(
            self, mock_send_command: mock.Mock) -> None:
        # The arguments carry the prefix that groups them, matching
        # mpfb_create_human; MPFB stores them without it.
        mock_send_command.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details(race_asian=1.0, race_african=0.0)

        (command, params), _kwargs = mock_send_command.call_args
        self.assertEqual(params["changes"], [
            {"argument": "race_asian", "property": "asian", "value": 1.0},
            {"argument": "race_african", "property": "african", "value": 0.0},
        ])

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_zero_is_a_value_and_not_an_omission(self, mock_send_command: mock.Mock) -> None:
        mock_send_command.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details(gender=0.0)

        (command, params), _kwargs = mock_send_command.call_args
        self.assertEqual(params["changes"], [
            {"argument": "gender", "property": "gender", "value": 0.0}])

    @mock.patch("mpfbmcp.bridge_connection.send_command")
    def test_integers_are_accepted_and_coerced(self, mock_send_command: mock.Mock) -> None:
        mock_send_command.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details(gender=1)

        (command, params), _kwargs = mock_send_command.call_args
        value = params["changes"][0]["value"]
        self.assertIsInstance(value, float)
        self.assertEqual(value, 1.0)

    def test_out_of_range_sliders_are_rejected_locally(self) -> None:
        # MPFB's own properties are unclamped - the JSON definitions carry a
        # default but no min/max - so this check exists here or nowhere.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for value in (-0.1, 1.1, 5.0, -1):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(gender=value)
            mock_send_command.assert_not_called()

    def test_non_numeric_sliders_are_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for value in ("0.5", True, False, [0.5], object()):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(gender=value)
            mock_send_command.assert_not_called()

    def test_non_bool_flags_are_rejected_locally(self) -> None:
        # Not truthiness: refit="false" would otherwise pay for a full refit.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for value in ("false", 0, 1, None):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(refit=value)
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(prune=value)
            mock_send_command.assert_not_called()

    def test_blank_and_non_string_names_are_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.bridge_connection.send_command") as mock_send_command:
            for bad in ("", "   ", 1, ["Human"]):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(name=bad)
            mock_send_command.assert_not_called()

    def test_the_error_names_the_argument_the_caller_used(self) -> None:
        # "asian must be between..." would name something the caller cannot pass.
        with self.assertRaises(ValueError) as raised:
            self.mpfb_set_macro_details(race_caucasian=2.0)

        self.assertIn("race_caucasian", str(raised.exception))


class SetMacroDetailsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *does* - that a written property moves the mesh, that
    the recalculation happens once, that an omitted slider is untouched - is
    checked against a real MPFB in
    ``bridge/test/tests/ppp_mutating/set_macro_details_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _register_and_get_tool()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_macro_details": fake_bridge.ok_envelope(
                "set_macro_details", {"found": True, "changed": [], "performed": False}),
        })

    def test_the_tool_sends_the_set_macro_details_command(self) -> None:
        self.call(gender=1.0)

        self.assertEqual(self.bridge.commands()[-1], "set_macro_details")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["name"], None)
        self.assertEqual(params["prune"], True)
        self.assertEqual(params["refit"], False)

    def test_only_the_named_sliders_reach_the_bridge(self) -> None:
        # The claim the whole tool turns on: an omitted slider is left alone
        # rather than sent at its default, and that is true on either transport
        # because the list is built before a transport is chosen.
        self.call(age=0.25, race_african=0.9)

        changes = self.bridge.decoded_requests()[-1]["params"]["changes"]
        self.assertEqual(
            sorted(entry["property"] for entry in changes), ["african", "age"])
        self.assertEqual(sorted(entry["argument"] for entry in changes),
                         ["age", "race_african"])

    def test_neither_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(gender=0.5)

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("refit_blocker", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(gender=1.5)
        with self.assertRaises(ValueError):
            self.call(prune="false")

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="set_macro_details", state="absent"))

        response = self.call(gender=0.5)

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
