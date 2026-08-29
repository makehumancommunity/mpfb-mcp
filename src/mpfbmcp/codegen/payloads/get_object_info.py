"""
Payload for ``mpfb_get_object_info``: identifies one object and its relatives.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, which is None
  when the caller wants whatever object is currently active.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap.

Failing to resolve a subject is a successful answer here, not an error: an agent
guessing at a name should get a usable "no" it can recover from. Two situations
produce it - no object by that name anywhere in the .blend, and no active object
at all - and ``message`` says which.

Everything below only reads: custom properties, the object hierarchy, bone names
and material node trees, plus file lookups on disk. ObjectService also carries
destructive and selection-mutating methods; none of them is touched, and in
particular nothing is selected or activated in order to be inspected, since that
would change state the user can see.
"""

import os

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
AssetService = _MPFB_SERVICES["AssetService"]
ClothesService = _MPFB_SERVICES["ClothesService"]
MaterialService = _MPFB_SERVICES["MaterialService"]
RigService = _MPFB_SERVICES["RigService"]
LocationService = _MPFB_SERVICES["LocationService"]
HumanService = _MPFB_SERVICES["HumanService"]

# The type vocabulary and the two property sets are all module-level names
# rather than services, so they are reached through the module of a service that
# already imported them - never by importing an MPFB submodule, some of which
# create directories on import. GeneralObjectProperties is imported by
# objectservice.py; HumanObjectProperties is not, and lives on humanservice.py's
# module instead. All four are private-ish and read with a fallback.
OBJECTSERVICE_MODULE = sys.modules[ObjectService.__module__]
HUMANSERVICE_MODULE = sys.modules[HumanService.__module__]

SKELETON_TYPES = getattr(OBJECTSERVICE_MODULE, "_SKELETON_TYPES", ("Skeleton", "Subrig"))
MESH_ASSET_TYPES = getattr(
    OBJECTSERVICE_MODULE,
    "_MESH_ASSET_TYPES",
    ("Proxymeshes", "Clothes", "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair"),
)
GeneralObjectProperties = getattr(OBJECTSERVICE_MODULE, "GeneralObjectProperties", None)
HumanObjectProperties = getattr(HUMANSERVICE_MODULE, "HumanObjectProperties", None)


def property_value(config_set, property_name, blender_object):
    # These are BlenderConfigSet entities, not services, so they may be absent
    # if MPFB reorganizes - hence the guard rather than an attribute error deep
    # in the response build. An unset string property reads back as "", which
    # means "nothing was recorded" and must not be reported as a fragment.
    if config_set is None or blender_object is None:
        return None
    try:
        value = config_set.get_value(property_name, entity_reference=blender_object)
    except Exception:  # pylint: disable=broad-except
        return None
    if not value:
        return None
    return str(value)


def as_path(path):
    # Coerce at the point a path enters the response. MPFB's path getters are
    # annotated as returning str, but LocationService.get_mpfb_root() has been
    # caught handing back a pathlib.Path, which fails strict_json and takes the
    # entire response down with it (commit 631989c).
    if not path:
        return None
    return str(path)


def rig_definition_path(rig_type):
    # Mirrors how HumanService.add_builtin_rig() assembles the file it loads
    # from: <mpfb data>/rigs/<standard or rigify>/rig.<name>.json. Nothing
    # records which definition a rig was built from, so this is derived from the
    # identified type, and reported only when the file is actually there.
    if not rig_type or rig_type == "unknown":
        return None
    if rig_type.startswith("custom."):
        # Custom rig definitions live under a user asset root, not in MPFB's own
        # data, so the path is taken from the entry rather than derived.
        wanted_name = rig_type[len("custom."):]
        for custom_rig in AssetService.get_custom_rigs():
            if custom_rig.get("name") == wanted_name:
                return as_path(custom_rig.get("path"))
        return None
    if rig_type.startswith("rigify_generated."):
        # Rigify built this from a metarig; it was never loaded from a
        # definition, so there is no file to point at.
        return None
    is_rigify = rig_type.startswith("rigify.")
    rig_name = rig_type[len("rigify."):] if is_rigify else rig_type
    rigs_directory = as_path(LocationService.get_mpfb_data("rigs"))
    if rigs_directory is None:
        return None
    candidate = os.path.join(
        rigs_directory, "rigify" if is_rigify else "standard", "rig." + rig_name + ".json")
    if not os.path.isfile(candidate):
        # Covers rigify.unknown, whose name is a placeholder rather than a rig,
        # as well as a definition that is simply not installed.
        return None
    return candidate


def material_type_of(blender_object):
    # identify_material() takes a material rather than an object and answers
    # "empty" for None, so the pair composes without a guard - but only meshes
    # have material slots at all. This is the one asset_info value derived from
    # the material actually present rather than from a record of what was
    # loaded, and it is a documented heuristic, not an authority.
    if blender_object.type != "MESH":
        return None
    return MaterialService.identify_material(MaterialService.get_material(blender_object, 0))


def material_asset_info(blender_object, object_type):
    # One response key filled from two different properties, each resolving
    # against a different asset subdir. material_source is the skin, written by
    # HumanService.set_character_skin() onto the basemesh and, when there is
    # one, the body proxy; it lives under "skins". alternative_material is a
    # material other than the asset's own, and lives under the asset's own
    # subdir. Resolving either against the other's directory does not raise - it
    # silently reports null for an asset that is installed, which is exactly the
    # failure the fragment/path pairing exists to make visible.
    fragment = property_value(HumanObjectProperties, "material_source", blender_object)
    asset_subdir = "skins"
    if fragment is None:
        fragment = property_value(GeneralObjectProperties, "alternative_material", blender_object)
        asset_subdir = str(object_type).lower()
    if fragment is None:
        # No fragment means no lookup: the asset-root walk happens only when
        # there is something to resolve.
        return {"material_source": None, "mhmat_path": None}
    return {
        "material_source": fragment,
        "mhmat_path": as_path(AssetService.find_asset_absolute_path(fragment, asset_subdir)),
    }


def asset_info_for(blender_object, object_type):
    # Three shapes, dispatched on the type family rather than on the type
    # string. The keys present say which question was asked; their values say
    # whether it could be answered. A union of all keys with the inapplicable
    # ones nulled would report mhclo_path: null on a skeleton, which reads as
    # "we looked for its mhclo and failed" - a different and much more alarming
    # claim than "a skeleton does not have one".
    if not object_type:
        return None

    if object_type in SKELETON_TYPES:
        rig_type = None
        if blender_object.type == "ARMATURE":
            # identify_rig() dereferences .data.bones, which a mesh does not
            # have. It matches bone names rather than reading back a property,
            # so a hand-edited armature can be identified as something it was
            # not built from.
            rig_type = RigService.identify_rig(blender_object)
        return {
            "rig_type": rig_type,
            "rig_definition_path": rig_definition_path(rig_type),
        }

    if object_type in MESH_ASSET_TYPES:
        asset_source = property_value(GeneralObjectProperties, "asset_source", blender_object)
        mhclo_path = None
        if asset_source is not None:
            # find_clothes_absolute_path() reads asset_source and the object
            # type and resolves both, for every mesh asset type and not only
            # Clothes. The file it points at may carry a .proxy extension rather
            # than .mhclo, since MPFB imports them all through the same format.
            mhclo_path = as_path(ClothesService.find_clothes_absolute_path(blender_object))
        info = {
            "asset_source": asset_source,
            "mhclo_path": mhclo_path,
            "material_type": material_type_of(blender_object),
        }
        info.update(material_asset_info(blender_object, object_type))
        return info

    if object_type == "Basemesh":
        info = {"material_type": material_type_of(blender_object)}
        info.update(material_asset_info(blender_object, object_type))
        return info

    # A type MPFB knows about that none of the families above covers - it added
    # one. Report the object normally and say, by an empty dict, that no asset
    # question applies to this type, rather than claiming any specific answer.
    return dict()


def in_current_scene(blender_object):
    return blender_object.name in bpy.context.scene.objects


def related_entry(blender_object):
    object_type = ObjectService.get_object_type(blender_object) or None
    return {
        "name": blender_object.name,
        "object_type": object_type,
        "blender_type": blender_object.type,
        # Relatives are found through get_list_of_children(), which walks
        # bpy.data.objects rather than the scene, so a relative can sit outside
        # the scene mpfb_list_objects searched. Flagging each one is what keeps
        # that from reading as a contradiction between the two tools.
        "in_current_scene": in_current_scene(blender_object),
        "asset_info": asset_info_for(blender_object, object_type),
    }


def rigify_role(blender_object):
    # Neither helper returns a bool: the first hands back Rigify's rig_id
    # string, the second a real bool. Only their truthiness is meaningful.
    if ObjectService.object_is_generated_rigify_rig(blender_object):
        return "generated_rig"
    if ObjectService.object_is_rigify_metarig(blender_object):
        return "metarig"
    return None


def other_related_entry(blender_object):
    # No asset_info here: these carry no MPFB type, so that value could only
    # ever be null, and a key that is always null is noise. rigify_role is the
    # analogous field for what little can be said about them.
    return {
        "name": blender_object.name,
        "object_type": None,
        "blender_type": blender_object.type,
        "in_current_scene": in_current_scene(blender_object),
        "rigify_role": rigify_role(blender_object),
    }


def neighbourhood(blender_object):
    # find_related_objects() only yields objects carrying an MPFB type, so the
    # untyped half of the neighbourhood needs its own walk. Same shape as
    # ObjectService's: the object, its children recursively, then the parent
    # chain and each parent's children.
    collected = []

    def collect(candidate):
        if candidate is None or candidate in collected:
            return
        collected.append(candidate)
        for child in ObjectService.get_list_of_children(candidate):
            collect(child)

    collect(blender_object)
    parent = blender_object.parent
    while parent is not None:
        collect(parent)
        parent = parent.parent
    return collected


requested_name = PARAMS["name"]
resolved_from = "active_object" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator, and the
    # view-layer form does not depend on which UI area happens to be current.
    # It is None whenever nothing is active, which is an answer, not a crash.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        message = ("No object name was given and no object is active in this Blender session, so "
                   "there is nothing to report on. Select an object, or call mpfb_list_objects "
                   "and pass one of its names.")
else:
    # bpy.data.objects rather than the scene: object names are unique across the
    # whole .blend, and "exists, but not in this scene" is a different and far
    # more useful answer than a bare "not found".
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        message = ("No object named '" + str(requested_name) + "' exists in this .blend file. "
                   "Call mpfb_list_objects to see what the current scene holds.")

if subject is None:
    result = {
        "found": False,
        "resolved_from": resolved_from,
        "name": None,
        "message": message,
    }
else:
    subject_type = ObjectService.get_object_type(subject) or None
    subject_in_scene = in_current_scene(subject)

    related_objects = []
    seen_names = []
    for relative in ObjectService.find_related_objects(subject):
        # find_all_objects_of_type_amongst_nearest_relatives() yields the object
        # it was asked about first, and find_related_objects() is a thin wrapper
        # over it, so the subject turns up in its own relatives. The traversal
        # excludes the branch it arrived from, but dedupe anyway: a duplicate
        # would read as two distinct objects.
        if relative is subject or relative.name in seen_names:
            continue
        seen_names.append(relative.name)
        related_objects.append(related_entry(relative))

    other_related_objects = [
        other_related_entry(neighbour)
        for neighbour in neighbourhood(subject)
        if neighbour is not subject
        and not ObjectService.object_is_any_makehuman_object(neighbour)
    ]

    # Built by concatenation rather than the repo's usual .format(): a payload
    # file must contain no empty brace pair anywhere, since that is what a
    # substitution point looks like, and nothing is ever substituted into a
    # payload. tests/test_codegen.py enforces it.
    message_parts = []
    if subject_type:
        message_parts.append(
            "'" + subject.name + "' is a MakeHuman " + subject_type + " object")
    else:
        message_parts.append(
            "'" + subject.name + "' carries no MPFB object type: it is a plain Blender object")
    if not subject_in_scene:
        # The one found case where the next step is not obvious, and the whole
        # reason in_current_scene is reported rather than the object simply
        # failing to resolve.
        message_parts.append(
            ", and it exists in this .blend file without being linked into the current scene, "
            "so mpfb_list_objects does not list it")
    message_parts.append(
        ". " + str(len(related_objects)) + " related MakeHuman objects were found.")
    message = "".join(message_parts)

    result = {
        "found": True,
        "resolved_from": resolved_from,
        "name": subject.name,
        "in_current_scene": subject_in_scene,
        "object_type": subject_type,
        "blender_type": subject.type,
        "is_makehuman_object": bool(subject_type),
        "asset_info": asset_info_for(subject, subject_type),
        "related_objects": related_objects,
        "other_related_objects": other_related_objects,
        "message": message,
    }
