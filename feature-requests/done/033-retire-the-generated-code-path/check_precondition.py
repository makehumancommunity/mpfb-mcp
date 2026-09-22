# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 033's requirement 1: refuse to start while any tool still has a payload.

This is the first thing the effort writes and the first thing it runs, and it
needs no Blender: every question it asks is answerable from the registry and
the seam's own table.

**Why a check rather than an assumption.** The deletion this request performs is
irreversible in practice - a payload removed while its tool still needs it is
not caught by any test that survives the same commit, because the test that
would have caught it is deleted in that commit too. So the property FR 032
claims to have established ("every tool that crosses the socket has a bridge
command") is re-established here, mechanically, immediately before it is relied
on.

Three questions, and a tool must answer yes to exactly one of the first two:

1. it has an entry in ``backend.MIGRATED_COMMANDS``, so a bridge command has
   replaced its payload; or
2. it has no payload at all, which is ``mpfb_list_docs`` and is expected to be
   ``mpfb_list_docs`` alone - a *second* payload-free tool appearing here would
   be a tool that had quietly stopped reaching Blender, which is a finding
   rather than a pass.

The third is the mirror image: every entry in ``MIGRATED_COMMANDS`` names a
payload that exists and a tool that is registered, so a table that has drifted
ahead of the package cannot report a clean precondition either.

Run from the repository root::

    PYTHONPATH=src python3 feature-requests/033-retire-the-generated-code-path/check_precondition.py

Exit code 0 means FR 032 is finished and FR 033 may start. Anything else means
it is not, and the answer is to finish FR 032 rather than to continue here.
"""

from __future__ import annotations

__all__ = ("main",)

import os
import sys

from mpfbmcp import backend, build_server

# The one tool that is allowed to have no payload, named rather than counted.
# It answers from a local table, never opens a socket, and has never had a
# payload; anything else landing in this set is a regression to report.
PAYLOAD_FREE_TOOLS = {"mpfb_list_docs"}

_PAYLOADS_DIRECTORY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "mpfbmcp", "codegen",
    "payloads")


def _registered_tool_names() -> set[str]:
    server = build_server()
    return {tool.name for tool in server._tool_manager.list_tools()}  # noqa: SLF001


def _payload_for(tool_name: str) -> str:
    """The payload filename a tool of this name would have.

    The correspondence is the package's own naming rule - ``mpfb_set_skin`` is
    ``codegen/payloads/set_skin.py`` - and it is applied here rather than read
    out of the tool module, because a tool that had stopped naming its payload
    correctly is exactly the case this check exists to notice.
    """
    return tool_name[len("mpfb_"):] + ".py"


def main() -> int:
    problems: list[str] = []
    notes: list[str] = []

    tools = _registered_tool_names()
    migrated = set(backend.MIGRATED_COMMANDS)

    payload_free = set()
    for tool_name in sorted(tools):
        payload = _payload_for(tool_name)
        on_disk = os.path.isfile(os.path.join(_PAYLOADS_DIRECTORY, payload))
        if payload in migrated:
            if not on_disk:
                problems.append(
                    "{:s} is in MIGRATED_COMMANDS but {:s} is not on disk".format(
                        tool_name, payload))
            continue
        if on_disk:
            problems.append(
                "{:s} still has a payload ({:s}) and no bridge command; FR 032 is not "
                "finished".format(tool_name, payload))
            continue
        payload_free.add(tool_name)

    unexpected = payload_free - PAYLOAD_FREE_TOOLS
    if unexpected:
        problems.append(
            "these tools have neither a payload nor a bridge command, and only {:s} may: "
            "{:s}".format(", ".join(sorted(PAYLOAD_FREE_TOOLS)), ", ".join(sorted(unexpected))))
    missing = PAYLOAD_FREE_TOOLS - payload_free
    if missing:
        problems.append(
            "{:s} was expected to have no payload and does not match that "
            "description any more".format(", ".join(sorted(missing))))

    for payload, command in sorted(backend.MIGRATED_COMMANDS.items()):
        tool_name = "mpfb_" + payload[:-len(".py")]
        if tool_name not in tools:
            problems.append(
                "MIGRATED_COMMANDS maps {:s} -> {:s}, but no tool named {:s} is "
                "registered".format(payload, command, tool_name))

    notes.append("{:d} tools registered".format(len(tools)))
    notes.append("{:d} in MIGRATED_COMMANDS".format(len(migrated)))
    notes.append("{:d} with no payload ({:s})".format(
        len(payload_free), ", ".join(sorted(payload_free)) or "-"))

    print("=== FR 033 precondition: every tool that crosses the socket is migrated ===")
    for note in notes:
        print("    . {:s}".format(note))
    if problems:
        for problem in problems:
            print("[ ] {:s}".format(problem))
        print("\n--- NOT startable: finish FR 032 first.")
        return 1
    print("[x] every registered tool has a bridge command or no payload at all")
    print("\n--- startable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
