"""
``set_face_units`` against a real MPFB: the pack precondition, and a real write.

**What is checked here is what cannot be checked with the pack faked.** The
vocabulary refusal (an unrecognised ``face_unit`` name) does not need
``faceunits01`` installed at all and is checked first. The pack-absent refusal
and the partial-install ``could_not_load`` case are then reproduced by
redirecting MPFB's data roots with :func:`only_these_data_roots` - the same
technique ``lll_list_assets_test.py`` and friends use - and by forcing
``FaceService``'s installed-probe cache to re-read them, since nothing else on
this side would bust it between tests. Finally, with the developer's own real
install (which ships every ARKit target under
``~/makehuman/mpfb/data/targets/faceunits/`` on this machine, confirmed by
:mod:`rrr_get_face_units_test`), a real weight is loaded from disk, a real
shape key lands on the mesh, and a second call proves the additive default and
``clear_first`` against each other.

``FaceService.is_faceunits01_installed()`` caches in a module global nothing
else invalidates, so every test that manipulates the data roots calls it with
``force_recheck=True`` **inside** the redirected block to seed a deterministic
cache, and restores the real answer again on the way out - both so that this
module's own tests do not see each other's cache, and so that a module running
after this one is not left looking at a faked "pack absent".
"""

import sys

import bpy

from .._fixtures import Character as _Character
from .._fixtures import only_these_data_roots
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import write_target


def _result(params=None):
    return _fixture_result("set_face_units", params)


def _faceservice_module(services):
    return sys.modules[services["FaceService"].__module__]


def _shapekey_value(basemesh, shapekey_name):
    keys = basemesh.data.shape_keys
    if keys is None or keys.key_blocks is None:
        return None
    block = keys.key_blocks.get(shapekey_name)
    return None if block is None else float(block.value)


def test_an_unknown_face_unit_refuses_the_whole_batch_and_writes_nothing():
    """This does not need the pack installed: the vocabulary check runs first."""
    with _Character() as character:
        result = _result({
            "name": character.basemesh.name,
            "face_units": [
                {"face_unit": "jawOpen", "weight": 0.3},
                {"face_unit": "browDownLeftt", "weight": 0.2},
            ],
        })

        assert result["found"] is True
        assert result["ready"] is False
        assert result["blocked_by"] == "unknown_face_units"
        assert result["performed"] is False
        assert _shapekey_value(character.basemesh, "!ex-jawOpen") is None, \
            "Nothing should have been written, including the recognised entry"
        unknown = result["unknown_face_units"]
        assert [entry["face_unit"] for entry in unknown] == ["browDownLeftt"]
        assert "browDownLeft" in unknown[0]["closest"], \
            "The closest legal spelling should be suggested"


def test_edit_mode_blocks_the_write():
    with _Character() as character:
        bpy.context.view_layer.objects.active = character.basemesh
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            result = _result({
                "name": character.basemesh.name,
                "face_units": [{"face_unit": "jawOpen", "weight": 0.3}],
            })
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

        assert result["ready"] is False
        assert result["blocked_by"] == "not_object_mode"
        assert result["performed"] is False


def test_the_pack_absent_refuses_the_whole_call():
    services = _services_or_skip()
    face_service = services["FaceService"]

    with _Character() as character:
        with only_these_data_roots(services):
            face_service.is_faceunits01_installed(force_recheck=True)
            try:
                result = _result({
                    "name": character.basemesh.name,
                    "face_units": [{"face_unit": "jawOpen", "weight": 0.3}],
                })
            finally:
                # Restore the real answer before this `with` block exits, so a
                # module running after this one is not left looking at a faked
                # absence.
                face_service.is_faceunits01_installed(force_recheck=True)

        assert result["ready"] is False
        assert result["blocked_by"] == "faceunits01_not_installed"
        assert result["performed"] is False
        assert _shapekey_value(character.basemesh, "!ex-jawOpen") is None


def test_a_partially_installed_pack_reports_could_not_load_rather_than_refusing(tmp_path):
    """The probe tests one target; a caller asking for another may still miss."""
    services = _services_or_skip()
    face_service = services["FaceService"]

    # Only "cheekPuff" (what the probe itself checks) and "jawOpen" are on
    # disk; every other unit, "mouthLeft" included, is not.
    root = str(tmp_path)
    write_target(root + "/targets/faceunits/cheekPuff.target")
    write_target(root + "/targets/faceunits/jawOpen.target")

    with _Character() as character:
        with only_these_data_roots(services, user_data=root):
            face_service.is_faceunits01_installed(force_recheck=True)
            assert face_service.is_faceunits01_installed() is True, \
                "The fixture should pass the pack's own install probe"
            try:
                result = _result({
                    "name": character.basemesh.name,
                    "face_units": [
                        {"face_unit": "jawOpen", "weight": 0.3},
                        {"face_unit": "mouthLeft", "weight": 0.2},
                    ],
                    "refit": False,
                })
            finally:
                face_service.is_faceunits01_installed(force_recheck=True)

        assert result["ready"] is True
        assert result["faceunits01_installed"] is True
        assert result["could_not_load"] == ["mouthLeft"]
        assert [entry["face_unit"] for entry in result["applied"]] == ["jawOpen"]
        assert result["loaded_from_disk"] == ["jawOpen"]
        assert result["performed"] is True
        assert _shapekey_value(character.basemesh, "!ex-jawOpen") is not None
        assert _shapekey_value(character.basemesh, "!ex-mouthLeft") is None


def test_a_zero_weight_on_an_absent_shapekey_is_skipped_entirely():
    services = _services_or_skip()
    if not services["FaceService"].is_faceunits01_installed():
        import pytest
        pytest.skip("this install has no faceunits01 pack")

    with _Character() as character:
        result = _result({
            "name": character.basemesh.name,
            "face_units": [{"face_unit": "jawOpen", "weight": 0.0}],
            "refit": False,
        })

        assert result["skipped_absent_at_zero"] == ["jawOpen"]
        assert result["applied"] == []
        assert result["loaded_from_disk"] == []
        assert result["performed"] is False, \
            "Nothing was actually written, so this should not read as a change"
        assert _shapekey_value(character.basemesh, "!ex-jawOpen") is None, \
            "A zero-weight unit with no shape key yet should not have created one"


def test_loading_then_reapplying_is_additive_and_clear_first_zeroes_it():
    services = _services_or_skip()
    if not services["FaceService"].is_faceunits01_installed():
        import pytest
        pytest.skip("this install has no faceunits01 pack")

    with _Character() as character:
        first = _result({
            "name": character.basemesh.name,
            "face_units": [{"face_unit": "jawOpen", "weight": 0.4}],
            "refit": False,
        })
        assert first["performed"] is True
        assert first["loaded_from_disk"] == ["jawOpen"]
        assert abs(_shapekey_value(character.basemesh, "!ex-jawOpen") - 0.4) < 1e-6

        # A second, different unit: additive by default, so the first should
        # be left exactly as it was.
        second = _result({
            "name": character.basemesh.name,
            "face_units": [{"face_unit": "mouthSmileLeft", "weight": 0.6}],
            "refit": False,
        })
        assert second["performed"] is True
        assert second["applied"] == [] or all(
            entry["face_unit"] != "jawOpen" for entry in second["applied"]), \
            "The unmentioned unit should not have been touched"
        assert abs(_shapekey_value(character.basemesh, "!ex-jawOpen") - 0.4) < 1e-6, \
            "set_expression is additive: a unit not mentioned is left alone"

        # clear_first zeroes both of the above, then applies exactly what is
        # asked for on this call.
        third = _result({
            "name": character.basemesh.name,
            "face_units": [{"face_unit": "jawOpen", "weight": 0.1}],
            "clear_first": True,
            "refit": False,
        })
        assert third["performed"] is True
        assert set(third["cleared"]) == {"jawOpen", "mouthSmileLeft"}
        assert abs(_shapekey_value(character.basemesh, "!ex-jawOpen") - 0.1) < 1e-6
        assert abs(_shapekey_value(character.basemesh, "!ex-mouthSmileLeft")) < 1e-6


def test_an_already_present_shapekey_is_reported_under_applied_not_loaded():
    services = _services_or_skip()
    if not services["FaceService"].is_faceunits01_installed():
        import pytest
        pytest.skip("this install has no faceunits01 pack")

    with _Character() as character:
        _result({
            "name": character.basemesh.name,
            "face_units": [{"face_unit": "jawOpen", "weight": 0.2}],
            "refit": False,
        })

        second = _result({
            "name": character.basemesh.name,
            "face_units": [{"face_unit": "jawOpen", "weight": 0.7}],
            "refit": False,
        })

        assert second["loaded_from_disk"] == [], \
            "The shape key already existed; this should not read as a disk load"
        applied_names = [entry["face_unit"] for entry in second["applied"]]
        assert applied_names == ["jawOpen"]
        assert abs(second["applied"][0]["previous_value"] - 0.2) < 1e-6
        assert abs(second["applied"][0]["new_value"] - 0.7) < 1e-6
