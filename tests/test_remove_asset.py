# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_remove_asset tool: argument validation, and the generated
code's refusals, its read-before-deleting, and what it reports being left with.

Two layers, as everywhere in this suite: the tool wrapper with send_code mocked,
then the assembled source executed against the stub services and the same
temporary asset library tests/test_add_asset.py uses. Several of these cases
equip an asset with mpfb_add_asset's payload first and then remove it, because
the interesting claims - which mask modifiers went, which vertex groups stayed -
are only meaningful about state that MPFB's own loading path produced.

What is *not* under test here, and cannot be: that a character with an asset
removed this way looks the way it did before the asset was added. That is a live
check against a running Blender (see feature-requests/done/010-mesh-assets).

Run with::

    python -m unittest tests.test_remove_asset -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import remove_asset

from tests.blender_stubs import (
    GeneralObjectProperties, MeshAssetTestCase, StubHumanService, StubObject,
    StubObjectService)


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    remove_asset.register(mcp)
    return mcp._tool_manager._tools["mpfb_remove_asset"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Shape only. Whether the name is an asset is answered inside Blender."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_the_name_crosses_the_socket(self):
        with mock.patch.object(remove_asset, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.fedora")
        source = send_code.call_args[0][0]
        self.assertIn("# --- payload: remove_asset.py ---", source)
        self.assertIn(json.dumps({"name": "Human.fedora"}), source)

    def test_the_name_is_required(self):
        # No active-object fallback anywhere: this deletes an object, and
        # "whatever happens to be selected" is not a way to choose which.
        with mock.patch.object(remove_asset, "send_code") as send_code:
            with self.assertRaises(TypeError):
                self.tool()
            with self.assertRaises(ValueError):
                self.tool(name="  ")
            with self.assertRaises(ValueError):
                self.tool(name=None)
        send_code.assert_not_called()

    def test_performed_py_is_the_only_shared_fragment_named(self):
        # Removal needs no section table: the object records its own type. The
        # one fragment it does name is the uniform "it happened" flag every
        # mutating tool carries.
        with mock.patch.object(remove_asset, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(name="Human.fedora")
        source = send_code.call_args[0][0]
        self.assertIn("# --- shared: performed.py ---", source)
        self.assertEqual(source.count("# --- shared:"), 1)

    def test_response_envelope_is_returned_unchanged(self):
        envelope = {"status": "error", "message": "no MPFB"}
        with mock.patch.object(remove_asset, "send_code") as send_code:
            send_code.return_value = envelope
            self.assertIs(self.tool(name="Human.fedora"), envelope)


class GeneratedCodeTests(MeshAssetTestCase):
    """The payload, executed against a character something was really put on."""

    def equip(self, path, asset_type="Clothes", **overrides):
        """Dress the character through mpfb_add_asset's own payload.

        Rather than hand-building the object: what removal has to undo is
        precisely what adding did, and a fixture assembled by hand would be a
        second opinion about that.
        """
        arguments = {
            "name": None, "path": path, "fragment": None, "asset_type": asset_type,
            "material_type": None, "subdiv_levels": 1, "set_up_rigging": True,
            "interpolate_weights": True, "import_subrig": True, "import_weights": True,
        }
        arguments.update(overrides)
        result = self.run_payload(
            "add_asset.py", arguments, scene_objects=self.objects,
            all_objects=self.objects, active=self.basemesh,
            shared=["asset_sections.py", "performed.py"])
        self.objects = list(StubObjectService.all_objects)
        return result

    def run_remove(self, name, context_mode="OBJECT"):
        result = self.run_payload(
            "remove_asset.py", {"name": name},
            scene_objects=self.objects, all_objects=self.objects,
            active=self.basemesh, context_mode=context_mode, shared=["performed.py"])
        self.objects = list(StubObjectService.all_objects)
        return result

    # --- the happy path ---------------------------------------------------

    def test_an_equipped_garment_comes_off_and_takes_its_mask_with_it(self):
        self.build_character()
        added = self.equip(self.fedora)
        result = self.run_remove(added["asset_object_name"])
        self.assertTrue(result["removed"])
        self.assertEqual(result["asset_object_name"], "Human.fedora")
        self.assertEqual(result["object_type"], "Clothes")
        self.assertEqual(result["asset_source"], "fedora/fedora.mhclo")
        self.assertEqual(result["basemesh_name"], "Human")
        self.assertEqual(
            [record["modifier_name"] for record in result["mask_modifiers_removed"]],
            ["Delete.fedora"])
        self.assertEqual(result["mask_modifiers_left_behind"], [])
        self.assertNotIn("Human.fedora", [obj.name for obj in StubObjectService.all_objects])

    def test_the_type_and_source_are_read_before_the_object_is_gone(self):
        # Everything reported about the removed asset has to be read first: the
        # object no longer exists when the call returns, and asset_source is
        # what every modifier name is derived from.
        self.build_character()
        added = self.equip(self.fedora)
        result = self.run_remove(added["asset_object_name"])
        self.assertEqual(result["objects_removed"], ["Human.fedora"])
        self.assertIsNotNone(result["asset_source"])
        self.assertIsNotNone(result["mesh_data_orphaned"])

    def test_the_delete_group_itself_is_left_behind_and_said_so(self):
        # MPFB removes the modifiers and not the groups. Harmless, and invisible
        # unless reported.
        self.build_character()
        added = self.equip(self.fedora)
        result = self.run_remove(added["asset_object_name"])
        self.assertEqual(
            [record["vertex_group"] for record in result["vertex_groups_left_behind"]],
            ["Delete.fedora"])
        self.assertIn("Delete.fedora", self.basemesh.vertex_groups)

    def test_the_body_proxy_mask_comes_off_too(self):
        self.build_character(proxy=True)
        added = self.equip(self.fedora)
        result = self.run_remove(added["asset_object_name"])
        self.assertEqual(
            sorted(record["object_name"] for record in result["mask_modifiers_removed"]),
            ["Human", "Human.proxy721"])
        self.assertEqual(result["body_proxy_name"], "Human.proxy721")

    def test_the_right_copy_is_taken_off_when_two_are_equipped(self):
        self.build_character()
        first = self.equip(self.fedora)
        second = self.equip(self.fedora)
        result = self.run_remove(second["asset_object_name"])
        self.assertEqual(result["asset_object_name"], "Human.fedora.001")
        remaining = [obj.name for obj in StubObjectService.all_objects]
        self.assertIn(first["asset_object_name"], remaining)
        self.assertNotIn(second["asset_object_name"], remaining)

    def test_a_subrig_goes_with_the_asset_that_brought_it(self):
        self.build_character(rig=True)
        added = self.equip(self.rigged)
        self.assertIsNotNone(added["subrig_object_name"])
        result = self.run_remove(added["asset_object_name"])
        self.assertEqual(result["subrig_object_name"], "Human.rigged.rig")
        self.assertTrue(result["subrig_removed"])
        self.assertNotIn(
            "Human.rigged.rig", [obj.name for obj in StubObjectService.all_objects])

    def test_an_asset_with_no_delete_group_reports_no_mask_rather_than_a_failure(self):
        self.build_character()
        added = self.equip(self.plain)
        result = self.run_remove(added["asset_object_name"])
        self.assertTrue(result["removed"])
        self.assertEqual(result["mask_modifiers_removed"], [])
        self.assertIn("normal for an asset", result["message"])

    # --- refusals as answers ---------------------------------------------

    def test_an_unknown_name_is_an_answer(self):
        self.build_character()
        result = self.run_remove("Nothing")
        self.assertFalse(result["removed"])
        self.assertEqual(result["blocked_by"], "not_found")
        self.assertFalse(result["found"])
        self.assertEqual(StubHumanService.unload_calls, [])

    def test_a_basemesh_is_refused_by_name(self):
        # unload_mhclo_asset() checks nothing and would delete it.
        self.build_character()
        result = self.run_remove("Human")
        self.assertEqual(result["blocked_by"], "not_a_mesh_asset")
        self.assertEqual(result["object_type"], "Basemesh")
        self.assertEqual(StubHumanService.unload_calls, [])
        self.assertIn("Human", [obj.name for obj in StubObjectService.all_objects])

    def test_a_skeleton_is_refused_by_name(self):
        self.build_character(rig=True)
        result = self.run_remove("Human.rig")
        self.assertEqual(result["blocked_by"], "not_a_mesh_asset")
        self.assertEqual(result["object_type"], "Skeleton")
        self.assertEqual(StubHumanService.unload_calls, [])

    def test_an_object_that_is_not_a_makehuman_object_is_refused(self):
        self.build_character()
        stray = StubObject("Cube")
        self.objects = self.objects + [stray]
        result = self.run_remove("Cube")
        self.assertEqual(result["blocked_by"], "not_a_mesh_asset")
        self.assertIsNone(result["object_type"])

    def test_an_asset_with_no_basemesh_relative_is_refused(self):
        # The mask cleanup needs the basemesh: deleting the object without it
        # would leave the body masked with nothing to explain why.
        self.build_character()
        orphan = StubObject(
            "Orphan.fedora", object_type="Clothes", asset_source="fedora/fedora.mhclo")
        self.objects = self.objects + [orphan]
        result = self.run_remove("Orphan.fedora")
        self.assertEqual(result["blocked_by"], "basemesh_not_found")
        self.assertEqual(StubHumanService.unload_calls, [])

    def test_an_empty_asset_source_is_refused_and_names_the_mask_it_could_not_identify(self):
        # unload_mhclo_asset() derives "Delete." from an empty property, matches
        # nothing, and deletes the object anyway - leaving the body masked under
        # an asset that is no longer there.
        self.build_character()
        added = self.equip(self.fedora)
        asset = self.last_bpy.data.objects[added["asset_object_name"]]
        GeneralObjectProperties.set_value("asset_source", "", entity_reference=asset)
        result = self.run_remove(added["asset_object_name"])
        self.assertEqual(result["blocked_by"], "asset_source_missing")
        # The delete-group masks only. MPFB's own `Hide helpers` is a MASK on
        # the basemesh too, and naming it here would point somebody removing an
        # orphaned mask by hand at a modifier they must not touch.
        self.assertEqual(result["mask_modifiers_present"], ["Delete.fedora"])
        self.assertIn("Hide helpers",
                      [modifier.name for modifier in self.basemesh.modifiers])
        self.assertEqual(StubHumanService.unload_calls, [])
        self.assertIn(
            added["asset_object_name"], [obj.name for obj in StubObjectService.all_objects])

    def test_edit_mode_is_an_answer_and_nothing_is_deleted(self):
        self.build_character()
        added = self.equip(self.fedora)
        asset = self.last_bpy.data.objects[added["asset_object_name"]]
        asset.mode = "EDIT"
        result = self.run_remove(added["asset_object_name"])
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(StubHumanService.unload_calls, [])

    def test_another_object_in_edit_mode_also_blocks(self):
        self.build_character()
        added = self.equip(self.fedora)
        result = self.run_remove(added["asset_object_name"], context_mode="EDIT_MESH")
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(StubHumanService.unload_calls, [])

    def test_a_renamed_mask_modifier_is_reported_as_left_behind(self):
        # unload_mhclo_asset() matches the modifier by *name*, so one renamed by
        # hand survives with its group intact - which the response has to say
        # rather than claim a clean removal.
        self.build_character()
        added = self.equip(self.fedora)
        for modifier in self.basemesh.modifiers:
            if modifier.type == "MASK" and modifier.name.startswith("Delete."):
                modifier.name = "Renamed by hand"
        result = self.run_remove(added["asset_object_name"])
        self.assertTrue(result["removed"])
        self.assertEqual(result["mask_modifiers_removed"], [])
        self.assertEqual(
            [modifier.name for modifier in self.basemesh.modifiers],
            ["Hide helpers", "Renamed by hand"])

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_tracks_removed(self):
        self.build_character()
        equipped = self.equip(self.fedora)["asset_object_name"]

        removed = self.run_remove(equipped)
        self.assertIs(removed["performed"], True)
        self.assertEqual(removed["performed"], removed["removed"])

        refused = self.run_remove("Nope")
        self.assertEqual(refused["blocked_by"], "not_found")
        self.assertIs(refused["performed"], False)
        self.assertEqual(refused["performed"], refused["removed"])


if __name__ == "__main__":
    unittest.main()
