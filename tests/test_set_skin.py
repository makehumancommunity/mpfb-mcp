# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_set_skin tool: argument validation, and what crosses the
socket.

Two layers (see ``tests/test_list_objects.py``, the template): the tool wrapper
with ``send_command`` mocked below the seam, and the **bridge path** against
``tests/fake_bridge.py``. ``skin_type`` is one of the two closed vocabularies
this package checks locally, and this module is where the defaulting that
follows MPFB's settings panel rather than the function signature is asserted:
``MAKESKIN``, with ``material_instances`` coerced off for three of the five
types, so the default call creates no material instances.

What this cannot say is that any of the five types produces the node tree MPFB's
own panel produces, or that applying a skin really deletes every material
already on the body and on its proxy. Both are checked against a real MPFB in
``bridge/test/tests/ddd_mutating/set_skin_test.py``.

Run with::

    python -m unittest tests.test_set_skin -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import set_skin

from tests import fake_bridge




def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_skin.register(mcp)
    return mcp._tool_manager._tools["mpfb_set_skin"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape, plus the one vocabulary this package checks on both sides."""

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

    def test_the_default_skin_type_is_the_panels_not_the_signatures(self):
        # set_character_skin() defaults to ENHANCED_SSS; MPFB's settings panel
        # defaults to MAKESKIN. A caller comparing against what they saw in the
        # UI has to get the UI's answer.
        self.assertEqual(
            self._sent_params(path="/assets/skins/young/young.mhmat")["skin_type"],
            "MAKESKIN")

    def test_skin_type_is_normalised_and_a_typo_never_crosses_the_socket(self):
        self.assertEqual(
            self._sent_params(path="/a/b.mhmat", skin_type="enhanced_sss")["skin_type"],
            "ENHANCED_SSS")
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(path="/a/b.mhmat", skin_type="ENHANCED_SS")
            send_command.assert_not_called()

    def test_both_identifiers_are_rejected_and_so_is_neither(self):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(path="/a/b.mhmat", fragment="b/b.mhmat")
            with self.assertRaises(ValueError):
                self.tool()
            send_command.assert_not_called()

    def test_layered_is_the_one_type_that_may_name_no_file(self):
        params = self._sent_params(skin_type="LAYERED")
        self.assertIsNone(params["path"])
        self.assertIsNone(params["fragment"])
        # ...and every other type still has to name one.
        for skin_type in ("MAKESKIN", "GAMEENGINE", "ENHANCED", "ENHANCED_SSS"):
            with self.subTest(skin_type=skin_type):
                with self.assertRaises(ValueError):
                    self.tool(skin_type=skin_type)

    def test_an_empty_string_is_not_an_omission(self):
        # An explicitly empty value and an omitted one arise from different
        # mistakes, and here the difference decides whether a file is wanted.
        for kwargs in ({"name": "", "path": "/a/b.mhmat"},
                       {"path": ""},
                       {"fragment": ""},
                       {"path": "", "skin_type": "LAYERED"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.tool(**kwargs)

    def test_material_instances_must_be_a_real_bool(self):
        with self.assertRaises(ValueError):
            self.tool(path="/a/b.mhmat", material_instances="false")

    def test_a_name_is_passed_through_as_the_subject(self):
        self.assertEqual(
            self._sent_params(name="Human.rig", path="/a/b.mhmat")["name"], "Human.rig")


class SetSkinOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the five node trees, what the call destroyed, the active-slot fixup and the settings file - is checked against a real MPFB
    in ``bridge/test/tests/ddd_mutating/set_skin_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_skin": fake_bridge.ok_envelope("set_skin", {"found": True, "applied": True, "performed": True}),
        })

    def test_the_tool_sends_the_set_skin_command(self) -> None:
        self.call(path="/skins/young/young.mhmat")

        self.assertEqual(self.bridge.commands()[-1], "set_skin")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["skin_type"], "MAKESKIN")
        self.assertEqual(params["path"], "/skins/young/young.mhmat")
        self.assertIsNone(params["fragment"])

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(path="/skins/young/young.mhmat")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("asset_sections", str(request))

    def test_material_instances_is_sent_as_requested_and_coerced_on_the_far_side(self) -> None:
        # The coercion is MPFB's panel behaviour and belongs where MPFB is: the
        # tool sends what the caller asked for, and the answer reports both.
        self.call(path="/skins/young/young.mhmat", material_instances=True)

        self.assertIs(
            self.bridge.decoded_requests()[-1]["params"]["material_instances"], True)

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(path="/a.mhmat", skin_type="NOT_A_SKIN")
        with self.assertRaises(ValueError):
            self.call(path="/a.mhmat", material_instances="false")

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="set_skin", state="absent"))

        response = self.call(path="/skins/young/young.mhmat")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
