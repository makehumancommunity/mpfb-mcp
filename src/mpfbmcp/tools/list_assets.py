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

from mpfbmcp import codegen
from mpfbmcp.connection import send_code

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
        eyes, skins, poses and the rest - narrowed by subdir, by a keyword in
        the name, and by asset pack. Adds nothing to the scene.

        Use this to answer "what could I put on this character": it is the
        forward counterpart of `mpfb_get_object_info`, which says what an
        existing object was made from.

        **The answer is capped and is usually a subset.** Check `truncated`
        before concluding an asset is not installed: `true` means entries
        matched that this page did not return, and `total_count` says how many
        matched in total. Narrow with `name_contains` or page with
        `offset`/`limit` rather than assuming a short list is the whole library.

        Arguments, all optional and combining with AND:

          - `asset_subdir` - one of MPFB's asset subdirs (`"clothes"`, `"hair"`,
            `"eyes"`, `"eyebrows"`, `"eyelashes"`, `"teeth"`, `"tongue"`,
            `"proxymeshes"`, `"skins"`, `"poses"`, `"ink_layers"`). Matched
            exactly, case-insensitively. Omit it to search every subdir - which
            is the slow call, and the one whose `counts_by_subdir` tells you
            which subdir to ask about next.
          - `name_contains` - case-insensitive substring of the asset's name or
            label.
          - `pack` - matched against installed pack names by substring, MPFB's
            own semantics, so `"hair03"` finds the pack `hair03_ccby`.
          - `limit` (default 200, max 1000) and `offset` - paging over the
            matched set, which is sorted by subdir then name so that two pages
            of one query neither skip nor repeat.
          - `refresh` - rescan before answering. Opt-in because it rescans the
            **whole** library rather than the requested subdir, and writes
            MPFB's caches, invalidating its alternative-material and pack
            metadata along the way. Needed only when assets were installed
            after Blender started; the default path scans only a subdir nothing
            has scanned yet.

        Returns blender_mcp's response envelope. On `status: "ok"`, `result`
        carries:

          - `assets`: the matched entries for this page, each with `name`
            (the filename without extension), `label` (MPFB's display text),
            `fragment`, `path`, `object_type`, `asset_subdir`, `file_type`,
            `pack`, `pack_ambiguous` and `thumb_path`.
          - `count`, `total_count`, `truncated`, `offset`, `limit`.
          - `counts_by_subdir`: how many assets each scanned subdir holds,
            ignoring `name_contains`, `pack` and the cap.
          - `requested_subdir`/`subdir_recognized`/`known_subdirs` and
            `requested_pack`/`pack_recognized`/`known_packs`, so a misspelling
            is distinguishable from an empty subdir or an empty pack.
          - `asset_roots_searched`: per subdir, the directories actually
            scanned. A configured data root that does not contain that subdir is
            not searched, which is the usual explanation for "I installed it and
            it is not listed".

        **How to name an asset when applying it.** `path` is the absolute file,
        and it is what `HumanService.add_mhclo_asset()` (clothes, hair, eyes,
        eyebrows, eyelashes, teeth, tongue, proxymeshes) and
        `set_character_skin()` (skins) actually take - the two are not
        interchangeable, a skin is a material rather than a mesh asset. For the
        subdirs `add_mhclo_asset()` handles, `object_type` is not decoration
        either: it is exactly the string that function's `asset_type` argument
        wants, and it defaults to `"Clothes"`, so hair added without it becomes
        clothes. For `skins`, `poses` and `ink_layers` the `object_type`
        (`"Material"`, `"Pose"`, `"Other"`) says what the asset is rather than
        naming an argument - those are not added by `add_mhclo_asset()` at all.

        `fragment` (`"fedora/fedora.mhclo"`) is the portable identifier: it is
        exactly what MPFB records on the resulting object as its `asset_source`,
        what `AssetService.find_asset_absolute_path()` resolves back to a path,
        and what stays valid across machines whose asset roots differ. Prefer
        the fragment when storing or passing an asset around, and note it is
        **not** a path - handing it to a file-opening tool fails confusingly.

        **`pack` is derived, not recorded.** MPFB stores no link from a file
        back to the pack that installed it. This matches the name of the asset's
        containing directory against the asset names in the installed packs'
        metadata, which is a naming convention rather than a record. So: an
        asset installed by hand matches nothing and gets `pack: null`, which is
        ordinary; an asset claimed by more than one pack gets
        `pack_ambiguous: true`, with `pack` holding the first alphabetically
        while the `pack` filter still matches on any of them; and pack metadata
        exists only under the user data root, so an asset under another root
        cannot be attributed even when it did come from a pack.

        **Two costs, both real.** The first call for a subdir populates MPFB's
        asset cache, which loads a Blender preview image for every asset that
        has a thumbnail. That is the slow, memory-hungry part, it is paid once
        per subdir per Blender session, and it is the same cache MPFB's own
        asset panels fill - a session where those were opened has already paid
        it. Rescanning afterwards, `refresh` included, does not reload a
        preview it already holds.

        The second cost is that the cache is keyed by *label*, derived from the
        filename alone, so two assets whose filenames differ only in case or
        underscores collapse into one entry: `total_count` can under-report, and
        one of the two is missing entirely rather than merely mislabelled. That
        is a limitation of MPFB's cache, not of the filters here, and it is why
        a listing count can disagree with a count of files on disk.
        """
        # `result` (built in codegen/payloads/list_assets.py) is always plain
        # JSON-safe data - notably the cached items' `thumb` preview object is
        # dropped rather than reported - so strict_json=True to surface a clear
        # error if that ever stops being true.
        code = codegen.assemble(
            "list_assets.py",
            bootstrap="raising",
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
        )
        return send_code(code, strict_json=True)
