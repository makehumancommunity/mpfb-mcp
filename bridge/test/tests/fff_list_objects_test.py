"""
``list_objects`` against a real MPFB, which is the point of this whole file.

**This is the first test module in this repository whose subject is MPFB rather
than a transport.** Every other check of what a tool answers is an
``exec()``-ed payload run against a stub ``bpy`` and stub services - a harness
that can prove the code does what its author expected and can prove nothing
whatever about MPFB, because the stub and the code were written by the same
person from the same reading of MPFB's source. Here the same questions are put
to a real install in a headless Blender, and two of them turn out to be claims
about MPFB that had never been asked of MPFB: that its type matching really is
a case-insensitive substring test, and that ``get_object_type()`` really
answers ``""`` rather than ``None``.

The discipline this module is meant to set, because twenty-three commands will
copy it:

- **Everything that can be checked here is checked here.** What stays on
  mpfb-mcp's side for a migrated tool is what genuinely cannot cross the
  socket: the tool's own local argument validation, what goes on the wire, the
  seam and the record.
- **A missing prerequisite is a skip with a reason, never a quiet pass.** This
  suite runs against whatever Blender the developer has, which may have no MPFB
  in it at all; a test that silently passed there would be worse than no test.
- **How a test builds a character to look at** is ``HumanService.create_human()``
  and a snapshot-and-delete cleanup, which is MPFB's own arrangement in
  ``mpfb2/test/tests/eee_ui/_helpers/scene_fixtures.py``. It works without a
  screen, which was not established before this module ran. FR 031 moved that
  arrangement, the skip and the dispatch helper into
  [`_fixtures.py`](_fixtures.py), where the eight commands that came next share
  them; this module now reads them from there rather than keeping its own.
- **A Blender with no MPFB is part of the test rather than an obstacle to it**,
  reached by supplying the resolution the dispatcher would have found.

Calls go through ``dispatch()`` rather than straight to the handler, because
that is what a caller gets: the parameter contract, the ``requires_mpfb``
precondition and the handler, in that order.
"""

import sys

import bpy

from . import bridge_module
from . import dynamic_import
from ._fixtures import Character as _Character
from ._fixtures import dispatch
from ._fixtures import linked_plain_object as _linked_plain_object
from ._fixtures import result as _fixture_result
from ._fixtures import services_or_skip as _services_or_skip
from ._fixtures import supplied_resolution


def _answer(params=None):
    return dispatch("list_objects", params)


def _result(params=None):
    return _fixture_result("list_objects", params)


def test_a_scene_with_no_makehuman_objects_answers_none_of_them():
    """commands.list_objects with nothing of MPFB's in the scene"""
    _services_or_skip()
    result = _result()

    assert result["count"] == 0, \
        "Expected no MakeHuman objects before one is made, got {!r}".format(result["objects"])
    assert result["objects"] == [], "count and objects should agree"
    # The pairing that makes an empty list trustworthy: nothing was filtered
    # out by a name MPFB does not know, because nothing was asked for.
    assert result["requested_type"] is None, "An omitted filter should come back as null"
    assert result["type_recognized"] is True, "No filter is not an unrecognised one"
    assert result["known_types"], "The vocabulary should be reported even when nothing matched"


def test_a_basemesh_is_listed_with_both_of_its_types():
    """commands.list_objects with a character in the scene"""
    with _Character() as character:
        result = _result()

        entries = {entry["name"]: entry for entry in result["objects"]}
        assert character.basemesh.name in entries, \
            "The basemesh should be listed, got {!r}".format(sorted(entries))
        entry = entries[character.basemesh.name]
        assert entry["object_type"] == "Basemesh", \
            "MPFB's own type should be reported, got {!r}".format(entry["object_type"])
        assert entry["blender_type"] == "MESH", \
            "Blender's type should be reported beside it, got {!r}".format(entry["blender_type"])
        assert result["count"] == len(result["objects"]), "count should count the entries"


def test_matching_is_mpfbs_substring_rule_rather_than_equality():
    """ObjectService.object_is() as the filter, and as the tool promises it"""
    # The claim mpfb_list_objects' description makes to a caller - "rig" matches
    # Subrig, "mesh" matches Basemesh - has until now rested on a reading of
    # MPFB's source and on a stub written from that reading. This is the first
    # time it is put to MPFB.
    services = _services_or_skip()
    with _Character() as character:
        object_service = services["ObjectService"]
        assert object_service.object_is(character.basemesh, "mesh"), \
            "MPFB itself should match a substring, or the tool's documented rule is wrong"

        listed = [entry["name"] for entry in _result({"object_type": "mesh"})["objects"]]
        exact = [entry["name"] for entry in _result({"object_type": "Basemesh"})["objects"]]

        assert character.basemesh.name in listed, \
            "A substring filter should have matched the basemesh, got {!r}".format(listed)
        assert character.basemesh.name in exact, "An exact filter should match it too"


def test_an_unrecognised_type_is_flagged_beside_the_empty_list():
    """commands.list_objects with a misspelled type"""
    with _Character():
        result = _result({"object_type": "Basemseh"})

        # The pairing is the whole point: without type_recognized, a misspelling
        # is indistinguishable from a scene that genuinely has no basemeshes.
        assert result["objects"] == [], "A misspelled type should match nothing"
        assert result["requested_type"] == "Basemseh", "The filter should be echoed back"
        assert result["type_recognized"] is False, \
            "A type MPFB does not know should be flagged as such"


def test_a_recognised_type_matching_nothing_stays_recognised():
    """commands.list_objects with a real type that is not in the scene"""
    with _Character():
        result = _result({"object_type": "Eyebrows"})

        assert result["objects"] == [], "A bare character has no eyebrows"
        assert result["type_recognized"] is True, \
            "'Eyebrows' is a type MPFB knows, so an empty list means the scene, not the spelling"


def test_an_object_with_no_mpfb_type_is_left_out_and_never_reported_as_empty():
    """ObjectService.get_object_type() answering "" rather than None"""
    services = _services_or_skip()
    plain = _linked_plain_object("BridgeTestPlainObject")
    try:
        # The quirk the coercion exists for, asserted against MPFB rather than
        # against a stub reproducing it.
        assert services["ObjectService"].get_object_type(plain) == "", \
            "MPFB should answer an empty string for an untyped object"

        result = _result()

        assert plain.name not in [entry["name"] for entry in result["objects"]], \
            "An object with no MPFB type is not a MakeHuman object"
        assert all(entry["object_type"] for entry in result["objects"]), \
            "object_type is a type name or null, never the empty string MPFB hands out"
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)


def test_an_object_outside_the_current_scene_is_not_listed():
    """bpy.context.scene.objects as the thing searched"""
    with _Character() as character:
        # Unlinked from every collection it is in rather than from the scene's
        # own, since MPFB may well have put the character in a collection of
        # its own and unlinking the wrong one would leave the object in the
        # scene and the test passing for no reason.
        collections = list(character.basemesh.users_collection)
        assert collections, "The basemesh should be linked somewhere to begin with"
        for collection in collections:
            collection.objects.unlink(character.basemesh)
        try:
            listed = [entry["name"] for entry in _result()["objects"]]
            assert character.basemesh.name not in listed, \
                "Only the current scene is searched, so an unlinked object should be absent"
        finally:
            for collection in collections:
                collection.objects.link(character.basemesh)


def test_the_vocabulary_is_mpfbs_own_and_not_this_addons_copy():
    """objectservice._ALL_TYPES, read through sys.modules"""
    services = _services_or_skip()
    module = sys.modules[services["ObjectService"].__module__]
    assert hasattr(module, "_ALL_TYPES"), \
        "MPFB no longer publishes _ALL_TYPES; the fallback is now the only answer"

    assert _result()["known_types"] == list(module._ALL_TYPES), \
        "known_types should be MPFB's list, not a copy that can drift from it"


def test_the_fallback_vocabulary_is_used_when_mpfb_stops_publishing_one():
    """commands.list_objects when _ALL_TYPES has been renamed away"""
    services = _services_or_skip()
    module = sys.modules[services["ObjectService"].__module__]
    fallback = dynamic_import("commands.list_objects", "_FALLBACK_TYPES")
    original = module._ALL_TYPES

    del module._ALL_TYPES
    try:
        result = _result()
    finally:
        module._ALL_TYPES = original

    # Reporting last year's type list is a better answer than failing the call,
    # which is the whole reason there is a fallback.
    assert result["known_types"] == list(fallback), \
        "A missing _ALL_TYPES should fall back rather than fail the call"


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    """command_server.dispatch() with requires_mpfb and no MPFB"""
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    # The first command in the table with requires_mpfb=True, so this is the
    # first time that precondition is exercised from outside its own test. The
    # state is supplied rather than waited for: this Blender may well have a
    # perfectly good MPFB in it.
    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = _answer()

    assert answer["status"] == "error", "A command needing MPFB cannot answer without it"
    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE, \
        "The refusal should say the install is wrong, not that the command failed"
    assert answer["command"] == "list_objects", "The refusal should name the command"
    assert "no MakeHuman" not in answer["message"], \
        "An install problem must not be phrased as an empty scene"


def test_a_filter_of_the_wrong_type_is_refused_before_the_handler_runs():
    """command_server.dispatch() validating list_objects' one parameter"""
    command_server = bridge_module("command_server")

    answer = _answer({"object_type": 7})

    assert answer["error"] == command_server.ERROR_INVALID_PARAMS, \
        "A non-string filter should be invalid_params"
    assert "object_type" in answer["message"], "The message should name the parameter"


def test_an_explicit_null_filter_is_the_same_request_as_an_omitted_one():
    """commands.list_objects with object_type null"""
    # mpfb-mcp always sends the key, with null when no filter was given, so
    # this is the shape the real client puts on the wire.
    _services_or_skip()
    assert _result({"object_type": None}) == _result(), \
        "An explicit null and an omitted parameter should be one request"
