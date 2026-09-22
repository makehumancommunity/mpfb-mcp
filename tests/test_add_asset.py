# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_add_asset tool: argument validation, and the generated code's
vocabulary checks, defaulting, observation and reporting.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_code`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source executed
against the stub services and a real temporary asset library
(tests/blender_stubs.py's MeshAssetTestCase). That third layer is **frozen**: it
stays while the payload stays, because the payload is half of what FR 032's live
comparison compares.

The library is real because these payloads read the MHCLO, list the directory
beside it and resolve a fragment by walking the asset roots; mocking the
filesystem away would leave nothing under test.

What layer 3 cannot say is that an asset equipped through this tool is
indistinguishable from the same asset equipped through MPFB's own asset library
panel - same fit, same delete group, same material. That is now checked against
a real MPFB in ``bridge/test/tests/ppp_mutating/add_asset_test.py``.

Run with::

    python -m unittest tests.test_add_asset -v
"""

__all__ = ()

import os
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import codegen
from mpfbmcp import backend
from mpfbmcp.tools import add_asset

from tests import fake_bridge
from tests.blender_stubs import (
    MeshAssetTestCase, StubAssetService, StubHumanService, StubObject,
    StubObjectService, write_mhclo)
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
    add_asset.register(mcp)
    return mcp._tool_manager._tools["mpfb_add_asset"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape only. Which asset types exist is MPFB's own table, read in Blender."""

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
        source = self._sent_source(asset_type="Clothes", path="/assets/fedora/fedora.mhclo")
        self.assertIn("# --- payload: add_asset.py ---", source)
        self.assertIn("# --- shared: asset_sections.py ---", source)
        self.assertEqual(
            self._sent_params(asset_type="Clothes", path="/assets/fedora/fedora.mhclo"),
            {"name": None, "path": "/assets/fedora/fedora.mhclo", "fragment": None,
             "asset_type": "Clothes", "material_type": None, "subdiv_levels": 1,
             "set_up_rigging": True, "interpolate_weights": True, "import_subrig": True,
             "import_weights": True})

    def test_the_shared_fragment_is_the_one_list_assets_uses(self):
        # Not decoration: if these two ever name different fragments, the
        # catalogue and this tool can disagree about which subdir a type lives
        # in - and an asset that was just listed comes back "not installed".
        source = self._sent_source(asset_type="Hair", fragment="ponytail/ponytail.mhclo")
        self.assertIn(codegen.read_shared("asset_sections.py"), source)

    def test_asset_type_is_required_and_is_rejected_before_any_code_is_generated(self):
        # The whole reason it is required: MPFB's own default of "Clothes" is
        # wrong for six of the eight types and wrong in a way nothing reports.
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            with self.assertRaises(TypeError):
                self.tool(path="/assets/fedora/fedora.mhclo")
            with self.assertRaises(ValueError):
                self.tool(asset_type="   ", path="/assets/fedora/fedora.mhclo")
            with self.assertRaises(ValueError):
                self.tool(asset_type=None, path="/assets/fedora/fedora.mhclo")
        send_code.assert_not_called()

    def test_both_path_and_fragment_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.tool(asset_type="Clothes", path="/assets/fedora/fedora.mhclo",
                      fragment="fedora/fedora.mhclo")
        self.assertIn("not both", str(raised.exception))

    def test_neither_path_nor_fragment_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.tool(asset_type="Clothes")
        self.assertIn("Give either path or fragment", str(raised.exception))

    def test_an_explicitly_empty_identifier_is_not_treated_as_an_omission(self):
        # "" and omitted arise from different mistakes, and quietly reading the
        # first as the second would turn "I built the path wrong" into "neither
        # was given".
        with self.assertRaises(ValueError):
            self.tool(asset_type="Clothes", path="  ")

    def test_subdiv_levels_rejects_a_bool_and_a_negative(self):
        # bool is a subclass of int, so subdiv_levels=True would silently mean 1.
        with self.assertRaises(ValueError):
            self.tool(asset_type="Clothes", path="/a.mhclo", subdiv_levels=True)
        with self.assertRaises(ValueError):
            self.tool(asset_type="Clothes", path="/a.mhclo", subdiv_levels=-1)

    def test_the_four_flags_must_be_real_bools(self):
        for flag in ("set_up_rigging", "interpolate_weights", "import_subrig",
                     "import_weights"):
            with self.subTest(flag=flag):
                with self.assertRaises(ValueError):
                    self.tool(asset_type="Clothes", path="/a.mhclo", **{flag: "false"})

    def test_the_material_type_vocabulary_is_not_checked_here(self):
        # Deliberately: which material types are valid for which asset type is
        # MPFB's own table plus its own eye special case, and a list kept here
        # would drift from it.
        params = self._sent_params(
            asset_type="Clothes", path="/a.mhclo", material_type="NOT_A_MATERIAL")
        self.assertEqual(params["material_type"], "NOT_A_MATERIAL")

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is carried through with its status and message intact and
        # an `error` slug added, which is the seam's one mapping: a caller
        # branches on `error` without having to learn which transport answered.
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "error", "message": "no MPFB"}
            response = self.tool(asset_type="Clothes", path="/a.mhclo")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)


class AddAssetOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the type vocabulary, the delete group, the proxy extras and every warning - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/add_asset_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "add_asset": fake_bridge.ok_envelope("add_asset", {"found": True, "added": True, "performed": True}),
        })

    def test_the_tool_sends_the_add_asset_command(self) -> None:
        self.call(asset_type="Clothes", path="/a.mhclo")

        self.assertEqual(self.bridge.commands()[-1], "add_asset")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["asset_type"], "Clothes")
        self.assertEqual(params["path"], "/a.mhclo")
        self.assertIsNone(params["fragment"])
        self.assertEqual(params["subdiv_levels"], 1)

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(asset_type="Clothes", path="/a.mhclo")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("asset_sections", str(request))

    def test_exactly_one_of_path_and_fragment_is_enforced_here(self) -> None:
        # Both or neither is a mistake the caller can fix without looking at the
        # scene, and it is the same refusal on either transport.
        with self.assertRaises(ValueError):
            self.call(asset_type="Clothes")
        with self.assertRaises(ValueError):
            self.call(asset_type="Clothes", path="/a.mhclo", fragment="pack/a.mhclo")

        self.assertEqual(self.bridge.requests, [])

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(asset_type="", path="/a.mhclo")
        with self.assertRaises(ValueError):
            self.call(asset_type="Clothes", path="/a.mhclo", subdiv_levels=True)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="add_asset", state="absent"))

        response = self.call(asset_type="Clothes", path="/a.mhclo")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GeneratedCodeTests(MeshAssetTestCase):
    """The payload, executed against a real asset library and a stub character."""

    def run_add_asset(self, **params):
        arguments = {
            "name": None,
            "path": None,
            "fragment": None,
            "asset_type": "Clothes",
            "material_type": None,
            "subdiv_levels": 1,
            "set_up_rigging": True,
            "interpolate_weights": True,
            "import_subrig": True,
            "import_weights": True,
        }
        arguments.update(params)
        result = self.run_payload(
            "add_asset.py", arguments,
            scene_objects=self.objects,
            all_objects=self.objects,
            active=self.basemesh,
            shared=["asset_sections.py", "performed.py"])
        # Carry the objects the payload created into the next call, so two
        # equips in one test see each other - which is what makes the .001
        # naming observable at all.
        self.objects = list(StubObjectService.all_objects)
        return result

    # --- the happy path ---------------------------------------------------

    def test_a_garment_is_equipped_and_reported_by_the_name_it_got(self):
        self.build_character()
        result = self.run_add_asset(path=self.fedora)
        self.assertTrue(result["added"])
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertEqual(result["asset_object_name"], "Human.fedora")
        self.assertEqual(result["object_type_recorded"], "Clothes")
        self.assertEqual(result["asset_source"], "fedora/fedora.mhclo")
        self.assertEqual(result["resolved_by"], "path")
        self.assertEqual(result["resolved_path"], self.fedora)

    def test_the_subject_may_be_any_object_in_the_family(self):
        self.build_character(rig=True)
        result = self.run_add_asset(name="Human.rig", path=self.fedora)
        self.assertEqual(result["subject_name"], "Human.rig")
        self.assertEqual(result["subject_resolved_by"], "name")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_a_second_copy_of_one_asset_gets_the_uniquified_name(self):
        # The reason asset_object_name is read off the object rather than
        # predicted: this is the address mpfb_remove_asset needs, and predicting
        # it would take the wrong garment off.
        self.build_character()
        first = self.run_add_asset(path=self.fedora)
        second = self.run_add_asset(path=self.fedora)
        self.assertEqual(first["asset_object_name"], "Human.fedora")
        self.assertEqual(second["asset_object_name"], "Human.fedora.001")

    def test_the_previous_active_object_and_selection_are_restored(self):
        self.build_character()
        self.run_add_asset(path=self.fedora)
        self.assertIn("Human", StubObjectService.activations)
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.basemesh)
        self.assertFalse(self.basemesh.select_get())

    # --- the two identifiers ---------------------------------------------

    def test_a_fragment_is_resolved_against_the_subdir_its_asset_type_names(self):
        self.build_character()
        result = self.run_add_asset(asset_type="Hair", fragment="ponytail/ponytail.mhclo")
        self.assertEqual(result["resolved_by"], "fragment")
        self.assertEqual(result["asset_subdir"], "hair")
        self.assertEqual(result["resolved_path"], self.ponytail)
        self.assertIn(("ponytail/ponytail.mhclo", "hair"), StubAssetService.calls)

    def test_an_ambiguous_fragment_still_reports_the_path_it_chose(self):
        # find_asset_absolute_path() matches on basename, so two roots holding
        # fedora.mhclo is a coin toss. The response has to expose which side it
        # landed on rather than absorbing it.
        self.build_character()
        result = self.run_add_asset(fragment="fedora/fedora.mhclo")
        self.assertTrue(result["added"])
        self.assertIn(result["resolved_path"], (self.fedora, self.other_fedora))
        self.assertTrue(os.path.isfile(result["resolved_path"]))

    def test_list_assets_and_add_asset_resolve_a_fragment_the_same_way(self):
        # The point of the shared fragment: the catalogue reports a fragment and
        # an object_type, and this tool has to be able to turn that pair back
        # into the same file. Both run against the same library on disk.
        self.build_character()
        listing = self.run_payload(
            "list_assets.py",
            {"asset_subdir": "hair", "name_contains": None, "pack": None,
             "limit": 200, "offset": 0, "refresh": False},
            scene_objects=self.objects, all_objects=self.objects, active=self.basemesh,
            shared=["asset_sections.py"])
        entry = listing["assets"][0]
        result = self.run_add_asset(
            asset_type=entry["object_type"], fragment=entry["fragment"])
        self.assertEqual(result["resolved_path"], entry["path"])
        self.assertEqual(result["asset_subdir"], entry["asset_subdir"])

    # --- the vocabulary --------------------------------------------------

    def test_an_unknown_asset_type_is_an_answer_with_the_vocabulary_beside_it(self):
        self.build_character()
        result = self.run_add_asset(asset_type="Trousers", path=self.fedora)
        self.assertFalse(result["added"])
        self.assertEqual(result["blocked_by"], "unknown_asset_type")
        self.assertIn("Clothes", result["known_asset_types"])
        self.assertEqual(StubHumanService.add_asset_calls, [])

    def test_the_catalogue_rows_that_are_not_mesh_assets_are_refused(self):
        # skins, poses and ink_layers are in mpfb_list_assets' answer but are
        # not objects that can be imported, so their object_types must not be
        # accepted here.
        self.build_character()
        for object_type in ("Material", "Pose", "Other"):
            with self.subTest(object_type=object_type):
                result = self.run_add_asset(asset_type=object_type, path=self.fedora)
                self.assertEqual(result["blocked_by"], "unknown_asset_type")
                self.assertNotIn(object_type, result["known_asset_types"])

    def test_the_asset_type_is_normalised_the_way_mpfb_normalises_it(self):
        self.build_character()
        result = self.run_add_asset(asset_type="hair", fragment="ponytail/ponytail.mhclo")
        self.assertTrue(result["added"])
        self.assertEqual(result["requested_asset_type"], "hair")
        self.assertEqual(result["object_type_recorded"], "Hair")
        self.assertEqual(StubHumanService.add_asset_calls[0]["asset_type"], "Hair")

    # --- material types ---------------------------------------------------

    def test_material_type_defaults_to_makeskin_for_a_body_part(self):
        self.build_character()
        result = self.run_add_asset(asset_type="Hair", fragment="ponytail/ponytail.mhclo")
        self.assertEqual(result["material_type_used"], "MAKESKIN")
        self.assertTrue(result["material_type_defaulted"])
        self.assertTrue(result["material_created"])

    def test_material_type_defaults_to_none_for_a_proxy(self):
        # What _check_add_proxy() passes, and not what the function signature
        # defaults to.
        self.build_character()
        result = self.run_add_asset(
            asset_type="Proxymeshes", fragment="proxy721/proxy721.mhclo")
        self.assertEqual(result["material_type_used"], "NONE")
        self.assertFalse(result["material_created"])

    def test_procedural_eyes_is_accepted_for_eyes_and_refused_for_hair(self):
        self.build_character()
        accepted = self.run_add_asset(
            asset_type="Eyes", fragment="lowpoly/lowpoly.mhclo",
            material_type="PROCEDURAL_EYES")
        self.assertTrue(accepted["added"])
        self.assertEqual(accepted["material_type_used"], "PROCEDURAL_EYES")
        refused = self.run_add_asset(
            asset_type="Hair", fragment="ponytail/ponytail.mhclo",
            material_type="PROCEDURAL_EYES")
        self.assertEqual(refused["blocked_by"], "invalid_material_type")
        self.assertNotIn("PROCEDURAL_EYES", refused["allowed_material_types"])

    def test_material_none_on_an_asset_that_names_one_is_warned_about(self):
        # It deletes the imported mesh's materials and creates nothing, which is
        # not obvious from the argument name.
        self.build_character()
        result = self.run_add_asset(path=self.fedora, material_type="NONE")
        self.assertTrue(result["added"])
        self.assertFalse(result["material_created"])
        self.assertTrue(result["mhclo_names_material"])
        self.assertTrue(any("deleted" in warning for warning in result["warnings"]))

    def test_an_mhclo_with_no_material_line_is_warned_about(self):
        # MPFB only logs this, so an object silently ends up with no material.
        self.build_character()
        result = self.run_add_asset(path=self.plain)
        self.assertTrue(result["added"])
        self.assertFalse(result["mhclo_names_material"])
        self.assertFalse(result["material_created"])
        self.assertTrue(any("names no material" in warning for warning in result["warnings"]))

    # --- rigging, and the ordering constraint ----------------------------

    def test_an_unrigged_character_gets_a_parented_asset_and_a_warning(self):
        self.build_character(rig=False)
        result = self.run_add_asset(path=self.fedora)
        self.assertIsNone(result["rigged_to"])
        self.assertEqual(result["parented_to"], "Human")
        self.assertEqual(result["armature_modifier_targets"], [])
        self.assertTrue(any("no rig" in warning for warning in result["warnings"]))

    def test_a_rigged_character_gets_a_rigged_asset(self):
        self.build_character(rig=True)
        result = self.run_add_asset(path=self.fedora)
        self.assertEqual(result["rigged_to"], "Human.rig")
        self.assertEqual(result["armature_modifier_targets"], ["Human.rig"])

    def test_a_subrig_is_imported_and_named(self):
        self.build_character(rig=True)
        result = self.run_add_asset(path=self.rigged)
        self.assertEqual(result["subrig_object_name"], "Human.rigged.rig")
        self.assertEqual(result["parented_to"], "Human.rigged.rig")

    def test_a_generated_rigify_rig_is_reported_as_an_ordering_mistake(self):
        # The other end of FR 009's constraint: the asset is rigged, but
        # adjust_children_for_rigify() has already run and will not run again.
        self.build_character(rig=True, rig_type="rigify_generated.human", rig_id="abc")
        result = self.run_add_asset(path=self.fedora)
        self.assertEqual(result["rigged_to"], "Human.rig")
        self.assertTrue(any("generated" in warning for warning in result["warnings"]))

    def test_missing_weights_beside_the_asset_are_reported(self):
        self.build_character(rig=True)
        with_weights = self.run_add_asset(path=self.rigged)
        self.assertEqual(with_weights["weights_files_beside_asset"], ["rigged.mhw"])
        without = self.run_add_asset(path=self.fedora)
        self.assertEqual(without["weights_files_beside_asset"], [])
        self.assertTrue(any("weights" in warning for warning in without["warnings"]))

    # --- the delete group -------------------------------------------------

    def test_the_delete_group_and_its_masks_are_reported(self):
        self.build_character()
        result = self.run_add_asset(path=self.fedora)
        self.assertEqual(result["delete_group_name"], "Delete.fedora")
        self.assertEqual(result["delete_group_applied_to"], ["Human"])
        self.assertIn("Delete.fedora", result["vertex_groups_created_on_basemesh"])

    def test_a_clothes_asset_masks_the_body_proxy_too(self):
        self.build_character(proxy=True)
        result = self.run_add_asset(path=self.fedora)
        self.assertEqual(
            result["delete_group_applied_to"], ["Human", "Human.proxy721"])

    def test_a_body_part_does_not_mask_the_body_proxy(self):
        # The clothes branch is keyed on the raw asset_type, so a garment
        # labelled Hair does not get it - correct behaviour, and exactly why the
        # argument must be right.
        self.build_character(proxy=True)
        result = self.run_add_asset(asset_type="Hair", fragment="ponytail/ponytail.mhclo")
        self.assertEqual(result["delete_group_applied_to"], ["Human"])

    def test_an_mhclo_with_no_delete_verts_gets_no_group_at_all(self):
        self.build_character()
        result = self.run_add_asset(path=self.plain)
        self.assertIsNone(result["delete_group_name"])
        self.assertEqual(result["delete_group_applied_to"], [])
        self.assertIn("no delete group", result["message"])

    # --- subdivision ------------------------------------------------------

    def test_subdiv_levels_zero_adds_no_modifier(self):
        self.build_character()
        self.assertTrue(self.run_add_asset(path=self.fedora)["subdiv_modifier_added"])
        self.assertFalse(
            self.run_add_asset(path=self.fedora, subdiv_levels=0)["subdiv_modifier_added"])

    # --- proxies ----------------------------------------------------------

    def test_a_proxy_gets_the_four_extras_check_add_proxy_does(self):
        self.build_character()
        result = self.run_add_asset(
            asset_type="Proxymeshes", fragment="proxy721/proxy721.mhclo")
        extras = result["proxy_extras"]
        self.assertTrue(extras["basemesh_hidden"])
        self.assertTrue(extras["basemesh_hide_modifier_present"])
        self.assertTrue(extras["scale_factor_copied"])
        self.assertEqual(extras["extra_vertex_groups_created"], ["HelperGeometry", "Left eye"])
        self.assertTrue(extras["corrective_applied"])
        self.assertEqual(
            StubHumanService.corrective_calls, [result["asset_object_name"]])

    def test_the_hide_modifier_is_added_beside_mpfbs_own_body_mask(self):
        # The regression this exists for: `Hide helpers` is a MASK modifier on
        # the vertex group "body" and every basemesh MPFB creates has one, so a
        # guard asking only "is there a mask on body?" is always satisfied and
        # the proxy's own hide modifier is never added. The two differ in
        # `invert_vertex_group`, and only the inverted one hides the body.
        self.build_character()
        masks_before = [
            (modifier.name, modifier.vertex_group, modifier.invert_vertex_group)
            for modifier in self.basemesh.modifiers if modifier.type == "MASK"]
        self.assertEqual(masks_before, [("Hide helpers", "body", False)])

        result = self.run_add_asset(
            asset_type="Proxymeshes", fragment="proxy721/proxy721.mhclo")

        masks_after = [
            (modifier.name, modifier.vertex_group, modifier.invert_vertex_group)
            for modifier in self.basemesh.modifiers if modifier.type == "MASK"]
        self.assertIn(("Hide base mesh", "body", True), masks_after)
        self.assertIn(("Hide helpers", "body", False), masks_after)
        self.assertTrue(result["proxy_extras"]["basemesh_hidden"])

    def test_a_second_proxy_does_not_add_a_second_hide_modifier(self):
        # The guard still has to be a guard: what it must not do is confuse
        # MPFB's own mask for the one it is looking for.
        self.build_character()
        self.run_add_asset(asset_type="Proxymeshes", fragment="proxy721/proxy721.mhclo")
        result = self.run_add_asset(
            asset_type="Proxymeshes", fragment="plainproxy/plainproxy.mhclo")
        inverted = [modifier.name for modifier in self.basemesh.modifiers
                    if modifier.type == "MASK" and modifier.invert_vertex_group
                    and modifier.vertex_group == "body"]
        self.assertEqual(inverted, ["Hide base mesh"])
        self.assertFalse(result["proxy_extras"]["basemesh_hidden"])
        self.assertTrue(result["proxy_extras"]["basemesh_hide_modifier_present"])

    def test_a_proxy_whose_uuid_has_no_extra_groups_is_the_ordinary_case(self):
        self.build_character()
        result = self.run_add_asset(
            asset_type="Proxymeshes", fragment="plainproxy/plainproxy.mhclo")
        self.assertEqual(result["proxy_extras"]["extra_vertex_groups_created"], [])
        self.assertEqual(result["proxy_extras"]["uuid"], "a-uuid-with-no-extra-groups")

    def test_a_garment_gets_no_proxy_extras_at_all(self):
        self.build_character()
        result = self.run_add_asset(path=self.fedora)
        self.assertIsNone(result["proxy_extras"])
        self.assertEqual(StubHumanService.corrective_calls, [])

    def test_a_renamed_proxy_corrective_degrades_rather_than_failing(self):
        # It is a private name reached with getattr(), so its disappearance is a
        # reportable degradation rather than an exception.
        self.build_character()
        with mock.patch.object(StubHumanService, "_proxy_corrective", None):
            result = self.run_add_asset(
                asset_type="Proxymeshes", fragment="proxy721/proxy721.mhclo")
        self.assertTrue(result["added"])
        self.assertFalse(result["proxy_extras"]["corrective_applied"])
        self.assertTrue(any("_proxy_corrective" in w for w in result["warnings"]))

    # --- preconditions as answers ----------------------------------------

    def test_no_active_object_is_an_answer(self):
        self.build_character()
        result = self.run_payload(
            "add_asset.py",
            {"name": None, "path": self.fedora, "fragment": None, "asset_type": "Clothes",
             "material_type": None, "subdiv_levels": 1, "set_up_rigging": True,
             "interpolate_weights": True, "import_subrig": True, "import_weights": True},
            scene_objects=self.objects, all_objects=self.objects, active=None,
            shared=["asset_sections.py", "performed.py"])
        self.assertEqual(result["blocked_by"], "subject_not_found")
        self.assertFalse(result["found"])
        self.assertEqual(StubHumanService.add_asset_calls, [])

    def test_an_object_that_is_not_part_of_a_character_is_an_answer(self):
        self.build_character()
        stray = StubObject("Cube")
        result = self.run_payload(
            "add_asset.py",
            {"name": "Cube", "path": self.fedora, "fragment": None, "asset_type": "Clothes",
             "material_type": None, "subdiv_levels": 1, "set_up_rigging": True,
             "interpolate_weights": True, "import_subrig": True, "import_weights": True},
            scene_objects=self.objects + [stray], all_objects=self.objects + [stray],
            active=None, shared=["asset_sections.py", "performed.py"])
        self.assertEqual(result["blocked_by"], "subject_not_found")

    def test_a_path_naming_no_file_is_an_answer(self):
        self.build_character()
        result = self.run_add_asset(path=os.path.join(self.system_root, "nope.mhclo"))
        self.assertEqual(result["blocked_by"], "asset_not_found")
        self.assertEqual(StubHumanService.add_asset_calls, [])

    def test_a_fragment_resolving_to_nothing_is_an_answer(self):
        self.build_character()
        result = self.run_add_asset(fragment="nope/nope.mhclo")
        self.assertEqual(result["blocked_by"], "asset_not_found")
        self.assertIsNone(result["resolved_path"])
        self.assertIn("clothes", result["message"])

    def test_edit_mode_is_an_answer_and_nothing_is_equipped(self):
        self.build_character()
        self.basemesh.mode = "EDIT"
        result = self.run_add_asset(path=self.fedora)
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(StubHumanService.add_asset_calls, [])

    def test_another_object_in_edit_mode_also_blocks(self):
        # bpy.ops polls on the *context* mode, so an unrelated object left in
        # edit mode fails the import even though the basemesh looks fine.
        self.build_character()
        result = self.run_payload(
            "add_asset.py",
            {"name": None, "path": self.fedora, "fragment": None, "asset_type": "Clothes",
             "material_type": None, "subdiv_levels": 1, "set_up_rigging": True,
             "interpolate_weights": True, "import_subrig": True, "import_weights": True},
            scene_objects=self.objects, all_objects=self.objects, active=self.basemesh,
            shared=["asset_sections.py", "performed.py"], context_mode="EDIT_MESH")
        self.assertEqual(result["blocked_by"], "not_object_mode")

    def test_a_failed_import_names_what_it_left_behind(self):
        self.build_character()
        StubHumanService.add_asset_raises = IOError(
            "failed to import the clothes mesh: object was None after import")
        result = self.run_add_asset(path=self.fedora)
        self.assertEqual(result["blocked_by"], "import_failed")
        self.assertFalse(result["added"])
        # Even a failure puts the scene back the way it was found.
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.basemesh)

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_tracks_added(self):
        self.build_character()

        added = self.run_add_asset(path=self.fedora)
        self.assertIs(added["performed"], True)
        self.assertEqual(added["performed"], added["added"])

        refused = self.run_add_asset(path=os.path.join(self.system_root, "nope.mhclo"))
        self.assertEqual(refused["blocked_by"], "asset_not_found")
        self.assertIs(refused["performed"], False)
        self.assertEqual(refused["performed"], refused["added"])

class UnreadableMhcloTests(MeshAssetTestCase):
    """An MHCLO that cannot be read claims nothing about its material."""

    def test_an_unreadable_mhclo_reports_not_known_rather_than_no_material(self):
        self.build_character()
        broken = write_mhclo(
            os.path.join(self.system_root, "clothes", "broken", "broken.mhclo"))
        # A real unreadable file rather than a mocked open(): the payload files
        # themselves are read through open() at assembly time, so mocking it
        # would break the harness rather than the case under test.
        os.chmod(broken, 0o000)
        self.addCleanup(os.chmod, broken, 0o644)
        arguments = {
            "name": None, "path": broken, "fragment": None, "asset_type": "Clothes",
            "material_type": None, "subdiv_levels": 1, "set_up_rigging": True,
            "interpolate_weights": True, "import_subrig": True, "import_weights": True,
        }
        result = self.run_payload(
            "add_asset.py", arguments, scene_objects=self.objects,
            all_objects=self.objects, active=self.basemesh,
            shared=["asset_sections.py", "performed.py"])
        self.assertIsNone(result["mhclo_names_material"])
        self.assertTrue(any("could not be read" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
