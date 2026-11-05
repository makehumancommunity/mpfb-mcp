"""
``generate_delete_group`` against a real MPFB, on a real character.

**The garment is a real one**, extracted from a helper group as MakeClothes' "Extract clothes" does,
so that it fits as a draft fits. What the numbers should be is ``bbb_shared/delete_group_test.py``'s,
on meshes whose answers are known, and whether it holds on the gi is the request's own live check.
What is claimed here is what a call does to a ``.blend``: a ``dry_run`` nothing, a run keeps the group
it found once and only once, and a helper vertex is never added.
"""

import sys

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import mpfb_root
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip

GROUP = "delete"
HELPER_GROUP = "helper-tights"


def _result(params):
    return _fixture_result("generate_delete_group", params)


def _members(body, name):
    index = body.vertex_groups[name].index
    return sorted(vertex.index for vertex in body.data.vertices
                  if any(element.group == index for element in vertex.groups))


def _extracted(services, basemesh, name="BridgeTestDeleteGroupMesh"):
    """A draft from a helper group, as MakeClothes' Extract clothes makes one."""
    before = set(blender_object.name for blender_object in bpy.data.objects)
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    services["ObjectService"].extract_vertex_group_to_new_object(basemesh, HELPER_GROUP)
    mesh = next(blender_object for blender_object in bpy.data.objects
                if blender_object.name not in before)
    mesh.name = name
    bpy.ops.object.select_all(action="DESELECT")
    for blender_object in selected:
        blender_object.select_set(True)
    bpy.context.view_layer.objects.active = active
    return mesh


@pytest.fixture(name="draft")
def _draft():
    """A character and a garment extracted from it, the garment a little off the skin."""
    services = services_or_skip()
    with Character() as character:
        mesh = _extracted(services, character.basemesh)
        yield (character.basemesh, mesh)


def _call(body, mesh, **params):
    params.setdefault("delete_group", GROUP)
    return _result(dict(name=mesh.name, basemesh=body.name, **params))


def _refused(reason, **params):
    answer = _result(params)
    assert answer["blocked_by"] == reason, answer
    assert answer["performed"] is False
    return answer


def _highest_skin(body):
    """The top of the head, which no garment extracted from the tights covers."""
    return max(_members(body, "body"), key=lambda index: body.data.vertices[index].co.z)


def _group_state(body):
    return [(group.name, _members(body, group.name)) for group in body.vertex_groups
            if group.name.startswith(GROUP)]


def test_a_dry_run_reports_everything_and_changes_nothing(draft):
    body, mesh = draft
    body.vertex_groups.new(name=GROUP).add([0, 1, 2], 1.0, "REPLACE")
    active = body.vertex_groups.active_index
    before = _group_state(body)
    modifiers = [modifier.name for modifier in body.modifiers]
    answer = _call(body, mesh, dry_run=True)
    assert answer["ready"] is True, answer["message"]
    assert answer["generated"] is False and answer["performed"] is False
    assert answer["vertices_before"] == 3
    assert answer["vertices_after"] > 3
    assert answer["original_kept_as"] is None
    assert answer["message"].startswith("Would generate")
    assert _group_state(body) == before
    assert body.vertex_groups.active_index == active
    assert [modifier.name for modifier in body.modifiers] == modifiers


def test_a_run_writes_the_group_and_answers_what_it_wrote(draft):
    body, mesh = draft
    answer = _call(body, mesh)
    assert answer["generated"] is True and answer["performed"] is True, answer["message"]
    assert answer["group_created"] is True
    members = _members(body, GROUP)
    assert len(members) == answer["vertices_after"] == answer["added"] > 0
    assert answer["vertices_before"] == 0 and answer["removed"] == 0
    assert answer["original_kept_as"] == GROUP + ".original"
    assert _members(body, GROUP + ".original") == []
    assert answer["delete_group_resolved_by"] == "argument"
    assert answer["basemesh_resolved_by"] == "argument"
    assert isinstance(answer["masked_skin_still_visible"], int)
    assert isinstance(answer["unmasked_skin_under_garment"], int)
    assert answer["openings"], "a garment extracted from a helper group is open"
    assert answer["openings_total"] == len(answer["openings"])
    for row in answer["openings"]:
        assert row["kind"] in ("trunk", "cuff", "hem", "covered")
        assert row["reason"]
        assert set(row["centre"]) == {"x", "y", "z"}


def test_a_helper_vertex_is_never_added(draft):
    body, mesh = draft
    _call(body, mesh)
    skin = set(_members(body, "body"))
    assert set(_members(body, GROUP)) <= skin


def test_merge_keeps_what_was_there_before_the_first_run_across_runs(draft):
    body, mesh = draft
    # A member the garment does not cover, so that only "keep" explains its staying.
    head = _highest_skin(body)
    body.vertex_groups.new(name=GROUP).add([head], 1.0, "REPLACE")
    first = _call(body, mesh)
    assert head in _members(body, GROUP)
    assert _members(body, GROUP + ".original") == [head]
    assert first["vertices_before"] == 1
    written = _members(body, GROUP)

    second = _call(body, mesh)
    assert _members(body, GROUP) == written, "the same mesh gives the same group"
    assert _members(body, GROUP + ".original") == [head], "kept once, and only once"
    assert second["added"] == 0 and second["removed"] == 0
    assert second["vertices_before"] == len(written)
    assert second["group_created"] is False


def test_replace_starts_empty_and_still_keeps_the_original(draft):
    body, mesh = draft
    head = _highest_skin(body)
    body.vertex_groups.new(name=GROUP).add([head], 1.0, "REPLACE")
    answer = _call(body, mesh, mode="replace")
    assert head not in _members(body, GROUP)
    assert answer["removed"] == 1
    assert _members(body, GROUP + ".original") == [head]
    # And merge afterwards still starts from what was kept, rather than from the replacement.
    _call(body, mesh, mode="merge")
    assert head in _members(body, GROUP)


def test_it_adds_no_modifier_and_says_whether_one_is_there(draft):
    body, mesh = draft
    names = [modifier.name for modifier in body.modifiers]
    answer = _call(body, mesh)
    assert answer["mask_modifier_present"] is False
    assert [modifier.name for modifier in body.modifiers] == names
    mask = body.modifiers.new(GROUP, "MASK")
    mask.vertex_group = GROUP
    assert _call(body, mesh)["mask_modifier_present"] is True


def test_a_garment_with_a_modifier_is_no_obstacle(draft):
    body, mesh = draft
    plain = _call(body, mesh, dry_run=True)
    subdivision = mesh.modifiers.new("Subdivision", "SUBSURF")
    subdivision.levels = 1
    answer = _call(body, mesh, dry_run=True)
    assert answer["vertices_after"] == plain["vertices_after"], "it reads the stripped mesh"
    assert subdivision.show_viewport is True


def test_margins_override_a_kind_and_never_a_classification(draft):
    body, mesh = draft
    plain = _call(body, mesh, dry_run=True)
    wider = _call(body, mesh, dry_run=True, margins=dict(trunk=0.3, hem=0.3, cuff=0.3))
    assert wider["margins"] == dict(trunk=0.3, hem=0.3, cuff=0.3)
    assert wider["vertices_after"] < plain["vertices_after"]
    assert ([row["kind"] for row in wider["openings"]]
            == [row["kind"] for row in plain["openings"]])
    partly = _call(body, mesh, dry_run=True, margins=dict(hem=0.3))
    assert partly["margins"]["hem"] == 0.3
    assert partly["margins"]["cuff"] == plain["margins"]["cuff"]


def test_the_group_defaults_to_the_garments_own(draft):
    body, mesh = draft
    properties = sys.modules[mpfb_root() + ".ui.create_assets.makeclothes"].MakeClothesObjectProperties
    properties.set_value("delete_group", "MyGroup", entity_reference=mesh)
    answer = _result(dict(name=mesh.name, basemesh=body.name, dry_run=True))
    assert answer["delete_group"] == "MyGroup"
    assert answer["delete_group_resolved_by"] == "object"
    assert not any("mpfb_write_mesh_asset" in warning for warning in answer["warnings"])
    named = _result(dict(name=mesh.name, basemesh=body.name, delete_group="Other", dry_run=True))
    assert any("mpfb_write_mesh_asset" in warning for warning in named["warnings"]), named["warnings"]


def test_the_written_group_reaches_the_mhclo_and_a_loaded_asset_masks_what_was_counted(draft, tmp_path):
    body, mesh = draft
    answer = _call(body, mesh)
    reading, _refusal = bridge_module("shared.delete_group").read(body, mesh)
    expected = bridge_module("shared.delete_group").as_loaded(
        reading, reading.members(body.vertex_groups[GROUP].index))
    module = bridge_module("export_directory")
    module.set_command_line(str(tmp_path))
    try:
        written = _fixture_result("write_mesh_asset", dict(
            name=mesh.name, basemesh=body.name, asset_name="my_gi", object_type="Clothes",
            destination="export_directory", delete_group=GROUP, license="CC0", author="Somebody"))
    finally:
        module.set_command_line(None)
    assert written["written"] is True, written["message"]
    assert written["delete_vertices"] == answer["vertices_after"]
    assert written["delete_group"] == GROUP
    with Character() as second:
        added = _fixture_result("add_asset", dict(
            name=second.basemesh.name, path=written["path"], object_type="Clothes"))
        assert added["added"] is True, added["message"]
        loaded = _members(second.basemesh, added["delete_group"] if added.get("delete_group")
                          else next(group.name for group in second.basemesh.vertex_groups
                                    if group.name.endswith("my_gi")))
    assert loaded == expected.nonzero()[0].tolist(), (
        "what is counted is what the next character gets, the written file's duplicates included")


def test_the_subject_and_the_group_can_be_refused(draft):
    body, mesh = draft
    _refused("subject_not_found", name="NoSuchObject")
    _refused("subject_is_basemesh", name=body.name)
    _refused("not_a_basemesh", name=mesh.name, basemesh=mesh.name)
    answer = _refused("group_is_a_kept_original", name=mesh.name, basemesh=body.name,
                      delete_group="delete.original")
    assert "undo" in answer["message"]
    _refused("group_name_too_long", name=mesh.name, basemesh=body.name, delete_group="x" * 60)
    _refused("invalid_margins", name=mesh.name, basemesh=body.name, margins=dict(neck=0.1))
    _refused("invalid_margins", name=mesh.name, basemesh=body.name, margins=dict(hem=-1.0))


def test_a_body_with_no_joint_groups_is_refused():
    services = services_or_skip()
    with Character() as character:
        body = character.basemesh
        mesh = _extracted(services, body)
        for group in list(body.vertex_groups):
            if group.name.startswith("joint-"):
                body.vertex_groups.remove(group)
        _refused("no_joint_groups", name=mesh.name, basemesh=body.name, delete_group=GROUP)
        body.vertex_groups.remove(body.vertex_groups["body"])
        _refused("no_body_group", name=mesh.name, basemesh=body.name, delete_group=GROUP)


def test_a_posed_body_is_refused_naming_the_way_back_and_a_turned_one_is_not():
    services = services_or_skip()
    with Character() as character:
        body = character.basemesh
        rig = rigged_character(services, character, "default")
        mesh = _extracted(services, body)
        at_rest = _call(body, mesh, dry_run=True)
        assert at_rest["ready"] is True, at_rest["message"]
        rig.rotation_euler = (0.0, 0.0, 1.5708)
        bpy.context.view_layer.update()
        mesh.parent = body
        turned = _call(body, mesh, dry_run=True)
        assert turned["ready"] is True, turned["message"]
        assert turned["vertices_after"] == at_rest["vertices_after"]
        rig.rotation_euler = (0.0, 0.0, 0.0)
        bone = rig.pose.bones["upperleg01.L"]
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (1.2, 0.0, 0.0)
        try:
            answer = _refused("rig_not_at_rest", name=mesh.name, basemesh=body.name,
                              delete_group=GROUP)
            assert answer["rig_name"] == rig.name
            assert "upperleg01.L" in answer["posed_bones"]
            assert "mpfb_reset_pose" in answer["message"]
        finally:
            bone.rotation_euler = (0.0, 0.0, 0.0)


def test_nothing_under_the_garment_is_a_warning_and_not_a_refusal(draft):
    body, mesh = draft
    mesh.location = (5.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    answer = _call(body, mesh, dry_run=True)
    assert answer["ready"] is True
    assert answer["vertices_after"] == 0
    assert any("under this garment" in warning for warning in answer["warnings"])
