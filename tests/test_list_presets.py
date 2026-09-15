# SPDX-License-Identifier: GPL-3.0-or-later

"""
``mpfb_list_presets``: the wrapper, and the payload over a real config directory.

A ``tempfile`` directory rather than a mocked filesystem, in the idiom
``test_list_rigs.py`` established for a payload whose job is ``os.listdir``: the
three fields worth having here - ``size_bytes``, ``modified`` and ``exists`` -
come from ``os.stat`` and from nowhere else, so mocking the filesystem away
would leave nothing under test.

The fixture (``PresetTestCase``) carries what a config directory that has been
used actually holds: presets MPFB's match accepts, three near misses it refuses
for three different reasons, and one preset whose name MPFB accepts and these
tools do not.

Run with::

    python -m unittest tests.test_list_presets -v
"""

from __future__ import annotations

__all__ = ()

import os
import unittest
from unittest import mock

from mpfbmcp.tools import list_presets

from tests.blender_stubs import PresetTestCase, StubHumanService


class ListPresetsToolTests(unittest.TestCase):
    """The wrapper, with ``send_code`` mocked: what is validated before the socket."""

    def setUp(self) -> None:
        self.sent: list = []

        class Recorder:
            def tool(self, **_kwargs):
                def decorate(function):
                    self.function = function
                    return function
                return decorate

        self.recorder = Recorder()
        list_presets.register(self.recorder)
        self.call = self.recorder.function

    def _run(self, **arguments):
        with mock.patch.object(list_presets, "send_code") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            return send.call_args[0][0]

    def test_the_default_call_does_not_refresh(self) -> None:
        self.assertIn('"refresh": false', self._run())

    def test_refresh_reaches_the_program(self) -> None:
        self.assertIn('"refresh": true', self._run(refresh=True))

    def test_a_truthy_non_bool_refresh_is_refused_before_the_socket(self) -> None:
        # "false" is a true value, and would rescan the disk - which is a write
        # to MPFB's own cache, read by MPFB's own panels.
        for value in ("false", "true", 1, 0, None):
            with self.subTest(refresh=value):
                with self.assertRaises(ValueError):
                    self._run(refresh=value)

    def test_the_program_carries_the_shared_fragment(self) -> None:
        # Same rule, same path construction, in all three preset tools.
        self.assertIn("preset_files.py", self._run())


class ListPresetsPayloadTests(PresetTestCase):
    """The assembled program, executed against the stub Blender."""

    def run_list(self, **params):
        arguments = dict(refresh=False)
        arguments.update(params)
        return self.run_payload("list_presets.py", arguments, shared=["preset_files.py"])

    def test_every_preset_in_the_directory_is_listed(self) -> None:
        result = self.run_list()
        self.assertEqual(
            sorted(entry["name"] for entry in result["presets"]),
            sorted(["alice", "bob-2", self.UNADDRESSABLE_PRESET]))
        self.assertEqual(result["count"], 3)

    def test_the_three_near_misses_are_not_listed(self) -> None:
        # human.json has no name between the dots, humans.foo.json has the wrong
        # prefix, human.decoy.json.bak has the wrong suffix. All three are in
        # the directory; none is a preset.
        result = self.run_list()
        names = [entry["name"] for entry in result["presets"]]
        self.assertNotIn("", names)
        self.assertNotIn("foo", names)
        self.assertNotIn("decoy", names)
        self.assertIn("human.json", self.preset_filenames())

    def test_each_entry_carries_the_filesystem_facts(self) -> None:
        # Derived here from os.stat, not recorded anywhere by MPFB.
        entry = [e for e in self.run_list()["presets"] if e["name"] == "alice"][0]
        self.assertEqual(entry["path"], self.saved_presets["alice"])
        self.assertTrue(entry["exists"])
        self.assertEqual(entry["size_bytes"], os.path.getsize(self.saved_presets["alice"]))
        # ISO 8601 carrying an offset, so the age is checkable against a clock.
        self.assertRegex(entry["modified"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

    def test_the_directory_is_reported_whether_or_not_anything_was_found(self) -> None:
        result = self.run_list()
        self.assertEqual(result["config_dir"], self.config_dir)
        self.assertTrue(result["config_dir_exists"])

    def test_an_empty_directory_is_an_answer_rather_than_an_ambiguity(self) -> None:
        for filename in self.preset_filenames():
            os.remove(os.path.join(self.config_dir, filename))
        result = self.run_list(refresh=True)
        self.assertEqual(result["presets"], [])
        self.assertEqual(result["count"], 0)
        # The part that makes the empty list mean something.
        self.assertEqual(result["config_dir"], self.config_dir)
        self.assertTrue(result["config_dir_exists"])
        self.assertIn("No character presets", result["message"])

    def test_a_missing_config_directory_is_reported_and_not_created(self) -> None:
        import shutil
        shutil.rmtree(self.config_dir)
        result = self.run_list()
        self.assertFalse(result["config_dir_exists"])
        self.assertEqual(result["config_dir"], self.config_dir)
        self.assertEqual(result["presets"], [])
        self.assertFalse(os.path.exists(self.config_dir))

    def test_refresh_selects_use_cache_false(self) -> None:
        # The cache is a module global MPFB invalidates only on a save, so a
        # preset written by any other means is invisible until this.
        self.run_list()
        first = list(StubHumanService.existing_presets)
        self.write_preset("carol")
        self.assertEqual(self.run_list()["count"], len(first))
        self.assertIn("carol", [e["name"] for e in self.run_list(refresh=True)["presets"]])

    def test_a_preset_the_cache_does_not_hold_is_named_without_a_refresh(self) -> None:
        # The half of the cache obligation a `refresh` flag cannot discharge: a
        # caller should not have to pass it to find out whether it would help.
        self.run_list()
        self.write_preset("carol")
        result = self.run_list()
        self.assertEqual(result["missing_from_mpfb_list"], ["carol"])
        self.assertFalse(result["refreshed"])
        self.assertIn("not in MPFB's list", result["message"])

    def test_a_refreshed_listing_has_nothing_missing(self) -> None:
        self.run_list()
        self.write_preset("carol")
        result = self.run_list(refresh=True)
        self.assertEqual(result["missing_from_mpfb_list"], [])
        self.assertTrue(result["refreshed"])

    def test_a_name_in_the_cache_whose_file_is_gone_is_reported_as_such(self) -> None:
        self.run_list()
        os.remove(self.saved_presets["alice"])
        entry = [e for e in self.run_list()["presets"] if e["name"] == "alice"][0]
        self.assertFalse(entry["exists"])
        self.assertIsNone(entry["size_bytes"])
        self.assertIsNone(entry["modified"])

    def test_a_preset_the_other_two_tools_would_refuse_is_flagged(self) -> None:
        # MPFB's own panel accepts names these tools will not. The listing is
        # where that disagreement should surface, not the refusal.
        entries = {entry["name"]: entry for entry in self.run_list()["presets"]}
        self.assertTrue(entries["alice"]["addressable"])
        self.assertIsNone(entries["alice"]["not_addressable_reason"])
        unaddressable = entries[self.UNADDRESSABLE_PRESET]
        self.assertFalse(unaddressable["addressable"])
        self.assertIn("' '", unaddressable["not_addressable_reason"])
        self.assertIn("addressable: false", self.run_list()["message"])

    def test_mpfbs_own_list_is_not_edited_in_place(self) -> None:
        # get_list_of_human_presets() hands back the module global itself, and
        # it is the list MPFB's preset dropdown is built from.
        self.run_list()
        self.assertEqual(
            StubHumanService.existing_presets,
            sorted(["alice", "bob-2", self.UNADDRESSABLE_PRESET]))

    def test_no_preset_is_parsed(self) -> None:
        # A preset that is not JSON at all must still be listed: this tool
        # reports files, and the one that reads a preset is the loading tool.
        handle = open(self.saved_presets["alice"], "w", encoding="utf-8")
        handle.write("not json at all")
        handle.close()
        entry = [e for e in self.run_list()["presets"] if e["name"] == "alice"][0]
        self.assertTrue(entry["exists"])

    def test_nothing_is_capped(self) -> None:
        # Deliberately unbounded, so a caller has no `truncated` to check.
        for index in range(60):
            self.write_preset("bulk{:02d}".format(index))
        result = self.run_list(refresh=True)
        self.assertEqual(result["count"], 63)
        self.assertNotIn("truncated", result)


if __name__ == "__main__":
    unittest.main()
