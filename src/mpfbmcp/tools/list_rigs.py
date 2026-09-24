"""
The ``mpfb_list_rigs`` tool: which rigs this Blender could add to a character.

The catalogue counterpart to ``mpfb_get_object_info``'s ``rig_type``, which says
what an *existing* armature looks like. The two vocabularies overlap without
being interchangeable, and closing that gap is the reason this tool exists: what
is reported here is, per rig, the exact string an adding function takes, plus
which of two non-interchangeable functions takes it.

Nothing about the rig list is validated on this side of the socket. The
directories are the authority on which rigs exist, and they are only readable
from inside Blender; a list kept here would drift from them silently.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List Available Rigs",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_list_rigs(refresh: bool = False) -> dict[str, object]:
        """
        List every rig this Blender could add to a MakeHuman basemesh: MPFB's
        bundled standard and Rigify rigs, plus custom rigs found in the user's
        data directories. Adds nothing to the scene.

        **Pass a rig's `identifier`, not its `name`, to `mpfb_add_rig`.** The
        two are not the same string: a standard rig is `"default_no_toes"`, a
        Rigify one `"rigify.human"`, a custom one `"custom.my_rig"`. The prefix
        also picks between MPFB's two non-interchangeable adding functions -
        `add_function` says which - and crossing them does not read as the
        mistake it is: a built-in name handed to the custom function comes back
        missing under a mangled one.

        `refresh=true` rescans the user data directories for custom rigs first.
        MPFB caches that list for the lifetime of the Blender session, so a rig
        installed after Blender started will not appear otherwise.

        `result` carries:

          - `rigs`: one entry per rig, with `name`, `identifier`, `family`
            ("standard"/"rigify"/"custom"), `path` (absolute, or null),
            `label`/`description` (MPFB's own UI text, null for custom rigs),
            `add_function`, `available` and `unavailable_reason`.
          - Per entry, what adding it would do about weights: `has_weights`,
            `weights_path` and `weights_from`. **MPFB resolves weights through
            a fallback table, not by filename**, so `weights_from` differs from
            `name` for `default_no_toes` (which borrows `default`'s) and
            `rigify.human` (which borrows `rigify.human_toes`'s). That is
            normal. `has_weights: false` is not: adding that rig produces a
            character with no vertex weights.
          - `count`, `families`, `message`, and `rigify_available` - whether
            Rigify is enabled here. Rigify rigs are listed either way, carrying
            `available: false` when it is not, since adding one then raises
            rather than degrading.
          - `rig_dirs`: every directory looked in, each flagged with whether it
            exists. MPFB scans its own data dir and the user data roots - not
            the MakeHuman user data directory.
          - `unrecognized_custom_rig_files`: `.json` files in a scanned user
            rigs directory that MPFB refused as rig definitions - a name
            outside `[A-Za-z0-9_]`, or no `identifying_bones` key. MPFB drops
            these silently, which otherwise makes "I put the file there and it
            does not show up" undiagnosable.

        **Do not expect this list to match `mpfb_get_object_info`'s
        `rig_type`.** That value comes from MPFB identifying an armature by its
        bone names and can be `rigify_generated.*` or `unknown`, neither of
        which names something addable. A character whose rig is not in this
        list is ordinary, not an error.
        """
        # `result` (built in bridge/mpfb_bridge/commands/list_rigs.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "list_rigs",
            # Not truthiness: refresh="false" would rescan the disk.
            params={"refresh": arguments.validated_flag(refresh, "refresh")},
            # Shared with mpfb_add_rig's command: this tool predicts which rig
            # file would be loaded and whose weights would come with it, and
            # that tool then does it. One implementation, so the prediction and
            # the action cannot drift apart.
        )
