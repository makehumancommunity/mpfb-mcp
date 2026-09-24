"""
``set_macro_details`` against a real MPFB: the write, and then the shape.

The claim a stub could never make. On this side the properties are really
written and ``TargetService.reapply_macro_details()`` really rebuilds the macro
target stack, so the two questions worth asking can be asked of MPFB rather than
of a fixture:

- **does an omitted slider stay where it was**, which is the distinction the
  whole tool turns on - "not mentioned" and "set to the default" are different
  requests; and
- **does the mesh actually change**, which is the difference between writing a
  number and modelling a character. Both are asserted through MPFB's own
  ``get_macro_info_dict_from_basemesh()`` and through the shape keys on the
  mesh, not through what this command reported.

**The no-op call is tested here too**, because its cost is the reason it exists:
a full macro reapply takes seconds, and a call naming no slider answers
immediately with ``recalculated: false`` rather than rebuilding a shape that
would come out identical.
"""

import bpy

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution


def _result(params=None):
    return _fixture_result("set_macro_details", params)


def _change(argument, prop, value):
    return {"argument": argument, "property": prop, "value": value}


def test_a_named_slider_is_written_and_the_shape_rebuilt():
    """commands.set_macro_details with one slider"""
    services = _services_or_skip()
    target_service = services["TargetService"]
    with _Character() as character:
        before = target_service.get_macro_info_dict_from_basemesh(character.basemesh)

        result = _result({"name": character.basemesh.name,
                          "changes": [_change("gender", "gender", 1.0)]})

        assert result["performed"] is True
        assert result["recalculated"] is True
        assert len(result["changes"]) == 1
        assert result["changes"][0]["name"] == "gender"

        after = target_service.get_macro_info_dict_from_basemesh(character.basemesh)
        assert abs(after["gender"] - 1.0) < 0.0001, \
            "MPFB should have stored the new value, got {!r}".format(after["gender"])
        assert abs(before["gender"] - after["gender"]) > 0.0001, \
            "the fixture should have started somewhere else, or this proves nothing"
        assert result["changes"][0]["new_value"] is not None
        assert abs(result["changes"][0]["new_value"] - after["gender"]) < 0.0001, \
            "the reported new value must be the one MPFB holds"


def test_an_omitted_slider_is_left_alone():
    """commands.set_macro_details naming one slider out of eleven

    The distinction the whole tool turns on: "not mentioned" and "set to the
    default" are different requests, and a command that quietly reset the other
    ten would destroy a phenotype on every call.
    """
    services = _services_or_skip()
    target_service = services["TargetService"]
    with _Character(macro_detail_dict={
            "gender": 0.2, "age": 0.8, "muscle": 0.3, "weight": 0.7,
            "proportions": 0.5, "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
            "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}}) as character:

        _result({"name": character.basemesh.name,
                 "changes": [_change("gender", "gender", 0.9)]})

        after = target_service.get_macro_info_dict_from_basemesh(character.basemesh)
        assert abs(after["gender"] - 0.9) < 0.0001
        assert abs(after["age"] - 0.8) < 0.0001, \
            "age was not named and must not have moved, got {!r}".format(after["age"])
        assert abs(after["weight"] - 0.7) < 0.0001
        assert abs(after["race"]["caucasian"] - 1.0) < 0.0001


def test_the_macro_shapekeys_really_change():
    """commands.set_macro_details changes what is on the mesh, not only a number

    Writing a macro property changes a number and nothing moves; the shape comes
    from ``reapply_macro_details()``. This is the test that says the second step
    happened.
    """
    services = _services_or_skip()
    with _Character(macro_detail_dict={
            "gender": 0.0, "age": 0.5, "muscle": 0.5, "weight": 0.5,
            "proportions": 0.5, "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
            "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}}) as character:

        result = _result({"name": character.basemesh.name,
                          "changes": [_change("gender", "gender", 1.0)]})

        assert result["macro_shapekeys_before"] != result["macro_shapekeys_after"] \
            or result["shapekeys_added"] or result["shapekeys_removed"], \
            "moving gender from 0.0 to 1.0 must change the macro shape key stack: {!r}".format(
                result["message"])
        # And the reported names are the names on the mesh, which is what makes
        # them addressable rather than merely readable.
        on_mesh = set(block.name for block in character.basemesh.data.shape_keys.key_blocks)
        for name in result["macro_shapekeys_after"]:
            assert name in on_mesh, \
                "{!r} was reported as a macro shape key but is not on the mesh".format(name)


def test_naming_no_slider_changes_nothing_and_says_so():
    """commands.set_macro_details with an empty changes list"""
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name, "changes": []})

        assert result["found"] is True
        assert result["ready"] is True
        assert result["recalculated"] is False
        assert result["performed"] is False, \
            "nothing was recalculated, so performed must be false"
        assert result["changes"] == []
        assert result["macro_details"], "the current values are the answer here"


def test_the_race_weights_are_independent_and_reported_as_such():
    """commands.set_macro_details raising one race weight

    MPFB treats the three as independent and does not normalise, so this is a
    fact about MPFB that the answer has to carry rather than hide.
    """
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name,
                          "changes": [_change("race_asian", "asian", 1.0)]})

        assert abs(result["race_sum"] - 1.0) > 0.001, \
            "raising one weight should not have reduced the others, sum is {!r}".format(
                result["race_sum"])
        assert result["race_normalized"] is False
        assert "independent" in result["message"]


def test_a_character_with_no_shapekeys_is_a_refusal_rather_than_a_warning():
    """commands.set_macro_details on a mesh tagged as a basemesh but not built by MPFB

    ``reapply_macro_details()`` merely logs "somewhat surprising" and carries
    on, which from across a socket is indistinguishable from success.
    """
    services = _services_or_skip()
    plain = bpy.data.objects.new("FakeBasemesh", bpy.data.meshes.new("FakeBasemeshMesh"))
    bpy.context.scene.collection.objects.link(plain)
    try:
        objectservice_module = __import__(
            services["ObjectService"].__module__, fromlist=["GeneralObjectProperties"])
        objectservice_module.GeneralObjectProperties.set_value(
            "object_type", "Basemesh", entity_reference=plain)

        result = _result({"name": "FakeBasemesh",
                          "changes": [_change("gender", "gender", 1.0)]})

        assert result["found"] is True
        assert result["ready"] is False
        assert result["blocked_by"] == "no_shapekeys"
        assert result["performed"] is False
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)


def test_the_callers_selection_and_active_object_are_restored():
    """commands.set_macro_details puts back what it borrowed"""
    services = _services_or_skip()
    with _Character() as character:
        bystander = bpy.data.objects.new("MacroBystander",
                                         bpy.data.meshes.new("MacroBystanderMesh"))
        bpy.context.scene.collection.objects.link(bystander)
        services["ObjectService"].activate_blender_object(bystander)
        character.basemesh.select_set(False)

        _result({"name": character.basemesh.name,
                 "changes": [_change("gender", "gender", 0.7)]})

        assert bpy.context.view_layer.objects.active is bystander
        assert character.basemesh.select_get() is False


def test_a_non_bool_prune_is_refused_by_the_contract():
    """commands.set_macro_details with prune as a string

    "false" is a true value, and a boolean check that accepted anything truthy
    would turn prune="false" into a deletion of shape keys.
    """
    _services_or_skip()
    envelope = dispatch("set_macro_details", {"prune": "false"})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"


def test_mpfb_being_unavailable_refuses_rather_than_half_writing():
    """commands.set_macro_details against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("set_macro_details")

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
