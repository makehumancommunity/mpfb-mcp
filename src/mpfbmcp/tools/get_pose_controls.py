"""
The ``mpfb_get_pose_controls`` tool: which bones pose a character, and what each one does.

The first posing tool ([FR 041](../../../feature-requests/done/041-pose-controls-and-read-back/README.md)),
and read-only. An agent that has to pose a character with a generated Rigify
rig faces 1090 bones, of which a few dozen are the ones a person would grab;
this says which, grouped by body part, with each one's role and rest position.

**The shared posing vocabulary is explained here and only here** - the
character frame, the body parts and the roles - because this is the tool a
caller meets first. ``mpfb_get_pose`` and the writing tools that follow point
at this description rather than repeating it, which is how
[a concept several tools share](../../../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget)
is paid for once.

**``body_parts`` is validated for shape only**: a list of distinct, non-empty
strings, or omitted. Which names are body parts is answered inside Blender,
which lists them when one is not. Everything about what the answer holds - the
classification, the frame, the switches - is decided and tested in
``bridge/mpfb_bridge/shared/pose_controls.py`` and its bridge tests.
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
            title="Get Pose Controls",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_pose_controls(name: str | None = None,
                               body_parts: list[str] | None = None) -> dict[str, object]:
        """
        List the bones that pose a MakeHuman character: its rig's controls,
        grouped by body part. Call once per character before posing; check the
        pose afterwards with `mpfb_get_pose`. Changes nothing.

        **The character frame.** Every position and direction is in metres
        along `forward`, `left` (the character's own left, the `.L` side) and
        `up`, from the rig object's origin, so it does not change when the
        character is moved or turned. `character_frame` gives the origin and
        the three axes in world space.

        `body_parts`: any of `root`, `torso`, `head`, `face`, `left_arm`,
        `right_arm`, `left_hand`, `right_hand`, `left_leg`, `right_leg` (feet
        and toes belong to the leg). Omitted, every part **except `face`**,
        which must be named. `counts_by_body_part` always covers every part.

        In `result`, `controls` maps each body part to its controls: `bone` (the name to
        pass back), `role`, `chain` (`ik`/`fk` on a limb), `source` (`rigify`,
        `rig`, or `mpfb_helper` for an IK helper MPFB added), rest `head` and
        `direction`, `rotation_mode`, `locked` channels and
        `hidden_by_default` (Rigify's tweak and detail controls - start with
        the others). Roles: `ik_control` places a hand or foot, `pole` aims the
        elbow or knee, `fk` is rotated directly, `body` is Rigify's
        torso/hips/chest, `finger_master`/`toe_master` bend a whole digit,
        `switches` carries a limb's switches, `look_target` aims the eyes.

        `switches` (Rigify only): per body part, each custom property such as
        `IK_FK`, `IK_Stretch`, `pole_vector`, `IK_parent`, with `range`,
        `default`, `ends` (what each end means: `IK_FK` 0.0 is IK) and, for a
        parent switch, `parent_names` (the parent each integer selects).

        On a default rig, `helper_modes` reports MPFB's IK helpers and an FK
        bone a helper holds has `driven_by`: rotating it does nothing; move the
        helper. A rig that is not classified (`classified: false`) is listed
        as plain `bones` instead; `classified_rigs` says which are. Refusals:
        `rig_not_found`, `rigify_not_generated` (call
        `mpfb_generate_rigify_rig`), `unknown_body_parts`. A full answer for a
        generated Rigify rig is ~60 KB; name the body parts you will pose.
        """
        return backend.send(
            "get_pose_controls",
            params={
                "name": arguments.validated_subject(name),
                "body_parts": arguments.validated_body_parts(body_parts),
            },
        )
