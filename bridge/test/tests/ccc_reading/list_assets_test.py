"""
``list_assets`` against a real MPFB, over an asset library this test builds.

The library is the test's own and **every data root is redirected**, not only
the one written into: ``get_available_data_roots()`` is the union of four
locations, so a test that pointed one at a fixture and inherited the rest would
pass or fail depending on which asset packs the developer has installed. A suite
whose result depends on that is a suite that cannot fail usefully.

What is put to MPFB here for the first time:

- **what ``ASSET_LIBRARY_SECTIONS`` actually contains**, and that it is a
  module-level name on ``assetservice.py`` rather than a member of the service -
  the thing ``section_table_from_mpfb`` reports on;
- **that ``get_asset_list()`` is keyed by label**, so two assets whose filenames
  differ only in case or underscores collapse into one entry. This command's
  counts under-report by exactly that much and say so;
- **that ``fragment`` is what MPFB records on an equipped object**, which is the
  field the whole command exists for;
- **that ``get_asset_roots()`` drops a data root holding no such subdir**, which
  is the usual explanation for "I installed it and it is not here".

The attribution (FR 046) is asked of an ``attributed`` library whose packs
record licenses: the filter, the counts beside it, the filter-aware ``pack``, a
matched pack with nothing installed, and claimants that disagree. How each file
is attributed is ``bbb_shared/pack_attribution_test.py``'s; what is checked here
is that the catalogue reports it.

The cap and the paging are checked here rather than on mpfb-mcp's side because
they are about a real library's ordering: MPFB's cached dict is insertion
ordered from an ``rglob``, whose order is filesystem-dependent, so "page 2 does
not repeat page 1" is a claim about a sort applied to real data.
"""

import os

import pytest

from .. import bridge_module
from .._fixtures import build_asset_library
from .._fixtures import build_attributed_library
from .._fixtures import dispatch
from .._fixtures import only_these_data_roots
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import supplied_resolution

COMMAND = "list_assets"


@pytest.fixture(name="library")
def _with_asset_library(tmp_path):
    """MPFB pointed at an asset library of this test's own, and at nothing else."""
    services = services_or_skip()
    system_root, user_root = build_asset_library(str(tmp_path))
    with only_these_data_roots(services, mpfb_data=system_root, user_data=user_root):
        # The cached asset lists are per (subdir, type) and survive a root
        # change, so they are rebuilt against this tree on the way in and
        # against the developer's own on the way out.
        services["AssetService"].update_all_asset_lists()
        yield {"system": system_root, "user": user_root}
    services["AssetService"].update_all_asset_lists()


@pytest.fixture(name="attributed")
def _with_attributed_library(tmp_path):
    """The same, over a library whose packs record licenses (FR 046)."""
    services = services_or_skip()
    system_root, user_root = build_attributed_library(str(tmp_path))
    with only_these_data_roots(services, mpfb_data=system_root, user_data=user_root):
        # update_all_asset_lists() invalidates the pack metadata cache too.
        services["AssetService"].update_all_asset_lists()
        yield {"system": system_root, "user": user_root}
    services["AssetService"].update_all_asset_lists()


def _names(answer):
    return sorted(entry["name"] for entry in answer["assets"])


def test_the_section_table_is_mpfbs_own(library):
    """assetservice.ASSET_LIBRARY_SECTIONS, through sys.modules"""
    import sys  # pylint: disable=import-outside-toplevel

    services = services_or_skip()
    module = sys.modules[services["AssetService"].__module__]
    assert hasattr(module, "ASSET_LIBRARY_SECTIONS"), \
        "MPFB no longer publishes the section table; the fallback is now the only answer"

    answer = result(COMMAND)

    assert answer["section_table_from_mpfb"] is True, \
        "the answer should say it read MPFB's table rather than the local copy"
    published = [str(section["asset_subdir"]) for section in module.ASSET_LIBRARY_SECTIONS]
    assert answer["known_asset_subdirs"] == published, \
        "known_asset_subdirs should be MPFB's list in MPFB's order"


def test_the_assets_in_the_tree_are_found_with_both_of_their_identifiers(library):
    """`path` for the adding function, `fragment` for writing down"""
    answer = result(COMMAND, {"asset_subdir": "clothes"})

    assert "fedora" in _names(answer), \
        "the fixture's clothes should be listed, got {!r}".format(_names(answer))
    entry = [asset for asset in answer["assets"] if asset["name"] == "fedora"][0]
    assert os.path.isfile(entry["path"]), "path should be a file an adding command can open"
    assert entry["fragment"], "fragment is the field this command exists for"
    assert not os.path.isabs(entry["fragment"]), \
        "a fragment is portable, so it is relative rather than this machine's path"
    assert entry["object_type"] == "Clothes", \
        "the object_type is what add_asset's object_type takes"
    assert entry["asset_subdir"] == "clothes"


def test_an_unknown_subdir_is_flagged_rather_than_silently_empty(library):
    """asset_subdir_recognized, and why the filter is exact rather than a substring"""
    answer = result(COMMAND, {"asset_subdir": "clothing"})

    assert answer["assets"] == []
    assert answer["asset_subdir_recognized"] is False, \
        "a misspelled subdir must be distinguishable from an empty one"
    assert "No asset subdir called" in answer["message"]
    assert "clothing" in answer["message"]

    # And the exactness itself: "clothes" is a subdir, "cloth" is not, even
    # though the second is a substring of the first. Unlike list_objects' type
    # filter there is no MPFB matcher to mirror here.
    assert result(COMMAND, {"asset_subdir": "cloth"})["asset_subdir_recognized"] is False
    assert result(COMMAND, {"asset_subdir": "CLOTHES"})["asset_subdir_recognized"] is True, \
        "exact, but case-insensitive"


def test_a_subdir_that_exists_and_holds_nothing_stays_recognised(library):
    """The other half of that pairing"""
    answer = result(COMMAND, {"asset_subdir": "poses"})

    assert answer["assets"] == []
    assert answer["asset_subdir_recognized"] is True, \
        "'poses' is a section MPFB knows, so empty means the library, not the spelling"


def test_only_the_roots_holding_the_subdir_are_searched(library):
    """AssetService.get_asset_roots() dropping a root with no such directory"""
    answer = result(COMMAND, {"asset_subdir": "hair"})

    searched = answer["asset_roots_searched"]["hair"]
    # The fixture puts hair under the system root only, so the user root - a
    # perfectly good data root - is not searched for it. That difference is the
    # usual explanation for "I installed it and it is not here".
    assert len(searched) == 1, "only the root holding hair/ should be searched: {!r}".format(
        searched)
    assert searched[0].startswith(library["system"])


def test_the_name_filter_is_a_substring_over_name_and_label(library):
    """The filter, and what it is matched against"""
    answer = result(COMMAND, {"name_contains": "fedor"})

    assert _names(answer) == ["fedora"], \
        "a substring of the name should match it, got {!r}".format(_names(answer))
    assert result(COMMAND, {"name_contains": "FEDORA"})["count"] == answer["count"], \
        "the name filter is case-insensitive"
    assert result(COMMAND, {"name_contains": "nothing-is-called-this"})["count"] == 0


def test_the_cap_is_always_declared_and_the_pages_do_not_overlap(library):
    """truncated, and a deterministic order before paging"""
    everything = result(COMMAND, {"limit": 1000})
    assert everything["truncated"] is False, \
        "the whole library fits, so nothing was cut"
    assert everything["total_count"] == everything["count"]

    first = result(COMMAND, {"limit": 2, "offset": 0})
    second = result(COMMAND, {"limit": 2, "offset": 2})

    assert first["truncated"] is True, \
        "a capped answer must never look like a complete one"
    assert first["total_count"] == everything["total_count"], \
        "total_count counts the matches, not the page"
    # MPFB's cached dict is insertion-ordered from an rglob, so without the
    # sort this pair would silently skip and repeat entries.
    assert set(_names(first)).isdisjoint(_names(second)), \
        "two pages of one query must not overlap: {!r} and {!r}".format(
            _names(first), _names(second))


def test_the_per_subdir_counts_ignore_the_filters_and_the_cap(library):
    """What keeps an over-broad call informative rather than merely truncated"""
    answer = result(COMMAND, {"asset_subdir": "clothes", "name_contains": "fedora",
                              "limit": 1})

    assert answer["count"] == 1
    # counts_by_asset_subdir is what the library holds, not what survived the filter,
    # so a caller can tell "one match" from "one asset installed".
    assert answer["counts_by_asset_subdir"]["clothes"] >= 1
    assert "clothes" in answer["counts_by_asset_subdir"]
    assert "hair" not in answer["counts_by_asset_subdir"], \
        "the counts cover the subdirs actually scanned, and only clothes was"


def test_mpfbs_cache_is_keyed_by_label_so_two_files_can_collapse(library):
    """The cost this command pays and reports rather than works around"""
    services = services_or_skip()
    clothes = services["AssetService"].get_asset_list("clothes", "mhclo")

    # Two fedora.mhclo files exist, under two different roots. MPFB's cached
    # dict is keyed by label, so they collapse into one entry - and this
    # command's counts under-report by exactly that much.
    fedoras = [item for item in clothes.values()
               if str(item.get("name_without_ext")) == "fedora"]
    assert len(fedoras) == 1, \
        "MPFB's list is keyed by label, so the two fedora.mhclo files collapse into one"

    answer = result(COMMAND, {"asset_subdir": "clothes", "name_contains": "fedora"})
    assert answer["count"] == 1, \
        "the command reports MPFB's list, collapsing included, rather than rescanning"


def test_an_unknown_pack_is_flagged_and_the_filter_is_mpfbs_substring_rule(library):
    """get_asset_names_in_pack_pattern()'s own semantics"""
    answer = result(COMMAND, {"pack": "no-such-pack-is-installed"})

    assert answer["assets"] == []
    assert answer["pack_recognized"] is False
    assert "No installed asset pack name contains" in answer["message"]
    assert isinstance(answer["known_packs"], list), \
        "the installed packs are reported so a caller can pick one"


def test_bad_paging_arguments_are_refused_before_the_handler_runs():
    """command_server.dispatch(): True is an int, and would page one at a time"""
    command_server = bridge_module("command_server")

    for params in ({"limit": True}, {"offset": True}, {"limit": -1}, {"offset": -1},
                   {"limit": 1001}, {"refresh": "false"}):
        answer = dispatch(COMMAND, params)
        assert answer["error"] == command_server.ERROR_INVALID_PARAMS, \
            "{!r} should be refused, got {!r}".format(params, answer)


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    """command_server.dispatch() with requires_mpfb and no MPFB"""
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = dispatch(COMMAND)

    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE
    assert "count" not in answer, "an install problem must not be phrased as an empty library"


def _row(answer, name):
    rows = [asset for asset in answer["assets"] if asset["name"] == name]
    assert len(rows) == 1, "expected one {!r}, got {!r}".format(name, _names(answer))
    return rows[0]


def test_every_row_says_who_made_it_and_under_what_license(attributed):
    """license, author, source_url and packs, from shared/pack_attribution.py"""
    answer = result(COMMAND, {"limit": 1000})

    fedora = _row(answer, "fedora")
    assert fedora["license"] == "CC0"
    assert fedora["author"] == "hatmaker"
    assert fedora["source_url"] == "http://www.makehumancommunity.org/node/1"
    assert fedora["packs"] == ["hats01", "hats01_cc0"]
    assert fedora["pack_ambiguous"] is True, "pack_ambiguous stays len(packs) > 1"

    plain = _row(answer, "plain")
    assert (plain["license"], plain["author"], plain["source_url"], plain["packs"]) == \
        (None, None, None, []), "an asset no pack claims is an ordinary null"
    assert answer["known_licenses"] == ["CC-BY", "CC0"]


def test_claimants_that_disagree_are_reported_once_beside_the_page(attributed):
    answer = result(COMMAND, {"asset_subdir": "hair"})

    ponytail = _row(answer, "ponytail")
    assert ponytail["license"] is None
    conflicts = answer["attribution_conflicts"]
    assert [conflict["path"] for conflict in conflicts] == [ponytail["path"]]
    assert sorted(claim["pack"] for claim in conflicts[0]["claims"]) == ["hair01", "hair01_ccby"]


def test_the_license_filter_is_exact_and_counts_what_it_left_out(attributed):
    """counts_by_license is taken before the license filter and the cap"""
    everything = result(COMMAND, {"limit": 1000})
    cc0 = result(COMMAND, {"license": "cc0", "limit": 1})

    assert cc0["license_recognized"] is True
    assert cc0["requested_license"] == "cc0"
    assert cc0["counts_by_license"] == everything["counts_by_license"], \
        "a filtered call still says what it filtered from"
    assert cc0["license_unknown_count"] == everything["license_unknown_count"]
    assert cc0["total_count"] == everything["counts_by_license"]["CC0"]
    assert cc0["count"] == 1 and cc0["truncated"] is True
    assert sum(everything["counts_by_license"].values()) + everything["license_unknown_count"] \
        == everything["total_count"]

    all_cc0 = result(COMMAND, {"license": "CC0", "limit": 1000})
    assert all(row["license"] == "CC0" for row in all_cc0["assets"])
    assert "plain" not in _names(all_cc0), "no recorded license never matches"
    assert "excluded, not checked" in all_cc0["message"]

    assert result(COMMAND, {"license": "CC"})["total_count"] == 0, \
        "exact, not a substring: 'CC' must not match both CC0 and CC-BY"


def test_an_unknown_license_is_flagged_rather_than_silently_empty(attributed):
    answer = result(COMMAND, {"license": "GPL"})

    assert answer["assets"] == []
    assert answer["license_recognized"] is False
    assert "No installed pack records the license" in answer["message"]


def test_pack_names_the_claimant_the_filter_matched(attributed):
    """pack="_cc0" never answers pack: "hats01" """
    unfiltered = _row(result(COMMAND, {"asset_subdir": "clothes"}), "fedora")
    assert unfiltered["pack"] == "hats01", "with no filter, the first claimant"

    filtered = result(COMMAND, {"pack": "_cc0"})
    assert _names(filtered) == ["fedora"]
    assert _row(filtered, "fedora")["pack"] == "hats01_cc0"
    assert all("_cc0" in row["pack"] for row in filtered["assets"])


def test_a_pack_filter_reports_each_pack_it_matched_and_what_is_installed(attributed):
    """A pack registered with nothing on disk shows as 0"""
    answer = result(COMMAND, {"pack": "_cc0"})

    assert answer["matched_packs"] == {"capes01_cc0": 0, "hats01_cc0": 1}
    assert result(COMMAND)["matched_packs"] is None, "no pack filter, nothing matched"
