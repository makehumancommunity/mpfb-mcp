# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the shared-fragment source cache, on both sides of it.

The cache exists for a measured reason that has nothing to do with what the
fragments compute: the blender_mcp add-on reads one 4 KB chunk of a request per
timer tick, so a generated program costs about 250 ms per 4 KB against a Blender
that has been talked to recently and about 1 s per 4 KB against one that has
not - whatever the program does. The four modeling-target tools carry 26 KB of
fragments that are byte-identical from call to call, and sending those once per
Blender session takes five to six chunks off every call after the first.

**What the tests are shaped by is which mistakes are dangerous.** Sending a
fragment twice wastes a second; running the *wrong copy* of ``target_categories``
writes a modifier to the wrong shape key. So most of what is asserted here is
about the key: that it follows the source, that two different copies of a
fragment cannot be confused for one another, and that a Blender which does not
hold a fragment says so in a way the tool side acts on rather than answering out
of nothing.

Note what is deliberately *not* cached: what a fragment computes. Every call
still runs the scan, so ``mpfb_list_targets`` still sees a target installed since
Blender started - which MPFB's own panels cannot - and no answer here can be
stale. That is a property of caching source keyed by a hash of itself, and
``test_a_target_installed_between_two_calls_is_still_seen`` is where it is
pinned rather than assumed.

Run with::

    python -m unittest tests.test_shared_cache -v
"""

__all__ = ()

import os
import unittest
from unittest import mock

from mpfbmcp import codegen, shared_cache
from mpfbmcp.codegen import shared_loader

from tests.blender_stubs import DetailTargetTestCase, SESSION_MODULE, touch

LIST_TARGETS_PARAMS = {"section": None, "name_contains": None, "limit": 1000, "offset": 0}


class LoaderTests(DetailTargetTestCase):
    """The generated half: what a program does with a fragment it was not sent."""

    def assemble(self, carry_sources, shared=("target_categories.py",)):
        return codegen.assemble(
            "list_targets.py", bootstrap="raising", params=dict(LIST_TARGETS_PARAMS),
            cached_shared=list(shared), carry_sources=carry_sources)

    def test_a_blender_that_holds_nothing_asks_rather_than_answering(self):
        envelope = self.execute_program(self.assemble(carry_sources=False))

        self.assertEqual(envelope["status"], "error")
        self.assertIn(shared_loader.SHARED_CACHE_MISS_MARKER, envelope["message"])
        self.assertIn(codegen.shared_key("target_categories.py"), envelope["message"])

    def test_the_marker_is_one_string_and_not_two(self):
        # The loader raises it and mpfbmcp/shared_cache.py matches it; a rename
        # on one side alone would turn every miss into a failed call that
        # retried nothing.
        self.assertIn(
            'MPFB_MCP_SHARED_CACHE_MISS = "' + shared_cache.CACHE_MISS_MARKER + '"',
            shared_loader.SHARED_SOURCE_LOADER)

    def test_a_carried_fragment_is_remembered_and_then_reusable(self):
        carried = self.execute_program(self.assemble(carry_sources=True))
        reused = self.execute_program(self.assemble(carry_sources=False))

        self.assertEqual(carried["status"], "ok")
        self.assertEqual(reused["status"], "ok")
        # Not merely "answered": the same answer, out of the same source.
        self.assertEqual(carried["result"], reused["result"])

    def test_the_reused_program_is_five_chunks_smaller_and_that_is_the_point(self):
        carried = self.assemble(carry_sources=True)
        reused = self.assemble(carry_sources=False)

        saved = len(carried.encode("utf-8")) - len(reused.encode("utf-8"))
        self.assertGreater(saved, len(codegen.read_shared("target_categories.py")) - 100)

    def test_a_fragment_is_addressed_by_its_content_and_not_by_its_name(self):
        # Two mpfb-mcp servers may address one Blender, and one of them may be
        # running an edited fragment. Whichever is right, neither may run the
        # other's copy.
        self.execute_program(self.assemble(carry_sources=True))
        source = codegen.assemble(
            "list_targets.py", bootstrap="raising", params=dict(LIST_TARGETS_PARAMS),
            cached_shared=["target_categories.py"], carry_sources=False)
        edited = source.replace(
            codegen.shared_fingerprint("target_categories.py"), "adifferentbuild")

        envelope = self.execute_program(edited)
        self.assertEqual(envelope["status"], "error")
        self.assertIn(shared_loader.SHARED_CACHE_MISS_MARKER, envelope["message"])

    def test_a_fragment_runs_in_the_programs_own_globals(self):
        # Which is what makes the two forms interchangeable from the payload's
        # point of view: it calls the fragment's functions either way.
        result = self.execute_program(self.assemble(carry_sources=True))["result"]
        self.assertTrue(result["sections"])
        self.assertEqual(result["system_targets_dir"], self.system_targets)

    def test_the_session_module_holds_source_and_nothing_else(self):
        import sys  # noqa: PLC0415 - what is in sys.modules is the subject here

        self.assertNotIn(SESSION_MODULE, sys.modules)
        self.execute_program(self.assemble(carry_sources=True))

        held = vars(sys.modules[SESSION_MODULE])["shared_sources"]
        self.assertEqual(list(held), [codegen.shared_key("target_categories.py")])
        self.assertEqual(held[codegen.shared_key("target_categories.py")],
                         codegen.read_shared("target_categories.py"))

    def test_a_traceback_from_inside_a_fragment_names_the_fragment(self):
        # The one thing the inline form gave for free and this one has to be
        # deliberate about: a line number reported from inside Blender has to be
        # traceable to a file. Compiling under the fragment's own name is
        # better than an offset into the whole program, not merely equal to it.
        broken = codegen.assemble(
            "list_targets.py", bootstrap="raising", params=dict(LIST_TARGETS_PARAMS),
            cached_shared=["target_categories.py"], carry_sources=True)
        broken = broken.replace('LocationService = _MPFB_SERVICES["LocationService"]',
                                'raise ValueError("deliberate")', 1)

        envelope = self.execute_program(broken)
        self.assertEqual(envelope["status"], "error")
        self.assertIn('File "<shared: target_categories.py>"', envelope["message"])


class SendTests(DetailTargetTestCase):
    """``shared_cache.send()`` against a socket that really runs the program."""

    def setUp(self):
        super().setUp()
        # Process-global, so a test that primed it would otherwise decide what
        # the next one sends.
        shared_cache._PRIMED.clear()
        self.addCleanup(shared_cache._PRIMED.clear)
        self.programs = []

    def fake_send_code(self, code, strict_json=True):
        self.programs.append(code)
        return self.execute_program(code)

    def list_targets(self, **kwargs):
        with mock.patch.object(shared_cache, "send_code", self.fake_send_code):
            return shared_cache.send(
                "list_targets.py", dict(LIST_TARGETS_PARAMS),
                cached_shared=["target_categories.py"], **kwargs)

    def carried(self, index):
        return "(carried)" in self.programs[index]

    def test_the_first_call_carries_the_source_and_the_second_does_not(self):
        first = self.list_targets()
        second = self.list_targets()

        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertEqual(len(self.programs), 2)
        self.assertTrue(self.carried(0))
        self.assertFalse(self.carried(1))
        self.assertLess(len(self.programs[1]), len(self.programs[0]))

    def test_the_two_calls_answer_identically(self):
        # The saving is in what crossed the socket, never in what came back.
        self.assertEqual(self.list_targets()["result"], self.list_targets()["result"])

    def test_a_target_installed_between_two_calls_is_still_seen(self):
        """What caching source rather than answers buys, stated as an assertion.

        FR 006 made mpfb_list_targets able to see a target installed since
        Blender started, which MPFB's own panels cannot. A cache of the scan's
        *result* would have had to work to keep that; a cache of the scan's
        *source* keeps it by doing nothing, and this is where that is checked
        rather than argued.
        """
        before = self.list_targets()["result"]
        self.assertNotIn("cat_whiskers", [entry["name"] for entry in before["user_targets"]])

        touch(os.path.join(self.user_targets, "animal", "cat_whiskers.target"))
        after = self.list_targets()["result"]

        self.assertIn("cat_whiskers", [entry["name"] for entry in after["user_targets"]])
        # And without a retry: the second program carried no source at all.
        self.assertEqual(len(self.programs), 2)
        self.assertFalse(self.carried(1))

    def test_a_blender_that_restarted_is_recovered_from_rather_than_reported(self):
        import sys  # noqa: PLC0415 - a restart is exactly the module going away

        self.list_targets()
        sys.modules.pop(SESSION_MODULE, None)

        response = self.list_targets()

        self.assertEqual(response["status"], "ok")
        # Three programs for two calls: the one that could not answer, and the
        # retry that carried the source.
        self.assertEqual(len(self.programs), 3)
        self.assertFalse(self.carried(1))
        self.assertTrue(self.carried(2))

    def test_a_miss_is_retried_once_and_not_twice(self):
        # A second miss means the cache is not being written at all, and the
        # caller is better served by that error than by a loop.
        envelope = {"status": "error",
                    "message": shared_cache.CACHE_MISS_MARKER + ": nothing here"}
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = envelope
            self.assertIs(shared_cache.send(
                "list_targets.py", dict(LIST_TARGETS_PARAMS),
                cached_shared=["target_categories.py"]), envelope)

        self.assertEqual(send_code.call_count, 2)

    def test_an_ordinary_error_is_returned_rather_than_retried(self):
        envelope = {"status": "error", "message": "no MPFB"}
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = envelope
            self.assertIs(shared_cache.send(
                "list_targets.py", dict(LIST_TARGETS_PARAMS),
                cached_shared=["target_categories.py"]), envelope)

        self.assertEqual(send_code.call_count, 1)

    def test_the_memo_is_per_address(self):
        # Two Blenders on one machine are two caches, and the memo must not let
        # a program that carries nothing be sent to the cold one.
        self.list_targets()
        with mock.patch.dict(os.environ, {"BLENDER_MCP_PORT": "9999"}):
            self.list_targets()

        self.assertEqual(len(self.programs), 2)
        self.assertTrue(self.carried(1))

    def test_one_unheld_fragment_makes_the_whole_call_carry_again(self):
        # Deliberately coarse: three fragments in one program are one decision,
        # and a partial carry would save a chunk while doubling the states the
        # retry has to reason about.
        with mock.patch.object(shared_cache, "send_code", self.fake_send_code):
            shared_cache.send("list_targets.py", dict(LIST_TARGETS_PARAMS),
                              cached_shared=["target_categories.py"])
            shared_cache.send("list_targets.py", dict(LIST_TARGETS_PARAMS),
                              cached_shared=["target_categories.py", "performed.py"])

        self.assertTrue(self.carried(1))

    def test_strict_json_is_always_asked_for(self):
        with mock.patch.object(shared_cache, "send_code") as send_code:
            send_code.return_value = {"status": "ok", "result": {}}
            shared_cache.send("list_targets.py", dict(LIST_TARGETS_PARAMS),
                              cached_shared=["target_categories.py"])

        self.assertIs(send_code.call_args[1]["strict_json"], True)


if __name__ == "__main__":
    unittest.main()
