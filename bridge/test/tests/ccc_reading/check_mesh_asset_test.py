"""
``check_mesh_asset`` against a real MPFB.

What each number means is ``bbb_shared/mesh_asset_report_test.py``'s. This is which mesh,
which body, the sections, and the claim that a call **leaves nothing behind**, on a
character rather than a cube, since MPFB's validator is the thing being held to it.
That the gi's own defects are found is the request's live check.
"""

import bmesh
import bpy

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip
from .._fixtures import typed_child


def _result(**params):
    return _fixture_result("check_mesh_asset", params)


def _worn(services, character, name):
    garment = typed_child(services, character.basemesh, name, "Clothes")
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=0.6)
    mesh = bpy.data.meshes.new(name)
    builder.to_mesh(mesh)
    builder.free()
    garment.data = mesh
    garment.location = (0.0, 0.0, 1.0)
    group = garment.vertex_groups.new(name="body")
    group.add(range(8), 1.0, "ADD")
    bpy.context.view_layer.update()
    return garment


def _loose(name):
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=0.5)
    mesh = bpy.data.meshes.new(name)
    builder.to_mesh(mesh)
    builder.free()
    blender_object = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(blender_object)
    bpy.context.view_layer.update()
    return blender_object


def _remove(blender_object):
    mesh = blender_object.data
    bpy.data.objects.remove(blender_object, do_unlink=True)
    bpy.data.meshes.remove(mesh)


def test_every_section_is_answered_and_the_validator_is_not_the_answer():
    services = services_or_skip()
    with Character() as character:
        garment = _worn(services, character, "Human.full")
        answer = _result(name=garment.name)
        assert answer["found"] is True and answer["ready"] is True, answer["message"]
        assert answer["subject_name"] == garment.name
        assert answer["basemesh_name"] == character.basemesh.name
        assert answer["basemesh_resolved_by"] == "relative"
        assert answer["object_type"] == "Clothes"
        assert answer["requested_sections"] == list(bridge_module(
            "commands.check_mesh_asset").SECTIONS)
        assert "all_checks_ok" in answer["validator"], "at the validator's own top level"
        assert "all_checks_ok" not in answer, "and not at the answer's, where it would be mistaken"
        assert answer["components"]["applies"] is True
        assert answer["uv"]["applies"] is False, "a bmesh cube has no UV map"
        assert answer["textures"] == []
        assert answer["metadata"]["general"]["values"]["object_type"] == {
            "value": "Clothes", "set": True}
        assert answer["write_state"]["delete_group"]["exists_on_basemesh"] is False


def test_a_section_left_out_is_null_and_is_not_measured(monkeypatch):
    services = services_or_skip()
    report = bridge_module("shared.mesh_asset_report")

    def unwanted(*_arguments):
        raise AssertionError("this section was not asked for")

    monkeypatch.setattr(report, "validator", unwanted)
    monkeypatch.setattr(report, "component_report", unwanted)
    with Character() as character:
        garment = _worn(services, character, "Human.narrow")
        answer = _result(name=garment.name, sections=["textures"])
        assert answer["requested_sections"] == ["textures"]
        assert answer["textures"] == []
        for section in ("validator", "components", "uv", "metadata", "write_state"):
            assert answer[section] is None, section


def test_nothing_is_left_behind_by_a_call():
    """The promise an agent relies on to call this after every change."""
    services = services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        garment = _worn(services, character, "Human.unchanged")
        delete = basemesh.vertex_groups.new(name="Delete.unchanged")
        delete.add([0, 1, 2], 1.0, "ADD")
        mask = basemesh.modifiers.new("Delete.unchanged", "MASK")
        mask.vertex_group = "Delete.unchanged"
        mask.invert_vertex_group = True
        bpy.context.view_layer.objects.active = garment
        garment.select_set(True)
        basemesh.select_set(False)

        objects = sorted(o.name for o in bpy.data.objects)
        meshes = sorted(m.name for m in bpy.data.meshes)
        modifiers = [(m.name, m.show_viewport) for m in basemesh.modifiers]
        answer = _result(name=garment.name)
        assert answer["found"] is True
        assert sorted(o.name for o in bpy.data.objects) == objects
        assert sorted(m.name for m in bpy.data.meshes) == meshes
        assert [(m.name, m.show_viewport) for m in basemesh.modifiers] == modifiers
        assert bpy.context.view_layer.objects.active == garment
        assert garment.select_get() is True
        assert basemesh.select_get() is False


def test_mixed_faces_fail_the_validator_and_everything_else_is_still_measured():
    services = services_or_skip()
    with Character() as character:
        garment = typed_child(services, character.basemesh, "Human.mixed", "Clothes")
        mesh = bpy.data.meshes.new("Human.mixed")
        mesh.from_pydata([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1), (2, 0, 1)], [],
                         [(0, 1, 2, 3), (1, 4, 2)])
        mesh.update()
        garment.data = mesh
        bpy.context.view_layer.update()
        answer = _result(name=garment.name)
        assert answer["validator"]["all_faces_same_type"] is False
        assert answer["validator"]["all_checks_ok"] is False
        assert answer["components"]["applies"] is True, "MPFB returned early and this does not"
        assert answer["components"]["rows"][0]["faces"] == 2


def test_viewport_subdivision_is_reported_and_warned_about():
    services = services_or_skip()
    with Character() as character:
        garment = _worn(services, character, "Human.subdivided")
        subdivision = garment.modifiers.new("Subdivision", "SUBSURF")
        subdivision.levels = 1
        subdivision.render_levels = 2
        bpy.context.view_layer.update()
        answer = _result(name=garment.name, sections=["components", "write_state"])
        assert answer["write_state"]["subdiv_viewport_levels"] == 1
        assert answer["write_state"]["subdiv_render_levels"] == 2
        assert answer["components"]["subdiv_levels"] == 1
        assert answer["components"]["rows"][0]["faces"] == 24, "what was measured, not the six"
        assert any("subdivision" in warning for warning in answer["warnings"])


def test_a_mesh_in_edit_mode_is_answered_and_says_what_that_costs():
    """Safe at any point is the promise, and Blender gives Python no UV data here."""
    services = services_or_skip()
    with Character() as character:
        garment = _worn(services, character, "Human.editing")
        garment.data.uv_layers.new(name="UVMap")
        bpy.context.view_layer.objects.active = garment
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            answer = _result(name=garment.name)
            assert answer["found"] is True, answer["message"]
            assert answer["uv"]["applies"] is False
            assert any("EDIT mode" in warning for warning in answer["warnings"])
            assert garment.mode == "EDIT", "left where it was"
        finally:
            bpy.context.view_layer.objects.active = garment
            bpy.ops.object.mode_set(mode="OBJECT")


def test_a_mesh_with_no_character_finds_the_only_body():
    services_or_skip()
    draft = _loose("draft_no_character")
    try:
        with Character() as character:
            for blender_object in bpy.context.selected_objects:
                blender_object.select_set(False)
            answer = _result(name=draft.name)
            assert answer["found"] is True, answer["message"]
            assert answer["basemesh_name"] == character.basemesh.name
            assert answer["basemesh_resolved_by"] == "only_basemesh"
            assert answer["object_type"] is None, "not marked as anything yet, which is allowed"
    finally:
        _remove(draft)


def test_a_mesh_with_two_possible_bodies_is_refused_until_one_is_selected_or_named():
    services_or_skip()
    draft = _loose("draft_two_bodies")
    try:
        with Character() as first:
            with Character() as second:
                for blender_object in bpy.context.selected_objects:
                    blender_object.select_set(False)
                refused = _result(name=draft.name)
                assert refused["found"] is True
                assert refused["blocked_by"] == "basemesh_ambiguous"
                assert refused["candidates"] == sorted([first.basemesh.name, second.basemesh.name])

                second.basemesh.select_set(True)
                selected = _result(name=draft.name, sections=["write_state"])
                assert selected["basemesh_name"] == second.basemesh.name
                assert selected["basemesh_resolved_by"] == "selection"
                second.basemesh.select_set(False)

                named = _result(name=draft.name, basemesh=first.basemesh.name,
                                sections=["write_state"])
                assert named["basemesh_name"] == first.basemesh.name
                assert named["basemesh_resolved_by"] == "argument"
    finally:
        _remove(draft)


def test_the_refusals():
    services_or_skip()
    assert _result(name="no such object")["blocked_by"] == "subject_not_found"
    assert _result(name="no such object")["found"] is False
    with Character() as character:
        assert _result(name=character.basemesh.name)["blocked_by"] == "subject_is_basemesh"
        draft = _loose("draft_refusals")
        try:
            assert _result(name=draft.name, basemesh="no such")["blocked_by"] == "basemesh_not_found"
            assert _result(name=draft.name, basemesh=draft.name)["blocked_by"] == "not_a_basemesh"
            unknown = _result(name=draft.name, sections=["normals"])
            assert unknown["blocked_by"] == "unknown_section"
            assert "uv" in unknown["known_sections"]
        finally:
            _remove(draft)
    empty = bpy.data.objects.new("an_empty_asset", None)
    bpy.context.collection.objects.link(empty)
    try:
        assert _result(name="an_empty_asset")["blocked_by"] == "not_a_mesh"
    finally:
        bpy.data.objects.remove(empty, do_unlink=True)


def test_a_mesh_with_no_body_in_the_file_is_refused():
    services = services_or_skip()
    assert not any(services["ObjectService"].object_is_basemesh(o) for o in bpy.data.objects), \
        "an earlier test left a character behind"
    draft = _loose("draft_no_body")
    try:
        assert _result(name=draft.name)["blocked_by"] == "basemesh_not_found"
    finally:
        _remove(draft)
