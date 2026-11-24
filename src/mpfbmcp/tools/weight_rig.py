"""
The ``mpfb_weight_rig`` tool: vertex weights for an authored rig, a fill for what they miss, and a
clean.

The second of [FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)'s rig authoring
steps. Nothing in MPFB weights a new rig: MakeRig's auto transfer matches only bones whose
ends coincide and MakeWeight's symmetrize does nothing. Why each method is built the way it is
- heat weighting on the neutral body without the joint cubes, which break Blender's solve, a
transfer that understands merged chains, a rule per helper and a clean that never touches a
mask ([FR 061](../../../feature-requests/done/061-rig-weights-that-hold-up/README.md)) - is in
the bridge command's docstring.

**Validated here is shape**: ``method`` and ``direction`` are this package's own vocabularies,
so they are checked here, as ``mpfb_symmetrize_targets`` checks ``direction``. Each method's own
argument is refused beside another method (``from_rig`` with ``mirror`` is a mistake, not an
argument to ignore), and a method missing its own is refused too. ``exclude_bones`` and
``bone_names`` are optional non-empty lists of distinct names, ``fill_unweighted`` a real bool,
``helper_bones`` an object of non-empty names, ``min_weight`` a finite number in [0, 1) and
``max_influences`` a positive count that is not a bool. **No bone, helper or rig vocabulary is
checked here.**
"""

from __future__ import annotations

__all__ = (
    "DIRECTIONS",
    "METHODS",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

METHODS = ("automatic", "transfer", "mirror", "clean")
DIRECTIONS = ("left_to_right", "right_to_left")

# Each method's own argument, which another method refuses.
_OWNED = {"exclude_bones": ("automatic",), "from_rig": ("transfer",), "direction": ("mirror",),
          "helper_bones": ("automatic", "transfer"),
          "bone_names": ("automatic", "transfer", "mirror")}

# MPFB's ``exclude_weights_below``, the clean's default.
_MIN_WEIGHT = 0.0001


def _validated_method(method: object) -> str:
    if method not in METHODS:
        raise ValueError("method must be one of {}, got {!r}".format(", ".join(METHODS), method))
    return method  # type: ignore[return-value]


def _validated_direction(direction: object) -> str | None:
    if direction is None:
        return None
    if direction not in DIRECTIONS:
        raise ValueError("direction must be one of {}, got {!r}".format(
            ", ".join(DIRECTIONS), direction))
    return direction  # type: ignore[return-value]


def _validated_helper_bones(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise ValueError("helper_bones must be a non-empty object of helper group to bone, or "
                         "omitted, got {!r}".format(value))
    for key, bone in value.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(bone, str) \
                or not bone.strip():
            raise ValueError("helper_bones maps a helper group's name to a bone's name, both "
                             "non-empty strings, got {!r}: {!r}".format(key, bone))
    return dict(value)


def _validated_min_weight(value: object) -> float:
    if not arguments.is_finite_number(value) or not 0.0 <= value < 1.0:  # type: ignore[operator]
        raise ValueError("min_weight must be a number from 0.0 up to but not including 1.0, "
                         "got {!r}".format(value))
    return float(value)  # type: ignore[arg-type]


def _validated_max_influences(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("max_influences must be a positive int, or omitted for no cap, got "
                         "{!r}".format(value))
    return value


def _refused_combination(method: str, supplied: dict[str, object]) -> None:
    for argument, owners in _OWNED.items():
        if supplied[argument] is not None and method not in owners:
            raise ValueError("{} is taken only with method {}, not {}".format(
                argument, " or ".join(owners), method))
    if method == "transfer" and supplied["from_rig"] is None:
        raise ValueError("method transfer needs from_rig, an identifier from mpfb_list_rigs")
    if method == "mirror" and supplied["direction"] is None:
        raise ValueError("method mirror needs direction, one of {}".format(", ".join(DIRECTIONS)))


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Weight Rig",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_weight_rig(
        method: str,
        name: str | None = None,
        exclude_bones: list[str] | None = None,
        from_rig: str | None = None,
        direction: str | None = None,
        fill_unweighted: bool = True,
        bone_names: list[str] | None = None,
        helper_bones: dict[str, str] | None = None,
        min_weight: float = _MIN_WEIGHT,
        max_influences: int | None = None,
    ) -> dict[str, object]:
        """
        Weight a rig `mpfb_create_rig` built (or one identified as `unknown`): after create,
        then `mpfb_check_rig_weights`, then `mpfb_store_rig`. Writes only the vertex groups
        of deforming bones, never a mask. The rig must be at rest.

        `method` is required:
        - `"automatic"`: Blender's heat weighting **on the neutral body** (the rig fitted to
          the Basis), whatever this character's shape, so a stored file suits every body;
          `weighted_on` says so and `ends_not_following_body` names fixed `position` ends.
          `exclude_bones` leaves bones out, set non-deforming; **a bone from `joint-ground`
          takes the thighs** (`deforming_bones_on_ground`).
        - `"transfer"`: `from_rig`'s weights (an `mpfb_list_rigs` identifier), by vertex
          index. Per bone `matched_by` is `exact` (both ends within 1 mm), `chain` (head on
          one, tail on a descendant's, summed) or `none` with `nearest_miss`; `sources` names
          each, `ancestor` for one nothing covered. `source_bones_unassigned` lost theirs.
        - `"mirror"`: one side onto the other through MPFB's `hm08.mirror`, `direction`
          `"left_to_right"` or `"right_to_left"`; `.L`/`.R` or `_l`/`_r`, a centre bone onto
          itself, `bones_without_partner` not guessed.
        - `"clean"`: only the clean below.

        `fill_unweighted` (default true; automatic, transfer) weights every vertex left
        unweighted, **by a rule per helper**: eyes and teeth `rigid` to one bone (the one
        with its head on the eye or mouth joint; `chosen_by` `only_candidate`,
        `anchor_name`, `nearest_dominant` or `helper_bones`, with the other `candidates`),
        the tongue `interior_chain`, everything else `nearest` skin. `helper_bones`
        (`{"helper-l-eye": "eye.L"}`) chooses a rigid helper's bone. `helpers` reports each.
        `unweighted` counts `before_fill`/`after_fill` as `body`, `helper`, `joint_cube`;
        **a body count before the fill means the pass failed there.**

        **Every method ends by cleaning** the deform groups: weights below `min_weight`
        (default 0.0001) dropped, at most `max_influences` per vertex (no cap by default),
        each vertex normalised. `clean` has `histogram_before`/`_after`,
        `vertices_trimmed`, `vertices_normalised`, `max_weight_removed`.

        `result` has `bones` with `vertex_count`, `bones_without_weights`, `groups_replaced`
        (had weights before), `groups_rescaled` (changed only by the clean),
        `set_non_deforming`, `next_with`. `bone_names` limits the call to those bones, and
        then the fill is `nearest` only. Refusals: `subject_not_found`, `not_rigged`,
        `rig_not_authored`, `rig_not_at_rest`, `not_object_mode`, `unknown_bone_names`,
        `unknown_helper_groups`, `not_deforming`, `unknown_identifier`, `no_weights`.
        """
        checked_method = _validated_method(method)
        supplied = {
            "exclude_bones": arguments.validated_names(
                exclude_bones, "exclude_bones", "no bone left out"),
            "from_rig": arguments.validated_text(
                from_rig, "from_rig", "omit it unless method is transfer"),
            "direction": _validated_direction(direction),
            "helper_bones": _validated_helper_bones(helper_bones),
            "bone_names": arguments.validated_names(
                bone_names, "bone_names", "every deforming bone"),
        }
        _refused_combination(checked_method, supplied)
        return backend.send(
            "weight_rig",
            params={
                "name": arguments.validated_subject(name),
                "method": checked_method,
                "exclude_bones": supplied["exclude_bones"],
                "from_rig": supplied["from_rig"],
                "direction": supplied["direction"],
                "fill_unweighted": arguments.validated_flag(fill_unweighted, "fill_unweighted"),
                "bone_names": supplied["bone_names"],
                "helper_bones": supplied["helper_bones"],
                "min_weight": _validated_min_weight(min_weight),
                "max_influences": _validated_max_influences(max_influences),
            },
        )
