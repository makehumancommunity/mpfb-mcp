# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_generate_rigify_rig tool: argument validation, meta-rig
resolution, and the reporting of a generation that changed the scene without
producing a rig.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_code`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source executed
against the stub services. That third layer is **frozen**: it stays while the
payload stays, because the payload is half of what FR 032's live comparison
compares.

The stub RigService.generate_rigify_rig() is written in MPFB's own order rather
than a convenient one - the rename, the deselection and the activation all
happen before the validity gate - because "a failed generation is not a no-op"
is the claim this tool exists to make, and a stub that checked validity first
would make it untestable.

What layer 3 cannot say is that the generated rig deforms the character the way
Rigify's own does, or that meta_rig_action "delete" really leaves
mpfb_refit_human unable to refit. Both are now checked against a real Rigify in
``bridge/test/tests/ppp_mutating/generate_rigify_rig_test.py``, which the
FR 032 spike established can run in a Blender with no window.

Run with::

    python -m unittest tests.test_generate_rigify_rig -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import codegen
from mpfbmcp import backend
from mpfbmcp.tools import generate_rigify_rig

from tests import fake_bridge
from tests.blender_stubs import (
    RigTestCase, StubObject, StubObjectService, StubRigService, StubSystemService)
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
    generate_rigify_rig.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_generate_rigify_rig"].fn


class ArgumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.tool = _tool_callable()

    def _sent_source(self, **kwargs):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_code.call_args[0][0]

    def test_the_defaults_are_mpfbs_own(self):
        source = self._sent_source()
        self.assertIn("# --- payload: generate_rigify_rig.py ---", source)
        self.assertIn(
            json.dumps({"name": None, "rig_name": None, "meta_rig_action": "hide"}), source)

    def test_performed_py_is_the_only_shared_fragment_sent(self):
        # This payload resolves nothing off the rig directories, so it names
        # none of the lookup fragments - and naming one it did not use would be
        # noise in the program. The one it does name is the uniform "it
        # happened" flag every mutating tool carries.
        source = self._sent_source()
        self.assertIn("# --- shared: performed.py ---", source)
        self.assertEqual(source.count("# --- shared:"), 1)

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is carried through with its status and message intact and
        # an `error` slug added, which is the seam's one mapping: a caller
        # branches on `error` without having to learn which transport answered.
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "error", "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)

    def test_strict_json_is_requested(self):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertIs(send_code.call_args[1]["strict_json"], True)

    def test_every_meta_rig_action_mpfb_knows_is_accepted(self):
        for action in ("keep", "hide", "delete"):
            with self.subTest(meta_rig_action=action):
                self.assertIn(
                    json.dumps({"name": None, "rig_name": None, "meta_rig_action": action}),
                    self._sent_source(meta_rig_action=action))

    def test_an_unknown_meta_rig_action_is_rejected_locally(self):
        # The one closed vocabulary this package validates on this side of the
        # socket: MPFB warns and silently falls back to "hide", which would make
        # a typo indistinguishable from a choice - on the single argument whose
        # wrong value cannot be undone.
        for bad in ("Hide", "remove", "", None, True, ["hide"]):
            with self.subTest(meta_rig_action=bad):
                with mock.patch("mpfbmcp.backend.send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(meta_rig_action=bad)
                send_code.assert_not_called()

    def test_an_explicitly_empty_name_or_rig_name_is_rejected(self):
        for kwargs in ({"name": ""}, {"name": "  "}, {"rig_name": ""}, {"rig_name": "  "},
                       {"name": 3}, {"rig_name": 3}):
            with self.subTest(**kwargs):
                with mock.patch("mpfbmcp.backend.send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(**kwargs)
                send_code.assert_not_called()


class GenerateRigifyRigOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the four refusals, what a rejected meta rig leaves behind, and ``active_object_after`` - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/generate_rigify_rig_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "generate_rigify_rig": fake_bridge.ok_envelope("generate_rigify_rig", {"found": True, "generated": True, "performed": True}),
        })

    def test_the_tool_sends_the_generate_rigify_rig_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "generate_rigify_rig")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(
            params, {"name": None, "rig_name": None, "meta_rig_action": "hide"})

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call()

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("performed", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        for value in ("Hide", "remove", "", None):
            with self.subTest(meta_rig_action=value):
                with self.assertRaises(ValueError):
                    self.call(meta_rig_action=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="generate_rigify_rig", state="absent"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GenerateGeneratedCodeTests(RigTestCase):
    """The payload, run against the stub scene."""

    def build_metarig_character(self, **kwargs):
        kwargs.setdefault("rig_name", "Human.metarig")
        kwargs.setdefault("rig_type", "rigify.human")
        return self.build_character(rig=True, **kwargs)

    def run_generate(self, name=None, rig_name=None, meta_rig_action="hide",
                     active=_UNSET, context_mode="OBJECT"):
        return self.run_payload(
            "generate_rigify_rig.py",
            {"name": name, "rig_name": rig_name, "meta_rig_action": meta_rig_action},
            scene_objects=self.objects,
            active=self.basemesh if active is _UNSET else active,
            context_mode=context_mode,
            shared=["performed.py"],
        )

    # -- the ordinary path --------------------------------------------------

    def test_the_meta_rig_is_resolved_from_the_basemesh(self):
        self.build_metarig_character()
        result = self.run_generate()

        self.assertTrue(result["generated"])
        self.assertEqual(result["metarig_name"], "Human.metarig")
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertEqual(result["rig_object_name"], "Human.rig")
        self.assertEqual(
            [call["meta_rig"] for call in StubRigService.generate_calls], ["Human.metarig"])

    def test_the_meta_rig_is_resolved_from_itself_and_from_a_garment(self):
        for subject in ("Human.metarig", "Shirt"):
            with self.subTest(subject=subject):
                self.build_metarig_character(dressed=True)
                result = self.run_generate(name=subject)
                self.assertTrue(result["generated"])
                self.assertEqual(result["subject_name"], subject)
                self.assertEqual(result["subject_resolved_by"], "name")
                self.assertEqual(result["metarig_name"], "Human.metarig")

    def test_mesh_assets_present_at_generation_time_are_reported(self):
        # The second half of the ordering problem: generation handles exactly
        # what is on the character when it runs, and nothing afterwards.
        self.build_metarig_character(dressed=True)
        result = self.run_generate()

        self.assertEqual(result["mesh_assets_present"], ["Shirt"])
        self.assertIn("1 mesh asset", result["message"])

    def test_an_undressed_character_is_told_the_order_is_right(self):
        self.build_metarig_character()
        result = self.run_generate()

        self.assertEqual(result["mesh_assets_present"], [])
        self.assertIn("right order", result["message"])

    def test_an_explicit_rig_name_reaches_mpfb_and_names_the_result(self):
        self.build_metarig_character()
        result = self.run_generate(rig_name="Hero.rigify")

        self.assertEqual(StubRigService.generate_calls[0]["name"], "Hero.rigify")
        self.assertEqual(result["rig_object_name"], "Hero.rigify")
        self.assertEqual(result["rig_name_requested"], "Hero.rigify")

    def test_the_selection_is_not_restored_and_the_response_says_so(self):
        # Unlike every other mutating tool here: generation's own last act is to
        # select and activate the rig it made, so there is nothing to restore to.
        self.build_metarig_character()
        result = self.run_generate()

        self.assertFalse(result["selection_restored"])
        self.assertEqual(result["active_object_after"], result["rig_object_name"])
        self.assertEqual(
            StubObjectService.bpy.context.view_layer.objects.active.name,
            result["rig_object_name"])

    # -- what becomes of the meta rig, and what that costs later ------------

    def test_hide_is_the_default_and_keeps_a_refit_possible(self):
        self.build_metarig_character()
        result = self.run_generate()

        self.assertEqual(result["metarig_disposition"], "hidden")
        self.assertTrue(self.rig.hide_viewport)
        self.assertTrue(self.rig.hide_render)
        self.assertTrue(result["refit_will_be_possible"])
        self.assertIsNone(result["refit_impossible_reason"])

    def test_keep_leaves_the_meta_rig_visible(self):
        self.build_metarig_character()
        result = self.run_generate(meta_rig_action="keep")

        self.assertEqual(result["metarig_disposition"], "kept")
        self.assertFalse(self.rig.hide_viewport)
        self.assertTrue(result["refit_will_be_possible"])

    def test_delete_removes_the_meta_rig_and_predicts_the_refit_failure(self):
        # This is the state mpfb_refit_human detects after the fact: a generated
        # Rigify rig with no meta rig, where refit() refits the mesh assets,
        # leaves the rig alone and reports nothing to a non-operator caller.
        self.build_metarig_character()
        result = self.run_generate(meta_rig_action="delete")

        self.assertTrue(result["generated"])
        self.assertEqual(result["metarig_disposition"], "deleted")
        self.assertIsNone(result["metarig_name_after"])
        self.assertFalse(result["refit_will_be_possible"])
        self.assertIn("mpfb_refit_human", result["refit_impossible_reason"])
        self.assertIn("mpfb_refit_human", result["message"])
        self.assertIsNone(StubObjectService.bpy.data.objects.get("Human.metarig"))

    def test_the_metarig_name_is_still_reported_after_deletion(self):
        # Read before the call, because the datablock is gone afterwards.
        self.build_metarig_character()
        result = self.run_generate(meta_rig_action="delete")
        self.assertEqual(result["metarig_name"], "Human.metarig")

    # -- a failed generation is not a no-op ---------------------------------

    def test_an_invalid_meta_rig_reports_what_did_happen(self):
        StubRigService.metarig_valid = False
        self.build_metarig_character(dressed=True)
        result = self.run_generate()

        self.assertTrue(result["found"])
        self.assertFalse(result["generated"])
        self.assertIsNone(result["blocked_by"])
        self.assertIsNone(result["rig_object_name"])
        self.assertIn("not a no-op", result["message"])
        # ...and it really was not: everything was deselected and the meta rig
        # made active before Rigify was ever asked.
        self.assertFalse(self.shirt.select_get())
        self.assertTrue(self.rig.select_get())
        self.assertEqual(result["active_object_after"], "Human.metarig")

    def test_an_invalid_meta_rig_reports_the_rename_that_did_happen(self):
        # generate_rigify_rig() renames a meta rig whose name ends in ".rig"
        # before it checks anything, which is how a sub-rig-shaped name gets
        # fixed - and how a rejected generation still changes the file.
        StubRigService.metarig_valid = False
        self.build_metarig_character(rig_name="Human.rig")
        result = self.run_generate()

        self.assertFalse(result["generated"])
        self.assertEqual(result["metarig_name"], "Human.rig")
        self.assertEqual(result["metarig_name_after"], "Human.metarig")
        self.assertTrue(result["metarig_renamed"])
        self.assertIn("Human.metarig", result["message"])

    def test_a_successful_generation_reports_no_rename(self):
        self.build_metarig_character()
        result = self.run_generate()
        self.assertFalse(result["metarig_renamed"])

    # -- preconditions, all answers ----------------------------------------

    def test_an_already_generated_character_is_a_distinct_answer(self):
        # After generation the basemesh's Skeleton relative *is* the generated
        # rig: adjust_children_for_rigify() re-parented it, so the meta rig is
        # no longer among its relatives at all.
        self.build_character(
            rig=True, rig_name="Human.rig", rig_type="rigify_generated.human",
            rig_id="stub-rig-id")
        result = self.run_generate()

        self.assertFalse(result["generated"])
        self.assertEqual(result["blocked_by"], "already_generated")
        self.assertEqual(result["generated_rigs"][0]["name"], "Human.rig")
        self.assertEqual(StubRigService.generate_calls, [])

    def test_a_non_rigify_rig_is_refused_as_not_a_metarig(self):
        self.build_character(rig=True)
        result = self.run_generate()

        self.assertEqual(result["blocked_by"], "not_a_metarig")
        self.assertEqual(result["skeletons"][0]["rig_type"], "default")
        self.assertEqual(StubRigService.generate_calls, [])

    def test_an_unidentifiable_armature_is_refused_rather_than_crashing(self):
        # identify_rig() really can come back with nothing: it starts from None
        # and matches on bone names, and MPFB's own operator poll() would raise
        # on that.
        self.build_character(rig=True, rig_type=None)
        result = self.run_generate()

        self.assertEqual(result["blocked_by"], "not_a_metarig")
        self.assertEqual(StubRigService.generate_calls, [])

    def test_a_character_with_no_armature_is_an_answer(self):
        self.build_character()
        result = self.run_generate()

        self.assertEqual(result["blocked_by"], "no_armature_found")
        self.assertIn("mpfb_add_rig", result["message"])

    def test_rigify_not_enabled_is_an_answer(self):
        StubSystemService.rigify_available = False
        self.build_metarig_character()
        result = self.run_generate()

        self.assertEqual(result["blocked_by"], "rigify_unavailable")
        self.assertFalse(result["rigify_available"])
        self.assertEqual(StubRigService.generate_calls, [])

    def test_an_unresolvable_name_is_an_answer(self):
        self.build_metarig_character()
        result = self.run_generate(name="Nonexistent")

        self.assertFalse(result["found"])
        self.assertEqual(result["blocked_by"], "subject_not_found")
        self.assertEqual(StubRigService.generate_calls, [])

    def test_no_active_object_is_an_answer(self):
        self.build_metarig_character()
        result = self.run_generate(active=None)

        self.assertFalse(result["found"])
        self.assertEqual(result["blocked_by"], "subject_not_found")

    def test_an_unrelated_object_is_an_answer(self):
        self.build_metarig_character()
        self.objects = self.objects + [StubObject("Cube")]
        result = self.run_generate(name="Cube")

        self.assertEqual(result["blocked_by"], "no_armature_found")

    def test_edit_mode_on_either_the_armature_or_blender_is_an_answer(self):
        for kwargs, mode in (({"context_mode": "EDIT_MESH"}, "OBJECT"), ({}, "POSE")):
            with self.subTest(context_mode=kwargs, armature_mode=mode):
                self.build_metarig_character()
                self.rig.mode = mode
                result = self.run_generate(**kwargs)
                self.assertEqual(result["blocked_by"], "not_object_mode")
                self.assertEqual(result["metarig_name"], "Human.metarig")
                self.assertEqual(StubRigService.generate_calls, [])

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_tracks_generated(self):
        self.build_character(rig=True)
        refused = self.run_generate()
        self.assertEqual(refused["blocked_by"], "not_a_metarig")
        self.assertIs(refused["performed"], False)
        self.assertEqual(refused["performed"], refused["generated"])

        self.build_metarig_character()
        generated = self.run_generate()
        self.assertIs(generated["performed"], True)
        self.assertEqual(generated["performed"], generated["generated"])

class PayloadSourceTests(unittest.TestCase):
    def test_the_payload_never_imports_an_mpfb_submodule(self):
        source = codegen.read_payload("generate_rigify_rig.py")
        self.assertNotIn("import_module", source)
        self.assertIn('_MPFB_SERVICES["RigService"]', source)

    def test_the_payload_does_not_pretend_to_restore_the_selection(self):
        # There is nothing to restore to, and claiming otherwise would be the
        # one place in this package where "restore what was borrowed" is a lie.
        source = codegen.read_payload("generate_rigify_rig.py")
        self.assertNotIn("previous_active", source)
        self.assertIn("active_object_after", source)


if __name__ == "__main__":
    unittest.main()
