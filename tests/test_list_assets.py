# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_assets tool: argument validation, and the generated
code's filtering, paging and pack attribution over MPFB's asset cache.

Migrated by FR 031, so three layers rather than two (see
``tests/test_list_objects.py``, the template): the wrapper with ``send_command``
mocked on the seam, the bridge path against ``tests/fake_bridge.py``, and the
payload against the stubs. **The payload layer is frozen.** What keeps the
bridge half honest is ``tests/test_fragment_drift.py``, which compares
``asset_sections.py`` against ``bridge/mpfb_bridge/shared/asset_sections.py``
on every run, and ``bridge/test/tests/lll_list_assets_test.py``, which puts the
questions below to a real MPFB over an asset library the test builds.

The share of this module that goes with the payload: 325 of its 574 lines, 57%.

Formerly two layers, as in tests/test_get_status.py: the tool wrapper with send_command
mocked, then the assembled source executed against the stub services in
tests/blender_stubs.py. Unlike tests/test_list_rigs.py there is no temporary
directory here, because this payload never touches the filesystem - it asks
AssetService, and what needs reproducing is that service's behavior rather than
a directory layout.

The stub library deliberately carries the awkward cases a real install has, each
of which is a branch the payload exists to get right: an asset claimed by two
packs, an asset claimed by none, a pack listing an asset that is not installed,
two assets whose labels collide, and an asset sitting directly in the asset root
rather than in a directory of its own.

Run with::

    python -m unittest tests.test_list_assets -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from tests import fake_bridge

from mpfbmcp.tools import list_assets




# One tree, standing in for two data roots. The second root holds a single
# clothes asset, so that a root is genuinely per-subdir rather than global.
_USER_CLOTHES = "/data/user/clothes"
_SECOND_CLOTHES = "/data/second/clothes"
_USER_HAIR = "/data/user/hair"
_USER_SKINS = "/data/user/skins"
_USER_PROXIES = "/data/user/proxymeshes"


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_assets.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_assets"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Everything rejected here would otherwise round-trip to Blender to fail."""

    def setUp(self):
        self.tool = _tool_callable()

    def _sent_params(self, **kwargs):
        """The parameters that reached the wire."""
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_command.call_args[0][1]

    def test_default_call_filters_nothing_and_pages_from_the_start(self):
        self.assertEqual(self._sent_params(), {
            "asset_subdir": None,
            "name_contains": None,
            "pack": None,
            "limit": 200,
            "offset": 0,
            "refresh": False,
        })

    def test_arguments_are_carried_across_verbatim(self):
        params = self._sent_params(
            asset_subdir="clothes", name_contains="fedora", pack="hair03",
            limit=10, offset=20, refresh=True)

        self.assertEqual(params, {
            "asset_subdir": "clothes",
            "name_contains": "fedora",
            "pack": "hair03",
            "limit": 10,
            "offset": 20,
            "refresh": True,
        })

    def test_non_string_filters_are_rejected_locally(self):
        for argument in ("asset_subdir", "name_contains", "pack"):
            for bad in (1, True, [], object()):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_empty_filters_are_rejected_rather_than_treated_as_omitted(self):
        # An explicitly empty value and an omitted one come from different
        # mistakes, and an empty substring filter would match everything.
        for argument in ("asset_subdir", "name_contains", "pack"):
            for bad in ("", "   ", "\t"):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_bad_limits_and_offsets_are_rejected_locally(self):
        bad_calls = (
            {"limit": -1},
            {"limit": list_assets.MAX_LIMIT + 1},
            {"limit": 1.5},
            {"limit": "10"},
            # bool is a subclass of int, so limit=True would silently page one
            # entry at a time rather than fail.
            {"limit": True},
            {"offset": -1},
            {"offset": 2.5},
            {"offset": False},
        )
        for kwargs in bad_calls:
            with self.subTest(**kwargs):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(**kwargs)
                send_command.assert_not_called()

    def test_the_maximum_limit_itself_is_accepted(self):
        self.assertEqual(self._sent_params(limit=list_assets.MAX_LIMIT)["limit"],
                         list_assets.MAX_LIMIT)

    def test_non_bool_refresh_is_rejected_locally(self):
        for bad in (1, 0, "true", "false", None, []):
            with self.subTest(refresh=bad):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(refresh=bad)
                send_command.assert_not_called()

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")

class ListAssetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the section table, the cap, the paging
    order, the pack attribution - is checked against a real MPFB in
    ``bridge/test/tests/lll_list_assets_test.py``.
    """

    def setUp(self):
        super().setUp()
        self.tool = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_assets": fake_bridge.ok_envelope("list_assets", {"count": 0}),
        })

    def test_the_tool_sends_the_list_assets_command_with_every_parameter(self):
        self.tool()

        self.assertEqual(self.bridge.commands()[-1], "list_assets")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {
            "asset_subdir": None, "name_contains": None, "pack": None,
            "limit": 200, "offset": 0, "refresh": False})

    def test_arguments_cross_the_wire_verbatim(self):
        self.tool(asset_subdir="clothes", name_contains="fedora", pack="system",
                  limit=5, offset=10, refresh=True)

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(request["params"], {
            "asset_subdir": "clothes", "name_contains": "fedora", "pack": "system",
            "limit": 5, "offset": 10, "refresh": True})
        # asset_sections.py is a property of how a program is assembled; on the
        # bridge it is a module the command imports.
        self.assertNotIn("asset_sections", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self):
        for arguments in ({"limit": True}, {"limit": -1}, {"offset": True},
                          {"limit": 1001}, {"refresh": "false"}, {"asset_subdir": "  "}):
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
                command="list_assets", state="absent"))

        response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
