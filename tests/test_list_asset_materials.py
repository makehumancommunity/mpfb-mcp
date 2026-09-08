# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_asset_materials tool: the catalogue that is not a
section, its cached snapshot, and what makes an empty answer explainable.

Two layers, as everywhere in this suite: the tool wrapper with send_code mocked,
then the assembled source executed against the stub services and a real
temporary asset library (tests/blender_stubs.py's MeshAssetTestCase). Real,
because the scan this wraps globs `*.mhmat` off disk and matches on a path
segment - mocking the filesystem away would leave nothing under test.

What is *not* under test here, and cannot be: that MPFB's own scan finds the
same files on a real install, or that the cache behaves as documented across a
Blender session rather than across a stub. Both are live checks (see
feature-requests/done/011-skin-and-materials).

Run with::

    python -m unittest tests.test_list_asset_materials -v
"""

__all__ = ()

import os
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import list_asset_materials

from tests.blender_stubs import (
    MeshAssetTestCase, StubAssetService, StubMhclo, StubObject, StubObjectService,
    write_mhmat)


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_asset_materials.register(mcp)
    # pylint: disable=protected-access
    return mcp._tool_manager._tools["mpfb_list_asset_materials"].fn


class ArgumentValidationTests(unittest.TestCase):
    """Shape only, and there is only one argument to have a shape."""

    def setUp(self):
        self.tool = _tool_callable()

    def _sent_source(self, **kwargs):
        with mock.patch.object(list_asset_materials, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        return send_code.call_args[0][0]

    def test_the_name_crosses_the_socket(self):
        source = self._sent_source(name="Human.fedora")
        self.assertIn("# --- payload: list_asset_materials.py ---", source)
        self.assertIn('{"name": "Human.fedora"}', source)

    def test_no_shared_fragment_is_named(self):
        self.assertNotIn("# --- shared:", self._sent_source(name="Human.fedora"))

    def test_name_is_required(self):
        with mock.patch.object(list_asset_materials, "send_code") as send_code:
            with self.assertRaises(TypeError):
                self.tool()
            for bad in ("", "   ", None, 7):
                with self.subTest(name=bad):
                    with self.assertRaises((ValueError, TypeError)):
                        self.tool(name=bad)
            send_code.assert_not_called()


class GeneratedCodeTests(MeshAssetTestCase):
    """The payload, executed against a real asset library and a stub character."""

    def equip(self, path=None, asset_type="Clothes"):
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

    def run_list(self, name):
        return self.run_payload(
            "list_asset_materials.py", {"name": name},
            scene_objects=self.objects, all_objects=self.objects, active=self.basemesh)

    # --- the catalogue -----------------------------------------------------

    def test_the_materials_beside_an_asset_are_listed_with_both_identifiers(self):
        self.build_character()
        equipped = self.equip()
        result = self.run_list(equipped)

        self.assertTrue(result["found"])
        self.assertEqual(result["object_type"], "Clothes")
        self.assertEqual(result["asset_subdir"], "clothes")
        self.assertEqual(result["asset_source"], "fedora/fedora.mhclo")
        paths = [entry["path"] for entry in result["materials"]]
        self.assertIn(self.fedora_red, paths)
        self.assertIn(self.fedora_blue, paths)
        self.assertEqual(result["count"], len(result["materials"]))
        for entry in result["materials"]:
            with self.subTest(entry=entry["path"]):
                self.assertEqual(
                    entry["fragment"],
                    os.path.basename(os.path.dirname(entry["path"]))
                    + "/" + os.path.basename(entry["path"]))
                self.assertFalse(entry["name"].endswith(".mhmat"))

    def test_the_scan_matches_a_whole_path_segment_and_not_a_substring(self):
        # "plainproxy" contains "plain", and MPFB matches path *segments*. A
        # substring match would attribute one asset's materials to another.
        self.build_character()
        equipped = self.equip(path=self.plain)
        result = self.run_list(equipped)

        self.assertEqual(result["materials"], [])

    def test_the_default_material_is_reported_and_flagged_rather_than_removed(self):
        # alternative_materials_for_asset() takes an exclude_default argument
        # and never reads it, so the asset's own material is in the list.
        # Filtering it out here would be this tool inventing a behaviour.
        self.build_character()
        equipped = self.equip()
        result = self.run_list(equipped)

        self.assertEqual(result["default_material"]["path"], self.fedora_default_material)
        self.assertTrue(result["default_material"]["exists"])
        self.assertEqual(result["default_material"]["fragment"], "fedora/fedora.mhmat")
        flagged = [entry["path"] for entry in result["materials"] if entry["is_default"]]
        self.assertEqual(flagged, [self.fedora_default_material])

    def test_the_material_currently_worn_is_named(self):
        self.build_character()
        equipped = self.equip()
        self.run_payload(
            "set_asset_material.py",
            {"name": equipped, "path": self.fedora_red, "fragment": None,
             "restore_default": False},
            scene_objects=self.objects, all_objects=self.objects,
            active=self.basemesh, shared=["performed.py"])
        result = self.run_list(equipped)

        self.assertEqual(result["current_alternative_material"], "fedora/red.mhmat")

    def test_an_asset_wearing_its_own_material_reports_none(self):
        self.build_character()
        equipped = self.equip()
        self.assertIsNone(self.run_list(equipped)["current_alternative_material"])

    def test_the_mhclo_is_read_without_its_vertex_tables(self):
        self.build_character()
        equipped = self.equip()
        StubMhclo.load_calls = []
        self.run_list(equipped)

        self.assertEqual(len(StubMhclo.load_calls), 1)
        self.assertTrue(StubMhclo.load_calls[0][1], "only_metadata should be True")

    # --- an empty answer must be explainable -------------------------------

    def test_an_empty_answer_names_the_roots_it_searched(self):
        self.build_character()
        equipped = self.equip(path=self.plain)
        result = self.run_list(equipped)

        self.assertEqual(result["count"], 0)
        self.assertEqual(len(result["search_roots"]), 2)
        self.assertIn(os.path.join(self.system_root, "clothes"), result["search_roots"])
        self.assertIn("asset root(s) were searched", result["message"])

    def test_an_asset_with_no_source_is_distinguishable_from_one_with_none_to_find(self):
        self.build_character()
        stray = StubObject("Human.hat", parent=self.basemesh, object_type="Clothes")
        self.objects = self.objects + [stray]
        result = self.run_list("Human.hat")

        self.assertTrue(result["found"])
        self.assertEqual(result["materials"], [])
        self.assertIsNone(result["asset_source"])
        self.assertEqual(result["default_material_reason"], "asset_source_missing")
        self.assertIn("records no asset_source", result["message"])

    def test_a_default_material_that_is_not_installed_is_said_so(self):
        self.build_character()
        equipped = self.equip(path=self.dangling)
        result = self.run_list(equipped)

        self.assertIsNotNone(result["default_material"])
        self.assertFalse(result["default_material"]["exists"])

    def test_an_mhclo_naming_no_material_reports_the_reason(self):
        self.build_character()
        equipped = self.equip(path=self.plain)
        result = self.run_list(equipped)

        self.assertIsNone(result["default_material"])
        self.assertEqual(result["default_material_reason"], "mhclo_names_no_material")
        self.assertIn("restore_default would refuse", result["message"])

    def test_an_unknown_name_is_an_answer_rather_than_an_error(self):
        self.build_character()
        result = self.run_list("Nope")

        self.assertFalse(result["found"])
        self.assertEqual(result["materials"], [])
        self.assertIn("Nope", result["message"])

    def test_an_object_with_no_mpfb_type_is_an_answer(self):
        self.build_character()
        self.objects = self.objects + [StubObject("Cube")]
        result = self.run_list("Cube")

        self.assertTrue(result["found"])
        self.assertIsNone(result["object_type"])
        self.assertEqual(result["materials"], [])
        self.assertIn("carries no MPFB object_type", result["message"])

    def test_the_basemesh_is_answered_rather_than_refused(self):
        # Read-only, so unlike the setter there is nothing to refuse. A basemesh
        # records no asset_source, and that is the answer.
        self.build_character()
        result = self.run_list("Human")

        self.assertTrue(result["found"])
        self.assertEqual(result["object_type"], "Basemesh")
        self.assertEqual(result["materials"], [])

    # --- the snapshot ------------------------------------------------------

    def test_a_material_installed_after_the_first_call_is_not_seen(self):
        # The staleness the docstring claims, made a fact. MPFB caches this per
        # (asset_source, asset_subdir) and never invalidates.
        self.build_character()
        equipped = self.equip()
        first = self.run_list(equipped)
        self.assertIn("cached snapshot", first["message"])

        write_mhmat(os.path.join(self.system_root, "clothes", "fedora", "green.mhmat"))
        second = self.run_list(equipped)

        self.assertEqual(
            [entry["path"] for entry in first["materials"]],
            [entry["path"] for entry in second["materials"]])
        self.assertNotIn(
            "green.mhmat", " ".join(entry["path"] for entry in second["materials"]))

    def test_the_cache_is_keyed_on_the_asset_and_not_shared_between_assets(self):
        self.build_character()
        fedora = self.equip()
        eyes = self.equip(path=self.lowpoly_eyes, asset_type="Eyes")
        self.run_list(fedora)
        self.run_list(eyes)

        self.assertIn(("fedora/fedora.mhclo", "clothes"),
                      StubAssetService.alternative_material_calls)
        self.assertIn(("lowpoly/lowpoly.mhclo", "eyes"),
                      StubAssetService.alternative_material_calls)

    def test_the_answer_changes_nothing(self):
        self.build_character()
        equipped = self.equip()
        before = [material.name
                  for blender_object in self.objects
                  for material in blender_object.data.materials]
        self.run_list(equipped)
        after = [material.name
                 for blender_object in self.objects
                 for material in blender_object.data.materials]

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
