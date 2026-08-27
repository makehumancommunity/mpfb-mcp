"""
Code generation for MPFB calls run inside Blender via blender_mcp.

MPFB is a Blender *extension*, so it is only reachable via relative imports
from within its own package - there is no stable, guessable absolute module
path (the top-level package name depends on which extension repository the
user installed it from, e.g. ``bl_ext.user_default.mpfb``). MPFB documents a
workaround for this in ``mpfb/__init__.py`` and uses it itself in
``test/tests/__init__.py``: scan ``sys.modules`` for a module whose name ends
with ``"mpfb"``, then pull classes out of the ``MPFB_CONTEXTUAL_INFORMATION``
dict it publishes on that module. ``_MPFB_BOOTSTRAP`` below is that same
pattern, reproduced so generated code can resolve ``HumanService`` without
knowing MPFB's install path.
"""

from __future__ import annotations

__all__ = (
    "build_create_human_code",
)

import json

# Resolves MPFB's HumanService and binds it to `HumanService`, or raises
# RuntimeError with a message pointing at the likely cause (extension not
# installed/enabled). Mirrors mpfb2/test/tests/__init__.py's dynamic_import().
_MPFB_BOOTSTRAP = """
import importlib, sys

def _mpfb_dynamic_import(absolute_package_str, key):
    for amod in sys.modules:
        if amod.endswith(absolute_package_str):
            mod = importlib.import_module(amod)
            if not hasattr(mod, key):
                raise AttributeError("Module {} does not have attribute {}".format(amod, key))
            return getattr(mod, key)
    raise RuntimeError(
        "No loaded module ends with 'mpfb'. Is the MPFB extension installed and enabled in "
        "this Blender instance?"
    )

_MPFB_CONTEXTUAL_INFORMATION = _mpfb_dynamic_import("mpfb", "MPFB_CONTEXTUAL_INFORMATION")
HumanService = _MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["HumanService"]
""".strip()


def build_create_human_code(macro_detail_dict: dict[str, object], scale: float) -> str:
    """
    Build the Python source to send to blender_mcp for ``HumanService.create_human()``.

    Uses ``create_human()``'s own defaults for ``mask_helpers``,
    ``detailed_helpers``, ``extra_vertex_groups`` and ``feet_on_ground``; only
    ``scale`` and ``macro_detail_dict`` are parameterized here.
    """
    return "{bootstrap}\n\nbasemesh = HumanService.create_human(scale={scale!r}, macro_detail_dict={macro!s})\n\nresult = {{\n    \"object_name\": basemesh.name,\n    \"vertex_count\": len(basemesh.data.vertices),\n    \"location\": list(basemesh.location),\n    \"macro_detail_dict\": {macro!s},\n}}\n".format(
        bootstrap=_MPFB_BOOTSTRAP,
        scale=scale,
        macro=json.dumps(macro_detail_dict),
    )
