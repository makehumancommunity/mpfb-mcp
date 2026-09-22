"""
The ``mpfb_add_asset`` tool: put an MHCLO asset on a character.

The acting counterpart to ``mpfb_list_assets``, which has named every garment,
proxy, eye, hair and tooth on the machine since FR 005 while nothing could
attach one. Its three identifiers - the absolute ``path``, the portable
``fragment`` and the ``object_type`` that doubles as an ``asset_type`` - existed
for this tool and were, until now, decorative.

Two of ``HumanService.add_mhclo_asset()``'s arguments are the ones that get
characters wrong, and both are handled here rather than passed through:

- ``asset_type`` defaults to ``"Clothes"`` there, which is wrong for six of the
  eight types it accepts and wrong in a way nothing reports: hair added without
  it *becomes* clothes, with the wrong colour, the wrong delete-group handling
  and an ``object_type`` property that is wrong from then on. It is **required**
  here. A defaulted argument that changes what the character *is* must not be
  defaulted.
- ``material_type`` defaults to ``"MAKESKIN"`` there, which is right for clothes,
  wrong for a topology proxy (which wants none at all) and merely one of three
  options for eyes. It is defaulted **per asset type** here, matching MPFB's own
  settings panel rather than the function signature, and the chosen value is
  echoed back because it was usually not the caller's.

One asset per call, deliberately: loading an MHCLO is seconds of mesh import and
vertex fitting, so the socket round trip does not dominate the way it does for
``mpfb_set_targets``, and per-asset failures stay legible.

Nothing about the asset vocabulary is validated on this side of the socket - the
installed library and MPFB's own section table are only readable inside Blender,
and a list kept here would drift from them. What is validated here is shape, and
the one thing shape can settle: that exactly one of ``path`` and ``fragment``
was given.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import backend


def _validated_name(name: object) -> str | None:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValueError("name must be a string or omitted, got {!r}".format(name))
    if not name.strip():
        raise ValueError(
            "name must not be empty or whitespace; omit it to use the active object")
    return name


def _validated_optional_text(value: object, argument: str, hint: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            "{:s} must be a string or omitted, got {!r}".format(argument, value))
    if not value.strip():
        # An explicitly empty value and an omitted one arise from different
        # mistakes, so the empty one is never quietly treated as the omission -
        # which matters especially here, where "omitted" is half of the
        # exactly-one-of rule below.
        raise ValueError("{:s} must not be empty or whitespace; {:s}".format(argument, hint))
    return value


def _validated_asset_type(asset_type: object) -> str:
    """Shape only. The vocabulary is MPFB's own section table, read in Blender."""
    if not isinstance(asset_type, str):
        raise ValueError("asset_type must be a string, got {!r}".format(asset_type))
    if not asset_type.strip():
        raise ValueError(
            "asset_type is required and must name what this asset is: call mpfb_list_assets and "
            "pass the entry's 'object_type' (Clothes, Proxymeshes, Eyes, Eyebrows, Eyelashes, "
            "Hair, Teeth or Tongue). MPFB's own default of 'Clothes' would silently mislabel a "
            "body part, so this tool has no default.")
    return asset_type


def _validated_source(path: object, fragment: object) -> tuple[str | None, str | None]:
    """Exactly one of the two identifiers the catalogue reports for every asset.

    Both are accepted because they are not interchangeable: ``path`` is what the
    adding function takes, ``fragment`` is what survives being written down and
    moved to another machine. Neither is a superset of the other, and taking
    only one of them would make half of every catalogue entry decorative.
    """
    checked_path = _validated_optional_text(
        path, "path", "pass mpfb_list_assets' 'path', or use 'fragment' instead")
    checked_fragment = _validated_optional_text(
        fragment, "fragment", "pass mpfb_list_assets' 'fragment', or use 'path' instead")
    if checked_path is not None and checked_fragment is not None:
        raise ValueError(
            "Give either path or fragment, not both. They can name different files, and "
            "silently preferring one would attach an asset the caller did not ask for.")
    if checked_path is None and checked_fragment is None:
        raise ValueError(
            "Give either path or fragment. Both are reported for every entry by "
            "mpfb_list_assets: 'path' is the absolute file, 'fragment' is the portable "
            "identifier resolved against this Blender's asset roots.")
    return (checked_path, checked_fragment)


def _validated_subdiv_levels(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        # bool is a subclass of int, so subdiv_levels=True would otherwise mean
        # 1 rather than fail.
        raise ValueError("subdiv_levels must be an int, got {!r}".format(value))
    if value < 0:
        raise ValueError("subdiv_levels must not be negative, got {!r}".format(value))
    return value


def _validated_flag(argument: str, value: object) -> bool:
    if not isinstance(value, bool):
        # Deliberately not truthiness: "false" and 0 are how a caller signals a
        # bool it did not manage to build, and import_weights="false" would
        # otherwise produce a garment parented to the armature but not deformed
        # by it.
        raise ValueError("{:s} must be a bool, got {!r}".format(argument, value))
    return value


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Add Mesh Asset",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_add_asset(
        asset_type: str,
        name: str | None = None,
        path: str | None = None,
        fragment: str | None = None,
        material_type: str | None = None,
        subdiv_levels: int = 1,
        set_up_rigging: bool = True,
        interpolate_weights: bool = True,
        import_subrig: bool = True,
        import_weights: bool = True,
    ) -> dict[str, object]:
        """
        Equip a MakeHuman character with one MHCLO asset - clothes, hair, eyes,
        eyebrows, eyelashes, teeth, tongue or a topology proxy.

        **Rig the character before dressing it**: MPFB rigs a garment only if a
        rig is present when the garment is attached, and nothing rigs it
        retroactively. The asset is attached either way, and `rigged_to` names
        the armature or is null with `parented_to` naming the basemesh.

        `asset_type` is **required**, and is exactly the `object_type`
        `mpfb_list_assets` reports for the entry: `Clothes`, `Proxymeshes`,
        `Eyes`, `Eyebrows`, `Eyelashes`, `Hair`, `Teeth` or `Tongue`. MPFB's
        own function defaults it to `"Clothes"`, which mislabels a body part
        silently and permanently, so there is no default here;
        `object_type_recorded` echoes what was stored.

        Name the asset with **either** `path` **or** `fragment`, never both;
        `mpfb_list_assets` reports both. A `fragment` (`"fedora/fedora.mhclo"`)
        is portable but is resolved by **basename**, so two packs shipping
        `hat.mhclo` resolve to a coin toss - check `resolved_path` when
        `resolved_by` is `"fragment"`.

        `material_type` is `MAKESKIN`, `GAMEENGINE`, `PROCEDURAL_EYES` or
        `NONE`, and is best left unset: it then follows MPFB's settings panel
        per asset type - `NONE` for `Proxymeshes`, `MAKESKIN` for everything
        else - and `material_type_used` reports the choice. `PROCEDURAL_EYES`
        is accepted only for `Eyes`. **`NONE` deletes the imported mesh's
        materials** and creates nothing, even when the MHCLO names one;
        `material_created` and `warnings` say when that happened.

        `subdiv_levels` (default 1, MPFB's own) sets the subdivision modifier's
        *render* level, viewport level 0; `0` adds no modifier.
        `set_up_rigging`, `interpolate_weights`, `import_subrig` and
        `import_weights` are MPFB's own flags at MPFB's own defaults. Fitting
        to the body and the delete group are unconditional, so neither has an
        argument, and an alternative material is chosen afterwards with
        `mpfb_set_asset_material`.

        On `added: true`, `result` carries `asset_object_name` - read off the
        created object, since Blender uniquifies a name already in use, and the
        address `mpfb_remove_asset` and `mpfb_set_asset_material` need - plus
        `basemesh_name`, `resolved_path`/`resolved_by`/`asset_source`,
        `object_type_recorded`, `material_type_used`,
        `material_created`/`material_name`, `rigged_to` or `parented_to`,
        `subrig_object_name`, `delete_group_name` and
        `delete_group_applied_to`, `subdiv_modifier_added`, `warnings` for what
        MPFB only logs, and `proxy_extras` - the four things a `Proxymeshes`
        asset gets from MPFB's `.mhm` loading path, which this follows rather
        than its proxy library panel.

        Refusals come back as `added: false` (and so `performed: false`) with a
        `blocked_by` and a sentence: `subject_not_found`, `asset_not_found`,
        `unknown_asset_type` (with `known_asset_types`),
        `invalid_material_type`, `no_asset_subdir` and `not_object_mode`.
        """
        checked_path, checked_fragment = _validated_source(path, fragment)
        # `result` (built in bridge/mpfb_bridge/commands/add_asset.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "add_asset",
            params={
                "name": _validated_name(name),
                "path": checked_path,
                "fragment": checked_fragment,
                "asset_type": _validated_asset_type(asset_type),
                "material_type": _validated_optional_text(
                    material_type, "material_type",
                    "omit it to take MPFB's own default for this asset type"),
                "subdiv_levels": _validated_subdiv_levels(subdiv_levels),
                "set_up_rigging": _validated_flag("set_up_rigging", set_up_rigging),
                "interpolate_weights": _validated_flag(
                    "interpolate_weights", interpolate_weights),
                "import_subrig": _validated_flag("import_subrig", import_subrig),
                "import_weights": _validated_flag("import_weights", import_weights),
            },
            # Shared with mpfb_list_assets' payload, which reported the
            # object_type and fragment this call is holding. Mapping the first
            # back to an asset subdir is the only way to resolve the second, and
            # two implementations of that table would make a just-listed asset
            # look uninstalled here.
        )
