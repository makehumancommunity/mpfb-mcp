"""
``store_rig`` against a real MPFB, into a user data root of the test's own.

Every collision is built from small rigs whose bones are known, because what is asserted is
MPFB's own identification: after a store, ``RigService.identify_rig()`` must name the armature as
the rig just stored, and each refusal exists because that would otherwise not be true. Nothing
here writes into the developer's library (``_fixtures.rig_library``).
"""

import json
import os

import bpy

from .._fixtures import Character
from .._fixtures import result
from .._fixtures import rig_library
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table


def _store(**params):
    return result("store_rig", params)


def _authored(character, prefix="t_", weighted=True):
    result("create_rig", {"name": character.basemesh.name, "bones": small_rig_table(prefix)})
    if weighted:
        result("weight_rig", {"name": character.basemesh.name, "method": "automatic"})


def test_a_rig_is_stored_whole_and_found_as_itself(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)) as rigs_dir, Character() as character:
        _authored(character)
        answer = _store(name=character.basemesh.name, rig_name="fr060_test")
        assert answer["stored"] is True and answer["performed"] is True, answer["message"]
        assert answer["path"] == os.path.join(rigs_dir, "fr060_test.json")
        assert sorted(os.listdir(rigs_dir)) == ["fr060_test.json", "weights.fr060_test.json"]
        assert answer["identified_as_after"] == "custom.fr060_test"
        with open(answer["path"], encoding="utf-8") as rig_file:
            header = json.load(rig_file)
        assert header["identifying_bones"] == answer["identifying_bones"]
        assert answer["identifying_bones_chosen_by"] == "picked"
        listed = result("list_rigs")["rigs"]
        assert "custom.fr060_test" in [entry["identifier"] for entry in listed]


def test_a_dry_run_settles_everything_and_writes_nothing(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)) as rigs_dir, Character() as character:
        _authored(character)
        answer = _store(name=character.basemesh.name, rig_name="fr060_test", dry_run=True)
        assert answer["ready"] is True and answer["stored"] is False
        assert answer["performed"] is False
        assert not os.path.exists(rigs_dir), "a dry run makes no directory either"


def test_an_existing_rig_is_refused_unless_overwrite(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)), Character() as character:
        _authored(character)
        _store(name=character.basemesh.name, rig_name="fr060_test")
        again = _store(name=character.basemesh.name, rig_name="fr060_test")
        assert again["blocked_by"] == "rig_exists"
        assert again["file_before"]["exists"] is True
        overwritten = _store(name=character.basemesh.name, rig_name="fr060_test",
                             overwrite=True)
        assert overwritten["overwrote"] is True


def test_identification_collisions_are_refused(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)), Character() as first, Character() as second:
        _authored(first, "a_", weighted=False)
        stored = _store(name=first.basemesh.name, rig_name="rig_a",
                        identifying_bones=["a_hips"], include_weights=False)
        assert stored["stored"] is True

        # A second rig holding every identifying bone of the first.
        table = small_rig_table("b_")
        table[0]["name"] = "a_hips"
        for row in table:
            if row["parent"] == "b_hips":
                row["parent"] = "a_hips"
        result("create_rig", {"name": second.basemesh.name, "bones": table})
        shadowed = _store(name=second.basemesh.name, rig_name="rig_b", include_weights=False,
                          identifying_bones=["b_chest"])
        assert shadowed["blocked_by"] == "identification_shadowed"
        assert shadowed["shadowed_by"] == ["rig_a"]



def test_a_rig_that_would_make_another_ambiguous_is_refused(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)), Character() as first, Character() as second:
        _authored(first, "a_", weighted=False)
        _store(name=first.basemesh.name, rig_name="rig_a", identifying_bones=["a_hips"],
               include_weights=False)
        # Holds rig_a's a_chest but not its identifying a_hips, and is identified by a_chest.
        table = small_rig_table("d_")
        table[1]["name"] = "a_chest"
        for row in table:
            if row["parent"] == "d_chest":
                row["parent"] = "a_chest"
        result("create_rig", {"name": second.basemesh.name, "bones": table})
        would = _store(name=second.basemesh.name, rig_name="rig_d", include_weights=False,
                       identifying_bones=["a_chest"])
        assert would["blocked_by"] == "would_shadow"
        assert would["would_shadow"] == ["rig_a"]


def test_a_rig_a_builtin_rule_claims_is_refused(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)), Character() as character:
        table = small_rig_table()
        table[2]["name"] = "oculi02.R"
        result("create_rig", {"name": character.basemesh.name, "bones": table})
        answer = _store(name=character.basemesh.name, rig_name="fr060_test")
        assert answer["blocked_by"] == "identified_as_builtin"
        assert answer["identified_as"] == "default_no_toes"


def test_a_name_in_another_root_is_refused(tmp_path):
    services = services_or_skip()
    second_root = tmp_path / "second"
    (second_root / "rigs").mkdir(parents=True)
    (second_root / "rigs" / "fr060_test.json").write_text("{}", encoding="utf-8")
    with rig_library(services, str(tmp_path / "user")), Character() as character:
        location_service = services["LocationService"]
        original = location_service._second_root  # pylint: disable=protected-access
        location_service._second_root = str(second_root)  # pylint: disable=protected-access
        try:
            _authored(character, weighted=False)
            answer = _store(name=character.basemesh.name, rig_name="fr060_test")
        finally:
            location_service._second_root = original  # pylint: disable=protected-access
        assert answer["blocked_by"] == "name_shadowed"


def test_masks_are_left_out_unless_asked_for_and_losses_are_named(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)), Character() as character:
        table = small_rig_table()
        table[0]["deform"] = False
        table[3]["tail"] = {"position": {"forward": 0.0, "left": 0.3, "up": 1.1}, "snap": False}
        result("create_rig", {"name": character.basemesh.name, "bones": table})
        result("weight_rig", {"name": character.basemesh.name, "method": "automatic"})
        mask = character.basemesh.vertex_groups.new(name="mhmask-preserve-volume")
        mask.add([0, 1, 2], 1.0, "REPLACE")

        left_out = _store(name=character.basemesh.name, rig_name="masks_out")
        assert left_out["masks_on_body"] == ["mhmask-preserve-volume"]
        assert left_out["masks_written"] == []
        assert left_out["deform_flags_lost"] == ["t_hips"]
        assert "t_arm.L.tail" in [row["end"] for row in left_out["ends_rematched"]]
        with open(left_out["weights_path"], encoding="utf-8") as weights_file:
            assert "mhmask-preserve-volume" not in json.load(weights_file)["weights"]



def test_include_masks_writes_the_bodys_masks(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)), Character() as character:
        _authored(character)
        mask = character.basemesh.vertex_groups.new(name="mhmask-preserve-volume")
        mask.add([0, 1, 2], 1.0, "REPLACE")
        kept = _store(name=character.basemesh.name, rig_name="masks_in", include_masks=True)
        assert kept["masks_written"] == ["mhmask-preserve-volume"]
        with open(kept["weights_path"], encoding="utf-8") as weights_file:
            weights = json.load(weights_file)["weights"]
        assert sorted(index for index, _weight in weights["mhmask-preserve-volume"]) == [0, 1, 2]


def test_the_refusals(tmp_path):
    services = services_or_skip()
    with rig_library(services, str(tmp_path)), Character() as character:
        name = character.basemesh.name
        assert _store(name=name, rig_name="fr060_test")["blocked_by"] == "not_rigged"
        assert _store(name=name, rig_name="bad-name")["blocked_by"] == "invalid_name"
        _authored(character, weighted=False)
        assert _store(name=name, rig_name="fr060_test", identifying_bones=["nope"])[
            "blocked_by"] == "unknown_bone_names"
        assert len([blender_object for blender_object in bpy.data.objects
                    if blender_object.type == "ARMATURE"]) == 1
