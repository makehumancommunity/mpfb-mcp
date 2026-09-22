# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_get_object_info tool, migrated by FR 031 and therefore in
three layers rather than two (see ``tests/test_list_objects.py``, the template).

1. **The wrapper**, with ``send_code`` mocked on the seam: argument validation,
   and what goes on the wire.
2. **The bridge path**, against ``tests/fake_bridge.py``. Thin, and deliberately
   so - nothing here asserts what MPFB answers.
3. **The payload**, ``exec()``-ed against the stubs in
   ``tests/blender_stubs.py``. **Frozen.** It stays while the payload stays,
   because the payload is half of what FR 031's live comparison compares, and
   it is deleted with the payload when the generated path is retired. Nothing
   is added to it: the stubs reproduce the MPFB behaviours the payload is
   written around - "" for an untyped object, a non-bool
   ``object_is_any_makehuman_object()``, a ``find_related_objects()`` that
   yields the subject itself - but they say nothing about the values real MPFB
   returns, and those assertions are now made against a real install in
   ``bridge/test/tests/hhh_get_object_info_test.py``.

The share of this module that goes with the payload: 409 of its 614 lines, 67%
- the stub scene and the five classes of payload tests - against a 381-line
payload with three ``asset_info`` shapes and three resolution outcomes each.
The highest rate of the three introspection tools, and the reason is the
fixture as much as the assertions: a scene of nine related objects exists only
to be looked at by a payload.

Run with::

    python -m unittest tests.test_get_object_info -v
"""

__all__ = ()

import json
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import backend
from mpfbmcp.tools import get_object_info
from tests import blender_stubs, fake_bridge
from tests.blender_stubs import GeneratedCodeTestCase, StubMaterial, StubObject
from tests import generated_path


# These tests are about the **generated path**: they mock `backend.send_code`
# and assert about the program that reached it. FR 032 made the bridge the
# default, so saying so is now necessary rather than implied.
# See tests/generated_path.py.
setUpModule = generated_path.pin
tearDownModule = generated_path.unpin

_SKIN_FRAGMENT = "young_caucasian_female/young_caucasian_female.mhmat"
_FEDORA_FRAGMENT = "fedora/fedora.mhclo"


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    get_object_info.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_get_object_info"]  # noqa: SLF001
    return tool.fn


def _params_in(code: str) -> dict:
    """The PARAMS the generated source will bind, by executing its prelude."""
    prelude, _sep, _payload = code.partition("# --- payload:")
    namespace: dict = {}
    exec(prelude[prelude.index("import json"):], namespace)  # noqa: S102
    return namespace["PARAMS"]


class GetObjectInfoToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_get_object_info = _register_and_get_tool()

    @mock.patch("mpfbmcp.backend.send_code")
    def test_omitted_name_means_the_active_object(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"found": True}}

        self.mpfb_get_object_info()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertEqual(_params_in(code), {"name": None})

    @mock.patch("mpfbmcp.backend.send_code")
    def test_name_is_passed_through_verbatim(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"found": True}}

        self.mpfb_get_object_info("Human.003")

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code), {"name": "Human.003"})

    @mock.patch("mpfbmcp.backend.send_code")
    def test_a_name_full_of_quotes_survives_as_data(self, mock_send_code: mock.Mock) -> None:
        # Parameters are carried as JSON data rather than interpolated into the
        # source, so a hostile object name cannot restructure the program.
        mock_send_code.return_value = {"status": "ok", "result": {"found": False}}
        hostile = "'\"\"\"\nresult = {}\n#"

        self.mpfb_get_object_info(hostile)

        (code,), _kwargs = mock_send_code.call_args
        self.assertEqual(_params_in(code), {"name": hostile})

    def test_blank_name_is_rejected_rather_than_treated_as_omitted(self) -> None:
        # The two come from different mistakes: answering about whatever happens
        # to be selected, when the caller believed they named something, is
        # worse than failing.
        with mock.patch("mpfbmcp.backend.send_code") as mock_send_code:
            for blank in ("", "   ", "\n"):
                with self.subTest(name=blank):
                    with self.assertRaises(ValueError):
                        self.mpfb_get_object_info(blank)
            mock_send_code.assert_not_called()

    def test_non_string_name_is_rejected_locally(self) -> None:
        with mock.patch("mpfbmcp.backend.send_code") as mock_send_code:
            with self.assertRaises(ValueError):
                self.mpfb_get_object_info(12)
            mock_send_code.assert_not_called()

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self) -> None:
        # `status` and `message` are unchanged and `error` is what a caller
        # branches on whichever transport answered.
        with mock.patch("mpfbmcp.backend.send_code",
                        return_value={"status": "error", "message": "boom"}):
            response = self.mpfb_get_object_info()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "boom")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)


class GetObjectInfoOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the three ``asset_info`` shapes, the
    relationship walk, the untyped neighbourhood, what resolves from what - is
    checked against a real MPFB in the bridge's own suite.
    """

    def setUp(self) -> None:
        super().setUp()
        self.mpfb_get_object_info = _register_and_get_tool()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_object_info": fake_bridge.ok_envelope("get_object_info", {"found": False}),
        })

    def test_the_tool_sends_the_get_object_info_command(self) -> None:
        self.mpfb_get_object_info()

        self.assertEqual(self.bridge.commands()[-1], "get_object_info")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": None})

    def test_a_name_crosses_the_wire_verbatim(self) -> None:
        self.mpfb_get_object_info("Human.body")

        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {"name": "Human.body"})

    def test_local_validation_runs_before_a_transport_is_chosen(self) -> None:
        # A blank name and an omitted one arise from different mistakes, so the
        # blank one is refused rather than treated as "use the active object" -
        # and that refusal is the tool's, not the transport's.
        for blank in ("", "   ", "\t"):
            with self.subTest(name=blank):
                with self.assertRaises(ValueError):
                    self.mpfb_get_object_info(blank)

        with self.assertRaises(ValueError):
            self.mpfb_get_object_info(12)

        self.assertEqual(self.bridge.requests, [],
                         "a locally invalid call must not be sent to any backend")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "mpfb_unavailable", "The command needs MPFB, which is not usable here.",
                command="get_object_info", state="absent"))

        response = self.mpfb_get_object_info()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "mpfb_unavailable")
        self.assertEqual(response["state"], "absent")


class _SceneTestCase(GeneratedCodeTestCase):
    """A character with a rig, two clothes items, a stray Rigify rig and a cube.

    The base of the payload layer. **Frozen**: see this module's docstring.
    """

    def setUp(self) -> None:
        super().setUp()
        self.skeleton = StubObject(
            "Human.rig", blender_type="ARMATURE", object_type="Skeleton", rig_type="default")
        self.basemesh = StubObject(
            "Human", parent=self.skeleton, object_type="Basemesh",
            material_source=_SKIN_FRAGMENT, material=StubMaterial("enhanced_skin"))
        self.fedora = StubObject(
            "Fedora", parent=self.basemesh, object_type="Clothes",
            asset_source=_FEDORA_FRAGMENT, material=StubMaterial("makeskin"))
        # Parented into the character but never linked into the scene.
        self.shirt = StubObject(
            "Shirt", parent=self.basemesh, object_type="Clothes",
            asset_source="shirt/shirt.mhclo")
        # A Rigify rig built outside MPFB, so it carries no object_type. A rig
        # MPFB generated itself would be tagged "Skeleton" (rigifyhelpers.py)
        # and land in related_objects instead - see SubjectRigifyRoleTests.
        self.generated_rig = StubObject(
            "RIG-Human", blender_type="ARMATURE", parent=self.skeleton, rig_id="abc123")
        self.cube = StubObject("Cube")
        # A typed object that exists in the file but is in no scene and is
        # related to nothing.
        self.orphan = StubObject("Orphan", object_type="Hair")

        self.scene_objects = [
            self.skeleton, self.basemesh, self.fedora, self.generated_rig, self.cube]
        self.all_objects = self.scene_objects + [self.shirt, self.orphan]

    def info(self, name=None, active=None):
        return self.run_payload(
            "get_object_info.py", {"name": name},
            scene_objects=self.scene_objects, all_objects=self.all_objects, active=active)


class SubjectResolutionTests(_SceneTestCase):
    def test_by_name(self) -> None:
        result = self.info("Human")

        self.assertTrue(result["found"])
        self.assertEqual(result["resolved_from"], "name")
        self.assertEqual(result["name"], "Human")
        self.assertTrue(result["in_current_scene"])
        self.assertEqual(result["object_type"], "Basemesh")
        self.assertEqual(result["blender_type"], "MESH")
        self.assertTrue(result["is_makehuman_object"])
        json.dumps(result)

    def test_active_object(self) -> None:
        result = self.info(active=self.fedora)

        self.assertTrue(result["found"])
        self.assertEqual(result["resolved_from"], "active_object")
        # The point of the form: an unstable subject turned into a stable name.
        self.assertEqual(result["name"], "Fedora")

    def test_no_active_object_is_an_answer_not_a_crash(self) -> None:
        # bpy.context.view_layer.objects.active is None whenever nothing is
        # active, which is the branch that raises AttributeError if missed.
        result = self.info(active=None)

        self.assertFalse(result["found"])
        self.assertEqual(result["resolved_from"], "active_object")
        self.assertIsNone(result["name"])
        self.assertIn("no object is active", result["message"])

    def test_unknown_name_is_an_answer_not_an_error(self) -> None:
        result = self.info("Nonexistent")

        self.assertFalse(result["found"])
        self.assertEqual(result["resolved_from"], "name")
        self.assertIsNone(result["name"])
        self.assertIn("Nonexistent", result["message"])

    def test_object_outside_the_current_scene_still_resolves(self) -> None:
        # Names are unique across the whole .blend, so "exists, elsewhere" is a
        # distinct answer from "no such object" - and from mpfb_list_objects,
        # which does not list it.
        result = self.info("Orphan")

        self.assertTrue(result["found"])
        self.assertFalse(result["in_current_scene"])
        self.assertEqual(result["object_type"], "Hair")
        self.assertIn("without being linked into the current scene", result["message"])

    def test_plain_blender_object_is_reported_as_one(self) -> None:
        result = self.info("Cube")

        self.assertTrue(result["found"])
        self.assertIsNone(result["object_type"])
        self.assertFalse(result["is_makehuman_object"])
        self.assertIsNone(result["asset_info"])
        self.assertEqual(result["related_objects"], [])


class SubjectRigifyRoleTests(_SceneTestCase):
    """
    rigify_role is reported for the subject, not only for untyped relatives.

    Verified against a live Blender: an agent that found a Rigify rig in some
    character's other_related_objects and then asked about it by name used to
    get strictly less back than the entry that pointed it there, plus a message
    calling it a plain Blender object.
    """

    def test_an_untyped_rigify_rig_reports_its_role_as_the_subject(self) -> None:
        result = self.info("RIG-Human")

        self.assertEqual(result["rigify_role"], "generated_rig")
        self.assertIsNone(result["object_type"])

    def test_the_subject_says_what_a_relative_entry_says_about_it(self) -> None:
        as_relative = self.info("Human")["other_related_objects"][0]
        as_subject = self.info("RIG-Human")

        self.assertEqual(as_relative["name"], as_subject["name"])
        self.assertEqual(as_relative["rigify_role"], as_subject["rigify_role"])

    def test_a_metarig_subject_is_classified_as_one(self) -> None:
        self.generated_rig.rig_id = None
        self.generated_rig.metarig = True

        self.assertEqual(self.info("RIG-Human")["rigify_role"], "metarig")

    def test_a_typed_rig_still_reports_the_role(self) -> None:
        # The commonest generated rig there is: MPFB tags the rig it produces
        # through Rigify as a Skeleton, so gating this on an absent object_type
        # would drop the field exactly where it is most wanted.
        self.skeleton.rig_id = "abc123"

        result = self.info("Human.rig")

        self.assertEqual(result["object_type"], "Skeleton")
        self.assertEqual(result["rigify_role"], "generated_rig")

    def test_ordinary_objects_report_no_role_rather_than_omitting_the_key(self) -> None:
        for name in ("Human", "Human.rig", "Cube"):
            with self.subTest(name=name):
                result = self.info(name)

                self.assertIn("rigify_role", result)
                self.assertIsNone(result["rigify_role"])

    def test_the_message_does_not_call_a_rigify_rig_a_plain_object(self) -> None:
        message = self.info("RIG-Human")["message"]

        self.assertIn("Rigify generated rig", message)
        self.assertNotIn("plain Blender object", message)

    def test_a_genuinely_plain_object_is_still_called_one(self) -> None:
        self.assertIn("plain Blender object", self.info("Cube")["message"])


class RelationshipTests(_SceneTestCase):
    def test_subject_is_excluded_from_its_own_relatives(self) -> None:
        # find_related_objects() yields the object it was asked about, first.
        names = [entry["name"] for entry in self.info("Human")["related_objects"]]

        self.assertNotIn("Human", names)
        self.assertEqual(sorted(names), ["Fedora", "Human.rig", "Shirt"])

    def test_a_relative_outside_the_scene_is_flagged_not_dropped(self) -> None:
        # get_list_of_children() walks the whole file, so a relative can sit
        # outside the scene mpfb_list_objects searched.
        by_name = {entry["name"]: entry for entry in self.info("Human")["related_objects"]}

        self.assertTrue(by_name["Fedora"]["in_current_scene"])
        self.assertFalse(by_name["Shirt"]["in_current_scene"])

    def test_untyped_relatives_are_kept_separate_and_classified(self) -> None:
        others = self.info("Human")["other_related_objects"]

        self.assertEqual([entry["name"] for entry in others], ["RIG-Human"])
        self.assertEqual(others[0]["rigify_role"], "generated_rig")
        self.assertIsNone(others[0]["object_type"])
        # A key that could only ever be null is noise, so there is none.
        self.assertNotIn("asset_info", others[0])

    def test_a_metarig_is_classified_as_one(self) -> None:
        self.generated_rig.rig_id = None
        self.generated_rig.metarig = True

        others = self.info("Human")["other_related_objects"]

        self.assertEqual(others[0]["rigify_role"], "metarig")

    def test_an_untyped_relative_that_is_not_rigify_has_no_role(self) -> None:
        self.generated_rig.rig_id = None

        others = self.info("Human")["other_related_objects"]

        self.assertIsNone(others[0]["rigify_role"])

    def test_relatives_carry_their_own_asset_info(self) -> None:
        # One call answers "what is this character wearing", rather than one
        # call per child.
        blender_stubs.StubAssetService.resolutions = {_FEDORA_FRAGMENT: "/assets/fedora/fedora.mhclo"}

        by_name = {entry["name"]: entry for entry in self.info("Human")["related_objects"]}

        self.assertEqual(by_name["Fedora"]["asset_info"]["mhclo_path"], "/assets/fedora/fedora.mhclo")
        self.assertEqual(by_name["Human.rig"]["asset_info"]["rig_type"], "default")


class AssetInfoShapeTests(_SceneTestCase):
    def test_skeleton_gets_rig_keys_only(self) -> None:
        asset_info = self.info("Human.rig")["asset_info"]

        self.assertEqual(sorted(asset_info), ["rig_definition_path", "rig_type"])
        self.assertEqual(asset_info["rig_type"], "default")

    def test_mesh_asset_gets_mhclo_keys_only(self) -> None:
        asset_info = self.info("Fedora")["asset_info"]

        self.assertEqual(
            sorted(asset_info),
            ["asset_source", "material_source", "material_type", "mhclo_path", "mhmat_path"])
        # No rig keys: a null one would read as "we looked and failed".
        self.assertNotIn("rig_type", asset_info)

    def test_basemesh_gets_material_keys_without_an_mhclo(self) -> None:
        asset_info = self.info("Human")["asset_info"]

        self.assertEqual(
            sorted(asset_info), ["material_source", "material_type", "mhmat_path"])
        self.assertEqual(asset_info["material_type"], "enhanced_skin")

    def test_a_type_outside_the_three_families_falls_through_to_an_empty_dict(self) -> None:
        # MPFB adding a type this list does not know is not an error.
        pose = StubObject("Walk", object_type="Pose")
        self.scene_objects.append(pose)
        self.all_objects.append(pose)

        result = self.info("Walk")

        self.assertTrue(result["is_makehuman_object"])
        self.assertEqual(result["asset_info"], {})

    def test_material_type_is_not_asked_of_an_armature(self) -> None:
        # identify_material() would need material slots, which an armature has
        # none of, and identify_rig() needs .data.bones, which a mesh lacks.
        self.assertNotIn("material_type", self.info("Human.rig")["asset_info"])


class AssetInfoResolutionTests(_SceneTestCase):
    def test_fragment_that_resolves_reports_both(self) -> None:
        blender_stubs.StubAssetService.resolutions = {_FEDORA_FRAGMENT: "/assets/fedora/fedora.mhclo"}

        asset_info = self.info("Fedora")["asset_info"]

        self.assertEqual(asset_info["asset_source"], _FEDORA_FRAGMENT)
        self.assertEqual(asset_info["mhclo_path"], "/assets/fedora/fedora.mhclo")

    def test_fragment_that_does_not_resolve_keeps_the_fragment(self) -> None:
        # The pack was moved or uninstalled. This is the case the pairing exists
        # for: an undifferentiated null path would hide it.
        asset_info = self.info("Fedora")["asset_info"]

        self.assertEqual(asset_info["asset_source"], _FEDORA_FRAGMENT)
        self.assertIsNone(asset_info["mhclo_path"])

    def test_no_fragment_reports_both_as_null(self) -> None:
        self.fedora.properties["GEN"]["asset_source"] = ""

        asset_info = self.info("Fedora")["asset_info"]

        self.assertIsNone(asset_info["asset_source"])
        self.assertIsNone(asset_info["mhclo_path"])

    def test_no_lookup_happens_without_a_fragment(self) -> None:
        # Resolving a fragment is an os.walk of the asset roots. The bounded
        # cost the design claims is otherwise unverifiable from this side of the
        # socket, and an unconditional walk would be invisible until someone
        # with a large asset library complained.
        # Every relative gets its own asset_info, so the whole neighbourhood has
        # to be fragment-free for this to prove anything.
        for blender_object in self.all_objects:
            blender_object.properties["GEN"]["asset_source"] = ""
            blender_object.properties["GEN"]["alternative_material"] = ""
            blender_object.properties["HUM"]["material_source"] = ""

        def explode(*args, **kwargs):
            raise AssertionError("the asset roots must not be walked without a fragment")

        with mock.patch.object(
                blender_stubs.StubAssetService, "find_asset_absolute_path", explode):
            self.info("Fedora")

    def test_a_path_object_from_mpfb_comes_out_as_a_string(self) -> None:
        # LocationService has been caught returning pathlib.Path despite a -> str
        # annotation, which fails strict_json and takes the response with it.
        blender_stubs.StubAssetService.resolutions = {
            _FEDORA_FRAGMENT: pathlib.Path("/assets/fedora/fedora.mhclo")}

        result = self.info("Fedora")

        self.assertIsInstance(result["asset_info"]["mhclo_path"], str)
        json.dumps(result)


class MaterialSourcePrecedenceTests(_SceneTestCase):
    def _subdir_for(self, fragment):
        for called_fragment, asset_subdir in blender_stubs.StubAssetService.calls:
            if called_fragment == fragment:
                return asset_subdir
        return None

    def test_basemesh_skin_resolves_against_skins(self) -> None:
        blender_stubs.StubAssetService.resolutions = {_SKIN_FRAGMENT: "/assets/skins/skin.mhmat"}

        asset_info = self.info("Human")["asset_info"]

        self.assertEqual(asset_info["material_source"], _SKIN_FRAGMENT)
        self.assertEqual(asset_info["mhmat_path"], "/assets/skins/skin.mhmat")
        self.assertEqual(self._subdir_for(_SKIN_FRAGMENT), "skins")

    def test_alternative_material_resolves_against_the_object_type(self) -> None:
        # A swap between the two subdirs is invisible in the response shape and
        # would only surface as an unresolvable path against a real library.
        self.fedora.properties["GEN"]["alternative_material"] = "red/red.mhmat"

        asset_info = self.info("Fedora")["asset_info"]

        self.assertEqual(asset_info["material_source"], "red/red.mhmat")
        self.assertEqual(self._subdir_for("red/red.mhmat"), "clothes")

    def test_the_human_property_wins_on_a_body_proxy_carrying_both(self) -> None:
        # MPFB writes the skin onto the body proxy as well, so a proxy can carry
        # both properties; the skin is the one that describes it.
        proxy = StubObject(
            "Proxy", parent=self.basemesh, object_type="Proxymeshes",
            material_source=_SKIN_FRAGMENT, alternative_material="red/red.mhmat")
        self.scene_objects.append(proxy)
        self.all_objects.append(proxy)

        asset_info = self.info("Proxy")["asset_info"]

        self.assertEqual(asset_info["material_source"], _SKIN_FRAGMENT)
        self.assertEqual(self._subdir_for(_SKIN_FRAGMENT), "skins")
        self.assertIsNone(self._subdir_for("red/red.mhmat"))

    def test_neither_property_reports_both_as_null(self) -> None:
        self.basemesh.properties["HUM"]["material_source"] = ""

        asset_info = self.info("Human")["asset_info"]

        self.assertIsNone(asset_info["material_source"])
        self.assertIsNone(asset_info["mhmat_path"])


class RigDefinitionPathTests(_SceneTestCase):
    def _with_rig_data(self, *relative_paths):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        for relative_path in relative_paths:
            full_path = os.path.join(directory, relative_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as handle:
                handle.write("{\n}\n")
        blender_stubs.StubLocationService.mpfb_data = directory
        return directory

    def test_builtin_rig_resolves_under_standard(self) -> None:
        directory = self._with_rig_data("rigs/standard/rig.default.json")

        asset_info = self.info("Human.rig")["asset_info"]

        self.assertEqual(
            asset_info["rig_definition_path"],
            os.path.join(directory, "rigs", "standard", "rig.default.json"))

    def test_rigify_rig_resolves_under_rigify_with_the_prefix_stripped(self) -> None:
        directory = self._with_rig_data("rigs/rigify/rig.human_toes.json")
        self.skeleton.rig_type = "rigify.human_toes"

        asset_info = self.info("Human.rig")["asset_info"]

        self.assertEqual(
            asset_info["rig_definition_path"],
            os.path.join(directory, "rigs", "rigify", "rig.human_toes.json"))

    def test_types_with_no_definition_file_report_null(self) -> None:
        self._with_rig_data("rigs/standard/rig.default.json")

        for rig_type in ("unknown", "rigify.unknown", "rigify_generated.human"):
            with self.subTest(rig_type=rig_type):
                self.skeleton.rig_type = rig_type

                asset_info = self.info("Human.rig")["asset_info"]

                self.assertEqual(asset_info["rig_type"], rig_type)
                self.assertIsNone(asset_info["rig_definition_path"])

    def test_a_definition_that_is_not_installed_reports_null(self) -> None:
        self._with_rig_data("rigs/standard/rig.default.json")
        self.skeleton.rig_type = "cmu_mb"

        self.assertIsNone(self.info("Human.rig")["asset_info"]["rig_definition_path"])

    def test_a_custom_rig_takes_its_path_from_the_asset_entry(self) -> None:
        # Custom definitions live under a user asset root, not in MPFB's data,
        # so the path is looked up rather than derived.
        self.skeleton.rig_type = "custom.my_rig"

        asset_info = self.info("Human.rig")["asset_info"]

        self.assertEqual(asset_info["rig_definition_path"], "/home/user/data/rigs/my_rig.json")

    def test_an_unknown_custom_rig_reports_null(self) -> None:
        self.skeleton.rig_type = "custom.absent"

        self.assertIsNone(self.info("Human.rig")["asset_info"]["rig_definition_path"])


if __name__ == "__main__":
    unittest.main()
