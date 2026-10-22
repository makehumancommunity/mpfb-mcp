"""
The ``mpfb_set_rigify_hand_shape`` tool: a named shape, or a curl and spread per finger, on a generated Rigify rig.

The writer half of [FR 047](../../../feature-requests/done/047-rigify-hand-shapes/README.md),
batched like ``mpfb_set_pose_bones`` but one entry per hand: a shape and its
exceptions is one entry, so "a fist with the index straight" is one call.

**Validated here**: each entry an object with known keys (a misspelled
``fingres`` fails here, loudly); ``body_part`` a non-empty string named once
per call; at least one of ``shape`` and ``fingers``; ``fingers`` an object of
finger name to ``curl`` and/or ``spread``; ``curl`` and ``spread`` finite
numbers in range and not ``bool``; ``symmetry`` a real ``bool``.

**Shape and finger names are checked here too**, as ``mode`` is: they are this
package's own vocabulary rather than the rig's or MPFB's, so a misspelled
``pinkie`` is a shape error with nothing to look up. The bridge checks them
again, and :data:`SHAPES` and :data:`FINGERS` are a copy of
``shared/rigify_hands.py``'s tables, which ``tests/test_set_rigify_hand_shape.py``
reads as data and requires to agree. **Which hands are hands is not checked
here**: ``body_part`` is the posing tools' vocabulary, answered bridge-side as
in every posing tool, and which fingers a rig has is the rig's.
"""

from __future__ import annotations

__all__ = (
    "CURL_RANGE",
    "FINGERS",
    "MAX_ENTRIES",
    "SHAPES",
    "SPREAD_RANGE",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

# Copies of the bridge's tables (shared/rigify_hands.py), checked against it.
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
SHAPES = ("open", "relaxed", "fist", "pointing", "grip", "pinch")
CURL_RANGE = (-0.2, 1.0)
SPREAD_RANGE = (-1.0, 1.0)

_KEYS = ("body_part", "shape", "fingers", "symmetry")
_AMOUNTS = {"curl": CURL_RANGE, "spread": SPREAD_RANGE}

# A character has two hands; anything longer repeats one.
MAX_ENTRIES = 2


def _validated_amounts(where: str, value: object) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError("{} must be an object with curl, spread or both, got {!r}".format(
            where, value))
    unknown = sorted(str(key) for key in value if key not in _AMOUNTS)
    if unknown:
        raise ValueError("{} has unknown key(s) {}; its keys are curl, spread".format(
            where, ", ".join(unknown)))
    checked = {}
    for key, amount in value.items():
        low, high = _AMOUNTS[key]
        if not arguments.is_finite_number(amount) or not low <= amount <= high:
            raise ValueError("{} {} must be a number from {:g} to {:g}, got {!r}".format(
                where, key, low, high, amount))
        checked[key] = float(amount)
    return checked


def _validated_fingers(where: str, value: object) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict) or not value:
        raise ValueError("{} must be an object keyed by finger ({}), got {!r}".format(
            where, ", ".join(FINGERS), value))
    unknown = [str(name) for name in value if name not in FINGERS]
    if unknown:
        raise ValueError("{} names {}, which {} not a finger; the fingers are {}".format(
            where, ", ".join(unknown), "is" if len(unknown) == 1 else "are", ", ".join(FINGERS)))
    return {name: _validated_amounts("{}.{}".format(where, name), amounts)
            for name, amounts in value.items()}


def _validated_entry(where: str, entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise ValueError("{} must be an object, got {!r}".format(where, entry))
    unknown = sorted(str(key) for key in entry if key not in _KEYS)
    if unknown:
        raise ValueError("{} has unknown key(s) {}; known keys are {}".format(
            where, ", ".join(unknown), ", ".join(_KEYS)))
    body_part = entry.get("body_part")
    if not isinstance(body_part, str) or not body_part.strip():
        raise ValueError("{} body_part must be a non-empty string, got {!r}".format(
            where, body_part))
    if "shape" not in entry and "fingers" not in entry:
        raise ValueError("{} changes nothing; give shape ({}), fingers, or both".format(
            where, ", ".join(SHAPES)))
    checked: dict[str, object] = {"body_part": body_part}
    if "shape" in entry:
        if entry["shape"] not in SHAPES:
            raise ValueError("{} shape must be one of {}, got {!r}".format(
                where, ", ".join(SHAPES), entry["shape"]))
        checked["shape"] = entry["shape"]
    if "fingers" in entry:
        checked["fingers"] = _validated_fingers("{} fingers".format(where), entry["fingers"])
    if "symmetry" in entry:
        checked["symmetry"] = arguments.validated_flag(entry["symmetry"],
                                                       "{} symmetry".format(where))
    return checked


def _validated_hands(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("hands must be a list of objects or omitted, got {!r}".format(value))
    checked = []
    seen: set = set()
    for position, entry in enumerate(value):
        where = "hands[{}]".format(position)
        normalized = _validated_entry(where, entry)
        if normalized["body_part"] in seen:
            raise ValueError("{} names {!r}, already named earlier in this call".format(
                where, normalized["body_part"]))
        seen.add(normalized["body_part"])
        checked.append(normalized)
    if len(checked) > MAX_ENTRIES:
        raise ValueError("hands must hold at most {} entries, one per hand, got {}".format(
            MAX_ENTRIES, len(checked)))
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Rigify Hand Shape",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_set_rigify_hand_shape(name: str | None = None,
                                   hands: list[dict] | None = None) -> dict[str, object]:
        """
        Shape the hands of a character rigged with a rig generated from MPFB's
        Rigify meta-rigs, one entry per hand, all or nothing. Any other rig is
        refused (`rig_not_supported`); pose its fingers with
        `mpfb_set_pose_bones`.

        An entry has `body_part` (`left_hand`/`right_hand`) and one or both of:

        - `shape`: `open`, `relaxed`, `fist`, `pointing`, `grip` or `pinch`,
          setting all five fingers; `mpfb_get_rigify_hand_shape`'s
          `known_shapes` gives each one's amounts.
        - `fingers`: `{finger: {curl, spread}}` for `thumb`, `index`,
          `middle`, `ring`, `pinky`, applied after `shape`. A finger or amount
          left out is left alone. `curl` is -0.2 (bent back) to 1.0 (closed
          as in a fist). `spread` is -1.0 to 1.0, the same on both hands:
          positive takes `index`, `ring` and `pinky` away from the middle
          finger, `middle` toward the index, the thumb away from the palm.

        `symmetry: true` applies the entry to the other hand too. A written
        finger's segment controls are put at rest (`segments_reset`).

        `result`'s `hands` give `fingers_before`/`fingers_after` as the
        reader reports them, `achieved` per written finger (false with
        `deviation` in degrees) and `matches_shape_after`. `restore_with` is
        the call, or two in order, that puts it back.
        """
        return backend.send(
            "set_rigify_hand_shape",
            params={
                "name": arguments.validated_subject(name),
                "hands": _validated_hands(hands),
            },
        )
