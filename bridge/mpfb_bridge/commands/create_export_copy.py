"""
``create_export_copy``: a processed copy of a character, for another application to open.

MPFB's **Export copy** panel, rebuilt from services. The panel's operator
(``ui/operations/exportops/operators/createexportcopy.py``) composes
``ExportService``, ``TargetService`` and ``FaceService`` calls in
``hardened_execute()`` and there is no service that does the same, so - as
``set_asset_material`` does for the asset library's material operator - this
command reproduces the sequence from the services it calls
([when mpfb-mcp models a UI concept](../../../specifications/mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not)).
It does not call ``bpy.ops.mpfb.export_copy``: that reads its options from the
user's ``EXPO_*`` scene properties, so calling it would mean writing the user's
panel settings and putting them back, and importing a UI operator is the rule
this package does not break.

**The panel's eleven options, its defaults, and its order**: copy, bake the
shape keys, load visemes and face units, interpolate them onto the mesh assets,
bake modifiers and remove helpers, remove the modifiers set to ``REMOVE``, and
remove the basemesh. Where the order or a quirk is the operator's, it is
reproduced. Where this command departs, it is below and in the answer.

**Departures, each reported in the answer rather than made silently:**

- **The copy is repaired.** ``ExportService.create_character_copy()`` copies the
  root and its *direct* children only, and points one modifier at the new rig:
  the one named ``Armature``. FR 039's live check found both short: a garment
  with a sub-rig is the sub-rig's child, so it is a grandchild of the root and
  is **not copied at all**; and the ``Armature PV`` modifier MPFB adds for
  preserve-volume weights (``RigService.ensure_armature_modifier()``, on every
  generated Rigify character) still points at the **original** rig, so the
  copy's body is partly deformed by the original's pose. The same live check
  answered the request's Rigify question: ``Object.copy()`` remaps a rig's own
  object drivers and constraints to the copy, but the copied **armature data**
  keeps its drivers on the original - 84 B-bone ease drivers on a generated
  ``human_toes`` rig - so the copy's bendy bones followed the original. ``create_character_copy()``'s
  own comment says "any armature modifier on the child is pointed to the new
  root", so this command follows the stated intent: it copies the descendants
  the service missed, then points every object reference on a copy - modifier,
  constraint, driver - that names an original in the family at that original's
  copy. ``copy_repairs`` lists each, and is empty on an MPFB that no longer needs
  it. FR 039 asked for the Rigify case to be reported rather than fixed; it is
  fixed, because it is the same rule as the modifiers - a copy driven by its
  original is not a copy - and one rule covering both is simpler than a fix for
  one and a report for the other. The three are filed in
  ``mpfb2/features/MCP_DISCOVERED_BUGS.md``.
- **The REMOVE step collects before it removes.** The operator removes
  modifiers from the list it is iterating, which FR 039 recorded as a defect
  candidate. The live check **refuted** it: Blender 5.1's collection iterator
  does not skip the neighbour of a removed modifier (nor of a removed vertex
  group, which ``bake_modifiers_remove_helpers()`` also does). Collecting first
  gives the same result and does not depend on that, so it stays, and the
  candidate is not filed.
- **The caller's selection and active object are put back**, in full
  (``selection.restored_all``). The operator leaves the copy active; a command
  working in the user's scene does not.
- **``material_type: "GAMEENGINE"`` is not the panel's** - it is what the panel
  lacks, and what MPFB's exporting documentation tells a user to arrange by hand.
  See :func:`_swap_to_game_engine`.

**What the panel does not say, and this answer does**:

- ``TargetService.bake_targets()`` bakes **every** shape key, not only the
  modeling ones the panel's label names. An applied expression and a face
  composed with ``set_face_units`` are frozen into the copy's mesh, and ARKit
  units loaded afterwards are relative to that face. ``face_baked_into_mesh``
  and ``expressions_baked_into_mesh`` say what was frozen, read through
  ``shared/expression_divergence.py`` so this agrees with the three tools that
  already report the face, and are empty for a neutral face.
- The copy **shares its materials** with the original: ``duplicate_blender_object()``
  copies the mesh, and a copied mesh points at the same material datablocks, so
  changing one changes both. ``materials_shared_with_original`` names them.

**The viseme packs have no MPFB probe**, unlike ``faceunits01``
(``FaceService.is_faceunits01_installed()``, which tests one target). So each is
probed the same way, with one target resolved through
``TargetService.target_full_path()``: the silence viseme, ``sil_00`` for
``visemes01`` (Microsoft) and ``viseme_sil`` for ``visemes02`` (Meta) - the
target MPFB's own ``configure_lip_sync()`` tests for. Resolving all 37 was
measured at 291 ms, too much to pay on every answer. As with ``faceunits01``,
the probe is not a verification: a requested set is resolved in full before
anything is copied, and a target that does not resolve is reported per set as
``could_not_load``. ``FaceService.load_targets()``'s docstring says it raises on
a missing target; ``bulk_load_targets()`` warns and skips, which is what
happens, and why the per-target resolution is this command's.

**How long it takes is MPFB's, and depends on the scene.** Baking masks while
keeping shape keys (``ExportService._apply_modifiers_keep_shapekeys()``)
duplicates the body once per shape key and applies the modifiers with an
operator each time, and every operator pays for the whole file. FR 039 measured
the worst case - no shape key bake, masks baked under all 89 loaded keys and the
modeling ones - at 7 s in a headless Blender holding one character, 27 s in a
windowed one holding a few hundred objects and 77 s once it held 1,900: under a third
of mpfb-mcp's 300 s socket timeout, but not by a margin a crowded file keeps. The
tool description says so; a faster bake would be MPFB's to write.

**A refusal is never a half-built copy.** The subject, the mode, the packs and
the proxy are all settled before anything is copied - including the one
combination MPFB's own sequence fails on part way, a body proxy whose modifiers
would be baked after ``interpolate`` gave it shape keys
(:func:`_proxy_modifiers_mpfb_cannot_bake`). A failure part way through
is not a refusal: what was built stays, and ``objects_created`` names it, as
``create_human_from_preset`` does.
"""

# The local bindings below are spelled with MPFB's own capitalisation.
# pylint: disable=invalid-name

__all__ = (
    "COLLECTION_NAME",
    "PARAMS",
    "SUMMARY",
    "create_export_copy",
)

import sys

import bpy

from ..log import get_logger
from ..shared import blender_data
from ..shared import expression_divergence
from ..shared import mpfb_surface
from ..shared import selection
from ..shared import subject_resolution
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.createexportcopy")

MODIFIER_STRATEGIES = ("KEEP", "REMOVE", "BAKE")
MATERIAL_TYPES = ("GAMEENGINE",)
SUFFIX_MAX_LENGTH = 32

# The operator's own collection name, created when missing and reused when not.
COLLECTION_NAME = "export copy"

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("bake_shapekeys", TYPE_BOOLEAN, default=True,
          description="Bake every shape key into the copy's mesh, the face included."),
    Param("mask_modifiers", TYPE_STRING, default="KEEP", choices=MODIFIER_STRATEGIES,
          description="What to do with mask modifiers on the copy's basemesh."),
    Param("subdiv_modifiers", TYPE_STRING, default="KEEP", choices=MODIFIER_STRATEGIES,
          description="What to do with subdivision modifiers on the copy's basemesh."),
    Param("delete_helpers", TYPE_BOOLEAN, default=True,
          description="Delete the helper geometry from the copy's basemesh."),
    Param("remove_basemesh", TYPE_BOOLEAN, default=False,
          description="Delete the copy's basemesh at the end. Needs a body proxy."),
    Param("load_microsoft_visemes", TYPE_BOOLEAN, default=False,
          description="Load the 22 Microsoft visemes (visemes01)."),
    Param("load_meta_visemes", TYPE_BOOLEAN, default=False,
          description="Load the 15 Meta visemes (visemes02)."),
    Param("load_arkit_face_units", TYPE_BOOLEAN, default=False,
          description="Load the 52 ARKit face units (faceunits01)."),
    Param("interpolate", TYPE_BOOLEAN, default=False,
          description="Interpolate the loaded visemes and face units onto the mesh assets."),
    Param("suffix", TYPE_STRING, default="_export_copy",
          description="Appended to the name of every object copied."),
    Param("in_export_collection", TYPE_BOOLEAN, default=True,
          description="Put the copy in the 'export copy' collection rather than the basemesh's."),
    Param("material_type", TYPE_STRING, default=None, nullable=True, choices=MATERIAL_TYPES,
          description="GAMEENGINE rebuilds every material on the copy as a GameEngine "
                      "material; null keeps the materials, shared with the original."),
)

SUMMARY = ("Make a processed copy of a character, MPFB's Export copy panel, without changing "
           "the original.")

# Each loadable set: the argument that asks for it, the key it is reported
# under, the pack it comes from, and the one target that probes the pack.
# ``vocabulary`` names FaceService's module-level list.
_SETS: tuple[dict, ...] = (
    dict(argument="load_microsoft_visemes", key="microsoft_visemes", pack="visemes01",
         vocabulary="MICROSOFT_VISEMES", probe="sil_00"),
    dict(argument="load_meta_visemes", key="meta_visemes", pack="visemes02",
         vocabulary="META_VISEMES", probe="viseme_sil"),
    dict(argument="load_arkit_face_units", key="arkit_face_units", pack="faceunits01",
         vocabulary="ARKIT_FACEUNITS", probe=None),
)

# A custom property put on every original in the family for the length of the
# copy, so that each copy can be told which object it was made from:
# ``Object.copy()`` copies custom properties. Removed from both again in a
# ``finally``.
_SOURCE_TAG = "mpfb_bridge_export_source"

# MPFB's mesh asset types whose material comes from their own MHCLO, which the
# GameEngine swap rebuilds. The body proxy is not one: it wears the skin.
_ASSET_TYPES = ("Clothes", "Eyes", "Eyebrows", "Eyelashes", "Hair", "Teeth", "Tongue")

_HELPER_GROUPS = ("HelperGeometry", "JointCubes")


# ----------------------------------------------------------------------------
# Reading the character and the packs
# ----------------------------------------------------------------------------


def _root_of(basemesh):
    """The object ``create_character_copy()`` copies from: the basemesh's parent, else itself."""
    return basemesh.parent if basemesh.parent is not None else basemesh


def _pack_probes(services):
    """``{pack: installed}`` for the three packs, each by its one probe target."""
    TargetService = services["TargetService"]
    probes: dict = {"faceunits01": bool(services["FaceService"].is_faceunits01_installed())}
    for entry in _SETS:
        if entry["probe"] is not None:
            probes[entry["pack"]] = TargetService.target_full_path(entry["probe"]) is not None
    return probes


def _resolve_sets(services, params):
    """Per requested set, which of its targets resolve and which do not.

    Done before anything is copied, as ``set_targets`` resolves its batch: a
    target that does not resolve is skipped by ``bulk_load_targets()`` with a
    warning nobody across the socket would see.
    """
    TargetService = services["TargetService"]
    resolved = {}
    for entry in _SETS:
        if not params[entry["argument"]]:
            continue
        names = list(mpfb_surface.required_module_level(services, "FaceService",
                                                        entry["vocabulary"]))
        missing = [name for name in names if TargetService.target_full_path(name) is None]
        resolved[entry["key"]] = dict(requested=names, could_not_load=missing)
    return resolved


def _shape_key_names(blender_object):
    keys = getattr(blender_object.data, "shape_keys", None) if blender_object.type == "MESH" else None
    if keys is None:
        return []
    return [str(block.name) for block in keys.key_blocks]


def _modifier_names(blender_object):
    return [str(modifier.name) for modifier in blender_object.modifiers]


def _face_that_will_be_baked(services, basemesh):
    """What ``bake_targets()`` is about to freeze: the stack rows and the live face units."""
    face_service = services["FaceService"]
    report: dict = expression_divergence.divergence(services, basemesh)
    rows = [row for row in report["applied_expressions"]
            if row["weight"] is not None and float(row["weight"]) != 0.0]
    live = face_service.read_current_expression(basemesh)
    from_stack = report["aggregate"]
    units = [dict(face_unit=name, value=round(float(value), 6),
                  from_stack=from_stack.get(name, 0.0))
             for name, value in sorted(live.items()) if abs(float(value)) > expression_divergence.TOLERANCE]
    return rows, units, report["unexplained_face_units"]


# ----------------------------------------------------------------------------
# Making the copy, and repairing it
# ----------------------------------------------------------------------------


def _collection_for(basemesh, in_export_collection):
    """The operator's choice of collection, reproduced."""
    if not in_export_collection:
        return basemesh.users_collection[0]
    collection = bpy.data.collections.get(COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _object_pointer_names(struct):
    """The writable properties of ``struct`` that point at an ``Object``."""
    for prop in struct.bl_rna.properties:
        if prop.type == "POINTER" and not prop.is_readonly \
                and getattr(prop.fixed_type, "identifier", None) == "Object":
            yield prop.identifier


def _retarget_struct(struct, by_source, record):
    """Point every object reference on ``struct`` at the copy of what it names."""
    for attribute in _object_pointer_names(struct):
        target = getattr(struct, attribute, None)
        if target is None or target.name not in by_source:
            continue
        replacement = by_source[target.name]
        if replacement == target:
            continue
        setattr(struct, attribute, replacement)
        record(attribute, target.name, replacement.name)


def _retarget_drivers(id_block, by_source, record):
    animation = getattr(id_block, "animation_data", None)
    if animation is None:
        return
    for fcurve in animation.drivers:
        for variable in fcurve.driver.variables:
            for target in variable.targets:
                original = target.id
                if original is None or not isinstance(original, bpy.types.Object) \
                        or original.name not in by_source:
                    continue
                replacement = by_source[original.name]
                if replacement == original:
                    continue
                target.id = replacement
                record(fcurve.data_path, original.name, replacement.name)


def _repair_references(copy, by_source):
    """Every reference on ``copy`` to an original in the family, pointed at its copy."""
    retargeted = []

    def recorder(kind, owner):
        def record(attribute, previous, new):
            retargeted.append(dict(object_name=copy.name, kind=kind, name=owner,
                                   attribute=attribute, previous_object_name=previous,
                                   new_object_name=new))
        return record

    for modifier in copy.modifiers:
        _retarget_struct(modifier, by_source, recorder("modifier", modifier.name))
    for constraint in copy.constraints:
        _retarget_struct(constraint, by_source, recorder("constraint", constraint.name))
    if copy.type == "ARMATURE" and copy.pose is not None:
        for pose_bone in copy.pose.bones:
            for constraint in pose_bone.constraints:
                _retarget_struct(constraint, by_source, recorder(
                    "bone_constraint", pose_bone.name + ": " + constraint.name))
    _retarget_drivers(copy, by_source, recorder("driver", copy.name))
    if copy.data is not None:
        _retarget_drivers(copy.data, by_source, recorder("driver", copy.data.name))
        keys = getattr(copy.data, "shape_keys", None)
        if keys is not None:
            _retarget_drivers(keys, by_source, recorder("driver", keys.name))
    return retargeted


def _make_copy(services, basemesh, family, suffix, collection):
    """``create_character_copy()``, then the two repairs. Returns ``(by_source, repairs)``.

    ``by_source`` maps each original's name to its copy, for every object in
    the family; the tag is how a copy is told from its source, whatever name
    Blender gave it.
    """
    ObjectService = services["ObjectService"]
    for original in family:
        original[_SOURCE_TAG] = original.name
    before = blender_data.object_names()
    try:
        services["ExportService"].create_character_copy(
            basemesh, name_suffix=suffix, place_in_collection=collection)
    finally:
        for original in family:
            if _SOURCE_TAG in original.keys():
                del original[_SOURCE_TAG]

    by_source = {}
    for blender_object in bpy.data.objects:
        if blender_object.name in before:
            continue
        source = blender_object.get(_SOURCE_TAG)
        if source is not None:
            by_source[str(source)] = blender_object
            del blender_object[_SOURCE_TAG]

    objects_copied = []
    for original in family:
        if original.name in by_source or original.parent is None:
            continue
        parent_copy = by_source.get(original.parent.name)
        if parent_copy is None:
            continue
        copy = ObjectService.duplicate_blender_object(original, collection=collection,
                                                      parent=parent_copy)
        copy.name = original.name + suffix
        by_source[original.name] = copy
        objects_copied.append(dict(name=copy.name, source_name=original.name))

    retargeted = []
    for original in family:
        copy = by_source.get(original.name)
        if copy is not None:
            retargeted.extend(_repair_references(copy, by_source))
    return by_source, dict(objects_copied=objects_copied, references_retargeted=retargeted)


def _shared_materials(by_source):
    """Per copied mesh, the material datablocks it shares with its original."""
    shared = []
    for source_name, copy in by_source.items():
        if copy.type != "MESH":
            continue
        source = bpy.data.objects.get(source_name)
        if source is None:
            continue
        theirs = set(material.name for material in getattr(source.data, "materials", [])
                     if material is not None)
        common = [material.name for material in copy.data.materials
                  if material is not None and material.name in theirs]
        if common:
            shared.append(dict(object_name=copy.name, materials=common))
    return shared


# ----------------------------------------------------------------------------
# The GameEngine swap
# ----------------------------------------------------------------------------


def _detach_materials(blender_object):
    """Pop every material off one mesh without touching the datablocks.

    Popping drops this mesh's use and nothing else, so a material the original
    still uses survives with its name and its node groups. This is what makes
    the swap safe: ``set_character_skin()`` would otherwise rename every
    material it finds ``.unused`` and clear its node tree, groups and all - and
    the material it found would be the original's.
    """
    materials = blender_object.data.materials
    while len(materials) > 0:
        materials.pop()


def _swap_skin(services, basemesh_copy, proxy_copy):
    """The skin, through ``set_character_skin(skin_type="GAMEENGINE")``. ``(done, reason, mhmat)``."""
    human_properties = mpfb_surface.human_object_properties(services)
    fragment = mpfb_surface.property_value(human_properties, "material_source", basemesh_copy)
    if fragment is None:
        return (False, "no_skin_recorded", None)
    mhmat = mpfb_surface.as_path(
        services["AssetService"].find_asset_absolute_path(fragment, "skins"))
    if mhmat is None:
        return (False, "skin_mhmat_not_found", None)
    _detach_materials(basemesh_copy)
    if proxy_copy is not None:
        _detach_materials(proxy_copy)
    services["HumanService"].set_character_skin(
        mhmat, basemesh_copy, bodyproxy=proxy_copy, skin_type="GAMEENGINE",
        material_instances=False)
    return (True, None, mhmat)


def _game_engine_wrapper(root_name):
    """MPFB's ``NodeWrapperGameEngine``, read out of ``sys.modules``, or None.

    It is imported inside ``HumanService``'s functions rather than at module
    level, so no service module carries it. Its package,
    ``entities.nodemodel.v2.materials``, imports it at registration - FR 039
    found it loaded in a fresh headless Blender and a windowed one - so it is
    read the way a UI module is, never imported
    ([a UI module with no service behind it](../../../specifications/architecture.md#a-ui-module-with-no-service-behind-it)).
    A miss leaves the mesh assets as they were, each reported as not swapped.
    """
    module = sys.modules.get(root_name + ".entities.nodemodel.v2.materials.nodewrappergameengine")
    return None if module is None else getattr(module, "NodeWrapperGameEngine", None)


def _asset_mhmat(services, copy, object_type, Mhclo):
    """The MHMAT a mesh asset's material comes from, the way MPFB picks it when equipping."""
    general_properties = mpfb_surface.general_object_properties(services)
    alternative = mpfb_surface.property_value(general_properties, "alternative_material", copy)
    if alternative is not None:
        path = mpfb_surface.as_path(services["AssetService"].find_asset_absolute_path(
            alternative, str(object_type).lower()))
        if path is not None:
            return path
    mhclo_path = services["ClothesService"].find_clothes_absolute_path(copy)
    if not mhclo_path:
        return None
    mhclo = Mhclo()
    mhclo.load(mhclo_path)
    return mpfb_surface.as_path(mhclo.material)


def _swap_asset(services, copy, object_type, entities):
    """One mesh asset, as ``add_mhclo_asset(material_type="GAMEENGINE")`` builds it. ``(done, reason, mhmat)``.

    ``entities`` is ``(Mhclo, MhMaterial, NodeWrapperGameEngine)``, any of them
    ``None`` where MPFB no longer publishes it.
    """
    Mhclo, MhMaterial, wrapper = entities
    if wrapper is None or Mhclo is None or MhMaterial is None:
        return (False, "game_engine_material_unavailable", None)
    mhmat_path = _asset_mhmat(services, copy, object_type, Mhclo)
    if mhmat_path is None:
        return (False, "mhmat_not_found", None)
    MaterialService = services["MaterialService"]
    _detach_materials(copy)
    material = MaterialService.create_empty_material(copy.name, copy)
    mhmat = MhMaterial()
    mhmat.populate_from_mhmat(mhmat_path)
    wrapper.create_instance(material.node_tree, mhmat=mhmat)
    material.diffuse_color = MaterialService.get_diffuse_colors().get(
        object_type, (0.8, 0.8, 0.8, 1.0))
    return (True, None, mhmat_path)


def _swap_to_game_engine(services, root_name, basemesh_copy, by_source):
    """Every mesh on the copy, its own GameEngine material. ``(swapped, not_swapped)``.

    The skin goes through ``HumanService.set_character_skin()``, which is how
    MPFB's settings panel makes a GameEngine skin. The mesh assets have no such
    service, so each is built the way ``HumanService.add_mhclo_asset()`` builds
    one when equipped with ``material_type="GAMEENGINE"`` - an alternative
    material recorded on the object first, else the MHCLO's own, into an empty
    material under the object's name, with MPFB's viewport colour per type.

    Every mesh's materials are **popped first** (:func:`_detach_materials`), so
    the original's are not touched. A mesh whose MHMAT cannot be found is left
    as it was and listed in ``not_swapped`` with a reason; the rest go on.
    """
    ObjectService = services["ObjectService"]
    MaterialService = services["MaterialService"]
    Mhclo = mpfb_surface.module_level(services, "HumanService", "Mhclo", fallback=None)
    MhMaterial = mpfb_surface.module_level(services, "HumanService", "MhMaterial", fallback=None)
    wrapper = _game_engine_wrapper(root_name)

    def identified(blender_object):
        return MaterialService.identify_material(MaterialService.get_material(blender_object, 0))

    swapped, not_swapped = [], []
    proxy_copy = None
    for copy in by_source.values():
        if copy.type == "MESH" and ObjectService.get_object_type(copy) == "Proxymeshes":
            proxy_copy = copy

    before = identified(basemesh_copy)
    done, reason, mhmat = _swap_skin(services, basemesh_copy, proxy_copy)
    for target in (basemesh_copy, proxy_copy):
        if target is None:
            continue
        if done:
            swapped.append(dict(object_name=target.name, material_identified_as_before=before,
                                material_identified_as=identified(target), mhmat_path=mhmat))
        else:
            not_swapped.append(dict(object_name=target.name, reason=reason))

    for copy in by_source.values():
        object_type = ObjectService.get_object_type(copy) if copy.type == "MESH" else None
        if object_type not in _ASSET_TYPES:
            continue
        before = identified(copy)
        done, reason, mhmat = _swap_asset(services, copy, object_type,
                                          (Mhclo, MhMaterial, wrapper))
        if done:
            swapped.append(dict(object_name=copy.name, material_identified_as_before=before,
                                material_identified_as=identified(copy), mhmat_path=mhmat))
        else:
            not_swapped.append(dict(object_name=copy.name, reason=reason))
    return swapped, not_swapped


# ----------------------------------------------------------------------------
# The answer
# ----------------------------------------------------------------------------


def _options(params):
    return {param.name: params[param.name] for param in PARAMS if param.name != "name"}


def _blocked(params, request, reason, message, **extra):
    answer = dict(
        found=request["basemesh"] is not None,
        ready=False,
        created=False,
        blocked_by=reason,
        subject_name=None if request["subject"] is None else request["subject"].name,
        subject_resolved_by=request["subject_resolved_by"],
        basemesh_name=None if request["basemesh"] is None else request["basemesh"].name,
        options_used=_options(params),
        message=message,
    )
    answer.update(request["probes"])
    answer.update(extra)
    return with_performed(answer, False)


def _refusal(params, request):
    """The first precondition that fails, as ``(blocked_by, sentence, extra)``, or None."""
    basemesh = request["basemesh"]
    if bpy.context.mode != "OBJECT" or basemesh.mode != "OBJECT":
        return ("not_object_mode",
                "Blender is in {:s} mode, and making an export copy applies modifiers and "
                "deletes geometry through operators that need object mode, so no copy was "
                "made. Switch to object mode and call again.".format(str(bpy.context.mode)),
                {})
    for entry in _SETS:
        if params[entry["argument"]] and not request["probes"][entry["pack"] + "_installed"]:
            return (entry["pack"] + "_not_installed",
                    "{:s} was asked for, and the {:s} asset pack it comes from is not installed, "
                    "so no copy was made. Install the pack, or call again without "
                    "{:s}.".format(entry["argument"], entry["pack"], entry["argument"]),
                    {})
    if params["remove_basemesh"] and request["bodyproxy"] is None:
        return ("no_bodyproxy",
                "remove_basemesh was asked for and '{:s}' has no body proxy, so the copy would "
                "have no body; no copy was made. Equip a proxy with mpfb_add_asset "
                "(object_type 'Proxymeshes') first, or keep the basemesh.".format(basemesh.name),
                {})
    doomed = _proxy_modifiers_mpfb_cannot_bake(params, request["bodyproxy"])
    if doomed:
        return ("proxy_cannot_be_baked",
                "Interpolating the loaded shape keys gives the body proxy shape keys of its own, "
                "and MPFB's bake then applies the proxy's {:s} with an operator Blender refuses "
                "on a mesh with shape keys - MPFB's own Export copy panel fails the same way. No "
                "copy was made. Call again with interpolate false, or without baking {:s} "
                "(mask_modifiers / subdiv_modifiers 'KEEP').".format(
                    ", ".join("'" + name + "'" for name in doomed),
                    "those modifiers" if len(doomed) > 1 else "that modifier"),
                dict(proxy_modifiers_blocking=doomed))
    if len(params["suffix"]) > SUFFIX_MAX_LENGTH:
        return ("invalid_suffix",
                "suffix must be at most {:d} characters; Blender truncates object names at 63, "
                "so a longer one would cut into the names it is appended to. No copy was "
                "made.".format(SUFFIX_MAX_LENGTH),
                {})
    return None


def _proxy_modifiers_mpfb_cannot_bake(params, bodyproxy):
    """The proxy's modifiers MPFB's bake would apply under shape keys, or ``[]``.

    ``bake_modifiers_remove_helpers()`` bakes the basemesh's modifiers through
    ``_apply_modifiers_keep_shapekeys()`` when it has shape keys, and the
    proxy's with a bare ``bpy.ops.object.modifier_apply()``, which Blender
    refuses on a mesh with shape keys. A proxy has none of its own, until
    ``interpolate`` copies the loaded visemes and face units onto it - which the
    operator does first. FR 039's live check met it as a ``RuntimeError`` half way
    through a copy; it is filed in ``mpfb2/features/MCP_DISCOVERED_BUGS.md``. The
    selection mirrors the service's own: masks when baking masks, subdivision
    at a render level above zero when baking subdivision.
    """
    if bodyproxy is None or not params["interpolate"] \
            or not any(params[entry["argument"]] for entry in _SETS):
        return []
    doomed = []
    for modifier in bodyproxy.modifiers:
        if modifier.type == "MASK" and params["mask_modifiers"] == "BAKE":
            doomed.append(str(modifier.name))
        elif modifier.type == "SUBSURF" and params["subdiv_modifiers"] == "BAKE" \
                and modifier.render_levels > 0:
            doomed.append(str(modifier.name))
    return doomed


def _message(params, answer):
    parts = ["Made an export copy of '{:s}': {:d} object(s), root '{:s}', in collection "
             "'{:s}'. The original is unchanged; the copy is a character of its own, so "
             "mpfb_list_objects now lists both.".format(
                 answer["basemesh_name"], len(answer["copied_objects"]),
                 answer["copy_root_name"], answer["collection_name"])]
    repairs = answer["copy_repairs"]
    if repairs["objects_copied"] or repairs["references_retargeted"]:
        parts.append(" MPFB's copy was repaired: {:d} object(s) it left out were copied and "
                     "{:d} reference(s) to the original were pointed at the copy; see "
                     "copy_repairs.".format(len(repairs["objects_copied"]),
                                            len(repairs["references_retargeted"])))
    if answer["face_baked_into_mesh"]:
        parts.append(" The face was not neutral and was baked into the mesh with the modeling "
                     "shape keys ({:d} face unit(s), see face_baked_into_mesh).".format(
                         len(answer["face_baked_into_mesh"])))
        if params["load_arkit_face_units"]:
            parts.append(" The ARKit face units were loaded after the bake, so they move the face "
                         "from that expression rather than from a neutral one.")
        if answer["expressions_baked_into_mesh"]:
            parts.append(" The copy still carries the expression stack, so a later "
                         "mpfb_apply_expressions on it would apply the face a second time.")
    for key, loaded in answer["shape_keys_loaded"].items():
        if loaded["could_not_load"]:
            parts.append(" {:d} of the {:s} could not be loaded; see shape_keys_loaded.".format(
                len(loaded["could_not_load"]), key.replace("_", " ")))
    if answer["materials_shared_with_original"]:
        parts.append(" {:d} copied mesh(es) share their materials with the original, so changing "
                     "one changes both; material_type 'GAMEENGINE' gives the copy its "
                     "own.".format(len(answer["materials_shared_with_original"])))
    if answer["materials_not_swapped"]:
        parts.append(" {:d} mesh(es) kept their material; see materials_not_swapped.".format(
            len(answer["materials_not_swapped"])))
    return "".join(parts)


def create_export_copy(params, resolution):  # pylint: disable=too-many-locals,too-many-statements
    """Copy one character, process the copy, and say what each step did."""
    services = resolution.services
    ObjectService = services["ObjectService"]
    ExportService = services["ExportService"]
    TargetService = services["TargetService"]
    FaceService = services["FaceService"]

    request: dict = dict(probes={pack + "_installed": installed
                           for pack, installed in _pack_probes(services).items()})
    (request["basemesh"], request["subject"], request["subject_resolved_by"],
     message) = subject_resolution.resolve_basemesh(
         services, params["name"], not_done="no copy was made",
         not_a_character="there is no character to copy")
    if request["basemesh"] is None:
        return _blocked(params, request, "subject_not_found", message)
    basemesh = request["basemesh"]
    request["bodyproxy"] = ObjectService.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Proxymeshes")

    refusal = _refusal(params, request)
    if refusal is not None:
        reason, text, extra = refusal
        return _blocked(params, request, reason, text, **extra)

    sets = _resolve_sets(services, params)
    if params["bake_shapekeys"]:
        expressions_baked, face_baked, _unexplained = _face_that_will_be_baked(services, basemesh)
    else:
        expressions_baked, face_baked = None, None

    family = blender_data.with_descendants(_root_of(basemesh))
    before = blender_data.object_names()
    steps: dict = dict(shape_keys_baked=None, shape_keys_loaded={}, interpolated_onto=[],
                 modifiers_baked={}, modifiers_removed={}, helper_vertices_left=None,
                 basemesh_vertices_before=None, basemesh_vertices_after=None,
                 basemesh_removed=False)
    swapped, not_swapped = [], []
    collection = _collection_for(basemesh, params["in_export_collection"])

    with selection.restored_all():
        try:
            by_source, repairs = _make_copy(services, basemesh, family, params["suffix"],
                                            collection)
            new_basemesh = by_source[basemesh.name]
            new_root = by_source[family[0].name]
            proxy_copy = None if request["bodyproxy"] is None \
                else by_source.get(request["bodyproxy"].name)
            meshes = [copy for copy in by_source.values() if copy.type == "MESH"]
            copied = [dict(name=copy.name, source_name=source,
                           object_type=ObjectService.get_object_type(copy) or None)
                      for source, copy in by_source.items()]

            if params["material_type"] == "GAMEENGINE":
                swapped, not_swapped = _swap_to_game_engine(
                    services, resolution.module.__name__, new_basemesh, by_source)
            shared = _shared_materials(by_source)

            if params["bake_shapekeys"]:
                steps["shape_keys_baked"] = [name for name in _shape_key_names(new_basemesh)
                                             if name.lower() != "basis"]
                TargetService.bake_targets(new_basemesh)

            if sets:
                FaceService.load_targets(
                    new_basemesh,
                    load_microsoft_visemes=params["load_microsoft_visemes"],
                    load_meta_visemes=params["load_meta_visemes"],
                    load_arkit_faceunits=params["load_arkit_face_units"])
                present = set(_shape_key_names(new_basemesh))
                for key, entry in sets.items():
                    loaded = [name for name in entry["requested"] if name in present]
                    steps["shape_keys_loaded"][key] = dict(
                        loaded_count=len(loaded),
                        could_not_load=[name for name in entry["requested"]
                                        if name not in present])

            if params["interpolate"]:
                keys_before = {copy.name: set(_shape_key_names(copy)) for copy in meshes}
                FaceService.interpolate_targets(new_basemesh)
                for copy in meshes:
                    if copy == new_basemesh:
                        continue
                    added = [name for name in _shape_key_names(copy)
                             if name not in keys_before[copy.name] and name.lower() != "basis"]
                    if added:
                        steps["interpolated_onto"].append(
                            dict(object_name=copy.name, shape_key_count=len(added)))

            steps["basemesh_vertices_before"] = len(new_basemesh.data.vertices)
            modifiers_before = {copy.name: _modifier_names(copy) for copy in meshes}
            ExportService.bake_modifiers_remove_helpers(
                new_basemesh,
                bake_masks=params["mask_modifiers"] == "BAKE",
                bake_subdiv=params["subdiv_modifiers"] == "BAKE",
                remove_helpers=params["delete_helpers"],
                also_proxy=True)
            for copy in meshes:
                gone = [name for name in modifiers_before[copy.name]
                        if name not in _modifier_names(copy)]
                if gone:
                    steps["modifiers_baked"][copy.name] = gone

            for strategy_key, modifier_type in (("mask_modifiers", "MASK"),
                                                ("subdiv_modifiers", "SUBSURF")):
                if params[strategy_key] != "REMOVE":
                    continue
                # Collected first, then removed; see the module docstring.
                doomed = [modifier for modifier in new_basemesh.modifiers
                          if modifier.type == modifier_type]
                for modifier in doomed:
                    steps["modifiers_removed"].setdefault(new_basemesh.name, []).append(
                        str(modifier.name))
                    new_basemesh.modifiers.remove(modifier)

            steps["basemesh_vertices_after"] = len(new_basemesh.data.vertices)
            steps["helper_vertices_left"] = blender_data.vertices_in_groups(
                new_basemesh, _HELPER_GROUPS)
            new_basemesh_name = new_basemesh.name
            # With no rig the basemesh is the root, and the proxy, parented to
            # it, becomes the root once it is gone.
            root_name = new_root.name
            if params["remove_basemesh"]:
                if new_root == new_basemesh and proxy_copy is not None:
                    root_name = proxy_copy.name
                ObjectService.delete_object(new_basemesh)
                steps["basemesh_removed"] = True
        except Exception as error:  # pylint: disable=broad-except
            _LOG.error("create_export_copy failed: %s", error)
            created = sorted(blender_data.object_names() - before)
            return _blocked(
                params, request, "copy_failed",
                "MPFB raised while making the export copy: {:s}: {!s}. The original is "
                "untouched, but what was copied before the failure is still in the scene: "
                "objects_created names it, and there is no undo for it across this "
                "socket.".format(type(error).__name__, error),
                found=True, objects_created=created)

    answer = dict(
        found=True,
        ready=True,
        created=True,
        blocked_by=None,
        subject_name=None if request["subject"] is None else request["subject"].name,
        subject_resolved_by=request["subject_resolved_by"],
        basemesh_name=basemesh.name,
        bodyproxy_name=None if request["bodyproxy"] is None else request["bodyproxy"].name,
        copy_root_name=root_name,
        copy_basemesh_name=None if steps["basemesh_removed"] else new_basemesh_name,
        copy_bodyproxy_name=None if proxy_copy is None else proxy_copy.name,
        copied_objects=[entry for entry in copied
                        if not (steps["basemesh_removed"] and entry["source_name"] == basemesh.name)],
        collection_name=collection.name,
        options_used=_options(params),
        copy_repairs=repairs,
        face_baked_into_mesh=face_baked,
        expressions_baked_into_mesh=expressions_baked,
        materials_shared_with_original=shared,
        materials_swapped=swapped,
        materials_not_swapped=not_swapped,
    )
    answer.update(steps)
    answer.update(request["probes"])
    answer["message"] = _message(params, answer)
    return with_performed(answer, True)
