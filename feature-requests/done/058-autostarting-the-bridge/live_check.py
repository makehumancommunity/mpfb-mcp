# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 058's own live check: starting Blender for real, and signalling the real process.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. The bridge's test suite runs inside a
background Blender, so it cannot reach an event loop, a second instance or a signal
sent from outside; all of those are what this request claims something about.

    BLENDER_EXE=/path/to/blender PYTHONPATH=src .venv/bin/python \
        feature-requests/done/058-autostarting-the-bridge/live_check.py

**It never touches the real preferences.** Every Blender here runs with a temporary
``BLENDER_USER_CONFIG`` holding a copy of ``userpref.blend``, a copy so that a custom
extension repository still resolves, and the real file's modification time is checked
at the end. Every port is one the system says is free, so a Blender already running on
the default ports is left alone. POSIX only, since half of it is about signals.

The windowed half needs a display, and opens a few small windows without taking focus.
Without a display it says it did not run and exits non-zero rather than passing.

Windowed Blenders report through a ``--python`` probe: a persistent timer that writes
what the add-on's own modules say to a JSON file, after doing whatever the case needs.

Prints PASS/FAIL per check, and exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mpfbmcp.bridge_connection import PROTOCOL_VERSION

BLENDER = os.environ.get("BLENDER_EXE", "")
HOST = "127.0.0.1"
LISTENING = re.compile(r"MPFB Bridge listening on (\S+):(\d+) with \d+ commands")

PROBE = r'''
import json, os, sys, addon_utils, bpy

OUT = os.environ["LIVE_PROBE_OUT"]
ACTION = os.environ.get("LIVE_PROBE_ACTION", "")
BLEND = os.environ.get("LIVE_PROBE_BLEND", "")
REPORTS = {}

def package():
    return next(n for n in sys.modules if n.endswith(".mpfb_bridge"))

def module(name):
    return sys.modules[package() + "." + name]

def report(label):
    server = module("command_server")
    ui = module("ui")
    REPORTS[label] = {
        "running": server.is_running(),
        "address": server.bound_address() if server.is_running() else None,
        "last_error": ui._State.last_error,
        "automatically": ui._State.started_automatically,
        "filepath": bpy.data.filepath,
        "background": bpy.app.background,
    }

def steps():
    yield 2.0
    report("settled")
    if ACTION == "stop_then_open":
        bpy.ops.mpfb_bridge.server_stop()
        bpy.ops.wm.open_mainfile(filepath=BLEND)
        yield 2.0
        report("after")
    elif ACTION == "reenable":
        addon_utils.disable(package(), default_set=False)
        addon_utils.enable(package(), default_set=False)
        yield 2.0
        report("after")

STEPS = steps()

def tick():
    try:
        return next(STEPS)
    except StopIteration:
        with open(OUT + ".tmp", "w") as handle:
            json.dump(REPORTS, handle)
        os.replace(OUT + ".tmp", OUT)
        return None

if ACTION == "start_first":
    bpy.ops.mpfb_bridge.server_start()

bpy.app.timers.register(tick, first_interval=0.0, persistent=True)
'''

BACKGROUND_PROBE = r'''
import json, os, socket, sys, bpy

package = next(n for n in sys.modules if n.endswith(".mpfb_bridge"))
preferences = bpy.context.preferences.addons[package].preferences
autostart = sys.modules[package + ".autostart"]
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    refused = probe.connect_ex(("127.0.0.1", preferences.port)) != 0
with open(os.environ["LIVE_PROBE_OUT"], "w") as handle:
    json.dump({
        "box": preferences.autostart,
        "background": bpy.app.background,
        "filepath": bpy.data.filepath,
        "running": sys.modules[package + ".command_server"].is_running(),
        "one_shot_registered": bpy.app.timers.is_registered(autostart.run_once),
        "port_refused": refused,
    }, handle)
'''

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
_running: list[subprocess.Popen] = []


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


def refused(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex((HOST, port)) != 0


def ask(port: int, command: str = "get_status", timeout: float = 10.0) -> dict:
    """One request, as the wire has it."""
    with socket.create_connection((HOST, port), timeout=timeout) as connection:
        connection.sendall(json.dumps({
            "command": command, "params": {}, "protocol_version": PROTOCOL_VERSION,
        }).encode() + b"\0")
        data = b""
        while not data.endswith(b"\0"):
            chunk = connection.recv(65536)
            if not chunk:
                raise ConnectionError("closed before a full answer")
            data += chunk
    return json.loads(data[:-1])


def wait_for_answer(port: int, deadline: float = 40.0) -> tuple[dict | None, float]:
    """The first answer on ``port`` and how long it took, or ``None`` at the deadline."""
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        try:
            return ask(port), time.monotonic() - started
        except (OSError, ConnectionError):
            time.sleep(0.05)
    return None, time.monotonic() - started


class Check:
    """The temporary config, and the means of starting Blenders under it."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.config = directory / "config"
        self.config.mkdir()
        self.environment = dict(os.environ, BLENDER_USER_CONFIG=str(self.config))
        self.probe = directory / "probe.py"
        self.probe.write_text(PROBE)
        self.background_probe = directory / "background_probe.py"
        self.background_probe.write_text(BACKGROUND_PROBE)
        self.configure_script = directory / "configure.py"
        self.configure_script.write_text(CONFIGURE)
        self.blend = directory / "scene.blend"
        self.counter = 0
        self.module = ""

    def real_userpref(self) -> Path:
        out = subprocess.run(
            [BLENDER, "--background", "--python-expr",
             "import bpy; print('CONFIG_DIR', bpy.utils.user_resource('CONFIG'), flush=True)"],
            capture_output=True, text=True, timeout=120, check=True).stdout
        return Path(re.search(r"CONFIG_DIR (.+)", out).group(1)) / "userpref.blend"

    def configure(self, autostart: bool, port: int) -> None:
        out = subprocess.run(
            [BLENDER, "--background", "--python", str(self.configure_script)],
            env=dict(self.environment, LIVE_AUTOSTART="1" if autostart else "0", LIVE_PORT=str(port)),
            capture_output=True, text=True, timeout=120, check=True).stdout
        found = re.search(r"BRIDGE_MODULE (\S+)", out)
        if found is None:
            raise RuntimeError("The bridge is not enabled in the copied preferences:\n" + out[-2000:])
        self.module = found.group(1)

    def make_scene(self) -> None:
        subprocess.run(
            [BLENDER, "--background", "--python-expr",
             "import bpy; bpy.ops.wm.save_as_mainfile(filepath={!r})".format(str(self.blend))],
            env=self.environment, capture_output=True, timeout=120, check=True)

    def window(self, *arguments: str, action: str = "") -> tuple[subprocess.Popen, Path]:
        """A windowed Blender with the probe. Returns it and where its report lands."""
        self.counter += 1
        out = self.directory / "report{:d}.json".format(self.counter)
        log = open(self.directory / "window{:d}.log".format(self.counter), "w", encoding="utf-8")  # pylint: disable=consider-using-with
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            [BLENDER, "--no-window-focus", "--window-geometry", "0", "0", "640", "480",
             *arguments, "--python", str(self.probe)],
            env=dict(self.environment, LIVE_PROBE_OUT=str(out), LIVE_PROBE_ACTION=action,
                     LIVE_PROBE_BLEND=str(self.blend)),
            stdout=log, stderr=subprocess.STDOUT)
        _running.append(process)
        return process, out

    def headless(self, *arguments: str, **environment: str) -> subprocess.Popen:
        """A background Blender with its stdout on a pipe, as a supervisor would have it."""
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            [BLENDER, "--background", *arguments],
            env=dict(self.environment, **environment),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        _running.append(process)
        return process


def wait_for_report(path: Path, deadline: float = 60.0) -> dict | None:
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        if path.exists():
            return json.loads(path.read_text())
        time.sleep(0.1)
    return None


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
    process.wait()
    if process in _running:
        _running.remove(process)


def read_ready_line(process: subprocess.Popen, deadline: float = 30.0) -> tuple[str, list[str]]:
    """Read the pipe until the ready line, without any request having been sent."""
    started = time.monotonic()
    seen = b""
    while time.monotonic() - started < deadline:
        ready, _, _ = select.select([process.stdout], [], [], 0.2)
        if ready:
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            seen += chunk
            found = LISTENING.search(seen.decode(errors="replace"))
            if found:
                return found.group(0), [found.group(1), found.group(2)]
    return seen.decode(errors="replace")[-400:], []


def windowed(check_: Check) -> None:
    print("\n--- Windowed", flush=True)
    port = free_port()

    check_.configure(False, port)
    process, out = check_.window()
    state = wait_for_report(out)
    check("box off: nothing starts", state is not None and not state["settled"]["running"], state)
    check("box off: nothing listens", refused(port))
    stop(process)

    check_.configure(True, port)
    process, out = check_.window(str(check_.blend))
    answer, seconds = wait_for_answer(port)
    check("box on: answers with no click",
          answer is not None and answer.get("status") == "ok", "{:.2f} s from launch".format(seconds))
    state = wait_for_report(out)
    check("box on: reports the real state", state is not None, state)
    if state:
        settled = state["settled"]
        check("box on: the named file is the one open",
              settled["filepath"] == str(check_.blend), settled["filepath"])
        check("box on: the panel knows the box started it", settled["automatically"])
    if answer:
        check("box on: real requests are answered",
              ask(port, "list_commands").get("status") == "ok")

    print("--- A second Blender, with the first still serving", flush=True)
    second, second_out = check_.window()
    state = wait_for_report(second_out)
    settled = state["settled"] if state else None
    check("second: did not start", settled is not None and not settled["running"], settled)
    check("second: the panel says why",
          settled is not None and "automatically" in settled["last_error"],
          settled and settled["last_error"])
    check("second: Blender itself is fine", second.poll() is None)
    check("first: still answers", ask(port).get("status") == "ok")
    stop(second)
    stop(process)

    process, out = check_.window(action="stop_then_open")
    state = wait_for_report(out)
    check("Stop, then open a file: was running first",
          state is not None and state["settled"]["running"], state and state["settled"])
    check("Stop, then open a file: stays stopped",
          state is not None and "after" in state and not state["after"]["running"]
          and state["after"]["filepath"] == str(check_.blend), state and state.get("after"))
    check("Stop, then open a file: nothing listens", refused(port))
    stop(process)

    process, out = check_.window(action="reenable")
    state = wait_for_report(out)
    check("re-enabling the add-on with the box ticked starts it",
          state is not None and "after" in state and state["after"]["running"]
          and state["after"]["automatically"], state and state.get("after"))
    stop(process)

    process, out = check_.window(action="start_first")
    state = wait_for_report(out)
    settled = state["settled"] if state else None
    check("a --python script got there first: left alone",
          settled is not None and settled["running"] and not settled["last_error"]
          and not settled["automatically"], settled)
    stop(process)


def background(check_: Check) -> None:
    print("\n--- Background, box ticked", flush=True)
    port = free_port()
    check_.configure(True, port)

    out = check_.directory / "background.json"
    started = time.monotonic()
    done = subprocess.run(
        [BLENDER, "--background", str(check_.blend), "--python", str(check_.background_probe)],
        env=dict(check_.environment, LIVE_PROBE_OUT=str(out)),
        capture_output=True, timeout=120, check=False)
    seconds = time.monotonic() - started
    state = json.loads(out.read_text()) if out.exists() else None
    check("no --command: the box really is ticked here", state is not None and state["box"], state)
    check("no --command: nothing started",
          state is not None and not state["running"] and not state["one_shot_registered"]
          and state["port_refused"], state)
    check("no --command: exits on its own, exit 0", done.returncode == 0,
          "exit {:d} in {:.2f} s".format(done.returncode, seconds))

    done = subprocess.run([BLENDER, "--command", "help"], env=check_.environment,
                          capture_output=True, timeout=120, check=False)
    check("another --command still runs and exits", done.returncode == 0)

    named = free_port()
    process = check_.headless("--command", "mpfb_bridge", "--port", str(named))
    answer, _ = wait_for_answer(named)
    check("--command: serves where it was asked",
          answer is not None and answer.get("status") == "ok")
    check("--command: exactly one server, not one on the preference too", refused(port))
    stop(process)

    print("\n--- The headless command as a process", flush=True)
    process = check_.headless("--command", "mpfb_bridge", "--port", "0")
    line, address = read_ready_line(process)
    check("--port 0: the line reaches a pipe before any request", bool(address), line)
    if address:
        check("--port 0: its port answers", ask(int(address[1])).get("status") == "ok", address[1])
        started = time.monotonic()
        process.send_signal(signal.SIGINT)
        code = process.wait(timeout=20)
        seconds = time.monotonic() - started
        rest = process.stdout.read().decode(errors="replace")
        check("SIGINT, once: exit 0", code == 0, "exit {:d} in {:.2f} s".format(code, seconds))
        check("SIGINT: went through the handler", "Interrupted." in rest and "Blender killed" not in rest)
        check("SIGINT: port free at once", refused(int(address[1])))
    stop(process)

    process = check_.headless("--command", "mpfb_bridge", "--port", "0")
    line, address = read_ready_line(process)
    if address:
        process.send_signal(signal.SIGTERM)
        code = process.wait(timeout=20)
        rest = process.stdout.read().decode(errors="replace")
        check("SIGTERM: exit 0", code == 0, "exit {:d}".format(code))
        check("SIGTERM: went through the handler", "Interrupted." in rest)
        check("SIGTERM: port free at once", refused(int(address[1])))
    else:
        check("SIGTERM: the line arrived", False, line)
    stop(process)

    process = check_.headless("--command", "mpfb_bridge")
    line, address = read_ready_line(process)
    check("no --port: serves on the preference", address[1:] == [str(port)], line)
    stop(process)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind((HOST, port))
        holder.listen(1)
        done = subprocess.run(
            [BLENDER, "--background", "--command", "mpfb_bridge"], env=check_.environment,
            capture_output=True, text=True, timeout=120, check=False)
    check("port held: exit 1", done.returncode == 1, done.returncode)
    check("port held: one clear line naming the address, no traceback",
          "could not start the MPFB Bridge server on {:s}:{:d}".format(HOST, port) in done.stdout
          and "Traceback" not in done.stdout + done.stderr)

    # The guard: --host is not named, and there are no preferences to read it from.
    named = free_port()
    process = check_.headless(
        "--factory-startup", "--addons", check_.module, "--command", "mpfb_bridge",
        "--port", str(named))
    line, address = read_ready_line(process)
    check("--factory-startup --addons, no preferences to read: serves", address == [HOST, str(named)], line)
    stop(process)


def main() -> int:
    if not BLENDER:
        print("Set BLENDER_EXE to the Blender to check.")
        return 2

    directory = Path(tempfile.mkdtemp(prefix="fr058_"))
    check_ = Check(directory)
    real = check_.real_userpref()
    before = real.stat().st_mtime_ns
    shutil.copy2(real, check_.config / "userpref.blend")

    try:
        check_.configure(False, free_port())
        check_.make_scene()
        background(check_)
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            windowed(check_)
        else:
            check("the windowed half ran", False, "no display here, so it did NOT run")
    finally:
        for process in list(_running):
            stop(process)
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
