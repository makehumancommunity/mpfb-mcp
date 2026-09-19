"""
``get_macro_details`` against a real MPFB: the phenotype, and its drift.

Every claim in this command is about ``TargetService``, and every one of them
has until now been checked against a stub of ``TargetService`` written from the
same reading of MPFB's source as the code being checked. What is put to MPFB
here:

- what ``get_macro_info_dict_from_basemesh()`` actually contains, including
  that ``race`` is a nested dict of three weights and everything else is flat;
- that ``calculate_target_stack_from_macro_info_dict()`` answers with
  ``(fragment, weight)`` pairs whose fragments are paths and not shape key
  names;
- that ``macrodetail_filename_to_shapekey_name(..., encode_name=True)`` and
  ``get_current_macro_targets(..., decode_names=False)`` speak **one**
  vocabulary - the encoded one. This is the claim the payload was changed to
  make true, and the one a caller's drift comparison rests on entirely;
- that a default ``create_human()`` character is *not* drifted, which is the
  only way to know the comparison is not reporting drift on everything.

One of these turned out differently than the stub asserted, and the difference
is caller-visible: MPFB's default race weights are the literal ``0.33`` each,
so they sum to 0.99 and **every** default character trips this command's
"that scales the phenotype" warning. See
``test_mpfbs_own_default_character_is_not_race_normalized``, which records it
rather than repairing it.

**Nothing here recalculates.** A command whose caller believes it read-only
must not repair what it finds, so the test that matters most is the one
asserting the shape keys are the same after the call as before it.
"""

from . import bridge_module
from ._fixtures import Character
from ._fixtures import dispatch
from ._fixtures import linked_plain_object
from ._fixtures import result
from ._fixtures import services_or_skip
from ._fixtures import supplied_resolution
from ._fixtures import typed_child

COMMAND = "get_macro_details"

RACE_NAMES = ("asian", "caucasian", "african")


def test_a_default_character_reads_back_its_phenotype():
    """TargetService.get_macro_info_dict_from_basemesh() on a real basemesh"""
    with Character() as character:
        answer = result(COMMAND, {"name": character.basemesh.name})

        assert answer["found"] is True
        assert answer["basemesh_name"] == character.basemesh.name
        assert answer["subject_resolved_by"] == "name"
        details = answer["macro_details"]
        assert isinstance(details.get("race"), dict), \
            "race is a nested dict of weights, which is what the coercion loop branches on"
        assert set(details["race"]) >= set(RACE_NAMES)
        for key, value in details.items():
            if key == "race":
                continue
            assert isinstance(value, float), \
                "{!r} should have been coerced to a plain float, got {!r}".format(key, value)


def test_the_subject_may_be_any_object_in_the_family():
    """ObjectService.find_object_of_type_amongst_nearest_relatives()"""
    import bpy  # pylint: disable=import-outside-toplevel

    services = services_or_skip()
    with Character() as character:
        garment = typed_child(services, character.basemesh, "BridgeTestShirt", "Clothes")
        try:
            answer = result(COMMAND, {"name": garment.name})

            # The whole reason a caller may pass the name list_objects handed
            # it: the basemesh is found from whatever member of the family was
            # named, and the answer says which object it actually read.
            assert answer["found"] is True
            assert answer["basemesh_name"] == character.basemesh.name
            assert answer["subject_name"] == garment.name
        finally:
            bpy.data.objects.remove(garment, do_unlink=True)


def test_an_object_outside_a_character_is_an_answer_rather_than_an_error():
    """commands.get_macro_details on a plain Blender object"""
    import bpy  # pylint: disable=import-outside-toplevel

    services_or_skip()
    plain = linked_plain_object("BridgeTestNotACharacter")
    try:
        answer = dispatch(COMMAND, {"name": plain.name})

        assert answer["status"] == "ok"
        assert answer["result"]["found"] is False
        assert answer["result"]["subject_name"] == plain.name
        assert answer["result"]["basemesh_name"] is None
        assert "no MakeHuman basemesh" in answer["result"]["message"]
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)


def test_the_stack_and_the_shapekeys_on_the_mesh_are_one_vocabulary():
    """The encoded names, which is what makes a drift comparison possible"""
    with Character() as character:
        answer = result(COMMAND, {"name": character.basemesh.name})

        stack_names = set(entry["shapekey_name"] for entry in answer["macro_target_stack"])
        on_the_mesh = set(answer["current_macro_shapekeys"])
        assert stack_names, "A character built by MPFB implies at least one macro target"
        assert on_the_mesh, "A character built by MPFB carries macro shape keys"
        # If these two ever stop being one vocabulary, a healthy character reads
        # as totally drifted and the tool's advice - call set_macro_details -
        # would be wrong every time.
        assert stack_names & on_the_mesh, \
            "The derived stack and the mesh listing must be comparable:\n  stack={!r}\n  mesh={!r}"\
            .format(sorted(stack_names), sorted(on_the_mesh))
        assert answer["macro_target_count"] == len(answer["macro_target_stack"])


def test_a_freshly_built_character_is_not_reported_as_drifted():
    """The comparison's other half: it must not fire on everything"""
    with Character() as character:
        answer = result(COMMAND, {"name": character.basemesh.name})

        assert answer["has_shapekeys"] is True
        assert "drifted apart" not in answer["message"], \
            "A character MPFB just built should not be reported as drifted: {!r}".format(
                answer["message"])


def test_the_decoded_names_are_reported_beside_the_encoded_ones():
    """TargetService.decode_shapekey_name() as a second view, not a replacement"""
    with Character() as character:
        answer = result(COMMAND, {"name": character.basemesh.name})

        assert len(answer["current_macro_shapekeys_decoded"]) == \
            len(answer["current_macro_shapekeys"])
        assert answer["current_macro_shapekeys_decoded"] != answer["current_macro_shapekeys"], \
            "Macro shape keys are stored encoded, so decoding should change them"


def test_mpfbs_own_default_character_is_not_race_normalized():
    """The finding: MPFB's default race weights are 0.33 each, and sum to 0.99

    This test asserted the opposite when it was written, from the same reading
    of MPFB's source that ``tests/blender_stubs.py`` was written from - where
    the three weights are a third each. MPFB's real default is the literal
    ``0.33``, so the sum is 0.99, the tool's tolerance is 0.001, and **every
    default character trips the "that scales the phenotype" warning**.

    It is recorded here rather than repaired. The payload behaves this way, the
    command reproduces the payload, and FR 031's comparison is between the two;
    whether a 0.01 tolerance is the right one is a question about the tool,
    with a caller-visible message attached, and it belongs to whichever effort
    decides to answer it rather than to a migration.
    """
    with Character() as character:
        answer = result(COMMAND, {"name": character.basemesh.name})

        assert answer["race_sum"] == 0.99, \
            "MPFB's default race weights sum to 0.99; got {!r}".format(answer["race_sum"])
        assert answer["race_normalized"] is False
        assert "sum to 0.99" in answer["message"], \
            "The message should report the sum it found: {!r}".format(answer["message"])
        # The three weights are reported raw rather than normalised, which is
        # what makes the sum above visible at all.
        for race_name in RACE_NAMES:
            assert answer["macro_details"]["race"][race_name] < 0.34


def test_the_defaults_are_reported_beside_the_current_values():
    """TargetService.get_default_macro_info_dict()"""
    with Character() as character:
        answer = result(COMMAND, {"name": character.basemesh.name})

        defaults = answer["default_macro_details"]
        assert isinstance(defaults, dict) and defaults
        assert set(defaults) == set(answer["macro_details"]), \
            "The defaults and the current values should describe the same sliders"


def test_nothing_is_recalculated_by_reading():
    """reapply_macro_details() deliberately not called"""
    with Character() as character:
        services = services_or_skip()
        target_service = services["TargetService"]
        before = list(target_service.get_current_macro_targets(
            character.basemesh, decode_names=False))
        values_before = [key_block.value for key_block
                         in character.basemesh.data.shape_keys.key_blocks]

        result(COMMAND, {"name": character.basemesh.name})

        after = list(target_service.get_current_macro_targets(
            character.basemesh, decode_names=False))
        values_after = [key_block.value for key_block
                        in character.basemesh.data.shape_keys.key_blocks]
        assert after == before, "Reading the phenotype must not change the shape keys"
        assert values_after == values_before, "Reading must not change any shape key's value"


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    """command_server.dispatch() with requires_mpfb and no MPFB"""
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_NOT_INITIALIZED):
        answer = dispatch(COMMAND, {"name": None})

    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE
    assert answer["state"] == "not_initialized", \
        "The refusal should name the state, so a caller knows which install problem it is"
