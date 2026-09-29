"""
Material settings through a preset and back: ``set_material_settings``, ``save_preset``,
``create_human_from_preset``, ``get_material_settings``.

**The claim is FR 040's primary goal**, and it is about four commands at once,
which is why it is here: settings written through ``set_material_settings``
survive ``save_preset`` then ``create_human_from_preset`` with clothes loaded,
and the rebuilt character's ``get_material_settings`` equals the original's -
exactly, since a preset carries each value as the float the socket held.

**And the ordering the request asked to have checked both ways.** A colour
adjustment is applied by ``add_mhclo_asset()`` only in its MakeSkin branch,
after any alternative material, so:

- an alternative material chosen *first* and tinted *afterwards* round-trips
  both - the preset records the material and the tint, and loading applies them
  in that order;
- a tint applied *first* is discarded by ``set_asset_material``, which rebuilds
  the material from its MHMAT. That is requirement 17's claim, and the tool
  description says so.

Everything the preset writes goes to a redirected config directory, and every
asset is read from a redirected data root that stays open across the load, per
``ddd_mutating/__init__.py``.
"""

import os

import bpy

from .._fixtures import Character
from .._fixtures import MATERIAL_FIXTURE_UUIDS
from .._fixtures import material_character
from .._fixtures import material_data_roots
from .._fixtures import redirected_locations
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import write_mhmat
from .._fixtures import write_png

GREEN = [0.05, 0.4, 0.1, 1.0]


def _settings(answer):
    """The preset-shaped part of a read, keyed as a preset keys it."""
    return dict(
        eyes=answer["eyes"]["settings"],
        skin={group: report["settings"] for group, report in answer["skin"]["groups"].items()},
        color_adjustments={record["uuid"]: record["settings"]
                           for record in answer["color_adjustments"] if record["applies"]},
    )


def _save_and_load(services, confdir, basemesh_name, preset_name):
    with redirected_locations(services, user_config=confdir):
        saved = result("save_preset", {"preset_name": preset_name, "name": basemesh_name})
        assert saved["performed"] is True, saved["message"]
        created = result("create_human_from_preset",
                         {"preset_name": preset_name, "load_clothes": True})
    assert created["performed"] is True, created["message"]
    return created["basemesh_name"]


def test_written_settings_survive_a_preset_round_trip(tmp_path):
    services = services_or_skip()
    confdir = str(tmp_path / "config")
    os.makedirs(confdir, exist_ok=True)
    with Character() as character, material_data_roots(services, tmp_path / "data"):
        names = material_character(services, character, tmp_path / "data")
        written = result("set_material_settings", {
            "name": character.basemesh.name,
            "eyes": [{"socket": "IrisMajorColor", "color": GREEN},
                     {"socket": "IrisMinorColor", "color": [0.02, 0.1, 0.03, 1.0]}],
            "skin": [{"group": "color", "socket": "SkinColor", "color": [0.3, 0.15, 0.08, 1.0]},
                     {"group": "color", "socket": "SkinOverride", "value": 1.0},
                     {"group": "lips", "socket": "LipsRoughness", "value": 0.6}],
            "color_adjustments": [
                {"object_name": names["hair"], "socket": "Color1",
                 "color": [0.02, 0.01, 0.005, 1.0]},
                {"object_name": names["hair"], "socket": "Factor", "value": 0.7},
                {"object_name": names["aoshirt"], "socket": "Factor", "value": 0.4}],
        })
        assert written["performed"] is True, written["resolution_errors"]
        original = _settings(result("get_material_settings", {"name": character.basemesh.name}))

        rebuilt_name = _save_and_load(services, confdir, character.basemesh.name, "materials")
        assert rebuilt_name != character.basemesh.name
        rebuilt = _settings(result("get_material_settings", {"name": rebuilt_name}))

        assert rebuilt["eyes"] == original["eyes"]
        assert rebuilt["skin"] == original["skin"]
        assert rebuilt["color_adjustments"] == original["color_adjustments"]
        assert len(rebuilt["color_adjustments"]) == 3, "hair, garment and aoshirt"


def test_an_alternative_material_then_a_tint_both_survive(tmp_path):
    services = services_or_skip()
    confdir = str(tmp_path / "config")
    os.makedirs(confdir, exist_ok=True)
    data = tmp_path / "data"
    with Character() as character, material_data_roots(services, data):
        names = material_character(services, character, data)
        texture = write_png(os.path.join(str(data), "textures", "red.png"), (0.8, 0.1, 0.1, 1.0))
        alternative = write_mhmat(
            os.path.join(str(data), "clothes", "fixture_garment", "fixture_garment_red.mhmat"),
            lines=("diffuseTexture " + texture,))
        applied = result("set_asset_material", {"name": names["garment"], "path": alternative})
        assert applied["performed"] is True, applied["message"]
        written = result("set_material_settings", {
            "name": character.basemesh.name,
            "color_adjustments": [{"object_name": names["garment"], "socket": "Color1",
                                   "color": GREEN},
                                  {"object_name": names["garment"], "socket": "Factor",
                                   "value": 0.35}]})
        assert written["performed"] is True, written["resolution_errors"]
        original = _settings(result("get_material_settings", {"name": character.basemesh.name}))

        rebuilt_name = _save_and_load(services, confdir, character.basemesh.name, "alternative")
        rebuilt = result("get_material_settings", {"name": rebuilt_name})

        assert _settings(rebuilt)["color_adjustments"] == original["color_adjustments"]
        garment = [record for record in rebuilt["color_adjustments"]
                   if record["uuid"] == MATERIAL_FIXTURE_UUIDS["garment"]][0]
        info = result("get_object_info", {"name": garment["object_name"]})
        assert info["asset_info"]["material_source"].endswith("fixture_garment_red.mhmat"), \
            "the alternative material should have been restored as well as the tint"


def test_a_tint_then_an_alternative_material_loses_the_tint(tmp_path):
    services = services_or_skip()
    data = tmp_path / "data"
    with Character() as character, material_data_roots(services, data):
        names = material_character(services, character, data)
        before = [record for record in result("get_material_settings", {
            "name": character.basemesh.name, "section": "color_adjustments"})[
                "color_adjustments"] if record["object_name"] == names["garment"]][0]
        result("set_material_settings", {
            "name": character.basemesh.name,
            "color_adjustments": [{"object_name": names["garment"], "socket": "Factor",
                                   "value": 0.35}]})

        texture = write_png(os.path.join(str(data), "textures", "red.png"), (0.8, 0.1, 0.1, 1.0))
        alternative = write_mhmat(
            os.path.join(str(data), "clothes", "fixture_garment", "fixture_garment_red.mhmat"),
            lines=("diffuseTexture " + texture,))
        result("set_asset_material", {"name": names["garment"], "path": alternative})

        after = [record for record in result("get_material_settings", {
            "name": character.basemesh.name, "section": "color_adjustments"})[
                "color_adjustments"] if record["object_name"] == names["garment"]][0]
        assert after["settings"]["Factor"] == before["settings"]["Factor"], \
            "set_asset_material rebuilds the material from MPFB's defaults"
        assert after["settings"]["Factor"] != 0.35
        assert bpy.data.objects[names["garment"]].material_slots[0].material.name.startswith(
            "makeskinmaterial")
