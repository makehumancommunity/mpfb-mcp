# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_rigs tool: argument validation, and the generated code's
enumeration of MPFB's rig directories.

Two layers, as in tests/test_get_status.py: the tool wrapper with send_code
mocked, then the assembled source executed against the stub services in
tests/blender_stubs.py. The rig tree those run against is a real temporary
directory rather than a mocked filesystem, because the payload's whole job is
os.listdir() and os.path.isfile() - mocking those away would leave nothing under
test.

The tree deliberately reproduces the asymmetries a real MPFB install has, since
they are what the payload is written around: a rig with no weights file of its
own, a weights file with no rig, and a rig with no entry in the UI enum.

Run with::

    python -m unittest tests.test_list_rigs -v
"""

__all__ = ()

import json
import os
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import codegen
from mpfbmcp.tools import list_rigs

from tests.blender_stubs import (
    RigTestCase, StubAssetService, StubLocationService, StubSystemService,
    write_json as _write_json)


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_rigs.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_rigs"].fn  # pylint: disable=protected-access


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


class RefreshValidationTests(unittest.TestCase):
    """The one argument, validated before anything crosses the socket."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_default_call_sends_refresh_false(self):
        with mock.patch.object(list_rigs, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        source = send_code.call_args[0][0]
        self.assertIn("# --- payload: list_rigs.py ---", source)
        self.assertIn(json.dumps({"refresh": False}), source)

    def test_refresh_true_is_carried_across(self):
        with mock.patch.object(list_rigs, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(refresh=True)
        self.assertIn(json.dumps({"refresh": True}), send_code.call_args[0][0])

    def test_response_envelope_is_returned_unchanged(self):
        envelope = {"status": "error", "message": "no MPFB"}
        with mock.patch.object(list_rigs, "send_code") as send_code:
            send_code.return_value = envelope
            self.assertIs(self.tool(), envelope)

    def test_strict_json_is_requested(self):
        with mock.patch.object(list_rigs, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertIs(send_code.call_args[1]["strict_json"], True)

    def test_non_bool_refresh_is_rejected_locally(self):
        # A truthy int or the string "false" is how a caller signals a bool it
        # failed to build; accepting either would make refresh="false" rescan.
        for bad in (1, 0, "true", "false", None, [], object()):
            with self.subTest(refresh=bad):
                with mock.patch.object(list_rigs, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(refresh=bad)
                send_code.assert_not_called()


class ListRigsGeneratedCodeTests(RigTestCase):
    """The payload, run against a real rig directory tree and the stub services.

    The tree, and ``install_custom_rig()``, live in
    ``blender_stubs.RigTestCase``: ``mpfb_add_rig``'s tests need the same one,
    and the whole point of the shared ``rig_lookup.py`` fragment is that what
    this tool predicts and what that tool does can be compared.
    """

    def run_list_rigs(self, refresh=False):
        # The fragment goes in exactly as tools/list_rigs.py names it, so what
        # runs here is the program the tool would send rather than a payload in
        # isolation - which matters, since the weights resolution now lives in
        # the fragment.
        return self.run_payload(
            "list_rigs.py", {"refresh": refresh}, shared=["rig_lookup.py"])

    def entry(self, result, identifier):
        for rig in result["rigs"]:
            if rig["identifier"] == identifier:
                return rig
        self.fail("no rig with identifier " + repr(identifier) + " in " + repr(
            [rig["identifier"] for rig in result["rigs"]]))

    # -- what is listed -----------------------------------------------------

    def test_every_rig_file_is_listed_and_nothing_else_is(self):
        result = self.run_list_rigs()
        self.assertEqual(
            sorted(rig["identifier"] for rig in result["rigs"]),
            ["default", "default_no_toes", "game_engine", "rigify.human",
             "rigify.human_toes", "undocumented_rig"])
        self.assertEqual(result["count"], len(result["rigs"]))

    def test_a_weights_file_without_a_rig_is_not_listed_as_a_rig(self):
        result = self.run_list_rigs()
        self.assertNotIn("orphan", [rig["name"] for rig in result["rigs"]])
        self.assertNotIn(
            "weights.orphan", [rig["identifier"] for rig in result["rigs"]])

    def test_identifier_carries_the_family_prefix_but_name_does_not(self):
        rigify = self.entry(self.run_list_rigs(), "rigify.human")
        self.assertEqual(rigify["name"], "human")
        self.assertEqual(rigify["family"], "rigify")
        self.assertEqual(rigify["add_function"], "add_builtin_rig")

    def test_paths_are_absolute_and_exist(self):
        for rig in self.run_list_rigs()["rigs"]:
            with self.subTest(rig=rig["identifier"]):
                self.assertTrue(os.path.isabs(rig["path"]))
                self.assertTrue(os.path.isfile(rig["path"]))

    def test_entries_are_sorted_by_family_then_name(self):
        self.install_custom_rig("my_rig")
        rigs = self.run_list_rigs()["rigs"]
        self.assertEqual(
            [(rig["family"], rig["name"]) for rig in rigs],
            [("standard", "default"), ("standard", "default_no_toes"),
             ("standard", "game_engine"), ("standard", "undocumented_rig"),
             ("rigify", "human"), ("rigify", "human_toes"), ("custom", "my_rig")])

    # -- weights ------------------------------------------------------------

    def test_a_rig_with_its_own_weights_reports_itself_as_the_source(self):
        default = self.entry(self.run_list_rigs(), "default")
        self.assertTrue(default["has_weights"])
        self.assertEqual(default["weights_from"], "default")
        self.assertTrue(os.path.isfile(default["weights_path"]))

    def test_default_no_toes_falls_back_to_the_default_weights(self):
        # The whole reason the payload walks get_rig_weight_fallbacks() rather
        # than testing weights.<name>.json: this rig ships no weights of its own
        # and is not unweighted.
        entry = self.entry(self.run_list_rigs(), "default_no_toes")
        self.assertTrue(entry["has_weights"])
        self.assertEqual(entry["weights_from"], "default")
        self.assertEqual(
            entry["weights_path"], os.path.join(self.standard_dir, "weights.default.json"))

    def test_rigify_human_falls_back_across_the_rigify_prefix(self):
        # The fallback table names "rigify.human_toes", but the file on disk is
        # weights.human_toes.json - add_builtin_rig() strips the prefix as it
        # goes, and so must this.
        entry = self.entry(self.run_list_rigs(), "rigify.human")
        self.assertTrue(entry["has_weights"])
        self.assertEqual(entry["weights_from"], "human_toes")
        self.assertEqual(
            entry["weights_path"], os.path.join(self.rigify_dir, "weights.human_toes.json"))

    def test_a_rig_with_no_weights_anywhere_is_reported_unweighted(self):
        entry = self.entry(self.run_list_rigs(), "undocumented_rig")
        self.assertFalse(entry["has_weights"])
        self.assertIsNone(entry["weights_path"])
        self.assertIsNone(entry["weights_from"])

    # -- labels -------------------------------------------------------------

    def test_labels_come_from_mpfbs_own_enum(self):
        result = self.run_list_rigs()
        self.assertEqual(self.entry(result, "default")["label"], "Default")
        self.assertEqual(
            self.entry(result, "default")["description"], "The default makehuman rig")
        # MPFB's own rigify labels, reported verbatim even though they read as
        # swapped: "human_toes" is the one it calls "Default".
        self.assertEqual(self.entry(result, "rigify.human_toes")["label"], "Default")
        self.assertEqual(self.entry(result, "rigify.human")["label"], "Default (no toes)")

    def test_a_rig_missing_from_the_enum_is_still_listed(self):
        # The directory is the authority on what exists, not the enum.
        entry = self.entry(self.run_list_rigs(), "undocumented_rig")
        self.assertIsNone(entry["label"])
        self.assertIsNone(entry["description"])

    def test_a_missing_enum_file_costs_labels_and_nothing_else(self):
        os.remove(os.path.join(self.standard_enum_path, "standard_rig.json"))
        result = self.run_list_rigs()
        self.assertIsNone(self.entry(result, "default")["label"])
        self.assertEqual(self.entry(result, "default")["name"], "default")
        # The rigify labels are read from a separate file and survive.
        self.assertEqual(self.entry(result, "rigify.human_toes")["label"], "Default")

    def test_an_unparseable_enum_file_costs_labels_and_nothing_else(self):
        with open(os.path.join(self.standard_enum_path, "standard_rig.json"), "w") as handle:
            handle.write("{not json at all")
        result = self.run_list_rigs()
        self.assertIsNone(self.entry(result, "default")["label"])
        self.assertEqual(len(result["rigs"]), 6)

    def test_the_pathlib_path_from_get_mpfb_root_does_not_break_anything(self):
        # get_mpfb_root() hands back a Path, and every value here has to survive
        # json.dumps() or strict_json takes the whole response down.
        json.dumps(self.run_list_rigs())

    # -- custom rigs --------------------------------------------------------

    def test_a_custom_rig_is_listed_with_its_own_identifier_and_function(self):
        path = self.install_custom_rig("my_rig")
        entry = self.entry(self.run_list_rigs(), "custom.my_rig")
        self.assertEqual(entry["name"], "my_rig")
        self.assertEqual(entry["family"], "custom")
        self.assertEqual(entry["add_function"], "add_custom_rig")
        self.assertEqual(entry["path"], path)
        self.assertIsNone(entry["label"])

    def test_custom_weights_sit_beside_the_rig_and_never_fall_back(self):
        self.install_custom_rig("my_rig")
        entry = self.entry(self.run_list_rigs(), "custom.my_rig")
        self.assertTrue(entry["has_weights"])
        self.assertEqual(entry["weights_from"], "my_rig")
        self.assertEqual(
            entry["weights_path"], os.path.join(self.user_rigs, "weights.my_rig.json"))

    def test_a_custom_rig_named_after_a_fallback_entry_still_does_not_fall_back(self):
        # add_custom_rig() ignores the fallback table entirely, so a custom rig
        # called default_no_toes must not borrow the built-in default's weights.
        self.install_custom_rig("default_no_toes", weights=False)
        entry = self.entry(self.run_list_rigs(), "custom.default_no_toes")
        self.assertFalse(entry["has_weights"])
        self.assertIsNone(entry["weights_from"])

    def test_identifying_bones_is_never_reported(self):
        self.install_custom_rig("my_rig")
        entry = self.entry(self.run_list_rigs(), "custom.my_rig")
        self.assertNotIn("identifying_bones", entry)

    # -- unrecognized files -------------------------------------------------

    def test_files_mpfb_refused_are_reported(self):
        self.install_custom_rig("my_rig")
        rejected_stem = os.path.join(self.user_rigs, "not a valid name.json")
        _write_json(rejected_stem, {"identifying_bones": ["root"]})
        no_bones = os.path.join(self.user_rigs, "nobones.json")
        _write_json(no_bones, {"bones": {}})
        result = self.run_list_rigs()
        self.assertEqual(
            sorted(result["unrecognized_custom_rig_files"]), sorted([rejected_stem, no_bones]))

    def test_weights_companions_are_never_reported_as_unrecognized(self):
        # They are .json files in a scanned rigs dir that get_custom_rigs()
        # rejects, so a naive set difference lists one per custom rig on every
        # real install - which is what live verification of FR 004 predicted.
        self.install_custom_rig("my_rig")
        self.assertEqual(self.run_list_rigs()["unrecognized_custom_rig_files"], [])

    def test_the_bundled_rig_directories_are_never_diffed(self):
        # Every rig.*.json MPFB ships would otherwise be "unrecognized".
        self.assertEqual(self.run_list_rigs()["unrecognized_custom_rig_files"], [])

    # -- rig_dirs -----------------------------------------------------------

    def test_rig_dirs_names_every_directory_looked_in(self):
        dirs = self.run_list_rigs()["rig_dirs"]
        self.assertEqual(
            [(entry["family"], entry["path"]) for entry in dirs],
            [("standard", self.standard_dir), ("rigify", self.rigify_dir),
             ("custom", self.user_rigs)])
        self.assertTrue(all(entry["exists"] for entry in dirs))

    def test_a_user_rigs_directory_that_does_not_exist_is_still_reported(self):
        # "We looked here and it was not there" is the answer a user missing
        # their custom rig actually needs.
        StubLocationService.user_data = os.path.join(self._rig_tree.name, "absent")
        dirs = self.run_list_rigs()["rig_dirs"]
        custom = [entry for entry in dirs if entry["family"] == "custom"]
        self.assertEqual(len(custom), 1)
        self.assertFalse(custom[0]["exists"])

    def test_a_second_root_is_scanned_when_there_is_one(self):
        second = os.path.join(self._rig_tree.name, "second")
        os.makedirs(os.path.join(second, "rigs"))
        StubLocationService.second_root = second
        dirs = [entry["path"] for entry in self.run_list_rigs()["rig_dirs"]]
        self.assertIn(os.path.join(second, "rigs"), dirs)

    def test_a_null_second_root_is_not_reported(self):
        StubLocationService.second_root = None
        custom = [entry for entry in self.run_list_rigs()["rig_dirs"]
                  if entry["family"] == "custom"]
        self.assertEqual([entry["path"] for entry in custom], [self.user_rigs])

    # -- rigify availability ------------------------------------------------

    def test_rigify_rigs_stay_listed_when_rigify_is_disabled(self):
        StubSystemService.rigify_available = False
        result = self.run_list_rigs()
        self.assertFalse(result["rigify_available"])
        entry = self.entry(result, "rigify.human")
        self.assertFalse(entry["available"])
        self.assertIn("Rigify", entry["unavailable_reason"])
        # A missing rig would be an unexplained absence; that is the whole point.
        self.assertIn("Rigify is not enabled", result["message"])

    def test_only_rigify_entries_become_unavailable(self):
        StubSystemService.rigify_available = False
        result = self.run_list_rigs()
        for rig in result["rigs"]:
            with self.subTest(rig=rig["identifier"]):
                self.assertEqual(rig["available"], rig["family"] != "rigify")

    def test_everything_is_available_when_rigify_is_enabled(self):
        result = self.run_list_rigs()
        self.assertTrue(result["rigify_available"])
        self.assertTrue(all(rig["available"] for rig in result["rigs"]))
        self.assertTrue(all(rig["unavailable_reason"] is None for rig in result["rigs"]))

    # -- refresh ------------------------------------------------------------

    def test_the_default_call_reads_the_cache(self):
        self.run_list_rigs()
        self.assertEqual(StubAssetService.custom_rig_calls, [True])
        self.assertEqual(StubAssetService.invalidations, 0)

    def test_refresh_rescans_in_a_single_call(self):
        self.run_list_rigs(refresh=True)
        self.assertEqual(StubAssetService.custom_rig_calls, [False])
        # use_cache=False repopulates the global; invalidating would leave it at
        # None for the custom-rig UI panel that reads the same one.
        self.assertEqual(StubAssetService.invalidations, 0)

    def test_refresh_falls_back_when_use_cache_is_not_accepted(self):
        StubAssetService.reject_use_cache = True
        self.run_list_rigs(refresh=True)
        self.assertEqual(StubAssetService.invalidations, 1)
        self.assertEqual(StubAssetService.custom_rig_calls, [True])

    # -- the response as a whole --------------------------------------------

    def test_the_result_is_json_safe_and_carries_the_vocabulary(self):
        self.install_custom_rig("my_rig")
        result = self.run_list_rigs()
        json.dumps(result)
        self.assertEqual(result["families"], ["standard", "rigify", "custom"])
        for rig in result["rigs"]:
            self.assertIn(rig["family"], result["families"])

    def test_the_message_points_at_identifier_rather_than_name(self):
        self.assertIn("identifier", self.run_list_rigs()["message"])


class PayloadSourceTests(unittest.TestCase):
    """Two rules the payload has to keep that are easiest to assert on source."""

    def test_the_payload_never_imports_an_mpfb_submodule(self):
        source = codegen.read_payload("list_rigs.py")
        self.assertNotIn("import_module", source)
        self.assertIn('_MPFB_SERVICES["SystemService"]', source)
        # LocationService and the rest are reached the same way, one file over:
        # the fragment the tool names beside this payload.
        fragment = codegen.read_shared("rig_lookup.py")
        self.assertNotIn("import_module", fragment)
        self.assertIn('_MPFB_SERVICES["LocationService"]', fragment)

    def test_the_payload_needs_no_bpy(self):
        # Nothing here touches the scene, and saying so in a test is what keeps
        # a later edit from quietly making this tool scene-dependent. The
        # fragment is held to the same rule: mpfb_add_rig does touch the scene,
        # but the shared half of it is pure path resolution.
        self.assertNotIn("import bpy", codegen.read_payload("list_rigs.py"))
        self.assertNotIn("import bpy", codegen.read_shared("rig_lookup.py"))


if __name__ == "__main__":
    unittest.main()
