"""
The ``mpfb_weight_rig`` tool: vertex weights for an authored rig, and a fill for what they miss.

The second of [FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)'s rig authoring
steps. Nothing in MPFB weights a new rig: MakeRig's auto transfer matches only bones whose
ends coincide and MakeWeight's symmetrize does nothing. Why each method is built the way it is
- heat weighting on a copy without the joint cubes, which break Blender's solve, and a transfer
that understands merged chains - is in the bridge command's docstring.

**Validated here is shape**: ``method`` and ``direction`` are this package's own vocabularies,
so they are checked here, as ``mpfb_symmetrize_targets`` checks ``direction``. Each method's own
argument is refused beside another method (``from_rig`` with ``mirror`` is a mistake, not an
argument to ignore), and a method missing its own is refused too. ``exclude_bones`` and
``bone_names`` are optional non-empty lists of distinct names, ``fill_unweighted`` a real bool.
**No bone or rig vocabulary is checked here.**
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

METHODS = ("automatic", "transfer", "mirror")
DIRECTIONS = ("left_to_right", "right_to_left")

# Each method's own argument, which another method refuses.
_OWNED = {"exclude_bones": "automatic", "from_rig": "transfer", "direction": "mirror"}


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


def _refused_combination(method: str, supplied: dict[str, object]) -> None:
    for argument, owner in _OWNED.items():
        if supplied[argument] is not None and method != owner:
            raise ValueError("{} is taken only with method {}, not {}".format(
                argument, owner, method))
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
    ) -> dict[str, object]:
        """
        Weight a rig `mpfb_create_rig` built (or one identified as `unknown`): the second
        step, after create and before `mpfb_store_rig`. Writes only the vertex groups of
        deforming bones, each replaced whole. The rig must be at rest.

        `method` is required:
        - `"automatic"`: Blender's heat weighting, run on a copy of the body at the shape
          MPFB fitted the bones to. `exclude_bones` leaves bones out and sets them
          non-deforming; **a bone from `joint-ground` takes the thighs**, and every answer
          names any in `deforming_bones_on_ground`.
        - `"transfer"`: `from_rig`'s weights (an `mpfb_list_rigs` identifier, the file
          `mpfb_add_rig` would load), by vertex index. Per bone `matched_by` is `exact`
          (both ends within 1 mm of one source bone), `chain` (head on one, tail on a
          descendant's, the chain summed) or `none` with `nearest_miss`; `sources` names
          each contribution, `ancestor` for a source bone nothing covered, given to its
          nearest matched ancestor's bone. `source_bones_unassigned` lost their weights.
        - `"mirror"`: one side onto the other through MPFB's `hm08.mirror`, `direction`
          `"left_to_right"` or `"right_to_left"`; bones pair by `.L`/`.R` or `_l`/`_r`, a
          centre bone onto itself, and `bones_without_partner` are not guessed.

        `fill_unweighted` (default true, not for mirror) gives every vertex left with no
        weight the weights of the nearest weighted body vertex. `unweighted` counts
        `before_fill` and `after_fill` as `body`, `helper` and `joint_cube`; **a body count
        before the fill means the pass itself failed there.** `bone_names` limits the call
        to those bones.

        `result` has `bones`, each with its `vertex_count`, `bones_without_weights`,
        `groups_replaced` (groups that had weights before), `set_non_deforming` and
        `next_with`. Refusals:
        `subject_not_found`, `not_rigged`, `rig_not_authored`, `rig_not_at_rest`,
        `not_object_mode`, `unknown_bone_names`, `not_deforming`, `unknown_identifier`,
        `no_weights`.
        """
        checked_method = _validated_method(method)
        supplied = {
            "exclude_bones": arguments.validated_names(
                exclude_bones, "exclude_bones", "no bone left out"),
            "from_rig": arguments.validated_text(
                from_rig, "from_rig", "omit it unless method is transfer"),
            "direction": _validated_direction(direction),
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
                "bone_names": arguments.validated_names(
                    bone_names, "bone_names", "every deforming bone"),
            },
        )
