"""
``remove_asset``: unload one MHCLO asset, and say what is left.

Deleting the object would be wrong, which is the whole reason this exists:
``bpy.data.objects.remove()`` leaves the body's mask modifier and the garment's
sub-rig behind, so a character ends up with a hole in it and nothing to explain
why. ``HumanService.unload_mhclo_asset()`` does the job properly - and needs
guarding.

**Everything reported is read before anything is deleted.** The object's name,
type and ``asset_source`` are gone the moment the object is removed, and
``asset_source`` is what every modifier name is derived from - so a response
assembled afterwards could describe almost nothing.

Three things about ``unload_mhclo_asset()`` shape this command.

**It does not check what it was given.** Handed a basemesh or a skeleton it
deletes it, cheerfully, along with whichever mask modifier happens to match. So
the type check is here, against ObjectService's own ``_MESH_ASSET_TYPES``, and a
``Basemesh`` or ``Skeleton`` is refused outright rather than passed through.

**It derives the delete group's name from ``asset_source``.** An asset whose
property was never set - or was edited by hand - produces the name ``Delete.``,
which matches nothing, and the object is then deleted while its mask modifier
stays on the body. That case is detected up front and refused, rather than
half-performed.

**It removes the modifiers but not the vertex groups**, and
``bpy.data.objects.remove()`` leaves the mesh datablock with no users until the
file is saved and reloaded. Both are harmless, both are invisible, and both are
reported - the response's job is to distinguish four different fates, not to
claim one clean outcome.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "remove_asset",
)

import os
import sys

import bpy

from ..log import get_logger
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.removeasset")

PARAMS = (
    Param("name", TYPE_STRING, required=True,
          description="The asset object's own name, as list_objects reports it. Required: there "
                      "is no sensible default for what to take off."),
)

SUMMARY = "Take one MHCLO asset off a character, masks and sub-rig included."

# MPFB's own list, with a fallback. Read off ObjectService's module rather than
# imported, for the reason the sys.modules scan exists.
_MESH_ASSET_TYPES_FALLBACK = (
    "Proxymeshes", "Clothes", "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair")


def _objectservice_module(services):
    return sys.modules[services["ObjectService"].__module__]


def _mesh_asset_types(services):
    return getattr(_objectservice_module(services), "_MESH_ASSET_TYPES",
                   _MESH_ASSET_TYPES_FALLBACK)


def _general_object_properties(services):
    return getattr(_objectservice_module(services), "GeneralObjectProperties", None)


def _property_value(config_set, property_name, blender_object):
    """One custom property, or ``None`` when it was never set (it reads back as "")."""
    if config_set is None or blender_object is None:
        return None
    try:
        value = config_set.get_value(property_name, entity_reference=blender_object)
    except Exception:  # pylint: disable=broad-except
        return None
    if not value:
        return None
    return str(value)


def _delete_group_name_from(asset_source):
    """The vertex group ``unload_mhclo_asset()`` will look for, its way.

    Reproduced statement for statement from that function, because the whole of
    the cleanup hangs off this string: it takes the basename of the recorded
    fragment, strips the mhclo extension in either case, replaces spaces with
    underscores and prefixes ``Delete.``. Reproducing it is what lets this
    command say which modifiers *should* go before it calls anything, and notice
    when none of them would.
    """
    if not asset_source:
        return None
    name = str(os.path.basename(str(asset_source)))
    name = name.replace(".mhclo", "")
    name = name.replace(".MHCLO", "")
    name = name.replace(" ", "_")
    return "Delete." + name


def _delete_group_masks_on(blender_object):
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


def _mask_modifiers_for(blender_object, group_name):
    """The MASK modifiers ``unload_mhclo_asset()`` would remove from this object.

    It matches on the modifier's *name*, not on its vertex group, which is worth
    reproducing exactly: a modifier renamed by hand survives the unload with its
    group intact.
    """
    found = []
    if blender_object is None or not group_name:
        return found
    for modifier in getattr(blender_object, "modifiers", None) or []:
        if (getattr(modifier, "type", None) == "MASK"
                and getattr(modifier, "name", None) == group_name):
            found.append(str(modifier.name))
    return found


def _vertex_group_names(blender_object):
    if blender_object is None:
        return []
    return [str(group.name) for group in (getattr(blender_object, "vertex_groups", None) or [])]


def _object_names():
    return set(blender_object.name for blender_object in bpy.data.objects)


def _blocked(services, requested_name, asset, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    object_service = services["ObjectService"]
    answer = dict(
        found=asset is not None,
        ready=False,
        removed=False,
        blocked_by=reason,
        requested_name=requested_name,
        asset_object_name=None if asset is None else asset.name,
        object_type=None if asset is None else (object_service.get_object_type(asset) or None),
        asset_source=_property_value(_general_object_properties(services), "asset_source", asset),
        basemesh_name=None,
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _refusal(services, requested_name, asset, object_type, basemesh, delete_group_name):
    """The first refusal that applies, or ``None``."""
    def blocked(reason, text, **extra):
        return _blocked(services, requested_name, asset, reason, text, **extra)

    if asset is None:
        return blocked(
            "not_found",
            "No object named '{!s}' exists in this .blend file, so nothing was removed. Call "
            "mpfb_list_objects to see what the current scene holds.".format(requested_name))
    if object_type not in _mesh_asset_types(services):
        # The refusal that matters most: unload_mhclo_asset() checks nothing and
        # would delete a basemesh or a rig as readily as a hat.
        return blocked(
            "not_a_mesh_asset",
            "'{:s}' is {:s}, not an MHCLO mesh asset, so nothing was removed. This tool removes "
            "clothes, body parts and topology proxies. A basemesh or a rig is refused "
            "deliberately: MPFB's unload function does not check, and would delete either.".format(
                asset.name,
                "of MPFB type '{!s}'".format(object_type) if object_type
                else "not a MakeHuman object at all"),
            known_mesh_asset_types=list(_mesh_asset_types(services)))
    if basemesh is None:
        return blocked(
            "basemesh_not_found",
            "'{:s}' has no MakeHuman basemesh among its nearest relatives, so nothing was "
            "removed. Removal needs the basemesh: the mask modifier hiding the body under this "
            "asset lives there, and deleting the object without it would leave the body masked "
            "with nothing to explain why.".format(asset.name))
    if asset.mode != "OBJECT" or bpy.context.mode != "OBJECT":
        return blocked(
            "not_object_mode",
            "Blender is in {:s} mode and '{:s}' is in {:s} mode, so nothing was removed. Leave "
            "edit mode and call again.".format(
                str(bpy.context.mode), asset.name, str(asset.mode)),
            basemesh_name=basemesh.name)
    if delete_group_name is None:
        # unload_mhclo_asset() would derive the name "Delete." from an empty
        # property, match no modifier with it, and delete the object anyway.
        return blocked(
            "asset_source_missing",
            "'{:s}' records no 'asset_source', so the name of its delete group cannot be derived "
            "and its mask modifier could not be identified. Removing it now would delete the "
            "object and leave the body masked under an asset that is no longer there, so nothing "
            "was removed. Delete the object and its Delete.* mask modifier by hand, or restore "
            "the property.".format(asset.name),
            basemesh_name=basemesh.name,
            mask_modifiers_present=_delete_group_masks_on(basemesh))
    return None


def _message_for(asset_object_name, basemesh, masks_removed, subrig_name, subrig_removed,
                 groups_left, masks_left, delete_group_name):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Removed '{:s}' from '{:s}'.".format(asset_object_name, basemesh.name)]
    if masks_removed:
        parts.append(" {:d} mask modifier(s) hiding the body under it were taken off.".format(
            len(masks_removed)))
    else:
        parts.append(" No mask modifier referenced it, which is normal for an asset whose MHCLO "
                     "defines no delete group.")
    if subrig_removed:
        parts.append(" Its sub-rig '{!s}' went with it.".format(subrig_name))
    elif subrig_name is not None:
        parts.append(" Its sub-rig '{!s}' was kept, because something else is still deformed by "
                     "it.".format(subrig_name))
    if groups_left:
        parts.append(" The '{:s}' vertex group remains on the body: MPFB removes the modifiers "
                     "but not the groups. It is harmless.".format(delete_group_name))
    if masks_left:
        parts.append(" {:d} mask modifier(s) could not be removed and are still hiding part of "
                     "the body; see 'mask_modifiers_left_behind'.".format(len(masks_left)))
    return "".join(parts)


def remove_asset(params, resolution):  # pylint: disable=too-many-locals
    """Take one asset off, having established that it is one and that it can be."""
    services = resolution.services
    object_service = services["ObjectService"]
    general_properties = _general_object_properties(services)

    requested_name = params["name"]

    asset = bpy.data.objects.get(requested_name)
    object_type = object_service.get_object_type(asset) if asset is not None else ""
    asset_source = _property_value(general_properties, "asset_source", asset)
    delete_group_name = _delete_group_name_from(asset_source)

    basemesh = None
    if asset is not None:
        basemesh = object_service.find_object_of_type_amongst_nearest_relatives(asset, "Basemesh")

    refused = _refusal(services, requested_name, asset, object_type, basemesh, delete_group_name)
    if refused is not None:
        _LOG.debug("remove_asset: refused %r for %r", refused["blocked_by"], requested_name)
        return refused

    # Everything below is read while the object still exists.
    body_proxy = object_service.find_object_of_type_amongst_nearest_relatives(
        asset, "Proxymeshes")
    subrig = object_service.find_object_of_type_amongst_nearest_relatives(
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
        for modifier_name in _mask_modifiers_for(owner, delete_group_name):
            expected_masks.append(dict(object_name=owner.name, modifier_name=modifier_name))

    names_before = _object_names()

    services["HumanService"].unload_mhclo_asset(basemesh, asset)

    names_after = _object_names()
    removed_objects = sorted(names_before - names_after)
    subrig_removed = bool(subrig_name is not None and subrig_name not in names_after)

    masks_removed = []
    masks_left = []
    for record in expected_masks:
        owner = bpy.data.objects.get(record["object_name"])
        still_there = _mask_modifiers_for(owner, delete_group_name)
        if record["modifier_name"] in still_there:
            masks_left.append(record)
        else:
            masks_removed.append(record)

    groups_left = []
    for owner in [basemesh, body_proxy]:
        if owner is None:
            continue
        for group_name in _vertex_group_names(owner):
            if group_name == delete_group_name:
                groups_left.append(dict(object_name=owner.name, vertex_group=group_name))

    _LOG.debug("remove_asset: removed %r, %d mask(s) taken off",
               asset_object_name, len(masks_removed))

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
        message=_message_for(asset_object_name, basemesh, masks_removed, subrig_name,
                             subrig_removed, groups_left, masks_left, delete_group_name),
    )

    # The verb is "removed". See shared/performed.py.
    return with_performed(result, result["removed"])
