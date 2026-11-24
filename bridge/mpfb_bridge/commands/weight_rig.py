"""
``weight_rig``: vertex weights for an authored rig, three ways, a fill for what they miss, and a clean.

Nothing in MPFB weights a new rig ([FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)).
MakeRig's auto transfer copies a group only between bones whose ends both coincide within a
millimetre, and MakeWeight's symmetrize does nothing at all
(``mpfb2/efforts/bugs/local/symmetrize-weights-not-implemented.md``). So this has four
methods, each writing the vertex groups of deforming bones and nothing else:

- **``automatic``** is Blender's heat weighting, ``parent_set(type='ARMATURE_AUTO')``.
- **``transfer``** takes a catalogue rig's weights, through a match that understands merged
  chains, which MakeRig's operator does not.
- **``mirror``** copies one side onto the other through MPFB's own ``hm08.mirror``.
- **``clean``** only trims, caps and normalises what is there (below).

**Heat weighting runs on the neutral body, never the character as modelled**
([FR 061](../../../feature-requests/done/061-rig-weights-that-hold-up/README.md)). A weights file is
per base-mesh vertex and is loaded onto every body, so a file weighted on a heavy, short character
would carry that character's proportions to all of them. So the rig's own definition - the
strategies ``create_rig`` saved on the bones - is fitted to the **Basis** in memory
(``rig_definition.fit_definition(shape_keys=False)``), a temporary armature is built from that fit
by MPFB's own ``create_armature_and_fit_to_basemesh()``, with no modifier, and the pass runs on a
temporary mesh at the Basis positions against it. Both temporaries are removed however the pass
ends. Two characters modelled differently, carrying one authored rig, get the same groups, which
a bridge test holds. An end that does not follow the body, a ``position`` built with
``snap: false``, sits at the same coordinates on the neutral body, which is not necessarily
where its author meant it, so every such end is named in ``ends_not_following_body``.

**Two findings of FR 060's still shape the pass.** Blender's skinning (``armature_skinning.cc``)
reads a mesh's original positions, ``mesh->vert_positions()``, so the pass needs a mesh whose
positions *are* the body it means; and with the joint cubes in the mesh the heat solve fails for
**every** bone, because MPFB fits a bone end exactly at a cube's centre (0 of 14,380 vertices
weighted on the default body). The cubes are never in the pass.

**The pass is over the skin only** (:data:`HEAT_PASS_CLASSES`), the helpers left out with the
cubes, and FR 061's live check chose it over the skin with the helpers. Blender's
``heat_ray_source_visible()`` tests line of sight through every triangle of the mesh, so interior
shells could have hidden bones from the skin; on ``claude_demo`` they did not - the skin's weights
and every bend number came out the same either way - but the whole-mesh pass was 24% slower (567
ms against 459) and the helper weights it made put three times as many vertices beyond their
bone's reach (9,834 against 3,226), where the rules below bind an eye rigidly. Two characters
modelled differently get the same groups to within 1.3e-6, which is what MPFB's shift of each
Basis to put the feet on the ground leaves; weighting the modelled body, as FR 060 did, differed
by up to 1.0.

**The fill is a rule per helper**, from one table in
[`shared/rig_weights.py`](../shared/rig_weights.py): the eyes and teeth rigid to one bone, the
tongue blended over the bones inside it, and everything else - the eyelashes, hair, skirt,
tights, the joint cubes - an inverse-distance blend of the four nearest weighted skin vertices.
The skirt is what that ``k`` was measured on, as the request said: with ``k = 1`` it splits
between the legs (edge stretch 8.0 at the 99th percentile with the hip abducted 45 degrees), with
2 to 16 it is 4.8, unchanged, because its nearest skin is one thigh or the other however many
are taken, and MPFB's hand-made ``default`` weights give 2.7. Nearest skin is not how to weight a
skirt; it is the rule until something better is scoped. A nearest-skin
fill alone put an eye on its eyelid. Per helper the answer says which rule, which bone, and for a
rigid one ``chosen_by`` and the other ``candidates``; ``helper_bones`` overrides the choice. The
rules run when the call writes every deforming bone; a call narrowed by ``bone_names`` gets the
nearest fill alone, as it cannot write the bones a rule would choose. The fill works on the
neutral body too, so its distances are the same on every character.

**Every method ends by cleaning**, and ``clean`` is a method of its own that does only that: a
weight below ``min_weight`` dropped, ``max_influences`` kept per vertex, the rest normalised, over
the deforming bones' groups only and never a mask. Normalising rescales groups the pass did not
otherwise write, and those are listed as ``groups_rescaled``, a second kind of change to state the
call did not create beside ``groups_replaced``. MakeWeight's Truncate empties the group
(``mpfb2/efforts/bugs/local/truncate-weights-wipes-group.md``) and is replaced, not called.

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
    "HEAT_PASS_CLASSES",
    "METHODS",
    "PARAMS",
    "SUMMARY",
    "weight_rig",
)

import json
import re

import bpy
from mathutils import Vector  # pylint: disable=import-error

from ..log import get_logger
from ..shared import mpfb_surface
from ..shared import pose_reading
from ..shared import rig_definition
from ..shared import rig_weights
from ..shared import selection
from ..shared import subject_resolution
from ..shared import view_layer
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_INTEGER
from ..validation import TYPE_NUMBER
from ..validation import TYPE_OBJECT
from ..validation import TYPE_STRING

_LOG = get_logger("commands.weightrig")

METHODS = ("automatic", "transfer", "mirror", "clean")
DIRECTIONS = ("left_to_right", "right_to_left")

# The vertex classes (``rig_weights.Layout``) the heat pass weights. The joint cubes are never
# among them; FR 061's live check chose between the skin alone and the skin with the helpers.
HEAT_PASS_CLASSES = ("body",)

_GROUND = "joint-ground"

# How many names a list in a refusal carries before it is cut.
_MAX_NAMED = 40

# The temporary objects' names carry this, so a leftover would say whose it was.
_TEMPORARY = ".mpfb_bridge_heat"

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("method", TYPE_STRING, required=True, choices=METHODS,
          description="automatic (heat weighting), transfer (from_rig's weights), mirror "
                      "(one side onto the other) or clean (only the clean)."),
    Param("exclude_bones", TYPE_ARRAY, default=None, nullable=True,
          description="automatic only: bones to leave out of the pass, set non-deforming."),
    Param("from_rig", TYPE_STRING, default=None, nullable=True,
          description="transfer only: the catalogue rig whose weights to take."),
    Param("direction", TYPE_STRING, default=None, nullable=True, choices=DIRECTIONS,
          description="mirror only: left_to_right or right_to_left."),
    Param("fill_unweighted", TYPE_BOOLEAN, default=True,
          description="After automatic or transfer, give every unweighted vertex weights by "
                      "the helper rules."),
    Param("bone_names", TYPE_ARRAY, default=None, nullable=True,
          description="Only weight these deforming bones. Omit for all of them."),
    Param("helper_bones", TYPE_OBJECT, default=None, nullable=True,
          description="automatic or transfer: {helper group: bone}, a rigid helper's bone "
                      "chosen rather than found."),
    Param("min_weight", TYPE_NUMBER, default=rig_weights.NO_WEIGHT, minimum=0.0, maximum=1.0,
          description="The clean drops a deform weight below this."),
    Param("max_influences", TYPE_INTEGER, default=None, nullable=True, minimum=1,
          description="The clean keeps at most this many deform weights per vertex. Omit for "
                      "no cap."),
)

SUMMARY = ("Weight an authored rig: heat weighting on the neutral body, a transfer from a "
           "catalogue rig, a mirror, or a clean; helpers filled by rule, influences cleaned.")


# ----------------------------------------------------------------------
# automatic


def _heat_copy(basemesh, armature, positions, classes, kept=None):
    """Heat-weight a mesh at ``positions`` against ``armature``; ``{bone: {vertex: weight}}``.

    The mesh is new, built from the basemesh's faces whose every vertex is of a ``kept`` class,
    renumbered, so it shares no group data with the character; the weights come back under the
    basemesh's own vertex indices.
    """
    kept = HEAT_PASS_CLASSES if kept is None else kept
    chosen = [index for index in range(len(positions)) if classes[index] in kept]
    renumbered = {index: slot for slot, index in enumerate(chosen)}
    faces = [tuple(renumbered[index] for index in polygon.vertices)
             for polygon in basemesh.data.polygons
             if all(index in renumbered for index in polygon.vertices)]
    mesh = bpy.data.meshes.new(basemesh.name + _TEMPORARY)
    mesh.from_pydata([tuple(positions[index]) for index in chosen], [], faces)
    mesh.update()
    copy = bpy.data.objects.new(mesh.name, mesh)
    try:
        bpy.context.scene.collection.objects.link(copy)
        copy.matrix_world = basemesh.matrix_world.copy()
        bpy.context.view_layer.update()
        deforming = rig_weights.deforming_bones(armature)
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
        weights = rig_weights.read_weights(copy, set(deforming))
        return {name: {chosen[slot]: weight for slot, weight in entries.items()}
                for name, entries in weights.items()}
    finally:
        bpy.data.objects.remove(copy, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _neutral_header(services, basemesh, armature):
    """The armature's own definition, in MPFB's format, as a header the fitter can build from."""
    definition, _saved = rig_definition.armature_definition(services, armature)
    for info in definition.values():
        info.setdefault("use_local_location", True)
        info.setdefault("use_inherit_rotation", True)
        info.setdefault("inherit_scale", "FULL")
        info.setdefault("rigify", {})
    return rig_definition.header_for(services, basemesh, definition)


def _neutral_fit(services, basemesh, armature):
    """The armature's definition fitted to the Basis, in memory: ``(fit, segments)``."""
    fit = rig_definition.fit_definition(services, basemesh,
                                        _neutral_header(services, basemesh, armature),
                                        shape_keys=False)
    segments = {}
    for name, info in fit.rig_definition.items():
        segments[name] = (Vector(fit.get_best_location_from_strategy(info["head"])),
                          Vector(fit.get_best_location_from_strategy(info["tail"])))
    return (fit, segments)


def _heat_neutral(services, basemesh, armature, fit, classes):
    """Heat weighting on the neutral body, against a temporary armature fitted to it."""
    names_before = set(bpy.data.objects.keys())
    armatures_before = set(bpy.data.armatures.keys())
    try:
        with selection.restored_all():
            services["ObjectService"].activate_blender_object(basemesh)
            temporary = fit.create_armature_and_fit_to_basemesh(add_modifier=False)
            temporary.name = temporary.data.name = basemesh.name + _TEMPORARY + ".rig"
            temporary.matrix_world = basemesh.matrix_world.copy()
            for bone in temporary.data.bones:
                original = armature.data.bones.get(bone.name)
                bone.use_deform = original is not None and original.use_deform
            bpy.context.view_layer.update()
        return _heat_copy(basemesh, temporary, fit.position_info["vertices"], classes)
    finally:
        for name in set(bpy.data.objects.keys()) - names_before:
            leftover = bpy.data.objects.get(name)
            if leftover is not None:
                bpy.data.objects.remove(leftover, do_unlink=True)
        for name in set(bpy.data.armatures.keys()) - armatures_before:
            leftover = bpy.data.armatures.get(name)
            if leftover is not None and leftover.users == 0:
                bpy.data.armatures.remove(leftover)
        bpy.context.view_layer.update()


def _fixed_ends(services, armature):
    """Every end the body does not move: MPFB's ``DEFAULT``, the table's ``snap: false``."""
    definition, _saved = rig_definition.armature_definition(services, armature)
    return [{"bone": name, "end": key} for name, info in definition.items()
            for key in ("head", "tail")
            if info[key].get("strategy") in (None, "DEFAULT") and info.get("use_deform")]


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
    """``(from, to)`` vertex pairs, the side ``direction`` copies: ``symmetrize_shape_key()``'s ``l``."""
    return rig_weights.mirror_pairs(services, "l" if direction == "left_to_right" else "r")


def _partner(name, direction):
    """``(partner name or None, kind)``, kind ``"source"``, ``"destination"`` or ``"centre"``."""
    for left, right in rig_weights.SIDES:
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


def _argument_refusal(params):  # pylint: disable=too-many-return-statements
    method = params["method"]
    for key, owners in (("exclude_bones", ("automatic",)), ("from_rig", ("transfer",)),
                        ("direction", ("mirror",)), ("helper_bones", ("automatic", "transfer")),
                        ("bone_names", ("automatic", "transfer", "mirror"))):
        if params[key] is not None and method not in owners:
            return "{:s} is taken only with method {:s}, not {:s}.".format(
                key, " or ".join(owners), method)
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
    helpers = params["helper_bones"]
    if helpers is not None and (not helpers or not all(
            isinstance(key, str) and key and isinstance(value, str) and value
            for key, value in helpers.items())):
        return "helper_bones must be a non-empty object of helper group names to bone names."
    if not params["min_weight"] < 1.0:
        return "min_weight must be below 1.0, or every weight would be dropped."
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


def _names_refusal(armature, params, the_layout):
    """``(reason, sentence, extra)`` for a name that is not a bone or not a helper, or None."""
    bone_names = set(armature.data.bones.keys())
    helpers = params["helper_bones"] or {}
    named = (list(params["exclude_bones"] or []) + list(params["bone_names"] or [])
             + list(helpers.values()))
    unknown = sorted(set(name for name in named if name not in bone_names))
    if unknown:
        return ("unknown_bone_names",
                "{:d} name(s) are not bones of '{:s}', so nothing was weighted: {:s}.".format(
                    len(unknown), armature.name, ", ".join(unknown[:_MAX_NAMED])),
                dict(unknown_bone_names=unknown))
    groups = sorted(name for name in helpers if name not in the_layout.helpers)
    if groups:
        return ("unknown_helper_groups",
                "{:d} key(s) of helper_bones are not helper groups on this body, so nothing was "
                "weighted: {:s}. They are: {:s}.".format(
                    len(groups), ", ".join(groups), ", ".join(sorted(the_layout.helpers))),
                dict(unknown_helper_groups=groups, helper_groups=sorted(the_layout.helpers)))
    excluded = set(params["exclude_bones"] or [])
    not_deforming = sorted(name for name in helpers.values()
                           if not armature.data.bones[name].use_deform or name in excluded)
    if not_deforming:
        return ("not_deforming",
                "{:d} bone(s) in helper_bones do not deform, so a helper bound to them would not "
                "move and nothing was weighted: {:s}.".format(
                    len(not_deforming), ", ".join(not_deforming)),
                dict(not_deforming_bones=not_deforming))
    return None


def _computed(services, params, basemesh, armature, deforming, current, the_layout, neutral):
    """``(weights for the written bones, report)`` by the method, or ``(None, refusal)``."""
    method = params["method"]
    if method == "transfer":
        space = rig_definition.Space(basemesh, armature)
        return _transfer(services, basemesh, armature, deforming, params["from_rig"], space)
    if method == "mirror":
        return _mirror(current, deforming, params["direction"],
                       _mirror_pairs(services, params["direction"]))
    for name in params["exclude_bones"] or []:
        armature.data.bones[name].use_deform = False
    return (_heat_neutral(services, basemesh, armature, neutral[0], the_layout.classes),
            {"weighted_on": "neutral_base_mesh",
             "ends_not_following_body": _fixed_ends(services, armature)})


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
    the_layout = rig_weights.layout(services, basemesh)
    refusal = _names_refusal(armature, params, the_layout)
    if refusal is not None:
        return blocked(refusal[0], refusal[1], rig_object_name=armature.name, **refusal[2])

    method = params["method"]
    excluded = list(params["exclude_bones"] or [])
    deforming = [name for name in rig_weights.deforming_bones(armature) if name not in excluded]
    if params["bone_names"] is not None:
        not_deforming = [name for name in params["bone_names"] if name not in deforming]
        if not_deforming:
            return blocked("not_deforming",
                           "{:d} bone(s) in bone_names do not deform, so they have no weights to "
                           "write and nothing was weighted: {:s}.".format(
                               len(not_deforming), ", ".join(not_deforming[:_MAX_NAMED])),
                           rig_object_name=armature.name, not_deforming_bones=not_deforming)
        written = [name for name in deforming if name in params["bone_names"]]
    elif method == "clean":
        written = []
    else:
        written = list(deforming)
    if not deforming or (method != "clean" and not written):
        return blocked("no_deforming_bones",
                       "'{:s}' has no deforming bone to weight, so nothing was weighted.".format(
                           armature.name), rig_object_name=armature.name)

    vertex_count = len(basemesh.data.vertices)
    floor = 0.0 if method == "clean" else rig_weights.NO_WEIGHT
    current = rig_weights.read_weights(basemesh, set(deforming), floor=floor)
    had_weights = sorted(name for name in written if current.get(name))
    neutral = _neutral_fit(services, basemesh, armature)

    report = {}
    if method == "clean":
        computed = {}
    else:
        computed, report = _computed(services, params, basemesh, armature, deforming, current,
                                     the_layout, neutral)
        if computed is None:
            return blocked(report[0], report[1], rig_object_name=armature.name, **report[2])

    weights = {name: dict(entries) for name, entries in current.items() if name not in written}
    for name in written:
        weights[name] = dict(computed.get(name, {}))
    rows = rig_weights.by_vertex(weights)
    before = rig_weights.unweighted_counts(the_layout, rows)
    fill = params["fill_unweighted"] and method in ("automatic", "transfer")
    fill_report = {"filled": 0, "helpers": [], "helpers_not_in_table": []}
    if fill:
        fit, segments = neutral
        anchors, _anchors_from = rig_definition.head_joints(
            services, armature, fit, rig_definition.Space(basemesh, armature))
        rows, fill_report = rig_weights.fill(
            the_layout, rows, fit.position_info["vertices"], deforming, anchors, segments,
            helper_bones=params["helper_bones"], apply_rules=params["bone_names"] is None)
    after = rig_weights.unweighted_counts(the_layout, rows)

    histogram_before = rig_weights.histogram(rows, vertex_count)
    rows, cleaned = rig_weights.clean(rows, params["min_weight"], params["max_influences"])
    final = rig_weights.by_group(rows, deforming)
    rescaled = sorted(name for name in cleaned["groups_changed"] if name not in written)
    if method == "clean":
        rescaled = sorted(cleaned["groups_changed"])
    rig_weights.write_groups(basemesh, {name: final[name] for name in list(written) + rescaled})

    per_bone = report.pop("per_bone", {}) if isinstance(report, dict) else {}
    bone_rows = []
    for name in written:
        row = {"name": name, "vertex_count": len(final.get(name, {}))}
        row.update(per_bone.get(name, {}))
        bone_rows.append(row)
    without = [row["name"] for row in bone_rows if row["vertex_count"] == 0]
    on_ground = _on_ground(services, armature)
    if method == "clean":
        parts = ["Cleaned the weights of '{:s}'.".format(armature.name)]
    else:
        parts = ["Weighted {:d} bone(s) of '{:s}' by {:s}{:s}.".format(
            len(written), armature.name, method,
            ", on the neutral body" if method == "automatic" else "")]
    if before["body"] and method != "clean":
        parts.append(" {:d} body vertex(es) had no weight after the pass, which means the pass "
                     "itself missed them.".format(before["body"]))
    if fill:
        parts.append(" The fill gave {:d} vertex(es) weights by the helper rules; {:d} remain "
                     "unweighted.".format(fill_report["filled"], sum(after.values())))
    parts.append(" The clean trimmed {:d} vertex(es) and normalised {:d}.".format(
        cleaned["vertices_trimmed"], cleaned["vertices_normalised"]))
    if without:
        parts.append(" {:d} bone(s) got no weights at all; see bones_without_weights.".format(
            len(without)))
    if on_ground:
        parts.append(" {:s} deform(s) from joint-ground and will take the thighs; exclude it, "
                     "or check its vertex_count.".format(", ".join(on_ground)))
    if had_weights:
        parts.append(" {:d} group(s) that had weights were replaced; see groups_replaced.".format(
            len(had_weights)))
    if rescaled:
        parts.append(" {:d} group(s) the call did not otherwise write were rescaled; see "
                     "groups_rescaled.".format(len(rescaled)))
    if report.get("ends_not_following_body"):
        parts.append(" {:d} end(s) are fixed positions, the same on the neutral body as on this "
                     "one; see ends_not_following_body.".format(
                         len(report["ends_not_following_body"])))
    _LOG.debug("weight_rig: %s on %r, %d bones", method, armature.name, len(written))
    answer = _answer(
        subject, resolved_by, basemesh, params,
        ready=True,
        weighted=True,
        rig_object_name=armature.name,
        weighted_on=None,
        ends_not_following_body=[],
        bones_weighted=len(written),
        bones=bone_rows,
        bones_without_weights=without,
        excluded_bones=sorted(excluded),
        set_non_deforming=sorted(excluded) if method == "automatic" else [],
        groups_replaced=had_weights,
        groups_rescaled=rescaled,
        unweighted={"before_fill": before, "after_fill": after},
        fill_applied=fill,
        vertices_filled=fill_report["filled"],
        helpers=fill_report["helpers"],
        helpers_not_in_table=fill_report["helpers_not_in_table"],
        clean={"min_weight": params["min_weight"], "max_influences": params["max_influences"],
               "histogram_before": histogram_before,
               "histogram_after": rig_weights.histogram(rows, vertex_count),
               "vertices_trimmed": cleaned["vertices_trimmed"],
               "vertices_normalised": cleaned["vertices_normalised"],
               "max_weight_removed": cleaned["max_weight_removed"]},
        deforming_bones_on_ground=on_ground,
        next_with={"mpfb_check_rig_weights": {"name": armature.name}},
        message="".join(parts))
    answer.update(report)
    return with_performed(answer, bool(written) or bool(rescaled))


def weight_rig(params, resolution):
    """Weight the rig, with the character in the view layer."""
    return view_layer.run(resolution.services, params["name"],
                          lambda: _weight_rig(params, resolution))
