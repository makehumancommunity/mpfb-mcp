# SPDX-License-Identifier: GPL-3.0-or-later

"""
The two properties of the smoke run that have to be verified by making them fail.

FR 023's Tests section asks for exactly this, and the reason is FR 013's: a
coverage rule and a skip path that have only ever been observed passing have not
been observed at all. Both are provoked here rather than described.

1. **FR-1's coverage check.** A tool the server registers with no smoke item
   must stop the run. Provoked by registering a twenty-first tool the item table
   has never heard of, and by removing an item from the table - the rule has two
   directions and both are checked.

2. **FR-6's skip path.** An install lacking a prerequisite must report the
   affected tools as ``skipped`` with a reason, must still pass, and must name
   every one of them in the summary. Provoked by making the asset catalogue
   answer empty, which is what an install with no MHCLO assets and no skins
   looks like from here.

This script is **this effort's own check and lives with this effort**, which is
the rule FR-10 writes into feature-requests/CLAUDE.md: an exhaustive live check
belongs to the request that needs it and goes to ``done/`` with it. It is not in
``verification/``, and adding it there would be the pivot undoing itself.

The coverage half needs no Blender. The skip half does, because the point is
that the run *completes* and passes with items skipped.

Run from the repository root::

    PYTHONPATH=. python3 feature-requests/023-verification-smoke-test/check_negatives.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys

from verification import fixtures, harness, smoke
from verification.harness import Report


def run() -> dict:
    report = Report("FR 023 - the two properties verified by making them fail")
    _check_extra_tool_fails_the_run(report)
    _check_missing_item_fails_the_run(report)
    _check_unknown_tool_fails_the_run(report)
    _check_empty_catalogue_skips_and_passes(report)
    return report.summary()


def _check_extra_tool_fails_the_run(report: Report) -> None:
    """A registered tool with no item stops the run with exit code 2."""
    real_tools = harness.tools

    def tools_with_an_extra_one() -> dict:
        resolved = real_tools()
        resolved["mpfb_unregistered_newcomer"] = lambda: dict(status="ok", result=dict())
        return resolved

    harness.tools = tools_with_an_extra_one
    try:
        counts = smoke.run()
    finally:
        harness.tools = real_tools
    report.check("a tool with no smoke item fails the run",
                 counts.get("exit_code") == 2 and counts.get("failed"),
                 dict(exit_code=counts.get("exit_code"), failed=counts.get("failed")))


def _check_missing_item_fails_the_run(report: Report) -> None:
    """The other direction: an item removed from the table is caught too."""
    dropped = smoke.ITEMS.pop()
    try:
        errors = smoke.coverage_errors(set(harness.tools()))
    finally:
        smoke.ITEMS.append(dropped)
    report.check("a tool whose item was removed is named as uncovered",
                 any(dropped["tool"] in error and "no smoke item" in error
                     for error in errors), errors)


def _check_unknown_tool_fails_the_run(report: Report) -> None:
    """An item naming a tool the server does not register is likewise a failure."""
    smoke.ITEMS.append(dict(tool="mpfb_tool_that_went_away", keys=(), call=lambda run: None))
    try:
        errors = smoke.coverage_errors(set(harness.tools()))
    finally:
        smoke.ITEMS.pop()
    report.check("an item for a tool that is not registered is named",
                 any("mpfb_tool_that_went_away" in error and "not registered" in error
                     for error in errors), errors)


def _check_empty_catalogue_skips_and_passes(report: Report) -> None:
    """An install with no assets skips five tools by name and still passes."""
    real_first_asset = fixtures.first_asset
    fixtures.first_asset = lambda tools, asset_subdir: None
    try:
        counts = smoke.run()
    finally:
        fixtures.first_asset = real_first_asset

    skips = [result for result in counts["results"] if result["outcome"] == "skip"]
    # Only the per-tool items; the traceback item skips too when
    # MPFB_MCP_RECORD_DIR is unset, which is its own documented behaviour.
    tool_skips = sorted(result["item"] for result in skips if result["item"].startswith("mpfb_"))
    expected = sorted(["mpfb_add_asset", "mpfb_set_skin", "mpfb_list_asset_materials",
                       "mpfb_set_asset_material", "mpfb_remove_asset"])
    report.check("an install with no assets skips exactly the tools that needed one",
                 tool_skips == expected, dict(skipped=tool_skips, expected=expected))
    report.check("every skip carries a reason",
                 all(result["observed"] for result in skips),
                 [result["observed"] for result in skips])
    report.check("the run still passes, and a skip is never counted as a pass",
                 counts.get("exit_code") == 0 and not counts["failed"]
                 and counts["skipped"] == len(skips)
                 and counts["passed"] + counts["skipped"] == len(counts["results"]),
                 dict(exit_code=counts.get("exit_code"), passed=counts["passed"],
                      failed=counts["failed"], skipped=counts["skipped"]))


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
