"""
``refit_human`` against a real MPFB, including the failure MPFB cannot report.

This module carries the claim that makes ``refit_human`` worth more than a bare
``HumanService.refit()`` call, and it is a claim no stub could establish: that a
**generated Rigify rig with no meta rig in the scene is not refitted**, that
MPFB says nothing about it, and that this command therefore answers
``refit_performed: false`` rather than reporting a refit it never made. Getting
there needs Rigify, a real generation and a real deletion, all of which
[the spike](../../../../feature-requests/done/032-creation-and-modification-migrated/SPIKE.md)
established work in a Blender with no window before any of this was written.

**The garment is equipped from a redirected data root**, not from a bare
temporary directory, because ``ClothesService.fit_clothes_to_human()`` re-reads
a garment's MHCLO through ``AssetService``. That is the spike's other finding
and it is the difference between this module testing a refit and this module
testing an ``IOError``. See [`ddd_mutating/__init__.py`](__init__.py).

**Every test here runs inside a ``Character`` block**, so the rig, the garment
and anything Rigify generated are all new objects that the fixture deletes
however the test ends. Nothing here needs cleanup code of its own, which is the
property that makes a *failing* mutating test safe to leave in a suite.
"""

import os

import bpy
import pytest

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import redirected_locations
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution
from .._fixtures import write_loadable_mhclo


def _result(params=None):
    return _fixture_result("refit_human", params)


def _equip(services, character, root):
    """One real garment on this character, from a root MPFB can search again.

    **Only ``user_data`` is redirected**, not every data root. Equipping reaches
    MPFB's own bundled ``node_trees/makeskin.json`` through ``mpfb_data``, so a
    fixture that pointed all four roots at temporary directories - which is what
    a read-only catalogue test wants - would fail here with a missing file
    rather than an unequipped garment. What this needs is one *extra* root that
    MPFB will search again on the way back in.
    """
    mhclo = write_loadable_mhclo(os.path.join(str(root), "clothes", "spike", "spike.mhclo"))
    with redirected_locations(services, user_data=str(root)):
        services["ObjectService"].activate_blender_object(character.basemesh)
        equipped = services["HumanService"].add_mhclo_asset(
            mhclo, character.basemesh, asset_type="Clothes")
    assert equipped is not None, "the fixture garment should have been equipped"
    return equipped


def test_an_unrigged_character_is_refitted_and_says_so():
    """commands.refit_human on a character with no rig"""
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name})

        assert result["found"] is True
        assert result["ready"] is True
        assert result["refit_performed"] is True
        assert result["performed"] is True, "performed is set from refit_performed"
        assert result["rig_object_name"] is None
        assert result["refit_incomplete_reason"] is None
        assert "no rig" in result["message"]


def test_a_dressed_character_reports_what_was_refitted():
    """commands.refit_human with a garment equipped from a data root"""
    services = _services_or_skip()
    with _Character() as character:
        root = os.path.join(bpy.app.tempdir, "refit-fixture")
        equipped = _equip(services, character, root)

        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name})

        assert result["refit_performed"] is True, result["message"]
        assert equipped.name in result["mesh_assets"], \
            "the equipped garment should be named among what was refitted, got {!r}".format(
                result["mesh_assets"])
        assert result["mesh_asset_count"] == len(result["mesh_assets"])


def test_the_subject_may_be_any_object_in_the_family():
    """commands.refit_human addressed by a garment's name rather than the basemesh's"""
    services = _services_or_skip()
    with _Character() as character:
        root = os.path.join(bpy.app.tempdir, "refit-family")
        equipped = _equip(services, character, root)

        with redirected_locations(services, user_data=root):
            result = _result({"name": equipped.name})

        assert result["found"] is True
        assert result["basemesh_name"] == character.basemesh.name, \
            "the basemesh is resolved from whatever object was named"
        assert result["subject_name"] == equipped.name
        assert result["subject_resolved_by"] == "name"


def test_the_active_object_is_used_when_no_name_is_given():
    """commands.refit_human with no name at all"""
    services = _services_or_skip()
    with _Character() as character:
        services["ObjectService"].activate_blender_object(character.basemesh)

        result = _result()

        assert result["found"] is True
        assert result["subject_resolved_by"] == "active"
        assert result["basemesh_name"] == character.basemesh.name


def test_an_unresolvable_name_is_an_answer_rather_than_an_error():
    """commands.refit_human naming an object that does not exist"""
    _services_or_skip()
    envelope = dispatch("refit_human", {"name": "no-such-object-anywhere"})

    assert envelope["status"] == "ok", \
        "a missing subject is an answer, not a failure: {!r}".format(envelope)
    result = envelope["result"]
    assert result["found"] is False
    assert result["performed"] is False
    assert "no-such-object-anywhere" in result["message"]


def test_an_object_outside_a_character_is_an_answer_not_a_valueerror():
    """commands.refit_human on a plain Blender object

    ``HumanService.refit()`` raises ``ValueError`` when it cannot find a
    basemesh. Resolving one first is what turns that into an answer, and this
    is the test that says the resolution really happens before the call.
    """
    _services_or_skip()
    plain = bpy.data.objects.new("PlainForRefit", bpy.data.meshes.new("PlainForRefitMesh"))
    bpy.context.scene.collection.objects.link(plain)
    try:
        envelope = dispatch("refit_human", {"name": "PlainForRefit"})

        assert envelope["status"] == "ok", \
            "refit() would have raised ValueError here; this must answer instead: {!r}".format(
                envelope)
        assert envelope["result"]["found"] is False
        assert envelope["result"]["subject_name"] == "PlainForRefit", \
            "the object was found; what it has no basemesh among its relatives"
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)


def _generated_rig(services, character, meta_rig_action):
    """A real generated Rigify rig on this character, or a skip saying why not."""
    if not services["SystemService"].check_for_rigify():
        pytest.skip("Rigify is not enabled in this Blender, so no rig can be generated")
    services["ObjectService"].activate_blender_object(character.basemesh)
    meta_rig = services["HumanService"].add_builtin_rig(
        character.basemesh, "rigify.human", import_weights=True)
    assert meta_rig is not None, "the fixture meta rig should have been added"
    generated = services["RigService"].generate_rigify_rig(
        meta_rig, name="", meta_rig_action=meta_rig_action)
    assert generated is not None, "Rigify should have generated a rig from MPFB's meta rig"
    return generated


def test_a_generated_rigify_rig_with_no_metarig_is_reported_not_claimed():
    """commands.refit_human on the one state MPFB refits silently incompletely

    The claim this whole command exists for. ``refit()`` refits the mesh assets,
    logs a warning, tries to report through an ``operator`` this add-on has none
    of, and returns - leaving the rig untouched with nothing in its return value
    to say so.
    """
    services = _services_or_skip()
    with _Character() as character:
        generated = _generated_rig(services, character, "delete")

        result = _result({"name": generated.name})

        assert result["ready"] is True, "this is a refusal about the rig, not about the call"
        assert result["refit_performed"] is False, \
            "the rig was not refitted, so this must not claim it was: {!r}".format(
                result["message"])
        assert result["performed"] is False, "performed is set from refit_performed"
        assert result["refit_incomplete_reason"] is not None
        assert "meta rig" in result["refit_incomplete_reason"]
        assert result["rig_object_name"] == generated.name


def test_the_answer_agrees_with_mpfbs_own_metarig_lookup():
    """commands.refit_human with the meta rig hidden rather than deleted

    **Written as an agreement rather than as an expected value, and that is
    deliberate.** What the command must do is reproduce
    ``ObjectService.find_rigify_metarig_by_rig()`` - the same test ``refit()``
    itself would make - so it is asserted against that lookup's own answer,
    whichever way the lookup goes.

    What that lookup answers **today** is ``None`` even here, where the meta rig
    is hidden and present: ``find_rigify_metarig_by_rig()`` reads
    ``armature.data.get("rigify_target_rig")``, and current Rigify stores
    ``rigify_target_rig`` as an RNA property rather than as an ID property, so
    the ID-property lookup finds nothing on any armature. The practical effect
    is that MPFB reports *every* generated Rigify rig as unrefittable. That is
    an MPFB defect, found while migrating this command and
    [left alone](../../../../feature-requests/done/032-creation-and-modification-migrated/README.md):
    reproduction over improvement, and it is recorded in NEXT_STEPS.md instead.
    Both transports read one statement of the condition, so they agree about it
    whether it is right or wrong.
    """
    services = _services_or_skip()
    with _Character() as character:
        generated = _generated_rig(services, character, "hide")
        metarig = services["ObjectService"].find_rigify_metarig_by_rig(generated)

        result = _result({"name": generated.name})

        assert result["refit_performed"] is (metarig is not None), \
            "the command must answer what MPFB's own lookup implies. Lookup found {!r}, " \
            "command answered refit_performed={!r}".format(metarig, result["refit_performed"])
        assert (result["refit_incomplete_reason"] is None) is (metarig is not None)
        assert result["performed"] is result["refit_performed"]


def test_an_ordinary_rig_is_never_mistaken_for_a_generated_rigify_one():
    """commands.refit_human on a character carrying MPFB's standard rig"""
    services = _services_or_skip()
    with _Character() as character:
        services["ObjectService"].activate_blender_object(character.basemesh)
        rig = services["HumanService"].add_builtin_rig(
            character.basemesh, "default", import_weights=True)
        assert rig is not None

        result = _result({"name": character.basemesh.name})

        assert result["refit_performed"] is True
        assert result["refit_incomplete_reason"] is None
        assert result["rig_object_name"] == rig.name
        assert "refitted as well" in result["message"]


def test_the_callers_selection_and_active_object_are_restored():
    """commands.refit_human puts back what it borrowed

    Twelve of the thirteen mutating commands do this; the user is looking at
    this scene, and a command that rearranges the selection as a side effect is
    one that cannot be called twice in a row without surprising somebody.
    """
    services = _services_or_skip()
    with _Character() as character:
        bystander = bpy.data.objects.new("Bystander", bpy.data.meshes.new("BystanderMesh"))
        bpy.context.scene.collection.objects.link(bystander)
        services["ObjectService"].activate_blender_object(bystander)
        character.basemesh.select_set(False)

        _result({"name": character.basemesh.name})

        assert bpy.context.view_layer.objects.active is bystander, \
            "the active object should be the one the caller left active"
        assert character.basemesh.select_get() is False, \
            "the basemesh was not selected before the call and must not be after it"


def test_a_basemesh_in_edit_mode_is_a_refusal_rather_than_an_attempt():
    """commands.refit_human while the basemesh is open in edit mode"""
    services = _services_or_skip()
    with _Character() as character:
        services["ObjectService"].activate_blender_object(character.basemesh)
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            result = _result({"name": character.basemesh.name})
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

        assert result["found"] is True
        assert result["ready"] is False
        assert result["blocked_by"] == "not_object_mode"
        assert result["performed"] is False


def test_mpfb_being_unavailable_refuses_rather_than_half_refitting():
    """commands.refit_human against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("refit_human")

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
