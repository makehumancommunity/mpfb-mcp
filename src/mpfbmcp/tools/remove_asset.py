"""
The ``mpfb_remove_asset`` tool: take an MHCLO asset off a character properly.

The counterpart to ``mpfb_add_asset``, and it exists for the same reason that
tool does: an agent that equips the wrong garment has to be able to undo it, and
deleting the object in Blender is *not* undoing it. MPFB masks
the body under the garment with a MASK modifier pointing at a ``Delete.<name>``
vertex group on the basemesh and, when the character has a body proxy, on that
too; a garment may also have brought a sub-rig of its own. A plain object delete
leaves all of that behind - a character with a hole in it and no visible cause.

``HumanService.unload_mhclo_asset()`` is the operation that does it properly,
and this tool is a thin wrapper over it plus the reporting it has none of.

``name`` is required rather than defaulting to the active object. Every other
mutating tool here takes its subject from anywhere in the character's family and
falls back to whatever is active; this one deletes an object, and "whatever
happens to be selected" is not an acceptable way to choose which.
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
            title="Remove Mesh Asset",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_remove_asset(name: str) -> dict[str, object]:
        """
        Take one MHCLO asset - a garment, a body part or a topology proxy - off
        a MakeHuman character and clean up after it, the way MPFB's own
        "unload" does.

        **Use this rather than deleting the object.** MPFB hides the body under
        a garment with a mask modifier on the basemesh (and on the body proxy,
        for clothes), and a garment may have brought a sub-rig of its own.
        Deleting the object with a generic Blender tool leaves both behind, and
        the character keeps a hole in it with nothing visible to explain it.

        `name` is **required** and is the asset object's own Blender name, as
        `mpfb_list_objects` reports it or as `mpfb_add_asset` returned it in
        `asset_object_name`. There is no active-object fallback: this deletes
        an object. Equipping two copies of one asset gives `...hat` and
        `...hat.001`, so check which you are naming. **This is not undoable
        across the socket**: the object and its mesh data are gone when the
        call returns.

        On `removed: true`, `result` carries `asset_object_name`, `object_type`
        and `asset_source` - all read *before* the deletion - plus
        `basemesh_name`, `objects_removed` naming everything the call deleted,
        `mask_modifiers_removed` naming the objects and modifiers that went,
        `subrig_removed`, and two things MPFB leaves behind and never mentions:
        `vertex_groups_left_behind` (the `Delete.<name>` groups themselves;
        only the modifiers referencing them are removed) and
        `mesh_data_orphaned` (the mesh datablock, which keeps no users until
        the file is saved and reloaded). Both are harmless and both are
        invisible unless reported.

        Refusals come back as `removed: false` (and so `performed: false`) with
        a `blocked_by` and a sentence: `subject_not_found`, `basemesh_not_found`,
        `not_object_mode`, `asset_source_missing` - without it the mask
        modifier cannot be identified and removal would be silently partial -
        and `not_a_mesh_asset`, which refuses a basemesh or a skeleton
        outright, because the underlying MPFB function would happily delete
        either.
        """
        # `result` (built in bridge/mpfb_bridge/commands/remove_asset.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "remove_asset",
            params={
                "name": arguments.validated_asset_name(
                    name, what="the asset to remove",
                    because=("It is required: this tool deletes an object, so it will not act "
                             "on whatever happens to be active.")),
            },
        )
