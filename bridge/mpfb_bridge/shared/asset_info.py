"""
What an object was made from, and which objects belong with it.

**One implementation, imported by both commands that report it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/``. ``get_object_info`` answers about one object with everything
here; ``get_character_summary`` reports the rig, the equipped assets and the
skin of a whole character from the same walk and the same ``asset_info``,
under the same names
([FR 034](../../../feature-requests/done/034-character-summary/README.md)). A
summary that walked the family its own way could report "no rig" beside
``get_object_info``'s "rig ``default``", and the caller would act on whichever
it read last.

Four of the behaviours below look like oversights and are decisions; a
reimplementation that "fixed" any of them would change what both commands
answer:

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
forbidden. :class:`Lookup` is where that reach happens, once per call, and it
is what every function here takes in place of the ``services`` dict the other
shared modules take.
"""

__all__ = (
    "Lookup",
    "asset_info_for",
    "in_current_scene",
    "neighbourhood",
    "other_related_entry",
    "other_related_objects",
    "related_entry",
    "related_objects",
    "rigify_role",
)

import os

import bpy

from . import mpfb_surface

# What to assume when MPFB stops publishing one of its private type
# vocabularies. Copies rather than guesses, and the fallback rather than the
# source, for the reason ``list_objects`` keeps its own: they go stale silently.
_FALLBACK_SKELETON_TYPES = ("Skeleton", "Subrig")
_FALLBACK_MESH_ASSET_TYPES = (
    "Proxymeshes", "Clothes", "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair")


class Lookup:
    """MPFB's services and the module-level names this module reads beside them.

    Assembled once per call rather than at import: MPFB can be disabled and
    re-enabled inside one Blender session, and a services dict cached across
    that is exactly the stale state nobody thinks to suspect. Gathering the four
    private names here reads each once per call rather than at every use; how
    they are read is [`mpfb_surface.py`](mpfb_surface.py)'s.
    """

    __slots__ = ("services", "skeleton_types", "mesh_asset_types",
                 "general_properties", "human_properties")

    def __init__(self, services):
        self.services = services
        self.skeleton_types = mpfb_surface.module_level(
            services, "ObjectService", "_SKELETON_TYPES", fallback=_FALLBACK_SKELETON_TYPES)
        self.mesh_asset_types = mpfb_surface.module_level(
            services, "ObjectService", "_MESH_ASSET_TYPES", fallback=_FALLBACK_MESH_ASSET_TYPES)
        # GeneralObjectProperties is imported by objectservice.py;
        # HumanObjectProperties is not, and lives on humanservice.py's module.
        self.general_properties = mpfb_surface.general_object_properties(services)
        self.human_properties = mpfb_surface.human_object_properties(services)


def _rig_definition_path(lookup, rig_type):
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
        for custom_rig in lookup.services["AssetService"].get_custom_rigs():
            if custom_rig.get("name") == wanted_name:
                return mpfb_surface.as_path(custom_rig.get("path"))
        return None
    if rig_type.startswith("rigify_generated."):
        # Rigify built this from a metarig; it was never loaded from a
        # definition, so there is no file to point at.
        return None
    is_rigify = rig_type.startswith("rigify.")
    rig_name = rig_type[len("rigify."):] if is_rigify else rig_type
    rigs_directory = mpfb_surface.as_path(lookup.services["LocationService"].get_mpfb_data("rigs"))
    if rigs_directory is None:
        return None
    candidate = os.path.join(
        rigs_directory, "rigify" if is_rigify else "standard", "rig." + rig_name + ".json")
    if not os.path.isfile(candidate):
        # Covers rigify.unknown, whose name is a placeholder rather than a rig,
        # as well as a definition that is simply not installed.
        return None
    return candidate


def _material_type_of(lookup, blender_object):
    """What kind of material this object carries, as MPFB identifies it.

    ``identify_material()`` takes a material rather than an object and answers
    ``"empty"`` for ``None``, so the pair composes without a guard - but only
    meshes have material slots at all. This is the one ``asset_info`` value
    derived from the material actually present rather than from a record of what
    was loaded, and it is a documented heuristic, not an authority.
    """
    if blender_object.type != "MESH":
        return None
    material_service = lookup.services["MaterialService"]
    return material_service.identify_material(material_service.get_material(blender_object, 0))


def _material_asset_info(lookup, blender_object, object_type):
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
    fragment = mpfb_surface.property_value(
        lookup.human_properties, "material_source", blender_object)
    asset_subdir = "skins"
    if fragment is None:
        fragment = mpfb_surface.property_value(
            lookup.general_properties, "alternative_material", blender_object)
        asset_subdir = str(object_type).lower()
    if fragment is None:
        # No fragment means no lookup: the asset-root walk happens only when
        # there is something to resolve.
        return {"material_source": None, "mhmat_path": None}
    return {
        "material_source": fragment,
        "mhmat_path": mpfb_surface.as_path(
            lookup.services["AssetService"].find_asset_absolute_path(fragment, asset_subdir)),
    }


def asset_info_for(lookup, blender_object, object_type):
    """What this object was made from, in one of three shapes. See this module's docstring."""
    if not object_type:
        return None

    if object_type in lookup.skeleton_types:
        rig_type = None
        if blender_object.type == "ARMATURE":
            # identify_rig() dereferences .data.bones, which a mesh does not
            # have. It matches bone names rather than reading back a property,
            # so a hand-edited armature can be identified as something it was
            # not built from.
            rig_type = lookup.services["RigService"].identify_rig(blender_object)
        return {
            "rig_identified_as": rig_type,
            "rig_definition_path": _rig_definition_path(lookup, rig_type),
        }

    if object_type in lookup.mesh_asset_types:
        asset_source = mpfb_surface.property_value(
            lookup.general_properties, "asset_source", blender_object)
        mhclo_path = None
        if asset_source is not None:
            # find_clothes_absolute_path() reads asset_source and the object
            # type and resolves both, for every mesh asset type and not only
            # Clothes. The file it points at may carry a .proxy extension rather
            # than .mhclo, since MPFB imports them all through the same format.
            mhclo_path = mpfb_surface.as_path(
                lookup.services["ClothesService"].find_clothes_absolute_path(blender_object))
        info = {
            "asset_source": asset_source,
            "mhclo_path": mhclo_path,
            "material_identified_as": _material_type_of(lookup, blender_object),
        }
        info.update(_material_asset_info(lookup, blender_object, object_type))
        return info

    if object_type == "Basemesh":
        info = {"material_identified_as": _material_type_of(lookup, blender_object)}
        info.update(_material_asset_info(lookup, blender_object, object_type))
        return info

    # A type MPFB knows about that none of the families above covers - it added
    # one. Report the object normally and say, by an empty dict, that no asset
    # question applies to this type, rather than claiming any specific answer.
    return dict()


def in_current_scene(blender_object):
    """Whether ``blender_object`` is linked into the current scene, which ``list_objects`` searches."""
    return blender_object.name in bpy.context.scene.objects


def related_entry(lookup, blender_object):
    """One MakeHuman relative: what it is and what it was made from."""
    object_service = lookup.services["ObjectService"]
    object_type = object_service.get_object_type(blender_object) or None
    return {
        "name": blender_object.name,
        "object_type": object_type,
        "blender_type": blender_object.type,
        # Relatives are found through get_list_of_children(), which walks
        # bpy.data.objects rather than the scene, so a relative can sit outside
        # the scene list_objects searched. Flagging each one is what keeps that
        # from reading as a contradiction between the two commands.
        "in_current_scene": in_current_scene(blender_object),
        "asset_info": asset_info_for(lookup, blender_object, object_type),
    }


def rigify_role(lookup, blender_object):
    """Whether this object is a Rigify metarig, a generated rig, or neither.

    Neither helper returns a bool: the first hands back Rigify's ``rig_id``
    string, the second a real bool. Only their truthiness is meaningful. Asked
    of typed objects as well as untyped ones - see this module's docstring.
    """
    object_service = lookup.services["ObjectService"]
    if object_service.object_is_generated_rigify_rig(blender_object):
        return "generated_rig"
    if object_service.object_is_rigify_metarig(blender_object):
        return "metarig"
    return None


def other_related_entry(lookup, blender_object):
    """One plain Blender object in the family.

    No ``asset_info`` here: these carry no MPFB type, so that value could only
    ever be null, and a key that is always null is noise. ``rigify_role`` is the
    analogous field for what little can be said about them.
    """
    return {
        "name": blender_object.name,
        "object_type": None,
        "blender_type": blender_object.type,
        "in_current_scene": in_current_scene(blender_object),
        "rigify_role": rigify_role(lookup, blender_object),
    }


def neighbourhood(lookup, blender_object):
    """Every object in this object's family, typed or not.

    ``find_related_objects()`` only yields objects carrying an MPFB type, so the
    untyped half of the neighbourhood needs its own walk. Same shape as
    ``ObjectService``'s: the object, its children recursively, then the parent
    chain and each parent's children.
    """
    object_service = lookup.services["ObjectService"]
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


def related_objects(lookup, blender_object):
    """Every MakeHuman relative of ``blender_object``, one :func:`related_entry` each.

    In ``ObjectService.find_related_objects()``'s order, which is the order both
    commands report.
    """
    object_service = lookup.services["ObjectService"]
    entries = []
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
        entries.append(related_entry(lookup, relative))
    return entries


def other_related_objects(lookup, blender_object):
    """Every plain Blender object in the family, one :func:`other_related_entry` each."""
    object_service = lookup.services["ObjectService"]
    return [
        other_related_entry(lookup, neighbour)
        for neighbour in neighbourhood(lookup, blender_object)
        if neighbour is not blender_object
        and not object_service.object_is_any_makehuman_object(neighbour)
    ]
