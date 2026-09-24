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
and are scanned per call - by ``bridge/mpfb_bridge/shared/target_categories.py``, which is
also where ``mpfb_set_targets`` and the other two get their vocabulary, so the
catalogue and the tools that act on it cannot disagree about what is installed.

Why the two divergences from MPFB's own panels are reported rather than
suppressed is
[A tool may report a fact MPFB's own UI does not show](../../../specifications/responses.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show).

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

from mpfbmcp import arguments
from mpfbmcp import backend

# A page of 1000 entries is already more than an agent can usefully read; the
# ceiling is here so that an over-broad call is capped rather than answered with
# every target on the system.
MAX_LIMIT = 1000


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
        report each under the name that setting it will require. Changes
        nothing.

        Macro details and phenotype (gender, age, weight, muscle, height,
        proportions) are **not** here: they are attributes on the basemesh
        rather than target files, and are `mpfb_get_macro_details` /
        `mpfb_set_macro_details` territory.

        **The answer is capped.** Check `truncated` before concluding a target
        does not exist; `total_count` says how many matched.

        Arguments, all optional: `section` (a section name from `target.json`
        or synthesized from a user target directory, matched exactly and
        case-insensitively; omit it for the overview), `name_contains`
        (case-insensitive substring, applied to category and target names
        alike), and `limit` (default 200, max 1000) with `offset`, which page
        over a section's `categories` when it has them and over `user_targets`
        otherwise.

        `result` carries:

          - `sections`: every section, each `{name, label, source,
            category_count, target_count}`. Around thirty entries, always
            present. `source` is `"system"`, `"user"`, or `"both"` when a user
            directory shares a bundled section's name - common, and MPFB merges
            the two, so such a section returns both.
          - `categories`: present when `section` named one with bundled
            categories, each `{name, label, has_left_and_right, targets,
            opposites}` from `target.json`. These are what `mpfb_set_targets`'
            `modifiers` entries address, and `opposites` is the `decr`/`incr`
            and left/right pairing behind MPFB's sliders. `null` when no
            section was asked for, or the one asked for is only a user
            directory.
          - `user_targets`: what the user data directories hold, filtered to
            `section` when one was given, each with `name`, `shapekey_name`,
            `path` and `listed_in_mpfb_ui`.
          - `target_json_path`/`target_json_exists` and `system_targets_dir`:
            the bundled index is ~140 KB of JSON and is not returned here - a
            client that can read the Blender host's filesystem should parse it
            directly instead.
          - `unindexed_system_target_dirs`: bundled target directories with no
            `target.json` section, each with a count. The index reads as the
            complete list of bundled targets and is not.
          - `user_target_dirs`: the directories actually scanned, so a target
            that did not appear can be looked for where it was expected.
          - `requested_section`/`section_recognized`/`known_sections`, `count`,
            `total_count`, `truncated`, `offset`, `limit`.

        **How to name a target when setting it.** Use `shapekey_name`, never
        `name`. `name` is the filename with its extension stripped, for
        display; `shapekey_name` is what MPFB calls the shape key and the only
        string it accepts. The two are equal for most targets and **not** above
        60 characters, where MPFB encodes the name - and a caller using `name`
        there addresses nothing at all, silently. Inside a category, `targets`
        and `opposites` are already in that form.

        Two differences from MPFB's own modeling panels, both real rather than
        bugs here: this tool scans per call, so it reports a target installed
        since Blender started, which the panels cannot show until it restarts;
        and `listed_in_mpfb_ui: false` marks a `*.target.gz` outside the
        `custom` section, loadable but skipped by MPFB's own scan.
        """
        # `result` (built in bridge/mpfb_bridge/commands/list_targets.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "list_targets",
            params={
                "section": arguments.validated_text(
                    section, "section",
                    "omit it for the overview of every section"),
                "name_contains": arguments.validated_text(
                    name_contains, "name_contains",
                    "omit it to match every name"),
                "limit": arguments.validated_count(limit, "limit", MAX_LIMIT),
                "offset": arguments.validated_count(offset, "offset", None),
            },
        )
