"""
``get_face_units`` against a real MPFB: the vocabulary and a real read.

The claim this module exists for is the zero-for-missing convention:
``FaceService.read_current_expression()`` always answers all 52 ARKit units,
reporting ``0.0`` for one whose shape key was never created - so a fresh
character (no expression ever composed) and a character with a genuinely
neutral face read identically, and ``known_face_units``/``faceunits01_installed``
are checked against a real install rather than assumed from its docstrings.

``shapekey_present`` is the one thing this command reports that MPFB itself
does not compute anywhere: it is a fact about the mesh (does a real shape key
back this value), not about the expression dict MPFB hands back. The fixture
for it adds a ``!ex-`` shape key with Blender's own API rather than through
``mpfb_set_face_units`` - the write side is the mutating command's own claim,
in ``ddd_mutating/set_face_units_test.py``.
"""

import bpy

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import supplied_resolution

COMMAND = "get_face_units"


def _answer(params=None):
    return dispatch(COMMAND, params)


def _result(params=None):
    return result(COMMAND, params)


def test_a_fresh_character_reports_no_nonzero_face_units():
    with Character() as character:
        answer = _result({"name": character.basemesh.name})

        assert answer["found"] is True
        assert answer["face_units"] == [], \
            "A freshly created character should have composed no expression"
        assert answer["total_count"] == 52


def test_include_zero_reports_all_fifty_two():
    with Character() as character:
        answer = _result({"name": character.basemesh.name, "include_zero": True})

        assert answer["face_unit_count"] == 52
        names = set(entry["face_unit"] for entry in answer["face_units"])
        assert len(names) == 52, "Every ARKit unit should be named exactly once"
        assert all(entry["value"] == 0.0 for entry in answer["face_units"])
        assert all(entry["shapekey_present"] is False for entry in answer["face_units"]), \
            "A fresh character has no !ex- shape keys at all yet"


def test_known_face_units_covers_every_arkit_name_exactly_once():
    import sys

    services = services_or_skip()
    faceservice_module = sys.modules[services["FaceService"].__module__]
    answer = _result()

    grouped = answer["known_face_units"]
    flattened = [name for names in grouped.values() for name in names]
    assert len(flattened) == len(set(flattened)) == 52, \
        "known_face_units should list every ARKit unit exactly once"
    assert set(flattened) == set(faceservice_module.ARKIT_FACEUNITS), \
        "known_face_units should agree with MPFB's own ARKIT_FACEUNITS"


def test_known_face_units_and_faceunits01_installed_are_reported_even_when_not_found():
    answer = _result({"name": "no-such-object"})

    assert answer["found"] is False
    assert answer["known_face_units"], \
        "The vocabulary does not depend on resolving a subject"
    assert isinstance(answer["faceunits01_installed"], bool)


def test_faceunits01_installed_is_reported_as_a_bool():
    answer = _result()
    assert isinstance(answer["faceunits01_installed"], bool)


def test_a_manually_added_shapekey_is_reported_as_present_with_its_value():
    with Character() as character:
        basemesh = character.basemesh
        if basemesh.data.shape_keys is None:
            basemesh.shape_key_add(name="Basis")
        basemesh.shape_key_add(name="!ex-jawOpen")
        basemesh.data.shape_keys.key_blocks["!ex-jawOpen"].value = 0.35

        answer = _result({"name": basemesh.name, "include_zero": True})

        entries = {entry["face_unit"]: entry for entry in answer["face_units"]}
        assert entries["jawOpen"]["shapekey_present"] is True
        assert abs(entries["jawOpen"]["value"] - 0.35) < 1e-6
        others = [entry for name, entry in entries.items() if name != "jawOpen"]
        assert all(entry["shapekey_present"] is False for entry in others)


def test_no_object_resolves_when_none_is_active_and_none_is_named():
    bpy.context.view_layer.objects.active = None
    answer = _result()

    assert answer["found"] is False
    assert answer["basemesh_name"] is None
    assert answer["message"]


def test_mpfb_unavailable_is_refused_before_the_handler_runs():
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_ABSENT):
        envelope = _answer()

    assert envelope["status"] == "error"
    assert envelope["error"] == command_server.ERROR_MPFB_UNAVAILABLE
