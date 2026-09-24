"""
Keeping MPFB's expressions-library panel in step with what a command changed.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/``.

MPFB's expressions-library panel draws one slider per expression file, and the
sliders are **scene properties registered once**, when
``ui/apply_assets/useexpression`` is imported. Two functions in that module keep
the panel agreeing with the character, and every path inside MPFB that changes
the stack or the library calls one of them:

- ``write_slider_values(scene, stack)`` sets the sliders from a stack.
  ``HumanService._apply_expressions_from_human_info`` calls it after a preset
  load. An ``apply_expressions`` that skipped it would leave MPFB's panel
  showing weights the character does not have, in the one place a human is
  looking.
- ``refresh_expression_sliders()`` registers a slider for any file that appeared
  since. MPFB's composer save operator calls it. A ``save_expression`` that
  skipped it would leave the new file without a slider until Blender restarts -
  and ``write_slider_values`` silently ignores a stack row with no slider, so
  the gap would compound.

**This is the third case of reaching a UI module, and the first that calls
one.** ``list_urls`` *reads* ``<root>.ui.weburls``, a table of constants. This
calls functions for their side effect on MPFB's own UI state, one of which
registers Blender properties. What makes it acceptable is that it is exactly
what MPFB itself does, from exactly the places it does it, and the rules that
bind the ``weburls`` read bind this too, per
[architecture.md](../../../specifications/architecture.md#a-ui-module-with-no-service-behind-it):

- the module is found with ``sys.modules.get()``, the root coming from the
  resolver's module scan, and **never imported** - on an initialized install
  MPFB imported it during ``register()``, and FR 027's live check confirmed it
  is there in both a windowed and a headless Blender;
- a miss is an ordinary answer, never a reason to import;
- each call is wrapped the way MPFB wraps it, since MPFB treats a failure here
  as cosmetic and so does this;
- the outcome is **reported**, as ``panel_synced`` with a ``panel_sync_reason``
  when it is false, rather than left implicit.

Takes the MPFB root package name rather than ``services``: the module is
addressed by where MPFB lives, not by anything a service knows.
"""

__all__ = (
    "PANEL_MODULE_SUFFIX",
    "refresh_sliders",
    "write_slider_values",
)

import sys

import bpy

PANEL_MODULE_SUFFIX = ".ui.apply_assets.useexpression"


def _panel_module(root_name):
    """The loaded ``useexpression`` module and its name, or ``None`` and the name."""
    module_name = root_name + PANEL_MODULE_SUFFIX
    return sys.modules.get(module_name), module_name


def _missing(module_name):
    return ("'{:s}' is not in sys.modules, so MPFB's expressions-library panel could not "
            "be updated. MPFB normally imports it during register(); this is left alone "
            "rather than imported.".format(module_name))


def write_slider_values(root_name, stack):
    """Sync the panel's sliders to ``stack``. Returns ``(synced, reason)``."""
    module, module_name = _panel_module(root_name)
    if module is None:
        return False, _missing(module_name)
    scene = bpy.context.scene
    if scene is None:
        return False, "There is no current scene, so there are no panel sliders to update."
    try:
        module.write_slider_values(scene, stack)
    except Exception as error:  # pylint: disable=broad-except
        return False, "MPFB's write_slider_values() raised: {:s}".format(str(error))
    return True, None


def refresh_sliders(root_name):
    """Register a slider for any new expression file. Returns ``(synced, reason, added)``."""
    module, module_name = _panel_module(root_name)
    if module is None:
        return False, _missing(module_name), 0
    try:
        added = module.refresh_expression_sliders()
    except Exception as error:  # pylint: disable=broad-except
        return False, "MPFB's refresh_expression_sliders() raised: {:s}".format(str(error)), 0
    return True, None, int(added or 0)
