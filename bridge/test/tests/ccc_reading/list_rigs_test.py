"""
``list_rigs`` against a real MPFB, over a rig tree this test builds.

The claim worth putting to MPFB here is the **weights fallback table**, because
it is the one thing ``list_rigs`` promises that a caller cannot check for
itself: ``default_no_toes`` has no ``weights.default_no_toes.json`` and is
nonetheless a fully weighted rig, because ``RigService.get_rig_weight_fallbacks()``
sends it to ``default``'s. Testing ``weights.<name>.json`` alone would report it
as unweighted, which is wrong in the one direction that matters - it would make
an ordinary rig look broken.

That claim has until now rested on a reading of MPFB's source and on a stub
written from the same reading. So this builds a rig tree, points MPFB's
``LocationService`` at it, and asks MPFB itself what the fallbacks are.

**The tree is the test's own** and every root is redirected, not only the one
being written into: ``<mpfb data>`` decides where the bundled rigs are, and
``user data`` and ``second root`` decide where the custom ones are. A test that
redirected one and inherited the others would pass or fail depending on which
asset packs the developer has installed.
"""

import os

import pytest

from .. import bridge_module
from .._fixtures import build_rig_tree
from .._fixtures import dispatch
from .._fixtures import only_these_data_roots
from .._fixtures import redirected_locations
from .._fixtures import result
from .._fixtures import services_or_skip
from .._fixtures import supplied_resolution
from .._fixtures import write

COMMAND = "list_rigs"

# What ``AssetService.get_custom_rigs()`` accepts a file on. A JSON without an
# ``identifying_bones`` key is skipped, and the skip is silent - which is a fact
# about MPFB this suite learned by writing the wrong fixture first.
CUSTOM_RIG_JSON = '{"identifying_bones": {"root": []}}\n'


@pytest.fixture(name="rigs")
def _with_rig_tree(tmp_path):
    """MPFB pointed at a rig tree of this test's own, and at nothing else."""
    services = services_or_skip()
    mpfb_data = build_rig_tree(str(tmp_path))
    user_data = os.path.join(str(tmp_path), "user-data")
    os.makedirs(os.path.join(user_data, "rigs"))
    with redirected_locations(services, mpfb_data=mpfb_data, user_data=user_data,
                              second_root=os.path.join(str(tmp_path), "no-second-root")):
        yield {"mpfb_data": mpfb_data, "user_data": user_data}


def _by_identifier(answer):
    return {entry["identifier"]: entry for entry in answer["rigs"]}


def test_every_rig_file_is_listed_with_the_identifier_its_adder_takes(rigs):
    """The field this command exists for"""
    answer = result(COMMAND)

    entries = _by_identifier(answer)
    assert set(entries) == {"default", "default_no_toes", "cmu_mb", "rigify.human"}, \
        "one entry per rig.*.json, with the rigify prefix applied; got {!r}".format(
            sorted(entries))
    # The bare name is not what the adding function takes, which is the whole
    # point of reporting both.
    assert entries["rigify.human"]["name"] == "human"
    assert entries["rigify.human"]["add_function"] == "add_builtin_rig"
    assert entries["default"]["family"] == "standard"
    assert answer["count"] == len(answer["rigs"])


def test_a_weights_file_is_not_listed_as_a_rig(rigs):
    """The rig. prefix as the filter"""
    answer = result(COMMAND)

    names = [entry["name"] for entry in answer["rigs"]]
    assert "orphan" not in names, \
        "weights.orphan.json sits beside no rig and must not be listed as one"


def test_mpfbs_own_fallback_table_is_what_resolves_the_weights(rigs):
    """RigService.get_rig_weight_fallbacks(), asked of MPFB rather than assumed"""
    services = services_or_skip()
    rig_service = services["RigService"]

    # The claim, put to MPFB: a rig with no weights file of its own borrows
    # another's, and MPFB is the thing that says whose.
    fallbacks = list(rig_service.get_rig_weight_fallbacks("default_no_toes"))
    assert "default" in fallbacks, \
        "MPFB should send default_no_toes to default's weights, got {!r}".format(fallbacks)

    entries = _by_identifier(result(COMMAND))
    borrowed = entries["default_no_toes"]
    assert borrowed["has_weights"] is True, \
        "a rig that borrows weights is weighted, and reporting otherwise makes it look broken"
    assert borrowed["weights_from"] == "default"
    assert os.path.basename(borrowed["weights_path"]) == "weights.default.json"

    # And the rig that owns its weights reports itself, so the two cases are
    # distinguishable rather than merely both true.
    assert entries["default"]["weights_from"] == "default"


def test_a_rig_with_no_weights_anywhere_says_so(rigs):
    """The other side of the fallback: has_weights false, and nothing invented"""
    entries = _by_identifier(result(COMMAND))

    cmu = entries["cmu_mb"]
    assert cmu["has_weights"] is False
    assert cmu["weights_path"] is None
    assert cmu["weights_from"] is None


def test_a_rig_with_no_ui_enum_entry_is_still_listed(rigs):
    """The directory as the authority, and the enum as decoration only

    Worth noting where the two come from, because they are not the same place:
    the rig *files* are under ``<mpfb data>``, which this fixture redirects, and
    the enum is a UI resource under ``<mpfb root>``, which it does not - so the
    labels below are the installed MPFB's own. That is the real arrangement: a
    label is read out of MPFB's UI JSON, and its absence costs decoration rather
    than an answer.
    """
    write(os.path.join(rigs["mpfb_data"], "rigs", "standard", "rig.homebrew.json"),
          '{"bones": {}}\n')

    entries = _by_identifier(result(COMMAND))

    assert "homebrew" in entries, \
        "a rig file with no enum entry is still addable and must still be listed"
    assert entries["homebrew"]["label"] is None, \
        "no enum entry means no label, which is null rather than the bare name"
    assert entries["homebrew"]["description"] is None
    # And a rig MPFB does publish an enum entry for carries the text, so the
    # null above is the absence of a label rather than the absence of a lookup.
    assert entries["default"]["label"], \
        "MPFB's own standard rig enum should still supply a label for 'default'"


def test_a_custom_rig_is_found_and_uses_no_fallback_table(rigs):
    """add_custom_rig() looking only for weights.<short name>.json"""
    custom_dir = os.path.join(rigs["user_data"], "rigs")
    # `identifying_bones` is what get_custom_rigs() accepts a file on - a JSON
    # without it is silently skipped, which is exactly what
    # unrecognized_custom_rig_files exists to report.
    write(os.path.join(custom_dir, "my_rig.json"), CUSTOM_RIG_JSON)
    write(os.path.join(custom_dir, "weights.my_rig.json"), "{}\n")
    # A second custom rig with no weights beside it, which must *not* borrow
    # `default`'s the way a built-in would.
    write(os.path.join(custom_dir, "bare_rig.json"), CUSTOM_RIG_JSON)

    answer = result(COMMAND, {"refresh": True})
    entries = _by_identifier(answer)

    assert "custom.my_rig" in entries, \
        "a custom rig should be listed under the custom. prefix, got {!r}".format(
            sorted(entries))
    mine = entries["custom.my_rig"]
    assert mine["add_function"] == "add_custom_rig", \
        "the two adding functions are not interchangeable, so the entry names which one"
    assert mine["has_weights"] is True and mine["weights_from"] == "my_rig"

    bare = entries["custom.bare_rig"]
    assert bare["has_weights"] is False, \
        "a custom rig uses no fallback table, so it must not borrow default's weights"
    assert bare["weights_from"] is None


def test_an_unrecognised_json_in_a_user_rigs_directory_is_named(rigs):
    """The set difference against what get_custom_rigs() accepted"""
    custom_dir = os.path.join(rigs["user_data"], "rigs")
    # No `identifying_bones`, so get_custom_rigs() skips it silently. That
    # silence is the whole reason this field is reported.
    write(os.path.join(custom_dir, "notes.json"), '{"this": "is not a rig"}\n')
    write(os.path.join(custom_dir, "weights.notes.json"), "{}\n")

    answer = result(COMMAND, {"refresh": True})

    unrecognized = [os.path.basename(path)
                    for path in answer["unrecognized_custom_rig_files"]]
    assert "notes.json" in unrecognized, \
        "a .json MPFB would not accept as a rig should be named, got {!r}".format(unrecognized)
    # The weights companion is subtracted on top, or a genuinely unrecognised
    # file would be buried in noise on every real install.
    assert "weights.notes.json" not in unrecognized
    assert "not recognized as rig definitions" in answer["message"]


def test_the_scanned_directories_are_reported_even_when_they_do_not_exist(rigs):
    """"We looked here and there was nothing" as the answer a user needs"""
    answer = result(COMMAND)

    by_path = {entry["path"]: entry for entry in answer["rig_dirs"]}
    assert any(entry["family"] == "custom" for entry in answer["rig_dirs"]), \
        "the custom directories are reported whether or not they hold anything"
    missing = [entry for entry in answer["rig_dirs"] if not entry["exists"]]
    assert all(os.path.basename(entry["path"]) == "rigs" for entry in missing)
    assert by_path, "the scanned directories should be named"


def test_rigify_rigs_stay_listed_when_rigify_is_off(rigs):
    """SystemService.check_for_rigify(), and the flag rather than the omission"""
    answer = result(COMMAND)
    entries = _by_identifier(answer)

    human = entries["rigify.human"]
    if answer["rigify_available"]:
        assert human["available"] is True
        assert human["unavailable_reason"] is None
    else:
        # Dropping them would turn an explainable refusal into an unexplained
        # absence, which is the failure mode this flag exists to avoid.
        assert human["available"] is False
        assert "Rigify is not enabled" in human["unavailable_reason"]
        assert "Rigify is not enabled" in answer["message"]
    # Either way the standard rigs are unaffected.
    assert entries["default"]["available"] is True


def test_a_truthy_non_bool_refresh_is_refused_before_the_handler_runs():
    """command_server.dispatch(): "false" is a true value"""
    command_server = bridge_module("command_server")

    answer = dispatch(COMMAND, {"refresh": "false"})

    assert answer["error"] == command_server.ERROR_INVALID_PARAMS
    assert "refresh" in answer["message"]


def test_the_command_is_refused_rather_than_answered_when_mpfb_is_absent():
    """command_server.dispatch() with requires_mpfb and no MPFB"""
    command_server = bridge_module("command_server")
    resolution_module = bridge_module("mpfb_resolution")

    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = dispatch(COMMAND)

    assert answer["error"] == command_server.ERROR_MPFB_UNAVAILABLE
    assert "count" not in answer, "an install problem must not be phrased as an empty library"
