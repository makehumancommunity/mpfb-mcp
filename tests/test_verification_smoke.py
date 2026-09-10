# SPDX-License-Identifier: GPL-3.0-or-later

"""
The smoke run's coverage rule, asserted without a Blender.

[FR 023](../feature-requests/done/023-verification-smoke-test/README.md) makes
``verification/smoke.py`` fail when a registered tool has no smoke item. That is
the mechanism which bounds the live check's growth, and it is a real check - but
it only fires when somebody has a Blender running, which is late. Everything it
needs is on this side of the socket: the built server knows which tools it
registers, and the item table is a list of dicts.

Two things are asserted here and nothing else. **Coverage** - one item per
registered tool, no item for a tool that is not registered - and that **every
contract key an item checks for is named by the tool's own description**, which
is what keeps that tuple from becoming a private second copy of the contract.
Both are properties of the table rather than of a running MPFB, so a missing
smoke item shows up in the nine-second unit run rather than in a live session.

``unittest discover -s tests`` does not reach ``verification/``, so the module is
imported by path from the repository root. That import must not touch a socket,
and does not: ``smoke.py`` builds its item table at import time and contacts
Blender only from ``run()``.
"""

from __future__ import annotations

__all__ = ("VerificationSmokeCoverageTests",)

import importlib.util
import os
import sys
import unittest

_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _smoke_module():
    """``verification/smoke.py``, imported by path rather than as a package sibling."""
    path = os.path.join(_REPOSITORY_ROOT, "verification", "smoke.py")
    if _REPOSITORY_ROOT not in sys.path:
        # smoke.py imports `verification.harness` and `verification.fixtures`.
        sys.path.insert(0, _REPOSITORY_ROOT)
    specification = importlib.util.spec_from_file_location("verification.smoke", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class VerificationSmokeCoverageTests(unittest.TestCase):

    def setUp(self) -> None:
        from mpfbmcp import build_server  # pylint: disable=import-outside-toplevel
        self.smoke = _smoke_module()
        self.registered = {tool.name: tool
                           for tool in build_server()._tool_manager.list_tools()}  # noqa: SLF001

    def test_every_registered_tool_has_exactly_one_smoke_item(self):
        self.assertEqual([], self.smoke.coverage_errors(set(self.registered)))

    def test_a_tool_with_no_item_is_reported(self):
        errors = self.smoke.coverage_errors(set(self.registered) | {"mpfb_newcomer"})
        self.assertEqual(["mpfb_newcomer is registered but has no smoke item"], errors)

    def test_an_item_for_an_unregistered_tool_is_reported(self):
        one_short = set(self.registered) - {"mpfb_get_status"}
        self.assertEqual(["mpfb_get_status has a smoke item but is not registered"],
                         self.smoke.coverage_errors(one_short))

    def test_every_contract_key_is_named_by_the_tools_own_description(self):
        # The description is what an MCP client downloads, so it is the contract
        # a smoke item's `keys` tuple is held to. A key nobody promises any more
        # must not go on being checked for.
        self.smoke._DESCRIPTIONS = {  # noqa: SLF001
            name: tool.description or "" for name, tool in self.registered.items()}
        unnamed = dict()
        for item in self.smoke.ITEMS:
            named = self.smoke._keys_the_tool_names(item["tool"])  # noqa: SLF001
            missing = [key for key in item["keys"] if key not in named]
            if missing:
                unnamed[item["tool"]] = missing
        self.assertEqual(dict(), unnamed)

    def test_every_item_checks_at_least_one_contract_key(self):
        # An item with no keys would pass on any answer at all, including an
        # empty one, which is not one of FR-3's three assertions.
        self.assertEqual([], [item["tool"] for item in self.smoke.ITEMS if not item["keys"]])


if __name__ == "__main__":
    unittest.main()
