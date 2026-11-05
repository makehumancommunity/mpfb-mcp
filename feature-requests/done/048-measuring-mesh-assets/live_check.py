# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 048 against the gi it was written about, and the added time it made a condition of.

Three questions, each answered through the real tool callables over a real socket,
against a headless Blender. Nothing is saved over a ``.blend`` here, since Blender is
pointed at the file and the file is never written.

1. **Does ``mpfb_check_mesh_asset`` find the draft's defects?** The coat's low
   ``outward_fraction``, the hakama's near 1.0, and the recorded overlaps: 77 through
   the hakama, 25 through the body, 14 of one flap through the other. **The draft is
   not the file the request names.** ``taido_gi.blend``'s coat already faces outward
   (925 of 925 faces), and the coat with inverted normals is the ``gi_draft_mesh`` the
   session stashed inside ``taido_gi_v2.blend``, which is what its rebuild script
   started from every run. So that mesh is put on the garment in memory by a
   ``--python`` script before the bridge starts; the file is never saved. The stash
   meets the delete group as it finished, not as it stood, so the masked body count
   is lower than the 25 recorded.
2. **Does ``taido_gi_v2.blend`` show them gone?** The coat and hakama: the belt's pieces
   are closed shells, whose inside faces toward the body, and they read near 0.5 by
   construction.
3. **What does ``intersections`` add to ``mpfb_add_asset``?** The request made an
   always-on field conditional on it being under a quarter of the call, on a rigged,
   fully dressed character, and it is not: this measured 36 %, so the field is opt-in
   and this now records the number rather than asserting it. The function behind the
   field is timed in that Blender by a wrapper a ``--python`` script installs, which
   writes each duration to a file this script reads, and the comparison is with a
   call that does not ask, on a second copy of the same asset.

It also records the size of the full answer, and how long each call takes posed and
subdivided, which the request asked to have written down.

Skips the gi parts if the files are absent. It needs ``mpfb_bridge`` enabled in the
Blender it is pointed at (``local_environment.md``)::

    BLENDER=/path/to/blender python3 feature-requests/done/048-measuring-mesh-assets/live_check.py
"""

from __future__ import annotations

__all__ = ()

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mpfbmcp import build_server

BLENDER = os.environ.get("BLENDER", shutil.which("blender") or "blender")
NAMED_DRAFT = Path("/export/3d/taido/taido_gi.blend")
FINISHED = Path("/export/3d/taido/taido_gi_v2.blend")
GARMENT = "Human.nurse_uniform_with_pants"

# What the add_asset command's field costs, measured where it runs.
TIME_THE_FIELD = """
import sys, time
module = sys.modules[next(name for name in sys.modules
                          if name.endswith("mpfb_bridge.commands.add_asset"))]
measured = module._intersections
def timed(*arguments):
    started = time.perf_counter()
    try:
        return measured(*arguments)
    finally:
        with open({!r}, "a", encoding="utf8") as durations:
            durations.write("{{:f}}\\n".format((time.perf_counter() - started) * 1000.0))
module._intersections = timed
"""

# In memory only: nothing in this run saves the file.
WEAR_THE_DRAFT = """
import bpy
bpy.data.objects["{:s}"].data = bpy.data.meshes["gi_draft_mesh"]
""".format(GARMENT)

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
    """A headless Blender with the bridge up on a port of its own, stopped on exit.

    ``before_bridge`` is a Python file run first, in memory, on the opened file.
    """

    def __init__(self, blend: Path | None = None, before_bridge: Path | None = None) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        arguments = [BLENDER, "--background"]
        if blend is not None:
            arguments.append(str(blend))
        if before_bridge is not None:
            arguments += ["--python", str(before_bridge)]
        arguments += ["--command", "mpfb_bridge", "--port", str(self.port)]
        self.process = subprocess.Popen(  # pylint: disable=consider-using-with
            arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def __enter__(self) -> "Blender":
        os.environ["MPFB_BRIDGE_PORT"] = str(self.port)
        deadline = time.monotonic() + 60.0
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


def describe(report: dict) -> None:
    """The numbers the Outcome quotes."""
    print("    validator all_checks_ok:", (report["validator"] or {}).get("all_checks_ok"))
    for row in report["components"]["rows"]:
        overlap = row["overlap"]
        print("    component {:d}: faces {:d}, z {:.2f}..{:.2f}, outward {!s}, fit {!s}, "
              "body {:d}/{:d} unmasked, self {:d}, others {!s}".format(
                  row["component"], row["faces"], row["bounds"]["min"]["z"],
                  row["bounds"]["max"]["z"], row["outward_fraction"], row["fit_offset"],
                  overlap["body"]["face_pairs"], overlap["body"]["face_pairs_unmasked"],
                  overlap["self"]["face_pairs"],
                  [(other["component"], other["face_pairs"])
                   for other in overlap["other_components"]]))
    uv = report["uv"]
    print("    uv: islands {!s}, overlapping {!s}, outside {!s}, texels {!s}".format(
        uv.get("islands"), uv.get("overlapping_islands"), uv.get("faces_outside_unit_square"),
        uv.get("texels_per_metre")))
    print("    textures:", [(row["slot"], row["file_exists"], row["size"])
                            for row in report["textures"]])
    print("    write_state:", report["write_state"])
    print("    warnings:", report["warnings"])


def check_named_file(available: dict) -> None:
    """The file the request named, whose coat turned out to be right already."""
    with Blender(NAMED_DRAFT):
        report = answer(available["mpfb_check_mesh_asset"](name=GARMENT, sections=["components"]))
        fractions = [row["outward_fraction"] for row in report["components"]["rows"]]
        print("taido_gi.blend: outward {!s}".format(fractions))
        check("taido_gi.blend's coat is not the inverted one", min(fractions) > 0.9, fractions)


def check_draft(available: dict) -> None:
    """The defects the request names, on the mesh that had them."""
    with tempfile.TemporaryDirectory() as directory:
        setup = Path(directory) / "wear_the_draft.py"
        setup.write_text(WEAR_THE_DRAFT, encoding="utf8")
        with Blender(FINISHED, before_bridge=setup):
            report, elapsed = timed(available["mpfb_check_mesh_asset"], name=GARMENT)
            print("draft, full answer: {:d} B in {:.0f} ms".format(
                len(json.dumps(report)), elapsed))
            describe(report)
            check("MPFB's validator passes the draft, which is the whole point",
                  report["validator"]["all_checks_ok"] is True)
            check("the draft has two components", report["components"]["component_count"] == 2,
                  report["components"]["component_count"])
            rows = report["components"]["rows"]
            coat = min(rows, key=lambda row: row["outward_fraction"])
            hakama = max(rows, key=lambda row: row["outward_fraction"])
            check("the coat is inside out", coat["outward_fraction"] < 0.1,
                  coat["outward_fraction"])
            check("the hakama's outward_fraction is near 1.0", hakama["outward_fraction"] > 0.9,
                  hakama["outward_fraction"])
            between = coat["overlap"]["other_components"][0]["face_pairs"]
            check("coat through hakama is the 77 recorded", between == 77, between)
            check("the coat passes through the body, seen through the mask",
                  coat["overlap"]["body"]["face_pairs_unmasked"] > 25,
                  (coat["overlap"]["body"]["face_pairs"],
                   coat["overlap"]["body"]["face_pairs_unmasked"]))
            check("the flap through the flap is the coat's self-overlap, near the 14 recorded",
                  5 <= coat["overlap"]["self"]["face_pairs"] <= 30,
                  coat["overlap"]["self"]["face_pairs"])
            repeated = answer(available["mpfb_check_mesh_asset"](name=GARMENT))
            check("a second call answers the same", repeated["components"] == report["components"])


def check_finished(available: dict) -> None:
    """The finished garment, and the masked trap."""
    with Blender(FINISHED):
        report, elapsed = timed(available["mpfb_check_mesh_asset"], name=GARMENT)
        print("finished, full answer: {:d} B in {:.0f} ms".format(
            len(json.dumps(report)), elapsed))
        describe(report)
        rows = report["components"]["rows"]
        check("the hakama and the coat both face outward",
              all(row["outward_fraction"] > 0.9 for row in rows[:2]),
              [row["outward_fraction"] for row in rows[:2]])
        check("the coat has come out of the hakama",
              not any(other["component"] in (0, 1) for row in rows[:2]
                      for other in row["overlap"]["other_components"]))
        family, elapsed = timed(available["mpfb_check_intersections"], name=GARMENT)
        row = family["pairs"][0]
        print("finished, intersections in {:.0f} ms: {!s}".format(elapsed, row))
        check("the masked body scores small and the unmasked one large: recorded 6 and 613",
              row["face_pairs"] < 50 and row["face_pairs_unmasked"] > 300,
              (row["face_pairs"], row["face_pairs_unmasked"]))
        band = answer(available["mpfb_check_intersections"](
            name=GARMENT, region={"min": {"z": 1.2}, "max": {"z": 1.25}}))["pairs"][0]
        check("a region narrows both counts",
              band["face_pairs"] <= row["face_pairs"]
              and band["face_pairs_unmasked"] < row["face_pairs_unmasked"],
              (band["face_pairs"], band["face_pairs_unmasked"]))


def dressed_character(available: dict) -> list:
    """One asset of each body part and three garments, which is a dressed character."""
    chosen = []
    for subdir, count in (("eyes", 1), ("eyebrows", 1), ("eyelashes", 1), ("teeth", 1),
                          ("tongue", 1), ("hair", 1), ("clothes", 3)):
        entries = answer(available["mpfb_list_assets"](asset_subdir=subdir, limit=count))["assets"]
        chosen.extend(entries)
    return chosen


def check_added_time(available: dict) -> None:
    """FR 13: what ``intersections`` adds to the call, on a rigged, fully dressed character."""
    with tempfile.TemporaryDirectory() as directory:
        durations = Path(directory) / "durations.txt"
        timer = Path(directory) / "time_the_field.py"
        timer.write_text(TIME_THE_FIELD.format(str(durations)), encoding="utf8")
        run_added_time(available, durations, timer)


def run_added_time(available: dict, durations: Path, timer: Path) -> None:
    """The dressed character itself."""
    with Blender(before_bridge=timer):
        body = answer(available["mpfb_create_human"]())["basemesh_name"]
        rigs = answer(available["mpfb_list_rigs"]())["rigs"]
        standard = next(rig["identifier"] for rig in rigs if "default" in rig["identifier"])
        answer(available["mpfb_add_rig"](name=body, identifier=standard))
        shares = []
        for entry in dressed_character(available):
            added, added_ms = timed(available["mpfb_add_asset"], name=body, path=entry["path"],
                                    object_type=entry["object_type"], measure_intersections=True)
            rows = added["intersections"]
            field_ms = float(durations.read_text(encoding="utf8").split()[-1])
            shares.append(field_ms / added_ms)
            print("  {:s}: add {:.0f} ms, of which the field {:.1f} ms ({:.0%}), {:d} rows, "
                  "largest {:d}".format(entry["fragment"], added_ms, field_ms, field_ms / added_ms,
                                        len(rows), max([row["face_pairs"] for row in rows] or [0])))
            check("{:s} answers intersections".format(entry["object_type"]), isinstance(rows, list))
        family, elapsed = timed(available["mpfb_check_intersections"], name=body)
        print("dressed character: {:d} pairs, {:d} B, {:.0f} ms".format(
            family["pairs_measured"], len(json.dumps(family)), elapsed))
        check("the full answer stays under the summary's 8 KB", len(json.dumps(family)) < 8192,
              len(json.dumps(family)))
        print("the field's share of the call: mean {:.0%}, worst {:.0%}".format(
            sum(shares) / len(shares), max(shares)))
        check("the added time is over a quarter of the call, which is why the field is opt-in",
              sum(shares) / len(shares) > 0.25, "{:.0%} mean".format(sum(shares) / len(shares)))
        entry = dressed_character(available)[-1]
        unasked = answer(available["mpfb_add_asset"](name=body, path=entry["path"],
                                                     object_type=entry["object_type"]))
        check("a call that does not ask reports null", unasked["intersections"] is None)

        controls = answer(available["mpfb_get_pose_controls"](name=body))["controls"]
        root = next(control["bone"] for entries in controls.values() for control in entries
                    if control["role"] == "root")
        answer(available["mpfb_set_pose_bones"](
            name=body, bones=[{"bone": root, "move_by": {"up": 0.05}}]))
        posed, elapsed = timed(available["mpfb_check_intersections"], name=body)
        check("a posed character measures, the second copy of the garment with it",
              posed["pairs_measured"] > family["pairs_measured"],
              (family["pairs_measured"], posed["pairs_measured"]))
        print("posed, every pair: {:.0f} ms".format(elapsed))


def main() -> int:
    available = tools()
    if NAMED_DRAFT.exists():
        check_named_file(available)
    else:
        print("skip: {!s} is absent".format(NAMED_DRAFT))
    if FINISHED.exists():
        check_draft(available)
        check_finished(available)
    else:
        print("skip: {!s} is absent".format(FINISHED))
    check_added_time(available)
    print("{:d} checks, {:d} failed".format(_checks, len(_failures)))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
