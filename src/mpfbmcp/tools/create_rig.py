"""
The ``mpfb_create_rig`` tool: a bone table, built onto a character by MPFB's own fitter.

The builder of [FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)'s rig authoring
tools. It takes the table ``mpfb_get_rig_definition`` reads, so a read-back is a write, and
MPFB fits every bone: no position is computed from a mesh's vertices on either side of the
socket. ``create`` rather than ``add``, because ``mpfb_add_rig`` applies a catalogue entry.

**Validated here is the table's shape**, all of it before anything is sent: a non-empty list of
objects with known keys (``tial`` fails here, loudly), distinct non-empty names, a parent that is
another entry or ``""``, no cycle, ``connect`` only with a parent; each end exactly one of
``joint``, ``vertex``, ``mean`` or ``position``, finite numbers, ``position`` and ``offset`` frame
objects, ``snap`` only on a position; ``roll`` one of two alignments or ``{"degrees": d}``.
What a reading adds is dropped before sending: ``features_not_carried``, and the resolved
``position`` beside another kind. An end MPFB has no table form for, read back with
``expressible: false``, is refused here with a sentence, since it cannot be built.
**No joint, vertex count or bone vocabulary is checked here**: which joints a body has and how
many vertices it holds are Blender's, answered as ``resolution_errors``.

The bridge's ``shared/rig_definition.py`` repeats these checks, because its socket is reachable
by more than this package; ``tests/test_create_rig.py`` holds the two to one table of cases.
"""

from __future__ import annotations

__all__ = (
    "BONE_KEYS",
    "END_KEYS",
    "MAX_BONES",
    "ROLL_ALIGNMENTS",
    "register",
    "validated_bones",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

AXES = ("forward", "left", "up")
END_KINDS = ("joint", "vertex", "mean", "position")
END_KEYS = END_KINDS + ("offset", "snap")
BONE_KEYS = ("name", "parent", "head", "tail", "roll", "deform", "connect", "collections")
_READ_ONLY_BONE_KEYS = ("features_not_carried",)
ROLL_ALIGNMENTS = ("align_z_world_z", "align_x_world_x")

# The bridge's MAX_BONES, above every rig MPFB ships, so a read-back is always accepted.
MAX_BONES = 1000


def _is_index(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validated_frame(where: str, value: object, complete: bool) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError("{} must be an object with {} of forward, left, up, got {!r}".format(
            where, "all" if complete else "any", value))
    unknown = sorted(key for key in value if key not in AXES)
    if unknown:
        raise ValueError("{} has unknown key(s) {}; its keys are forward, left, up".format(
            where, ", ".join(unknown)))
    if complete and set(value) != set(AXES):
        raise ValueError("{} must give all of forward, left, up, got {!r}".format(where, value))
    if not all(arguments.is_finite_number(component) for component in value.values()):
        raise ValueError("{} must hold finite numbers, got {!r}".format(where, value))
    return {key: float(component) for key, component in value.items()}


def _validated_end(where: str, end: object) -> dict[str, object]:
    if not isinstance(end, dict):
        raise ValueError("{} must be an object, got {!r}".format(where, end))
    if end.get("expressible") is False:
        raise ValueError("{} is an end MPFB has no table form for ({!s}), so it cannot be "
                         "built; give it a joint, vertex, mean or position".format(
                             where, end.get("strategy")))
    unknown = sorted(key for key in end if key not in END_KEYS)
    if unknown:
        raise ValueError("{} has unknown key(s) {}; an end takes {}".format(
            where, ", ".join(unknown), ", ".join(END_KEYS)))
    kinds = [kind for kind in END_KINDS[:3] if kind in end] or (
        ["position"] if "position" in end else [])
    if len(kinds) != 1:
        raise ValueError("{} must give exactly one of joint, vertex, mean or position, got "
                         "{}".format(where, ", ".join(kinds) if kinds else "none"))
    kind = kinds[0]
    checked: dict[str, object] = {}
    if kind == "joint":
        if not isinstance(end["joint"], str) or not end["joint"].strip():
            raise ValueError("{} joint must be a joint cube's name, got {!r}".format(
                where, end["joint"]))
        checked["joint"] = end["joint"]
    elif kind == "vertex":
        if not _is_index(end["vertex"]):
            raise ValueError("{} vertex must be a non-negative integer, got {!r}".format(
                where, end["vertex"]))
        checked["vertex"] = end["vertex"]
    elif kind == "mean":
        indices = end["mean"]
        if (not isinstance(indices, list) or len(indices) < 2
                or not all(_is_index(index) for index in indices)
                or len(set(indices)) != len(indices)):
            raise ValueError("{} mean must be a list of two or more distinct vertex indices, got "
                             "{!r}".format(where, indices))
        checked["mean"] = list(indices)
    else:
        checked["position"] = _validated_frame(where + " position", end["position"], True)
    if "snap" in end:
        if kind != "position":
            raise ValueError("{} snap is taken only by a position end".format(where))
        checked["snap"] = arguments.validated_flag(end["snap"], where + " snap")
    if "offset" in end:
        checked["offset"] = _validated_frame(where + " offset", end["offset"], False)
    return checked


def _validated_roll(where: str, roll: object) -> object:
    if isinstance(roll, str) and roll in ROLL_ALIGNMENTS:
        return roll
    if (isinstance(roll, dict) and set(roll) == {"degrees"}
            and arguments.is_finite_number(roll["degrees"])):
        return {"degrees": float(roll["degrees"])}
    raise ValueError("{} roll must be one of {}, or {{\"degrees\": n}}, got {!r}".format(
        where, ", ".join(ROLL_ALIGNMENTS), roll))


def _validated_bone(where: str, bone: object) -> dict[str, object]:
    if not isinstance(bone, dict):
        raise ValueError("{} must be an object, got {!r}".format(where, bone))
    unknown = sorted(key for key in bone
                     if key not in BONE_KEYS and key not in _READ_ONLY_BONE_KEYS)
    if unknown:
        raise ValueError("{} has unknown key(s) {}; a bone takes {}".format(
            where, ", ".join(unknown), ", ".join(BONE_KEYS)))
    name = bone.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("{} name must be a non-empty string, got {!r}".format(where, name))
    parent = bone.get("parent", "")
    if not isinstance(parent, str):
        raise ValueError("{} parent must be a string, \"\" for none, got {!r}".format(
            where, parent))
    checked: dict[str, object] = {"name": name, "parent": parent}
    for key in ("head", "tail"):
        if key not in bone:
            raise ValueError("{} {} is required".format(where, key))
        checked[key] = _validated_end("{} {}".format(where, key), bone[key])
    if "roll" in bone:
        checked["roll"] = _validated_roll(where, bone["roll"])
    for flag in ("deform", "connect"):
        if flag in bone:
            checked[flag] = arguments.validated_flag(bone[flag], "{} {}".format(where, flag))
    if "collections" in bone:
        collections = arguments.validated_names(bone["collections"], where + " collections",
                                                "the default collection, Bones")
        checked["collections"] = collections
    return checked


def validated_bones(value: object) -> list[dict[str, object]]:
    """The table, every bone and end checked, with what a reading adds dropped."""
    if not isinstance(value, list) or not value:
        raise ValueError("bones must be a non-empty list of bone objects, got {!r}".format(value))
    if len(value) > MAX_BONES:
        raise ValueError("bones must hold at most {} entries, got {}".format(
            MAX_BONES, len(value)))
    checked = []
    seen: set = set()
    for position, bone in enumerate(value):
        where = "bones[{}]".format(position)
        normalized = _validated_bone(where, bone)
        if normalized["name"] in seen:
            raise ValueError("{} names {!r}, already named earlier in this table".format(
                where, normalized["name"]))
        seen.add(normalized["name"])
        checked.append(normalized)
    by_name = {bone["name"]: bone for bone in checked}
    for position, bone in enumerate(checked):
        where = "bones[{}]".format(position)
        parent = bone["parent"]
        if parent and parent not in by_name:
            raise ValueError("{} parent {!r} is not a bone in this table".format(where, parent))
        if bone.get("connect") and not parent:
            raise ValueError("{} connect needs a parent".format(where))
        ancestors = {bone["name"]}
        while parent:
            if parent in ancestors:
                raise ValueError("{} is its own ancestor through {!r}".format(where, parent))
            ancestors.add(parent)
            parent = by_name[parent]["parent"]
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create Rig",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_create_rig(
        bones: list[dict[str, object]],
        name: str | None = None,
        replace: bool = False,
    ) -> dict[str, object]:
        """
        Build a rig onto a character from a bone table, **fitted by MPFB to the body's
        joints** so it follows any later body. The first of four steps: create, then
        `mpfb_weight_rig`, `mpfb_store_rig`, and `mpfb_add_rig` with `custom.<name>` on
        another character. Rig a character before equipping it: `assets_not_rigged` names
        what was already on it.

        `bones` is exactly what `mpfb_get_rig_definition` reads, so a shipped rig's table
        is a starting point; what a reading adds is ignored. Per bone: `name`, `parent`
        (`""` for none), `head`, `tail`, and optionally `roll` (`"align_z_world_z"`,
        `"align_x_world_x"` or `{"degrees": d}`, default 0), `deform` (true), `connect`
        (false), `collections` (`["Bones"]`). An end is one of `{"joint": "joint-l-elbow"}`
        (names from `mpfb_get_rig_definition` with `include_joints`), `{"vertex": i}`,
        `{"mean": [i, j, ...]}` or `{"position": {forward, left, up}}` in the character
        frame, metres; any end may add an `offset` in the frame. **A position snaps** as
        MPFB's own save would match it, to a joint within 1 cm, else a vertex mean or a
        vertex, and `snapped_to` says to what and how far; `"snap": false` keeps it fixed,
        and `ends_not_following_body` names it, since a refit will not move it.

        The whole table is resolved first; any error is `resolution_failed` with every one
        in `resolution_errors` (`where`, `error`, `message`), and nothing is built.
        **A rigged character is refused** (`already_rigged`); `replace: true` rebuilds over
        a rig this tool built or one identified as `unknown`, keeping the groups of bones
        whose name and both ends are unchanged (`weights_kept`, `weights_dropped`), and
        refuses any other (`rig_not_authored`).

        `result` has `rig_object_name`, `bones` read back with positions, `snapped_to`,
        `ends_not_following_body`, `not_deforming`, `groups_already_present`,
        `basemesh_rotation_moved_to_rig`, `assets_not_rigged` and `next_with`. Other
        refusals: `subject_not_found`, `invalid_table`, `not_object_mode`, `build_failed`.
        """
        return backend.send(
            "create_rig",
            params={
                "name": arguments.validated_subject(name),
                "bones": validated_bones(bones),
                "replace": arguments.validated_flag(replace, "replace"),
            },
        )
