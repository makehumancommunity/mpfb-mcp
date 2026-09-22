# SPDX-License-Identifier: GPL-3.0-or-later

"""
``mpfb_create_human_from_preset``: the overrides, the settings dict, and a round trip.

Three layers since FR 032 migrated it: the wrapper with ``send_code`` mocked on
the seam, the **bridge path** against ``tests/fake_bridge.py``, and the payload
against the stubs - the last **frozen**, since it is half of what FR 032's live
comparison compares.

The payload test that matters most is
``test_every_key_mpfb_subscripts_is_in_the_settings_dict``, and what makes it
mean anything is in the stub rather than here: ``StubHumanService
.deserialize_from_dict()`` reads its eight settings keys with ``[]`` exactly as
MPFB does, so a payload that assembled a settings dict from literals and forgot
one really does raise ``KeyError`` in this suite. A stub that tolerated a partial
dict would let the suite pass on precisely the bug the payload builds from
``get_default_deserialization_settings()`` to avoid.

The last class is a **round trip**: save a stub character, load what was
written, compare. Both ends are stubs and neither is MPFB, so it establishes
nothing about the character MPFB would build - but it is the only place the two
payloads' assumptions about the same JSON are checked against each other rather
than each against a fixture of its own.
``bridge/test/tests/ppp_mutating/create_human_from_preset_test.py`` now does the
same round trip against a real MPFB, which is where the claim about the
*character* lives.

Run with::

    python -m unittest tests.test_create_human_from_preset -v
"""

from __future__ import annotations

__all__ = ()

import unittest
from unittest import mock

from mpfbmcp import backend
from mpfbmcp.tools import create_human_from_preset

from tests import fake_bridge
from tests.blender_stubs import PresetTestCase, StubHumanService
from tests import generated_path


# These tests are about the **generated path**: they mock `backend.send_code`
# and assert about the program that reached it. FR 032 made the bridge the
# default, so saying so is now necessary rather than implied.
# See tests/generated_path.py.
setUpModule = generated_path.pin
tearDownModule = generated_path.unpin


class CreateHumanFromPresetToolTests(unittest.TestCase):
    """The wrapper, with ``send_code`` mocked."""

    def setUp(self) -> None:
        class Recorder:
            def tool(self, **_kwargs):
                def decorate(function):
                    self.function = function
                    return function
                return decorate

        self.recorder = Recorder()
        create_human_from_preset.register(self.recorder)
        self.call = self.recorder.function

    def _run(self, **arguments):
        arguments.setdefault("name", "alice")
        with mock.patch("mpfbmcp.backend.send_code") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            self.assertEqual(send.call_count, 1)
            return send.call_args[0][0]

    def _refused(self, **arguments):
        arguments.setdefault("name", "alice")
        with mock.patch("mpfbmcp.backend.send_code") as send:
            with self.assertRaises(ValueError) as raised:
                self.call(**arguments)
            self.assertEqual(send.call_count, 0)
        return str(raised.exception)

    def test_the_name_is_held_to_the_same_rule_as_the_saving_tool(self) -> None:
        # Same whitelist, same module. A name that could be written must be a
        # name that can be looked up, and vice versa.
        for name in ("..", "../escape", "a/b", ".hidden", "", "has space", "x" * 65, 3):
            with self.subTest(name=name):
                self._refused(name=name)

    def test_every_override_defaults_to_null(self) -> None:
        # "Not mentioned" and "set to the default" are different requests, and
        # null is how the payload is told which one it got.
        program = self._run()
        for argument in ("override_rig", "override_skin_model", "override_clothes_model",
                         "override_eyes_model", "load_clothes", "scale",
                         "material_instances"):
            with self.subTest(argument=argument):
                self.assertIn('"{}": null'.format(argument), program)

    def test_an_override_reaches_the_program(self) -> None:
        self.assertIn('"override_rig": "NONE"', self._run(override_rig="NONE"))
        self.assertIn('"load_clothes": false', self._run(load_clothes=False))
        self.assertIn('"scale": 1.0', self._run(scale=1.0))
        self.assertIn('"material_instances": "NEVER"',
                      self._run(material_instances="NEVER"))

    def test_an_explicitly_empty_override_is_not_an_omission(self) -> None:
        for argument in ("override_rig", "override_skin_model", "override_clothes_model",
                         "override_eyes_model", "material_instances"):
            with self.subTest(argument=argument):
                self._refused(**{argument: "   "})

    def test_load_clothes_must_be_a_real_bool(self) -> None:
        # "false" is a true value, and would load the garments it asked to skip.
        for value in ("false", 1, 0, "no"):
            with self.subTest(load_clothes=value):
                self._refused(load_clothes=value)

    def test_scale_is_range_checked_rather_than_vocabulary_checked(self) -> None:
        # An ordinary "validate structured input" case: any positive number is
        # accepted and MPFB's own three are named in the message.
        for value in (0.1, 1.0, 10.0, 2):
            with self.subTest(scale=value):
                self._run(scale=value)
        for value in (0.0, -1.0, "0.1", True):
            with self.subTest(scale=value):
                self._refused(scale=value)

    def test_the_program_carries_both_fragments(self) -> None:
        program = self._run()
        self.assertIn("preset_files.py", program)
        self.assertIn("performed.py", program)


class CreateHumanFromPresetOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the settings dict, the unresolved assets, and what a mid-way failure left behind - is checked against a real MPFB
    in ``bridge/test/tests/ppp_mutating/create_human_from_preset_test.py``.
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
        create_human_from_preset.register(recorder)
        self.call = recorder.function
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "create_human_from_preset": fake_bridge.ok_envelope("create_human_from_preset", {"found": True, "created": True, "performed": True}),
        })

    def test_the_tool_sends_the_create_human_from_preset_command(self) -> None:
        self.call(name="alice")

        self.assertEqual(self.bridge.commands()[-1], "create_human_from_preset")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["name"], "alice")
        # Every override defaults to null, which is "use what the preset says"
        # rather than a value - and that has to survive the transport.
        for key in ("override_rig", "override_skin_model", "override_clothes_model",
                    "override_eyes_model", "load_clothes", "scale", "material_instances"):
            self.assertIsNone(params[key], "{} should default to null".format(key))

    def test_the_shared_fragment_does_not_reach_the_bridge(self) -> None:
        self.call(name="alice")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("preset_files", str(request))

    def test_the_name_rule_is_the_same_rule_the_saving_tool_uses(self) -> None:
        # If these two ever disagreed, a preset could be written under a name
        # that cannot be loaded back - which is the worst shape this pair could
        # take, and why the rule lives in one module.
        for name in ("../escape", "with space", "", "a/b"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.call(name=name)

        self.assertEqual(self.bridge.requests, [])

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(name="alice", load_clothes="false")

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="create_human_from_preset", state="absent"))

        response = self.call(name="alice")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class CreateHumanFromPresetPayloadTests(PresetTestCase):
    """The assembled program against a real config directory and asset library."""

    def run_load(self, name="alice", context_mode="OBJECT", **overrides):
        params = dict(
            name=name, override_rig=None, override_skin_model=None,
            override_clothes_model=None, override_eyes_model=None,
            load_clothes=None, scale=None, material_instances=None)
        params.update(overrides)
        return self.run_payload(
            "create_human_from_preset.py", params,
            scene_objects=(), shared=["preset_files.py", "performed.py"],
            context_mode=context_mode)

    # -- what is built ----------------------------------------------------

    def test_a_character_is_created_and_named_after_the_preset(self) -> None:
        result = self.run_load()
        self.assertTrue(result["created"])
        self.assertTrue(result["performed"])
        self.assertEqual(result["basemesh_name"], "alice.body")
        self.assertEqual(result["objects_created"], ["alice.body"])
        self.assertEqual(result["path"], self.saved_presets["alice"])

    def test_the_selection_it_leaves_behind_is_reported(self) -> None:
        # There is no prior state to restore to: deserialization activates what
        # it creates. Same exception mpfb_generate_rigify_rig has.
        result = self.run_load()
        self.assertEqual(result["active_object_after"], "alice.body")

    def test_a_preset_carrying_assets_reports_what_was_equipped(self) -> None:
        self.write_preset("dressed", self.preset_contents(
            clothes=["fedora/fedora.mhclo"], hair="ponytail/ponytail.mhclo"))
        result = self.run_load(name="dressed")
        kinds = sorted(entry["kind"] for entry in result["equipped_assets"])
        self.assertEqual(kinds, ["clothes", "hair"])
        self.assertEqual(result["unresolved_assets"], [])

    # -- refusals ---------------------------------------------------------

    def test_a_missing_preset_names_the_ones_that_exist(self) -> None:
        # A misspelled name is the likeliest failure, so the refusal ends the
        # guessing rather than only reporting it.
        result = self.run_load(name="alicce")
        self.assertFalse(result["found"])
        self.assertFalse(result["created"])
        self.assertEqual(result["blocked_by"], "preset_not_found")
        self.assertIn("alice", result["available_presets"])
        self.assertEqual(result["available_preset_count"], 3)

    def test_the_suggestions_come_from_the_directory_not_from_mpfbs_cache(self) -> None:
        # A preset written moments ago in another Blender is offered here; the
        # cache would not have it.
        self.run_load()
        self.write_preset("carol")
        self.assertIn("carol", self.run_load(name="nope")["available_presets"])

    def test_an_unreadable_preset_is_an_answer(self) -> None:
        path = self.write_preset("broken")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")
        result = self.run_load(name="broken")
        self.assertEqual(result["blocked_by"], "preset_unreadable")
        self.assertTrue(result["file"]["exists"])

    def test_edit_mode_is_a_precondition_rather_than_a_traceback(self) -> None:
        result = self.run_load(context_mode="EDIT_MESH")
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertEqual(result["objects_created"], [])

    def test_an_unknown_material_instances_value_is_refused_before_anything_is_built(self):
        # _set_skin() tests this with substring matches, so an unrecognised one
        # would silently mean NEVER rather than failing.
        result = self.run_load(material_instances="SOMETIMES")
        self.assertEqual(result["blocked_by"], "unknown_material_instances")
        self.assertEqual(result["known_material_instances"],
                         ["NEVER", "ENHANCED", "ENHANCEDMS"])
        self.assertEqual(result["objects_created"], [])

    def test_a_missing_config_directory_is_an_answer(self) -> None:
        import shutil
        shutil.rmtree(self.config_dir)
        self.assertEqual(self.run_load()["blocked_by"], "config_dir_missing")

    def test_an_incomplete_settings_default_is_refused_rather_than_risked(self) -> None:
        # A version mismatch between MPFB and this tool. Loading would raise a
        # KeyError from inside MPFB with a character half built.
        original = StubHumanService.get_default_deserialization_settings

        def partial():
            settings = original()
            del settings["subdiv_levels"]
            return settings

        StubHumanService.get_default_deserialization_settings = staticmethod(partial)
        self.addCleanup(setattr, StubHumanService,
                        "get_default_deserialization_settings", original)
        result = self.run_load()
        self.assertEqual(result["blocked_by"], "settings_incomplete")
        self.assertEqual(result["missing_settings"], ["subdiv_levels"])
        self.assertEqual(result["objects_created"], [])

    # -- the settings dict ------------------------------------------------

    def test_every_key_mpfb_subscripts_is_in_the_settings_dict(self) -> None:
        # The one that matters. The stub subscripts all eight, so a payload that
        # built the dict from literals and forgot one raises here.
        self.run_load()
        settings = StubHumanService.deserialize_calls[0]["settings"]
        for key in ("mask_helpers", "detailed_helpers", "extra_vertex_groups",
                    "feet_on_ground", "scale", "subdiv_levels", "load_clothes",
                    "material_instances"):
            with self.subTest(key=key):
                self.assertIn(key, settings)

    def test_the_two_keys_mpfbs_defaults_omit_are_added(self) -> None:
        # override_clothes_model and override_eyes_model are honoured by
        # deserialize_from_dict() and passed by MPFB's own panel, and are not in
        # get_default_deserialization_settings(). The vocabulary is wider than
        # the defaults.
        defaults = StubHumanService.get_default_deserialization_settings()
        self.assertNotIn("override_clothes_model", defaults)
        self.assertNotIn("override_eyes_model", defaults)
        self.run_load()
        settings = StubHumanService.deserialize_calls[0]["settings"]
        self.assertEqual(settings["override_clothes_model"], "PRESET")
        self.assertEqual(settings["override_eyes_model"], "PRESET")

    def test_an_omitted_override_leaves_mpfbs_preset_sentinel_in_place(self) -> None:
        self.run_load()
        settings = StubHumanService.deserialize_calls[0]["settings"]
        self.assertEqual(settings["override_rig"], "PRESET")
        self.assertEqual(settings["override_skin_model"], "PRESET")
        self.assertEqual(settings["scale"], 0.1)
        self.assertIs(settings["load_clothes"], True)

    def test_each_override_reaches_the_settings_dict(self) -> None:
        self.run_load(override_rig="NONE", override_skin_model="ENHANCED",
                      override_clothes_model="GAMEENGINE",
                      override_eyes_model="PROCEDURAL_EYES",
                      load_clothes=False, scale=1.0, material_instances="ENHANCEDMS")
        settings = StubHumanService.deserialize_calls[0]["settings"]
        self.assertEqual(settings["override_rig"], "NONE")
        self.assertEqual(settings["override_skin_model"], "ENHANCED")
        self.assertEqual(settings["override_clothes_model"], "GAMEENGINE")
        self.assertEqual(settings["override_eyes_model"], "PROCEDURAL_EYES")
        self.assertIs(settings["load_clothes"], False)
        self.assertEqual(settings["scale"], 1.0)
        self.assertEqual(settings["material_instances"], "ENHANCEDMS")

    def test_material_instances_follows_mpfbs_panel_not_its_service(self) -> None:
        # The service default is NEVER and the panel the user actually sees
        # defaults to ENHANCED. A character loaded here should be the character
        # that panel would have produced - and both values come back.
        result = self.run_load()
        self.assertIsNone(result["material_instances_requested"])
        self.assertEqual(result["material_instances_used"], "ENHANCED")
        self.assertEqual(result["material_instances_service_default"], "NEVER")
        self.assertEqual(
            StubHumanService.deserialize_calls[0]["settings"]["material_instances"],
            "ENHANCED")

    # -- what the preset held --------------------------------------------

    def test_each_override_is_reported_beside_the_value_the_preset_held(self) -> None:
        self.write_preset("rigged", self.preset_contents(rig="default"))
        result = self.run_load(name="rigged", override_rig="NONE")
        entry = result["overrides"]["override_rig"]
        self.assertEqual(entry["requested"], "NONE")
        self.assertEqual(entry["preset_value"], "default")
        self.assertEqual(entry["used"], "NONE")
        self.assertIsNone(result["rig_object_name"])

    def test_the_presets_own_rig_is_added_when_nothing_overrides_it(self) -> None:
        self.write_preset("rigged", self.preset_contents(rig="default"))
        result = self.run_load(name="rigged")
        self.assertEqual(result["rig_object_name"], "rigged")
        self.assertEqual(result["rig_identified_as"], "default")

    def test_a_rigify_preset_says_the_rig_is_only_a_metarig(self) -> None:
        self.write_preset("meta", self.preset_contents(rig="rigify.human"))
        result = self.run_load(name="meta")
        self.assertIn("meta", result["message"])
        self.assertIn("mpfb_generate_rigify_rig", result["message"])

    # -- assets MPFB drops silently ---------------------------------------

    def test_an_asset_the_preset_names_and_this_blender_lacks_is_reported(self) -> None:
        # MPFB logs a warning and carries on, so the character comes back
        # missing its hair with nothing in the scene to say why.
        self.write_preset("missing", self.preset_contents(
            hair="notinstalled/notinstalled.mhclo", clothes=["fedora/fedora.mhclo"]))
        result = self.run_load(name="missing")
        self.assertTrue(result["created"])
        self.assertEqual(len(result["unresolved_assets"]), 1)
        unresolved = result["unresolved_assets"][0]
        self.assertEqual(unresolved["kind"], "hair")
        self.assertEqual(unresolved["asset_subdir"], "hair")
        self.assertIsNone(unresolved["resolved_path"])
        self.assertIn("not installed here", result["message"])

    def test_a_skipped_garment_is_not_an_unresolved_one(self) -> None:
        # "You asked not to load the clothes" and "the clothes are not
        # installed" have to stay distinguishable in one answer.
        self.write_preset("dressed", self.preset_contents(clothes=["fedora/fedora.mhclo"]))
        result = self.run_load(name="dressed", load_clothes=False)
        self.assertEqual(result["unresolved_assets"], [])
        self.assertEqual([entry["kind"] for entry in result["equipped_assets"]], [])
        self.assertIn("load_clothes was false", result["message"])

    # -- the failure that is not a no-op ----------------------------------

    def test_a_failure_part_way_through_names_what_was_left_behind(self) -> None:
        # A character is built in stages, so a rig MPFB cannot find raises after
        # create_human() has already run. There is no undo across the socket;
        # the caller gets the names instead.
        self.write_preset("orphan", self.preset_contents(rig="no_such_rig"))
        result = self.run_load(name="orphan")
        self.assertFalse(result["created"])
        self.assertFalse(result["performed"])
        self.assertEqual(result["blocked_by"], "deserialization_failed")
        self.assertEqual(result["objects_created"], ["orphan.body"])
        self.assertEqual(result["preset_rig"], "no_such_rig")
        self.assertIn("mpfb_list_rigs", result["message"])
        self.assertIn("override_rig", result["message"])

    def test_the_failure_answer_still_says_what_is_active(self) -> None:
        StubHumanService.deserialize_raises = RuntimeError("boom")
        result = self.run_load()
        self.assertEqual(result["blocked_by"], "deserialization_failed")
        self.assertIn("boom", result["message"])
        self.assertEqual(result["objects_created"], ["alice.body"])


class PresetRoundTripTests(PresetTestCase):
    """Save a character, load what was written, compare.

    Both ends are stubs, so this says nothing about the character real MPFB
    would build. What it does say is that the two payloads agree about the same
    JSON - which neither payload's own tests can establish, because each of
    those builds its own fixture at one end and asserts against it.
    """

    def save(self, name, **kwargs):
        return self.run_payload(
            "save_preset.py", dict(name=name, subject=None, overwrite=False),
            scene_objects=self.objects, active=self.basemesh,
            shared=["preset_files.py", "performed.py"], **kwargs)

    def load(self, name, **overrides):
        params = dict(
            name=name, override_rig=None, override_skin_model=None,
            override_clothes_model=None, override_eyes_model=None,
            load_clothes=None, scale=None, material_instances=None)
        params.update(overrides)
        return self.run_payload(
            "create_human_from_preset.py", params, scene_objects=(),
            shared=["preset_files.py", "performed.py"])

    def test_a_phenotype_survives_the_round_trip(self) -> None:
        self.build_character(macro_details=dict(gender=0.8, age=0.2))
        saved = self.save("trip")
        self.assertTrue(saved["saved"])
        loaded = self.load("trip")
        self.assertTrue(loaded["created"])
        phenotype = StubHumanService.deserialize_calls[0]["human_info"]["phenotype"]
        self.assertEqual(phenotype["gender"], 0.8)
        self.assertEqual(phenotype["age"], 0.2)

    def test_a_rig_and_a_garment_survive_the_round_trip(self) -> None:
        self.build_character(rig=True, dressed=True, rig_type="default")
        saved = self.save("trip")
        self.assertEqual(saved["contents"]["rig"], "default")
        self.assertEqual(saved["contents"]["clothes"], ["fedora/fedora.mhclo"])

        loaded = self.load("trip")
        self.assertEqual(loaded["rig_identified_as"], "default")
        self.assertEqual(
            [entry["asset_source"] for entry in loaded["equipped_assets"]],
            ["fedora/fedora.mhclo"])
        self.assertEqual(loaded["unresolved_assets"], [])

    def test_the_name_the_save_reports_is_the_name_the_load_takes(self) -> None:
        # The whole point of one shared rule: a preset written under a name must
        # be loadable under it, with no transformation in between.
        self.build_character()
        saved = self.save("round-trip.v2")
        self.assertTrue(saved["saved"])
        loaded = self.load(saved["name"])
        self.assertTrue(loaded["created"])
        self.assertEqual(loaded["path"], saved["path"])

    def test_a_saved_preset_is_listed_and_addressable(self) -> None:
        self.build_character()
        self.save("trip")
        listed = self.run_payload(
            "list_presets.py", dict(refresh=True), shared=["preset_files.py"])
        entry = [e for e in listed["presets"] if e["name"] == "trip"][0]
        self.assertTrue(entry["addressable"])
        self.assertTrue(self.load(entry["name"])["created"])


if __name__ == "__main__":
    unittest.main()
