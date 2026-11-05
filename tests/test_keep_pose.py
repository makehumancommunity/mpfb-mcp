# SPDX-License-Identifier: GPL-3.0-or-later

"""
``keep_pose``, on the six tools that refit.

One module rather than a test in six, because the claim is that the six agree: the same argument, the
same default, the same refusal, the same thing on the wire. Whether the pose is kept is asked of a real
MPFB in ``bridge/test/tests/eee_composite/keep_pose_test.py``, and nothing here can establish it.

Run with::

    python -m unittest tests.test_keep_pose -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import apply_expressions
from mpfbmcp.tools import refit_human
from mpfbmcp.tools import set_face_units
from mpfbmcp.tools import set_macro_details
from mpfbmcp.tools import set_targets
from mpfbmcp.tools import symmetrize_targets

_REQUIRED = {"mpfb_symmetrize_targets": {"direction": "left_to_right"}}

_TOOLS = (
    ("mpfb_refit_human", refit_human, "refit_human"),
    ("mpfb_set_macro_details", set_macro_details, "set_macro_details"),
    ("mpfb_set_targets", set_targets, "set_targets"),
    ("mpfb_symmetrize_targets", symmetrize_targets, "symmetrize_targets"),
    ("mpfb_set_face_units", set_face_units, "set_face_units"),
    ("mpfb_apply_expressions", apply_expressions, "apply_expressions"),
)


def _tool(name, module):
    mcp = FastMCP("test")
    module.register(mcp)
    return mcp._tool_manager._tools[name].fn  # noqa: SLF001


class KeepPoseTests(unittest.TestCase):
    def _sent(self, name, module, **arguments):
        with mock.patch("mpfbmcp.backend.send", return_value={"status": "ok"}) as send:
            _tool(name, module)(**_REQUIRED.get(name, {}), **arguments)
        return send.call_args

    def test_each_tool_keeps_the_pose_unless_told_otherwise(self):
        for name, module, command in _TOOLS:
            with self.subTest(tool=name):
                call = self._sent(name, module)
                self.assertEqual(call.args[0], command)
                self.assertIs(call.kwargs["params"]["keep_pose"], True)

    def test_false_reaches_the_wire_as_false(self):
        for name, module, _command in _TOOLS:
            with self.subTest(tool=name):
                call = self._sent(name, module, keep_pose=False)
                self.assertIs(call.kwargs["params"]["keep_pose"], False)

    def test_anything_but_a_real_bool_is_refused_before_sending(self):
        # "false" is the one that matters: it is true, and would keep the pose of a caller who
        # asked not to.
        for name, module, _command in _TOOLS:
            for bad in ("false", 0, 1, None, []):
                with self.subTest(tool=name, value=bad):
                    with mock.patch("mpfbmcp.backend.send") as send:
                        with self.assertRaises(ValueError):
                            _tool(name, module)(**_REQUIRED.get(name, {}), keep_pose=bad)
                    send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
