"""
``shared/mesh_overlap.py`` called directly, on meshes whose answers are known.

Cubes rather than characters, because a count on a character can only be compared
with itself. Two cubes overlapping by a known amount have a known box of intersection,
and two apart by a known gap have a known distance, so what is asserted here is
arithmetic rather than a snapshot. What a real character does is in
``ccc_reading/check_intersections_test.py``.

The claims this module is for:

- **Geometry is world space and evaluated**, so a moved object and a modifier's result
  are what is measured.
- **A mask is put back exactly, including after a failure**, and one a user turned off
  is left off.
- **The helper mask stays on and a proxy's inverted mask on the same group does not**,
  which is the request's rule refined by what MPFB actually carries.
- **Trees limited to a shared box give the same count as whole ones**, since the box is
  an optimisation and must be invisible.
"""

import bmesh
import bpy
import numpy
import pytest
from mathutils.bvhtree import BVHTree

from .. import bridge_module


def _overlap():
    return bridge_module("shared.mesh_overlap")


def _cube(name, location=(0.0, 0.0, 0.0), size=1.0, subdivisions=0):
    """A cube of side ``size`` centred at ``location``, linked to the current scene."""
    mesh = bpy.data.meshes.new(name)
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=size)
    if subdivisions:
        bmesh.ops.subdivide_edges(builder, edges=builder.edges[:], cuts=subdivisions,
                                  use_grid_fill=True)
    builder.to_mesh(mesh)
    builder.free()
    blender_object = bpy.data.objects.new(name, mesh)
    blender_object.location = location
    bpy.context.collection.objects.link(blender_object)
    bpy.context.view_layer.update()
    return blender_object


@pytest.fixture(name="made")
def _made():
    """What a test built, removed however it ends."""
    built = []
    yield built
    for blender_object in built:
        mesh = blender_object.data
        bpy.data.objects.remove(blender_object, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def _read(blender_objects, bodies=()):
    return _overlap().read_all(blender_objects, set(bodies))[0]


def test_two_overlapping_cubes_report_the_box_they_share(made):
    first = _cube("overlap_a")
    second = _cube("overlap_b", location=(0.75, 0.0, 0.0))
    made.extend((first, second))
    readings = _read(made)
    row = _overlap().pair_row(readings["overlap_a"], readings["overlap_b"])
    assert row["face_pairs"] > 0
    assert row["min_distance"] == 0.0, "two intersecting surfaces are 0.0 apart, unmeasured"
    # Where the faces lie: on the first cube's +X side and the second's -X side.
    region = row["region"]
    assert region["max"]["x"] == pytest.approx(1.25), "the far corner of the second cube's faces"
    assert region["min"]["x"] == pytest.approx(-0.5), "the far corner of the first cube's faces"
    assert "face_pairs_unmasked" not in row, "neither is a body, so nothing is hidden to report"


def test_a_separated_pair_has_no_region_and_its_gap_as_distance(made):
    made.append(_cube("gap_a"))
    made.append(_cube("gap_b", location=(1.25, 0.0, 0.0)))
    readings = _read(made)
    row = _overlap().pair_row(readings["gap_a"], readings["gap_b"])
    assert row["face_pairs"] == 0
    assert row["region"] is None
    assert row["min_distance"] == pytest.approx(0.25), "1.25 between centres less two half sides"


def test_a_moved_object_is_measured_where_it_stands(made):
    first = _cube("moved_a")
    second = _cube("moved_b", location=(5.0, 0.0, 0.0))
    made.extend((first, second))
    assert _overlap().pair_row(*[_read(made)[name] for name in ("moved_a", "moved_b")]
                               )["face_pairs"] == 0
    second.location = (0.5, 0.0, 0.0)
    assert _overlap().pair_row(*[_read(made)[name] for name in ("moved_a", "moved_b")]
                               )["face_pairs"] > 0, "a read must see the move without being told"


def test_an_evaluated_modifier_is_what_is_measured(made):
    first = _cube("evaluated_a")
    second = _cube("evaluated_b", location=(1.5, 0.0, 0.0))
    made.extend((first, second))
    displace = first.modifiers.new("along_x", "DISPLACE")
    displace.direction = "X"
    displace.mid_level = 0.0
    displace.strength = 1.0
    bpy.context.view_layer.update()
    readings = _read(made)
    assert _overlap().pair_row(readings["evaluated_a"], readings["evaluated_b"])["face_pairs"] > 0


def test_the_level_measured_at_is_reported(made):
    first = _cube("levels_a")
    made.append(first)
    subdivision = first.modifiers.new("Subdivision", "SUBSURF")
    subdivision.levels = 2
    subdivision.render_levels = 3
    bpy.context.view_layer.update()
    reading = _read(made)["levels_a"]
    assert reading.subdiv_levels == 2, "the viewport's, not the render's"
    assert len(reading.masked.triangles) == 12 * 16, "two levels make four faces of each, twice"
    subdivision.show_viewport = False
    assert _overlap().viewport_subdiv_levels(first) == 0


def test_a_self_row_leaves_out_neighbours_and_has_no_distance(made):
    made.append(_cube("self_clean", subdivisions=2))
    reading = _read(made)["self_clean"]
    row = _overlap().pair_row(reading, reading)
    assert row["face_pairs"] == 0, "every face of a clean cube touches only faces it shares with"
    assert row["min_distance"] is None


def test_a_mesh_through_itself_is_counted_once_per_pair(made):
    """Two crossing quads in one mesh, sharing no vertex."""
    mesh = bpy.data.meshes.new("crossing")
    mesh.from_pydata([(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1),
                      (0, -1, -1), (0, 1, -1), (0, 1, 1), (0, -1, 1)],
                     [], [(0, 1, 2, 3), (4, 5, 6, 7)])
    mesh.update()
    blender_object = bpy.data.objects.new("crossing", mesh)
    bpy.context.collection.objects.link(blender_object)
    made.append(blender_object)
    reading = _read(made)["crossing"]
    pairs = _overlap().overlapping_triangles(reading.masked, reading.masked)
    assert len(pairs) > 0
    assert (pairs[:, 0] < pairs[:, 1]).all(), "each pair once, not in both orders"


def test_trees_limited_to_the_shared_box_count_what_whole_trees_count(made):
    made.append(_cube("whole_a", subdivisions=5))
    made.append(_cube("whole_b", location=(0.6, 0.3, 0.1), subdivisions=5))
    readings = _read(made)
    one = readings["whole_a"].masked
    other = readings["whole_b"].masked
    limited = _overlap().overlapping_triangles(one, other)
    whole = numpy.array(one.tree.overlap(other.tree)).reshape(-1, 2)
    assert len(limited) > 0
    assert (sorted(map(tuple, limited.tolist())) == sorted(map(tuple, whole.tolist())))


def test_surfaces_whose_boxes_do_not_meet_build_nothing(made, monkeypatch):
    made.append(_cube("far_a"))
    made.append(_cube("far_b", location=(50.0, 0.0, 0.0)))
    readings = _read(made)
    module = _overlap()

    def unwanted(*_arguments):
        raise AssertionError("no tree should be built for boxes that do not meet")

    monkeypatch.setattr(module, "_tree_within", unwanted)
    assert len(module.overlapping_triangles(readings["far_a"].masked,
                                            readings["far_b"].masked)) == 0


def test_a_region_counts_only_faces_inside_it_and_leaves_axes_open(made):
    made.append(_cube("region_a", subdivisions=5))
    made.append(_cube("region_b", location=(0.5, 0.0, 0.0), subdivisions=5))
    readings = _read(made)
    module = _overlap()
    everywhere = module.pair_row(readings["region_a"], readings["region_b"])
    band = module.pair_row(readings["region_a"], readings["region_b"],
                           box={"min": {"z": 0.25}, "max": {}})
    nowhere = module.pair_row(readings["region_a"], readings["region_b"],
                              box={"min": {"z": 10.0}, "max": {}})
    assert 0 < band["face_pairs"] < everywhere["face_pairs"]
    assert band["region"]["min"]["z"] >= 0.1, "a face's centre decides, so its corner may be below"
    assert nowhere["face_pairs"] == 0
    assert nowhere["region"] is None
    assert nowhere["min_distance"] is None, "no vertex inside, so no distance to speak of"


def _masked_body(made, name, removed_group="Delete.test"):
    """A cube carrying MPFB's arrangement: a helper mask and a delete group's mask."""
    body = _cube(name, subdivisions=3)
    made.append(body)
    helpers = body.vertex_groups.new(name="body")
    helpers.add(range(len(body.data.vertices)), 1.0, "ADD")
    deleted = body.vertex_groups.new(name=removed_group)
    deleted.add([vertex.index for vertex in body.data.vertices if vertex.co.x > 0.1], 1.0, "ADD")
    hide_helpers = body.modifiers.new("Hide helpers", "MASK")
    hide_helpers.vertex_group = "body"
    delete_mask = body.modifiers.new(removed_group, "MASK")
    delete_mask.vertex_group = removed_group
    delete_mask.invert_vertex_group = True
    bpy.context.view_layer.update()
    return (body, hide_helpers, delete_mask)


def test_a_body_is_read_twice_and_a_mask_can_hide_the_whole_intersection(made):
    _body, _hide_helpers, _delete_mask = _masked_body(made, "two_counts")
    garment = _cube("two_counts_garment", location=(0.75, 0.0, 0.0))
    made.append(garment)
    readings = _read(made, bodies=("two_counts",))
    row = _overlap().pair_row(readings["two_counts"], readings["two_counts_garment"])
    assert row["face_pairs"] == 0, "the mask removed everything the garment passes through"
    assert row["face_pairs_unmasked"] > 0, "which is the trap the second count exists for"
    assert row["region"] is None
    assert row["region_unmasked"] is not None
    assert row["min_distance"] > 0.0
    assert row["min_distance_unmasked"] == 0.0


def test_the_helper_mask_stays_on_and_the_inverted_one_on_its_group_does_not(made):
    body = _cube("mask_kinds", subdivisions=1)
    made.append(body)
    body.vertex_groups.new(name="body")
    hide_helpers = body.modifiers.new("Hide helpers", "MASK")
    hide_helpers.vertex_group = "body"
    hide_base_mesh = body.modifiers.new("Hide base mesh", "MASK")
    hide_base_mesh.vertex_group = "body"
    hide_base_mesh.invert_vertex_group = True
    module = _overlap()
    assert module.is_helper_mask(hide_helpers)
    assert not module.is_helper_mask(hide_base_mesh)
    assert module.body_masks(body) == [hide_base_mesh]


def test_masks_are_put_back_exactly_after_a_failure(made):
    body, hide_helpers, delete_mask = _masked_body(made, "failed_read")
    already_off = body.modifiers.new("Already off", "MASK")
    already_off.vertex_group = "Delete.test"
    already_off.show_viewport = False
    module = _overlap()
    with pytest.raises(RuntimeError):
        with module.masks_off([body]):
            assert delete_mask.show_viewport is False
            assert hide_helpers.show_viewport is True, "helper geometry is not skin"
            raise RuntimeError("induced")
    assert delete_mask.show_viewport is True
    assert hide_helpers.show_viewport is True
    assert already_off.show_viewport is False, "off before, so off after"
    after = module.read_surface(body, bpy.context.evaluated_depsgraph_get())
    reread = module.read_all([body], {"failed_read"})[0]["failed_read"].masked
    assert len(after.triangles) == len(reread.triangles), \
        "a read after the restore must see the mask on, which takes a depsgraph update"


def test_reading_changes_nothing_a_caller_can_see(made):
    body, _hide_helpers, delete_mask = _masked_body(made, "unobserved")
    module = _overlap()
    before_active = bpy.context.view_layer.objects.active
    before_selected = [o.name for o in bpy.context.selected_objects]
    before_meshes = len(bpy.data.meshes)
    module.read_all([body], {"unobserved"})
    assert delete_mask.show_viewport is True
    assert bpy.context.view_layer.objects.active == before_active
    assert [o.name for o in bpy.context.selected_objects] == before_selected
    assert len(bpy.data.meshes) == before_meshes, "to_mesh_clear() was reached for every read"


def test_an_unevaluated_mesh_is_reported_and_an_eye_hidden_one_is_measured(made):
    hidden = _cube("eye_hidden")
    gone = _cube("not_evaluated")
    made.extend((hidden, gone))
    hidden.hide_set(True)
    gone.hide_viewport = True
    bpy.context.view_layer.update()
    readings, unmeasured = _overlap().read_all(made, set())
    assert "eye_hidden" in readings
    assert [(entry.object_name, entry.reason) for entry in unmeasured] == [
        ("not_evaluated", "not_evaluated")]
    hidden.hide_set(False)


def test_a_mesh_with_no_faces_is_reported(made):
    mesh = bpy.data.meshes.new("faceless")
    mesh.from_pydata([(0, 0, 0)], [], [])
    faceless = bpy.data.objects.new("faceless", mesh)
    bpy.context.collection.objects.link(faceless)
    made.append(faceless)
    readings, unmeasured = _overlap().read_all(made, set())
    assert not readings
    assert unmeasured[0].reason == "no_faces"


def test_the_distance_agrees_with_a_brute_force_check(made):
    """Against every vertex by hand, so that the limit passed to the tree cannot hide one."""
    made.append(_cube("brute_a", subdivisions=3))
    made.append(_cube("brute_b", location=(1.4, 0.2, -0.3), subdivisions=3))
    readings = _read(made)
    one = readings["brute_a"].masked
    other = readings["brute_b"].masked
    expected = min(
        min(BVHTree.FromPolygons(other.vertices.tolist(), other.triangles.tolist(),
                                 all_triangles=True).find_nearest(point)[3]
            for point in one.vertices.tolist()),
        min(BVHTree.FromPolygons(one.vertices.tolist(), one.triangles.tolist(),
                                 all_triangles=True).find_nearest(point)[3]
            for point in other.vertices.tolist()))
    assert _overlap().closest_approach(one, other) == pytest.approx(expected)
