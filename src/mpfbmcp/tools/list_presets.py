"""
The ``mpfb_list_presets`` tool: which characters have been saved.

The catalogue half of the preset trio. ``mpfb_save_preset`` writes into MPFB's
user config directory and ``mpfb_create_human_from_preset`` reads out of it;
this says what is in there, under the names those two take.

It is a catalogue of *files* rather than of anything MPFB computes, which makes
it the first listing tool here whose interesting fields - size and age - come
from ``os.stat`` rather than from a service. MPFB's own list is bare names, and
nothing in MPFB knows how old a preset is.

Nothing is capped and nothing is paged. Every other listing tool in this package
answers from a scan of a user's whole asset library or of MPFB's bundled target
index, where an answer really can be thousands of entries; a preset collection is
tens of files - the largest seen while this was written held 45 - so a
``truncated`` flag would be an obligation on every caller to guard against a case
that does not arise.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import codegen
from mpfbmcp.connection import send_code


def _validated_refresh(refresh: object) -> bool:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if not isinstance(refresh, bool):
        # Deliberately not truthiness: 0/1 and "false" are how a caller signals
        # a bool it did not manage to build, and quietly accepting them would
        # make `refresh="false"` rescan the disk.
        raise ValueError("refresh must be a bool, got {!r}".format(refresh))
    return refresh


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List Character Presets",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_list_presets(refresh: bool = False) -> dict[str, object]:
        """
        List the character presets saved in MPFB's user config directory -
        MPFB's "save files", the same ones its own preset panel offers. Each
        entry's `name` is what `mpfb_save_preset` and
        `mpfb_create_human_from_preset` take; neither accepts a path.

        **Not capped and not paged**, unlike the other listing tools: a preset
        collection is tens of files. No preset is parsed, so this says nothing
        about what is *in* one; `mpfb_create_human_from_preset` reports that for
        the one it loads.

        `refresh=true` rescans the directory through MPFB. MPFB caches the list
        for the Blender session and rebuilds it only when a preset is saved, so
        one written by hand, by another Blender or by an earlier session is
        missing until then - but you do not need to pass `refresh` to find that
        out: `missing_from_mpfb_list` already names any preset file the cache
        does not hold, because this tool lists the directory itself as well.

        `result` carries:

          - `presets`: per preset `name`, `path`, `size_bytes`, `modified`
            (ISO 8601 with a UTC offset) and `exists`. **`size_bytes` and
            `modified` come from `os.stat` here**, not from MPFB, which records
            neither. `exists: false` means MPFB's cached list still names a
            preset whose file has been deleted.
          - Per preset, `addressable` and `not_addressable_reason`. MPFB's own
            panel accepts names these tools will not - anything that could
            become a path - so a preset saved by hand can be listed here and
            refused by the other two. Rare, and worth seeing here rather than
            in a refusal.
          - `config_dir` and `config_dir_exists`: the directory that was
            scanned, reported whether or not anything was found, so an empty
            list is an answer rather than an ambiguity.
          - `count`, `files_in_config_dir`, `missing_from_mpfb_list`,
            `refreshed`, `listing_failed` (a sentence when MPFB could not read
            the directory at all) and `message`.
        """
        code = codegen.assemble(
            "list_presets.py",
            bootstrap="raising",
            params={"refresh": _validated_refresh(refresh)},
            # Shared with the two tools that act on what this lists: one rule
            # for which names are legal, one construction of the path they
            # address. A preset this tool names must be one those two can open.
            shared=["preset_files.py"],
        )
        # `result` (built in codegen/payloads/list_presets.py) is plain JSON-safe
        # data, so strict_json=True surfaces a clear error if that ever stops
        # being true.
        return send_code(code, strict_json=True)
