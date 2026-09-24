"""
``create_human_from_preset``: build a **new** character from a save file.

**This creates a character; it does not load one into an existing character.**
``deserialize_from_dict()`` calls ``create_human()`` unconditionally, so a call
adds a new basemesh, a new rig and new garments to the scene and changes nothing
that was already there. The command is named for that, because "load a preset"
reads to an agent like "restore over what is there".

**Every settings dict starts from ``get_default_deserialization_settings()``.**
``deserialize_from_dict()`` reads eight keys with ``[]`` rather than ``.get()``
- ``mask_helpers``, ``detailed_helpers``, ``extra_vertex_groups``,
``feet_on_ground``, ``scale``, ``subdiv_levels``, ``load_clothes`` and
``material_instances`` - so a dict assembled from literals is one forgotten key
away from a ``KeyError`` raised from inside MPFB with a character half built.
This takes MPFB's own default and overwrites into it, and checks that the
default really carries all eight rather than assuming the install matches the
one this was written against. Two keys go the other way:
``override_clothes_model`` and ``override_eyes_model`` are honoured (behind
``in`` guards) and MPFB's own panel passes them, but they are **not** in that
default dict - so the vocabulary is wider than the defaults and these are added
rather than assumed to be there.

**``material_instances_policy`` follows MPFB's panel rather than the service's
default.** It is MPFB's ``material_instances`` setting, renamed because it is a
policy over skin types rather than ``mpfb_set_skin``'s bool of the same name.
``get_default_deserialization_settings()`` says ``NEVER``; the property MPFB's
own "from preset" panel is built from defaults to ``ENHANCED``. A character
loaded through this command should be the character the user would have got
from that panel, so ``ENHANCED`` is what an omitted argument means - and
``material_instances_policy_requested`` comes back beside ``_used`` and
``_service_default`` so the substitution is never silent.

**A preset naming an asset that is not installed is silent inside MPFB.**
``_check_add_clothes()`` and ``_check_add_bodyparts()`` call
``find_asset_absolute_path()`` and, on a miss, ``_LOG.warn()`` and carry on - so
a character comes back missing its hair and nothing in the scene says why. Every
asset the preset names is therefore resolved *here*, before the call, and
anything that does not resolve is reported as ``unresolved_assets``.

**Its failure is not a no-op, and that is the one place in the package where
losing that would be dangerous.** ``_check_add_rig()`` calls
``add_builtin_rig()`` / ``add_custom_rig()``, which raise when handed no
operator - and by then ``create_human()`` has already run, so the raise leaves a
naked character in the scene. The whole deserialization therefore runs inside a
``try``, and a failure reports what it raised together with
``objects_created``: every object that appeared while it ran, by name, so the
caller can clean up rather than guess. **A command that let that exception reach
the dispatcher would answer ``command_failed`` and say nothing about the
objects**, which is exactly the shape FR 032's requirement 3 forbids.

**The selection cannot be restored.** Deserialization ends with MPFB having
created and activated objects, and there is no prior state to restore to - the
same exception ``generate_rigify_rig`` has and for the same reason. So
``active_object_after`` is reported instead.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "create_human_from_preset",
)

import json
import os

import bpy

from ..log import get_logger
from ..shared import blender_data
from ..shared import mpfb_surface
from ..shared import preset_files
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_NUMBER
from ..validation import TYPE_STRING

_LOG = get_logger("commands.createhumanfrompreset")

# The eight keys deserialize_from_dict() reads with [] rather than .get(). Named
# here so that "the default dict really does carry all of them" is something
# this command checks rather than assumes.
REQUIRED_SETTINGS = (
    "mask_helpers", "detailed_helpers", "extra_vertex_groups", "feet_on_ground",
    "scale", "subdiv_levels", "load_clothes", "material_instances",
)

# MPFB's "from preset" panel default, which is not the service default. See this
# module's docstring.
PANEL_MATERIAL_INSTANCES = "ENHANCED"
MATERIAL_INSTANCES_VALUES = ("NEVER", "ENHANCED", "ENHANCEDMS")

# Which asset subdir each preset key is resolved against. These are the strings
# MPFB's own _check_add_* functions pass to find_asset_absolute_path(), not a
# derivation from the section table - MPFB does not derive them either, and a
# cleverer answer here would look in a different directory from the one the load
# is about to look in.
BODYPARTS = (
    ("eyes", "eyes", "Eyes"),
    ("eyelashes", "eyelashes", "Eyelashes"),
    ("eyebrows", "eyebrows", "Eyebrows"),
    ("tongue", "tongue", "Tongue"),
    ("teeth", "teeth", "Teeth"),
    ("hair", "hair", "Hair"),
)
CLOTHES_SUBDIR = "clothes"
PROXY_SUBDIR = "proxymeshes"
SKIN_SUBDIR = "skins"

# How many names a "no such preset" refusal offers back. A preset collection is
# tens of files, so this is a cap that will rarely bite - but an unbounded list
# inside an error message is how a refusal becomes the largest response the
# command can produce.
SUGGESTION_CAP = 50

# Each overridable argument, and the key MPFB's deserialization settings read it
# under. They were one spelling until FR 037 (R7) named the arguments by the
# glossary - material_instances is a policy over skin types, and the three
# "models" are the material types the other tools call skin_type and
# material_type - while the settings dict is MPFB's and keeps MPFB's names,
# which is also how settings_used reports it.
_SETTING_FOR = dict(
    override_rig="override_rig",
    override_skin_type="override_skin_model",
    override_clothes_material_type="override_clothes_model",
    override_eyes_material_type="override_eyes_model",
    load_clothes="load_clothes",
    scale="scale",
    material_instances_policy="material_instances",
)

# The four whose absence from the settings dict means "use the preset's".
_OVERRIDE_KEYS = ("override_rig", "override_skin_type",
                  "override_clothes_material_type", "override_eyes_material_type")

PARAMS = (
    Param("preset_name", TYPE_STRING, required=True,
          description="The preset's name, as list_presets reports it. Never a path."),
    Param("override_rig", TYPE_STRING, default=None, nullable=True,
          description="Use this rig identifier instead of the preset's. 'NONE' loads the "
                      "character without one."),
    Param("override_skin_type", TYPE_STRING, default=None, nullable=True,
          description="Use this skin type instead of the preset's."),
    Param("override_clothes_material_type", TYPE_STRING, default=None, nullable=True,
          description="Use this material type for garments and body parts instead of the "
                      "preset's."),
    Param("override_eyes_material_type", TYPE_STRING, default=None, nullable=True,
          description="Use this material type for the eyes instead of the preset's."),
    Param("load_clothes", TYPE_BOOLEAN, default=None, nullable=True,
          description="Load the garments the preset names. Omit for MPFB's own default."),
    Param("scale", TYPE_NUMBER, default=None, nullable=True,
          description="Basemesh scale factor. Omit for the preset's."),
    Param("material_instances_policy", TYPE_STRING, default=None, nullable=True,
          choices=MATERIAL_INSTANCES_VALUES,
          description="NEVER, ENHANCED or ENHANCEDMS. Omit for ENHANCED, which is MPFB's own "
                      "'from preset' panel default rather than the service's NEVER."),
)

SUMMARY = "Create a new character from a saved preset, with optional overrides."


def _resolve_asset(services, fragment, subdir):
    """Where MPFB will look for one asset the preset names, or ``None``.

    The same call the deserializer makes, so a miss here is the miss it will
    have. Matching is by *basename*, so which of two identically named files
    this finds is a coin toss - which is why the resolved path is reported
    rather than only whether it resolved.
    """
    if not fragment:
        return None
    try:
        return mpfb_surface.as_path(
            services["AssetService"].find_asset_absolute_path(str(fragment), subdir))
    except Exception:  # pylint: disable=broad-except
        return None


def _asset_expectations(services, human_info, load_clothes):
    """Every asset this preset names, with where it resolved to.

    Built before the deserialization rather than compared against the scene
    afterwards: an asset MPFB could not find leaves nothing behind to compare.
    """
    expectations = []
    for key, subdir, _object_type in BODYPARTS:
        fragment = human_info.get(key)
        if fragment and str(fragment).strip():
            expectations.append(dict(
                kind=key, fragment=str(fragment).strip(), asset_subdir=subdir,
                resolved_path=_resolve_asset(services, fragment, subdir), skipped=False))
    proxy = human_info.get("proxy")
    if proxy and str(proxy).strip():
        expectations.append(dict(
            kind="proxy", fragment=str(proxy).strip(), asset_subdir=PROXY_SUBDIR,
            resolved_path=_resolve_asset(services, proxy, PROXY_SUBDIR), skipped=False))
    for garment in human_info.get("clothes") or []:
        if not garment or not str(garment).strip():
            continue
        expectations.append(dict(
            kind="clothes", fragment=str(garment).strip(), asset_subdir=CLOTHES_SUBDIR,
            # Resolved even when it will be skipped, so that "you asked not to
            # load the clothes" and "the clothes are not installed" stay
            # distinguishable in one answer.
            resolved_path=_resolve_asset(services, garment, CLOTHES_SUBDIR),
            skipped=not load_clothes))
    skin = human_info.get("skin_mhmat")
    if skin and str(skin).strip():
        expectations.append(dict(
            kind="skin", fragment=str(skin).strip(), asset_subdir=SKIN_SUBDIR,
            resolved_path=_resolve_asset(services, skin, SKIN_SUBDIR), skipped=False))
    return expectations


def _object_record(general_properties, blender_object, kind):
    if blender_object is None:
        return None
    record = dict(kind=kind, object_name=str(blender_object.name))
    try:
        record["asset_source"] = mpfb_surface.as_path(general_properties.get_value(
            "asset_source", entity_reference=blender_object))
    except Exception:  # pylint: disable=broad-except
        record["asset_source"] = None
    return record


class _Request:
    """One call's resolved state, so the refusals can be read in one place."""

    __slots__ = ("confdir", "file_path", "name_rejection", "preset_exists", "human_info",
                 "parse_error", "settings", "service_defaults", "settings_error",
                 "missing_settings", "material_instances_used", "overrides_requested")


def _read_preset(request, params):
    """Parse the preset file, or record why it could not be parsed."""
    request.human_info = None
    request.parse_error = None
    if not request.preset_exists:
        return
    try:
        with open(request.file_path, "r", encoding="utf-8") as handle:
            request.human_info = json.load(handle)
    except Exception as error:  # pylint: disable=broad-except
        request.parse_error = str(error)
    if request.human_info is not None and not isinstance(request.human_info, dict):
        request.parse_error = "the file holds a {:s} rather than an object".format(
            type(request.human_info).__name__)
        request.human_info = None


def _resolve(services, params):
    """Everything that has to be true before a character is built."""
    request = _Request()
    request.overrides_requested = dict(
        override_rig=params["override_rig"],
        override_skin_type=params["override_skin_type"],
        override_clothes_material_type=params["override_clothes_material_type"],
        override_eyes_material_type=params["override_eyes_material_type"],
        load_clothes=params["load_clothes"],
        scale=params["scale"],
        material_instances_policy=params["material_instances_policy"],
    )

    request.confdir = preset_files.config_directory(services)
    request.name_rejection = preset_files.preset_name_rejection(params["preset_name"])
    request.file_path = None
    if request.name_rejection is None:
        request.file_path = preset_files.preset_path(request.confdir, params["preset_name"])
    request.preset_exists = bool(
        request.file_path is not None and os.path.isfile(request.file_path))

    _read_preset(request, params)

    # MPFB's defaults, asked for once and checked rather than trusted.
    request.settings = None
    request.service_defaults = None
    request.settings_error = None
    try:
        request.service_defaults = dict(
            services["HumanService"].get_default_deserialization_settings())
        request.settings = dict(request.service_defaults)
    except Exception as error:  # pylint: disable=broad-except
        request.settings_error = str(error)
    request.missing_settings = []
    if request.settings is not None:
        request.missing_settings = [
            key for key in REQUIRED_SETTINGS if key not in request.settings]

    request.material_instances_used = None
    if request.settings is not None:
        # The panel's default, not the service's. Reported either way.
        request.material_instances_used = request.overrides_requested["material_instances_policy"]
        if request.material_instances_used is None:
            request.material_instances_used = PANEL_MATERIAL_INSTANCES
    return request


def _blocked(params, request, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=request.preset_exists,
        ready=False,
        created=False,
        blocked_by=reason,
        preset_name=params["preset_name"],
        config_dir=request.confdir,
        path=request.file_path,
        basemesh_name=None,
        rig_object_name=None,
        active_object_after=None,
        objects_created=[],
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _refusal(services, params, request):  # pylint: disable=too-many-return-statements
    """The first refusal that applies, or ``None``."""
    def blocked(reason, text, **extra):
        return _blocked(params, request, reason, text, **extra)

    if request.name_rejection is not None:
        # Defence in depth: mpfb-mcp refuses this before a request is built.
        return blocked(
            "invalid_name",
            request.name_rejection + " A preset is always human.<name>.json in MPFB's user "
            "config directory, so a name that could become a path is refused rather than "
            "resolved.")
    if request.confdir is None or not os.path.isdir(request.confdir):
        return blocked(
            "config_dir_missing",
            "MPFB's user config directory {!r} does not exist, so no preset could be read. MPFB "
            "creates it when it loads, so this means the install is broken.".format(
                request.confdir))
    if not request.preset_exists:
        # A misspelled name is the likeliest way this is called wrongly, so the
        # refusal ends the guessing rather than only reporting it. The names
        # come from the directory rather than from MPFB's cached list: a preset
        # saved moments ago in another Blender is offered here, and the cache
        # would not have it.
        available = preset_files.scan_preset_names(request.confdir)
        return blocked(
            "preset_not_found",
            "No preset named '{!s}' exists in '{!s}'. available_presets names the {:d} of {:d} "
            "that do; mpfb_list_presets reports each one's age and size.".format(
                params["preset_name"], request.confdir,
                min(len(available), SUGGESTION_CAP), len(available)),
            available_presets=available[:SUGGESTION_CAP],
            available_preset_count=len(available))
    if request.human_info is None:
        return blocked(
            "preset_unreadable",
            "'{!s}' exists but could not be read as a character preset: {!s}. A preset is a JSON "
            "object written by MPFB; a truncated or hand-edited file looks like this.".format(
                request.file_path, request.parse_error),
            file=preset_files.file_facts(request.file_path))
    if request.settings is None:
        return blocked(
            "settings_unavailable",
            "HumanService.get_default_deserialization_settings() raised: {!s}. Nothing can be "
            "loaded without it - deserialize_from_dict() reads eight of its keys with [] rather "
            "than .get(), so a dict assembled here instead would fail somewhere inside MPFB with "
            "a character half built.".format(request.settings_error))
    if request.missing_settings:
        return blocked(
            "settings_incomplete",
            "MPFB's default deserialization settings are missing {:s}, which "
            "deserialize_from_dict() reads with [] rather than .get(). Loading would raise from "
            "inside MPFB with a character half built, so nothing was attempted. This is a "
            "version mismatch between MPFB and this tool.".format(
                ", ".join(request.missing_settings)),
            missing_settings=request.missing_settings,
            known_settings=sorted(request.settings.keys()))
    if request.material_instances_used not in MATERIAL_INSTANCES_VALUES:
        return blocked(
            "unknown_material_instances_policy",
            "'{!s}' is not a material_instances_policy MPFB knows, so nothing was loaded. "
            "known_material_instances_policies lists the three; _set_skin() tests the value with "
            "substring matches, so an unrecognised one silently means NEVER rather than "
            "failing.".format(request.overrides_requested["material_instances_policy"]),
            known_material_instances_policies=list(MATERIAL_INSTANCES_VALUES))
    if bpy.context.mode != "OBJECT":
        # Building a character runs operators, and bpy.ops polls on the
        # *context* mode - so an unrelated object left in edit mode fails them.
        return blocked(
            "not_object_mode",
            "Blender is in {:s} mode. Building a character runs operators that require OBJECT "
            "mode, so nothing was loaded. Leave edit mode and call again.".format(
                str(bpy.context.mode)))
    return None


def _settings_for(request, load_clothes):
    """MPFB's default dict with this call's overrides written into it."""
    settings = request.settings
    settings["load_clothes"] = load_clothes
    settings["material_instances"] = request.material_instances_used
    if request.overrides_requested["scale"] is not None:
        settings["scale"] = float(request.overrides_requested["scale"])
    for argument in _OVERRIDE_KEYS:
        key = _SETTING_FOR[argument]
        if request.overrides_requested[argument] is not None:
            settings[key] = request.overrides_requested[argument]
        elif key not in settings:
            # The two MPFB's defaults omit. "PRESET" is the sentinel
            # deserialize_from_dict() reads as "use what the preset says", and
            # it is what MPFB's own panel passes for both.
            settings[key] = "PRESET"
    return settings


def _equipped(services, general_properties, basemesh):
    """Every asset that ended up on the character, by kind."""
    object_service = services["ObjectService"]
    equipped = []
    for key, _subdir, object_type in BODYPARTS:
        found = object_service.find_object_of_type_amongst_nearest_relatives(
            basemesh, object_type)
        record = _object_record(general_properties, found, key)
        if record is not None:
            equipped.append(record)
    proxy_object = object_service.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Proxymeshes")
    proxy_record = _object_record(general_properties, proxy_object, "proxy")
    if proxy_record is not None:
        equipped.append(proxy_record)
    for garment in object_service.find_all_objects_of_type_amongst_nearest_relatives(
            basemesh, "Clothes") or []:
        record = _object_record(general_properties, garment, "clothes")
        if record is not None:
            equipped.append(record)
    return equipped


def _message_for(params, request, basemesh, rig_object, rig_identified_as, equipped,
                 unresolved_assets, load_clothes, preset_clothes):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Created '{!s}' from preset '{!s}'.".format(basemesh.name, params["preset_name"])]
    if rig_object is not None:
        parts.append(" It carries the rig '{!s}' ({!s}).".format(
            rig_object.name, rig_identified_as))
        if str(rig_identified_as or "").startswith("rigify."):
            parts.append(" That is a Rigify *meta* rig; finish it with "
                         "mpfb_generate_rigify_rig once nothing else needs adding.")
    if equipped:
        parts.append(" {:d} asset(s) were equipped with it.".format(len(equipped)))
    if unresolved_assets:
        parts.append(
            " {:d} asset(s) the preset names are not installed here and were silently skipped by "
            "MPFB: unresolved_assets names them. The character is otherwise complete.".format(
                len(unresolved_assets)))
    if not load_clothes and preset_clothes:
        parts.append(" load_clothes was false, so the {:d} garment(s) in the preset were not "
                     "loaded.".format(len(preset_clothes)))
    parts.append(
        " The selection was not restored - deserialization activates what it creates, and there "
        "was no prior state to return to; active_object_after says what is active now.")
    return "".join(parts)


def create_human_from_preset(params, resolution):  # pylint: disable=too-many-locals
    """Build one character from one preset, and name what a failure left behind."""
    services = resolution.services
    object_service = services["ObjectService"]
    general_properties = mpfb_surface.general_object_properties(services)

    request = _resolve(services, params)

    refused = _refusal(services, params, request)
    if refused is not None:
        _LOG.debug("create_human_from_preset: refused %r", refused["blocked_by"])
        return refused

    load_clothes = request.overrides_requested["load_clothes"]
    if load_clothes is None:
        load_clothes = bool(request.settings["load_clothes"])
    settings = _settings_for(request, load_clothes)

    expectations = _asset_expectations(services, request.human_info, load_clothes)
    unresolved_assets = [entry for entry in expectations
                         if entry["resolved_path"] is None and not entry["skipped"]]

    before = blender_data.object_names()
    basemesh = None
    failure = None
    try:
        basemesh = services["HumanService"].deserialize_from_json_file(
            request.file_path, settings)
    except Exception as error:  # pylint: disable=broad-except
        failure = type(error).__name__ + ": " + str(error)

    created = sorted(blender_data.object_names() - before)
    active_after = bpy.context.view_layer.objects.active
    active_object_after = None if active_after is None else str(active_after.name)

    if basemesh is None:
        return _blocked(
            params, request, "deserialization_failed",
            "MPFB raised while building a character from '{!s}': {!s} A character is built in "
            "stages - mesh, targets, rig, body parts, clothes, materials - so what was made "
            "before the failure is still in the scene: objects_created names it, and there is no "
            "undo for it across this socket. The commonest cause is a rig the preset names and "
            "this Blender does not have, since MPFB's rig adders raise rather than degrade; "
            "mpfb_list_rigs says which rigs exist here, and override_rig='NONE' loads the "
            "character without one.".format(params["preset_name"], failure),
            objects_created=created,
            active_object_after=active_object_after,
            preset_rig=request.human_info.get("rig") or None,
            unresolved_assets=unresolved_assets)

    rig_object = object_service.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Skeleton")
    rig_identified_as = None
    if rig_object is not None:
        try:
            rig_identified_as = services["RigService"].identify_rig(rig_object)
        except Exception:  # pylint: disable=broad-except
            rig_identified_as = None

    equipped = _equipped(services, general_properties, basemesh)

    try:
        material_service = services["MaterialService"]
        skin_identified_as = material_service.identify_material(
            material_service.get_material(basemesh, 0))
    except Exception:  # pylint: disable=broad-except
        skin_identified_as = None

    # Beside each override the caller passed, what the preset itself held - so
    # "I overrode the rig" and "the preset had no rig" are one read apart.
    preset_values = dict(
        override_rig=request.human_info.get("rig") or None,
        override_skin_type=request.human_info.get("skin_material_type") or None,
        override_clothes_material_type=request.human_info.get("clothes_material_type") or None,
        override_eyes_material_type=request.human_info.get("eyes_material_type") or None,
        load_clothes=list(request.human_info.get("clothes") or []),
        scale=None,
        material_instances_policy=None,
    )
    overrides = dict()
    for argument in request.overrides_requested:
        overrides[argument] = dict(
            requested=request.overrides_requested[argument],
            preset_value=preset_values[argument],
            used=settings.get(_SETTING_FOR[argument]),
        )

    _LOG.debug("create_human_from_preset: built %r from %r", basemesh.name, params["preset_name"])

    result = dict(
        found=True,
        ready=True,
        created=True,
        blocked_by=None,
        preset_name=params["preset_name"],
        config_dir=request.confdir,
        path=request.file_path,
        basemesh_name=str(basemesh.name),
        rig_object_name=None if rig_object is None else str(rig_object.name),
        rig_identified_as=rig_identified_as,
        equipped_assets=equipped,
        unresolved_assets=unresolved_assets,
        skin_material_identified_as=skin_identified_as,
        overrides=overrides,
        material_instances_policy_requested=request.overrides_requested[
            "material_instances_policy"],
        material_instances_policy_used=request.material_instances_used,
        material_instances_policy_service_default=request.service_defaults.get(
            "material_instances"),
        known_material_instances_policies=list(MATERIAL_INSTANCES_VALUES),
        settings_used=settings,
        objects_created=created,
        active_object_after=active_object_after,
        message=_message_for(params, request, basemesh, rig_object, rig_identified_as,
                             equipped, unresolved_assets, load_clothes,
                             preset_values["load_clothes"]),
    )

    # The verb is "created". See shared/performed.py.
    return with_performed(result, result["created"])
