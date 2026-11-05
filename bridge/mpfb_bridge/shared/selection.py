"""
The caller's selection, put back after a command borrowed it.

**One implementation, used by every mutating command that activates something.**
See [`__init__.py`](__init__.py) for why this directory exists beside
``commands/``. A command that activates the basemesh to do its work - MPFB's own
slider callback does, ``refit()`` reaches ``bpy.ops`` through
``ClothesService``, and adding a rig or an asset calls operators - is working in
the scene the user is looking at. So it puts every object's selection and the
active object back, however the work ends
([mutating-tools.md](../../../specifications/mutating-tools.md#where-these-rules-are-enforced)).

**It restores and does not activate.** What a command activates inside the
block differs - ``set_asset_material`` activates the asset rather than the
basemesh - so each command still does that itself.

**Why every object, and not only the one borrowed.** Ten commands put back the
active object and the borrowed object's own selection, through a ``restored()``
that [FR 036](../../../feature-requests/done/036-subject-resolver-and-duplication/README.md)
made of ten ``finally`` blocks. An operator that selects *other* objects - a new
armature, an imported garment - left them selected, and FR 054's scoping saw a
selected bystander end up deselected.
[FR 039](../../../feature-requests/done/039-exporting-characters/README.md) wrote
:func:`restored_all` for the export commands, and FR 054 moved the ten onto it, which
was all of them, so ``restored()`` is gone. Anything the block created is left
deselected.

Like ``performed`` and ``subject_resolution``'s subject step, it reads nothing
out of MPFB and takes no ``services``.
"""

__all__ = (
    "restored_all",
)

import contextlib

import bpy


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
