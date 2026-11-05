"""
A MakeSkin material through the reader, the writer, a file and MPFB's own loader.

The claims are about several commands at once, so they are here. **Two of them hold whole,
and one holds only in part, and this module says which part.**

- The reader's ``textures``, ``values`` and ``metadata`` sent to the writer unchanged give
  the same reading back. Whole.
- Through a file and ``set_asset_material`` or ``set_skin``, the textures, their colour
  spaces, their pixels and ``diffuseColor`` read back equal. Whole.
- **Every other number does not come back, and nothing here can make it.** MPFB's
  ``apply_node_tree()`` builds its template from the textures and ``diffuseColor`` alone.
  So ``test_the_other_numbers_come_back_as_the_template_has_them`` asserts exactly what is
  lost, against what the store said would be, and it is written to **fail once MPFB reads
  them**, per
  [how a defect is tracked](../../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).
  The panel's behaviour is followed on purpose: see ``set_asset_material``'s docstring.
"""

import os

import bpy
import pytest

from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import material_data_roots
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import write_loadable_mhclo
from .._fixtures import write_png

# Away from the template's own, each, so that a value carried through is a value carried.
_NUMBERS = dict(roughness=0.2, metallic=0.3, ior=1.7, diffuseIntensity=0.8,
                normalmapIntensity=0.6, displacementMapIntensity=0.05)
_COLOR = [0.1, 0.2, 0.3, 1.0]
_METADATA = dict(description="A round trip.", license="CC-BY", author="Somebody", tag="one, two",
                 backfaceCull=False)


@pytest.fixture(name="dressed")
def _dressed(tmp_path):
    services = services_or_skip()
    root = tmp_path / "data"
    write_loadable_mhclo(str(root / "clothes" / "spike" / "spike.mhclo"))
    with Character() as character:
        with material_data_roots(services, str(root)):
            envelope = dispatch("add_asset", dict(name=character.basemesh.name,
                                                  fragment="spike/spike.mhclo",
                                                  object_type="Clothes"))
            assert envelope["result"]["added"] is True, envelope["result"]["message"]
            yield (character, envelope["result"]["asset_object_name"], root)


def _sources(directory):
    return dict(
        diffuse=dict(path=write_png(os.path.join(str(directory), "d.png"), (0.9, 0.1, 0.1, 1.0))),
        normalmap=dict(path=write_png(os.path.join(str(directory), "n.png"), (0.5, 0.5, 1.0, 1.0))),
        displacementmap=dict(path=write_png(os.path.join(str(directory), "h.png"),
                                            (0.25, 0.25, 0.25, 1.0))))


def _numbers():
    values = {key: dict(value=value) for key, value in _NUMBERS.items()}
    values["diffuseColor"] = dict(color=list(_COLOR))
    return values


def _build(subject, directory):
    answer = result("set_makeskin_material", dict(
        name=subject, material_name="made", replace=True, textures=_sources(directory),
        values=_numbers(), metadata=dict(_METADATA)))
    assert answer["applied"] is True, answer["message"]
    return answer


def _read(subject):
    answer = result("get_makeskin_material", dict(name=subject))
    assert answer["ready"] is True, answer["message"]
    return answer


def _pixels(subject, slot):
    nodes = bpy.data.objects[subject].material_slots[0].material.node_tree.nodes
    return list(nodes[slot + "Texture"].image.pixels[:4])


def _comparable_textures(textures):
    return {slot: (entry["wired"], entry["color_space"], entry["size"])
            for slot, entry in textures.items()}


def test_a_reading_sent_back_unchanged_reads_the_same(dressed, tmp_path):
    _character, asset, _root = dressed
    _build(asset, tmp_path)
    first = _read(asset)
    answer = result("set_makeskin_material", dict(
        name=asset, material_name=first["material_name"], replace=True,
        textures=first["textures"], values=first["values"], metadata=first["metadata"]))
    assert answer["applied"] is True, answer
    second = _read(asset)
    for key in ("textures", "values", "values_absent", "metadata", "material_name"):
        assert second[key] == first[key], key


def test_a_reading_with_an_unsaved_image_keeps_its_pixels(dressed, tmp_path):
    _character, asset, _root = dressed
    _build(asset, tmp_path)
    nodes = bpy.data.objects[asset].material_slots[0].material.node_tree.nodes
    nodes["diffuseTexture"].image.pixels[0] = 0.0
    first = _read(asset)
    assert "image" in first["textures"]["diffuse"]
    answer = result("set_makeskin_material", dict(
        name=asset, material_name="again", replace=True, textures=first["textures"]))
    assert answer["applied"] is True, answer
    assert sorted(answer["reloaded"]) == ["displacementmap", "normalmap"]
    assert _pixels(asset, "diffuse")[0] == pytest.approx(0.0)


def test_through_a_file_and_set_asset_material_textures_and_color_read_back_equal(
        dressed, tmp_path):
    _character, asset, _root = dressed
    _build(asset, tmp_path)
    before = _read(asset)
    pixels = {slot: _pixels(asset, slot) for slot in before["textures"]}
    stored = result("store_makeskin_material", dict(
        name=asset, store_as="alternate", material_name="alternate_one"))
    assert stored["saved"] is True, stored["message"]

    applied = result("set_asset_material", stored["apply_with"]["mpfb_set_asset_material"])
    assert applied["applied"] is True, applied["message"]
    after = _read(asset)
    assert _comparable_textures(after["textures"]) == _comparable_textures(before["textures"])
    for slot, entry in after["textures"].items():
        assert entry["path"] == os.path.join(os.path.dirname(stored["path"]),
                                             "alternate_one_{:s}.png".format(slot))
        assert _pixels(asset, slot) == pytest.approx(pixels[slot], abs=0.01), slot
    assert after["values"]["diffuseColor"]["color"] == pytest.approx(_COLOR, abs=1e-4)


def test_through_a_file_and_set_skin_textures_and_color_read_back_equal(dressed, tmp_path):
    character, _asset, _root = dressed
    body = character.basemesh.name
    _build(body, tmp_path)
    before = _read(body)
    pixels = {slot: _pixels(body, slot) for slot in before["textures"]}
    stored = result("store_makeskin_material", dict(
        name=body, store_as="skin", material_name="skin_one"))
    assert stored["saved"] is True, stored["message"]

    applied = result("set_skin", stored["apply_with"]["mpfb_set_skin"])
    assert applied["applied"] is True, applied["message"]
    after = _read(body)
    assert _comparable_textures(after["textures"]) == _comparable_textures(before["textures"])
    for slot in before["textures"]:
        assert _pixels(body, slot) == pytest.approx(pixels[slot], abs=0.01), slot
    assert after["values"]["diffuseColor"]["color"] == pytest.approx(_COLOR, abs=1e-4)


def test_an_image_with_no_file_survives_the_file(dressed):
    _character, asset, _root = dressed
    image = bpy.data.images.new("bridge_test_roundtrip_baked", 2, 2)
    image.pixels[:] = [0.0, 1.0, 0.0, 1.0] * 4
    try:
        result("set_makeskin_material", dict(
            name=asset, material_name="made", replace=True,
            textures=dict(diffuse=dict(image=image.name))))
        stored = result("store_makeskin_material", dict(
            name=asset, store_as="alternate", material_name="from_blender"))
        assert stored["textures_written"][0]["how"] == "saved_from_blender"
        result("set_asset_material", stored["apply_with"]["mpfb_set_asset_material"])
        assert _pixels(asset, "diffuse")[:3] == pytest.approx([0.0, 1.0, 0.0], abs=0.01)
    finally:
        bpy.data.images.remove(image)


def test_the_other_numbers_come_back_as_the_template_has_them(dressed, tmp_path):
    """What the store says is lost is what is lost, and the file still holds it.

    **This is written to fail the day MPFB's loader reads these**, at which point
    ``values_not_restored`` will have emptied itself and the module docstring is stale.
    """
    _character, asset, _root = dressed
    _build(asset, tmp_path)
    before = _read(asset)
    stored = result("store_makeskin_material", dict(
        name=asset, store_as="alternate", material_name="numbers"))
    promised = stored["values_not_restored"]
    assert sorted(promised) == sorted(_NUMBERS)

    with open(stored["path"], encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for key, value in _NUMBERS.items():
        assert "{:s} {:.4f}".format(key, value) in lines, key

    result("set_asset_material", stored["apply_with"]["mpfb_set_asset_material"])
    after = _read(asset)
    for key, entry in promised.items():
        assert before["values"][key]["value"] == pytest.approx(entry["stored"], abs=1e-4), key
        assert after["values"][key]["value"] == pytest.approx(entry["after_apply"], abs=1e-4), key

    # Which leaves the caller one call away from what it had, as the answer says.
    repaired = result("set_makeskin_material", dict(
        name=asset, material_name=after["material_name"], replace=True,
        textures=after["textures"], values=before["values"], metadata=after["metadata"]))
    assert repaired["applied"] is True, repaired
    for key, value in _NUMBERS.items():
        assert repaired["values"][key]["value"] == pytest.approx(value, abs=1e-4), key


def test_a_material_mpfb_built_stores_and_comes_back_the_same(dressed, tmp_path):
    """The other direction: from MPFB's own loader, through the store, and back."""
    services = services_or_skip()
    _character, asset, root = dressed
    texture = write_png(str(root / "clothes" / "spike" / "spike_diffuse.png"), (0.2, 0.8, 0.2, 1.0))
    mhmat = root / "clothes" / "spike" / "spike_green.mhmat"
    mhmat.write_text("name spike_green\ndiffuseColor 0.4 0.5 0.6\n"
                     "diffuseTexture {:s}\nnormalmapTexture {:s}\n".format(
                         os.path.basename(texture), os.path.basename(texture)))
    services["AssetService"].invalidate_alternative_materials_cache()
    applied = result("set_asset_material", dict(name=asset, path=str(mhmat)))
    assert applied["applied"] is True, applied["message"]
    before = _read(asset)
    # MPFB let a colour map be read as data here, since one image holds one colour space.
    assert before["textures"]["diffuse"]["image_name"] == before["textures"]["normalmap"][
        "image_name"]
    stored = result("store_makeskin_material", dict(
        name=asset, store_as="alternate", material_name="from_mpfb"))
    assert stored["saved"] is True, stored["message"]
    assert stored["values_not_restored"] == {}
    result("set_asset_material", stored["apply_with"]["mpfb_set_asset_material"])
    after = _read(asset)
    assert sorted(after["textures"]) == ["diffuse", "normalmap"]
    assert after["values"] == before["values"]
