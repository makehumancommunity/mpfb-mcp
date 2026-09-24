"""
``get_expression`` against a real MPFB: the divergence check is the centre of it.

Four cases, each set up with MPFB's **own** functions - ``set_stack_weight`` to
put an expression on, ``set_expression`` to compose on top, the private stack
writer for a row whose file does not exist - so that this module tests what the
command reports about a state MPFB produced, and not what ``apply_expressions``
produced:

- the stack and the live face agree;
- a unit the stack does not explain (composed work);
- a stack row whose file is missing;
- a stack whose sum clamped.

Plus FR 027's requirement 12 boundary: the answer does not carry the 52 live
values, which are ``get_face_units``' answer.

All of it runs inside :func:`_fixtures.expression_library`, a redirected tree
carrying a small but real faceunits01 pack, so the shape keys genuinely load.
"""

# pylint: disable=protected-access

from .._fixtures import Character
from .._fixtures import expression_library
from .._fixtures import result
from .._fixtures import services_or_skip


def _get(basemesh):
    return result("get_expression", {"name": basemesh.name})


def test_an_unresolved_subject_is_an_answer():
    services_or_skip()
    answer = result("get_expression", {"name": "no such object anywhere"})

    assert answer["found"] is False
    assert answer["applied_expressions"] == []
    assert answer["matches_stack"] is None
    assert "faceunits01_installed" in answer


def test_a_fresh_character_wears_nothing_and_matches(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            answer = _get(character.basemesh)

    assert answer["found"] is True
    assert answer["applied_expressions"] == []
    assert answer["aggregate"] == {}
    assert answer["matches_stack"] is True
    assert answer["unexplained_face_units"] == []
    assert "exactly what the stack produces" in answer["message"]


def test_a_stack_applied_by_mpfb_explains_the_face(tmp_path):
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path) as paths:
            face_service.set_stack_weight(character.basemesh, "smile.json", 0.5)
            answer = _get(character.basemesh)

    assert answer["applied_expressions"] == [dict(
        fragment="smile.json", weight=0.5, resolved=True, path=paths["smile"],
        unresolved_reason=None)]
    assert answer["aggregate"] == {"jawOpen": 0.3, "mouthSmileLeft": 0.4,
                                   "mouthSmileRight": 0.4}
    assert answer["matches_stack"] is True, answer["unexplained_face_units"]
    assert answer["unresolved_count"] == 0


def test_a_unit_composed_on_top_of_the_stack_is_unexplained(tmp_path):
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path):
            face_service.set_stack_weight(character.basemesh, "smile.json", 1.0)
            # Composed on top, the way mpfb_set_face_units writes: directly.
            face_service.set_expression(character.basemesh, {"browInnerUp": 0.4,
                                                              "jawOpen": 0.2})
            answer = _get(character.basemesh)

    assert answer["matches_stack"] is False
    unexplained = {entry["face_unit"]: entry for entry in answer["unexplained_face_units"]}
    assert set(unexplained) == {"browInnerUp", "jawOpen"}
    assert unexplained["browInnerUp"]["from_stack"] == 0.0
    assert abs(unexplained["browInnerUp"]["live"] - 0.4) < 1e-4
    assert abs(unexplained["jawOpen"]["from_stack"] - 0.6) < 1e-4, \
        "a unit composed *down* from what the stack says is unexplained too"
    assert "mpfb_save_expression" in answer["message"]


def test_a_row_whose_file_is_gone_is_reported_and_contributes_nothing(tmp_path):
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path):
            face_service._write_applied_expressions(character.basemesh, [
                {"asset": "smile.json", "weight": 1.0},
                {"asset": "from_another_machine.json", "weight": 1.0}])
            face_service.rebuild_expression_stack(character.basemesh)
            answer = _get(character.basemesh)

    rows = {row["fragment"]: row for row in answer["applied_expressions"]}
    assert rows["from_another_machine.json"]["resolved"] is False
    assert rows["from_another_machine.json"]["unresolved_reason"] == "not_found"
    assert rows["smile.json"]["resolved"] is True
    assert answer["unresolved_count"] == 1
    assert answer["matches_stack"] is True, \
        "the missing row contributes nothing to a rebuild, so nothing is unexplained"
    assert "cannot be found" in answer["message"]


def test_a_sum_past_one_is_reported_as_clamped(tmp_path):
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path):
            # smile opens the jaw 0.6 and jaw opens it 0.7: 1.3, clamped to 1.0.
            face_service.set_stack_weight(character.basemesh, "smile.json", 1.0)
            face_service.set_stack_weight(character.basemesh, "jaw.json", 1.0)
            answer = _get(character.basemesh)

    assert answer["clamped_face_units"] == [dict(face_unit="jawOpen", sum=1.3, applied=1.0)]
    assert answer["aggregate"]["jawOpen"] == 1.0
    assert answer["matches_stack"] is True
    assert "clamped" in answer["message"]


def test_the_52_live_values_are_not_restated(tmp_path):
    """FR 027 requirement 12: those are mpfb_get_face_units' answer."""
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path):
            face_service.set_stack_weight(character.basemesh, "smile.json", 1.0)
            answer = _get(character.basemesh)

    assert "face_units" not in answer
    assert len(answer["aggregate"]) == 3, "only the units the stack sets"
    assert answer["unexplained_face_units"] == []
