# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 046's own live check: the license in the catalogues, on the maintainer's full install.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. It drives the **real mpfb-mcp
tools over the real socket**, against a Blender already running with the MPFB
Bridge's server started (``MPFB_BRIDGE_PORT``, default 9877), on the developer's
real install with its community asset packs.

The community blender-mcp add-on's socket (``BLENDER_MCP_PORT``, default 9876) is
used once, for the one measurement no tool can make: how many files the
attribution's file-stem fallback reaches, which is what requirement 2 is decided
on. That walk imports the bridge's own ``shared/pack_attribution.py`` inside
Blender, so it measures the module the commands use.

    PYTHONPATH=. .venv/bin/python feature-requests/done/046-license-in-the-catalogues/live_check.py

It adds one dressed character to the open scene and leaves it there.

1. **The CC0 split**: ``mpfb_list_assets(asset_subdir="clothes", license="CC0")``
   is 226, and ``counts_by_license`` reproduces 226 / 392 / 21.
2. **The stem fallback, measured**: per subdir, how many files are attributed
   with and without it, and every file it attributes.
3. **``pack="_cc0"``** reports no row whose ``pack`` lacks ``_cc0``, and
   ``matched_packs`` shows the packs registered with nothing on disk.
4. **The five hair materials** the scene sessions used are ``CC0``, attributed
   to their ``system_hair_materials0N`` pack, by ``mpfb_list_asset_materials``
   and, once applied, by ``mpfb_get_object_info``.
5. **Response sizes** of a default page and a 1000-row page, before and after
   (before = the same answer with FR 046's keys removed).
6. **The summary**: a dressed character's ``equipped_assets`` carries the
   licenses ``mpfb_get_object_info`` reports, and what that adds to its size.
   **Found here, and not this request's**: ``ponytail01``, which carries a
   sub-rig, is in neither the basemesh's ``related_objects`` nor the summary,
   because MPFB's ``find_related_objects()`` does not walk past a ``Subrig``.
   The two agree, so the check holds; the finding records what is missing.

Prints PASS/FAIL per check, then the findings, and exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

BLENDER_MCP_PORT = int(os.environ.get("BLENDER_MCP_PORT", "9876"))

# FR 046's new row and answer keys, removed to reconstruct the "before" size.
NEW_ROW_KEYS = ("packs", "license", "author", "source_url")
NEW_ANSWER_KEYS = ("counts_by_license", "license_unknown_count", "matched_packs",
                   "requested_license", "license_recognized", "known_licenses",
                   "attribution_conflicts")

# The hair, and the alternative material on it, of the FULL_SESSION line-up and
# the man-and-woman scene: five materials by four authors.
HAIR_MATERIALS = (
    ("short02", "bogdan666_short_02_gray", "system_hair_materials01"),
    ("long01", "toigo_long_01_black", "system_hair_materials01"),
    # Beside its sibling: the check wears one hair at a time, in this order.
    ("long01", "ricardo2020_long_01_bronze", "system_hair_materials03"),
    ("short04", "toigo_short_04_ginger", "system_hair_materials01"),
    ("ponytail01", "dariush086_ponytail01_pink", "system_hair_materials01"),
)

FAILURES = []
FINDINGS = {}


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print("[{:s}] {:s}{:s}".format(status, label, "" if not detail else " - " + str(detail)),
          flush=True)
    if not condition:
        FAILURES.append(label)


def ok(envelope, what):
    if envelope.get("status") != "ok":
        raise SystemExit("{:s} failed: {!r}".format(what, envelope))
    return envelope["result"]


def in_blender(code):
    """Run ``code`` in the running Blender through the community add-on; returns its stdout."""
    with socket.create_connection(("127.0.0.1", BLENDER_MCP_PORT), timeout=300) as connection:
        connection.sendall(json.dumps({"type": "execute_code",
                                       "params": {"code": code}}).encode("utf-8"))
        buffer = b""
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            buffer += chunk
            try:
                answer = json.loads(buffer.decode("utf-8"))
                break
            except ValueError:
                continue
    if answer.get("status") != "success":
        raise SystemExit("Blender-side code failed: {!r}".format(answer))
    return answer["result"]["result"]


def blender_json(code):
    output = in_blender("import bpy, json, os, sys\n" + code)
    return json.loads([line for line in output.splitlines() if line.strip()][-1])


def size(value):
    return len(json.dumps(value).encode("utf-8"))


def without_new_keys(answer):
    old = {key: value for key, value in answer.items() if key not in NEW_ANSWER_KEYS}
    old["assets"] = [{key: value for key, value in row.items() if key not in NEW_ROW_KEYS}
                     for row in answer["assets"]]
    return old


def cc0_split(tools):
    """Requirement 8 and 9 on the install the request was scoped against."""
    answer = ok(tools["mpfb_list_assets"](asset_subdir="clothes", license="CC0", limit=1000),
                "list_assets CC0 clothes")
    FINDINGS["clothes_counts_by_license"] = answer["counts_by_license"]
    FINDINGS["clothes_license_unknown_count"] = answer["license_unknown_count"]
    check("226 CC0 garments", answer["total_count"] == 226, answer["total_count"])
    check("the split is 226 / 392 / 21",
          answer["counts_by_license"] == {"CC-BY": 392, "CC0": 226}
          and answer["license_unknown_count"] == 21,
          (answer["counts_by_license"], answer["license_unknown_count"]))
    check("every CC0 row says CC0", all(row["license"] == "CC0" for row in answer["assets"]))
    check("the message says the unknown ones were excluded, not checked",
          "excluded, not checked" in answer["message"], answer["message"])
    check("known_licenses is the metadata's own", answer["known_licenses"] == ["CC-BY", "CC0"],
          answer["known_licenses"])
    check("no claimants disagree on this install", answer["attribution_conflicts"] == [])

    lower = ok(tools["mpfb_list_assets"](asset_subdir="clothes", license="cc0", limit=1),
               "list_assets cc0")
    check("the filter is case-insensitive", lower["total_count"] == 226, lower["total_count"])

    everything = ok(tools["mpfb_list_assets"](limit=1), "list_assets everything")
    FINDINGS["all_subdirs_counts_by_license"] = everything["counts_by_license"]
    FINDINGS["all_subdirs_license_unknown_count"] = everything["license_unknown_count"]
    FINDINGS["all_subdirs_total"] = everything["total_count"]
    unknown = [row["fragment"] for row in ok(tools["mpfb_list_assets"](
        asset_subdir="clothes", limit=1000), "clothes")["assets"] if row["license"] is None]
    FINDINGS["clothes_without_a_license"] = unknown


STEM_FALLBACK_CODE = '''
bridge = [m for n, m in sys.modules.items() if n.endswith("mpfb_bridge")][0]
attribution = sys.modules[bridge.__name__ + ".shared.pack_attribution"]
services = [m for n, m in sys.modules.items() if n.endswith("mpfb")][0].MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
asset_service = services["AssetService"]
index = attribution.read_index(services)
report = dict()
for subdir in ("clothes", "eyebrows", "eyelashes", "eyes", "hair", "proxymeshes", "skins",
               "teeth", "tongue"):
    roots = [str(root) for root in asset_service.get_asset_roots(subdir) or []]
    normalized = [os.path.normpath(root) for root in roots]
    files = []
    for root in roots:
        for directory, _dirs, names in os.walk(root):
            for name in names:
                if os.path.splitext(name)[1] in (".mhclo", ".mhmat", ".proxy"):
                    files.append(os.path.join(directory, name))
    row = dict(files=len(files), attributed=0, attributed_without_fallback=0, by_fallback=[],
               in_root=0)
    for path in files:
        directory = os.path.normpath(os.path.dirname(path))
        by_directory = (directory not in normalized
                        and bool(index.claims.get(os.path.basename(directory))))
        row["in_root"] += directory in normalized
        answer = attribution.attribute(index, path, roots)
        if answer["packs"]:
            row["attributed"] += 1
        if by_directory:
            row["attributed_without_fallback"] += 1
        elif answer["packs"]:
            root = [root for root in roots if path.startswith(root)][0]
            row["by_fallback"].append(os.path.relpath(path, root))
    report[subdir] = row
print(json.dumps(report))
'''


def stem_fallback():
    """Requirement 2: what the file-stem fallback reaches, measured with the module itself."""
    report = blender_json(STEM_FALLBACK_CODE)
    FINDINGS["stem_fallback_by_subdir"] = report
    reached = [(subdir, path) for subdir, row in report.items() for path in row["by_fallback"]]
    check("the fallback reaches nine files", len(reached) == 9, reached)
    check("all of them under eyes/materials",
          all(subdir == "eyes" and path.startswith("materials" + os.sep) for subdir, path in reached),
          reached)


def pack_filter(tools):
    """Requirements 7 and 10."""
    answer = ok(tools["mpfb_list_assets"](pack="_cc0", limit=1000), "list_assets _cc0")
    offenders = [row["fragment"] for row in answer["assets"] if "_cc0" not in row["pack"]]
    check("pack=\"_cc0\" reports no row whose pack lacks _cc0", offenders == [], offenders)
    # The rows the old rule - the first claimant - would have reported wrongly.
    FINDINGS["cc0_rows_whose_first_claimant_is_not_cc0"] = sum(
        1 for row in answer["assets"] if row["pack"] != row["packs"][0])
    empty = sorted(name for name, count in answer["matched_packs"].items() if count == 0)
    FINDINGS["cc0_packs_with_nothing_installed"] = empty
    FINDINGS["cc0_matched_packs"] = answer["matched_packs"]
    check("accessories01_cc0 shows 0 installed", answer["matched_packs"].get(
        "accessories01_cc0") == 0, answer["matched_packs"].get("accessories01_cc0"))


def find_fragment(tools, subdir, name):
    rows = ok(tools["mpfb_list_assets"](asset_subdir=subdir, name_contains=name, limit=1000),
              "find " + name)["assets"]
    exact = [row for row in rows if row["name"] == name]
    if not exact:
        raise SystemExit("{:s}/{:s} is not installed".format(subdir, name))
    return exact[0]


def hair_and_summary(tools):
    """Requirements 11, 13 and 14 on one dressed character."""
    created = ok(tools["mpfb_create_human"](), "create_human")
    name = created["basemesh_name"]
    ok(tools["mpfb_place_character"](name=name, position={"x": 8.0, "y": 4.0}), "place")
    ok(tools["mpfb_add_rig"](name=name, identifier="default"), "add_rig")
    ok(tools["mpfb_set_skin"](name=name, skin_type="LAYERED"), "set_skin")
    equipped = dict()
    for subdir, asset, object_type in (
            ("eyes", "high-poly", "Eyes"), ("eyebrows", "eyebrow001", "Eyebrows"),
            ("eyelashes", "eyelashes01", "Eyelashes"), ("teeth", "teeth_base", "Teeth"),
            ("tongue", "tongue01", "Tongue"), ("clothes", "male_elegantsuit01", "Clothes"),
            ("clothes", "shoes04", "Clothes"), ("clothes", "fedora01", "Clothes")):
        row = find_fragment(tools, subdir, asset)
        added = ok(tools["mpfb_add_asset"](name=name, fragment=row["fragment"],
                                           object_type=object_type), "add " + asset)
        equipped[asset] = (added["asset_object_name"], row)

    licenses = dict()
    hairs = dict()
    for hair, material, pack in HAIR_MATERIALS:
        if hair not in hairs:
            row = find_fragment(tools, "hair", hair)
            if hairs:
                ok(tools["mpfb_remove_asset"](name=list(hairs.values())[-1]), "remove hair")
            hairs[hair] = ok(tools["mpfb_add_asset"](name=name, fragment=row["fragment"],
                                                     object_type="Hair"),
                             "add " + hair)["asset_object_name"]
            equipped["hair"] = (hairs[hair], row)
        listed = ok(tools["mpfb_list_asset_materials"](name=hairs[hair]), "materials " + hair)
        entry = [item for item in listed["materials"] if item["name"] == material][0]
        licenses[material] = (entry["license"], entry["packs"], entry["author"])
        check("{:s} is CC0 in {:s}".format(material, pack),
              entry["license"] == "CC0" and entry["packs"] == [pack], licenses[material])
        applied = ok(tools["mpfb_set_asset_material"](name=hairs[hair],
                                                      fragment=entry["fragment"]),
                     "apply " + material)
        check("{:s} applied".format(material), applied.get("applied") is True)
        info = ok(tools["mpfb_get_object_info"](name=hairs[hair]), "info")["asset_info"]
        check("get_object_info names {:s}'s license and pack".format(material),
              (info["material_license"], info["material_packs"], info["material_author"])
              == licenses[material], (info["material_license"], info["material_packs"]))
    FINDINGS["hair_materials"] = licenses
    check("five materials by four authors",
          len(licenses) == 5 and len({value[2] for value in licenses.values()}) == 4,
          sorted({value[2] for value in licenses.values()}))

    # Every equipped asset's license equals its catalogue row's.
    disagreements = []
    for asset, (object_name, row) in equipped.items():
        info = ok(tools["mpfb_get_object_info"](name=object_name), "info")["asset_info"]
        if (info["license"], info["author"], info["packs"]) != \
                (row["license"], row["author"], row["packs"]):
            disagreements.append((asset, info["license"], row["license"]))
    check("every equipped asset reports its catalogue row's attribution", disagreements == [],
          disagreements)

    summary = ok(tools["mpfb_get_character_summary"](name=name), "summary")
    summarized = {row["name"]: row["license"] for row in summary["equipped_assets"]}
    # Against the basemesh's relatives, which is what the summary reads: a
    # garment behind its own sub-rig is not among them (see the finding below).
    family = ok(tools["mpfb_get_object_info"](name=name), "info")["related_objects"]
    expected = {entry["name"]: entry["asset_info"]["license"] for entry in family
                if entry["object_type"] not in ("Skeleton", "Subrig")}
    check("the summary's licenses are get_object_info's", summarized == expected,
          (summarized, expected))
    FINDINGS["equipped_but_not_in_the_summary"] = sorted(
        object_name for object_name, _row in equipped.values() if object_name not in summarized)
    stripped = json.loads(json.dumps(summary))
    for row in stripped["equipped_assets"]:
        del row["license"]
        del row["material_license"]
    del stripped["skin"]["material_license"]
    FINDINGS["summary_bytes"] = {"after": size(summary), "before": size(stripped),
                                 "assets": len(summary["equipped_assets"]),
                                 "modifier_count": summary["targets"]["modifier_count"]}
    # FR 034's worst case: this answer with the rollup at its caps.
    worst = size(summary) + 25 * 105 + 8 * 115
    FINDINGS["summary_worst_case_estimate_bytes"] = worst
    check("the summary's worst case stays under 8 KB", worst < 8192, worst)


def sizes_and_cost(tools):
    """Response sizes before and after, and that attribution adds no read per row."""
    for label, arguments in (("default_page", dict()), ("page_of_1000", dict(limit=1000))):
        start = time.perf_counter()
        answer = ok(tools["mpfb_list_assets"](**arguments), "list_assets " + label)
        elapsed = time.perf_counter() - start
        FINDINGS["size_" + label] = {"before": size(without_new_keys(answer)),
                                     "after": size(answer), "rows": answer["count"],
                                     "seconds": round(elapsed, 3)}


def main():
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()
    ok(tools["mpfb_list_assets"](limit=1, refresh=True), "refresh")

    cc0_split(tools)
    stem_fallback()
    pack_filter(tools)
    sizes_and_cost(tools)
    hair_and_summary(tools)

    print(json.dumps(FINDINGS, indent=1, sort_keys=True))
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
