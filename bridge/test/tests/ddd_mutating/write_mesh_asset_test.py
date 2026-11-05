"""
``write_mesh_asset`` against a real MPFB: a mesh becomes an asset, and an asset goes back on a body.

**The mesh is a real one**, built by ``ObjectService.extract_vertex_group_to_new_object()`` from a
helper group, as MakeClothes' "Extract clothes" builds a draft, so that MPFB's validator and
matching have something real to judge. **Every test writes into a redirected data root or a
``tmp_path`` export directory**, per this directory's rule, and every refusal is compared against
the tree: a refused write leaving an empty directory is the first thing "Store in library" gets
wrong. Each test that writes an asset goes on to equip it where that is what it claims.

The xref cache is MPFB's real one except in the one test that builds it, which redirects it, since
building it takes half a minute.
"""

import contextlib
import hashlib
import os
import uuid

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import material_data_roots
from .._fixtures import mpfb_root
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import write
from .._fixtures import write_png

GROUP = "helper-tights"
BLOCKED_DIFFERENCE = "a refusal must leave the tree as it was"


def _result(params):
    return _fixture_result("write_mesh_asset", params)


def _tree(root):
    """Every file and directory under a root, to compare before and after a refusal."""
    found = []
    for dirpath, dirs, files in os.walk(str(root)):
        found.extend(os.path.join(dirpath, name) for name in dirs + files)
    return sorted(found)


def _digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _vertex_lines(path):
    with open(path, "r", encoding="utf8") as handle:
        return sum(1 for line in handle if line.startswith("v "))


def _mhclo_vertex_lines(path):
    with open(path, "r", encoding="utf8") as handle:
        lines = handle.read().split("verts 0\n", 1)[1].split("\n\n", 1)[0].splitlines()
    return len(lines)


def _extracted(services, basemesh, name="BridgeTestWriteMesh"):
    """A draft from a helper group, as MakeClothes' Extract clothes makes one."""
    before = set(blender_object.name for blender_object in bpy.data.objects)
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    services["ObjectService"].extract_vertex_group_to_new_object(basemesh, GROUP)
    mesh = next(blender_object for blender_object in bpy.data.objects
                if blender_object.name not in before)
    mesh.name = name
    # MPFB marks what it extracts. A mesh from generic Blender work arrives with no type.
    _general(services).set_value("object_type", "", entity_reference=mesh)
    bpy.ops.object.select_all(action="DESELECT")
    for blender_object in selected:
        blender_object.select_set(True)
    bpy.context.view_layer.objects.active = active
    return mesh


@contextlib.contextmanager
def _export_directory(path):
    module = bridge_module("export_directory")
    module.set_command_line(str(path))
    try:
        yield
    finally:
        module.set_command_line(None)


@pytest.fixture(name="draft")
def _draft(tmp_path):
    """A character, a draft mesh and a redirected, empty user data root."""
    services = _services_or_skip()
    root = tmp_path / "data"
    root.mkdir()
    with _Character() as character:
        mesh = _extracted(services, character.basemesh)
        with material_data_roots(services, str(root)):
            yield (character, mesh, root)


def _write(mesh, body, **params):
    params.setdefault("object_type", "Clothes")
    params.setdefault("license", "CC0")
    params.setdefault("author", "Somebody")
    return _result(dict(name=mesh.name, basemesh=body.name, **params))


# ----------------------------------------------------------------------------
# Writing
# ----------------------------------------------------------------------------


def test_a_library_write_lands_where_the_panel_puts_it(draft):
    character, mesh, root = draft
    answer = _write(mesh, character.basemesh, asset_name="my_gi")
    assert answer["written"] is True and answer["performed"] is True, answer["message"]
    directory = root / "clothes" / "my_gi"
    assert answer["path"] == str(directory / "my_gi.mhclo")
    assert answer["fragment"] == "my_gi/my_gi.mhclo"
    assert answer["path_resolved_by"] == "library"
    assert sorted(os.listdir(str(directory))) == ["my_gi.mhclo", "my_gi.obj"]
    rows = {row["kind"]: row for row in answer["files"]}
    assert rows["mhclo"]["action"] == "created"
    assert rows["mhclo"]["size_bytes"] == (directory / "my_gi.mhclo").stat().st_size
    assert rows["obj"]["path"] == str(directory / "my_gi.obj")
    assert not [name for name in os.listdir(str(root / "clothes")) if name.startswith(".")]
    assert answer["match_counts"]["exact"] + answer["match_counts"]["offset"] == len(
        mesh.data.vertices)
    assert answer["max_pole"] > 0
    text = (directory / "my_gi.mhclo").read_text()
    assert "name my_gi\n" in text and "obj_file my_gi.obj\n" in text
    assert "# license: CC0\n" in text and "# author: Somebody\n" in text
    assert "uuid {:s}\n".format(answer["uuid"]) in text


def test_an_export_directory_write_leaves_the_library_and_asset_source_alone(draft, tmp_path):
    character, mesh, root = draft
    exports = tmp_path / "exports"
    exports.mkdir()
    general = _general(_services_or_skip())
    general.set_value("asset_source", "was/was.mhclo", entity_reference=mesh)
    with _export_directory(exports):
        answer = _write(mesh, character.basemesh, asset_name="my_gi",
                        destination="export_directory")
    assert answer["path"] == str(exports / "my_gi" / "my_gi.mhclo")
    assert answer["path_resolved_by"] == "command_line"
    assert (exports / "my_gi" / "my_gi.obj").is_file()
    assert answer["asset_source_updated"] is False and answer["asset_source"] == "was/was.mhclo"
    assert general.get_value("asset_source", entity_reference=mesh) == "was/was.mhclo"
    assert _tree(root) == []
    assert answer["try_with"]["mpfb_add_asset"]["path"] == answer["path"]
    assert "fragment" not in answer["try_with"]["mpfb_add_asset"]


def test_a_missing_export_directory_is_refused_and_not_created(draft, tmp_path):
    character, mesh, _root = draft
    missing = tmp_path / "typo"
    with _export_directory(missing):
        answer = _write(mesh, character.basemesh, asset_name="my_gi",
                        destination="export_directory")
    assert answer["blocked_by"] == "export_directory_missing"
    assert not missing.exists()


def test_a_written_asset_goes_on_a_second_character_from_either_destination(draft, tmp_path):
    character, mesh, _root = draft
    services = _services_or_skip()
    exports = tmp_path / "exports"
    exports.mkdir()
    with _export_directory(exports):
        library = _write(mesh, character.basemesh, asset_name="my_gi", delete_group=None)
        elsewhere = _write(mesh, character.basemesh, asset_name="my_gi_two",
                           destination="export_directory")
    with _Character() as second:
        for how in (dict(fragment=library["fragment"]), dict(path=elsewhere["path"])):
            added = _fixture_result("add_asset", dict(
                name=second.basemesh.name, object_type="Clothes", **how))
            assert added["added"] is True, added["message"]
            equipped = bpy.data.objects[added["asset_object_name"]]
            assert len(equipped.data.vertices) == len(mesh.data.vertices)
            assert services["ObjectService"].get_object_type(equipped) == "Clothes"
        summary = _fixture_result("get_object_info", dict(name=equipped.name))
        assert summary["found"] is True


def test_the_recipe_try_with_names_calls_that_work(draft):
    character, mesh, _root = draft
    answer = _write(mesh, character.basemesh, asset_name="my_gi")
    calls = answer["try_with"]
    assert list(calls) == ["mpfb_create_human_from_preset", "mpfb_add_asset",
                           "mpfb_check_intersections"]
    with _Character() as second:
        arguments = dict(calls["mpfb_add_asset"], name=second.basemesh.name)
        added = _fixture_result("add_asset", arguments)
        assert added["added"] is True, added["message"]
        measured = _fixture_result("check_intersections", dict(name=second.basemesh.name))
        assert measured["pairs_measured"] >= 1


# ----------------------------------------------------------------------------
# What the object knows afterwards
# ----------------------------------------------------------------------------


def _general(services):
    return bridge_module("shared.mpfb_surface").general_object_properties(services)


def _clothes_properties():
    return bridge_module("shared.mpfb_surface").make_clothes_properties(mpfb_root())


def test_a_library_write_tells_the_object_what_it_became(draft):
    character, mesh, _root = draft
    services = _services_or_skip()
    general = _general(services)
    assert general.get_value("asset_source", entity_reference=mesh) in ("", None)
    answer = _write(mesh, character.basemesh, asset_name="my_gi", description="A gi.")
    assert answer["asset_source_updated"] is True and answer["asset_lists_refreshed"] is True
    assert general.get_value("asset_source", entity_reference=mesh) == "my_gi/my_gi.mhclo"
    assert general.get_value("object_type", entity_reference=mesh) == "Clothes"
    assert services["ClothesService"].find_clothes_absolute_path(mesh) == answer["path"]
    for key in ("asset_source", "object_type", "uuid", "license", "author", "description", "name"):
        assert key in answer["properties_set"], key
    clothes = _clothes_properties()
    assert clothes.get_value("author", entity_reference=mesh) == "Somebody"
    assert clothes.get_value("description", entity_reference=mesh) == "A gi."
    assert clothes.get_value("name", entity_reference=mesh) == "my_gi"
    listed = _fixture_result("list_assets", dict(asset_subdir="clothes", refresh=True))
    assert "my_gi/my_gi.mhclo" in [asset["fragment"] for asset in listed["assets"]]


def test_the_catalogues_find_it_through_the_object_after_a_library_write(draft):
    character, mesh, _root = draft
    _write(mesh, character.basemesh, asset_name="my_gi")
    answer = _fixture_result("list_asset_materials", dict(name=mesh.name))
    assert answer["default_material_reason"] != "mhclo_not_installed", answer
    info = _fixture_result("get_object_info", dict(name=mesh.name))["asset_info"]
    assert info["mhclo_path"].endswith("my_gi/my_gi.mhclo"), info


def test_a_uuid_is_generated_when_there_is_none_and_kept_across_an_overwrite(draft):
    character, mesh, _root = draft
    general = _general(_services_or_skip())
    first = _write(mesh, character.basemesh, asset_name="my_gi")
    assert first["uuid_resolved_by"] == "generated"
    uuid.UUID(first["uuid"])
    assert general.get_value("uuid", entity_reference=mesh) == first["uuid"]
    second = _write(mesh, character.basemesh, asset_name="my_gi", overwrite=True)
    assert second["uuid"] == first["uuid"] and second["uuid_resolved_by"] == "object"


def test_a_mesh_with_no_uuid_keeps_the_one_in_the_file_it_replaces(draft):
    character, mesh, _root = draft
    general = _general(_services_or_skip())
    first = _write(mesh, character.basemesh, asset_name="my_gi")
    general.set_value("uuid", "", entity_reference=mesh)
    second = _write(mesh, character.basemesh, asset_name="my_gi", overwrite=True)
    assert second["uuid"] == first["uuid"] and second["uuid_resolved_by"] == "existing_file"


def test_license_resolved_by_says_where_each_came_from(draft):
    character, mesh, _root = draft
    body = character.basemesh
    default = _result(dict(name=mesh.name, basemesh=body.name, asset_name="one",
                           object_type="Clothes", dry_run=True))
    assert default["license"] == "CC0" and default["license_resolved_by"] == "mpfb_default"
    assert default["author_resolved_by"] == "mpfb_default"
    assert any("license is MPFB's default" in warning for warning in default["warnings"])

    named = _result(dict(name=mesh.name, basemesh=body.name, asset_name="two",
                         object_type="Clothes", license="CC-BY", author="Somebody"))
    assert named["license_resolved_by"] == "argument" and named["author_resolved_by"] == "argument"
    assert not any("license is MPFB's default" in warning for warning in named["warnings"])

    # The argument went on the object, so now the object answers.
    kept = _result(dict(name=mesh.name, basemesh=body.name, asset_name="three"))
    assert kept["license"] == "CC-BY" and kept["license_resolved_by"] == "object"
    assert kept["author"] == "Somebody" and kept["author_resolved_by"] == "object"

    chosen = _clothes_properties()
    chosen.set_value("license", "CC0", entity_reference=mesh)
    # A chosen CC0 is not MPFB's default CC0, and that is the point of asking Blender.
    assert _result(dict(name=mesh.name, basemesh=body.name, asset_name="four", dry_run=True))[
        "license_resolved_by"] == "object"


def test_a_license_outside_mpfbs_list_is_refused(draft):
    character, mesh, root = draft
    answer = _write(mesh, character.basemesh, asset_name="my_gi", license="WTFPL")
    assert answer["blocked_by"] == "invalid_license"
    assert "CC-BY" in answer["known_values"]
    assert _tree(root) == []


# ----------------------------------------------------------------------------
# Matching, and the file matching the file
# ----------------------------------------------------------------------------


def test_the_obj_matches_the_mhclo_with_the_viewport_subdivision_raised(draft):
    character, mesh, _root = draft
    modifier = mesh.modifiers.new("Subdivision", "SUBSURF")
    modifier.levels = 1
    answer = _write(mesh, character.basemesh, asset_name="my_gi")
    stem = os.path.splitext(answer["path"])[0]
    assert _vertex_lines(stem + ".obj") == len(mesh.data.vertices)
    assert _mhclo_vertex_lines(answer["path"]) == len(mesh.data.vertices)
    # Put back as it was found, on, and the mesh still subdivided.
    assert modifier.show_viewport is True and modifier.levels == 1


def test_a_modifier_that_was_off_stays_off(draft):
    character, mesh, _root = draft
    modifier = mesh.modifiers.new("Subdivision", "SUBSURF")
    modifier.show_viewport = False
    _write(mesh, character.basemesh, asset_name="my_gi")
    assert modifier.show_viewport is False


def test_exact_matching_follows_the_panel_unless_named(draft):
    character, mesh, _root = draft
    body = character.basemesh
    settings = bridge_module("shared.mpfb_surface").make_clothes_scene_properties(mpfb_root())
    scene = bpy.context.scene
    was = settings.get_value("disable_exact_strategy", entity_reference=scene)
    try:
        settings.set_value("disable_exact_strategy", False, entity_reference=scene)
        allowed = _write(mesh, body, asset_name="a", dry_run=True)
        assert allowed["allow_exact_matching"] is True
        assert allowed["allow_exact_matching_resolved_by"] == "panel"
        settings.set_value("disable_exact_strategy", True, entity_reference=scene)
        disabled = _write(mesh, body, asset_name="a", dry_run=True)
        assert disabled["allow_exact_matching"] is False
        assert disabled["match_counts"]["exact"] < allowed["match_counts"]["exact"]
        named = _write(mesh, body, asset_name="a", dry_run=True, allow_exact_matching=True)
        assert named["allow_exact_matching"] is True
        assert named["allow_exact_matching_resolved_by"] == "argument"
    finally:
        settings.set_value("disable_exact_strategy", was, entity_reference=scene)


def test_a_delete_group_reaches_the_file_and_one_that_is_absent_says_so(draft):
    character, mesh, _root = draft
    body = character.basemesh
    group = body.vertex_groups.new(name="Delete.bridge_test")
    group.add([1, 2, 3, 9], 1.0, "ADD")
    answer = _write(mesh, body, asset_name="with_group", delete_group="Delete.bridge_test")
    assert answer["delete_vertices"] == 4 and answer["delete_group_resolved_by"] == "argument"
    with open(answer["path"], encoding="utf8") as handle:
        assert "delete_verts" in handle.read()
    assert _clothes_properties().get_value("delete_group", entity_reference=mesh) == \
        "Delete.bridge_test"

    body.vertex_groups.remove(group)
    without = _write(mesh, body, asset_name="without_group")
    assert without["delete_vertices"] == 0 and without["delete_group_resolved_by"] == "object"
    assert any("no delete group" in warning for warning in without["warnings"])


def test_a_delete_group_named_and_absent_is_refused(draft):
    character, mesh, root = draft
    answer = _write(mesh, character.basemesh, asset_name="my_gi", delete_group="NoSuchGroup")
    assert answer["blocked_by"] == "delete_group_not_found"
    assert _tree(root) == []


def test_a_missing_xref_cache_is_built_and_reported(draft, tmp_path, monkeypatch):
    character, mesh, _root = draft
    services = _services_or_skip()
    cache = tmp_path / "cache" / "basemesh_xref"
    monkeypatch.setattr(services["LocationService"], "get_user_cache",
                        lambda _name=None: str(cache))
    dry = _write(mesh, character.basemesh, asset_name="my_gi", dry_run=True)
    assert dry["xref_cache_built"] is False and dry["xref_cache_missing"] is True
    assert not cache.exists(), "a dry run builds nothing, and leaves no empty directory"

    # An empty directory is what MPFB's own validator leaves, and reads as a cache that exists.
    cache.mkdir(parents=True)
    answer = _write(mesh, character.basemesh, asset_name="my_gi")
    assert answer["xref_cache_built"] is True and answer["xref_cache_missing"] is False
    assert len(os.listdir(str(cache))) > 0
    again = _write(mesh, character.basemesh, asset_name="my_gi", overwrite=True)
    assert again["xref_cache_built"] is False


# ----------------------------------------------------------------------------
# The material
# ----------------------------------------------------------------------------


def _textured(mesh, directory):
    diffuse = write_png(os.path.join(str(directory), "src_diffuse.png"), (0.1, 0.2, 0.3, 1.0))
    answer = _fixture_result("set_makeskin_material", dict(
        name=mesh.name, material_name="made", replace=True,
        textures=dict(diffuse=dict(path=diffuse)),
        values=dict(roughness=dict(value=0.13))))
    assert answer["applied"] is True, answer["message"]
    return diffuse


def test_a_makeskin_material_is_written_and_its_source_is_untouched(draft, tmp_path):
    character, mesh, root = draft
    diffuse = _textured(mesh, tmp_path)
    digest = _digest(diffuse)
    modified = os.stat(diffuse).st_mtime_ns
    answer = _write(mesh, character.basemesh, asset_name="my_gi")
    directory = root / "clothes" / "my_gi"
    assert answer["material_written"] is True and answer["material_not_written_because"] is None
    assert sorted(os.listdir(str(directory))) == [
        "my_gi.mhclo", "my_gi.mhmat", "my_gi.obj", "my_gi_diffuse.png"]
    row = next(row for row in answer["files"] if row["kind"] == "texture")
    assert row["how"] == "copied" and row["source_path"] == diffuse and row["slot"] == "diffuse"
    assert _digest(row["path"]) == digest
    assert _digest(diffuse) == digest and os.stat(diffuse).st_mtime_ns == modified
    assert "material my_gi.mhmat\n" in (directory / "my_gi.mhclo").read_text()
    text = (directory / "my_gi.mhmat").read_text()
    assert "diffuseTexture my_gi_diffuse.png\n" in text
    assert "license CC0\n" in text and "author Somebody\n" in text
    assert "name my_gi\n" in text
    assert "roughness" in answer["values_not_restored"]
    assert answer["values_not_restored"]["roughness"]["stored"] == pytest.approx(0.13)


def test_an_untextured_makeskin_material_is_written(draft):
    character, mesh, root = draft
    answer = _fixture_result("set_makeskin_material", dict(
        name=mesh.name, material_name="plain", replace=True))
    assert answer["applied"] is True, answer["message"]
    assert _services_or_skip()["MaterialService"].identify_material(
        mesh.material_slots[0].material) == "gameengine"
    written = _write(mesh, character.basemesh, asset_name="my_gi")
    assert written["material_written"] is True
    assert (root / "clothes" / "my_gi" / "my_gi.mhmat").is_file()


def test_another_material_writes_none_and_says_why(draft):
    character, mesh, root = draft
    material = bpy.data.materials.new("BridgeTestForeign")
    material.use_nodes = True
    material.node_tree.nodes.new("ShaderNodeEmission")
    mesh.data.materials.append(material)
    try:
        answer = _write(mesh, character.basemesh, asset_name="my_gi")
    finally:
        mesh.data.materials.clear()
        bpy.data.materials.remove(material)
    assert answer["written"] is True and answer["material_written"] is False
    assert "BridgeTestForeign" in answer["material_not_written_because"]
    assert not (root / "clothes" / "my_gi" / "my_gi.mhmat").exists()
    assert "material " not in (root / "clothes" / "my_gi" / "my_gi.mhclo").read_text()


def test_write_material_false_writes_none(draft, tmp_path):
    character, mesh, root = draft
    _textured(mesh, tmp_path)
    answer = _write(mesh, character.basemesh, asset_name="my_gi", write_material=False)
    assert answer["material_written"] is False
    assert "write_material" in answer["material_not_written_because"]
    assert sorted(os.listdir(str(root / "clothes" / "my_gi"))) == ["my_gi.mhclo", "my_gi.obj"]


def test_a_texture_that_cannot_be_written_is_left_out_and_does_not_block(draft, tmp_path):
    character, mesh, root = draft
    diffuse = _textured(mesh, tmp_path)
    image = mesh.material_slots[0].material.node_tree.nodes["diffuseTexture"].image
    image.source = "SEQUENCE"
    try:
        answer = _write(mesh, character.basemesh, asset_name="my_gi")
    finally:
        image.source = "FILE"
    assert answer["written"] is True, answer["message"]
    assert [row["slot"] for row in answer["textures_left_out"]] == ["diffuse"]
    assert any("left out of the MHMAT" in warning for warning in answer["warnings"])
    assert os.path.isfile(diffuse)
    assert "diffuseTexture my_gi" not in (root / "clothes" / "my_gi" / "my_gi.mhmat").read_text()


def test_a_proxy_goes_to_its_section_with_its_extension_and_no_material(draft, tmp_path):
    character, mesh, root = draft
    _textured(mesh, tmp_path)
    answer = _write(mesh, character.basemesh, asset_name="my_proxy", object_type="proxymeshes")
    assert answer["object_type"] == "Proxymeshes"
    assert answer["path"] == str(root / "proxymeshes" / "my_proxy" / "my_proxy.proxy")
    assert answer["fragment"] == "my_proxy/my_proxy.proxy"
    assert answer["material_written"] is False
    assert sorted(os.listdir(str(root / "proxymeshes" / "my_proxy"))) == [
        "my_proxy.obj", "my_proxy.proxy"]
    assert _general(_services_or_skip()).get_value(
        "object_type", entity_reference=mesh) == "Proxymeshes"


def test_a_mesh_the_panel_marked_as_a_proxy_is_written_as_the_table_spells_it(draft):
    character, mesh, _root = draft
    general = _general(_services_or_skip())
    general.set_value("object_type", "Proxymesh", entity_reference=mesh)
    answer = _result(dict(name=mesh.name, basemesh=character.basemesh.name, asset_name="p",
                          license="CC0", author="Somebody"))
    assert answer["object_type"] == "Proxymeshes"
    assert answer["object_type_before"] == "Proxymesh"
    assert general.get_value("object_type", entity_reference=mesh) == "Proxymeshes"


# ----------------------------------------------------------------------------
# Overwriting, and what a call leaves behind
# ----------------------------------------------------------------------------


def test_overwrite_replaces_this_assets_files_and_nothing_beside_them(draft, tmp_path):
    character, mesh, root = draft
    _textured(mesh, tmp_path)
    first = _write(mesh, character.basemesh, asset_name="my_gi")
    directory = root / "clothes" / "my_gi"
    neighbours = (write(str(directory / "blue" / "blue.mhmat"), "name blue\n"),
                  write(str(directory / "my_gi.mhw"), "{}\n"),
                  write(str(directory / "my_gi.thumb"), "thumb\n"))
    before = (directory / "my_gi.mhclo").stat().st_size

    refused = _write(mesh, character.basemesh, asset_name="my_gi")
    assert refused["blocked_by"] == "asset_exists"
    assert refused["file_before"]["size_bytes"] == before
    assert refused["path"] == first["path"]
    assert str(directory / "my_gi.mhclo") in refused["existing_files"]

    answer = _write(mesh, character.basemesh, asset_name="my_gi", overwrite=True)
    assert answer["overwrote"] is True and answer["file_before"]["size_bytes"] == before
    assert {row["action"] for row in answer["files"]} == {"replaced"}
    for path in neighbours:
        assert os.path.isfile(path), path
    assert sorted(name for name in os.listdir(str(directory)) if name.startswith("my_gi.")) == [
        "my_gi.mhclo", "my_gi.mhmat", "my_gi.mhw", "my_gi.obj", "my_gi.thumb"]


def test_a_lone_leftover_of_this_asset_also_counts_as_existing(draft):
    character, mesh, root = draft
    leftover = write(str(root / "clothes" / "my_gi" / "my_gi.obj"), "v 0 0 0\n")
    answer = _write(mesh, character.basemesh, asset_name="my_gi")
    assert answer["blocked_by"] == "asset_exists" and answer["file_before"] is None
    assert answer["existing_files"] == [leftover]


def test_a_material_already_in_place_is_not_copied_over_itself(draft, tmp_path):
    character, mesh, root = draft
    _textured(mesh, tmp_path)
    written = _write(mesh, character.basemesh, asset_name="my_gi")
    row = next(row for row in written["files"] if row["kind"] == "texture")
    image = mesh.material_slots[0].material.node_tree.nodes["diffuseTexture"].image
    image.filepath = row["path"]
    image.reload()
    digest = _digest(row["path"])
    again = _write(mesh, character.basemesh, asset_name="my_gi", overwrite=True)
    texture = next(entry for entry in again["files"] if entry["kind"] == "texture")
    assert texture["how"] == "already_in_place" and texture["action"] == "kept"
    assert _digest(row["path"]) == digest
    assert "diffuseTexture my_gi_diffuse.png\n" in (
        root / "clothes" / "my_gi" / "my_gi.mhmat").read_text()


def test_a_dry_run_writes_nothing_and_changes_nothing(draft, tmp_path):
    character, mesh, root = draft
    _textured(mesh, tmp_path)
    general = _general(_services_or_skip())
    meshes = sorted(entry.name for entry in bpy.data.meshes)
    answer = _write(mesh, character.basemesh, asset_name="my_gi", dry_run=True)
    assert answer["ready"] is True and answer["written"] is False
    assert answer["performed"] is False
    assert not (root / "clothes" / "my_gi").exists()
    assert general.get_value("object_type", entity_reference=mesh) in ("", None)
    assert general.get_value("uuid", entity_reference=mesh) in ("", None)
    assert answer["properties_set"] == [] and answer["asset_source_updated"] is False
    assert {row["action"] for row in answer["files"]} == {"created"}
    assert answer["match_counts"]["exact"] + answer["match_counts"]["offset"] > 0
    assert answer["check"]["applies"] is True
    assert sorted(entry.name for entry in bpy.data.meshes) == meshes


def test_selection_and_active_are_unchanged_however_it_was(draft):
    character, mesh, _root = draft
    other = bpy.data.objects.new("BridgeTestWriteOther", None)
    bpy.context.scene.collection.objects.link(other)
    try:
        bpy.ops.object.select_all(action="DESELECT")
        other.select_set(True)
        bpy.context.view_layer.objects.active = other
        answer = _write(mesh, character.basemesh, asset_name="my_gi")
        assert answer["selection_restored"] is True
        assert list(bpy.context.selected_objects) == [other]
        assert bpy.context.view_layer.objects.active == other
    finally:
        bpy.data.objects.remove(other)


def test_a_call_leaves_no_objects_or_meshes_behind(draft):
    character, mesh, _root = draft
    objects = sorted(entry.name for entry in bpy.data.objects)
    meshes = sorted(entry.name for entry in bpy.data.meshes)
    _write(mesh, character.basemesh, asset_name="my_gi")
    assert sorted(entry.name for entry in bpy.data.objects) == objects
    assert sorted(entry.name for entry in bpy.data.meshes) == meshes


def test_the_check_is_the_one_check_mesh_asset_reads(draft):
    character, mesh, _root = draft
    answer = _write(mesh, character.basemesh, asset_name="my_gi", dry_run=True)
    report = _fixture_result("check_mesh_asset", dict(
        name=mesh.name, basemesh=character.basemesh.name, sections=["components"]))["components"]
    check = answer["check"]
    assert check["component_count"] == report["component_count"]
    for row, full in zip(check["rows"], report["rows"]):
        assert row["component"] == full["component"]
        assert row["outward_fraction"] == full["outward_fraction"]
        assert row["fit_offset"] == full["fit_offset"]
        assert row["body_face_pairs"] == full["overlap"]["body"]["face_pairs"]
        assert row["body_face_pairs_unmasked"] == full["overlap"]["body"]["face_pairs_unmasked"]
        assert row["self_face_pairs"] == full["overlap"]["self"]["face_pairs"]
    assert check["lowest_outward_fraction"] == min(
        row["outward_fraction"] for row in check["rows"])


# ----------------------------------------------------------------------------
# Refusals, every one leaving the tree as it was
# ----------------------------------------------------------------------------


def _refused(root, reason, **params):
    before = _tree(root)
    answer = _result(params)
    assert answer["blocked_by"] == reason, answer["message"]
    assert answer["written"] is False and answer["performed"] is False
    assert _tree(root) == before, BLOCKED_DIFFERENCE
    return answer


def test_who_and_what_refusals_write_nothing(draft):
    character, mesh, root = draft
    body = character.basemesh
    _refused(root, "subject_not_found", name="NoSuchObject", asset_name="a")
    assert _refused(root, "subject_is_basemesh", name=body.name, asset_name="a")
    _refused(root, "basemesh_not_found", name=mesh.name, basemesh="NoSuchBody", asset_name="a")
    _refused(root, "not_a_basemesh", name=mesh.name, basemesh=mesh.name, asset_name="a")
    assert "Clothes" in _refused(root, "object_type_required", name=mesh.name, basemesh=body.name,
                                 asset_name="a")["known_object_types"]
    for bad in ("Basemesh", "Skeleton", "Proxymesh", "Material"):
        answer = _refused(root, "unknown_object_type", name=mesh.name, basemesh=body.name,
                          asset_name="a", object_type=bad)
        assert "Proxymeshes" in answer["known_object_types"]


def test_not_a_mesh_is_refused(draft):
    _character, _mesh, root = draft
    empty = bpy.data.objects.new("BridgeTestWriteEmpty", None)
    bpy.context.scene.collection.objects.link(empty)
    try:
        _refused(root, "not_a_mesh", name=empty.name, asset_name="a")
    finally:
        bpy.data.objects.remove(empty)


def test_a_name_that_is_a_path_is_refused_on_this_side_too(draft):
    character, mesh, root = draft
    for name in ("../escape", "a/b", "my-gi", "a__b", ".hidden"):
        _refused(root, "invalid_name", name=mesh.name, basemesh=character.basemesh.name,
                 asset_name=name, object_type="Clothes")


def test_several_bodies_and_none_named_is_refused_with_candidates(draft):
    character, mesh, root = draft
    with _Character() as second:
        bpy.ops.object.select_all(action="DESELECT")
        answer = _refused(root, "basemesh_ambiguous", name=mesh.name, asset_name="a",
                          object_type="Clothes")
        assert sorted(answer["candidates"]) == sorted(
            [character.basemesh.name, second.basemesh.name])


def test_a_validator_failure_blocks_and_carries_its_report(draft):
    character, mesh, root = draft
    mesh.vertex_groups.clear()
    answer = _refused(root, "not_valid_as_asset", name=mesh.name,
                      basemesh=character.basemesh.name, asset_name="a", object_type="Clothes",
                      license="CC0")
    assert answer["validator"]["all_checks_ok"] is False


def test_a_measured_defect_does_not_block(draft):
    character, mesh, _root = draft
    for polygon in mesh.data.polygons:
        polygon.flip()
    mesh.data.update()
    answer = _write(mesh, character.basemesh, asset_name="inside_out")
    assert answer["written"] is True, answer["message"]
    assert answer["check"]["lowest_outward_fraction"] < 0.5


def test_a_body_in_edit_mode_is_refused(draft):
    character, mesh, root = draft
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        _refused(root, "not_in_object_mode", name=mesh.name, basemesh=character.basemesh.name,
                 asset_name="a", object_type="Clothes")
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def test_a_hidden_mesh_is_refused_rather_than_exported_empty(draft):
    character, mesh, root = draft
    mesh.hide_set(True)
    try:
        _refused(root, "mesh_not_visible", name=mesh.name, basemesh=character.basemesh.name,
                 asset_name="a", object_type="Clothes")
    finally:
        mesh.hide_set(False)


def test_a_shadowing_file_in_an_earlier_root_refuses(tmp_path):
    services = _services_or_skip()
    user = tmp_path / "user"
    earlier = tmp_path / "earlier"
    write(str(earlier / "clothes" / "my_gi" / "my_gi.mhclo"), "name my_gi\n")
    with _Character() as character:
        mesh = _extracted(services, character.basemesh)
        with material_data_roots(services, str(user)):
            real = services["AssetService"].get_available_data_roots
            services["AssetService"].get_available_data_roots = staticmethod(
                lambda: [str(earlier), str(user)])
            try:
                answer = _refused(tmp_path, "name_shadowed", name=mesh.name,
                                  basemesh=character.basemesh.name, asset_name="my_gi",
                                  object_type="Clothes", license="CC0")
                assert answer["shadowed_by"]["path"].startswith(str(earlier))
            finally:
                services["AssetService"].get_available_data_roots = staticmethod(real)


def test_a_failure_while_matching_leaves_no_file_and_no_directory(draft, monkeypatch):
    character, mesh, root = draft
    clothes_service = _services_or_skip()["ClothesService"]

    def raises(*_args, **_keywords):
        raise ValueError("Vertex 12 is not part of any group")

    monkeypatch.setattr(clothes_service, "create_mhclo_from_clothes_matching", raises)
    answer = _refused(root, "match_failed", name=mesh.name, basemesh=character.basemesh.name,
                      asset_name="my_gi", object_type="Clothes", license="CC0")
    assert "Vertex 12" in answer["message"]
    assert not (root / "clothes").exists() or not (root / "clothes" / "my_gi").exists()


def test_a_failure_while_writing_leaves_no_part_of_an_asset(draft, tmp_path, monkeypatch):
    character, mesh, root = draft
    _textured(mesh, tmp_path)
    module = bridge_module("commands.write_mesh_asset")

    def raises(*_args, **_keywords):
        raise OSError("the disk is full")

    monkeypatch.setattr(module, "_write_mhclo_and_obj", raises)
    answer = _refused(root, "write_failed", name=mesh.name, basemesh=character.basemesh.name,
                      asset_name="my_gi", object_type="Clothes", license="CC0")
    assert "the disk is full" in answer["message"]
    # The object was not told it became anything.
    assert _general(_services_or_skip()).get_value("object_type", entity_reference=mesh) in (
        "", None)


def test_an_obj_that_does_not_match_moves_nothing_into_place(draft, monkeypatch):
    character, mesh, root = draft
    module = bridge_module("commands.write_mesh_asset")
    monkeypatch.setattr(module, "_vertex_lines", lambda _path: 1)
    answer = _refused(root, "obj_does_not_match", name=mesh.name, basemesh=character.basemesh.name,
                      asset_name="my_gi", object_type="Clothes", license="CC0")
    assert "1 vertices" in answer["message"]
    assert not (root / "clothes" / "my_gi").exists()


def test_a_failed_write_keeps_modifiers_as_they_were(draft, monkeypatch):
    character, mesh, _root = draft
    modifier = mesh.modifiers.new("Subdivision", "SUBSURF")
    module = bridge_module("commands.write_mesh_asset")
    monkeypatch.setattr(module, "_vertex_lines", lambda _path: 1)
    _write(mesh, character.basemesh, asset_name="my_gi")
    assert modifier.show_viewport is True


# ----------------------------------------------------------------------------
# A body that would be baked into the file
# ----------------------------------------------------------------------------


@pytest.fixture(name="rigged_draft")
def _rigged_draft(tmp_path):
    services = _services_or_skip()
    root = tmp_path / "data"
    root.mkdir()
    with _Character() as character:
        rig = rigged_character(services, character, "default")
        mesh = _extracted(services, character.basemesh)
        with material_data_roots(services, str(root)):
            yield (character.basemesh, rig, mesh, root)


def test_a_posed_body_is_refused_naming_the_way_back(rigged_draft):
    basemesh, rig, mesh, root = rigged_draft
    bone = rig.pose.bones["upperleg01.L"]
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = (1.2, 0.0, 0.0)
    try:
        answer = _refused(root, "rig_not_at_rest", name=mesh.name, basemesh=basemesh.name,
                          asset_name="my_gi", object_type="Clothes", license="CC0")
        assert answer["rig_name"] == rig.name
        assert "upperleg01.L" in answer["posed_bones"]
        assert "mpfb_reset_pose" in answer["message"]
    finally:
        bone.rotation_euler = (0.0, 0.0, 0.0)
    assert _write(mesh, basemesh, asset_name="my_gi")["written"] is True


def test_a_rig_showing_its_rest_position_is_at_rest(rigged_draft):
    basemesh, rig, mesh, _root = rigged_draft
    bone = rig.pose.bones["upperleg01.L"]
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = (1.2, 0.0, 0.0)
    rig.data.pose_position = "REST"
    try:
        assert _write(mesh, basemesh, asset_name="my_gi", dry_run=True)["ready"] is True
    finally:
        rig.data.pose_position = "POSE"
        bone.rotation_euler = (0.0, 0.0, 0.0)


def test_a_generated_rigify_rig_at_rest_is_at_rest(tmp_path):
    # Rigify's deforming bones move through constraints, which do not land exactly on rest.
    services = _services_or_skip()
    root = tmp_path / "data"
    root.mkdir()
    with _Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        mesh = _extracted(services, character.basemesh)
        with material_data_roots(services, str(root)):
            answer = _write(mesh, character.basemesh, asset_name="my_gi", dry_run=True)
            assert answer["ready"] is True, answer["message"]
            hand = rig.pose.bones["hand_ik.L"]
            hand.location = (0.1, 0.0, 0.0)
            try:
                refused = _write(mesh, character.basemesh, asset_name="my_gi", dry_run=True)
                assert refused["blocked_by"] == "rig_not_at_rest"
                assert refused["posed_bone_count"] > 0
            finally:
                hand.location = (0.0, 0.0, 0.0)


def test_a_turned_body_is_refused_and_a_moved_one_is_not(draft):
    character, mesh, root = draft
    body = character.basemesh
    body.rotation_euler = (0.0, 0.0, 1.5708)
    try:
        answer = _refused(root, "character_turned", name=mesh.name, basemesh=body.name,
                          asset_name="my_gi", object_type="Clothes", license="CC0")
        assert answer["rotation_degrees"] == pytest.approx(90.0, abs=0.1)
        assert "mpfb_place_character" in answer["message"]
    finally:
        body.rotation_euler = (0.0, 0.0, 0.0)
    body.location = (2.0, 1.0, 0.0)
    mesh.location = (2.0, 1.0, 0.0)
    try:
        assert _write(mesh, body, asset_name="my_gi", dry_run=True)["ready"] is True
    finally:
        body.location = (0.0, 0.0, 0.0)
        mesh.location = (0.0, 0.0, 0.0)


def test_the_envelope_is_never_an_error_for_a_refusal(draft):
    character, mesh, _root = draft
    envelope = dispatch("write_mesh_asset", dict(
        name=mesh.name, basemesh=character.basemesh.name, asset_name="a"))
    assert envelope["status"] == "ok"
    assert envelope["result"]["blocked_by"] == "object_type_required"
