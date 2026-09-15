# SPDX-License-Identifier: GPL-3.0-or-later

"""
The preloaded tool surface, measured and capped.

An MCP client downloads every tool's description and parameter schema before
any work happens, so the twenty-five docstrings in ``src/mpfbmcp/tools/`` are a
call-time cost paid by every session whether or not a tool is used.
[FR 013](../feature-requests/done/013-live-verification/review.md) measured it
for the first time and found 66.7 KB of descriptions against an estimate of
58.5 KB - it had grown unnoticed across five requests, because nothing counted
it. This module counts it.

The ceiling below is what keeps the number from drifting silently again. It is
deliberately close to the current total rather than generous: a ceiling with
room in it is a ceiling that gets filled. Raising it is a decision, and the
right way to make it is to raise it here in the same commit as the docstring
that needs the space.

What this cannot test is whether a description is any *good*. Nothing on this
side of the socket can, which is why
[FR 016](../feature-requests/done/016-trim-tool-descriptions/README.md) trimmed
one tool at a time rather than in one pass, and why the rule it applied - a
sentence stays only if a caller with no access to this repository would act
differently for having read it - lives in
[tool-interface.md](../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget)
rather than in an assertion here.

Run as a script to print the per-tool table rather than the assertion::

    python3 tests/test_description_budget.py

Run with::

    python -m unittest tests.test_description_budget -v
"""

from __future__ import annotations

__all__ = ()

import asyncio
import json
import unittest

import mpfbmcp

# The total of every tool's description, in bytes of UTF-8. FR 016 brought the
# measured total from 70,352 to 47,759 - a third of it - by moving rationale into
# specifications/, by shipping the docstrings dedented, and by giving the server
# instructions the conventions every tool was repeating. It stopped there rather
# than at the ~45,000 that request aimed for, because what was left was
# instruction: see FR 016 for what came out, and what was left in on purpose.
# The ceiling leaves about 700 bytes, which is a paragraph - enough that a real
# addition fits and a habit of adding does not.
#
# Raised from 48,500 to 52,200 by
# [FR 024](../feature-requests/done/024-documentation-urls/README.md), which
# added `mpfb_list_urls` and `mpfb_list_docs`. Two new tools cannot be made to
# fit inside a ceiling with 740 B of headroom and a 400 B floor per tool, so the
# request raised it deliberately rather than trimming twenty descriptions to pay
# for two. What keeps that from being a licence: both newcomers came in at 1,981
# and 1,806 B against a 2,387 B per-tool average, because a lookup tool
# instructs about a small static vocabulary and most of what a caller needs is
# visible in the response - and the headroom left over is the same paragraph it
# was before.
#
# Raised from 52,200 to 59,200 by
# [FR 025](../feature-requests/done/025-character-presets/README.md), which added
# `mpfb_list_presets`, `mpfb_save_preset` and `mpfb_create_human_from_preset` -
# 1,885, 2,404 and 2,723 B against a 2,341 B per-tool average. The catalogue one
# came in well under, as a catalogue tool should. The other two did not, and each
# has a reason that is instruction rather than rationale:
# `mpfb_create_human_from_preset` is the only tool in the package with seven
# optional arguments, each of which changes what gets built and none of which a
# caller can discover from a response (the two vocabularies it shares with
# existing tools - rig identifiers, skin models - are named by pointing at those
# tools rather than restated); and `mpfb_save_preset` is the only tool here that
# writes a file nothing can undo. The ceiling moves by roughly what the three
# cost, and the paragraph of headroom stays a paragraph.
DESCRIPTION_CEILING = 59200

# The parameter schemas FastMCP derives from the signatures and annotations.
# Not docstring text, not written by hand, and not what FR 016 was about - but
# it is downloaded with the descriptions, so it is measured beside them and
# capped so that a signature cannot grow the preload unnoticed either. Raised
# from 9,000 to 10,400 by FR 025: `mpfb_create_human_from_preset` alone declares
# eight parameters, seven of them nullable, which is 881 B of `anyOf` - the
# largest schema in the package and the price of the "omitted means use what the
# preset says" idiom it shares with `mpfb_set_macro_details`.
SCHEMA_CEILING = 10400

# Every tool the server registers is expected to describe itself. A zero-byte
# description would otherwise pass every assertion here.
MINIMUM_DESCRIPTION = 400


def measure() -> list[dict[str, object]]:
    """One entry per registered tool, largest description first.

    Measures the server ``mpfbmcp.build_server()`` actually builds rather than a
    list of tools kept here, so a tool registered without being thought about is
    inside the budget rather than outside it.
    """
    tools = asyncio.run(mpfbmcp.build_server().list_tools())
    measured = [
        {
            "name": tool.name,
            "description": tool.description or "",
            "description_bytes": len((tool.description or "").encode("utf-8")),
            "schema_bytes": len(
                json.dumps(tool.inputSchema, separators=(",", ":")).encode("utf-8")),
        }
        for tool in tools
    ]
    measured.sort(key=lambda entry: entry["description_bytes"], reverse=True)
    return measured


def report() -> str:
    """The table a human reads: per tool, then the totals against the ceilings."""
    measured = measure()
    lines = ["{:>8s} {:>8s}  {:s}".format("desc", "schema", "tool")]
    for entry in measured:
        lines.append("{:8d} {:8d}  {:s}".format(
            entry["description_bytes"], entry["schema_bytes"], entry["name"]))
    descriptions = sum(entry["description_bytes"] for entry in measured)
    schemas = sum(entry["schema_bytes"] for entry in measured)
    lines.append("")
    lines.append("{:d} tools, {:d} B of descriptions (ceiling {:d}) plus {:d} B of "
                 "parameter schemas (ceiling {:d}) = {:d} B preloaded".format(
                     len(measured), descriptions, DESCRIPTION_CEILING,
                     schemas, SCHEMA_CEILING, descriptions + schemas))
    return "\n".join(lines)


class DescriptionBudgetTests(unittest.TestCase):

    def setUp(self) -> None:
        self.measured = measure()

    def test_every_registered_tool_is_measured(self) -> None:
        self.assertEqual(25, len(self.measured))

    def test_total_description_size_is_under_the_ceiling(self) -> None:
        total = sum(entry["description_bytes"] for entry in self.measured)
        self.assertLessEqual(
            total, DESCRIPTION_CEILING,
            "tool descriptions total {:d} B, over the {:d} B ceiling. Move rationale into "
            "specifications/ rather than raising this, or raise it deliberately and say "
            "why in the commit.".format(total, DESCRIPTION_CEILING))

    def test_total_parameter_schema_size_is_under_the_ceiling(self) -> None:
        total = sum(entry["schema_bytes"] for entry in self.measured)
        self.assertLessEqual(total, SCHEMA_CEILING)

    def test_every_tool_describes_itself(self) -> None:
        for entry in self.measured:
            self.assertGreaterEqual(
                entry["description_bytes"], MINIMUM_DESCRIPTION, entry["name"])

    def test_every_description_names_the_response_field_carrying_the_answer(self) -> None:
        """FR-2: a caller must be able to see what to read, not only what to send.

        The check is deliberately weak - it asserts that a description mentions
        ``result`` and at least one backtick-quoted field name - because the
        strong version is a judgement no assertion can make. It fails on the one
        regression it can see: a trim that removes the response section.
        """
        for entry in self.measured:
            self.assertIn("result", entry["description"], entry["name"])
            self.assertIn("`", entry["description"], entry["name"])


if __name__ == "__main__":
    print(report())
