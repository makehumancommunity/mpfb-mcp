"""
``shared/blender_data.py``, called directly.

Five reads of plain Blender data that four commands used to write for
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


def test_vertices_in_groups_counts_members_not_groups():
    import bpy  # pylint: disable=import-outside-toplevel
    mesh = bpy.data.meshes.new("BridgeTestDataVerticesMesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)], [], [(0, 1, 3, 2)])
    made = bpy.data.objects.new("BridgeTestDataVertices", mesh)
    bpy.context.scene.collection.objects.link(made)
    try:
        assert _module().vertices_in_groups(made, ("HelperGeometry",)) == 0
        helper = made.vertex_groups.new(name="HelperGeometry")
        joints = made.vertex_groups.new(name="JointCubes")
        # An empty group, which is what baking MPFB's mask leaves behind.
        assert _module().vertices_in_groups(made, ("HelperGeometry", "JointCubes")) == 0
        helper.add([0, 1], 1.0, "REPLACE")
        joints.add([1, 2], 0.1, "REPLACE")
        assert _module().vertices_in_groups(made, ("HelperGeometry", "JointCubes")) == 3
        assert _module().vertices_in_groups(made, ("JointCubes",)) == 2
        assert _module().vertices_in_groups(None, ("HelperGeometry",)) == 0
    finally:
        bpy.data.objects.remove(made, do_unlink=True)


def test_with_descendants_walks_every_depth_parents_first():
    import bpy  # pylint: disable=import-outside-toplevel
    root = linked_plain_object("BridgeTestDataRoot")
    child = linked_plain_object("BridgeTestDataChild")
    grandchild = linked_plain_object("BridgeTestDataGrandchild")
    stranger = linked_plain_object("BridgeTestDataStranger")
    child.parent = root
    grandchild.parent = child
    try:
        assert _module().with_descendants(root) == [root, child, grandchild]
        assert _module().with_descendants(grandchild) == [grandchild]
    finally:
        for made in (root, child, grandchild, stranger):
            bpy.data.objects.remove(made, do_unlink=True)
