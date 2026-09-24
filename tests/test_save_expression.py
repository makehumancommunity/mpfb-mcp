# SPDX-License-Identifier: GPL-3.0-or-later

"""``mpfb_save_expression``: the name rule on this side, and the write on the other.

Two layers (see ``tests/test_list_objects.py``, the template), and as in
``tests/test_save_preset.py`` the first carries the weight: ``name`` becomes a
**path**, so the whitelist is exercised exhaustively *before* anything is sent,
over the same table of names the preset tool is held to. The drift check between
the two copies of the rule is in ``tests/test_save_preset.py``, which runs every
name as a preset and as an expression.

What the command writes - the file after rounding and zero-dropping, the
overwrite refusal carrying size and age, the shadowed-name refusal, the
empty-face refusal, and that the character is untouched - is checked against a
real MPFB in ``bridge/test/tests/ddd_mutating/save_expression_test.py``, with
MPFB's user data redirected so a failing test cannot leave a file in the
developer's own library.

Run with::

    python -m unittest tests.test_save_expression -v
"""

from __future__ import annotations

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import save_expression

from tests import fake_bridge
from tests.test_save_preset import ACCEPTED_NAMES
from tests.test_save_preset import REFUSED_NAMES


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    save_expression.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_save_expression"].fn


class SaveExpressionValidationTests(unittest.TestCase):
    """The name rule and the metadata shapes, before anything is sent."""

    def setUp(self) -> None:
        self.call = _tool_callable()

    def _run(self, **arguments):
        """The parameters that reached the wire for one accepted call."""
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            send.return_value = {"status": "ok", "result": {}}
            self.call(**arguments)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args[0][0], "save_expression")
            return send.call_args[0][1]

    def _refused(self, **arguments):
        with mock.patch("mpfbmcp.bridge_connection.send_command") as send:
            with self.assertRaises(ValueError) as raised:
                self.call(**arguments)
            # The point of the whole layer: nothing crossed the socket.
            self.assertEqual(send.call_count, 0)
        return str(raised.exception)

    def test_every_dangerous_or_malformed_name_is_refused_before_the_socket(self) -> None:
        for name, why in REFUSED_NAMES:
            with self.subTest(name=name, why=why):
                self._refused(expression_name=name)

    def test_every_legal_name_is_accepted_and_sent_as_given(self) -> None:
        for name in ACCEPTED_NAMES + ("smile", "angry-shout", "Wink"):
            with self.subTest(name=name):
                self.assertEqual(self._run(expression_name=name)["expression_name"], name)

    def test_a_refusal_speaks_of_an_expression_and_says_where_files_go(self) -> None:
        message = self._refused(expression_name="../escape")
        self.assertIn("expression name", message)
        self.assertIn("<name>.json", message)
        self.assertIn("mpfb_list_expressions", message)

    def test_a_name_is_not_trimmed_or_normalised(self) -> None:
        # MPFB's composer promises lowercasing and dashes and does neither; the
        # name is saved as given, and a trailing space is refused, not repaired.
        self._refused(expression_name="smile ")
        self.assertEqual(self._run(expression_name="Big_Smile")["expression_name"], "Big_Smile")

    def test_the_default_call(self) -> None:
        self.assertEqual(self._run(expression_name="smile"), {
            "expression_name": "smile", "name": None, "overwrite": False,
            "description": "", "tags": [], "author": "", "copyright": "",
            "license": "CC0", "homepage": ""})

    def test_overwrite_must_be_a_real_bool(self) -> None:
        for value in ("false", "true", 1, 0, None):
            with self.subTest(overwrite=value):
                self._refused(expression_name="smile", overwrite=value)

    def test_the_subject_is_optional_and_shape_checked(self) -> None:
        self.assertEqual(self._run(expression_name="smile", name="Human")["name"], "Human")
        self._refused(expression_name="smile", name="")
        self._refused(expression_name="smile", name=3)

    def test_each_text_argument_must_be_a_string(self) -> None:
        for argument in ("description", "author", "copyright", "license", "homepage"):
            for bad in (None, 3, True, ["x"]):
                with self.subTest(argument=argument, value=bad):
                    self._refused(expression_name="smile", **{argument: bad})

    def test_tags_must_be_a_list_of_strings(self) -> None:
        # A comma-separated string is refused rather than split: MPFB's
        # save_expression would split one itself, and two splitters is two
        # answers to what "a, b" means.
        for bad in ("happy, subtle", ["happy", 3], [None], {"happy": True}, 3):
            with self.subTest(tags=bad):
                self._refused(expression_name="smile", tags=bad)
        self.assertEqual(self._run(expression_name="smile", tags=["happy", "subtle"])["tags"],
                         ["happy", "subtle"])

    def test_too_many_tags_are_refused(self) -> None:
        self._refused(expression_name="smile", tags=["t"] * (save_expression.MAX_TAGS + 1))


class SaveExpressionOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What reaches the wire, and nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.call = _tool_callable()
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "save_expression": fake_bridge.ok_envelope(
                "save_expression", {"found": True, "saved": True, "performed": True}),
        })

    def test_the_tool_sends_the_save_expression_command(self) -> None:
        self.call(expression_name="smile", license="CC-BY-4.0")

        self.assertEqual(self.bridge.commands()[-1], "save_expression")
        params = self.bridge.decoded_requests()[-1]["params"]
        self.assertEqual(params["expression_name"], "smile")
        self.assertEqual(params["license"], "CC-BY-4.0")

    def test_a_name_that_could_become_a_path_reaches_no_backend(self) -> None:
        for name in ("../escape", "with space", "", "a/b", ".hidden"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.call(expression_name=name)

        self.assertEqual(self.bridge.requests, [],
                         "a name that could become a path must not reach any backend")
