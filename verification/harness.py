# SPDX-License-Identifier: GPL-3.0-or-later

"""
The instrument the live verification session runs on.

Everything here exists because FR 006's run was thrown away. That session built
a scratch basemesh, loaded four targets, snapshotted twelve datablock
collections and compared them afterwards - all by hand, and none of it
re-runnable. Five requests then landed unverified, each postponement justified
by the same cost. This module is the part of that cost that can be removed:
the scratch scene, the snapshot/compare, the tool callables and the pass/fail
reporting, so that re-running a whole checklist after a code fix is one command.

Three things about it are decisions rather than details.

**Checks run through the real tool callables.** ``tools()`` registers every tool
module on a ``FastMCP`` instance and hands back the underlying sync functions,
the way ``tests/`` reaches them. A check written as a hand-assembled
``send_code()`` call would verify a program no MCP client will ever send: the
tool module's own validation, defaulting and coercion is a large part of what
is under test here, and FR 011's ``skin_type`` vocabulary check lives *only*
there.

**The scratch scene, not a scratch file.** The session runs against whatever
Blender the user has prepared, and that Blender holds their work. Reloading a
home file to get a clean baseline would discard it. So the harness makes its own
scene, builds in that, and deletes what it made; the snapshot/compare is what
turns "deleted what it made" from a claim into an assertion. The ``.blend`` is
never saved, by anything here.

**Probes are sent with a payload marker.** ``probe()`` is the harness's own
channel into Blender - for snapshots, for reading back what MPFB's UI thinks,
and for the observations no tool exposes. It goes through the same
``send_code()`` every tool uses, so FR 012's record covers it too; the marker is
written so those records are named after the probe rather than all landing under
``unnamed``.

Nothing here is unit-tested and nothing here may be imported by ``src/``. Its
own correctness is established the way the request asks: by pointing a checklist
at a deliberately broken call and watching it fail.
"""

from __future__ import annotations

__all__ = (
    "DATABLOCK_COLLECTIONS",
    "Report",
    "SCRATCH_SCENE",
    "cleanup_scratch_scene",
    "diff_snapshots",
    "ensure_scratch_scene",
    "context_is_clean",
    "probe",
    "results_directory",
    "snapshot",
    "tools",
)

import json
import os
import sys
import time

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module

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


def tools() -> dict:
    """Every MCP tool, by name, as the plain callable behind the coroutine.

    This is the same route ``tests/`` takes into a tool. Registering all twenty
    on one server rather than one per check also means a checklist pays the
    registration cost once.
    """
    mcp = FastMCP("mpfb-mcp-verification")
    from mpfbmcp.tools import (  # pylint: disable=import-outside-toplevel
        add_asset, add_rig, create_human, generate_rigify_rig, get_macro_details,
        get_object_info, get_status, get_target_stack, list_asset_materials, list_assets,
        list_objects, list_rigs, list_targets, refit_human, remove_asset, set_asset_material,
        set_macro_details, set_skin, set_targets, symmetrize_targets)
    for module in (
            add_asset, add_rig, create_human, generate_rigify_rig, get_macro_details,
            get_object_info, get_status, get_target_stack, list_asset_materials, list_assets,
            list_objects, list_rigs, list_targets, refit_human, remove_asset, set_asset_material,
            set_macro_details, set_skin, set_targets, symmetrize_targets):
        module.register(mcp)
    return {name: tool.fn for name, tool in mcp._tool_manager._tools.items()}  # noqa: SLF001


def probe(label: str, code: str, **params: object) -> dict:
    """Run harness-owned code inside Blender and return its ``result``.

    The first argument is called ``label`` rather than ``name`` so that a probe
    can take a ``name=`` parameter of its own - almost every one of them names
    an object, and a collision there would be a footgun in every check script.

    ``params`` is bound as ``PARAMS`` from a JSON literal, the same way
    ``codegen``'s prelude binds a payload's parameters - so a probe contains no
    placeholders and no escaping either. Raises on an error envelope, because a
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

    Reported per collection rather than as one boolean: "identical" is the
    claim the revert discipline makes, and a report that only says "not
    identical" leaves the next hour to finding out what leaked.
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


def cleanup_scratch_scene(keep: list | None = None) -> dict:
    """Delete every object in the scratch scene, and the datablocks they held.

    Orphan meshes, armatures, materials, images and node groups are purged
    afterwards, because deleting an object leaves all five behind and the
    snapshot compare would report every one of them. ``keep`` names objects to
    leave alone, for a checklist that wants the character to survive into the
    next one.
    """
    return probe("cleanup", _CLEANUP_CODE, scene=SCRATCH_SCENE, keep=list(keep or []))


_CLEANUP_CODE = '''
import bpy

removed = []
scene = bpy.data.scenes.get(PARAMS["scene"])
if scene is not None:
    keep = set(PARAMS["keep"])
    for obj in list(scene.collection.all_objects):
        if obj.name in keep:
            continue
        removed.append(obj.name)
        bpy.data.objects.remove(obj, do_unlink=True)

# An object removal leaves its data behind. Purge only what nothing uses, and
# only in these five collections: a zero-user brush or world is Blender's own
# business and predates this session.
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


def context_is_clean() -> dict:
    """OBJECT mode and a scratch-scene context, checked before a checklist item.

    Both FR 009 and FR 010 learned from source that ``bpy.ops`` polls on
    ``bpy.context.mode`` and not on the subject's - so an unrelated object left
    in edit mode fails an operator on a character that looks perfectly fine.
    Asserting it here is what keeps such a failure from being read as the
    tool's.
    """
    return probe("context", _CONTEXT_CODE)


_CONTEXT_CODE = '''
import bpy

result = dict(
    mode=str(bpy.context.mode),
    clean=str(bpy.context.mode) == "OBJECT",
    scene=bpy.context.scene.name,
    active_object=None if bpy.context.active_object is None else bpy.context.active_object.name,
    selected=sorted([o.name for o in bpy.context.selected_objects]),
)
'''


def results_directory() -> str:
    """Where a checklist writes its full result, for the record that follows it.

    The printed line is capped so a terminal stays readable; the record FR-4
    asks for wants the observed value in full. Overridable, and defaulted
    outside the repository is deliberately *not* done here - unlike FR 012's
    per-call record, a checklist result is a list of pass/fail lines about this
    package, not diagnostic output about the user's machine.
    """
    return os.environ.get("MPFB_MCP_VERIFICATION_RESULTS",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))


class Report:
    """One checklist: a pass/fail/skip line per item, with the observed value.

    FR-4 wants each source request's record rewritten with the observed value
    beside each item, and FR 013's non-functional requirements put truthfulness
    above completeness. So there are three outcomes and not two: ``skip`` is a
    first-class result carrying the reason it could not be reached, and an item
    nobody called is reported as missing at the end rather than silently absent.
    """

    def __init__(self, name: str, expected_items: tuple = ()) -> None:
        self.name = name
        self.expected_items = tuple(expected_items)
        self.results = []
        self._started = time.perf_counter()
        print("\n=== {} ===".format(name), flush=True)

    def check(self, item: str, passed: bool, observed: object = None) -> bool:
        self.results.append(dict(item=item, outcome="pass" if passed else "fail",
                                 observed=observed))
        print("[{}] {}{}".format(
            "x" if passed else " ", item, _observed_suffix(observed)), flush=True)
        return passed

    def equal(self, item: str, actual: object, expected: object) -> bool:
        """A check whose observed value is worth reporting even when it passes."""
        return self.check(item, actual == expected,
                          actual if actual == expected else
                          "expected {!r}, got {!r}".format(expected, actual))

    def skip(self, item: str, reason: str) -> bool:
        self.results.append(dict(item=item, outcome="skip", observed=reason))
        print("[-] {} -- SKIPPED: {}".format(item, reason), flush=True)
        return False

    def note(self, text: str) -> None:
        """An observation that is not itself a check. Kept out of the counts."""
        print("    . {}".format(text), flush=True)

    def summary(self) -> dict:
        counts = dict(passed=0, failed=0, skipped=0)
        for result in self.results:
            counts["passed" if result["outcome"] == "pass" else
                   "failed" if result["outcome"] == "fail" else "skipped"] += 1
        reached = set(result["item"] for result in self.results)
        never_run = [item for item in self.expected_items if item not in reached]
        print("--- {}: {} passed, {} failed, {} skipped, {} never run, {:.1f}s".format(
            self.name, counts["passed"], counts["failed"], counts["skipped"],
            len(never_run), time.perf_counter() - self._started), flush=True)
        for item in never_run:
            print("[ ] {} -- NEVER RUN".format(item), flush=True)
        counts["never_run"] = never_run
        counts["results"] = self.results
        self._write(counts)
        return counts

    def _write(self, counts: dict) -> None:
        """Persist the full result. Best-effort, for FR 012's reason: a report
        that cannot be written must not take the checklist down with it."""
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


def _observed_suffix(observed: object) -> str:
    if observed is None:
        return ""
    text = observed if isinstance(observed, str) else json.dumps(observed, default=repr)
    if len(text) > 600:
        text = text[:600] + " ..."
    return " -- " + text


def main_guard(function) -> int:
    """Run one checklist, reporting a broken instrument differently from a fail."""
    try:
        counts = function()
    except Exception as exception:  # noqa: BLE001 - the report is the product
        print("\n!!! harness error: {}: {}".format(type(exception).__name__, exception),
              file=sys.stderr, flush=True)
        raise
    return 1 if counts.get("failed") else 0
