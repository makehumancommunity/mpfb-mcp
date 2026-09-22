# SPDX-License-Identifier: GPL-3.0-or-later

"""
``mpfb_list_presets``, migrated by FR 031 and therefore in three layers rather
than two (see ``tests/test_list_objects.py``, the template).

1. **The wrapper**, with ``send_code`` mocked on the seam: what is validated
   before a transport is chosen, and what goes on the wire.
2. **The bridge path**, against ``tests/fake_bridge.py``. Thin, and it carries
   the claim this tool is the first to make: a tool that names a **shared
   fragment** sends the same request over the bridge as without one, because a
   fragment is a property of how a program is assembled and the bridge
   assembles nothing.
3. **The payload** over a real ``tempfile`` config directory. **Frozen.** It
   stays while the payload stays, because the payload is half of what FR 031's
   live comparison compares, and it is deleted with the payload when the
   generated path is retired.

A ``tempfile`` directory rather than a mocked filesystem, in the idiom
``test_list_rigs.py`` established for a payload whose job is ``os.listdir``: the
three fields worth having here - ``size_bytes``, ``modified`` and ``exists`` -
come from ``os.stat`` and from nowhere else, so mocking the filesystem away
would leave nothing under test. That fixture is **also** what
``bridge/test/tests/jjj_list_presets_test.py`` builds, against MPFB's own
``LocationService`` rather than a stub reporting it, which is where the claims
about what MPFB's list holds are now made.

The share of this module that goes with the payload: 129 of its 294 lines, 44%
- ``ListPresetsPayloadTests`` alone. The fixture it runs against is **not**
counted, because ``PresetTestCase`` lives in ``tests/blender_stubs.py`` and is
shared with the two preset-writing tools that have not migrated; it goes when
they do. That is the shape to expect wherever a fixture straddles the stage
boundary, and it means 44% understates what this tool's migration eventually
removes.

Run with::

    python -m unittest tests.test_list_presets -v
"""

from __future__ import annotations

__all__ = ()

import os
import unittest
from unittest import mock

from mpfbmcp import backend
from mpfbmcp.tools import list_presets

from tests import fake_bridge
from tests.blender_stubs import PresetTestCase, StubHumanService
from tests import generated_path


# These tests are about the **generated path**: they mock `backend.send_code`
# and assert about the program that reached it. FR 032 made the bridge the
# default, so saying so is now necessary rather than implied.
# See tests/generated_path.py.
setUpModule = generated_path.pin
tearDownModule = generated_path.unpin


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
        with mock.patch("mpfbmcp.backend.send_code") as send:
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


class ListPresetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - what MPFB's cached list holds, which files
    its own match accepts, what a rescan gains - is checked against a real MPFB
    in ``bridge/test/tests/jjj_list_presets_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()

        class Recorder:
            def tool(self, **_kwargs):
                def decorate(function):
                    self.function = function
                    return function
                return decorate

        recorder = Recorder()
        list_presets.register(recorder)
        self.call = recorder.function
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_presets": fake_bridge.ok_envelope("list_presets", {"count": 0}),
        })

    def test_the_tool_sends_the_list_presets_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "list_presets")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"refresh": False})

    def test_the_shared_fragment_does_not_reach_the_bridge(self) -> None:
        # The first tool to carry a fragment across the seam. A fragment is a
        # property of how a *program* is assembled; the bridge dispatches a
        # name, and what the fragment modelled is a module it imports. So the
        # request is exactly the parameters, with nothing named `shared` in it.
        self.call(refresh=True)

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(request["params"], {"refresh": True})
        self.assertNotIn("shared", request)
        self.assertNotIn("preset_files", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        # "false" is a true value and would rescan the disk, which is a write to
        # MPFB's own cache. The refusal is the tool's, not the transport's.
        for value in ("false", "true", 1, 0, None):
            with self.subTest(refresh=value):
                with self.assertRaises(ValueError):
                    self.call(refresh=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="list_presets", state="absent"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


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
