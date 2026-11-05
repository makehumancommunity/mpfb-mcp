"""
``check_intersections`` against a real MPFB, on a real character.

What is counted is ``bbb_shared/mesh_overlap_test.py``'s, on cubes. This is what only a
character can show: **helper geometry is never counted**, and **a delete group's mask
changes ``face_pairs`` and not ``face_pairs_unmasked``**. It also covers which pairs a
call measures, and the cap, whose totals must cover what it cuts.
"""

import bmesh
import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip
from .._fixtures import typed_child


def _result(**params):
    return _fixture_result("check_intersections", params)


def _prop(name, location, size=0.2):
    """A cube belonging to no character."""
    mesh = bpy.data.meshes.new(name)
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=size)
    builder.to_mesh(mesh)
    builder.free()
    blender_object = bpy.data.objects.new(name, mesh)
    blender_object.location = location
    bpy.context.collection.objects.link(blender_object)
    bpy.context.view_layer.update()
    return blender_object


@pytest.fixture(name="props")
def _props():
    built = []
    yield built
    for blender_object in built:
        mesh = blender_object.data
        bpy.data.objects.remove(blender_object, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def _worn(services, character, name, location=(0.0, 0.0, 1.0), size=0.6):
    """A cube typed as a garment and parented to the basemesh, through the chest by default."""
    garment = typed_child(services, character.basemesh, name, "Clothes")
    builder = bmesh.new()
    bmesh.ops.create_cube(builder, size=size)
    mesh = bpy.data.meshes.new(name)
    builder.to_mesh(mesh)
    builder.free()
    garment.data = mesh
    garment.location = location
    bpy.context.view_layer.update()
    return garment


def _masked_by_delete_group(basemesh, garment_box=(-0.4, 0.4)):
    """A delete group and its mask over the torso, as MPFB's update_delete_group() adds them."""
    group = basemesh.vertex_groups.new(name="Delete.test")
    low, high = garment_box
    indices = [vertex.index for vertex in basemesh.data.vertices
               if 0.7 <= vertex.co.z <= 1.3 and low <= vertex.co.x <= high]
    group.add(indices, 1.0, "ADD")
    mask = basemesh.modifiers.new("Delete.test", "MASK")
    mask.vertex_group = "Delete.test"
    mask.invert_vertex_group = True
    bpy.context.view_layer.update()
    return mask


def test_a_body_alone_has_no_pairs():
    services_or_skip()
    with Character() as character:
        alone = _result(name=character.basemesh.name)
        assert alone["found"] is True and alone["ready"] is True, alone["message"]
        assert alone["pairs"] == [], "one mesh, and no include_self, is no pair"
        assert alone["pairs_measured"] == 0
        assert alone["pairs_truncated"] is False


def test_a_delete_groups_mask_changes_one_count_and_not_the_other():
    services = services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        garment = _worn(services, character, "Human.chest_box")
        before = _result(name=basemesh.name)["pairs"][0]
        assert before["face_pairs"] > 0
        assert before["face_pairs"] == before["face_pairs_unmasked"], \
            "no delete group yet, so the second count has nothing to differ by"

        mask = _masked_by_delete_group(basemesh)
        after = _result(name=garment.name)["pairs"][0]
        assert after["face_pairs"] < before["face_pairs"], "the mask hid skin from the first count"
        assert after["face_pairs_unmasked"] == before["face_pairs_unmasked"], \
            "and the second count cannot see a mask"
        assert mask.show_viewport is True, "put back"


def test_helper_geometry_is_never_counted():
    """Against the same character with the helper mask off, by the body's own triangles."""
    services_or_skip()
    overlap = bridge_module("shared.mesh_overlap")
    with Character() as character:
        basemesh = character.basemesh
        with_helpers_hidden = overlap.read_all([basemesh], {basemesh.name})[0][basemesh.name]
        assert with_helpers_hidden.unmasked is with_helpers_hidden.masked, \
            "the helper mask alone is not a reason to read the body twice"

        mask = next(m for m in basemesh.modifiers if overlap.is_helper_mask(m))
        full = len(basemesh.data.loop_triangles)
        assert len(with_helpers_hidden.masked.triangles) < full, "helpers are hidden from the read"

        _masked_by_delete_group(basemesh)
        reading = overlap.read_all([basemesh], {basemesh.name})[0][basemesh.name]
        assert len(reading.unmasked.triangles) == len(with_helpers_hidden.masked.triangles), \
            "turning the masks off leaves the helpers hidden"
        assert mask.show_viewport is True


def test_a_proxied_bodys_hidden_skin_is_seen_unmasked_only():
    """The inverted mask on ``body`` hides the skin, so the body reads as nothing until it is off."""
    services = services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        _worn(services, character, "Human.proxied_box")
        hide = basemesh.modifiers.new("Hide base mesh", "MASK")
        hide.vertex_group = "body"
        hide.invert_vertex_group = True
        bpy.context.view_layer.update()
        row = _result(name=basemesh.name)["pairs"][0]
        assert row["face_pairs"] == 0, "nothing of the body is drawn"
        assert row["min_distance"] is None, "and nothing drawn has no distance"
        assert row["face_pairs_unmasked"] > 0
        assert hide.show_viewport is True


def test_a_held_prop_is_a_subject_of_one_mesh(props):
    services_or_skip()
    # Before the character, whose fixture removes whatever appeared while it lived.
    props.append(_prop("held_prop", (0.0, 0.0, 1.0)))
    with Character() as character:
        answer = _result(name="held_prop", other=character.basemesh.name)
        assert answer["subject_name"] == "held_prop"
        assert answer["other_name"] == character.basemesh.name
        assert answer["pairs_measured"] == 1
        row = answer["pairs"][0]
        assert {row["object_name"], row["other_object_name"]} == {
            "held_prop", character.basemesh.name}
        assert "face_pairs_unmasked" in row, "a body is one side of it"


def test_with_other_only_pairs_across_the_two_are_measured():
    services = services_or_skip()
    with Character() as first:
        one = _worn(services, first, "Human.first_a", location=(0.0, 0.0, 1.0))
        two = _worn(services, first, "Human.first_b", location=(5.0, 0.0, 1.0))
        with Character() as second:
            answer = _result(name=first.basemesh.name, other=second.basemesh.name)
            assert answer["pairs_measured"] == 3, "three in the first and one in the second"
            named = {frozenset((row["object_name"], row["other_object_name"]))
                     for row in answer["pairs"]}
            assert frozenset((one.name, two.name)) not in named, "that pair is inside the first"


def test_every_pair_inside_a_family_each_once_and_self_on_request():
    services = services_or_skip()
    with Character() as character:
        _worn(services, character, "Human.family_a")
        _worn(services, character, "Human.family_b")
        answer = _result(name=character.basemesh.name)
        assert answer["pairs_measured"] == 3, "body and two garments have three pairs"
        with_self = _result(name=character.basemesh.name, include_self=True)
        assert with_self["pairs_measured"] == 6
        self_rows = [row for row in with_self["pairs"]
                     if row["object_name"] == row["other_object_name"]]
        assert len(self_rows) == 3
        assert all(row["min_distance"] is None for row in self_rows)


def test_the_totals_cover_what_the_cap_cuts(monkeypatch):
    services = services_or_skip()
    command = bridge_module("commands.check_intersections")
    monkeypatch.setattr(command, "MAX_ROWS", 1)
    with Character() as character:
        _worn(services, character, "Human.cap_touching")
        _worn(services, character, "Human.cap_far", location=(20.0, 0.0, 1.0))
        answer = _result(name=character.basemesh.name)
        assert answer["pairs_measured"] == 3
        assert answer["pairs_truncated"] is True
        assert len(answer["pairs"]) == 1
        assert answer["pairs"][0]["face_pairs"] > 0, "largest first, so what is cut is the least"
        assert answer["pairs_clear"] >= 1, "counted over the cut ones too"
        assert answer["closest_pair"]["min_distance"] == 0.0


def test_a_row_sorts_on_its_larger_count_rather_than_the_masked_one():
    """A pair a mask hides entirely must not be buried by a pair with a few pairs showing."""
    services = services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        _worn(services, character, "Human.sort_hidden", size=0.7)
        small_a = _worn(services, character, "Human.sort_a", location=(2.0, 0.0, 1.0), size=0.2)
        _worn(services, character, "Human.sort_b", location=(2.05, 0.0, 1.0), size=0.2)
        _masked_by_delete_group(basemesh, garment_box=(-1.0, 1.0))
        rows = _result(name=small_a.name)["pairs"]
        assert rows[0]["object_name"] == basemesh.name
        assert rows[0]["face_pairs_unmasked"] > rows[1]["face_pairs"]


def test_the_refusals():
    services_or_skip()
    missing = _result(name="no such object")
    assert missing["found"] is False
    assert missing["blocked_by"] == "subject_not_found"
    with Character() as character:
        other = _result(name=character.basemesh.name, other="no such object")
        assert other["blocked_by"] == "other_not_found"
        assert other["found"] is True
        assert other["ready"] is False
    empty = bpy.data.objects.new("an_empty", None)
    bpy.context.collection.objects.link(empty)
    try:
        answer = _result(name="an_empty")
        assert answer["blocked_by"] == "no_meshes"
    finally:
        bpy.data.objects.remove(empty, do_unlink=True)


def test_an_unmeasurable_family_member_is_named():
    services = services_or_skip()
    with Character() as character:
        garment = _worn(services, character, "Human.gone")
        garment.hide_viewport = True
        bpy.context.view_layer.update()
        answer = _result(name=character.basemesh.name)
        assert answer["not_measured"] == [{"object_name": "Human.gone", "reason": "not_evaluated"}]
        assert answer["pairs_measured"] == 0


def test_the_contract_refuses_a_bad_argument():
    services_or_skip()
    envelope = dispatch("check_intersections", {"include_self": "yes"})
    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
