# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_urls tool: the four states, and the payload's prefix scan.

Two layers as usual, but the split between them is unusual and is the thing
worth checking. The payload only *reads* MPFB's ``ui.weburls`` module; the merge
against the vendored copy, the descriptions and the staleness report are
assembled on this side of the socket, so the wrapper layer carries most of the
behaviour here rather than most of the plumbing.

Four states have to come back as successful answers and one must not:

- MPFB read live;
- MPFB absent, or loaded but with no ``weburls`` in ``sys.modules``;
- Blender unreachable - a ``ConnectionError`` out of ``send_code()``, which this
  is the only tool in the package to catch;
- and a payload that **raised inside Blender**, which is a defect and must still
  surface as an error envelope. Swallowing that into a "fallback" answer would
  hide it permanently, so it has a test of its own.

The payload is executed against a stub ``sys.modules`` carrying a fake
``ui.weburls`` - including one with an **extra** ``URL_`` constant and one
**missing** a key mpfb-mcp vendors, since enumerate-by-prefix and the staleness
report are exactly the two claims a table copied by hand cannot make for itself.

What none of this can establish is that a real, initialized MPFB has
``<root>.ui.weburls`` in ``sys.modules`` at all: the stub here is built from
that assumption. That is checked against a running Blender by
``feature-requests/done/024-documentation-urls/check_weburls.py``.

Run with::

    python -m unittest tests.test_list_urls -v
"""

from __future__ import annotations

__all__ = ()

import inspect
import sys
import types
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import codegen
from mpfbmcp.reference import urls
from mpfbmcp.tools import list_urls

_STUB_PACKAGE = "bl_ext.test_repo.mpfb"
# Deliberately not ending in "mpfb", or the bootstrap's candidate scan would
# pick the weburls module up as an MPFB install of its own.
_STUB_WEBURLS = _STUB_PACKAGE + ".ui.weburls"


def _list_urls_code() -> str:
    """The source mpfb_list_urls sends, assembled exactly as the tool does."""
    return codegen.assemble("list_urls.py", bootstrap="non_raising")


def _register_and_get_tool():
    mcp = FastMCP("test")
    list_urls.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_urls"].fn  # noqa: SLF001


def _payload_result(**overrides) -> dict:
    """A payload answer of the shape the generated code actually leaves behind."""
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

    def _call(self, payload: dict) -> dict:
        with mock.patch("mpfbmcp.tools.list_urls.send_code",
                        return_value={"status": "ok", "result": payload}):
            envelope = self.mpfb_list_urls()
        self.assertEqual(envelope["status"], "ok")
        return envelope["result"]

    def test_takes_no_arguments(self) -> None:
        self.assertEqual(list(inspect.signature(self.mpfb_list_urls).parameters), [])

    def test_an_agreeing_live_read_is_reported_as_live_and_not_stale(self) -> None:
        result = self._call(_payload_result())

        self.assertEqual(result["source_of_truth"], "mpfb")
        self.assertIsNone(result["fallback_reason"])
        self.assertTrue(result["blender_reachable"])
        self.assertFalse(result["fallback_stale"])
        self.assertEqual(result["fallback_differences"], [])
        self.assertEqual(result["mpfb_status"]["state"], "ok")
        self.assertEqual(result["mpfb_status"]["version"], "2.0.17")
        self.assertTrue(result["mpfb_status"]["weburls_read"])

    def test_every_mpfb_key_is_described_and_sourced(self) -> None:
        entries = _by_key(self._call(_payload_result()))

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
        entries = _by_key(self._call(_payload_result()))

        for key in urls.ECOSYSTEM_URLS:
            with self.subTest(key=key):
                self.assertEqual(entries[key]["source"], "mpfb_mcp")
                self.assertEqual(entries[key]["url"], urls.ECOSYSTEM_URLS[key])

    def test_count_matches_the_entries_and_nothing_is_capped(self) -> None:
        result = self._call(_payload_result())

        self.assertEqual(result["count"], len(result["urls"]))
        # FR-6: this answer fits, so a caller must not go looking for paging.
        for absent in ("truncated", "total_count", "offset", "limit"):
            self.assertNotIn(absent, result)

    def test_a_constant_mpfb_added_is_reported_undescribed_and_as_added(self) -> None:
        live = dict(urls.MPFB_URLS)
        live["URL_NEWLY_ADDED"] = "https://example.invalid/new"

        result = self._call(_payload_result(urls=live))
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

        result = self._call(_payload_result(urls=live))

        self.assertEqual(_by_key(result)["URL_FORUM"]["url"], "https://example.invalid/moved")
        self.assertTrue(result["fallback_stale"])
        self.assertIn({"key": "URL_FORUM", "difference": "changed",
                       "mpfb_url": "https://example.invalid/moved",
                       "vendored_url": urls.MPFB_URLS["URL_FORUM"]},
                      result["fallback_differences"])

    def test_a_constant_mpfb_removed_is_not_reported_but_is_named_as_a_difference(self) -> None:
        live = dict(urls.MPFB_URLS)
        del live["URL_FAQ"]

        result = self._call(_payload_result(urls=live))

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

        entries = _by_key(self._call(_payload_result(urls=live)))

        # Reported once, as MPFB's: the live value wins every disagreement, and
        # an ecosystem key is not an exception to that.
        self.assertEqual(entries[collision]["url"], "https://example.invalid/mpfbs-own")
        self.assertEqual(entries[collision]["source"], "mpfb")

    def test_a_weburls_module_with_no_constants_is_a_live_read_of_nothing(self) -> None:
        # The one place an empty dict and None must not be conflated: MPFB was
        # read and publishes nothing is a live answer, not a fallback, and the
        # differences say the vendored copy is the one out of step.
        result = self._call(_payload_result(urls=dict()))

        self.assertEqual(result["source_of_truth"], "mpfb")
        self.assertEqual([entry for entry in result["urls"] if entry["source"] == "mpfb"], [])
        self.assertTrue(result["fallback_stale"])
        self.assertEqual(
            sorted(difference["difference"] for difference in result["fallback_differences"]),
            ["missing_from_mpfb"] * len(urls.MPFB_URLS))

    def test_a_skipped_non_string_constant_is_reported(self) -> None:
        result = self._call(_payload_result(skipped_keys=["URL_SOMETHING_ODD"]))

        self.assertEqual(result["skipped_keys"], ["URL_SOMETHING_ODD"])


class ListUrlsFallbackTests(unittest.TestCase):
    """The three states in which MPFB's own values could not be read."""

    def setUp(self) -> None:
        self.mpfb_list_urls = _register_and_get_tool()

    def _call_with_payload(self, payload: dict) -> dict:
        with mock.patch("mpfbmcp.tools.list_urls.send_code",
                        return_value={"status": "ok", "result": payload}):
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
        result = self._call_with_payload(_payload_result(
            state="absent", package=None, version=None, weburls_module=None,
            weburls_read=False, urls=None, skipped_keys=None,
            reason="MPFB is not loaded in this Blender instance ..."))

        self._assert_answers_from_the_vendored_copy(result)
        self._assert_staleness_is_unknown(result)
        self.assertEqual(result["mpfb_status"]["state"], "absent")
        self.assertTrue(result["blender_reachable"])

    def test_mpfb_present_without_its_weburls_module_answers_and_says_why(self) -> None:
        result = self._call_with_payload(_payload_result(
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
        with mock.patch("mpfbmcp.tools.list_urls.send_code", side_effect=failure):
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

    def test_a_payload_error_is_not_swallowed_into_a_fallback(self) -> None:
        # A payload that raised inside Blender is a defect here. If it came back
        # as a cheerful fallback answer it would never be found.
        envelope = {"status": "error", "message": "NameError: _mpfb_module"}
        with mock.patch("mpfbmcp.tools.list_urls.send_code", return_value=envelope):
            self.assertEqual(self.mpfb_list_urls(), envelope)

    def test_a_non_dict_result_is_passed_through_rather_than_reshaped(self) -> None:
        envelope = {"status": "ok", "result": "something unexpected"}
        with mock.patch("mpfbmcp.tools.list_urls.send_code", return_value=envelope):
            self.assertEqual(self.mpfb_list_urls(), envelope)

    def test_only_a_connection_error_is_caught(self) -> None:
        # Any other exception out of send_code() is a bug on this side and must
        # propagate; catching broadly here would hide it behind an answer.
        with mock.patch("mpfbmcp.tools.list_urls.send_code",
                        side_effect=ValueError("a defect in this package")):
            with self.assertRaises(ValueError):
                self.mpfb_list_urls()


class ListUrlsCodeTests(unittest.TestCase):
    def test_generated_code_compiles(self) -> None:
        compile(_list_urls_code(), "<generated>", "exec")

    def test_generated_code_never_imports_the_ui_module(self) -> None:
        # weburls is read out of sys.modules. An import here would re-execute
        # MPFB code inside an install that may already be broken.
        code = _list_urls_code()
        self.assertNotIn("import_module", code)
        self.assertNotIn("importlib", code)
        self.assertIn("sys.modules.get(", code)

    def test_the_program_does_not_carry_the_vendored_table(self) -> None:
        """The size claim behind assembling the answer on this side of the socket.

        A program costs ~250 ms per 4 KB on the wire whatever it does, so the
        alternative design - send the vendored URLs in as PARAMS and merge
        inside Blender - would have put ~3 KB on every call to compute what a
        local function already computes. What is asserted is therefore that the
        table is *not* in the program, rather than a byte ceiling: at 6.8 KB
        assembled this is the third-smallest of the package's twenty-one
        programs, and like all of them it is mostly its own docstring.
        """
        code = _list_urls_code()
        for url in urls.MPFB_URLS.values():
            self.assertNotIn(url, code)
        for url in urls.ECOSYSTEM_URLS.values():
            self.assertNotIn(url, code)


class GeneratedCodeExecutionTests(unittest.TestCase):
    """Executes the generated source against a stubbed MPFB in sys.modules."""

    def setUp(self) -> None:
        stray = [name for name in list(sys.modules) if name.endswith("mpfb")]
        self.assertEqual(stray, [], "a real module ending in 'mpfb' would skew these tests")
        self._injected: list[str] = []

    def tearDown(self) -> None:
        for name in self._injected:
            sys.modules.pop(name, None)

    def _inject(self, name, module) -> None:
        sys.modules[name] = module
        self._injected.append(name)

    def _inject_mpfb(self, contextual_information=None):
        module = types.ModuleType(_STUB_PACKAGE)
        module.VERSION = (2, 0, 17)
        module.MPFB_CONTEXTUAL_INFORMATION = (
            contextual_information if contextual_information is not None
            else {"SERVICES": dict()})
        self._inject(_STUB_PACKAGE, module)

    def _inject_weburls(self, values, extras=None):
        module = types.ModuleType(_STUB_WEBURLS)
        for key, value in values.items():
            setattr(module, key, value)
        for key, value in (extras or dict()).items():
            setattr(module, key, value)
        # Module-level names MPFB's own weburls.py also has, none of which start
        # with URL_ and none of which may end up in the answer.
        module.__doc__ = "This file contains the web addresses used by the UI."
        module.SOMETHING_ELSE = "not a url"
        self._inject(_STUB_WEBURLS, module)

    def _run(self) -> dict:
        namespace = dict()
        exec(_list_urls_code(), namespace)  # noqa: S102
        return namespace["result"]

    def test_reads_every_url_prefixed_constant_and_nothing_else(self) -> None:
        self._inject_mpfb()
        self._inject_weburls(urls.MPFB_URLS)

        result = self._run()

        self.assertTrue(result["weburls_read"])
        self.assertEqual(result["urls"], dict(urls.MPFB_URLS))
        self.assertEqual(result["skipped_keys"], [])
        self.assertIsNone(result["reason"])
        self.assertEqual(result["weburls_module"], _STUB_WEBURLS)
        self.assertEqual(result["version"], "2.0.17")

    def test_a_constant_mpfb_adds_later_is_picked_up_by_the_prefix_scan(self) -> None:
        # The claim the enumerate-by-prefix rule exists to make: no change in
        # this repository is needed for MPFB to publish a new address.
        self._inject_mpfb()
        self._inject_weburls(urls.MPFB_URLS, extras={"URL_SOMETHING_NEW": "https://new.invalid/"})

        self.assertEqual(self._run()["urls"]["URL_SOMETHING_NEW"], "https://new.invalid/")

    def test_a_url_constant_that_is_not_a_string_is_skipped_and_named(self) -> None:
        self._inject_mpfb()
        self._inject_weburls(urls.MPFB_URLS, extras={"URL_NOT_A_STRING": ["a", "list"]})

        result = self._run()

        self.assertNotIn("URL_NOT_A_STRING", result["urls"])
        self.assertEqual(result["skipped_keys"], ["URL_NOT_A_STRING"])

    def test_mpfb_absent_reports_the_reason_and_reads_nothing(self) -> None:
        result = self._run()

        self.assertEqual(result["state"], "absent")
        self.assertFalse(result["weburls_read"])
        self.assertIsNone(result["urls"])
        self.assertIsNone(result["weburls_module"])
        self.assertIn("not loaded", result["reason"])

    def test_an_initialized_mpfb_without_weburls_reports_that_specifically(self) -> None:
        self._inject_mpfb()

        result = self._run()

        self.assertEqual(result["state"], "ok")
        self.assertFalse(result["weburls_read"])
        self.assertIsNone(result["urls"])
        # Named in full, since this is an unusual install rather than a normal
        # absence and the module name is what somebody would go looking for.
        self.assertEqual(result["weburls_module"], _STUB_WEBURLS)
        self.assertIn(_STUB_WEBURLS, result["reason"])

    def test_a_half_registered_mpfb_still_reads_weburls_if_it_is_there(self) -> None:
        # MPFB imports its UI during register(), so a run that died later can
        # leave the module loaded. Reading one that is already in sys.modules
        # executes nothing, so there is no reason to refuse.
        self._inject_mpfb(contextual_information={"__package__": _STUB_PACKAGE})
        self._inject_weburls(urls.MPFB_URLS)

        result = self._run()

        self.assertEqual(result["state"], "not_initialized")
        self.assertTrue(result["weburls_read"])
        self.assertEqual(result["urls"], dict(urls.MPFB_URLS))
        self.assertIsNone(result["reason"])


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
