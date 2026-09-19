"""
``get_object_info`` against a real MPFB: three ``asset_info`` shapes, one walk.

The command's whole difficulty is that it answers a different question
depending on what the object turns out to be, and every one of those answers
has until now been checked only against ``tests/blender_stubs.py`` - a stub
scene written from the same reading of MPFB's source as the payload it was
checking. What is put to MPFB here:

- that ``ObjectService._SKELETON_TYPES`` and ``_MESH_ASSET_TYPES`` exist and are
  what the three shapes dispatch on;
- that ``find_related_objects()`` really yields the object it was asked about,
  which is why the subject is filtered out of its own relatives;
- that ``get_list_of_children()`` walks ``bpy.data.objects`` rather than the
  scene, which is why every entry carries ``in_current_scene``;
- that ``identify_material()`` answers ``"empty"`` for a missing material
  rather than raising, which is what lets ``material_type_of()`` compose
  without a guard;
- that a freshly created character really is a family - a basemesh with a set
  of relatives - rather than a single object with properties on it.

A bare ``create_human()`` character is the fixture throughout. It has no rig and
no clothes, so the skeleton and mesh-asset shapes are reached by asking about
objects this suite makes itself rather than by equipping anything: equipping is
stage 4's territory, and a read-only command's test should not be the first
place an asset is added.
"""

import bpy

from . import bridge_module
from ._fixtures import Character
from ._fixtures import dispatch
from ._fixtures import linked_plain_object
from ._fixtures import result
from ._fixtures import services_or_skip
from ._fixtures import supplied_resolution
from ._fixtures import typed_child

COMMAND = "get_object_info"


def test_an_unknown_name_is_an_answer_rather_than_an_error():
    """commands.get_object_info with a name nothing carries"""
    services_or_skip()
    answer = dispatch(COMMAND, {"name": "NoSuchObjectExistsHere"})

    # An agent guessing at a name should get a "no" it can recover from, not a
    # command_failed envelope it cannot.
    assert answer["status"] == "ok", "A miss is a successful answer, got {!r}".format(answer)
    assert answer["result"]["found"] is False
    assert answer["result"]["resolved_from"] == "name"
    assert "NoSuchObjectExistsHere" in answer["result"]["message"]
    assert answer["result"]["name"] is None


def test_a_bare_character_is_a_family_of_one():
    """HumanService.create_human() on its own, which is less than it sounds"""
    services = services_or_skip()
    with Character() as character:
        # Worth its own test because every other test in this module has to
        # work around it: a character MPFB has just built is **one object**,
        # with no rig, no clothes and no relatives at all.
        relatives = list(services["ObjectService"].find_related_objects(character.basemesh))
        assert relatives == [character.basemesh], \
            "create_human() should build a character of one object, got {!r}".format(
                [relative.name for relative in relatives])


def test_the_basemesh_is_reported_with_its_family():
    """ObjectService.find_related_objects() on a character with a relative"""
    services = services_or_skip()
    with Character() as character:
        garment = typed_child(services, character.basemesh, "BridgeTestHat", "Clothes")
        try:
            answer = result(COMMAND, {"name": character.basemesh.name})

            assert answer["found"] is True
            assert answer["object_type"] == "Basemesh"
            assert answer["blender_type"] == "MESH"
            assert answer["is_makehuman_object"] is True
            assert answer["in_current_scene"] is True

            names = [entry["name"] for entry in answer["related_objects"]]
            assert garment.name in names, \
                "The garment should be among the basemesh's relatives, got {!r}".format(names)
            # The subject is yielded by its own relatives walk and is filtered
            # out of it; a duplicate would read as two distinct objects.
            assert character.basemesh.name not in names, \
                "The subject must not appear among its own relatives, got {!r}".format(names)
            assert len(names) == len(set(names)), "Relatives should be deduplicated"
        finally:
            bpy.data.objects.remove(garment, do_unlink=True)


def test_a_basemesh_answers_the_material_question_and_not_the_mhclo_one():
    """asset_info: three shapes, and which keys each carries"""
    with Character() as character:
        info = result(COMMAND, {"name": character.basemesh.name})["asset_info"]

        # The shape *is* the answer. A union with the inapplicable keys nulled
        # would report mhclo_path: null on a basemesh, which reads as "we looked
        # for its mhclo and failed".
        assert set(info) == {"material_type", "material_source", "mhmat_path"}, \
            "A Basemesh answers the material question only, got {!r}".format(sorted(info))
        assert info["material_type"] is not None, \
            "identify_material() answers for a mesh even with no material on it"


def test_an_untyped_object_is_found_and_reported_as_plain():
    """ObjectService.get_object_type() on something MPFB never made"""
    services_or_skip()
    plain = linked_plain_object("BridgeTestPlainSubject")
    try:
        answer = result(COMMAND, {"name": plain.name})

        assert answer["found"] is True
        assert answer["object_type"] is None, \
            "MPFB answers '' for an untyped object and this coerces it in one place"
        assert answer["is_makehuman_object"] is False
        assert answer["asset_info"] is None, \
            "No type means no asset question was asked, which is not the same as no answer"
        assert answer["rigify_role"] is None
        assert "plain Blender object" in answer["message"]
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)


def test_an_object_outside_the_scene_resolves_and_says_so():
    """bpy.data.objects as what a name is looked up in"""
    with Character() as character:
        collections = list(character.basemesh.users_collection)
        assert collections, "The basemesh should be linked somewhere to begin with"
        for collection in collections:
            collection.objects.unlink(character.basemesh)
        try:
            answer = result(COMMAND, {"name": character.basemesh.name})

            # "Exists, but not in this scene" is a far more useful answer than a
            # bare "not found", and it is the reason the lookup is not the scene.
            assert answer["found"] is True
            assert answer["in_current_scene"] is False
            assert "without being linked into the current scene" in answer["message"]
        finally:
            for collection in collections:
                collection.objects.link(character.basemesh)


def test_the_active_object_is_used_when_no_name_is_given():
    """bpy.context.view_layer.objects.active as the fallback subject"""
    with Character() as character:
        previous = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = character.basemesh
        try:
            answer = result(COMMAND, {"name": None})

            assert answer["resolved_from"] == "active_object"
            assert answer["name"] == character.basemesh.name
        finally:
            bpy.context.view_layer.objects.active = previous


def test_nothing_is_selected_or_activated_in_order_to_answer():
    """The read-only claim, asserted rather than intended"""
    with Character() as character:
        previous_active = bpy.context.view_layer.objects.active
        selected_before = sorted(
            blender_object.name for blender_object in bpy.context.scene.objects
            if blender_object.select_get())

        result(COMMAND, {"name": character.basemesh.name})

        selected_after = sorted(
            blender_object.name for blender_object in bpy.context.scene.objects
            if blender_object.select_get())
        assert selected_after == selected_before, \
            "Inspecting an object must not change what the user has selected"
        assert bpy.context.view_layer.objects.active is previous_active, \
            "Inspecting an object must not change what is active"


def test_a_relative_entry_and_an_untyped_neighbour_have_different_shapes():
    """Two walks, two things that can be said"""
    with Character() as character:
        # An untyped child of the basemesh: the neighbourhood walk finds it, the
        # MakeHuman relatives walk does not.
        plain = linked_plain_object("BridgeTestNeighbour")
        plain.parent = character.basemesh
        try:
            answer = result(COMMAND, {"name": character.basemesh.name})

            others = {entry["name"]: entry for entry in answer["other_related_objects"]}
            assert plain.name in others, \
                "An untyped child should be in other_related_objects, got {!r}".format(
                    sorted(others))
            assert set(others[plain.name]) == {
                "name", "object_type", "blender_type", "in_current_scene", "rigify_role"}, \
                "An untyped neighbour carries rigify_role where a relative carries asset_info"
            for entry in answer["related_objects"]:
                assert "asset_info" in entry and "rigify_role" not in entry, \
                    "A MakeHuman relative carries asset_info and not rigify_role"
        finally:
            bpy.data.objects.remove(plain, do_unlink=True)


def test_the_type_vocabularies_are_mpfbs_own():
    """objectservice._SKELETON_TYPES and _MESH_ASSET_TYPES, through sys.modules"""
    import sys  # pylint: disable=import-outside-toplevel

    services = services_or_skip()
    module = sys.modules[services["ObjectService"].__module__]

    # The three asset_info shapes dispatch on these two, so a rename would
    # silently move every mesh asset into the "no question applies" branch.
    for name in ("_SKELETON_TYPES", "_MESH_ASSET_TYPES"):
        assert hasattr(module, name), \
            "MPFB no longer publishes {:s}; the command now uses its own fallback".format(name)
    assert "Basemesh" not in module._MESH_ASSET_TYPES, \
        "A basemesh is not a mesh *asset*, which is why it has a shape of its own"


def test_a_name_of_the_wrong_type_is_refused_before_the_handler_runs():
    """command_server.dispatch() validating get_object_info's one parameter"""
    command_server = bridge_module("command_server")

    answer = dispatch(COMMAND, {"name": 12})

    assert answer["error"] == command_server.ERROR_INVALID_PARAMS
    assert "name" in answer["message"]


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    """command_server.dispatch() with requires_mpfb and no MPFB"""
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = dispatch(COMMAND, {"name": None})

    assert answer["status"] == "error"
    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE, \
        "The refusal should say the install is wrong, not that nothing was found"
    assert "found" not in answer, "An install problem must not be phrased as a missing object"
