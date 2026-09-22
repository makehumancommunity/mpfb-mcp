# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_add_rig tool: argument validation, and the generated code's
dispatch, pre-checks and reporting.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_code`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source executed
against the stub services and a real temporary rig tree
(tests/blender_stubs.py's RigTestCase). That third layer is **frozen**: it stays
while the payload stays, because the payload is half of what FR 032's live
comparison compares.

The rig tree is shared with tests/test_list_rigs.py deliberately - the point of
the shared rig_lookup rule is that the catalogue's prediction and this tool's
outcome cannot disagree, and that can only be asserted by running both against
the same disk. **Both halves of that pair are now on the bridge**, so the same
agreement is checked there against a real MPFB.

What layer 3 cannot say is that a rig added through this tool is
indistinguishable from one added through MPFB's own panel. That is now checked
in ``bridge/test/tests/ppp_mutating/add_rig_test.py``.

Run with::

    python -m unittest tests.test_add_rig -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import codegen
from mpfbmcp import backend
from mpfbmcp.tools import add_rig

from tests import fake_bridge
from tests.blender_stubs import (
    RigTestCase, StubHumanService, StubObject, StubObjectService, StubRigService,
    StubSystemService)
from tests import generated_path


# These tests are about the **generated path**: they mock `backend.send_code`
# and assert about the program that reached it. FR 032 made the bridge the
# default, so saying so is now necessary rather than implied.
# See tests/generated_path.py.
setUpModule = generated_path.pin
tearDownModule = generated_path.unpin


# Distinguishes "the test did not say" from "the test said: nothing is active".
_UNSET = object()


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    add_rig.register(mcp)
    return mcp._tool_manager._tools["mpfb_add_rig"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape only. Which rigs exist is a directory listing inside Blender."""

    def setUp(self):
        self.tool = _tool_callable()

    def _sent_source(self, **kwargs):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_code.call_args[0][0]

    def test_the_identifier_and_defaults_cross_the_socket(self):
        source = self._sent_source(identifier="default")
        self.assertIn("# --- payload: add_rig.py ---", source)
        self.assertIn("# --- shared: rig_lookup.py ---", source)
        self.assertIn(
            json.dumps({"name": None, "identifier": "default", "import_weights": True}), source)

    def test_the_shared_fragment_is_the_one_list_rigs_uses(self):
        # Not decoration: if these two ever name different fragments, the
        # catalogue and the adder can predict different weights for one rig.
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(identifier="default")
        self.assertIn(codegen.read_shared("rig_lookup.py"), send_code.call_args[0][0])

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is carried through with its status and message intact and
        # an `error` slug added, which is the seam's one mapping: a caller
        # branches on `error` without having to learn which transport answered.
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "error", "message": "no MPFB"}
            response = self.tool(identifier="default")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)

    def test_strict_json_is_requested(self):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(identifier="default")
        self.assertIs(send_code.call_args[1]["strict_json"], True)

    def test_a_missing_or_empty_identifier_is_rejected_locally(self):
        for bad in ("", "   ", None, 3, ["default"]):
            with self.subTest(identifier=bad):
                with mock.patch("mpfbmcp.backend.send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(identifier=bad)
                send_code.assert_not_called()

    def test_an_explicitly_empty_name_is_never_read_as_an_omitted_one(self):
        for bad in ("", "   ", 7, []):
            with self.subTest(name=bad):
                with mock.patch("mpfbmcp.backend.send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(name=bad, identifier="default")
                send_code.assert_not_called()

    def test_non_bool_import_weights_is_rejected_locally(self):
        # Truthiness would make import_weights="false" add a rig the mesh is
        # parented to but not deformed by, which is invisible until it is posed.
        for bad in (1, 0, "true", "false", None, []):
            with self.subTest(import_weights=bad):
                with mock.patch("mpfbmcp.backend.send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(identifier="default", import_weights=bad)
                send_code.assert_not_called()

    def test_the_vocabulary_is_deliberately_not_validated_here(self):
        # A rig list kept on this side of the socket would drift from the
        # directories, so an unknown identifier has to reach Blender to be
        # refused there, with known_identifiers beside it.
        self.assertIn("no-such-rig", self._sent_source(identifier="no-such-rig"))


class AddRigOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - which file loads, whose weights come with it, the ordering warning, the AssertionError path - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/add_rig_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "add_rig": fake_bridge.ok_envelope("add_rig", {"found": True, "added": True, "performed": True}),
        })

    def test_the_tool_sends_the_add_rig_command(self) -> None:
        self.call(identifier="default")

        self.assertEqual(self.bridge.commands()[-1], "add_rig")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params, {"name": None, "identifier": "default", "import_weights": True})

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(identifier="default")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("rig_lookup", str(request))

    def test_the_identifier_is_not_validated_against_a_vocabulary_here(self) -> None:
        # A rig list kept on this side of the socket would drift from the
        # directories, so an unknown identifier reaches the bridge to be refused
        # there, with known_identifiers beside it.
        self.call(identifier="no-such-rig")

        self.assertEqual(
            self.bridge.decoded_requests()[-1]["params"]["identifier"], "no-such-rig")

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        for value in ("", "   ", None, 3):
            with self.subTest(identifier=value):
                with self.assertRaises(ValueError):
                    self.call(identifier=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="add_rig", state="absent"))

        response = self.call(identifier="default")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class AddRigGeneratedCodeTests(RigTestCase):
    """The payload, run against the stub scene and a real rig tree."""

    def run_add_rig(self, identifier, name=None, import_weights=True, active=_UNSET):
        # active defaults to the basemesh; pass None for the "nothing is active"
        # branch, which is what crashes on None.name if a payload misses it.
        return self.run_payload(
            "add_rig.py",
            {"name": name, "identifier": identifier, "import_weights": import_weights},
            scene_objects=self.objects,
            active=self.basemesh if active is _UNSET else active,
            shared=["rig_lookup.py", "performed.py"],
        )

    # -- the ordinary path --------------------------------------------------

    def test_a_standard_rig_is_added_through_add_builtin_rig(self):
        self.build_character()
        result = self.run_add_rig("default")

        self.assertTrue(result["added"])
        self.assertEqual(result["family"], "standard")
        self.assertEqual(result["add_function_used"], "add_builtin_rig")
        self.assertEqual(result["rig_object_name"], "Human.rig")
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertFalse(result["is_metarig"])
        self.assertIsNone(result["next_step"])
        self.assertEqual(
            [call["function"] for call in StubHumanService.add_rig_calls], ["add_builtin_rig"])

    def test_the_created_name_is_read_off_the_object_rather_than_predicted(self):
        # Blender uniquifies a name already in use, so a second character in the
        # same file gets Human.rig.001 - which is why nothing here guesses.
        self.build_character()
        StubHumanService.add_rig_calls = []
        result = self.run_add_rig("default")
        created = StubObjectService.bpy.data.objects.get(result["rig_object_name"])
        self.assertIsNotNone(created)
        self.assertEqual(created.type, "ARMATURE")

    def test_a_rigify_identifier_produces_a_meta_rig_and_says_so(self):
        self.build_character()
        result = self.run_add_rig("rigify.human")

        self.assertTrue(result["added"])
        self.assertEqual(result["family"], "rigify")
        self.assertEqual(result["add_function_used"], "add_builtin_rig")
        self.assertEqual(result["rig_object_name"], "Human.metarig")
        self.assertTrue(result["is_metarig"])
        self.assertIn("mpfb_generate_rigify_rig", result["next_step"])
        self.assertIn("mpfb_generate_rigify_rig", result["message"])

    def test_only_a_custom_prefix_dispatches_to_add_custom_rig(self):
        self.install_custom_rig("my_rig")
        self.build_character()
        result = self.run_add_rig("custom.my_rig")

        self.assertTrue(result["added"])
        self.assertEqual(result["family"], "custom")
        self.assertEqual(result["add_function_used"], "add_custom_rig")
        self.assertEqual(
            [call["function"] for call in StubHumanService.add_rig_calls], ["add_custom_rig"])
        # And the identifier reaches MPFB whole, prefix included: add_custom_rig
        # strips the first seven characters itself.
        self.assertEqual(StubHumanService.add_rig_calls[0]["rig_name"], "custom.my_rig")

    def test_no_other_identifier_reaches_add_custom_rig(self):
        for identifier in ("default", "rigify.human"):
            with self.subTest(identifier=identifier):
                self.build_character()
                StubHumanService.add_rig_calls = []
                self.run_add_rig(identifier)
                self.assertEqual(
                    [call["function"] for call in StubHumanService.add_rig_calls],
                    ["add_builtin_rig"])

    def test_the_subject_resolves_from_a_garments_name(self):
        self.build_character(dressed=True)
        result = self.run_add_rig("default", name="Shirt")

        self.assertTrue(result["added"])
        self.assertEqual(result["subject_name"], "Shirt")
        self.assertEqual(result["subject_resolved_by"], "name")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_the_active_object_is_used_when_no_name_is_given(self):
        self.build_character()
        result = self.run_add_rig("default")
        self.assertEqual(result["subject_resolved_by"], "active")
        self.assertEqual(result["subject_name"], "Human")

    # -- weights ------------------------------------------------------------

    def test_weights_are_reported_as_loaded_with_their_source(self):
        self.build_character()
        result = self.run_add_rig("default")

        self.assertTrue(result["weights_loaded"])
        self.assertEqual(result["weights_from"], "default")
        self.assertTrue(result["weights_path"].endswith("weights.default.json"))
        self.assertTrue(result["armature_modifier_added"])

    def test_a_rig_borrowing_another_rigs_weights_says_whose(self):
        # default_no_toes ships no weights file of its own and falls back to
        # default's. Reporting has_weights: false here would make an ordinary
        # rig look broken.
        self.build_character()
        result = self.run_add_rig("default_no_toes")

        self.assertTrue(result["weights_loaded"])
        self.assertEqual(result["weights_from"], "default")
        self.assertIn("fallback", result["message"])

    def test_a_rigify_rig_is_not_reported_as_borrowing_from_itself(self):
        # weights_from is always a bare name, so comparing it against the
        # identifier would report rigify.human_toes as a fallback of itself.
        self.build_character()
        result = self.run_add_rig("rigify.human_toes")

        self.assertEqual(result["weights_from"], "human_toes")
        self.assertNotIn("fallback", result["message"])

    def test_the_weights_prediction_matches_what_list_rigs_reports(self):
        # The reason codegen/shared/rig_lookup.py exists. Both payloads run
        # against the same tree, and their answers have to be the same answer.
        self.build_character()
        catalogue = self.run_payload(
            "list_rigs.py", {"refresh": False}, scene_objects=self.objects,
            shared=["rig_lookup.py"])
        predictions = dict(
            (entry["identifier"], (entry["has_weights"], entry["weights_from"]))
            for entry in catalogue["rigs"])

        for identifier in ("default", "default_no_toes", "rigify.human", "rigify.human_toes"):
            with self.subTest(identifier=identifier):
                self.build_character()
                result = self.run_add_rig(identifier)
                self.assertEqual(
                    (result["weights_loaded"], result["weights_from"]),
                    predictions[identifier])

    def test_a_rig_with_no_weights_at_all_is_reported_rather_than_silent(self):
        # add_builtin_rig() reports this through an operator only, so with none
        # it adds an unweighted rig and says nothing whatsoever.
        self.build_character()
        result = self.run_add_rig("undocumented_rig")

        self.assertTrue(result["added"])
        self.assertFalse(result["weights_loaded"])
        self.assertIsNone(result["weights_from"])
        self.assertIn("no vertex weights", result["message"])

    def test_import_weights_false_adds_no_armature_modifier(self):
        self.build_character()
        result = self.run_add_rig("default", import_weights=False)

        self.assertTrue(result["added"])
        self.assertFalse(result["weights_loaded"])
        self.assertFalse(result["armature_modifier_added"])
        self.assertEqual(StubRigService.weights_loaded, [])
        self.assertIn("not deformed by it", result["message"])

    def test_a_custom_rig_uses_no_fallback_table(self):
        self.install_custom_rig("my_rig", weights=False)
        self.build_character()
        result = self.run_add_rig("custom.my_rig")

        self.assertTrue(result["added"])
        self.assertFalse(result["weights_loaded"])

    # -- the ordering constraint, which is what this tool exists for ---------

    def test_assets_attached_before_the_rig_are_named(self):
        self.build_character(dressed=True, subrig=True)
        result = self.run_add_rig("default")

        self.assertTrue(result["added"])
        self.assertEqual(result["mesh_assets_not_rigged"], ["Shirt"])
        self.assertEqual(result["subrigs_not_rigged"], ["Shirt.subrig"])
        self.assertIn("NOT", result["message"])

    def test_an_undressed_character_reports_nothing_unrigged(self):
        self.build_character()
        result = self.run_add_rig("default")

        self.assertEqual(result["mesh_assets_not_rigged"], [])
        self.assertEqual(result["subrigs_not_rigged"], [])
        self.assertNotIn("NOT", result["message"])

    # -- side effects the caller would not otherwise see ---------------------

    def test_moving_the_basemesh_to_the_origin_is_reported(self):
        self.build_character(location=(1.0, 2.0, 3.0))
        result = self.run_add_rig("default")

        self.assertEqual(result["basemesh_location_before"], [1.0, 2.0, 3.0])
        self.assertTrue(result["basemesh_moved_to_origin"])
        self.assertEqual(result["rig_location"], [1.0, 2.0, 3.0])
        self.assertIn("moved to the origin", result["message"])

    def test_a_character_already_at_the_origin_reports_no_move(self):
        self.build_character()
        result = self.run_add_rig("default")

        self.assertFalse(result["basemesh_moved_to_origin"])
        self.assertNotIn("moved to the origin", result["message"])

    def test_the_previous_active_object_and_selection_are_restored(self):
        self.build_character(dressed=True)
        self.run_add_rig("default", active=self.shirt)

        self.assertEqual(StubObjectService.activations, ["Human"])
        self.assertIs(
            StubObjectService.bpy.context.view_layer.objects.active, self.shirt)
        self.assertFalse(self.basemesh.select_get())

    # -- preconditions, all answers ----------------------------------------

    def test_an_unresolvable_name_is_an_answer(self):
        self.build_character()
        result = self.run_add_rig("default", name="Nonexistent")

        self.assertFalse(result["found"])
        self.assertFalse(result["added"])
        self.assertEqual(result["blocked_by"], "subject_not_found")
        self.assertIn("mpfb_list_objects", result["message"])
        self.assertEqual(StubHumanService.add_rig_calls, [])

    def test_no_active_object_is_an_answer(self):
        self.build_character()
        result = self.run_add_rig("default", active=None)

        self.assertFalse(result["found"])
        self.assertEqual(result["blocked_by"], "subject_not_found")

    def test_an_object_with_no_basemesh_relative_is_an_answer(self):
        self.build_character()
        stray = StubObject("Cube")
        self.objects = self.objects + [stray]
        result = self.run_add_rig("default", name="Cube")

        self.assertFalse(result["found"])
        self.assertEqual(result["blocked_by"], "subject_not_found")
        self.assertIn("basemesh", result["message"])

    def test_an_already_rigged_character_is_refused_by_name(self):
        self.build_character(rig=True)
        result = self.run_add_rig("default")

        self.assertTrue(result["found"])
        self.assertFalse(result["added"])
        self.assertEqual(result["blocked_by"], "already_rigged")
        self.assertEqual(result["existing_rig_name"], "Human.rig")
        self.assertIn("Human.rig", result["message"])
        self.assertEqual(StubHumanService.add_rig_calls, [])

    def test_an_unknown_identifier_lists_the_family_it_addressed(self):
        self.build_character()
        result = self.run_add_rig("no_such_rig")

        self.assertFalse(result["added"])
        self.assertEqual(result["blocked_by"], "unknown_identifier")
        self.assertEqual(
            sorted(result["known_identifiers"]),
            ["default", "default_no_toes", "game_engine", "undocumented_rig"])
        self.assertEqual(StubHumanService.add_rig_calls, [])

    def test_an_unknown_rigify_identifier_lists_only_rigify_rigs(self):
        self.build_character()
        result = self.run_add_rig("rigify.nonexistent")

        self.assertEqual(result["blocked_by"], "unknown_identifier")
        self.assertEqual(
            sorted(result["known_identifiers"]), ["rigify.human", "rigify.human_toes"])

    def test_an_unknown_custom_identifier_lists_only_custom_rigs(self):
        self.install_custom_rig("my_rig")
        self.build_character()
        result = self.run_add_rig("custom.other_rig")

        self.assertEqual(result["blocked_by"], "unknown_identifier")
        self.assertEqual(result["known_identifiers"], ["custom.my_rig"])

    def test_a_weights_file_is_not_addable_as_a_rig(self):
        # weights.orphan.json sits in the standard directory; "orphan" is not a
        # rig, and the catalogue does not list it either.
        self.build_character()
        result = self.run_add_rig("orphan")
        self.assertEqual(result["blocked_by"], "unknown_identifier")

    def test_a_rigify_identifier_with_rigify_off_is_refused_before_mpfb(self):
        StubSystemService.rigify_available = False
        self.build_character()
        result = self.run_add_rig("rigify.human")

        self.assertEqual(result["blocked_by"], "rigify_unavailable")
        self.assertFalse(result["rigify_available"])
        self.assertIn("Rigify", result["message"])
        self.assertEqual(StubHumanService.add_rig_calls, [])

    def test_a_standard_rig_is_unaffected_by_rigify_being_off(self):
        StubSystemService.rigify_available = False
        self.build_character()
        self.assertTrue(self.run_add_rig("default")["added"])

    def test_a_basemesh_in_edit_mode_is_an_answer(self):
        self.build_character(mode="EDIT")
        result = self.run_add_rig("default")

        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(StubHumanService.add_rig_calls, [])

    def test_blender_being_in_another_mode_is_an_answer_too(self):
        # The basemesh looks fine; something else is in edit mode, and every
        # bpy.ops call the armature build makes polls on the context.
        self.build_character()
        result = self.run_payload(
            "add_rig.py",
            {"name": None, "identifier": "default", "import_weights": True},
            scene_objects=self.objects, active=self.basemesh,
            shared=["rig_lookup.py", "performed.py"],
            context_mode="EDIT_MESH")

        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(StubHumanService.add_rig_calls, [])

    def test_the_rigify_colour_assertion_is_translated_and_the_stray_named(self):
        # A bare AssertionError with no message, downstream of the
        # check_for_rigify() guard and so not pre-checkable. It fires after the
        # armature exists and before it is parented.
        StubHumanService.rigify_colors = 0
        self.build_character()
        result = self.run_add_rig("rigify.human")

        self.assertFalse(result["added"])
        self.assertEqual(result["blocked_by"], "rigify_colors_missing")
        self.assertEqual(result["partial_objects_created"], ["Human.metarig"])
        self.assertIn("colour sets", result["message"])
        # ...and the scene is put back the way it was found, apart from the
        # stray, which is exactly why the stray is reported.
        self.assertIs(
            StubObjectService.bpy.context.view_layer.objects.active, self.basemesh)

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_tracks_added(self):
        # The refusal first: it changes nothing, so the same character can then
        # be rigged for real.
        self.build_character()

        refused = self.run_add_rig("no_such_rig")
        self.assertEqual(refused["blocked_by"], "unknown_identifier")
        self.assertIs(refused["performed"], False)
        self.assertEqual(refused["performed"], refused["added"])

        added = self.run_add_rig("default")
        self.assertIs(added["performed"], True)
        self.assertEqual(added["performed"], added["added"])

class PayloadSourceTests(unittest.TestCase):
    """Two rules the payload has to keep that are easiest to assert on source."""

    def test_the_payload_never_imports_an_mpfb_submodule(self):
        source = codegen.read_payload("add_rig.py")
        self.assertNotIn("import_module", source)
        self.assertIn('_MPFB_SERVICES["HumanService"]', source)

    def test_dispatch_is_on_the_prefix_and_not_on_a_caller_supplied_name(self):
        # add_function_used is reported, never accepted: crossing the two adding
        # functions does not fail legibly.
        source = codegen.read_payload("add_rig.py")
        self.assertNotIn('PARAMS["add_function"]', source)
        self.assertIn('family_of(requested_identifier)', source)


if __name__ == "__main__":
    unittest.main()
