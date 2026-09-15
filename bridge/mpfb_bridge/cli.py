"""
Driving the bridge from a Blender with no screen.

``bpy.app.timers`` callbacks are run by Blender's event loop, and a
``--background`` Blender has none. So the timer that answers requests in a GUI
session never fires here, and the start operator refuses rather than binding a
socket nothing could ever answer on - which it did once, and every client hung
until its own timeout.

This is the second drive mechanism, reached the way Blender 4.2 and later expect
an extension to offer one::

    blender --background scene.blend --command mpfb_bridge
    blender --background --command mpfb_bridge --port 9900

It blocks until interrupted, which is the whole difference. Everything below the
waiting is shared with the GUI path: the same socket, the same framing, the same
dispatch and the same command table, because a headless bridge that answered
differently from a windowed one would be a second thing to verify rather than
the same thing without a screen.

**Two prerequisites that are easy to miss.** The add-on must be *enabled* in the
Blender being run, since a disabled extension registers no CLI command and
``--command mpfb_bridge`` is then an unknown command. And whatever the pipeline
does with the scene afterwards happens in the same process: this loop owns the
main thread until it is interrupted.

**What this does not establish** is that MPFB itself is fully usable without a
screen. It makes the *bridge* drivable headless; how much of MPFB works there is
a separate question and this module answers none of it.
"""

__all__ = (
    "CLI_COMMAND_ID",
    "cli_execute",
)

import argparse

from . import command_server
from .commands import COMMANDS
from .log import get_logger

_LOG = get_logger("cli")

# Must pass str.isidentifier, which Blender checks when the command is
# registered. Deliberately the same string as the add-on's package name, so
# `--command mpfb_bridge` is guessable from having installed it.
CLI_COMMAND_ID = "mpfb_bridge"


def cli_execute(argv):
    """Serve commands until interrupted. Returns a process exit code.

    Blender calls this with the arguments that followed the command id. Errors
    are printed rather than logged, because the thing reading them is a terminal
    or a CI log and not Blender's console.
    """
    parser = argparse.ArgumentParser(
        prog=CLI_COMMAND_ID,
        description="Run the MPFB Bridge command server in a background Blender. Serves the "
                    "same commands as the GUI panel does, over the same protocol, until "
                    "interrupted with Ctrl+C.")
    parser.add_argument(
        "--host", default=command_server.DEFAULT_HOST,
        help="Address to bind. Leave this at the default unless you know why you are changing "
             "it: any address but the loopback one exposes Blender to the network "
             "(default: %(default)s)")
    parser.add_argument(
        "--port", type=int, default=command_server.DEFAULT_PORT,
        help="Port to listen on (default: %(default)s)")
    arguments = parser.parse_args(argv)

    try:
        command_server.start(arguments.host, arguments.port, COMMANDS)
    except Exception as error:  # pylint: disable=broad-except
        # Broad on purpose: start() raises RuntimeError when something is
        # already running and OSError when the address will not bind, and a
        # background process should report either as one clear line rather than
        # a traceback.
        print("Error: could not start the MPFB Bridge server: {:s}".format(str(error)))
        return 1

    host, port = command_server.bound_address()
    print("MPFB Bridge listening on {:s}:{:d} with {:d} commands. Press Ctrl+C to stop.".format(
        host, port, len(COMMANDS)))
    _LOG.info("Headless command loop started on %s:%d", host, port)

    try:
        while command_server.is_running():
            command_server.poll_blocking()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        # In a finally, because an interrupted background job that leaves a
        # bound socket behind is a confusing failure on the next run.
        command_server.stop()

    return 0
