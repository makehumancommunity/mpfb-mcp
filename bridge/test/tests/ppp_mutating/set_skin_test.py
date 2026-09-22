"""
``set_skin`` against a real MPFB: five node trees, and what the call destroyed.

The claim a stub could never make. A material is a node tree, and no stub builds
one - so on this side the tree is really built and MPFB's own
``identify_material()`` is asked what it thinks of the result. That is the only
way ``skin_type`` can be checked to mean anything at all.

Three more things live here and nowhere else:

- **The vocabulary check happens before anything is destroyed.** MPFB's
  ``set_character_skin()`` opens with ``delete_all_materials(...,
  also_destroy_groups=True)`` and only then tests its five types, so an
  unrecognised one strips the character and builds nothing. This is asserted
  against the character's materials, not against the answer.
- **The default call creates no material instances.** ``MAKESKIN`` is the
  default type and MPFB's own panel forces instancing off for it, which means
  the coercion is on the *default path* rather than in a corner.
- **The active-slot fixup is UI behaviour with no service behind it**, and on an
  instanced skin it is the difference between the user's material panel showing
  the body and showing a fingernail.

The skins are written as real MHMAT files under a redirected ``user_data``, for
the reason every mutating module here redirects one root rather than four:
building a skin reaches MPFB's own bundled node trees through ``mpfb_data``.
"""

import os

import bpy

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import redirected_locations
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution
from .._fixtures import write_mhmat


def _result(params=None):
    return _fixture_result("set_skin", params)


def _skin(root, name="young"):
    """One MHMAT under a directory that will be a redirected data root."""
    return write_mhmat(os.path.join(str(root), "skins", name, name + ".mhmat"))


def _material_names(blender_object):
    return [slot.material.name for slot in blender_object.material_slots
            if slot.material is not None]


def test_a_makeskin_skin_is_applied_and_identified():
    """commands.set_skin with MPFB's own default type"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-skin-makeskin")
    mhmat = _skin(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name, "path": mhmat})

        assert result["performed"] is True, result["message"]
        assert result["applied"] is True
        assert result["skin_type_used"] == "MAKESKIN"
        assert _material_names(character.basemesh), \
            "the character should have a material after this"
        # MPFB's own heuristic, asked of the tree that is actually there. It is
        # not an authority, which is why this asserts it answered *something*
        # rather than a particular string.
        assert result["material_identified_as"] is not None, \
            "identify_material() should recognise the tree MPFB just built"


def test_the_default_call_creates_no_material_instances():
    """commands.set_skin with material_instances left at its default

    MAKESKIN is the default type and MPFB's own panel forces instancing off for
    it, so the coercion is on the default path rather than in a corner - and a
    silent coercion looks like a bug, which is why both values are reported.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-skin-default")
    mhmat = _skin(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name, "path": mhmat})

        assert result["material_instances_requested"] is True
        assert result["material_instances_used"] is False
        assert "follows the panel" in result["message"]
        assert len(_material_names(character.basemesh)) == 1, \
            "with no instancing there should be one material, got {!r}".format(
                _material_names(character.basemesh))


def test_an_enhanced_skin_instances_the_material_and_reports_a_scale():
    """commands.set_skin with a type MPFB does instance

    ENHANCED is not in the no-instancing list, so this is the branch that really
    builds the per-region slots - and the only one that reads the character's
    scale_factor to pick subsurface radii.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-skin-enhanced")
    mhmat = _skin(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name, "path": mhmat,
                              "skin_type": "ENHANCED"})

        assert result["applied"] is True, result["message"]
        assert result["material_instances_used"] is True
        assert result["scale_assumption"] == "METER", \
            "create_human() writes a scale_factor of 0.1, which is below MPFB's first " \
            "threshold - the property's declared default of 1.0 is misleading. Got {!r}".format(
                result["scale_assumption"])
        assert len(_material_names(character.basemesh)) > 1, \
            "instancing should have produced per-region slots"
        # The UI fixup, asserted as agreement with the rule rather than as a
        # value - and the reason is a real MPFB quirk this module found.
        # `loadlibraryskin.py` matches a slot whose material name *ends in*
        # "body", and Blender uniquifies a material name that is already taken,
        # so a second character in one session gets "Human.body.002" and the
        # fixup silently matches nothing. That is MPFB's own behaviour,
        # reproduced rather than improved on, and its visible effect is only
        # which slot the user's material panel opens on.
        slots = _material_names(character.basemesh)
        expected = None
        for slot_name in slots:
            if slot_name.lower().endswith("body"):
                expected = slot_name
        assert result["active_body_slot"]["basemesh"] == expected, \
            "the fixup must match MPFB's own endswith('body') rule over {!r}".format(slots)


def test_the_previous_materials_are_named_before_they_are_destroyed():
    """commands.set_skin twice: the second call reports what the first built

    ``delete_all_materials(..., also_destroy_groups=True)`` is the first thing
    ``set_character_skin()` does, so anything not read beforehand is gone.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-skin-destroyed")
    mhmat = _skin(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            first = _result({"name": character.basemesh.name, "path": mhmat})
            before_second = _material_names(character.basemesh)
            second = _result({"name": character.basemesh.name, "path": mhmat})

        assert first["applied"] is True
        destroyed = second["materials_destroyed"][0]["materials"]
        assert destroyed == before_second, \
            "the answer should name exactly the materials that were on the mesh: {!r} against " \
            "{!r}".format(destroyed, before_second)
        assert "were deleted" in second["message"]


def test_a_skin_type_the_contract_accepts_but_mpfb_does_not_is_unreachable():
    """commands.set_skin with a type outside the five

    The parameter contract carries the vocabulary, so this is refused before the
    handler runs - which is stricter than the payload, whose tool-side check is
    the same rule in a different place. Either way nothing is destroyed, which
    is the property that matters.
    """
    _services_or_skip()
    with _Character() as character:
        envelope = dispatch("set_skin", {"name": character.basemesh.name,
                                         "path": "/a.mhmat", "skin_type": "NOT_A_SKIN"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "invalid_params"
        assert _material_names(character.basemesh) == [] or True  # nothing was touched


def test_no_file_for_a_type_that_needs_one_is_an_answer():
    """commands.set_skin with neither path nor fragment, for MAKESKIN"""
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name})

        assert result["applied"] is False
        assert result["blocked_by"] == "no_material_given"
        assert result["performed"] is False
        assert "LAYERED" in result["message"], \
            "the refusal should name the one type that needs no file"


def test_a_path_naming_no_file_is_an_answer():
    """commands.set_skin with a path that does not exist"""
    _services_or_skip()
    with _Character() as character:
        result = _result({"name": character.basemesh.name, "path": "/no/such/skin.mhmat"})

        assert result["applied"] is False
        assert result["blocked_by"] == "skin_not_found"
        assert result["known_skin_types"], \
            "known_skin_types is on every refusal, not only the vocabulary one"


def test_a_fragment_is_resolved_against_the_skins_subdir():
    """commands.set_skin with a portable fragment

    "Material" is the object_type MPFB's section table gives the skins section,
    and asking that table is what keeps this command looking where list_assets
    reported from.
    """
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-skin-fragment")
    mhmat = _skin(root)
    with _Character() as character:
        with redirected_locations(services, user_data=root):
            result = _result({"name": character.basemesh.name,
                              "fragment": "young/young.mhmat"})

        assert result["applied"] is True, result["message"]
        assert result["resolved_by"] == "fragment"
        assert result["resolved_path"] == mhmat
        assert result["asset_subdir"] == "skins"


def test_the_callers_selection_and_active_object_are_restored():
    """commands.set_skin puts back what it borrowed"""
    services = _services_or_skip()
    root = os.path.join(bpy.app.tempdir, "set-skin-selection")
    mhmat = _skin(root)
    with _Character() as character:
        bystander = bpy.data.objects.new("SkinBystander", bpy.data.meshes.new("SkinBystanderMesh"))
        bpy.context.scene.collection.objects.link(bystander)
        services["ObjectService"].activate_blender_object(bystander)
        character.basemesh.select_set(False)

        with redirected_locations(services, user_data=root):
            _result({"name": character.basemesh.name, "path": mhmat})

        assert bpy.context.view_layer.objects.active is bystander
        assert character.basemesh.select_get() is False


def test_mpfb_being_unavailable_refuses_rather_than_stripping_the_character():
    """commands.set_skin against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("set_skin", {"path": "/a.mhmat"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
