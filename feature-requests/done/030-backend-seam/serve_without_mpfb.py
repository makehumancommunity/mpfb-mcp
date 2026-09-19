# SPDX-License-Identifier: GPL-3.0-or-later

"""
A bridge with no MPFB behind it, for the half of FR 030's check that needs one.

``mpfb_unavailable`` is the precondition FR 029 built and nothing outside the
add-on had ever reached, because no command in the table required MPFB until
``list_objects`` did. Exercising it needs a Blender running the bridge *and no
MPFB*, which is awkward to arrange by hand: ``--factory-startup`` gives a
Blender with no add-ons enabled at all, so the ``--command mpfb_bridge`` CLI
entry point does not exist there either - a disabled extension registers no
command.

So this script is the third drive mechanism, and it exists only for a test:
enable the one extension, start the server, and drive it from the blocking loop
``cli.py`` drives, for a bounded time. Run it in another terminal::

    blender --factory-startup --background -P serve_without_mpfb.py -- --port 9878
    MPFB_BRIDGE_PORT=9878 PYTHONPATH=. python3 check_backend_seam.py --expect-no-mpfb

A port of its own by default, so it cannot be confused with - or collide with -
the bridge inside the Blender the rest of the check talks to.
"""

import sys
import time

import bpy

_PACKAGE = "mpfb_bridge"
_DEFAULT_PORT = 9878
_DEFAULT_SECONDS = 120.0


def _arguments():
    """Whatever follows a bare ``--`` on Blender's command line."""
    if "--" not in sys.argv:
        return _DEFAULT_PORT, _DEFAULT_SECONDS
    rest = sys.argv[sys.argv.index("--") + 1:]
    port, seconds = _DEFAULT_PORT, _DEFAULT_SECONDS
    if "--port" in rest:
        port = int(rest[rest.index("--port") + 1])
    if "--seconds" in rest:
        seconds = float(rest[rest.index("--seconds") + 1])
    return port, seconds


def _enable_addon():
    """Enable the bridge, and only the bridge. The module name is asked for."""
    candidates = ["bl_ext.{:s}.{:s}".format(repo.module, _PACKAGE)
                  for repo in bpy.context.preferences.extensions.repos]
    candidates.append(_PACKAGE)
    for candidate in candidates:
        try:
            bpy.ops.preferences.addon_enable(module=candidate)
        except Exception:  # pylint: disable=broad-except
            continue
        if candidate in bpy.context.preferences.addons:
            return candidate
    raise SystemExit("Could not enable the MPFB Bridge add-on. Tried: " + ", ".join(candidates))


def main():
    port, seconds = _arguments()
    package = _enable_addon()
    module = sys.modules[package]
    command_server = sys.modules[package + ".command_server"]
    commands = sys.modules[package + ".commands"].COMMANDS
    resolution = sys.modules[package + ".mpfb_resolution"].resolve()

    print("Enabled {:s} {:s}".format(package, getattr(module, "__name__", "")))
    print("MPFB in this Blender: {:s} ({:d} candidate modules)".format(
        resolution.state, len(resolution.candidates)))
    if resolution.is_ok:
        # The whole point of --factory-startup is that MPFB is not loaded here.
        # If it is, this Blender cannot answer the question being asked.
        print("WARNING: MPFB is usable in this Blender, so mpfb_unavailable cannot be reached.")

    command_server.start("127.0.0.1", port, commands)
    print("Serving {:d} commands on 127.0.0.1:{:d} for {:.0f} seconds".format(
        len(commands), port, seconds))
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            command_server.poll_blocking(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        command_server.stop()
    print("Stopped")


main()
