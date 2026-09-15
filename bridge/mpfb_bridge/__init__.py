"""
MPFB Bridge: a local command server that lets an MCP client drive MPFB.

This add-on exists so that MPFB's Blender-side logic can live in Blender rather
than be shipped across a socket as generated Python on every call. It listens on
127.0.0.1, dispatches a fixed set of named commands, and executes nothing a
caller sends. MPFB itself is not modified and does not know this exists; the
bridge reaches it through the ``sys.modules`` scan MPFB documents for exactly
this purpose.

It is not finished. Two commands are implemented - see :mod:`commands.table` -
and the twenty-odd that a migration adds are still to come. What exists proves
the transport, the dispatch, the parameter contract and the MPFB resolution; it
proves nothing about the behaviour of the commands not yet written, nor about
performance under real payloads.

The modules, in dependency order:

- ``log`` - the add-on's own logger, in MPFB's shape but not MPFB's dependency
- ``version`` - the add-on version, which must match the manifest
- ``validation`` - what a command takes, declared as data; no ``bpy``
- ``stats`` - what the server has been doing, for the panel to paint; no ``bpy``
- ``mpfb_resolution`` - finding MPFB and classifying the install; no ``bpy``
- ``command_server`` - the socket, the framing and the dispatch; no ``bpy``
- ``commands`` - one module per command, and ``commands/table.py``, the only
  file that need be read to know everything this add-on can be asked to do
- ``timer`` - the main-thread callback that drives the server in a GUI Blender
- ``cli`` - the blocking loop that drives it in a background one
- ``ui`` - preferences, the start and stop operators, and the panel

WARNING, and it is MPFB's warning rather than a new one: do not import anything
from this package outside ``register()``. Only once Blender has called that can
the rest of the package rely on Blender being far enough along to be useful. The
``bpy`` import below is the exception every add-on has to make.
"""

__all__ = (
    "register",
    "unregister",
)

import bpy

_REGISTERED_CLASSES = []
_REGISTERED_CLI_COMMANDS = []


def register():
    """Register the add-on's classes and its CLI command.

    Starts no server and opens no socket. Registering the CLI command does not
    run it: it makes ``blender --command mpfb_bridge`` resolve to something,
    which is the only way a background Blender can be asked to serve, since a
    disabled extension registers nothing and an unregistered command id is an
    unknown command.

    No version guard on ``register_cli_command``. The manifest declares a
    Blender floor of 5.0.0, which is comfortably past the release that added it.
    """
    from .cli import CLI_COMMAND_ID  # pylint: disable=import-outside-toplevel
    from .cli import cli_execute  # pylint: disable=import-outside-toplevel
    from .ui import CLASSES  # pylint: disable=import-outside-toplevel

    for cls in CLASSES:
        bpy.utils.register_class(cls)
        _REGISTERED_CLASSES.append(cls)

    _REGISTERED_CLI_COMMANDS.append(
        bpy.utils.register_cli_command(CLI_COMMAND_ID, cli_execute))


def unregister():
    """Stop the server if it is running, then unregister in reverse order."""
    from . import command_server  # pylint: disable=import-outside-toplevel
    from . import timer  # pylint: disable=import-outside-toplevel

    while _REGISTERED_CLI_COMMANDS:
        bpy.utils.unregister_cli_command(_REGISTERED_CLI_COMMANDS.pop())

    # Order matters: the timer must go before the classes it was drawn beside, and
    # the socket must not outlive the add-on that owns it. Disabling the add-on
    # with the server running is an ordinary thing for a user to do.
    timer.unregister_timer()
    command_server.stop()

    while _REGISTERED_CLASSES:
        bpy.utils.unregister_class(_REGISTERED_CLASSES.pop())
