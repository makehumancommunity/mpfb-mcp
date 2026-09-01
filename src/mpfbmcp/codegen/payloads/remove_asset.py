"""
Payload for ``mpfb_remove_asset``: unload one MHCLO asset, and say what is left.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap, and used here to reach the
  object-type vocabulary and ``GeneralObjectProperties`` off ObjectService's
  module.

**Everything reported is read before anything is deleted.** The object's name,
type and ``asset_source`` are gone the moment ``bpy.data.objects.remove()``
runs, and ``asset_source`` is what every modifier name is derived from - so a
response assembled afterwards could describe almost nothing.

Three things about ``HumanService.unload_mhclo_asset()`` shape this payload.

**It does not check what it was given.** Handed a basemesh or a skeleton it
deletes it, cheerfully, along with whichever mask modifier happens to match. So
the type check is here, against ObjectService's own ``_MESH_ASSET_TYPES``, and a
``Basemesh`` or ``Skeleton`` is refused outright rather than passed through.

**It derives the delete group's name from ``asset_source``.** An asset whose
property was never set - or was edited by hand - produces the name ``Delete.``,
which matches nothing, and the object is then deleted while its mask modifier
stays on the body: a character with a hole in it and nothing left to explain it.
That case is detected up front and refused, rather than half-performed.

**It removes the modifiers but not the vertex groups**, and
``bpy.data.objects.remove()`` leaves the mesh datablock with no users until the
file is saved and reloaded. Both are harmless, both are invisible, and both are
reported - the response's job is to distinguish four different fates, not to
claim one clean outcome.
"""

import os

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
HumanService = _MPFB_SERVICES["HumanService"]

OBJECTSERVICE_MODULE = sys.modules[ObjectService.__module__]

MESH_ASSET_TYPES = getattr(
    OBJECTSERVICE_MODULE,
    "_MESH_ASSET_TYPES",
    ("Proxymeshes", "Clothes", "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair"),
)
GeneralObjectProperties = getattr(OBJECTSERVICE_MODULE, "GeneralObjectProperties", None)


def property_value(config_set, property_name, blender_object):
    """One custom property, or None when it was never set (it reads back as "")."""
    if config_set is None or blender_object is None:
        return None
    try:
        value = config_set.get_value(property_name, entity_reference=blender_object)
    except Exception:  # pylint: disable=broad-except
        return None
    if not value:
        return None
    return str(value)


def delete_group_name_from(asset_source):
    """The vertex group ``unload_mhclo_asset()`` will look for, its way.

    Reproduced statement for statement from that function, because the whole of
    the cleanup hangs off this string: it takes the basename of the recorded
    fragment, strips the mhclo extension in either case, replaces spaces with
    underscores and prefixes ``Delete.``. Reproducing it is what lets this
    payload say which modifiers *should* go before it calls anything, and notice
    when none of them would.
    """
    if not asset_source:
        return None
    name = str(os.path.basename(str(asset_source)))
    name = name.replace(".mhclo", "")
    name = name.replace(".MHCLO", "")
    name = name.replace(" ", "_")
    return "Delete." + name


def delete_group_masks_on(blender_object):
    """The MASK modifiers on this object that could be an asset's delete group.

    Every MASK modifier is *not* the answer, and that is the point of the
    filter. MPFB puts a ``Hide helpers`` MASK on every basemesh it creates, and
    a body proxy adds a ``Hide base mesh`` one - both structural, both on the
    ``body`` vertex group, and both catastrophic to delete. This field is read
    by someone about to remove an orphaned mask by hand, so naming those two
    beside the one they are looking for would be worse than naming nothing.
    ``Delete.`` is the prefix ``unload_mhclo_asset()`` itself derives, so
    filtering on it is not a heuristic of this package's own.
    """
    found = []
    for modifier in getattr(blender_object, "modifiers", None) or []:
        if getattr(modifier, "type", None) != "MASK":
            continue
        if str(getattr(modifier, "name", "")).startswith("Delete."):
            found.append(str(modifier.name))
    return found


def mask_modifiers_for(blender_object, group_name):
    """The MASK modifiers ``unload_mhclo_asset()`` would remove from this object.

    It matches on the modifier's *name*, not on its vertex group, which is worth
    reproducing exactly: a modifier renamed by hand survives the unload with its
    group intact.
    """
    found = []
    if blender_object is None or not group_name:
        return found
    for modifier in getattr(blender_object, "modifiers", None) or []:
        if getattr(modifier, "type", None) == "MASK" and getattr(modifier, "name", None) == group_name:
            found.append(str(modifier.name))
    return found


def vertex_group_names(blender_object):
    if blender_object is None:
        return []
    return [str(group.name) for group in (getattr(blender_object, "vertex_groups", None) or [])]


def object_names():
    return set(blender_object.name for blender_object in bpy.data.objects)


def blocked(asset, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=asset is not None,
        ready=False,
        removed=False,
        blocked_by=reason,
        requested_name=requested_name,
        asset_object_name=None if asset is None else asset.name,
        object_type=None if asset is None else (ObjectService.get_object_type(asset) or None),
        asset_source=property_value(GeneralObjectProperties, "asset_source", asset),
        basemesh_name=None,
        message=message,
    )
    answer.update(extra)
    return answer


requested_name = PARAMS["name"]

asset = bpy.data.objects.get(requested_name)
object_type = ObjectService.get_object_type(asset) if asset is not None else ""
asset_source = property_value(GeneralObjectProperties, "asset_source", asset)
delete_group_name = delete_group_name_from(asset_source)

basemesh = None
if asset is not None:
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(asset, "Basemesh")

if asset is None:
    result = blocked(
        None, "not_found",
        ("No object named '" + str(requested_name) + "' exists in this .blend file, so nothing "
         "was removed. Call mpfb_list_objects to see what the current scene holds."))
elif object_type not in MESH_ASSET_TYPES:
    # The refusal that matters most: unload_mhclo_asset() checks nothing and
    # would delete a basemesh or a rig as readily as a hat.
    result = blocked(
        asset, "not_a_mesh_asset",
        ("'" + asset.name + "' is " + (
            "of MPFB type '" + str(object_type) + "'" if object_type
            else "not a MakeHuman object at all")
         + ", not an MHCLO mesh asset, so nothing was removed. This tool removes clothes, body "
           "parts and topology proxies. A basemesh or a rig is refused deliberately: MPFB's "
           "unload function does not check, and would delete either."),
        known_mesh_asset_types=list(MESH_ASSET_TYPES))
elif basemesh is None:
    result = blocked(
        asset, "basemesh_not_found",
        ("'" + asset.name + "' has no MakeHuman basemesh among its nearest relatives, so nothing "
         "was removed. Removal needs the basemesh: the mask modifier hiding the body under this "
         "asset lives there, and deleting the object without it would leave the body masked with "
         "nothing to explain why."))
elif asset.mode != "OBJECT" or bpy.context.mode != "OBJECT":
    result = blocked(
        asset, "not_object_mode",
        ("Blender is in " + str(bpy.context.mode) + " mode and '" + asset.name + "' is in "
         + str(asset.mode) + " mode, so nothing was removed. Leave edit mode and call again."),
        basemesh_name=basemesh.name)
elif delete_group_name is None:
    # unload_mhclo_asset() would derive the name "Delete." from an empty
    # property, match no modifier with it, and delete the object anyway.
    result = blocked(
        asset, "asset_source_missing",
        ("'" + asset.name + "' records no 'asset_source', so the name of its delete group cannot "
         "be derived and its mask modifier could not be identified. Removing it now would delete "
         "the object and leave the body masked under an asset that is no longer there, so "
         "nothing was removed. Delete the object and its Delete.* mask modifier by hand, or "
         "restore the property."),
        basemesh_name=basemesh.name,
        mask_modifiers_present=delete_group_masks_on(basemesh))
else:
    # Everything below is read while the object still exists.
    body_proxy = ObjectService.find_object_of_type_amongst_nearest_relatives(
        asset, "Proxymeshes")
    subrig = ObjectService.find_object_of_type_amongst_nearest_relatives(
        asset, "Subrig", only_parents=True)

    asset_object_name = asset.name
    subrig_name = None if subrig is None else subrig.name
    mesh_data_name = None
    if asset.type == "MESH" and getattr(asset, "data", None) is not None:
        mesh_data_name = str(asset.data.name)

    expected_masks = []
    for owner in [basemesh, body_proxy]:
        if owner is None:
            continue
        for modifier_name in mask_modifiers_for(owner, delete_group_name):
            expected_masks.append(dict(object_name=owner.name, modifier_name=modifier_name))

    names_before = object_names()

    HumanService.unload_mhclo_asset(basemesh, asset)

    names_after = object_names()
    removed_objects = sorted(names_before - names_after)
    subrig_removed = bool(subrig_name is not None and subrig_name not in names_after)

    masks_removed = []
    masks_left = []
    for record in expected_masks:
        owner = bpy.data.objects.get(record["object_name"])
        still_there = mask_modifiers_for(owner, delete_group_name)
        if record["modifier_name"] in still_there:
            masks_left.append(record)
        else:
            masks_removed.append(record)

    groups_left = []
    for owner in [basemesh, body_proxy]:
        if owner is None:
            continue
        for group_name in vertex_group_names(owner):
            if group_name == delete_group_name:
                groups_left.append(dict(object_name=owner.name, vertex_group=group_name))

    message_parts = [
        "Removed '" + asset_object_name + "' from '" + basemesh.name + "'."]
    if masks_removed:
        message_parts.append(
            " " + str(len(masks_removed)) + " mask modifier(s) hiding the body under it were "
            "taken off.")
    else:
        message_parts.append(
            " No mask modifier referenced it, which is normal for an asset whose MHCLO defines "
            "no delete group.")
    if subrig_removed:
        message_parts.append(" Its sub-rig '" + str(subrig_name) + "' went with it.")
    elif subrig_name is not None:
        message_parts.append(
            " Its sub-rig '" + str(subrig_name) + "' was kept, because something else is still "
            "deformed by it.")
    if groups_left:
        message_parts.append(
            " The '" + delete_group_name + "' vertex group remains on the body: MPFB removes the "
            "modifiers but not the groups. It is harmless.")
    if masks_left:
        message_parts.append(
            " " + str(len(masks_left)) + " mask modifier(s) could not be removed and are still "
            "hiding part of the body; see 'mask_modifiers_left_behind'.")

    result = dict(
        found=True,
        ready=True,
        removed=True,
        blocked_by=None,
        requested_name=requested_name,
        asset_object_name=asset_object_name,
        object_type=object_type,
        asset_source=asset_source,
        basemesh_name=basemesh.name,
        body_proxy_name=None if body_proxy is None else body_proxy.name,
        delete_group_name=delete_group_name,
        mask_modifiers_removed=masks_removed,
        mask_modifiers_left_behind=masks_left,
        subrig_object_name=subrig_name,
        subrig_removed=subrig_removed,
        objects_removed=removed_objects,
        # Two things MPFB leaves behind and never mentions. Neither is a
        # failure; both are invisible unless said out loud.
        vertex_groups_left_behind=groups_left,
        mesh_data_orphaned=mesh_data_name,
        message="".join(message_parts),
    )
