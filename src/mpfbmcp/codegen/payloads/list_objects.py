"""
Payload for ``mpfb_list_objects``: names the MakeHuman objects in this scene.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``object_type``, which
  is None when no filter was given.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap.

Only ``bpy.context.scene.objects`` is searched, so the answer matches what the
user is looking at. An object that exists in the .blend without being linked
into the scene is therefore absent here; ``mpfb_get_object_info`` resolves such
an object by name and says so explicitly, rather than pretending it is gone.

Per-object output deliberately stops at the name and the two types. Reporting
what an object was made from can cost a walk of the asset roots per object, and
paying that for every object in the scene would make the cheap orienting tool
the expensive one.
"""

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]

# _ALL_TYPES is a module-level constant in objectservice.py, not a member of
# ObjectService and not in SERVICES. The module is necessarily already imported,
# since ObjectService resolved. It is underscore-private and MPFB may rename it
# without notice, so a stale local vocabulary is the fallback: reporting last
# year's type list is a better answer than failing the call.
ALL_TYPES = getattr(
    sys.modules[ObjectService.__module__],
    "_ALL_TYPES",
    ("Skeleton", "Subrig", "Basemesh", "Proxymeshes", "Clothes",
     "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair"),
)

requested_type = PARAMS["object_type"]


def type_is_recognized(requested):
    # Mirrors ObjectService.object_is(), which lowercases both sides and asks
    # whether the requested name occurs *within* the stored one. Answering this
    # by equality instead would report "rig" as an unknown type while the filter
    # below happily matches Subrig - and the whole point of the flag is that a
    # caller can trust an empty list.
    if requested is None:
        return True
    stripped = str(requested).lower().strip()
    if not stripped:
        return False
    for known_type in ALL_TYPES:
        if stripped in known_type.lower():
            return True
    return False


def matches(blender_object):
    if requested_type is None:
        return bool(ObjectService.object_is_any_makehuman_object(blender_object))
    return bool(ObjectService.object_is(blender_object, requested_type))


def entry(blender_object):
    # get_object_type() answers "" rather than None for an object carrying no
    # MPFB type. Only typed objects reach here, but coercing in one place is
    # what keeps this key's contract - a type name or null, never "" - true.
    object_type = ObjectService.get_object_type(blender_object)
    return {
        "name": blender_object.name,
        "object_type": object_type or None,
        "blender_type": blender_object.type,
    }


objects = [entry(scene_object) for scene_object in bpy.context.scene.objects if matches(scene_object)]

result = {
    "objects": objects,
    "count": len(objects),
    "requested_type": requested_type,
    "type_recognized": type_is_recognized(requested_type),
    "known_types": list(ALL_TYPES),
}
