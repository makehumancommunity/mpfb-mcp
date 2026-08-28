"""
Payload for ``mpfb_get_status``: reports what MPFB is doing in this Blender.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the non-raising bootstrap
(see ``mpfbmcp.codegen.assemble``). A linter will flag several names as
undefined because the assembler binds them ahead of this file:

- ``_mpfb_state``, ``_mpfb_candidates``, ``_mpfb_module``, ``_mpfb_services``
  - the classification from the non-raising bootstrap; the latter two may be
  None. ``sys`` is likewise already imported by that bootstrap.
- ``PARAMS`` - bound but unused: this tool takes no arguments.

Builds the ``result`` dict in three tiers of fields: those needing nothing but
bpy (available in every state), those readable off the mpfb module object
(available once it is found), and those needing services (available only when
initialized). That build-up is what makes MPFB's absence a successful answer
rather than an error. MPFB submodules are deliberately never imported to fill
in the middle tier - see ``mpfbmcp.codegen.bootstrap``.
"""

import bpy

def _mpfb_dotted(version):
    if version is None:
        return None
    return ".".join([str(part) for part in version])

def _mpfb_str_path(path):
    # LocationService is annotated as returning str throughout, but
    # get_mpfb_root() hands back a pathlib.Path (its backing field is a Path and
    # the shared _return_path() passes it through unchanged when no sub-path is
    # given). That is not JSON-serializable, so coerce every path we report.
    if path is None:
        return None
    return str(path)

def _mpfb_path_entry(path):
    # get_second_root() and get_mh_user_data() return None when unset; the flag
    # separates "not configured" from "configured but does not exist on disk".
    return {"path": _mpfb_str_path(path), "configured": bool(path)}

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
    result["addon_installation_path"] = _mpfb_str_path(
        _mpfb_location_service.get_mpfb_root())
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
    result["asset_roots"] = [
        _mpfb_str_path(_mpfb_root) for _mpfb_root in _mpfb_asset_service.get_available_data_roots()]
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
