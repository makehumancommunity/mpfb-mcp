"""
MPFB Bridge: a local command server that lets an MCP client drive MPFB.

This add-on exists so that MPFB's Blender-side logic can live in Blender rather
than be shipped across a socket as generated Python on every call. It listens on
127.0.0.1, dispatches a fixed set of named commands, and executes nothing a
caller sends. MPFB itself is not modified and does not know this exists; the
bridge reaches it through the ``sys.modules`` scan MPFB documents for exactly
this purpose.

It is a proof of concept. One command is implemented - see :mod:`commands` - and
what that proves is the transport, the dispatch and the MPFB resolution. It
proves nothing about the twenty-odd commands a migration would add, nor about
performance under real payloads.

The modules, in dependency order:

- ``log`` - the add-on's own logger, in MPFB's shape but not MPFB's dependency
- ``mpfb_resolution`` - finding MPFB and classifying the install; no ``bpy``
- ``command_server`` - the socket, the framing and the dispatch; no ``bpy``
- ``commands`` - the closed vocabulary, and the only file that need be read to
  know everything this add-on can be asked to do
- ``timer`` - the main-thread callback that drives the server
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


def register():
    """Register the add-on's classes. Starts no server and opens no socket."""
    from .ui import CLASSES  # pylint: disable=import-outside-toplevel

    for cls in CLASSES:
        bpy.utils.register_class(cls)
        _REGISTERED_CLASSES.append(cls)


def unregister():
    """Stop the server if it is running, then unregister in reverse order."""
    from . import command_server  # pylint: disable=import-outside-toplevel
    from . import timer  # pylint: disable=import-outside-toplevel

    # Order matters: the timer must go before the classes it was drawn beside, and
    # the socket must not outlive the add-on that owns it. Disabling the add-on
    # with the server running is an ordinary thing for a user to do.
    timer.unregister_timer()
    command_server.stop()

    while _REGISTERED_CLASSES:
        bpy.utils.unregister_class(_REGISTERED_CLASSES.pop())
