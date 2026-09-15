"""
The closed command vocabulary. This module *is* the security argument.

Everything this add-on can be made to do from outside is in :data:`COMMANDS`
below. A request names a key of that dict; a name that is not a key is refused
with an error that lists the alternatives. There is no ``exec``, no ``eval``, no
``importlib`` and no path by which a caller's string becomes Python. That claim
is only worth making if it can be checked, and checking it means reading one
short file - which is why the table is a literal dict here rather than a registry
populated by decorators scattered across the package.

**The proof of concept carries exactly one command.** One is enough to establish
what was actually in doubt - that a socket server inside Blender, dispatching on
a name from a fixed table and running on the main thread, is unremarkable to
write - and no number of commands would establish more. What it deliberately does
*not* prove is the behaviour of the twenty-odd commands the migration will add,
performance under real payloads, or whether that migration is affordable.

``get_status`` was chosen because it is the one command that must work in every
state the system can be in, including the states where MPFB is missing or broken.
It is therefore the command most likely to expose a resolution mistake, and the
only one whose answer is still useful when everything else has failed.
"""

__all__ = (
    "COMMANDS",
    "BRIDGE_VERSION",
    "get_status",
)

import bpy

from . import mpfb_resolution
from .command_server import PROTOCOL_VERSION
from .log import get_logger

_LOG = get_logger("commands")

# Kept in step with blender_manifest.toml by hand. There are two of them because
# the manifest is data Blender reads and this is a value a command reports, and
# nothing in the extension format publishes the former to the latter.
BRIDGE_VERSION = "0.1.0"


def _dotted(version):
    """MPFB's ``VERSION`` tuple as the string a human recognises, or ``None``."""
    if not isinstance(version, (tuple, list)):
        return None
    return ".".join(str(part) for part in version)


def get_status(params):  # pylint: disable=unused-argument
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
    state, module, _services, candidates = mpfb_resolution.resolve()

    result = {
        "state": state,
        "message": mpfb_resolution.STATE_MESSAGES[state],
        "candidate_modules": candidates,
        "package": None,
        "enabled": None,
        "version": None,
        "build_info": None,
        "bridge_version": BRIDGE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "blender": {"version": bpy.app.version_string},
    }

    if module is not None:
        # __name__ rather than MPFB_CONTEXTUAL_INFORMATION["__package__"]: the same
        # value on a healthy install, and readable in the not_initialized state too,
        # where the dict may not exist at all.
        result["package"] = module.__name__
        result["enabled"] = module.__name__ in bpy.context.preferences.addons
        result["version"] = _dotted(getattr(module, "VERSION", None))
        result["build_info"] = getattr(module, "BUILD_INFO", None)

    _LOG.debug("get_status: %s (%d candidate modules)", state, len(candidates))
    return result


# The table. Adding a command means adding a function above and one line here;
# there is no other way in.
COMMANDS = {
    "get_status": get_status,
}
