"""
The ``mpfb_export_character`` tool: one character, one file another application opens.

The step MPFB's documentation leaves to the user - select the character, run
Blender's exporter with the right settings - for FBX, glTF and USD, on any
character: an export copy from ``mpfb_create_export_copy`` or not
([FR 039](../../../feature-requests/done/039-exporting-characters/README.md)).

**It writes a file outside the ``.blend``**, so its shape is the saving tools'
([mutating-tools.md](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)):
``overwrite`` defaults to refusing, the absolute path is in every answer, and
``export_name`` is a name and never a path - the rule is
``mpfbmcp.artifact_names``, the third noun beside presets and saved
expressions, checked before anything is sent. **There is no directory
argument at all**: the directory is chosen by the person running the bridge,
in its preferences, and an argument here would hand that choice to whoever
writes the call.

``format`` and ``target_engine`` are this package's own vocabularies - no MPFB
function sees them - so they are shapes, checked here and again in the
command's contract. Which preset supports which format is the command's,
because the preset tables live there beside their sources; a pair with no
table is refused there, naming the formats the preset has.
"""

from __future__ import annotations

__all__ = (
    "FORMATS",
    "TARGET_ENGINES",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend
from mpfbmcp.artifact_names import validated_export_name

FORMATS = ("fbx", "gltf", "usd")
TARGET_ENGINES = ("generic", "unity", "unreal", "godot")


def _validated_format(value: object) -> str | None:
    if value is not None and value not in FORMATS:
        raise ValueError("format must be null (the preset's own) or one of {:s}, got {!r}".format(
            ", ".join(FORMATS), value))
    return value  # type: ignore[return-value]


def _validated_engine(value: object) -> str:
    if value not in TARGET_ENGINES:
        raise ValueError("target_engine must be one of {:s}, got {!r}".format(
            ", ".join(TARGET_ENGINES), value))
    return value  # type: ignore[return-value]


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Export Character",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_export_character(
        export_name: str,
        name: str | None = None,
        format: str | None = None,  # pylint: disable=redefined-builtin
        target_engine: str = "generic",
        overwrite: bool = False,
    ) -> dict[str, object]:
        """
        Write a MakeHuman character - its rig and every visible object in its
        family, nothing else - to **one self-contained file**, textures
        embedded. **This writes a file outside the .blend; nothing can undo
        it.** The character is not changed. Usually given an
        `mpfb_create_export_copy` copy.

        `export_name` is a name, never a path (letters, digits, `_`, `-`, `.`,
        at most 64): the file is `<export_name>.fbx`, `.glb` or `.usdz` in the
        **export directory, which only the person running Blender chooses**.
        `path` and `path_resolved_by` are in every answer. `format`: `"fbx"`,
        `"gltf"` or `"usd"`, null for the preset's. `target_engine`:
        `"generic"` (any format), `"unity"`, `"unreal"` (FBX) or `"godot"`
        (glTF); `exporter_options` is exactly what Blender's exporter got.

        On `exported: true`, `result` has `size_bytes`, `objects_exported`,
        `objects_left_out` (hidden), and `readiness` - facts, not refusals: per
        mesh `material_identified_as`, `shape_keys` by kind and
        `topology_changing_modifiers_beside_shape_keys`, and
        `procedural_material_meshes`, `helper_vertices`, `rig_identified_as`.
        `overwrite` (default false) refuses an existing file (`export_exists`,
        `file_before` giving its size and age). Other refusals:
        `subject_not_found`, `format_not_supported_by_engine`,
        `export_directory_missing`, `not_object_mode`.
        """
        return backend.send(
            "export_character",
            params={
                # The authoritative check, here rather than in Blender: this
                # name becomes a path. See mpfbmcp/artifact_names.py.
                "export_name": validated_export_name(export_name),
                "name": arguments.validated_subject(name),
                "format": _validated_format(format),
                "target_engine": _validated_engine(target_engine),
                # Not truthiness: this flag stands between a caller and an
                # irreversible file replacement.
                "overwrite": arguments.validated_flag(overwrite, "overwrite"),
            },
        )
