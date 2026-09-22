# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_asset_materials tool: the catalogue that is not a
section, its cached snapshot, and what makes an empty answer explainable.

Migrated by FR 031, so three layers rather than two (see
``tests/test_list_objects.py``, the template). **The payload layer is frozen**,
and the questions it asks are now put to a real MPFB in
``bridge/test/tests/mmm_list_asset_materials_test.py`` - including the one this
tool is most defined by, that MPFB's scan is cached per asset and nothing
invalidates it.

The share of this module that goes with the payload: 213 of its 354 lines, 60%.

Formerly two layers: the tool wrapper with send_command mocked,
then the assembled source executed against the stub services and a real
temporary asset library (tests/blender_stubs.py's MeshAssetTestCase). Real,
because the scan this wraps globs `*.mhmat` off disk and matches on a path
segment - mocking the filesystem away would leave nothing under test.

What is *not* under test here, and cannot be: that MPFB's own scan finds the
same files on a real install, or that the cache behaves as documented across a
Blender session rather than across a stub. Both are live checks (see
feature-requests/done/011-skin-and-materials).

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
    """Shape only, and there is only one argument to have a shape."""

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
        self.assertEqual(params, {"name": "Human.fedora"})

    def test_name_is_required(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(TypeError):
                self.tool()
            for bad in ("", "   ", None, 7):
                with self.subTest(name=bad):
                    with self.assertRaises((ValueError, TypeError)):
                        self.tool(name=bad)
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
                         {"name": "Human.fedora"})

    def test_local_validation_runs_before_a_transport_is_chosen(self):
        with self.assertRaises(TypeError):
            self.tool()
        for bad in ("", "   ", None, 7):
            with self.subTest(name=bad):
                with self.assertRaises((ValueError, TypeError)):
                    self.tool(name=bad)

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
