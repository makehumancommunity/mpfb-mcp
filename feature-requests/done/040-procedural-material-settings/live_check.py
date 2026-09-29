# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 040's own live check: the material settings pair on a real install.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. Like FR 034's, it drives the
**real mpfb-mcp tools over the real socket**: it starts a headless Blender
running the bridge on a spare port, points ``MPFB_BRIDGE_PORT`` at it, and calls
the tools the way an MCP client would, against the **installed asset library**
rather than the bridge tests' fixture files.

    PYTHONPATH=. python3 feature-requests/done/040-procedural-material-settings/live_check.py

**It writes one file outside that Blender**, the preset the round trip needs,
as ``human.fr040_live_check.json`` in MPFB's user config directory, and deletes
it again however the run ends.

It builds the request's size case - procedural eyes, a LAYERED skin, hair,
eyebrows, eyelashes and two garments, one of them the first ``casualsuit01`` the
library offers (``female_casualsuit01`` on the machine this ran on), whose MHMAT
has an AO map - and then checks:

1. **Every section applies**, and the garment with the AO map reports ``aoMix``
   as its node, with what that node's inputs are.
2. **The answer's size**, whole and per section, against the ~16 KB line
   requirement 7 draws; and the latency of the read and a write, against the
   100 ms the request sets.
3. **The pitfalls**: a linked region colour is refused naming ``color``'s socket;
   a group input outside its declared range is stored as given (not clamped) for
   the one socket MPFB itself contradicts; a colour component above 1.0 is kept;
   a built-in ``Factor`` outside 0-1 is refused.
4. **The summary's three colours** equal the read's.
5. **The preset round trip** (requirement 16): after a write, the preset file
   MPFB writes holds exactly what the read reports, and the character
   ``mpfb_create_human_from_preset`` builds from it reads back the same.

Prints PASS/FAIL per check and exits non-zero on any failure. It cannot judge
whether a colour looks right; nothing is rendered.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

BLENDER = os.environ.get("BLENDER_EXE", "/home/joepal/system/blender-5.1.0-linux-x64/blender")
PORT = int(os.environ.get("FR040_PORT", "9940"))
PRESET = "fr040_live_check"

# What each asset slot is looked up by, in the installed library.
ASSETS = (
    ("eyes", "Eyes", "high-poly", "PROCEDURAL_EYES"),
    ("hair", "Hair", "long01", None),
    ("eyebrows", "Eyebrows", "eyebrow001", None),
    ("eyelashes", "Eyelashes", "eyelashes01", None),
    ("clothes", "Clothes", "casualsuit01", None),
    ("clothes", "Clothes", "tight_jeans", None),
)

# The add-on's own headless entry point, called directly rather than through
# ``--command mpfb_bridge``. On the machine this ran on, the add-on is installed
# in two extension repositories - both symlinks to this checkout - so Blender
# registers the command twice and refuses to run either. Whichever copy loaded
# is this checkout's code.
START_BRIDGE = (
    "import sys; "
    "cli = [module for name, module in sorted(sys.modules.items()) "
    "if name.endswith('mpfb_bridge.cli')][0]; "
    "cli.cli_execute(['--port', '{port}'])"
)

SIZE_LINE = 16 * 1024
LATENCY_LINE = 0.100

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


def _first(tools, subdir, name_contains):
    assets = ok(tools["mpfb_list_assets"](asset_subdir=subdir, name_contains=name_contains,
                                          limit=5), "list_assets")["assets"]
    if not assets:
        raise SystemExit("this install has no {:s} asset matching {!r}".format(
            subdir, name_contains))
    return assets[0]


def build(tools):
    """The request's size case. Returns the basemesh name and the equipped objects by role."""
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    equipped = {}
    for subdir, object_type, name_contains, material_type in ASSETS:
        asset = _first(tools, subdir, name_contains)
        arguments = dict(name=name, fragment=asset["fragment"], object_type=object_type)
        if material_type is not None:
            arguments["material_type"] = material_type
        added = ok(tools["mpfb_add_asset"](**arguments), "add_asset " + name_contains)
        check("equipped " + name_contains, added["added"] is True, added["message"])
        equipped[name_contains] = added["asset_object_name"]
    skin = _first(tools, "skins", "young_caucasian_female")
    applied = ok(tools["mpfb_set_skin"](name=name, fragment=skin["fragment"],
                                        skin_type="LAYERED"), "set_skin")
    check("a LAYERED skin was applied", applied["applied"] is True, applied["message"])
    return name, equipped


def _timed(call):
    start = time.perf_counter()
    envelope = call()
    return envelope, time.perf_counter() - start


def _settings(answer):
    return dict(
        eyes=answer["eyes"]["settings"],
        skin={group: report["settings"] for group, report in answer["skin"]["groups"].items()},
        color_adjustments={record["uuid"]: record["settings"]
                           for record in answer["color_adjustments"] if record["applies"]},
    )


def check_sections_and_size(tools, name, equipped):
    envelope, _ = _timed(lambda: tools["mpfb_get_material_settings"](name=name))
    answer = ok(envelope, "get_material_settings")
    check("eyes apply", answer["eyes"]["applies"] is True, answer["eyes"]["reason"])
    check("skin applies, with MPFB's nine groups",
          answer["skin"]["applies"] is True and len(answer["skin"]["groups"]) == 9
          and answer["skin"]["groups_missing"] == [] and
          answer["skin"]["groups_not_serialized"] == [],
          sorted(answer["skin"].get("groups", {})))
    records = {record["object_name"]: record for record in answer["color_adjustments"]}
    applying = sorted(record["object_name"] for record in records.values() if record["applies"])
    print("colour adjustments that apply: {!r}".format(applying))
    check("five assets carry a colour adjustment (all but the eyes)", len(applying) == 5,
          applying)
    suit = records[equipped["casualsuit01"]]
    print("casualsuit01's node: {!r}, settings {!r}, linked {!r}, ranges {!r}".format(
        suit["node_name"], suit.get("settings"), suit.get("linked"), suit.get("ranges")))
    check("an asset with an AO map reports aoMix", suit["node_name"] == "aoMix",
          suit["node_name"])

    whole = len(json.dumps(envelope))
    per_section = {}
    for section in ("eyes", "skin", "color_adjustments"):
        per_section[section] = len(json.dumps(tools["mpfb_get_material_settings"](
            name=name, section=section)))
    print("answer size: whole {:d} B; by section {!r}".format(whole, per_section))
    check("the whole answer is past the 16 KB line, which is what earns the filter",
          whole > SIZE_LINE, whole)
    check("each section alone is within about 16 KB",
          all(size <= SIZE_LINE * 1.05 for size in per_section.values()), per_section)

    best = min(_timed(lambda: tools["mpfb_get_material_settings"](name=name))[1]
               for _ in range(3))
    print("read: {:.1f} ms, best of 3".format(best * 1000))
    check("the read is under 100 ms", best < LATENCY_LINE, best)
    return answer


def check_pitfalls(tools, name, answer):
    linked = ok(tools["mpfb_set_material_settings"](
        name=name, skin=[{"group": "body", "socket": "SkinColor",
                          "color": [0.3, 0.2, 0.1, 1.0]}]), "set_material_settings")
    error = (linked["resolution_errors"] or [{}])[0]
    check("a linked region colour is refused, naming color's SkinColor",
          error.get("reason") == "linked_socket"
          and error.get("write_instead") == {"group": "color", "socket": "SkinColor"}, error)

    body = answer["skin"]["groups"]["body"]
    print("body sockets whose value is outside their declared range: {!r}".format(
        body["values_outside_range"]))
    unclamped = ok(tools["mpfb_set_material_settings"](
        name=name, skin=[{"group": "body", "socket": "NavelWidthMultiplier", "value": 12.0}]),
        "set_material_settings")
    check("a group input outside its declared range is stored as given, where MPFB's own "
          "value already contradicts the range",
          unclamped["performed"] and unclamped["changes"][0]["new_value"] == 12.0,
          unclamped["changes"] or unclamped["resolution_errors"])

    bright = ok(tools["mpfb_set_material_settings"](
        name=name, eyes=[{"socket": "IrisMajorColor", "color": [2.0, 0.5, 0.1, 1.0]}]),
        "set_material_settings")
    check("a colour component above 1.0 is kept, not clamped",
          bright["performed"] and bright["changes"][0]["new_value"][0] == 2.0,
          bright["changes"])
    check("and its hex is clamped", bright["changes"][0]["new_srgb_hex"].startswith("#ff"),
          bright["changes"][0]["new_srgb_hex"])

    hair = [record for record in answer["color_adjustments"]
            if record["object_type"] == "Hair"][0]
    factor = ok(tools["mpfb_set_material_settings"](
        name=name, color_adjustments=[{"object_name": hair["object_name"], "socket": "Factor",
                                       "value": 1.5}]), "set_material_settings")
    check("a built-in Factor outside 0-1 is refused, since Blender would clamp it",
          [error["reason"] for error in factor["resolution_errors"]] == ["out_of_range"],
          factor["resolution_errors"])


def write_distinctive(tools, name, answer):
    hair = [record for record in answer["color_adjustments"] if record["object_type"] == "Hair"][0]
    suit = [record for record in answer["color_adjustments"] if record["node_name"] == "aoMix"][0]
    envelope, elapsed = _timed(lambda: tools["mpfb_set_material_settings"](
        name=name,
        eyes=[{"socket": "IrisMajorColor", "color": [0.05, 0.3, 0.08, 1.0]},
              {"socket": "IrisMinorColor", "color": [0.02, 0.08, 0.02, 1.0]}],
        skin=[{"group": "color", "socket": "SkinColor", "color": [0.45, 0.25, 0.15, 1.0]},
              {"group": "color", "socket": "SkinOverride", "value": 0.6},
              {"group": "color", "socket": "LipsColor", "color": [0.5, 0.1, 0.1, 1.0]},
              {"group": "color", "socket": "LipsOverride", "value": 0.8}],
        color_adjustments=[{"object_name": hair["object_name"], "socket": "Color1",
                            "color": [0.02, 0.01, 0.005, 1.0]},
                           {"object_name": hair["object_name"], "socket": "Factor",
                            "value": 0.6}] + [
            {"object_name": suit["object_name"], "socket": socket_name, "value": 0.5}
            for socket_name, value in suit["settings"].items()
            if isinstance(value, float) and socket_name not in suit["linked"]]))
    written = ok(envelope, "set_material_settings")
    check("a batch across all three sections is written", written["performed"] is True,
          written["resolution_errors"])
    print("write: {:.1f} ms, {:d} change(s)".format(elapsed * 1000, written["change_count"]))
    check("the write is under 100 ms", elapsed < LATENCY_LINE, elapsed)

    summary = ok(tools["mpfb_get_character_summary"](name=name), "get_character_summary")
    now = ok(tools["mpfb_get_material_settings"](name=name), "get_material_settings")
    check("the summary's iris colours are the read's",
          summary["material_settings"]["eyes"]["srgb_hex"] == {
              key: now["eyes"]["srgb_hex"][key] for key in ("IrisMajorColor", "IrisMinorColor")},
          summary["material_settings"]["eyes"])
    check("the summary's skin colour is the read's",
          summary["material_settings"]["skin"]["groups"]["color"]["srgb_hex"]["SkinColor"]
          == now["skin"]["groups"]["color"]["srgb_hex"]["SkinColor"],
          summary["material_settings"]["skin"])
    return now


def check_round_trip(tools, name, now):
    saved = ok(tools["mpfb_save_preset"](preset_name=PRESET, name=name, overwrite=True),
               "save_preset")
    path = saved["path"]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            preset = json.load(handle)
        expected = _settings(now)
        check("the preset file's eye settings are the read's",
              preset["eyes_material_settings"] == expected["eyes"])
        check("the preset file's skin settings are the read's",
              preset["skin_material_settings"] == expected["skin"])
        check("the preset file's colour adjustments are the read's",
              preset["color_adjustments"] == expected["color_adjustments"],
              sorted(preset["color_adjustments"]))

        created = ok(tools["mpfb_create_human_from_preset"](preset_name=PRESET,
                                                            load_clothes=True),
                     "create_human_from_preset")
        check("the preset built a new character", created["created"] is True,
              created["message"])
        rebuilt = _settings(ok(tools["mpfb_get_material_settings"](
            name=created["basemesh_name"]), "get_material_settings"))
        for section in ("eyes", "skin", "color_adjustments"):
            check("round trip: {:s} unchanged".format(section),
                  rebuilt[section] == expected[section],
                  _first_difference(rebuilt[section], expected[section]))
    finally:
        os.remove(path)
        print("removed {:s}".format(path))


def _first_difference(got, wanted):
    if got == wanted:
        return ""
    for key in sorted(set(got) | set(wanted)):
        if got.get(key) != wanted.get(key):
            return "{!r}: {!r} != {!r}".format(key, got.get(key), wanted.get(key))
    return ""


def main():
    os.environ["MPFB_BRIDGE_PORT"] = str(PORT)
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()

    blender = subprocess.Popen(
        [BLENDER, "--background", "-noaudio", "--python-expr", START_BRIDGE.format(port=PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for_port(PORT):
            raise SystemExit("the headless bridge never started listening on {:d}".format(PORT))
        name, equipped = build(tools)
        answer = check_sections_and_size(tools, name, equipped)
        check_pitfalls(tools, name, answer)
        now = write_distinctive(tools, name, answer)
        check_round_trip(tools, name, now)
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
