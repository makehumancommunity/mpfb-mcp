"""
``get_object_info``: what one object is, what it was made from, what is with it.

Where ``list_objects`` orients a caller in a scene, this answers about one
object: its MPFB type, the asset or rig definition it came from, the MakeHuman
objects it belongs with, and the plain Blender objects sitting in the same
family. It is the tool an agent reaches for after a listing, and the one whose
answer other tools act on.

**Failing to resolve a subject is a successful answer here, not an error.** Two
situations produce it - no object by that name anywhere in the ``.blend``, and
no active object at all - and ``message`` says which, so an agent that guessed
at a name gets a "no" it can recover from rather than a ``command_failed``
envelope it cannot.

**What an object was made from, and what belongs with it, is read by
[`shared/asset_info.py`](../shared/asset_info.py)**, together with the four
decisions there that look like oversights - three ``asset_info`` shapes, two
entry shapes, ``rigify_role`` asked of typed objects, nothing selected in order
to be inspected. It moved there so that ``get_character_summary`` reports a
character's rig, assets and skin from the same walk
([FR 034](../../../feature-requests/done/034-character-summary/README.md)). The
subject is resolved by [`shared/subject_resolution.py`](../shared/subject_resolution.py),
like every other command's, and what is left here is the answer's shape.

**That the file is searched by name, not the scene, matters most here.** Object
names are unique across the whole ``.blend``, and "exists, but not in this
scene" is a far more useful answer than a bare "not found" - which is also why
every entry carries ``in_current_scene``.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_object_info",
)

from ..log import get_logger
from ..shared import asset_info
from ..shared import subject_resolution
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getobjectinfo")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="The name of the object to report on. Omit or pass null to report on "
                      "whatever object is currently active in Blender."),
)

SUMMARY = "Identify one object, what it was made from, and the objects that belong with it."


def _message_for(blender_object, object_type, rigify_role, in_scene, related_count):
    """The sentence an agent reads before it reads the fields."""
    parts = []
    if object_type:
        parts.append("'{:s}' is a MakeHuman {:s} object".format(blender_object.name, object_type))
    elif rigify_role is not None:
        # Untyped *and* a Rigify rig. Saying only "plain Blender object" here
        # would be actively wrong: this is very often the armature that actually
        # drives a MakeHuman character, and an agent told it was plain would
        # conclude the character has no rig.
        parts.append(
            "'{:s}' carries no MPFB object type, but it is a Rigify {:s}, so it may still be "
            "what drives a MakeHuman character".format(
                blender_object.name,
                "generated rig" if rigify_role == "generated_rig" else "metarig"))
    else:
        parts.append("'{:s}' carries no MPFB object type: it is a plain Blender object".format(
            blender_object.name))
    if not in_scene:
        # The one found case where the next step is not obvious, and the whole
        # reason in_current_scene is reported rather than the object simply
        # failing to resolve.
        parts.append(", and it exists in this .blend file without being linked into the current "
                     "scene, so mpfb_list_objects does not list it")
    parts.append(". {:d} related MakeHuman objects were found.".format(related_count))
    return "".join(parts)


def get_object_info(params, resolution):
    """Report on one object: what it is, what made it, and what belongs with it."""
    lookup = asset_info.Lookup(resolution.services)
    object_service = lookup.services["ObjectService"]

    requested_name = params["name"]
    # Any object at all is a subject here, so the caller is not told to select
    # a MakeHuman one.
    blender_object, resolved_by, message = subject_resolution.resolve_subject(
        requested_name, select="an object")
    # This answer says "active_object" where the seventeen other commands say
    # "active", under a different key. Renaming either breaks a caller, so the
    # difference is kept on purpose and recorded in NEXT_STEPS.md
    # ("resolved_from and subject_resolved_by").
    resolved_from = "active_object" if resolved_by == "active" else resolved_by

    if blender_object is None:
        _LOG.debug("get_object_info: nothing resolved from %r", requested_name)
        return {
            "found": False,
            "resolved_from": resolved_from,
            "name": None,
            "message": message,
        }

    object_type = object_service.get_object_type(blender_object) or None
    in_scene = asset_info.in_current_scene(blender_object)
    related_objects = asset_info.related_objects(lookup, blender_object)
    other_related_objects = asset_info.other_related_objects(lookup, blender_object)
    rigify_role = asset_info.rigify_role(lookup, blender_object)

    _LOG.debug("get_object_info: %r is %r with %d relatives",
               blender_object.name, object_type, len(related_objects))

    return {
        "found": True,
        "resolved_from": resolved_from,
        "name": blender_object.name,
        "in_current_scene": in_scene,
        "object_type": object_type,
        "blender_type": blender_object.type,
        "is_makehuman_object": bool(object_type),
        # Always present, unlike on a relative entry, where it is the untyped
        # half's substitute for asset_info. The subject shape is a union rather
        # than a split, so an agent that found a Rigify rig in some character's
        # other_related_objects and then asked about it by name gets at least as
        # much back as the entry that sent it there.
        "rigify_role": rigify_role,
        "asset_info": asset_info.asset_info_for(lookup, blender_object, object_type),
        "related_objects": related_objects,
        "other_related_objects": other_related_objects,
        "message": _message_for(
            blender_object, object_type, rigify_role, in_scene, len(related_objects)),
    }
