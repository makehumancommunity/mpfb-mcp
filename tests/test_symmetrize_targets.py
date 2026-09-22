# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_symmetrize_targets tool: argument validation, the dry run,
and the category walk that makes an asymmetric detail stack symmetric.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_code`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source - shared
fragments included - executed against the stub scene and the real temporary
target tree in tests/blender_stubs.py. That third layer is **frozen**, and what
this tool actually does to a character is checked against a real MPFB in
``bridge/test/tests/ppp_mutating/symmetrize_targets_test.py``.

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

from mpfbmcp import backend, codegen, shared_cache
from mpfbmcp.tools import symmetrize_targets

from tests import fake_bridge
from tests.blender_stubs import (
    DetailTargetTestCase, StubHumanService, StubObject, StubObjectService,
    StubTargetService)
from tests import generated_path


# These tests are about the **generated path**: they mock `backend.send_code`
# and assert about the program that reached it. FR 032 made the bridge the
# default, so saying so is now necessary rather than implied.
# See tests/generated_path.py.
setUpModule = generated_path.pin
tearDownModule = generated_path.unpin


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
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(direction="left_to_right")
        source = send_code.call_args[0][0]
        self.assertIn("# --- payload: symmetrize_targets.py ---", source)
        self.assertIn("# --- cached shared: " + codegen.shared_key("target_categories.py"), source)
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
                with mock.patch.object(shared_cache, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(direction=bad)
                send_code.assert_not_called()

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(direction="right_to_left", name="Human.rig", section="eyes",
                      dry_run=True, prune=False, refit=True)
        self.assertIn(json.dumps({
            "name": "Human.rig", "direction": "right_to_left", "section": "eyes",
            "dry_run": True, "prune": False, "refit": True}),
            send_code.call_args[0][0])

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is this package's: `status` and `message` are unchanged,
        # and `error` is what a caller branches on whichever transport answered.
        # Since FR 031 this tool's fragments go through the seam rather than
        # around it, so the mapping applies to a cached-fragment call too.
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "error", "message": "no MPFB"}
            response = self.tool(direction="left_to_right")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)

    def test_strict_json_is_requested(self):
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(direction="left_to_right")
        self.assertIs(send_code.call_args[1]["strict_json"], True)

    def test_non_string_or_empty_text_arguments_are_rejected_locally(self):
        for argument in ("name", "section"):
            for bad in (1, True, [], object(), "", "   "):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(shared_cache, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(direction="left_to_right", **{argument: bad})
                    send_code.assert_not_called()

    def test_flags_must_be_real_bools(self):
        # dry_run="false" would otherwise write.
        for argument in ("dry_run", "prune", "refit"):
            for bad in ("false", "true", 0, 1, None):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(shared_cache, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(direction="left_to_right", **{argument: bad})
                    send_code.assert_not_called()

    def test_an_unknown_section_is_not_rejected_locally(self):
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(direction="left_to_right", section="no-such-section")
        send_code.assert_called_once()


class SymmetrizeTargetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    The category walk, the dry run agreeing with the real run, and the write
    order are checked against a real MPFB in
    ``bridge/test/tests/ppp_mutating/symmetrize_targets_test.py``. What is left
    here is the one required argument in the package, and that it is refused
    before a transport is chosen - which is what keeps the most destructive
    tool here from guessing which half of a face to keep.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "symmetrize_targets": fake_bridge.ok_envelope(
                "symmetrize_targets", {"found": True, "changed": [], "performed": False}),
        })

    def test_the_tool_sends_the_symmetrize_targets_command(self) -> None:
        self.call(direction="left_to_right")

        self.assertEqual(self.bridge.commands()[-1], "symmetrize_targets")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["direction"], "left_to_right")
        self.assertEqual(params["dry_run"], False)
        self.assertEqual(params["prune"], True)

    def test_a_dry_run_is_carried_as_a_parameter_like_any_other(self) -> None:
        self.call(direction="right_to_left", dry_run=True, section="nose")

        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["dry_run"], True)
        self.assertEqual(params["section"], "nose")

    def test_the_required_direction_is_refused_before_a_transport_is_chosen(self) -> None:
        # The package's only required argument, and the reason is that guessing
        # wrong destroys work with no undo across the socket.
        for value in (None, "", "leftward", 3):
            with self.subTest(direction=value):
                with self.assertRaises(ValueError):
                    self.call(direction=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(direction="left_to_right")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("cached_shared", request)
        self.assertNotIn("modifier_reading", str(request))

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "TargetService.set_target_value() raised.",
                command="symmetrize_targets"))

        response = self.call(direction="left_to_right")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")


class GeneratedSymmetrizeTargetsTests(DetailTargetTestCase):
    """The payload, run against a real target tree and the stub scene."""

    def run_symmetrize(self, direction="left_to_right", name="Human", section=None,
                       dry_run=False, prune=True, refit=False, active=None):
        return self.run_payload(
            "symmetrize_targets.py",
            {"name": name, "direction": direction, "section": section,
             "dry_run": dry_run, "prune": prune, "refit": refit},
            scene_objects=self.objects, active=active,
            shared=["target_categories.py", "modifier_reading.py",
                    "refit_blocker.py", "performed.py"])

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

    def test_a_dry_run_leaves_the_per_target_list_null_rather_than_empty(self):
        # The one thing a dry run genuinely cannot report: which target files a
        # write would touch depends on whether the opposing target is already on
        # the mesh, which is only settled by doing the write. `[]` would say "no
        # shape keys would be touched" - a different claim, and a false one.
        self.asymmetric_character()

        dry = self.run_symmetrize(dry_run=True)
        real = self.run_symmetrize()

        self.assertTrue(dry["changed"])
        self.assertEqual([entry["targets"] for entry in dry["changed"]],
                         [None] * len(dry["changed"]))
        self.assertTrue(all(isinstance(entry["targets"], list) for entry in real["changed"]))

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

    def test_every_reading_matches_what_get_target_stack_reports(self):
        # Not decoration, and the reason codegen/shared/modifier_reading.py
        # exists: mpfb_get_target_stack reports these numbers and this tool acts
        # on them, so two implementations of the reading would leave a character
        # symmetric in one tool and asymmetric in the other, with nothing in
        # either answer to say which is right. Both payloads are run over one
        # character on purpose - agreement asserted over two fixtures would not
        # be agreement.
        self.asymmetric_character()

        stack = self.run_payload(
            "get_target_stack.py",
            {"name": "Human", "include_macro": False, "include_expressions": False,
             "name_contains": None, "limit": 500, "offset": 0},
            scene_objects=self.objects,
            shared=["target_categories.py", "modifier_reading.py"])
        # A dry run: it measures every sided category the same way a real one
        # does, and writes nothing between the two readings being compared.
        planned = self.run_symmetrize(dry_run=True)

        reported = dict(
            ((entry["section"], entry["category"], entry["side"]), entry["value"])
            for entry in stack["modifiers"])
        entries = planned["changed"] + planned["already_symmetric"] + planned["skipped"]
        self.assertTrue(entries, "the fixture must exercise at least one sided category")
        compared = 0
        for entry in entries:
            for side_key, value_key in (("source_side", "source_value"),
                                        ("destination_side", "destination_value_before")):
                with self.subTest(category=entry["category"], side=entry[side_key]):
                    # 0.0 where the catalogue lists nothing: mpfb_get_target_stack
                    # reports only the categories with a reading above MPFB's own
                    # epsilon, while this tool measures every sided one.
                    self.assertEqual(
                        entry[value_key],
                        reported.get(
                            (entry["section"], entry["category"], entry[side_key]), 0.0))
                    compared += 1
        self.assertGreater(compared, 0)
        # The asymmetric pair specifically, so that this passes for a reason
        # rather than because both answers were empty: +0.4 against -0.25, the
        # negative side read back negated by both payloads.
        arm = [entry for entry in stack["asymmetries"]
               if entry["category"] == "lowerarm-scale-depth-decr-incr"]
        self.assertEqual(len(arm), 1)
        self.assertEqual((arm[0]["left"], arm[0]["right"]), (0.4, -0.25))

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

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_is_false_under_dry_run_however_full_changed_is(self):
        # The case that makes the flag more than a rename: a dry run reports
        # every change it would make and writes none of them.
        self.asymmetric_character()

        preview = self.run_symmetrize(dry_run=True)
        self.assertTrue(preview["changed"])
        self.assertIs(preview["performed"], False)

        applied = self.run_symmetrize()
        self.assertTrue(applied["changed"])
        self.assertIs(applied["performed"], True)

        # Nothing left asymmetric, so nothing was written this time either.
        again = self.run_symmetrize()
        self.assertEqual(again["changed"], [])
        self.assertIs(again["performed"], False)

        self.asymmetric_character()
        blocked = self.run_symmetrize(section="nope")
        self.assertEqual(blocked["blocked_by"], "unknown_section")
        self.assertIs(blocked["performed"], False)


if __name__ == "__main__":
    unittest.main()
