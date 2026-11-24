"""
``get_rig_definition`` against a real MPFB: where a definition is read from, and that reading
changes nothing.

Three places a table comes from (``definition_from``), each provoked here: a catalogue rig
fitted in memory, the catalogue file of a rig the character has, and the strategies
``create_rig`` saves on an armature. The round trip that rests on the third - a table built and
read back is the table - is ``eee_composite/rig_roundtrip_test.py``'s.
"""

import bpy

from .._fixtures import Character
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table


def _read(**params):
    return result("get_rig_definition", params)


def _counts(basemesh):
    return (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures),
            len(basemesh.data.shape_keys.key_blocks), basemesh.active_shape_key_index)


def test_a_catalogue_rig_is_fitted_in_memory_and_nothing_is_created():
    services_or_skip()
    with Character() as character:
        before = _counts(character.basemesh)
        answer = _read(name=character.basemesh.name, rig="default")
        assert _counts(character.basemesh) == before
        assert answer["ready"] is True
        assert answer["definition_from"] == "catalogue"
        assert answer["rig_object_name"] is None
        assert answer["bone_count"] == len(answer["bones"]) == 163
        upperarm = next(bone for bone in answer["bones"] if bone["name"] == "upperarm01.L")
        assert upperarm["head"]["joint"] == "joint-l-shoulder"
        assert set(upperarm["head"]["position"]) == {"forward", "left", "up"}
        assert upperarm["head"]["position"]["left"] > 0.1, "the left arm is on the left"
        assert set(upperarm) == {"name", "parent", "head", "tail", "roll", "deform", "connect",
                                 "collections"}


def test_a_rig_added_from_the_catalogue_is_read_from_its_file():
    services = services_or_skip()
    with Character() as character:
        services["HumanService"].add_builtin_rig(character.basemesh, "game_engine",
                                                 import_weights=False)
        answer = _read(name=character.basemesh.name)
        assert answer["definition_from"] == "catalogue"
        assert answer["rig_identified_as"] == "game_engine"
        assert answer["definition_path"].endswith("rig.game_engine.json")


def test_an_authored_rig_is_read_off_its_armature():
    services_or_skip()
    with Character() as character:
        result("create_rig", {"name": character.basemesh.name, "bones": small_rig_table()})
        answer = _read(name=character.basemesh.name)
        assert answer["definition_from"] == "armature"
        assert answer["rig_identified_as"] == "unknown"
        assert [bone["name"] for bone in answer["bones"]] == \
            [bone["name"] for bone in small_rig_table()]


def test_compact_drops_positions_and_keys_at_their_default():
    services_or_skip()
    with Character() as character:
        full = _read(name=character.basemesh.name, rig="default")
        compact = _read(name=character.basemesh.name, rig="default", compact=True)
        assert compact["features_not_carried"] is None
        assert all("position" not in bone["head"] for bone in compact["bones"])
        assert all("deform" not in bone for bone in compact["bones"])
        assert len(str(compact["bones"])) < len(str(full["bones"])) / 2


def test_bone_names_narrow_and_an_unknown_one_is_refused():
    services_or_skip()
    with Character() as character:
        narrow = _read(name=character.basemesh.name, rig="default",
                       bone_names=["root", "spine05"])
        assert sorted(bone["name"] for bone in narrow["bones"]) == ["root", "spine05"]
        assert narrow["bone_count"] == 163
        refused = _read(name=character.basemesh.name, rig="default", bone_names=["rooot"])
        assert refused["blocked_by"] == "unknown_bone_names"
        assert refused["unknown_bone_names"] == ["rooot"]


def test_joints_are_every_joint_cube_of_the_body():
    services_or_skip()
    with Character() as character:
        answer = _read(name=character.basemesh.name, rig="default", include_joints=True)
        groups = [group.name for group in character.basemesh.vertex_groups
                  if "joint" in group.name]
        assert sorted(answer["joints"]) == sorted(groups)
        assert answer["joint_count"] == len(groups)


def test_the_refusals():
    services_or_skip()
    with Character() as character:
        assert _read(name=character.basemesh.name)["blocked_by"] == "not_rigged"
        assert _read(name=character.basemesh.name, rig="custom.no_such_rig")["blocked_by"] == \
            "unknown_identifier"
    assert _read(name="no such object")["blocked_by"] == "subject_not_found"


def test_what_a_rigify_meta_rig_carries_beyond_the_table_is_named():
    services_or_skip()
    with Character() as character:
        answer = _read(name=character.basemesh.name, rig="rigify.human_toes")
        if answer["blocked_by"] == "unknown_identifier":
            return
        assert answer["features_not_carried"], "a Rigify meta-rig's bones carry Rigify types"
        assert "rigify_ui" in answer["rig_features_not_carried"]
        heel = [bone for bone in answer["bones"]
                if bone["head"].get("expressible") is False
                or bone["tail"].get("expressible") is False]
        assert heel, "the heel markers use the XYZ strategy, which has no table form"
        assert answer["unexpressible_ends"] >= len(heel)
