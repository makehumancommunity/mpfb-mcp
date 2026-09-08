# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_get_target_stack tool: argument validation, and the
generated code's two views of a character's shape keys.

Two layers, as established: the tool wrapper with send_code mocked, then the
assembled source - shared fragment included, so what runs here is the same
program the tool sends - executed against the stub scene and the real temporary
target tree in tests/blender_stubs.py.

What the second layer is really testing is the *reverse* mapping. A shape key
carries no metadata at all, so placing "r-lowerarm-scale-depth-decr" back into
its category, side and polarity means rebuilding MPFB's category table and
looking the name up in it - and rolling the stack up into modifier values means
reproducing _get_opposed_modifier_value(), including its rule that the positive
target wins and the negative one is reported negated.

Run with::

    python -m unittest tests.test_get_target_stack -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import get_target_stack

from tests.blender_stubs import DetailTargetTestCase, LONG_USER_TARGET, StubObject


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    get_target_stack.register(mcp)
    return mcp._tool_manager._tools["mpfb_get_target_stack"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape checked here, vocabulary deliberately not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_default_call_sends_the_documented_defaults(self):
        with mock.patch.object(get_target_stack, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        source = send_code.call_args[0][0]
        self.assertIn("# --- payload: get_target_stack.py ---", source)
        self.assertIn(json.dumps({
            "name": None, "include_macro": False, "include_expressions": False,
            "name_contains": None, "limit": 200, "offset": 0}), source)

    def test_the_shared_category_table_is_assembled_in(self):
        # Without it the payload cannot place a shape key back into a category,
        # and would fail on an undefined name rather than answer wrongly.
        with mock.patch.object(get_target_stack, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertIn("# --- shared: target_categories.py ---", send_code.call_args[0][0])

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(get_target_stack, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.rig", include_macro=True, include_expressions=True,
                      name_contains="nose", limit=5, offset=10)
        self.assertIn(json.dumps({
            "name": "Human.rig", "include_macro": True, "include_expressions": True,
            "name_contains": "nose", "limit": 5, "offset": 10}),
            send_code.call_args[0][0])

    def test_response_envelope_is_returned_unchanged(self):
        envelope = {"status": "error", "message": "no MPFB"}
        with mock.patch.object(get_target_stack, "send_code") as send_code:
            send_code.return_value = envelope
            self.assertIs(self.tool(), envelope)

    def test_strict_json_is_requested(self):
        with mock.patch.object(get_target_stack, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertIs(send_code.call_args[1]["strict_json"], True)

    def test_non_string_or_empty_text_arguments_are_rejected_locally(self):
        for argument in ("name", "name_contains"):
            for bad in (1, True, [], object(), "", "   ", "\t"):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(get_target_stack, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_code.assert_not_called()

    def test_flags_must_be_real_bools(self):
        # Not truthiness: include_macro="false" would otherwise return the macro
        # stack the caller was trying to exclude.
        for argument in ("include_macro", "include_expressions"):
            for bad in ("false", "true", 0, 1, None, []):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(get_target_stack, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_code.assert_not_called()

    def test_bad_limit_and_offset_are_rejected_locally(self):
        for bad in (True, False, -1, "10", 1.5, None):
            for argument in ("limit", "offset"):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(get_target_stack, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_code.assert_not_called()

    def test_limit_above_the_ceiling_is_rejected_locally(self):
        with mock.patch.object(get_target_stack, "send_code") as send_code:
            with self.assertRaises(ValueError):
                self.tool(limit=get_target_stack.MAX_LIMIT + 1)
        send_code.assert_not_called()


class GeneratedGetTargetStackTests(DetailTargetTestCase):
    """The payload, run against a real target tree and the stub scene."""

    def run_stack(self, name="Human", include_macro=False, include_expressions=False,
                  name_contains=None, limit=200, offset=0, active=None):
        return self.run_payload(
            "get_target_stack.py",
            {"name": name, "include_macro": include_macro,
             "include_expressions": include_expressions, "name_contains": name_contains,
             "limit": limit, "offset": offset},
            scene_objects=self.objects, active=active,
            shared=["target_categories.py", "modifier_reading.py"])

    def entry(self, result, shapekey_name):
        for entry in result["targets"]:
            if entry["shapekey_name"] == shapekey_name:
                return entry
        self.fail("no target called " + repr(shapekey_name) + " in " + repr(
            [entry["shapekey_name"] for entry in result["targets"]]))

    def modifier(self, result, category, side):
        for entry in result["modifiers"]:
            if entry["category"] == category and entry["side"] == side:
                return entry
        self.fail("no modifier " + repr((category, side)) + " in " + repr(result["modifiers"]))

    def modeled_character(self):
        return self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("$md-$as-$fe-$yn", 0.5),
            ("!ex-browDownLeft", 0.2),
            ("l-lowerarm-scale-depth-incr", 0.4),
            ("r-lowerarm-scale-depth-decr", 0.25),
            ("nose-scale-depth-incr", 0.7),
        ])

    # -- subject resolution -------------------------------------------------

    def test_the_basemesh_is_found_from_the_rig(self):
        self.modeled_character()

        result = self.run_stack(name="Human.rig")

        self.assertTrue(result["found"])
        self.assertEqual(result["subject_name"], "Human.rig")
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertEqual(result["subject_resolved_by"], "name")

    def test_the_basemesh_is_found_from_a_garment(self):
        # The garment hangs off the rig, so this is a walk up and back down.
        self.modeled_character()

        result = self.run_stack(name="Shirt")

        self.assertEqual(result["basemesh_name"], "Human")

    def test_the_active_object_is_used_when_no_name_is_given(self):
        self.modeled_character()

        result = self.run_stack(name=None, active=self.rig)

        self.assertEqual(result["subject_resolved_by"], "active")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_no_active_object_is_an_answer_rather_than_a_crash(self):
        # The branch that would fail on None.name if it were missed.
        self.modeled_character()

        result = self.run_stack(name=None, active=None)

        self.assertFalse(result["found"])
        self.assertIsNone(result["subject_name"])
        self.assertEqual(result["targets"], [])
        self.assertIn("no object is active", result["message"])

    def test_an_unrelated_object_is_an_answer(self):
        self.modeled_character()
        stray = StubObject("Cube")
        self.objects.append(stray)

        result = self.run_stack(name="Cube")

        self.assertFalse(result["found"])
        self.assertIsNone(result["basemesh_name"])
        self.assertIn("no MakeHuman basemesh", result["message"])

    # -- the per-shape-key view ---------------------------------------------

    def test_a_detail_target_is_placed_back_into_its_category(self):
        self.modeled_character()

        entry = self.entry(self.run_stack(), "r-lowerarm-scale-depth-decr")

        self.assertEqual(entry["section"], "arms")
        self.assertEqual(entry["category"], "lowerarm-scale-depth-decr-incr")
        self.assertEqual(entry["side"], "right")
        self.assertEqual(entry["polarity"], "negative")
        self.assertEqual(entry["kind"], "detail")
        self.assertTrue(entry["listed_in_target_json"])
        self.assertEqual(entry["value"], 0.25)

    def test_the_basis_key_is_never_listed(self):
        self.modeled_character()

        names = [entry["shapekey_name"] for entry in self.run_stack()["targets"]]

        self.assertNotIn("Basis", names)

    def test_macro_and_expression_keys_are_excluded_by_default(self):
        self.modeled_character()

        result = self.run_stack()

        names = [entry["shapekey_name"] for entry in result["targets"]]
        self.assertNotIn("$md-$as-$fe-$yn", names)
        self.assertNotIn("!ex-browDownLeft", names)
        # ...but still counted, so their absence is explainable.
        self.assertEqual(result["counts_by_kind"]["macro"], 1)
        self.assertEqual(result["counts_by_kind"]["expression"], 1)
        self.assertIn("macro shape key(s) were left out", result["message"])

    def test_macro_keys_are_included_on_request_and_decoded(self):
        self.modeled_character()

        entry = self.entry(self.run_stack(include_macro=True), "$md-$as-$fe-$yn")

        self.assertEqual(entry["kind"], "macro")
        # The raw name is the address; the decoded one is what a human reads.
        self.assertEqual(entry["decoded_name"], "macrodetail-asian-female-young")
        self.assertIsNone(entry["category"])

    def test_expression_keys_are_included_on_request(self):
        self.modeled_character()

        entry = self.entry(
            self.run_stack(include_expressions=True), "!ex-browDownLeft")

        self.assertEqual(entry["kind"], "expression")

    def test_a_user_target_is_reported_as_detail_but_not_as_indexed(self):
        # It has a synthesized category, which MPFB's panel shows and
        # target.json has never heard of.
        self.build_character(shapekeys=[("Basis", 0.0), ("cat_ears", 0.6)])

        entry = self.entry(self.run_stack(), "cat_ears")

        self.assertEqual(entry["kind"], "detail")
        self.assertEqual(entry["section"], "animal")
        self.assertEqual(entry["category"], "cat_ears")
        self.assertFalse(entry["listed_in_target_json"])

    def test_a_shape_key_in_no_category_at_all_is_reported_as_unknown(self):
        self.build_character(shapekeys=[("Basis", 0.0), ("handmade_thing", 0.3)])

        entry = self.entry(self.run_stack(), "handmade_thing")

        self.assertEqual(entry["kind"], "unknown")
        self.assertIsNone(entry["section"])
        self.assertFalse(entry["listed_in_target_json"])

    def test_an_encoded_user_target_is_addressed_by_its_encoded_name(self):
        # FR 006 proved live that the filename addresses nothing at all here.
        encoded = ("$yn-$fe-$av-$ca-$un-$pr-$wg-$hg-experiment")
        self.build_character(shapekeys=[("Basis", 0.0), (encoded, 0.5)])

        entry = self.entry(self.run_stack(), encoded)

        self.assertEqual(entry["section"], "animal")
        self.assertEqual(entry["category"], LONG_USER_TARGET)
        self.assertEqual(entry["decoded_name"], LONG_USER_TARGET)

    # -- the "basis" blind spot ---------------------------------------------

    def test_a_shape_key_containing_basis_is_listed_and_flagged(self):
        # MPFB's own get_target_stack() excludes any name *containing* "basis",
        # so this key is real, is deforming the mesh, and is invisible to every
        # MPFB read and write. Suppressing it here too would hide it entirely.
        self.build_character(shapekeys=[("Basis", 0.0), ("basis-nose-widen", 0.9)])

        result = self.run_stack()
        entry = self.entry(result, "basis-nose-widen")

        self.assertFalse(entry["visible_to_targetservice"])
        self.assertEqual(entry["value"], 0.9)
        self.assertIn("invisible to MPFB itself", result["message"])

    def test_an_ordinary_shape_key_is_not_flagged(self):
        self.modeled_character()

        self.assertTrue(self.entry(self.run_stack(), "nose-scale-depth-incr")[
            "visible_to_targetservice"])

    # -- the rolled-up modifier view ----------------------------------------

    def test_a_positive_target_reads_back_as_a_positive_modifier(self):
        self.modeled_character()

        self.assertEqual(
            self.modifier(self.run_stack(), "lowerarm-scale-depth-decr-incr", "left")["value"],
            0.4)

    def test_a_negative_target_reads_back_negated(self):
        # _get_opposed_modifier_value()'s rule: the shape key holds 0.25 and the
        # modifier is -0.25, because the *negative* half of the pair is loaded.
        self.modeled_character()

        self.assertEqual(
            self.modifier(self.run_stack(), "lowerarm-scale-depth-decr-incr", "right")["value"],
            -0.25)

    def test_the_positive_target_wins_when_both_halves_are_present(self):
        # A stack that should not exist, but does after a hand edit - and MPFB's
        # own getter reports the positive one, so this one does too.
        self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("nose-scale-depth-incr", 0.6),
            ("nose-scale-depth-decr", 0.2),
        ])

        self.assertEqual(
            self.modifier(self.run_stack(), "nose-scale-depth-decr-incr", "unsided")["value"],
            0.6)

    def test_a_category_with_nothing_on_the_mesh_is_not_reported(self):
        self.modeled_character()

        categories = [entry["category"] for entry in self.run_stack()["modifiers"]]

        self.assertNotIn("chin-triangle", categories)

    def test_a_simple_category_reports_its_own_value(self):
        self.build_character(shapekeys=[("Basis", 0.0), ("chin-triangle", 0.8)])

        entry = self.modifier(self.run_stack(), "chin-triangle", "unsided")

        self.assertEqual(entry["value"], 0.8)
        self.assertFalse(entry["opposed"])

    def test_modifiers_are_not_filtered_by_name_contains(self):
        # The rollup is the view a caller writes back, so narrowing the target
        # listing must not quietly narrow it too.
        self.modeled_character()

        result = self.run_stack(name_contains="nose")

        self.assertEqual(len(result["targets"]), 1)
        self.assertEqual(result["modifier_count"], 3)

    # -- asymmetries ---------------------------------------------------------

    def test_two_sides_that_differ_are_reported_as_an_asymmetry(self):
        self.modeled_character()

        result = self.run_stack()

        self.assertEqual(result["asymmetries"], [{
            "section": "arms",
            "category": "lowerarm-scale-depth-decr-incr",
            "left": 0.4,
            "right": -0.25,
            "difference": 0.65,
        }])

    def test_two_sides_that_match_are_not_reported(self):
        self.build_character(shapekeys=[
            ("Basis", 0.0),
            ("l-lowerarm-scale-depth-incr", 0.4),
            ("r-lowerarm-scale-depth-incr", 0.4),
        ])

        self.assertEqual(self.run_stack()["asymmetries"], [])

    def test_an_unsided_category_is_never_an_asymmetry(self):
        self.modeled_character()

        categories = [entry["category"] for entry in self.run_stack()["asymmetries"]]

        self.assertNotIn("nose-scale-depth-decr-incr", categories)

    # -- paging --------------------------------------------------------------

    def test_the_answer_is_capped_and_says_so(self):
        self.modeled_character()

        result = self.run_stack(limit=1)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["total_count"], 3)
        self.assertTrue(result["truncated"])
        self.assertIn("not the whole stack", result["message"])

    def test_truncated_is_present_even_when_false(self):
        self.modeled_character()

        self.assertIn("truncated", self.run_stack())
        self.assertFalse(self.run_stack()["truncated"])

    def test_paging_is_deterministic_and_does_not_repeat_or_skip(self):
        # key_blocks order is insertion order, so sorting has to happen before
        # the slice or two pages of one query overlap.
        self.modeled_character()

        first = self.run_stack(limit=2, offset=0)["targets"]
        second = self.run_stack(limit=2, offset=2)["targets"]
        whole = self.run_stack()["targets"]

        self.assertEqual(first + second, whole)

    def test_paging_is_echoed_back(self):
        self.modeled_character()

        result = self.run_stack(limit=2, offset=1)

        self.assertEqual(result["offset"], 1)
        self.assertEqual(result["limit"], 2)

    def test_counts_are_over_everything_not_over_the_page(self):
        self.modeled_character()

        result = self.run_stack(limit=1, name_contains="lowerarm")

        self.assertEqual(result["counts_by_section"]["arms"], 2)
        self.assertEqual(result["counts_by_kind"]["detail"], 3)

    # -- a mesh with nothing on it -------------------------------------------

    def test_a_basemesh_without_shape_keys_is_an_answer(self):
        self.build_character(shapekeys=None)

        result = self.run_stack()

        self.assertTrue(result["found"])
        self.assertFalse(result["has_shapekeys"])
        self.assertEqual(result["targets"], [])
        self.assertEqual(result["modifiers"], [])

    # -- nothing is changed --------------------------------------------------

    def test_nothing_is_activated_selected_or_recalculated(self):
        from tests.blender_stubs import StubObjectService, StubTargetService

        self.modeled_character()
        before = dict(self.shapekey_values())

        self.run_stack()

        self.assertEqual(StubObjectService.activations, [])
        self.assertEqual(StubTargetService.reapply_calls, [])
        self.assertEqual(StubTargetService.load_calls, [])
        self.assertEqual(StubTargetService.set_calls, [])
        self.assertEqual(self.shapekey_values(), before)


if __name__ == "__main__":
    unittest.main()
