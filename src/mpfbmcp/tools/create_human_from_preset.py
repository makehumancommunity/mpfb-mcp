"""
The ``mpfb_create_human_from_preset`` tool: build a character from a save file.

**Named for what it does rather than for what MPFB calls it.**
``mpfb_load_preset`` would be shorter and would cost fewer bytes in every tool
listing an MCP client downloads, and it would be wrong in the one way that
matters: ``deserialize_from_dict()`` calls ``create_human()`` unconditionally,
so a call adds a *new* character to the scene and changes no existing one. "Load
a preset" reads to an agent like "restore over what is there". The name states
the hazard, which is cheaper than a description paragraph undoing the wrong
reading - and it mirrors both ``mpfb_create_human`` and MPFB's own panel, where
the button under "From save file" says "Create human".

The seven overrides each default to ``None`` meaning *use what the preset says*,
which is the ``mpfb_set_macro_details`` idiom: "not mentioned" and "set to the
default" are different requests. Where a vocabulary is already documented by
another tool - rig identifiers by ``mpfb_list_rigs``, skin models by
``mpfb_set_skin`` - the description names that tool rather than restating the
list.

**Five of ``create_human()``'s arguments are deliberately not exposed**:
``mask_helpers``, ``detailed_helpers``, ``extra_vertex_groups``,
``feet_on_ground`` and ``subdiv_levels``. They are meaningful when *creating* a
character and close to meaningless when rebuilding a saved one, and each would
cost description budget that this effort has very little of. They keep MPFB's
own defaults, which is what its preset panel passes.

The interesting decisions - why every settings dict starts from
``get_default_deserialization_settings()``, why ``material_instances_policy``
follows the panel rather than the service, which of the operator's conveniences were
dropped and why, and what happens when a preset names an asset or a rig this
Blender does not have - are in the command's docstring, where the code that
makes them is.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend
from mpfbmcp.artifact_names import validated_preset_name


def _validated_optional_flag(value: object, argument: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        # Deliberately not truthiness: "false" is a true value, and
        # load_clothes="false" would load the clothes it was asking to skip.
        raise ValueError("{:s} must be a bool or omitted, got {!r}".format(argument, value))
    return value


def _stripped_text(value: object, argument: str, hint: str) -> str | None:
    """:func:`arguments.validated_text`, stripped.

    Stripped here, unlike anywhere else, because each of these decides whether
    the preset's own value is used at all, and a value with stray whitespace
    would otherwise be looked up verbatim and miss.
    """
    checked = arguments.validated_text(value, argument, hint)
    return None if checked is None else checked.strip()


def _validated_scale(scale: object) -> float | None:
    """A range check on a number, not a vocabulary check on a name.

    This is the ordinary "validate structured input before crossing the socket"
    case rather than an exception to it: ``scale`` multiplies the whole
    character, MPFB's own panel offers exactly 0.1, 1.0 and 10.0 for it, and a
    zero or a negative would produce a degenerate mesh rather than a small one.
    ``mpfb_create_human`` takes the same argument the same way.
    """
    if scale is None:
        return None
    if isinstance(scale, bool) or not isinstance(scale, (int, float)):
        raise ValueError("scale must be a number or omitted, got {!r}".format(scale))
    if scale <= 0.0:
        raise ValueError(
            "scale must be greater than 0.0, got {!r}. MPFB's own panel offers 0.1 (metre), "
            "1.0 (decimetre) and 10.0 (centimetre).".format(scale))
    return float(scale)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create Character From Preset",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_create_human_from_preset(
        preset_name: str,
        override_rig: str | None = None,
        override_skin_type: str | None = None,
        override_clothes_material_type: str | None = None,
        override_eyes_material_type: str | None = None,
        load_clothes: bool | None = None,
        scale: float | None = None,
        material_instances_policy: str | None = None,
    ) -> dict[str, object]:
        """
        Build a **new** character from a saved MPFB preset: phenotype, detail
        morphs, rig, body parts, garments, skin and eye materials. It **adds**
        a character and changes nothing already in the scene - this is not
        "load into the current character". Seconds, not milliseconds: it
        imports and fits every asset the preset names.

        `preset_name` is a name, never a path - `mpfb_list_presets` reports the
        ones that exist, and a miss here comes back with `available_presets`
        naming them.

        Each override defaults to null meaning **use what the preset says**;
        `overrides` in the response reports, per argument, what you asked for,
        what the preset held and what was used.

          - `override_rig`: `"NONE"` for no rig, or any `identifier`
            `mpfb_list_rigs` reports, `custom.*` included. A `rigify.*` preset
            gives you a **meta** rig - finish it with
            `mpfb_generate_rigify_rig`.
          - `override_skin_type`: `mpfb_set_skin`'s five `skin_type` values,
            plus `"NONE"` for no skin at all.
          - `override_clothes_material_type` / `override_eyes_material_type`:
            `mpfb_add_asset`'s `material_type`, for garments and every body
            part but the eyes, and for the eyes.
          - `load_clothes` false builds the body and skips the garments.
          - `scale`: 0.1 metre (MPFB's default), 1.0 decimetre, 10.0
            centimetre.
          - `material_instances_policy`: `NEVER`, `ENHANCED` or `ENHANCEDMS` -
            which skin types get per-region material slots. **Defaults to
            `ENHANCED`, which is MPFB's preset panel's default rather than the
            `NEVER` its service function defaults to**; both come back, as
            `material_instances_policy_used` and `_service_default`.

        On `created: true` (and so `performed: true`), `result` carries
        `basemesh_name`, `rig_object_name` and `rig_identified_as`,
        `equipped_assets` (`kind`, `name` and `asset_source` per item),
        `skin_material_identified_as`, `settings_used` (MPFB's own settings
        dict, in MPFB's own key names), `objects_created` and
        `active_object_after` - **the selection is not restored**, because
        deserialization activates what it creates and there is no prior state
        to return to.

        **Read `unresolved_assets`.** A preset that names a garment or body
        part which is not installed here loads without it and MPFB says
        nothing; that field names each one and the subdirectory it was looked
        for in.

        Refusals come back as `created: false` with a `blocked_by`:
        `preset_not_found` (with `available_presets`), `preset_unreadable`,
        `not_object_mode`, `unknown_material_instances_policy`,
        `config_dir_missing`,
        `settings_incomplete`, and `deserialization_failed` - the one that is
        **not** a no-op, since a character is built in stages, so
        `objects_created` names what was left behind. Its commonest cause is a
        rig the preset names and this Blender lacks: MPFB's rig adders raise
        rather than degrade, so retry with `override_rig`.
        """
        # `result` (built in bridge/mpfb_bridge/commands/create_human_from_preset.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "create_human_from_preset",
            params={
                # The authoritative check, here rather than in Blender: this
                # name becomes a path. See mpfbmcp/artifact_names.py.
                "preset_name": validated_preset_name(preset_name),
                "override_rig": _stripped_text(
                    override_rig, "override_rig",
                    "omit it to use the preset's rig, or pass 'NONE' for no rig"),
                "override_skin_type": _stripped_text(
                    override_skin_type, "override_skin_type",
                    "omit it to use the preset's skin type, or pass 'NONE' for no skin"),
                "override_clothes_material_type": _stripped_text(
                    override_clothes_material_type, "override_clothes_material_type",
                    "omit it to use the preset's clothes material type"),
                "override_eyes_material_type": _stripped_text(
                    override_eyes_material_type, "override_eyes_material_type",
                    "omit it to use the preset's eye material type"),
                "load_clothes": _validated_optional_flag(load_clothes, "load_clothes"),
                "scale": _validated_scale(scale),
                "material_instances_policy": _stripped_text(
                    material_instances_policy, "material_instances_policy",
                    "omit it for MPFB's preset panel default, ENHANCED"),
            },
            # preset_files.py so that this tool, the catalogue and the save tool
            # cannot disagree about which names are legal or where the file is;
            # performed.py for the uniform flag every mutating tool reports.
        )
