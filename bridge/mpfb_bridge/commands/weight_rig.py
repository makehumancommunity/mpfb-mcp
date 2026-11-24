"""
``weight_rig``: vertex weights for an authored rig, three ways, and a fill for what they miss.

Nothing in MPFB weights a new rig ([FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)).
MakeRig's auto transfer copies a group only between bones whose ends both coincide within a
millimetre, and MakeWeight's symmetrize does nothing at all
(``mpfb2/efforts/bugs/local/symmetrize-weights-not-implemented.md``). So this has three
methods, each writing the vertex groups of deforming bones and nothing else:

- **``automatic``** is Blender's heat weighting, ``parent_set(type='ARMATURE_AUTO')``.
- **``transfer``** takes a catalogue rig's weights, through a match that understands merged
  chains, which MakeRig's operator does not.
- **``mirror``** copies one side onto the other through MPFB's own ``hm08.mirror``.

**Heat weighting runs on a temporary copy, for two reasons this effort measured.**

- **Blender reads the wrong body.** Its skinning (``armature_skinning.cc``) reads the mesh's
  original vertex positions, ``mesh->vert_positions()``, which on a basemesh is the Basis
  shape - the neutral body - while MPFB fits the bones to the body *with* its shape keys
  evaluated. Even the default character's mix is 6 mm from its Basis at vertex 0. The copy's
  vertices are where MPFB's position info puts them, the mix the bones were fitted to.
- **The joint cubes break the solve.** A bone end MPFB fits sits exactly at a joint cube's
  centre, and with the cubes in the mesh Blender's heat solve fails for **every** bone: on the
  default body, 0 of 14,380 body and cube vertices weighted, against 13,380 of 13,380 with the
  cubes left out. On the Basis positions the bones are a few millimetres off the cubes and the
  pass happened to work, which is why a run on the basemesh itself looked fine. So the copy
  leaves the cubes out, and the fill gives them their nearest body vertex's weights.

The copy has no shape keys, no modifiers and no groups of the character's; the heat pass
parents it, adds its modifier and writes its groups, and none of that touches the character.
The groups come back by vertex index and the copy is removed, which also makes the context
handling the request feared (reparenting, the modifier stack, the selection) a matter of
deleting one object. Weighting the neutral mesh on purpose, and choosing between a skin-only
and a whole-mesh pass, is
[FR 061](../../../feature-requests/061-rig-weights-that-hold-up/README.md)'s.

**Transfer.** The source rig is fitted to this body in memory
([`shared/rig_definition.py`](../shared/rig_definition.py)), and its weights file is the one
``mpfb_add_rig`` would load, through ``shared/rig_lookup.py``: ``default_no_toes`` takes
``default``'s. Weights are per base-mesh vertex index, so nothing is interpolated. Each
deforming bone of the authored rig is matched:

- ``exact``: both ends within 1 mm of one source bone's, as MakeRig's operator matches;
- ``chain``: its head on a source bone's head and its tail on a descendant's tail, the chain's
  groups summed - ``upperarm.L`` taking ``upperarm01.L`` and ``upperarm02.L``;
- ``none``, with the nearest miss and its distances.

A source bone no target bone covers then gives its group to the target bone of its nearest
matched ancestor (``ancestor``), which keeps each vertex's total: the fingers into ``hand.L``.
Each contribution says which rule brought it. A weights group naming no source bone is mapped
as ``RigService.apply_weights()`` maps one, so ``default``'s toe groups reach
``default_no_toes``' common toe.

**The fill.** Heat weighting leaves parts of the disconnected interior shells - eyes, teeth,
tongue, the skirt and tights helpers - unweighted, and the joint cubes are not in its pass, so
after ``automatic`` or ``transfer`` every vertex with no deform weight takes the weights of the
nearest weighted **body** vertex, found in a KD-tree over the vertices
in no ``helper-*`` and no ``joint-*`` group, at the fitted positions. The counts before and
after are split into ``body``, ``helper`` and ``joint_cube``; a body vertex unweighted before
the fill is the one that means the pass went wrong.

**What is changed, and what is owed for it.** Only the groups of the deforming bones the call
weights (all of them, or ``bone_names``); each is replaced whole. A group that had weights
before the call is listed in ``groups_replaced``, per
[a tool that destroys state it did not create](../../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list).
``exclude_bones`` is set non-deforming and stays so. The rig must be at rest, and must be one
``create_rig`` built or one identified as ``unknown``: a shipped rig has its own weights.

**The root.** A bone from ``joint-ground`` takes the thighs under heat weighting, and once a
rig has been through the library its non-deforming flag is gone (``store_rig`` says so). So
every deforming bone whose head is on ``joint-ground`` is named on every answer.
"""

__all__ = (
    "DIRECTIONS",
    "METHODS",
    "PARAMS",
    "SUMMARY",
    "weight_rig",
)

import json
import os
import re

import bpy
from mathutils import Vector  # pylint: disable=import-error
from mathutils.kdtree import KDTree  # pylint: disable=import-error

from ..log import get_logger
from ..shared import mpfb_surface
from ..shared import pose_reading
from ..shared import rig_definition
from ..shared import selection
from ..shared import subject_resolution
from ..shared import view_layer
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.weightrig")

METHODS = ("automatic", "transfer", "mirror")
DIRECTIONS = ("left_to_right", "right_to_left")

# A weight at or below this is no weight, as MPFB's get_weights() drops below 0.0001.
_NO_WEIGHT = 0.0001

# The side suffixes a mirror pairs bones by, left first.
_SIDES = ((".L", ".R"), ("_l", "_r"))

_HELPER_PREFIX = "helper-"
_JOINT_PREFIX = "joint-"
_GROUND = "joint-ground"

# How many names a list in a refusal carries before it is cut.
_MAX_NAMED = 40

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("method", TYPE_STRING, required=True, choices=METHODS,
          description="automatic (heat weighting), transfer (from_rig's weights) or mirror "
                      "(one side onto the other)."),
    Param("exclude_bones", TYPE_ARRAY, default=None, nullable=True,
          description="automatic only: bones to leave out of the pass, set non-deforming."),
    Param("from_rig", TYPE_STRING, default=None, nullable=True,
          description="transfer only: the catalogue rig whose weights to take."),
    Param("direction", TYPE_STRING, default=None, nullable=True, choices=DIRECTIONS,
          description="mirror only: left_to_right or right_to_left."),
    Param("fill_unweighted", TYPE_BOOLEAN, default=True,
          description="After automatic or transfer, give every unweighted vertex the weights "
                      "of the nearest weighted body vertex."),
    Param("bone_names", TYPE_ARRAY, default=None, nullable=True,
          description="Only weight these deforming bones. Omit for all of them."),
)

SUMMARY = ("Weight an authored rig: heat weighting, a transfer from a catalogue rig through merged "
           "chains, or a mirror, then fill what the pass missed.")


# ----------------------------------------------------------------------
# Reading and writing groups


def _vertex_classes(basemesh):
    """Per vertex, ``"joint_cube"``, ``"helper"`` or ``"body"``, from MPFB's own groups."""
    joint = set()
    helper = set()
    for group in basemesh.vertex_groups:
        if group.name.startswith(_JOINT_PREFIX):
            joint.add(group.index)
        elif group.name.startswith(_HELPER_PREFIX):
            helper.add(group.index)
    classes = []
    for vertex in basemesh.data.vertices:
        indices = {element.group for element in vertex.groups}
        if indices & joint:
            classes.append("joint_cube")
        elif indices & helper:
            classes.append("helper")
        else:
            classes.append("body")
    return classes


def _read_groups(mesh_object, names):
    """``{group name: {vertex index: weight}}`` for the named groups that exist."""
    by_index = {group.index: group.name for group in mesh_object.vertex_groups
                if group.name in names}
    weights = {name: {} for name in by_index.values()}
    for vertex in mesh_object.data.vertices:
        for element in vertex.groups:
            name = by_index.get(element.group)
            if name is not None and element.weight > _NO_WEIGHT:
                weights[name][vertex.index] = float(element.weight)
    return weights


def _write_groups(basemesh, weights):
    """Replace each named group's content with ``weights[name]``, creating it if need be."""
    every = list(range(len(basemesh.data.vertices)))
    for name, entries in weights.items():
        group = basemesh.vertex_groups.get(name)
        if group is None:
            group = basemesh.vertex_groups.new(name=name)
        group.remove(every)
        for index, weight in entries.items():
            group.add([index], min(1.0, weight), "REPLACE")


def _unweighted(classes, weights, vertex_count):
    """How many vertices carry no deform weight, by class, and which they are."""
    weighted = set()
    for entries in weights.values():
        weighted.update(entries)
    missing = [index for index in range(vertex_count) if index not in weighted]
    counts = {"body": 0, "helper": 0, "joint_cube": 0}
    for index in missing:
        counts[classes[index]] += 1
    return (counts, missing)


def _fill(classes, weights, positions, missing, written):
    """Give each vertex in ``missing`` the ``written`` groups of its nearest weighted body vertex."""
    weighted = set()
    for entries in weights.values():
        weighted.update(entries)
    sources = [index for index in weighted if classes[index] == "body"]
    if not sources or not missing:
        return 0
    tree = KDTree(len(sources))
    for slot, index in enumerate(sources):
        tree.insert(positions[index], slot)
    tree.balance()
    by_vertex = {}
    for name in written:
        for index, weight in weights.get(name, {}).items():
            by_vertex.setdefault(index, []).append((name, weight))
    filled = 0
    for index in missing:
        _co, slot, _distance = tree.find(positions[index])
        source = sources[slot]
        for name, weight in by_vertex.get(source, ()):
            weights[name][index] = weight
        if by_vertex.get(source):
            filled += 1
    return filled


# ----------------------------------------------------------------------
# automatic


def _heat_copy(basemesh, armature, positions, classes):
    """Heat-weight a copy at the fitted positions, without the joint cubes; ``{bone: {vertex: weight}}``.

    The copy is a new mesh built from the basemesh's faces, its vertices at ``positions`` and
    renumbered, so it shares no group data with the character; the weights come back under
    the basemesh's own vertex indices.
    """
    kept = [index for index in range(len(positions)) if classes[index] != "joint_cube"]
    renumbered = {index: slot for slot, index in enumerate(kept)}
    faces = [tuple(renumbered[index] for index in polygon.vertices)
             for polygon in basemesh.data.polygons
             if all(index in renumbered for index in polygon.vertices)]
    mesh = bpy.data.meshes.new(basemesh.name + ".mpfb_bridge_heat")
    mesh.from_pydata([tuple(positions[index]) for index in kept], [], faces)
    mesh.update()
    copy = bpy.data.objects.new(mesh.name, mesh)
    try:
        bpy.context.scene.collection.objects.link(copy)
        copy.matrix_world = basemesh.matrix_world.copy()
        bpy.context.view_layer.update()
        deforming = [bone.name for bone in armature.data.bones if bone.use_deform]
        with selection.restored_all():
            for other in bpy.context.view_layer.objects:
                other.select_set(False)
            copy.select_set(True)
            armature.select_set(True)
            bpy.context.view_layer.objects.active = armature
            with bpy.context.temp_override(active_object=armature, object=armature,
                                           selected_objects=[copy, armature],
                                           selected_editable_objects=[copy, armature]):
                bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        weights = _read_groups(copy, set(deforming))
        return {name: {kept[slot]: weight for slot, weight in entries.items()}
                for name, entries in weights.items()}
    finally:
        bpy.data.objects.remove(copy, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


# ----------------------------------------------------------------------
# transfer


def _source_bone_for_group(group, source_names):
    """The source bone a weights group belongs to, as ``RigService.apply_weights()`` maps it."""
    if group in source_names:
        return group
    toggled = group[4:] if group.startswith("DEF-") else "DEF-" + group
    if toggled in source_names:
        return toggled
    match = re.fullmatch(r"^(?:DEF-)?toe\d-\d.([LR])$", group)
    if match:
        side = match.group(1)
        for candidate in ("toe.{:s}".format(side), "DEF-toe.{:s}".format(side),
                          "toe1-1.{:s}".format(side)):
            if candidate in source_names:
                return candidate
    return None


def _descendants_path(parents, ancestor, descendant):
    """The bones from ``ancestor`` down to ``descendant``, or None if it is not below it."""
    path = [descendant]
    current = descendant
    while current != ancestor:
        current = parents.get(current) or ""
        if not current:
            return None
        path.append(current)
    return list(reversed(path))


def _matched(targets, sources, parents):
    """Each target's sources and rule. See the module docstring."""
    assigned = {}
    matches = {}
    for name, (head, tail) in targets.items():
        for source, (source_head, source_tail) in sources.items():
            if source in assigned:
                continue
            if ((head - source_head).length < rig_definition.EXACT_METRES
                    and (tail - source_tail).length < rig_definition.EXACT_METRES):
                assigned[source] = name
                matches[name] = ("exact", [source])
                break
    for name, (head, tail) in targets.items():
        if name in matches:
            continue
        best = None
        for start, (source_head, _source_tail) in sources.items():
            if (head - source_head).length >= rig_definition.EXACT_METRES:
                continue
            for end, (_end_head, end_tail) in sources.items():
                if (tail - end_tail).length >= rig_definition.EXACT_METRES:
                    continue
                path = _descendants_path(parents, start, end)
                if path is None or any(bone in assigned for bone in path):
                    continue
                if best is None or len(path) < len(best):
                    best = path
        if best is not None:
            for bone in best:
                assigned[bone] = name
            matches[name] = ("chain", best)
    return (assigned, matches)


def _nearest_miss(head, tail, sources):
    best = None
    for source, (source_head, source_tail) in sources.items():
        distance = (head - source_head).length + (tail - source_tail).length
        if best is None or distance < best[0]:
            best = (distance, source, (head - source_head).length, (tail - source_tail).length)
    if best is None:
        return None
    return {"bone": best[1], "head_distance": round(best[2], 4),
            "tail_distance": round(best[3], 4)}


def _transfer(services, basemesh, armature, deforming, from_rig, space):
    """``(weights, report)`` or ``(None, refusal)``."""
    path, weights_path, weights_from = rig_definition.catalogue_files(services, from_rig)
    if path is None:
        return (None, ("unknown_identifier",
                       "No rig in the catalogue is identified by '{!s}', so nothing was "
                       "weighted. Call mpfb_list_rigs and pass an entry's 'identifier'.".format(
                           from_rig), {}))
    if weights_path is None:
        return (None, ("no_weights",
                       "'{!s}' has no weights file for mpfb_add_rig to load, so there is nothing "
                       "to transfer and nothing was weighted.".format(from_rig), {}))
    fit = rig_definition.fit_file(services, basemesh, path)
    sources = {}
    parents = {}
    for name, info in fit.rig_definition.items():
        sources[name] = (Vector(fit.get_best_location_from_strategy(info["head"])),
                         Vector(fit.get_best_location_from_strategy(info["tail"])))
        parents[name] = info.get("parent") or ""
    targets = {}
    for name in deforming:
        bone = armature.data.bones[name]
        targets[name] = (space.armature_to_local(armature, bone.head_local),
                         space.armature_to_local(armature, bone.tail_local))
    assigned, matches = _matched(targets, sources, parents)

    contributions = {name: [(source, rule) for source in found]
                     for name, (rule, found) in matches.items()}
    unassigned = []
    for source in sources:
        if source in assigned:
            continue
        ancestor = parents.get(source) or ""
        while ancestor and ancestor not in assigned:
            ancestor = parents.get(ancestor) or ""
        if ancestor:
            assigned[source] = assigned[ancestor]
            contributions[assigned[ancestor]].append((source, "ancestor"))
        else:
            unassigned.append(source)

    with open(weights_path, "r", encoding="utf-8") as json_file:
        groups = json.load(json_file).get("weights", {})
    weights = {name: {} for name in deforming}
    not_mapped = []
    for group, entries in groups.items():
        source = _source_bone_for_group(group, sources)
        if source is None:
            if not group.startswith("mhmask-"):
                not_mapped.append(group)
            continue
        target = assigned.get(source)
        if target is None:
            continue
        for index, weight in entries:
            weights[target][int(index)] = weights[target].get(int(index), 0.0) + float(weight)
    rows = {}
    for name in deforming:
        rule, _found = matches.get(name, ("none", []))
        row = {"matched_by": rule,
               "sources": [{"bone": source, "matched_by": how}
                           for source, how in contributions.get(name, [])]}
        if rule == "none":
            row["nearest_miss"] = _nearest_miss(targets[name][0], targets[name][1], sources)
        rows[name] = row
    return (weights, dict(
        from_rig=from_rig, weights_from=weights_from,
        weights_path=mpfb_surface.as_path(weights_path), per_bone=rows,
        source_bones_unassigned=sorted(unassigned), groups_not_mapped=sorted(not_mapped)))


# ----------------------------------------------------------------------
# mirror


def _mirror_pairs(services, direction):
    """``(from, to)`` vertex pairs out of MPFB's ``hm08.mirror``, the side ``direction`` copies.

    Read off the data file through ``LocationService`` rather than through
    ``TargetService._load_mirror_table()``, which is private; the file's format is
    ``<from> <to> <l|r|m>``, and ``symmetrize_shape_key()`` copies the ``l`` lines left to right.
    """
    directory = mpfb_surface.as_path(services["LocationService"].get_mpfb_data("mesh_metadata"))
    side = "l" if direction == "left_to_right" else "r"
    pairs = []
    with open(os.path.join(directory, "hm08.mirror"), "r", encoding="utf-8") as mirror_file:
        for line in mirror_file:
            parts = line.split()
            if len(parts) >= 3 and parts[2] == side:
                pairs.append((int(parts[0]), int(parts[1])))
    return pairs


def _partner(name, direction):
    """``(partner name or None, kind)``, kind ``"source"``, ``"destination"`` or ``"centre"``."""
    for left, right in _SIDES:
        for own, other, is_left in ((left, right, True), (right, left, False)):
            if name.endswith(own):
                partner = name[:-len(own)] + other
                source = is_left == (direction == "left_to_right")
                return (partner, "source" if source else "destination")
    return (name, "centre")


def _mirror(current, deforming, direction, pairs):
    """``(weights, report)``: destination vertices rewritten from their mirror images."""
    weights = {name: dict(entries) for name, entries in current.items()}
    for name in deforming:
        weights.setdefault(name, {})
    destination = [to_index for _from, to_index in pairs]
    for entries in weights.values():
        for index in destination:
            entries.pop(index, None)
    without_partner = []
    target_of = {}
    for name in deforming:
        partner, kind = _partner(name, direction)
        if kind == "centre":
            target_of[name] = name
        elif partner in deforming:
            target_of[name] = partner
        else:
            without_partner.append(name)
    for name, entries in current.items():
        target = target_of.get(name)
        if target is None:
            continue
        for from_index, to_index in pairs:
            weight = entries.get(from_index)
            if weight is not None:
                weights[target][to_index] = weight
    return (weights, dict(direction=direction, vertices_mirrored=len(pairs),
                          bones_without_partner=sorted(without_partner)))


# ----------------------------------------------------------------------
# The command


def _answer(subject, resolved_by, basemesh, params, **fields):
    answer = dict(
        found=basemesh is not None,
        ready=False,
        weighted=False,
        blocked_by=None,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        method=params["method"],
        rig_object_name=None,
    )
    answer.update(fields)
    return answer


def _argument_refusal(params):
    method = params["method"]
    for key, owner in (("exclude_bones", "automatic"), ("from_rig", "transfer"),
                       ("direction", "mirror")):
        if params[key] is not None and method != owner:
            return "{:s} is taken only with method {:s}, not {:s}.".format(key, owner, method)
    if method == "transfer" and params["from_rig"] is None:
        return "method transfer needs from_rig, a catalogue identifier from mpfb_list_rigs."
    if method == "mirror" and params["direction"] is None:
        return "method mirror needs direction, left_to_right or right_to_left."
    for key in ("exclude_bones", "bone_names"):
        value = params[key]
        if value is not None and (
                not isinstance(value, list) or not value
                or not all(isinstance(item, str) and item for item in value)
                or len(set(value)) != len(value)):
            return "{:s} must be a non-empty list of distinct bone names, or omitted.".format(key)
    return None


def _on_ground(services, armature):
    """Deforming bones whose head strategy is the ``joint-ground`` cube."""
    Rig = rig_definition.rig_class(services)  # pylint: disable=invalid-name
    names = []
    for bone in armature.data.bones:
        if not bone.use_deform:
            continue
        end, _force = Rig.get_bone_end_strategy(bone, False)
        if end is not None and end.get("cube_name") == _GROUND:
            names.append(bone.name)
    return sorted(names)


def _world_refusal(services, basemesh, armature):
    identified = services["RigService"].identify_rig(armature)
    if not rig_definition.is_authored(armature) and identified != "unknown":
        return ("rig_not_authored",
                "'{:s}' is the rig '{!s}', which mpfb_create_rig did not build and which has "
                "weights of its own, so nothing was weighted.".format(armature.name, identified),
                dict(rig_identified_as=identified))
    if bpy.context.mode != "OBJECT" or basemesh.mode != "OBJECT":
        return ("not_object_mode",
                "Blender is in {:s} mode, and weighting writes vertex groups in OBJECT mode, so "
                "nothing was weighted.".format(str(bpy.context.mode)), {})
    pose_reading.evaluated()
    posed = [pose_bone.name for pose_bone in armature.pose.bones if pose_reading.off_rest(pose_bone)]
    if posed:
        return ("rig_not_at_rest",
                "'{:s}' has {:d} bone(s) off rest, and weights are worked out at rest, so nothing "
                "was weighted. mpfb_reset_pose puts it back.".format(armature.name, len(posed)),
                dict(posed_bones=posed[:_MAX_NAMED]))
    return None


def _weight_rig(params, resolution):  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
    services = resolution.services
    basemesh, subject, resolved_by, message = subject_resolution.resolve_basemesh(
        services, params["name"], not_done="nothing was weighted",
        not_a_character="there is no body to weight")

    def blocked(reason, text, **extra):
        return with_performed(_answer(subject, resolved_by, basemesh, params, blocked_by=reason,
                                      message=text, **extra), False)

    if basemesh is None:
        return blocked("subject_not_found", message)
    error = _argument_refusal(params)
    if error is not None:
        return blocked("invalid_shape", error)
    armature = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        basemesh, "Skeleton")
    if armature is None:
        return blocked("not_rigged",
                       "'{:s}' has no rig, so there is nothing to weight. Build one with "
                       "mpfb_create_rig.".format(basemesh.name))
    refusal = _world_refusal(services, basemesh, armature)
    if refusal is not None:
        return blocked(refusal[0], refusal[1], rig_object_name=armature.name, **refusal[2])

    bone_names = set(armature.data.bones.keys())
    named = list(params["exclude_bones"] or []) + list(params["bone_names"] or [])
    unknown = sorted(set(name for name in named if name not in bone_names))
    if unknown:
        return blocked("unknown_bone_names",
                       "{:d} name(s) are not bones of '{:s}', so nothing was weighted: {:s}."
                       .format(len(unknown), armature.name, ", ".join(unknown[:_MAX_NAMED])),
                       rig_object_name=armature.name, unknown_bone_names=unknown)
    excluded = list(params["exclude_bones"] or [])
    deforming = [bone.name for bone in armature.data.bones
                 if bone.use_deform and bone.name not in excluded]
    if params["bone_names"] is not None:
        not_deforming = [name for name in params["bone_names"] if name not in deforming]
        if not_deforming:
            return blocked("not_deforming",
                           "{:d} bone(s) in bone_names do not deform, so they have no weights to "
                           "write and nothing was weighted: {:s}.".format(
                               len(not_deforming), ", ".join(not_deforming[:_MAX_NAMED])),
                           rig_object_name=armature.name, not_deforming_bones=not_deforming)
        written = [name for name in deforming if name in params["bone_names"]]
    else:
        written = list(deforming)
    if not written:
        return blocked("no_deforming_bones",
                       "'{:s}' has no deforming bone to weight, so nothing was weighted.".format(
                           armature.name), rig_object_name=armature.name)

    space = rig_definition.Space(basemesh, armature)
    fit = rig_definition.fit_definition(services, basemesh, {"bones": {}, "version": 110})
    positions = fit.position_info["vertices"]
    vertex_count = len(basemesh.data.vertices)
    classes = _vertex_classes(basemesh)
    current = _read_groups(basemesh, set(deforming))
    had_weights = sorted(name for name in written if current.get(name))

    report = {}
    method = params["method"]
    if method == "transfer":
        computed, report = _transfer(services, basemesh, armature, deforming,
                                     params["from_rig"], space)
        if computed is None:
            return blocked(report[0], report[1], rig_object_name=armature.name, **report[2])
    elif method == "mirror":
        computed, report = _mirror(current, deforming, params["direction"],
                                   _mirror_pairs(services, params["direction"]))
    else:
        for name in excluded:
            armature.data.bones[name].use_deform = False
        computed = _heat_copy(basemesh, armature, positions, classes)

    weights = {name: dict(entries) for name, entries in current.items() if name not in written}
    for name in written:
        weights[name] = dict(computed.get(name, {}))
    before, missing = _unweighted(classes, weights, vertex_count)
    fill = params["fill_unweighted"] and method != "mirror"
    filled = _fill(classes, weights, positions, missing, written) if fill else 0
    after, _missing = _unweighted(classes, weights, vertex_count)
    _write_groups(basemesh, {name: weights[name] for name in written})

    per_bone = report.pop("per_bone", {}) if isinstance(report, dict) else {}
    rows = []
    for name in written:
        row = {"name": name, "vertex_count": sum(
            1 for weight in weights[name].values() if weight > _NO_WEIGHT)}
        row.update(per_bone.get(name, {}))
        rows.append(row)
    without = [row["name"] for row in rows if row["vertex_count"] == 0]
    on_ground = _on_ground(services, armature)
    parts = ["Weighted {:d} bone(s) of '{:s}' by {:s}.".format(len(written), armature.name, method)]
    if before["body"]:
        parts.append(" {:d} body vertex(es) had no weight after the pass, which means the pass "
                     "itself missed them.".format(before["body"]))
    if fill:
        parts.append(" The fill gave {:d} vertex(es) their nearest body vertex's weights; {:d} "
                     "remain unweighted.".format(filled, sum(after.values())))
    if without:
        parts.append(" {:d} bone(s) got no weights at all; see bones_without_weights.".format(
            len(without)))
    if on_ground:
        parts.append(" {:s} deform(s) from joint-ground and will take the thighs; exclude it, "
                     "or check its vertex_count.".format(", ".join(on_ground)))
    if had_weights:
        parts.append(" {:d} group(s) that had weights were replaced; see groups_replaced.".format(
            len(had_weights)))
    _LOG.debug("weight_rig: %s on %r, %d bones", method, armature.name, len(written))
    answer = _answer(
        subject, resolved_by, basemesh, params,
        ready=True,
        weighted=True,
        rig_object_name=armature.name,
        bones_weighted=len(written),
        bones=rows,
        bones_without_weights=without,
        excluded_bones=sorted(excluded),
        set_non_deforming=sorted(excluded) if method == "automatic" else [],
        groups_replaced=had_weights,
        unweighted={"before_fill": before, "after_fill": after},
        fill_applied=fill,
        vertices_filled=filled,
        deforming_bones_on_ground=on_ground,
        next_with={"mpfb_store_rig": {"name": armature.name, "rig_name": None}},
        message="".join(parts))
    answer.update(report)
    return with_performed(answer, True)


def weight_rig(params, resolution):
    """Weight the rig, with the character in the view layer."""
    return view_layer.run(resolution.services, params["name"],
                          lambda: _weight_rig(params, resolution))
