"""
The ``mpfb_store_rig`` tool: an authored rig into the user library, found as itself.

The last of [FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)'s rig authoring
steps, and the sixth tool to write outside the ``.blend``: ``rigs/<rig_name>.json`` and
``rigs/weights.<rig_name>.json`` in MPFB's user data, as MakeRig's "Save rig to library" writes
them. The first refusal in this package that is about **identification** rather than about a
name: MPFB finds a custom rig by its identifying bones, after every built-in rule and in
directory order, so a rig that could be identified as something else is refused before
anything is written.

**Validated here**: ``rig_name`` by MPFB's own rule, through ``artifact_names``, whose bridge
copy is the last statement before ``open()`` and which ``tests/test_store_rig.py`` holds to this
one over one table of names; ``identifying_bones`` an optional non-empty list of distinct names;
four real bools. **No bone or rig vocabulary is checked here.**
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import artifact_names
from mpfbmcp import backend


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Store Rig",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_store_rig(
        rig_name: str,
        name: str | None = None,
        include_weights: bool = True,
        identifying_bones: list[str] | None = None,
        include_masks: bool = False,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> dict[str, object]:
        """
        Store a character's rig in the user library as `custom.<rig_name>`, after
        `mpfb_create_rig` and `mpfb_weight_rig`. **Writes files, with no undo.** Then try it
        on a different body with `try_with`: `mpfb_create_human`, then `mpfb_add_rig` with
        the identifier.

        `rig_name` is a name, never a path: letters, digits and `_`. Writes
        `rigs/<rig_name>.json` and, unless `include_weights` is false,
        `rigs/weights.<rig_name>.json` in MPFB's user data, as one artifact; `path` is on
        every answer. `overwrite` is false by default; `dry_run` settles everything and
        writes nothing.

        MPFB identifies a custom rig by `identifying_bones`, only after no built-in rig
        matched, taking the first custom rig in directory order. Left out, the smallest set
        of this rig's bones that no other rig holds is picked. **A rig that would not be
        found as itself is refused**: `identified_as_builtin`, `identification_shadowed`
        (`shadowed_by`: another rig's identifying bones are all in this one),
        `would_shadow` (this one's are all in another), and `name_shadowed` (the name in
        another data root).

        **Masks are left out as MPFB's panel leaves them**; `include_masks` writes the
        body's `mhmask-*` groups, and `masks_on_body`/`masks_written` say which. What the
        round trip loses is named: `deform_flags_lost` (non-deforming bones come back
        deforming: MPFB's format has no such flag), `features_not_carried`,
        `unweighted_bones`, and `ends_rematched` (an end whose strategy MPFB's save changed,
        as a fixed position becomes a vertex or a mean).

        On `stored: true`, `result` also has `identifying_bones` with
        `identifying_bones_chosen_by`, `identified_as_after`, `overwrote` and `file_before`.
        Other refusals: `subject_not_found`, `invalid_name`, `not_rigged`,
        `unknown_bone_names`, `not_object_mode`, `rig_exists` with `file_before`,
        `no_identifying_bones`, `no_armature_context`, `write_failed`.
        """
        return backend.send(
            "store_rig",
            params={
                "name": arguments.validated_subject(name),
                "rig_name": artifact_names.validated_rig_name(rig_name),
                "include_weights": arguments.validated_flag(include_weights, "include_weights"),
                "identifying_bones": arguments.validated_names(
                    identifying_bones, "identifying_bones", "a set picked for you"),
                "include_masks": arguments.validated_flag(include_masks, "include_masks"),
                "overwrite": arguments.validated_flag(overwrite, "overwrite"),
                "dry_run": arguments.validated_flag(dry_run, "dry_run"),
            },
        )
