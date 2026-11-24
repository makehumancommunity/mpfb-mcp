"""
``check_rig_weights``: a rig's weighting, measured, and a bend test that puts back what it moves.

Nothing in MPFB reads a weighting back
([FR 061](../../../feature-requests/done/061-rig-weights-that-hold-up/README.md)), and the only
evidence that FR 060's weights held up was a 90-degree bend looked at in a render. This reads the
weights of whichever rig moves a character - shipped, library or authored - so that a shipped rig
on a similar body can be the baseline an authored one is compared against. **It gives numbers, not
a verdict**, as ``check_intersections`` does.

**Every reading is [`shared/rig_weights.py`](../shared/rig_weights.py)'s**, the one ``weight_rig``
reports its counts through and ``store_rig`` its ``unweighted_bones``, so a character weighted and
then checked gets the same counts twice. Positions are the character at rest with its shape keys
evaluated, MPFB's position info, which is the body that will be posed; bones are where the rig has
them.

**The bend test is opt-in** (``sections`` naming ``bend``). It poses a fixed set of movements, one
at a time from rest, and measures each on the evaluated base mesh with every modifier but the
armature off, masks included, so the evaluated mesh keeps the base mesh's own vertex indices:

- **Which bone.** The deforming bone whose head is on that joint's cube, read through
  ``rig_definition.head_joints()``; several are resolved as the rigid helpers' are, by a word in
  the name, then by the most weight near the joint. None is ``not_tested``.
- **Which axis.** From a table in the **character frame**: each movement moves the bone toward a
  frame direction, about the axis perpendicular to that direction and the parent bone's rest
  direction (the bone's own when the parent's is parallel to it); a turn is about the bone's own
  rest direction. Never the bone's local axes, so a custom rig's roll cannot change what is
  tested. Only the left side is bent; the ``symmetry`` section is what says whether the right
  would differ.
- **A constrained bone is not bent.** A generated Rigify rig's ``DEF-`` bones copy their
  ``ORG-`` bones, and writing one would be undone by its constraint or would tear it from its
  children, so each is ``not_tested`` with ``constrained``.
- **Four measurements**, on the skin only - helpers are interior shells whose tiny edges would
  swamp a ratio - over the skin within :data:`REGION_METRES` of the joint, the same skin on any
  rig, so that a rig merging two bones is measured where one splitting them is: ``collapse``,
  the region's mean distance to the bone line (the parent and the moved bone) bent over rest,
  under 1.0 meaning pinching or candy-wrapping; ``edge_stretch``, the 99th percentile and largest
  ratio of an edge's length bent over rest; ``self_intersections``, face
  pairs in the region that intersect at rest and bent, through ``shared/mesh_overlap.py``; and
  ``stray``, vertices anywhere that moved more than :data:`STRAY_METRES` while farther than the
  reach limit from every bone of the moved chain - a left elbow that moves the torso.

The armature modifier's ``use_deform_preserve_volume`` is reported beside them, since it changes
them. The pose goes back through ``shared/pose_writing.py``'s snapshot, the modifiers as they
were; a rig that is not at rest is refused, since a bend from a pose measures that pose.

Changes nothing, ``bend`` included: a bridge test compares the ``bpy.data`` counts, the pose and
the modifiers before and after.
"""

__all__ = (
    "MOVEMENTS",
    "PARAMS",
    "SECTIONS",
    "SUMMARY",
    "check_rig_weights",
)

import contextlib
import math
import time

import bpy
import numpy
from mathutils import Quaternion  # pylint: disable=import-error

from ..log import get_logger
from ..shared import mesh_overlap
from ..shared import pose_reading
from ..shared import pose_writing
from ..shared import rig_definition
from ..shared import rig_weights
from ..shared import subject_resolution
from ..shared import view_layer
from ..shared.character_frame import Frame
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_STRING

_LOG = get_logger("commands.checkrigweights")

SECTIONS = ("coverage", "influences", "bones", "helpers", "symmetry", "bend")
DEFAULT_SECTIONS = SECTIONS[:-1]

# How many bones the bones section lists, worst first.
MAX_BONE_ROWS = 20

# The movements, each ``(name, joints, toward, degrees, words)``. ``joints`` is tried in order
# and the first with a deforming bone's head on it is bent, since rigs split a spine differently.
# ``toward`` is the frame direction the bone moves toward, or None for a turn about the bone's own
# direction; ``words`` picks among several bones on the joint.
MOVEMENTS = (
    ("elbow_flex", ("joint-l-elbow",), {"forward": 1.0}, 90.0, ("lowerarm", "forearm")),
    ("knee_flex", ("joint-l-knee",), {"forward": -1.0}, 90.0, ("lowerleg", "shin", "calf")),
    ("shoulder_abduct", ("joint-l-shoulder",), {"left": 1.0}, 90.0, ("upperarm", "arm")),
    ("hip_flex", ("joint-l-upper-leg",), {"forward": 1.0}, 90.0, ("upperleg", "thigh")),
    ("hip_abduct", ("joint-l-upper-leg",), {"left": 1.0}, 45.0, ("upperleg", "thigh")),
    ("wrist_flex", ("joint-l-hand",), {"forward": 1.0}, 60.0, ("hand", "wrist")),
    ("neck_turn", ("joint-neck",), None, 45.0, ("neck",)),
    ("spine_bend", ("joint-spine-3", "joint-spine-2", "joint-spine-4", "joint-spine-1"),
     {"forward": 1.0}, 30.0, ("spine", "chest")),
)

# The region a movement is measured over: the skin within this of the joint. A fixed radius
# rather than one scaled by the bone, so that two rigs, one of which merges the bones the other
# splits, are measured over the same skin and their numbers compare.
REGION_METRES = 0.1

# A vertex has moved when it moved more than this.
STRAY_METRES = 0.001

# A reference direction this close to parallel with the movement's direction gives no axis.
_PARALLEL_SINE = 0.3

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("sections", TYPE_ARRAY, default=None, nullable=True,
          description="Which sections to measure, from: {:s}. Omit for all but bend.".format(
              ", ".join(SECTIONS))),
)

SUMMARY = ("Measure a rig's weighting: coverage, influences, each bone's reach, the helpers, "
           "symmetry, and an opt-in bend test.")


def _answer(subject, resolved_by, basemesh, **fields):
    answer = dict(
        found=basemesh is not None,
        ready=False,
        blocked_by=None,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        rig_object_name=None,
        rig_identified_as=None,
        requested_sections=None,
    )
    answer.update(dict.fromkeys(SECTIONS))
    answer.update(fields)
    return answer


def _sections(requested):
    """``(sections, unknown)``, in :data:`SECTIONS` order."""
    if requested is None:
        return (list(DEFAULT_SECTIONS), [])
    unknown = [name for name in requested if name not in SECTIONS]
    return ([name for name in SECTIONS if name in requested], unknown)


def _thresholds():
    return {
        "no_weight": rig_weights.NO_WEIGHT,
        "normalised_tolerance": rig_weights.NORMALISED_TOLERANCE,
        "rigid_share": rig_weights.RIGID_SHARE,
        "reach_weight": rig_weights.REACH_WEIGHT,
        "far_ratio": rig_weights.FAR_RATIO,
        "far_min_metres": rig_weights.FAR_MIN_METRES,
        "region_metres": REGION_METRES,
        "stray_metres": STRAY_METRES,
    }


# ----------------------------------------------------------------------
# The bend test


@contextlib.contextmanager
def _only_the_armature(basemesh):
    """Every modifier but the armature off for the block, and each put back as it was."""
    shown = [(modifier, modifier.show_viewport) for modifier in basemesh.modifiers]
    try:
        for modifier, _was in shown:
            if modifier.type != "ARMATURE":
                modifier.show_viewport = False
        bpy.context.view_layer.update()
        yield
    finally:
        for modifier, was in shown:
            if modifier.show_viewport != was:
                modifier.show_viewport = was
        bpy.context.view_layer.update()


def _evaluated(basemesh):
    """``(positions, triangles)`` of the evaluated base mesh, basemesh-local, as arrays."""
    bpy.context.view_layer.update()
    evaluated = basemesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        count = len(mesh.vertices)
        positions = numpy.empty(count * 3, dtype=numpy.float64)
        mesh.vertices.foreach_get("co", positions)
        triangles = numpy.empty(len(mesh.loop_triangles) * 3, dtype=numpy.int64)
        mesh.loop_triangles.foreach_get("vertices", triangles)
    finally:
        evaluated.to_mesh_clear()
    return (positions.reshape(count, 3), triangles.reshape(-1, 3))


def _segment_distances(points, head, tail):
    """Each point's distance to the segment ``head``-``tail``, vectorised."""
    head = numpy.array(head, dtype=numpy.float64)
    line = numpy.array(tail, dtype=numpy.float64) - head
    length_squared = float(line @ line)
    if length_squared == 0.0:
        return numpy.linalg.norm(points - head, axis=1)
    factor = numpy.clip((points - head) @ line / length_squared, 0.0, 1.0)
    return numpy.linalg.norm(points - (head + factor[:, None] * line), axis=1)


def _self_pairs(positions, triangles, region):
    """Intersecting face pairs among the triangles wholly inside ``region``."""
    inside = numpy.zeros(len(positions), dtype=bool)
    inside[region] = True
    kept = triangles[inside[triangles].all(axis=1)]
    if len(kept) == 0:
        return 0
    used, reindexed = numpy.unique(kept, return_inverse=True)
    surface = mesh_overlap.Surface(positions[used], reindexed.reshape(-1, 3))
    return int(len(mesh_overlap.overlapping_triangles(surface, surface)))


def _descendants(armature, name):
    """``name`` and every bone below it."""
    names = []
    stack = [armature.data.bones[name]]
    while stack:
        bone = stack.pop()
        names.append(bone.name)
        stack.extend(bone.children)
    return names


def _axis(frame, bone, toward):
    """The armature-space axis a movement turns ``bone`` about, or None when there is none."""
    own = (bone.tail_local - bone.head_local).normalized()
    if toward is None:
        return own
    direction = frame.to_armature_direction(toward)
    if direction is None:
        return None
    references = []
    if bone.parent is not None:
        references.append((bone.parent.tail_local - bone.parent.head_local).normalized())
    references.append(own)
    for reference in references:
        axis = reference.cross(direction)
        if axis.length > _PARALLEL_SINE:
            return axis.normalized()
    return None


def _chosen_bone(candidates, words, weights, region):
    """``(bone, chosen_by)`` among the bones on a joint, as the rigid helpers choose."""
    if len(candidates) == 1:
        return (candidates[0], "only_candidate")
    named = [name for name in candidates if any(word in name.lower() for word in words)]
    if len(named) == 1:
        return (named[0], "joint_name")
    pool = named or candidates
    near = set(int(index) for index in region)

    def weight_near(name):
        return sum(weight for index, weight in weights.get(name, {}).items() if index in near)

    return (max(pool, key=lambda name: (weight_near(name), name)), "weight_near_joint")


def _movement(context, movement):  # pylint: disable=too-many-locals,too-many-statements
    """One movement's row: bent, measured and put back."""
    name, joints, toward, degrees, words = movement
    armature = context["armature"]
    space = context["space"]
    row = {"movement": name, "joint": joints[0], "degrees": degrees}
    candidates = []
    for joint in joints:
        candidates = sorted(bone for bone in context["deforming"]
                            if context["anchors"].get(bone) == joint)
        if candidates:
            row["joint"] = joint
            break
    if not candidates:
        return dict(row, tested=False, not_tested="no_bone_on_joint")
    rest = context["rest"]
    skin = context["skin"]
    first = armature.data.bones[candidates[0]]
    joint_position = numpy.array(space.armature_to_local(armature, first.head_local))
    region = skin[numpy.linalg.norm(rest[skin] - joint_position, axis=1) < REGION_METRES]
    bone_name, chosen_by = _chosen_bone(candidates, words, context["weights"], region)
    bone = armature.data.bones[bone_name]
    pose_bone = armature.pose.bones[bone_name]
    row.update(bone=bone_name, chosen_by=chosen_by,
               candidates=[other for other in candidates if other != bone_name])
    if any(constraint.enabled for constraint in pose_bone.constraints):
        return dict(row, tested=False, not_tested="constrained")
    axis = _axis(context["frame"], bone, toward)
    if axis is None:
        return dict(row, tested=False, not_tested="no_axis")

    saved = pose_writing.snapshot(armature, [bone_name])
    try:
        _location, orientation, _scale = pose_writing.own_matrix(pose_bone).decompose()
        pose_writing.write(pose_bone,
                           orientation=Quaternion(axis, math.radians(degrees)) @ orientation)
        bent, _triangles = _evaluated(context["basemesh"])
        posed_head = space.armature_to_local(armature, pose_bone.head)
        posed_tail = space.armature_to_local(armature, pose_bone.tail)
    finally:
        pose_writing.restore(armature, saved)
    if len(bent) != len(rest):
        return dict(row, tested=False, not_tested="vertex_count_changed")

    lines_rest = [(space.armature_to_local(armature, bone.head_local),
                   space.armature_to_local(armature, bone.tail_local))]
    lines_bent = [(posed_head, posed_tail)]
    if bone.parent is not None:
        parent = (space.armature_to_local(armature, bone.parent.head_local),
                  space.armature_to_local(armature, bone.parent.tail_local))
        lines_rest.append(parent)
        lines_bent.append(parent)

    def spread(points, lines):
        return numpy.min([_segment_distances(points, *line) for line in lines], axis=0)

    collapse = None
    if len(region):
        at_rest = float(spread(rest[region], lines_rest).mean())
        if at_rest > 0.0:
            collapse = round(float(spread(bent[region], lines_bent).mean()) / at_rest, 3)
    edges = context["edges"]
    in_region = numpy.zeros(len(rest), dtype=bool)
    in_region[region] = True
    kept = edges[in_region[edges].all(axis=1)]
    stretch = {"p99": None, "max": None, "edges": int(len(kept))}
    if len(kept):
        before = numpy.linalg.norm(rest[kept[:, 0]] - rest[kept[:, 1]], axis=1)
        after = numpy.linalg.norm(bent[kept[:, 0]] - bent[kept[:, 1]], axis=1)
        ratios = after[before > 0.0] / before[before > 0.0]
        if len(ratios):
            stretch.update(p99=round(float(numpy.percentile(ratios, 99)), 3),
                           max=round(float(ratios.max()), 3))
    moved = skin[numpy.linalg.norm(bent[skin] - rest[skin], axis=1) > STRAY_METRES]
    stray = 0
    if len(moved):
        near_any = numpy.zeros(len(moved), dtype=bool)
        for chained in _descendants(armature, bone_name):
            chain_bone = armature.data.bones[chained]
            chain_head = space.armature_to_local(armature, chain_bone.head_local)
            chain_tail = space.armature_to_local(armature, chain_bone.tail_local)
            limit = rig_weights.reach_limit(chain_head, chain_tail)
            near_any |= _segment_distances(rest[moved], chain_head, chain_tail) <= limit
        stray = int((~near_any).sum())
    return dict(
        row, tested=True,
        axis=context["frame"].armature_direction(axis),
        region_vertices=int(len(region)),
        collapse=collapse,
        edge_stretch=stretch,
        self_intersections={"rest": _self_pairs(rest, context["triangles"], region),
                            "bent": _self_pairs(bent, context["triangles"], region)},
        moved_vertices=int(len(moved)),
        stray=stray)


def _bend(services, basemesh, armature, weights, deforming, fit, space, the_layout):  # pylint: disable=too-many-arguments,too-many-locals
    """The bend section: every movement, measured and put back."""
    started = time.perf_counter()
    anchors, anchors_from = rig_definition.head_joints(services, armature, fit, space)
    modifier = next(modifier for modifier in basemesh.modifiers
                    if modifier.type == "ARMATURE" and modifier.object == armature)
    edges = numpy.empty(len(basemesh.data.edges) * 2, dtype=numpy.int64)
    basemesh.data.edges.foreach_get("vertices", edges)
    rows = []
    with pose_writing.showing_pose(armature):
        with _only_the_armature(basemesh):
            rest, triangles = _evaluated(basemesh)
            skin = numpy.array(the_layout.skin(), dtype=numpy.int64)
            is_skin = numpy.zeros(len(rest), dtype=bool)
            is_skin[skin] = True
            context = {"armature": armature, "basemesh": basemesh, "space": space, "skin": skin,
                       "frame": Frame(armature), "deforming": deforming, "anchors": anchors,
                       "weights": weights, "rest": rest,
                       "triangles": triangles[is_skin[triangles].all(axis=1)],
                       "edges": edges.reshape(-1, 2)}
            for movement in MOVEMENTS:
                rows.append(_movement(context, movement))
    return {
        "movements": rows,
        "tested": sum(1 for row in rows if row["tested"]),
        "not_tested": [row["movement"] for row in rows if not row["tested"]],
        "anchors_from": anchors_from,
        "preserve_volume": bool(modifier.use_deform_preserve_volume),
        "milliseconds": round((time.perf_counter() - started) * 1000.0),
    }


def _bend_refusal(basemesh, armature):
    """``(reason, sentence)`` when the bend cannot be measured, or None."""
    if bpy.context.mode != "OBJECT":
        return ("not_object_mode",
                "Blender is in {:s} mode and the bend test evaluates the mesh in OBJECT mode, so "
                "nothing was measured.".format(str(bpy.context.mode)))
    if not any(modifier.type == "ARMATURE" and modifier.object == armature
               for modifier in basemesh.modifiers):
        return ("no_armature_modifier",
                "'{:s}' has no armature modifier on '{:s}', so a bend would not move it and "
                "nothing was measured.".format(basemesh.name, armature.name))
    pose_reading.evaluated()
    posed = [pose_bone.name for pose_bone in armature.pose.bones
             if pose_reading.off_rest(pose_bone)]
    if posed:
        return ("rig_not_at_rest",
                "'{:s}' has {:d} bone(s) off rest, and a bend is measured from rest, so nothing "
                "was measured. mpfb_reset_pose puts it back.".format(armature.name, len(posed)))
    return None


# ----------------------------------------------------------------------
# The command


def _check_rig_weights(params, resolution):  # pylint: disable=too-many-locals
    services = resolution.services
    basemesh, subject, resolved_by, message = subject_resolution.resolve_basemesh(
        services, params["name"], not_done="nothing was measured",
        not_a_character="there is no body to measure")

    def blocked(reason, text, **extra):
        return _answer(subject, resolved_by, basemesh, blocked_by=reason, message=text, **extra)

    if basemesh is None:
        return blocked("subject_not_found", message)
    sections, unknown = _sections(params["sections"])
    if unknown:
        return blocked("unknown_section",
                       "sections knows only {:s}; {:s} is not one, so nothing was measured."
                       .format(", ".join(SECTIONS), ", ".join(unknown)),
                       known_sections=list(SECTIONS))
    if not sections:
        return blocked("invalid_shape", "sections must name at least one section, or be omitted.")
    armature = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        basemesh, "Skeleton")
    if armature is None:
        return blocked("not_rigged",
                       "'{:s}' has no rig, so there are no weights to measure.".format(
                           basemesh.name))
    identified = services["RigService"].identify_rig(armature)
    if "bend" in sections:
        refusal = _bend_refusal(basemesh, armature)
        if refusal is not None:
            return blocked(refusal[0], refusal[1], rig_object_name=armature.name,
                           rig_identified_as=identified, requested_sections=sections)

    deforming = rig_weights.deforming_bones(armature)
    weights = rig_weights.read_weights(basemesh, set(deforming))
    rows = rig_weights.by_vertex(weights)
    the_layout = rig_weights.layout(services, basemesh)
    vertex_count = len(basemesh.data.vertices)
    space = rig_definition.Space(basemesh, armature)
    fit = rig_definition.fit_definition(services, basemesh, {"bones": {}, "version": 110})
    positions = fit.position_info["vertices"]
    segments = {name: (space.armature_to_local(armature, armature.data.bones[name].head_local),
                       space.armature_to_local(armature, armature.data.bones[name].tail_local))
                for name in deforming}

    found = {}
    if "coverage" in sections:
        found["coverage"] = rig_weights.coverage(the_layout, weights, deforming, basemesh,
                                                 armature.data.bones.keys())
    if "influences" in sections:
        found["influences"] = rig_weights.influences(rows, vertex_count)
    if "bones" in sections:
        found["bones"] = rig_weights.bone_rows(weights, deforming, segments, positions,
                                               MAX_BONE_ROWS)
    if "helpers" in sections:
        found["helpers"] = {"rows": rig_weights.helper_rows(the_layout, rows),
                            "not_in_table": sorted(name for name in the_layout.helpers
                                                   if name not in rig_weights.HELPER_RULES)}
    if "symmetry" in sections:
        found["symmetry"] = rig_weights.symmetry(weights, deforming,
                                                 rig_weights.mirror_pairs(services, "l"))
    if "bend" in sections:
        found["bend"] = _bend(services, basemesh, armature, weights, deforming, fit, space,
                              the_layout)

    parts = ["Measured the weights of '{:s}' ({!s}), {:d} deforming bone(s).".format(
        armature.name, identified, len(deforming))]
    if "coverage" in found and found["coverage"]["unweighted"]["total"]:
        parts.append(" {:d} vertex(es) have no deform weight.".format(
            found["coverage"]["unweighted"]["total"]))
    if "influences" in found and found["influences"]["unnormalised"]:
        parts.append(" {:d} vertex(es) do not add up to 1.".format(
            found["influences"]["unnormalised"]))
    if "bend" in found and found["bend"]["not_tested"]:
        parts.append(" Not bent: {:s}.".format(", ".join(found["bend"]["not_tested"])))
    parts.append(" Compare against a shipped rig on a similar body; there is no verdict here.")
    _LOG.debug("check_rig_weights: %r, %s", armature.name, sections)
    return _answer(subject, resolved_by, basemesh, ready=True, rig_object_name=armature.name,
                   rig_identified_as=identified, requested_sections=sections,
                   deforming_bone_count=len(deforming), vertex_count=vertex_count,
                   thresholds=_thresholds(), message="".join(parts), **found)


def check_rig_weights(params, resolution):
    """Measure the weights, with the character in the view layer."""
    return view_layer.run(resolution.services, params["name"],
                          lambda: _check_rig_weights(params, resolution))
