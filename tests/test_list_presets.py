# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_list_presets``, in two layers (see ``tests/test_list_objects.py``, the
template).

1. **The wrapper**, with ``send_command`` mocked below the seam: what is
   validated before anything is sent, and what goes on the wire.
2. **The bridge path**, against ``tests/fake_bridge.py``.

The three fields worth having here - ``size_bytes``, ``modified`` and
``exists`` - come from ``os.stat`` and from nowhere else, so what this tool
answers can only be checked against a real directory.
``bridge/test/tests/jjj_list_presets_test.py`` builds one and points MPFB's own
``LocationService`` at it, which is where the claims about what MPFB's list
holds are made.

Run with::

    python -m unittest tests.test_list_presets -v
"""

from __future__ import annotations

__all__ = ()

import unittest
from unittest import mock

from mpfbmcp.tools import list_presets

from tests import fake_bridge




class ListPresetsToolTests(unittest.TestCase):
    """The wrapper, with ``send_command`` mocked: what is validated before the socket."""

    def setUp(self) -> None:
        self.sent: list = []

        class Recorder:
            def tool(self, **_kwargs):
                def decorate(function):
                    self.function = function
                    return function
                return decorate

        self.recorder = Recorder()
        list_presets.register(self.recorder)
        self.call = self.recorder.function

    def _run(self, **arguments):
        """The parameters that reached the wire."""
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            self.assertEqual(send.call_args[0][0], "list_presets")
            return send.call_args[0][1]

    def test_the_default_call_does_not_refresh(self) -> None:
        self.assertIs(self._run()["refresh"], False)

    def test_refresh_reaches_the_command(self) -> None:
        self.assertIs(self._run(refresh=True)["refresh"], True)

    def test_a_truthy_non_bool_refresh_is_refused_before_the_socket(self) -> None:
        # "false" is a true value, and would rescan the disk - which is a write
        # to MPFB's own cache, read by MPFB's own panels.
        for value in ("false", "true", 1, 0, None):
            with self.subTest(refresh=value):
                with self.assertRaises(ValueError):
                    self._run(refresh=value)


class ListPresetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - what MPFB's cached list holds, which files
    its own match accepts, what a rescan gains - is checked against a real MPFB
    in ``bridge/test/tests/jjj_list_presets_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()

        class Recorder:
            def tool(self, **_kwargs):
                def decorate(function):
                    self.function = function
                    return function
                return decorate

        recorder = Recorder()
        list_presets.register(recorder)
        self.call = recorder.function
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_presets": fake_bridge.ok_envelope("list_presets", {"count": 0}),
        })

    def test_the_tool_sends_the_list_presets_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "list_presets")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"refresh": False})

    def test_the_shared_fragment_does_not_reach_the_bridge(self) -> None:
        # The first tool to carry a fragment across the seam. A fragment is a
        # property of how a *program* is assembled; the bridge dispatches a
        # name, and what the fragment modelled is a module it imports. So the
        # request is exactly the parameters, with nothing named `shared` in it.
        self.call(refresh=True)

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(request["params"], {"refresh": True})
        self.assertNotIn("shared", request)
        self.assertNotIn("preset_files", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        # "false" is a true value and would rescan the disk, which is a write to
        # MPFB's own cache. The refusal is the tool's, not the transport's.
        for value in ("false", "true", 1, 0, None):
            with self.subTest(refresh=value):
                with self.assertRaises(ValueError):
                    self.call(refresh=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="list_presets", state="absent"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
