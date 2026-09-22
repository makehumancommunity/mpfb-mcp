# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_add_asset tool: argument validation, and what crosses the
socket.

Two layers (see ``tests/test_list_objects.py``, the template): the tool wrapper
with ``send_command`` mocked below the seam, and the **bridge path** against
``tests/fake_bridge.py``. The first carries the weight here, because
``asset_type`` is required and exactly one of ``path``/``fragment`` is allowed,
and both are refused before anything is sent.

What this cannot say is that an asset equipped through this tool is
indistinguishable from the same asset equipped through MPFB's own asset library
panel - same fit, same delete group, same material. That is checked against a
real MPFB in ``bridge/test/tests/ppp_mutating/add_asset_test.py``, over an
asset library that test builds.

Run with::

    python -m unittest tests.test_add_asset -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import add_asset

from tests import fake_bridge




def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    add_asset.register(mcp)
    return mcp._tool_manager._tools["mpfb_add_asset"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape only. Which asset types exist is MPFB's own table, read in Blender."""

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **kwargs):
        """The command and the parameters that reached the wire."""
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_command.call_args[0]

    def _sent_params(self, **kwargs):
        return self._sent(**kwargs)[1]

    def test_asset_type_is_required_and_is_rejected_before_any_code_is_generated(self):
        # The whole reason it is required: MPFB's own default of "Clothes" is
        # wrong for six of the eight types and wrong in a way nothing reports.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(TypeError):
                self.tool(path="/assets/fedora/fedora.mhclo")
            with self.assertRaises(ValueError):
                self.tool(asset_type="   ", path="/assets/fedora/fedora.mhclo")
            with self.assertRaises(ValueError):
                self.tool(asset_type=None, path="/assets/fedora/fedora.mhclo")
        send_command.assert_not_called()

    def test_both_path_and_fragment_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.tool(asset_type="Clothes", path="/assets/fedora/fedora.mhclo",
                      fragment="fedora/fedora.mhclo")
        self.assertIn("not both", str(raised.exception))

    def test_neither_path_nor_fragment_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.tool(asset_type="Clothes")
        self.assertIn("Give either path or fragment", str(raised.exception))

    def test_an_explicitly_empty_identifier_is_not_treated_as_an_omission(self):
        # "" and omitted arise from different mistakes, and quietly reading the
        # first as the second would turn "I built the path wrong" into "neither
        # was given".
        with self.assertRaises(ValueError):
            self.tool(asset_type="Clothes", path="  ")

    def test_subdiv_levels_rejects_a_bool_and_a_negative(self):
        # bool is a subclass of int, so subdiv_levels=True would silently mean 1.
        with self.assertRaises(ValueError):
            self.tool(asset_type="Clothes", path="/a.mhclo", subdiv_levels=True)
        with self.assertRaises(ValueError):
            self.tool(asset_type="Clothes", path="/a.mhclo", subdiv_levels=-1)

    def test_the_four_flags_must_be_real_bools(self):
        for flag in ("set_up_rigging", "interpolate_weights", "import_subrig",
                     "import_weights"):
            with self.subTest(flag=flag):
                with self.assertRaises(ValueError):
                    self.tool(asset_type="Clothes", path="/a.mhclo", **{flag: "false"})

    def test_the_material_type_vocabulary_is_not_checked_here(self):
        # Deliberately: which material types are valid for which asset type is
        # MPFB's own table plus its own eye special case, and a list kept here
        # would drift from it.
        params = self._sent_params(
            asset_type="Clothes", path="/a.mhclo", material_type="NOT_A_MATERIAL")
        self.assertEqual(params["material_type"], "NOT_A_MATERIAL")

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is carried through with its status and message intact and
        # an `error` slug added, which is the seam's one mapping: a caller
        # branches on `error` without having to learn which transport answered.
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool(asset_type="Clothes", path="/a.mhclo")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")


class AddAssetOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the type vocabulary, the delete group, the proxy extras and every warning - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/add_asset_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "add_asset": fake_bridge.ok_envelope("add_asset", {"found": True, "added": True, "performed": True}),
        })

    def test_the_tool_sends_the_add_asset_command(self) -> None:
        self.call(asset_type="Clothes", path="/a.mhclo")

        self.assertEqual(self.bridge.commands()[-1], "add_asset")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["asset_type"], "Clothes")
        self.assertEqual(params["path"], "/a.mhclo")
        self.assertIsNone(params["fragment"])
        self.assertEqual(params["subdiv_levels"], 1)

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(asset_type="Clothes", path="/a.mhclo")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("asset_sections", str(request))

    def test_exactly_one_of_path_and_fragment_is_enforced_here(self) -> None:
        # Both or neither is a mistake the caller can fix without looking at the
        # scene, and it is the same refusal on either transport.
        with self.assertRaises(ValueError):
            self.call(asset_type="Clothes")
        with self.assertRaises(ValueError):
            self.call(asset_type="Clothes", path="/a.mhclo", fragment="pack/a.mhclo")

        self.assertEqual(self.bridge.requests, [])

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(asset_type="", path="/a.mhclo")
        with self.assertRaises(ValueError):
            self.call(asset_type="Clothes", path="/a.mhclo", subdiv_levels=True)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="add_asset", state="absent"))

        response = self.call(asset_type="Clothes", path="/a.mhclo")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
