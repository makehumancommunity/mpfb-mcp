# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_set_material_settings tool: entry shape, and what crosses
the socket.

Two layers (see ``tests/test_list_objects.py``, the template). Entry *shape* is
checked here: that each list holds objects with exactly their section's keys,
that exactly one of ``value`` and ``color`` is present, that a ``color`` is four
finite non-negative numbers that are not ``bool``s, and that no socket is named
twice. **No socket or group vocabulary is checked here**
(``test_the_socket_and_group_vocabulary_is_not_checked_locally``): those are
MPFB's node trees, read live inside Blender, and answered there as
``resolution_errors``.

What the payload does with a batch - the all-or-nothing resolution, the linked,
kind-mismatch and range refusals, the writes and the shared-material report -
is checked against a real MPFB in
``bridge/test/tests/ddd_mutating/set_material_settings_test.py``, and the
preset round trip in ``bridge/test/tests/eee_composite/``.

Run with::

    python -m unittest tests.test_set_material_settings -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import set_material_settings

from tests import fake_bridge

GREEN = [0.1, 0.4, 0.1, 1.0]


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_material_settings.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_set_material_settings"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Entry *shape* checked here; the socket vocabulary is not."""

    def setUp(self):
        self.tool = _tool_callable()

    def _refused(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError) as raised:
                self.tool(**arguments)
        send_command.assert_not_called()
        return str(raised.exception)

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def test_a_call_naming_nothing_is_legal(self):
        self.assertEqual(self._sent(), {
            "name": None, "eyes": [], "skin": [], "color_adjustments": []})

    def test_entries_are_normalized_before_they_cross_the_socket(self):
        sent = self._sent(
            eyes=[{"socket": "IrisMajorColor", "color": [0, 1, 0, 1]}],
            skin=[{"group": "color", "socket": "SkinOverride", "value": 1}],
            color_adjustments=[{"object_name": "Hair", "socket": "Factor", "value": 0}])
        self.assertEqual(sent["eyes"], [{"socket": "IrisMajorColor",
                                         "color": [0.0, 1.0, 0.0, 1.0]}])
        self.assertEqual(sent["skin"], [{"group": "color", "socket": "SkinOverride",
                                         "value": 1.0}])
        self.assertEqual(sent["color_adjustments"],
                         [{"object_name": "Hair", "socket": "Factor", "value": 0.0}])
        self.assertIsInstance(sent["skin"][0]["value"], float)

    def test_each_list_must_be_a_list_of_objects(self):
        for section in ("eyes", "skin", "color_adjustments"):
            for bad in ("IrisMajorColor", {"socket": "x"}, 1, ["x"]):
                with self.subTest(section=section, value=bad):
                    self._refused(**{section: bad})

    def test_an_unknown_key_is_rejected_locally(self):
        # A misspelled `sokcet` quietly dropped would be an entry with no socket.
        message = self._refused(eyes=[{"sokcet": "PupilSize", "value": 0.3}])
        self.assertIn("sokcet", message)
        # A key that belongs to another section is unknown in this one.
        self._refused(eyes=[{"group": "color", "socket": "SkinColor", "color": GREEN}])
        self._refused(skin=[{"object_name": "Hair", "group": "color",
                             "socket": "SkinColor", "color": GREEN}])

    def test_a_missing_or_empty_address_is_rejected_locally(self):
        self._refused(eyes=[{"value": 0.3}])
        self._refused(eyes=[{"socket": "  ", "value": 0.3}])
        self._refused(skin=[{"socket": "SkinColor", "color": GREEN}])
        self._refused(skin=[{"group": "", "socket": "SkinColor", "color": GREEN}])
        self._refused(color_adjustments=[{"socket": "Factor", "value": 0.5}])
        self._refused(color_adjustments=[{"object_name": 3, "socket": "Factor", "value": 0.5}])

    def test_exactly_one_of_value_and_color(self):
        message = self._refused(eyes=[{"socket": "PupilSize"}])
        self.assertIn("exactly one", message)
        self._refused(eyes=[{"socket": "PupilSize", "value": 0.3, "color": GREEN}])

    def test_a_value_is_a_finite_number_and_not_a_bool(self):
        for bad in (True, False, "0.3", None, [0.3], float("nan"), float("inf")):
            with self.subTest(value=bad):
                self._refused(eyes=[{"socket": "PupilSize", "value": bad}])

    def test_a_color_is_four_finite_numbers(self):
        for bad in ("#00ff00", [0.1, 0.4, 0.1, True], [0.1, "0.4", 0.1, 1.0],
                    [0.1, float("nan"), 0.1, 1.0], (0.1, 0.4, 0.1, 1.0), 0.5):
            with self.subTest(color=bad):
                self._refused(eyes=[{"socket": "IrisMajorColor", "color": bad}])

    def test_three_components_are_refused_saying_alpha_is_required(self):
        message = self._refused(eyes=[{"socket": "IrisMajorColor", "color": [0.1, 0.4, 0.1]}])
        self.assertIn("alpha is required", message)
        self._refused(eyes=[{"socket": "IrisMajorColor", "color": [0.1, 0.4, 0.1, 1.0, 1.0]}])

    def test_a_negative_component_is_refused_and_a_bright_one_is_not(self):
        # Blender stores a negative component as zero and keeps one above 1.0.
        self._refused(eyes=[{"socket": "IrisMajorColor", "color": [-0.1, 0.4, 0.1, 1.0]}])
        sent = self._sent(eyes=[{"socket": "IrisMajorColor", "color": [2.0, 0.4, 0.1, 1.0]}])
        self.assertEqual(sent["eyes"][0]["color"], [2.0, 0.4, 0.1, 1.0])

    def test_a_repeated_socket_is_refused_locally(self):
        self._refused(eyes=[{"socket": "PupilSize", "value": 0.3},
                            {"socket": "PupilSize", "value": 0.4}])
        self._refused(skin=[{"group": "color", "socket": "SkinColor", "color": GREEN},
                            {"group": "color", "socket": "SkinColor", "color": GREEN}])
        self._refused(color_adjustments=[
            {"object_name": "Hair", "socket": "Factor", "value": 0.3},
            {"object_name": "Hair", "socket": "Factor", "value": 0.4}])

    def test_the_same_socket_name_under_different_addresses_is_not_a_repeat(self):
        sent = self._sent(
            skin=[{"group": "body", "socket": "Roughness", "value": 0.3},
                  {"group": "face", "socket": "Roughness", "value": 0.3}],
            color_adjustments=[{"object_name": "Hair", "socket": "Factor", "value": 0.3},
                               {"object_name": "Shirt", "socket": "Factor", "value": 0.3}])
        self.assertEqual(len(sent["skin"]), 2)
        self.assertEqual(len(sent["color_adjustments"]), 2)

    def test_the_socket_and_group_vocabulary_is_not_checked_locally(self):
        # Names MPFB has never used. Whether they exist is answered inside
        # Blender against the live node, as a resolution error.
        sent = self._sent(
            eyes=[{"socket": "NoSuchSocket", "value": 12345.0}],
            skin=[{"group": "nosuchgroup", "socket": "NoSuchSocket", "color": GREEN}])
        self.assertEqual(sent["eyes"][0]["socket"], "NoSuchSocket")
        self.assertEqual(sent["skin"][0]["group"], "nosuchgroup")

    def test_a_batch_above_the_ceiling_is_rejected_locally(self):
        too_many = [{"socket": "S{}".format(index), "value": 0.0}
                    for index in range(set_material_settings.MAX_ENTRIES + 1)]
        self._refused(eyes=too_many)

    def test_the_error_names_the_offending_entry_by_position(self):
        message = self._refused(skin=[
            {"group": "color", "socket": "SkinColor", "color": GREEN},
            {"group": "color", "socket": "SkinOverride", "value": "high"}])
        self.assertIn("skin[1]", message)


class SetMaterialSettingsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_material_settings": fake_bridge.ok_envelope(
                "set_material_settings", {"found": True, "changes": [], "performed": False}),
        })

    def test_the_tool_sends_the_set_material_settings_command(self) -> None:
        self.call(skin=[{"group": "color", "socket": "SkinColor", "color": GREEN}])

        self.assertEqual(self.bridge.commands()[-1], "set_material_settings")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params, {
            "name": None, "eyes": [], "color_adjustments": [],
            "skin": [{"group": "color", "socket": "SkinColor", "color": GREEN}]})

    def test_the_request_is_the_arguments_and_nothing_else(self) -> None:
        self.call()

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(set(request), {"command", "params", "protocol_version"})

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "set_socket_default_values() raised.",
                command="set_material_settings"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")
