"""
The ``mpfb_set_asset_material`` tool: swap an equipped asset's material.

A hat in three colours is one mesh and three MHMATs sitting beside it. MPFB lets
the user pick between them from its alternative-material panel, and put the
asset's own back afterwards. Nothing in mpfb-mcp could do either: a garment came
with whatever material its MHCLO named at the moment ``mpfb_add_asset`` equipped
it, and stayed with it.

**There is no service function behind this one.** The mechanism lives entirely
in ``mpfb/ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py``, as two
module-level helpers - ``_apply_mhmat()`` and ``_find_default_material()`` - and
importing an MPFB submodule is forbidden
([architecture.md](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)),
with a UI operator module the worst case of it. Both are reimplemented from
services in the command, the way FR 006 and FR 008 reimplement the modeling
panels, and the command says so.

``name`` is required and is the **asset's** own object name, not the character's.
Every other mutating tool here takes its subject from anywhere in the family and
falls back to whatever is active; this one destroys the named object's material,
and "whatever happens to be selected" is not an acceptable way to choose which
object loses its material. It is the same rule ``mpfb_remove_asset`` follows for
the same reason.

The three object types this refuses - ``Basemesh``, ``Proxymeshes`` and
``Skeleton`` - are the three MPFB's own panel refuses. The first two have a
*skin* rather than an asset material, and that is ``mpfb_set_skin``'s job.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend


def _validated_request(
        path: object, fragment: object,
        restore_default: bool) -> tuple[str | None, str | None]:
    """Exactly one request: a named material, or the asset's own back.

    ``path`` and ``fragment`` are the two identifiers ``mpfb_list_asset_materials``
    reports per entry, and the exactly-one-of rule between them is the standing
    one. ``restore_default`` is a third, mutually exclusive request rather than a
    modifier of the other two: it names no file at all, because the file it wants
    is whatever the asset's own MHCLO points at.
    """
    checked_path = arguments.validated_text(
        path, "path", "pass mpfb_list_asset_materials' 'path', or use 'fragment' instead")
    checked_fragment = arguments.validated_text(
        fragment, "fragment", "pass mpfb_list_asset_materials' 'fragment', or use 'path'")
    if checked_path is not None and checked_fragment is not None:
        raise ValueError(
            "Give either path or fragment, not both. They can name different files, and "
            "silently preferring one would apply a material the caller did not ask for.")
    if restore_default and (checked_path is not None or checked_fragment is not None):
        raise ValueError(
            "restore_default puts back the material the asset's own MHCLO names, so it cannot "
            "be combined with path or fragment. Give one or the other.")
    if not restore_default and checked_path is None and checked_fragment is None:
        raise ValueError(
            "Give either path or fragment - both are reported for every entry by "
            "mpfb_list_asset_materials - or pass restore_default=true to put back the material "
            "the asset's own MHCLO names.")
    return (checked_path, checked_fragment)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Asset Material",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_set_asset_material(
        name: str,
        path: str | None = None,
        fragment: str | None = None,
        restore_default: bool = False,
    ) -> dict[str, object]:
        """
        Replace the material on an equipped MHCLO asset with one of the
        alternatives that ship beside it - a hat in another colour - or put the
        asset's own material back.

        `name` is **required** and is the **asset's** own Blender object name,
        as `mpfb_list_objects` reports it or as `mpfb_add_asset` returned it in
        `asset_object_name` - not the character's. There is no active-object
        fallback: this destroys that object's current material.

        Name the material with **either** `path` **or** `fragment`, never both.
        Both come from `mpfb_list_asset_materials`, the only catalogue for
        them: alternative materials sit in the asset's own directory rather
        than in an asset library section, so `mpfb_list_assets` does not know
        about them.

        `restore_default` (default false) instead puts back the material named
        by the asset's own MHCLO and clears the recorded
        `alternative_material`. It cannot be combined with `path` or
        `fragment`.

        MPFB has no service-level "set an alternative material" - the logic
        exists only in its asset library panel - and two of that panel's quirks
        are reproduced here rather than tidied up, because tidying them would
        make the result differ from what a user gets from the panel: the new
        material is **always a MakeSkin material named `makeskinmaterial`**,
        whatever the asset had before, and the slots are popped rather than
        deleted, so node groups from the previous material survive. The
        viewport display colour comes from MPFB's per-type table keyed on the
        asset's `object_type`, so an asset mislabelled when it was equipped
        gets the wrong colour here too; `diffuse_color_from` reports which type
        was used and is null when the neutral grey fallback applied.

        On `applied: true`, `result` carries `asset_object_name`,
        `object_type`, `asset_subdir`, `path_resolved_by`/`resolved_path`,
        `alternative_material` (the fragment now recorded on the object, empty
        when the default was restored) beside `alternative_material_before`,
        `materials_destroyed`, `material_name` and `diffuse_color_from`.

        Refusals come back as `applied: false` (and so `performed: false`) with
        a `blocked_by` and a sentence: `subject_not_found`, `not_an_mpfb_object`,
        `material_not_found`, `not_object_mode`, `asset_source_missing` and
        `default_material_not_found` (both for `restore_default` on an asset
        whose own MHCLO cannot be found or names no material on disk), and
        `type_not_supported` for a `Basemesh`, `Proxymeshes` or `Skeleton` -
        MPFB's own panel refuses all three, and the first two have a skin
        rather than an asset material, which is `mpfb_set_skin`'s job.
        """
        checked_restore = arguments.validated_flag(restore_default, "restore_default")
        checked_path, checked_fragment = _validated_request(
            path, fragment, checked_restore)
        # `result` (built in bridge/mpfb_bridge/commands/set_asset_material.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "set_asset_material",
            params={
                "name": arguments.validated_asset_name(
                    name, what="the asset whose material should change",
                    because=("It is required: this tool destroys that object's material, so it "
                             "will not act on whatever happens to be active.")),
                "path": checked_path,
                "fragment": checked_fragment,
                "restore_default": checked_restore,
            },
        )
