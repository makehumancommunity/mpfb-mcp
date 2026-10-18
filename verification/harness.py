# SPDX-License-Identifier: GPL-3.0-or-later

"""
The instrument the smoke run stands on: the tools, what they left behind, and a
report.

**Checks run through the real tool callables**, taken off the server
``build_server()`` builds. A check written as a hand-assembled request would
verify something no MCP client will ever send: a tool module's own validation,
defaulting and coercion is a large part of what is under test here.

**The harness has no private channel into Blender, and that is the point.** It
had one: FR 012 through FR 032 it made its own scene, built in it, snapshotted
twelve ``bpy.data`` collections, deleted what it made and compared - all by
sending Python to an add-on that would ``exec()`` it. The bridge executes
nothing, so that channel has no replacement, and FR 033 chose to rewrite this
instrument on commands that already exist rather than have the bridge grow
instrument-serving ones. **A verification harness is not a reason to reopen the
hole the whole pivot exists to close.**

What that costs is written down rather than absorbed. The scratch scene, the
cleanup and the datablock snapshot are gone; ``mpfb_list_objects`` is the only
window into the scene that remains, so what this module can still see is *the
MakeHuman objects in the current scene, by name and type*, and what it can still
assert is correspondingly narrower. ``verification/README.md`` says so in the
section about what the run deliberately does not check, and says it beside the
consequence a reader actually cares about: **the run now builds in whatever
scene it finds and leaves what it built there.**

Nothing here is unit-tested and nothing here may be imported by ``src/``.
"""

from __future__ import annotations

__all__ = (
    "MUTATING_VERBS",
    "Report",
    "descriptions",
    "diff_objects",
    "main_guard",
    "makehuman_objects",
    "performed_disagreement",
    "results_directory",
    "tools",
)

import json
import os
import sys
import time

from mpfbmcp import build_server

# The verb each mutating tool reports beside the uniform ``performed`` flag
# (FR 014). ``None`` is mpfb_create_human, which has no verb of its own: it
# creates a character or comes back as an error envelope. The batch tools
# have no verb either, only their list of per-entry writes, ``changes``
# (FR 037, R3), which is what the flag is audited against for them.
#
# This is not a second opinion about what "performed" means - the commands
# decide that, on the far side of the socket. It is the audit that would catch
# a command stamping the flag from the wrong variable, which is the one mistake
# the unit tests can miss, because there the verb and the flag are read out of
# the same stub run. Here they are read out of a real Blender.
MUTATING_VERBS = {
    "mpfb_create_human": None,
    "mpfb_create_human_from_preset": "created",
    "mpfb_save_preset": "saved",
    "mpfb_set_macro_details": "recalculated",
    "mpfb_refit_human": "refit_performed",
    "mpfb_set_targets": "changes",
    "mpfb_symmetrize_targets": "changes",
    "mpfb_set_face_units": "changes",
    "mpfb_set_material_settings": "changes",
    "mpfb_save_expression": "saved",
    "mpfb_apply_expressions": "changed",
    "mpfb_add_rig": "added",
    "mpfb_generate_rigify_rig": "generated",
    "mpfb_add_asset": "added",
    "mpfb_remove_asset": "removed",
    "mpfb_set_skin": "applied",
    "mpfb_set_asset_material": "applied",
    "mpfb_set_pose_bones": "changes",
    "mpfb_set_pose_switches": "changes",
    "mpfb_reset_pose": "reset",
}


def performed_disagreement(tool_name: str, envelope: dict) -> str | None:
    """Why ``performed`` and this tool's verb disagree in one answer, or None."""
    if not isinstance(envelope, dict) or envelope.get("status") != "ok":
        return None
    result = envelope.get("result")
    if not isinstance(result, dict):
        return None
    if "performed" not in result:
        return "no 'performed' in the answer"
    performed = result["performed"]
    if not isinstance(performed, bool):
        return "'performed' is {!r}, not a bool".format(performed)
    verb = MUTATING_VERBS[tool_name]
    if verb is None:
        return None
    if verb not in result:
        # Every refusal carries the verb too, so its absence is itself a finding.
        return "no {!r} in the answer beside 'performed'".format(verb)
    expected = bool(result[verb])
    if tool_name == "mpfb_symmetrize_targets" and result.get("dry_run"):
        # The one tool whose verb is deliberately not the flag: a dry run lists
        # the changes it would make and writes none of them.
        expected = False
    if performed != expected:
        return "performed={!r} but {}={!r} (dry_run={!r})".format(
            performed, verb, result[verb], result.get("dry_run"))
    return None


def _registered() -> list:
    """The tools of the server ``main()`` runs, not a re-registration of them.

    ``build_server()`` is what an MCP client connects to, so asking it is what
    makes "called the way a client would call it" true rather than nearly true -
    and its descriptions are the dedented ones the client downloads, which is
    what the smoke run holds each item's contract keys to.
    """
    server = build_server()
    return list(server._tool_manager.list_tools())  # noqa: SLF001


def tools() -> dict:
    """Every MCP tool, by name, as the plain callable behind the coroutine.

    This is the same route ``tests/`` takes into a tool, and it is what FR 023's
    coverage rule is measured against: the smoke run asks this for the set of
    registered tools and fails if any of them has no item.
    """
    return {tool.name: tool.fn for tool in _registered()}


def descriptions() -> dict:
    """Every tool's description, by name - the contract an MCP client downloads."""
    return {tool.name: tool.description or "" for tool in _registered()}


def makehuman_objects(tool_callables: dict) -> dict:
    """The MakeHuman objects in the current scene, by name, with their type.

    **This is the whole of the harness's view of Blender**, and it is a tool
    call rather than a probe: ``mpfb_list_objects`` is the only command in the
    bridge's vocabulary that reports what is in the scene. So what a before/after
    comparison here can see is MakeHuman objects and nothing else - not meshes,
    materials, images, node groups, actions or collections, and not
    ``bpy.data.is_dirty``.

    Raises on an error envelope. A listing that failed is a broken instrument
    rather than a failed check, and the two must not be able to look alike in a
    report.
    """
    envelope = tool_callables["mpfb_list_objects"]()
    if envelope.get("status") != "ok":
        raise RuntimeError("the harness could not list the scene's objects: {}".format(
            envelope.get("message")))
    return {entry["name"]: entry.get("object_type")
            for entry in envelope["result"].get("objects") or []}


def diff_objects(before: dict, after: dict) -> dict:
    """What the run added to the scene and what disappeared from under it.

    Two questions rather than one, because after FR 033 only the second has an
    answer the run can insist on. **Nothing may disappear**: every MakeHuman
    object that was in the scene before the run must still be there, since no
    tool the run calls is entitled to remove one it did not create. What was
    *added* is reported rather than asserted against zero - the run no longer
    cleans up, so a non-empty ``added`` is the expected outcome and naming its
    contents is the point.
    """
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    return dict(
        added=[dict(name=name, object_type=after[name]) for name in added],
        removed=[dict(name=name, object_type=before[name]) for name in removed],
        nothing_disappeared=not removed,
    )


def results_directory() -> str:
    """Where the run writes its full result: the printed line is capped, the file
    is not. Defaulting it outside the repository is deliberately *not* done -
    unlike FR 012's per-call record, a run result is pass/fail lines about this
    package rather than diagnostics about the user's machine."""
    return os.environ.get("MPFB_MCP_VERIFICATION_RESULTS",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))


class Report:
    """The run: a pass/fail/skip line per item, with the observed value and a time.

    There are three outcomes and not two. ``skip`` is a first-class result
    carrying the reason the item could not be reached, and the summary names
    every skipped item rather than only counting it: twenty passes and four
    skips must not be presentable as twenty-four passes. The per-item duration
    is kept because the sixty-second target is watched rather than enforced, so
    it has to be visible on every run.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.results = []
        self._started = time.perf_counter()
        print("\n=== {} ===".format(name), flush=True)

    def check(self, item: str, passed: bool, observed: object = None,
              elapsed: float = 0.0) -> bool:
        self.results.append(dict(item=item, outcome="pass" if passed else "fail",
                                 observed=observed, elapsed=elapsed))
        print("[{}] {}{}{}".format(
            "x" if passed else " ", item, _elapsed_prefix(elapsed),
            _observed_suffix(observed)), flush=True)
        return passed

    def skip(self, item: str, reason: str, elapsed: float = 0.0) -> bool:
        self.results.append(dict(item=item, outcome="skip", observed=reason, elapsed=elapsed))
        print("[-] {} -- SKIPPED: {}".format(item, reason), flush=True)
        return False

    def note(self, text: str) -> None:
        """An observation that is not itself a check. Kept out of the counts."""
        print("    . {}".format(text), flush=True)

    def summary(self, target_seconds: float | None = None) -> dict:
        total = time.perf_counter() - self._started
        counts = dict(passed=0, failed=0, skipped=0)
        for result in self.results:
            counts["passed" if result["outcome"] == "pass" else
                   "failed" if result["outcome"] == "fail" else "skipped"] += 1
        counts["seconds"] = total
        counts["results"] = self.results

        print("\n--- {}: {} passed, {} failed, {} skipped, {:.1f}s".format(
            self.name, counts["passed"], counts["failed"], counts["skipped"], total), flush=True)
        for result in self.results:
            if result["outcome"] == "fail":
                print("    FAILED: {}".format(result["item"]), flush=True)
        for result in self.results:
            if result["outcome"] == "skip":
                print("    not exercised: {} -- {}".format(
                    result["item"], result["observed"]), flush=True)
        slowest = sorted(self.results, key=lambda r: -r["elapsed"])[:3]
        print("    slowest: {}".format(", ".join(
            "{} {:.1f}s".format(result["item"], result["elapsed"])
            for result in slowest if result["elapsed"])), flush=True)
        if target_seconds is not None and total > target_seconds:
            # Over target is a prompt to look, never a failure: the number being
            # measured is somebody else's Blender. A run that used to take most
            # of a minute now takes a few seconds, so going over target is a
            # much louder signal than it was, and the likeliest cause is the
            # install rather than this package - a cold asset library, or MPFB
            # rebuilding a cache the first call touches.
            print("    over the {:.0f}s target. That is roughly ten times the run's own "
                  "measured cost, so look at the install - a cold asset scan is the usual "
                  "answer. This does not fail the run.".format(target_seconds), flush=True)
        self._write(counts)
        return counts

    def _write(self, counts: dict) -> None:
        """Persist the full result. Best-effort: a report that cannot be written
        must not take the run down with it."""
        try:
            directory = results_directory()
            os.makedirs(directory, exist_ok=True)
            slug = "".join(character if character.isalnum() else "_"
                           for character in self.name.split(" - ")[0]).strip("_").lower()
            path = os.path.join(directory, "{}.json".format(slug))
            handle = open(path, "w", encoding="utf-8")
            json.dump(dict(name=self.name, counts=counts), handle, indent=1, default=repr)
            handle.close()
            print("    -> {}".format(path), flush=True)
        except OSError as error:  # noqa: BLE001 - the printed report is the product
            print("    (could not write result: {})".format(error), flush=True)


def _elapsed_prefix(elapsed: float) -> str:
    return "" if not elapsed else " ({:.1f}s)".format(elapsed)


def _observed_suffix(observed: object) -> str:
    if observed is None:
        return ""
    text = observed if isinstance(observed, str) else json.dumps(observed, default=repr)
    if len(text) > 600:
        text = text[:600] + " ..."
    return " -- " + text


def main_guard(function) -> int:
    """Run one script, reporting a broken instrument differently from a fail."""
    try:
        counts = function()
    except Exception as exception:  # noqa: BLE001 - the report is the product
        print("\n!!! harness error: {}: {}".format(type(exception).__name__, exception),
              file=sys.stderr, flush=True)
        raise
    return 1 if counts.get("failed") else 0
