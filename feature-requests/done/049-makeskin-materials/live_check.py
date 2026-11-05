# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 049 against the gi it was written about: its three real textures, in Cycles.

The request's own check, through the real tool callables over a real socket against a
headless Blender. It rebuilds the gi's material from its three textures, stores it as an
alternate of the written ``taido_gi``, confirms ``mpfb_list_asset_materials`` lists it and
that it renders the same as the original, and compares the source files' hashes and
modification times before and after, since MPFB's own store re-encoded these same files.

**Nothing of the user's is written.** ``taido_gi_asset`` is copied into a temporary user data
root, which the script below points MPFB at, and ``taido_gi_v2.blend`` is opened and never
saved. The garment's ``asset_source`` still says ``nurse_uniform_with_pants``, the stale
record NEXT_STEPS describes and FR 050 fixes, so that same script sets it in memory.

**The render needs a command the bridge does not have, and that is not a gap.** The script
adds one to the running table, in this process only: the closed vocabulary is what the
add-on ships, and a check is allowed to add to it in memory what no caller ever could.

Skips if the gi's files are absent. It needs ``mpfb_bridge`` enabled in the Blender it is
pointed at (``local_environment.md``)::

    BLENDER=/path/to/blender python3 feature-requests/done/049-makeskin-materials/live_check.py
"""

from __future__ import annotations

__all__ = ()

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mpfbmcp import backend
from mpfbmcp import build_server

BLENDER = os.environ.get("BLENDER", shutil.which("blender") or "blender")
TAIDO = Path("/export/3d/taido")
SCENE = TAIDO / "taido_gi_v2.blend"
ASSET = TAIDO / "taido_gi_asset"
GARMENT = "Human.nurse_uniform_with_pants"
SOURCES = {"diffuse": TAIDO / "taido_gi_diffuse.png",
           "normalmap": TAIDO / "taido_gi_normalmap.png",
           "roughnessmap": TAIDO / "taido_gi_roughnessmap.png"}

# Mean and worst difference between two stills of one material, in 0..1 per channel, at a
# fixed seed. Sampling is deterministic here, and the file's four decimals of colour are not.
MEAN_DIFFERENCE_LIMIT = 0.002

BEFORE_BRIDGE = """
import os, sys
import bpy
import numpy
from mathutils import Vector

USER_DATA = {user_data!r}
OUT = {out!r}

root = next(name[:-len(".services.humanservice")] for name in sys.modules
            if name.endswith(".services.humanservice"))
sys.modules[root + ".services.locationservice"].LocationService._user_data = USER_DATA
properties = sys.modules[root + ".services.objectservice"].GeneralObjectProperties
properties.set_value("asset_source", "taido_gi/taido_gi.mhclo",
                     entity_reference=bpy.data.objects[{garment!r}])

scene = bpy.context.scene
camera = bpy.data.objects.new("live_check_camera", bpy.data.cameras.new("live_check_camera"))
scene.collection.objects.link(camera)
camera.data.lens = 85
target = Vector((0.0, -0.03, 0.95))
camera.location = target + Vector((0.3, -1.0, 0.05)).normalized() * 3.4
camera.rotation_mode = "QUATERNION"
camera.rotation_quaternion = (target - camera.location).to_track_quat("-Z", "Y")
scene.camera = camera
sun = bpy.data.objects.new("live_check_sun", bpy.data.lights.new("live_check_sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (0.9, 0.2, 0.4)
scene.collection.objects.link(sun)
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 16
scene.cycles.seed = 49
scene.cycles.use_denoising = False
scene.cycles.use_adaptive_sampling = False
scene.render.resolution_x = 500
scene.render.resolution_y = 700
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_depth = "16"


def pixels(path):
    image = bpy.data.images.load(path, check_existing=False)
    try:
        values = numpy.empty(len(image.pixels), dtype=numpy.float32)
        image.pixels.foreach_get(values)
        return values
    finally:
        bpy.data.images.remove(image)


def render_still(params, resolution):
    path = os.path.join(OUT, params["still"] + ".png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    answer = dict(path=path)
    if params["against"] is not None:
        difference = numpy.abs(pixels(path) - pixels(os.path.join(OUT, params["against"] + ".png")))
        answer.update(mean_difference=float(difference.mean()),
                      worst_difference=float(difference.max()))
    return answer


bridge = next(name[:-len(".commands.table")] for name in sys.modules
              if name.endswith("mpfb_bridge.commands.table"))
table = sys.modules[bridge + ".commands.table"]
validation = sys.modules[bridge + ".validation"]
table.COMMANDS["render_still"] = table.Command(
    name="render_still", handler=render_still,
    params=(validation.Param("still", validation.TYPE_STRING, required=True),
            validation.Param("against", validation.TYPE_STRING, default=None, nullable=True)),
    requires_mpfb=True, summary="This check's own, in this process only.")
"""

_failures = []
_checks = 0


def check(what: str, passed: bool, observed: object = None) -> None:
    """One claim. Printed either way, so that the run is its own record."""
    global _checks  # pylint: disable=global-statement
    _checks += 1
    print("{:s} {:s}{:s}".format("ok  " if passed else "FAIL", what,
                                 "" if observed is None else "  [{!s}]".format(observed)))
    if not passed:
        _failures.append(what)


class Blender:
    """A headless Blender with the bridge up on a port of its own, stopped on exit."""

    def __init__(self, blend: Path, before_bridge: Path) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.process = subprocess.Popen(  # pylint: disable=consider-using-with
            [BLENDER, "--background", str(blend), "--python", str(before_bridge),
             "--command", "mpfb_bridge", "--port", str(self.port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def __enter__(self) -> "Blender":
        os.environ["MPFB_BRIDGE_PORT"] = str(self.port)
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return self
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("the bridge did not come up")

    def __exit__(self, *_exception: object) -> None:
        self.process.terminate()
        self.process.wait(timeout=30)


def tools() -> dict:
    """The real tool callables, off the server that ships."""
    # pylint: disable=protected-access
    return {tool.name: tool.fn for tool in build_server()._tool_manager.list_tools()}


def answer(envelope: dict) -> dict:
    """The result of a call that must not have failed."""
    if envelope.get("status") != "ok":
        raise RuntimeError(json.dumps(envelope)[:800])
    return envelope["result"]


def timed(call, **arguments) -> tuple[dict, float]:
    """A call's answer and how long it took, in milliseconds."""
    started = time.perf_counter()
    result = answer(call(**arguments))
    return (result, (time.perf_counter() - started) * 1000.0)


def fingerprint(path: Path) -> tuple[str, int, int]:
    """What says a file was not touched: its bytes, its size and when it was last written."""
    stat = path.stat()
    return (hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_size, stat.st_mtime_ns)


def render(still: str, against: str | None = None) -> dict:
    return answer(backend.send("render_still", params={"still": still, "against": against}))


def check_the_gi(available: dict, data: Path) -> None:
    """The request's list, in its order."""
    before = {slot: fingerprint(path) for slot, path in SOURCES.items()}

    baseline = render("original")
    print("baseline still: {:s}".format(baseline["path"]))

    original = answer(available["mpfb_get_makeskin_material"](name=GARMENT))
    check("the file's own material reads as MakeSkin", original["ready"], original["message"])
    check("its three maps are wired, from their own files",
          {slot: entry.get("path") for slot, entry in original["textures"].items()}
          == {slot: str(path) for slot, path in SOURCES.items()})
    check("its colour spaces follow the slots",
          {slot: entry["color_space"] for slot, entry in original["textures"].items()}
          == dict(diffuse="sRGB", normalmap="Non-Color", roughnessmap="Non-Color"))
    check("roughness beside its map says it is not in effect",
          original["values"]["roughness"]["in_effect"] is False
          and original["values"]["roughness"]["overridden_by"] == "roughnessmap")

    rebuilt, elapsed = timed(
        available["mpfb_set_makeskin_material"], name=GARMENT, material_name="taido_gi_rebuilt",
        replace=True,
        textures={slot: {"path": str(path)} for slot, path in SOURCES.items()},
        values={"diffuseColor": {"color": [1.0, 1.0, 1.0, 1.0]}, "roughness": {"value": 0.9},
                "diffuseIntensity": {"value": 1.0}, "normalmapIntensity": {"value": 1.0}},
        metadata={"description": "Taido gi, rebuilt.", "license": "CC0", "author": "Joel",
                  "tag": "gi, taido, martial arts", "backfaceCull": False})
    print("set, three 4096 px textures: {:.0f} ms".format(elapsed))
    check("the material is rebuilt from the three textures", rebuilt["applied"], rebuilt["message"])
    check("a path Blender had loaded was reloaded", sorted(rebuilt["reloaded"]) == sorted(SOURCES),
          rebuilt["reloaded"])
    check("it read as the original did", all(
        rebuilt["textures"][slot][key] == original["textures"][slot][key]
        for slot in SOURCES for key in ("path", "wired", "color_space", "size")))

    same = render("rebuilt", against="original")
    check("the rebuilt material renders the same as the original",
          same["mean_difference"] < MEAN_DIFFERENCE_LIMIT,
          "mean {:.6f}, worst {:.4f}".format(same["mean_difference"], same["worst_difference"]))

    stored, elapsed = timed(available["mpfb_store_makeskin_material"], name=GARMENT,
                            store_as="alternate", material_name="taido_gi_again")
    print("store: {:.0f} ms".format(elapsed))
    target = data / "clothes" / "taido_gi" / "taido_gi_again" / "taido_gi_again.mhmat"
    check("it lands where MPFB's panel puts an alternate", stored["path"] == str(target),
          stored["path"])
    check("nothing was lost to MPFB's loader, since the one odd number had a map over it",
          stored["values_not_restored"] == {}, stored["values_not_restored"])
    for row in stored["textures_written"]:
        check("{:s} was copied byte for byte".format(row["slot"]),
              row["how"] == "copied"
              and fingerprint(Path(row["path"]))[0] == before[row["slot"]][0],
              "{:d} B".format(row["size_bytes"]))
    check("the MHMAT names them beside it", all(
        "{:s}Texture taido_gi_again_{:s}.png\n".format(slot, slot) in target.read_text()
        for slot in SOURCES))

    listed = answer(available["mpfb_list_asset_materials"](name=GARMENT))
    check("mpfb_list_asset_materials lists it at once",
          str(target) in [entry["path"] for entry in listed["materials"]],
          [entry["fragment"] for entry in listed["materials"]])

    applied = answer(available["mpfb_set_asset_material"](**stored["apply_with"][
        "mpfb_set_asset_material"]))
    check("apply_with applies it", applied["applied"], applied["message"])
    stored_read = answer(available["mpfb_get_makeskin_material"](name=GARMENT))
    check("MPFB's loader wired the stored files", all(
        stored_read["textures"][slot]["path"] == str(
            target.parent / "taido_gi_again_{:s}.png".format(slot)) for slot in SOURCES))
    same = render("stored", against="original")
    check("the stored alternate renders the same as the original",
          same["mean_difference"] < MEAN_DIFFERENCE_LIMIT,
          "mean {:.6f}, worst {:.4f}".format(same["mean_difference"], same["worst_difference"]))

    again = answer(available["mpfb_store_makeskin_material"](
        name=GARMENT, store_as="alternate", material_name="taido_gi_again"))
    check("storing the name again is refused", again["blocked_by"] == "material_exists",
          again["file_before"])

    after = {slot: fingerprint(path) for slot, path in SOURCES.items()}
    check("every source file is byte-identical and unwritten", after == before)


def main() -> int:
    if not SCENE.exists() or not ASSET.exists():
        print("skip: the gi's files are absent")
        return 0
    with tempfile.TemporaryDirectory(prefix="fr049_") as temporary:
        root = Path(temporary)
        data = root / "data"
        shutil.copytree(ASSET, data / "clothes" / "taido_gi")
        out = root / "stills"
        out.mkdir()
        script = root / "before_bridge.py"
        script.write_text(BEFORE_BRIDGE.format(user_data=str(data), out=str(out),
                                               garment=GARMENT), encoding="utf8")
        with Blender(SCENE, script):
            check_the_gi(tools(), data)
        keep = os.environ.get("FR049_KEEP_STILLS")
        if keep:
            shutil.copytree(out, keep, dirs_exist_ok=True)
    print("{:d} checks, {:d} failed".format(_checks, len(_failures)))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
