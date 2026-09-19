# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for mpfbmcp.bridge_connection: the bridge's wire protocol and handshake.

A local TCP server standing in for the add-on (``tests/fake_bridge.py``), so
the framing, the error paths and the version handshake are exercised without a
Blender anywhere. The shape mirrors ``tests/test_connection.py`` deliberately:
the two clients are siblings and the failures they have to survive are the
same ones.

Two groups here are not merely the old tests with a new address on them.

**The handshake** has no counterpart on the generated path. What is asserted is
not only that a mismatch is refused, but that the refusal names *which end to
upgrade*, which is the whole reason the probe reads
``min_supported_protocol_version`` rather than comparing two numbers and
shrugging. And that the probe is one per address per process - a probe per call
would double the round trips of the cheapest tool in the package, which is
precisely the tool that has been migrated.

**A ``ConnectionError`` for the same situations ``connection.py`` raises one
for** is asserted here so that stage 4 inherits it rather than discovers it:
``mpfb_list_urls`` is the one tool that catches a connection failure and answers
anyway, and it must keep working when it moves to the bridge.

Run with::

    python -m unittest tests.test_bridge_connection -v
"""

__all__ = ()

import json
import os
import re
import socket
import unittest
from unittest import mock

from mpfbmcp import bridge_connection
from tests import fake_bridge

_ADDON_SOURCE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bridge", "mpfb_bridge", "command_server.py")


def _free_port() -> int:
    """A port that was valid a moment ago and has nothing listening on it."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class SendCommandTests(fake_bridge.BridgeTestCase):
    def test_round_trip_ok_response(self) -> None:
        self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })

        response = bridge_connection.send_command("list_objects", {"object_type": None})

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"], {"count": 0})
        self.assertEqual(response["command"], "list_objects")

    def test_the_request_carries_the_command_its_params_and_a_version(self) -> None:
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })

        bridge_connection.send_command("list_objects", {"object_type": "Basemesh"})

        request = server.decoded_requests()[-1]
        self.assertEqual(request, {
            "command": "list_objects",
            "params": {"object_type": "Basemesh"},
            "protocol_version": bridge_connection.PROTOCOL_VERSION,
        })

    def test_every_request_declares_the_protocol_version_including_the_probe(self) -> None:
        # Declaring it is free and earns the bridge's own protocol_mismatch
        # refusal for nothing, which is what catches a stale memo.
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })

        bridge_connection.send_command("list_objects")

        for request in server.decoded_requests():
            self.assertEqual(request["protocol_version"], bridge_connection.PROTOCOL_VERSION)

    def test_omitted_params_are_sent_as_an_empty_object(self) -> None:
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_commands": fake_bridge.ok_envelope("list_commands", {"commands": []}),
        })

        bridge_connection.send_command("list_commands")

        self.assertEqual(server.decoded_requests()[-1]["params"], {})

    def test_an_error_envelope_comes_back_with_its_slug_intact(self) -> None:
        self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.error_envelope(
                "mpfb_unavailable", "MPFB is not usable in this Blender.", command="list_objects"),
        })

        response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
        self.assertIn("MPFB", response["message"])

    def test_an_answer_split_across_recv_calls_is_reassembled(self) -> None:
        # One byte at a time: where the split falls is the framing's whole job.
        self.run_fake_bridge(
            responder=lambda request: fake_bridge.ok_envelope(
                str(request.get("command")),
                fake_bridge.status_result() if request.get("command") == "get_status"
                else {"objects": [{"name": "Human", "object_type": "Basemesh"}]}),
            chunk_size=1)

        response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["result"]["objects"][0]["name"], "Human")

    def test_bytes_after_the_delimiter_are_ignored(self) -> None:
        # One request per connection, so anything past the NUL is not this
        # client's business - and must not become a parse failure.
        frame = (json.dumps(fake_bridge.ok_envelope("list_objects", {"count": 0}))
                 + "\0" + "{\"trailing\": ").encode("utf-8")
        self.run_fake_bridge(responder=lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status" else frame))

        response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["result"], {"count": 0})

    def test_a_non_ascii_answer_survives_a_split_inside_a_character(self) -> None:
        # NUL cannot occur inside a UTF-8 multi-byte sequence, which is why the
        # delimiter search is a byte search - but the client is what has to not
        # decode before the boundary.
        self.run_fake_bridge(
            responder=lambda request: fake_bridge.ok_envelope(
                str(request.get("command")),
                fake_bridge.status_result() if request.get("command") == "get_status"
                else {"name": "Hüman — café"}),
            chunk_size=1)

        response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["result"]["name"], "Hüman — café")


class AddressTests(fake_bridge.BridgeTestCase):
    def test_the_defaults_are_the_bridges_own_port(self) -> None:
        self.set_env_var(bridge_connection.BRIDGE_HOST_VARIABLE, None)
        self.set_env_var(bridge_connection.BRIDGE_PORT_VARIABLE, None)

        self.assertEqual(bridge_connection.get_connection_params(), ("127.0.0.1", 9877))

    def test_the_environment_overrides_both(self) -> None:
        self.point_env_at_bridge("192.0.2.4", 9999)

        self.assertEqual(bridge_connection.get_connection_params(), ("192.0.2.4", 9999))


class ConnectionFailureTests(fake_bridge.BridgeTestCase):
    """The commonest failure this system has, and the message is the diagnosis."""

    def test_a_refused_connection_names_the_bridge_and_the_preferences_panel(self) -> None:
        port = _free_port()
        self.point_env_at_bridge("127.0.0.1", port)

        with self.assertRaises(ConnectionError) as raised:
            bridge_connection.send_command("list_objects")

        message = str(raised.exception)
        self.assertIn("MPFB Bridge", message)
        self.assertIn(str(port), message)
        self.assertIn("preferences", message)

    def test_a_closed_connection_with_no_reply_raises_connection_error(self) -> None:
        self.run_fake_bridge(responder=lambda request: None)

        with self.assertRaises(ConnectionError):
            bridge_connection.send_command("list_objects")

    def test_an_unparseable_answer_raises_connection_error(self) -> None:
        self.run_fake_bridge(responder=lambda request: b"not json at all\0")

        with self.assertRaises(ConnectionError):
            bridge_connection.send_command("list_objects")

    def test_a_connection_failure_drops_the_memo_so_the_next_call_probes(self) -> None:
        # The memo records what this process learned, not what Blender is, and
        # Blender restarting invalidates it without telling anyone. One address
        # throughout, because the memo is keyed on the address and a test that
        # moved to a second one would be asserting nothing.
        answering = {"silent": False}

        def responder(request: dict[str, object]) -> object:
            if answering["silent"]:
                return None
            command = str(request.get("command"))
            result = fake_bridge.status_result() if command == "get_status" else {"count": 0}
            return fake_bridge.ok_envelope(command, result)

        server = self.run_fake_bridge(responder=responder)
        bridge_connection.send_command("list_objects")

        answering["silent"] = True
        with self.assertRaises(ConnectionError):
            bridge_connection.send_command("list_objects")

        answering["silent"] = False
        server.requests.clear()
        bridge_connection.send_command("list_objects")

        self.assertEqual(server.commands(), ["get_status", "list_objects"],
                         "the address should be probed again after a failure at it")


class HandshakeTests(fake_bridge.BridgeTestCase):
    def test_the_first_call_probes_and_the_second_does_not(self) -> None:
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })

        bridge_connection.send_command("list_objects")
        bridge_connection.send_command("list_objects")

        self.assertEqual(server.commands(), ["get_status", "list_objects", "list_objects"])

    def test_a_second_address_is_probed_on_its_own(self) -> None:
        # The memo is keyed on (host, port): a developer pointing at a second
        # Blender must not inherit the first one's verdict.
        first = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })
        bridge_connection.send_command("list_objects")

        second = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 1}),
        })
        bridge_connection.send_command("list_objects")

        self.assertEqual(first.commands(), ["get_status", "list_objects"])
        self.assertEqual(second.commands(), ["get_status", "list_objects"])

    def test_a_bridge_from_the_future_is_refused_and_says_to_upgrade_mpfb_mcp(self) -> None:
        newer = bridge_connection.PROTOCOL_VERSION + 2
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope(
                "get_status",
                fake_bridge.status_result(protocol_version=newer,
                                          min_supported=newer - 1)),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })

        response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "protocol_mismatch")
        self.assertIn(str(bridge_connection.PROTOCOL_VERSION), response["message"])
        self.assertIn(str(newer - 1), response["message"])
        self.assertIn("Upgrade mpfb-mcp", response["message"])
        self.assertEqual(server.commands(), ["get_status"],
                         "a call that cannot be understood must not reach Blender")

    def test_a_bridge_too_old_is_refused_and_says_to_upgrade_the_add_on(self) -> None:
        self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope(
                "get_status", fake_bridge.status_result(protocol_version=1, min_supported=1)),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })

        with mock.patch.object(bridge_connection, "PROTOCOL_VERSION", 5):
            response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["error"], "protocol_mismatch")
        self.assertIn("5", response["message"])
        self.assertIn("Upgrade the MPFB Bridge add-on", response["message"])

    def test_a_refused_probe_is_read_for_the_versions_it_carries(self) -> None:
        # The same disagreement seen from the other side: the bridge refused the
        # probe's own declared version, and put both numbers in the refusal.
        newer = bridge_connection.PROTOCOL_VERSION + 3
        self.run_answering_bridge({
            "get_status": fake_bridge.error_envelope(
                "protocol_mismatch", "This bridge speaks a later protocol.",
                min_supported_protocol_version=newer - 1,
                requested_protocol_version=bridge_connection.PROTOCOL_VERSION),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
        })

        response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["error"], "protocol_mismatch")
        self.assertIn("Upgrade mpfb-mcp", response["message"])
        self.assertEqual(response["min_supported_protocol_version"], newer - 1)

    def test_every_call_fails_the_same_way_while_the_versions_disagree(self) -> None:
        newer = bridge_connection.PROTOCOL_VERSION + 2
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope(
                "get_status", fake_bridge.status_result(protocol_version=newer,
                                                        min_supported=newer)),
        })

        first = bridge_connection.send_command("list_objects")
        second = bridge_connection.send_command("list_commands")

        self.assertEqual(first, second)
        self.assertEqual(server.commands(), ["get_status"],
                         "the refusal is memoised too: one probe, not one per call")

    def test_a_bridge_that_reports_no_versions_is_talked_to_anyway(self) -> None:
        # A handshake exists to catch a mismatch, not to invent one. Something
        # that answers and claims no version is served, exactly as the bridge
        # serves a request that declares none.
        server = self.run_answering_bridge({
            "get_status": {"status": "ok", "result": {"state": "ok"}},
            "list_objects": {"status": "ok", "result": {"count": 0}},
        })

        response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(server.commands(), ["get_status", "list_objects"])


class ProtocolVersionDriftTests(unittest.TestCase):
    """The one number this client and the add-on must agree about by hand."""

    @unittest.skipUnless(os.path.isfile(_ADDON_SOURCE),
                         "the bridge add-on's source is not beside this package")
    def test_the_client_speaks_the_version_the_add_on_serves(self) -> None:
        # Read rather than imported: the add-on is a Blender extension whose
        # package imports bpy, and this suite must run on a machine with no
        # Blender. Same discipline as tests/test_reference_drift.py.
        with open(_ADDON_SOURCE, encoding="utf-8") as stream:
            source = stream.read()
        found = re.search(r"^PROTOCOL_VERSION = (\d+)$", source, re.MULTILINE)

        self.assertIsNotNone(found, "could not find PROTOCOL_VERSION in {}".format(_ADDON_SOURCE))
        self.assertEqual(
            int(found.group(1)), bridge_connection.PROTOCOL_VERSION,
            "bridge_connection.PROTOCOL_VERSION and the add-on's have drifted apart; "
            "they are duplicated deliberately and kept in step by hand")


if __name__ == "__main__":
    unittest.main()
