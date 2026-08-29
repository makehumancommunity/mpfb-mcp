# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for code assembly: the payload files themselves, bootstrap selection,
and the parameter prelude.

The payload files are never imported by this package, so nothing would notice a
syntax error in one of them until it reached Blender - hence a test that
compiles every payload on its own. The prelude tests assert on *values* after
executing the generated source rather than on its text, since carrying
parameters as data instead of interpolated source is exactly what is being
checked.

Run with::

    python -m unittest tests.test_codegen -v
"""

__all__ = ()

import unittest

from mpfbmcp import codegen


class PayloadFileTests(unittest.TestCase):
    def test_there_is_a_payload_for_each_implemented_tool(self) -> None:
        self.assertEqual(
            codegen.payload_names(),
            ["create_human.py", "get_object_info.py", "get_status.py", "list_objects.py"])

    def test_every_payload_compiles_on_its_own(self) -> None:
        for name in codegen.payload_names():
            with self.subTest(payload=name):
                compile(codegen.read_payload(name), name, "exec")

    def test_no_payload_contains_substitution_points(self) -> None:
        # Parameters arrive as data, so a payload never has anything formatted
        # into it - and therefore never needs escaped newlines or doubled braces.
        for name in codegen.payload_names():
            with self.subTest(payload=name):
                source = codegen.read_payload(name)
                self.assertNotIn("{}", source)
                self.assertNotIn("{{", source)
                self.assertNotIn("\\n", source)


class AssembleTests(unittest.TestCase):
    def test_raising_bootstrap_is_the_default(self) -> None:
        source = codegen.assemble("create_human.py", params={"scale": 0.1})

        self.assertEqual(source, codegen.assemble(
            "create_human.py", bootstrap="raising", params={"scale": 0.1}))
        self.assertIn("raise RuntimeError", source)
        self.assertIn("_MPFB_SERVICES", source)

    def test_non_raising_bootstrap_classifies_instead_of_failing(self) -> None:
        source = codegen.assemble("get_status.py", bootstrap="non_raising")

        self.assertNotIn("raise RuntimeError", source)
        self.assertIn("_mpfb_state", source)

    def test_unknown_bootstrap_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            codegen.assemble("get_status.py", bootstrap="silent")

    def test_assembled_source_compiles(self) -> None:
        payloads = (
            ("create_human.py", "raising"),
            ("get_object_info.py", "raising"),
            ("get_status.py", "non_raising"),
            ("list_objects.py", "raising"),
        )
        for name, bootstrap in payloads:
            with self.subTest(payload=name):
                compile(codegen.assemble(name, bootstrap=bootstrap), "<generated>", "exec")

    def test_seam_comment_names_the_payload_file(self) -> None:
        # What makes a line number reported from inside Blender traceable back
        # to a file: the payload starts at a known, labelled offset.
        source = codegen.assemble("get_status.py", bootstrap="non_raising")

        self.assertIn("# --- payload: get_status.py ---", source)
        marker, _sep, after = source.partition("# --- payload: get_status.py ---\n")
        self.assertTrue(marker)
        self.assertEqual(after, codegen.read_payload("get_status.py"))


class ParameterPreludeTests(unittest.TestCase):
    """Executes the assembled prelude and inspects what PARAMS ended up as."""

    def _params_after_exec(self, params) -> dict:
        # Everything up to the seam, which is the non-raising bootstrap (safe to
        # run anywhere: with no MPFB loaded it just classifies) plus the prelude.
        source = codegen.assemble("get_status.py", bootstrap="non_raising", params=params)
        prelude, _sep, _payload = source.partition("# --- payload:")
        namespace: dict = {}
        exec(prelude, namespace)  # noqa: S102
        return namespace["PARAMS"]

    def test_params_round_trip(self) -> None:
        params = {
            "scale": 0.1,
            "macro_detail_dict": {"gender": 1.0, "race": {"asian": 0.33}},
            "flag": True,
            "nothing": None,
            "names": ["a", "b"],
        }

        self.assertEqual(self._params_after_exec(params), params)

    def test_params_is_always_bound_even_without_arguments(self) -> None:
        # get_status takes none, but its payload must still be able to name PARAMS.
        self.assertEqual(self._params_after_exec(None), {})

    def test_hostile_string_survives_as_data_rather_than_code(self) -> None:
        # The reason parameters are injected as data at all: this is a system
        # whose whole job is to exec() the source it builds, so a value must
        # never be able to alter the structure of the generated program.
        hostile = "'\"\\\n\"\"\" \nimport os\nos.system('boom')\n#"
        params = {"asset_name": hostile}

        self.assertEqual(self._params_after_exec(params), params)

    def test_hostile_string_does_not_appear_verbatim_in_the_source(self) -> None:
        hostile = 'x"""\nresult = "pwned"\n'
        source = codegen.assemble(
            "create_human.py", params={"asset_name": hostile})

        self.assertNotIn(hostile, source)
        compile(source, "<generated>", "exec")


if __name__ == "__main__":
    unittest.main()
