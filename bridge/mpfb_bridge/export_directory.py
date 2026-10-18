"""
Where an exported file goes: the directory the **human** chose, never the caller.

``export_character`` writes a file another application opens, and it takes only
a *name* for it, as ``save_preset`` and ``save_expression`` do. What the
directory is cannot come from the request: a caller-supplied path would let
anything that reaches this socket write anywhere Blender can. It cannot come
from mpfb-mcp's environment either, since that is the MCP client's
configuration, which an agent may be able to edit. So it comes from here, the
add-on, which only the person who started the bridge configures
([FR 039](../../feature-requests/done/039-exporting-characters/README.md)):

- ``--export-dir`` on ``blender --background --command mpfb_bridge``, for a
  Blender with no preferences window worth using (:func:`set_command_line`);
- otherwise the ``export_directory`` preference on the add-on's preferences
  panel, beside host and port;
- otherwise ``<MPFB user data>/exports``, which the command creates on first use.

The command line wins over the preference because it is the more specific and
the more recent choice: a headless run started with ``--export-dir`` reads the
same ``userpref.blend`` a windowed Blender saved.

**A directory the human named and that does not exist is reported, not
created.** A typo in a preference should not become a new directory tree; the
command refuses with ``export_directory_missing``. Only the default is created,
as MPFB creates its own user data directories.

This is a module of its own rather than a part of ``ui.py`` or ``cli.py``
because both of those write the choice and a command reads it, and a command
importing the UI module would drag ``bpy.types`` registration into every
dispatch. It reads plain Blender preferences and nothing out of MPFB; the
default directory is passed in by the command, which has MPFB's
``LocationService``.
"""

__all__ = (
    "RESOLVED_BY_COMMAND_LINE",
    "RESOLVED_BY_DEFAULT",
    "RESOLVED_BY_PREFERENCES",
    "preference_value",
    "resolve",
    "set_command_line",
)

import os

import bpy

RESOLVED_BY_COMMAND_LINE = "command_line"
RESOLVED_BY_PREFERENCES = "preferences"
RESOLVED_BY_DEFAULT = "default"

# The add-on's package, which is what Blender keys its preferences by. This
# module sits at the package root, so its own __package__ is that name.
_ADDON_PACKAGE = __package__


class _State:
    """The ``--export-dir`` of the headless loop, for as long as it runs."""

    command_line = None


def set_command_line(directory):
    """Record ``--export-dir``, or clear it with ``None``. Called by ``cli.py`` only."""
    _State.command_line = directory or None


def preference_value():
    """The preference as the human typed it, or ``""`` when unset or unreadable.

    Unreadable covers the add-on not being enabled in the preferences being
    read, which happens to a test harness that registered the add-on for one
    process: there is then no preference to have set.
    """
    addon = bpy.context.preferences.addons.get(_ADDON_PACKAGE)
    if addon is None or addon.preferences is None:
        return ""
    return str(getattr(addon.preferences, "export_directory", "") or "")


def _absolute(directory):
    """A ``DIR_PATH`` value as an absolute path: ``//`` is relative to the open .blend."""
    if directory.startswith("//"):
        directory = bpy.path.abspath(directory)
    return os.path.abspath(os.path.expanduser(directory))


def resolve(default_directory):
    """``(directory, resolved_by, exists)``: where an export goes, and who chose it.

    ``default_directory`` is ``<MPFB user data>/exports``, passed in by the
    command. ``exists`` is reported rather than acted on, because whether a
    missing directory is a refusal or something to create depends on who chose
    it, and saying so is the command's job.
    """
    if _State.command_line:
        directory = _absolute(_State.command_line)
        return (directory, RESOLVED_BY_COMMAND_LINE, os.path.isdir(directory))
    preference = preference_value().strip()
    if preference:
        directory = _absolute(preference)
        return (directory, RESOLVED_BY_PREFERENCES, os.path.isdir(directory))
    directory = os.path.abspath(str(default_directory))
    return (directory, RESOLVED_BY_DEFAULT, os.path.isdir(directory))
