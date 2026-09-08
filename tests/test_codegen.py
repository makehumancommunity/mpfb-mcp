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

# Every payload for a tool that changes a character, and therefore every payload
# that owes its caller the uniform ``performed`` flag. Written out rather than
# derived, so that adding a mutating tool without the flag fails here instead of
# quietly agreeing with itself.
MUTATING_PAYLOADS = (
    "add_asset.py",
    "add_rig.py",
    "create_human.py",
    "generate_rigify_rig.py",
    "refit_human.py",
    "remove_asset.py",
    "set_asset_material.py",
    "set_macro_details.py",
    "set_skin.py",
    "set_targets.py",
    "symmetrize_targets.py",
)

# Every payload that refits, and therefore every payload that has to know when
# HumanService.refit() would silently leave the rig behind. Written out for the
# same reason as the list above: a fifth refitting payload that re-derives the
# condition should fail here rather than agree with the other four until one of
# them is edited.
REFITTING_PAYLOADS = (
    "refit_human.py",
    "set_macro_details.py",
    "set_targets.py",
    "symmetrize_targets.py",
)

# The two payloads that read a modeling category's slider value: one reports it,
# the other acts on it. That they agree is asserted against a real fixture in
# tests/test_symmetrize_targets.py; that neither has a second implementation to
# disagree with is asserted here.
CATEGORY_READING_PAYLOADS = (
    "get_target_stack.py",
    "symmetrize_targets.py",
)


class PayloadFileTests(unittest.TestCase):
    def test_there_is_a_payload_for_each_implemented_tool(self) -> None:
        self.assertEqual(
            codegen.payload_names(),
            ["add_asset.py", "add_rig.py", "create_human.py", "generate_rigify_rig.py",
             "get_macro_details.py", "get_object_info.py", "get_status.py",
             "get_target_stack.py", "list_asset_materials.py", "list_assets.py",
             "list_objects.py", "list_rigs.py", "list_targets.py", "refit_human.py",
             "remove_asset.py", "set_asset_material.py", "set_macro_details.py",
             "set_skin.py", "set_targets.py", "symmetrize_targets.py"])

    def test_shared_fragments_are_the_ones_expected(self) -> None:
        # A short list on purpose: a fragment exists only where two or more
        # payloads model the same concept, and a growing list is a sign the
        # seam is being used for ordinary tool code.
        self.assertEqual(
            codegen.shared_names(),
            ["asset_sections.py", "modifier_reading.py", "performed.py",
             "refit_blocker.py", "rig_lookup.py", "target_categories.py"])

    def test_every_mutating_payload_stamps_the_performed_flag(self) -> None:
        # The uniform "it happened" flag is the one thing every mutating tool
        # has to report under the same name, so the check that it is reported
        # at all belongs here rather than eleven times over.
        for name in MUTATING_PAYLOADS:
            with self.subTest(payload=name):
                self.assertIn("with_performed(result,", codegen.read_payload(name))

    def test_no_read_only_payload_stamps_it(self) -> None:
        # The other half of the same claim: a read-only tool changes nothing,
        # so "performed" would be a field with no meaning rather than a
        # uniformly false one.
        for name in codegen.payload_names():
            if name in MUTATING_PAYLOADS:
                continue
            with self.subTest(payload=name):
                self.assertNotIn("with_performed", codegen.read_payload(name))

    def test_every_payload_compiles_on_its_own(self) -> None:
        for name in codegen.payload_names():
            with self.subTest(payload=name):
                compile(codegen.read_payload(name), name, "exec")

    def test_every_shared_fragment_compiles_on_its_own(self) -> None:
        # Nothing imports these either, so a syntax error would otherwise
        # surface only inside Blender - and in three tools at once.
        for name in codegen.shared_names():
            with self.subTest(shared=name):
                compile(codegen.read_shared(name), name, "exec")

    def test_no_payload_contains_substitution_points(self) -> None:
        # Parameters arrive as data, so a payload never has anything formatted
        # into it - and therefore never needs escaped newlines or doubled braces.
        for name in codegen.payload_names() + codegen.shared_names():
            with self.subTest(source_file=name):
                if name in codegen.payload_names():
                    source = codegen.read_payload(name)
                else:
                    source = codegen.read_shared(name)
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
            ("create_human.py", "raising", ()),
            ("get_object_info.py", "raising", ()),
            ("get_status.py", "non_raising", ()),
            ("list_assets.py", "raising", ()),
            ("list_objects.py", "raising", ()),
            ("list_rigs.py", "raising", ("rig_lookup.py",)),
            ("add_rig.py", "raising", ("rig_lookup.py",)),
            ("generate_rigify_rig.py", "raising", ()),
            ("list_targets.py", "raising", ()),
            ("get_macro_details.py", "raising", ()),
            ("set_macro_details.py", "raising", ("refit_blocker.py",)),
            ("refit_human.py", "raising", ("refit_blocker.py",)),
            ("get_target_stack.py", "raising",
             ("target_categories.py", "modifier_reading.py")),
            ("set_targets.py", "raising",
             ("target_categories.py", "refit_blocker.py")),
            ("symmetrize_targets.py", "raising",
             ("target_categories.py", "modifier_reading.py", "refit_blocker.py")),
            ("add_asset.py", "raising", ("asset_sections.py",)),
            ("remove_asset.py", "raising", ()),
            ("set_skin.py", "raising", ("asset_sections.py",)),
            ("set_asset_material.py", "raising", ()),
            ("list_asset_materials.py", "raising", ()),
        )
        for name, bootstrap, shared in payloads:
            with self.subTest(payload=name):
                compile(
                    codegen.assemble(name, bootstrap=bootstrap, shared=list(shared)),
                    "<generated>", "exec")

    def test_seam_comment_names_the_payload_file(self) -> None:
        # What makes a line number reported from inside Blender traceable back
        # to a file: the payload starts at a known, labelled offset. The marker
        # has a second reader - observability parses the tool's name out of it,
        # which is why send_code() needs no extra argument - and the other half
        # of that coupling is pinned in tests/test_observability.py.
        source = codegen.assemble("get_status.py", bootstrap="non_raising")

        self.assertIn("# --- payload: get_status.py ---", source)
        marker, _sep, after = source.partition("# --- payload: get_status.py ---\n")
        self.assertTrue(marker)
        self.assertEqual(after, codegen.read_payload("get_status.py"))

    def test_shared_fragment_is_placed_between_the_prelude_and_the_payload(self) -> None:
        # The order is what lets a payload simply call a fragment's functions,
        # and what lets a fragment read PARAMS if it ever needs to.
        source = codegen.assemble(
            "set_targets.py", shared=["target_categories.py"], params={"name": "Human"})

        prelude_at = source.index("PARAMS = json.loads")
        shared_at = source.index("# --- shared: target_categories.py ---")
        payload_at = source.index("# --- payload: set_targets.py ---")
        self.assertLess(prelude_at, shared_at)
        self.assertLess(shared_at, payload_at)

        between = source[shared_at:payload_at]
        _marker, _sep, fragment = between.partition(
            "# --- shared: target_categories.py ---\n")
        self.assertEqual(fragment, codegen.read_shared("target_categories.py") + "\n")

    def test_fragments_are_concatenated_in_the_order_given(self) -> None:
        source = codegen.assemble(
            "set_targets.py",
            shared=["target_categories.py", "target_categories.py"])

        self.assertEqual(source.count("# --- shared: target_categories.py ---"), 2)

    def test_a_payload_with_no_fragments_is_assembled_exactly_as_before(self) -> None:
        # The seam machinery must not change what an existing tool sends.
        self.assertEqual(
            codegen.assemble("get_status.py", bootstrap="non_raising"),
            codegen.assemble("get_status.py", bootstrap="non_raising", shared=[]))
        self.assertNotIn(
            "# --- shared:", codegen.assemble("get_status.py", bootstrap="non_raising"))


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


class PerformedFragmentTests(unittest.TestCase):
    """``with_performed()`` from codegen/shared/performed.py, run directly.

    The fragment is the one that binds nothing from the bootstrap and touches
    no ``bpy``, so it can be executed here rather than through a payload inside
    a stub Blender. That is the point of testing the two guards in the place
    they live: eleven payloads rely on them, and none of the eleven should have
    to re-establish that a refusal is never "performed".
    """

    def setUp(self) -> None:
        namespace: dict = {}
        exec(codegen.read_shared("performed.py"), namespace)  # noqa: S102
        self.with_performed = namespace["with_performed"]

    def test_the_answer_is_stamped_in_place_and_returned(self) -> None:
        answer = {"added": True}
        self.assertIs(self.with_performed(answer, True), answer)
        self.assertEqual(answer, {"added": True, "performed": True})

    def test_the_flag_is_a_real_bool_whatever_the_verb_is(self) -> None:
        # Several verbs are lists - "applied" holds one entry per change - and a
        # caller branching on the flag should not have to know which.
        for done, expected in ((True, True), (False, False), ([], False),
                               ([{"target": "x"}], True), (None, False), (0, False)):
            with self.subTest(done=done):
                answer = self.with_performed({}, done)
                self.assertIs(answer["performed"], expected)

    def test_a_refusal_is_never_performed(self) -> None:
        # Both guards, against a "done" that says otherwise: a payload that
        # stamps the flag from its verb at the bottom of the file must not be
        # able to claim a refusal succeeded.
        self.assertIs(
            self.with_performed({"found": False, "ready": False}, True)["performed"], False)
        self.assertIs(
            self.with_performed({"found": True, "ready": False}, True)["performed"], False)

    def test_an_answer_carrying_neither_key_is_taken_at_its_word(self) -> None:
        # create_human's answer has no found/ready: it either creates a
        # character or raises, and a raise never reaches this function.
        self.assertIs(self.with_performed({"object_name": "Human"}, True)["performed"], True)


class RefitBlockerFragmentTests(unittest.TestCase):
    """``rig_refit_is_blocked()`` from codegen/shared/refit_blocker.py.

    Executed directly, with a stub standing in for ObjectService: the function
    asks MPFB two questions and combines the answers, so a stub that can answer
    them is the whole of the Blender it needs.

    The four payloads that refit each phrase their own sentence about this
    condition - one reports a refit that has happened, three predict one that
    has not - so what has to be pinned centrally is that all four *ask* rather
    than decide, which the delegation test below does. Each payload's own tests
    still cover its wording and its behaviour.
    """

    def setUp(self) -> None:
        test = self

        class StubObjectService:
            @staticmethod
            def object_is_generated_rigify_rig(rig):
                # Rigify's own answer is its rig_id string rather than a bool,
                # which is why only its truthiness may be relied on.
                return rig.get("rig_id")

            @staticmethod
            def find_rigify_metarig_by_rig(rig):
                test.metarig_lookups.append(rig)
                return rig.get("metarig")

        self.metarig_lookups: list = []
        namespace: dict = {"_MPFB_SERVICES": {"ObjectService": StubObjectService}}
        exec(codegen.read_shared("refit_blocker.py"), namespace)  # noqa: S102
        self.rig_refit_is_blocked = namespace["rig_refit_is_blocked"]

    def test_an_unrigged_character_is_not_blocked(self) -> None:
        # The ordinary case, and the reason every call site may ask before it
        # has established that there is a rig at all.
        self.assertIs(self.rig_refit_is_blocked(None), False)
        self.assertEqual(self.metarig_lookups, [])

    def test_an_ordinary_rig_is_never_mistaken_for_a_generated_one(self) -> None:
        self.assertIs(self.rig_refit_is_blocked({"name": "Human.rig"}), False)
        self.assertEqual(self.metarig_lookups, [])

    def test_a_generated_rigify_rig_with_a_metarig_is_not_blocked(self) -> None:
        rig = {"name": "RIG-human", "rig_id": "abc123", "metarig": {"name": "metarig"}}
        self.assertIs(self.rig_refit_is_blocked(rig), False)

    def test_a_generated_rigify_rig_without_a_metarig_is_blocked(self) -> None:
        rig = {"name": "RIG-human", "rig_id": "abc123", "metarig": None}
        self.assertIs(self.rig_refit_is_blocked(rig), True)

    def test_every_refitting_payload_asks_rather_than_decides(self) -> None:
        # The drift check. A payload that tests object_is_generated_rigify_rig()
        # itself has a second copy of the condition, which is the failure the
        # fragment exists to prevent: one tool reporting a refit that another
        # tool, over the same character, reports as impossible.
        for name in REFITTING_PAYLOADS:
            with self.subTest(payload=name):
                source = codegen.read_payload(name)
                self.assertIn("rig_refit_is_blocked(rig)", source)
                self.assertNotIn("object_is_generated_rigify_rig", source)
                self.assertNotIn("find_rigify_metarig_by_rig", source)


class ModifierReadingFragmentTests(unittest.TestCase):
    """``modifier_reading()`` from codegen/shared/modifier_reading.py.

    Executed directly over a hand-written category and a dict of shape keys.
    What it gets from the caller is the pair of lookups, so the interesting
    cases are the ones where the two answers differ from each other: an opposed
    category reads its negative target back negated, and a target that is on the
    mesh under an encoded name is found by ``present`` and by ``value_of`` alike
    or not at all.
    """

    def setUp(self) -> None:
        namespace: dict = {
            "category_is_opposed": lambda category: bool(category.get("opposed")),
            "target_names_for": lambda category, side, polarity: category.get(
                side + "-" + polarity, ""),
        }
        exec(codegen.read_shared("modifier_reading.py"), namespace)  # noqa: S102
        self.modifier_reading = namespace["modifier_reading"]

    def reading(self, category, side, stack):
        return self.modifier_reading(
            category, side,
            lambda name: bool(name) and name in stack,
            lambda name: stack.get(name, 0.0))

    def test_an_opposed_category_reads_its_negative_target_negated(self) -> None:
        category = {"opposed": True,
                    "left-positive": "l-arm-incr", "left-negative": "l-arm-decr"}
        self.assertEqual(self.reading(category, "left", {"l-arm-incr": 0.4}), 0.4)
        self.assertEqual(self.reading(category, "left", {"l-arm-decr": 0.25}), -0.25)

    def test_the_positive_target_wins_when_both_are_somehow_present(self) -> None:
        # _get_opposed_modifier_value()'s rule. Both present at once is a state
        # MPFB's own writes never produce, but a hand-edited .blend can.
        category = {"opposed": True,
                    "left-positive": "l-arm-incr", "left-negative": "l-arm-decr"}
        self.assertEqual(
            self.reading(category, "left", {"l-arm-incr": 0.4, "l-arm-decr": 0.25}), 0.4)

    def test_a_category_with_neither_target_on_the_mesh_reads_zero(self) -> None:
        # The ordinary case for all but a handful of several hundred categories.
        category = {"opposed": True,
                    "left-positive": "l-arm-incr", "left-negative": "l-arm-decr"}
        self.assertEqual(self.reading(category, "left", {}), 0.0)

    def test_an_unopposed_category_reads_its_one_target(self) -> None:
        category = {"opposed": False, "unsided-positive": "chin-triangle"}
        self.assertEqual(
            self.reading(category, "unsided", {"chin-triangle": 0.7}), 0.7)
        self.assertEqual(self.reading(category, "unsided", {}), 0.0)

    def test_a_category_naming_no_target_for_this_side_reads_zero(self) -> None:
        # target_names_for() answers "" for a side a category does not have,
        # and an empty name must never be looked up as if it were one.
        category = {"opposed": True, "left-positive": "", "left-negative": ""}
        self.assertEqual(self.reading(category, "left", {"": 0.9}), 0.0)

    def test_both_readers_are_the_callers_own(self) -> None:
        # The reconciliation itself: the rule is here, finding a value is not.
        # mpfb_get_target_stack answers from a snapshot and
        # mpfb_symmetrize_targets from key_blocks as they stand, and the rule
        # cannot tell the difference.
        category = {"opposed": True,
                    "left-positive": "l-arm-incr", "left-negative": "l-arm-decr"}
        asked: list = []
        value = self.modifier_reading(
            category, "left",
            lambda name: asked.append(("present", name)) or name == "l-arm-decr",
            lambda name: asked.append(("value_of", name)) or 0.25)

        self.assertEqual(value, -0.25)
        self.assertEqual(asked, [("present", "l-arm-incr"), ("present", "l-arm-decr"),
                                 ("value_of", "l-arm-decr")])

    def test_neither_reading_payload_keeps_an_implementation_of_its_own(self) -> None:
        # The drift check, on the rule's signature move: reading a negative
        # target back negated is what a second implementation would get subtly
        # wrong, and a payload that still does it here has one.
        for name in CATEGORY_READING_PAYLOADS:
            with self.subTest(payload=name):
                source = codegen.read_payload(name)
                self.assertIn("modifier_reading(", source)
                self.assertNotIn("return -", source)


if __name__ == "__main__":
    unittest.main()
