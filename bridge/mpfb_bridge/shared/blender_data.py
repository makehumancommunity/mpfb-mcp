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

Like ``performed`` and ``selection``, it reads nothing out of MPFB and takes no
``services``. The shape-key reads are not here: they live in
[`target_rollup.py`](target_rollup.py), beside the rule for where a target is
stored among them.
"""

__all__ = (
    "material_names",
    "object_names",
    "vertex_group_names",
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
