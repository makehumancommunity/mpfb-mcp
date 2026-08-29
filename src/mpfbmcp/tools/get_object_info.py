"""
The ``mpfb_get_object_info`` tool: identifies one object and what belongs to it.

Two things make this more than a type lookup. It resolves the *active* object
when given no name, which is what a user pointing at something on screen and
asking "what is this" means, and which is how MPFB's own UI panels work
throughout. And it reports what each object was made from, so a caller can ask
"which shirt is that" rather than only "is that a Clothes item".

Like ``mpfb_get_status``, failing to find a subject is a successful answer here
rather than an error envelope: an agent guessing at a name needs a "no" it can
recover from. The classification lives in the generated code (see
``mpfbmcp.codegen.payloads.get_object_info``); this module only validates.
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
        # An explicitly empty name is a caller error, not a request for the
        # active object. The two come from different mistakes, and quietly
        # answering about whatever happens to be selected, when the caller
        # believed they had named something, is worse than failing here.
        raise ValueError(
            "name must not be empty or whitespace; omit it to use the active object")
    return name


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get MakeHuman Object Info",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_get_object_info(name: str | None = None) -> dict[str, object]:
        """
        Identify one Blender object, say what MakeHuman asset it was made from,
        and list what else belongs with it. Changes nothing, selects nothing.

        `name` is a Blender object name, typically one from
        `mpfb_list_objects`. **Omit it to ask about the currently active
        object** - what the user just created or clicked. Not resolving a
        subject is a normal answer, not an error: `found` is false, and
        `message` says whether no such object exists or nothing is active.

        Returns blender_mcp's response envelope. On `status: "ok"`, `result`
        always carries `found`, `resolved_from` ("name" or "active_object") and
        `message`. When `found` is true it also carries:

          - `name`: the resolved object's name. This is the point of the
            active-object form - carry this forward to later tools rather than
            re-deriving from the active object, which changes as the user
            clicks.
          - `in_current_scene`: object names are unique across the whole .blend,
            so a name can resolve to an object `mpfb_list_objects` does not
            list. False here is not a contradiction between the two tools.
          - `object_type` (MPFB's type, or null for a plain Blender object),
            `blender_type`, `is_makehuman_object`.
          - `asset_info`: what the object was made from, or null when it has no
            MPFB type. **Its keys depend on the object type** - a skeleton has
            no mhclo, so it has no `mhclo_path` key rather than a null one:
            - `Skeleton`/`Subrig`: `rig_type`, `rig_definition_path`.
            - mesh assets (`Clothes`, `Eyes`, `Hair`, `Proxymeshes`, ...):
              `asset_source`, `mhclo_path`, `material_type`, `material_source`,
              `mhmat_path`.
            - `Basemesh`: `material_type`, `material_source`, `mhmat_path`.
            An unrecognized MakeHuman type gets an empty dict.
          - `related_objects`: the MakeHuman objects among this one's parents,
            children and siblings - "what belongs with this character" - each
            with the same fields plus its own `asset_info`, excluding the
            subject. A flat list, not a tree; call this tool again on a name to
            walk the structure.
          - `other_related_objects`: relatives carrying no MPFB type, each with
            a `rigify_role` of "generated_rig", "metarig" or null. MPFB does not
            tag Rigify's generated rig, so without this a Rigify-driven
            character would report no rig while one is plainly attached.

        Reading `asset_info` correctly:

          - Every `*_path` is an absolute path or null; the `*_source` fields
            beside them are MPFB's short fragments ("fedora/fedora.mhclo") and
            are **not** paths - do not pass one to a file-opening tool. The
            pairing is also how two different situations stay apart: a null
            fragment means nothing was recorded, while a fragment with a null
            path means the asset is recorded but is not installed under any
            asset root this Blender can see.
          - A null `material_source` on a mesh asset is the ordinary case and
            means the object uses the default material named inside its mhclo -
            not that the material is unknown. That default is deliberately not
            resolved here; derive it from `mhclo_path` if you need it.
          - `rig_type` and `material_type` are identified from the object as it
            is now (bone names, material nodes); the `*_source` fragments record
            what was *loaded*, and nothing rewrites them if the object is later
            edited by hand. Where the two disagree, the identified value
            describes reality. Both are heuristics, not authorities.
          - `mhclo_path` may point at a file with a `.proxy` extension rather
            than `.mhclo`; do not match on the suffix to decide what it is.

        The result describes one scene at one moment and is not cacheable - the
        active-object form especially, since its subject changes when the user
        clicks elsewhere in the viewport.
        """
        # `result` (built in codegen/payloads/get_object_info.py) is always
        # plain JSON-safe data, so strict_json=True to surface a clear error if
        # that ever stops being true, rather than silently falling back to
        # `repr`.
        code = codegen.assemble(
            "get_object_info.py",
            bootstrap="raising",
            params={"name": _validated_name(name)},
        )
        return send_code(code, strict_json=True)
