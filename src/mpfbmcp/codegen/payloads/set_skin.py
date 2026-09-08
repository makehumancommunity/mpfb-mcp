"""
Payload for ``mpfb_set_skin``: apply a skin, and say what it destroyed on the way.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag four names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, ``path``,
  ``fragment``, ``skin_type`` and ``material_instances``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap, and used here to reach
  ``GeneralObjectProperties`` and ``HumanObjectProperties``, which MPFB keeps at
  module level rather than on a service.
- ``with_performed()`` - from the shared fragment ``performed.py``, named by
  every mutating payload. It stamps the uniform ``performed`` flag onto the
  finished answer, in the last line of this file.

...and a further set because they come from the shared fragment
``asset_sections.py``, concatenated ahead of this file: ``AssetService``,
``as_path()``, ``read_sections()`` and ``subdir_for_object_type()``. Only one
call is needed from it - ``subdir_for_object_type(sections, "Material")``, which
is MPFB's own answer to "which subdir do skins live in" - but it is the call
that keeps this tool and ``mpfb_list_assets`` agreeing about where a fragment is
looked up.

**The work itself is MPFB's.** ``HumanService.set_character_skin()`` deletes the
old materials, records the source fragment, builds one of five node trees and
optionally creates the per-region material slots. None of that is reimplemented.
What is here is everything around it, and five things in particular could not
live in the tool module.

**The vocabulary check has to happen before the call, not inside it.** That
function tests its five types with five separate ``if`` statements, *after*
opening with ``delete_all_materials(..., also_destroy_groups=True)`` on both
objects. An unrecognised ``skin_type`` therefore destroys the character's
materials, builds nothing, and then raises from
``create_and_assign_material_slots()`` about a mesh with no materials. So the
type is checked here first and refused as an answer.

**The UI's ``material_instances`` coercion is the UI's alone.**
``loadlibraryskin.py`` forces the flag to ``False`` for ``LAYERED``,
``GAMEENGINE`` *and* ``MAKESKIN``; the service's own guard names only the first
two. Following the panel is deliberate - it is what the user sees and what a
character loaded from a ``.mhm`` was made with - and both values are reported,
because a silent coercion looks like a bug.

**The body proxy is resolved here and passed explicitly.**
``set_character_skin()`` would resolve it itself when handed ``None``, but this
payload needs the same object anyway - for ``materials_destroyed``, for the
active-slot fixup and for the response, which is the only place a caller learns
that a second object was modified at all.

**Everything reported as destroyed is read before the call.** The materials are
gone the moment that function's first statement runs, and with
``also_destroy_groups=True`` their node groups go too.

**The active-material-slot fixup is UI behaviour with no service behind it.**
After loading, MPFB's operator selects the slot whose material name ends in
``body``, on the basemesh and on the proxy, so the user's material properties
panel is not looking at a fingernail. Reproduced statement for statement, last
match winning, exactly as that loop does.

Two facts are reported that nothing in Blender shows. The enhanced types copy
``enhanced_settings.default.json`` into the user config directory when it is
absent - the only file this package ever writes outside the ``.blend`` - and the
copy is gated on ``material_instances`` rather than on the skin type, so the
default call writes nothing. And the enhanced types derive a scale name from the
character's ``scale_factor``, which changes the subsurface radii. Note where the
bands actually fall, since the property's declared default is misleading: it
declares ``1.0``, which is above the first threshold of ``> 0.9`` and would give
``DECIMETER`` - but ``create_human()`` writes ``0.1`` onto every character it
makes, so an ordinary character is below it and reports ``METER``. Observed
live, not read off the property definition.
"""

import os

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
HumanService = _MPFB_SERVICES["HumanService"]
MaterialService = _MPFB_SERVICES["MaterialService"]
LocationService = _MPFB_SERVICES["LocationService"]

# Both property sets are BlenderConfigSet entities kept at module level rather
# than in SERVICES, so both are read through the module of a service that has
# already resolved - never by importing an MPFB submodule. They live on
# different modules: material_source is a *human* property and scale_factor is a
# general one.
OBJECTSERVICE_MODULE = sys.modules[ObjectService.__module__]
HUMANSERVICE_MODULE = sys.modules[HumanService.__module__]

GeneralObjectProperties = getattr(OBJECTSERVICE_MODULE, "GeneralObjectProperties", None)
HumanObjectProperties = getattr(HUMANSERVICE_MODULE, "HumanObjectProperties", None)

# MPFB's five skin models, from the same enum its settings panel is built on.
SKIN_TYPES = ("MAKESKIN", "GAMEENGINE", "ENHANCED", "ENHANCED_SSS", "LAYERED")

# The three the UI refuses to instance materials for. The service guard names
# only LAYERED and GAMEENGINE; MAKESKIN is the panel's own decision, and since
# MAKESKIN is the default type it is the reason the default call instances
# nothing.
NO_MATERIAL_INSTANCES = ("LAYERED", "GAMEENGINE", "MAKESKIN")

# The two that build EnhancedSkinMaterial, and so the two that read a scale.
ENHANCED_TYPES = ("ENHANCED", "ENHANCED_SSS")

# The one type that can be applied with no MHMAT at all.
NEEDS_NO_FILE = "LAYERED"

ENHANCED_SETTINGS_FILE = "enhanced_settings.default.json"


def property_value(config_set, property_name, blender_object):
    """One custom property, or None when it was never set.

    An unset string property reads back as "" rather than None, and "" means
    "nothing was recorded" - it must not be reported as a fragment.
    """
    if config_set is None or blender_object is None:
        return None
    try:
        value = config_set.get_value(property_name, entity_reference=blender_object)
    except Exception:  # pylint: disable=broad-except
        return None
    if not value:
        return None
    return str(value)


def material_names(blender_object):
    """Every material name on an object, read off its slots.

    Read *before* the call, because ``delete_all_materials()`` is the first
    thing ``set_character_skin()`` does, and it takes the node groups with it.
    """
    names = []
    if blender_object is None:
        return names
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        if material is not None:
            names.append(str(material.name))
    return names


def material_slot_records(blender_object):
    """The slots as they are now, which is how instancing differs observably."""
    if blender_object is None:
        return None
    slots = []
    index = 0
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        slots.append(dict(
            slot_index=int(getattr(slot, "slot_index", index)),
            material_name=None if material is None else str(material.name),
        ))
        index = index + 1
    return dict(
        object_name=blender_object.name,
        slots=slots,
        active_material_index=int(getattr(blender_object, "active_material_index", 0) or 0),
    )


def activate_body_slot(blender_object):
    """MPFB's operator does this and the service does not.

    Without it the user's material properties panel is left looking at whichever
    slot happens to be index 0 - a fingernail material, on an instanced skin.
    The loop takes the *last* match rather than breaking on the first, exactly
    as ``loadlibraryskin.py`` does.
    """
    if blender_object is None:
        return None
    chosen = None
    index = 0
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        if material is not None and str(material.name).lower().endswith("body"):
            blender_object.active_material_index = int(getattr(slot, "slot_index", index))
            chosen = str(material.name)
        index = index + 1
    return chosen


def scale_assumption_for(basemesh):
    """MPFB's own scale detection, reproduced only to be able to report it.

    ``set_character_skin()`` runs exactly these comparisons inside its enhanced
    branch and feeds the answer to the subsurface radii. Note where they fall on
    a real character: ``create_human()`` writes a ``scale_factor`` of 0.1, which
    is below the first threshold, so an ordinary character is treated as
    metre-scaled. The property's *declared* default of 1.0 would give
    ``DECIMETER`` and no character MPFB builds has it. Reported because a
    wrongly scaled character gets a subtly wrong skin and nothing else in the
    response would explain it.
    """
    if GeneralObjectProperties is None or basemesh is None:
        return None
    try:
        scale_factor = GeneralObjectProperties.get_value(
            "scale_factor", entity_reference=basemesh)
    except Exception:  # pylint: disable=broad-except
        return None
    if scale_factor is None:
        return None
    scale_name = "METER"
    if scale_factor > 0.9:
        scale_name = "DECIMETER"
    if scale_factor > 9:
        scale_name = "CENTIMETER"
    return scale_name


def enhanced_settings_path():
    """Where MPFB would copy its default enhanced-skin settings to.

    Read before and after the call so ``settings_file_created`` is an
    observation rather than a guess about which branch ran.
    """
    try:
        return as_path(LocationService.get_user_config(ENHANCED_SETTINGS_FILE))
    except Exception:  # pylint: disable=broad-except
        return None


def blocked(subject, basemesh, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=basemesh is not None,
        ready=False,
        applied=False,
        blocked_by=reason,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        bodyproxy_name=None,
        resolved_by=resolved_by,
        resolved_path=None,
        skin_type_used=None,
        material_instances_requested=requested_material_instances,
        material_instances_used=None,
        materials_destroyed=[],
        # Always present, on every refusal as well as on success: a caller that
        # got the vocabulary wrong should be able to correct itself from the
        # same response, and one that got something *else* wrong should not have
        # to guess whether the omission means anything.
        known_skin_types=list(SKIN_TYPES),
        message=message,
    )
    answer.update(extra)
    return answer


requested_name = PARAMS["name"]
requested_path = PARAMS["path"]
requested_fragment = PARAMS["fragment"]
requested_skin_type = PARAMS["skin_type"]
requested_material_instances = PARAMS["material_instances"]

skin_type = str(requested_skin_type).strip().upper()
file_requested = requested_path is not None or requested_fragment is not None
resolved_by = None
if requested_path is not None:
    resolved_by = "path"
elif requested_fragment is not None:
    resolved_by = "fragment"

subject_resolved_by = "active" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        message = ("No object name was given and no object is active in this Blender session, so "
                   "no skin was applied. Select a MakeHuman object, or call mpfb_list_objects "
                   "and pass one of its names.")
else:
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        message = ("No object named '" + str(requested_name) + "' exists in this .blend file, so "
                   "no skin was applied. Call mpfb_list_objects to see what the current scene "
                   "holds.")

basemesh = None
if subject is not None:
    # The same call MPFB's own skin panel makes: the caller may name a garment
    # or the character's rig, and the object actually changed is reported back
    # rather than the argument echoed.
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if basemesh is None:
        message = ("'" + subject.name + "' has no MakeHuman basemesh among its nearest relatives, "
                   "so there is nothing to give a skin to. A skin is a material on the body; "
                   "call mpfb_get_object_info to see what this object is related to.")

# The argument's own resolution, done before anything is touched. "Material" is
# the object_type MPFB's section table gives the skins section, and asking that
# table is what keeps this tool looking in the same place mpfb_list_assets
# reported from.
sections, sections_from_mpfb = read_sections()
asset_subdir = subdir_for_object_type(sections, "Material")

resolved_path = None
if requested_path is not None:
    resolved_path = as_path(requested_path)
elif requested_fragment is not None and asset_subdir is not None:
    # find_asset_absolute_path() matches on *basename*, prefers a candidate
    # whose parent directory also matches, and otherwise returns the first hit,
    # so whatever it chooses is reported rather than assumed.
    try:
        resolved_path = as_path(
            AssetService.find_asset_absolute_path(requested_fragment, asset_subdir))
    except Exception:  # pylint: disable=broad-except
        resolved_path = None

if basemesh is None:
    result = blocked(subject, None, "subject_not_found", message)
elif skin_type not in SKIN_TYPES:
    # Checked before anything is destroyed, which is the whole point: the
    # function this wraps deletes every material on the character and only then
    # looks at this value.
    result = blocked(
        subject, basemesh, "unknown_skin_type",
        ("'" + str(requested_skin_type) + "' is not a skin type MPFB knows, so nothing was "
         "changed. known_skin_types lists the five; they are five different node trees built "
         "from the same MHMAT. Note that MPFB's own function would have deleted this "
         "character's materials before discovering this, so the check happens here instead."))
elif not file_requested and skin_type != NEEDS_NO_FILE:
    result = blocked(
        subject, basemesh, "no_material_given",
        ("skin_type '" + skin_type + "' builds its node tree from an MHMAT file, and neither "
         "path nor fragment was given, so nothing was changed. Call mpfb_list_assets for the "
         "'skins' subdir and pass an entry's 'path' or 'fragment'. Only skin_type '"
         + NEEDS_NO_FILE + "' can build a material with no file at all."))
elif file_requested and (resolved_path is None or not os.path.isfile(resolved_path)):
    if requested_path is not None:
        not_found_message = (
            "No file exists at '" + str(requested_path) + "', so nothing was changed. Pass the "
            "'path' mpfb_list_assets reports for an installed skin, or its 'fragment' to have "
            "this Blender's asset roots searched.")
    else:
        not_found_message = (
            "The fragment '" + str(requested_fragment) + "' resolved to no file under this "
            "Blender's '" + str(asset_subdir) + "' asset roots, so nothing was changed. The "
            "skin may not be installed here, or the fragment may name an asset of another kind "
            "- fragments are resolved per subdir, and a skin's is always 'skins'.")
    result = blocked(subject, basemesh, "skin_not_found", not_found_message,
                     asset_subdir=asset_subdir,
                     resolved_path=resolved_path,
                     section_table_from_mpfb=sections_from_mpfb)
elif basemesh.mode != "OBJECT" or bpy.context.mode != "OBJECT":
    # Two checks rather than one, the same lesson mpfb_add_rig and
    # mpfb_add_asset learned: creating the per-region material slots runs
    # bpy.ops.object.material_slot_assign() in edit mode, and bpy.ops polls on
    # the *context* mode, so an unrelated object left in edit mode fails the
    # operator even though the basemesh itself looks fine.
    result = blocked(
        subject, basemesh, "not_object_mode",
        ("Blender is in " + str(bpy.context.mode) + " mode and the basemesh '" + basemesh.name
         + "' is in " + str(basemesh.mode) + " mode. Building a skin's material slots runs "
           "operators that require OBJECT mode, so nothing was changed. Leave edit mode and "
           "call again."))
else:
    # Resolved here rather than left to set_character_skin(), which would do it
    # itself when passed None: this payload needs the same object for the
    # destroyed-material list and the slot fixup, and the response is the only
    # place a caller learns a second object was modified.
    body_proxy = ObjectService.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Proxymeshes")

    # MPFB's UI coercion, reproduced rather than the signature's default passed
    # through. See this module's docstring.
    material_instances_used = bool(
        requested_material_instances and skin_type not in NO_MATERIAL_INSTANCES)

    # Everything below is observed *before* the call, which is what makes the
    # claims afterwards precise rather than reconstructed.
    materials_destroyed = [dict(object_name=basemesh.name, materials=material_names(basemesh))]
    if body_proxy is not None:
        materials_destroyed.append(
            dict(object_name=body_proxy.name, materials=material_names(body_proxy)))

    material_source_before = property_value(
        HumanObjectProperties, "material_source", basemesh)

    settings_path = enhanced_settings_path()
    settings_file_existed = bool(settings_path is not None and os.path.exists(settings_path))

    scale_assumption = None
    if skin_type in ENHANCED_TYPES:
        scale_assumption = scale_assumption_for(basemesh)

    previous_active = bpy.context.view_layer.objects.active
    basemesh_was_selected = bool(basemesh.select_get())

    failure_message = None
    try:
        # MPFB's own operator runs with the character active, and the material
        # slot assignment goes through bpy.ops, which reads the context.
        ObjectService.activate_blender_object(basemesh)
        HumanService.set_character_skin(
            resolved_path,
            basemesh,
            bodyproxy=body_proxy,
            skin_type=skin_type,
            material_instances=material_instances_used)
    except Exception as error:  # pylint: disable=broad-except
        # Broad on purpose. By the time anything in there can raise, the old
        # materials are already deleted - so a traceback in an error envelope
        # would leave the caller with a character stripped of materials and no
        # record of what was on it. This is reported as an answer instead, with
        # materials_destroyed intact.
        failure_message = (
            "MPFB raised while building a " + skin_type + " skin: " + str(error))
    finally:
        if not basemesh_was_selected:
            basemesh.select_set(False)
        # Put back what was borrowed: the user is looking at this scene.
        bpy.context.view_layer.objects.active = previous_active

    if failure_message is not None:
        result = blocked(
            subject, basemesh, "skin_failed",
            failure_message + (
                " The character's previous materials were already deleted when this happened "
                "and cannot be restored across the socket; materials_destroyed names them."),
            bodyproxy_name=None if body_proxy is None else body_proxy.name,
            resolved_path=resolved_path,
            skin_type_used=skin_type,
            material_instances_used=material_instances_used,
            materials_destroyed=materials_destroyed,
            material_slots=[record for record in
                            (material_slot_records(basemesh), material_slot_records(body_proxy))
                            if record is not None])
    else:
        # The UI's fixup, after the load and before anything is read back.
        active_body_slot = dict(
            basemesh=activate_body_slot(basemesh),
            bodyproxy=activate_body_slot(body_proxy),
        )

        material_source = property_value(HumanObjectProperties, "material_source", basemesh)
        settings_file_created = bool(
            settings_path is not None
            and not settings_file_existed
            and os.path.exists(settings_path))

        # Identified from the node tree that is now there rather than from the
        # argument: this is the one field that says the requested tree was
        # actually built. It is a heuristic of MPFB's own, not an authority.
        material_identified_as = None
        try:
            material_identified_as = MaterialService.identify_material(
                MaterialService.get_material(basemesh, 0))
        except Exception:  # pylint: disable=broad-except
            material_identified_as = None

        message_parts = [
            "Applied a " + skin_type + " skin to '" + basemesh.name + "'"]
        if resolved_path is not None:
            message_parts.append(" from '" + os.path.basename(resolved_path) + "'")
        message_parts.append(".")
        if body_proxy is not None:
            message_parts.append(
                " The body proxy '" + body_proxy.name + "' was given it too.")
        if material_instances_used != requested_material_instances:
            message_parts.append(
                " material_instances was requested as "
                + ("true" if requested_material_instances else "false")
                + " but used as " + ("true" if material_instances_used else "false")
                + ": MPFB's skin library forces it off for " + ", ".join(NO_MATERIAL_INSTANCES)
                + ", and this tool follows the panel rather than the function signature.")
        destroyed_count = sum(len(entry["materials"]) for entry in materials_destroyed)
        if destroyed_count:
            message_parts.append(
                " " + str(destroyed_count) + " existing material(s) were deleted, node groups "
                "included; materials_destroyed names them.")
        if resolved_path is None:
            message_parts.append(
                " No MHMAT was given, so MPFB recorded no material_source and the previous "
                "value is left in place.")
        if settings_file_created:
            message_parts.append(
                " " + ENHANCED_SETTINGS_FILE + " was created in your MPFB user config "
                "directory; it did not exist before this call.")

        result = dict(
            found=True,
            ready=True,
            applied=True,
            blocked_by=None,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            bodyproxy_name=None if body_proxy is None else body_proxy.name,
            resolved_by=resolved_by,
            resolved_path=resolved_path,
            asset_subdir=asset_subdir,
            material_source=material_source,
            material_source_before=material_source_before,
            skin_type_used=skin_type,
            known_skin_types=list(SKIN_TYPES),
            material_instances_requested=requested_material_instances,
            material_instances_used=material_instances_used,
            materials_destroyed=materials_destroyed,
            material_slots=[record for record in
                            (material_slot_records(basemesh), material_slot_records(body_proxy))
                            if record is not None],
            material_identified_as=material_identified_as,
            active_body_slot=active_body_slot,
            settings_file_created=settings_file_created,
            settings_file_path=settings_path,
            scale_assumption=scale_assumption,
            message="".join(message_parts),
        )


# The verb is "applied". See codegen/shared/performed.py.
result = with_performed(result, result.get("applied", False))
