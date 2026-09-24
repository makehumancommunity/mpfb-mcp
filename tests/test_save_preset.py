# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_save_preset``: the name rule on this side, and the write on the other.

Two layers (see ``tests/test_list_objects.py``, the template), and the first
carries more weight here than in any other tool module. ``name`` is the only
argument in this package that becomes a **path**, so the whitelist is exercised
exhaustively *before* anything is sent - a name that escapes the config
directory must never cross the socket at all, and a test that only checked the
far side's copy would be testing the wrong statement. The second is the
**bridge path** against ``tests/fake_bridge.py``.

The last class in this module is the drift check between the two copies of that
rule, which moved here from ``tests/test_codegen.py`` when FR 033 deleted the
third.

The three things a tool that writes a file owes its caller - that a refusal
leaves the existing file byte-identical, that the absolute path is in every
answer, and that what is reported as written is read back out of the file rather
than assembled from the scene - are checked against a real MPFB in
``bridge/test/tests/ddd_mutating/save_preset_test.py``, which redirects MPFB's
user config directory so that a failing test cannot leave a preset in the
developer's own panel.

Run with::

    python -m unittest tests.test_save_preset -v
"""

from __future__ import annotations

__all__ = ()

import os
import pathlib
import unittest
from unittest import mock

from mpfbmcp import artifact_names
from mpfbmcp.tools import save_preset

from tests import fake_bridge


_BRIDGE_SHARED = pathlib.Path(__file__).resolve().parent.parent / "bridge" / "mpfb_bridge" / "shared"


def _bridge_shared_namespace(name: str) -> dict:
    """One of the bridge's shared modules, executed here rather than imported.

    The bridge is a Blender extension and is outside this package's root
    entirely, so there is nothing to import. Executing the source is enough for
    the rules that are plain Python over plain data, which is what the check
    below is about, and it keeps this module free of ``bpy``.
    """
    namespace: dict = {}
    source = (_BRIDGE_SHARED / name).read_text(encoding="utf-8")
    exec(compile(source, str(_BRIDGE_SHARED / name), "exec"), namespace)  # noqa: S102
    return namespace




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
        """The parameters that reached the wire for one accepted call."""
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args[0][0], "save_preset")
            return send.call_args[0][1]

    def _refused(self, **arguments):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            with self.assertRaises(ValueError) as raised:
                self.call(**arguments)
            # The point of the whole layer: nothing crossed the socket.
            self.assertEqual(send.call_count, 0)
        return str(raised.exception)

    def test_every_dangerous_or_malformed_name_is_refused_before_the_socket(self) -> None:
        for name, why in REFUSED_NAMES:
            with self.subTest(name=name, why=why):
                self._refused(preset_name=name)

    def test_a_refusal_says_what_to_do_instead(self) -> None:
        message = self._refused(preset_name="../escape")
        self.assertIn("mpfb_list_presets", message)
        self.assertIn("human.<name>.json", message)

    def test_a_refusal_names_the_offending_characters(self) -> None:
        # An agent that built the name out of a display name needs to know which
        # character to drop, not that the name was rejected.
        message = self._refused(preset_name="Anna Svensson")
        self.assertIn("' '", message)

    def test_every_name_a_working_install_actually_holds_is_accepted(self) -> None:
        for name in ACCEPTED_NAMES:
            with self.subTest(name=name):
                self.assertEqual(self._run(preset_name=name)["preset_name"], name)

    def test_a_name_is_not_trimmed_before_it_is_used(self) -> None:
        # A trailing space is a different name, MPFB's filename would carry it,
        # and quietly trimming would save a preset the caller did not ask for.
        # It is refused rather than repaired.
        self._refused(preset_name="alice ")

    def test_overwrite_must_be_a_real_bool(self) -> None:
        for value in ("false", "true", 1, 0, None):
            with self.subTest(overwrite=value):
                self._refused(preset_name="alice", overwrite=value)

    def test_the_default_call_refuses_to_overwrite(self) -> None:
        self.assertIs(self._run(preset_name="alice")["overwrite"], False)

    def test_the_subject_is_optional_and_shape_checked(self) -> None:
        self.assertIsNone(self._run(preset_name="alice")["name"])
        self.assertEqual(self._run(preset_name="alice", name="Human")["name"], "Human")
        self._refused(preset_name="alice", name="")
        self._refused(preset_name="alice", name=3)


class SavePresetOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - what MPFB writes, which characters it refuses to serialize, and the generated-Rigify substitution - is checked against a real MPFB
    in ``bridge/test/tests/ddd_mutating/save_preset_test.py``.
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
        save_preset.register(recorder)
        self.call = recorder.function
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "save_preset": fake_bridge.ok_envelope("save_preset", {"found": True, "saved": True, "performed": True}),
        })

    def test_the_tool_sends_the_save_preset_command(self) -> None:
        self.call(preset_name="alice")

        self.assertEqual(self.bridge.commands()[-1], "save_preset")
        self.assertEqual(
            self.bridge.decoded_requests()[-1]["params"],
            {"preset_name": "alice", "name": None, "overwrite": False})

    def test_the_shared_fragment_does_not_reach_the_bridge(self) -> None:
        self.call(preset_name="alice")

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("preset_files", str(request))

    def test_the_name_rule_is_enforced_here_before_a_path_exists(self) -> None:
        # The one argument in this package that becomes a **path**. It is
        # checked on this side of the socket because a name that could escape
        # the config directory is a *shape*, knowable before a request is built.
        for name in ("../escape", "with space", "", "a/b", ".hidden"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.call(preset_name=name)

        self.assertEqual(self.bridge.requests, [],
                         "a name that could become a path must not reach any backend")

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        with self.assertRaises(ValueError):
            self.call(preset_name="alice", overwrite="true")

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="save_preset", state="absent"))

        response = self.call(preset_name="alice")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")


class NameRuleDriftTests(unittest.TestCase):
    """The one rule that lives on both sides of the socket, run as **two**.

    ``mpfbmcp.artifact_names`` is the authoritative check - the tools apply it
    before anything crosses the socket, because a name that becomes a path is a
    shape knowable here - and ``bridge/mpfb_bridge/shared/artifact_names.py``
    carries the same rule as the last statement before ``open()`` on the far
    side. It is there rather than trusted to the client because a listening
    socket is reachable by anything on this machine and not only by mpfb-mcp.
    So both are run over one table of names and held to the same verdicts.

    **Both nouns.** Until FR 027 the rule was the preset rule, in
    ``preset_names.py`` and ``shared/preset_files.py``. FR 027 generalised it on
    each side rather than copying it for saved expressions, so the check now
    runs every name as a ``"preset"`` and as an ``"expression"``: a gap between
    the two sides for either artifact would let a file be written under a name
    that cannot be addressed back.

    It lived in ``tests/test_codegen.py`` and ran as **three** until FR 033
    deleted the generated path, which carried a third copy. The reason the check
    exists is unchanged and is nothing to do with how many copies there are.

    It sits in this module because ``mpfb_save_preset`` is where a name first
    became a path.
    """

    # Every name from the preset and expression tool test modules, plus the
    # boundary cases that only a character-by-character rule can get wrong.
    NAMES = (
        "alice", "bob-2", "klara-v2", "Girl_test_walkCycle", "anna_v2", "v1.2",
        "smile", "angry-shout", "Wink", "subtle.smile",
        "a" * 64, "a" * 65, "1", "_", "-", "...",
        "", "   ", ".", "..", ".hidden", "has space", "trailing ",
        "a/b", "a\\b", "../escape", "/absolute", "c:nope", "na\u00efve", "sm\u00f6rg\u00e5s",
        "semi;colon", "quote'd", 'double"d', "star*", "pipe|", "null\x00byte",
        None, 3, True, 1.5, [], {},
    )

    NOUNS = ("preset", "expression")

    def setUp(self) -> None:
        self.bridge_namespace = _bridge_shared_namespace("artifact_names.py")
        self.bridge_rejection = self.bridge_namespace["name_rejection"]

    def test_both_accept_and_refuse_exactly_the_same_names(self) -> None:
        for noun in self.NOUNS:
            for name in self.NAMES:
                with self.subTest(name=name, noun=noun):
                    self.assertEqual(artifact_names.name_rejection(name, noun) is None,
                                     self.bridge_rejection(name, noun) is None)

    def test_both_give_the_same_reason(self) -> None:
        # Not merely the same verdict: the sentence is what a caller is shown,
        # and two different explanations for one rule is the drift starting.
        for noun in self.NOUNS:
            for name in self.NAMES:
                with self.subTest(name=name, noun=noun):
                    self.assertEqual(artifact_names.name_rejection(name, noun),
                                     self.bridge_rejection(name, noun))

    def test_the_verdict_does_not_depend_on_the_noun(self) -> None:
        # One rule, two artifacts: only the sentence may differ.
        for name in self.NAMES:
            with self.subTest(name=name):
                self.assertEqual(artifact_names.name_rejection(name, "preset") is None,
                                 artifact_names.name_rejection(name, "expression") is None)

    def test_the_preset_wrapper_is_the_rule_with_the_preset_noun(self) -> None:
        for name in self.NAMES:
            with self.subTest(name=name):
                self.assertEqual(artifact_names.preset_name_rejection(name),
                                 artifact_names.name_rejection(name, "preset"))

    def test_the_bound_and_the_pattern_are_the_same_on_both(self) -> None:
        self.assertEqual(artifact_names.NAME_MAX_LENGTH,
                         self.bridge_namespace["NAME_MAX_LENGTH"])
        self.assertEqual(artifact_names.NAME_PATTERN,
                         self.bridge_namespace["NAME_PATTERN"])

    def test_no_accepted_name_can_leave_its_directory(self) -> None:
        # The property the rule exists for, asserted rather than inferred from
        # the pattern: os.path.join of the directory and each artifact's
        # filename stays inside the directory, for every name either side
        # accepts. The two filename shapes are the two commands' own.
        directory = os.path.abspath(os.path.join("/tmp", "mpfb", "somewhere"))
        shapes = (lambda name: "human." + name + ".json", lambda name: name + ".json")
        for name in self.NAMES:
            if self.bridge_rejection(name, "preset") is not None:
                continue
            for shape in shapes:
                with self.subTest(name=name, filename=shape(name)):
                    joined = os.path.abspath(os.path.join(directory, shape(name)))
                    self.assertEqual(os.path.dirname(joined), directory)
