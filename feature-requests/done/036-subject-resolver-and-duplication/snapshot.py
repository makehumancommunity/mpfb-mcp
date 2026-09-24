# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 036's live check: what the bridge answers, before and after each move.

Run during the effort, and not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance for why it does not belong in
verification/. It follows FR 034's ``live_check.py --snapshot``, with one
difference that matters for this request: it talks to the bridge through
``mpfbmcp.backend.send`` rather than through the tool callables. FR 036 moves
code on both sides of the socket, and a bridge-side snapshot taken through the
tools would change whenever the tool side did. This one sees only the commands.

    PYTHONPATH=src python3 feature-requests/done/036-subject-resolver-and-duplication/snapshot.py OUT.json

It starts a headless Blender with the bridge on a spare port, using the Blender
named in local_environment.md, and **before the bridge starts** makes the one
state no command can make: nothing active, with a plain cube in the file that
belongs to no character. Then it writes one JSON file with sorted keys:

- ``misses``: all eighteen subject-taking commands in the three miss states -
  nothing active, a name that does not exist, and the cube;
- ``character``: every read-only one among them on a real character, then the
  mutating commands in an order that leaves each one something to act on, with
  ``get_object_info`` on the *active* object after each, since that is the one
  window a command offers onto whether the caller's selection was put back;
- ``status``: ``get_status``, ``get_mpfb_status`` and ``list_urls``, for the
  version strings.

Every call's whole envelope is kept. :data:`VOLATILE` names the few values that
differ between two runs of the same code (uptimes and file times), which are
replaced by a placeholder so that the diff shows what moved rather than what
ticked. Run it twice on one commit to confirm that list is complete.

Nothing is written outside the throwaway Blender.
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
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

BLENDER = os.environ.get("BLENDER_EXE", "/home/joepal/system/blender-5.1.0-linux-x64/blender")
PORT = int(os.environ.get("FR036_PORT", "9936"))

CUBE = "fr036-cube"
NO_SUCH = "fr036-no-such-object"

# Before the bridge serves anything: nothing active, and an object with no
# basemesh among its relatives. No command can make either state.
PREPARE = (
    "import bpy\n"
    "mesh = bpy.data.meshes.new('{cube}')\n"
    "cube = bpy.data.objects.new('{cube}', mesh)\n"
    "bpy.context.scene.collection.objects.link(cube)\n"
    "for obj in bpy.context.view_layer.objects:\n"
    "    obj.select_set(False)\n"
    "bpy.context.view_layer.objects.active = None\n"
).format(cube=CUBE)

# Keys whose values differ between two runs of the same code.
VOLATILE = frozenset((
    "uptime_seconds", "started_at", "mtime", "modified", "age_seconds", "last_request_at",
    "requests_served", "elapsed_ms", "duration_ms",
))


def _subject_calls(subject):
    """The eighteen subject-taking commands, each with the least it needs to run."""
    return {
        "get_object_info": dict(name=subject),
        "get_macro_details": dict(name=subject),
        "get_character_summary": dict(name=subject),
        "get_target_stack": dict(name=subject),
        "get_face_units": dict(name=subject),
        "get_expression": dict(name=subject),
        "set_macro_details": dict(name=subject, changes=[
            dict(argument="gender", property="gender", value=0.4)]),
        "refit_human": dict(name=subject),
        "set_targets": dict(name=subject, modifiers=[
            dict(section="nose", category="nose-trans-up|down", side="unsided", value=0.2)]),
        "symmetrize_targets": dict(name=subject, direction="left_to_right", dry_run=True),
        "set_face_units": dict(name=subject, face_units=[dict(face_unit="jawOpen",
                                                              weight=0.3)]),
        "apply_expressions": dict(name=subject, expressions=[]),
        "save_expression": dict(name="fr036_snapshot_never_written", subject=subject),
        "save_preset": dict(name="fr036_snapshot_never_written", subject=subject),
        "add_rig": dict(name=subject, identifier="default"),
        "generate_rigify_rig": dict(name=subject),
        "add_asset": dict(name=subject, fragment="fr036/none.mhclo", asset_type="Clothes"),
        "set_skin": dict(name=subject),
    }


def _scrub(value):
    if isinstance(value, dict):
        return {key: ("<volatile>" if key in VOLATILE else _scrub(inner))
                for key, inner in value.items()}
    if isinstance(value, list):
        return [_scrub(inner) for inner in value]
    return value


def wait_for_port(port, seconds=90.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return True
        except OSError:
            time.sleep(0.5)
    return False


def _ok(envelope, what):
    if envelope.get("status") != "ok":
        raise SystemExit("{:s} failed: {!r}".format(what, envelope))
    return envelope["result"]


def _first(send, subdir):
    assets = _ok(send("list_assets", params=dict(asset_subdir=subdir, limit=1)),
                 "list_assets")["assets"]
    return assets[0] if assets else None


def _modifiers(send):
    """Two unsided categories and two sided ones set lopsided, so symmetrize has work."""
    entries = []
    for section in ("nose", "ears", "eyes"):
        categories = _ok(send("list_targets", params=dict(section=section)),
                         "list_targets")["categories"]
        unsided = [entry for entry in categories if not entry["has_left_and_right"]]
        sided = [entry for entry in categories if entry["has_left_and_right"]]
        if unsided:
            entries.append(dict(section=section, category=unsided[0]["name"], side="unsided",
                                value=0.25))
        if sided:
            entries.append(dict(section=section, category=sided[0]["name"], side="left",
                                value=0.4))
            entries.append(dict(section=section, category=sided[0]["name"], side="right",
                                value=0.1))
    return entries


def snapshot(send):
    answers = dict(misses=dict(), character=dict(), status=dict())

    # The nothing-active state first, before any command makes something active.
    for label, subject in (("nothing_active", None), ("no_such_name", NO_SUCH),
                           ("no_basemesh", CUBE)):
        answers["misses"][label] = {
            command: send(command, params=params)
            for command, params in sorted(_subject_calls(subject).items())}

    for command in ("get_status", "get_mpfb_status", "list_urls"):
        answers["status"][command] = send(command)

    steps = []

    def step(label, command, **params):
        envelope = send(command, params=params)
        steps.append(dict(label=label, command=command, answer=envelope,
                          active_after=send("get_object_info", params=dict(name=None))))
        return envelope

    human = _ok(step("create_human", "create_human"), "create_human")["object_name"]
    for command in ("get_object_info", "get_macro_details", "get_character_summary",
                    "get_target_stack", "get_face_units", "get_expression"):
        step("read " + command, command, name=human)

    step("set_macro_details", "set_macro_details", name=human, changes=[
        dict(argument="gender", property="gender", value=0.3),
        dict(argument="muscle", property="muscle", value=0.7)])
    step("set_targets", "set_targets", name=human, refit=True, modifiers=_modifiers(send))
    step("read get_target_stack after set_targets", "get_target_stack", name=human)
    step("symmetrize_targets dry", "symmetrize_targets", name=human,
         direction="left_to_right", dry_run=True)
    step("set_face_units", "set_face_units", name=human,
         face_units=[dict(face_unit="jawOpen", weight=0.4)])
    step("apply_expressions clear", "apply_expressions", name=human, expressions=[],
         mode="replace")

    rigs = _ok(send("list_rigs"), "list_rigs")["rigs"]
    rigify = [rig for rig in rigs if rig.get("family") == "rigify"]
    step("add_rig", "add_rig", name=human,
         identifier=(rigify[0] if rigify else rigs[0])["identifier"])

    clothes = _first(send, "clothes")
    added = _ok(step("add_asset", "add_asset", name=human, fragment=clothes["fragment"],
                     asset_type=clothes["object_type"]), "add_asset")
    asset_object = added["asset_object_name"]
    materials = _ok(step("list_asset_materials", "list_asset_materials", name=asset_object),
                    "list_asset_materials")["materials"]
    if materials:
        step("set_asset_material", "set_asset_material", name=asset_object,
             path=materials[0]["path"])
    skin = _first(send, "skins")
    step("set_skin", "set_skin", name=human, fragment=skin["fragment"],
         skin_type="ENHANCED")
    step("refit_human", "refit_human", name=human)
    step("remove_asset", "remove_asset", name=asset_object)
    if rigify:
        step("generate_rigify_rig", "generate_rigify_rig", name=human)
    for command in ("get_object_info", "get_macro_details", "get_character_summary",
                    "get_target_stack"):
        step("read again " + command, command, name=human)

    presets = _ok(send("list_presets"), "list_presets")["presets"]
    if presets:
        step("create_human_from_preset", "create_human_from_preset", name=presets[0]["name"])
    step("save_preset refused", "save_preset", name=presets[0]["name"] if presets else "x",
         subject=human)
    step("list_objects", "list_objects")
    answers["character"] = steps
    return _scrub(answers)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: snapshot.py OUT.json")
    os.environ["MPFB_BRIDGE_PORT"] = str(PORT)
    from mpfbmcp import backend  # pylint: disable=import-outside-toplevel

    blender = subprocess.Popen(
        [BLENDER, "--background", "-noaudio", "--python-expr", PREPARE,
         "--command", "mpfb_bridge", "--port", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_for_port(PORT):
            raise SystemExit("the headless bridge never started listening on {:d}".format(PORT))
        answers = snapshot(backend.send)
    finally:
        blender.terminate()
        try:
            blender.wait(timeout=20)
        except subprocess.TimeoutExpired:
            blender.kill()

    with open(sys.argv[1], "w", encoding="utf-8") as handle:
        json.dump(answers, handle, indent=1, sort_keys=True)
    print("wrote {:s}: {:d} bytes".format(sys.argv[1], os.path.getsize(sys.argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
