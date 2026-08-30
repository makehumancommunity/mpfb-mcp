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
([architecture.md](../../specifications/architecture.md#never-import-mpfb-submodules-directly)),
with a UI operator module the worst case of it. Both are reimplemented from
services in the payload, the way FR 006 and FR 008 reimplement the modeling
panels, and the payload says so.

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

from mpfbmcp import codegen
from mpfbmcp.connection import send_code


def _validated_name(name: object) -> str:
    """Shape only. Whether the name is an equipped asset is answered in Blender."""
    if not isinstance(name, str):
        raise ValueError("name must be a string, got {!r}".format(name))
    if not name.strip():
        raise ValueError(
            "name must be the Blender object name of the asset whose material should change, as "
            "mpfb_list_objects or mpfb_add_asset reports it. It is required: this tool destroys "
            "that object's material, so it will not act on whatever happens to be active.")
    return name


def _validated_optional_text(value: object, argument: str, hint: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            "{:s} must be a string or omitted, got {!r}".format(argument, value))
    if not value.strip():
        raise ValueError("{:s} must not be empty or whitespace; {:s}".format(argument, hint))
    return value


def _validated_flag(argument: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("{:s} must be a bool, got {!r}".format(argument, value))
    return value


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
    checked_path = _validated_optional_text(
        path, "path", "pass mpfb_list_asset_materials' 'path', or use 'fragment' instead")
    checked_fragment = _validated_optional_text(
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

        `name` is **required** and is the **asset's** own Blender object name, as
        `mpfb_list_objects` reports it or as `mpfb_add_asset` returned it in
        `asset_object_name` - not the character's. There is no active-object
        fallback: this destroys that object's current material.

        Name the material with **either** `path` **or** `fragment`, never both;
        both are reported for every entry by `mpfb_list_asset_materials`, which
        is the catalogue this tool consumes and the only place those files are
        listed - alternative materials are *not* part of `mpfb_list_assets`'
        answer, because they do not live in an asset library section. They sit in
        the asset's own directory.

        `restore_default` (default false) instead puts back the material named by
        the asset's own MHCLO and clears the recorded `alternative_material`. It
        cannot be combined with `path` or `fragment`.

        **What this reproduces is a UI operator, not a service function.** MPFB
        has no service-level "set an alternative material"; the logic exists only
        in its asset library panel, and this payload reimplements it from
        services rather than importing it. Two of its quirks are reproduced
        deliberately rather than tidied up, because tidying them would make the
        result differ from what the panel produces: the new material is **always
        a MakeSkin material named `makeskinmaterial`**, whatever kind the asset
        had before, and the slots are popped rather than deleted, so node groups
        from the previous material survive.

        The object's viewport display colour is taken from MPFB's per-type table,
        keyed on the asset's `object_type` - so an asset mislabelled when it was
        equipped gets the wrong colour here too. `diffuse_color_from` reports
        which type was used, and is `null` when the type was not in the table and
        the neutral grey fallback applied.

        Returns blender_mcp's response envelope. On `status: "ok"` and
        `applied: true`, `result` carries `asset_object_name`, `object_type`,
        `asset_subdir`, `resolved_by`/`resolved_path`, `alternative_material`
        (the fragment now recorded on the object - empty when the default was
        restored) beside `previous_alternative_material`, `materials_destroyed`,
        `material_name` and `diffuse_color_from`.

        Six situations answer with `applied: false` and a `blocked_by` naming
        which, rather than failing: no object by that name (`not_found`); the
        object carries no MPFB `object_type` (`not_an_mpfb_object`); it is a
        `Basemesh`, `Proxymeshes` or `Skeleton` (`type_not_supported` - MPFB's
        own panel refuses all three, and the first two have a skin rather than an
        asset material, which is `mpfb_set_skin`'s job); `restore_default` on an
        object that records no `asset_source`, so its own MHCLO cannot be found
        (`asset_source_missing`); the default material cannot be resolved, either
        because the MHCLO names none or because the file it names is not on disk
        (`default_material_not_found`); and the requested file does not exist
        (`material_not_found`). Edit mode answers with `not_object_mode`.
        """
        checked_restore = _validated_flag("restore_default", restore_default)
        checked_path, checked_fragment = _validated_request(
            path, fragment, checked_restore)
        code = codegen.assemble(
            "set_asset_material.py",
            bootstrap="raising",
            params={
                "name": _validated_name(name),
                "path": checked_path,
                "fragment": checked_fragment,
                "restore_default": checked_restore,
            },
        )
        # `result` (built in codegen/payloads/set_asset_material.py) is plain
        # JSON-safe data, so strict_json=True surfaces a clear error if that ever
        # stops being true.
        return send_code(code, strict_json=True)
