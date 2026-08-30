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

from mpfbmcp import codegen
from mpfbmcp.connection import send_code


def _validated_name(name: object) -> str | None:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValueError("name must be a string or omitted, got {!r}".format(name))
    if not name.strip():
        raise ValueError(
            "name must not be empty or whitespace; omit it to use the active object")
    return name


def _validated_identifier(identifier: object) -> str:
    """Shape only. The vocabulary lives in Blender's rig directories."""
    if not isinstance(identifier, str):
        raise ValueError("identifier must be a string, got {!r}".format(identifier))
    if not identifier.strip():
        raise ValueError(
            "identifier must name a rig; call mpfb_list_rigs and pass an entry's 'identifier'")
    return identifier


def _validated_flag(argument: str, value: object) -> bool:
    if not isinstance(value, bool):
        # Deliberately not truthiness: "false" and 0 are how a caller signals a
        # bool it did not manage to build, and import_weights="false" would
        # otherwise add a rig the character is parented to but not deformed by.
        raise ValueError("{:s} must be a bool, got {!r}".format(argument, value))
    return value


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
        Attach a rig to an existing MakeHuman character, with the same result
        MPFB's own "Add standard rig" / "Add rigify rig" / "Add custom rig"
        buttons produce.

        **Rig the character before dressing it.** MPFB rigs a garment only if a
        rig is present at the moment the garment is attached, and nothing rigs
        it retroactively - not `mpfb_refit_human` either. This tool does not
        refuse to rig a dressed character, because decorative clothes are a
        legitimate thing to have, but it reports every asset it just failed to
        rig in `mesh_assets_not_rigged`. Treat a non-empty list as a mistake
        unless you meant it.

        `identifier` is exactly what `mpfb_list_rigs` reports in its
        `identifier` field, never the `name` beside it and never a filename: a
        bare name for a standard rig (`"default_no_toes"`), `"rigify.human"` for
        a Rigify one, `"custom.my_rig"` for a user one. The prefix is what
        selects which of MPFB's two non-interchangeable adding functions runs,
        and this tool dispatches on it - `add_function_used` in the response
        says which was taken, so you can see the identifier was read the way you
        meant it.

        `name` is any object in the character's family - the basemesh, a
        garment, anything `mpfb_list_objects` reports. Omit it to use the active
        object. The basemesh is resolved from it and `basemesh_name` names the
        object that was actually rigged.

        `import_weights` (default true, MPFB's own) loads the vertex weights and
        adds the armature modifier. With it false the mesh is parented to the
        armature but not deformed by it.

        **A `rigify.*` identifier produces a meta rig, not a finished rig.**
        `is_metarig: true` comes back with a `next_step`: attach the clothes
        first, then call `mpfb_generate_rigify_rig`. A meta rig deforms nothing
        on its own.

        Returns blender_mcp's response envelope. On `status: "ok"` and
        `added: true`, `result` carries `rig_object_name` (read off the created
        object, since Blender uniquifies a name already in use),
        `add_function_used` and `family`, `is_metarig`/`next_step`,
        `weights_loaded` with `weights_from` and `weights_path` - **MPFB
        resolves weights through a fallback table, so a rig legitimately
        borrowing another's is normal and `weights_loaded: false` is not** -
        `armature_modifier_added`, `basemesh_location_before` with
        `basemesh_moved_to_origin` and `rig_location` (both adding functions
        move the basemesh to the origin and give the armature its old location,
        which visibly moves a character standing anywhere else), and
        `mesh_assets_not_rigged` / `subrigs_not_rigged`.

        Five situations answer with `added: false` and a `blocked_by` naming
        which, rather than failing: the subject resolves to no basemesh
        (`subject_not_found`); the identifier names no rig
        (`unknown_identifier`, with `known_identifiers` for the family you
        addressed); the character **already has a rig** (`already_rigged` - MPFB
        cannot swap one, so delete the existing rig first); a `rigify.*`
        identifier with Rigify not enabled (`rigify_unavailable`); and anything
        not in OBJECT mode (`not_object_mode`).
        """
        code = codegen.assemble(
            "add_rig.py",
            bootstrap="raising",
            params={
                "name": _validated_name(name),
                "identifier": _validated_identifier(identifier),
                "import_weights": _validated_flag("import_weights", import_weights),
            },
            # Shared with mpfb_list_rigs' payload, which predicts what this tool
            # then does. One implementation of "which file, whose weights", so
            # the catalogue and the action cannot disagree.
            shared=["rig_lookup.py"],
        )
        # `result` (built in codegen/payloads/add_rig.py) is plain JSON-safe
        # data - locations are coerced to lists of float there - so
        # strict_json=True surfaces a clear error if that ever stops being true.
        return send_code(code, strict_json=True)
