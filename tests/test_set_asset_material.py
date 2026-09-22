# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_set_asset_material tool: the reimplemented UI operator, its
three refusals, and the quirks reproduced rather than tidied up.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_command`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source executed
against the stub services and a real temporary asset library
(tests/blender_stubs.py's MeshAssetTestCase). That third layer is **frozen**: it
stays while the payload stays, because the payload is half of what FR 032's live
comparison compares.

The library is real because this payload reads the asset's MHCLO for its
material line and resolves a fragment by walking the asset roots. The dressed
character is built by running mpfb_add_asset's own payload rather than by hand,
for the same reason test_remove_asset.py does it: the material this tool
replaces is exactly the one that tool built.

What layer 3 cannot say is that the material this produces is the one MPFB's own
alternative-material panel produces. That is a node tree, and no stub builds
one. That is now checked against a real MPFB in
``bridge/test/tests/ppp_mutating/set_asset_material_test.py``.

Run with::

    python -m unittest tests.test_set_asset_material -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import set_asset_material

from tests import fake_bridge




def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_asset_material.register(mcp)
    # pylint: disable=protected-access
    return mcp._tool_manager._tools["mpfb_set_asset_material"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Shape, plus the two mutual exclusions shape can settle."""

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

    def test_the_arguments_cross_the_socket(self):
        command, params = self._sent(name="Human.fedora", path="/assets/fedora/red.mhmat")
        self.assertEqual(command, "set_asset_material")
        self.assertEqual(
            self._sent_params(name="Human.fedora", path="/assets/fedora/red.mhmat"),
            {"name": "Human.fedora", "path": "/assets/fedora/red.mhmat",
             "fragment": None, "restore_default": False})

    def test_name_is_required_and_has_no_active_object_fallback(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(TypeError):
                self.tool(path="/a/b.mhmat")
            for bad in ("", "   ", None, 7):
                with self.subTest(name=bad):
                    with self.assertRaises((ValueError, TypeError)):
                        self.tool(name=bad, path="/a/b.mhmat")
            send_command.assert_not_called()

    def test_both_identifiers_are_rejected_and_so_is_neither(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(name="Human.fedora", path="/a/b.mhmat", fragment="b/b.mhmat")
            with self.assertRaises(ValueError):
                self.tool(name="Human.fedora")
            send_command.assert_not_called()

    def test_restore_default_excludes_a_named_material(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(name="Human.fedora", path="/a/b.mhmat", restore_default=True)
            with self.assertRaises(ValueError):
                self.tool(name="Human.fedora", fragment="b/b.mhmat", restore_default=True)
            send_command.assert_not_called()

    def test_restore_default_alone_is_a_complete_request(self):
        self.assertEqual(
            self._sent_params(name="Human.fedora", restore_default=True),
            {"name": "Human.fedora", "path": None, "fragment": None,
             "restore_default": True})

    def test_restore_default_must_be_a_real_bool(self):
        with self.assertRaises(ValueError):
            self.tool(name="Human.fedora", restore_default="true")


class SetAssetMaterialOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the eleven refusals, the popped slots, the fixed material name and the viewport colour - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/set_asset_material_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_asset_material": fake_bridge.ok_envelope("set_asset_material", {"found": True, "applied": True, "performed": True}),
        })

    def test_the_tool_sends_the_set_asset_material_command(self) -> None:
        self.call(name="Human.fedora", path="/a.mhmat")

        self.assertEqual(self.bridge.commands()[-1], "set_asset_material")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["name"], "Human.fedora")
        self.assertEqual(params["path"], "/a.mhmat")
        self.assertIs(params["restore_default"], False)

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(name="Human.fedora", path="/a.mhmat")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("performed", str(request))

    def test_restore_default_travels_as_a_parameter_like_any_other(self) -> None:
        self.call(name="Human.fedora", restore_default=True)

        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertIs(params["restore_default"], True)
        self.assertIsNone(params["path"])
        self.assertIsNone(params["fragment"])

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(name="Human.fedora")
        with self.assertRaises(ValueError):
            self.call(name="Human.fedora", path="/a.mhmat", restore_default=True)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="set_asset_material", state="absent"))

        response = self.call(name="Human.fedora", path="/a.mhmat")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
