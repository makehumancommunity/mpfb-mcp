"""
``apply_expressions`` against a real MPFB: the stack, the rebuild, and the refusals.

The refusals are the half that matters most, because a refusal here must be
**no write at all**. MPFB's ``aggregate_expression_stack`` skips a row it cannot
resolve and carries on, so a command that wrote first and resolved second would
leave a stack claiming an expression the face never showed. Each refusal test
therefore asserts that the custom property is **byte-identical** afterwards, not
merely that ``performed`` is false.

Then the two modes, removal at ``0.0``, clearing with ``replace`` and an empty
list, clamping, and FR 027's requirement 20: units composed on top of the stack
before the call are gone after it, and are named.

Every test runs inside :func:`_fixtures.expression_library` (a redirected tree
with a small real faceunits01 pack), with the character built first, outside the
redirect, and ``refit`` off except where the refit is what is being tested.
"""

# pylint: disable=protected-access

import sys

from .._fixtures import Character
from .._fixtures import expression_library
from .._fixtures import only_these_data_roots
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip


def _apply(basemesh, expressions, mode="merge", refit=False):
    return _fixture_result("apply_expressions", {
        "name": basemesh.name, "expressions": expressions, "mode": mode, "refit": refit})


def _stored(services, basemesh):
    """The raw custom property, for byte-identical comparisons."""
    prop = sys.modules[services["FaceService"].__module__].APPLIED_EXPRESSIONS_PROP
    return basemesh.get(prop)


def _live(services, basemesh, unit):
    return services["FaceService"].read_current_expression(basemesh)[unit]


def test_an_unresolvable_fragment_refuses_and_leaves_the_stack_byte_identical(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            _apply(character.basemesh, [{"fragment": "smile.json", "weight": 0.5}])
            before = _stored(services, character.basemesh)

            answer = _apply(character.basemesh, [
                {"fragment": "jaw.json", "weight": 1.0},
                {"fragment": "simle.json", "weight": 1.0}])

            assert _stored(services, character.basemesh) == before
            assert abs(_live(services, character.basemesh, "jawOpen") - 0.3) < 1e-4, \
                "the resolvable row in the same batch must not have been applied either"

    assert answer["ready"] is False
    assert answer["blocked_by"] == "unresolved_fragments"
    assert answer["performed"] is False
    assert answer["changed"] is False
    assert [row["fragment"] for row in answer["unresolved_fragments"]] == ["simle.json"]
    assert "smile.json" in answer["unresolved_fragments"][0]["closest"]
    assert "smile.json" in answer["available_fragments"]


def test_the_pack_absent_refuses_and_writes_nothing_to_the_stack(tmp_path):
    """Requirement 18's whole point: the stack write would persist."""
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path) as paths:
            before = _stored(services, character.basemesh)
            # The expressions stay; the pack goes.
            with only_these_data_roots(services, user_data=paths["user"] + "-no-pack",
                                       mpfb_data=paths["system"]):
                face_service.is_faceunits01_installed(force_recheck=True)
                try:
                    answer = _apply(character.basemesh,
                                    [{"fragment": "shadowing.json", "weight": 1.0}])
                finally:
                    face_service.is_faceunits01_installed(force_recheck=True)
            after = _stored(services, character.basemesh)

    assert answer["blocked_by"] == "faceunits01_not_installed"
    assert answer["performed"] is False
    assert after == before


def test_merge_upserts_and_leaves_other_rows_alone(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            first = _apply(character.basemesh, [{"fragment": "smile.json", "weight": 0.5}])
            second = _apply(character.basemesh, [{"fragment": "jaw.json", "weight": 0.2},
                                                 {"fragment": "smile.json", "weight": 1.0}])

    assert first["performed"] is True
    assert [row["action"] for row in first["requested"]] == ["added"]
    assert {row["fragment"]: row["action"] for row in second["requested"]} == {
        "jaw.json": "added", "smile.json": "updated"}
    assert second["requested"][1]["previous_weight"] == 0.5
    assert [(row["fragment"], row["weight"]) for row in second["applied_expressions"]] == [
        ("jaw.json", 0.2), ("smile.json", 1.0)], "sorted by fragment, as MPFB writes it"
    assert second["stack_before"] == [dict(fragment="smile.json", weight=0.5)]
    assert second["matches_stack"] is True


def test_replace_replaces_and_says_what_it_took_off(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            _apply(character.basemesh, [{"fragment": "smile.json", "weight": 0.5}])
            answer = _apply(character.basemesh, [{"fragment": "jaw.json", "weight": 0.4}],
                            mode="replace")
            smile = _live(services, character.basemesh, "mouthSmileLeft")

    assert [row["fragment"] for row in answer["applied_expressions"]] == ["jaw.json"]
    assert answer["removed_by_replace"] == ["smile.json"]
    assert abs(smile) < 1e-6, "the rebuild should have cleared what smile contributed"
    assert answer["aggregate"] == {"jawOpen": 0.28}, "jaw.json opens it 0.7, at 0.4"


def test_a_weight_of_zero_removes_a_row_and_a_missing_one_is_absent(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            _apply(character.basemesh, [{"fragment": "smile.json", "weight": 0.5},
                                        {"fragment": "jaw.json", "weight": 0.5}])
            answer = _apply(character.basemesh, [
                {"fragment": "smile.json", "weight": 0.0},
                {"fragment": "never_applied.json", "weight": 0.0}])

    assert {row["fragment"]: row["action"] for row in answer["requested"]} == {
        "smile.json": "removed", "never_applied.json": "absent"}
    assert [row["fragment"] for row in answer["applied_expressions"]] == ["jaw.json"]


def test_removing_a_row_whose_file_is_gone_is_allowed(tmp_path):
    """Removal is not resolved: it is how a stack from another machine is cleaned."""
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path):
            face_service._write_applied_expressions(character.basemesh, [
                {"asset": "from_another_machine.json", "weight": 1.0}])
            answer = _apply(character.basemesh,
                            [{"fragment": "from_another_machine.json", "weight": 0.0}])

    assert answer["ready"] is True
    assert answer["applied_expressions"] == []
    assert answer["performed"] is True


def test_replace_with_an_empty_list_clears_everything(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            _apply(character.basemesh, [{"fragment": "smile.json", "weight": 1.0}])
            answer = _apply(character.basemesh, [], mode="replace")
            jaw = _live(services, character.basemesh, "jawOpen")

    assert answer["applied_expressions"] == []
    assert answer["aggregate"] == {}
    assert answer["removed_by_replace"] == ["smile.json"]
    assert abs(jaw) < 1e-6
    assert answer["performed"] is True


def test_a_sum_past_one_is_reported_as_clamped(tmp_path):
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            answer = _apply(character.basemesh, [{"fragment": "smile.json", "weight": 1.0},
                                                 {"fragment": "jaw.json", "weight": 1.0}])

    assert answer["clamped_face_units"] == [dict(face_unit="jawOpen", sum=1.3, from_stack=1.0)]
    assert "clamped" in answer["message"]


def test_units_composed_before_the_call_are_discarded_and_named(tmp_path):
    """Requirement 20: the rebuild destroys composed work; the answer says so."""
    services = services_or_skip()
    face_service = services["FaceService"]
    with Character() as character:
        with expression_library(services, tmp_path):
            face_service.set_expression(character.basemesh, {"browInnerUp": 0.4})
            answer = _apply(character.basemesh, [{"fragment": "jaw.json", "weight": 0.5}])
            brow = _live(services, character.basemesh, "browInnerUp")

    assert [entry["face_unit"] for entry in answer["discarded_face_units"]] == ["browInnerUp"]
    assert abs(answer["discarded_face_units"][0]["live"] - 0.4) < 1e-4
    assert abs(brow) < 1e-6, "the composed unit really is gone"
    assert "mpfb_save_expression" in answer["message"]
    assert answer["matches_stack"] is True


def test_nothing_composed_means_nothing_discarded(tmp_path):
    """Requirement 36: the normal case must not read as a warning."""
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path):
            answer = _apply(character.basemesh, [{"fragment": "jaw.json", "weight": 0.5}])

    assert answer["discarded_face_units"] == []
    assert "discarded" not in answer["message"]


def test_a_fragment_resolved_by_basename_reports_both_files(tmp_path):
    """find_asset_absolute_path matches by basename; the answer shows where it landed."""
    services = services_or_skip()
    with Character() as character:
        with expression_library(services, tmp_path) as paths:
            answer = _apply(character.basemesh,
                            [{"fragment": "shadowing.json", "weight": 1.0}])

    row = answer["requested"][0]
    assert row["resolved_path"] == paths["shadowing"], \
        "the system copy comes first and wins, as it does in MPFB's listing"
    assert row["listed_path"] == paths["shadowing"]


def test_the_panel_sliders_follow_the_stack(tmp_path):
    services = services_or_skip()
    import bpy  # pylint: disable=import-outside-toplevel
    with Character() as character:
        with expression_library(services, tmp_path):
            panel = sys.modules[
                services["FaceService"].__module__.rsplit(".services.", 1)[0]
                + ".ui.apply_assets.useexpression"]
            panel.refresh_expression_sliders()
            answer = _apply(character.basemesh, [{"fragment": "jaw.json", "weight": 0.3}])
            slider = [identifier for identifier, entry in panel._EXPRESSION_PROP_MAP.items()
                      if entry["asset"] == "jaw.json"]
            value = getattr(bpy.context.scene, slider[0]) if slider else None

    assert answer["panel_synced"] is True, answer["panel_sync_reason"]
    assert value is not None and abs(value - 0.3) < 1e-6


def test_a_refit_happens_when_the_face_changed_and_the_selection_survives_it(tmp_path):
    services = services_or_skip()
    import bpy  # pylint: disable=import-outside-toplevel
    with Character() as character:
        bystander = bpy.data.objects.new("fr027_bystander", None)
        bpy.context.scene.collection.objects.link(bystander)
        bpy.context.view_layer.objects.active = bystander
        character.basemesh.select_set(False)
        with expression_library(services, tmp_path):
            answer = _apply(character.basemesh, [{"fragment": "jaw.json", "weight": 0.3}],
                            refit=True)
        active = bpy.context.view_layer.objects.active
        active_after = None if active is None else active.name
        basemesh_selected_after = character.basemesh.select_get()

    assert answer["refit_requested"] is True
    assert answer["refit_performed"] is True
    assert answer["assets_possibly_stale"] is None
    assert active_after == "fr027_bystander"
    assert basemesh_selected_after is False
