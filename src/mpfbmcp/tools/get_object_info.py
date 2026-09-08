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
        subject is a normal answer: `found` is false and `message` says whether
        no such object exists or nothing is active.

        `result` always carries `found`, `resolved_from` ("name" or
        "active_object") and `message`. When `found` is true it also carries:

          - `name`: the resolved object's name. Carry this forward rather than
            re-deriving from the active object, which changes as the user
            clicks.
          - `in_current_scene`: object names are unique across the whole
            .blend, so a name can resolve to an object `mpfb_list_objects` does
            not list. False here is not a contradiction between the two tools.
          - `object_type` (MPFB's type, or null for a plain Blender object),
            `blender_type`, `is_makehuman_object`.
          - `rigify_role`: "generated_rig", "metarig", or null - reported
            whatever the object's type, because MPFB tags the rig it generates
            through Rigify as a `Skeleton`.
          - `asset_info`: what the object was made from, or null when it has no
            MPFB type. **Its keys depend on the object type** - a skeleton has
            no mhclo, so it has no `mhclo_path` key rather than a null one.
            `Skeleton`/`Subrig` carry `rig_type` and `rig_definition_path`; a
            mesh asset (`Clothes`, `Eyes`, `Hair`, `Proxymeshes`, ...) carries
            `asset_source`, `mhclo_path`, `material_type`, `material_source`
            and `mhmat_path`; a `Basemesh` carries the last three. An
            unrecognized MakeHuman type gets an empty dict.
          - `related_objects`: the MakeHuman objects among this one's parents,
            children and siblings - "what belongs with this character" - each
            with the same fields plus its own `asset_info`, excluding the
            subject. A flat list, not a tree; call this tool again on a name to
            walk the structure.
          - `other_related_objects`: relatives carrying no MPFB type, each with
            a `rigify_role`. This is where a Rigify rig built outside MPFB
            shows up: it drives the character but appears in no other list this
            server returns.

        Reading `asset_info` correctly: every `*_path` is an absolute path or
        null, while the `*_source` fields beside them are MPFB's short
        fragments and are **not** paths. The pair keeps two situations apart -
        a null fragment means nothing was recorded, a fragment with a null path
        means the asset is recorded but is not installed under any asset root
        this Blender can see. A null `material_source` on a mesh asset is
        ordinary: the object uses the default material named inside its mhclo,
        deliberately not resolved here. `rig_type` and `material_type` are
        identified from the object as it is now, while the `*_source` fragments
        record what was loaded and are never rewritten when the object is
        edited by hand; where they disagree, the identified value describes
        reality. And `mhclo_path` may point at a `.proxy` file, so do not
        decide what something is from the suffix.
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
