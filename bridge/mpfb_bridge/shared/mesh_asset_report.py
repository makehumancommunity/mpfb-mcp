"""
Whether a mesh is ready to be written as an asset, read section by section.

**One reading, so that a later summary is not a second opinion**
([FR 048](../../../feature-requests/done/048-measuring-mesh-assets/README.md)).
``check_mesh_asset`` reports it whole, and FR 050's write answer is to carry a
summary of the same reading, which is the rule ``get_character_summary`` already
follows. The overlap itself is [`mesh_overlap.py`](mesh_overlap.py)'s.

**Why more than MPFB's validator.** ``ClothesService.mesh_is_valid_as_clothes()``
checks vertex groups, scale and face type. It gave ``all_checks_ok: true`` for
the gi draft, whose coat had inward normals and passed through the hakama, the
body and itself. Its report is carried unchanged (:func:`validator`) and nothing
here adds a verdict: the finished gi has 613 unmasked pairs and is fine, so no
threshold on a count would be objective.

**Per connected component, because that is what a draft is made of.** The draft
had two, hakama and coat, with sleeves and flaps all in the second, so "the under
flap through the top flap" is the coat's self-overlap and is found there. The
components are of the evaluated mesh, so ``faces`` and ``vertices`` are what was
measured and count a viewport subdivision if there is one, which the answer's
``subdiv_levels`` says. A mesh made of a great many, as hair cards are, has its
largest listed and the rest counted, because :data:`MAX_COMPONENTS` rows of this
is already long.

**``outward_fraction`` compares with the body rather than with the mesh's own
middle.** It is the share of faces whose normal agrees with that of the nearest
surface of the unmasked body. A garment's own centre would answer that badly: a sleeve's centre is inside the sleeve, not inside the coat.
A single layer facing the right way reads near 1.0 and one inside out near 0, as
the gi's draft coat did at exactly 0.0, while a closed shell with thickness reads
near 0.5 whichever way it faces, because half of it faces the body: the finished
gi's belt reads 0.36 to 0.71 and is right. **``fit_offset``** is each vertex's
distance from that surface, signed by that surface's normal, so a negative ``min``
is a vertex inside the body. Both use the unmasked body, since a mask would remove
the very surface being asked about.

**UV and textures read the object's own mesh, not the evaluated one**: an island
is a property of what gets written. Overlapping islands are found on a grid of
:data:`_UV_GRID` cells rather than exactly, so a sliver smaller than a cell is
missed and a cell centre exactly on two touching edges would count, neither of
which is what the number is for: it finds mirrored or duplicated islands sharing
texture space. Cells outside 0..1 are not looked at, and
``faces_outside_unit_square`` counts those faces instead.

**``metadata``'s ``set`` is Blender's own ``is_property_set()``**, on the
property's full name. ``BlenderConfigSet.has_key_with_value()`` cannot say, since
it reads through to the default, and FR 050 asked whether anything could: on
Blender 5.1 this tells a chosen ``CC0`` from MPFB's default ``CC0`` on the gi.

**MPFB's validator has two side effects, and both are undone here**
(:func:`validator`). It builds a ``MeshCrossRef``, which copies the mesh and links
the copy, deletes the object and leaves the copied mesh data behind as an orphan.
And its ``MeshCrossRef`` for the basemesh is given ``cache_dir``, which it creates
when absent, so on an install with no xref cache it leaves an empty directory, and
MPFB's own panel and writer then read that directory as a cache that exists.
:func:`write_state` looks inside it for that reason.

Takes ``services`` first where it reads MPFB. ``textures`` and ``components`` are
plain Blender and do not.
"""

__all__ = (
    "MAX_COMPONENTS",
    "component_report",
    "metadata",
    "metadata_warnings",
    "textures",
    "uv_report",
    "validator",
    "write_state",
)

import math
import os

import bpy
import numpy

from . import blender_data
from . import character_frame
from . import mesh_overlap
from . import mpfb_surface
from . import selection

# Rows of per-component detail, largest first. Everything else is counted.
MAX_COMPONENTS = 20

# Rows naming another component this one intersects, largest first.
_MAX_OTHER_COMPONENTS = 5

# Rows naming the lowest resolution islands, and overlapping island pairs.
_MAX_LOWEST_ISLANDS = 5
_MAX_OVERLAPPING_PAIRS = 10

# Cells per side of the grid overlapping islands are looked for on. A 4096 px
# texture has four texels to a cell, far finer than an island is wide.
_UV_GRID = 1024

# Past this many islands the pairwise box test stops being cheap, and a mesh with
# this many (hair cards) is not one whose islands anyone reads one at a time.
_MAX_ISLANDS_COMPARED = 2000

# A coordinate this close to the edge of 0..1 is on it, not outside it.
_UV_TOLERANCE = 1e-5

# Which of the three property sets a written asset draws on holds which.
_METADATA_LICENSE_KEYS = ("license", "author")


def _not_applicable(reason):
    return {"applies": False, "reason": reason}


def _connected_labels(vertex_count, triangles):
    """Per vertex, the lowest vertex index it is connected to through the triangles."""
    labels = numpy.arange(vertex_count)
    edges = numpy.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]]))
    while True:
        lowest = numpy.minimum(labels[edges[:, 0]], labels[edges[:, 1]])
        updated = labels.copy()
        numpy.minimum.at(updated, edges[:, 0], lowest)
        numpy.minimum.at(updated, edges[:, 1], lowest)
        updated = updated[updated]
        if numpy.array_equal(updated, labels):
            return labels
        labels = updated


def _outward_fraction(surface, triangle_indices, body_tree):
    """The share of these faces whose normal agrees with the nearest body surface's."""
    _polygons, first = numpy.unique(surface.polygons[triangle_indices], return_index=True)
    corners = surface.vertices[surface.triangles[triangle_indices[first]]]
    normals = numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    centres = corners.mean(axis=1)
    agreeing = 0
    measured = 0
    for centre, normal in zip(centres.tolist(), normals.tolist()):
        location, body_normal, _index, _distance = body_tree.find_nearest(centre)
        if location is None:
            continue
        measured += 1
        if (normal[0] * body_normal[0] + normal[1] * body_normal[1]
                + normal[2] * body_normal[2]) > 0.0:
            agreeing += 1
    return None if measured == 0 else round(agreeing / measured, 4)


def _fit_offset(points, body_tree):
    """Signed ``min`` and ``max`` distance of these points from the surface, or ``None``."""
    lowest = None
    highest = None
    for point in points.tolist():
        location, normal, _index, distance = body_tree.find_nearest(point)
        if location is None:
            continue
        outside = ((point[0] - location[0]) * normal[0] + (point[1] - location[1]) * normal[1]
                   + (point[2] - location[2]) * normal[2])
        signed = distance if outside >= 0.0 else -distance
        lowest = signed if lowest is None else min(lowest, signed)
        highest = signed if highest is None else max(highest, signed)
    if lowest is None:
        return None
    return {"min": character_frame.rounded_metres(lowest),
            "max": character_frame.rounded_metres(highest)}


def _group_names_of(surface, vertex_mask, group_names):
    """The names of the vertex groups these vertices belong to, sorted."""
    rows = surface.memberships
    if rows is None or len(rows) == 0:
        return []
    indices = numpy.unique(rows[vertex_mask[rows[:, 0]], 1])
    return sorted(group_names[index] for index in indices.tolist() if index < len(group_names))


def _other_components(surface, pairs, first_component, second_component, this, position_of):
    """This component's rows against the others, largest first, and how many there are."""
    theirs = dict()
    involved = (first_component == this) | (second_component == this)
    involved &= first_component != second_component
    for pair_index in numpy.flatnonzero(involved).tolist():
        one = int(first_component[pair_index])
        other = int(second_component[pair_index]) if one == this else one
        theirs.setdefault(other, []).append(pair_index)
    rows = [dict(component=position_of[other], face_pairs=len(indices),
                 region=mesh_overlap.region_of(surface, surface, pairs[indices]))
            for other, indices in theirs.items()]
    rows.sort(key=lambda row: (-row["face_pairs"], row["component"]))
    return (rows[:_MAX_OTHER_COMPONENTS], len(rows))


def component_report(mesh, body, group_names):
    """Per connected component of ``mesh``, measured against the body's :class:`Reading`.

    ``mesh`` is a ``mesh_overlap.Reading`` read with groups. Takes the two
    readings rather than the objects, so that a caller reads each once.
    """
    surface = mesh.masked
    if surface is None:
        return _not_applicable("The mesh has no faces to measure.")
    bare_body = body.unmasked

    labels = _connected_labels(len(surface.vertices), surface.triangles)
    triangle_component = labels[surface.triangles[:, 0]]

    faces_by_component = dict()
    for component in numpy.unique(triangle_component).tolist():
        faces_by_component[component] = int(len(numpy.unique(
            surface.polygons[triangle_component == component])))
    order = sorted(faces_by_component, key=lambda component: (-faces_by_component[component],
                                                              component))
    position_of = {component: position for position, component in enumerate(order)}

    self_pairs = mesh_overlap.overlapping_triangles(surface, surface)
    first_component = triangle_component[self_pairs[:, 0]]
    second_component = triangle_component[self_pairs[:, 1]]
    with_masks = mesh_overlap.overlapping_triangles(surface, body.masked)
    without_masks = (with_masks if bare_body is body.masked
                     else mesh_overlap.overlapping_triangles(surface, bare_body))

    rows = []
    for component in order[:MAX_COMPONENTS]:
        triangles = numpy.flatnonzero(triangle_component == component)
        vertex_mask = labels == component
        own = (first_component == component) & (second_component == component)
        masked_here = with_masks[triangle_component[with_masks[:, 0]] == component]
        bare_here = without_masks[triangle_component[without_masks[:, 0]] == component]
        others, other_count = _other_components(
            surface, self_pairs, first_component, second_component, component, position_of)
        rows.append(dict(
            component=position_of[component],
            faces=faces_by_component[component],
            vertices=int(vertex_mask.sum()),
            vertex_groups=_group_names_of(surface, vertex_mask, group_names),
            bounds=mesh_overlap.box_of(surface.vertices[vertex_mask]),
            outward_fraction=(None if bare_body is None else
                              _outward_fraction(surface, triangles, bare_body.tree)),
            fit_offset=(None if bare_body is None else
                        _fit_offset(surface.vertices[vertex_mask], bare_body.tree)),
            overlap=dict(
                body=dict(
                    face_pairs=int(len(masked_here)),
                    region=mesh_overlap.region_of(surface, body.masked, masked_here),
                    face_pairs_unmasked=int(len(bare_here)),
                    region_unmasked=mesh_overlap.region_of(surface, bare_body, bare_here),
                ),
                self=dict(
                    face_pairs=int(own.sum()),
                    region=mesh_overlap.region_of(surface, surface, self_pairs[own]),
                ),
                other_components=others,
                other_components_intersecting=other_count,
            ),
        ))

    connected = numpy.zeros(len(surface.vertices), dtype=bool)
    connected[surface.triangles.reshape(-1)] = True
    return dict(
        applies=True,
        measured_against=body.object_name,
        subdiv_levels=mesh.subdiv_levels,
        body_subdiv_levels=body.subdiv_levels,
        component_count=len(order),
        components_truncated=len(order) > len(rows),
        loose_vertices=int((~connected).sum()),
        rows=rows,
    )


def _image_nodes(node_tree, seen=None):
    """Every image node in a node tree, going down into groups and visiting each group once."""
    seen = set() if seen is None else seen
    found = []
    if node_tree is None or node_tree.name in seen:
        return found
    seen.add(node_tree.name)
    for node in node_tree.nodes:
        if node.type == "TEX_IMAGE":
            found.append(node)
        elif node.type == "GROUP":
            found.extend(_image_nodes(node.node_tree, seen))
    return found


def _texture_row(material_name, node):
    image = node.image
    row = dict(material_name=material_name, slot=str(node.name), image_name=None, path=None,
               file_exists=False, size=None, color_space=None, packed=False, unsaved_changes=False)
    if image is None:
        return row
    path = bpy.path.abspath(image.filepath, library=image.library) if image.filepath else None
    row.update(
        image_name=str(image.name),
        path=None if path is None else os.path.normpath(path),
        file_exists=path is not None and os.path.isfile(path),
        size=[int(side) for side in image.size],
        color_space=str(image.colorspace_settings.name),
        packed=image.packed_file is not None,
        unsaved_changes=bool(image.is_dirty),
    )
    return row


def textures(blender_object):
    """Every image node on this object's materials, as one row each."""
    rows = []
    for slot in blender_object.material_slots:
        material = slot.material
        if material is None:
            continue
        for node in _image_nodes(material.node_tree):
            rows.append(_texture_row(str(material.name), node))
    return rows


def _uv_islands(mesh, coordinates):
    """Per polygon, which UV island it is on, numbered in polygon order; and how many.

    Two polygons are on one island when they share an edge whose two ends have the
    same coordinates on both sides. **Not ``bpy_extras.mesh_utils.mesh_linked_uv_islands()``**,
    which joins polygons that merely hold one UV coordinate in common, vertex or no
    vertex, so two unrelated islands packed corner to corner would read as one.
    """
    polygon_count = len(mesh.polygons)
    starts = numpy.empty(polygon_count, dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_start", starts)
    totals = numpy.empty(polygon_count, dtype=numpy.int64)
    mesh.polygons.foreach_get("loop_total", totals)
    vertices = numpy.empty(len(mesh.loops), dtype=numpy.int64)
    mesh.loops.foreach_get("vertex_index", vertices)
    vertices = vertices.tolist()
    rounded = [tuple(pair) for pair in numpy.round(coordinates, 5).tolist()]

    parents = list(range(polygon_count))

    def root_of(polygon):
        while parents[polygon] != polygon:
            parents[polygon] = parents[parents[polygon]]
            polygon = parents[polygon]
        return polygon

    first_on_edge = dict()
    for polygon, (start, total) in enumerate(zip(starts.tolist(), totals.tolist())):
        for offset in range(total):
            here = start + offset
            there = start + (offset + 1) % total
            one = (vertices[here], rounded[here])
            other = (vertices[there], rounded[there])
            key = (one, other) if one <= other else (other, one)
            earlier = first_on_edge.setdefault(key, polygon)
            parents[root_of(polygon)] = root_of(earlier)

    numbers = dict()
    labels = numpy.empty(polygon_count, dtype=numpy.int64)
    for polygon in range(polygon_count):
        labels[polygon] = numbers.setdefault(root_of(polygon), len(numbers))
    return (labels, len(numbers))


def _rasterised(triangles):
    """Which cells of a window these triangles cover: ``(x0, y0, mask)``, or ``None``.

    ``triangles`` is ``(n, 3, 2)`` in cell units. A cell is covered when its
    centre is inside a triangle.
    """
    x_low = max(int(math.floor(triangles[:, :, 0].min())), 0)
    y_low = max(int(math.floor(triangles[:, :, 1].min())), 0)
    x_high = min(int(math.ceil(triangles[:, :, 0].max())), _UV_GRID)
    y_high = min(int(math.ceil(triangles[:, :, 1].max())), _UV_GRID)
    if x_low >= x_high or y_low >= y_high:
        return None
    mask = numpy.zeros((y_high - y_low, x_high - x_low), dtype=bool)
    for corner_a, corner_b, corner_c in triangles.tolist():
        left = max(int(math.floor(min(corner_a[0], corner_b[0], corner_c[0]))), x_low)
        right = min(int(math.ceil(max(corner_a[0], corner_b[0], corner_c[0]))), x_high)
        bottom = max(int(math.floor(min(corner_a[1], corner_b[1], corner_c[1]))), y_low)
        top = min(int(math.ceil(max(corner_a[1], corner_b[1], corner_c[1]))), y_high)
        if left >= right or bottom >= top:
            continue
        grid_x, grid_y = numpy.meshgrid(numpy.arange(left, right) + 0.5,
                                        numpy.arange(bottom, top) + 0.5)
        sides = [(end[0] - start[0]) * (grid_y - start[1]) - (end[1] - start[1]) * (grid_x - start[0])
                 for start, end in ((corner_a, corner_b), (corner_b, corner_c), (corner_c, corner_a))]
        inside = (((sides[0] >= 0) & (sides[1] >= 0) & (sides[2] >= 0))
                  | ((sides[0] <= 0) & (sides[1] <= 0) & (sides[2] <= 0)))
        mask[bottom - y_low:top - y_low, left - x_low:right - x_low] |= inside
    return (x_low, y_low, mask)


def _overlapping_islands(uv_triangles, island_of_triangle, island_count):
    """Which islands share a grid cell, as sorted ``(island, other)`` pairs, or ``None``.

    Only islands whose box touches another's are rasterised. ``None`` when there
    are too many islands to compare, which is not the same as none overlapping.
    """
    if island_count > _MAX_ISLANDS_COMPARED:
        return None
    if island_count < 2:
        return []
    low = numpy.full((island_count, 2), numpy.inf)
    high = numpy.full((island_count, 2), -numpy.inf)
    numpy.minimum.at(low, island_of_triangle, uv_triangles.min(axis=1))
    numpy.maximum.at(high, island_of_triangle, uv_triangles.max(axis=1))
    touching = ((low[:, None, :] < high[None, :, :]) & (low[None, :, :] < high[:, None, :])).all(axis=2)
    numpy.fill_diagonal(touching, False)
    candidates = numpy.flatnonzero(touching.any(axis=1))
    owner = numpy.full((_UV_GRID, _UV_GRID), -1, dtype=numpy.int32)
    pairs = set()
    for island in candidates.tolist():
        window = _rasterised(uv_triangles[island_of_triangle == island] * _UV_GRID)
        if window is None:
            continue
        x_low, y_low, mask = window
        cells = owner[y_low:y_low + mask.shape[0], x_low:x_low + mask.shape[1]]
        for other in numpy.unique(cells[mask]).tolist():
            if other >= 0:
                pairs.add((min(other, island), max(other, island)))
        cells[mask] = island
    return sorted(pairs)


def _uv_box(low, high):
    return {"min": [round(float(low[0]), 4), round(float(low[1]), 4)],
            "max": [round(float(high[0]), 4), round(float(high[1]), 4)]}


def _largest_image(texture_rows):
    """The largest image on the object, by its longer side, which resolution is measured on."""
    sized = [row for row in texture_rows if row["size"] and min(row["size"]) > 0]
    if not sized:
        return None
    return max(sized, key=lambda row: (max(row["size"]), row["image_name"]))


def uv_report(blender_object, texture_rows):
    """Islands, overlaps, what is outside 0..1 and how many texels each metre gets."""
    mesh = blender_object.data
    uv_layer = mesh.uv_layers.active
    if uv_layer is None:
        return _not_applicable("The mesh has no UV map.")
    if blender_object.mode == "EDIT":
        # Blender hands Python no UV data for a mesh being edited.
        return _not_applicable("The mesh is in edit mode, where Blender gives Python no UV data.")
    triangle_count = len(mesh.loop_triangles)
    polygon_count = len(mesh.polygons)
    if triangle_count == 0:
        return _not_applicable("The mesh has no faces.")

    coordinates = numpy.empty(len(mesh.loops) * 2, dtype=numpy.float64)
    uv_layer.uv.foreach_get("vector", coordinates)
    coordinates = coordinates.reshape(-1, 2)
    loops = numpy.empty(triangle_count * 3, dtype=numpy.int32)
    mesh.loop_triangles.foreach_get("loops", loops)
    polygon_of_triangle = numpy.empty(triangle_count, dtype=numpy.int32)
    mesh.loop_triangles.foreach_get("polygon_index", polygon_of_triangle)
    uv_triangles = coordinates[loops.reshape(-1, 3)]
    areas = numpy.empty(polygon_count, dtype=numpy.float64)
    mesh.polygons.foreach_get("area", areas)

    island_of_polygon, island_count = _uv_islands(mesh, coordinates)
    island_of_triangle = island_of_polygon[polygon_of_triangle]

    edge_one = uv_triangles[:, 1] - uv_triangles[:, 0]
    edge_two = uv_triangles[:, 2] - uv_triangles[:, 0]
    uv_areas = numpy.zeros(island_count)
    numpy.add.at(uv_areas, island_of_triangle,
                 0.5 * numpy.abs(edge_one[:, 0] * edge_two[:, 1] - edge_one[:, 1] * edge_two[:, 0]))
    # Polygon areas are in the object's own units; a garment scaled in the object
    # is measured in the metres it stands in.
    scale = abs(blender_object.matrix_world.to_3x3().determinant()) ** (2.0 / 3.0)
    world_areas = numpy.zeros(island_count)
    numpy.add.at(world_areas, island_of_polygon, areas * scale)

    outside = ((uv_triangles < -_UV_TOLERANCE) | (uv_triangles > 1.0 + _UV_TOLERANCE)).any(axis=(1, 2))

    low = numpy.full((island_count, 2), numpy.inf)
    high = numpy.full((island_count, 2), -numpy.inf)
    numpy.minimum.at(low, island_of_triangle, uv_triangles.min(axis=1))
    numpy.maximum.at(high, island_of_triangle, uv_triangles.max(axis=1))

    overlapping = _overlapping_islands(uv_triangles, island_of_triangle, island_count)
    measurable = (uv_areas > 0.0) & (world_areas > 0.0)
    units_per_metre = numpy.zeros(island_count)
    units_per_metre[measurable] = numpy.sqrt(uv_areas[measurable] / world_areas[measurable])

    image = _largest_image(texture_rows)
    texels = None if image is None else math.sqrt(image["size"][0] * image["size"][1])

    def resolution(values):
        if not measurable.any():
            return None
        return {"min": round(float(values[measurable].min()), 2),
                "max": round(float(values[measurable].max()), 2)}

    lowest = numpy.flatnonzero(measurable)
    lowest = lowest[numpy.argsort(units_per_metre[lowest], kind="stable")][:_MAX_LOWEST_ISLANDS]
    faces_per_island = numpy.bincount(island_of_polygon, minlength=island_count)

    return dict(
        applies=True,
        uv_map=str(uv_layer.name),
        islands=island_count,
        overlapping_islands=(None if overlapping is None
                             else len(set(island for pair in overlapping for island in pair))),
        overlapping_pairs=(None if overlapping is None else [
            dict(island=one, other_island=other,
                 uv_box=_uv_box(numpy.maximum(low[one], low[other]),
                                numpy.minimum(high[one], high[other])))
            for one, other in overlapping[:_MAX_OVERLAPPING_PAIRS]]),
        overlapping_pairs_truncated=(False if overlapping is None
                                     else len(overlapping) > _MAX_OVERLAPPING_PAIRS),
        faces_outside_unit_square=int(len(numpy.unique(polygon_of_triangle[outside]))),
        uv_units_per_metre=resolution(units_per_metre),
        texels_per_metre=None if texels is None else resolution(units_per_metre * texels),
        measured_against_image=None if image is None else dict(
            image_name=image["image_name"], size=image["size"]),
        lowest_islands=[
            dict(island=island,
                 faces=int(faces_per_island[island]),
                 uv_box=_uv_box(low[island], high[island]),
                 uv_units_per_metre=round(float(units_per_metre[island]), 2),
                 texels_per_metre=(None if texels is None
                                   else round(float(units_per_metre[island] * texels), 2)))
            for island in lowest.tolist()],
    )


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _config_group(config_set, blender_object, missing_reason):
    """Every value of one property set, beside whether it was ever set on this object."""
    if config_set is None:
        return _not_applicable(missing_reason)
    values = dict()
    for key in sorted(config_set.get_keys()):
        full_name = config_set.get_fullname_key_from_shortname_key(key)
        values[key] = dict(
            value=_json_safe(config_set.get_value(key, entity_reference=blender_object)),
            set=bool(blender_object.is_property_set(full_name)),
        )
    return dict(applies=True, values=values)


def metadata(services, root_name, blender_object):
    """The three property groups a written asset draws on."""
    return dict(
        makeclothes=_config_group(
            mpfb_surface.make_clothes_properties(root_name), blender_object,
            "MPFB's MakeClothes properties are not loaded, so nothing can be said about them."),
        makeskin=_config_group(
            mpfb_surface.make_skin_properties(root_name), blender_object,
            "MPFB's MakeSkin properties are not loaded, so nothing can be said about them."),
        general=_config_group(
            mpfb_surface.general_object_properties(services), blender_object,
            "MPFB's general object properties are not where this bridge expects them."),
    )


def metadata_warnings(metadata_section):
    """A sentence for each value MakeClothes and MakeSkin would write differently."""
    warnings = []
    clothes = metadata_section["makeclothes"]
    skin = metadata_section["makeskin"]
    if not clothes["applies"] or not skin["applies"]:
        return warnings
    for key in _METADATA_LICENSE_KEYS:
        ours = clothes["values"].get(key)
        theirs = skin["values"].get(key)
        if ours is None or theirs is None or ours["value"] == theirs["value"]:
            continue
        warnings.append(
            "MakeClothes' {0:s} is {1!r} ({2:s}) and MakeSkin's is {3!r} ({4:s}). The MHCLO takes "
            "the first and the MHMAT the second, so a written asset would disagree with "
            "itself.".format(key, ours["value"], "set" if ours["set"] else "MPFB's default",
                             theirs["value"], "set" if theirs["set"] else "MPFB's default"))
    return warnings


def _cache_directory(services):
    return mpfb_surface.as_path(services["LocationService"].get_user_cache("basemesh_xref"))


def _render_subdiv_levels(blender_object):
    return sum(int(modifier.render_levels) for modifier in blender_object.modifiers
               if modifier.type == "SUBSURF" and modifier.show_render)


def write_state(services, root_name, blender_object, basemesh):
    """What a write would find: the cache, the source record, the delete group, subdivision.

    The cache is reported by what is in the directory. MPFB's own check is the
    directory's existence, which its validator can itself bring about; see this
    module's docstring. Read this **before** :func:`validator`.
    """
    general = mpfb_surface.general_object_properties(services)
    asset_source = mpfb_surface.property_value(general, "asset_source", blender_object)
    source_path = None
    if asset_source is not None:
        try:
            source_path = mpfb_surface.as_path(
                services["ClothesService"].find_clothes_absolute_path(blender_object))
        except Exception:  # pylint: disable=broad-except
            source_path = None
    cache_directory = _cache_directory(services)
    cache_exists = bool(cache_directory and os.path.isdir(cache_directory)
                        and os.listdir(cache_directory))

    clothes_properties = mpfb_surface.make_clothes_properties(root_name)
    delete_group_name = None
    if clothes_properties is not None:
        delete_group_name = mpfb_surface.property_value(
            clothes_properties, "delete_group", blender_object)
    group_exists = (delete_group_name is not None
                    and delete_group_name in blender_data.vertex_group_names(basemesh))
    return dict(
        xref_cache_exists=cache_exists,
        xref_cache_directory=cache_directory,
        asset_source=asset_source,
        asset_source_resolves=None if asset_source is None else source_path is not None,
        asset_source_path=source_path,
        delete_group=dict(
            name=delete_group_name,
            exists_on_basemesh=group_exists,
            vertices=(blender_data.vertices_in_groups(basemesh, (delete_group_name,))
                      if group_exists else 0),
        ),
        subdiv_viewport_levels=mesh_overlap.viewport_subdiv_levels(blender_object),
        subdiv_render_levels=_render_subdiv_levels(blender_object),
    )


def validator(services, blender_object, basemesh):
    """MPFB's validator's report, unchanged, with its two side effects undone.

    Returns ``(report, sentence)``: a ``report`` of ``None`` means it raised, and
    ``sentence`` says what it raised.
    """
    cache_directory = _cache_directory(services)
    cache_existed = bool(cache_directory and os.path.exists(cache_directory))
    meshes_before = set(mesh.name for mesh in bpy.data.meshes)
    report = None
    sentence = None
    with selection.restored_all():
        try:
            report = services["ClothesService"].mesh_is_valid_as_clothes(blender_object, basemesh)
        except Exception as error:  # pylint: disable=broad-except
            sentence = "MPFB's validator raised {:s}: {!s}".format(type(error).__name__, error)
    for mesh in list(bpy.data.meshes):
        if mesh.name not in meshes_before and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    if cache_directory and not cache_existed and os.path.isdir(cache_directory):
        try:
            os.rmdir(cache_directory)
        except OSError:
            # Something is in it, so it is not what this call created.
            pass
    return (report if report is None else dict(report), sentence)
