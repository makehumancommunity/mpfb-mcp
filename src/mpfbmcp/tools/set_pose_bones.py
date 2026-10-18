"""
The ``mpfb_set_pose_bones`` tool: move, rotate, aim and scale a character's controls.

The transform half of [FR 042](../../../feature-requests/done/042-posing-bones-switches-and-reset/README.md),
batched like ``mpfb_set_targets``: a stance is a few dozen bone writes, and
the answer reports every one. Positions and rotations are in the character
frame, in exactly the shape ``mpfb_get_pose`` reads them back, so a read-back -
and ``mpfb_reset_pose``'s ``restore_with`` - is a valid write.

**Validated here is shape only**: each entry is an object with known keys
(a misspelled ``move_too`` fails here, loudly); ``bone`` is a non-empty string,
named once per call; at most one position and one rotation, at least one change;
a vector is an object with only ``forward``/``left``/``up`` and finite numbers;
a rotation is exactly ``axis`` and ``degrees``, its axis not the zero vector
(``rotate_to`` also takes ``axis: null``, which is how a read-back reports rest);
``aim`` is not the zero vector and ``twist`` comes only with it; ``scale_to``
factors are positive; ``symmetry`` is a real ``bool``. **No bone vocabulary is
checked here**: which bones exist, which are controls and which are in charge
is the rig's, answered as ``resolution_errors``.

The cap is far above a stance and above every control a generated rig has,
because ``mpfb_reset_pose``'s ``restore_with`` is never capped and must always
be a call this tool accepts.
"""

from __future__ import annotations

__all__ = (
    "MAX_ENTRIES",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

AXES = ("forward", "left", "up")
_POSITIONS = ("move_by", "move_to")
_ROTATIONS = ("rotate_by", "rotate_to", "aim")
_KEYS = ("bone",) + _POSITIONS + _ROTATIONS + ("twist", "scale_to", "symmetry")

MAX_ENTRIES = 2000


def _validated_vector(where: str, value: object, nonzero: bool) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError("{} must be an object with any of {}, got {!r}".format(
            where, ", ".join(AXES), value))
    unknown = sorted(key for key in value if key not in AXES)
    if unknown:
        raise ValueError("{} has unknown key(s) {}; its keys are {}".format(
            where, ", ".join(unknown), ", ".join(AXES)))
    if not all(arguments.is_finite_number(component) for component in value.values()):
        raise ValueError("{} must hold finite numbers, got {!r}".format(where, value))
    if nonzero and all(float(component) == 0.0 for component in value.values()):
        raise ValueError("{} must not be the zero vector".format(where))
    return {key: float(component) for key, component in value.items()}


def _validated_rotation(where: str, value: object, rest_allowed: bool) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"axis", "degrees"}:
        raise ValueError("{} must be an object with exactly axis and degrees, got {!r}".format(
            where, value))
    if not arguments.is_finite_number(value["degrees"]):
        raise ValueError("{} degrees must be a finite number, got {!r}".format(
            where, value["degrees"]))
    if value["axis"] is None and rest_allowed:
        return {"axis": None, "degrees": float(value["degrees"])}
    return {"axis": _validated_vector(where + " axis", value["axis"], nonzero=True),
            "degrees": float(value["degrees"])}


def _validated_scale_to(where: str, value: object) -> dict[str, float]:
    if not isinstance(value, dict) or not value or any(key not in ("x", "y", "z")
                                                       for key in value):
        raise ValueError("{} must be an object with any of x, y, z, got {!r}".format(
            where, value))
    if not all(arguments.is_finite_number(factor) and factor > 0.0 for factor in value.values()):
        raise ValueError("{} factors must be finite positive numbers, got {!r}".format(
            where, value))
    return {key: float(factor) for key, factor in value.items()}


def _validated_entry(where: str, entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise ValueError("{} must be an object, got {!r}".format(where, entry))
    unknown = sorted(key for key in entry if key not in _KEYS)
    if unknown:
        raise ValueError("{} has unknown key(s) {}; known keys are {}".format(
            where, ", ".join(unknown), ", ".join(_KEYS)))
    bone = entry.get("bone")
    if not isinstance(bone, str) or not bone.strip():
        raise ValueError("{} bone must be a non-empty string, got {!r}".format(where, bone))
    for kinds, what in ((_POSITIONS, "a position"), (_ROTATIONS, "a rotation")):
        named = [key for key in kinds if key in entry]
        if len(named) > 1:
            raise ValueError("{} gives {} twice ({}); at most one of {}".format(
                where, what, ", ".join(named), ", ".join(kinds)))
    if not any(key in entry for key in _POSITIONS + _ROTATIONS + ("scale_to",)):
        raise ValueError("{} changes nothing; give a position ({}), a rotation ({}) or "
                         "scale_to".format(where, " or ".join(_POSITIONS), ", ".join(_ROTATIONS)))
    checked: dict[str, object] = {"bone": bone}
    for key in _POSITIONS:
        if key in entry:
            checked[key] = _validated_vector("{} {}".format(where, key), entry[key], False)
    for key in ("rotate_by", "rotate_to"):
        if key in entry:
            checked[key] = _validated_rotation("{} {}".format(where, key), entry[key],
                                               rest_allowed=key == "rotate_to")
    if "aim" in entry:
        checked["aim"] = _validated_vector("{} aim".format(where), entry["aim"], True)
    if "twist" in entry:
        if "aim" not in entry:
            raise ValueError("{} twist is only taken with aim".format(where))
        if not arguments.is_finite_number(entry["twist"]):
            raise ValueError("{} twist must be a finite number of degrees, got {!r}".format(
                where, entry["twist"]))
        checked["twist"] = float(entry["twist"])
    if "scale_to" in entry:
        checked["scale_to"] = _validated_scale_to("{} scale_to".format(where), entry["scale_to"])
    if "symmetry" in entry:
        checked["symmetry"] = arguments.validated_flag(entry["symmetry"],
                                                       "{} symmetry".format(where))
    return checked


def _validated_bones(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("bones must be a list of objects or omitted, got {!r}".format(value))
    if len(value) > MAX_ENTRIES:
        raise ValueError("bones must hold at most {} entries, got {}".format(
            MAX_ENTRIES, len(value)))
    checked = []
    seen: set = set()
    for position, entry in enumerate(value):
        where = "bones[{}]".format(position)
        normalized = _validated_entry(where, entry)
        if normalized["bone"] in seen:
            raise ValueError("{} names {!r}, already named earlier in this call".format(
                where, normalized["bone"]))
        seen.add(normalized["bone"])
        checked.append(normalized)
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Pose Bones",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_set_pose_bones(name: str | None = None,
                            bones: list[dict] | None = None) -> dict[str, object]:
        """
        Pose a MakeHuman character: move, rotate, aim and scale its controls,
        as one all-or-nothing batch. Bones, body parts, roles and the
        character frame are as `mpfb_get_pose_controls` describes. Send the
        whole stance in one call.

        Each entry names a `bone` and at most one change of each kind:

        - position: `move_by` (metres, a frame vector) or `move_to` (where the
          head goes - `mpfb_get_pose`'s `head`);
        - rotation: `rotate_by` (`{axis, degrees}`, about the head) or
          `rotate_to` (from rest, parents included - `mpfb_get_pose`'s
          `rotation`), or `aim` (the head-to-tail direction, swung from rest)
          with optional `twist` in degrees;
        - `scale_to`: factors relative to rest, keyed `x`/`y`/`z` in the
          **bone's own** axes (`y` along it). A fist on Rigify is `y` below 1
          on the finger masters.

        Bones are written parent before child, relative changes from the pose
        at that moment. `symmetry: true` also writes the counterpart, mirrored
        (`left` negated); it comes back as its own change with
        `mirrored_from`.

        **Nothing is written unless every entry can be.** `resolution_errors`
        gives each `reason`: not a control, a chain `IK_FK` has handed away,
        an FK bone an MPFB helper drives, a locked or driven channel. Its
        `write_instead` names the bone, or the `mpfb_set_pose_switches` entry,
        that would work.

        `result`'s `changes`, in request order, give `head`/`rotation`/
        `scale` before and after and `achieved` (false with `deviation` when
        a constraint or IK stopped it short). `landmarks` before and after,
        `limbs` after as in
        `mpfb_get_pose`, and `limbs_made_stretched`/`limbs_made_unreachable`
        say what moved as a consequence. Blender's undo does not see this;
        `mpfb_reset_pose` does.
        """
        return backend.send(
            "set_pose_bones",
            params={
                "name": arguments.validated_subject(name),
                "bones": _validated_bones(bones),
            },
        )
