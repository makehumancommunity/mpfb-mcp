"""
How much two meshes intersect and how close they come, and the masks that hide it.

**One measurement, exposed three ways**
([FR 048](../../../feature-requests/done/048-measuring-mesh-assets/README.md)):
``check_intersections`` answers it for any pairs, ``add_asset`` for the asset it
just equipped, and :mod:`mesh_asset_report` for a mesh's connected components.
Three copies would disagree, and the gi session's own script shows how: it read
one mesh in local coordinates before modifiers and the other evaluated.

**The geometry is the evaluated mesh in world space**, so a posed or placed
character measures as it stands. What is evaluated is what the viewport draws,
and MPFB adds Subdivision at viewport level 0 and render level 1, so what is
counted is not necessarily what renders. That is why :class:`Reading` carries
the level it was measured at.

**A count is of triangles, which is why it is a measure of extent and not of
faces.** Trees are built from the evaluated mesh's loop triangles, so a quad
counts as two. The tools call the unit "face pairs", since that is what the
number is read as and the difference is a factor, not a kind.

**A body is read twice, because a count on a masked body is blind.** A delete
group's mask takes the skin under a garment out of the evaluated mesh, so the
body's count goes to zero exactly where a garment passes through it on the next
character: the gi session's ``coat/body`` stayed at 0 while skin poked through,
and the same finished garment scores 6 pairs against the masked body and 613
against the unmasked one while rendering cleanly. Neither number is judged. So
``face_pairs`` is the masks as they are and ``face_pairs_unmasked`` is every mask
off **except the one that hides helper geometry**, which is not skin and would
swamp the count.

**That mask is found by what it does, not by its name**
(:func:`is_helper_mask`): a ``MASK`` on the vertex group ``body``, not inverted.
The request said "by its ``vertex_group`` being ``body``", and that alone is not
enough. A proxied character's basemesh carries ``Hide base mesh`` on the same
group, inverted, as ``add_asset``'s ``_hides_the_base_mesh`` already had to
learn. It hides the skin and leaves nothing, so it comes off with the delete
groups, and "unmasked" means the body the garment was fitted to.

**Masks are put back exactly, however the block ends** (:func:`masks_off`). Only
a mask this module turned off is turned on again, so one a user had already
disabled stays disabled, and the depsgraph is updated on the way in and on the
way out, since a read after the restore would otherwise see the unmasked mesh.

**``min_distance`` is an upper bound.** It is the nearest any vertex of either
mesh comes to the other's surface, and two surfaces can come closer at an edge
crossing an edge. For meshes this dense that is a small difference, and the
tool's description says so. It is ``0.0`` when they intersect, without being
measured, since the walk is the expensive part and the answer is already known.

**A self-overlap excludes faces that share a vertex**, or every neighbouring pair
would count.

**A mesh Blender does not evaluate is not read.** An object in an excluded
collection or with ``hide_viewport`` on has no evaluated geometry, and
``evaluated_get()`` quietly hands back the original, whose mesh would be measured
without its modifiers, so it is reported as not measured instead. One hidden only
with the eye icon is evaluated and is measured, measured on a live file rather
than assumed, unlike ``placement.footprint``, whose question is what is drawn. A
body reduced to nothing by its masks is read and has ``masked`` ``None``.

Plain Blender apart from :func:`bodies_among` and :func:`family_of`, which ask
MPFB what a body is and whose character this is, and take ``services`` for it.
"""

__all__ = (
    "Reading",
    "Surface",
    "Unmeasured",
    "bodies_among",
    "body_masks",
    "box_of",
    "closest_approach",
    "family_of",
    "is_helper_mask",
    "masks_off",
    "overlapping_triangles",
    "pair_row",
    "read_all",
    "read_surface",
    "region_of",
    "viewport_subdiv_levels",
)

import collections
import contextlib

import bpy
import numpy
from mathutils.bvhtree import BVHTree

from . import blender_data
from . import character_frame
from . import placement

_AXIS_NAMES = ("x", "y", "z")

# The vertex group of MPFB's "Hide helpers" mask (HumanService.create_human).
_HELPER_MASK_GROUP = "body"

# A mesh that was not measured, and why. See read_all().
Unmeasured = collections.namedtuple("Unmeasured", ("object_name", "reason"))


class Surface:
    """One mesh's evaluated triangles, in world space, and a tree built on first use.

    ``polygons`` is each triangle's evaluated polygon and ``memberships`` the
    ``(vertex, group)`` rows of the evaluated mesh's vertex groups. Both are
    ``None`` unless they were asked for, since only a per-component report reads
    them. The bounds are worked out once, because one surface meets many others.
    """

    __slots__ = ("vertices", "triangles", "polygons", "memberships", "low", "high",
                 "_triangle_low", "_triangle_high", "_tree")

    def __init__(self, vertices, triangles, polygons=None, memberships=None):
        self.vertices = vertices
        self.triangles = triangles
        self.polygons = polygons
        self.memberships = memberships
        self.low = vertices.min(axis=0)
        self.high = vertices.max(axis=0)
        self._triangle_low = None
        self._triangle_high = None
        self._tree = None

    def triangles_touching(self, low, high):
        """The indices of the triangles whose own box meets this one."""
        if self._triangle_low is None:
            corners = self.vertices[self.triangles]
            self._triangle_low = corners.min(axis=1)
            self._triangle_high = corners.max(axis=1)
        return numpy.flatnonzero(((self._triangle_low <= high) & (self._triangle_high >= low))
                                 .all(axis=1))

    @property
    def tree(self):
        """The BVH tree over the triangles, built once."""
        if self._tree is None:
            self._tree = BVHTree.FromPolygons(
                self.vertices.tolist(), self.triangles.tolist(), all_triangles=True)
        return self._tree

    def triangles_inside(self, box):
        """Per triangle, whether its centre lies in ``box``; all true when ``box`` is ``None``."""
        if box is None:
            return numpy.ones(len(self.triangles), dtype=bool)
        return _inside(self.vertices[self.triangles].mean(axis=1), box)

    def vertices_inside(self, box):
        """The world coordinates of the vertices in ``box``, or all of them."""
        if box is None:
            return self.vertices
        return self.vertices[_inside(self.vertices, box)]


class Reading:
    """One mesh as measured: how it stands, and without its masks when it is a body.

    ``unmasked`` is the very same :class:`Surface` as ``masked`` when nothing
    differs, which is how a row knows that it need not count twice.
    """

    __slots__ = ("object_name", "is_body", "subdiv_levels", "masked", "unmasked")

    def __init__(self, object_name, is_body, subdiv_levels, masked, unmasked):
        self.object_name = object_name
        self.is_body = is_body
        self.subdiv_levels = subdiv_levels
        self.masked = masked
        self.unmasked = unmasked


def _inside(points, box):
    """Per point, whether it lies in ``box``, whose axes may be left open."""
    keep = numpy.ones(len(points), dtype=bool)
    for bound, compare in (("min", numpy.greater_equal), ("max", numpy.less_equal)):
        for index, axis in enumerate(_AXIS_NAMES):
            limit = box.get(bound, {}).get(axis)
            if limit is not None:
                keep &= compare(points[:, index], limit)
    return keep


def is_helper_mask(modifier):
    """Whether this is the mask that hides helper geometry. See this module's docstring."""
    return (modifier.type == "MASK"
            and str(modifier.vertex_group) == _HELPER_MASK_GROUP
            and not modifier.invert_vertex_group)


def body_masks(blender_object):
    """The masks hiding part of this body right now: every enabled one but the helper mask."""
    return [modifier for modifier in blender_object.modifiers
            if modifier.type == "MASK" and modifier.show_viewport
            and not is_helper_mask(modifier)]


@contextlib.contextmanager
def masks_off(blender_objects):
    """Run the block with these bodies' masks off, and put back exactly those.

    The restore is in a ``finally`` that covers turning them off too, so that a
    failure half way through the list leaves nothing behind.
    """
    turned_off = []
    try:
        for blender_object in blender_objects:
            for modifier in body_masks(blender_object):
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


def viewport_subdiv_levels(blender_object):
    """How many subdivision levels the viewport evaluates on this object; 0 with no modifier."""
    return sum(int(modifier.levels) for modifier in blender_object.modifiers
               if modifier.type == "SUBSURF" and modifier.show_viewport)


def _memberships_of(mesh):
    """The evaluated mesh's ``(vertex, group)`` rows, as an array of two columns."""
    rows = [(vertex.index, element.group) for vertex in mesh.vertices
            for element in vertex.groups]
    return numpy.array(rows, dtype=numpy.int64).reshape(-1, 2)


def read_surface(blender_object, depsgraph, with_groups=False):
    """This mesh's evaluated triangles in world space, or ``None`` when it has none.

    ``with_groups`` also reads which polygon each triangle is and the vertex groups.
    """
    evaluated = blender_object.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        triangle_count = len(mesh.loop_triangles)
        if triangle_count == 0:
            return None
        vertex_count = len(mesh.vertices)
        local = numpy.empty(vertex_count * 3, dtype=numpy.float32)
        mesh.vertices.foreach_get("co", local)
        triangles = numpy.empty(triangle_count * 3, dtype=numpy.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles)
        polygons = None
        memberships = None
        if with_groups:
            polygons = numpy.empty(triangle_count, dtype=numpy.int32)
            mesh.loop_triangles.foreach_get("polygon_index", polygons)
            memberships = _memberships_of(mesh)
        matrix = numpy.array(evaluated.matrix_world, dtype=numpy.float64)
    finally:
        evaluated.to_mesh_clear()
    world = local.reshape(vertex_count, 3).astype(numpy.float64) @ matrix[:3, :3].T + matrix[:3, 3]
    return Surface(world, triangles.reshape(triangle_count, 3), polygons, memberships)


def read_all(blender_objects, body_names, with_groups=False):
    """Read every mesh, the bodies twice. Returns ``(readings by name, unmeasured)``.

    Every mesh is read with the masks as they are before any is turned off, then
    the bodies that have a mask are read again inside :func:`masks_off`. A mesh
    Blender does not evaluate, and a mesh with no faces even unmasked, is
    :class:`Unmeasured`.
    """
    readings = dict()
    unmeasured = []
    drawn = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for blender_object in blender_objects:
        if blender_object.evaluated_get(depsgraph).is_evaluated:
            drawn.append(blender_object)
        else:
            unmeasured.append(Unmeasured(blender_object.name, "not_evaluated"))

    masked = dict((blender_object.name, read_surface(blender_object, depsgraph, with_groups))
                  for blender_object in drawn)

    masked_bodies = [blender_object for blender_object in drawn
                     if blender_object.name in body_names and body_masks(blender_object)]
    unmasked = dict()
    with masks_off(masked_bodies):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for blender_object in masked_bodies:
            unmasked[blender_object.name] = read_surface(blender_object, depsgraph, with_groups)

    for blender_object in drawn:
        name = blender_object.name
        surface = masked[name]
        bare = unmasked.get(name, surface)
        if surface is None and bare is None:
            unmeasured.append(Unmeasured(name, "no_faces"))
            continue
        readings[name] = Reading(name, name in body_names, viewport_subdiv_levels(blender_object),
                                 surface, bare)
    return (readings, unmeasured)


def _tree_within(surface, low, high):
    """A tree of only the triangles touching a box, and which triangle each of its faces is.

    Reindexing the vertices matters as much as dropping the triangles: a tree
    copies every coordinate it is given, and a hat needs a few hundred of a
    body's twenty thousand.
    """
    touching = surface.triangles_touching(low, high)
    used, reindexed = numpy.unique(surface.triangles[touching], return_inverse=True)
    tree = BVHTree.FromPolygons(surface.vertices[used].tolist(),
                                reindexed.reshape(-1, 3).tolist(), all_triangles=True)
    return (tree, touching)


def overlapping_triangles(first, second, box=None):
    """The intersecting triangle pairs of two surfaces, as an array of two index columns.

    Given one surface twice, each pair appears once and pairs sharing a vertex
    do not appear. With ``box``, both triangles' centres must be inside it.
    Either surface may be ``None``, which intersects nothing.

    **Two different surfaces can only intersect inside the box they share**, so
    the trees here hold only what touches it, and two surfaces whose boxes do not
    meet build none. That is what makes a body's 26,000 triangles cheap to ask
    about a hat, on a call whose other work may take 50 ms. The trees are not
    kept, since the next pair has a different box.
    """
    if first is None or second is None:
        return numpy.empty((0, 2), dtype=numpy.int64)
    if first is second:
        pairs = numpy.array(first.tree.overlap(first.tree), dtype=numpy.int64).reshape(-1, 2)
    else:
        low = numpy.maximum(first.low, second.low)
        high = numpy.minimum(first.high, second.high)
        if (low > high).any():
            return numpy.empty((0, 2), dtype=numpy.int64)
        first_tree, first_triangles = _tree_within(first, low, high)
        second_tree, second_triangles = _tree_within(second, low, high)
        found = numpy.array(first_tree.overlap(second_tree), dtype=numpy.int64).reshape(-1, 2)
        pairs = numpy.column_stack((first_triangles[found[:, 0]], second_triangles[found[:, 1]]))
    if first is second:
        pairs = pairs[pairs[:, 0] < pairs[:, 1]]
        one = first.triangles[pairs[:, 0]]
        other = first.triangles[pairs[:, 1]]
        share_a_vertex = (one[:, :, None] == other[:, None, :]).any(axis=(1, 2))
        pairs = pairs[~share_a_vertex]
    if box is not None:
        pairs = pairs[first.triangles_inside(box)[pairs[:, 0]]
                      & second.triangles_inside(box)[pairs[:, 1]]]
    return pairs


def box_of(points):
    """``{"min": {x, y, z}, "max": {x, y, z}}`` around world points, or ``None`` for none."""
    if len(points) == 0:
        return None
    return {
        bound: {axis: character_frame.rounded_metres(value)
                for axis, value in zip(_AXIS_NAMES, values)}
        for bound, values in (("min", points.min(axis=0)), ("max", points.max(axis=0)))
    }


def region_of(first, second, pairs):
    """The world box of the intersecting faces, on both surfaces, or ``None``."""
    if len(pairs) == 0:
        return None
    return box_of(numpy.concatenate((
        first.vertices[first.triangles[pairs[:, 0]]].reshape(-1, 3),
        second.vertices[second.triangles[pairs[:, 1]]].reshape(-1, 3))))


def _nearest_from(points, tree, best):
    """The nearest any of ``points`` comes to ``tree``, no further than ``best``, or ``best``.

    Each search is limited by the best so far, which is what makes this cheap: a
    tree can give up on most of itself once it has a bound to beat.
    """
    for point in points.tolist():
        if best is None:
            found = tree.find_nearest(point)
        else:
            found = tree.find_nearest(point, best)
        if found[3] is not None:
            best = found[3]
    return best


def closest_approach(first, second, box=None):
    """The nearest either surface's vertices come to the other's surface, or ``None``.

    An upper bound on the true closest approach, for the reason in this module's
    docstring. ``None`` when either surface is ``None``, or ``box`` holds no
    vertex of either.
    """
    if first is None or second is None:
        return None
    best = _nearest_from(first.vertices_inside(box), second.tree, None)
    best = _nearest_from(second.vertices_inside(box), first.tree, best)
    return best


def _distance(first, second, pairs, box):
    if len(pairs) > 0:
        return 0.0
    nearest = closest_approach(first, second, box)
    return None if nearest is None else character_frame.rounded_metres(nearest)


def pair_row(one, other, box=None, distances=True):
    """One pair of :class:`Reading`, as every tool that reports a pair reports it.

    A row with a body in it has the ``_unmasked`` fields, and one without does
    not: a mesh that is not a body has nothing hidden for them to say. The second
    measurement is made only if a surface actually differs.
    """
    is_self = one is other
    pairs = overlapping_triangles(one.masked, other.masked, box)
    row = dict(
        object_name=one.object_name,
        other_object_name=other.object_name,
        face_pairs=int(len(pairs)),
        region=region_of(one.masked, other.masked, pairs),
    )
    if distances:
        row["min_distance"] = None if is_self else _distance(one.masked, other.masked, pairs, box)
    if one.is_body or other.is_body:
        if one.unmasked is one.masked and other.unmasked is other.masked:
            row["face_pairs_unmasked"] = row["face_pairs"]
            row["region_unmasked"] = row["region"]
            if distances:
                row["min_distance_unmasked"] = row["min_distance"]
        else:
            bare = overlapping_triangles(one.unmasked, other.unmasked, box)
            row["face_pairs_unmasked"] = int(len(bare))
            row["region_unmasked"] = region_of(one.unmasked, other.unmasked, bare)
            if distances:
                row["min_distance_unmasked"] = (
                    None if is_self else _distance(one.unmasked, other.unmasked, bare, box))
    row["subdiv_levels"] = one.subdiv_levels
    row["other_subdiv_levels"] = other.subdiv_levels
    return row


def bodies_among(services, blender_objects):
    """The names of those objects that are skin rather than something worn over it."""
    is_body = services["ObjectService"].object_is_basemesh_or_body_proxy
    return set(blender_object.name for blender_object in blender_objects
               if is_body(blender_object))


def family_of(services, subject):
    """The meshes in ``subject``'s character, or ``subject`` alone if it belongs to none.

    From the root, as a placement moves them, so that a garment behind a sub-rig
    is found. A subject that belongs to no character and is not a mesh has an
    empty family.
    """
    basemesh = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        subject, "Basemesh")
    if basemesh is None:
        return [subject] if subject.type == "MESH" else []
    return [blender_object
            for blender_object in blender_data.with_descendants(placement.root_of(basemesh))
            if blender_object.type == "MESH"]
