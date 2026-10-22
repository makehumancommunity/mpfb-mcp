"""
``shared/pack_attribution.py``, called directly.

The attribution is a join nothing records, and its answer may end up in a
licensing decision, so each shape a real install has is put to it here once,
against MPFB's own reading of a ``packs/`` directory this test writes
(``build_attributed_library``), rather than through whichever catalogue happens
to reach it first. The catalogues' own tests then only have to show that they
report what this module answers.

Two claims are about MPFB rather than about the join, and are asserted because a
wrong one would degrade every license to ``null`` without raising:
``get_pack_names()`` populates ``assetservice._PACKS``, and the entries there
are the parsed JSON. The agree-or-null rule is also checked on a hand-built
index, since the disagreement it exists for is one no install has yet.
"""

import os

import pytest

from .. import bridge_module
from .._fixtures import build_attributed_library
from .._fixtures import only_these_data_roots
from .._fixtures import services_or_skip
from .._fixtures import write_pack


def _module():
    return bridge_module("shared.pack_attribution")


@pytest.fixture(name="attributed")
def _with_attributed_library(tmp_path):
    """MPFB pointed at the attributed library, its pack cache emptied both ways."""
    services = services_or_skip()
    system_root, user_root = build_attributed_library(str(tmp_path))
    with only_these_data_roots(services, mpfb_data=system_root, user_data=user_root):
        services["AssetService"].invalidate_pack_metadata_cache()
        yield {"services": services, "system": system_root, "user": user_root,
               "index": _module().read_index(services)}
    services["AssetService"].invalidate_pack_metadata_cache()


def _attribute(attributed, root, *parts):
    """The attribution of ``<root>/<parts...>``, judged against both roots' subdir."""
    subdir = parts[0]
    roots = [os.path.join(attributed["system"], subdir), os.path.join(attributed["user"], subdir)]
    return _module().attribute(attributed["index"], os.path.join(attributed[root], *parts), roots)


def test_the_entries_are_read_off_mpfbs_own_scan(attributed):
    """_PACKS after get_pack_names(), so pack and license come from one read"""
    index = attributed["index"]
    assert index.entries_read is True, \
        "assetservice._PACKS should be readable; without it every license is null"
    assert index.pack_names == sorted([
        "capes01_cc0", "fedora_materials01", "hair01", "hair01_ccby", "hats01", "hats01_cc0",
        "makehuman_system_assets", "odd01"])
    assert index.known_licenses == ["CC-BY", "CC0"]


def test_two_packs_that_agree_attribute_the_asset_to_both(attributed):
    """The hats01/hats01_cc0 shape"""
    answer = _attribute(attributed, "system", "clothes", "fedora", "fedora.mhclo")
    assert answer["packs"] == ["hats01", "hats01_cc0"]
    assert answer["license"] == "CC0"
    assert answer["author"] == "hatmaker"
    assert answer["source_url"] == "http://www.makehumancommunity.org/node/1"
    assert answer["claims_disagree"] is False


def test_a_material_in_its_assets_directory_takes_the_assets_attribution(attributed):
    answer = _attribute(attributed, "system", "clothes", "fedora", "fedora_red.mhmat")
    assert answer["packs"] == ["hats01", "hats01_cc0"]
    assert answer["license"] == "CC0"


def test_a_material_in_a_directory_of_its_own_takes_that_directorys(attributed):
    """Not its asset's: a different pack, a different license"""
    answer = _attribute(attributed, "system", "clothes", "fedora", "fedora_green",
                        "fedora_green.mhmat")
    assert answer["packs"] == ["fedora_materials01"]
    assert answer["license"] == "CC-BY"
    assert answer["author"] == "painter"


def test_an_eye_material_is_attributed_by_its_file_stem(attributed):
    """eyes/materials/brown.mhmat: a directory nothing claims, a stem a pack does"""
    answer = _attribute(attributed, "system", "eyes", "materials", "brown.mhmat")
    assert answer["packs"] == ["makehuman_system_assets"]
    assert answer["license"] == "CC0"


def test_a_file_directly_in_an_asset_root_is_not_attributed(attributed):
    """Even though a pack claims an asset named for the subdir it sits in"""
    answer = _attribute(attributed, "user", "skins", "default.mhmat")
    assert answer["packs"] == [], \
        "skins/default.mhmat must not be attributed to the pack claiming 'skins'"
    assert answer["license"] is None


def test_an_asset_no_pack_claims_is_an_ordinary_null(attributed):
    answer = _attribute(attributed, "system", "clothes", "plain", "plain.mhclo")
    assert answer == _module().unattributed()


def test_claimants_that_disagree_report_null_and_every_claim(attributed):
    """hair01 says CC0, hair01_ccby says CC-BY: neither is reported as the license"""
    answer = _attribute(attributed, "system", "hair", "ponytail", "ponytail.mhclo")
    assert answer["packs"] == ["hair01", "hair01_ccby"]
    assert answer["license"] is None, "a disagreement must not be resolved by picking one"
    assert answer["claims_disagree"] is True
    assert sorted(claim["license"] for claim in answer["claims"]) == ["CC-BY", "CC0"]
    # The fields they agree on are still reported.
    assert answer["author"] == "barber"


def test_a_public_getter_is_preferred_to_the_private_read(attributed, monkeypatch):
    """AssetService.get_pack_metadata(), if MPFB ever publishes one"""
    services = attributed["services"]
    asked = []

    def get_pack_metadata(pack_name):
        asked.append(pack_name)
        return {"fedora": {"license": "Getter-License", "author": "x", "source": "y"}}

    monkeypatch.setattr(services["AssetService"], "get_pack_metadata", get_pack_metadata,
                        raising=False)
    index = _module().read_index(services)
    assert sorted(asked) == index.pack_names
    assert index.known_licenses == ["Getter-License"]


def test_without_the_entries_the_names_still_attribute_and_licenses_are_null(attributed,
                                                                              monkeypatch):
    """The fallback when MPFB renames _PACKS: pack survives, license does not"""
    services = attributed["services"]
    monkeypatch.setattr(_module().mpfb_surface, "module_level",
                        lambda services, service, name, fallback: fallback)
    index = _module().read_index(services)
    assert index.entries_read is False
    assert index.known_licenses == []
    answer = _module().attribute(index, os.path.join(
        attributed["system"], "clothes", "fedora", "fedora.mhclo"), [])
    assert answer["packs"] == ["hats01", "hats01_cc0"]
    assert answer["license"] is None


def test_the_index_is_mpfbs_cached_scan_until_it_is_invalidated(attributed):
    """A pack written after the first read is not seen until the cache is cleared"""
    services = attributed["services"]
    write_pack(attributed["user"], "plain01", {
        "plain": ("CC0", "weaver", "http://www.makehumancommunity.org/node/6")})
    path = os.path.join(attributed["system"], "clothes", "plain", "plain.mhclo")

    stale = _module().attribute(_module().read_index(services), path, [])
    assert stale["packs"] == [], "MPFB caches the metadata, and this reads its cache"

    services["AssetService"].invalidate_pack_metadata_cache()
    fresh = _module().attribute(_module().read_index(services), path, [])
    assert fresh["packs"] == ["plain01"]
    assert fresh["license"] == "CC0"


def test_a_field_one_claim_leaves_empty_is_a_disagreement():
    """No MPFB needed: the rule over a hand-built index"""
    module = _module()
    claims = {"cap": [
        {"pack": "a", "license": "CC0", "author": "x", "source_url": None},
        {"pack": "b", "license": None, "author": "x", "source_url": None}]}
    index = module.PackIndex(["a", "b"], claims, True)
    answer = module.attribute(index, os.path.join(os.sep, "data", "clothes", "cap", "cap.mhclo"),
                              [os.path.join(os.sep, "data", "clothes")])
    assert answer["license"] is None
    assert answer["claims_disagree"] is True
    assert answer["author"] == "x"
    assert answer["source_url"] is None


def test_no_path_is_attributed_to_nothing():
    module = _module()
    index = module.PackIndex([], {}, True)
    assert module.attribute(index, None, []) == module.unattributed()
