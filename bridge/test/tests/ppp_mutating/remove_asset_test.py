"""
``remove_asset`` against a real MPFB: what comes off, and what stays behind.

Every test here **equips through ``add_asset``' own command first**, rather than
hand-building an object with the right properties. That is deliberate and it is
the only arrangement in which these assertions mean anything: what removal has
to undo is precisely what adding did, and a fixture assembled by hand would be a
second opinion about what MPFB's loading path produces.

The claims:

- **A basemesh or a rig is refused.** ``unload_mhclo_asset()`` checks nothing
  and would delete either, cheerfully, along with whichever mask modifier
  happened to match. This is the refusal that matters most, and it cannot be
  established anywhere but against a real character.
- **An asset with no ``asset_source`` is refused before anything is deleted.**
  MPFB would derive the delete group name ``Delete.`` from an empty property,
  match no modifier, and delete the object anyway - leaving a body masked under
  an asset that is no longer there.
- **The vertex group is left behind and the mesh datablock is orphaned**, both
  of which MPFB does silently and neither of which is a failure.
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


def _result(params=None):
    return _fixture_result("remove_asset", params)


def _equip(services, character, root, asset_type="Clothes"):
    """One garment on this character, through add_asset's own command."""
    write_loadable_mhclo(os.path.join(str(root), "clothes", "spike", "spike.mhclo"))
    with redirected_locations(services, user_data=str(root)):
        envelope = dispatch("add_asset", {
            "name": character.basemesh.name,
            "fragment": "spike/spike.mhclo",
            "asset_type": asset_type,
        })
    assert envelope["status"] == "ok", "the fixture equip should have succeeded: {!r}".format(
        envelope)
    assert envelope["result"]["added"] is True, envelope["result"]["message"]
    return envelope["result"]


def test_an_equipped_garment_comes_off():
    """commands.remove_asset on something add_asset put on"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "remove-asset-simple")
    with _Character() as character:
        added = _equip(services, character, root)
        asset_name = added["asset_object_name"]

        result = _result({"name": asset_name})

        assert result["performed"] is True, result["message"]
        assert result["removed"] is True
        assert asset_name not in bpy.data.objects, "the object should really be gone"
        assert asset_name in result["objects_removed"]
        assert result["basemesh_name"] == character.basemesh.name


def test_the_type_and_source_are_read_before_the_object_is_gone():
    """commands.remove_asset reports what only existed before the delete

    ``asset_source`` is what every modifier name is derived from, and it is gone
    the moment the object is removed - so a response assembled afterwards could
    describe almost nothing.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "remove-asset-readfirst")
    with _Character() as character:
        added = _equip(services, character, root)

        result = _result({"name": added["asset_object_name"]})

        assert result["object_type"] == "Clothes"
        assert result["asset_source"], "the recorded fragment must be in the answer"
        assert result["delete_group_name"] == "Delete.spike", \
            "the delete group name is derived from asset_source, got {!r}".format(
                result["delete_group_name"])


def test_a_basemesh_is_refused_by_name():
    """commands.remove_asset handed the character itself

    The refusal that matters most: ``unload_mhclo_asset()`` would delete it.
    """
    _services_or_skip()
    with _Character() as character:
        envelope = dispatch("remove_asset", {"name": character.basemesh.name})

        assert envelope["status"] == "ok"
        result = envelope["result"]
        assert result["removed"] is False
        assert result["blocked_by"] == "not_a_mesh_asset"
        assert result["performed"] is False
        assert character.basemesh.name in bpy.data.objects, "and it must still be there"
        assert result["known_mesh_asset_types"], "the refusal should say what this does remove"


def test_a_rig_is_refused_by_name():
    """commands.remove_asset handed an armature"""
    services = _services_or_skip()
    with _Character() as character:
        services["ObjectService"].activate_blender_object(character.basemesh)
        rig = services["HumanService"].add_builtin_rig(
            character.basemesh, "default", import_weights=True)

        result = _result({"name": rig.name})

        assert result["removed"] is False
        assert result["blocked_by"] == "not_a_mesh_asset"
        assert rig.name in bpy.data.objects


def test_an_asset_with_no_asset_source_is_refused_before_anything_is_deleted():
    """commands.remove_asset on an asset whose property was cleared

    MPFB would derive the name ``Delete.``, match no modifier, and delete the
    object anyway.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "remove-asset-nosource")
    with _Character() as character:
        added = _equip(services, character, root)
        asset = bpy.data.objects[added["asset_object_name"]]

        import sys  # pylint: disable=import-outside-toplevel
        objectservice_module = sys.modules[services["ObjectService"].__module__]
        objectservice_module.GeneralObjectProperties.set_value(
            "asset_source", "", entity_reference=asset)

        result = _result({"name": asset.name})

        assert result["removed"] is False
        assert result["blocked_by"] == "asset_source_missing"
        assert asset.name in bpy.data.objects, "nothing may be deleted on this path"


def test_an_unknown_name_is_an_answer():
    """commands.remove_asset naming an object that does not exist"""
    _services_or_skip()
    envelope = dispatch("remove_asset", {"name": "no-such-object-anywhere"})

    assert envelope["status"] == "ok"
    assert envelope["result"]["blocked_by"] == "not_found"
    assert envelope["result"]["performed"] is False


def test_what_mpfb_leaves_behind_is_reported_rather_than_claimed_clean():
    """commands.remove_asset names the vertex group and the orphaned mesh

    Neither is a failure; both are invisible unless said out loud.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "remove-asset-leftovers")
    with _Character() as character:
        added = _equip(services, character, root)

        result = _result({"name": added["asset_object_name"]})

        assert result["mesh_data_orphaned"], \
            "bpy.data.objects.remove() leaves the mesh datablock with no users"
        # The vertex group is only created when the MHCLO defines delete
        # vertices, so this is asserted as agreement rather than as a value.
        group_names = [group.name for group in character.basemesh.vertex_groups]
        reported = [entry["vertex_group"] for entry in result["vertex_groups_left_behind"]]
        for name in reported:
            assert name in group_names, \
                "{!r} was reported as left behind but is not on the body".format(name)


def test_the_name_is_required_by_the_contract():
    """commands.remove_asset with no name at all

    No active-object fallback anywhere: this deletes an object, and "whatever
    happens to be selected" is not a way to choose which.
    """
    _services_or_skip()
    envelope = dispatch("remove_asset", {})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "name" in envelope["message"]


def test_mpfb_being_unavailable_refuses_rather_than_half_removing():
    """commands.remove_asset against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("remove_asset", {"name": "anything"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
