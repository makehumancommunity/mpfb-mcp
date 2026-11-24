"""
``weight_rig`` against a real MPFB: three methods, the fill, and what each leaves behind.

The answers that are known in advance are what is asserted:

- **automatic** weights every body vertex before the fill, leaves no object or mesh behind, and
  rests on a finding this module also holds: with the joint cubes in the mesh, Blender's heat
  solve fails for every bone, because MPFB fits a bone end exactly at a cube's centre. If
  Blender ever solves that case, ``test_the_joint_cubes_break_the_heat_solve`` fails and the
  copy's exclusion can be revisited.
- **transfer** from ``default_no_toes`` onto a reduced rig whose matches are known: two chains,
  an exact hand that takes the fingers by ``ancestor``, and a bone that matches
  nothing, with its nearest miss.
- **mirror** of a deliberately one-sided weighting copies it exactly through ``hm08.mirror``.
"""

import bpy

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table


def _weight(**params):
    return result("weight_rig", params)


def _built(character, table=None):
    answer = result("create_rig", {"name": character.basemesh.name,
                                   "bones": table if table is not None else small_rig_table()})
    assert answer["created"] is True, answer["message"]
    return bpy.data.objects[answer["rig_object_name"]]


def _group(basemesh, name):
    group = basemesh.vertex_groups.get(name)
    if group is None:
        return {}
    return {vertex.index: element.weight for vertex in basemesh.data.vertices
            for element in vertex.groups if element.group == group.index and element.weight > 0}


def test_automatic_weights_every_body_vertex_and_leaves_nothing_behind():
    services_or_skip()
    with Character() as character:
        _built(character)
        counts = (len(bpy.data.objects), len(bpy.data.meshes))
        answer = _weight(name=character.basemesh.name, method="automatic")
        assert answer["performed"] is True and answer["weighted"] is True
        assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts
        assert answer["unweighted"]["before_fill"]["body"] == 0, answer["message"]
        assert answer["unweighted"]["after_fill"] == {"body": 0, "helper": 0, "joint_cube": 0}
        assert answer["bones_without_weights"] == []
        assert all(row["vertex_count"] > 0 for row in answer["bones"])


def test_the_joint_cubes_break_the_heat_solve():
    services = services_or_skip()
    module = bridge_module("commands.weight_rig")
    with Character() as character:
        armature = _built(character)
        positions = bridge_module("shared.rig_definition").fit_definition(
            services, character.basemesh, {"bones": {}, "version": 110}).position_info["vertices"]
        everything_is_body = ["body"] * len(positions)
        # pylint: disable=protected-access
        with_cubes = module._heat_copy(character.basemesh, armature, positions,
                                       everything_is_body)
        without = module._heat_copy(character.basemesh, armature, positions,
                                    module._vertex_classes(character.basemesh))
        assert sum(len(entries) for entries in with_cubes.values()) == 0
        assert sum(len(entries) for entries in without.values()) > 10000


def test_exclude_bones_are_set_non_deforming():
    services_or_skip()
    with Character() as character:
        armature = _built(character)
        answer = _weight(name=character.basemesh.name, method="automatic",
                         exclude_bones=["t_hips"])
        assert armature.data.bones["t_hips"].use_deform is False
        assert answer["set_non_deforming"] == ["t_hips"]
        assert "t_hips" not in [row["name"] for row in answer["bones"]]


def test_a_bone_on_the_ground_is_named():
    services_or_skip()
    with Character() as character:
        table = small_rig_table()
        table.insert(0, {"name": "t_root", "parent": "", "head": {"joint": "joint-ground"},
                         "tail": {"joint": "joint-pelvis"}})
        table[1]["parent"] = "t_root"
        _built(character, table)
        answer = _weight(name=character.basemesh.name, method="automatic")
        assert answer["deforming_bones_on_ground"] == ["t_root"]


def _reduced_default_table():
    """Bones whose matches against default_no_toes are known."""
    return [
        {"name": "pelvis_t", "parent": "", "head": {"joint": "joint-pelvis"},
         "tail": {"joint": "joint-spine-3"}},
        {"name": "upperarm_t.L", "parent": "pelvis_t", "head": {"joint": "joint-l-shoulder"},
         "tail": {"joint": "joint-l-elbow"}},
        {"name": "hand_t.L", "parent": "upperarm_t.L", "head": {"joint": "joint-l-hand"},
         "tail": {"joint": "joint-l-hand-3"}},
        {"name": "nothing_t", "parent": "pelvis_t", "head": {"joint": "joint-l-eye"},
         "tail": {"joint": "joint-r-eye"}},
    ]


def test_transfer_matches_exact_chain_and_ancestor_and_names_a_miss():
    services_or_skip()
    with Character() as character:
        _built(character, _reduced_default_table())
        answer = _weight(name=character.basemesh.name, method="transfer",
                         from_rig="default_no_toes", fill_unweighted=False)
        rows = {row["name"]: row for row in answer["bones"]}
        assert rows["nothing_t"]["matched_by"] == "none"
        assert rows["nothing_t"]["nearest_miss"]["bone"]
        assert rows["upperarm_t.L"]["matched_by"] == "chain"
        assert [source["bone"] for source in rows["upperarm_t.L"]["sources"]
                if source["matched_by"] == "chain"] == ["upperarm01.L", "upperarm02.L"]
        assert rows["pelvis_t"]["matched_by"] == "chain"
        assert [source["bone"] for source in rows["pelvis_t"]["sources"]
                if source["matched_by"] == "chain"] == ["spine05", "spine04"]
        assert rows["hand_t.L"]["matched_by"] == "exact"
        hand_sources = {source["bone"]: source["matched_by"]
                        for source in rows["hand_t.L"]["sources"]}
        assert hand_sources.get("wrist.L") == "exact"
        assert hand_sources.get("finger2-3.L") == "ancestor", \
            "a finger nothing covers gives its weights to the hand"
        assert answer["weights_from"] == "default"


def test_mirror_copies_a_one_sided_weighting_exactly():
    services = services_or_skip()
    module = bridge_module("commands.weight_rig")
    with Character() as character:
        basemesh = character.basemesh
        _built(character)
        pairs = module._mirror_pairs(services, "left_to_right")  # pylint: disable=protected-access
        sources = [from_index for from_index, _to in pairs[:200]]
        group = basemesh.vertex_groups.new(name="t_arm.L")
        for index in sources:
            group.add([index], 0.75, "REPLACE")
        answer = _weight(name=basemesh.name, method="mirror", direction="left_to_right")
        assert answer["bones_without_partner"] == []
        mirrored = _group(basemesh, "t_arm.R")
        expected = {to_index: 0.75 for _from, to_index in pairs[:200]}
        assert {index: round(weight, 4) for index, weight in mirrored.items()} == expected
        assert set(_group(basemesh, "t_arm.L")) == set(sources), "the source side is untouched"


def test_bone_names_limit_the_pass_and_a_replaced_group_is_listed():
    services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        _built(character)
        _weight(name=basemesh.name, method="automatic")
        head_before = _group(basemesh, "t_head")
        answer = _weight(name=basemesh.name, method="automatic", bone_names=["t_arm.L"])
        assert [row["name"] for row in answer["bones"]] == ["t_arm.L"]
        assert answer["groups_replaced"] == ["t_arm.L"]
        assert _group(basemesh, "t_head") == head_before


def test_the_refusals():
    services = services_or_skip()
    with Character() as character:
        name = character.basemesh.name
        assert _weight(name=name, method="automatic")["blocked_by"] == "not_rigged"
        armature = _built(character)
        assert _weight(name=name, method="automatic", bone_names=["nope"])["blocked_by"] == \
            "unknown_bone_names"
        assert _weight(name=name, method="transfer", from_rig="custom.nope")["blocked_by"] == \
            "unknown_identifier"
        armature.pose.bones["t_arm.L"].location = (0.0, 0.1, 0.0)
        assert _weight(name=name, method="automatic")["blocked_by"] == "rig_not_at_rest"
    with Character() as character:
        services["HumanService"].add_builtin_rig(character.basemesh, "game_engine",
                                                 import_weights=False)
        assert _weight(name=character.basemesh.name, method="automatic")["blocked_by"] == \
            "rig_not_authored"
