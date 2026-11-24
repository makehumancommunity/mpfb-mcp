"""
``create_rig`` against a real MPFB: MPFB fits the bones, and every refusal builds nothing.

What is asked of a real install: a table becomes an armature MPFB fitted, parented the way
``add_custom_rig()`` parents one, with each end's strategy saved on the bone; a turned body
gives its turn to the rig; ``deform: false`` reaches the bone; every refusal leaves the file as
it was; and ``replace`` keeps exactly the groups whose bones did not change.
"""

import math

import bpy

from .._fixtures import Character
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table


def _create(**params):
    return result("create_rig", params)


def _object_count():
    return (len(bpy.data.objects), len(bpy.data.armatures))


def test_a_table_is_built_onto_the_character_and_parented():
    services = services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        answer = _create(name=basemesh.name, bones=small_rig_table())
        assert answer["performed"] is True and answer["created"] is True, answer["message"]
        armature = bpy.data.objects[answer["rig_object_name"]]
        assert armature.name == basemesh.name + ".rig"
        assert basemesh.parent is armature
        assert any(modifier.type == "ARMATURE" and modifier.object is armature
                   for modifier in basemesh.modifiers)
        assert services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
            basemesh, "Skeleton") is armature
        assert len(armature.data.bones) == len(small_rig_table())
        assert answer["next_with"] == {"mpfb_weight_rig": {"name": armature.name,
                                                           "method": "automatic"}}
        elbow = armature.data.bones["t_arm.L"].tail_local
        row = next(bone for bone in answer["bones"] if bone["name"] == "t_arm.L")
        assert row["tail"]["joint"] == "joint-l-elbow"
        assert abs(row["tail"]["position"]["up"] - elbow[2]) < 0.002


def test_deform_false_reaches_the_bone():
    services_or_skip()
    with Character() as character:
        table = small_rig_table()
        table[0]["deform"] = False
        answer = _create(name=character.basemesh.name, bones=table)
        armature = bpy.data.objects[answer["rig_object_name"]]
        assert armature.data.bones["t_hips"].use_deform is False
        assert answer["not_deforming"] == ["t_hips"]


def test_a_turned_body_gives_its_turn_to_the_rig():
    services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        basemesh.rotation_euler = (0.0, 0.0, math.radians(90.0))
        basemesh.location = (2.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        answer = _create(name=basemesh.name, bones=small_rig_table())
        armature = bpy.data.objects[answer["rig_object_name"]]
        assert answer["basemesh_rotation_moved_to_rig"] is True
        assert abs(armature.matrix_world.to_euler().z - math.radians(90.0)) < 1e-4
        assert tuple(round(value, 4) for value in armature.location) == (2.0, 0.0, 0.0)
        # The arm is still on the character's left, in its own frame.
        row = next(bone for bone in answer["bones"] if bone["name"] == "t_arm.L")
        assert row["tail"]["position"]["left"] > 0.1


def test_every_refusal_builds_nothing():
    services = services_or_skip()
    with Character() as character:
        name = character.basemesh.name
        before = _object_count()
        table = small_rig_table()
        table[0]["head"] = {"joint": "joint-nowhere"}
        failed = _create(name=name, bones=table)
        assert failed["blocked_by"] == "resolution_failed"
        assert failed["resolution_errors"][0]["error"] == "unknown_joint"
        assert _object_count() == before

        bad = _create(name=name, bones=[{"name": "x", "head": {}, "tail": {}}])
        assert bad["blocked_by"] == "invalid_table"
        assert _object_count() == before

        services["HumanService"].add_builtin_rig(character.basemesh, "game_engine",
                                                 import_weights=False)
        rigged = _object_count()
        assert _create(name=name, bones=small_rig_table())["blocked_by"] == "already_rigged"
        assert _create(name=name, bones=small_rig_table(), replace=True)["blocked_by"] == \
            "rig_not_authored"
        assert _object_count() == rigged


def test_a_rebuild_keeps_the_groups_of_unchanged_bones_and_drops_the_rest():
    services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        first = _create(name=basemesh.name, bones=small_rig_table())
        for row in small_rig_table():
            group = basemesh.vertex_groups.new(name=row["name"])
            group.add([0], 1.0, "REPLACE")
        table = small_rig_table()
        table[3]["tail"] = {"joint": "joint-l-hand"}
        second = _create(name=basemesh.name, bones=table, replace=True)
        assert second["replaced"] is True
        assert second["replaced_rig_object_name"] == first["rig_object_name"]
        assert second["weights_dropped"] == ["t_arm.L"]
        assert "t_arm.R" in second["weights_kept"]
        assert "t_arm.L" not in basemesh.vertex_groups
        assert "t_arm.R" in basemesh.vertex_groups
        armatures = [blender_object for blender_object in bpy.data.objects
                     if blender_object.type == "ARMATURE"]
        assert len(armatures) == 1, "the old rig is gone"


def test_a_position_snaps_or_stays_and_the_answer_says_which():
    services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        joints = result("get_rig_definition", {"name": basemesh.name, "rig": "default",
                                               "include_joints": True})["joints"]
        near = dict(joints["joint-l-elbow"])
        near["up"] += 0.003
        table = small_rig_table()
        table[3]["tail"] = {"position": near}
        table[4]["tail"] = {"position": dict(joints["joint-r-elbow"]), "snap": False}
        answer = _create(name=basemesh.name, bones=table)
        assert answer["snapped_to"]["t_arm.L"]["tail"]["joint"] == "joint-l-elbow"
        assert answer["ends_not_following_body"] == ["t_arm.R.tail"]
