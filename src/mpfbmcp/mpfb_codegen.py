"""
Code generation for MPFB calls run inside Blender via blender_mcp.

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

- ``_MPFB_BOOTSTRAP`` raises ``RuntimeError`` unless MPFB is fully
  initialized. Use it for tools that cannot do their job without MPFB.
- ``_MPFB_STATUS_BOOTSTRAP`` never raises; it classifies the situation into
  ``absent`` / ``not_initialized`` / ``ok``. Use it for tools whose job is
  partly *to answer* whether MPFB is there at all.

Generated code must resolve services only through the ``SERVICES`` dict, never
by importing MPFB submodules directly: several of them have import-time side
effects (``locationservice.py`` ends by creating directories on disk).
"""

from __future__ import annotations

__all__ = (
    "build_create_human_code",
    "build_get_status_code",
)

import json

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
_MPFB_BOOTSTRAP = _MPFB_MODULE_SCAN + """

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
_MPFB_STATUS_BOOTSTRAP = _MPFB_MODULE_SCAN + """

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

# Builds the `result` dict for mpfb_get_status. Three tiers of fields: those
# needing nothing but bpy (available in every state), those readable off the
# mpfb module object (available once it is found), and those needing services
# (available only when initialized). MPFB submodules are deliberately never
# imported to fill in the middle tier - see this module's docstring.
_MPFB_STATUS_BODY = """
import bpy

def _mpfb_dotted(version):
    if version is None:
        return None
    return ".".join([str(part) for part in version])

def _mpfb_path_entry(path):
    # get_second_root() and get_mh_user_data() return None when unset; the flag
    # separates "not configured" from "configured but does not exist on disk".
    return {"path": path, "configured": bool(path)}

_MPFB_STATE_MESSAGES = {
    "absent": "MPFB is not loaded in this Blender instance: no loaded module name ends in "
              "'mpfb'. Install and enable the MPFB extension, then try again.",
    "not_initialized": "MPFB is loaded but did not finish initializing, so none of its services "
                       "are available. Check Blender's console for errors raised during MPFB "
                       "registration, and check whether this Blender version is new enough for "
                       "this MPFB version.",
    "ok": "MPFB is loaded and initialized.",
}

result = {
    "state": _mpfb_state,
    "message": _MPFB_STATE_MESSAGES[_mpfb_state],
    "candidate_modules": list(_mpfb_candidates),
    "package": None,
    "enabled": None,
    "blender": {"version": bpy.app.version_string},
}

if _mpfb_module is not None:
    # __name__ rather than MPFB_CONTEXTUAL_INFORMATION["__package__"]: same value,
    # but readable in the not_initialized state too, where the dict may be None.
    result["package"] = _mpfb_module.__name__
    # unregister() leaves MPFB_CONTEXTUAL_INFORMATION populated in sys.modules, so a
    # disabled MPFB still reports state "ok"; this is what tells the two apart.
    result["enabled"] = _mpfb_module.__name__ in bpy.context.preferences.addons
    result["version"] = _mpfb_dotted(getattr(_mpfb_module, "VERSION", None))
    result["build_info"] = getattr(_mpfb_module, "BUILD_INFO", None)

if _mpfb_services is not None:
    _mpfb_location_service = _mpfb_services["LocationService"]
    _mpfb_asset_service = _mpfb_services["AssetService"]
    _mpfb_system_service = _mpfb_services["SystemService"]

    # LOWEST_FUNCTIONAL_BLENDER_VERSION is a module-level constant in
    # systemservice.py, not a member of SystemService and not in SERVICES. The
    # module is necessarily already imported, since SystemService resolved.
    _mpfb_lowest_blender = getattr(
        sys.modules[_mpfb_system_service.__module__],
        "LOWEST_FUNCTIONAL_BLENDER_VERSION",
        None,
    )

    # Kept alongside build_info: a build rewrites BUILD_INFO *and* drops test/, so
    # the two disagreeing points at an unusual or partial install.
    result["is_source_dist"] = bool(_mpfb_location_service.is_source_dist())
    result["addon_installation_path"] = _mpfb_location_service.get_mpfb_root()
    result["paths"] = {
        "mpfb_data": _mpfb_path_entry(_mpfb_location_service.get_mpfb_data()),
        "user_home": _mpfb_path_entry(_mpfb_location_service.get_user_home()),
        "user_data": _mpfb_path_entry(_mpfb_location_service.get_user_data()),
        "user_config": _mpfb_path_entry(_mpfb_location_service.get_user_config()),
        "user_cache": _mpfb_path_entry(_mpfb_location_service.get_user_cache()),
        "log_dir": _mpfb_path_entry(_mpfb_location_service.get_log_dir()),
        # Scene-scoped, not global: read off bpy.context.scene, so it changes when
        # another .blend is loaded. Do not cache this result across scene loads.
        "second_root": _mpfb_path_entry(_mpfb_location_service.get_second_root()),
        "mh_user_data": _mpfb_path_entry(_mpfb_location_service.get_mh_user_data()),
    }
    # paths shows what is *configured*; asset_roots shows what MPFB will actually
    # search (already filtered to directories that exist).
    result["asset_roots"] = list(_mpfb_asset_service.get_available_data_roots())
    _mpfb_pack_names = list(_mpfb_asset_service.get_pack_names())
    result["asset_packs"] = {
        "count": len(_mpfb_pack_names),
        "names": _mpfb_pack_names,
        "system_assets_pack_installed": bool(
            _mpfb_asset_service.system_assets_pack_is_installed()),
    }
    result["blender"]["platform"] = _mpfb_system_service.deduce_platform()
    # Answer the compatibility question rather than handing back two versions to
    # compare - an incompatible Blender is a prime cause of not_initialized.
    result["blender"]["meets_mpfb_minimum"] = bool(
        _mpfb_system_service.is_blender_version_at_least())
    result["blender"]["mpfb_minimum_version"] = _mpfb_dotted(_mpfb_lowest_blender)
    # Logs a warning per missing Rigify component when Rigify is unavailable;
    # that is expected here and not an error.
    result["rigify_available"] = bool(_mpfb_system_service.check_for_rigify())
"""


def build_create_human_code(macro_detail_dict: dict[str, object], scale: float) -> str:
    """
    Build the Python source to send to blender_mcp for ``HumanService.create_human()``.

    Uses ``create_human()``'s own defaults for ``mask_helpers``,
    ``detailed_helpers``, ``extra_vertex_groups`` and ``feet_on_ground``; only
    ``scale`` and ``macro_detail_dict`` are parameterized here.
    """
    return "{bootstrap}\n\nHumanService = _MPFB_SERVICES[\"HumanService\"]\n\nbasemesh = HumanService.create_human(scale={scale!r}, macro_detail_dict={macro!s})\n\nresult = {{\n    \"object_name\": basemesh.name,\n    \"vertex_count\": len(basemesh.data.vertices),\n    \"location\": list(basemesh.location),\n    \"macro_detail_dict\": {macro!s},\n}}\n".format(
        bootstrap=_MPFB_BOOTSTRAP,
        scale=scale,
        macro=json.dumps(macro_detail_dict),
    )


def build_get_status_code() -> str:
    """
    Build the Python source to send to blender_mcp for ``mpfb_get_status``.

    Takes no parameters: the whole point is to report what is there. The
    generated code always leaves a ``result`` dict bound, whether or not MPFB
    is present or initialized - the caller reads ``result["state"]`` rather
    than relying on an exception.
    """
    return "{bootstrap}\n{body}".format(
        bootstrap=_MPFB_STATUS_BOOTSTRAP,
        body=_MPFB_STATUS_BODY,
    )
