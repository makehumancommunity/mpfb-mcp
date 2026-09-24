"""
The ``mpfb_save_expression`` tool: keep a composed face as an expression file.

A face composed with ``mpfb_set_face_units`` survives nothing - not a preset,
and not the next ``mpfb_apply_expressions``, which rebuilds the face from the
stack. Saving it as an expression file is the only way across: once
``mpfb_apply_expressions`` puts the new fragment on the stack in ``replace``
mode, the library's rebuilds reproduce the face instead of erasing it, and a
preset carries it.

**It writes a file outside the ``.blend``**, which is where its shape comes
from, exactly as ``mpfb_save_preset``'s does
([mutating-tools.md](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)):
``overwrite`` defaults to refusing, the name is a name and never a path - the
rule is ``mpfbmcp.artifact_names``, shared with the preset tools and checked
before anything is sent - and the absolute path is in every answer.

**It does not also apply the file.** One call with two effects is a call whose
second half can refuse after its first has written a file, which is a partial
outcome no mutating tool here is allowed. The answer names the next call
instead, in ``apply_with``.

The six metadata arguments are flat and optional, one schema line each, and the
description does not re-explain the file format. ``license`` defaults to
``"CC0"``, which is MPFB's composer panel's default and is reported back in
``metadata``. See the command's docstring,
``bridge/mpfb_bridge/commands/save_expression.py``, for why it saves the shape
keys rather than the composer's sliders, and why it refuses a shadowed name.
"""

from __future__ import annotations

__all__ = (
    "MAX_TAGS",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import backend
from mpfbmcp.artifact_names import validated_expression_name

# Tags are a filter vocabulary for a human browsing a library; far more than
# this is a caller that put the wrong list in the wrong argument.
MAX_TAGS = 50


def _validated_subject(name: object) -> str | None:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValueError("subject must be a string or omitted, got {!r}".format(name))
    if not name.strip():
        raise ValueError(
            "subject must not be empty or whitespace; omit it to use the active object")
    return name


def _validated_overwrite(overwrite: object) -> bool:
    if not isinstance(overwrite, bool):
        # Deliberately not truthiness. This is the flag standing between a
        # caller and an irreversible file replacement, so `overwrite="false"`
        # must not read as permission to overwrite.
        raise ValueError("overwrite must be a bool, got {!r}".format(overwrite))
    return overwrite


def _validated_text(argument: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("{} must be a string, got {!r}".format(argument, value))
    return value


def _validated_tags(tags: object) -> list[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        # MPFB's save_expression would split a comma-separated string itself;
        # accepting one here would make "a, b" and ["a, b"] mean different
        # things depending on which side of the socket looked first.
        raise ValueError("tags must be a list of strings or omitted, got {!r}".format(tags))
    if len(tags) > MAX_TAGS:
        raise ValueError("tags must hold at most {} entries, got {}".format(MAX_TAGS, len(tags)))
    for position, tag in enumerate(tags):
        if not isinstance(tag, str):
            raise ValueError("tags[{}] must be a string, got {!r}".format(position, tag))
    return list(tags)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Save Expression",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_save_expression(  # pylint: disable=too-many-arguments
        name: str,
        subject: str | None = None,
        overwrite: bool = False,
        description: str = "",
        tags: list[str] | None = None,
        author: str = "",
        copyright: str = "",  # pylint: disable=redefined-builtin
        license: str = "CC0",  # pylint: disable=redefined-builtin
        homepage: str = "",
    ) -> dict[str, object]:
        """
        Save a MakeHuman character's live face - every non-zero ARKit face unit
        - as a named expression file that `mpfb_apply_expressions` can apply
        and presets can carry. **This writes a file outside the .blend, and
        nothing in Blender can undo it.** The character is not changed.

        `name` is a name, never a path: the file is `<name>.json` in the
        expressions directory of MPFB's user data, and `path` and `fragment`
        are in every answer. Same rule as preset names: letters, digits, `_`,
        `-`, `.`, at most 64 characters, no leading dot. The character is named
        by `subject` (any object in its family; omit for the active one).

        What is saved is the **whole** live face, including what applied
        expressions contribute. To make it durable, call
        `mpfb_apply_expressions` with `mode: "replace"` and the new `fragment`
        at 1.0 - replace, not merge, or the stack counts twice. `result`'s
        `apply_with` holds exactly those arguments.

        `overwrite` (default false) refuses an existing file
        (`blocked_by: "expression_exists"`, `previous_file` giving its size and
        age); the directory is shared with installed asset packs. Other
        refusals, nothing written: `name_shadowed` (a same-named file in a
        higher-priority data root would hide this one from MPFB for good -
        `shadowed_by` names it), `empty_expression` (every unit is 0.0),
        `subject_not_found`.

        Optional metadata, stored as given: `description`, `tags` (list of
        strings), `author`, `copyright`, `license` (default `"CC0"`, MPFB's
        composer default), `homepage`. On success `result` also carries
        `face_units` and `metadata` as read back from the file, `overwrote`,
        and `panel_synced` (whether MPFB's library panel gained the slider).
        """
        # `result` (built in bridge/mpfb_bridge/commands/save_expression.py) is
        # plain JSON-safe data.
        return backend.send(
            "save_expression",
            params={
                # The authoritative check, here rather than in Blender: this
                # name becomes a path. See mpfbmcp/artifact_names.py.
                "name": validated_expression_name(name),
                "subject": _validated_subject(subject),
                "overwrite": _validated_overwrite(overwrite),
                "description": _validated_text("description", description),
                "tags": _validated_tags(tags),
                "author": _validated_text("author", author),
                "copyright": _validated_text("copyright", copyright),
                "license": _validated_text("license", license),
                "homepage": _validated_text("homepage", homepage),
            },
        )
