# SPDX-License-Identifier: GPL-3.0-or-later

"""
Has the vendored reference data drifted from the mpfb2 checkout beside it?

``mpfbmcp.reference`` holds two tables copied by hand from another repository: a
copy of MPFB's ``ui/weburls.py``, and a list of paths into mpfb2's ``docs/``
tree. Both go stale silently. MPFB edits a URL, or renames a document, and
nothing in this repository notices - the URL still looks like a URL and the path
still looks like a path, and the failure surfaces as a 404 in front of a user.

Neither can be checked at run time without the network, which
[mpfb-mcp does not use](../specifications/architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on).
But on the machine where this work actually happens there is a checkout of mpfb2
one directory up, and that is enough to check both against the source they were
copied from.

**So these tests skip when it is absent**, which is a new kind here and worth
being explicit about. A skipped test proves nothing, and a suite that silently
proves less on one machine than another is a real cost. It is accepted because
the alternatives are worse: a hard dependency on a sibling checkout would break
the suite everywhere else, and no check at all would leave the drift to be found
by whoever follows a dead link. The check costs nothing where the checkout is
missing and fires where the editing happens - see
[testing.md](../specifications/testing.md#a-test-may-depend-on-a-sibling-checkout-if-it-skips-without-one).

What a failure here means is that ``src/mpfbmcp/reference/`` needs updating, not
that mpfb2 is wrong. The live values always win at run time
(``mpfb_list_urls`` reports the running MPFB's and flags the copy as stale), so
a drifted URL degrades an answer rather than breaking it - but only while MPFB
is reachable, which is exactly the case the vendored copy exists to cover.

Run with::

    python -m unittest tests.test_reference_drift -v
"""

from __future__ import annotations

__all__ = ()

import ast
import os
import unittest

from mpfbmcp.reference import docs, urls

_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MPFB2 = os.path.join(os.path.dirname(_REPOSITORY_ROOT), "mpfb2")
_WEBURLS = os.path.join(_MPFB2, "src", "mpfb", "ui", "weburls.py")
_DOCS = os.path.join(_MPFB2, "docs")

_HAS_CHECKOUT = os.path.isdir(_MPFB2)
_SKIP_REASON = "no sibling mpfb2 checkout at {}".format(_MPFB2)


def _weburls_constants() -> dict[str, str]:
    """Every ``URL_*`` string assigned at module level in MPFB's weburls.py.

    Parsed rather than imported: importing a file out of another repository to
    read two dozen string literals runs whatever else is in it, and this module
    has no business executing mpfb2's code. ``ast`` sees exactly the assignments
    and nothing else.
    """
    with open(_WEBURLS, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=_WEBURLS)

    found = dict()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("URL_"):
                found[target.id] = node.value.value
    return found


@unittest.skipUnless(_HAS_CHECKOUT, _SKIP_REASON)
class VendoredUrlDriftTests(unittest.TestCase):

    def setUp(self) -> None:
        if not os.path.isfile(_WEBURLS):
            self.skipTest("the sibling checkout has no {}".format(_WEBURLS))
        self.live = _weburls_constants()

    def test_the_checkout_actually_yielded_constants(self) -> None:
        # Guards the checks below against passing vacuously: a parse that found
        # nothing would make "no differences" true and meaningless.
        self.assertTrue(self.live, "parsed no URL_ constants out of {}".format(_WEBURLS))

    def test_every_constant_mpfb_publishes_is_vendored_with_the_same_value(self) -> None:
        differences = [
            "{}: mpfb2 has {!r}, reference/urls.py has {!r}".format(
                key, value, urls.MPFB_URLS.get(key))
            for key, value in sorted(self.live.items())
            if urls.MPFB_URLS.get(key) != value]

        self.assertEqual([], differences,
                         "src/mpfbmcp/reference/urls.py has drifted from mpfb2's weburls.py; "
                         "update MPFB_URLS (and DESCRIPTIONS for any new key)")

    def test_nothing_is_vendored_that_mpfb_no_longer_publishes(self) -> None:
        # The other direction, and the one that actually hands out dead links:
        # a constant MPFB removed stays in the copy and is still reported
        # whenever MPFB cannot be read.
        removed = sorted(set(urls.MPFB_URLS) - set(self.live))

        self.assertEqual([], removed,
                         "reference/urls.py vendors constants mpfb2 no longer has")

    def test_an_ecosystem_key_does_not_shadow_one_of_mpfbs(self) -> None:
        # Handled at run time (the live value wins), but a collision means the
        # two tables have grown into each other and should be untangled here.
        self.assertEqual(set(), set(urls.ECOSYSTEM_URLS) & set(self.live))


@unittest.skipUnless(_HAS_CHECKOUT, _SKIP_REASON)
class CuratedDocumentDriftTests(unittest.TestCase):

    def setUp(self) -> None:
        if not os.path.isdir(_DOCS):
            self.skipTest("the sibling checkout has no {}".format(_DOCS))

    def test_every_curated_path_names_a_file_that_exists(self) -> None:
        missing = [document["path"] for document in docs.DOCUMENTS
                   if not os.path.isfile(os.path.join(_MPFB2, document["path"]))]

        self.assertEqual([], missing,
                         "src/mpfbmcp/reference/docs.py names documents mpfb2 does not have; "
                         "they have been renamed or removed")

    def test_the_reported_tree_size_still_matches_the_tree(self) -> None:
        actual = sum(len([name for name in files if name.endswith(".md")])
                     for _root, _dirs, files in os.walk(_DOCS))

        # Not an equality anybody has to chase to the document: the number is
        # reported so a caller can see eighteen-of-many rather than
        # eighteen-of-eighteen, so it has to stay roughly right rather than
        # exactly right. A drift of more than a tenth means the tree has been
        # reorganized and the curation is worth re-reading.
        self.assertAlmostEqual(
            docs.TREE_DOCUMENT_COUNT, actual, delta=max(5, actual // 10),
            msg="reference/docs.py reports {} documents in the tree, which now holds {}".format(
                docs.TREE_DOCUMENT_COUNT, actual))


if __name__ == "__main__":
    unittest.main()
