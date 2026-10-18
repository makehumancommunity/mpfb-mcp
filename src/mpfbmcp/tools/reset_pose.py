"""
The ``mpfb_reset_pose`` tool: put a character back at rest, and answer with the way back.

The undo of [FR 042](../../../feature-requests/done/042-posing-bones-switches-and-reset/README.md):
Blender's undo stack does not record a bridge command's writes, so this and the
``restore_with`` it answers with are how a pose change is undone across the
socket.

``body_parts`` is the posing tools' argument, validated by
:func:`arguments.validated_body_parts`, but its default is **every** part, the
face included - unlike the readers'. ``include_switches`` is a real ``bool``.
Everything the answer holds is decided and tested in
``bridge/mpfb_bridge/commands/reset_pose.py``.
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
            title="Reset Pose",
            readOnlyHint=False,
            # It destroys a pose it did not create; restore_with is the way back.
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_reset_pose(name: str | None = None,
                        body_parts: list[str] | None = None,
                        include_switches: bool = False) -> dict[str, object]:
        """
        Put a MakeHuman character's pose controls back at rest - by body part,
        or all of them. `body_parts` defaults to **every part, face
        included** (a reset that left the face posed would not be one); on a
        rig `mpfb_get_pose_controls` does not classify, omit it and every bone
        is reset. `include_switches: true` also returns those parts' Rigify
        switches to their defaults.

        **`result`'s `restore_with` is the way back**: the arguments for
        `mpfb_set_pose_switches` (when switches were reset; send it first) and
        `mpfb_set_pose_bones` that put back exactly what this reset, keyed by
        tool name. It is empty when the character was already at rest.
        `not_restorable` names reset bones those tools would refuse, none of
        which moved the body - a chain `IK_FK` had handed away, for one.

        `bones_reset`, `switches_reset` (`previous_value`/`new_value`),
        `left_off_rest` (bones that are not controls, still posed by
        something else), and `landmarks`/`limbs` as in `mpfb_set_pose_bones`.
        """
        return backend.send(
            "reset_pose",
            params={
                "name": arguments.validated_subject(name),
                "body_parts": arguments.validated_body_parts(body_parts),
                # Not truthiness: include_switches="false" would reset them.
                "include_switches": arguments.validated_flag(include_switches,
                                                             "include_switches"),
            },
        )
