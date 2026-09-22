# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_set_skin tool: the two coercions, the two side effects, and
the vocabulary check that has to happen before anything is destroyed.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_code`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source executed
against the stub services and a real temporary asset library
(tests/blender_stubs.py's MeshAssetTestCase). That third layer is **frozen**: it
stays while the payload stays, because the payload is half of what FR 032's live
comparison compares.

The library is real because this payload resolves a fragment by walking the
skins roots and because `settings_file_created` claims a file appeared in a
directory where none was - neither of which a mocked filesystem could settle.

What layer 3 cannot say is that any of the five skin types produces the node
tree MPFB's own skin library panel produces. A material is a node tree, and no
stub builds one. That is now checked against a real MPFB in
``bridge/test/tests/ppp_mutating/set_skin_test.py``.

Run with::

    python -m unittest tests.test_set_skin -v
"""

__all__ = ()

import os
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import codegen
from mpfbmcp import backend
from mpfbmcp.tools import set_skin

from tests import fake_bridge
from tests.blender_stubs import (
    MeshAssetTestCase, StubHumanService, StubMaterialService, StubObject)


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    set_skin.register(mcp)
    return mcp._tool_manager._tools["mpfb_set_skin"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape, plus the one vocabulary this package checks on both sides."""

    def setUp(self):
        self.tool = _tool_callable()

    def _sent_source(self, **kwargs):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_code.call_args[0][0]

    def _sent_params(self, **kwargs):
        source = self._sent_source(**kwargs)
        binding = [line for line in source.splitlines()
                   if line.startswith("PARAMS = json.loads(")]
        self.assertEqual(len(binding), 1)
        namespace = {}
        exec("import json\n" + binding[0], namespace)  # noqa: S102
        return namespace["PARAMS"]

    def test_the_arguments_and_defaults_cross_the_socket(self):
        source = self._sent_source(path="/assets/skins/young/young.mhmat")
        self.assertIn("# --- payload: set_skin.py ---", source)
        self.assertIn("# --- shared: asset_sections.py ---", source)
        self.assertEqual(
            self._sent_params(path="/assets/skins/young/young.mhmat"),
            {"name": None, "path": "/assets/skins/young/young.mhmat", "fragment": None,
             "skin_type": "MAKESKIN", "material_instances": True})

    def test_the_default_skin_type_is_the_panels_not_the_signatures(self):
        # set_character_skin() defaults to ENHANCED_SSS; MPFB's settings panel
        # defaults to MAKESKIN. A caller comparing against what they saw in the
        # UI has to get the UI's answer.
        self.assertEqual(
            self._sent_params(path="/assets/skins/young/young.mhmat")["skin_type"],
            "MAKESKIN")

    def test_the_shared_fragment_is_the_one_list_assets_uses(self):
        source = self._sent_source(fragment="young/young.mhmat")
        self.assertIn(codegen.read_shared("asset_sections.py"), source)

    def test_skin_type_is_normalised_and_a_typo_never_crosses_the_socket(self):
        self.assertEqual(
            self._sent_params(path="/a/b.mhmat", skin_type="enhanced_sss")["skin_type"],
            "ENHANCED_SSS")
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            with self.assertRaises(ValueError):
                self.tool(path="/a/b.mhmat", skin_type="ENHANCED_SS")
            send_code.assert_not_called()

    def test_both_identifiers_are_rejected_and_so_is_neither(self):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            with self.assertRaises(ValueError):
                self.tool(path="/a/b.mhmat", fragment="b/b.mhmat")
            with self.assertRaises(ValueError):
                self.tool()
            send_code.assert_not_called()

    def test_layered_is_the_one_type_that_may_name_no_file(self):
        params = self._sent_params(skin_type="LAYERED")
        self.assertIsNone(params["path"])
        self.assertIsNone(params["fragment"])
        # ...and every other type still has to name one.
        for skin_type in ("MAKESKIN", "GAMEENGINE", "ENHANCED", "ENHANCED_SSS"):
            with self.subTest(skin_type=skin_type):
                with self.assertRaises(ValueError):
                    self.tool(skin_type=skin_type)

    def test_an_empty_string_is_not_an_omission(self):
        # An explicitly empty value and an omitted one arise from different
        # mistakes, and here the difference decides whether a file is wanted.
        for kwargs in ({"name": "", "path": "/a/b.mhmat"},
                       {"path": ""},
                       {"fragment": ""},
                       {"path": "", "skin_type": "LAYERED"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.tool(**kwargs)

    def test_material_instances_must_be_a_real_bool(self):
        with self.assertRaises(ValueError):
            self.tool(path="/a/b.mhmat", material_instances="false")

    def test_a_name_is_passed_through_as_the_subject(self):
        self.assertEqual(
            self._sent_params(name="Human.rig", path="/a/b.mhmat")["name"], "Human.rig")


class SetSkinOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the five node trees, what the call destroyed, the active-slot fixup and the settings file - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/set_skin_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_skin": fake_bridge.ok_envelope("set_skin", {"found": True, "applied": True, "performed": True}),
        })

    def test_the_tool_sends_the_set_skin_command(self) -> None:
        self.call(path="/skins/young/young.mhmat")

        self.assertEqual(self.bridge.commands()[-1], "set_skin")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["skin_type"], "MAKESKIN")
        self.assertEqual(params["path"], "/skins/young/young.mhmat")
        self.assertIsNone(params["fragment"])

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(path="/skins/young/young.mhmat")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("asset_sections", str(request))

    def test_material_instances_is_sent_as_requested_and_coerced_on_the_far_side(self) -> None:
        # The coercion is MPFB's panel behaviour and belongs where MPFB is: the
        # tool sends what the caller asked for, and the answer reports both.
        self.call(path="/skins/young/young.mhmat", material_instances=True)

        self.assertIs(
            self.bridge.decoded_requests()[-1]["params"]["material_instances"], True)

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(path="/a.mhmat", skin_type="NOT_A_SKIN")
        with self.assertRaises(ValueError):
            self.call(path="/a.mhmat", material_instances="false")

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="set_skin", state="absent"))

        response = self.call(path="/skins/young/young.mhmat")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GeneratedCodeTests(MeshAssetTestCase):
    """The payload, executed against a real skins library and a stub character."""

    def run_set_skin(self, **params):
        arguments = {
            "name": None,
            "path": None,
            "fragment": None,
            "skin_type": "MAKESKIN",
            "material_instances": True,
        }
        arguments.update(params)
        return self.run_payload(
            "set_skin.py", arguments,
            scene_objects=self.objects,
            all_objects=self.objects,
            active=self.basemesh,
            shared=["asset_sections.py", "performed.py"])

    # --- the happy path ---------------------------------------------------

    def test_a_skin_is_applied_and_the_file_it_landed_on_is_reported(self):
        self.build_character()
        result = self.run_set_skin(path=self.young_skin)

        self.assertTrue(result["applied"])
        self.assertIsNone(result["blocked_by"])
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertEqual(result["resolved_by"], "path")
        self.assertEqual(result["resolved_path"], self.young_skin)
        self.assertEqual(result["skin_type_used"], "MAKESKIN")
        self.assertEqual(result["material_identified_as"], "makeskin")

    def test_a_fragment_is_resolved_under_the_skins_subdir(self):
        # "Material" is the object_type MPFB's section table gives the skins
        # section, and the only thing that maps it to "skins" is that table.
        self.build_character()
        result = self.run_set_skin(fragment="old/old.mhmat")

        self.assertTrue(result["applied"])
        self.assertEqual(result["resolved_by"], "fragment")
        self.assertEqual(result["asset_subdir"], "skins")
        self.assertEqual(result["resolved_path"], self.old_skin)

    def test_the_recorded_fragment_is_reported_beside_the_previous_one(self):
        self.build_character()
        first = self.run_set_skin(path=self.young_skin)
        self.assertIsNone(first["material_source_before"])
        self.assertEqual(first["material_source"], "young/young.mhmat")

        second = self.run_set_skin(path=self.old_skin)
        self.assertEqual(second["material_source_before"], "young/young.mhmat")
        self.assertEqual(second["material_source"], "old/old.mhmat")

    def test_the_subject_may_be_any_object_in_the_family(self):
        self.build_character(rig=True, dressed=True)
        result = self.run_set_skin(name="Human.fedora", path=self.young_skin)

        self.assertEqual(result["subject_name"], "Human.fedora")
        self.assertEqual(result["subject_resolved_by"], "name")
        self.assertEqual(result["basemesh_name"], "Human")

    # --- the two coercions -------------------------------------------------

    def test_material_instances_is_forced_off_for_the_three_types_the_ui_forces(self):
        for skin_type in ("MAKESKIN", "GAMEENGINE", "LAYERED"):
            with self.subTest(skin_type=skin_type):
                self.build_character()
                result = self.run_set_skin(
                    path=self.young_skin, skin_type=skin_type, material_instances=True)
                self.assertTrue(result["material_instances_requested"])
                self.assertFalse(result["material_instances_used"])
                self.assertIn("forces it off", result["message"])

    def test_material_instances_survives_for_the_two_enhanced_types(self):
        for skin_type in ("ENHANCED", "ENHANCED_SSS"):
            with self.subTest(skin_type=skin_type):
                self.build_character(vertex_groups=("lips", "fingernails"))
                result = self.run_set_skin(
                    path=self.young_skin, skin_type=skin_type, material_instances=True)
                self.assertTrue(result["material_instances_used"])

    def test_the_coercion_is_the_payloads_and_not_the_stubs(self):
        # The stub service deliberately does not coerce, so what MPFB is handed
        # is what this tool decided. If the coercion moved into the stub, this
        # assertion would pass while the tool did nothing.
        self.build_character()
        self.run_set_skin(path=self.young_skin, skin_type="MAKESKIN",
                          material_instances=True)
        self.assertEqual(len(StubHumanService.skin_calls), 1)
        self.assertFalse(StubHumanService.skin_calls[0]["material_instances"])

    def test_material_instances_off_is_reported_as_asked_for_rather_than_coerced(self):
        self.build_character(vertex_groups=("lips",))
        result = self.run_set_skin(
            path=self.young_skin, skin_type="ENHANCED", material_instances=False)
        self.assertFalse(result["material_instances_requested"])
        self.assertFalse(result["material_instances_used"])
        self.assertNotIn("forces it off", result["message"])

    def test_instancing_produces_the_extra_slots_and_not_instancing_does_not(self):
        self.build_character(vertex_groups=("lips", "fingernails"))
        instanced = self.run_set_skin(
            path=self.young_skin, skin_type="ENHANCED", material_instances=True)
        slot_names = [slot["material_name"]
                      for entry in instanced["material_slots"] for slot in entry["slots"]]
        self.assertIn("Human.lips", slot_names)
        self.assertIn("Human.fingernails", slot_names)

        self.build_character(vertex_groups=("lips", "fingernails"))
        plain = self.run_set_skin(
            path=self.young_skin, skin_type="ENHANCED", material_instances=False)
        slot_names = [slot["material_name"]
                      for entry in plain["material_slots"] for slot in entry["slots"]]
        self.assertEqual(slot_names, ["Human.body"])

    def test_a_slot_is_created_only_where_the_vertex_group_exists(self):
        self.build_character(vertex_groups=("lips",))
        result = self.run_set_skin(
            path=self.young_skin, skin_type="ENHANCED", material_instances=True)
        slot_names = [slot["material_name"]
                      for entry in result["material_slots"] for slot in entry["slots"]]
        self.assertIn("Human.lips", slot_names)
        self.assertNotIn("Human.fingernails", slot_names)

    # --- the destruction ---------------------------------------------------

    def test_the_materials_that_were_there_are_named_before_they_go(self):
        self.build_character()
        self.basemesh.data.materials.append(
            StubMaterialService.create_empty_material("HandBuilt"))
        result = self.run_set_skin(path=self.young_skin)

        self.assertEqual(
            result["materials_destroyed"],
            [{"object_name": "Human", "materials": ["HandBuilt"]}])
        self.assertIn("node groups included", result["message"])

    def test_the_node_groups_go_too_and_the_call_says_so(self):
        self.build_character()
        self.run_set_skin(path=self.young_skin)
        self.assertIn(("Human", True), StubMaterialService.delete_calls)

    def test_a_body_proxy_gets_the_skin_and_its_materials_are_reported_destroyed(self):
        self.build_character(proxy=True)
        self.body_proxy.data.materials.append(
            StubMaterialService.create_empty_material("ProxyMaterial"))
        result = self.run_set_skin(path=self.young_skin)

        self.assertEqual(result["bodyproxy_name"], "Human.proxy721")
        self.assertEqual(
            result["materials_destroyed"],
            [{"object_name": "Human", "materials": []},
             {"object_name": "Human.proxy721", "materials": ["ProxyMaterial"]}])
        self.assertIn("Human.proxy721", result["message"])
        # The proxy really does end up with a material rather than only a
        # mention in the response.
        self.assertEqual(len(self.body_proxy.data.materials), 1)

    def test_the_body_proxy_is_resolved_here_and_passed_explicitly(self):
        # set_character_skin() would find it itself, but then the response could
        # not name the second object that was modified.
        self.build_character(proxy=True)
        self.run_set_skin(path=self.young_skin)
        self.assertEqual(StubHumanService.skin_calls[0]["bodyproxy"], "Human.proxy721")

    def test_a_character_with_no_proxy_reports_null_rather_than_omitting_it(self):
        self.build_character()
        result = self.run_set_skin(path=self.young_skin)
        self.assertIsNone(result["bodyproxy_name"])
        self.assertIsNone(StubHumanService.skin_calls[0]["bodyproxy"])

    # --- LAYERED, the one type that needs no file --------------------------

    def test_layered_with_no_mhmat_is_applied(self):
        self.build_character()
        result = self.run_set_skin(skin_type="LAYERED")

        self.assertTrue(result["applied"])
        self.assertIsNone(result["resolved_path"])
        self.assertIsNone(result["resolved_by"])
        self.assertEqual(result["material_identified_as"], "layered_skin")

    def test_layered_with_no_mhmat_leaves_the_previous_material_source_alone(self):
        # MPFB records material_source only when it was given a file, so the
        # property keeps a value that no longer describes the material. Reported
        # rather than papered over.
        self.build_character()
        self.run_set_skin(path=self.young_skin)
        result = self.run_set_skin(skin_type="LAYERED")

        self.assertEqual(result["material_source_before"], "young/young.mhmat")
        self.assertEqual(result["material_source"], "young/young.mhmat")
        self.assertIn("recorded no material_source", result["message"])

    def test_layered_with_a_file_still_uses_it(self):
        self.build_character()
        result = self.run_set_skin(path=self.young_skin, skin_type="LAYERED")
        self.assertEqual(result["resolved_path"], self.young_skin)
        self.assertEqual(result["material_source"], "young/young.mhmat")

    # --- the two facts nothing in Blender shows ----------------------------

    def test_the_settings_file_is_created_once_and_reported_once(self):
        self.assertFalse(os.path.exists(self.enhanced_settings_target))
        self.build_character(vertex_groups=("lips",))
        first = self.run_set_skin(
            path=self.young_skin, skin_type="ENHANCED_SSS", material_instances=True)

        self.assertTrue(first["settings_file_created"])
        self.assertEqual(first["settings_file_path"], self.enhanced_settings_target)
        self.assertTrue(os.path.exists(self.enhanced_settings_target))
        self.assertIn("user config", first["message"])

        second = self.run_set_skin(
            path=self.old_skin, skin_type="ENHANCED_SSS", material_instances=True)
        self.assertFalse(second["settings_file_created"])

    def test_the_default_call_writes_no_file_at_all(self):
        # The copy is gated on material_instances rather than on the skin type,
        # and MAKESKIN is coerced to no instances - so nothing outside the
        # .blend is touched by an ordinary call.
        self.build_character(vertex_groups=("lips",))
        result = self.run_set_skin(path=self.young_skin)
        self.assertFalse(result["settings_file_created"])
        self.assertFalse(os.path.exists(self.enhanced_settings_target))

    def test_an_enhanced_skin_without_instances_writes_no_file_either(self):
        self.build_character(vertex_groups=("lips",))
        result = self.run_set_skin(
            path=self.young_skin, skin_type="ENHANCED", material_instances=False)
        self.assertFalse(result["settings_file_created"])
        self.assertFalse(os.path.exists(self.enhanced_settings_target))

    def test_the_scale_assumption_follows_mpfbs_own_thresholds(self):
        # 1.0 is MPFB's default scale_factor and the first threshold is > 0.9,
        # so an ordinary character is decimetre-scaled. A caller expecting METER
        # would be wrong, which is exactly why this is reported.
        for scale, expected in ((0.1, "METER"), (1.0, "DECIMETER"), (10.0, "CENTIMETER")):
            with self.subTest(scale=scale):
                self.build_character()
                self.basemesh.properties["GEN"]["scale_factor"] = scale
                result = self.run_set_skin(path=self.young_skin, skin_type="ENHANCED_SSS")
                self.assertEqual(result["scale_assumption"], expected)

    def test_the_scale_assumption_is_null_for_the_types_that_do_not_use_it(self):
        for skin_type in ("MAKESKIN", "GAMEENGINE", "LAYERED"):
            with self.subTest(skin_type=skin_type):
                self.build_character()
                result = self.run_set_skin(path=self.young_skin, skin_type=skin_type)
                self.assertIsNone(result["scale_assumption"])

    # --- the UI fixup ------------------------------------------------------

    def test_the_body_slot_is_made_active_on_both_objects(self):
        self.build_character(proxy=True, vertex_groups=("lips", "fingernails"))
        result = self.run_set_skin(
            path=self.young_skin, skin_type="ENHANCED", material_instances=True)

        self.assertEqual(result["active_body_slot"]["basemesh"], "Human.body")
        self.assertEqual(result["active_body_slot"]["bodyproxy"], "Human.body")
        # The slot index really moved off 0 on the proxy, which is the point:
        # the user's material panel would otherwise be showing a fingernail.
        active = dict((entry["object_name"], entry["active_material_index"])
                      for entry in result["material_slots"])
        self.assertEqual(active["Human"], 0)

    # --- preconditions as answers -----------------------------------------

    def test_an_unknown_skin_type_changes_nothing_at_all(self):
        # The sharpest precondition in the project: MPFB's own function would
        # have deleted every material on the character before discovering this.
        self.build_character()
        self.basemesh.data.materials.append(
            StubMaterialService.create_empty_material("HandBuilt"))
        result = self.run_set_skin(path=self.young_skin, skin_type="ENHANCED_SS")

        self.assertFalse(result["applied"])
        self.assertEqual(result["blocked_by"], "unknown_skin_type")
        self.assertIn("ENHANCED_SSS", result["known_skin_types"])
        self.assertEqual(StubHumanService.skin_calls, [])
        self.assertEqual([material.name for material in self.basemesh.data.materials],
                         ["HandBuilt"])

    def test_every_refusal_carries_the_vocabulary(self):
        # A caller that got something *else* wrong should not have to guess
        # whether the missing field means anything.
        self.build_character()
        for params in ({"path": os.path.join(self.system_root, "nope.mhmat")},
                       {"path": self.young_skin, "skin_type": "NOPE"},
                       {"skin_type": "ENHANCED"},
                       {"name": "Nope", "path": self.young_skin}):
            with self.subTest(params=params):
                result = self.run_set_skin(**params)
                self.assertFalse(result["applied"])
                self.assertEqual(len(result["known_skin_types"]), 5)

    def test_a_missing_basemesh_is_an_answer(self):
        self.build_character()
        stray = StubObject("Cube")
        self.objects = self.objects + [stray]
        result = self.run_set_skin(name="Cube", path=self.young_skin)

        self.assertFalse(result["found"])
        self.assertEqual(result["blocked_by"], "subject_not_found")
        self.assertEqual(StubHumanService.skin_calls, [])

    def test_an_unknown_name_is_an_answer(self):
        self.build_character()
        result = self.run_set_skin(name="Nope", path=self.young_skin)
        self.assertEqual(result["blocked_by"], "subject_not_found")
        self.assertIn("Nope", result["message"])

    def test_no_active_object_is_an_answer(self):
        self.build_character()
        result = self.run_payload(
            "set_skin.py",
            {"name": None, "path": self.young_skin, "fragment": None,
             "skin_type": "MAKESKIN", "material_instances": True},
            scene_objects=self.objects, all_objects=self.objects, active=None,
            shared=["asset_sections.py", "performed.py"])
        self.assertEqual(result["blocked_by"], "subject_not_found")
        self.assertEqual(result["subject_resolved_by"], "active")

    def test_a_missing_file_is_an_answer(self):
        self.build_character()
        result = self.run_set_skin(path=os.path.join(self.system_root, "nope.mhmat"))
        self.assertEqual(result["blocked_by"], "skin_not_found")
        self.assertEqual(StubHumanService.skin_calls, [])

    def test_an_unresolvable_fragment_names_the_subdir_it_searched(self):
        self.build_character()
        result = self.run_set_skin(fragment="nope/nope.mhmat")
        self.assertEqual(result["blocked_by"], "skin_not_found")
        self.assertEqual(result["asset_subdir"], "skins")
        self.assertIn("skins", result["message"])

    def test_no_file_for_a_type_that_needs_one_is_an_answer_rather_than_a_crash(self):
        # Rejected in the tool module too, but the payload has to be able to
        # answer it - a caller reaching the payload another way still gets a
        # sentence rather than a stripped character.
        self.build_character()
        result = self.run_set_skin(skin_type="ENHANCED")
        self.assertEqual(result["blocked_by"], "no_material_given")
        self.assertEqual(StubHumanService.skin_calls, [])

    def test_edit_mode_is_an_answer_and_nothing_is_changed(self):
        self.build_character()
        self.basemesh.mode = "EDIT"
        result = self.run_set_skin(path=self.young_skin)
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(StubHumanService.skin_calls, [])

    def test_the_context_mode_is_checked_as_well_as_the_objects(self):
        self.build_character()
        result = self.run_payload(
            "set_skin.py",
            {"name": None, "path": self.young_skin, "fragment": None,
             "skin_type": "MAKESKIN", "material_instances": True},
            scene_objects=self.objects, all_objects=self.objects, active=self.basemesh,
            shared=["asset_sections.py", "performed.py"], context_mode="POSE")
        self.assertEqual(result["blocked_by"], "not_object_mode")

    # --- a failed skin is not a no-op --------------------------------------

    def test_a_failure_inside_mpfb_is_an_answer_naming_what_was_lost(self):
        self.build_character()
        self.basemesh.data.materials.append(
            StubMaterialService.create_empty_material("HandBuilt"))
        StubHumanService.skin_raises = ValueError("Basemesh has no material")
        result = self.run_set_skin(path=self.young_skin)

        self.assertFalse(result["applied"])
        self.assertEqual(result["blocked_by"], "skin_failed")
        self.assertEqual(
            result["materials_destroyed"],
            [{"object_name": "Human", "materials": ["HandBuilt"]}])
        self.assertIn("cannot be restored", result["message"])

    # --- restore what was borrowed -----------------------------------------

    def test_the_previous_active_object_and_selection_are_restored(self):
        self.build_character(rig=True)
        self.assertFalse(self.basemesh.select_get())
        self.run_payload(
            "set_skin.py",
            {"name": "Human", "path": self.young_skin, "fragment": None,
             "skin_type": "MAKESKIN", "material_instances": True},
            scene_objects=self.objects, all_objects=self.objects, active=self.rig,
            shared=["asset_sections.py", "performed.py"])

        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.rig)
        self.assertFalse(self.basemesh.select_get())

    def test_the_restore_happens_even_when_the_skin_failed(self):
        self.build_character(rig=True)
        StubHumanService.skin_raises = ValueError("boom")
        self.run_payload(
            "set_skin.py",
            {"name": "Human", "path": self.young_skin, "fragment": None,
             "skin_type": "MAKESKIN", "material_instances": True},
            scene_objects=self.objects, all_objects=self.objects, active=self.rig,
            shared=["asset_sections.py", "performed.py"])

        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.rig)
        self.assertFalse(self.basemesh.select_get())

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_tracks_applied(self):
        self.build_character()

        applied = self.run_set_skin(path=self.young_skin)
        self.assertIs(applied["performed"], True)
        self.assertEqual(applied["performed"], applied["applied"])

        refused = self.run_set_skin(name="Nope", path=self.young_skin)
        self.assertEqual(refused["blocked_by"], "subject_not_found")
        self.assertIs(refused["performed"], False)
        self.assertEqual(refused["performed"], refused["applied"])


if __name__ == "__main__":
    unittest.main()
