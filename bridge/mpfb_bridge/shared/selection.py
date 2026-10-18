"""
The caller's selection, put back after a command borrowed it.

**One implementation, used by every mutating command that activates something.**
See [`__init__.py`](__init__.py) for why this directory exists beside
``commands/``. A command that activates the basemesh to do its work - MPFB's own
slider callback does, ``refit()`` reaches ``bpy.ops`` through
``ClothesService``, and adding a rig or an asset calls operators - is working in
the scene the user is looking at. So it puts the previous active object and the
borrowed object's own selection state back, however the work ends
([mutating-tools.md](../../../specifications/mutating-tools.md#where-these-rules-are-enforced)).
Ten commands did that in a ``finally`` of their own until
[FR 036](../../../feature-requests/done/036-subject-resolver-and-duplication/README.md);
they now do it with :func:`restored`, which is also the one place to search for.

**It restores and does not activate.** What a command activates inside the
block differs - ``set_asset_material`` activates the asset rather than the
basemesh - so each command still does that itself, and passes in the object it
borrowed.

**What it restores is exactly what the ten copies did, and no more**: the active
object, and the borrowed object's own selection. An operator that selects
*other* objects - a new armature, an imported garment - leaves them selected.
That gap is recorded in NEXT_STEPS.md rather than closed here, since closing it
would change what a command leaves behind.

**:func:`restored_all` is the full snapshot, and two commands use it**
([FR 039](../../../feature-requests/done/039-exporting-characters/README.md)).
``export_character`` has to *select* a whole family, because Blender's exporters
write the selection, and ``create_export_copy`` drives MPFB's
``bake_modifiers_remove_helpers()``, which selects and deselects throughout. For
those, putting back one object's state would leave the user's scene visibly
rearranged, so every object's selection is recorded and put back, and anything
the block created is left deselected. The other ten commands keep
:func:`restored`, for the reason above; moving them is the NEXT_STEPS entry's.

Like ``performed`` and ``subject_resolution``'s subject step, it reads nothing
out of MPFB and takes no ``services``.
"""

__all__ = (
    "restored",
    "restored_all",
)

import contextlib

import bpy


@contextlib.contextmanager
def restored(borrowed):
    """Run the block, then put back the active object and ``borrowed``'s selection.

    Both are read when the block is entered. ``borrowed`` is deselected again
    only if it was not selected to begin with, so a caller who had it selected
    still has it selected.
    """
    previous_active = bpy.context.view_layer.objects.active
    was_selected = bool(borrowed.select_get())
    try:
        yield
    finally:
        if not was_selected:
            borrowed.select_set(False)
        bpy.context.view_layer.objects.active = previous_active


@contextlib.contextmanager
def restored_all():
    """Run the block, then put back the active object and **every** object's selection.

    Read when the block is entered, from the view layer. Afterwards every object
    in the view layer is deselected and the ones that were selected are selected
    again, so an object the block created - an export copy, a temporary
    duplicate - ends deselected, and the previously active object is active.

    An object the block deleted is skipped rather than failing the restore: the
    references raise ``ReferenceError`` once their object is gone. And an object
    that cannot be selected any more (moved out of the view layer) is skipped
    too, since Blender raises ``RuntimeError`` for that.
    """
    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previously_selected = [blender_object for blender_object in view_layer.objects
                           if blender_object.select_get()]
    try:
        yield
    finally:
        view_layer = bpy.context.view_layer
        for blender_object in view_layer.objects:
            try:
                blender_object.select_set(False)
            except RuntimeError:
                pass
        for blender_object in previously_selected:
            try:
                blender_object.select_set(True)
            except (ReferenceError, RuntimeError):
                pass
        try:
            view_layer.objects.active = previous_active
        except (ReferenceError, RuntimeError):
            view_layer.objects.active = None
