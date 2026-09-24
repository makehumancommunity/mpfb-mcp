"""
``save_expression`` against a real MPFB, writing into a redirected user data.

It writes outside the ``.blend``, so per this package's ``__init__.py`` every
test writes somewhere redirected: :func:`_fixtures.expression_library` points
MPFB's user data at ``tmp_path``, and nothing here can reach the developer's own
expression library.

What is checked is what FR 027 requires of a tool that writes a file: the file's
contents after MPFB's rounding and zero-dropping, read back rather than assumed;
the overwrite refusal carrying the existing file's size and age and leaving it
byte-identical; the shadowed-name refusal, which rests on MPFB's own precedence
rule; the empty-face refusal; and that the character's stack and shape keys are
untouched by a save.
"""

# pylint: disable=protected-access

import json
import os
import sys

from .._fixtures import Character
from .._fixtures import expression_library
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip


def _save(basemesh, name, **extra):
    params = {"expression_name": name, "name": basemesh.name}
    params.update(extra)
    return _fixture_result("save_expression", params)


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_the_live_face_is_written_rounded_and_without_zeros(tmp_path):
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path) as paths:
            face_service.set_expression(character.basemesh, {
                "jawOpen": 0.123456, "browInnerUp": 0.5, "eyeBlinkLeft": 0.0})
            answer = _save(character.basemesh, "composed", tags=["test"], author="me")
            on_disk = _read(answer["path"])

    assert answer["saved"] is True
    assert answer["performed"] is True
    assert answer["path"] == os.path.join(paths["user_expressions"], "composed.json")
    assert answer["fragment"] == "composed.json"
    assert on_disk["face_units"] == {"browInnerUp": 0.5, "jawOpen": 0.1235}, \
        "four decimals, and no zero-valued unit"
    assert answer["face_units"] == on_disk["face_units"], "reported as read back from the file"
    assert on_disk["name"] == "composed"
    assert on_disk["license"] == "CC0", "the composer panel's default, not save_expression's"
    assert on_disk["tags"] == ["test"]
    assert answer["metadata"]["author"] == "me"
    assert answer["overwrote"] is False
    assert answer["file_before"] is None
    assert answer["apply_with"] == dict(
        expressions=[dict(fragment="composed.json", weight=1.0)], mode="replace")


def test_the_name_is_saved_as_given(tmp_path):
    """The composer promises lowercasing and dashes; nothing in MPFB does either."""
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            services["FaceService"].set_expression(character.basemesh, {"jawOpen": 0.2})
            answer = _save(character.basemesh, "Big_Grin")

    assert os.path.basename(answer["path"]) == "Big_Grin.json"
    assert answer["metadata"]["name"] == "Big_Grin"


def test_an_existing_file_is_refused_with_its_facts_and_left_byte_identical(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path) as paths:
            services["FaceService"].set_expression(character.basemesh, {"browInnerUp": 0.9})
            with open(paths["smile"], "rb") as handle:
                before = handle.read()
            refused = _save(character.basemesh, "smile")
            with open(paths["smile"], "rb") as handle:
                after = handle.read()
            replaced = _save(character.basemesh, "smile", overwrite=True)

    assert refused["saved"] is False
    assert refused["blocked_by"] == "expression_exists"
    assert refused["performed"] is False
    assert refused["path"] == paths["smile"]
    assert refused["file_before"]["size_bytes"] == len(before)
    assert refused["file_before"]["modified"]
    assert after == before
    assert replaced["overwrote"] is True
    assert replaced["file_before"]["size_bytes"] == len(before)
    assert replaced["face_units"] == {"browInnerUp": 0.9}


def test_a_name_a_higher_priority_root_already_holds_is_refused(tmp_path):
    """The file would be written and then never listed, applied or restored."""
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path) as paths:
            services["FaceService"].set_expression(character.basemesh, {"jawOpen": 0.2})
            # shadowing.json exists in user data too, so overwrite is needed to
            # get past the first refusal and reach this one.
            answer = _save(character.basemesh, "shadowing", overwrite=True)
            with open(paths["shadowed"], "r", encoding="utf-8") as handle:
                untouched = json.load(handle)

    assert answer["blocked_by"] == "name_shadowed"
    assert answer["shadowed_by"]["path"] == paths["shadowing"]
    assert answer["shadowed_by"]["same_fragment"] is True
    assert untouched["face_units"] == {"browInnerUp": 0.5}


def test_the_premise_of_the_shadowing_refusal_is_mpfbs_own_behaviour(tmp_path):
    """Asked of MPFB directly, so the refusal above rests on something checked.

    MPFB's composer panel says user-saved expressions take priority over
    system-shipped ones. Its listing and its resolver both say the opposite.
    """
    services = services_or_skip()
    face_service = services["FaceService"]
    asset_service = services["AssetService"]
    with expression_library(services, tmp_path) as paths:
        listed = {fragment: path for path, fragment, _meta
                  in face_service.list_available_expressions()}
        resolved = asset_service.find_asset_absolute_path("shadowing.json",
                                                          asset_subdir="expressions")

    assert listed["shadowing.json"] == os.path.abspath(paths["shadowing"])
    assert os.path.abspath(resolved) == os.path.abspath(paths["shadowing"])


def test_a_face_with_nothing_on_it_is_refused(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path) as paths:
            answer = _save(character.basemesh, "nothing")
            exists = os.path.exists(os.path.join(paths["user_expressions"], "nothing.json"))

    assert answer["blocked_by"] == "empty_expression"
    assert answer["path"].endswith("nothing.json"), "the path is in every answer"
    assert exists is False


def test_a_save_changes_nothing_on_the_character(tmp_path):
    services = services_or_skip()
    face_service = services["FaceService"]
    prop = sys.modules[face_service.__module__].APPLIED_EXPRESSIONS_PROP
    with Character() as character:
        with expression_library(services, tmp_path):
            face_service.set_stack_weight(character.basemesh, "jaw.json", 0.5)
            face_service.set_expression(character.basemesh, {"browInnerUp": 0.3})
            stack_before = character.basemesh.get(prop)
            face_before = face_service.read_current_expression(character.basemesh)
            answer = _save(character.basemesh, "whole_face")
            stack_after = character.basemesh.get(prop)
            face_after = face_service.read_current_expression(character.basemesh)

    assert stack_after == stack_before
    assert face_after == face_before
    assert answer["stack_contributed"] is True
    assert set(answer["face_units"]) == {"browInnerUp", "jawOpen"}, \
        "the whole face is saved, including what the stack contributed"


def test_the_new_file_gains_a_slider_in_mpfbs_panel(tmp_path):
    services = services_or_skip()
    panel = sys.modules[services["FaceService"].__module__.rsplit(".services.", 1)[0]
                        + ".ui.apply_assets.useexpression"]
    with Character() as character:
        with expression_library(services, tmp_path):
            services["FaceService"].set_expression(character.basemesh, {"jawOpen": 0.2})
            answer = _save(character.basemesh, "fresh_slider_{:d}".format(os.getpid()))
            assets = [entry["asset"] for entry in panel._EXPRESSION_PROP_MAP.values()]

    assert answer["panel_synced"] is True, answer["panel_sync_reason"]
    assert answer["fragment"] in assets


def test_an_unresolved_subject_is_refused_with_the_path(tmp_path):
    services = services_or_skip()
    with expression_library(services, tmp_path) as paths:
        answer = _fixture_result("save_expression",
                                 {"expression_name": "orphan", "name": "no such object"})

    assert answer["blocked_by"] == "subject_not_found"
    assert answer["path"] == os.path.join(paths["user_expressions"], "orphan.json")
    assert answer["expression_name"] == "orphan"
    assert "pass it as expression_name" in answer["message"], \
        "name changed meaning in FR 037, and a caller using the old spelling lands here"


def test_a_path_shaped_name_is_refused_on_this_side_too(tmp_path):
    """Defence in depth: the socket is reachable by more than mpfb-mcp."""
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            services["FaceService"].set_expression(character.basemesh, {"jawOpen": 0.2})
            answer = _save(character.basemesh, "../escape")

    assert answer["blocked_by"] == "invalid_name"
    assert answer["path"] is None
    assert not os.path.exists(os.path.join(str(tmp_path), "user", "escape.json"))
