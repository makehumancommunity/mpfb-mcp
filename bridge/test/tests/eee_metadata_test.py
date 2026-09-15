"""
The claims about the add-on that are kept in step by hand.

Two of them, and both are the kind of thing that is correct when written and
wrong three releases later, silently, in a way no other test would notice:
the version this add-on reports against the version Blender reads from its
manifest, and the description ``list_commands`` hands out against the table the
dispatcher actually uses.

Neither is interesting. Both are cheap, and the failure each prevents is an
add-on confidently telling a client something untrue about itself.
"""

import os
import tomllib

from . import bridge_package
from . import dynamic_import


def _manifest():
    """The add-on's own ``blender_manifest.toml``, parsed.

    Found next to the package rather than by a path from this file: the tests
    resolve the add-on through Blender's extension repositories, so the checkout
    they are running against is whatever ``__file__`` says it is.
    """
    package = bridge_package()
    path = os.path.join(os.path.dirname(package.__file__), "blender_manifest.toml")
    assert os.path.exists(path), "The add-on should ship a manifest at {:s}".format(path)
    with open(path, "rb") as stream:
        return tomllib.load(stream)


def test_the_reported_version_matches_the_manifest():
    """version.BRIDGE_VERSION against blender_manifest.toml"""
    # There are two of them because the manifest is data Blender reads and
    # BRIDGE_VERSION is a value a command reports, and nothing in the extension
    # format publishes one to the other. A comment saying "keep these in step"
    # is what this was before, and a comment is not a check.
    bridge_version = dynamic_import("version", "BRIDGE_VERSION")
    manifest_version = _manifest()["version"]

    assert bridge_version == manifest_version, \
        "BRIDGE_VERSION is {:s} but the manifest says {:s}. A released add-on that misreports " \
        "its own version is one a client cannot reason about".format(
            bridge_version, manifest_version)


def test_the_manifest_declares_a_blender_floor_the_cli_command_needs():
    """blender_manifest.toml blender_version_min"""
    # bpy.utils.register_cli_command is what the headless drive mechanism hangs
    # off, and the add-on registers it unguarded. That is only safe while the
    # declared floor is past the release that added it - so if somebody lowers
    # the floor, this is the test that says what else has to change.
    floor = _manifest()["blender_version_min"]
    major = int(floor.split(".")[0])

    assert major >= 5, \
        "blender_version_min is {:s}. The add-on registers a CLI command without a hasattr " \
        "guard, which needs a floor where bpy.utils.register_cli_command certainly " \
        "exists".format(floor)


def test_list_commands_describes_the_table_the_dispatcher_uses():
    """commands.list_commands.list_commands()"""
    # A discoverability command that kept its own catalogue would be one more
    # thing able to drift from the vocabulary it claims to describe. It reads
    # the dispatcher's live table, and this asserts that it really does.
    commands = dynamic_import("commands", "COMMANDS")
    start = dynamic_import("command_server", "start")
    stop = dynamic_import("command_server", "stop")
    dispatch = dynamic_import("command_server", "dispatch")

    start("127.0.0.1", 0, commands)
    try:
        answer = dispatch({"command": "list_commands"})
        short = dispatch({"command": "list_commands", "params": {"include_params": False}})
    finally:
        stop()

    described = answer["result"]["commands"]
    assert [entry["name"] for entry in described] == sorted(commands), \
        "list_commands should describe exactly the table, in a stable order"
    assert answer["result"]["command_count"] == len(commands), \
        "The count should agree with the list beside it"

    for entry in described:
        command = commands[entry["name"]]
        assert entry["requires_mpfb"] == command.requires_mpfb, \
            "{:s} should report its real MPFB requirement".format(entry["name"])
        assert entry["summary"] == command.summary, \
            "{:s} should report its real summary".format(entry["name"])
        assert len(entry["params"]) == len(command.params), \
            "{:s} should describe every parameter it declares".format(entry["name"])

    for entry in short["result"]["commands"]:
        assert "params" not in entry, \
            "include_params=False should leave the parameter specifications out"


def test_every_command_carries_a_usable_description():
    """commands.table.COMMANDS descriptions"""
    # The table is what a caller reads to decide what to ask for. A command with
    # an empty summary, or a parameter with no description, is one the caller
    # has to guess at - and guessing is what the closed vocabulary removed.
    commands = dynamic_import("commands", "COMMANDS")

    for name, command in commands.items():
        assert command.summary.strip(), "Command {:s} should carry a summary".format(name)
        assert command.summary.endswith("."), \
            "Command {:s}'s summary should be a sentence".format(name)
        for param in command.params:
            assert param.description.strip(), \
                "Parameter {:s} of {:s} should be described".format(param.name, name)
