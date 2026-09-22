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

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
 Five of its behaviours look like oversights and are decisions; a
reimplementation that "fixed" any of them would break the field-by-field
comparison the migration rests on, and four of the five are load-bearing for
callers:

- **``asset_info`` has three shapes, not one union.** Which keys are present
  says which question was asked; their values say whether it could be answered.
  A union with the inapplicable keys nulled would report ``mhclo_path: null``
  on a skeleton, which reads as "we looked for its mhclo and failed" rather
  than "a skeleton does not have one". A type in no family at all gets an empty
  dict, which claims nothing.
- **A relative's entry carries ``asset_info`` and an untyped neighbour's
  carries ``rigify_role``.** They are different shapes because the two are
  found by different walks and different things can be said about them.
- **``rigify_role`` is asked of *typed* objects too.** MPFB tags the rig it
  generates through Rigify as a ``Skeleton``, so restricting the question to
  untyped objects would drop the field from the commonest generated rig there
  is.
- **``bpy.data.objects`` is searched by name, not the scene.** Object names are
  unique across the whole ``.blend``, and "exists, but not in this scene" is a
  far more useful answer than a bare "not found" - which is also why every
  entry carries ``in_current_scene``.
- **Nothing is selected or activated in order to be inspected.**
  ``ObjectService`` carries destructive and selection-mutating methods; none is
  touched here, because changing what the user has selected in order to answer
  a read-only question is a side effect they would see and did not ask for.

The two property sets and the two type vocabularies are module-level names in
MPFB rather than services, so they are reached through the module a resolved
service already came from - never by importing an MPFB submodule, several of
which create directories on import.
[Never import MPFB submodules directly](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
survives the pivot: being add-on code makes the import *possible* and leaves it
forbidden.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_object_info",
)

import os
import sys

import bpy

from ..log import get_logger
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getobjectinfo")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="The name of the object to report on. Omit or pass null to report on "
                      "whatever object is currently active in Blender."),
)

SUMMARY = "Identify one object, what it was made from, and the objects that belong with it."

# What to assume when MPFB stops publishing one of its private type
# vocabularies. Copies rather than guesses, and the fallback rather than the
# source, for the reason ``list_objects`` keeps its own: they go stale silently.
_FALLBACK_SKELETON_TYPES = ("Skeleton", "Subrig")
_FALLBACK_MESH_ASSET_TYPES = (
    "Proxymeshes", "Clothes", "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair")


class _Subject:
    """MPFB's services and the module-level names this command reads beside them.

    Assembled once per call rather than at import: MPFB can be disabled and
    re-enabled inside one Blender session, and a services dict cached across
    that is exactly the stale state nobody thinks to suspect. Gathering the four
    private names here rather than at each use keeps the ``sys.modules`` reach
    in one place, where the rule about it can be stated once.
    """

    __slots__ = ("services", "skeleton_types", "mesh_asset_types",
                 "general_properties", "human_properties")

    def __init__(self, services):
        self.services = services
        objectservice_module = sys.modules[services["ObjectService"].__module__]
        humanservice_module = sys.modules[services["HumanService"].__module__]

        self.skeleton_types = getattr(
            objectservice_module, "_SKELETON_TYPES", _FALLBACK_SKELETON_TYPES)
        self.mesh_asset_types = getattr(
            objectservice_module, "_MESH_ASSET_TYPES", _FALLBACK_MESH_ASSET_TYPES)
        # GeneralObjectProperties is imported by objectservice.py;
        # HumanObjectProperties is not, and lives on humanservice.py's module.
        self.general_properties = getattr(
            objectservice_module, "GeneralObjectProperties", None)
        self.human_properties = getattr(humanservice_module, "HumanObjectProperties", None)


def _property_value(config_set, property_name, blender_object):
    """One BlenderConfigSet string property, or ``None``.

    These are entities rather than services, so they may be absent if MPFB
    reorganizes - hence the guard rather than an attribute error deep in the
    response build. An unset string property reads back as ``""``, which means
    "nothing was recorded" and must not be reported as a fragment.
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


def _as_path(path):
    """Coerce at the point a path enters the response.

    MPFB's path getters are annotated as returning ``str``, but
    ``LocationService.get_mpfb_root()`` has been caught handing back a
    ``pathlib.Path``, which the dispatcher's serialize-before-answering check
    would turn into a ``result_not_serializable`` envelope for the whole call.
    """
    if not path:
        return None
    return str(path)


def _rig_definition_path(subject, rig_type):
    """The rig definition file this rig would have been built from, or ``None``.

    Mirrors how ``HumanService.add_builtin_rig()`` assembles the file it loads
    from: ``<mpfb data>/rigs/<standard or rigify>/rig.<name>.json``. Nothing
    records which definition a rig was built from, so this is derived from the
    identified type, and reported only when the file is actually there.
    """
    if not rig_type or rig_type == "unknown":
        return None
    if rig_type.startswith("custom."):
        # Custom rig definitions live under a user asset root, not in MPFB's own
        # data, so the path is taken from the entry rather than derived.
        wanted_name = rig_type[len("custom."):]
        for custom_rig in subject.services["AssetService"].get_custom_rigs():
            if custom_rig.get("name") == wanted_name:
                return _as_path(custom_rig.get("path"))
        return None
    if rig_type.startswith("rigify_generated."):
        # Rigify built this from a metarig; it was never loaded from a
        # definition, so there is no file to point at.
        return None
    is_rigify = rig_type.startswith("rigify.")
    rig_name = rig_type[len("rigify."):] if is_rigify else rig_type
    rigs_directory = _as_path(subject.services["LocationService"].get_mpfb_data("rigs"))
    if rigs_directory is None:
        return None
    candidate = os.path.join(
        rigs_directory, "rigify" if is_rigify else "standard", "rig." + rig_name + ".json")
    if not os.path.isfile(candidate):
        # Covers rigify.unknown, whose name is a placeholder rather than a rig,
        # as well as a definition that is simply not installed.
        return None
    return candidate


def _material_type_of(subject, blender_object):
    """What kind of material this object carries, as MPFB identifies it.

    ``identify_material()`` takes a material rather than an object and answers
    ``"empty"`` for ``None``, so the pair composes without a guard - but only
    meshes have material slots at all. This is the one ``asset_info`` value
    derived from the material actually present rather than from a record of what
    was loaded, and it is a documented heuristic, not an authority.
    """
    if blender_object.type != "MESH":
        return None
    material_service = subject.services["MaterialService"]
    return material_service.identify_material(material_service.get_material(blender_object, 0))


def _material_asset_info(subject, blender_object, object_type):
    """The material fragment recorded on this object, and where it resolves to.

    One response key filled from two different properties, each resolving
    against a different asset subdir. ``material_source`` is the skin, written
    by ``HumanService.set_character_skin()`` onto the basemesh and, when there
    is one, the body proxy; it lives under ``skins``. ``alternative_material``
    is a material other than the asset's own, and lives under the asset's own
    subdir. Resolving either against the other's directory does not raise - it
    silently reports null for an asset that is installed, which is exactly the
    failure the fragment/path pairing exists to make visible.
    """
    fragment = _property_value(subject.human_properties, "material_source", blender_object)
    asset_subdir = "skins"
    if fragment is None:
        fragment = _property_value(
            subject.general_properties, "alternative_material", blender_object)
        asset_subdir = str(object_type).lower()
    if fragment is None:
        # No fragment means no lookup: the asset-root walk happens only when
        # there is something to resolve.
        return {"material_source": None, "mhmat_path": None}
    return {
        "material_source": fragment,
        "mhmat_path": _as_path(
            subject.services["AssetService"].find_asset_absolute_path(fragment, asset_subdir)),
    }


def _asset_info_for(subject, blender_object, object_type):
    """What this object was made from, in one of three shapes. See the docstring."""
    if not object_type:
        return None

    if object_type in subject.skeleton_types:
        rig_type = None
        if blender_object.type == "ARMATURE":
            # identify_rig() dereferences .data.bones, which a mesh does not
            # have. It matches bone names rather than reading back a property,
            # so a hand-edited armature can be identified as something it was
            # not built from.
            rig_type = subject.services["RigService"].identify_rig(blender_object)
        return {
            "rig_type": rig_type,
            "rig_definition_path": _rig_definition_path(subject, rig_type),
        }

    if object_type in subject.mesh_asset_types:
        asset_source = _property_value(
            subject.general_properties, "asset_source", blender_object)
        mhclo_path = None
        if asset_source is not None:
            # find_clothes_absolute_path() reads asset_source and the object
            # type and resolves both, for every mesh asset type and not only
            # Clothes. The file it points at may carry a .proxy extension rather
            # than .mhclo, since MPFB imports them all through the same format.
            mhclo_path = _as_path(
                subject.services["ClothesService"].find_clothes_absolute_path(blender_object))
        info = {
            "asset_source": asset_source,
            "mhclo_path": mhclo_path,
            "material_type": _material_type_of(subject, blender_object),
        }
        info.update(_material_asset_info(subject, blender_object, object_type))
        return info

    if object_type == "Basemesh":
        info = {"material_type": _material_type_of(subject, blender_object)}
        info.update(_material_asset_info(subject, blender_object, object_type))
        return info

    # A type MPFB knows about that none of the families above covers - it added
    # one. Report the object normally and say, by an empty dict, that no asset
    # question applies to this type, rather than claiming any specific answer.
    return dict()


def _in_current_scene(blender_object):
    return blender_object.name in bpy.context.scene.objects


def _related_entry(subject, blender_object):
    """One MakeHuman relative: what it is and what it was made from."""
    object_service = subject.services["ObjectService"]
    object_type = object_service.get_object_type(blender_object) or None
    return {
        "name": blender_object.name,
        "object_type": object_type,
        "blender_type": blender_object.type,
        # Relatives are found through get_list_of_children(), which walks
        # bpy.data.objects rather than the scene, so a relative can sit outside
        # the scene list_objects searched. Flagging each one is what keeps that
        # from reading as a contradiction between the two commands.
        "in_current_scene": _in_current_scene(blender_object),
        "asset_info": _asset_info_for(subject, blender_object, object_type),
    }


def _rigify_role(subject, blender_object):
    """Whether this object is a Rigify metarig, a generated rig, or neither.

    Neither helper returns a bool: the first hands back Rigify's ``rig_id``
    string, the second a real bool. Only their truthiness is meaningful. Asked
    of typed objects as well as untyped ones - see this module's docstring.
    """
    object_service = subject.services["ObjectService"]
    if object_service.object_is_generated_rigify_rig(blender_object):
        return "generated_rig"
    if object_service.object_is_rigify_metarig(blender_object):
        return "metarig"
    return None


def _other_related_entry(subject, blender_object):
    """One plain Blender object in the family.

    No ``asset_info`` here: these carry no MPFB type, so that value could only
    ever be null, and a key that is always null is noise. ``rigify_role`` is the
    analogous field for what little can be said about them.
    """
    return {
        "name": blender_object.name,
        "object_type": None,
        "blender_type": blender_object.type,
        "in_current_scene": _in_current_scene(blender_object),
        "rigify_role": _rigify_role(subject, blender_object),
    }


def _neighbourhood(subject, blender_object):
    """Every object in this object's family, typed or not.

    ``find_related_objects()`` only yields objects carrying an MPFB type, so the
    untyped half of the neighbourhood needs its own walk. Same shape as
    ``ObjectService``'s: the object, its children recursively, then the parent
    chain and each parent's children.
    """
    object_service = subject.services["ObjectService"]
    collected = []

    def collect(candidate):
        if candidate is None or candidate in collected:
            return
        collected.append(candidate)
        for child in object_service.get_list_of_children(candidate):
            collect(child)

    collect(blender_object)
    parent = blender_object.parent
    while parent is not None:
        collect(parent)
        parent = parent.parent
    return collected


def _resolve(requested_name):
    """The object to report on, and the sentence to say when there is none."""
    if requested_name is None:
        # The view layer rather than bpy.context.active_object: this code runs
        # from a timer or a background loop, not from a viewport operator, and
        # the view-layer form does not depend on which UI area happens to be
        # current. It is None whenever nothing is active, which is an answer.
        found = bpy.context.view_layer.objects.active
        if found is None:
            return (None, "No object name was given and no object is active in this Blender "
                          "session, so there is nothing to report on. Select an object, or call "
                          "mpfb_list_objects and pass one of its names.")
        return (found, None)

    found = bpy.data.objects.get(requested_name)
    if found is None:
        return (None, "No object named '{:s}' exists in this .blend file. Call mpfb_list_objects "
                      "to see what the current scene holds.".format(str(requested_name)))
    return (found, None)


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
    subject = _Subject(resolution.services)
    object_service = subject.services["ObjectService"]

    requested_name = params["name"]
    resolved_from = "active_object" if requested_name is None else "name"
    blender_object, message = _resolve(requested_name)

    if blender_object is None:
        _LOG.debug("get_object_info: nothing resolved from %r", requested_name)
        return {
            "found": False,
            "resolved_from": resolved_from,
            "name": None,
            "message": message,
        }

    object_type = object_service.get_object_type(blender_object) or None
    in_scene = _in_current_scene(blender_object)

    related_objects = []
    seen_names = []
    for relative in object_service.find_related_objects(blender_object):
        # find_all_objects_of_type_amongst_nearest_relatives() yields the object
        # it was asked about first, and find_related_objects() is a thin wrapper
        # over it, so the subject turns up in its own relatives. The traversal
        # excludes the branch it arrived from, but dedupe anyway: a duplicate
        # would read as two distinct objects.
        if relative is blender_object or relative.name in seen_names:
            continue
        seen_names.append(relative.name)
        related_objects.append(_related_entry(subject, relative))

    other_related_objects = [
        _other_related_entry(subject, neighbour)
        for neighbour in _neighbourhood(subject, blender_object)
        if neighbour is not blender_object
        and not object_service.object_is_any_makehuman_object(neighbour)
    ]

    rigify_role = _rigify_role(subject, blender_object)

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
        "asset_info": _asset_info_for(subject, blender_object, object_type),
        "related_objects": related_objects,
        "other_related_objects": other_related_objects,
        "message": _message_for(
            blender_object, object_type, rigify_role, in_scene, len(related_objects)),
    }
