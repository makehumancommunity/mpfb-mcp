# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_targets tool: argument validation, and the generated
code's two-source scan of the bundled index and the user target directories.

Migrated by FR 031, so three layers rather than two (see
``tests/test_list_objects.py``, the template). **The payload layer is frozen**,
and this is the tool whose migration mattered most to measure: it carried 26 KB
of shared fragment source on a cold call, which is the number
``src/mpfbmcp/shared_cache.py`` exists because of, and over the bridge it is a
single JSON request. What it *answers* is now asked of a real MPFB in
``bridge/test/tests/nnn_list_targets_test.py``.

The share of this module that goes with the payload: 420 of its 719 lines, 58%.

Formerly two layers, as in tests/test_get_status.py: the tool wrapper with
send_code mocked, then the assembled source executed against the stub services in
tests/blender_stubs.py. As in tests/test_list_rigs.py the tree those run against
is a real temporary directory, because most of this payload is filesystem logic
- os.walk(), os.listdir(), an rglob through the stub AssetService - and mocking
that away would leave nothing under test.

The tree reproduces the awkward parts of a real install, since each is a branch
the payload exists to get right: a section name present in *both* the bundled
index and a user directory (MPFB merges those rather than keeping them apart),
a section with no categories, bundled directories with no section at all, a
directory holding no targets, a ``.target.gz`` where MPFB's own scan matches
only ``*.target``, a target reachable through two scans at once, and a name long
enough that its shape key name is encoded and no longer equals its filename.

Run with::

    python -m unittest tests.test_list_targets -v
"""

__all__ = ()

import json
import os
import tempfile
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from tests import fake_bridge

from mpfbmcp import backend, codegen, shared_cache
from mpfbmcp.tools import list_targets

from tests.blender_stubs import (
    GeneratedCodeTestCase, StubAssetService, StubLocationService, StubTargetService)
from tests import generated_path


# These tests are about the **generated path**: they mock `backend.send_code`
# and assert about the program that reached it. FR 032 made the bridge the
# default, so saying so is now necessary rather than implied.
# See tests/generated_path.py.
setUpModule = generated_path.pin
tearDownModule = generated_path.unpin

# A trimmed target.json with the shape MPFB's really has. "arms" is the section
# whose name a user directory also uses, "measure" is the real index's empty
# section, and the left/right category carries the opposites table the modeling
# sliders are built from.
_TARGET_JSON = {
    "arms": {
        "include_per_default": True,
        "label": "Arms",
        "unsorted": False,
        "categories": [
            {
                "has_left_and_right": True,
                "label": "lowerarm-scale-depth-decr-incr",
                "name": "lowerarm-scale-depth-decr-incr",
                "opposites": {
                    "negative-left": "l-lowerarm-scale-depth-decr",
                    "negative-right": "r-lowerarm-scale-depth-decr",
                    "negative-unsided": "",
                    "positive-left": "l-lowerarm-scale-depth-incr",
                    "positive-right": "r-lowerarm-scale-depth-incr",
                    "positive-unsided": "",
                },
                "targets": [
                    "l-lowerarm-scale-depth-decr", "r-lowerarm-scale-depth-incr",
                    "r-lowerarm-scale-depth-decr", "l-lowerarm-scale-depth-incr",
                ],
            },
            {
                "has_left_and_right": False,
                "label": "upperarm-fat-decr-incr",
                "name": "upperarm-fat-decr-incr",
                "opposites": {
                    "negative-left": "", "negative-right": "",
                    "negative-unsided": "upperarm-fat-decr",
                    "positive-left": "", "positive-right": "",
                    "positive-unsided": "upperarm-fat-incr",
                },
                "targets": ["upperarm-fat-decr", "upperarm-fat-incr"],
            },
        ],
    },
    "nose": {
        "include_per_default": True,
        "label": "Nose",
        "unsorted": False,
        "categories": [
            {
                "has_left_and_right": False,
                "label": "nose-scale-depth-decr-incr",
                "name": "nose-scale-depth-decr-incr",
                "opposites": {
                    "negative-left": "", "negative-right": "",
                    "negative-unsided": "nose-scale-depth-decr",
                    "positive-left": "", "positive-right": "",
                    "positive-unsided": "nose-scale-depth-incr",
                },
                "targets": ["nose-scale-depth-decr", "nose-scale-depth-incr"],
            },
        ],
    },
    # The real index's "measure": a section that exists, has no categories, and
    # has no directory on disk either.
    "measure": {
        "include_per_default": False,
        "label": "measure",
        "unsorted": False,
        "categories": [],
    },
}

# Over 60 characters after the extension is stripped, and containing words from
# MPFB's encoding table, so the encoded name provably differs from the filename.
_LONG_NAME = "young-female-average-caucasian-uncommon-proportions-weight-height-experiment"


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_targets.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_targets"].fn  # pylint: disable=protected-access


def _touch(path, content="dummy target data"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class ArgumentValidationTests(unittest.TestCase):
    """Shape checked here, vocabulary deliberately not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_default_call_sends_the_documented_defaults(self):
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        source = send_code.call_args[0][0]
        self.assertIn("# --- payload: list_targets.py ---", source)
        self.assertIn(json.dumps({
            "section": None, "name_contains": None, "limit": 200, "offset": 0}), source)

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(section="arms", name_contains="Nose", limit=5, offset=10)
        self.assertIn(json.dumps({
            "section": "arms", "name_contains": "Nose", "limit": 5, "offset": 10}),
            send_code.call_args[0][0])

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is this package's: `status` and `message` are unchanged,
        # and `error` is what a caller branches on whichever transport answered.
        # Since FR 031 this tool's fragments go through the seam rather than
        # around it, so the mapping applies to a cached-fragment call too.
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "error", "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)

    def test_strict_json_is_requested(self):
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool()
        self.assertIs(send_code.call_args[1]["strict_json"], True)

    def test_non_string_or_empty_text_arguments_are_rejected_locally(self):
        # An explicitly empty value is never quietly read as an omitted one: the
        # two arise from different mistakes.
        for argument in ("section", "name_contains"):
            for bad in (1, True, [], object(), "", "   ", "\t"):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(shared_cache, "send_code") as send_code:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_code.assert_not_called()

    def test_bad_limit_and_offset_are_rejected_locally(self):
        # bool is a subclass of int, so limit=True would otherwise page one
        # entry at a time rather than fail.
        for bad in (True, False, -1, "10", 1.5, None):
            with self.subTest(limit=bad):
                with mock.patch.object(shared_cache, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(limit=bad)
                send_code.assert_not_called()
            with self.subTest(offset=bad):
                with mock.patch.object(shared_cache, "send_code") as send_code:
                    with self.assertRaises(ValueError):
                        self.tool(offset=bad)
                send_code.assert_not_called()

    def test_limit_above_the_ceiling_is_rejected_locally(self):
        with mock.patch.object(shared_cache, "send_code") as send_code:
            with self.assertRaises(ValueError):
                self.tool(limit=list_targets.MAX_LIMIT + 1)
        send_code.assert_not_called()
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(limit=list_targets.MAX_LIMIT)
        send_code.assert_called_once()

    def test_an_unknown_section_is_not_rejected_locally(self):
        # Half the sections are synthesized from the user's own directories, so
        # a vocabulary kept here could not be right even in principle. The
        # generated code answers it with section_recognized.
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            self.tool(section="no-such-section")
        send_code.assert_called_once()




class ListTargetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the two-source merge, the over-60-character
    encoding, the gzipped target MPFB's own scan misses - is checked against a
    real MPFB in ``bridge/test/tests/nnn_list_targets_test.py``.
    """

    def setUp(self):
        super().setUp()
        self.tool = _tool_callable()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_targets": fake_bridge.ok_envelope("list_targets", {"count": 0}),
        })

    def test_the_tool_sends_the_list_targets_command(self):
        self.tool()

        self.assertEqual(self.bridge.commands()[-1], "list_targets")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {
            "section": None, "name_contains": None, "limit": 200, "offset": 0})

    def test_the_cached_fragment_does_not_reach_the_bridge(self):
        # The one tool the session source cache was built for. On the bridge
        # there is no source to cache: target_categories.py is a module the
        # command imports, and the request is exactly the parameters. Nothing
        # of `shared_cache`'s machinery - the loader, the fingerprint, the
        # carried/reused marker - appears on this wire.
        self.tool(section="arms", name_contains="Nose", limit=5, offset=10)

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(request["params"], {
            "section": "arms", "name_contains": "Nose", "limit": 5, "offset": 10})
        self.assertNotIn("target_categories", str(request))
        self.assertNotIn("cached shared", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self):
        for arguments in ({"limit": True}, {"limit": -1}, {"limit": 1001},
                          {"offset": True}, {"section": "  "}, {"name_contains": ""}):
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
                command="list_targets", state="absent"))

        response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class ListTargetsGeneratedCodeTests(GeneratedCodeTestCase):
    """The payload, run against a real target tree and the stub services."""

    def setUp(self):
        super().setUp()
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        root = self._temporary.name

        self.mpfb_data = os.path.join(root, "mpfb", "data")
        self.system_targets = os.path.join(self.mpfb_data, "targets")
        self.target_json = os.path.join(self.system_targets, "target.json")
        os.makedirs(self.system_targets)
        self.write_target_json(_TARGET_JSON)

        # Bundled target files. Never enumerated in the response - the index
        # names them - but they are what the unindexed diff counts.
        for name in ("l-lowerarm-scale-depth-decr", "l-lowerarm-scale-depth-incr"):
            _touch(os.path.join(self.system_targets, "arms", name + ".target.gz"))
        _touch(os.path.join(self.system_targets, "nose", "nose-scale-depth-incr.target.gz"))
        for index in range(3):
            _touch(os.path.join(
                self.system_targets, "asym", "asym-brow-" + str(index) + ".target.gz"))
        for index in range(2):
            _touch(os.path.join(
                self.system_targets, "expression", "expr-" + str(index) + ".target.gz"))
        for index in range(4):
            _touch(os.path.join(
                self.system_targets, "macrodetails", "macro-" + str(index) + ".target.gz"))
        # Holds no target file at all, so it must drop out of the diff by its
        # count rather than by a name check.
        _touch(os.path.join(self.system_targets, "_images", "arms.png"))

        self.user_data = os.path.join(root, "user", "data")
        self.user_targets = os.path.join(self.user_data, "targets")
        self.user_custom = os.path.join(self.user_data, "custom")

        # A section name shared with the bundled index. MPFB's own panel appends
        # these into the existing section rather than making a second one.
        _touch(os.path.join(self.user_targets, "arms", "elvs_arm_bulk.target"))
        _touch(os.path.join(self.user_targets, "arms", "elvs_arm_slim.target"))
        # Gzipped, in a directory where MPFB's scan matches only *.target.
        _touch(os.path.join(self.user_targets, "arms", "elvs_arm_gz.target.gz"))
        # A section that exists only as a user directory.
        _touch(os.path.join(self.user_targets, "animal", "cat_ears.target"))
        _touch(os.path.join(self.user_targets, "animal", _LONG_NAME + ".target"))
        # Reachable by both scans at once: get_asset_roots("targets/custom")
        # finds it, and so does the rglob of <user data>/targets.
        _touch(os.path.join(self.user_targets, "custom", "dual_reachable.target"))
        # The custom section proper, beside a file that is not a target at all.
        _touch(os.path.join(self.user_custom, "closed_eyes.target"))
        _touch(os.path.join(self.user_custom, "vwide.target.gz"))
        _touch(os.path.join(self.user_custom, "not_a_target.safetensors"))

        StubLocationService.mpfb_data = self.mpfb_data
        StubLocationService.user_data = self.user_data
        StubAssetService.asset_roots = {
            "custom": [self.user_custom],
            "targets/custom": [os.path.join(self.user_targets, "custom")],
        }

    def write_target_json(self, data):
        with open(self.target_json, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def run_list_targets(self, section=None, name_contains=None, limit=200, offset=0):
        # The fragment is named the way the tool names it: FR 017 moved this
        # payload's scan of the user target directories onto it, so what runs
        # here is the same scan mpfb_set_targets resolves a category with.
        return self.run_payload("list_targets.py", {
            "section": section,
            "name_contains": name_contains,
            "limit": limit,
            "offset": offset,
        }, shared=["target_categories.py"])

    def section_entry(self, result, name):
        for entry in result["sections"]:
            if entry["name"] == name:
                return entry
        self.fail("no section called " + repr(name) + " in " + repr(
            [entry["name"] for entry in result["sections"]]))

    def target_entry(self, result, name):
        for entry in result["user_targets"]:
            if entry["name"] == name:
                return entry
        self.fail("no user target called " + repr(name) + " in " + repr(
            [entry["name"] for entry in result["user_targets"]]))

    # -- the bundled index --------------------------------------------------

    def test_target_json_is_located_and_reported_rather_than_returned(self):
        result = self.run_list_targets()
        self.assertEqual(result["target_json_path"], self.target_json)
        self.assertIs(result["target_json_exists"], True)
        self.assertEqual(result["system_targets_dir"], self.system_targets)
        # The index itself is never inlined: its size is the whole reason the
        # path is reported instead.
        self.assertNotIn("categories", json.dumps(result["sections"]))

    def test_a_missing_target_json_is_an_answer_not_an_error(self):
        os.remove(self.target_json)
        result = self.run_list_targets()
        self.assertIs(result["target_json_exists"], False)
        self.assertEqual(result["target_json_path"], self.target_json)
        # The user directories were still scanned, which is the half of the
        # answer that survives a broken install.
        self.assertGreater(len(result["user_targets"]), 0)
        self.assertIn("No target.json", result["message"])
        self.assertEqual(
            [entry["source"] for entry in result["sections"]],
            ["user"] * len(result["sections"]))

    def test_an_unparsable_target_json_is_also_an_answer(self):
        with open(self.target_json, "w", encoding="utf-8") as handle:
            handle.write("{not json at all")
        result = self.run_list_targets()
        self.assertIs(result["target_json_exists"], False)
        self.assertIn("could not be parsed", result["message"])
        self.assertGreater(len(result["user_targets"]), 0)

    # -- the section overview ----------------------------------------------

    def test_sections_merge_by_name_and_report_which_sources_they_came_from(self):
        result = self.run_list_targets()
        self.assertEqual(
            [entry["name"] for entry in result["sections"]],
            ["animal", "arms", "custom", "measure", "nose"])
        # "arms" is in target.json and is also a user directory. MPFB merges the
        # two, so this is one section from both sources rather than two entries
        # a caller could not tell apart when asking for one.
        arms = self.section_entry(result, "arms")
        self.assertEqual(arms["source"], "both")
        self.assertEqual(arms["label"], "Arms")
        self.assertEqual(arms["category_count"], 2)
        self.assertEqual(arms["target_count"], 3)

        nose = self.section_entry(result, "nose")
        self.assertEqual(nose["source"], "system")
        self.assertEqual(nose["category_count"], 1)
        self.assertEqual(nose["target_count"], 0)

        animal = self.section_entry(result, "animal")
        self.assertEqual(animal["source"], "user")
        self.assertEqual(animal["category_count"], 0)
        self.assertEqual(animal["target_count"], 2)
        # No index label to take, so the name stands in for one.
        self.assertEqual(animal["label"], "animal")

    def test_a_section_with_no_categories_is_still_reported(self):
        # "measure" is real: it is in the index, has no categories, and has no
        # directory. Dropping it would make the index look smaller than it is.
        result = self.run_list_targets()
        measure = self.section_entry(result, "measure")
        self.assertEqual(measure["source"], "system")
        self.assertEqual(measure["category_count"], 0)
        self.assertEqual(measure["target_count"], 0)

    def test_the_overview_is_present_regardless_of_the_section_argument(self):
        for section in (None, "arms", "animal"):
            with self.subTest(section=section):
                result = self.run_list_targets(section=section)
                self.assertEqual(len(result["sections"]), 5)

    # -- section contents ---------------------------------------------------

    def test_a_system_section_returns_its_categories_with_their_opposites(self):
        result = self.run_list_targets(section="arms")
        self.assertEqual(
            [category["name"] for category in result["categories"]],
            ["lowerarm-scale-depth-decr-incr", "upperarm-fat-decr-incr"])
        left_and_right = result["categories"][0]
        self.assertIs(left_and_right["has_left_and_right"], True)
        self.assertEqual(
            left_and_right["opposites"]["positive-left"], "l-lowerarm-scale-depth-incr")
        self.assertEqual(sorted(left_and_right["targets"]), [
            "l-lowerarm-scale-depth-decr", "l-lowerarm-scale-depth-incr",
            "r-lowerarm-scale-depth-decr", "r-lowerarm-scale-depth-incr"])

    def test_a_merged_section_returns_its_categories_and_its_user_targets(self):
        result = self.run_list_targets(section="arms")
        self.assertEqual(len(result["categories"]), 2)
        self.assertEqual(
            sorted(entry["name"] for entry in result["user_targets"]),
            ["elvs_arm_bulk", "elvs_arm_gz", "elvs_arm_slim"])

    def test_a_user_only_section_has_no_categories_rather_than_an_empty_list(self):
        # null and [] are different claims: "this section has no bundled
        # categories" versus "none of its categories matched".
        result = self.run_list_targets(section="animal")
        self.assertIsNone(result["categories"])
        self.assertEqual(
            sorted(entry["name"] for entry in result["user_targets"]),
            ["cat_ears", _LONG_NAME])

    def test_no_section_means_no_categories_and_every_user_target(self):
        result = self.run_list_targets()
        self.assertIsNone(result["categories"])
        self.assertEqual(len(result["user_targets"]), 8)

    def test_section_matching_is_case_insensitive_and_resolves_to_mpfbs_spelling(self):
        result = self.run_list_targets(section="ARMS")
        self.assertIs(result["section_recognized"], True)
        self.assertEqual(len(result["categories"]), 2)

    def test_a_misspelled_section_is_not_the_same_answer_as_an_empty_one(self):
        misspelled = self.run_list_targets(section="armz")
        self.assertIs(misspelled["section_recognized"], False)
        self.assertEqual(misspelled["requested_section"], "armz")
        self.assertIn("armz", misspelled["message"])
        self.assertIn("arms", misspelled["known_sections"])

        empty = self.run_list_targets(section="measure")
        self.assertIs(empty["section_recognized"], True)
        self.assertEqual(empty["categories"], [])
        self.assertEqual(empty["user_targets"], [])

    # -- user targets and their names ---------------------------------------

    def test_every_user_target_is_found_and_nothing_else_is(self):
        result = self.run_list_targets()
        self.assertEqual(
            sorted(entry["name"] for entry in result["user_targets"]),
            ["cat_ears", "closed_eyes", "dual_reachable", "elvs_arm_bulk",
             "elvs_arm_gz", "elvs_arm_slim", "vwide", _LONG_NAME])
        # A file that is not a target must not be listed, however it got there.
        self.assertNotIn("not_a_target", [
            entry["name"] for entry in result["user_targets"]])

    def test_a_target_reachable_by_both_scans_is_listed_once(self):
        # get_asset_roots("targets/custom") and the rglob of <user data>/targets
        # both find it; reported twice it would inflate every count.
        result = self.run_list_targets()
        names = [entry["name"] for entry in result["user_targets"]]
        self.assertEqual(names.count("dual_reachable"), 1)

    def test_the_shapekey_name_is_taken_from_mpfb_and_differs_for_a_long_name(self):
        result = self.run_list_targets(section="animal")
        short = self.target_entry(result, "cat_ears")
        self.assertEqual(short["shapekey_name"], "cat_ears")
        # Over 60 characters, so MPFB encodes it - and a caller using `name`
        # here would silently address nothing.
        long_target = self.target_entry(result, _LONG_NAME)
        self.assertNotEqual(long_target["shapekey_name"], long_target["name"])
        self.assertEqual(
            long_target["shapekey_name"],
            "$yn-$fe-$av-$ca-$un-$pr-$wg-$hg-experiment")

    def test_the_shapekey_name_is_never_derived_locally(self):
        self.run_list_targets()
        # Called once per listed target, always with macrodetail=False stated
        # rather than left to the path sniff - macro details are out of scope.
        self.assertEqual(len(StubTargetService.calls), 8)
        for _filename, macrodetail, _encode in StubTargetService.calls:
            self.assertIs(macrodetail, False)

    def test_file_type_distinguishes_the_two_extensions(self):
        result = self.run_list_targets()
        self.assertEqual(self.target_entry(result, "elvs_arm_bulk")["file_type"], "target")
        self.assertEqual(self.target_entry(result, "elvs_arm_gz")["file_type"], "target.gz")
        self.assertEqual(self.target_entry(result, "vwide")["file_type"], "target.gz")

    def test_a_gzipped_target_under_user_targets_is_reported_as_invisible_to_mpfbs_ui(self):
        # MPFB's scan of <user data>/targets/<section>/ matches only *.target,
        # so this file is on disk and loadable but absent from its panels. The
        # tool reports it, and says which one MPFB will show.
        result = self.run_list_targets(section="arms")
        self.assertIs(self.target_entry(result, "elvs_arm_gz")["listed_in_mpfb_ui"], False)
        self.assertIs(self.target_entry(result, "elvs_arm_bulk")["listed_in_mpfb_ui"], True)

    def test_a_gzipped_target_in_the_custom_section_is_visible_to_mpfbs_ui(self):
        # The asymmetry is the point: MPFB's custom scan matches both
        # extensions, so the flag is true throughout that section.
        result = self.run_list_targets(section="custom")
        self.assertIs(self.target_entry(result, "vwide")["listed_in_mpfb_ui"], True)
        self.assertEqual(self.target_entry(result, "vwide")["file_type"], "target.gz")

    def test_every_path_is_a_string_rather_than_a_pathlib_path(self):
        # find_asset_files_matching_pattern() hands back pathlib.Path objects,
        # and one of those reaching the response fails strict_json and takes the
        # whole answer down.
        result = self.run_list_targets()
        for entry in result["user_targets"]:
            self.assertIsInstance(entry["path"], str)
        for directory in result["user_target_dirs"]:
            self.assertIsInstance(directory, str)
        json.dumps(result)

    def test_the_scanned_directories_are_reported(self):
        result = self.run_list_targets()
        self.assertEqual(sorted(result["user_target_dirs"]), sorted([
            self.user_custom,
            os.path.join(self.user_targets, "custom"),
            self.user_targets,
        ]))

    # -- what the index leaves out ------------------------------------------

    def test_unindexed_bundled_directories_are_diffed_not_hardcoded(self):
        result = self.run_list_targets()
        self.assertEqual(
            [(entry["name"], entry["target_count"])
             for entry in result["unindexed_system_target_dirs"]],
            [("asym", 3), ("expression", 2)])
        self.assertEqual(
            result["unindexed_system_target_dirs"][0]["path"],
            os.path.join(self.system_targets, "asym"))

    def test_a_new_unindexed_directory_is_picked_up_by_the_diff(self):
        # Hardcoding asym and expression would pass every test above and drift
        # the moment MPFB adds a directory.
        _touch(os.path.join(self.system_targets, "wings", "wing-span-incr.target.gz"))
        result = self.run_list_targets()
        self.assertIn(
            "wings", [entry["name"] for entry in result["unindexed_system_target_dirs"]])

    def test_macrodetails_is_excluded_and_a_directory_without_targets_drops_out(self):
        result = self.run_list_targets()
        names = [entry["name"] for entry in result["unindexed_system_target_dirs"]]
        # Out of scope: driven by basemesh attributes rather than by loading a
        # target file.
        self.assertNotIn("macrodetails", names)
        # Holds a .png and nothing else, so its count is zero.
        self.assertNotIn("_images", names)

    def test_an_indexed_directory_is_never_reported_as_unindexed(self):
        result = self.run_list_targets()
        names = [entry["name"] for entry in result["unindexed_system_target_dirs"]]
        self.assertNotIn("arms", names)
        self.assertNotIn("nose", names)

    # -- filtering ----------------------------------------------------------

    def test_name_contains_filters_user_targets_case_insensitively(self):
        result = self.run_list_targets(name_contains="ELVS_ARM")
        self.assertEqual(
            sorted(entry["name"] for entry in result["user_targets"]),
            ["elvs_arm_bulk", "elvs_arm_gz", "elvs_arm_slim"])
        self.assertEqual(result["total_count"], 3)

    def test_name_contains_also_matches_the_shapekey_name(self):
        # The encoded name is what a caller would have seen from an earlier
        # call, so searching for it has to work.
        result = self.run_list_targets(name_contains="$yn-$fe")
        self.assertEqual([entry["name"] for entry in result["user_targets"]], [_LONG_NAME])

    def test_name_contains_filters_categories_by_name_and_by_target_name(self):
        by_name = self.run_list_targets(section="arms", name_contains="upperarm")
        self.assertEqual(
            [category["name"] for category in by_name["categories"]],
            ["upperarm-fat-decr-incr"])
        # A caller who knows a target name but not its category should still
        # find the category that sets it.
        by_target = self.run_list_targets(
            section="arms", name_contains="l-lowerarm-scale-depth-incr")
        self.assertEqual(
            [category["name"] for category in by_target["categories"]],
            ["lowerarm-scale-depth-decr-incr"])

    def test_a_filter_matching_nothing_is_an_empty_list_not_a_failure(self):
        result = self.run_list_targets(name_contains="nothing-is-called-this")
        self.assertEqual(result["user_targets"], [])
        self.assertEqual(result["total_count"], 0)
        self.assertIs(result["truncated"], False)
        # The overview still describes the whole install, so the caller can see
        # what it filtered out of.
        self.assertEqual(len(result["sections"]), 5)

    # -- paging -------------------------------------------------------------

    def test_pages_concatenate_to_the_unpaged_listing_without_skips_or_repeats(self):
        whole = self.run_list_targets()["user_targets"]
        paged = []
        for offset in (0, 3, 6):
            paged.extend(self.run_list_targets(limit=3, offset=offset)["user_targets"])
        self.assertEqual(paged, whole)

    def test_ordering_is_deterministic_across_calls(self):
        first = [entry["path"] for entry in self.run_list_targets()["user_targets"]]
        second = [entry["path"] for entry in self.run_list_targets()["user_targets"]]
        self.assertEqual(first, second)
        # Sorted by section, then name: an rglob's own order is
        # filesystem-dependent and would make two pages skip and repeat.
        self.assertEqual(
            [(entry["section"], entry["name"])
             for entry in self.run_list_targets()["user_targets"]],
            sorted((entry["section"], entry["name"])
                   for entry in self.run_list_targets()["user_targets"]))

    def test_total_count_and_truncated_describe_the_matched_set_not_the_page(self):
        result = self.run_list_targets(limit=2)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total_count"], 8)
        self.assertIs(result["truncated"], True)
        self.assertEqual(result["offset"], 0)
        self.assertEqual(result["limit"], 2)
        self.assertIn("not the whole list", result["message"])

    def test_truncated_is_present_and_false_on_a_complete_answer(self):
        result = self.run_list_targets()
        self.assertIn("truncated", result)
        self.assertIs(result["truncated"], False)

    def test_categories_are_paged_when_a_system_section_was_asked_for(self):
        result = self.run_list_targets(section="arms", limit=1)
        self.assertEqual(len(result["categories"]), 1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["total_count"], 2)
        self.assertIs(result["truncated"], True)
        # The user targets of a merged section are small by construction and
        # come back whole beside the paged categories.
        self.assertEqual(len(result["user_targets"]), 3)

    def test_an_offset_past_the_end_answers_rather_than_fails(self):
        result = self.run_list_targets(offset=500)
        self.assertEqual(result["user_targets"], [])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["total_count"], 8)
        self.assertIs(result["truncated"], True)


if __name__ == "__main__":
    unittest.main()
