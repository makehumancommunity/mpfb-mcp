"""
``set_makeskin_material`` against a real MPFB: a MakeSkin material from images and numbers.

Every image here is a real PNG written by Blender, and what the command builds is read
back through ``get_makeskin_material``, whose own module passed first. What each refusal
is asserted to leave is the point of most of these: **a refusal changes nothing**, the
mesh's material, the file's images and the file's materials all compared.
"""

import hashlib
import os

import bpy
import pytest

from .._fixtures import Character as _Character
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import write_png

CUBE = "BridgeTestMakeSkinCube"


def _result(params):
    return _fixture_result("set_makeskin_material", params)


def _read(name):
    return _fixture_result("get_makeskin_material", dict(name=name))


@pytest.fixture(name="cube")
def _cube():
    _services_or_skip()
    images_before = set(bpy.data.images.keys())
    materials_before = set(bpy.data.materials.keys())
    mesh = bpy.data.meshes.new(CUBE)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)])
    blender_object = bpy.data.objects.new(CUBE, mesh)
    bpy.context.scene.collection.objects.link(blender_object)
    yield blender_object
    bpy.data.objects.remove(blender_object)
    bpy.data.meshes.remove(mesh)
    for name in set(bpy.data.materials.keys()) - materials_before:
        bpy.data.materials.remove(bpy.data.materials[name])
    for name in set(bpy.data.images.keys()) - images_before:
        bpy.data.images.remove(bpy.data.images[name])


def _file_state():
    return (sorted(bpy.data.images.keys()), sorted(bpy.data.materials.keys()))


def _digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def test_an_untextured_material_is_built_and_recognised(cube):
    answer = _result(dict(name=cube.name, material_name="plain",
                          values=dict(diffuseColor=dict(color=[0.2, 0.3, 0.4, 1.0]),
                                      roughness=dict(value=0.25), metallic=dict(value=0.5),
                                      ior=dict(value=1.6))))
    assert answer["applied"] is True and answer["performed"] is True, answer["message"]
    assert answer["material_name"] == "plain"
    assert cube.material_slots[0].material.name == "plain"
    # MPFB's own verdict is gameengine, so the reader must have got there by the nodes.
    read = _read(cube.name)
    assert read["ready"] is True, read["message"]
    assert read["material_identified_as"] == "gameengine"
    assert read["recognized_by"] == "template_nodes"
    assert read["values"]["roughness"]["value"] == pytest.approx(0.25)
    assert read["values"]["metallic"]["value"] == pytest.approx(0.5)
    assert read["values"]["ior"]["value"] == pytest.approx(1.6)
    assert read["values"]["diffuseColor"]["color"][:3] == pytest.approx([0.2, 0.3, 0.4])


def test_each_slot_gets_the_colour_space_it_is_read_in(cube, tmp_path):
    paths = {slot: write_png(str(tmp_path / "{:s}.png".format(slot)))
             for slot in ("diffuse", "normalmap", "roughnessmap", "emissionColorMap",
                          "emissionStrengthMap", "bumpmap", "metallicmap", "aomap", "opacitymap",
                          "displacementmap", "transmissionmap", "subsurfaceStrengthMap")}
    answer = _result(dict(name=cube.name, material_name="spaces",
                          textures={slot: dict(path=path) for slot, path in paths.items()}))
    assert answer["applied"] is True, answer
    for slot, entry in answer["textures"].items():
        expected = "sRGB" if slot in ("diffuse", "emissionColorMap") else "Non-Color"
        assert entry["color_space"] == expected, slot
        assert entry["path"] == paths[slot]
        assert entry["wired"] is True, slot
        assert "image" not in entry


def test_a_blender_image_is_used_and_said_to_have_no_file(cube):
    image = bpy.data.images.new("bridge_test_baked", 4, 4)
    answer = _result(dict(name=cube.name, material_name="baked",
                          textures=dict(diffuse=dict(image=image.name))))
    assert answer["applied"] is True, answer
    entry = answer["textures"]["diffuse"]
    assert entry["image"] == image.name and "path" not in entry
    assert entry["file_exists"] is False and entry["resolved_path"] is None
    assert answer["unsaved_slots"] == ["diffuse"]
    assert "no file" in answer["message"]


def test_two_files_with_one_basename_do_not_share_pixels(cube, tmp_path):
    """``set_image_in_image_node()`` would have reused the first for the second."""
    red = write_png(str(tmp_path / "a" / "diffuse.png"), (1.0, 0.0, 0.0, 1.0))
    blue = write_png(str(tmp_path / "b" / "diffuse.png"), (0.0, 0.0, 1.0, 1.0))
    first = bpy.data.images.load(red)
    answer = _result(dict(name=cube.name, material_name="second",
                          textures=dict(diffuse=dict(path=blue))))
    assert answer["applied"] is True, answer
    image = cube.material_slots[0].material.node_tree.nodes["diffuseTexture"].image
    assert image != first
    assert image.pixels[2] == pytest.approx(1.0) and image.pixels[0] == pytest.approx(0.0)


def test_a_regenerated_file_shows_its_new_pixels(cube, tmp_path):
    path = write_png(str(tmp_path / "tex.png"), (1.0, 0.0, 0.0, 1.0))
    first = _result(dict(name=cube.name, material_name="one",
                         textures=dict(diffuse=dict(path=path))))
    assert first["reloaded"] == []
    image = cube.material_slots[0].material.node_tree.nodes["diffuseTexture"].image
    assert image.pixels[0] == pytest.approx(1.0)
    write_png(path, (0.0, 1.0, 0.0, 1.0))
    second = _result(dict(name=cube.name, material_name="one", replace=True,
                          textures=dict(diffuse=dict(path=path))))
    assert second["reloaded"] == ["diffuse"], second
    again = cube.material_slots[0].material.node_tree.nodes["diffuseTexture"].image
    assert again == image
    assert again.pixels[0] == pytest.approx(0.0) and again.pixels[1] == pytest.approx(1.0)


def test_an_image_with_unsaved_changes_is_not_reloaded_away(cube, tmp_path):
    path = write_png(str(tmp_path / "tex.png"), (1.0, 0.0, 0.0, 1.0))
    image = bpy.data.images.load(path)
    image.pixels[0] = 0.25
    assert image.is_dirty
    answer = _result(dict(name=cube.name, material_name="x",
                          textures=dict(diffuse=dict(path=path))))
    assert answer["blocked_by"] == "resolution_failed"
    row = answer["resolution_errors"][0]
    assert row["error"] == "image_has_unsaved_changes"
    assert image.name in row["message"]
    assert image.pixels[0] == pytest.approx(0.25, abs=0.01)


@pytest.mark.parametrize("textures, error", [
    (dict(nosuchslot=dict(image="x")), "unknown_slot"),
    (dict(diffuse=dict(path="/no/such/file.png")), "file_not_found"),
    (dict(diffuse=dict(image="no such image")), "image_not_found"),
    (dict(diffuse=dict(path="relative.png")), "path_not_absolute"),
    (dict(diffuse=dict(path="/no/such/file.txt")), "not_an_image_path"),
    (dict(diffuse=dict(path="/x.png", image="y")), "source_shape"),
])
def test_a_source_that_does_not_resolve_changes_nothing(cube, textures, error):
    before = _file_state()
    answer = _result(dict(name=cube.name, material_name="x", textures=textures))
    assert answer["blocked_by"] == "resolution_failed" and answer["performed"] is False
    assert answer["resolution_errors"][0]["error"] == error
    assert answer["known_slots"]
    assert _file_state() == before
    assert not cube.material_slots


def test_a_corrupt_image_is_a_refusal_and_leaves_no_image(cube, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"this is not a png")
    before = _file_state()
    answer = _result(dict(name=cube.name, material_name="x",
                          textures=dict(diffuse=dict(path=str(bad)))))
    assert answer["resolution_errors"][0]["error"] == "image_unreadable"
    assert _file_state() == before


def test_one_bad_entry_applies_nothing_and_unloads_what_the_good_ones_loaded(cube, tmp_path):
    good = write_png(str(tmp_path / "good.png"))
    existing = bpy.data.materials.new("existing")
    cube.data.materials.append(existing)
    before = _file_state()
    answer = _result(dict(name=cube.name, material_name="x", replace=True,
                          textures=dict(diffuse=dict(path=good)),
                          values=dict(shininess=dict(value=0.5))))
    assert answer["blocked_by"] == "resolution_failed"
    assert answer["resolution_errors"][0]["error"] == "unknown_value"
    assert _file_state() == before
    assert cube.material_slots[0].material == existing


@pytest.mark.parametrize("values, textures, error", [
    (dict(roughness=dict(value=1.5)), None, "value_out_of_range"),
    (dict(roughness=dict(color=[0.1, 0.1, 0.1, 1.0])), None, "value_wrong_kind"),
    (dict(roughness=0.5), None, "value_wrong_kind"),
    (dict(diffuseColor=dict(value=0.5)), None, "value_wrong_kind"),
    (dict(diffuseColor=dict(color=[0.1, 0.1, 0.1, 0.5])), None, "alpha_not_kept"),
    (dict(normalmapIntensity=dict(value=0.5)), None, "value_has_no_socket"),
])
def test_a_value_is_judged_against_the_socket_that_would_hold_it(cube, values, textures, error):
    before = _file_state()
    answer = _result(dict(name=cube.name, material_name="x", values=values, textures=textures))
    assert answer["blocked_by"] == "resolution_failed", answer
    assert answer["resolution_errors"][0]["error"] == error
    assert _file_state() == before


def test_a_value_with_its_map_is_written(cube, tmp_path):
    normal = write_png(str(tmp_path / "n.png"))
    bump = write_png(str(tmp_path / "b.png"))
    displacement = write_png(str(tmp_path / "d.png"))
    diffuse = write_png(str(tmp_path / "c.png"))
    answer = _result(dict(
        name=cube.name, material_name="x",
        textures=dict(normalmap=dict(path=normal), bumpmap=dict(path=bump),
                      displacementmap=dict(path=displacement), diffuse=dict(path=diffuse)),
        values=dict(normalmapIntensity=dict(value=0.4), bumpmapIntensity=dict(value=0.3),
                    displacementMapIntensity=dict(value=0.2), diffuseIntensity=dict(value=0.6))))
    assert answer["applied"] is True, answer
    assert answer["textures"]["normalmap"]["strength"] == pytest.approx(0.4)
    assert answer["textures"]["normalmap"]["strength_value"] == "normalmapIntensity"
    assert answer["textures"]["bumpmap"]["strength"] == pytest.approx(0.3)
    assert answer["textures"]["displacementmap"]["strength"] == pytest.approx(0.2)
    assert answer["textures"]["diffuse"]["strength"] == pytest.approx(0.6)
    nodes = cube.material_slots[0].material.node_tree.nodes
    assert nodes["displacementmap"].inputs["Scale"].default_value == pytest.approx(0.2)
    assert nodes["diffuseIntensity"].inputs[0].default_value == pytest.approx(0.6)


def test_specular_with_roughness_is_refused_as_the_panel_refuses_it(cube, tmp_path):
    path = write_png(str(tmp_path / "s.png"))
    before = _file_state()
    answer = _result(dict(name=cube.name, material_name="x",
                          textures=dict(specularmap=dict(path=path),
                                        roughnessmap=dict(path=path))))
    assert answer["blocked_by"] == "specular_with_roughness"
    assert _file_state() == before


def test_one_image_in_two_colour_spaces_is_refused(cube, tmp_path):
    path = write_png(str(tmp_path / "s.png"))
    before = _file_state()
    answer = _result(dict(name=cube.name, material_name="x",
                          textures=dict(diffuse=dict(path=path), normalmap=dict(path=path))))
    assert answer["resolution_errors"][0]["error"] == "color_space_conflict"
    assert _file_state() == before


def test_changing_the_colour_space_of_an_image_something_else_uses_is_reported(cube):
    image = bpy.data.images.new("bridge_test_shared", 4, 4)
    other = bpy.data.materials.new("bridge_test_other")
    other.use_nodes = True
    other.node_tree.nodes.new("ShaderNodeTexImage").image = image
    assert image.colorspace_settings.name == "sRGB"
    answer = _result(dict(name=cube.name, material_name="x",
                          textures=dict(normalmap=dict(image=image.name))))
    assert answer["applied"] is True, answer
    assert answer["color_space_changes"] == [dict(
        image_name=image.name, slot="normalmap", previous_value="sRGB", new_value="Non-Color",
        used_by=["bridge_test_other"])]
    assert image.colorspace_settings.name == "Non-Color"


def test_an_existing_material_is_refused_unless_replacing(cube):
    existing = bpy.data.materials.new("bridge_test_existing")
    cube.data.materials.append(existing)
    answer = _result(dict(name=cube.name, material_name="x"))
    assert answer["blocked_by"] == "material_exists" and answer["performed"] is False
    assert answer["materials_present"] == ["bridge_test_existing"]
    assert cube.material_slots[0].material == existing

    answer = _result(dict(name=cube.name, material_name="x", replace=True))
    assert answer["applied"] is True
    assert answer["materials_destroyed"] == ["bridge_test_existing"]
    assert answer["material_shared_with"] == []
    assert "bridge_test_existing" not in bpy.data.materials


def test_replacing_keeps_one_name_when_regenerating(cube):
    for _attempt in range(3):
        answer = _result(dict(name=cube.name, material_name="stable", replace=True))
        assert answer["material_name"] == "stable"
    assert [name for name in bpy.data.materials.keys() if name.startswith("stable")] == ["stable"]


def test_a_shared_material_stays_on_the_other_object(cube):
    shared = bpy.data.materials.new("bridge_test_shared_material")
    cube.data.materials.append(shared)
    other_mesh = bpy.data.meshes.new("bridge_test_other_mesh")
    other = bpy.data.objects.new("bridge_test_other_object", other_mesh)
    bpy.context.scene.collection.objects.link(other)
    other_mesh.materials.append(shared)
    try:
        refused = _result(dict(name=cube.name, material_name="x"))
        assert refused["material_shared_with"] == [other.name]
        answer = _result(dict(name=cube.name, material_name="x", replace=True))
        assert answer["material_shared_with"] == [other.name]
        assert other.material_slots[0].material == shared
    finally:
        bpy.data.objects.remove(other)
        bpy.data.meshes.remove(other_mesh)


def test_a_name_in_use_elsewhere_is_reported_with_its_suffix(cube):
    other = bpy.data.materials.new("bridge_test_taken")
    other.use_fake_user = True
    answer = _result(dict(name=cube.name, material_name="bridge_test_taken"))
    assert answer["requested_material_name"] == "bridge_test_taken"
    assert answer["material_name"] == cube.material_slots[0].material.name
    assert answer["material_name"] != "bridge_test_taken"


def test_metadata_is_set_on_the_object_where_the_store_reads_it(cube):
    answer = _result(dict(name=cube.name, material_name="x", metadata=dict(
        description="A test.", license="CC-BY", author="Somebody", tag="one, two",
        backfaceCull=False, litsphereTexture="lit_hair")))
    assert answer["applied"] is True, answer
    assert answer["metadata"]["description"] == "A test."
    assert answer["metadata"]["license"] == "CC-BY"
    assert answer["metadata"]["backfaceCull"] is False
    assert answer["metadata"]["litsphereTexture"] == "lit_hair"
    assert "backfaceCull" not in answer["metadata_unset"]
    changed = {row["key"]: row for row in answer["metadata_changes"]}
    assert changed["license"]["previous_value"] == "CC0"
    assert changed["license"]["new_value"] == "CC-BY"
    assert changed["backfaceCull"]["previous_value"] is True


@pytest.mark.parametrize("metadata, error", [
    (dict(shininess="x"), "unknown_metadata"),
    (dict(name="x"), "unknown_metadata"),
    (dict(license="WTFPL"), "unknown_metadata_value"),
    (dict(backfaceCull="false"), "metadata_wrong_type"),
    (dict(description=3), "metadata_wrong_type"),
    (dict(description="one\nroughness 0.1"), "metadata_wrong_type"),
])
def test_metadata_that_would_not_reach_a_file_is_refused(cube, metadata, error):
    before = _file_state()
    answer = _result(dict(name=cube.name, material_name="x", metadata=metadata))
    assert answer["blocked_by"] == "resolution_failed", answer
    assert answer["resolution_errors"][0]["error"] == error
    assert answer["known_metadata"]
    assert _file_state() == before


def test_the_source_file_is_never_written(cube, tmp_path):
    path = write_png(str(tmp_path / "keep.png"))
    digest = _digest(path)
    mtime = os.stat(path).st_mtime_ns
    _result(dict(name=cube.name, material_name="x", textures=dict(diffuse=dict(path=path)),
                 values=dict(roughness=dict(value=0.1))))
    _result(dict(name=cube.name, material_name="x", replace=True,
                 textures=dict(diffuse=dict(path=path))))
    assert _digest(path) == digest and os.stat(path).st_mtime_ns == mtime


def test_a_failure_in_mpfb_leaves_the_mesh_with_what_it_had(cube, monkeypatch):
    services = _services_or_skip()
    existing = bpy.data.materials.new("bridge_test_kept")
    cube.data.materials.append(existing)
    before = _file_state()

    def explode(*_arguments, **_keywords):
        raise RuntimeError("provoked")

    module = __import__("sys").modules[services["HumanService"].__module__]
    monkeypatch.setattr(module.MakeSkinMaterial, "apply_node_tree", explode)
    answer = _result(dict(name=cube.name, material_name="x", replace=True))
    assert answer["blocked_by"] == "material_failed"
    assert "provoked" in answer["message"]
    assert cube.material_slots[0].material == existing
    assert _file_state() == before


def test_not_a_mesh_and_edit_mode_are_refused(cube):
    armature = bpy.data.armatures.new("bridge_test_arm")
    armature_object = bpy.data.objects.new("bridge_test_arm", armature)
    bpy.context.scene.collection.objects.link(armature_object)
    try:
        answer = _result(dict(name=armature_object.name, material_name="x"))
        assert answer["blocked_by"] == "not_a_mesh"
    finally:
        bpy.data.objects.remove(armature_object)
        bpy.data.armatures.remove(armature)

    bpy.context.view_layer.objects.active = cube
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        answer = _result(dict(name=cube.name, material_name="x"))
        assert answer["blocked_by"] == "not_object_mode"
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def test_any_mesh_on_a_character_is_accepted(tmp_path):
    services = _services_or_skip()
    with _Character() as character:
        path = write_png(str(tmp_path / "skin.png"))
        answer = _result(dict(name=character.basemesh.name, material_name="x", replace=True,
                              textures=dict(diffuse=dict(path=path))))
        assert answer["applied"] is True, answer
        assert services["MaterialService"].identify_material(
            character.basemesh.material_slots[0].material) == "makeskin"
