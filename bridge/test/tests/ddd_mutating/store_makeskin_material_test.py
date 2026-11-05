"""
``store_makeskin_material`` against a real MPFB: an MHMAT and textures, where MPFB looks.

**Every test here writes into a redirected data root**, per this directory's rule, and
every refusal is asserted to have written nothing and made no directory: that is the
thing MPFB's two operators get wrong, by creating the directory first. The source
textures are compared by hash and modification time, which is the other thing they get
wrong, by re-encoding them.
"""

import hashlib
import os

import bpy
import pytest

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import material_data_roots
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import write
from .._fixtures import write_loadable_mhclo
from .._fixtures import write_mhmat
from .._fixtures import write_pack
from .._fixtures import write_png

MESH = "BridgeTestStoreMesh"


def _result(params):
    return _fixture_result("store_makeskin_material", params)


def _set(name, **params):
    answer = _fixture_result("set_makeskin_material", dict(name=name, **params))
    assert answer["applied"] is True, answer["message"]
    return answer


def _tree(root):
    """Every file and directory under a root, to compare before and after a refusal."""
    found = []
    for dirpath, dirs, files in os.walk(str(root)):
        found.extend(os.path.join(dirpath, name) for name in dirs + files)
    return sorted(found)


def _digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.fixture(name="dressed")
def _dressed(tmp_path):
    """A character wearing a garment from a redirected library, inside that library."""
    services = _services_or_skip()
    root = tmp_path / "data"
    write_loadable_mhclo(str(root / "clothes" / "spike" / "spike.mhclo"))
    # The character comes first: MPFB's own data root holds what it is built from.
    with _Character() as character:
        with material_data_roots(services, str(root)):
            envelope = dispatch("add_asset", dict(name=character.basemesh.name,
                                                  fragment="spike/spike.mhclo",
                                                  object_type="Clothes"))
            assert envelope["result"]["added"] is True, envelope["result"]["message"]
            yield (character, envelope["result"]["asset_object_name"], root)


def _textured(asset, directory, values=None):
    diffuse = write_png(os.path.join(str(directory), "src_diffuse.png"), (0.1, 0.2, 0.3, 1.0))
    normal = write_png(os.path.join(str(directory), "src_normal.png"), (0.5, 0.5, 1.0, 1.0))
    _set(asset, material_name="made", replace=True, values=values,
         textures=dict(diffuse=dict(path=diffuse), normalmap=dict(path=normal)))
    return (diffuse, normal)


def test_an_alternate_lands_where_mpfbs_panel_puts_it(dressed, tmp_path):
    _character, asset, root = dressed
    diffuse, normal = _textured(asset, tmp_path)
    digests = (_digest(diffuse), _digest(normal))
    times = (os.stat(diffuse).st_mtime_ns, os.stat(normal).st_mtime_ns)

    answer = _result(dict(name=asset, store_as="alternate", material_name="belt_blue",
                          license="CC-BY", author="Somebody"))
    assert answer["saved"] is True and answer["performed"] is True, answer["message"]
    expected = root / "clothes" / "spike" / "belt_blue" / "belt_blue.mhmat"
    assert answer["path"] == str(expected) and expected.is_file()
    assert answer["fragment"] == "belt_blue/belt_blue.mhmat"
    assert answer["size_bytes"] == expected.stat().st_size

    rows = {row["slot"]: row for row in answer["textures_written"]}
    assert sorted(rows) == ["diffuse", "normalmap"]
    written = rows["diffuse"]
    assert written["how"] == "copied" and written["source_path"] == diffuse
    assert written["path"] == str(expected.parent / "belt_blue_diffuse.png")
    assert written["size_bytes"] == os.stat(diffuse).st_size
    # Byte for byte, and the source neither re-encoded nor touched.
    assert _digest(written["path"]) == digests[0]
    assert (_digest(diffuse), _digest(normal)) == digests
    assert (os.stat(diffuse).st_mtime_ns, os.stat(normal).st_mtime_ns) == times

    text = expected.read_text()
    assert "name belt_blue\n" in text
    assert "license CC-BY\n" in text and "author Somebody\n" in text
    assert "diffuseTexture belt_blue_diffuse.png\n" in text
    assert "normalmapTexture belt_blue_normalmap.png\n" in text
    assert answer["license_resolved_by"] == "argument"
    assert answer["author_resolved_by"] == "argument"
    assert answer["apply_with"] == dict(
        mpfb_set_asset_material=dict(name=asset, path=str(expected)))
    # No stray staging directory beside it.
    assert not [name for name in os.listdir(str(expected.parent.parent))
                if name.startswith(".")]


def test_the_catalogue_lists_it_at_once(dressed, tmp_path):
    _character, asset, _root = dressed
    _textured(asset, tmp_path)
    before = _fixture_result("list_asset_materials", dict(name=asset))
    answer = _result(dict(name=asset, store_as="alternate", material_name="fresh"))
    assert answer["cache_invalidated"] is True
    after = _fixture_result("list_asset_materials", dict(name=asset))
    assert answer["path"] in [entry["path"] for entry in after["materials"]]
    assert answer["path"] not in [entry["path"] for entry in before["materials"]]


def test_an_image_with_no_file_is_saved_from_blender_and_keeps_no_new_path(dressed):
    _character, asset, _root = dressed
    image = bpy.data.images.new("bridge_test_store_baked", 4, 4)
    try:
        _set(asset, material_name="made", replace=True,
             textures=dict(diffuse=dict(image=image.name)))
        answer = _result(dict(name=asset, store_as="alternate", material_name="baked"))
        row = answer["textures_written"][0]
        assert row["how"] == "saved_from_blender" and row["source_image"] == image.name
        assert row["source_path"] is None
        assert row["path"].endswith("baked_diffuse.png") and os.path.isfile(row["path"])
        assert image.filepath == "" and image.source == "GENERATED"
    finally:
        bpy.data.images.remove(image)


def test_an_image_with_unsaved_changes_keeps_them_and_its_source_is_untouched(dressed, tmp_path):
    _character, asset, _root = dressed
    path = write_png(str(tmp_path / "edited.png"), (1.0, 0.0, 0.0, 1.0))
    digest = _digest(path)
    answer = _set(asset, material_name="made", replace=True,
                  textures=dict(diffuse=dict(path=path)))
    assert answer["textures"]["diffuse"]["path"] == path
    image = bpy.data.objects[asset].material_slots[0].material.node_tree.nodes[
        "diffuseTexture"].image
    image.pixels[0] = 0.0
    assert image.is_dirty
    answer = _result(dict(name=asset, store_as="alternate", material_name="edited"))
    row = answer["textures_written"][0]
    assert row["how"] == "saved_from_blender"
    assert _digest(path) == digest
    assert image.is_dirty and bpy.path.abspath(image.filepath) == path
    stored = bpy.data.images.load(row["path"], check_existing=False)
    try:
        assert stored.size[0] == 2
        assert stored.pixels[0] == pytest.approx(0.0)
    finally:
        bpy.data.images.remove(stored)


def test_a_skin_lands_among_the_user_skins_and_the_catalogue_lists_it(dressed, tmp_path):
    character, _asset, root = dressed
    body = character.basemesh.name
    diffuse = write_png(str(tmp_path / "skin.png"))
    _set(body, material_name="made", replace=True, textures=dict(diffuse=dict(path=diffuse)))
    answer = _result(dict(name=body, store_as="skin", material_name="my_skin"))
    assert answer["saved"] is True, answer["message"]
    assert answer["path"] == str(root / "skins" / "my_skin" / "my_skin.mhmat")
    assert answer["apply_with"] == dict(mpfb_set_skin=dict(
        name=body, skin_type="MAKESKIN", path=answer["path"]))
    assert answer["cache_invalidated"] is True
    listed = _fixture_result("list_assets", dict(asset_subdir="skins"))
    assert answer["fragment"] in [entry["fragment"] for entry in listed["assets"]]


@pytest.mark.parametrize("store_as, on_asset", [("alternate", False), ("skin", True)])
def test_each_panel_refuses_the_others_kind_of_object(dressed, tmp_path, store_as, on_asset):
    character, asset, root = dressed
    subject = asset if on_asset else character.basemesh.name
    _set(subject, material_name="made", replace=True)
    before = _tree(root)
    answer = _result(dict(name=subject, store_as=store_as, material_name="nope"))
    assert answer["blocked_by"] == "type_not_supported" and answer["performed"] is False
    assert answer["path"] is None
    assert _tree(root) == before
    assert tmp_path  # the fixture's tree is what is compared


def test_a_mesh_that_is_no_asset_is_refused(dressed):
    _character, _asset, root = dressed
    mesh = bpy.data.meshes.new(MESH)
    blender_object = bpy.data.objects.new(MESH, mesh)
    bpy.context.scene.collection.objects.link(blender_object)
    before = _tree(root)
    try:
        _set(MESH, material_name="made")
        assert _result(dict(name=MESH, store_as="alternate", material_name="x"))[
            "blocked_by"] == "not_an_mpfb_object"
        assert _result(dict(name=MESH, store_as="skin", material_name="x"))[
            "blocked_by"] == "type_not_supported"
    finally:
        bpy.data.objects.remove(blender_object)
        bpy.data.meshes.remove(mesh)
    assert _tree(root) == before


def test_an_asset_outside_the_library_is_refused(dressed):
    """FR 050's export directory: somewhere MPFB would never look for an alternate."""
    services = _services_or_skip()
    _character, asset, root = dressed
    _set(asset, material_name="made", replace=True)
    general = services["ObjectService"].__module__
    properties = __import__("sys").modules[general].GeneralObjectProperties
    properties.set_value("asset_source", "elsewhere/elsewhere.mhclo",
                         entity_reference=bpy.data.objects[asset])
    before = _tree(root)
    answer = _result(dict(name=asset, store_as="alternate", material_name="x"))
    assert answer["blocked_by"] == "asset_not_in_library"
    assert answer["asset_source"] == "elsewhere/elsewhere.mhclo"
    properties.set_value("asset_source", "", entity_reference=bpy.data.objects[asset])
    assert _result(dict(name=asset, store_as="alternate", material_name="x"))[
        "blocked_by"] == "asset_source_missing"
    assert _tree(root) == before


@pytest.mark.parametrize("material_name", ["Has_Caps", "has space", "a/b", "..", "dot.ted", ""])
def test_a_name_that_would_not_survive_is_refused_on_this_side_too(dressed, material_name):
    _character, asset, root = dressed
    _set(asset, material_name="made", replace=True)
    before = _tree(root)
    answer = _result(dict(name=asset, store_as="alternate", material_name=material_name))
    assert answer["blocked_by"] == "invalid_name"
    assert _tree(root) == before


def test_no_material_and_another_kind_of_material_are_refused(dressed):
    _character, asset, root = dressed
    blender_object = bpy.data.objects[asset]
    material = blender_object.material_slots[0].material
    before = _tree(root)
    other = bpy.data.materials.new("bridge_test_store_other")
    other.use_nodes = True
    other.node_tree.nodes.new("ShaderNodeEmission").name = "somebody's node"
    blender_object.data.materials[0] = other
    try:
        answer = _result(dict(name=asset, store_as="alternate", material_name="x"))
        assert answer["blocked_by"] == "not_makeskin"
        assert answer["material_identified_as"] == "gameengine"
    finally:
        blender_object.data.materials[0] = material
        bpy.data.materials.remove(other)
    while len(blender_object.data.materials) > 0:
        blender_object.data.materials.pop(index=0)
    assert _result(dict(name=asset, store_as="alternate", material_name="x"))[
        "blocked_by"] == "no_material"
    assert _tree(root) == before


def test_an_unknown_license_is_refused_with_mpfbs_own(dressed):
    _character, asset, root = dressed
    _set(asset, material_name="made", replace=True)
    before = _tree(root)
    answer = _result(dict(name=asset, store_as="alternate", material_name="x", license="WTFPL"))
    assert answer["blocked_by"] == "invalid_license"
    assert answer["known_values"] == ["CC0", "CC-BY", "AGPL"]
    assert _tree(root) == before


def test_license_and_author_default_from_the_object_and_say_so(dressed, tmp_path):
    _character, asset, _root = dressed
    _textured(asset, tmp_path)
    fresh = _result(dict(name=asset, store_as="alternate", material_name="first"))
    assert fresh["license"] == "CC0" and fresh["license_resolved_by"] == "mpfb_default"
    assert fresh["author"] is None and fresh["author_resolved_by"] == "mpfb_default"
    assert any("license is MPFB's default" in warning for warning in fresh["warnings"])
    with open(fresh["path"], encoding="utf-8") as handle:
        text = handle.read()
    assert "// author\n" in text and "license CC0\n" in text

    _set(asset, material_name="made", replace=True,
         metadata=dict(license="AGPL", author="Chosen"))
    chosen = _result(dict(name=asset, store_as="alternate", material_name="second"))
    assert chosen["license"] == "AGPL" and chosen["license_resolved_by"] == "object"
    assert chosen["author"] == "Chosen" and chosen["author_resolved_by"] == "object"
    assert not any("license is MPFB's default" in warning for warning in chosen["warnings"])


def test_every_accepted_metadata_key_reaches_the_file(dressed):
    """FR 6's round trip, which decided which keys are accepted."""
    _character, asset, _root = dressed
    metadata = dict(description="One line.", license="CC-BY", author="Me", tag="one, two",
                    homepage="http://example.org", backfaceCull=False, transparent=True,
                    castShadows=False, receiveShadows=False, shadeless=True, wireframe=True,
                    depthless=True, alphaToCoverage=False, autoBlendSkin=True, sssEnabled=True,
                    litsphereTexture="lit_hair")
    answer = _set(asset, material_name="made", replace=True, metadata=metadata)
    assert sorted(metadata) == answer["known_metadata"], "a key survives that is not accepted"
    stored = _result(dict(name=asset, store_as="alternate", material_name="meta"))
    with open(stored["path"], encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for line in ("description One line.", "license CC-BY", "author Me", "tag one", "tag two",
                 "homepage http://example.org", "backfaceCull False", "transparent True",
                 "castShadows False", "receiveShadows False", "shadeless True", "wireframe True",
                 "depthless True", "alphaToCoverage False", "autoBlendSkin True",
                 "sssEnabled True", "litsphereTexture lit_hair"):
        assert line in lines, line


def test_the_numbers_mpfb_would_lose_reach_the_file(dressed, tmp_path):
    """The displacement key MPFB misspells, and the mix factor it looks for by an old name."""
    _character, asset, _root = dressed
    displacement = write_png(str(tmp_path / "d.png"))
    diffuse = write_png(str(tmp_path / "c.png"))
    _set(asset, material_name="made", replace=True,
         textures=dict(displacementmap=dict(path=displacement), diffuse=dict(path=diffuse)),
         values=dict(displacementMapIntensity=dict(value=0.123), diffuseIntensity=dict(value=0.75),
                     roughness=dict(value=0.2)))
    stored = _result(dict(name=asset, store_as="alternate", material_name="numbers"))
    with open(stored["path"], encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    assert "displacementMapIntensity 0.1230" in lines
    assert "diffuseIntensity 0.7500" in lines
    assert "roughness 0.2000" in lines


def test_values_mpfbs_loader_will_not_restore_are_named(dressed, tmp_path):
    _character, asset, _root = dressed
    diffuse = write_png(str(tmp_path / "c.png"))
    _set(asset, material_name="made", replace=True, textures=dict(diffuse=dict(path=diffuse)),
         values=dict(roughness=dict(value=0.2), diffuseColor=dict(color=[0.1, 0.2, 0.3, 1.0])))
    answer = _result(dict(name=asset, store_as="alternate", material_name="lost"))
    assert sorted(answer["values_not_restored"]) == ["roughness"]
    assert answer["values_not_restored"]["roughness"]["stored"] == pytest.approx(0.2)
    assert answer["values_not_restored"]["roughness"]["after_apply"] == pytest.approx(0.7)
    assert "values_not_restored" in answer["message"]


def test_values_at_the_templates_own_are_not_named(dressed):
    _character, asset, _root = dressed
    _set(asset, material_name="made", replace=True)
    answer = _result(dict(name=asset, store_as="alternate", material_name="same"))
    assert answer["values_not_restored"] == {}
    assert "values_not_restored" not in answer["message"]


def test_an_existing_material_is_refused_with_its_facts_and_replaced_when_asked(
        dressed, tmp_path):
    _character, asset, _root = dressed
    _textured(asset, tmp_path)
    first = _result(dict(name=asset, store_as="alternate", material_name="twice"))
    with open(first["path"], "rb") as handle:
        contents = handle.read()
    refused = _result(dict(name=asset, store_as="alternate", material_name="twice"))
    assert refused["blocked_by"] == "material_exists" and refused["performed"] is False
    assert refused["path"] == first["path"]
    assert refused["file_before"]["exists"] is True
    assert refused["file_before"]["size_bytes"] == len(contents)
    assert refused["file_before"]["modified"]

    replaced = _result(dict(name=asset, store_as="alternate", material_name="twice",
                            overwrite=True, author="Another"))
    assert replaced["saved"] is True and replaced["overwrote"] is True
    assert replaced["file_before"]["size_bytes"] == len(contents)
    with open(first["path"], encoding="utf-8") as handle:
        assert "author Another\n" in handle.read()


def test_a_texture_in_the_way_with_no_material_is_refused_too(dressed, tmp_path):
    _character, asset, root = dressed
    _textured(asset, tmp_path)
    in_the_way = root / "clothes" / "spike" / "orphan" / "orphan_diffuse.png"
    write(str(in_the_way), "somebody's")
    answer = _result(dict(name=asset, store_as="alternate", material_name="orphan"))
    assert answer["blocked_by"] == "material_exists"
    assert answer["existing_textures"] == [str(in_the_way)]
    assert answer["file_before"] is None
    assert in_the_way.read_text() == "somebody's"


def test_a_material_stored_in_place_over_itself_copies_nothing(dressed, tmp_path):
    _character, asset, _root = dressed
    _textured(asset, tmp_path)
    first = _result(dict(name=asset, store_as="alternate", material_name="self"))
    fragment = first["apply_with"]["mpfb_set_asset_material"]["path"]
    envelope = dispatch("set_asset_material", dict(name=asset, path=fragment))
    assert envelope["result"]["applied"] is True, envelope["result"]["message"]
    diffuse = first["textures_written"][0]["path"]
    digest = _digest(diffuse)
    mtime = os.stat(diffuse).st_mtime_ns
    second = _result(dict(name=asset, store_as="alternate", material_name="self", overwrite=True))
    assert second["saved"] is True, second["message"]
    assert {row["how"] for row in second["textures_written"]} == {"already_in_place"}
    assert _digest(diffuse) == digest and os.stat(diffuse).st_mtime_ns == mtime


def test_a_replaced_file_reaches_the_image_mpfb_would_reuse_by_name(dressed, tmp_path):
    _character, asset, _root = dressed
    diffuse = write_png(str(tmp_path / "c.png"), (1.0, 0.0, 0.0, 1.0))
    _set(asset, material_name="made", replace=True, textures=dict(diffuse=dict(path=diffuse)))
    first = _result(dict(name=asset, store_as="alternate", material_name="again"))
    envelope = dispatch("set_asset_material", dict(
        name=asset, path=first["path"]))
    assert envelope["result"]["applied"] is True
    loaded = bpy.data.objects[asset].material_slots[0].material.node_tree.nodes[
        "diffuseTexture"].image
    assert loaded.pixels[0] == pytest.approx(1.0)

    blue = write_png(str(tmp_path / "b.png"), (0.0, 0.0, 1.0, 1.0))
    _set(asset, material_name="made", replace=True, textures=dict(diffuse=dict(path=blue)))
    _result(dict(name=asset, store_as="alternate", material_name="again", overwrite=True))
    assert loaded.pixels[0] == pytest.approx(0.0) and loaded.pixels[2] == pytest.approx(1.0)


def test_a_loaded_image_from_elsewhere_with_that_name_is_warned_about(dressed, tmp_path):
    _character, asset, _root = dressed
    _textured(asset, tmp_path)
    other = write_png(str(tmp_path / "other" / "taken_diffuse.png"))
    image = bpy.data.images.load(other)
    try:
        answer = _result(dict(name=asset, store_as="alternate", material_name="taken"))
        assert any("taken_diffuse.png" in warning for warning in answer["warnings"])
    finally:
        bpy.data.images.remove(image)


def test_dry_run_settles_everything_and_writes_nothing(dressed, tmp_path):
    _character, asset, root = dressed
    _textured(asset, tmp_path)
    before = _tree(root)
    answer = _result(dict(name=asset, store_as="alternate", material_name="dry", dry_run=True))
    assert answer["ready"] is True and answer["dry_run"] is True
    assert answer["saved"] is False and answer["performed"] is False
    assert answer["path"].endswith("dry/dry.mhmat")
    assert answer["cache_invalidated"] is False
    assert {row["how"] for row in answer["textures_written"]} == {"copied"}
    assert answer["message"].startswith("Would store")
    assert _tree(root) == before

    _result(dict(name=asset, store_as="alternate", material_name="dry"))
    assert _result(dict(name=asset, store_as="alternate", material_name="dry", dry_run=True))[
        "blocked_by"] == "material_exists"


def test_a_name_another_root_or_asset_holds_is_shadowed(tmp_path):
    services = _services_or_skip()
    root = tmp_path / "data"
    earlier = tmp_path / "mh_data"
    write_loadable_mhclo(str(root / "clothes" / "spike" / "spike.mhclo"))
    with _Character() as character:
        with material_data_roots(services, str(root)):
            # MakeHuman's user data is searched before MPFB's user data.
            services["LocationService"]._mh_user_data = str(earlier)  # pylint: disable=protected-access
            envelope = dispatch("add_asset", dict(name=character.basemesh.name,
                                                  fragment="spike/spike.mhclo",
                                                  object_type="Clothes"))
            assert envelope["result"]["added"] is True, envelope["result"]["message"]
            asset = envelope["result"]["asset_object_name"]
            _set(asset, material_name="made", replace=True)
            taken = write_mhmat(str(earlier / "clothes" / "any" / "taken" / "taken.mhmat"))
            before = _tree(tmp_path)
            answer = _result(dict(name=asset, store_as="alternate", material_name="taken"))
            assert answer["blocked_by"] == "name_shadowed", answer["message"]
            assert answer["shadowed_by"] == dict(path=taken, same_root=False)
            assert _tree(tmp_path) == before

            # The same fragment beside another asset in this root could answer for it too.
            other = write_mhmat(str(root / "clothes" / "hat" / "blue" / "blue.mhmat"))
            answer = _result(dict(name=asset, store_as="alternate", material_name="blue"))
            assert answer["blocked_by"] == "name_shadowed"
            assert answer["shadowed_by"] == dict(path=other, same_root=True)


def test_a_pack_claiming_the_asset_is_warned_about(tmp_path):
    services = _services_or_skip()
    root = tmp_path / "data"
    write_loadable_mhclo(str(root / "clothes" / "spike" / "spike.mhclo"))
    write_pack(str(root), "somepack", dict(spike=("CC0", "A", "http://x")))
    with _Character() as character:
        with material_data_roots(services, str(root)):
            services["AssetService"].invalidate_pack_metadata_cache()
            try:
                envelope = dispatch("add_asset", dict(name=character.basemesh.name,
                                                      fragment="spike/spike.mhclo",
                                                      object_type="Clothes"))
                asset = envelope["result"]["asset_object_name"]
                _set(asset, material_name="made", replace=True)
                answer = _result(dict(name=asset, store_as="alternate", material_name="mine"))
                assert answer["asset_packs"] == ["somepack"], answer
                assert any("somepack" in warning for warning in answer["warnings"])
                # FR 046's rule looks at the file's own directory, so the pack does not claim it.
                assert answer["attribution"]["packs"] == []
            finally:
                services["AssetService"].invalidate_pack_metadata_cache()


def test_a_failure_while_writing_leaves_nothing_in_place(dressed, tmp_path, monkeypatch):
    _character, asset, root = dressed
    _textured(asset, tmp_path)
    before = _tree(root)
    texture_writing = __import__("sys").modules[
        _store_module_name()].texture_writing

    def explode(*_arguments, **_keywords):
        raise OSError("provoked")

    monkeypatch.setattr(texture_writing, "move_into_place", explode)
    answer = _result(dict(name=asset, store_as="alternate", material_name="fails"))
    assert answer["blocked_by"] == "write_failed" and answer["performed"] is False
    assert "provoked" in answer["message"]
    assert _tree(root) == before


def _store_module_name():
    from .. import dynamic_import  # pylint: disable=import-outside-toplevel
    commands = dynamic_import("commands", "COMMANDS")
    return commands["store_makeskin_material"].handler.__module__


def test_a_skin_write_makes_no_directory_before_its_last_refusal(tmp_path):
    services = _services_or_skip()
    root = tmp_path / "data"
    with _Character() as character:
        _set(character.basemesh.name, material_name="made", replace=True)
        with material_data_roots(services, str(root)):
            answer = _result(dict(name=character.basemesh.name, store_as="skin",
                                  material_name="Bad Name"))
            assert answer["blocked_by"] == "invalid_name"
            assert not root.exists()
            answer = _result(dict(name=character.basemesh.name, store_as="skin",
                                  material_name="dry", dry_run=True))
            assert answer["ready"] is True
            assert not root.exists()
