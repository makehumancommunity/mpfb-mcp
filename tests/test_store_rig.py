# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_store_rig tool: the name rule on both sides, and what crosses the socket.

Two layers (see ``tests/test_list_objects.py``, the template), and the name rule run on both
sides of the socket over one table, executing the bridge's ``shared/artifact_names.py`` as
``tests/test_save_preset.py`` does. The rule is MPFB's own, ``^[a-zA-Z0-9_]+$``, since
``AssetService.get_custom_rigs()`` skips a rig file whose name fails it. **No bone or rig
vocabulary is checked here.** Every refusal about identification, the staged write and what the
round trip loses are ``bridge/test/tests/ddd_mutating/store_rig_test.py``'s and
``bridge/test/tests/eee_composite/rig_roundtrip_test.py``'s.

Run with::

    python -m unittest tests.test_store_rig -v
"""

__all__ = ()

import pathlib
import re
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import artifact_names
from mpfbmcp import bridge_connection
from mpfbmcp.tools import store_rig

from tests import fake_bridge

_BRIDGE = pathlib.Path(__file__).resolve().parent.parent / "bridge" / "mpfb_bridge"

# MPFB's own pattern, from assetservice.py's get_custom_rigs() and savetolibrary.py.
_MPFB_PATTERN = r"^[a-zA-Z0-9_]+$"

ACCEPTED = ("claude_demo", "a", "_", "1", "Rig2", "a__b", "__", "_lead", "trail_", "a" * 64)
REFUSED = ("my-rig", "my.rig", "my rig", "rig/top", "rig\\top", "..", ".", ".hidden", "", " ",
           "a" * 65, "naïve", "trailing ", "c:nope", "null\x00byte", None, 3, True, 1.5, [], {})


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    store_rig.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_store_rig"].fn


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def test_rig_name_is_required(self):
        with self.assertRaises(TypeError):
            self.tool()

    def test_the_default_call_reaches_the_wire(self):
        self.assertEqual(self._sent(rig_name="claude_demo"), {
            "name": None, "rig_name": "claude_demo", "include_weights": True,
            "identifying_bones": None, "include_masks": False, "overwrite": False,
            "dry_run": False})

    def test_a_name_that_is_refused_never_crosses(self):
        for name in REFUSED:
            with self.subTest(name=name):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(rig_name=name)
                send_command.assert_not_called()

    def test_a_name_that_is_accepted_crosses_as_given(self):
        for name in ACCEPTED:
            with self.subTest(name=name):
                self.assertEqual(self._sent(rig_name=name)["rig_name"], name)

    def test_the_flags_are_real_bools(self):
        for argument in ("include_weights", "include_masks", "overwrite", "dry_run"):
            for bad in ("false", 0, None):
                with self.subTest(argument=argument, value=bad):
                    with self.assertRaises(ValueError):
                        self.tool(rig_name="a", **{argument: bad})

    def test_identifying_bones_is_a_list_of_distinct_names(self):
        for bad in ([], "root", ["root", "root"], [""], [3]):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    self.tool(rig_name="a", identifying_bones=bad)
        self.assertEqual(self._sent(rig_name="a", identifying_bones=["spine_01"])[
            "identifying_bones"], ["spine_01"])


@unittest.skipUnless(_BRIDGE.exists(), "the add-on's source is not beside this checkout")
class BothSidesTests(unittest.TestCase):
    """One rule, run on both sides of the socket over one table."""

    def setUp(self):
        namespace: dict = {}
        path = _BRIDGE / "shared" / "artifact_names.py"
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
        self.bridge_rejection = namespace["rig_name_rejection"]
        self.bridge_pattern = namespace["RIG_NAME_PATTERN"]

    def test_both_give_the_same_verdict_and_the_same_sentence(self):
        for name in ACCEPTED + REFUSED:
            with self.subTest(name=name):
                self.assertEqual(artifact_names.rig_name_rejection(name),
                                 self.bridge_rejection(name))

    def test_the_pattern_is_the_same_on_both_and_is_mpfbs(self):
        self.assertEqual(artifact_names.RIG_NAME_PATTERN, self.bridge_pattern)
        self.assertEqual(artifact_names.RIG_NAME_PATTERN, _MPFB_PATTERN)

    def test_the_table_says_what_it_means(self):
        for name in ACCEPTED:
            self.assertIsNone(artifact_names.rig_name_rejection(name), name)
            self.assertIsNotNone(re.match(_MPFB_PATTERN, name), name)
        for name in REFUSED:
            self.assertIsNotNone(artifact_names.rig_name_rejection(name), name)

    def test_every_name_accepted_is_one_mpfbs_scan_finds(self):
        # Strict in one direction only: nothing accepted here is a file MPFB would skip.
        for name in ACCEPTED:
            self.assertIsNotNone(re.match(_MPFB_PATTERN, name))


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "store_rig": fake_bridge.ok_envelope("store_rig", {"stored": False}),
        })
        envelope = _tool_callable()(rig_name="claude_demo", dry_run=True)
        self.assertEqual(envelope["result"], {"stored": False})
        self.assertEqual(server.commands()[-1], "store_rig")


if __name__ == "__main__":
    unittest.main()
