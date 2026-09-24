"""
The ``mpfb_save_preset`` tool: keep the character that has been built.

Everything else in this package changes a ``.blend`` that nothing here can save.
This is the one tool whose effect **outlives the Blender session**, and it is
the first in the package to write a file outside the ``.blend`` at all - which
is where its two unusual decisions come from.

**``overwrite`` defaults to refusing.** Blender's undo stack does not reach a
file, there is no confirmation channel across MCP, and a caller cannot see the
directory to notice what it is about to replace. So a preset that already exists
is a refusal carrying the existing file's size and age, not a silent
replacement - and the caller decides.

**A preset is addressed by name, never by path**, in this tool and in
``mpfb_create_human_from_preset``. Three reasons, and each is enough on its own:
writing is confined to a directory MPFB owns rather than to anywhere the Blender
process can reach; it is the same namespace MPFB's own panels use, so a preset
saved here appears in MPFB's dropdown and vice versa, where two namespaces would
be two lists that disagree; and ``deserialize_from_json_file()`` extracts the
name with a regex whose match it never checks, so any path not of exactly the
shape ``human.<name>.json`` raises ``AttributeError: 'NoneType' object has no
attribute 'group'`` from inside MPFB. Confining the input makes that unreachable
rather than merely unlikely. The name rule itself is in
``mpfbmcp.artifact_names``.

**One tool where MPFB has two operators.** ``mpfb.save_new_human_presets``
refuses when the file exists, and ``mpfb.overwrite_human_presets`` is reachable
only from a dropdown of the presets that do. They differ in nothing else - both
call ``serialize_to_json_file(basemesh, file_name, True)`` and then report the
same warning - and a pair of MCP tools distinguished only by a precondition is
a pair an agent will pick wrongly. ``overwrite`` is that precondition.

**The generated-Rigify warning those two operators emit is deliberately not
reproduced.** See the command's docstring for why it overstates the problem and
what is reported instead.
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


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Save Character Preset",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_save_preset(
        preset_name: str,
        name: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """
        Save a character as an MPFB preset - phenotype, modeling targets, rig,
        body parts, garments, skin and eye materials - to be rebuilt later with
        `mpfb_create_human_from_preset` or from MPFB's own preset panel.
        **This writes a file outside the .blend, and nothing in Blender can
        undo it.**

        `preset_name` is a name, never a path: the file is always
        `human.<preset_name>.json` in MPFB's user config directory, and `path`
        in the response says which file that was. Letters, digits, `_`, `-` and `.`
        only, at most 64 characters, no leading dot - stricter than MPFB's own
        panel, which rejects only a space, so that a name cannot become a path.

        `basemesh_name` says which character was actually serialized.

        `overwrite` (default false) is the only thing standing between a call
        and the loss of an existing preset. With it false and the preset
        present, the tool refuses - `blocked_by: "preset_exists"`, nothing
        written - and `file_before` carries that file's size and age so the
        decision can be made from the response.

        **A generated Rigify rig does not round-trip.** MPFB stores the meta
        rig it was generated from, so loading the preset back gives you the
        meta rig and `mpfb_generate_rigify_rig` finishes the job. Nothing is
        lost and nothing fails; `rig_identified_as` and `rig_saved_as` show the
        substitution on the call where it happened.

        On `saved: true` (and so `performed: true`), `result` carries `path`,
        `size_bytes`, `modified`, `overwrote`, `file_before` (the replaced
        file's facts, or null), `config_dir`, `basemesh_name`, `rig_object_name`,
        `rig_identified_as`/`rig_saved_as`, and `contents` - what the written
        file actually holds, read back from it: `rig`, `proxy`, `bodyparts`,
        `clothes`, `skin_mhmat`, `skin_material_type`, `eyes_material_type`,
        `target_count`, `expression_count`, `makeup_count`.

        Refusals come back as `saved: false` with a `blocked_by`, having
        written nothing: `subject_not_found`, `preset_exists`,
        `not_a_human_project` (MPFB only serializes characters made within
        MPFB, not imported meshes), `rig_not_identifiable` (an armature MPFB
        cannot name - for a custom rig, its definition is no longer in your
        user data), `config_dir_missing` and `serialize_failed`.
        """
        # `result` (built in bridge/mpfb_bridge/commands/save_preset.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "save_preset",
            params={
                # The authoritative check, here rather than in Blender: this
                # name becomes a path. See mpfbmcp/artifact_names.py.
                "preset_name": validated_preset_name(preset_name),
                "name": arguments.validated_subject(name),
                # Not truthiness. This flag stands between a caller and an irreversible file
                # replacement, so overwrite="false" must not read as permission to overwrite.
                "overwrite": arguments.validated_flag(overwrite, "overwrite"),
            },
            # preset_files.py so that this tool, the catalogue and the load tool
            # cannot disagree about which names are legal or where the file is;
            # performed.py for the uniform flag every mutating tool reports.
        )
