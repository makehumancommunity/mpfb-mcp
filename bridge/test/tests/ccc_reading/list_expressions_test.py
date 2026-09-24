"""
``list_expressions`` against a real MPFB, over a redirected expressions tree.

Everything here runs inside :func:`_fixtures.expression_library`, which points
MPFB's data roots at a tree this module builds - so the answer depends on the
fixture and not on which expressions the developer has installed. The files are
written by ``FaceService.save_expression()`` itself, except the one that must be
malformed, which MPFB's writer cannot produce.

The four shapes FR 027 names: the same library-relative path in two roots (the
first root wins, and the loser is reported as shadowed), a file that does not
parse (skipped by MPFB, but counted and named here), a file with no ``name``
(label falls back to the basename), and an empty tree - plus the pack-absent
answer.
"""

import os

from .._fixtures import expression_library
from .._fixtures import only_these_data_roots
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import write
from .._fixtures import write_expression


def _by_fragment(answer):
    return {entry["fragment"]: entry for entry in answer["expressions"]}


def test_every_file_is_listed_with_both_identifiers_and_its_face_units(tmp_path):
    services = services_or_skip()
    with expression_library(services, tmp_path) as paths:
        answer = result("list_expressions")

    listed = _by_fragment(answer)
    assert set(listed) == {"jaw.json", "shadowing.json", "smile.json"}
    smile = listed["smile.json"]
    assert smile["path"] == os.path.abspath(paths["smile"])
    assert smile["root"] == paths["user_expressions"]
    assert smile["label"] == "smile"
    assert smile["description"] == "A broad smile."
    assert smile["tags"] == ["happy"]
    assert smile["license"] == "CC0"
    assert smile["face_units"] == {"jawOpen": 0.6, "mouthSmileLeft": 0.8,
                                   "mouthSmileRight": 0.8}
    assert answer["count"] == 3
    assert answer["faceunits01_installed"] is True


def test_the_roots_are_reported_in_mpfbs_priority_order(tmp_path):
    services = services_or_skip()
    with expression_library(services, tmp_path) as paths:
        answer = result("list_expressions")

    assert answer["roots"] == [paths["system_expressions"], paths["user_expressions"]]


def test_the_same_path_in_two_roots_lists_the_first_and_reports_the_other(tmp_path):
    """The premise of save_expression's name_shadowed refusal, as MPFB's scan has it."""
    services = services_or_skip()
    with expression_library(services, tmp_path) as paths:
        answer = result("list_expressions")

    winner = _by_fragment(answer)["shadowing.json"]
    assert winner["path"] == os.path.abspath(paths["shadowing"]), \
        "mpfb_data comes before user_data, so the system copy should be the listed one"
    assert winner["face_units"] == {"eyeBlinkLeft": 0.5}
    assert answer["shadowed"] == [dict(
        fragment="shadowing.json",
        path=os.path.abspath(paths["shadowed"]),
        shadowed_by=os.path.abspath(paths["shadowing"]))]


def test_a_file_that_does_not_parse_is_counted_and_named_rather_than_hidden(tmp_path):
    services = services_or_skip()
    with expression_library(services, tmp_path) as paths:
        # The one hand-written file in this module: MPFB's writer cannot produce
        # a broken one, and a broken one is what is being tested.
        broken = write(os.path.join(paths["user_expressions"], "broken.json"), "{ not json")
        answer = result("list_expressions")

    assert "broken.json" not in _by_fragment(answer), "MPFB's own scan skips it"
    assert [entry["fragment"] for entry in answer["unreadable"]] == ["broken.json"]
    assert answer["unreadable"][0]["path"] == os.path.abspath(broken)
    assert answer["unreadable"][0]["error"]
    assert "could not be parsed" in answer["message"]


def test_a_file_with_no_name_is_labelled_from_its_basename(tmp_path):
    services = services_or_skip()
    with expression_library(services, tmp_path) as paths:
        write_expression(services, os.path.join(paths["user_expressions"], "big_grin.json"),
                         {"jawOpen": 0.2}, name="")
        answer = result("list_expressions")

    assert _by_fragment(answer)["big_grin.json"]["label"] == "big grin"


def test_an_empty_tree_is_an_answer_naming_no_roots(tmp_path):
    services = services_or_skip()
    face_service = services["FaceService"]
    with only_these_data_roots(services, user_data=str(tmp_path)):
        try:
            answer = result("list_expressions", {"refresh": True})
        finally:
            face_service.is_faceunits01_installed(force_recheck=True)

    assert answer["expressions"] == []
    assert answer["count"] == 0
    assert answer["roots"] == []
    assert answer["unreadable"] == []
    assert answer["shadowed"] == []
    assert answer["faceunits01_installed"] is False, \
        "no targets exist under the redirected roots, so the probe must fail"
    assert "faceunits01" in answer["message"]


def test_refresh_re_probes_the_pack(tmp_path):
    """Without refresh, the cached probe answers; with it, the redirected disk does."""
    services = services_or_skip()
    face_service = services["FaceService"]
    with expression_library(services, tmp_path) as paths:
        assert result("list_expressions")["faceunits01_installed"] is True
        os.remove(os.path.join(paths["user"], "targets", "faceunits", "cheekPuff.target"))
        assert result("list_expressions")["faceunits01_installed"] is True, \
            "the cache has not been busted yet"
        assert result("list_expressions", {"refresh": True})["faceunits01_installed"] is False
    assert face_service.is_faceunits01_installed() is not None
