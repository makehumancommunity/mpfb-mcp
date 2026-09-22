# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for mpfbmcp.backend: what a tool's call becomes, and what comes back.

The seam is the one module that knows a call leaves this process, so this is
the one module that may know it too. **What is under test is passage, not
behaviour**: that the command name and the parameters a tool handed over are
what arrives on the wire unreshaped, that the envelope is returned exactly as
the bridge wrote it, and that an unreachable bridge is an exception rather than
an envelope.

The assertions are made by watching *what arrived at a fake server* rather than
by patching ``bridge_connection.send_command`` and checking which mock was
called. The difference matters: a mock asserts that this module called what this
module was expected to call, while a fake asserts that bytes arrived somewhere,
which is the claim a tool's caller actually depends on.

Two of these classes were larger until FR 033. Routing, the ``MIGRATED_COMMANDS``
table, the fragment arguments and the envelope mapping were all about a second
transport, and go with it; what is left is the seam doing the one thing it now
does. The envelope tests stay, and their claim narrows usefully: nothing is
synthesised, rewritten or dropped on the way through, so a caller reads exactly
what the add-on wrote.

Run with::

    python -m unittest tests.test_backend -v
"""

__all__ = ()

import unittest

from mpfbmcp import backend, bridge_connection
from tests import fake_bridge


class SeamTestCase(fake_bridge.BridgeTestCase):
    """A fake bridge answering the two commands these tests send."""

    def setUp(self) -> None:
        super().setUp()
        self.set_env_var(backend.BACKEND_VARIABLE, None)
        backend._warned_about_backend_variable = False  # noqa: SLF001
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope(
                "list_objects", {"count": 0, "via": "bridge"}),
        })


class PassageTests(SeamTestCase):
    def test_a_call_reaches_the_bridge_under_the_command_it_named(self) -> None:
        response = backend.send("list_objects", params={"object_type": None})

        self.assertEqual(response["result"]["via"], "bridge")
        # get_status first: the handshake probe, one per address per process.
        self.assertEqual(self.bridge.commands(), ["get_status", "list_objects"])

    def test_the_params_arrive_unreshaped(self) -> None:
        # Both sides receive the tool's already-validated arguments and neither
        # reshapes them. There is deliberately no parameter mapping in the seam,
        # and this is what would fail if one were added.
        params = {"object_type": "Basemesh"}

        backend.send("list_objects", params=params)

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], params)

    def test_no_params_becomes_an_empty_object_rather_than_null(self) -> None:
        # The add-on's validation reads `params` as a mapping. Sending null
        # would make every argument-free tool a malformed request.
        backend.send("list_objects")

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {})

    def test_nothing_of_the_seam_appears_in_the_frame(self) -> None:
        # The request is the command, its parameters and the protocol version.
        # Anything else here would be the seam leaking into the wire.
        backend.send("list_objects", params={"object_type": None})

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(set(request), {"command", "params", "protocol_version"})


class EnvelopeTests(SeamTestCase):
    def test_a_success_is_returned_exactly_as_the_bridge_wrote_it(self) -> None:
        response = backend.send("list_objects", params={"object_type": None})

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"], {"count": 0, "via": "bridge"})
        self.assertIn("protocol_version", response)

    def test_an_error_keeps_the_slug_the_bridge_chose(self) -> None:
        # Every error envelope is built by one function in the add-on
        # (command_server._error), which always writes `error`. There is
        # nothing for the seam to fill in, and this is what would fail if it
        # started filling something in anyway.
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope("invalid_params", "Parameter 'object_type' ..."))

        response = backend.send("list_objects", params={"object_type": 7})

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "invalid_params")
        self.assertIn("object_type", response["message"])


class RetiredVariableTests(SeamTestCase):
    """``MPFB_MCP_BACKEND`` is read for exactly one purpose: saying it is not.

    A value left behind in somebody's MCP client configuration would otherwise
    be obeyed by nothing and reported by nothing, which is the same argument
    that made an *unrecognised* value an error rather than a fallback while
    there were still two backends to choose between.
    """

    def test_an_unset_variable_says_nothing(self) -> None:
        with self.assertNoLogs("mpfbmcp.backend"):
            backend.send("list_objects", params={"object_type": None})

    def test_a_set_variable_is_reported_on_this_package_s_logger(self) -> None:
        self.set_env_var(backend.BACKEND_VARIABLE, "blender_mcp")

        with self.assertLogs("mpfbmcp.backend", level="WARNING") as logged:
            backend.send("list_objects", params={"object_type": None})

        self.assertIn("blender_mcp", logged.output[0])
        self.assertIn(backend.BACKEND_VARIABLE, logged.output[0])

    def test_the_call_is_performed_anyway(self) -> None:
        # A stale variable is worth a line, never a refusal: there is one
        # transport, so there is nothing a wrong value could route to.
        self.set_env_var(backend.BACKEND_VARIABLE, "something else entirely")

        with self.assertLogs("mpfbmcp.backend", level="WARNING"):
            response = backend.send("list_objects", params={"object_type": None})

        self.assertEqual(response["status"], "ok")

    def test_it_is_said_once_rather_than_once_per_call(self) -> None:
        # A stale variable does not become less stale during a session, and a
        # line per call would be its own kind of damage.
        self.set_env_var(backend.BACKEND_VARIABLE, "blender_mcp")

        with self.assertLogs("mpfbmcp.backend", level="WARNING") as logged:
            backend.send("list_objects", params={"object_type": None})
            backend.send("list_objects", params={"object_type": None})

        self.assertEqual(len(logged.output), 1)


class ConnectionFailureTests(SeamTestCase):
    def test_an_unreachable_bridge_raises_rather_than_answering(self) -> None:
        # mpfb_list_urls catches ConnectionError and answers anyway, which is
        # the one tool that depends on this being an exception and not an
        # envelope.
        self.set_env_var(bridge_connection.BRIDGE_PORT_VARIABLE, str(_free_port()))

        with self.assertRaises(ConnectionError):
            backend.send("list_objects", params={"object_type": None})


def _free_port() -> int:
    import socket  # pylint: disable=import-outside-toplevel

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


if __name__ == "__main__":
    unittest.main()
