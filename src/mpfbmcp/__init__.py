"""
MCP server for MPFB (MakeHuman Plugin For Blender).

Proof-of-concept: exposes MPFB-specific tools that run inside a running Blender
instance. A tool names a command from a closed vocabulary and hands over its
parameters; the MPFB Bridge add-on - this project's own, in ``bridge/`` -
dispatches it and answers over its TCP socket (see bridge_connection.py).

This requires:
  - Blender running with MPFB and the MPFB Bridge add-on installed & enabled.
  - The bridge's command server started (from the add-on's preferences panel,
    or ``blender --background --command mpfb_bridge`` for a headless one).
  - This server's client configuring MPFB_BRIDGE_HOST / MPFB_BRIDGE_PORT to
    match, if not using the defaults (127.0.0.1:9877).
"""

from __future__ import annotations

__all__ = (
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
        instructions=(
            "Tools for creating MakeHuman characters via the MPFB Blender add-on. "
            "Requires the MPFB Bridge add-on's command server to be running inside "
            "Blender (see MPFB_BRIDGE_HOST / MPFB_BRIDGE_PORT), with the MPFB "
            "extension installed and enabled in that Blender instance. When an "
            "MPFB tool fails unexpectedly, call mpfb_get_status first: it reports "
            "whether MPFB is present, initialized and correctly configured. To act "
            "on a character this session did not create, find it with "
            "mpfb_list_objects and identify it with mpfb_get_object_info rather "
            "than guessing from Blender object names. To find an asset to apply "
            "or a rig to add, use mpfb_list_assets or mpfb_list_rigs, and "
            "mpfb_list_targets for the modeling morphs: each names its entries "
            "the way the acting function will want them. Order matters when "
            "building a character and MPFB reports no error when it is wrong: "
            "add the rig with mpfb_add_rig BEFORE attaching any clothes, since "
            "a garment is rigged only if a rig exists when it is attached and "
            "nothing rigs it afterwards. A rigify.* rig is only a meta rig when "
            "mpfb_add_rig returns; attach the clothes with mpfb_add_asset "
            "and then finish it with mpfb_generate_rigify_rig, which is not "
            "undoable. mpfb_add_asset equips one garment, body part or "
            "topology proxy per call and requires an asset_type - pass "
            "mpfb_list_assets' object_type, since MPFB's own default "
            "silently turns hair into clothes. Take an asset off with "
            "mpfb_remove_asset rather than by deleting the object, or the "
            "body stays masked under something that is no longer there. "
            "A character with no skin is grey: give it one with mpfb_set_skin, "
            "whose skin_type picks between five entirely different materials "
            "and defaults to MAKESKIN as MPFB's own panel does, not to the "
            "ENHANCED_SSS its service function defaults to. Applying a skin "
            "deletes every material already on the body, and on the body proxy "
            "too. To recolour a garment rather than the body, list its "
            "alternatives with mpfb_list_asset_materials - they are not in "
            "mpfb_list_assets' answer - and apply one with "
            "mpfb_set_asset_material. To change an existing "
            "character rather than create one, read it with "
            "mpfb_get_character_summary first - one call for its phenotype, "
            "rig, assets, skin, morphs and face - and change only what should "
            "differ: mpfb_set_macro_details leaves unnamed sliders alone. "
            "For the individual morphs below the phenotype level, read "
            "mpfb_get_target_stack and write mpfb_set_targets - which is "
            "batched, so send a whole series of modeling changes as one call "
            "rather than one call each, and which applies nothing at all if any "
            "entry fails to resolve. mpfb_symmetrize_targets repairs a "
            "left/right asymmetry that MPFB itself has no way to undo; run it "
            "with dry_run first. "
            "To give a character an expression, mpfb_get_face_units reads the "
            "52 ARKit face units and mpfb_set_face_units composes them; both "
            "need the faceunits01 asset pack, and a composed face is transient "
            "- not saved by mpfb_save_preset. "
            "Changing a body's shape moves it out from under everything fitted "
            "to it, so finish a series of modeling changes with one call to "
            "mpfb_refit_human. "
            "A character exists only in the running .blend until it is saved "
            "as an MPFB preset: mpfb_save_preset writes one - the only file "
            "any tool here creates, and not undoable - mpfb_list_presets says "
            "which exist, and mpfb_create_human_from_preset builds a NEW "
            "character from one rather than loading into the current one. "
            "A preset is addressed by its preset_name, never by a path. "
            "Neither of the two lookup tools acts on Blender at all: they hand "
            "out addresses for the client to retrieve, and neither fetches "
            "anything itself. mpfb_list_urls gives the community sites - where "
            "to download MPFB, get asset packs, ask on the forum, file a bug - "
            "and answers even when MPFB or Blender is unreachable, which is "
            "when those links matter most. mpfb_list_docs gives MPFB's "
            "developer documentation, one document per service and per file "
            "format, for when a tool response does not say how MPFB actually "
            "does something. Use them rather than composing a URL. "
            "Conventions every tool here shares, so that no single tool's "
            "description repeats them. Each returns the same envelope: "
            "check `status` (\"ok\" or \"error\"), then read `result` - and on "
            "a failure branch on `error`, a short slug, rather than on the "
            "human sentence in `message`. A tool "
            "acting on an existing character takes `name` - any object in that "
            "character's family, the basemesh, its rig or a garment fitted to "
            "it - or omit `name` to use whatever is active in Blender, and the "
            "response names the object actually worked on. A tool that cannot "
            "do what was asked answers rather than failing, so read `found` "
            "(the subject could not be resolved), `ready` and `blocked_by` (the "
            "world was not in a fit state, and which way) before concluding a "
            "call went wrong. Every tool that changes a character reports "
            "`performed`, a real boolean, true exactly when something changed; "
            "most keep a verb beside it (`added`, `applied`, `removed`, "
            "`generated`, `recalculated`, `refit_performed`), and the batch "
            "tools list their per-entry writes as `changes`; the tool says where "
            "the flag and its verb can differ. A capped listing "
            "always reports `truncated`, `total_count`, `offset` and `limit`: "
            "check `truncated` before concluding something is not installed."
        ),
    )

    from mpfbmcp.tools import (
        add_asset, add_rig, apply_expressions, create_human, create_human_from_preset,
        generate_rigify_rig, get_character_summary, get_expression, get_face_units,
        get_macro_details, get_object_info, get_status, get_target_stack, list_asset_materials,
        list_assets, list_docs, list_expressions, list_objects, list_presets, list_rigs,
        list_targets, list_urls, refit_human, remove_asset, save_expression, save_preset,
        set_asset_material, set_face_units, set_macro_details, set_skin, set_targets,
        symmetrize_targets)
    add_asset.register(mcp)
    add_rig.register(mcp)
    apply_expressions.register(mcp)
    create_human.register(mcp)
    create_human_from_preset.register(mcp)
    generate_rigify_rig.register(mcp)
    get_character_summary.register(mcp)
    get_expression.register(mcp)
    get_face_units.register(mcp)
    get_macro_details.register(mcp)
    get_object_info.register(mcp)
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
    refit_human.register(mcp)
    remove_asset.register(mcp)
    save_expression.register(mcp)
    save_preset.register(mcp)
    set_asset_material.register(mcp)
    set_face_units.register(mcp)
    set_macro_details.register(mcp)
    set_skin.register(mcp)
    set_targets.register(mcp)
    symmetrize_targets.register(mcp)

    _shipped_without_source_indentation(mcp)
    mcp.declared_arguments = {
        tool.name: frozenset(tool.parameters.get("properties", {}))
        for tool in _registered_tools(mcp)}
    return mcp


def main() -> int:
    build_server().run(transport="stdio")
    return 0
