"""
``set_targets`` against a real MPFB: the all-or-nothing batch, and the write order.

Two claims live here and nowhere else, and both are about what MPFB does rather
than about what this command intends:

- **A batch with one bad entry applies none of it.** Asserted by counting the
  shape keys on the mesh before and after, not by reading ``applied``: a command
  that reported an empty ``applied`` while having written half the batch would
  pass a weaker test and would be exactly the defect the two-phase split exists
  to prevent.
- **A target that is not on the mesh is loaded rather than silently ignored.**
  ``TargetService.set_target_value()`` on an absent shape key walks the key
  blocks, finds no match and does nothing - it neither loads nor raises - so the
  presence-check-then-load path is the only thing standing between a caller and
  a call that succeeds and changes nothing.

**The fixture target tree is MPFB's own**, redirected through
``LocationService``, because this command's whole resolution phase is a question
about which files exist where. What it must *not* depend on is which target
packs the developer happens to have installed.
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


def _result(params=None):
    return _fixture_result("set_targets", params)


def _shapekey_names(basemesh):
    keys = basemesh.data.shape_keys
    if keys is None or keys.key_blocks is None:
        return []
    return [str(block.name) for block in keys.key_blocks]


def _fixture_tree(root):
    """MPFB pointed at a target tree this test built, and put back afterwards."""
    paths = build_target_tree(root)
    return paths


def test_a_category_modifier_is_resolved_and_written():
    """commands.set_targets with one modifier entry over a fixture target tree"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-targets-simple")
    paths = _fixture_tree(root)
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            result = _result({
                "name": character.basemesh.name,
                "modifiers": [{"section": "nose",
                               "category": "nose-scale-depth-decr-incr",
                               "value": 0.4}],
            })

        assert result["performed"] is True, result["message"]
        assert result["resolution_errors"] == []
        assert len(result["applied"]) == 1
        applied = result["applied"][0]
        assert applied["section"] == "nose"
        assert applied["value"] == 0.4
        assert applied["targets"], "a write should name the targets it touched"

        # And the shape key is really on the mesh, under the name that was
        # reported - which is what makes the answer addressable.
        names = _shapekey_names(character.basemesh)
        written = [entry for entry in applied["targets"] if entry["new_value"]]
        assert written, "something should have ended up non-zero: {!r}".format(applied["targets"])
        assert written[0]["target"] in names, \
            "{!r} was reported written but is not a shape key on the mesh".format(written[0])


def test_a_target_not_on_the_mesh_is_loaded_rather_than_silently_ignored():
    """commands.set_targets where set_target_value() alone would do nothing

    MPFB's ``set_target_value()`` is a **silent no-op** for a name that is not
    among the key blocks. This is the test that says the load happened.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-targets-load")
    paths = _fixture_tree(root)
    with _Character() as character:
        before = set(_shapekey_names(character.basemesh))
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            result = _result({
                "name": character.basemesh.name,
                "modifiers": [{"section": "chin", "category": "chin-triangle", "value": 0.6}],
            })

        assert result["performed"] is True, result["message"]
        after = set(_shapekey_names(character.basemesh))
        assert after - before, \
            "a target absent from the mesh should have been loaded onto it, nothing was added"
        touched = result["applied"][0]["targets"][0]
        assert touched["present_before"] is False
        assert touched["loaded_from"], "the answer should name the file it read"


def test_one_bad_entry_applies_none_of_the_batch():
    """commands.set_targets with a good entry and an unknown category

    The whole point of the two-phase split, and it is asserted against the
    **mesh** rather than against ``applied``: a command that wrote half the
    batch and reported none of it would pass a weaker test.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-targets-atomic")
    paths = _fixture_tree(root)
    with _Character() as character:
        before = _shapekey_names(character.basemesh)
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            result = _result({
                "name": character.basemesh.name,
                "modifiers": [
                    {"section": "chin", "category": "chin-triangle", "value": 0.6},
                    {"section": "chin", "category": "no-such-category-at-all", "value": 0.2},
                ],
            })

        assert result["applied"] == [], "nothing at all should have been applied"
        assert result["performed"] is False
        assert len(result["resolution_errors"]) == 1
        assert result["resolution_errors"][0]["reason"] == "unknown_category"
        assert "known_categories_in_section" in result["resolution_errors"][0]
        assert _shapekey_names(character.basemesh) == before, \
            "the good entry must not have been written either"


def test_a_sided_category_refuses_to_guess_a_side():
    """commands.set_targets on a left/right category with no side given"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-targets-sided")
    paths = _fixture_tree(root)
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            result = _result({
                "name": character.basemesh.name,
                "modifiers": [{"section": "arms",
                               "category": "lowerarm-scale-depth-decr-incr",
                               "value": 0.3}],
            })

        assert result["applied"] == []
        assert result["resolution_errors"][0]["reason"] == "side_required"
        assert "coin flip" in result["resolution_errors"][0]["message"]


def test_symmetry_applies_a_sided_category_to_both_sides():
    """commands.set_targets with symmetry on"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-targets-symmetry")
    paths = _fixture_tree(root)
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            result = _result({
                "name": character.basemesh.name,
                "symmetry": True,
                "modifiers": [{"section": "arms",
                               "category": "lowerarm-scale-depth-decr-incr",
                               "side": "left", "value": 0.3}],
            })

        assert result["performed"] is True, result["message"]
        applied = result["applied"][0]
        assert applied["symmetry_applied"] is True
        sides = set(entry["side"] for entry in applied["targets"])
        assert sides == {"left", "right"}, \
            "both sides should have been written, got {!r}".format(sides)


def test_a_missing_target_file_is_a_resolution_error_not_an_ioerror():
    """commands.set_targets on the fixture category whose right-hand files are absent

    ``ears`` has only its left-hand target files on disk, deliberately. A
    resolution phase that did not check would raise ``IOError`` out of
    ``load_target()`` with part of the batch already written.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-targets-missing")
    paths = _fixture_tree(root)
    with _Character() as character:
        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            envelope = dispatch("set_targets", {
                "name": character.basemesh.name,
                "modifiers": [{"section": "ears", "category": "ear-lobe-decr-incr",
                               "side": "right", "value": 0.5}],
            })

        assert envelope["status"] == "ok", \
            "a missing file is an answer, not a command_failed: {!r}".format(envelope)
        result = envelope["result"]
        assert result["applied"] == []
        assert result["resolution_errors"][0]["reason"] == "target_file_not_found"


def test_naming_nothing_changes_nothing():
    """commands.set_targets with neither modifiers nor targets"""
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name})

        assert result["found"] is True
        assert result["ready"] is True
        assert result["applied"] == []
        assert result["performed"] is False


def test_the_callers_selection_and_active_object_are_restored():
    """commands.set_targets puts back what it borrowed"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-targets-selection")
    paths = _fixture_tree(root)
    with _Character() as character:
        bystander = bpy.data.objects.new("TargetsBystander",
                                         bpy.data.meshes.new("TargetsBystanderMesh"))
        bpy.context.scene.collection.objects.link(bystander)
        services["ObjectService"].activate_blender_object(bystander)
        character.basemesh.select_set(False)

        with redirected_locations(services, mpfb_data=paths["mpfb_data"],
                                  user_data=paths["user_data"]):
            _result({"name": character.basemesh.name,
                     "modifiers": [{"section": "chin", "category": "chin-triangle",
                                    "value": 0.6}]})

        assert bpy.context.view_layer.objects.active is bystander
        assert character.basemesh.select_get() is False


def test_mpfb_being_unavailable_refuses_rather_than_half_writing():
    """commands.set_targets against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("set_targets")

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
