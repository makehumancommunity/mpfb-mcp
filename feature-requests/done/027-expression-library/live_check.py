# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 027's own live check: five claims this side of the socket cannot settle.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance and verification/README.md for
why it does not belong in verification/. Unlike FR 026's check, which ran
inside Blender, this one drives the **real mpfb-mcp tools over the real
socket**: it starts a headless Blender running the bridge on a spare port,
points ``MPFB_BRIDGE_PORT`` at it, and calls the tools the way an MCP client
would. The character it builds lives in that throwaway Blender and dies with
it. Prints PASS/FAIL per check and exits non-zero on any failure.

    PYTHONPATH=. python3 feature-requests/done/027-expression-library/live_check.py

It writes into the **developer's real MPFB directories**, because what is
being checked is the real install's layout, and it removes what it wrote in a
``finally``: ``fr027_live_check.json`` and ``fr027_shadow_probe.json`` in
the expressions directory of MPFB's user data, ``human.fr027_live_check.json``
in the user config directory, and - for claim 3 only - a temporary
``fr027_shadow_probe.json`` in ``mpfb_data/expressions``, which on a
development install is inside the mpfb2 source tree.

The five claims, each named in README.md's Tests section:

1. A face composed with ``mpfb_set_face_units`` really is destroyed by the next
   ``mpfb_apply_expressions`` - and the answer names what went.
2. ``ui.apply_assets.useexpression`` is in ``sys.modules`` on a normal install,
   so the panel can be kept in step: ``panel_synced`` is true after an apply,
   and a save registers a new slider. (The windowed half was confirmed
   separately, in the developer's GUI Blender; this is the headless half.)
3. A user-saved expression really is shadowed by a same-named file in a
   higher-priority root - MPFB's panel says the opposite.
4. An expression applied through the stack survives ``mpfb_save_preset`` /
   ``mpfb_create_human_from_preset``.
5. The whole sequence - compose, save, apply ``replace``, preset round trip -
   returns the composed face. That is the secondary goal.

Everything runs against a character carrying a rig and a garment, with
``refit`` left at each tool's default, so the refit path is exercised too.
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
PORT = int(os.environ.get("FR027_PORT", "9899"))

EXPRESSION_NAME = "fr027_live_check"
PROBE_NAME = "fr027_shadow_probe"
PRESET_NAME = "fr027_live_check"

# The format document's own example, used as the shadowing file's content so
# that no hand-simplified JSON stands in for a real expression.
FORMAT_DOC_EXAMPLE = {
    "format_version": 1,
    "name": "subtle-smile",
    "description": "A small, closed-mouth smile suitable for portrait shots.",
    "tags": ["happy", "subtle", "portrait"],
    "face_units": {"mouthSmileLeft": 0.35, "mouthSmileRight": 0.35,
                   "cheekSquintLeft": 0.15, "cheekSquintRight": 0.15},
    "author": "Jane Example",
    "copyright": "Copyright 2026 Jane Example",
    "license": "CC0",
    "homepage": "https://example.com/jane/expressions",
}

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


def live_units(tools, name):
    """The live face as {unit: weight}, via mpfb_get_face_units, all 52."""
    result = ok(tools["mpfb_get_face_units"](name=name, include_zero=True), "get_face_units")
    return {entry["face_unit"]: entry["weight"] for entry in result["face_units"]}


def main():  # pylint: disable=too-many-locals,too-many-statements
    os.environ["MPFB_BRIDGE_PORT"] = str(PORT)
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()

    blender = subprocess.Popen(
        [BLENDER, "--background", "-noaudio", "--command", "mpfb_bridge", "--port", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    written = []
    try:
        if not wait_for_port(PORT):
            raise SystemExit("the headless bridge never started listening on {:d}".format(PORT))

        listing = ok(tools["mpfb_list_expressions"](), "list_expressions")
        roots = listing["roots"]
        check("the pack is installed on this machine", listing["faceunits01_installed"] is True)
        user_expressions = [root for root in roots if "makehuman" in root] or roots[-1:]
        user_expressions = user_expressions[0]
        mpfb_expressions = roots[0]
        installed = [entry["fragment"] for entry in listing["expressions"]]
        print("roots: {!r}; installed: {!r}".format(roots, installed))
        library_fragment = "Wink.json" if "Wink.json" in installed else installed[0]

        # ------------------------------------------------------------------
        # A character with a rig and a garment.
        # ------------------------------------------------------------------
        name = ok(tools["mpfb_create_human"](), "create_human")["object_name"]
        rigs = ok(tools["mpfb_list_rigs"](), "list_rigs")["rigs"]
        standard = [rig for rig in rigs if rig.get("available") and rig.get("family") == "standard"]
        ok(tools["mpfb_add_rig"](name=name, identifier=standard[0]["identifier"]), "add_rig")
        garment = ok(tools["mpfb_list_assets"](asset_subdir="clothes", limit=1),
                     "list_assets")["assets"][0]
        ok(tools["mpfb_add_asset"](name=name, fragment=garment["fragment"],
                                   asset_type=garment["object_type"]), "add_asset")
        print("character {!r} with rig {!r} and garment {!r}".format(
            name, standard[0]["identifier"], garment["fragment"]))

        # ------------------------------------------------------------------
        # Claim 1: composed work is destroyed by the next library change.
        # ------------------------------------------------------------------
        composed = ok(tools["mpfb_set_face_units"](
            name=name, face_units=[{"face_unit": "browInnerUp", "weight": 0.5}]),
            "set_face_units")
        check("1a set_face_units reports the composed unit as unexplained",
              [entry["face_unit"] for entry in composed["unexplained_face_units"]]
              == ["browInnerUp"], composed["unexplained_face_units"])
        check("1b set_face_units refitted rig and garment", composed["refit_performed"] is True)
        read = ok(tools["mpfb_get_expression"](name=name), "get_expression")
        check("1c get_expression agrees", read["matches_stack"] is False
              and read["unexplained_face_units"] == composed["unexplained_face_units"])
        applied = ok(tools["mpfb_apply_expressions"](
            name=name, expressions=[{"fragment": library_fragment, "weight": 1.0}]),
            "apply_expressions")
        check("1d apply_expressions names the discarded unit",
              [entry["face_unit"] for entry in applied["discarded_face_units"]]
              == ["browInnerUp"], applied["discarded_face_units"])
        after = live_units(tools, name)
        check("1e the composed unit really is gone from the live face",
              abs(after["browInnerUp"]) < 1e-6, after["browInnerUp"])
        check("1f the stack now explains the face", applied["matches_stack"] is True)

        # ------------------------------------------------------------------
        # Claim 2: the panel module is loaded and can be kept in step.
        # ------------------------------------------------------------------
        check("2a panel_synced after apply (useexpression is in sys.modules headless)",
              applied["panel_synced"] is True, applied.get("panel_sync_reason"))

        # ------------------------------------------------------------------
        # Claim 5 (and 2b): compose on top, save, apply replace.
        # ------------------------------------------------------------------
        ok(tools["mpfb_set_face_units"](
            name=name, face_units=[{"face_unit": "jawOpen", "weight": 0.25},
                                   {"face_unit": "mouthSmileLeft", "weight": 0.61234}]),
           "set_face_units")
        composed_face = live_units(tools, name)
        saved = ok(tools["mpfb_save_expression"](name=EXPRESSION_NAME, subject=name,
                                                 overwrite=True, tags=["fr027"]),
                   "save_expression")
        written.append(saved["path"])
        check("5a the face was saved", saved["saved"] is True, saved.get("message"))
        check("5b the saved file holds the stack's contribution too",
              saved["stack_contributed"] is True
              and set(saved["face_units"]) == set(u for u, v in composed_face.items() if v))
        check("2b the save registered a panel slider",
              saved["panel_synced"] is True and saved["panel_sliders_added"] == 1,
              (saved["panel_synced"], saved["panel_sliders_added"]))
        replaced = ok(tools["mpfb_apply_expressions"](name=name, **saved["apply_with"]),
                      "apply_expressions")
        check("5c replace discards nothing, since the file holds the whole face",
              replaced["discarded_face_units"] == [], replaced["discarded_face_units"])
        check("5d replace took the library expression off",
              replaced["removed_by_replace"] == [library_fragment], replaced["removed_by_replace"])
        kept = live_units(tools, name)
        worst = max(abs(kept[unit] - composed_face[unit]) for unit in composed_face)
        check("5e the face survived the rebuild within four-decimal rounding",
              worst <= 0.00006, worst)
        check("5f the stack now explains it", replaced["matches_stack"] is True)

        # ------------------------------------------------------------------
        # Claim 4 (and 5g): the preset round trip.
        # ------------------------------------------------------------------
        preset = ok(tools["mpfb_save_preset"](name=PRESET_NAME, subject=name, overwrite=True),
                    "save_preset")
        written.append(preset["path"])
        check("4a the preset records one expression", preset["contents"]["expression_count"] == 1)
        rebuilt = ok(tools["mpfb_create_human_from_preset"](name=PRESET_NAME),
                     "create_human_from_preset")
        second = rebuilt["basemesh_name"]
        reread = ok(tools["mpfb_get_expression"](name=second), "get_expression")
        check("4b the loaded character wears the saved expression",
              [row["fragment"] for row in reread["applied_expressions"]]
              == [EXPRESSION_NAME + ".json"], reread["applied_expressions"])
        check("4c and the stack explains its face", reread["matches_stack"] is True,
              reread["unexplained_face_units"])
        loaded_face = live_units(tools, second)
        worst = max(abs(loaded_face[unit] - composed_face[unit]) for unit in composed_face)
        check("5g the composed face came back through a preset", worst <= 0.00006, worst)

        # ------------------------------------------------------------------
        # Claim 3: a user-saved file is shadowed by a higher-priority root.
        # ------------------------------------------------------------------
        user_copy = os.path.join(user_expressions, PROBE_NAME + ".json")
        system_copy = os.path.join(mpfb_expressions, PROBE_NAME + ".json")
        # The user's copy first, as if saved before the pack arrived; then the
        # higher-priority one. Both are the format document's example.
        for path in (user_copy, system_copy):
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(FORMAT_DOC_EXAMPLE, handle, indent=4, sort_keys=True)
            written.append(path)
        listing = ok(tools["mpfb_list_expressions"](), "list_expressions")
        listed = {entry["fragment"]: entry["path"] for entry in listing["expressions"]}
        check("3a MPFB lists the higher-priority copy, not the user's",
              listed.get(PROBE_NAME + ".json") == system_copy, listed.get(PROBE_NAME + ".json"))
        check("3b the user's copy is reported as shadowed",
              [(entry["path"], entry["shadowed_by"]) for entry in listing["shadowed"]]
              == [(user_copy, system_copy)], listing["shadowed"])
        refused = ok(tools["mpfb_save_expression"](name=PROBE_NAME, subject=name,
                                                   overwrite=True), "save_expression")
        check("3c save_expression refuses the shadowed name",
              refused["blocked_by"] == "name_shadowed"
              and refused["shadowed_by"]["path"] == system_copy, refused.get("blocked_by"))
    finally:
        blender.terminate()
        try:
            blender.wait(timeout=20)
        except subprocess.TimeoutExpired:
            blender.kill()
        for path in written:
            if path and os.path.exists(path):
                os.remove(path)
                print("removed {:s}".format(path))

    print()
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
