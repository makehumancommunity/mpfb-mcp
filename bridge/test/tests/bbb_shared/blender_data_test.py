"""
``shared/blender_data.py``, called directly.

Three reads of plain Blender data that four commands used to write for
themselves. They need ``bpy`` and no MPFB: each is checked on an object the test
makes, on ``None``, and on an object that has none of what is being read.
"""

from .. import bridge_module
from .._fixtures import linked_plain_object


def _module():
    return bridge_module("shared.blender_data")


def test_object_names_sees_an_object_created_since():
    import bpy  # pylint: disable=import-outside-toplevel
    before = _module().object_names()
    made = linked_plain_object("BridgeTestDataObject")
    try:
        assert _module().object_names() - before == {"BridgeTestDataObject"}
    finally:
        bpy.data.objects.remove(made, do_unlink=True)


def test_vertex_group_names_in_order():
    import bpy  # pylint: disable=import-outside-toplevel
    made = linked_plain_object("BridgeTestDataGroups")
    try:
        assert _module().vertex_group_names(made) == []
        made.vertex_groups.new(name="first")
        made.vertex_groups.new(name="second")
        assert _module().vertex_group_names(made) == ["first", "second"]
        assert _module().vertex_group_names(None) == []
    finally:
        bpy.data.objects.remove(made, do_unlink=True)


def test_material_names_skip_an_empty_slot():
    import bpy  # pylint: disable=import-outside-toplevel
    made = linked_plain_object("BridgeTestDataMaterials")
    material = bpy.data.materials.new("BridgeTestDataMaterial")
    try:
        assert _module().material_names(made) == []
        made.data.materials.append(material)
        made.data.materials.append(None)
        assert _module().material_names(made) == ["BridgeTestDataMaterial"]
        assert _module().material_names(None) == []
    finally:
        bpy.data.objects.remove(made, do_unlink=True)
        bpy.data.materials.remove(material)
