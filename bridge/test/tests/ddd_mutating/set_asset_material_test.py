"""
``set_asset_material`` against a real MPFB: the reimplemented UI operator.

**The one command in the table with no service function behind it.** The
mechanism exists only in
``mpfb/ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py``, and
being an add-on now makes importing that module *possible* - which is exactly
why the rule against it is restated in the command's own docstring and why this
module checks the reimplementation against what MPFB really does rather than
against what it was read to do.

Three of that operator's quirks are asserted here, because each is something a
reimplementation would quietly improve on and each would then make this command
disagree with MPFB's own panel:

- **the result is always a MakeSkin material under the fixed name**
  ``makeskinmaterial``, whatever the asset had before;
- **the slots are popped rather than deleted**, so ``materials_destroyed`` means
  "removed from the object" and not "destroyed";
- **the viewport colour is keyed on the object's recorded ``object_type``**,
  with a neutral grey when the type is not in MPFB's table - so a mislabelled
  asset gets the wrong colour here too, which is why ``diffuse_color_from`` is
  reported.

The asset is equipped through ``add_asset``'s own command first, for the reason
``remove_asset``'s module does the same: the material this command replaces is
exactly the one that command built.
"""

import os

import bpy

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import redirected_locations
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution
from .._fixtures import write_loadable_mhclo
from .._fixtures import write_mhmat


def _result(params=None):
    return _fixture_result("set_asset_material", params)


def _dressed(services, character, root):
    """One garment with two alternative materials beside it, equipped."""
    root = str(root)
    write_loadable_mhclo(os.path.join(root, "clothes", "spike", "spike.mhclo"))
    alternative = write_mhmat(os.path.join(root, "clothes", "spike", "spike_red.mhmat"))
    with redirected_locations(services, user_data=root):
        envelope = dispatch("add_asset", {
            "name": character.basemesh.name,
            "fragment": "spike/spike.mhclo",
            "object_type": "Clothes",
        })
    assert envelope["status"] == "ok", "the fixture equip should have succeeded: {!r}".format(
        envelope)
    assert envelope["result"]["added"] is True, envelope["result"]["message"]
    return (envelope["result"]["asset_object_name"], alternative)


def _material_names(blender_object):
    return [slot.material.name for slot in blender_object.material_slots
            if slot.material is not None]


def test_an_alternative_material_is_applied_under_mpfbs_fixed_name():
    """commands.set_asset_material with an alternative MHMAT

    Whatever the asset had before, MPFB's panel builds a MakeSkin material
    called ``makeskinmaterial``. Reproduced rather than improved on.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-asset-material-apply")
    with _Character() as character:
        asset_name, alternative = _dressed(services, character, root)
        asset = bpy.data.objects[asset_name]

        with redirected_locations(services, user_data=root):
            result = _result({"name": asset_name, "path": alternative})

        assert result["performed"] is True, result["message"]
        assert result["applied"] is True
        assert result["material_name"].startswith("makeskinmaterial"), \
            "MPFB names it literally, whatever the asset had: got {!r}".format(
                result["material_name"])
        assert _material_names(asset) == [result["material_name"]], \
            "the object should carry exactly the new material"
        assert result["object_type"] == "Clothes"
        assert result["asset_subdir"] == "clothes"


def test_the_recorded_alternative_material_is_written_and_read_back():
    """commands.set_asset_material records what get_object_info will report

    The write half of a property whose read half ``get_object_info`` already
    has. Both derive the asset subdir as ``str(object_type).lower()``, which is
    why they agree.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-asset-material-recorded")
    with _Character() as character:
        asset_name, alternative = _dressed(services, character, root)

        with redirected_locations(services, user_data=root):
            result = _result({"name": asset_name, "path": alternative})
            info = _fixture_result("get_object_info", {"name": asset_name})

        assert result["alternative_material"], "an alternative should have been recorded"
        assert result["alternative_material_before"] is None, \
            "there was none before this call"
        # ``get_object_info`` reports it as ``material_source`` - the field is
        # named for what it *is* to a reader of that answer (where this asset's
        # material came from) rather than for the property it is stored in.
        # This is the one place the two halves are checked against each other.
        asset_info = info.get("asset_info") or {}
        assert asset_info.get("material_source") == result["alternative_material"], \
            "get_object_info should read back what this wrote: {!r} against {!r}".format(
                asset_info.get("material_source"), result["alternative_material"])


def test_restore_default_puts_back_the_mhclos_own_material_and_clears_the_record():
    """commands.set_asset_material with restore_default"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-asset-material-restore")
    with _Character() as character:
        asset_name, alternative = _dressed(services, character, root)

        with redirected_locations(services, user_data=root):
            _result({"name": asset_name, "path": alternative})
            restored = _result({"name": asset_name, "restore_default": True})

        assert restored["applied"] is True, restored["message"]
        assert restored["resolved_by"] == "default"
        assert restored["resolved_path"].endswith("spike.mhmat"), \
            "the MHCLO's own material line should have been followed, got {!r}".format(
                restored["resolved_path"])
        assert restored["alternative_material"] is None, \
            "the record is cleared on a restore, exactly as MPFB's panel does"
        assert restored["alternative_material_before"], \
            "and the answer should say what was cleared"


def test_the_slots_are_popped_rather_than_destroyed():
    """commands.set_asset_material reports removal, not destruction

    ``_apply_mhmat()`` pops ``obj.data.materials`` rather than calling
    ``delete_all_materials(..., also_destroy_groups=True)``, so the previous
    material's node groups survive in the file. That is a real difference from
    set_skin and the field name means what it means because of it.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-asset-material-popped")
    with _Character() as character:
        asset_name, alternative = _dressed(services, character, root)
        asset = bpy.data.objects[asset_name]
        before = _material_names(asset)

        with redirected_locations(services, user_data=root):
            result = _result({"name": asset_name, "path": alternative})

        assert result["materials_destroyed"] == before, \
            "the answer should name the slots that were removed: {!r} against {!r}".format(
                result["materials_destroyed"], before)
        for name in before:
            assert name in bpy.data.materials, \
                "{!r} was popped from the object, not destroyed, so it is still in the " \
                "file".format(name)
        assert "pops the slots" in result["message"]


def test_the_viewport_colour_is_keyed_on_the_recorded_object_type():
    """commands.set_asset_material reports where the diffuse colour came from

    A mislabelled asset gets the wrong viewport colour here too, which is why
    this is reported rather than silently applied.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-asset-material-colour")
    with _Character() as character:
        asset_name, alternative = _dressed(services, character, root)

        with redirected_locations(services, user_data=root):
            result = _result({"name": asset_name, "path": alternative})

        colours = services["MaterialService"].get_diffuse_colors()
        expected = "Clothes" if "Clothes" in colours else None
        assert result["diffuse_color_from"] == expected, \
            "the colour must come from MPFB's own table keyed on the object type, or from " \
            "nowhere; MPFB's table holds {!r}".format(sorted(colours))


def test_a_basemesh_is_refused_the_way_mpfbs_own_panel_refuses_it():
    """commands.set_asset_material handed the character itself

    A basemesh carries a *skin* rather than an asset material, which is
    set_skin's job.
    """
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name, "path": "/a.mhmat"})

        assert result["applied"] is False
        assert result["blocked_by"] == "type_not_supported"
        assert result["performed"] is False
        assert "mpfb_set_skin" in result["message"]
        assert "Basemesh" in result["refused_types"]


def test_an_object_with_no_mpfb_type_is_refused():
    """commands.set_asset_material on a plain Blender object"""
    _services_or_skip()
    plain = bpy.data.objects.new("PlainForMaterial", bpy.data.meshes.new("PlainForMaterialMesh"))
    bpy.context.scene.collection.objects.link(plain)
    try:
        result = _result({"name": "PlainForMaterial", "path": "/a.mhmat"})

        assert result["applied"] is False
        assert result["blocked_by"] == "not_an_mpfb_object"
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)


def test_restore_default_with_no_asset_source_is_refused_before_anything_changes():
    """commands.set_asset_material restoring an asset whose property was cleared"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-asset-material-nosource")
    with _Character() as character:
        asset_name, _alternative = _dressed(services, character, root)
        asset = bpy.data.objects[asset_name]
        before = _material_names(asset)

        import sys  # pylint: disable=import-outside-toplevel
        objectservice_module = sys.modules[services["ObjectService"].__module__]
        objectservice_module.GeneralObjectProperties.set_value(
            "asset_source", "", entity_reference=asset)

        result = _result({"name": asset_name, "restore_default": True})

        assert result["applied"] is False
        assert result["blocked_by"] == "asset_source_missing"
        assert _material_names(asset) == before, "nothing may change on this path"


def test_a_path_naming_no_file_is_an_answer():
    """commands.set_asset_material with a path that does not exist"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-asset-material-nofile")
    with _Character() as character:
        asset_name, _alternative = _dressed(services, character, root)

        result = _result({"name": asset_name, "path": "/no/such/material.mhmat"})

        assert result["applied"] is False
        assert result["blocked_by"] == "material_not_found"


def test_the_name_is_required_by_the_contract():
    """commands.set_asset_material with no name at all"""
    _services_or_skip()
    envelope = dispatch("set_asset_material", {"path": "/a.mhmat"})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "name" in envelope["message"]


def test_mpfb_being_unavailable_refuses_rather_than_stripping_the_asset():
    """commands.set_asset_material against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("set_asset_material", {"name": "anything", "path": "/a.mhmat"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
