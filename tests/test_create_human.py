# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_create_human tool: parameter validation and generated code,
independent of a live Blender connection (mpfbmcp.connection.send_code is
mocked out). Assembly itself is covered in tests/test_codegen.py.

Run with::

    python -m unittest tests.test_create_human -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.tools import create_human


def _params_in(code: str) -> dict:
    """
    The PARAMS the generated source will bind, by executing its prelude.

    Parameters are carried into the payload as JSON data rather than
    interpolated into it, so the values are asserted on after execution rather
    than as substrings of the source.
    """
    prelude, _sep, _payload = code.partition("# --- payload:")
    # The prelude sits behind the raising bootstrap, which would fail here with
    # no MPFB loaded, so run only the two lines that bind PARAMS.
    namespace: dict = {}
    exec(prelude[prelude.index("import json"):], namespace)  # noqa: S102
    return namespace["PARAMS"]


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
        self.assertIn("HumanService.create_human(", code)
        params = _params_in(code)
        self.assertEqual(params["scale"], 0.1)
        self.assertEqual(params["macro_detail_dict"]["gender"], 0.5)
        self.assertEqual(
            params["macro_detail_dict"]["race"],
            {"asian": 0.33, "caucasian": 0.33, "african": 0.33},
        )

    @mock.patch("mpfbmcp.tools.create_human.send_code")
    def test_custom_values_are_passed_through(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {}}

        self.mpfb_create_human(gender=1.0, age=0.2, scale=0.05)

        (code,), _kwargs = mock_send_code.call_args
        params = _params_in(code)
        self.assertEqual(params["scale"], 0.05)
        self.assertEqual(params["macro_detail_dict"]["gender"], 1.0)
        self.assertEqual(params["macro_detail_dict"]["age"], 0.2)

    @mock.patch("mpfbmcp.tools.create_human.send_code")
    def test_bootstrap_still_raises_when_mpfb_is_unusable(self, mock_send_code: mock.Mock) -> None:
        # This tool cannot do its job without MPFB, so it keeps the raising
        # bootstrap - unlike mpfb_get_status, which shares the same module scan
        # but classifies instead. Guards against the refactor that split the two.
        mock_send_code.return_value = {"status": "ok", "result": {}}

        self.mpfb_create_human()

        (code,), _kwargs = mock_send_code.call_args
        self.assertIn("raise RuntimeError", code)
        self.assertIn("_MPFB_SERVICES", code)

    def test_out_of_range_macro_value_is_rejected_locally(self) -> None:
        # Should raise before ever touching the network.
        with mock.patch("mpfbmcp.tools.create_human.send_code") as mock_send_code:
            with self.assertRaises(ValueError):
                self.mpfb_create_human(gender=1.5)
            mock_send_code.assert_not_called()


if __name__ == "__main__":
    unittest.main()
