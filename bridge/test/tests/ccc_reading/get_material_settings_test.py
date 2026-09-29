"""
``get_material_settings`` against a real MPFB: every section, and agreement with the serializer.

**The claim this module exists for is agreement with MPFB's own serializer**,
key for key: what the command reports as ``settings`` is what
``HumanService.serialize_to_json_string()`` writes under
``eyes_material_settings``, ``skin_material_settings`` and
``color_adjustments`` for the same character. It is the "never a second
opinion" rule held against MPFB rather than against another command, and it is
what makes a read useful to an agent reasoning about a preset.

The fixture is ``_fixtures.material_character()``: procedural eyes, a LAYERED
skin, a textured hair and garment, and a garment with an AO map - each equipped the way a user would, never written
node by node. The "does not apply" reasons each get a character of their own.

Socket names appear in this module, and only here and in the ``ddd_`` and
``eee_`` modules: they are what the live node is checked for. Neither command
nor tool names one.
"""

import os

import bpy

from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import MATERIAL_FIXTURE_UUIDS
from .._fixtures import material_character
from .._fixtures import material_data_roots
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import write_loadable_mhclo
from .._fixtures import write_mhmat
from .._fixtures import write_png

COMMAND = "get_material_settings"


def _read(name, section=None):
    params = {"name": name}
    if section is not None:
        params["section"] = section
    return result(COMMAND, params)


def _records_by_role(answer, names):
    by_object = {record["object_name"]: record for record in answer["color_adjustments"]}
    return {role: by_object[name] for role, name in names.items() if name in by_object}


def test_every_section_applies_to_the_fixture(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)
        answer = _read(character.basemesh.name)

        assert answer["found"] is True
        assert answer["requested_section"] is None
        eyes = answer["eyes"]
        assert eyes["applies"] is True and eyes["reason"] is None
        assert eyes["object_name"] == names["eyes"]
        assert eyes["material_identified_as"] == "procedural_eyes"
        assert "IrisMinorColor" in eyes["settings"]

        skin = answer["skin"]
        assert skin["applies"] is True
        assert skin["material_identified_as"] == "layered_skin"
        assert set(skin["groups"]) == {"color", "body", "face", "ears", "lips", "aureolae",
                                       "genitals", "fingernails", "toenails"}
        assert skin["groups_missing"] == []
        assert skin["groups_not_serialized"] == []
        assert skin["groups"]["color"]["node_name"] == "colorgroup"

        records = _records_by_role(answer, names)
        assert records["eyes"]["applies"] is False
        assert records["eyes"]["reason"] == "eyes_excluded", \
            "the serializer never records a colour adjustment for the eyes"
        for role in ("hair", "garment", "aoshirt"):
            assert records[role]["applies"] is True, (role, records[role]["reason"])
            assert records[role]["uuid"] == MATERIAL_FIXTURE_UUIDS[role]
            assert records[role]["material_identified_as"] == "makeskin"
        assert records["hair"]["node_name"] == "diffuseIntensity"
        assert records["garment"]["node_name"] == "diffuseIntensity"
        assert records["aoshirt"]["node_name"] == "aoMix", \
            "with an AO map, the node on Base Color is aoMix, and that is what MPFB saves"


def test_settings_agree_with_mpfbs_serializer_key_for_key(tmp_path):
    """commands.get_material_settings equals HumanService.serialize_to_json_string()

    Exact equality, not a tolerance: both sides read the same floats through
    the same NodeService call, and the read rounds nothing.
    """
    import json  # pylint: disable=import-outside-toplevel
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        material_character(services, character, tmp_path)
        answer = _read(character.basemesh.name)
        preset = json.loads(services["HumanService"].serialize_to_json_string(
            character.basemesh))

        assert preset["eyes_material_type"] == "PROCEDURAL_EYES"
        assert preset["eyes_material_settings"] == answer["eyes"]["settings"]
        assert preset["skin_material_type"] == "LAYERED"
        assert preset["skin_material_settings"] == {
            group: report["settings"] for group, report in answer["skin"]["groups"].items()}
        assert preset["color_adjustments"] == {
            record["uuid"]: record["settings"]
            for record in answer["color_adjustments"] if record["applies"]}


def test_linked_sockets_are_reported_with_what_drives_them(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)
        answer = _read(character.basemesh.name)
        groups = answer["skin"]["groups"]

        assert groups["body"]["linked"]["SkinColor"] == dict(
            from_node="colorgroup", from_socket="SkinColor")
        assert groups["face"]["linked"]["EyelidColor"]["from_node"] == "colorgroup"
        assert "SkinColor" not in groups["color"]["linked"], \
            "the colour group's own SkinColor is the one that can be written"

        records = _records_by_role(answer, names)
        assert "Color2" in records["hair"]["linked"], \
            "a diffuse texture drives diffuseIntensity's Color2"
        assert records["hair"]["linked"]["Color2"]["from_socket"] == "Color"
        assert "Color1" not in records["hair"]["linked"], \
            "Color1 is the MHMAT's diffuse colour, and the socket a tint writes"


def test_colours_carry_srgb_hex_and_floats_carry_ranges(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        material_character(services, character, tmp_path)
        answer = _read(character.basemesh.name)
        reports = [answer["eyes"]] + list(answer["skin"]["groups"].values())

        for report in reports:
            for socket, value in report["settings"].items():
                if isinstance(value, list):
                    assert len(value) == 4
                    assert report["srgb_hex"][socket].startswith("#")
                    assert len(report["srgb_hex"][socket]) == 7
                    assert socket not in report["ranges"]
                else:
                    assert isinstance(value, float)
                    assert socket not in report["srgb_hex"]
            for socket in report["values_outside_range"]:
                minimum, maximum = report["ranges"][socket]
                value = report["settings"][socket]
                assert (minimum is not None and value < minimum) or \
                    (maximum is not None and value > maximum)

        color = answer["skin"]["groups"]["color"]
        assert color["ranges"]["SkinOverride"] == [0.0, 1.0]
        # White is white in either colour space.
        assert answer["eyes"]["srgb_hex"]["EyeWhiteColor"] == "#ffffff"


def test_mpfbs_own_default_can_contradict_its_declared_range(tmp_path):
    """MpfbBody declares NavelWidthMultiplier as 0.001-0.2 and defaults it to 11.0.

    A candidate MPFB defect, confirmed here rather than read from source. If
    MPFB fixes it this assertion fails, and set_material_settings' exception
    for such sockets can be reconsidered.
    """
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        material_character(services, character, tmp_path)
        body = _read(character.basemesh.name, section="skin")["skin"]["groups"]["body"]

        assert "NavelWidthMultiplier" in body["values_outside_range"]
        assert body["ranges"]["NavelWidthMultiplier"] == [0.001, 0.2]


def test_a_section_argument_reads_one_section_and_nulls_the_others(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        material_character(services, character, tmp_path)
        for section in ("eyes", "skin", "color_adjustments"):
            answer = _read(character.basemesh.name, section=section)
            assert answer["requested_section"] == section
            for other in ("eyes", "skin", "color_adjustments"):
                if other == section:
                    assert answer[other] is not None
                else:
                    assert answer[other] is None, \
                        "a section not read is null - not computed - rather than empty"


def test_a_bare_character_has_no_eyes_and_no_skin_material():
    with Character() as character:
        answer = _read(character.basemesh.name)

        assert answer["eyes"]["applies"] is False
        assert answer["eyes"]["reason"] == "no_eyes"
        assert answer["skin"]["applies"] is False
        assert answer["skin"]["reason"] in ("no_material", "not_layered")
        assert answer["color_adjustments"] == [], "a bare character wears nothing"


def test_makeskin_eyes_and_skin_and_a_gameengine_garment_do_not_apply(tmp_path):
    services = services_or_skip()
    root = str(tmp_path)
    # Textured, as every real MHMAT is: without one, MPFB builds no
    # diffuseIntensity node and identifies the material as gameengine.
    texture = ("diffuseTexture " + write_png(os.path.join(root, "textures", "plain.png")),)
    skin_mhmat = write_mhmat(os.path.join(root, "skins", "plain", "plain.mhmat"), lines=texture)
    for stem, subdir, lines in (("mseyes", "eyes", texture), ("gameshirt", "clothes", texture),
                                ("bareshirt", "clothes", ())):
        write_loadable_mhclo(os.path.join(root, subdir, stem, stem + ".mhclo"),
                             uuid="b1d9e0a0-0000-4000-8000-0000000{:s}".format(
                                 {"mseyes": "0e1e", "gameshirt": "0ea1", "bareshirt": "0ba1"}[stem]),
                             mhmat_lines=lines)
    with Character() as character, material_data_roots(services, root):
        for stem, object_type, material_type in (("mseyes", "Eyes", "MAKESKIN"),
                                                 ("gameshirt", "Clothes", "GAMEENGINE"),
                                                 ("bareshirt", "Clothes", "MAKESKIN")):
            envelope = dispatch("add_asset", {
                "name": character.basemesh.name, "fragment": stem + "/" + stem + ".mhclo",
                "object_type": object_type, "material_type": material_type})
            assert envelope["status"] == "ok" and envelope["result"]["added"], envelope
        services["HumanService"].set_character_skin(
            skin_mhmat, character.basemesh, skin_type="MAKESKIN", material_instances=False)

        answer = _read(character.basemesh.name)

        assert answer["eyes"]["applies"] is False
        assert answer["eyes"]["reason"] == "not_procedural"
        assert answer["eyes"]["material_identified_as"] == "makeskin"
        assert answer["skin"]["applies"] is False
        assert answer["skin"]["reason"] == "not_layered"
        assert answer["skin"]["material_identified_as"] == "makeskin"

        # Neither garment keeps a tint in a preset, for two different reasons.
        # The GameEngine one has an image node on Base Color, which has no
        # colour or float input. The second is the surprise: a MakeSkin
        # material whose MHMAT names no diffuse texture gets no diffuseIntensity
        # node at all, so MPFB identifies it as gameengine too.
        garments = {record["object_name"].split(".")[-1]: record
                    for record in answer["color_adjustments"]
                    if record["object_type"] == "Clothes"}
        assert garments["gameshirt"]["reason"] == "no_settings_on_node"
        assert garments["gameshirt"]["node_name"] is not None
        assert garments["bareshirt"]["reason"] == "nothing_on_base_color"
        for record in garments.values():
            assert record["material_identified_as"] == "gameengine", record["object_name"]
            assert record["applies"] is False
            assert record.get("settings") is None


def test_a_material_used_outside_the_section_is_named(tmp_path):
    services = services_or_skip()
    with Character() as character, material_data_roots(services, tmp_path):
        names = material_character(services, character, tmp_path)
        eyes = bpy.data.objects[names["eyes"]]
        copy = bpy.data.objects.new("BridgeTestEyeCopy", eyes.data.copy())
        bpy.context.scene.collection.objects.link(copy)

        answer = _read(character.basemesh.name, section="eyes")

        assert answer["eyes"]["material_shared_with"] == ["BridgeTestEyeCopy"], \
            "a write to the eye material would change the copy too"
