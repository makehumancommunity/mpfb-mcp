"""
The ``mpfb_add_rig`` tool: attach a rig to a character that already exists.

The acting counterpart to ``mpfb_list_rigs``, which has named every addable rig
since FR 004 while nothing could add one. Until this tool, every character
mpfb-mcp produced was a static mesh.

Its real subject is an **ordering constraint that produces no error**.
``HumanService.add_mhclo_asset()`` rigs a garment only if a ``Skeleton``
relative exists at the moment the garment is attached, and nothing re-rigs it
afterwards - ``HumanService.refit()`` deliberately passes ``set_parent=False``.
So "dress the character, then rig it" produces clothes that do not follow the
armature, silently, and the mistake is only discovered when someone moves a
bone. No single call can enforce the order, but this one can *see* it being
broken, and reporting that is the cheapest form of preventing it.

Rigify turns that into three steps rather than two: ``add_builtin_rig()`` on a
``rigify.*`` identifier produces only a **meta rig**, and generation has to run
after the clothes. That is why generation is a tool of its own
(``mpfb_generate_rigify_rig``) rather than a flag here - a flag would make the
correct order impossible to express.

Nothing about the rig vocabulary is validated on this side of the socket: which
rigs exist is a directory listing inside Blender, and a list kept here would
drift from it. What is validated here is shape, and one thing more - the
``import_weights`` flag has to be a real bool, because ``import_weights="false"``
would otherwise be truthy and produce a rigged character that never deforms.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend


def _validated_identifier(identifier: object) -> str:
    """Shape only. The vocabulary lives in Blender's rig directories."""
    if not isinstance(identifier, str):
        raise ValueError("identifier must be a string, got {!r}".format(identifier))
    if not identifier.strip():
        raise ValueError(
            "identifier must name a rig; call mpfb_list_rigs and pass an entry's 'identifier'")
    return identifier


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Add Rig",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_add_rig(
        name: str | None = None,
        identifier: str = "",
        import_weights: bool = True,
    ) -> dict[str, object]:
        """
        Attach a rig to an existing MakeHuman character - MPFB's "Add standard
        rig" / "Add rigify rig" / "Add custom rig".

        **Rig the character before dressing it.** MPFB rigs a garment only if a
        rig is present when the garment is attached, and nothing rigs it
        retroactively. This tool does not refuse to rig a dressed character -
        decorative clothes are legitimate - but `mesh_assets_not_rigged` names
        every asset it just failed to rig, and a non-empty list is a mistake
        unless you meant it.

        `identifier` is exactly what `mpfb_list_rigs` reports in its
        `identifier` field, never the `name` beside it and never a filename:
        `"default_no_toes"` for a standard rig, `"rigify.human"` for a Rigify
        one, `"custom.my_rig"` for a user one. The prefix selects which of
        MPFB's two non-interchangeable adding functions runs, and
        `add_function_used` says which was taken.

        `import_weights` (default true, MPFB's own) loads the vertex weights
        and adds the armature modifier. With it false the mesh is parented to
        the armature but not deformed by it.

        **A `rigify.*` identifier produces a meta rig, not a finished rig.**
        `is_metarig: true` comes back with a `next_step`: attach the clothes
        first, then call `mpfb_generate_rigify_rig`. A meta rig deforms nothing
        on its own.

        On `added: true`, `result` carries `rig_object_name` - read off the
        created object, since Blender uniquifies a name already in use, and the
        address other tools need for the rig - plus `basemesh_name`,
        `add_function_used`, `family`, `is_metarig`/`next_step`,
        `weights_loaded` with `weights_from` and `weights_path` (**MPFB
        resolves weights through a fallback table, so a rig legitimately
        borrowing another's is normal and `weights_loaded: false` is not**),
        `armature_modifier_added`, `basemesh_location_before` with
        `basemesh_moved_to_origin` and `rig_location` - both adding functions
        move the basemesh to the origin and give the armature its old location,
        which visibly moves a character standing anywhere else - and
        `mesh_assets_not_rigged` / `subrigs_not_rigged`.

        Refusals come back as `added: false` (and so `performed: false`) with a
        `blocked_by` and a sentence: `subject_not_found`, `unknown_identifier`
        (with `known_identifiers` for the family you addressed),
        `rigify_unavailable`, `not_object_mode`, and `already_rigged` - **MPFB
        cannot swap a rig**, so an existing one has to be deleted first.
        """
        # `result` (built in bridge/mpfb_bridge/commands/add_rig.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "add_rig",
            params={
                "name": arguments.validated_subject(name),
                "identifier": _validated_identifier(identifier),
                # Not truthiness: import_weights="false" would add a rig the character is parented
                # to but not deformed by.
                "import_weights": arguments.validated_flag(import_weights, "import_weights"),
            },
            # Shared with mpfb_list_rigs' command, which predicts what this tool
            # then does. One implementation of "which file, whose weights", so
            # the catalogue and the action cannot disagree.
        )
