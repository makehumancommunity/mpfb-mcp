"""
``export_character`` against a real MPFB: one file, where the human said, holding only the character.

**The export directory is always this suite's**, a ``tmp_path`` set through the
add-on's own ``export_directory`` preference (:func:`_preference`), through
``export_directory.set_command_line()`` as ``--export-dir`` sets it, or - for the
default - MPFB's user data redirected to a ``tmp_path``. No test here writes
into the developer's own exports directory.

What a file holds is read back in ``eee_composite/export_roundtrip_test.py``;
here the subject is the command's own contract: the path and who chose its
directory in every answer, the refusals before anything is written (an existing
file left byte-identical), the selection put back in full, only the family
selected, a hidden member left out and named, and a character with no basemesh.
"""

import os

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character as _Character
from .._fixtures import linked_plain_object
from .._fixtures import material_data_roots
from .._fixtures import redirected_locations
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import write_loadable_mhclo


def _result(params=None):
    return _fixture_result("export_character", params)


@pytest.fixture(name="preference")
def _preference(tmp_path):
    """The add-on's export_directory preference pointed at ``tmp_path``, and put back."""
    module = bridge_module("export_directory")
    preferences = bpy.context.preferences.addons[module.__package__].preferences
    previous = preferences.export_directory
    preferences.export_directory = str(tmp_path)
    try:
        yield tmp_path
    finally:
        preferences.export_directory = previous


def _rigged(services, character):
    return services["HumanService"].add_builtin_rig(character.basemesh, "default",
                                                    import_weights=True)


def test_a_file_is_written_where_the_preference_says(preference):
    services = _services_or_skip()
    with _Character() as character:
        rig = _rigged(services, character)
        result = _result({"name": character.basemesh.name, "export_name": "hero"})
        assert result["exported"] is True and result["performed"] is True, result["message"]
        assert result["path"] == os.path.join(str(preference), "hero.fbx")
        assert result["path_resolved_by"] == "preferences"
        assert result["export_directory"] == str(preference)
        assert os.path.getsize(result["path"]) == result["size_bytes"] > 0
        assert result["root_name"] == rig.name
        assert result["format"] == "fbx" and result["requested_format"] is None
        assert result["exporter"] == "export_scene.fbx"
        assert result["exporter_options"]["path_mode"] == "COPY"
        assert result["exporter_options"]["embed_textures"] is True
        assert result["overwrote"] is False and result["file_before"] is None
        readiness = result["readiness"]
        assert readiness["rig_identified_as"] == "default"
        assert readiness["helper_vertices"] > 0
        assert character.basemesh.name in readiness["meshes_with_modifiers_beside_shape_keys"]


def test_each_format_and_preset_writes_its_own_extension(preference):
    services = _services_or_skip()
    with _Character() as character:
        _rigged(services, character)
        name = character.basemesh.name
        for chosen, engine, extension in (("gltf", "generic", ".glb"), ("usd", "generic", ".usdz"),
                                          ("fbx", "unity", ".fbx"), ("fbx", "unreal", ".fbx"),
                                          (None, "godot", ".glb")):
            export_name = "hero_{:s}_{:s}".format(str(chosen), engine)
            result = _result({"name": name, "export_name": export_name, "format": chosen,
                              "target_engine": engine})
            assert result["exported"] is True, result["message"]
            assert result["path"].endswith(export_name + extension)
            assert os.path.isfile(result["path"])
        unity = _result({"name": name, "export_name": "u2", "target_engine": "unity"})
        assert unity["exporter_options"]["add_leaf_bones"] is False
        assert unity["exporter_options"]["apply_scale_options"] == "FBX_SCALE_ALL"


def test_the_command_line_overrides_the_preference(preference, tmp_path_factory):
    services = _services_or_skip()
    module = bridge_module("export_directory")
    elsewhere = tmp_path_factory.mktemp("command_line")
    module.set_command_line(str(elsewhere))
    try:
        with _Character() as character:
            result = _result({"name": character.basemesh.name, "export_name": "hero"})
    finally:
        module.set_command_line(None)
    assert result["path_resolved_by"] == "command_line"
    assert result["path"] == os.path.join(str(elsewhere), "hero.fbx")
    assert not os.listdir(str(preference))


def test_the_default_directory_is_created_under_user_data(tmp_path):
    services = _services_or_skip()
    module = bridge_module("export_directory")
    preferences = bpy.context.preferences.addons[module.__package__].preferences
    previous = preferences.export_directory
    preferences.export_directory = ""
    try:
        with _Character() as character:
            with redirected_locations(services, user_data=str(tmp_path)):
                result = _result({"name": character.basemesh.name, "export_name": "hero"})
    finally:
        preferences.export_directory = previous
    assert result["path_resolved_by"] == "default"
    assert result["path"] == os.path.join(str(tmp_path), "exports", "hero.fbx")
    assert os.path.isfile(result["path"])


def test_a_missing_named_directory_is_refused_and_not_created(preference):
    services = _services_or_skip()
    module = bridge_module("export_directory")
    missing = os.path.join(str(preference), "no", "such")
    module.set_command_line(missing)
    try:
        with _Character() as character:
            result = _result({"name": character.basemesh.name, "export_name": "hero"})
    finally:
        module.set_command_line(None)
    assert result["blocked_by"] == "export_directory_missing"
    assert result["path"] == os.path.join(missing, "hero.fbx")
    assert result["performed"] is False and result["exported"] is False
    assert not os.path.exists(os.path.join(str(preference), "no"))


def test_an_existing_file_is_refused_with_its_facts_and_left_byte_identical(preference):
    services = _services_or_skip()
    existing = os.path.join(str(preference), "hero.fbx")
    with open(existing, "wb") as handle:
        handle.write(b"not mine to replace")
    with _Character() as character:
        refused = _result({"name": character.basemesh.name, "export_name": "hero"})
        with open(existing, "rb") as handle:
            assert handle.read() == b"not mine to replace"
        assert refused["blocked_by"] == "export_exists"
        assert refused["file_before"]["size_bytes"] == len(b"not mine to replace")
        assert refused["path"] == existing
        replaced = _result({"name": character.basemesh.name, "export_name": "hero",
                            "overwrite": True})
    assert replaced["overwrote"] is True and replaced["file_before"]["exists"] is True
    assert os.path.getsize(existing) > len(b"not mine to replace")


def test_refusals_write_nothing(preference):
    services = _services_or_skip()
    with _Character() as character:
        name = character.basemesh.name
        godot = _result({"name": name, "export_name": "hero", "format": "fbx",
                         "target_engine": "godot"})
        assert godot["blocked_by"] == "format_not_supported_by_engine"
        assert godot["known_formats_for_target_engine"] == ["gltf"]
        # Defence in depth: mpfb-mcp refuses this before sending it.
        escape = _result({"name": name, "export_name": "../escape"})
        assert escape["blocked_by"] == "invalid_name" and escape["path"] is None
        missing = _result({"name": "No such object", "export_name": "hero"})
        assert missing["blocked_by"] == "subject_not_found" and missing["found"] is False
        assert missing["path"] == os.path.join(str(preference), "hero.fbx")
        plain = linked_plain_object("Fixture.not_a_character")
        try:
            unrelated = _result({"name": plain.name, "export_name": "hero"})
        finally:
            bpy.data.objects.remove(plain, do_unlink=True)
        assert unrelated["blocked_by"] == "subject_not_found"
        bpy.context.view_layer.objects.active = character.basemesh
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            edit = _result({"name": name, "export_name": "hero"})
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
        assert edit["blocked_by"] == "not_object_mode"
    assert os.listdir(str(preference)) == []


def test_only_the_family_is_selected_and_the_selection_is_put_back(preference):
    services = _services_or_skip()
    with _Character() as character, _Character() as other:
        rig = _rigged(services, character)
        hidden = linked_plain_object("Fixture.hidden_child")
        hidden.parent = rig
        hidden.hide_set(True)
        bystander = linked_plain_object("Fixture.bystander")
        for o in bpy.context.view_layer.objects:
            o.select_set(o in (bystander, other.basemesh))
        bpy.context.view_layer.objects.active = bystander
        try:
            result = _result({"name": rig.name, "export_name": "hero"})
            assert sorted(o.name for o in bpy.context.view_layer.objects if o.select_get()) == \
                sorted([bystander.name, other.basemesh.name])
            assert bpy.context.view_layer.objects.active == bystander
        finally:
            bpy.data.objects.remove(hidden, do_unlink=True)
            bpy.data.objects.remove(bystander, do_unlink=True)
    exported = set(o["name"] for o in result["objects_exported"])
    assert exported == {result["root_name"], result["basemesh_name"]}
    assert result["objects_left_out"] == [dict(name="Fixture.hidden_child", reason="not_visible")]


def test_a_character_with_only_a_body_proxy_is_exported_through_it(preference, tmp_path_factory):
    services = _services_or_skip()
    root = str(tmp_path_factory.mktemp("assets"))
    write_loadable_mhclo(os.path.join(root, "proxymeshes", "fixture_proxy", "fixture_proxy.mhclo"),
                         material=False)
    with _Character() as character:
        _rigged(services, character)
        with material_data_roots(services, root):
            added = _fixture_result("add_asset", {
                "name": character.basemesh.name, "fragment": "fixture_proxy/fixture_proxy.mhclo",
                "object_type": "Proxymeshes"})
            assert added["added"] is True, added["message"]
            copy = _fixture_result("create_export_copy", {
                "name": character.basemesh.name, "remove_basemesh": True})
        try:
            result = _result({"name": copy["copy_bodyproxy_name"], "export_name": "proxy_only"})
        finally:
            collection = bpy.data.collections.get("export copy")
            if collection is not None:
                bpy.data.collections.remove(collection)
    assert result["exported"] is True, result["message"]
    assert result["basemesh_name"] is None
    assert result["bodyproxy_name"] == copy["copy_bodyproxy_name"]
    assert result["root_name"] == copy["copy_root_name"]
    assert result["readiness"]["helper_vertices"] is None
