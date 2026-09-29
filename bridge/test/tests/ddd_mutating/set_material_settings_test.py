"""
``set_material_settings`` against a real MPFB: resolve everything, then write through MPFB.

Every write is read back through ``get_material_settings``, whose own module in
``ccc_reading/`` has passed by the time this one runs, so "written" means the
read reports it - which is what an agent will check.

Three claims beyond the round trip are made here:

- **One bad entry writes nothing.** A batch with a valid eye colour and a
  misspelled skin socket leaves the eye colour as it was.
- **Each refusal says what to do instead.** A linked layered socket names the
  ``color`` group's socket that drives it, as ``write_instead``.
- **Nothing is borrowed.** Writing a socket's default value needs no active
  object, selection or mode, so the command must leave all three alone even
  though it acts on objects other than the one active.

The range rule has two halves, and both are asserted against the live install:
a group input outside its declared range is refused unless MPFB's own value
already contradicts that range, and a built-in node's factor is refused
because Blender would clamp it.
"""

import bpy

from .._fixtures import Character
from .._fixtures import MATERIAL_FIXTURE_UUIDS
from .._fixtures import material_character
from .._fixtures import material_data_roots
from .._fixtures import result
from .._fixtures import services_or_skip

COMMAND = "set_material_settings"
GREEN = [0.05, 0.4, 0.1, 1.0]


def _write(name, **sections):
    params = {"name": name}
    params.update(sections)
    return result(COMMAND, params)


def _read(name):
    return result("get_material_settings", {"name": name})


def _record(answer, object_name):
    return [record for record in answer["color_adjustments"]
            if record["object_name"] == object_name][0]


def test_each_section_is_written_and_read_back(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)
        before = _read(character.basemesh.name)

        answer = _write(
            character.basemesh.name,
            eyes=[{"socket": "IrisMajorColor", "color": GREEN},
                  {"socket": "PupilSize", "value": 0.25}],
            skin=[{"group": "color", "socket": "SkinColor", "color": [0.3, 0.15, 0.08, 1.0]},
                  {"group": "color", "socket": "SkinOverride", "value": 1.0}],
            color_adjustments=[{"object_name": names["hair"], "socket": "Color1",
                                "color": [0.02, 0.01, 0.005, 1.0]},
                               {"object_name": names["hair"], "socket": "Factor",
                                "value": 0.8}])

        assert answer["performed"] is True, answer["message"]
        assert answer["resolution_errors"] == []
        assert answer["change_count"] == 6
        assert [(change["section"], change["socket"]) for change in answer["changes"]] == [
            ("eyes", "IrisMajorColor"), ("eyes", "PupilSize"),
            ("skin", "SkinColor"), ("skin", "SkinOverride"),
            ("color_adjustments", "Color1"), ("color_adjustments", "Factor")], \
            "changes are reported in request order"
        iris = answer["changes"][0]
        assert iris["previous_value"] == before["eyes"]["settings"]["IrisMajorColor"]
        assert iris["new_srgb_hex"] != iris["previous_srgb_hex"]
        assert answer["changes"][1]["previous_srgb_hex"] is None, "a float has no hex"

        after = _read(character.basemesh.name)
        assert after["eyes"]["settings"]["IrisMajorColor"] == \
            [float(channel) for channel in bpy.data.objects[names["eyes"]]
             .material_slots[0].material.node_tree.nodes[after["eyes"]["node_name"]]
             .inputs["IrisMajorColor"].default_value]
        assert all(abs(got - wanted) < 1e-6 for got, wanted in
                   zip(after["eyes"]["settings"]["IrisMajorColor"], GREEN))
        assert abs(after["eyes"]["settings"]["PupilSize"] - 0.25) < 1e-6
        assert abs(after["skin"]["groups"]["color"]["settings"]["SkinOverride"] - 1.0) < 1e-6
        hair = _record(after, names["hair"])
        assert abs(hair["settings"]["Factor"] - 0.8) < 1e-6
        assert [change["new_value"] for change in answer["changes"]] == [
            after["eyes"]["settings"]["IrisMajorColor"], after["eyes"]["settings"]["PupilSize"],
            after["skin"]["groups"]["color"]["settings"]["SkinColor"],
            after["skin"]["groups"]["color"]["settings"]["SkinOverride"],
            hair["settings"]["Color1"], hair["settings"]["Factor"]], \
            "new_value is what the read now reports"

        written = {entry["object_name"] for entry in answer["materials_written"]}
        assert written == {names["eyes"], names["body"], names["hair"]}


def test_one_bad_entry_writes_nothing(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        material_character(services, character, tmp_path)
        before = _read(character.basemesh.name)

        answer = _write(character.basemesh.name,
                        eyes=[{"socket": "IrisMajorColor", "color": GREEN}],
                        skin=[{"group": "color", "socket": "SkinColour", "color": GREEN}])

        assert answer["performed"] is False
        assert answer["changes"] == []
        assert len(answer["resolution_errors"]) == 1
        error = answer["resolution_errors"][0]
        assert error["reason"] == "unknown_socket"
        assert error["section"] == "skin" and error["index"] == 0
        assert "SkinColor" in error["closest"]
        assert _read(character.basemesh.name)["eyes"]["settings"] == \
            before["eyes"]["settings"], "the valid eye entry must not have been written"


def test_a_linked_socket_is_refused_naming_what_to_write_instead(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)

        answer = _write(
            character.basemesh.name,
            skin=[{"group": "body", "socket": "SkinColor", "color": GREEN}],
            color_adjustments=[{"object_name": names["hair"], "socket": "Color2",
                                "color": GREEN}])

        errors = {error["section"]: error for error in answer["resolution_errors"]}
        assert errors["skin"]["reason"] == "linked_socket"
        assert errors["skin"]["linked_from"] == dict(from_node="colorgroup",
                                                     from_socket="SkinColor")
        assert errors["skin"]["write_instead"] == dict(group="color", socket="SkinColor")
        assert errors["color_adjustments"]["reason"] == "linked_socket"
        assert errors["color_adjustments"]["write_instead"] is None, \
            "a texture is not a socket the caller can set instead"


def test_kind_mismatch_and_unknown_addresses_are_refused(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)

        answer = _write(
            character.basemesh.name,
            eyes=[{"socket": "IrisMajorColor", "value": 0.5},
                  {"socket": "PupilSize", "color": GREEN}],
            skin=[{"group": "colour", "socket": "SkinColor", "color": GREEN}],
            color_adjustments=[{"object_name": "NoSuchObject", "socket": "Factor", "value": 0.5},
                               {"object_name": names["eyes"], "socket": "Factor",
                                "value": 0.5}])

        reasons = [(error["section"], error["reason"]) for error in answer["resolution_errors"]]
        assert reasons == [("eyes", "kind_mismatch"), ("eyes", "kind_mismatch"),
                           ("skin", "unknown_group"),
                           ("color_adjustments", "object_not_found"),
                           ("color_adjustments", "section_not_applicable")]
        assert "color" in answer["resolution_errors"][2]["known_groups"]
        assert answer["resolution_errors"][4]["section_reason"] == "eyes_excluded"
        assert answer["performed"] is False


def test_the_range_rule_and_its_one_exception(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)

        refused = _write(
            character.basemesh.name,
            skin=[{"group": "color", "socket": "SkinOverride", "value": 1.5}],
            color_adjustments=[{"object_name": names["garment"], "socket": "Factor",
                                "value": 1.5}])
        assert [error["reason"] for error in refused["resolution_errors"]] == \
            ["out_of_range", "out_of_range"]
        assert refused["resolution_errors"][0]["range"] == [0.0, 1.0]

        # MPFB's own default for this socket is 11.0 against a declared 0.001-0.2,
        # so the range is not enforced for it.
        accepted = _write(character.basemesh.name,
                          skin=[{"group": "body", "socket": "NavelWidthMultiplier",
                                 "value": 12.0}])
        assert accepted["performed"] is True, accepted["resolution_errors"]
        assert accepted["changes"][0]["new_value"] == 12.0


def test_a_call_naming_nothing_answers_without_writing():
    with Character() as character:
        answer = _write(character.basemesh.name)

        assert answer["found"] is True
        assert answer["ready"] is True
        assert answer["performed"] is False
        assert answer["changes"] == [] and answer["change_count"] == 0
        assert "mpfb_get_material_settings" in answer["message"]


def test_a_section_that_does_not_apply_is_a_resolution_error():
    with Character() as character:
        answer = _write(character.basemesh.name,
                        eyes=[{"socket": "IrisMajorColor", "color": GREEN}])

        error = answer["resolution_errors"][0]
        assert error["reason"] == "section_not_applicable"
        assert error["section_reason"] == "no_eyes"


def test_a_malformed_entry_from_another_client_is_a_resolution_error():
    """The socket is reachable by clients other than mpfb-mcp, which checks this too."""
    with Character() as character:
        answer = _write(character.basemesh.name,
                        eyes=[{"socket": "IrisMajorColor", "color": [0.1, 0.2, 0.3]},
                              {"socket": "PupilSize", "value": True},
                              "PupilSize",
                              {"socket": "PupilSize", "value": 0.2},
                              {"socket": "PupilSize", "value": 0.3}])

        reasons = [error["reason"] for error in answer["resolution_errors"]]
        assert reasons[:3] == ["invalid_entry", "invalid_entry", "invalid_entry"]
        assert "alpha is required" in answer["resolution_errors"][0]["message"]
        assert "duplicate_entry" in reasons


def test_a_shared_material_is_reported_as_changed_for_its_other_users(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)
        eyes = bpy.data.objects[names["eyes"]]
        copy = bpy.data.objects.new("BridgeTestEyeCopy", eyes.data.copy())
        bpy.context.scene.collection.objects.link(copy)

        answer = _write(character.basemesh.name,
                        eyes=[{"socket": "IrisMajorColor", "color": GREEN}])

        assert answer["materials_written"] == [dict(
            material_name=eyes.material_slots[0].material.name, object_name=names["eyes"],
            material_shared_with=["BridgeTestEyeCopy"])]
        assert "BridgeTestEyeCopy" in answer["message"]


def test_selection_active_object_and_mode_are_left_alone(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)
        view_layer = bpy.context.view_layer
        hair = bpy.data.objects[names["hair"]]
        for blender_object in view_layer.objects:
            blender_object.select_set(False)
        hair.select_set(True)
        view_layer.objects.active = hair
        mode_before = hair.mode

        answer = _write(character.basemesh.name,
                        eyes=[{"socket": "IrisMajorColor", "color": GREEN}],
                        skin=[{"group": "color", "socket": "SkinOverride", "value": 0.5}],
                        color_adjustments=[{"object_name": names["garment"],
                                            "socket": "Factor", "value": 0.5}])

        assert answer["performed"] is True
        assert view_layer.objects.active == hair
        assert [blender_object.name for blender_object in view_layer.objects
                if blender_object.select_get()] == [hair.name]
        assert hair.mode == mode_before


def test_the_colour_adjustment_is_keyed_by_the_assets_uuid(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)
        _write(character.basemesh.name,
               color_adjustments=[{"object_name": names["garment"], "socket": "Factor",
                                   "value": 0.3}])

        adjustment = services["MaterialService"].find_color_adjustment(
            bpy.data.objects[names["garment"]])
        assert abs(adjustment["Factor"] - 0.3) < 1e-6, \
            "MPFB's own reader must see what was written, since it is what a preset saves"
        assert _record(_read(character.basemesh.name), names["garment"])["uuid"] == \
            MATERIAL_FIXTURE_UUIDS["garment"]
