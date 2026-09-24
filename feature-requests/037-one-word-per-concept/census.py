#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 037's census: every name on the tool surface, and where each is spelled.

The request asks whether each concept has one spelling and each spelling one
concept. This script answers the mechanical half: which names exist, of which
kind, and where. Whether two names are one concept, or one name two concepts,
is a judgement, and ``census.md`` beside this file is that judgement. The
tables in the README were the starting point; this is what they are checked
against.

Four inventories, from three sources:

- **Arguments**, from ``mpfbmcp.build_server()``: name, JSON type, default and
  tool, read from the input schema a client downloads. This is the one part
  that imports the package, since the server that ships is the thing measured.
- **Command parameters**, from each bridge command's ``Param(...)`` calls, so a
  tool argument and the parameter it becomes can be seen side by side.
- **Response keys and refusal slugs**, from the bridge source by ``ast``: the
  keyword names of every ``dict(...)`` call, the string keys of every dict
  literal and subscript store, the keywords a refusal helper passes on, and
  every slug-shaped string handed to ``blocked_by`` or to a helper whose name
  says it blocks. This over-reports: a dict built for internal use is counted
  too. That is why the answer keys are checked here, with the internal ones
  named, rather than by a permanent test.
- **Prose terms**, every backticked term in the tool descriptions and the
  server instructions, since that is where a caller learns a spelling first.

**``--check``** says whether the renames ``census.md`` decided have landed.
For each entry in ``RENAMES``, the old spelling must be gone from the places
the entry names, and the new one present. Run at the start of the effort it
lists everything outstanding; at the end it must exit 0.

## Running

Inside the repository's venv, since the argument inventory imports the package::

    python3 feature-requests/037-one-word-per-concept/census.py
    python3 feature-requests/037-one-word-per-concept/census.py --section keys
    python3 feature-requests/037-one-word-per-concept/census.py --check
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import collections
import json
import os
import re
import sys

__all__ = (
    "RENAMES",
    "arguments",
    "command_parameters",
    "main",
    "prose_terms",
    "response_keys",
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
_COMMANDS = os.path.join(_ROOT, "bridge", "mpfb_bridge", "commands")
_SHARED = os.path.join(_ROOT, "bridge", "mpfb_bridge", "shared")

# Bridge modules that are not a tool's command: the dispatch table, the base
# class, and the two commands that answer about the bridge itself.
_NOT_A_TOOL = frozenset(("table", "command", "get_status", "list_commands"))

# Variables holding a dict of MPFB's own, whose keys are MPFB's spelling and are
# never renamed: create_human_from_preset's deserialization settings, which it
# also reports verbatim as `settings_used`, and save_expression's file metadata.
_MPFB_DICTS = frozenset(("settings", "metadata"))

_SLUG = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$|^[a-z]+$")
_BACKTICKED = re.compile(r"`([^`\n]+)`")


# ---------------------------------------------------------------- the renames
#
# What census.md decided, as data. Each entry is one spelling retired:
#
#   kind   - "argument", "key" (a response key) or "slug" (a blocked_by value)
#   old    - the retired spelling
#   new    - what replaces it
#   where  - the tools (argument) or bridge modules (key, slug) the rename
#            covers. The old spelling may legitimately remain elsewhere, meaning
#            something else, and is not checked there.
#   rule   - the census.md heading that decided it
#
# and two optional flags, each for a case a plain "old gone, new present" check
# would get wrong:
#
#   old_stays   - the old spelling remains in `where` with another meaning, as
#                 `name` does in the two save tools (R1 swaps it)
#   prose_stays - the old word remains in the description legitimately, as
#                 `weight` does wherever expression rows are described
#
# census.md is the judgement and this is its checkable half. An entry leaves
# --check's output when its commit lands, and stays here as the record.


def _renames(kind, rule, where, pairs, **flags):
    return [dict(kind=kind, old=old, new=new, where=list(where), rule=rule, **flags)
            for old, new in pairs]


def _commands(*names):
    return ["commands/" + name for name in names]


_ASSETS_POSSIBLY_STALE = ("apply_expressions", "set_face_units", "set_macro_details",
                          "set_targets", "symmetrize_targets")

RENAMES: list[dict] = (
    # R1
    _renames("argument", "R1", ["mpfb_save_preset", "mpfb_save_expression"],
             [("subject", "name")])
    + _renames("argument", "R1", ["mpfb_save_preset"], [("name", "preset_name")],
               old_stays=True)
    + _renames("argument", "R1", ["mpfb_save_expression"], [("name", "expression_name")],
               old_stays=True)
    + _renames("argument", "R1", ["mpfb_create_human_from_preset"], [("name", "preset_name")])
    + _renames("key", "R1", _commands("save_preset", "create_human_from_preset"),
               [("name", "preset_name")])
    + _renames("key", "R1", _commands("save_expression"), [("name", "expression_name")])
    # R2
    + _renames("key", "R2", _commands("create_human"), [("object_name", "basemesh_name")])
    + _renames("key", "R2", _commands("refit_human", "save_preset", *_ASSETS_POSSIBLY_STALE),
               [("rig_name", "rig_object_name")])
    + _renames("key", "R2", _commands("add_rig"),
               [("existing_rig_name", "existing_rig_object_name")])
    + _renames("key", "R2", _commands("remove_asset"), [("body_proxy_name", "bodyproxy_name")])
    + _renames("argument", "R2", ["mpfb_generate_rigify_rig"], [("rig_name", "generated_rig_name")])
    + _renames("key", "R2", _commands("generate_rigify_rig"),
               [("rig_name_requested", "generated_rig_name_requested")])
    # R3
    + _renames("key", "R3", _commands("set_targets", "set_face_units"), [("applied", "changes")])
    + _renames("key", "R3", _commands("set_macro_details", "symmetrize_targets"),
               [("changed", "changes")])
    + _renames("key", "R3", _commands("set_face_units"), [("applied_count", "change_count")])
    + _renames("key", "R3", _commands("symmetrize_targets"), [("changed_count", "change_count")])
    + _renames("key", "R3", ["shared/expression_divergence"], [("applied", "from_stack")])
    # R4
    + _renames("key", "R4", ["shared/asset_info", "commands/generate_rigify_rig"],
               [("rig_type", "rig_identified_as")])
    + _renames("key", "R4", ["shared/asset_info"], [("material_type", "material_identified_as")])
    + _renames("key", "R4", _commands("add_rig"),
               [("existing_rig_type", "existing_rig_identified_as")])
    # R5
    + _renames("key", "R5", _commands("set_macro_details"),
               [("previous", "previous_value"), ("new", "new_value")])
    + _renames("key", "R5", _commands("set_asset_material"),
               [("previous_alternative_material", "alternative_material_before")])
    + _renames("key", "R5", _commands("save_preset", "save_expression"),
               [("previous_file", "file_before"), ("current_file", "file_after")])
    # R6
    + _renames("argument", "R6", ["mpfb_add_asset"], [("asset_type", "object_type")])
    + _renames("key", "R6", _commands("add_asset"),
               [("asset_type", "object_type"),
                ("requested_asset_type", "requested_object_type"),
                ("known_asset_types", "known_object_types")])
    + _renames("slug", "R6", _commands("add_asset"), [("unknown_asset_type", "unknown_object_type")])
    + _renames("key", "R6", _commands("list_objects"),
               [("requested_type", "requested_object_type"),
                ("type_recognized", "object_type_recognized"),
                ("known_types", "known_object_types")])
    + _renames("key", "R6", _commands("list_assets"),
               [("requested_subdir", "requested_asset_subdir"),
                ("subdir_recognized", "asset_subdir_recognized"),
                ("known_subdirs", "known_asset_subdirs"),
                ("counts_by_subdir", "counts_by_asset_subdir")])
    + _renames("argument", "R6", ["mpfb_set_face_units"], [("clear_first", "mode")])
    + _renames("key", "R6", _commands("set_face_units"),
               [("clear_first", "mode"), ("cleared", "removed_by_replace")])
    # R7
    + _renames("argument", "R7", ["mpfb_create_human_from_preset"],
               [("material_instances", "material_instances_policy"),
                ("override_skin_model", "override_skin_type"),
                ("override_clothes_model", "override_clothes_material_type"),
                ("override_eyes_model", "override_eyes_material_type")])
    + _renames("key", "R7", _commands("create_human_from_preset"),
               [("material_instances", "material_instances_policy"),
                ("material_instances_requested", "material_instances_policy_requested"),
                ("material_instances_used", "material_instances_policy_used"),
                ("material_instances_service_default",
                 "material_instances_policy_service_default"),
                ("known_material_instances", "known_material_instances_policies"),
                ("override_skin_model", "override_skin_type"),
                ("override_clothes_model", "override_clothes_material_type"),
                ("override_eyes_model", "override_eyes_material_type")])
    + _renames("slug", "R7", _commands("create_human_from_preset"),
               [("unknown_material_instances", "unknown_material_instances_policy")])
    # A face unit's number is `value`
    + _renames("key", "face unit value", _commands("get_face_units", "set_face_units"),
               [("weight", "value")])
    + _renames("key", "face unit value", _commands("get_character_summary"),
               [("weight", "value")], prose_stays=True)
    # How something was resolved, and what was not found
    + _renames("key", "resolution", _commands("get_object_info"),
               [("resolved_from", "subject_resolved_by")])
    + _renames("key", "resolution", _commands("add_asset", "set_asset_material", "set_skin"),
               [("resolved_by", "path_resolved_by")])
    + _renames("slug", "resolution", _commands("remove_asset", "set_asset_material"),
               [("not_found", "subject_not_found")])
    + _renames("slug", "resolution", _commands("save_preset"),
               [("properties_unreachable", "properties_unavailable")])
    # The mesh assets on a character
    + _renames("key", "mesh assets", _commands("get_character_summary"),
               [("assets", "equipped_assets")])
    + _renames("key", "mesh assets", _commands("create_human_from_preset"),
               [("object_name", "name")])
)


# ------------------------------------------------------------------ arguments

def _json_type(schema):
    if "type" in schema:
        return schema["type"]
    return "|".join(sorted(
        option["type"] for option in schema.get("anyOf", ())
        if option.get("type") not in (None, "null")))


def _tools():
    sys.path.insert(0, os.path.join(_ROOT, "src"))
    import mpfbmcp  # pylint: disable=import-outside-toplevel
    server = mpfbmcp.build_server()
    return server, asyncio.run(server.list_tools())


def arguments(tools):
    """Argument name -> [(tool, JSON type, default or "required")]."""
    found = collections.defaultdict(list)
    for tool in tools:
        schema = tool.inputSchema
        required = set(schema.get("required", ()))
        for name, prop in schema.get("properties", {}).items():
            default = "required" if name in required else json.dumps(prop.get("default"))
            found[name].append((tool.name, _json_type(prop), default))
    return found


# ------------------------------------------------------------ bridge source

def _bridge_modules():
    for directory, kind in ((_COMMANDS, "commands"), (_SHARED, "shared")):
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".py") or filename == "__init__.py":
                continue
            stem = filename[:-3]
            if kind == "commands" and stem in _NOT_A_TOOL:
                continue
            with open(os.path.join(directory, filename), encoding="utf-8") as handle:
                yield "{:s}/{:s}".format(kind, stem), ast.parse(handle.read())


def _called_name(call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _string(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def command_parameters():
    """Command -> [(parameter, declared type, default)], from each ``Param(...)``."""
    found = {}
    for module, tree in _bridge_modules():
        if not module.startswith("commands/"):
            continue
        params = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _called_name(node) == "Param" and node.args:
                name = _string(node.args[0])
                kind = ast.unparse(node.args[1]) if len(node.args) > 1 else "?"
                default = next((ast.unparse(k.value) for k in node.keywords
                                if k.arg == "default"), "required")
                if name:
                    params.append((name, kind, default))
        found[module.split("/", 1)[1]] = params
    return found


def response_keys():
    """(key -> {module}, slug -> {module}) over every command and shared module."""
    keys = collections.defaultdict(set)
    slugs = collections.defaultdict(set)
    for module, tree in _bridge_modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _called_name(node)
                if name == "dict" or "blocked" in name or name in ("with_performed",):
                    for keyword in node.keywords:
                        if keyword.arg:
                            keys[keyword.arg].add(module)
                        if keyword.arg == "blocked_by" and _string(keyword.value):
                            slugs[_string(keyword.value)].add(module)
                if "blocked" in name or name.endswith("_refusal"):
                    for argument in node.args:
                        text = _string(argument)
                        if text and _SLUG.match(text):
                            slugs[text].add(module)
            elif isinstance(node, ast.FunctionDef) and any(
                    part in node.name for part in ("precondition", "refusal", "blocker")):
                # A helper that returns (slug, sentence) rather than an answer.
                for inner in ast.walk(node):
                    if (isinstance(inner, ast.Return) and isinstance(inner.value, ast.Tuple)
                            and inner.value.elts and _string(inner.value.elts[0])
                            and _SLUG.match(_string(inner.value.elts[0]))):
                        slugs[_string(inner.value.elts[0])].add(module)
            elif isinstance(node, ast.Dict):
                for key in node.keys:
                    if _string(key):
                        keys[_string(key)].add(module)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Subscript) and _string(target.slice)
                            and ast.unparse(target.value) not in _MPFB_DICTS):
                        keys[_string(target.slice)].add(module)
                        if _string(target.slice) == "blocked_by" and _string(node.value):
                            slugs[_string(node.value)].add(module)
    return keys, slugs


# ---------------------------------------------------------------------- prose

def prose_terms(server, tools):
    """Backticked term -> [tool] (``(instructions)`` for the server's own)."""
    found = collections.defaultdict(list)
    texts = [(tool.name, tool.description or "") for tool in tools]
    texts.append(("(instructions)", server.instructions or ""))
    for owner, text in texts:
        for term in _BACKTICKED.findall(text):
            if owner not in found[term]:
                found[term].append(owner)
    return found


# --------------------------------------------------------------------- report

def _short(module):
    return module.split("/", 1)[1] if module.startswith("commands/") else module


def _report(section, server, tools):
    if section in ("all", "arguments"):
        args = arguments(tools)
        print("## Arguments: {:d} names over {:d} tools\n".format(len(args), len(tools)))
        for name in sorted(args):
            uses = args[name]
            types = sorted(set(kind for _tool, kind, _default in uses))
            flag = "  <-- {:d} types".format(len(types)) if len(types) > 1 else ""
            print("{:s} ({:d}){:s}".format(name, len(uses), flag))
            for tool, kind, default in sorted(uses):
                print("    {:<34s} {:<14s} {:s}".format(tool, kind, default))
        print()
    if section in ("all", "parameters"):
        params = command_parameters()
        print("## Command parameters\n")
        for command in sorted(params):
            print("{:s}: {:s}".format(command, ", ".join(
                "{:s}={:s}".format(name, default) for name, _kind, default in params[command])))
        print()
    if section in ("all", "keys", "slugs"):
        keys, slugs = response_keys()
        if section in ("all", "keys"):
            print("## Response keys: {:d}\n".format(len(keys)))
            for key in sorted(keys):
                print("{:<40s} {:s}".format(key, ", ".join(sorted(_short(m) for m in keys[key]))))
            print()
        if section in ("all", "slugs"):
            print("## Refusal slugs: {:d}\n".format(len(slugs)))
            for slug in sorted(slugs):
                print("{:<40s} {:s}".format(slug, ", ".join(sorted(_short(m) for m in slugs[slug]))))
            print()
    if section in ("all", "prose"):
        terms = prose_terms(server, tools)
        print("## Backticked terms: {:d}\n".format(len(terms)))
        for term in sorted(terms):
            print("{:<40s} {:s}".format(term, ", ".join(
                owner.replace("mpfb_", "") for owner in terms[term])))
        print()


# ---------------------------------------------------------------------- check

def _tool_of(place):
    """The tool a ``where`` entry belongs to, or ``None`` for a shared module."""
    if place.startswith("mpfb_"):
        return place
    if place.startswith("commands/"):
        return "mpfb_" + place.split("/", 1)[1]
    return None


def _check(server, tools):
    args = arguments(tools)
    keys, slugs = response_keys()
    terms = prose_terms(server, tools)
    problems = []
    for rename in RENAMES:
        kind, old, new, where = rename["kind"], rename["old"], rename["new"], rename["where"]
        if kind == "argument":
            present = {tool for tool, _kind, _default in args.get(old, ())}
            added = {tool for tool, _kind, _default in args.get(new, ())}
        else:
            table = keys if kind == "key" else slugs
            present = table.get(old, set())
            added = table.get(new, set())
        for place in where:
            if place in present and not rename.get("old_stays"):
                problems.append("NOT RENAMED: {:s} {!r} is still in {:s} (should be {!r})".format(
                    kind, old, place, new))
            if place not in added:
                problems.append("MISSING: {:s} {!r} is not in {:s}".format(kind, new, place))
        if rename.get("old_stays") or rename.get("prose_stays"):
            continue
        tools = {_tool_of(place) for place in where} - {None}
        for owner in terms.get(old, ()):
            if owner in tools:
                problems.append("DESCRIBED: {!r} is still backticked in {:s}'s description".format(
                    old, owner))
    for problem in problems:
        print(problem)
    print("{:d} renames, {:d} outstanding".format(len(RENAMES), len(problems)))
    return 1 if problems else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0].strip())
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero while any rename in RENAMES is outstanding")
    parser.add_argument("--section", default="all",
                        choices=("all", "arguments", "parameters", "keys", "slugs", "prose"))
    options = parser.parse_args()
    server, tools = _tools()
    if options.check:
        return _check(server, tools)
    _report(options.section, server, tools)
    return 0


if __name__ == "__main__":
    sys.exit(main())
