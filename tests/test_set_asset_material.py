# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_set_asset_material tool: the reimplemented UI operator, its
three refusals, and the quirks reproduced rather than tidied up.

Three layers since FR 032 migrated it (see ``tests/test_list_objects.py``, the
template): the tool wrapper with ``send_code`` mocked on the seam; the **bridge
path** against ``tests/fake_bridge.py``; and the assembled source executed
against the stub services and a real temporary asset library
(tests/blender_stubs.py's MeshAssetTestCase). That third layer is **frozen**: it
stays while the payload stays, because the payload is half of what FR 032's live
comparison compares.

The library is real because this payload reads the asset's MHCLO for its
material line and resolves a fragment by walking the asset roots. The dressed
character is built by running mpfb_add_asset's own payload rather than by hand,
for the same reason test_remove_asset.py does it: the material this tool
replaces is exactly the one that tool built.

What layer 3 cannot say is that the material this produces is the one MPFB's own
alternative-material panel produces. That is a node tree, and no stub builds
one. That is now checked against a real MPFB in
``bridge/test/tests/ppp_mutating/set_asset_material_test.py``.

Run with::

    python -m unittest tests.test_set_asset_material -v
"""

__all__ = ()

import os
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import backend
from mpfbmcp.tools import set_asset_material

from tests import fake_bridge
from tests.blender_stubs import (
    MeshAssetTestCase, StubMakeSkinMaterial, StubMaterialService, StubMhclo, StubObject,
    StubObjectService)
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
    set_asset_material.register(mcp)
    # pylint: disable=protected-access
    return mcp._tool_manager._tools["mpfb_set_asset_material"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Shape, plus the two mutual exclusions shape can settle."""

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

    def test_the_arguments_cross_the_socket(self):
        source = self._sent_source(name="Human.fedora", path="/assets/fedora/red.mhmat")
        self.assertIn("# --- payload: set_asset_material.py ---", source)
        self.assertEqual(
            self._sent_params(name="Human.fedora", path="/assets/fedora/red.mhmat"),
            {"name": "Human.fedora", "path": "/assets/fedora/red.mhmat",
             "fragment": None, "restore_default": False})

    def test_performed_py_is_the_only_shared_fragment_named(self):
        # The asset subdir here is MPFB's own str(object_type).lower(), the same
        # derivation payloads/get_object_info.py makes when it resolves this
        # property back to a file - not asset_sections.py's section table. The
        # one fragment that is named is the uniform "it happened" flag every
        # mutating tool carries.
        source = self._sent_source(
            name="Human.fedora", path="/assets/fedora/red.mhmat")
        self.assertIn("# --- shared: performed.py ---", source)
        self.assertEqual(source.count("# --- shared:"), 1)

    def test_name_is_required_and_has_no_active_object_fallback(self):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            with self.assertRaises(TypeError):
                self.tool(path="/a/b.mhmat")
            for bad in ("", "   ", None, 7):
                with self.subTest(name=bad):
                    with self.assertRaises((ValueError, TypeError)):
                        self.tool(name=bad, path="/a/b.mhmat")
            send_code.assert_not_called()

    def test_both_identifiers_are_rejected_and_so_is_neither(self):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            with self.assertRaises(ValueError):
                self.tool(name="Human.fedora", path="/a/b.mhmat", fragment="b/b.mhmat")
            with self.assertRaises(ValueError):
                self.tool(name="Human.fedora")
            send_code.assert_not_called()

    def test_restore_default_excludes_a_named_material(self):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            with self.assertRaises(ValueError):
                self.tool(name="Human.fedora", path="/a/b.mhmat", restore_default=True)
            with self.assertRaises(ValueError):
                self.tool(name="Human.fedora", fragment="b/b.mhmat", restore_default=True)
            send_code.assert_not_called()

    def test_restore_default_alone_is_a_complete_request(self):
        self.assertEqual(
            self._sent_params(name="Human.fedora", restore_default=True),
            {"name": "Human.fedora", "path": None, "fragment": None,
             "restore_default": True})

    def test_restore_default_must_be_a_real_bool(self):
        with self.assertRaises(ValueError):
            self.tool(name="Human.fedora", restore_default="true")


class SetAssetMaterialOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the eleven refusals, the popped slots, the fixed material name and the viewport colour - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/set_asset_material_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "set_asset_material": fake_bridge.ok_envelope("set_asset_material", {"found": True, "applied": True, "performed": True}),
        })

    def test_the_tool_sends_the_set_asset_material_command(self) -> None:
        self.call(name="Human.fedora", path="/a.mhmat")

        self.assertEqual(self.bridge.commands()[-1], "set_asset_material")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["name"], "Human.fedora")
        self.assertEqual(params["path"], "/a.mhmat")
        self.assertIs(params["restore_default"], False)

    def test_no_shared_fragment_reaches_the_bridge(self) -> None:
        self.call(name="Human.fedora", path="/a.mhmat")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("performed", str(request))

    def test_restore_default_travels_as_a_parameter_like_any_other(self) -> None:
        self.call(name="Human.fedora", restore_default=True)

        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertIs(params["restore_default"], True)
        self.assertIsNone(params["path"])
        self.assertIsNone(params["fragment"])

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(name="Human.fedora")
        with self.assertRaises(ValueError):
            self.call(name="Human.fedora", path="/a.mhmat", restore_default=True)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="set_asset_material", state="absent"))

        response = self.call(name="Human.fedora", path="/a.mhmat")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class GeneratedCodeTests(MeshAssetTestCase):
    """The payload, executed against a real asset library and a stub character."""

    def equip(self, path=None, asset_type="Clothes"):
        """Dress the character by running mpfb_add_asset's own payload.

        What this tool replaces is exactly the material that tool built, so
        hand-building the object would be testing against a fixture rather than
        against the thing being changed.
        """
        arguments = {
            "name": None,
            "path": path or self.fedora,
            "fragment": None,
            "asset_type": asset_type,
            "material_type": None,
            "subdiv_levels": 1,
            "set_up_rigging": True,
            "interpolate_weights": True,
            "import_subrig": True,
            "import_weights": True,
        }
        added = self.run_payload(
            "add_asset.py", arguments,
            scene_objects=self.objects, all_objects=self.objects, active=self.basemesh,
            shared=["asset_sections.py", "performed.py"])
        self.objects = list(StubObjectService.all_objects)
        return added["asset_object_name"]

    def run_set(self, name, **params):
        arguments = {"name": name, "path": None, "fragment": None, "restore_default": False}
        arguments.update(params)
        return self.run_payload(
            "set_asset_material.py", arguments,
            scene_objects=self.objects, all_objects=self.objects,
            active=self.basemesh, shared=["performed.py"])

    def object_named(self, name):
        for blender_object in self.objects:
            if blender_object.name == name:
                return blender_object
        raise AssertionError("no object called " + name)

    # --- the happy path ---------------------------------------------------

    def test_an_alternative_is_applied_and_recorded(self):
        self.build_character()
        equipped = self.equip()
        result = self.run_set(equipped, path=self.fedora_red)

        self.assertTrue(result["applied"])
        self.assertIsNone(result["blocked_by"])
        self.assertEqual(result["asset_object_name"], equipped)
        self.assertEqual(result["object_type"], "Clothes")
        self.assertEqual(result["asset_subdir"], "clothes")
        self.assertEqual(result["resolved_by"], "path")
        self.assertEqual(result["resolved_path"], self.fedora_red)
        self.assertEqual(result["alternative_material"], "fedora/red.mhmat")

    def test_a_fragment_resolves_under_the_assets_own_type(self):
        self.build_character()
        equipped = self.equip()
        result = self.run_set(equipped, fragment="fedora/blue.mhmat")

        self.assertEqual(result["resolved_by"], "fragment")
        self.assertEqual(result["resolved_path"], self.fedora_blue)
        self.assertEqual(result["alternative_material"], "fedora/blue.mhmat")

    def test_the_previous_alternative_is_reported_beside_the_new_one(self):
        self.build_character()
        equipped = self.equip()
        self.run_set(equipped, path=self.fedora_red)
        result = self.run_set(equipped, path=self.fedora_blue)

        self.assertEqual(result["previous_alternative_material"], "fedora/red.mhmat")
        self.assertEqual(result["alternative_material"], "fedora/blue.mhmat")

    def test_the_material_that_was_there_is_named_before_it_goes(self):
        self.build_character()
        equipped = self.equip()
        result = self.run_set(equipped, path=self.fedora_red)

        self.assertEqual(result["materials_destroyed"], [equipped])
        self.assertIn("pops the slots", result["message"])

    def test_the_node_tree_is_built_from_the_file_that_was_named(self):
        self.build_character()
        equipped = self.equip()
        self.run_set(equipped, path=self.fedora_red)

        self.assertEqual(StubMakeSkinMaterial.applied[-1][0], self.fedora_red)
        asset = self.object_named(equipped)
        self.assertEqual(asset.data.materials[0].built_from, self.fedora_red)

    # --- the quirks reproduced rather than tidied up -----------------------

    def test_the_new_material_is_always_a_makeskin_material_under_one_name(self):
        # Whatever the asset had before. Tidying this up would make the result
        # differ from what MPFB's own panel produces.
        self.build_character()
        equipped = self.equip(path=self.lowpoly_eyes, asset_type="Eyes")
        result = self.run_set(equipped, path=self.fedora_red)

        self.assertEqual(result["material_name"], "makeskinmaterial")
        self.assertEqual(self.object_named(equipped).data.materials[0].identified, "makeskin")
        self.assertIn("MakeSkin material", result["message"])

    def test_the_slots_are_popped_rather_than_destroyed(self):
        # delete_all_materials(also_destroy_groups=True) is the skin path. This
        # one pops, so node groups survive - a real difference between the two
        # tools, and one a shared helper would have erased.
        self.build_character()
        equipped = self.equip()
        StubMaterialService.delete_calls = []
        self.run_set(equipped, path=self.fedora_red)

        self.assertEqual(StubMaterialService.delete_calls, [])

    def test_the_display_colour_comes_from_the_objects_recorded_type(self):
        self.build_character()
        equipped = self.equip()
        result = self.run_set(equipped, path=self.fedora_red)

        self.assertEqual(result["diffuse_color_from"], "Clothes")
        self.assertEqual(
            self.object_named(equipped).data.materials[0].diffuse_color,
            StubMaterialService.DIFFUSE_COLORS["Clothes"])

    def test_a_type_outside_mpfbs_colour_table_gets_the_grey_fallback(self):
        self.build_character()
        cape = StubObject("Human.cape", parent=self.basemesh, object_type="Cape",
                          asset_source="fedora/fedora.mhclo")
        self.objects = self.objects + [cape]
        result = self.run_set("Human.cape", path=self.fedora_red)

        self.assertTrue(result["applied"])
        self.assertIsNone(result["diffuse_color_from"])
        self.assertEqual(cape.data.materials[0].diffuse_color, (0.8, 0.8, 0.8, 1.0))
        self.assertIn("neutral grey fallback", result["message"])

    # --- restore_default ---------------------------------------------------

    def test_restore_default_puts_back_the_mhclos_own_material(self):
        self.build_character()
        equipped = self.equip()
        self.run_set(equipped, path=self.fedora_red)
        result = self.run_set(equipped, restore_default=True)

        self.assertTrue(result["applied"])
        self.assertEqual(result["resolved_by"], "default")
        self.assertEqual(result["resolved_path"], self.fedora_default_material)
        self.assertEqual(result["previous_alternative_material"], "fedora/red.mhmat")
        self.assertIsNone(result["alternative_material"])
        self.assertIn("Restored", result["message"])

    def test_restore_default_reads_the_mhclo_without_its_vertex_tables(self):
        self.build_character()
        equipped = self.equip()
        StubMhclo.load_calls = []
        self.run_set(equipped, restore_default=True)

        self.assertEqual(len(StubMhclo.load_calls), 1)
        self.assertTrue(StubMhclo.load_calls[0][1], "only_metadata should be True")

    def test_restore_default_on_an_asset_with_no_asset_source_is_refused(self):
        self.build_character()
        stray = StubObject("Human.hat", parent=self.basemesh, object_type="Clothes")
        self.objects = self.objects + [stray]
        result = self.run_set("Human.hat", restore_default=True)

        self.assertFalse(result["applied"])
        self.assertEqual(result["blocked_by"], "asset_source_missing")

    def test_restore_default_when_the_mhclo_names_no_material_is_refused(self):
        self.build_character()
        equipped = self.equip(path=self.plain)
        result = self.run_set(equipped, restore_default=True)

        self.assertEqual(result["blocked_by"], "default_material_not_found")
        self.assertEqual(result["default_material_reason"], "mhclo_names_no_material")

    def test_restore_default_when_the_named_material_is_not_on_disk_is_refused(self):
        # A partially installed pack: the MHCLO names a file that was never
        # shipped. Refused rather than applied as an empty material.
        self.build_character()
        equipped = self.equip(path=self.dangling)
        result = self.run_set(equipped, restore_default=True)

        self.assertEqual(result["blocked_by"], "default_material_not_found")
        self.assertEqual(result["default_material_reason"], "file_missing")

    # --- refusals as answers ----------------------------------------------

    def test_the_three_types_mpfbs_own_panel_refuses_are_refused(self):
        self.build_character(rig=True, proxy=True)
        for name in ("Human", "Human.proxy721", "Human.rig"):
            with self.subTest(name=name):
                result = self.run_set(name, path=self.fedora_red)
                self.assertFalse(result["applied"])
                self.assertEqual(result["blocked_by"], "type_not_supported")
                self.assertIn("mpfb_set_skin", result["message"])

    def test_an_object_with_no_mpfb_type_is_an_answer(self):
        self.build_character()
        self.objects = self.objects + [StubObject("Cube")]
        result = self.run_set("Cube", path=self.fedora_red)

        self.assertEqual(result["blocked_by"], "not_an_mpfb_object")

    def test_an_unknown_name_is_an_answer(self):
        self.build_character()
        result = self.run_set("Nope", path=self.fedora_red)

        self.assertFalse(result["found"])
        self.assertEqual(result["blocked_by"], "not_found")
        self.assertIn("Nope", result["message"])

    def test_a_missing_file_is_an_answer(self):
        self.build_character()
        equipped = self.equip()
        result = self.run_set(equipped, path=os.path.join(self.system_root, "nope.mhmat"))

        self.assertEqual(result["blocked_by"], "material_not_found")

    def test_an_unresolvable_fragment_names_the_subdir_and_the_catalogue(self):
        self.build_character()
        equipped = self.equip()
        result = self.run_set(equipped, fragment="nope/nope.mhmat")

        self.assertEqual(result["blocked_by"], "material_not_found")
        self.assertIn("clothes", result["message"])
        self.assertIn("mpfb_list_asset_materials", result["message"])

    def test_edit_mode_is_an_answer_and_nothing_is_changed(self):
        self.build_character()
        equipped = self.equip()
        asset = self.object_named(equipped)
        asset.mode = "EDIT"
        before = [material.name for material in asset.data.materials]
        result = self.run_set(equipped, path=self.fedora_red)

        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual([material.name for material in asset.data.materials], before)

    def test_a_refusal_never_touches_the_recorded_property(self):
        self.build_character()
        equipped = self.equip()
        self.run_set(equipped, path=self.fedora_red)
        result = self.run_set(equipped, path=os.path.join(self.system_root, "nope.mhmat"))

        self.assertEqual(result["alternative_material"], "fedora/red.mhmat")
        self.assertEqual(result["previous_alternative_material"], "fedora/red.mhmat")

    # --- a failed application is not a no-op -------------------------------

    def test_a_failure_while_building_names_what_was_already_removed(self):
        self.build_character()
        equipped = self.equip()
        StubMakeSkinMaterial.raise_on_apply = RuntimeError("bad node tree")
        result = self.run_set(equipped, path=self.fedora_red)

        self.assertFalse(result["applied"])
        self.assertEqual(result["blocked_by"], "material_failed")
        self.assertEqual(result["materials_destroyed"], [equipped])

    # --- restore what was borrowed -----------------------------------------

    def test_the_previous_active_object_and_selection_are_restored(self):
        self.build_character()
        equipped = self.equip()
        asset = self.object_named(equipped)
        self.assertFalse(asset.select_get())
        self.run_payload(
            "set_asset_material.py",
            {"name": equipped, "path": self.fedora_red, "fragment": None,
             "restore_default": False},
            scene_objects=self.objects, all_objects=self.objects,
            active=self.basemesh, shared=["performed.py"])

        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.basemesh)
        self.assertFalse(asset.select_get())

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_tracks_applied(self):
        self.build_character()
        equipped = self.equip()

        applied = self.run_set(equipped, path=self.fedora_red)
        self.assertIs(applied["performed"], True)
        self.assertEqual(applied["performed"], applied["applied"])

        refused = self.run_set("Nope", path=self.fedora_red)
        self.assertFalse(refused["found"])
        self.assertIs(refused["performed"], False)
        self.assertEqual(refused["performed"], refused["applied"])


if __name__ == "__main__":
    unittest.main()
