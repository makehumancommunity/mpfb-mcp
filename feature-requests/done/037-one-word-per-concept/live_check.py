#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 037's live check: every renamed spelling, once, against a running Blender.

The bridge's own tests run each command against a real MPFB, and the unit
suite checks what each tool sends. Neither proves that the two halves agree
about a name, which is the whole of this effort. This script does: it calls
every renamed argument once, through a real MCP client session, and asserts
that each renamed key comes back and each retired one does not. A retired
argument must be refused by name with its replacement, which only a call
through the server's ``call_tool`` shows - the smoke harness calls a tool's
function directly and so would never see that refusal.

It is the effort's exhaustive check, run during the effort, and it moves to
``done/`` with the request. The smoke run in ``verification/`` stays the
re-runnable one.

**What it leaves behind** is what the smoke run leaves: two characters (one of
them built from a preset), their rigs and an equipped garment in the scene, and
the smoke run's own preset and expression files, overwritten under the same
constant names so that no new file appears in the user's data. Point it at a
Blender you are willing to throw away:

    blender --background --command mpfb_bridge --port 9938
    MPFB_BRIDGE_PORT=9938 PYTHONPATH=. python3 feature-requests/done/037-one-word-per-concept/live_check.py

It exits non-zero if any check fails, and prints one line per check.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

import mpfbmcp  # noqa: E402
from mpfbmcp import arguments  # noqa: E402

# The smoke run's own names, so that this script overwrites its files rather
# than adding two more to the user's data (verification/smoke.py).
PRESET_NAME = "mpfbmcp_smoke_run"
EXPRESSION_NAME = "mpfbmcp_smoke_run"
GENERATED_RIG_NAME = "FR037LiveRig"


class Checks:
    """One line per check, and the count that decides the exit status."""

    def __init__(self):
        self.failed = 0
        self.passed = 0

    def that(self, label, condition, detail=""):
        if condition:
            self.passed += 1
            print("[x] {}".format(label))
        else:
            self.failed += 1
            print("[ ] {} -- {}".format(label, detail))

    def keys(self, label, answer, present=(), absent=()):
        """``present`` keys are in ``answer`` and ``absent`` ones are not, at this level."""
        missing = [key for key in present if key not in answer]
        stale = [key for key in absent if key in answer]
        self.that(label, not missing and not stale,
                  "missing {} / still present {} / keys {}".format(
                      missing, stale, sorted(answer)))


async def _call(client, tool, **params):
    """The tool's answer: ``(is_error, result-or-text)``."""
    response = await client.call_tool(tool, params)
    text = response.content[0].text if response.content else ""
    if response.isError:
        return True, text
    envelope = json.loads(text)
    if envelope.get("status") != "ok":
        return True, envelope
    return False, envelope["result"]


async def _first_asset(client, subdir):
    _error, result = await _call(client, "mpfb_list_assets", asset_subdir=subdir, limit=1)
    assets = (result or {}).get("assets") or []
    return assets[0] if assets else None


async def _identifier(client, family):
    _error, result = await _call(client, "mpfb_list_rigs")
    for rig in result.get("rigs") or []:
        if rig.get("available") and rig.get("family") == family:
            return rig["identifier"]
    return None


async def _retired_arguments(client, check):
    """Every retired spelling is refused by name, with what it became."""
    for tool, renames in sorted(arguments.RETIRED_ARGUMENTS.items()):
        for old, new in sorted(renames.items()):
            is_error, text = await _call(client, tool, **{old: "x"})
            check.that("{}: retired {!r} is refused naming {!r}".format(tool, old, new),
                       is_error and "'{}' (now called '{}')".format(old, new) in str(text),
                       text)
    is_error, text = await _call(client, "mpfb_set_face_units",
                                 face_units=[{"face_unit": "jawOpen", "weight": 0.3}])
    check.that("mpfb_set_face_units: a face unit's retired 'weight' names 'value'",
               is_error and "weight (now called value)" in str(text), text)


async def _run(client, check):
    await _retired_arguments(client, check)

    _error, human = await _call(client, "mpfb_create_human")
    check.keys("mpfb_create_human", human, ["basemesh_name"], ["object_name"])
    body = human["basemesh_name"]

    _error, info = await _call(client, "mpfb_get_object_info", name=body)
    check.keys("mpfb_get_object_info", info, ["subject_resolved_by"], ["resolved_from"])
    check.that("mpfb_get_object_info: subject_resolved_by is 'name'",
               info["subject_resolved_by"] == "name", info["subject_resolved_by"])

    _error, listed = await _call(client, "mpfb_list_objects", object_type="Basemesh")
    check.keys("mpfb_list_objects echo", listed,
               ["requested_object_type", "object_type_recognized", "known_object_types"],
               ["requested_type", "type_recognized", "known_types"])

    _error, assets = await _call(client, "mpfb_list_assets", asset_subdir="clothes", limit=1)
    check.keys("mpfb_list_assets echo", assets,
               ["requested_asset_subdir", "asset_subdir_recognized", "known_asset_subdirs",
                "counts_by_asset_subdir"],
               ["requested_subdir", "subdir_recognized", "known_subdirs", "counts_by_subdir"])

    _error, macro = await _call(client, "mpfb_set_macro_details", name=body, gender=0.4)
    check.keys("mpfb_set_macro_details", macro, ["changes"], ["changed"])
    check.keys("mpfb_set_macro_details changes[0]", macro["changes"][0],
               ["previous_value", "new_value"], ["previous", "new"])
    check.keys("mpfb_set_macro_details assets_possibly_stale", macro["assets_possibly_stale"],
               ["rig_object_name"], ["rig_name"])

    _error, targets = await _call(client, "mpfb_set_targets", name=body, modifiers=[])
    check.keys("mpfb_set_targets", targets, ["changes"], ["applied"])

    _error, symmetric = await _call(client, "mpfb_symmetrize_targets", name=body,
                                    direction="left_to_right", dry_run=True)
    check.keys("mpfb_symmetrize_targets", symmetric, ["changes", "change_count"],
               ["changed", "changed_count"])

    _error, faced = await _call(client, "mpfb_set_face_units", name=body, mode="replace",
                                face_units=[{"face_unit": "jawOpen", "value": 0.3}], refit=False)
    check.keys("mpfb_set_face_units", faced,
               ["changes", "change_count", "mode", "removed_by_replace"],
               ["applied", "applied_count", "clear_first", "cleared"])
    if faced.get("changes"):
        check.keys("mpfb_set_face_units changes[0]", faced["changes"][0],
                   ["value", "previous_value", "new_value"], ["weight"])
        _error, units = await _call(client, "mpfb_get_face_units", name=body)
        check.keys("mpfb_get_face_units face_units[0]", units["face_units"][0],
                   ["value"], ["weight"])
    else:
        check.that("mpfb_set_face_units wrote a unit (needs faceunits01)", False, faced)

    missing = "FR037NoSuchObject"
    _error, orphan = await _call(client, "mpfb_save_expression", expression_name=EXPRESSION_NAME,
                                 name=missing, overwrite=True)
    check.that("mpfb_save_expression: a name that is no object points at expression_name",
               orphan.get("blocked_by") == "subject_not_found"
               and "pass it as expression_name" in orphan.get("message", ""), orphan)
    _error, saved = await _call(client, "mpfb_save_expression", expression_name=EXPRESSION_NAME,
                                name=body, overwrite=True)
    check.keys("mpfb_save_expression", saved, ["expression_name", "file_before"],
               ["name", "previous_file"])

    standard = await _identifier(client, "standard")
    _error, rigged = await _call(client, "mpfb_add_rig", name=body, identifier=standard)
    check.keys("mpfb_add_rig", rigged, ["rig_object_name"])
    _error, again = await _call(client, "mpfb_add_rig", name=body, identifier=standard)
    check.keys("mpfb_add_rig already_rigged", again,
               ["existing_rig_object_name", "existing_rig_identified_as"],
               ["existing_rig_name", "existing_rig_type"])

    _error, rig_info = await _call(client, "mpfb_get_object_info", name=rigged["rig_object_name"])
    check.keys("mpfb_get_object_info asset_info of a rig", rig_info["asset_info"],
               ["rig_identified_as"], ["rig_type"])

    _error, not_meta = await _call(client, "mpfb_generate_rigify_rig", name=body)
    check.that("mpfb_generate_rigify_rig not_a_metarig names rig_identified_as per skeleton",
               not_meta.get("blocked_by") == "not_a_metarig"
               and all("rig_identified_as" in entry and "rig_type" not in entry
                       for entry in not_meta.get("skeletons") or [None]), not_meta)

    _error, refit = await _call(client, "mpfb_refit_human", name=body)
    check.keys("mpfb_refit_human", refit, ["rig_object_name"], ["rig_name"])

    garment = await _first_asset(client, "clothes")
    _error, unknown = await _call(client, "mpfb_add_asset", name=body,
                                  fragment=garment["fragment"], object_type="Trousers")
    check.that("mpfb_add_asset: an unknown object_type is unknown_object_type",
               unknown.get("blocked_by") == "unknown_object_type"
               and "known_object_types" in unknown and "known_asset_types" not in unknown,
               unknown)
    _error, added = await _call(client, "mpfb_add_asset", name=body,
                                fragment=garment["fragment"], object_type=garment["object_type"])
    check.keys("mpfb_add_asset", added, ["requested_object_type", "path_resolved_by"],
               ["requested_asset_type", "resolved_by", "asset_type"])
    asset_object = added["asset_object_name"]

    _error, material = await _call(client, "mpfb_set_asset_material", name=asset_object,
                                   restore_default=True)
    check.keys("mpfb_set_asset_material", material,
               ["path_resolved_by", "alternative_material_before"],
               ["resolved_by", "previous_alternative_material"])
    for tool, extra in (("mpfb_set_asset_material", {"restore_default": True}),
                        ("mpfb_remove_asset", {})):
        is_error, miss = await _call(client, tool, name=missing, **extra)
        check.that("{}: an unknown name is subject_not_found".format(tool),
                   not is_error and miss.get("blocked_by") == "subject_not_found", miss)

    skin_asset = await _first_asset(client, "skins")
    is_error, skin = await _call(client, "mpfb_set_skin", name=body,
                                 fragment=skin_asset["fragment"])
    check.that("mpfb_set_skin answered", not is_error, skin)
    if not is_error:
        check.keys("mpfb_set_skin", skin, ["path_resolved_by"], ["resolved_by"])

    _error, summary = await _call(client, "mpfb_get_character_summary", name=body)
    check.keys("mpfb_get_character_summary", summary, ["equipped_assets"], ["assets"])
    check.keys("mpfb_get_character_summary rig", summary["rig"], ["rig_identified_as"],
               ["rig_type"])
    check.keys("mpfb_get_character_summary skin", summary["skin"], ["material_identified_as"],
               ["material_type"])
    if summary["equipped_assets"]:
        check.keys("mpfb_get_character_summary equipped_assets[0]", summary["equipped_assets"][0],
                   ["material_identified_as"], ["material_type"])

    _error, removed = await _call(client, "mpfb_remove_asset", name=asset_object)
    check.keys("mpfb_remove_asset", removed, ["bodyproxy_name"], ["body_proxy_name"])

    _error, preset_orphan = await _call(client, "mpfb_save_preset", preset_name=PRESET_NAME,
                                        name=missing, overwrite=True)
    check.that("mpfb_save_preset: a name that is no object points at preset_name",
               preset_orphan.get("blocked_by") == "subject_not_found"
               and "pass it as preset_name" in preset_orphan.get("message", ""), preset_orphan)
    _error, preset = await _call(client, "mpfb_save_preset", preset_name=PRESET_NAME, name=body,
                                 overwrite=True)
    check.keys("mpfb_save_preset", preset, ["preset_name", "file_before", "rig_object_name"],
               ["name", "previous_file", "rig_name"])

    _error, built = await _call(client, "mpfb_create_human_from_preset", preset_name=PRESET_NAME,
                                material_instances_policy="NEVER")
    check.keys("mpfb_create_human_from_preset", built,
               ["preset_name", "material_instances_policy_requested",
                "material_instances_policy_used", "material_instances_policy_service_default",
                "known_material_instances_policies", "equipped_assets"],
               ["name", "material_instances_requested", "material_instances_used",
                "material_instances_service_default", "known_material_instances"])
    check.that("mpfb_create_human_from_preset: overrides keyed by the new argument names",
               set(built["overrides"]) == {
                   "override_rig", "override_skin_type", "override_clothes_material_type",
                   "override_eyes_material_type", "load_clothes", "scale",
                   "material_instances_policy"}, sorted(built["overrides"]))
    check.that("mpfb_create_human_from_preset: settings_used keeps MPFB's own keys",
               "material_instances" in built["settings_used"]
               and built["settings_used"]["material_instances"] == "NEVER",
               built["settings_used"])
    for record in built["equipped_assets"]:
        check.keys("mpfb_create_human_from_preset equipped_assets record", record,
                   ["kind", "name", "asset_source"], ["object_name"])

    rigify = await _identifier(client, "rigify")
    if rigify is None:
        check.that("mpfb_generate_rigify_rig (needs Rigify)", False, "no rigify.* rig here")
        return
    _error, second = await _call(client, "mpfb_create_human")
    await _call(client, "mpfb_add_rig", name=second["basemesh_name"], identifier=rigify)
    _error, generated = await _call(client, "mpfb_generate_rigify_rig",
                                    name=second["basemesh_name"],
                                    generated_rig_name=GENERATED_RIG_NAME)
    check.keys("mpfb_generate_rigify_rig", generated,
               ["generated_rig_name_requested", "rig_object_name"], ["rig_name_requested"])
    check.that("mpfb_generate_rigify_rig echoes generated_rig_name",
               generated.get("generated_rig_name_requested") == GENERATED_RIG_NAME, generated)


async def _main():
    check = Checks()
    async with create_connected_server_and_client_session(mpfbmcp.build_server()) as client:
        await _run(client, check)
    print("--- FR 037 live check: {} passed, {} failed".format(check.passed, check.failed))
    return 1 if check.failed else 0


if __name__ == "__main__":
    # FastMCP logs every request at INFO through a handler of its own.
    logging.disable(logging.INFO)
    sys.exit(asyncio.run(_main()))
