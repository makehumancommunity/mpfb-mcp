"""
MCP server for MPFB (MakeHuman Plugin For Blender).

Early beta: exposes MPFB-specific tools that run inside a running Blender
instance. A tool names a command from a closed vocabulary and hands over its
parameters; the MPFB Bridge add-on - this project's own, in ``bridge/`` -
dispatches it and answers over its TCP socket (see bridge_connection.py).

This requires:
  - Blender running with MPFB and the MPFB Bridge add-on installed & enabled.
  - The bridge's command server started (from the add-on's preferences panel,
    where a checkbox can also start it with Blender, or
    ``blender --background --command mpfb_bridge`` for a headless one).
  - This server's client configuring MPFB_BRIDGE_HOST / MPFB_BRIDGE_PORT to
    match, if not using the defaults (127.0.0.1:9877).
"""

from __future__ import annotations

__all__ = (
    "INSTRUCTIONS",
    "build_server",
    "main",
)

import inspect
from typing import Any

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.server.fastmcp.exceptions import ToolError  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments as arguments_module


class _Server(FastMCP):
    """FastMCP, refusing an argument the called tool does not declare.

    FastMCP validates a call through a model built from the tool's signature,
    and that model ignores a key it has no field for: ``topc`` misspelled
    reaches ``mpfb_list_docs`` as no filter at all, and a renamed argument's old
    spelling would reach its tool as the default. The check cannot live in a
    tool, which never sees the key, so it lives here, the one place every call
    passes through with its arguments as they arrived. ``call_tool`` is the
    public method FastMCP hands its protocol handler, bound at construction,
    which is why this is a subclass rather than a patch applied afterwards.

    The refusal is raised as a ``ToolError`` worded the way FastMCP words any
    other failure inside a tool, so the client sees an ``isError`` result naming
    the argument, exactly as it sees every other shape refusal - not a protocol
    error it might hide. MCP's own ``_meta`` travels beside ``arguments`` in the
    request, never inside it, so no client has a key of its own to lose here.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Filled by build_server() once every tool is registered. A tool missing
        # from it is not checked; tests/test_vocabulary.py is what fails if that
        # is ever all of them.
        self.declared_arguments: dict[str, frozenset[str]] = {}

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        declared = self.declared_arguments.get(name)
        if declared is not None:
            try:
                arguments_module.refuse_undeclared(name, declared, arguments or {})
            except ValueError as error:
                raise ToolError("Error executing tool {:s}: {!s}".format(name, error)) from error
        return await super().call_tool(name, arguments)


def _registered_tools(mcp: FastMCP) -> list:
    """Every registered tool, from the one place this package reaches into FastMCP.

    Guarded rather than assumed: if a future mcp release moves the tool manager,
    this is empty, the descriptions arrive indented and no argument is refused -
    and ``tests/test_description_budget.py`` and ``tests/test_vocabulary.py`` are
    what fail, rather than a user's server at startup.
    """
    manager = getattr(mcp, "_tool_manager", None)
    list_tools = getattr(manager, "list_tools", None)
    return [] if list_tools is None else list(list_tools())


def _shipped_without_source_indentation(mcp: FastMCP) -> None:
    """Send the docstrings the way a reader of the source sees them.

    ``Tool.from_function()`` takes ``fn.__doc__`` verbatim, so every line of
    every tool description would otherwise cross the wire carrying the eight
    spaces it is indented by in the file: about 500 bytes per tool, 12 KB across
    the twenty-five, of whitespace an MCP client downloads before any work happens.
    ``inspect.cleandoc`` is what ``help()`` shows and what the docstrings are
    written to look like.
    """
    for tool in _registered_tools(mcp):
        if tool.description:
            tool.description = inspect.cleandoc(tool.description)


# The keywords whose value is a schema, or a list or a map of schemas, and so is walked into.
# Everything else - `default`, `enum`, `const`, `examples` - is data, and a dict found there is
# left alone however it is keyed.
_SUBSCHEMA_KEYWORDS = ("items", "additionalProperties", "not", "if", "then", "else")
_SUBSCHEMA_LIST_KEYWORDS = ("anyOf", "allOf", "oneOf", "prefixItems")
_SUBSCHEMA_MAP_KEYWORDS = ("properties", "$defs", "definitions", "patternProperties")


def _without_generated_keys(schema: dict) -> dict:
    """A parameter schema without what pydantic generated and no caller acts on.

    Two things, and nothing else
    ([FR 059](../../feature-requests/done/059-what-a-session-pays-for/README.md)):

    - **Every `title` keyword.** Pydantic titles the schema `mpfb_list_docsArguments` and each
      property `Topic`, which is the property's own name restated - 272 of them, 7 KB of a 22 KB
      schema total. A *property* named `title` is a key of `properties` rather than a keyword, so
      the walk descends into `properties` by name and never strips one.
    - **The `null` option of an optional argument.** `str | None = None` is published as
      `anyOf: [{type: string}, {type: null}]` with `default: null`, which says "a string, or
      leave it out" at three times the length of `type: string` left out of `required`. Only that
      exact shape is collapsed: a union of two real types stays a union, a non-null default stays,
      and an argument with no default - a required nullable one - keeps its `null`, since a
      schema forbidding what it accepts would be worse than a long one.

    An explicit `null` is still accepted, because FastMCP validates a call through the model
    built from the signature, which this does not touch, and registers its handler with
    `validate_input=False`. That second fact is the library's: `tests/test_vocabulary.py` sends
    `null` to every optional argument through a real client, and is what fails if it changes.
    """
    cleaned: dict = {}
    for key, value in schema.items():
        if key == "title":
            continue
        if key in _SUBSCHEMA_MAP_KEYWORDS and isinstance(value, dict):
            cleaned[key] = {name: _without_generated_keys(sub) if isinstance(sub, dict) else sub
                            for name, sub in value.items()}
        elif key in _SUBSCHEMA_LIST_KEYWORDS and isinstance(value, list):
            cleaned[key] = [_without_generated_keys(sub) if isinstance(sub, dict) else sub
                            for sub in value]
        elif key in _SUBSCHEMA_KEYWORDS and isinstance(value, dict):
            cleaned[key] = _without_generated_keys(value)
        else:
            cleaned[key] = value
    return _as_its_own_type(cleaned)


def _as_its_own_type(schema: dict) -> dict:
    """``anyOf: [X, {type: null}]`` with ``default: null`` as X, with no default; else unchanged."""
    options = schema.get("anyOf")
    if ("default" not in schema or schema["default"] is not None
            or not isinstance(options, list) or len(options) != 2):
        return schema
    real = [option for option in options if option != {"type": "null"}]
    if len(real) != 1 or not isinstance(real[0], dict):
        return schema
    collapsed = {key: value for key, value in schema.items() if key not in ("anyOf", "default")}
    for key, value in real[0].items():
        collapsed.setdefault(key, value)
    return collapsed


def _published_without_generated_keys(mcp: FastMCP) -> None:
    """Rewrite each tool's published parameter schema; the model a call is validated by is not touched."""
    for tool in _registered_tools(mcp):
        tool.parameters = _without_generated_keys(tool.parameters)


# What every session receives before any tool is loaded, and the one text no tool owns
# ([FR 059](../../feature-requests/done/059-what-a-session-pays-for/README.md)). It crosses the wire
# as a single string; the groups below are for the reader of this file.
#
# **The conventions come first, and end within 2,048 characters.** One client was observed
# delivering only the first 4,096 characters of a server's instructions, and a secondary source
# puts the limit at 2 KB; the conventions are the part no tool description repeats, so they are
# the part that must survive either. The whole is held to 4,000 characters by
# `tests/test_description_budget.py`.
#
# **A sentence stays only if it states a convention, routes - says which tool does which job,
# since this may be all a model reads before loading one - or states an order across tools that no
# single description can own.** A fact about one tool belongs in that tool's description, which a
# caller reads before it can call the tool, under tool search as much as anywhere.
INSTRUCTIONS = " ".join((
    # What this is.
    "Tools for building and changing MakeHuman characters in Blender, through MPFB and the MPFB "
    "Bridge add-on.",

    # The conventions.
    "Conventions every tool shares, which no tool's description repeats. Each returns the same "
    "envelope: check `status` (\"ok\" or \"error\"), then read `result`; on a failure, branch on "
    "`error`, a short slug, not on the sentence in `message`. A tool acting on an "
    "existing character takes `name` - any object in that character's family, the basemesh, its "
    "rig or a garment fitted to it - or omit `name` to use whatever is active in Blender, and the "
    "response names the object actually worked on. A tool that cannot do what was asked answers "
    "rather than failing, so read `found` (the subject could not be resolved), `ready` and "
    "`blocked_by` (the world was not in a fit state, and which way) before concluding a call went "
    "wrong. Every tool that changes a character reports `performed`, a real boolean, true exactly "
    "when something changed; most keep a verb beside it (`added`, `applied`, `removed`, "
    "`generated`, `recalculated`, `refit_performed`), and the batch tools list their per-entry "
    "writes as `changes`; the tool says where the flag and its verb can differ. A capped listing "
    "always reports `truncated`, `total_count`, `offset` and `limit`: check `truncated` before "
    "concluding something is not installed. A character whose collection is excluded from the "
    "view layer is included for the call and excluded again, named in `temporarily_included`.",

    # Where to start.
    "When a tool fails unexpectedly, call mpfb_get_status first. To act on a character this "
    "session did not create, find it with mpfb_list_objects and identify it with "
    "mpfb_get_object_info rather than by its object names; to change one, read it with "
    "mpfb_get_character_summary and change only what should differ. The catalogues name entries "
    "the way the acting tool wants them: mpfb_list_assets (no arguments: a library summary), "
    "mpfb_list_rigs and mpfb_list_targets.",

    # Building a character, in the order MPFB needs and does not check.
    "Order matters and MPFB reports no error when it is wrong: add the rig with mpfb_add_rig "
    "BEFORE equipping anything with mpfb_add_asset, since nothing rigs an asset afterwards. A "
    "rigify.* rig is only a meta rig until mpfb_generate_rigify_rig, which is not undoable and "
    "comes after the assets. Take an asset off with mpfb_remove_asset, not by deleting the "
    "object. A character with no skin is grey: give it one with mpfb_set_skin. Recolour a garment "
    "with mpfb_list_asset_materials and mpfb_set_asset_material. Shape a body with "
    "mpfb_set_macro_details, mpfb_set_targets or mpfb_symmetrize_targets, then refit once with "
    "mpfb_refit_human, or everything fitted to it is left behind. Equip a character before "
    "laying several out with mpfb_place_character.",

    # Face and pose.
    "Compose a face from ARKit units with mpfb_set_face_units or apply saved expressions with "
    "mpfb_apply_expressions; a composed face is transient: "
    "mpfb_save_preset does not keep it and mpfb_save_expression does. Pose with "
    "mpfb_get_pose_controls (which bones to move, in the character's own frame), "
    "mpfb_set_pose_bones, mpfb_set_pose_switches and mpfb_reset_pose, a Rigify hand with "
    "mpfb_set_rigify_hand_shape, and read the result with mpfb_get_pose, not a screenshot.",

    # Measuring, materials and authoring assets.
    "Whether meshes pass through each other is measured with mpfb_check_intersections, not a "
    "render. A material from textures is mpfb_set_makeskin_material's, kept with "
    "mpfb_store_makeskin_material. To author a mesh asset, check it with mpfb_check_mesh_asset, "
    "give the body a delete group with mpfb_generate_delete_group, write it with "
    "mpfb_write_mesh_asset and follow its try_with; a rig with mpfb_create_rig "
    "(mpfb_get_rig_definition reads a rig as a table), mpfb_weight_rig, "
    "mpfb_check_rig_weights, mpfb_store_rig.",

    # Leaving Blender.
    "A character exists only in the .blend until mpfb_save_preset writes it; mpfb_list_presets "
    "lists them and mpfb_create_human_from_preset builds a NEW character from one. Export with "
    "mpfb_create_export_copy, then mpfb_export_character. For a community or documentation "
    "address, use mpfb_list_urls, which answers even without Blender, or mpfb_list_docs, never "
    "a URL of your own.",
))


def build_server() -> FastMCP:
    """The configured server, built but not run.

    Separate from ``main()`` so that the tool surface can be inspected without
    starting a stdio transport: ``tests/test_description_budget.py`` measures
    what an MCP client downloads before any work happens, and measuring the real
    server rather than a list of its own is what keeps a newly registered tool
    inside the budget rather than outside it.
    """
    mcp = _Server(
        "mpfb-mcp",
        instructions=INSTRUCTIONS,
    )

    from mpfbmcp.tools import (
        add_asset, add_rig, apply_expressions, check_intersections, check_mesh_asset,
        check_rig_weights,
        create_export_copy, create_human, create_rig,
        create_human_from_preset, export_character, generate_delete_group, generate_rigify_rig, get_character_summary, get_expression, get_face_units,
        get_macro_details, get_makeskin_material, get_material_settings, get_object_info, get_pose, get_pose_controls,
        get_rig_definition, get_rigify_hand_shape, get_status, get_target_stack,
        list_asset_materials, list_assets, list_docs, list_expressions, list_objects,
        list_presets, list_rigs, list_targets, list_urls, place_character, refit_human, remove_asset, reset_pose,
        save_expression, save_preset, set_asset_material, set_face_units, set_macro_details,
        set_makeskin_material, set_material_settings, set_pose_bones, set_pose_switches, set_rigify_hand_shape, set_skin,
        set_targets, store_makeskin_material, store_rig,
        symmetrize_targets, weight_rig, write_mesh_asset)
    add_asset.register(mcp)
    add_rig.register(mcp)
    apply_expressions.register(mcp)
    check_intersections.register(mcp)
    check_mesh_asset.register(mcp)
    check_rig_weights.register(mcp)
    create_export_copy.register(mcp)
    create_human.register(mcp)
    create_rig.register(mcp)
    create_human_from_preset.register(mcp)
    export_character.register(mcp)
    generate_delete_group.register(mcp)
    generate_rigify_rig.register(mcp)
    get_character_summary.register(mcp)
    get_expression.register(mcp)
    get_face_units.register(mcp)
    get_macro_details.register(mcp)
    get_makeskin_material.register(mcp)
    get_material_settings.register(mcp)
    get_object_info.register(mcp)
    get_pose.register(mcp)
    get_pose_controls.register(mcp)
    get_rig_definition.register(mcp)
    get_rigify_hand_shape.register(mcp)
    get_status.register(mcp)
    get_target_stack.register(mcp)
    list_asset_materials.register(mcp)
    list_assets.register(mcp)
    list_docs.register(mcp)
    list_expressions.register(mcp)
    list_objects.register(mcp)
    list_presets.register(mcp)
    list_rigs.register(mcp)
    list_targets.register(mcp)
    list_urls.register(mcp)
    place_character.register(mcp)
    refit_human.register(mcp)
    remove_asset.register(mcp)
    reset_pose.register(mcp)
    save_expression.register(mcp)
    save_preset.register(mcp)
    set_asset_material.register(mcp)
    set_face_units.register(mcp)
    set_macro_details.register(mcp)
    set_makeskin_material.register(mcp)
    set_material_settings.register(mcp)
    set_pose_bones.register(mcp)
    set_pose_switches.register(mcp)
    set_rigify_hand_shape.register(mcp)
    set_skin.register(mcp)
    set_targets.register(mcp)
    store_makeskin_material.register(mcp)
    store_rig.register(mcp)
    symmetrize_targets.register(mcp)
    weight_rig.register(mcp)
    write_mesh_asset.register(mcp)

    _shipped_without_source_indentation(mcp)
    _published_without_generated_keys(mcp)
    mcp.declared_arguments = {
        tool.name: frozenset(tool.parameters.get("properties", {}))
        for tool in _registered_tools(mcp)}
    return mcp


def main() -> int:
    build_server().run(transport="stdio")
    return 0
