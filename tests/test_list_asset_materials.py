# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_list_asset_materials tool: argument validation, and what
crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``.

The questions this tool is defined by are put to a real MPFB in
``bridge/test/tests/mmm_list_asset_materials_test.py`` - including the one that
defines it most, that MPFB's scan is cached per asset and nothing invalidates
it, so this tool's answer is stale by design and says so.

Run with::

    python -m unittest tests.test_list_asset_materials -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from tests import fake_bridge

from mpfbmcp.tools import list_asset_materials





def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_asset_materials.register(mcp)
    # pylint: disable=protected-access
    return mcp._tool_manager._tools["mpfb_list_asset_materials"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Shape only: the name, and now refresh alongside it."""

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **kwargs):
        """The command and the parameters that reached the wire."""
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_command.call_args[0]

    def test_the_name_crosses_the_socket(self):
        command, params = self._sent(name="Human.fedora")
        self.assertEqual(command, "list_asset_materials")
        self.assertEqual(params, {"name": "Human.fedora", "refresh": False})

    def test_refresh_true_is_carried_across(self):
        command, params = self._sent(name="Human.fedora", refresh=True)
        self.assertEqual(command, "list_asset_materials")
        self.assertEqual(params, {"name": "Human.fedora", "refresh": True})

    def test_name_is_required(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(TypeError):
                self.tool()
            for bad in ("", "   ", None, 7):
                with self.subTest(name=bad):
                    with self.assertRaises((ValueError, TypeError)):
                        self.tool(name=bad)
            send_command.assert_not_called()

    def test_non_bool_refresh_is_rejected_locally(self):
        # A truthy int or the string "false" is how a caller signals a bool it
        # failed to build; accepting either would silently clear a cache every
        # other asset relies on.
        for bad in (1, 0, "true", "false", None, [], object()):
            with self.subTest(refresh=bad):
                with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(name="Human.fedora", refresh=bad)
                send_command.assert_not_called()


class ListAssetMaterialsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the scan, its staleness, the default
    material and why it might be unknown - is checked against a real MPFB in
    ``bridge/test/tests/mmm_list_asset_materials_test.py``.
    """

    def setUp(self):
        super().setUp()
        self.tool = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_asset_materials": fake_bridge.ok_envelope("list_asset_materials", {"count": 0}),
        })

    def test_the_tool_sends_the_list_asset_materials_command(self):
        self.tool(name="Human.fedora")

        self.assertEqual(self.bridge.commands()[-1], "list_asset_materials")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human.fedora", "refresh": False})

    def test_refresh_reaches_the_bridge(self):
        self.tool(name="Human.fedora", refresh=True)

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"],
                         {"name": "Human.fedora", "refresh": True})

    def test_local_validation_runs_before_a_transport_is_chosen(self):
        with self.assertRaises(TypeError):
            self.tool()
        for bad in ("", "   ", None, 7):
            with self.subTest(name=bad):
                with self.assertRaises((ValueError, TypeError)):
                    self.tool(name=bad)
        for bad in (1, 0, "true", "false", None, [], object()):
            with self.subTest(refresh=bad):
                with self.assertRaises(ValueError):
                    self.tool(name="Human.fedora", refresh=bad)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self):
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="list_asset_materials", state="absent"))

        response = self.tool(name="Human.fedora")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
