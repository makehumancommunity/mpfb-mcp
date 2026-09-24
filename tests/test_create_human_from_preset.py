# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_create_human_from_preset``: the overrides, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the **bridge path** against
``tests/fake_bridge.py``. The wrapper carries most of it, because every
override defaults to ``None`` rather than to MPFB's value - "not mentioned" and
"set to the default" are different requests - and the preset name is held to
the same whitelist ``mpfb_save_preset`` applies, so that a name that can be
written is a name that can be looked up.

What MPFB builds from a preset, and the settings dict it is built from - eight
keys MPFB reads with ``[]``, so a dict missing one raises rather than
degrading - are checked against a real MPFB in
``bridge/test/tests/ddd_mutating/create_human_from_preset_test.py``, which does
the save-and-load round trip there rather than between two stubs.

Run with::

    python -m unittest tests.test_create_human_from_preset -v
"""

from __future__ import annotations

__all__ = ()

import unittest
from unittest import mock

from mpfbmcp.tools import create_human_from_preset

from tests import fake_bridge




class CreateHumanFromPresetToolTests(unittest.TestCase):
    """The wrapper, with ``send_command`` mocked."""

    def setUp(self) -> None:
        class Recorder:
            def tool(self, **_kwargs):
                def decorate(function):
                    self.function = function
                    return function
                return decorate

        self.recorder = Recorder()
        create_human_from_preset.register(self.recorder)
        self.call = self.recorder.function

    def _run(self, **arguments):
        """The parameters that reached the wire for one accepted call."""
        arguments.setdefault("preset_name", "alice")
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args[0][0], "create_human_from_preset")
            return send.call_args[0][1]

    def _refused(self, **arguments):
        arguments.setdefault("preset_name", "alice")
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            with self.assertRaises(ValueError) as raised:
                self.call(**arguments)
            self.assertEqual(send.call_count, 0)
        return str(raised.exception)

    def test_the_name_is_held_to_the_same_rule_as_the_saving_tool(self) -> None:
        # Same whitelist, same module. A name that could be written must be a
        # name that can be looked up, and vice versa.
        for name in ("..", "../escape", "a/b", ".hidden", "", "has space", "x" * 65, 3):
            with self.subTest(name=name):
                self._refused(preset_name=name)

    def test_every_override_defaults_to_null(self) -> None:
        # "Not mentioned" and "set to the default" are different requests, and
        # null is how the command is told which one it got.
        params = self._run()
        for argument in ("override_rig", "override_skin_type", "override_clothes_material_type",
                         "override_eyes_material_type", "load_clothes", "scale",
                         "material_instances_policy"):
            with self.subTest(argument=argument):
                self.assertIsNone(params[argument])

    def test_an_override_reaches_the_command(self) -> None:
        self.assertEqual(self._run(override_rig="NONE")["override_rig"], "NONE")
        self.assertIs(self._run(load_clothes=False)["load_clothes"], False)
        self.assertEqual(self._run(scale=1.0)["scale"], 1.0)
        self.assertEqual(
            self._run(material_instances_policy="NEVER")["material_instances_policy"], "NEVER")

    def test_an_explicitly_empty_override_is_not_an_omission(self) -> None:
        for argument in ("override_rig", "override_skin_type", "override_clothes_material_type",
                         "override_eyes_material_type", "material_instances_policy"):
            with self.subTest(argument=argument):
                self._refused(**{argument: "   "})

    def test_load_clothes_must_be_a_real_bool(self) -> None:
        # "false" is a true value, and would load the garments it asked to skip.
        for value in ("false", 1, 0, "no"):
            with self.subTest(load_clothes=value):
                self._refused(load_clothes=value)

    def test_scale_is_range_checked_rather_than_vocabulary_checked(self) -> None:
        # An ordinary "validate structured input" case: any positive number is
        # accepted and MPFB's own three are named in the message.
        for value in (0.1, 1.0, 10.0, 2):
            with self.subTest(scale=value):
                self._run(scale=value)
        for value in (0.0, -1.0, "0.1", True):
            with self.subTest(scale=value):
                self._refused(scale=value)


class CreateHumanFromPresetOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the settings dict, the unresolved assets, and what a mid-way failure left behind - is checked against a real MPFB
    in ``bridge/test/tests/ddd_mutating/create_human_from_preset_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        class Recorder:
            def tool(self, **_kwargs):
                def decorate(function):
                    self.function = function
                    return function
                return decorate

        recorder = Recorder()
        create_human_from_preset.register(recorder)
        self.call = recorder.function
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "create_human_from_preset": fake_bridge.ok_envelope("create_human_from_preset", {"found": True, "created": True, "performed": True}),
        })

    def test_the_tool_sends_the_create_human_from_preset_command(self) -> None:
        self.call(preset_name="alice")

        self.assertEqual(self.bridge.commands()[-1], "create_human_from_preset")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["preset_name"], "alice")
        # Every override defaults to null, which is "use what the preset says"
        # rather than a value - and that has to survive the transport.
        for key in ("override_rig", "override_skin_type", "override_clothes_material_type",
                    "override_eyes_material_type", "load_clothes", "scale",
                    "material_instances_policy"):
            self.assertIsNone(params[key], "{} should default to null".format(key))

    def test_the_shared_fragment_does_not_reach_the_bridge(self) -> None:
        self.call(preset_name="alice")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("preset_files", str(request))

    def test_the_name_rule_is_the_same_rule_the_saving_tool_uses(self) -> None:
        # If these two ever disagreed, a preset could be written under a name
        # that cannot be loaded back - which is the worst shape this pair could
        # take, and why the rule lives in one module.
        for name in ("../escape", "with space", "", "a/b"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.call(preset_name=name)

        self.assertEqual(self.bridge.requests, [])

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(preset_name="alice", load_clothes="false")

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="create_human_from_preset", state="absent"))

        response = self.call(preset_name="alice")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
