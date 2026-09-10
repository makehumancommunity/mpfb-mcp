# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 024's live check: is MPFB's ``ui.weburls`` really there, and does the fallback work?

Two claims, and neither can be established on this side of the socket.

**One: ``<root>.ui.weburls`` is in ``sys.modules`` on a normally installed and
initialized MPFB.** The whole design of ``mpfb_list_urls`` rests on it - the
payload reads the module out of ``sys.modules`` and never imports it, because
importing MPFB submodules runs code with side effects. ``tests/test_list_urls.py``
executes the payload against a stub ``sys.modules`` carrying exactly such a
module, which is to say it is built out of the assumption under test and can
never check it. Only a running Blender can.

**Two: a real transport failure produces the fallback answer**, rather than the
error envelope every other tool in the package produces. The unit suite raises
``ConnectionError`` from a mock; here the socket really is refused, so the whole
path through ``connection.send_code()`` is exercised, observability included.

Beside the two, the script prints the constants MPFB actually publishes against
the ones ``src/mpfbmcp/reference/urls.py`` vendors - which is the same
comparison ``tests/test_reference_drift.py`` makes against a sibling checkout,
made here against the installed extension instead. The two can disagree: the
checkout is whatever is checked out, and the extension is whatever is installed.

**This is this effort's own check and lives with this effort**, per
[feature-requests/CLAUDE.md](../../CLAUDE.md). It is not in ``verification/``;
what FR 024 adds there is one smoke item per tool and no new file.

Requires a running Blender with MPFB and the blender_mcp add-on, as
``verification/`` does. Run from the repository root::

    PYTHONPATH=. python3 feature-requests/024-documentation-urls/check_weburls.py
"""

from __future__ import annotations

__all__ = ("run",)

import os
import sys

from mpfbmcp.reference import urls
from verification import harness
from verification.harness import Report

# The probe that answers claim one. Deliberately does its own sys.modules scan
# rather than reusing the payload's: a probe that shares an implementation with
# the thing it is checking cannot contradict it.
_WEBURLS_PROBE = """
import sys

_names = [name for name in list(sys.modules) if name.endswith("mpfb")]
result = {"candidates": _names, "root": None, "weburls_module": None,
          "weburls_in_sys_modules": False, "constants": None,
          "loaded_ui_modules": None, "weburls_file": None}

if _names:
    _root = _names[0]
    result["root"] = _root
    _module_name = _root + ".ui.weburls"
    result["weburls_module"] = _module_name
    _weburls = sys.modules.get(_module_name)
    result["weburls_in_sys_modules"] = _weburls is not None
    # How many of MPFB's UI modules are loaded at all, as context for a miss:
    # if weburls is absent and so is everything else under .ui., the diagnosis
    # is that the UI never registered rather than that this module is special.
    result["loaded_ui_modules"] = len(
        [name for name in list(sys.modules) if name.startswith(_root + ".ui.")])
    if _weburls is not None:
        result["weburls_file"] = getattr(_weburls, "__file__", None)
        result["constants"] = dict(
            [(name, getattr(_weburls, name)) for name in sorted(dir(_weburls))
             if name.startswith("URL_") and isinstance(getattr(_weburls, name), str)])
"""


def run() -> dict:
    report = Report("FR 024 - MPFB's weburls module, read live")
    tools = harness.tools()

    observed = _check_the_module_is_loaded(report)
    _check_the_tool_reads_it(report, tools, observed)
    _check_the_vendored_copy_matches(report, observed)
    _check_an_unreachable_blender_still_answers(report, tools)
    _check_the_docs_tool_needs_nothing(report, tools)

    return report.summary()


def _check_the_module_is_loaded(report: Report) -> dict:
    """Claim one, asked of Blender directly rather than through the tool."""
    observed = harness.probe("weburls", _WEBURLS_PROBE)

    report.check("MPFB is loaded and its root package was found",
                 bool(observed["root"]), dict(root=observed["root"],
                                              candidates=observed["candidates"]))
    report.check("<root>.ui.weburls is in sys.modules without anything importing it",
                 observed["weburls_in_sys_modules"],
                 dict(module=observed["weburls_module"],
                      file=observed["weburls_file"],
                      loaded_ui_modules=observed["loaded_ui_modules"]))
    constants = observed.get("constants") or dict()
    report.check("it publishes URL_ constants, all of them strings",
                 bool(constants), dict(count=len(constants)))
    for key in sorted(constants):
        report.note("{} = {}".format(key, constants[key]))
    return observed


def _check_the_tool_reads_it(report: Report, tools: dict, observed: dict) -> None:
    """The tool's own answer, against what the probe saw independently."""
    envelope = tools["mpfb_list_urls"]()
    if envelope.get("status") != "ok":
        report.check("mpfb_list_urls answers", False, envelope.get("message"))
        return
    result = envelope["result"]

    report.check("it reports MPFB as the source of truth, not the fallback",
                 result["source_of_truth"] == "mpfb",
                 dict(source_of_truth=result["source_of_truth"],
                      fallback_reason=result["fallback_reason"]))
    report.check("its mpfb_status agrees with the probe",
                 result["mpfb_status"]["weburls_read"] is True
                 and result["mpfb_status"]["weburls_module"] == observed["weburls_module"],
                 result["mpfb_status"])

    reported = {entry["key"]: entry["url"] for entry in result["urls"]
                if entry["source"] == "mpfb"}
    constants = observed.get("constants") or dict()
    report.check("every constant the probe saw is reported, with the same value",
                 reported == constants,
                 dict(probe_only=sorted(set(constants) - set(reported)),
                      tool_only=sorted(set(reported) - set(constants)),
                      disagreeing=sorted(key for key in set(constants) & set(reported)
                                         if constants[key] != reported[key])))

    undescribed = [entry["key"] for entry in result["urls"] if entry["description"] is None]
    report.check("every reported address carries prose of ours",
                 not undescribed,
                 dict(undescribed=undescribed,
                      note="a key here is one MPFB has added since; add it to DESCRIPTIONS"))

    ecosystem = [entry["key"] for entry in result["urls"] if entry["source"] == "mpfb_mcp"]
    report.check("the ecosystem links are carried beside MPFB's and marked as ours",
                 sorted(ecosystem) == sorted(urls.ECOSYSTEM_URLS), dict(keys=sorted(ecosystem)))


def _check_the_vendored_copy_matches(report: Report, observed: dict) -> None:
    """The drift check, made against the *installed* extension.

    tests/test_reference_drift.py makes the same comparison against a sibling
    checkout. This one can disagree with it, and the disagreement is worth
    seeing: the checkout is whatever is checked out and the extension is
    whatever is installed, and mpfb-mcp's users have the latter.
    """
    constants = observed.get("constants") or dict()
    if not constants:
        report.skip("the vendored copy matches the installed MPFB",
                    "no constants were read, so there is nothing to compare")
        return

    differences = []
    for key in sorted(set(constants) | set(urls.MPFB_URLS)):
        if constants.get(key) != urls.MPFB_URLS.get(key):
            differences.append(dict(key=key, installed=constants.get(key),
                                    vendored=urls.MPFB_URLS.get(key)))
    report.check("the vendored copy matches the installed MPFB exactly",
                 not differences,
                 differences or dict(keys=len(constants)))


def _check_an_unreachable_blender_still_answers(report: Report, tools: dict) -> None:
    """Claim two: a real refused socket, not a mocked exception.

    Points the connection at a port nothing is listening on, which is what a
    Blender that is not running looks like. The tool must come back with a
    successful envelope carrying the vendored addresses - it is the only tool
    in the package that may, and the reason is that the download link is the
    answer precisely when nothing is running.
    """
    original = os.environ.get("BLENDER_MCP_PORT")
    # A port in the ephemeral range that nothing should be bound to. If
    # something is, the check fails loudly rather than passing by accident -
    # the assertions below all require the fallback answer specifically.
    os.environ["BLENDER_MCP_PORT"] = "9"
    try:
        envelope = tools["mpfb_list_urls"]()
    finally:
        if original is None:
            os.environ.pop("BLENDER_MCP_PORT", None)
        else:
            os.environ["BLENDER_MCP_PORT"] = original

    if envelope.get("status") != "ok":
        report.check("an unreachable Blender still produces a successful answer", False,
                     dict(status=envelope.get("status"), message=envelope.get("message")))
        return
    result = envelope["result"]

    report.check("an unreachable Blender still produces a successful answer",
                 result["source_of_truth"] == "builtin_fallback"
                 and result["blender_reachable"] is False
                 and result["mpfb_status"]["state"] == "unreachable",
                 dict(source_of_truth=result["source_of_truth"],
                      state=result["mpfb_status"]["state"],
                      reason=result["fallback_reason"]))
    report.check("the fallback carries every vendored address",
                 {entry["key"] for entry in result["urls"]}
                 == set(urls.MPFB_URLS) | set(urls.ECOSYSTEM_URLS),
                 dict(count=result["count"]))
    report.check("and reports staleness as unknown rather than as agreement",
                 result["fallback_stale"] is None
                 and result["fallback_differences"] is None,
                 dict(fallback_stale=result["fallback_stale"],
                      fallback_differences=result["fallback_differences"]))
    # The confirmation that the port really was refused rather than answered.
    report.check("the reason names the socket failure",
                 "9" in (result["fallback_reason"] or ""),
                 result["fallback_reason"])


def _check_the_docs_tool_needs_nothing(report: Report, tools: dict) -> None:
    """mpfb_list_docs against the same unreachable Blender: it must not notice."""
    original = os.environ.get("BLENDER_MCP_PORT")
    os.environ["BLENDER_MCP_PORT"] = "9"
    try:
        envelope = tools["mpfb_list_docs"]()
    finally:
        if original is None:
            os.environ.pop("BLENDER_MCP_PORT", None)
        else:
            os.environ["BLENDER_MCP_PORT"] = original

    result = envelope.get("result") or dict()
    report.check("mpfb_list_docs answers with no Blender at all",
                 envelope.get("status") == "ok" and result.get("count"),
                 dict(count=result.get("count"), curated=result.get("curated"),
                      tree_document_count=result.get("tree_document_count")))


if __name__ == "__main__":
    sys.exit(1 if run().get("failed") else 0)
