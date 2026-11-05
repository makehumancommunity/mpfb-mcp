# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 051's spike: can a garment's openings be classified automatically?

Run inside a headless Blender, once per garment, from ``spike_run.py``. Reads and prints; it changes
nothing that is saved. For each boundary loop of the garment it reports the three candidate signals
the request names, so that they can be compared on real garments:

- **``chains``**: which limb and trunk chains, built from the basemesh's ``joint-*`` helper groups, pass
  through the loop. Needs no rig. It is a winding number of the loop around a chain's crossing of the
  loop's own plane, so a loop that a limb goes through says so whatever shape it is.
- **``dominant_bones``**: which bones' weights dominate the body vertices nearest the loop. The request
  says this one needs a rig. MPFB's default weights are read from its own ``weights.default.json`` here
  so that the signal can be compared on the gi's riggless scene too, which a tool could not assume.
- **``gap``**: how loose the opening is, from the loop's vertices to the unmasked body.

Beside them, two things the request did not list and the first run showed were needed, because a boundary
loop is not always an opening: **``reaches_skin``**, the share of a loop's vertices with no garment between
them and the body (a button's rim and a jacket over a shirt have none), and **``exposed``**, the share that
can see open air (a waistband under a coat, and the under flap of a V, have none).

Run through::

    python3 feature-requests/done/051-delete-groups/spike_run.py
"""

import json
import os
import sys

import bmesh
import bpy
import numpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ARGUMENTS = sys.argv[sys.argv.index("--") + 1:]
GARMENT_KIND = ARGUMENTS[0]
GARMENT_NAME = ARGUMENTS[1]
OUT_PATH = ARGUMENTS[2]

CHAINS = {
    "trunk": ("joint-pelvis", "joint-spine-3", "joint-spine-2", "joint-spine-1", "joint-neck", "joint-head", "joint-head-2"),
    "l-arm": ("joint-l-shoulder", "joint-l-elbow", "joint-l-hand", "joint-l-hand-3"),
    "r-arm": ("joint-r-shoulder", "joint-r-elbow", "joint-r-hand", "joint-r-hand-3"),
    "l-leg": ("joint-l-upper-leg", "joint-l-knee", "joint-l-ankle", "joint-l-foot-2"),
    "r-leg": ("joint-r-upper-leg", "joint-r-knee", "joint-r-ankle", "joint-r-foot-2"),
}


def services():
    root = next(name[:-len(".services.humanservice")] for name in sys.modules
                if name.endswith(".services.humanservice"))
    return dict(
        human=sys.modules[root + ".services.humanservice"].HumanService,
        location=sys.modules[root + ".services.locationservice"].LocationService,
        object=sys.modules[root + ".services.objectservice"].ObjectService)


def scene_objects():
    """``(garment, body)``: the gi's scene as it stands, or a fresh body wearing a library asset."""
    if GARMENT_KIND == "scene":
        garment = bpy.data.objects[GARMENT_NAME]
        return (garment, garment.parent)
    mpfb = services()
    body = mpfb["human"].create_human()
    directory = os.path.join(str(mpfb["location"].get_user_data("clothes")), GARMENT_NAME)
    path = sorted(os.path.join(parent, entry) for parent, _directories, entries in os.walk(directory)
                  for entry in entries if entry.endswith(".mhclo"))[0]
    garment = mpfb["human"].add_mhclo_asset(path, body, asset_type="Clothes", subdiv_levels=0,
                                            set_up_rigging=False)
    bpy.context.view_layer.update()
    return (garment, body)


def body_reading(body):
    """Every vertex of the body, by its own index, in world space, and each one's normal and neighbours."""
    states = [(modifier, modifier.show_viewport) for modifier in body.modifiers
              if modifier.type in ("MASK", "SUBSURF")]
    for modifier, _state in states:
        modifier.show_viewport = False
    bpy.context.view_layer.update()
    evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    work = bmesh.new()
    work.from_mesh(mesh)
    work.normal_update()
    assert len(work.verts) == len(body.data.vertices)
    matrix = body.matrix_world
    points = numpy.array([matrix @ vertex.co for vertex in work.verts])
    normals = numpy.array([(matrix.to_3x3() @ vertex.normal).normalized() for vertex in work.verts])
    faces = [[vertex.index for vertex in face.verts] for face in work.faces]
    work.free()
    evaluated.to_mesh_clear()
    for modifier, state in states:
        modifier.show_viewport = state
    return (points, normals, faces)


def group_members(body, name):
    index = body.vertex_groups[name].index
    return [vertex.index for vertex in body.data.vertices
            if any(element.group == index for element in vertex.groups)]


def joints_of(body, points):
    joints = dict()
    for group in body.vertex_groups:
        if group.name.startswith("joint-"):
            members = group_members(body, group.name)
            if members:
                joints[group.name] = points[members].mean(axis=0)
    return joints


def boundary_loops(garment):
    """Each boundary loop as vertex indices, joining at a vertex only along a clean path."""
    counts = dict()
    mesh = garment.data
    for polygon in mesh.polygons:
        indices = list(polygon.vertices)
        for first, second in zip(indices, indices[1:] + indices[:1]):
            key = (min(first, second), max(first, second))
            counts[key] = counts.get(key, 0) + 1
    edges = [key for key, count in counts.items() if count == 1]
    around = dict()
    for first, second in edges:
        around.setdefault(first, []).append(second)
        around.setdefault(second, []).append(first)
    seen = set()
    loops = []
    for start in sorted(around):
        for next_vertex in around[start]:
            edge = (min(start, next_vertex), max(start, next_vertex))
            if edge in seen:
                continue
            seen.add(edge)
            loop = [start]
            previous, current = start, next_vertex
            while current != start:
                loop.append(current)
                onward = [vertex for vertex in around[current]
                          if (min(current, vertex), max(current, vertex)) not in seen]
                if not onward:
                    break
                previous, current = current, onward[0]
                seen.add((min(previous, current), max(previous, current)))
            loops.append(loop)
    return (loops, len(edges))


def components_of(garment):
    """The connected component each vertex belongs to."""
    mesh = garment.data
    parent = list(range(len(mesh.vertices)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for edge in mesh.edges:
        first, second = edge.vertices
        parent[find(first)] = find(second)
    return [find(index) for index in range(len(mesh.vertices))]


def winding_number(point_2d, polygon_2d):
    total = 0.0
    for first, second in zip(polygon_2d, numpy.roll(polygon_2d, -1, axis=0)):
        a = first - point_2d
        b = second - point_2d
        total += numpy.arctan2(a[0] * b[1] - a[1] * b[0], a @ b)
    return total / (2.0 * numpy.pi)


def sight_lines(count=240):
    """A Fibonacci sphere: fixed, so that the same mesh gives the same answer."""
    lines = []
    for k in range(count):
        z = 1.0 - 2.0 * (k + 0.5) / count
        radius = (1.0 - z * z) ** 0.5
        angle = k * 2.399963
        lines.append(Vector((radius * numpy.cos(angle), radius * numpy.sin(angle), z)))
    return lines


def open_shares(loop_points, body_tree, garment_tree):
    """``(reaches_skin, exposed)``: how much of a loop has nothing in front of or behind it."""
    reaches = 0
    exposed = 0
    lines = sight_lines()
    for point in loop_points.tolist():
        origin = Vector(point)
        location, normal, _index, distance = body_tree.find_nearest(origin)
        toward = (location - origin)
        if distance > 1e-5:
            toward.normalize()
            hit = garment_tree.ray_cast(origin + toward * 0.001, toward, max(distance - 0.002, 0.0))[0]
            if hit is None:
                reaches += 1
        else:
            reaches += 1
        for line in lines:
            if line.dot(normal) < 0.35:
                continue
            if garment_tree.ray_cast(origin + line * 0.001, line, 1.0)[0] is None:
                exposed += 1
                break
    return (round(reaches / len(loop_points), 3), round(exposed / len(loop_points), 3))


def weights_table(root_directory):
    """Per body vertex, its bones and weights, from MPFB's own default weights."""
    with open(os.path.join(root_directory, "data", "rigs", "standard", "weights.default.json"), "r",
              encoding="utf8") as handle:
        weights = json.load(handle)["weights"]
    table = dict()
    for bone, rows in weights.items():
        for vertex, weight in rows:
            table.setdefault(vertex, []).append((weight, bone))
    return table


def dominant_bones(loop_points, body_tree, triangles, table):
    """The bones weighing most on the body vertices nearest this loop."""
    totals = dict()
    for point in loop_points.tolist():
        _location, _normal, index, _distance = body_tree.find_nearest(Vector(point))
        for vertex in triangles[index]:
            for weight, bone in table.get(vertex, ()):
                totals[bone] = totals.get(bone, 0.0) + weight
    ranked = sorted(totals, key=lambda bone: -totals[bone])
    return ranked[:3]


def by_chains(row):
    """The joint signal's rule: which limb goes through."""
    chains = row["chains"]
    if "l-arm" in chains or "r-arm" in chains:
        return "cuff"
    if "l-leg" in chains or "r-leg" in chains:
        return "hem"
    return "trunk"


def by_bones(row):
    """The rig weights' rule: which part of the body dominates."""
    bone = row["dominant_bones"][0] if row["dominant_bones"] else ""
    if any(word in bone for word in ("lowerarm", "upperarm", "wrist", "hand", "finger", "metacarpal")):
        return "cuff"
    if any(word in bone for word in ("upperleg", "lowerleg", "foot", "toe")):
        return "hem"
    return "trunk"


def by_gap(row):
    """The looseness rule: a limb's opening is the wide one."""
    return "limb" if row["gap_median"] > 0.02 else "trunk"


def chains_through(loop_points, joints):
    """Which chains cross the loop's best-fit plane inside the loop, and how far along each."""
    centre = loop_points.mean(axis=0)
    _u, _s, axes = numpy.linalg.svd(loop_points - centre)
    x_axis, y_axis, normal = axes[0], axes[1], axes[2]
    polygon = numpy.column_stack(((loop_points - centre) @ x_axis, (loop_points - centre) @ y_axis))
    found = dict()
    for chain, names in CHAINS.items():
        path = [joints[name] for name in names if name in joints]
        travelled = 0.0
        total = sum(numpy.linalg.norm(b - a) for a, b in zip(path, path[1:]))
        for first, second in zip(path, path[1:]):
            length = numpy.linalg.norm(second - first)
            side_a = (first - centre) @ normal
            side_b = (second - centre) @ normal
            if side_a * side_b < 0.0:
                t = side_a / (side_a - side_b)
                crossing = first + (second - first) * t
                local = numpy.array(((crossing - centre) @ x_axis, (crossing - centre) @ y_axis))
                if abs(winding_number(local, polygon)) > 0.5:
                    found[chain] = round(float((travelled + t * length) / total), 3)
            travelled += length
    return found


def main():
    garment, body = scene_objects()
    points, normals, faces = body_reading(body)
    joints = joints_of(body, points)
    body_vertices = group_members(body, "body")
    body_set = set(body_vertices)
    body_faces = [face for face in faces if all(index in body_set for index in face)]
    triangles = []
    for face in body_faces:
        triangles.extend((face[0], face[k], face[k + 1]) for k in range(1, len(face) - 1))
    tree = BVHTree.FromPolygons(points.tolist(), triangles, all_triangles=True)

    matrix = garment.matrix_world
    garment_points = numpy.array([matrix @ vertex.co for vertex in garment.data.vertices])
    garment_tree = BVHTree.FromPolygons(garment_points.tolist(),
                                        [list(polygon.vertices) for polygon in garment.data.polygons])
    root_directory = os.path.dirname(os.path.dirname(os.path.abspath(
        sys.modules[next(name for name in sys.modules if name.endswith(".services.humanservice"))].__file__)))
    table = weights_table(root_directory)
    loops, boundary_edges = boundary_loops(garment)
    components = components_of(garment)
    component_sizes = dict()
    for component in components:
        component_sizes[component] = component_sizes.get(component, 0) + 1

    rows = []
    for loop in loops:
        loop_points = garment_points[loop]
        perimeter = float(numpy.linalg.norm(loop_points - numpy.roll(loop_points, -1, axis=0), axis=1).sum())
        gaps = [tree.find_nearest(Vector(point))[3] for point in loop_points.tolist()]
        nearest = sorted(joints, key=lambda name: numpy.linalg.norm(joints[name] - loop_points.mean(axis=0)))[:3]
        rows.append(dict(
            vertices=len(loop),
            perimeter=round(perimeter, 3),
            centre=[round(float(value), 3) for value in loop_points.mean(axis=0)],
            low_z=round(float(loop_points[:, 2].min()), 3),
            high_z=round(float(loop_points[:, 2].max()), 3),
            component_vertices=component_sizes[components[loop[0]]],
            chains=chains_through(loop_points, joints),
            gap_median=round(float(numpy.median(gaps)), 4),
            gap_max=round(float(numpy.max(gaps)), 4),
            nearest_joints=nearest,
            dominant_bones=dominant_bones(loop_points, tree, triangles, table)))
        rows[-1]["reaches_skin"], rows[-1]["exposed"] = open_shares(loop_points, tree, garment_tree)
        rows[-1]["kind_by_chains"] = by_chains(rows[-1])
        rows[-1]["kind_by_bones"] = by_bones(rows[-1])
        rows[-1]["kind_by_gap"] = by_gap(rows[-1])
    rows.sort(key=lambda row: -row["perimeter"])
    answer = dict(garment=garment.name, body_vertices=len(body_vertices), garment_vertices=len(garment.data.vertices),
                  garment_polygons=len(garment.data.polygons), boundary_edges=boundary_edges,
                  components=sorted(component_sizes.values(), reverse=True)[:12], loops=rows,
                  groups=dict((group.name, len(group_members(body, group.name))) for group in body.vertex_groups
                              if group.name.lower().startswith("delete")),
                  masks=[(modifier.name, str(modifier.vertex_group)) for modifier in body.modifiers if modifier.type == "MASK"],
                  joint_heights=dict((name, round(float(joints[name][2]), 3)) for name in
                                     ("joint-neck", "joint-l-hand", "joint-l-knee", "joint-l-ankle", "joint-pelvis")),
                  )
    with open(OUT_PATH, "w", encoding="utf8") as handle:
        json.dump(answer, handle, indent=1)


main()
