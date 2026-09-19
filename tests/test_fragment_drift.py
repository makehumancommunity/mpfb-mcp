# SPDX-License-Identifier: GPL-3.0-or-later

"""
Every migrated fragment against the bridge module that replaced it.

For the duration of the pivot a shared concept exists **twice**: as a fragment
under ``src/mpfbmcp/codegen/shared/``, concatenated ahead of a payload, and as a
module under ``bridge/mpfb_bridge/shared/``, imported by a command. That is not
temporary redundancy to be tidied away - it is what lets a tool migrate while
the tool it has to agree with has not. ``mpfb_list_rigs`` predicts which weights
``mpfb_add_rig`` will load; ``mpfb_list_assets`` reports the vocabulary
``mpfb_add_asset`` resolves with. Those pairings were the reason the fragments
were written, and with one half of each pair on the bridge and the other still
generated, **"these two agree" has to be asserted rather than intended**.

So this module parses both files with ``ast``, strips docstrings, and compares
what is left through ``ast.unparse``. No Blender, no ``bpy``, no socket: it is
about two files in this repository and runs on every unit run, which is the
only frequency at which a drift check is worth anything.

**One declared substitution, and it is the only one.** A fragment finds MPFB in
a module global the bootstrap bound above it; a bridge module is *handed* MPFB,
because an add-on module that resolved services at import would hold them
across a disable and re-enable. That one difference has three syntactic shapes,
and :class:`_Injected` undoes all three:

- a leading parameter named in :data:`_INJECTED_PARAMETERS`;
- a leading statement unpacking that parameter - ``LocationService =
  services["LocationService"]``, ``TARGET_SECTIONS = tables.sections``;
- that parameter passed as the leading argument to a sibling function.

Nothing else is normalised. A renamed local, a reordered branch or a changed
constant is a difference and is reported as one.

**It must not claim more than it checks.** Three things make that true rather
than hoped for:

1. Every function and every module-level constant in the fragment must be
   accounted for: compared, or named in :data:`UNCOMPARABLE` with a reason.
   A function that quietly vanished from the bridge module would otherwise
   pass as "nothing to compare".
2. :data:`UNCOMPARABLE` is asserted against, not consulted: a name listed there
   that turns out to be comparable fails, so the list cannot rot into a
   suppression file.
3. The pairs are asserted to be non-empty, for the reason
   ``tests/test_reference_drift.py`` asserts its parse found something: a drift
   check that passes because it compared nothing is worse than none.

**The bridge is not installed as a package here** - it is a Blender extension,
outside ``pyproject.toml``'s root entirely - so its modules are read from disk
and parsed, never imported. That is also what keeps this module out of the
harness split: nothing here imports ``bpy``.

Run with::

    python -m unittest tests.test_fragment_drift -v
"""

__all__ = ()

import ast
import pathlib
import unittest

from mpfbmcp import codegen

_REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BRIDGE_SHARED = _REPOSITORY_ROOT / "bridge" / "mpfb_bridge" / "shared"

# Fragment filename -> bridge module filename. They are the same name on
# purpose: a fragment and the module replacing it have to be findable from each
# other during the migration. The table exists so that this test knows which
# fragments have migrated at all - the two that have not, `performed.py` and
# `refit_blocker.py`, belong to mutating tools and arrive in stage 4.
MIGRATED_FRAGMENTS = {
    "preset_files.py": "preset_files.py",
}

# The parameter names a bridge function is handed its context through. Two,
# and each is one concept: `services` is MPFB's SERVICES dict, which the
# bootstrap bound as `_MPFB_SERVICES` on the other side; `tables` is what a
# fragment computed at import time into module globals and a command computes
# per call.
_INJECTED_PARAMETERS = ("services", "tables")

# fragment -> {name: why it cannot be compared}. Asserted rather than consulted:
# a name here that turns out to compare cleanly fails this test, so the list
# cannot become a place to hide a divergence.
UNCOMPARABLE: dict[str, dict[str, str]] = {}


def _bridge_source(name: str) -> str:
    return (_BRIDGE_SHARED / name).read_text(encoding="utf-8")


class _Injected(ast.NodeTransformer):
    """Undo the one declared difference: how the function reaches MPFB.

    Applied to the **bridge** side only. The fragment is compared as written,
    so a divergence can never be normalised into agreement from that direction.
    """

    def __init__(self, sibling_functions: set[str]) -> None:
        self.sibling_functions = sibling_functions
        self.injected: str | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # noqa: N802
        arguments = node.args.args
        if arguments and arguments[0].arg in _INJECTED_PARAMETERS:
            self.injected = arguments[0].arg
            node.args.args = arguments[1:]
            node.body = _without_unpacking(node.body, self.injected)
        node = self.generic_visit(node)  # type: ignore[assignment]
        self.injected = None
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:  # noqa: N802
        self.generic_visit(node)
        if self.injected is None or not node.args:
            return node
        first = node.args[0]
        called = node.func
        if (isinstance(called, ast.Name) and called.id in self.sibling_functions
                and isinstance(first, ast.Name) and first.id == self.injected):
            node.args = node.args[1:]
        return node


def _without_unpacking(body: list[ast.stmt], injected: str) -> list[ast.stmt]:
    """Drop the leading ``X = <injected>...`` statements from a function body."""
    index = 0
    for statement in body:
        if (isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and _names_in(statement.value) == {injected}):
            index += 1
            continue
        break
    return body[index:]


def _names_in(node: ast.AST) -> set[str]:
    return {found.id for found in ast.walk(node) if isinstance(found, ast.Name)}


def _strip_docstrings(node: ast.AST) -> ast.AST:
    """Remove every docstring, so prose may differ where code may not.

    The two copies address different readers - one is executed inside a
    generated program, the other is add-on code - and their docstrings say so.
    What must not differ is what they do.
    """
    for candidate in ast.walk(node):
        if not isinstance(candidate, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            continue
        body = candidate.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            candidate.body = body[1:] or [ast.Pass()]
    return node


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _constants(tree: ast.Module) -> dict[str, ast.expr]:
    """Module-level ``NAME = <literal>`` assignments, by name.

    Literals only. A fragment's ``TARGET_INDEX = build_target_index()`` is a
    computation run at import, which is the thing a bridge module deliberately
    does not do, so it is not a constant and is not compared as one.
    """
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            ast.literal_eval(node.value)
        except (ValueError, SyntaxError, TypeError):
            continue
        found[target.id] = node.value
    return found


def _normalised_bridge(tree: ast.Module) -> ast.Module:
    transformer = _Injected(set(_functions(tree)))
    return ast.fix_missing_locations(transformer.visit(tree))


class FragmentDriftTests(unittest.TestCase):
    """Each migrated fragment against the bridge module that replaced it."""

    def _pair(self, fragment: str) -> tuple[ast.Module, ast.Module]:
        left = _strip_docstrings(ast.parse(codegen.read_shared(fragment)))
        right = _strip_docstrings(ast.parse(_bridge_source(MIGRATED_FRAGMENTS[fragment])))
        return (left, _normalised_bridge(right))  # type: ignore[arg-type]

    def test_the_table_names_fragments_that_exist_on_both_sides(self) -> None:
        available = set(codegen.shared_names())
        for fragment, module in MIGRATED_FRAGMENTS.items():
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, available)
                self.assertTrue((_BRIDGE_SHARED / module).is_file(),
                                "{} has no bridge module yet".format(fragment))

    def test_something_was_actually_compared(self) -> None:
        # The vacuity guard, for the reason test_reference_drift.py has one: a
        # check that passes because it parsed nothing is worse than no check.
        self.assertTrue(MIGRATED_FRAGMENTS, "no fragment has migrated, so nothing is checked")
        for fragment in MIGRATED_FRAGMENTS:
            with self.subTest(fragment=fragment):
                left, _right = self._pair(fragment)
                self.assertTrue(_functions(left), "{} defines no functions".format(fragment))

    def test_every_function_agrees_with_its_bridge_module(self) -> None:
        for fragment in MIGRATED_FRAGMENTS:
            left, right = self._pair(fragment)
            bridge_functions = _functions(right)
            uncomparable = UNCOMPARABLE.get(fragment, {})
            for name, node in _functions(left).items():
                if name in uncomparable:
                    continue
                with self.subTest(fragment=fragment, function=name):
                    self.assertIn(name, bridge_functions,
                                  "the bridge module has no {}()".format(name))
                    self.assertEqual(
                        ast.unparse(node), ast.unparse(bridge_functions[name]),
                        "{}'s {}() has drifted from the bridge module's".format(fragment, name))

    def test_every_constant_agrees_with_its_bridge_module(self) -> None:
        for fragment in MIGRATED_FRAGMENTS:
            left, right = self._pair(fragment)
            bridge_constants = _constants(right)
            uncomparable = UNCOMPARABLE.get(fragment, {})
            for name, node in _constants(left).items():
                if name in uncomparable:
                    continue
                with self.subTest(fragment=fragment, constant=name):
                    self.assertIn(name, bridge_constants,
                                  "the bridge module has no {}".format(name))
                    self.assertEqual(ast.literal_eval(node),
                                     ast.literal_eval(bridge_constants[name]),
                                     "{}'s {} has drifted".format(fragment, name))

    def test_nothing_in_the_fragment_is_silently_left_out(self) -> None:
        # The claim that makes the two tests above mean something: every name
        # the fragment defines is either compared or named as uncomparable.
        for fragment in MIGRATED_FRAGMENTS:
            left, right = self._pair(fragment)
            uncomparable = set(UNCOMPARABLE.get(fragment, {}))
            defined = set(_functions(left)) | set(_constants(left))
            compared = (set(_functions(right)) | set(_constants(right))) & defined
            with self.subTest(fragment=fragment):
                self.assertEqual(
                    defined - compared - uncomparable, set(),
                    "{}: these are neither compared nor declared uncomparable".format(fragment))

    def test_the_uncomparable_list_is_asserted_rather_than_consulted(self) -> None:
        # A name listed as uncomparable that turns out to compare cleanly fails
        # here, so the list cannot rot into a suppression file. Each entry also
        # has to carry a reason somebody wrote down.
        for fragment, entries in UNCOMPARABLE.items():
            left, right = self._pair(fragment)
            bridge_functions = _functions(right)
            for name, reason in entries.items():
                with self.subTest(fragment=fragment, name=name):
                    self.assertTrue(reason.strip(), "an uncomparable name needs a reason")
                    node = _functions(left).get(name)
                    if node is None or name not in bridge_functions:
                        continue
                    self.assertNotEqual(
                        ast.unparse(node), ast.unparse(bridge_functions[name]),
                        "{}() compares cleanly now; remove it from UNCOMPARABLE".format(name))


if __name__ == "__main__":
    unittest.main()
