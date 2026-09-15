"""
``get_status``: is MPFB here, did it finish starting, and what is this bridge?

This is the command that must work in every state the system can be in,
including the states where MPFB is missing or broken - which is why it is the
one command in the table with ``requires_mpfb=False``. A status command that
could not run without MPFB would answer only the question nobody needs asking.

It is also the handshake. Every answer carries the protocol version the bridge
speaks and the oldest it accepts, so a client can decide whether to continue
before it depends on anything more specific. MPFB, the bridge and mpfb-mcp are
three separately released pieces; the compatibility matrix is a real cost of
keeping them apart, and a version in the first answer is the cheap defence.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_status",
)

import bpy

from ..command_server import MIN_SUPPORTED_PROTOCOL_VERSION
from ..command_server import PROTOCOL_VERSION
from ..log import get_logger
from ..version import BRIDGE_VERSION

_LOG = get_logger("commands.getstatus")

PARAMS = ()

SUMMARY = "Report whether MPFB is present and initialized, and which protocol this bridge speaks."


def _dotted(version):
    """MPFB's ``VERSION`` tuple as the string a human recognises, or ``None``."""
    if not isinstance(version, (tuple, list)):
        return None
    return ".".join(str(part) for part in version)


def get_status(params, resolution):  # pylint: disable=unused-argument
    """Report whether MPFB is present, initialized and reachable.

    Takes no parameters. Answers in three tiers, because the three states differ
    in what can be known: ``state``, ``message`` and ``candidate_modules`` need
    nothing but ``bpy`` and are always present; ``package``, ``enabled``,
    ``version`` and ``build_info`` are readable off the module object as soon as
    one is found, so they survive the ``not_initialized`` state; anything needing
    MPFB's services would need ``ok``, and this command deliberately asks for
    none of it.

    ``enabled`` is the field that earns its place. MPFB's ``unregister()`` leaves
    ``MPFB_CONTEXTUAL_INFORMATION`` populated in ``sys.modules``, so a *disabled*
    MPFB still classifies as ``ok``; Blender's add-on preferences are the only
    thing that tells the two apart.
    """
    result = {
        "state": resolution.state,
        "message": resolution.message,
        "candidate_modules": resolution.candidates,
        "package": None,
        "enabled": None,
        "version": None,
        "build_info": None,
        "bridge_version": BRIDGE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "min_supported_protocol_version": MIN_SUPPORTED_PROTOCOL_VERSION,
        "blender": {"version": bpy.app.version_string, "background": bpy.app.background},
    }

    module = resolution.module
    if module is not None:
        # __name__ rather than MPFB_CONTEXTUAL_INFORMATION["__package__"]: the same
        # value on a healthy install, and readable in the not_initialized state too,
        # where the dict may not exist at all.
        result["package"] = module.__name__
        result["enabled"] = module.__name__ in bpy.context.preferences.addons
        result["version"] = _dotted(getattr(module, "VERSION", None))
        result["build_info"] = getattr(module, "BUILD_INFO", None)

    _LOG.debug("get_status: %s (%d candidate modules)",
               resolution.state, len(resolution.candidates))
    return result
