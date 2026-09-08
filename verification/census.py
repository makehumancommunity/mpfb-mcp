# SPDX-License-Identifier: GPL-3.0-or-later

"""
The duplication census: which helpers the payloads repeat, and whether they agree.

The only script here that needs no Blender at all. It sits beside the live
checklists rather than under ``tests/`` because it is an instrument and not a
test: it answers a question about the code, it makes no assertion, and a
divergence it reports may well be the right answer - four sentences that differ
by tense are not a defect, four conditions that differ by a clause are.

The question is the one
[FR 013](../feature-requests/done/013-live-verification/README.md) asked and
[FR 015](../feature-requests/done/015-fourth-shared-fragment/README.md) turned
into this file: **not whether the payloads repeat code - they do, in nineteen
module-level helpers with two or more copies - but whether any two copies have
drifted**, because drift is what turns duplication into a bug. Sixteen of those
nineteen were byte-identical when the census was first run by hand, and being
identical is not by itself a reason to merge them: ``blocked()``'s six variants
are one convention applied six times, and a mechanism for "this tool's null
response" would be bigger than the six copies.

Each function is compared after its docstring is removed and the rest is put
through ``ast.unparse``, so comments, formatting and line breaks cannot make two
identical implementations look different - only the code can.

Four kinds of finding, printed most serious first:

- **shadowed**: a payload defines a name that a fragment *it names* already
  defines. The fragment is concatenated ahead of the payload, so the payload's
  copy wins silently and the fragment's is dead code in that one program. A
  defect whatever the two bodies say, which is why the pairings are read out of
  the tool modules rather than guessed: which fragments a payload is assembled
  with is decided there, in the ``assemble(..., shared=[...])`` or
  ``shared_cache.send(..., shared=[...])`` call.
- **reimplemented**: a payload defines a name a fragment defines, without naming
  that fragment. Not a defect - the two may be unrelated functions that happen
  to share a name - but it is where a migration candidate shows up. This is how
  ``list_targets.py``'s second copy of the user-target scan was found, and
  [FR 017](../feature-requests/done/017-category-table-cost/README.md) closed it
  by pointing that payload at ``target_categories.py``; running this afterwards
  is how the closing was shown.
- **differing**: two or more payloads define one name with different bodies.
  Worth reading; not necessarily worth merging.
- **identical**: the ordinary case, listed last and counted rather than shown.

Run with::

    python3 verification/census.py
"""

from __future__ import annotations

__all__ = ("census", "run")

import ast
import pathlib
import sys

from mpfbmcp import codegen

# The tool modules, which is where a payload's fragments are decided. Reached by
# path rather than by import: what is wanted is the literal argument list, and
# importing twenty modules to read one keyword out of each would need a running
# FastMCP to register them against.
_TOOLS_DIRECTORY = pathlib.Path(__file__).resolve().parent.parent.joinpath(
    "src", "mpfbmcp", "tools")


def _normalised(node: ast.FunctionDef) -> str:
    """One function's body as comparable text: docstring out, formatting away."""
    # A copy, so that stripping the docstring cannot affect a second reading of
    # the same tree. ast.unparse() then removes every difference that is not
    # code: indentation, line breaks, quote style, and comments, which the
    # parser has already dropped.
    stripped = ast.parse(ast.unparse(node)).body[0]
    if (stripped.body and isinstance(stripped.body[0], ast.Expr)
            and isinstance(stripped.body[0].value, ast.Constant)
            and isinstance(stripped.body[0].value.value, str)):
        stripped.body = stripped.body[1:] or [ast.Pass()]
    return ast.unparse(stripped)


def _functions_in(source: str) -> dict[str, str]:
    """Every function defined at module level, by name, normalised.

    Module level only. A closure is part of the function that holds it and is
    compared with it; a method would belong to a class this package's payloads
    do not define.
    """
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            found[node.name] = _normalised(node)
    return found


def fragments_per_payload() -> dict[str, list[str]]:
    """Which fragments each payload is actually assembled with.

    Read out of the ``codegen.assemble()`` or ``shared_cache.send()`` call in
    each tool module, where every argument is a literal. Both spellings, because
    a tool that goes through the session source cache calls the second and names
    the same fragments in the same keyword; whether a fragment is concatenated
    or executed out of the cache makes no difference at all to what it shadows.
    A payload whose tool module could not be read at all comes back with no
    fragments, which under-reports rather than invents a pairing that does not
    exist.
    """
    pairings: dict[str, list[str]] = {}
    for path in sorted(_TOOLS_DIRECTORY.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            name = called.attr if isinstance(called, ast.Attribute) else getattr(
                called, "id", None)
            if name not in ("assemble", "send") or not node.args:
                continue
            payload = getattr(node.args[0], "value", None)
            if not isinstance(payload, str):
                continue
            shared = []
            for keyword in node.keywords:
                if keyword.arg != "shared" or not isinstance(keyword.value, ast.List):
                    continue
                shared = [element.value for element in keyword.value.elts
                          if isinstance(getattr(element, "value", None), str)]
            pairings[payload] = shared
    return pairings


def census() -> dict:
    """The whole finding, as data, so a caller can assert on it if it wants to."""
    fragments: dict[str, dict[str, str]] = {}
    for name in codegen.shared_names():
        fragments[name] = _functions_in(codegen.read_shared(name))

    payloads: dict[str, dict[str, str]] = {}
    for name in codegen.payload_names():
        payloads[name] = _functions_in(codegen.read_payload(name))

    # Which payloads define each name, and which distinct bodies they give it.
    definitions: dict[str, list[str]] = {}
    bodies: dict[str, dict[str, list[str]]] = {}
    for payload_name, functions in payloads.items():
        for function_name, body in functions.items():
            definitions.setdefault(function_name, []).append(payload_name)
            bodies.setdefault(function_name, {}).setdefault(body, []).append(payload_name)

    pairings = fragments_per_payload()
    shadowed = []
    reimplemented = []
    for fragment_name, functions in fragments.items():
        for function_name in functions:
            named_by = sorted(
                payload_name for payload_name in definitions.get(function_name, [])
                if fragment_name in pairings.get(payload_name, []))
            elsewhere = sorted(
                payload_name for payload_name in definitions.get(function_name, [])
                if fragment_name not in pairings.get(payload_name, []))
            if named_by:
                shadowed.append({
                    "function": function_name,
                    "fragment": fragment_name,
                    "payloads": named_by,
                })
            if elsewhere:
                reimplemented.append({
                    "function": function_name,
                    "fragment": fragment_name,
                    "payloads": elsewhere,
                })

    differing = []
    identical = []
    for function_name, payload_names in sorted(definitions.items()):
        if len(payload_names) < 2:
            continue
        variants = bodies[function_name]
        entry = {
            "function": function_name,
            "copies": len(payload_names),
            "payloads": sorted(payload_names),
            "variants": [sorted(names) for names in variants.values()],
        }
        (identical if len(variants) == 1 else differing).append(entry)

    return {
        "payloads": len(payloads),
        "fragments": len(fragments),
        "duplicated_names": len(differing) + len(identical),
        "shadowed": sorted(shadowed, key=lambda entry: entry["function"]),
        "reimplemented": sorted(reimplemented, key=lambda entry: entry["function"]),
        "differing": sorted(differing, key=lambda entry: -entry["copies"]),
        "identical": sorted(identical, key=lambda entry: -entry["copies"]),
    }


def run() -> dict:
    finding = census()

    print("{} payloads, {} shared fragments, {} names defined in more than one payload".format(
        finding["payloads"], finding["fragments"], finding["duplicated_names"]))

    if finding["shadowed"]:
        print("")
        print("SHADOWED - a payload redefines a name from a fragment it names, "
              "and the fragment's copy is then dead code:")
        for entry in finding["shadowed"]:
            print("  {}()  in {}, redefined by {}".format(
                entry["function"], entry["fragment"], ", ".join(entry["payloads"])))

    if finding["reimplemented"]:
        print("")
        print("REIMPLEMENTED - a payload defines a name a fragment also defines, "
              "without naming that fragment. A migration candidate, not a defect:")
        for entry in finding["reimplemented"]:
            print("  {}()  in {}, also defined by {}".format(
                entry["function"], entry["fragment"], ", ".join(entry["payloads"])))

    print("")
    print("DIFFERING - one name, more than one body ({} of {}):".format(
        len(finding["differing"]), finding["duplicated_names"]))
    for entry in finding["differing"]:
        print("  {}()  {} copies in {} variants".format(
            entry["function"], entry["copies"], len(entry["variants"])))
        for variant in entry["variants"]:
            print("      {}".format(", ".join(variant)))

    print("")
    print("IDENTICAL after normalisation ({} of {}), which is not by itself a reason "
          "to merge:".format(len(finding["identical"]), finding["duplicated_names"]))
    for entry in finding["identical"]:
        print("  {}()  {} copies: {}".format(
            entry["function"], entry["copies"], ", ".join(entry["payloads"])))

    return finding


if __name__ == "__main__":
    run()
    sys.exit(0)
