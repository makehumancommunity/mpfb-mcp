# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_create_human tool: parameter validation and generated code,
independent of a live Blender connection (mpfbmcp.connection.send_code is
mocked out).

Run with::

    python -m unittest tests.test_create_human -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import create_human


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    create_human.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_create_human"]  # noqa: SLF001
    return tool.fn


class CreateHumanToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_create_human = _register_and_get_tool()

    @mock.patch("mpfbmcp.tools.create_human.send_code")
    def test_default_call_uses_mpfb_default_macro_dict(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"object_name": "Human"}}

        response = self.mpfb_create_human()

        self.assertEqual(response, {"status": "ok", "result": {"object_name": "Human"}})
        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertIn("HumanService.create_human(scale=0.1", code)
        self.assertIn('"gender": 0.5', code)
        self.assertIn('"race"', code)
        self.assertIn('"asian": 0.33', code)

    @mock.patch("mpfbmcp.tools.create_human.send_code")
    def test_custom_values_are_passed_through(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {}}

        self.mpfb_create_human(gender=1.0, age=0.2, scale=0.05)

        (code,), _kwargs = mock_send_code.call_args
        self.assertIn("scale=0.05", code)
        self.assertIn('"gender": 1.0', code)
        self.assertIn('"age": 0.2', code)

    def test_out_of_range_macro_value_is_rejected_locally(self) -> None:
        # Should raise before ever touching the network.
        with mock.patch("mpfbmcp.tools.create_human.send_code") as mock_send_code:
            with self.assertRaises(ValueError):
                self.mpfb_create_human(gender=1.5)
            mock_send_code.assert_not_called()


if __name__ == "__main__":
    unittest.main()
