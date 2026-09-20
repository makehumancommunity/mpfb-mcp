# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for mpfbmcp.backend: which transport a call takes, and what comes back.

The seam is the one module that knows there are two transports, so this is the
one module that may know it too. **What is under test is routing, not
behaviour**: that a migrated tool follows the configured preference, that an
unmigrated one cannot be made to leave the generated path however the
environment is set, that an unrecognised backend fails instead of quietly
falling back, and that an error envelope carries the same slug whichever side
produced it.

The routing assertions are made by watching *which fake server was spoken to*
rather than by patching the two send functions and checking which mock was
called. The difference matters: a mock asserts that this module called what
this module was expected to call, while a fake asserts that bytes arrived
somewhere, which is the claim a tool's caller actually depends on.

Run with::

    python -m unittest tests.test_backend -v
"""

__all__ = ()

import json
import unittest

from mpfbmcp import backend, bridge_connection
from tests import fake_bridge


# The payloads whose bridge command is deliberately not named after them. One,
# and it is one because the bridge already answers `get_status` about itself.
_RENAMED_ON_THE_BRIDGE = {"get_status.py": "get_mpfb_status"}


def _program_of(request: bytes) -> str:
    """The code out of one blender_mcp request, as the add-on would read it."""
    return json.loads(request.partition(b"\0")[0].decode("utf-8"))["code"]


class BothBackendsTestCase(fake_bridge.BridgeTestCase):
    """A fake blender_mcp and a fake bridge, and the variable choosing between.

    Both are started for every test in this group, because most of the claims
    here are about the one that was *not* spoken to.
    """

    def setUp(self) -> None:
        super().setUp()
        self.set_env_var(backend.BACKEND_VARIABLE, None)
        self.addon = self.run_fake_server(
            {"status": "ok", "result": {"count": 0, "via": "blender_mcp"}})
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope(
                "list_objects", {"count": 0, "via": "bridge"}),
        })

    def prefer(self, name: str | None) -> None:
        self.set_env_var(backend.BACKEND_VARIABLE, name)


class PreferenceTests(BothBackendsTestCase):
    def test_the_default_is_blender_mcp(self) -> None:
        self.prefer(None)

        self.assertEqual(backend.preferred_backend(), backend.BACKEND_BLENDER_MCP)

    def test_an_empty_value_is_treated_as_unset(self) -> None:
        # A shell exporting an empty variable is the ordinary way one ends up
        # set to nothing, and that is not a configuration mistake.
        self.prefer("   ")

        self.assertEqual(backend.preferred_backend(), backend.BACKEND_BLENDER_MCP)

    def test_the_bridge_can_be_asked_for_by_name(self) -> None:
        self.prefer(backend.BACKEND_BRIDGE)

        self.assertEqual(backend.preferred_backend(), backend.BACKEND_BRIDGE)

    def test_an_unrecognised_backend_fails_rather_than_falling_back(self) -> None:
        # A typo that quietly leaves every call on the old path is
        # indistinguishable from the bridge not working, which is the most
        # expensive shape a configuration mistake can take.
        self.prefer("bridg")

        with self.assertRaises(ValueError) as raised:
            backend.send("list_objects.py", params={"object_type": None})

        self.assertIn("bridg", str(raised.exception))
        self.assertIn(backend.BACKEND_BRIDGE, str(raised.exception))
        self.assertEqual(self.addon.requests, [], "nothing should have been sent")
        self.assertEqual(self.bridge.requests, [], "and nothing to the bridge either")


class RoutingTests(BothBackendsTestCase):
    def test_a_migrated_tool_takes_the_generated_path_by_default(self) -> None:
        self.prefer(None)

        response = backend.send("list_objects.py", params={"object_type": None})

        self.assertEqual(response["result"]["via"], "blender_mcp")
        self.assertEqual(len(self.addon.requests), 1)
        self.assertEqual(self.bridge.requests, [])
        self.assertIn("# --- payload: list_objects.py ---", _program_of(self.addon.requests[0]))

    def test_a_migrated_tool_takes_the_bridge_when_it_is_preferred(self) -> None:
        self.prefer(backend.BACKEND_BRIDGE)

        response = backend.send("list_objects.py", params={"object_type": None})

        self.assertEqual(response["result"]["via"], "bridge")
        self.assertEqual(self.addon.requests, [])
        self.assertEqual(self.bridge.commands(), ["get_status", "list_objects"])

    def test_the_params_are_the_same_dict_on_both_paths(self) -> None:
        # Both sides receive the tool's already-validated arguments and neither
        # reshapes them. There is deliberately no per-path parameter mapping,
        # and this is what would fail if one were added.
        params = {"object_type": "Basemesh"}

        self.prefer(None)
        backend.send("list_objects.py", params=params)
        self.prefer(backend.BACKEND_BRIDGE)
        backend.send("list_objects.py", params=params)

        program = _program_of(self.addon.requests[0])
        generated = json.loads(program.split("PARAMS = json.loads(")[1].split(")\n")[0].strip("'"))
        self.assertEqual(generated, params)
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], params)

    def test_an_unmigrated_tool_stays_on_the_generated_path_in_both(self) -> None:
        # `create_human.py` is a mutating tool, so it stays unmigrated until
        # stage 4 and this test keeps a subject for as long as the table has
        # anything left in it to be the point of.
        for preference in (None, backend.BACKEND_BRIDGE):
            with self.subTest(backend=preference):
                self.addon.requests.clear()
                self.bridge.requests.clear()
                self.prefer(preference)

                backend.send("create_human.py", params={})

                self.assertEqual(len(self.addon.requests), 1)
                self.assertEqual(self.bridge.requests, [],
                                 "a tool with no command has nowhere else to go")

    def test_the_table_names_a_command_for_every_payload_in_it(self) -> None:
        # The table is the list of what has been migrated, so an entry naming a
        # payload that does not exist would misreport the migration's progress.
        from mpfbmcp import codegen  # pylint: disable=import-outside-toplevel

        payloads = set(codegen.payload_names())
        for payload, command in backend.MIGRATED_COMMANDS.items():
            with self.subTest(payload=payload):
                self.assertIn(payload, payloads)
                if payload in _RENAMED_ON_THE_BRIDGE:
                    self.assertEqual(command, _RENAMED_ON_THE_BRIDGE[payload])
                    continue
                # Payload and command share a name, which is what lets a mixed
                # record be sorted by one word.
                self.assertEqual(command, payload[:-len(".py")])

    def test_the_one_renamed_command_is_the_one_that_had_to_be(self) -> None:
        # Spelled out rather than tolerated by the loop above: the bridge's own
        # `get_status` reports the bridge, and this one reports MPFB. Any
        # further exception is a naming decision somebody should have to make
        # on purpose, so the exception list is asserted rather than consulted.
        self.assertEqual(_RENAMED_ON_THE_BRIDGE, {"get_status.py": "get_mpfb_status"})
        for payload in _RENAMED_ON_THE_BRIDGE:
            self.assertIn(payload, backend.MIGRATED_COMMANDS)


class FragmentTests(BothBackendsTestCase):
    """What a tool carrying a shared fragment does on each path.

    Five of the nine tools FR 031 migrated name a fragment, three of them
    through the session source cache, and the requirement is that **a tool
    passes the same call on both paths**: `shared` and `cached_shared` are what
    they have always been on the generated path and are *ignored* on the bridge,
    because a fragment is a property of how a program is assembled and the
    bridge assembles nothing.
    """

    def setUp(self) -> None:
        super().setUp()
        self.bridge.responder = lambda request: fake_bridge.ok_envelope(
            request.get("command"),
            fake_bridge.status_result() if request.get("command") == "get_status"
            else {"count": 0, "via": "bridge"})

    def test_a_fragment_is_concatenated_on_the_generated_path(self) -> None:
        self.prefer(None)

        backend.send("list_presets.py", params={"refresh": False},
                     shared=["preset_files.py"])

        program = _program_of(self.addon.requests[0])
        self.assertIn("# --- shared: preset_files.py ---", program)
        self.assertIn("def preset_name_rejection(", program)

    def test_a_fragment_does_not_reach_the_bridge(self) -> None:
        self.prefer(backend.BACKEND_BRIDGE)

        backend.send("list_presets.py", params={"refresh": False},
                     shared=["preset_files.py"])

        self.assertEqual(self.addon.requests, [])
        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(request["command"], "list_presets")
        self.assertEqual(request["params"], {"refresh": False})
        # Not merely absent from `params`: nothing anywhere in the frame.
        self.assertNotIn("preset_files", json.dumps(request))
        self.assertNotIn("shared", request)

    def test_a_cached_fragment_goes_through_the_cache_on_the_generated_path(self) -> None:
        # The seam consults shared_cache rather than a tool importing it, which
        # is what lets a tool migrate without the tools left behind losing the
        # cache. The claim here is only that it was consulted: the cache's own
        # behaviour is tests/test_shared_cache.py's.
        self.prefer(None)

        backend.send("list_targets.py", params={"section": None},
                     cached_shared=["target_categories.py"])

        program = _program_of(self.addon.requests[0])
        self.assertIn("# --- shared loader ---", program)
        self.assertIn("# --- cached shared: target_categories.py@", program)

    def test_a_cached_fragment_does_not_reach_the_bridge(self) -> None:
        self.prefer(backend.BACKEND_BRIDGE)

        backend.send("list_targets.py", params={"section": None},
                     cached_shared=["target_categories.py"])

        self.assertEqual(self.addon.requests, [])
        frame = json.dumps(self.bridge.decoded_requests()[-1])
        self.assertNotIn("target_categories", frame)
        self.assertNotIn("cached shared", frame)

    def test_an_unmigrated_tool_keeps_the_cache_in_both_configurations(self) -> None:
        # `set_targets.py` is a stage-4 tool sharing `target_categories.py` with
        # the two that migrated here. Requirement 2 is that it did not lose the
        # session source cache by the seam taking it over.
        for preference in (None, backend.BACKEND_BRIDGE):
            with self.subTest(backend=preference):
                self.addon.requests.clear()
                self.bridge.requests.clear()
                self.prefer(preference)

                backend.send("set_targets.py", params={},
                             cached_shared=["target_categories.py"])

                self.assertEqual(len(self.addon.requests), 1)
                self.assertEqual(self.bridge.requests, [])
                self.assertIn("# --- cached shared: target_categories.py@",
                              _program_of(self.addon.requests[0]))

    def test_a_tool_passes_the_same_call_whichever_path_it_is_on(self) -> None:
        # The requirement stated as one assertion: identical arguments, and the
        # only difference is which server was spoken to.
        arguments = {"params": {"refresh": True}, "shared": ["preset_files.py"]}

        self.prefer(None)
        backend.send("list_presets.py", **arguments)
        self.prefer(backend.BACKEND_BRIDGE)
        backend.send("list_presets.py", **arguments)

        self.assertEqual(len(self.addon.requests), 1)
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"refresh": True})


class EnvelopeTests(BothBackendsTestCase):
    def test_a_generated_error_is_given_the_command_failed_slug(self) -> None:
        self.prefer(None)
        self.addon.response = {"status": "error", "message": "NameError on line 312"}

        response = backend.send("list_objects.py", params={"object_type": None})

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)
        self.assertEqual(response["message"], "NameError on line 312")

    def test_a_generated_success_is_returned_byte_for_byte(self) -> None:
        self.prefer(None)
        envelope = {"status": "ok", "result": {"count": 0, "via": "blender_mcp"},
                    "stdout": "", "stderr": ""}
        self.addon.response = dict(envelope)

        response = backend.send("list_objects.py", params={"object_type": None})

        self.assertEqual(response, envelope)

    def test_a_bridge_error_keeps_the_slug_the_bridge_chose(self) -> None:
        self.prefer(backend.BACKEND_BRIDGE)
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope("invalid_params", "Parameter 'object_type' ..."))

        response = backend.send("list_objects.py", params={"object_type": 7})

        self.assertEqual(response["error"], "invalid_params",
                         "the seam must not overwrite a slug the bridge chose")

    def test_the_two_paths_agree_about_status_result_and_message(self) -> None:
        # The spellings are what no existing caller or test had to change for,
        # and they are the only three keys a caller is promised on both.
        self.prefer(None)
        generated = backend.send("list_objects.py", params={"object_type": None})
        self.prefer(backend.BACKEND_BRIDGE)
        bridged = backend.send("list_objects.py", params={"object_type": None})

        self.assertEqual(generated["status"], bridged["status"])
        self.assertEqual(set(generated["result"]), set(bridged["result"]))

    def test_nothing_is_synthesised_onto_a_generated_answer(self) -> None:
        # protocol_version is a fact about the bridge's protocol. Inventing one
        # for a generated answer would make the field a lie on half the calls.
        self.prefer(None)

        response = backend.send("list_objects.py", params={"object_type": None})

        self.assertNotIn("protocol_version", response)
        self.assertNotIn("command", response)


class EnvelopeMappingUnitTests(unittest.TestCase):
    """``as_common_envelope`` on its own, including what it must not touch."""

    def test_a_non_dict_is_returned_unchanged(self) -> None:
        self.assertEqual(backend.as_common_envelope("not an envelope"), "not an envelope")

    def test_a_success_is_returned_unchanged(self) -> None:
        envelope = {"status": "ok", "result": 1}
        self.assertIs(backend.as_common_envelope(envelope), envelope)

    def test_an_existing_slug_is_left_alone(self) -> None:
        envelope = {"status": "error", "error": "mpfb_unavailable", "message": "no MPFB"}
        self.assertIs(backend.as_common_envelope(envelope), envelope)

    def test_the_original_dict_is_not_modified(self) -> None:
        envelope = {"status": "error", "message": "boom"}

        mapped = backend.as_common_envelope(envelope)

        self.assertNotIn("error", envelope)
        self.assertEqual(mapped["error"], backend.ERROR_COMMAND_FAILED)

    def test_everything_else_in_the_envelope_survives(self) -> None:
        envelope = {"status": "error", "message": "boom", "stdout": "printed",
                    "mpfb_mcp_record": {"program": "/tmp/0001-list_objects.py"}}

        mapped = backend.as_common_envelope(envelope)

        self.assertEqual(mapped["stdout"], "printed")
        self.assertEqual(mapped["mpfb_mcp_record"], {"program": "/tmp/0001-list_objects.py"})
        self.assertEqual(list(mapped)[:2], ["status", "error"],
                         "the slug should sit where a reader looks for it")


class ConnectionFailureTests(BothBackendsTestCase):
    def test_a_missing_bridge_raises_the_same_exception_type_as_a_missing_addon(self) -> None:
        # What stage 4 inherits: mpfb_list_urls catches ConnectionError and
        # answers anyway, and it must keep working when it crosses the bridge.
        self.prefer(backend.BACKEND_BRIDGE)
        self.set_env_var(bridge_connection.BRIDGE_PORT_VARIABLE, str(_free_port()))

        with self.assertRaises(ConnectionError):
            backend.send("list_objects.py", params={"object_type": None})

    def test_a_missing_addon_raises_connection_error_on_the_generated_path(self) -> None:
        self.prefer(None)
        self.set_env_var("BLENDER_MCP_PORT", str(_free_port()))

        with self.assertRaises(ConnectionError):
            backend.send("list_objects.py", params={"object_type": None})


def _free_port() -> int:
    import socket  # pylint: disable=import-outside-toplevel

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


if __name__ == "__main__":
    unittest.main()
