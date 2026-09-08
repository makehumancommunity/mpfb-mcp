# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_set_targets tool: per-entry argument validation, the
all-or-nothing resolution phase, and the write sequence itself.

Two layers, as established: the tool wrapper with send_code mocked, then the
assembled source - shared fragment included - executed against the stub scene
and the real temporary target tree in tests/blender_stubs.py. The tree is real
because most of what this payload does is decide *which file* a change would
have to load, and from where.

The stubs reproduce the three quirks the payload exists to work around, and none
of them can be observed if the stub is helpful instead: set_target_value() is a
silent no-op for a name that is not on the mesh, get_target_value() returns 0.0
for one, and a shape key value is clamped to 0.0-1.0 on assignment. A negative
modifier value therefore has to be expressed as the opposing target at a
positive weight, or it fails here rather than in Blender.

Run with::

    python -m unittest tests.test_set_targets -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import set_targets

from tests.blender_stubs import (
    DetailTargetTestCase, LONG_USER_TARGET, StubHumanService, StubObject,
    StubObjectService, StubTargetService)

_ENCODED_LONG_NAME = "$yn-$fe-$av-$ca-$un-$pr-$wg-$hg-experiment"


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_targets.register(mcp)
    return mcp._tool_manager._tools["mpfb_set_targets"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Entry *shape* checked here; section and category vocabulary is not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_default_call_sends_the_documented_defaults(self):
        with mock.patch.object(set_targets, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        source = send_code.call_args[0][0]
        self.assertIn("# --- payload: set_targets.py ---", source)
        self.assertIn("# --- shared: target_categories.py ---", source)
        self.assertIn(json.dumps({
            "name": None, "modifiers": [], "targets": [],
            "symmetry": False, "prune": True, "refit": False}), source)

    def test_entries_are_normalized_before_they_cross_the_socket(self):
        # An omitted side arrives as an explicit null, and an int value as a
        # float, so the payload never has to guess what a missing key meant.
        with mock.patch.object(set_targets, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(modifiers=[{"section": "nose", "category": "c", "value": 1}],
                      targets=[{"shapekey_name": "vwide", "value": 0}])
        self.assertIn(json.dumps({
            "name": None,
            "modifiers": [{"section": "nose", "category": "c", "value": 1.0, "side": None}],
            "targets": [{"shapekey_name": "vwide", "value": 0.0}],
            "symmetry": False, "prune": True, "refit": False}),
            send_code.call_args[0][0])

    def test_response_envelope_is_returned_unchanged(self):
        envelope = {"status": "error", "message": "no MPFB"}
        with mock.patch.object(set_targets, "send_code") as send_code:
            send_code.return_value = envelope
            self.assertIs(self.tool(), envelope)

    def test_strict_json_is_requested(self):
        with mock.patch.object(set_targets, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertIs(send_code.call_args[1]["strict_json"], True)

    def test_a_bad_name_is_rejected_locally(self):
        for bad in (1, True, [], object(), "", "   "):
            with self.subTest(value=bad):
                with mock.patch.object(set_targets, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad)
                send_code.assert_not_called()

    def test_flags_must_be_real_bools(self):
        for argument in ("symmetry", "prune", "refit"):
            for bad in ("false", "true", 0, 1, None):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(set_targets, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_code.assert_not_called()

    def test_a_list_argument_must_be_a_list_of_objects(self):
        for bad in ("modifiers", {"section": "nose"}, 3, [1], ["x"], [None]):
            with self.subTest(value=bad):
                with mock.patch.object(set_targets, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(modifiers=bad)
                send_code.assert_not_called()

    def test_an_unknown_key_in_an_entry_is_rejected_locally(self):
        # A misspelled key is the commonest way a caller gets a dict-shaped
        # argument wrong, and it is silent unless it is checked.
        with mock.patch.object(set_targets, "send_code") as send_code:
            with self.assertRaises(ValueError) as raised:
                self.tool(modifiers=[
                    {"section": "nose", "catagory": "c", "value": 0.1}])
        send_code.assert_not_called()
        self.assertIn("catagory", str(raised.exception))

    def test_the_error_names_the_offending_entry_by_position(self):
        with self.assertRaises(ValueError) as raised:
            self.tool(modifiers=[
                {"section": "nose", "category": "c", "value": 0.1},
                {"section": "nose", "category": "c", "value": 5.0}])

        self.assertIn("modifiers[1]", str(raised.exception))

    def test_a_modifier_value_must_be_a_number_in_minus_one_to_one(self):
        for bad in (True, False, "0.5", None, 1.5, -1.5, [0.5]):
            with self.subTest(value=bad):
                with mock.patch.object(set_targets, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(modifiers=[
                            {"section": "nose", "category": "c", "value": bad}])
                send_code.assert_not_called()

    def test_a_raw_target_value_must_be_a_number_in_zero_to_one(self):
        # Narrower than a modifier's on purpose: Blender clamps a shape key
        # value to 0.0-1.0, so a negative here would silently store 0.0.
        for bad in (-0.4, 1.5, True, "0.5", None):
            with self.subTest(value=bad):
                with mock.patch.object(set_targets, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(targets=[{"shapekey_name": "x", "value": bad}])
                send_code.assert_not_called()

    def test_a_side_must_be_one_of_three_strings_or_omitted(self):
        for bad in ("l", "Left", 1, True, ""):
            with self.subTest(value=bad):
                with mock.patch.object(set_targets, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(modifiers=[
                            {"section": "nose", "category": "c", "value": 0.1, "side": bad}])
                send_code.assert_not_called()

    def test_empty_entry_strings_are_rejected_locally(self):
        with mock.patch.object(set_targets, "send_code") as send_code:
            with self.assertRaises(ValueError):
                self.tool(modifiers=[{"section": "  ", "category": "c", "value": 0.1}])
            with self.assertRaises(ValueError):
                self.tool(targets=[{"shapekey_name": "", "value": 0.1}])
        send_code.assert_not_called()

    def test_a_batch_above_the_ceiling_is_rejected_locally(self):
        entries = [{"section": "nose", "category": "c", "value": 0.1}] * (
            set_targets.MAX_ENTRIES + 1)
        with mock.patch.object(set_targets, "send_code") as send_code:
            with self.assertRaises(ValueError):
                self.tool(modifiers=entries)
        send_code.assert_not_called()

    def test_an_unknown_section_or_category_is_not_rejected_locally(self):
        # Half the sections are synthesized from the user's own directories, so
        # a vocabulary kept here could not be right even in principle.
        with mock.patch.object(set_targets, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(modifiers=[
                {"section": "no-such-section", "category": "no-such-category",
                 "value": 0.5}])
        send_code.assert_called_once()


class GeneratedSetTargetsTests(DetailTargetTestCase):
    """The payload, run against a real target tree and the stub scene."""

    def run_set(self, modifiers=(), targets=(), name="Human", symmetry=False,
                prune=True, refit=False, active=None):
        return self.run_payload(
            "set_targets.py",
            {"name": name, "modifiers": list(modifiers), "targets": list(targets),
             "symmetry": symmetry, "prune": prune, "refit": refit},
            scene_objects=self.objects, active=active,
            shared=["target_categories.py", "performed.py"])

    @staticmethod
    def modifier(section, category, value, side=None):
        return {"section": section, "category": category, "value": value, "side": side}

    def error(self, result, reason):
        for entry in result["resolution_errors"]:
            if entry["reason"] == reason:
                return entry
        self.fail("no resolution error " + repr(reason) + " in " + repr(
            [entry["reason"] for entry in result["resolution_errors"]]))

    def touched(self, result, index=0):
        return {entry["target"]: entry for entry in result["applied"][index]["targets"]}

    # -- subject resolution and preconditions --------------------------------

    def test_the_basemesh_is_found_from_a_garment(self):
        self.build_character()

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)], name="Shirt")

        self.assertTrue(result["found"])
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertEqual(result["subject_resolved_by"], "name")

    def test_no_active_object_is_an_answer_rather_than_a_crash(self):
        self.build_character()

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)],
                              name=None, active=None)

        self.assertFalse(result["found"])
        self.assertEqual(result["applied"], [])

    def test_an_unrelated_object_is_an_answer(self):
        self.build_character()
        self.objects.append(StubObject("Cube"))

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)], name="Cube")

        self.assertFalse(result["found"])
        self.assertIn("no MakeHuman basemesh", result["message"])

    def test_edit_mode_is_an_answer_and_nothing_is_written(self):
        # TargetService.create_shape_key() opens with a bare assert on this.
        self.build_character(mode="EDIT")

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)])

        self.assertTrue(result["found"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(result["applied"], [])
        self.assertEqual(StubTargetService.load_calls, [])

    def test_a_basemesh_without_shape_keys_is_an_answer(self):
        self.build_character(shapekeys=None)

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)])

        self.assertEqual(result["blocked_by"], "no_shapekeys")
        self.assertEqual(result["applied"], [])

    def test_a_call_naming_nothing_does_nothing(self):
        self.build_character()

        result = self.run_set()

        self.assertTrue(result["ready"])
        self.assertEqual(result["applied"], [])
        self.assertEqual(result["resolution_errors"], [])
        self.assertIn("Neither 'modifiers' nor 'targets'", result["message"])
        self.assertEqual(StubTargetService.load_calls, [])

    # -- the opposed-category write sequence ---------------------------------

    def test_a_positive_value_loads_the_positive_target(self):
        self.build_character()

        result = self.run_set([
            self.modifier("nose", "nose-scale-depth-decr-incr", 0.6)])

        self.assertEqual(self.shapekey_values()["nose-scale-depth-incr"], 0.6)
        touched = self.touched(result)
        self.assertEqual(touched["nose-scale-depth-incr"]["polarity"], "positive")
        self.assertFalse(touched["nose-scale-depth-incr"]["present_before"])
        self.assertTrue(touched["nose-scale-depth-incr"]["loaded_from"].endswith(
            "nose-scale-depth-incr.target.gz"))

    def test_a_negative_value_loads_the_negative_target_at_a_positive_weight(self):
        # The whole reason the category level exists: Blender clamps a shape key
        # to 0.0-1.0, so -0.4 has no representation except decr at 0.4.
        self.build_character()

        self.run_set([self.modifier("nose", "nose-scale-depth-decr-incr", -0.4)])

        self.assertEqual(self.shapekey_values()["nose-scale-depth-decr"], 0.4)
        self.assertNotIn("nose-scale-depth-incr", self.shapekey_values())

    def test_going_positive_clears_the_negative_target_first(self):
        self.build_character(shapekeys=[("Basis", 0.0), ("nose-scale-depth-decr", 0.5)])

        result = self.run_set([
            self.modifier("nose", "nose-scale-depth-decr-incr", 0.3)])

        self.assertEqual(self.shapekey_values()["nose-scale-depth-incr"], 0.3)
        # Pruned away, because it was driven to zero before the other was set.
        self.assertNotIn("nose-scale-depth-decr", self.shapekey_values())
        touched = self.touched(result)
        self.assertEqual(touched["nose-scale-depth-decr"]["previous_value"], 0.5)
        self.assertTrue(touched["nose-scale-depth-decr"]["pruned"])

    def test_going_negative_clears_the_positive_target_first(self):
        self.build_character(shapekeys=[("Basis", 0.0), ("nose-scale-depth-incr", 0.5)])

        self.run_set([self.modifier("nose", "nose-scale-depth-decr-incr", -0.3)])

        self.assertEqual(self.shapekey_values()["nose-scale-depth-decr"], 0.3)
        self.assertNotIn("nose-scale-depth-incr", self.shapekey_values())

    def test_a_value_at_zero_clears_both_halves(self):
        self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("nose-scale-depth-incr", 0.5),
            ("nose-scale-depth-decr", 0.2),
        ])

        self.run_set([self.modifier("nose", "nose-scale-depth-decr-incr", 0.0)])

        self.assertEqual(list(self.shapekey_values()), ["Basis"])

    def test_an_existing_target_is_set_rather_than_reloaded(self):
        # set_target_value() is a silent no-op for an absent name, so the
        # payload checks presence first - and must not then load what is there.
        self.build_character(shapekeys=[("Basis", 0.0), ("nose-scale-depth-incr", 0.2)])

        result = self.run_set([
            self.modifier("nose", "nose-scale-depth-decr-incr", 0.9)])

        self.assertEqual(self.shapekey_values()["nose-scale-depth-incr"], 0.9)
        self.assertEqual(StubTargetService.load_calls, [])
        touched = self.touched(result)
        self.assertTrue(touched["nose-scale-depth-incr"]["present_before"])
        self.assertEqual(touched["nose-scale-depth-incr"]["previous_value"], 0.2)
        self.assertEqual(touched["nose-scale-depth-incr"]["new_value"], 0.9)
        self.assertIsNone(touched["nose-scale-depth-incr"]["loaded_from"])

    def test_a_target_that_ships_uncompressed_is_still_found(self):
        # _set_opposed_modifier_value() builds ".target.gz" only and would hand
        # a non-existent path to load_target(), which raises IOError.
        self.build_character()

        result = self.run_set([self.modifier("arms", "upperarm-fat-decr-incr", 0.5)])

        self.assertEqual(result["resolution_errors"], [])
        self.assertEqual(self.shapekey_values()["upperarm-fat-incr"], 0.5)
        self.assertTrue(self.touched(result)["upperarm-fat-incr"]["loaded_from"].endswith(
            "upperarm-fat-incr.target"))

    # -- simple categories ----------------------------------------------------

    def test_a_category_without_opposites_takes_a_single_target(self):
        self.build_character()

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.8)])

        self.assertEqual(self.shapekey_values()["chin-triangle"], 0.8)
        self.assertFalse(result["applied"][0]["opposed"])

    def test_a_simple_category_rejects_a_negative_value(self):
        # -1.0..+1.0 passes the local check, since some categories are pairs;
        # this one is not, and the narrower range is enforced inside Blender.
        self.build_character()

        result = self.run_set([self.modifier("chin", "chin-triangle", -0.5)])

        error = self.error(result, "value_out_of_range")
        self.assertEqual(error["category"], "chin-triangle")
        self.assertIn("no opposite", error["message"])
        self.assertEqual(result["applied"], [])

    # -- sides and symmetry ---------------------------------------------------

    def test_a_sided_category_requires_a_side(self):
        self.build_character()

        result = self.run_set([
            self.modifier("arms", "lowerarm-scale-depth-decr-incr", 0.5)])

        self.assertEqual(self.error(result, "side_required")["category"],
                         "lowerarm-scale-depth-decr-incr")
        self.assertEqual(result["applied"], [])
        self.assertEqual(StubTargetService.load_calls, [])

    def test_unsided_is_not_accepted_as_a_side_for_a_sided_category(self):
        self.build_character()

        result = self.run_set([
            self.modifier("arms", "lowerarm-scale-depth-decr-incr", 0.5, side="unsided")])

        self.assertEqual(self.error(result, "side_required")["reason"], "side_required")

    def test_an_unsided_category_rejects_a_side(self):
        self.build_character()

        result = self.run_set([
            self.modifier("nose", "nose-scale-depth-decr-incr", 0.5, side="left")])

        self.assertEqual(self.error(result, "side_not_applicable")["category"],
                         "nose-scale-depth-decr-incr")

    def test_a_sided_change_touches_only_that_side_by_default(self):
        self.build_character()

        result = self.run_set([
            self.modifier("arms", "lowerarm-scale-depth-decr-incr", 0.5, side="left")])

        self.assertEqual(list(self.shapekey_values()),
                         ["Basis", "l-lowerarm-scale-depth-incr"])
        self.assertFalse(result["applied"][0]["symmetry_applied"])

    def test_symmetry_mirrors_a_sided_change_onto_the_other_side(self):
        self.build_character()

        result = self.run_set(
            [self.modifier("arms", "lowerarm-scale-depth-decr-incr", 0.5, side="left")],
            symmetry=True)

        values = self.shapekey_values()
        self.assertEqual(values["l-lowerarm-scale-depth-incr"], 0.5)
        self.assertEqual(values["r-lowerarm-scale-depth-incr"], 0.5)
        self.assertTrue(result["applied"][0]["symmetry_applied"])

    def test_symmetry_on_a_sided_category_can_touch_all_four_targets(self):
        # The case the per-entry report has to be able to describe: both
        # opposing halves on both sides.
        self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("l-lowerarm-scale-depth-incr", 0.1),
            ("l-lowerarm-scale-depth-decr", 0.2),
            ("r-lowerarm-scale-depth-incr", 0.3),
            ("r-lowerarm-scale-depth-decr", 0.4),
        ])

        result = self.run_set(
            [self.modifier("arms", "lowerarm-scale-depth-decr-incr", 0.5, side="right")],
            symmetry=True, prune=False)

        self.assertEqual(len(result["applied"][0]["targets"]), 4)
        values = self.shapekey_values()
        self.assertEqual(values["l-lowerarm-scale-depth-incr"], 0.5)
        self.assertEqual(values["r-lowerarm-scale-depth-incr"], 0.5)
        self.assertEqual(values["l-lowerarm-scale-depth-decr"], 0.0)
        self.assertEqual(values["r-lowerarm-scale-depth-decr"], 0.0)

    def test_symmetry_does_nothing_to_an_unsided_category(self):
        self.build_character()

        result = self.run_set(
            [self.modifier("nose", "nose-scale-depth-decr-incr", 0.5)], symmetry=True)

        self.assertEqual(len(result["applied"][0]["targets"]), 1)
        self.assertFalse(result["applied"][0]["symmetry_applied"])

    def test_a_missing_target_file_is_a_resolution_error(self):
        # The "ears" category is sided but only its left-hand files exist.
        self.build_character()

        result = self.run_set([
            self.modifier("ears", "ear-lobe-decr-incr", 0.5, side="right")])

        self.assertEqual(self.error(result, "target_file_not_found")["category"],
                         "ear-lobe-decr-incr")
        self.assertEqual(result["applied"], [])

    # -- unknown names --------------------------------------------------------

    def test_an_unknown_section_comes_back_with_the_vocabulary(self):
        self.build_character()

        result = self.run_set([self.modifier("nsoe", "whatever", 0.5)])

        error = self.error(result, "unknown_section")
        self.assertIn("nose", error["known_sections"])
        self.assertIn("animal", error["known_sections"])

    def test_an_unknown_category_comes_back_with_that_sections_vocabulary(self):
        # Scoped to what the caller got wrong rather than the whole table.
        self.build_character()

        result = self.run_set([self.modifier("nose", "nose-scale-depth", 0.5)])

        error = self.error(result, "unknown_category")
        self.assertEqual(error["known_categories_in_section"],
                         {"nose": ["nose-scale-depth-decr-incr"]})

    def test_a_section_name_is_matched_case_insensitively(self):
        self.build_character()

        result = self.run_set([self.modifier("NOSE", "Nose-Scale-Depth-Decr-Incr", 0.5)])

        self.assertEqual(result["resolution_errors"], [])
        self.assertEqual(result["applied"][0]["section"], "nose")

    # -- all or nothing -------------------------------------------------------

    def test_one_bad_entry_in_a_batch_applies_none_of_them(self):
        self.build_character()

        result = self.run_set([
            self.modifier("nose", "nose-scale-depth-decr-incr", 0.5),
            self.modifier("chin", "chin-triangle", 0.5),
            self.modifier("nose", "no-such-category", 0.5),
        ])

        self.assertEqual(result["applied"], [])
        self.assertEqual(list(self.shapekey_values()), ["Basis"])
        self.assertEqual(StubTargetService.load_calls, [])
        self.assertEqual(StubTargetService.set_calls, [])
        self.assertIn("nothing at all was applied", result["message"])

    def test_every_bad_entry_is_reported_not_just_the_first(self):
        self.build_character()

        result = self.run_set([
            self.modifier("nope", "x", 0.5),
            self.modifier("nose", "no-such-category", 0.5),
        ])

        self.assertEqual(
            sorted(entry["reason"] for entry in result["resolution_errors"]),
            ["unknown_category", "unknown_section"])

    def test_a_resolution_error_carries_the_index_of_the_entry(self):
        self.build_character()

        result = self.run_set([
            self.modifier("chin", "chin-triangle", 0.5),
            self.modifier("nope", "x", 0.5),
        ])

        self.assertEqual(result["resolution_errors"][0]["index"], 1)

    def test_a_bad_raw_target_also_stops_the_whole_batch(self):
        self.build_character()

        result = self.run_set(
            [self.modifier("chin", "chin-triangle", 0.5)],
            [{"shapekey_name": "no_such_target", "value": 0.5}])

        self.assertEqual(result["applied"], [])
        self.assertEqual(list(self.shapekey_values()), ["Basis"])
        self.assertEqual(self.error(result, "unknown_target")["shapekey_name"],
                         "no_such_target")

    def test_a_whole_batch_applies_in_request_order(self):
        self.build_character()

        result = self.run_set([
            self.modifier("chin", "chin-triangle", 0.5),
            self.modifier("nose", "nose-scale-depth-decr-incr", -0.5),
            self.modifier("arms", "lowerarm-scale-depth-decr-incr", 0.5, side="left"),
        ])

        self.assertEqual([entry["category"] for entry in result["applied"]], [
            "chin-triangle", "nose-scale-depth-decr-incr",
            "lowerarm-scale-depth-decr-incr"])
        self.assertEqual([entry["index"] for entry in result["applied"]], [0, 1, 2])

    # -- the raw shape-key level ---------------------------------------------

    def test_a_raw_target_already_on_the_mesh_is_set(self):
        self.build_character(shapekeys=[("Basis", 0.0), ("cat_ears", 0.1)])

        result = self.run_set(targets=[{"shapekey_name": "cat_ears", "value": 0.7}])

        self.assertEqual(self.shapekey_values()["cat_ears"], 0.7)
        self.assertEqual(StubTargetService.load_calls, [])
        self.assertEqual(self.touched(result)["cat_ears"]["previous_value"], 0.1)

    def test_a_raw_target_not_on_the_mesh_is_loaded_from_disk(self):
        self.build_character()

        result = self.run_set(targets=[{"shapekey_name": "cat_ears", "value": 0.7}])

        self.assertEqual(self.shapekey_values()["cat_ears"], 0.7)
        self.assertTrue(self.touched(result)["cat_ears"]["loaded_from"].endswith(
            "cat_ears.target"))
        self.assertEqual(result["applied"][0]["path_resolved_by"], "category_full_path")

    def test_an_encoded_user_target_is_addressed_by_its_encoded_name(self):
        # FR 006 proved live that the *filename* addresses nothing at all, and
        # does so silently. Both names resolve to the same file here.
        self.build_character()

        result = self.run_set(
            targets=[{"shapekey_name": _ENCODED_LONG_NAME, "value": 0.5}])

        self.assertEqual(result["resolution_errors"], [])
        self.assertEqual(self.shapekey_values()[_ENCODED_LONG_NAME], 0.5)

    def test_the_catalogue_name_of_a_long_target_also_resolves(self):
        self.build_character()

        result = self.run_set(targets=[{"shapekey_name": LONG_USER_TARGET, "value": 0.5}])

        self.assertEqual(result["resolution_errors"], [])

    def test_a_bundled_target_with_no_category_is_reachable_raw(self):
        # Nothing in the fixture's target.json names "chin-triangle" twice, so
        # the raw level goes through the category index rather than the
        # last-resort target_full_path() fallback.
        self.build_character()

        result = self.run_set(targets=[{"shapekey_name": "chin-triangle", "value": 0.4}])

        self.assertEqual(self.shapekey_values()["chin-triangle"], 0.4)
        self.assertEqual(result["applied"][0]["path_resolved_by"], "section_dir")

    # -- the gzipped-custom-target naming divergence -------------------------

    def test_a_gzipped_custom_target_keeps_mpfbs_own_name(self):
        # MPFB's category name is a substring replace that does not strip
        # ".gz", so the shape key its own slider expects is "vwide.gz" - while
        # mpfb_list_targets reports "vwide". Writing MPFB's name is what makes
        # the slider read the value back.
        self.build_character()

        result = self.run_set([self.modifier("custom", "vwide.gz", 0.5)])

        self.assertEqual(self.shapekey_values()["vwide.gz"], 0.5)
        self.assertTrue(result["applied"][0]["name_diverges_from_catalogue"])
        self.assertEqual(result["applied"][0]["catalogue_shapekey_name"], "vwide")
        self.assertIn("gzipped custom target", result["message"])

    def test_an_ordinary_custom_target_does_not_diverge(self):
        self.build_character()

        result = self.run_set([self.modifier("custom", "closed_eyes", 0.5)])

        self.assertFalse(result["applied"][0]["name_diverges_from_catalogue"])
        self.assertNotIn("gzipped custom target", result["message"])

    # -- pruning --------------------------------------------------------------

    def test_prune_removes_a_target_driven_to_zero(self):
        self.build_character(shapekeys=[("Basis", 0.0), ("chin-triangle", 0.5)])

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.0)])

        self.assertNotIn("chin-triangle", self.shapekey_values())
        self.assertTrue(self.touched(result)["chin-triangle"]["pruned"])
        self.assertEqual(result["shapekeys_removed"], ["chin-triangle"])

    def test_prune_false_keeps_a_zeroed_target(self):
        self.build_character(shapekeys=[("Basis", 0.0), ("chin-triangle", 0.5)])

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.0)], prune=False)

        self.assertEqual(self.shapekey_values()["chin-triangle"], 0.0)
        self.assertFalse(self.touched(result)["chin-triangle"]["pruned"])
        self.assertEqual(result["shapekeys_removed"], [])

    def test_added_shape_keys_are_reported(self):
        self.build_character()

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)])

        self.assertEqual(result["shapekeys_added"], ["chin-triangle"])
        self.assertEqual(result["shapekeys_before"], ["Basis"])

    # -- activation, restoration and refit ------------------------------------

    def test_the_basemesh_is_activated_and_the_previous_state_restored(self):
        self.build_character()

        self.run_set([self.modifier("chin", "chin-triangle", 0.5)], active=self.shirt)

        self.assertEqual(StubObjectService.activations, ["Human"])
        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.shirt)

    def test_a_basemesh_that_was_already_selected_stays_selected(self):
        self.build_character(selected=True)

        self.run_set([self.modifier("chin", "chin-triangle", 0.5)], active=self.basemesh)

        self.assertTrue(self.basemesh.select_get())

    def test_the_previous_state_is_restored_even_when_the_refit_fails(self):
        self.build_character()
        StubHumanService.refit_raises = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            self.run_set([self.modifier("chin", "chin-triangle", 0.5)],
                         refit=True, active=self.shirt)

        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.shirt)

    def test_nothing_is_refitted_by_default_and_the_response_says_so(self):
        self.build_character()

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)])

        self.assertFalse(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, [])
        self.assertEqual(result["assets_possibly_stale"]["mesh_assets"], ["Shirt"])
        self.assertTrue(result["assets_possibly_stale"]["rig_attached"])
        self.assertIn("Call mpfb_refit_human", result["message"])

    def test_a_requested_refit_is_performed_and_reported(self):
        self.build_character()

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)], refit=True)

        self.assertTrue(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, ["Human"])
        self.assertIsNone(result["assets_possibly_stale"])

    def test_a_generated_rigify_rig_without_a_metarig_is_reported(self):
        # HumanService.refit() reports this only through an operator an MCP tool
        # cannot give it: it refits the mesh assets and silently skips the rig.
        self.build_character()
        self.rig.rig_id = "generated"

        result = self.run_set([self.modifier("chin", "chin-triangle", 0.5)], refit=True)

        self.assertFalse(result["refit_performed"])
        self.assertIn("generated Rigify rig", result["refit_incomplete_reason"])
        self.assertEqual(StubHumanService.refit_calls, ["Human"])
        self.assertIsNotNone(result["assets_possibly_stale"])

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_is_true_only_when_something_was_applied(self):
        self.build_character()

        applied = self.run_set([self.modifier("chin", "chin-triangle", 0.5)])
        self.assertTrue(applied["applied"])
        self.assertIs(applied["performed"], True)

        # Named nothing: a ready: true answer that wrote nothing.
        nothing = self.run_set()
        self.assertTrue(nothing["ready"])
        self.assertIs(nothing["performed"], False)

        # One unresolvable entry fails the whole batch, so the answer is
        # ready: true with an empty "applied" - the case a flag read off
        # "ready" alone would get wrong.
        rejected = self.run_set([self.modifier("chin", "no-such-category", 0.5)])
        self.assertTrue(rejected["ready"])
        self.assertTrue(rejected["resolution_errors"])
        self.assertEqual(rejected["applied"], [])
        self.assertIs(rejected["performed"], False)


if __name__ == "__main__":
    unittest.main()
