"""
What a bone table may look like, checked without Blender.

The shape half of [`rig_definition.py`](rig_definition.py), apart because it imports nothing
but the standard library: ``tests/test_create_rig.py`` executes this file's source directly and
runs it and ``mpfbmcp.tools.create_rig``'s checks over one table of cases, as
``tests/test_save_preset.py`` does for ``artifact_names.py``. The tool refuses before sending;
this is the copy the socket needs, since anything on this machine can reach it. **No joint,
vertex count or bone vocabulary is checked here**: that is the body's, and
``rig_definition.resolve_table()`` answers it.
"""

__all__ = (
    "AXES",
    "BONE_KEYS",
    "DEFAULT_COLLECTION",
    "END_KEYS",
    "END_KINDS",
    "READ_ONLY_BONE_KEYS",
    "ROLL_ALIGNMENTS",
    "end_kind",
    "table_shape_errors",
)

import math

# The character frame's axes, as shared/character_frame.py names them.
AXES = ("forward", "left", "up")

# The four kinds of bone end, in the order a refusal lists them.
END_KINDS = ("joint", "vertex", "mean", "position")

# Every key an end may carry on the way in.
END_KEYS = END_KINDS + ("offset", "snap")

# Every key a bone may carry on the way in.
BONE_KEYS = ("name", "parent", "head", "tail", "roll", "deform", "connect", "collections")

# What the reader adds and the builder drops, so a read-back can be sent unchanged.
READ_ONLY_BONE_KEYS = ("features_not_carried",)

# The table's spelling of MPFB's two recomputed roll strategies.
ROLL_ALIGNMENTS = {
    "align_z_world_z": "ALIGN_Z_WORLD_Z",
    "align_x_world_x": "ALIGN_X_WORLD_X",
}

# The collection a bone that names none goes into, and the one Blender gives a new armature.
DEFAULT_COLLECTION = "Bones"


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _frame_vector_error(value, complete):
    if not isinstance(value, dict) or not value:
        return "must be an object with {:s} of forward, left, up".format(
            "all" if complete else "any")
    unknown = sorted(key for key in value if key not in AXES)
    if unknown:
        return "has unknown key(s) {:s}; its keys are forward, left, up".format(", ".join(unknown))
    if complete and set(value) != set(AXES):
        return "must give all of forward, left, up"
    if not all(_is_number(component) for component in value.values()):
        return "must hold finite numbers"
    return None


def end_kind(end):
    """The one kind an end gives, ``position`` only when none of the other three is there."""
    named = [kind for kind in END_KINDS[:3] if kind in end]
    if named:
        return named
    return ["position"] if "position" in end else []


def _end_shape_error(end):
    if not isinstance(end, dict):
        return "must be an object"
    unknown = sorted(key for key in end if key not in END_KEYS)
    if unknown:
        return "has unknown key(s) {:s}; an end takes {:s}".format(
            ", ".join(unknown), ", ".join(END_KEYS))
    kinds = end_kind(end)
    if len(kinds) != 1:
        return ("must give exactly one of joint, vertex, mean or position, got {:s}".format(
            ", ".join(kinds) if kinds else "none"))
    kind = kinds[0]
    if kind == "joint" and (not isinstance(end["joint"], str) or not end["joint"]):
        return "joint must be a joint cube's name"
    if kind == "vertex" and not _is_count(end["vertex"]):
        return "vertex must be a vertex index, a non-negative integer"
    if kind == "mean":
        indices = end["mean"]
        if (not isinstance(indices, list) or len(indices) < 2
                or not all(_is_count(index) for index in indices)
                or len(set(indices)) != len(indices)):
            return "mean must be a list of two or more distinct vertex indices"
    if "position" in end:
        error = _frame_vector_error(end["position"], complete=True)
        if error is not None:
            return "position " + error
    if "offset" in end:
        error = _frame_vector_error(end["offset"], complete=False)
        if error is not None:
            return "offset " + error
    if "snap" in end:
        if not isinstance(end["snap"], bool):
            return "snap must be a boolean"
        if kind != "position":
            return "snap is taken only by a position end"
    return None


def _roll_shape_error(roll):
    if isinstance(roll, str):
        if roll not in ROLL_ALIGNMENTS:
            return "roll must be one of {:s}, or {{\"degrees\": n}}".format(
                ", ".join(ROLL_ALIGNMENTS))
        return None
    if not isinstance(roll, dict) or set(roll) != {"degrees"} or not _is_number(roll["degrees"]):
        return "roll must be one of {:s}, or {{\"degrees\": n}}".format(", ".join(ROLL_ALIGNMENTS))
    return None


def table_shape_errors(bones, max_bones):
    """Every shape fault in a table, as ``{where, error, message}`` rows. Empty means sound.

    The bridge's copy of the tool's checks, because the socket is reachable by more than
    mpfb-mcp. No joint, vertex count or bone vocabulary is checked here: that is the body's.
    """
    errors = []

    def fault(where, message, error="invalid_shape"):
        errors.append({"where": where, "error": error, "message": message})

    if not isinstance(bones, list) or not bones:
        fault("bones", "bones must be a non-empty list of bone objects")
        return errors
    if len(bones) > max_bones:
        fault("bones", "bones holds {:d} entries; at most {:d}".format(len(bones), max_bones))
        return errors
    names = []
    for position, bone in enumerate(bones):
        where = "bones[{:d}]".format(position)
        if not isinstance(bone, dict):
            fault(where, "must be an object")
            continue
        unknown = sorted(key for key in bone
                         if key not in BONE_KEYS and key not in READ_ONLY_BONE_KEYS)
        if unknown:
            fault(where, "has unknown key(s) {:s}; a bone takes {:s}".format(
                ", ".join(unknown), ", ".join(BONE_KEYS)))
            continue
        name = bone.get("name")
        if not isinstance(name, str) or not name.strip():
            fault(where, "name must be a non-empty string")
            continue
        if name in names:
            fault(where, "names {!r}, already named earlier in this table".format(name),
                  "duplicate_bone")
        names.append(name)
        parent = bone.get("parent", "")
        if not isinstance(parent, str):
            fault(where, "parent must be a string, empty for none")
        for key in ("head", "tail"):
            if key not in bone:
                fault(where, "{:s} is required".format(key))
                continue
            error = _end_shape_error(bone[key])
            if error is not None:
                fault("{:s}.{:s}".format(where, key), "{:s} {:s}".format(key, error))
        if "roll" in bone:
            error = _roll_shape_error(bone["roll"])
            if error is not None:
                fault(where, error)
        for flag in ("deform", "connect"):
            if flag in bone and not isinstance(bone[flag], bool):
                fault(where, "{:s} must be a boolean".format(flag))
        if "collections" in bone:
            collections = bone["collections"]
            if (not isinstance(collections, list) or not collections
                    or not all(isinstance(item, str) and item for item in collections)
                    or len(set(collections)) != len(collections)):
                fault(where, "collections must be a non-empty list of distinct names")
    if errors:
        return errors
    by_name = {bone["name"]: bone for bone in bones}
    for position, bone in enumerate(bones):
        parent = bone.get("parent", "")
        where = "bones[{:d}]".format(position)
        if parent and parent not in by_name:
            fault(where, "parent {!r} is not a bone in this table".format(parent),
                  "unknown_parent")
        elif parent == bone["name"]:
            fault(where, "is its own parent", "parent_cycle")
        if bone.get("connect") and not parent:
            fault(where, "connect needs a parent", "connect_without_parent")
    if errors:
        return errors
    for position, bone in enumerate(bones):
        seen = {bone["name"]}
        parent = bone.get("parent", "")
        while parent:
            if parent in seen:
                fault("bones[{:d}]".format(position),
                      "is its own ancestor through {!r}".format(parent), "parent_cycle")
                break
            seen.add(parent)
            parent = by_name[parent].get("parent", "")
    return errors
