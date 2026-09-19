"""
``list_targets`` against a real MPFB, over a target tree this test builds.

The largest migration in FR 031 and the one with the most claims about MPFB in
it, none of which had been asked of MPFB before. What is put to it here:

- **that a name over 60 characters is encoded**, so the filename and the
  addressable ``shapekey_name`` really do differ. This is the field the whole
  command exists for, and addressing a long target by its filename fails
  *silently*;
- **that MPFB's user-targets scan matches only ``*.target``**, so a
  ``.target.gz`` in a user targets directory is on disk, loadable, and absent
  from MPFB's own panels - which is what ``listed_in_mpfb_ui: false`` reports;
- **that a user directory sharing a bundled section's name is merged into it**
  rather than making a second section, which is what ``source: "both"`` means;
- **that MPFB's category naming is a substring replace** which leaves ``.gz``
  behind, so a gzipped custom target is a category called ``vwide.gz`` whose
  shape key is called ``vwide``.

**Everything is redirected**, both the bundled data directory and the user one,
because ``get_available_data_roots()`` is a union: a test that pointed one at a
fixture and inherited the rest would answer partly from whatever targets the
developer has installed.
"""

import os

import pytest

from . import bridge_module
from ._fixtures import LONG_USER_TARGET
from ._fixtures import build_target_tree
from ._fixtures import dispatch
from ._fixtures import only_these_data_roots
from ._fixtures import result
from ._fixtures import services_or_skip
from ._fixtures import supplied_resolution

COMMAND = "list_targets"


@pytest.fixture(name="targets")
def _with_target_tree(tmp_path):
    """MPFB pointed at a target tree of this test's own, and at nothing else."""
    services = services_or_skip()
    tree = build_target_tree(str(tmp_path))
    with only_these_data_roots(services, mpfb_data=tree["mpfb_data"],
                               user_data=tree["user_data"]):
        yield tree


def _sections(answer):
    return {entry["name"]: entry for entry in answer["sections"]}


def test_the_bundled_index_and_the_user_directories_are_both_reported(targets):
    """target.json read, and the user directories scanned beside it"""
    answer = result(COMMAND)

    assert answer["target_json_exists"] is True
    assert answer["target_json_path"] == targets["target_json_path"]
    assert answer["system_targets_dir"] == targets["system_targets"]

    sections = _sections(answer)
    # Five from target.json, plus the user-only one, plus the custom section
    # MPFB synthesizes.
    assert {"arms", "nose", "chin", "ears", "measure"} <= set(sections)
    assert "animal" in sections, \
        "a user directory with no bundled counterpart is a section of its own"
    assert sections["animal"]["source"] == "user"
    assert sections["nose"]["source"] == "system"


def test_a_user_directory_sharing_a_bundled_name_is_merged_into_it(targets):
    """MPFB appending rather than making a second section"""
    sections = _sections(result(COMMAND))

    assert sections["arms"]["source"] == "both", \
        "a section with both sources should say so, got {!r}".format(sections["arms"])
    assert sections["arms"]["category_count"] >= 2, \
        "the bundled categories are still there"
    assert sections["arms"]["target_count"] >= 1, \
        "and the user target in the same-named directory is counted beside them"


def test_a_long_name_is_encoded_so_the_filename_does_not_address_it(targets):
    """TargetService.filename_to_shapekey_name(), the field this command is for"""
    services = services_or_skip()
    answer = result(COMMAND, {"section": "animal"})

    entries = {entry["name"]: entry for entry in answer["user_targets"]}
    assert LONG_USER_TARGET in entries, \
        "the long-named target should be listed, got {!r}".format(sorted(entries))
    entry = entries[LONG_USER_TARGET]

    # The claim, put to MPFB: the derivation is not the identity function.
    assert entry["shapekey_name"] != entry["name"], \
        "a name over 60 characters should be encoded, got {!r}".format(entry["shapekey_name"])
    assert len(entry["shapekey_name"]) <= 60, \
        "the encoding exists to fit Blender's shape key name limit"
    assert entry["shapekey_name"] == services["TargetService"].filename_to_shapekey_name(
        entry["path"], macrodetail=False), \
        "the reported name should be MPFB's own derivation rather than a copy of the rule"


def test_a_short_name_is_reported_unchanged(targets):
    """The other half: the encoding is not applied to everything"""
    entries = {entry["name"]: entry for entry in result(COMMAND, {"section": "animal"})[
        "user_targets"]}

    assert entries["cat_ears"]["shapekey_name"] == "cat_ears", \
        "a short name needs no encoding, so the two are equal"


def test_a_gzipped_user_target_is_listed_and_flagged_as_invisible_to_mpfb(targets):
    """MPFB's user scan matching only *.target"""
    entries = {entry["name"]: entry for entry in result(COMMAND, {"section": "animal"})[
        "user_targets"]}

    assert "winged" in entries, \
        "a .target.gz is on disk and loadable, so it is listed, got {!r}".format(
            sorted(entries))
    assert entries["winged"]["file_type"] == "target.gz"
    # The asymmetry is MPFB's, not this command's: its own scan matches only
    # "*.target", so this file is invisible in MPFB's modeling panels.
    assert entries["winged"]["listed_in_mpfb_ui"] is False
    assert entries["cat_ears"]["listed_in_mpfb_ui"] is True


def test_the_custom_section_is_labelled_as_mpfb_labels_it(targets):
    """The synthesized section, and where its name diverges from its shape key"""
    answer = result(COMMAND)
    sections = _sections(answer)

    assert "custom" in sections, "the custom asset roots should produce a section"
    assert sections["custom"]["label"] == "Custom targets", \
        "MPFB names this section rather than its directory naming it"

    entries = {entry["name"]: entry for entry in result(COMMAND, {"section": "custom"})[
        "user_targets"]}
    assert "vwide" in entries, \
        "the display name strips both extensions, got {!r}".format(sorted(entries))
    # MPFB's *category* name for this file is "vwide.gz", because its naming is
    # a substring replace of ".target" that leaves ".gz" behind - while the
    # shape key it loads under is "vwide". Both exist, which is why this
    # command reports the addressable one.
    assert entries["vwide"]["shapekey_name"] == "vwide"
    assert entries["vwide"]["file_type"] == "target.gz"


def test_a_section_is_browsable_one_at_a_time_and_its_categories_come_back(targets):
    """The bundled index reported by path, and its sections by request"""
    answer = result(COMMAND, {"section": "arms"})

    assert answer["section_recognized"] is True
    assert answer["categories"] is not None, "a bundled section has categories"
    names = [category["name"] for category in answer["categories"]]
    assert "lowerarm-scale-depth-decr-incr" in names
    sided = [category for category in answer["categories"]
             if category["name"] == "lowerarm-scale-depth-decr-incr"][0]
    assert sided["has_left_and_right"] is True
    # The opposites table is what tells a caller that setting one target
    # meaningfully means clearing its opposite, so it is passed through.
    assert sided["opposites"]["positive-left"] == "l-lowerarm-scale-depth-incr"


def test_a_section_that_is_only_a_user_directory_has_no_categories(targets):
    """None, which is not the same as an empty list"""
    answer = result(COMMAND, {"section": "animal"})

    assert answer["section_recognized"] is True
    assert answer["categories"] is None, \
        "a user-only section has no bundled categories at all"
    assert answer["user_targets"], "and its targets are what it does have"


def test_a_bundled_section_with_no_categories_still_answers_as_one(targets):
    """"measure" - empty rather than falling through to the target listing"""
    answer = result(COMMAND, {"section": "measure"})

    assert answer["section_recognized"] is True
    assert answer["categories"] == [], \
        "an empty list means the section has none, where None would mean it is not that kind"
    assert answer["total_count"] == 0


def test_an_unknown_section_is_flagged_rather_than_silently_empty(targets):
    """section_recognized, and the exactness of the match"""
    answer = result(COMMAND, {"section": "armz"})

    assert answer["section_recognized"] is False
    assert "No target section called" in answer["message"]
    assert result(COMMAND, {"section": "ARMS"})["section_recognized"] is True, \
        "exact, but case-insensitive"


def test_a_bundled_directory_target_json_never_mentions_is_reported(targets):
    """The diff, never a hardcoded pair of names"""
    answer = result(COMMAND)

    unindexed = {entry["name"]: entry for entry in answer["unindexed_system_target_dirs"]}
    assert "asym" in unindexed, \
        "a bundled directory with targets and no index entry should be named, got {!r}".format(
            sorted(unindexed))
    assert unindexed["asym"]["target_count"] == 1
    # A directory holding no target file at all drops out by the count rather
    # than by a name check, which is what keeps this from needing a blocklist.
    assert "_images" not in unindexed


def test_the_cap_is_always_declared(targets):
    """truncated, on whichever list the call is really about"""
    everything = result(COMMAND, {"limit": 1000})
    assert everything["truncated"] is False

    first = result(COMMAND, {"limit": 1, "offset": 0})
    second = result(COMMAND, {"limit": 1, "offset": 1})

    assert first["truncated"] is True
    assert first["total_count"] == everything["total_count"]
    assert first["user_targets"] != second["user_targets"], \
        "two pages of one query must not repeat"


def test_bad_paging_arguments_are_refused_before_the_handler_runs():
    """command_server.dispatch(): True is an int"""
    command_server = bridge_module("command_server")

    for params in ({"limit": True}, {"offset": True}, {"limit": -1}, {"limit": 1001}):
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
    assert "count" not in answer
