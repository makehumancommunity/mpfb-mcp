"""
Payload for ``mpfb_create_human_from_preset``: build a new character from a save file.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag four names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name`` and the seven
  overrides.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap (unused here, but bound).
- ``with_performed()`` - from the shared fragment ``performed.py``, named by
  every mutating payload. It stamps the uniform ``performed`` flag onto the
  finished answer, in the last line of this file.

...and a further set from the shared fragment ``preset_files.py``:
``preset_name_rejection()``, ``config_directory()``, ``preset_path()``,
``mpfb_presets()``, ``scan_preset_names()`` and ``file_facts()``.

**This creates a character; it does not load one into an existing character.**
``deserialize_from_dict()`` calls ``create_human()`` unconditionally, so a call
adds a new basemesh, a new rig and new garments to the scene and changes nothing
that was already there. The tool is named for that and says it in its first
sentence, because "load a preset" reads to an agent like "restore over what is
there".

**Every settings dict starts from ``get_default_deserialization_settings()``.**
``deserialize_from_dict()`` reads eight keys with ``[]`` rather than ``.get()``
- ``mask_helpers``, ``detailed_helpers``, ``extra_vertex_groups``,
``feet_on_ground``, ``scale``, ``subdiv_levels``, ``load_clothes`` and
``material_instances`` - so a dict assembled from literals is one forgotten key
away from a ``KeyError`` raised from inside MPFB with a character half built.
This payload takes MPFB's own default and overwrites into it. Two keys go the
other way: ``override_clothes_model`` and ``override_eyes_model`` are honoured
(behind ``in`` guards) and MPFB's own panel passes them, but they are **not** in
that default dict - so the vocabulary is wider than the defaults and these are
added rather than assumed to be there.

**``material_instances`` follows MPFB's panel rather than the service's
default**, which is the coercion rule in
specifications/mpfb-integration.md. ``get_default_deserialization_settings()``
says ``NEVER``; the property MPFB's own "from preset" panel is built from
(``ui/new_human/newhuman/properties/material_instances.json``) defaults to
``ENHANCED``. A character loaded through this tool should be the character the
user would have got from that panel, so ``ENHANCED`` is what an omitted argument
means - and ``material_instances_requested`` comes back beside
``material_instances_used`` and ``material_instances_service_default`` so the
substitution is never silent.

**The operator's UI conveniences are deliberately not reproduced**, and each was
considered rather than overlooked. ``mpfb.human_from_presets`` enters *edit
mode* on the proxy and on the basemesh to preselect a vertex group, sets an
active material index by matching a slot name against that group, and optionally
runs Rigify generation. The vertex-group preselection is a modelling-workflow
nicety with no meaning to an agent; entering edit mode across the socket is a
hazard, since every subsequent bpy.ops call polls on the context mode and a
program that fails between the two ``mode_set`` calls leaves Blender in edit
mode; and ``mpfb_generate_rigify_rig`` exists, is not undoable, and should be
called deliberately rather than as a side effect of loading. The material-index
fixup is the one that is arguably lost, and it is the one that changes nothing
about the character - only which slot a panel is looking at.

**A preset naming an asset that is not installed is silent inside MPFB.**
``_check_add_clothes()`` and ``_check_add_bodyparts()`` call
``find_asset_absolute_path()`` and, on a miss, ``_LOG.warn()`` and carry on - so
a character comes back missing its hair and nothing in the scene says why. Every
asset the preset names is therefore resolved *here*, before the call, and
anything that does not resolve is reported as ``unresolved_assets``. The
resolution is MPFB's own function against MPFB's own subdirs, so a miss here is
a miss there.

**A rig the preset names and this Blender does not have is worse than silent.**
``_check_add_rig()`` calls ``add_builtin_rig()`` / ``add_custom_rig()``, which
raise when handed no operator - and by then ``create_human()`` has already run,
so the raise leaves a naked character in the scene. That cannot be prevented
without duplicating ``rig_lookup.py``'s resolution or paying its 8.5 KB on every
call for one of several failure modes, so it is *caught* instead: the whole
deserialization runs inside a ``try``, and a failure reports what it raised
together with ``objects_created`` - every object that appeared while it ran, by
name, so the caller can clean up rather than guess. That covers the rig case and
every other partial failure with it.

**The selection cannot be restored.** Deserialization ends with MPFB having
created and activated objects, and there is no prior state to restore to - the
same exception ``mpfb_generate_rigify_rig`` has and for the same reason. So
``active_object_after`` is reported instead.
"""

import json
import os

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
HumanService = _MPFB_SERVICES["HumanService"]
AssetService = _MPFB_SERVICES["AssetService"]
MaterialService = _MPFB_SERVICES["MaterialService"]
RigService = _MPFB_SERVICES["RigService"]

# A BlenderConfigSet kept at module level rather than in SERVICES, so it is read
# through the module of a service that has already resolved - never by importing
# an MPFB submodule.
OBJECTSERVICE_MODULE = sys.modules[ObjectService.__module__]
GeneralObjectProperties = getattr(OBJECTSERVICE_MODULE, "GeneralObjectProperties", None)

# The eight keys deserialize_from_dict() reads with [] rather than .get(). Named
# here so that "the default dict really does carry all of them" is something
# this payload checks rather than assumes: MPFB's default is what it is on the
# install this is running against, not on the one this was written against.
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
# Each row is (preset key, asset subdir, MPFB object type). The first two are
# the same string in every row and the third is not quite - the object type is
# what ObjectService names a body part, and writing it out is cheaper than
# deriving it from the key and being wrong about one of them later.
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
# inside an error message is how a refusal becomes the largest response the tool
# can produce.
SUGGESTION_CAP = 50


def as_path(path):
    # MPFB's path getters are annotated as returning str and do not always do
    # so; a pathlib.Path fails strict_json and takes the response down with it.
    if not path:
        return None
    return str(path)


def resolve_asset(fragment, subdir):
    """Where MPFB will look for one asset the preset names, or None.

    The same call the deserializer makes, so a miss here is the miss it will
    have. Matching is by *basename*, so which of two identically named files
    this finds is a coin toss - which is why the resolved path is reported
    rather than only whether it resolved.
    """
    if not fragment:
        return None
    try:
        return as_path(AssetService.find_asset_absolute_path(str(fragment), subdir))
    except Exception:  # pylint: disable=broad-except
        return None


def asset_expectations(human_info, load_clothes):
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
                resolved_path=resolve_asset(fragment, subdir), skipped=False))
    proxy = human_info.get("proxy")
    if proxy and str(proxy).strip():
        expectations.append(dict(
            kind="proxy", fragment=str(proxy).strip(), asset_subdir=PROXY_SUBDIR,
            resolved_path=resolve_asset(proxy, PROXY_SUBDIR), skipped=False))
    for garment in human_info.get("clothes") or []:
        if not garment or not str(garment).strip():
            continue
        expectations.append(dict(
            kind="clothes", fragment=str(garment).strip(), asset_subdir=CLOTHES_SUBDIR,
            # Resolved even when it will be skipped, so that "you asked not to
            # load the clothes" and "the clothes are not installed" stay
            # distinguishable in one answer.
            resolved_path=resolve_asset(garment, CLOTHES_SUBDIR),
            skipped=not load_clothes))
    skin = human_info.get("skin_mhmat")
    if skin and str(skin).strip():
        expectations.append(dict(
            kind="skin", fragment=str(skin).strip(), asset_subdir=SKIN_SUBDIR,
            resolved_path=resolve_asset(skin, SKIN_SUBDIR), skipped=False))
    return expectations


def object_names():
    """Every object in the file right now, as a set of names.

    bpy.data rather than the scene: deserialization creates objects and links
    them, and an object created into another collection would otherwise look
    like nothing happened.
    """
    return set(str(blender_object.name) for blender_object in bpy.data.objects)


def object_record(blender_object, kind):
    if blender_object is None:
        return None
    record = dict(kind=kind, object_name=str(blender_object.name))
    try:
        record["asset_source"] = as_path(GeneralObjectProperties.get_value(
            "asset_source", entity_reference=blender_object))
    except Exception:  # pylint: disable=broad-except
        record["asset_source"] = None
    return record


def blocked(reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=preset_exists,
        ready=False,
        created=False,
        blocked_by=reason,
        name=requested_name,
        config_dir=confdir,
        path=file_path,
        basemesh_name=None,
        rig_object_name=None,
        active_object_after=None,
        objects_created=[],
        message=message,
    )
    answer.update(extra)
    return answer


requested_name = PARAMS["name"]
overrides_requested = dict(
    override_rig=PARAMS["override_rig"],
    override_skin_model=PARAMS["override_skin_model"],
    override_clothes_model=PARAMS["override_clothes_model"],
    override_eyes_model=PARAMS["override_eyes_model"],
    load_clothes=PARAMS["load_clothes"],
    scale=PARAMS["scale"],
    material_instances=PARAMS["material_instances"],
)

confdir = config_directory()
name_rejection = preset_name_rejection(requested_name)
file_path = None
if name_rejection is None:
    file_path = preset_path(confdir, requested_name)
preset_exists = bool(file_path is not None and os.path.isfile(file_path))

human_info = None
parse_error = None
if preset_exists:
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            human_info = json.load(handle)
    except Exception as error:  # pylint: disable=broad-except
        parse_error = str(error)
    if human_info is not None and not isinstance(human_info, dict):
        # Concatenated rather than formatted: a payload carries no substitution
        # points at all, so that nothing in it can be mistaken for one.
        parse_error = ("the file holds a " + type(human_info).__name__
                       + " rather than an object")
        human_info = None

# MPFB's defaults, asked for once and checked rather than trusted.
settings = None
service_defaults = None
settings_error = None
try:
    service_defaults = dict(HumanService.get_default_deserialization_settings())
    settings = dict(service_defaults)
except Exception as error:  # pylint: disable=broad-except
    settings_error = str(error)
missing_settings = []
if settings is not None:
    missing_settings = [key for key in REQUIRED_SETTINGS if key not in settings]

material_instances_used = None
if settings is not None:
    # The panel's default, not the service's. Reported either way.
    material_instances_used = overrides_requested["material_instances"]
    if material_instances_used is None:
        material_instances_used = PANEL_MATERIAL_INSTANCES

if name_rejection is not None:
    # Defence in depth: the tool module refuses this before the program is
    # built (see mpfbmcp/preset_names.py).
    result = blocked(
        "invalid_name",
        name_rejection + " A preset is always human.<name>.json in MPFB's user config "
        "directory, so a name that could become a path is refused rather than resolved.")
elif confdir is None or not os.path.isdir(confdir):
    result = blocked(
        "config_dir_missing",
        "MPFB's user config directory " + repr(confdir) + " does not exist, so no preset "
        "could be read. MPFB creates it when it loads, so this means the install is broken.")
elif not preset_exists:
    # A misspelled name is the likeliest way this tool is called wrongly, so the
    # refusal ends the guessing rather than only reporting it. The names come
    # from the directory rather than from MPFB's cached list: a preset saved
    # moments ago in another Blender is offered here, and the cache would not
    # have it.
    available = scan_preset_names(confdir)
    result = blocked(
        "preset_not_found",
        "No preset named '" + str(requested_name) + "' exists in '" + str(confdir)
        + "'. available_presets names the " + str(min(len(available), SUGGESTION_CAP))
        + " of " + str(len(available)) + " that do; mpfb_list_presets reports each one's age "
        "and size.",
        available_presets=available[:SUGGESTION_CAP],
        available_preset_count=len(available))
elif human_info is None:
    result = blocked(
        "preset_unreadable",
        "'" + str(file_path) + "' exists but could not be read as a character preset: "
        + str(parse_error) + ". A preset is a JSON object written by MPFB; a truncated or "
        "hand-edited file looks like this.",
        file=file_facts(file_path))
elif settings is None:
    result = blocked(
        "settings_unavailable",
        "HumanService.get_default_deserialization_settings() raised: " + str(settings_error)
        + ". Nothing can be loaded without it - deserialize_from_dict() reads eight of its "
          "keys with [] rather than .get(), so a dict assembled here instead would fail "
          "somewhere inside MPFB with a character half built.")
elif missing_settings:
    result = blocked(
        "settings_incomplete",
        "MPFB's default deserialization settings are missing " + ", ".join(missing_settings)
        + ", which deserialize_from_dict() reads with [] rather than .get(). Loading would "
          "raise from inside MPFB with a character half built, so nothing was attempted. This "
          "is a version mismatch between MPFB and this tool.",
        missing_settings=missing_settings,
        known_settings=sorted(settings.keys()))
elif material_instances_used not in MATERIAL_INSTANCES_VALUES:
    result = blocked(
        "unknown_material_instances",
        "'" + str(overrides_requested["material_instances"]) + "' is not a material_instances "
        "setting MPFB knows, so nothing was loaded. known_material_instances lists the three; "
        "_set_skin() tests the value with substring matches, so an unrecognised one silently "
        "means NEVER rather than failing.",
        known_material_instances=list(MATERIAL_INSTANCES_VALUES))
elif bpy.context.mode != "OBJECT":
    # Building a character runs operators, and bpy.ops polls on the *context*
    # mode - so an unrelated object left in edit mode fails them.
    result = blocked(
        "not_object_mode",
        "Blender is in " + str(bpy.context.mode) + " mode. Building a character runs operators "
        "that require OBJECT mode, so nothing was loaded. Leave edit mode and call again.")
else:
    load_clothes = overrides_requested["load_clothes"]
    if load_clothes is None:
        load_clothes = bool(settings["load_clothes"])

    settings["load_clothes"] = load_clothes
    settings["material_instances"] = material_instances_used
    if overrides_requested["scale"] is not None:
        settings["scale"] = float(overrides_requested["scale"])
    for key in ("override_rig", "override_skin_model",
                "override_clothes_model", "override_eyes_model"):
        if overrides_requested[key] is not None:
            settings[key] = overrides_requested[key]
        elif key not in settings:
            # The two MPFB's defaults omit. "PRESET" is the sentinel
            # deserialize_from_dict() reads as "use what the preset says", and
            # it is what MPFB's own panel passes for both.
            settings[key] = "PRESET"

    expectations = asset_expectations(human_info, load_clothes)
    unresolved_assets = [entry for entry in expectations
                         if entry["resolved_path"] is None and not entry["skipped"]]

    before = object_names()
    basemesh = None
    failure = None
    try:
        basemesh = HumanService.deserialize_from_json_file(file_path, settings)
    except Exception as error:  # pylint: disable=broad-except
        failure = type(error).__name__ + ": " + str(error)

    created = sorted(object_names() - before)
    active_after = bpy.context.view_layer.objects.active
    active_object_after = None if active_after is None else str(active_after.name)

    if basemesh is None:
        result = blocked(
            "deserialization_failed",
            "MPFB raised while building a character from '" + str(requested_name) + "': "
            + str(failure) + " A character is built in stages - mesh, targets, rig, body parts,"
            " clothes, materials - so what was made before the failure is still in the scene: "
            "objects_created names it, and there is no undo for it across this socket. The "
            "commonest cause is a rig the preset names and this Blender does not have, since "
            "MPFB's rig adders raise rather than degrade; mpfb_list_rigs says which rigs exist "
            "here, and override_rig='NONE' loads the character without one.",
            objects_created=created,
            active_object_after=active_object_after,
            preset_rig=human_info.get("rig") or None,
            unresolved_assets=unresolved_assets)
    else:
        rig_object = ObjectService.find_object_of_type_amongst_nearest_relatives(
            basemesh, "Skeleton")
        rig_identified_as = None
        if rig_object is not None:
            try:
                rig_identified_as = RigService.identify_rig(rig_object)
            except Exception:  # pylint: disable=broad-except
                rig_identified_as = None

        equipped = []
        for key, _subdir, object_type in BODYPARTS:
            found = ObjectService.find_object_of_type_amongst_nearest_relatives(
                basemesh, object_type)
            record = object_record(found, key)
            if record is not None:
                equipped.append(record)
        proxy_object = ObjectService.find_object_of_type_amongst_nearest_relatives(
            basemesh, "Proxymeshes")
        proxy_record = object_record(proxy_object, "proxy")
        if proxy_record is not None:
            equipped.append(proxy_record)
        for garment in ObjectService.find_all_objects_of_type_amongst_nearest_relatives(
                basemesh, "Clothes") or []:
            record = object_record(garment, "clothes")
            if record is not None:
                equipped.append(record)

        skin_identified_as = None
        try:
            skin_identified_as = MaterialService.identify_material(
                MaterialService.get_material(basemesh, 0))
        except Exception:  # pylint: disable=broad-except
            skin_identified_as = None

        # Beside each override the caller passed, what the preset itself held -
        # so "I overrode the rig" and "the preset had no rig" are one read apart.
        preset_values = dict(
            override_rig=human_info.get("rig") or None,
            override_skin_model=human_info.get("skin_material_type") or None,
            override_clothes_model=human_info.get("clothes_material_type") or None,
            override_eyes_model=human_info.get("eyes_material_type") or None,
            load_clothes=list(human_info.get("clothes") or []),
            scale=None,
            material_instances=None,
        )
        overrides = dict()
        for key in overrides_requested:
            overrides[key] = dict(
                requested=overrides_requested[key],
                preset_value=preset_values[key],
                used=settings.get(key),
            )

        message_parts = [
            "Created '" + str(basemesh.name) + "' from preset '" + str(requested_name) + "'."]
        if rig_object is not None:
            message_parts.append(
                " It carries the rig '" + str(rig_object.name) + "' (" + str(rig_identified_as)
                + ").")
            if str(rig_identified_as or "").startswith("rigify."):
                message_parts.append(
                    " That is a Rigify *meta* rig; finish it with mpfb_generate_rigify_rig "
                    "once nothing else needs adding.")
        if equipped:
            message_parts.append(" " + str(len(equipped)) + " asset(s) were equipped with it.")
        if unresolved_assets:
            message_parts.append(
                " " + str(len(unresolved_assets)) + " asset(s) the preset names are not "
                "installed here and were silently skipped by MPFB: unresolved_assets names "
                "them. The character is otherwise complete.")
        if not load_clothes and preset_values["load_clothes"]:
            message_parts.append(
                " load_clothes was false, so the " + str(len(preset_values["load_clothes"]))
                + " garment(s) in the preset were not loaded.")
        message_parts.append(
            " The selection was not restored - deserialization activates what it creates, and "
            "there was no prior state to return to; active_object_after says what is active "
            "now.")

        result = dict(
            found=True,
            ready=True,
            created=True,
            blocked_by=None,
            name=requested_name,
            config_dir=confdir,
            path=file_path,
            basemesh_name=str(basemesh.name),
            rig_object_name=None if rig_object is None else str(rig_object.name),
            rig_identified_as=rig_identified_as,
            equipped_assets=equipped,
            unresolved_assets=unresolved_assets,
            skin_material_identified_as=skin_identified_as,
            overrides=overrides,
            material_instances_requested=overrides_requested["material_instances"],
            material_instances_used=material_instances_used,
            material_instances_service_default=service_defaults.get("material_instances"),
            known_material_instances=list(MATERIAL_INSTANCES_VALUES),
            settings_used=settings,
            objects_created=created,
            active_object_after=active_object_after,
            message="".join(message_parts),
        )


# The verb is "created". See codegen/shared/performed.py.
result = with_performed(result, result.get("created", False))
