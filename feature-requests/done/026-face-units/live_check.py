# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 026's own live check: three claims this side of the socket cannot settle.

Run once during the effort, against a real Blender with MPFB and the MPFB
Bridge add-on installed. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance and
verification/README.md for why this script does not belong in
verification/. Prints PASS/FAIL for each claim and exits non-zero on any
failure.

    /path/to/blender -b -noaudio -P feature-requests/done/026-face-units/live_check.py

Three claims, each named in README.md:

1. `FaceService.set_expression()` really does return normally with the
   `faceunits01` pack absent rather than raising - the premise behind
   requirement 11's refusal and the first defect candidate.
2. Composing face units and refitting really does move a rigged, fitted
   mesh asset (an eyebrow) further toward the new face shape than not
   refitting does - the justification for requirement 13.
3. Whether `mpfb_set_targets` can write an `!ex-` key directly - the
   overlap `mpfb_set_face_units`' description warns about rather than
   `mpfb_set_targets` refusing.
"""

import os
import sys

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO_ROOT, "bridge", "test"))

FAILURES = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print("[{:s}] {:s}{:s}".format(status, label, "" if not detail else " - " + detail))
    if not condition:
        FAILURES.append(label)


def enable_bridge():
    candidates = ["bl_ext.{:s}.mpfb_bridge".format(repo.module)
                  for repo in bpy.context.preferences.extensions.repos]
    candidates.append("mpfb_bridge")
    for candidate in candidates:
        try:
            bpy.ops.preferences.addon_enable(module=candidate)
        except Exception:  # pylint: disable=broad-except
            continue
        if candidate in bpy.context.preferences.addons:
            print("Enabled the add-on under test as " + candidate)
            return
    raise SystemExit("Could not enable the MPFB Bridge add-on")


enable_bridge()

from tests._fixtures import dispatch, services_or_skip  # noqa: E402  pylint: disable=wrong-import-position

services = services_or_skip()
face_service = services["FaceService"]
target_service = services["TargetService"]
object_service = services["ObjectService"]
human_service = services["HumanService"]

before_objects = set(blender_object.name for blender_object in bpy.data.objects)


# --------------------------------------------------------------------------
# Claim 1: set_expression() returns normally with the pack absent.
# --------------------------------------------------------------------------

basemesh = human_service.create_human()
try:
    import contextlib

    @contextlib.contextmanager
    def _no_data_roots():
        location_service = services["LocationService"]
        missing = os.path.join(os.sep, "mpfb-mcp-live-check", "no-such-root")
        fields = ("_user_data", "_mpfb_data", "_second_root", "_mh_user_data")
        original = {field: getattr(location_service, field) for field in fields}
        try:
            for field in fields:
                setattr(location_service, field, missing)
            yield
        finally:
            for field, value in original.items():
                setattr(location_service, field, value)

    raised = False
    with _no_data_roots():
        face_service.is_faceunits01_installed(force_recheck=True)
        try:
            face_service.set_expression(basemesh, {"jawOpen": 0.5})
        except Exception:  # pylint: disable=broad-except
            raised = True
    # Restored real roots by now (the `with` block above exited); re-probe so
    # the cache reflects reality again for the claims that follow.
    face_service.is_faceunits01_installed(force_recheck=True)

    check("Claim 1: set_expression() does not raise with the pack absent", not raised)
finally:
    bpy.data.objects.remove(basemesh, do_unlink=True)


# --------------------------------------------------------------------------
# Claim 3: mpfb_set_targets and a "!ex-" key.
# --------------------------------------------------------------------------

envelope = dispatch("create_human", {})
assert envelope["status"] == "ok", envelope
character_name = envelope["result"]["object_name"]

before = dispatch("set_targets", {
    "name": character_name,
    "targets": [{"shapekey_name": "!ex-jawOpen", "value": 0.3}],
})
cannot_create = (
    before["status"] == "ok"
    and before["result"]["performed"] is False
    and bool(before["result"].get("resolution_errors")))
check("Claim 3a: mpfb_set_targets cannot CREATE a !ex- shape key from nothing",
      cannot_create, repr(before["result"].get("resolution_errors")))

fixture_envelope = dispatch("set_face_units", {
    "name": character_name, "face_units": [{"face_unit": "jawOpen", "weight": 0.1}],
    "refit": False})
assert fixture_envelope["status"] == "ok" and fixture_envelope["result"]["performed"] is True, \
    "fixture setup failed: {!r}".format(fixture_envelope)
after = dispatch("set_targets", {
    "name": character_name,
    "targets": [{"shapekey_name": "!ex-jawOpen", "value": 0.55}],
})
character_object = bpy.data.objects[character_name]
key_block = character_object.data.shape_keys.key_blocks.get("!ex-jawOpen")
check("Claim 3b: mpfb_set_targets CAN write an existing !ex- key directly",
      after["result"]["performed"] is True and key_block is not None
      and abs(key_block.value - 0.55) < 1e-6,
      "value={!r}".format(None if key_block is None else key_block.value))


# --------------------------------------------------------------------------
# Claim 2: refit moves a fitted mesh asset further than not refitting.
# --------------------------------------------------------------------------

def _first_eyebrow_fragment():
    envelope = dispatch("list_assets", {"asset_subdir": "eyebrows", "limit": 5})
    assets = envelope["result"]["assets"] if envelope["status"] == "ok" else []
    return assets[0]["fragment"] if assets else None


fragment = _first_eyebrow_fragment()
if fragment is None:
    print("[SKIP] Claim 2: no eyebrows asset on this install")
else:
    def _build_and_measure(refit):
        envelope = dispatch("create_human", {})
        assert envelope["status"] == "ok", envelope
        name = envelope["result"]["object_name"]
        asset_envelope = dispatch("add_asset", {
            "name": name, "fragment": fragment, "asset_type": "Eyebrows"})
        assert asset_envelope["status"] == "ok", asset_envelope
        asset_name = asset_envelope["result"]["asset_object_name"]
        asset_object = bpy.data.objects[asset_name]
        bpy.context.view_layer.update()
        before_coords = [tuple(asset_object.matrix_world @ vertex.co)
                         for vertex in asset_object.data.vertices]
        dispatch("set_face_units", {
            "name": name, "face_units": [{"face_unit": "jawOpen", "weight": 0.9}],
            "refit": refit})
        bpy.context.view_layer.update()
        after_coords = [tuple(asset_object.matrix_world @ vertex.co)
                        for vertex in asset_object.data.vertices]
        moved = sum(
            (bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2
            for (ax, ay, az), (bx, by, bz) in zip(before_coords, after_coords))
        return name, moved

    _, moved_without_refit = _build_and_measure(False)
    _, moved_with_refit = _build_and_measure(True)

    check("Claim 2: refit moves the eyebrow mesh further than not refitting",
          moved_with_refit > moved_without_refit,
          "without={!r} with={!r}".format(moved_without_refit, moved_with_refit))


# --------------------------------------------------------------------------
# Cleanup: this script leaves nothing behind, unlike verification/smoke.py.
# --------------------------------------------------------------------------

for blender_object in list(bpy.data.objects):
    if blender_object.name not in before_objects:
        bpy.data.objects.remove(blender_object, do_unlink=True)


if FAILURES:
    print("\n{:d} claim(s) failed: {:s}".format(len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("\nAll claims held.")
