"""
``place_character`` against a real MPFB: one call places a character, and says what it broke.

What is asserted is [FR 045](../../../../feature-requests/done/045-placing-a-character/README.md)'s
list, each against a real character rather than a bare object (which is
``bbb_shared/placement_test.py``'s):

- **everything that belongs to the character moves**, on no rig, the default
  rig and a generated Rigify rig - the last with its meta-rig hidden beside it,
  which must come along or the next refit builds at the old position;
- ``face_toward`` a point and an object, in the same call as a ``position``,
  and its two refusals;
- **the character frame makes posing independent of placement**: ``get_pose``
  answers the same about a posed character before and after a move, asserted
  rather than assumed;
- ``restore_with`` puts the character back exactly;
- an external parent left alone, a tilted root refused a turn and allowed a move;
- the ``footprint`` against the evaluated vertices of the body and its assets;
- ``subrigs_broken`` on a character carrying the sub-rig fixture, from this
  command and from ``add_asset``: **measured, and not caused by a move**. The
  request expected every sub-rig to break whenever its character stood away
  from the origin; the live check found that a move breaks none, that equipping
  one on a placed character breaks it wherever the character goes after, and
  that ``refit_human`` re-binds it. That sequence is asserted here, on the
  fixture, so it does not rest on one session's measurement of ``ponytail01``.
"""

import math
import os

import bpy

from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import redirected_locations
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip
from .._fixtures import supplied_resolution
from .._fixtures import write_loadable_mhclo
from .._fixtures import write_subrigged_mhclo

COMMAND = "place_character"


def _result(params):
    return _fixture_result(COMMAND, params)


def _world(blender_object):
    return blender_object.matrix_world.copy()


def _close(first, second, tolerance=1e-5):
    return all(abs(first[row][column] - second[row][column]) <= tolerance
               for row in range(4) for column in range(4))


def _family_worlds(root):
    """Every object below ``root``, by name, with its world matrix."""
    found = {}
    pending = [root]
    while pending:
        parent = pending.pop()
        found[parent.name] = _world(parent)
        pending.extend(child for child in bpy.data.objects if child.parent == parent)
    return found


def _evaluated_box(root):
    """The footprint's definition, computed here by plain bpy rather than by the module."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    pending = [root]
    while pending:
        blender_object = pending.pop()
        pending.extend(child for child in bpy.data.objects if child.parent == blender_object)
        if blender_object.type != "MESH" or not blender_object.visible_get():
            continue
        evaluated = blender_object.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        points.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
        evaluated.to_mesh_clear()
    return ([min(point[axis] for point in points) for axis in range(3)],
            [max(point[axis] for point in points) for axis in range(3)])


def _garment(services, character, root_directory, writer=write_loadable_mhclo, name="spike"):
    mhclo = writer(os.path.join(str(root_directory), "clothes", name, name + ".mhclo"))
    with redirected_locations(services, user_data=str(root_directory)):
        equipped = _fixture_result("add_asset", {
            "name": character.basemesh.name, "path": mhclo, "object_type": "Clothes"})
    assert equipped["added"] is True, equipped["message"]
    return equipped


def test_an_unrigged_character_is_moved_and_turned_by_its_body():
    """commands.place_character on a character with no rig"""
    services_or_skip()
    with Character() as character:
        result = _result({"name": character.basemesh.name,
                          "position": {"x": 2.0, "y": 1.0}, "facing": 90.0})

        assert result["performed"] is True, result["message"]
        assert result["placed"] is True
        assert result["root_name"] == character.basemesh.name
        assert result["position_before"] == {"x": 0.0, "y": 0.0, "z": 0.0}
        assert result["position_after"] == {"x": 2.0, "y": 1.0, "z": 0.0}
        assert result["facing_before"] == 0.0
        assert result["facing_after"] == 90.0
        assert result["moved_with"] == []
        assert result["external_parent_name"] is None
        assert result["character_frame"]["origin"] == [2.0, 1.0, 0.0]
        assert result["character_frame"]["forward"] == [1.0, 0.0, 0.0], \
            "turned 90 degrees counter-clockwise, -Y becomes +X"
        assert result["subrigs_broken"] == []


def test_a_key_left_out_of_position_keeps_its_value():
    """commands.place_character with only x"""
    services_or_skip()
    with Character() as character:
        _result({"name": character.basemesh.name, "position": {"x": 1.0, "y": 2.0, "z": 0.5}})
        result = _result({"name": character.basemesh.name, "position": {"x": -1.0}})
        assert result["position_after"] == {"x": -1.0, "y": 2.0, "z": 0.5}
        assert result["facing_after"] == 0.0, "a move alone does not turn"


def test_a_rigged_character_is_moved_by_its_rig_and_everything_follows():
    """commands.place_character on a dressed character with the default rig"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "default")
        garment = _garment(services, character, os.path.join(bpy.app.tempdir, "place-rigged"))
        locals_before = {name: bpy.data.objects[name].matrix_basis.copy()
                         for name in (character.basemesh.name, garment["asset_object_name"])}

        result = _result({"name": garment["asset_object_name"],
                          "position": {"x": -3.0, "y": 2.0}, "facing": 30.0})

        assert result["root_name"] == rig.name, "the rig is the root, whatever was named"
        assert result["basemesh_name"] == character.basemesh.name
        for name, matrix in locals_before.items():
            assert _close(bpy.data.objects[name].matrix_basis, matrix), \
                "{:s} moves with its parent, not by a write of its own".format(name)
        assert result["position_after"] == {"x": -3.0, "y": 2.0, "z": 0.0}
        assert result["facing_after"] == 30.0


def test_a_hidden_metarig_moves_with_the_generated_rig():
    """commands.place_character on a generated human_toes rig, meta-rig hidden"""
    services = services_or_skip()
    with Character() as character:
        generated = rigged_character(services, character, "generated:human_toes")
        metarig = services["ObjectService"].find_rigify_metarig_by_rig(generated)
        assert metarig is not None and metarig.hide_viewport, "the fixture hides the meta-rig"
        offset = generated.matrix_world.inverted() @ metarig.matrix_world

        result = _result({"name": character.basemesh.name,
                          "position": {"x": 4.0, "y": -2.0}, "facing": -45.0})

        assert result["root_name"] == generated.name
        assert result["moved_with"] == [metarig.name]
        assert _close(generated.matrix_world.inverted() @ metarig.matrix_world, offset), \
            "the meta-rig must keep its place relative to the rig it generated"
        assert "moved with it" in result["message"]


def test_face_toward_a_point_is_computed_from_where_the_call_puts_it():
    """commands.place_character with a position and face_toward a point together"""
    services_or_skip()
    with Character() as character:
        result = _result({"name": character.basemesh.name, "position": {"x": 1.0, "y": 1.0},
                          "face_toward": {"x": 1.0, "y": 5.0}})
        assert result["facing_after"] == 180.0, \
            "a target in +Y of the new position is behind an unturned character"
        assert result["requested_face_toward"] == {"x": 1.0, "y": 5.0}


def test_face_toward_an_object_uses_its_world_location():
    """commands.place_character turned toward a camera parented under a moved empty"""
    services_or_skip()
    holder = bpy.data.objects.new("PlaceCameraHolder", None)
    camera = bpy.data.objects.new("PlaceCamera", bpy.data.cameras.new("PlaceCameraData"))
    for blender_object in (holder, camera):
        bpy.context.scene.collection.objects.link(blender_object)
    try:
        holder.location = (0.0, -5.0, 0.0)
        camera.parent = holder
        camera.location = (5.0, 0.0, 1.5)
        bpy.context.view_layer.update()
        with Character() as character:
            result = _result({"name": character.basemesh.name,
                              "face_toward": {"object": camera.name}})
            assert result["facing_after"] == 45.0, \
                "the camera is at world (5, -5): forward, -Y, turned 45 degrees toward +X"
            assert "toward 'PlaceCamera'" in result["message"]
    finally:
        for blender_object in (camera, holder):
            bpy.data.objects.remove(blender_object, do_unlink=True)


def test_face_toward_refusals_change_nothing():
    """commands.place_character toward a missing object, and toward a point overhead"""
    services_or_skip()
    with Character() as character:
        before = _world(character.basemesh)

        missing = _result({"name": character.basemesh.name, "position": {"x": 3.0},
                           "face_toward": {"object": "PlaceNoSuchCamera"}})
        assert missing["blocked_by"] == "face_toward_not_found"
        assert missing["performed"] is False
        assert missing["found"] is True

        overhead = _result({"name": character.basemesh.name, "position": {"x": 3.0},
                            "face_toward": {"x": 3.0, "y": 0.0}})
        assert overhead["blocked_by"] == "face_toward_has_no_direction"
        assert overhead["performed"] is False

        assert _close(_world(character.basemesh), before), "a refusal must write nothing"


def test_restore_with_puts_the_character_back_exactly():
    """commands.place_character twice, the second time with the first's restore_with"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "default")
        rig.location = (0.3, -0.7, 0.0)
        rig.rotation_euler = (0.0, 0.0, math.radians(12.5))
        bpy.context.view_layer.update()
        family_before = _family_worlds(rig)

        moved = _result({"name": rig.name, "position": {"x": 5.0, "y": 5.0}, "facing": 170.0})
        back = _result(moved["restore_with"]["mpfb_place_character"])

        assert back["performed"] is True
        for name, matrix in family_before.items():
            assert _close(bpy.data.objects[name].matrix_world, matrix), name
        assert back["restore_with"]["mpfb_place_character"]["facing"] == 170.0


def test_the_pose_reads_the_same_wherever_the_character_stands():
    """commands.get_pose before and after a move, on a posed default rig

    The character frame's claim, FR 041's requirement 3, asserted against a
    move rather than assumed: every posing answer is measured from the rig
    object, so placing the character changes nothing but the frame itself.
    """
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "default")
        posed = _fixture_result("set_pose_bones", {"name": rig.name, "bones": [
            {"bone": "upperarm01.L", "rotate_by": {"axis": {"forward": 1.0}, "degrees": -30.0}},
            {"bone": "spine03", "rotate_by": {"axis": {"up": 1.0}, "degrees": 15.0}}]})
        assert posed["performed"] is True, posed["message"]

        before = _fixture_result("get_pose", {"name": rig.name})
        _result({"name": rig.name, "position": {"x": 3.0, "y": -4.0, "z": 0.2}, "facing": 110.0})
        after = _fixture_result("get_pose", {"name": rig.name})

        assert before["posed_count"] > 0
        assert before["character_frame"] != after["character_frame"]
        for key in ("posed", "landmarks", "limbs", "at_rest", "posed_count"):
            assert before[key] == after[key], key


def test_an_external_parent_is_left_alone_and_named():
    """commands.place_character on a rig the user grouped under a turned empty"""
    services = services_or_skip()
    group = bpy.data.objects.new("PlaceGroup", None)
    bpy.context.scene.collection.objects.link(group)
    try:
        group.location = (10.0, 0.0, 0.0)
        group.rotation_euler = (0.0, 0.0, math.radians(90.0))
        with Character() as character:
            rig = rigged_character(services, character, "default")
            rig.parent = group
            bpy.context.view_layer.update()
            group_world = _world(group)

            result = _result({"name": rig.name, "position": {"x": 1.0, "y": 1.0, "z": 0.0},
                              "facing": 0.0})

            assert result["external_parent_name"] == group.name
            assert _close(_world(group), group_world)
            assert result["position_after"] == {"x": 1.0, "y": 1.0, "z": 0.0}, \
                "the values are world values, not the parent's"
            assert result["facing_after"] == 0.0
    finally:
        bpy.data.objects.remove(group, do_unlink=True)


def test_a_tilted_character_is_refused_a_turn_and_allowed_a_move():
    """commands.place_character on a basemesh tilted 10 degrees"""
    services_or_skip()
    with Character() as character:
        character.basemesh.rotation_euler = (math.radians(10.0), 0.0, 0.0)
        bpy.context.view_layer.update()
        before = _world(character.basemesh)
        euler_before = tuple(character.basemesh.rotation_euler)

        turned =_result({"name": character.basemesh.name, "position": {"x": 1.0},
                          "facing": 45.0})
        assert turned["blocked_by"] == "character_tilted"
        assert turned["performed"] is False
        assert _close(_world(character.basemesh), before), "nothing is written"

        moved = _result({"name": character.basemesh.name, "position": {"x": 1.0}})
        assert moved["performed"] is True
        assert moved["tilted"] is True
        assert tuple(character.basemesh.rotation_euler) == euler_before, \
            "a move alone keeps the rotation channels exactly"
        assert "facing" not in moved["restore_with"]["mpfb_place_character"], \
            "a turn would be refused on a tilted root, so the way back is a position alone"


def test_the_footprint_is_the_evaluated_body_and_its_assets():
    """commands.place_character's footprint against the evaluated vertices"""
    services = services_or_skip()
    with Character() as character:
        rigged_character(services, character, "default")
        _garment(services, character, os.path.join(bpy.app.tempdir, "place-footprint"))
        result = _result({"name": character.basemesh.name,
                          "position": {"x": 1.5, "y": -0.5}, "facing": 20.0})

        lowest, highest = _evaluated_box(bpy.data.objects[result["root_name"]])
        footprint = result["footprint"]
        for index, axis in enumerate(("x", "y", "z")):
            assert abs(footprint["min"][axis] - lowest[index]) <= 0.0006, axis
            assert abs(footprint["max"][axis] - highest[index]) <= 0.0006, axis
        assert abs(footprint["width"] - (highest[0] - lowest[0])) <= 0.0011
        assert abs(footprint["depth"] - (highest[1] - lowest[1])) <= 0.0011
        assert 1.0 < footprint["height"] < 2.5, "a default character is about 1.7 m tall"
        assert lowest[2] > -0.01, \
            "helper geometry hangs below the feet and must not be counted"


def test_a_subrig_is_broken_by_being_equipped_away_from_the_origin_not_by_a_move():
    """commands.add_asset, place_character and refit_human on garments carrying a sub-rig

    A sub-rig equipped at the origin survives any move; one equipped on a
    placed character is bound wrong and stays wrong at the origin; a refit
    re-binds it. The fixture's ``.mpfbskel`` is MPFB's own format, with
    ``ponytail01``'s one bone and one constraint.
    """
    services = services_or_skip()
    root_directory = os.path.join(bpy.app.tempdir, "place-subrig")
    with Character() as character:
        rig = rigged_character(services, character, "default")

        at_origin = _garment(services, character, root_directory,
                             writer=write_subrigged_mhclo, name="tail")
        assert at_origin["subrig_object_name"] is not None, \
            "the fixture's .mpfbskel must make MPFB build a sub-rig"
        assert at_origin["subrigs_broken"] == []

        moved = _result({"name": rig.name, "position": {"x": 2.0, "y": -1.0}, "facing": 70.0})
        assert moved["subrigs_broken"] == [], "a move breaks no sub-rig"

        placed = _garment(services, character, root_directory,
                          writer=write_subrigged_mhclo, name="braid")
        broken = placed["subrigs_broken"]
        assert [record["subrig_object_name"] for record in broken] == \
            [placed["subrig_object_name"]], "only the one equipped away from the origin"
        assert broken[0]["asset_object_name"] == placed["asset_object_name"]
        assert broken[0]["displacement"] > 0.5, broken
        assert "mpfb_refit_human" in placed["message"]

        back = _result(moved["restore_with"]["mpfb_place_character"])
        assert [record["subrig_object_name"] for record in back["subrigs_broken"]] == \
            [placed["subrig_object_name"]], "a move does not cure one either, origin included"
        assert "mpfb_refit_human re-binds" in back["message"]

        with redirected_locations(services, user_data=root_directory):
            refit = _fixture_result("refit_human", {"name": rig.name})
        assert refit["refit_performed"] is True, refit["message"]
        again = _result({"name": rig.name, "position": {"x": -3.0}, "facing": -40.0})
        assert again["subrigs_broken"] == [], "a refit re-binds it, and it then survives a move"


def test_an_empty_call_is_refused_by_the_far_side_too():
    """commands.place_character with nothing to do, and with a misshapen position"""
    services_or_skip()
    with Character() as character:
        nothing = _result({"name": character.basemesh.name})
        assert nothing["blocked_by"] == "invalid_arguments"
        assert nothing["performed"] is False

        misspelled = _result({"name": character.basemesh.name, "position": {"xx": 1.0}})
        assert misspelled["blocked_by"] == "invalid_arguments"
        assert "xx" in misspelled["message"]

        both = _result({"name": character.basemesh.name, "facing": 1.0,
                        "face_toward": {"x": 1.0, "y": 1.0}})
        assert both["blocked_by"] == "invalid_arguments"

        half_a_point = _result({"name": character.basemesh.name,
                                "face_toward": {"x": 1.0, "w": 2.0}})
        assert half_a_point["blocked_by"] == "invalid_arguments"
        assert "{'object': <a name>}" in half_a_point["message"]
        assert "w" in half_a_point["message"]

        an_object_and_a_point = _result({"name": character.basemesh.name,
                                         "face_toward": {"object": "Camera", "x": 1.0}})
        assert an_object_and_a_point["blocked_by"] == "invalid_arguments"


def test_nothing_is_borrowed():
    """commands.place_character leaves the selection and the active object alone"""
    services = services_or_skip()
    with Character() as character:
        bystander = bpy.data.objects.new("PlaceBystander", None)
        bpy.context.scene.collection.objects.link(bystander)
        try:
            services["ObjectService"].activate_blender_object(bystander)
            character.basemesh.select_set(False)
            _result({"name": character.basemesh.name, "position": {"y": 3.0}})
            assert bpy.context.view_layer.objects.active is bystander
            assert character.basemesh.select_get() is False
        finally:
            bpy.data.objects.remove(bystander, do_unlink=True)


def test_mpfb_being_unavailable_refuses_rather_than_half_placing():
    """commands.place_character against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch(COMMAND, {"position": {"x": 1.0}})
        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
