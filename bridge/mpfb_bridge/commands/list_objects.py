"""
``list_objects``: which MakeHuman objects are in this scene, and what they are.

**The first command with MPFB behind it**, and the first in the table declaring
``requires_mpfb=True`` - so the dispatcher's ``mpfb_unavailable`` precondition,
which until now existed only for its own tests, is reachable from outside for
the first time.

It was chosen to be migrated first for being dull: one optional string
parameter, read-only, a result of five keys, and no dependence on anything
another command will also need. What is interesting about it is therefore not
the command but the pair - ``src/mpfbmcp/codegen/payloads/list_objects.py``
answers the same question over the other transport, and the two answers are
compared field by field against one Blender by FR 030's own live check.

**This reproduces that payload rather than tidying it up.** Four of its
behaviours are quirks worth naming, because each is a thing a reimplementation
would "fix" and thereby break the comparison:

- ``_ALL_TYPES`` is read off the service's own module, with a stale local
  vocabulary as the fallback. Reporting last year's type list is a better
  answer than failing the call.
- Matching is MPFB's own, a case-insensitive **substring** test rather than
  equality: ``"rig"`` matches ``Subrig`` and ``"mesh"`` matches both
  ``Basemesh`` and ``Proxymeshes``. ``type_recognized`` is answered the same
  way, or a caller would be told ``"rig"`` is unknown while the filter happily
  matched with it.
- ``get_object_type()`` answers ``""`` rather than ``None`` for an object
  carrying no MPFB type, and that is coerced to ``null`` in one place.
- Only ``bpy.context.scene.objects`` is searched, so the answer matches what
  the user is looking at. An object in the ``.blend`` that is not linked into
  the scene is absent here on purpose.

An empty ``object_type`` is not refused here, which looks like a gap and is
not. The dispatcher's parameter contract is about *shape*, and "not empty" is a
rule with an MPFB reason behind it - an empty filter substring-matches every
type rather than none - which mpfb-mcp's own tool applies before anything
reaches a transport. A hand-written client that sends one gets the payload's
behaviour: every MakeHuman object, with ``type_recognized`` false beside the
list saying why the answer is broader than the question.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_objects",
)

import sys

import bpy

from ..log import get_logger
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.listobjects")

PARAMS = (
    Param("object_type", TYPE_STRING, default=None, nullable=True,
          description="One of MPFB's own object type names, matched as a case-insensitive "
                      "substring. Omit or pass null to list every MakeHuman object."),
)

SUMMARY = "List the MakeHuman objects in the current scene, optionally filtered by MPFB type."

# What to report when MPFB's private ``_ALL_TYPES`` cannot be found. A copy
# rather than a guess: it is the vocabulary MPFB published when this was
# written, and it goes stale silently, which is why it is the fallback and
# never the source.
_FALLBACK_TYPES = ("Skeleton", "Subrig", "Basemesh", "Proxymeshes", "Clothes",
                   "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair")


def _all_types(object_service):
    """MPFB's object type vocabulary, read the supported way.

    ``_ALL_TYPES`` is a module-level name in ``objectservice.py``: not a member
    of ``ObjectService``, not in ``SERVICES``, and underscore-private. Being
    add-on code rather than generated code makes ``from ... import _ALL_TYPES``
    possible here for the first time, and it stays forbidden -
    [never import MPFB submodules directly](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
    survives the pivot unchanged. The module is necessarily already imported,
    since ``ObjectService`` resolved out of it, so ``sys.modules`` is both the
    supported route and the cheap one.
    """
    module = sys.modules.get(object_service.__module__)
    found = getattr(module, "_ALL_TYPES", None) if module is not None else None
    if not found:
        _LOG.warning("MPFB's _ALL_TYPES could not be read; reporting this add-on's own copy")
        return list(_FALLBACK_TYPES)
    return list(found)


def _type_is_recognized(requested, all_types):
    """Whether a requested filter names something MPFB could match.

    Mirrors ``ObjectService.object_is()``, which lowercases both sides and asks
    whether the requested name occurs *within* the stored one. Answering by
    equality instead would report ``"rig"`` as an unknown type while the filter
    below happily matches ``Subrig`` - and the whole point of the flag is that
    a caller can trust an empty list.
    """
    if requested is None:
        return True
    stripped = str(requested).lower().strip()
    if not stripped:
        return False
    for known_type in all_types:
        if stripped in known_type.lower():
            return True
    return False


def _entry(object_service, blender_object):
    # get_object_type() answers "" rather than None for an object carrying no
    # MPFB type. Only typed objects reach here, but coercing in one place is
    # what keeps this key's contract - a type name or null, never "" - true.
    object_type = object_service.get_object_type(blender_object)
    return {
        "name": blender_object.name,
        "object_type": object_type or None,
        "blender_type": blender_object.type,
    }


def list_objects(params, resolution):
    """Name the MakeHuman objects in the current scene, optionally filtered.

    Per-object output deliberately stops at the name and the two types.
    Reporting what an object was made from can cost a walk of the asset roots
    per object, and paying that for every object in the scene would make the
    cheap orienting command the expensive one.
    """
    object_service = resolution.services["ObjectService"]
    all_types = _all_types(object_service)
    requested_type = params["object_type"]

    def matches(blender_object):
        if requested_type is None:
            return bool(object_service.object_is_any_makehuman_object(blender_object))
        return bool(object_service.object_is(blender_object, requested_type))

    objects = [_entry(object_service, scene_object)
               for scene_object in bpy.context.scene.objects if matches(scene_object)]

    _LOG.debug("list_objects: %d of %d scene objects matched %r",
               len(objects), len(bpy.context.scene.objects), requested_type)

    return {
        "objects": objects,
        "count": len(objects),
        "requested_type": requested_type,
        "type_recognized": _type_is_recognized(requested_type, all_types),
        "known_types": all_types,
    }
