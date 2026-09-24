"""
The expression tools together, against a real MPFB: one answer, and one round trip.

**Not one command's module, and deliberately.** Two claims in FR 027 are about
several commands at once and mean nothing asserted separately:

- ``shared/expression_divergence.py`` exists so that ``set_face_units``,
  ``get_expression`` and ``apply_expressions`` report **the same** divergence.
  A copy growing in one of them would still pass each command's own tests; it
  is caught only by asking all three about one character, in the shape the
  ``modifier_reading.py`` users share.
- the gap FR 026 left open - a composed face survives nothing - is closed by
  compose, save, apply ``replace`` at ``1.0``. That the face comes back within
  the file's four-decimal rounding and the stack then explains it is a claim
  about three commands in sequence.

Both run inside :func:`_fixtures.expression_library`, with the character built
first, and with ``refit`` off because a refit is not what is being tested.
"""

from .._fixtures import Character
from .._fixtures import expression_library
from .._fixtures import result
from .._fixtures import services_or_skip


def _units(entries):
    return [(entry["face_unit"], entry["live"], entry["from_stack"]) for entry in entries]


def test_the_three_divergence_users_agree_about_one_character(tmp_path):
    services = services_or_skip()
    with Character() as character:
        name = character.basemesh.name
        with expression_library(services, tmp_path):
            result("apply_expressions", {
                "name": name, "expressions": [{"fragment": "smile.json", "weight": 1.0}],
                "refit": False})
            composed = result("set_face_units", {
                "name": name, "refit": False,
                "face_units": [{"face_unit": "browInnerUp", "weight": 0.4},
                               {"face_unit": "jawOpen", "weight": 0.1}]})
            read = result("get_expression", {"name": name})
            applied = result("apply_expressions", {
                "name": name, "expressions": [{"fragment": "jaw.json", "weight": 0.5}],
                "refit": False})

    assert composed["matches_stack"] is False
    assert read["matches_stack"] is False
    assert _units(composed["unexplained_face_units"]) == _units(read["unexplained_face_units"])
    assert _units(applied["discarded_face_units"]) == _units(read["unexplained_face_units"]), \
        "what apply_expressions discarded is exactly what get_expression called unexplained"
    assert [entry[0] for entry in _units(read["unexplained_face_units"])] == [
        "browInnerUp", "jawOpen"]


def test_set_face_units_on_a_character_with_no_stack_is_not_a_warning(tmp_path):
    """The common case: nothing on the stack, nothing composed. It must not alarm."""
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            answer = result("set_face_units", {
                "name": character.basemesh.name, "face_units": [], "refit": False})

    assert answer["matches_stack"] is True
    assert answer["unexplained_face_units"] == []
    assert answer["applied_expression_count"] == 0
    assert "transient" not in answer["message"]
    assert "overwrite" not in answer["message"]


def test_compose_save_apply_returns_the_composed_face_and_the_stack_explains_it(tmp_path):
    """FR 026's gap, closed: the sequence every answer in this effort points at."""
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        name = character.basemesh.name
        with expression_library(services, tmp_path):
            # Something on the stack first, so the saved file must hold the
            # stack's contribution too and `replace` is the only right mode.
            result("apply_expressions", {
                "name": name, "expressions": [{"fragment": "jaw.json", "weight": 0.5}],
                "refit": False})
            result("set_face_units", {
                "name": name, "refit": False,
                "face_units": [{"face_unit": "browInnerUp", "weight": 0.33333},
                               {"face_unit": "mouthSmileLeft", "weight": 0.6}]})
            composed = face_service.read_current_expression(character.basemesh)

            saved = result("save_expression", {"expression_name": "kept", "name": name})
            applied = result("apply_expressions", dict(
                name=name, refit=False, **saved["apply_with"]))
            after = face_service.read_current_expression(character.basemesh)
            read = result("get_expression", {"name": name})

    assert saved["saved"] is True
    assert applied["discarded_face_units"] == [], \
        "the saved file already holds the composed units, so nothing composed is lost"
    for unit, value in composed.items():
        assert abs(after[unit] - value) <= 0.00006, \
            "{:s} came back as {!r}, composed as {!r}".format(unit, after[unit], value)
    assert read["matches_stack"] is True
    assert [row["fragment"] for row in read["applied_expressions"]] == ["kept.json"]
