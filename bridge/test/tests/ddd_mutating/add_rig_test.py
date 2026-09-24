"""
``add_rig`` against a real MPFB, and against ``list_rigs``' own prediction.

The claim this module exists for is the pairing one: **what the catalogue
promised is what the adder delivers.** ``list_rigs`` predicts, per rig, which
file would load and whose weights come with it; ``add_rig`` does it. Both read
``shared/rig_lookup.py``, and since FR 032 both are commands here - so the
agreement can be asserted by asking one and then the other against **one real
install**, which is the only way it means anything.

Everything else here is a refusal, and each one exists because
``HumanService.add_builtin_rig()`` / ``add_custom_rig()`` **raise** rather than
report when handed no operator: an unknown identifier, a character that already
has a rig, a Blender without Rigify. A command that let those through would turn
an ordinary mistake into a ``command_failed`` envelope with a traceback in it.

The rigs are MPFB's own rather than a fixture tree. ``add_builtin_rig()`` builds
a real armature from a real rig definition, and a fixture rig file would be
testing this module's JSON rather than MPFB's loader - which is the opposite of
what a bridge test is for. ``list_rigs``' own module is where the fixture tree
belongs, and it has one.
"""

import bpy
import pytest

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution


def _result(params=None):
    return _fixture_result("add_rig", params)


def _catalogue_entry(identifier):
    """What ``list_rigs`` says about one rig, or ``None``."""
    listing = _fixture_result("list_rigs")
    for entry in listing["rigs"]:
        if entry["identifier"] == identifier:
            return entry
    return None


def test_a_standard_rig_is_added_and_named():
    """commands.add_rig with MPFB's own default rig"""
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name, "identifier": "default"})

        assert result["performed"] is True, result["message"]
        assert result["added"] is True
        assert result["family"] == "standard"
        assert result["add_function_used"] == "add_builtin_rig"
        assert result["rig_object_name"] in bpy.data.objects, \
            "the reported rig name must be the name the object really has"
        assert result["is_metarig"] is False
        assert result["next_step"] is None

        rig = bpy.data.objects[result["rig_object_name"]]
        assert rig.type == "ARMATURE"
        assert len(rig.data.bones) > 0, "a rig with no bones is not a rig"


def test_the_catalogue_prediction_is_what_the_adder_delivers():
    """commands.list_rigs then commands.add_rig, against one install

    The pairing claim, and the reason ``shared/rig_lookup.py`` exists. Asserted
    against the *same* Blender in the *same* test, which is the only arrangement
    in which "these two agree" is worth anything.
    """
    _services_or_skip()
    predicted = _catalogue_entry("default")
    if predicted is None:
        pytest.skip("this MPFB does not ship a rig called 'default'")

    with _Character() as character:
        actual = _result({"name": character.basemesh.name, "identifier": "default"})

        assert actual["rig_definition_path"] == predicted["path"], \
            "the catalogue named {!r} and the adder loaded {!r}".format(
                predicted["path"], actual["rig_definition_path"])
        assert actual["weights_loaded"] is predicted["has_weights"], \
            "the catalogue predicted has_weights={!r} and the adder reported " \
            "weights_loaded={!r}".format(predicted["has_weights"], actual["weights_loaded"])
        if actual["weights_loaded"]:
            assert actual["weights_from"] == predicted["weights_from"], \
                "the catalogue predicted weights from {!r}, the adder used {!r}".format(
                    predicted["weights_from"], actual["weights_from"])


def test_weights_are_really_loaded_onto_the_mesh():
    """commands.add_rig with import_weights on, checked against the basemesh

    ``weights_loaded`` is a prediction from a file's existence; this is the
    observation. The difference matters because MPFB reports a *missing* weights
    file through an operator only, so an unweighted rig is otherwise silent.
    """
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name, "identifier": "default"})

        assert result["armature_modifier_added"] is True, \
            "with weights the basemesh must be deformed by the armature, not merely parented"
        # See test_import_weights_false_loads_no_weights_and_says_so: the
        # modifier is not what import_weights decides.
        if result["weights_loaded"]:
            assert character.basemesh.vertex_groups, \
                "loading weights should have produced vertex groups on the basemesh"


def test_import_weights_false_loads_no_weights_and_says_so():
    """commands.add_rig with import_weights off

    **This test corrected a standing claim about MPFB.** The generated program's comment
    said ``ensure_armature_modifier()`` is called only when ``import_weights``
    is true, so ``armature_modifier_added`` would be false here. It is not:
    ``Rig.create_armature_and_fit_to_basemesh()`` adds the modifier itself,
    whatever ``import_weights`` says. The reported field was always an
    observation off the object rather than a derivation from the argument, so
    the answer was right and only the reasoning behind it was wrong - which is
    the kind of thing that can only be found by asking a real MPFB.
    """
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name, "identifier": "default",
                          "import_weights": False})

        assert result["added"] is True
        assert result["weights_loaded"] is False
        assert "not deformed by it" in result["message"]
        assert result["armature_modifier_added"] is True, \
            "MPFB adds the armature modifier from Rig.create_armature_and_fit_to_basemesh() " \
            "regardless of import_weights; if this ever becomes false, MPFB changed"


def test_a_rigify_metarig_says_what_to_do_next():
    """commands.add_rig with a rigify identifier"""
    services = _services_or_skip()
    if not services["SystemService"].check_for_rigify():
        pytest.skip("Rigify is not enabled in this Blender")

    with _Character() as character:
        result = _result({"name": character.basemesh.name, "identifier": "rigify.human"})

        assert result["added"] is True
        assert result["family"] == "rigify"
        assert result["is_metarig"] is True
        assert result["next_step"] is not None
        assert "mpfb_generate_rigify_rig" in result["next_step"]
        assert services["RigService"].identify_rig(
            bpy.data.objects[result["rig_object_name"]]).startswith("rigify.")


def test_an_unknown_identifier_is_an_answer_with_the_vocabulary_beside_it():
    """commands.add_rig with an identifier that names no file

    ``add_builtin_rig()`` raises ``IOError`` here. Checking first is what turns
    that into something an agent can act on.
    """
    _services_or_skip()
    with _Character() as character:
        envelope = dispatch("add_rig", {"name": character.basemesh.name,
                                        "identifier": "no-such-rig-anywhere"})

        assert envelope["status"] == "ok", \
            "an unknown identifier is an answer, not a failure: {!r}".format(envelope)
        result = envelope["result"]
        assert result["added"] is False
        assert result["performed"] is False
        assert result["blocked_by"] == "unknown_identifier"
        assert result["known_identifiers"], \
            "the refusal must say what could have been asked for"


def test_a_character_that_already_has_a_rig_is_refused():
    """commands.add_rig twice

    MPFB has no way to swap a rig: adding a second one re-parents the basemesh
    to it and leaves the first orphaned, with no error anywhere.
    """
    _services_or_skip()
    with _Character() as character:
        first = _result({"name": character.basemesh.name, "identifier": "default"})
        second = _result({"name": character.basemesh.name, "identifier": "cmu_mb"})

        assert second["added"] is False
        assert second["blocked_by"] == "already_rigged"
        assert second["existing_rig_name"] == first["rig_object_name"]
        assert second["performed"] is False


def test_assets_attached_before_the_rig_are_named_as_unrigged():
    """commands.add_rig on a character that is already wearing something

    ``add_mhclo_asset()`` rigs a garment only if a rig is present at the moment
    it is attached, and nothing re-rigs it afterwards - not refit_human either.
    This is the command that makes that ordering visible.
    """
    services = _services_or_skip()
    with _Character() as character:
        # A typed relative is enough: what is under test is the enumeration,
        # not the fit. Equipping a real garment is add_asset's own test.
        from .._fixtures import typed_child  # pylint: disable=import-outside-toplevel
        garment = typed_child(services, character.basemesh, "PreRigGarment", "Clothes")

        result = _result({"name": character.basemesh.name, "identifier": "default"})

        assert garment.name in result["mesh_assets_not_rigged"], \
            "a garment attached before the rig must be named: {!r}".format(
                result["mesh_assets_not_rigged"])
        assert "NOT rigged" in result["message"]


def test_the_subject_may_be_any_object_in_the_family():
    """commands.add_rig addressed by a garment rather than the basemesh"""
    services = _services_or_skip()
    with _Character() as character:
        from .._fixtures import typed_child  # pylint: disable=import-outside-toplevel
        garment = typed_child(services, character.basemesh, "AddressGarment", "Clothes")

        result = _result({"name": garment.name, "identifier": "default"})

        assert result["added"] is True
        assert result["basemesh_name"] == character.basemesh.name
        assert result["subject_name"] == garment.name


def test_the_callers_selection_and_active_object_are_restored():
    """commands.add_rig puts back what it borrowed"""
    services = _services_or_skip()
    with _Character() as character:
        bystander = bpy.data.objects.new("RigBystander", bpy.data.meshes.new("RigBystanderMesh"))
        bpy.context.scene.collection.objects.link(bystander)
        services["ObjectService"].activate_blender_object(bystander)
        character.basemesh.select_set(False)

        _result({"name": character.basemesh.name, "identifier": "default"})

        assert bpy.context.view_layer.objects.active is bystander
        assert character.basemesh.select_get() is False


def test_the_identifier_is_required_by_the_contract():
    """commands.add_rig with no identifier at all"""
    _services_or_skip()
    envelope = dispatch("add_rig", {})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "identifier" in envelope["message"]


def test_mpfb_being_unavailable_refuses_rather_than_half_rigging():
    """commands.add_rig against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("add_rig", {"identifier": "default"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
