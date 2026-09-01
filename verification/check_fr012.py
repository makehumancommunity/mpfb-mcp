# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 012's one outstanding item, and the reason it goes first.

[FR 012](../feature-requests/done/012-observability/README.md) landed with
everything on this side of the socket asserted and one thing it could not
establish: that a traceback line number coming back from a *real* Blender
resolves to the right line of the program the recorder dumped. Nothing in
``tests/`` has ever received a line number from Blender.

Everything else in this session is harder to diagnose until that is confirmed,
which is why FR 013 puts it at step 0. It is confirmed the only way it can be:
by making Blender fail on a line this script chose, and reading the number back.

The failure is deliberate and its program is built the way ``codegen.assemble()``
builds one - the same bootstrap, the same JSON prelude, the same labelled payload
seam, and a real payload file underneath it, so the line number has the same
distance to travel as a real tool's would. It is *not* a real tool call, and the
reason is worth stating: no tool in this package has an uncaught path, which is
the property the package is written for. Editing a payload to raise would test
the same thing while leaving the working tree dirty if the run were interrupted.

Run with::

    MPFB_MCP_RECORD_DIR=~/mpfb-mcp-records python3 verification/check_fr012.py
"""

from __future__ import annotations

__all__ = ("run",)

import json
import os
import re
import sys

from mpfbmcp import codegen
from mpfbmcp.connection import send_code

from verification import harness
from verification.harness import Report

ITEMS = (
    "a traceback line number from a real add-on failure resolves to the dumped program",
    "the error envelope names the two files the record wrote",
    "the index line carries the tool, the byte count, the duration and the status",
    "with the record off, nothing is written and the call still works",
)


def run() -> dict:
    report = Report("FR 012 - observability, the live check it could not make", ITEMS)
    directory = os.environ.get("MPFB_MCP_RECORD_DIR")
    if not directory:
        report.skip("a traceback line number from a real add-on failure resolves to the "
                    "dumped program",
                    "MPFB_MCP_RECORD_DIR is not set, so there is no record to resolve against")
        return report.summary()

    program, expected_line = _program_that_raises()
    response = send_code(program, strict_json=True)

    record = response.get("mpfb_mcp_record") or dict()
    report.check("the error envelope names the two files the record wrote",
                 response.get("status") == "error"
                 and os.path.isfile(record.get("program", ""))
                 and os.path.isfile(record.get("response", "")),
                 dict(status=response.get("status"), record=record))

    reported_line = _line_from(response.get("message") or "")
    dumped = ""
    if record.get("program") and os.path.isfile(record["program"]):
        handle = open(record["program"], "r", encoding="utf-8")
        dumped = handle.read()
        handle.close()
    lines = dumped.split("\n")
    at_reported = lines[reported_line - 1] if reported_line and reported_line <= len(lines) else None

    report.check("a traceback line number from a real add-on failure resolves to the "
                 "dumped program",
                 reported_line == expected_line
                 and at_reported is not None and "MPFB_MCP_DELIBERATE_FAILURE" in at_reported,
                 dict(traceback_line=reported_line, expected_line=expected_line,
                      line_in_the_dumped_program=at_reported,
                      program_bytes=len(dumped.encode("utf-8"))))

    report.check("the index line carries the tool, the byte count, the duration and the "
                 "status",
                 _index_line_ok(record.get("program")),
                 _index_tail(record.get("program")))

    _check_disabled_path(report)
    return report.summary()


def _program_that_raises() -> tuple:
    """A program shaped exactly like an assembled one, raising on a known line.

    ``codegen.assemble()`` is used for everything above the failure, so the
    bootstrap, the JSON prelude and the labelled payload seam are the real ones
    and the line number has the same distance to travel. The raise is appended,
    which is why the expected line is computed rather than written down.
    """
    assembled = codegen.assemble("get_status.py", bootstrap="non_raising", params=dict())
    failure = 'raise RuntimeError("MPFB_MCP_DELIBERATE_FAILURE")\n'
    program = assembled
    if not program.endswith("\n"):
        program = program + "\n"
    program = program + failure
    # The raise is the last line; ``split`` on the trailing newline leaves an
    # empty final element, so the raise is the one before it.
    expected_line = len(program.split("\n")) - 1
    return program, expected_line


def _line_from(message: str) -> int:
    """The last ``File "<string>", line N`` in a traceback: the innermost frame."""
    matches = re.findall(r'File "<string>", line (\d+)', message)
    return int(matches[-1]) if matches else 0


def _index_line_ok(program_path: str) -> bool:
    tail = _index_tail(program_path)
    if not tail:
        return False
    fields = tail.get("last_line", "").split("\t")
    return (len(fields) == 7 and fields[2] == "get_status" and fields[5] == "error"
            and float(fields[4]) > 0.0 and int(fields[3]) > 0)


def _index_tail(program_path: str) -> dict:
    if not program_path:
        return dict()
    index_path = os.path.join(os.path.dirname(program_path), "index.tsv")
    if not os.path.isfile(index_path):
        return dict()
    handle = open(index_path, "r", encoding="utf-8")
    lines = [line.rstrip("\n") for line in handle if line.strip()]
    handle.close()
    return dict(index=index_path, last_line=lines[-1] if lines else "",
                header=lines[0] if lines else "")


def _check_disabled_path(report: Report) -> None:
    """The property the whole design rests on: off means nothing at all."""
    previous = os.environ.pop("MPFB_MCP_RECORD_DIR", None)
    try:
        answer = harness.probe("record_disabled", 'result = dict(alive=True)\n')
        directories_after = sorted(os.listdir(previous)) if previous else []
    finally:
        if previous is not None:
            os.environ["MPFB_MCP_RECORD_DIR"] = previous
    report.check("with the record off, nothing is written and the call still works",
                 answer == dict(alive=True),
                 dict(answer=answer, run_directories=len(directories_after)))


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
