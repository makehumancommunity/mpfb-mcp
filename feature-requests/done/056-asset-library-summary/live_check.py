# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 056's own live check: the summary against the install it was scoped on.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. The bridge's tests ask a real MPFB about a
library they build, of a dozen assets; what they cannot say is how large this answer is on a
real one, or what the first call costs in a Blender with a window, where the previews are
really loaded. Those two claims are what this script is for.

    BLENDER_EXE=/path/to/blender PYTHONPATH=src .venv/bin/python \
        feature-requests/done/056-asset-library-summary/live_check.py

**It changes nothing of the user's.** Every Blender runs with a temporary
``BLENDER_USER_CONFIG`` holding a copy of ``userpref.blend``, on a port the system says is free,
so a Blender already running on the default port is left alone, and the real preferences'
modification time is checked at the end. Every call is the read-only ``mpfb_list_assets``.

The windowed half needs a display, and opens one small window without taking focus. Without a
display it says it did not run and exits non-zero rather than passing.

**A windowed bridge's answer includes its wait for the next timer tick**, up to a second when
Blender has nothing to do (NEXT_STEPS). So a cold call is reported beside the slowest of several
``get_status`` calls: only what is clearly past that is the call's own cost.

Prints PASS/FAIL per check and the measurements, and exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mpfbmcp.bridge_connection import PROTOCOL_VERSION
from mpfbmcp.tools import list_assets

BLENDER = os.environ.get("BLENDER_EXE", "")
HOST = "127.0.0.1"
SUMMARY_CEILING = 8 * 1024
PAGE = 1000

CONFIGURE = r'''
import os, sys, bpy
package = next(n for n in sys.modules if n.endswith(".mpfb_bridge"))
preferences = bpy.context.preferences.addons[package].preferences
preferences.autostart = os.environ["LIVE_AUTOSTART"] == "1"
preferences.port = int(os.environ["LIVE_PORT"])
bpy.ops.wm.save_userpref()
print("BRIDGE_MODULE", package, flush=True)
'''

_failures = 0


def check(name: str, passed: bool, detail: object = "") -> None:
    global _failures  # pylint: disable=global-statement
    _failures += 0 if passed else 1
    print("{:s}  {:s}{:s}".format(
        "PASS" if passed else "FAIL", name, "  [{}]".format(detail) if detail != "" else ""),
        flush=True)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def get_status(port: int, timeout: float = 10.0) -> float:
    """How long one ``get_status`` took on the wire, which nothing but the bridge's tick slows."""
    started = time.perf_counter()
    with socket.create_connection((HOST, port), timeout=timeout) as connection:
        connection.sendall(json.dumps({
            "command": "get_status", "params": {}, "protocol_version": PROTOCOL_VERSION,
        }).encode() + b"\0")
        data = b""
        while not data.endswith(b"\0"):
            chunk = connection.recv(65536)
            if not chunk:
                raise ConnectionError("closed before a full answer")
            data += chunk
    return time.perf_counter() - started


def wait_for_bridge(port: int, deadline: float = 60.0) -> bool:
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        try:
            get_status(port)
            return True
        except (OSError, ConnectionError):
            time.sleep(0.1)
    return False


def tool():
    """The real tool function, which is the path a client's call takes."""
    mcp = FastMCP("live")
    list_assets.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_assets"].fn  # pylint: disable=protected-access


def call(function, **arguments) -> tuple[dict, int, float]:
    """A call's ``result``, how many bytes its envelope is, and how long it took."""
    started = time.perf_counter()
    envelope = function(**arguments)
    seconds = time.perf_counter() - started
    if envelope.get("status") != "ok":
        raise RuntimeError("mpfb_list_assets{!r}: {!r}".format(arguments, envelope))
    return envelope["result"], len(json.dumps(envelope)), seconds


def sweep(function, subdirs: list) -> tuple[list, int, float]:
    """Every row in the library, a subdir and a page at a time, as a session has to."""
    rows, size, seconds = [], 0, 0.0
    for subdir in subdirs:
        offset = 0
        while True:
            answer, bytes_, took = call(function, asset_subdir=subdir, limit=PAGE, offset=offset)
            rows.extend(answer["assets"])
            size += bytes_
            seconds += took
            offset += PAGE
            if not answer["truncated"]:
                break
    return rows, size, seconds


def tally(rows: list) -> dict:
    counts = dict()
    for row in rows:
        key = (row["asset_subdir"], row["pack"], row["license"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def against_the_library(function) -> None:
    """Everything that does not depend on whether Blender has a window."""
    bare, bare_size, bare_seconds = call(function)
    size_of = {"bare call, a summary": bare_size}

    check("a bare call is a summary", bare["summary"] is True and bare["requested_summary"] is None)
    check("it has no rows and nothing was cut",
          bare["assets"] == [] and bare["count"] == 0 and bare["truncated"] is False)
    check("the page's keys are there, as null", bare["offset"] is None and bare["limit"] is None)
    check("the self-correction keys are left out",
          "known_packs" not in bare and "asset_roots_searched" not in bare)
    check("under 8 KB on this install", bare_size < SUMMARY_CEILING,
          "{:d} B, {:d} facets, {:d} assets, {:d} claimed twice, {:d} conflicts".format(
              bare_size, len(bare["facets"]), bare["total_count"], bare["pack_ambiguous_count"],
              len(bare["attribution_conflicts"])))

    rows, sweep_size, sweep_seconds = sweep(function, sorted(bare["counts_by_asset_subdir"]))
    size_of["every subdir at limit=1000, a sweep"] = sweep_size
    check("the sweep found the assets the summary counted",
          len(rows) == bare["total_count"], "{:d} rows".format(len(rows)))
    from_facets = {(facet["asset_subdir"], facet["pack"], facet["license"]): facet["count"]
                   for facet in bare["facets"]}
    check("the facets are the rows, on the real library", from_facets == tally(rows))

    license_ = next(iter(sorted(bare["counts_by_license"], key=bare["counts_by_license"].get,
                                reverse=True)))
    narrowed, narrowed_size, _ = call(function, summary=True, license=license_)
    size_of["summary, license=" + license_] = narrowed_size
    check("a license narrows it",
          narrowed["total_count"] == bare["counts_by_license"][license_]
          and all(facet["license"] == license_ for facet in narrowed["facets"]))

    page, page_size, page_seconds = call(function, summary=False)
    size_of["summary=false, today's bare call"] = page_size
    check("summary=false is 200 rows, of one type", page["count"] == 200
          and {row["asset_subdir"] for row in page["assets"]} == {"clothes"} and page["truncated"])

    empty, empty_size, _ = call(function, limit=0)
    size_of["limit=0"] = empty_size
    check("limit=0 is a page of no rows, without facets", empty["assets"] == []
          and "facets" not in empty and empty["truncated"] and "limit=0" in empty["message"])

    missing, missing_size, _ = call(function, pack="no-such-pack-is-installed")
    size_of["pack not recognised, rows"] = missing_size
    wrong, wrong_size, _ = call(function, summary=True, pack="no-such-pack-is-installed")
    size_of["pack not recognised, summary"] = wrong_size
    check("an unrecognised filter brings the self-correction keys back",
          "known_packs" in wrong and "asset_roots_searched" in wrong and wrong["facets"] == []
          and missing["pack_recognized"] is False)

    print("\nSizes:")
    for name, size in size_of.items():
        print("  {:>9,d} B  {:s}".format(size, name))
    print("\nWarm times: bare {:.0f} ms, summary=false {:.0f} ms, sweep {:.0f} ms".format(
        bare_seconds * 1000, page_seconds * 1000, sweep_seconds * 1000))
    print("Message: {:s}\n".format(bare["message"]))


def cold_call(function, port: int, label: str) -> None:
    """The first summary in this Blender, which scans every subdir, then the second."""
    ticks = [get_status(port) for _ in range(5)]
    _, _, first = call(function)
    _, _, second = call(function)
    print("{:s}: get_status at most {:.0f} ms, first summary {:.0f} ms, second {:.0f} ms".format(
        label, max(ticks) * 1000, first * 1000, second * 1000), flush=True)


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
    process.wait()


def configure(environment: dict, port: int, autostart: bool) -> str:
    out = subprocess.run(
        [BLENDER, "--background", "--python-expr", CONFIGURE],
        env=dict(environment, LIVE_AUTOSTART="1" if autostart else "0", LIVE_PORT=str(port)),
        capture_output=True, text=True, timeout=120, check=True).stdout
    if "BRIDGE_MODULE" not in out:
        raise RuntimeError("The bridge is not enabled in the copied preferences:\n" + out[-2000:])
    return out


def real_userpref() -> Path:
    out = subprocess.run(
        [BLENDER, "--background", "--python-expr",
         "import bpy; print('CONFIG_DIR', bpy.utils.user_resource('CONFIG'), flush=True)"],
        capture_output=True, text=True, timeout=120, check=True).stdout
    marker = out.split("CONFIG_DIR ", 1)[1]
    return Path(marker.splitlines()[0]) / "userpref.blend"


def main() -> int:
    if not BLENDER:
        print("Set BLENDER_EXE to the Blender to check.")
        return 2

    directory = Path(tempfile.mkdtemp(prefix="fr056_"))
    config = directory / "config"
    config.mkdir()
    environment = dict(os.environ, BLENDER_USER_CONFIG=str(config))
    real = real_userpref()
    before = real.stat().st_mtime_ns
    shutil.copy2(real, config / "userpref.blend")
    function = tool()

    try:
        print("--- Headless", flush=True)
        port = free_port()
        configure(environment, port, False)
        with open(directory / "headless.log", "w", encoding="utf-8") as log:
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                [BLENDER, "--background", "--command", "mpfb_bridge", "--port", str(port)],
                env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            check("the headless bridge answers", wait_for_bridge(port))
            os.environ["MPFB_BRIDGE_PORT"] = str(port)
            cold_call(function, port, "Headless")
            against_the_library(function)
        finally:
            stop(process)

        print("--- Windowed", flush=True)
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            check("the windowed half ran", False, "no display here, so it did NOT run")
        else:
            port = free_port()
            configure(environment, port, True)
            with open(directory / "windowed.log", "w", encoding="utf-8") as log:
                process = subprocess.Popen(  # pylint: disable=consider-using-with
                    [BLENDER, "--no-window-focus", "--window-geometry", "0", "0", "640", "480"],
                    env=environment, stdout=log, stderr=subprocess.STDOUT)
            try:
                check("the windowed bridge answers", wait_for_bridge(port))
                os.environ["MPFB_BRIDGE_PORT"] = str(port)
                cold_call(function, port, "Windowed")
            finally:
                stop(process)
    finally:
        print("\n--- Cleanup", flush=True)
        check("the real preferences were not written", real.stat().st_mtime_ns == before, real)
        if _failures:
            print("Logs kept in {:s}".format(str(directory)))
        else:
            shutil.rmtree(directory, ignore_errors=True)

    print("\n{:s}".format("{:d} FAILED".format(_failures) if _failures else "All passed"))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
