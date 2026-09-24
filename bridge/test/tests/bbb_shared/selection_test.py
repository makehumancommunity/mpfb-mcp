"""
``shared/selection.py``, called directly.

Ten mutating commands put the caller's selection back through this one context
manager, so what it restores is asserted here once: the active object, and the
borrowed object's own selection - put back when the block raises as well as when
it finishes, and left selected when the caller had it selected. It needs
``bpy`` and no MPFB.

**And what it does not restore**, asserted so that the gap stays a decision
rather than a surprise: another object the block selected stays selected
(recorded in NEXT_STEPS.md).
"""

import pytest

from .. import bridge_module
from .._fixtures import linked_plain_object
from .._fixtures import nothing_active


def _restored(borrowed):
    return bridge_module("shared.selection").restored(borrowed)


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


def test_the_active_object_and_the_borrowed_selection_are_put_back(objects):
    import bpy  # pylint: disable=import-outside-toplevel
    caller_active, borrowed, _bystander = objects
    with _restored(borrowed):
        borrowed.select_set(True)
        bpy.context.view_layer.objects.active = borrowed
    assert bpy.context.view_layer.objects.active == caller_active
    assert not borrowed.select_get()


def test_they_are_put_back_when_the_block_raises(objects):
    import bpy  # pylint: disable=import-outside-toplevel
    caller_active, borrowed, _bystander = objects
    with pytest.raises(RuntimeError):
        with _restored(borrowed):
            borrowed.select_set(True)
            bpy.context.view_layer.objects.active = borrowed
            raise RuntimeError("the work failed")
    assert bpy.context.view_layer.objects.active == caller_active
    assert not borrowed.select_get()


def test_a_borrowed_object_the_caller_had_selected_stays_selected(objects):
    _caller_active, borrowed, _bystander = objects
    borrowed.select_set(True)
    with _restored(borrowed):
        pass
    assert borrowed.select_get()


def test_nothing_active_is_put_back_as_nothing_active(objects):
    import bpy  # pylint: disable=import-outside-toplevel
    _caller_active, borrowed, _bystander = objects
    bpy.context.view_layer.objects.active = None
    with _restored(borrowed):
        bpy.context.view_layer.objects.active = borrowed
    assert bpy.context.view_layer.objects.active is None


def test_another_object_the_block_selected_is_not_deselected(objects):
    """The recorded gap: only the borrowed object's own selection is restored."""
    _caller_active, borrowed, bystander = objects
    with _restored(borrowed):
        bystander.select_set(True)
    assert bystander.select_get()
