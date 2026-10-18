# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_create_export_copy``: the shape of thirteen arguments, and what reaches the wire.

Two layers (see ``tests/test_list_objects.py``, the template). Every argument is
checked here before anything is sent: nine real bools, the subject, the two
modifier strategies and ``material_type`` - this package's own vocabularies,
since no MPFB function receives them - and ``suffix``'s length. The defaults
are the panel's, so the default call is pinned whole.

What the copy *is* - the original unchanged after every option, each option's
effect, the pack and proxy refusals, the repairs MPFB's copy needs, the baked
face, the GameEngine swap leaving the original's materials alone - is checked
against a real MPFB in ``bridge/test/tests/ddd_mutating/create_export_copy_test.py``.

Run with::

    python -m unittest tests.test_create_export_copy -v
"""

from __future__ import annotations

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import create_export_copy

from tests import fake_bridge

_FLAGS = ("bake_shapekeys", "delete_helpers", "remove_basemesh", "load_microsoft_visemes",
          "load_meta_visemes", "load_arkit_face_units", "interpolate", "in_export_collection")


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    create_export_copy.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_create_export_copy"].fn


class CreateExportCopyValidationTests(unittest.TestCase):
    """Every argument's shape, before anything is sent."""

    def setUp(self) -> None:
        self.call = _tool_callable()

    def _run(self, **arguments):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args[0][0], "create_export_copy")
            return send.call_args[0][1]

    def _refused(self, **arguments):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            with self.assertRaises(ValueError) as raised:
                self.call(**arguments)
            self.assertEqual(send.call_count, 0)
        return str(raised.exception)

    def test_the_default_call_is_the_panels_defaults(self) -> None:
        self.assertEqual(self._run(), {
            "name": None, "bake_shapekeys": True, "mask_modifiers": "KEEP",
            "subdiv_modifiers": "KEEP", "delete_helpers": True, "remove_basemesh": False,
            "load_microsoft_visemes": False, "load_meta_visemes": False,
            "load_arkit_face_units": False, "interpolate": False, "suffix": "_export_copy",
            "in_export_collection": True, "material_type": None})

    def test_every_flag_must_be_a_real_bool(self) -> None:
        for flag in _FLAGS:
            for value in ("false", "true", 1, 0, None):
                with self.subTest(flag=flag, value=value):
                    self.assertIn(flag, self._refused(**{flag: value}))
            self.assertIs(self._run(**{flag: False})[flag], False)

    def test_the_modifier_strategies_are_this_packages_three(self) -> None:
        for argument in ("mask_modifiers", "subdiv_modifiers"):
            for value in create_export_copy.MODIFIER_STRATEGIES:
                with self.subTest(argument=argument, value=value):
                    self.assertEqual(self._run(**{argument: value})[argument], value)
            # Not normalised: the panel's spelling is upper case, and a lower
            # case one is a caller who guessed.
            for bad in ("bake", "APPLY", "", None, 1):
                with self.subTest(argument=argument, value=bad):
                    message = self._refused(**{argument: bad})
                    self.assertIn("KEEP, REMOVE, BAKE", message)

    def test_material_type_is_null_or_gameengine(self) -> None:
        self.assertEqual(self._run(material_type="GAMEENGINE")["material_type"], "GAMEENGINE")
        self.assertIsNone(self._run(material_type=None)["material_type"])
        for bad in ("MAKESKIN", "gameengine", "", 3):
            with self.subTest(material_type=bad):
                self._refused(material_type=bad)

    def test_the_suffix_is_any_string_up_to_its_bound(self) -> None:
        # The empty suffix is MPFB's panel's to accept, so it is accepted here.
        self.assertEqual(self._run(suffix="")["suffix"], "")
        self.assertEqual(self._run(suffix="_unity")["suffix"], "_unity")
        self.assertEqual(self._run(suffix="x" * create_export_copy.SUFFIX_MAX_LENGTH)["suffix"],
                         "x" * create_export_copy.SUFFIX_MAX_LENGTH)
        self._refused(suffix="x" * (create_export_copy.SUFFIX_MAX_LENGTH + 1))
        self._refused(suffix=None)
        self._refused(suffix=3)

    def test_the_subject_is_optional_and_shape_checked(self) -> None:
        self.assertEqual(self._run(name="Human")["name"], "Human")
        self._refused(name="")
        self._refused(name=3)


class CreateExportCopyOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "create_export_copy": fake_bridge.ok_envelope(
                "create_export_copy", {"found": True, "created": True, "performed": True}),
        })

    def test_the_tool_sends_the_create_export_copy_command(self) -> None:
        envelope = self.call(name="Human", mask_modifiers="BAKE", load_arkit_face_units=True)

        self.assertEqual(envelope["result"]["created"], True)
        self.assertEqual(self.bridge.commands()[-1], "create_export_copy")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["mask_modifiers"], "BAKE")
        self.assertIs(params["load_arkit_face_units"], True)

    def test_a_refused_argument_reaches_no_backend(self) -> None:
        with self.assertRaises(ValueError):
            self.call(mask_modifiers="apply")
        self.assertEqual(self.bridge.requests, [])
