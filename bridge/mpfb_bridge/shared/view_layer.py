"""
A character the view layer excludes, included for one call and excluded again.

One collection per character, all but one excluded, is the easy way to manage several characters at
the origin, and ``bpy.ops``, ``select_set`` and setting the active object all raise on an object
outside the view layer. So a refit, ``add_asset`` and ``set_skin`` failed on such a character, the last
after deleting its materials. A refusal would leave a caller with no MPFB tool to continue, so
[FR 054](../../../feature-requests/done/054-refits-keep-the-pose/README.md) includes the collection
instead and says so. The view layer is the user's setting, and the ``finally`` is the whole reason that
is acceptable.

**Which commands call :func:`run` was measured**, by scanning every mutating command against an excluded
character, and ``eee_composite/excluded_character_test.py`` holds the table. Those that raised, refused
for no reason of the caller's, or answered from a pose Blender had not evaluated are wrapped. A command
that works, or that refuses in terms a caller can act on, is not: "Commands that work today are not
wrapped" is the request's rule, and ``generate_delete_group``, ``write_mesh_asset`` and the two ``check_*``
commands already say what stopped them.

**Only what is needed, and exactly that put back.** The excluded layer collections holding the family,
with their excluded parents, top down. Blender's ``exclude`` is recursive and remembers: including a
parent includes any child that was not excluded on its own, which is more than was needed, so such a
child is excluded again for the duration; and a child is told it was "previously excluded" only when a
parent is excluded around it. So everything done here is a stack, undone in reverse, which leaves those
remembered flags as they were: a parent included later by the user brings back what it brought back
before. A path of names is held rather than a ``LayerCollection``, because Rigify makes a collection
during a refit, and the tree may have been rebuilt by the time the undo runs.

**``hide_set()`` is lost by the exclude itself**, and not by anything here: Blender keeps it on the
object's base in the view layer, and an excluded object has none. FR 054's scan measured it, setting it
and excluding and including with no tool involved, and it reads false at the end every time. So what an
excluded object was hidden as cannot be put back, and what is put back is the state of each family
object that was in the view layer when the work began.

**What a command creates during an inclusion joins the character.** Otherwise a garment stands visible at
the origin beside a character the user excluded, because ``bpy.ops`` puts it in the active collection.
Only objects in the character's family are moved, which leaves Rigify's widgets in their own collection.
An object in two collections has no single answer, so the first one included is used, and
``objects_moved_to_collection`` names it. A call with no inclusion moves nothing.

**A hidden collection is not an excluded one.** Its objects are in the view layer, and FR 054's non-goals
leave it alone unless it stops the work, which was measured. ``add_asset``, ``set_skin`` and a refit of a
default rig or an ungenerated meta-rig all work there. What does not is Rigify itself, which refuses to
regenerate a target it cannot see and to generate from a meta-rig it cannot see, so those two are refused
rather than raising: ``refits`` says the command will refit, and ``generates`` that it will generate.

It reads nothing out of MPFB but the family, which needs the back-pointer from a generated rig to its
meta-rig: the meta-rig is what a refit edits, and no parent chain reaches it.
"""

__all__ = (
    "BLOCKED_BY",
    "family_of",
    "included",
    "run",
)

import contextlib

import bpy

from ..log import get_logger
from . import blender_data
from . import selection
from . import subject_resolution
from .performed import with_performed

_LOG = get_logger("shared.viewlayer")

BLOCKED_BY = "not_in_view_layer"


class _Inclusion:
    """What one inclusion did: the two lists an answer carries."""

    def __init__(self):
        self.names = []
        self.moved = []


def family_of(services, anchor):
    """Every object a command on this character can reach: the tree it is in, and the meta-rigs."""
    object_service = services["ObjectService"]
    root = anchor
    while root.parent is not None:
        root = root.parent
    family = blender_data.with_descendants(root)
    for blender_object in list(family):
        if blender_object.type != "ARMATURE":
            continue
        metarig = object_service.find_rigify_metarig_by_rig(blender_object)
        if metarig is not None and metarig not in family:
            family.append(metarig)
    return family


def _walk(layer_collection, path=()):
    """Each layer collection below this one with its path of names, parents first."""
    for child in layer_collection.children:
        child_path = path + (child.name,)
        yield (child_path, child)
        yield from _walk(child, child_path)


def _at(view_layer, path):
    """The layer collection at a path of names, or ``None`` if it is gone."""
    found = view_layer.layer_collection
    for name in path:
        found = found.children.get(name)
        if found is None:
            return None
    return found


def _paths_of(view_layer, blender_object):
    """Every path by which this object's collections reach this view layer."""
    names = set(collection.name for collection in blender_object.users_collection)
    if view_layer.layer_collection.collection.name in names:
        return [()]
    return [path for path, _child in _walk(view_layer.layer_collection) if path[-1] in names]


def _excluded_on(view_layer, path):
    """The excluded layer collections along one path, top down, as paths."""
    return [path[:depth] for depth in range(1, len(path) + 1)
            if _at(view_layer, path[:depth]).exclude]


def _cannot_be_included(view_layer, family):
    return [blender_object for blender_object in family
            if blender_object.name not in view_layer.objects
            and not _paths_of(view_layer, blender_object)]


def _needed(view_layer, family):
    """The excluded paths to include, top down: for each object outside, its first way in."""
    needed = []
    for blender_object in family:
        if blender_object.name in view_layer.objects:
            continue
        paths = _paths_of(view_layer, blender_object)
        already = [path for path in paths
                   if all(step in needed for step in _excluded_on(view_layer, path))]
        for step in _excluded_on(view_layer, (already or paths)[0]):
            if step not in needed:
                needed.append(step)
    return sorted(needed, key=len)


def _set_exclude(view_layer, path, value, undo):
    layer_collection = _at(view_layer, path)
    if layer_collection.exclude != value:
        layer_collection.exclude = value
        undo.append((path, not value))


def _include(view_layer, needed, excluded_before, undo):
    """Include the needed paths, and exclude again any child that came along with a parent."""
    for path in needed:
        _set_exclude(view_layer, path, False, undo)
        for child_path, child in list(_walk(_at(view_layer, path), path)):
            if child_path not in needed and child_path in excluded_before and not child.exclude:
                _set_exclude(view_layer, child_path, True, undo)
    view_layer.update()


def _undone(view_layer, undo):
    """Undo in reverse, then let the view layer catch up. A collection that is gone is skipped."""
    for path, value in reversed(undo):
        layer_collection = _at(view_layer, path)
        if layer_collection is not None:
            layer_collection.exclude = value
    view_layer.update()


def _move_created(view_layer, anchor, created, needed, inclusion):
    """Link what was created to the anchor's collection, first the one included, and off the rest."""
    collections = list(anchor.users_collection)
    if not collections:
        return
    included_names = set(path[-1] for path in needed)
    target = next((collection for collection in collections if collection.name in included_names),
                  collections[0])
    for blender_object in created:
        if target in blender_object.users_collection:
            continue
        target.objects.link(blender_object)
        for collection in list(blender_object.users_collection):
            if collection != target:
                collection.objects.unlink(blender_object)
        inclusion.moved.append({"object": blender_object.name, "collection": target.name})
    view_layer.update()


def _path_of_active(view_layer):
    """The active layer collection's path, which is empty for the scene's own collection."""
    active = view_layer.active_layer_collection
    return next((path for path, child in _walk(view_layer.layer_collection) if child == active), ())


def _put_active_collection_back(view_layer, path):
    active = _at(view_layer, path)
    if active is not None and not active.exclude:
        view_layer.active_layer_collection = active


@contextlib.contextmanager
def included(anchor, family):
    """Run the block with these objects in the view layer, and put the view layer back.

    ``family`` is a function, called on the way in and on the way out, because what the block created
    is part of the family only afterwards. Yields the record of what was done: ``names`` holds the
    collections included, and is empty when nothing needed to be; ``moved`` what was linked elsewhere.
    The caller refuses what :func:`_cannot_be_included` finds, before this.
    """
    view_layer = bpy.context.view_layer
    # exclude only takes effect in view_layer.objects after a sync, and a user's script may have just
    # set it.
    view_layer.update()
    inclusion = _Inclusion()
    needed = _needed(view_layer, family())
    if not needed:
        yield inclusion
        return

    excluded_before = set(path for path, child in _walk(view_layer.layer_collection)
                          if child.exclude)
    active_path = _path_of_active(view_layer)
    objects_before = set(bpy.data.objects)
    undo = []
    try:
        _include(view_layer, needed, excluded_before, undo)
        inclusion.names = [path[-1] for path in needed]
        _LOG.debug("included %r for the call", inclusion.names)
        yield inclusion
    finally:
        try:
            created = [blender_object for blender_object in family()
                       if blender_object not in objects_before]
            _move_created(view_layer, anchor, created, needed, inclusion)
        finally:
            _undone(view_layer, undo)
            _put_active_collection_back(view_layer, active_path)


def _hidden_collection_of(view_layer, blender_object):
    """The hidden collection every way to this object goes through, or ``None``."""
    hidden = None
    for path in _paths_of(view_layer, blender_object):
        found = None
        for depth in range(1, len(path) + 1):
            layer_collection = _at(view_layer, path[:depth])
            if layer_collection.hide_viewport or layer_collection.collection.hide_viewport:
                found = layer_collection.name
                break
        if found is None:
            return None
        hidden = found
    return hidden


def _stops_rigify(object_service, blender_object, refits, generates):
    """Whether Rigify would have to run on this object, and so has to be able to see it."""
    if blender_object.type != "ARMATURE":
        return False
    if generates:
        return True
    return refits and object_service.find_rigify_metarig_by_rig(blender_object) is not None


def _stuck_objects(services, view_layer, family, refits, generates):
    """Each object that stops this call, with where it is and why."""
    stuck = [dict(object=blender_object.name,
                  collections=[collection.name for collection in blender_object.users_collection],
                  reason="outside_this_view_layer")
             for blender_object in _cannot_be_included(view_layer, family)]
    if stuck:
        return stuck
    for blender_object in family:
        if not _stops_rigify(services["ObjectService"], blender_object, refits, generates):
            continue
        hidden = _hidden_collection_of(view_layer, blender_object)
        if hidden is not None:
            stuck.append(dict(object=blender_object.name, collections=[hidden],
                              reason="in_a_hidden_collection"))
    return stuck


def _stuck_sentence(stuck):
    entry = stuck[0]
    if entry["reason"] == "in_a_hidden_collection":
        where = ("is in the collection '{:s}', which is hidden in the viewport, and Rigify refuses a "
                 "rig it cannot see".format(entry["collections"][0]))
    elif entry["collections"]:
        where = ("is in {:s}, which this view layer does not hold: it belongs to another "
                 "scene".format(", ".join("'{:s}'".format(name) for name in entry["collections"])))
    else:
        where = "is in no collection at all"
    return "'{:s}' {:s}, so nothing was changed.".format(entry["object"], where)


def _refused(subject, resolved_by, basemesh, stuck, refused_with):
    answer = dict(
        found=basemesh is not None,
        ready=False,
        blocked_by=BLOCKED_BY,
        subject_name=subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        not_in_view_layer=stuck,
        temporarily_included=[],
        objects_moved_to_collection=[],
        message=_stuck_sentence(stuck),
    )
    answer.update(refused_with or {})
    return with_performed(answer, False)


def _inclusion_sentence(inclusion):
    if not inclusion.names:
        return ""
    sentence = " The collection(s) {:s} were excluded from the view layer, so they were included " \
               "for this call and excluded again.".format(
                   ", ".join("'{:s}'".format(name) for name in inclusion.names))
    for entry in inclusion.moved:
        sentence += " '{:s}' was put in '{:s}' with the character.".format(
            entry["object"], entry["collection"])
    return sentence


@contextlib.contextmanager
def _hide_state_restored(view_layer, family):
    hidden = [(blender_object, blender_object.hide_get()) for blender_object in family
              if blender_object.name in view_layer.objects]
    try:
        yield
    finally:
        for blender_object, was_hidden in hidden:
            try:
                if blender_object.hide_get() != was_hidden:
                    blender_object.hide_set(was_hidden)
            except (ReferenceError, RuntimeError):
                pass


def run(services, requested_name, work, *, refits=False, generates=False, refused_with=None):
    """Run a command's ``work`` with its character in the view layer, and report on having done so.

    ``work`` answers as the command always did, its own refusals included: a subject that resolves to
    nothing goes straight to it, since saying so is its job. This adds ``temporarily_included`` and
    ``objects_moved_to_collection`` to the answer, ``[]`` on an ordinary call, and a sentence to its
    message when they are not; and refuses what cannot be included, before anything is written.

    ``generates`` is for the one command whose result is what it selects and hides. Its selection is put
    back only around an inclusion, because what it selected is about to leave the view layer, and the
    hide state not at all. ``refits`` says the command will refit, and ``refused_with`` is what its
    refusals otherwise carry, such as ``refit_performed``.
    """
    subject, resolved_by, _message = subject_resolution.resolve_subject(requested_name)
    if subject is None:
        return _with_keys(work(), _Inclusion())
    basemesh = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        subject, "Basemesh")
    anchor = subject if basemesh is None else basemesh
    view_layer = bpy.context.view_layer
    view_layer.update()
    stuck = _stuck_objects(services, view_layer, family_of(services, anchor), refits, generates)
    if stuck:
        return _refused(subject, resolved_by, basemesh, stuck, refused_with)

    with included(anchor, lambda: family_of(services, anchor)) as inclusion:
        family = family_of(services, anchor)
        if generates:
            guard = selection.restored_all() if inclusion.names else contextlib.nullcontext()
        else:
            guard = _hide_state_restored(view_layer, family)
        with guard:
            answer = work()
    return _with_keys(answer, inclusion)


def _with_keys(answer, inclusion):
    answer["temporarily_included"] = list(inclusion.names)
    answer["objects_moved_to_collection"] = list(inclusion.moved)
    answer["message"] = answer["message"] + _inclusion_sentence(inclusion)
    return answer
