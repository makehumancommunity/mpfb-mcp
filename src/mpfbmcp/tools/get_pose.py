"""
The ``mpfb_get_pose`` tool: what a character's pose is now.

The read-back half of [FR 041](../../../feature-requests/done/041-pose-controls-and-read-back/README.md):
what is off rest, where the hands, feet, hips and head are, the switches, and
whether a limb is stretched or out of reach. It is what an agent calls after
every pose change instead of a screenshot, so it is held to the line
``mpfb_get_character_summary`` holds - about 8 KB - and its description is
short: the frame, the body parts and the roles are ``mpfb_get_pose_controls``'
and are only pointed at here.

``body_parts`` is the same argument as ``mpfb_get_pose_controls``', validated
the same way, by :func:`arguments.validated_body_parts`. Everything about what
the answer holds is decided and tested in
``bridge/mpfb_bridge/commands/get_pose.py`` and ``shared/pose_reading.py``.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get Pose",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_pose(name: str | None = None,
                      body_parts: list[str] | None = None) -> dict[str, object]:
        """
        Read a MakeHuman character's current pose - call it after every pose
        change instead of looking. Positions, the character frame, `body_parts`
        and the roles are as `mpfb_get_pose_controls` describes. Changes
        nothing. `result` holds:

        - `at_rest`: true when nothing is posed, in any body part.
          `counts_by_body_part` counts posed controls in every part.
        - `posed`: per body part, each control off rest by location,
          rotation **or scale** (a Rigify fist scales its finger masters):
          `bone`, `role`, `head` (where it is now - pass it back as a
          position), `moved_by` (from rest), `rotation` (`axis` and `degrees`
          from rest, including what its parents did) and `scale` in the
          bone's own axes, or `null`.
        - `switch_values` and `switch_parents`: each switch's value, and the
          parent a parent switch selects, by body part.
        - `landmarks`: `hips`, `head`, `left_hand`, `right_hand`, `left_foot`,
          `right_foot`, `now` and at `rest`, measured on the deforming bones:
          where the body is, not where a control sits.
        - `limbs`: per arm and leg, `in_charge` (`ik`, `fk` or `blend`),
          `length` and `rest_length`, `stretched` (longer than at rest),
          `reach_ratio` (above 1.0 the IK control is beyond a straight limb)
          and `target_unreachable`. These are derived; `limb_measures` says
          how. A limb Rigify's `IK_Stretch` lets grow shows as `stretched`.

        A rig that is not classified gets `posed_bones` instead, and no
        landmarks, limbs or switches (`null`).
        """
        return backend.send(
            "get_pose",
            params={
                "name": arguments.validated_subject(name),
                "body_parts": arguments.validated_body_parts(body_parts),
            },
        )
