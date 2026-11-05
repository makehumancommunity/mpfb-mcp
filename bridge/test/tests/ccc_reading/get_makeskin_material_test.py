"""
``get_makeskin_material`` against a real MPFB: what a MakeSkin material holds.

Every material here is built by MPFB's own ``MakeSkinMaterial`` from a real MHMAT and real
PNGs, the way a user's panel builds one, so that the reader is asked about the trees MPFB
makes rather than about the ones ``set_makeskin_material`` makes. Nothing here changes
anything, which the last test holds it to.
"""

import os

import bpy
import pytest

from .._fixtures import dispatch
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import write_mhmat
from .._fixtures import write_png

MESH = "BridgeTestMakeSkinReader"


def _result(name=MESH):
    return _fixture_result("get_makeskin_material", dict(name=name))


@pytest.fixture(name="mesh")
def _mesh():
    _services_or_skip()
    images_before = set(bpy.data.images.keys())
    materials_before = set(bpy.data.materials.keys())
    data = bpy.data.meshes.new(MESH)
    data.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)])
    blender_object = bpy.data.objects.new(MESH, data)
    bpy.context.scene.collection.objects.link(blender_object)
    yield blender_object
    bpy.data.objects.remove(blender_object)
    bpy.data.meshes.remove(data)
    for name in set(bpy.data.materials.keys()) - materials_before:
        bpy.data.materials.remove(bpy.data.materials[name])
    for name in set(bpy.data.images.keys()) - images_before:
        bpy.data.images.remove(bpy.data.images[name])


def _built_by_mpfb(mesh, root, lines):
    """A material through MPFB's own parser and template, as its import panel builds one."""
    services = _services_or_skip()
    module = __import__("sys").modules[services["HumanService"].__module__]
    path = write_mhmat(os.path.join(str(root), "material.mhmat"), lines=lines)
    material = services["MaterialService"].create_empty_material("from_mpfb", mesh)
    entity = module.MakeSkinMaterial()
    entity.populate_from_mhmat(path)
    entity.apply_node_tree(material)
    return material


def test_a_textured_material_reads_slot_by_slot(mesh, tmp_path):
    diffuse = write_png(str(tmp_path / "c.png"))
    normal = write_png(str(tmp_path / "n.png"))
    _built_by_mpfb(mesh, tmp_path, ["diffuseTexture c.png", "normalmapTexture n.png"])
    answer = _result()
    assert answer["ready"] is True, answer["message"]
    assert answer["material_identified_as"] == "makeskin"
    assert answer["recognized_by"] == "identify_material"
    assert sorted(answer["textures"]) == ["diffuse", "normalmap"]
    entry = answer["textures"]["diffuse"]
    assert entry["path"] == diffuse and entry["resolved_path"] == diffuse
    assert entry["file_exists"] is True and entry["wired"] is True
    assert entry["size"] == [2, 2] and entry["color_space"] == "sRGB"
    assert entry["packed"] is False and entry["unsaved_changes"] is False
    assert entry["strength_value"] == "diffuseIntensity"
    assert answer["textures"]["normalmap"]["path"] == normal
    assert answer["textures"]["normalmap"]["color_space"] == "Non-Color"
    assert answer["textures"]["normalmap"]["strength_value"] == "normalmapIntensity"
    assert answer["known_slots"]
    assert answer["empty_slots"] == []


def test_a_value_beside_its_map_is_not_in_effect(mesh, tmp_path):
    """The third item under NEXT_STEPS' *Worth raising in MPFB*, answered for a reader."""
    write_png(str(tmp_path / "r.png"))
    _built_by_mpfb(mesh, tmp_path, ["roughnessmapTexture r.png"])
    values = _result()["values"]
    assert values["roughness"]["in_effect"] is False
    assert values["roughness"]["overridden_by"] == "roughnessmap"
    assert values["metallic"]["in_effect"] is True
    assert values["metallic"]["overridden_by"] is None
    assert values["roughness"]["range"] == [0.0, 1.0]


def test_a_specular_map_overrides_roughness_through_its_invert(mesh, tmp_path):
    write_png(str(tmp_path / "s.png"))
    _built_by_mpfb(mesh, tmp_path, ["specularmapTexture s.png"])
    assert _result()["values"]["roughness"]["overridden_by"] == "specularmap"


def test_a_strength_with_no_map_to_scale_is_not_in_effect(mesh, tmp_path):
    write_png(str(tmp_path / "n.png"))
    _built_by_mpfb(mesh, tmp_path, ["normalmapTexture n.png"])
    values = _result()["values"]
    assert values["normalmapIntensity"]["in_effect"] is True
    # The bump node exists to pass a normal map on, and with no bump map scales nothing.
    assert values["bumpmapIntensity"]["in_effect"] is False
    assert values["bumpmapIntensity"]["needs_slot"] == "bumpmap"


def test_the_diffuse_colour_behind_a_texture_shows_only_below_a_full_mix(mesh, tmp_path):
    write_png(str(tmp_path / "c.png"))
    material = _built_by_mpfb(mesh, tmp_path, ["diffuseTexture c.png"])
    values = _result()["values"]
    assert values["diffuseColor"]["in_effect"] is False
    assert values["diffuseColor"]["overridden_by"] == "diffuse"
    assert values["diffuseColor"]["srgb_hex"].startswith("#")
    material.node_tree.nodes["diffuseIntensity"].inputs[0].default_value = 0.5
    assert _result()["values"]["diffuseColor"]["in_effect"] is True


def test_what_the_tree_has_no_socket_for_is_absent_with_the_slot_that_would_give_it(
        mesh, tmp_path):
    _built_by_mpfb(mesh, tmp_path, [])
    answer = _result()
    assert "normalmapIntensity" not in answer["values"]
    assert answer["values_absent"]["normalmapIntensity"] == ["normalmap"]
    assert answer["values_absent"]["bumpmapIntensity"] == ["bumpmap", "normalmap"]
    assert answer["values_absent"]["displacementMapIntensity"] == ["displacementmap"]
    assert answer["values_absent"]["diffuseIntensity"] == ["diffuse"]


def test_an_untextured_material_is_accepted_though_mpfb_calls_it_gameengine(mesh, tmp_path):
    _built_by_mpfb(mesh, tmp_path, ["diffuseColor 0.1 0.2 0.3"])
    answer = _result()
    assert answer["ready"] is True, answer["message"]
    assert answer["material_identified_as"] == "gameengine"
    assert answer["recognized_by"] == "template_nodes"
    assert answer["values"]["diffuseColor"]["in_effect"] is True
    assert answer["textures"] == {}


def test_an_image_with_unsaved_changes_answers_with_image_not_path(mesh, tmp_path):
    """So that a read-back sent to the writer reproduces the live pixels."""
    write_png(str(tmp_path / "c.png"))
    material = _built_by_mpfb(mesh, tmp_path, ["diffuseTexture c.png"])
    image = material.node_tree.nodes["diffuseTexture"].image
    image.pixels[0] = 0.125
    entry = _result()["textures"]["diffuse"]
    assert entry["image"] == image.name and "path" not in entry
    assert entry["unsaved_changes"] is True and entry["file_exists"] is True
    assert entry["resolved_path"] == str(tmp_path / "c.png")


def test_a_file_that_has_gone_is_reported(mesh, tmp_path):
    path = write_png(str(tmp_path / "c.png"))
    material = _built_by_mpfb(mesh, tmp_path, ["diffuseTexture c.png"])
    assert material.node_tree.nodes["diffuseTexture"].image.size[0] == 2
    os.remove(path)
    entry = _result()["textures"]["diffuse"]
    assert entry["file_exists"] is False and "image" in entry and "path" not in entry


def test_a_blank_node_is_an_empty_slot(mesh, tmp_path):
    write_png(str(tmp_path / "c.png"))
    material = _built_by_mpfb(mesh, tmp_path, ["diffuseTexture c.png"])
    material.node_tree.nodes["diffuseTexture"].image = None
    answer = _result()
    assert answer["empty_slots"] == ["diffuse"]
    assert "diffuse" not in answer["textures"]


def test_metadata_says_what_is_still_mpfbs_default(mesh, tmp_path):
    _built_by_mpfb(mesh, tmp_path, [])
    answer = _result()
    assert answer["metadata"]["license"] == "CC0"
    assert "license" in answer["metadata_unset"]
    assert "name" not in answer["metadata"]
    assert answer["metadata"]["backfaceCull"] is True


def test_refusals(mesh):
    assert _result("BridgeTestNoSuchObject")["blocked_by"] == "subject_not_found"
    assert _result("BridgeTestNoSuchObject")["found"] is False

    answer = _result()
    assert answer["blocked_by"] == "no_material" and answer["found"] is True

    armature = bpy.data.armatures.new("bridge_test_reader_arm")
    armature_object = bpy.data.objects.new("bridge_test_reader_arm", armature)
    bpy.context.scene.collection.objects.link(armature_object)
    try:
        assert _result(armature_object.name)["blocked_by"] == "not_a_mesh"
    finally:
        bpy.data.objects.remove(armature_object)
        bpy.data.armatures.remove(armature)


def test_another_kind_of_material_is_not_makeskin(mesh):
    material = bpy.data.materials.new("bridge_test_other_kind")
    material.use_nodes = True
    material.node_tree.nodes.new("ShaderNodeEmission").name = "somebody's node"
    mesh.data.materials.append(material)
    answer = _result()
    assert answer["blocked_by"] == "not_makeskin"
    assert answer["material_identified_as"] == "gameengine"
    assert answer["material_name"] == material.name


def test_reading_changes_nothing(mesh, tmp_path):
    write_png(str(tmp_path / "c.png"))
    material = _built_by_mpfb(mesh, tmp_path, ["diffuseTexture c.png"])
    before = (sorted(bpy.data.images.keys()), sorted(bpy.data.materials.keys()),
              len(material.node_tree.nodes), len(material.node_tree.links))
    envelope = dispatch("get_makeskin_material", dict(name=mesh.name))
    assert envelope["status"] == "ok"
    assert "performed" not in envelope["result"]
    assert before == (sorted(bpy.data.images.keys()), sorted(bpy.data.materials.keys()),
                      len(material.node_tree.nodes), len(material.node_tree.links))
