# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_symmetrize_targets tool: argument validation, the dry run,
and the category walk that makes an asymmetric detail stack symmetric.

Two layers, as established: the tool wrapper with send_code mocked, then the
assembled source - shared fragment included - executed against the stub scene
and the real temporary target tree in tests/blender_stubs.py.

The operation has no MPFB equivalent - MPFB's own ``symmetry`` setting only
mirrors changes made while it is on - so there is nothing to compare against,
and what is under test is instead that the *pairing* comes from target.json's
opposites table rather than from matching ``l-``/``r-`` name prefixes, and that
a dry run reports exactly what a real run then does.

Run with::

    python -m unittest tests.test_symmetrize_targets -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import symmetrize_targets

from tests.blender_stubs import (
    DetailTargetTestCase, StubHumanService, StubObject, StubObjectService,
    StubTargetService)


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    symmetrize_targets.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_symmetrize_targets"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Shape checked here; the section vocabulary deliberately is not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_default_call_sends_the_documented_defaults(self):
        with mock.patch.object(symmetrize_targets, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(direction="left_to_right")
        source = send_code.call_args[0][0]
        self.assertIn("# --- payload: symmetrize_targets.py ---", source)
        self.assertIn("# --- shared: target_categories.py ---", source)
        self.assertIn(json.dumps({
            "name": None, "direction": "left_to_right", "section": None,
            "dry_run": False, "prune": True, "refit": False}), source)

    def test_direction_has_no_default(self):
        # Which half of a face is the good one is not something a tool can
        # guess, and guessing wrong destroys work.
        with self.assertRaises(TypeError):
            self.tool()

    def test_an_unknown_direction_is_rejected_locally(self):
        for bad in ("left", "LEFT_TO_RIGHT", "l2r", None, True, 1, ""):
            with self.subTest(value=bad):
                with mock.patch.object(symmetrize_targets, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(direction=bad)
                send_code.assert_not_called()

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(symmetrize_targets, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(direction="right_to_left", name="Human.rig", section="eyes",
                      dry_run=True, prune=False, refit=True)
        self.assertIn(json.dumps({
            "name": "Human.rig", "direction": "right_to_left", "section": "eyes",
            "dry_run": True, "prune": False, "refit": True}),
            send_code.call_args[0][0])

    def test_response_envelope_is_returned_unchanged(self):
        envelope = {"status": "error", "message": "no MPFB"}
        with mock.patch.object(symmetrize_targets, "send_code") as send_code:
            send_code.return_value = envelope
            self.assertIs(self.tool(direction="left_to_right"), envelope)

    def test_strict_json_is_requested(self):
        with mock.patch.object(symmetrize_targets, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(direction="left_to_right")
        self.assertIs(send_code.call_args[1]["strict_json"], True)

    def test_non_string_or_empty_text_arguments_are_rejected_locally(self):
        for argument in ("name", "section"):
            for bad in (1, True, [], object(), "", "   "):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(symmetrize_targets, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(direction="left_to_right", **{argument: bad})
                    send_code.assert_not_called()

    def test_flags_must_be_real_bools(self):
        # dry_run="false" would otherwise write.
        for argument in ("dry_run", "prune", "refit"):
            for bad in ("false", "true", 0, 1, None):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(symmetrize_targets, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(direction="left_to_right", **{argument: bad})
                    send_code.assert_not_called()

    def test_an_unknown_section_is_not_rejected_locally(self):
        with mock.patch.object(symmetrize_targets, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(direction="left_to_right", section="no-such-section")
        send_code.assert_called_once()


class GeneratedSymmetrizeTargetsTests(DetailTargetTestCase):
    """The payload, run against a real target tree and the stub scene."""

    def run_symmetrize(self, direction="left_to_right", name="Human", section=None,
                       dry_run=False, prune=True, refit=False, active=None):
        return self.run_payload(
            "symmetrize_targets.py",
            {"name": name, "direction": direction, "section": section,
             "dry_run": dry_run, "prune": prune, "refit": refit},
            scene_objects=self.objects, active=active,
            shared=["target_categories.py"])

    def asymmetric_character(self):
        """Left arm at +0.4, right arm at -0.25, plus an unsided target."""
        return self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("l-lowerarm-scale-depth-incr", 0.4),
            ("r-lowerarm-scale-depth-decr", 0.25),
            ("nose-scale-depth-incr", 0.7),
        ])

    def changed(self, result, category):
        for entry in result["changed"]:
            if entry["category"] == category:
                return entry
        self.fail("no changed category " + repr(category) + " in " + repr(
            [entry["category"] for entry in result["changed"]]))

    # -- subject resolution and preconditions --------------------------------

    def test_the_basemesh_is_found_from_a_garment(self):
        self.asymmetric_character()

        result = self.run_symmetrize(name="Shirt")

        self.assertTrue(result["found"])
        self.assertEqual(result["basemesh_name"], "Human")

    def test_an_unrelated_object_is_an_answer(self):
        self.asymmetric_character()
        self.objects.append(StubObject("Cube"))

        result = self.run_symmetrize(name="Cube")

        self.assertFalse(result["found"])
        self.assertEqual(result["changed"], [])

    def test_edit_mode_is_an_answer_and_nothing_is_written(self):
        self.asymmetric_character()
        self.basemesh.mode = "EDIT"

        result = self.run_symmetrize()

        self.assertFalse(result["ready"])
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(result["changed"], [])
        self.assertEqual(StubTargetService.load_calls, [])

    def test_a_basemesh_without_shape_keys_is_an_answer(self):
        self.build_character(shapekeys=None)

        result = self.run_symmetrize()

        self.assertEqual(result["blocked_by"], "no_shapekeys")

    def test_an_unknown_section_is_an_answer_carrying_the_vocabulary(self):
        self.asymmetric_character()

        result = self.run_symmetrize(section="nsoe")

        self.assertFalse(result["ready"])
        self.assertEqual(result["blocked_by"], "unknown_section")
        self.assertFalse(result["section_recognized"])
        self.assertIn("nose", result["known_sections"])
        self.assertEqual(self.shapekey_values()["l-lowerarm-scale-depth-incr"], 0.4)

    # -- the dry run ----------------------------------------------------------

    def test_a_dry_run_writes_nothing(self):
        self.asymmetric_character()
        before = dict(self.shapekey_values())

        result = self.run_symmetrize(dry_run=True)

        self.assertEqual(self.shapekey_values(), before)
        self.assertEqual(StubTargetService.load_calls, [])
        self.assertEqual(StubTargetService.set_calls, [])
        self.assertEqual(StubObjectService.activations, [])
        self.assertIn("Nothing was written", result["message"])

    def test_a_dry_run_reports_the_same_changes_the_real_run_makes(self):
        self.asymmetric_character()
        dry = self.run_symmetrize(dry_run=True)

        real = self.run_symmetrize()

        self.assertEqual(
            [(entry["section"], entry["category"], entry["source_value"],
              entry["destination_value_before"], entry["destination_value_after"])
             for entry in dry["changed"]],
            [(entry["section"], entry["category"], entry["source_value"],
              entry["destination_value_before"], entry["destination_value_after"])
             for entry in real["changed"]])

    def test_a_dry_run_reports_no_stale_assets(self):
        self.asymmetric_character()

        self.assertIsNone(self.run_symmetrize(dry_run=True)["assets_possibly_stale"])

    # -- the mirroring itself -------------------------------------------------

    def test_left_is_copied_onto_right(self):
        self.asymmetric_character()

        result = self.run_symmetrize(direction="left_to_right")

        values = self.shapekey_values()
        self.assertEqual(values["l-lowerarm-scale-depth-incr"], 0.4)
        self.assertEqual(values["r-lowerarm-scale-depth-incr"], 0.4)
        # The right side's opposing half was cleared before the other was set.
        self.assertNotIn("r-lowerarm-scale-depth-decr", values)
        entry = self.changed(result, "lowerarm-scale-depth-decr-incr")
        self.assertEqual(entry["source_side"], "left")
        self.assertEqual(entry["destination_side"], "right")
        self.assertEqual(entry["source_value"], 0.4)
        self.assertEqual(entry["destination_value_before"], -0.25)
        self.assertEqual(entry["destination_value_after"], 0.4)

    def test_right_is_copied_onto_left(self):
        self.asymmetric_character()

        self.run_symmetrize(direction="right_to_left")

        values = self.shapekey_values()
        self.assertEqual(values["r-lowerarm-scale-depth-decr"], 0.25)
        self.assertEqual(values["l-lowerarm-scale-depth-decr"], 0.25)
        self.assertNotIn("l-lowerarm-scale-depth-incr", values)

    def test_the_result_is_symmetric_and_a_second_run_changes_nothing(self):
        self.asymmetric_character()

        self.run_symmetrize()
        again = self.run_symmetrize()

        self.assertEqual(again["changed"], [])
        self.assertEqual(again["changed_count"], 0)

    def test_a_side_at_zero_is_copied_as_zero(self):
        # The destructive case: an untouched left side flattens a deliberately
        # modelled right one. It is reported entry by entry, which is what the
        # dry run exists to show first.
        self.build_character(shapekeys=[
            ("Basis", 0.0), ("r-lowerarm-scale-depth-incr", 0.6)])

        result = self.run_symmetrize(direction="left_to_right")

        self.assertEqual(list(self.shapekey_values()), ["Basis"])
        self.assertEqual(
            self.changed(result, "lowerarm-scale-depth-decr-incr")["source_value"], 0.0)

    def test_an_already_symmetric_category_is_reported_and_left_alone(self):
        self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("l-lowerarm-scale-depth-incr", 0.4),
            ("r-lowerarm-scale-depth-incr", 0.4),
        ])

        result = self.run_symmetrize()

        self.assertEqual(result["changed"], [])
        categories = [entry["category"] for entry in result["already_symmetric"]]
        self.assertIn("lowerarm-scale-depth-decr-incr", categories)
        self.assertEqual(StubTargetService.set_calls, [])

    def test_an_unsided_category_is_never_touched(self):
        self.asymmetric_character()

        result = self.run_symmetrize()

        for group in ("changed", "already_symmetric", "skipped"):
            categories = [entry["category"] for entry in result[group]]
            self.assertNotIn("nose-scale-depth-decr-incr", categories)
            self.assertNotIn("chin-triangle", categories)
        # And its value is untouched.
        self.assertEqual(self.shapekey_values()["nose-scale-depth-incr"], 0.7)

    def test_a_category_whose_file_is_missing_is_skipped_not_fatal(self):
        # The "ears" category is sided but only its left-hand files exist. The
        # rest of the body must still be symmetrized.
        self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("l-ear-lobe-incr", 0.3),
            ("l-lowerarm-scale-depth-incr", 0.4),
        ])

        result = self.run_symmetrize()

        skipped = result["skipped"]
        self.assertEqual([entry["category"] for entry in skipped], ["ear-lobe-decr-incr"])
        self.assertEqual(skipped[0]["reason"], "target_file_not_found")
        self.assertEqual(self.shapekey_values()["r-lowerarm-scale-depth-incr"], 0.4)
        self.assertIn("were skipped", result["message"])

    # -- the section filter ---------------------------------------------------

    def test_a_section_filter_restricts_the_walk(self):
        self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("l-lowerarm-scale-depth-incr", 0.4),
            ("l-ear-lobe-incr", 0.3),
        ])

        result = self.run_symmetrize(section="arms")

        self.assertEqual([entry["section"] for entry in result["changed"]], ["arms"])
        self.assertEqual(result["skipped"], [])
        self.assertNotIn("r-ear-lobe-incr", self.shapekey_values())

    def test_a_section_name_is_matched_case_insensitively(self):
        self.asymmetric_character()

        result = self.run_symmetrize(section="ARMS")

        self.assertTrue(result["section_recognized"])
        self.assertEqual(result["changed_count"], 1)

    # -- pruning, activation and refit ---------------------------------------

    def test_prune_false_keeps_a_zeroed_target(self):
        self.asymmetric_character()

        self.run_symmetrize(prune=False)

        self.assertEqual(self.shapekey_values()["r-lowerarm-scale-depth-decr"], 0.0)

    def test_removed_and_added_shape_keys_are_reported(self):
        self.asymmetric_character()

        result = self.run_symmetrize()

        self.assertEqual(result["shapekeys_removed"], ["r-lowerarm-scale-depth-decr"])
        self.assertEqual(result["shapekeys_added"], ["r-lowerarm-scale-depth-incr"])

    def test_the_basemesh_is_activated_and_the_previous_state_restored(self):
        self.asymmetric_character()

        self.run_symmetrize(active=self.shirt)

        self.assertEqual(StubObjectService.activations, ["Human"])
        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.shirt)

    def test_the_previous_state_is_restored_even_when_the_refit_fails(self):
        self.asymmetric_character()
        StubHumanService.refit_raises = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            self.run_symmetrize(refit=True, active=self.shirt)

        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.shirt)

    def test_nothing_is_refitted_by_default_and_the_response_says_so(self):
        self.asymmetric_character()

        result = self.run_symmetrize()

        self.assertFalse(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, [])
        self.assertEqual(result["assets_possibly_stale"]["mesh_assets"], ["Shirt"])
        self.assertIn("Call mpfb_refit_human", result["message"])

    def test_a_requested_refit_is_performed_and_reported(self):
        self.asymmetric_character()

        result = self.run_symmetrize(refit=True)

        self.assertTrue(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, ["Human"])

    def test_a_generated_rigify_rig_without_a_metarig_is_reported(self):
        self.asymmetric_character()
        self.rig.rig_id = "generated"

        result = self.run_symmetrize(refit=True)

        self.assertFalse(result["refit_performed"])
        self.assertIn("generated Rigify rig", result["refit_incomplete_reason"])

    def test_a_character_that_needs_no_change_is_not_refitted(self):
        # Nothing moved, so nothing is stale - and refit() is not called for
        # the sake of it.
        self.build_character(shapekeys=[("Basis", 0.0), ("nose-scale-depth-incr", 0.5)])

        result = self.run_symmetrize(refit=True)

        self.assertEqual(result["changed"], [])
        self.assertEqual(StubHumanService.refit_calls, [])
        self.assertFalse(result["refit_performed"])
        self.assertIsNone(result["assets_possibly_stale"])
        self.assertIn("No refit was needed", result["message"])


if __name__ == "__main__":
    unittest.main()
