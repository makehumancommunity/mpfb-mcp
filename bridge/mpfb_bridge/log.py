"""
The bridge's own logger, deliberately not MPFB's.

MPFB's modules open with ``_LOG = LogService.get_logger("services.objectservice")``
and this add-on copies that shape, because a MakeHuman developer reading
``bridge/`` should recognise where the logger comes from. What it cannot copy is
the *dependency*: the bridge's first command answers whether MPFB is present at
all, so it must be able to report "MPFB is missing" without asking MPFB for a
logger to report it with.

So the idiom is MPFB's and the backing is the standard library. Names are dotted
below a single ``mpfb_bridge`` root the way MPFB's are dotted below ``mpfb``, and
nothing here attaches a handler - Blender's own console is the destination, and a
library that installs handlers on somebody else's root logger is a nuisance.
"""

__all__ = (
    "get_logger",
    "ROOT_LOGGER_NAME",
)

import logging

ROOT_LOGGER_NAME = "mpfb_bridge"


def get_logger(name):
    """Return the logger for one module, named the way MPFB names its own.

    ``name`` is the dotted suffix identifying the module, without the root: pass
    ``"commandserver"`` and get ``mpfb_bridge.commandserver``.
    """
    return logging.getLogger("{:s}.{:s}".format(ROOT_LOGGER_NAME, name))
