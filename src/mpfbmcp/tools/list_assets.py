"""
The ``mpfb_list_assets`` tool: which assets are installed and could be applied.

The forward direction of the fragment convention that ``mpfb_get_object_info``
uses backwards: that tool says which asset an object was made *from*, this one
says what could be put *on* a character, naming each asset the way a later
``mpfb_add_asset`` / ``mpfb_set_skin`` will want it.

The library is large - thousands of files on an install with the community packs
- so this is a filtering tool rather than a listing one, and its answer is
capped. That makes the response a subset by design, which is the one thing it
must never be mistaken for the library itself; ``truncated``, ``total_count``,
``subdir_recognized`` and ``pack_recognized`` all exist for that.

What the tool description no longer carries lives one link away: the two
costs of MPFB's asset cache are
[MPFB caches what it scans](../../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides),
and the pack attribution is
[How tools report a derived rather than recorded fact](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact).

Nothing here validates a subdir or pack name. The installed library is the
authority on both and is only readable from inside Blender; a vocabulary kept on
this side would drift from it silently.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import backend

# A page of 1000 entries is already more than an agent can usefully read; the
# ceiling is here so that an over-broad call is capped rather than answered with
# the whole library.
MAX_LIMIT = 1000


def _validated_text(value: object, argument: str, hint: str) -> str | None:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            "{} must be a string or omitted, got {!r}".format(argument, value))
    if not value.strip():
        # An explicitly empty value and an omitted one arise from different
        # mistakes, so the empty one is never quietly treated as the omission.
        raise ValueError("{} must not be empty or whitespace; {}".format(argument, hint))
    return value


def _validated_count(value: object, argument: str, maximum: int | None) -> int:
    """Reject a non-int, a bool, a negative, and a limit above the ceiling."""
    if isinstance(value, bool) or not isinstance(value, int):
        # bool is a subclass of int, so `limit=True` would otherwise page one
        # entry at a time rather than fail.
        raise ValueError(
            "{} must be an int, got {!r}".format(argument, value))
    if value < 0:
        raise ValueError("{} must not be negative, got {!r}".format(argument, value))
    if maximum is not None and value > maximum:
        raise ValueError(
            "{} must be at most {}, got {!r}".format(argument, maximum, value))
    return value


def _validated_refresh(refresh: object) -> bool:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if not isinstance(refresh, bool):
        # Deliberately not truthiness: 0/1 and "false" are how a caller signals
        # a bool it did not manage to build, and quietly accepting them would
        # make `refresh="false"` rescan the entire library.
        raise ValueError(
            "refresh must be a bool, got {!r}".format(refresh))
    return refresh


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List Available Assets",
            # Nothing in the scene is touched and no file is written. It does
            # populate MPFB's own asset cache, which is a side effect inside
            # Blender - see the docstring's note on cost.
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_list_assets(asset_subdir: str | None = None,
                         name_contains: str | None = None,
                         pack: str | None = None,
                         limit: int = 200,
                         offset: int = 0,
                         refresh: bool = False) -> dict[str, object]:
        """
        Find the MakeHuman assets installed in this Blender - clothes, hair,
        eyes, eyebrows, eyelashes, teeth, tongue, topology proxies, skins,
        poses - narrowed by subdir, by a keyword in the name, and by asset
        pack. Adds nothing to the scene. The forward counterpart of
        `mpfb_get_object_info`, which says what an existing object was made
        from.

        **The answer is capped and is usually a subset.** Check `truncated`
        before concluding an asset is not installed; `total_count` says how
        many matched. The first call for a subdir is the slow one: MPFB loads a
        preview image per asset, once per subdir per Blender session.

        Arguments, all optional and combining with AND:

          - `asset_subdir` - one of `"clothes"`, `"hair"`, `"eyes"`,
            `"eyebrows"`, `"eyelashes"`, `"teeth"`, `"tongue"`,
            `"proxymeshes"`, `"skins"`, `"poses"`, `"ink_layers"`, matched
            exactly and case-insensitively. Omit it to search every subdir,
            then read `counts_by_subdir` to pick a narrower one.
          - `name_contains` - case-insensitive substring of the asset's name or
            label.
          - `pack` - substring of an installed pack's name, so `"hair03"` finds
            `hair03_ccby`.
          - `limit` (default 200, max 1000) and `offset` - paging over the
            matched set, sorted by subdir then name.
          - `refresh` - rescan first. Needed only when assets were installed
            after Blender started; it rescans the **whole** library and writes
            MPFB's caches.

        `result` carries:

          - `assets`: this page's entries, each with `name` (filename without
            extension), `label` (MPFB's display text), `fragment`, `path`,
            `object_type`, `asset_subdir`, `file_type`, `pack`,
            `pack_ambiguous` and `thumb_path`.
          - `counts_by_subdir`: how many assets each scanned subdir holds,
            ignoring `name_contains`, `pack` and the cap.
          - `requested_subdir`/`subdir_recognized`/`known_subdirs` and
            `requested_pack`/`pack_recognized`/`known_packs`, so a misspelling
            is distinguishable from an empty subdir or pack.
          - `asset_roots_searched`: per subdir, the directories actually
            scanned. A configured data root that does not hold that subdir is
            not searched, which is the usual explanation for "I installed it
            and it is not listed".
          - `count`, `total_count`, `truncated`, `offset`, `limit`.

        **How to name an asset when applying it.** Pass an entry's `path`
        (absolute) or its `fragment` (`"fedora/fedora.mhclo"`, what MPFB
        records on the resulting object and what survives a move to another
        machine) to `mpfb_add_asset`, together with its `object_type`, which is
        exactly that tool's required `asset_type`. Assets in `skins` are
        materials rather than meshes and go to `mpfb_set_skin` instead. A
        fragment is **not** a path; handing one to a file-opening tool fails
        confusingly. For `skins`, `poses` and `ink_layers` the `object_type`
        (`"Material"`, `"Pose"`, `"Other"`) says what the asset is rather than
        naming an argument.

        **`pack` is derived from a directory-name convention, not recorded by
        MPFB.** `pack: null` is ordinary for a hand-installed asset, and
        `pack_ambiguous: true` means two packs claim the name and the reported
        one is a coin toss. `total_count` can under-report too: MPFB's cache is
        keyed by a label derived from the filename alone, so two assets whose
        filenames differ only in case or underscores collapse into one entry.
        """
        # `result` (built in bridge/mpfb_bridge/commands/list_assets.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "list_assets",
            params={
                "asset_subdir": _validated_text(
                    asset_subdir, "asset_subdir",
                    "omit it to search every asset subdir"),
                "name_contains": _validated_text(
                    name_contains, "name_contains",
                    "omit it to match every name"),
                "pack": _validated_text(
                    pack, "pack", "omit it to match assets from every pack"),
                "limit": _validated_count(limit, "limit", MAX_LIMIT),
                "offset": _validated_count(offset, "offset", None),
                "refresh": _validated_refresh(refresh),
            },
            # Shared with mpfb_add_asset's payload, which is handed the
            # object_type and fragment reported here and has to map them back to
            # an asset subdir to find the file. One implementation of MPFB's
            # section table, so the catalogue and the action cannot disagree
            # about what an entry means.
        )
