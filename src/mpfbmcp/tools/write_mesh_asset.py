"""
The ``mpfb_write_mesh_asset`` tool: one checked mesh becomes a complete asset.

Writing an asset took ``bpy.ops.mpfb.write_makeclothes_clothes(filepath=...)`` with exactly the
basemesh and the garment selected, which leaves the selection cleared, reports only through
``self.report`` and can say ``{'ERROR'}`` and still return ``{'FINISHED'}``
([FR 050](../../../feature-requests/done/050-writing-mesh-assets/README.md)).

**It writes outside the ``.blend``**, so it owes
[what a save owes](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more):
a name and never a path, checked here by ``artifact_names`` under a rule of its own since the
panel would rewrite anything else, and ``overwrite`` false by default. ``destination`` is this
package's own word, so it is checked here too, and neither of its values is a path. ``object_type``,
``license`` and ``delete_group`` are vocabularies MPFB and the body hold, and are checked on the
far side. ``license``, ``author`` and ``description`` are one line of text, because an MHCLO and an
MHMAT are one key per line.

**There is no ``homepage``, tag or ``z_depth`` argument, because they would not reach the file.**
The command's docstring says why, and this tool's description says so to a caller holding a mesh
whose panel has them filled in.
"""

from __future__ import annotations

__all__ = (
    "DESTINATIONS",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import artifact_names
from mpfbmcp import backend

DESTINATIONS = ("library", "export_directory")


def _validated_destination(destination: object) -> str:
    if destination not in DESTINATIONS:
        raise ValueError("destination must be one of {}, got {!r}".format(
            ", ".join(DESTINATIONS), destination))
    return destination  # type: ignore[return-value]


def _validated_line(value: object, argument: str) -> str | None:
    checked = arguments.validated_text(value, argument, "omit it to take the object's")
    if checked is not None and ("\n" in checked or "\r" in checked):
        # An MHCLO is one key per line, so a line break would write a second key.
        raise ValueError("{} must be one line of text".format(argument))
    return checked


def _validated_optional_flag(value: object, argument: str) -> bool | None:
    return None if value is None else arguments.validated_flag(value, argument)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Write Mesh Asset",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_write_mesh_asset(
        asset_name: str,
        name: str | None = None,
        basemesh: str | None = None,
        object_type: str | None = None,
        destination: str = "library",
        overwrite: bool = False,
        dry_run: bool = False,
        license: str | None = None,  # pylint: disable=redefined-builtin
        author: str | None = None,
        description: str | None = None,
        delete_group: str | None = None,
        allow_exact_matching: bool | None = None,
        write_material: bool = True,
    ) -> dict[str, object]:
        """
        Write a mesh as a complete asset: MHCLO (`.proxy` for a body proxy), OBJ, and for
        a MakeSkin material its MHMAT and textures. **Writes files, with no undo. Source
        textures are never changed.** Measure first with `mpfb_check_mesh_asset`: **only
        MPFB's own validator blocks a write**, and the rest is reported in `check`.

        `asset_name` is a name, never a path: letters, digits and single `_`. `destination`
        is `"library"` (`<user data>/<type>/<asset_name>/`) or `"export_directory"` (the
        directory the bridge's user chose), to iterate without filling the library.
        `object_type` is `mpfb_add_asset`'s, required when the mesh has none, and stored.
        `dry_run` does everything but write. `allow_exact_matching` left out follows
        MakeClothes' setting on the scene. `delete_group` left out takes the object's, and
        one absent writes `delete_vertices: 0`; one named must exist. **`homepage`, tags and
        `z_depth` are not arguments, since MPFB's writer drops them.**

        `license`, `author` and `description` default from the object, and an argument is
        set on it. `license_resolved_by` and `author_resolved_by` say `"argument"`,
        `"object"` or `"mpfb_default"`; **`warnings` says when the license is only MPFB's
        CC0**, which the catalogues then show.

        On `written: true`, `result` has `path` (on every answer), `fragment`, `path_resolved_by`,
        `overwrote`, `file_before`, `files`, `match_counts`, `delete_vertices`, `max_pole`,
        `uuid`, `xref_cache_built` (about 30 s, once), `material_written` or
        `material_not_written_because`, `textures_left_out`, `values_not_restored` as
        `mpfb_store_makeskin_material` says it, `properties_set`, `selection_restored`.
        **A library write updates `asset_source`** (`asset_source_updated`); an
        export-directory write leaves it. `check` is per component `outward_fraction`,
        `fit_offset` and overlaps, unmasked included. `try_with` is the next calls, keyed by
        tool in order: a body from a preset (yours to choose), this asset on it, the measure.

        Refusals: `subject_not_found`, `not_a_mesh`, `subject_is_basemesh`, `invalid_name`,
        `basemesh_not_found`, `not_a_basemesh`, `basemesh_ambiguous` with `candidates`,
        `object_type_required`, `unknown_object_type`, `export_directory_missing`,
        `invalid_license`, `delete_group_not_found`, `not_in_object_mode`, `mesh_not_visible`,
        **`rig_not_at_rest`** and **`character_turned`**, since either would be baked into
        the asset, `asset_exists`, `name_shadowed`, `not_valid_as_asset` with `validator`,
        and `match_failed`, `obj_does_not_match` and `write_failed`, which moved nothing.
        """
        return backend.send(
            "write_mesh_asset",
            params={
                "name": arguments.validated_subject(name),
                "basemesh": arguments.validated_text(
                    basemesh, "basemesh", "omit it to have the body found"),
                "asset_name": artifact_names.validated_asset_name(asset_name),
                "object_type": arguments.validated_text(
                    object_type, "object_type", "omit it to take the object's"),
                "destination": _validated_destination(destination),
                "overwrite": arguments.validated_flag(overwrite, "overwrite"),
                "dry_run": arguments.validated_flag(dry_run, "dry_run"),
                "license": _validated_line(license, "license"),
                "author": _validated_line(author, "author"),
                "description": _validated_line(description, "description"),
                "delete_group": arguments.validated_text(
                    delete_group, "delete_group", "omit it to take the object's"),
                "allow_exact_matching": _validated_optional_flag(
                    allow_exact_matching, "allow_exact_matching"),
                "write_material": arguments.validated_flag(write_material, "write_material"),
            },
        )
