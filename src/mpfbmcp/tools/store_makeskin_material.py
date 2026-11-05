"""
The ``mpfb_store_makeskin_material`` tool: an MHMAT and its textures, where MPFB looks.

MakeSkin's panel stores a material as an alternate beside an asset or as a body skin.
The gi's own README says another belt colour "would be an alternative material", and
no tool could make one
([FR 049](../../../feature-requests/done/049-makeskin-materials/README.md)).

**It writes outside the ``.blend``**, so it owes
[what a save owes](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more):
a name and never a path, checked here by ``artifact_names`` under a rule of its own, and
``overwrite`` false by default. ``store_as`` is required, since the two destinations are
different directories and neither is a safe guess; it is this package's own word, so it
is checked here too. ``license`` is a vocabulary MPFB holds and is checked on the far
side, and ``author`` is one line of text because an MHMAT is one key per line.
"""

from __future__ import annotations

__all__ = (
    "STORE_AS",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import artifact_names
from mpfbmcp import backend

STORE_AS = ("alternate", "skin")


def _validated_store_as(store_as: object) -> str:
    if store_as not in STORE_AS:
        raise ValueError("store_as must be one of {}, got {!r}".format(
            ", ".join(STORE_AS), store_as))
    return store_as  # type: ignore[return-value]


def _validated_line(value: object, argument: str) -> str | None:
    checked = arguments.validated_text(value, argument, "omit it to take the object's")
    if checked is not None and ("\n" in checked or "\r" in checked):
        # An MHMAT is one key per line, so a line break would write a second key.
        raise ValueError("{} must be one line of text".format(argument))
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Store MakeSkin Material",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_store_makeskin_material(
        store_as: str,
        material_name: str,
        name: str | None = None,
        overwrite: bool = False,
        dry_run: bool = False,
        license: str | None = None,  # pylint: disable=redefined-builtin
        author: str | None = None,
    ) -> dict[str, object]:
        """
        Write a mesh's MakeSkin material as an MHMAT with its textures, where MPFB
        will find it. **Writes files, with no undo. Source textures are never
        changed**, unlike MPFB's own panel, which re-encodes them.

        `store_as` is required. `"alternate"` writes `<asset dir>/<name>/<name>.mhmat`
        for a mesh asset whose `asset_source` resolves; `"skin"` writes
        `<user data>/skins/<name>/<name>.mhmat` for a body or body proxy.
        `material_name` is a name, never a path: lower case letters, digits and
        `_`, which is what survives MPFB's normalisation. `dry_run` does everything
        but write.

        `license` and `author` default from the object; `license_resolved_by` and
        `author_resolved_by` say `"argument"`, `"object"` or `"mpfb_default"`.

        On `saved: true`, `result` carries `path` (in every answer, refusals too),
        `fragment`, `size_bytes`, `overwrote`, `file_before`, and
        `textures_written`, one row per slot: `source_path`, `source_image`, `how`
        (`copied`, `saved_from_blender`, `already_in_place`), `path`, `size_bytes`.
        `apply_with` is the arguments for `mpfb_set_asset_material` or
        `mpfb_set_skin`, keyed by tool; `cache_invalidated` says that catalogue was
        refreshed, so the material is listed at once.

        **`values_not_restored`: MPFB's loader reads a stored file's textures and
        `diffuseColor` and no other number.** Each other value this material holds
        away from MPFB's template is listed with what it `stored` and what it will
        be `after_apply`, through MPFB's panel and those two tools alike. To have
        one on a mesh, apply the file, then send it to `mpfb_set_makeskin_material`
        with `textures` from `mpfb_get_makeskin_material`.

        `asset_packs` names packs claiming the asset; `warnings` says what that
        risks, and when the license is only MPFB's default.

        Refusals: `subject_not_found`, `not_a_mesh`, `invalid_name`, `no_material`,
        `not_makeskin`, `type_not_supported` (a body as an alternate, anything else
        as a skin), `not_an_mpfb_object`, `asset_source_missing`,
        `asset_not_in_library`, `invalid_license`, `invalid_author`,
        `texture_unavailable` with `texture_errors`, `material_exists` with
        `file_before` and `existing_textures`, `name_shadowed` with `shadowed_by`,
        and `write_failed`, which moved nothing into place.
        """
        return backend.send(
            "store_makeskin_material",
            params={
                "name": arguments.validated_subject(name),
                "store_as": _validated_store_as(store_as),
                "material_name": artifact_names.validated_material_name(material_name),
                "overwrite": arguments.validated_flag(overwrite, "overwrite"),
                "dry_run": arguments.validated_flag(dry_run, "dry_run"),
                "license": _validated_line(license, "license"),
                "author": _validated_line(author, "author"),
            },
        )
