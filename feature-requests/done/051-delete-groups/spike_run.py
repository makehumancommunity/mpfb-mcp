# SPDX-License-Identifier: GPL-3.0-or-later

"""
Runs :mod:`spike` over the garments and prints the comparison. See that module's docstring.

The three the request names first, then some of other construction, added once those three had shown what to
look at. Each writes its reading into ``spike_results.json`` beside this file.

Needs MPFB enabled in the Blender it is pointed at (``local_environment.md``)::

    BLENDER=/path/to/blender python3 feature-requests/done/051-delete-groups/spike_run.py
"""

from __future__ import annotations

__all__ = ()

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BLENDER = os.environ.get("BLENDER", shutil.which("blender") or "blender")
HERE = Path(__file__).resolve().parent
GI_SCENE = "/export/3d/taido/taido_gi_v2.blend"

GARMENTS = (
    ("scene", "Human.nurse_uniform_with_pants"),
    ("library", "toigo_keyhole_neck_dress"),
    ("library", "mindfront_m_suit_01"),
    ("library", "toigo_keyhole_tank_top"),
    ("library", "callharvey3d_harvey_female_scrubtop2"),
    ("library", "cortu_cargo_pants"),
    ("library", "cortu_jeans_shorts"),
    ("library", "aethelraed_flapper_dress"),
    ("library", "culturalibre_hero-heroine_gloves_1"),
    ("library", "culturalibre_hero_boots_1"),
    ("library", "callharvey3d_harvey_croptopsweater1"),
)

# What each loop of the request's three garments is, by a person reading the table, longest first and
# over 10 cm. Gap's rule says only "limb" or "trunk", so a cuff and a hem count alike for it.
LABELS = {
    "Human.nurse_uniform_with_pants": ("trunk", "trunk", "hem", "hem", "cuff", "cuff"),
    "toigo_keyhole_neck_dress": ("hem", "trunk", "trunk", "trunk", "trunk"),
    "mindfront_m_suit_01": ("trunk", "trunk", "trunk", "trunk", "trunk", "hem", "hem",
                            "cuff", "cuff", "cuff", "cuff", "cuff", "cuff"),
}


def read(kind: str, name: str, out: Path) -> dict:
    """One garment's reading, from a Blender of its own."""
    command = [BLENDER, "--background"]
    if kind == "scene":
        command.append(GI_SCENE)
    command.extend(("--python-exit-code", "1", "--python", str(HERE / "spike.py"), "--", kind, name, str(out)))
    done = subprocess.run(command, check=False, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError("{:s}: {:s}".format(name, done.stdout[-600:] + done.stderr[-600:]))
    return json.loads(out.read_text(encoding="utf8"))


def main() -> None:
    results = dict()
    with tempfile.TemporaryDirectory() as directory:
        for kind, name in GARMENTS:
            results[name] = read(kind, name, Path(directory) / "reading.json")
    (HERE / "spike_results.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf8")
    for name, answer in results.items():
        print("== {:s}  (verts {:d}, components {!s}, groups {!s})".format(
            name, answer["garment_vertices"], answer["components"][:5], answer["groups"]))
        for row in answer["loops"]:
            if row["perimeter"] < 0.1:
                continue
            print("  v{:<4d} p{:<6.3f} z{:.2f}-{:.2f} gap{:.3f} skin{:.2f} exp{:.2f} chains:{:<6s} bones:{:<6s} "
                  "gap:{:<6s} {!s} {:s}".format(
                      row["vertices"], row["perimeter"], row["low_z"], row["high_z"], row["gap_median"],
                      row["reaches_skin"], row["exposed"], row["kind_by_chains"], row["kind_by_bones"],
                      row["kind_by_gap"], row["chains"], row["dominant_bones"][0] if row["dominant_bones"] else "-"))
        small = sum(1 for row in answer["loops"] if row["perimeter"] < 0.1)
        print("  and {:d} loops under 10 cm".format(small))
    for signal in ("kind_by_chains", "kind_by_bones", "kind_by_gap"):
        right = 0
        total = 0
        for name, labels in LABELS.items():
            rows = [row for row in results[name]["loops"] if row["perimeter"] >= 0.1]
            for row, label in zip(rows, labels):
                total += 1
                wanted = "limb" if signal == "kind_by_gap" and label != "trunk" else label
                right += row[signal] == wanted
        print("{:s}: {:d} of {:d}".format(signal, right, total))


main()
