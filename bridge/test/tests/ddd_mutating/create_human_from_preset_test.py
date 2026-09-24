"""
``create_human_from_preset`` against a real MPFB, and against ``save_preset``.

**This is the only place the two halves of one JSON are checked against each
other.** One command writes the file and the other reads it; a fixture preset
written by hand would be a third opinion about a format neither of them owns. So
every test here saves through ``save_preset``'s own command first, and then
loads what was written.

Three claims live here:

- **It creates a character rather than loading into one.**
  ``deserialize_from_dict()`` calls ``create_human()`` unconditionally, so this
  is asserted by counting the basemeshes before and after - the naming of the
  command is the warning, and this is the check behind it.
- **The settings dict really is MPFB's own.** ``deserialize_from_dict()`` reads
  eight keys with ``[]`` rather than ``.get()``, so a dict assembled from
  literals is one forgotten key away from a ``KeyError`` with a character half
  built. The command starts from ``get_default_deserialization_settings()`` and
  checks all eight are there; this asserts that the *check* is meaningful by
  reading the settings the answer reports.
- **Its failure is not a no-op**, which is the one place in the package where
  losing that would be dangerous. A preset naming a rig this Blender does not
  have raises from inside MPFB *after* ``create_human()`` has run, so the answer
  has to name what is now in the scene. Provoked here by editing a saved
  preset's rig field, which is the situation a user reaches by moving a preset
  between installs.
"""

import json
import os

import bpy

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import redirected_locations
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution


def _result(params=None):
    return _fixture_result("create_human_from_preset", params)


def _config(root):
    confdir = os.path.join(str(root), "config")
    os.makedirs(confdir, exist_ok=True)
    return confdir


def _saved(services, confdir, name, subject=None):
    """One preset, written through save_preset's own command."""
    params = {"preset_name": name, "overwrite": True}
    if subject is not None:
        params["name"] = subject
    with redirected_locations(services, user_config=confdir):
        envelope = dispatch("save_preset", params)
    assert envelope["status"] == "ok", "the fixture save should have succeeded: {!r}".format(
        envelope)
    assert envelope["result"]["saved"] is True, envelope["result"]["message"]
    return envelope["result"]["path"]


def _basemesh_count(services):
    return len([blender_object for blender_object in bpy.data.objects
                if services["ObjectService"].get_object_type(blender_object) == "Basemesh"])


class _Created:
    """Whatever this block created, deleted again however the test ends."""

    def __init__(self):
        self._before = None

    def __enter__(self):
        self._before = set(blender_object.name for blender_object in bpy.data.objects)
        return self

    def __exit__(self, *args):
        for blender_object in list(bpy.data.objects):
            if blender_object.name not in self._before:
                bpy.data.objects.remove(blender_object, do_unlink=True)


def test_a_saved_preset_loads_back_as_a_new_character():
    """commands.save_preset then commands.create_human_from_preset

    The round trip, against one real MPFB. Neither command owns the format, so
    this is the only check that they agree about it.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "from-preset-roundtrip"))
    with _Character(macro_detail_dict={
            "gender": 1.0, "age": 0.7, "muscle": 0.5, "weight": 0.5,
            "proportions": 0.5, "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
            "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}}) as character:
        _saved(services, confdir, "roundtrip", character.basemesh.name)

        with _Created():
            with redirected_locations(services, user_config=confdir):
                result = _result({"preset_name": "roundtrip"})

            assert result["performed"] is True, result["message"]
            assert result["created"] is True
            rebuilt = bpy.data.objects[result["basemesh_name"]]
            assert rebuilt is not character.basemesh, "a *new* character, not the old one"

            # A record *of* an object names it `name` (FR 037), as list_objects does.
            for record in result["equipped_assets"]:
                assert set(record) == {"kind", "name", "asset_source"}, record
                assert record["name"] in bpy.data.objects

            stored = services["TargetService"].get_macro_info_dict_from_basemesh(rebuilt)
            assert abs(stored["gender"] - 1.0) < 0.0001, \
                "the phenotype should have survived the round trip, got {!r}".format(
                    stored["gender"])
            assert abs(stored["age"] - 0.7) < 0.0001


def test_it_creates_a_character_rather_than_loading_into_one():
    """commands.create_human_from_preset adds to the scene

    The command is named for this because "load a preset" reads to an agent like
    "restore over what is there".
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "from-preset-creates"))
    with _Character() as character:
        _saved(services, confdir, "creates", character.basemesh.name)
        before = _basemesh_count(services)

        with _Created():
            with redirected_locations(services, user_config=confdir):
                result = _result({"preset_name": "creates"})

            assert _basemesh_count(services) == before + 1, \
                "one more basemesh than before, not the same one reused"
            assert character.basemesh.name in bpy.data.objects, \
                "and the existing character is untouched"
            assert result["objects_created"], "the answer should name what appeared"


def test_the_settings_used_are_mpfbs_own_defaults_with_overrides_written_in():
    """commands.create_human_from_preset reports the dict it handed MPFB

    ``deserialize_from_dict()`` reads eight keys with ``[]``. This asserts they
    are all there, against the install this is running on rather than the one
    the command was written against.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "from-preset-settings"))
    with _Character() as character:
        _saved(services, confdir, "settings", character.basemesh.name)

        with _Created():
            with redirected_locations(services, user_config=confdir):
                result = _result({"preset_name": "settings", "load_clothes": False})

        settings = result["settings_used"]
        for key in ("mask_helpers", "detailed_helpers", "extra_vertex_groups", "feet_on_ground",
                    "scale", "subdiv_levels", "load_clothes", "material_instances"):
            assert key in settings, \
                "{!r} is read with [] inside MPFB and must be in the dict".format(key)
        assert settings["load_clothes"] is False, "the override should have been written in"
        # The two MPFB's defaults omit, added rather than assumed to be there.
        assert settings["override_rig"] == "PRESET"
        assert settings["override_skin_model"] == "PRESET"
        # `overrides` is keyed by this command's arguments, which FR 037 named by
        # the glossary, while settings_used keeps MPFB's keys: `used` has to be
        # read across that mapping, not by the argument's own name.
        overrides = result["overrides"]
        assert set(overrides) == {
            "override_rig", "override_skin_type", "override_clothes_material_type",
            "override_eyes_material_type", "load_clothes", "scale", "material_instances_policy"}
        assert overrides["override_skin_type"]["used"] == settings["override_skin_model"]
        assert overrides["material_instances_policy"]["used"] == settings["material_instances"]
        assert overrides["load_clothes"]["used"] is False


def test_material_instances_policy_follows_mpfbs_panel_rather_than_the_service_default():
    """commands.create_human_from_preset with material_instances_policy omitted

    ``get_default_deserialization_settings()`` says NEVER; MPFB's own "from
    preset" panel defaults to ENHANCED, and a character loaded here should be
    the one the user would have got from that panel. Both are reported so the
    substitution is never silent.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "from-preset-instances"))
    with _Character() as character:
        _saved(services, confdir, "instances", character.basemesh.name)

        with _Created():
            with redirected_locations(services, user_config=confdir):
                result = _result({"preset_name": "instances"})

        assert result["material_instances_policy_requested"] is None
        assert result["material_instances_policy_used"] == "ENHANCED"
        assert result["material_instances_policy_service_default"] == "NEVER", \
            "if MPFB's service default changes, this substitution needs revisiting; got " \
            "{!r}".format(result["material_instances_policy_service_default"])


def test_a_preset_naming_a_rig_this_blender_lacks_names_what_it_left_behind():
    """commands.create_human_from_preset on a preset edited to name a missing rig

    **The one place in the package where a failure that lost its report would be
    dangerous.** ``_check_add_rig()`` raises after ``create_human()`` has
    already run, so a naked character is in the scene and only
    ``objects_created`` says which objects it is.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "from-preset-badrig"))
    with _Character() as character:
        path = _saved(services, confdir, "badrig", character.basemesh.name)

        with open(path, "r", encoding="utf-8") as handle:
            human_info = json.load(handle)
        human_info["rig"] = "no-such-rig-anywhere"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(human_info, handle)

        with _Created():
            with redirected_locations(services, user_config=confdir):
                envelope = dispatch("create_human_from_preset", {"preset_name": "badrig"})

            assert envelope["status"] == "ok", \
                "a mid-way failure must be an answer, not a command_failed: {!r}".format(
                    envelope)
            result = envelope["result"]
            assert result["created"] is False
            assert result["blocked_by"] == "deserialization_failed"
            assert result["performed"] is False
            assert result["objects_created"], \
                "MPFB had already built something before it raised, and the answer must name it"
            for name in result["objects_created"]:
                assert name in bpy.data.objects, \
                    "{!r} was named as left behind and must really be there".format(name)
            assert result["preset_rig"] == "no-such-rig-anywhere"


def test_an_unknown_preset_name_offers_what_is_there():
    """commands.create_human_from_preset with a misspelled name

    The likeliest way this is called wrongly, so the refusal ends the guessing.
    The names come from the directory rather than MPFB's cached list.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "from-preset-unknown"))
    with _Character() as character:
        _saved(services, confdir, "realpreset", character.basemesh.name)

        with redirected_locations(services, user_config=confdir):
            result = _result({"preset_name": "notapreset"})

        assert result["created"] is False
        assert result["blocked_by"] == "preset_not_found"
        assert "realpreset" in result["available_presets"], \
            "the refusal should offer what is actually there: {!r}".format(
                result["available_presets"])


def test_an_unreadable_preset_is_an_answer():
    """commands.create_human_from_preset on a truncated file"""
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "from-preset-unreadable"))
    with open(os.path.join(confdir, "human.broken.json"), "w", encoding="utf-8") as handle:
        handle.write("{ not json at all")

    with redirected_locations(services, user_config=confdir):
        result = _result({"preset_name": "broken"})

    assert result["created"] is False
    assert result["blocked_by"] == "preset_unreadable"
    assert result["file"]["size_bytes"] > 0


def test_the_selection_is_not_restored_and_the_answer_says_so():
    """commands.create_human_from_preset activates what it created

    The same exception generate_rigify_rig has, and for the same reason: there
    is no prior state to restore to.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "from-preset-selection"))
    with _Character() as character:
        _saved(services, confdir, "selection", character.basemesh.name)

        with _Created():
            with redirected_locations(services, user_config=confdir):
                result = _result({"preset_name": "selection"})

            assert result["active_object_after"] is not None
            assert bpy.context.view_layer.objects.active.name == result["active_object_after"], \
                "the reported active object must be the one that is active"
            assert "not restored" in result["message"]


def test_the_preset_name_is_required_by_the_contract():
    """commands.create_human_from_preset with no preset_name at all"""
    _services_or_skip()
    envelope = dispatch("create_human_from_preset", {})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "preset_name" in envelope["message"]


def test_an_unknown_material_instances_policy_is_refused_by_the_contract():
    """commands.create_human_from_preset with a value outside the three

    ``_set_skin()`` tests the value with substring matches, so an unrecognised
    one silently means NEVER rather than failing.
    """
    _services_or_skip()
    envelope = dispatch("create_human_from_preset",
                        {"preset_name": "anything", "material_instances_policy": "SOMETIMES"})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "ENHANCED" in envelope["message"]


def test_mpfb_being_unavailable_refuses_rather_than_half_building():
    """commands.create_human_from_preset against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("create_human_from_preset", {"preset_name": "anything"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
