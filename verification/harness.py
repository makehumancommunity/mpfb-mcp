# SPDX-License-Identifier: GPL-3.0-or-later

"""
The instrument the smoke run stands on: the tools, a scene of its own, and a
report.

**Checks run through the real tool callables**, taken off the server
``build_server()`` builds. A check written as a hand-assembled ``send_code()``
call would verify a program no MCP client will ever send: a tool module's own
validation, defaulting and coercion is a large part of what is under test here.

**The scratch scene, not a scratch file.** The run happens in whatever Blender
the user has prepared, and that Blender holds their work; reloading a home file
to get a clean baseline would discard it. So the harness makes its own scene,
builds in that, and deletes what it made. ``snapshot``/``diff_snapshots`` is
what turns "deleted what it made" from a claim into an assertion, and the
``.blend`` is never saved by anything here.

**Probes are sent with a payload marker.** ``probe()`` is the harness's own
channel into Blender - the snapshot, the scene, the rename - and goes through
the same ``send_code()`` every tool uses, so FR 012's record covers it too. The
marker is what keeps those records named rather than all landing under
``unnamed``.

Nothing here is unit-tested and nothing here may be imported by ``src/``.
"""

from __future__ import annotations

__all__ = (
    "DATABLOCK_COLLECTIONS",
    "MUTATING_VERBS",
    "Report",
    "SCRATCH_SCENE",
    "cleanup_scratch_scene",
    "descriptions",
    "diff_snapshots",
    "ensure_scratch_scene",
    "main_guard",
    "performed_disagreement",
    "probe",
    "rename_object",
    "results_directory",
    "snapshot",
    "tools",
)

import json
import os
import sys
import time

from mpfbmcp import build_server
from mpfbmcp.connection import send_code

# The twelve collections FR 006's run named, plus the dirty flag. Kept as a
# tuple of (report key, bpy.data attribute) rather than derived from bpy.data,
# because a collection appearing or disappearing between Blender versions
# should change this list visibly rather than silently change what "identical"
# means.
DATABLOCK_COLLECTIONS = (
    ("objects", "objects"),
    ("meshes", "meshes"),
    ("materials", "materials"),
    ("images", "images"),
    ("node_groups", "node_groups"),
    ("armatures", "armatures"),
    ("actions", "actions"),
    ("shape_keys", "shape_keys"),
    ("collections", "collections"),
    ("textures", "textures"),
    ("brushes", "brushes"),
    ("worlds", "worlds"),
)

SCRATCH_SCENE = "MPFBMCP_VERIFY"

# The verb each mutating tool reports beside the uniform ``performed`` flag
# (FR 014). ``None`` is mpfb_create_human, which has no verb of its own: it
# creates a character or comes back as an error envelope.
#
# This is not a second opinion about what "performed" means - the payloads
# decide that, on the far side of the socket. It is the audit that would catch
# a payload stamping the flag from the wrong variable, which is the one mistake
# the unit tests can miss, because there the verb and the flag are read out of
# the same stub run. Here they are read out of a real Blender.
MUTATING_VERBS = {
    "mpfb_create_human": None,
    "mpfb_set_macro_details": "recalculated",
    "mpfb_refit_human": "refit_performed",
    "mpfb_set_targets": "applied",
    "mpfb_symmetrize_targets": "changed",
    "mpfb_add_rig": "added",
    "mpfb_generate_rigify_rig": "generated",
    "mpfb_add_asset": "added",
    "mpfb_remove_asset": "removed",
    "mpfb_set_skin": "applied",
    "mpfb_set_asset_material": "applied",
}


def performed_disagreement(tool_name: str, envelope: dict) -> str | None:
    """Why ``performed`` and this tool's verb disagree in one answer, or None."""
    if not isinstance(envelope, dict) or envelope.get("status") != "ok":
        return None
    result = envelope.get("result")
    if not isinstance(result, dict):
        return None
    if "performed" not in result:
        return "no 'performed' in the answer"
    performed = result["performed"]
    if not isinstance(performed, bool):
        return "'performed' is {!r}, not a bool".format(performed)
    verb = MUTATING_VERBS[tool_name]
    if verb is None:
        return None
    if verb not in result:
        # Every refusal carries the verb too, so its absence is itself a finding.
        return "no {!r} in the answer beside 'performed'".format(verb)
    expected = bool(result[verb])
    if tool_name == "mpfb_symmetrize_targets" and result.get("dry_run"):
        # The one tool whose verb is deliberately not the flag: a dry run lists
        # the changes it would make and writes none of them.
        expected = False
    if performed != expected:
        return "performed={!r} but {}={!r} (dry_run={!r})".format(
            performed, verb, result[verb], result.get("dry_run"))
    return None


def _registered() -> list:
    """The tools of the server ``main()`` runs, not a re-registration of them.

    ``build_server()`` is what an MCP client connects to, so asking it is what
    makes "called the way a client would call it" true rather than nearly true -
    and its descriptions are the dedented ones the client downloads, which is
    what the smoke run holds each item's contract keys to.
    """
    server = build_server()
    return list(server._tool_manager.list_tools())  # noqa: SLF001


def tools() -> dict:
    """Every MCP tool, by name, as the plain callable behind the coroutine.

    This is the same route ``tests/`` takes into a tool, and it is what FR 023's
    coverage rule is measured against: the smoke run asks this for the set of
    registered tools and fails if any of them has no item.
    """
    return {tool.name: tool.fn for tool in _registered()}


def descriptions() -> dict:
    """Every tool's description, by name - the contract an MCP client downloads."""
    return {tool.name: tool.description or "" for tool in _registered()}


def probe(label: str, code: str, **params: object) -> dict:
    """Run harness-owned code inside Blender and return its ``result``.

    The first argument is ``label`` rather than ``name`` so that a probe can take
    a ``name=`` parameter of its own. ``params`` is bound as ``PARAMS`` from a
    JSON literal, the way ``codegen``'s prelude binds a payload's, so a probe
    contains no placeholders and no escaping. Raises on an error envelope: a
    probe that failed is a broken instrument rather than a failed check, and the
    two must not be able to look alike in a report.
    """
    program = "".join((
        "# --- probe: {} ---\n".format(label),
        "PARAMS = ", json.dumps(params, indent=4), "\n",
        "# --- payload: probe_{}.py ---\n".format(label),
        code))
    response = send_code(program, strict_json=True)
    if response.get("status") != "ok":
        raise RuntimeError("probe {} failed: {}".format(label, response.get("message")))
    return response.get("result")


def snapshot() -> dict:
    """The twelve collections by name, plus the dirty flag and the context."""
    return probe("snapshot", _SNAPSHOT_CODE, collections=[c[1] for c in DATABLOCK_COLLECTIONS])


_SNAPSHOT_CODE = '''
import bpy

names = dict()
for collection_name in PARAMS["collections"]:
    collection = getattr(bpy.data, collection_name, None)
    if collection is None:
        names[collection_name] = None
        continue
    names[collection_name] = sorted([datablock.name for datablock in collection])

result = dict(
    names=names,
    is_dirty=bool(bpy.data.is_dirty),
    active_object=None if bpy.context.active_object is None else bpy.context.active_object.name,
    mode=str(bpy.context.mode),
    scene=bpy.context.scene.name,
)
'''


def diff_snapshots(before: dict, after: dict) -> dict:
    """What appeared, what disappeared, and whether anything did.

    Reported per collection rather than as one boolean: "identical" is the claim
    the revert discipline makes, and a report that only says "not identical"
    leaves the next hour to finding out what leaked.
    """
    differences = dict()
    for key, _attribute in DATABLOCK_COLLECTIONS:
        old = set(before["names"].get(key) or [])
        new = set(after["names"].get(key) or [])
        added = sorted(new - old)
        removed = sorted(old - new)
        if added or removed:
            differences[key] = dict(added=added, removed=removed)
    return dict(
        identical=not differences,
        differences=differences,
        is_dirty_before=before["is_dirty"],
        is_dirty_after=after["is_dirty"],
        active_object_before=before["active_object"],
        active_object_after=after["active_object"],
    )


def ensure_scratch_scene() -> str:
    """Make (or re-select) the scratch scene, so nothing is built in the user's."""
    return probe("scene", _SCENE_CODE, scene=SCRATCH_SCENE)["scene"]


_SCENE_CODE = '''
import bpy

scene = bpy.data.scenes.get(PARAMS["scene"])
created = False
if scene is None:
    scene = bpy.data.scenes.new(PARAMS["scene"])
    created = True
for window in bpy.context.window_manager.windows:
    window.scene = scene

result = dict(scene=scene.name, created=created)
'''


def rename_object(old: str, new: str) -> str:
    """Give a character a name of its own.

    MPFB names every character ``Human`` and uniquifies the second one, so two
    of them would be told apart by a suffix that depends on what was already in
    the file.
    """
    return probe("rename", _RENAME_CODE, old=old, new=new)["name"]


_RENAME_CODE = '''
import bpy

obj = bpy.data.objects.get(PARAMS["old"])
if obj is None:
    raise RuntimeError("no object named " + PARAMS["old"])
obj.name = PARAMS["new"]
result = dict(name=obj.name)
'''


def cleanup_scratch_scene() -> dict:
    """Delete every object in the scratch scene, and the datablocks they held.

    Orphan meshes, armatures, materials, images and node groups are purged
    afterwards, because deleting an object leaves all five behind and the
    snapshot compare would report every one of them.
    """
    return probe("cleanup", _CLEANUP_CODE, scene=SCRATCH_SCENE)


_CLEANUP_CODE = '''
import bpy

removed = []
scene = bpy.data.scenes.get(PARAMS["scene"])
if scene is not None:
    for obj in list(scene.collection.all_objects):
        removed.append(obj.name)
        bpy.data.objects.remove(obj, do_unlink=True)

# An object removal leaves its data behind. Purge only what nothing uses, and
# only in these six collections: a zero-user brush or world is Blender's own
# business and predates this run.
purged = dict()
for collection_name in ["meshes", "armatures", "materials", "images", "node_groups", "actions"]:
    collection = getattr(bpy.data, collection_name)
    gone = []
    # Repeat until stable: a material's node group is only orphaned once the
    # material itself is gone.
    while True:
        orphans = [datablock for datablock in collection if datablock.users == 0]
        if not orphans:
            break
        for datablock in orphans:
            gone.append(datablock.name)
            collection.remove(datablock)
    purged[collection_name] = gone

# Rigify generation creates a WGTS_<rig> collection for its bone widgets, and
# deleting the widgets leaves the empty collection behind. An empty collection
# is a datablock like any other and the revert compare reports it, so anything
# that is now empty and childless goes too. Non-empty collections - the user's
# own - are never touched.
empty_collections = []
for collection in list(bpy.data.collections):
    if len(collection.objects) == 0 and len(collection.children) == 0:
        empty_collections.append(collection.name)
        bpy.data.collections.remove(collection)
purged["collections"] = empty_collections

result = dict(removed=removed, purged=purged)
'''


def results_directory() -> str:
    """Where the run writes its full result: the printed line is capped, the file
    is not. Defaulting it outside the repository is deliberately *not* done -
    unlike FR 012's per-call record, a run result is pass/fail lines about this
    package rather than diagnostics about the user's machine."""
    return os.environ.get("MPFB_MCP_VERIFICATION_RESULTS",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))


class Report:
    """The run: a pass/fail/skip line per item, with the observed value and a time.

    There are three outcomes and not two. ``skip`` is a first-class result
    carrying the reason the item could not be reached, and the summary names
    every skipped item rather than only counting it: twenty passes and four
    skips must not be presentable as twenty-four passes. The per-item duration
    is kept because the sixty-second target is watched rather than enforced, so
    it has to be visible on every run.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.results = []
        self._started = time.perf_counter()
        print("\n=== {} ===".format(name), flush=True)

    def check(self, item: str, passed: bool, observed: object = None,
              elapsed: float = 0.0) -> bool:
        self.results.append(dict(item=item, outcome="pass" if passed else "fail",
                                 observed=observed, elapsed=elapsed))
        print("[{}] {}{}{}".format(
            "x" if passed else " ", item, _elapsed_prefix(elapsed),
            _observed_suffix(observed)), flush=True)
        return passed

    def skip(self, item: str, reason: str, elapsed: float = 0.0) -> bool:
        self.results.append(dict(item=item, outcome="skip", observed=reason, elapsed=elapsed))
        print("[-] {} -- SKIPPED: {}".format(item, reason), flush=True)
        return False

    def note(self, text: str) -> None:
        """An observation that is not itself a check. Kept out of the counts."""
        print("    . {}".format(text), flush=True)

    def summary(self, target_seconds: float | None = None) -> dict:
        total = time.perf_counter() - self._started
        counts = dict(passed=0, failed=0, skipped=0)
        for result in self.results:
            counts["passed" if result["outcome"] == "pass" else
                   "failed" if result["outcome"] == "fail" else "skipped"] += 1
        counts["seconds"] = total
        counts["results"] = self.results

        print("\n--- {}: {} passed, {} failed, {} skipped, {:.1f}s".format(
            self.name, counts["passed"], counts["failed"], counts["skipped"], total), flush=True)
        for result in self.results:
            if result["outcome"] == "fail":
                print("    FAILED: {}".format(result["item"]), flush=True)
        for result in self.results:
            if result["outcome"] == "skip":
                print("    not exercised: {} -- {}".format(
                    result["item"], result["observed"]), flush=True)
        slowest = sorted(self.results, key=lambda r: -r["elapsed"])[:3]
        print("    slowest: {}".format(", ".join(
            "{} {:.1f}s".format(result["item"], result["elapsed"])
            for result in slowest if result["elapsed"])), flush=True)
        if target_seconds is not None and total > target_seconds:
            # Over target is a prompt to look, never a failure: the number being
            # measured is somebody else's Blender. The likeliest cause by a wide
            # margin is a configuration mistake rather than a regression.
            print("    over the {:.0f}s target. Check blender_mcp's "
                  "timer_interval_active first - 0.25s is its default and 0.05s is the "
                  "module's; every call here is four to five times slower at the "
                  "former. This does not fail the run.".format(target_seconds), flush=True)
        self._write(counts)
        return counts

    def _write(self, counts: dict) -> None:
        """Persist the full result. Best-effort: a report that cannot be written
        must not take the run down with it."""
        try:
            directory = results_directory()
            os.makedirs(directory, exist_ok=True)
            slug = "".join(character if character.isalnum() else "_"
                           for character in self.name.split(" - ")[0]).strip("_").lower()
            path = os.path.join(directory, "{}.json".format(slug))
            handle = open(path, "w", encoding="utf-8")
            json.dump(dict(name=self.name, counts=counts), handle, indent=1, default=repr)
            handle.close()
            print("    -> {}".format(path), flush=True)
        except OSError as error:  # noqa: BLE001 - the printed report is the product
            print("    (could not write result: {})".format(error), flush=True)


def _elapsed_prefix(elapsed: float) -> str:
    return "" if not elapsed else " ({:.1f}s)".format(elapsed)


def _observed_suffix(observed: object) -> str:
    if observed is None:
        return ""
    text = observed if isinstance(observed, str) else json.dumps(observed, default=repr)
    if len(text) > 600:
        text = text[:600] + " ..."
    return " -- " + text


def main_guard(function) -> int:
    """Run one script, reporting a broken instrument differently from a fail."""
    try:
        counts = function()
    except Exception as exception:  # noqa: BLE001 - the report is the product
        print("\n!!! harness error: {}: {}".format(type(exception).__name__, exception),
              file=sys.stderr, flush=True)
        raise
    return 1 if counts.get("failed") else 0
