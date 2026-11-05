# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 050 against the gi it was written about: the first run of "Store in library".

The request's own check, through the real tool callables over a real socket against a headless
Blender. From ``taido_gi_v2.blend`` it writes the gi to both destinations, then runs the recipe on a
second body in a pose, through tools alone, and records its counts beside the session's 159 and 105.
Those were taken on the Taido template's own poses, so they are a reference and not a target. It
also shows that ``mpfb_get_object_info`` and ``mpfb_list_asset_materials`` no longer report
``mhclo_not_installed``, that the OBJ matches the MHCLO at any viewport level, that no source texture
changed, and it provokes the posed and turned bodies.

**Two commands the bridge does not have**, added to the running table in this process only as
FR 049's check adds one: raising the gi's Subdivision, and asking MPFB's own exporter what it would
write at that level. The closed vocabulary is what the add-on ships.

**Nothing of the user's is written.** User data and the export directory are temporary directories,
which the script below and ``--export-dir`` point at, ``taido_gi_v2.blend`` is opened and never
saved, and all of it is gone when the check ends. Presets are read from the real configuration, and
none is written.

Skips if the gi's files are absent. It needs ``mpfb_bridge`` enabled in the Blender it is pointed at
(``local_environment.md``)::

    BLENDER=/path/to/blender python3 feature-requests/done/050-writing-mesh-assets/live_check.py
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
GARMENT = "Human.nurse_uniform_with_pants"
SOURCES = {"diffuse": TAIDO / "taido_gi_diffuse.png",
           "normalmap": TAIDO / "taido_gi_normalmap.png",
           "roughnessmap": TAIDO / "taido_gi_roughnessmap.png"}

# The session's counts on the Taido template's poses, for the record beside this run's.
SESSION_COUNTS = (159, 105)

BEFORE_BRIDGE = """
import os, sys
import bpy

OUT = {out!r}

root = next(name[:-len(".services.humanservice")] for name in sys.modules
            if name.endswith(".services.humanservice"))
sys.modules[root + ".services.locationservice"].LocationService._user_data = {user_data!r}
object_service = sys.modules[root + ".services.objectservice"].ObjectService


def _subdivision(params, resolution):
    garment = bpy.data.objects[params["name"]]
    modifier = next(modifier for modifier in garment.modifiers if modifier.type == "SUBSURF")
    was = modifier.levels
    modifier.levels = params["levels"]
    return dict(was=was)


def _mpfb_obj(params, resolution):
    garment = bpy.data.objects[params["name"]]
    window = bpy.context.window_manager.windows[0]
    path = os.path.join(OUT, "as_mpfb_writes_it.obj")
    with bpy.context.temp_override(window=window):
        object_service.save_wavefront_file(path, garment)
    with open(path, "r", encoding="utf8") as handle:
        return dict(vertices=sum(1 for line in handle if line.startswith("v ")))


bridge = next(name[:-len(".commands.table")] for name in sys.modules
              if name.endswith("mpfb_bridge.commands.table"))
table = sys.modules[bridge + ".commands.table"]
validation = sys.modules[bridge + ".validation"]
table.COMMANDS["live_check_subdivision"] = table.Command(
    name="live_check_subdivision", handler=_subdivision,
    params=(validation.Param("name", validation.TYPE_STRING, required=True),
            validation.Param("levels", validation.TYPE_INTEGER, required=True)),
    requires_mpfb=True, summary="This check's own, in this process only.")
table.COMMANDS["live_check_mpfb_obj"] = table.Command(
    name="live_check_mpfb_obj", handler=_mpfb_obj,
    params=(validation.Param("name", validation.TYPE_STRING, required=True),),
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

    def __init__(self, blend: Path, before_bridge: Path, export_directory: Path) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.process = subprocess.Popen(  # pylint: disable=consider-using-with
            [BLENDER, "--background", str(blend), "--python", str(before_bridge),
             "--command", "mpfb_bridge", "--port", str(self.port),
             "--export-dir", str(export_directory)],
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


def vertex_lines(path: Path) -> int:
    with open(path, "r", encoding="utf8") as handle:
        return sum(1 for line in handle if line.startswith("v "))


def mhclo_lines(path: Path) -> int:
    text = path.read_text(encoding="utf8").split("verts 0\n", 1)[1]
    return len(text.split("\n\n", 1)[0].splitlines())


def write_to_both(available: dict, data: Path, exports: Path) -> dict:
    """The two destinations, and what the object knows after each."""
    write = available["mpfb_write_mesh_asset"]
    before_info = answer(available["mpfb_get_object_info"](name=GARMENT))
    before_materials = answer(available["mpfb_list_asset_materials"](name=GARMENT))
    print("before: asset_source={!r}, default_material_reason={!r}".format(
        before_info.get("asset_info", {}).get("asset_source"),
        before_materials.get("default_material_reason")))
    check("the stale record is what the request describes",
          before_materials.get("default_material_reason") == "mhclo_not_installed",
          before_materials.get("default_material_reason"))

    dry, elapsed = timed(write, name=GARMENT, asset_name="taido_gi", dry_run=True)
    print("dry run: {:.0f} ms, {!s}".format(elapsed, dry["message"]))
    check("a dry run wrote nothing", dry["written"] is False and not (data / "clothes").exists())

    elsewhere, elapsed = timed(write, name=GARMENT, asset_name="taido_gi",
                               destination="export_directory", license="CC0", author="Joel")
    print("export directory: {:.0f} ms, {!s}".format(elapsed, elsewhere["message"]))
    target = exports / "taido_gi"
    check("the export directory write landed there", elsewhere["path"] == str(
        target / "taido_gi.mhclo"), elsewhere["path"])
    check("and said who chose it", elsewhere["path_resolved_by"] == "command_line")
    check("and left asset_source alone", elsewhere["asset_source_updated"] is False,
          elsewhere["asset_source"])

    written, elapsed = timed(write, name=GARMENT, asset_name="taido_gi", license="CC0",
                             author="Joel")
    print("library: {:.0f} ms".format(elapsed))
    directory = data / "clothes" / "taido_gi"
    check("'Store in library' landed where the panel would",
          written["path"] == str(directory / "taido_gi.mhclo"), written["path"])
    check("it wrote the whole asset", sorted(os.listdir(directory)) == [
        "taido_gi.mhclo", "taido_gi.mhmat", "taido_gi.obj", "taido_gi_diffuse.png",
        "taido_gi_normalmap.png", "taido_gi_roughnessmap.png"], sorted(os.listdir(directory)))
    print("match_counts={!s}, delete_vertices={!s}, max_pole={!s}, exact={!s} ({:s})".format(
        written["match_counts"], written["delete_vertices"], written["max_pole"],
        written["allow_exact_matching"], written["allow_exact_matching_resolved_by"]))
    print("check: {:s}".format(json.dumps(written["check"])))
    print("uuid {!s} ({:s}); warnings: {!s}".format(
        written["uuid"], written["uuid_resolved_by"], written["warnings"]))
    check("the OBJ and the MHCLO hold one count, the gi's 2,027",
          vertex_lines(directory / "taido_gi.obj") == mhclo_lines(directory / "taido_gi.mhclo")
          == 2027, vertex_lines(directory / "taido_gi.obj"))
    check("asset_source was updated", written["asset_source_updated"] is True
          and written["asset_source"] == "taido_gi/taido_gi.mhclo", written["asset_source"])

    after_materials = answer(available["mpfb_list_asset_materials"](name=GARMENT))
    check("mpfb_list_asset_materials no longer says mhclo_not_installed",
          after_materials.get("default_material_reason") != "mhclo_not_installed",
          after_materials.get("default_material_reason"))
    after_info = answer(available["mpfb_get_object_info"](name=GARMENT))
    check("mpfb_get_object_info resolves it", after_info["asset_info"].get("mhclo_path") == str(
        directory / "taido_gi.mhclo"), after_info["asset_info"].get("mhclo_path"))

    again = answer(write(name=GARMENT, asset_name="taido_gi"))
    check("writing it again is refused", again["blocked_by"] == "asset_exists",
          again["file_before"])
    return written


def viewport_levels_match(available: dict, exports: Path) -> None:
    """What the gi escaped only because MPFB's modifier sat at level 0."""
    before = answer(backend.send("live_check_subdivision", params={"name": GARMENT, "levels": 1}))
    print("the gi's viewport subdivision was at level {!s}, now 1".format(before["was"]))
    theirs = answer(backend.send("live_check_mpfb_obj", params={"name": GARMENT}))["vertices"]
    check("MPFB's exporter at level 1 writes more than the MHCLO describes", theirs > 2027,
          "{:d} vertices, against the request's 11,862".format(theirs))
    ours = answer(available["mpfb_write_mesh_asset"](
        name=GARMENT, asset_name="at_level_one", destination="export_directory", license="CC0",
        author="Joel"))
    directory = exports / "at_level_one"
    check("this one's OBJ at level 1 holds what the MHCLO describes",
          ours["written"] and vertex_lines(directory / "at_level_one.obj") == mhclo_lines(
              directory / "at_level_one.mhclo") == 2027,
          vertex_lines(directory / "at_level_one.obj"))
    answer(backend.send("live_check_subdivision",
                        params={"name": GARMENT, "levels": before["was"]}))


def recipe(available: dict, written: dict) -> None:
    """Author on one character, write, then a second body, posed, the asset on it, masks off."""
    presets = answer(available["mpfb_list_presets"]())
    names = [entry["name"] for entry in presets["presets"] if entry.get("addressable", True)]
    print("presets: {!s}".format(names[:10]))
    calls = written["try_with"]
    if names:
        second = answer(available["mpfb_create_human_from_preset"](preset_name=names[0]))
        check("a body from a preset", second["ready"], second.get("message"))
        body = second.get("basemesh_name") or second["objects_created"][0]
    else:
        second = answer(available["mpfb_create_human"]())
        body = second["object_name"]
    summary = answer(available["mpfb_get_character_summary"](name=body))
    if summary["rig"] is None or not summary["rig"].get("name"):
        answer(available["mpfb_add_rig"](name=body, rig="default"))

    arguments = dict(calls["mpfb_add_asset"], name=body)
    added = answer(available["mpfb_add_asset"](**arguments))
    check("try_with equips it on the second body", added["added"], added["message"])
    equipped = added["asset_object_name"]

    at_rest = answer(available["mpfb_check_intersections"](name=body))
    print("at rest: {!s}".format(json.dumps(at_rest["pairs"][:3])))

    controls = answer(available["mpfb_get_pose_controls"](
        name=body, body_parts=["left_arm", "right_arm"], roles=["fk"], compact=True))
    print("the rig is {!s}".format(controls.get("rig_type")))
    # The first FK bone of each arm is the upper arm, and raising both moves the sleeves
    # against a coat, which is the kind of pose that found the session's defects.
    arms = [(part, entries[0]["bone"]) for part, entries in controls["controls"].items()
            if entries]
    posed = answer(available["mpfb_set_pose_bones"](name=body, bones=[
        dict(bone=bone, rotate_by=dict(axis=dict(forward=-1.0 if part == "left_arm" else 1.0),
                                       degrees=60.0))
        for part, bone in arms]))
    check("the second body is posed", posed["performed"] is True and len(arms) == 2,
          posed["message"])
    measured = answer(available["mpfb_check_intersections"](name=body))
    rows = [row for row in measured["pairs"] if equipped in (row["object_name"],
                                                             row["other_object_name"])]
    print("posed: {:s}".format(json.dumps(rows[:3])))
    print("the session's counts on the Taido poses, for reference: {!s}".format(SESSION_COUNTS))
    check("the recipe measured it with the masks off", rows and "face_pairs_unmasked" in rows[0])

    refused = answer(available["mpfb_write_mesh_asset"](
        name=equipped, basemesh=body, asset_name="posed_copy", license="CC0", author="Joel",
        dry_run=True))
    check("the same mesh on a posed body is refused", refused["blocked_by"] == "rig_not_at_rest",
          refused["message"])
    answer(available["mpfb_reset_pose"](name=body))
    placed = answer(available["mpfb_place_character"](name=body, facing=90.0))
    check("the second body is turned", placed["placed"], placed["facing_after"])
    refused = answer(available["mpfb_write_mesh_asset"](
        name=equipped, basemesh=body, asset_name="turned_copy", license="CC0", author="Joel",
        dry_run=True))
    check("and on a turned one too", refused["blocked_by"] == "character_turned",
          refused["message"])


def main() -> int:
    if not SCENE.exists():
        print("skip: the gi's files are absent")
        return 0
    before = {slot: fingerprint(path) for slot, path in SOURCES.items()}
    with tempfile.TemporaryDirectory(prefix="fr050_") as temporary:
        root = Path(temporary)
        data = root / "data"
        data.mkdir()
        exports = root / "exports"
        exports.mkdir()
        script = root / "before_bridge.py"
        script.write_text(BEFORE_BRIDGE.format(user_data=str(data), out=temporary),
                          encoding="utf8")
        with Blender(SCENE, script, exports):
            available = tools()
            written = write_to_both(available, data, exports)
            viewport_levels_match(available, exports)
            recipe(available, written)
    after = {slot: fingerprint(path) for slot, path in SOURCES.items()}
    check("every source file is byte-identical and unwritten", after == before)
    print("{:d} checks, {:d} failed".format(_checks, len(_failures)))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
