# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for mpfbmcp.arguments, the shape validators every tool calls, and the
refusal of an argument no tool declares.

Entirely on this side of the socket, so tested here and directly, under
[the exception for what is entirely on this side](../specifications/testing.md#the-exception-what-is-entirely-on-this-side-of-the-socket).
Each validator used to be a private copy in the tool that called it, and the
tool tests assert that a bad argument raises ``ValueError`` - almost never what
it says. So **the sentences are pinned here**, word for word, including the
parts a caller supplies (the argument's name, a hint, which asset and why), because
those are the part of a refusal an agent reads to decide what to do next.
FR 036's ``tool_refusals.py`` proved the move changed none of them; these keep
it that way.

Run with::

    python -m unittest tests.test_arguments -v
"""

from __future__ import annotations

__all__ = ()

import unittest
from unittest import mock

from mpfbmcp import arguments


class ValidatedSubjectTests(unittest.TestCase):
    def test_omitted_means_the_active_object(self) -> None:
        self.assertIsNone(arguments.validated_subject(None))

    def test_a_name_is_returned_as_given(self) -> None:
        self.assertEqual(arguments.validated_subject(" Human "), " Human ")

    def test_not_a_string(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_subject(7)
        self.assertEqual(str(raised.exception), "name must be a string or omitted, got 7")

    def test_empty_is_not_omitted(self) -> None:
        for value in ("", "   "):
            with self.assertRaises(ValueError) as raised:
                arguments.validated_subject(value)
            self.assertEqual(
                str(raised.exception),
                "name must not be empty or whitespace; omit it to use the active object")

    def test_the_argument_name_is_the_callers(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_subject("", "subject")
        self.assertTrue(str(raised.exception).startswith("subject must not be empty"))


class ValidatedAssetNameTests(unittest.TestCase):
    def test_a_name_is_returned_as_given(self) -> None:
        self.assertEqual(arguments.validated_asset_name("Hat", "x", "y"), "Hat")

    def test_required_so_none_is_refused(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_asset_name(None, "x", "y")
        self.assertEqual(str(raised.exception), "name must be a string, got None")

    def test_empty_says_which_asset_and_why(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_asset_name(
                " ", "the asset to remove", "It is required: this tool deletes an object.")
        self.assertEqual(
            str(raised.exception),
            "name must be the Blender object name of the asset to remove, as mpfb_list_objects "
            "or mpfb_add_asset reports it. It is required: this tool deletes an object.")


class IsFiniteNumberTests(unittest.TestCase):

    def test_ints_and_floats_are_numbers(self):
        for value in (0, -3, 1.5, -0.0, 1e300):
            with self.subTest(value=value):
                self.assertTrue(arguments.is_finite_number(value))

    def test_a_bool_nan_infinity_or_text_is_not(self):
        for value in (True, False, float("nan"), float("inf"), -float("inf"), "1", None, [1]):
            with self.subTest(value=value):
                self.assertFalse(arguments.is_finite_number(value))


class ValidatedFlagTests(unittest.TestCase):
    def test_a_bool_is_returned(self) -> None:
        self.assertIs(arguments.validated_flag(False, "refresh"), False)
        self.assertIs(arguments.validated_flag(True, "refresh"), True)

    def test_truthiness_is_not_enough(self) -> None:
        for value in ("false", "true", 0, 1, None):
            with self.assertRaises(ValueError) as raised:
                arguments.validated_flag(value, "refit")
            self.assertEqual(str(raised.exception),
                             "refit must be a bool, got {!r}".format(value))


class ValidatedCountTests(unittest.TestCase):
    def test_zero_and_a_positive_int_pass(self) -> None:
        self.assertEqual(arguments.validated_count(0, "offset"), 0)
        self.assertEqual(arguments.validated_count(5, "limit", 10), 5)

    def test_a_bool_is_not_an_int_here(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_count(True, "limit", 10)
        self.assertEqual(str(raised.exception), "limit must be an int, got True")

    def test_negative(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_count(-1, "offset")
        self.assertEqual(str(raised.exception), "offset must not be negative, got -1")

    def test_above_the_ceiling(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_count(11, "limit", 10)
        self.assertEqual(str(raised.exception), "limit must be at most 10, got 11")

    def test_no_ceiling_by_default(self) -> None:
        self.assertEqual(arguments.validated_count(10 ** 9, "subdiv_levels"), 10 ** 9)


class ValidatedTextTests(unittest.TestCase):
    def test_omitted_and_given(self) -> None:
        self.assertIsNone(arguments.validated_text(None, "pack", "hint"))
        self.assertEqual(arguments.validated_text(" a ", "pack", "hint"), " a ",
                         "returned as given; the one tool that strips does it itself")

    def test_not_a_string(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_text(["x"], "section", "hint")
        self.assertEqual(str(raised.exception),
                         "section must be a string or omitted, got ['x']")

    def test_empty_carries_the_callers_hint(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_text("", "section", "omit it to cover every section")
        self.assertEqual(str(raised.exception),
                         "section must not be empty or whitespace; omit it to cover every section")


class ValidatedBodyPartsTests(unittest.TestCase):
    def test_omitted_means_the_default(self) -> None:
        self.assertIsNone(arguments.validated_body_parts(None))

    def test_a_list_is_returned_as_given_vocabulary_unchecked(self) -> None:
        self.assertEqual(arguments.validated_body_parts(["face", "elbows"]), ["face", "elbows"])

    def test_not_a_list(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_body_parts("left_arm")
        self.assertEqual(str(raised.exception),
                         "body_parts must be a list of strings or omitted, got 'left_arm'")

    def test_empty_is_not_omitted(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_body_parts([])
        self.assertEqual(str(raised.exception),
                         "body_parts must not be empty; omit it for the default body parts")

    def test_an_entry_that_is_not_a_name(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_body_parts(["left_arm", " "])
        self.assertEqual(str(raised.exception),
                         "body_parts[1] must be a non-empty string, got ' '")

    def test_a_repeated_name(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_body_parts(["face", "torso", "face"])
        self.assertEqual(str(raised.exception), "body_parts names face more than once")


class ValidatedNamesTests(unittest.TestCase):
    """The rule behind body_parts and roles, worded with each argument's own name."""

    def test_omitted_means_the_default(self) -> None:
        self.assertIsNone(arguments.validated_names(None, "roles", "every role"))

    def test_a_list_is_returned_as_given_vocabulary_unchecked(self) -> None:
        self.assertEqual(arguments.validated_names(["pole", "elbow"], "roles", "every role"),
                         ["pole", "elbow"])

    def test_not_a_list(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_names("pole", "roles", "every role")
        self.assertEqual(str(raised.exception),
                         "roles must be a list of strings or omitted, got 'pole'")

    def test_empty_names_what_omitting_it_means(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_names([], "roles", "every role")
        self.assertEqual(str(raised.exception), "roles must not be empty; omit it for every role")

    def test_an_entry_that_is_not_a_name(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_names(["pole", 3], "roles", "every role")
        self.assertEqual(str(raised.exception), "roles[1] must be a non-empty string, got 3")

    def test_a_repeated_name(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.validated_names(["tweak", "pole", "tweak"], "roles", "every role")
        self.assertEqual(str(raised.exception), "roles names tweak more than once")


class RefuseUndeclaredTests(unittest.TestCase):
    def test_declared_arguments_pass(self) -> None:
        arguments.refuse_undeclared("mpfb_list_docs", {"topic", "keyword"}, {"topic": "x"})
        arguments.refuse_undeclared("mpfb_get_status", frozenset(), {})

    def test_one_unknown_is_named_beside_what_is_accepted(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.refuse_undeclared("mpfb_list_docs", {"topic", "keyword"}, {"topc": "x"})
        self.assertEqual(str(raised.exception),
                         "Unknown argument 'topc'. This tool accepts keyword, topic.")

    def test_several_unknowns_are_sorted_and_plural(self) -> None:
        with self.assertRaises(ValueError) as raised:
            arguments.refuse_undeclared("mpfb_get_status", frozenset(), {"x": 1, "a": 2})
        self.assertEqual(str(raised.exception),
                         "Unknown arguments 'a', 'x'. This tool accepts no arguments.")

    def test_a_retired_spelling_names_its_replacement(self) -> None:
        retired = {"mpfb_set_face_units": {"clear_first": "mode"}}
        with mock.patch.dict(arguments.RETIRED_ARGUMENTS, retired):
            with self.assertRaises(ValueError) as raised:
                arguments.refuse_undeclared(
                    "mpfb_set_face_units", {"name", "mode"}, {"clear_first": True, "x": 1})
        self.assertEqual(str(raised.exception),
                         "Unknown arguments 'clear_first' (now called 'mode'), 'x'. "
                         "This tool accepts mode, name.")

    def test_a_spelling_retired_from_another_tool_is_only_unknown(self) -> None:
        retired = {"mpfb_set_face_units": {"clear_first": "mode"}}
        with mock.patch.dict(arguments.RETIRED_ARGUMENTS, retired):
            with self.assertRaises(ValueError) as raised:
                arguments.refuse_undeclared("mpfb_list_docs", {"topic"}, {"clear_first": True})
        self.assertEqual(str(raised.exception),
                         "Unknown argument 'clear_first'. This tool accepts topic.")


if __name__ == "__main__":
    unittest.main()
