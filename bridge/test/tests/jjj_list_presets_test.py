"""
``list_presets`` against a real MPFB and a real config directory.

The first command in this suite whose subject is a **filesystem** rather than a
scene, and the first whose fixture is a tree the test builds and points MPFB
at. That tree is moved from ``tests/blender_stubs.py``'s ``PresetTestCase``
rather than reinvented: the same four presets, the same one with a name MPFB's
panel accepts and mpfb-mcp refuses, the same three near misses MPFB's two-step
match rejects for three different reasons. What changes is that MPFB really
walks it.

Two claims are put to MPFB here for the first time:

- **that ``update_list_of_human_presets()``'s match is what the shared module
  reproduces**. It is an ``fnmatch`` against ``human.*.json`` followed by a
  regex whose group must be non-empty, and the three near misses are the three
  ways that pair says no. A simplification of it would make this command list
  files MPFB's own dropdown does not.
- **that ``_EXISTING_PRESETS`` really is cached until a save**, which is the
  whole reason this command reports ``missing_from_mpfb_list`` instead of
  quietly rescanning. A preset written into the directory after MPFB has
  listed it is invisible to MPFB and visible to the ``os.listdir`` here, and
  the difference between the two lists is the answer.

**The cache is also what makes this suite order-dependent**, and it is handled
rather than discovered: every test calls
``HumanService.invalidate_preset_cache()`` - or the ``use_cache=False`` path -
through :func:`_with_presets`, so a test never inherits the list some earlier
test warmed.
"""

import os

import pytest

from . import bridge_module
from ._fixtures import dispatch
from ._fixtures import redirected_locations
from ._fixtures import result
from ._fixtures import services_or_skip
from ._fixtures import supplied_resolution
from ._fixtures import write

COMMAND = "list_presets"

# The preset MPFB will list and mpfb-mcp's tools will refuse. MPFB's panel
# rejects only an empty name and one containing a space... which is this one,
# so it is a name that panel would refuse and its own *scan* still finds -
# written by hand, or by an older MPFB. Either way it is in somebody's
# directory.
UNADDRESSABLE_PRESET = "hand made"

SAVED = ("alice", "bob-2", UNADDRESSABLE_PRESET)

# Three files MPFB's match refuses, each for its own reason: nothing between
# the dots, the wrong prefix, and the wrong suffix.
NEAR_MISSES = ("human.json", "humans.foo.json", "human.decoy.json.bak")


def _preset_json(name):
    """The least a preset file may hold and still be one. Nothing parses it here."""
    return '{"name": "' + name + '", "phenotype": {}}\n'


def _forget_mpfbs_list(services):
    """Drop MPFB's cached preset list, however this MPFB spells that.

    ``_EXISTING_PRESETS`` is a module global invalidated by exactly one thing,
    a save. There is no public "forget this" for a test to call, so the
    supported route is the one this command's ``refresh`` uses:
    ``use_cache=False`` rescans *and* repopulates in one call.

    **It raises when the config directory is missing**, because
    ``update_list_of_human_presets()`` does a bare ``os.listdir()``. That is the
    quirk ``list_presets`` guards against by checking the directory before
    asking MPFB anything, and it is swallowed here for the same reason: a test
    pointing MPFB at a directory that does not exist is testing exactly that,
    and its cleanup should not be the thing that fails.
    """
    try:
        services["HumanService"].get_list_of_human_presets(as_list_enum=False, use_cache=False)
    except OSError:
        pass


def _config_directory(tmp_path):
    """A config directory holding what one that has been used actually holds."""
    confdir = os.path.join(str(tmp_path), "config")
    for name in SAVED:
        write(os.path.join(confdir, "human." + name + ".json"), _preset_json(name))
    for filename in NEAR_MISSES:
        write(os.path.join(confdir, filename), "{}\n")
    return confdir


@pytest.fixture(name="presets")
def _with_presets(tmp_path):
    """MPFB pointed at a config directory of this test's own, cache dropped.

    The cache is dropped on the way **in** and on the way out: on the way in so
    that this test does not inherit a list warmed against the developer's own
    config directory, and on the way out so that the next test does not inherit
    one warmed against a directory that no longer exists.
    """
    services = services_or_skip()
    confdir = _config_directory(tmp_path)
    with redirected_locations(services, user_config=confdir):
        _forget_mpfbs_list(services)
        yield confdir
    _forget_mpfbs_list(services)


def test_the_saved_presets_are_listed_and_the_near_misses_are_not(presets):
    """HumanService.update_list_of_human_presets()' two-step match"""
    answer = result(COMMAND)

    names = sorted(record["name"] for record in answer["presets"])
    assert names == sorted(SAVED), \
        "MPFB should list exactly the human.<name>.json files, got {!r}".format(names)
    assert answer["count"] == len(names)
    assert answer["config_dir"] == presets
    assert answer["config_dir_exists"] is True
    # The three near misses are the three ways MPFB's fnmatch-plus-regex says
    # no, and a simplification of that pair would list at least one of them.
    assert answer["files_in_config_dir"] == len(SAVED)


def test_each_entry_carries_the_file_facts_mpfb_does_not_have(presets):
    """os.stat as the only source of size and age"""
    answer = result(COMMAND)

    by_name = {record["name"]: record for record in answer["presets"]}
    alice = by_name["alice"]
    assert alice["exists"] is True
    assert alice["size_bytes"] == os.path.getsize(
        os.path.join(presets, "human.alice.json")), \
        "size_bytes should be the file's, since MPFB's list is bare names"
    assert alice["modified"], "an mtime should be reported as an ISO timestamp"
    assert "+" in alice["modified"] or "Z" in alice["modified"] or "-" in alice["modified"], \
        "the timestamp carries an offset, or nobody can check it against their clock"
    assert alice["path"] == os.path.join(presets, "human.alice.json")


def test_a_name_mpfb_accepts_and_mpfb_mcp_refuses_is_flagged_rather_than_hidden(presets):
    """The whole reason `addressable` exists"""
    answer = result(COMMAND)

    by_name = {record["name"]: record for record in answer["presets"]}
    assert UNADDRESSABLE_PRESET in by_name, \
        "MPFB lists a name with a space in it, so this command must too"
    entry = by_name[UNADDRESSABLE_PRESET]
    assert entry["addressable"] is False
    assert entry["not_addressable_reason"], "a refusal needs a sentence, not a flag"
    assert "' '" in entry["not_addressable_reason"], \
        "the reason should name the offending character: {!r}".format(
            entry["not_addressable_reason"])
    # And the listing says so out loud, since a caller reading only `message`
    # would otherwise find out when the load fails.
    assert "will not accept" in answer["message"]

    for name in ("alice", "bob-2"):
        assert by_name[name]["addressable"] is True
        assert by_name[name]["not_addressable_reason"] is None


def test_a_preset_written_after_mpfb_listed_is_reported_rather_than_rescanned(presets):
    """_EXISTING_PRESETS being invalidated by nothing but a save"""
    result(COMMAND)  # warms MPFB's list with exactly the three presets above

    write(os.path.join(presets, "human.carol.json"), _preset_json("carol"))
    answer = result(COMMAND)

    # The claim the whole `missing_from_mpfb_list` field rests on. If MPFB
    # turned out to rescan on its own, this command would be reporting a
    # difference that can never be non-empty.
    assert "carol" not in [record["name"] for record in answer["presets"]], \
        "MPFB's list is cached until a save, so a new file should be invisible to it"
    assert answer["missing_from_mpfb_list"] == ["carol"], \
        "the difference should be observed and reported, got {!r}".format(
            answer["missing_from_mpfb_list"])
    assert answer["files_in_config_dir"] == len(SAVED) + 1
    assert "not in MPFB's list" in answer["message"]
    assert answer["refreshed"] is False


def test_refresh_is_the_rescan_and_says_that_it_ran(presets):
    """get_list_of_human_presets(use_cache=False)"""
    result(COMMAND)
    write(os.path.join(presets, "human.dave.json"), _preset_json("dave"))

    answer = result(COMMAND, {"refresh": True})

    assert "dave" in [record["name"] for record in answer["presets"]]
    assert answer["missing_from_mpfb_list"] == [], \
        "after a rescan there is nothing left for a rescan to gain"
    assert answer["refreshed"] is True


def test_a_name_in_mpfbs_list_whose_file_has_gone_is_an_ordinary_answer(presets):
    """exists: false, which MPFB's own list cannot express"""
    result(COMMAND)  # MPFB now holds all three names

    os.remove(os.path.join(presets, "human.alice.json"))
    answer = result(COMMAND)

    by_name = {record["name"]: record for record in answer["presets"]}
    assert by_name["alice"]["exists"] is False
    assert by_name["alice"]["size_bytes"] is None
    assert by_name["alice"]["modified"] is None
    assert "no longer have a file" in answer["message"]


def test_an_empty_config_directory_is_an_answer_rather_than_an_error(tmp_path):
    """The empty case, which must not read like a broken install"""
    services = services_or_skip()
    empty = os.path.join(str(tmp_path), "empty-config")
    os.makedirs(empty)
    with redirected_locations(services, user_config=empty):
        _forget_mpfbs_list(services)
        answer = result(COMMAND)
    _forget_mpfbs_list(services)

    assert answer["count"] == 0
    assert answer["presets"] == []
    assert answer["config_dir_exists"] is True, \
        "an empty directory exists, and the two facts are reported separately"
    assert "No character presets" in answer["message"]
    assert answer["listing_failed"] is None


def test_a_missing_config_directory_says_the_install_is_broken(tmp_path):
    """config_dir_exists: false, and what it means"""
    services = services_or_skip()
    missing = os.path.join(str(tmp_path), "not-created")
    with redirected_locations(services, user_config=missing):
        _forget_mpfbs_list(services)
        # The quirk the guard exists for, asserted against MPFB: its own
        # listing does a bare os.listdir() and raises rather than answering.
        with pytest.raises(OSError):
            services["HumanService"].get_list_of_human_presets(
                as_list_enum=False, use_cache=False)
        answer = result(COMMAND)
    _forget_mpfbs_list(services)

    assert answer["config_dir_exists"] is False
    assert answer["listing_failed"] is None, \
        "the directory is checked before MPFB is asked, so nothing failed"
    assert answer["count"] == 0
    # MPFB creates this directory when it loads, so its absence is an install
    # problem rather than "nothing has been saved yet".
    assert "install is broken" in answer["message"]


def test_a_truthy_non_bool_refresh_is_refused_before_the_handler_runs():
    """command_server.dispatch(): "false" is a true value"""
    command_server = bridge_module("command_server")

    for value in ("false", "true", 1, 0, None):
        answer = dispatch(COMMAND, {"refresh": value})
        assert answer["error"] == command_server.ERROR_INVALID_PARAMS, \
            "refresh={!r} should be refused rather than rescanning the disk".format(value)
        assert "refresh" in answer["message"]


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    """command_server.dispatch() with requires_mpfb and no MPFB"""
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = dispatch(COMMAND)

    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE
    assert "count" not in answer, "an install problem must not be phrased as an empty directory"
