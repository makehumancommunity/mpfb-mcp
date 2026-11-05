"""
``shared/mesh_asset_report.py`` called directly, on meshes with known answers.

A sphere inside a larger sphere is a body and a garment whose fit is arithmetic, and
flipping a known number of its faces gives a known ``outward_fraction``. Spheres rather than
cubes, because the nearest surface to the face beside a cube's corner is a side at right
angles to it, which agrees with nothing, and a body has no such corners. Two UV islands placed
by hand give a known overlap, and an area given in advance gives a known resolution.

What a real character and MPFB's validator do is ``ccc_reading/check_mesh_asset_test.py``'s.
"""

import os

import bmesh
import bpy
import pytest
from mathutils import Matrix

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import services_or_skip


def _report():
    return bridge_module("shared.mesh_asset_report")


def _overlap():
    return bridge_module("shared.mesh_overlap")


def _link(name, mesh):
    blender_object = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(blender_object)
    bpy.context.view_layer.update()
    return blender_object


def _sphere_mesh(name, radius, flipped=0, subdivisions=2):
    """A closed sphere of 80 faces by default, outward unless ``flipped`` were reversed."""
    mesh = bpy.data.meshes.new(name)
    builder = bmesh.new()
    bmesh.ops.create_icosphere(builder, subdivisions=subdivisions, radius=radius)
    if flipped:
        builder.faces.ensure_lookup_table()
        bmesh.ops.reverse_faces(builder, faces=builder.faces[:flipped])
    builder.to_mesh(mesh)
    builder.free()
    return mesh


def _cube_mesh(name, size):
    """A closed cube mesh, for what is not about facing."""
    mesh = bpy.data.meshes.new(name)
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=size)
    builder.to_mesh(mesh)
    builder.free()
    return mesh


@pytest.fixture(name="made")
def _made():
    built = []
    yield built
    for blender_object in built:
        mesh = blender_object.data
        bpy.data.objects.remove(blender_object, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def _components(made, garment, body):
    made.extend((garment, body))
    readings, _unmeasured = _overlap().read_all([garment, body], {body.name}, with_groups=True)
    return _report().component_report(readings[garment.name], readings[body.name],
                                      [str(group.name) for group in garment.vertex_groups])


def test_a_garment_outside_a_body_is_outward_with_a_positive_fit(made):
    body = _link("fit_body", _sphere_mesh("fit_body", 0.5, subdivisions=4))
    garment = _link("fit_garment", _sphere_mesh("fit_garment", 0.75))
    report = _components(made, garment, body)
    assert report["applies"] is True
    assert report["component_count"] == 1
    row = report["rows"][0]
    assert row["outward_fraction"] == 1.0
    assert row["fit_offset"]["min"] == pytest.approx(0.25, abs=0.01), "the radii differ by this"
    assert row["fit_offset"]["max"] == pytest.approx(0.25, abs=0.01)
    assert row["overlap"]["body"]["face_pairs"] == 0
    assert row["overlap"]["self"]["face_pairs"] == 0


def test_a_known_share_of_flipped_faces_is_the_outward_fraction(made):
    body = _link("flip_body", _sphere_mesh("flip_body", 0.5, subdivisions=4))
    garment = _link("flip_garment", _sphere_mesh("flip_garment", 0.75, flipped=20))
    row = _components(made, garment, body)["rows"][0]
    assert row["outward_fraction"] == 0.75, "twenty of the eighty are reversed"


def test_an_inside_out_garment_reads_zero(made):
    body = _link("inside_out_body", _sphere_mesh("inside_out_body", 0.5, subdivisions=4))
    garment = _link("inside_out_garment", _sphere_mesh("inside_out_garment", 0.75, flipped=80))
    assert _components(made, garment, body)["rows"][0]["outward_fraction"] == 0.0


def test_a_quad_counts_as_one_face_rather_than_two_triangles(made):
    mesh = _cube_mesh("quads", 1.5)
    builder = bmesh.new()
    builder.from_mesh(mesh)
    builder.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(builder, faces=builder.faces[:3])
    builder.to_mesh(mesh)
    builder.free()
    body = _link("quads_body", _sphere_mesh("quads_body", 0.5, subdivisions=4))
    row = _components(made, _link("quads", mesh), body)["rows"][0]
    assert row["faces"] == 6
    assert row["vertices"] == 8
    assert row["outward_fraction"] * 6 == pytest.approx(round(row["outward_fraction"] * 6)), \
        "a share of six faces rather than of twelve triangles"


def test_a_garment_inside_the_body_has_a_negative_fit(made):
    body = _link("inner_body", _sphere_mesh("inner_body", 0.5, subdivisions=4))
    garment = _link("inner_garment", _sphere_mesh("inner_garment", 0.25))
    fit = _components(made, garment, body)["rows"][0]["fit_offset"]
    assert fit["max"] < 0.0, "every vertex is inside"


def _two_parts(name):
    """Two connected components of different sizes, overlapping each other."""
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=1.4)
    second = bmesh.new()
    bmesh.ops.create_cube(second, size=1.4)
    bmesh.ops.subdivide_edges(second, edges=second.edges[:], cuts=2, use_grid_fill=True)
    bmesh.ops.translate(second, vec=(0.4, 0.0, 0.0), verts=second.verts)
    mesh = bpy.data.meshes.new(name)
    second.to_mesh(mesh)
    builder.from_mesh(mesh)
    builder.to_mesh(mesh)
    builder.free()
    second.free()
    return mesh


def test_components_are_found_largest_first_and_each_names_the_other(made):
    body = _link("parts_body", _cube_mesh("parts_body", 1.0))
    garment = _link("parts_garment", _two_parts("parts_garment"))
    report = _components(made, garment, body)
    assert report["component_count"] == 2
    assert report["components_truncated"] is False
    large, small = report["rows"]
    assert large["faces"] > small["faces"], "largest first"
    assert (large["component"], small["component"]) == (0, 1)
    assert large["overlap"]["other_components"][0]["component"] == 1
    assert small["overlap"]["other_components"][0]["component"] == 0
    assert (large["overlap"]["other_components"][0]["face_pairs"]
            == small["overlap"]["other_components"][0]["face_pairs"]), "the same pairs, seen twice"
    assert large["overlap"]["other_components"][0]["region"] is not None


def test_a_mesh_of_many_parts_lists_the_largest_and_counts_the_rest(made):
    builder = bmesh.new()
    count = _report().MAX_COMPONENTS + 3
    for index in range(count):
        bmesh.ops.create_cube(builder, size=0.1,
                              matrix=Matrix.Translation((index * 0.2, 2.0, 0.0)))
    mesh = bpy.data.meshes.new("many_parts")
    builder.to_mesh(mesh)
    builder.free()
    body = _link("many_parts_body", _cube_mesh("many_parts_body", 1.0))
    report = _components(made, _link("many_parts", mesh), body)
    assert report["component_count"] == count, "counted before the cap"
    assert report["components_truncated"] is True
    assert len(report["rows"]) == _report().MAX_COMPONENTS


def test_vertex_groups_are_named_per_component_and_loose_vertices_counted(made):
    mesh = _cube_mesh("grouped", 1.5)
    garment = _link("grouped", mesh)
    group = garment.vertex_groups.new(name="spine")
    group.add(range(4), 1.0, "ADD")
    garment.vertex_groups.new(name="unused")
    body = _link("grouped_body", _cube_mesh("grouped_body", 1.0))
    report = _components(made, garment, body)
    assert report["rows"][0]["vertex_groups"] == ["spine"]
    assert report["loose_vertices"] == 0


def _quads_with_uv(name, placements):
    """One flat quad per placement, ``(x_offset, (u0, v0, u1, v1))``, each of a square metre."""
    vertices = []
    faces = []
    for index, (offset, _box) in enumerate(placements):
        base = len(vertices)
        vertices.extend(((offset, 0, 0), (offset + 1, 0, 0), (offset + 1, 1, 0), (offset, 1, 0)))
        faces.append((base, base + 1, base + 2, base + 3))
        assert index == len(faces) - 1
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon, (_offset, (u_low, v_low, u_high, v_high)) in zip(mesh.polygons, placements):
        corners = ((u_low, v_low), (u_high, v_low), (u_high, v_high), (u_low, v_high))
        for loop, corner in zip(polygon.loop_indices, corners):
            uv_layer.uv[loop].vector = corner
    return mesh


def test_islands_and_resolution_are_arithmetic(made):
    garment = _link("uv_plain", _quads_with_uv("uv_plain", [(0, (0.0, 0.0, 0.5, 0.5)),
                                                            (2, (0.6, 0.6, 0.8, 0.8))]))
    made.append(garment)
    texture = dict(size=[1024, 1024], image_name="plain.png")
    report = _report().uv_report(garment, [texture])
    assert report["islands"] == 2
    assert report["overlapping_islands"] == 0
    assert report["faces_outside_unit_square"] == 0
    # A metre of quad across half of the map's side is 512 texels per metre.
    assert report["texels_per_metre"] == {"min": pytest.approx(204.8), "max": pytest.approx(512.0)}
    assert report["uv_units_per_metre"] == {"min": pytest.approx(0.2), "max": pytest.approx(0.5)}
    assert report["measured_against_image"]["size"] == [1024, 1024]
    assert report["lowest_islands"][0]["texels_per_metre"] == pytest.approx(204.8)
    assert report["lowest_islands"][0]["uv_box"] == {"min": [0.6, 0.6], "max": [0.8, 0.8]}


def test_no_image_leaves_texels_null_and_units_reported(made):
    garment = _link("uv_no_image", _quads_with_uv("uv_no_image", [(0, (0.0, 0.0, 0.5, 0.5))]))
    made.append(garment)
    report = _report().uv_report(garment, [])
    assert report["texels_per_metre"] is None, "not computed, since there is nothing to count"
    assert report["uv_units_per_metre"]["max"] == pytest.approx(0.5)


def test_overlapping_and_touching_islands_are_told_apart(made):
    garment = _link("uv_overlap", _quads_with_uv("uv_overlap", [
        (0, (0.0, 0.0, 0.5, 0.5)),
        (2, (0.25, 0.25, 0.75, 0.75)),
        (4, (0.75, 0.0, 1.0, 0.25)),
    ]))
    made.append(garment)
    report = _report().uv_report(garment, [])
    assert report["islands"] == 3
    assert report["overlapping_islands"] == 2
    pair = report["overlapping_pairs"][0]
    assert (pair["island"], pair["other_island"]) == (0, 1)
    assert pair["uv_box"] == {"min": [0.25, 0.25], "max": [0.5, 0.5]}


def test_polygons_are_on_one_island_only_through_an_edge_they_share(made):
    """Blender's own helper would join two islands that merely touch at a corner's value."""
    corner_to_corner = _link("uv_corners", _quads_with_uv("uv_corners", [
        (0, (0.0, 0.0, 0.5, 0.5)), (2, (0.5, 0.5, 1.0, 1.0))]))
    made.append(corner_to_corner)
    assert _report().uv_report(corner_to_corner, [])["islands"] == 2

    joined = bpy.data.meshes.new("uv_joined")
    joined.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0), (2, 1, 0)], [],
                       [(0, 1, 2, 3), (1, 4, 5, 2)])
    joined.update()
    uv_layer = joined.uv_layers.new(name="UVMap")
    corners = ((0.0, 0.0), (0.25, 0.0), (0.25, 0.25), (0.0, 0.25),
               (0.25, 0.0), (0.5, 0.0), (0.5, 0.25), (0.25, 0.25))
    for loop, corner in enumerate(corners):
        uv_layer.uv[loop].vector = corner
    connected = _link("uv_joined", joined)
    made.append(connected)
    assert _report().uv_report(connected, [])["islands"] == 1, "a shared edge, seamless"

    for loop, corner in zip(range(4, 8), ((0.5, 0.5), (0.75, 0.5), (0.75, 0.75), (0.5, 0.75))):
        uv_layer.uv[loop].vector = corner
    assert _report().uv_report(connected, [])["islands"] == 2, "the same edge with a seam on it"


def test_faces_outside_the_unit_square_are_counted(made):
    garment = _link("uv_outside", _quads_with_uv("uv_outside", [
        (0, (0.0, 0.0, 1.0, 1.0)), (2, (1.5, 0.0, 2.0, 0.5))]))
    made.append(garment)
    assert _report().uv_report(garment, [])["faces_outside_unit_square"] == 1


def test_a_mesh_with_no_uv_map_says_so(made):
    garment = _link("uv_none", _cube_mesh("uv_none", 1.0))
    made.append(garment)
    report = _report().uv_report(garment, [])
    assert report["applies"] is False
    assert "UV" in report["reason"]


def _material_with_image(name, image, grouped=False):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    if grouped:
        group = bpy.data.node_groups.new(name + "_group", "ShaderNodeTree")
        tree = group
        holder = material.node_tree.nodes.new("ShaderNodeGroup")
        holder.node_tree = group
    node = tree.nodes.new("ShaderNodeTexImage")
    node.name = "diffuseTexture"
    node.image = image
    return material


def test_a_texture_row_says_what_a_write_would_need(made, tmp_path):
    garment = _link("tex", _cube_mesh("tex", 1.0))
    made.append(garment)
    path = str(tmp_path / "missing.png")
    image = bpy.data.images.new("tex_image", 4, 2)
    image.filepath_raw = path
    garment.data.materials.append(_material_with_image("tex_material", image))
    empty = bpy.data.materials.new("tex_empty")
    empty.use_nodes = True
    empty.node_tree.nodes.new("ShaderNodeTexImage")
    garment.data.materials.append(empty)
    garment.data.materials.append(_material_with_image(
        "tex_nested", bpy.data.images.new("tex_nested_image", 2, 2), grouped=True))
    rows = _report().textures(garment)
    assert [row["material_name"] for row in rows] == ["tex_material", "tex_empty", "tex_nested"], \
        "an image node inside a node group counts too"
    row = rows[0]
    assert row["slot"] == "diffuseTexture"
    assert row["image_name"] == "tex_image"
    assert row["path"] == os.path.normpath(path)
    assert row["file_exists"] is False
    assert row["size"] == [4, 2]
    assert row["packed"] is False
    assert rows[1]["image_name"] is None, "a node with no image is still a row"


def test_metadata_tells_a_set_value_from_mpfbs_default():
    services = services_or_skip()
    root = bridge_module("shared.mpfb_surface")
    module_name = services["ObjectService"].__module__.rsplit(".services", 1)[0]
    if root.make_clothes_properties(module_name) is None:
        pytest.skip("MPFB's MakeClothes properties are not loaded here")
    mesh = bpy.data.meshes.new("meta")
    garment = _link("meta", mesh)
    try:
        report = _report()
        before = report.metadata(services, module_name, garment)
        license_before = before["makeclothes"]["values"]["license"]
        assert license_before == {"value": "CC0", "set": False}, "CC0 by default, chosen by nobody"
        properties = root.make_clothes_properties(module_name)
        properties.set_value("license", "CC0", entity_reference=garment)
        after = report.metadata(services, module_name, garment)
        assert after["makeclothes"]["values"]["license"] == {"value": "CC0", "set": True}, \
            "the same value, now chosen, which FR 050 asked whether anything could tell"
        assert after["general"]["applies"] is True
        assert after["makeskin"]["applies"] is True
    finally:
        bpy.data.objects.remove(garment, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def test_a_disagreement_between_makeclothes_and_makeskin_is_a_warning():
    def group(license_value, author):
        return dict(applies=True, values=dict(license=dict(value=license_value, set=True),
                                              author=dict(value=author, set=False)))

    warnings = _report().metadata_warnings(dict(makeclothes=group("CC0", "A"),
                                                makeskin=group("CC-BY", "A")))
    assert len(warnings) == 1
    assert "license" in warnings[0] and "MHMAT" in warnings[0]
    assert not _report().metadata_warnings(dict(makeclothes=group("CC0", "A"),
                                                makeskin=group("CC0", "A")))
    assert not _report().metadata_warnings(dict(makeclothes=dict(applies=False, reason="x"),
                                                makeskin=group("CC0", "A")))


def test_mpfbs_validator_leaves_nothing_behind():
    """The object list, the selection, the active object, and the copy's mesh data."""
    services = services_or_skip()
    with Character() as character:
        garment = _link("left_nothing", _cube_mesh("left_nothing", 1.5))
        group = garment.vertex_groups.new(name="body")
        group.add(range(len(garment.data.vertices)), 1.0, "ADD")
        bpy.context.view_layer.objects.active = garment
        garment.select_set(True)
        objects_before = sorted(o.name for o in bpy.data.objects)
        meshes_before = sorted(m.name for m in bpy.data.meshes)
        selected_before = sorted(o.name for o in bpy.context.selected_objects)
        report, sentence = _report().validator(services, garment, character.basemesh)
        assert sentence is None
        assert isinstance(report["all_checks_ok"], bool)
        assert sorted(o.name for o in bpy.data.objects) == objects_before
        assert sorted(m.name for m in bpy.data.meshes) == meshes_before, \
            "MeshCrossRef deletes its copy's object and leaves the copied mesh data"
        assert sorted(o.name for o in bpy.context.selected_objects) == selected_before
        assert bpy.context.view_layer.objects.active == garment
        mesh = garment.data
        bpy.data.objects.remove(garment, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def test_a_raising_validator_is_a_sentence_rather_than_a_failure():
    services = dict(services_or_skip())

    class Raising:
        @staticmethod
        def mesh_is_valid_as_clothes(_mesh, _basemesh):
            raise ValueError("induced")

    services["ClothesService"] = Raising
    with Character() as character:
        report, sentence = _report().validator(services, character.basemesh, character.basemesh)
    assert report is None
    assert "induced" in sentence


def test_a_cache_directory_the_validator_creates_is_removed_and_never_read_as_a_cache(tmp_path):
    """MeshCrossRef creates ``cache_dir``, and MPFB's panel then reads that as a built cache."""
    services = services_or_skip()
    absent = tmp_path / "basemesh_xref"

    class Location:
        @staticmethod
        def get_user_cache(_sub_path):
            return str(absent)

    class Creating:
        @staticmethod
        def mesh_is_valid_as_clothes(_mesh, _basemesh):
            os.makedirs(str(absent))
            return dict(all_checks_ok=True)

    replaced = dict(services, LocationService=Location, ClothesService=Creating)
    with Character() as character:
        report, _sentence = _report().validator(replaced, character.basemesh, character.basemesh)
    assert report["all_checks_ok"] is True
    assert not absent.exists(), "it did not exist before the call"

    os.makedirs(str(absent))
    with Character() as character:
        state = _report().write_state(dict(services, LocationService=Location), "no.such.root",
                                      character.basemesh, character.basemesh)
    assert state["xref_cache_exists"] is False, "an empty directory is not a cache"
    (absent / "vertices_without_group.npy").write_bytes(b"")
    with Character() as character:
        state = _report().write_state(dict(services, LocationService=Location), "no.such.root",
                                      character.basemesh, character.basemesh)
    assert state["xref_cache_exists"] is True
    assert state["delete_group"]["name"] is None, "the property set is not reachable from that root"


def test_the_summary_reduces_one_reading_and_invents_nothing():
    # FR 050's write answer carries this, so it must be arithmetic on the report and no more.
    module = bridge_module("shared.mesh_asset_report")
    rows = [dict(component=0, faces=20, outward_fraction=0.9, fit_offset=dict(min=0.0, max=0.1),
                 overlap=dict(body=dict(face_pairs=2, face_pairs_unmasked=30),
                              self=dict(face_pairs=4), other_components_intersecting=1)),
            dict(component=1, faces=10, outward_fraction=0.4, fit_offset=None,
                 overlap=dict(body=dict(face_pairs=0, face_pairs_unmasked=7),
                              self=dict(face_pairs=9), other_components_intersecting=0))]
    summary = module.check_summary(dict(
        applies=True, measured_against="Human", component_count=3, components_truncated=True,
        rows=rows))
    assert summary["lowest_outward_fraction"] == 0.4
    assert summary["largest_body_face_pairs_unmasked"] == 30
    assert summary["largest_self_face_pairs"] == 9
    assert summary["component_count"] == 3 and summary["components_truncated"] is True
    assert summary["rows"][1] == dict(
        component=1, faces=10, outward_fraction=0.4, fit_offset=None, body_face_pairs=0,
        body_face_pairs_unmasked=7, self_face_pairs=9, other_components_intersecting=0)


def test_a_summary_of_nothing_measured_says_why():
    module = bridge_module("shared.mesh_asset_report")
    reason = dict(applies=False, reason="The mesh has no faces to measure.")
    assert module.check_summary(reason) == reason


def test_debris_is_what_the_block_left_and_nothing_older():
    services = services_or_skip()
    module = bridge_module("shared.mesh_asset_report")
    older = bpy.data.meshes.new("BridgeTestOlderOrphan")
    try:
        with module.debris_removed(services):
            bpy.data.meshes.new("BridgeTestNewOrphan")
        assert "BridgeTestNewOrphan" not in bpy.data.meshes
        assert "BridgeTestOlderOrphan" in bpy.data.meshes
    finally:
        bpy.data.meshes.remove(older)
