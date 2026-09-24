# SPDX-License-Identifier: GPL-3.0-or-later

"""
The argument vocabulary across every tool, measured on the server that ships.

Built on ``mpfbmcp.build_server()``, as ``tests/test_description_budget.py`` is,
so that a newly registered tool is inside these rules rather than outside them.
None of it needs a Blender.

[FR 037](../feature-requests/037-one-word-per-concept/README.md) found that the
MCP layer drops an argument it does not know: ``mpfb_list_docs`` called with
``topc`` answered with every document. A caller is a language model that
generalizes one tool's spellings to the next, so a wrong guess, a misspelling
and a renamed argument's old spelling all used to look like the same thing - a
successful call with the default in place of what was asked. What is checked
here:

- **every tool refuses an argument it does not declare**, before anything is
  sent, and the refusal reaches a real MCP client as an ``isError`` result
  naming the argument rather than as a protocol failure it might hide;
- **the retired spellings table is coherent**: each entry is a registered tool,
  the old spelling is no longer declared by it, and the new one is;
- **no argument name carries two JSON types** across tools, since a caller that
  learned the name in one tool sends the wrong type to the other.

Response keys are not checked here. They are built bridge-side as dicts and
keyword arguments, and a list of forbidden spellings over that source would
also match internal dictionaries; FR 037's ``census.py --check`` is where they
are checked.

Run with::

    python -m unittest tests.test_vocabulary -v
"""

from __future__ import annotations

__all__ = ()

import asyncio
import collections
import logging
import unittest
from unittest import mock

from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session

import mpfbmcp
from mpfbmcp import arguments

# The argument names that carry two JSON types, and the tools that declare them.
# An exact match rather than an allowance, so that adding a collision fails
# here. FR 037 removed the last one: the preset tool's `material_instances`
# string became `material_instances_policy`, and `mpfb_set_skin`'s bool kept
# the name.
_KNOWN_TYPE_COLLISIONS: dict = {}

_UNDECLARED = "not_an_argument_of_any_tool"


def _json_type(schema: dict) -> str:
    """The JSON type a property takes, with an optional argument's ``null`` left out."""
    if "type" in schema:
        return schema["type"]
    return "|".join(sorted(
        option["type"] for option in schema.get("anyOf", ())
        if option.get("type") not in (None, "null")))


class DeclaredArgumentsTests(unittest.TestCase):

    def setUp(self) -> None:
        self.server = mpfbmcp.build_server()
        self.tools = asyncio.run(self.server.list_tools())

    def test_every_tool_is_checked_against_what_its_schema_declares(self) -> None:
        # If FastMCP's tool manager ever moves, build_server() finds no tools and
        # silently checks nothing; this is what says so.
        self.assertEqual(len(self.tools), 32)
        self.assertEqual(
            self.server.declared_arguments,
            {tool.name: frozenset(tool.inputSchema.get("properties", {}))
             for tool in self.tools})

    def test_every_tool_refuses_an_undeclared_argument_before_sending(self) -> None:
        with mock.patch("mpfbmcp.backend.send",
                        side_effect=AssertionError("crossed the socket")) as send:
            for tool in self.tools:
                with self.subTest(tool=tool.name):
                    with self.assertRaises(ToolError) as raised:
                        asyncio.run(self.server.call_tool(tool.name, {_UNDECLARED: 1}))
                    message = str(raised.exception)
                    self.assertIn("Error executing tool {:s}: ".format(tool.name), message)
                    self.assertIn("Unknown argument {!r}.".format(_UNDECLARED), message)
                    for name in tool.inputSchema.get("properties", {}):
                        self.assertIn(name, message)
        send.assert_not_called()

    def test_a_retired_spelling_is_refused_with_its_replacement(self) -> None:
        # A made-up spelling, so that this holds while the table is empty and
        # whatever it goes on to hold.
        retired = {"mpfb_set_face_units": {"retired_spelling": "face_units"}}
        with mock.patch.dict(arguments.RETIRED_ARGUMENTS, retired), \
                mock.patch("mpfbmcp.backend.send",
                           side_effect=AssertionError("crossed the socket")):
            with self.assertRaises(ToolError) as raised:
                asyncio.run(self.server.call_tool(
                    "mpfb_set_face_units", {"retired_spelling": True}))
        self.assertIn("'retired_spelling' (now called 'face_units')", str(raised.exception))

    def test_the_retired_spellings_table_is_coherent(self) -> None:
        declared = self.server.declared_arguments
        for tool, renames in arguments.RETIRED_ARGUMENTS.items():
            self.assertIn(tool, declared)
            for old, new in renames.items():
                with self.subTest(tool=tool, old=old):
                    self.assertNotIn(old, declared[tool], "a retired spelling is still declared")
                    self.assertIn(new, declared[tool], "a replacement the tool does not declare")

    def test_no_argument_name_has_two_json_types(self) -> None:
        types = collections.defaultdict(lambda: collections.defaultdict(list))
        for tool in self.tools:
            for name, schema in tool.inputSchema.get("properties", {}).items():
                types[name][_json_type(schema)].append(tool.name)
        collisions = {name: {kind: sorted(tools) for kind, tools in by_type.items()}
                      for name, by_type in types.items() if len(by_type) > 1}
        self.assertEqual(collisions, _KNOWN_TYPE_COLLISIONS)


class RefusalReachesTheClientTests(unittest.TestCase):
    """Through a real MCP client session, in memory, rather than by calling the server."""

    def test_the_client_sees_a_tool_error_naming_the_argument(self) -> None:
        async def call() -> object:
            async with create_connected_server_and_client_session(
                    mpfbmcp.build_server()) as client:
                return await client.call_tool("mpfb_list_docs", {"topc": "services"})

        # FastMCP logs every request at INFO through a handler of its own.
        logging.disable(logging.INFO)
        try:
            result = asyncio.run(call())
        finally:
            logging.disable(logging.NOTSET)
        self.assertTrue(result.isError)
        self.assertEqual(
            result.content[0].text,
            "Error executing tool mpfb_list_docs: Unknown argument 'topc'. "
            "This tool accepts keyword, topic.")


if __name__ == "__main__":
    unittest.main()
