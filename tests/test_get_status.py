# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for the mpfb_get_status tool: the tool wrapper, and the generated code's
three-state classification.

The generated code cannot be run against real MPFB from here (see
specifications/architecture.md), but unlike the other tools' generated code it
carries real branching logic, so it is worth executing locally against stubbed
``sys.modules`` entries and a stubbed ``bpy``. That checks the branching and
the shape of ``result``; it says nothing about whether real MPFB returns the
values we assume, which remains a manual check against a running Blender.

Run with::

    python -m unittest tests.test_get_status -v
"""

__all__ = ()

import inspect
import sys
import types
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp.mpfb_codegen import build_get_status_code
from mpfbmcp.tools import get_status

# SystemService's module, which is where MPFB keeps LOWEST_FUNCTIONAL_BLENDER_VERSION
# (a module-level constant, not a class member). Must not itself end in "mpfb", or
# the candidate scan would pick it up.
_STUB_SYSTEMSERVICE_MODULE = "mpfb_stub_services_systemservice"
_STUB_PACKAGE = "bl_ext.test_repo.mpfb"


class _LocationServiceStub:
    """Stands in for MPFB's LocationService singleton."""

    @staticmethod
    def is_source_dist():
        return True

    @staticmethod
    def get_mpfb_root(sub_path=None):
        return "/addons/mpfb"

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

    @mock.patch("mpfbmcp.tools.get_status.send_code")
    def test_takes_no_arguments_and_requests_strict_json(self, mock_send_code: mock.Mock) -> None:
        mock_send_code.return_value = {"status": "ok", "result": {"state": "ok"}}

        self.assertEqual(list(inspect.signature(self.mpfb_get_status).parameters), [])
        self.mpfb_get_status()

        (code,), kwargs = mock_send_code.call_args
        self.assertTrue(kwargs.get("strict_json"))
        self.assertIn("_mpfb_state", code)

    @mock.patch("mpfbmcp.tools.get_status.send_code")
    def test_response_is_passed_through_unchanged(self, mock_send_code: mock.Mock) -> None:
        # The tool must not interpret or reshape the envelope: graceful absence
        # lives in the generated code, not in Python on this side of the socket.
        envelope = {"status": "ok", "result": {"state": "absent", "candidate_modules": []}}
        mock_send_code.return_value = envelope

        self.assertEqual(self.mpfb_get_status(), envelope)

    def test_error_envelope_is_also_passed_through(self) -> None:
        envelope = {"status": "error", "message": "boom"}
        with mock.patch("mpfbmcp.tools.get_status.send_code", return_value=envelope):
            self.assertEqual(self.mpfb_get_status(), envelope)


class GetStatusCodeTests(unittest.TestCase):
    def test_generated_code_compiles(self) -> None:
        compile(build_get_status_code(), "<generated>", "exec")

    def test_generated_code_classifies_rather_than_raises(self) -> None:
        code = build_get_status_code()
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
        code = build_get_status_code()
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
            exec(build_get_status_code(), namespace)  # noqa: S102
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
