# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR-8: the numbers four decisions rest on.

Four decisions in this package were argued against a round-trip figure of about
one second, measured once, on one tool, in
[FR 005](../feature-requests/done/005-list-assets/README.md). This script
re-measures it and takes the three further measurements FR 013 asks for. Every
timing is three runs with the median reported, and the first call to a tool is
reported separately, since it pays for MPFB's caches.

**Where a call's time goes** is the one that needs a word. FR 012 records the
round trip undivided and deliberately does not instrument the generated program
- a diagnostic setting that changes the program sent would destroy the one
property the record depends on. So the split is taken here instead, ad hoc, the
way FR 013 points at: a probe of its own compiles a real assembled program with
``compile()`` and times that, which is the ``exec`` half; the transport half is
an empty program's round trip; and MPFB's own work is what is left.

Run with::

    python3 verification/measure.py
"""

from __future__ import annotations

__all__ = ("run",)

import json
import math
import statistics
import sys
import time

from mpfbmcp import codegen, shared_cache

from verification import fixtures, harness
from verification.harness import probe

RUNS = 3


def run() -> dict:
    tools = harness.tools()
    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()

    measurements = dict(
        round_trip=_round_trip(tools),
        transport_by_program_size=_transport_by_program_size(),
        shared_source_cache=_shared_source_cache(tools),
        where_the_time_goes=_where_the_time_goes(),
        batching=_batching(tools),
        per_skin_type=_per_skin_type(tools),
        one_asset=_one_asset(tools),
        program_sizes=_program_sizes(),
    )
    harness.cleanup_scratch_scene()

    print(json.dumps(measurements, indent=1), flush=True)
    path = harness.results_directory() + "/measurements.json"
    handle = open(path, "w", encoding="utf-8")
    json.dump(measurements, handle, indent=1, default=repr)
    handle.close()
    print("-> {}".format(path), flush=True)
    return measurements


def _timed(call) -> float:
    started = time.perf_counter()
    call()
    return round((time.perf_counter() - started) * 1000.0, 1)


def _series(call, runs: int = RUNS) -> dict:
    """First call reported separately: it is the one that pays for the caches."""
    first = _timed(call)
    rest = [_timed(call) for _ in range(runs)]
    return dict(first_ms=first, runs_ms=rest, median_ms=round(statistics.median(rest), 1))


def _round_trip(tools: dict) -> dict:
    """The baseline itself, on three tools rather than the one FR 005 used."""
    empty = _series(lambda: probe("empty", "result = dict(ok=True)\n"))
    status = _series(lambda: tools["mpfb_get_status"]())
    objects = _series(lambda: tools["mpfb_list_objects"]())
    return dict(empty_program=empty, mpfb_get_status=status, mpfb_list_objects=objects)


def _where_the_time_goes() -> dict:
    """Transport, compile, and what is left - measured inside Blender.

    The compile figure is the interesting one, because it is what the
    readability-over-size tradeoff costs: a payload's comments and docstrings
    are most of a 20-50 KB program.
    """
    programs = dict()
    for payload, bootstrap in (("create_human.py", "raising"),
                               ("get_status.py", "non_raising"),
                               ("set_targets.py", "raising"),
                               ("add_asset.py", "raising")):
        shared = []
        if payload == "set_targets.py":
            shared = ["target_categories.py", "refit_blocker.py", "performed.py"]
        if payload == "add_asset.py":
            shared = ["asset_sections.py"]
        programs[payload] = codegen.assemble(
            payload, bootstrap=bootstrap, shared=shared,
            params=dict(name=None, macro_details=None))
    return probe("compile_cost", _COMPILE_COST_CODE,
                 programs=programs, runs=RUNS)


_COMPILE_COST_CODE = '''
import time

results = dict()
for payload in sorted(PARAMS["programs"]):
    source = PARAMS["programs"][payload]
    timings = []
    for _run in range(PARAMS["runs"]):
        started = time.perf_counter()
        compile(source, "<measurement>", "exec")
        timings.append(round((time.perf_counter() - started) * 1000.0, 3))
    results[payload] = dict(bytes=len(source.encode("utf-8")),
                            lines=len(source.split("\\n")),
                            compile_ms=timings)

result = dict(compile=results)
'''


# The add-on reads one chunk of this many bytes per timer tick, and its
# preference for that tick is 0.25 s while busy and 1.0 s once five seconds have
# passed without a request being *executed* - a transfer in progress does not
# count as work. Named here rather than imported: blender_mcp is not a
# dependency (see specifications/architecture.md), and a value that drifts out
# of agreement with the add-on shows up as a failed prediction below rather than
# as a silently wrong model.
ADDON_RECV_BUFFER_SIZE = 4096
ADDON_TICK_BUSY_MS = 250.0
ADDON_TICK_IDLE_MS = 1000.0
ADDON_IDLE_DELAY_S = 5.0


def _filler_program(kilobytes: int) -> str:
    """A program of a given size that does nothing, so only transport is timed."""
    line = "# " + "x" * 78 + "\n"
    return line * int(kilobytes * 1024 / 80) + "result = dict(ok=True)\n"


def _transport_by_program_size() -> dict:
    """What a byte of generated program costs, which is the whole of FR 017.

    FR 013 measured "the round trip" as 250 ms on an empty program and four
    decisions were argued against that number. It is not a round trip: it is one
    timer tick, and the add-on reads one 4 KB chunk per tick. So the transport
    cost of a program is its *size*, at about 250 ms per 4 KB against a Blender
    that has been talked to recently and about 1 s per 4 KB against one that has
    been quiet for five seconds. A 50 KB program costs 3 s or 12 s and it makes
    no difference at all what it computes.

    Both intervals are measured here, because the second is the one an agent
    actually meets: it thinks between calls.
    """
    measurements = []
    for kilobytes in (0, 5, 10, 20, 40, 60):
        program = _filler_program(kilobytes)
        chunks = max(1, math.ceil(len(program.encode("utf-8")) / ADDON_RECV_BUFFER_SIZE))
        # Woken first, so this one is charged the busy interval.
        probe("wake", "result = dict(ok=True)\n")
        busy = _timed(lambda source=program: probe("filler", source))
        time.sleep(ADDON_IDLE_DELAY_S + 1.0)
        idle = _timed(lambda source=program: probe("filler", source))
        measurements.append(dict(
            kilobytes=kilobytes, bytes=len(program.encode("utf-8")), chunks=chunks,
            busy_ms=busy, idle_ms=idle,
            predicted_busy_ms=round(chunks * ADDON_TICK_BUSY_MS, 1),
            predicted_idle_ms=round((chunks - 1) * ADDON_TICK_IDLE_MS, 1)))
    return dict(
        note="one recv({}) per timer tick, in blender_mcp's _service_clients()".format(
            ADDON_RECV_BUFFER_SIZE),
        measurements=measurements)


def _shared_source_cache(tools: dict) -> dict:
    """FR 017's own before/after: the four tools that carry shared fragments.

    The program is measured beside the duration, because the duration is a
    function of it and of nothing else that matters. "Cold" is the first call of
    a Blender session, which carries the fragments' source; "warm" is every call
    after it, which names them.

    **Read the bytes, not the milliseconds.** A one-chunk probe precedes each
    timing to try to charge it the add-on's busy interval, and it does not
    reliably succeed: the add-on's idle countdown is global state this side
    cannot see, so a run can come back with some timings at 250 ms per chunk and
    others at 1 s per chunk, differing by four times for the same program. The
    durable measurement here is ``cold_bytes`` and ``warm_bytes``; what a chunk
    costs, in both intervals and against predictions, is
    ``transport_by_program_size`` above, and the two multiply.
    """
    sizes = []
    real_send_code = shared_cache.send_code

    def spy(code, strict_json=True):
        sizes.append(len(code.encode("utf-8")))
        return real_send_code(code, strict_json=strict_json)

    fixtures.fresh_human(tools, "TableCharacter")
    # A real category off this install rather than a name written here, which
    # would make the measurement fail as a resolution error the day MPFB renames
    # one.
    section, category = probe(
        "one_category", _THIRTY_CATEGORIES_CODE, count=1)["categories"][0]
    calls = (
        ("mpfb_list_targets", lambda: tools["mpfb_list_targets"](limit=5)),
        ("mpfb_get_target_stack", lambda: tools["mpfb_get_target_stack"](
            name="TableCharacter", limit=5)),
        ("mpfb_set_targets", lambda: tools["mpfb_set_targets"](
            name="TableCharacter",
            modifiers=[dict(section=section, category=category, value=0.3)])),
        ("mpfb_symmetrize_targets", lambda: tools["mpfb_symmetrize_targets"](
            name="TableCharacter", direction="left_to_right", dry_run=True)),
    )

    measured = dict()
    shared_cache.send_code = spy
    try:
        for name, call in calls:
            # Each tool is asked to go cold again, so the two halves are
            # measured on the same call rather than across tools. Blender still
            # holds the source; what is measured is what this process sends,
            # which is what the memo decides.
            shared_cache._PRIMED.clear()  # pylint: disable=protected-access
            probe("wake", "result = dict(ok=True)\n")
            cold_ms = _timed(call)
            cold_bytes = sizes[-1]
            probe("wake", "result = dict(ok=True)\n")
            warm_ms = _timed(call)
            warm_bytes = sizes[-1]
            measured[name] = dict(
                cold_ms=cold_ms, cold_bytes=cold_bytes,
                warm_ms=warm_ms, warm_bytes=warm_bytes,
                saved_bytes=cold_bytes - warm_bytes,
                saved_ms=round(cold_ms - warm_ms, 1))
    finally:
        shared_cache.send_code = real_send_code
    harness.cleanup_scratch_scene()
    return measured


def _batching(tools: dict) -> dict:
    """FR 008's batching claim: thirty modifier changes one way and the other.

    The second half of the claim - how much of the difference is target files
    coming off disk rather than round trips - is separated by running the batch
    twice: the second time every file is already on the mesh.
    """
    categories = probe("thirty_categories", _THIRTY_CATEGORIES_CODE, count=30)["categories"]
    modifiers = [dict(section=entry[0], category=entry[1], value=0.4) for entry in categories]

    fixtures.fresh_human(tools, "BatchCharacter")
    cold_batch = _timed(lambda: tools["mpfb_set_targets"](
        name="BatchCharacter", modifiers=modifiers))
    warm_batch = _timed(lambda: tools["mpfb_set_targets"](
        name="BatchCharacter", modifiers=[dict(entry, value=0.5) for entry in modifiers]))
    harness.cleanup_scratch_scene()

    fixtures.fresh_human(tools, "OneAtATimeCharacter")
    started = time.perf_counter()
    for entry in modifiers:
        tools["mpfb_set_targets"](name="OneAtATimeCharacter", modifiers=[entry])
    cold_one_at_a_time = round((time.perf_counter() - started) * 1000.0, 1)

    started = time.perf_counter()
    for entry in modifiers:
        tools["mpfb_set_targets"](name="OneAtATimeCharacter",
                                  modifiers=[dict(entry, value=0.5)])
    warm_one_at_a_time = round((time.perf_counter() - started) * 1000.0, 1)
    harness.cleanup_scratch_scene()

    return dict(categories=len(modifiers),
                one_call_cold_ms=cold_batch, one_call_warm_ms=warm_batch,
                thirty_calls_cold_ms=cold_one_at_a_time,
                thirty_calls_warm_ms=warm_one_at_a_time,
                # What the batching actually buys, and what of it is transport.
                saved_ms=round(cold_one_at_a_time - cold_batch, 1),
                disk_ms_in_the_batch=round(cold_batch - warm_batch, 1))


_THIRTY_CATEGORIES_CODE = '''
import json, os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
LocationService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["LocationService"]

handle = open(os.path.join(str(LocationService.get_mpfb_data("targets")), "target.json"), "r")
table = json.load(handle)
handle.close()

# Unsided categories only, so a single value writes a single target and the
# comparison is thirty writes either way.
categories = []
for section in sorted(table):
    for category in table[section].get("categories", []):
        if category.get("has_left_and_right"):
            continue
        categories.append([section, category["name"]])

result = dict(categories=categories[:PARAMS["count"]], available=len(categories))
'''


def _per_skin_type(tools: dict) -> dict:
    """MPFB documents LAYERED as too heavy for animation. Is it too heavy here?"""
    skin = fixtures.skin_fragment(tools)
    timings = dict()
    for skin_type in ("MAKESKIN", "ENHANCED", "ENHANCED_SSS", "LAYERED", "GAMEENGINE"):
        character = "MeasureSkin" + skin_type
        fixtures.fresh_human(tools, character)
        timings[skin_type] = _series(
            lambda name=character, kind=skin_type: tools["mpfb_set_skin"](
                name=name, fragment=skin, skin_type=kind), runs=2)
        harness.cleanup_scratch_scene()
    return timings


def _one_asset(tools: dict) -> dict:
    """What one-asset-per-call rests on: how long one asset takes."""
    fixtures.fresh_human(tools, "MeasureAssetCharacter")
    timings = []
    listing = tools["mpfb_list_assets"](asset_subdir="clothes", limit=6)["result"]
    for entry in listing["assets"][:4]:
        timings.append(dict(fragment=entry["fragment"], ms=_timed(
            lambda fragment=entry["fragment"]: tools["mpfb_add_asset"](
                name="MeasureAssetCharacter", fragment=fragment, asset_type="Clothes"))))
    harness.cleanup_scratch_scene()
    return dict(assets=timings,
                median_ms=round(statistics.median([entry["ms"] for entry in timings]), 1))


def _program_sizes() -> dict:
    """Every payload's source in bytes, and the bootstrap that goes above it.

    Measured on the payload rather than on an assembled program, because
    assembling one needs that tool's parameters and the point here is the
    *source* size the compile figure above is charged against.
    """
    sizes = dict()
    for payload in codegen.payload_names():
        source = codegen.read_payload(payload)
        sizes[payload] = dict(bytes=len(source.encode("utf-8")),
                              lines=len(source.split("\n")))
    shared = dict()
    for fragment in codegen.shared_names():
        source = codegen.read_shared(fragment)
        shared[fragment] = dict(bytes=len(source.encode("utf-8")),
                                lines=len(source.split("\n")))
    total = sum(entry["bytes"] for entry in sizes.values())
    return dict(payloads=sizes, shared=shared, payload_total_bytes=total,
                payload_mean_bytes=round(total / len(sizes)))


if __name__ == "__main__":
    run()
