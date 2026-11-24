# SPDX-License-Identifier: GPL-3.0-or-later

"""
The argument vocabulary across every tool, measured on the server that ships.

Built on ``mpfbmcp.build_server()``, as ``tests/test_description_budget.py`` is,
so that a newly registered tool is inside these rules rather than outside them.
None of it needs a Blender.

[FR 037](../feature-requests/done/037-one-word-per-concept/README.md) found that the
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
    """The JSON type a property takes, with an optional argument's ``null`` left out.

    An array is told apart by what it holds: ``switches`` is
    ``mpfb_set_pose_switches``' list of objects, and a list of strings under the
    same name would be the collision FR 044 named its filter ``switch_names``
    to avoid. Both are JSON arrays, so without their items it would pass.
    """
    options = [schema] if "type" in schema else [
        option for option in schema.get("anyOf", ())
        if option.get("type") not in (None, "null")]
    return "|".join(sorted(
        "array of {:s}".format(option.get("items", {}).get("type", "anything"))
        if option["type"] == "array" else option["type"]
        for option in options))


class DeclaredArgumentsTests(unittest.TestCase):

    def setUp(self) -> None:
        self.server = mpfbmcp.build_server()
        self.tools = asyncio.run(self.server.list_tools())

    def test_every_tool_is_checked_against_what_its_schema_declares(self) -> None:
        # If FastMCP's tool manager ever moves, build_server() finds no tools and
        # silently checks nothing; this is what says so.
        self.assertEqual(len(self.tools), 56)
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

    def test_a_list_of_objects_and_a_list_of_names_are_two_types(self) -> None:
        # What test_no_argument_name_has_two_json_types relies on to see a
        # `switches` list of names beside mpfb_set_pose_switches' list of objects.
        self.assertEqual(_json_type({"type": "array", "items": {"type": "object"}}),
                         "array of object")
        self.assertEqual(
            _json_type({"anyOf": [{"type": "array", "items": {"type": "string"}},
                                  {"type": "null"}]}),
            "array of string")
        declared = {tool.name: tool.inputSchema.get("properties", {}) for tool in self.tools}
        self.assertEqual(_json_type(declared["mpfb_set_pose_switches"]["switches"]),
                         "array of object")
        self.assertEqual(_json_type(declared["mpfb_get_pose_controls"]["switch_names"]),
                         "array of string")


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


def _optional_arguments(tool) -> list[tuple[str, dict]]:
    """Each argument a call may leave out, with its published schema."""
    schema = tool.inputSchema
    required = set(schema.get("required", ()))
    return [(name, sub) for name, sub in schema.get("properties", {}).items()
            if name not in required]


def _wrong_value(schema: dict) -> object:
    """A value of no type this argument accepts: an object for anything but an object, and a
    string, which FastMCP's pre-parse cannot read as JSON, for an object."""
    if "object" in _json_type(schema).split("|"):
        return "not an object"
    return {"not": "this type"}


# What FastMCP's argument model says when it refuses a call, and what the low-level server would
# say if it validated the published schema: either one, beside an argument that should have been
# accepted, is the failure these tests exist for. A tool's own refusal of a combination - naming
# neither `path` nor `fragment`, say - is a different sentence and not this test's business.
_MODEL_REFUSAL = "validation error for"
_SCHEMA_REFUSAL = "Input validation error"


class PublishedSchemaTests(unittest.TestCase):
    """What FR 059's schema rewrite must not have changed, through a real MCP client.

    The rewrite publishes `str | None = None` as `type: string` and no default. An explicit `null`
    is still accepted only because FastMCP validates through the model built from the signature
    and registers its handler with `validate_input=False` - a fact about the library rather than
    this package, and the one that would break `mpfb_write_mesh_asset`'s `try_with`, which carries
    a `null` for the caller to fill. This is what fails if an `mcp` release changes it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.tools = asyncio.run(mpfbmcp.build_server().list_tools())
        # Which arguments accepted an explicit null before the rewrite, read off the schema
        # FastMCP generated - the published one no longer says, which is the point of it.
        with mock.patch("mpfbmcp._published_without_generated_keys"):
            generated = asyncio.run(mpfbmcp.build_server().list_tools())
        cls.nullable = {
            (tool.name, name)
            for tool in generated
            for name, sub in tool.inputSchema.get("properties", {}).items()
            if {"type": "null"} in sub.get("anyOf", ())}
        cls.results = cls._call_every_optional_argument()

    @classmethod
    def _call_every_optional_argument(cls) -> dict:
        envelope = {"status": "ok", "result": {}, "message": "stubbed"}

        async def call_all() -> dict:
            results = {}
            async with create_connected_server_and_client_session(
                    mpfbmcp.build_server()) as client:
                await client.list_tools()
                for tool in cls.tools:
                    required = {name: _required_value(sub) for name, sub in
                                tool.inputSchema.get("properties", {}).items()
                                if name in tool.inputSchema.get("required", ())}
                    for name, sub in _optional_arguments(tool):
                        for label, value in (("null", None), ("wrong", _wrong_value(sub))):
                            arguments_sent = dict(required)
                            arguments_sent[name] = value
                            results[(tool.name, name, label)] = await client.call_tool(
                                tool.name, arguments_sent)
            return results

        logging.disable(logging.INFO)
        try:
            with mock.patch("mpfbmcp.backend.send", return_value=envelope), \
                    mock.patch("mpfbmcp.bridge_connection.send_command", return_value=envelope):
                return asyncio.run(call_all())
        finally:
            logging.disable(logging.NOTSET)

    def test_an_explicit_null_is_accepted_wherever_it_was(self) -> None:
        checked = 0
        for (tool, name, label), result in self.results.items():
            if label != "null" or (tool, name) not in self.nullable:
                continue
            checked += 1
            with self.subTest(tool=tool, argument=name):
                text = "" if not result.isError else result.content[0].text
                self.assertNotIn(_MODEL_REFUSAL, text)
                self.assertNotIn(_SCHEMA_REFUSAL, text)
        self.assertGreater(checked, 100)

    def test_a_wrong_type_is_still_refused_for_every_optional_argument(self) -> None:
        for (tool, name, label), result in self.results.items():
            if label != "wrong":
                continue
            with self.subTest(tool=tool, argument=name):
                self.assertTrue(result.isError)
                self.assertIn(_MODEL_REFUSAL, result.content[0].text)
                self.assertIn(name, result.content[0].text)

    def test_every_tool_still_declares_an_output_schema(self) -> None:
        # Kept on purpose: see FR 059's "Why the output schemas stay".
        for tool in self.tools:
            with self.subTest(tool=tool.name):
                self.assertIsNotNone(tool.outputSchema)


def _required_value(schema: dict) -> object:
    """A value of the right type for a required argument, so a call reaches the optional one."""
    kind = _json_type(schema).split("|")[0]
    return {"string": "x", "integer": 0, "number": 0.0, "boolean": False, "object": {}}.get(
        kind, [])


if __name__ == "__main__":
    unittest.main()
