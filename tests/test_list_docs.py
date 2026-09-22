# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_list_docs tool: URL construction, filtering, and partiality.

Entirely on this side of the socket, and uniquely so - this is the one tool in
the package with no bridge command and no Blender behind it, so
there is no second layer here and no stub scene. What that leaves worth testing
is exactly three things:

- **the URLs are built from ``path``, not stored beside it**, which is what
  makes ``tree_url`` consistent with the entries under it and removes two of
  every three chances to mistype an address;
- **the filters**, including the one shape a filter must never take: an unknown
  ``topic`` matching nothing while ``topic_recognized`` says why;
- **the answer never reads as the whole tree.** ``curated``,
  ``tree_document_count`` and ``tree_url`` are present on every answer, filtered
  or not, because a short list read as complete is what this table's whole
  design is trying to prevent.

Whether the curated paths still name files that exist in mpfb2 is a different
question, and it cannot be answered from a table that was copied by hand -
``tests/test_reference_drift.py`` asks it of a sibling checkout when there is
one.

Run with::

    python -m unittest tests.test_list_docs -v
"""

from __future__ import annotations

__all__ = ()

import unittest

from mcp.server.fastmcp import FastMCP

from mpfbmcp.reference import docs
from mpfbmcp.tools import list_docs


def _register_and_get_tool():
    mcp = FastMCP("test")
    list_docs.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_docs"].fn  # noqa: SLF001


class ListDocsTests(unittest.TestCase):

    def setUp(self) -> None:
        self.mpfb_list_docs = _register_and_get_tool()

    def _call(self, **arguments) -> dict:
        envelope = self.mpfb_list_docs(**arguments)
        self.assertEqual(envelope["status"], "ok")
        return envelope["result"]

    def test_an_unfiltered_call_returns_the_whole_curated_table(self) -> None:
        result = self._call()

        self.assertEqual(result["count"], len(docs.DOCUMENTS))
        self.assertEqual(result["curated_document_count"], len(docs.DOCUMENTS))
        self.assertEqual(len(result["documents"]), len(docs.DOCUMENTS))

    def test_every_answer_says_it_is_partial_and_where_the_rest_is(self) -> None:
        # On the unfiltered call too, which is the one most likely to be read as
        # complete: eighteen of eighteen looks whole, eighteen of 105 does not.
        for arguments in (dict(), dict(topic="services"), dict(keyword="rig"),
                          dict(topic="nonexistent")):
            with self.subTest(arguments=arguments):
                result = self._call(**arguments)
                self.assertIs(result["curated"], True)
                self.assertEqual(result["tree_document_count"], docs.TREE_DOCUMENT_COUNT)
                self.assertEqual(result["tree_url"], docs.TREE_URL)
                self.assertLess(result["curated_document_count"],
                                result["tree_document_count"])

    def test_urls_are_built_from_the_path_rather_than_stored(self) -> None:
        entry = self._by_path()["docs/services/humanservice.md"]

        self.assertEqual(
            entry["raw_url"],
            "https://raw.githubusercontent.com/makehumancommunity/mpfb2/master/"
            "docs/services/humanservice.md")
        self.assertEqual(
            entry["page_url"],
            "https://github.com/makehumancommunity/mpfb2/blob/master/"
            "docs/services/humanservice.md")

    def test_every_entry_gets_both_addresses_and_they_agree_with_the_tree(self) -> None:
        result = self._call()

        for entry in result["documents"]:
            with self.subTest(path=entry["path"]):
                # The rule, applied to every row: one stored string, two built
                # from it, both under the tree the response points at.
                self.assertTrue(entry["path"].startswith("docs/"))
                self.assertTrue(entry["raw_url"].endswith(entry["path"]))
                self.assertTrue(entry["page_url"].endswith(entry["path"]))
                self.assertIn(docs.REF, entry["raw_url"])
                self.assertIn(docs.REPOSITORY, entry["page_url"])

    def test_the_ref_is_reported_because_it_pins_what_a_document_describes(self) -> None:
        result = self._call()

        self.assertEqual(result["ref"], "master")
        self.assertEqual(result["repository"], "makehumancommunity/mpfb2")

    def test_filtering_by_topic_is_exact_and_case_insensitive(self) -> None:
        lowercase = self._call(topic="fileformats")
        uppercase = self._call(topic="FileFormats")

        self.assertEqual(lowercase["documents"], uppercase["documents"])
        self.assertTrue(lowercase["documents"])
        for entry in lowercase["documents"]:
            self.assertEqual(entry["topic"], "fileformats")
        self.assertTrue(lowercase["topic_recognized"])
        self.assertEqual(lowercase["requested_topic"], "fileformats")

    def test_an_unknown_topic_answers_empty_rather_than_failing(self) -> None:
        result = self._call(topic="services-ish")

        # The distinction the flag exists for: "no such topic" and "that topic
        # is empty" would otherwise be one indistinguishable empty list.
        self.assertEqual(result["documents"], [])
        self.assertFalse(result["topic_recognized"])
        self.assertEqual(result["known_topics"], list(docs.TOPICS))

    def test_filtering_by_keyword_searches_title_description_keywords_and_path(self) -> None:
        by_keyword = self._call(keyword="mhclo")
        paths = {entry["path"] for entry in by_keyword["documents"]}

        # Named in the path and title of one document, and in the description or
        # keywords of others - all of which must match.
        self.assertIn("docs/fileformats/mhclo.md", paths)
        self.assertIn("docs/services/clothesservice.md", paths)
        self.assertEqual(by_keyword["count"], len(by_keyword["documents"]))
        self.assertEqual(by_keyword["requested_keyword"], "mhclo")

    def test_a_keyword_matches_case_insensitively(self) -> None:
        self.assertEqual(self._call(keyword="RIGIFY")["documents"],
                         self._call(keyword="rigify")["documents"])

    def test_topic_and_keyword_are_applied_together(self) -> None:
        both = self._call(topic="services", keyword="rig")

        self.assertTrue(both["documents"])
        for entry in both["documents"]:
            self.assertEqual(entry["topic"], "services")
        self.assertLess(both["count"], self._call(keyword="rig")["count"])

    def test_a_keyword_matching_nothing_returns_an_empty_list_not_everything(self) -> None:
        result = self._call(keyword="quaternion slerp cache")

        self.assertEqual(result["documents"], [])
        self.assertEqual(result["count"], 0)
        # Still says it was curated, so an empty answer sends the caller to the
        # tree rather than to a conclusion.
        self.assertIs(result["curated"], True)

    def test_the_returned_keywords_are_a_copy_the_caller_cannot_corrupt(self) -> None:
        # The table is module-level and every call reads it, so handing out the
        # stored list would let one caller's mutation reach the next one.
        first = self._call()["documents"][0]
        first["keywords"].append("injected")

        self.assertNotIn("injected", self._call()["documents"][0]["keywords"])

    def test_a_non_string_filter_is_rejected_locally(self) -> None:
        for argument in ("topic", "keyword"):
            with self.subTest(argument=argument):
                with self.assertRaises(ValueError):
                    self.mpfb_list_docs(**{argument: 7})

    def test_an_empty_filter_is_rejected_rather_than_read_as_omitted(self) -> None:
        # An explicitly empty value and an omitted one arise from different
        # mistakes, so the empty one is never quietly treated as the omission.
        for argument in ("topic", "keyword"):
            for value in ("", "   "):
                with self.subTest(argument=argument, value=value):
                    with self.assertRaises(ValueError):
                        self.mpfb_list_docs(**{argument: value})

    def _by_path(self) -> dict:
        return {entry["path"]: entry for entry in self._call()["documents"]}


class CuratedTableTests(unittest.TestCase):
    """The table itself, independent of the tool that filters it."""

    def test_every_document_carries_prose_and_a_known_topic(self) -> None:
        for document in docs.DOCUMENTS:
            with self.subTest(path=document["path"]):
                self.assertIn(document["topic"], docs.TOPICS)
                self.assertTrue(document["title"])
                self.assertTrue(document["description"])
                self.assertTrue(document["keywords"])

    def test_no_path_appears_twice(self) -> None:
        paths = [document["path"] for document in docs.DOCUMENTS]
        self.assertEqual(len(paths), len(set(paths)))

    def test_the_table_stays_a_curation(self) -> None:
        # FR-7's own bound: much past twenty-five and this has stopped being a
        # selection, and requirement 7 should be revisited rather than the
        # number quietly raised.
        self.assertLessEqual(len(docs.DOCUMENTS), 25)
        self.assertLess(len(docs.DOCUMENTS), docs.TREE_DOCUMENT_COUNT)


if __name__ == "__main__":
    unittest.main()
