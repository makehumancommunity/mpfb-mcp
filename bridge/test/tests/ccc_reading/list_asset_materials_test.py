"""
``list_asset_materials`` against a real MPFB: the scan, and its staleness.

This command's defining property is that **its answer is stale by design**, and
that property has never been checked against MPFB.
``AssetService.alternative_materials_for_asset()`` caches per
``(asset_source, asset_subdir)`` in a module-level dict that nothing invalidates
automatically, so the answer is a snapshot from the first time anything in this
Blender session asked about this asset. ``test_the_answer_is_a_cached_snapshot``
is that claim, put to MPFB.

Three more things are put to it here for the first time:

- that ``exclude_default`` is **accepted and never read**, so the asset's own
  material appears in the list and is flagged rather than removed;
- that ``Mhclo`` is a module-level name on humanservice.py and that
  ``load(only_metadata=True)`` reads the ``material`` line without the vertex
  tables;
- that an asset whose MHCLO names **no** material produces
  ``mhclo_names_no_material`` rather than a failure - the branch that decides
  whether ``set_asset_material``'s ``restore_default`` could work at all.

The object this asks about is **typed and property-written by the test** rather
than equipped: equipping is ``add_asset``'s, which is stage 4's, and a read-only
command's test should not be the first place an asset is imported.
"""

import os

import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import build_asset_library
from .._fixtures import dispatch
from .._fixtures import linked_plain_object
from .._fixtures import only_these_data_roots
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import supplied_resolution
from .._fixtures import typed_child
from .._fixtures import write_mhmat

COMMAND = "list_asset_materials"


def _set_asset_source(services, blender_object, fragment):
    """Write MPFB's own ``asset_source`` property, as equipping one would."""
    import sys  # pylint: disable=import-outside-toplevel

    objectservice_module = sys.modules[services["ObjectService"].__module__]
    general_properties = objectservice_module.GeneralObjectProperties
    general_properties.set_value("asset_source", fragment, entity_reference=blender_object)


@pytest.fixture(name="equipped")
def _with_an_equipped_asset(tmp_path):
    """A character wearing something the fixture library ships, plus the library.

    ``asset_source`` is the fragment MPFB records when it equips an asset, and
    it is what every lookup in this command starts from - so it is written here
    directly rather than by importing a garment.

    **The character is built before the roots are redirected**, and the order is
    load-bearing: ``create_human()`` reads ``base.obj`` out of MPFB's own data
    directory, so a fixture that pointed ``<mpfb data>`` at a temporary tree
    first would fail inside MPFB rather than testing anything. Nothing after
    that point needs the real data root.
    """
    services = services_or_skip()
    system_root, user_root = build_asset_library(str(tmp_path))
    with Character() as character:
        with only_these_data_roots(services, mpfb_data=system_root, user_data=user_root):
            services["AssetService"].invalidate_alternative_materials_cache()
            garment = typed_child(services, character.basemesh, "BridgeTestFedora", "Clothes")
            _set_asset_source(services, garment, "fedora/fedora.mhclo")
            yield {"garment": garment, "system": system_root, "character": character}
    services["AssetService"].invalidate_alternative_materials_cache()


def test_the_materials_beside_the_asset_are_listed_with_both_identifiers(equipped):
    """AssetService.alternative_materials_for_asset(), and the addressing around it"""
    answer = result(COMMAND, {"name": equipped["garment"].name})

    assert answer["found"] is True
    assert answer["object_type"] == "Clothes"
    assert answer["asset_subdir"] == "clothes", \
        "the subdir is str(object_type).lower(), matching the write half of this property"
    names = sorted(entry["name"] for entry in answer["materials"])
    assert "fedora_red" in names and "fedora_blue" in names, \
        "both materials beside the asset should be listed, got {!r}".format(names)
    for entry in answer["materials"]:
        assert os.path.isfile(entry["path"]), "path should be a file"
        assert entry["fragment"], "fragment is the portable identifier beside it"


def test_the_assets_own_material_is_flagged_rather_than_removed(equipped):
    """exclude_default being accepted by MPFB and never read

    The fixture ships ``fedora.mhclo`` under **two** roots, which is a real
    arrangement - two packs shipping the same asset - and it makes this test
    sharper rather than harder: ``find_asset_absolute_path()`` matches on
    basename and resolves to one of them, the scan finds the materials beside
    both, and exactly one of the two ``fedora.mhmat`` files is therefore the
    default. Asserting "exactly one, and it is the one the MHCLO named" is the
    claim; asserting "the entry called fedora" would depend on which root won.
    """
    answer = result(COMMAND, {"name": equipped["garment"].name})

    assert answer["default_material"] is not None
    assert answer["default_material"]["exists"] is True
    assert answer["default_material_reason"] is None

    defaults = [entry for entry in answer["materials"] if entry["is_default"]]
    assert len(defaults) == 1, \
        "exactly one entry is the asset's own material, got {!r}".format(
            [entry["path"] for entry in defaults])
    # MPFB does not filter it out, despite alternative_materials_for_asset()
    # taking an exclude_default argument it never reads.
    assert defaults[0]["path"] == answer["default_material"]["path"]
    assert defaults[0]["name"] == "fedora"

    alternatives = {entry["name"] for entry in answer["materials"] if not entry["is_default"]}
    assert {"fedora_red", "fedora_blue"} <= alternatives, \
        "the alternatives should be listed and not flagged, got {!r}".format(alternatives)


def test_the_answer_is_a_cached_snapshot(equipped):
    """The property this command is most defined by, asked of MPFB

    MPFB caches the scan per (asset_source, asset_subdir) and nothing
    invalidates it automatically, so a material installed after the first call
    in this Blender session is applicable and invisible. This command says so in
    its own message rather than rescanning by default, because rescanning would
    be this command inventing a behaviour MPFB does not have on its own -
    unless asked to, which is what FR 018's `refresh` argument is for.
    """
    before = result(COMMAND, {"name": equipped["garment"].name})
    assert before["count"] >= 2, "the fixture ships materials to cache"
    assert before["cache_invalidated"] is False

    write_mhmat(os.path.join(equipped["system"], "clothes", "fedora", "fedora_green.mhmat"))
    after = result(COMMAND, {"name": equipped["garment"].name})

    assert [entry["name"] for entry in after["materials"]] == \
        [entry["name"] for entry in before["materials"]], \
        "the scan is cached, so a new material should be invisible"
    assert "cached snapshot" in after["message"], \
        "the staleness has to be in the answer, or a caller reads it as a bug here"
    assert after["cache_invalidated"] is False

    # refresh=True is the invalidator FR 018 wires up - AssetService's own
    # invalidate_alternative_materials_cache() exists and this is the only
    # caller of it, since it clears every asset's cache and not only this one.
    rescanned = result(COMMAND, {"name": equipped["garment"].name, "refresh": True})
    assert rescanned["cache_invalidated"] is True
    assert "fedora_green" in [entry["name"] for entry in rescanned["materials"]], \
        "refresh=True should make the new material appear"
    assert "cached snapshot" not in rescanned["message"]


def test_an_asset_whose_mhclo_names_no_material_says_which_branch_it_took(equipped):
    """mhclo_names_no_material, and what set_asset_material would do about it"""
    services = services_or_skip()
    _set_asset_source(services, equipped["garment"], "plain/plain.mhclo")

    answer = result(COMMAND, {"name": equipped["garment"].name})

    assert answer["default_material"] is None
    assert answer["default_material_reason"] == "mhclo_names_no_material", \
        "the reason is data here, where set_asset_material turns it into a refusal"
    assert "restore_default would refuse" in answer["message"]


def test_an_asset_source_naming_nothing_installed_is_an_answer(equipped):
    """mhclo_not_installed rather than a failed call"""
    services = services_or_skip()
    _set_asset_source(services, equipped["garment"], "nowhere/nothing.mhclo")

    answer = result(COMMAND, {"name": equipped["garment"].name})

    assert answer["found"] is True
    assert answer["default_material_reason"] == "mhclo_not_installed"
    assert answer["materials"] == [], "nothing resolves, so nothing is claimed to ship beside it"


def test_an_object_with_no_asset_source_claims_nothing(equipped):
    """The difference between "none exist" and "we could not look" """
    services = services_or_skip()
    bare = typed_child(services, equipped["character"].basemesh,
                       "BridgeTestBareAsset", "Clothes")
    try:
        answer = result(COMMAND, {"name": bare.name})

        assert answer["found"] is True
        assert answer["asset_source"] is None
        assert answer["materials"] == []
        assert "Nothing is claimed about whether any exist" in answer["message"]
    finally:
        import bpy  # pylint: disable=import-outside-toplevel
        bpy.data.objects.remove(bare, do_unlink=True)


def test_an_object_with_no_mpfb_type_is_told_what_it_is_instead():
    """The command wants the asset's own name, not the character's"""
    services_or_skip()
    plain = linked_plain_object("BridgeTestNotAnAsset")
    try:
        answer = result(COMMAND, {"name": plain.name})

        assert answer["found"] is True
        assert answer["object_type"] is None
        assert "carries no MPFB object_type" in answer["message"]
        assert "mpfb_get_object_info" in answer["message"]
    finally:
        import bpy  # pylint: disable=import-outside-toplevel
        bpy.data.objects.remove(plain, do_unlink=True)


def test_an_unknown_name_is_an_answer_rather_than_an_error():
    """found: false, and the sentence that says which mistake was made"""
    services_or_skip()
    answer = dispatch(COMMAND, {"name": "NoSuchObjectExistsHere"})

    assert answer["status"] == "ok"
    assert answer["result"]["found"] is False
    assert "not the character's" in answer["result"]["message"], \
        "the commonest mistake is passing the character's name, so the message names it"


def test_the_name_is_required_rather_than_defaulted():
    """command_server.dispatch(): no active-object fallback here"""
    command_server = bridge_module("command_server")

    answer = dispatch(COMMAND)

    # Unlike get_object_info, there is no sensible active-object fallback: the
    # active object is usually the character, and the character is never the
    # thing this command is asked about.
    assert answer["error"] == command_server.ERROR_INVALID_PARAMS
    assert "name" in answer["message"] and "required" in answer["message"]


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    """command_server.dispatch() with requires_mpfb and no MPFB"""
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = dispatch(COMMAND, {"name": "anything"})

    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE
    assert "found" not in answer
