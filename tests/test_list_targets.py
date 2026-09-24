# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_list_targets tool: argument validation, and what crosses the
socket.

Two layers (see ``tests/test_list_objects.py``, the template): the wrapper with
``send_command`` mocked below the seam, and the bridge path against
``tests/fake_bridge.py``.

This is the tool whose migration mattered most to measure: it carried 26 KB of
shared fragment source on a cold call over the retired transport, which is the
number the session source cache existed because of, and over the bridge it is a
single JSON request. What it *answers* - the two-source scan that merges the
bundled index with the user's own target directories, the ``.target.gz`` MPFB's
own scan misses, the name long enough that its shape key name is encoded - is
asked of a real MPFB in ``bridge/test/tests/ccc_reading/list_targets_test.py``.

Run with::

    python -m unittest tests.test_list_targets -v
"""

__all__ = ()

import os
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from tests import fake_bridge

from mpfbmcp import bridge_connection
from mpfbmcp.tools import list_targets




# A trimmed target.json with the shape MPFB's really has. "arms" is the section
# whose name a user directory also uses, "measure" is the real index's empty
# section, and the left/right category carries the opposites table the modeling
# sliders are built from.
_TARGET_JSON = {
    "arms": {
        "include_per_default": True,
        "label": "Arms",
        "unsorted": False,
        "categories": [
            {
                "has_left_and_right": True,
                "label": "lowerarm-scale-depth-decr-incr",
                "name": "lowerarm-scale-depth-decr-incr",
                "opposites": {
                    "negative-left": "l-lowerarm-scale-depth-decr",
                    "negative-right": "r-lowerarm-scale-depth-decr",
                    "negative-unsided": "",
                    "positive-left": "l-lowerarm-scale-depth-incr",
                    "positive-right": "r-lowerarm-scale-depth-incr",
                    "positive-unsided": "",
                },
                "targets": [
                    "l-lowerarm-scale-depth-decr", "r-lowerarm-scale-depth-incr",
                    "r-lowerarm-scale-depth-decr", "l-lowerarm-scale-depth-incr",
                ],
            },
            {
                "has_left_and_right": False,
                "label": "upperarm-fat-decr-incr",
                "name": "upperarm-fat-decr-incr",
                "opposites": {
                    "negative-left": "", "negative-right": "",
                    "negative-unsided": "upperarm-fat-decr",
                    "positive-left": "", "positive-right": "",
                    "positive-unsided": "upperarm-fat-incr",
                },
                "targets": ["upperarm-fat-decr", "upperarm-fat-incr"],
            },
        ],
    },
    "nose": {
        "include_per_default": True,
        "label": "Nose",
        "unsorted": False,
        "categories": [
            {
                "has_left_and_right": False,
                "label": "nose-scale-depth-decr-incr",
                "name": "nose-scale-depth-decr-incr",
                "opposites": {
                    "negative-left": "", "negative-right": "",
                    "negative-unsided": "nose-scale-depth-decr",
                    "positive-left": "", "positive-right": "",
                    "positive-unsided": "nose-scale-depth-incr",
                },
                "targets": ["nose-scale-depth-decr", "nose-scale-depth-incr"],
            },
        ],
    },
    # The real index's "measure": a section that exists, has no categories, and
    # has no directory on disk either.
    "measure": {
        "include_per_default": False,
        "label": "measure",
        "unsorted": False,
        "categories": [],
    },
}

# Over 60 characters after the extension is stripped, and containing words from
# MPFB's encoding table, so the encoded name provably differs from the filename.
_LONG_NAME = "young-female-average-caucasian-uncommon-proportions-weight-height-experiment"


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    list_targets.register(mcp)
    return mcp._tool_manager._tools["mpfb_list_targets"].fn  # pylint: disable=protected-access


def _touch(path, content="dummy target data"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class ArgumentValidationTests(unittest.TestCase):
    """Shape checked here, vocabulary deliberately not."""

    def setUp(self):
        self.tool = _tool_callable()

    def test_default_call_sends_the_documented_defaults(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool()
        command, params = send_command.call_args[0]
        self.assertEqual(command, "list_targets")
        self.assertEqual(params, {
            "section": None, "name_contains": None, "limit": 200, "offset": 0})

    def test_arguments_are_carried_across_unchanged(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(section="arms", name_contains="Nose", limit=5, offset=10)
        self.assertEqual(send_command.call_args[0][1], {
            "section": "arms", "name_contains": "Nose", "limit": 5, "offset": 10})

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self):
        # The envelope is this package's: `status` and `message` are unchanged,
        # and `error` is what a caller branches on whichever transport answered.
        # Since FR 031 this tool's fragments go through the seam rather than
        # around it, so the mapping applies to a cached-fragment call too.
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {
                "status": "error", "error": "mpfb_unavailable",
                "message": "no MPFB"}
            response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "no MPFB")
        self.assertEqual(response["error"], "mpfb_unavailable")

    def test_non_string_or_empty_text_arguments_are_rejected_locally(self):
        # An explicitly empty value is never quietly read as an omitted one: the
        # two arise from different mistakes.
        for argument in ("section", "name_contains"):
            for bad in (1, True, [], object(), "", "   ", "\t"):
                with self.subTest(argument=argument, value=bad):
                    with mock.patch.object(bridge_connection, "send_command") as send_command:
                        with self.assertRaises(ValueError):
                            self.tool(**{argument: bad})
                    send_command.assert_not_called()

    def test_bad_limit_and_offset_are_rejected_locally(self):
        # bool is a subclass of int, so limit=True would otherwise page one
        # entry at a time rather than fail.
        for bad in (True, False, -1, "10", 1.5, None):
            with self.subTest(limit=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(limit=bad)
                send_command.assert_not_called()
            with self.subTest(offset=bad):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(offset=bad)
                send_command.assert_not_called()

    def test_limit_above_the_ceiling_is_rejected_locally(self):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            with self.assertRaises(ValueError):
                self.tool(limit=list_targets.MAX_LIMIT + 1)
        send_command.assert_not_called()
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(limit=list_targets.MAX_LIMIT)
        send_command.assert_called_once()

    def test_an_unknown_section_is_not_rejected_locally(self):
        # Half the sections are synthesized from the user's own directories, so
        # a vocabulary kept here could not be right even in principle. The
        # far side answers it with section_recognized.
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(section="no-such-section")
        send_command.assert_called_once()


class ListTargetsOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the two-source merge, the over-60-character
    encoding, the gzipped target MPFB's own scan misses - is checked against a
    real MPFB in ``bridge/test/tests/ccc_reading/list_targets_test.py``.
    """

    def setUp(self):
        super().setUp()
        self.tool = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_targets": fake_bridge.ok_envelope("list_targets", {"count": 0}),
        })

    def test_the_tool_sends_the_list_targets_command(self):
        self.tool()

        self.assertEqual(self.bridge.commands()[-1], "list_targets")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {
            "section": None, "name_contains": None, "limit": 200, "offset": 0})

    def test_the_request_is_exactly_the_parameters(self):
        # The tool that used to carry the most source of any in the package.
        # target_categories.py is a module the command imports, so the request
        # is the four arguments and the protocol version, and nothing else.
        self.tool(section="arms", name_contains="Nose", limit=5, offset=10)

        request = self.bridge.decoded_requests()[-1]
        self.assertEqual(set(request), {"command", "params", "protocol_version"})
        self.assertEqual(request["params"], {
            "section": "arms", "name_contains": "Nose", "limit": 5, "offset": 10})
        self.assertNotIn("target_categories", str(request))

    def test_local_validation_runs_before_a_transport_is_chosen(self):
        for arguments in ({"limit": True}, {"limit": -1}, {"limit": 1001},
                          {"offset": True}, {"section": "  "}, {"name_contains": ""}):
            with self.subTest(**arguments):
                with self.assertRaises(ValueError):
                    self.tool(**arguments)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self):
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="list_targets", state="absent"))

        response = self.tool()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
