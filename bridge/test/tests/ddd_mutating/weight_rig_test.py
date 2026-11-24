"""
``weight_rig`` against a real MPFB: four methods, the fill, the clean, and what each leaves behind.

The answers that are known in advance are what is asserted:

- **automatic** weights every body vertex before the fill, leaves no object, mesh or armature
  behind, weights the neutral body - two characters modelled differently get the same groups
  (FR 061) - and rests on a finding this module also holds: with the joint cubes in the mesh,
  Blender's heat solve fails for every bone, because MPFB fits a bone end exactly at a cube's
  centre. If Blender ever solves that case, ``test_the_joint_cubes_break_the_heat_solve`` fails
  and the copy's exclusion can be revisited.
- **the helper rules** bind the eyes rigidly, to the head on a rig with no eye bone, and
  ``helper_bones`` overrides the choice.
- **the clean** caps influences, normalises, lists a group it rescaled that the call did not
  otherwise write, and never touches a mask.
- **transfer** from ``default_no_toes`` onto a reduced rig whose matches are known: two chains,
  an exact hand that takes the fingers by ``ancestor``, and a bone that matches
  nothing, with its nearest miss.
- **mirror** of a deliberately one-sided weighting copies it exactly through ``hm08.mirror``.
"""

import bpy

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import dispatch
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


def _counts():
    return (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures),
            len(bpy.data.actions))


def test_automatic_weights_every_body_vertex_and_leaves_nothing_behind():
    services_or_skip()
    with Character() as character:
        _built(character)
        counts = _counts()
        answer = _weight(name=character.basemesh.name, method="automatic")
        assert answer["performed"] is True and answer["weighted"] is True
        assert answer["weighted_on"] == "neutral_base_mesh"
        assert _counts() == counts
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
        classes = bridge_module("shared.rig_weights").layout(services, character.basemesh).classes
        # pylint: disable=protected-access
        with_cubes = module._heat_copy(character.basemesh, armature, positions,
                                       everything_is_body)
        without = module._heat_copy(character.basemesh, armature, positions, classes,
                                    kept=("body", "helper"))
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
        # Every method ends by cleaning (FR 061), and a vertex whose one weight is 0.75 is
        # normalised to 1.0, on both sides alike.
        expected = {to_index: 1.0 for _from, to_index in pairs[:200]}
        assert {index: round(weight, 4) for index, weight in mirrored.items()} == expected
        assert answer["groups_rescaled"] == [], "the source side is the call's own group"
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
        # The clean renormalises every vertex the new arm group shares, so another group can
        # change; when it does, it is named (FR 061), and it changes only in its weights.
        head_after = _group(basemesh, "t_head")
        assert (head_after != head_before) == ("t_head" in answer["groups_rescaled"])
        assert set(head_after) <= set(head_before)


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


def _deform_groups(basemesh, names):
    return {name: {index: round(weight, 5) for index, weight in _group(basemesh, name).items()}
            for name in names}


def test_two_differently_modelled_characters_get_the_same_groups():
    services_or_skip()
    names = [row["name"] for row in small_rig_table()]
    other = {"gender": 1.0, "age": 0.9, "muscle": 0.5, "weight": 0.9, "proportions": 0.5,
             "height": 0.1, "cupsize": 0.5, "firmness": 0.5,
             "race": {"asian": 1.0 / 3.0, "caucasian": 1.0 / 3.0, "african": 1.0 / 3.0}}
    with Character() as first, Character(macro_detail_dict=other) as second:
        _built(first)
        _built(second)
        _weight(name=first.basemesh.name, method="automatic")
        _weight(name=second.basemesh.name, method="automatic")
        one = _deform_groups(first.basemesh, names)
        two = _deform_groups(second.basemesh, names)
        # Not bit for bit: MPFB moves each body's Basis to put the feet on the ground, 2.4 mm
        # apart on this pair, and the heat solve on a translated mesh differs by float noise,
        # 1.3e-6 at most when this was written.
        assert {name: set(entries) for name, entries in one.items()} == \
            {name: set(entries) for name, entries in two.items()}
        assert max(abs(one[name][index] - two[name][index])
                   for name in names for index in one[name]) < 1e-4


def test_the_eyes_are_rigid_and_helper_bones_overrides_the_choice():
    services_or_skip()
    with Character() as character:
        _built(character)
        answer = _weight(name=character.basemesh.name, method="automatic")
        helpers = {row["group"]: row for row in answer["helpers"]}
        eye = helpers["helper-l-eye"]
        assert (eye["rule"], eye["bone"], eye["chosen_by"]) == \
            ("rigid", "t_head", "nearest_dominant"), eye
        assert helpers["helper-skirt"]["rule"] == "nearest"
        assert answer["helpers_not_in_table"] == []
        chosen = _weight(name=character.basemesh.name, method="automatic",
                         helper_bones={"helper-l-eye": "t_chest"})
        eye = {row["group"]: row for row in chosen["helpers"]}["helper-l-eye"]
        assert (eye["bone"], eye["chosen_by"]) == ("t_chest", "helper_bones")
        members = bridge_module("shared.rig_weights").layout(
            services_or_skip(), character.basemesh).helpers["helper-l-eye"]
        chest = _group(character.basemesh, "t_chest")
        assert all(round(chest.get(index, 0.0), 4) == 1.0 for index in members)


def test_the_clean_caps_normalises_lists_what_it_rescaled_and_leaves_masks_alone():
    services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        _built(character)
        _weight(name=basemesh.name, method="automatic")
        mask = basemesh.vertex_groups.new(name="mhmask-fr061")
        mask.add(list(range(0, 400)), 0.3, "REPLACE")
        head = basemesh.vertex_groups["t_head"]
        vertex = next(iter(_group(basemesh, "t_head")))
        head.add([vertex], 1.0, "ADD")
        neck = basemesh.vertex_groups["t_chest"]
        neck.add([vertex], 0.5, "REPLACE")
        answer = _weight(name=basemesh.name, method="automatic", bone_names=["t_arm.L"])
        assert "t_head" in answer["groups_rescaled"] or "t_chest" in answer["groups_rescaled"]
        assert "t_arm.L" not in answer["groups_rescaled"]
        cleaned = _weight(name=basemesh.name, method="clean", max_influences=2)
        assert max(int(count) for count in cleaned["clean"]["histogram_after"]) <= 2
        assert cleaned["clean"]["vertices_trimmed"] > 0
        totals = {}
        for name in [row["name"] for row in small_rig_table()]:
            for index, weight in _group(basemesh, name).items():
                totals[index] = totals.get(index, 0.0) + weight
        assert all(abs(total - 1.0) < 0.001 for total in totals.values())
        assert {round(weight, 4) for weight in _group(basemesh, "mhmask-fr061").values()} == {0.3}
        assert len(_group(basemesh, "mhmask-fr061")) == 400


def test_the_clean_and_its_own_refusals():
    services_or_skip()
    with Character() as character:
        _built(character)
        name = character.basemesh.name
        assert _weight(name=name, method="automatic",
                       helper_bones={"helper-nothing": "t_head"})["blocked_by"] == \
            "unknown_helper_groups"
        assert _weight(name=name, method="automatic",
                       helper_bones={"helper-l-eye": "nope"})["blocked_by"] == "unknown_bone_names"
        envelope = dispatch("weight_rig", {"name": name, "method": "clean",
                                           "bone_names": ["t_head"]})
        assert envelope["result"]["blocked_by"] == "invalid_shape", envelope
