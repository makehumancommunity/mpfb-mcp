"""
``symmetrize_targets`` against a real MPFB: the dry run, and then the same run.

**The most destructive command in the package**, and what is checked here is the
two properties that make it safe to offer at all:

- **A dry run and the real run report the same set of changes.** Asserted by
  doing both against the same starting state and comparing, which is only
  meaningful because everything is measured before anything is written. A
  command that planned as it went would pass a test that only looked at one run.
- **A dry run writes nothing.** Asserted against the mesh, not against the
  answer: ``changes`` is *populated* on a dry run, which is exactly the case
  where reading the answer would tell you nothing.

The asymmetry is built through ``set_targets``' own command rather than by
writing shape keys by hand, so what is symmetrized is a character a caller could
actually have produced - and so the two commands' assumptions about what a
category means are checked against each other on one character, which is what
``shared/modifier_reading.py`` exists for.
"""

import os

import bpy

from .._fixtures import Character as _Character
from .._fixtures import build_target_tree
from .._fixtures import dispatch
from .._fixtures import redirected_locations
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution

# The fixture's one sided category whose four target files are all on disk.
# `ears` is sided too and deliberately has only its left-hand files, which is a
# different test.
_SIDED = {"section": "arms", "category": "lowerarm-scale-depth-decr-incr"}


def _result(params=None):
    return _fixture_result("symmetrize_targets", params)


def _shapekey_names(basemesh):
    keys = basemesh.data.shape_keys
    if keys is None or keys.key_blocks is None:
        return []
    return [str(block.name) for block in keys.key_blocks]


def _make_asymmetric(character, value=0.4):
    """One sided category set on the left only, through set_targets itself."""
    envelope = dispatch("set_targets", {
        "name": character.basemesh.name,
        "modifiers": [dict(_SIDED, side="left", value=value)],
    })
    assert envelope["status"] == "ok", "the fixture change should have applied: {!r}".format(
        envelope)
    assert envelope["result"]["performed"] is True, envelope["result"]["message"]


def test_a_dry_run_reports_changes_and_writes_nothing():
    """commands.symmetrize_targets with dry_run on"""
    services = _services_or_skip()
    paths = build_target_tree(os.path.join(bpy.app.tempdir, "symmetrize-dry"))
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            _make_asymmetric(character)
            before = _shapekey_names(character.basemesh)

            result = _result({"name": character.basemesh.name,
                              "direction": "left_to_right", "dry_run": True})

        assert result["dry_run"] is True
        assert result["changes"], "the character is asymmetric, so something should be planned"
        assert result["performed"] is False, \
            "a dry run writes nothing, so performed must be false however full changed is"
        assert _shapekey_names(character.basemesh) == before, \
            "a dry run must not have touched the mesh"
        # Null rather than an empty list: which target files a write would touch
        # is only knowable by doing the write.
        assert result["changes"][0]["targets"] is None


def test_the_real_run_makes_exactly_the_changes_the_dry_run_named():
    """commands.symmetrize_targets, dry then real, from one starting state"""
    services = _services_or_skip()
    paths = build_target_tree(os.path.join(bpy.app.tempdir, "symmetrize-agree"))
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            _make_asymmetric(character)

            predicted = _result({"name": character.basemesh.name,
                                 "direction": "left_to_right", "dry_run": True})
            actual = _result({"name": character.basemesh.name,
                              "direction": "left_to_right"})

        predicted_categories = [(entry["section"], entry["category"])
                                for entry in predicted["changes"]]
        actual_categories = [(entry["section"], entry["category"])
                             for entry in actual["changes"]]
        assert predicted_categories == actual_categories, \
            "the dry run promised {!r} and the real run made {!r}".format(
                predicted_categories, actual_categories)
        assert actual["performed"] is True
        for predicted_entry, actual_entry in zip(predicted["changes"], actual["changes"]):
            assert abs(predicted_entry["destination_value_after"]
                       - actual_entry["destination_value_after"]) < 0.0001, \
                "the dry run's predicted value must be the one the real run produced"


def test_the_destination_side_ends_up_equal_to_the_source():
    """commands.symmetrize_targets really makes the character symmetric"""
    services = _services_or_skip()
    paths = build_target_tree(os.path.join(bpy.app.tempdir, "symmetrize-equal"))
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            _make_asymmetric(character, value=0.4)

            result = _result({"name": character.basemesh.name,
                              "direction": "left_to_right"})

            # Asked again, there is now nothing left to do - which is the
            # claim "symmetric" actually means.
            again = _result({"name": character.basemesh.name,
                             "direction": "left_to_right"})

        changed = [entry for entry in result["changes"]
                   if entry["category"] == _SIDED["category"]]
        assert changed, "the asymmetric category should have been changed: {!r}".format(
            result["message"])
        assert abs(changed[0]["source_value"] - 0.4) < 0.0001
        assert abs(changed[0]["destination_value_after"] - 0.4) < 0.0001

        assert not [entry for entry in again["changes"]
                    if entry["category"] == _SIDED["category"]], \
            "a second run should find that category already symmetric"
        assert any(entry["category"] == _SIDED["category"]
                   for entry in again["already_symmetric"])


def test_an_unsided_category_is_never_walked():
    """commands.symmetrize_targets leaves a category with no left/right alone

    The pairing comes from target.json's ``opposites`` table rather than from
    matching ``l-``/``r-`` name prefixes, so a category with
    ``has_left_and_right: false`` has no partner and must not appear at all.
    """
    services = _services_or_skip()
    paths = build_target_tree(os.path.join(bpy.app.tempdir, "symmetrize-unsided"))
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            result = _result({"name": character.basemesh.name,
                              "direction": "left_to_right", "dry_run": True})

        walked = set(entry["category"] for entry
                     in result["changes"] + result["already_symmetric"] + result["skipped"])
        assert "chin-triangle" not in walked, \
            "chin-triangle is unsided and must not be walked"
        assert "nose-scale-depth-decr-incr" not in walked, \
            "an unsided opposed category is still unsided"


def test_a_category_whose_file_is_missing_is_skipped_rather_than_fatal():
    """commands.symmetrize_targets over the fixture's half-present ears category

    Unlike set_targets, this command is asked to make a character symmetric
    rather than to apply a list, so one unreachable target is a fact about that
    category and not a reason to leave the rest of the body asymmetric.
    """
    services = _services_or_skip()
    paths = build_target_tree(os.path.join(bpy.app.tempdir, "symmetrize-missing"))
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            # `ears` has left-hand files only, so copying left to right needs a
            # file that is not there.
            dispatch("set_targets", {
                "name": character.basemesh.name,
                "modifiers": [{"section": "ears", "category": "ear-lobe-decr-incr",
                               "side": "left", "value": 0.5}],
            })
            envelope = dispatch("symmetrize_targets", {
                "name": character.basemesh.name, "direction": "left_to_right",
                "section": "ears"})

        assert envelope["status"] == "ok", \
            "a missing file must not become a command_failed: {!r}".format(envelope)
        result = envelope["result"]
        assert result["skipped"], "the ears category should have been skipped"
        assert result["skipped"][0]["reason"] == "target_file_not_found"


def test_the_direction_is_required_by_the_contract():
    """commands.symmetrize_targets with no direction at all

    The package's only required argument, and this is the half of the rule that
    lives on the add-on: a listening socket is reachable by anything on this
    machine, not only by a tool that already checked.
    """
    _services_or_skip()
    envelope = dispatch("symmetrize_targets", {})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "direction" in envelope["message"]


def test_an_unknown_direction_is_refused_by_the_contract():
    """commands.symmetrize_targets with a direction that is not one of the two"""
    _services_or_skip()
    envelope = dispatch("symmetrize_targets", {"direction": "leftward"})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "left_to_right" in envelope["message"]


def test_an_unknown_section_is_an_answer_rather_than_an_error():
    """commands.symmetrize_targets limited to a section that does not exist"""
    _services_or_skip()
    with _Character() as character:
        envelope = dispatch("symmetrize_targets", {
            "name": character.basemesh.name, "direction": "left_to_right",
            "section": "no-such-section"})

        assert envelope["status"] == "ok"
        result = envelope["result"]
        assert result["ready"] is False
        assert result["blocked_by"] == "unknown_section"
        assert result["known_sections"], "the refusal should say what could have been asked for"
        assert result["performed"] is False


def test_the_callers_selection_and_active_object_are_restored():
    """commands.symmetrize_targets puts back what it borrowed"""
    services = _services_or_skip()
    paths = build_target_tree(os.path.join(bpy.app.tempdir, "symmetrize-selection"))
    with _Character() as character:
        bystander = bpy.data.objects.new("SymmetrizeBystander",
                                         bpy.data.meshes.new("SymmetrizeBystanderMesh"))
        bpy.context.scene.collection.objects.link(bystander)

        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            _make_asymmetric(character)
            services["ObjectService"].activate_blender_object(bystander)
            character.basemesh.select_set(False)

            _result({"name": character.basemesh.name, "direction": "left_to_right"})

        assert bpy.context.view_layer.objects.active is bystander
        assert character.basemesh.select_get() is False


def test_mpfb_being_unavailable_refuses_rather_than_half_mirroring():
    """commands.symmetrize_targets against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("symmetrize_targets", {"direction": "left_to_right"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
