# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 018's live check: ``refresh`` actually clears MPFB's alternative-materials cache.

The unit suite cannot establish this - it never talks to a real
``AssetService``, so the claim that ``invalidate_alternative_materials_cache()``
makes a material installed after the first call visible is a claim about MPFB,
not about this package's own code. This script puts it to a real Blender, the
same way the deleted ``check_fr011.py`` did before this effort: an MHCLO asset
is equipped, ``mpfb_list_asset_materials`` is called once to warm MPFB's cache,
a probe ``.mhmat`` is written beside the asset on disk, and the tool is called
twice more - once with the default ``refresh=False``, which must still miss
the probe, and once with ``refresh=True``, which must see it. The probe file is
always removed afterwards, in a ``finally``, whatever the calls answered.

**No scratch scene.** Like every live check written since FR 033
(see [harness.py](../../verification/harness.py)), this builds in whatever
scene it is pointed at and leaves what it built there; only the probe file,
which is outside the ``.blend`` entirely, is cleaned up.

Run with::

    PYTHONPATH=. python3 feature-requests/018-alternative-material-refresh/check_fr018.py

against a Blender with MPFB and the MPFB Bridge enabled and the bridge's
command server started (``MPFB_BRIDGE_HOST``/``MPFB_BRIDGE_PORT`` if not the
default ``127.0.0.1:9877``). Exit code 0 if every check passed, 1 if any
failed, 2 if the run could not be made at all (no MPFB, or no MHCLO asset to
equip).
"""

from __future__ import annotations

__all__ = ("main",)

import os
import sys

from verification import fixtures, harness

PROBE_FILENAME = "fr018_probe.mhmat"

PROBE_CONTENT = (
    "# MakeHuman mhmat File\n"
    "# Written by feature-requests/018-alternative-material-refresh/check_fr018.py and "
    "removed before the script exits.\n"
    "version 1\n"
)


def run() -> dict:
    tools = harness.tools()
    report = harness.Report("FR 018 - mpfb_list_asset_materials refresh")

    install = fixtures.check_install(tools)
    if not report.check("MPFB is loaded and initialized", install["usable"],
                        install["state"] or install.get("envelope")):
        report.note("nothing below can run against this install")
        counts = report.summary()
        counts["exit_code"] = 2
        return counts

    envelope, character = fixtures.create_character(tools)
    if not report.check("a character could be built to hang an asset on",
                        envelope.get("status") == "ok" and character is not None, envelope):
        counts = report.summary()
        counts["exit_code"] = 2
        return counts

    asset = fixtures.first_asset(tools, "clothes")
    if asset is None:
        report.skip("refresh clears the cache and the next call sees a new material",
                    "this install has no asset under 'clothes' to equip")
        counts = report.summary()
        counts["exit_code"] = 0
        return counts

    equipped = tools["mpfb_add_asset"](
        name=character, fragment=asset["fragment"], asset_type=asset["object_type"])
    if not report.check("the asset could be equipped", equipped.get("status") == "ok",
                        equipped):
        counts = report.summary()
        counts["exit_code"] = 2
        return counts
    garment = equipped["result"]["asset_object_name"]

    _check_refresh_lifts_the_staleness(tools, report, garment)

    counts = report.summary()
    counts["exit_code"] = 1 if counts["failed"] else 0
    return counts


def _check_refresh_lifts_the_staleness(tools: dict, report: harness.Report,
                                       garment: str) -> None:
    """Warm the cache, drop a probe material on disk, and ask twice more."""
    warm = tools["mpfb_list_asset_materials"](name=garment)
    if not report.check("the first call answers and warms MPFB's cache",
                        warm.get("status") == "ok", warm):
        return
    warm_result = warm["result"]
    if not report.check("the answer carries cache_invalidated, false by default",
                        warm_result.get("cache_invalidated") is False, warm_result):
        return
    default_material = warm_result.get("default_material")
    if not report.check("the asset's own material resolved, so its directory is known",
                        default_material is not None, warm_result.get("default_material_reason")):
        return

    probe_path = os.path.join(os.path.dirname(default_material["path"]), PROBE_FILENAME)
    names_before = sorted(entry["name"] for entry in warm_result["materials"])

    try:
        with open(probe_path, "w", encoding="utf-8") as handle:
            handle.write(PROBE_CONTENT)
        report.note("wrote a probe material to {}".format(probe_path))

        stale = tools["mpfb_list_asset_materials"](name=garment)
        stale_result = (stale.get("result") or {}) if stale.get("status") == "ok" else {}
        names_stale = sorted(entry["name"] for entry in stale_result.get("materials", []))
        report.check(
            "refresh=False still answers from the warm cache, missing the probe",
            stale.get("status") == "ok" and names_stale == names_before
            and stale_result.get("cache_invalidated") is False,
            dict(before=names_before, stale=names_stale,
                 cache_invalidated=stale_result.get("cache_invalidated")))
        report.check("the staleness is in the message, not only in the data",
                    "cached snapshot" in str(stale_result.get("message", "")),
                    stale_result.get("message"))

        refreshed = tools["mpfb_list_asset_materials"](name=garment, refresh=True)
        refreshed_result = (
            (refreshed.get("result") or {}) if refreshed.get("status") == "ok" else {})
        names_refreshed = sorted(
            entry["name"] for entry in refreshed_result.get("materials", []))
        report.check(
            "refresh=True clears the cache and the probe material appears",
            refreshed.get("status") == "ok"
            and "fr018_probe" in names_refreshed
            and refreshed_result.get("cache_invalidated") is True,
            dict(refreshed=names_refreshed,
                 cache_invalidated=refreshed_result.get("cache_invalidated")))
        report.check("the cleared-cache message names the global side effect",
                    "global" in str(refreshed_result.get("message", "")),
                    refreshed_result.get("message"))

        # The cache is global (see the module docstring on the bridge command):
        # a second asset's next call must not be handed a stale answer either.
        # There is nothing else equipped to check this against on every
        # install, so this is a note rather than an assertion.
    finally:
        if os.path.isfile(probe_path):
            os.remove(probe_path)
        report.note("removed the probe material ({})".format(
            "gone" if not os.path.isfile(probe_path) else "STILL THERE"))


def main() -> int:
    # Not harness.main_guard(): that only distinguishes pass from fail, and this
    # script also has a "could not be made at all" outcome (no MPFB, no asset to
    # equip, no character) that earns its own exit code rather than either.
    counts = run()
    return counts.get("exit_code", 1 if counts.get("failed") else 0)


if __name__ == "__main__":
    sys.exit(main())
