# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 005's checklist, re-run.

Stale for the same reason FR 004's was: FR 010 migrated
``payloads/list_assets.py`` onto the shared ``asset_sections.py`` fragment, so
the program sent into Blender is a different program even though the unit tests
see no behavior change. The re-run belongs before FR 010's own checklist because
that one compares its ``resolved_path`` against this one's ``path``.

Two of FR 005's items could not be observed at all when it was written, and both
can be now: this install has grown from 730 assets to 845, and ``poses`` from
zero entries to 59 - so the ``bvh`` row's item shape, which FR 005 recorded as
the one thing it could not see, is checkable here.

Run with::

    python3 verification/check_fr005.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys

from verification import harness
from verification.harness import Report, probe

ITEMS = (
    "all eleven subdirs listed from MPFB's own ASSET_LIBRARY_SECTIONS, in its order",
    "the item key set is present for every subdir that has assets",
    "the label collision is real and is counted",
    "pack attribution against the real packs",
    "filters: name_contains, pack, asset_subdir, and the three combining",
    "a misspelled subdir, a misspelled pack and an empty subdir are three answers",
    "paging concatenates to the unpaged listing",
    "asset_roots_searched is per subdir and narrower than the data roots",
    "assets reported here can actually be applied",
    "whole response survives strict_json at full size",
)

ITEM_KEYS = ("path", "fragment", "name", "label", "object_type", "asset_subdir",
             "file_type", "pack", "pack_ambiguous", "thumb_path")


def run() -> dict:
    tools = harness.tools()
    report = Report("FR 005 - mpfb_list_assets (re-check after the asset_sections migration)",
                    ITEMS)
    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()

    full = tools["mpfb_list_assets"](limit=1000)
    report.check("whole response survives strict_json at full size",
                 full.get("status") == "ok"
                 and len(full["result"]["assets"]) == full["result"]["total_count"],
                 dict(total=full["result"].get("total_count"),
                      returned=len(full["result"].get("assets", [])),
                      message=full.get("message")))
    listing = full["result"]
    assets = listing["assets"]

    on_disk = probe("asset_files_on_disk", _ON_DISK_CODE)
    report.check("all eleven subdirs listed from MPFB's own ASSET_LIBRARY_SECTIONS, in its order",
                 list(listing["counts_by_subdir"]) == on_disk["section_order"]
                 and listing["section_table_from_mpfb"] is True,
                 dict(counts=listing["counts_by_subdir"], total=listing["total_count"],
                      section_table_from_mpfb=listing["section_table_from_mpfb"]))

    subdirs_with_assets = sorted(set(asset["asset_subdir"] for asset in assets))
    missing_keys = dict()
    for subdir in subdirs_with_assets:
        sample = [asset for asset in assets if asset["asset_subdir"] == subdir][0]
        absent = [key for key in ITEM_KEYS if key not in sample]
        if absent:
            missing_keys[subdir] = absent
    report.check("the item key set is present for every subdir that has assets",
                 not missing_keys,
                 dict(subdirs=subdirs_with_assets, missing=missing_keys,
                      poses_sample=[asset for asset in assets
                                    if asset["asset_subdir"] == "poses"][:1]))

    collisions = dict()
    for subdir, files in on_disk["files_by_subdir"].items():
        reported = len([asset for asset in assets if asset["asset_subdir"] == subdir])
        if len(files) != reported:
            collisions[subdir] = dict(on_disk=len(files), reported=reported)
    report.check("the label collision is real and is counted",
                 bool(collisions), collisions)

    attributed = len([asset for asset in assets if asset["pack"]])
    ambiguous = len([asset for asset in assets if asset["pack_ambiguous"]])
    report.check("pack attribution against the real packs",
                 attributed > 0 and ambiguous > 0,
                 dict(total=len(assets), attributed=attributed,
                      unattributed=len(assets) - attributed, ambiguous=ambiguous,
                      packs=len(listing["known_packs"])))

    _check_filters(tools, report, assets)
    _check_three_answers(tools, report)
    _check_paging(tools, report)

    per_subdir_roots = listing["asset_roots_searched"]
    all_roots = set()
    for roots in per_subdir_roots.values():
        all_roots.update(roots)
    narrower = [subdir for subdir, roots in per_subdir_roots.items()
                if len(roots) < len(all_roots)]
    report.check("asset_roots_searched is per subdir and narrower than the data roots",
                 bool(narrower), dict(all_roots=sorted(all_roots), narrower=narrower))

    _check_applied(tools, report, assets)

    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("revert: every datablock collection identical afterwards",
                 difference["identical"] and not difference["is_dirty_after"], difference)
    return report.summary()


def _check_filters(tools: dict, report: Report, assets: list) -> None:
    by_name = tools["mpfb_list_assets"](name_contains="JEANS", limit=1000)["result"]
    lowercase = tools["mpfb_list_assets"](name_contains="jeans", limit=1000)["result"]
    by_pack = tools["mpfb_list_assets"](pack="hair03", limit=1000)["result"]
    uppercase_pack = tools["mpfb_list_assets"](pack="HAIR03", limit=1000)["result"]
    by_subdir = tools["mpfb_list_assets"](asset_subdir="HAIR", limit=1000)["result"]
    combined = tools["mpfb_list_assets"](
        asset_subdir="clothes", name_contains="jeans", limit=1000)["result"]

    combined_by_hand = [asset for asset in assets
                        if asset["asset_subdir"] == "clothes"
                        and "jeans" in (asset["name"] + asset["label"]).lower()]
    report.check("filters: name_contains, pack, asset_subdir, and the three combining",
                 by_name["total_count"] == lowercase["total_count"]
                 and by_pack["total_count"] == uppercase_pack["total_count"]
                 and by_subdir["total_count"] > 0
                 and combined["total_count"] == len(combined_by_hand),
                 dict(name_contains_case=[by_name["total_count"], lowercase["total_count"]],
                      pack_case=[by_pack["total_count"], uppercase_pack["total_count"]],
                      subdir_case=by_subdir["total_count"],
                      combined=[combined["total_count"], len(combined_by_hand)]))


def _check_three_answers(tools: dict, report: Report) -> None:
    misspelled_subdir = tools["mpfb_list_assets"](asset_subdir="clothing")["result"]
    misspelled_pack = tools["mpfb_list_assets"](pack="no_such_pack_at_all")["result"]
    empty_subdir = tools["mpfb_list_assets"](asset_subdir="ink_layers", limit=1000)["result"]
    report.check("a misspelled subdir, a misspelled pack and an empty subdir are three answers",
                 misspelled_subdir["subdir_recognized"] is False
                 and misspelled_pack["pack_recognized"] is False
                 and empty_subdir["subdir_recognized"] is True,
                 dict(misspelled_subdir=dict(recognized=misspelled_subdir["subdir_recognized"],
                                             count=misspelled_subdir["count"]),
                      misspelled_pack=dict(recognized=misspelled_pack["pack_recognized"],
                                           count=misspelled_pack["count"]),
                      ink_layers=dict(recognized=empty_subdir["subdir_recognized"],
                                      count=empty_subdir["count"])))


def _check_paging(tools: dict, report: Report) -> None:
    unpaged = tools["mpfb_list_assets"](asset_subdir="clothes", limit=1000)["result"]
    pages = []
    truncated = []
    for offset in (0, 250, 500):
        page = tools["mpfb_list_assets"](
            asset_subdir="clothes", limit=250, offset=offset)["result"]
        pages.extend(page["assets"])
        truncated.append(page["truncated"])
    past_end = tools["mpfb_list_assets"](asset_subdir="clothes", offset=100000)["result"]
    report.check("paging concatenates to the unpaged listing",
                 [asset["fragment"] for asset in pages]
                 == [asset["fragment"] for asset in unpaged["assets"]]
                 and past_end["count"] == 0,
                 dict(unpaged=unpaged["total_count"], paged=len(pages),
                      truncated=truncated, past_end=past_end["count"]))


def _check_applied(tools: dict, report: Report, assets: list) -> None:
    """One asset from four different subdirs, applied through the tools that take them."""
    outcomes = []
    ok = True
    created = tools["mpfb_create_human"]()["result"]["object_name"]
    for subdir, tool_name in (("clothes", "mpfb_add_asset"), ("hair", "mpfb_add_asset"),
                              ("proxymeshes", "mpfb_add_asset"), ("skins", "mpfb_set_skin")):
        candidates = [asset for asset in assets if asset["asset_subdir"] == subdir]
        if not candidates:
            outcomes.append(dict(subdir=subdir, skipped="no assets in this subdir"))
            continue
        entry = candidates[0]
        if tool_name == "mpfb_add_asset":
            response = tools["mpfb_add_asset"](
                name=created, fragment=entry["fragment"], asset_type=entry["object_type"])
        else:
            response = tools["mpfb_set_skin"](name=created, fragment=entry["fragment"])
        result = response.get("result") or dict()
        outcome = dict(subdir=subdir, fragment=entry["fragment"],
                       reported_path=entry["path"],
                       resolved_path=result.get("resolved_path"),
                       status=response.get("status"),
                       applied=bool(result.get("added") or result.get("applied")))
        if not outcome["applied"] or outcome["resolved_path"] != entry["path"]:
            ok = False
            outcome["message"] = response.get("message") or result.get("message")
        outcomes.append(outcome)
    report.check("assets reported here can actually be applied", ok, outcomes)


_ON_DISK_CODE = '''
import os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
AssetService = services["AssetService"]

# ASSET_LIBRARY_SECTIONS is module-level in assetservice.py, not a member of
# AssetService and not in the SERVICES dict - the same reach the shared
# asset_sections.py fragment makes.
sections = sys.modules[AssetService.__module__].ASSET_LIBRARY_SECTIONS

files_by_subdir = dict()
for section in sections:
    subdir = section["asset_subdir"]
    extension = section["asset_type"]
    found = []
    for root in AssetService.get_asset_roots(subdir):
        for dirpath, subdirs, filenames in os.walk(str(root)):
            for filename in filenames:
                if filename.endswith("." + extension):
                    found.append(os.path.join(dirpath, filename))
    files_by_subdir[subdir] = sorted(found)

result = dict(
    section_order=[section["asset_subdir"] for section in sections],
    files_by_subdir=dict((k, v) for k, v in files_by_subdir.items()),
)
'''


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
