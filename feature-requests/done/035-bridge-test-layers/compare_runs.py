# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 035's own check: the bridge suite before and after the move is the same suite.

The effort only moves and renames files, so the proof that nothing about what is
tested changed is two saved ``-v`` logs of the bridge suite - one from before
the first ``git mv``, one from after the last edit - compared as the set of
``(module name without its prefix, test function, outcome)``. Directories and
the old three-letter prefix are stripped from each node ID, so
``tests/fff_list_objects_test.py::test_x`` and
``tests/ccc_reading/list_objects_test.py::test_x`` are the same entry.

It also checks the order in the "after" log, which is the point of the effort:
every node ID of one layer comes before any node ID of a later one, and nothing
is collected from outside a layer.

Run once during the effort, from the repository root, on logs written by::

    BLENDER_EXE=... bridge/test/execute_tests_headless.bash > before.log 2>&1
    ...
    python3 feature-requests/done/035-bridge-test-layers/compare_runs.py before.log after.log

Exits non-zero when the sets differ or the order is wrong.
"""

from __future__ import annotations

__all__ = ()

import re
import sys

# ``--capture=tee-sys`` lets a test's own output land between its node ID and its
# outcome, sometimes lines later, so the two are matched separately and paired in
# order rather than expected on one line.
_NODE = re.compile(r"^tests/(?P<path>\S+?\.py)::(?P<test>\S+)", re.MULTILINE)
_OUTCOME = re.compile(r"\b(?P<outcome>PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS) +\[ *\d+%\]")
# Only the old prefix - one letter three times - so that ``get_`` survives.
_PREFIX = re.compile(r"^([a-z])\1\1_")
_LAYERS = ("aaa_addon", "bbb_shared", "ccc_reading", "ddd_mutating", "eee_composite")


def read(log_path):
    """Every result line of a ``pytest -v`` log, in order, as (path, test, outcome)."""
    with open(log_path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    nodes = list(_NODE.finditer(text))
    results = []
    for index, node in enumerate(nodes):
        end = nodes[index + 1].start() if index + 1 < len(nodes) else len(text)
        outcome = _OUTCOME.search(text, node.end(), end)
        results.append((node.group("path"), node.group("test"),
                        outcome.group("outcome") if outcome else "NO_OUTCOME"))
    return results


def normalized(results):
    """The comparable set: module name without directory or prefix, test, outcome."""
    return {(_PREFIX.sub("", path.rsplit("/", 1)[-1]), test, outcome)
            for path, test, outcome in results}


def order_problems(results):
    """What is wrong with the layer order of one run, as readable lines."""
    problems = []
    highest = -1
    for path, test, _outcome in results:
        layer = path.split("/", 1)[0]
        if "/" not in path or layer not in _LAYERS:
            problems.append("{:s}::{:s} is not inside a layer".format(path, test))
            continue
        index = _LAYERS.index(layer)
        if index < highest:
            problems.append("{:s}::{:s} runs after a later layer, {:s}".format(path, test, _LAYERS[highest]))
        highest = max(highest, index)
    return problems


def main(before_path, after_path):
    """Compare two runs; print what differs; return a process exit code."""
    before, after = read(before_path), read(after_path)
    old, new = normalized(before), normalized(after)
    print("before: {:d} results, {:d} distinct".format(len(before), len(old)))
    print("after:  {:d} results, {:d} distinct".format(len(after), len(new)))
    for label, entries in (("only before", old - new), ("only after", new - old)):
        for module, test, outcome in sorted(entries):
            print("{:s}: {:s}::{:s} {:s}".format(label, module, test, outcome))
    for outcome in ("PASSED", "SKIPPED", "FAILED", "ERROR"):
        print("{:s}: before {:d}, after {:d}".format(
            outcome,
            sum(1 for entry in old if entry[2] == outcome),
            sum(1 for entry in new if entry[2] == outcome)))
    problems = order_problems(after)
    for problem in problems:
        print("order: " + problem)
    identical = bool(before) and old == new and len(before) == len(after)
    print("identical: {}".format(identical))
    print("layer order: {:s}".format("ok" if not problems else "WRONG"))
    return 0 if identical and not problems else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: compare_runs.py BEFORE.log AFTER.log")
    sys.exit(main(sys.argv[1], sys.argv[2]))
