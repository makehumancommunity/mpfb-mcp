# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_get_status tool, migrated by FR 031 and therefore in three
layers rather than two (see ``tests/test_list_objects.py``, the template).

1. **The wrapper**, with ``send_code`` mocked on the seam. This tool takes no
   arguments at all, so what is left here is the smallest a wrapper layer gets:
   the bootstrap it asks for, and that the envelope reaches the caller.
2. **The bridge path**, against ``tests/fake_bridge.py``. Thin, and one of its
   four tests exists only for this tool: the command it sends is
   ``get_mpfb_status`` and **not** ``get_status``, which the bridge already
   uses for its own state. A tool that sent ``get_status`` would get a
   plausible-looking answer about the wrong piece of software.
3. **The payload**, ``exec()``-ed against stubbed ``sys.modules`` entries and a
   stubbed ``bpy``. **Frozen.** It stays while the payload stays, because the
   payload is half of what FR 031's live comparison compares, and it is deleted
   with the payload when the generated path is retired. Nothing is added to it:
   a new assertion about MPFB's behaviour belongs in
   ``bridge/test/tests/ggg_get_mpfb_status_test.py``, where it is made against
   a real install rather than against stubs written by whoever wrote the code
   under test.

The share of this module that goes with the payload: 203 of its 410 lines, 50%
- the three stub services, the assembled-source checks and the execution tests
- against a 122-line payload whose logic is a three-way classification. Read it
beside ``mpfb_list_objects``' 27%: that tool's payload is a filter and a
substring test, and this is what the rate looks like once a payload branches.

Run with::

    python -m unittest tests.test_get_status -v
"""

__all__ = ()

import inspect
import json
import pathlib
import sys
import types
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import backend, codegen
from mpfbmcp.tools import get_status
from tests import fake_bridge

# SystemService's module, which is where MPFB keeps LOWEST_FUNCTIONAL_BLENDER_VERSION
# (a module-level constant, not a class member). Must not itself end in "mpfb", or
# the candidate scan would pick it up.
_STUB_SYSTEMSERVICE_MODULE = "mpfb_stub_services_systemservice"
_STUB_PACKAGE = "bl_ext.test_repo.mpfb"


def _get_status_code() -> str:
    """The source mpfb_get_status sends, assembled exactly as the tool does."""
    return codegen.assemble("get_status.py", bootstrap="non_raising")


class _LocationServiceStub:
    """Stands in for MPFB's LocationService singleton."""

    @staticmethod
    def is_source_dist():
        return True

    @staticmethod
    def get_mpfb_root(sub_path=None):
        # A pathlib.Path, not a str, despite LocationService's annotation: MPFB
        # keeps this one path as a Path and returns it unchanged when no
        # sub-path is given. Reporting it raw made the whole response fail
        # strict_json, so the stub keeps the real type here.
        return pathlib.Path("/addons/mpfb")

    @staticmethod
    def get_mpfb_data(sub_path=None):
        return "/addons/mpfb/data"

    @staticmethod
    def get_user_home(sub_path=None):
        return "/home/user/mpfb"

    @staticmethod
    def get_user_data(sub_path=None):
        return "/home/user/mpfb/data"

    @staticmethod
    def get_user_config(sub_path=None):
        return "/home/user/mpfb/config"

    @staticmethod
    def get_user_cache(sub_path=None):
        return "/home/user/mpfb/cache"

    @staticmethod
    def get_log_dir(sub_path=None):
        return "/home/user/mpfb/logs"

    @staticmethod
    def get_second_root(sub_path=None):
        # Unset, as it usually is. MPFB returns None rather than "" here.
        return None

    @staticmethod
    def get_mh_user_data(sub_path=None):
        return None


class _AssetServiceStub:
    @staticmethod
    def get_available_data_roots():
        return ["/addons/mpfb/data", "/home/user/mpfb/data"]

    @staticmethod
    def get_pack_names():
        return ["system_assets", "extra_assets"]

    @staticmethod
    def system_assets_pack_is_installed():
        return True


class _SystemServiceStub:
    @staticmethod
    def deduce_platform():
        return "LINUX"

    @staticmethod
    def is_blender_version_at_least(version=None):
        return True

    @staticmethod
    def check_for_rigify():
        return False


def _make_bpy_stub(enabled_addons=(), version_string="5.1.0"):
    bpy = types.ModuleType("bpy")
    bpy.app = types.SimpleNamespace(version_string=version_string)
    bpy.context = types.SimpleNamespace(
        preferences=types.SimpleNamespace(addons={name: object() for name in enabled_addons})
    )
    return bpy


def _make_mpfb_stub(name, contextual_information):
    module = types.ModuleType(name)
    module.VERSION = (2, 0, 17)
    module.BUILD_INFO = "FROM_SOURCE"
    module.MPFB_CONTEXTUAL_INFORMATION = contextual_information
    return module


_SERVICES = {
    "LocationService": _LocationServiceStub,
    "AssetService": _AssetServiceStub,
    "SystemService": _SystemServiceStub,
}


def _register_and_get_tool() -> object:
    mcp = FastMCP("test")
    get_status.register(mcp)
    # FastMCP tools are coroutine functions wrapping the sync function; the
    # underlying callable is what we actually want to invoke directly.
    tool = mcp._tool_manager._tools["mpfb_get_status"]  # noqa: SLF001
    return tool.fn


class GetStatusToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mpfb_get_status = _register_and_get_tool()

    @mock.patch("mpfbmcp.backend.send_code")
    def test_takes_no_arguments_and_requests_strict_json(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"state": "ok"}}

        self.assertEqual(list(inspect.signature(self.mpfb_get_status).parameters), [])
        self.mpfb_get_status()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertIn("_mpfb_state", code)

    @mock.patch("mpfbmcp.backend.send_code")
    def test_response_is_passed_through_unchanged(self, mock_send_code: mock.Mock) -> None:
        # The tool must not interpret or reshape the envelope: graceful absence
        # lives in the generated code, not in Python on this side of the socket.
        envelope = {"status": "ok", "result": {"state": "absent", "candidate_modules": []}}
        mock_send_code.return_value = envelope

        self.assertEqual(self.mpfb_get_status(), envelope)

    def test_a_failure_reaches_the_caller_with_a_slug_to_branch_on(self) -> None:
        # `status` and `message` are unchanged and `error` is what a caller
        # branches on whichever transport answered. The mapping is
        # tests/test_backend.py's.
        with mock.patch("mpfbmcp.backend.send_code",
                        return_value={"status": "error", "message": "boom"}):
            response = self.mpfb_get_status()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["message"], "boom")
        self.assertEqual(response["error"], backend.ERROR_COMMAND_FAILED)


class GetStatusOverTheBridgeTests(fake_bridge.BridgeTestCase):
    """What cannot cross the socket, and nothing else.

    Everything this tool *answers* - the three states, the tiers of fields, the
    disabled-but-loaded case - is checked against a real MPFB in the bridge's
    own suite.
    """

    def setUp(self) -> None:
        super().setUp()
        self.mpfb_get_status = _register_and_get_tool()
        self.set_env_var(backend.BACKEND_VARIABLE, backend.BACKEND_BRIDGE)
        self.bridge = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "get_mpfb_status": fake_bridge.ok_envelope(
                "get_mpfb_status", {"state": "ok", "candidate_modules": []}),
        })

    def test_the_tool_sends_get_mpfb_status_and_not_get_status(self) -> None:
        # The one naming exception in MIGRATED_COMMANDS, asserted where it would
        # actually bite: `get_status` is the bridge's own state, and a tool
        # sending it would get a well-formed answer about the wrong software.
        self.mpfb_get_status()

        # The first `get_status` is the handshake probe, which every first call
        # to an address makes; the command this tool sent is the last one.
        self.assertEqual(self.bridge.commands()[-1], "get_mpfb_status")
        self.assertEqual(self.bridge.decoded_requests()[-1]["params"], {})

    def test_the_answer_reaches_the_caller_as_it_arrived(self) -> None:
        response = self.mpfb_get_status()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["state"], "ok")

    def test_absence_is_still_a_successful_answer_over_the_bridge(self) -> None:
        # The whole value of this tool, and the reason its command declares
        # requires_mpfb=False: a Blender with no MPFB answers rather than
        # refusing. The bridge's precondition would have produced an
        # mpfb_unavailable envelope instead.
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.ok_envelope("get_mpfb_status", {
                "state": "absent",
                "message": "MPFB is not loaded in this Blender instance",
                "candidate_modules": []}))

        response = self.mpfb_get_status()

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["state"], "absent")

    def test_a_bridge_error_envelope_reaches_the_caller_intact(self) -> None:
        self.bridge.responder = lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope(
                "command_failed", "The command raised while running inside Blender.",
                command="get_mpfb_status"))

        response = self.mpfb_get_status()

        self.assertEqual(response["status"], "error")
        self.assertEqual(response["error"], "command_failed")


class GetStatusCodeTests(unittest.TestCase):
    """The payload against the stubs. **Frozen**: see this module's docstring."""


    def test_generated_code_compiles(self) -> None:
        compile(_get_status_code(), "<generated>", "exec")

    def test_generated_code_classifies_rather_than_raises(self) -> None:
        code = _get_status_code()
        # The two conditions that would otherwise escape as TypeError/KeyError,
        # in exactly the states a broken MPFB install produces.
        self.assertIn("_mpfb_contextual_information is None", code)
        self.assertIn('"SERVICES" not in _mpfb_contextual_information', code)
        for state in ('"absent"', '"not_initialized"', '"ok"'):
            self.assertIn(state, code)
        self.assertNotIn("raise RuntimeError", code)

    def test_generated_code_does_not_import_mpfb_submodules(self) -> None:
        # locationservice.py creates directories on disk at import time, so
        # generated code must reach services only through the SERVICES dict.
        code = _get_status_code()
        self.assertNotIn("import_module", code)
        self.assertNotIn("importlib", code)


class GeneratedCodeExecutionTests(unittest.TestCase):
    """Executes the generated source against stubbed sys.modules entries."""

    def setUp(self) -> None:
        stray = [name for name in list(sys.modules) if name.endswith("mpfb")]
        self.assertEqual(stray, [], "a real module ending in 'mpfb' would skew these tests")
        self._injected: list[str] = []

    def tearDown(self) -> None:
        for name in self._injected:
            sys.modules.pop(name, None)

    def _inject(self, name, module) -> None:
        sys.modules[name] = module
        self._injected.append(name)

    def _run(self, enabled_addons=()):
        namespace = {}
        with mock.patch.dict(sys.modules, {"bpy": _make_bpy_stub(enabled_addons)}):
            exec(_get_status_code(), namespace)  # noqa: S102
        return namespace["result"]

    def test_absent_still_reports_blender_version(self) -> None:
        result = self._run()

        self.assertEqual(result["state"], "absent")
        self.assertEqual(result["candidate_modules"], [])
        self.assertIsNone(result["package"])
        self.assertIsNone(result["enabled"])
        self.assertEqual(result["blender"]["version"], "5.1.0")
        self.assertNotIn("version", result)
        self.assertTrue(result["message"])

    def test_not_initialized_reports_module_fields_only(self) -> None:
        self._inject(_STUB_PACKAGE, _make_mpfb_stub(_STUB_PACKAGE, None))

        result = self._run(enabled_addons=(_STUB_PACKAGE,))

        self.assertEqual(result["state"], "not_initialized")
        self.assertEqual(result["package"], _STUB_PACKAGE)
        self.assertTrue(result["enabled"])
        self.assertEqual(result["version"], "2.0.17")
        self.assertEqual(result["build_info"], "FROM_SOURCE")
        # Nothing needing services, since importing them would have side effects.
        self.assertNotIn("paths", result)
        self.assertNotIn("asset_roots", result)

    def test_contextual_information_without_services_is_not_initialized(self) -> None:
        # register() started but did not reach its last line.
        self._inject(_STUB_PACKAGE, _make_mpfb_stub(_STUB_PACKAGE, {"__package__": _STUB_PACKAGE}))

        self.assertEqual(self._run()["state"], "not_initialized")

    def test_ok_populates_every_documented_field(self) -> None:
        self._inject(_STUB_SYSTEMSERVICE_MODULE, self._systemservice_module())
        self._inject(_STUB_PACKAGE, _make_mpfb_stub(_STUB_PACKAGE, {"SERVICES": _SERVICES}))

        result = self._run(enabled_addons=(_STUB_PACKAGE,))

        self.assertEqual(result["state"], "ok")
        self.assertTrue(result["enabled"])
        self.assertTrue(result["is_source_dist"])
        self.assertEqual(result["addon_installation_path"], "/addons/mpfb")
        # The tool sends this with strict_json=True, so anything left in result
        # that json cannot encode turns the whole call into an error envelope.
        json.dumps(result)
        self.assertEqual(
            result["paths"]["user_data"], {"path": "/home/user/mpfb/data", "configured": True})
        # The two optional roots: unset must read as "not configured", not as a path.
        self.assertEqual(result["paths"]["second_root"], {"path": None, "configured": False})
        self.assertEqual(result["paths"]["mh_user_data"], {"path": None, "configured": False})
        self.assertEqual(result["asset_roots"], ["/addons/mpfb/data", "/home/user/mpfb/data"])
        self.assertEqual(result["asset_packs"]["count"], 2)
        self.assertTrue(result["asset_packs"]["system_assets_pack_installed"])
        self.assertFalse(result["rigify_available"])
        self.assertEqual(result["blender"]["platform"], "LINUX")
        self.assertTrue(result["blender"]["meets_mpfb_minimum"])
        self.assertEqual(result["blender"]["mpfb_minimum_version"], "4.2.0")

    def test_disabled_mpfb_is_distinguished_only_by_enabled(self) -> None:
        # unregister() leaves MPFB_CONTEXTUAL_INFORMATION populated, so state
        # stays "ok" and `enabled` is the only thing that tells them apart.
        self._inject(_STUB_SYSTEMSERVICE_MODULE, self._systemservice_module())
        self._inject(_STUB_PACKAGE, _make_mpfb_stub(_STUB_PACKAGE, {"SERVICES": _SERVICES}))

        result = self._run(enabled_addons=())

        self.assertEqual(result["state"], "ok")
        self.assertFalse(result["enabled"])

    def test_two_installs_are_both_reported(self) -> None:
        second = "bl_ext.other_repo.mpfb"
        self._inject(_STUB_PACKAGE, _make_mpfb_stub(_STUB_PACKAGE, None))
        self._inject(second, _make_mpfb_stub(second, None))

        result = self._run()

        self.assertEqual(sorted(result["candidate_modules"]), sorted([_STUB_PACKAGE, second]))
        # The first match wins, arbitrarily - reporting both is the diagnosis.
        self.assertIn(result["package"], (_STUB_PACKAGE, second))

    def _systemservice_module(self):
        module = types.ModuleType(_STUB_SYSTEMSERVICE_MODULE)
        module.LOWEST_FUNCTIONAL_BLENDER_VERSION = (4, 2, 0)
        _SystemServiceStub.__module__ = _STUB_SYSTEMSERVICE_MODULE
        return module


if __name__ == "__main__":
    unittest.main()
