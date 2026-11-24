"""
``shared/rig_weights.py`` against MPFB's own shipped weights, where the answers are known.

Every claim the request made by reading the files is asserted here on the files as MPFB loads them
onto a body (FR 061):

- ``default`` leaves no vertex unweighted, has at most eight influences, is normalised, binds the
  eyes and teeth rigidly and is close to symmetric;
- ``mixamo`` is unnormalised on 9,858 vertices;
- on ``default``'s own anchors, the rigid rule picks ``eye.L`` and ``jaw`` by name and ``head``
  for the upper teeth by the weight of the nearest skin, which is why the name tie-break exists:
  ``eye.L`` and two eyelid bones all have their head on ``joint-l-eye``;
- ``clean`` on rows with a known answer.
"""

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import rigged_character
from .._fixtures import services_or_skip


def _module():
    return bridge_module("shared.rig_weights")


def _reading(services, basemesh, armature):
    module = _module()
    deforming = module.deforming_bones(armature)
    weights = module.read_weights(basemesh, set(deforming))
    return (module, deforming, weights, module.by_vertex(weights),
            module.layout(services, basemesh))


def test_default_is_fully_weighted_normalised_rigid_and_close_to_symmetric():
    services = services_or_skip()
    with Character() as character:
        armature = rigged_character(services, character, "default")
        module, deforming, weights, rows, layout = _reading(services, character.basemesh, armature)
        vertex_count = len(character.basemesh.data.vertices)
        coverage = module.coverage(layout, weights, deforming, character.basemesh,
                                   armature.data.bones.keys())
        assert coverage["unweighted"]["total"] == 0
        assert coverage["orphan_groups"] == []
        influences = module.influences(rows, vertex_count)
        assert influences["max_influences"] == 8
        assert influences["unnormalised"] == 0
        helpers = {row["group"]: row for row in module.helper_rows(layout, rows)}
        assert (helpers["helper-l-eye"]["dominant_bone"], helpers["helper-l-eye"]["rigid"]) == \
            ("eye.L", True)
        assert (helpers["helper-lower-teeth"]["dominant_bone"],
                helpers["helper-lower-teeth"]["rigid"]) == ("jaw", True)
        assert helpers["helper-upper-teeth"]["rigid"] is True
        assert helpers["helper-skirt"]["rigid"] is False
        symmetry = module.symmetry(weights, deforming, module.mirror_pairs(services, "l"))
        assert symmetry["bones_without_partner"] == []
        assert all(row["mean_difference"] < 0.05 for row in symmetry["worst"]), symmetry["worst"]


def test_mixamo_is_unnormalised_where_the_file_is():
    services = services_or_skip()
    with Character() as character:
        armature = rigged_character(services, character, "mixamo")
        module, _deforming, _weights, rows, _layout = _reading(services, character.basemesh,
                                                               armature)
        influences = module.influences(rows, len(character.basemesh.data.vertices))
        assert influences["unnormalised"] == 9858, influences["unnormalised"]


def test_the_rigid_rule_on_defaults_own_anchors():
    services = services_or_skip()
    rig_definition = bridge_module("shared.rig_definition")
    with Character() as character:
        basemesh = character.basemesh
        armature = rigged_character(services, character, "default")
        module, deforming, _weights, rows, layout = _reading(services, basemesh, armature)
        fit = rig_definition.fit_definition(services, basemesh, {"bones": {}, "version": 110})
        space = rig_definition.Space(basemesh, armature)
        anchors, anchors_from = rig_definition.head_joints(services, armature, fit, space)
        assert anchors_from == "catalogue"
        assert sorted(name for name in deforming if anchors.get(name) == "joint-l-eye") == \
            ["eye.L", "orbicularis03.L", "orbicularis04.L"]
        for index in layout.helper_of:
            rows.pop(index, None)
        segments = {name: (space.armature_to_local(armature, armature.data.bones[name].head_local),
                           space.armature_to_local(armature, armature.data.bones[name].tail_local))
                    for name in deforming}
        _rows, report = module.fill(layout, rows, fit.position_info["vertices"], deforming,
                                    anchors, segments)
        chosen = {row["group"]: row for row in report["helpers"]}
        assert (chosen["helper-l-eye"]["bone"], chosen["helper-l-eye"]["chosen_by"]) == \
            ("eye.L", "anchor_name")
        assert set(chosen["helper-l-eye"]["candidates"]) == {"orbicularis03.L", "orbicularis04.L"}
        assert (chosen["helper-lower-teeth"]["bone"],
                chosen["helper-lower-teeth"]["chosen_by"]) == ("jaw", "anchor_name")
        assert (chosen["helper-upper-teeth"]["bone"],
                chosen["helper-upper-teeth"]["chosen_by"]) == ("head", "nearest_dominant")
        assert chosen["helper-tongue"]["rule"] == "interior_chain"
        assert all(name.startswith("tongue") for name in chosen["helper-tongue"]["bones"]), \
            chosen["helper-tongue"]
        assert chosen["helper-skirt"]["rule"] == "nearest"
        assert module.unweighted_counts(layout, _rows) == {"body": 0, "helper": 0,
                                                            "joint_cube": 0}


def test_clean_on_rows_with_a_known_answer():
    services_or_skip()
    module = _module()
    rows = {
        0: {"a": 0.6, "b": 0.3, "c": 0.00005},
        1: {"a": 0.5, "b": 0.5},
        2: {"a": 0.4, "b": 0.3, "c": 0.2, "d": 0.1},
        3: {"a": 0.00001},
    }
    cleaned, report = module.clean(rows, 0.0001, 2)
    assert {name: round(weight, 6) for name, weight in cleaned[0].items()} == \
        {"a": round(0.6 / 0.9, 6), "b": round(0.3 / 0.9, 6)}
    assert cleaned[1] == {"a": 0.5, "b": 0.5}
    assert {name: round(weight, 6) for name, weight in cleaned[2].items()} == \
        {"a": round(0.4 / 0.7, 6), "b": round(0.3 / 0.7, 6)}
    assert cleaned[3] == {"a": 1.0}, "the clean never unweights a vertex"
    assert report["vertices_trimmed"] == 2, "a lone weight below min_weight is kept, not trimmed"
    assert report["max_weight_removed"] == 0.2
    assert report["vertices_normalised"] == 3
    assert report["groups_changed"] == ["a", "b", "c", "d"]
    assert rows[0]["c"] == 0.00005, "the rows given are not changed"
