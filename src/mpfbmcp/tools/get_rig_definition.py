"""
The ``mpfb_get_rig_definition`` tool: a rig, read as the bone table ``mpfb_create_rig`` takes.

The reader of [FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)'s four rig
authoring tools, there so that a shipped rig can be the starting point of an authored one and
so that **a read-back is a write**: every bone comes back in the builder's shape, each end with
its resolved ``position`` beside it, which the builder ignores next to another kind. The
translation lives once, in the bridge's ``shared/rig_definition.py``.

**Validated here is shape only**: ``rig`` is optional non-empty text, ``bone_names`` an optional
non-empty list of distinct names, the two flags real bools. **No rig or bone vocabulary is
checked here**: which rigs the catalogue holds and which bones a rig has are Blender's, answered
as ``unknown_identifier`` and ``unknown_bone_names``. The name filter is ``bone_names`` rather
than ``bones``, because ``bones`` is ``mpfb_create_rig``'s and ``mpfb_set_pose_bones``' list of
objects, and one argument name carrying two JSON types is what ``tests/test_vocabulary.py``
refuses.
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
            title="Get Rig Definition",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_rig_definition(
        name: str | None = None,
        rig: str | None = None,
        bone_names: list[str] | None = None,
        include_joints: bool = False,
        compact: bool = False,
    ) -> dict[str, object]:
        """
        Read a rig as the bone table `mpfb_create_rig` takes, so a shipped rig can start an
        authored one and **a read-back is a write**. Changes nothing.

        Without `rig`, reads the rig that moves the character; `definition_from` says from
        where: `"armature"` (strategies saved on the bones, as `mpfb_create_rig` builds),
        `"catalogue"` (its catalogue file, fitted to this body) or `"armature_positions"`
        (neither, so every end is a fixed position). With `rig`, an `mpfb_list_rigs`
        identifier, that file is fitted to this body in memory; the character need not
        have a rig.

        Each of `bones` is `name`, `parent` (`""` for none), `head`, `tail`, `roll`,
        `deform`, `connect`, `collections`. An end is one of `{"joint": name}`,
        `{"vertex": i}`, `{"mean": [i, j, ...]}` or `{"position": {forward, left, up},
        "snap": false}` (a fixed position), with an optional `offset`, and carries its
        `position` in the character frame. `roll` is `"align_z_world_z"`,
        `"align_x_world_x"` or `{"degrees": d}`. An end or roll MPFB has no table form for
        (a Rigify heel) says `expressible: false`. `features_not_carried` names, per bone
        that has any, what the builder would drop: constraints, bendy bones, Rigify types
        and parameters, inheritance, custom properties; `rig_features_not_carried` the
        rig-level ones.

        **The default rig is 163 bones and 53 KB.** `compact` drops each non-position end's
        `position`, `features_not_carried` and keys at the builder's default (24 KB);
        `bone_names` narrows. `include_joints` adds `joints`, every joint cube's centre in
        the frame as MPFB evaluates it when fitting: the names a `joint` end takes.

        `result` also has `rig_object_name`, `rig_identified_as`, `definition_path`,
        `version`, `bone_count` and `character_frame`. Refusals: `subject_not_found`,
        `not_rigged` (no rig and no `rig`), `unknown_identifier`, `unknown_bone_names`.
        """
        return backend.send(
            "get_rig_definition",
            params={
                "name": arguments.validated_subject(name),
                "rig": arguments.validated_text(
                    rig, "rig", "omit it to read the rig that moves the character"),
                "bone_names": arguments.validated_names(bone_names, "bone_names", "every bone"),
                "include_joints": arguments.validated_flag(include_joints, "include_joints"),
                "compact": arguments.validated_flag(compact, "compact"),
            },
        )
