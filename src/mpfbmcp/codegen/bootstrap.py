"""
The shared MPFB bootstrap prepended to every generated payload.

MPFB is a Blender *extension*, so it is only reachable via relative imports
from within its own package - there is no stable, guessable absolute module
path (the top-level package name depends on which extension repository the
user installed it from, e.g. ``bl_ext.user_default.mpfb``). MPFB documents a
workaround for this in ``mpfb/__init__.py`` and uses it itself in
``test/tests/__init__.py``: scan ``sys.modules`` for a module whose name ends
with ``"mpfb"``, then pull classes out of the ``MPFB_CONTEXTUAL_INFORMATION``
dict it publishes on that module.

Resolution is *two* steps, not one, and the two are worth keeping apart:
finding such a module says nothing about whether it is usable. MPFB declares
``MPFB_CONTEXTUAL_INFORMATION = None`` at module level and only builds it
inside ``register()``, assigning the ``"SERVICES"`` entry on that function's
very last line; ``unregister()`` never resets it. A module can therefore be
present while the services are not.

Hence the two bootstraps below, both built on the same ``_MPFB_MODULE_SCAN``:

- ``MPFB_BOOTSTRAP`` raises ``RuntimeError`` unless MPFB is fully
  initialized. Use it for tools that cannot do their job without MPFB.
- ``MPFB_STATUS_BOOTSTRAP`` never raises; it classifies the situation into
  ``absent`` / ``not_initialized`` / ``ok``. Use it for tools whose job is
  partly *to answer* whether MPFB is there at all.

Generated code must resolve services only through the ``SERVICES`` dict, never
by importing MPFB submodules directly: several of them have import-time side
effects (``locationservice.py`` ends by creating directories on disk).

This is the only part of a generated program that is shared between tools, and
the only part still written as a string rather than as a payload file under
``payloads/``: it is prepended to every payload, so it has no file of its own.
"""

from __future__ import annotations

__all__ = (
    "MPFB_BOOTSTRAP",
    "MPFB_STATUS_BOOTSTRAP",
)

# Lists every loaded module whose name ends in "mpfb". Shared by both
# bootstraps below. More than one match is possible and is itself a diagnosis:
# MPFB installed under two extension repositories, or a stale legacy addon
# lingering beside an extension install. Which one the raising bootstrap picks
# is then arbitrary.
_MPFB_MODULE_SCAN = """
import sys

def _mpfb_candidate_module_names():
    # list() because sys.modules can change size while Blender imports things.
    return [name for name in list(sys.modules) if name.endswith("mpfb")]
""".strip()

# Resolves MPFB's SERVICES dict and binds it to `_MPFB_SERVICES`, or raises
# RuntimeError with a message pointing at the likely cause (extension not
# installed/enabled, or installed but not successfully registered).
MPFB_BOOTSTRAP = _MPFB_MODULE_SCAN + """

def _mpfb_resolve_services():
    names = _mpfb_candidate_module_names()
    if not names:
        raise RuntimeError(
            "No loaded module ends with 'mpfb'. Is the MPFB extension installed and enabled in "
            "this Blender instance?"
        )
    mpfb = sys.modules[names[0]]
    contextual_information = getattr(mpfb, "MPFB_CONTEXTUAL_INFORMATION", None)
    if contextual_information is None or "SERVICES" not in contextual_information:
        raise RuntimeError(
            "The module '{}' is loaded, but MPFB has not finished initializing: its "
            "MPFB_CONTEXTUAL_INFORMATION['SERVICES'] is not available. MPFB is installed but did "
            "not register successfully. Call mpfb_get_status for details.".format(names[0])
        )
    return contextual_information["SERVICES"]

_MPFB_SERVICES = _mpfb_resolve_services()
"""

# Non-raising counterpart: classifies rather than fails. Leaves `_mpfb_state`,
# `_mpfb_candidates`, `_mpfb_module` and `_mpfb_services` bound, the latter two
# possibly None. MPFB being missing or half-registered are everyday answers for
# a status tool, not error conditions - so neither MPFB_CONTEXTUAL_INFORMATION
# being None (TypeError) nor it lacking "SERVICES" (KeyError) may escape here.
MPFB_STATUS_BOOTSTRAP = _MPFB_MODULE_SCAN + """

_mpfb_candidates = _mpfb_candidate_module_names()
_mpfb_module = None
_mpfb_services = None

if not _mpfb_candidates:
    _mpfb_state = "absent"
else:
    _mpfb_module = sys.modules[_mpfb_candidates[0]]
    _mpfb_contextual_information = getattr(_mpfb_module, "MPFB_CONTEXTUAL_INFORMATION", None)
    if _mpfb_contextual_information is None:
        # register() never ran, or died before its first line of bookkeeping.
        _mpfb_state = "not_initialized"
    elif "SERVICES" not in _mpfb_contextual_information:
        # register() started but did not reach its last line, where SERVICES is set.
        _mpfb_state = "not_initialized"
    else:
        _mpfb_services = _mpfb_contextual_information["SERVICES"]
        _mpfb_state = "ok"
"""
