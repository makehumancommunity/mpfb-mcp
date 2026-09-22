"""
``add_asset`` against a real MPFB: the import, the fit, and what MPFB never says.

The command wraps ``HumanService.add_mhclo_asset()``, which does a great deal
and reports almost none of it. So what is asserted here is the *reporting* -
against a real import rather than against a stub that was written from the same
reading of MPFB's source as the code under test:

- **the asset is really on the character**, named as the answer names it, with
  the ``object_type`` MPFB recorded;
- **the vocabulary checks are real refusals**, and ``asset_type`` is required
  because MPFB's own ``"Clothes"`` default mislabels six of the eight types
  silently;
- **the warnings fire on the states that produce them** - no rig at attachment
  time, no ``.mhw`` beside the asset - because each is something MPFB does in
  complete silence.

**The asset library is a redirected data root**, not a bare temporary
directory, which is [the spike's](../../../../feature-requests/032-creation-and-modification-migrated/SPIKE.md)
other finding: ``AssetService`` searches the roots, so an asset outside them can
be equipped by absolute path and then never re-found. Only ``user_data`` is
redirected, because equipping reaches MPFB's own bundled ``node_trees`` through
``mpfb_data``.
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
    return _fixture_result("add_asset", params)


def _library(root, material=True):
    """One garment under a directory that will be a redirected data root."""
    return write_loadable_mhclo(
        os.path.join(str(root), "clothes", "spike", "spike.mhclo"), material=material)


def test_a_garment_is_equipped_and_reported_by_the_name_it_got():
    """commands.add_asset with an absolute path"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-simple")
    mhclo = _library(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name,
                              "path": mhclo, "asset_type": "Clothes"})

        assert result["performed"] is True, result["message"]
        assert result["added"] is True
        assert result["asset_object_name"] in bpy.data.objects, \
            "the reported name must be the name the object really has"
        equipped = bpy.data.objects[result["asset_object_name"]]
        assert services["ObjectService"].get_object_type(equipped) == "Clothes", \
            "MPFB should have recorded the type that was asked for"
        assert result["object_type_recorded"] == "Clothes"
        assert result["resolved_by"] == "path"
        assert result["resolved_path"] == mhclo
        assert result["objects_created"], "the answer should name what appeared"


def test_a_fragment_is_resolved_against_the_subdir_its_asset_type_names():
    """commands.add_asset with a portable fragment rather than a path

    The half of the catalogue contract this command is the consumer of:
    ``list_assets`` reports an ``object_type`` and a ``fragment``, and turning
    the first into the asset subdir needed to resolve the second is what
    ``shared/asset_sections.py`` is for.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-fragment")
    mhclo = _library(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name,
                              "fragment": "spike/spike.mhclo", "asset_type": "Clothes"})

        assert result["added"] is True, result["message"]
        assert result["resolved_by"] == "fragment"
        assert result["resolved_path"] == mhclo, \
            "the fragment should have resolved to the fixture file, got {!r}".format(
                result["resolved_path"])
        assert result["asset_subdir"] == "clothes"


def test_an_unknown_asset_type_is_an_answer_with_the_vocabulary_beside_it():
    """commands.add_asset with a type MPFB's section table does not hold"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-badtype")
    mhclo = _library(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            envelope = dispatch("add_asset", {"name": character.basemesh.name,
                                              "path": mhclo, "asset_type": "Trousers"})

        assert envelope["status"] == "ok", \
            "an unknown type is an answer, not a failure: {!r}".format(envelope)
        result = envelope["result"]
        assert result["added"] is False
        assert result["blocked_by"] == "unknown_asset_type"
        assert result["known_asset_types"], "the refusal must say what MPFB accepts"
        assert "Clothes" in result["known_asset_types"]


def test_a_path_naming_no_file_is_an_answer():
    """commands.add_asset with a path that does not exist"""
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name,
                          "path": "/no/such/asset/anywhere.mhclo", "asset_type": "Clothes"})

        assert result["added"] is False
        assert result["blocked_by"] == "asset_not_found"
        assert result["performed"] is False


def test_a_fragment_resolving_to_nothing_is_an_answer():
    """commands.add_asset with a fragment no data root holds"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-nofragment")
    _library(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name,
                              "fragment": "nowhere/nothing.mhclo", "asset_type": "Clothes"})

        assert result["added"] is False
        assert result["blocked_by"] == "asset_not_found"
        assert "asset_type" in result["message"], \
            "the sentence should say that a fragment is resolved per subdir"


def test_an_unrigged_character_gets_a_parented_asset_and_a_warning():
    """commands.add_asset before the character has a rig

    MPFB rigs a garment only if a rig exists at the moment it is attached, and
    nothing rigs it afterwards - not refit_human either. MPFB says nothing at
    all about this.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-norig")
    mhclo = _library(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name,
                              "path": mhclo, "asset_type": "Clothes"})

        assert result["added"] is True
        assert result["rigged_to"] is None
        assert result["parented_to"] == character.basemesh.name
        assert any("no rig" in warning for warning in result["warnings"]), \
            "the silent ordering mistake must be warned about: {!r}".format(result["warnings"])


def test_a_rigged_character_gets_a_rigged_asset():
    """commands.add_asset after the character has a rig"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-rigged")
    mhclo = _library(root)
    with _Character() as character:
        services["ObjectService"].activate_blender_object(character.basemesh)
        rig = services["HumanService"].add_builtin_rig(
            character.basemesh, "default", import_weights=True)

        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name,
                              "path": mhclo, "asset_type": "Clothes"})

        assert result["added"] is True, result["message"]
        assert result["rigged_to"] == rig.name
        assert rig.name in result["armature_modifier_targets"], \
            "the asset should be deformed by the rig, not merely parented to it"


def test_missing_weights_beside_the_asset_are_reported():
    """commands.add_asset where no .mhw ships beside the MHCLO

    MPFB guards every weights read with ``os.path.isfile()`` and says nothing
    when the file is absent.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-noweights")
    mhclo = _library(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name,
                              "path": mhclo, "asset_type": "Clothes"})

        assert result["weights_files_beside_asset"] == []
        assert any(".mhw" in warning for warning in result["warnings"])


def test_an_mhclo_with_no_material_line_is_warned_about():
    """commands.add_asset on an MHCLO naming no material

    ``add_mhclo_asset()`` guards its whole material block with ``if
    mhclo.material is not None``, so this produces an object with no material
    and no complaint.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-nomaterial")
    mhclo = _library(root, material=False)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name,
                              "path": mhclo, "asset_type": "Clothes"})

        assert result["added"] is True
        assert result["mhclo_names_material"] is False
        assert any("names no material" in warning for warning in result["warnings"])


def test_subdiv_levels_zero_adds_no_modifier():
    """commands.add_asset with subdivision off

    Read off the asset rather than assumed from the argument: MPFB skips the
    modifier entirely at zero.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-nosubdiv")
    mhclo = _library(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name, "path": mhclo,
                              "asset_type": "Clothes", "subdiv_levels": 0})

        assert result["added"] is True
        assert result["subdiv_modifier_added"] is False


def test_the_callers_selection_and_active_object_are_restored():
    """commands.add_asset puts back what it borrowed"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "add-asset-selection")
    mhclo = _library(root)
    with _Character() as character:
        bystander = bpy.data.objects.new("AssetBystander",
                                         bpy.data.meshes.new("AssetBystanderMesh"))
        bpy.context.scene.collection.objects.link(bystander)
        services["ObjectService"].activate_blender_object(bystander)
        character.basemesh.select_set(False)

        with redirected_locations(services, user_data=root):
            _result({"name": character.basemesh.name, "path": mhclo, "asset_type": "Clothes"})

        assert bpy.context.view_layer.objects.active is bystander
        assert character.basemesh.select_get() is False


def test_the_asset_type_is_required_by_the_contract():
    """commands.add_asset with no asset_type at all

    Required, and deliberately: MPFB's own default of "Clothes" is wrong for six
    of the eight types and mislabels a body part with no error anywhere.
    """
    _services_or_skip()
    envelope = dispatch("add_asset", {"path": "/a.mhclo"})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "asset_type" in envelope["message"]


def test_mpfb_being_unavailable_refuses_rather_than_half_equipping():
    """commands.add_asset against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("add_asset", {"path": "/a.mhclo", "asset_type": "Clothes"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
