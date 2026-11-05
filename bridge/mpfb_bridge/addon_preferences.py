"""
This add-on's preferences, or ``None`` when there are none to read.

There are two states in which the add-on's code runs without any: a test harness
that registered it for one process, and ``--addons`` on Blender's command line,
which registers the add-on and leaves ``preferences.addons`` with no entry for it
(measured on ``--factory-startup --addons``, FR 058). Three modules read a
preference from places where neither may raise, so they read it through here:
``export_directory``, ``cli`` and ``autostart``.
"""

__all__ = (
    "read",
)

import bpy

# The add-on's package, which is what Blender keys its preferences by. This
# module sits at the package root, so its own __package__ is that name.
_ADDON_PACKAGE = __package__


def read():
    """The ``MPFB_BRIDGE_Preferences`` of the running Blender, or ``None``."""
    addon = bpy.context.preferences.addons.get(_ADDON_PACKAGE)
    if addon is None:
        return None
    return addon.preferences
