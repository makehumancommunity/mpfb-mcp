# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_get_macro_details tool: argument validation, and the
generated code's subject resolution, reading and drift reporting.

The generated code cannot be run against real MPFB from here (see
specifications/architecture.md), so it is executed against the stubs in
tests/blender_stubs.py. That checks the branching and the shape of ``result``;
it says nothing about whether real MPFB returns the values we assume, which
remains a manual check against a running Blender.

The cases worth naming here are the ones the tool exists for: resolving the
basemesh from *any* member of the character's family, reporting the raw race
sum rather than a normalized one, and reporting the derived target stack beside
the shape keys actually on the mesh so that a drifted character is visible.

Run with::

    python -m unittest tests.test_get_macro_details -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import get_macro_details
from tests.blender_stubs import GeneratedCodeTestCase, StubObject


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    get_macro_details.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_get_macro_details"]  # noqa: SLF001
    return tool.fn


class GetMacroDetailsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_get_macro_details = _register_and_get_tool()

    @mock.patch("mpfbmcp.tools.get_macro_details.send_code")
    def test_omitted_name_is_sent_as_null(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"found": False}}

        self.mpfb_get_macro_details()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertEqual(_params_in(code), {"name": None})

    @mock.patch("mpfbmcp.tools.get_macro_details.send_code")
    def test_name_is_passed_through_verbatim(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"found": True}}

        self.mpfb_get_macro_details("Human")

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code), {"name": "Human"})

    def test_blank_name_is_rejected_locally(self) -> None:
        # An explicitly empty name and an omitted one arise from different
        # mistakes, so the empty one never falls back to the active object.
        with mock.patch("mpfbmcp.tools.get_macro_details.send_code") as mock_send_code:
            for blank in ("", "   ", "\t"):
                with self.subTest(name=blank):
                    with self.assertRaises(ValueError):
                        self.mpfb_get_macro_details(blank)
            mock_send_code.assert_not_called()

    def test_non_string_name_is_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.tools.get_macro_details.send_code") as mock_send_code:
            for bad in (1, 1.5, True, ["Human"]):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        self.mpfb_get_macro_details(bad)
            mock_send_code.assert_not_called()


class GeneratedGetMacroDetailsTests(GeneratedCodeTestCase):
    """Runs the payload against the stub scene."""

    def build_character(self, **basemesh_kwargs):
        """A rigged, dressed character: rig -> basemesh -> shirt."""
        rig = StubObject("Human.rig", blender_type="ARMATURE", object_type="Skeleton")
        basemesh = StubObject(
            "Human", parent=rig, object_type="Basemesh",
            shapekeys=basemesh_kwargs.pop("shapekeys", [("$md-$ca-$fe-$yn", 1.0)]),
            **basemesh_kwargs)
        shirt = StubObject("Shirt", parent=basemesh, object_type="Clothes")
        return rig, basemesh, shirt

    def run_get(self, name=None, scene_objects=(), all_objects=None, active=None):
        return self.run_payload(
            "get_macro_details.py", {"name": name},
            scene_objects=scene_objects, all_objects=all_objects, active=active)

    def test_named_basemesh_is_read(self) -> None:
        rig, basemesh, shirt = self.build_character()

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertTrue(result["found"])
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertEqual(result["subject_name"], "Human")
        self.assertEqual(result["subject_resolved_by"], "name")
        self.assertEqual(result["macro_details"]["gender"], 0.5)
        self.assertEqual(result["macro_details"]["race"]["caucasian"], 0.33)

    def test_subject_resolves_from_the_rig(self) -> None:
        # The whole point of resolving through the relationship walk: an agent
        # that got a name out of mpfb_list_objects has no reason to know which
        # member of the family owns the macro properties.
        rig, basemesh, shirt = self.build_character()

        result = self.run_get("Human.rig", scene_objects=[rig, basemesh, shirt])

        self.assertTrue(result["found"])
        self.assertEqual(result["subject_name"], "Human.rig")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_subject_resolves_from_a_clothes_object(self) -> None:
        rig, basemesh, shirt = self.build_character()

        result = self.run_get("Shirt", scene_objects=[rig, basemesh, shirt])

        self.assertTrue(result["found"])
        self.assertEqual(result["subject_name"], "Shirt")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_active_object_is_used_when_no_name_is_given(self) -> None:
        rig, basemesh, shirt = self.build_character()

        result = self.run_get(None, scene_objects=[rig, basemesh, shirt], active=shirt)

        self.assertTrue(result["found"])
        self.assertEqual(result["subject_resolved_by"], "active")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_no_active_object_is_an_answer_rather_than_a_crash(self) -> None:
        # The branch that would otherwise fail on None.name.
        result = self.run_get(None, scene_objects=[], active=None)

        self.assertFalse(result["found"])
        self.assertIsNone(result["basemesh_name"])
        self.assertIn("no object is active", result["message"])

    def test_unresolvable_name_is_an_answer(self) -> None:
        rig, basemesh, shirt = self.build_character()

        result = self.run_get("Nonexistent", scene_objects=[rig, basemesh, shirt])

        self.assertFalse(result["found"])
        self.assertIn("Nonexistent", result["message"])

    def test_object_outside_a_character_is_an_answer(self) -> None:
        cube = StubObject("Cube")

        result = self.run_get("Cube", scene_objects=[cube])

        self.assertFalse(result["found"])
        self.assertEqual(result["subject_name"], "Cube")
        self.assertIn("no MakeHuman basemesh", result["message"])

    def test_object_outside_the_scene_still_resolves(self) -> None:
        rig, basemesh, shirt = self.build_character()

        result = self.run_get("Human", scene_objects=[], all_objects=[rig, basemesh, shirt])

        self.assertTrue(result["found"])
        self.assertFalse(result["basemesh_in_current_scene"])

    def test_values_are_read_through_the_property_store(self) -> None:
        rig, basemesh, shirt = self.build_character(
            macro_details={"gender": 1.0, "age": 0.1875, "asian": 0.0})

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertEqual(result["macro_details"]["gender"], 1.0)
        self.assertEqual(result["macro_details"]["age"], 0.1875)
        self.assertEqual(result["macro_details"]["race"]["asian"], 0.0)

    def test_defaults_are_reported_beside_the_current_values(self) -> None:
        # Without them there is no way to tell a deliberately average character
        # from an untouched one except by hardcoding 0.5 on the caller's side.
        rig, basemesh, shirt = self.build_character()

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertEqual(result["default_macro_details"]["gender"], 0.5)
        self.assertEqual(result["default_macro_details"]["race"]["african"], 0.33)

    def test_race_weights_are_reported_raw_and_summed(self) -> None:
        # MPFB does not normalize them, so neither does this - it reports the
        # sum and says so.
        rig, basemesh, shirt = self.build_character(
            macro_details={"asian": 1.0, "caucasian": 0.33, "african": 0.33})

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertEqual(result["macro_details"]["race"]["asian"], 1.0)
        self.assertAlmostEqual(result["race_sum"], 1.66)
        self.assertFalse(result["race_normalized"])
        self.assertIn("1.66", result["message"])

    def test_a_race_sum_of_one_is_reported_as_normalized(self) -> None:
        rig, basemesh, shirt = self.build_character(
            macro_details={"asian": 0.0, "caucasian": 1.0, "african": 0.0})

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertTrue(result["race_normalized"])
        self.assertNotIn("rather than 1.0", result["message"])

    def test_target_stack_names_the_fragment_and_the_shape_key(self) -> None:
        # The two are different strings, and neither is an address a tool takes.
        rig, basemesh, shirt = self.build_character(
            macro_details={"asian": 0.0, "caucasian": 1.0, "african": 0.0})

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertEqual(result["macro_target_count"], len(result["macro_target_stack"]))
        entry = result["macro_target_stack"][0]
        self.assertTrue(entry["target_fragment"].startswith("macrodetails/"))
        self.assertTrue(entry["shapekey_name"].startswith("$md-"))
        self.assertNotEqual(entry["target_fragment"], entry["shapekey_name"])
        self.assertIsInstance(entry["weight"], float)

    def test_current_shapekeys_are_reported_under_the_names_on_the_mesh(self) -> None:
        rig, basemesh, shirt = self.build_character(
            shapekeys=[("Basis", 0.0), ("$md-$ca-$fe-$yn", 1.0)])

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        # Undecoded, and only the macro ones: Basis is not a macro target. The
        # name matters as much as the filtering - see the test below, which is
        # the reason this one is not asserting the decoded form.
        self.assertEqual(result["current_macro_shapekeys"], ["$md-$ca-$fe-$yn"])
        self.assertEqual(result["current_macro_shapekeys_decoded"],
                         ["macrodetail-caucasian-female-young"])

    def test_the_stack_and_the_mesh_listing_are_one_vocabulary(self) -> None:
        # The docstring tells a caller to compare macro_target_stack against
        # current_macro_shapekeys and read a difference as drift. That is only
        # possible if the two name shape keys the same way. They did not: the
        # stack reported encoded names and the mesh listing decoded ones, so the
        # comparison reported drift on every healthy character there is.
        rig, basemesh, shirt = self.build_character(
            shapekeys=[("Basis", 0.0), ("$md-$ca-$fe-$yn", 1.0)])

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        on_the_mesh = set(result["current_macro_shapekeys"])
        in_the_stack = set(entry["shapekey_name"] for entry in result["macro_target_stack"])
        self.assertTrue(on_the_mesh)
        self.assertTrue(on_the_mesh <= in_the_stack)

    def test_drift_between_properties_and_shape_is_reported(self) -> None:
        # The state mpfb_set_macro_details exists to repair: the values imply a
        # stack the mesh does not carry.
        rig, basemesh, shirt = self.build_character(shapekeys=[("Basis", 0.0)])

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertEqual(result["current_macro_shapekeys"], [])
        self.assertGreater(result["macro_target_count"], 0)
        self.assertIn("drifted apart", result["message"])

    def test_a_mesh_with_no_shapekeys_is_flagged(self) -> None:
        # An imported mesh tagged as a basemesh reads back a full set of macro
        # properties that describe nothing.
        rig, basemesh, shirt = self.build_character(shapekeys=None)

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertTrue(result["found"])
        self.assertFalse(result["has_shapekeys"])
        self.assertIn("describe nothing", result["message"])

    def test_is_human_project_is_reported(self) -> None:
        rig, basemesh, shirt = self.build_character(is_human_project=True)

        result = self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertIs(result["is_human_project"], True)

    def test_nothing_is_activated_or_recalculated(self) -> None:
        # A read-only tool that quietly repaired the drift it reports would be
        # lying about being read-only.
        from tests.blender_stubs import StubObjectService, StubTargetService
        rig, basemesh, shirt = self.build_character()
        before = list(basemesh.data.shape_keys.key_blocks)

        self.run_get("Human", scene_objects=[rig, basemesh, shirt])

        self.assertEqual(StubObjectService.activations, [])
        self.assertEqual(StubTargetService.reapply_calls, [])
        self.assertEqual(list(basemesh.data.shape_keys.key_blocks), before)


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
