# SPDX-License-Identifier: GPL-3.0-or-later

"""
``mpfb_save_preset``: the name rule on this side, and the write on the other.

Two layers, and the first one carries more weight here than in any other tool
module. ``name`` is the only argument in this package that becomes a **path**,
so the whitelist is exercised exhaustively *before* ``send_code`` - a name that
escapes the config directory must never cross the socket at all, and a test that
only checked the payload's copy would be testing the wrong statement.

The second layer runs the assembled program against a real config directory and
a stub character, and asserts the three things a tool that writes a file owes
its caller: that a refusal leaves the existing file byte-identical, that the
absolute path is in every answer, and that what is reported as written is read
back out of the file rather than assembled from the scene.

Run with::

    python -m unittest tests.test_save_preset -v
"""

from __future__ import annotations

__all__ = ()

import json
import os
import unittest
from unittest import mock

from mpfbmcp.tools import save_preset

from tests.blender_stubs import (
    PresetTestCase, StubHumanService, StubObject, StubObjectService)


# Names that must be refused, and the reason each one exists in this list. The
# first four are the ones that would leave the config directory.
REFUSED_NAMES = (
    ("..", "the parent directory"),
    ("../elsewhere", "an escape by path"),
    ("a/b", "a posix separator"),
    ("a\\b", "a windows separator"),
    (".hidden", "a leading dot"),
    (".", "the directory itself"),
    ("", "empty"),
    ("   ", "whitespace only"),
    ("has space", "a space, which MPFB's own panel also refuses"),
    ("x" * 65, "over the length bound"),
    (None, "not a string"),
    (7, "not a string"),
    (True, "not a string"),
)

# ...and names that must be accepted, because every one of them is a real preset
# name seen in a working install's config directory.
ACCEPTED_NAMES = ("alice", "bob-2", "klara-v2", "Girl_test_walkCycle", "anna_v2", "v1.2")


class SavePresetNameValidationTests(unittest.TestCase):
    """Requirement 8, where it lives: before the program is built."""

    def setUp(self) -> None:
        class Recorder:
            def tool(self, **_kwargs):
                def decorate(function):
                    self.function = function
                    return function
                return decorate

        self.recorder = Recorder()
        save_preset.register(self.recorder)
        self.call = self.recorder.function

    def _run(self, **arguments):
        with mock.patch.object(save_preset, "send_code") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            self.assertEqual(send.call_count, 1)
            return send.call_args[0][0]

    def _refused(self, **arguments):
        with mock.patch.object(save_preset, "send_code") as send:
            with self.assertRaises(ValueError) as raised:
                self.call(**arguments)
            # The point of the whole layer: nothing crossed the socket.
            self.assertEqual(send.call_count, 0)
        return str(raised.exception)

    def test_every_dangerous_or_malformed_name_is_refused_before_the_socket(self) -> None:
        for name, why in REFUSED_NAMES:
            with self.subTest(name=name, why=why):
                self._refused(name=name)

    def test_a_refusal_says_what_to_do_instead(self) -> None:
        message = self._refused(name="../escape")
        self.assertIn("mpfb_list_presets", message)
        self.assertIn("human.<name>.json", message)

    def test_a_refusal_names_the_offending_characters(self) -> None:
        # An agent that built the name out of a display name needs to know which
        # character to drop, not that the name was rejected.
        message = self._refused(name="Anna Svensson")
        self.assertIn("' '", message)

    def test_every_name_a_working_install_actually_holds_is_accepted(self) -> None:
        for name in ACCEPTED_NAMES:
            with self.subTest(name=name):
                self.assertIn(json.dumps(name), self._run(name=name))

    def test_a_name_is_not_trimmed_before_it_is_used(self) -> None:
        # A trailing space is a different name, MPFB's filename would carry it,
        # and quietly trimming would save a preset the caller did not ask for.
        # It is refused rather than repaired.
        self._refused(name="alice ")

    def test_overwrite_must_be_a_real_bool(self) -> None:
        for value in ("false", "true", 1, 0, None):
            with self.subTest(overwrite=value):
                self._refused(name="alice", overwrite=value)

    def test_the_default_call_refuses_to_overwrite(self) -> None:
        self.assertIn('"overwrite": false', self._run(name="alice"))

    def test_the_subject_is_optional_and_shape_checked(self) -> None:
        self.assertIn('"subject": null', self._run(name="alice"))
        self.assertIn('"subject": "Human"', self._run(name="alice", subject="Human"))
        self._refused(name="alice", subject="")
        self._refused(name="alice", subject=3)

    def test_the_program_carries_both_fragments(self) -> None:
        program = self._run(name="alice")
        self.assertIn("preset_files.py", program)
        self.assertIn("performed.py", program)


class SavePresetPayloadTests(PresetTestCase):
    """The assembled program against a real directory and a stub character."""

    def run_save(self, name="charlie", subject=None, overwrite=False, objects=None,
                 active=None, context_mode="OBJECT"):
        scene = self.objects if objects is None else objects
        return self.run_payload(
            "save_preset.py",
            dict(name=name, subject=subject, overwrite=overwrite),
            scene_objects=scene,
            active=active if active is not None else (scene[0] if scene else None),
            shared=["preset_files.py", "performed.py"],
            context_mode=context_mode)

    def test_a_clean_save_writes_the_file_and_names_it(self) -> None:
        self.build_character()
        result = self.run_save(active=self.basemesh)
        self.assertTrue(result["saved"])
        self.assertTrue(result["performed"])
        self.assertFalse(result["overwrote"])
        self.assertIsNone(result["previous_file"])
        expected = os.path.join(self.config_dir, "human.charlie.json")
        self.assertEqual(result["path"], expected)
        self.assertTrue(os.path.isfile(expected))
        self.assertEqual(result["size_bytes"], os.path.getsize(expected))
        self.assertEqual(result["basemesh_name"], "Human")

    def test_the_subject_may_be_any_object_in_the_family(self) -> None:
        # A rig, not the basemesh - and the response names the object actually
        # serialized rather than echoing the argument.
        self.build_character(rig=True, dressed=True)
        result = self.run_save(subject=self.shirt.name)
        self.assertTrue(result["saved"])
        self.assertEqual(result["subject_name"], self.shirt.name)
        self.assertEqual(result["subject_resolved_by"], "name")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_the_active_object_is_the_subject_when_none_is_named(self) -> None:
        self.build_character(rig=True)
        result = self.run_save(active=self.rig)
        self.assertEqual(result["subject_resolved_by"], "active")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_a_missing_subject_is_an_answer(self) -> None:
        self.build_character()
        result = self.run_save(subject="Nonexistent")
        self.assertFalse(result["found"])
        self.assertFalse(result["performed"])
        self.assertEqual(result["blocked_by"], "subject_not_found")
        self.assertFalse(os.path.exists(os.path.join(self.config_dir, "human.charlie.json")))

    def test_an_object_with_no_basemesh_relative_is_an_answer(self) -> None:
        stray = StubObject("Cube")
        StubObjectService.register_object(stray)
        result = self.run_save(objects=[stray], active=stray)
        self.assertFalse(result["found"])
        self.assertEqual(result["blocked_by"], "subject_not_found")

    def test_an_existing_preset_is_refused_and_left_byte_identical(self) -> None:
        self.build_character()
        path = self.saved_presets["alice"]
        with open(path, "rb") as handle:
            before = handle.read()
        result = self.run_save(name="alice", active=self.basemesh)
        self.assertFalse(result["saved"])
        self.assertFalse(result["performed"])
        self.assertEqual(result["blocked_by"], "preset_exists")
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), before)
        # The caller cannot see the directory, so the refusal has to carry
        # enough to decide with.
        self.assertEqual(result["path"], path)
        self.assertEqual(result["previous_file"]["size_bytes"], len(before))
        self.assertIsNotNone(result["previous_file"]["modified"])
        self.assertEqual(StubHumanService.serialize_calls, [])

    def test_overwrite_replaces_it_and_reports_what_it_replaced(self) -> None:
        self.build_character()
        path = self.saved_presets["alice"]
        before_size = os.path.getsize(path)
        result = self.run_save(name="alice", overwrite=True, active=self.basemesh)
        self.assertTrue(result["saved"])
        self.assertTrue(result["overwrote"])
        self.assertEqual(result["previous_file"]["size_bytes"], before_size)
        self.assertIn("cannot be restored", result["message"])
        self.assertEqual(self.read_preset("alice")["phenotype"]["gender"], 0.5)

    def test_a_mesh_that_is_not_an_mpfb_character_is_refused(self) -> None:
        # MPFB's own guard, checked here rather than let raise: an imported mesh
        # tagged as a basemesh looks exactly like this.
        imported = StubObject("Imported", object_type="Basemesh", is_human_project=False)
        StubObjectService.register_object(imported)
        result = self.run_save(objects=[imported], active=imported)
        self.assertFalse(result["saved"])
        self.assertEqual(result["blocked_by"], "not_a_human_project")
        self.assertFalse(result["is_human_project"])
        self.assertEqual(StubHumanService.serialize_calls, [])

    def test_an_unidentifiable_rig_is_a_refusal_rather_than_a_valueerror(self) -> None:
        # MPFB raises ValueError("...Custom rigs cannot be serialized.") here,
        # which is both a traceback and a wrong explanation.
        self.build_character(rig=True, rig_type="unknown")
        result = self.run_save(active=self.basemesh)
        self.assertFalse(result["saved"])
        self.assertEqual(result["blocked_by"], "rig_not_identifiable")
        self.assertEqual(result["rig_name"], "Human.rig")
        self.assertEqual(result["rig_identified_as"], "unknown")
        self.assertEqual(StubHumanService.serialize_calls, [])

    def test_mpfbs_other_spelling_of_unknown_is_refused_too(self) -> None:
        # MPFB checks "unkown" as well as "unknown", which suggests the typo is
        # load-bearing somewhere.
        self.build_character(rig=True, rig_type="unkown")
        self.assertEqual(self.run_save(active=self.basemesh)["blocked_by"],
                         "rig_not_identifiable")

    def test_save_clothes_true_is_what_is_passed(self) -> None:
        # Dead in MPFB today - the body never reads it - and passed anyway,
        # because both of MPFB's operators pass it and the day it starts working
        # this tool should keep doing what the panel does.
        self.build_character()
        self.run_save(active=self.basemesh)
        self.assertEqual(StubHumanService.serialize_calls[0]["save_clothes"], True)

    def test_garments_are_saved_whatever_save_clothes_says(self) -> None:
        # The defect itself, asserted rather than described: the stub ignores
        # the flag because MPFB ignores it.
        self.build_character(rig=True, dressed=True)
        result = self.run_save(active=self.basemesh)
        self.assertEqual(result["contents"]["clothes"], ["fedora/fedora.mhclo"])

    def test_the_contents_report_is_read_back_out_of_the_written_file(self) -> None:
        self.build_character(rig=True, proxy=True, dressed=True, rig_type="default")
        result = self.run_save(active=self.basemesh)
        written = self.read_preset("charlie")
        self.assertEqual(result["contents"]["rig"], written["rig"])
        self.assertEqual(result["contents"]["clothes"], written["clothes"])
        self.assertEqual(result["contents"]["proxy"], written["proxy"])
        self.assertEqual(result["contents"]["target_count"], len(written["targets"]))

    def test_a_generated_rigify_rig_is_saved_as_its_metarig_and_says_so(self) -> None:
        # Not the WARNING MPFB's operators emit - the substitution reported as
        # the fact it is, on the call where it happened.
        self.build_character(rig=True, rig_type="rigify_generated.human")
        self.rig.inferred_metarig = "rigify.human"
        result = self.run_save(active=self.basemesh)
        self.assertTrue(result["saved"])
        self.assertEqual(result["rig_identified_as"], "rigify_generated.human")
        self.assertEqual(result["rig_saved_as"], "rigify.human")
        self.assertIn("mpfb_generate_rigify_rig", result["message"])

    def test_a_generated_rig_mpfb_cannot_infer_falls_back_to_human_toes(self) -> None:
        self.build_character(rig=True, rig_type="rigify_generated.something")
        self.rig.inferred_metarig = None
        result = self.run_save(active=self.basemesh)
        self.assertEqual(result["rig_saved_as"], "rigify.human_toes")

    def test_an_ordinary_rig_round_trips_without_a_sentence_about_it(self) -> None:
        self.build_character(rig=True, rig_type="default")
        result = self.run_save(active=self.basemesh)
        self.assertEqual(result["rig_identified_as"], "default")
        self.assertEqual(result["rig_saved_as"], "default")
        self.assertNotIn("mpfb_generate_rigify_rig", result["message"])

    def test_a_save_makes_the_preset_visible_to_the_list_without_a_refresh(self) -> None:
        # serialize_to_json_file() is the one thing that invalidates MPFB's
        # cached list, which is why a preset written *through this tool* needs
        # no refresh and one written any other way does.
        self.build_character()
        self.run_payload("list_presets.py", dict(refresh=False), shared=["preset_files.py"])
        self.run_save(active=self.basemesh)
        listed = self.run_payload(
            "list_presets.py", dict(refresh=False), shared=["preset_files.py"])
        self.assertIn("charlie", [entry["name"] for entry in listed["presets"]])
        self.assertEqual(listed["missing_from_mpfb_list"], [])

    def test_a_missing_config_directory_is_refused_and_not_created(self) -> None:
        import shutil
        self.build_character()
        shutil.rmtree(self.config_dir)
        result = self.run_save(active=self.basemesh)
        self.assertEqual(result["blocked_by"], "config_dir_missing")
        self.assertFalse(os.path.exists(self.config_dir))

    def test_a_name_that_escapes_is_refused_by_the_payload_too(self) -> None:
        # Unreachable through the tool module, which is the point: this is the
        # last statement before a path is assembled, and it is checked there as
        # well as here.
        self.build_character()
        result = self.run_save(name="../escaped", active=self.basemesh)
        self.assertEqual(result["blocked_by"], "invalid_name")
        self.assertIsNone(result["path"])
        self.assertFalse(os.path.exists(
            os.path.join(os.path.dirname(self.config_dir), "human.../escaped.json")))

    def test_a_failure_inside_mpfb_is_reported_rather_than_raised(self) -> None:
        self.build_character()
        original = StubHumanService.serialize_to_json_string

        def explode(basemesh, save_clothes=False):
            raise RuntimeError("something went wrong deep inside")

        StubHumanService.serialize_to_json_string = staticmethod(explode)
        self.addCleanup(setattr, StubHumanService, "serialize_to_json_string", original)
        result = self.run_save(active=self.basemesh)
        self.assertFalse(result["saved"])
        self.assertFalse(result["performed"])
        self.assertEqual(result["blocked_by"], "serialize_failed")
        self.assertIn("something went wrong deep inside", result["message"])

    def test_the_path_is_in_every_answer_refusals_included(self) -> None:
        # A caller cannot see the directory, so "which file was this about" is
        # the first thing they need whatever happened.
        self.build_character()
        for arguments in (dict(name="alice"), dict(name="charlie"),
                          dict(name="charlie", subject="Nonexistent")):
            with self.subTest(**arguments):
                result = self.run_save(active=self.basemesh, **arguments)
                self.assertIn("path", result)
                self.assertIn("config_dir", result)


if __name__ == "__main__":
    unittest.main()
