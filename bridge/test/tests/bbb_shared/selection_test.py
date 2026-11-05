"""
``shared/selection.py``, called directly.

Every mutating command that activates something puts the caller's selection back through
``restored_all``, so what it restores is asserted here once: the active object and every object's
selection, put back when the block raises as well as when it finishes. What the block created is left
deselected and what it deleted is skipped. It needs ``bpy`` and no MPFB.
"""

import pytest

from .. import bridge_module
from .._fixtures import linked_plain_object
from .._fixtures import nothing_active


@pytest.fixture(name="objects")
def _objects():
    import bpy  # pylint: disable=import-outside-toplevel
    made = [linked_plain_object(name) for name in
            ("BridgeTestCallerActive", "BridgeTestBorrowed", "BridgeTestBystander")]
    for blender_object in made:
        blender_object.select_set(False)
    with nothing_active():
        bpy.context.view_layer.objects.active = made[0]
        yield made
    for blender_object in made:
        bpy.data.objects.remove(blender_object, do_unlink=True)


def _restored_all():
    return bridge_module("shared.selection").restored_all()


def test_restored_all_puts_every_objects_selection_back(objects):
    import bpy  # pylint: disable=import-outside-toplevel
    caller_active, borrowed, bystander = objects
    bystander.select_set(True)
    with _restored_all():
        for blender_object in bpy.context.view_layer.objects:
            blender_object.select_set(False)
        borrowed.select_set(True)
        bpy.context.view_layer.objects.active = borrowed
    assert bpy.context.view_layer.objects.active == caller_active
    assert bystander.select_get() and not borrowed.select_get()


def test_restored_all_leaves_what_the_block_created_deselected(objects):
    import bpy  # pylint: disable=import-outside-toplevel
    with _restored_all():
        created = linked_plain_object("BridgeTestCreatedInBlock")
        created.select_set(True)
        bpy.context.view_layer.objects.active = created
    try:
        assert not created.select_get()
        assert bpy.context.view_layer.objects.active == objects[0]
    finally:
        bpy.data.objects.remove(created, do_unlink=True)


def test_restored_all_skips_what_the_block_deleted(objects):
    import bpy  # pylint: disable=import-outside-toplevel
    doomed = linked_plain_object("BridgeTestDeletedInBlock")
    doomed.select_set(True)
    bpy.context.view_layer.objects.active = doomed
    with pytest.raises(RuntimeError):
        with _restored_all():
            bpy.data.objects.remove(doomed, do_unlink=True)
            raise RuntimeError("the work failed")
    assert bpy.context.view_layer.objects.active is None
    assert not any(o.select_get() for o in objects)


def test_restored_all_puts_them_back_when_the_block_raises(objects):
    import bpy  # pylint: disable=import-outside-toplevel
    caller_active, borrowed, bystander = objects
    bystander.select_set(True)
    with pytest.raises(RuntimeError):
        with _restored_all():
            bystander.select_set(False)
            borrowed.select_set(True)
            bpy.context.view_layer.objects.active = borrowed
            raise RuntimeError("the work failed")
    assert bpy.context.view_layer.objects.active == caller_active
    assert bystander.select_get() and not borrowed.select_get()


def test_nothing_active_is_put_back_as_nothing_active(objects):
    import bpy  # pylint: disable=import-outside-toplevel
    _caller_active, borrowed, _bystander = objects
    bpy.context.view_layer.objects.active = None
    with _restored_all():
        bpy.context.view_layer.objects.active = borrowed
    assert bpy.context.view_layer.objects.active is None
