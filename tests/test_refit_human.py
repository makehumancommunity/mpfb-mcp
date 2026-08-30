# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_refit_human tool: argument validation, and the generated
code's subject resolution, enumeration and the one failure MPFB reports only
through an operator.

The generated code cannot be run against real MPFB from here (see
specifications/architecture.md), so it is executed against the stubs in
tests/blender_stubs.py. Whether a refit visibly puts clothes back on a deformed
body is exactly what these tests cannot say; that remains a manual check against
a running Blender.

What they do check is the reporting around the call, which is where this tool
adds anything at all over ``HumanService.refit()``: a missing basemesh comes back
as an answer rather than the ValueError refit() raises, and a generated Rigify
rig with no meta rig is reported rather than passed off as a successful refit.

Run with::

    python -m unittest tests.test_refit_human -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import refit_human
from tests.blender_stubs import GeneratedCodeTestCase, StubHumanService, StubObject


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    refit_human.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_refit_human"]  # noqa: SLF001
    return tool.fn


class RefitHumanToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_refit_human = _register_and_get_tool()

    @mock.patch("mpfbmcp.tools.refit_human.send_code")
    def test_omitted_name_is_sent_as_null(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"found": False}}

        self.mpfb_refit_human()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertEqual(_params_in(code), {"name": None})

    @mock.patch("mpfbmcp.tools.refit_human.send_code")
    def test_name_is_passed_through_verbatim(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"found": True}}

        self.mpfb_refit_human("Human.rig")

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code), {"name": "Human.rig"})

    def test_blank_and_non_string_names_are_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.tools.refit_human.send_code") as mock_send_code:
            for bad in ("", "   ", "\t", 1, True, ["Human"]):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        self.mpfb_refit_human(bad)
            mock_send_code.assert_not_called()


class GeneratedRefitHumanTests(GeneratedCodeTestCase):
    """Runs the payload against the stub scene."""

    def build_character(self, rig=True, garments=("Shirt",), subrigs=(), **basemesh_kwargs):
        """A dressed character, parented the way MPFB parents one.

        Garments hang off the rig rather than off the basemesh when there is a
        rig, which is what refit()'s own only_children walk from the rig is
        written for.
        """
        self.rig = None
        if rig:
            self.rig = StubObject(
                "Human.rig", blender_type="ARMATURE", object_type="Skeleton")
        self.basemesh = StubObject(
            "Human", parent=self.rig, object_type="Basemesh",
            shapekeys=[("Basis", 0.0), ("$md-$ca-$fe-$yn", 1.0)], **basemesh_kwargs)
        parent = self.rig or self.basemesh
        self.garments = [
            StubObject(name, parent=parent, object_type="Clothes") for name in garments]
        self.subrigs = [
            StubObject(name, blender_type="ARMATURE", parent=parent, object_type="Subrig")
            for name in subrigs]
        self.objects = [obj for obj in [self.rig, self.basemesh] if obj]
        self.objects += self.garments + self.subrigs
        return self.objects

    def run_refit(self, name="Human", active=None):
        return self.run_payload(
            "refit_human.py", {"name": name},
            scene_objects=self.objects, active=active)

    def test_a_rigged_dressed_character_is_refitted(self) -> None:
        self.build_character(garments=("Shirt", "Shoes"), subrigs=("Shirt.rig",))

        result = self.run_refit()

        self.assertTrue(result["found"])
        self.assertTrue(result["ready"])
        self.assertTrue(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, ["Human"])
        self.assertEqual(sorted(result["mesh_assets"]), ["Shirt", "Shoes"])
        self.assertEqual(result["mesh_asset_count"], 2)
        self.assertEqual(result["subrigs"], ["Shirt.rig"])
        self.assertEqual(result["rig_name"], "Human.rig")

    def test_an_unrigged_character_is_refitted_and_says_so(self) -> None:
        self.build_character(rig=False)

        result = self.run_refit()

        self.assertTrue(result["refit_performed"])
        self.assertIsNone(result["rig_name"])
        self.assertEqual(result["mesh_assets"], ["Shirt"])
        self.assertIn("no rig", result["message"])

    def test_subject_resolves_from_the_rig_and_from_a_garment(self) -> None:
        for name in ("Human.rig", "Shirt"):
            with self.subTest(name=name):
                self.build_character()

                result = self.run_refit(name)

                self.assertEqual(result["subject_name"], name)
                self.assertEqual(result["basemesh_name"], "Human")
                self.assertTrue(result["refit_performed"])

    def test_active_object_is_used_when_no_name_is_given(self) -> None:
        self.build_character()

        result = self.run_refit(None, active=self.garments[0])

        self.assertEqual(result["subject_resolved_by"], "active")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_no_active_object_is_an_answer(self) -> None:
        self.build_character()

        result = self.run_refit(None, active=None)

        self.assertFalse(result["found"])
        self.assertFalse(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, [])

    def test_unresolvable_name_is_an_answer(self) -> None:
        self.build_character()

        result = self.run_refit("Nonexistent")

        self.assertFalse(result["found"])
        self.assertEqual(StubHumanService.refit_calls, [])

    def test_an_object_with_no_basemesh_is_an_answer_not_a_valueerror(self) -> None:
        # refit() raises here, which is why the basemesh is resolved first.
        self.build_character()
        cube = StubObject("Cube")
        self.objects = [cube]

        result = self.run_refit("Cube")

        self.assertFalse(result["found"])
        self.assertIn("no MakeHuman basemesh", result["message"])
        self.assertEqual(StubHumanService.refit_calls, [])

    def test_edit_mode_is_an_answer(self) -> None:
        self.build_character(mode="EDIT")

        result = self.run_refit()

        self.assertTrue(result["found"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertFalse(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, [])

    def test_generated_rigify_without_a_metarig_is_reported_not_claimed(self) -> None:
        # The failure refit() reports only through an operator: it refits the
        # mesh assets, silently leaves the rig, and returns.
        self.build_character(rig=False)
        rigify = StubObject("RIG-human", blender_type="ARMATURE", object_type="Skeleton",
                            rig_id="abc123")
        self.basemesh.parent = rigify
        self.garments[0].parent = rigify
        self.objects = [rigify] + self.objects

        result = self.run_refit("Human")

        self.assertEqual(StubHumanService.refit_calls, ["Human"])
        self.assertFalse(result["refit_performed"])
        self.assertIn("generated Rigify rig", result["refit_incomplete_reason"])
        self.assertIn("Meta-rig", result["message"])

    def test_generated_rigify_with_a_metarig_refits_normally(self) -> None:
        self.build_character(rig=False)
        rigify = StubObject("RIG-human", blender_type="ARMATURE", object_type="Skeleton",
                            rig_id="abc123")
        metarig = StubObject("metarig", blender_type="ARMATURE", metarig=True,
                             rigify_target_rig=rigify)
        self.basemesh.parent = rigify
        self.garments[0].parent = rigify
        self.objects = [rigify, metarig] + self.objects

        result = self.run_refit("Human")

        self.assertTrue(result["refit_performed"])
        self.assertIsNone(result["refit_incomplete_reason"])

    def test_an_ordinary_rig_is_never_mistaken_for_a_rigify_one(self) -> None:
        # object_is_generated_rigify_rig() answers with Rigify's rig_id string
        # rather than a bool, so only its truthiness may be relied on.
        self.build_character()

        result = self.run_refit()

        self.assertTrue(result["refit_performed"])
        self.assertIsNone(result["refit_incomplete_reason"])

    def test_the_previous_active_object_and_selection_are_restored(self) -> None:
        self.build_character()

        self.run_refit("Human", active=self.garments[0])

        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.garments[0])

    def test_the_previous_state_is_restored_even_when_the_refit_fails(self) -> None:
        self.build_character()
        StubHumanService.refit_raises = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            self.run_refit("Human", active=self.garments[0])

        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.garments[0])


def _params_in(code: str) -> dict:
    """The PARAMS the generated source will bind, by executing its prelude."""
    prelude, _sep, _payload = code.partition("# --- payload:")
    # The prelude sits behind the raising bootstrap, which would fail here with
    # no MPFB loaded, so run only the two lines that bind PARAMS.
    namespace: dict = {}
    exec(prelude[prelude.index("import json"):], namespace)  # noqa: S102
    return namespace["PARAMS"]


if __name__ == "__main__":
    unittest.main()
