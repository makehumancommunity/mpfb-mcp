# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_assets tool: argument validation, and the generated
code's filtering, paging and pack attribution over MPFB's asset cache.

Migrated by FR 031, so three layers rather than two (see
``tests/test_list_objects.py``, the template): the wrapper with ``send_code``
mocked on the seam, the bridge path against ``tests/fake_bridge.py``, and the
payload against the stubs. **The payload layer is frozen.** What keeps the
bridge half honest is ``tests/test_fragment_drift.py``, which compares
``asset_sections.py`` against ``bridge/mpfb_bridge/shared/asset_sections.py``
on every run, and ``bridge/test/tests/lll_list_assets_test.py``, which puts the
questions below to a real MPFB over an asset library the test builds.

The share of this module that goes with the payload: 325 of its 574 lines, 57%.

Formerly two layers, as in tests/test_get_status.py: the tool wrapper with send_code
mocked, then the assembled source executed against the stub services in
tests/blender_stubs.py. Unlike tests/test_list_rigs.py there is no temporary
directory here, because this payload never touches the filesystem - it asks
AssetService, and what needs reproducing is that service's behavior rather than
a directory layout.

The stub library deliberately carries the awkward cases a real install has, each
of which is a branch the payload exists to get right: an asset claimed by two
packs, an asset claimed by none, a pack listing an asset that is not installed,
two assets whose labels collide, and an asset sitting directly in the asset root
rather than in a directory of its own.

Run with::

    python -m unittest tests.test_list_assets -v
"""

__all__ = ()

import json
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import backend
from tests import fake_bridge

from mpfbmcp.tools import list_assets

from tests.blender_stubs import GeneratedCodeTestCase, StubAssetService
from tests import generated_path


# These tests are about the **generated path**: they mock `backend.send_code`
# and assert about the program that reached it. FR 032 made the bridge the
# default, so saying so is now necessary rather than implied.
# See tests/generated_path.py.
setUpModule = generated_path.pin
tearDownModule = generated_path.unpin

# One tree, standing in for two data roots. The second root holds a single
# clothes asset, so that a root is genuinely per-subdir rather than global.
_USER_CLOTHES = "/data/user/clothes"
_SECOND_CLOTHES = "/data/second/clothes"
_USER_HAIR = "/data/user/hair"
_USER_SKINS = "/data/user/skins"
_USER_PROXIES = "/data/user/proxymeshes"


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_assets.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_assets"].fn  # pylint: disable=protected-access


class ArgumentValidationTests(unittest.TestCase):
    """Everything rejected here would otherwise round-trip to Blender to fail."""

    def setUp(self):
        self.tool = _tool_callable()

    def _sent_params(self, **kwargs):
        with mock.patch("mpfbmcp.backend.send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(**kwargs)
        source = send_code.call_args[0][0]
        self.assertIn("# --- payload: list_assets.py ---", source)
        # The section table this payload reports from is the one mpfb_add_asset
        # resolves a fragment with, so it has to be the same table.
        self.assertIn("# --- shared: asset_sections.py ---", source)
        # Just the prelude's one binding, executed on its own: the rest of the
        # generated source is the raising bootstrap, which has no MPFB to find
        # out here. Asserting on values rather than on source text is the point
        # - the parameters travel as data, not as interpolated code.
        binding = [line for line in source.splitlines()
                   if line.startswith("PARAMS = json.loads(")]
        self.assertEqual(len(binding), 1)
        namespace = {}
        exec("import json\n" + binding[0], namespace)  # noqa: S102
        return namespace["PARAMS"]

    def test_default_call_filters_nothing_and_pages_from_the_start(self):
        self.assertEqual(self._sent_params(), {
            "asset_subdir": None,
            "name_contains": None,
            "pack": None,
            "limit": 200,
            "offset": 0,
            "refresh": False,
        })

    def test_arguments_are_carried_across_verbatim(self):
        params = self._sent_params(
            asset_subdir="clothes", name_contains="fedora", pack="hair03",
            limit=10, offset=20, refresh=True)

        self.assertEqual(params, {
            "asset_subdir": "clothes",
            "name_contains": "fedora",
            "pack": "hair03",
            "limit": 10,
            "offset": 20,
            "refresh": True,
        })

    def test_non_string_filters_are_rejected_locally(self):
        for argument in ("asset_subdir", "name_contains", "pack"):
            for bad in (1, True, [], object()):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch("mpfbmcp.backend.send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_code.assert_not_called()

    def test_empty_filters_are_rejected_rather_than_treated_as_omitted(self):
        # An explicitly empty value and an omitted one come from different
        # mistakes, and an empty substring filter would match everything.
        for argument in ("asset_subdir", "name_contains", "pack"):
            for bad in ("", "   ", "\t"):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch("mpfbmcp.backend.send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_code.assert_not_called()

    def test_bad_limits_and_offsets_are_rejected_locally(self):
        bad_calls = (
            {"limit": -1},
            {"limit": list_assets.MAX_LIMIT + 1},
            {"limit": 1.5},
            {"limit": "10"},
            # bool is a subclass of int, so limit=True would silently page one
            # entry at a time rather than fail.
            {"limit": True},
            {"offset": -1},
            {"offset": 2.5},
            {"offset": False},
        )
        for kwargs in bad_calls:
            with self.subTest(**kwargs):
                with mock.patch("mpfbmcp.backend.send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(**kwargs)
                send_code.assert_not_called()

    def test_the_maximum_limit_itself_is_accepted(self):
        self.assertEqual(self._sent_params(limit=list_assets.MAX_LIMIT)["limit"],
                         list_assets.MAX_LIMIT)

    def test_non_bool_refresh_is_rejected_locally(self):
        for bad in (1, 0, "true", "false", None, []):
            with self.subTest(refresh=bad):
                with mock.patch("mpfbmcp.backend.send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(refresh=bad)
                send_code.assert_not_called()

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
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




class ListAssetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the section table, the cap, the paging
    order, the pack attribution - is checked against a real MPFB in
    ``bridge/test/tests/lll_list_assets_test.py``.
    """

    def setUp(self):
        super().setUp()
        self.tool = _tool_callable()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_assets": fake_bridge.ok_envelope("list_assets", {"count": 0}),
        })

    def test_the_tool_sends_the_list_assets_command_with_every_parameter(self):
        self.tool()

        self.assertEqual(self.bridge.commands()[-1], "list_assets")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {
            "asset_subdir": None, "name_contains": None, "pack": None,
            "limit": 200, "offset": 0, "refresh": False})

    def test_arguments_cross_the_wire_verbatim(self):
        self.tool(asset_subdir="clothes", name_contains="fedora", pack="system",
                  limit=5, offset=10, refresh=True)

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(request["params"], {
            "asset_subdir": "clothes", "name_contains": "fedora", "pack": "system",
            "limit": 5, "offset": 10, "refresh": True})
        # asset_sections.py is a property of how a program is assembled; on the
        # bridge it is a module the command imports.
        self.assertNotIn("asset_sections", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self):
        for arguments in ({"limit": True}, {"limit": -1}, {"offset": True},
                          {"limit": 1001}, {"refresh": "false"}, {"asset_subdir": "  "}):
            with self.subTest(**arguments):
                with self.assertRaises(ValueError):
                    self.tool(**arguments)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self):
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="list_assets", state="absent"))

        response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class ListAssetsGeneratedCodeTests(GeneratedCodeTestCase):
    """The payload, run against the stub asset library."""

    def setUp(self):
        super().setUp()
        StubAssetService.asset_roots = {
            "clothes": [_USER_CLOTHES, _SECOND_CLOTHES],
            "hair": [_USER_HAIR],
            "skins": [_USER_SKINS],
            "proxymeshes": [_USER_PROXIES],
            # A subdir with a root but nothing in it, which is a different
            # answer from a subdir whose root does not exist at all.
            "poses": ["/data/user/poses"],
        }
        StubAssetService.asset_files = {
            "clothes": [
                _USER_CLOTHES + "/fedora/fedora.mhclo",
                _USER_CLOTHES + "/jeans/jeans.mhclo",
                _SECOND_CLOTHES + "/handmade_shirt/handmade_shirt.mhclo",
                _USER_CLOTHES + "/sunglasses/sunglasses.mhclo",
            ],
            "hair": [
                _USER_HAIR + "/ponytail/ponytail.mhclo",
            ],
            "skins": [
                _USER_SKINS + "/young_caucasian/young_caucasian.mhmat",
                # An asset lying directly in the asset root rather than in a
                # directory of its own, exactly as skins/default.mhmat does on a
                # real install.
                _USER_SKINS + "/default.mhmat",
                # Two files whose labels collide: MPFB's cache is keyed by
                # label, so only one of these survives.
                _USER_SKINS + "/old_skin/old_skin.mhmat",
                _USER_SKINS + "/old skin/old skin.mhmat",
            ],
            "proxymeshes": [
                _USER_PROXIES + "/proxy741/proxy741.proxy",
            ],
            "poses": [],
        }
        StubAssetService.thumbs = (_USER_CLOTHES + "/fedora/fedora.thumb",)
        StubAssetService.packs = {
            # "sunglasses" is claimed by two packs, "fedora" by one, and
            # "handmade_shirt" by none. "vanished" is listed by a pack but is
            # not installed, which is the case that stops the tool reporting
            # from metadata rather than from disk.
            "hats01": ["fedora", "vanished"],
            "glasses": ["sunglasses"],
            "various01": ["sunglasses", "jeans"],
            "hair03_ccby": ["ponytail"],
        }

    def run_list_assets(self, **params):
        arguments = {
            "asset_subdir": None,
            "name_contains": None,
            "pack": None,
            "limit": 200,
            "offset": 0,
            "refresh": False,
        }
        arguments.update(params)
        # The same fragment the tool module names, so what runs here is the same
        # program mpfb_list_assets sends.
        return self.run_payload(
            "list_assets.py", arguments, shared=["asset_sections.py"])

    def names_in(self, result):
        return [entry["name"] for entry in result["assets"]]

    def entry_named(self, result, name):
        for entry in result["assets"]:
            if entry["name"] == name:
                return entry
        self.fail("no entry called " + name + " in " + repr(self.names_in(result)))

    def test_unfiltered_call_lists_every_subdir_in_the_section_table(self):
        result = self.run_list_assets()

        self.assertEqual(self.names_in(result), [
            "fedora", "handmade_shirt", "jeans", "sunglasses",
            "ponytail",
            "proxy741",
            "default", "old skin", "young_caucasian",
        ])
        self.assertEqual(result["count"], 9)
        self.assertEqual(result["total_count"], 9)
        self.assertIs(result["truncated"], False)

    def test_the_section_table_is_read_from_mpfb(self):
        result = self.run_list_assets()

        self.assertIs(result["section_table_from_mpfb"], True)
        self.assertEqual(result["known_subdirs"],
                         ["proxymeshes", "skins", "hair", "eyes", "clothes", "poses"])

    def test_the_section_table_falls_back_rather_than_raising(self):
        # These are MPFB's own module-level names, read with a fallback because
        # MPFB may rename them without notice.
        import sys  # pylint: disable=import-outside-toplevel
        module = sys.modules[StubAssetService.__module__]
        with mock.patch.object(module, "ASSET_LIBRARY_SECTIONS", None):
            result = self.run_list_assets(asset_subdir="ink_layers")

        self.assertIs(result["section_table_from_mpfb"], False)
        self.assertIn("ink_layers", result["known_subdirs"])
        self.assertIs(result["subdir_recognized"], True)
        self.assertEqual(len(result["known_subdirs"]), 11)

    def test_an_entry_carries_everything_a_later_tool_needs(self):
        result = self.run_list_assets(asset_subdir="clothes", name_contains="fedora")

        self.assertEqual(self.entry_named(result, "fedora"), {
            "name": "fedora",
            "label": "Fedora",
            "fragment": "fedora/fedora.mhclo",
            "path": _USER_CLOTHES + "/fedora/fedora.mhclo",
            "object_type": "Clothes",
            "asset_subdir": "clothes",
            "file_type": "mhclo",
            "pack": "hats01",
            "pack_ambiguous": False,
            "thumb_path": _USER_CLOTHES + "/fedora/fedora.thumb",
        })

    def test_the_two_rows_that_are_not_scene_object_types(self):
        # A skin's object_type is "Material" and a proxy is a .proxy file, so
        # neither the type nor the extension can be inferred from the other.
        skins = self.run_list_assets(asset_subdir="skins")
        proxies = self.run_list_assets(asset_subdir="proxymeshes")

        self.assertEqual(self.entry_named(skins, "young_caucasian")["object_type"], "Material")
        self.assertEqual(self.entry_named(skins, "young_caucasian")["file_type"], "mhmat")
        self.assertEqual(self.entry_named(proxies, "proxy741")["object_type"], "Proxymeshes")
        self.assertEqual(self.entry_named(proxies, "proxy741")["file_type"], "proxy")

    def test_the_blender_preview_object_never_reaches_the_response(self):
        # item["thumb"] is a bpy preview in the real cache; reporting it would
        # fail strict_json and take the whole answer down.
        result = self.run_list_assets()

        json.dumps(result)
        for entry in result["assets"]:
            self.assertNotIn("thumb", entry)
            self.assertNotIn("_claimants", entry)

    def test_pack_attribution_is_derived_from_the_directory_name(self):
        result = self.run_list_assets()

        self.assertEqual(self.entry_named(result, "fedora")["pack"], "hats01")
        self.assertIs(self.entry_named(result, "fedora")["pack_ambiguous"], False)
        # Claimed by two packs: the first alphabetically, and flagged.
        self.assertEqual(self.entry_named(result, "sunglasses")["pack"], "glasses")
        self.assertIs(self.entry_named(result, "sunglasses")["pack_ambiguous"], True)
        # Hand-installed: no pack claims the name, which is ordinary.
        self.assertIsNone(self.entry_named(result, "handmade_shirt")["pack"])

    def test_an_asset_lying_directly_in_the_asset_root_is_not_attributed(self):
        # Its containing directory is the root, named for the subdir, so the
        # directory-name join would attribute it to whichever pack happened to
        # ship an asset called "skins".
        result = self.run_list_assets(asset_subdir="skins")
        entry = self.entry_named(result, "default")

        self.assertIsNone(entry["pack"])
        self.assertIs(entry["pack_ambiguous"], False)
        self.assertEqual(entry["fragment"], "skins/default.mhmat")

    def test_a_pack_listing_an_asset_that_is_not_installed_reports_nothing(self):
        # The metadata says hats01 ships "vanished"; the disk says otherwise,
        # and the disk wins.
        result = self.run_list_assets(pack="hats01")

        self.assertEqual(self.names_in(result), ["fedora"])

    def test_the_label_collision_under_reports_and_is_pinned_here(self):
        # A limitation of MPFB's cache, which keys by label: "old_skin" and
        # "old skin" produce one entry, not two, so the counts under-report.
        result = self.run_list_assets(asset_subdir="skins")

        self.assertEqual(len(StubAssetService.asset_files["skins"]), 4)
        self.assertEqual(result["total_count"], 3)
        self.assertEqual(result["counts_by_subdir"], {"skins": 3})

    def test_name_filter_matches_name_or_label_case_insensitively(self):
        self.assertEqual(self.names_in(self.run_list_assets(name_contains="FED")), ["fedora"])
        # The label is "Handmade shirt" while the name is "handmade_shirt", so a
        # search with a space only matches through the label.
        self.assertEqual(
            self.names_in(self.run_list_assets(name_contains="made shirt")),
            ["handmade_shirt"])

    def test_pack_filter_uses_mpfb_substring_semantics(self):
        # "hair03" finds the pack "hair03_ccby", the same way
        # get_asset_names_in_pack_pattern() matches.
        self.assertEqual(self.names_in(self.run_list_assets(pack="hair03")), ["ponytail"])

    def test_pack_filter_matches_any_claiming_pack_not_just_the_reported_one(self):
        # sunglasses reports pack "glasses" because it sorts first, but it is
        # genuinely in various01 too, and a filter that missed it would report
        # an installed asset as absent.
        result = self.run_list_assets(pack="various01")

        self.assertEqual(self.names_in(result), ["jeans", "sunglasses"])
        self.assertEqual(self.entry_named(result, "sunglasses")["pack"], "glasses")

    def test_filters_combine_with_and(self):
        result = self.run_list_assets(
            asset_subdir="clothes", name_contains="s", pack="various01")

        self.assertEqual(self.names_in(result), ["jeans", "sunglasses"])

    def test_a_misspelled_subdir_is_distinguishable_from_an_empty_one(self):
        misspelled = self.run_list_assets(asset_subdir="clothing")
        empty = self.run_list_assets(asset_subdir="poses")

        self.assertIs(misspelled["subdir_recognized"], False)
        self.assertEqual(misspelled["assets"], [])
        self.assertEqual(misspelled["counts_by_subdir"], {})
        self.assertEqual(misspelled["requested_subdir"], "clothing")
        self.assertIn("known_subdirs", misspelled)

        self.assertIs(empty["subdir_recognized"], True)
        self.assertEqual(empty["assets"], [])
        self.assertEqual(empty["counts_by_subdir"], {"poses": 0})
        # The roots really were searched, which is a third distinct answer.
        self.assertEqual(empty["asset_roots_searched"], {"poses": ["/data/user/poses"]})

    def test_subdir_matching_is_case_insensitive_and_reported_in_mpfb_spelling(self):
        result = self.run_list_assets(asset_subdir="  Clothes ")

        self.assertIs(result["subdir_recognized"], True)
        self.assertEqual(result["counts_by_subdir"], {"clothes": 4})

    def test_a_misspelled_pack_is_distinguishable_from_an_empty_one(self):
        misspelled = self.run_list_assets(pack="hats99")

        self.assertIs(misspelled["pack_recognized"], False)
        self.assertEqual(misspelled["assets"], [])
        self.assertEqual(misspelled["requested_pack"], "hats99")
        self.assertEqual(misspelled["known_packs"],
                         ["glasses", "hair03_ccby", "hats01", "various01"])

    def test_asset_roots_searched_is_per_subdir_and_narrower_than_the_data_roots(self):
        result = self.run_list_assets()

        self.assertEqual(result["asset_roots_searched"]["clothes"],
                         [_USER_CLOTHES, _SECOND_CLOTHES])
        self.assertEqual(result["asset_roots_searched"]["hair"], [_USER_HAIR])
        # get_available_data_roots() is wider, which is exactly why the response
        # reports the narrower one.
        self.assertNotEqual(sorted(StubAssetService.get_available_data_roots()),
                            sorted(result["asset_roots_searched"]["clothes"]))

    def test_counts_by_subdir_ignores_the_name_and_pack_filters(self):
        result = self.run_list_assets(name_contains="fedora")

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(result["counts_by_subdir"],
                         {"proxymeshes": 1, "skins": 3, "hair": 1, "eyes": 0, "clothes": 4,
                      "poses": 0})

    def test_paging_neither_skips_nor_repeats(self):
        whole = self.names_in(self.run_list_assets())
        first = self.run_list_assets(limit=4)
        second = self.run_list_assets(limit=4, offset=4)
        third = self.run_list_assets(limit=4, offset=8)

        self.assertEqual(
            self.names_in(first) + self.names_in(second) + self.names_in(third), whole)
        self.assertEqual(first["count"], 4)
        self.assertEqual(third["count"], 1)

    def test_truncation_describes_the_matched_set_rather_than_the_page(self):
        page = self.run_list_assets(limit=2)

        self.assertEqual(page["count"], 2)
        self.assertEqual(page["total_count"], 9)
        self.assertIs(page["truncated"], True)
        self.assertEqual(page["limit"], 2)
        self.assertEqual(page["offset"], 0)
        self.assertIn("not the whole library", page["message"])

    def test_a_last_page_is_still_flagged_as_a_subset(self):
        # Entries were left out, even though none follow this page.
        page = self.run_list_assets(limit=4, offset=8)

        self.assertIs(page["truncated"], True)
        self.assertEqual(page["total_count"], 9)

    def test_an_offset_past_the_end_answers_rather_than_fails(self):
        page = self.run_list_assets(offset=500)

        self.assertEqual(page["assets"], [])
        self.assertEqual(page["count"], 0)
        self.assertEqual(page["total_count"], 9)

    def test_ordering_is_deterministic_across_a_reshuffled_library(self):
        first = self.names_in(self.run_list_assets())
        StubAssetService.asset_files["clothes"] = list(
            reversed(StubAssetService.asset_files["clothes"]))

        self.assertEqual(self.names_in(self.run_list_assets()), first)

    def test_default_call_does_not_rescan(self):
        self.run_list_assets()

        self.assertEqual(StubAssetService.update_all_calls, 0)
        self.assertEqual(
            [call[0] for call in StubAssetService.asset_list_calls],
            ["proxymeshes", "skins", "hair", "eyes", "clothes", "poses"])

    def test_refresh_rescans_the_whole_library_exactly_once(self):
        self.run_list_assets(asset_subdir="clothes", refresh=True)

        self.assertEqual(StubAssetService.update_all_calls, 1)
        # Still only the requested subdir is read back out.
        self.assertEqual([call[0] for call in StubAssetService.asset_list_calls], ["clothes"])

    def test_each_subdir_is_read_with_its_own_asset_type(self):
        self.run_list_assets()

        self.assertIn(("skins", "mhmat"), StubAssetService.asset_list_calls)
        self.assertIn(("proxymeshes", "proxy"), StubAssetService.asset_list_calls)
        self.assertIn(("poses", "bvh"), StubAssetService.asset_list_calls)


if __name__ == "__main__":
    unittest.main()
