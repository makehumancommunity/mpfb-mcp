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
``asset_subdir_recognized`` and ``pack_recognized`` all exist for that.

What the tool description no longer carries lives one link away: the two
costs of MPFB's asset cache are
[MPFB caches what it scans](../../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides),
and the pack attribution is
[How tools report a derived rather than recorded fact](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact).

``license`` names the argument after the answer key it filters, which shadows
a Python builtin inside one function body and nowhere else; the glossary's
rule that an argument is named for what it filters wins over that.

Nothing here validates a subdir, pack or license name. The installed library is the
authority on both and is only readable from inside Blender; a vocabulary kept on
this side would drift from it silently.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

# A page of 1000 entries is already more than an agent can usefully read; the
# ceiling is here so that an over-broad call is capped rather than answered with
# the whole library.
MAX_LIMIT = 1000


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
                         license: str | None = None,  # pylint: disable=redefined-builtin
                         limit: int = 200,
                         offset: int = 0,
                         refresh: bool = False) -> dict[str, object]:
        """
        Find the MakeHuman assets installed in this Blender - garments, hair,
        eyes, eyebrows, eyelashes, teeth, tongue, body proxies, skins,
        poses - narrowed by subdir, name, asset pack and license. Adds nothing to the scene. The forward counterpart of
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
            then read `counts_by_asset_subdir` to pick a narrower one.
          - `name_contains` - case-insensitive substring of the asset's name or
            label.
          - `pack` - substring of an installed pack's name, so `"hair03"` finds
            `hair03_ccby`.
          - `license` - exact, case-insensitive: `"CC0"`, `"CC-BY"`. An asset
            with no recorded license never matches.
          - `limit` (default 200, max 1000) and `offset` - paging over the
            matched set, sorted by subdir then name.
          - `refresh` - rescan first. Needed only when assets were installed
            after Blender started; it rescans the **whole** library and writes
            MPFB's caches.

        `result` carries:

          - `assets`: this page's entries, each with `name` (filename without
            extension), `label` (MPFB's display text), `fragment`, `path`,
            `object_type`, `asset_subdir`, `file_type`, `pack` (the claimant
            your filter matched), `packs`, `pack_ambiguous`, `license`,
            `author`, `source_url` (the page to credit) and `thumb_path`.
          - `counts_by_asset_subdir`: how many assets each scanned subdir
            holds, ignoring `name_contains`, `pack` and the cap.
          - `counts_by_license` and `license_unknown_count`: the matches
            before the `license` filter and the cap.
          - `requested_asset_subdir`/`asset_subdir_recognized`/
            `known_asset_subdirs` and `requested_pack`/`pack_recognized`/
            `known_packs`/`matched_packs` (per pack, the installed assets it
            claims; 0 means none on disk) and `requested_license`/
            `license_recognized`/`known_licenses`, so a misspelling is distinguishable from an empty subdir or pack.
          - `asset_roots_searched`: per subdir, the directories actually
            scanned. A configured data root that does not hold that subdir is
            not searched, which is the usual explanation for "I installed it
            and it is not listed".
          - `count`, `total_count`, `truncated`, `offset`, `limit`.

        **How to name an asset when applying it.** Pass an entry's `path`
        (absolute) or its `fragment` (`"fedora/fedora.mhclo"`, what MPFB
        records on the resulting object and what survives a move to another
        machine) to `mpfb_add_asset`, together with its `object_type`. Assets
        in `skins` are materials rather than meshes and go to `mpfb_set_skin`
        instead. A fragment is **not** a path; handing one to a file-opening
        tool fails confusingly. For `skins`, `poses` and `ink_layers` the
        `object_type` (`"Material"`, `"Pose"`, `"Other"`) says what the asset
        is rather than naming an argument.

        **`pack` and `license` are derived from a directory name, not recorded
        by MPFB.** `null` is ordinary for a hand-installed asset and means
        unknown, never permissive; `attribution_conflicts` lists claimants that
        disagree. `total_count` can under-report: MPFB's cache is
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
                "asset_subdir": arguments.validated_text(
                    asset_subdir, "asset_subdir",
                    "omit it to search every asset subdir"),
                "name_contains": arguments.validated_text(
                    name_contains, "name_contains",
                    "omit it to match every name"),
                "pack": arguments.validated_text(
                    pack, "pack", "omit it to match assets from every pack"),
                "license": arguments.validated_text(
                    license, "license", "omit it to match assets under any license"),
                "limit": arguments.validated_count(limit, "limit", MAX_LIMIT),
                "offset": arguments.validated_count(offset, "offset", None),
                # Not truthiness: refresh="false" would rescan the entire library.
                "refresh": arguments.validated_flag(refresh, "refresh"),
            },
            # Shared with mpfb_add_asset's command, which is handed the
            # object_type and fragment reported here and has to map them back to
            # an asset subdir to find the file. One implementation of MPFB's
            # section table, so the catalogue and the action cannot disagree
            # about what an entry means.
        )
