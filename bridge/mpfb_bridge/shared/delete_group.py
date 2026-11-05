"""
Which of a body's vertices a garment should hide, and how the result stands.

**A delete group fails in two opposite ways**
([FR 051](../../../feature-requests/done/051-delete-groups/README.md)). Too small, and skin pokes
through on another body or in a pose. Too large, and dark slits open where someone can see in
through an opening. At the gi's V-neck a fixed margin was wrong both ways, 3.5 cm leaving slits
inside the lapel and 7.5 cm leaving skin poking through the coat, and the group took eleven runs
of a script. This is that script's algorithm with its hard-coded openings replaced by a reading of
the garment, and :data:`DEFAULT_MARGINS` and the constants below it are the script's numbers.

**A boundary loop is not always an opening.** Two questions come first, for each of its vertices,
and neither was in the request; the spike found both ("The spike" in the request's Outcome). Is
there garment between it and the skin? A button's rim and a jacket's front edge over a shirt have
some. Can it see open air? A waistband under a coat and the under flap of a V cannot. A vertex
that answers no to the first and yes to the second is *open*, and only an open edge sets a margin
or a sight zone. The gi's script did this by hand, with ``z > 1.24`` on the V and a comment on why.

**What is left is classified by what goes through it.** A loop an arm passes through is a ``cuff``
and one a leg passes through a ``hem``, because the limb moves inside it and a margin decides; any
other is ``trunk``, a neck, an armhole or a keyhole, where the body stays still relative to the
opening and what can be seen decides. "Goes through" is a winding number around where the chain
built from the ``joint-*`` helper groups crosses the loop's own plane, and needs no rig. The spike
compared it with the two the request proposed, and it alone was right on all 24 loops: how loose the
opening is fails on a fitted trouser hem, whose gap is that of a neck, and rig weights call a
sleeveless armhole a cuff and need a rig the gi did not have. **An arm's chain starts at the shoulder joint**, so that an
armhole is not a cuff: an arm that rises takes the armhole's skin with it.

**A closed shell has no boundary**, as gloves, boots and some shirts do, so nothing says where its
openings are and no margin applies. Skin under one is sight-tested wherever it is, which errs
toward keeping skin, and ``closed_components`` says so.

**An authoring body and a loaded asset mask differently.** On the authoring body a Mask modifier
removes any face touching a member. When MPFB loads an asset, ``ClothesService._conservative_mask()``
first removes members of a partly covered face, moving the boundary inward by about a ring. The group
that looks right in the authoring scene is not the one the next character gets, so the request's
two counts are of the second (:func:`as_loaded`), and a third is of the first (:func:`measure`).

**Everything is in the body's own frame**, its rotation and location undone, so that a turned or
moved character gets the same group: the sight lines are a fixed set of directions, and fixed in
the world they would differ with a turn. **A posed one would not**, since the skin moves against the
garment's fit, and the command refuses that.

**Read with every mask and subdivision off, helper mask included**, unlike
:func:`mesh_overlap.masks_off`: a group's indices are the mesh's, and the evaluated mesh only has
them while nothing removes or adds a vertex.

Plain Blender, like :mod:`mesh_overlap`, with no ``services``: what a body is, and whose, is the
command's to ask MPFB.
"""

__all__ = (
    "BODY_GROUP",
    "DEFAULT_MARGINS",
    "JOINT_PREFIX",
    "KIND_CUFF",
    "KIND_HEM",
    "KIND_TRUNK",
    "KIND_COVERED",
    "Opening",
    "Reading",
    "as_loaded",
    "boundary_edges",
    "boundary_loops",
    "distance_to_segments",
    "generate",
    "limbs_through",
    "measure",
    "openings_of",
    "read",
    "rounded_centre",
    "sight_lines",
    "stripped",
    "vertex_normals",
)

import contextlib
import math

import bpy
import numpy
from mathutils import Matrix
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import character_frame
from . import mesh_overlap

KIND_CUFF = "cuff"
KIND_HEM = "hem"
KIND_TRUNK = "trunk"
KIND_COVERED = "covered"

# How much skin stays in play beside an open edge of each kind, in metres. From the gi:
# 7 cm for a limb moving inside a wide sleeve, 16 cm inside a trouser leg, and at a neck only
# what the sight lines might miss between one ring of vertices and the next.
DEFAULT_MARGINS = {KIND_TRUNK: 0.012, KIND_CUFF: 0.07, KIND_HEM: 0.16}

# How far a body vertex's normal may travel to a garment and still be under it.
_MAX_GAP = 0.14
# How far from a trunk opening anything can see in through it. Beyond this nothing is tested.
_SIGHT_ZONE = 0.20
# How many directions a sight line can take. A Fibonacci sphere, so the same every time.
_SIGHT_LINE_COUNT = 240
# A sight line grazing the skin more steeply than this does not count. 0.35 is about 20 degrees.
_MIN_FACING = 0.35
# A sight line that has met nothing after this far has reached open air.
_SIGHT_LINE_LENGTH = 1.0
# Rings of skin kept around anything visible, since a mask takes the whole face.
_COLLAR_RINGS = 3
# Passes of the hole filling. The second catches what the first's additions enclosed.
_HOLE_FILL_PASSES = 2
# Off a surface before a ray starts, in metres, so that it does not hit where it started.
_RAY_START = 0.001
# A body vertex this close to an edge's nearest skin has no room for a layer in between.
_TOUCHING = 1e-5

# Which vertex group says what is skin (HumanService.create_human).
BODY_GROUP = "body"
JOINT_PREFIX = "joint-"

# The limbs a loop can be a cuff or a hem of, each from where it starts to move on its own.
_LIMB_CHAINS = {
    "left arm": ("joint-l-shoulder", "joint-l-elbow", "joint-l-hand", "joint-l-hand-3"),
    "right arm": ("joint-r-shoulder", "joint-r-elbow", "joint-r-hand", "joint-r-hand-3"),
    "left leg": ("joint-l-upper-leg", "joint-l-knee", "joint-l-ankle", "joint-l-foot-2"),
    "right leg": ("joint-r-upper-leg", "joint-r-knee", "joint-r-ankle", "joint-r-foot-2"),
}

_TOPOLOGY_MODIFIERS = ("MASK", "SUBSURF")


class Reading:
    """The body and the garment as one call needs them, in the body's own frame.

    ``body_tree`` holds the skin alone. ``corner_vertices``, ``face_starts`` and ``face_sizes``
    are the body's polygons, and ``skin_faces`` says which have no helper vertex in them.
    ``garment_component`` is each garment triangle's connected component, and ``closed``
    which of those have no boundary.
    """

    __slots__ = ("points", "normals", "is_skin", "joints", "neighbours", "corner_vertices",
                 "face_starts", "face_sizes", "skin_faces", "body_tree", "garment_points",
                 "garment_triangles", "garment_tree", "garment_closed_triangle", "frame",
                 "closed_component_sizes", "loops", "memberships")

    def members(self, group_index):
        """A vertex group's members, as a bool per vertex."""
        members = numpy.zeros(len(self.points), dtype=bool)
        rows = self.memberships
        members[rows[rows[:, 1] == group_index, 0]] = True
        return members


class Opening:
    """One boundary loop as classified. See this module's docstring."""

    __slots__ = ("kind", "reason", "margin", "limbs", "centre", "vertices", "perimeter",
                 "open_share", "edges", "kept_by_margin")

    def __init__(self, kind, reason, margin, limbs, centre, vertices, perimeter, open_share, edges):
        self.kind = kind
        self.reason = reason
        self.margin = margin
        self.limbs = limbs
        self.centre = centre
        self.vertices = vertices
        self.perimeter = perimeter
        self.open_share = open_share
        self.edges = edges
        self.kept_by_margin = 0


def sight_lines():
    """The fixed directions a sight line can take, as ``(array, vectors)``."""
    rows = []
    for index in range(_SIGHT_LINE_COUNT):
        height = 1.0 - 2.0 * (index + 0.5) / _SIGHT_LINE_COUNT
        radius = math.sqrt(1.0 - height * height)
        angle = index * math.pi * (3.0 - math.sqrt(5.0))
        rows.append((radius * math.cos(angle), radius * math.sin(angle), height))
    return (numpy.array(rows, dtype=numpy.float64), [Vector(row) for row in rows])


@contextlib.contextmanager
def stripped(blender_objects):
    """Run the block with these meshes' masks and subdivision off, and put back exactly those.

    Every mask, the helper mask too (see this module's docstring). The restore is in a
    ``finally`` that covers turning them off, as in :func:`mesh_overlap.masks_off`.
    """
    turned_off = []
    try:
        for blender_object in blender_objects:
            for modifier in blender_object.modifiers:
                if modifier.type in _TOPOLOGY_MODIFIERS and modifier.show_viewport:
                    modifier.show_viewport = False
                    turned_off.append(modifier)
        if turned_off:
            bpy.context.view_layer.update()
        yield
    finally:
        for modifier in turned_off:
            modifier.show_viewport = True
        if turned_off:
            bpy.context.view_layer.update()


def _frame_of(body):
    """The world-to-body matrix, as a rotation and a location with no scale in it."""
    location, rotation, _scale = body.matrix_world.decompose()
    return Matrix.LocRotScale(location, rotation, None)


def _into(points, matrix):
    array = numpy.array(matrix, dtype=numpy.float64)
    return points @ array[:3, :3].T + array[:3, 3]


def vertex_normals(points, triangles):
    """Area-weighted vertex normals, for a mesh whose indices must not be disturbed."""
    corners = points[triangles]
    faces = numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    normals = numpy.zeros_like(points)
    for column in range(3):
        numpy.add.at(normals, triangles[:, column], faces)
    lengths = numpy.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0.0] = 1.0
    return normals / lengths


def _neighbours_of(mesh):
    """Per vertex, the vertices one edge away."""
    pairs = numpy.empty(len(mesh.edges) * 2, dtype=numpy.int32)
    mesh.edges.foreach_get("vertices", pairs)
    neighbours = [[] for _vertex in range(len(mesh.vertices))]
    for first, second in pairs.reshape(-1, 2).tolist():
        neighbours[first].append(second)
        neighbours[second].append(first)
    return neighbours


def _polygons_of(mesh):
    """``(corner vertices, face starts, face sizes)`` of a mesh's polygons."""
    corners = numpy.empty(len(mesh.loops), dtype=numpy.int32)
    mesh.loops.foreach_get("vertex_index", corners)
    starts = numpy.empty(len(mesh.polygons), dtype=numpy.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    sizes = numpy.empty(len(mesh.polygons), dtype=numpy.int32)
    mesh.polygons.foreach_get("loop_total", sizes)
    return (corners, starts, sizes)


def _joints_of(body, reading):
    """Each ``joint-*`` group's centre, which is where the helper cube around it is."""
    joints = dict()
    for group in body.vertex_groups:
        if group.name.startswith(JOINT_PREFIX):
            members = reading.members(group.index)
            if members.any():
                joints[group.name] = reading.points[members].mean(axis=0)
    return joints


def _connected_triangles(triangles, vertex_count):
    """Each triangle's connected component, as an array of labels."""
    parent = numpy.arange(vertex_count)

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first, second, third in triangles.tolist():
        low = root(first)
        for other in (second, third):
            high = root(other)
            if high != low:
                parent[high] = low
    return numpy.array([root(first) for first in triangles[:, 0].tolist()], dtype=numpy.int64)


def boundary_edges(triangles):
    """The edges only one triangle has, as an array of two sorted index columns.

    From triangles rather than polygons, since an n-gon's diagonals have two.
    """
    edges = numpy.sort(triangles[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    unique, counts = numpy.unique(edges, axis=0, return_counts=True)
    return unique[counts == 1]


def boundary_loops(edges):
    """Each boundary loop, as a list of vertex indices in order around it."""
    around = dict()
    for first, second in edges.tolist():
        around.setdefault(first, []).append(second)
        around.setdefault(second, []).append(first)
    seen = set()
    loops = []
    for start in sorted(around):
        for onward in around[start]:
            if (min(start, onward), max(start, onward)) in seen:
                continue
            seen.add((min(start, onward), max(start, onward)))
            loop = [start]
            current = onward
            while current != start:
                loop.append(current)
                following = [vertex for vertex in around[current]
                             if (min(current, vertex), max(current, vertex)) not in seen]
                if not following:
                    break
                seen.add((min(current, following[0]), max(current, following[0])))
                current = following[0]
            loops.append(loop)
    return loops


def read(body, garment):
    """Both meshes, stripped and in the body's frame, as a :class:`Reading`.

    Returns ``(reading, refusal)``. ``refusal`` is ``(blocked_by, sentence)`` for a mesh that
    cannot be read this way: nothing else here knows what to say about one.
    """
    reading = Reading()
    with stripped((body, garment)):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for blender_object in (body, garment):
            if not blender_object.evaluated_get(depsgraph).is_evaluated:
                return (None, ("mesh_not_evaluated",
                               "'{:s}' is in an excluded collection or has hide_viewport on, so "
                               "Blender has no evaluated geometry for it.".format(
                                   blender_object.name)))
        surface = mesh_overlap.read_surface(body, depsgraph, with_groups=True)
        garment_surface = mesh_overlap.read_surface(garment, depsgraph)
    if garment_surface is None:
        return (None, ("garment_has_no_faces", "'{:s}' has no faces.".format(garment.name)))
    mesh = body.data
    if surface is None or len(surface.vertices) != len(mesh.vertices):
        return (None, ("body_topology_changed",
                       "'{:s}' evaluates to a different vertex count from its mesh with its masks "
                       "and subdivision off, so another modifier adds or removes vertices and a "
                       "group's indices would not address them.".format(body.name)))
    reading.frame = _frame_of(body)
    to_body = reading.frame.inverted()
    reading.points = _into(surface.vertices, to_body)
    reading.normals = vertex_normals(reading.points, surface.triangles)
    reading.neighbours = _neighbours_of(mesh)
    reading.corner_vertices, reading.face_starts, reading.face_sizes = _polygons_of(mesh)
    reading.memberships = surface.memberships
    reading.joints = _joints_of(body, reading)
    reading.is_skin = reading.members(body.vertex_groups[BODY_GROUP].index)
    all_skin = numpy.logical_and.reduceat(reading.is_skin[reading.corner_vertices],
                                          reading.face_starts)
    reading.skin_faces = all_skin
    skin_triangles = surface.triangles[reading.is_skin[surface.triangles].all(axis=1)]
    reading.body_tree = BVHTree.FromPolygons(
        reading.points.tolist(), skin_triangles.tolist(), all_triangles=True)

    reading.garment_points = _into(garment_surface.vertices, to_body)
    reading.garment_triangles = garment_surface.triangles
    reading.garment_tree = BVHTree.FromPolygons(
        reading.garment_points.tolist(), reading.garment_triangles.tolist(), all_triangles=True)
    edges = boundary_edges(reading.garment_triangles)
    reading.loops = boundary_loops(edges)
    components = _connected_triangles(reading.garment_triangles, len(reading.garment_points))
    open_vertices = numpy.zeros(len(reading.garment_points), dtype=bool)
    open_vertices[edges.reshape(-1)] = True
    has_boundary = set(components[open_vertices[reading.garment_triangles].any(axis=1)].tolist())
    closed_labels = sorted(set(components.tolist()) - has_boundary)
    reading.garment_closed_triangle = numpy.isin(components, closed_labels)
    reading.closed_component_sizes = sorted(
        (int(len(numpy.unique(reading.garment_triangles[components == label])))
         for label in closed_labels), reverse=True)
    return (reading, None)


def _winding_number(point, polygon):
    """How many times a 2D polygon goes around a 2D point."""
    first = polygon - point
    second = numpy.roll(first, -1, axis=0)
    cross = first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]
    dot = (first * second).sum(axis=1)
    return numpy.arctan2(cross, dot).sum() / (2.0 * math.pi)


def limbs_through(loop_points, joints):
    """The limbs whose chain crosses this loop's best-fit plane inside the loop."""
    centre = loop_points.mean(axis=0)
    _unused, _values, axes = numpy.linalg.svd(loop_points - centre)
    plane = axes[:2]
    normal = axes[2]
    polygon = (loop_points - centre) @ plane.T
    limbs = []
    for limb, names in _LIMB_CHAINS.items():
        path = [joints[name] for name in names if name in joints]
        for first, second in zip(path, path[1:]):
            side_first = (first - centre) @ normal
            side_second = (second - centre) @ normal
            if side_first * side_second >= 0.0:
                continue
            crossing = first + (second - first) * (side_first / (side_first - side_second))
            if abs(_winding_number(plane @ (crossing - centre), polygon)) > 0.5:
                limbs.append(limb)
                break
    return limbs


def _escapes(tree, origin, normal, line_array, line_vectors):
    """Whether a sight line from ``origin``, facing away from ``normal``, meets no garment."""
    for index in numpy.flatnonzero(line_array @ normal >= _MIN_FACING).tolist():
        line = line_vectors[index]
        if tree.ray_cast(origin + line * _RAY_START, line, _SIGHT_LINE_LENGTH)[0] is None:
            return True
    return False


def _open_vertices(reading, loop, lines):
    """For each vertex of a loop, ``(reaches skin, sees open air)``. See this module's docstring."""
    reaches = []
    exposed = []
    for point in reading.garment_points[loop].tolist():
        origin = Vector(point)
        location, normal, _index, distance = reading.body_tree.find_nearest(origin)
        if location is None:
            reaches.append(False)
            exposed.append(False)
            continue
        if distance <= _TOUCHING:
            reaches.append(True)
        else:
            toward = (location - origin).normalized()
            reaches.append(reading.garment_tree.ray_cast(
                origin + toward * _RAY_START, toward, max(distance - 2.0 * _RAY_START, 0.0))[0]
                is None)
        exposed.append(_escapes(reading.garment_tree, origin, numpy.array(normal),
                                lines[0], lines[1]))
    return (numpy.array(reaches, dtype=bool), numpy.array(exposed, dtype=bool))


def _named(limbs):
    if set(limbs) == {"left leg", "right leg"}:
        return "both legs pass"
    if set(limbs) == {"left arm", "right arm"}:
        return "both arms pass"
    return "the {:s} passes".format(" and the ".join(limbs))


def _classified(limbs, margins):
    """``(kind, reason, margin)`` for a loop with something open in it."""
    if any("arm" in limb for limb in limbs):
        return (KIND_CUFF, "Open, and {:s} through it, moving inside it, so a margin decides.".format(
            _named(limbs)), margins[KIND_CUFF])
    if any("leg" in limb for limb in limbs):
        return (KIND_HEM, "Open, and {:s} through it, moving inside it, so a margin decides.".format(
            _named(limbs)), margins[KIND_HEM])
    return (KIND_TRUNK, "Open, and no limb passes through it, so the body stays still against it "
                        "and what can be seen decides.", margins[KIND_TRUNK])


def openings_of(reading, margins, lines=None):
    """Every boundary loop as an :class:`Opening`, the covered ones with their reason."""
    lines = lines or sight_lines()
    openings = []
    from_body = numpy.array(reading.frame, dtype=numpy.float64)
    for loop in reading.loops:
        loop_points = reading.garment_points[loop]
        reaches, exposed = _open_vertices(reading, loop, lines)
        is_open = reaches & exposed
        limbs = limbs_through(loop_points, reading.joints)
        if is_open.any():
            kind, reason, margin = _classified(limbs, margins)
        else:
            kind, reason, margin = (KIND_COVERED, _covered_reason(reaches, exposed), 0.0)
        following = numpy.roll(numpy.arange(len(loop)), -1)
        open_edges = is_open | is_open[following]
        edges = numpy.stack((loop_points[open_edges], loop_points[following][open_edges]), axis=1)
        perimeter = float(numpy.linalg.norm(loop_points - loop_points[following], axis=1).sum())
        centre_points = loop_points[is_open] if is_open.any() else loop_points
        centre = centre_points.mean(axis=0) @ from_body[:3, :3].T + from_body[:3, 3]
        openings.append(Opening(kind, reason, margin, limbs, centre, len(loop), perimeter,
                                float(is_open.mean()), edges))
    openings.sort(key=lambda opening: -opening.perimeter)
    return openings


def _covered_reason(reaches, exposed):
    """Why a loop has no open vertex, in the words of what is true of most of it."""
    if not reaches.any():
        return "Another layer lies between all of it and the skin, so it opens onto no skin."
    if not exposed.any():
        return "Another layer covers all of it, so nothing can be seen through it."
    return ("No part of it both reaches the skin and can see open air: it lies over another layer "
            "where it shows, and under one where it does not.")


def distance_to_segments(points, segments):
    """Per point, the distance to the nearest of ``segments``, an array of ``(n, 2, 3)``."""
    distances = numpy.full(len(points), numpy.inf)
    if len(segments) == 0 or len(points) == 0:
        return distances
    starts = segments[:, 0]
    spans = segments[:, 1] - starts
    lengths = numpy.maximum((spans * spans).sum(axis=1), 1e-12)
    for begin in range(0, len(points), 512):
        chunk = points[begin:begin + 512]
        offsets = chunk[:, None, :] - starts[None, :, :]
        along = numpy.clip((offsets * spans[None, :, :]).sum(axis=2) / lengths[None, :], 0.0, 1.0)
        nearest = offsets - along[:, :, None] * spans[None, :, :]
        distances[begin:begin + 512] = numpy.sqrt((nearest * nearest).sum(axis=2).min(axis=1))
    return distances


def _segments_of_kind(openings, kind):
    rows = [opening.edges for opening in openings if opening.kind == kind and len(opening.edges)]
    return numpy.concatenate(rows) if rows else numpy.empty((0, 2, 3))


def _under_garment(reading, candidates):
    """``(vertices under the garment, whether what they hit is a closed shell)``."""
    under = []
    closed = []
    tree = reading.garment_tree
    points = reading.points
    normals = reading.normals
    for vertex in candidates.tolist():
        normal = Vector(normals[vertex])
        hit = tree.ray_cast(Vector(points[vertex]) + normal * (_RAY_START / 2.0), normal, _MAX_GAP)
        if hit[0] is not None:
            under.append(vertex)
            closed.append(bool(reading.garment_closed_triangle[hit[2]]))
    return (numpy.array(under, dtype=numpy.int64), numpy.array(closed, dtype=bool))


def _grown(seeds, neighbours, rings):
    """``seeds`` and everything within ``rings`` edges of them."""
    reached = set(seeds)
    frontier = set(seeds)
    for _ring in range(rings):
        frontier = set(other for vertex in frontier for other in neighbours[vertex]) - reached
        reached |= frontier
    return reached


def _filled(reading, base, under, kept_clear):
    """``under`` with single-vertex holes filled, each of which would leave faces standing."""
    covered = base | under
    neighbours = reading.neighbours
    for _unused in range(_HOLE_FILL_PASSES):
        holes = []
        for vertex in numpy.flatnonzero(reading.is_skin & ~covered).tolist():
            around = neighbours[vertex]
            if vertex in kept_clear or not around:
                continue
            if sum(1 for other in around if covered[other]) >= len(around) - 1:
                holes.append(vertex)
        covered[holes] = True
    return covered


def generate(reading, base, margins):
    """The new membership, as a bool per vertex, and the openings it was worked out from.

    ``base`` is the members that stay whatever is found, as a bool per vertex. What is under the
    garment, less what a margin keeps; a collar around everything in a sight zone that can be
    seen; then the single-vertex holes.

    **A vertex a margin keeps is still tested, and grows a collar if it is seen.** The gi's script
    measured a margin to each edge's midpoint and tested whatever that let through. Measured to
    the edge, as here, nearly everything beside a lapel was kept untested, grew no collar, and
    black wedges opened on the chest while every count stayed where it was.
    """
    lines = sight_lines()
    openings = openings_of(reading, margins, lines)
    candidates = numpy.flatnonzero(reading.is_skin & ~base)
    under, closed = _under_garment(reading, candidates)

    keep = numpy.zeros(len(under), dtype=bool)
    for kind in (KIND_TRUNK, KIND_CUFF, KIND_HEM):
        for opening in (row for row in openings if row.kind == kind):
            near = distance_to_segments(reading.points[under], opening.edges) <= opening.margin
            opening.kept_by_margin = int((near & ~keep).sum())
            keep |= near

    trunk_edges = _segments_of_kind(openings, KIND_TRUNK)
    in_zone = closed | (distance_to_segments(reading.points[under], trunk_edges) <= _SIGHT_ZONE)
    seen = []
    for vertex, position in zip(under.tolist(), range(len(under))):
        if not in_zone[position]:
            continue
        normal = reading.normals[vertex]
        if _escapes(reading.garment_tree,
                    Vector(reading.points[vertex]) + Vector(normal) * _RAY_START, normal,
                    lines[0], lines[1]):
            seen.append(vertex)
    kept_clear = _grown(seen, reading.neighbours, _COLLAR_RINGS)

    covered = numpy.zeros(len(reading.points), dtype=bool)
    chosen = [vertex for vertex, kept in zip(under.tolist(), keep.tolist())
              if not kept and vertex not in kept_clear]
    covered[chosen] = True
    return (_filled(reading, base, covered, kept_clear), openings)


def as_loaded(reading, members):
    """What a character gets of a group once its asset is loaded, as a bool per vertex.

    ``ClothesService._conservative_mask()``: every member of a face only partly covered goes, in
    one pass. **Not quite every one, and the reason is two defects meeting.** ``Mhclo.load()`` reads
    the ``a - b`` ranges ``write_mhclo()`` wrote and appends ``a`` twice, and
    ``_conservative_mask()`` removes one occurrence per partly covered face, so a vertex starting
    a run of consecutive indices survives one such face. The gi's 3,209 members leave 2,698 on a
    character where the rule alone says 2,680. Reproduced, because this is what the count claims
    to be about, and held to MPFB's own functions by the bridge's tests.
    """
    corners = members[reading.corner_vertices]
    any_member = numpy.logical_or.reduceat(corners, reading.face_starts)
    every_member = numpy.logical_and.reduceat(corners, reading.face_starts)
    partly = numpy.repeat(any_member & ~every_member, reading.face_sizes)
    partly_covered_faces = numpy.zeros(len(members), dtype=numpy.int64)
    numpy.add.at(partly_covered_faces, reading.corner_vertices[partly], 1)
    run_starts = members & ~numpy.concatenate(((False,), members[:-1]))
    return members.astype(numpy.int64) + run_starts > partly_covered_faces


def _face_centres_and_normals(reading, faces):
    """The centre and area-weighted normal of each of ``faces``, indices into the polygons."""
    centres = []
    normals = []
    points = reading.points
    for face in faces.tolist():
        start = reading.face_starts[face]
        corners = points[reading.corner_vertices[start:start + reading.face_sizes[face]]]
        centres.append(corners.mean(axis=0))
        fan = numpy.cross(corners[1:-1] - corners[0], corners[2:] - corners[0]).sum(axis=0)
        length = numpy.linalg.norm(fan)
        normals.append(fan / length if length > 0.0 else fan)
    return (centres, normals)


def _in_front_of_garment(tree, centre, normal):
    """Whether the garment's nearest point is on a face's outward side.

    Skin with the garment behind it has poked through, and removing it shows the garment, so it
    is what a mask is for. It sees open air from every direction, and on the gi's back it was
    most of what a sight line alone called a slit.
    """
    nearest = tree.find_nearest(centre)[0]
    return nearest is not None and (nearest - centre).dot(normal) > 0.0


def _slits(reading, removed, near_edges, lines):
    """How many of the ``removed`` skin faces are slits. See :func:`measure`."""
    tree = reading.garment_tree
    count = 0
    faces = numpy.flatnonzero(removed & reading.skin_faces)
    centres, normals = _face_centres_and_normals(reading, faces)
    near = distance_to_segments(numpy.array(centres).reshape(-1, 3), near_edges) <= _SIGHT_ZONE
    for centre, normal, is_near in zip(centres, normals, near.tolist()):
        direction = Vector(normal)
        origin = Vector(centre)
        if not is_near:
            hit = tree.ray_cast(origin + direction * (_RAY_START / 2.0), direction, _MAX_GAP)
            if hit[0] is None or not reading.garment_closed_triangle[hit[2]]:
                continue
        if (_escapes(tree, origin + direction * _RAY_START, normal, lines[0], lines[1])
                and _in_front_of_garment(tree, origin, direction)):
            count += 1
    return count


def measure(reading, members, openings):
    """``(slits as loaded, skin left under the garment, slits on this body)``, in faces.

    With the algorithm's sight lines, from each face's centre. A Mask modifier removes any face
    touching a member.

    A slit is removed skin with the garment in front of it that a sight line reaches. **Only within
    :data:`_SIGHT_ZONE` of an open edge**, or under a closed shell, because a line of sight far up a
    trouser leg needs an eye on the floor.

    **Slits are counted twice, because a group has two lives.** The first count is on what the
    loaded asset masks (:func:`as_loaded`), about a ring less, which is what the next character
    gets. The third is on the group as it stands, which is what a Mask modifier shows on this
    body, and the first cannot see what it finds: on the gi, wedges on the authoring body's chest
    changed the first count by nothing. The second count is on the loaded asset too, and is standing
    skin the garment covers and no sight line reaches, which includes what a limb's margin keeps on
    purpose. Each opening's ``kept_by_margin`` says how much of that is.
    """
    lines = sight_lines()
    loaded = as_loaded(reading, members)
    removed = numpy.logical_or.reduceat(loaded[reading.corner_vertices], reading.face_starts)
    open_rows = [opening.edges for opening in openings if len(opening.edges) > 0]
    open_edges = numpy.concatenate(open_rows) if open_rows else numpy.empty((0, 2, 3))

    loaded_slits = _slits(reading, removed, open_edges, lines)
    authoring_slits = _slits(
        reading, numpy.logical_or.reduceat(members[reading.corner_vertices], reading.face_starts),
        open_edges, lines)

    tree = reading.garment_tree
    still_under = 0
    standing_faces = numpy.flatnonzero(~removed & reading.skin_faces)
    for centre, normal in zip(*_face_centres_and_normals(reading, standing_faces)):
        direction = Vector(normal)
        origin = Vector(centre)
        if tree.ray_cast(origin + direction * (_RAY_START / 2.0), direction, _MAX_GAP)[0] is None:
            continue
        if not _escapes(tree, origin + direction * _RAY_START, normal, lines[0], lines[1]):
            still_under += 1
    return (loaded_slits, still_under, authoring_slits)


def rounded_centre(opening):
    """An opening's centre as ``{x, y, z}``, rounded the way every position here is."""
    return dict((axis, character_frame.rounded_metres(value))
                for axis, value in zip(("x", "y", "z"), opening.centre))
