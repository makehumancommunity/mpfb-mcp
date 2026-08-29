"""
The ``mpfb_list_targets`` tool: which modeling targets could be set, and how named.

The catalogue behind a later ``mpfb_set_target_value``. A target is addressed by
the name of the *shape key* it becomes, which is derived from its filename and is
not always equal to it, so the identifier is reported as its own field rather
than left for the caller to reassemble.

Two sources, answered differently. The bundled targets are indexed by a ~140 KB
``target.json`` that is far too large to return and exactly the sort of file a
caller with the same filesystem can read for itself, so its path is reported and
its sections are browsable one at a time. The user data directories have no index
and are scanned per call.

Nothing here validates a section name. Half the sections are synthesized from the
user's own directories and cannot be known on this side of the socket at all;
``section_recognized`` and ``known_sections`` answer that from inside Blender.
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
# every target on the system.
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


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List Available Targets",
            # Genuinely read-only, unlike mpfb_list_assets: directory walks and
            # one JSON read, populating no MPFB cache and loading no preview.
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_list_targets(section: str | None = None,
                          name_contains: str | None = None,
                          limit: int = 200,
                          offset: int = 0) -> dict[str, object]:
        """
        Find the MakeHuman modeling targets available in this Blender - the
        named morphs like `nose-scale-depth-incr` that shape a character - and
        report each one under the name that setting it will require. Changes
        nothing.

        Macro details and phenotype (gender, age, weight, muscle, height,
        proportions) are **not** here: those are attributes on the basemesh
        rather than target files, and are `mpfb_set_macro_details`' territory.

        **The answer is capped.** Check `truncated` before concluding a target
        does not exist: `true` means entries matched that this page did not
        return, and `total_count` says how many matched. Narrow with
        `name_contains` or page with `offset`/`limit`.

        Arguments, all optional:

          - `section` - a section name, from `target.json` or synthesized from a
            user target directory. Matched exactly, case-insensitively. Omit it
            for the overview.
          - `name_contains` - case-insensitive substring, applied to category
            and target names alike.
          - `limit` (default 200, max 1000) and `offset` - paging over whichever
            list the call is about: a section's `categories` when `section` names
            one that has them, `user_targets` otherwise. Both are sorted before
            paging, so two pages of one query neither skip nor repeat.

        Returns blender_mcp's response envelope. On `status: "ok"`, `result`
        carries:

          - `target_json_path` and `target_json_exists`: the bundled index of
            modeling targets. It is ~140 KB of JSON and is not returned here -
            a client that can read the Blender host's filesystem should parse it
            directly and skip most of this tool. `system_targets_dir` is the
            directory holding it.
          - `sections`: every section, each `{name, label, source,
            category_count, target_count}`. Small - around thirty entries - and
            always present. `source` is `"system"` for a `target.json` section,
            `"user"` for one synthesized from a user directory, and **`"both"`
            when a user directory shares its name with a bundled section**,
            which is common: MPFB merges the two rather than keeping them apart,
            so asking for such a section returns the bundled categories *and*
            that directory's user targets.
          - `categories`: present when `section` named one with bundled
            categories, each `{name, label, has_left_and_right, targets,
            opposites}` straight from `target.json`. `opposites` is the
            `decr`/`incr` and left/right pairing MPFB's modeling sliders are
            built from - it is what says that setting one target meaningfully
            means clearing its opposite. `null` when no section was asked for,
            or when the one asked for is only a user directory.
          - `user_targets`: the targets found in the user data directories,
            filtered to `section` when one was given. See below on naming.
          - `unindexed_system_target_dirs`: bundled target directories with no
            `target.json` section at all, each with a count. `target.json` reads
            as the complete list of bundled targets and it is not; these hold
            targets that can be loaded but that the index never mentions.
          - `user_target_dirs`: the directories actually scanned, so a user
            whose target did not appear can see where it was looked for.
          - `requested_section`/`section_recognized`/`known_sections`, so a
            misspelled section is distinguishable from an empty one.
          - `count`, `total_count`, `truncated`, `offset`, `limit`.

        **How to name a target when setting it.** Use `shapekey_name`, never
        `name`. `name` is the filename with its extension stripped, for display;
        `shapekey_name` is what MPFB will call the shape key, and therefore the
        only string `TargetService` accepts. The two are equal for most targets
        and **not** for a name over 60 characters, which MPFB encodes to fit
        Blender's shape key name limit - and a caller using `name` there
        addresses nothing at all, silently. For a bundled target, the names
        inside a category's `targets` and `opposites` are already in that form.

        **This is deliberately more current than MPFB's own modeling panels.**
        Those build their target list when their module is imported, which is
        when Blender started, so a target installed since then is missing from
        the Blender UI until it is restarted. This tool scans on every call and
        will report it. Where the two disagree, this one is describing what is
        on disk now.

        **`listed_in_mpfb_ui: false` is also a real difference, not a bug here.**
        MPFB's scan of `<user data>/targets/<section>/` matches only `*.target`,
        so a `*.target.gz` sitting there is on disk and loadable but absent from
        MPFB's panels. Such targets are reported, with the flag saying so. In
        the `custom` section MPFB matches both extensions, so the flag is `true`
        throughout it.
        """
        # `result` (built in codegen/payloads/list_targets.py) is always plain
        # JSON-safe data - every path is coerced with str(), since
        # find_asset_files_matching_pattern() hands back pathlib.Path objects -
        # so strict_json=True to surface a clear error if that stops being true.
        code = codegen.assemble(
            "list_targets.py",
            bootstrap="raising",
            params={
                "section": _validated_text(
                    section, "section",
                    "omit it for the overview of every section"),
                "name_contains": _validated_text(
                    name_contains, "name_contains",
                    "omit it to match every name"),
                "limit": _validated_count(limit, "limit", MAX_LIMIT),
                "offset": _validated_count(offset, "offset", None),
            },
        )
        return send_code(code, strict_json=True)
