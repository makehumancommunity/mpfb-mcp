# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_set_macro_details tool: argument validation, and the
generated code's preconditions, write-then-recalculate sequence and reporting.

The generated code cannot be run against real MPFB from here (see
specifications/architecture.md), so it is executed against the stubs in
tests/blender_stubs.py. That checks the branching and the shape of ``result``;
it says nothing about whether a character modified through this tool ends up
with the same shape keys at the same weights as one modified through MPFB's own
phenotype sliders, which is the point of the tool and remains a manual check
against a running Blender.

The distinctions worth testing are the ones a caller would otherwise get wrong:
an omitted slider is left alone rather than reset to its default; a slider set
to the value it already had is *reported* rather than silently dropped; a call
naming nothing recalculates nothing; and a change that leaves the character's
clothes fitted to the old shape says so.

Run with::

    python -m unittest tests.test_set_macro_details -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import set_macro_details
from tests.blender_stubs import (
    GeneratedCodeTestCase, StubHumanService, StubObject, StubObjectService,
    StubTargetService)


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    set_macro_details.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_set_macro_details"]  # noqa: SLF001
    return tool.fn


class SetMacroDetailsToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_set_macro_details = _register_and_get_tool()

    @mock.patch("mpfbmcp.tools.set_macro_details.send_code")
    def test_defaults_name_nothing_and_keep_mpfbs_own_flags(
            self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertEqual(_params_in(code), {
            "name": None, "changes": [], "prune": True, "refit": False})

    @mock.patch("mpfbmcp.tools.set_macro_details.send_code")
    def test_only_named_sliders_are_sent(self, mock_send_code: mock.Mock) -> None:
        # The distinction a nested macro-detail dict could not express without a
        # sentinel, and the reason the arguments are flat.
        mock_send_code.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details(name="Human", age=0.75)

        (code,), _kwargs = mock_send_code.call_args
        params = _params_in(code)
        self.assertEqual(params["name"], "Human")
        self.assertEqual(params["changes"], [
            {"argument": "age", "property": "age", "value": 0.75}])

    @mock.patch("mpfbmcp.tools.set_macro_details.send_code")
    def test_race_arguments_map_onto_mpfbs_property_names(
            self, mock_send_code: mock.Mock) -> None:
        # The arguments carry the prefix that groups them, matching
        # mpfb_create_human; MPFB stores them without it.
        mock_send_code.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details(race_asian=1.0, race_african=0.0)

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code)["changes"], [
            {"argument": "race_asian", "property": "asian", "value": 1.0},
            {"argument": "race_african", "property": "african", "value": 0.0},
        ])

    @mock.patch("mpfbmcp.tools.set_macro_details.send_code")
    def test_zero_is_a_value_and_not_an_omission(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details(gender=0.0)

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code)["changes"], [
            {"argument": "gender", "property": "gender", "value": 0.0}])

    @mock.patch("mpfbmcp.tools.set_macro_details.send_code")
    def test_integers_are_accepted_and_coerced(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"changed": []}}

        self.mpfb_set_macro_details(gender=1)

        (code,), _kwargs = mock_send_code.call_args
        value = _params_in(code)["changes"][0]["value"]
        self.assertIsInstance(value, float)
        self.assertEqual(value, 1.0)

    def test_out_of_range_sliders_are_rejected_locally(self) -> None:
        # MPFB's own properties are unclamped - the JSON definitions carry a
        # default but no min/max - so this check exists here or nowhere.
        with mock.patch("mpfbmcp.tools.set_macro_details.send_code") as mock_send_code:
            for value in (-0.1, 1.1, 5.0, -1):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(gender=value)
            mock_send_code.assert_not_called()

    def test_non_numeric_sliders_are_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.tools.set_macro_details.send_code") as mock_send_code:
            for value in ("0.5", True, False, [0.5], object()):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(gender=value)
            mock_send_code.assert_not_called()

    def test_non_bool_flags_are_rejected_locally(self) -> None:
        # Not truthiness: refit="false" would otherwise pay for a full refit.
        with mock.patch("mpfbmcp.tools.set_macro_details.send_code") as mock_send_code:
            for value in ("false", 0, 1, None):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(refit=value)
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(prune=value)
            mock_send_code.assert_not_called()

    def test_blank_and_non_string_names_are_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.tools.set_macro_details.send_code") as mock_send_code:
            for bad in ("", "   ", 1, ["Human"]):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        self.mpfb_set_macro_details(name=bad)
            mock_send_code.assert_not_called()

    def test_the_error_names_the_argument_the_caller_used(self) -> None:
        # "asian must be between..." would name something the caller cannot pass.
        with self.assertRaises(ValueError) as raised:
            self.mpfb_set_macro_details(race_caucasian=2.0)

        self.assertIn("race_caucasian", str(raised.exception))


class GeneratedSetMacroDetailsTests(GeneratedCodeTestCase):
    """Runs the payload against the stub scene."""

    def build_character(self, shapekeys=(("Basis", 0.0), ("$md-$as-$fe-$yn", 0.5)),
                        rig=True, **basemesh_kwargs):
        """A dressed - and by default rigged - character to modify.

        Parented the way MPFB parents one: a garment on a rigged character hangs
        off the *rig* rather than off the basemesh (ClothesService parents to
        `basemesh.parent` when there is one), so the mesh assets are found by
        walking up to the rig and back down its other branches rather than
        straight down from the basemesh.
        """
        self.rig = None
        if rig:
            self.rig = StubObject(
                "Human.rig", blender_type="ARMATURE", object_type="Skeleton")
        self.basemesh = StubObject(
            "Human", parent=self.rig, object_type="Basemesh",
            shapekeys=list(shapekeys) if shapekeys else None, **basemesh_kwargs)
        self.shirt = StubObject(
            "Shirt", parent=self.rig or self.basemesh, object_type="Clothes")
        self.objects = [obj for obj in (self.rig, self.basemesh, self.shirt) if obj]
        return self.objects

    def run_set(self, changes=(), name="Human", prune=True, refit=False, active=None):
        return self.run_payload(
            "set_macro_details.py",
            {"name": name, "changes": list(changes), "prune": prune, "refit": refit},
            scene_objects=self.objects, active=active)

    @staticmethod
    def change(argument, prop, value):
        return {"argument": argument, "property": prop, "value": value}

    def macro_property(self, name):
        return self.basemesh.properties["HUM"][name]

    def test_a_named_slider_is_written_and_reported(self) -> None:
        self.build_character()

        result = self.run_set([self.change("age", "age", 1.0)])

        self.assertTrue(result["found"])
        self.assertTrue(result["ready"])
        self.assertTrue(result["recalculated"])
        self.assertEqual(result["changed"], [
            {"name": "age", "property": "age", "previous": 0.5, "new": 1.0}])
        self.assertEqual(self.macro_property("age"), 1.0)
        self.assertEqual(result["macro_details"]["age"], 1.0)

    def test_an_omitted_slider_is_left_alone_rather_than_defaulted(self) -> None:
        # The mistake a caller would make if omission meant "use the default":
        # a character built at gender 1.0 would quietly revert to 0.5.
        self.build_character(macro_details={"gender": 1.0, "cupsize": 0.2})

        result = self.run_set([self.change("age", "age", 0.75)])

        self.assertEqual(self.macro_property("gender"), 1.0)
        self.assertEqual(self.macro_property("cupsize"), 0.2)
        self.assertEqual([entry["name"] for entry in result["changed"]], ["age"])
        self.assertEqual(result["macro_details"]["gender"], 1.0)

    def test_a_slider_set_to_its_current_value_is_still_reported(self) -> None:
        # Not the same claim as not mentioning it: the caller asked for it, and
        # a recalculation ran.
        self.build_character()

        result = self.run_set([self.change("gender", "gender", 0.5)])

        self.assertEqual(result["changed"], [
            {"name": "gender", "property": "gender", "previous": 0.5, "new": 0.5}])
        self.assertTrue(result["recalculated"])

    def test_naming_nothing_recalculates_nothing(self) -> None:
        # A no-op is a common agent mistake and a macro reapply costs seconds.
        self.build_character()

        result = self.run_set([])

        self.assertTrue(result["found"])
        self.assertTrue(result["ready"])
        self.assertEqual(result["changed"], [])
        self.assertFalse(result["recalculated"])
        self.assertEqual(StubTargetService.reapply_calls, [])
        self.assertEqual(StubObjectService.activations, [])
        self.assertIn("No macro detail was named", result["message"])
        # Still worth answering with, so the caller can name something next.
        self.assertEqual(result["macro_details"]["gender"], 0.5)

    def test_every_property_is_written_before_a_single_recalculation(self) -> None:
        # Recalculating per property would be N times the work for the same
        # result, since the stack is derived from all eleven values at once.
        self.build_character()

        self.run_set([
            self.change("gender", "gender", 1.0),
            self.change("age", "age", 0.25),
            self.change("race_asian", "asian", 0.0),
        ])

        self.assertEqual(StubTargetService.reapply_calls, [("Human", True)])
        self.assertEqual(self.macro_property("gender"), 1.0)
        self.assertEqual(self.macro_property("age"), 0.25)
        self.assertEqual(self.macro_property("asian"), 0.0)

    def test_prune_is_passed_through(self) -> None:
        self.build_character()

        self.run_set([self.change("age", "age", 1.0)], prune=False)

        self.assertEqual(StubTargetService.reapply_calls, [("Human", False)])

    def test_race_weights_are_stored_raw(self) -> None:
        # Normalizing here would produce a character MPFB's own sliders cannot
        # reproduce, which is the one thing this tool must not do.
        self.build_character()

        result = self.run_set([self.change("race_asian", "asian", 1.0)])

        self.assertEqual(self.macro_property("asian"), 1.0)
        self.assertEqual(self.macro_property("caucasian"), 0.33)
        self.assertAlmostEqual(result["race_sum"], 1.66)
        self.assertFalse(result["race_normalized"])
        self.assertIn("does not normalize", result["message"])

    def test_removed_and_added_shapekeys_are_reported(self) -> None:
        # With prune on, a macro target that fell to zero is deleted; a caller
        # comparing two reads would otherwise see shape keys vanish unexplained.
        self.build_character()

        result = self.run_set([self.change("race_asian", "asian", 0.0)])

        self.assertIn("macrodetail-asian-female-young", result["macro_shapekeys_before"])
        self.assertIn("macrodetail-asian-female-young", result["shapekeys_removed"])
        self.assertNotIn("macrodetail-asian-female-young", result["macro_shapekeys_after"])
        self.assertTrue(result["shapekeys_added"])
        self.assertEqual(
            sorted(result["macro_shapekeys_after"]),
            sorted(set(result["macro_shapekeys_before"])
                   - set(result["shapekeys_removed"])
                   | set(result["shapekeys_added"])))

    def test_without_prune_zero_weight_shapekeys_stay(self) -> None:
        self.build_character()

        result = self.run_set([self.change("race_asian", "asian", 0.0)], prune=False)

        self.assertEqual(result["shapekeys_removed"], [])
        self.assertIn("macrodetail-asian-female-young", result["macro_shapekeys_after"])

    def test_edit_mode_is_an_answer_rather_than_an_assertion(self) -> None:
        # TargetService.create_shape_key() opens with a bare assert, which would
        # come back as a traceback naming nothing.
        self.build_character(mode="EDIT")

        result = self.run_set([self.change("age", "age", 1.0)])

        self.assertTrue(result["found"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(result["changed"], [])
        self.assertEqual(StubTargetService.reapply_calls, [])
        self.assertEqual(self.macro_property("age"), 0.5)
        self.assertIn("EDIT", result["message"])

    def test_a_mesh_with_no_shapekeys_is_an_answer(self) -> None:
        # reapply_macro_details() only logs "somewhat surprising" and carries on.
        self.build_character(shapekeys=None)

        result = self.run_set([self.change("age", "age", 1.0)])

        self.assertFalse(result["ready"])
        self.assertEqual(result["blocked_by"], "no_shapekeys")
        self.assertEqual(StubTargetService.reapply_calls, [])
        self.assertEqual(self.macro_property("age"), 0.5)

    def test_subject_resolves_from_the_rig_and_names_the_basemesh(self) -> None:
        self.build_character()

        result = self.run_set([self.change("age", "age", 1.0)], name="Human.rig")

        self.assertEqual(result["subject_name"], "Human.rig")
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertEqual(self.macro_property("age"), 1.0)

    def test_subject_resolves_from_a_clothes_object(self) -> None:
        self.build_character()

        result = self.run_set([self.change("age", "age", 1.0)], name="Shirt")

        self.assertEqual(result["basemesh_name"], "Human")

    def test_unresolvable_subject_changes_nothing(self) -> None:
        self.build_character()

        result = self.run_set([self.change("age", "age", 1.0)], name="Nonexistent")

        self.assertFalse(result["found"])
        self.assertEqual(result["changed"], [])
        self.assertEqual(self.macro_property("age"), 0.5)

    def test_no_active_object_changes_nothing(self) -> None:
        self.build_character()

        result = self.run_set([self.change("age", "age", 1.0)], name=None, active=None)

        self.assertFalse(result["found"])
        self.assertIn("no object is active", result["message"])

    def test_stale_assets_are_reported_when_no_refit_was_asked_for(self) -> None:
        # A tool that moves a body under fitted clothes and says nothing has
        # told the caller something false by omission.
        self.build_character()

        result = self.run_set([self.change("age", "age", 1.0)])

        self.assertFalse(result["refit_performed"])
        self.assertEqual(result["assets_possibly_stale"]["mesh_assets"], ["Shirt"])
        self.assertEqual(result["assets_possibly_stale"]["mesh_asset_count"], 1)
        self.assertTrue(result["assets_possibly_stale"]["rig_attached"])
        self.assertEqual(result["assets_possibly_stale"]["rig_name"], "Human.rig")
        self.assertIn("mpfb_refit_human", result["message"])

    def test_refit_runs_when_asked_for(self) -> None:
        self.build_character()

        result = self.run_set([self.change("age", "age", 1.0)], refit=True)

        self.assertEqual(StubHumanService.refit_calls, ["Human"])
        self.assertTrue(result["refit_performed"])
        self.assertIsNone(result["assets_possibly_stale"])
        self.assertIsNone(result["refit_incomplete_reason"])

    def test_generated_rigify_without_a_metarig_is_reported_not_claimed(self) -> None:
        # refit() reports this through an operator it will not be given here,
        # and refits the mesh assets but not the rig.
        self.build_character(rig=False)
        rigify = StubObject("RIG-human", blender_type="ARMATURE", object_type="Skeleton",
                            rig_id="abc123")
        self.basemesh.parent = rigify
        self.shirt.parent = rigify
        self.objects = [rigify] + self.objects

        result = self.run_set([self.change("age", "age", 1.0)], refit=True)

        self.assertEqual(StubHumanService.refit_calls, ["Human"])
        self.assertFalse(result["refit_performed"])
        self.assertIn("generated Rigify rig", result["refit_incomplete_reason"])
        self.assertIn("Mesh assets were refitted", result["message"])
        self.assertIsNotNone(result["assets_possibly_stale"])

    def test_generated_rigify_with_a_metarig_refits_normally(self) -> None:
        self.build_character(rig=False)
        rigify = StubObject("RIG-human", blender_type="ARMATURE", object_type="Skeleton",
                            rig_id="abc123")
        metarig = StubObject("metarig", blender_type="ARMATURE", metarig=True,
                             rigify_target_rig=rigify)
        self.basemesh.parent = rigify
        self.shirt.parent = rigify
        self.objects = [rigify, metarig] + self.objects

        result = self.run_set([self.change("age", "age", 1.0)], refit=True)

        self.assertTrue(result["refit_performed"])
        self.assertIsNone(result["refit_incomplete_reason"])

    def test_the_basemesh_is_activated_and_the_previous_state_restored(self) -> None:
        # MPFB's own slider callback activates the basemesh. The user is looking
        # at this scene, so what was borrowed is put back.
        self.build_character()
        result = self.run_set(
            [self.change("age", "age", 1.0)], name="Human", active=self.shirt)

        self.assertEqual(StubObjectService.activations, ["Human"])
        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.shirt)
        self.assertTrue(result["recalculated"])

    def test_a_basemesh_that_was_already_selected_stays_selected(self) -> None:
        self.build_character(selected=True)

        self.run_set([self.change("age", "age", 1.0)], active=self.basemesh)

        self.assertTrue(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.basemesh)

    def test_the_previous_state_is_restored_even_when_the_refit_fails(self) -> None:
        self.build_character()
        StubHumanService.refit_raises = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            self.run_set([self.change("age", "age", 1.0)], refit=True, active=self.shirt)

        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.shirt)


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
