# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 061 against a real Blender: the five questions the request left to a measurement.

Through the real tool callables over a real socket against a headless Blender, on ``claude_demo``'s
table (renamed, so it is a rig of its own) and on the shipped ``default`` and ``game_engine`` as
baselines on the same body:

1. **Skin-only against whole-mesh heat** (FR 2): unweighted body vertices before the fill, then the
   bend numbers, for each pass.
2. **Neutral against modelled authoring** (FR 1): two differently modelled bodies weighted on the
   neutral body must get the same groups; the same rig weighted on the modelled body, as FR 060
   did, differs by how much; and both weightings, carried by index to a third body, bend how.
3. **``k`` for ``nearest``**: the skirt's edge stretch with the left hip abducted 45 degrees, per
   ``k``. It hangs between the legs, so ``k = 1`` splits it down the middle.
4. **``clean`` to 4 influences on ``default``**, through an authored copy of ``default``'s table
   transferred from ``default``: ``max_weight_removed``, and the bend before and after.
5. **The bend section's time**, on ``default``.

**Four commands the bridge does not have**, added to the running table in this process only, as
FR 060's check adds its own: one that switches the heat pass, ``k`` and neutral/modelled fitting
inside the running add-on, one that compares two bodies' groups, one that copies a body's groups to
another, and one that measures the skirt. The closed vocabulary is what the add-on ships.

**Nothing of the user's is written**: nothing is stored and no scene is saved. ``claude_demo`` is
read from the user's library and the check skips without it. It needs ``mpfb_bridge`` enabled in
the Blender it is pointed at (``local_environment.md``)::

    BLENDER=/path/to/blender python3 feature-requests/done/061-rig-weights-that-hold-up/live_check.py
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
LIBRARY = Path("/home/joepal/makehuman/mpfb/data/rigs")
DEMO = "claude_demo"
PREFIX = "fr061_"

# What the code ships, which this check's numbers must still support.
SHIPPED_HEAT_PASS = ("body",)
SHIPPED_K = 4

PASSES = (("body",), ("body", "helper"))
KS = (1, 2, 4, 8, 16, 32, 64)
ALL = ["coverage", "influences", "bones", "helpers", "symmetry", "bend"]

BEFORE_BRIDGE = r"""
import sys
import bpy
import numpy

bridge = next(name[:-len(".commands.table")] for name in sys.modules
              if name.endswith("mpfb_bridge.commands.table"))
table = sys.modules[bridge + ".commands.table"]
validation = sys.modules[bridge + ".validation"]
weight_rig = sys.modules[bridge + ".commands.weight_rig"]
check = sys.modules[bridge + ".commands.check_rig_weights"]
rig_weights = sys.modules[bridge + ".shared.rig_weights"]
rig_definition = sys.modules[bridge + ".shared.rig_definition"]
pose_writing = sys.modules[bridge + ".shared.pose_writing"]
frame_module = sys.modules[bridge + ".shared.character_frame"]
shipped_fit = weight_rig._neutral_fit


def _modelled_fit(services, basemesh, armature):
    # FR 060's body: the rig's definition fitted to the shape-key mix, as the character is modelled.
    fit = rig_definition.fit_definition(services, basemesh,
                                        weight_rig._neutral_header(services, basemesh, armature))
    segments = shipped_fit(services, basemesh, armature)[1]
    return (fit, segments)


def _set(params, resolution):
    weight_rig.HEAT_PASS_CLASSES = tuple(params["heat_pass"])
    rig_weights.NEAREST_K = int(params["k"])
    weight_rig._neutral_fit = _modelled_fit if params["modelled"] else shipped_fit
    return dict(heat_pass=list(weight_rig.HEAT_PASS_CLASSES), k=rig_weights.NEAREST_K,
                modelled=params["modelled"])


def _deform(name):
    basemesh = bpy.data.objects[name]
    armature = basemesh.parent
    deforming = rig_weights.deforming_bones(armature)
    return basemesh, rig_weights.read_weights(basemesh, set(deforming)), deforming


def _compare(params, resolution):
    _one, first, deforming = _deform(params["first"])
    _two, second, _deforming = _deform(params["second"])
    largest = 0.0
    total = 0.0
    counted = 0
    for bone in deforming:
        a = first.get(bone, {})
        b = second.get(bone, {})
        for index in set(a) | set(b):
            difference = abs(a.get(index, 0.0) - b.get(index, 0.0))
            largest = max(largest, difference)
            total += difference
            counted += 1
    return dict(max_difference=round(largest, 5),
                mean_difference=round(total / counted, 5) if counted else 0.0,
                entries=counted)


def _copy(params, resolution):
    _source, weights, deforming = _deform(params["source"])
    target = bpy.data.objects[params["target"]]
    rig_weights.write_groups(target, {bone: weights.get(bone, {}) for bone in deforming})
    return dict(copied=len(deforming))


def _skirt(params, resolution):
    services = resolution.services
    basemesh = bpy.data.objects[params["name"]]
    armature = basemesh.parent
    space = rig_definition.Space(basemesh, armature)
    fit = rig_definition.fit_definition(services, basemesh, {"bones": {}, "version": 110})
    anchors, _from = rig_definition.head_joints(services, armature, fit, space)
    bone_name = sorted(name for name in rig_weights.deforming_bones(armature)
                       if anchors.get(name) == "joint-l-upper-leg")[0]
    the_layout = rig_weights.layout(services, basemesh)
    skirt = set(the_layout.helpers["helper-skirt"])
    edges = [tuple(edge.vertices) for edge in basemesh.data.edges
             if edge.vertices[0] in skirt and edge.vertices[1] in skirt]
    edges = numpy.array(edges, dtype=numpy.int64)
    pose_bone = armature.pose.bones[bone_name]
    axis = check._axis(frame_module.Frame(armature), armature.data.bones[bone_name], {"left": 1.0})
    from mathutils import Quaternion
    import math
    with check._only_the_armature(basemesh):
        rest, _triangles = check._evaluated(basemesh)
        saved = pose_writing.snapshot(armature, [bone_name])
        try:
            _l, orientation, _s = pose_writing.own_matrix(pose_bone).decompose()
            pose_writing.write(pose_bone, orientation=Quaternion(
                axis, math.radians(params["degrees"])) @ orientation)
            bent, _triangles = check._evaluated(basemesh)
        finally:
            pose_writing.restore(armature, saved)
    before = numpy.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    after = numpy.linalg.norm(bent[edges[:, 0]] - bent[edges[:, 1]], axis=1)
    ratios = after / before
    return dict(bone=bone_name, edges=int(len(edges)),
                p99=round(float(numpy.percentile(ratios, 99)), 3),
                max=round(float(ratios.max()), 3))


for command, handler, params in (
        ("live_check_set", _set,
         (validation.Param("heat_pass", validation.TYPE_ARRAY, required=True),
          validation.Param("k", validation.TYPE_INTEGER, required=True),
          validation.Param("modelled", validation.TYPE_BOOLEAN, required=True))),
        ("live_check_compare", _compare,
         (validation.Param("first", validation.TYPE_STRING, required=True),
          validation.Param("second", validation.TYPE_STRING, required=True))),
        ("live_check_copy", _copy,
         (validation.Param("source", validation.TYPE_STRING, required=True),
          validation.Param("target", validation.TYPE_STRING, required=True))),
        ("live_check_skirt", _skirt,
         (validation.Param("name", validation.TYPE_STRING, required=True),
          validation.Param("degrees", validation.TYPE_NUMBER, required=True)))):
    table.COMMANDS[command] = table.Command(name=command, handler=handler, params=params,
                                            requires_mpfb=True,
                                            summary="This check's own, in this process only.")
"""

_failures = []
_checks = 0
_record = {}


def check(what: str, passed: bool, observed: object = None) -> None:
    """One claim. Printed either way, so that the run is its own record."""
    global _checks  # pylint: disable=global-statement
    _checks += 1
    print("{:s} {:s}{:s}".format("ok  " if passed else "FAIL", what,
                                 "" if observed is None else "  [{!s}]".format(observed)))
    if not passed:
        _failures.append(what)


def note(what: str, observed: object) -> None:
    """A measurement with no pass or fail, kept for the request's record."""
    _record[what] = observed
    print("note {:s}  [{!s}]".format(what, observed))


class Blender:
    """A headless Blender with the bridge up on a port of its own, stopped on exit."""

    def __init__(self, before_bridge: Path) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.process = subprocess.Popen(  # pylint: disable=consider-using-with
            [BLENDER, "--background", "--python", str(before_bridge),
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
        raise RuntimeError(json.dumps(envelope)[:1200])
    return envelope["result"]


def live(command: str, **params: object) -> dict:
    """One of this check's own commands, straight over the socket."""
    from mpfbmcp import backend  # pylint: disable=import-outside-toplevel
    return answer(backend.send(command, params=params))


def timed(call, **arguments) -> tuple[dict, float]:
    """A call's answer and how long it took, in milliseconds."""
    started = time.perf_counter()
    result = answer(call(**arguments))
    return (result, (time.perf_counter() - started) * 1000.0)


def human(available: dict, **macro: float) -> str:
    return answer(available["mpfb_create_human"](**macro))["basemesh_name"]


def configure(heat_pass=SHIPPED_HEAT_PASS, k=SHIPPED_K, modelled=False) -> None:
    live("live_check_set", heat_pass=list(heat_pass), k=k, modelled=modelled)


def bend_line(result: dict) -> dict:
    """Each movement's four numbers, compactly."""
    rows = {}
    for row in result["bend"]["movements"]:
        if not row["tested"]:
            rows[row["movement"]] = row["not_tested"]
            continue
        rows[row["movement"]] = (row["collapse"], row["edge_stretch"]["p99"],
                                 row["self_intersections"]["bent"], row["stray"],
                                 row["moved_vertices"])
    return rows


def rigged(available: dict, table: list, **macro: float) -> str:
    body = human(available, **macro)
    built = answer(available["mpfb_create_rig"](name=body, bones=table))
    check("the table builds on {!s}".format(macro or "the default body"), built["created"] is True,
          built["message"])
    return body


def weighted(available: dict, body: str) -> dict:
    return answer(available["mpfb_weight_rig"](name=body, method="automatic",
                                               exclude_bones=[PREFIX + "root"]))


def heat_passes(available: dict, table: list) -> None:
    """Question 1: which heat pass ships."""
    for heat_pass in PASSES:
        configure(heat_pass=heat_pass)
        body = rigged(available, table)
        result, ms = timed(available["mpfb_weight_rig"], name=body, method="automatic",
                           exclude_bones=[PREFIX + "root"])
        label = "+".join(heat_pass)
        note("pass {:s}: weight_rig ms".format(label), round(ms))
        note("pass {:s}: unweighted before the fill".format(label),
             result["unweighted"]["before_fill"])
        report = answer(available["mpfb_check_rig_weights"](name=body, sections=ALL))
        note("pass {:s}: helpers' dominant bones".format(label),
             {row["group"]: (row["dominant_bone"], row["dominant_share"])
              for row in report["helpers"]["rows"]
              if row["group"] in ("helper-l-eye", "helper-upper-teeth", "helper-tongue")})
        note("pass {:s}: bend (collapse, p99 stretch, self-intersections, stray, moved)".format(label),
             bend_line(report))
        note("pass {:s}: far vertices".format(label), report["bones"]["far_vertices_total"])
    configure()


def neutral_against_modelled(available: dict, table: list) -> None:
    """Question 2: the authoring body leaks into the weights unless the pass is neutral."""
    first = rigged(available, table)
    second = rigged(available, table, gender=1.0, age=0.9, weight=0.9, height=0.1)
    third = rigged(available, table, gender=0.0, age=0.2, weight=0.1, height=0.9)
    one = weighted(available, first)
    two = weighted(available, second)
    check("the neutral pass says so", one["weighted_on"] == "neutral_base_mesh")
    same = live("live_check_compare", first=first, second=second)
    note("neutral on two bodies, difference", same)
    check("two differently modelled bodies get the same groups", same["max_difference"] < 0.001,
          same)
    modelled_body = rigged(available, table, gender=1.0, age=0.9, weight=0.9, height=0.1)
    configure(modelled=True)
    weighted(available, modelled_body)
    configure()
    leak = live("live_check_compare", first=second, second=modelled_body)
    note("neutral against modelled on the second body, difference", leak)
    check("weighting the modelled body gives different groups", leak["max_difference"] > 0.01, leak)
    for label, source in (("neutral", second), ("modelled", modelled_body)):
        live("live_check_copy", source=source, target=third)
        report = answer(available["mpfb_check_rig_weights"](name=third, sections=["bend"]))
        note("{:s} weights from the second body, bent on the third".format(label),
             bend_line(report))


def nearest_k(available: dict, table: list) -> None:
    """Question 3: how many skin vertices the nearest fill blends."""
    body = rigged(available, table)
    for k in KS:
        configure(k=k)
        weighted(available, body)
        note("k {:d}: the skirt with the left hip abducted 45 degrees".format(k),
             live("live_check_skirt", name=body, degrees=45.0))
    configure()
    shipped = human(available)
    answer(available["mpfb_add_rig"](name=shipped, identifier="default"))
    note("default's own weights: the skirt with the left hip abducted 45 degrees",
         live("live_check_skirt", name=shipped, degrees=45.0))


def cleaned_default(available: dict) -> None:
    """Question 4: what a cap of four costs on default's own weights."""
    body = human(available)
    table = answer(available["mpfb_get_rig_definition"](name=body, rig="default",
                                                       compact=True))["bones"]
    built = answer(available["mpfb_create_rig"](name=body, bones=table))
    check("default's table builds as an authored rig", built["created"] is True, built["message"])
    moved = answer(available["mpfb_weight_rig"](name=body, method="transfer", from_rig="default"))
    exact = sum(1 for row in moved["bones"] if row["matched_by"] == "exact")
    check("default's weights transfer onto its own table exactly",
          exact == len(moved["bones"]), (exact, len(moved["bones"])))
    before = answer(available["mpfb_check_rig_weights"](name=body, sections=ALL))
    note("default transferred: influences", before["influences"]["histogram"])
    cleaned = answer(available["mpfb_weight_rig"](name=body, method="clean", max_influences=4))
    note("clean to 4: the clean", {key: cleaned["clean"][key] for key in (
        "vertices_trimmed", "vertices_normalised", "max_weight_removed")})
    note("clean to 4: groups rescaled", len(cleaned["groups_rescaled"]))
    after = answer(available["mpfb_check_rig_weights"](name=body, sections=ALL))
    check("the clean leaves at most four influences", after["influences"]["max_influences"] <= 4,
          after["influences"]["histogram"])
    check("the clean leaves every vertex normalised", after["influences"]["unnormalised"] == 0)
    note("default bend before the clean", bend_line(before))
    note("default bend after the clean", bend_line(after))


def baselines(available: dict, table: list) -> None:
    """Question 5, and the shipped rigs beside the authored one on the same body."""
    for rig in ("default", "game_engine"):
        body = human(available)
        answer(available["mpfb_add_rig"](name=body, identifier=rig))
        report, ms = timed(available["mpfb_check_rig_weights"], name=body, sections=ALL)
        plain, plain_ms = timed(available["mpfb_check_rig_weights"], name=body)
        note("{:s}: check ms with bend, without".format(rig), (round(ms), round(plain_ms)))
        note("{:s}: bend section ms".format(rig), report["bend"]["milliseconds"])
        note("{:s}: default answer bytes".format(rig), len(json.dumps(plain)))
        note("{:s}: bend".format(rig), bend_line(report))
        note("{:s}: rigid helpers".format(rig),
             [row["group"] for row in report["helpers"]["rows"] if row["rigid"]])
        note("{:s}: far vertices, symmetry".format(rig),
             (report["bones"]["far_vertices_total"], report["symmetry"]["max_difference"]))
    body = rigged(available, table)
    weighted(available, body)
    report = answer(available["mpfb_check_rig_weights"](name=body, sections=ALL))
    note("claude_demo: bend", bend_line(report))
    note("claude_demo: rigid helpers",
         [row["group"] for row in report["helpers"]["rows"] if row["rigid"]])
    note("claude_demo: far vertices, symmetry",
         (report["bones"]["far_vertices_total"], report["symmetry"]["max_difference"]))


def main() -> int:
    if not (LIBRARY / (DEMO + ".json")).is_file():
        print("skip: no {:s} in {!s}".format(DEMO, LIBRARY))
        return 0
    with tempfile.TemporaryDirectory() as scratch:
        before = Path(scratch) / "before_bridge.py"
        before.write_text(BEFORE_BRIDGE, encoding="utf-8")
        with Blender(before):
            available = tools()
            body = human(available)
            demo = answer(available["mpfb_get_rig_definition"](name=body,
                                                               rig="custom." + DEMO))["bones"]
            table = []
            for row in demo:
                copy = dict(row)
                copy["name"] = PREFIX + row["name"]
                copy["parent"] = PREFIX + row["parent"] if row["parent"] else ""
                table.append(copy)
            heat_passes(available, table)
            neutral_against_modelled(available, table)
            nearest_k(available, table)
            cleaned_default(available)
            baselines(available, table)
    print("\n{:d} checks, {:d} failed".format(_checks, len(_failures)))
    print(json.dumps(_record, indent=1))
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
