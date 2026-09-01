# SPDX-License-Identifier: GPL-3.0-or-later

"""
Every checklist, in the order where each pays for the next.

The order is FR 013's and it is not arbitrary. FR 012's inherited check goes
first because everything below is harder to diagnose until a traceback's line
number is known to resolve. The two read-only re-checks go next because
FR 009's weights answers and FR 010's ``resolved_path`` are compared against
their output. FR 007 and FR 008 run on an undressed character; FR 010 dresses
one and, in doing so, settles FR 009's ordering claim from the other end and
produces the first live evidence that FR 007's refit does anything; FR 009 and
FR 011 come last.

Each script is also runnable on its own - it builds whatever character its own
items need - so a checklist can be re-run after a fix without re-running the
six around it. That is FR-1's actual requirement, and it is why this file is
short: it sequences, it does not orchestrate.

Run with::

    MPFB_MCP_RECORD_DIR=~/mpfb-mcp-records python3 verification/run_all.py

Add ``--measure`` to take FR-8's cost measurements afterwards; they take a few
minutes and nothing else depends on them.
"""

from __future__ import annotations

__all__ = ("run",)

import json
import sys

from verification import fixtures, harness

CHECKLISTS = (
    ("FR 012", "check_fr012"),
    ("FR 004", "check_fr004"),
    ("FR 005", "check_fr005"),
    ("FR 007", "check_fr007"),
    ("FR 008", "check_fr008"),
    ("FR 010", "check_fr010"),
    ("FR 009", "check_fr009"),
    ("FR 011", "check_fr011"),
)


def run(measure: bool = False) -> int:
    tools = harness.tools()
    harness.ensure_scratch_scene()

    install = fixtures.check_install(tools)
    print("=== install ===", flush=True)
    print(json.dumps(install, indent=1), flush=True)
    missing = [key for key in ("mpfb", "custom_rig", "rigify", "skin")
               if install.get(key) is None]
    missing += ["asset:" + key for key, path in install["paths"].items() if path is None]
    if missing:
        print("\n!!! this install cannot run the session: missing {}".format(
            ", ".join(missing)), file=sys.stderr, flush=True)
        return 2

    totals = dict(passed=0, failed=0, skipped=0, never_run=0)
    per_checklist = dict()
    for label, module_name in CHECKLISTS:
        module = __import__("verification." + module_name, fromlist=["run"])
        counts = module.run()
        per_checklist[label] = dict(
            passed=counts["passed"], failed=counts["failed"],
            skipped=counts["skipped"], never_run=len(counts["never_run"]))
        for key in ("passed", "failed", "skipped"):
            totals[key] += counts[key]
        totals["never_run"] += len(counts["never_run"])

    if measure:
        from verification import measure as measure_module  # pylint: disable=C0415
        measure_module.run()

    print("\n=== session ===", flush=True)
    for label in per_checklist:
        print("{}: {}".format(label, per_checklist[label]), flush=True)
    print("total: {}".format(totals), flush=True)
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    sys.exit(run(measure="--measure" in sys.argv))
