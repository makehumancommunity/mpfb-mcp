"""
``generate_rigify_rig`` against a real Rigify, in a Blender with no window.

**This module is the reason FR 032 ran a spike first.** Rigify generation drives
``bpy.ops`` throughout - ``select_all``, ``mode_set``, ``rigify_upgrade_face``,
``rigify_generate`` - and operators in ``blender --background`` fail for context
reasons that have nothing to do with this project's code. They do not fail here:
[the spike](../../../../feature-requests/done/032-creation-and-modification-migrated/SPIKE.md)
established that before any of this was written, which is why this module tests
the real thing rather than skipping to a live check.

Two claims live here and could live nowhere else:

- **Generation really produces a Rigify rig**, identified as one by MPFB's own
  ``identify_rig()``, with the character re-parented onto it.
- **Nothing is restored afterwards, and the answer says so.** Every other
  mutating command puts the caller's selection back; this one cannot, because
  the operator's final act is to select and activate its own result.
  ``active_object_after`` is asserted to be that result, which is the only
  honest form the claim can take.

Every test that generates skips with a reason when Rigify is not enabled. That
is the one thing this suite still cannot establish - a Blender with Rigify
**off**, where the ``rigify_unavailable`` refusal lives - and it is named in the
spike's own "what it does not establish" rather than quietly missing.
"""

import bpy
import pytest

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution
from .._fixtures import typed_child


def _result(params=None):
    return _fixture_result("generate_rigify_rig", params)


def _rigify_or_skip(services):
    if not services["SystemService"].check_for_rigify():
        pytest.skip("Rigify is not enabled in this Blender, so nothing can be generated")


def _with_metarig(services, character):
    services["ObjectService"].activate_blender_object(character.basemesh)
    meta_rig = services["HumanService"].add_builtin_rig(
        character.basemesh, "rigify.human", import_weights=True)
    assert meta_rig is not None, "the fixture meta rig should have been added"
    return meta_rig


def test_a_metarig_becomes_a_real_rigify_rig():
    """commands.generate_rigify_rig on a character carrying a meta rig"""
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        meta_rig = _with_metarig(services, character)

        result = _result({"name": character.basemesh.name})

        assert result["performed"] is True, result["message"]
        assert result["generated"] is True
        assert result["metarig_name"] == meta_rig.name
        generated = bpy.data.objects[result["rig_object_name"]]
        assert services["RigService"].identify_rig(generated).startswith("rigify_generated."), \
            "MPFB should recognise what Rigify produced as a generated rig"
        assert result["metarig_disposition"] == "hidden", "hide is the default"
        assert result["refit_will_be_possible"] is True


def test_the_answer_reports_the_active_object_rather_than_restoring_it():
    """commands.generate_rigify_rig leaves its own result active, deliberately

    The one mutating command here that cannot put the caller's selection back.
    """
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        _with_metarig(services, character)
        bystander = bpy.data.objects.new("GenBystander", bpy.data.meshes.new("GenBystanderMesh"))
        bpy.context.scene.collection.objects.link(bystander)
        services["ObjectService"].activate_blender_object(bystander)

        result = _result({"name": character.basemesh.name})

        assert result["selection_restored"] is False
        assert result["active_object_after"] == result["rig_object_name"], \
            "the operator activates its own result, and the answer must say what is active now"
        assert bpy.context.view_layer.objects.active.name == result["active_object_after"], \
            "and it must be *true*, not merely reported"


def test_deleting_the_metarig_is_reported_as_permanent():
    """commands.generate_rigify_rig with meta_rig_action delete

    The consequence that outlives the call: a generated rig with no meta rig in
    the scene can never be refitted, and refit_human will say so from now on.
    """
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        meta_rig = _with_metarig(services, character)
        metarig_name = meta_rig.name

        result = _result({"name": character.basemesh.name, "meta_rig_action": "delete"})

        assert result["generated"] is True
        assert result["metarig_disposition"] == "deleted"
        assert result["metarig_name_after"] is None, \
            "the datablock is gone, so the rename that preceded it cannot be observed"
        assert result["refit_will_be_possible"] is False
        assert result["refit_impossible_reason"] is not None
        assert metarig_name not in bpy.data.objects, "the meta rig should really be gone"


def test_keeping_the_metarig_leaves_it_visible():
    """commands.generate_rigify_rig with meta_rig_action keep"""
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        meta_rig = _with_metarig(services, character)

        result = _result({"name": character.basemesh.name, "meta_rig_action": "keep"})

        assert result["metarig_disposition"] == "kept"
        assert result["refit_will_be_possible"] is True
        assert meta_rig.name in bpy.data.objects


def test_generating_twice_is_refused_rather_than_attempted():
    """commands.generate_rigify_rig on a character that already has one

    Generation re-parents the character onto the generated rig, so the meta rig
    is no longer among its relatives - which is why "already generated" is a
    distinct answer from "that is not a meta rig".
    """
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        _with_metarig(services, character)
        first = _result({"name": character.basemesh.name})

        second = _result({"name": character.basemesh.name})

        assert second["generated"] is False
        assert second["blocked_by"] == "already_generated"
        assert second["performed"] is False
        assert second["generated_rigs"][0]["name"] == first["rig_object_name"]


def test_an_ordinary_rig_is_not_a_metarig():
    """commands.generate_rigify_rig on a character carrying MPFB's standard rig"""
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        services["ObjectService"].activate_blender_object(character.basemesh)
        services["HumanService"].add_builtin_rig(
            character.basemesh, "default", import_weights=True)

        result = _result({"name": character.basemesh.name})

        assert result["generated"] is False
        assert result["blocked_by"] == "not_a_metarig"
        assert result["skeletons"], "the refusal should name what it found instead"


def test_a_character_with_no_armature_says_what_to_do():
    """commands.generate_rigify_rig on an unrigged character"""
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        result = _result({"name": character.basemesh.name})

        assert result["generated"] is False
        assert result["blocked_by"] == "no_armature_found"
        assert "mpfb_add_rig" in result["message"]


def test_mesh_assets_present_at_generation_time_are_named():
    """commands.generate_rigify_rig reports what it re-parented

    Generation handles exactly what is on the character when it runs and will
    not run again, which is the second half of the ordering problem add_rig
    reports the first half of.
    """
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        meta_rig = _with_metarig(services, character)
        # Parented to the **rig**, as MPFB does on a rigged character: adding a
        # rig re-parents the basemesh onto it, so a garment hung off the
        # basemesh is a grandchild and find_related_mesh_assets(), which takes
        # children, does not see it. That is MPFB's arrangement rather than this
        # fixture's convenience.
        garment = typed_child(services, meta_rig, "GenGarment", "Clothes")

        result = _result({"name": character.basemesh.name})

        assert result["generated"] is True
        assert garment.name in result["mesh_assets_present"], \
            "a garment on the character at generation time must be named: {!r}".format(
                result["mesh_assets_present"])


def test_a_placed_metarig_generates_a_rig_where_it_stands():
    """commands.generate_rigify_rig on a meta rig moved and turned, garment on

    FR 045's requirement 17. Generation leaves the generated rig at the origin,
    unturned, with its bones in the meta rig's space - and the character,
    re-parented onto it, goes back to the origin with it. The command gives the
    generated rig the meta rig's world matrix, so the body and its garment end
    where they were.
    """
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        meta_rig = _with_metarig(services, character)
        garment = typed_child(services, meta_rig, "PlacedGarment", "Clothes")
        meta_rig.location = (4.0, -2.0, 0.0)
        meta_rig.rotation_euler = (0.0, 0.0, -0.7853981633974483)
        bpy.context.view_layer.update()
        body_world = character.basemesh.matrix_world.copy()
        garment_world = garment.matrix_world.copy()

        result = _result({"name": character.basemesh.name})

        assert result["generated"] is True, result["message"]
        assert result["metarig_placement_moved_to_rig"] is True
        generated = bpy.data.objects[result["rig_object_name"]]
        assert (generated.matrix_world.to_translation()
                - meta_rig.matrix_world.to_translation()).length < 1e-6
        for blender_object, before in ((character.basemesh, body_world),
                                       (garment, garment_world)):
            after = blender_object.matrix_world
            assert all(abs(after[row][column] - before[row][column]) < 1e-5
                       for row in range(4) for column in range(4)), blender_object.name


def test_a_metarig_at_the_origin_needs_no_placement_carried():
    """commands.generate_rigify_rig on an unmoved meta rig"""
    services = _services_or_skip()
    _rigify_or_skip(services)
    with _Character() as character:
        _with_metarig(services, character)
        result = _result({"name": character.basemesh.name})
        assert result["generated"] is True, result["message"]
        assert result["metarig_placement_moved_to_rig"] is False


def test_an_unresolvable_name_is_an_answer():
    """commands.generate_rigify_rig naming an object that does not exist"""
    _services_or_skip()
    envelope = dispatch("generate_rigify_rig", {"name": "no-such-object-anywhere"})

    assert envelope["status"] == "ok"
    assert envelope["result"]["blocked_by"] == "subject_not_found"
    assert envelope["result"]["performed"] is False


def test_an_unknown_meta_rig_action_is_refused_by_the_contract():
    """commands.generate_rigify_rig with a meta_rig_action that is not one of three"""
    _services_or_skip()
    envelope = dispatch("generate_rigify_rig", {"meta_rig_action": "remove"})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "hide" in envelope["message"]


def test_mpfb_being_unavailable_refuses_rather_than_half_generating():
    """commands.generate_rigify_rig against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("generate_rigify_rig")

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
