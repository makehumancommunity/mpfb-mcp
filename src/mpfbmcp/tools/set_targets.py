"""
The ``mpfb_set_targets`` tool: change a character's detail targets, in batches.

The tool ``mpfb_list_targets`` was built for. It works at two levels, because
MPFB does. A modeling *slider* is a ``target.json`` **category**: a modifier
running from -1.0 to +1.0, built from a pair of opposing targets, where the sign
selects which of the two is loaded and the other is driven to zero - and about a
third of the categories have separate ``l-`` and ``r-`` variants, giving four
target files behind one conceptual control. Shape keys cannot express that:
Blender clamps a shape key value to 0.0-1.0, so "flaring -0.4" only exists as
"flaring-decr at 0.4, flaring-incr at 0.0". So the category level is what an
agent should normally use, and the raw shape-key level is the escape hatch for a
user's own installed targets, which belong to no category.

**Batched from the outset rather than retrofitted.** A socket round trip costs
roughly a second while the work inside costs milliseconds, so a modeling session
of thirty small changes would be half a minute of waiting for a fraction of a
second of work. That is also why the arguments are lists of dicts rather than
the flat scalars every other mutating tool here takes: a batch is irreducibly a
list, and what compensates for a schema that cannot check its entries is the
per-entry validation below plus the ``resolution_errors`` channel in the
response.

Validation here is **shape only** - that an entry is a dict, that its keys are
known, that a value is a real number in the right range, that a side is one of
three strings. Never the vocabulary of sections, categories or shape key names:
half the sections are synthesized from the user's own directories and cannot be
known on this side of the socket at all.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

_MODIFIER_KEYS = ("section", "category", "value", "side")
_TARGET_KEYS = ("shapekey_name", "value")
_SIDES = ("left", "right", "unsided")

# Generous, but not unbounded: a batch is one exec() inside Blender, and a
# runaway list would be a very long-running call with no way to report progress.
MAX_ENTRIES = 500


def _validated_number(where: str, value: object, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # A bool is an int in Python, so True would otherwise be stored as 1.0
        # under the guise of a number the caller never wrote.
        raise ValueError(
            "{} value must be a number between {} and {}, got {!r}".format(
                where, low, high, value))
    if not low <= float(value) <= high:
        raise ValueError(
            "{} value must be between {} and {}, got {!r}".format(where, low, high, value))
    return float(value)


def _validated_entry_text(where: str, key: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("{} {} must be a string, got {!r}".format(where, key, value))
    if not value.strip():
        raise ValueError("{} {} must not be empty or whitespace".format(where, key))
    return value


def _validated_list(argument: str, value: object, known_keys: tuple[str, ...]) -> list[dict]:
    """Every entry a dict whose keys are known - misspellings fail here, loudly."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(
            "{} must be a list of objects or omitted, got {!r}".format(argument, value))
    if len(value) > MAX_ENTRIES:
        raise ValueError(
            "{} must hold at most {} entries, got {}".format(
                argument, MAX_ENTRIES, len(value)))
    for position, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise ValueError(
                "{}[{}] must be an object, got {!r}".format(argument, position, entry))
        unknown = sorted(key for key in entry if key not in known_keys)
        if unknown:
            raise ValueError(
                "{}[{}] has unknown key(s) {}; known keys are {}".format(
                    argument, position, ", ".join(unknown), ", ".join(known_keys)))
    return value


def _validated_modifiers(value: object) -> list[dict]:
    entries = _validated_list("modifiers", value, _MODIFIER_KEYS)
    checked = []
    for position, entry in enumerate(entries):
        where = "modifiers[{}]".format(position)
        section = _validated_entry_text(where, "section", entry.get("section"))
        category = _validated_entry_text(where, "category", entry.get("category"))
        # -1.0..+1.0 here, because a category *may* be a pair of opposites.
        # Which range actually applies depends on the category, which is only
        # knowable inside Blender - so the narrower 0.0..1.0 check for a
        # category with no opposites happens there and comes back as a
        # resolution error rather than as a local failure.
        number = _validated_number(where, entry.get("value"), -1.0, 1.0)
        side = entry.get("side")
        if side is not None and side not in _SIDES:
            raise ValueError(
                "{} side must be one of {} or omitted, got {!r}".format(
                    where, ", ".join(_SIDES), side))
        checked.append({"section": section, "category": category,
                        "value": number, "side": side})
    return checked


def _validated_targets(value: object) -> list[dict]:
    entries = _validated_list("targets", value, _TARGET_KEYS)
    checked = []
    for position, entry in enumerate(entries):
        where = "targets[{}]".format(position)
        shapekey_name = _validated_entry_text(
            where, "shapekey_name", entry.get("shapekey_name"))
        # 0.0..1.0 and not wider: this is a raw shape key value, and Blender
        # clamps one to that range. A negative here would silently store 0.0.
        number = _validated_number(where, entry.get("value"), 0.0, 1.0)
        checked.append({"shapekey_name": shapekey_name, "value": number})
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Detail Targets",
            readOnlyHint=False,
            # Pruning deletes shape keys, including ones the caller did not name.
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_set_targets(name: str | None = None,
                         modifiers: list[dict] | None = None,
                         targets: list[dict] | None = None,
                         symmetry: bool = False,
                         prune: bool = True,
                         refit: bool = False) -> dict[str, object]:
        """
        Change a MakeHuman character's detail targets - one modeling slider,
        one raw target, or fifty of them in a single call.

        **Send the whole change as one call.** A round trip costs about half a
        second and the work inside costs milliseconds.

        **`modifiers` is the level to use normally.** Each entry is `{section,
        category, value, side}`, naming a `target.json` section and one of its
        categories exactly as `mpfb_list_targets` reports them:

          - `value` runs -1.0..+1.0 for a category that has `opposites` - the
            sign picks which of the opposing pair is loaded, and the other is
            driven to zero - and 0.0..1.0 for one that does not.
          - `side` is `"left"`, `"right"` or `"unsided"`. **Required** for a
            category with `has_left_and_right: true`, and omitted or
            `"unsided"` for one without.

        **`targets` is the escape hatch**, for a user-installed target that
        belongs to no category. Each entry is `{shapekey_name, value}` with
        `value` in 0.0..1.0, the range Blender clamps a shape key to. Use the
        `shapekey_name` `mpfb_list_targets` reports, **not** the filename:
        above 60 characters MPFB encodes the name, and a filename then
        addresses nothing at all, silently.

        Both lists are optional and either may be empty; a call naming neither
        does nothing and says so.

        **Nothing is applied unless everything resolves.** Every entry is
        checked inside Blender first - the section and category exist, the side
        fits the category, the value is in that category's range, the target
        file can be found - and if any entry fails, `resolution_errors` names
        which and **zero changes are made**. Fix them and resend the whole
        batch; `known_sections` and `known_categories_in_section` come back
        with the error.

        `symmetry` (default false, MPFB's own) also applies a sided change to
        the other side, so one entry touches up to four shape keys. `prune`
        (default true, MPFB's own) deletes a target's shape key once its value
        reaches zero. `refit` (default false, MPFB's own) re-fits clothes and
        the rig afterwards; leave it false, read `assets_possibly_stale`, and
        call `mpfb_refit_human` once when the modeling is done.


        `result` carries `changes` - one entry per requested change, in request
        order, each listing every target file touched with `present_before`,
        `previous_value`, `new_value`, `loaded_from` (set when the target was
        read off disk on this call) and `pruned` - plus `shapekeys_added` and
        `shapekeys_removed`, `refit_performed`, `assets_possibly_stale` and
        `basemesh_name`. An unresolvable subject answers `found: false`, and a
        basemesh in edit mode or without shape keys `ready: false` with
        `blocked_by`. `performed` is false whenever `changes` is empty, the
        all-or-nothing resolution failure included.
        """
        # `result` (built in bridge/mpfb_bridge/commands/set_targets.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "set_targets",
            params={
                "name": arguments.validated_subject(name),
                "modifiers": _validated_modifiers(modifiers),
                "targets": _validated_targets(targets),
                "symmetry": arguments.validated_flag(symmetry, "symmetry"),
                "prune": arguments.validated_flag(prune, "prune"),
                # Not truthiness: refit="false" would pay for a full asset refit.
                "refit": arguments.validated_flag(refit, "refit"),
            },
        )
