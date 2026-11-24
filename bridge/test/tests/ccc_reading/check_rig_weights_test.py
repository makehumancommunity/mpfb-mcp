"""
``check_rig_weights`` against a real MPFB: read-only, bend included, and catching what it is for.

- **It changes nothing.** The ``bpy.data`` counts, every deform group, the pose and every
  modifier's ``show_viewport`` are the same after a call with every section as before it.
- **A bad weighting shows.** The right thigh's vertices put on the left arm make the arm's
  ``far_vertices`` and the shoulder's ``stray`` count them, without a render.
- **An eye on its eyelid is not rigid**, on ``default`` with half the eye moved to
  ``orbicularis03.L``.
- **A rig with no elbow bone** is ``not_tested`` there, and the refusals.
"""

import bpy

from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table

_ALL = ["coverage", "influences", "bones", "helpers", "symmetry", "bend"]


def _authored(character):
    answer = result("create_rig", {"name": character.basemesh.name, "bones": small_rig_table()})
    assert answer["created"] is True, answer["message"]
    result("weight_rig", {"name": character.basemesh.name, "method": "automatic"})
    return bpy.data.objects[answer["rig_object_name"]]


def _check(**params):
    return result("check_rig_weights", params)


def _state(basemesh, armature):
    groups = {}
    for vertex in basemesh.data.vertices:
        for element in vertex.groups:
            groups[(vertex.index, element.group)] = round(element.weight, 6)
    pose = {pose_bone.name: (tuple(pose_bone.location), tuple(pose_bone.rotation_quaternion),
                             tuple(pose_bone.rotation_euler), tuple(pose_bone.scale))
            for pose_bone in armature.pose.bones}
    return dict(counts=(len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures)),
                groups=groups, pose=pose,
                modifiers=[(modifier.name, modifier.show_viewport)
                           for modifier in basemesh.modifiers],
                pose_position=armature.data.pose_position, mode=bpy.context.mode)


def test_the_tool_is_read_only_bend_included():
    services_or_skip()
    with Character() as character:
        armature = _authored(character)
        before = _state(character.basemesh, armature)
        answer = _check(name=character.basemesh.name, sections=_ALL)
        assert answer["ready"] is True, answer["message"]
        assert answer["bend"]["tested"] > 0
        assert _state(character.basemesh, armature) == before


def test_a_thigh_put_on_the_arm_shows_as_far_and_stray():
    services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        armature = _authored(character)
        clean = _check(name=basemesh.name, sections=["bones", "bend"])
        thigh = basemesh.vertex_groups["t_thigh.R"]
        arm = basemesh.vertex_groups["t_arm.L"]
        members = [vertex.index for vertex in basemesh.data.vertices
                   for element in vertex.groups
                   if element.group == thigh.index and element.weight > 0.5]
        thigh.remove(members)
        arm.add(members, 1.0, "REPLACE")
        bad = _check(name=basemesh.name, sections=["bones", "bend"])

        def far(answer):
            return {row["name"]: row["far_vertices"] for row in answer["bones"]["rows"]}["t_arm.L"]

        def stray(answer):
            return {row["movement"]: row for row in answer["bend"]["movements"]}[
                "shoulder_abduct"]["stray"]

        assert far(bad) >= len(members) * 0.9 > far(clean), (far(clean), far(bad), len(members))
        assert stray(bad) > stray(clean) + len(members) * 0.5, (stray(clean), stray(bad))
        assert armature.data.bones["t_arm.L"].use_deform


def test_an_eye_on_its_eyelid_is_not_rigid():
    services = services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        rigged_character(services, character, "default")
        assert {row["group"]: row["rigid"] for row in _check(
            name=basemesh.name, sections=["helpers"])["helpers"]["rows"]}["helper-l-eye"] is True
        eye_group = basemesh.vertex_groups["helper-l-eye"]
        members = [vertex.index for vertex in basemesh.data.vertices
                   for element in vertex.groups if element.group == eye_group.index]
        half = members[:len(members) // 2]
        basemesh.vertex_groups["eye.L"].remove(half)
        basemesh.vertex_groups["orbicularis03.L"].add(half, 1.0, "REPLACE")
        row = {row["group"]: row for row in _check(
            name=basemesh.name, sections=["helpers"])["helpers"]["rows"]}["helper-l-eye"]
        assert row["rigid"] is False and row["dominant_share"] < 0.99, row


def test_a_rig_with_no_elbow_bone_is_not_tested_there():
    services_or_skip()
    with Character() as character:
        _authored(character)
        answer = _check(name=character.basemesh.name, sections=["bend"])
        rows = {row["movement"]: row for row in answer["bend"]["movements"]}
        assert rows["elbow_flex"]["tested"] is False
        assert rows["elbow_flex"]["not_tested"] == "no_bone_on_joint"
        assert rows["shoulder_abduct"]["tested"] is True
        assert rows["shoulder_abduct"]["bone"] == "t_arm.L"
        assert answer["coverage"] is None, "an unnamed section is null"


def test_the_refusals():
    services_or_skip()
    with Character() as character:
        name = character.basemesh.name
        assert _check(name=name)["blocked_by"] == "not_rigged"
        armature = _authored(character)
        envelope = dispatch("check_rig_weights", {"name": name, "sections": ["weights"]})
        assert envelope["result"]["blocked_by"] == "unknown_section", envelope
        armature.pose.bones["t_arm.L"].location = (0.0, 0.1, 0.0)
        assert _check(name=name, sections=["bend"])["blocked_by"] == "rig_not_at_rest"
        assert _check(name=name)["ready"] is True, "only the bend needs the rig at rest"
