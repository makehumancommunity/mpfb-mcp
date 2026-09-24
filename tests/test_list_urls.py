# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_urls tool: the four states, and the merge.

Two layers as usual, but the split between them is unusual and is the thing
worth checking. The command only *reads* MPFB's ``ui.weburls`` module; the
merge against the vendored copy, the descriptions and the staleness report are
assembled on this side of the socket, so the wrapper layer carries most of the
behaviour here rather than most of the plumbing.

Four states have to come back as successful answers and one must not:

- MPFB read live;
- MPFB absent, or loaded but with no ``weburls`` in ``sys.modules``;
- Blender unreachable - a ``ConnectionError`` out of the wire client, which this
  is the only tool in the package to catch;
- and a command that **failed inside Blender**, which is a defect and must
  still surface as an error envelope. Swallowing that into a "fallback" answer
  would hide it permanently, so it has a test of its own.

The merge is exercised against hand-built answers of the shape the command
leaves behind - including one reporting an **extra** ``URL_`` key and one
**missing** a key mpfb-mcp vendors, since enumerate-by-prefix and the staleness
report are exactly the two claims a table copied by hand cannot make for
itself. What the command reads out of a real, initialized MPFB is asked in
``bridge/test/tests/ccc_reading/list_urls_test.py``; that ``<root>.ui.weburls`` is in
``sys.modules`` at all was established against a running Blender by
``feature-requests/done/024-documentation-urls/check_weburls.py``.

Run with::

    python -m unittest tests.test_list_urls -v
"""

from __future__ import annotations

__all__ = ()

import inspect
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.reference import urls

from tests import fake_bridge
from mpfbmcp.tools import list_urls



_STUB_PACKAGE = "bl_ext.test_repo.mpfb"
# Deliberately not ending in "mpfb", or the add-on's candidate scan would pick
# the weburls module up as an MPFB install of its own.
_STUB_WEBURLS = _STUB_PACKAGE + ".ui.weburls"


def _register_and_get_tool():
    mcp = FastMCP("test")
    list_urls.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_urls"].fn  # noqa: SLF001


def _command_result(**overrides) -> dict:
    """An answer of the shape ``list_urls`` actually leaves behind."""
    answer = {
        "state": "ok",
        "package": _STUB_PACKAGE,
        "version": "2.0.17",
        "weburls_module": _STUB_WEBURLS,
        "weburls_read": True,
        "urls": dict(urls.MPFB_URLS),
        "skipped_keys": [],
        "reason": None,
    }
    answer.update(overrides)
    return answer


def _by_key(result: dict) -> dict:
    return {entry["key"]: entry for entry in result["urls"]}


class ListUrlsLiveTests(unittest.TestCase):
    """MPFB was read: the live values win, and the answer says so."""

    def setUp(self) -> None:
        self.mpfb_list_urls = _register_and_get_tool()

    def _call(self, answer: dict) -> dict:
        with mock.patch("mpfbmcp.bridge_connection.send_command",
                        return_value={"status": "ok", "result": answer}):
            envelope = self.mpfb_list_urls()
        self.assertEqual(envelope["status"], "ok")
        return envelope["result"]

    def test_takes_no_arguments(self) -> None:
        self.assertEqual(list(inspect.signature(self.mpfb_list_urls).parameters), [])

    def test_an_agreeing_live_read_is_reported_as_live_and_not_stale(self) -> None:
        result = self._call(_command_result())

        self.assertEqual(result["source_of_truth"], "mpfb")
        self.assertIsNone(result["fallback_reason"])
        self.assertTrue(result["blender_reachable"])
        self.assertFalse(result["fallback_stale"])
        self.assertEqual(result["fallback_differences"], [])
        self.assertEqual(result["mpfb_status"]["state"], "ok")
        self.assertEqual(result["mpfb_status"]["version"], "2.0.17")
        self.assertTrue(result["mpfb_status"]["weburls_read"])

    def test_every_mpfb_key_is_described_and_sourced(self) -> None:
        entries = _by_key(self._call(_command_result()))

        for key in urls.MPFB_URLS:
            with self.subTest(key=key):
                self.assertEqual(entries[key]["source"], "mpfb")
                self.assertEqual(entries[key]["url"], urls.MPFB_URLS[key])
                # Every vendored key has prose of ours; an undescribed one is
                # only possible for a constant MPFB added later.
                self.assertTrue(entries[key]["title"])
                self.assertTrue(entries[key]["description"])
                self.assertTrue(entries[key]["keywords"])

    def test_ecosystem_links_are_carried_and_marked_as_ours(self) -> None:
        entries = _by_key(self._call(_command_result()))

        for key in urls.ECOSYSTEM_URLS:
            with self.subTest(key=key):
                self.assertEqual(entries[key]["source"], "mpfb_mcp")
                self.assertEqual(entries[key]["url"], urls.ECOSYSTEM_URLS[key])

    def test_count_matches_the_entries_and_nothing_is_capped(self) -> None:
        result = self._call(_command_result())

        self.assertEqual(result["count"], len(result["urls"]))
        # FR-6: this answer fits, so a caller must not go looking for paging.
        for absent in ("truncated", "total_count", "offset", "limit"):
            self.assertNotIn(absent, result)

    def test_a_constant_mpfb_added_is_reported_undescribed_and_as_added(self) -> None:
        live = dict(urls.MPFB_URLS)
        live["URL_NEWLY_ADDED"] = "https://example.invalid/new"

        result = self._call(_command_result(urls=live))
        entries = _by_key(result)

        # Enumerated by prefix, so it appears without a change in this package -
        # with null prose rather than being dropped for want of it.
        self.assertEqual(entries["URL_NEWLY_ADDED"]["url"], "https://example.invalid/new")
        self.assertEqual(entries["URL_NEWLY_ADDED"]["source"], "mpfb")
        self.assertIsNone(entries["URL_NEWLY_ADDED"]["title"])
        self.assertIsNone(entries["URL_NEWLY_ADDED"]["description"])
        self.assertIsNone(entries["URL_NEWLY_ADDED"]["keywords"])
        self.assertTrue(result["fallback_stale"])
        self.assertIn({"key": "URL_NEWLY_ADDED", "difference": "added_by_mpfb",
                       "mpfb_url": "https://example.invalid/new", "vendored_url": None},
                      result["fallback_differences"])

    def test_a_constant_mpfb_changed_is_reported_with_the_live_value_winning(self) -> None:
        live = dict(urls.MPFB_URLS)
        live["URL_FORUM"] = "https://example.invalid/moved"

        result = self._call(_command_result(urls=live))

        self.assertEqual(_by_key(result)["URL_FORUM"]["url"], "https://example.invalid/moved")
        self.assertTrue(result["fallback_stale"])
        self.assertIn({"key": "URL_FORUM", "difference": "changed",
                       "mpfb_url": "https://example.invalid/moved",
                       "vendored_url": urls.MPFB_URLS["URL_FORUM"]},
                      result["fallback_differences"])

    def test_a_constant_mpfb_removed_is_not_reported_but_is_named_as_a_difference(self) -> None:
        live = dict(urls.MPFB_URLS)
        del live["URL_FAQ"]

        result = self._call(_command_result(urls=live))

        # The live read is the source of truth in both directions: a key MPFB no
        # longer has must not be resurrected from the vendored copy.
        self.assertNotIn("URL_FAQ", _by_key(result))
        self.assertTrue(result["fallback_stale"])
        self.assertIn({"key": "URL_FAQ", "difference": "missing_from_mpfb",
                       "mpfb_url": None, "vendored_url": urls.MPFB_URLS["URL_FAQ"]},
                      result["fallback_differences"])

    def test_an_mpfb_constant_colliding_with_an_ecosystem_key_resolves_to_mpfbs(self) -> None:
        collision = sorted(urls.ECOSYSTEM_URLS)[0]
        live = dict(urls.MPFB_URLS)
        live[collision] = "https://example.invalid/mpfbs-own"

        entries = _by_key(self._call(_command_result(urls=live)))

        # Reported once, as MPFB's: the live value wins every disagreement, and
        # an ecosystem key is not an exception to that.
        self.assertEqual(entries[collision]["url"], "https://example.invalid/mpfbs-own")
        self.assertEqual(entries[collision]["source"], "mpfb")

    def test_a_weburls_module_with_no_constants_is_a_live_read_of_nothing(self) -> None:
        # The one place an empty dict and None must not be conflated: MPFB was
        # read and publishes nothing is a live answer, not a fallback, and the
        # differences say the vendored copy is the one out of step.
        result = self._call(_command_result(urls=dict()))

        self.assertEqual(result["source_of_truth"], "mpfb")
        self.assertEqual([entry for entry in result["urls"] if entry["source"] == "mpfb"], [])
        self.assertTrue(result["fallback_stale"])
        self.assertEqual(
            sorted(difference["difference"] for difference in result["fallback_differences"]),
            ["missing_from_mpfb"] * len(urls.MPFB_URLS))

    def test_a_skipped_non_string_constant_is_reported(self) -> None:
        result = self._call(_command_result(skipped_keys=["URL_SOMETHING_ODD"]))

        self.assertEqual(result["skipped_keys"], ["URL_SOMETHING_ODD"])


class ListUrlsFallbackTests(unittest.TestCase):
    """The three states in which MPFB's own values could not be read."""

    def setUp(self) -> None:
        self.mpfb_list_urls = _register_and_get_tool()

    def _call_with_answer(self, answer: dict) -> dict:
        with mock.patch("mpfbmcp.bridge_connection.send_command",
                        return_value={"status": "ok", "result": answer}):
            envelope = self.mpfb_list_urls()
        self.assertEqual(envelope["status"], "ok")
        return envelope["result"]

    def _assert_answers_from_the_vendored_copy(self, result: dict) -> None:
        self.assertEqual(result["source_of_truth"], "builtin_fallback")
        self.assertTrue(result["fallback_reason"])
        entries = _by_key(result)
        for key, url in urls.MPFB_URLS.items():
            self.assertEqual(entries[key]["url"], url, key)
        for key, url in urls.ECOSYSTEM_URLS.items():
            self.assertEqual(entries[key]["url"], url, key)

    def _assert_staleness_is_unknown(self, result: dict) -> None:
        # null, not false and not []: "the copy agrees with MPFB" and "we could
        # not ask MPFB" are different claims and must not be spelled alike.
        self.assertIsNone(result["fallback_stale"])
        self.assertIsNone(result["fallback_differences"])

    def test_mpfb_absent_still_answers_from_the_vendored_copy(self) -> None:
        result = self._call_with_answer(_command_result(
            state="absent", package=None, version=None, weburls_module=None,
            weburls_read=False, urls=None, skipped_keys=None,
            reason="MPFB is not loaded in this Blender instance ..."))

        self._assert_answers_from_the_vendored_copy(result)
        self._assert_staleness_is_unknown(result)
        self.assertEqual(result["mpfb_status"]["state"], "absent")
        self.assertTrue(result["blender_reachable"])

    def test_mpfb_present_without_its_weburls_module_answers_and_says_why(self) -> None:
        result = self._call_with_answer(_command_result(
            weburls_read=False, urls=None, skipped_keys=None,
            reason="MPFB is loaded and initialized, but ... is not in sys.modules ..."))

        self._assert_answers_from_the_vendored_copy(result)
        self._assert_staleness_is_unknown(result)
        # The state is still "ok" - MPFB is fine, the module simply is not there,
        # and the two are separate facts the caller may need both of.
        self.assertEqual(result["mpfb_status"]["state"], "ok")
        self.assertEqual(result["mpfb_status"]["weburls_module"], _STUB_WEBURLS)
        self.assertIn("sys.modules", result["fallback_reason"])

    def test_an_unreachable_blender_answers_rather_than_failing(self) -> None:
        failure = ConnectionError("Cannot connect to Blender at localhost:9876.")
        with mock.patch("mpfbmcp.bridge_connection.send_command", side_effect=failure):
            envelope = self.mpfb_list_urls()

        # The whole reason this tool catches the transport failure at all: the
        # download link is the answer precisely when nothing is running.
        self.assertEqual(envelope["status"], "ok")
        result = envelope["result"]
        self._assert_answers_from_the_vendored_copy(result)
        self._assert_staleness_is_unknown(result)
        self.assertFalse(result["blender_reachable"])
        self.assertEqual(result["mpfb_status"]["state"], "unreachable")
        # The socket error's own text, which names the host and port.
        self.assertIn("localhost:9876", result["fallback_reason"])

    def test_a_command_failure_is_not_swallowed_into_a_fallback(self) -> None:
        # A command that failed inside Blender is a defect here. If it came back
        # as a cheerful fallback answer it would never be found. The envelope
        # reaches the caller exactly as the add-on wrote it, slug and all: the
        # fallback is for a bridge that cannot be reached, not for one that
        # answered.
        envelope = {"status": "error", "error": "mpfb_unavailable",
                    "message": "NameError: _mpfb_module"}
        with mock.patch("mpfbmcp.bridge_connection.send_command", return_value=envelope):
            response = self.mpfb_list_urls()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "NameError: _mpfb_module")
        self.assertEqual(response["error"], "mpfb_unavailable")
        self.assertNotIn("result", response, "a failure must not carry a fallback answer")

    def test_a_non_dict_result_is_passed_through_rather_than_reshaped(self) -> None:
        envelope = {"status": "ok", "result": "something unexpected"}
        with mock.patch("mpfbmcp.bridge_connection.send_command", return_value=envelope):
            self.assertEqual(self.mpfb_list_urls(), envelope)

    def test_only_a_connection_error_is_caught(self) -> None:
        # Any other exception out of send_command() is a bug on this side and must
        # propagate; catching broadly here would hide it behind an answer.
        with mock.patch("mpfbmcp.bridge_connection.send_command",
                        side_effect=ValueError("a defect in this package")):
            with self.assertRaises(ValueError):
                self.mpfb_list_urls()


class ListUrlsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """The bridge path, and the one case where the two transports differ.

    This tool migrated because ``bridge_connection.send_command()`` raises
    ``ConnectionError`` in exactly the situations ``send_command()``
    does - which is what the fallback answer turns on. What it does **not** do
    is turn a protocol handshake refusal into one, and FR 032 decided
    deliberately that it should not: a version mismatch between mpfb-mcp and
    the add-on is a configuration fault the operator has to fix, and an answer
    full of vendored URLs would hide it for as long as it lasted.

    Both halves of that are asserted below, because a test for only the first
    would pass if the second were quietly changed.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _register_and_get_tool()

    def _bridge_answering(self, answer):
        return self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_urls": fake_bridge.ok_envelope("list_urls", answer),
        })

    def test_the_tool_sends_the_list_urls_command_with_no_parameters(self) -> None:
        bridge = self._bridge_answering(
            {"state": "ok", "weburls_read": True, "urls": {}, "skipped_keys": [],
             "package": "bl_ext.user_default.mpfb", "version": "2.0.0",
             "weburls_module": "bl_ext.user_default.mpfb.ui.weburls", "reason": None})

        response = self.call()

        self.assertEqual(bridge.commands()[-1], "list_urls")
        self.assertEqual(bridge.decoded_requests()[-1].get("params", {}), {})
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["source_of_truth"], "mpfb")

    def test_the_merge_still_happens_on_this_side(self) -> None:
        # The bridge removes the wire argument for splitting the merge off, and
        # the real reason survives it: the same merge runs in the state where no
        # command runs at all. So the command hands back raw pairs and this side
        # assembles the answer, exactly as on the generated path.
        self._bridge_answering(
            {"state": "ok", "weburls_read": True,
             "urls": {"URL_ASSET_PACKS": "https://example.invalid/packs"},
             "skipped_keys": [], "package": "mpfb", "version": "2.0.0",
             "weburls_module": "mpfb.ui.weburls", "reason": None})

        result = self.call()["result"]

        entries = {entry["key"]: entry for entry in result["urls"]}
        self.assertEqual(entries["URL_ASSET_PACKS"]["url"], "https://example.invalid/packs")
        self.assertTrue(entries["URL_ASSET_PACKS"]["description"],
                        "the description is mpfb-mcp's text, added here")
        self.assertIsNotNone(result["fallback_differences"],
                             "the staleness report is computed here too")

    def test_an_unreachable_bridge_answers_from_the_vendored_copy(self) -> None:
        # The claim that made this tool migratable at all, asserted against the
        # bridge's own client rather than assumed from the other one's.
        self.set_env_var(bridge_connection.BRIDGE_PORT_VARIABLE, "1")

        response = self.call()

        self.assertEqual(response["status"], "ok")
        result = response["result"]
        self.assertEqual(result["source_of_truth"], "builtin_fallback")
        self.assertIs(result["blender_reachable"], False)
        self.assertEqual(result["mpfb_status"]["state"], "unreachable")
        self.assertTrue(result["urls"], "the vendored copy is the answer here")

    def test_a_handshake_refusal_is_an_error_rather_than_a_fallback(self) -> None:
        # The one narrow case where the two transports answer differently, and
        # it is a decision rather than an oversight: see this class's docstring.
        self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope(
                "get_status",
                fake_bridge.status_result(
                    protocol_version=bridge_connection.PROTOCOL_VERSION + 5,
                    min_supported=bridge_connection.PROTOCOL_VERSION + 5)),
        })

        response = self.call()

        self.assertEqual(response["status"], "error",
                         "a version mismatch is a configuration fault, not a circumstance")
        self.assertNotIn("result", response,
                         "and it must not be papered over with vendored URLs")


class VendoredTableTests(unittest.TestCase):
    """The table itself, independent of how it is read."""

    def test_every_vendored_and_ecosystem_key_has_prose(self) -> None:
        for key in list(urls.MPFB_URLS) + list(urls.ECOSYSTEM_URLS):
            with self.subTest(key=key):
                self.assertIn(key, urls.DESCRIPTIONS)
                described = urls.DESCRIPTIONS[key]
                self.assertTrue(described["title"])
                self.assertTrue(described["description"])
                self.assertTrue(described["keywords"])

    def test_no_description_is_written_for_a_key_no_table_carries(self) -> None:
        # Prose for a key nothing can report is prose nobody reads, and is the
        # first symptom of a URL having been removed from a table by hand.
        orphans = set(urls.DESCRIPTIONS) - set(urls.MPFB_URLS) - set(urls.ECOSYSTEM_URLS)
        self.assertEqual(set(), orphans)

    def test_every_url_is_absolute_and_no_two_keys_collide(self) -> None:
        self.assertEqual(set(), set(urls.MPFB_URLS) & set(urls.ECOSYSTEM_URLS))
        for key, url in list(urls.MPFB_URLS.items()) + list(urls.ECOSYSTEM_URLS.items()):
            with self.subTest(key=key):
                self.assertTrue(url.startswith("http://") or url.startswith("https://"))
                self.assertTrue(key.startswith("URL_"))

    def test_merging_nothing_live_leaves_staleness_unknown(self) -> None:
        merged = urls.merge(None)

        self.assertIsNone(merged["fallback_stale"])
        self.assertIsNone(merged["fallback_differences"])
        self.assertEqual(merged["count"], len(urls.MPFB_URLS) + len(urls.ECOSYSTEM_URLS))
        self.assertEqual(merged["vendored_mpfb_key_count"], len(urls.MPFB_URLS))


if __name__ == "__main__":
    unittest.main()
