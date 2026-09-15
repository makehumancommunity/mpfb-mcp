"""
Finding MPFB from a companion add-on, and deciding whether it is usable.

MPFB is a Blender *extension*, so its top-level package name depends on which
extension repository the user installed it from - ``bl_ext.user_default.mpfb``,
``bl_ext.some_repo.mpfb``, or a plain ``mpfb`` when it is run from source. There
is no path to hardcode. MPFB knows this and publishes the way around it: scan
``sys.modules`` for a module whose name ends in ``"mpfb"``, then read what you
need off the ``MPFB_CONTEXTUAL_INFORMATION`` dict that module exports. The
pattern is written out in a comment in MPFB's own ``__init__.py`` and used by
MPFB's own test suite, so a companion add-on doing this is using the supported
entry point rather than a trick.

**Finding the module answers only half the question.** MPFB declares
``MPFB_CONTEXTUAL_INFORMATION = None`` at module level and builds it inside
``register()``, assigning the ``"SERVICES"`` key on that function's very last
line. So a module can be present while its services are not, and the two have to
be asked separately or a half-registered MPFB surfaces as a bare ``TypeError``.
Hence three states rather than two.

Two further consequences, both of which this module reports rather than hides.
The scan can match **more than one** module - MPFB installed under two extension
repositories, or a stale legacy add-on lingering beside an extension install - and
which one wins is then arbitrary, so every candidate is named. And MPFB's
``unregister()`` never resets the dict, so a *disabled* MPFB still classifies as
``ok``; only Blender's add-on preferences tell the two apart, which is why that
question is answered in :mod:`commands` where ``bpy`` is available and not here.

Nothing in this module imports ``bpy``, which is what lets it be read and
reasoned about outside a running Blender.
"""

__all__ = (
    "STATE_ABSENT",
    "STATE_NOT_INITIALIZED",
    "STATE_OK",
    "STATE_MESSAGES",
    "find_candidates",
    "resolve",
)

import sys

from .log import get_logger

_LOG = get_logger("mpfbresolution")

STATE_ABSENT = "absent"
STATE_NOT_INITIALIZED = "not_initialized"
STATE_OK = "ok"

# One sentence per state, phrased for whoever has to fix it. These are the same
# three states and substantially the same wording mpfb-mcp's own `mpfb_get_status`
# uses, deliberately: an agent should not have to learn a second vocabulary when
# the transport underneath it changes.
STATE_MESSAGES = {
    STATE_ABSENT: "MPFB is not loaded in this Blender instance: no loaded module name ends in "
                  "'mpfb'. Install and enable the MPFB extension, then try again.",
    STATE_NOT_INITIALIZED: "MPFB is loaded but did not finish initializing, so none of its services "
                           "are available. Check Blender's console for errors raised during MPFB "
                           "registration, and check whether this Blender version is new enough for "
                           "this MPFB version.",
    STATE_OK: "MPFB is loaded and initialized.",
}


def find_candidates():
    """Every loaded module name ending in ``"mpfb"``, in sorted order.

    Sorted so that the answer does not depend on dictionary ordering, which makes
    a report comparable between two runs. More than one candidate is a real and
    reportable situation, not an error.
    """
    return sorted(name for name in list(sys.modules) if name.endswith("mpfb"))


def resolve():
    """Classify this Blender's MPFB install.

    Returns ``(state, module, services, candidates)``. ``module`` is ``None`` in
    the ``absent`` state and ``services`` is ``None`` in every state but ``ok``,
    so a caller can report progressively: what is readable off ``bpy`` alone,
    then what is readable off the module object, then what needs services.
    """
    candidates = find_candidates()
    if not candidates:
        _LOG.debug("No loaded module name ends in 'mpfb'")
        return (STATE_ABSENT, None, None, candidates)

    # Arbitrary among several, which is why every candidate is reported.
    module = sys.modules[candidates[0]]

    contextual_information = getattr(module, "MPFB_CONTEXTUAL_INFORMATION", None)
    if not isinstance(contextual_information, dict):
        # Still None: register() never ran, or raised before it got this far.
        _LOG.debug("MPFB module found but MPFB_CONTEXTUAL_INFORMATION is not a dict")
        return (STATE_NOT_INITIALIZED, module, None, candidates)

    services = contextual_information.get("SERVICES")
    if not isinstance(services, dict):
        # register() ran but did not reach its last line.
        _LOG.debug("MPFB is initialized but published no SERVICES dict")
        return (STATE_NOT_INITIALIZED, module, None, candidates)

    return (STATE_OK, module, services, candidates)
