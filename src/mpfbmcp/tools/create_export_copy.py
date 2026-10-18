"""
The ``mpfb_create_export_copy`` tool: MPFB's Export copy panel, as one call.

A copy of a character processed for another application - shape keys baked,
helper geometry deleted, masks and subdivision baked or removed, visemes and
ARKit face units loaded - with the original left as it was
([FR 039](../../../feature-requests/done/039-exporting-characters/README.md)).
It writes no file; ``mpfb_export_character`` does, from this copy or from any
character. Two tools rather than one so that a copy can be read and changed
with the other tools before it is written.

**The panel's eleven options under its own spellings, with its defaults**, per
[where MPFB's UI re-defaults a service argument](../../../specifications/mpfb-integration.md#where-mpfbs-ui-coerces-or-re-defaults-a-service-argument-mpfb-mcp-does-the-same-and-reports-both),
except where the glossary disagrees: ``load_arkit_face_units`` (MPFB's
``faceunits_arkit``), ``load_microsoft_visemes`` / ``load_meta_visemes``
(``visemes_microsoft`` / ``visemes_meta``) and ``in_export_collection``
(``collection``, which reads as a collection's name). ``material_type`` is what
the panel lacks.

**Three vocabularies are checked here, and none is the vocabulary exception.**
``mask_modifiers`` and ``subdiv_modifiers`` (``KEEP``/``REMOVE``/``BAKE``) look
like MPFB's enum, and are the panel's - but no MPFB function receives them: the
operator, and this tool's command, branch on them. That makes them this
package's own, like ``mode``, so a shape. ``material_type`` takes one value
today. All three are checked again in the command's parameter contract.

``suffix`` is any string up to 32 characters, the empty one included: MPFB's
panel accepts it, and Blender then gives each copy a ``.001`` name, which the
answer reports. Why the command departs from the operator where it does - the
copy's repairs, collecting before removing - is its docstring's,
``bridge/mpfb_bridge/commands/create_export_copy.py``.
"""

from __future__ import annotations

__all__ = (
    "MATERIAL_TYPES",
    "MODIFIER_STRATEGIES",
    "SUFFIX_MAX_LENGTH",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

MODIFIER_STRATEGIES = ("KEEP", "REMOVE", "BAKE")
MATERIAL_TYPES = ("GAMEENGINE",)
SUFFIX_MAX_LENGTH = 32


def _validated_strategy(value: object, argument: str) -> str:
    if value not in MODIFIER_STRATEGIES:
        raise ValueError("{:s} must be one of {:s}, got {!r}".format(
            argument, ", ".join(MODIFIER_STRATEGIES), value))
    return value  # type: ignore[return-value]


def _validated_material_type(value: object) -> str | None:
    if value is not None and value not in MATERIAL_TYPES:
        raise ValueError("material_type must be null (keep the materials) or one of {:s}, got "
                         "{!r}".format(", ".join(MATERIAL_TYPES), value))
    return value  # type: ignore[return-value]


def _validated_suffix(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("suffix must be a string, got {!r}".format(value))
    if len(value) > SUFFIX_MAX_LENGTH:
        raise ValueError("suffix must be at most {:d} characters, got {:d}: Blender truncates "
                         "object names at 63".format(SUFFIX_MAX_LENGTH, len(value)))
    return value


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create Export Copy",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_create_export_copy(  # pylint: disable=too-many-arguments
        name: str | None = None,
        bake_shapekeys: bool = True,
        mask_modifiers: str = "KEEP",
        subdiv_modifiers: str = "KEEP",
        delete_helpers: bool = True,
        remove_basemesh: bool = False,
        load_microsoft_visemes: bool = False,
        load_meta_visemes: bool = False,
        load_arkit_face_units: bool = False,
        interpolate: bool = False,
        suffix: str = "_export_copy",
        in_export_collection: bool = True,
        material_type: str | None = None,
    ) -> dict[str, object]:
        """
        Copy a MakeHuman character - rig, body, every mesh asset - and process
        the copy for another application, as MPFB's Export copy panel does,
        with its defaults. **The original is not changed**; the copy is a
        character of its own, which `mpfb_export_character` writes to a file.
        Blender is busy for the whole call: baking masks under loaded sets
        took 7 s headless and over a minute in a crowded windowed Blender.

        `bake_shapekeys` bakes **every** shape key, the face included:
        `face_baked_into_mesh` / `expressions_baked_into_mesh` say what was
        frozen (empty when neutral), and face units loaded afterwards move the
        face from there. `mask_modifiers` / `subdiv_modifiers`: `"KEEP"`,
        `"REMOVE"` or `"BAKE"`; under a mask FBX drops the shape keys and glTF
        and USD ignore the mask, so engines need `"BAKE"`, which also drops the
        helper geometry.
        `remove_basemesh` needs a body proxy. `load_microsoft_visemes` (22,
        pack visemes01), `load_meta_visemes` (15, visemes02) and
        `load_arkit_face_units` (52, faceunits01) load after the bake;
        `interpolate` copies them onto the mesh assets.
        `material_type: "GAMEENGINE"` gives every copied mesh its own
        GameEngine material, the one MPFB calls likely to survive export;
        otherwise the copy **shares** the original's materials
        (`materials_shared_with_original`).

        On `created: true`, `result` has `copy_root_name`, `copy_basemesh_name` (null if
        removed), `copy_bodyproxy_name`, `copied_objects`, what each step did
        (`shape_keys_loaded` with `could_not_load`, `modifiers_baked`,
        `modifiers_removed`, `helper_vertices_left`...), `materials_swapped`,
        and `copy_repairs`: what MPFB's own copy missed and this one fixed.
        Every answer reports `faceunits01_installed`, `visemes01_installed`
        and `visemes02_installed`. Refusals copy nothing: `subject_not_found`,
        `not_object_mode`, `<pack>_not_installed`, `no_bodyproxy`,
        `proxy_cannot_be_baked` (MPFB cannot bake a proxy `interpolate` gave
        shape keys); a failure part way is `copy_failed`, naming
        `objects_created`.
        """
        return backend.send(
            "create_export_copy",
            params={
                "name": arguments.validated_subject(name),
                "bake_shapekeys": arguments.validated_flag(bake_shapekeys, "bake_shapekeys"),
                "mask_modifiers": _validated_strategy(mask_modifiers, "mask_modifiers"),
                "subdiv_modifiers": _validated_strategy(subdiv_modifiers, "subdiv_modifiers"),
                "delete_helpers": arguments.validated_flag(delete_helpers, "delete_helpers"),
                "remove_basemesh": arguments.validated_flag(remove_basemesh, "remove_basemesh"),
                "load_microsoft_visemes": arguments.validated_flag(
                    load_microsoft_visemes, "load_microsoft_visemes"),
                "load_meta_visemes": arguments.validated_flag(load_meta_visemes,
                                                              "load_meta_visemes"),
                "load_arkit_face_units": arguments.validated_flag(
                    load_arkit_face_units, "load_arkit_face_units"),
                "interpolate": arguments.validated_flag(interpolate, "interpolate"),
                "suffix": _validated_suffix(suffix),
                "in_export_collection": arguments.validated_flag(
                    in_export_collection, "in_export_collection"),
                "material_type": _validated_material_type(material_type),
            },
        )
