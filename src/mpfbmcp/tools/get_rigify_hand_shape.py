"""
The ``mpfb_get_rigify_hand_shape`` tool: each hand of a generated Rigify rig, as a curl and a spread per finger.

The reader half of [FR 047](../../../feature-requests/done/047-rigify-hand-shapes/README.md).
Each finger comes back in exactly the shape ``mpfb_set_rigify_hand_shape``
takes, so a read-back is a write, beside the joint angles and fingertip
measured on the deforming bones. **The name says Rigify** because the tool
cannot work on any other rig, and a caller that picks a tool by its name should
not reach for this one on a default rig.

``body_parts`` is validated by :func:`arguments.validated_body_parts`, as every
posing tool's is; which names are hands is the bridge's answer
(``unknown_body_parts``). Everything about what the answer holds is decided and
tested in ``bridge/mpfb_bridge/commands/get_rigify_hand_shape.py`` and
``shared/rigify_hands.py``.
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
            title="Get Rigify Hand Shape",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_rigify_hand_shape(name: str | None = None,
                                   body_parts: list[str] | None = None) -> dict[str, object]:
        """
        Read the hands of a character rigged with a rig generated from MPFB's
        Rigify meta-rigs: per finger (`thumb`, `index`, `middle`, `ring`,
        `pinky`) the `curl` and `spread` `mpfb_set_rigify_hand_shape` takes,
        so a read-back can be sent back. `body_parts`: `left_hand`,
        `right_hand`, default both. Changes nothing; any other rig is refused
        (`rig_not_supported`).

        `result`'s `hands`, per finger, beside the amounts: `joint_degrees`
        (each joint's bend from rest, first knuckle first) and
        `spread_degrees`, measured on the deforming bones, and `tip`, the
        fingertip in the character frame.
        A finger posed some other way - a bent segment, a hook, a twist - is
        `expressible: false` with `not_expressible_because`, and its amounts
        are then a fit. Per hand, `matches_shape` names the shape it is in,
        or null. `known_shapes` lists every shape's amounts.
        """
        return backend.send(
            "get_rigify_hand_shape",
            params={
                "name": arguments.validated_subject(name),
                "body_parts": arguments.validated_body_parts(body_parts),
            },
        )
