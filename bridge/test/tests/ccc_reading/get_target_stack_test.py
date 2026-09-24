"""
``get_target_stack`` against a real MPFB: two views of one character.

The claim this module exists for is the one about ``"basis"``.
``TargetService.get_target_stack()`` excludes any shape key whose lowercased
name *contains* that word - not merely equals it - so a user target called
``basis-nose-widen`` is invisible to ``has_target()``, ``get_target_value()``
and every write MPFB can perform. That reading of MPFB's source is why this
command reads ``key_blocks`` directly, and
``test_a_shapekey_containing_basis_is_invisible_to_mpfb_itself`` is the first
time it has been put to MPFB.

Three more claims are checked here rather than against a stub:

- **that the rollup is MPFB's own arithmetic** - the positive target wins when
  both are somehow present, and the negative one reads back *negated*, so a
  slider at -0.4 is a shape key at 0.4 under the ``decr`` name;
- **that the two views agree**, which is what makes ``modifiers`` safe to write
  back through ``set_targets``;
- **that a shape key carries no metadata at all**, so placing
  ``l-lowerarm-scale-depth-incr`` back into its category, side and polarity is
  a lookup in a table rebuilt per call.

**The shape keys are added with Blender's own API rather than loaded through
MPFB**, and that is the right fixture rather than a shortcut: this command
reads ``key_blocks``, so a key added that way is exactly what it sees.
Loading a real target would mean shipping real vertex data, would exercise
``TargetService.load_target()`` - a *write*, which is stage 4's - and would
test nothing this command does.
"""

import os

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import build_target_tree
from .._fixtures import dispatch
from .._fixtures import only_these_data_roots
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import supplied_resolution

COMMAND = "get_target_stack"

# One of the four target files behind the sided, opposed category in the
# fixture's target.json. The category slider reads +0.4 for the `incr` half and
# -0.4 for the `decr` half, which is the arithmetic under test.
LEFT_POSITIVE = "l-lowerarm-scale-depth-incr"
LEFT_NEGATIVE = "l-lowerarm-scale-depth-decr"
RIGHT_POSITIVE = "r-lowerarm-scale-depth-incr"
CATEGORY = "lowerarm-scale-depth-decr-incr"

# Contains "basis", so MPFB cannot see it. Not "Basis", which is Blender's own
# rest shape and is excluded for a different and correct reason.
INVISIBLE_TO_MPFB = "basis-nose-widen"


def _add_shapekey(basemesh, name, value):
    """One shape key on the mesh, by Blender's own API. See the docstring."""
    block = basemesh.shape_key_add(name=name, from_mix=False)
    block.value = value
    return block


@pytest.fixture(name="character")
def _with_a_character_and_a_target_tree(tmp_path):
    """A real character, then MPFB pointed at a target tree of this test's own.

    **The order is load-bearing**: ``create_human()`` reads ``base.obj`` out of
    MPFB's own data directory, so redirecting ``<mpfb data>`` first would fail
    inside MPFB rather than testing anything.
    """
    services = services_or_skip()
    tree = build_target_tree(str(tmp_path))
    with Character() as built:
        with only_these_data_roots(services, mpfb_data=tree["mpfb_data"],
                                   user_data=tree["user_data"]):
            yield built


def _entries(answer):
    return {entry["shapekey_name"]: entry for entry in answer["targets"]}


def _modifier(answer, category, side):
    for entry in answer["modifiers"]:
        if entry["category"] == category and entry["side"] == side:
            return entry
    return None


def test_a_bare_character_has_macro_keys_and_no_details(character):
    """The default stack, and what is left out of it unasked"""
    answer = result(COMMAND, {"name": character.basemesh.name})

    assert answer["found"] is True
    assert answer["basemesh_name"] == character.basemesh.name
    assert answer["has_shapekeys"] is True
    # The macro keys are on the mesh and are left out by default, because
    # mpfb_get_macro_details reports them far more usefully.
    assert answer["counts_by_kind"].get("macro"), \
        "a character MPFB built carries macro shape keys"
    assert all(entry["kind"] != "macro" for entry in answer["targets"])
    assert "macro shape key(s) were left out" in answer["message"]

    with_macro = result(COMMAND, {"name": character.basemesh.name, "include_macro": True})
    assert any(entry["kind"] == "macro" for entry in with_macro["targets"])


def test_blenders_own_basis_is_never_listed(character):
    """"Basis" is the rest shape, not a target, and is never addressable"""
    answer = result(COMMAND, {"name": character.basemesh.name, "include_macro": True})

    assert "Basis" not in _entries(answer), \
        "Blender's rest shape is not a target and must not be listed"
    assert answer["counts_by_kind"].get("basis") is None


def test_a_detail_shapekey_is_placed_back_into_its_category(character):
    """The reverse mapping: a shape key carries no metadata of its own"""
    _add_shapekey(character.basemesh, LEFT_POSITIVE, 0.4)

    answer = result(COMMAND, {"name": character.basemesh.name})

    entry = _entries(answer)[LEFT_POSITIVE]
    assert entry["kind"] == "detail"
    assert entry["section"] == "arms"
    assert entry["category"] == CATEGORY
    assert entry["side"] == "left"
    assert entry["polarity"] == "positive"
    assert entry["listed_in_target_json"] is True, \
        "this category really is in the bundled index"
    assert entry["value"] == 0.4


def test_the_rollup_is_mpfbs_arithmetic_including_the_negation(character):
    """_get_opposed_modifier_value(), reproduced rather than approximated"""
    _add_shapekey(character.basemesh, LEFT_POSITIVE, 0.4)

    positive = result(COMMAND, {"name": character.basemesh.name})
    reading = _modifier(positive, CATEGORY, "left")
    assert reading is not None, \
        "a non-zero category should appear in the rollup, got {!r}".format(
            positive["modifiers"])
    assert reading["value"] == 0.4
    assert reading["opposed"] is True

    # The negative half reads back *negated*: a slider at -0.4 exists only as a
    # shape key at 0.4 under the decr name, because Blender clamps a shape key
    # value to 0.0-1.0. The positive key is *removed* rather than zeroed, for
    # the reason the next test asserts.
    character.basemesh.shape_key_remove(
        character.basemesh.data.shape_keys.key_blocks[LEFT_POSITIVE])
    _add_shapekey(character.basemesh, LEFT_NEGATIVE, 0.4)

    negative = result(COMMAND, {"name": character.basemesh.name})
    assert _modifier(negative, CATEGORY, "left")["value"] == -0.4, \
        "the decr half should read back negated, got {!r}".format(
            _modifier(negative, CATEGORY, "left"))


def test_the_positive_target_wins_when_both_halves_are_present(character):
    """_get_opposed_modifier_value()'s first branch, which looks like a bug

    MPFB asks whether the positive target is *present*, not whether it is
    non-zero - so a category whose positive shape key exists at 0.0 reads 0.0
    however far the negative one is pushed. That is a quirk worth reproducing
    rather than fixing: the two halves are not supposed to coexist, and a
    reimplementation that summed them would disagree with the slider the user
    is looking at.
    """
    _add_shapekey(character.basemesh, LEFT_POSITIVE, 0.0)
    _add_shapekey(character.basemesh, LEFT_NEGATIVE, 0.4)

    answer = result(COMMAND, {"name": character.basemesh.name})

    assert _modifier(answer, CATEGORY, "left") is None, \
        "the positive half is present at 0.0, so the category reads 0.0 and is omitted"
    # Both shape keys are still reported in the raw view, which is how a caller
    # can see the state the rollup is hiding.
    entries = _entries(answer)
    assert entries[LEFT_NEGATIVE]["value"] == 0.4
    assert entries[LEFT_POSITIVE]["value"] == 0.0


def test_a_sided_category_that_differs_is_reported_as_an_asymmetry(character):
    """The derived view, and the threshold it uses"""
    _add_shapekey(character.basemesh, LEFT_POSITIVE, 0.4)
    _add_shapekey(character.basemesh, RIGHT_POSITIVE, 0.1)

    answer = result(COMMAND, {"name": character.basemesh.name})

    asymmetries = {entry["category"]: entry for entry in answer["asymmetries"]}
    assert CATEGORY in asymmetries, \
        "a sided category with two different readings is an asymmetry, got {!r}".format(
            answer["asymmetries"])
    entry = asymmetries[CATEGORY]
    assert entry["left"] == 0.4 and entry["right"] == 0.1
    assert round(entry["difference"], 6) == 0.3


def test_a_symmetric_character_reports_no_asymmetry(character):
    """The other half: the comparison must not fire on everything"""
    _add_shapekey(character.basemesh, LEFT_POSITIVE, 0.4)
    _add_shapekey(character.basemesh, RIGHT_POSITIVE, 0.4)

    answer = result(COMMAND, {"name": character.basemesh.name})

    assert not [entry for entry in answer["asymmetries"] if entry["category"] == CATEGORY], \
        "two equal readings are not an asymmetry, got {!r}".format(answer["asymmetries"])


def test_a_shapekey_containing_basis_is_invisible_to_mpfb_itself(character):
    """TargetService excluding any name *containing* "basis", not equalling it

    The claim this whole command is shaped around, asked of MPFB. If it stopped
    being true, reading key_blocks directly would merely be redundant; while it
    is true, reading through TargetService would hide a shape key that is really
    deforming the mesh.
    """
    services = services_or_skip()
    target_service = services["TargetService"]
    _add_shapekey(character.basemesh, INVISIBLE_TO_MPFB, 0.5)

    # MPFB cannot see it - which is why this command does not ask MPFB.
    assert not target_service.has_target(character.basemesh, INVISIBLE_TO_MPFB), \
        "MPFB should not be able to see a shape key whose name contains 'basis'"
    visible_to_mpfb = [str(entry.get("target"))
                       for entry in target_service.get_target_stack(character.basemesh)]
    assert INVISIBLE_TO_MPFB not in visible_to_mpfb, \
        "MPFB's own stack should exclude it, got {!r}".format(visible_to_mpfb)

    answer = result(COMMAND, {"name": character.basemesh.name})

    entry = _entries(answer)[INVISIBLE_TO_MPFB]
    assert entry["value"] == 0.5, "it is really on the mesh and really deforming it"
    assert entry["visible_to_targetservice"] is False, \
        "the entry has to say that MPFB cannot address it"
    assert "invisible to MPFB itself" in answer["message"], \
        "and the message has to say so, or a caller will try to set it"


def test_the_two_views_are_two_readings_of_one_snapshot(character):
    """What keeps `targets` and `modifiers` from disagreeing"""
    _add_shapekey(character.basemesh, LEFT_POSITIVE, 0.25)

    answer = result(COMMAND, {"name": character.basemesh.name})

    raw = _entries(answer)[LEFT_POSITIVE]["value"]
    rolled = _modifier(answer, CATEGORY, "left")["value"]
    # The rollup is the same number seen through MPFB's slider arithmetic, and
    # for a positive unsided reading that arithmetic is the identity.
    assert raw == rolled == 0.25


def test_the_rollup_is_neither_filtered_nor_paged(character):
    """The asymmetry that looks like an oversight and is not"""
    _add_shapekey(character.basemesh, LEFT_POSITIVE, 0.4)

    answer = result(COMMAND, {"name": character.basemesh.name,
                              "name_contains": "nothing-matches-this", "limit": 0})

    assert answer["targets"] == [], "the filter and the cap apply to the raw view"
    assert _modifier(answer, CATEGORY, "left") is not None, \
        "the rollup is what a caller writes back, so cutting it would break the round trip"
    assert answer["modifier_count"] == len(answer["modifiers"])


def test_the_counts_are_taken_before_any_filter(character):
    """So a filtered answer still says what it was filtered out of"""
    _add_shapekey(character.basemesh, LEFT_POSITIVE, 0.4)

    answer = result(COMMAND, {"name": character.basemesh.name,
                              "name_contains": "lowerarm"})

    assert answer["total_count"] == 1, "one shape key matched the filter"
    assert answer["counts_by_kind"].get("macro"), \
        "the macro keys are still counted, though none of them matched"


def test_the_subject_may_be_any_object_in_the_family(character):
    """find_object_of_type_amongst_nearest_relatives(), as everywhere else"""
    from .._fixtures import typed_child  # pylint: disable=import-outside-toplevel

    services = services_or_skip()
    garment = typed_child(services, character.basemesh, "BridgeTestStackShirt", "Clothes")
    try:
        answer = result(COMMAND, {"name": garment.name})

        assert answer["basemesh_name"] == character.basemesh.name
        assert answer["subject_name"] == garment.name
        assert answer["subject_resolved_by"] == "name"
    finally:
        bpy.data.objects.remove(garment, do_unlink=True)


def test_an_object_outside_a_character_is_an_answer_rather_than_an_error(character):
    """found: false, with a sentence saying which mistake was made"""
    from .._fixtures import linked_plain_object  # pylint: disable=import-outside-toplevel

    plain = linked_plain_object("BridgeTestNoStack")
    try:
        answer = dispatch(COMMAND, {"name": plain.name})

        assert answer["status"] == "ok"
        assert answer["result"]["found"] is False
        assert answer["result"]["targets"] == []
        assert "no target stack" in answer["result"]["message"]
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)


def test_bad_arguments_are_refused_before_the_handler_runs():
    """command_server.dispatch(): "true" is a true value, and True is an int"""
    command_server = bridge_module("command_server")

    for params in ({"include_macro": "true"}, {"include_expressions": 1},
                   {"limit": True}, {"limit": -1}, {"offset": True}):
        answer = dispatch(COMMAND, params)
        assert answer["error"] == command_server.ERROR_INVALID_PARAMS, \
            "{!r} should be refused, got {!r}".format(params, answer)


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    """command_server.dispatch() with requires_mpfb and no MPFB"""
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = dispatch(COMMAND, {"name": None})

    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE
    assert "found" not in answer
