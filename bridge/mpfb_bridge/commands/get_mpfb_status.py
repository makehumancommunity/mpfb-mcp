"""
``get_mpfb_status``: how MPFB is installed and configured, in three tiers.

**Not ``get_status``, and the difference is the point.** That command reports
*this bridge* - which protocol it speaks, which version it is, whether MPFB
looks present - and is the first thing a client asks. This one reports *MPFB*:
where it is installed, which asset roots it will search, which packs are there,
whether this Blender is new enough for it, whether Rigify is available. Two
commands answering "status" about two different pieces of software would be a
collision that is cheap to avoid now and permanent later, so the tool-to-
command naming convention is broken here deliberately and the exception is
written into ``commands/table.py`` beside the entry.

It is the **second** command in the table declaring ``requires_mpfb=False``
that is not about the bridge itself, and the first migrated one. That is its
whole value: a status tool gated on the thing it reports about answers only the
question nobody needs to ask. The dispatcher's ``mpfb_unavailable``
precondition must therefore never fire for it, which is what lets ``absent``
and ``not_initialized`` come back as ordinary successful answers.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
, down to which keys exist in which state. Three of those are worth naming,
because each is a thing a reimplementation would "fix":

- **The tiers are shapes, not nulls.** ``version`` and ``build_info`` are
  *absent* until a module is found, and everything in the third tier is absent
  until services are. A uniform shape mostly filled with nulls would say "we
  looked at the asset roots and there are none" on an install where nothing was
  ever looked at.
- **``enabled`` is the field that earns its place.** MPFB's ``unregister()``
  leaves ``MPFB_CONTEXTUAL_INFORMATION`` populated in ``sys.modules``, so a
  *disabled* MPFB still classifies as ``ok``; Blender's add-on preferences are
  the only thing that tells the two apart.
- **Every path is coerced with ``str()``.** ``LocationService`` is annotated as
  returning ``str`` throughout and ``get_mpfb_root()`` hands back a
  ``pathlib.Path``. The dispatcher serializes a result before it commits to an
  answer, so one uncoerced path would turn this whole answer into a
  ``result_not_serializable`` envelope - which is precisely the state in which
  a caller needs it least.

``check_for_rigify()`` logs a warning per missing Rigify component when Rigify
is unavailable. That is expected here and is not an error.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_mpfb_status",
)


import bpy

from ..log import get_logger
from ..shared import mpfb_surface

_LOG = get_logger("commands.getmpfbstatus")

PARAMS = ()

SUMMARY = ("Report whether MPFB is loaded and usable in this Blender, and how it is configured. "
           "For the bridge's own state, ask get_status instead.")


def _dotted(version):
    """A version tuple as the dotted string a human recognises, or ``None``."""
    if version is None:
        return None
    return ".".join([str(part) for part in version])


def _str_path(path):
    """One path, coerced at the point it enters the answer."""
    if path is None:
        return None
    return str(path)


def _path_entry(path):
    """One configured path, and whether it was configured at all.

    ``get_second_root()`` and ``get_mh_user_data()`` return ``None`` when unset;
    the flag separates "not configured" from "configured but not on disk".
    """
    return {"path": _str_path(path), "configured": bool(path)}


def _module_tier(result, module):
    """What is readable off the module object, which survives not_initialized."""
    # __name__ rather than MPFB_CONTEXTUAL_INFORMATION["__package__"]: the same
    # value on a healthy install, and readable in the not_initialized state too,
    # where the dict may not exist at all.
    result["package"] = module.__name__
    result["enabled"] = module.__name__ in bpy.context.preferences.addons
    result["version"] = _dotted(getattr(module, "VERSION", None))
    result["build_info"] = getattr(module, "BUILD_INFO", None)


def _services_tier(result, services):
    """What needs MPFB to have finished starting: paths, roots, packs, Rigify."""
    location_service = services["LocationService"]
    asset_service = services["AssetService"]
    system_service = services["SystemService"]

    # LOWEST_FUNCTIONAL_BLENDER_VERSION is a module-level constant in
    # systemservice.py, not a member of SystemService and not in SERVICES.
    lowest_blender = mpfb_surface.module_level(
        services, "SystemService", "LOWEST_FUNCTIONAL_BLENDER_VERSION", fallback=None)

    # Kept alongside build_info: a build rewrites BUILD_INFO *and* drops test/,
    # so the two disagreeing points at an unusual or partial install.
    result["is_source_dist"] = bool(location_service.is_source_dist())
    result["addon_installation_path"] = _str_path(location_service.get_mpfb_root())
    result["paths"] = {
        "mpfb_data": _path_entry(location_service.get_mpfb_data()),
        "user_home": _path_entry(location_service.get_user_home()),
        "user_data": _path_entry(location_service.get_user_data()),
        "user_config": _path_entry(location_service.get_user_config()),
        "user_cache": _path_entry(location_service.get_user_cache()),
        "log_dir": _path_entry(location_service.get_log_dir()),
        # Scene-scoped, not global: read off bpy.context.scene, so it changes
        # when another .blend is loaded. Do not cache this across scene loads.
        "second_root": _path_entry(location_service.get_second_root()),
        "mh_user_data": _path_entry(location_service.get_mh_user_data()),
    }
    # paths shows what is *configured*; asset_roots shows what MPFB will
    # actually search, already filtered to directories that exist.
    result["asset_roots"] = [
        _str_path(root) for root in asset_service.get_available_data_roots()]
    pack_names = list(asset_service.get_pack_names())
    result["asset_packs"] = {
        "count": len(pack_names),
        "names": pack_names,
        "system_assets_pack_installed": bool(asset_service.system_assets_pack_is_installed()),
    }
    result["blender"]["platform"] = system_service.deduce_platform()
    # Answer the compatibility question rather than handing back two versions to
    # compare - an incompatible Blender is a prime cause of not_initialized.
    result["blender"]["meets_mpfb_minimum"] = bool(system_service.is_blender_version_at_least())
    result["blender"]["mpfb_minimum_version"] = _dotted(lowest_blender)
    result["rigify_available"] = bool(system_service.check_for_rigify())


def get_mpfb_status(params, resolution):  # pylint: disable=unused-argument
    """Classify this Blender's MPFB install and describe how it is configured.

    Takes no parameters. The three tiers map onto :class:`Resolution`'s
    progressive fields exactly - ``bpy`` alone, then ``resolution.module``,
    then ``resolution.services`` - which is what makes MPFB's absence a
    successful answer rather than an error.
    """
    result = {
        "state": resolution.state,
        "message": resolution.message,
        "candidate_modules": list(resolution.candidates),
        "package": None,
        "enabled": None,
        "blender": {"version": bpy.app.version_string},
    }

    if resolution.module is not None:
        _module_tier(result, resolution.module)

    if resolution.services is not None:
        _services_tier(result, resolution.services)

    _LOG.debug("get_mpfb_status: %s (%d candidate modules)",
               resolution.state, len(resolution.candidates))
    return result
