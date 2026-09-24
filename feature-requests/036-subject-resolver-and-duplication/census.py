#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 036's census: which code is written more than once, and how differently.

The request this belongs to asks two questions of the same code: are these
copies the same, and should they be one. This script answers only the first,
because the first is mechanical and the second is not. Whether a group is
shared depends on whether its drift would mislead a caller, whether it names
one concept, and whether it is a convention applied per tool - the rule as
FR 036's README restates it. What this prints is the input to that judgement,
and ``census.md`` beside it is the judgement.

It reads source and imports nothing, so it runs with no Blender, no MPFB and no
installed package. It looks in three places: the bridge's ``commands/`` and
``shared/``, and this package's ``tools/``.

**Two kinds of finding, because two kinds of duplication exist.**

- **By name**: a module-level function defined in more than one module. Each
  group is reported with two counts of distinct bodies - one with string
  literals kept, one with them all replaced by a placeholder - since a group
  that is one body with thirteen different messages is a different finding
  from thirteen different bodies. Docstrings are stripped from both.
- **By shape**: a pattern written under several names or inline, which a name
  census cannot see. The subject resolver is the reason this exists. It is
  ``_resolve`` in fourteen commands, ``_resolve_basemesh`` in two, and
  ``resolve_basemesh`` in a shared module. And ``_resolve`` also names things
  that are not resolvers at all, such as ``create_human_from_preset``'s.

**Run it at the start of the effort and again at the end.** The difference is
what the effort did; what is left at the end should be exactly what
``census.md`` records as kept on purpose, and ``--check`` says whether it is.

## Running

    python3 feature-requests/036-subject-resolver-and-duplication/census.py
    python3 feature-requests/036-subject-resolver-and-duplication/census.py --check
"""

from __future__ import annotations

import argparse
import ast
import collections
import os
import sys

__all__ = (
    "KEPT",
    "census_by_name",
    "census_by_shape",
    "main",
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))

_SEARCHED = (
    os.path.join("bridge", "mpfb_bridge", "commands"),
    os.path.join("bridge", "mpfb_bridge", "shared"),
    os.path.join("src", "mpfbmcp", "tools"),
)

# Names every module of a kind defines by design: one per tool or per command,
# never a candidate for sharing, and noise in every other line of the output.
_CONVENTIONAL = frozenset(("register",))

# What the effort decided to leave duplicated, name -> the census.md heading
# that says why. Filled in by the effort, not before it: until a group has been
# judged it belongs in neither this table nor a shared module. ``--check``
# fails on any group of copies that is neither.
KEPT = {
}


class _Normalised(ast.NodeTransformer):
    """A body with its docstrings dropped and, optionally, its strings blanked."""

    def __init__(self, blank_strings):
        self.blank_strings = blank_strings

    def _drop_docstring(self, node):
        body = node.body
        if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
        return node

    def visit_FunctionDef(self, node):  # pylint: disable=invalid-name
        self.generic_visit(node)
        return self._drop_docstring(node)

    def visit_Constant(self, node):  # pylint: disable=invalid-name
        if self.blank_strings and isinstance(node.value, str):
            return ast.Constant(value="S")
        return node


def _modules():
    for directory in _SEARCHED:
        absolute = os.path.join(_ROOT, directory)
        for filename in sorted(os.listdir(absolute)):
            if filename.endswith(".py") and filename != "__init__.py":
                path = os.path.join(absolute, filename)
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
                yield os.path.relpath(path, _ROOT), source, ast.parse(source)


def _body_key(node, blank_strings):
    copy = ast.parse(ast.unparse(node)).body[0]
    copy = _Normalised(blank_strings).visit(copy)
    copy.name = "_"
    return ast.dump(copy)


def census_by_name():
    """Every module-level function name defined in two or more searched modules."""
    groups = collections.defaultdict(list)
    for path, _source, tree in _modules():
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name not in _CONVENTIONAL:
                groups[node.name].append(dict(
                    path=path, line=node.lineno,
                    exact=_body_key(node, blank_strings=False),
                    shape=_body_key(node, blank_strings=True)))
    return {name: copies for name, copies in groups.items() if len(copies) > 1}


def _is_view_layer_active(node):
    return (isinstance(node, ast.Attribute) and node.attr == "active"
            and ast.unparse(node) == "bpy.context.view_layer.objects.active")


def _reads_active_and_name(node):
    text = ast.unparse(node)
    return ("bpy.context.view_layer.objects.active" in text
            and "bpy.data.objects.get(" in text)


def _restores_active(node):
    if not isinstance(node, ast.Try):
        return False
    for statement in node.finalbody:
        for inner in ast.walk(statement):
            if isinstance(inner, ast.Assign) and any(_is_view_layer_active(target)
                                                     for target in inner.targets):
                return True
    return False


def _reaches_module_level(node):
    return (isinstance(node, ast.Subscript)
            and ast.unparse(node.value) == "sys.modules")


def _resolves_subject(node):
    return isinstance(node, ast.FunctionDef) and _reads_active_and_name(node)


# Pattern name -> (what it is, predicate over any node inside a top-level
# function or class). Methods count: asset_info's Lookup reaches sys.modules
# from inside a class, and a census of top-level functions alone missed it.
_SHAPES = {
    "subject resolution": (
        "the active object or a named one, from the view layer or bpy.data",
        _resolves_subject),
    "selection restored": (
        "a finally that puts the caller's active object back",
        _restores_active),
    "module-level reach": (
        "a name MPFB keeps on a service's module, read through sys.modules",
        _reaches_module_level),
}


def census_by_shape():
    """Pattern -> [(path, line, enclosing top-level function or class)]."""
    found = collections.defaultdict(list)
    for path, _source, tree in _modules():
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                continue
            for shape, (_meaning, predicate) in _SHAPES.items():
                for inner in ast.walk(node):
                    if predicate(inner):
                        found[shape].append((path, inner.lineno, node.name))
    return found


def _report(by_name, by_shape):
    print("## By name: {:d} function names defined in more than one module\n".format(
        len(by_name)))
    print("{:<30s} {:>6s} {:>9s} {:>9s}  {:s}".format(
        "name", "copies", "distinct", "shapes", "where"))
    ordered = sorted(by_name.items(), key=lambda item: (-len(item[1]), item[0]))
    for name, copies in ordered:
        distinct = len(set(copy["exact"] for copy in copies))
        shapes = len(set(copy["shape"] for copy in copies))
        where = ", ".join(sorted(set(
            "{:s}/{:s}".format(os.path.basename(os.path.dirname(copy["path"])),
                               os.path.basename(copy["path"])[:-3])
            for copy in copies)))
        print("{:<30s} {:>6d} {:>9d} {:>9d}  {:s}".format(
            name, len(copies), distinct, shapes, where))
    print()
    for shape, (meaning, _predicate) in _SHAPES.items():
        hits = by_shape.get(shape, [])
        print("## By shape: {:s} ({:s}), {:d} occurrences\n".format(shape, meaning, len(hits)))
        for path, line, function in hits:
            print("    {:s}:{:d}  in {:s}()".format(path, line, function))
        print()


def _check(by_name):
    unjudged = sorted(name for name in by_name if name not in KEPT)
    stale = sorted(name for name in KEPT if name not in by_name)
    for name in unjudged:
        print("NOT JUDGED: {:s} has {:d} copies and is not in KEPT".format(
            name, len(by_name[name])))
    for name in stale:
        print("STALE: {:s} is in KEPT but is no longer duplicated".format(name))
    return 1 if unjudged or stale else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0].strip())
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if a duplicate is neither shared nor listed in KEPT")
    arguments = parser.parse_args()
    by_name = census_by_name()
    if arguments.check:
        return _check(by_name)
    _report(by_name, census_by_shape())
    return 0


if __name__ == "__main__":
    sys.exit(main())
