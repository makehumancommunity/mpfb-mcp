# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 034's own live check: the summary against the tools it summarizes.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance and verification/README.md for
why it does not belong in verification/. Like FR 027's, it drives the **real
mpfb-mcp tools over the real socket**: it starts a headless Blender running the
bridge on a spare port, points ``MPFB_BRIDGE_PORT`` at it, and calls the tools
the way an MCP client would. The characters it builds live in that throwaway
Blender and die with it; it writes no file outside it.

    PYTHONPATH=. python3 feature-requests/034-character-summary/live_check.py
    PYTHONPATH=. python3 feature-requests/034-character-summary/live_check.py --snapshot OUT.json

**It builds the worst case the request names**: every macro slider moved, a
Rigify rig generated after the garments were attached, all eight mesh asset
types, a non-default skin, a few dozen detail targets with left/right
differences, an expression from the library, and a face unit composed on top of
it. Then:

1. ``mpfb_get_character_summary`` is called on it, and **every field it shares
   with a detailed tool is compared with that tool's answer**, section by
   section, on the same character in the same state.
2. The same is done for a bare basemesh and for a miss.
3. The answer's size is measured against the 8 KB target, and its latency
   against the sum of the calls it replaces.

``--snapshot`` is the other half of the request's claim, and runs instead of
the above: it builds the same character and writes the **detailed** commands'
answers - ``mpfb_get_macro_details``, ``mpfb_get_object_info`` on every object
in the family, ``mpfb_get_target_stack`` under three argument sets,
``mpfb_get_face_units`` and ``mpfb_get_expression``, plus their misses - to one
JSON file with sorted keys. Run at the commit before the extraction and again
after each move, a ``diff`` of two snapshots is the byte-for-byte check the
bridge tests only approximate. The one expected difference is
``mpfb_get_macro_details`` gaining ``macro_drift``.

Prints PASS/FAIL per check and exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

BLENDER = os.environ.get("BLENDER_EXE", "/home/joepal/system/blender-5.1.0-linux-x64/blender")
PORT = int(os.environ.get("FR034_PORT", "9897"))

# The eight mesh asset types, as list_assets names their subdirs.
ASSET_SUBDIRS = ("proxymeshes", "eyes", "eyebrows", "eyelashes", "hair", "teeth", "tongue",
                 "clothes")

# Sections to take detail targets from, and how many categories from each. A
# spread across the body rather than one section, so the rollup's section walk
# is exercised; ~40 categories in all, some of them sided.
TARGET_SECTIONS = (("nose", 6), ("chin", 4), ("ears", 5), ("eyes", 6), ("mouth", 6),
                   ("cheek", 3), ("torso", 5), ("arms", 3), ("legs", 3))

# What the target is, in bytes of JSON, and what the summary must not exceed.
SIZE_TARGET = 8 * 1024

FAILURES = []


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


def wait_for_port(port, seconds=90.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return True
        except OSError:
            time.sleep(0.5)
    return False


# --------------------------------------------------------------------------
# The characters.
# --------------------------------------------------------------------------


def _modifiers_to_set(tools):
    """About forty modeling changes across nine sections, some of them lopsided."""
    entries = []
    for section, wanted in TARGET_SECTIONS:
        categories = ok(tools["mpfb_list_targets"](section=section), "list_targets")["categories"]
        for index, category in enumerate(categories[:wanted]):
            opposed = bool(category.get("opposites", {}).get("negative-unsided")
                           or category.get("opposites", {}).get("negative-left"))
            value = (-0.3 if opposed and index % 2 else 0.35)
            if category["has_left_and_right"]:
                entries.append(dict(section=section, category=category["name"],
                                    side="left", value=value))
                entries.append(dict(section=section, category=category["name"],
                                    side="right", value=round(value * 0.5, 3)))
            else:
                entries.append(dict(section=section, category=category["name"],
                                    side="unsided", value=value))
    return entries


def build_worst_case(tools):
    """The request's worst-case character. Returns its basemesh name."""
    name = ok(tools["mpfb_create_human"](
        gender=0.8, age=0.6, muscle=0.7, weight=0.4, proportions=0.6, height=0.65,
        cupsize=0.3, firmness=0.55, race_asian=0.2, race_caucasian=0.5, race_african=0.3),
        "create_human")["object_name"]

    # The rig before the garments, since a garment is rigged only if a rig
    # exists when it is attached; generated afterwards, as the server's
    # instructions say.
    ok(tools["mpfb_add_rig"](name=name, identifier="rigify.human"), "add_rig")
    for subdir in ASSET_SUBDIRS:
        asset = ok(tools["mpfb_list_assets"](asset_subdir=subdir, limit=1),
                   "list_assets")["assets"][0]
        ok(tools["mpfb_add_asset"](name=name, fragment=asset["fragment"],
                                   asset_type=asset["object_type"]), "add_asset " + subdir)
    ok(tools["mpfb_generate_rigify_rig"](name=name), "generate_rigify_rig")

    skin = ok(tools["mpfb_list_assets"](asset_subdir="skins", limit=1), "list_assets")["assets"][0]
    ok(tools["mpfb_set_skin"](name=name, fragment=skin["fragment"], skin_type="ENHANCED"),
       "set_skin")

    ok(tools["mpfb_set_targets"](name=name, modifiers=_modifiers_to_set(tools), refit=True),
       "set_targets")

    expressions = [entry["fragment"] for entry in
                   ok(tools["mpfb_list_expressions"](), "list_expressions")["expressions"]]
    library = "Wink.json" if "Wink.json" in expressions else expressions[0]
    ok(tools["mpfb_apply_expressions"](
        name=name, expressions=[{"fragment": library, "weight": 0.8}]), "apply_expressions")
    ok(tools["mpfb_set_face_units"](
        name=name, face_units=[{"face_unit": "browInnerUp", "weight": 0.45},
                               {"face_unit": "jawOpen", "weight": 0.2}]), "set_face_units")
    return name


def family_of(tools, name):
    """Every object mpfb_get_object_info names in the character's family, subject first."""
    info = ok(tools["mpfb_get_object_info"](name=name), "get_object_info")
    names = [info["name"]]
    names += [entry["name"] for entry in info["related_objects"]]
    names += [entry["name"] for entry in info["other_related_objects"]]
    return names


# --------------------------------------------------------------------------
# --snapshot: the detailed answers, for a before/after diff.
# --------------------------------------------------------------------------


def snapshot(tools, path):
    worst = build_worst_case(tools)
    bare = ok(tools["mpfb_create_human"](), "create_human")["object_name"]
    plain_miss = "fr034-no-such-object"

    answers = {}
    for label, subject in (("worst", worst), ("bare", bare), ("miss", plain_miss)):
        answers[label] = {
            "get_macro_details": tools["mpfb_get_macro_details"](name=subject),
            "get_target_stack": tools["mpfb_get_target_stack"](name=subject),
            "get_target_stack_everything": tools["mpfb_get_target_stack"](
                name=subject, include_macro=True, include_expressions=True, limit=1000),
            "get_target_stack_filtered": tools["mpfb_get_target_stack"](
                name=subject, name_contains="nose", limit=3, offset=1),
            "get_face_units": tools["mpfb_get_face_units"](name=subject),
            "get_expression": tools["mpfb_get_expression"](name=subject),
        }
    for label, subject in (("worst", worst), ("bare", bare)):
        answers[label]["get_object_info"] = {
            member: tools["mpfb_get_object_info"](name=member)
            for member in family_of(tools, subject)}
    answers["miss"]["get_object_info"] = tools["mpfb_get_object_info"](name=plain_miss)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(answers, handle, indent=1, sort_keys=True)
    print("wrote {:s}: {:d} bytes".format(path, os.path.getsize(path)))
    return 0


# --------------------------------------------------------------------------
# The check proper.
# --------------------------------------------------------------------------


def _pick(dictionary, keys):
    return {key: dictionary.get(key) for key in keys}


def _compare_phenotype(summary, tools, name):
    macro = ok(tools["mpfb_get_macro_details"](name=name), "get_macro_details")
    phenotype = summary["phenotype"]
    shared = ("macro_details", "race_sum", "race_normalized", "macro_drift")
    check("phenotype agrees with mpfb_get_macro_details",
          _pick(phenotype, shared) == _pick(macro, shared),
          (_pick(phenotype, shared), _pick(macro, shared)))
    for key in ("subject_name", "subject_resolved_by", "basemesh_name"):
        check("{:s} agrees with mpfb_get_macro_details".format(key),
              summary[key] == macro[key], (summary[key], macro[key]))
    return macro


def _compare_rig_assets_skin(summary, tools, name):
    info = ok(tools["mpfb_get_object_info"](name=summary["basemesh_name"]), "get_object_info")
    skin = summary["skin"]
    check("skin agrees with mpfb_get_object_info's basemesh asset_info",
          skin == _pick(info["asset_info"], ("material_type", "material_source", "mhmat_path")),
          (skin, info["asset_info"]))

    rig = summary["rig"]
    skeletons = [entry for entry in info["related_objects"]
                 if entry["object_type"] == "Skeleton"]
    if rig is None:
        check("no rig in the summary, and none among the basemesh's relatives", not skeletons,
              skeletons)
    else:
        rig_info = ok(tools["mpfb_get_object_info"](name=rig["name"]), "get_object_info rig")
        expected = dict(name=rig_info["name"], object_type=rig_info["object_type"],
                        in_current_scene=rig_info["in_current_scene"],
                        rigify_role=rig_info["rigify_role"])
        expected.update(_pick(rig_info["asset_info"], ("rig_type", "rig_definition_path")))
        check("rig agrees with mpfb_get_object_info on the rig", rig == expected,
              (rig, expected))
        check("the rig is one of the basemesh's Skeleton relatives",
              rig["name"] in [entry["name"] for entry in skeletons], skeletons)

    expected_assets = []
    for entry in info["related_objects"]:
        if entry["object_type"] in (None, "Skeleton", "Subrig", "Basemesh"):
            continue
        row = dict(name=entry["name"], object_type=entry["object_type"],
                   in_current_scene=entry["in_current_scene"])
        row.update(_pick(entry["asset_info"], ("asset_source", "material_type",
                                                "material_source")))
        expected_assets.append(row)
    expected_assets.sort(key=lambda row: (row["object_type"], row["name"]))
    check("assets agree with mpfb_get_object_info's related objects",
          summary["assets"] == expected_assets, (summary["assets"], expected_assets))
    return info


def _compare_targets(summary, tools, name):
    stack = ok(tools["mpfb_get_target_stack"](name=name), "get_target_stack")
    shared = ("modifiers", "asymmetries", "counts_by_kind", "total_count")
    check("targets agree with mpfb_get_target_stack's defaults",
          summary["targets"] == _pick(stack, shared),
          (summary["targets"], _pick(stack, shared)))
    return stack


def _compare_face(summary, tools, name):
    units = ok(tools["mpfb_get_face_units"](name=name), "get_face_units")
    expression = ok(tools["mpfb_get_expression"](name=name), "get_expression")
    face = summary["face"]
    check("faceunits01_installed agrees with mpfb_get_face_units",
          face["faceunits01_installed"] == units["faceunits01_installed"])
    check("face_units agree with mpfb_get_face_units' non-zero units",
          face["face_units"] == [dict(face_unit=entry["face_unit"], weight=entry["weight"])
                                 for entry in units["face_units"]],
          (face["face_units"], units["face_units"]))
    check("applied_expressions agree with mpfb_get_expression",
          face["applied_expressions"] == [
              _pick(row, ("fragment", "weight", "resolved"))
              for row in expression["applied_expressions"]],
          (face["applied_expressions"], expression["applied_expressions"]))
    for key in ("matches_stack", "unexplained_face_units"):
        check("{:s} agrees with mpfb_get_expression".format(key),
              face[key] == expression[key], (face[key], expression[key]))


def _timed(call):
    started = time.perf_counter()
    envelope = call()
    return envelope, time.perf_counter() - started


def _latency(tools, name, rig_name):
    """Best of three for the summary, and for the calls it replaces."""
    replaced = (
        lambda: tools["mpfb_get_macro_details"](name=name),
        lambda: tools["mpfb_get_object_info"](name=name),
        lambda: tools["mpfb_get_object_info"](name=rig_name),
        lambda: tools["mpfb_get_target_stack"](name=name),
        lambda: tools["mpfb_get_face_units"](name=name),
        lambda: tools["mpfb_get_expression"](name=name),
    )
    summary_times = [_timed(lambda: tools["mpfb_get_character_summary"](name=name))[1]
                     for _ in range(3)]
    per_call = [min(_timed(call)[1] for _ in range(3)) for call in replaced]
    return min(summary_times), per_call


def check_worst_case(tools):
    name = build_worst_case(tools)
    print("worst-case character: {!r}".format(name))
    # Asked by a garment's name, so that the family resolution is exercised.
    garment = [member for member in family_of(tools, name) if member != name][0]
    envelope = tools["mpfb_get_character_summary"](name=garment)
    summary = ok(envelope, "get_character_summary")
    size = len(json.dumps(envelope, separators=(",", ":")))
    print(json.dumps(summary, indent=1))

    check("found", summary["found"] is True)
    check("resolved from a garment to the basemesh", summary["basemesh_name"] == name
          and summary["subject_name"] == garment, (summary["subject_name"],
                                                    summary["basemesh_name"]))
    _compare_phenotype(summary, tools, garment)
    _compare_rig_assets_skin(summary, tools, name)
    _compare_targets(summary, tools, name)
    _compare_face(summary, tools, name)

    check("the rig is the generated one", summary["rig"] is not None
          and summary["rig"]["rigify_role"] == "generated_rig", summary["rig"])
    check("all eight asset types are listed",
          sorted(set(row["object_type"] for row in summary["assets"])) == sorted(
              ["Proxymeshes", "Eyes", "Eyebrows", "Eyelashes", "Hair", "Teeth", "Tongue",
               "Clothes"]), [row["object_type"] for row in summary["assets"]])
    check("the skin is the ENHANCED one asked for",
          summary["skin"]["material_type"] == "ENHANCED", summary["skin"])
    check("dozens of modifiers are reported", len(summary["targets"]["modifiers"]) >= 30,
          len(summary["targets"]["modifiers"]))
    check("the composed units are unexplained by the stack",
          summary["face"]["matches_stack"] is False
          and set(entry["face_unit"] for entry in summary["face"]["unexplained_face_units"])
          >= {"browInnerUp", "jawOpen"}, summary["face"]["unexplained_face_units"])
    check("the answer is under {:d} bytes".format(SIZE_TARGET), size < SIZE_TARGET, size)

    best, per_call = _latency(tools, name, summary["rig"]["name"])
    print("summary: {:.1f} ms (best of 3), {:d} bytes; the six calls it replaces: {:s} = "
          "{:.1f} ms".format(best * 1000, size,
                             " + ".join("{:.1f}".format(value * 1000) for value in per_call),
                             sum(per_call) * 1000))
    check("one summary is cheaper than the six calls it replaces", best < sum(per_call),
          (best, sum(per_call)))
    check("and not much slower than the slowest of them", best < 2 * max(per_call),
          (best, max(per_call)))


def check_bare_and_miss(tools):
    bare = ok(tools["mpfb_create_human"](), "create_human")["object_name"]
    summary = ok(tools["mpfb_get_character_summary"](name=bare), "get_character_summary")
    check("bare: found", summary["found"] is True)
    _compare_phenotype(summary, tools, bare)
    _compare_rig_assets_skin(summary, tools, bare)
    _compare_targets(summary, tools, bare)
    _compare_face(summary, tools, bare)
    check("bare: no rig, no assets, no modifiers",
          summary["rig"] is None and summary["assets"] == []
          and summary["targets"]["modifiers"] == [], summary)

    miss = ok(tools["mpfb_get_character_summary"](name="fr034-no-such-object"),
              "get_character_summary")
    check("miss: found is false, with a message", miss["found"] is False and miss["message"])
    check("miss: every section key present",
          all(key in miss for key in ("phenotype", "rig", "assets", "skin", "targets", "face")),
          sorted(miss))


def main():
    os.environ["MPFB_BRIDGE_PORT"] = str(PORT)
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()

    snapshot_path = None
    if len(sys.argv) == 3 and sys.argv[1] == "--snapshot":
        snapshot_path = sys.argv[2]

    blender = subprocess.Popen(
        [BLENDER, "--background", "-noaudio", "--command", "mpfb_bridge", "--port", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for_port(PORT):
            raise SystemExit("the headless bridge never started listening on {:d}".format(PORT))
        if snapshot_path is not None:
            return snapshot(tools, snapshot_path)
        check_worst_case(tools)
        check_bare_and_miss(tools)
    finally:
        blender.terminate()
        try:
            blender.wait(timeout=20)
        except subprocess.TimeoutExpired:
            blender.kill()

    print()
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
