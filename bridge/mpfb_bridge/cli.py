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
    blender --background --command mpfb_bridge --export-dir /srv/exports

It blocks until interrupted, which is the whole difference. Everything below the
waiting is shared with the GUI path: the same socket, the same framing, the same
dispatch and the same command table, because a headless bridge that answered
differently from a windowed one would be a second thing to verify rather than
the same thing without a screen.

**This is the only way to ask a background Blender to serve, and not for want of
trying another.** Blender registers add-ons, loads the files on its command line,
runs its ``--python`` scripts and exits, and it runs no timers in between. An
environment variable, an argument after ``--`` or the preference to start with
Blender would each have to be noticed by the add-on for itself, and it could then
only block in ``register()`` or a ``load_post`` handler, in front of the file and
the scripts, or not block and watch Blender exit. A deferred ``--command`` runs
after all of them, and Blender waits for it (measured in FR 058).

**It answers to the signals a supervisor sends, and says when it is ready.**
Blender replaces ``SIGINT`` in background mode with a handler of its own that only
sets a flag for the render loop, so without :func:`_stop_on_signals` the first
Ctrl+C prints a message and leaves the bridge serving, and the second kills Blender
past every ``finally`` here. The "listening" line is flushed because a pipe is
block-buffered, and a process reading one would otherwise see nothing while the
bridge serves. Its form, ``MPFB Bridge listening on <host>:<port>``, is one a script
may rely on, and is how a caller learns the port it got from ``--port 0``.

**The preferences say where; only this command line says whether.** ``--host`` and
``--port`` fall back to the preferences as ``--export-dir`` does, so a port set
there and in the client's configuration is the same port headless. The preference
to start with Blender is not read here at all.

**Two prerequisites that are easy to miss.** The add-on must be *enabled* in the
Blender being run, since a disabled extension registers no CLI command and
``--command mpfb_bridge`` is then an unknown command; ``--addons`` before
``--command`` enables it for one process. And whatever the pipeline does with the
scene afterwards happens in the same process: this loop owns the main thread until
it is interrupted.

**What this does not establish** is that MPFB itself is fully usable without a
screen. It makes the *bridge* drivable headless; how much of MPFB works there is
a separate question and this module answers none of it.
"""

__all__ = (
    "CLI_COMMAND_ID",
    "cli_execute",
)

import argparse
import signal

from . import addon_preferences
from . import command_server
from . import export_directory
from .commands import COMMANDS
from .log import get_logger

_LOG = get_logger("cli")

# Must pass str.isidentifier, which Blender checks when the command is
# registered. Deliberately the same string as the add-on's package name, so
# `--command mpfb_bridge` is guessable from having installed it.
CLI_COMMAND_ID = "mpfb_bridge"


def _address_or_preference(host, port):
    """``(host, port)``: what was named, else the preference, else the default.

    The same order as the export directory. There may be no preferences to read,
    under ``--addons``, and that is not an error.
    """
    preferences = addon_preferences.read()
    if host is None:
        host = preferences.host if preferences is not None else command_server.DEFAULT_HOST
    if port is None:
        port = preferences.port if preferences is not None else command_server.DEFAULT_PORT
    return (host, port)


def _interrupt(_signum, _frame):
    """Turn a signal into what the loop below already knows how to stop on."""
    raise KeyboardInterrupt


def _stop_on_signals():
    """Make ``SIGINT`` and ``SIGTERM`` stop the loop. Returns what :func:`_restore_signals` needs.

    Installed here rather than at registration, because Blender's own ``SIGINT``
    behaviour is what stops a long render. ``getattr``, because a platform need not
    have ``SIGTERM``.
    """
    previous = {}
    for name in ("SIGINT", "SIGTERM"):
        number = getattr(signal, name, None)
        if number is not None:
            previous[number] = signal.signal(number, _interrupt)
    return previous


def _restore_signals(previous):
    """Put back the handlers Python can name, and the default where it cannot.

    Blender's ``SIGINT`` handler is C, so ``signal.signal`` returned ``None`` for it
    and it cannot be installed again from here. By then Blender is on its way out,
    and a second Ctrl+C ending that at once is what its own handler would have done.
    """
    for number, handler in previous.items():
        signal.signal(number, signal.SIG_DFL if handler is None else handler)


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
        "--host", default=None,
        help="Address to bind. Leave this at the default unless you know why you are changing "
             "it: any address but the loopback one exposes Blender to the network (default: the "
             "add-on's host preference, else {:s})".format(command_server.DEFAULT_HOST))
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port to listen on. 0 asks the system for a free one, and the line printed once "
             "listening says which (default: the add-on's port preference, else "
             "{:d})".format(command_server.DEFAULT_PORT))
    parser.add_argument(
        "--export-dir", default=None,
        help="Directory mpfb_export_character writes into, overriding the add-on's "
             "export_directory preference. It must exist: a named directory that does not is "
             "refused rather than created (default: the preference, else <MPFB user "
             "data>/exports)")
    arguments = parser.parse_args(argv)

    export_directory.set_command_line(arguments.export_dir)
    host, port = _address_or_preference(arguments.host, arguments.port)
    try:
        command_server.start(host, port, COMMANDS)
    except Exception as error:  # pylint: disable=broad-except
        # Broad on purpose: start() raises RuntimeError when something is
        # already running and OSError when the address will not bind, and a
        # background process should report either as one clear line rather than
        # a traceback.
        print("Error: could not start the MPFB Bridge server on {:s}:{:d}: {:s}".format(
            host, port, str(error)), flush=True)
        export_directory.set_command_line(None)
        return 1

    previous_handlers = _stop_on_signals()
    try:
        # Inside the try, and after the handlers: a process that reads this line and
        # stops the bridge straight away should find it able to stop.
        host, port = command_server.bound_address()
        print("MPFB Bridge listening on {:s}:{:d} with {:d} commands. Press Ctrl+C to "
              "stop.".format(host, port, len(COMMANDS)), flush=True)
        _LOG.info("Headless command loop started on %s:%d", host, port)

        while command_server.is_running():
            command_server.poll_blocking()
    except KeyboardInterrupt:
        print("\nInterrupted.", flush=True)
    finally:
        # In a finally, because an interrupted background job that leaves a
        # bound socket behind is a confusing failure on the next run.
        command_server.stop()
        export_directory.set_command_line(None)
        _restore_signals(previous_handlers)

    return 0
