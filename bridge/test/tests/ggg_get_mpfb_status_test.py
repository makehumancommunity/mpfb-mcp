"""
``get_mpfb_status`` against a real MPFB, in all three of the states it reports.

This is the command whose *value* is that MPFB's absence is a successful
answer, so two of the three states it classifies are ones a working Blender
cannot produce. They are **supplied** rather than waited for, exactly as the
``mpfb_unavailable`` refusal is in
[`fff_list_objects_test.py`](fff_list_objects_test.py): the developer's Blender
very likely has a perfectly good MPFB in it, and a test that could only run on
a broken install would never run at all.

Three claims here had until now rested on a reading of MPFB's source and on a
stub written from that reading:

- that ``LocationService.get_mpfb_root()`` really hands back a ``pathlib.Path``
  despite being annotated ``str`` - the reason every path in this answer is
  coerced, and the reason an uncoerced one would turn the whole answer into a
  ``result_not_serializable`` envelope;
- that ``LOWEST_FUNCTIONAL_BLENDER_VERSION`` really is a module-level name in
  systemservice.py rather than a member of the service;
- that ``get_available_data_roots()`` really is already filtered to directories
  that exist, which is what lets ``asset_roots`` and ``paths`` mean different
  things.

The fourth thing worth stating is a naming decision rather than an MPFB fact,
and it is asserted here because it is invisible everywhere else: this command
is **not** ``get_status``. That name is taken by the command reporting the
*bridge*, and the two answer about different software.
"""

import json
import pathlib
import sys

import bpy

from . import bridge_module
from . import dynamic_import
from ._fixtures import dispatch
from ._fixtures import result
from ._fixtures import services_or_skip
from ._fixtures import supplied_resolution

COMMAND = "get_mpfb_status"


def test_the_command_is_not_called_get_status():
    """commands.table: two commands, two pieces of software"""
    commands = dynamic_import("commands", "COMMANDS")

    assert COMMAND in commands, \
        "The MPFB status command should be called {!r}, got {!r}".format(
            COMMAND, sorted(commands))
    assert "get_status" in commands, "The bridge's own status command should still exist"
    assert commands["get_status"].handler is not commands[COMMAND].handler, \
        "The two status commands must not be the same handler"

    # The distinction has to be legible to a client that only reads
    # list_commands, since that is all a discovering caller has.
    assert "bridge" in commands["get_status"].summary.lower(), \
        "get_status' summary should say it is about the bridge"
    assert "MPFB" in commands[COMMAND].summary, \
        "get_mpfb_status' summary should say it is about MPFB"


def test_it_is_not_gated_on_the_thing_it_reports_about():
    """commands.table: requires_mpfb=False, and what that buys"""
    commands = dynamic_import("commands", "COMMANDS")
    assert commands[COMMAND].requires_mpfb is False, \
        "A status command gated on MPFB answers only the question nobody needs asking"

    resolution_module = bridge_module("mpfb_resolution")
    with supplied_resolution(resolution_module.STATE_ABSENT):
        envelope = dispatch(COMMAND)

    # The whole point: an absent MPFB is an ok envelope, not mpfb_unavailable.
    assert envelope["status"] == "ok", \
        "Absence must be a successful answer, got {!r}".format(envelope)
    assert envelope["result"]["state"] == "absent"
    assert envelope["result"]["candidate_modules"] == []


def test_the_absent_tier_carries_only_what_bpy_alone_can_say():
    """commands.get_mpfb_status: the first tier"""
    resolution_module = bridge_module("mpfb_resolution")
    with supplied_resolution(resolution_module.STATE_ABSENT):
        answer = result(COMMAND)

    assert answer["package"] is None and answer["enabled"] is None
    assert answer["blender"]["version"] == bpy.app.version_string
    # Shapes, not nulls: a key that is always present and always null would say
    # "we looked at the asset roots and there are none" on an install where
    # nothing was ever looked at.
    for absent_key in ("version", "build_info", "paths", "asset_roots", "asset_packs",
                       "rigify_available", "is_source_dist", "addon_installation_path"):
        assert absent_key not in answer, \
            "{!r} should be absent in the absent state, not null".format(absent_key)
    assert "platform" not in answer["blender"], \
        "Even blender.platform needs a service to answer, so it waits for one"


def test_the_message_is_the_one_sentence_the_resolution_keeps():
    """mpfb_resolution.STATE_MESSAGES as the single wording"""
    resolution_module = bridge_module("mpfb_resolution")
    messages = dynamic_import("mpfb_resolution", "STATE_MESSAGES")

    for state in (resolution_module.STATE_ABSENT, resolution_module.STATE_NOT_INITIALIZED):
        with supplied_resolution(state):
            answer = result(COMMAND)
        # One wording, in one place. The generated payload carries its own copy
        # of these three sentences, so a divergence here is what FR 031's live
        # comparison would report as a field-by-field difference.
        assert answer["message"] == messages[state], \
            "The sentence for {!r} should be the resolution's own".format(state)
        assert answer["state"] == state


def test_an_ok_install_answers_all_three_tiers():
    """commands.get_mpfb_status against the MPFB this Blender really has"""
    services_or_skip()
    answer = result(COMMAND)

    assert answer["state"] == "ok"
    assert answer["package"], "An ok install has a package name"
    assert answer["enabled"] is True, \
        "This suite enables the bridge, not MPFB; MPFB being enabled is the prerequisite"
    assert isinstance(answer["paths"], dict) and answer["paths"]
    assert isinstance(answer["asset_packs"]["count"], int)
    assert isinstance(answer["rigify_available"], bool)
    assert isinstance(answer["blender"]["meets_mpfb_minimum"], bool)


def test_every_path_is_a_string_so_the_answer_can_be_serialized():
    """LocationService.get_mpfb_root() returning a pathlib.Path"""
    services = services_or_skip()

    # The quirk the coercion exists for, asserted against MPFB rather than
    # against a stub reproducing it. If this ever stops being true the coercion
    # is merely redundant; if the coercion went away while it is true, every
    # call to this command would come back as result_not_serializable.
    raw_root = services["LocationService"].get_mpfb_root()
    assert isinstance(raw_root, (str, pathlib.Path))

    answer = result(COMMAND)
    assert isinstance(answer["addon_installation_path"], str)
    for name, entry in answer["paths"].items():
        assert entry["path"] is None or isinstance(entry["path"], str), \
            "paths.{:s} should be a string or null".format(name)
    # The dispatcher serializes before it commits to an answer, so this is
    # belt and braces - but it is the assertion that names what would break.
    json.dumps(answer)


def test_asset_roots_are_the_ones_that_exist_and_paths_are_the_ones_configured():
    """AssetService.get_available_data_roots() being pre-filtered"""
    import os  # pylint: disable=import-outside-toplevel

    services_or_skip()
    answer = result(COMMAND)

    for root in answer["asset_roots"]:
        assert os.path.isdir(root), \
            "asset_roots is what MPFB will actually search, so {!r} should exist".format(root)
    # paths is the other half of that pairing: it reports what is *configured*,
    # including a second root that is set and missing, which is exactly the
    # install problem this command is for diagnosing.
    for name, entry in answer["paths"].items():
        assert set(entry) == {"path", "configured"}, \
            "paths.{:s} should be a path and a flag".format(name)
        assert entry["configured"] == bool(entry["path"])


def test_the_blender_minimum_is_read_off_the_service_module():
    """systemservice.LOWEST_FUNCTIONAL_BLENDER_VERSION, through sys.modules"""
    services = services_or_skip()
    module = sys.modules[services["SystemService"].__module__]
    assert hasattr(module, "LOWEST_FUNCTIONAL_BLENDER_VERSION"), \
        "MPFB no longer publishes this constant; the command now reports null for it"

    answer = result(COMMAND)
    expected = ".".join(str(part) for part in module.LOWEST_FUNCTIONAL_BLENDER_VERSION)
    assert answer["blender"]["mpfb_minimum_version"] == expected


def test_the_command_takes_no_parameters():
    """command_server.dispatch() with an argument this command does not have"""
    command_server = bridge_module("command_server")

    envelope = dispatch(COMMAND, {"refresh": True})

    assert envelope["error"] == command_server.ERROR_INVALID_PARAMS, \
        "An unknown parameter must be refused rather than ignored"
    assert "refresh" in envelope["message"]
