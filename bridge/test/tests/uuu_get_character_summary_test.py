"""
``get_character_summary`` against a real MPFB: never a second opinion.

The test this command is really about is
:func:`test_every_shared_field_agrees_with_its_detailed_command`. For one
character, rigged, dressed, skinned, morphed, wearing a saved expression with a
face unit composed on top of it, the summary and **each detailed command** are
dispatched, and every field the summary shares with one of them is asserted
equal to that command's answer. The summary reads each section through the
shared module its detailed command uses
([FR 034](../../../feature-requests/034-character-summary/README.md)), so today
the two agree by construction; this test is what keeps them agreeing after
somebody has forgotten why - a copy of a reading grown inside one command would
pass that command's own tests and fail here.

It asks twice, because the fixtures cannot give one moment where every section
is interesting. The expression fixture redirects MPFB's data roots to a small
``faceunits01`` pack, and inside it MPFB's bundled ``target.json`` is out of
reach, so the rollup reads empty in both commands; outside it the rollup is
real and the stack's rows no longer resolve. Agreement is asserted in both
states, which is also two different shapes of ``face`` for free.

The cap on the rollup is tested by lowering it on the module rather than by
building sixty categories: what is under test is which entries are kept and
that the cut is reported, not how many a real character carries - the live
check measured that.
"""

import os

import bpy
import pytest

from . import bridge_module
from ._fixtures import Character
from ._fixtures import dispatch
from ._fixtures import expression_library
from ._fixtures import linked_plain_object
from ._fixtures import redirected_locations
from ._fixtures import result
from ._fixtures import services_or_skip
from ._fixtures import supplied_resolution
from ._fixtures import write_loadable_mhclo

COMMAND = "get_character_summary"

SECTIONS = ("phenotype", "rig", "assets", "skin", "targets", "face")

# Four categories MPFB itself ships in target.json, two of them sided, so the
# rollup has entries and asymmetries to report. Values chosen distinct in
# magnitude, so that "the largest are kept" has one right answer.
MODIFIERS = [
    {"section": "nose", "category": "nose-scale-depth-decr-incr", "value": 0.4},
    {"section": "chin", "category": "chin-height-decr-incr", "value": -0.2},
    {"section": "ears", "category": "ear-lobe-decr-incr", "side": "left", "value": 0.5},
    {"section": "ears", "category": "ear-lobe-decr-incr", "side": "right", "value": 0.1},
    {"section": "eyes", "category": "eye-bag-decr-incr", "side": "left", "value": 0.3},
]


def _pick(dictionary, keys):
    return {key: dictionary.get(key) for key in keys}


def _dress(services, character, root):
    """A rig, then a garment, then a skin and some modeling: the order MPFB needs."""
    name = character.basemesh.name
    added = result("add_rig", {"name": name, "identifier": "default"})
    assert added["performed"] is True, added["message"]

    write_loadable_mhclo(os.path.join(str(root), "clothes", "spike", "spike.mhclo"))
    with redirected_locations(services, user_data=str(root)):
        equipped = result("add_asset", {
            "name": name, "fragment": "spike/spike.mhclo", "asset_type": "Clothes"})
    assert equipped["added"] is True, equipped["message"]

    skinned = result("set_skin", {"name": name, "skin_type": "LAYERED"})
    assert skinned["performed"] is True, skinned["message"]

    modelled = result("set_targets", {"name": name, "modifiers": MODIFIERS})
    assert modelled["performed"] is True, modelled["message"]
    return equipped["asset_object_name"]


def _put_on_a_face(name):
    """Inside an expression_library: a saved expression, and a unit composed on top."""
    result("apply_expressions", {
        "name": name, "expressions": [{"fragment": "smile.json", "weight": 0.5}],
        "refit": False})
    result("set_face_units", {
        "name": name, "refit": False,
        "face_units": [{"face_unit": "browInnerUp", "weight": 0.4}]})


def _assert_agreement(name):
    """Every field the summary shares with a detailed command, against that command."""
    summary = result(COMMAND, {"name": name})
    assert summary["found"] is True

    macro = result("get_macro_details", {"name": name})
    for key in ("subject_name", "subject_resolved_by", "basemesh_name",
                "basemesh_in_current_scene"):
        assert summary[key] == macro[key], key
    assert summary["phenotype"] == _pick(
        macro, ("macro_details", "race_sum", "race_normalized", "macro_drift"))

    basemesh = summary["basemesh_name"]
    info = result("get_object_info", {"name": basemesh})
    assert summary["skin"] == _pick(
        info["asset_info"], ("material_type", "material_source", "mhmat_path"))

    expected_assets = []
    for entry in info["related_objects"]:
        if entry["object_type"] in ("Skeleton", "Subrig", "Basemesh", None):
            continue
        row = _pick(entry, ("name", "object_type", "in_current_scene"))
        row.update(_pick(entry["asset_info"], ("asset_source", "material_type",
                                                "material_source")))
        expected_assets.append(row)
    expected_assets.sort(key=lambda row: (row["object_type"], row["name"]))
    assert summary["assets"] == expected_assets

    skeletons = [entry["name"] for entry in info["related_objects"]
                 if entry["object_type"] == "Skeleton"]
    if summary["rig"] is None:
        assert skeletons == []
    else:
        assert summary["rig"]["name"] in skeletons
        rig_info = result("get_object_info", {"name": summary["rig"]["name"]})
        expected_rig = _pick(rig_info, ("name", "in_current_scene", "rigify_role"))
        expected_rig.update(_pick(rig_info["asset_info"], ("rig_type", "rig_definition_path")))
        assert summary["rig"] == expected_rig

    stack = result("get_target_stack", {"name": name})
    targets = summary["targets"]
    for key in ("modifiers", "asymmetries", "counts_by_kind", "total_count", "modifier_count"):
        assert targets[key] == stack[key], key
    assert targets["asymmetry_count"] == len(stack["asymmetries"])
    assert targets["rollup_truncated"] is False

    units = result("get_face_units", {"name": name})
    expression = result("get_expression", {"name": name})
    face = summary["face"]
    assert face["faceunits01_installed"] == units["faceunits01_installed"]
    assert face["face_units"] == [_pick(entry, ("face_unit", "weight"))
                                  for entry in units["face_units"]]
    assert face["applied_expressions"] == [_pick(row, ("fragment", "weight", "resolved"))
                                           for row in expression["applied_expressions"]]
    assert face["matches_stack"] == expression["matches_stack"]
    assert face["unexplained_face_units"] == expression["unexplained_face_units"]
    return summary


def test_every_shared_field_agrees_with_its_detailed_command(tmp_path):
    """The summary, dispatched beside each command it summarizes, on one character"""
    services = services_or_skip()
    with Character() as character:
        basemesh_name = character.basemesh.name
        garment = _dress(services, character, tmp_path / "assets")
        with expression_library(services, tmp_path / "expressions"):
            _put_on_a_face(basemesh_name)
            # Asked by the garment's name, so the family resolution is in it too.
            inside = _assert_agreement(garment)
        outside = _assert_agreement(garment)

    assert inside["subject_name"] == garment
    assert inside["basemesh_name"] == basemesh_name
    assert inside["rig"]["rig_type"] == "default"
    assert [row["name"] for row in inside["assets"]] == [garment]
    # Inside the fixture the stack explains everything but the composed unit;
    # outside it, the saved file is out of reach and explains nothing.
    assert inside["face"]["applied_expressions"] == [
        {"fragment": "smile.json", "weight": 0.5, "resolved": True}]
    assert [entry["face_unit"] for entry in inside["face"]["unexplained_face_units"]] == [
        "browInnerUp"]
    assert outside["face"]["applied_expressions"] == [
        {"fragment": "smile.json", "weight": 0.5, "resolved": False}]
    # And the other way about for the rollup, which is why the test asks twice.
    assert inside["targets"]["modifiers"] == []
    assert len(outside["targets"]["modifiers"]) == 5
    assert len(outside["targets"]["asymmetries"]) == 2


def test_a_bare_basemesh_has_empty_sections_not_missing_ones():
    with Character() as character:
        summary = _assert_agreement(character.basemesh.name)

    assert summary["rig"] is None
    assert summary["assets"] == []
    assert summary["targets"]["modifiers"] == []
    assert summary["face"]["face_units"] == []
    assert summary["face"]["matches_stack"] is True
    assert summary["phenotype"]["macro_drift"] is False


def test_a_generated_rigify_rig_is_the_rig():
    """MPFB tags the rig Rigify generates as a Skeleton; the summary says which kind"""
    services = services_or_skip()
    if not services["SystemService"].check_for_rigify():
        pytest.skip("Rigify is not enabled in this Blender, so no rig can be generated")
    with Character() as character:
        result("add_rig", {"name": character.basemesh.name, "identifier": "rigify.human"})
        generated = result("generate_rigify_rig", {"name": character.basemesh.name})
        summary = _assert_agreement(character.basemesh.name)

    assert summary["rig"]["name"] == generated["rig_object_name"]
    assert summary["rig"]["rigify_role"] == "generated_rig"


def test_the_rollup_is_capped_to_its_largest_entries_and_says_so(monkeypatch):
    """What is kept, in whose order, and that the cut is never silent"""
    command = bridge_module("commands.get_character_summary")
    monkeypatch.setattr(command, "MODIFIER_CAP", 2)
    monkeypatch.setattr(command, "ASYMMETRY_CAP", 1)
    with Character() as character:
        name = character.basemesh.name
        result("set_targets", {"name": name, "modifiers": MODIFIERS})
        stack = result("get_target_stack", {"name": name})
        targets = result(COMMAND, {"name": name})["targets"]

    assert targets["rollup_truncated"] is True
    assert targets["modifier_count"] == len(stack["modifiers"]) == 5
    assert targets["asymmetry_count"] == len(stack["asymmetries"]) == 2
    # The two furthest from zero, in get_target_stack's own order.
    assert targets["modifiers"] == [entry for entry in stack["modifiers"]
                                    if abs(entry["value"]) in (0.5, 0.4)]
    assert targets["asymmetries"] == [entry for entry in stack["asymmetries"]
                                      if entry["category"] == "ear-lobe-decr-incr"]


def test_reading_changes_nothing():
    """No recalculation, no selection change: a read the caller believed read-only"""
    with Character() as character:
        basemesh = character.basemesh
        bpy.context.view_layer.objects.active = None
        basemesh.select_set(False)
        values = [block.value for block in basemesh.data.shape_keys.key_blocks]

        result(COMMAND, {"name": basemesh.name})

        assert [block.value for block in basemesh.data.shape_keys.key_blocks] == values
        assert bpy.context.view_layer.objects.active is None
        assert basemesh.select_get() is False


def test_a_miss_is_an_answer_with_every_section_present():
    services_or_skip()
    absent = result(COMMAND, {"name": "BridgeTestNoSuchObject"})
    assert absent["found"] is False
    assert absent["subject_name"] is None
    assert "No object named" in absent["message"]

    plain = linked_plain_object("BridgeTestNotACharacter")
    try:
        unrelated = result(COMMAND, {"name": plain.name})
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)
    assert unrelated["found"] is False
    assert unrelated["subject_name"] == "BridgeTestNotACharacter"
    assert unrelated["subject_in_current_scene"] is True
    assert "no MakeHuman basemesh" in unrelated["message"]

    for answer in (absent, unrelated):
        for section in SECTIONS:
            assert section in answer, section
        assert answer["assets"] == []
        assert all(answer[section] is None for section in SECTIONS if section != "assets")


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = dispatch(COMMAND, {"name": None})

    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE
