"""
``list_urls``: MPFB's own web addresses, read out of its UI module.

**This command reports raw material, not the answer.** It hands back a key ->
URL mapping and enough state to explain a miss; the merge against mpfb-mcp's
vendored copy, the descriptions and the staleness report are assembled on the
*other* side of the socket by ``mpfbmcp.tools.list_urls``. That is unlike every
other command here, and it is deliberate.

**The stated reason for that split was the wire, and the bridge removes it. The
real reason survives.** On the generated path the argument was that sending the
vendored table in as parameters would put ~3 KB past the add-on's 4 KB chunk to
compute what a local function already computes. True, and now irrelevant. What
is unchanged is that **the same merge has to run in all four states**, including
the one where Blender cannot be reached and no command runs at all - so the
merge has to live where it can run without this add-on. One implementation, used
in four states, is worth the divergence, and it would be worth it at zero wire
cost.

**``requires_mpfb=False``, and it is the third command for which it is**, after
``get_status`` and ``get_mpfb_status``. The reason is the same: "where do I
download MPFB" is asked most often by somebody whose MPFB is not working, so a
command gated on MPFB would refuse exactly when its answer is most valuable.

**``weburls`` is a UI module reached through ``sys.modules``, never imported.**
Being an add-on makes importing it *possible* for the first time, which is
precisely why this is written down rather than left to the rule: it would
violate
[Never import MPFB submodules directly](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
and would, on a half-registered install, run MPFB code inside a Blender that is
already broken. MPFB imports its UI during ``register()``, so on an initialized
install ``<root>.ui.weburls`` is already there and reading it re-executes
nothing. Missing from ``sys.modules`` is therefore an ordinary answer here,
reported with a reason, and not something to fix by importing.

Note what makes ``weburls`` safe to read where ``ui/model/_modelsubpanels.py`` -
which ``set_targets`` deliberately does *not* read - is not: this module is a
dozen string literals with no computation at import time, so there is no
snapshot in it to go stale.

**Enumerated by prefix, not by a list.** Every module-level name beginning
``URL_`` is reported, so a constant MPFB adds later appears here without a
change to this add-on. A name whose value is not a string is reported under
``skipped_keys`` rather than silently dropped: an absent entry has to be
explainable.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_urls",
)

import sys

from ..log import get_logger

_LOG = get_logger("commands.listurls")

PARAMS = ()

SUMMARY = ("Report MPFB's own web addresses, read live out of its weburls module. The merge "
           "against mpfb-mcp's vendored copy happens on the client.")

URL_PREFIX = "URL_"

# Why the live values could not be read, per state. None of these is an error:
# "where do I download MPFB" is asked most often by somebody whose MPFB is not
# working, so the client answers from its vendored copy and says so.
STATE_REASONS = {
    "absent": "MPFB is not loaded in this Blender instance, so its own web addresses could not "
              "be read; the addresses below are mpfb-mcp's vendored copy of them.",
    "not_initialized": "MPFB is loaded but did not finish initializing, and its weburls module "
                       "is not among the modules it managed to import; the addresses below are "
                       "mpfb-mcp's vendored copy of them.",
}

MISSING_MODULE_REASON = (
    "MPFB is loaded and initialized, but '{:s}' is not in sys.modules - MPFB normally imports "
    "its UI during register(), so this install is unusual. The addresses below are mpfb-mcp's "
    "vendored copy of them."
)


def _dotted(version):
    if version is None:
        return None
    return ".".join([str(part) for part in version])


def _read_weburls(module):
    """Every ``URL_`` constant on one module, and the names that were not strings."""
    found = dict()
    skipped = []
    for name in sorted(dir(module)):
        if not name.startswith(URL_PREFIX):
            continue
        value = getattr(module, name)
        if isinstance(value, str):
            found[name] = value
        else:
            # A URL_ name holding something other than a string is not an
            # address, but its absence still has to be accounted for.
            skipped.append(name)
    return (found, skipped)


def list_urls(params, resolution):  # pylint: disable=unused-argument
    """Read MPFB's web addresses, or say why they could not be read.

    Takes no parameters. Every state is a successful answer, including the two
    in which MPFB is not usable at all - which is what ``requires_mpfb=False``
    on this command's table entry is for.
    """
    result = {
        "state": resolution.state,
        "package": None,
        "version": None,
        "weburls_module": None,
        "weburls_read": False,
        "urls": None,
        "skipped_keys": None,
        "reason": STATE_REASONS.get(resolution.state),
    }

    if resolution.module is None:
        _LOG.debug("list_urls: MPFB is %s", resolution.state)
        return result

    result["package"] = resolution.module.__name__
    result["version"] = _dotted(getattr(resolution.module, "VERSION", None))

    # Attempted whatever the state is: a half-registered MPFB may still have
    # imported its UI, and reading a module that is already loaded costs nothing
    # and cannot make the install any more broken.
    module_name = resolution.module.__name__ + ".ui.weburls"
    result["weburls_module"] = module_name
    weburls = sys.modules.get(module_name)

    if weburls is None:
        if resolution.state == "ok":
            result["reason"] = MISSING_MODULE_REASON.format(module_name)
        return result

    found, skipped = _read_weburls(weburls)
    result["weburls_read"] = True
    result["urls"] = found
    result["skipped_keys"] = skipped
    result["reason"] = None

    _LOG.debug("list_urls: read %d address(es) from %s", len(found), module_name)
    return result
