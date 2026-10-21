"""
The ``mpfb_place_character`` tool: where a character stands, and which way it faces.

[FR 045](../../../feature-requests/done/045-placing-a-character/README.md). MPFB
builds every character at the origin, so a scene with more than one starts by
moving them apart; this is that step, with the answer a caller needs to space
them (``footprint``) and to undo it (``restore_with``).

**Validated here is shape only.** ``position`` is an object with any of ``x``,
``y`` and ``z`` and finite numbers; ``facing`` a finite number of degrees;
``face_toward`` either ``{"object": <name>}`` alone or a point with ``x`` and
``y`` (a ``z`` is accepted and ignored, so a ``position`` can be passed as
one), never both forms; ``facing`` and ``face_toward`` are refused together,
and a call naming none of the three is refused, since it would change nothing.
An unknown key anywhere is refused, because a misspelled ``positon`` key
inside an object is otherwise silent. **No object name is checked here**:
whether ``face_toward``'s object exists is the far side's answer
(``face_toward_not_found``), as is a tilted character and a target with no
direction. Everything about what the answer holds is decided and tested in
``bridge/mpfb_bridge/commands/place_character.py``.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

_POSITION_KEYS = ("x", "y", "z")


def _validated_numbers(where: str, value: dict) -> dict[str, float]:
    if not all(arguments.is_finite_number(component) for component in value.values()):
        raise ValueError("{} must hold finite numbers, got {!r}".format(where, value))
    return {key: float(component) for key, component in value.items()}


def _validated_position(value: object) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise ValueError("position must be an object with any of x, y, z, got {!r}".format(value))
    unknown = sorted(key for key in value if key not in _POSITION_KEYS)
    if unknown:
        raise ValueError("position has unknown key(s) {}; its keys are x, y, z".format(
            ", ".join(unknown)))
    return _validated_numbers("position", value)


def _validated_facing(value: object) -> float | None:
    if value is None:
        return None
    if not arguments.is_finite_number(value):
        raise ValueError("facing must be a finite number of degrees, got {!r}".format(value))
    return float(value)  # type: ignore[arg-type]


def _validated_face_toward(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("face_toward must be an object, {{\"object\": <name>}} or "
                         "{{\"x\", \"y\"}}, got {!r}".format(value))
    if "object" in value:
        if set(value) != {"object"}:
            raise ValueError("face_toward names an object, so it must hold 'object' alone, got "
                             "{!r}".format(value))
        target = value["object"]
        if not isinstance(target, str) or not target.strip():
            raise ValueError("face_toward object must be a non-empty Blender object name, got "
                             "{!r}".format(target))
        return {"object": target}
    unknown = sorted(key for key in value if key not in _POSITION_KEYS)
    if unknown:
        raise ValueError("face_toward has unknown key(s) {}; give 'object', or a point with "
                         "x and y".format(", ".join(unknown)))
    if "x" not in value or "y" not in value:
        raise ValueError("face_toward as a point needs both x and y, got {!r}".format(value))
    return _validated_numbers("face_toward", value)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Place Character",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_place_character(name: str | None = None,
                             position: dict | None = None,
                             facing: float | None = None,
                             face_toward: dict | None = None) -> dict[str, object]:
        """
        Place a MakeHuman character in the scene: where it stands and which
        way it faces. MPFB builds every character at the origin. Moves the
        root - the rig, else the body - and everything on it, a hidden Rigify
        meta-rig included.

        - `position`: world metres, any of `x`, `y`, `z`; a key left out
          keeps its value, so `{"x": 2}` slides it without lifting it.
        - `facing`: degrees about world up. `0` faces world -Y, as MPFB builds
          characters; positive turns counter-clockwise seen from above.
        - `face_toward`, instead of `facing`: a point `{"x", "y"}` or
          `{"object": "Camera"}`, faced from where `position` puts it.

        `result`: `placed`, `root_name`, `position_before`/`position_after`,
        `facing_before`/`facing_after`, `moved_with`, `character_frame`, and
        `footprint` - the visible body and assets' world box, `min`/`max` and
        `width`/`depth`/`height` along world X/Y/Z - to space characters.
        `restore_with` is the call that puts it back. A character turned
        about anything but up is refused a turn (`character_tilted`).

        **Dress a character before placing it**: a garment's sub-rig (e.g.
        ponytail01's) equipped away from the origin is bound wrong and drags
        its vertices away. `subrigs_broken` names each, measured; a move
        neither causes nor cures it, `mpfb_refit_human` does. Read placement
        with `mpfb_get_character_summary`.
        """
        position_checked = _validated_position(position)
        facing_checked = _validated_facing(facing)
        face_toward_checked = _validated_face_toward(face_toward)
        if facing_checked is not None and face_toward_checked is not None:
            raise ValueError("give facing or face_toward, not both")
        if position_checked is None and facing_checked is None and face_toward_checked is None:
            raise ValueError("name at least one of position, facing and face_toward; a call "
                             "that names none would change nothing (read a character's placement "
                             "with mpfb_get_character_summary)")
        return backend.send(
            "place_character",
            params={
                "name": arguments.validated_subject(name),
                "position": position_checked,
                "facing": facing_checked,
                "face_toward": face_toward_checked,
            },
        )
