# SPDX-License-Identifier: GPL-3.0-or-later

"""
``mpfb_refit_human``, migrated by FR 032 and therefore in three layers rather
than two (see ``tests/test_list_objects.py``, the template).

1. **The wrapper**, with ``send_code`` mocked on the seam: argument validation,
   and what the generated program binds as ``PARAMS``.
2. **The bridge path**, against ``tests/fake_bridge.py``. Thin, and it carries
   the claim this tool is the first to make: a tool naming **two** shared
   fragments sends the same request over the bridge as one naming none.
3. **The payload** against the stubs in ``tests/blender_stubs.py``. **Frozen.**
   It stays while the payload stays, because the payload is half of what
   FR 032's live comparison compares, and it is deleted with the payload when
   the generated path is retired.

What layer 3 checks is the reporting around the call, which is where this tool
adds anything at all over ``HumanService.refit()``: a missing basemesh comes
back as an answer rather than the ``ValueError`` refit() raises, and a generated
Rigify rig with no meta rig is reported rather than passed off as a successful
refit. Whether a refit visibly puts clothes back on a deformed body is exactly
what it cannot say - and that is now checked against a real MPFB in
``bridge/test/tests/ppp_mutating/refit_human_test.py``, which builds a character,
equips a garment from a redirected data root, deforms the body and refits it.

The share of this module that goes with the payload: 219 of its 372 lines, 59%
- ``GeneratedRefitHumanTests`` alone, which is within a point of the 60% rate
FR 031 measured over nine modules.

Run with::

    python -m unittest tests.test_refit_human -v
"""

__all__ = ()

import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import backend
from mpfbmcp.tools import refit_human

from tests import fake_bridge
from tests.blender_stubs import GeneratedCodeTestCase, StubHumanService, StubObject
from tests import generated_path


# These tests are about the **generated path**: they mock `backend.send_code`
# and assert about the program that reached it. FR 032 made the bridge the
# default, so saying so is now necessary rather than implied.
# See tests/generated_path.py.
setUpModule = generated_path.pin
tearDownModule = generated_path.unpin


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    refit_human.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_refit_human"]  # noqa: SLF001
    return tool.fn


class RefitHumanToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_refit_human = _register_and_get_tool()

    @mock.patch("mpfbmcp.backend.send_code")
    def test_omitted_name_is_sent_as_null(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"found": False}}

        self.mpfb_refit_human()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertEqual(_params_in(code), {"name": None})

    @mock.patch("mpfbmcp.backend.send_code")
    def test_name_is_passed_through_verbatim(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"found": True}}

        self.mpfb_refit_human("Human.rig")

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code), {"name": "Human.rig"})

    def test_blank_and_non_string_names_are_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.backend.send_code") as mock_send_code:
            for bad in ("", "   ", "\t", 1, True, ["Human"]):
                with self.subTest(name=bad):
                    with self.assertRaises(ValueError):
                        self.mpfb_refit_human(bad)
            mock_send_code.assert_not_called()


class RefitHumanOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - what was refitted, what a generated Rigify
    rig with no meta rig does to ``refit_performed``, that the caller's
    selection comes back - is checked against a real MPFB in
    ``bridge/test/tests/ppp_mutating/refit_human_test.py``.
    """

    def setUp(self) -> None:
        super().setUp()
        self.call = _register_and_get_tool()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "refit_human": fake_bridge.ok_envelope(
                "refit_human", {"found": True, "refit_performed": True, "performed": True}),
        })

    def test_the_tool_sends_the_refit_human_command(self) -> None:
        self.call()

        self.assertEqual(self.bridge.commands()[-1], "refit_human")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": None})

    def test_a_named_subject_is_passed_through_verbatim(self) -> None:
        self.call(name="Human.rigify")

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": "Human.rigify"})

    def test_neither_shared_fragment_reaches_the_bridge(self) -> None:
        # Two fragments rather than one, which is what makes this worth
        # asserting separately from `list_presets`: `shared` is a property of
        # how a program is assembled, and the bridge assembles nothing.
        self.call()

        request = self.bridge.decoded_requests()[-1]
        self.assertNotIn("shared", request)
        self.assertNotIn("refit_blocker", str(request))
        self.assertNotIn("performed", str(request["params"]))

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        for value in ("", "   ", 17):
            with self.subTest(name=value):
                with self.assertRaises(ValueError):
                    self.call(name=value)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "HumanService.refit() raised.",
                command="refit_human"))

        response = self.call()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")


class GeneratedRefitHumanTests(GeneratedCodeTestCase):
    """Runs the payload against the stub scene."""

    def build_character(self, rig=True, garments=("Shirt",), subrigs=(), **basemesh_kwargs):
        """A dressed character, parented the way MPFB parents one.

        Garments hang off the rig rather than off the basemesh when there is a
        rig, which is what refit()'s own only_children walk from the rig is
        written for.
        """
        self.rig = None
        if rig:
            self.rig = StubObject(
                "Human.rig", blender_type="ARMATURE", object_type="Skeleton")
        self.basemesh = StubObject(
            "Human", parent=self.rig, object_type="Basemesh",
            shapekeys=[("Basis", 0.0), ("$md-$ca-$fe-$yn", 1.0)], **basemesh_kwargs)
        parent = self.rig or self.basemesh
        self.garments = [
            StubObject(name, parent=parent, object_type="Clothes") for name in garments]
        self.subrigs = [
            StubObject(name, blender_type="ARMATURE", parent=parent, object_type="Subrig")
            for name in subrigs]
        self.objects = [obj for obj in [self.rig, self.basemesh] if obj]
        self.objects += self.garments + self.subrigs
        return self.objects

    def run_refit(self, name="Human", active=None):
        return self.run_payload(
            "refit_human.py", {"name": name},
            scene_objects=self.objects, active=active,
            shared=["refit_blocker.py", "performed.py"])

    def test_a_rigged_dressed_character_is_refitted(self) -> None:
        self.build_character(garments=("Shirt", "Shoes"), subrigs=("Shirt.rig",))

        result = self.run_refit()

        self.assertTrue(result["found"])
        self.assertTrue(result["ready"])
        self.assertTrue(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, ["Human"])
        self.assertEqual(sorted(result["mesh_assets"]), ["Shirt", "Shoes"])
        self.assertEqual(result["mesh_asset_count"], 2)
        self.assertEqual(result["subrigs"], ["Shirt.rig"])
        self.assertEqual(result["rig_name"], "Human.rig")

    def test_an_unrigged_character_is_refitted_and_says_so(self) -> None:
        self.build_character(rig=False)

        result = self.run_refit()

        self.assertTrue(result["refit_performed"])
        self.assertIsNone(result["rig_name"])
        self.assertEqual(result["mesh_assets"], ["Shirt"])
        self.assertIn("no rig", result["message"])

    def test_subject_resolves_from_the_rig_and_from_a_garment(self) -> None:
        for name in ("Human.rig", "Shirt"):
            with self.subTest(name=name):
                self.build_character()

                result = self.run_refit(name)

                self.assertEqual(result["subject_name"], name)
                self.assertEqual(result["basemesh_name"], "Human")
                self.assertTrue(result["refit_performed"])

    def test_active_object_is_used_when_no_name_is_given(self) -> None:
        self.build_character()

        result = self.run_refit(None, active=self.garments[0])

        self.assertEqual(result["subject_resolved_by"], "active")
        self.assertEqual(result["basemesh_name"], "Human")

    def test_no_active_object_is_an_answer(self) -> None:
        self.build_character()

        result = self.run_refit(None, active=None)

        self.assertFalse(result["found"])
        self.assertFalse(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, [])

    def test_unresolvable_name_is_an_answer(self) -> None:
        self.build_character()

        result = self.run_refit("Nonexistent")

        self.assertFalse(result["found"])
        self.assertEqual(StubHumanService.refit_calls, [])

    def test_an_object_with_no_basemesh_is_an_answer_not_a_valueerror(self) -> None:
        # refit() raises here, which is why the basemesh is resolved first.
        self.build_character()
        cube = StubObject("Cube")
        self.objects = [cube]

        result = self.run_refit("Cube")

        self.assertFalse(result["found"])
        self.assertIn("no MakeHuman basemesh", result["message"])
        self.assertEqual(StubHumanService.refit_calls, [])

    def test_edit_mode_is_an_answer(self) -> None:
        self.build_character(mode="EDIT")

        result = self.run_refit()

        self.assertTrue(result["found"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["blocked_by"], "not_object_mode")
        self.assertFalse(result["refit_performed"])
        self.assertEqual(StubHumanService.refit_calls, [])

    def test_generated_rigify_without_a_metarig_is_reported_not_claimed(self) -> None:
        # The failure refit() reports only through an operator: it refits the
        # mesh assets, silently leaves the rig, and returns.
        self.build_character(rig=False)
        rigify = StubObject("RIG-human", blender_type="ARMATURE", object_type="Skeleton",
                            rig_id="abc123")
        self.basemesh.parent = rigify
        self.garments[0].parent = rigify
        self.objects = [rigify] + self.objects

        result = self.run_refit("Human")

        self.assertEqual(StubHumanService.refit_calls, ["Human"])
        self.assertFalse(result["refit_performed"])
        self.assertIn("generated Rigify rig", result["refit_incomplete_reason"])
        self.assertIn("Meta-rig", result["message"])

    def test_generated_rigify_with_a_metarig_refits_normally(self) -> None:
        self.build_character(rig=False)
        rigify = StubObject("RIG-human", blender_type="ARMATURE", object_type="Skeleton",
                            rig_id="abc123")
        metarig = StubObject("metarig", blender_type="ARMATURE", metarig=True,
                             rigify_target_rig=rigify)
        self.basemesh.parent = rigify
        self.garments[0].parent = rigify
        self.objects = [rigify, metarig] + self.objects

        result = self.run_refit("Human")

        self.assertTrue(result["refit_performed"])
        self.assertIsNone(result["refit_incomplete_reason"])

    def test_an_ordinary_rig_is_never_mistaken_for_a_rigify_one(self) -> None:
        # object_is_generated_rigify_rig() answers with Rigify's rig_id string
        # rather than a bool, so only its truthiness may be relied on.
        self.build_character()

        result = self.run_refit()

        self.assertTrue(result["refit_performed"])
        self.assertIsNone(result["refit_incomplete_reason"])

    def test_the_previous_active_object_and_selection_are_restored(self) -> None:
        self.build_character()

        self.run_refit("Human", active=self.garments[0])

        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.garments[0])

    def test_the_previous_state_is_restored_even_when_the_refit_fails(self) -> None:
        self.build_character()
        StubHumanService.refit_raises = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            self.run_refit("Human", active=self.garments[0])

        self.assertFalse(self.basemesh.select_get())
        self.assertIs(self.last_bpy.context.view_layer.objects.active, self.garments[0])

    # --- the uniform "it happened" flag -------------------------------------

    def test_performed_is_set_from_refit_performed(self) -> None:
        # Including the case the two could most easily disagree about: a
        # generated Rigify rig with no meta rig is ready: true, refits the mesh
        # assets, and leaves the rig - which is not "performed".
        self.build_character()
        refitted = self.run_refit()
        self.assertIs(refitted["performed"], True)
        self.assertEqual(refitted["performed"], refitted["refit_performed"])

        self.build_character(rig=False)
        rigify = StubObject("RIG-human", blender_type="ARMATURE", object_type="Skeleton",
                            rig_id="abc123")
        self.basemesh.parent = rigify
        self.garments[0].parent = rigify
        self.objects = [rigify] + self.objects
        partial = self.run_refit("Human")
        self.assertTrue(partial["ready"])
        self.assertIs(partial["performed"], False)
        self.assertEqual(partial["performed"], partial["refit_performed"])

        self.build_character(mode="EDIT")
        blocked = self.run_refit()
        self.assertEqual(blocked["blocked_by"], "not_object_mode")
        self.assertIs(blocked["performed"], False)
        self.assertEqual(blocked["performed"], blocked["refit_performed"])


def _params_in(code: str) -> dict:
    """The PARAMS the generated source will bind, by executing its prelude."""
    # Cut at whichever comes first: a shared fragment or the payload. The
    # prelude sits behind the raising bootstrap, and a fragment resolves MPFB
    # services of its own, so both would fail here with no MPFB loaded - and
    # only the two lines binding PARAMS are wanted.
    prelude, _sep, _rest = code.partition("# --- shared:")
    prelude, _sep, _payload = prelude.partition("# --- payload:")
    namespace: dict = {}
    exec(prelude[prelude.index("import json"):], namespace)  # noqa: S102
    return namespace["PARAMS"]

if __name__ == "__main__":
    unittest.main()
