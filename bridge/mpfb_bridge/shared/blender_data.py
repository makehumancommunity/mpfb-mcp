"""
Plain Blender data, read without MPFB.

**Shared because each is one concept written several times**, which is the
second of the rules in
[architecture.md](../../../specifications/architecture.md#shared-modules-and-what-warrants-one):
not because two copies drifting apart would mislead a caller, but because an
import costs nothing now and a name is easier to read than a comprehension
repeated in four commands
([FR 036](../../../feature-requests/done/036-subject-resolver-and-duplication/README.md)).

- :func:`object_names` is every object in the file, which is how a command
  finds what an operation created: take it before, take it after, subtract.
  ``bpy.data`` rather than the scene, because an object created into another
  collection would otherwise look like nothing happened.
- :func:`vertex_group_names` and :func:`material_names` read one object's
  groups and slots, both tolerating ``None`` and an object that has neither.
- :func:`with_descendants` is an object and everything parented below it,
  parents first: the family both export commands walk from the root, which they
  must agree about - what ``create_export_copy`` copies is what
  ``export_character`` writes. Recursive, because a garment with a sub-rig is the
  sub-rig's child, and MPFB's ``ObjectService.get_list_of_children()`` returns
  direct children only.
- :func:`vertices_in_groups` counts the vertices that belong to named groups,
  which is how both export commands
  ([FR 039](../../../feature-requests/done/039-exporting-characters/README.md))
  say whether a basemesh still carries its helper geometry. Not by the groups'
  presence: baking MPFB's ``Hide helpers`` mask deletes the vertices and leaves
  the groups behind, empty, and a copy reported as still having helpers when it
  has none would send a caller to remove what is not there.

Like ``performed`` and ``selection``, it reads nothing out of MPFB and takes no
``services``. The shape-key reads are not here: they live in
[`target_rollup.py`](target_rollup.py), beside the rule for where a target is
stored among them.
"""

__all__ = (
    "material_names",
    "object_names",
    "vertex_group_names",
    "vertices_in_groups",
    "with_descendants",
)

import bpy


def object_names():
    """Every object in the file right now, as a set of names."""
    return set(str(blender_object.name) for blender_object in bpy.data.objects)


def vertex_group_names(blender_object):
    """The vertex group names on one object, in order, or ``[]``."""
    if blender_object is None:
        return []
    return [str(group.name) for group in (getattr(blender_object, "vertex_groups", None) or [])]


def material_names(blender_object):
    """The names of the materials in one object's slots, in order, or ``[]``.

    An empty slot is skipped rather than reported as ``None``.
    """
    names = []
    if blender_object is None:
        return names
    for slot in getattr(blender_object, "material_slots", None) or []:
        material = getattr(slot, "material", None)
        if material is not None:
            names.append(str(material.name))
    return names


def vertices_in_groups(blender_object, group_names):
    """How many of one mesh's vertices belong to any of ``group_names``, or 0.

    Membership at any weight, as ``ExportService._delete_vertex_group()``
    selects the vertices it deletes.
    """
    if blender_object is None or blender_object.type != "MESH":
        return 0
    indices = set(group.index for group in blender_object.vertex_groups
                  if group.name in group_names)
    if not indices:
        return 0
    return sum(1 for vertex in blender_object.data.vertices
               if any(element.group in indices for element in vertex.groups))


def with_descendants(root):
    """``root`` and every object parented below it at any depth, parents before children.

    Over ``bpy.data.objects``, as MPFB's own child walk is, so a descendant
    outside the current scene is still found.
    """
    family = [root]
    index = 0
    while index < len(family):
        parent = family[index]
        family.extend(blender_object for blender_object in bpy.data.objects
                      if blender_object.parent == parent)
        index += 1
    return family
